import unittest
from types import SimpleNamespace

from bot.handlers import _can_report_department_in_chat, _is_registered_department_chat
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


if __name__ == "__main__":
    unittest.main()