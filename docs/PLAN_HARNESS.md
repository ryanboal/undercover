# Plan: the agent's harness

This plan builds the brief in `HARNESS.md` on top of the finished pilot, in six phases. Each phase leaves `npm run check` green and is committed before the next one starts. `PLAN.md` stays as it is.

When it's done, one command starts the UnderCover Agent on the queue. A queue agent plans the run as a to-do list, which the dashboard shows, and hands each claim to a fresh claim agent. The claim agent looks up the sections of the policy wording and the claims manual it needs, and the claim page shows what it read. Timeouts, provider errors and failed claims are put right by the harness, so one bad claim never stops the run or leaves a claim stuck in progress.

## Design

### Why this shape

The harness is the code around the model: its tools, its middleware and its instructions. The pilot's harness was a Python loop that fed the model one claim at a time with the whole wording in the prompt. This build hands the organizing to the model and keeps the guarantees in code:

- **The model decides what to do next.** The queue agent reads the queue, writes its to-do list, picks the order and writes the summary.
- **The code decides what is allowed.** The cap, the retry rule, "never decided or paid twice" and the check for missed claims are enforced by the tools and the backend, so they hold whatever the model does. This is the same pattern as the sign-off rule in the pilot: the agent can try, and the system refuses.

Everything is built with LangChain's `create_agent`, its built-in middleware and our own tools. No other agent framework is added (the brief rules it out, so `deepagents`, though installed for the labs, is not used).

### Two agents

| | Queue agent | Claim agent |
| --- | --- | --- |
| Job | Works the whole run | Works one claim from a clean start |
| Thread | The run id | A new thread id for each attempt |
| Tools | `list_claims`, `record_todos`, `work_claim`, `finish_run` | `get_claim`, `get_policy`, `get_claim_history`, `search_documents`, `read_section`, `record_decision`, `pay_claim` |
| Instructions | `backend/instructions/queue.md` | `backend/instructions/claim.md`, followed by the contents of the wording and the manual |
| Steps recorded | Its to-do list on the run | Every step on the claim, as in the pilot |

`work_claim` is the subagent: a tool of the queue agent that builds a claim agent, runs it to the end, and returns one line, such as `CLM-1001 approve $420.00, paid`, `CLM-1003 approve $1,350.00, held for sign-off`, `CLM-1007 failed (timeout), back in the queue` or `CLM-1007 failed twice, left for a handler`. The claim's long conversation stays inside the claim agent and never reaches the queue agent, so the queue agent's context grows by one line per claim instead of a whole claim's worth.

### Middleware

- `ModelRetryMiddleware` on both agents: retries a provider error or timeout with exponential backoff (3 retries). On the claim agent it raises once the retries are spent, so `work_claim` sees the failure.
- `ToolRetryMiddleware` on the claim agent, for network errors reaching the backend (`httpx.TransportError` only). A refusal from the backend is not an error: it goes back to the model as text, as in the pilot.
- `ModelCallLimitMiddleware` on the claim agent (25 model calls per attempt, `exit_behavior="error"`), so a claim agent that loops fails and is retried instead of running up cost. The queue agent gets a limit worked out from the cap (4 calls per claim plus 10).
- The model client has a 120-second request timeout.

### Failures, retries and the cap

The backend gains a fifth claim state and a count of failed attempts:

| State | Meaning | Label | Color |
| --- | --- | --- | --- |
| `needs_handler` | The agent failed on it twice | Needs a handler | Raspberry |

`work_claim(claim_id)` does this:

1. Refuses, as text to the model, if the claim isn't one the run may work: the run has already attempted as many claims as its cap and this claim isn't one of them.
2. Starts the claim with a new thread id. If the backend refuses (it isn't waiting), it returns that, so a claim can never be started twice.
3. Runs the claim agent, recording its steps.
4. If anything raises, or the claim agent ends without recording a decision, it records an `error` step and calls the new `release_claim` operation. The backend moves the claim back to `waiting` on the first failure and to `needs_handler` on the second.
5. Returns the one-line outcome.

A failed claim is back in the queue, so the queue agent can try it again later in the run; its to-do item goes back to "to do". `finish_run` is the check for missed claims: it refuses, with the list of claim ids, while a waiting claim remains that the run could still work, meaning the run is under its cap or the claim was tried once and is waiting for its retry. The queue agent then carries on. If the queue agent stops without finishing the run, the harness tells it to carry on, up to two times, and then finishes the run itself with a note that it stopped early.

A run that crashed (say, Ctrl-C) can leave a claim in progress. At the start of every run, the harness releases any claim still in progress, which counts as a failed attempt. So nothing stays stuck between runs either.

"Never decided or paid twice" already holds in the backend: `start_claim` needs a waiting claim, `record_decision` needs a claim in progress and the decision table allows one row per claim, and `pay_claim` refuses a second payment. `release_claim` adds one more rule: it refuses a claim that has a decision (409), so a decided claim can never go back in the queue.

### Runs and the to-do list

A new `runs` table holds one row per run: id, cap, started and finished times, the to-do list as JSON, and the summary.

| Operation | Route | What it does |
| --- | --- | --- |
| `start_run` | `POST /api/runs` | Body `{cap}`. Starts a run and returns it |
| `get_current_run` | `GET /api/runs/current` | The latest run, or `null` before the first one |
| `record_todos` | `PUT /api/runs/{run_id}/todos` | Body `{todos}`. Replaces the run's to-do list |
| `finish_run` | `POST /api/runs/{run_id}/finish` | Body `{summary}`. Finishes the run with the summary for the handlers; 409 if already finished |
| `release_claim` | `POST /api/claims/{claim_id}/release` | Body `{reason}`. Puts a failed claim back in the queue, or leaves it for a handler on its second failure |

A to-do item is `{task, status}`, where `status` is `to_do`, `in_progress`, `done` or `left_for_handler`. The queue agent rewrites the whole list each time it changes, the same shape as LangChain's `write_todos`. We write our own tool rather than use `TodoListMiddleware`, because the list has to be stored in the backend for the dashboard, not only in the agent's state.

The agent's `record_todos` and `finish_run` tools take only what the model decides (the list, the summary); the harness fills in the run id. `finish_run` runs the missed-claims check before it calls the backend.

### Looking things up in the wording and the manual

The seed splits `policy_wording.md` and `claims_manual.md` at their `##` headings into a `sections` table: document (`wording` or `manual`), number, title and text. The manual is about 2,900 words and the wording 1,400, in 26 sections.

| Operation | Route | What it does |
| --- | --- | --- |
| `search_documents` | `GET /api/documents/search?query=...` | The five best-matching sections across both documents, each with its document, number, title and a short snippet around the match |
| `read_section` | `GET /api/documents/{document}/sections/{number}` | One section in full |

Search uses SQLite's built-in full-text search (FTS5) with its ranking and snippets, so there is nothing new to install. The claim agent's instructions end with the contents of both documents (section numbers and titles only), so it can go straight to a section it knows it needs, such as section 10 of the wording for the payout or section 9 of the manual for repeat claims, and search for the rest, such as "monkey" or "receipts for meals".

Each `read_section` result is recorded as a step of a new kind, `read`, such as "Claims manual, section 9: Repeat claims", with the text folded underneath. The claim page shows these as "Read" lines, so the team can see what the agent looked up. A failure is recorded as a step of kind `error`.

### Instructions

`backend/instructions.md` becomes two files:

- `backend/instructions/queue.md`: list the waiting claims, write the to-do list, work each claim with `work_claim` in an order of the agent's choosing, keep the list up to date, retry a claim that went back in the queue, stay inside the cap, and finish with a summary of a few lines for the handlers.
- `backend/instructions/claim.md`: the pilot's instructions, rewritten so the agent looks up what it needs instead of being handed the wording, and updated with the manual: the decision rules in manual sections 2 and 8, the third claim in 12 months (section 9), the required documents (section 5), meals without receipts (section 10) and the interpretation notes (section 7). It is written from the wording and the manual only, never from `data/evals/`.

`get_instructions` returns `{queue, claim}`, where `claim` ends with the two contents lists. The instructions page shows both, read only.

### Model

The default becomes `deepseek/deepseek-v4.1-flash` with low reasoning effort. `MODEL_NAME` still overrides it, as before. Both agents use the same model.

### Running it

- `uv run -m agent` works the whole queue in one run, with the cap set to the number of waiting claims.
- `uv run -m agent --cap 5` works at most five claims and leaves the rest waiting.
- `uv run -m agent CLM-1001` works one named claim with the claim agent and its retry handling, without a run.

The command prints each `work_claim` line as it happens, then the run's summary.

### Dashboard

- The queue page gets an "Agent's to-do list" panel for the current run above the table: when it started, its cap, each item with its status, and the summary once it finishes. Status colors: to do Cerulean, in progress Marigold, done Sea Green, left for a handler Raspberry. Before any run it says "No runs yet". It refreshes every two seconds with the rest of the page.
- A fifth state tile and chip: Needs a handler, in Raspberry.
- The step list shows `read` steps as "Read" with the section's name, folded like a tool result, and `error` steps in Raspberry.
- The instructions page shows the queue agent's instructions, then the claim agent's.

### Tests

Tests never call a model. The pilot's `StubModel` gets a sibling for the queue agent, and `work_claim` takes the claim agent's model as an argument, so a test can give each claim a script, including one that raises. Tests run against the backend's test client and a temporary database, as in the pilot.

### How the criteria are checked

API calls run against `npm run dev` on a freshly seeded database. Pages are checked in the browser with the Playwright MCP server at `http://localhost:5173`. Only the criteria marked "Live" use the real model, and every live run reseeds first and is capped at five claims, as the brief asks.

## Phase 1: The wording and the manual as sections

Split both documents into sections at seed time, add `search_documents` and `read_section`, and update `SPEC.md` now that the manual is in use.

- [x] pytest: seeding stores 12 sections of the wording and 14 of the manual, with numbers and titles, and the text of each section without the next one's
- [x] `curl -s "localhost:8000/api/documents/search?query=monkey"` returns manual section 7 (Interpretation notes) first, with a snippet that mentions monkeys
- [x] `curl -s "localhost:8000/api/documents/search?query=meals%20without%20receipts"` includes manual section 10
- [x] `curl -s localhost:8000/api/documents/wording/sections/10` returns "How we work out your payment" and its text in full; `.../manual/sections/9` returns "Repeat claims"
- [x] An unknown document or section returns 404, and an empty query returns 422
- [x] A search with FTS5 syntax characters in it, such as `"quote` or `a AND (`, returns results or an empty list, not a 500
- [x] The OpenAPI test passes with the new operations
- [x] `docs/SPEC.md` no longer lists the claims manual as "Not for now", and says decisions follow the manual as well as the wording
- [x] `grep -rn evals backend agent dashboard/src` finds nothing
- [x] `npm run check` passes

## Phase 2: Runs, to-do lists and releasing a failed claim

Add the `runs` table and its four operations, `release_claim`, the `needs_handler` state, the attempt count, and the `read` and `error` step kinds.

- [ ] pytest covers every new rule, including each 404, 409 and 422
- [ ] `start_run` with cap 5 returns a run with an id, the cap, a start time, an empty to-do list and no summary; a cap of 0 returns 422
- [ ] `get_current_run` returns `null` on a fresh database, then the latest run once one has started
- [ ] `record_todos` with three items, then `get_current_run`, returns the three items in order; a status of `maybe` returns 422
- [ ] `finish_run` stores the summary and the finish time; a second call returns 409
- [ ] Walked through with curl: start `CLM-1001`, release it with a reason, and it is `waiting` again with 1 failed attempt; start and release it again, and it is `needs_handler`; `start_claim` on it then returns 409
- [ ] `release_claim` on a waiting claim returns 409, and on a claim with a decision returns 409
- [ ] `list_claims` and `get_claim` include the failed attempt count
- [ ] `record_step` accepts the kinds `read` and `error`
- [ ] The OpenAPI test passes with the new operations
- [ ] `npm run check` passes

## Phase 3: The claim agent

Turn the pilot's agent into the claim agent: the new instructions, the two look-up tools, the middleware, the default model, and `work_claim` with its failure handling. `uv run -m agent CLM-1001` uses it.

- [ ] `curl -s localhost:8000/api/instructions` returns `queue` and `claim`; `claim` ends with the contents of both documents and does not contain the full text of any section (for example, no "Worked example 1")
- [ ] pytest: the claim agent's tools are exactly `get_claim`, `get_policy`, `get_claim_history`, `search_documents`, `read_section`, `record_decision` and `pay_claim`, each named after a backend operation
- [ ] pytest: with `MODEL_NAME` unset the model is `deepseek/deepseek-v4.1-flash` with low reasoning effort; with `MODEL_NAME` set it is that model
- [ ] Stub model test: the stub searches, reads manual section 9, decides and pays. The claim is `decided` and paid, and its steps include a `read` step named "Claims manual, section 9: Repeat claims". `work_claim` returns `CLM-1001 approve $420.00, paid`
- [ ] Stub model test: an approval over the limit returns a line that says "held for sign-off", and the claim has no payment
- [ ] Stub model test, a failed claim: the stub raises partway. `work_claim` returns a line ending "back in the queue", the claim is `waiting` with 1 failed attempt, and an `error` step is recorded
- [ ] Stub model test, fails twice: the claim fails again on its second attempt and is `needs_handler`, and the line says "left for a handler"
- [ ] Stub model test: a stub that ends without recording a decision counts as a failure in the same way
- [ ] Stub model test: a provider error on the first call is retried by the middleware and the claim is then decided normally
- [ ] Stub model test: a stub that loops past the model call limit fails the attempt, and the claim goes back in the queue
- [ ] Stub model test: `work_claim` on a decided claim returns the backend's refusal, and the claim's decision and payment are unchanged
- [ ] Live: on a reseeded database, `uv run -m agent CLM-1001` prints a one-line outcome, and the claim's steps include at least one `search_documents` or `read_section` call and a `read` step
- [ ] `npm run check` passes

## Phase 4: The queue agent

Build the queue agent with `list_claims`, `record_todos`, `work_claim` and `finish_run`, the cap, the missed-claims check, the release of claims left in progress, and `uv run -m agent [--cap N]`.

- [ ] pytest: the queue agent's tools are exactly `list_claims`, `record_todos`, `work_claim` and `finish_run`
- [ ] Stub model test, a whole run: the queue stub lists the claims, records a to-do list, works three claims (each with its own claim stub), ticks each off and finishes. The run is stored with its to-do list all `done` and the summary, and each claim has its own steps and thread id
- [ ] Stub model test, the cap: with cap 2, a third `work_claim` is refused with a message about the cap, and the third claim stays `waiting` with no steps
- [ ] Stub model test, a failed claim doesn't stop the run: the second of three claims raises, the run carries on, and the third claim is decided
- [ ] Stub model test, retried: a claim fails once, goes back in the queue, the queue stub works it again and it is decided
- [ ] Stub model test, the missed-claims check: the queue stub calls `finish_run` with a claim still waiting under its cap; it is refused with that claim's id, the stub works it, and then `finish_run` succeeds
- [ ] Stub model test: a queue stub that stops without finishing is told to carry on, and one that never finishes has its run finished by the harness with a note that it stopped early
- [ ] Stub model test: a claim left `in_progress` before the run starts is released at the start and counts as a failed attempt
- [ ] Stub model test: `uv run -m agent --cap 2` prints a line per claim, then the summary
- [ ] Live: on a reseeded database, `uv run -m agent --cap 5` works five claims and finishes with a summary; 20 claims are still `waiting`, none is `in_progress`, and no claim has two decisions or two payments
- [ ] `npm run check` passes

## Phase 5: The dashboard

Add the to-do list panel, the Needs a handler state, the `read` and `error` steps, and both sets of instructions.

- [ ] vitest covers the to-do panel with no run, a run in progress and a finished run, each to-do status, the Needs a handler chip, `read` and `error` steps, and the instructions page with both parts, against a stubbed `fetch`
- [ ] e2e: the test starts a run and records a to-do list through the API. Without a reload, the queue page shows the items; after the test updates and finishes the run, it shows them done and the summary
- [ ] e2e: the test records a `read` step on a claim, and the claim page shows "Read" with the section's name, and the text when opened
- [ ] e2e: a claim released twice through the API shows Needs a handler on the queue and the claim page
- [ ] Browser, `/`: the to-do panel says "No runs yet" on a fresh database, and the state tiles show five states
- [ ] Browser, `/instructions`: the queue agent's instructions, then the claim agent's, with no text box, input or edit button in the snapshot
- [ ] Browser, with `browser_evaluate`: each to-do status and the Needs a handler chip have the background colors from the design
- [ ] Browser: screenshots of the queue with a run in light and dark mode follow `BRAND.md`: rounded panels with no outlines, no one-edge borders and no gradients
- [ ] Browser: `browser_console_messages` shows no errors on any page
- [ ] `npm run check` passes

## Phase 6: A live run and the documents

Run the agent live as the brief's "what done looks like" describes, and bring the documents up to date.

- [ ] Live, in the browser: reseed, open `/`, and run `uv run -m agent --cap 5`. Snapshots taken during the run show the to-do list appearing and items being ticked off; the page ends with five claims worked, the summary, and 20 claims Waiting
- [ ] Live, in the browser: a claim from the run shows its steps, including "Read" lines for the sections it looked up, and its decision with a section and a reason of two or three sentences
- [ ] Live: every approval over $1,000 in the run is `waiting_for_sign_off` with no payment, and every other approval is paid exactly its payout
- [ ] `docs/SPEC.md` describes the manual, the run with its cap, the to-do list and the Needs a handler state
- [ ] `docs/TECH_STACK.md` names DeepSeek V4.1 Flash as the default model and describes the queue agent, the claim agent and the middleware
- [ ] `docs/STATUS.md` describes what's built, how to run the agent (whole queue, capped, one claim), and the results of the live run
- [ ] `npm run check` passes

## Not in this plan

- Scoring the agent against the handlers' decisions in `data/evals/`, which the process says not to open unless asked.
- Starting a run from the dashboard. Runs start from the command line, and the dashboard shows them as they happen.
- Running claims in parallel. The queue agent works one claim at a time, which keeps the run simple to follow on the dashboard.
- Keeping a run's state across a crash. The agent keeps its memory in process, and a crashed run is put right by releasing its claims at the start of the next run. Durable state comes later in the course.
