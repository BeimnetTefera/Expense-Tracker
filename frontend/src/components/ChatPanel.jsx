import { useEffect, useRef, useState } from "react";
import { useSecondsUntil } from "../hooks/useAllowance.js";
import { EXAMPLES } from "../lib/explain.js";
import { markdownToHtml } from "../lib/format.js";
import ApprovalCard from "./ApprovalCard.jsx";
import Reply from "./Reply.jsx";

function Item({ item, onDecide }) {
  switch (item.type) {
    case "user":
      return <div className="msg user">{item.text}</div>;
    case "agent":
      return <div className="msg" dangerouslySetInnerHTML={{ __html: markdownToHtml(item.markdown) }} />;
    case "note":
      return <div className="msg note">{item.text}</div>;
    case "err":
      return <div className="msg err">{item.text}</div>;
    case "reply":
      return <Reply item={item} />;
    case "approval":
      return <ApprovalCard pending={item.pending} onDecide={(decision) => onDecide(item, decision)} />;
    default:
      return null;
  }
}

export default function ChatPanel({ items, busy, allowance, onSend, onDecide }) {
  const [text, setText] = useState("");
  const scrollRef = useRef(null);
  const inputRef = useRef(null);

  // Out of messages: block sending (the server would answer 429 anyway) and say when it frees up.
  const blocked = allowance?.remaining === 0;
  const secs = useSecondsUntil(blocked ? allowance.freesAt : null);
  const disabled = busy || blocked;

  // New message -> scroll to the bottom.
  useEffect(() => {
    const el = scrollRef.current;
    el?.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [items]);

  // Give focus back to the box after each answer.
  useEffect(() => {
    if (!busy) inputRef.current?.focus();
  }, [busy]);

  function submit(message) {
    if (disabled || !message.trim()) return;
    onSend(message.trim());
    setText("");
  }

  return (
    <section className="panel col-chat" aria-label="Chat">
      <div className="scroll" ref={scrollRef}>
        <div className="inner">
          <div id="chat" aria-live="polite">
            {items.map((item) => (
              <Item key={item.id} item={item} onDecide={onDecide} />
            ))}
          </div>
        </div>
      </div>
      <div className="footer-bar">
        <div className="inner examples">
          {EXAMPLES.map((example) => (
            <button key={example} type="button" className="chip" disabled={disabled} onClick={() => submit(example)}>
              {example}
            </button>
          ))}
        </div>
        <form
          className="inner composer"
          onSubmit={(e) => {
            e.preventDefault();
            submit(text);
          }}
        >
          <label htmlFor="input" className="vh">
            Message
          </label>
          <input
            id="input"
            ref={inputRef}
            maxLength={500}
            autoComplete="off"
            placeholder="Tell me what you spent…"
            value={text}
            readOnly={busy} // readOnly (not disabled) keeps focus and avoids a flash
            onChange={(e) => setText(e.target.value)}
          />
          <button className="btn-send" type="submit" disabled={disabled}>
            Send
          </button>
        </form>
        {blocked && (
          <div className="inner composer-hint" role="status">
            You've used this minute's {allowance.limit} messages. You can send again in {secs} s.
          </div>
        )}
      </div>
    </section>
  );
}
