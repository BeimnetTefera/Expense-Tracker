// Every call to the FastAPI backend goes through here.
export const API_URL = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

// Connection status for the header pill: "connecting" | "ok" | "waking" | "down".
// Components subscribe; api() reports what happened on each request.
const listeners = new Set();
export function onConnection(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
const report = (state) => listeners.forEach((fn) => fn(state));

// JSON in/out, readable errors, and a hint while a free host wakes up (~30 s cold start).
export async function api(path, options = {}) {
  const slow = setTimeout(() => report("waking"), 3500);
  try {
    const res = await fetch(API_URL + path, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    const data = await res.json().catch(() => ({}));
    report("ok"); // the server answered, even if it said no
    if (!res.ok) {
      const detail = typeof data.detail === "string" ? data.detail : `Request rejected (${res.status}).`;
      const err = new Error(detail);
      err.status = res.status;
      throw err;
    }
    return data;
  } catch (e) {
    if (!e.status) {
      report("down");
      e.message = "Can't reach the server. Is the backend running?";
    }
    throw e;
  } finally {
    clearTimeout(slow);
  }
}

export const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body) });
