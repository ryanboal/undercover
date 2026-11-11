"""Work the queue: `uv run -m agent` for every waiting claim, or name the claims."""

import sys
import uuid

from agent import tools
from agent.main import run


def waiting_claims() -> list[str]:
    """List the claims waiting in the queue."""
    with tools.backend() as client:
        claims = client.get("/api/claims").raise_for_status().json()
    return [claim["claim_id"] for claim in claims if claim["status"] == "waiting"]


def main(claim_ids: list[str]) -> None:
    """Work the named claims, or every waiting claim, each in a new thread."""
    for claim_id in claim_ids or waiting_claims():
        print(f"{claim_id}: {run(claim_id, str(uuid.uuid4()))}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
