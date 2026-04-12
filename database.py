from __future__ import annotations
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "expenses.db"


class Database:
    def __init__(self):
        self.db_path = DB_PATH
        self._init_db()

    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
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

    def _init_db(self):
        """Initialize database with tables and indexes."""
        with self.get_connection() as conn:
            # Create main table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE NOT NULL,
                    amount INTEGER NOT NULL,
                    notes TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for faster queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_expenses_date 
                ON expenses(date)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_expenses_category 
                ON expenses(category)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_expenses_date_category 
                ON expenses(date, category)
            """)
            
            # Run migration for legacy databases
            self._migrate(conn)
            
        logger.info("Database initialized successfully")

    def _migrate(self, conn: sqlite3.Connection):
        """Migrate legacy databases to add category column if missing."""
        cursor = conn.execute("PRAGMA table_info(expenses)")
        existing_columns = {row["name"] for row in cursor.fetchall()}

        if "category" not in existing_columns:
            conn.execute("""
                ALTER TABLE expenses ADD COLUMN category TEXT DEFAULT 'general'
            """)
            logger.info("Added 'category' column to expenses table")
        
        # Check if indexes exist (for databases created before indexes were added)
        cursor = conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND tbl_name='expenses'
        """)
        existing_indexes = {row["name"] for row in cursor.fetchall()}
        
        if "idx_expenses_date" not in existing_indexes:
            conn.execute("CREATE INDEX idx_expenses_date ON expenses(date)")
        if "idx_expenses_category" not in existing_indexes:
            conn.execute("CREATE INDEX idx_expenses_category ON expenses(category)")
        if "idx_expenses_date_category" not in existing_indexes:
            conn.execute("CREATE INDEX idx_expenses_date_category ON expenses(date, category)")

    def add_expense(self, date: datetime, amount: int, notes: str, category: str = 'general') -> int:
        """Add a new expense. Returns the new expense ID."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO expenses (date, amount, notes, category) VALUES (?, ?, ?, ?)",
                (date.strftime("%Y-%m-%d"), amount, notes, category)
            )
            logger.info(f"Added expense: {date.strftime('%Y-%m-%d')}, {amount}, {category}")
            return cursor.lastrowid

    def get_expenses_by_date(self, date: datetime, category: Optional[str] = None) -> list[dict]:
        """Get expenses for a specific date, optionally filtered by category."""
        with self.get_connection() as conn:
            query = """
                SELECT id, date, amount, notes, category 
                FROM expenses 
                WHERE date = ?
            """
            params = [date.strftime("%Y-%m-%d")]
            
            if category is not None:
                query += " AND category = ?"
                params.append(category)
                
            query += " ORDER BY created_at"
            
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]

    def get_expenses_by_range(self, start: datetime, end: datetime) -> list[dict]:
        """Get expenses within a date range."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, date, amount, notes, category 
                FROM expenses 
                WHERE date BETWEEN ? AND ? 
                ORDER BY date, created_at
                """,
                (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
            )
            rows = cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]

    def get_summary_by_months(
        self, 
        month_start: int, 
        month_end: int, 
        year: int, 
        category: Optional[str] = None
    ) -> list[dict]:
        """Get monthly summary for a month range."""
        with self.get_connection() as conn:
            query = """
                SELECT 
                    CAST(strftime('%m', date) AS INTEGER) as month,
                    SUM(amount) as total,
                    COUNT(*) as count
                FROM expenses
                WHERE 
                    CAST(strftime('%Y', date) AS INTEGER) = ?
                    AND CAST(strftime('%m', date) AS INTEGER) BETWEEN ? AND ?
            """
            params = [year, month_start, month_end]

            if category is not None:
                query += " AND category = ?"
                params.append(category)

            query += " GROUP BY month ORDER BY month"

            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            return [
                {
                    "month": row["month"],
                    "total": row["total"],
                    "count": row["count"]
                }
                for row in rows
            ]
        
    def get_expense_by_id(self, expense_id: int) -> Optional[dict]:
        """Get a single expense by ID."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, date, amount, notes, category FROM expenses WHERE id = ?", 
                (expense_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_dict(row)

    def delete_expense(self, expense_id: int) -> bool:
        """Delete an expense by ID. Returns True if deleted, False if not found."""
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted expense ID: {expense_id}")
            return deleted

    def edit_expense(
        self, 
        expense_id: int, 
        new_amount: Optional[int] = None, 
        new_notes: Optional[str] = None,
        new_category: Optional[str] = None
    ) -> bool:
        """
        Edit an expense. Only provided fields are updated.
        Returns True if updated, False if not found.
        """
        expense = self.get_expense_by_id(expense_id)
        if not expense:
            return False
            
        with self.get_connection() as conn:
            # Build dynamic update query based on provided fields
            updates = []
            params = []
            
            if new_amount is not None:
                updates.append("amount = ?")
                params.append(new_amount)
            if new_notes is not None:
                updates.append("notes = ?")
                params.append(new_notes)
            if new_category is not None:
                updates.append("category = ?")
                params.append(new_category)
            
            if not updates:
                return False  # Nothing to update
            
            params.append(expense_id)
            query = f"UPDATE expenses SET {', '.join(updates)} WHERE id = ?"
            cursor = conn.execute(query, params)
            updated = cursor.rowcount > 0
            
            if updated:
                logger.info(f"Updated expense ID: {expense_id}")
            return updated

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        """Convert a database row to a dictionary."""
        return {
            "id": row["id"],
            "date": datetime.strptime(row["date"], "%Y-%m-%d"),
            "amount": row["amount"],
            "notes": row["notes"],
            "category": row["category"]
        }
