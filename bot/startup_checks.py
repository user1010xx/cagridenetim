from __future__ import annotations

import logging
import os
from pathlib import Path


logger = logging.getLogger(__name__)


def validate_runtime_setup(database_path: str) -> list[str]:
    warnings: list[str] = []
    if not os.getenv("ADMIN_USER_IDS", "").strip():
        warnings.append("ADMIN_USER_IDS tanımlı değil. İlk kurulum için en az bir admin Telegram kullanıcı ID giriniz.")
    if not os.getenv("ALLOWED_GROUP_NAMES", "").strip():
        warnings.append("ALLOWED_GROUP_NAMES boş. Kurulum tamamlanana kadar sadece admin özel sohbet ve kayıtlı departman grupları kullanılabilir.")
    if _looks_like_ephemeral_database_path(database_path):
        warnings.append(
            f"Veritabanı yolu kalıcı görünmüyor: {database_path}. "
            "Railway kullanıyorsanız /data volume mount edip DATABASE_PATH=/data/bot.sqlite3 ayarlayın."
        )
    for warning in warnings:
        logger.warning(warning)
    return warnings


def _looks_like_ephemeral_database_path(database_path: str) -> bool:
    normalized = Path(database_path)
    if normalized.is_absolute() and str(normalized).startswith("/data"):
        return False
    if os.getenv("RAILWAY_ENVIRONMENT"):
        return str(normalized) in {"data/bot.sqlite3", "bot.sqlite3"} or not normalized.is_absolute()
    return False