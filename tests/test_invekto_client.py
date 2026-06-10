import unittest
from datetime import date
from unittest.mock import patch

from bot.invekto_client import InvektoClient


class InvektoClientTest(unittest.TestCase):
    def test_fetch_call_report_retries_alternate_date_formats_when_empty(self) -> None:
        client = InvektoClient("https://example.invalid")
        calls = [{"id": 1}]

        with patch.object(client, "_fetch_call_report_for_date", side_effect=[[], calls]) as fetch:
            result = client._fetch_call_report_sync("COMPANY", date(2026, 6, 10))

        self.assertEqual(result, calls)
        self.assertEqual(fetch.call_args_list[0].args, ("COMPANY", "2026-06-10"))
        self.assertEqual(fetch.call_args_list[1].args, ("COMPANY", "10.06.2026"))

    def test_fetch_call_report_uses_slash_date_format_as_last_fallback(self) -> None:
        client = InvektoClient("https://example.invalid")
        calls = [{"id": 1}]

        with patch.object(client, "_fetch_call_report_for_date", side_effect=[[], [], calls]) as fetch:
            result = client._fetch_call_report_sync("COMPANY", date(2026, 6, 10))

        self.assertEqual(result, calls)
        self.assertEqual(fetch.call_args_list[2].args, ("COMPANY", "10/06/2026"))

    def test_fetch_call_report_returns_empty_after_all_date_formats(self) -> None:
        client = InvektoClient("https://example.invalid")

        with patch.object(client, "_fetch_call_report_for_date", side_effect=[[], [], []]) as fetch:
            result = client._fetch_call_report_sync("COMPANY", date(2026, 6, 10))

        self.assertEqual(result, [])
        self.assertEqual(fetch.call_count, 3)


if __name__ == "__main__":
    unittest.main()
