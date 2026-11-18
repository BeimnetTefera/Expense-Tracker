# Integration tests: run_agent -> dispatcher -> registry/tools -> services -> SQLite.
# Everything is real except the LLM, which is replaced by a scripted fake so the
# tests are fast, free, and deterministic.

import copy
import json
from types import SimpleNamespace

import pytest

from app.agent import runtime
from app.agent.registry import build_registry
from app.agent.runtime import run_agent
from app.models import ExpenseCreate
from app.services.expense_services import create_expense


# ---------- helpers to build fake LLM messages ----------

def tool_call(name, arguments, call_id="call_1"):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def llm_calls_tools(*calls):
    return SimpleNamespace(content=None, tool_calls=list(calls))


def llm_says(text):
    return SimpleNamespace(content=text, tool_calls=None)


class FakeLLM:
    """Returns scripted responses in order and records what it was sent."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.received = []

    def __call__(self, messages):
        self.received.append(copy.deepcopy(messages))
        if not self.responses:
            raise AssertionError("FakeLLM was called more times than scripted.")
        return self.responses.pop(0)


def tool_results(messages):
    """The JSON results of every tool message in a conversation."""
    return [json.loads(m["content"]) for m in messages if m["role"] == "tool"]


# ---------- fixtures ----------

# History now lives in the `conversations` table, and every test gets a fresh
# in-memory database (see conftest.py), so tests can't leak history into each other.

@pytest.fixture
def registry(db):
    return build_registry(db)


@pytest.fixture
def fake_llm(monkeypatch):
    def install(*responses):
        llm = FakeLLM(*responses)
        # runtime imported get_llm_response by name, so patch it there.
        monkeypatch.setattr(runtime, "get_llm_response", llm)
        return llm
    return install


def count_expenses(db):
    return db.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]


def add_expense(db, amount_cents=30000, category="food", description="Lunch"):
    return create_expense(
        db,
        ExpenseCreate(amount_cents=amount_cents, category=category, description=description),
    )


# ---------- tests ----------

def test_save_expense_end_to_end(db, registry, fake_llm):
    llm = fake_llm(
        llm_calls_tools(tool_call("save_expense", {
            "amount_cents": 25000, "category": " Transport ", "description": "Taxi",
        })),
        llm_says("Saved your 250 ETB taxi expense."),
    )

    reply = run_agent("I spent 250 birr on a taxi", registry, db).reply

    assert reply == "Saved your 250 ETB taxi expense."

    row = db.execute("SELECT * FROM expenses").fetchone()
    assert row["amount_cents"] == 25000
    assert row["category"] == "transport"  # normalized by the model
    assert row["description"] == "Taxi"

    # The LLM's second call must include the successful tool result.
    [result] = tool_results(llm.received[1])
    assert result["ok"] is True
    assert result["result"]["amount_cents"] == 25000


def test_list_expenses_returns_db_rows_to_llm(db, registry, fake_llm):
    add_expense(db, 30000, "food", "Lunch")
    add_expense(db, 5000, "coffee", "Macchiato")

    llm = fake_llm(
        llm_calls_tools(tool_call("list_expenses", {"limit": 10})),
        llm_says("You have 2 expenses."),
    )

    reply = run_agent("list my expenses", registry, db).reply

    assert reply == "You have 2 expenses."
    [result] = tool_results(llm.received[1])
    assert result["ok"] is True
    assert {e["description"] for e in result["result"]} == {"Lunch", "Macchiato"}


def test_invalid_tool_arguments_are_reported_to_llm_and_nothing_saved(db, registry, fake_llm):
    llm = fake_llm(
        llm_calls_tools(tool_call("save_expense", {"amount_cents": -5, "category": "food"})),
        llm_says("That amount is not valid."),
    )

    reply = run_agent("I spent -5 on food", registry, db).reply

    assert reply == "That amount is not valid."
    assert count_expenses(db) == 0
    [result] = tool_results(llm.received[1])
    assert result["ok"] is False
    assert result["error"]["code"] == "VALIDATION_ERROR"


def test_delete_requires_approval_then_deletes_on_yes(db, registry, fake_llm):
    expense = add_expense(db)
    fake_llm(
        llm_calls_tools(tool_call("prepare_delete", {"expense_ids": [expense.id]})),
        llm_says("Reply yes to confirm deleting expense 1."),
    )

    run_agent("delete my lunch expense", registry, db)
    assert count_expenses(db) == 1  # nothing deleted before approval

    # Any other message is blocked while approval is pending.
    blocked = run_agent("list my expenses", registry, db).reply
    assert "pending deletion approval" in blocked
    assert count_expenses(db) == 1

    reply = run_agent("yes", registry, db).reply

    assert reply.startswith("Deletion approved")
    assert count_expenses(db) == 0
    status = db.execute("SELECT status FROM pending_deletions").fetchone()[0]
    assert status == "EXECUTED"


def test_delete_cancelled_on_no(db, registry, fake_llm):
    expense = add_expense(db)
    fake_llm(
        llm_calls_tools(tool_call("prepare_delete", {"expense_ids": [expense.id]})),
        llm_says("Reply yes to confirm."),
    )

    run_agent("delete my lunch expense", registry, db)
    reply = run_agent("no", registry, db).reply

    assert reply.startswith("Deletion cancelled")
    assert count_expenses(db) == 1
    status = db.execute("SELECT status FROM pending_deletions").fetchone()[0]
    assert status == "CANCELLED"


def test_history_is_saved_and_sent_on_next_request(db, registry, fake_llm):
    llm = fake_llm(llm_says("Hi!"), llm_says("You said hello earlier."))

    run_agent("hello", registry, db)
    saved = db.execute(
        "SELECT messages FROM conversations WHERE owner_id = 'local'"
    ).fetchone()
    assert saved is not None

    run_agent("what did I say?", registry, db)

    second_request = llm.received[1]
    assert second_request[0]["role"] == "system"
    contents = [m["content"] for m in second_request if m["role"] == "user"]
    assert contents == ["hello", "what did I say?"]


def test_sessions_do_not_see_each_others_history(db, fake_llm):
    llm = fake_llm(llm_says("Noted."), llm_says("Hello!"))
    registry_a = build_registry(db, owner="session-a")
    registry_b = build_registry(db, owner="session-b")

    run_agent("my secret is 1234", registry_a, db, owner="session-a")
    run_agent("hi", registry_b, db, owner="session-b")

    # What the LLM received for session B must not contain A's message.
    b_request = llm.received[1]
    contents = [m["content"] for m in b_request if m["role"] == "user"]
    assert contents == ["hi"]


def test_llm_failure_returns_friendly_message(db, registry, monkeypatch):
    def broken_llm(messages):
        raise RuntimeError("LLM_UNAVAILABLE")

    monkeypatch.setattr(runtime, "get_llm_response", broken_llm)

    reply = run_agent("list my expenses", registry, db).reply

    assert "currently unavailable" in reply


def test_stops_after_max_steps(db, registry, fake_llm):
    fake_llm(*[
        llm_calls_tools(tool_call("list_expenses", {}, call_id=f"call_{i}"))
        for i in range(runtime.MAX_STEPS)
    ])

    reply = run_agent("loop forever", registry, db).reply

    assert "maximum number of steps" in reply


def test_trace_records_every_llm_and_tool_step(db, registry, fake_llm):
    fake_llm(
        llm_calls_tools(tool_call("save_expense", {"amount_cents": -5, "category": "food"})),
        llm_says("That amount is not valid."),
    )

    result = run_agent("I spent -5 on food", registry, db)

    # llm (asks for tool) -> tool (fails validation) -> llm (final answer)
    assert [s["kind"] for s in result.trace] == ["llm", "tool", "llm"]

    tool_step = result.trace[1]
    assert tool_step["tool"] == "save_expense"
    assert tool_step["ok"] is False
    assert tool_step["error"]  # the validation message is recorded
    assert all(isinstance(s["ms"], int) for s in result.trace)


def test_invalid_tool_call_from_groq_lets_model_self_correct(db, registry, monkeypatch):
    from app.agent.llm import InvalidToolCallError

    responses = [
        InvalidToolCallError("period must be one of 'all', 'today', ..."),  # 1st try: rejected
        llm_says("You have spent 0 ETB in total."),                          # 2nd try: fixed
    ]
    received = []

    def scripted_llm(messages):
        received.append(copy.deepcopy(messages))
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(runtime, "get_llm_response", scripted_llm)

    result = run_agent("how much have I spent?", registry, db)

    assert result.reply == "You have spent 0 ETB in total."
    assert result.trace[0]["error"] == "INVALID_TOOL_CALL"
    # On the retry, the model was shown why its call was rejected.
    assert "rejected" in received[1][-1]["content"]


def test_llm_cannot_approve_its_own_delete(db, registry, fake_llm):
    # Regression: the model once called confirm_delete itself and deleted
    # an expense with no human approval. That must be impossible.
    expense = add_expense(db)
    llm = fake_llm(
        llm_calls_tools(tool_call("prepare_delete", {"expense_ids": [expense.id]}, call_id="c1")),
        llm_calls_tools(tool_call("confirm_delete", {"approval_id": 1}, call_id="c2")),
        llm_says("Deleted."),
    )

    run_agent("delete my lunch", registry, db)

    assert count_expenses(db) == 1  # still there
    status = db.execute("SELECT status FROM pending_deletions").fetchone()[0]
    assert status == "PENDING"      # still waiting for the HUMAN
    # The model was told the tool doesn't exist.
    results = tool_results(llm.received[2])
    assert results[-1]["error"]["code"] == "UNKNOWN_TOOL"


def test_llm_is_not_offered_approval_tools():
    from app.agent.definitions import TOOLS
    names = {t["function"]["name"] for t in TOOLS}
    assert "confirm_delete" not in names
    assert "cancel_delete" not in names


# ---------- context trimming ----------

from app.agent.runtime import trim_history


def test_trim_keeps_system_and_last_turns_only():
    msgs = [{"role": "system", "content": "sys"}]
    for i in range(10):
        msgs += [
            {"role": "user", "content": f"q{i}"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": f"c{i}"}]},
            {"role": "tool", "tool_call_id": f"c{i}", "content": "{}"},
            {"role": "assistant", "content": f"a{i}"},
        ]

    trimmed = trim_history(msgs, max_turns=3)

    assert trimmed[0]["role"] == "system"
    assert [m["content"] for m in trimmed if m["role"] == "user"] == ["q7", "q8", "q9"]
    # Never starts with an orphan tool result: first kept message is a user message.
    assert trimmed[1]["role"] == "user"


def test_llm_only_receives_recent_history(db, registry, fake_llm):
    total = runtime.MAX_HISTORY_TURNS + 3
    llm = fake_llm(*[llm_says(f"reply {i}") for i in range(total)])

    for i in range(total):
        run_agent(f"message {i}", registry, db)

    last_request = llm.received[-1]
    user_msgs = [m for m in last_request if m["role"] == "user"]
    # the last MAX_HISTORY_TURNS earlier exchanges + the new message
    assert len(user_msgs) == runtime.MAX_HISTORY_TURNS + 1
    assert user_msgs[-1]["content"] == f"message {total - 1}"
