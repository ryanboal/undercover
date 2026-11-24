"""Run the UnderCover Agent: uv run -m agent [--cap N | CLM-1001]"""

import argparse
import socket
import sys

from agent.api import BackendError, Unreachable
from agent.harness import run_queue, work_claim

LOCK_PORT = 8765


def main(args: list[str]) -> None:
    """Work one named claim, or the queue in one run up to a cap."""
    parser = argparse.ArgumentParser(prog="uv run -m agent")
    parser.add_argument("claim_id", nargs="?", help="work only this claim")
    parser.add_argument("--cap", type=int, help="the most claims the run may work")
    options = parser.parse_args(args)
    if options.cap is not None and options.cap < 1:
        parser.error("--cap must be at least 1")
    # Holding a local port is the lock: the system frees it even after a crash.
    with socket.socket() as lock:
        try:
            lock.bind(("127.0.0.1", LOCK_PORT))
        except OSError:
            sys.exit("The agent is already running. Try again when it has finished.")
        try:
            if options.claim_id:
                print(work_claim(options.claim_id))
            else:
                print(f"\n{run_queue(options.cap)}")
        except Unreachable as error:
            sys.exit(
                f"The backend can't be reached ({error}). The next queue run puts"
                " right anything left half done."
            )
        except BackendError as error:
            sys.exit(str(error))


if __name__ == "__main__":
    main(sys.argv[1:])
