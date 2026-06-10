from dataclasses import dataclass
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from bot.time_utils import parse_hhmm


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    invekto_api_url: str
    timezone_name: str
    admin_user_ids: set[int]
    allowed_group_names: set[str]
    database_path: str
    report_interval_minutes: int
    request_timeout_seconds: int
    scheduler_start_time: object
    scheduler_end_time: object

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)


def _parse_admin_user_ids(value: str) -> set[int]:
    ids: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if item:
            ids.add(int(item))
    return ids


def _parse_group_names(value: str) -> set[str]:
    names: set[str] = set()
    for item in value.split(","):
        item = item.strip().casefold()
        if item:
            names.add(item)
    return names


def load_config() -> Config:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN env değeri zorunludur.")

    database_path = os.getenv("DATABASE_PATH", "data/bot.sqlite3").strip()
    parent = Path(database_path).parent
    if str(parent) and str(parent) != ".":
        parent.mkdir(parents=True, exist_ok=True)

    return Config(
        telegram_bot_token=token,
        invekto_api_url=os.getenv(
            "INVEKTO_API_URL",
            "https://app.invekto.com/invekto/pbxreport",
        ).strip(),
        timezone_name=os.getenv("TIMEZONE", "Europe/Istanbul").strip(),
        admin_user_ids=_parse_admin_user_ids(os.getenv("ADMIN_USER_IDS", "")),
        allowed_group_names=_parse_group_names(os.getenv("ALLOWED_GROUP_NAMES", "")),
        database_path=database_path,
        report_interval_minutes=int(os.getenv("REPORT_INTERVAL_MINUTES", "60")),
        request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "60")),
        scheduler_start_time=parse_hhmm(os.getenv("SCHEDULER_START_TIME", "11:30")),
        scheduler_end_time=parse_hhmm(os.getenv("SCHEDULER_END_TIME", "19:00")),
    )