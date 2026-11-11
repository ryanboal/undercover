"""The UnderCover database, in SQLite."""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DEFAULT_PATH = Path(__file__).parent / "undercover.db"

SCHEMA = """
DROP TABLE IF EXISTS steps;
DROP TABLE IF EXISTS claims;
DROP TABLE IF EXISTS policies;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS handlers;

CREATE TABLE policies (policy_id TEXT PRIMARY KEY, record TEXT NOT NULL);
CREATE TABLE customers (customer_id TEXT PRIMARY KEY, record TEXT NOT NULL);
CREATE TABLE handlers (handler_id TEXT PRIMARY KEY, record TEXT NOT NULL);
CREATE TABLE claims (
    claim_id TEXT PRIMARY KEY,
    record TEXT NOT NULL,
    status TEXT NOT NULL,
    decision TEXT,
    payout REAL,
    reason TEXT,
    policy_section TEXT,
    decided_at TEXT,
    paid_amount REAL,
    paid_by TEXT,
    paid_at TEXT
);
CREATE TABLE steps (
    step_id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL REFERENCES claims (claim_id),
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL
);
"""


def path() -> str:
    """Return the database's path: UNDERCOVER_DB if set, else backend/undercover.db."""
    return os.getenv("UNDERCOVER_DB") or str(DEFAULT_PATH)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open the database, commit on success and close it afterwards."""
    db = sqlite3.connect(path())
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()


def is_empty() -> bool:
    """Return True when the database has no claims table yet."""
    with connect() as db:
        row = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'claims'"
        ).fetchone()
    return row is None
