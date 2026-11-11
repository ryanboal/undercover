import { Link } from "react-router";
import type { ClaimSummary, Status } from "./api";
import { DecisionBadge, StatusBadge } from "./Badge";
import { date, money, statusLabels, words } from "./format";
import { usePolling } from "./usePolling";

const STATUSES: Status[] = [
  "waiting",
  "in_progress",
  "waiting_for_sign_off",
  "decided",
];

export function QueuePage() {
  const { data: claims, error } = usePolling<ClaimSummary[]>("/api/claims");

  return (
    <>
      <h1>Claims queue</h1>
      {error && <p className="error">The backend is not responding: {error}</p>}
      {claims && (
        <>
          <section className="counts" aria-label="Claims by status">
            {STATUSES.map((status) => (
              <div key={status} className={`count status-${status}`}>
                {statusLabels[status]}
                <strong>
                  {claims.filter((claim) => claim.status === status).length}
                </strong>
              </div>
            ))}
          </section>
          <section className="panel">
            <QueueTable claims={claims} />
          </section>
        </>
      )}
      {!claims && !error && <p className="muted">Loading the queue</p>}
    </>
  );
}

function QueueTable({ claims }: Readonly<{ claims: ClaimSummary[] }>) {
  return (
    <table>
      <thead>
        <tr>
          <th>Claim</th>
          <th>Customer</th>
          <th>Type</th>
          <th className="number">Claimed</th>
          <th>Submitted</th>
          <th>Status</th>
          <th>Decision</th>
          <th className="number">Payout</th>
        </tr>
      </thead>
      <tbody>
        {claims.map((claim) => (
          <tr key={claim.claim_id}>
            <td className="mono">
              <Link to={`/claims/${claim.claim_id}`}>{claim.claim_id}</Link>
            </td>
            <td>{claim.customer_name}</td>
            <td>{words(claim.claim_type)}</td>
            <td className="number money">{money(claim.amount_claimed)}</td>
            <td>{date(claim.submitted_on)}</td>
            <td>
              <StatusBadge status={claim.status} />
            </td>
            <td>
              {claim.decision && <DecisionBadge decision={claim.decision} />}
            </td>
            <td className="number money">
              {claim.payout !== null && money(claim.payout)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
