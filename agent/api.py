"""Every call the agent makes to the UnderCover backend."""

import time
from typing import Any
from urllib.parse import quote

import httpx

BASE_URL = "http://localhost:8000/api"
CONNECT_DELAYS = (1, 2, 4, 8, 15)

type Record = dict[str, Any]


class BackendError(Exception):
    """The backend couldn't answer."""


class Unreachable(BackendError):
    """The backend couldn't be reached, or its reply was lost."""


class Refused(BackendError):
    """The backend understood the request and refused it."""

    def __init__(self, status: int, detail: object) -> None:
        super().__init__(f"Refused with status {status}: {detail}")
        self.status = status


def client() -> httpx.Client:
    """Return a client for the backend."""
    return httpx.Client(base_url=BASE_URL, timeout=30)


def call(method: str, *path: str, **options: Any) -> Any:
    """Call an operation and return its JSON, or raise a BackendError."""
    url = "/" + "/".join(quote(part, safe="") for part in path)
    try:
        response = send(method, url, **options)
    except httpx.TransportError as error:
        raise Unreachable(f"{type(error).__name__}: {error}") from error
    if response.is_client_error:
        raise Refused(response.status_code, response.json()["detail"])
    if response.is_error:
        raise BackendError(f"{response.status_code}: {response.text}")
    return response.json()


def send(method: str, url: str, **options: Any) -> httpx.Response:
    """Send a request, trying again only when it couldn't connect."""
    for delay in CONNECT_DELAYS:
        try:
            return send_once(method, url, **options)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            time.sleep(delay)
    return send_once(method, url, **options)


def send_once(method: str, url: str, **options: Any) -> httpx.Response:
    """Send a request."""
    with client() as backend:
        return backend.request(method, url, **options)


def list_claims() -> list[Record]:
    return call("GET", "claims")


def get_claim(claim_id: str) -> Record:
    return call("GET", "claims", claim_id)


def get_policy(policy_id: str) -> Record:
    return call("GET", "policies", policy_id)


def get_claim_history(customer_id: str) -> list[Record]:
    return call("GET", "customers", customer_id, "claims")


def search_documents(query: str) -> list[Record]:
    return call("GET", "documents", "search", params={"query": query})


def read_section(document: str, number: str) -> Record:
    return call("GET", "documents", document, "sections", number)


def get_instructions() -> Record:
    return call("GET", "instructions")


def start_claim(claim_id: str, thread_id: str) -> Record:
    return call("POST", "claims", claim_id, "start", json={"thread_id": thread_id})


def record_step(claim_id: str, kind: str, content: str) -> Record:
    body = {"kind": kind, "content": content}
    return call("POST", "claims", claim_id, "steps", json=body)


def record_decision(claim_id: str, decision: Record) -> Record:
    return call("POST", "claims", claim_id, "decision", json=decision)


def pay_claim(claim_id: str, amount: float) -> Record:
    return call("POST", "claims", claim_id, "payment", json={"amount": amount})


def release_claim(claim_id: str, reason: str) -> Record:
    return call("POST", "claims", claim_id, "release", json={"reason": reason})


def start_run(cap: int) -> Record:
    return call("POST", "runs", json={"cap": cap})


def get_current_run() -> Record:
    return call("GET", "runs", "current")


def record_todos(run_id: str, todos: list[Any]) -> Record:
    return call("PUT", "runs", run_id, "todos", json={"todos": todos})


def finish_run(run_id: str, summary: str) -> Record:
    return call("POST", "runs", run_id, "finish", json={"summary": summary})
