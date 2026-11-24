"""The claim agent, which works one claim from a clean start."""

import json
import os
import uuid
from typing import Any

import httpx
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
    ToolRetryMiddleware,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr

from agent.tools import CLAIM_TOOLS, request

load_dotenv(override=True)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"
MODEL_TIMEOUT = 120
MODEL_RETRIES = 3
RETRY_DELAY = 2.0
CLAIM_CALL_LIMIT = 25


def model() -> ChatOpenAI:
    """Return the model named in MODEL_NAME, or DeepSeek V4.1 Flash by default."""
    name = os.getenv("MODEL_NAME")
    return ChatOpenAI(
        model=name or DEFAULT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        reasoning_effort=None if name else "low",
        timeout=MODEL_TIMEOUT,
        max_retries=0,
    )


def model_retry() -> ModelRetryMiddleware:
    """Retry a timeout or an error from the model provider, then give up."""
    return ModelRetryMiddleware(
        max_retries=MODEL_RETRIES, on_failure="error", initial_delay=RETRY_DELAY
    )


class BackendError(Exception):
    """The backend refused a request the agent's run depends on."""


def call_backend(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    """Call the backend and return its JSON, raising if it refuses."""
    response = request(method, path, body)
    if response.is_error:
        raise BackendError(f"{response.status_code}: {response.json()['detail']}")
    return response.json()


def steps(message: AnyMessage) -> list[tuple[str, str]]:
    """Turn one message from the agent's run into steps for the dashboard."""
    if isinstance(message, ToolMessage):
        if message.name == "read_section" and not message.text.startswith("Refused"):
            return [("read", message.text)]
        return [("tool_result", f"{message.name}: {message.text}")]
    found = []
    if message.text:
        found.append(("message", message.text))
    if isinstance(message, AIMessage):
        for call in message.tool_calls:
            args = ", ".join(f"{k}={json.dumps(v)}" for k, v in call["args"].items())
            found.append(("tool_call", f"{call['name']}({args})"))
    return found


def run_claim_agent(claim_id: str, thread_id: str, llm: BaseChatModel) -> None:
    """Run a fresh claim agent on a started claim, recording each step."""
    instructions = call_backend("GET", "/api/instructions")["claim"]
    middleware: list[AgentMiddleware[Any, Any]] = [
        ModelCallLimitMiddleware(run_limit=CLAIM_CALL_LIMIT, exit_behavior="error"),
        model_retry(),
        ToolRetryMiddleware(
            retry_on=(httpx.TransportError,),
            on_failure="error",
            initial_delay=RETRY_DELAY,
        ),
    ]
    agent = create_agent(
        llm,
        tools=CLAIM_TOOLS,
        system_prompt=instructions,
        middleware=middleware,
        checkpointer=InMemorySaver(),
    )
    states = agent.stream(
        {"messages": [{"role": "user", "content": f"Claim {claim_id}"}]},
        config={"configurable": {"thread_id": thread_id}},
        stream_mode="values",
    )
    messages = next(states)["messages"]
    for state in states:
        for message in state["messages"][len(messages) :]:
            for kind, content in steps(message):
                call_backend(
                    "POST",
                    f"/api/claims/{claim_id}/steps",
                    {"kind": kind, "content": content},
                )
        messages = state["messages"]


def outcome(claim: dict[str, Any]) -> str:
    """Describe a decided claim in a line."""
    decision = claim["decision"]
    if decision["decision"] != "approve":
        return f"{claim['claim_id']} {decision['decision']}"
    if claim["payment"] is not None:
        payment = "paid"
    elif claim["status"] == "waiting_for_sign_off":
        payment = "held for sign-off"
    else:
        payment = "not paid"
    return f"{claim['claim_id']} approve ${decision['payout']:,.2f}, {payment}"


def pay_if_due(claim: dict[str, Any]) -> dict[str, Any]:
    """Pay an approval within the limit that was left unpaid, and return the claim."""
    decision = claim["decision"]
    if (
        claim["status"] != "decided"
        or decision["decision"] != "approve"
        or claim["payment"] is not None
    ):
        return claim
    path = f"/api/claims/{claim['claim_id']}"
    request("POST", f"{path}/payment", {"amount": decision["payout"]})
    return call_backend("GET", path)


def work_claim(claim_id: str, llm: BaseChatModel | None = None) -> str:
    """Work one claim with a fresh claim agent and report the outcome in a line."""
    thread_id = str(uuid.uuid4())
    started = request("POST", f"/api/claims/{claim_id}/start", {"thread_id": thread_id})
    if started.is_error:
        return f"{claim_id} not started: {started.json()['detail']}"
    reason = "The agent finished without recording a decision"
    try:
        run_claim_agent(claim_id, thread_id, llm or model())
    except Exception as error:  # any failure puts the claim back in the queue
        reason = f"{type(error).__name__}: {error}"[:300]
    claim = call_backend("GET", f"/api/claims/{claim_id}")
    if claim["status"] != "in_progress":
        return outcome(pay_if_due(claim))
    claim = call_backend("POST", f"/api/claims/{claim_id}/release", {"reason": reason})
    if claim["status"] == "needs_handler":
        return f"{claim_id} failed twice ({reason}), left for a handler"
    return f"{claim_id} failed ({reason}), back in the queue"
