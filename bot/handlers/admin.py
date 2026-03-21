"""
Admin command handlers for the Spotify Payment Bot
"""

import logging
import asyncio
import tempfile
import os
from html import escape
from datetime import datetime, timedelta
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.enums import ChatType
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError

from bot.database.operations import Database
from bot.config.settings import Settings
from bot.utils.states import AdminStates
from bot.utils.keyboards import get_admin_main_keyboard, get_confirmation_keyboard, get_pagination_keyboard
from bot.utils.helpers import (
    format_date, calculate_days_until,
    get_payment_status_emoji, get_payment_status_text,
    is_admin, get_now, format_datetime, get_region_from_group_id, get_payment_info
)

# Initialize router
admin_router = Router()
logger = logging.getLogger(__name__)

# Global database instance (will be injected)
db: Database = None
settings: Settings = None

PAID_IN_ADVANCE_MIN_DAYS = 32
PAID_IN_ADVANCE_PAGE_SIZE = 12
PAID_IN_ADVANCE_SORT = "group_then_paid_until_desc"


def init_admin_handlers(database: Database, bot_settings: Settings):
    """Initialize handlers with database and settings"""
    global db, settings
    db = database
    settings = bot_settings


@admin_router.message(Command("admin"))
async def admin_command(message: types.Message, state: FSMContext):
    """Handle /admin command"""
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await message.answer("❌ Доступ запрещён. Команда только для администраторов.")
        return

    if not db or not db.pool:
        await message.answer("❌ База данных в настоящее время недоступна.")
        return

    # Clear any active state (allows canceling any operation)
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        await message.answer("✅ Предыдущая операция отменена.\n")

    await message.answer(
        "🔧 <b>Панель администратора</b>\n\n"
        "Выберите действие:",
        reply_markup=get_admin_main_keyboard(),
        parse_mode="HTML"
    )


@admin_router.message(Command("link_group"))
async def link_group_command(message: types.Message):
    """Link current Telegram group chat to a payment group.
    
    Usage: /link_group 001
    Must be run in a Telegram group (not private chat).
    """
    # This command should work in group chats, not private
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(
            "❌ Эта команда должна использоваться в групповом чате.\n\n"
            "📝 <b>Инструкция:</b>\n"
            "1. Добавьте бота в семейную Telegram-группу\n"
            "2. Запустите <code>/link_group 001</code> в этой группе\n"
            "   (замените 001 на ID вашей группы оплаты)",
            parse_mode="HTML"
        )
        return

    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await message.answer("❌ Доступ запрещён. Команда только для администраторов.")
        return

    if not db or not db.pool:
        await message.answer("❌ База данных в настоящее время недоступна.")
        return

    # Parse command arguments
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "❌ Укажите ID группы оплаты.\n\n"
            "<b>Пример:</b> <code>/link_group 001</code>",
            parse_mode="HTML"
        )
        return

    group_display_id = args[1].strip()
    
    # Find the payment group by display ID
    group = await db.get_group_by_display_id(group_display_id)
    if not group:
        await message.answer(
            f"❌ Группа оплаты с ID <b>{group_display_id}</b> не найдена.\n\n"
            "💡 Используйте /admin для просмотра списка групп.",
            parse_mode="HTML"
        )
        return

    # Link this Telegram chat to the payment group
    telegram_chat_id = message.chat.id
    success = await db.set_group_telegram_chat(group.group_id, telegram_chat_id)

    if success:
        await message.answer(
            f"✅ <b>Группа успешно привязана!</b>\n\n"
            f"📋 Группа оплаты: <b>{group.group_name}</b>\n"
            f"💬 Telegram чат: <code>{telegram_chat_id}</code>\n\n"
            f"🔔 Теперь напоминания об оплате будут отправляться в этот чат.",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "❌ Не удалось привязать группу. Попробуйте позже.",
            parse_mode="HTML"
        )


@admin_router.message(Command("broadcast"))
async def broadcast_command(message: types.Message, state: FSMContext):
    """Handle /broadcast command"""
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await message.answer("❌ Доступ запрещён. Команда только для администраторов.")
        return

    if not db or not db.pool:
        await message.answer("❌ База данных в настоящее время недоступна.")
        return

    # Clear previous state
    await state.clear()

    # Create keyboard for target selection
    builder = InlineKeyboardBuilder()
    builder.button(text="🌍 Все пользователи", callback_data="broadcast_target_all")
    builder.button(text="🇰🇿 Казахстан (KZ)", callback_data="broadcast_target_kz")
    builder.button(text="🇷🇺 Россия (RU)", callback_data="broadcast_target_ru")
    builder.button(text="👥 Группа", callback_data="broadcast_target_group")
    builder.adjust(1)

    await message.answer(
        "📢 <b>Рассылка сообщений</b>\n\n"
        "Выберите целевую аудиторию для рассылки:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.broadcasting_message)


@admin_router.callback_query(F.data.startswith("broadcast_target_"), StateFilter(AdminStates.broadcasting_message))
async def broadcast_target_selection(callback: types.CallbackQuery, state: FSMContext):
    """Handle broadcast target selection"""
    target = callback.data.split("_")[-1]  # all, kz, ru, group

    if target == "group":
        await state.update_data(broadcast_target="group")
        await callback.message.edit_text(
            "📢 <b>Рассылка: Конкретная группа</b>\n\n"
            "Введите название или номер группы (например: <code>spotify 112</code> или <code>112</code>):\n\n"
            "❌ Отправьте /cancel для отмены.",
            parse_mode="HTML"
        )
        await state.set_state(AdminStates.broadcasting_select_group)
        await callback.answer()
        return

    target_names = {
        'all': "Все пользователи",
        'kz': "Казахстан (KZ)",
        'ru': "Россия (RU)"
    }

    await state.update_data(broadcast_target=target)

    await callback.message.edit_text(
        f"📢 <b>Рассылка: {target_names.get(target, target)}</b>\n\n"
        f"Теперь отправьте сообщение, которое вы хотите разослать.\n"
        f"Поддерживается текст, фото и форматирование.\n\n"
        f"❌ Отправьте /cancel для отмены.",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.broadcasting_message)
    await callback.answer()


@admin_router.message(StateFilter(AdminStates.broadcasting_select_group))
async def broadcast_group_input(message: types.Message, state: FSMContext):
    """Handle group name/ID input for group-targeted broadcast"""
    if message.chat.type != ChatType.PRIVATE:
        return

    if message.text and message.text.startswith('/cancel'):
        await state.clear()
        await message.answer("❌ Рассылка отменена.")
        return

    identifier = message.text.strip() if message.text else ""
    if not identifier:
        await message.answer("⚠️ Пожалуйста, введите название или номер группы.")
        return

    group = await db.get_group_by_name_or_id(identifier)
    if not group:
        await message.answer(
            f"❌ Группа <code>{identifier}</code> не найдена.\n"
            "Попробуйте ещё раз или отправьте /cancel для отмены.",
            parse_mode="HTML"
        )
        return

    await state.update_data(broadcast_group_id=group.group_id, broadcast_group_name=group.group_name)

    await message.answer(
        f"📢 <b>Рассылка: {group.group_name}</b>\n\n"
        f"Теперь отправьте сообщение, которое вы хотите разослать.\n"
        f"Поддерживается текст, фото и форматирование.\n\n"
        f"❌ Отправьте /cancel для отмены.",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.broadcasting_message)


@admin_router.message(StateFilter(AdminStates.broadcasting_message))
async def broadcast_message_input(message: types.Message, state: FSMContext):
    """Handle broadcast message input and show preview"""
    if message.chat.type != ChatType.PRIVATE:
        return

    if message.text and message.text.startswith('/cancel'):
        await state.clear()
        await message.answer("❌ Рассылка отменена.")
        return

    # Save message content details to state
    await state.update_data(
        message_id=message.message_id,
        chat_id=message.chat.id
    )

    # Show preview
    try:
        await message.answer("📝 <b>Предпросмотр сообщения:</b>", parse_mode="HTML")
        # Copy the message back to user as preview
        await message.send_copy(chat_id=message.chat.id)
    except Exception as e:
        await message.answer(f"⚠️ Ошибка предпросмотра: {e}")
        return

    # Confirmation keyboard
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Отправить", callback_data="broadcast_confirm")
    builder.button(text="❌ Отменить", callback_data="broadcast_cancel")
    builder.adjust(2)

    data = await state.get_data()
    target = data.get('broadcast_target')
    target_names = {
        'all': "Все пользователи",
        'kz': "Казахстан (KZ)",
        'ru': "Россия (RU)",
        'group': data.get('broadcast_group_name', 'Группа')
    }

    await message.answer(
        f"❓ <b>Подтверждение рассылки</b>\n\n"
        f"🎯 Целевая аудитория: <b>{target_names.get(target, target)}</b>\n"
        f"📤 Это сообщение будет отправлено всем выбранным пользователям.\n\n"
        f"Подтверждаете отправку?",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.broadcasting_confirm)


@admin_router.callback_query(StateFilter(AdminStates.broadcasting_confirm))
async def broadcast_confirmation_handler(callback: types.CallbackQuery, state: FSMContext):
    """Handle broadcast confirmation"""
    if callback.data == "broadcast_cancel":
        await state.clear()
        await callback.message.edit_text("❌ Рассылка отменена.")
        await callback.answer()
        return

    if callback.data == "broadcast_confirm":
        # Answer immediately — Telegram times out callbacks after 30 seconds,
        # and the broadcast loop can run much longer than that.
        await callback.answer()

        data = await state.get_data()
        target = data.get('broadcast_target')
        message_id = data.get('message_id')
        chat_id = data.get('chat_id')

        await callback.message.edit_text(
            "⏳ <b>Начинаю рассылку...</b>\n"
            "Пожалуйста, не используйте бота до завершения операции.",
            parse_mode="HTML"
        )

        try:
            if target == "group":
                group_id = data.get('broadcast_group_id')
                users = await db.get_users_by_group(group_id)
            else:
                users = await db.get_users_by_region(target)

            if not users:
                await callback.message.edit_text("❌ Пользователи не найдены для выбранной категории.")
                await state.clear()
                return

            success_count = 0
            fail_count = 0
            total = len(users)
            last_progress_update = datetime.now()

            for i, user_id in enumerate(users, 1):
                try:
                    await callback.bot.copy_message(
                        chat_id=user_id,
                        from_chat_id=chat_id,
                        message_id=message_id
                    )
                    success_count += 1
                except TelegramRetryAfter as e:
                    # Rate limited — wait and retry once
                    await asyncio.sleep(e.retry_after)
                    try:
                        await callback.bot.copy_message(
                            chat_id=user_id,
                            from_chat_id=chat_id,
                            message_id=message_id
                        )
                        success_count += 1
                    except Exception:
                        fail_count += 1
                except TelegramForbiddenError:
                    # User blocked the bot — not an error worth logging
                    fail_count += 1
                except Exception as e:
                    fail_count += 1
                    logger.error(f"Failed to broadcast to {user_id}: {e}")

                await asyncio.sleep(0.05)

                # Live progress update — throttled to once every 2 seconds
                # to avoid hitting the message-edit rate limit.
                now = datetime.now()
                if (now - last_progress_update).total_seconds() >= 2:
                    try:
                        await callback.message.edit_text(
                            f"⏳ <b>Рассылка...</b> {i}/{total}\n"
                            f"✅ Успешно: {success_count}  ❌ Ошибки: {fail_count}",
                            parse_mode="HTML"
                        )
                        last_progress_update = now
                    except Exception:
                        pass  # Ignore edit failures (e.g. message not modified)

            await callback.message.edit_text(
                f"✅ <b>Рассылка завершена!</b>\n\n"
                f"👥 Всего пользователей: {total}\n"
                f"📤 Успешно отправлено: {success_count}\n"
                f"⚠️ Не удалось отправить: {fail_count}",
                parse_mode="HTML"
            )

        except Exception as e:
            logger.error(f"Broadcast failed: {e}")
            await callback.message.edit_text(f"❌ Ошибка при рассылке: {e}")

        await state.clear()


@admin_router.message(Command("check_notifications"))
async def check_notifications_command(message: types.Message):
    """Check what notifications would be sent (without actually sending them)"""
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await message.answer("❌ Доступ запрещён. Команда только для администраторов.")
        return

    if not db or not db.pool:
        await message.answer("❌ База данных в настоящее время недоступна.")
        return

    try:
        # Check users needing reminders
        reminder_users = await db.get_users_needing_reminders(settings.bot_payment_reminder_days)

        # Check users overdue for admin warnings
        overdue_users = await db.get_users_overdue_for_admin_warning(3)

        response = "🔍 <b>Проверка статуса уведомлений</b>\n\n"

        if reminder_users:
            response += f"📬 <b>Пользователи, нуждающиеся в напоминаниях</b> ({len(reminder_users)}):\n"
            for status in reminder_users:
                response += f"• Пользователь {status.user_id} в '{status.group_name}'\n"
                response += f"  📅 Срок: {format_date(status.next_payment_date)}\n"
            response += "\n"
        else:
            response += "📭 Сегодня никому не нужны напоминания об оплате\n\n"

        if overdue_users:
            response += f"🚨 <b>Пользователи с просроченными платежами для предупреждения администратора</b> ({len(overdue_users)}):\n"
            for status in overdue_users:
                user_name = getattr(status, 'first_name',
                                    f'Пользователь {status.user_id}')
                response += f"• {user_name} в '{status.group_name}'\n"
                response += f"  📅 Срок был: {format_date(status.next_payment_date)}\n"
            response += "\n"
        else:
            response += "✅ Нет пользователей с просроченными предупреждениями\n\n"

        response += "💡 Используйте /test_notifications для фактической отправки этих уведомлений"

        await message.answer(response, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Check notifications failed: {e}")
        await message.answer(
            f"❌ <b>Проверка не удалась:</b>\n\n<code>{str(e)}</code>",
            parse_mode="HTML"
        )


@admin_router.message(Command("test_notifications"))
async def test_notifications_command(message: types.Message):
    """Handle /test_notifications command"""
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await message.answer("❌ Доступ запрещён. Команда только для администраторов.")
        return

    if not db or not db.pool:
        await message.answer("❌ База данных в настоящее время недоступна.")
        return

    await message.answer("🧪 Запуск тестовых уведомлений...")

    try:
        # Import here to avoid circular imports
        from bot.utils.notifications import NotificationScheduler

        # Create a temporary scheduler for testing
        test_scheduler = NotificationScheduler(message.bot, db, settings)

        # Run the notification checks
        await test_scheduler.send_test_notifications()

        await message.answer(
            "✅ <b>Тестовые уведомления завершены!</b>\n\n"
            "Проверьте логи бота, чтобы увидеть, были ли отправлены уведомления.\n\n"
            "💡 <b>Напоминание:</b> Уведомления отправляются автоматически ежедневно в 9:00 утра.",
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"❌ Test notifications failed: {e}")
        await message.answer(
            f"❌ <b>Тестовые уведомления не удались:</b>\n\n"
            f"<code>{str(e)}</code>\n\n"
            f"Проверьте логи бота для получения дополнительной информации.",
            parse_mode="HTML"
        )


@admin_router.message(Command("test_admin_notification"))
async def test_admin_notification_command(message: types.Message):
    """Handle /test_admin_notification command - instantly trigger admin warnings"""
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await message.answer("❌ Доступ запрещён. Команда только для администраторов.")
        return

    if not db or not db.pool:
        await message.answer("❌ База данных в настоящее время недоступна.")
        return

    await message.answer("🧪 Запуск теста уведомлений администраторов...")

    try:
        # Import here to avoid circular imports
        from bot.utils.notifications import NotificationScheduler

        # Create a temporary scheduler for testing
        test_scheduler = NotificationScheduler(message.bot, db, settings)

        # Run only the admin warning check
        await test_scheduler._send_admin_warnings()

        await message.answer(
            "✅ <b>Тест уведомлений администраторов завершен!</b>\n\n"
            "Если есть пользователи, просроченные на 3+ дня, вы должны были получить уведомление.\n\n"
            "💡 <b>Напоминание:</b> Уведомления администраторов отправляются автоматически ежедневно в 9:00 утра.",
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"❌ Test admin notification failed: {e}")
        await message.answer(
            f"❌ <b>Тест не удался:</b>\n\n"
            f"<code>{str(e)}</code>\n\n"
            f"Проверьте логи бота для получения дополнительной информации.",
            parse_mode="HTML"
        )


@admin_router.message(Command("update_due_date"))
async def update_due_date_command(message: types.Message, state: FSMContext):
    """Handle /update_due_date command"""
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await message.answer("❌ Доступ запрещён. Команда только для администраторов.")
        return

    if not db or not db.pool:
        await message.answer("❌ База данных в настоящее время недоступна.")
        return

    # Show available groups
    groups = await db.get_all_groups()
    if not groups:
        await message.answer("❌ Нет доступных групп.")
        return

    groups_text = "📅 <b>Обновить дату платежа группы</b>\n\n"
    groups_text += "Доступные группы:\n\n"

    for group in groups:
        days_until = calculate_days_until(group.next_payment_date)
        status_emoji = get_payment_status_emoji(days_until)

    for group in groups:
        days_until = calculate_days_until(group.next_payment_date)
        status_emoji = get_payment_status_emoji(days_until)

        groups_text += (
            f"{status_emoji} <b>{group.group_name}</b> (ID: {group.display_id})\n"
            f"📅 Текущая дата платежа: {format_date(group.next_payment_date)}\n"
            f"📊 Статус: {get_payment_status_text(days_until)}\n\n"
        )

    groups_text += "Пожалуйста, введите название группы или ID (например: 'spotify 001' или '001'):"

    await message.answer(groups_text, parse_mode="HTML")
    await state.set_state(AdminStates.updating_due_date_group)


@admin_router.message(Command("paid_in_advance"))
async def paid_in_advance_command(message: types.Message):
    """List users who have paid for future months"""
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await message.answer("❌ Доступ запрещён. Команда только для администраторов.")
        return

    if not db or not db.pool:
        await message.answer("❌ База данных в настоящее время недоступна.")
        return

    response, keyboard = await build_paid_in_advance_page(page=0)
    if not response:
        await message.answer("No users paid in advance.")
        return

    await message.answer(response, parse_mode="HTML", reply_markup=keyboard)
    return

@admin_router.callback_query(F.data.startswith("paid_in_advance_page_"))
async def paid_in_advance_page_handler(callback: types.CallbackQuery):
    """Handle pagination for paid-in-advance view."""
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Access denied", show_alert=True)
        return

    if not db or not db.pool:
        await callback.answer("Database unavailable", show_alert=True)
        return

    try:
        page = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer("Invalid page", show_alert=True)
        return

    response, keyboard = await build_paid_in_advance_page(page=page)
    if not response:
        await callback.message.edit_text("No users paid in advance.")
        await callback.answer()
        return

    await callback.message.edit_text(response, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


async def build_paid_in_advance_page(page: int = 0):
    """Build one page of users paid in advance and pagination keyboard."""
    total_users = await db.count_users_paid_in_advance(
        min_days_ahead=PAID_IN_ADVANCE_MIN_DAYS
    )
    if total_users <= 0:
        return None, None

    total_pages = max(1, (total_users + PAID_IN_ADVANCE_PAGE_SIZE - 1) // PAID_IN_ADVANCE_PAGE_SIZE)
    current_page = min(max(0, page), total_pages - 1)

    users = await db.get_users_paid_in_advance(
        min_days_ahead=PAID_IN_ADVANCE_MIN_DAYS,
        page=current_page,
        page_size=PAID_IN_ADVANCE_PAGE_SIZE,
        sort_by=PAID_IN_ADVANCE_SORT
    )
    if not users:
        return None, None

    grouped_users = {}
    for user in users:
        group_id = user['group_id']
        if group_id not in grouped_users:
            grouped_users[group_id] = {'name': user['group_name'], 'users': []}
        grouped_users[group_id]['users'].append(user)

    groups_on_page = len(grouped_users)
    response = (
        f"<b>Users Paid In Advance</b>\n"
        f"Rule: next payment is more than {PAID_IN_ADVANCE_MIN_DAYS} days away\n"
        f"Total users: {total_users} | Groups on this page: {groups_on_page}\n"
        f"Page: {current_page + 1}/{total_pages}\n"
    )

    for group_id in sorted(grouped_users.keys()):
        group_data = grouped_users[group_id]
        response += f"\n<b>{escape(str(group_data['name']))}</b> (ID: {escape(str(group_id))})\n"

        for user in group_data['users']:
            username_link = f"@{escape(user['username'])}" if user['username'] else f"ID: {user['user_id']}"
            months = user['months_ahead']

            if months >= 6:
                status_emoji = "🌟"
            elif months >= 3:
                status_emoji = "⭐"
            else:
                status_emoji = "🔹"

            response += (
                f"{status_emoji} <b>{escape(str(user['name']))}</b> ({username_link})\n"
                f"   Paid until: {format_date(user['paid_until'])} (+{months} months)\n"
            )

    keyboard = get_pagination_keyboard(
        current_page,
        total_pages,
        "paid_in_advance",
        show_back=True
    )
    return response, keyboard


@admin_router.callback_query(F.data == "admin_view_groups")
async def view_groups(callback: types.CallbackQuery):
    """View all payment groups with fill status summary - page 0"""
    await view_groups_page(callback, page=0)


@admin_router.callback_query(F.data.startswith("view_groups_page_"))
async def view_groups_page_handler(callback: types.CallbackQuery):
    """Handle pagination for view groups"""
    page = int(callback.data.split("_")[-1])
    await view_groups_page(callback, page)


async def view_groups_page(callback: types.CallbackQuery, page: int = 0):
    """View all payment groups with fill status summary"""
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    groups = await db.get_all_groups()

    if not groups:
        await callback.message.edit_text("📭 Группы оплаты не найдены.")
        return

    # Pagination settings
    GROUPS_PER_PAGE = 5
    total_groups = len(groups)
    total_pages = (total_groups + GROUPS_PER_PAGE - 1) // GROUPS_PER_PAGE

    # Validate page number
    if page < 0 or page >= total_pages:
        page = 0

    # Get groups for current page
    start_idx = page * GROUPS_PER_PAGE
    end_idx = min(start_idx + GROUPS_PER_PAGE, total_groups)
    page_groups = groups[start_idx:end_idx]

    response = f"👥 <b>Все группы оплаты с участниками (стр. {page + 1}/{total_pages}):</b>\n\n"

    for group in page_groups:
        # Get members for this group
        members = await db.get_group_members(group.group_id)
        total_members = len(members) if members else 0

        # Count members who have paid (not overdue)
        paid_count = 0
        if members:
            for member in members:
                if not member['is_overdue']:
                    paid_count += 1

        # Determine emoji based on member payment status
        if total_members == 0:
            emoji = "📭"  # Empty group
        elif paid_count == total_members:
            emoji = "✅"  # All paid
        elif paid_count == 0:
            emoji = "❌"  # None paid
        else:
            emoji = "⚠️"  # Partially paid

        response += (
            f"{emoji} <b>Группа: {group.group_name}</b> (ID: {group.display_id})\n"
            f"📅 Следующий платёж: {format_date(group.next_payment_date)}\n"
            f"👥 {paid_count}/{total_members}\n\n"
        )

    # Add pagination keyboard
    keyboard = get_pagination_keyboard(
        page, total_pages, "view_groups", show_back=True)

    await callback.message.edit_text(response, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@admin_router.callback_query(F.data == "admin_import_groups")
async def import_groups_start(callback: types.CallbackQuery, state: FSMContext):
    """Start group import process"""
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    await state.set_state(AdminStates.importing_groups_file)
    await callback.message.edit_text(
        "📊 <b>Импорт групп из Excel файла</b>\n\n"
        "Отправьте Excel файл (.xlsx) с данными для импорта групп.\n\n"
        "<b>Формат файла:</b>\n"
        "• Столбец A: Названия групп (например: spotify 001)\n"
        "• Столбец B: ID групп (например: 001)\n\n"
        "<b>Пример:</b>\n"
        "<pre>\n"
        "spotify 001 | 001\n"
        "spotify 002 | 002\n"
        "</pre>\n\n"
        "📎 Прикрепите файл к следующему сообщению или используйте /admin для отмены:",
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin_create_group")
async def create_group_start(callback: types.CallbackQuery, state: FSMContext):
    """Start group creation process"""
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    await callback.message.edit_text(
        "➕ <b>Создать новую группу</b>\n\n"
        "Пожалуйста, введите название группы:\n\n"
        "💡 <i>Используйте /admin для отмены операции</i>",
        parse_mode="HTML"
    )

    await state.set_state(AdminStates.creating_group)
    await callback.answer()


@admin_router.message(StateFilter(AdminStates.creating_group))
async def create_group_finish(message: types.Message, state: FSMContext):
    """Ask for next payment date after group name"""
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        return

    group_name = message.text.strip()

    if not group_name:
        await message.answer(
            "❌ Название группы не может быть пустым. "
            "Пожалуйста, попробуйте снова."
        )
        return

    # Check if group already exists (either by full name or display ID)
    existing_group = await db.get_group_by_name_or_id(group_name)
    if existing_group:
        await message.answer(
            f"❌ Группа с таким названием или ID уже существует:\n\n"
            f"👥 Название: <b>{existing_group.group_name}</b>\n"
            f"🆔 ID: <b>{existing_group.display_id}</b>\n\n"
            f"Пожалуйста, введите другое название или используйте /admin для отмены.",
            parse_mode="HTML"
        )
        return

    # Save group name and ask for next payment date
    await state.update_data(group_name=group_name)

    await message.answer(
        f"✅ Название группы: <b>{group_name}</b>\n\n"
        f"📅 Теперь введите дату следующего платежа:\n\n"
        f"Формат: <b>ДД.ММ.ГГГГ</b>\n"
        f"Пример: <code>15.01.2026</code>\n\n"
        f"💡 Или отправьте <code>+30</code> для автоматической даты "
        f"(через 30 дней)\n\n"
        f"<i>Используйте /admin для отмены</i>",
        parse_mode="HTML"
    )

    await state.set_state(AdminStates.creating_group_date)


@admin_router.message(StateFilter(AdminStates.creating_group_date))
async def create_group_with_date(message: types.Message, state: FSMContext):
    """Create group with specified next payment date"""
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        return

    date_input = message.text.strip()

    # Handle automatic date (+30)
    if date_input == "+30":
        next_payment_date = get_now() + timedelta(days=30)
    else:
        # Parse date in DD.MM.YYYY format
        try:
            next_payment_date = datetime.strptime(date_input, "%d.%m.%Y")

            # Check if date is not in the past
            if next_payment_date.date() <= get_now().date():
                await message.answer(
                    "❌ Дата не может быть в прошлом или сегодня. "
                    "Пожалуйста, введите будущую дату."
                )
                return
        except ValueError:
            await message.answer(
                f"❌ Неверный формат даты.\n\n"
                f"Используйте формат <b>ДД.ММ.ГГГГ</b>\n"
                f"Пример: <code>15.01.2026</code>\n\n"
                f"Или отправьте <code>+30</code> для автоматической даты",
                parse_mode="HTML"
            )
            return

    # Get saved group name
    data = await state.get_data()
    group_name = data.get('group_name')

    # Create group
    group_id = await db.create_group(group_name, next_payment_date)

    if group_id:
        # Get the created group to show display_id
        created_groups = await db.get_all_groups() if db else []
        created_group = next(
            (g for g in created_groups if g.group_id == group_id), None
        )

        await message.answer(
            f"✅ <b>Группа успешно создана!</b>\n\n"
            f"👥 Название группы: {created_group.group_name if created_group else 'N/A'}\n"
            f"🆔 ID группы: {created_group.display_id if created_group else 'N/A'}\n"
            f"📅 Дата следующего платежа: {format_date(next_payment_date)}",
            parse_mode="HTML"
        )
        logger.info(
            f"Admin {user_id} created group (ID: {group_id}) "
            f"with payment date {format_date(next_payment_date)}"
        )
    else:
        await message.answer(
            "❌ Не удалось создать группу. Пожалуйста, попробуйте снова."
        )

    await state.clear()


@admin_router.callback_query(F.data == "admin_add_user")
async def add_user_start(callback: types.CallbackQuery, state: FSMContext):
    """Start user addition process"""
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    await callback.message.edit_text(
        "👤 <b>Добавить пользователя в группу</b>\n\n"
        "Введите <b>Telegram ID</b> и <b>ID группы</b> через пробел:\n"
        "<code>8000913303 001</code>\n\n"
        "💡 <i>Используйте /admin для отмены операции</i>",
        parse_mode="HTML"
    )

    await state.set_state(AdminStates.adding_user_username)
    await callback.answer()


@admin_router.message(StateFilter(AdminStates.adding_user_username))
async def add_user_finish(message: types.Message, state: FSMContext):
    """Parse USER_ID GROUP_ID and add user to group"""
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        return

    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer(
            "❌ Неверный формат. Введите через пробел:\n"
            "<code>TELEGRAM_ID ID_ГРУППЫ</code>\n"
            "Например: <code>8000913303 001</code>",
            parse_mode="HTML"
        )
        return

    try:
        target_user_id = int(parts[0])
    except ValueError:
        await message.answer("❌ Telegram ID должен быть числом.")
        return

    group_display_id = parts[1].strip()

    # Look up group by display_id
    group = await db.get_group_by_display_id(group_display_id)
    if not group:
        await message.answer(f"❌ Группа с ID <code>{group_display_id}</code> не найдена.", parse_mode="HTML")
        await state.clear()
        return

    # Only create user record if they don't already exist (avoid overwriting real username/name)
    existing_user = await db.get_user(target_user_id)
    if not existing_user:
        await db.add_user(target_user_id, f"user_{target_user_id}", None)

    # Add user to group
    success = await db.add_user_to_group(target_user_id, group.group_id)

    if success:
        await message.answer(
            f"✅ <b>Пользователь добавлен!</b>\n\n"
            f"👤 Telegram ID: <code>{target_user_id}</code>\n"
            f"👥 Группа: {group.group_name} (ID: {group.display_id})\n"
            f"📅 Следующий платёж: {format_date(group.next_payment_date)}",
            parse_mode="HTML"
        )
        logger.info(f"Admin {user_id} added user {target_user_id} to group '{group.group_name}' ({group.display_id})")
    else:
        await message.answer("❌ Не удалось добавить пользователя в группу. Возможно, он уже в этой группе.")

    await state.clear()


@admin_router.message(Command("addphantom"))
async def add_phantom_command(message: types.Message):
    """Add a phantom (free, non-paying) user to a group. Usage: /addphantom GROUP_ID"""
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        return

    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer(
            "❌ Неверный формат.\n\n"
            "Использование: <code>/addphantom ID_ГРУППЫ</code>\n"
            "Например: <code>/addphantom 001</code>",
            parse_mode="HTML"
        )
        return

    group_display_id = parts[1].strip()
    group = await db.get_group_by_display_id(group_display_id)
    if not group:
        await message.answer(f"❌ Группа с ID <code>{group_display_id}</code> не найдена.", parse_mode="HTML")
        return

    success = await db.add_phantom_to_group(group.group_id)
    if success:
        await message.answer(
            f"👻 <b>Фантом добавлен!</b>\n\n"
            f"👥 Группа: {group.group_name} (ID: {group.display_id})\n"
            f"💡 Фантом занимает слот, не платит и не получает уведомлений.",
            parse_mode="HTML"
        )
        logger.info(f"Admin {user_id} added phantom to group '{group.group_name}' ({group.display_id})")
    else:
        await message.answer("❌ Не удалось добавить фантома в группу.")


@admin_router.callback_query(F.data == "admin_update_due_date")
async def update_due_date_start(callback: types.CallbackQuery, state: FSMContext):
    """Start due date update process"""
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Access denied", show_alert=True)
        return

    # Show available groups
    groups = await db.get_all_groups()
    if not groups:
        await callback.message.edit_text("❌ No groups available.")
        return

    groups_text = "📅 <b>Update Group Due Date</b>\n\n"
    groups_text += "Available groups:\n\n"

    for group in groups:
        days_until = calculate_days_until(group.next_payment_date)
        status_emoji = get_payment_status_emoji(days_until)

        groups_text += (
            f"{status_emoji} <b>{group.group_name}</b> (ID: {group.group_id})\n"
            f"📅 Current due date: {format_date(group.next_payment_date)}\n"
            f"📊 Status: {get_payment_status_text(days_until)}\n\n"
        )

    groups_text += "Please enter the group name you want to update:\n\n"
    groups_text += "💡 <i>Используйте /admin для отмены операции</i>"

    await callback.message.edit_text(groups_text, parse_mode="HTML")
    await state.set_state(AdminStates.updating_due_date_group)
    await callback.answer()


@admin_router.message(StateFilter(AdminStates.updating_due_date_group))
async def update_due_date_get_date(message: types.Message, state: FSMContext):
    """Get new due date for the group"""
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        return

    identifier = message.text.strip()

    # Get group by name or display ID
    group = await db.get_group_by_name_or_id(identifier)
    if not group:
        await message.answer(f"❌ Группа '{identifier}' не найдена. Пожалуйста, попробуйте снова.")
        return

    await state.update_data(group=group)

    await message.answer(
        f"📅 <b>Update Due Date for {group.group_name}</b>\n\n"
        f"Current due date: {format_date(group.next_payment_date)}\n\n"
        f"Please enter the new due date in format: <b>YYYY-MM-DD</b>\n\n"
        f"Examples:\n"
        f"• <code>2025-11-15</code> (November 15, 2025)\n"
        f"• <code>2025-12-01</code> (December 1, 2025)\n\n"
        f"💡 <i>Используйте /admin для отмены операции</i>",
        parse_mode="HTML"
    )

    await state.set_state(AdminStates.updating_due_date_date)


@admin_router.message(StateFilter(AdminStates.updating_due_date_date))
async def update_due_date_finish(message: types.Message, state: FSMContext):
    """Finish due date update"""
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        return

    if message.text.strip().lower() == 'cancel':
        await message.answer("❌ Due date update cancelled.")
        await state.clear()
        return

    data = await state.get_data()
    group = data.get('group')

    if not group:
        await message.answer("❌ Error: Group data not found. Please start over.")
        await state.clear()
        return

    # Parse the date
    try:
        from datetime import datetime
        date_str = message.text.strip()
        new_due_date = datetime.strptime(date_str, "%d.%m.%Y")

        # Check if date is not in the past or today
        if new_due_date.date() <= get_now().date():
            await message.answer("❌ Due date cannot be in the past or today. Please enter a future date.")
            return

    except ValueError:
        await message.answer(
            "❌ Invalid date format. Please use <b>DD.MM.YYYY</b> format.\n\n"
            "Example: 15.11.2025",
            parse_mode="HTML"
        )
        return

    # Update the due date
    success = await db.update_group_due_date(group.group_id, new_due_date)

    if success:
        days_until = calculate_days_until(new_due_date)
        status_emoji = get_payment_status_emoji(days_until)

        await message.answer(
            f"✅ <b>Due Date Updated Successfully!</b>\n\n"
            f"👥 Group: {group.group_name}\n"
            f"📅 Old due date: {format_date(group.next_payment_date)}\n"
            f"📅 New due date: {format_date(new_due_date.date())}\n"
            f"{status_emoji} Status: {get_payment_status_text(days_until)}\n\n"
            f"💡 All users in this group will now be reminded based on the new date.",
            parse_mode="HTML"
        )

        logger.info(
            f"Admin {user_id} updated due date for group '{group.group_name}' from {group.next_payment_date} to {new_due_date.date()}")
    else:
        await message.answer(
            "❌ Failed to update due date. Please try again or check the logs for errors."
        )

    await state.clear()


@admin_router.callback_query(F.data == "admin_stats_kz")
async def view_statistics_kz(callback: types.CallbackQuery):
    """Show ordering selection for Kazakhstan statistics"""
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    # Create ordering selection keyboard for KZ
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 По ID (001, 002, ...)", callback_data="admin_stats_kz_order_id")
    builder.button(text="📅 По дате платежа (01-28)", callback_data="admin_stats_kz_order_date")
    builder.button(text="🔙 Назад", callback_data="admin_menu")
    builder.adjust(1)

    await callback.message.edit_text(
        "📈 <b>Статистика 🇰🇿 Казахстан - Выберите порядок сортировки:</b>\n\n"
        "📋 <b>По ID</b> - группы будут отсортированы по их идентификатору (001, 002, 003, ...)\n\n"
        "📅 <b>По дате платежа</b> - группы будут отсортированы по дню оплаты в месяце (01-28), затем по ID",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin_stats_ru")
async def view_statistics_ru(callback: types.CallbackQuery):
    """Show ordering selection for Russia statistics"""
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    # Create ordering selection keyboard for RU
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 По ID (101, 102, ...)", callback_data="admin_stats_ru_order_id")
    builder.button(text="📅 По дате платежа (01-28)", callback_data="admin_stats_ru_order_date")
    builder.button(text="🔙 Назад", callback_data="admin_menu")
    builder.adjust(1)

    await callback.message.edit_text(
        "📈 <b>Статистика 🇷🇺 Россия - Выберите порядок сортировки:</b>\n\n"
        "📋 <b>По ID</b> - группы будут отсортированы по их идентификатору (101, 102, 103, ...)\n\n"
        "📅 <b>По дате платежа</b> - группы будут отсортированы по дню оплаты в месяце (01-28), затем по ID",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


# Keep old handler for backward compatibility
@admin_router.callback_query(F.data == "admin_stats")
async def view_statistics(callback: types.CallbackQuery):
    """Show ordering selection for statistics (all regions)"""
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    # Create ordering selection keyboard
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 По ID (001, 002, ...)", callback_data="admin_stats_order_id")
    builder.button(text="📅 По дате платежа (01-28)", callback_data="admin_stats_order_date")
    builder.button(text="🔙 Назад", callback_data="admin_menu")
    builder.adjust(1)

    await callback.message.edit_text(
        "📈 <b>Статистика - Выберите порядок сортировки:</b>\n\n"
        "📋 <b>По ID</b> - группы будут отсортированы по их идентификатору (001, 002, 003, ...)\n\n"
        "📅 <b>По дате платежа</b> - группы будут отсортированы по дню оплаты в месяце (01-28), затем по ID",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin_stats_order_id")
async def view_statistics_by_id(callback: types.CallbackQuery):
    """View statistics ordered by ID - page 0"""
    await view_statistics_page(callback, page=0, order_by="id")


@admin_router.callback_query(F.data == "admin_stats_order_date")
async def view_statistics_by_date(callback: types.CallbackQuery):
    """View statistics ordered by payment date - page 0"""
    await view_statistics_page(callback, page=0, order_by="date")


# Kazakhstan regional stats handlers
@admin_router.callback_query(F.data == "admin_stats_kz_order_id")
async def view_statistics_kz_by_id(callback: types.CallbackQuery):
    """View KZ statistics ordered by ID - page 0"""
    await view_statistics_page(callback, page=0, order_by="id", region="kz")


@admin_router.callback_query(F.data == "admin_stats_kz_order_date")
async def view_statistics_kz_by_date(callback: types.CallbackQuery):
    """View KZ statistics ordered by payment date - page 0"""
    await view_statistics_page(callback, page=0, order_by="date", region="kz")


# Russia regional stats handlers
@admin_router.callback_query(F.data == "admin_stats_ru_order_id")
async def view_statistics_ru_by_id(callback: types.CallbackQuery):
    """View RU statistics ordered by ID - page 0"""
    await view_statistics_page(callback, page=0, order_by="id", region="ru")


@admin_router.callback_query(F.data == "admin_stats_ru_order_date")
async def view_statistics_ru_by_date(callback: types.CallbackQuery):
    """View RU statistics ordered by payment date - page 0"""
    await view_statistics_page(callback, page=0, order_by="date", region="ru")


@admin_router.callback_query(F.data.startswith("admin_stats_page_"))
async def view_statistics_page_handler(callback: types.CallbackQuery):
    """Handle pagination for statistics"""
    # Format: admin_stats_page_{order}_{page} or admin_stats_page_{region}_{order}_{page}
    parts = callback.data.split("_")
    if len(parts) == 5:
        # Old format: admin_stats_page_{order}_{page}
        order_by = parts[3]  # 'id' or 'date'
        page = int(parts[4])
        region = None
    else:
        # New format: admin_stats_page_{region}_{order}_{page}
        region = parts[3]  # 'kz' or 'ru'
        order_by = parts[4]  # 'id' or 'date'
        page = int(parts[5])
    await view_statistics_page(callback, page, order_by, region)


async def view_statistics_page(callback: types.CallbackQuery, page: int = 0, order_by: str = "date", region: str = None):
    """View detailed statistics with all payment groups and members
    
    Args:
        callback: Callback query
        page: Page number
        order_by: 'id' or 'date'
        region: 'kz', 'ru', or None for all groups
    """
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    # Get groups with selected ordering
    if order_by == "id":
        groups = await db.get_all_groups()
        order_text = "по ID"
    else:  # date
        groups = await db.get_all_groups_for_statistics()
        order_text = "по дате платежа"

    # Filter groups by region if specified
    if region:
        groups = [g for g in groups if get_region_from_group_id(g.display_id) == region]

    # Determine region title
    if region == "kz":
        region_title = "🇰🇿 Казахстан"
    elif region == "ru":
        region_title = "🇷🇺 Россия"
    else:
        region_title = "Все регионы"

    if not groups:
        await callback.message.edit_text(f"📭 Группы оплаты не найдены для региона {region_title}.")
        return

    # Pagination settings
    # Fewer groups per page for statistics (more detailed info)
    GROUPS_PER_PAGE = 3
    total_groups = len(groups)
    total_pages = (total_groups + GROUPS_PER_PAGE - 1) // GROUPS_PER_PAGE

    # Validate page number
    if page < 0 or page >= total_pages:
        page = 0

    # Get groups for current page
    start_idx = page * GROUPS_PER_PAGE
    end_idx = min(start_idx + GROUPS_PER_PAGE, total_groups)
    page_groups = groups[start_idx:end_idx]

    response = f"📈 <b>Статистика {region_title} ({order_text}) - Группы с участниками (стр. {page + 1}/{total_pages}):</b>\n\n"

    for group in page_groups:
        # Get members for this group
        members = await db.get_group_members(group.group_id)
        total_members = len(members) if members else 0

        # Count members who have paid (not overdue)
        paid_count = 0
        if members:
            for member in members:
                if not member['is_overdue']:
                    paid_count += 1

        # Determine emoji based on member payment status
        if total_members == 0:
            emoji = "📭"  # Empty group
        elif paid_count == total_members:
            emoji = "✅"  # All paid
        elif paid_count == 0:
            emoji = "❌"  # None paid
        else:
            emoji = "⚠️"  # Partially paid

        response += (
            f"{emoji} <b>Группа: {group.group_name}</b> (ID: {group.display_id})\n"
            f"📅 Следующий платёж: {format_date(group.next_payment_date)}\n"
        )

        if members:
            response += f"👥 <b>Участники ({len(members)}):</b>\n"
            for idx, member in enumerate(members, 1):
                first_name = member['first_name'] or 'N/A'
                username_display = f"@{member['username']}" if member['username'] else 'нет username'

                # Determine payment status
                if member['is_overdue']:
                    status = "❌ Просрочено"
                else:
                    member_days = (
                        member['next_payment_date'] - get_now().date()).days
                    if member_days <= 3:
                        status = "⚠️ Скоро срок"
                    else:
                        status = "✅ Оплачено"

                response += (
                    f"   {idx}. {first_name} - {username_display} - {status}\n"
                )
        else:
            response += "👥 <i>Участников нет</i>\n"

        response += "\n"

    # Add enhanced pagination keyboard with jump-by-4 buttons
    from bot.utils.keyboards import get_statistics_pagination_keyboard
    keyboard = get_statistics_pagination_keyboard(page, total_pages, order_by, region)
    
    await callback.message.edit_text(response, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@admin_router.callback_query(F.data == "admin_test_notifications")
async def handle_test_notifications(callback: types.CallbackQuery):
    """Handle test notifications request"""
    user_id = callback.from_user.id

    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("❌ Access denied.", show_alert=True)
        return

    await callback.answer("🔔 Testing notifications...")

    # Import here to avoid circular imports
    from bot.utils.notifications import NotificationScheduler

    if not db or not db.pool:
        await callback.message.edit_text(
            "❌ <b>Test Notifications Failed</b>\n\n"
            "Database is not available.",
            parse_mode="HTML"
        )
        return

    try:
        # Create a temporary scheduler for testing
        test_scheduler = NotificationScheduler(callback.bot, db, settings)

        await callback.message.edit_text(
            "🧪 <b>Running Test Notifications</b>\n\n"
            "Checking for users needing reminders and overdue warnings...\n"
            "This may take a few seconds.",
            parse_mode="HTML"
        )

        # Run the notification checks
        await test_scheduler.send_test_notifications()

        await callback.message.edit_text(
            "✅ <b>Test Notifications Complete</b>\n\n"
            "Check the bot logs for details about sent notifications.\n\n"
            "💡 <b>Note:</b> Notifications are sent automatically daily at 9:00 AM.",
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"❌ Test notifications failed: {e}")
        await callback.message.edit_text(
            f"❌ <b>Test Notifications Failed</b>\n\n"
            f"Error: {str(e)}\n\n"
            f"Check the bot logs for more details.",
            parse_mode="HTML"
        )


@admin_router.message(Command("test_receipt_storage"))
async def test_receipt_storage_command(message: types.Message):
    """Test receipt storage configuration"""
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await message.answer("❌ Доступ запрещён. Команда только для администраторов.")
        return

    if not settings.tg_receipt_storage_chat_id:
        await message.answer(
            "⚠️ <b>Хранилище чеков не настроено</b>\n\n"
            "Для включения функции хранения чеков:\n"
            "1. Создайте приватный чат/группу для хранения чеков\n"
            "2. Получите Chat ID этого чата\n"
            "3. Добавьте в .env файл:\n"
            "<code>TG_RECEIPT_STORAGE_CHAT_ID=ваш_chat_id</code>\n\n"
            "📖 Подробные инструкции в файле RECEIPT_STORAGE_README.md",
            parse_mode="HTML"
        )
        return

    try:
        # Test sending message to storage chat
        test_message = (
            f"🧪 <b>ТЕСТ ХРАНИЛИЩА ЧЕКОВ</b>\n\n"
            f"✅ Соединение с хранилищем чеков успешно!\n"
            f"📅 Время теста: {format_datetime(get_now())}\n"
            f"👤 Инициатор: {message.from_user.first_name} (ID: {message.from_user.id})\n\n"
            f"💡 Это тестовое сообщение для проверки настроек."
        )

        await message.bot.send_message(
            chat_id=settings.tg_receipt_storage_chat_id,
            text=test_message,
            parse_mode="HTML"
        )

        await message.answer(
            f"✅ <b>Тест хранилища чеков прошёл успешно!</b>\n\n"
            f"📊 Chat ID: <code>{settings.tg_receipt_storage_chat_id}</code>\n"
            f"📨 Тестовое сообщение отправлено в хранилище\n\n"
            f"🔧 Все новые чеки будут автоматически пересылаться в это хранилище.",
            parse_mode="HTML"
        )

        logger.info(
            f"Receipt storage test successful for chat_id: {settings.tg_receipt_storage_chat_id}")

    except Exception as e:
        error_msg = str(e)
        await message.answer(
            f"❌ <b>Ошибка теста хранилища чеков</b>\n\n"
            f"📊 Chat ID: <code>{settings.tg_receipt_storage_chat_id}</code>\n"
            f"⚠️ Ошибка: {error_msg}\n\n"
            f"<b>Возможные причины:</b>\n"
            f"• Неверный Chat ID\n"
            f"• Бот не добавлен в целевой чат\n"
            f"• Нет прав на отправку сообщений\n"
            f"• Чат заблокирован или удалён\n\n"
            f"📖 Проверьте инструкции в RECEIPT_STORAGE_README.md",
            parse_mode="HTML"
        )

        logger.error(f"Receipt storage test failed: {e}")


@admin_router.message(Command("import_groups"))
async def import_groups_command(message: types.Message, state: FSMContext):
    """Handle /import_groups command for bulk group creation from Excel"""
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await message.answer("❌ Доступ запрещён. Команда только для администраторов.")
        return

    if not db or not db.pool:
        await message.answer("❌ База данных в настоящее время недоступна.")
        return

    await state.set_state(AdminStates.importing_groups_file)
    await message.answer(
        "📊 <b>Импорт групп из Excel файла</b>\n\n"
        "Отправьте Excel файл (.xlsx) с данными для импорта групп.\n\n"
        "<b>Формат файла:</b>\n"
        "• Столбец A: Названия групп (например: spotify 001)\n"
        "• Столбец B: ID групп (например: 001)\n\n"
        "<b>Пример:</b>\n"
        "<pre>\n"
        "spotify 001 | 001\n"
        "spotify 002 | 002\n"
        "</pre>\n\n"
        "📎 Прикрепите файл к следующему сообщению:",
        parse_mode="HTML"
    )


@admin_router.message(AdminStates.importing_groups_file, F.document)
async def handle_import_file(message: types.Message, state: FSMContext):
    """Handle Excel file upload for group import"""
    file_path = None
    try:
        if not message.document:
            await message.answer("❌ Пожалуйста, отправьте файл.")
            return

        # Check file extension
        file_name = message.document.file_name
        if not file_name or not file_name.lower().endswith('.xlsx'):
            await message.answer(
                "❌ Неподдерживаемый формат файла.\n"
                "Пожалуйста, отправьте Excel файл (.xlsx)."
            )
            return

        # Check file size (limit to 10MB)
        if message.document.file_size > 10 * 1024 * 1024:
            await message.answer("❌ Файл слишком большой. Максимальный размер: 10 MB.")
            return

        await message.answer("⏳ Обработка файла...")

        # Download file
        file = await message.bot.get_file(message.document.file_id)

        # Create temporary file with proper extension
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as temp_file:
            file_path = temp_file.name

        await message.bot.download_file(file.file_path, file_path)

        # Parse Excel file
        from openpyxl import load_workbook

        try:
            workbook = load_workbook(file_path)
            sheet = workbook.active

            groups_data = []
            errors = []

            for row_num, row in enumerate(sheet.iter_rows(min_row=1, values_only=True), 1):
                if not row or len(row) < 2:
                    continue

                group_name = str(row[0]).strip() if row[0] else ""
                group_id = str(row[1]).strip() if row[1] else ""

                # Skip header row (if first row contains non-numeric ID)
                if row_num == 1 and not group_id.isdigit():
                    continue

                if not group_name or not group_id:
                    errors.append(f"Строка {row_num}: пустые данные")
                    continue

                # Validate group ID format (should be 3 digits)
                if not group_id.isdigit() or len(group_id) != 3:
                    errors.append(
                        f"Строка {row_num}: ID должен быть 3-значным числом")
                    continue

                groups_data.append({
                    'name': group_name,
                    'display_id': group_id,  # Keep as string for VARCHAR(10)
                    'row': row_num
                })

            if not groups_data:
                await message.answer("❌ В файле не найдено валидных данных для импорта.")
                await state.clear()
                return

            # Check for duplicate IDs in file
            display_ids = [group['display_id'] for group in groups_data]
            if len(display_ids) != len(set(display_ids)):
                errors.append("Обнаружены дублирующиеся ID в файле")

            # Check for existing groups in database
            existing_display_ids = []
            for group_data in groups_data:
                existing_group = await db.get_group_by_display_id(group_data['display_id'])
                if existing_group:
                    existing_display_ids.append(group_data['display_id'])

            if existing_display_ids:
                errors.append(
                    f"ID уже существуют в базе: {', '.join(map(str, existing_display_ids))}")

            # Store data for confirmation
            await state.update_data(groups_data=groups_data, errors=errors)

            # Show preview
            preview_text = "📋 <b>Предварительный просмотр импорта:</b>\n\n"
            preview_text += f"✅ Найдено групп для импорта: {len(groups_data)}\n\n"

            if errors:
                preview_text += f"⚠️ <b>Ошибки ({len(errors)}):</b>\n"
                for error in errors[:5]:  # Show first 5 errors
                    preview_text += f"• {error}\n"
                if len(errors) > 5:
                    preview_text += f"• ... и ещё {len(errors) - 5} ошибок\n"
                preview_text += "\n"

            if groups_data and not errors:
                preview_text += "<b>Группы для создания:</b>\n"
                for i, group in enumerate(groups_data[:10]):  # Show first 10
                    preview_text += f"• {group['name']} (ID: {group['display_id']})\n"
                if len(groups_data) > 10:
                    preview_text += f"• ... и ещё {len(groups_data) - 10} групп\n"

                await state.set_state(AdminStates.importing_groups_confirm)

                # Create custom keyboard for import confirmation
                builder = InlineKeyboardBuilder()
                builder.row(
                    types.InlineKeyboardButton(
                        text="✅ Да", callback_data="confirm_yes", style="success"),
                    types.InlineKeyboardButton(
                        text="❌ Нет", callback_data="confirm_no", style="danger")
                )

                await message.answer(
                    preview_text,
                    parse_mode="HTML",
                    reply_markup=builder.as_markup()
                )
            else:
                await message.answer(
                    preview_text + "\n❌ Импорт невозможен из-за ошибок в данных.",
                    parse_mode="HTML"
                )
                await state.clear()

        except Exception as e:
            logger.error(f"Error parsing Excel file: {e}")
            await message.answer(
                "❌ Ошибка при обработке файла.\n"
                "Убедитесь, что файл не повреждён и соответствует требуемому формату."
            )
            await state.clear()

        finally:
            # Clean up temp file
            if file_path and os.path.exists(file_path):
                try:
                    os.unlink(file_path)
                except Exception as cleanup_error:
                    logger.warning(
                        f"Failed to cleanup temp file {file_path}: {cleanup_error}")

    except Exception as e:
        logger.error(f"Error in handle_import_file: {e}")
        await message.answer("❌ Произошла ошибка при обработке файла.")
        await state.clear()
        # Cleanup file if it exists
        if 'file_path' in locals() and file_path and os.path.exists(file_path):
            try:
                os.unlink(file_path)
            except:
                pass


@admin_router.message(AdminStates.importing_groups_file)
async def handle_import_file_invalid(message: types.Message):
    """Handle invalid file uploads during import"""
    await message.answer(
        "❌ Пожалуйста, отправьте Excel файл (.xlsx).\n"
        "Или используйте /admin для отмены операции."
    )


@admin_router.callback_query(AdminStates.importing_groups_confirm, F.data == "confirm_yes")
async def confirm_import_groups(callback: types.CallbackQuery, state: FSMContext):
    """Confirm and execute group import"""
    try:
        data = await state.get_data()
        groups_data = data.get('groups_data', [])

        if not groups_data:
            await callback.message.edit_text("❌ Данные для импорта не найдены.")
            await state.clear()
            return

        await callback.message.edit_text("⏳ Импорт групп в процессе...")

        # Import groups
        success_count = await db.bulk_import_groups(groups_data)

        await callback.message.edit_text(
            f"✅ <b>Импорт завершён!</b>\n\n"
            f"Успешно создано групп: {success_count} из {len(groups_data)}\n\n"
            f"Используйте /admin для управления группами.",
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Error in confirm_import_groups: {e}")
        await callback.message.edit_text("❌ Произошла ошибка при импорте групп.")

    finally:
        await state.clear()


@admin_router.callback_query(AdminStates.importing_groups_confirm, F.data == "confirm_no")
async def cancel_import_groups(callback: types.CallbackQuery, state: FSMContext):
    """Cancel group import"""
    await callback.message.edit_text("❌ Импорт групп отменён.")
    await state.clear()


@admin_router.callback_query(F.data == "admin_delete_group")
async def delete_group_start(callback: types.CallbackQuery, state: FSMContext):
    """Start group deletion process - page 0"""
    await delete_group_page(callback, state, page=0)


@admin_router.callback_query(F.data.startswith("delete_group_page_"))
async def delete_group_page_handler(callback: types.CallbackQuery, state: FSMContext):
    """Handle pagination for delete group"""
    page = int(callback.data.split("_")[-1])
    await delete_group_page(callback, state, page)


async def delete_group_page(callback: types.CallbackQuery, state: FSMContext, page: int = 0):
    """Show paginated group list for deletion"""
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    # Show available groups
    groups = await db.get_all_groups()
    if not groups:
        await callback.message.edit_text("❌ Нет доступных групп для удаления.")
        return

    # Pagination settings
    GROUPS_PER_PAGE = 5
    total_groups = len(groups)
    total_pages = (total_groups + GROUPS_PER_PAGE - 1) // GROUPS_PER_PAGE

    # Validate page number
    if page < 0 or page >= total_pages:
        page = 0

    # Get groups for current page
    start_idx = page * GROUPS_PER_PAGE
    end_idx = min(start_idx + GROUPS_PER_PAGE, total_groups)
    page_groups = groups[start_idx:end_idx]

    groups_text = f"🗑️ <b>Удаление группы (стр. {page + 1}/{total_pages})</b>\n\n"
    groups_text += "⚠️ <b>ВНИМАНИЕ</b>: Удаление группы необратимо!\n"
    groups_text += "Будут удалены:\n• Все участники группы\n• История платежей\n• Все связанные данные\n\n"
    groups_text += "Доступные группы:\n\n"

    for group in page_groups:
        # Get member count
        members = await db.get_group_members(group.group_id)
        member_count = len(members)

        groups_text += (
            f"🏷️ <b>{group.group_name}</b> (ID: {group.display_id})\n"
            f"👥 Участников: {member_count}\n"
            f"📅 Следующий платёж: {format_date(group.next_payment_date)}\n\n"
        )

    groups_text += "Введите название группы или ID для удаления (например: 'spotify 001' или '001'):\n\n"
    groups_text += "💡 <i>Используйте /admin для отмены операции</i>"

    # Add pagination keyboard
    keyboard = get_pagination_keyboard(
        page, total_pages, "delete_group", show_back=True)

    await callback.message.edit_text(groups_text, parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(AdminStates.deleting_group_select)
    await callback.answer()


@admin_router.message(StateFilter(AdminStates.deleting_group_select))
async def delete_group_confirm(message: types.Message, state: FSMContext):
    """Confirm group deletion"""
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        return

    identifier = message.text.strip()

    # Find the group by name or display ID
    group = await db.get_group_by_name_or_id(identifier)
    if not group:
        await message.answer(
            f"❌ Группа '{identifier}' не найдена.\n\n"
            f"Проверьте название или ID и попробуйте снова, или используйте /admin для отмены."
        )
        return

    # Get members for confirmation
    members = await db.get_group_members(group.group_id)
    member_count = len(members)

    # Store group info for confirmation
    await state.update_data(group=group, member_count=member_count)

    confirmation_text = (
        f"⚠️ <b>ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ</b>\n\n"
        f"Вы действительно хотите удалить группу?\n\n"
        f"🏷️ <b>Группа</b>: {group.group_name} (ID: {group.display_id})\n"
        f"👥 <b>Участников</b>: {member_count}\n"
        f"📅 <b>Дата платежа</b>: {format_date(group.next_payment_date)}\n\n"
        f"🚨 <b>ЭТО ДЕЙСТВИЕ НЕОБРАТИМО!</b>\n"
        f"Будут удалены:\n"
        f"• Все {member_count} участников\n"
        f"• Вся история платежей\n"
        f"• Все связанные данные\n\n"
        f"Вы уверены?"
    )

    # Create confirmation keyboard
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="🗑️ ДА, УДАЛИТЬ", callback_data="confirm_delete_group", style="danger"),
        types.InlineKeyboardButton(
            text="❌ Отменить", callback_data="cancel_delete_group", style="danger")
    )

    await message.answer(
        confirmation_text,
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

    await state.set_state(AdminStates.deleting_group_confirm)


@admin_router.callback_query(AdminStates.deleting_group_confirm, F.data == "confirm_delete_group")
async def execute_group_deletion(callback: types.CallbackQuery, state: FSMContext):
    """Execute group deletion"""
    try:
        data = await state.get_data()
        group = data.get('group')
        member_count = data.get('member_count', 0)

        if not group:
            await callback.message.edit_text("❌ Данные группы не найдены.")
            await state.clear()
            return

        await callback.message.edit_text("⏳ Удаление группы...")

        # Delete the group
        success = await db.delete_group(group.group_id)

        if success:
            await callback.message.edit_text(
                f"✅ <b>Группа успешно удалена!</b>\n\n"
                f"🗑️ Удалена группа: {group.group_name} (ID: {group.display_id})\n"
                f"👥 Удалено участников: {member_count}\n"
                f"📅 Время удаления: {format_datetime(get_now())}\n\n"
                f"Все связанные данные были удалены из базы данных.",
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                f"❌ <b>Ошибка при удалении группы</b>\n\n"
                f"Не удалось удалить группу {group.group_name}.\n"
                f"Пожалуйста, попробуйте позже или обратитесь к техподдержке.",
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error(f"Error in execute_group_deletion: {e}")
        await callback.message.edit_text("❌ Произошла ошибка при удалении группы.")

    finally:
        await state.clear()


@admin_router.callback_query(AdminStates.deleting_group_confirm, F.data == "cancel_delete_group")
async def cancel_group_deletion(callback: types.CallbackQuery, state: FSMContext):
    """Cancel group deletion"""
    await callback.message.edit_text("❌ Удаление группы отменено.")
    await state.clear()


@admin_router.callback_query(F.data == "admin_manage_members")
async def manage_members_start(callback: types.CallbackQuery, state: FSMContext):
    """Start member management - page 0"""
    await manage_members_page(callback, state, page=0)


@admin_router.callback_query(F.data.startswith("manage_members_page_"))
async def manage_members_page_handler(callback: types.CallbackQuery, state: FSMContext):
    """Handle pagination for manage members"""
    page = int(callback.data.split("_")[-1])
    await manage_members_page(callback, state, page)


async def manage_members_page(callback: types.CallbackQuery, state: FSMContext, page: int = 0):
    """Show paginated group list for member management"""
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    groups = await db.get_all_groups()
    if not groups:
        await callback.message.edit_text("❌ Нет доступных групп.")
        return

    # Pagination settings
    GROUPS_PER_PAGE = 5
    total_groups = len(groups)
    total_pages = (total_groups + GROUPS_PER_PAGE - 1) // GROUPS_PER_PAGE

    # Validate page number
    if page < 0 or page >= total_pages:
        page = 0

    # Get groups for current page
    start_idx = page * GROUPS_PER_PAGE
    end_idx = min(start_idx + GROUPS_PER_PAGE, total_groups)
    page_groups = groups[start_idx:end_idx]

    groups_text = f"👥 <b>Управление участниками групп (стр. {page + 1}/{total_pages})</b>\n\n"
    groups_text += "Выберите группу для просмотра участников:\n\n"

    for group in page_groups:
        members = await db.get_group_members(group.group_id)
        member_count = len(members)

        groups_text += (
            f"🏷️ <b>{group.group_name}</b> (ID: {group.display_id})\n"
            f"👥 Участников: {member_count}\n\n"
        )

    groups_text += "Введите название группы или ID (например: 'spotify 001' или '001'):\n\n"
    groups_text += "💡 <i>Используйте /admin для отмены операции</i>"

    # Add pagination keyboard
    keyboard = get_pagination_keyboard(
        page, total_pages, "manage_members", show_back=True)

    await callback.message.edit_text(groups_text, parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(AdminStates.removing_user_select_group)
    await callback.answer()


@admin_router.message(StateFilter(AdminStates.removing_user_select_group))
async def show_group_members(message: types.Message, state: FSMContext):
    """Show group members and management options"""
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        return

    identifier = message.text.strip()

    group = await db.get_group_by_name_or_id(identifier)
    if not group:
        await message.answer(
            f"❌ Группа '{identifier}' не найдена.\n\n"
            f"Проверьте название или ID и попробуйте снова, или используйте /admin для отмены."
        )
        return

    members = await db.get_group_members(group.group_id)

    if not members:
        await message.answer(
            f"📭 <b>Группа {group.group_name} пуста</b>\n\n"
            f"В этой группе пока нет участников.",
            parse_mode="HTML"
        )
        await state.clear()
        return

    members_text = (
        f"👥 <b>Участники группы {group.group_name}</b>\n"
        f"🆔 ID группы: {group.display_id}\n\n"
    )

    for member in members:
        from html import escape
        last_payment = "Никогда" if not member['last_payment'] else member['last_payment'].strftime(
            '%Y-%m-%d')
        username_display = f"@{escape(member['username'])}" if member['username'] else 'нет username'
        first_name = escape(member['first_name'] or 'N/A')

        slots = member.get('slots', 1)
        slots_line = f"🔢 Слотов: {slots}\n" if slots > 1 else ""
        members_text += (
            f"👤 <b>{first_name}</b> ({username_display})\n"
            f"🆔 ID: {member['display_id']} | Telegram ID: <code>{member['user_id']}</code>\n"
            f"💳 Платежей: {member['total_payments']} | Последний: {last_payment}\n"
            f"{slots_line}\n"
        )

    members_text += f"Всего участников: {len(members)}\n\n"
    members_text += "Для удаления пользователя из группы введите его Telegram ID:"

    await message.answer(members_text, parse_mode="HTML")
    await state.update_data(group=group)
    await state.set_state(AdminStates.removing_user_select_user)


@admin_router.message(StateFilter(AdminStates.removing_user_select_user))
async def remove_user_from_group(message: types.Message, state: FSMContext):
    """Remove selected user from group"""
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        return

    if message.text and message.text.strip().lower() in ('/admin', '/cancel'):
        await state.clear()
        await message.answer("✅ Управление участниками завершено. Используйте /admin для панели.")
        return

    try:
        target_user_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Неверный формат ID. Введите числовой Telegram ID пользователя.\n"
            "Используйте /admin для выхода."
        )
        return

    data = await state.get_data()
    group = data.get('group')

    if not group:
        await message.answer("❌ Данные группы не найдены. Попробуйте снова.")
        await state.clear()
        return

    # Check if user is in the group
    members = await db.get_group_members(group.group_id)
    target_member = next(
        (m for m in members if m['user_id'] == target_user_id), None)

    if not target_member:
        await message.answer(
            f"❌ Пользователь с ID {target_user_id} не найден в группе {group.group_name}.\n\n"
            f"Введите другой ID или /admin для выхода."
        )
        return

    # Remove user from group
    success = await db.remove_user_from_group(target_user_id, group.group_id)

    if success:
        await message.answer(
            f"✅ <b>Пользователь удалён из группы!</b>\n\n"
            f"👤 Пользователь: {target_member['first_name']} (@{target_member['username'] or 'нет'})\n"
            f"🆔 ID: {target_member['display_id']}\n"
            f"🏷️ Группа: {group.group_name}\n"
            f"📅 Время удаления: {format_datetime(get_now())}",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"❌ <b>Ошибка при удалении пользователя</b>\n\n"
            f"Не удалось удалить пользователя из группы.",
            parse_mode="HTML"
        )
        return

    # Re-fetch and show updated member list so admin can continue
    members = await db.get_group_members(group.group_id)

    if not members:
        await message.answer(
            f"📭 <b>Группа {group.group_name} теперь пуста.</b>\n\n"
            f"Используйте /admin для возврата в меню.",
            parse_mode="HTML"
        )
        await state.clear()
        return

    from html import escape
    members_text = (
        f"👥 <b>Участники группы {group.group_name}</b> (осталось: {len(members)})\n\n"
    )
    for member in members:
        last_payment = "Никогда" if not member['last_payment'] else member['last_payment'].strftime('%Y-%m-%d')
        username_display = f"@{escape(member['username'])}" if member['username'] else 'нет username'
        first_name = escape(member['first_name'] or 'N/A')
        slots = member.get('slots', 1)
        slots_line = f"🔢 Слотов: {slots}\n" if slots > 1 else ""
        members_text += (
            f"👤 <b>{first_name}</b> ({username_display})\n"
            f"🆔 ID: {member['display_id']} | Telegram ID: <code>{member['user_id']}</code>\n"
            f"💳 Платежей: {member['total_payments']} | Последний: {last_payment}\n"
            f"{slots_line}\n"
        )
    members_text += "Введите Telegram ID следующего участника для удаления или /admin для выхода:"

    await message.answer(members_text, parse_mode="HTML")


@admin_router.callback_query(F.data == "back_to_admin_menu")
async def back_to_admin_menu(callback: types.CallbackQuery):
    """Return to admin main menu"""
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    await callback.message.edit_text(
        "🔧 <b>Панель администратора</b>\n\n"
        "Выберите действие:",
        reply_markup=get_admin_main_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.callback_query(F.data == "noop")
async def noop_handler(callback: types.CallbackQuery):
    """Handle no-operation callbacks (like page indicators)"""
    await callback.answer()


# Handle any unrecognized admin callback
@admin_router.callback_query(F.data.startswith("admin_"))
async def handle_unknown_admin_action(callback: types.CallbackQuery):
    """Handle unknown admin actions"""
    await callback.answer("This feature is not implemented yet.", show_alert=True)
@admin_router.message(Command("fraudcheck"))
async def fraud_check_command(message: types.Message, state: FSMContext):
    """Handle /fraudcheck command - KZ Only (starts with '0')"""
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await message.answer("❌ Доступ запрещён. Команда только для администраторов.")
        return

    if not db or not db.pool:
        await message.answer("❌ База данных недоступна.")
        return

    await message.answer(
        "🕵️‍♀️ <b>Проверка на мошенничество (Fraud Check)</b>\n\n"
        "Пожалуйста, введите <b>дату начала</b> проверки в формате <b>ДД.ММ</b>\n"
        "(Например: <code>01.02</code> для 1 февраля текущего года).\n\n"
        "Бот сверит операции из выписки с базой данных (только для групп Казахстана).\n\n"
        "💡 <i>Используйте /admin для отмены</i>",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.fraud_check_date)


@admin_router.message(StateFilter(AdminStates.fraud_check_date))
async def fraud_check_date_process(message: types.Message, state: FSMContext):
    """Process date input for fraud check"""
    try:
        # Parse date. format is DD.MM
        date_str = message.text.strip()
        parts = date_str.split('.')
        # Allow DD.MM.YYYY too
        year = get_now().year
        
        day = int(parts[0])
        month = int(parts[1])
        if len(parts) == 3:
            year = int(parts[2])
            
        # Create date object
        start_date = datetime(year, month, day, 0, 0, 0)
        
        # Save to state (store as string isoformat)
        await state.update_data(fraud_check_start_date=start_date.isoformat())
        
        # Format for nicer display
        display_date = f"{day:02d}.{month:02d}.{year}"
        
        await message.answer(
            f"✅ Дата начала установлена: <b>{display_date}</b>\n\n"
            "📥 Теперь отправьте файл выписки Kaspi (Excel .xlsx или .csv).",
            parse_mode="HTML"
        )
        await state.set_state(AdminStates.fraud_check_file)
        
    except Exception as e:
        await message.answer(
            "❌ <b>Неверный формат даты!</b>\n"
            "Используйте формат <code>ДД.ММ</code> (например: <code>01.02</code>).\n"
            "Попробуйте снова."
        )


@admin_router.message(StateFilter(AdminStates.fraud_check_file), F.document)
async def fraud_check_process(message: types.Message, state: FSMContext):
    """Process fraud check statement file"""
    document = message.document
    file_name = document.file_name.lower()
    
    if not (file_name.endswith('.xlsx') or file_name.endswith('.xls') or file_name.endswith('.csv')):
        await message.answer(
            "❌ Неверный формат файла. Пожалуйста, отправьте Excel (.xlsx) или CSV файл."
        )
        return

    # Retrieve date from state
    data = await state.get_data()
    start_date_iso = data.get('fraud_check_start_date')
    
    if start_date_iso:
        current_month_start = datetime.fromisoformat(start_date_iso)
    else:
        # Fallback (should not happen normally)
        current_month_start = get_now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    start_date_display = current_month_start.strftime("%d.%m.%Y")
    await message.answer(f"⏳ Обработка файла и сверка данных с {start_date_display}...")

    import tempfile
    import os
    from bot.utils.receipt_parser import load_kaspi_statement

    try:
        # Download statement
        file = await message.bot.get_file(document.file_id)
        
        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(file_name)[1], delete=False) as temp_file:
            temp_file_name = temp_file.name
            
        await message.bot.download_file(file.file_path, temp_file_name)
        
        # Parse statement
        statement_ops = load_kaspi_statement(temp_file_name)
        
        try:
             os.remove(temp_file_name)
        except OSError:
             pass
        
        if not statement_ops:
            await message.answer("❌ Не удалось найти операции в файле или файл пуст.")
            await state.clear()
            return

        # Fetch all relevant payments from DB (KZ groups only, with accumulated op_numbers)
        # current_month_start is already set from FSM state above (user-selected date)
        async with db.pool.acquire() as conn:
             # Groups starting with '0' are KZ
             # We want payments that HAVE an op number
             # JOIN users table to get username
            rows = await conn.fetch(
                """
                SELECT 
                    p.payment_id, 
                    p.payment_date, 
                    p.receipt_op_number, 
                    p.user_id, 
                    g.group_name,
                    u.username
                FROM payments p
                JOIN groups g ON p.group_id = g.group_id
                JOIN users u ON p.user_id = u.user_id
                WHERE p.receipt_op_number IS NOT NULL
                AND g.display_id LIKE '0%'
                AND p.payment_date >= $1
                ORDER BY p.payment_date DESC
                """,
                current_month_start
            )
            
        frauds = []
        
        for row in rows:
            op_num = row['receipt_op_number']
            # Normalize just in case
            norm_op = str(op_num).replace("QR", "").replace(" ", "").strip()
            
            if norm_op not in statement_ops:
                # Format user display name: ID (copyable) + @username
                user_id_display = f"<code>{row['user_id']}</code>"
                if row['username']:
                    user_display = f"ID: {user_id_display} (@{row['username']})"
                else:
                    user_display = f"ID: {user_id_display}"
                    
                frauds.append({
                    'date': row['payment_date'],
                    'op': op_num,
                    'user': user_display,
                    'group': row['group_name']
                })

        if not frauds:
            await message.answer(
                f"✅ <b>Всё чисто!</b>\n\n"
                f"Проверено {len(rows)} платежей за этот месяц.\n"
                f"Все номера квитанций найдены в выписке.",
                parse_mode="HTML"
            )
        else:
            report_lines = [f"⚠️ <b>Подозрительные платежи ({len(frauds)}):</b>\n"]
            report_lines.append("(Есть в базе, но НЕТ в выписке)\n")
            
            for f in frauds:
                dt = format_datetime(f['date'])
                report_lines.append(f"• {dt} | {f['group']}")
                report_lines.append(f"  👤 {f['user']}")
                report_lines.append(f"  🧾 <code>{f['op']}</code>")
                report_lines.append("")
                
            report = "\n".join(report_lines)
            
            # Split if too long
            if len(report) > 4000:
                report = report[:4000] + "\n...(обрезано)"
                
            await message.answer(report, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Fraud check error: {e}")
        await message.answer(f"❌ Ошибка проверки: {e}")
    
    await state.clear()


@admin_router.message(Command("backfill_receipts"))
async def backfill_receipts_command(message: types.Message):
    """Backfill missing receipt numbers from files (Feb 2026+)"""
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await message.answer("❌ Доступ запрещён.")
        return

    await message.answer("⏳ Начинаю сканирование старых чеков (с 01.02.2026)...")
    
    try:
        # Get candidates: KZ payments (0%), since Feb 1st, with file but no op number
        candidates = await db.get_payments_without_op_number(region='kz', start_date='2026-02-01')
        
        if not candidates:
            await message.answer("✅ Нет чеков для обработки.")
            return

        total = len(candidates)
        await message.answer(f"Найдено {total} чеков. Обработка...")
        
        import tempfile
        import os
        from bot.utils.receipt_parser import parse_kaspi_receipt
        
        updated_count = 0
        failed_count = 0
        
        for i, p in enumerate(candidates, 1):
            try:
                # Progress update every 5 items
                if i % 5 == 0:
                   await message.bot.send_chat_action(message.chat.id, "typing")
                   
                file_id = p['receipt_file_id']
                payment_id = p['payment_id']
                
                # Download
                file = await message.bot.get_file(file_id)
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
                    temp_name = temp_file.name
                
                await message.bot.download_file(file.file_path, temp_name)
                
                # Parse
                op_number = parse_kaspi_receipt(temp_name)
                
                try:
                    os.remove(temp_name)
                except OSError:
                    pass
                
                if op_number:
                    await db.update_payment_op_number(payment_id, op_number)
                    updated_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"Backfill error payment {p.get('payment_id')}: {e}")
                failed_count += 1

        await message.answer(
            f"🏁 <b>Обработка завершена</b>\n\n"
            f"Всего: {total}\n"
            f"✅ Распознано: {updated_count}\n"
            f"❌ Не распознано: {failed_count}",
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Backfill fatal error: {e}")
        await message.answer(f"❌ Критическая ошибка: {e}")


# ──────────────────────────────────────────────
# /setslots — set number of accounts (slots) for a user in a group
# ──────────────────────────────────────────────

@admin_router.message(Command("setslots"))
async def setslots_command(message: types.Message, state: FSMContext):
    """Start setslots flow: ask which group."""
    if message.chat.type != ChatType.PRIVATE:
        return
    if not is_admin(message.from_user.id, settings.tg_admin_ids):
        return

    await message.answer(
        "🔢 <b>Изменение слотов пользователя</b>\n\n"
        "Введите название или ID группы:\n\n"
        "💡 <i>Используйте /admin для отмены</i>",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.setting_slots_group)


@admin_router.message(StateFilter(AdminStates.setting_slots_group))
async def setslots_get_group(message: types.Message, state: FSMContext):
    """Receive group, show members, ask for user+slots input."""
    if message.chat.type != ChatType.PRIVATE:
        return
    if not is_admin(message.from_user.id, settings.tg_admin_ids):
        return

    group = await db.get_group_by_name_or_id(message.text.strip())
    if not group:
        await message.answer(
            f"❌ Группа '{message.text.strip()}' не найдена. Попробуйте снова."
        )
        return

    members = await db.get_group_members(group.group_id)
    if not members:
        await message.answer(
            f"📭 Группа {group.group_name} пуста.",
            parse_mode="HTML"
        )
        await state.clear()
        return

    text = (
        f"👥 <b>Участники группы {group.group_name}</b>\n\n"
    )
    for m in members:
        slots = m.get('slots', 1)
        name = m['first_name'] or 'N/A'
        username = f"@{m['username']}" if m['username'] else 'нет username'
        text += (
            f"• <b>{name}</b> ({username}) — "
            f"ID: <code>{m['user_id']}</code> — Слотов: {slots}\n"
        )

    text += (
        "\n\nВведите: <code>telegram_id количество_слотов</code>\n"
        "Пример: <code>123456789 2</code>"
    )

    await message.answer(text, parse_mode="HTML")
    await state.update_data(setslots_group=group)
    await state.set_state(AdminStates.setting_slots_user)


@admin_router.message(StateFilter(AdminStates.setting_slots_user))
async def setslots_apply(message: types.Message, state: FSMContext):
    """Parse user_id + slots and apply."""
    if message.chat.type != ChatType.PRIVATE:
        return
    if not is_admin(message.from_user.id, settings.tg_admin_ids):
        return

    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer(
            "❌ Неверный формат. Введите: <code>telegram_id количество_слотов</code>\n"
            "Пример: <code>123456789 2</code>",
            parse_mode="HTML"
        )
        return

    try:
        target_user_id = int(parts[0])
        new_slots = int(parts[1])
    except ValueError:
        await message.answer("❌ Оба значения должны быть числами.")
        return

    if new_slots < 1:
        await message.answer("❌ Количество слотов должно быть не менее 1.")
        return

    data = await state.get_data()
    group = data.get('setslots_group')
    if not group:
        await message.answer("❌ Данные группы потеряны. Начните заново.")
        await state.clear()
        return

    # Verify user is actually in this group
    members = await db.get_group_members(group.group_id)
    member = next((m for m in members if m['user_id'] == target_user_id), None)
    if not member:
        await message.answer(
            f"❌ Пользователь {target_user_id} не найден в группе {group.group_name}."
        )
        return

    success = await db.set_user_slots(target_user_id, group.group_id, new_slots)
    await state.clear()

    if success:
        # Calculate monthly amount for confirmation
        region = get_region_from_group_id(group.display_id)
        payment_info = get_payment_info(region, settings)
        monthly = payment_info['price'] * new_slots
        currency = payment_info['currency']

        name = member['first_name'] or 'N/A'
        username = f"@{member['username']}" if member['username'] else 'нет username'
        await message.answer(
            f"✅ <b>Слоты обновлены</b>\n\n"
            f"👤 Пользователь: <b>{name}</b> ({username})\n"
            f"👥 Группа: {group.group_name}\n"
            f"🔢 Слотов: {new_slots}\n"
            f"💰 Сумма оплаты: {monthly} {currency}/мес",
            parse_mode="HTML"
        )
        logger.info(
            f"Admin {message.from_user.id} set slots={new_slots} "
            f"for user {target_user_id} in group {group.group_id}"
        )
    else:
        await message.answer("❌ Не удалось обновить слоты. Попробуйте снова.")


@admin_router.message(Command("notfull"))
async def cmd_notfull(message: types.Message):
    """Show groups with fewer than 6 members"""
    if message.chat.type != ChatType.PRIVATE:
        return
    if not is_admin(message.from_user.id, settings.tg_admin_ids):
        return

    groups = await db.get_groups_with_member_count()
    incomplete = [g for g in groups if g['member_count'] < 6]

    if not incomplete:
        await message.answer("✅ Все группы заполнены (6/6).")
        return

    lines = [f"<b>Группы не на 6 человек ({len(incomplete)}):</b>\n"]
    for g in incomplete:
        lines.append(
            f"📁 <b>{g['group_name']}</b> (ID: {g['display_id']}) — "
            f"{g['member_count']}/6"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")


@admin_router.message(Command("fixusers"))
async def cmd_fixusers(message: types.Message):
    """Fetch real Telegram info for users with corrupted usernames and fix them in DB"""
    if message.chat.type != ChatType.PRIVATE:
        return
    if not is_admin(message.from_user.id, settings.tg_admin_ids):
        return

    # Find users with fake auto-generated usernames
    corrupted = await db.get_corrupted_users()
    if not corrupted:
        await message.answer("✅ Нет пользователей с повреждёнными данными.")
        return

    await message.answer(f"🔄 Исправляю данные для {len(corrupted)} пользователей...")

    fixed = 0
    failed_ids = []
    for user_id in corrupted:
        try:
            chat = await message.bot.get_chat(user_id)
            username = chat.username or chat.first_name or "User"
            first_name = chat.first_name
            await db.add_user(user_id, username, first_name)
            fixed += 1
        except Exception:
            failed_ids.append(user_id)

    lines = [f"✅ Исправлено: {fixed}"]
    if failed_ids:
        lines.append(f"❌ Не удалось получить данные ({len(failed_ids)}):")
        for uid in failed_ids:
            lines.append(f"  • <code>{uid}</code>")
        lines.append("(пользователи не писали боту)")
    await message.answer("\n".join(lines), parse_mode="HTML")


@admin_router.message(Command("adminhelp"))
async def cmd_adminhelp(message: types.Message):
    """Show all available admin commands"""
    if message.chat.type != ChatType.PRIVATE:
        return
    if not is_admin(message.from_user.id, settings.tg_admin_ids):
        return

    await message.answer(
        "<b>📋 Команды администратора</b>\n"
        "\n"
        "<b>— Основные —</b>\n"
        "/admin — главное меню (группы, статистика, участники)\n"
        "/broadcast — отправить сообщение всем пользователям\n"
        "\n"
        "<b>— Пользователи и группы —</b>\n"
        "/setslots — установить количество слотов пользователю в группе\n"
        "/notfull — показать группы с менее чем 6 участниками\n"
        "/overdue — показать пользователей с просрочкой 3+ дней (под отключение)\n"
        "/paid_in_advance — показать пользователей, оплативших вперёд\n"
        "/update_due_date — обновить дату следующего платежа для группы\n"
        "/import_groups — импортировать группы из файла\n"
        "\n"
        "<b>— Проверки —</b>\n"
        "/fraudcheck — проверка дублей платежей по выписке Kaspi (KZ)\n"
        "/fraudcheck_ru — сверка платежей RU по дате (количество + сумма)\n"
        "/backfill_receipts — восстановить номера чеков из файлов\n"
        "/fixusers — исправить повреждённые имена пользователей через Telegram\n"
        "\n"
        "<b>— Уведомления (тест) —</b>\n"
        "/check_notifications — проверить статус уведомлений\n"
        "/test_notifications — тест рассылки уведомлений\n"
        "/test_admin_notification — тест уведомления для админа\n"
        "\n"
        "<b>— Прочее —</b>\n"
        "/link_group — привязать Telegram-чат к группе (в чате: /link_group 001)\n"
        "/adminhelp — эта справка\n",
        parse_mode="HTML"
    )


@admin_router.message(Command("overdue"))
async def cmd_overdue(message: types.Message):
    """Show all users overdue by more than 3 days"""
    if message.chat.type != ChatType.PRIVATE:
        return
    if not is_admin(message.from_user.id, settings.tg_admin_ids):
        return

    overdue = await db.get_users_overdue_for_admin_warning(3)

    if not overdue:
        await message.answer("✅ Нет пользователей с просрочкой более 3 дней.")
        return

    lines = [f"🚨 <b>Просрочка 3+ дней ({len(overdue)}):</b>\n"]
    for s in overdue:
        name = s.first_name or "N/A"
        username = f"@{s.username}" if s.username else "нет username"
        lines.append(
            f"👤 <b>{name}</b> ({username})\n"
            f"🆔 ID: {s.user_display_id} | <code>{s.user_id}</code>\n"
            f"👥 Группа: {s.group_name} ({s.group_display_id})\n"
            f"📅 Срок был: {format_date(s.next_payment_date)} | Просрочка: <b>{s.days_overdue} дн.</b>\n"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")


@admin_router.message(Command("fraudcheck_ru"))
async def fraudcheck_ru_start(message: types.Message, state: FSMContext):
    """Start RU fraud check — ask for date"""
    if message.chat.type != ChatType.PRIVATE:
        return
    if not is_admin(message.from_user.id, settings.tg_admin_ids):
        return

    await message.answer(
        "🇷🇺 <b>Проверка платежей RU</b>\n\n"
        "Введите дату для проверки (ДД.ММ.ГГГГ):\n"
        "Например: <code>04.03.2026</code>",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.ru_fraud_check_date)


@admin_router.message(StateFilter(AdminStates.ru_fraud_check_date))
async def fraudcheck_ru_process(message: types.Message, state: FSMContext):
    """Show RU payment checksum for the given date"""
    if message.chat.type != ChatType.PRIVATE:
        return
    if not is_admin(message.from_user.id, settings.tg_admin_ids):
        return

    await state.clear()

    text = message.text.strip()
    try:
        from datetime import datetime as dt
        check_date = dt.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте ДД.ММ.ГГГГ")
        return

    payments = await db.get_ru_payments_on_date(check_date)
    ru_price = settings.bot_ru_payment_price

    if not payments:
        await message.answer(
            f"📭 За <b>{text}</b> платежей от RU клиентов не найдено.",
            parse_mode="HTML"
        )
        return

    total_amount = 0
    lines = [f"🇷🇺 <b>Платежи RU за {text}</b>\n"]

    for p in payments:
        name = p['first_name'] or "N/A"
        username = f"@{p['username']}" if p['username'] else "нет username"
        slots = p['slots']
        months = p['months_paid']
        amount = ru_price * slots * months
        total_amount += amount

        slot_note = f" × {slots} слота" if slots > 1 else ""
        month_note = f" × {months} мес." if months > 1 else ""
        lines.append(
            f"👤 {name} ({username})\n"
            f"   🆔 {p['user_display_id']} | 👥 {p['group_display_id']}\n"
            f"   💰 {ru_price} ₽{slot_note}{month_note} = <b>{amount:.0f} ₽</b>\n"
        )

    lines.append(
        f"─────────────────\n"
        f"📊 Транзакций: <b>{len(payments)}</b>\n"
        f"💰 Ожидаемая сумма: <b>{total_amount:.0f} ₽</b>\n\n"
        f"Сверьте с выпиской банка.\n"
        f"Если суммы или количество не совпадают — возможен фрод."
    )

    await message.answer("\n".join(lines), parse_mode="HTML")
