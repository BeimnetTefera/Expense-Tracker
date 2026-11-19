import { etb, shortDate } from "../lib/format.js";

// The human-in-the-loop step: the agent only PROPOSED this delete.
export default function ApprovalCard({ pending, onDecide }) {
  return (
    <div className="approval" role="group" aria-label="Approve deletion">
      <div className="t">Approve deletion?</div>
      <div className="sub">The agent proposed this. Only you can carry it out.</div>
      {pending.expenses.map((e) => (
        <div className="item" key={e.id}>
          <span>
            {e.description || e.category} · {shortDate(e.spent_on)}
          </span>
          <span className="mono">{etb(e.amount_cents)} ETB</span>
        </div>
      ))}
      <div className="row">
        <button type="button" className="btn-delete" onClick={() => onDecide("approve")}>
          Delete
        </button>
        <button type="button" className="btn-keep" onClick={() => onDecide("cancel")}>
          Keep it
        </button>
      </div>
    </div>
  );
}
