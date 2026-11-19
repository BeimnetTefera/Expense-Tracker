import { useEffect, useId, useState } from "react";
import { explain } from "../lib/explain.js";
import { fmtMs, highlightJson, markdownToHtml } from "../lib/format.js";

// Live "Working… 1.2 s" line while we wait, like ChatGPT's "Thinking".
function LiveClock({ startedAt }) {
  const [now, setNow] = useState(performance.now());
  useEffect(() => {
    const t = setInterval(() => setNow(performance.now()), 100);
    return () => clearInterval(t);
  }, []);
  return <span className="clock">{((now - startedAt) / 1000).toFixed(1)} s</span>;
}

function Step({ s, maxMs, open }) {
  const width = Math.max(1, Math.round(((s.ms || 0) / maxMs) * 100));
  const timing = (
    <div className="timing">
      <div className="bar">
        {/* width animates from 0 when the trace opens (CSS transition on .bar i) */}
        <i style={{ width: open ? `${width}%` : 0 }} />
      </div>
      <span className="ms">{fmtMs(s.ms || 0)}</span>
    </div>
  );
  const why = <div className={`why${s.ok === false ? " err" : ""}`}>{explain(s)}</div>;

  if (s.kind === "llm") {
    return (
      <div className="step llm">
        <div>
          <div className="k">LLM · step {s.step}</div>
          {why}
        </div>
        {timing}
      </div>
    );
  }
  return (
    <div className={`step ${s.kind}${s.kind === "tool" ? " sub" : ""}`}>
      <div style={{ minWidth: 0 }}>
        <div className="k">{s.kind === "approval" ? "you · no LLM" : "tool"}</div>
        <div className="name">
          {s.tool} {s.ok ? <span className="ok">✓</span> : <span className="bad">✗ failed</span>}
        </div>
        {why}
        {s.ok === false && s.error && <div className="why err">{s.error}</div>}
        <code className="args" dangerouslySetInnerHTML={{ __html: highlightJson(s.args) }} />
      </div>
      {timing}
    </div>
  );
}

// Clickable "▸ Worked for 1.4 s · used x, y" + the collapsible steps.
function Trace({ trace, waiting }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const totalMs = trace.reduce((sum, s) => sum + (s.ms || 0), 0);
  const maxMs = Math.max(1, ...trace.map((s) => s.ms || 0));
  const tools = [...new Set(trace.filter((s) => s.kind !== "llm").map((s) => s.tool))];

  return (
    <>
      <button type="button" className="worked" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
        <span className="chev" aria-hidden="true">▸</span>
        <span>
          Worked for {fmtMs(totalMs)}
          {tools.length ? (
            <>
              {" · used "}
              {tools.map((n, i) => (
                <span key={n}>
                  {i > 0 && ", "}
                  <span className="tools">{n}</span>
                </span>
              ))}
            </>
          ) : (
            " · answered without tools"
          )}
        </span>
      </button>
      <div className={`trace${open ? " open" : ""}`} id={id}>
        <div>
          <div className="steps">
            {trace.map((s, i) => (
              <Step key={i} s={s} maxMs={maxMs} open={open} />
            ))}
            {waiting && (
              <div className="step you">
                <div>
                  <div className="k">you</div>
                  <div className="why">
                    Waiting for your decision. <span className="mono">confirm_delete</span> isn't on the LLM's tool
                    list, so only your click can delete.
                  </div>
                </div>
              </div>
            )}
            <div className="total">
              {trace.length} step{trace.length === 1 ? "" : "s"} · {fmtMs(totalMs)} total
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

// One agent turn: [Worked for… line] + [hidden steps] + [answer bubble].
export default function Reply({ item }) {
  if (item.status === "working") {
    return (
      <div className="reply">
        <div className="worked live" aria-live="polite">
          <span className="spinner" aria-hidden="true" />
          <span className="label">
            {item.label}… <LiveClock startedAt={item.startedAt} />
          </span>
        </div>
      </div>
    );
  }
  if (item.status === "failed") {
    return (
      <div className="reply">
        <div className="msg err">{item.error}</div>
      </div>
    );
  }
  return (
    <div className="reply">
      <Trace trace={item.trace} waiting={item.waiting} />
      {item.markdown != null ? (
        <div className="msg" dangerouslySetInnerHTML={{ __html: markdownToHtml(item.markdown) }} />
      ) : (
        <div className="msg note">{item.note}</div>
      )}
    </div>
  );
}
