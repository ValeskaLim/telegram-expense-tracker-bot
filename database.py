"""SQLite persistence layer for the Expense Tracker bot."""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "expenses.db"

# Columns selected for every expense row, in a single place so reads stay in sync.
_COLUMNS = "id, date, amount, notes, bank"


class Database:
    """Thin wrapper around the SQLite database storing expenses."""

    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = Path(db_path)
        self._init_db()

    # ── Connection management ────────────────────────────────────────────────
    @contextmanager
    def get_connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection, committing on success and rolling back on error."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    # ── Schema ───────────────────────────────────────────────────────────────
    def _init_db(self) -> None:
        """Create the table/indexes if needed and migrate legacy schemas."""
        with self.get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE NOT NULL,
                    amount INTEGER NOT NULL,
                    notes TEXT NOT NULL,
                    bank TEXT NOT NULL DEFAULT 'unknown',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._migrate(conn)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_expenses_bank ON expenses(bank)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_expenses_date_bank ON expenses(date, bank)"
            )
        logger.info("Database initialized at %s", self.db_path)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Bring older databases up to the current schema.

        Handles three states:
          * no payment column   -> add `bank`
          * legacy `category`   -> rename it to `bank`
          * already has `bank`  -> nothing to do
        """
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(expenses)")}
        if "bank" in columns:
            return
        if "category" in columns:
            conn.execute("ALTER TABLE expenses RENAME COLUMN category TO bank")
            logger.info("Migrated: renamed column 'category' -> 'bank'")
        else:
            conn.execute(
                "ALTER TABLE expenses ADD COLUMN bank TEXT NOT NULL DEFAULT 'unknown'"
            )
            logger.info("Migrated: added 'bank' column")

    # ── Writes ───────────────────────────────────────────────────────────────
    def add_expense(self, date: datetime, amount: int, notes: str, bank: str) -> int:
        """Insert a new expense and return its id."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO expenses (date, amount, notes, bank) VALUES (?, ?, ?, ?)",
                (date.strftime("%Y-%m-%d"), amount, notes, bank),
            )
            logger.info("Added expense id=%s amount=%s bank=%s", cursor.lastrowid, amount, bank)
            return cursor.lastrowid

    def delete_expense(self, expense_id: int) -> bool:
        """Delete an expense by id. Returns True if a row was removed."""
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
            if cursor.rowcount:
                logger.info("Deleted expense id=%s", expense_id)
                return True
            return False

    def update_expense(
        self,
        expense_id: int,
        *,
        amount: Optional[int] = None,
        notes: Optional[str] = None,
        bank: Optional[str] = None,
        date: Optional[datetime] = None,
    ) -> bool:
        """Update only the provided fields of an expense. Returns True if updated."""
        updates: list[str] = []
        params: list[object] = []
        if amount is not None:
            updates.append("amount = ?")
            params.append(amount)
        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)
        if bank is not None:
            updates.append("bank = ?")
            params.append(bank)
        if date is not None:
            updates.append("date = ?")
            params.append(date.strftime("%Y-%m-%d"))
        if not updates:
            return False

        params.append(expense_id)
        with self.get_connection() as conn:
            cursor = conn.execute(
                f"UPDATE expenses SET {', '.join(updates)} WHERE id = ?", params
            )
            if cursor.rowcount:
                logger.info("Updated expense id=%s", expense_id)
                return True
            return False

    # ── Reads ────────────────────────────────────────────────────────────────
    def get_expense_by_id(self, expense_id: int) -> Optional[dict]:
        with self.get_connection() as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM expenses WHERE id = ?", (expense_id,)
            ).fetchone()
            return self._row_to_dict(row) if row else None

    def get_expenses_by_date(
        self, date: datetime, bank: Optional[str] = None
    ) -> list[dict]:
        """All expenses on a date, optionally filtered by bank."""
        query = f"SELECT {_COLUMNS} FROM expenses WHERE date = ?"
        params: list[object] = [date.strftime("%Y-%m-%d")]
        if bank is not None:
            query += " AND bank = ?"
            params.append(bank)
        query += " ORDER BY created_at, id"
        with self.get_connection() as conn:
            return [self._row_to_dict(r) for r in conn.execute(query, params)]

    def get_expenses_by_month(self, month: int, year: int) -> list[dict]:
        """All expenses within a given month/year, ordered by date."""
        with self.get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT {_COLUMNS} FROM expenses
                WHERE CAST(strftime('%Y', date) AS INTEGER) = ?
                  AND CAST(strftime('%m', date) AS INTEGER) = ?
                ORDER BY date, created_at, id
                """,
                (year, month),
            )
            return [self._row_to_dict(r) for r in rows]

    # ── Helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "date": datetime.strptime(row["date"], "%Y-%m-%d"),
            "amount": row["amount"],
            "notes": row["notes"],
            "bank": row["bank"],
        }
