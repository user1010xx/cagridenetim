from __future__ import annotations

import logging
from dataclasses import dataclass
from copy import copy
from dataclasses import replace
from datetime import date, datetime

from bot.database import Database
from bot.invekto_client import InvektoClient
from bot.models import Personnel
from bot.reporting import build_department_report
from bot.rules import PersonnelEvaluation
from bot.rules import evaluate_department, find_unmatched_call_names, normalize_calls
from bot.rules import _duration_to_seconds, _normalize_extension, _normalize_key
from bot.violation_keys import violation_key


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DepartmentReport:
    chat_id: str
    message: str
    notification_violations: tuple[tuple[str, str], ...]
    should_send: bool


async def generate_department_report(
    database: Database,
    client: InvektoClient,
    department_identifier: str | int,
    report_date: date,
    now: datetime,
    suppress_notified: bool = False,
) -> tuple[str, str]:
    report = await generate_department_report_payload(database, client, department_identifier, report_date, now, suppress_notified)
    return report.chat_id, report.message


async def generate_department_report_payload(
    database: Database,
    client: InvektoClient,
    department_identifier: str | int,
    report_date: date,
    now: datetime,
    suppress_notified: bool = False,
) -> DepartmentReport:
    department = database.get_department(department_identifier)
    if department is None:
        raise ValueError("Departman bulunamadı.")
    rules = database.get_rules(department.id)
    if not rules.is_configured:
        raise ValueError("Departman kuralları tanımlı değil. Önce /kuralayarla ile kuralları giriniz.")
    if database.is_department_weekly_leave(department.id, report_date.weekday(), report_date.isoformat()):
        message = (
            f"🟨 {department.name} için bugün haftalık departman izin günü.\n"
            "Otomatik saatlik rapor gönderilmez. Manuel /rapor da bu gün atlandı."
        )
        return DepartmentReport(department.telegram_chat_id, message, (), False)
    personnel = database.list_personnel(department.id)
    raw_calls = await client.fetch_call_report(department.company_code, report_date)
    calls = normalize_calls(raw_calls, now.tzinfo)
    leave_periods = _load_leave_periods(database, department.id, report_date, now.tzinfo)
    responsibles = database.list_responsibles(department.id)
    unmatched_call_names = find_unmatched_call_names(calls, personnel)
    if len(raw_calls) == 0:
        evaluations: list[PersonnelEvaluation] = []
    else:
        evaluations = evaluate_department(
            calls,
            personnel,
            rules,
            report_date,
            now,
            now.tzinfo,
            leave_periods=leave_periods,
        )
        evaluations = await _with_performance_totals(client, department.company_code, report_date, evaluations, personnel)
    notified_violations = database.list_notified_violations(department.id, report_date.isoformat()) if suppress_notified else set()
    report_evaluations = _filter_notified_violations(evaluations, notified_violations)
    notification_violations = tuple(_violation_keys(report_evaluations)) if suppress_notified else ()
    message = build_department_report(
        department=department,
        rules=rules,
        evaluations=report_evaluations,
        report_date=report_date,
        now=now,
        raw_call_count=len(raw_calls),
        processed_call_count=len(calls),
        raw_call_sample_keys=_raw_call_sample_keys(raw_calls),
        personnel=personnel,
        responsibles=responsibles,
        new_violations_only=suppress_notified,
        unmatched_call_names=unmatched_call_names,
    )
    should_send = _should_send_report(
        suppress_notified=suppress_notified,
        notification_violations=notification_violations,
        raw_call_count=len(raw_calls),
        processed_call_count=len(calls),
    )
    return DepartmentReport(department.telegram_chat_id, message, notification_violations, should_send)


def _filter_notified_violations(
    evaluations: list[PersonnelEvaluation],
    notified_violations: set[tuple[str, str]],
) -> list[PersonnelEvaluation]:
    if not notified_violations:
        return list(evaluations)
    filtered: list[PersonnelEvaluation] = []
    for evaluation in evaluations:
        next_evaluation = copy(evaluation)
        next_evaluation.calls = list(evaluation.calls)
        next_evaluation.leave_periods = list(evaluation.leave_periods)
        next_evaluation.violations = [
            violation
            for violation in evaluation.violations
            if (evaluation.name.casefold(), _violation_key(violation)) not in notified_violations
        ]
        filtered.append(next_evaluation)
    return filtered


def _violation_keys(evaluations: list[PersonnelEvaluation]) -> list[tuple[str, str]]:
    return [
        (evaluation.name.casefold(), _violation_key(violation))
        for evaluation in evaluations
        for violation in evaluation.violations
    ]


def _violation_key(violation: str) -> str:
    return violation_key(violation)


def _should_send_report(
    *,
    suppress_notified: bool,
    notification_violations: tuple[tuple[str, str], ...],
    raw_call_count: int,
    processed_call_count: int,
) -> bool:
    if not suppress_notified:
        return True
    if notification_violations:
        return True
    if raw_call_count == 0:
        return True
    if raw_call_count > 0 and processed_call_count == 0:
        return True
    return False


def _raw_call_sample_keys(raw_calls: list[dict[str, object]]) -> list[str]:
    if not raw_calls or not isinstance(raw_calls[0], dict):
        return []
    return [str(key) for key in raw_calls[0].keys()]


async def _with_performance_totals(
    client: InvektoClient,
    company_code: str,
    report_date: date,
    evaluations: list[PersonnelEvaluation],
    personnel: list[Personnel],
) -> list[PersonnelEvaluation]:
    try:
        performance_rows = await client.fetch_performance_report(company_code, report_date)
    except Exception as exc:
        logger.warning("Performans raporu alınamadı, detay çağrı toplamları kullanılacak: %s", exc)
        return evaluations
    return _apply_performance_totals(evaluations, performance_rows, personnel)


def _apply_performance_totals(
    evaluations: list[PersonnelEvaluation],
    performance_rows: list[dict[str, object]],
    personnel: list[Personnel],
) -> list[PersonnelEvaluation]:
    if not performance_rows:
        return evaluations
    totals = _performance_totals_by_person(performance_rows, personnel)
    if not totals:
        return evaluations
    updated_evaluations: list[PersonnelEvaluation] = []
    for evaluation in evaluations:
        key = evaluation.name.casefold()
        if key not in totals:
            updated_evaluations.append(evaluation)
            continue
        total_call_count, total_duration_seconds = totals[key]
        updated_evaluations.append(
            replace(
                evaluation,
                total_call_count=total_call_count,
                total_call_duration_seconds=total_duration_seconds,
            )
        )
    return updated_evaluations


def _performance_totals_by_person(
    performance_rows: list[dict[str, object]],
    personnel: list[Personnel],
) -> dict[str, tuple[int, int]]:
    extension_to_name = {
        _normalize_extension(person.extension): person.name
        for person in personnel
        if _normalize_extension(person.extension)
    }
    known_names = {_normalize_key(person.name): person.name for person in personnel}
    totals: dict[str, tuple[int, int]] = {}
    for row in performance_rows:
        if not isinstance(row, dict):
            continue
        name = _performance_person_name(row, extension_to_name, known_names)
        if not name:
            continue
        call_count = _performance_total_call_count(row)
        duration_seconds = _performance_total_duration_seconds(row)
        totals[name.casefold()] = (call_count, duration_seconds)
    return totals


def _performance_person_name(
    row: dict[str, object],
    extension_to_name: dict[str, str],
    known_names: dict[str, str],
) -> str | None:
    extension = _normalize_extension(_first_performance_value(row, "ExtensionNumber", "Extension", "Ext", "Dahili", "DAHİLİ"))
    if extension and extension in extension_to_name:
        return extension_to_name[extension]
    raw_name = _first_performance_value(row, "ExtensionName", "Extension Name", "Dahili Adı", "DAHİLİ ADI")
    if raw_name is None:
        return None
    name = " ".join(str(raw_name).strip().split())
    if not name:
        return None
    return known_names.get(_normalize_key(name), name)


def _performance_total_call_count(row: dict[str, object]) -> int:
    return _to_int(_first_performance_value(row, "TotalCall", "TOTALCALL", "TotalCallCount", "TOTALCALLCOUNT"))


def _performance_total_duration_seconds(row: dict[str, object]) -> int:
    return _duration_to_seconds(
        _first_performance_value(
            row,
            "TotalDuration",
            "TOTALDURATION",
            "TotalCallDuration",
            "TotalCallTime",
            "TOTALCALLTIME",
            "TOPLAM GÖRÜŞME SÜRESİ",
            "TOPLAM GORUSME SURESI",
        )
    )


def _first_performance_value(row: dict[str, object], *keys: str) -> object | None:
    casefolded = {str(key).strip().casefold(): value for key, value in row.items()}
    normalized = {_normalize_key(key): value for key, value in row.items()}
    for key in keys:
        value = row.get(key)
        if value is None:
            value = casefolded.get(key.casefold())
        if value is None:
            value = normalized.get(_normalize_key(key))
        if value not in (None, ""):
            return value
    return None


def _to_int(value: object | None) -> int:
    try:
        return int(float(str(value or "0").replace(",", ".")))
    except ValueError:
        return 0


def _load_leave_periods(database: Database, department_id: int, report_date: date, timezone) -> dict[str, list[tuple[datetime, datetime | None]]]:
    periods: dict[str, list[tuple[datetime, datetime | None]]] = {}
    for row in database.list_leave_periods(department_id, report_date.isoformat()):
        start_at = datetime.fromisoformat(str(row["start_at"])).astimezone(timezone)
        end_value = row["end_at"]
        end_at = datetime.fromisoformat(str(end_value)).astimezone(timezone) if end_value else None
        periods.setdefault(str(row["personnel_name"]).casefold(), []).append((start_at, end_at))
    return periods