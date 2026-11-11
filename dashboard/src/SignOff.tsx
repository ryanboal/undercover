import { useState, type SubmitEvent } from "react";
import { postJson, type Claim, type Handler } from "./api";
import { money } from "./format";
import { useJson } from "./useJson";

export function SignOff({
  claim,
  onSignedOff,
}: Readonly<{ claim: Claim; onSignedOff: () => void }>) {
  const { data: handlers = [] } = useJson<Handler[]>("/api/handlers", false);
  const [handlerId, setHandlerId] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string>();
  const payout = money(claim.decision?.payout ?? 0);

  const signOff = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSending(true);
    setError(undefined);
    postJson<Claim>(`/api/claims/${claim.claim_id}/sign-off`, {
      handler_id: handlerId,
    })
      .then(onSignedOff, (reason: unknown) => {
        setError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => {
        setSending(false);
      });
  };

  return (
    <section className="panel sign-off">
      <h2>Sign off the payment</h2>
      <p>
        The agent approved {payout}. That is over the agent's approval limit, so
        it waits for a handler's sign-off before it is paid.
      </p>
      <form onSubmit={signOff}>
        <label>
          Handler
          <select
            value={handlerId}
            onChange={(event) => {
              setHandlerId(event.target.value);
            }}
          >
            <option value="">Choose a handler</option>
            {handlers
              .filter((handler) => handler.can_approve_over_limit)
              .map((handler) => (
                <option key={handler.handler_id} value={handler.handler_id}>
                  {handler.name}
                </option>
              ))}
          </select>
        </label>
        <button type="submit" disabled={!handlerId || sending}>
          Sign off and pay {payout}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
    </section>
  );
}
