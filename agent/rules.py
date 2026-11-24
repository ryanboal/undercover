"""UnderCover's rules for claims and runs, whatever the model does."""

from http import HTTPStatus

from agent import api
from agent.api import BackendError, Record, Refused
from agent.context import RunContext

STALE = "Work on this claim stopped before it was decided"


class NotStarted(BackendError):
    """A claim that can't be worked, because it isn't waiting."""


def outcome(claim: Record) -> str:
    """Describe a decided claim in a line."""
    decision = claim["decision"]
    if decision["decision"] != "approve":
        return f"{claim['claim_id']} {decision['decision']}"
    held = claim["status"] == "waiting_for_sign_off"
    payment = (
        "held for sign-off" if held else "paid" if claim["payment"] else "not paid"
    )
    return f"{claim['claim_id']} approve ${decision['payout']:,.2f}, {payment}"


def pay_if_due(claim: Record) -> Record:
    """Pay an approval within the limit that was left unpaid, and return the claim."""
    decision = claim["decision"]
    due = claim["status"] == "decided" and decision["decision"] == "approve"
    if not due or claim["payment"]:
        return claim
    try:
        api.pay_claim(claim["claim_id"], decision["payout"])
    except Refused as error:
        if error.status != HTTPStatus.CONFLICT:  # already paid
            raise
    return api.get_claim(claim["claim_id"])


def settle(claim_id: str, problem: str) -> str:
    """Put right a claim whose agent has stopped, and report it in a line."""
    claim = api.get_claim(claim_id)
    if claim["decision"]:
        return outcome(pay_if_due(claim))
    if api.release_claim(claim_id, problem)["status"] == "needs_handler":
        return f"{claim_id} failed twice ({problem}), left for a handler"
    return f"{claim_id} failed ({problem}), back in the queue"


def put_right() -> None:
    """Release claims left in progress, and pay approvals left unpaid."""
    for claim in api.list_claims():
        if claim["decision"] == "approve":
            pay_if_due(api.get_claim(claim["claim_id"]))
        if claim["status"] == "in_progress":
            api.release_claim(claim["claim_id"], STALE)


def waiting_claims() -> list[str]:
    """Return the ids of the claims waiting in the queue."""
    return [c["claim_id"] for c in api.list_claims() if c["status"] == "waiting"]


def missed_claims(run: RunContext) -> list[str]:
    """Return the waiting claims a run can still work: retries, then new ones."""
    waiting = waiting_claims()
    retries = [c for c in waiting if c in run.attempted]
    fresh = [c for c in waiting if c not in run.attempted]
    return retries + fresh[: max(run.cap - len(run.attempted), 0)]


def close(run: RunContext, summary: str) -> None:
    """Finish a run, unless an earlier try already did."""
    try:
        api.finish_run(run.run_id, summary)
    except Refused as error:
        if error.status != HTTPStatus.CONFLICT:
            raise
    run.finished = True
