from fastapi.testclient import TestClient

from backend.db import connect
from backend.main import app
from backend.seed import seed

client = TestClient(app)


def start(claim_id):
    return client.post(f"/api/claims/{claim_id}/start")


def decide(claim_id, decision, payout):
    return client.post(
        f"/api/claims/{claim_id}/decision",
        json={
            "decision": decision,
            "payout": payout,
            "reason": "The reason.",
            "policy_section": "Section 3, Trip Delay",
        },
    )


def pay(claim_id, amount):
    return client.post(f"/api/claims/{claim_id}/payment", json={"amount": amount})


def sign_off(claim_id, handler_id):
    return client.post(
        f"/api/claims/{claim_id}/sign-off", json={"handler_id": handler_id}
    )


def test_start_puts_a_waiting_claim_in_progress():
    assert start("CLM-1001").json()["status"] == "in_progress"
    response = start("CLM-1001")
    assert response.status_code == 409
    assert response.json()["detail"] == "Claim CLM-1001 is not waiting"


def test_an_approval_within_the_limit_is_decided_once_the_agent_pays():
    start("CLM-1001")
    claim = decide("CLM-1001", "approve", 420).json()
    assert claim["status"] == "in_progress"
    assert claim["decision"]["decision"] == "approve"
    assert claim["decision"]["payout"] == 420
    assert claim["decision"]["policy_section"] == "Section 3, Trip Delay"
    assert claim["payment"] is None
    claim = pay("CLM-1001", 420).json()
    assert claim["status"] == "decided"
    assert claim["payment"]["amount"] == 420
    assert claim["payment"]["paid_by"] == "UnderCover Agent"
    assert pay("CLM-1001", 420).json()["detail"] == "Claim CLM-1001 is already paid"


def test_a_payout_of_exactly_the_limit_needs_no_sign_off():
    start("CLM-1002")
    assert decide("CLM-1002", "approve", 1000).json()["status"] == "in_progress"
    assert pay("CLM-1002", 1000).json()["status"] == "decided"


def test_the_agent_cannot_pay_a_payout_over_the_limit():
    start("CLM-1003")
    assert decide("CLM-1003", "approve", 1150).json()["status"] == (
        "waiting_for_sign_off"
    )
    response = pay("CLM-1003", 1150)
    assert response.status_code == 403
    assert response.json()["detail"] == (
        "A payout over $1,000.00 needs a handler's sign-off"
    )
    response = pay("CLM-1003", 900)
    assert response.status_code == 400
    assert response.json()["detail"] == (
        "The payment must be the approved payout of $1,150.00"
    )
    claim = client.get("/api/claims/CLM-1003").json()
    assert claim["status"] == "waiting_for_sign_off"
    assert claim["payment"] is None


def test_a_handler_signs_off_and_pays():
    start("CLM-1003")
    decide("CLM-1003", "approve", 1150)
    claim = sign_off("CLM-1003", "HND-01").json()
    assert claim["status"] == "decided"
    assert claim["payment"]["amount"] == 1150
    assert claim["payment"]["paid_by"] == "Dana Whitfield"
    response = sign_off("CLM-1003", "HND-01")
    assert response.status_code == 409
    assert response.json()["detail"] == "Claim CLM-1003 is not waiting for sign-off"


def test_sign_off_needs_a_handler_who_can_approve_over_the_limit():
    start("CLM-1003")
    decide("CLM-1003", "approve", 1150)
    assert sign_off("CLM-1003", "HND-99").status_code == 404
    with connect() as db:
        db.execute(
            "UPDATE handlers SET record = json_set(record, "
            "'$.can_approve_over_limit', json('false')) WHERE handler_id = 'HND-02'"
        )
    response = sign_off("CLM-1003", "HND-02")
    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Marcus Oyelaran cannot sign off payouts over the limit"
    )


def test_a_claim_waiting_or_in_progress_cannot_be_signed_off():
    assert sign_off("CLM-1001", "HND-01").status_code == 409
    start("CLM-1001")
    decide("CLM-1001", "approve", 420)
    assert sign_off("CLM-1001", "HND-01").status_code == 409


def test_a_decline_is_decided_with_no_payment_and_is_final():
    start("CLM-1004")
    claim = decide("CLM-1004", "decline", 0).json()
    assert claim["status"] == "decided"
    assert claim["payment"] is None
    response = pay("CLM-1004", 186)
    assert response.status_code == 409
    assert response.json()["detail"] == "Claim CLM-1004 is not approved"
    response = decide("CLM-1004", "approve", 186)
    assert response.status_code == 409
    assert response.json()["detail"] == "Claim CLM-1004 is not in progress"


def test_a_referral_is_decided():
    start("CLM-1005")
    claim = decide("CLM-1005", "refer", 0).json()
    assert claim["status"] == "decided"
    assert claim["decision"]["decision"] == "refer"


def test_a_waiting_claim_cannot_be_decided():
    assert decide("CLM-1001", "approve", 420).status_code == 409


def test_a_decline_or_referral_cannot_carry_a_payout():
    start("CLM-1004")
    response = decide("CLM-1004", "decline", 50)
    assert response.status_code == 400
    assert response.json()["detail"] == "A decline or referral pays 0"


def test_payouts_and_payments_cannot_be_negative():
    start("CLM-1001")
    assert decide("CLM-1001", "approve", -1).status_code == 422
    decide("CLM-1001", "approve", 420)
    assert pay("CLM-1001", -420).status_code == 422


def test_steps_come_back_in_order():
    for kind, text in [("tool_call", "get_claim"), ("tool_result", "{}")]:
        step = client.post(
            "/api/claims/CLM-1001/steps", json={"kind": kind, "text": text}
        ).json()
        assert step["kind"] == kind
    steps = client.get("/api/claims/CLM-1001/steps").json()
    assert [(step["kind"], step["text"]) for step in steps] == [
        ("tool_call", "get_claim"),
        ("tool_result", "{}"),
    ]
    assert steps[0]["step_id"] < steps[1]["step_id"]
    assert client.get("/api/claims/CLM-1002/steps").json() == []


def test_steps_need_a_known_claim():
    response = client.post(
        "/api/claims/CLM-9999/steps", json={"kind": "message", "text": "Hello"}
    )
    assert response.status_code == 404
    assert client.get("/api/claims/CLM-9999/steps").status_code == 404


def test_the_queue_shows_each_decision_and_payout():
    start("CLM-1003")
    decide("CLM-1003", "approve", 1150)
    summary = client.get("/api/claims").json()[2]
    assert summary["status"] == "waiting_for_sign_off"
    assert summary["decision"] == "approve"
    assert summary["payout"] == 1150


def test_seeding_again_resets_the_queue():
    start("CLM-1001")
    decide("CLM-1001", "approve", 420)
    pay("CLM-1001", 420)
    client.post("/api/claims/CLM-1001/steps", json={"kind": "message", "text": "Hi"})
    seed()
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "waiting"
    assert claim["decision"] is None
    assert claim["payment"] is None
    assert client.get("/api/claims/CLM-1001/steps").json() == []
