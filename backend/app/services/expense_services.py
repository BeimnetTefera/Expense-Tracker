# Application operations
    # This is where the actual operations happen.
        # create_expense() inserts an expense.
        # list_expenses() retrieves expenses.
        # search_expenses() applies search filters.
        # get_summary() calculates spending totals.
        # prepare_delete() and confirm_delete() manage deletion.

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json

from app.models import Expense, ExpenseCreate, SearchFilters, SummaryQuery, Period

def _now():
    return datetime.now(ZoneInfo("Africa/Addis_Ababa"))

def _today():
    return _now().date()

def search_expenses(
    conn,
    filters: SearchFilters,
    owner: str = "local",
    limit: int = 50,
) -> list[Expense]:
    
    if limit <= 0:
        raise ValueError("Limit must be greater than zero.")

    conditions = ["owner_id = ?"]
    params = [owner]

    if filters.category is not None:
        conditions.append("category = ?")
        params.append(filters.category)
        
    if filters.text is not None:
        conditions.append("(LOWER(description) LIKE ? OR LOWER(category) LIKE ?)")
        search_text = f"%{filters.text.lower()}%"
        params.extend([search_text, search_text])

        
        
    if filters.start_date is not None:
        conditions.append("spent_on >= ?")
        params.append(filters.start_date.isoformat())

    if filters.end_date is not None:
        conditions.append("spent_on <= ?")
        params.append(filters.end_date.isoformat())
        
        
    where_clause = " AND ".join(conditions)
    
    query = f"""
        SELECT *
        FROM expenses
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ?
    """
    
    params.append(limit)

    rows = conn.execute(query, params).fetchall()

    return [Expense(**dict(row)) for row in rows]



def create_expense(
    conn,
    data: ExpenseCreate,
    owner: str = "local",                     
    idempotency_key: str | None = None,       
) -> Expense:

    # only check for a duplicate when a key was actually given.
    if idempotency_key is not None:
        existing = conn.execute(
            "SELECT * FROM expenses WHERE idempotency_key = ? AND owner_id = ?",
            (idempotency_key, owner),
        ).fetchone()
        if existing:
            return Expense(**dict(existing))

    # Get the current timestamp in Africa/Addis_Ababa.
    created_at = datetime.now(ZoneInfo("Africa/Addis_Ababa"))

    # Insert the expense into the expenses table.
    cursor = conn.execute("""
                          INSERT INTO expenses(
                            owner_id,
                            amount_cents,
                            currency,
                            category,
                            description,
                            spent_on,
                            created_at,
                            idempotency_key
                          )
                          VALUES (?,?,?,?,?,?,?,?)
                          """,
                          (
                              owner,
                              data.amount_cents,
                              data.currency,
                              data.category,
                              data.description,
                              data.spent_on.isoformat(),
                              created_at.isoformat(),
                              idempotency_key,
                          ),
                          )
    # Commit the transaction.
    conn.commit()
    # Retrieve the generated ID using cursor.lastrowid.
    row = conn.execute(
        "SELECT * FROM expenses WHERE id = ?",
        (cursor.lastrowid,),
        ).fetchone()
    # Return an Expense model containing all saved fields.
    return Expense(**dict(row))



def list_expenses(conn, owner: str = "local", limit: int = 10) -> list[Expense]:
    rows = conn.execute(
        "SELECT * FROM expenses WHERE owner_id = ? ORDER BY created_at DESC LIMIT ?", (owner, limit)
    ).fetchall()
    expense_model = [Expense(**dict(row)) for row in rows]
    return expense_model


def _get_period_dates(query: SummaryQuery):
    today = _today()

    # All time: no date limits at all.
    if query.period == Period.ALL:
        return None, None

    if query.period == Period.TODAY:
        return today, today

    if query.period == Period.WEEK:
        start_date = today - timedelta(days=today.weekday())
        return start_date, today

    if query.period == Period.MONTH:
        start_date = today.replace(day=1)
        return start_date, today

    if query.period == Period.RANGE:
        return query.start_date, query.end_date

    raise ValueError("Unsupported summary period.")


def get_summary(
    conn,
    query: SummaryQuery,
    owner: str = "local",
) -> dict:

    start_date, end_date = _get_period_dates(query)

    conditions = ["owner_id = ?"]
    params = [owner]

    # Only filter by date when the period has dates ('all' has none).
    if start_date is not None:
        conditions.append("spent_on >= ?")
        params.append(start_date.isoformat())
    if end_date is not None:
        conditions.append("spent_on <= ?")
        params.append(end_date.isoformat())

    if query.category is not None:
        conditions.append("category = ?")
        params.append(query.category)

    where_clause = " AND ".join(conditions)

    totals = conn.execute(
        f"""
        SELECT
            COALESCE(SUM(amount_cents), 0) AS total_cents,
            COUNT(*) AS expense_count
        FROM expenses
        WHERE {where_clause}
        """,
        params,
    ).fetchone()

    categories = conn.execute(
        f"""
        SELECT
            category,
            SUM(amount_cents) AS total_cents,
            COUNT(*) AS expense_count
        FROM expenses
        WHERE {where_clause}
        GROUP BY category
        ORDER BY total_cents DESC
        """,
        params,
    ).fetchall()

    return {
        "period": query.period.value,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "total_cents": totals["total_cents"],
        "expense_count": totals["expense_count"],
        "by_category": [
            {
                "category": row["category"],
                "total_cents": row["total_cents"],
                "expense_count": row["expense_count"],
            }
            for row in categories
        ],
    }
    
    
def prepare_delete(
    conn,
    owner: str,
    expense_ids: list[int],
) -> dict:

    if not expense_ids:
        raise ValueError("No expense IDs provided.")

    if any(expense_id <= 0 for expense_id in expense_ids):
        raise ValueError("Expense IDs must be positive integers.")

    # Remove duplicate IDs while preserving their order.
    expense_ids = list(dict.fromkeys(expense_ids))

    placeholders = ", ".join("?" for _ in expense_ids)

    rows = conn.execute(
        f"""
        SELECT id
        FROM expenses
        WHERE owner_id = ?
        AND id IN ({placeholders})
        """,
        [owner, *expense_ids],
    ).fetchall()

    found_ids = {row["id"] for row in rows}

    if found_ids != set(expense_ids):
        raise LookupError("One or more expenses were not found.")

    expires_at = _now() + timedelta(minutes=5)

    cursor = conn.execute(
        """
        INSERT INTO pending_deletions (
            owner_id,
            expense_ids,
            status,
            expires_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            owner,
            json.dumps(expense_ids),
            "PENDING",
            expires_at.isoformat(),
        ),
    )

    conn.commit()

    return {
        "approval_id": cursor.lastrowid,
        "expense_ids": expense_ids,
        "status": "PENDING",
        "expires_at": expires_at.isoformat(),
    }
    
    
def confirm_delete(
    conn,
    owner: str,
    approval_id: int,
) -> dict:

    approval = conn.execute(
        """
        SELECT *
        FROM pending_deletions
        WHERE id = ? AND owner_id = ?
        """,
        (approval_id, owner),
    ).fetchone()

    if approval is None:
        raise LookupError("Deletion approval not found.")

    if approval["status"] != "PENDING":
        raise ValueError("This deletion approval is no longer pending.")

    expires_at = datetime.fromisoformat(approval["expires_at"])

    if _now() >= expires_at:
        conn.execute(
            """
            UPDATE pending_deletions
            SET status = 'EXPIRED'
            WHERE id = ? AND owner_id = ?
            """,
            (approval_id, owner),
        )
        conn.commit()
        raise ValueError("Deletion approval has expired.")

    expense_ids = json.loads(approval["expense_ids"])

    if not expense_ids:
        raise ValueError("No expenses stored in this approval.")

    placeholders = ", ".join("?" for _ in expense_ids)

    cursor = conn.execute(
        f"""
        DELETE FROM expenses
        WHERE owner_id = ?
        AND id IN ({placeholders})
        """,
        [owner, *expense_ids],
    )

    deleted_count = cursor.rowcount

    conn.execute(
        """
        UPDATE pending_deletions
        SET status = 'EXECUTED'
        WHERE id = ? AND owner_id = ?
        """,
        (approval_id, owner),
    )

    conn.commit()

    return {
        "approval_id": approval_id,
        "status": "EXECUTED",
        "deleted_count": deleted_count,
    }
    
    
def cancel_delete(
    conn,
    owner: str,
    approval_id: int,
) -> dict:

    approval = conn.execute(
        """
        SELECT *
        FROM pending_deletions
        WHERE id = ? AND owner_id = ?
        """,
        (approval_id, owner),
    ).fetchone()

    if approval is None:
        raise LookupError("Deletion approval not found.")

    if approval["status"] != "PENDING":
        raise ValueError("This deletion approval is no longer pending.")

    expires_at = datetime.fromisoformat(approval["expires_at"])

    if _now() >= expires_at:
        conn.execute(
            """
            UPDATE pending_deletions
            SET status = 'EXPIRED'
            WHERE id = ? AND owner_id = ?
            """,
            (approval_id, owner),
        )
        conn.commit()
        raise ValueError("Deletion approval has expired.")

    conn.execute(
        """
        UPDATE pending_deletions
        SET status = 'CANCELLED'
        WHERE id = ? AND owner_id = ?
        """,
        (approval_id, owner),
    )

    conn.commit()

    return {
        "approval_id": approval_id,
        "status": "CANCELLED",
    }
    
    
def get_pending_approval(conn, owner):
    row = conn.execute(
        """
        SELECT *
        FROM pending_deletions
        WHERE owner_id = ?
        AND status = 'PENDING'
        ORDER BY id DESC
        LIMIT 1
        """,
        (owner,),
    ).fetchone()

    if row is None:
        return None

    # An approval past its expiry is no longer pending: mark it and ignore it,
    # so an old forgotten delete can't block the user's next messages.
    if _now() >= datetime.fromisoformat(row["expires_at"]):
        conn.execute(
            "UPDATE pending_deletions SET status = 'EXPIRED' WHERE id = ? AND owner_id = ?",
            (row["id"], owner),
        )
        conn.commit()
        return None

    return row


# Fetch specific expenses, but only the ones this owner actually owns.
def get_expenses_by_ids(conn, owner: str, expense_ids: list[int]) -> list[Expense]:
    if not expense_ids:
        return []

    placeholders = ", ".join("?" for _ in expense_ids)
    rows = conn.execute(
        f"SELECT * FROM expenses WHERE owner_id = ? AND id IN ({placeholders})",
        [owner, *expense_ids],
    ).fetchall()
    return [Expense(**dict(row)) for row in rows]


# Wipe EVERYTHING one owner has (expenses, pending deletes, chat history).
# Every DELETE is filtered by owner_id: one visitor's reset never touches another.
def reset_owner_data(conn, owner: str) -> None:
    for table in ("expenses", "pending_deletions", "conversations"):
        # Table names come from the fixed tuple above, never from the user,
        # so the f-string is safe here. The VALUE still uses a ? placeholder.
        conn.execute(f"DELETE FROM {table} WHERE owner_id = ?", (owner,))
    conn.commit()
