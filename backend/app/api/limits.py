# Rate limiting: protects the Groq bill once the API is public.
# In-memory "sliding window": remember WHEN recent requests happened per key,
# and refuse when too many fall inside the window.
#
# Trade-off (fine for a one-instance demo): counts reset on restart and are not
# shared between processes. At scale you'd keep these counters in Redis.

import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window = window_seconds
        self.hits = defaultdict(deque)  # key -> timestamps of recent requests
        # /chat runs in parallel threads; the lock makes check+record atomic,
        # so two simultaneous requests can't both slip in as "the 10th".
        self.lock = threading.Lock()

    def check(self, key: str) -> float | None:
        """Record a request for `key`.
        Returns None if allowed, or the seconds to wait if over the limit."""
        now = time.monotonic()
        with self.lock:
            timestamps = self.hits[key]

            # Forget requests that have slid out of the window.
            while timestamps and now - timestamps[0] >= self.window:
                timestamps.popleft()

            if len(timestamps) >= self.limit:
                # Wait until the oldest request leaves the window.
                return self.window - (now - timestamps[0])

            timestamps.append(now)
            return None

    def peek(self, key: str) -> tuple[int, float | None]:
        """Look WITHOUT recording: (requests left, seconds until the next slot frees).
        The second value is None when nothing is in the window."""
        now = time.monotonic()
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
                self.hits[key].pop()

    def reset(self):
        with self.lock:
            self.hits.clear()


# Three layers - each stops a different kind of abuse.
per_session = SlidingWindowLimiter(limit=10, window_seconds=60)       # one chatty user
per_ip = SlidingWindowLimiter(limit=30, window_seconds=60)            # fake session ids
global_daily = SlidingWindowLimiter(limit=300, window_seconds=86400)  # caps the bill


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
    for limiter in (per_session, per_ip, global_daily):
        limiter.reset()
