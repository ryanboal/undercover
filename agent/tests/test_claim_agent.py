from itertools import count

import pytest
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from openai import APITimeoutError

from agent import api, harness
from agent.rules import NotStarted
from agent.tests.stubs import StubModel, call, claim_script, decide, stub
from agent.tools import CLAIM_TOOLS, QUEUE_TOOLS


def failures(text):
    """Enough errors to outlast the retries."""
    return [ValueError(text)] * (harness.MODEL_RETRIES + 1)


def operation_ids(client):
    return {
        operation["operationId"]
        for path in client.get("/openapi.json").json()["paths"].values()
        for operation in path.values()
    }


def test_tools_are_named_after_backend_operations(client):
    names = [t.name for t in CLAIM_TOOLS]
    assert names == [
        "get_claim",
        "get_policy",
        "get_claim_history",
        "search_documents",
        "read_section",
        "record_decision",
        "pay_claim",
    ]
    assert set(names) <= operation_ids(client)


def test_claim_instructions_hold_the_contents_not_the_documents(client):
    instructions = client.get("/api/instructions").json()
    assert instructions["queue"].startswith("# UnderCover Agent: running the queue")
    claim = instructions["claim"]
    assert claim.startswith("# UnderCover Agent: working a claim")
    assert claim.endswith("- 14. Records\n")
    assert "- 10. How we work out your payment" in claim
    assert "- 9. Repeat claims" in claim
    assert "Worked example 1" not in claim
    assert "Monkeys, gulls" not in claim


def test_work_claim_looks_things_up_decides_and_pays(client):
    model = stub(
        call("get_claim"),
        call("get_policy", policy_id="POL-2001"),
        call("get_claim_history", customer_id="CUS-3001"),
        call("search_documents", query="third claim in 12 months"),
        call("read_section", document="manual", number="9"),
        decide("approve", 420.0),
        call("pay_claim", text="Paying now.", amount=420.0),
        AIMessage(content="Approved for $420.00."),
    )
    assert harness.work_claim("CLM-1001", model) == "CLM-1001 approve $420.00, paid"

    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "decided"
    assert claim["payment"]["amount"] == 420.0

    steps = client.get("/api/claims/CLM-1001/steps").json()
    assert {s["thread_id"] for s in steps} == {claim["thread_id"]}
    kinds = [s["kind"] for s in steps]
    assert kinds == [
        *(["tool_call", "tool_result"] * 4),
        "tool_call",
        "read",
        "tool_call",
        "tool_result",
        "message",
        "tool_call",
        "tool_result",
        "message",
    ]
    assert steps[0]["content"] == "get_claim()"
    assert '"number": "9"' in steps[7]["content"]
    read = steps[9]["content"]
    assert read.startswith("Claims manual, section 9: Repeat claims\n\n")
    assert "third claim within any 12 month period" in read
    assert steps[-1]["content"] == "Approved for $420.00."


def test_the_system_prompt_is_the_claim_instructions(client):
    model = stub(*claim_script())
    harness.work_claim("CLM-1003", model)
    system = model.prompts[0][0]
    assert isinstance(system, SystemMessage)
    assert system.content == client.get("/api/instructions").json()["claim"]


def test_an_unknown_section_is_refused_as_a_tool_result(client):
    model = stub(
        call("read_section", document="manual", number="99"),
        *claim_script(),
    )
    harness.work_claim("CLM-1003", model)
    steps = client.get("/api/claims/CLM-1003/steps").json()
    assert steps[1]["kind"] == "tool_result"
    assert steps[1]["content"].startswith("read_section: Refused with status 404")


def test_a_payout_over_the_limit_is_held(client):
    model = stub(
        *claim_script(
            "approve",
            1350.0,
            call("pay_claim", amount=1350.0),
        )
    )
    line = harness.work_claim("CLM-1002", model)
    assert line == "CLM-1002 approve $1,350.00, held for sign-off"
    refusal = model.prompts[-1][-1]
    assert isinstance(refusal, ToolMessage)
    assert "needs a handler's sign-off" in refusal.text
    assert client.get("/api/claims/CLM-1002").json()["payment"] is None


def test_an_approval_the_agent_left_unpaid_is_paid(client):
    model = stub(*claim_script("approve", 420.0))
    assert harness.work_claim("CLM-1001", model) == "CLM-1001 approve $420.00, paid"
    assert client.get("/api/claims/CLM-1001").json()["payment"]["amount"] == 420.0


def test_a_failure_between_approving_and_paying_is_put_right(client):
    model = stub(decide("approve", 420.0), *failures("too late"))
    assert harness.work_claim("CLM-1001", model) == "CLM-1001 approve $420.00, paid"
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["payment"]["amount"] == 420.0
    assert claim["failed_attempts"] == 0


def test_an_unpaid_approval_over_the_limit_is_still_held(client):
    model = stub(*claim_script("approve", 1350.0))
    line = harness.work_claim("CLM-1002", model)
    assert line == "CLM-1002 approve $1,350.00, held for sign-off"
    assert client.get("/api/claims/CLM-1002").json()["payment"] is None


@pytest.mark.parametrize("decision", ["decline", "refer"])
def test_declines_and_referrals(client, decision):
    line = harness.work_claim("CLM-1003", stub(*claim_script(decision)))
    assert line == f"CLM-1003 {decision}"
    claim = client.get("/api/claims/CLM-1003").json()
    assert claim["status"] == "decided"
    assert claim["payment"] is None


def test_a_failed_claim_goes_back_in_the_queue(client):
    model = stub(call("get_claim"), *failures("nonsense"))
    line = harness.work_claim("CLM-1001", model)
    assert line == ("CLM-1001 failed (ValueError: nonsense), back in the queue")
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "waiting"
    assert claim["failed_attempts"] == 1
    steps = client.get("/api/claims/CLM-1001/steps").json()
    assert steps[-1] == steps[-1] | {
        "kind": "error",
        "content": "ValueError: nonsense",
    }
    assert len(model.prompts) == 1 + harness.MODEL_RETRIES + 1


def test_a_claim_that_fails_twice_is_left_for_a_handler(client):
    harness.work_claim("CLM-1001", stub(*failures("first")))
    line = harness.work_claim("CLM-1001", stub(*failures("second")))
    assert line == "CLM-1001 failed twice (ValueError: second), left for a handler"
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "needs_handler"
    assert claim["failed_attempts"] == 2
    assert [s["kind"] for s in client.get("/api/claims/CLM-1001/steps").json()].count(
        "error"
    ) == 2


def test_ending_without_a_decision_is_a_failure(client):
    line = harness.work_claim("CLM-1001", stub(call("get_claim"), AIMessage("Hmm.")))
    assert line == (
        "CLM-1001 failed (The agent finished without recording a decision),"
        " back in the queue"
    )
    assert client.get("/api/claims/CLM-1001").json()["status"] == "waiting"


def test_a_provider_error_is_retried(client):
    timeout = APITimeoutError(request=None)  # type: ignore[arg-type]
    model = stub(timeout, *claim_script())
    assert harness.work_claim("CLM-1003", model) == "CLM-1003 refer"


def test_a_looping_claim_agent_hits_the_call_limit(client):
    ids = count()
    model = StubModel(messages=(call("get_claim") for _ in ids))
    line = harness.work_claim("CLM-1001", model)
    assert line.startswith("CLM-1001 failed (ModelCallLimitExceededError")
    assert line.endswith("back in the queue")
    assert next(ids) == harness.CLAIM_CALL_LIMIT


def test_a_decided_claim_is_never_worked_again(client):
    harness.work_claim(
        "CLM-1001",
        stub(
            *claim_script(
                "approve",
                420.0,
                call("pay_claim", amount=420.0),
            )
        ),
    )
    before = client.get("/api/claims/CLM-1001").json()
    with pytest.raises(NotStarted, match="CLM-1001 not started.*is not waiting"):
        harness.work_claim("CLM-1001", stub(*claim_script("decline")))
    assert client.get("/api/claims/CLM-1001").json() == before


def test_model_name(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    default = harness.model()
    assert default.model_name == "deepseek/deepseek-v4.1-flash"
    assert default.reasoning_effort == "low"
    monkeypatch.setenv("MODEL_NAME", "openrouter/free")
    chosen = harness.model()
    assert chosen.model_name == "openrouter/free"
    assert chosen.reasoning_effort is None


def test_a_claim_agent_can_only_act_on_its_own_claim(client):
    client.post("/api/claims/CLM-1001/start", json={"thread_id": "other"})
    sneaky = decide("approve", 420.0)
    sneaky.tool_calls[0]["args"]["claim_id"] = "CLM-1001"
    harness.work_claim("CLM-1003", stub(sneaky, claim_script()[-1]))
    assert client.get("/api/claims/CLM-1001").json()["decision"] is None
    assert client.get("/api/claims/CLM-1003").json()["decision"] is not None


def test_the_model_never_sees_what_the_code_knows():
    for tool in [*CLAIM_TOOLS, *QUEUE_TOOLS]:
        arguments = convert_to_openai_tool(tool)["function"]["parameters"]["properties"]
        assert not {"runtime", "run_id"} & set(arguments), tool.name
    for tool in CLAIM_TOOLS:
        assert "claim_id" not in tool.args, tool.name


@pytest.mark.parametrize("odd", ["../claims", "POL-2001/../../runs", "a?b=c", ".."])
def test_an_odd_id_cannot_reach_another_operation(odd):
    with pytest.raises(api.Refused, match="404"):
        api.get_policy(odd)
