from __future__ import annotations

from datetime import date, datetime

from bot.database import Database
from bot.invekto_client import InvektoClient
from bot.reporting import build_department_report
from bot.rules import evaluate_department, normalize_calls


async def generate_department_report(
    database: Database,
    client: InvektoClient,
    department_identifier: str | int,
    report_date: date,
    now: datetime,
) -> tuple[str, str]:
    department = database.get_department(department_identifier)
    if department is None:
        raise ValueError("Departman bulunamadı.")
    rules = database.get_rules(department.id)
    personnel = database.list_personnel(department.id)
    raw_calls = await client.fetch_call_report(department.company_code, report_date)
    calls = normalize_calls(raw_calls, now.tzinfo)
    leave_periods = _load_leave_periods(database, department.id, report_date, now.tzinfo)
    weekly_leave_names = {
        str(row["personnel_name"]).casefold()
        for row in database.list_weekly_leaves(department.id)
        if int(row["weekday"]) == report_date.weekday()
    }
    responsibles = database.list_responsibles(department.id)
    evaluations = evaluate_department(
        calls,
        personnel,
        rules,
        report_date,
        now,
        now.tzinfo,
        leave_periods=leave_periods,
        weekly_leave_names=weekly_leave_names,
    )
    message = build_department_report(
        department=department,
        rules=rules,
        evaluations=evaluations,
        report_date=report_date,
        now=now,
        raw_call_count=len(calls),
        personnel=personnel,
        responsibles=responsibles,
    )
    return department.telegram_chat_id, message


def _load_leave_periods(database: Database, department_id: int, report_date: date, timezone) -> dict[str, list[tuple[datetime, datetime | None]]]:
    periods: dict[str, list[tuple[datetime, datetime | None]]] = {}
    for row in database.list_leave_periods(department_id, report_date.isoformat()):
        start_at = datetime.fromisoformat(str(row["start_at"])).astimezone(timezone)
        end_value = row["end_at"]
        end_at = datetime.fromisoformat(str(end_value)).astimezone(timezone) if end_value else None
        periods.setdefault(str(row["personnel_name"]).casefold(), []).append((start_at, end_at))
    return periods