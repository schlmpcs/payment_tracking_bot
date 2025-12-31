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
        InlineKeyboardButton(text="📈 Статистика", callback_data="admin_stats")
    )
    builder.row(
        InlineKeyboardButton(text="➕ Создать группу", callback_data="admin_create_group"),
        InlineKeyboardButton(text="🗑️ Удалить группу", callback_data="admin_delete_group")
    )
    builder.row(
        InlineKeyboardButton(text="👥 Управление участниками", callback_data="admin_manage_members")
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


def get_pagination_keyboard(
    current_page: int, 
    total_pages: int, 
    callback_prefix: str,
    show_back: bool = False
) -> InlineKeyboardMarkup:
    """
    Create pagination keyboard with Previous/Next buttons
    
    Args:
        current_page: Current page number (0-indexed)
        total_pages: Total number of pages
        callback_prefix: Prefix for callback data (e.g., 'view_groups', 'admin_stats')
        show_back: Whether to show a "Back to menu" button
    
    Returns:
        InlineKeyboardMarkup with navigation buttons
    """
    builder = InlineKeyboardBuilder()
    
    # Navigation buttons
    buttons = []
    
    if current_page > 0:
        buttons.append(InlineKeyboardButton(
            text="⬅️ Назад", 
            callback_data=f"{callback_prefix}_page_{current_page - 1}"
        ))
    
    # Page indicator
    buttons.append(InlineKeyboardButton(
        text=f"📄 {current_page + 1}/{total_pages}",
        callback_data="noop"  # No operation
    ))
    
    if current_page < total_pages - 1:
        buttons.append(InlineKeyboardButton(
            text="Вперёд ➡️", 
            callback_data=f"{callback_prefix}_page_{current_page + 1}"
        ))
    
    builder.row(*buttons)
    
    # Back to menu button
    if show_back:
        builder.row(
            InlineKeyboardButton(
                text="🔙 Главное меню", 
                callback_data="back_to_admin_menu"
            )
        )
    
    return builder.as_markup()
