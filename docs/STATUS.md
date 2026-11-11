# Status

The pilot is built: all six phases of `docs/PLAN.md` are done.

## What's built

- `backend/`: FastAPI on SQLite. The database is `backend/undercover.db`, or the path in `UNDERCOVER_DB`. It seeds itself from `data/` when empty, and never reads `data/evals/`.
  - Records: `list_claims`, `get_claim`, `get_policy`, `get_customer`, `get_claim_history` (earlier claims only, no personal details), `list_handlers` and `health`
  - The workflow: `start_claim`, `add_step`, `list_steps`, `decide_claim`, `pay_claim` and `sign_off_claim`. A claim moves from waiting to in progress to decided, or to waiting for sign-off when the agent approves a payout over $1,000 (the limit in `data/company.json`). A referral is a decision, so a referred claim is decided.
  - `pay_claim` pays only an approved, unpaid claim, only its exact payout and only up to $1,000. A payout over $1,000 is paid by a handler's sign-off.
  - `get_instructions`: the agent's instructions in `backend/agent_instructions.md`, followed by the policy wording in `data/policy_wording.md`
  - A test checks that every operation has an `operation_id`, a one-line docstring and only required inputs
- `agent/`: the UnderCover Agent, LangChain's `create_agent` on OpenRouter (`openai/gpt-6-luna` at low reasoning, or `MODEL_NAME`)
  - `run(claim_id, thread_id)` starts the claim, takes its system prompt from `GET /api/instructions`, and posts every step to the backend as it works
  - Its tools, in `agent/tools.py`, call the API: `get_claim`, `get_policy`, `get_claim_history`, `decide_claim` and `pay_claim`. A refusal from the backend goes back to the model as text.
  - If the model fails partway through, the claim stays in progress until the next reseed
- `dashboard/`: React, Vite and TypeScript, in UnderCover's brand with light and dark mode
  - The queue at `/`: a count for each status and every claim with its status, decision and payout, refreshed every two seconds
  - A claim's page at `/claims/:claimId`: the story, items, documents, policy and the customer's earlier claims, with the agent's decision, payout, reason, policy section and payment
  - The agent's steps on the claim page, refreshed every two seconds while it works, with results folded away and refusals marked
  - While a claim waits for sign-off, a handler picks their name and signs off, which pays it
  - The agent's instructions at `/instructions`, read only
- `e2e/`: Playwright tests of the queue, the sign-off, the live steps and the instructions. They run on their own backend (port 8001, a freshly seeded database in the temp folder) and dashboard (port 5174), so they never touch the dev queue.

## How to run it

- `npm run dev` starts the backend on port 8000 and the dashboard at http://localhost:5173
- `uv run -m agent` works every waiting claim, and `uv run -m agent CLM-1001` works one. The backend must be running. With the dashboard open on a claim, you can watch the agent's steps arrive.
- `uv run -m backend.seed` resets the queue to the 25 waiting claims. A decided claim is final, so run this before working the queue again.
- `npm run check` runs every check

## Not in the pilot

- From the spec: the claims manual, sign-in, real payments and messages to customers
- Scoring the agent against `data/evals/`, starting the agent from the dashboard, and retrying a claim when the agent fails
