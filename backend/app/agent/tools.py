# Every tool receives the validated Pydantic model for its arguments.
from app.models import (
    Expense,
    ExpenseCreate,
    ListExpensesArgs,
    PrepareDeleteArgs,
    SearchFilters,
    SummaryQuery,
)
from app.services.expense_services import (
    create_expense,
    list_expenses,
    get_summary,
    search_expenses,
    prepare_delete,
)


def make_save_expense_tool(conn, owner="local"):
    def save_expense_tool(args: ExpenseCreate) -> Expense:
        return create_expense(conn, args, owner)
    return save_expense_tool


def make_list_expenses_tool(conn, owner="local"):
    def list_expenses_tool(args: ListExpensesArgs) -> list[Expense]:
        return list_expenses(conn, owner, args.limit)
    return list_expenses_tool


def make_get_summary_tool(conn, owner="local"):
    def get_summary_tool(args: SummaryQuery) -> dict:
        return get_summary(conn, args, owner)
    return get_summary_tool


def make_search_expenses_tool(conn, owner="local"):
    def search_expenses_tool(args: SearchFilters, limit: int = 50) -> list[Expense]:
        return search_expenses(conn, args, owner, limit)
    return search_expenses_tool


def make_prepare_delete_tool(conn, owner="local"):
    def prepare_delete_tool(args: PrepareDeleteArgs) -> dict:
        return prepare_delete(conn, owner, args.expense_ids)
    return prepare_delete_tool

# confirm/cancel are NOT tools: the LLM must never be able to approve a delete.
# Trusted code calls confirm_delete / cancel_delete from the service directly.
