import { useCallback, useEffect, useRef, useState } from "react";
import ChatPanel from "./components/ChatPanel.jsx";
import ExpensesPanel from "./components/ExpensesPanel.jsx";
import Header from "./components/Header.jsx";
import HowItWorks from "./components/HowItWorks.jsx";
import { useAllowance } from "./hooks/useAllowance.js";
import { useConnection } from "./hooks/useConnection.js";
import { post } from "./lib/api.js";
import { SESSION } from "./lib/session.js";

const WELCOME =
  "Hi! I track expenses in **ETB**, and I've loaded some sample spending for you.\n\n" +
  "Try a suggestion below or tell me about something you bought. Click **Worked for…** above any reply to see every step I took.";

let nextId = 0;
const withId = (item) => ({ ...item, id: ++nextId });

// The chat is a list of items: user / agent / note / err / reply / approval.
export default function App() {
  const connection = useConnection();
  const { allowance, setAllowance, refresh: refreshAllowance } = useAllowance(SESSION.id);

  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [howOpen, setHowOpen] = useState(false);
  const [reloadToken, setReloadToken] = useState(0); // bump -> expenses re-fetch
  const [expensesEpoch, setExpensesEpoch] = useState(0); // bump -> expenses panel starts fresh

  const add = useCallback((item) => {
    const full = withId(item);
    setItems((list) => [...list, full]);
    return full.id;
  }, []);
  const update = useCallback((id, patch) => {
    setItems((list) => list.map((i) => (i.id === id ? { ...i, ...patch } : i)));
  }, []);
  const reloadExpenses = () => setReloadToken((n) => n + 1);

  async function send(message) {
    if (busy) return;
    setBusy(true);
    add({ type: "user", text: message });
    const replyId = add({ type: "reply", status: "working", label: "Working", startedAt: performance.now() });

    try {
      const data = await post("/chat", { session_id: SESSION.id, message });
      setAllowance(data.allowance); // the server's count, right after this message
      update(replyId, { status: "done", trace: data.trace, waiting: Boolean(data.pending_approval), markdown: data.reply });
      if (data.pending_approval) {
        // Only one approval card at a time.
        const card = withId({ type: "approval", pending: data.pending_approval });
        setItems((list) => [...list.filter((i) => i.type !== "approval"), card]);
      }
      reloadExpenses();
    } catch (e) {
      update(replyId, { status: "failed", error: e.status === 429 ? "Slow down a little: " + e.message : e.message });
      refreshAllowance(); // 429 / 503 / network: ask the server what's left
    } finally {
      setBusy(false);
    }
  }

  async function decide(card, decision) {
    setItems((list) => list.filter((i) => i.id !== card.id));
    const approvalId = card.pending.approval_id;
    const start = performance.now();
    const replyId = add({ type: "reply", status: "working", label: "Applying your decision", startedAt: start });

    try {
      const r = await post(`/approvals/${approvalId}`, { session_id: SESSION.id, decision });
      update(replyId, {
        status: "done",
        waiting: false,
        trace: [
          {
            step: 0,
            kind: "approval",
            tool: decision === "approve" ? "confirm_delete" : "cancel_delete",
            args: JSON.stringify({ approval_id: approvalId }),
            ok: true,
            ms: Math.round(performance.now() - start),
            error: null,
          },
        ],
        note:
          r.status === "EXECUTED"
            ? `You approved the deletion. ${r.deleted_count} expense${r.deleted_count === 1 ? "" : "s"} removed.`
            : "You kept it. Nothing was deleted.",
      });
    } catch (e) {
      update(replyId, { status: "failed", error: e.message });
    }
    reloadExpenses();
  }

  async function resetDemo(showNote) {
    setResetting(true);
    try {
      await post("/demo/reset", { session_id: SESSION.id });
      setItems([
        ...(showNote ? [withId({ type: "note", text: "Fresh start: your session was wiped and the sample data reloaded." })] : []),
        withId({ type: "agent", markdown: WELCOME }),
      ]);
      setExpensesEpoch((n) => n + 1);
    } catch (e) {
      add({ type: "err", text: e.message });
    } finally {
      setResetting(false);
    }
  }

  // First visit: seed sample data. Returning visitor: just greet them.
  // (The ref stops React's dev-mode double effect from seeding twice.)
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    if (SESSION.isNew) resetDemo(false);
    else setItems([withId({ type: "agent", markdown: WELCOME })]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <Header
        connection={connection}
        allowance={allowance}
        onHow={() => setHowOpen(true)}
        onReset={() => resetDemo(true)}
        resetting={resetting}
      />
      <main>
        <ChatPanel items={items} busy={busy} allowance={allowance} onSend={send} onDecide={decide} />
        <ExpensesPanel key={expensesEpoch} sessionId={SESSION.id} reloadToken={reloadToken} />
      </main>
      <HowItWorks open={howOpen} onClose={() => setHowOpen(false)} />
    </>
  );
}
