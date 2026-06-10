from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo

from bot.models import DepartmentRules, Personnel
from bot.time_utils import format_time, parse_datetime


@dataclass(frozen=True)
class CallRecord:
    extension_name: str
    extension: str | None
    started_at: datetime
    duration_seconds: int
    event_type: str
    call_id: str | None = None

    @property
    def ended_at(self) -> datetime:
        return self.started_at + timedelta(seconds=max(0, self.duration_seconds))


@dataclass
class PersonnelEvaluation:
    name: str
    extension: str | None
    calls: list[CallRecord] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    leave_periods: list[tuple[datetime, datetime | None]] = field(default_factory=list)


def normalize_calls(raw_calls: list[dict[str, object]], timezone: ZoneInfo) -> list[CallRecord]:
    records: list[CallRecord] = []
    for item in raw_calls:
        event_type = str(_first_value(item, "EventType", "EVENTTYPE") or "").strip()
        if event_type and event_type not in {"1", "2"}:
            continue
        duration = _call_duration_seconds(item)
        if duration <= 0:
            continue
        date_value = _first_value(item, "Date", "CallDate", "ARAMA TARİHİ", "ARAMA TARIHI")
        time_value = _first_value(item, "Time", "CallTime", "ARAMA SAATİ", "ARAMA SAATI")
        extension_name = _clean_extension_name(
            _first_value(item, "ExtensionName", "DAHİLİ ADI", "DAHILI ADI", fuzzy=False) or "Bilinmeyen"
        )
        try:
            started_at = parse_datetime(date_value, time_value, timezone)
        except Exception:
            continue
        records.append(
            CallRecord(
                extension_name=extension_name,
                extension=_clean_optional_text(_first_value(item, "Extension", "Dahili", "DAHİLİ", "DAHILI")),
                started_at=started_at,
                duration_seconds=duration,
                event_type=event_type or "1",
                call_id=_clean_optional_text(_first_value(item, "CallID", "CALLID")),
            )
        )
    return sorted(records, key=lambda record: record.started_at)


def evaluate_department(
    calls: list[CallRecord],
    personnel: list[Personnel],
    rules: DepartmentRules,
    report_date: date,
    now: datetime,
    timezone: ZoneInfo,
    leave_periods: dict[str, list[tuple[datetime, datetime | None]]] | None = None,
    weekly_leave_names: set[str] | None = None,
) -> list[PersonnelEvaluation]:
    weekly_leave_names = weekly_leave_names or set()
    grouped = _group_calls(calls, personnel)
    evaluations: list[PersonnelEvaluation] = []
    if personnel:
        expected_people = list(personnel)
    else:
        expected_people = [
            Personnel(
                id=0,
                department_id=rules.department_id,
                name=name,
                extension=records[0].extension if records else None,
                is_active=True,
            )
            for name, records in grouped.items()
        ]
    if personnel:
        known_names = {person.name.casefold() for person in personnel}
        known_extensions = {person.extension for person in personnel if person.extension}
        for name, records in grouped.items():
            first_record = records[0] if records else None
            if name.casefold() in known_names:
                continue
            if first_record and first_record.extension in known_extensions:
                continue
            expected_people.append(
                Personnel(
                    id=0,
                    department_id=rules.department_id,
                    name=name,
                    extension=first_record.extension if first_record else None,
                    is_active=True,
                )
            )

    for person in expected_people:
        if person.name.casefold() in weekly_leave_names:
            continue
        person_calls = _calls_for_person(person, grouped)
        person_leave_periods = _leave_periods_for_person(person, leave_periods or {})
        person_calls = _filter_calls_by_leave(person_calls, person_leave_periods)
        evaluation = PersonnelEvaluation(
            name=person.name,
            extension=person.extension,
            calls=person_calls,
            leave_periods=person_leave_periods,
        )
        _check_work_start(evaluation, rules, report_date, now, timezone)
        _check_call_gaps(evaluation, rules, report_date, timezone)
        _check_current_idle_gap(evaluation, rules, report_date, now, timezone)
        _check_pre_break_leave(evaluation, rules, report_date, now, timezone)
        _check_post_break_start(evaluation, rules, report_date, now, timezone)
        _check_work_end(evaluation, rules, report_date, now, timezone)
        evaluations.append(evaluation)

    return sorted(evaluations, key=lambda item: item.name.casefold())


def has_violations(evaluations: list[PersonnelEvaluation]) -> bool:
    return any(evaluation.violations for evaluation in evaluations)


def _group_calls(calls: list[CallRecord], personnel: list[Personnel]) -> dict[str, list[CallRecord]]:
    extension_to_name = {
        person.extension.strip(): person.name
        for person in personnel
        if person.extension and person.extension.strip()
    }
    known_names = {person.name.casefold(): person.name for person in personnel}
    grouped: dict[str, list[CallRecord]] = {}
    for call in calls:
        name = extension_to_name.get(call.extension or "")
        if name is None:
            name = known_names.get(call.extension_name.casefold(), call.extension_name)
        grouped.setdefault(name, []).append(call)
    return grouped


def _calls_for_person(person: Personnel, grouped: dict[str, list[CallRecord]]) -> list[CallRecord]:
    if person.name in grouped:
        return grouped[person.name]
    if person.extension:
        for records in grouped.values():
            if records and records[0].extension == person.extension:
                return records
    return []


def _leave_periods_for_person(
    person: Personnel,
    leave_periods: dict[str, list[tuple[datetime, datetime | None]]],
) -> list[tuple[datetime, datetime | None]]:
    return leave_periods.get(person.name.casefold(), [])


def _filter_calls_by_leave(
    calls: list[CallRecord],
    leave_periods: list[tuple[datetime, datetime | None]],
) -> list[CallRecord]:
    if not leave_periods:
        return calls
    filtered: list[CallRecord] = []
    for call in calls:
        if any(_call_overlaps_leave(call, leave_start, leave_end) for leave_start, leave_end in leave_periods):
            continue
        filtered.append(call)
    return filtered


def _call_overlaps_leave(call: CallRecord, leave_start: datetime, leave_end: datetime | None) -> bool:
    effective_leave_end = leave_end or datetime.max.replace(tzinfo=call.started_at.tzinfo)
    return call.started_at < effective_leave_end and call.ended_at > leave_start


def _check_work_start(
    evaluation: PersonnelEvaluation,
    rules: DepartmentRules,
    report_date: date,
    now: datetime,
    timezone: ZoneInfo,
) -> None:
    if rules.work_start_time is None:
        return
    work_start = datetime.combine(report_date, rules.work_start_time, tzinfo=timezone)
    if now < work_start:
        return
    if _datetime_in_leave(work_start, evaluation.leave_periods):
        return
    if not evaluation.calls:
        evaluation.violations.append(f"Mesai başlangıcı ihlali: {format_time(rules.work_start_time)} sonrası çağrı yok")
        return
    first_call = evaluation.calls[0]
    if first_call.started_at > work_start:
        evaluation.violations.append(
            f"Mesai başlangıcı ihlali: ilk çağrı {first_call.started_at.strftime('%H:%M')} (limit {format_time(rules.work_start_time)})"
        )


def _check_call_gaps(
    evaluation: PersonnelEvaluation,
    rules: DepartmentRules,
    report_date: date,
    timezone: ZoneInfo,
) -> None:
    if len(evaluation.calls) < 2 or rules.max_call_gap_minutes is None:
        return
    work_start = datetime.combine(report_date, rules.work_start_time, tzinfo=timezone) if rules.work_start_time else datetime.combine(report_date, time.min, tzinfo=timezone)
    work_end = datetime.combine(report_date, rules.work_end_time, tzinfo=timezone) if rules.work_end_time else datetime.combine(report_date, time.max, tzinfo=timezone)

    for previous, current in zip(evaluation.calls, evaluation.calls[1:]):
        idle_start = previous.ended_at
        idle_end = min(current.started_at, work_end)
        if idle_end <= idle_start:
            continue
        idle_seconds = (idle_end - idle_start).total_seconds()
        idle_seconds -= _ignored_gap_seconds(idle_start, idle_end, rules, report_date, timezone, previous)
        idle_seconds -= _leave_overlap_seconds(idle_start, idle_end, evaluation.leave_periods)
        idle_minutes = int(idle_seconds // 60)
        if idle_minutes > rules.max_call_gap_minutes:
            evaluation.violations.append(
                f"Çağrı arası bekleme ihlali: {previous.started_at.strftime('%H:%M')} - {current.started_at.strftime('%H:%M')} arası {idle_minutes} dk (limit {rules.max_call_gap_minutes} dk)"
            )


def _check_current_idle_gap(
    evaluation: PersonnelEvaluation,
    rules: DepartmentRules,
    report_date: date,
    now: datetime,
    timezone: ZoneInfo,
) -> None:
    if not evaluation.calls or rules.max_call_gap_minutes is None:
        return
    work_start = datetime.combine(report_date, rules.work_start_time, tzinfo=timezone) if rules.work_start_time else datetime.combine(report_date, time.min, tzinfo=timezone)
    work_end = datetime.combine(report_date, rules.work_end_time, tzinfo=timezone) if rules.work_end_time else datetime.combine(report_date, time.max, tzinfo=timezone)
    idle_end = min(now, work_end)
    if idle_end <= work_start:
        return
    last_call = max((call for call in evaluation.calls if call.started_at <= idle_end), default=None, key=lambda call: call.started_at)
    if last_call is None:
        return
    idle_start = max(last_call.ended_at, work_start)
    if idle_end <= idle_start:
        return
    idle_seconds = (idle_end - idle_start).total_seconds()
    idle_seconds -= _ignored_gap_seconds(idle_start, idle_end, rules, report_date, timezone, last_call)
    idle_seconds -= _leave_overlap_seconds(idle_start, idle_end, evaluation.leave_periods)
    idle_minutes = int(idle_seconds // 60)
    if idle_minutes > rules.max_call_gap_minutes:
        evaluation.violations.append(
            f"Güncel bekleme ihlali: son çağrı {last_call.started_at.strftime('%H:%M')} sonrası {idle_minutes} dk bekleme var (limit {rules.max_call_gap_minutes} dk)"
        )


def _check_pre_break_leave(
    evaluation: PersonnelEvaluation,
    rules: DepartmentRules,
    report_date: date,
    now: datetime,
    timezone: ZoneInfo,
) -> None:
    if rules.pre_break_leave_time is None:
        return
    leave_time = datetime.combine(report_date, rules.pre_break_leave_time, tzinfo=timezone)
    if now < leave_time:
        return
    if _datetime_in_leave(leave_time, evaluation.leave_periods):
        return
    latest_allowed_window = datetime.combine(report_date, rules.break_start_time, tzinfo=timezone) if rules.break_start_time else leave_time
    relevant_calls = [call for call in evaluation.calls if call.started_at <= latest_allowed_window]
    has_call_until_leave_time = any(call.started_at >= leave_time or call.ended_at >= leave_time for call in relevant_calls)
    if not has_call_until_leave_time:
        last_call_text = relevant_calls[-1].started_at.strftime("%H:%M") if relevant_calls else "yok"
        evaluation.violations.append(
            f"Mola öncesi çağrı bırakma ihlali: {format_time(rules.pre_break_leave_time)} saatine kadar çağrı yok (son çağrı: {last_call_text})"
        )


def _check_post_break_start(
    evaluation: PersonnelEvaluation,
    rules: DepartmentRules,
    report_date: date,
    now: datetime,
    timezone: ZoneInfo,
) -> None:
    if rules.post_break_start_time is None:
        return
    start_limit = datetime.combine(report_date, rules.post_break_start_time, tzinfo=timezone)
    if now < start_limit:
        return
    if _datetime_in_leave(start_limit, evaluation.leave_periods):
        return
    break_end = datetime.combine(report_date, rules.break_end_time, tzinfo=timezone) if rules.break_end_time else start_limit
    calls_after_break = [
        call
        for call in evaluation.calls
        if call.started_at >= break_end or call.ended_at >= break_end
    ]
    if not calls_after_break:
        evaluation.violations.append(
            f"Mola sonrası çağrı başlangıç ihlali: {format_time(rules.post_break_start_time)} saatine kadar çağrı yok"
        )
        return
    first_call = calls_after_break[0]
    if first_call.started_at > start_limit:
        evaluation.violations.append(
            f"Mola sonrası çağrı başlangıç ihlali: ilk çağrı {first_call.started_at.strftime('%H:%M')} (limit {format_time(rules.post_break_start_time)})"
        )


def _check_work_end(
    evaluation: PersonnelEvaluation,
    rules: DepartmentRules,
    report_date: date,
    now: datetime,
    timezone: ZoneInfo,
) -> None:
    if rules.work_end_time is None:
        return
    work_end = datetime.combine(report_date, rules.work_end_time, tzinfo=timezone)
    if now < work_end:
        return
    if _datetime_in_leave(work_end, evaluation.leave_periods):
        return
    has_call_at_or_after_end = any(call.started_at >= work_end or call.ended_at >= work_end for call in evaluation.calls)
    if not has_call_at_or_after_end:
        last_call_text = evaluation.calls[-1].started_at.strftime("%H:%M") if evaluation.calls else "yok"
        evaluation.violations.append(
            f"Mesai bitişi ihlali: {format_time(rules.work_end_time)} ve sonrasında çağrı yok (son çağrı: {last_call_text})"
        )


def _overlap_seconds(start: datetime, end: datetime, other_start: datetime, other_end: datetime) -> float:
    overlap_start = max(start, other_start)
    overlap_end = min(end, other_end)
    if overlap_end <= overlap_start:
        return 0.0
    return (overlap_end - overlap_start).total_seconds()


def _leave_overlap_seconds(
    start: datetime,
    end: datetime,
    leave_periods: list[tuple[datetime, datetime | None]],
) -> float:
    total = 0.0
    for leave_start, leave_end in leave_periods:
        effective_leave_end = leave_end or end
        total += _overlap_seconds(start, end, leave_start, effective_leave_end)
    return total


def _datetime_in_leave(
    value: datetime,
    leave_periods: list[tuple[datetime, datetime | None]],
) -> bool:
    for leave_start, leave_end in leave_periods:
        effective_leave_end = leave_end or datetime.max.replace(tzinfo=value.tzinfo)
        if leave_start <= value <= effective_leave_end:
            return True
    return False


def _break_interval(
    rules: DepartmentRules,
    report_date: date,
    timezone: ZoneInfo,
) -> tuple[datetime | None, datetime | None]:
    if rules.break_start_time is None or rules.break_end_time is None:
        return None, None
    return (
        datetime.combine(report_date, rules.break_start_time, tzinfo=timezone),
        datetime.combine(report_date, rules.break_end_time, tzinfo=timezone),
    )


def _ignored_gap_seconds(
    start: datetime,
    end: datetime,
    rules: DepartmentRules,
    report_date: date,
    timezone: ZoneInfo,
    previous_call: CallRecord,
) -> float:
    ignored_seconds = 0.0
    intervals: list[tuple[datetime, datetime]] = []
    if rules.pre_break_leave_time and rules.break_start_time:
        intervals.append(
            (
                datetime.combine(report_date, rules.pre_break_leave_time, tzinfo=timezone),
                datetime.combine(report_date, rules.break_start_time, tzinfo=timezone),
            )
        )
    if rules.break_start_time and rules.break_end_time:
        intervals.append(
            (
                datetime.combine(report_date, rules.break_start_time, tzinfo=timezone),
                datetime.combine(report_date, rules.break_end_time, tzinfo=timezone),
            )
        )
    if rules.break_end_time and rules.post_break_start_time:
        break_end = datetime.combine(report_date, rules.break_end_time, tzinfo=timezone)
        post_break_start = datetime.combine(report_date, rules.post_break_start_time, tzinfo=timezone)
        if previous_call.started_at < break_end and end > break_end:
            intervals.append((break_end, post_break_start))
    for interval_start, interval_end in intervals:
        ignored_seconds += _overlap_seconds(start, end, interval_start, interval_end)
    return ignored_seconds


def _to_int(value: object) -> int:
    try:
        return int(float(str(value or "0").replace(",", ".")))
    except ValueError:
        return 0


def _first_value(item: dict[str, object], *keys: str, fuzzy: bool = True) -> object | None:
    casefolded = {str(key).strip().casefold(): value for key, value in item.items()}
    normalized = {_normalize_key(key): value for key, value in item.items()}
    for key in keys:
        value = item.get(key)
        if value is None:
            value = casefolded.get(key.casefold())
        if value is None:
            value = normalized.get(_normalize_key(key))
        if value is None and fuzzy:
            value = _fuzzy_value(normalized, _normalize_key(key))
        if value not in (None, ""):
            return value
    return None


def _call_duration_seconds(item: dict[str, object]) -> int:
    conversation_seconds = _duration_to_seconds(
        _first_value(item, "CallTimeSecond", "CALLTIMESECOND", "KONUŞMA SÜRESİ", "KONUSMA SURESI")
    )
    ring_seconds = _duration_to_seconds(
        _first_value(item, "RingTimeSecond", "RINGTIMESECOND", "ÇALDIRMA SÜRESİ", "CALDIRMA SURESI")
    )
    return conversation_seconds if conversation_seconds > 0 else ring_seconds


def _duration_to_seconds(value: object) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    if ":" not in text:
        return _to_int(text)
    parts = text.split(":")
    if len(parts) not in (2, 3):
        return 0
    try:
        values = [int(float(part.replace(",", "."))) for part in parts]
    except ValueError:
        return 0
    if len(values) == 2:
        minutes, seconds = values
        return minutes * 60 + seconds
    hours, minutes, seconds = values
    return hours * 3600 + minutes * 60 + seconds


def _clean_extension_name(value: object) -> str:
    text = str(value or "").strip()
    if " -" in text:
        text = text.split(" -", 1)[0].strip()
    return text or "Bilinmeyen"


def _clean_optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_key(value: object) -> str:
    replacements = str.maketrans(
        {
            "ç": "c",
            "Ç": "c",
            "ğ": "g",
            "Ğ": "g",
            "ı": "i",
            "I": "i",
            "İ": "i",
            "ö": "o",
            "Ö": "o",
            "ş": "s",
            "Ş": "s",
            "ü": "u",
            "Ü": "u",
        }
    )
    text = str(value).translate(replacements).casefold()
    return "".join(character for character in text if character.isalnum())


def _fuzzy_value(normalized: dict[str, object], target: str) -> object | None:
    if len(target) < 6:
        return None
    best_value: object | None = None
    best_score = 0.0
    for key, value in normalized.items():
        if not key:
            continue
        if target in key:
            return value
        if len(key) >= 6:
            score = SequenceMatcher(None, key, target).ratio()
            if score >= 0.78 and score > best_score:
                best_value = value
                best_score = score
    return best_value