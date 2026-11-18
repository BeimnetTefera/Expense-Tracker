
from datetime import date

import pytest

from app.models import ExpenseCreate, SearchFilters, SummaryQuery, Period
from app.services.expense_services import (
    create_expense,
    list_expenses,
    search_expenses,
    get_summary,
    prepare_delete,
    confirm_delete,
    cancel_delete,
)


# Helper: create an expense for our tests
def make_expense(db, amount, category, description, spent_on):
    data = ExpenseCreate(
        amount_cents=amount,
        category=category,
        description=description,
        spent_on=spent_on,
    )
    return create_expense(db, data)


# 1. CREATE EXPENSE

def test_create_expense(db):
    data = ExpenseCreate(
        amount_cents=25000,
        category="food",
        currency="ETB",
        description="Lunch",
    )

    expense = create_expense(db, data)

    assert expense.id > 0
    assert expense.amount_cents == 25000
    assert expense.category == "food"
    assert expense.currency == "ETB"
    assert expense.description == "Lunch"

    row = db.execute(
        "SELECT * FROM expenses WHERE id = ?",
        (expense.id,),
    ).fetchone()

    assert row is not None
    assert row["amount_cents"] == 25000


# 2. LIST EXPENSES

def test_list_expenses_empty(db):
    expenses = list_expenses(db)

    assert expenses == []


def test_list_expenses_multiple(db):
    make_expense(db, 25000, "food", "Lunch", date(2026, 11, 10))
    make_expense(db, 10000, "transport", "Taxi", date(2026, 11, 11))

    expenses = list_expenses(db)

    assert len(expenses) == 2
    assert all(expense.id > 0 for expense in expenses)


def test_list_expenses_limit(db):
    for amount in [10000, 20000, 30000]:
        make_expense(db, amount, "food", "Meal", date(2026, 11, 10))

    expenses = list_expenses(db, limit=2)

    assert len(expenses) == 2


# 3. SEARCH EXPENSES

def test_search_by_category(db):
    make_expense(db, 25000, "food", "Lunch", date(2026, 11, 10))
    make_expense(db, 10000, "transport", "Taxi", date(2026, 11, 11))

    filters = SearchFilters(category="food")
    results = search_expenses(db, filters)

    assert len(results) == 1
    assert results[0].category == "food"


def test_search_by_text(db):
    make_expense(db, 25000, "food", "Lunch at restaurant", date(2026, 11, 10))
    make_expense(db, 10000, "transport", "Taxi ride", date(2026, 11, 11))

    filters = SearchFilters(text="restaurant")
    results = search_expenses(db, filters)

    assert len(results) == 1
    assert results[0].description == "Lunch at restaurant"


def test_search_by_date_range(db):
    make_expense(db, 10000, "food", "Meal one", date(2026, 11, 5))
    make_expense(db, 20000, "food", "Meal two", date(2026, 11, 15))
    make_expense(db, 30000, "food", "Meal three", date(2026, 11, 25))

    filters = SearchFilters(
        start_date=date(2026, 11, 10),
        end_date=date(2026, 11, 20),
    )

    results = search_expenses(db, filters)

    assert len(results) == 1
    assert results[0].amount_cents == 20000


def test_search_no_results(db):
    filters = SearchFilters(category="entertainment")

    results = search_expenses(db, filters)

    assert results == []


# 4. SUMMARY

def test_get_summary(db):
    make_expense(db, 25000, "food", "Lunch", date(2026, 11, 10))
    make_expense(db, 10000, "transport", "Taxi", date(2026, 11, 11))
    make_expense(db, 15000, "food", "Dinner", date(2026, 11, 12))

    query = SummaryQuery(
        period=Period.RANGE,
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 30),
    )

    summary = get_summary(db, query)

    assert summary["total_cents"] == 50000
    assert summary["expense_count"] == 3
    assert len(summary["by_category"]) == 2


def test_get_summary_with_category_filter(db):
    make_expense(db, 25000, "food", "Lunch", date(2026, 11, 10))
    make_expense(db, 10000, "transport", "Taxi", date(2026, 11, 11))

    query = SummaryQuery(
        period=Period.RANGE,
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 30),
        category="food",
    )

    summary = get_summary(db, query)

    assert summary["total_cents"] == 25000
    assert summary["expense_count"] == 1


def test_get_summary_empty_database(db):
    query = SummaryQuery(
        period=Period.RANGE,
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 30),
    )

    summary = get_summary(db, query)

    assert summary["total_cents"] == 0
    assert summary["expense_count"] == 0
    assert summary["by_category"] == []


# 5. DELETION WORKFLOW

def test_prepare_delete(db):
    expense = make_expense(
        db, 25000, "food", "Lunch", date(2026, 11, 10)
    )

    approval = prepare_delete(
        db,
        owner="local",
        expense_ids=[expense.id],
    )

    assert approval["status"] == "PENDING"
    assert expense.id in approval["expense_ids"]


def test_confirm_delete(db):
    expense = make_expense(
        db, 25000, "food", "Lunch", date(2026, 11, 10)
    )

    approval = prepare_delete(
        db,
        owner="local",
        expense_ids=[expense.id],
    )

    result = confirm_delete(
        db,
        owner="local",
        approval_id=approval["approval_id"],
    )

    assert result["status"] == "EXECUTED"
    assert result["deleted_count"] == 1
    assert list_expenses(db) == []


def test_cancel_delete(db):
    expense = make_expense(
        db, 25000, "food", "Lunch", date(2026, 11, 10)
    )

    approval = prepare_delete(
        db,
        owner="local",
        expense_ids=[expense.id],
    )

    result = cancel_delete(
        db,
        owner="local",
        approval_id=approval["approval_id"],
    )

    assert result["status"] == "CANCELLED"
    assert len(list_expenses(db)) == 1


def test_cannot_confirm_cancelled_deletion(db):
    expense = make_expense(
        db, 25000, "food", "Lunch", date(2026, 11, 10)
    )

    approval = prepare_delete(
        db,
        owner="local",
        expense_ids=[expense.id],
    )

    cancel_delete(
        db,
        owner="local",
        approval_id=approval["approval_id"],
    )

    with pytest.raises(ValueError):
        confirm_delete(
            db,
            owner="local",
            approval_id=approval["approval_id"],
        )


def test_get_summary_all_time_includes_every_date(db):
    # Years apart: only 'all' covers both.
    make_expense(db, 25000, "food", "Old lunch", date(2020, 1, 5))
    make_expense(db, 10000, "transport", "Taxi", date(2026, 11, 11))

    summary = get_summary(db, SummaryQuery(period=Period.ALL))

    assert summary["total_cents"] == 35000
    assert summary["expense_count"] == 2
    assert summary["start_date"] is None
