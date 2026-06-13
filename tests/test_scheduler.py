import asyncio
import unittest
from datetime import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.config import Config
from bot.models import Department, DepartmentRules
from bot.scheduler import _send_message_with_retry, _should_wait_before_next_department, send_scheduled_reports


class SchedulerTest(unittest.TestCase):
    def test_waits_between_departments_but_not_after_last_department(self) -> None:
        self.assertTrue(_should_wait_before_next_department(0, 3))
        self.assertTrue(_should_wait_before_next_department(1, 3))
        self.assertFalse(_should_wait_before_next_department(2, 3))

    def test_single_department_does_not_wait(self) -> None:
        self.assertFalse(_should_wait_before_next_department(0, 1))

    def test_scheduled_report_skips_department_on_weekly_leave_day(self) -> None:
        department = Department(1, "Destek", "COMPANY", "CHAT", True)
        database = SimpleNamespace(
            list_departments=lambda only_active=False: [department],
            is_department_weekly_leave=lambda department_id, weekday, report_date: True,
            get_rules=lambda department_id: DepartmentRules(department_id, time(11, 10), None, None, None, None, None, 15),
        )
        application = SimpleNamespace(
            bot_data={
                "config": _config(),
                "database": database,
                "client": SimpleNamespace(),
            },
            bot=SimpleNamespace(send_message=AsyncMock()),
        )

        with patch("bot.scheduler.generate_department_report_payload", new_callable=AsyncMock) as generate:
            asyncio.run(send_scheduled_reports(application))

        generate.assert_not_awaited()
        application.bot.send_message.assert_not_awaited()

    def test_send_message_retries_before_success(self) -> None:
        send_message = AsyncMock(side_effect=[RuntimeError("temporary"), None])
        application = SimpleNamespace(bot=SimpleNamespace(send_message=send_message))

        with patch("bot.scheduler.asyncio.sleep", new_callable=AsyncMock) as sleep:
            asyncio.run(_send_message_with_retry(application, "CHAT", "message"))

        self.assertEqual(send_message.await_count, 2)
        sleep.assert_awaited_once_with(1)


def _config() -> Config:
    return Config(
        telegram_bot_token="token",
        invekto_api_url="https://example.invalid",
        timezone_name="Europe/Istanbul",
        admin_user_ids=set(),
        allowed_group_names=set(),
        database_path=":memory:",
        report_interval_minutes=60,
        request_timeout_seconds=60,
        scheduler_start_time=time(0, 0),
        scheduler_end_time=time(23, 59),
    )


if __name__ == "__main__":
    unittest.main()