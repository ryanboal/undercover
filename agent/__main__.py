"""Work the queue with the UnderCover Agent: uv run -m agent [CLM-1001]"""

import sys

from agent.main import call_backend, work_claim


def main(args: list[str]) -> None:
    """Work the claim named on the command line, or every waiting claim."""
    claim_ids = args or [
        claim["claim_id"]
        for claim in call_backend("GET", "/api/claims")
        if claim["status"] == "waiting"
    ]
    for claim_id in claim_ids:
        print(work_claim(claim_id), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
