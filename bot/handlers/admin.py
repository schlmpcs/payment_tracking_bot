"""
Admin command handlers for the Spotify Payment Bot
"""

import logging
import tempfile
import os
from datetime import datetime, timedelta
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.enums import ChatType
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.operations import Database
from bot.config.settings import Settings
from bot.utils.states import AdminStates
from bot.utils.keyboards import get_admin_main_keyboard, get_confirmation_keyboard
from bot.utils.helpers import (
    format_date, calculate_days_until,
    get_payment_status_emoji, get_payment_status_text,
    is_admin
)

# Initialize router
admin_router = Router()
logger = logging.getLogger(__name__)

# Global database instance (will be injected)
db: Database = None
settings: Settings = None


def init_admin_handlers(database: Database, bot_settings: Settings):
    """Initialize handlers with database and settings"""
    global db, settings
    db = database
    settings = bot_settings


@admin_router.message(Command("admin"))
async def admin_command(message: types.Message):
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
    
    await message.answer(
        "🔧 **Панель администратора**\n\n"
        "Выберите действие:",
        reply_markup=get_admin_main_keyboard(),
        parse_mode="Markdown"
    )


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
        
        response = "🔍 *Проверка статуса уведомлений*\n\n"
        
        if reminder_users:
            response += f"📬 *Пользователи, нуждающиеся в напоминаниях* ({len(reminder_users)}):\n"
            for status in reminder_users:
                response += f"• Пользователь {status.user_id} в '{status.group_name}'\n"
                response += f"  📅 Срок: {format_date(status.next_payment_date)}\n"
            response += "\n"
        else:
            response += "📭 Сегодня никому не нужны напоминания об оплате\n\n"
        
        if overdue_users:
            response += f"🚨 *Пользователи с просроченными платежами для предупреждения администратора* ({len(overdue_users)}):\n"
            for status in overdue_users:
                user_name = getattr(status, 'first_name', f'Пользователь {status.user_id}')
                response += f"• {user_name} в '{status.group_name}'\n"
                response += f"  📅 Срок был: {format_date(status.next_payment_date)}\n"
            response += "\n"
        else:
            response += "✅ Нет пользователей с просроченными предупреждениями\n\n"
        
        response += "💡 Используйте /test\\_notifications для фактической отправки этих уведомлений"
        
        await message.answer(response, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Check notifications failed: {e}")
        await message.answer(
            f"❌ *Проверка не удалась:*\n\n`{str(e)}`",
            parse_mode="Markdown"
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
            "✅ **Тестовые уведомления завершены!**\n\n"
            "Проверьте логи бота, чтобы увидеть, были ли отправлены уведомления.\n\n"
            "💡 **Напоминание:** Уведомления отправляются автоматически ежедневно в 9:00 утра.",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"❌ Test notifications failed: {e}")
        await message.answer(
            f"❌ **Тестовые уведомления не удались:**\n\n"
            f"`{str(e)}`\n\n"
            f"Проверьте логи бота для получения дополнительной информации.",
            parse_mode="Markdown"
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
    
    groups_text = "📅 **Обновить дату платежа группы**\n\n"
    groups_text += "Доступные группы:\n\n"
    
    for group in groups:
        days_until = calculate_days_until(group.next_payment_date)
        status_emoji = get_payment_status_emoji(days_until)
        
    for group in groups:
        days_until = calculate_days_until(group.next_payment_date)
        status_emoji = get_payment_status_emoji(days_until)
        
        groups_text += (
            f"{status_emoji} **{group.group_name}** (ID: {group.display_id})\n"
            f"📅 Текущая дата платежа: {format_date(group.next_payment_date)}\n"
            f"📊 Статус: {get_payment_status_text(days_until)}\n\n"
        )
    
    groups_text += "Пожалуйста, введите название группы, которую хотите обновить:"
    
    await message.answer(groups_text, parse_mode="Markdown")
    await state.set_state(AdminStates.updating_due_date_group)


@admin_router.callback_query(F.data == "admin_view_groups")
async def view_groups(callback: types.CallbackQuery):
    """View all payment groups"""
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    
    groups = await db.get_all_groups()
    
    if not groups:
        await callback.message.edit_text("📭 Группы оплаты не найдены.")
        return
    
    response = "👥 **Все группы оплаты:**\n\n"
    
    for group in groups:
        days_until = calculate_days_until(group.next_payment_date)
        emoji = get_payment_status_emoji(days_until)
        
        response += (
            f"{emoji} **{group.group_name}** (ID: {group.display_id})\n"
            f"📅 Следующий платёж: {format_date(group.next_payment_date)}\n"
            f"📊 Статус: {get_payment_status_text(days_until)}\n\n"
        )
    
    await callback.message.edit_text(response, parse_mode="Markdown")
    await callback.answer()


@admin_router.callback_query(F.data == "admin_overdue_users")
async def view_overdue_users(callback: types.CallbackQuery):
    """View users with overdue payments"""
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    
    overdue_users = await db.get_overdue_users()
    
    if not overdue_users:
        await callback.message.edit_text("✅ Просроченных платежей не найдено!")
        return
    
    response = "❌ **Просроченные платежи:**\n\n"
    
    for status in overdue_users:
        days_overdue = abs(calculate_days_until(status.next_payment_date))
        
        response += (
            f"👤 ID пользователя: {status.user_id}\n"
            f"👥 Группа: {status.group_name}\n"
            f"📅 Дата платежа: {format_date(status.next_payment_date)}\n"
            f"⏰ Просрочено: {days_overdue} дней\n\n"
        )
    
    await callback.message.edit_text(response, parse_mode="Markdown")
    await callback.answer()


@admin_router.callback_query(F.data == "admin_create_group")
async def create_group_start(callback: types.CallbackQuery, state: FSMContext):
    """Start group creation process"""
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    
    await callback.message.edit_text(
        "➕ **Создать новую группу**\n\n"
        "Пожалуйста, введите название группы:"
    )
    
    await state.set_state(AdminStates.creating_group)
    await callback.answer()


@admin_router.message(StateFilter(AdminStates.creating_group))
async def create_group_finish(message: types.Message, state: FSMContext):
    """Finish group creation"""
    if message.chat.type != ChatType.PRIVATE:
        return
    
    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        return
    
    group_name = message.text.strip()
    
    if not group_name:
        await message.answer("❌ Название группы не может быть пустым. Пожалуйста, попробуйте снова.")
        return
    
    # Create group with next display ID and formatted name
    next_payment_date = datetime.now() + timedelta(days=30)
    group_id = await db.create_group(group_name, next_payment_date)  # Function handles formatting internally
    
    if group_id:
        # Get the created group to show display_id
        created_groups = await db.get_all_groups() if db else []
        created_group = next((g for g in created_groups if g.group_id == group_id), None)
        
        await message.answer(
            f"✅ **Группа успешно создана!**\n\n"
            f"👥 Название группы: {created_group.group_name if created_group else 'N/A'}\n"
            f"🆔 ID группы: {created_group.display_id if created_group else 'N/A'}\n"
            f"📅 Дата следующего платежа: {format_date(next_payment_date)}",
            parse_mode="Markdown"
        )
        logger.info(f"Admin {user_id} created group (ID: {group_id})")
    else:
        await message.answer("❌ Не удалось создать группу. Пожалуйста, попробуйте снова.")
    
    await state.clear()


@admin_router.callback_query(F.data == "admin_add_user")
async def add_user_start(callback: types.CallbackQuery, state: FSMContext):
    """Start user addition process"""
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    
    await callback.message.edit_text(
        "👤 **Добавить пользователя в группу**\n\n"
        "Пожалуйста, введите Telegram ID пользователя (числовой):"
    )
    
    await state.set_state(AdminStates.adding_user_username)
    await callback.answer()


@admin_router.message(StateFilter(AdminStates.adding_user_username))
async def add_user_get_group(message: types.Message, state: FSMContext):
    """Get group for user addition"""
    if message.chat.type != ChatType.PRIVATE:
        return
    
    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        return
    
    try:
        target_user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Please enter a valid numeric user ID.")
        return
    
    await state.update_data(target_user_id=target_user_id)
    
    # Show available groups
    groups = await db.get_all_groups()
    if not groups:
        await message.answer("❌ No groups available. Create a group first.")
        await state.clear()
        return
    
    groups_text = "Available groups:\n\n"
    for group in groups:
        groups_text += f"• {group.group_name} (ID: {group.group_id})\n"
    
    await message.answer(
        f"{groups_text}\n"
        f"Please enter the group name to add user {target_user_id} to:"
    )
    
    await state.set_state(AdminStates.adding_user_group)


@admin_router.message(StateFilter(AdminStates.adding_user_group))
async def add_user_finish(message: types.Message, state: FSMContext):
    """Finish user addition"""
    if message.chat.type != ChatType.PRIVATE:
        return
    
    user_id = message.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        return
    
    data = await state.get_data()
    target_user_id = data.get('target_user_id')
    group_name = message.text.strip()
    
    # Get group
    group = await db.get_group_by_name(group_name)
    if not group:
        await message.answer(f"❌ Group '{group_name}' not found.")
        await state.clear()
        return
    
    # Add user (this will create user record if it doesn't exist)
    await db.add_user(target_user_id, f"user_{target_user_id}", None)
    
    # Add user to group
    success = await db.add_user_to_group(target_user_id, group.group_id)
    
    if success:
        await message.answer(
            f"✅ **User Added Successfully!**\n\n"
            f"👤 User ID: {target_user_id}\n"
            f"👥 Group: {group_name}\n"
            f"📅 Next payment due: {format_date(group.next_payment_date)}",
            parse_mode="Markdown"
        )
        logger.info(f"Admin {user_id} added user {target_user_id} to group '{group_name}'")
    else:
        await message.answer("❌ Failed to add user to group. Please try again.")
    
    await state.clear()


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
    
    groups_text = "📅 **Update Group Due Date**\n\n"
    groups_text += "Available groups:\n\n"
    
    for group in groups:
        days_until = calculate_days_until(group.next_payment_date)
        status_emoji = get_payment_status_emoji(days_until)
        
        groups_text += (
            f"{status_emoji} **{group.group_name}** (ID: {group.group_id})\n"
            f"📅 Current due date: {format_date(group.next_payment_date)}\n"
            f"📊 Status: {get_payment_status_text(days_until)}\n\n"
        )
    
    groups_text += "Please enter the group name you want to update:"
    
    await callback.message.edit_text(groups_text, parse_mode="Markdown")
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
    
    group_name = message.text.strip()
    
    # Get group
    group = await db.get_group_by_name(group_name)
    if not group:
        await message.answer(f"❌ Group '{group_name}' not found. Please try again.")
        return
    
    await state.update_data(group=group)
    
    await message.answer(
        f"📅 **Update Due Date for {group.group_name}**\n\n"
        f"Current due date: {format_date(group.next_payment_date)}\n\n"
        f"Please enter the new due date in format: **YYYY-MM-DD**\n\n"
        f"Examples:\n"
        f"• `2025-11-15` (November 15, 2025)\n"
        f"• `2025-12-01` (December 1, 2025)\n\n"
        f"Or type `cancel` to cancel.",
        parse_mode="Markdown"
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
        new_due_date = datetime.strptime(date_str, "%Y-%m-%d")
        
        # Check if date is not in the past
        if new_due_date.date() < datetime.now().date():
            await message.answer("❌ Due date cannot be in the past. Please enter a future date.")
            return
            
    except ValueError:
        await message.answer(
            "❌ Invalid date format. Please use **YYYY-MM-DD** format.\n\n"
            "Example: `2025-11-15`",
            parse_mode="Markdown"
        )
        return
    
    # Update the due date
    success = await db.update_group_due_date(group.group_id, new_due_date)
    
    if success:
        days_until = calculate_days_until(new_due_date)
        status_emoji = get_payment_status_emoji(days_until)
        
        await message.answer(
            f"✅ **Due Date Updated Successfully!**\n\n"
            f"👥 Group: {group.group_name}\n"
            f"📅 Old due date: {format_date(group.next_payment_date)}\n"
            f"📅 New due date: {format_date(new_due_date.date())}\n"
            f"{status_emoji} Status: {get_payment_status_text(days_until)}\n\n"
            f"💡 All users in this group will now be reminded based on the new date.",
            parse_mode="Markdown"
        )
        
        logger.info(f"Admin {user_id} updated due date for group '{group.group_name}' from {group.next_payment_date} to {new_due_date.date()}")
    else:
        await message.answer(
            "❌ Failed to update due date. Please try again or check the logs for errors."
        )
    
    await state.clear()


@admin_router.callback_query(F.data == "admin_stats")
async def view_statistics(callback: types.CallbackQuery):
    """View payment statistics"""
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Access denied", show_alert=True)
        return
    
    # Get basic statistics
    groups = await db.get_all_groups()
    overdue_users = await db.get_overdue_users()
    
    total_groups = len(groups)
    total_overdue = len(overdue_users)
    
    # Calculate some basic stats
    upcoming_payments = 0
    for group in groups:
        days_until = calculate_days_until(group.next_payment_date)
        if 0 <= days_until <= 7:  # Due within a week
            upcoming_payments += 1
    
    response = (
        f"📈 **Payment Statistics**\n\n"
        f"👥 Total groups: {total_groups}\n"
        f"❌ Overdue payments: {total_overdue}\n"
        f"⚠️ Due within 7 days: {upcoming_payments}\n"
        f"✅ Up to date: {total_groups - total_overdue - upcoming_payments}\n\n"
        f"📊 System Status: {'✅ Healthy' if total_overdue == 0 else '⚠️ Needs Attention'}"
    )
    
    await callback.message.edit_text(response, parse_mode="Markdown")
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
            "❌ **Test Notifications Failed**\n\n"
            "Database is not available.",
            parse_mode="Markdown"
        )
        return
    
    try:
        # Create a temporary scheduler for testing
        test_scheduler = NotificationScheduler(callback.bot, db, settings)
        
        await callback.message.edit_text(
            "🧪 **Running Test Notifications**\n\n"
            "Checking for users needing reminders and overdue warnings...\n"
            "This may take a few seconds.",
            parse_mode="Markdown"
        )
        
        # Run the notification checks
        await test_scheduler.send_test_notifications()
        
        await callback.message.edit_text(
            "✅ **Test Notifications Complete**\n\n"
            "Check the bot logs for details about sent notifications.\n\n"
            "💡 **Note:** Notifications are sent automatically daily at 9:00 AM.",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"❌ Test notifications failed: {e}")
        await callback.message.edit_text(
            f"❌ **Test Notifications Failed**\n\n"
            f"Error: {str(e)}\n\n"
            f"Check the bot logs for more details.",
            parse_mode="Markdown"
        )


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
        "📊 **Импорт групп из Excel файла**\n\n"
        "Отправьте Excel файл (.xlsx) с данными для импорта групп.\n\n"
        "**Формат файла:**\n"
        "• Столбец A: Названия групп (например: spotify 001)\n"
        "• Столбец B: ID групп (например: 001)\n\n"
        "**Пример:**\n"
        "```\n"
        "spotify 001 | 001\n"
        "spotify 002 | 002\n"
        "```\n\n"
        "📎 Прикрепите файл к следующему сообщению:",
        parse_mode="Markdown"
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
                    errors.append(f"Строка {row_num}: ID должен быть 3-значным числом")
                    continue
                
                groups_data.append({
                    'name': group_name,
                    'display_id': group_id,  # Keep as string for VARCHAR(3)
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
                errors.append(f"ID уже существуют в базе: {', '.join(map(str, existing_display_ids))}")
            
            # Store data for confirmation
            await state.update_data(groups_data=groups_data, errors=errors)
            
            # Show preview
            preview_text = "📋 **Предварительный просмотр импорта:**\n\n"
            preview_text += f"✅ Найдено групп для импорта: {len(groups_data)}\n\n"
            
            if errors:
                preview_text += f"⚠️ **Ошибки ({len(errors)}):**\n"
                for error in errors[:5]:  # Show first 5 errors
                    preview_text += f"• {error}\n"
                if len(errors) > 5:
                    preview_text += f"• ... и ещё {len(errors) - 5} ошибок\n"
                preview_text += "\n"
            
            if groups_data and not errors:
                preview_text += "**Группы для создания:**\n"
                for i, group in enumerate(groups_data[:10]):  # Show first 10
                    preview_text += f"• {group['name']} (ID: {group['display_id']})\n"
                if len(groups_data) > 10:
                    preview_text += f"• ... и ещё {len(groups_data) - 10} групп\n"
                
                await state.set_state(AdminStates.importing_groups_confirm)
                
                # Create custom keyboard for import confirmation
                builder = InlineKeyboardBuilder()
                builder.row(
                    types.InlineKeyboardButton(text="✅ Да", callback_data="confirm_yes"),
                    types.InlineKeyboardButton(text="❌ Нет", callback_data="confirm_no")
                )
                
                await message.answer(
                    preview_text,
                    parse_mode="Markdown",
                    reply_markup=builder.as_markup()
                )
            else:
                await message.answer(
                    preview_text + "\n❌ Импорт невозможен из-за ошибок в данных.",
                    parse_mode="Markdown"
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
                    logger.warning(f"Failed to cleanup temp file {file_path}: {cleanup_error}")
    
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
            f"✅ **Импорт завершён!**\n\n"
            f"Успешно создано групп: {success_count} из {len(groups_data)}\n\n"
            f"Используйте /admin для управления группами.",
            parse_mode="Markdown"
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


# Handle any unrecognized admin callback
@admin_router.callback_query(F.data.startswith("admin_"))
async def handle_unknown_admin_action(callback: types.CallbackQuery):
    """Handle unknown admin actions"""
    await callback.answer("This feature is not implemented yet.", show_alert=True)
