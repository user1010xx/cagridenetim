import unittest
from io import BytesIO

from openpyxl import Workbook

from bot.handlers import _format_invekto_check_success, _format_invekto_http_error, _format_personnel_list
from bot.models import Personnel
from bot.personnel_import import parse_personnel_workbook
from bot.reporting import _call_count_text
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


if __name__ == "__main__":
    unittest.main()
