import { useCallback } from "react";
import { useParams } from "react-router";
import { ApiError, api } from "../api";
import { StatusChip } from "../components/Chips";
import { DecisionPanel } from "../components/DecisionPanel";
import { Message } from "../components/Message";
import { HistoryPanel, PolicyPanel } from "../components/PolicyPanels";
import { StepList } from "../components/StepList";
import { REFRESH_MS, useLoad } from "../useLoad";
import {
  ClaimDetails,
  DocumentsPanel,
  ItemsPanel,
} from "../components/ClaimPanels";

export function ClaimPage() {
  const { claimId = "" } = useParams();
  const load = useCallback(() => api.getClaim(claimId), [claimId]);
  const { data: claim, error, reload } = useLoad(load, REFRESH_MS);

  if (!claim) {
    if (error instanceof ApiError && error.status === 404)
      return <p className="message">Claim not found</p>;
    return <Message error={error} />;
  }

  return (
    <>
      <div className="claim-heading">
        <p className="mono muted">{claim.claim_id}</p>
        <h1>{claim.summary}</h1>
        <StatusChip status={claim.status} />
      </div>
      <div className="claim-layout">
        <div className="column">
          <ClaimDetails claim={claim} />
          <ItemsPanel claim={claim} />
          <DocumentsPanel claim={claim} />
        </div>
        <div className="column">
          <DecisionPanel claim={claim} onSignedOff={reload} />
          <StepList claimId={claim.claim_id} />
          <PolicyPanel policyId={claim.policy_id} />
          <HistoryPanel customerId={claim.customer_id} />
        </div>
      </div>
    </>
  );
}
