# Status

The pilot is being built from `docs/PLAN.md`. Done so far: Phases 1 and 2.

## What's built

- `backend/`: FastAPI on SQLite. The database is `backend/undercover.db`, or the path in `UNDERCOVER_DB`. It seeds itself from `data/` when empty, and never reads `data/evals/`.
  - Read-only routes: `list_claims`, `get_claim`, `get_policy`, `get_customer`, `get_claim_history` (earlier claims only, no personal details), `list_handlers` and `health`
  - The workflow: `start_claim`, `add_step`, `list_steps`, `decide_claim`, `pay_claim` and `sign_off_claim`. A claim moves from waiting to in progress to decided, or to waiting for sign-off when the agent approves a payout over $1,000 (the limit in `data/company.json`).
  - `pay_claim` pays only an approved, unpaid claim, only its exact payout and only up to $1,000. A payout over $1,000 is paid by a handler's sign-off.
  - A test checks that every operation has an `operation_id`, a one-line docstring and only required inputs
- `agent/`: still the skeleton's hello-world agent
- `dashboard/`: still the skeleton's health page
- `e2e/`: one test of that page

## How to run it

- `npm run dev` starts the backend on port 8000 and the dashboard on port 5173
- `uv run -m backend.seed` resets the queue to the 25 waiting claims
- `npm run check` runs every check
