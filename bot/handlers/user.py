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
from bot.utils.states import PaymentStates
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
async def start_command(message: types.Message):
    """Handle /start command"""
    if message.chat.type != ChatType.PRIVATE:
        return
    
    user = message.from_user
    username = user.username or user.first_name or "User"
    
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
                    f"👋 Welcome back, {username}!\n\n"
                    f"👥 Group: **{status.group_name}**\n"
                    f"{emoji} Next payment: {format_date(status.next_payment_date)}\n"
                    f"📊 Status: {get_payment_status_text(days_until)}\n\n"
                    f"💡 Use /pay to upload a payment receipt\n"
                    f"📋 Use /status for detailed payment information\n"
                    f"❓ Use /help for all available commands"
                )
            else:
                welcome_text = (
                    f"👋 Welcome, {username}!\n\n"
                    f"⚠️ There's an issue with your account.\n"
                    f"Please contact an admin for assistance."
                )
        else:
            welcome_text = (
                f"👋 Welcome, {username}!\n\n"
                f"🔒 You're not registered in any payment group yet.\n"
                f"Please contact an admin to be added to a group.\n\n"
                f"Once registered, you'll be able to:\n"
                f"• 💳 Upload payment receipts\n"
                f"• 📊 Check payment status\n"
                f"• 📅 Track payment history"
            )
    else:
        welcome_text = (
            f"👋 Welcome, {username}!\n\n"
            f"⚠️ Database is currently unavailable.\n"
            f"Please try again later."
        )
    
    await message.answer(welcome_text, parse_mode="Markdown")


@user_router.message(Command("help"))
async def help_command(message: types.Message):
    """Handle /help command"""
    if message.chat.type != ChatType.PRIVATE:
        return
    
    help_text = (
        "🤖 **Spotify Payment Bot Help**\n\n"
        "**Available Commands:**\n"
        "🏠 /start - Welcome message and status overview\n"
        "💳 /pay - Upload payment receipt\n"
        "📊 /status - Check your payment status\n"
        "❓ /help - Show this help message\n\n"
        "**How to pay:**\n"
        "1. Use the /pay command\n"
        "2. Select how many months to pay (1-6)\n"
        "3. Upload your bank transfer receipt\n"
        "4. Payment will be processed automatically\n\n"
        "**Supported receipt formats:**\n"
        "• 📷 Photos (JPG, PNG)\n"
        "• 📄 PDF documents\n\n"
        "**Need help?** Contact an admin if you have any issues."
    )
    
    await message.answer(help_text, parse_mode="Markdown")


@user_router.message(Command("status"))
async def status_command(message: types.Message):
    """Handle /status command"""
    if message.chat.type != ChatType.PRIVATE:
        return
    
    if not db or not db.pool:
        await message.answer(
            "❌ Database is currently unavailable.\n"
            "Please try again later."
        )
        return
    
    user_id = message.from_user.id
    
    # Check if user is registered
    if not await db.is_user_registered(user_id):
        await message.answer(
            "❌ You're not registered in any payment group yet.\n"
            "Please contact an admin to be added to a group."
        )
        return
    
    # Get payment status
    status = await db.get_user_payment_status(user_id)
    if not status:
        await message.answer(
            "❌ Unable to retrieve your payment information.\n"
            "Please contact an admin."
        )
        return
    
    days_until = calculate_days_until(status.next_payment_date)
    emoji = get_payment_status_emoji(days_until)
    status_text = get_payment_status_text(days_until)
    
    response = (
        f"{emoji} **Payment Status**\n\n"
        f"👥 Group: {status.group_name}\n"
        f"📅 Next payment due: {format_date(status.next_payment_date)}\n"
        f"📊 Status: {status_text}\n"
    )
    
    if status.last_payment_date:
        response += f"💰 Last payment: {format_date(status.last_payment_date)}\n"
    
    if days_until <= 3:
        response += f"\n💡 Use /pay to make a payment"
    
    await message.answer(response, parse_mode="Markdown")


@user_router.message(Command("pay"))
async def pay_command(message: types.Message, state: FSMContext):
    """Handle /pay command"""
    if message.chat.type != ChatType.PRIVATE:
        return
    
    if not db or not db.pool:
        await message.answer(
            "❌ Database is currently unavailable.\n"
            "Please try again later."
        )
        return
    
    user_id = message.from_user.id
    
    # Check if user is registered
    if not await db.is_user_registered(user_id):
        await message.answer(
            "❌ You're not registered in any payment group yet.\n"
            "Please contact an admin to be added to a group."
        )
        return
    
    # Get user's current status
    status = await db.get_user_payment_status(user_id)
    if not status:
        await message.answer(
            "❌ Unable to retrieve your payment information.\n"
            "Please contact an admin."
        )
        return
    
    days_until = calculate_days_until(status.next_payment_date)
    emoji = get_payment_status_emoji(days_until)
    
    # Show current status and payment options
    status_message = (
        f"💳 **Payment for Group: {status.group_name}**\n\n"
        f"{emoji} Next payment due: {format_date(status.next_payment_date)}\n"
        f"📊 Status: {get_payment_status_text(days_until)}\n\n"
        f"Please select how many months you want to pay:"
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
        f"✅ You selected **{months} month{'s' if months != 1 else ''}**\n\n"
        f"📎 Please upload your payment receipt\n\n"
        f"💡 Accepted formats: JPG, PNG, PDF\n"
        f"After uploading, your payment will be processed automatically.",
        parse_mode="Markdown"
    )
    
    await callback.answer()
    await state.set_state(PaymentStates.uploading_receipt)


@user_router.callback_query(F.data == "cancel_payment")
async def cancel_payment(callback: types.CallbackQuery, state: FSMContext):
    """Cancel payment process"""
    await callback.message.edit_text("❌ Payment process cancelled.")
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
            "❌ Unsupported file type. Please upload:\n"
            "• Photo (JPG, PNG)\n"
            "• PDF document"
        )
        return
    
    await process_receipt_upload(message, state, document.file_id)


async def process_receipt_upload(message: types.Message, state: FSMContext, file_id: str):
    """Process receipt upload and record payment"""
    try:
        data = await state.get_data()
        months = data.get('months')
        
        if not months:
            await message.answer("❌ Error: Payment duration not found. Please start over with /pay")
            await state.clear()
            return
        
        user_id = message.from_user.id
        
        # Get user's group
        group = await db.get_user_group(user_id)
        if not group:
            await message.answer("❌ Error: Unable to find your group. Please contact an admin.")
            await state.clear()
            return
        
        # Record payment
        success = await db.add_payment(user_id, group.group_id, months, file_id)
        
        if success:
            await message.answer(
                f"✅ **Payment Confirmed!**\n\n"
                f"💰 Paid for: {months} month{'s' if months != 1 else ''}\n"
                f"📅 Payment processed: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"👥 Group: {group.group_name}\n\n"
                f"Thank you for your payment! 🎉\n"
                f"Your subscription has been extended.",
                parse_mode="Markdown"
            )
            
            logger.info(f"Payment processed: User {user_id} paid for {months} months in group {group.group_name}")
        else:
            await message.answer(
                "❌ **Payment Processing Failed**\n\n"
                "There was an error processing your payment.\n"
                "Please contact an admin or try again later.",
                parse_mode="Markdown"
            )
            logger.error(f"Payment processing failed for user {user_id}")
        
        await state.clear()
        
    except Exception as e:
        await message.answer(
            "❌ **An error occurred**\n\n"
            "Please contact an admin or try again later.",
            parse_mode="Markdown"
        )
        logger.error(f"Error in payment processing: {e}")
        await state.clear()


@user_router.message(StateFilter(PaymentStates.uploading_receipt))
async def handle_invalid_receipt(message: types.Message):
    """Handle invalid receipt uploads"""
    await message.answer(
        "❌ **Invalid receipt format**\n\n"
        "Please upload a valid receipt:\n"
        "• 📷 Photo (JPG, PNG)\n"
        "• 📄 PDF document\n\n"
        "Or use /pay to start over.",
        parse_mode="Markdown"
    )