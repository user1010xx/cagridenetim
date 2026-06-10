from __future__ import annotations

import asyncio
from datetime import date
import json
import socket
import time
from typing import Any
from urllib import request


class InvektoTimeoutError(RuntimeError):
    pass


class InvektoClient:
    def __init__(self, api_url: str, timeout_seconds: int = 60, max_attempts: int = 2) -> None:
        self.api_url = api_url
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, max_attempts)

    async def fetch_call_report(self, company_code: str, report_date: date) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._fetch_call_report_sync, company_code, report_date)

    def _fetch_call_report_sync(self, company_code: str, report_date: date) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for date_text in _date_texts(report_date):
            results = self._fetch_call_report_for_date(company_code, date_text)
            if results:
                return results
        return results

    def _fetch_call_report_for_date(self, company_code: str, date_text: str) -> list[dict[str, Any]]:
        payload = {
            "filterType": 0,
            "callID": "",
            "companyCode": company_code,
            "startDate": date_text,
            "endDate": date_text,
            "reportType": 5,
        }
        body = json.dumps(payload).encode("utf-8")
        api_request = request.Request(
            self.api_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "User-Agent": "invekto-kalite-kontrol-bot/1.0",
            },
            method="POST",
        )
        try:
            raw_body = self._read_response(api_request)
        except TimeoutError as exc:
            raise InvektoTimeoutError(
                f"Invekto API {self.timeout_seconds} saniye içinde yanıt vermedi. "
                "API geçici olarak yavaş olabilir veya kayıt sayısı yüksek olabilir."
            ) from exc
        result = json.loads(raw_body)
        if not result.get("Status"):
            message = result.get("Message") or "Invekto API isteği başarısız döndü."
            raise RuntimeError(str(message))
        data = result.get("Data") or []
        if not isinstance(data, list):
            raise RuntimeError("Invekto API Data alanı liste formatında değil.")
        return data

    def _read_response(self, api_request: request.Request) -> str:
        last_error: TimeoutError | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                with request.urlopen(api_request, timeout=self.timeout_seconds) as response:
                    return response.read().decode("utf-8-sig")
            except (TimeoutError, socket.timeout) as exc:
                last_error = exc
                if attempt < self.max_attempts:
                    time.sleep(1)
        if last_error is not None:
            raise last_error
        raise RuntimeError("Invekto API yanıtı okunamadı.")


def _date_texts(report_date: date) -> tuple[str, ...]:
    return (
        report_date.isoformat(),
        report_date.strftime("%d.%m.%Y"),
        report_date.strftime("%d/%m/%Y"),
    )
