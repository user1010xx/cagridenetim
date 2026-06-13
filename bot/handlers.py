from __future__ import annotations

from datetime import datetime
from itertools import count
from typing import Callable, Sequence
from urllib.error import HTTPError, URLError

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from bot.config import Config
from bot.database import Database
from bot.invekto_client import InvektoClient
from bot.models import Department, Personnel
from bot.personnel_import import PersonnelImportRow, parse_personnel_workbook
from bot.reporting import split_telegram_message
from bot.service import generate_department_report
from bot.time_utils import parse_hhmm


_STATE_COUNTER = count()
RULE_DEPARTMENT = next(_STATE_COUNTER)
RULE_WORK_START = next(_STATE_COUNTER)
RULE_MAX_GAP = next(_STATE_COUNTER)
RULE_PRE_BREAK_LEAVE = next(_STATE_COUNTER)
RULE_BREAK_INTERVAL = next(_STATE_COUNTER)
RULE_POST_BREAK_START = next(_STATE_COUNTER)
RULE_WORK_END = next(_STATE_COUNTER)
DEPARTMENT_ADD_NAME = next(_STATE_COUNTER)
DEPARTMENT_ADD_COMPANY_CODE = next(_STATE_COUNTER)
COMPANY_CODE_DEPARTMENT = next(_STATE_COUNTER)
COMPANY_CODE_VALUE = next(_STATE_COUNTER)
CHAT_DEPARTMENT = next(_STATE_COUNTER)
CHAT_VALUE = next(_STATE_COUNTER)
PERSONNEL_ADD_DEPARTMENT = next(_STATE_COUNTER)
PERSONNEL_ADD_NAME = next(_STATE_COUNTER)
PERSONNEL_ADD_EXTENSION = next(_STATE_COUNTER)
PERSONNEL_BULK_FILE = next(_STATE_COUNTER)
LEAVE_DEPARTMENT = next(_STATE_COUNTER)
LEAVE_PERSONNEL = next(_STATE_COUNTER)
LEAVE_CANCEL_DEPARTMENT = next(_STATE_COUNTER)
LEAVE_CANCEL_PERSONNEL = next(_STATE_COUNTER)
RESPONSIBLE_ADD_DEPARTMENT = next(_STATE_COUNTER)
RESPONSIBLE_ADD_USERNAME = next(_STATE_COUNTER)
RESPONSIBLE_DELETE_DEPARTMENT = next(_STATE_COUNTER)
RESPONSIBLE_DELETE_USERNAME = next(_STATE_COUNTER)
RESPONSIBLE_LIST_DEPARTMENT = next(_STATE_COUNTER)
WEEKLY_LEAVE_DEPARTMENT = next(_STATE_COUNTER)
WEEKLY_LEAVE_PERSONNEL = next(_STATE_COUNTER)
WEEKLY_LEAVE_DAY = next(_STATE_COUNTER)
WEEKLY_LEAVE_CANCEL_DEPARTMENT = next(_STATE_COUNTER)
WEEKLY_LEAVE_CANCEL_PERSONNEL = next(_STATE_COUNTER)
WEEKLY_LEAVE_CANCEL_DAY = next(_STATE_COUNTER)
DEPARTMENT_DELETE_IDENTIFIER = next(_STATE_COUNTER)


WEEKDAY_NAMES = {
    "pazartesi": 0,
    "salı": 1,
    "sali": 1,
    "çarşamba": 2,
    "carsamba": 2,
    "perşembe": 3,
    "persembe": 3,
    "cuma": 4,
    "cumartesi": 5,
    "pazar": 6,
}

WEEKDAY_LABELS = {
    0: "Pazartesi",
    1: "Salı",
    2: "Çarşamba",
    3: "Perşembe",
    4: "Cuma",
    5: "Cumartesi",
    6: "Pazar",
}


HELP_TEXT = """
🤖 Invekto Kalite Kontrol Botu

Temel komutlar:
/chat_id - Bu sohbetin chat ID değerini gösterir
/kimim - Telegram kullanıcı ID değerini gösterir
/departmanekle - Departmanı adım adım ekler
/departman_listele
/departman_sil DepartmanAdı veya ID
/departman_aktif DepartmanAdı veya ID
/departman_pasif DepartmanAdı veya ID
/companycodeayarla - CompanyCode değerini adım adım günceller
/chatayarla - Rapor chat ID değerini adım adım günceller
/kuralayarla - Kuralları adım adım tanımlar
/personelekle - Personeli adım adım ekler
/personeltopluekle - Excel dosyasıyla toplu personel ekler
/personel_listele Departman
/personel_sil PersonelID
/rapor DepartmanAdı veya ID - Tek departman kontrol eder
/kontrolinvekto DepartmanAdı veya ID - Invekto erişimini test eder
/izin - Personeli geçici izinli yapar
/iziniptal - Geçici izni bitirir
/haftalikizin - Haftalık izin ekler
/haftalikizinduzenle - Haftalık izni yeniden düzenler
/haftalikiziniptal - Haftalık izni kaldırır
/sorumluekle - Departman sorumlusu ekler
/sorumlusil - Departman sorumlusu siler
/sorumlulistele - Departman sorumlularını listeler

Not: Departman ve kural bilgileri bot veritabanında tutulur; Railway env içine tek tek yazılmaz.
""".strip()


def admin_only(handler: Callable) -> Callable:
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        config: Config = context.application.bot_data["config"]
        user = update.effective_user
        is_admin = user is not None and user.id in config.admin_user_ids
        if not is_admin:
            await update.effective_message.reply_text("Bu komut için yetkiniz yok.")
            return ConversationHandler.END
        if not _is_allowed(update, context):
            await update.effective_message.reply_text("Bu botu bu sohbet içinde kullanma yetkiniz yok.")
            return ConversationHandler.END
        return await handler(update, context)

    return wrapper


def allowed_only(handler: Callable) -> Callable:
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not _is_allowed(update, context):
            await update.effective_message.reply_text("Bu botu kullanma yetkiniz yok.")
            return
        return await handler(update, context)

    return wrapper


def _is_allowed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    config: Config = context.application.bot_data["config"]
    chat = update.effective_chat
    user = update.effective_user
    if chat is None:
        return False
    if user is not None and user.id in config.admin_user_ids:
        return True
    if chat.type == "private":
        return False
    title = (chat.title or "").strip().casefold()
    if title in config.allowed_group_names:
        return True
    return _is_registered_department_chat(context.application.bot_data.get("database"), chat.id)


def _is_registered_department_chat(database: Database | None, chat_id: int) -> bool:
    if database is None:
        return False
    return any(department.telegram_chat_id == str(chat_id) for department in database.list_departments())


@allowed_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP_TEXT)


@allowed_only
async def chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(f"Chat ID: `{update.effective_chat.id}`", parse_mode=ParseMode.MARKDOWN)


@allowed_only
async def kimim(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        await update.effective_message.reply_text("Kullanıcı bilgisi alınamadı.")
        return
    await update.effective_message.reply_text(f"Kullanıcı ID: `{user.id}`", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def departmanekle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["department_add"] = {}
    await update.effective_message.reply_text("Departman adını giriniz.")
    return DEPARTMENT_ADD_NAME


async def departmanekle_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = _message_text(update)
    if not name:
        await update.effective_message.reply_text("Departman adı boş olamaz. Lütfen departman adını giriniz.")
        return DEPARTMENT_ADD_NAME
    context.user_data["department_add"] = {"name": name}
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text("CompanyCode'u giriniz.")
    return DEPARTMENT_ADD_COMPANY_CODE


async def departmanekle_company_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    setup = context.user_data.get("department_add", {})
    name = setup.get("name")
    company_code = _message_text(update)
    if not name:
        await update.effective_message.reply_text("Departman ekleme oturumu bulunamadı. Lütfen /departmanekle ile tekrar başlayın.")
        return ConversationHandler.END
    if not company_code:
        await update.effective_message.reply_text("CompanyCode boş olamaz. Lütfen CompanyCode'u giriniz.")
        return DEPARTMENT_ADD_COMPANY_CODE
    try:
        department = database.add_department(name, company_code, str(update.effective_chat.id))
    except Exception as exc:
        await update.effective_message.reply_text(f"Departman eklenemedi: {exc}")
        return DEPARTMENT_ADD_COMPANY_CODE
    context.user_data.pop("department_add", None)
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text(f"✅ Departman eklendi: {department.name} (ID: {department.id})")
    return ConversationHandler.END


@allowed_only
async def departman_listele(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    database: Database = context.application.bot_data["database"]
    departments = _departments_visible_in_chat(update, database.list_departments())
    if not departments:
        await update.effective_message.reply_text("Bu sohbete bağlı departman bulunamadı.")
        return
    lines = ["🏢 Departmanlar"]
    for department in departments:
        rules = database.get_rules(department.id)
        status = "aktif" if department.is_active else "pasif"
        rule_text = f"{rules.max_call_gap_minutes} dk" if rules.is_configured else "kural tanımlı değil"
        lines.append(
            f"{department.id}. {department.name} | {status} | code: {department.company_code} | chat: {department.telegram_chat_id} | {rule_text}"
        )
    await update.effective_message.reply_text("\n".join(lines))


def _departments_visible_in_chat(update: Update, departments: list[Department]) -> list[Department]:
    chat = update.effective_chat
    if chat is None:
        return []
    if chat.type == "private":
        return departments
    return [department for department in departments if department.telegram_chat_id == str(chat.id)]


@admin_only
async def departman_sil_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    args = _plain_args(update)
    if args:
        await _delete_or_toggle_department(update, context, "delete", args)
        return ConversationHandler.END
    context.user_data["department_delete"] = {}
    await update.effective_message.reply_text("Departman adı veya ID gönderin.")
    return DEPARTMENT_DELETE_IDENTIFIER


async def departman_sil_identifier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _delete_or_toggle_department(update, context, "delete", _message_text(update))
    context.user_data.pop("department_delete", None)
    return ConversationHandler.END


@admin_only
async def departman_aktif(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _delete_or_toggle_department(update, context, "active")


@admin_only
async def departman_pasif(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _delete_or_toggle_department(update, context, "passive")


@admin_only
async def companycodeayarla_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["company_code_setup"] = {}
    await update.effective_message.reply_text("Departman adını giriniz.")
    return COMPANY_CODE_DEPARTMENT


async def companycodeayarla_department(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    department = database.get_department(_identifier(_message_text(update)))
    if department is None:
        await update.effective_message.reply_text("Departman bulunamadı. Lütfen departman adı veya ID giriniz.")
        return COMPANY_CODE_DEPARTMENT
    context.user_data["company_code_setup"] = {"department": department}
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text("CompanyCode'u giriniz.")
    return COMPANY_CODE_VALUE


async def companycodeayarla_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    setup = context.user_data.get("company_code_setup", {})
    department = setup.get("department")
    company_code = _message_text(update)
    if department is None:
        await update.effective_message.reply_text("CompanyCode ayarlama oturumu bulunamadı. Lütfen /companycodeayarla ile tekrar başlayın.")
        return ConversationHandler.END
    if not company_code:
        await update.effective_message.reply_text("CompanyCode boş olamaz. Lütfen CompanyCode'u giriniz.")
        return COMPANY_CODE_VALUE
    database.update_department_code(department.id, company_code)
    context.user_data.pop("company_code_setup", None)
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text(f"✅ {department.name} için CompanyCode güncellendi.")
    return ConversationHandler.END


@admin_only
async def chatayarla_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["chat_setup"] = {}
    await update.effective_message.reply_text("Departman adını giriniz.")
    return CHAT_DEPARTMENT


async def chatayarla_department(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    department = database.get_department(_identifier(_message_text(update)))
    if department is None:
        await update.effective_message.reply_text("Departman bulunamadı. Lütfen departman adı veya ID giriniz.")
        return CHAT_DEPARTMENT
    context.user_data["chat_setup"] = {"department": department}
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text("Telegram chat ID değerini giriniz. Mevcut sohbet kullanılacaksa buraya yaz yazınız.")
    return CHAT_VALUE


async def chatayarla_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    setup = context.user_data.get("chat_setup", {})
    department = setup.get("department")
    value = _message_text(update)
    if department is None:
        await update.effective_message.reply_text("Chat ayarlama oturumu bulunamadı. Lütfen /chatayarla ile tekrar başlayın.")
        return ConversationHandler.END
    chat_id = str(update.effective_chat.id) if value.casefold() == "buraya yaz" else value
    if not chat_id:
        await update.effective_message.reply_text("Chat ID boş olamaz. Lütfen chat ID değerini giriniz.")
        return CHAT_VALUE
    database.update_department_chat(department.id, chat_id)
    context.user_data.pop("chat_setup", None)
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text(f"✅ {department.name} için Telegram chat ID güncellendi.")
    return ConversationHandler.END


@admin_only
async def kuralayarla_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["rule_setup"] = {}
    await update.effective_message.reply_text("Departman adı giriniz.")
    return RULE_DEPARTMENT


async def kuralayarla_department(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    department_name = _message_text(update)
    department = database.get_department(_identifier(department_name))
    if department is None:
        await update.effective_message.reply_text("Departman bulunamadı. Lütfen departman adı veya ID giriniz.")
        return RULE_DEPARTMENT
    context.user_data["rule_setup"] = {"department": department}
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text("Mesai Başlangıcı en erken çağrı başlama saati giriniz. Bu kural uygulanmayacaksa boş yazınız.")
    return RULE_WORK_START


async def kuralayarla_work_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["rule_setup"]["work_start_time"] = _optional_time_text(_message_text(update))
    except ValueError as exc:
        await update.effective_message.reply_text(str(exc))
        return RULE_WORK_START
    await update.effective_message.reply_text("✅ Kural güncellendi.")
    await update.effective_message.reply_text("Her iki çağrı arası max bekleme süresi giriniz. Bu kural uygulanmayacaksa boş yazınız.")
    return RULE_MAX_GAP


async def kuralayarla_max_gap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = _message_text(update)
    if _is_blank_rule(value):
        context.user_data["rule_setup"]["max_call_gap_minutes"] = None
    else:
        if not value.isdigit() or int(value) <= 0:
            await update.effective_message.reply_text("Lütfen dakika değerini pozitif sayı olarak giriniz veya boş yazınız.")
            return RULE_MAX_GAP
        context.user_data["rule_setup"]["max_call_gap_minutes"] = int(value)
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text("Mola öncesi en erken çağrı bırakma süresi giriniz. Bu kural uygulanmayacaksa boş yazınız.")
    return RULE_PRE_BREAK_LEAVE


async def kuralayarla_pre_break_leave(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["rule_setup"]["pre_break_leave_time"] = _optional_time_text(_message_text(update))
    except ValueError as exc:
        await update.effective_message.reply_text(str(exc))
        return RULE_PRE_BREAK_LEAVE
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text("Departmanın mola saat aralığını giriniz. Örnek: 14:00,15:00. Bu kural uygulanmayacaksa boş yazınız.")
    return RULE_BREAK_INTERVAL


async def kuralayarla_break_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = _message_text(update)
    if _is_blank_rule(value):
        context.user_data["rule_setup"]["break_start_time"] = None
        context.user_data["rule_setup"]["break_end_time"] = None
    else:
        parts = [part.strip() for part in value.split(",")]
        if len(parts) != 2:
            await update.effective_message.reply_text("Lütfen mola aralığını 14:00,15:00 formatında giriniz veya boş yazınız.")
            return RULE_BREAK_INTERVAL
        try:
            parse_hhmm(parts[0])
            parse_hhmm(parts[1])
        except Exception:
            await update.effective_message.reply_text("Saat formatı geçersiz. Örnek: 14:00,15:00")
            return RULE_BREAK_INTERVAL
        context.user_data["rule_setup"]["break_start_time"] = parts[0]
        context.user_data["rule_setup"]["break_end_time"] = parts[1]
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text("Mola sonrası en geç çağrı başlangıç süresini giriniz. Bu kural uygulanmayacaksa boş yazınız.")
    return RULE_POST_BREAK_START


async def kuralayarla_post_break_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["rule_setup"]["post_break_start_time"] = _optional_time_text(_message_text(update))
    except ValueError as exc:
        await update.effective_message.reply_text(str(exc))
        return RULE_POST_BREAK_START
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text("Mesai sonu en erken çağrı bırakma süresini giriniz. Bu kural uygulanmayacaksa boş yazınız.")
    return RULE_WORK_END


async def kuralayarla_work_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    setup = context.user_data.get("rule_setup", {})
    department = setup.get("department")
    if department is None:
        await update.effective_message.reply_text("Kural kurulumu bulunamadı. Lütfen /kuralayarla ile tekrar başlayın.")
        return ConversationHandler.END
    try:
        setup["work_end_time"] = _optional_time_text(_message_text(update))
        database.update_rules(
            department.id,
            setup.get("work_start_time"),
            setup.get("pre_break_leave_time"),
            setup.get("break_start_time"),
            setup.get("break_end_time"),
            setup.get("post_break_start_time"),
            setup.get("work_end_time"),
            setup.get("max_call_gap_minutes"),
        )
    except Exception as exc:
        await update.effective_message.reply_text(f"Kural güncellenemedi: {exc}")
        return RULE_WORK_END
    context.user_data.pop("rule_setup", None)
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text(f"✅ {department.name} departmanı için kurallar kaydedildi.")
    return ConversationHandler.END


async def kuralayarla_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("rule_setup", None)
    context.user_data.pop("department_add", None)
    context.user_data.pop("company_code_setup", None)
    context.user_data.pop("chat_setup", None)
    context.user_data.pop("personnel_add", None)
    for key in (
        "leave_setup",
        "leave_cancel_setup",
        "responsible_add",
        "responsible_delete",
        "responsible_list",
        "weekly_leave",
        "weekly_leave_cancel",
    ):
        context.user_data.pop(key, None)
    await update.effective_message.reply_text("İşlem iptal edildi.")
    return ConversationHandler.END


@admin_only
async def personelekle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["personnel_add"] = {}
    await update.effective_message.reply_text("Departman adını giriniz.")
    return PERSONNEL_ADD_DEPARTMENT


async def personelekle_department(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    department = database.get_department(_identifier(_message_text(update)))
    if department is None:
        await update.effective_message.reply_text("Departman bulunamadı. Lütfen departman adı veya ID giriniz.")
        return PERSONNEL_ADD_DEPARTMENT
    context.user_data["personnel_add"] = {"department": department}
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text("Personel adını giriniz.")
    return PERSONNEL_ADD_NAME


async def personelekle_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = _message_text(update)
    if not name:
        await update.effective_message.reply_text("Personel adı boş olamaz. Lütfen personel adını giriniz.")
        return PERSONNEL_ADD_NAME
    context.user_data["personnel_add"]["name"] = name
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text("Dahili numarasını giriniz. Yoksa boş yazınız.")
    return PERSONNEL_ADD_EXTENSION


async def personelekle_extension(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    setup = context.user_data.get("personnel_add", {})
    department = setup.get("department")
    name = setup.get("name")
    if department is None or not name:
        await update.effective_message.reply_text("Personel ekleme oturumu bulunamadı. Lütfen /personelekle ile tekrar başlayın.")
        return ConversationHandler.END
    value = _message_text(update)
    extension = None if _is_blank_rule(value) else value
    try:
        personnel = database.add_personnel(department.id, name, extension)
    except Exception as exc:
        await update.effective_message.reply_text(f"Personel eklenemedi: {exc}")
        return PERSONNEL_ADD_EXTENSION
    context.user_data.pop("personnel_add", None)
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text(f"✅ Personel eklendi: {personnel.name} (ID: {personnel.id})")
    return ConversationHandler.END


@admin_only
async def personeltopluekle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text("Excel dosyasını gönderiniz. İlk sayfada A departman, B personel adı, C dahili olmalı.")
    return PERSONNEL_BULK_FILE


async def personeltopluekle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    document = update.effective_message.document
    if document is None:
        await update.effective_message.reply_text("Lütfen .xlsx veya .xlsm Excel dosyası gönderiniz.")
        return PERSONNEL_BULK_FILE
    file_name = (document.file_name or "").casefold()
    if not file_name.endswith((".xlsx", ".xlsm")):
        await update.effective_message.reply_text("Lütfen .xlsx veya .xlsm uzantılı Excel dosyası gönderiniz.")
        return PERSONNEL_BULK_FILE
    try:
        telegram_file = await document.get_file()
        content = bytes(await telegram_file.download_as_bytearray())
        rows, errors = parse_personnel_workbook(content)
    except Exception as exc:
        await update.effective_message.reply_text(f"Excel dosyası okunamadı: {exc}")
        return PERSONNEL_BULK_FILE
    if not rows and not errors:
        await update.effective_message.reply_text("Excel dosyasında eklenecek personel bulunamadı.")
        return PERSONNEL_BULK_FILE
    added_count, failed = _import_personnel_rows(database, rows, errors)
    lines = [f"✅ Toplu personel ekleme tamamlandı. Eklenen: {added_count}"]
    if failed:
        lines.append(f"Eklenemeyen: {len(failed)}")
        lines.extend(failed[:30])
        if len(failed) > 30:
            lines.append(f"... {len(failed) - 30} satır daha")
    for message in split_telegram_message("\n".join(lines)):
        await update.effective_message.reply_text(message)
    return ConversationHandler.END


@allowed_only
async def personel_listele(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    database: Database = context.application.bot_data["database"]
    args = _plain_args(update)
    if not args:
        await update.effective_message.reply_text("Kullanım: /personel_listele Departman")
        return
    department = database.get_department(_identifier(args))
    if department is None:
        await update.effective_message.reply_text("Departman bulunamadı.")
        return
    personnel = database.list_personnel(department.id, only_active=False)
    if not personnel:
        await update.effective_message.reply_text("Bu departmanda personel yok.")
        return
    for message in split_telegram_message(_format_personnel_list(department.name, personnel)):
        await update.effective_message.reply_text(message)


@admin_only
async def personel_sil(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    database: Database = context.application.bot_data["database"]
    args = _plain_args(update)
    if not args or not args.isdigit():
        await update.effective_message.reply_text("Kullanım: /personel_sil PersonelID")
        return
    if not database.delete_personnel(int(args)):
        await update.effective_message.reply_text("Personel bulunamadı.")
        return
    await update.effective_message.reply_text("✅ Personel silindi.")


@admin_only
async def izin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["leave_setup"] = {}
    await update.effective_message.reply_text("Departman adını giriniz.")
    return LEAVE_DEPARTMENT


async def izin_department(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    department = database.get_department(_identifier(_message_text(update)))
    if department is None:
        await update.effective_message.reply_text("Departman bulunamadı. Lütfen departman adı veya ID giriniz.")
        return LEAVE_DEPARTMENT
    context.user_data["leave_setup"] = {"department": department}
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text("İzinli personel adını giriniz.")
    return LEAVE_PERSONNEL


async def izin_personnel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    config: Config = context.application.bot_data["config"]
    setup = context.user_data.get("leave_setup", {})
    department = setup.get("department")
    personnel_name = _message_text(update)
    if department is None:
        await update.effective_message.reply_text("İzin oturumu bulunamadı. Lütfen /izin ile tekrar başlayın.")
        return ConversationHandler.END
    database.start_leave(department.id, personnel_name, datetime.now(config.timezone).isoformat())
    context.user_data.pop("leave_setup", None)
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text(f"✅ {personnel_name} izinli olarak işaretlendi.")
    return ConversationHandler.END


@admin_only
async def iziniptal_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["leave_cancel_setup"] = {}
    await update.effective_message.reply_text("Departman adını giriniz.")
    return LEAVE_CANCEL_DEPARTMENT


async def iziniptal_department(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    department = database.get_department(_identifier(_message_text(update)))
    if department is None:
        await update.effective_message.reply_text("Departman bulunamadı. Lütfen departman adı veya ID giriniz.")
        return LEAVE_CANCEL_DEPARTMENT
    context.user_data["leave_cancel_setup"] = {"department": department}
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text("İzni iptal edilecek personel adını giriniz.")
    return LEAVE_CANCEL_PERSONNEL


async def iziniptal_personnel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    config: Config = context.application.bot_data["config"]
    setup = context.user_data.get("leave_cancel_setup", {})
    department = setup.get("department")
    personnel_name = _message_text(update)
    if department is None:
        await update.effective_message.reply_text("İzin iptal oturumu bulunamadı. Lütfen /iziniptal ile tekrar başlayın.")
        return ConversationHandler.END
    if not database.end_leave(department.id, personnel_name, datetime.now(config.timezone).isoformat()):
        await update.effective_message.reply_text("Aktif izin kaydı bulunamadı.")
        return LEAVE_CANCEL_PERSONNEL
    context.user_data.pop("leave_cancel_setup", None)
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text(f"✅ {personnel_name} tekrar kontrole dahil edildi.")
    return ConversationHandler.END


@admin_only
async def sorumluekle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["responsible_add"] = {}
    await update.effective_message.reply_text("Departman adını giriniz.")
    return RESPONSIBLE_ADD_DEPARTMENT


async def sorumluekle_department(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    department = database.get_department(_identifier(_message_text(update)))
    if department is None:
        await update.effective_message.reply_text("Departman bulunamadı. Lütfen departman adı veya ID giriniz.")
        return RESPONSIBLE_ADD_DEPARTMENT
    context.user_data["responsible_add"] = {"department": department}
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text("Sorumlu kişinin Telegram kullanıcı adını giriniz.")
    return RESPONSIBLE_ADD_USERNAME


async def sorumluekle_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    setup = context.user_data.get("responsible_add", {})
    department = setup.get("department")
    username = _message_text(update)
    if department is None:
        await update.effective_message.reply_text("Sorumlu ekleme oturumu bulunamadı. Lütfen /sorumluekle ile tekrar başlayın.")
        return ConversationHandler.END
    try:
        database.add_responsible(department.id, username)
    except ValueError as exc:
        await update.effective_message.reply_text(str(exc))
        return RESPONSIBLE_ADD_USERNAME
    context.user_data.pop("responsible_add", None)
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text(f"✅ @{username.strip().lstrip('@')} sorumlu olarak eklendi.")
    return ConversationHandler.END


@admin_only
async def sorumlusil_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["responsible_delete"] = {}
    await update.effective_message.reply_text("Departman adını giriniz.")
    return RESPONSIBLE_DELETE_DEPARTMENT


async def sorumlusil_department(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    department = database.get_department(_identifier(_message_text(update)))
    if department is None:
        await update.effective_message.reply_text("Departman bulunamadı. Lütfen departman adı veya ID giriniz.")
        return RESPONSIBLE_DELETE_DEPARTMENT
    context.user_data["responsible_delete"] = {"department": department}
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text("Silinecek sorumlunun Telegram kullanıcı adını giriniz.")
    return RESPONSIBLE_DELETE_USERNAME


async def sorumlusil_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    setup = context.user_data.get("responsible_delete", {})
    department = setup.get("department")
    username = _message_text(update)
    if department is None:
        await update.effective_message.reply_text("Sorumlu silme oturumu bulunamadı. Lütfen /sorumlusil ile tekrar başlayın.")
        return ConversationHandler.END
    if not database.delete_responsible(department.id, username):
        await update.effective_message.reply_text("Sorumlu bulunamadı.")
        return RESPONSIBLE_DELETE_USERNAME
    context.user_data.pop("responsible_delete", None)
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text(f"✅ @{username.strip().lstrip('@')} sorumlu listesinden silindi.")
    return ConversationHandler.END


@allowed_only
async def sorumlulistele_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["responsible_list"] = {}
    await update.effective_message.reply_text("Departman adını giriniz.")
    return RESPONSIBLE_LIST_DEPARTMENT


@allowed_only
async def sorumlulistele_department(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    department = database.get_department(_identifier(_message_text(update)))
    if department is None:
        await update.effective_message.reply_text("Departman bulunamadı. Lütfen departman adı veya ID giriniz.")
        return RESPONSIBLE_LIST_DEPARTMENT
    responsibles = database.list_responsibles(department.id)
    context.user_data.pop("responsible_list", None)
    if not responsibles:
        await update.effective_message.reply_text("Bu departmanda sorumlu tanımlı değil.")
        return ConversationHandler.END
    await update.effective_message.reply_text("\n".join([f"👥 {department.name} sorumluları"] + [f"@{item.username}" for item in responsibles]))
    return ConversationHandler.END


@admin_only
async def haftalikizin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["weekly_leave"] = {}
    await update.effective_message.reply_text("Departman adını giriniz.")
    return WEEKLY_LEAVE_DEPARTMENT


async def haftalikizin_department(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    department = database.get_department(_identifier(_message_text(update)))
    if department is None:
        await update.effective_message.reply_text("Departman bulunamadı. Lütfen departman adı veya ID giriniz.")
        return WEEKLY_LEAVE_DEPARTMENT
    context.user_data["weekly_leave"] = {"department": department}
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text("Haftalık izinli personel adını giriniz.")
    return WEEKLY_LEAVE_PERSONNEL


async def haftalikizin_personnel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    personnel_name = _message_text(update)
    if not personnel_name:
        await update.effective_message.reply_text("Personel adı boş olamaz.")
        return WEEKLY_LEAVE_PERSONNEL
    context.user_data["weekly_leave"]["personnel_name"] = personnel_name
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text("Haftalık izin gününü giriniz. Örnek: pazartesi")
    return WEEKLY_LEAVE_DAY


async def haftalikizin_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    setup = context.user_data.get("weekly_leave", {})
    department = setup.get("department")
    personnel_name = setup.get("personnel_name")
    weekday = _parse_weekday(_message_text(update))
    if department is None or not personnel_name:
        await update.effective_message.reply_text("Haftalık izin oturumu bulunamadı. Lütfen /haftalikizin ile tekrar başlayın.")
        return ConversationHandler.END
    if weekday is None:
        await update.effective_message.reply_text("Gün adı geçersiz. Örnek: pazartesi")
        return WEEKLY_LEAVE_DAY
    database.add_weekly_leave(department.id, personnel_name, weekday)
    context.user_data.pop("weekly_leave", None)
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text(f"✅ {personnel_name} için haftalık izin günü {WEEKDAY_LABELS[weekday]} olarak kaydedildi.")
    return ConversationHandler.END


@admin_only
async def haftalikiziniptal_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["weekly_leave_cancel"] = {}
    await update.effective_message.reply_text("Departman adını giriniz.")
    return WEEKLY_LEAVE_CANCEL_DEPARTMENT


async def haftalikiziniptal_department(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    department = database.get_department(_identifier(_message_text(update)))
    if department is None:
        await update.effective_message.reply_text("Departman bulunamadı. Lütfen departman adı veya ID giriniz.")
        return WEEKLY_LEAVE_CANCEL_DEPARTMENT
    context.user_data["weekly_leave_cancel"] = {"department": department}
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text("Haftalık izni iptal edilecek personel adını giriniz.")
    return WEEKLY_LEAVE_CANCEL_PERSONNEL


async def haftalikiziniptal_personnel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    personnel_name = _message_text(update)
    if not personnel_name:
        await update.effective_message.reply_text("Personel adı boş olamaz.")
        return WEEKLY_LEAVE_CANCEL_PERSONNEL
    context.user_data["weekly_leave_cancel"]["personnel_name"] = personnel_name
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text("İptal edilecek izin gününü giriniz. Tüm günleri silmek için boş yazınız.")
    return WEEKLY_LEAVE_CANCEL_DAY


async def haftalikiziniptal_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    database: Database = context.application.bot_data["database"]
    setup = context.user_data.get("weekly_leave_cancel", {})
    department = setup.get("department")
    personnel_name = setup.get("personnel_name")
    if department is None or not personnel_name:
        await update.effective_message.reply_text("Haftalık izin iptal oturumu bulunamadı. Lütfen /haftalikiziniptal ile tekrar başlayın.")
        return ConversationHandler.END
    text = _message_text(update)
    weekday = None if _is_blank_rule(text) else _parse_weekday(text)
    if weekday is None and not _is_blank_rule(text):
        await update.effective_message.reply_text("Gün adı geçersiz. Örnek: pazartesi veya boş")
        return WEEKLY_LEAVE_CANCEL_DAY
    if not database.delete_weekly_leave(department.id, personnel_name, weekday):
        await update.effective_message.reply_text("Haftalık izin kaydı bulunamadı.")
        return WEEKLY_LEAVE_CANCEL_DAY
    context.user_data.pop("weekly_leave_cancel", None)
    await update.effective_message.reply_text("Ayarlandı.")
    await update.effective_message.reply_text(f"✅ {personnel_name} haftalık izin kaydı iptal edildi.")
    return ConversationHandler.END


haftalikizinduzenle_start = haftalikizin_start


@allowed_only
async def rapor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    database: Database = context.application.bot_data["database"]
    client: InvektoClient = context.application.bot_data["client"]
    config: Config = context.application.bot_data["config"]
    now = datetime.now(config.timezone)
    args = _plain_args(update)
    if not args:
        await update.effective_message.reply_text("Kullanım: /rapor DepartmanAdı veya ID")
        return
    department = database.get_department(_identifier(args))
    if department is None:
        await update.effective_message.reply_text("Departman bulunamadı.")
        return
    if not _can_report_department_in_chat(update, department):
        await update.effective_message.reply_text("Bu departman raporu sadece kayıtlı Telegram grubunda alınabilir.")
        return
    if not database.get_rules(department.id).is_configured:
        await update.effective_message.reply_text("Bu departman için kurallar tanımlı değil. Önce /kuralayarla ile kuralları giriniz.")
        return
    await update.effective_message.reply_text("Rapor hazırlanıyor...")
    try:
        _, message = await generate_department_report(database, client, department.id, now.date(), now)
    except Exception as exc:
        message = f"❌ {department.name} raporu alınamadı: {exc}"
    for part in split_telegram_message(message):
        await update.effective_message.reply_text(part)


def _can_report_department_in_chat(update: Update, department: Department) -> bool:
    chat = update.effective_chat
    if chat is None:
        return False
    if chat.type == "private":
        return True
    return str(chat.id) == department.telegram_chat_id


@admin_only
async def kontrolinvekto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    database: Database = context.application.bot_data["database"]
    client: InvektoClient = context.application.bot_data["client"]
    config: Config = context.application.bot_data["config"]
    args = _plain_args(update)
    if not args:
        await update.effective_message.reply_text("Kullanım: /kontrolinvekto DepartmanAdı veya ID")
        return
    department = database.get_department(_identifier(args))
    if department is None:
        await update.effective_message.reply_text("Departman bulunamadı.")
        return
    if not department.company_code.strip():
        await update.effective_message.reply_text("Bu departman için CompanyCode boş. Önce /companycodeayarla ile giriniz.")
        return
    report_date = datetime.now(config.timezone).date()
    await update.effective_message.reply_text(f"🔎 {department.name} için Invekto erişimi test ediliyor...")
    try:
        calls = await client.fetch_call_report(department.company_code, report_date)
    except HTTPError as exc:
        message = _format_invekto_http_error(department.name, exc)
    except URLError as exc:
        message = f"❌ {department.name} için Invekto bağlantısı kurulamadı: {exc.reason}"
    except TimeoutError:
        message = f"❌ {department.name} için Invekto isteği zaman aşımına uğradı."
    except RuntimeError as exc:
        message = f"❌ {department.name} için Invekto yanıtı başarısız: {exc}"
    except Exception as exc:
        message = f"❌ {department.name} için Invekto kontrolü başarısız: {exc}"
    else:
        message = _format_invekto_check_success(department.name, len(calls), report_date.isoformat())
    await update.effective_message.reply_text(message)


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text("Bilinmeyen komut. /start ile komut listesini görebilirsin.")


async def _delete_or_toggle_department(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, identifier_text: str | None = None) -> None:
    database: Database = context.application.bot_data["database"]
    args = identifier_text if identifier_text is not None else _plain_args(update)
    if not args:
        await update.effective_message.reply_text("Departman adı veya ID gönderin.")
        return
    identifier = _identifier(args)
    if action == "delete":
        ok = database.delete_department(identifier)
        text = "✅ Departman silindi."
    elif action == "active":
        ok = database.set_department_active(identifier, True)
        text = "✅ Departman aktif edildi."
    else:
        ok = database.set_department_active(identifier, False)
        text = "✅ Departman pasif edildi."
    await update.effective_message.reply_text(text if ok else "Departman bulunamadı.")


def _semicolon_args(update: Update) -> list[str]:
    text = update.effective_message.text or ""
    _, _, payload = text.partition(" ")
    return [part.strip() for part in payload.split(";") if part.strip()]


def _plain_args(update: Update) -> str:
    text = update.effective_message.text or ""
    _, _, payload = text.partition(" ")
    return payload.strip()


def _format_personnel_list(department_name: str, personnel: Sequence[Personnel]) -> str:
    lines = [f"👥 {department_name} personelleri"]
    for index, person in enumerate(personnel, start=1):
        status = "aktif" if person.is_active else "pasif"
        extension = person.extension or "-"
        lines.append(f"{index}. {person.name} | ID: {person.id} | dahili: {extension} | {status}")
    return "\n".join(lines)


def _import_personnel_rows(database: Database, rows: Sequence[PersonnelImportRow], errors: Sequence[str]) -> tuple[int, list[str]]:
    added_count = 0
    failed = list(errors)
    departments: dict[str, Department | None] = {}
    for row in rows:
        key = row.department_name.casefold()
        if key not in departments:
            departments[key] = database.get_department(row.department_name)
        department = departments[key]
        if department is None:
            failed.append(f"Satır {row.row_number}: departman bulunamadı")
            continue
        try:
            database.add_personnel(department.id, row.personnel_name, row.extension)
        except Exception as exc:
            failed.append(f"Satır {row.row_number}: {exc}")
            continue
        added_count += 1
    return added_count, failed


def _format_invekto_check_success(department_name: str, call_count: int, report_date: str) -> str:
    return (
        f"✅ {department_name} için Invekto yanıt verdi.\n"
        f"Tarih: {report_date}\n"
        f"Kayıt sayısı: {call_count}\n"
        "IP/CompanyCode yetkisi bu istek için uygun görünüyor."
    )


def _format_invekto_http_error(department_name: str, error: HTTPError) -> str:
    if error.code in (401, 403):
        reason = "IP whitelist, CompanyCode veya API yetkisi reddedilmiş olabilir."
    elif error.code == 404:
        reason = "Invekto API adresi hatalı olabilir."
    else:
        reason = error.reason or "HTTP hatası alındı."
    return f"❌ {department_name} için Invekto HTTP {error.code} döndü. {reason}"


def _message_text(update: Update) -> str:
    return (update.effective_message.text or "").strip()


def _identifier(value: str) -> str | int:
    return int(value) if value.isdigit() else value


def _is_blank_rule(value: str) -> bool:
    return value.strip().casefold() == "boş"


def _optional_time_text(value: str) -> str | None:
    if _is_blank_rule(value):
        return None
    try:
        parse_hhmm(value)
    except Exception as exc:
        raise ValueError("Saat formatı geçersiz. Örnek: 11:10 veya boş") from exc
    return value


def _parse_weekday(value: str) -> int | None:
    return WEEKDAY_NAMES.get(value.strip().casefold())