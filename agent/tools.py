"""The UnderCover Agent's tools, each a call to the backend's API."""

from typing import Any, Literal

import httpx
from langchain_core.tools import tool

BACKEND_URL = "http://localhost:8000"


def backend() -> httpx.Client:
    """Return a client for the UnderCover backend."""
    return httpx.Client(base_url=BACKEND_URL, timeout=30)


def call(method: str, path: str, body: dict[str, Any] | None = None) -> str:
    """Call the API and return its reply, or the reason it refused."""
    with backend() as client:
        response = client.request(method, path, json=body)
    if response.is_client_error:
        return f"Refused: {response.json()['detail']}"
    response.raise_for_status()
    return response.text


@tool
def get_claim(claim_id: str) -> str:
    """Get a claim: the customer's story, the items claimed and the documents."""
    return call("GET", f"/api/claims/{claim_id}")


@tool
def get_policy(policy_id: str) -> str:
    """Get a policy: the plan, add-ons, purchase date, trip and travelers."""
    return call("GET", f"/api/policies/{policy_id}")


@tool
def get_claim_history(customer_id: str) -> str:
    """Get the customer's earlier claims."""
    return call("GET", f"/api/customers/{customer_id}/claim-history")


@tool
def decide_claim(
    claim_id: str,
    decision: Literal["approve", "decline", "refer"],
    payout: float,
    reason: str,
    policy_section: str,
) -> str:
    """Record your decision on the claim, with the payout, reason and section."""
    return call(
        "POST",
        f"/api/claims/{claim_id}/decision",
        {
            "decision": decision,
            "payout": payout,
            "reason": reason,
            "policy_section": policy_section,
        },
    )


@tool
def pay_claim(claim_id: str, amount: float) -> str:
    """Pay an approved claim its payout, in US dollars."""
    return call("POST", f"/api/claims/{claim_id}/payment", {"amount": amount})


TOOLS = [get_claim, get_policy, get_claim_history, decide_claim, pay_claim]
