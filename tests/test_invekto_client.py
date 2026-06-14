import unittest
from datetime import date
from unittest.mock import Mock, patch

from bot.invekto_client import InvektoClient, InvektoConnectionError, InvektoTimeoutError


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

    def test_fetch_performance_report_uses_performance_report_type(self) -> None:
        client = InvektoClient("https://example.invalid")

        with patch.object(client, "_read_response", return_value='{"Status": true, "Data": []}') as read_response:
            client._fetch_performance_report_for_date("COMPANY", "2026-06-10")

        request_body = read_response.call_args.args[0].data.decode("utf-8")
        self.assertIn('"reportType": 1', request_body)

    def test_read_response_retries_timeout(self) -> None:
        client = InvektoClient("https://example.invalid", timeout_seconds=60, max_attempts=2)
        response = Mock()
        response.read.return_value = b'{"Status": true, "Data": []}'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)

        with patch("bot.invekto_client.time.sleep"), patch(
            "bot.invekto_client.request.urlopen", side_effect=[TimeoutError(), response]
        ) as urlopen:
            text = client._read_response(Mock())

        self.assertEqual(text, '{"Status": true, "Data": []}')
        self.assertEqual(urlopen.call_count, 2)

    def test_read_response_retries_connection_reset(self) -> None:
        client = InvektoClient("https://example.invalid", timeout_seconds=60, max_attempts=2)
        response = Mock()
        response.read.return_value = b'{"Status": true, "Data": []}'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)

        with patch("bot.invekto_client.time.sleep"), patch(
            "bot.invekto_client.request.urlopen", side_effect=[ConnectionResetError(), response]
        ) as urlopen:
            text = client._read_response(Mock())

        self.assertEqual(text, '{"Status": true, "Data": []}')
        self.assertEqual(urlopen.call_count, 2)

    def test_fetch_call_report_wraps_timeout_with_clear_message(self) -> None:
        client = InvektoClient("https://example.invalid", timeout_seconds=60, max_attempts=1)

        with patch.object(client, "_read_response", side_effect=TimeoutError):
            with self.assertRaises(InvektoTimeoutError) as error:
                client._fetch_call_report_for_date("COMPANY", "2026-06-10")

        self.assertIn("60 saniye", str(error.exception))

    def test_fetch_call_report_wraps_connection_reset_with_clear_message(self) -> None:
        client = InvektoClient("https://example.invalid", timeout_seconds=60, max_attempts=1)

        with patch.object(client, "_read_response", side_effect=ConnectionResetError):
            with self.assertRaises(InvektoConnectionError) as error:
                client._fetch_call_report_for_date("COMPANY", "2026-06-10")

        self.assertIn("bağlantıyı yarıda kapattı", str(error.exception))


if __name__ == "__main__":
    unittest.main()
