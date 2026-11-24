"""The harness: the model, the two agents and how they run."""

import os
import uuid
from collections.abc import Callable
from typing import Any

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
    ToolCallRequest,
    ToolErrorMiddleware,
    ToolRetryMiddleware,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr

from agent import api, rules
from agent.api import BackendError, Refused, Unreachable
from agent.context import ClaimContext, RunContext
from agent.steps import steps
from agent.tools import CLAIM_TOOLS, QUEUE_TOOLS

load_dotenv(override=True)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"
MODEL_TIMEOUT = 120
MODEL_RETRIES = 3
RETRY_DELAY = 2.0
CLAIM_CALL_LIMIT = 25
NUDGES = 2
NO_DECISION = "The agent finished without recording a decision"
CARRY_ON = (
    "You haven't finished the run. Carry on with the queue, and call finish_run"
    " when every claim is done or left for a handler."
)

type Middleware = list[AgentMiddleware[Any, Any]]


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


def describe(error: Exception) -> str:
    """Describe an error briefly."""
    return f"{type(error).__name__}: {error}"[:300]


def model_retry() -> ModelRetryMiddleware:
    """Retry a timeout or an error from the model provider, then give up."""
    return ModelRetryMiddleware(
        max_retries=MODEL_RETRIES, on_failure="error", initial_delay=RETRY_DELAY
    )


def refusal(error: Exception, _: ToolCallRequest) -> str | None:
    """Give the claim agent the backend's reason for refusing."""
    return str(error) if isinstance(error, Refused) else None


def backend_trouble(error: Exception, _: ToolCallRequest) -> str | None:
    """Tell the queue agent what the backend said, so that the run carries on."""
    if isinstance(error, Refused | rules.NotStarted):
        return str(error)
    if isinstance(error, BackendError):
        return (
            f"The backend had a problem ({error})."
            " Carry on; finish_run puts right anything left half done."
        )
    return None


def claim_agent(llm: BaseChatModel) -> Any:
    """Build an agent that works one claim."""
    middleware: Middleware = [
        ModelCallLimitMiddleware(run_limit=CLAIM_CALL_LIMIT, exit_behavior="error"),
        model_retry(),
        ToolErrorMiddleware(refusal),
        ToolRetryMiddleware(
            retry_on=(Unreachable,),
            on_failure="error",
            initial_delay=RETRY_DELAY,
        ),
    ]
    return create_agent(
        llm,
        tools=CLAIM_TOOLS,
        system_prompt=api.get_instructions()["claim"],
        context_schema=ClaimContext,
        middleware=middleware,
    )


def queue_agent(llm: BaseChatModel, cap: int) -> Any:
    """Build an agent that works the queue, up to a cap."""
    middleware: Middleware = [
        ModelCallLimitMiddleware(thread_limit=4 * cap + 10, exit_behavior="error"),
        model_retry(),
        ToolErrorMiddleware(backend_trouble),
    ]
    return create_agent(
        llm,
        tools=QUEUE_TOOLS,
        system_prompt=api.get_instructions()["queue"],
        context_schema=RunContext,
        middleware=middleware,
        checkpointer=InMemorySaver(),
    )


def user(text: str) -> dict[str, Any]:
    """Return an agent's input with one message from the user."""
    return {"messages": [{"role": "user", "content": text}]}


def run_claim_agent(claim_id: str, llm: BaseChatModel) -> None:
    """Run a fresh claim agent on a started claim, recording each step."""
    seen = 1  # the user's message isn't a step
    for state in claim_agent(llm).stream(
        user(f"Claim {claim_id}"), context=ClaimContext(claim_id), stream_mode="values"
    ):
        for message in state["messages"][seen:]:
            for kind, content in steps(message):
                api.record_step(claim_id, kind, content)
        seen = len(state["messages"])


def work_claim(claim_id: str, llm: BaseChatModel | None = None) -> str:
    """Work one claim from a clean start and report the outcome in a line."""
    llm = llm or model()
    try:
        api.start_claim(claim_id, str(uuid.uuid4()))
    except Refused as error:
        raise rules.NotStarted(f"{claim_id} not started: {error}") from error
    problem = NO_DECISION
    try:
        run_claim_agent(claim_id, llm)
    except Exception as error:  # any failure puts the claim back in the queue
        problem = describe(error)
    return rules.settle(claim_id, problem)


def run_queue_agent(run: RunContext, llm: BaseChatModel) -> str:
    """Run the queue agent until it finishes the run, and say why if it doesn't."""
    agent = queue_agent(llm, run.cap)
    config: RunnableConfig = {"configurable": {"thread_id": run.run_id}}
    message = f"Run the queue. This run is capped at {run.cap} claims."
    for _ in range(1 + NUDGES):
        try:
            agent.invoke(user(message), config, context=run)
        except Exception as error:  # the run is closed, whatever went wrong
            return describe(error)
        if run.finished:
            break
        message = CARRY_ON
    return ""


def run_queue(
    cap: int | None,
    llm: BaseChatModel | None = None,
    claim_llm: Callable[[str], BaseChatModel] = lambda _: model(),
) -> str:
    """Work the queue in one run, up to the cap, and return the run's summary."""

    def work(claim_id: str) -> str:
        line = work_claim(claim_id, claim_llm(claim_id))
        print(line, flush=True)
        return line

    llm = llm or model()
    rules.put_right()
    if cap is None:
        cap = max(len(rules.waiting_claims()), 1)
    run = RunContext(api.start_run(cap)["run_id"], cap, work)
    problem = run_queue_agent(run, llm)
    if not run.finished:
        rules.put_right()
        rules.close(
            run, f"The agent stopped before finishing the run. {problem}".strip()
        )
    return api.get_current_run()["summary"]
