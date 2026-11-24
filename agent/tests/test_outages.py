import httpx
import pytest
from fastapi.testclient import TestClient

from agent import __main__ as cli
from agent import api, harness
from agent.tests.conftest import BASE_URL
from agent.tests.stubs import call, claim_script, decide, stub
from agent.tests.test_queue_agent import claim_models, finish, tool_replies, work
from backend.main import app

DOWN = httpx.ConnectError("Connection refused")
LOST = httpx.ReadTimeout("No reply")
STOP = claim_script()[-1]


class Flaky(TestClient):
    """A backend that fails the first few requests to one operation."""

    def __init__(self, method, ending, failure, times=1, *, arrives=False):
        super().__init__(app, BASE_URL)
        self.matches = lambda m, url: m == method and str(url).endswith(ending)
        self.failure = failure
        self.left = times
        self.arrives = arrives

    def request(self, method, url, **kwargs):  # type: ignore[override]
        if not self.left or not self.matches(method, url):
            return super().request(method, url, **kwargs)
        self.left -= 1
        if self.arrives:
            super().request(method, url, **kwargs)
        if isinstance(self.failure, Exception):
            raise self.failure
        return self.failure


@pytest.fixture
def flaky(monkeypatch):
    def install(*args, **kwargs):
        backend = Flaky(*args, **kwargs)
        monkeypatch.setattr(api, "client", lambda: backend)
        return backend

    return install


def status(client, claim_id="CLM-1001"):
    return client.get(f"/api/claims/{claim_id}").json()


def test_a_short_outage_is_ridden_out(flaky):
    flaky("POST", "/start", DOWN, times=3)
    assert harness.work_claim("CLM-1001", stub(*claim_script())) == "CLM-1001 refer"


def test_a_request_that_may_have_arrived_is_not_repeated(flaky):
    backend = flaky("POST", "/runs", LOST, times=5)
    with pytest.raises(api.Unreachable, match="ReadTimeout"):
        api.start_run(1)
    assert backend.left == 4


@pytest.mark.parametrize("arrives", [False, True])
def test_an_outage_releasing_a_claim_does_not_stop_the_run(client, flaky, arrives):
    flaky("POST", "/release", LOST, arrives=arrives)
    model = stub(
        *work("CLM-1001"),
        call("finish_run", summary="Too soon."),
        *work("CLM-1001", "CLM-1002"),
        *finish(),
    )
    bad = [ValueError("bad")] * (harness.MODEL_RETRIES + 1)
    claims = claim_models(CLM_1001=[bad, claim_script()], CLM_1002=[claim_script()])
    assert harness.run_queue(2, model, claims) == "Worked the queue."
    assert "ReadTimeout" in tool_replies(model)[0]
    assert status(client)["status"] == "decided"
    assert status(client)["failed_attempts"] == 1
    assert status(client, "CLM-1002")["status"] == "decided"
    assert status(client, "CLM-1003")["status"] == "waiting"


def test_an_outage_starting_a_claim_leaves_nothing_in_progress(client, flaky):
    flaky("POST", "/start", LOST, arrives=True)
    model = stub(
        *work("CLM-1001"),
        call("finish_run", summary="Too soon."),
        *work("CLM-1001"),
        *finish(),
    )
    harness.run_queue(1, model, claim_models(CLM_1001=[[], claim_script()]))
    assert status(client)["status"] == "decided"


@pytest.mark.parametrize("arrives", [False, True])
def test_an_outage_paying_is_put_right_before_finishing(client, flaky, arrives):
    flaky("POST", "/payment", LOST, arrives=arrives)
    model = stub(*work("CLM-1001"), *finish())
    claims = claim_models(CLM_1001=[[decide("approve", 420.0), STOP]])
    assert harness.run_queue(1, model, claims) == "Worked the queue."
    assert status(client)["payment"]["amount"] == 420.0


def test_an_outage_recording_the_to_do_list_does_not_stop_the_run(flaky):
    flaky("PUT", "/todos", LOST)
    model = stub(call("record_todos", todos=[]), *work("CLM-1001"), *finish())
    claims = claim_models(CLM_1001=[claim_script()])
    assert harness.run_queue(1, model, claims) == "Worked the queue."
    assert "ReadTimeout" in tool_replies(model)[0]


def test_an_outage_listing_the_claims_does_not_stop_the_run(flaky):
    backend = flaky("GET", "/claims", LOST, times=0)
    model = stub(call("list_claims"), *work("CLM-1001"), *finish())

    def claims(_):
        return stub(*claim_script())

    start_run = api.start_run

    def start_then_fail(cap):
        backend.left = 1
        return start_run(cap)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(api, "start_run", start_then_fail)
        assert harness.run_queue(1, model, claims) == "Worked the queue."
    assert "ReadTimeout" in tool_replies(model)[0]


@pytest.mark.parametrize("arrives", [False, True])
def test_an_outage_finishing_the_run(client, flaky, arrives):
    flaky("POST", "/finish", LOST, arrives=arrives)
    model = stub(*work("CLM-1001"), call("finish_run", summary="First."), *finish())
    harness.run_queue(1, model, claim_models(CLM_1001=[claim_script()]))
    run = client.get("/api/runs/current").json()
    assert run["summary"] == ("First." if arrives else "Worked the queue.")


def test_a_server_error_without_json_does_not_stop_the_run(client, flaky):
    flaky("POST", "/start", httpx.Response(500, text="Internal Server Error"))
    model = stub(*work("CLM-1001", "CLM-1001"), *finish())
    harness.run_queue(1, model, claim_models(CLM_1001=[[], claim_script()]))
    assert "Internal Server Error" in tool_replies(model)[0]
    assert status(client)["status"] == "decided"


def test_an_error_does_not_free_a_place_under_the_cap(client, flaky):
    flaky("GET", "/claims/CLM-1001", LOST, times=9)
    model = stub(*work("CLM-1001", "CLM-1002"), *[STOP] * 3)
    claims = claim_models(CLM_1001=[[decide("approve", 420.0), STOP]])
    with pytest.raises(api.Unreachable):
        harness.run_queue(1, model, claims)
    assert "capped at 1" in tool_replies(model)[1]
    assert status(client, "CLM-1002")["status"] == "waiting"


def test_the_command_line_says_when_the_backend_is_down(monkeypatch):
    def down(_):
        raise api.Unreachable("Connection refused")

    monkeypatch.setattr(cli, "run_queue", down)
    with pytest.raises(SystemExit, match="can't be reached"):
        cli.main([])
