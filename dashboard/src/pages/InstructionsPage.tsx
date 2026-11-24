import { api } from "../api";
import { Message } from "../components/Message";
import { useLoad } from "../useLoad";
import { Panel } from "../components/Panel";

export function InstructionsPage() {
  const { data, error } = useLoad(api.getInstructions);

  return (
    <>
      <h1>Agent instructions</h1>
      <p className="lead">
        What the agent reads before it starts: its instructions for running the
        queue, then for working each claim, which end with the contents of the
        policy wording and the claims manual. This page is read only.
      </p>
      {data ? (
        <>
          <Panel title="Running the queue">
            <pre className="instructions">{data.queue}</pre>
          </Panel>
          <Panel title="Working a claim">
            <pre className="instructions">{data.claim}</pre>
          </Panel>
        </>
      ) : (
        <section className="panel">
          <Message error={error} />
        </section>
      )}
    </>
  );
}
