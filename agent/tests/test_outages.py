import httpx
import pytest
from fastapi.testclient import TestClient

from agent import __main__ as cli
from agent import main, queue, tools
from agent.tests.stubs import call, claim_script, decide, stub
from agent.tests.test_queue_agent import claim_models, finish, tool_replies, work
from backend.main import app


class Flaky(TestClient):
    """A backend that fails the first few requests to one path."""

    def __init__(self, method, path, error, times=1, *, lost=False):
        super().__init__(app)
        self.match = (method, path)
        self.error = error
        self.left = times
        self.lost = lost

    def request(self, method, url, **kwargs):  # type: ignore[override]
        if (method, url) == self.match and self.left:
            self.left -= 1
            if self.lost:
                super().request(method, url, **kwargs)
            raise self.error
        return super().request(method, url, **kwargs)


@pytest.fixture
def flaky(monkeypatch):
    def install(*args, **kwargs):
        backend = Flaky(*args, **kwargs)
        monkeypatch.setattr(tools, "backend", lambda: backend)
        return backend

    return install


DOWN = httpx.ConnectError("Connection refused")
LOST = httpx.ReadTimeout("No reply")
REFER = {"CLM_1001": [claim_script("CLM-1001")]}


def status(client, claim_id="CLM-1001"):
    return client.get(f"/api/claims/{claim_id}").json()


def test_a_short_outage_is_ridden_out(client, flaky):
    flaky("POST", "/api/claims/CLM-1001/start", DOWN, times=3)
    line = main.work_claim("CLM-1001", stub(*claim_script("CLM-1001")))
    assert line == "CLM-1001 refer"


def test_a_request_that_may_have_arrived_is_not_repeated(flaky):
    backend = flaky("POST", "/api/runs", LOST, times=5)
    with pytest.raises(httpx.ReadTimeout):
        tools.request("POST", "/api/runs", {"cap": 1})
    assert backend.left == 4


@pytest.mark.parametrize("lost", [False, True])
def test_an_outage_releasing_a_claim_does_not_stop_the_run(client, flaky, lost):
    flaky("POST", "/api/claims/CLM-1001/release", LOST, lost=lost)
    model = stub(
        *work("CLM-1001"),
        call("finish_run", summary="Too soon."),
        *work("CLM-1001", "CLM-1002"),
        *finish(),
    )
    bad = [ValueError("bad")] * (main.MODEL_RETRIES + 1)
    claims = claim_models(
        CLM_1001=[bad, claim_script("CLM-1001")],
        CLM_1002=[claim_script("CLM-1002")],
    )
    assert queue.run_queue(2, model, claims) == "Worked the queue."
    assert "ReadTimeout" in tool_replies(model)[0]
    assert status(client)["status"] == "decided"
    assert status(client)["failed_attempts"] == 1
    assert status(client, "CLM-1002")["status"] == "decided"
    assert status(client, "CLM-1003")["status"] == "waiting"


def test_an_outage_starting_a_claim_leaves_nothing_in_progress(client, flaky):
    flaky("POST", "/api/claims/CLM-1001/start", LOST, lost=True)
    model = stub(
        *work("CLM-1001"),
        call("finish_run", summary="Too soon."),
        *work("CLM-1001"),
        *finish(),
    )
    queue.run_queue(1, model, claim_models(CLM_1001=[[], claim_script("CLM-1001")]))
    assert status(client)["status"] == "decided"


@pytest.mark.parametrize("lost", [False, True])
def test_an_outage_paying_is_put_right_before_finishing(client, flaky, lost):
    flaky("POST", "/api/claims/CLM-1001/payment", LOST, lost=lost)
    model = stub(*work("CLM-1001"), *finish())
    claims = claim_models(
        CLM_1001=[
            [
                decide("CLM-1001", "approve", 420.0),
                call("get_claim", claim_id="CLM-1001"),
                *claim_script("CLM-1001")[-1:],
            ]
        ]
    )
    assert queue.run_queue(1, model, claims) == "Worked the queue."
    assert status(client)["payment"]["amount"] == 420.0


@pytest.mark.parametrize(
    ("method", "path", "tool"),
    [
        ("GET", "/api/claims", call("list_claims")),
        ("PUT", None, call("record_todos", todos=[])),
    ],
)
def test_an_outage_in_another_tool_does_not_stop_the_run(
    client, monkeypatch, method, path, tool
):
    real = tools.backend
    broken = []

    class Break(TestClient):
        def request(self, m, url, **kwargs):  # type: ignore[override]
            started = client.get("/api/runs/current").json() is not None
            if started and m == method and path in (None, url) and not broken:
                broken.append(url)
                raise LOST
            return real().request(m, url, **kwargs)

    monkeypatch.setattr(tools, "backend", lambda: Break(app))
    model = stub(tool, *work("CLM-1001"), *finish())
    assert queue.run_queue(1, model, claim_models(**REFER)) == "Worked the queue."
    assert "ReadTimeout" in tool_replies(model)[0]


@pytest.mark.parametrize("lost", [False, True])
def test_an_outage_finishing_the_run(client, monkeypatch, lost):
    real = tools.backend
    broken = []

    class Break(TestClient):
        def request(self, m, url, **kwargs):  # type: ignore[override]
            if url.endswith("/finish") and not broken:
                broken.append(url)
                if lost:
                    real().request(m, url, **kwargs)
                raise LOST
            return real().request(m, url, **kwargs)

    monkeypatch.setattr(tools, "backend", lambda: Break(app))
    model = stub(*work("CLM-1001"), call("finish_run", summary="First."), *finish())
    queue.run_queue(1, model, claim_models(**REFER))
    run = client.get("/api/runs/current").json()
    assert run["summary"] == ("First." if lost else "Worked the queue.")


def test_a_server_error_without_json_does_not_stop_the_run(client, monkeypatch):
    real = tools.backend
    broken = []

    class Break(TestClient):
        def request(self, m, url, **kwargs):  # type: ignore[override]
            if url.endswith("/start") and not broken:
                broken.append(url)
                return httpx.Response(500, text="Internal Server Error")
            return real().request(m, url, **kwargs)

    monkeypatch.setattr(tools, "backend", lambda: Break(app))
    model = stub(*work("CLM-1001", "CLM-1001"), *finish())
    queue.run_queue(1, model, claim_models(CLM_1001=[[], claim_script("CLM-1001")]))
    assert "Internal Server Error" in tool_replies(model)[0]
    assert status(client)["status"] == "decided"


def test_an_error_does_not_free_a_place_under_the_cap(client, flaky):
    stop = claim_script("CLM-1001")[-1]
    flaky("GET", "/api/claims/CLM-1001", LOST, times=9)
    model = stub(*work("CLM-1001", "CLM-1002"), *[stop] * 3)
    with pytest.raises(httpx.ReadTimeout):
        queue.run_queue(
            1,
            model,
            claim_models(CLM_1001=[[decide("CLM-1001", "approve", 420.0), stop]]),
        )
    assert "capped at 1" in tool_replies(model)[1]
    assert status(client, "CLM-1002")["status"] == "waiting"


def test_the_command_line_says_when_the_backend_is_down(monkeypatch):
    def down(_):
        raise DOWN

    monkeypatch.setattr(cli, "run_queue", down)
    with pytest.raises(SystemExit, match="can't be reached"):
        cli.main([])
