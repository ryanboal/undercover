import type { Claim, Customer, Payment, Policy } from "./api";
import { DecisionBadge } from "./Badge";
import { AGENT, date, dateTime, money, words } from "./format";
import { useJson } from "./useJson";

export function DecisionPanel({ claim }: Readonly<{ claim: Claim }>) {
  const { decision } = claim;
  if (!decision) {
    return (
      <section className="panel">
        <h2>Decision</h2>
        <p className="muted">
          {claim.status === "waiting"
            ? "The agent has not started this claim."
            : "The agent is working on this claim."}
        </p>
      </section>
    );
  }
  return (
    <section className="panel decision">
      <h2>Decision</h2>
      <p className="decision-line">
        <DecisionBadge decision={decision.decision} />
        {decision.decision === "approve" && (
          <span className="money payout">{money(decision.payout)}</span>
        )}
      </p>
      <p>{decision.reason}</p>
      <dl>
        <dt>Policy section</dt>
        <dd>{decision.policy_section}</dd>
        <dt>Decided</dt>
        <dd>{dateTime(decision.decided_at)}</dd>
      </dl>
      {decision.decision === "approve" && <PaymentLine claim={claim} />}
    </section>
  );
}

function PaymentLine({ claim }: Readonly<{ claim: Claim }>) {
  if (claim.payment) return <p className="paid">{paidText(claim.payment)}</p>;
  if (claim.status === "waiting_for_sign_off") {
    return <p className="pending">Payment waits for a handler's sign-off.</p>;
  }
  return <p className="pending">Payment due.</p>;
}

function paidText(payment: Payment): string {
  const when = dateTime(payment.paid_at);
  if (payment.paid_by === AGENT) {
    return `Paid ${money(payment.amount)} by the ${AGENT} on ${when}.`;
  }
  return `Paid ${money(payment.amount)}, signed off by ${payment.paid_by} on ${when}.`;
}

export function PolicyPanel({ policyId }: Readonly<{ policyId: string }>) {
  const { data: policy } = useJson<Policy>(`/api/policies/${policyId}`, false);
  if (!policy) return null;
  return (
    <section className="panel">
      <h2>
        Policy <span className="mono muted">{policy.policy_id}</span>
      </h2>
      <dl>
        <dt>Plan</dt>
        <dd>{words(policy.plan)}</dd>
        <dt>Add-ons</dt>
        <dd>{policy.add_ons.map(words).join(", ") || "None"}</dd>
        <dt>Bought</dt>
        <dd>
          {date(policy.purchased_on)}, through {policy.sold_through}
        </dd>
        <dt>Trip</dt>
        <dd>
          {policy.trip.destination}, {date(policy.trip.departs_on)} to{" "}
          {date(policy.trip.returns_on)}
        </dd>
        <dt>Trip cost</dt>
        <dd className="money">{money(policy.trip.trip_cost)}</dd>
        <dt>Travelers</dt>
        <dd>{policy.travelers.join(", ")}</dd>
      </dl>
    </section>
  );
}

export function CustomerPanel({
  customerId,
}: Readonly<{ customerId: string }>) {
  const { data: customer } = useJson<Customer>(
    `/api/customers/${customerId}`,
    false,
  );
  if (!customer) return null;
  return (
    <section className="panel">
      <h2>
        {customer.name}{" "}
        <span className="mono muted">{customer.customer_id}</span>
      </h2>
      <p className="muted">
        {customer.email}, {customer.phone}. A customer since{" "}
        {date(customer.customer_since)}.
      </p>
      <h3>Earlier claims</h3>
      {customer.previous_claims.length === 0 ? (
        <p className="muted">None</p>
      ) : (
        <ul className="history">
          {customer.previous_claims.map((previous) => (
            <li key={previous.claim_id}>
              <span className="mono">{previous.claim_id}</span>,{" "}
              {date(previous.filed_on)}: {previous.summary}.{" "}
              {words(previous.outcome)}, paid{" "}
              <span className="money">{money(previous.amount_paid)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
