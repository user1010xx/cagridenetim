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

    def test_notified_violations_are_deduplicated(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        try:
            database = Database(path)
            department = database.add_department("Destek", "COMPANY", "CHAT")

            database.mark_notified_violations(
                department.id,
                "2026-06-10",
                [("Ayşe", "mesai ihlali"), ("Ayşe", "mesai ihlali")],
            )

            self.assertEqual(
                database.list_notified_violations(department.id, "2026-06-10"),
                {("ayşe", "mesai ihlali")},
            )
        finally:
            os.remove(path)

    def test_list_active_leave_periods_only_returns_open_leaves(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        try:
            database = Database(path)
            department = database.add_department("Destek", "COMPANY", "CHAT")
            other_department = database.add_department("Satış", "COMPANY", "CHAT2")
            database.start_leave(department.id, "Ayşe", "2026-06-10T11:00:00+03:00")
            database.start_leave(department.id, "Mehmet", "2026-06-10T12:00:00+03:00")
            database.start_leave(department.id, "Fatma", "2026-06-11T12:00:00+03:00")
            database.start_leave(other_department.id, "Veli", "2026-06-10T11:30:00+03:00")
            database.end_leave(department.id, "Mehmet", "2026-06-10T13:00:00+03:00")

            rows = database.list_active_leave_periods(department.id, "2026-06-10T14:00:00+03:00")

            self.assertEqual([str(row["personnel_name"]) for row in rows], ["Ayşe"])
        finally:
            os.remove(path)

    def test_department_weekly_leave_is_separate_from_personnel_weekly_leaves(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        try:
            database = Database(path)
            department = database.add_department("Destek", "COMPANY", "CHAT")
            database.add_weekly_leave(department.id, "Ayşe", 1)
            database.add_department_weekly_leave(department.id, 3)

            self.assertEqual([str(row["personnel_name"]) for row in database.list_weekly_leaves(department.id)], ["Ayşe"])
            self.assertEqual([int(row["weekday"]) for row in database.list_department_weekly_leaves(department.id)], [3])
            self.assertTrue(database.is_department_weekly_leave(department.id, 3))
            self.assertFalse(database.is_department_weekly_leave(department.id, 4))
        finally:
            os.remove(path)

    def test_department_weekly_leave_update_replaces_previous_day(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        try:
            database = Database(path)
            department = database.add_department("Destek", "COMPANY", "CHAT")
            database.add_department_weekly_leave(department.id, 1)
            database.add_department_weekly_leave(department.id, 3)

            self.assertEqual([int(row["weekday"]) for row in database.list_department_weekly_leaves(department.id)], [3])
        finally:
            os.remove(path)

    def test_new_department_starts_without_configured_rules(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        try:
            database = Database(path)
            department = database.add_department("Destek", "COMPANY", "CHAT")

            rules = database.get_rules(department.id)

            self.assertFalse(rules.is_configured)
            self.assertIsNone(rules.work_start_time)
            self.assertIsNone(rules.max_call_gap_minutes)
        finally:
            os.remove(path)

    def test_update_rules_marks_department_rules_configured(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        try:
            database = Database(path)
            department = database.add_department("Destek", "COMPANY", "CHAT")

            self.assertTrue(database.update_rules(department.id, "11:10", "13:50", "14:00", "15:00", "15:15", "18:50", 15))
            rules = database.get_rules(department.id)

            self.assertTrue(rules.is_configured)
            self.assertEqual(rules.max_call_gap_minutes, 15)
        finally:
            os.remove(path)

    def test_legacy_auto_default_rules_are_marked_unconfigured_once(self) -> None:
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
                    work_start_time TEXT,
                    pre_break_leave_time TEXT,
                    break_start_time TEXT,
                    break_end_time TEXT,
                    post_break_start_time TEXT,
                    work_end_time TEXT,
                    max_call_gap_minutes INTEGER
                )
                """
            )
            connection.execute(
                "INSERT INTO departments (name, company_code, telegram_chat_id) VALUES (?, ?, ?)",
                ("Karşılama", "COMPANY", "CHAT"),
            )
            connection.execute(
                "INSERT INTO department_rules VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (1, "11:10", None, "13:50", "15:15", None, "18:50", 15),
            )
            connection.commit()
            connection.close()

            database = Database(path)
            rules = database.get_rules(1)

            self.assertFalse(rules.is_configured)
            self.assertIsNone(rules.work_start_time)
            self.assertIsNone(rules.max_call_gap_minutes)
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()