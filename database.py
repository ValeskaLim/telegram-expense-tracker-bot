from __future__ import annotations
import sqlite3
from datetime import datetime
from pathlib import Path
DB_PATH = Path(__file__).parent / "expenses.db"

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                amount INTEGER NOT NULL,
                notes TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._migrate()
        self.conn.commit()
        
    def _migrate(self):
        cursor = self.conn.execute("PRAGMA table_info(expenses)")
        existing_columns = {row["name"] for row in cursor.fetchall()}

        # Only alter if column doesn't exist yet
        if "category" not in existing_columns:
            self.conn.execute("""
                ALTER TABLE expenses ADD COLUMN category TEXT DEFAULT 'general'
            """)

    def add_expense(self, date: datetime, amount: int, notes: str, category: str = 'general'):
        self.conn.execute(
            "INSERT INTO expenses (date, amount, notes, category) VALUES (?, ?, ?, ?)",
            (date.strftime("%Y-%m-%d"), amount, notes, category)
        )
        self.conn.commit()

    def get_expenses_by_date(self, date: datetime) -> list[dict]:
        cursor = self.conn.execute(
            "SELECT id, date, amount, notes, category FROM expenses WHERE date = ? ORDER BY created_at",
            (date.strftime("%Y-%m-%d"),)
        )
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "date": datetime.strptime(row["date"], "%Y-%m-%d"),
                "amount": row["amount"],
                "notes": row["notes"],
                "category": row["category"]
            }
            for row in rows
        ]

    def get_expenses_by_range(self, start: datetime, end: datetime) -> list[dict]:
        cursor = self.conn.execute(
            "SELECT id, date, amount, notes, category FROM expenses WHERE date BETWEEN ? AND ? ORDER BY date, created_at",
            (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        )
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "date": datetime.strptime(row["date"], "%Y-%m-%d"),
                "amount": row["amount"],
                "notes": row["notes"],
                "category": row["category"]
            }
            for row in rows
        ]

    def get_summary_by_months(self, month_start: int, month_end: int, year: int, category: str | None = None) -> list[dict]:
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

        cursor = self.conn.execute(query, params)
        rows = cursor.fetchall()
        return [
            {
                "month": row["month"],
                "total": row["total"],
                "count": row["count"]
            }
            for row in rows
        ]
        
    def get_expense_by_id(self, expense_id: int):
        cursor = self.conn.execute(
            "SELECT id, date, amount, notes, category FROM expenses WHERE id = ?", (expense_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "date": datetime.strptime(row["date"], "%Y-%m-%d"),
            "amount": row["amount"],
            "notes": row["notes"],
            "category": row["category"]
        }

    def delete_expense(self, expense_id: int):
        self.conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        self.conn.commit()

    def edit_expense(self, expense_id: int, new_amount: int, new_notes: str, new_category: str = 'general'):
        self.conn.execute(
            "UPDATE expenses SET amount = ?, notes = ?, category = ? WHERE id = ?",
            (new_amount, new_notes, new_category, expense_id)
        )
        self.conn.commit()