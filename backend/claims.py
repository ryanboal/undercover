"""Claims: reading them, and the rules for working, paying and signing them off."""

import json
import sqlite3

from fastapi import APIRouter, HTTPException

from backend.database import Database, now
from backend.models import (
    Claim,
    ClaimSummary,
    Decision,
    DecisionRequest,
    Handler,
    Payment,
    PaymentRequest,
    ReleaseRequest,
    SignOffRequest,
    StartRequest,
    Step,
    StepRequest,
)

router = APIRouter()
MAX_ATTEMPTS = 2


def dollars(amount: float) -> str:
    """Format an amount like $1,250.00."""
    return f"${amount:,.2f}"


def approval_limit(db: sqlite3.Connection) -> float:
    """Return the largest payout that can be paid without a handler's sign-off."""
    return db.execute("SELECT payout_approval_limit FROM settings").fetchone()[0]


def find_claim(db: sqlite3.Connection, claim_id: str) -> sqlite3.Row:
    """Return one claim's row, or raise a 404."""
    row = db.execute(
        "SELECT * FROM claim_view WHERE claim_id = ?", (claim_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"Claim {claim_id} not found")
    return row


def to_summary(row: sqlite3.Row) -> ClaimSummary:
    """Build a claim's line in the queue from its row."""
    return ClaimSummary(**json.loads(row["record"]) | dict(row))


def to_claim(row: sqlite3.Row) -> Claim:
    """Build a claim in full, with its decision and payment, from its row."""
    fields = dict(row)
    decided, paid = row["decision"] is not None, row["paid_at"] is not None
    return Claim(
        **json.loads(row["record"])
        | fields
        | {
            "decision": Decision(**fields) if decided else None,
            "payment": Payment(**fields) if paid else None,
        }
    )


def add_step(
    db: sqlite3.Connection, claim_id: str, thread_id: str, kind: str, content: str
) -> sqlite3.Row:
    """Record one step of the agent's work on a claim."""
    return db.execute(
        "INSERT INTO steps (claim_id, thread_id, kind, content, created_at)"
        " VALUES (?, ?, ?, ?, ?) RETURNING *",
        (claim_id, thread_id, kind, content, now()),
    ).fetchone()


def pay(
    db: sqlite3.Connection, claim_id: str, amount: float, signed_off_by: str | None
) -> Payment:
    """Record a payment on a claim."""
    payment = Payment(amount=amount, paid_at=now(), signed_off_by=signed_off_by)
    db.execute(
        "INSERT INTO payments VALUES (?, ?, ?, ?)",
        (claim_id, payment.amount, payment.paid_at, payment.signed_off_by),
    )
    return payment


@router.get("/claims", operation_id="list_claims")
def list_claims(db: Database) -> list[ClaimSummary]:
    """List every claim in the queue, in id order."""
    rows = db.execute("SELECT * FROM claim_view ORDER BY claim_id").fetchall()
    return [to_summary(row) for row in rows]


@router.get("/claims/{claim_id}", operation_id="get_claim")
def get_claim(claim_id: str, db: Database) -> Claim:
    """Get one claim in full: the story, the items claimed and the documents."""
    return to_claim(find_claim(db, claim_id))


@router.post("/claims/{claim_id}/start", operation_id="start_claim")
def start_claim(claim_id: str, request: StartRequest, db: Database) -> Claim:
    """Start work on a waiting claim, which moves it to in progress."""
    if find_claim(db, claim_id)["status"] != "waiting":
        raise HTTPException(409, f"Claim {claim_id} is not waiting")
    db.execute(
        "UPDATE claims SET status = 'in_progress', thread_id = ? WHERE claim_id = ?",
        (request.thread_id, claim_id),
    )
    return to_claim(find_claim(db, claim_id))


@router.post("/claims/{claim_id}/steps", operation_id="record_step")
def record_step(claim_id: str, request: StepRequest, db: Database) -> Step:
    """Record one step of the agent's work on a claim."""
    thread_id = find_claim(db, claim_id)["thread_id"]
    if thread_id is None:
        raise HTTPException(409, f"Claim {claim_id} has not been started")
    row = add_step(db, claim_id, thread_id, request.kind, request.content)
    return Step(**dict(row))


@router.get("/claims/{claim_id}/steps", operation_id="list_steps")
def list_steps(claim_id: str, db: Database) -> list[Step]:
    """List the steps of the agent's work on a claim, in order."""
    find_claim(db, claim_id)
    rows = db.execute(
        "SELECT * FROM steps WHERE claim_id = ? ORDER BY step_id", (claim_id,)
    ).fetchall()
    return [Step(**dict(row)) for row in rows]


@router.post("/claims/{claim_id}/decision", operation_id="record_decision")
def record_decision(claim_id: str, request: DecisionRequest, db: Database) -> Claim:
    """Record the decision on a claim; an approval over the limit waits for sign-off."""
    if find_claim(db, claim_id)["status"] != "in_progress":
        raise HTTPException(409, f"Claim {claim_id} is not in progress")
    payout = round(request.payout, 2)
    held = request.decision == "approve" and payout > approval_limit(db)
    db.execute(
        "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?)",
        (claim_id, request.decision, payout, request.section, request.reason, now()),
    )
    db.execute(
        "UPDATE claims SET status = ? WHERE claim_id = ?",
        ("waiting_for_sign_off" if held else "decided", claim_id),
    )
    return to_claim(find_claim(db, claim_id))


@router.post("/claims/{claim_id}/payment", operation_id="pay_claim")
def pay_claim(claim_id: str, request: PaymentRequest, db: Database) -> Payment:
    """Pay an approved claim its payout, unless it needs a handler's sign-off."""
    claim = find_claim(db, claim_id)
    if claim["decision"] != "approve":
        raise HTTPException(409, f"Claim {claim_id} has not been approved")
    if claim["paid_at"] is not None:
        raise HTTPException(409, f"Claim {claim_id} has already been paid")
    if claim["status"] == "waiting_for_sign_off":
        raise HTTPException(
            403,
            f"A payout over {dollars(approval_limit(db))} needs a handler's sign-off",
        )
    if round(request.amount, 2) != claim["payout"]:
        raise HTTPException(
            422, f"The amount must be the approved payout of {dollars(claim['payout'])}"
        )
    return pay(db, claim_id, claim["payout"], None)


@router.post("/claims/{claim_id}/sign-off", operation_id="sign_off_claim")
def sign_off_claim(claim_id: str, request: SignOffRequest, db: Database) -> Claim:
    """Sign off a held payout as a handler, which pays it and decides the claim."""
    claim = find_claim(db, claim_id)
    if claim["status"] != "waiting_for_sign_off":
        raise HTTPException(409, f"Claim {claim_id} is not waiting for sign-off")
    row = db.execute(
        "SELECT * FROM handlers WHERE handler_id = ?", (request.handler_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"Handler {request.handler_id} not found")
    handler = Handler(**dict(row))
    if not handler.can_approve_over_limit:
        raise HTTPException(
            403,
            f"{handler.name} can't sign off payouts over {dollars(approval_limit(db))}",
        )
    pay(db, claim_id, claim["payout"], handler.name)
    db.execute("UPDATE claims SET status = 'decided' WHERE claim_id = ?", (claim_id,))
    return to_claim(find_claim(db, claim_id))


@router.post("/claims/{claim_id}/release", operation_id="release_claim")
def release_claim(claim_id: str, request: ReleaseRequest, db: Database) -> Claim:
    """Put a failed claim back in the queue, or leave it for a handler after two."""
    claim = find_claim(db, claim_id)
    if claim["status"] != "in_progress":
        raise HTTPException(409, f"Claim {claim_id} is not in progress")
    attempts = claim["failed_attempts"] + 1
    status = "needs_handler" if attempts >= MAX_ATTEMPTS else "waiting"
    db.execute(
        "UPDATE claims SET status = ?, failed_attempts = ? WHERE claim_id = ?",
        (status, attempts, claim_id),
    )
    add_step(db, claim_id, claim["thread_id"], "error", request.reason)
    return to_claim(find_claim(db, claim_id))
