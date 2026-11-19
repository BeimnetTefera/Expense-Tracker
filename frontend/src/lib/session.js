// A random id per browser. The server uses it as owner_id, so visitors never see
// each other's data. localStorage can be blocked: then the id lives in memory only.
const KEY = "expense-agent-session";

function makeId() {
  const raw = crypto.randomUUID ? crypto.randomUUID() : Date.now() + "-" + Math.random().toString(16).slice(2);
  return raw.replace(/[^A-Za-z0-9-]/g, "");
}

function load() {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved) return { id: saved, isNew: false };
    const id = makeId();
    localStorage.setItem(KEY, id);
    return { id, isNew: true };
  } catch {
    return { id: makeId(), isNew: true };
  }
}

// Computed once when the module loads, so every component sees the same id.
export const SESSION = load();
