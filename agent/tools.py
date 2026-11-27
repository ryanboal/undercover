"""The agents' tools, each named after the backend operation it calls."""

import json
from typing import Literal, TypedDict

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

from agent import api, rules
from agent.api import Record
from agent.context import ClaimContext, RunContext

DOCUMENT_NAMES = {"wording": "Policy wording", "manual": "Claims manual"}


def found(records: list[Record], none: str) -> str:
    """The records as JSON, or a sentence when there are none."""
    return json.dumps(records) if records else none


@tool
def get_claim(runtime: ToolRuntime[ClaimContext]) -> Record:
    """Get your claim in full: the story, the items claimed and the documents."""
    return api.get_claim(runtime.context.claim_id)


@tool
def get_policy(policy_id: str) -> Record:
    """Get a policy: the plan, add-ons, purchase date, trip and travelers."""
    return api.get_policy(policy_id)


@tool
def get_claim_history(customer_id: str) -> str:
    """Get a customer's earlier claims, with the outcome and the amount paid."""
    records = api.get_claim_history(customer_id)
    return found(records, "This customer has no earlier claims.")


@tool
def search_documents(query: str) -> str:
    """Search the policy wording and the claims manual for the five best sections."""
    return found(api.search_documents(query), "No sections match that search.")


@tool
def read_section(document: Literal["wording", "manual"], number: str) -> str:
    """Read one section of the policy wording or the claims manual in full."""
    section = api.read_section(document, number)
    heading = f"{DOCUMENT_NAMES[document]}, section {number}: {section['title']}"
    return f"{heading}\n\n{section['text']}"


@tool
def record_decision(
    decision: Literal["approve", "decline", "refer"],
    payout: float,
    section: str,
    reason: str,
    runtime: ToolRuntime[ClaimContext],
) -> Record:
    """Record your decision, once; an approval over the limit waits for sign-off."""
    return api.record_decision(
        runtime.context.claim_id,
        {"decision": decision, "payout": payout, "section": section, "reason": reason},
    )


@tool
def pay_claim(amount: float, runtime: ToolRuntime[ClaimContext]) -> Record:
    """Pay your approved claim its payout, unless it needs a handler's sign-off."""
    return api.pay_claim(runtime.context.claim_id, amount)


class TodoItem(TypedDict):
    task: str
    status: Literal["to_do", "in_progress", "done", "left_for_handler"]


@tool
def list_claims() -> str:
    """List the claims queue, one claim a line, with its status and summary."""
    return "\n".join(
        f"{c['claim_id']}  {c['status']}  {c['claim_type']}"
        f"  ${c['amount_claimed']:,.2f}  submitted {c['submitted_on']}"
        f"  {c['summary']}"
        for c in api.list_claims()
    )


@tool
def record_todos(todos: list[TodoItem], runtime: ToolRuntime[RunContext]) -> str:
    """Replace the run's to-do list, which the handlers watch. Send every item."""
    api.record_todos(runtime.context.run_id, todos)
    return f"Saved {len(todos)} items."


@tool
def work_claim(claim_id: str, runtime: ToolRuntime[RunContext]) -> str:
    """Hand a waiting claim to a fresh claim agent and get its outcome in a line."""
    run = runtime.context
    with run.one_at_a_time:
        if not run.has_room_for(claim_id):
            worked = ", ".join(sorted(run.attempted))
            return (
                f"Refused: the run is capped at {run.cap} claims"
                f" and has worked {worked}"
            )
        before = set(run.attempted)
        run.attempted.add(claim_id)
        try:
            return run.work_claim(claim_id)
        except rules.NotStarted:
            run.attempted = before
            raise


@tool
def finish_run(summary: str, runtime: ToolRuntime[RunContext]) -> str:
    """Finish the run with a short summary for the handlers."""
    run = runtime.context
    with run.one_at_a_time:
        rules.put_right()
        missed = rules.missed_claims(run)
    if missed:
        return (
            "Refused: these waiting claims can still be worked in this run:"
            f" {', '.join(missed)}. Work them, then finish."
        )
    rules.close(run, summary)
    return "The run is finished."


CLAIM_TOOLS: list[BaseTool] = [
    get_claim,
    get_policy,
    get_claim_history,
    search_documents,
    read_section,
    record_decision,
    pay_claim,
]
QUEUE_TOOLS: list[BaseTool] = [list_claims, record_todos, work_claim, finish_run]
