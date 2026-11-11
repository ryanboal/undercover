import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { Claim, Customer, Handler, Policy } from "./api";
import { ApiError, claim, renderAt, stubApi } from "./testing";

const policy: Policy = {
  policy_id: "POL-2001",
  customer_id: "CUS-3001",
  plan: "premium",
  add_ons: ["electronics_plus"],
  purchased_on: "2026-04-22",
  sold_through: "Meridian Air checkout",
  trip: {
    destination: "Rome, Italy",
    departs_on: "2026-06-10",
    returns_on: "2026-06-18",
    trip_cost: 3100,
  },
  travelers: ["Maya Patel"],
  status: "active",
};

const customer: Customer = {
  customer_id: "CUS-3001",
  name: "Maya Patel",
  email: "maya.patel@example.com",
  phone: "+1 201 555 0143",
  date_of_birth: "1988-03-14",
  address: {
    street: "48 Wayne Street",
    city: "Jersey City",
    state: "NJ",
    zip: "07302",
  },
  customer_since: "2023-04-11",
  previous_claims: [
    {
      claim_id: "CLM-0412",
      filed_on: "2024-08-19",
      incident_date: "2024-08-09",
      claim_type: "baggage_delay",
      summary: "Checked bag arrived 30 hours late in Lisbon",
      outcome: "approved",
      amount_paid: 140,
    },
  ],
};

const handlers: Handler[] = [
  {
    handler_id: "HND-01",
    name: "Dana Whitfield",
    role: "Senior Claims Handler",
    email: "dana.whitfield@undercover.example",
    can_approve_over_limit: true,
  },
  {
    handler_id: "HND-09",
    name: "Sam Trainee",
    role: "Trainee",
    email: "sam@undercover.example",
    can_approve_over_limit: false,
  },
];

const approved = {
  decision: "approve",
  payout: 1150,
  reason: "The wrist fracture is covered under Emergency Medical.",
  policy_section: "Section 7, Emergency Medical",
  decided_at: "2026-11-11T03:10:09+00:00",
} as const;

// Answers in `more` replace the defaults, and keep any getters as getters.
function show(shown: Claim, more: Record<string, unknown> = {}) {
  const answers = {
    "GET /api/claims/CLM-1001": shown,
    "GET /api/policies/POL-2001": policy,
    "GET /api/customers/CUS-3001": customer,
    "GET /api/handlers": handlers,
  };
  Object.defineProperties(answers, Object.getOwnPropertyDescriptors(more));
  const fetchMock = stubApi(answers);
  renderAt("/claims/CLM-1001");
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the claim in full before the agent starts", async () => {
  show(claim);
  expect(
    await screen.findByText("My flight home from Rome was canceled."),
  ).toBeDefined();
  expect(screen.getByText("Airport hotel, one night")).toBeDefined();
  expect(screen.getByText("$245.00")).toBeDefined();
  expect(screen.getByText("$340.00")).toBeDefined();
  expect(
    screen.getByText("Hotel Aurelia Fiumicino. Total paid: $245.00."),
  ).toBeDefined();
  expect(
    screen.getByText("The agent has not started this claim."),
  ).toBeDefined();
  expect(await screen.findByText("Premium")).toBeDefined();
  expect(screen.getByText("Electronics plus")).toBeDefined();
  expect(
    screen.getByText("Rome, Italy, Jun 10, 2026 to Jun 18, 2026"),
  ).toBeDefined();
  expect(screen.getByText("$3,100.00")).toBeDefined();
  expect(
    await screen.findByText(/Checked bag arrived 30 hours late/),
  ).toBeDefined();
  expect(screen.queryByRole("button")).toBeNull();
});

it("says when the agent is working on a claim", async () => {
  show({ ...claim, status: "in_progress" });
  expect(
    await screen.findByText("The agent is working on this claim."),
  ).toBeDefined();
});

it("shows an approval the agent paid", async () => {
  show({
    ...claim,
    status: "decided",
    decision: { ...approved, payout: 340 },
    payment: {
      amount: 340,
      paid_by: "UnderCover Agent",
      paid_at: "2026-11-11T03:10:11+00:00",
    },
  });
  expect(await screen.findByText("Approve")).toBeDefined();
  expect(
    screen.getByText("The wrist fracture is covered under Emergency Medical."),
  ).toBeDefined();
  expect(screen.getByText("Section 7, Emergency Medical")).toBeDefined();
  expect(
    screen.getByText(/^Paid \$340\.00 by the UnderCover Agent on/),
  ).toBeDefined();
});

it("shows an approval whose payment is due", async () => {
  show({
    ...claim,
    status: "in_progress",
    decision: { ...approved, payout: 340 },
  });
  expect(await screen.findByText("Payment due.")).toBeDefined();
});

it("shows a decline and a referral with no payment", async () => {
  const declined = { ...approved, decision: "decline", payout: 0 } as const;
  show({ ...claim, status: "decided", decision: declined });
  expect(await screen.findByText("Decline")).toBeDefined();
  expect(screen.queryByText(/Paid|Payment/)).toBeNull();
  cleanup();
  show({
    ...claim,
    status: "decided",
    decision: { ...declined, decision: "refer" },
  });
  expect(await screen.findByText("Refer")).toBeDefined();
});

it("lets a handler sign off a payout over the limit", async () => {
  let current: Claim = {
    ...claim,
    status: "waiting_for_sign_off",
    decision: approved,
  };
  const fetchMock = show(current, {
    get "GET /api/claims/CLM-1001"() {
      return current;
    },
    get "POST /api/claims/CLM-1001/sign-off"() {
      current = {
        ...current,
        status: "decided",
        payment: {
          amount: 1150,
          paid_by: "Dana Whitfield",
          paid_at: "2026-11-11T04:00:00+00:00",
        },
      };
      return current;
    },
  });
  expect(
    await screen.findByText("Payment waits for a handler's sign-off."),
  ).toBeDefined();
  const button = screen.getByRole("button", {
    name: "Sign off and pay $1,150.00",
  });
  expect(button.hasAttribute("disabled")).toBe(true);
  expect(
    await screen.findByRole("option", { name: "Dana Whitfield" }),
  ).toBeDefined();
  expect(screen.queryByRole("option", { name: "Sam Trainee" })).toBeNull();
  fireEvent.change(screen.getByLabelText("Handler"), {
    target: { value: "HND-01" },
  });
  fireEvent.click(button);
  expect(
    await screen.findByText(
      /^Paid \$1,150\.00, signed off by Dana Whitfield on/,
    ),
  ).toBeDefined();
  expect(screen.queryByRole("button")).toBeNull();
  const signOff = fetchMock.mock.calls.find(([path]) =>
    path.endsWith("/sign-off"),
  );
  expect(signOff?.[1]?.body).toBe(JSON.stringify({ handler_id: "HND-01" }));
});

it("shows why a sign-off was refused", async () => {
  show(
    { ...claim, status: "waiting_for_sign_off", decision: approved },
    {
      "POST /api/claims/CLM-1001/sign-off": new ApiError(
        409,
        "Claim CLM-1001 is not waiting for sign-off",
      ),
    },
  );
  await screen.findByRole("option", { name: "Dana Whitfield" });
  fireEvent.change(screen.getByLabelText("Handler"), {
    target: { value: "HND-01" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Sign off and pay $1,150.00" }),
  );
  expect(
    await screen.findByText("Claim CLM-1001 is not waiting for sign-off"),
  ).toBeDefined();
});
