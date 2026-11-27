# Code standards

1. Keep it simple, do not overcomplicate.
2. Comments only when necessary.
3. Be concise: a short README and no emojis.
4. IMPORTANT: avoid overly defensive code. Handle exceptions only when necessary.
5. Use uv: ALWAYS `uv run`, NEVER `python3`.
6. TypeScript: strict mode, never `any`.
7. Calls to another service live in one module, with its address in one place and one function per operation. Nothing else builds a URL or sends a request: `agent/api.py` and `dashboard/src/api.ts`.
8. Each module has one job, and imports only from the layers below it. No module reaches into a main module. The agent's layers are `api`, `context`, `rules`, `tools`, `steps`, `harness` and `__main__`.
9. Keep the harness (`agent/harness.py`) and the tools (`agent/tools.py`) apart from the business rules (`agent/rules.py`). Tools take state from `ToolRuntime`, and the model never supplies what the code knows.
10. Functions do one thing, in 40 lines or fewer in the agent. Signal problems with exceptions, never by matching text.
11. Instructions give an agent a goal, what to rely on and its boundaries. They are never a numbered script: if the steps are fixed, write code.
12. Don't repeat markup or row mapping. Extract it the second time.
13. A tool always gives the model something to read. Return text or a record, never a bare list, and say so in a sentence when nothing is found: an empty reply looks like a failed call, and the model asks again.

`agent/tests/test_structure.py` enforces 7 to 11 for the agent as far as a test can, and ESLint enforces 7 for the dashboard.
