"""Run the UnderCover Agent: uv run -m agent [--cap N | CLM-1001]"""

import argparse
import sys

from agent.main import work_claim
from agent.queue import run_queue


def main(args: list[str]) -> None:
    """Work one named claim, or the queue in one run up to a cap."""
    parser = argparse.ArgumentParser(prog="uv run -m agent")
    parser.add_argument("claim_id", nargs="?", help="work only this claim")
    parser.add_argument("--cap", type=int, help="the most claims the run may work")
    options = parser.parse_args(args)
    if options.claim_id:
        print(work_claim(options.claim_id))
    else:
        print(f"\n{run_queue(options.cap)}")


if __name__ == "__main__":
    main(sys.argv[1:])
