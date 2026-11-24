"""The policy wording, the claims manual and the agent's instructions."""

import re
import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from backend.database import Database
from backend.models import (
    Instructions,
    SearchResult,
    Section,
)

router = APIRouter()
INSTRUCTIONS = Path(__file__).parent / "instructions"
DOCUMENT_NAMES = {"wording": "the policy wording", "manual": "the claims manual"}


def contents(db: sqlite3.Connection) -> str:
    """List the sections of the wording and the manual, by number and title."""
    parts = []
    for document, name in DOCUMENT_NAMES.items():
        rows = db.execute(
            "SELECT number, title FROM sections WHERE document = ?", (document,)
        ).fetchall()
        lines = "\n".join(f"- {row['number']}. {row['title']}" for row in rows)
        parts.append(f"## Contents of {name}, document `{document}`\n\n{lines}\n")
    return "\n".join(parts)


@router.get("/instructions", operation_id="get_instructions")
def get_instructions(db: Database) -> Instructions:
    """Get the instructions for running the queue and for working a claim."""
    claim = (INSTRUCTIONS / "claim.md").read_text(encoding="utf-8")
    return Instructions(
        queue=(INSTRUCTIONS / "queue.md").read_text(encoding="utf-8"),
        claim=f"{claim}\n{contents(db)}",
    )


@router.get("/documents/search", operation_id="search_documents")
def search_documents(
    query: Annotated[str, Query(min_length=1)], db: Database
) -> list[SearchResult]:
    """Find the five sections of the wording and the manual that best match a query."""
    words = re.findall(r"\w+", query)
    if not words:
        return []
    rows = db.execute(
        "SELECT document, number, title,"
        " snippet(sections, 3, '', '', '...', 24) AS snippet"
        " FROM sections WHERE sections MATCH ? ORDER BY rank LIMIT 5",
        (" OR ".join(f'"{word}"' for word in words),),
    ).fetchall()
    return [SearchResult(**dict(row)) for row in rows]


@router.get("/documents/{document}/sections/{number}", operation_id="read_section")
def read_section(document: str, number: str, db: Database) -> Section:
    """Read one section of the policy wording or the claims manual in full."""
    row = db.execute(
        "SELECT document, number, title, text FROM sections"
        " WHERE document = ? AND number = ?",
        (document, number),
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"Section {number} of {document} not found")
    return Section(**dict(row))
