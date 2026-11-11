import { Link, useParams } from "react-router";
import type { Claim } from "./api";
import { StatusBadge } from "./Badge";
import { CustomerPanel, DecisionPanel, PolicyPanel } from "./ClaimPanels";
import { date, money, words } from "./format";
import { SignOff } from "./SignOff";
import { Steps } from "./Steps";
import { useJson } from "./useJson";

export function ClaimPage() {
  const { claimId = "" } = useParams();
  const {
    data: claim,
    error,
    refresh,
  } = useJson<Claim>(`/api/claims/${claimId}`, true);

  if (!claim) {
    return <p className={error ? "error" : "muted"}>{error ?? "Loading"}</p>;
  }
  return (
    <>
      <Link to="/" className="back">
        Back to the queue
      </Link>
      <header className="claim-header">
        <h1>
          <span className="mono">{claim.claim_id}</span> {claim.summary}
        </h1>
        <p className="muted">
          <StatusBadge status={claim.status} /> {words(claim.claim_type)} in{" "}
          {claim.incident_location} on {date(claim.incident_date)}, submitted{" "}
          {date(claim.submitted_on)}
        </p>
      </header>
      <div className="claim-layout">
        <div className="column">
          <ClaimDetails claim={claim} />
        </div>
        <div className="column">
          <DecisionPanel claim={claim} />
          {claim.status === "waiting_for_sign_off" && (
            <SignOff claim={claim} onSignedOff={refresh} />
          )}
          <Steps claimId={claim.claim_id} />
          <PolicyPanel policyId={claim.policy_id} />
          <CustomerPanel customerId={claim.customer_id} />
        </div>
      </div>
    </>
  );
}

function ClaimDetails({ claim }: Readonly<{ claim: Claim }>) {
  return (
    <>
      <section className="panel">
        <h2>The customer's story</h2>
        <blockquote className="story">{claim.story}</blockquote>
      </section>
      <section className="panel">
        <h2>What they are claiming</h2>
        <table>
          <thead>
            <tr>
              <th>Item</th>
              <th>Category</th>
              <th className="number">Amount</th>
            </tr>
          </thead>
          <tbody>
            {claim.items.map((item) => (
              <tr key={item.description}>
                <td>{item.description}</td>
                <td>{words(item.category)}</td>
                <td className="number money">{money(item.amount)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th colSpan={2}>Total claimed</th>
              <td className="number money">{money(claim.amount_claimed)}</td>
            </tr>
          </tfoot>
        </table>
      </section>
      <section className="panel">
        <h2>Documents</h2>
        {claim.documents.map((document) => (
          <article key={document.name} className="document">
            <h3>
              {document.name}{" "}
              <span className="muted">{words(document.type)}</span>
            </h3>
            <p>{document.content}</p>
          </article>
        ))}
      </section>
    </>
  );
}
