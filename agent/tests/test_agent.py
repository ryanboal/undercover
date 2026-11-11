from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

import agent.__main__ as cli
from agent import main
from backend.main import app

client = TestClient(app)


class StubModel(GenericFakeChatModel):
    """A chat model that gives scripted replies in place of a real model."""

    def bind_tools(self, tools, **kwargs):
        return self


def calls(*tool_calls):
    """An AI message that calls each (name, args) tool in turn."""
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": args, "id": f"call-{i}"}
            for i, (name, args) in enumerate(tool_calls)
        ],
    )


def decide(claim_id, decision, payout):
    return calls(
        (
            "decide_claim",
            {
                "claim_id": claim_id,
                "decision": decision,
                "payout": payout,
                "reason": "The reason.",
                "policy_section": "Section 3, Trip Delay",
            },
        )
    )


def stub(*replies):
    return StubModel(messages=iter(replies))


def steps(claim_id):
    return [
        (step["kind"], step["text"])
        for step in client.get(f"/api/claims/{claim_id}/steps").json()
    ]


def test_an_approval_within_the_limit_is_paid_and_every_step_recorded():
    reply = main.run(
        "CLM-1001",
        "thread-1",
        stub(
            calls(("get_claim", {"claim_id": "CLM-1001"})),
            calls(
                ("get_policy", {"policy_id": "POL-2001"}),
                ("get_claim_history", {"customer_id": "CUS-3001"}),
            ),
            decide("CLM-1001", "approve", 420),
            calls(("pay_claim", {"claim_id": "CLM-1001", "amount": 420})),
            AIMessage(content="Approved CLM-1001 and paid $420.00."),
        ),
    )
    assert reply == "Approved CLM-1001 and paid $420.00."
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "decided"
    assert claim["payment"]["paid_by"] == "UnderCover Agent"
    recorded = steps("CLM-1001")
    assert [kind for kind, _ in recorded] == [
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_call",
        "tool_result",
        "tool_result",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "message",
    ]
    assert recorded[0][1] == 'get_claim(claim_id="CLM-1001")'
    assert recorded[1][1].startswith('get_claim: {"claim_id":"CLM-1001"')
    assert recorded[2][1] == 'get_policy(policy_id="POL-2001")'
    assert recorded[4][1].startswith("get_policy: ")
    assert recorded[5][1].startswith('get_claim_history: [{"claim_id":"CLM-0412"')
    assert recorded[-1] == ("message", "Approved CLM-1001 and paid $420.00.")


def test_the_agent_cannot_pay_a_payout_over_the_limit():
    main.run(
        "CLM-1003",
        "thread-1",
        stub(
            decide("CLM-1003", "approve", 1150),
            calls(("pay_claim", {"claim_id": "CLM-1003", "amount": 1150})),
            AIMessage(content="Approved CLM-1003; it waits for sign-off."),
        ),
    )
    claim = client.get("/api/claims/CLM-1003").json()
    assert claim["status"] == "waiting_for_sign_off"
    assert claim["payment"] is None
    assert (
        "tool_result",
        "pay_claim: Refused: A payout over $1,000.00 needs a handler's sign-off",
    ) in steps("CLM-1003")


def test_a_decline_is_decided_with_no_payment():
    main.run(
        "CLM-1004",
        "thread-1",
        stub(decide("CLM-1004", "decline", 0), AIMessage(content="Declined.")),
    )
    claim = client.get("/api/claims/CLM-1004").json()
    assert claim["status"] == "decided"
    assert claim["decision"]["decision"] == "decline"
    assert claim["payment"] is None


def test_the_system_prompt_comes_from_the_api(monkeypatch):
    prompts = []
    create_agent = main.create_agent

    def spy(model, tools, system_prompt):
        prompts.append(system_prompt)
        return create_agent(model, tools=tools, system_prompt=system_prompt)

    monkeypatch.setattr(main, "create_agent", spy)
    main.run("CLM-1001", "thread-1", stub(AIMessage(content="Done.")))
    assert prompts == [client.get("/api/instructions").json()["instructions"]]


def test_the_instructions_are_followed_by_the_policy_wording():
    instructions = client.get("/api/instructions").json()["instructions"]
    assert instructions.startswith("# The UnderCover Agent")
    assert "# UnderCover Travel Insurance: Policy Wording" in instructions
    assert "## 12. Definitions" in instructions


def test_a_message_with_text_and_tool_calls_makes_a_step_for_each():
    message = AIMessage(
        content="Reading the claim.",
        tool_calls=[{"name": "get_claim", "args": {"claim_id": "CLM-1"}, "id": "1"}],
    )
    assert main.steps_of(message) == [
        ("message", "Reading the claim."),
        ("tool_call", 'get_claim(claim_id="CLM-1")'),
    ]


def test_the_command_works_only_the_waiting_claims(monkeypatch, capsys):
    worked = []
    monkeypatch.setattr(cli, "run", lambda claim_id, _: worked.append(claim_id) or "ok")
    client.post("/api/claims/CLM-1001/start")
    cli.main([])
    assert worked == [f"CLM-{n}" for n in range(1002, 1026)]
    assert "CLM-1002: ok" in capsys.readouterr().out


def test_the_command_works_the_named_claims(monkeypatch):
    worked = []
    monkeypatch.setattr(cli, "run", lambda claim_id, _: worked.append(claim_id) or "ok")
    cli.main(["CLM-1007"])
    assert worked == ["CLM-1007"]


def test_model_name(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    assert main.model().model_name == "openai/gpt-6-luna"
    monkeypatch.setenv("MODEL_NAME", "openrouter/free")
    assert main.model().model_name == "openrouter/free"
