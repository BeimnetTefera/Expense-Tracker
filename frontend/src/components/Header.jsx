import { useSecondsUntil } from "../hooks/useAllowance.js";

function StatusPill({ connection, allowance }) {
  const secs = useSecondsUntil(allowance?.remaining === 0 ? allowance.freesAt : null);

  let kind = "wait";
  let text = "connecting…";
  if (connection === "down") {
    kind = "bad";
    text = "can't reach the server";
  } else if (connection === "waking") {
    text = "waking up the server… (~30s)";
  } else if (connection === "ok" && allowance) {
    kind = allowance.remaining > 0 ? "ok" : "wait";
    text =
      allowance.remaining > 0
        ? `api online · ${allowance.remaining}/${allowance.limit} msgs left`
        : `limit reached · next msg in ${secs} s`;
  }

  return (
    <span className="pill" role="status">
      <span className={`dot ${kind}`} />
      <span className={connection === "ok" && allowance?.remaining === 0 ? "zero" : undefined}>{text}</span>
    </span>
  );
}

export default function Header({ connection, allowance, onHow, onReset, resetting }) {
  return (
    <header>
      <div className="brand">
        <h1>
          expense<span>.agent</span>
        </h1>
      </div>
      <div className="head-actions">
        <StatusPill connection={connection} allowance={allowance} />
        <button className="btn link" type="button" onClick={onHow}>
          How it works
        </button>
        <button className="btn" type="button" onClick={onReset} disabled={resetting} title="Wipe your session and reload sample data">
          Reset demo
        </button>
      </div>
    </header>
  );
}
