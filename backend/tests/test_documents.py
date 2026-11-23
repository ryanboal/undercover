import sqlite3
from contextlib import closing

import pytest

from backend.database import split_sections


def test_seeding_splits_both_documents_into_sections(database):
    with closing(sqlite3.connect(database)) as db:
        rows = db.execute(
            "SELECT document, number, title, text FROM sections"
        ).fetchall()
    numbers = {
        document: [number for d, number, _, _ in rows if d == document]
        for document in ("wording", "manual")
    }
    assert numbers["wording"] == [str(n) for n in range(1, 13)]
    assert numbers["manual"] == [str(n) for n in range(1, 15)]
    titles = {(d, n): t for d, n, t, _ in rows}
    assert titles["manual", "9"] == "Repeat claims"
    assert titles["wording", "10"] == "How we work out your payment"
    texts = {(d, n): t for d, n, _, t in rows}
    assert "third claim" in texts["manual", "9"]
    assert "Meals without receipts" not in texts["manual", "9"]
    assert "## " not in texts["manual", "9"]


def test_split_sections():
    markdown = "# Title\n\nIntro.\n\n## 1. First\n\nOne.\n\n## 2. Second\nTwo.\n"
    assert split_sections(markdown) == [("1", "First", "One."), ("2", "Second", "Two.")]


def test_search_finds_the_wild_animals_note(client):
    results = client.get("/api/documents/search", params={"query": "monkey"}).json()
    assert (results[0]["document"], results[0]["number"]) == ("manual", "7")
    assert results[0]["title"] == "Interpretation notes"
    assert "onkey" in results[0]["snippet"]


def test_search_ranks_and_limits(client):
    results = client.get(
        "/api/documents/search", params={"query": "meals without receipts"}
    ).json()
    assert len(results) <= 5
    assert ("manual", "10") in [(r["document"], r["number"]) for r in results]


@pytest.mark.parametrize("query", ['"quote', "a AND (", "NEAR(", "*", "?!"])
def test_search_ignores_query_syntax(client, query):
    response = client.get("/api/documents/search", params={"query": query})
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_search_needs_a_query(client):
    assert client.get("/api/documents/search", params={"query": ""}).status_code == 422


def test_read_section(client):
    section = client.get("/api/documents/wording/sections/10").json()
    assert section["title"] == "How we work out your payment"
    assert section["text"].startswith("1. We start with the eligible amount")
    manual = client.get("/api/documents/manual/sections/9").json()
    assert manual["title"] == "Repeat claims"


@pytest.mark.parametrize(
    "path", ["/api/documents/novel/sections/1", "/api/documents/manual/sections/99"]
)
def test_read_section_not_found(client, path):
    assert client.get(path).status_code == 404
