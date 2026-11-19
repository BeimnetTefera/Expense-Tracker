# API tests: real FastAPI + real SQLite (temp file), fake LLM (no network, no tokens).

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agent import runtime
from app.api import limits, main


def llm_says(text):
    return SimpleNamespace(content=text, tool_calls=None)


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Point the API at a throwaway database file for this test only.
    monkeypatch.setattr(main, "DB_PATH", str(tmp_path / "api_test.db"))
    # Replace Groq with a fake that always answers "Hello!".
    monkeypatch.setattr(runtime, "get_llm_response", lambda messages: llm_says("Hello!"))
    # Every test starts with empty rate-limit counters.
    limits.reset_all()
    # `with` runs the lifespan (startup), so init_db creates the tables.
    with TestClient(main.app) as c:
        yield c


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_reply_and_trace(client):
    response = client.post("/chat", json={"session_id": "test-session-1", "message": "hi"})

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Hello!"
    assert body["trace"][0]["kind"] == "llm"


@pytest.mark.parametrize("bad_body", [
    {"session_id": "../../etc", "message": "hi"},       # path-traversal style id
    {"session_id": "test-session-1", "message": ""},   # empty message
    {"session_id": "test-session-1"},                  # missing message
    {"session_id": "test-session-1", "message": "x" * 5000},  # too long
])
def test_bad_body_is_rejected_with_422(client, bad_body):
    response = client.post("/chat", json=bad_body)
    assert response.status_code == 422


# ---------- approvals ----------

from app.db import get_connection
from app.models import ExpenseCreate
from app.services.expense_services import create_expense, prepare_delete

SESSION_A = "session-aaaa-1"
SESSION_B = "session-bbbb-2"


def make_pending_delete(owner):
    """Save one expense for `owner` and prepare its deletion. Returns approval_id."""
    conn = get_connection(main.DB_PATH)
    try:
        expense = create_expense(conn, ExpenseCreate(amount_cents=20000, category="tea"), owner)
        return prepare_delete(conn, owner, [expense.id])["approval_id"]
    finally:
        conn.close()


def count_expenses(owner):
    conn = get_connection(main.DB_PATH)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE owner_id = ?", (owner,)
        ).fetchone()[0]
    finally:
        conn.close()


def test_chat_shows_pending_approval_card(client):
    approval_id = make_pending_delete(SESSION_A)

    body = client.post("/chat", json={"session_id": SESSION_A, "message": "hi"}).json()

    card = body["pending_approval"]
    assert card["approval_id"] == approval_id
    assert card["expenses"][0]["amount_cents"] == 20000


def test_chat_without_pending_has_no_card(client):
    body = client.post("/chat", json={"session_id": SESSION_A, "message": "hi"}).json()
    assert body["pending_approval"] is None


def test_approve_deletes(client):
    approval_id = make_pending_delete(SESSION_A)

    response = client.post(f"/approvals/{approval_id}",
                           json={"session_id": SESSION_A, "decision": "approve"})

    assert response.status_code == 200
    assert response.json()["status"] == "EXECUTED"
    assert count_expenses(SESSION_A) == 0


def test_cancel_keeps_expense(client):
    approval_id = make_pending_delete(SESSION_A)

    response = client.post(f"/approvals/{approval_id}",
                           json={"session_id": SESSION_A, "decision": "cancel"})

    assert response.json()["status"] == "CANCELLED"
    assert count_expenses(SESSION_A) == 1


def test_other_session_cannot_approve(client):
    approval_id = make_pending_delete(SESSION_A)

    response = client.post(f"/approvals/{approval_id}",
                           json={"session_id": SESSION_B, "decision": "approve"})

    assert response.status_code == 404      # not 403: don't reveal it exists
    assert count_expenses(SESSION_A) == 1   # nothing deleted


def test_approving_twice_is_conflict(client):
    approval_id = make_pending_delete(SESSION_A)
    payload = {"session_id": SESSION_A, "decision": "approve"}

    client.post(f"/approvals/{approval_id}", json=payload)
    second = client.post(f"/approvals/{approval_id}", json=payload)

    assert second.status_code == 409


def test_unknown_decision_is_422(client):
    approval_id = make_pending_delete(SESSION_A)
    response = client.post(f"/approvals/{approval_id}",
                           json={"session_id": SESSION_A, "decision": "maybe"})
    assert response.status_code == 422


# ---------- demo reset + expenses ----------

from app.seed import SAMPLE_EXPENSES


def test_reset_seeds_sample_data(client):
    response = client.post("/demo/reset", json={"session_id": SESSION_A})

    assert response.status_code == 200
    assert response.json()["seeded"] == len(SAMPLE_EXPENSES)
    expenses = client.get("/expenses", params={"session_id": SESSION_A}).json()
    assert len(expenses) == len(SAMPLE_EXPENSES)


def test_reset_twice_does_not_duplicate(client):
    client.post("/demo/reset", json={"session_id": SESSION_A})
    client.post("/demo/reset", json={"session_id": SESSION_A})

    expenses = client.get("/expenses", params={"session_id": SESSION_A}).json()
    assert len(expenses) == len(SAMPLE_EXPENSES)


def test_reset_only_touches_own_session(client):
    make_pending_delete(SESSION_B)  # B has 1 expense + a pending delete

    client.post("/demo/reset", json={"session_id": SESSION_A})

    assert count_expenses(SESSION_B) == 1  # B untouched
    b_chat = client.post("/chat", json={"session_id": SESSION_B, "message": "hi"}).json()
    assert b_chat["pending_approval"] is not None  # B's approval survived


def test_reset_clears_history_and_pending(client):
    make_pending_delete(SESSION_A)
    client.post("/chat", json={"session_id": SESSION_A, "message": "hi"})

    client.post("/demo/reset", json={"session_id": SESSION_A})

    conn = get_connection(main.DB_PATH)
    try:
        history = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE owner_id = ?", (SESSION_A,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert history == 0
    body = client.post("/chat", json={"session_id": SESSION_A, "message": "hi"}).json()
    assert body["pending_approval"] is None


def test_expenses_rejects_bad_session_id(client):
    response = client.get("/expenses", params={"session_id": "../etc"})
    assert response.status_code == 422


# ---------- rate limits ----------

def test_session_rate_limit_returns_429(client):
    payload = {"session_id": SESSION_A, "message": "hi"}
    for _ in range(limits.per_session.limit):
        assert client.post("/chat", json=payload).status_code == 200

    blocked = client.post("/chat", json=payload)

    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0


def test_rate_limit_is_per_session(client):
    for _ in range(limits.per_session.limit):
        client.post("/chat", json={"session_id": SESSION_A, "message": "hi"})

    # A is blocked, but B still gets through.
    other = client.post("/chat", json={"session_id": SESSION_B, "message": "hi"})
    assert other.status_code == 200


def test_fake_session_ids_still_hit_ip_limit(client):
    # Attacker invents a new session id every time: the per-IP limit catches it.
    statuses = [
        client.post("/chat", json={"session_id": f"fake-session-{i:04d}", "message": "hi"}).status_code
        for i in range(limits.per_ip.limit + 1)
    ]
    assert statuses[-1] == 429


def test_rate_limited_request_never_calls_llm(client, monkeypatch):
    for _ in range(limits.per_session.limit):
        client.post("/chat", json={"session_id": SESSION_A, "message": "hi"})

    def must_not_be_called(messages):
        raise AssertionError("LLM called despite rate limit")
    monkeypatch.setattr(runtime, "get_llm_response", must_not_be_called)

    assert client.post("/chat", json={"session_id": SESSION_A, "message": "hi"}).status_code == 429


# ---------- allowance: the "N/10 msgs left" pill ----------

def test_limits_starts_full_and_peeking_is_free(client):
    for _ in range(3):  # looking must never use up a message
        body = client.get("/limits", params={"session_id": SESSION_A}).json()
    assert body == {"limit": 10, "remaining": 10, "resets_in": None}


def test_chat_response_carries_the_server_count(client):
    for expected_left in (9, 8, 7):
        body = client.post("/chat", json={"session_id": SESSION_A, "message": "hi"}).json()
        assert body["allowance"]["remaining"] == expected_left
        assert 0 < body["allowance"]["resets_in"] <= 60

    # A page reload asks /limits and must see the SAME count (the old bug: it showed 10 again).
    assert client.get("/limits", params={"session_id": SESSION_A}).json()["remaining"] == 7


def test_limits_shows_zero_when_blocked(client):
    for _ in range(limits.per_session.limit + 2):
        client.post("/chat", json={"session_id": SESSION_A, "message": "hi"})
    assert client.get("/limits", params={"session_id": SESSION_A}).json()["remaining"] == 0


def test_limits_reflects_the_ip_layer(client):
    # 25 messages from other sessions on the same IP leave only 5 for a fresh session.
    for i in range(25):
        client.post("/chat", json={"session_id": f"other-session-{i:04d}", "message": "hi"})
    assert client.get("/limits", params={"session_id": SESSION_B}).json()["remaining"] == 5


def test_failed_llm_call_is_not_counted_in_allowance(client, monkeypatch):
    monkeypatch.setattr(runtime, "get_llm_response", lambda m: (_ for _ in ()).throw(RuntimeError("LLM_UNAVAILABLE")))
    client.post("/chat", json={"session_id": SESSION_A, "message": "hi"})
    assert client.get("/limits", params={"session_id": SESSION_A}).json()["remaining"] == 10


# ---------- CORS ----------

def preflight(client, origin):
    # What a browser sends before a cross-site POST.
    return client.options("/chat", headers={
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
    })


def test_cors_allows_configured_origin(client):
    allowed = main.ALLOWED_ORIGINS[0]
    response = preflight(client, allowed)
    assert response.headers.get("access-control-allow-origin") == allowed


def test_cors_blocks_unknown_origin(client):
    response = preflight(client, "https://evil.example.com")
    assert "access-control-allow-origin" not in response.headers


# ---------- LLM unavailable: 503 and no charge ----------

def test_llm_unavailable_returns_503_and_is_not_counted(client, monkeypatch):
    def broken_llm(messages):
        raise RuntimeError("LLM_UNAVAILABLE")
    monkeypatch.setattr(runtime, "get_llm_response", broken_llm)

    for _ in range(limits.per_session.limit + 3):   # more than the limit...
        response = client.post("/chat", json={"session_id": SESSION_A, "message": "hi"})
        assert response.status_code == 503           # ...but never 429: failures are refunded

    assert len(limits.per_session.hits[SESSION_A]) == 0


def test_session_refusal_does_not_charge_ip(client):
    for _ in range(limits.per_session.limit + 5):
        client.post("/chat", json={"session_id": SESSION_A, "message": "hi"})

    # Only the 10 accepted requests count against the IP, not the refused ones.
    assert len(limits.per_ip.hits["testclient"]) == limits.per_session.limit
