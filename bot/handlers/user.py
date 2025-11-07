"""
User command handlers for the Spotify Payment Bot
"""

import logging
from datetime import datetime
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.enums import ChatType

from bot.database.operations import Database
from bot.config.settings import Settings
from bot.utils.states import PaymentStates, JoinStates
from bot.utils.keyboards import get_months_keyboard
from bot.utils.helpers import (
    format_date, calculate_days_until,
    get_payment_status_emoji, get_payment_status_text,
    validate_file_type
)

# Initialize router
user_router = Router()
logger = logging.getLogger(__name__)

# Global database instance (will be injected)
db: Database = None
settings: Settings = None


def init_user_handlers(database: Database, bot_settings: Settings):
    """Initialize handlers with database and settings"""
    global db, settings
    db = database
    settings = bot_settings


@user_router.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext):
    """Handle /start command"""
    if message.chat.type != ChatType.PRIVATE:
        return
    
    # Clear any active state (allows canceling any operation)
    current_state = await state.get_state()
    if current_state:
        await state.clear()
    
    user = message.from_user
    username = user.username or user.first_name or "User"
    
    # Debug: Log user ID for admin setup
    logger.info(f"🆔 User {username} (ID: {user.id}) started the bot")
    
    # Add user to database
    if db and db.pool:
        await db.add_user(user.id, username, user.first_name)
        
        # Check if user is registered in a group
        is_registered = await db.is_user_registered(user.id)
        
        if is_registered:
            status = await db.get_user_payment_status(user.id)
            if status:
                days_until = calculate_days_until(status.next_payment_date)
                emoji = get_payment_status_emoji(days_until)
                
                welcome_text = (
                    f"👋 С возвращением, {username}!\n\n"
                    f"👥 Группа: **{status.group_name}**\n"
                    f"{emoji} Следующий платёж: {format_date(status.next_payment_date)}\n"
                    f"📊 Статус: {get_payment_status_text(days_until)}\n\n"
                    f"💡 Используйте /pay для загрузки чека об оплате\n"
                    f"📋 Используйте /status для подробной информации о платежах\n"
                    f"❓ Используйте /help для просмотра всех команд"
                )
            else:
                welcome_text = (
                    f"👋 Добро пожаловать, {username}!\n\n"
                    f"⚠️ Возникла проблема с вашим аккаунтом.\n"
                    f"Пожалуйста, обратитесь к администратору за помощью."
                )
        else:
            welcome_text = (
                f"👋 Добро пожаловать, {username}!\n\n"
                f"🔒 Вы ещё не зарегистрированы ни в одной группе для оплаты.\n\n"
                f"🚪 **Присоединиться к группе:** Используйте /join для просмотра доступных групп\n"
                f"❓ **Нужна помощь:** Используйте /help для просмотра всех команд\n\n"
                f"После регистрации вы сможете:\n"
                f"• 💳 Загружать чеки об оплате\n"
                f"• 📊 Проверять статус платежей\n"
                f"• 📅 Отслеживать историю платежей"
            )
    else:
        welcome_text = (
            f"👋 Добро пожаловать, {username}!\n\n"
            f"⚠️ База данных в настоящее время недоступна.\n"
            f"Пожалуйста, попробуйте позже."
        )
    
    await message.answer(welcome_text, parse_mode="Markdown")


@user_router.message(Command("help"))
async def help_command(message: types.Message):
    """Handle /help command"""
    if message.chat.type != ChatType.PRIVATE:
        return
    
    help_text = (
        "🤖 **Справка по боту Spotify Payment**\n\n"
        "**Доступные команды:**\n"
        "🏠 /start - Приветственное сообщение и обзор статуса\n"
        "🆔 /id - Показать ваш ID для администратора\n"
        "🚪 /join - Присоединиться к группе оплаты\n"
        "� /leave - Покинуть текущую группу\n"
        "�💳 /pay - Загрузить чек об оплате\n"
        "📊 /status - Проверить статус ваших платежей\n"
        "📈 /history - Показать историю платежей\n"
        "❓ /help - Показать эту справку\n\n"
        "**Как оплатить:**\n"
        "1. Используйте команду /pay\n"
        "2. Выберите количество месяцев для оплаты (1-6)\n"
        "3. Загрузите чек банковского перевода\n"
        "4. Платёж будет обработан автоматически\n\n"
        "**Поддерживаемые форматы чеков:**\n"
        "• 📷 Фотографии (JPG, PNG)\n"
        "• 📄 PDF документы\n\n"
        "**Нужна помощь?** Обратитесь к администратору, если у вас есть проблемы."
    )
    
    await message.answer(help_text, parse_mode="Markdown")


@user_router.message(Command("id"))
async def id_command(message: types.Message):
    """Handle /id command - show user ID for admin setup"""
    if message.chat.type != ChatType.PRIVATE:
        return
    
    user = message.from_user
    username = user.username or user.first_name or "User"
    
    # Get user's display ID from database
    user_obj = None
    if db and db.pool:
        user_obj = await db.get_user(user.id)
    
    id_text = (
        f"🆔 **Информация о вашем Telegram**\n\n"
        f"👤 Имя: {user.first_name or 'Н/Д'}\n"
        f"🏷️ Имя пользователя: @{user.username or 'Нет'}\n"
        f"🔢 ID пользователя: `{user.id}`\n"
    )
    
    if user_obj and hasattr(user_obj, 'display_id'):
        id_text += f"🎯 Ваш ID в боте: **{user_obj.display_id}**\n"
    
    id_text += f"\n💡 **Для администраторов:** Чтобы сделать {username} администратором, добавьте этот ID в список TG_ADMIN_IDS в файле .env."
    
    await message.answer(id_text, parse_mode="Markdown")


@user_router.message(Command("leave"))
async def leave_group_command(message: types.Message):
    """Handle /leave command - leave current group"""
    if message.chat.type != ChatType.PRIVATE:
        return
    
    if not db or not db.pool:
        await message.answer("❌ База данных в настоящее время недоступна.")
        return
    
    user_id = message.from_user.id
    
    # Check if user is in any group
    group = await db.get_user_group(user_id)
    if not group:
        await message.answer(
            "ℹ️ **Вы не состоите ни в одной группе**\n\n"
            "Используйте /join для поиска доступных групп."
        )
        return
    
    # Show confirmation
    confirmation_text = (
        f"🚪 **Покинуть группу**\n\n"
        f"Вы действительно хотите покинуть группу?\n\n"
        f"🏷️ **Группа**: {group.group_name}\n"
        f"📅 **Следующий платёж**: {format_date(group.next_payment_date)}\n\n"
        f"⚠️ **Внимание**: После выхода из группы вам потребуется заново присоединиться через /join"
    )
    
    # Create confirmation keyboard
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🚪 Да, покинуть", callback_data=f"leave_group_{group.group_id}"),
        types.InlineKeyboardButton(text="❌ Остаться", callback_data="cancel_leave_group")
    )
    
    await message.answer(
        confirmation_text,
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )


@user_router.callback_query(F.data.startswith("leave_group_"))
async def confirm_leave_group(callback: types.CallbackQuery):
    """Confirm leaving group"""
    try:
        group_id = int(callback.data.split("_")[-1])
        user_id = callback.from_user.id
        
        # Get group info before removing
        group = await db.get_user_group(user_id)
        if not group or group.group_id != group_id:
            await callback.message.edit_text("❌ Группа не найдена или вы не состоите в ней.")
            return
        
        # Remove user from group
        success = await db.remove_user_from_group(user_id, group_id)
        
        if success:
            await callback.message.edit_text(
                f"✅ **Вы покинули группу!**\n\n"
                f"🏷️ Группа: {group.group_name}\n"
                f"📅 Время выхода: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"Используйте /join для поиска новых групп.",
                parse_mode="Markdown"
            )
        else:
            await callback.message.edit_text("❌ Ошибка при выходе из группы. Попробуйте позже.")
        
    except Exception as e:
        logger.error(f"Error in confirm_leave_group: {e}")
        await callback.message.edit_text("❌ Произошла ошибка при выходе из группы.")


@user_router.callback_query(F.data == "cancel_leave_group")
async def cancel_leave_group(callback: types.CallbackQuery):
    """Cancel leaving group"""
    await callback.message.edit_text("✅ Вы остались в группе.")


@user_router.message(Command("history"))
async def payment_history_command(message: types.Message):
    """Handle /history command - show payment history"""
    if message.chat.type != ChatType.PRIVATE:
        return
    
    if not db or not db.pool:
        await message.answer("❌ База данных в настоящее время недоступна.")
        return
    
    user_id = message.from_user.id
    
    # Get user's group
    group = await db.get_user_group(user_id)
    if not group:
        await message.answer(
            "ℹ️ **История платежей недоступна**\n\n"
            "Вы не состоите ни в одной группе.\n"
            "Используйте /join для поиска доступных групп."
        )
        return
    
    # Get payment history
    try:
        payments = await db.get_user_payment_history(user_id)
        
        if not payments:
            await message.answer(
                f"📭 **История платежей пуста**\n\n"
                f"🏷️ Группа: {group.group_name}\n"
                f"💡 Используйте /pay для загрузки первого чека об оплате."
            )
            return
        
        history_text = (
            f"📊 **История ваших платежей**\n"
            f"🏷️ Группа: {group.group_name}\n\n"
        )
        
        total_months = 0
        total_amount = 0
        
        for payment in payments[-10:]:  # Show last 10 payments
            payment_date = payment.created_at.strftime('%Y-%m-%d')
            amount = payment.months_paid * settings.bot_default_payment_price
            total_months += payment.months_paid
            total_amount += amount
            
            history_text += (
                f"💳 **{payment_date}**\n"
                f"   📅 Месяцев: {payment.months_paid}\n"
                f"   💰 Сумма: {amount:.2f}€\n\n"
            )
        
        if len(payments) > 10:
            history_text += f"... и ещё {len(payments) - 10} платежей\n\n"
        
        history_text += (
            f"📈 **Итого:**\n"
            f"💳 Всего платежей: {len(payments)}\n"
            f"📅 Всего месяцев: {total_months}\n"
            f"💰 Общая сумма: {total_amount:.2f}€"
        )
        
        await message.answer(history_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error getting payment history for user {user_id}: {e}")
        await message.answer("❌ Ошибка при получении истории платежей.")


@user_router.message(Command("join"))
async def join_command(message: types.Message, state: FSMContext):
    """Handle /join command - show available groups and allow user to join"""
    if message.chat.type != ChatType.PRIVATE:
        return
    
    user = message.from_user
    username = user.username or user.first_name or "User"
    
    if not db or not db.pool:
        await message.answer(
            "❌ База данных в настоящее время недоступна.\n"
            "Пожалуйста, попробуйте позже."
        )
        return
    
    # Check if user is already in a group
    is_registered = await db.is_user_registered(user.id)
    if is_registered:
        current_group = await db.get_user_group(user.id)
        if current_group:
            await message.answer(
                f"ℹ️ Вы уже являетесь участником группы **{current_group.group_name}**.\n\n"
                f"Если хотите сменить группу, пожалуйста, обратитесь к администратору.",
                parse_mode="Markdown"
            )
            return
    
    # Get all available groups with member counts
    groups = await db.get_groups_with_member_count()
    
    if not groups:
        await message.answer(
            "❌ На данный момент нет доступных групп оплаты.\n"
            "Пожалуйста, обратитесь к администратору для создания группы."
        )
        return
    
    # Build groups list message
    groups_text = "🚪 **Доступные группы оплаты**\n\n"
    groups_text += "Выберите группу для присоединения, отправив её номер:\n\n"
    
    for i, group in enumerate(groups, 1):
        member_text = f"{group['member_count']} участник{'ов' if group['member_count'] != 1 else ''}"
        groups_text += f"**{i}.** {group['group_name']} ({member_text})\n"
    
    groups_text += f"\n💡 **Пример:** Отправьте `{1}` чтобы присоединиться к первой группе"
    groups_text += f"\n❌ Отправьте `отмена` или используйте /start для отмены"
    
    await message.answer(groups_text, parse_mode="Markdown")
    
    # Store groups in state data and set state
    await state.set_data({"available_groups": groups})
    await state.set_state(JoinStates.selecting_group)


@user_router.message(StateFilter(JoinStates.selecting_group))
async def handle_group_selection(message: types.Message, state: FSMContext):
    """Handle group selection during join process"""
    if message.chat.type != ChatType.PRIVATE:
        return
    
    user = message.from_user
    username = user.username or user.first_name or "User"
    text = message.text.strip()
    
    # Handle cancel
    if text.lower() in ['cancel', 'отмена']:
        await state.clear()
        await message.answer("❌ Присоединение к группе отменено.")
        return
    
    # Get stored groups data
    data = await state.get_data()
    available_groups = data.get('available_groups', [])
    
    if not available_groups:
        await state.clear()
        await message.answer("❌ Ошибка: Данные групп не найдены. Пожалуйста, попробуйте /join снова.")
        return
    
    # Parse selection
    try:
        selection = int(text)
        if selection < 1 or selection > len(available_groups):
            await message.answer(
                f"❌ Неверный выбор. Пожалуйста, выберите номер от 1 до {len(available_groups)}, или отправьте 'отмена'."
            )
            return
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, отправьте номер для выбора группы, или 'отмена' для отмены."
        )
        return
    
    # Get selected group
    selected_group = available_groups[selection - 1]
    group_id = selected_group['group_id']
    group_name = selected_group['group_name']
    
    # Add user to group
    success = await db.add_user_to_group(user.id, group_id)
    
    if success:
        await state.clear()
        logger.info(f"User {username} (ID: {user.id}) joined group '{group_name}' (ID: {group_id})")
        
        await message.answer(
            f"🎉 **Добро пожаловать в {group_name}!**\n\n"
            f"Вы успешно присоединились к группе оплаты.\n\n"
            f"✅ Теперь вы можете:\n"
            f"• 💳 Загружать чеки об оплате командой /pay\n"
            f"• 📊 Проверять свой статус командой /status\n"
            f"• 📅 Просматривать историю платежей\n\n"
            f"💡 Используйте /help для просмотра всех доступных команд.",
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            f"❌ Не удалось присоединиться к **{group_name}**.\n"
            f"Это может произойти из-за:\n"
            f"• Вы уже в этой группе\n"
            f"• Произошла ошибка базы данных\n\n"
            f"Пожалуйста, попробуйте снова или обратитесь к администратору.",
            parse_mode="Markdown"
        )


@user_router.message(Command("status"))
async def status_command(message: types.Message):
    """Handle /status command"""
    if message.chat.type != ChatType.PRIVATE:
        return
    
    if not db or not db.pool:
        await message.answer(
            "❌ База данных в настоящее время недоступна.\n"
            "Пожалуйста, попробуйте позже."
        )
        return
    
    user_id = message.from_user.id
    
    # Check if user is registered
    if not await db.is_user_registered(user_id):
        await message.answer(
            "❌ Вы ещё не зарегистрированы ни в одной группе оплаты.\n"
            "Пожалуйста, обратитесь к администратору для добавления в группу."
        )
        return
    
    # Get payment status
    status = await db.get_user_payment_status(user_id)
    if not status:
        await message.answer(
            "❌ Не удается получить информацию о ваших платежах.\n"
            "Пожалуйста, обратитесь к администратору."
        )
        return
    
    days_until = calculate_days_until(status.next_payment_date)
    emoji = get_payment_status_emoji(days_until)
    status_text = get_payment_status_text(days_until)
    
    response = (
        f"{emoji} **Статус платежей**\n\n"
        f"👥 Группа: {status.group_name}\n"
        f"📅 Следующий платёж до: {format_date(status.next_payment_date)}\n"
        f"📊 Статус: {status_text}\n"
    )
    
    if status.last_payment_date:
        response += f"💰 Последний платёж: {format_date(status.last_payment_date)}\n"
    
    if days_until <= 3:
        response += f"\n💡 Используйте /pay для совершения платежа"
    
    await message.answer(response, parse_mode="Markdown")


@user_router.message(Command("pay"))
async def pay_command(message: types.Message, state: FSMContext):
    """Handle /pay command"""
    if message.chat.type != ChatType.PRIVATE:
        return
    
    if not db or not db.pool:
        await message.answer(
            "❌ База данных в настоящее время недоступна.\n"
            "Пожалуйста, попробуйте позже."
        )
        return
    
    user_id = message.from_user.id
    
    # Check if user is registered
    if not await db.is_user_registered(user_id):
        await message.answer(
            "❌ Вы ещё не зарегистрированы ни в одной группе оплаты.\n"
            "Пожалуйста, обратитесь к администратору для добавления в группу."
        )
        return
    
    # Get user's current status
    status = await db.get_user_payment_status(user_id)
    if not status:
        await message.answer(
            "❌ Не удается получить информацию о ваших платежах.\n"
            "Пожалуйста, обратитесь к администратору."
        )
        return
    
    days_until = calculate_days_until(status.next_payment_date)
    emoji = get_payment_status_emoji(days_until)
    
    # Show current status and payment options
    status_message = (
        f"💳 **Оплата для группы: {status.group_name}**\n\n"
        f"{emoji} Следующий платёж до: {format_date(status.next_payment_date)}\n"
        f"📊 Статус: {get_payment_status_text(days_until)}\n\n"
        f"Пожалуйста, выберите на сколько месяцев хотите заплатить:"
    )
    
    await message.answer(
        status_message,
        reply_markup=get_months_keyboard(),
        parse_mode="Markdown"
    )
    
    await state.set_state(PaymentStates.selecting_months)


@user_router.callback_query(F.data.startswith("months_"), StateFilter(PaymentStates.selecting_months))
async def handle_months_selection(callback: types.CallbackQuery, state: FSMContext):
    """Handle months selection"""
    months = int(callback.data.split("_")[1])
    
    await state.update_data(months=months)
    
    await callback.message.edit_text(
        f"✅ Вы выбрали **{months} месяц{'ев' if months > 1 else ''}**\n\n"
        f"📎 Пожалуйста, загрузите чек об оплате\n\n"
        f"💡 Поддерживаемые форматы: JPG, PNG, PDF\n"
        f"После загрузки ваш платёж будет обработан автоматически.\n\n"
        f"💡 *Используйте /start для отмены операции*",
        parse_mode="Markdown"
    )
    
    await callback.answer()
    await state.set_state(PaymentStates.uploading_receipt)


@user_router.callback_query(F.data == "cancel_payment")
async def cancel_payment(callback: types.CallbackQuery, state: FSMContext):
    """Cancel payment process"""
    await callback.message.edit_text("❌ Процесс оплаты отменён.")
    await callback.answer()
    await state.clear()


@user_router.message(StateFilter(PaymentStates.uploading_receipt), F.photo)
async def handle_photo_receipt(message: types.Message, state: FSMContext):
    """Handle photo receipt upload"""
    await process_receipt_upload(message, state, message.photo[-1].file_id)


@user_router.message(StateFilter(PaymentStates.uploading_receipt), F.document)
async def handle_document_receipt(message: types.Message, state: FSMContext):
    """Handle document receipt upload"""
    document = message.document
    
    if not validate_file_type(document.mime_type):
        await message.answer(
            "❌ Неподдерживаемый тип файла. Пожалуйста, загрузите:\n"
            "• Фотографию (JPG, PNG)\n"
            "• PDF документ"
        )
        return
    
    await process_receipt_upload(message, state, document.file_id)


async def forward_receipt_to_storage(message: types.Message, user_info: dict, payment_info: dict) -> bool:
    """
    Forward receipt to storage chat for audit trail
    
    Args:
        message: Original message with receipt
        user_info: Dict with user details (id, username, first_name, etc.)
        payment_info: Dict with payment details (months, group_name, amount, etc.)
    
    Returns:
        bool: True if forwarded successfully, False otherwise
    """
    if not settings.tg_receipt_storage_chat_id:
        return True  # No storage chat configured, skip silently
    
    try:
        # Create audit message with context
        audit_text = (
            f"💳 **ПЛАТЁЖНЫЙ ЧЕК** - Получен новый платёж\n\n"
            f"👤 **Пользователь:**\n"
            f"• ID: `{user_info['id']}`\n"
            f"• Имя: {user_info.get('first_name', 'N/A')}\n"
            f"• Username: @{user_info.get('username', 'нет')}\n\n"
            f"💰 **Детали платежа:**\n"
            f"• Группа: {payment_info['group_name']}\n"
            f"• Месяцев оплачено: {payment_info['months']}\n"
            f"• Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"📸 **Чек во вложении ниже:**"
        )
        
        # Send audit message
        await message.bot.send_message(
            chat_id=settings.tg_receipt_storage_chat_id,
            text=audit_text,
            parse_mode="Markdown"
        )
        
        # Forward the original receipt
        await message.forward(settings.tg_receipt_storage_chat_id)
        
        logger.info(f"Receipt forwarded to storage chat for user {user_info['id']}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to forward receipt to storage chat: {e}")
        return False


async def process_receipt_upload(message: types.Message, state: FSMContext, file_id: str):
    """Process receipt upload and record payment"""
    try:
        data = await state.get_data()
        months = data.get('months')
        
        if not months:
            await message.answer("❌ Ошибка: Период оплаты не найден. Пожалуйста, начните заново с /pay")
            await state.clear()
            return
        
        user_id = message.from_user.id
        
        # Get user's group
        group = await db.get_user_group(user_id)
        if not group:
            await message.answer("❌ Ошибка: Не удается найти вашу группу. Пожалуйста, обратитесь к администратору.")
            await state.clear()
            return
        
        # Record payment
        success = await db.add_payment(user_id, group.group_id, months, file_id)
        
        if success:
            await message.answer(
                f"✅ **Платёж подтверждён!**\n\n"
                f"💰 Оплачено за: {months} месяц{'ев' if months > 1 else ''}\n"
                f"📅 Платёж обработан: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"👥 Группа: {group.group_name}\n\n"
                f"Спасибо за ваш платёж! 🎉\n"
                f"Ваша подписка была продлена.",
                parse_mode="Markdown"
            )
            
            logger.info(f"Payment processed: User {user_id} paid for {months} months in group {group.group_name}")
            
            # Forward receipt to storage chat for audit trail
            user_info = {
                'id': user_id,
                'username': message.from_user.username,
                'first_name': message.from_user.first_name,
                'last_name': message.from_user.last_name
            }
            
            payment_info = {
                'months': months,
                'group_name': group.group_name,
                'group_id': group.group_id
            }
            
            await forward_receipt_to_storage(message, user_info, payment_info)
        else:
            await message.answer(
                "❌ **Ошибка обработки платежа**\n\n"
                "Произошла ошибка при обработке вашего платежа.\n"
                "Пожалуйста, обратитесь к администратору или попробуйте позже.",
                parse_mode="Markdown"
            )
            logger.error(f"Payment processing failed for user {user_id}")
        
        await state.clear()
        
    except Exception as e:
        await message.answer(
            "❌ **Произошла ошибка**\n\n"
            "Пожалуйста, обратитесь к администратору или попробуйте позже.",
            parse_mode="Markdown"
        )
        logger.error(f"Error in payment processing: {e}")
        await state.clear()


@user_router.message(StateFilter(PaymentStates.uploading_receipt))
async def handle_invalid_receipt(message: types.Message):
    """Handle invalid receipt uploads"""
    await message.answer(
        "❌ **Неверный формат чека**\n\n"
        "Пожалуйста, загрузите действительный чек:\n"
        "• 📷 Фотографию (JPG, PNG)\n"
        "• 📄 PDF документ\n\n"
        "Или используйте /pay для начала заново.",
        parse_mode="Markdown"
    )