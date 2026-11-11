import type { Step } from "./api";
import { clock } from "./format";
import { useJson } from "./useJson";

const REFUSED = "Refused: ";

export function Steps({ claimId }: Readonly<{ claimId: string }>) {
  const { data: steps = [] } = useJson<Step[]>(
    `/api/claims/${claimId}/steps`,
    true,
  );
  return (
    <section className="panel">
      <h2>The agent's steps</h2>
      {steps.length === 0 ? (
        <p className="muted">No steps yet.</p>
      ) : (
        <ol className="steps">
          {steps.map((step) => (
            <li key={step.step_id} className={`step step-${step.kind}`}>
              <time className="mono muted" dateTime={step.at}>
                {clock(step.at)}
              </time>
              <StepText step={step} />
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function StepText({ step }: Readonly<{ step: Step }>) {
  if (step.kind === "message") return <p>{step.text}</p>;
  if (step.kind === "tool_call") return <p className="mono">{step.text}</p>;
  const [tool = "", ...rest] = step.text.split(": ");
  const result = rest.join(": ");
  if (result.startsWith(REFUSED)) {
    return (
      <p className="refused">
        <span className="mono">{tool}</span> refused:{" "}
        {result.slice(REFUSED.length)}
      </p>
    );
  }
  return (
    <details>
      <summary>
        Result of <span className="mono">{tool}</span>
      </summary>
      <pre>{result}</pre>
    </details>
  );
}
