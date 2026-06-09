import os
import sqlite3
import tempfile
import unittest

from bot.database import Database


class DatabaseMigrationTest(unittest.TestCase):
    def test_old_not_null_rules_table_accepts_blank_rules_after_migration(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        try:
            connection = sqlite3.connect(path)
            connection.execute(
                """
                CREATE TABLE departments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    company_code TEXT NOT NULL,
                    telegram_chat_id TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE department_rules (
                    department_id INTEGER PRIMARY KEY,
                    work_start_time TEXT NOT NULL,
                    break_start_time TEXT NOT NULL,
                    break_end_time TEXT NOT NULL,
                    work_end_time TEXT NOT NULL,
                    max_call_gap_minutes INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                "INSERT INTO departments (name, company_code, telegram_chat_id) VALUES (?, ?, ?)",
                ("Satış", "11111111", "-100"),
            )
            connection.execute(
                "INSERT INTO department_rules VALUES (?, ?, ?, ?, ?, ?)",
                (1, "11:10", "13:50", "15:15", "18:50", 15),
            )
            connection.commit()
            connection.close()

            database = Database(path)
            self.assertTrue(database.update_rules("Satış", None, None, None, None, None, None, None))
            rules = database.get_rules(1)
            self.assertIsNone(rules.work_start_time)
            self.assertIsNone(rules.pre_break_leave_time)
            self.assertIsNone(rules.break_start_time)
            self.assertIsNone(rules.break_end_time)
            self.assertIsNone(rules.post_break_start_time)
            self.assertIsNone(rules.work_end_time)
            self.assertIsNone(rules.max_call_gap_minutes)
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()