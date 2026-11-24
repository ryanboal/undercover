"""The queue agent, which works the whole queue in one run."""

from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Literal, TypedDict

import httpx
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ToolCallRequest,
    ToolErrorMiddleware,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from langgraph.checkpoint.memory import InMemorySaver

from agent import main
from agent.main import BackendError, call_backend, model, model_retry, pay_if_due
from agent.tools import reply, request

NUDGES = 2
CARRY_ON = (
    "You haven't finished the run. Carry on with the queue, and call finish_run"
    " when every claim is done or left for a handler."
)
STALE = "Work on this claim stopped before it was decided"


class TodoItem(TypedDict):
    task: str
    status: Literal["to_do", "in_progress", "done", "left_for_handler"]


@dataclass
class Run:
    """What the harness knows about a run, which the model can't change."""

    run_id: str
    cap: int
    claim_llm: Callable[[str], BaseChatModel]
    attempted: set[str] = field(default_factory=set)
    finished: bool = False
    one_at_a_time: Lock = field(default_factory=Lock)


def waiting_claims() -> list[str]:
    """Return the ids of the claims waiting in the queue."""
    claims = call_backend("GET", "/api/claims")
    return [c["claim_id"] for c in claims if c["status"] == "waiting"]


def missed_claims(run: Run) -> list[str]:
    """Return the waiting claims this run can still work: retries, then new ones."""
    waiting = waiting_claims()
    retries = [c for c in waiting if c in run.attempted]
    room = run.cap - len(run.attempted)
    fresh = [c for c in waiting if c not in run.attempted][: max(room, 0)]
    return retries + fresh


def queue_tools(run: Run) -> list[BaseTool]:
    """Build the queue agent's tools for one run."""

    @tool
    def list_claims() -> str:
        """List the claims queue, one claim a line, with its status and summary."""
        return "\n".join(
            f"{c['claim_id']}  {c['status']}  {c['claim_type']}"
            f"  ${c['amount_claimed']:,.2f}  submitted {c['submitted_on']}"
            f"  {c['summary']}"
            for c in call_backend("GET", "/api/claims")
        )

    @tool
    def record_todos(todos: list[TodoItem]) -> str:
        """Replace the run's to-do list, which the handlers watch. Send every item."""
        response = request("PUT", f"/api/runs/{run.run_id}/todos", {"todos": todos})
        return reply(response) if response.is_error else f"Saved {len(todos)} items."

    @tool
    def work_claim(claim_id: str) -> str:
        """Hand a waiting claim to a fresh claim agent and get its outcome in a line."""
        with run.one_at_a_time:
            if claim_id not in run.attempted and len(run.attempted) >= run.cap:
                return (
                    f"Refused: the run is capped at {run.cap} claims and has worked"
                    f" {', '.join(sorted(run.attempted))}"
                )
            before = set(run.attempted)
            run.attempted.add(claim_id)
            line = main.work_claim(claim_id, run.claim_llm(claim_id))
            if " not started: " in line:
                run.attempted = before
            print(line, flush=True)
            return line

    @tool
    def finish_run(summary: str) -> str:
        """Finish the run with a short summary for the handlers."""
        with run.one_at_a_time:
            put_right()
            missed = missed_claims(run)
        if missed:
            return (
                "Refused: these waiting claims can still be worked in this run:"
                f" {', '.join(missed)}. Work them, then finish."
            )
        close(run, summary)
        return "The run is finished."

    return [list_claims, record_todos, work_claim, finish_run]


def backend_trouble(error: Exception, _: ToolCallRequest) -> str | None:
    """Tell the queue agent when the backend fails, so that the run carries on."""
    if isinstance(error, httpx.TransportError | BackendError):
        return (
            f"The backend had a problem ({type(error).__name__}: {error})."
            " Carry on; finish_run puts right anything left half done."
        )
    return None


def close(run: Run, summary: str) -> None:
    """Finish the run, unless an earlier try already did."""
    path = f"/api/runs/{run.run_id}/finish"
    response = request("POST", path, {"summary": summary})
    if response.is_error and response.status_code != httpx.codes.CONFLICT:
        raise BackendError(f"{response.status_code}: {response.text}")
    run.finished = True


def put_right() -> None:
    """Release claims left in progress, and pay approvals left unpaid."""
    for claim in call_backend("GET", "/api/claims"):
        if claim["decision"] == "approve":
            pay_if_due(call_backend("GET", f"/api/claims/{claim['claim_id']}"))
        if claim["status"] == "in_progress":
            call_backend(
                "POST", f"/api/claims/{claim['claim_id']}/release", {"reason": STALE}
            )


def run_queue(
    cap: int | None,
    llm: BaseChatModel | None = None,
    claim_llm: Callable[[str], BaseChatModel] | None = None,
) -> str:
    """Work the queue in one run, up to the cap, and return the run's summary."""
    put_right()
    if cap is None:
        cap = max(len(waiting_claims()), 1)
    started = call_backend("POST", "/api/runs", {"cap": cap})
    run = Run(started["run_id"], cap, claim_llm or (lambda _: model()))
    middleware: list[AgentMiddleware[Any, Any]] = [
        ModelCallLimitMiddleware(thread_limit=4 * cap + 10, exit_behavior="error"),
        model_retry(),
        ToolErrorMiddleware(backend_trouble),
    ]
    agent = create_agent(
        llm or model(),
        tools=queue_tools(run),
        system_prompt=call_backend("GET", "/api/instructions")["queue"],
        middleware=middleware,
        checkpointer=InMemorySaver(),
    )
    config: RunnableConfig = {"configurable": {"thread_id": run.run_id}}
    message = f"Run the queue. This run is capped at {cap} claims."
    stopped = ""
    for _ in range(1 + NUDGES):
        try:
            agent.invoke({"messages": [{"role": "user", "content": message}]}, config)
        except Exception as error:  # the run is finished below, whatever went wrong
            stopped = f" {type(error).__name__}: {error}"[:300]
            break
        if run.finished:
            break
        message = CARRY_ON
    if not run.finished:
        summary = f"The agent stopped before finishing the run.{stopped}"
        put_right()
        close(run, summary)
    return call_backend("GET", "/api/runs/current")["summary"]
