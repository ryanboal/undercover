import { api } from "../api";
import { time } from "../format";
import { REFRESH_MS, useLoad } from "../useLoad";
import { TodoChip } from "./Chips";
import { Message } from "./Message";

export function TodoPanel() {
  const { data: run, error } = useLoad(api.getCurrentRun, REFRESH_MS);

  return (
    <section className="panel todo-panel" aria-labelledby="todo-title">
      <h2 id="todo-title">Agent's to-do list</h2>
      {run === undefined && <Message error={error} />}
      {run === null && (
        <p className="muted">
          No runs yet. The list appears here when the agent starts a run.
        </p>
      )}
      {run && (
        <>
          <p className="small muted">
            {run.finished_at
              ? `Run finished at ${time(run.finished_at)}`
              : `Run started at ${time(run.started_at)}`}
            , capped at {run.cap} {run.cap === 1 ? "claim" : "claims"}
          </p>
          {run.todos.length === 0 ? (
            <p className="muted">The agent is planning its work.</p>
          ) : (
            <ol className="todos">
              {run.todos.map((todo) => (
                <li key={todo.task} className="todo">
                  <TodoChip status={todo.status} />
                  <span>{todo.task}</span>
                </li>
              ))}
            </ol>
          )}
          {run.summary && (
            <div className="run-summary">
              <h3>Summary</h3>
              <p>{run.summary}</p>
            </div>
          )}
        </>
      )}
    </section>
  );
}
