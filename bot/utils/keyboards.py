"""
Inline keyboards for the bot
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_months_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for selecting payment months"""
    builder = InlineKeyboardBuilder()
    
    for i in range(1, 7):
        text = f"{i} месяц{'ев' if i > 1 else ''}"
        builder.button(text=text, callback_data=f"months_{i}")
    
    builder.adjust(2)  # 2 buttons per row
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_payment")
    )
    
    return builder.as_markup()


def get_admin_main_keyboard() -> InlineKeyboardMarkup:
    """Create main admin keyboard"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="👥 Просмотр групп", callback_data="admin_view_groups"),
        InlineKeyboardButton(text="📊 Просроченные пользователи", callback_data="admin_overdue_users")
    )
    builder.row(
        InlineKeyboardButton(text="➕ Создать группу", callback_data="admin_create_group"),
        InlineKeyboardButton(text="�️ Удалить группу", callback_data="admin_delete_group")
    )
    builder.row(
        InlineKeyboardButton(text="�👤 Добавить пользователя", callback_data="admin_add_user"),
        InlineKeyboardButton(text="👥 Управление участниками", callback_data="admin_manage_members")
    )
    builder.row(
        InlineKeyboardButton(text="� Импорт групп", callback_data="admin_import_groups")
    )
    builder.row(
        InlineKeyboardButton(text="�📅 Обновить дату платежа", callback_data="admin_update_due_date")
    )
    builder.row(
        InlineKeyboardButton(text="📈 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton(text="🔔 Тест уведомлений", callback_data="admin_test_notifications")
    )

    return builder.as_markup()


def get_confirmation_keyboard(action: str) -> InlineKeyboardMarkup:
    """Create confirmation keyboard"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_{action}"),
        InlineKeyboardButton(text="❌ Нет", callback_data=f"cancel_{action}")
    )
    
    return builder.as_markup()


def get_user_main_menu() -> InlineKeyboardMarkup:
    """Create user main menu keyboard"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="💳 Оплатить", callback_data="user_pay"),
        InlineKeyboardButton(text="📊 Статус", callback_data="user_status")
    )
    builder.row(
        InlineKeyboardButton(text="❓ Помощь", callback_data="user_help")
    )
    
    return builder.as_markup()
