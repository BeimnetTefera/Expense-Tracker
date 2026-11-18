# tells Python which actual function to execute when the LLM requests a tool.
# This dict is the ALLOWLIST: anything in here, the LLM can trigger.
# So confirm_delete / cancel_delete must NEVER be added here - they are called
# only by trusted code (the yes/no path in runtime.py and POST /approvals).
from app.agent.tools import (
    make_get_summary_tool,
    make_list_expenses_tool,
    make_prepare_delete_tool,
    make_save_expense_tool,
    make_search_expenses_tool,
)


def build_registry(conn, owner="local"):
    # Call each factory so the registry holds ready-to-run tools bound to conn/owner.
    return {
        "save_expense": make_save_expense_tool(conn, owner),
        "list_expenses": make_list_expenses_tool(conn, owner),
        "search_expenses": make_search_expenses_tool(conn, owner),
        "get_summary": make_get_summary_tool(conn, owner),
        "prepare_delete": make_prepare_delete_tool(conn, owner),
    }
