# Plan: the claims pilot

We build the first version of UnderCover's claims platform from `docs/SPEC.md`:

- a backend that holds the queue and enforces the $1,000 rule
- the UnderCover Agent, which works a claim through the backend's API
- a dashboard where handlers see the queue, each claim in full, the agent's steps as it works and its instructions, and sign off large payouts

The work is in six phases. Each one builds on the last and ends with checks I run myself, then a commit.

## How it fits together

```
 dashboard (React, :5173) --HTTP--> backend (FastAPI, :8000) <--HTTP-- UnderCover Agent
                                         |                          (create_agent on OpenRouter)
                                    SQLite database
                                         ^
                       uv run -m backend.seed loads data/ (never data/evals/)
```

The backend is the single source of truth. The agent has no access to files or the database. It sees a claim, the claim's policy, the customer's claim history and its own instructions only through the API, and it records its decision and payment through the API too. The backend makes the payment rules hold, whatever the agent tries.

### How a claim moves through the queue

| From | What happens | To |
|---|---|---|
| Waiting | The agent starts work (`start_claim`) | In progress |
| In progress | The agent declines or refers | Decided |
| In progress | The agent approves with a payout of $1,000 or less | In progress, payment due |
| In progress, payment due | The agent pays the payout (`pay_claim`) | Decided |
| In progress | The agent approves with a payout over $1,000 | Waiting for sign-off |
| Waiting for sign-off | The agent tries to pay | Refused, still waiting |
| Waiting for sign-off | A handler signs off in the dashboard | Decided, paid |

A referral is a decision, so a referred claim is Decided with the decision Refer. "Decided" always means there's nothing left for the agent to do: an approved claim is Decided only once it's paid.

`pay_claim` succeeds only when the claim is approved, in progress and unpaid, the amount equals the approved payout, and the payout is $1,000 or less. Otherwise it's refused with the reason, such as "A payout over $1,000.00 needs a handler's sign-off". Matching the amount to the payout stops the agent splitting a large payout into small payments. A decision is final: `decide_claim` is refused unless the claim is in progress. The $1,000 limit is read from `data/company.json` (`payout_approval_limit`), not written into the code.

### The API

Every operation has an `operation_id`, a one-line docstring and only required inputs, as `docs/TECH_STACK.md` asks. A test checks this for every route in the OpenAPI schema, so it stays true as the API grows.

| Operation | Method and path | Used by |
|---|---|---|
| `health` | `GET /api/health` | checks |
| `list_claims` | `GET /api/claims` | dashboard, `uv run -m agent` |
| `get_claim` | `GET /api/claims/{claim_id}` | dashboard, agent |
| `get_policy` | `GET /api/policies/{policy_id}` | dashboard, agent |
| `get_customer` | `GET /api/customers/{customer_id}` | dashboard |
| `get_claim_history` | `GET /api/customers/{customer_id}/claim-history` | agent |
| `list_handlers` | `GET /api/handlers` | dashboard |
| `get_instructions` | `GET /api/instructions` | agent, dashboard |
| `start_claim` | `POST /api/claims/{claim_id}/start` | agent's run |
| `add_step` | `POST /api/claims/{claim_id}/steps` (kind, text) | agent's run |
| `list_steps` | `GET /api/claims/{claim_id}/steps` | dashboard |
| `decide_claim` | `POST /api/claims/{claim_id}/decision` (decision, payout, reason, policy_section) | agent |
| `pay_claim` | `POST /api/claims/{claim_id}/payment` (amount) | agent |
| `sign_off_claim` | `POST /api/claims/{claim_id}/sign-off` (handler_id) | dashboard |

### Choices, and why

- **SQLite through Python's built-in `sqlite3`.** The stack asks for SQLite, and there are five small tables, so an ORM would add a layer without saving any work. Claims, policies, customers and handlers keep their original JSON record next to the columns we update (status, decision, payment). The database is `backend/undercover.db`, which git already ignores, or the path in `UNDERCOVER_DB` when that's set (the end-to-end tests use it).
- **The backend seeds itself** when the database is empty, so `npm run dev` works on a fresh clone. `uv run -m backend.seed` resets the queue at any time. It's safe to run while the servers are up.
- **The agent's instructions and the policy wording are served together.** `GET /api/instructions` returns the instructions from `backend/agent_instructions.md` followed by the full `data/policy_wording.md`, and that's the agent's whole system prompt. The dashboard's Instructions page shows exactly what the agent sees. Because the wording sits at the start of every prompt, the model provider can cache it across claims, which costs less than the agent fetching it with a tool on every claim.
- **The agent gets the claim history only.** `customers.json` is personal data. The agent needs only the earlier claims, so its tool returns those and leaves out the address, phone number and date of birth. The dashboard gets the full record.
- **The agent's run records its steps, not the model.** `run(claim_id, thread_id)` streams the agent's updates. It posts each step to the backend: the agent's messages, each tool call with its arguments, and each tool's result. The model can't skip or invent steps, and the dashboard shows them by polling.
- **A refused tool call goes back to the model as text.** When the backend refuses a payment, the tool returns the reason to the model instead of raising an error. The agent sees it, the step shows it, and the run finishes cleanly.
- **The dashboard polls every two seconds.** That's enough to watch the agent work, and much simpler than WebSockets or server-sent events.
- **Two small, well-known libraries for the dashboard.** `react-router` handles the three pages, which is clearer than hand-written routing. `react-markdown` with `remark-gfm` shows the instructions and the wording's tables properly, not as raw markdown.
- **The end-to-end tests get their own servers and database.** Playwright starts the backend on port 8001, with a freshly seeded database in the system temp folder, and the dashboard on port 5174. `npm run check` then never touches your working queue, where the agent's decisions cost money to make, and it can run while `npm run dev` is up. `dashboard/vite.config.ts` reads the backend's address from `BACKEND_URL`, with `http://127.0.0.1:8000` as the default.
- **Colors from the brand.** Statuses: Decided in Sea Green, In progress in Marigold, Waiting for sign-off in Coral, Waiting in Cerulean. Decisions: Approve in Sea Green, Refer in Marigold, Decline in Coral. Raspberry marks a refused payment or an error. Every color comes with a text label, so color is never the only signal.

## Getting ready

- [x] `uv sync` and `npm install` run. There's no `node_modules` yet, so `npm install` also installs the pre-commit hook and Playwright's Chromium.
- [x] `npm run check` passes on the skeleton before anything changes.
- [x] Commits go on `week1day3-ryanb`, staging only the build's files. Your changes to `labs/week1day2.ipynb` and `setup/setup.ipynb` stay uncommitted.

## Phase 1: The records

**Builds** the database, the seed and the read-only API, so that everything else has real data to work on.

- `backend/db.py`: the connection and the schema (claims, policies, customers, handlers, steps)
- `backend/seed.py`: `uv run -m backend.seed` recreates the tables and loads `claims.json`, `policies.json`, `customers.json` and `handlers.json` from `data/`. Each claim starts as Waiting (the data says `open`). Nothing is read from `data/evals/`.
- `backend/models.py`: Pydantic models for every record and response, so the OpenAPI schema is fully typed
- Routes: `list_claims` (each claim with its customer's name, status, decision and payout), `get_claim`, `get_policy`, `get_customer`, `get_claim_history`, `list_handlers`
- The test that checks every operation for an `operation_id`, a one-line docstring and only required inputs

**Success criteria**

- [x] `uv run -m backend.seed` prints `Seeded 25 claims, 50 policies, 49 customers and 3 handlers.`
- [x] `GET /api/claims` returns 25 claims, CLM-1001 to CLM-1025, all `waiting`, with no claim from the held-out set (CLM-11xx)
- [x] `GET /api/claims/CLM-1001` returns Maya Patel's trip delay with the story, 3 items, 4 documents, `amount_claimed` 420.0, status `waiting`, and `decision` and `payment` both null
- [x] `GET /api/policies/POL-2001` returns the Premium plan and the Rome trip from 2026-06-10 to 2026-06-18
- [x] `GET /api/customers/CUS-3001/claim-history` returns one earlier claim, CLM-0412, and no address, phone number or date of birth
- [x] `GET /api/claims/CLM-9999` returns 404
- [x] The OpenAPI test passes for every operation
- [x] The backend seeds itself on startup when the database is empty (tested with a temporary database)
- [x] `grep -rn evals backend agent` finds nothing
- [x] `npm run check:python` passes with coverage at 80% or more

## Phase 2: The claim workflow and the $1,000 rule

**Builds** the operations that move a claim through the queue, with the payment rule enforced by the backend. It comes before the agent, so the rule is proven on its own before anything tries to break it.

- Routes: `start_claim`, `add_step`, `list_steps`, `decide_claim`, `pay_claim`, `sign_off_claim`
- `get_claim` now includes the decision (decision, payout, reason, policy section, when) and the payment (amount, paid by, when)
- `sign_off_claim` takes a handler id. The handler must exist and have `can_approve_over_limit`. It records the payment against the handler's name and marks the claim Decided.

**Success criteria**

- [x] pytest covers every move in the table above and every refusal
- [x] On a fresh seed, these API calls (made with curl) give these results:
  - [x] `start_claim` on CLM-1001 makes it `in_progress`; a second `start_claim` returns 409
  - [x] `decide_claim` approve with payout 420.00 keeps it `in_progress` with the decision recorded; `pay_claim` 420.00 makes it `decided`, paid by the UnderCover Agent
  - [x] On CLM-1003, `decide_claim` approve with payout 1,150.00 makes it `waiting_for_sign_off`
  - [x] `pay_claim` 1,150.00 on CLM-1003 returns 403, saying it needs a handler's sign-off; `pay_claim` 900.00 is refused because it doesn't match the payout; the claim stays unpaid
  - [x] `sign_off_claim` with HND-01 makes CLM-1003 `decided`, paid 1,150.00 by Dana Whitfield; signing off again returns 409
  - [x] `decide_claim` decline on CLM-1004 makes it `decided` with no payment; `pay_claim` on it is refused; `decide_claim` again returns 409
  - [x] Two `add_step` calls on CLM-1001 come back in order from `list_steps`
- [x] `uv run -m backend.seed` puts all 25 claims back to `waiting` with no decisions, payments or steps
- [x] `npm run check:python` passes with coverage at 80% or more

## Phase 3: The UnderCover Agent

**Builds** the agent on the workflow. It reads the claim, decides it, records the decision and pays, and its run posts every step to the backend.

- `backend/agent_instructions.md` and the `get_instructions` route. The instructions are short and say what to achieve, not every keystroke: work the claim as a handler would; read the claim, its policy and the customer's claim history; decide by the policy wording (covered trip dates, the 90-day filing window, the benefit's conditions and exclusions, the general exclusions and the add-ons); work out the payout as section 10 says; refer only when a required document is missing, the story and the documents disagree or the wording doesn't settle it; give the reason in two or three plain sentences with the section; pay an approved claim, knowing a payout over $1,000 waits for a handler's sign-off. Nothing from the claims manual goes in, as the spec says.
- `agent/tools.py`: `get_claim`, `get_policy`, `get_claim_history`, `decide_claim` and `pay_claim`, each a thin call to the API. A refusal comes back to the model as text.
- `agent/main.py`: `run(claim_id, thread_id)` starts the claim, fetches the instructions from the API, runs `create_agent` on the model (`openai/gpt-6-luna` at low reasoning, or `MODEL_NAME`), posts each step as it happens and returns the agent's final reply
- `agent/__main__.py`: `uv run -m agent` works every waiting claim in turn, and `uv run -m agent CLM-1001` works one. Each claim gets a new thread id.

If the model fails partway through, the run stops and the claim stays In progress until a reseed. Retries and failure handling belong to the harness on Week 1 Day 5, so the pilot leaves them out.

**Success criteria**

- [x] Tests with a stub model, with no real model calls:
  - [x] An approval under $1,000 ends Decided and paid by the agent, with the steps recorded in order: tool calls, their results and the final message
  - [x] An approval over $1,000 where the agent then tries to pay ends Waiting for sign-off with no payment, and the refusal appears in the steps
  - [x] A decline ends Decided with no payment
  - [x] The system prompt is the text from `GET /api/instructions`
  - [x] `uv run -m agent` works only the waiting claims, and `uv run -m agent CLM-1001` works just that one
- [x] `GET /api/instructions` returns the instructions followed by the full policy wording
- [x] `grep -rn "data/" agent` finds nothing: the agent reads no files
- [x] A live run: with `npm run dev` up, `uv run -m agent CLM-1001` uses the real model (a few cents at most). It ends with CLM-1001 Decided or Waiting for sign-off, with a decision, a payout, a reason of two or three sentences and a policy section, and its steps appear in `GET /api/claims/CLM-1001/steps`.
- [x] `npm run check:python` passes with coverage at 80% or more

## Phase 4: The dashboard and the queue

**Builds** the dashboard's frame in UnderCover's brand and the queue page, and moves the end-to-end tests onto their own servers.

- `dashboard/index.html` loads Instrument Sans, Instrument Serif and JetBrains Mono from Google Fonts
- `dashboard/src/styles.css`: the brand colors and surfaces as CSS variables for light and dark mode, following the system setting; rounded panels with no outlines
- `react-router` with three routes: the queue (`/`), a claim (`/claims/:claimId`) and the instructions (`/instructions`), with a header that links to the queue and the instructions
- `src/api.ts` (types that mirror the backend's models, and fetch functions), `src/format.ts` (money as $1,250.00, dates, claim types in plain words) and `src/usePolling.ts`
- The queue page: a count for each of the four statuses, and a table of claims (claim, customer, type, amount claimed, submitted, status, decision, payout), each linking to its claim page. It refreshes every two seconds.
- The health page goes. `playwright.config.ts` runs the backend on port 8001 with a freshly seeded database in the temp folder, and the dashboard on port 5174 pointing at it. `e2e/queue.spec.ts` replaces `e2e/health.spec.ts`.

**Success criteria**

- [ ] vitest: the queue renders claims from a stubbed API with the right status labels and money formats, the counts are right, and a poll picks up a change
- [ ] e2e: the queue shows 25 claims, and clicking CLM-1001 opens its page
- [ ] In the browser with the Playwright MCP server, at `localhost:5173`:
  - [ ] the queue shows 25 claims, with each status's count, in Instrument Sans with money in JetBrains Mono
  - [ ] the page background is `#F0F4F5` in light mode and `#04232E` in dark mode, with white and black panels
  - [ ] after `start_claim` on CLM-1002 with curl, its row shows In progress within three seconds, without a reload
- [ ] `npm run e2e` passes while `npm run dev` is running, and afterwards the dev queue is exactly as it was
- [ ] `npm run check:ts` passes with coverage at 80% or more

## Phase 5: The claim page and sign-off

**Builds** each claim in full with the agent's decision and its reasons, and the handler's sign-off.

- The claim page: the claim's id, status, customer and summary; the customer's story; the items with their amounts and the total claimed; the documents; the policy (plan, add-ons, purchase date, trip, trip cost, travelers); the customer's earlier claims
- The decision panel: the decision, payout, reason and policy section, and the payment: paid, and by whom, or waiting for sign-off
- The sign-off panel, only while a claim is Waiting for sign-off: a choice of handler and a Sign off button. A refusal from the backend shows in Raspberry.

**Success criteria**

- [ ] vitest: the page in each state: Waiting with no decision yet, approved and paid, declined, referred, and Waiting for sign-off with the panel; signing off sends the chosen handler and the page updates
- [ ] e2e: on CLM-1003, acting as the agent through the API: start, approve with payout 1,150.00, and try to pay (refused with 403). The claim page shows Waiting for sign-off. Choose Dana Whitfield and sign off, and the page shows paid $1,150.00, signed off by Dana Whitfield. The queue shows CLM-1003 as Decided.
- [ ] In the browser: CLM-1001, from the Phase 3 live run, shows the agent's decision, payout, reason and policy section
- [ ] `npm run check` passes

## Phase 6: Watching the agent work, and its instructions

**Builds** the last two things the team needs to see. Then the pilot is wrapped up.

- The steps on the claim page: a timeline of the agent's messages, tool calls (the tool and its arguments, in JetBrains Mono) and results (folded away, open on a click). It updates every two seconds while the agent works, and refused calls are marked.
- The Instructions page: the agent's instructions and the policy wording from `GET /api/instructions`, rendered as markdown, read only
- `docs/STATUS.md` says what's built and how to run it

**Success criteria**

- [ ] vitest: the steps render each kind and fold the results away; new steps appear after a poll; the Instructions page renders headings and tables and has no inputs
- [ ] e2e: steps added through the API appear on an open claim page without a reload; the Instructions page shows the instructions and the policy wording's section headings, with nothing to edit
- [ ] A live run in the browser: with the claim page for CLM-1003 open, `uv run -m agent CLM-1003` (a few cents at most) shows its steps arriving one at a time, and the claim ends Decided or Waiting for sign-off
- [ ] `npm run check` passes: ruff, pyright, pytest, ESLint, Prettier, tsc, vitest and Playwright
- [ ] `uv run -m backend.seed` resets the queue, so the pilot starts with 25 waiting claims

## Left out of the pilot

- What the spec leaves for later: the claims manual, sign-in, real payments (a payment is a record in the database), and messages to customers
- Scoring the agent against the handlers' decisions. `docs/PROCESS.md` says not to open `data/evals/` unless asked, so the pilot doesn't read it. See the first question below.
- Starting the agent from the dashboard. The spec asks for the team to see the queue and the agent's work, so the agent runs from the terminal with `uv run -m agent`.
- Retrying a claim when the agent fails. That's part of the Week 1 Day 5 harness.

## Questions for you

1. **Scoring.** Should the pilot include a command that scores the agent's decisions against `data/evals/decisions.json`, giving decision accuracy and payout accuracy? It would read that file only to score, never to show the agent. My default is to leave it out, since `docs/PROCESS.md` keeps `data/evals/` closed unless you ask.
2. **Live runs.** Phases 3 and 6 each run the real agent on one claim, a few cents at most on GPT-6 Luna. If you'd rather I make no model calls, or use `MODEL_NAME=openrouter/free`, say so and I'll adjust those two checks.
