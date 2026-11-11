import { act, cleanup, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ClaimSummary } from "./api";
import { renderAt, stubApi, summary } from "./testing";
import { POLL_MS } from "./useJson";

const queue: ClaimSummary[] = [
  summary,
  {
    ...summary,
    claim_id: "CLM-1003",
    customer_name: "Sofia Alvarez",
    claim_type: "emergency_medical",
    amount_claimed: 3800,
    status: "waiting_for_sign_off",
    decision: "approve",
    payout: 1150,
  },
  {
    ...summary,
    claim_id: "CLM-1004",
    status: "decided",
    decision: "decline",
    payout: 0,
  },
];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it("lists each claim with its status, decision and payout", async () => {
  stubApi({ "GET /api/claims": queue });
  renderAt("/");
  const row = (await screen.findByRole("link", { name: "CLM-1003" })).closest(
    "tr",
  );
  if (!row) throw new Error("CLM-1003 has no row");
  const cells = within(row);
  expect(cells.getByText("Sofia Alvarez")).toBeDefined();
  expect(cells.getByText("Emergency medical")).toBeDefined();
  expect(cells.getByText("$3,800.00")).toBeDefined();
  expect(cells.getByText("Jun 24, 2026")).toBeDefined();
  expect(cells.getByText("Waiting for sign-off")).toBeDefined();
  expect(cells.getByText("Approve")).toBeDefined();
  expect(cells.getByText("$1,150.00")).toBeDefined();
  expect(
    screen.getByRole("link", { name: "CLM-1001" }).getAttribute("href"),
  ).toBe("/claims/CLM-1001");
});

it("counts the claims in each status", async () => {
  stubApi({ "GET /api/claims": queue });
  renderAt("/");
  const counts = await screen.findByRole("region", {
    name: "Claims by status",
  });
  expect(counts.textContent).toBe(
    "Waiting1In progress0Waiting for sign-off1Decided1",
  );
});

it("picks up changes on the next poll", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  let status: ClaimSummary["status"] = "waiting";
  stubApi({
    get "GET /api/claims"() {
      return [{ ...summary, status }];
    },
  });
  renderAt("/");
  expect(
    await screen.findByText("Waiting", { selector: ".badge" }),
  ).toBeDefined();
  status = "in_progress";
  await act(() => vi.advanceTimersByTimeAsync(POLL_MS));
  expect(screen.getByText("In progress", { selector: ".badge" })).toBeDefined();
});

it("says when the backend is not responding", async () => {
  stubApi({});
  renderAt("/");
  expect(
    await screen.findByText("The backend is not responding: Failed to fetch"),
  ).toBeDefined();
});
