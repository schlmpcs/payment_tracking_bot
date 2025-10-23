"""
Inline keyboards for the bot
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_months_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for selecting payment months"""
    builder = InlineKeyboardBuilder()
    
    for i in range(1, 7):
        text = f"{i} month{'s' if i != 1 else ''}"
        builder.button(text=text, callback_data=f"months_{i}")
    
    builder.adjust(2)  # 2 buttons per row
    builder.row(
        InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_payment")
    )
    
    return builder.as_markup()


def get_admin_main_keyboard() -> InlineKeyboardMarkup:
    """Create main admin keyboard"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="👥 View Groups", callback_data="admin_view_groups"),
        InlineKeyboardButton(text="📊 Overdue Users", callback_data="admin_overdue_users")
    )
    builder.row(
        InlineKeyboardButton(text="➕ Create Group", callback_data="admin_create_group"),
        InlineKeyboardButton(text="👤 Add User", callback_data="admin_add_user")
    )
    builder.row(
        InlineKeyboardButton(text="📈 Statistics", callback_data="admin_stats")
    )
    
    return builder.as_markup()


def get_confirmation_keyboard(action: str) -> InlineKeyboardMarkup:
    """Create confirmation keyboard"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="✅ Yes", callback_data=f"confirm_{action}"),
        InlineKeyboardButton(text="❌ No", callback_data=f"cancel_{action}")
    )
    
    return builder.as_markup()