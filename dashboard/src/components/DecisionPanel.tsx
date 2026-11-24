import type { Claim } from "../api";
import { money, time } from "../format";
import { DecisionChip } from "./Chips";
import { SignOffForm } from "./SignOffForm";
import { Panel } from "./Panel";

export function DecisionPanel({
  claim,
  onSignedOff,
}: Readonly<{ claim: Claim; onSignedOff: () => void }>) {
  const { decision, payment } = claim;

  return (
    <Panel title="Decision">
      {!decision && <p className="muted">{progress(claim)}</p>}
      {decision && (
        <>
          <div className="decision-line">
            <DecisionChip decision={decision.decision} />
            {decision.decision === "approve" && (
              <span className="payout mono">{money(decision.payout)}</span>
            )}
          </div>
          <p className="section-ref">{decision.section}</p>
          <p className="reason">{decision.reason}</p>
          <p className="small muted">Decided at {time(decision.decided_at)}</p>
        </>
      )}
      {payment && (
        <p className="payment">
          Paid <span className="mono">{money(payment.amount)}</span>
          {payment.signed_off_by && `, signed off by ${payment.signed_off_by}`}
        </p>
      )}
      {decision?.decision === "approve" &&
        !payment &&
        claim.status === "decided" && <p className="payment">Not paid yet</p>}
      {decision && claim.status === "waiting_for_sign_off" && (
        <div className="sign-off">
          <p>
            The payment of{" "}
            <span className="mono">{money(decision.payout)}</span> is over the
            approval limit and waits for a handler's sign-off.
          </p>
          <SignOffForm claimId={claim.claim_id} onSignedOff={onSignedOff} />
        </div>
      )}
    </Panel>
  );
}

function progress(claim: Claim): string {
  if (claim.status === "in_progress")
    return "The agent is working on this claim.";
  if (claim.status === "needs_handler")
    return "The agent failed on this claim twice, so it's left for a handler.";
  if (claim.failed_attempts > 0)
    return "The agent failed on this claim once, and it's back in the queue.";
  return "The agent hasn't started on this claim.";
}
