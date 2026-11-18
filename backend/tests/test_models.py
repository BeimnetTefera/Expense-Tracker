
from datetime import date, datetime

from pydantic import ValidationError

from app.models import (
    ExpenseCreate,
    Expense,
    SearchFilters,
    SummaryQuery,
    Period,
)


# 1. ExpenseCreate: valid input
expense = ExpenseCreate(
    amount_cents=15000,
    category=" Food ",
    description="Lunch",
)

assert expense.amount_cents == 15000
assert expense.category == "food"
assert expense.currency == "ETB"
assert expense.spent_on == date.today()

print("1. ExpenseCreate valid input: PASSED")


# 2. ExpenseCreate: invalid inputs
for invalid_data in [
    {"amount_cents": 0, "category": "food"},
    {"amount_cents": -100, "category": "food"},
    {"amount_cents": 1000, "category": "   "},
]:
    try:
        ExpenseCreate(**invalid_data)
        raise AssertionError("Invalid expense was accepted")
    except ValidationError:
        pass

print("2. ExpenseCreate invalid inputs: PASSED")


# 3. Expense: complete saved expense
saved_expense = Expense(
    id=1,
    owner_id="local",
    amount_cents=15000,
    currency="ETB",
    category=" FOOD ",
    description="Lunch",
    spent_on=date(2026, 11, 14),
    created_at=datetime(2026, 11, 14, 9, 30),
)

assert saved_expense.category == "food"
assert saved_expense.id == 1

print("3. Expense saved model: PASSED")


# 4. SearchFilters: optional fields and normalization
filters = SearchFilters(
    category=" FOOD ",
    text="  lunch  ",
)

assert filters.category == "food"
assert filters.text == "lunch"
assert filters.start_date is None
assert filters.end_date is None

print("4. SearchFilters valid input: PASSED")


# 5. SearchFilters: invalid date range
try:
    SearchFilters(
        start_date=date(2026, 11, 15),
        end_date=date(2026, 11, 10),
    )
    raise AssertionError("Invalid date range was accepted")
except ValidationError:
    pass

print("5. SearchFilters invalid date range: PASSED")


# 6. SummaryQuery: valid monthly summary
summary = SummaryQuery(
    period=Period.MONTH,
    category=" FOOD ",
)

assert summary.period == Period.MONTH
assert summary.category == "food"

print("6. SummaryQuery valid input: PASSED")


# 7. SummaryQuery: range requires both dates
try:
    SummaryQuery(
        period=Period.RANGE,
        start_date=date(2026, 11, 1),
    )
    raise AssertionError("Incomplete date range was accepted")
except ValidationError:
    pass

print("7. SummaryQuery missing date: PASSED")


# 8. SummaryQuery: invalid date order
try:
    SummaryQuery(
        period=Period.RANGE,
        start_date=date(2026, 11, 15),
        end_date=date(2026, 11, 10),
    )
    raise AssertionError("Invalid summary date range was accepted")
except ValidationError:
    pass

print("8. SummaryQuery invalid date order: PASSED")


print("\nALL MODEL TESTS PASSED!")
