import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api.js";

// "How many messages can I still send this minute?"
//
// The SERVER counts (backend/app/api/limits.py). The old page counted in the browser,
// which broke in three ways: it reset to 10/10 on every reload, it never saw the
// per-IP / daily limits, and it only redrew every 5 seconds. Now:
//   - on load we ask GET /limits
//   - every /chat reply carries a fresh `allowance`
//   - when the server says a slot frees up (`resets_in`), we ask again at that moment
export function useAllowance(sessionId) {
  const [allowance, setRaw] = useState(null); // {limit, remaining, resets_in, freesAt}

  const setAllowance = useCallback((a) => {
    if (!a) return;
    setRaw({ ...a, freesAt: a.resets_in != null ? Date.now() + a.resets_in * 1000 : null });
  }, []);

  const refresh = useCallback(async () => {
    try {
      setAllowance(await api(`/limits?session_id=${encodeURIComponent(sessionId)}`));
    } catch {
      /* the status pill already shows connection problems */
    }
  }, [sessionId, setAllowance]);

  // First look.
  useEffect(() => {
    refresh();
  }, [refresh]);

  // A message slides out of the 60 s window -> ask the server for the new number.
  useEffect(() => {
    if (!allowance?.freesAt) return;
    const t = setTimeout(refresh, Math.max(0, allowance.freesAt - Date.now()) + 300);
    return () => clearTimeout(t);
  }, [allowance, refresh]);

  // Browsers slow down timers in background tabs: re-check when the tab comes back.
  useEffect(() => {
    const onVisible = () => document.visibilityState === "visible" && refresh();
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [refresh]);

  return { allowance, setAllowance, refresh };
}

// Whole seconds until `deadline` (ms timestamp), re-rendering every second while active.
export function useSecondsUntil(deadline) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!deadline) return;
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [deadline]);
  return deadline ? Math.max(0, Math.ceil((deadline - now) / 1000)) : 0;
}
