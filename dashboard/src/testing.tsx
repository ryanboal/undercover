import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";
import type { Claim, ClaimSummary } from "./api";
import { App } from "./App";

export class ApiError {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {}
}

// Stubs fetch with answers keyed by "GET /api/..." or "POST /api/...". A
// getter in place of a value gives a fresh answer on every request.
export function stubApi(answers: Record<string, unknown>) {
  const fetchMock = vi.fn((input: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${input}`;
    if (!(key in answers)) {
      return Promise.reject(new TypeError("Failed to fetch"));
    }
    const answer = answers[key];
    const status = answer instanceof ApiError ? answer.status : 200;
    const body =
      answer instanceof ApiError ? { detail: answer.detail } : answer;
    return Promise.resolve(new Response(JSON.stringify(body), { status }));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

export const summary: ClaimSummary = {
  claim_id: "CLM-1001",
  customer_id: "CUS-3001",
  customer_name: "Maya Patel",
  claim_type: "trip_delay",
  summary: "Flight home canceled by the airline",
  amount_claimed: 420,
  submitted_on: "2026-06-24",
  status: "waiting",
  decision: null,
  payout: null,
};

export const claim: Claim = {
  claim_id: "CLM-1001",
  policy_id: "POL-2001",
  customer_id: "CUS-3001",
  claim_type: "trip_delay",
  submitted_on: "2026-06-24",
  incident_date: "2026-06-18",
  incident_location: "Rome, Italy",
  summary: "Flight home canceled by the airline",
  story: "My flight home from Rome was canceled.",
  items: [
    {
      description: "Airport hotel, one night",
      category: "accommodation",
      amount: 245,
    },
    { description: "Dinner and breakfast", category: "meals", amount: 95 },
  ],
  amount_claimed: 340,
  documents: [
    {
      name: "Hotel receipt",
      type: "receipt",
      content: "Hotel Aurelia Fiumicino. Total paid: $245.00.",
    },
  ],
  status: "waiting",
  decision: null,
  payment: null,
};
