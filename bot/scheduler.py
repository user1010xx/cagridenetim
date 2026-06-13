from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging

from telegram.ext import Application

from bot.config import Config
from bot.database import Database
from bot.invekto_client import InvektoClient
from bot.reporting import split_telegram_message
from bot.service import generate_department_report_payload


logger = logging.getLogger(__name__)
DEPARTMENT_REPORT_DELAY_SECONDS = 90


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
    for index, department in enumerate(departments):
        report = None
        try:
            if database.is_department_weekly_leave(department.id, now.weekday(), now.date().isoformat()):
                logger.info("Departman haftalık izinli, zamanlanmış rapor atlandı: %s", department.name)
                continue
            if not database.get_rules(department.id).is_configured:
                logger.info("Departman kuralları tanımlı değil, zamanlanmış rapor atlandı: %s", department.name)
                continue
            report = await generate_department_report_payload(
                database,
                client,
                department.id,
                now.date(),
                now,
                suppress_notified=True,
            )
            chat_id = report.chat_id
            message = report.message
        except Exception as exc:
            chat_id = department.telegram_chat_id
            message = f"❌ {department.name} zamanlanmış raporu alınamadı: {exc}"
        try:
            if report is not None and not report.should_send:
                logger.info("Yeni ihlal yok, zamanlanmış rapor gönderilmedi: %s", department.name)
                continue
            for part in split_telegram_message(message):
                await _send_message_with_retry(application, chat_id, part)
            if report is not None and report.notification_violations:
                database.mark_notified_violations(department.id, now.date().isoformat(), report.notification_violations)
        except Exception:
            logger.exception("Zamanlanmış rapor gönderilemedi: %s", department.name)
        if _should_wait_before_next_department(index, len(departments)):
            await asyncio.sleep(DEPARTMENT_REPORT_DELAY_SECONDS)


async def _send_message_with_retry(application: Application, chat_id: str, text: str) -> None:
    delays = (0, 1, 3)
    last_error: Exception | None = None
    for delay in delays:
        if delay:
            await asyncio.sleep(delay)
        try:
            await application.bot.send_message(chat_id=chat_id, text=text)
            return
        except Exception as exc:
            last_error = exc
            logger.warning("Telegram mesaj parçası gönderilemedi, tekrar deneniyor.", exc_info=True)
    if last_error is not None:
        raise last_error


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


def _should_wait_before_next_department(index: int, department_count: int) -> bool:
    return index < department_count - 1