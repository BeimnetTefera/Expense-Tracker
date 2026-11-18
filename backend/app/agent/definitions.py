# tells the LLM which tools exist and what arguments they accept.
# Tool Definitions

from app.models import (
    ExpenseCreate, 
    SearchFilters, 
    SummaryQuery, 
    ListExpensesArgs, 
    PrepareDeleteArgs,
    )



def build_tool_definition(name, description, model):
    
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": model.model_json_schema()
        },
    }
    
    
TOOLS = [
    build_tool_definition(
        "save_expense",
        "save a new expense.",
        ExpenseCreate
        ),
    build_tool_definition(
        "list_expenses",
        "List the user's recent expenses.",
        ListExpensesArgs
        ),
    build_tool_definition(
        "get_summary",
        "Get total spending and per-category totals. period must be one of: "
        "'all' (every expense ever, use for 'so far' / 'in total'), 'today', "
        "'week' (this week), 'month' (this month), or 'range' (then start_date "
        "and end_date are required, e.g. for 'last 10 days').",
        SummaryQuery,
        ),
    build_tool_definition(
        "search_expenses",
        "Search expenses using filters such as category, text, and dates.",
        SearchFilters,
        ),
    build_tool_definition(
        "prepare_delete",
        "Prepare expenses for deletion. This does NOT delete anything. "
        "After calling it, tell the user to approve or cancel; only the user can do that.",
        PrepareDeleteArgs,
        ),
    # NO confirm_delete / cancel_delete here, on purpose: the LLM may only
    # PROPOSE a delete. Approving is the human's job, on a path the LLM can't reach.
]
