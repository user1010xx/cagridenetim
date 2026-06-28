from __future__ import annotations

from typing import Callable

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.config import Config
from bot.database import Database
from bot.models import Department


def is_allowed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
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
    return is_registered_department_chat(context.application.bot_data.get("database"), chat.id)


def can_use_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if user is None:
        return False
    config: Config = context.application.bot_data["config"]
    return user.id in config.admin_user_ids


def is_registered_department_chat(database: Database | None, chat_id: int) -> bool:
    if database is None:
        return False
    return any(department.telegram_chat_id == str(chat_id) for department in database.list_departments())


def can_report_department_in_chat(update: Update, department: Department, config: Config | None = None, database: Database | None = None) -> bool:
    chat = update.effective_chat
    if chat is None:
        return False
    if chat.type == "private":
        return True
    # If this group has any department registered, allow full access for members
    if database is not None and is_registered_department_chat(database, chat.id):
        return True
    if config is not None:
        title = (chat.title or "").strip().casefold()
        if title in config.allowed_group_names:
            return True
    return str(chat.id) == department.telegram_chat_id


def departments_visible_in_chat(
    update: Update,
    departments: list[Department],
    config: Config | None = None,
) -> list[Department]:
    chat = update.effective_chat
    if chat is None:
        return []
    if chat.type == "private":
        if config is not None:
            user = update.effective_user
            if user is None or user.id not in config.admin_user_ids:
                return []
        return departments
    current_chat_str = str(chat.id)
    # If this chat has any registered department, it's a managed group → show all departments
    if any(d.telegram_chat_id == current_chat_str for d in departments):
        return departments
    if config is not None:
        title = (chat.title or "").strip().casefold()
        if title in config.allowed_group_names:
            return departments
    return [department for department in departments if department.telegram_chat_id == current_chat_str]


def admin_only(handler: Callable) -> Callable:
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not can_use_admin_command(update, context):
            await update.effective_message.reply_text("Bu komutu kullanma yetkiniz yok. Sadece tanımlı admin kullanıcılar çalıştırabilir.")
            return ConversationHandler.END
        return await handler(update, context)

    return wrapper


def allowed_only(handler: Callable) -> Callable:
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not is_allowed(update, context):
            await update.effective_message.reply_text("Bu botu kullanma yetkiniz yok.")
            return
        return await handler(update, context)

    return wrapper