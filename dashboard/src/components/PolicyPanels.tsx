import { useCallback } from "react";
import { api } from "../api";
import { addOnName, date, label, money } from "../format";
import { useLoad } from "../useLoad";
import { Message } from "./Message";
import { Panel } from "./Panel";
import { Fact } from "./Fact";

export function PolicyPanel({ policyId }: Readonly<{ policyId: string }>) {
  const load = useCallback(() => api.getPolicy(policyId), [policyId]);
  const { data: policy, error } = useLoad(load);

  return (
    <Panel title="Policy">
      {policy ? (
        <dl className="facts">
          <Fact name="Policy" mono>
            {policy.policy_id}
          </Fact>
          <Fact name="Plan">{label(policy.plan)}</Fact>
          <Fact name="Add-ons">
            {policy.add_ons.length > 0
              ? policy.add_ons.map(addOnName).join(", ")
              : "None"}
          </Fact>
          <Fact name="Purchased">{date(policy.purchased_on)}</Fact>
          <Fact name="Sold through">{policy.sold_through}</Fact>
          <Fact name="Trip">
            {policy.trip.destination}, {date(policy.trip.departs_on)} to{" "}
            {date(policy.trip.returns_on)}
          </Fact>
          <Fact name="Trip cost" mono>
            {money(policy.trip.trip_cost)}
          </Fact>
          <Fact name="Travelers">{policy.travelers.join(", ")}</Fact>
        </dl>
      ) : (
        <Message error={error} />
      )}
    </Panel>
  );
}

export function HistoryPanel({ customerId }: Readonly<{ customerId: string }>) {
  const load = useCallback(() => api.getClaimHistory(customerId), [customerId]);
  const { data: history, error } = useLoad(load);

  return (
    <Panel title="Earlier claims">
      {!history && <Message error={error} />}
      {history?.length === 0 && <p className="muted">No earlier claims</p>}
      {history && history.length > 0 && (
        <ul className="history">
          {history.map((claim) => (
            <li key={claim.claim_id}>
              <p className="small muted">
                <span className="mono">{claim.claim_id}</span>,{" "}
                {label(claim.claim_type)}, filed {date(claim.filed_on)}
              </p>
              <p>{claim.summary}</p>
              <p className="small">
                {label(claim.outcome)}, paid{" "}
                <span className="mono">{money(claim.amount_paid)}</span>
              </p>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
