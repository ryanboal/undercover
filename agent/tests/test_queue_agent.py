import sqlite3
from contextlib import closing

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent import __main__ as cli
from agent import main, queue
from agent.tests.stubs import call, claim_script, stub


@pytest.fixture
def three_waiting(database):
    """Leave only CLM-1001, CLM-1002 and CLM-1003 waiting in the queue."""
    with closing(sqlite3.connect(database)) as db, db:
        db.execute(
            "UPDATE claims SET status = 'decided'"
            " WHERE claim_id NOT IN ('CLM-1001', 'CLM-1002', 'CLM-1003')"
        )


def failures():
    return [ValueError("The provider is down")] * (main.MODEL_RETRIES + 1)


def claim_models(**attempts):
    """A fresh stub claim agent for each attempt at each claim, in order."""
    scripts = {claim_id: list(lines) for claim_id, lines in attempts.items()}
    return lambda claim_id: stub(*scripts[claim_id.replace("-", "_")].pop(0))


def decided(claim_id):
    return claim_script(claim_id, "refer")


def todos(*statuses):
    return [
        {"task": f"Work CLM-100{n}", "status": status}
        for n, status in enumerate(statuses, start=1)
    ]


def work(*claim_ids):
    return [call("work_claim", claim_id=claim_id) for claim_id in claim_ids]


def finish(summary="Worked the queue."):
    return [call("finish_run", summary=summary), AIMessage(content="Finished.")]


def tool_replies(model):
    """The tool results the queue agent saw, in order."""
    return [m.text for m in model.prompts[-1] if m.type == "tool"]


def test_the_queue_agent_has_four_tools():
    run = queue.Run("run-1", 5, lambda _: stub())
    names = [t.name for t in queue.queue_tools(run)]
    assert names == ["list_claims", "record_todos", "work_claim", "finish_run"]


def test_a_whole_run(client, three_waiting):
    model = stub(
        call("list_claims"),
        call("record_todos", todos=todos("to_do", "to_do", "to_do")),
        *work("CLM-1001", "CLM-1002", "CLM-1003"),
        call("record_todos", todos=todos("done", "done", "done")),
        *finish("Worked 3 claims: 3 referred."),
    )
    claims = claim_models(
        CLM_1001=[decided("CLM-1001")],
        CLM_1002=[decided("CLM-1002")],
        CLM_1003=[decided("CLM-1003")],
    )
    assert queue.run_queue(5, model, claims) == "Worked 3 claims: 3 referred."

    run = client.get("/api/runs/current").json()
    assert run["cap"] == 5
    assert run["todos"] == todos("done", "done", "done")
    assert run["finished_at"]

    system, first = model.prompts[0][:2]
    assert isinstance(system, SystemMessage)
    assert system.content == client.get("/api/instructions").json()["queue"]
    assert first.text == "Run the queue. This run is capped at 5 claims."

    replies = tool_replies(model)
    assert "CLM-1001  waiting  trip_delay  $420.00  submitted 2026-06-24" in replies[0]
    assert replies[1] == "Saved 3 items."
    assert replies[2:5] == ["CLM-1001 refer", "CLM-1002 refer", "CLM-1003 refer"]
    assert replies[-1] == "The run is finished."

    threads = set()
    for claim_id in ("CLM-1001", "CLM-1002", "CLM-1003"):
        claim = client.get(f"/api/claims/{claim_id}").json()
        assert claim["status"] == "decided"
        steps = client.get(f"/api/claims/{claim_id}/steps").json()
        assert {s["thread_id"] for s in steps} == {claim["thread_id"]}
        threads.add(claim["thread_id"])
    assert len(threads) == 3


def test_the_cap(client, three_waiting):
    model = stub(*work("CLM-1001", "CLM-1002", "CLM-1003"), *finish())
    claims = claim_models(
        CLM_1001=[decided("CLM-1001")], CLM_1002=[decided("CLM-1002")]
    )
    queue.run_queue(2, model, claims)

    refusal = tool_replies(model)[2]
    assert refusal == (
        "Refused: the run is capped at 2 claims and has worked CLM-1001, CLM-1002"
    )
    assert client.get("/api/claims/CLM-1003").json()["status"] == "waiting"
    assert client.get("/api/claims/CLM-1003/steps").json() == []
    assert client.get("/api/runs/current").json()["summary"] == "Worked the queue."


def test_a_failed_claim_does_not_stop_the_run_and_is_retried(client, three_waiting):
    model = stub(
        *work("CLM-1001", "CLM-1002", "CLM-1003"),
        call("finish_run", summary="Too soon."),
        *work("CLM-1002"),
        *finish(),
    )
    claims = claim_models(
        CLM_1001=[decided("CLM-1001")],
        CLM_1002=[failures(), decided("CLM-1002")],
        CLM_1003=[decided("CLM-1003")],
    )
    queue.run_queue(3, model, claims)

    replies = tool_replies(model)
    assert replies[1] == (
        "CLM-1002 failed (ValueError: The provider is down), back in the queue"
    )
    assert replies[3] == (
        "Refused: these waiting claims can still be worked in this run: CLM-1002."
        " Work them, then finish."
    )
    assert replies[4] == "CLM-1002 refer"
    for claim_id in ("CLM-1001", "CLM-1002", "CLM-1003"):
        assert client.get(f"/api/claims/{claim_id}").json()["status"] == "decided"
    assert client.get("/api/claims/CLM-1002").json()["failed_attempts"] == 1


def test_a_claim_that_fails_twice_is_left_for_a_handler(client, three_waiting):
    model = stub(*work("CLM-1001", "CLM-1001"), *finish())
    claims = claim_models(CLM_1001=[failures(), failures()])
    queue.run_queue(1, model, claims)

    assert tool_replies(model)[1].endswith("left for a handler")
    assert client.get("/api/claims/CLM-1001").json()["status"] == "needs_handler"
    assert client.get("/api/runs/current").json()["summary"] == "Worked the queue."


def test_the_check_for_missed_claims(client, three_waiting):
    model = stub(
        *work("CLM-1001", "CLM-1002"),
        call("finish_run", summary="Too soon."),
        *work("CLM-1003"),
        *finish(),
    )
    claims = claim_models(
        CLM_1001=[decided("CLM-1001")],
        CLM_1002=[decided("CLM-1002")],
        CLM_1003=[decided("CLM-1003")],
    )
    queue.run_queue(3, model, claims)

    assert tool_replies(model)[2] == (
        "Refused: these waiting claims can still be worked in this run: CLM-1003."
        " Work them, then finish."
    )
    assert client.get("/api/claims/CLM-1003").json()["status"] == "decided"
    assert client.get("/api/runs/current").json()["summary"] == "Worked the queue."


def test_a_queue_agent_that_stops_early_is_told_to_carry_on(client, three_waiting):
    model = stub(
        AIMessage(content="I'll stop here."),
        *work("CLM-1001"),
        *finish(),
    )
    queue.run_queue(1, model, claim_models(CLM_1001=[decided("CLM-1001")]))

    nudges = [m for m in model.prompts[-1] if isinstance(m, HumanMessage)]
    assert nudges[-1].text == queue.CARRY_ON
    assert client.get("/api/runs/current").json()["summary"] == "Worked the queue."


def test_a_queue_agent_that_never_finishes(client, three_waiting):
    model = stub(*[AIMessage(content="Hmm.")] * (1 + queue.NUDGES))
    summary = queue.run_queue(1, model, claim_models())
    assert summary == "The agent stopped before finishing the run."
    assert client.get("/api/runs/current").json()["finished_at"]


def test_a_queue_agent_that_fails(client, three_waiting):
    summary = queue.run_queue(1, stub(*failures()), claim_models())
    assert summary == (
        "The agent stopped before finishing the run. ValueError: The provider is down"
    )


def test_claims_left_in_progress_are_released_first(client, database):
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE claims SET status = 'decided' WHERE claim_id != 'CLM-1001'")
    client.post("/api/claims/CLM-1001/start", json={"thread_id": "crashed"})

    model = stub(*work("CLM-1001"), *finish())
    queue.run_queue(None, model, claim_models(CLM_1001=[decided("CLM-1001")]))

    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "decided"
    assert claim["failed_attempts"] == 1
    steps = client.get("/api/claims/CLM-1001/steps").json()
    assert (steps[0]["kind"], steps[0]["content"]) == ("error", queue.STALE)
    assert client.get("/api/runs/current").json()["cap"] == 1


def test_without_a_cap_the_run_may_work_every_waiting_claim(client, three_waiting):
    queue.run_queue(None, stub(*finish()), claim_models())
    assert client.get("/api/runs/current").json()["cap"] == 3


def test_command_line_runs_the_queue(monkeypatch, capsys, three_waiting):
    model = stub(*work("CLM-1001", "CLM-1002"), *finish("Worked 2 claims."))
    claims = claim_models(
        CLM_1001=[decided("CLM-1001")], CLM_1002=[decided("CLM-1002")]
    )
    monkeypatch.setattr(
        cli, "run_queue", lambda cap: queue.run_queue(cap, model, claims)
    )
    cli.main(["--cap", "2"])
    assert capsys.readouterr().out.splitlines() == [
        "CLM-1001 refer",
        "CLM-1002 refer",
        "",
        "Worked 2 claims.",
    ]


def test_command_line_works_one_claim(monkeypatch, capsys):
    monkeypatch.setattr(cli, "work_claim", lambda claim_id: f"{claim_id} refer")
    cli.main(["CLM-1001"])
    assert capsys.readouterr().out == "CLM-1001 refer\n"
