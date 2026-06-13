from __future__ import annotations

from datetime import date, timedelta
from typing import Sequence

from bot.models import Personnel


def find_personnel_by_name(personnel: Sequence[Personnel], name: str) -> Personnel | None:
    normalized = name.strip().casefold()
    for person in personnel:
        if person.name.casefold() == normalized:
            return person
    return None


def date_for_weekday_in_current_week(today: date, weekday: int) -> date:
    week_start = today - timedelta(days=today.weekday())
    return week_start + timedelta(days=weekday)