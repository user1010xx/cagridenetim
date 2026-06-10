from __future__ import annotations

import asyncio
from datetime import date
import json
from typing import Any
from urllib import request


class InvektoClient:
    def __init__(self, api_url: str, timeout_seconds: int = 30) -> None:
        self.api_url = api_url
        self.timeout_seconds = timeout_seconds

    async def fetch_call_report(self, company_code: str, report_date: date) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._fetch_call_report_sync, company_code, report_date)

    def _fetch_call_report_sync(self, company_code: str, report_date: date) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for date_text in _date_texts(report_date):
            results = self._fetch_call_report_for_date(company_code, date_text)
            if results:
                return results
        return results

    def _fetch_call_report_for_date(self, company_code: str, report_date: str) -> list[dict[str, Any]]:
        payload = {
            "filterType": 0,
            "callID": "",
            "companyCode": company_code,
            "startDate": report_date,
            "endDate": report_date,
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
        with request.urlopen(api_request, timeout=self.timeout_seconds) as response:
            raw_body = response.read().decode("utf-8-sig")
        result = json.loads(raw_body)
        if not result.get("Status"):
            message = result.get("Message") or "Invekto API isteği başarısız döndü."
            raise RuntimeError(str(message))
        data = result.get("Data") or []
        if not isinstance(data, list):
            raise RuntimeError("Invekto API Data alanı liste formatında değil.")
        return data


def _date_texts(report_date: date) -> tuple[str, ...]:
    return (
        report_date.isoformat(),
        report_date.strftime("%d.%m.%Y"),
        report_date.strftime("%d/%m/%Y"),
    )