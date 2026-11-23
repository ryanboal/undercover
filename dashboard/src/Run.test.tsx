import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";
import type { Run, Step } from "./api";
import { Refusal, claim, history, policy, stubApi, summary } from "./testing";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const startedAt = "2026-11-22T17:06:16+00:00";

const running: Run = {
  run_id: "run-1",
  cap: 5,
  started_at: startedAt,
  finished_at: null,
  todos: [
    { task: "Work CLM-1001", status: "done" },
    { task: "Work CLM-1002", status: "in_progress" },
    { task: "Work CLM-1003", status: "to_do" },
    { task: "Work CLM-1004", status: "left_for_handler" },
  ],
  summary: null,
};

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

function showQueue(run: Run | null) {
  stubApi({ "GET /api/claims": [summary], "GET /api/runs/current": run });
  renderAt("/");
}

function todoPanel() {
  return screen.getByRole("region", { name: "Agent's to-do list" });
}

it("says when there are no runs yet", async () => {
  showQueue(null);
  expect(await screen.findByText(/No runs yet/)).toBeDefined();
});

it("shows the to-do list of a run in progress", async () => {
  showQueue(running);
  const items = await screen.findAllByRole("listitem");
  expect(items.map((item) => item.textContent)).toEqual([
    "DoneWork CLM-1001",
    "In progressWork CLM-1002",
    "To doWork CLM-1003",
    "Left for a handlerWork CLM-1004",
  ]);
  const panel = todoPanel();
  expect(within(panel).getByText(/^Run started at/).textContent).toMatch(
    /capped at 5 claims$/,
  );
  expect(within(panel).getByText("Done").className).toBe("chip todo-done");
  expect(within(panel).getByText("In progress").className).toBe(
    "chip todo-in_progress",
  );
  expect(within(panel).getByText("To do").className).toBe("chip todo-to_do");
  expect(within(panel).getByText("Left for a handler").className).toBe(
    "chip todo-left_for_handler",
  );
  expect(within(panel).queryByText("Summary")).toBeNull();
});

it("says when the agent is still planning", async () => {
  showQueue({ ...running, cap: 1, todos: [] });
  expect(
    await screen.findByText("The agent is planning its work."),
  ).toBeDefined();
  expect(screen.getByText(/capped at 1 claim$/)).toBeDefined();
});

it("shows a finished run and its summary", async () => {
  showQueue({
    ...running,
    finished_at: startedAt,
    summary: "Worked 4 claims.\nOne left for a handler.",
  });
  expect(await screen.findByText("Summary")).toBeDefined();
  expect(screen.getByText(/^Run finished at/)).toBeDefined();
  expect(screen.getByText(/Worked 4 claims\./).textContent).toBe(
    "Worked 4 claims.\nOne left for a handler.",
  );
});

it("shows an error when the run can't load", async () => {
  stubApi({
    "GET /api/claims": [summary],
    "GET /api/runs/current": new Refusal(500, "The backend is down"),
  });
  renderAt("/");
  expect((await screen.findByRole("alert")).textContent).toBe(
    "The backend is down",
  );
});

it("counts and marks claims that need a handler", async () => {
  stubApi({
    "GET /api/claims": [
      summary,
      { ...summary, claim_id: "CLM-1004", status: "needs_handler" },
    ],
    "GET /api/runs/current": null,
  });
  renderAt("/");
  expect(await screen.findByLabelText("Needs a handler: 1")).toBeDefined();
  const row = screen.getByRole("row", { name: /CLM-1004/ });
  expect(within(row).getByText("Needs a handler").className).toBe(
    "chip status-needs_handler",
  );
});

const readStep: Step = {
  step_id: 1,
  thread_id: "t-1",
  kind: "read",
  content:
    "Claims manual, section 9: Repeat claims\n\nBefore deciding any claim.",
  created_at: startedAt,
};

const errorStep: Step = {
  step_id: 2,
  thread_id: "t-1",
  kind: "error",
  content: "APITimeoutError: Request timed out.",
  created_at: startedAt,
};

function showClaim(
  status: "waiting" | "needs_handler",
  failedAttempts: number,
) {
  stubApi({
    "GET /api/claims/CLM-1002": {
      ...claim,
      status,
      failed_attempts: failedAttempts,
    },
    "GET /api/claims/CLM-1002/steps": [readStep, errorStep],
    "GET /api/policies/POL-2002": policy,
    "GET /api/customers/CUS-3002/claims": history,
    "GET /api/handlers": [],
  });
  renderAt("/claims/CLM-1002");
}

it("shows the sections the agent read, folded, and its failures", async () => {
  showClaim("waiting", 1);
  const title = await screen.findByText(
    "Claims manual, section 9: Repeat claims",
    { exact: false },
  );
  const read = title.closest("details");
  expect(read?.open).toBe(false);
  expect(read?.querySelector(".step-label")?.textContent).toBe("Read");
  expect(read?.querySelector("pre")?.textContent).toBe(
    "Before deciding any claim.",
  );
  const failure = screen.getByText(/APITimeoutError/);
  expect(failure.className).toBe("step-error-text");
  expect(failure.textContent).toBe(
    "Failed APITimeoutError: Request timed out.",
  );
  expect(
    screen.getByText(
      "The agent failed on this claim once, and it's back in the queue.",
    ),
  ).toBeDefined();
});

it("says when a claim is left for a handler", async () => {
  showClaim("needs_handler", 2);
  expect(
    await screen.findByText(
      "The agent failed on this claim twice, so it's left for a handler.",
    ),
  ).toBeDefined();
});
