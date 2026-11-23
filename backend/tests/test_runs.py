import pytest

from backend.tests.test_workflow import decide, start

TODOS = [
    {"task": "Work CLM-1001", "status": "done"},
    {"task": "Work CLM-1002", "status": "in_progress"},
    {"task": "Work CLM-1003", "status": "to_do"},
]


def start_run(client, cap=5):
    return client.post("/api/runs", json={"cap": cap})


def release(client, claim_id, reason="The model timed out"):
    return client.post(f"/api/claims/{claim_id}/release", json={"reason": reason})


def test_start_run(client):
    run = start_run(client).json()
    assert len(run["run_id"]) == 36
    assert run["cap"] == 5
    assert run["started_at"]
    assert run["todos"] == []
    assert run["finished_at"] is None
    assert run["summary"] is None


def test_a_run_needs_a_cap_of_at_least_one(client):
    assert start_run(client, 0).status_code == 422


def test_current_run(client):
    assert client.get("/api/runs/current").json() is None
    start_run(client, 1)
    latest = start_run(client, 2).json()
    assert client.get("/api/runs/current").json() == latest


def test_record_todos(client):
    run_id = start_run(client).json()["run_id"]
    response = client.put(f"/api/runs/{run_id}/todos", json={"todos": TODOS})
    assert response.status_code == 200
    assert client.get("/api/runs/current").json()["todos"] == TODOS


@pytest.mark.parametrize(
    "todo",
    [{"task": "Work CLM-1001", "status": "maybe"}, {"task": "", "status": "done"}],
)
def test_record_todos_checks_each_item(client, todo):
    run_id = start_run(client).json()["run_id"]
    response = client.put(f"/api/runs/{run_id}/todos", json={"todos": [todo]})
    assert response.status_code == 422


def test_finish_run(client):
    run_id = start_run(client).json()["run_id"]
    run = client.post(f"/api/runs/{run_id}/finish", json={"summary": "All done."})
    assert run.json()["summary"] == "All done."
    assert run.json()["finished_at"]
    again = client.post(f"/api/runs/{run_id}/finish", json={"summary": "Again."})
    assert again.status_code == 409


def test_finish_run_needs_a_summary(client):
    run_id = start_run(client).json()["run_id"]
    response = client.post(f"/api/runs/{run_id}/finish", json={"summary": ""})
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("put", "/api/runs/nope/todos", {"todos": []}),
        ("post", "/api/runs/nope/finish", {"summary": "Done."}),
    ],
)
def test_unknown_run(client, method, path, body):
    assert client.request(method, path, json=body).status_code == 404


def test_release_twice_leaves_the_claim_for_a_handler(client):
    start(client, "CLM-1001")
    claim = release(client, "CLM-1001").json()
    assert claim["status"] == "waiting"
    assert claim["failed_attempts"] == 1
    assert start(client, "CLM-1001").status_code == 200
    claim = release(client, "CLM-1001", "The model returned an error").json()
    assert claim["status"] == "needs_handler"
    assert claim["failed_attempts"] == 2
    assert start(client, "CLM-1001").status_code == 409
    summary = client.get("/api/claims").json()[0]
    assert summary["status"] == "needs_handler"
    assert summary["failed_attempts"] == 2


def test_release_records_the_reason_as_a_step(client):
    start(client, "CLM-1001")
    release(client, "CLM-1001")
    steps = client.get("/api/claims/CLM-1001/steps").json()
    assert [(s["kind"], s["content"]) for s in steps] == [
        ("error", "The model timed out")
    ]


def test_release_needs_a_claim_in_progress(client):
    assert release(client, "CLM-1001").status_code == 409
    start(client, "CLM-1001")
    decide(client, "CLM-1001", "refer", 0)
    assert release(client, "CLM-1001").status_code == 409
    assert release(client, "CLM-9999").status_code == 404


def test_release_needs_a_reason(client):
    start(client, "CLM-1001")
    assert release(client, "CLM-1001", "").status_code == 422


@pytest.mark.parametrize("kind", ["read", "error"])
def test_new_step_kinds(client, kind):
    start(client, "CLM-1001")
    response = client.post(
        "/api/claims/CLM-1001/steps", json={"kind": kind, "content": "Something"}
    )
    assert response.status_code == 200
