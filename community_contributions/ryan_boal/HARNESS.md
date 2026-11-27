# Week 1 Day 5: the harness

Ryan Boal

My build of the harness brief in `docs/HARNESS.md`, starting from Ed's `week1day5-start`. I directed the work; Claude Code planned and built it in six phases, then restructured it after Ed's human review in `docs/HUMAN_REVIEW_HARNESS.md`.

**Code after the review:** https://github.com/ryanboal/undercover/tree/week1day5-end

**Code before the review:** https://github.com/ryanboal/undercover/tree/week1day5-start (both branches keep Ed's names, but hold my build)

**Plan:** [PLAN_HARNESS.md](https://github.com/ryanboal/undercover/blob/week1day5-start/docs/PLAN_HARNESS.md)

## How it works

- **A queue agent and a claim agent.** The queue agent plans the run as a to-do list and hands each claim to a fresh claim agent, which reports back in a line. Both use LangChain's `create_agent` and its middleware.
- **Rules in code.** The model chooses the order and writes the summary. The tools enforce the cap and the check for missed claims, and the backend enforces retries, sign-off and never deciding or paying twice.
- **Looking things up.** The wording and the manual are split into 26 sections and searched with SQLite's FTS5. The instructions hold only their contents, and the claim page shows each section the agent read.
- **Failures.** A claim that fails goes back in the queue. After a second failure it moves to a new state, Needs a handler, instead of being recorded as a referral the agent never made.

## Live runs and score

All on DeepSeek V4.1 Flash, scored against the handlers' decisions in `data/evals/` after each run. The agent never sees them.

| Run | Time | Decision and payout right |
|---|---|---|
| Capped at five, before the fixes below | about 1.5 min | 5 of 5 |
| All 25, after the fixes | 7 min 46 s | 24 of 25 |
| 25 held-out claims, without the rule below | 9 min 49 s | 25 of 25 |
| 25 held-out claims, with the rule | 8 min 44 s | 25 of 25 |
| Five claims and CLM-1025, with the rule | not timed in full | 6 of 6 |

| Difficulty, in the full run of the queue | Claims | Right |
|---|---|---|
| Routine | 15 | 15 |
| Needs the manual or the claim history | 5 | 5 |
| Hard | 5 | 4 |

The miss was CLM-1025, approved and paid at $71.00. The handler referred it because the carrier's certificate doesn't give the cause of the delay. The agent took the cause from the customer's story and said the certificate confirmed it.

The rule I then added comes from section 5 of the manual: each required document must itself state what it has to prove. It did no harm on the held-out claims, and they can't show whether it helps, because the agent already had them all right. With the rule, CLM-1025 was referred because the certificate gives no cause, but that is one try on the claim that prompted the rule.

In the full run of the queue, three approvals over $1,000 were held for sign-off and the other twelve were paid once each. No claim failed in any run, so the retries and outage handling have been tested only with stub models. Each run was done once.

## What we learned

- **A contents list mostly replaced search.** Only 3 of the 25 claim agents in the full run searched. The others went straight to the sections they needed.
- **Search needed stemming.** A search for "monkey" missed "Monkeys" until we turned on the Porter stemmer.
- **A request in the instructions isn't a rule.** They ask for reasons of two or three sentences, and three of the five in the first run ran longer. The limits enforced in code held.

## Gaps found after the build

Every check was green, but rereading the code for this write-up found four gaps. Each now has a fix and tests that failed before it.

- `--cap 0` ran the whole queue, because zero was read as no cap. A cap below 1 is now refused.
- A claim agent that failed between approving and paying left the claim unpaid. The harness now pays it, within the sign-off limit.
- A second run released the claim the first was working on. Only one agent now runs at a time on a machine.
- A backend error at the wrong moment stopped the run. Short outages are now waited out, and the run carries on after other backend errors. With stub models, a run survived the backend being killed and restarted. A backend that stays down still ends the run, and the next one puts right what was left.

## After the human review

Ed's review found four problems in the agent: backend URLs hard-coded in more than 20 places with two ways to call the backend, modules reaching into each other, the harness mixed with UnderCover's rules, and instructions written as step-by-step scripts. All four were real.

**How they got through.** Every check was about behavior: lint, types, coverage and tests, and they were all green. Nothing in the process reviewed the design, and the code standards said nothing about module boundaries, calls to the backend or how to write instructions. The plan never said which module held what, and it planned the scripted instructions itself. Each phase then built around the last one instead of restructuring it.

**What changed.**

- **The agent** is now seven layers, each importing only from those before it: `api` (every backend call, with the address in one place), `context`, `rules`, `tools` (all the tools, taking their state from `ToolRuntime`), `steps`, `harness` and `__main__`.
- **The instructions** give each agent a goal, what to rely on and its boundaries, with no numbered steps.
- **The backend's** 409-line `main.py` is split by resource, with the API unchanged. In the dashboard, repeated markup was extracted and the claim page split up.
- **Three more problems** turned up along the way and were fixed: a claim agent could try to act on another claim, ids from the model could reach other backend operations, and two identical to-do items broke the list.

**How it won't repeat.** `CODE_STANDARDS.md` gained rules on all of this. `PROCESS.md` now asks each plan to say which module holds each piece, and each phase to end with a review of the whole diff against the standards. A structure test fails on layering, stray backend calls, stray tools, long functions and numbered instructions, and ESLint blocks `fetch` outside the dashboard's API module. I planted violations of four of these checks, and each was caught. They can't judge design, so the review step matters most.

## Comparing the instructions

After the restructure, one full run of the queue scored 24 of 25. So I compared the two sets of instructions on the same harness, alternating them, each run in its own database.

| | Step-by-step | Goals |
|---|---|---|
| Three full runs of all 25 | 73 of 75 | 71 of 75 |
| Five random routine claims, three times | 15 of 15 | 15 of 15 |
| The ten hard and manual claims, three times | 29 of 30 | 28 of 30 |
| Sections read per claim, full runs | 8.4 | 10.6 |

Across six tries at the hard and manual claims, the step-by-step instructions got 57 of 60 and the goals 55 of 60, which is too close to separate them. No claim was missed every time. Four of the goals' five misses paid a claim the handler referred, and they missed CLM-1025 twice despite its rule. Those are hints, not proof, and I didn't tune the instructions for them.

**A bug the runs found.** One full run left CLM-1006 for a handler. Its customer has no earlier claims, and the history tool handed the model an empty reply, so it asked again, up to 37 times, until it ran out of model calls. It looped in three of the six full runs, with both sets of instructions. Tools now always give the model text, saying so when nothing is found, and a new standard and check stop a tool returning a bare list. CLM-1006 then asked once and was right in all nine tries.

## My takeaways

- **Let the model organize, and let the code guarantee.** The agent planned its own work and kept its own to-do list, and I didn't need to trust it with the cap or the payments, because the tools and the backend refuse what isn't allowed.
- **Green checks only cover the failures you thought of.** The build met every criterion in its plan and still had four gaps. Asking "what if it stops right here?" at each step found them, so I'd put that question in the plan next time.
- **A lost reply is harder than a failed request.** When a reply never arrives, the payment may or may not have gone through. Retrying blindly isn't safe, so the harness checks the claim's state and the backend refuses a second payment.
- **Scoring found what the checks couldn't.** The harness worked as designed on CLM-1025, and the decision was still wrong: the agent read the right rule, then trusted the story over the document. The miss prompted a general rule drawn from the manual, and the held-out claims showed that it did no harm, not that it works.
- **Passing checks isn't passing review.** Every test was green and the code still wasn't fit for a PR. The checks only asked whether it worked, not whether it was well built. Now a reviewer's pass over the whole diff is part of every phase.
- **One run proves very little.** A single run after the restructure looked like a new mistake, and six runs showed it was chance. A real bug only showed up because the runs were repeated: an empty reply the model read as a failed call.
