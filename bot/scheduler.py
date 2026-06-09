from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging

from telegram.ext import Application

from bot.config import Config
from bot.database import Database
from bot.invekto_client import InvektoClient
from bot.reporting import split_telegram_message
from bot.service import generate_department_report


logger = logging.getLogger(__name__)


async def run_scheduler(application: Application) -> None:
    config: Config = application.bot_data["config"]
    while True:
        await asyncio.sleep(_seconds_until_next_run(config))
        try:
            await send_scheduled_reports(application)
        except Exception:
            logger.exception("Zamanlanmış rapor döngüsünde beklenmeyen hata oluştu.")


async def send_scheduled_reports(application: Application) -> None:
    config: Config = application.bot_data["config"]
    database: Database = application.bot_data["database"]
    client: InvektoClient = application.bot_data["client"]
    now = datetime.now(config.timezone)
    if not _is_within_report_window(config, now):
        logger.info("Zamanlanmış rapor saati dışında: %s", now.strftime("%H:%M"))
        return
    departments = database.list_departments(only_active=True)
    for department in departments:
        try:
            chat_id, message = await generate_department_report(database, client, department.id, now.date(), now)
        except Exception as exc:
            chat_id = department.telegram_chat_id
            message = f"❌ {department.name} zamanlanmış raporu alınamadı: {exc}"
        try:
            for part in split_telegram_message(message):
                await application.bot.send_message(chat_id=chat_id, text=part)
        except Exception:
            logger.exception("Zamanlanmış rapor gönderilemedi: %s", department.name)


def _seconds_until_next_run(config: Config) -> float:
    now = datetime.now(config.timezone)
    if config.report_interval_minutes == 60:
        next_run = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    else:
        next_run = now + timedelta(minutes=config.report_interval_minutes)
    return max(1.0, (next_run - now).total_seconds())


def _is_within_report_window(config: Config, now: datetime) -> bool:
    current_time = now.time()
    return config.scheduler_start_time <= current_time <= config.scheduler_end_time