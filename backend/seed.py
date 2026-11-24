"""Rebuild the database from data/, with: uv run -m backend.seed"""

import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from backend.database import ROOT, SCHEMA, database_path

DATA = ROOT / "data"
DOCUMENTS = {"wording": "policy_wording.md", "manual": "claims_manual.md"}


def load(name: str) -> Any:
    """Read one of the JSON files in data/."""
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def split_sections(markdown: str) -> list[tuple[str, str, str]]:
    """Split a document at its ## headings into (number, title, text)."""
    sections = []
    for part in re.split(r"^## ", markdown, flags=re.MULTILINE)[1:]:
        heading, _, text = part.partition("\n")
        number, _, title = heading.partition(". ")
        sections.append((number, title.strip(), text.strip()))
    return sections


def seed(path: Path) -> dict[str, int]:
    """Build a fresh database at path from data/ and count what it holds."""
    company = load("company.json")
    handlers = load("handlers.json")
    customers = load("customers.json")
    policies = load("policies.json")
    claims = load("claims.json")
    path.unlink(missing_ok=True)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.executescript(SCHEMA)
        connection.execute(
            "INSERT INTO settings VALUES (?)",
            (company["payout_approval_limit"],),
        )
        connection.executemany(
            "INSERT INTO handlers VALUES (?, ?, ?, ?)",
            [
                (h["handler_id"], h["name"], h["role"], h["can_approve_over_limit"])
                for h in handlers
            ],
        )
        connection.executemany(
            "INSERT INTO customers VALUES (?, ?, ?)",
            [(c["customer_id"], c["name"], json.dumps(c)) for c in customers],
        )
        connection.executemany(
            "INSERT INTO policies VALUES (?, ?)",
            [(p["policy_id"], json.dumps(p)) for p in policies],
        )
        connection.executemany(
            "INSERT INTO claims VALUES (?, ?, ?, 'waiting', NULL, 0)",
            [(c["claim_id"], c["customer_id"], json.dumps(c)) for c in claims],
        )
        for document, name in DOCUMENTS.items():
            markdown = (DATA / name).read_text(encoding="utf-8")
            connection.executemany(
                "INSERT INTO sections VALUES (?, ?, ?, ?)",
                [(document, *section) for section in split_sections(markdown)],
            )
    return {
        "claims": len(claims),
        "policies": len(policies),
        "customers": len(customers),
        "handlers": len(handlers),
    }


def main() -> None:
    """Rebuild the database and say what it holds."""
    path = database_path()
    counts = seed(path)
    print(
        f"Seeded {counts['claims']} claims, {counts['policies']} policies, "
        f"{counts['customers']} customers and {counts['handlers']} handlers "
        f"into {path.name}"
    )


if __name__ == "__main__":
    main()
