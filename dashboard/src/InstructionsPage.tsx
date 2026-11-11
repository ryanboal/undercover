import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useJson } from "./useJson";

export function InstructionsPage() {
  const { data, error } = useJson<{ instructions: string }>(
    "/api/instructions",
    false,
  );
  return (
    <>
      <h1>The agent's instructions</h1>
      <p className="muted">
        What the UnderCover Agent reads before every claim: its instructions,
        then the policy wording it decides by. This page is read only.
      </p>
      {error && <p className="error">{error}</p>}
      {data && (
        <article className="panel markdown">
          <Markdown remarkPlugins={[remarkGfm]}>{data.instructions}</Markdown>
        </article>
      )}
    </>
  );
}
