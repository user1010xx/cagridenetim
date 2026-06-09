from datetime import date, datetime, time
from zoneinfo import ZoneInfo


DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d")
TIME_FORMATS = ("%H:%M:%S", "%H:%M")


def parse_date(value: object) -> date:
    text = str(value).strip()
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            pass
    return datetime.fromisoformat(text).date()


def parse_time(value: object) -> time:
    text = str(value).strip()
    for time_format in TIME_FORMATS:
        try:
            return datetime.strptime(text, time_format).time()
        except ValueError:
            pass
    return datetime.fromisoformat(text).time()


def parse_datetime(date_value: object, time_value: object, timezone: ZoneInfo) -> datetime:
    return datetime.combine(parse_date(date_value), parse_time(time_value), tzinfo=timezone)


def format_time(value: time) -> str:
    return value.strftime("%H:%M")


def parse_hhmm(value: str) -> time:
    return parse_time(value)