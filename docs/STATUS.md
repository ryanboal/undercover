# Status

The pilot is being built from `docs/PLAN.md`. Done so far: Phases 1 to 4.

## What's built

- `backend/`: FastAPI on SQLite. The database is `backend/undercover.db`, or the path in `UNDERCOVER_DB`. It seeds itself from `data/` when empty, and never reads `data/evals/`.
  - Read-only routes: `list_claims`, `get_claim`, `get_policy`, `get_customer`, `get_claim_history` (earlier claims only, no personal details), `list_handlers` and `health`
  - The workflow: `start_claim`, `add_step`, `list_steps`, `decide_claim`, `pay_claim` and `sign_off_claim`. A claim moves from waiting to in progress to decided, or to waiting for sign-off when the agent approves a payout over $1,000 (the limit in `data/company.json`).
  - `pay_claim` pays only an approved, unpaid claim, only its exact payout and only up to $1,000. A payout over $1,000 is paid by a handler's sign-off.
  - `get_instructions`: the agent's instructions in `backend/agent_instructions.md`, followed by the policy wording in `data/policy_wording.md`
  - A test checks that every operation has an `operation_id`, a one-line docstring and only required inputs
- `agent/`: the UnderCover Agent, LangChain's `create_agent` on OpenRouter (`openai/gpt-6-luna` at low reasoning, or `MODEL_NAME`)
  - `run(claim_id, thread_id)` starts the claim, takes its system prompt from `GET /api/instructions`, and posts every step to the backend as it works
  - Its tools, in `agent/tools.py`, call the API: `get_claim`, `get_policy`, `get_claim_history`, `decide_claim` and `pay_claim`. A refusal from the backend goes back to the model as text.
  - If the model fails partway through, the claim stays in progress until the next reseed
- `dashboard/`: React, Vite and TypeScript, in UnderCover's brand with light and dark mode
  - The queue at `/`: a count for each status and every claim with its status, decision and payout, refreshed every two seconds
  - A claim's page at `/claims/:claimId`, so far with its heading and status
- `e2e/`: Playwright tests on their own backend (port 8001, a freshly seeded database in the temp folder) and dashboard (port 5174), so they never touch the dev queue

## How to run it

- `npm run dev` starts the backend on port 8000 and the dashboard on port 5173
- `uv run -m agent` works every waiting claim, and `uv run -m agent CLM-1001` works one. The backend must be running.
- `uv run -m backend.seed` resets the queue to the 25 waiting claims
- `npm run check` runs every check
