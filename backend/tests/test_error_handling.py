
import sqlite3
from unittest.mock import Mock

from app.agent.dispatcher import dispatch_tool
from app.agent.llm import get_llm_response


def test_unknown_tool():
    result = dispatch_tool("fake_tool", "{}", {})

    assert result["ok"] is False
    assert result["error"]["code"] == "UNKNOWN_TOOL"


def test_validation_error():
    registry = {"save_expense": Mock()}

    result = dispatch_tool(
        "save_expense",
        '{"amount_cents": -100, "description": "Lunch", "category": "food"}',
        registry,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "VALIDATION_ERROR"


def test_not_found():
    def fake_tool(args):
        raise LookupError("Expense not found.")

    registry = {"prepare_delete": fake_tool}

    result = dispatch_tool("prepare_delete",'{"expense_ids": [1]}', registry)

    assert result["ok"] is False
    assert result["error"]["code"] == "NOT_FOUND"


def test_db_error():
    def fake_tool(args):
        raise sqlite3.OperationalError("Database is locked.")

    registry = {"save_expense": fake_tool}

    result = dispatch_tool(
        "save_expense",
        '{"amount_cents": 10000, "description": "Lunch", "category": "food"}',
        registry,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "DB_ERROR"


def test_llm_unavailable(monkeypatch):
    def fake_create(*args, **kwargs):
        raise ConnectionError("Connection failed.")

    monkeypatch.setattr(
        "app.agent.llm.client.chat.completions.create",
        fake_create,
    )

    try:
        get_llm_response([])
        assert False, "Expected RuntimeError was not raised."

    except RuntimeError as error:
        assert str(error) == "LLM_UNAVAILABLE"
