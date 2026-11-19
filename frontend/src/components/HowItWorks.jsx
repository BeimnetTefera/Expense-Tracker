import { useEffect, useRef } from "react";

export default function HowItWorks({ open, onClose }) {
  const ref = useRef(null);

  // <dialog> is opened/closed imperatively; keep it in sync with `open`.
  useEffect(() => {
    const dialog = ref.current;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog ref={ref} aria-labelledby="howTitle" onClose={onClose}>
      <h2 id="howTitle">How it works</h2>
      <ol>
        <li>
          Your message and a list of tool descriptions go to an <b>LLM on Groq</b>.
        </li>
        <li>
          The LLM can only <b>ask</b> for a tool. Python looks the name up in an <b>allowlist</b> and validates the
          arguments with <b>Pydantic</b>. Bad arguments go back to the LLM as an error so it can fix them.
        </li>
        <li>
          The tool runs plain Python against <b>SQLite</b>. The result goes back to the LLM, and the loop repeats (at
          most 5 rounds) until it writes an answer.
        </li>
        <li>
          Deleting is split in two: the LLM can <b>propose</b> a delete, but only <b>you</b> can approve it. The
          approve action isn't a tool, so the LLM has no way to call it.
        </li>
      </ol>
      <p>
        Click <b>"Worked for…"</b> above any reply to see each step the agent took, with its arguments and timing.
      </p>
      <button className="btn" type="button" onClick={onClose}>
        Close
      </button>
    </dialog>
  );
}
