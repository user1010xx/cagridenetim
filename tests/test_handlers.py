import unittest
from types import SimpleNamespace

from bot.config import Config
from bot.handlers import (
    _can_report_department_in_chat,
    _departments_visible_in_chat,
    _format_datetime_text,
    _is_allowed,
    _is_registered_department_chat,
)
from bot.models import Department


class HandlerTest(unittest.TestCase):
    def test_can_report_department_in_registered_group(self) -> None:
        update = SimpleNamespace(effective_chat=SimpleNamespace(id=-1001, type="group"))
        department = Department(1, "Satış1", "COMPANY", "-1001", True)

        self.assertTrue(_can_report_department_in_chat(update, department))

    def test_cannot_report_department_in_other_group(self) -> None:
        update = SimpleNamespace(effective_chat=SimpleNamespace(id=-1002, type="group"))
        department = Department(1, "Satış1", "COMPANY", "-1001", True)

        self.assertFalse(_can_report_department_in_chat(update, department))

    def test_admin_private_chat_can_report_department(self) -> None:
        update = SimpleNamespace(effective_chat=SimpleNamespace(id=123, type="private"))
        department = Department(1, "Satış1", "COMPANY", "-1001", True)

        self.assertTrue(_can_report_department_in_chat(update, department))

    def test_registered_department_chat_is_allowed_without_group_name_env(self) -> None:
        database = SimpleNamespace(
            list_departments=lambda: [
                Department(1, "Satış1", "COMPANY", "-1001", True),
                Department(2, "Satış2", "COMPANY", "-1002", True),
            ]
        )

        self.assertTrue(_is_registered_department_chat(database, -1002))

    def test_unregistered_department_chat_is_not_allowed(self) -> None:
        database = SimpleNamespace(
            list_departments=lambda: [
                Department(1, "Satış1", "COMPANY", "-1001", True),
            ]
        )

        self.assertFalse(_is_registered_department_chat(database, -1003))

    def test_admin_can_use_commands_in_unregistered_group_for_setup(self) -> None:
        update = SimpleNamespace(
            effective_chat=SimpleNamespace(id=-1003, type="group", title="Yeni Grup"),
            effective_user=SimpleNamespace(id=42),
        )
        context = SimpleNamespace(
            application=SimpleNamespace(
                bot_data={
                    "config": _config(admin_user_ids={42}),
                    "database": SimpleNamespace(list_departments=lambda: []),
                }
            )
        )

        self.assertTrue(_is_allowed(update, context))

    def test_non_admin_cannot_use_commands_in_unregistered_group(self) -> None:
        update = SimpleNamespace(
            effective_chat=SimpleNamespace(id=-1003, type="group", title="Yeni Grup"),
            effective_user=SimpleNamespace(id=7),
        )
        context = SimpleNamespace(
            application=SimpleNamespace(
                bot_data={
                    "config": _config(admin_user_ids={42}),
                    "database": SimpleNamespace(list_departments=lambda: []),
                }
            )
        )

        self.assertFalse(_is_allowed(update, context))

    def test_department_list_in_group_shows_only_group_department(self) -> None:
        update = SimpleNamespace(effective_chat=SimpleNamespace(id=-1002, type="group"))
        departments = [
            Department(1, "Satış1", "COMPANY", "-1001", True),
            Department(2, "Satış2", "COMPANY", "-1002", True),
        ]

        self.assertEqual(_departments_visible_in_chat(update, departments), [departments[1]])

    def test_department_list_in_private_chat_shows_all_departments_for_admin(self) -> None:
        update = SimpleNamespace(effective_chat=SimpleNamespace(id=42, type="private"), effective_user=SimpleNamespace(id=42))
        departments = [
            Department(1, "Satış1", "COMPANY", "-1001", True),
            Department(2, "Satış2", "COMPANY", "-1002", True),
        ]

        self.assertEqual(_departments_visible_in_chat(update, departments, _config({42})), departments)

    def test_department_list_in_private_chat_hides_departments_for_non_admin(self) -> None:
        update = SimpleNamespace(effective_chat=SimpleNamespace(id=7, type="private"), effective_user=SimpleNamespace(id=7))
        departments = [
            Department(1, "Satış1", "COMPANY", "-1001", True),
        ]

        self.assertEqual(_departments_visible_in_chat(update, departments, _config({42})), [])

    def test_format_datetime_text_formats_iso_values(self) -> None:
        self.assertEqual(_format_datetime_text("2026-06-10T11:00:00+03:00"), "10.06.2026 11:00")

    def test_format_datetime_text_converts_to_config_timezone(self) -> None:
        self.assertEqual(_format_datetime_text("2026-06-10T08:00:00+00:00", _config({42})), "10.06.2026 11:00")


def _config(admin_user_ids: set[int]) -> Config:
    return Config(
        telegram_bot_token="token",
        invekto_api_url="https://example.invalid",
        timezone_name="Europe/Istanbul",
        admin_user_ids=admin_user_ids,
        allowed_group_names=set(),
        database_path=":memory:",
        report_interval_minutes=60,
        request_timeout_seconds=60,
        scheduler_start_time=None,
        scheduler_end_time=None,
    )


if __name__ == "__main__":
    unittest.main()