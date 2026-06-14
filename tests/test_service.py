import asyncio
import unittest
from datetime import date, datetime, time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from bot.models import Department, DepartmentRules, Personnel
from bot.service import generate_department_report_payload


TZ = ZoneInfo("Europe/Istanbul")


class ServiceTest(unittest.TestCase):
    def test_department_report_uses_performance_totals_for_call_count_and_duration(self) -> None:
        database = SimpleNamespace(
            get_department=lambda department_identifier: Department(1, "Destek", "COMPANY", "CHAT", True),
            get_rules=lambda department_id: DepartmentRules(1, time(11, 10), None, None, None, None, None, 15),
            list_personnel=lambda department_id: [Personnel(1, 1, "Ahmet", "213", True)],
            list_leave_periods=lambda department_id, report_date: [],
            list_responsibles=lambda department_id: [],
        )
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


class _Client:
    def __init__(self, call_rows: list[dict[str, object]], performance_rows: list[dict[str, object]]) -> None:
        self.call_rows = call_rows
        self.performance_rows = performance_rows

    async def fetch_call_report(self, company_code: str, report_date: date) -> list[dict[str, object]]:
        return self.call_rows

    async def fetch_performance_report(self, company_code: str, report_date: date) -> list[dict[str, object]]:
        return self.performance_rows


if __name__ == "__main__":
    unittest.main()