# Status

The claims pilot in `docs/PLAN.md` and the agent's harness in `docs/PLAN_HARNESS.md` are built: all six phases of each are done. The code was then restructured after `docs/HUMAN_REVIEW_HARNESS.md`, and the rules that came from it are 7 to 12 in `docs/CODE_STANDARDS.md`.

## Running it

- `npm run dev` starts the backend on port 8000 and the dashboard on http://localhost:5173.
- `uv run -m backend.seed` rebuilds the database from `data/`, putting every claim back in the queue.
- `uv run -m agent` works the whole queue in one run. `uv run -m agent --cap 5` works at most five claims and leaves the rest waiting. `uv run -m agent CLM-1001` works one claim with the claim agent. Each prints a line per claim, and a run ends with its summary. A cap must be at least 1, and only one agent runs at a time on a machine: it holds local port 8765 while it works. All use the real model through OpenRouter.

## Built

- `backend/`: `main.py` puts together one router per resource (`claims.py`, `records.py`, `documents.py` and `runs.py`); `database.py` holds the schema and the connection, and `seed.py` the seeding. SQLite database seeded from `data/` (never `data/evals/`), at `undercover.db` or the path in `UNDERCOVER_DB`, created on startup when missing. Read operations: `health`, `list_claims`, `get_claim`, `get_policy`, `get_claim_history`, `list_handlers`, `list_steps`, `get_instructions`, `search_documents` (full-text search over the sections of the policy wording and the claims manual) and `read_section`. Workflow operations: `start_claim`, `record_step`, `record_decision`, `pay_claim`, `sign_off_claim` and `release_claim`, which puts a failed claim back in the queue and leaves it for a handler (`needs_handler`) after its second failure, recording the reason as an `error` step. Runs: `start_run` (with a cap), `get_current_run`, `record_todos` and `finish_run`. A claim moves from waiting to in progress to decided, or to waiting for sign-off when an approval pays over the limit in `company.json`. `pay_claim` refuses such a payout with a 403 until a handler signs off, and signing off pays it. The agent's instructions are in `backend/instructions/`, and `get_instructions` serves the instructions for the queue and for a claim. A test checks that every operation follows the API rules.
- `agent/`: the queue agent and the claim agent, in layers that import only from those before them:
  - `api.py`: every backend call, one function per operation. It tries again for about 30 seconds when it can't connect, and never repeats a request that may have arrived.
  - `context.py`: what the code knows and the model can't change, such as the claim being worked and the cap.
  - `rules.py`: outcomes, payments that are due, missed claims and putting right work left half done.
  - `tools.py`: all the tools, with their state from `ToolRuntime`. A claim agent can only act on its own claim. Tools always give the model text, and say so when nothing is found.
  - `steps.py`: an agent's messages as steps for the dashboard.
  - `harness.py`: the model, the two agents with their middleware, and `work_claim` and `run_queue`, which run them. Provider errors are retried 3 times and a claim agent stops after 25 model calls. A failure before a decision releases the claim, and an approval within the limit that was left unpaid is paid. A queue agent that stops early is told to carry on, twice, before the harness closes the run.
- `dashboard/`: the queue (`/`), with counts by state (including Needs a handler), the agent's to-do list for the current run with its summary once finished, and a line per claim. A claim in full (`/claims/:claimId`), with its policy, earlier claims, the decision and payment, the agent's steps as it works (including the sections it read and any failed attempts), and a sign-off form for a held payout. The agent's instructions for running the queue and for working a claim (`/instructions`), read only. The queue and a claim page refresh every two seconds. Styled to `BRAND.md` in light and dark mode.
- `e2e/`: tests of the three pages, the agent's steps appearing on a claim page, a handler signing off a held payout, the to-do list filling in and finishing, a section read, and a claim that fails twice needing a handler. Playwright runs its own backend on port 8001 with `e2e/undercover.db`, and its own dashboard on port 5174, so it can run next to `npm run dev`.

## Last live runs: the two sets of instructions compared

On November 27, 2026, the same model worked all 25 claims six times, each in its own temporary database: three runs with the step-by-step instructions from before the review and three with the goal instructions, alternating, on the same harness. Scored against the handlers' decisions and payouts:

| Run | Step-by-step | Goals |
|---|---|---|
| 1 | 25/25 | 25/25 |
| 2 | 23/25 | 24/25 |
| 3 | 25/25 | 22/25 |
| Total | 73/75 | 71/75 |
| Sections read per claim | 8.4 | 10.6 |
| Claims that searched, per run | about 2 | about 16 |

Each run took 7 to 10 minutes. No claim was missed twice: the misses were CLM-1014 (paid $545.00, handler $605.00) and CLM-1023 (paid $61.00, handler referred) with the step-by-step instructions, and CLM-1021 (approved $1,053.00 and held for sign-off, handler $825.00), CLM-1024 and CLM-1025 (paid $250.00 and $71.00, handler referred both) and CLM-1006 (left for a handler) with the goals. CLM-1012, missed in the run below, was right all six times. Two claims in 75 can't separate the two: they decide about as well, and the goal instructions read and search more.

CLM-1006 was left for a handler because its customer has no earlier claims. The history tool gave the model an empty reply, so it asked again, up to 37 times, until it ran out of model calls. It looped in three of the six runs, with both sets of instructions. Tools now always give the model text, with a sentence when nothing is found, and a check stops a tool returning a bare list (rule 13 in `docs/CODE_STANDARDS.md`). With the fix, CLM-1006 was worked three times live: one history call each time, approved at $425.00, as the handler did.

## Retests after the fix

With the fix in place, the claim agent alone worked chosen claims three times with each set of instructions, alternating, in a fresh temporary database each round.

- Five claims picked at random with a fixed seed (CLM-1004, CLM-1005, CLM-1006, CLM-1009 and CLM-1016, all routine): 15/15 with each set, the same decision and payout every time. CLM-1006 asked for the history once each time and was approved at $425.00.
- The ten hard and manual claims (CLM-1011, CLM-1014 and CLM-1018 to CLM-1025), chosen from the difficulty in `data/evals/` for checking only: 29/30 with the step-by-step instructions and 28/30 with the goals. The misses were CLM-1021 paid $954.00 (handler $825.00) with the step-by-step instructions, and CLM-1025 and CLM-1019 approved and paid $71.00 and $210.00 (handler referred both) with the goals. The goals read 10.8 sections a claim against 8.3.

Over the six tries at the hard and manual claims, three here and three in the full runs, the step-by-step instructions got 57/60 and the goals 55/60. That gap is too small to separate them. Four of the goals' five misses approved and paid a claim the handler referred, against one of the step-by-step instructions' three, and the goals missed CLM-1025 twice in six, though its rule is in both. These are hints, not proof, and the instructions were not changed for them.

## Earlier live run, with the goal instructions

On November 24, 2026, after the restructure and with instructions that give goals instead of steps, the same model worked all 25 claims in a temporary database: 15 approve, 4 decline and 6 refer. No claim failed, every payment was right for its decision, and three approvals over $1,000 were held. The run took 54 minutes, 44 of them while the computer was asleep. Each claim agent read between 6 and 16 sections, 11.4 on average, and 18 of the 25 searched.

24 of 25 matched the handlers' decisions and payouts. CLM-1025 was referred, as the handler did. The miss was CLM-1012, a routine claim: the agent paid $920.00 where the handler declined because the bag was unattended. It had read the sections on unattended belongings and did not apply them. The earlier instructions declined it in the one full run they had. One run of each can't say whether the new instructions are better or worse. The held-out claims have not been run with them.

## Earlier live runs, with the step-by-step instructions

On November 23, 2026, after reseeding, `uv run -m agent` with `deepseek/deepseek-v4.1-flash` worked all 25 claims in 7 minutes 46 seconds: 15 approve, 5 decline and 5 refer. No claim failed. Three approvals were over $1,000 and waited for sign-off (CLM-1003, CLM-1008 and CLM-1011), and every other approval was paid its payout once, $4,730.00 in total. Each claim agent read between 4 and 14 sections, 8 on average, and 3 of the 25 searched.

Scored against the handlers' decisions in `data/evals/decisions.json`, 24 of 25 matched on both the decision and the payout: all 15 routine claims, all 5 that need the manual or the history, and 4 of the 5 hard ones. The miss was CLM-1025, which the agent approved and paid at $71.00. The handler referred it, because the carrier's certificate gives no cause for the delay. An earlier run capped at five claims matched on all five.

The claim instructions then gained one general rule from section 5 of the manual: each required document must itself state what it is required to prove. The 25 held-out claims were run once without the rule and once with it, in temporary databases, and all 25 matched on the decision and the payout both times. So the rule did no harm on those claims, and they can't show whether it helps. With the rule, a run capped at five and one run of CLM-1025 also matched on all six claims. CLM-1025 was referred because the certificate gives no cause, but that is one try on the claim that prompted the rule.
