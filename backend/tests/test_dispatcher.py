
import inspect
from app.agent.dispatcher import dispatch_tool



def fake_tool(args):
    return {"message": "Success"}


def test_valid_tool():
    registry = {"save_expense": fake_tool}

    result = dispatch_tool(
        "save_expense",
        '{"amount_cents": 10000, "description": "Lunch", "category": "food"}',
        registry,
    )

    assert result["ok"] is True


def test_unknown_tool():
    result = dispatch_tool("unknown_tool", "{}", {})
    assert result["ok"] is False
    assert result["error"]["code"] == "UNKNOWN_TOOL"


def test_invalid_arguments():
    registry = {"save_expense": fake_tool}
    result = dispatch_tool(
        "save_expense",
        '{"amount": -100, "description": "Lunch", "category": "food"}',
        registry,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "VALIDATION_ERROR"