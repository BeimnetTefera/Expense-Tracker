import { useEffect, useRef, useState } from "react";
import { useAnimatedNumber } from "../hooks/useAnimatedNumber.js";
import { api } from "../lib/api.js";
import { etb, shortDate } from "../lib/format.js";

const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// Read straight from SQLite via GET /expenses (no LLM). Re-fetches whenever
// `reloadToken` changes. New rows flash, deleted rows fade out.
export default function ExpensesPanel({ sessionId, reloadToken }) {
  const [rows, setRows] = useState([]); // [{e: expense, state: "" | "new" | "gone"}]
  const [loaded, setLoaded] = useState(false);
  const firstLoad = useRef(true);

  useEffect(() => {
    let cancelled = false;
    api(`/expenses?session_id=${encodeURIComponent(sessionId)}`)
      .then((list) => {
        if (cancelled) return;
        list.sort((a, b) => b.spent_on.localeCompare(a.spent_on) || b.id - a.id); // newest first
        const isFirst = firstLoad.current;
        firstLoad.current = false;
        setLoaded(true);

        setRows((prev) => {
          const known = new Set(prev.map((r) => r.e.id));
          const wanted = new Set(list.map((e) => e.id));
          const next = list.map((e) => ({ e, state: isFirst || known.has(e.id) ? "" : "new" }));
          if (!reducedMotion()) {
            // Keep removed rows in place for their fade-out; onAnimationEnd drops them.
            prev.forEach((r, i) => {
              if (!wanted.has(r.e.id)) next.splice(Math.min(i, next.length), 0, { e: r.e, state: "gone" });
            });
          }
          return next;
        });
      })
      .catch(() => {
        /* the status pill already shows the problem */
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, reloadToken]);

  const live = rows.filter((r) => r.state !== "gone");
  const total = useAnimatedNumber(live.reduce((sum, r) => sum + r.e.amount_cents, 0));
  const dropRow = (id) => setRows((list) => list.filter((r) => !(r.e.id === id && r.state === "gone")));

  return (
    <section className="panel col-data" aria-label="Expenses">
      <div className="panel-head">
        <h2>Expenses</h2>
      </div>
      <div className="scroll data-body">
        <div className="grand-total">
          <span>{loaded ? etb(Math.round(total)) : "–"}</span> <small>ETB</small>
        </div>
        <div className="data-meta">
          {loaded ? `${live.length} row${live.length === 1 ? "" : "s"} · ` : ""}read from SQLite, no LLM
        </div>
        <div>
          {rows.map(({ e, state }) => (
            <div
              key={`${e.id}-${state === "gone" ? "gone" : "live"}`}
              className={`exp${state ? " " + state : ""}`}
              onAnimationEnd={state === "gone" ? () => dropRow(e.id) : undefined}
            >
              <div style={{ minWidth: 0 }}>
                <div>{e.description || e.category}</div>
                <div className="c">
                  {e.category} · {shortDate(e.spent_on)}
                </div>
              </div>
              <span className="a">{etb(e.amount_cents)}</span>
            </div>
          ))}
          {loaded && live.length === 0 && (
            <p className="empty">No expenses. Tell the agent about something you bought.</p>
          )}
        </div>
      </div>
    </section>
  );
}
