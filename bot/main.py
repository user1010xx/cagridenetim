from __future__ import annotations

import asyncio
import logging

from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, filters

from bot.config import load_config
from bot.database import Database
from bot.department_handlers import (
    chatayarla_department,
    chatayarla_start,
    chatayarla_value,
    companycodeayarla_department,
    companycodeayarla_start,
    companycodeayarla_value,
    departman_aktif,
    departman_listele,
    departman_pasif,
    departman_sil_identifier,
    departman_sil_start,
    departmanekle_company_code,
    departmanekle_name,
    departmanekle_start,
)
from bot.handlers import (
    CHAT_DEPARTMENT,
    CHAT_VALUE,
    COMPANY_CODE_DEPARTMENT,
    COMPANY_CODE_VALUE,
    DEPARTMENT_ADD_COMPANY_CODE,
    DEPARTMENT_ADD_NAME,
    DEPARTMENT_DELETE_IDENTIFIER,
    LEAVE_CANCEL_DEPARTMENT,
    LEAVE_CANCEL_PERSONNEL,
    LEAVE_DEPARTMENT,
    LEAVE_PERSONNEL,
    PERSONNEL_ADD_DEPARTMENT,
    PERSONNEL_ADD_EXTENSION,
    PERSONNEL_ADD_NAME,
    PERSONNEL_BULK_FILE,
    PERSONNEL_DELETE_DEPARTMENT,
    PERSONNEL_DELETE_NAME,
    RESPONSIBLE_ADD_DEPARTMENT,
    RESPONSIBLE_ADD_USERNAME,
    RESPONSIBLE_DELETE_DEPARTMENT,
    RESPONSIBLE_DELETE_USERNAME,
    RESPONSIBLE_LIST_DEPARTMENT,
    chat_id,
    kimim,
    kuralayarla_break_interval,
    kuralayarla_cancel,
    kuralayarla_department,
    kuralayarla_max_gap,
    kuralayarla_post_break_start,
    kuralayarla_pre_break_leave,
    kuralayarla_start,
    kuralayarla_work_end,
    kuralayarla_work_start,
    sorumluekle_department,
    sorumluekle_start,
    sorumluekle_username,
    sorumlulistele_department,
    sorumlulistele_start,
    sorumlusil_department,
    sorumlusil_start,
    sorumlusil_username,
    RULE_BREAK_INTERVAL,
    RULE_DEPARTMENT,
    RULE_MAX_GAP,
    RULE_POST_BREAK_START,
    RULE_PRE_BREAK_LEAVE,
    RULE_WORK_END,
    RULE_WORK_START,
    WEEKLY_LEAVE_CANCEL_DAY,
    WEEKLY_LEAVE_CANCEL_DEPARTMENT,
    WEEKLY_LEAVE_DAY,
    WEEKLY_LEAVE_DEPARTMENT,
    start,
    unknown,
)
from bot.leave_handlers import (
    haftalikizin_day,
    haftalikizin_department,
    haftalikizin_start,
    haftalikizinduzenle_start,
    haftalikiziniptal_day,
    haftalikiziniptal_department,
    haftalikiziniptal_start,
    izin_department,
    izin_personnel,
    izin_start,
    iziniptal_department,
    iziniptal_personnel,
    iziniptal_start,
    izinlistele,
)
from bot.personnel_handlers import (
    personel_listele,
    personel_sil_department,
    personel_sil_name,
    personel_sil_start,
    personelekle_department,
    personelekle_extension,
    personelekle_name,
    personelekle_start,
    personeltopluekle_file,
    personeltopluekle_start,
)
from bot.report_handlers import kontrolinvekto, kurallistele, rapor
from bot.invekto_client import InvektoClient
from bot.scheduler import run_scheduler


logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


async def post_init(application: Application) -> None:
    application.bot_data["scheduler_task"] = asyncio.create_task(
        run_scheduler(application),
        name="hourly-report-scheduler",
    )


def build_application() -> Application:
    config = load_config()
    database = Database(config.database_path)
    client = InvektoClient(config.invekto_api_url, config.request_timeout_seconds)
    application = Application.builder().token(config.telegram_bot_token).post_init(post_init).build()
    application.bot_data["config"] = config
    application.bot_data["database"] = database
    application.bot_data["client"] = client

    application.add_handler(CommandHandler(["start", "help"], start))
    application.add_handler(CommandHandler("chat_id", chat_id))
    application.add_handler(CommandHandler("kimim", kimim))
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler(["departmanekle", "departman_ekle"], departmanekle_start)],
            states={
                DEPARTMENT_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, departmanekle_name)],
                DEPARTMENT_ADD_COMPANY_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, departmanekle_company_code)],
            },
            fallbacks=[CommandHandler("iptal", kuralayarla_cancel)],
        )
    )
    application.add_handler(CommandHandler("departman_listele", departman_listele))
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("departman_sil", departman_sil_start)],
            states={
                DEPARTMENT_DELETE_IDENTIFIER: [MessageHandler(filters.TEXT & ~filters.COMMAND, departman_sil_identifier)],
            },
            fallbacks=[CommandHandler("iptal", kuralayarla_cancel)],
        )
    )
    application.add_handler(CommandHandler("departman_aktif", departman_aktif))
    application.add_handler(CommandHandler("departman_pasif", departman_pasif))
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler(["companycodeayarla", "companycode_ayarla"], companycodeayarla_start)],
            states={
                COMPANY_CODE_DEPARTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, companycodeayarla_department)],
                COMPANY_CODE_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, companycodeayarla_value)],
            },
            fallbacks=[CommandHandler("iptal", kuralayarla_cancel)],
        )
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler(["chatayarla", "chat_ayarla"], chatayarla_start)],
            states={
                CHAT_DEPARTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, chatayarla_department)],
                CHAT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, chatayarla_value)],
            },
            fallbacks=[CommandHandler("iptal", kuralayarla_cancel)],
        )
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler(["kuralayarla", "kural_ayarla"], kuralayarla_start)],
            states={
                RULE_DEPARTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, kuralayarla_department)],
                RULE_WORK_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, kuralayarla_work_start)],
                RULE_MAX_GAP: [MessageHandler(filters.TEXT & ~filters.COMMAND, kuralayarla_max_gap)],
                RULE_PRE_BREAK_LEAVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, kuralayarla_pre_break_leave)],
                RULE_BREAK_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, kuralayarla_break_interval)],
                RULE_POST_BREAK_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, kuralayarla_post_break_start)],
                RULE_WORK_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, kuralayarla_work_end)],
            },
            fallbacks=[CommandHandler("iptal", kuralayarla_cancel)],
        )
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler(["personelekle", "personel_ekle"], personelekle_start)],
            states={
                PERSONNEL_ADD_DEPARTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, personelekle_department)],
                PERSONNEL_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, personelekle_name)],
                PERSONNEL_ADD_EXTENSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, personelekle_extension)],
            },
            fallbacks=[CommandHandler("iptal", kuralayarla_cancel)],
        )
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler(["personeltopluekle", "personel_toplu_ekle"], personeltopluekle_start)],
            states={
                PERSONNEL_BULK_FILE: [MessageHandler(~filters.COMMAND, personeltopluekle_file)],
            },
            fallbacks=[CommandHandler("iptal", kuralayarla_cancel)],
        )
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("izin", izin_start)],
            states={
                LEAVE_DEPARTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, izin_department)],
                LEAVE_PERSONNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, izin_personnel)],
            },
            fallbacks=[CommandHandler("iptal", kuralayarla_cancel)],
        )
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("iziniptal", iziniptal_start)],
            states={
                LEAVE_CANCEL_DEPARTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, iziniptal_department)],
                LEAVE_CANCEL_PERSONNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, iziniptal_personnel)],
            },
            fallbacks=[CommandHandler("iptal", kuralayarla_cancel)],
        )
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("sorumluekle", sorumluekle_start)],
            states={
                RESPONSIBLE_ADD_DEPARTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, sorumluekle_department)],
                RESPONSIBLE_ADD_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, sorumluekle_username)],
            },
            fallbacks=[CommandHandler("iptal", kuralayarla_cancel)],
        )
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("sorumlusil", sorumlusil_start)],
            states={
                RESPONSIBLE_DELETE_DEPARTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, sorumlusil_department)],
                RESPONSIBLE_DELETE_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, sorumlusil_username)],
            },
            fallbacks=[CommandHandler("iptal", kuralayarla_cancel)],
        )
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("sorumlulistele", sorumlulistele_start)],
            states={
                RESPONSIBLE_LIST_DEPARTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, sorumlulistele_department)],
            },
            fallbacks=[CommandHandler("iptal", kuralayarla_cancel)],
        )
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler(["haftalikizin", "haftalikizinduzenle"], haftalikizin_start)],
            states={
                WEEKLY_LEAVE_DEPARTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, haftalikizin_department)],
                WEEKLY_LEAVE_DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, haftalikizin_day)],
            },
            fallbacks=[CommandHandler("iptal", kuralayarla_cancel)],
        )
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("haftalikiziniptal", haftalikiziniptal_start)],
            states={
                WEEKLY_LEAVE_CANCEL_DEPARTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, haftalikiziniptal_department)],
                WEEKLY_LEAVE_CANCEL_DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, haftalikiziniptal_day)],
            },
            fallbacks=[CommandHandler("iptal", kuralayarla_cancel)],
        )
    )
    application.add_handler(CommandHandler("personel_listele", personel_listele))
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("personel_sil", personel_sil_start)],
            states={
                PERSONNEL_DELETE_DEPARTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, personel_sil_department)],
                PERSONNEL_DELETE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, personel_sil_name)],
            },
            fallbacks=[CommandHandler("iptal", kuralayarla_cancel)],
        )
    )
    application.add_handler(CommandHandler("izinlistele", izinlistele))
    application.add_handler(CommandHandler("kurallistele", kurallistele))
    application.add_handler(CommandHandler("rapor", rapor))
    application.add_handler(CommandHandler("kontrolinvekto", kontrolinvekto))
    application.add_handler(MessageHandler(filters.COMMAND, unknown))
    return application


def main() -> None:
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    application = build_application()
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()

