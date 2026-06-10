from __future__ import annotations

from datetime import date, datetime

from bot.models import Department, DepartmentResponsible, DepartmentRules, Personnel
from bot.rules import PersonnelEvaluation
from bot.time_utils import format_time


def build_department_report(
    department: Department,
    rules: DepartmentRules,
    evaluations: list[PersonnelEvaluation],
    report_date: date,
    now: datetime,
    raw_call_count: int,
    personnel: list[Personnel],
    responsibles: list[DepartmentResponsible] | None = None,
    processed_call_count: int | None = None,
) -> str:
    violation_count = sum(len(evaluation.violations) for evaluation in evaluations)
    ok_count = sum(1 for evaluation in evaluations if not evaluation.violations)
    lines = [
        "📊 Invekto Çağrı Kural Kontrol Raporu",
        f"🏢 Departman: {department.name}",
        f"📅 Tarih: {report_date.strftime('%d.%m.%Y')} | ⏰ Kontrol: {now.strftime('%H:%M')}",
        f"⚙️ Kurallar: {_rules_summary(rules)}",
        _call_count_text(raw_call_count, processed_call_count),
        "",
    ]
    if responsibles:
        mentions = " ".join(f"@{responsible.username}" for responsible in responsibles)
        lines.append(f"👥 Sorumlular: {mentions}")
    if not personnel:
        lines.extend(
            [
                "ℹ️ Bu departmanda personel listesi tanımlı değil.",
                "Sadece API'de çağrısı görünen kişiler kontrol edildi.",
                "",
            ]
        )
    lines.append(f"Özet: {'❌' if violation_count else '✅'} {violation_count} ihlal | ✅ {ok_count} uygun personel")
    lines.append("")

    if violation_count:
        lines.append("❌ İhlaller")
        for evaluation in evaluations:
            if not evaluation.violations:
                continue
            extension_text = f" ({evaluation.extension})" if evaluation.extension else ""
            lines.append(f"👤 {evaluation.name}{extension_text}")
            for violation in evaluation.violations:
                lines.append(f"   • {violation}")
        lines.append("")

    ok_people = [evaluation for evaluation in evaluations if not evaluation.violations]
    if ok_people:
        lines.append("✅ Uygun Personeller")
        for evaluation in ok_people:
            extension_text = f" ({evaluation.extension})" if evaluation.extension else ""
            lines.append(f"   • {evaluation.name}{extension_text} - {len(evaluation.calls)} çağrı")

    if not evaluations:
        lines.append("⚠️ Kontrol edilecek personel veya çağrı kaydı bulunamadı.")

    return "\n".join(lines)


def _rules_summary(rules: DepartmentRules) -> str:
    items = [
        f"mesai başlangıcı {_format_optional_time(rules.work_start_time)}",
        f"max bekleme {_format_optional_minutes(rules.max_call_gap_minutes)}",
        f"mola öncesi bırakma {_format_optional_time(rules.pre_break_leave_time)}",
        f"mola {_format_optional_time(rules.break_start_time)}-{_format_optional_time(rules.break_end_time)}",
        f"mola sonrası başlangıç {_format_optional_time(rules.post_break_start_time)}",
        f"mesai sonu {_format_optional_time(rules.work_end_time)}",
    ]
    return ", ".join(items)


def _format_optional_time(value) -> str:
    return format_time(value) if value else "kapalı"


def _format_optional_minutes(value: int | None) -> str:
    return f"{value} dk" if value is not None else "kapalı"


def _call_count_text(raw_call_count: int, processed_call_count: int | None) -> str:
    if processed_call_count is None or processed_call_count == raw_call_count:
        return f"☎️ API görüşme kaydı: {raw_call_count}"
    return f"☎️ API görüşme kaydı: {raw_call_count} | işlenen: {processed_call_count}"


def split_telegram_message(message: str, limit: int = 3900) -> list[str]:
    if len(message) <= limit:
        return [message]
    parts: list[str] = []
    current: list[str] = []
    current_length = 0
    for line in message.splitlines():
        line_length = len(line) + 1
        if current and current_length + line_length > limit:
            parts.append("\n".join(current))
            current = []
            current_length = 0
        current.append(line)
        current_length += line_length
    if current:
        parts.append("\n".join(current))
    return parts