"""
Inline keyboards for the bot
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def get_months_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for selecting payment months"""
    builder = InlineKeyboardBuilder()

    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]
    for i in range(1, 7):
        text = f"{number_emojis[i-1]} {i} мес."
        builder.button(text=text, callback_data=f"months_{i}")

    builder.adjust(2)  # 2 buttons per row
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_payment", style="destructive")
    )

    return builder.as_markup()


def get_admin_main_keyboard() -> InlineKeyboardMarkup:
    """Create main admin keyboard"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="👁 Просмотр групп", callback_data="admin_view_groups")
    )
    builder.row(
        InlineKeyboardButton(text="📊 Статистика 🇰🇿", callback_data="admin_stats_kz"),
        InlineKeyboardButton(text="📊 Статистика 🇷🇺", callback_data="admin_stats_ru")
    )
    builder.row(
        InlineKeyboardButton(text="✅ Создать группу", callback_data="admin_create_group"),
        InlineKeyboardButton(text="🗑️ Удалить группу", callback_data="admin_delete_group", style="destructive")
    )
    builder.row(
        InlineKeyboardButton(text="⚙️ Управление участниками", callback_data="admin_manage_members")
    )
    builder.row(
        InlineKeyboardButton(text="➕ Добавить пользователя", callback_data="admin_add_user")
    )

    return builder.as_markup()


def get_confirmation_keyboard(action: str) -> InlineKeyboardMarkup:
    """Create confirmation keyboard"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_{action}"),
        InlineKeyboardButton(text="❌ Нет", callback_data=f"cancel_{action}", style="destructive")
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


def get_status_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard shown after status display — pay is the primary CTA"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="💳 Оплатить", callback_data="user_pay")
    )
    builder.row(
        InlineKeyboardButton(text="📊 Статус", callback_data="user_status"),
        InlineKeyboardButton(text="❓ Помощь", callback_data="user_help")
    )

    return builder.as_markup()


def get_unregistered_user_menu() -> InlineKeyboardMarkup:
    """Create menu keyboard for unregistered users with Buy and Join buttons"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="🛒 Купить подписку", callback_data="buy_subscription")
    )
    builder.row(
        InlineKeyboardButton(text="🚪 Присоединиться к группе", callback_data="user_join")
    )
    builder.row(
        InlineKeyboardButton(text="❓ Помощь", callback_data="user_help")
    )

    return builder.as_markup()


def get_region_keyboard() -> InlineKeyboardMarkup:
    """Region selection keyboard for the buy flow"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="🇰🇿 Казахстан (KZ)", callback_data="buy_region_kz"),
        InlineKeyboardButton(text="🇷🇺 Россия (RU)", callback_data="buy_region_ru")
    )
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="buy_cancel_early", style="destructive")
    )

    return builder.as_markup()


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    """Keyboard with a single Cancel button"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="buy_cancel_early", style="destructive")
    )
    return builder.as_markup()


def get_plans_keyboard(region: str, base_price: int = 0) -> InlineKeyboardMarkup:
    """Subscription plan selection keyboard for the buy flow"""
    builder = InlineKeyboardBuilder()

    currency = "₸" if region == "KZ" else "₽"
    if not base_price:
        base_price = 700 if region == "KZ" else 200

    if region == "KZ":
        months_list = [1, 2, 3, 4, 5, 6]
    else:
        months_list = [1, 3, 6, 9, 12]

    for months in months_list:
        total_price = base_price * months
        builder.row(InlineKeyboardButton(
            text=f"💚 Spotify {months} мес - {total_price} {currency}", 
            callback_data=f"buy_plan_spotify_{months}"
        ))

    builder.row(
        InlineKeyboardButton(text="⭐ Отзывы", url="https://t.me/sptfykz/210"),
        InlineKeyboardButton(text="❓ Помощь", callback_data="user_help")
    )

    return builder.as_markup()

def get_pay_button_keyboard(price: int, currency: str, region: str = "RU", payment_link: str = "") -> InlineKeyboardMarkup:
    """Pay button after plan is selected"""
    builder = InlineKeyboardBuilder()
    if region == "KZ":
        builder.row(InlineKeyboardButton(text=f"Оплатить | {price} {currency}", url=payment_link))
        # We also need a callback button to advance the FSM state
        builder.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data="buy_pay_confirm"))
    else:
        builder.row(InlineKeyboardButton(text=f"Оплатить | {price} {currency}", callback_data="buy_pay_confirm"))

    builder.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="buy_back_to_plans"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="buy_cancel_early", style="destructive")
    )
    return builder.as_markup()

def get_buy_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Confirm/cancel keyboard for the buy flow summary step"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="✅ Отправить заявку", callback_data="buy_confirm"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="buy_cancel", style="destructive")
    )

    return builder.as_markup()


def get_rejected_user_keyboard(request_id: int) -> InlineKeyboardMarkup:
    """Keyboard shown to user when admin rejects due to bad credentials."""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="🔄 Отправить новые данные",
            callback_data=f"buy_resend_{request_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📩 Связаться с менеджером",
            url="https://t.me/sptfy_premium",
        )
    )

    return builder.as_markup()


def get_buy_admin_keyboard(user_id: int, request_id: int) -> InlineKeyboardMarkup:
    """Simple Accept / Reject keyboard for the admin channel buy request."""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="✅ Принять", callback_data=f"buy_accept_{user_id}_{request_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"buy_reject_{user_id}_{request_id}", style="destructive")
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


def get_statistics_pagination_keyboard(
    current_page: int, 
    total_pages: int, 
    order_by: str,
    region: str = None
) -> InlineKeyboardMarkup:
    """
    Create enhanced pagination keyboard for statistics with jump-by-4 buttons
    
    Args:
        current_page: Current page number (0-indexed)
        total_pages: Total number of pages
        order_by: Ordering type ('id' or 'date')
        region: Region filter ('kz', 'ru', or None for all)
    
    Returns:
        InlineKeyboardMarkup with navigation and jump buttons
    """
    builder = InlineKeyboardBuilder()
    
    # Build callback data prefix based on region
    if region:
        callback_prefix = f"admin_stats_page_{region}_{order_by}"
    else:
        callback_prefix = f"admin_stats_page_{order_by}"
    
    # First row: Jump back by 4, Previous
    first_row = []
    if current_page >= 4:
        first_row.append(InlineKeyboardButton(
            text="⏪ -4", 
            callback_data=f"{callback_prefix}_{current_page - 4}"
        ))
    if current_page > 0:
        first_row.append(InlineKeyboardButton(
            text="⬅️ Назад", 
            callback_data=f"{callback_prefix}_{current_page - 1}"
        ))
    
    if first_row:
        builder.row(*first_row)
    
    # Second row: Page indicator
    builder.row(InlineKeyboardButton(
        text=f"📄 {current_page + 1}/{total_pages}",
        callback_data="noop"
    ))
    
    # Third row: Next, Jump forward by 4
    third_row = []
    if current_page < total_pages - 1:
        third_row.append(InlineKeyboardButton(
            text="Вперёд ➡️", 
            callback_data=f"{callback_prefix}_{current_page + 1}"
        ))
    if current_page + 4 < total_pages:
        third_row.append(InlineKeyboardButton(
            text="+4 ⏩", 
            callback_data=f"{callback_prefix}_{current_page + 4}"
        ))
    
    if third_row:
        builder.row(*third_row)
    
    # Back to menu button
    builder.row(
        InlineKeyboardButton(
            text="🔙 Главное меню",
            callback_data="back_to_admin_menu"
        )
    )

    return builder.as_markup()


# Reply keyboard button labels (used both for building and matching in handlers)
BTN_PAY = "💳 Оплатить подписку"
BTN_BUY = "🛒 Купить подписку"
BTN_JOIN = "🚪 Присоединиться к группе"
BTN_HELP = "❓ Помощь"


def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Persistent bottom keyboard for registered users."""
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text=BTN_PAY))
    builder.row(KeyboardButton(text=BTN_JOIN), KeyboardButton(text=BTN_HELP))
    return builder.as_markup(resize_keyboard=True)


def get_unregistered_reply_keyboard() -> ReplyKeyboardMarkup:
    """Persistent bottom keyboard for unregistered users."""
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text=BTN_BUY))
    builder.row(KeyboardButton(text=BTN_JOIN), KeyboardButton(text=BTN_HELP))
    return builder.as_markup(resize_keyboard=True)
