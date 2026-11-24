# Tech stack

- `backend/`: FastAPI and SQLite. Every API operation has an `operation_id`, a one-line docstring and no optional inputs. Paying a claim is a separate operation that takes the amount.
- `backend/`'s full-text search over the policy wording and the claims manual uses SQLite's built-in FTS5, with the Porter stemmer.
- `agent/`: two agents built with LangChain's `create_agent` on OpenRouter, and no other agent framework. The queue agent works a run with the tools `list_claims`, `record_todos`, `work_claim` and `finish_run`. `work_claim` hands each claim to a fresh claim agent, a subagent that works one claim and reports back in a line. Built-in middleware gives both agents retries on provider errors and timeouts (`ModelRetryMiddleware`) and a cap on model calls (`ModelCallLimitMiddleware`), the claim agent retries backend network errors (`ToolRetryMiddleware`), and the queue agent is told of backend errors and carries on (`ToolErrorMiddleware`). The agents reach claims, documents and their instructions only through the backend's API. They use `deepseek/deepseek-v4.1-flash` with low reasoning effort by default, or the model in the environment variable `MODEL_NAME` if set, such as `openrouter/free`.
- `dashboard/`: React, Vite and TypeScript.
- `e2e/`: Playwright tests.
- `data/`: the business data the backend starts from. The agent never sees `data/evals/`, which holds the answer key.

Python 3.12 with uv, all in the root `pyproject.toml`. Node 26. The OpenRouter key is `OPENROUTER_API_KEY` in `.env`.
