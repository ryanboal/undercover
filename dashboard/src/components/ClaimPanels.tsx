import type { Claim } from "../api";
import { date, label, money } from "../format";
import { Fact } from "./Fact";
import { Panel } from "./Panel";

export function ClaimDetails({ claim }: Readonly<{ claim: Claim }>) {
  return (
    <Panel title="Claim">
      <dl className="facts">
        <Fact name="Customer">{claim.customer_name}</Fact>
        <Fact name="Type">{label(claim.claim_type)}</Fact>
        <Fact name="Incident">
          {date(claim.incident_date)}, {claim.incident_location}
        </Fact>
        <Fact name="Submitted">{date(claim.submitted_on)}</Fact>
        <Fact name="Amount claimed" mono>
          {money(claim.amount_claimed)}
        </Fact>
      </dl>
      <h3>The customer's story</h3>
      <p className="story">{claim.story}</p>
    </Panel>
  );
}

export function ItemsPanel({ claim }: Readonly<{ claim: Claim }>) {
  const total = claim.items.reduce((sum, item) => sum + item.amount, 0);
  return (
    <Panel title="Items claimed">
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>Item</th>
              <th>Category</th>
              <th className="num">Amount</th>
            </tr>
          </thead>
          <tbody>
            {claim.items.map((item) => (
              <tr key={item.description}>
                <td>{item.description}</td>
                <td>{label(item.category)}</td>
                <td className="num mono">{money(item.amount)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" colSpan={2}>
                Total
              </th>
              <td className="num mono">{money(total)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </Panel>
  );
}

export function DocumentsPanel({ claim }: Readonly<{ claim: Claim }>) {
  return (
    <Panel title="Documents">
      {claim.documents.map((document) => (
        <article className="document" key={document.name}>
          <h3>{document.name}</h3>
          <p className="muted small">{label(document.type)}</p>
          <p>{document.content}</p>
        </article>
      ))}
    </Panel>
  );
}
