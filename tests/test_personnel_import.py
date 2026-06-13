import unittest
from io import BytesIO

from openpyxl import Workbook

from bot.handlers import _format_invekto_check_success, _format_invekto_http_error, _format_personnel_list
from bot.models import Personnel
from bot.personnel_import import parse_personnel_workbook
from bot.reporting import build_department_report, _call_count_text
from urllib.error import HTTPError


class PersonnelImportTest(unittest.TestCase):
    def test_parse_personnel_workbook_reads_expected_columns(self) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["DEPARTMAN", "PERSONEL ADI", "DAHİLİ"])
        sheet.append(["Destek", "Ayşe", 101])
        sheet.append(["Destek", "Mehmet", None])
        content = BytesIO()
        workbook.save(content)
        workbook.close()

        rows, errors = parse_personnel_workbook(content.getvalue())

        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].department_name, "Destek")
        self.assertEqual(rows[0].personnel_name, "Ayşe")
        self.assertEqual(rows[0].extension, "101")
        self.assertIsNone(rows[1].extension)

    def test_parse_personnel_workbook_reports_missing_required_cells(self) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["DEPARTMAN", "PERSONEL ADI", "DAHİLİ"])
        sheet.append([None, "Ayşe", 101])
        sheet.append(["Destek", None, 624])
        sheet.append([None, None, None])
        content = BytesIO()
        workbook.save(content)
        workbook.close()

        rows, errors = parse_personnel_workbook(content.getvalue())

        self.assertEqual(rows, [])
        self.assertEqual(errors, ["Satır 2: departman boş", "Satır 3: personel adı boş"])

    def test_format_personnel_list_uses_sequential_numbers(self) -> None:
        text = _format_personnel_list(
            "Destek",
            [
                Personnel(id=41, department_id=1, name="Ayşe", extension="101", is_active=True),
                Personnel(id=12, department_id=1, name="Mehmet", extension=None, is_active=False),
            ],
        )

        lines = text.splitlines()
        self.assertTrue(lines[1].startswith("1. Ayşe"))
        self.assertTrue(lines[2].startswith("2. Mehmet"))

    def test_format_invekto_check_success(self) -> None:
        text = _format_invekto_check_success("Destek", 3, "2026-06-10")

        self.assertIn("✅ Destek için Invekto yanıt verdi.", text)
        self.assertIn("Kayıt sayısı: 3", text)

    def test_format_invekto_http_error_identifies_authorization_errors(self) -> None:
        error = HTTPError("https://example.invalid", 403, "Forbidden", {}, None)

        text = _format_invekto_http_error("Destek", error)

        self.assertIn("HTTP 403", text)
        self.assertIn("IP whitelist", text)

    def test_call_count_text_shows_raw_and_processed_counts(self) -> None:
        text = _call_count_text(10, 3)

        self.assertEqual(text, "☎️ API görüşme kaydı: 10 | işlenen: 3")

    def test_report_shows_sample_keys_when_raw_calls_are_not_processed(self) -> None:
        from datetime import date, datetime, time
        from zoneinfo import ZoneInfo

        from bot.models import Department, DepartmentRules

        text = build_department_report(
            department=Department(1, "Destek", "COMPANY", "CHAT", True),
            rules=DepartmentRules(1, time(11, 10), None, None, None, None, None, 15),
            evaluations=[],
            report_date=date(2026, 6, 10),
            now=datetime(2026, 6, 10, 12, 0, tzinfo=ZoneInfo("Europe/Istanbul")),
            raw_call_count=5,
            processed_call_count=0,
            raw_call_sample_keys=["Date", "Time", "Duration"],
            personnel=[],
        )

        self.assertIn("API veri döndü ama bot işleyemedi", text)
        self.assertIn("Date, Time, Duration", text)

    def test_report_new_violations_only_hides_ok_people(self) -> None:
        from datetime import date, datetime, time
        from zoneinfo import ZoneInfo

        from bot.models import Department, DepartmentRules
        from bot.rules import CallRecord, PersonnelEvaluation

        text = build_department_report(
            department=Department(1, "Destek", "COMPANY", "CHAT", True),
            rules=DepartmentRules(1, time(11, 10), None, None, None, None, None, 15),
            evaluations=[
                PersonnelEvaluation(
                    name="Ayşe",
                    extension="1001",
                    calls=[
                        CallRecord(
                            "Ayşe",
                            "1001",
                            datetime(2026, 6, 10, 11, 10, tzinfo=ZoneInfo("Europe/Istanbul")),
                            60,
                            "1",
                        )
                    ],
                    violations=["Yeni ihlal"],
                ),
                PersonnelEvaluation(
                    name="Mehmet",
                    extension="1002",
                    calls=[
                        CallRecord(
                            "Mehmet",
                            "1002",
                            datetime(2026, 6, 10, 11, 12, tzinfo=ZoneInfo("Europe/Istanbul")),
                            60,
                            "1",
                        ),
                        CallRecord(
                            "Mehmet",
                            "1002",
                            datetime(2026, 6, 10, 11, 30, tzinfo=ZoneInfo("Europe/Istanbul")),
                            60,
                            "1",
                        ),
                    ],
                    violations=[],
                ),
            ],
            report_date=date(2026, 6, 10),
            now=datetime(2026, 6, 10, 12, 0, tzinfo=ZoneInfo("Europe/Istanbul")),
            raw_call_count=5,
            processed_call_count=5,
            personnel=[],
            new_violations_only=True,
        )

        self.assertIn("1 yeni ihlal", text)
        self.assertIn("Ayşe", text)
        self.assertNotIn("Uygun Personeller", text)
        self.assertIn("Personel Çağrı Adetleri", text)
        self.assertIn("Ayşe (1001) - 1 çağrı", text)
        self.assertIn("Mehmet (1002) - 2 çağrı", text)

    def test_report_new_violations_only_shows_ok_people_when_no_new_violations(self) -> None:
        from datetime import date, datetime, time
        from zoneinfo import ZoneInfo

        from bot.models import Department, DepartmentRules
        from bot.rules import PersonnelEvaluation

        text = build_department_report(
            department=Department(1, "Destek", "COMPANY", "CHAT", True),
            rules=DepartmentRules(1, time(11, 10), None, None, None, None, None, 15),
            evaluations=[PersonnelEvaluation(name="Ayşe", extension="1001", violations=[])],
            report_date=date(2026, 6, 10),
            now=datetime(2026, 6, 10, 12, 0, tzinfo=ZoneInfo("Europe/Istanbul")),
            raw_call_count=5,
            processed_call_count=5,
            personnel=[],
            new_violations_only=True,
        )

        self.assertIn("0 yeni ihlal", text)
        self.assertIn("Yeni ihlal yok", text)
        self.assertNotIn("Uygun Personeller", text)
        self.assertIn("Yeni İhlali Olmayan Personeller", text)
        self.assertIn("Ayşe", text)

    def test_report_personnel_call_counts_use_total_call_count_when_available(self) -> None:
        from datetime import date, datetime, time
        from zoneinfo import ZoneInfo

        from bot.models import Department, DepartmentRules
        from bot.rules import PersonnelEvaluation

        text = build_department_report(
            department=Department(1, "Destek", "COMPANY", "CHAT", True),
            rules=DepartmentRules(1, time(11, 10), None, None, None, None, None, 15),
            evaluations=[PersonnelEvaluation(name="Asu", extension="605", calls=[], violations=[], total_call_count=12)],
            report_date=date(2026, 6, 10),
            now=datetime(2026, 6, 10, 12, 0, tzinfo=ZoneInfo("Europe/Istanbul")),
            raw_call_count=12,
            processed_call_count=12,
            personnel=[],
        )

        self.assertIn("Asu (605) - 12 çağrı", text)


if __name__ == "__main__":
    unittest.main()
