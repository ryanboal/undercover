import { useParams } from "react-router";
import type { Claim } from "./api";
import { StatusBadge } from "./Badge";
import { usePolling } from "./usePolling";

export function ClaimPage() {
  const { claimId = "" } = useParams();
  const { data: claim, error } = usePolling<Claim>(`/api/claims/${claimId}`);

  if (error && !claim) return <p className="error">{error}</p>;
  if (!claim) return <p className="muted">Loading {claimId}</p>;
  return (
    <>
      <h1>
        <span className="mono">{claim.claim_id}</span> {claim.summary}
      </h1>
      <StatusBadge status={claim.status} />
    </>
  );
}
