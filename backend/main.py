"""The UnderCover backend."""

import json
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status

from backend.db import connect, is_empty
from backend.models import (
    Claim,
    ClaimSummary,
    Customer,
    Decision,
    Handler,
    Payment,
    Policy,
    PreviousClaim,
)
from backend.seed import seed


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
