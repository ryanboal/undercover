"""Runs of the agent on the queue, and their to-do lists."""

import json
import sqlite3
import uuid

from fastapi import APIRouter, HTTPException

from backend.database import Database, now
from backend.models import (
    FinishRunRequest,
    Run,
    StartRunRequest,
    TodosRequest,
)

router = APIRouter()


def find_run(db: sqlite3.Connection, run_id: str) -> sqlite3.Row:
    """Return one run's row, or raise a 404."""
    row = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"Run {run_id} not found")
    return row


def to_run(row: sqlite3.Row) -> Run:
    """Build a run, with its to-do list, from its row."""
    return Run(**dict(row) | {"todos": json.loads(row["todos"])})


@router.post("/runs", operation_id="start_run")
def start_run(request: StartRunRequest, db: Database) -> Run:
    """Start a run of the agent on the queue, capped at a number of claims."""
    run_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO runs (run_id, cap, started_at, todos) VALUES (?, ?, ?, '[]')",
        (run_id, request.cap, now()),
    )
    return to_run(find_run(db, run_id))


@router.get("/runs/current", operation_id="get_current_run")
def get_current_run(db: Database) -> Run | None:
    """Get the latest run with its to-do list, or null before the first run."""
    row = db.execute(
        "SELECT * FROM runs ORDER BY started_at DESC, rowid DESC LIMIT 1"
    ).fetchone()
    return None if row is None else to_run(row)


@router.put("/runs/{run_id}/todos", operation_id="record_todos")
def record_todos(run_id: str, request: TodosRequest, db: Database) -> Run:
    """Replace a run's to-do list."""
    find_run(db, run_id)
    todos = json.dumps([todo.model_dump() for todo in request.todos])
    db.execute("UPDATE runs SET todos = ? WHERE run_id = ?", (todos, run_id))
    return to_run(find_run(db, run_id))


@router.post("/runs/{run_id}/finish", operation_id="finish_run")
def finish_run(run_id: str, request: FinishRunRequest, db: Database) -> Run:
    """Finish a run with a short summary for the handlers."""
    if find_run(db, run_id)["finished_at"] is not None:
        raise HTTPException(409, f"Run {run_id} has already finished")
    db.execute(
        "UPDATE runs SET finished_at = ?, summary = ? WHERE run_id = ?",
        (now(), request.summary, run_id),
    )
    return to_run(find_run(db, run_id))
