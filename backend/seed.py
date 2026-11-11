"""Reset the database to UnderCover's records in data/: run `uv run -m backend.seed`."""

import json
from pathlib import Path
from typing import Any

from backend.db import SCHEMA, connect

DATA = Path(__file__).parent.parent / "data"


def load(name: str) -> list[dict[str, Any]]:
    """Read one of the JSON files in data/."""
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def rows(records: list[dict[str, Any]], key: str) -> list[tuple[str, str]]:
    """Pair each record's id with the record as JSON."""
    return [(record[key], json.dumps(record)) for record in records]


def seed() -> str:
    """Recreate the tables, load the queue and the records, and say what was loaded."""
    claims = load("claims.json")
    for claim in claims:
        del claim["status"]
    policies = load("policies.json")
    customers = load("customers.json")
    handlers = load("handlers.json")
    with connect() as db:
        db.executescript(SCHEMA)
        db.executemany(
            "INSERT INTO claims (claim_id, record, status) VALUES (?, ?, 'waiting')",
            rows(claims, "claim_id"),
        )
        db.executemany(
            "INSERT INTO policies VALUES (?, ?)", rows(policies, "policy_id")
        )
        db.executemany(
            "INSERT INTO customers VALUES (?, ?)", rows(customers, "customer_id")
        )
        db.executemany(
            "INSERT INTO handlers VALUES (?, ?)", rows(handlers, "handler_id")
        )
    return (
        f"Seeded {len(claims)} claims, {len(policies)} policies, "
        f"{len(customers)} customers and {len(handlers)} handlers."
    )


if __name__ == "__main__":
    print(seed())
