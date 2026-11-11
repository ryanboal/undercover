import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { Step } from "./api";
import { Steps } from "./Steps";
import { stubApi } from "./testing";
import { POLL_MS } from "./useJson";

const at = "2026-11-11T03:10:09+00:00";
const steps: Step[] = [
  { step_id: 1, at, kind: "tool_call", text: 'get_claim(claim_id="CLM-1003")' },
  {
    step_id: 2,
    at,
    kind: "tool_result",
    text: 'get_claim: {"claim_id": "CLM-1003", "note": "a: b"}',
  },
  {
    step_id: 3,
    at,
    kind: "tool_result",
    text: "pay_claim: Refused: A payout over $1,000.00 needs a handler's sign-off",
  },
  { step_id: 4, at, kind: "message", text: "Approved; it waits for sign-off." },
];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it("shows each kind of step and folds the results away", async () => {
  stubApi({ "GET /api/claims/CLM-1003/steps": steps });
  render(<Steps claimId="CLM-1003" />);
  expect(
    await screen.findByText('get_claim(claim_id="CLM-1003")'),
  ).toBeDefined();
  const result = screen.getByText('{"claim_id": "CLM-1003", "note": "a: b"}');
  expect(result.closest("details")?.open).toBe(false);
  expect(screen.getByText("Result of", { exact: false }).textContent).toBe(
    "Result of get_claim",
  );
  const refused = screen.getByText(/needs a handler's sign-off/);
  expect(refused.textContent).toBe(
    "pay_claim refused: A payout over $1,000.00 needs a handler's sign-off",
  );
  expect(refused.closest("details")).toBeNull();
  expect(screen.getByText("Approved; it waits for sign-off.")).toBeDefined();
  expect(screen.getAllByRole("listitem")).toHaveLength(4);
});

it("says when there are no steps yet", async () => {
  stubApi({ "GET /api/claims/CLM-1003/steps": [] });
  render(<Steps claimId="CLM-1003" />);
  expect(await screen.findByText("No steps yet.")).toBeDefined();
});

it("shows new steps as the agent works", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  let shown = steps.slice(0, 1);
  stubApi({
    get "GET /api/claims/CLM-1003/steps"() {
      return shown;
    },
  });
  render(<Steps claimId="CLM-1003" />);
  expect(await screen.findAllByRole("listitem")).toHaveLength(1);
  shown = steps;
  await act(() => vi.advanceTimersByTimeAsync(POLL_MS));
  expect(screen.getAllByRole("listitem")).toHaveLength(4);
});
