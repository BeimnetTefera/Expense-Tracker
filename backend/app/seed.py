# Sample data so a portfolio visitor sees a "lived-in" tracker, not an empty one.
# Dates are RELATIVE to today, so "this week" / "this month" always have data.

from datetime import timedelta

from app.models import ExpenseCreate
from app.services.expense_services import _today, create_expense, reset_owner_data

# (days ago, amount in ETB, category, description)
SAMPLE_EXPENSES = [
    (0, 60, "coffee", "Macchiato"),
    (0, 250, "food", "Lunch - shiro"),
    (1, 150, "transport", "Ride to office"),
    (2, 1200, "groceries", "Weekly groceries"),
    (3, 300, "internet", "Mobile data bundle"),
    (5, 450, "food", "Dinner with friends"),
    (8, 600, "utilities", "Electricity bill"),
    (12, 200, "entertainment", "Cinema ticket"),
]


def seed_owner(conn, owner: str) -> int:
    """Add the sample expenses for one owner. Returns how many were added."""
    today = _today()
    for days_ago, etb, category, description in SAMPLE_EXPENSES:
        create_expense(
            conn,
            ExpenseCreate(
                amount_cents=etb * 100,       # money stored as santim (integers)
                category=category,
                description=description,
                spent_on=today - timedelta(days=days_ago),
            ),
            owner,
        )
    return len(SAMPLE_EXPENSES)


def reset_demo(conn, owner: str) -> int:
    """Fresh start for one visitor: wipe their data, then re-add the samples."""
    reset_owner_data(conn, owner)
    return seed_owner(conn, owner)
