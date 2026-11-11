export type Status =
  "waiting" | "in_progress" | "waiting_for_sign_off" | "decided";
export type DecisionKind = "approve" | "decline" | "refer";

export interface ClaimSummary {
  claim_id: string;
  customer_id: string;
  customer_name: string;
  claim_type: string;
  summary: string;
  amount_claimed: number;
  submitted_on: string;
  status: Status;
  decision: DecisionKind | null;
  payout: number | null;
}

export interface Item {
  description: string;
  category: string;
  amount: number;
}

export interface ClaimDocument {
  name: string;
  type: string;
  content: string;
}

export interface Decision {
  decision: DecisionKind;
  payout: number;
  reason: string;
  policy_section: string;
  decided_at: string;
}

export interface Payment {
  amount: number;
  paid_by: string;
  paid_at: string;
}

export interface Claim {
  claim_id: string;
  policy_id: string;
  customer_id: string;
  claim_type: string;
  submitted_on: string;
  incident_date: string;
  incident_location: string;
  summary: string;
  story: string;
  items: Item[];
  amount_claimed: number;
  documents: ClaimDocument[];
  status: Status;
  decision: Decision | null;
  payment: Payment | null;
}

export async function getJson<T>(path: string): Promise<T> {
  return answer<T>(await fetch(path));
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  return answer<T>(
    await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

async function answer<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const { detail } = (await response.json()) as { detail: string };
    throw new Error(detail);
  }
  return (await response.json()) as T;
}
