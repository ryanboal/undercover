import type { DecisionKind, Status } from "./api";
import { decisionLabels, statusLabels } from "./format";

export function StatusBadge({ status }: Readonly<{ status: Status }>) {
  return (
    <span className={`badge status-${status}`}>{statusLabels[status]}</span>
  );
}

export function DecisionBadge({
  decision,
}: Readonly<{ decision: DecisionKind }>) {
  return (
    <span className={`badge decision-${decision}`}>
      {decisionLabels[decision]}
    </span>
  );
}
