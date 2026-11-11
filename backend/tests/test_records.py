from fastapi.testclient import TestClient

from backend.main import app
from backend.seed import seed

client = TestClient(app)


def test_seed_reports_what_it_loaded():
    assert seed() == "Seeded 25 claims, 50 policies, 49 customers and 3 handlers."


def test_the_queue_holds_only_the_25_claims_all_waiting():
    claims = client.get("/api/claims").json()
    assert [claim["claim_id"] for claim in claims] == [
        f"CLM-{n}" for n in range(1001, 1026)
    ]
    assert {claim["status"] for claim in claims} == {"waiting"}
    assert claims[0]["customer_name"] == "Maya Patel"
    assert claims[0]["decision"] is None
    assert claims[0]["payout"] is None


def test_get_claim():
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["claim_type"] == "trip_delay"
    assert claim["story"].startswith("My flight home from Rome")
    assert len(claim["items"]) == 3
    assert len(claim["documents"]) == 4
    assert claim["amount_claimed"] == 420.0
    assert claim["status"] == "waiting"
    assert claim["decision"] is None
    assert claim["payment"] is None


def test_get_policy():
    policy = client.get("/api/policies/POL-2001").json()
    assert policy["plan"] == "premium"
    assert policy["trip"]["destination"] == "Rome, Italy"
    assert policy["trip"]["departs_on"] == "2026-06-10"
    assert policy["trip"]["returns_on"] == "2026-06-18"


def test_get_customer():
    customer = client.get("/api/customers/CUS-3001").json()
    assert customer["name"] == "Maya Patel"
    assert customer["address"]["city"] == "Jersey City"


def test_claim_history_leaves_out_personal_details():
    history = client.get("/api/customers/CUS-3001/claim-history").json()
    assert [claim["claim_id"] for claim in history] == ["CLM-0412"]
    assert "Jersey City" not in str(history)
    assert "1988-03-14" not in str(history)


def test_list_handlers():
    handlers = client.get("/api/handlers").json()
    assert [handler["name"] for handler in handlers] == [
        "Dana Whitfield",
        "Marcus Oyelaran",
        "Priya Raman",
    ]


def test_unknown_records_are_404():
    for path in [
        "/api/claims/CLM-9999",
        "/api/policies/POL-9999",
        "/api/customers/CUS-9999",
        "/api/customers/CUS-9999/claim-history",
    ]:
        response = client.get(path)
        assert response.status_code == 404
        assert "9999 not found" in response.json()["detail"]


def test_the_backend_seeds_an_empty_database_on_startup(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERCOVER_DB", str(tmp_path / "empty.db"))
    with TestClient(app) as fresh:
        assert len(fresh.get("/api/claims").json()) == 25
