"""
Buy-subscription flow handlers.

Guides a non-member through:
  1. Region selection  (KZ / RU)
  2. Spotify login     (email or username)
  3. Temporary password
  4. Confirmation → forwards data to admin channel
  5. Admin accepts → enters group ID → user gets assigned & notified
  6. 24h payment deadline check (handled by NotificationScheduler)
"""

import asyncio
import logging
import random
from datetime import datetime
from aiogram import Router, types, F, Bot
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from bot.database.operations import Database
from bot.config.settings import Settings
from bot.utils.states import BuyStates
from bot.utils.keyboards import (
    get_region_keyboard,
    get_buy_confirmation_keyboard,
    get_buy_admin_keyboard,
    get_rejected_user_keyboard,
    get_unregistered_user_menu,
    get_user_main_menu,
    get_plans_keyboard,
    get_pay_button_keyboard,
    get_cancel_keyboard,
    BTN_BUY,
)
from bot.utils.helpers import get_now, format_datetime, format_date

buy_router = Router()
logger = logging.getLogger(__name__)

# Injected at startup via init_buy_handlers()
db: Database = None
settings: Settings = None

# Pending admin accept operations, keyed by admin user_id.
# Avoids FSM state collisions when multiple admins share an admin channel.
_pending_admin_ops: dict[int, dict] = {}

# Active 30-min order expiration timers, keyed by user_id.
_order_timers: dict[int, asyncio.Task] = {}

ORDER_TIMEOUT_SECONDS = 30 * 60  # 30 minutes


def _cancel_order_timer(user_id: int) -> None:
    """Cancel an active order timer for the given user, if any."""
    task = _order_timers.pop(user_id, None)
    if task and not task.done():
        task.cancel()


async def _order_timeout(bot: Bot, user_id: int, order_id: str, state: FSMContext):
    """Wait ORDER_TIMEOUT_SECONDS, then cancel the order if user is still in the buy flow."""
    try:
        await asyncio.sleep(ORDER_TIMEOUT_SECONDS)

        # Check if user is still in a buy state with the same order
        current_state = await state.get_state()
        buy_states = {
            BuyStates.selecting_plan.state,
            BuyStates.uploading_receipt.state,
        }
        if current_state not in buy_states:
            return

        data = await state.get_data()
        if data.get("order_id") != order_id:
            return

        await state.clear()
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"❌ Заказ <code>#{order_id}</code> был отменён.\n\n"
                     f"Время на оплату истекло (30 мин).",
                parse_mode="HTML",
                reply_markup=get_unregistered_user_menu(),
            )
        except Exception as e:
            logger.error(f"Failed to send order timeout to user {user_id}: {e}")

    except asyncio.CancelledError:
        pass
    finally:
        _order_timers.pop(user_id, None)


def _start_order_timer(bot: Bot, user_id: int, order_id: str, state: FSMContext) -> None:
    """Start (or restart) a 30-min expiration timer for an order."""
    _cancel_order_timer(user_id)
    _order_timers[user_id] = asyncio.create_task(
        _order_timeout(bot, user_id, order_id, state)
    )


def init_buy_handlers(database: Database, bot_settings: Settings):
    """Inject shared database and settings instances."""
    global db, settings
    db = database
    settings = bot_settings


# ── helpers ──────────────────────────────────────────────────────────────────

def _region_emoji(region: str) -> str:
    return "🇰🇿" if region == "KZ" else "🇷🇺"



# ═══════════════════════════════════════════════════════════════════════════════
#  USER FLOW
# ═══════════════════════════════════════════════════════════════════════════════


# ── Step 1: Entry point ──────────────────────────────────────────────────────

@buy_router.message(F.text == BTN_BUY)
async def handle_buy_button(message: types.Message, state: FSMContext):
    """Reply keyboard: Купить подписку"""
    if message.chat.type != ChatType.PRIVATE:
        return
    await state.clear()
    if not db or not db.pool:
        await message.answer("❌ База данных недоступна. Попробуйте позже.")
        return
    if await db.is_user_registered(message.from_user.id):
        await message.answer(
            "ℹ️ Вы уже зарегистрированы в группе.\n"
            "Используйте /status для проверки статуса."
        )
        return
    pending = await db.get_pending_purchase_request_by_user(message.from_user.id)
    if pending:
        await message.answer(
            "⏳ <b>У вас уже есть активная заявка</b>\n\n"
            "Администратор обработает её в ближайшее время.",
            parse_mode="HTML"
        )
        return
    if not settings.tg_admin_channel_id:
        await message.answer("⚠️ Покупка подписки временно недоступна.\nОбратитесь к администратору.")
        return
    await message.answer(
        "🎵 <b>Покупка подписки Spotify</b>\n\n"
        "Для оформления подписки нам понадобятся ваши логин и пароль.\n"
        "Нет аккаунта? Создадим для вас новый!\n\n"
        "Шаг 1 из 3 — Выберите регион вашего аккаунта Spotify:",
        parse_mode="HTML",
        reply_markup=get_region_keyboard()
    )
    await state.set_state(BuyStates.selecting_region)


@buy_router.callback_query(F.data == "buy_subscription")
async def start_buy_flow(callback: types.CallbackQuery, state: FSMContext):
    """User taps the 'Buy Subscription' button."""
    if not db or not db.pool:
        await callback.message.answer("❌ База данных недоступна. Попробуйте позже.")
        await callback.answer()
        return

    if await db.is_user_registered(callback.from_user.id):
        await callback.message.answer(
            "ℹ️ Вы уже зарегистрированы в группе.\n"
            "Используйте /status для проверки статуса."
        )
        await callback.answer()
        return

    pending = await db.get_pending_purchase_request_by_user(callback.from_user.id)
    if pending:
        await callback.message.edit_text(
            "⏳ <b>У вас уже есть активная заявка</b>\n\n"
            "Администратор обработает её в ближайшее время.",
            parse_mode="HTML"
        )
        await callback.answer()
        return

    if not settings.tg_admin_channel_id:
        await callback.message.answer(
            "⚠️ Покупка подписки временно недоступна.\nОбратитесь к администратору."
        )
        await callback.answer()
        return

    try:
        await callback.message.edit_text(
            "🎵 <b>Покупка подписки Spotify</b>\n\n"
            "Для оформления подписки нам понадобятся ваши логин и пароль.\n"
            "Нет аккаунта? Создадим для вас новый!\n\n"
            "Шаг 1 из 3 — Выберите регион вашего аккаунта Spotify:",
            parse_mode="HTML",
            reply_markup=get_region_keyboard()
        )
    except TelegramBadRequest as repr_err:
        if "message is not modified" not in str(repr_err):
            raise
    
    await state.set_state(BuyStates.selecting_region)
    await callback.answer()


# ── Step 2: Region selected → ask for login ──────────────────────────────────

@buy_router.callback_query(
    StateFilter(BuyStates.selecting_region),
    F.data.in_({"buy_region_kz", "buy_region_ru"})
)
async def handle_region_selection(callback: types.CallbackQuery, state: FSMContext):
    region = "KZ" if callback.data == "buy_region_kz" else "RU"
    await state.update_data(region=region)

    text = (
        "Срок выполнения заказа: от 10 минут до 24 часов\n\n"
        "<i>Выберите подписку:</i>"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_plans_keyboard(region, base_price=int(settings.bot_default_payment_price if region == "KZ" else settings.bot_ru_payment_price))
    )
    await state.set_state(BuyStates.selecting_plan)
    await callback.answer()


@buy_router.callback_query(
    StateFilter(BuyStates.selecting_plan),
    F.data.startswith("buy_plan_")
)
async def handle_plan_selection(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    region = data["region"]
    plan_data = callback.data.replace("buy_plan_", "")
    
    if plan_data in ("gift", "chatgpt", "other", "plat_1", "plat_6", "promo"):
        await callback.answer("Эта опция недоступна.", show_alert=True)
        return
        
    months = int(plan_data.split("_")[1])
    await state.update_data(months=months)
    
    currency = "₸" if region == "KZ" else "₽"
    base_price = int(settings.bot_default_payment_price if region == "KZ" else settings.bot_ru_payment_price)
    price = base_price * months
    await state.update_data(price=price)
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    order_id = data.get("order_id") or f"{int(datetime.now().timestamp()) % 100000:05d}{random.randint(100, 999)}"
    await state.update_data(order_id=order_id)
    
    _start_order_timer(bot, callback.from_user.id, order_id, state)
    
    pay_method = "Kaspi" if region == "KZ" else "VTB"
    
    text = (
        f"🧾 <b>Товар:</b> Подписка Spotify Premium на {months} месяц{'ев' if months > 4 else 'а' if months > 1 else ''}\n"
        f"💰 <b>Цена:</b> {price} {currency}\n"
        f"📦 <b>Кол-во:</b> 1 шт.\n"
        f"💡 <b>Заказ:</b> <code>{order_id}</code>\n"
        f"🕦 <b>Время заказа:</b> {now_str}\n"
        f"⚪ <b>Итоговая сумма:</b> {price} {currency}\n"
        f"💲 <b>Способ оплаты:</b> {pay_method}\n"
        f"-----------------\n"
        f"Перейдите по ссылке для оплаты\n"
        f"⏰ <b>Время на оплату:</b> 30 минут\n"
        f"-----------------\n"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_pay_button_keyboard(price, currency, region, payment_link=settings.bot_payment_link)
    )
    await callback.answer()


@buy_router.callback_query(
    StateFilter(BuyStates.selecting_plan),
    F.data == "buy_back_to_plans"
)
async def handle_back_to_plans(callback: types.CallbackQuery, state: FSMContext):
    """User clicks 'Back' on the invoice screen to return to plan selection."""
    data = await state.get_data()
    region = data["region"]
    base_price = int(settings.bot_default_payment_price if region == "KZ" else settings.bot_ru_payment_price)

    text = (
        "Срок выполнения заказа: от 10 минут до 24 часов\n\n"
        "<i>Выберите подписку:</i>"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_plans_keyboard(region, base_price=base_price)
    )
    await callback.answer()


@buy_router.callback_query(
    StateFilter(BuyStates.selecting_plan),
    F.data == "buy_pay_confirm"
)
async def handle_pay_confirm(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    region = data["region"]
    months = data.get("months", 1)
    default_price = int(settings.bot_default_payment_price if region == "KZ" else settings.bot_ru_payment_price)
    price = data.get("price", default_price)
    currency = "₸" if region == "KZ" else "₽"
    
    if region == "KZ":
        text = (
            f"<b>{price} {currency}</b>\n\n"
            "🤖 Пожалуйста, отправьте квитанцию об оплате <b>(PDF файл)</b> \n"
            "Затем вам нужно будет ввести логин и пароль.\n\n"
        )
    else:
        card = settings.bot_ru_payment_card
        bank = settings.bot_ru_payment_bank
        recipient = settings.bot_ru_payment_recipient
        text = (
            f"<b>{price} {currency}</b>\n\n"
            f"<code>{card}</code> - <b>{bank}</b> (<code>{recipient}</code>)\n\n"
            "🤖 Пожалуйста, отправьте квитанцию об оплате <b>(PDF файл)</b> \n"
            "Затем вам нужно будет ввести логин и пароль.\n\n"
        )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(BuyStates.uploading_receipt)
    await callback.answer()


# ── Step 2.5: User uploads receipt ───────────────────────────────────────────

@buy_router.message(StateFilter(BuyStates.uploading_receipt), F.document)
async def handle_buy_receipt_document(message: types.Message, state: FSMContext):
    receipt_file_id = message.document.file_id
    await state.update_data(receipt_file_id=receipt_file_id, receipt_type="document")

    data = await state.get_data()
    region = data["region"]

    await message.answer(
        f"✅ Квитанция получена.\n\n"
        f"Шаг 2 из 3 — Введите email или имя пользователя Spotify:\n\n"
        f"💡 Если аккаунт создан через Google/Apple, <a href='https://t.me/sptfykz/114'>сначала отвяжите его по инструкции</a>.\n"
        f"Затем введите системный логин (пример: <code>77ojssakeifsdsbg...</code>).\n\n",
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(BuyStates.entering_login)

@buy_router.message(StateFilter(BuyStates.uploading_receipt), F.photo)
async def handle_buy_receipt_photo(message: types.Message, state: FSMContext):
    """Accept a photo as receipt fallback."""
    receipt_file_id = message.photo[-1].file_id
    await state.update_data(receipt_file_id=receipt_file_id, receipt_type="photo")

    await message.answer(
        f"✅ Чек получен (фото).\n\n"
        f"Шаг 2 из 3 — Введите email или имя пользователя Spotify:\n\n"
        f"💡 Если аккаунт создан через Google/Apple, <a href='https://t.me/sptfykz/114'>сначала отвяжите его по инструкции</a>.\n"
        f"Затем введите системный логин (пример: <code>77ojssakeifsdsbg...</code>).\n\n",
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(BuyStates.entering_login)


@buy_router.message(StateFilter(BuyStates.uploading_receipt))
async def handle_buy_receipt_fallback(message: types.Message, state: FSMContext):
    """Handle cancel or invalid input during receipt upload."""
    text = message.text
    if text and text.lower() in ("отмена", "cancel"):
        _cancel_order_timer(message.from_user.id)
        await state.clear()
        await message.answer("❌ Покупка подписки отменена.", reply_markup=get_unregistered_user_menu())
        return

    await message.answer("❌ Пожалуйста, отправьте квитанцию об оплате <b>файлом (PDF)</b>.", parse_mode="HTML", reply_markup=get_cancel_keyboard())


# ── Cancel early (from region keyboard) ──────────────────────────────────────

@buy_router.callback_query(F.data == "buy_cancel_early")
async def handle_buy_cancel_early(callback: types.CallbackQuery, state: FSMContext):
    _cancel_order_timer(callback.from_user.id)
    await state.clear()
    await callback.message.edit_text(
        "❌ Покупка подписки отменена.",
        reply_markup=get_unregistered_user_menu()
    )
    await callback.answer()


# ── Step 3: Login entered → ask for password ─────────────────────────────────

@buy_router.message(StateFilter(BuyStates.entering_login))
async def handle_login_input(message: types.Message, state: FSMContext):
    text = message.text
    if not text:
        await message.answer("❌ Пожалуйста, введите текстовое сообщение.")
        return

    login = text.strip()

    if login.lower() in ("отмена", "cancel"):
        _cancel_order_timer(message.from_user.id)
        await state.clear()
        await message.answer("❌ Покупка подписки отменена.", reply_markup=get_unregistered_user_menu())
        return

    if len(login) < 3 or len(login) > 150:
        await message.answer("❌ Неверный формат. Введите корректный email или имя пользователя.")
        return

    await state.update_data(spotify_login=login)

    await message.answer(
        "✅ Логин принят.\n\n"
        "Шаг 3 из 3 — Введите <b>пароль</b> от Spotify:\n\n",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(BuyStates.entering_password)


# ── Step 4: Password entered → show confirmation ────────────────────────────

@buy_router.message(StateFilter(BuyStates.entering_password))
async def handle_password_input(message: types.Message, state: FSMContext):
    text = message.text
    if not text:
        await message.answer("❌ Пожалуйста, введите текстовое сообщение.")
        return

    password = text.strip()

    if password.lower() in ("отмена", "cancel"):
        _cancel_order_timer(message.from_user.id)
        await state.clear()
        await message.answer("❌ Покупка подписки отменена.", reply_markup=get_unregistered_user_menu())
        return

    # Removed password length validation as requested

    await state.update_data(spotify_password=password)

    data = await state.get_data()
    region = data["region"]
    login = data["spotify_login"]

    await message.answer(
        f"📋 <b>Проверьте данные перед отправкой</b>\n\n"
        f"🌍 Регион: {_region_emoji(region)} {region}\n"
        f"📧 Логин: <code>{login}</code>\n"
        f"🔒 Пароль: <code>{password}</code>\n\n"
        f"⚠️ После подтверждения заявка будет отправлена администратору.",
        parse_mode="HTML",
        reply_markup=get_buy_confirmation_keyboard()
    )
    await state.set_state(BuyStates.confirming_request)


# ── Step 5a: User confirms → send to admin channel ──────────────────────────

@buy_router.callback_query(
    StateFilter(BuyStates.confirming_request), F.data == "buy_confirm"
)
async def handle_buy_confirm(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    region = data["region"]
    login = data["spotify_login"]
    password = data["spotify_password"]
    user = callback.from_user

    # Re-check registration — user may have been registered externally during the flow
    if await db.is_user_registered(user.id):
        _cancel_order_timer(user.id)
        await state.clear()
        await callback.message.edit_text(
            "ℹ️ Вы уже зарегистрированы в группе.\n"
            "Используйте /status для проверки статуса.",
            reply_markup=get_user_main_menu()
        )
        await callback.answer()
        return

    # Ensure user exists in DB
    await db.add_user(user.id, user.username or user.first_name or "User", user.first_name)

    months = data.get("months", 1)
    price = data.get("price", 0)
    receipt_file_id = data.get("receipt_file_id")
    receipt_type = data.get("receipt_type", "photo")
    request_id = await db.create_purchase_request(
        user.id, region,
        months_paid=months,
        amount_paid=price,
        receipt_file_id=receipt_file_id,
        receipt_type=receipt_type,
    )
    if not request_id:
        await callback.message.edit_text("❌ Ошибка при создании заявки. Попробуйте позже.")
        _cancel_order_timer(user.id)
        await state.clear()
        await callback.answer()
        return

    username_str = f"@{user.username}" if user.username else "<i>нет username</i>"
    currency = "₸" if region == "KZ" else "₽"
    admin_text = (
        f"🆕 <b>НОВАЯ ЗАЯВКА НА ПОДПИСКУ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Пользователь:</b>\n"
        f"   Имя: {user.first_name or 'N/A'}\n"
        f"   Username: {username_str}\n"
        f"   Telegram ID: <code>{user.id}</code>\n\n"
        f"🌍 <b>Регион:</b> {_region_emoji(region)} {region}\n"
        f"📦 <b>Подписка:</b> {months} мес. — {price} {currency}\n\n"
        f"🎵 <b>Данные Spotify:</b>\n"
        f"   Логин: <code>{login}</code>\n"
        f"   Пароль: <code>{password}</code>\n\n"
        f"📅 {format_datetime(get_now())}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    try:
        receipt_file_id = data.get("receipt_file_id")
        receipt_type = data.get("receipt_type", "photo")
        
        if receipt_type == "document":
            sent = await bot.send_document(
                chat_id=settings.tg_admin_channel_id,
                document=receipt_file_id,
                caption=admin_text,
                parse_mode="HTML",
                reply_markup=get_buy_admin_keyboard(user.id, request_id),
            )
        else:
            sent = await bot.send_photo(
                chat_id=settings.tg_admin_channel_id,
                photo=receipt_file_id,
                caption=admin_text,
                parse_mode="HTML",
                reply_markup=get_buy_admin_keyboard(user.id, request_id),
            )
        await db.set_purchase_request_message_id(request_id, sent.message_id)
    except Exception as e:
        logger.error(f"Failed to send buy request to admin channel: {e}")
        await db.reject_purchase_request(request_id)
        await callback.message.edit_text("❌ Не удалось отправить заявку. Попробуйте позже.")
        await state.clear()
        await callback.answer()
        return

    await callback.message.edit_text(
        f"✅ <b>Заявка #{request_id} отправлена!</b>\n\n"
        f"⏳ Администратор обработает её в ближайшее время.\n"
        f"Вы получите уведомление, когда будете подключены к подписке.",
        parse_mode="HTML"
    )
    _cancel_order_timer(user.id)
    await state.clear()
    await callback.answer("✅ Заявка отправлена!")


# ── Step 5b: User cancels ────────────────────────────────────────────────────

@buy_router.callback_query(
    StateFilter(BuyStates.confirming_request), F.data == "buy_cancel"
)
async def handle_buy_cancel(callback: types.CallbackQuery, state: FSMContext):
    _cancel_order_timer(callback.from_user.id)
    await state.clear()
    await callback.message.edit_text(
        "❌ Покупка подписки отменена.",
        reply_markup=get_unregistered_user_menu()
    )
    await callback.answer()


# ═══════════════════════════════════════════════════════════════════════════════
#  ADMIN FLOW  (callbacks from the admin channel)
# ═══════════════════════════════════════════════════════════════════════════════


@buy_router.callback_query(F.data.startswith("buy_accept_"))
async def handle_admin_accept(callback: types.CallbackQuery, state: FSMContext):
    """
    Admin clicks 'Accept'. Bot asks for group ID in the admin channel.
    Callback data: buy_accept_{user_id}_{request_id}

    Uses _pending_admin_ops (keyed by admin user_id) instead of FSM state
    so that multiple admins can work in the same channel without collisions.
    """
    if callback.from_user.id not in settings.tg_admin_ids:
        await callback.answer("⛔ Недостаточно прав", show_alert=True)
        return

    parts = callback.data.split("_")
    if len(parts) != 4:
        await callback.answer("❌ Неверный формат", show_alert=True)
        return

    try:
        user_id = int(parts[2])
        request_id = int(parts[3])
    except ValueError:
        await callback.answer("❌ Неверный формат данных", show_alert=True)
        return

    admin_id = callback.from_user.id

    # Protect against double-accept by the same admin
    if admin_id in _pending_admin_ops:
        await callback.answer("⏳ Завершите текущее назначение (введите ID группы или Отмена) перед принятием другой заявки.", show_alert=True)
        return

    _pending_admin_ops[admin_id] = {
        "user_id": user_id,
        "request_id": request_id,
        "admin_msg_id": callback.message.message_id,
        "admin_msg_html": callback.message.html_text,
        "chat_id": callback.message.chat.id,
    }
    await state.set_state(BuyStates.admin_entering_group_id)

    # Edit message: remove buttons, ask for group ID
    await callback.message.edit_caption(
        caption=callback.message.html_text
        + "\n\n⏳ <b>Введите ID группы</b> (например: 001):\n"
          "Или отправьте <code>отмена</code> для отмены.",
        parse_mode="HTML",
        reply_markup=None,
    )
    await callback.answer()


@buy_router.message(StateFilter(BuyStates.admin_entering_group_id))
async def handle_admin_group_id_input(message: types.Message, state: FSMContext, bot: Bot):
    """Admin types a group ID (e.g. '001') in the admin channel."""
    # Only accept input from the designated admin channel
    if message.chat.id != settings.tg_admin_channel_id:
        return

    text = message.text
    if not text:
        return

    admin_id = message.from_user.id
    op = _pending_admin_ops.get(admin_id)
    if not op:
        # No pending operation for this admin — ignore
        await state.clear()
        return

    text = text.strip()
    user_id = op["user_id"]
    request_id = op["request_id"]
    admin_msg_id = op["admin_msg_id"]
    original_html = op["admin_msg_html"]
    chat_id = op["chat_id"]

    # Cancel
    if text.lower() in ("отмена", "cancel"):
        _pending_admin_ops.pop(admin_id, None)
        await state.clear()
        # Restore original message with buttons
        try:
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=admin_msg_id,
                caption=original_html,
                parse_mode="HTML",
                reply_markup=get_buy_admin_keyboard(user_id, request_id),
            )
        except Exception:
            pass
        await message.answer("❌ Назначение отменено. Кнопки восстановлены.")
        return

    # Validate group
    group = await db.get_group_by_display_id(text)
    if not group:
        await message.answer(f"❌ Группа <code>{text}</code> не найдена. Попробуйте ещё раз.", parse_mode="HTML")
        return

    # Check if user is already registered
    if await db.is_user_registered(user_id):
        _pending_admin_ops.pop(admin_id, None)
        await state.clear()
        await message.answer("⚠️ Пользователь уже зарегистрирован в группе!")
        return

    # Fetch purchase request data before the transaction
    pr = await db.get_purchase_request(request_id)
    months_paid = pr.get('months_paid', 1) if pr else 1
    receipt_fid = pr.get('receipt_file_id') if pr else None

    # Atomically: add to group + record payment + approve request
    ok, next_date, err = await db.accept_purchase_request_tx(
        user_id, group.group_id, request_id, months_paid, receipt_fid
    )
    if not ok:
        await message.answer(f"❌ Не удалось оформить подписку ({err}). Попробуйте ещё раз.")
        return

    _pending_admin_ops.pop(admin_id, None)
    await state.clear()

    # Determine region for the notification
    region = "RU" if group.display_id.startswith("1") else "KZ"

    # Notify the user
    user_msg = (
        f"🎉 <b>💚 Добро пожаловать в Spotify Premium! Можете авторизоваться в свой аккаунт и проверить подписку! </b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Группа: <b>{group.group_name}</b>\n"
        f"🌍 Регион: {_region_emoji(region)} {region}\n"
    )
    status = await db.get_user_payment_status(user_id)
    if status:
        user_msg += f"📅 Следующий платёж: <b>{format_date(status.next_payment_date)}</b>\n"
    user_msg += (
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📱 /status — проверить статус\n"
        f"💳 /pay — оплатить подписку"
    )

    try:
        await bot.send_message(
            chat_id=user_id, text=user_msg,
            parse_mode="HTML", reply_markup=get_user_main_menu()
        )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id}: {e}")

    # Update admin channel message
    try:
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=admin_msg_id,
            caption=original_html
                 + f"\n\n✅ <b>ОДОБРЕНО</b> → <b>{group.group_name}</b>\n"
                   f"🕐 {format_datetime(get_now())}",
            parse_mode="HTML",
            reply_markup=None,
        )
    except Exception:
        pass

    await message.answer(f"✅ Пользователь добавлен в <b>{group.group_name}</b>!", parse_mode="HTML")


@buy_router.callback_query(F.data.startswith("buy_reject_"))
async def handle_admin_reject(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """
    Admin clicks 'Reject'.
    Callback data: buy_reject_{user_id}_{request_id}
    """
    if callback.from_user.id not in settings.tg_admin_ids:
        await callback.answer("⛔ Недостаточно прав", show_alert=True)
        return

    parts = callback.data.split("_")
    if len(parts) != 4:
        await callback.answer("❌ Неверный формат", show_alert=True)
        return

    try:
        user_id = int(parts[2])
        request_id = int(parts[3])
    except ValueError:
        await callback.answer("❌ Неверный формат данных", show_alert=True)
        return

    admin_id = callback.from_user.id
    # Check if THIS admin is in the middle of assigning another request
    if admin_id in _pending_admin_ops:
        await callback.answer("⏳ Завершите текущее назначение перед отклонением другой заявки.", show_alert=True)
        return

    await db.reject_purchase_request(request_id)

    # Notify the user
    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                "❌ <b>Заявка отклонена</b>\n\n"
                "Администратор не смог войти в ваш аккаунт Spotify.\n"
                "Пожалуйста, проверьте логин и пароль и отправьте заново, "
                f"или свяжитесь с менеджером: @{settings.bot_support_username}"
            ),
            parse_mode="HTML",
            reply_markup=get_rejected_user_keyboard(request_id),
        )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id} about rejection: {e}")

    await callback.message.edit_caption(
        caption=callback.message.html_text
        + f"\n\n❌ <b>ОТКЛОНЕНО</b>\n🕐 {format_datetime(get_now())}",
        parse_mode="HTML",
        reply_markup=None,
    )
    await callback.answer("❌ Заявка отклонена")


# ── Resend credentials after rejection ───────────────────────────────────────

@buy_router.callback_query(F.data.startswith("buy_resend_"))
async def handle_resend_credentials(callback: types.CallbackQuery, state: FSMContext):
    """User clicks 'Resend credentials' after admin rejection."""
    parts = callback.data.split("_")
    if len(parts) != 3:
        await callback.answer("❌ Неверный формат", show_alert=True)
        return

    try:
        old_request_id = int(parts[2])
    except ValueError:
        await callback.answer("❌ Неверный формат данных", show_alert=True)
        return

    # Fetch the old request to carry over region, months, receipt
    pr = await db.get_purchase_request(old_request_id)
    if not pr:
        await callback.answer("❌ Заявка не найдена", show_alert=True)
        return

    # Pre-fill FSM data from the old request
    await state.update_data(
        region=pr["region"],
        months=pr.get("months_paid", 1),
        price=pr.get("amount_paid", 0),
        receipt_file_id=pr.get("receipt_file_id"),
        receipt_type=pr.get("receipt_type", "photo"),
    )

    await callback.message.edit_text(
        "🔄 <b>Повторная отправка данных</b>\n\n"
        "Введите <b>логин</b> (email) от Spotify:\n\n",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(BuyStates.entering_login)
    await callback.answer()
