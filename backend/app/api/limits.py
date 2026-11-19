# Rate limiting: protects the Groq bill once the API is public.
# "Sliding window": remember WHEN recent requests happened per key,
# and refuse when too many fall inside the window.
#
# The timestamps live in memory (fast checks) AND are written through to a
# SQLite table, so a server restart doesn't hand everyone a fresh allowance:
# on startup, load_persisted_hits() reloads whatever is still inside a window.
# Trade-off (fine for a one-instance demo): not shared between processes.
# At scale you'd keep these counters in Redis.

import sqlite3
import threading
import time
from collections import defaultdict, deque

# One shared connection for all limiters, set by load_persisted_hits().
# None = memory only (e.g. before startup). Guarded by _db_lock.
_db: sqlite3.Connection | None = None
_db_lock = threading.Lock()


def _db_write(sql: str, params: tuple = ()):
    with _db_lock:
        if _db is not None:
            _db.execute(sql, params)
            _db.commit()


class SlidingWindowLimiter:
    def __init__(self, name: str, limit: int, window_seconds: float):
        self.name = name  # row label in the rate_limit_hits table
        self.limit = limit
        self.window = window_seconds
        self.hits = defaultdict(deque)  # key -> timestamps of recent requests
        # /chat runs in parallel threads; the lock makes check+record atomic,
        # so two simultaneous requests can't both slip in as "the 10th".
        self.lock = threading.Lock()

    def check(self, key: str) -> float | None:
        """Record a request for `key`.
        Returns None if allowed, or the seconds to wait if over the limit."""
        now = time.time()  # wall clock: must mean the same after a restart
        with self.lock:
            timestamps = self.hits[key]

            # Forget requests that have slid out of the window.
            while timestamps and now - timestamps[0] >= self.window:
                timestamps.popleft()

            if len(timestamps) >= self.limit:
                # Wait until the oldest request leaves the window.
                return self.window - (now - timestamps[0])

            timestamps.append(now)
            _db_write(
                "INSERT INTO rate_limit_hits(limiter, key, ts) VALUES (?, ?, ?)",
                (self.name, key, now),
            )
            return None

    def peek(self, key: str) -> tuple[int, float | None]:
        """Look WITHOUT recording: (requests left, seconds until the next slot frees).
        The second value is None when nothing is in the window."""
        now = time.time()  # wall clock: must mean the same after a restart
        with self.lock:
            timestamps = self.hits[key]
            while timestamps and now - timestamps[0] >= self.window:
                timestamps.popleft()
            left = max(0, self.limit - len(timestamps))
            next_free = self.window - (now - timestamps[0]) if timestamps else None
            return left, next_free

    def refund(self, key: str):
        """Give back the most recent request for `key` (it failed on our side)."""
        with self.lock:
            if self.hits[key]:
                ts = self.hits[key].pop()
                _db_write(
                    "DELETE FROM rate_limit_hits WHERE limiter = ? AND key = ? AND ts = ?",
                    (self.name, key, ts),
                )

    def reset(self):
        with self.lock:
            self.hits.clear()
            _db_write("DELETE FROM rate_limit_hits WHERE limiter = ?", (self.name,))


# Three layers - each stops a different kind of abuse.
per_session = SlidingWindowLimiter("session", limit=10, window_seconds=60)      # one chatty user
per_ip = SlidingWindowLimiter("ip", limit=30, window_seconds=60)                # fake session ids
global_daily = SlidingWindowLimiter("daily", limit=300, window_seconds=86400)   # caps the bill
LIMITERS = (per_session, per_ip, global_daily)


def load_persisted_hits(db_path: str):
    """Called once at startup: open the rate-limit table and reload every hit
    that is still inside its window, so a restart doesn't reset anyone's count."""
    global _db
    conn = sqlite3.connect(db_path, check_same_thread=False)  # used from worker threads, behind _db_lock
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rate_limit_hits(
            limiter TEXT NOT NULL,
            key TEXT NOT NULL,
            ts REAL NOT NULL
        )
    """)
    now = time.time()
    for limiter in LIMITERS:
        # Expired rows are useless: drop them so the table stays small.
        conn.execute(
            "DELETE FROM rate_limit_hits WHERE limiter = ? AND ts <= ?",
            (limiter.name, now - limiter.window),
        )
        rows = conn.execute(
            "SELECT key, ts FROM rate_limit_hits WHERE limiter = ? ORDER BY ts",
            (limiter.name,),
        ).fetchall()
        with limiter.lock:
            limiter.hits.clear()
            for key, ts in rows:
                limiter.hits[key].append(ts)
    conn.commit()
    with _db_lock:
        if _db is not None:
            _db.close()
        _db = conn


def close_persistence():
    global _db
    with _db_lock:
        if _db is not None:
            _db.close()
        _db = None


def check_chat_limits(session_id: str, client_ip: str) -> float | None:
    """None = allowed. Otherwise: seconds the caller should wait (-> HTTP 429)."""
    passed = []
    for limiter, key in (
        (per_ip, client_ip),
        (per_session, session_id),
        (global_daily, "all"),
    ):
        wait = limiter.check(key)
        if wait is not None:
            # Refused: undo the counts the earlier layers already recorded,
            # so a rejected request costs nothing anywhere.
            for earlier, earlier_key in passed:
                earlier.refund(earlier_key)
            return wait
        passed.append((limiter, key))
    return None


def refund_chat_limits(session_id: str, client_ip: str):
    """The LLM was unavailable: the visitor got no answer, so don't charge them."""
    per_ip.refund(client_ip)
    per_session.refund(session_id)
    global_daily.refund("all")


def chat_allowance(session_id: str, client_ip: str) -> dict:
    """What the UI's "N/10 msgs left" pill shows. The server is the source of truth:
    the browser's own count would reset on reload and can't see the IP/daily layers.
    remaining = the tightest of the three layers (the one that would refuse first)."""
    layers = [
        per_session.peek(session_id),
        per_ip.peek(client_ip),
        global_daily.peek("all"),
    ]
    remaining, next_free = min(layers, key=lambda layer: layer[0])
    return {
        "limit": per_session.limit,
        "remaining": min(remaining, per_session.limit),
        "resets_in": round(next_free, 1) if next_free is not None else None,
    }


def reset_all():
    """For tests: start every limiter from zero."""
    for limiter in LIMITERS:
        limiter.reset()
