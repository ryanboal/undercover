"""The UnderCover backend."""

import json
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, status

from backend.db import connect, is_empty
from backend.models import (
    Claim,
    ClaimSummary,
    Customer,
    Decision,
    Handler,
    NewDecision,
    NewPayment,
    NewStep,
    Payment,
    Policy,
    PreviousClaim,
    SignOff,
    Step,
)
from backend.seed import DATA, seed

COMPANY = json.loads((DATA / "company.json").read_text(encoding="utf-8"))
APPROVAL_LIMIT: float = COMPANY["payout_approval_limit"]
AGENT_NAME = "UnderCover Agent"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Seed the database on startup when it is empty."""
    if is_empty():
        seed()
    yield


app = FastAPI(title="UnderCover", lifespan=lifespan)


def find(db: sqlite3.Connection, query: str, key: str, what: str) -> sqlite3.Row:
    """Fetch one row by its id, or answer 404."""
    row = db.execute(query, (key,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{what} {key} not found")
    return row


def find_claim(db: sqlite3.Connection, claim_id: str) -> sqlite3.Row:
    """Fetch one claim's row, or answer 404."""
    return find(db, "SELECT * FROM claims WHERE claim_id = ?", claim_id, "Claim")


def to_claim(row: sqlite3.Row) -> Claim:
    """Build a claim from its record, its status, its decision and its payment."""
    decision = None
    if row["decision"]:
        decision = Decision(
            decision=row["decision"],
            payout=row["payout"],
            reason=row["reason"],
            policy_section=row["policy_section"],
            decided_at=row["decided_at"],
        )
    payment = None
    if row["paid_at"]:
        payment = Payment(
            amount=row["paid_amount"], paid_by=row["paid_by"], paid_at=row["paid_at"]
        )
    return Claim(
        **json.loads(row["record"]),
        status=row["status"],
        decision=decision,
        payment=payment,
    )


@app.get("/api/health", operation_id="health")
def health() -> dict[str, str]:
    """Check that the backend is running."""
    return {"status": "ok"}


@app.get("/api/claims", operation_id="list_claims")
def list_claims() -> list[ClaimSummary]:
    """List every claim in the queue with where it stands."""
    with connect() as db:
        rows = db.execute(
            """
            SELECT c.record, c.status, c.decision, c.payout,
                   json_extract(cu.record, '$.name') AS customer_name
            FROM claims c
            JOIN customers cu
              ON cu.customer_id = json_extract(c.record, '$.customer_id')
            ORDER BY c.claim_id
            """
        ).fetchall()
    return [
        ClaimSummary(
            **json.loads(row["record"]),
            customer_name=row["customer_name"],
            status=row["status"],
            decision=row["decision"],
            payout=row["payout"],
        )
        for row in rows
    ]


@app.get("/api/claims/{claim_id}", operation_id="get_claim")
def get_claim(claim_id: str) -> Claim:
    """Get one claim in full, with its decision and payment."""
    with connect() as db:
        return to_claim(find_claim(db, claim_id))


@app.get("/api/policies/{policy_id}", operation_id="get_policy")
def get_policy(policy_id: str) -> Policy:
    """Get one policy: its plan, add-ons, trip and travelers."""
    with connect() as db:
        row = find(
            db, "SELECT * FROM policies WHERE policy_id = ?", policy_id, "Policy"
        )
    return Policy(**json.loads(row["record"]))


def customer_record(customer_id: str) -> Customer:
    """Fetch one customer's full record, or answer 404."""
    with connect() as db:
        row = find(
            db, "SELECT * FROM customers WHERE customer_id = ?", customer_id, "Customer"
        )
    return Customer(**json.loads(row["record"]))


@app.get("/api/customers/{customer_id}", operation_id="get_customer")
def get_customer(customer_id: str) -> Customer:
    """Get one customer's contact details and claim history."""
    return customer_record(customer_id)


@app.get("/api/customers/{customer_id}/claim-history", operation_id="get_claim_history")
def get_claim_history(customer_id: str) -> list[PreviousClaim]:
    """Get one customer's earlier claims, without their personal details."""
    return customer_record(customer_id).previous_claims


@app.get("/api/handlers", operation_id="list_handlers")
def list_handlers() -> list[Handler]:
    """List the claims handlers."""
    with connect() as db:
        rows = db.execute("SELECT record FROM handlers ORDER BY handler_id").fetchall()
    return [Handler(**json.loads(row["record"])) for row in rows]


def now() -> str:
    """Return the time now in UTC, to the second."""
    return datetime.now(UTC).isoformat(timespec="seconds")


@app.post("/api/claims/{claim_id}/start", operation_id="start_claim")
def start_claim(claim_id: str) -> Claim:
    """Start work on a waiting claim, which puts it in progress."""
    with connect() as db:
        if find_claim(db, claim_id)["status"] != "waiting":
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"Claim {claim_id} is not waiting"
            )
        db.execute(
            "UPDATE claims SET status = 'in_progress' WHERE claim_id = ?", (claim_id,)
        )
        return to_claim(find_claim(db, claim_id))


@app.post("/api/claims/{claim_id}/steps", operation_id="add_step")
def add_step(claim_id: str, step: NewStep) -> Step:
    """Record one step of the agent's work on a claim."""
    with connect() as db:
        find_claim(db, claim_id)
        row = db.execute(
            "INSERT INTO steps (claim_id, at, kind, text) VALUES (?, ?, ?, ?) "
            "RETURNING step_id, at, kind, text",
            (claim_id, now(), step.kind, step.text),
        ).fetchone()
    return Step(**row)


@app.get("/api/claims/{claim_id}/steps", operation_id="list_steps")
def list_steps(claim_id: str) -> list[Step]:
    """List the steps of the agent's work on a claim, in order."""
    with connect() as db:
        find_claim(db, claim_id)
        rows = db.execute(
            "SELECT step_id, at, kind, text FROM steps WHERE claim_id = ? "
            "ORDER BY step_id",
            (claim_id,),
        ).fetchall()
    return [Step(**row) for row in rows]


def status_after(decision: NewDecision) -> str:
    """Say where a claim stands once this decision is recorded."""
    if decision.decision != "approve":
        return "decided"
    if decision.payout > APPROVAL_LIMIT:
        return "waiting_for_sign_off"
    return "in_progress"


@app.post("/api/claims/{claim_id}/decision", operation_id="decide_claim")
def decide_claim(claim_id: str, decision: NewDecision) -> Claim:
    """Record the decision on a claim in progress: approve, decline or refer."""
    if decision.decision != "approve" and decision.payout != 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A decline or referral pays 0")
    with connect() as db:
        if find_claim(db, claim_id)["status"] != "in_progress":
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"Claim {claim_id} is not in progress"
            )
        db.execute(
            """
            UPDATE claims SET status = ?, decision = ?, payout = ?, reason = ?,
                              policy_section = ?, decided_at = ?
            WHERE claim_id = ?
            """,
            (
                status_after(decision),
                decision.decision,
                round(decision.payout, 2),
                decision.reason,
                decision.policy_section,
                now(),
                claim_id,
            ),
        )
        return to_claim(find_claim(db, claim_id))


def record_payment(db: sqlite3.Connection, claim_id: str, paid_by: str) -> Claim:
    """Pay a claim its approved payout and mark it decided."""
    db.execute(
        """
        UPDATE claims SET status = 'decided', paid_amount = payout, paid_by = ?,
                          paid_at = ?
        WHERE claim_id = ?
        """,
        (paid_by, now(), claim_id),
    )
    return to_claim(find_claim(db, claim_id))


@app.post("/api/claims/{claim_id}/payment", operation_id="pay_claim")
def pay_claim(claim_id: str, payment: NewPayment) -> Claim:
    """Pay an approved claim its payout, up to the limit without a sign-off."""
    with connect() as db:
        row = find_claim(db, claim_id)
        if row["decision"] != "approve":
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"Claim {claim_id} is not approved"
            )
        if row["paid_at"]:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"Claim {claim_id} is already paid"
            )
        if round(payment.amount, 2) != row["payout"]:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"The payment must be the approved payout of ${row['payout']:,.2f}",
            )
        if row["payout"] > APPROVAL_LIMIT:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"A payout over ${APPROVAL_LIMIT:,.2f} needs a handler's sign-off",
            )
        return record_payment(db, claim_id, AGENT_NAME)


@app.post("/api/claims/{claim_id}/sign-off", operation_id="sign_off_claim")
def sign_off_claim(claim_id: str, sign_off: SignOff) -> Claim:
    """Sign off a payout over the limit as a handler, which pays the claim."""
    with connect() as db:
        if find_claim(db, claim_id)["status"] != "waiting_for_sign_off":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Claim {claim_id} is not waiting for sign-off",
            )
        row = find(
            db,
            "SELECT record FROM handlers WHERE handler_id = ?",
            sign_off.handler_id,
            "Handler",
        )
        handler = Handler(**json.loads(row["record"]))
        if not handler.can_approve_over_limit:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"{handler.name} cannot sign off payouts over the limit",
            )
        return record_payment(db, claim_id, handler.name)
