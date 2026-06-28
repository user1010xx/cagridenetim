import asyncio
import unittest
from datetime import date, datetime, time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from bot.models import Department, DepartmentRules, Personnel
from bot.service import _should_send_report, generate_department_report_payload


TZ = ZoneInfo("Europe/Istanbul")


class ServiceTest(unittest.TestCase):
    def test_department_report_uses_performance_totals_for_call_count_and_duration(self) -> None:
        database = _database([Personnel(1, 1, "Ahmet", "213", True)])
        client = _Client(
            call_rows=[
                {
                    "Date": "2026-06-10",
                    "Time": "11:20:00",
                    "ExtensionName": "Ahmet",
                    "ExtensionNumber": "213",
                    "CallTimeSecond": "300",
                    "RingTimeSecond": "30",
                }
            ],
            performance_rows=[
                {
                    "ExtensionName": "Ahmet",
                    "ExtensionNumber": "213",
                    "TotalCall": "6",
                    "TotalDuration": "00:02:35",
                }
            ],
        )

        report = asyncio.run(
            generate_department_report_payload(
                database,
                client,
                "Destek",
                date(2026, 6, 10),
                datetime(2026, 6, 10, 12, 0, tzinfo=TZ),
            )
        )

        self.assertIn("Ahmet (213) - 6 çağrı - 00:02:35", report.message)

    def test_department_report_keeps_call_totals_when_performance_report_is_empty(self) -> None:
        database = _database([Personnel(1, 1, "Ahmet", "213", True)])
        client = _Client(
            call_rows=[
                {
                    "Date": "2026-06-10",
                    "Time": "11:20:00",
                    "ExtensionName": "Ahmet",
                    "ExtensionNumber": "213",
                    "CallTimeSecond": "60",
                }
            ],
            performance_rows=[],
        )

        report = asyncio.run(
            generate_department_report_payload(
                database,
                client,
                "Destek",
                date(2026, 6, 10),
                datetime(2026, 6, 10, 12, 0, tzinfo=TZ),
            )
        )

        self.assertIn("Ahmet (213) - 1 çağrı - 00:01:00", report.message)

    def test_department_report_matches_performance_totals_by_name_without_extension(self) -> None:
        database = _database([Personnel(1, 1, "Ahmet", "213", True)])
        client = _Client(
            call_rows=[
                {
                    "Date": "2026-06-10",
                    "Time": "11:20:00",
                    "ExtensionName": "Ahmet",
                    "ExtensionNumber": "213",
                    "CallTimeSecond": "60",
                }
            ],
            performance_rows=[
                {
                    "ExtensionName": "Ahmet",
                    "TotalCall": "4",
                    "TotalDuration": "00:03:10",
                }
            ],
        )

        report = asyncio.run(
            generate_department_report_payload(
                database,
                client,
                "Destek",
                date(2026, 6, 10),
                datetime(2026, 6, 10, 12, 0, tzinfo=TZ),
            )
        )

        self.assertIn("Ahmet (213) - 4 çağrı - 00:03:10", report.message)

    def test_department_report_ignores_unmatched_performance_rows(self) -> None:
        database = _database([Personnel(1, 1, "Ahmet", "213", True)])
        client = _Client(
            call_rows=[
                {
                    "Date": "2026-06-10",
                    "Time": "11:20:00",
                    "ExtensionName": "Ahmet",
                    "ExtensionNumber": "213",
                    "CallTimeSecond": "60",
                }
            ],
            performance_rows=[
                {
                    "ExtensionName": "Mehmet",
                    "ExtensionNumber": "999",
                    "TotalCall": "9",
                    "TotalDuration": "00:09:00",
                }
            ],
        )

        report = asyncio.run(
            generate_department_report_payload(
                database,
                client,
                "Destek",
                date(2026, 6, 10),
                datetime(2026, 6, 10, 12, 0, tzinfo=TZ),
            )
        )

        self.assertIn("Ahmet (213) - 1 çağrı - 00:01:00", report.message)
        self.assertNotIn("00:09:00", report.message)

    def test_department_report_continues_when_performance_report_fails(self) -> None:
        database = _database([Personnel(1, 1, "Ahmet", "213", True)])
        client = _Client(
            call_rows=[
                {
                    "Date": "2026-06-10",
                    "Time": "11:20:00",
                    "ExtensionName": "Ahmet",
                    "ExtensionNumber": "213",
                    "CallTimeSecond": "60",
                }
            ],
            performance_rows=RuntimeError("performans raporu geçici olarak alınamadı"),
        )

        report = asyncio.run(
            generate_department_report_payload(
                database,
                client,
                "Destek",
                date(2026, 6, 10),
                datetime(2026, 6, 10, 12, 0, tzinfo=TZ),
            )
        )

        self.assertIn("Ahmet (213) - 1 çağrı - 00:01:00", report.message)

    def test_scheduled_report_is_not_sent_when_no_new_violations(self) -> None:
        database = _database(
            [Personnel(1, 1, "Ahmet", "213", True)],
            rules=DepartmentRules(1, None, None, None, None, None, None, None, True),
        )
        client = _Client(
            call_rows=[
                {
                    "Date": "2026-06-10",
                    "Time": "11:20:00",
                    "ExtensionName": "Ahmet",
                    "ExtensionNumber": "213",
                    "CallTimeSecond": "60",
                    "EventType": "1",
                }
            ],
            performance_rows=[],
        )

        report = asyncio.run(
            generate_department_report_payload(
                database,
                client,
                "Destek",
                date(2026, 6, 10),
                datetime(2026, 6, 10, 12, 0, tzinfo=TZ),
                suppress_notified=True,
            )
        )

        self.assertFalse(report.should_send)

    def test_scheduled_report_is_sent_for_zero_api_calls_alarm(self) -> None:
        database = _database([Personnel(1, 1, "Ahmet", "213", True)])
        client = _Client(call_rows=[], performance_rows=[])

        report = asyncio.run(
            generate_department_report_payload(
                database,
                client,
                "Destek",
                date(2026, 6, 10),
                datetime(2026, 6, 10, 12, 0, tzinfo=TZ),
                suppress_notified=True,
            )
        )

        self.assertTrue(report.should_send)
        self.assertIn("0 ÇAĞRI KAYDI", report.message)

    def test_department_weekly_leave_skips_manual_report(self) -> None:
        database = _database([Personnel(1, 1, "Ahmet", "213", True)], weekly_leave=True)
        client = _Client(call_rows=[], performance_rows=[])

        report = asyncio.run(
            generate_department_report_payload(
                database,
                client,
                "Destek",
                date(2026, 6, 11),
                datetime(2026, 6, 11, 12, 0, tzinfo=TZ),
            )
        )

        self.assertFalse(report.should_send)
        self.assertIn("haftalık departman izin günü", report.message.casefold())

    def test_should_send_report_helper(self) -> None:
        self.assertFalse(
            _should_send_report(
                suppress_notified=True,
                notification_violations=(),
                raw_call_count=5,
                processed_call_count=5,
            )
        )
        self.assertTrue(
            _should_send_report(
                suppress_notified=True,
                notification_violations=(("ali", "mesai başlangıcı ihlali"),),
                raw_call_count=5,
                processed_call_count=5,
            )
        )


class _Client:
    def __init__(self, call_rows: list[dict[str, object]], performance_rows: list[dict[str, object]] | Exception) -> None:
        self.call_rows = call_rows
        self.performance_rows = performance_rows

    async def fetch_call_report(self, company_code: str, report_date: date) -> list[dict[str, object]]:
        return self.call_rows

    async def fetch_performance_report(self, company_code: str, report_date: date) -> list[dict[str, object]]:
        if isinstance(self.performance_rows, Exception):
            raise self.performance_rows
        return self.performance_rows


def _database(
    personnel: list[Personnel],
    weekly_leave: bool = False,
    rules: DepartmentRules | None = None,
) -> SimpleNamespace:
    department_rules = rules or DepartmentRules(1, time(11, 10), None, None, None, None, None, 15, True)
    return SimpleNamespace(
        get_department=lambda department_identifier: Department(1, "Destek", "COMPANY", "CHAT", True),
        get_rules=lambda department_id: department_rules,
        list_personnel=lambda department_id: personnel,
        list_leave_periods=lambda department_id, report_date: [],
        list_responsibles=lambda department_id: [],
        list_notified_violations=lambda department_id, report_date: set(),
        is_department_weekly_leave=lambda department_id, weekday, report_date=None: weekly_leave,
    )


if __name__ == "__main__":
    unittest.main()