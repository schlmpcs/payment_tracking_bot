from datetime import datetime
from typing import Tuple
from aiogram import Router, types, F
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext

from .users.user import User
from ..tools import ErrorLogger
from ..tools.forms import PayForm

user_router = Router()
user = User()

logger = ErrorLogger()


@user_router.message(Command("start"))
async def start_command(message: types.Message):
    """Welcome message for users"""
    if message.chat.type != ChatType.PRIVATE:
        return  # Only process DMs
    
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    # Check if user is registered
    is_registered = await user.is_registered(user_id)
    
    if is_registered:
        # Get user's group info
        payment_info = await user.get_payment_info(user_id)
        if payment_info:
            group_id, group_name, next_payment, last_paid = payment_info
            welcome_text = (
                f"👋 Welcome back, {username}!\n\n"
                f"You're registered in group: **{group_name}**\n"
                f"Next payment due: {next_payment.strftime('%Y-%m-%d')}\n\n"
                f"Use /status to check your payment status\n"
                f"Use /pay to upload a payment receipt\n"
                f"Use /help for more information"
            )
        else:
            welcome_text = (
                f"👋 Welcome, {username}!\n\n"
                f"There seems to be an issue with your account.\n"
                f"Please contact the admin for assistance."
            )
    else:
        welcome_text = (
            f"👋 Welcome, {username}!\n\n"
            f"🔒 You are not registered in any payment group yet.\n"
            f"Please contact the admin to be added to a group.\n\n"
            f"Once registered, you'll be able to:\n"
            f"• 💳 Upload payment receipts\n"
            f"• 📊 Check payment status\n"
            f"• 📅 Track payment history"
        )
    
    await message.answer(welcome_text)


@user_router.message(Command("pay"))
async def pay_bill(message: types.Message, state: FSMContext):
    """Start payment process"""
    if message.chat.type != ChatType.PRIVATE:
        return  # Only process DMs

    user_id = message.from_user.id
    
    # Check database connection first
    from ..routers.users.admin import db
    if not db.pool:
        await message.answer(
            "❌ Database connection is not available.\n"
            "Please try again later or contact the admin."
        )
        return
    
    # Check if user is registered in the system
    if not await user.is_registered(user_id):
        await message.answer(
            "❌ You are not registered in any payment group yet.\n"
            "Please contact the admin to be added to a group."
        )
        return

    # Get user's payment info
    payment_info = await user.get_payment_info(user_id)
    if not payment_info:
        await message.answer(
            "❌ Unable to retrieve your payment information.\n"
            "Please contact the admin."
        )
        return

    group_id, group_name, next_payment, last_paid = payment_info
    
    # Show current status
    await message.answer(
        f"💳 **Payment for Group: {group_name}**\n\n"
        f"📅 Next payment due: {next_payment.strftime('%Y-%m-%d')}\n"
        f"💰 Last payment: {last_paid.strftime('%Y-%m-%d %H:%M') if last_paid else 'Never'}\n\n"
        "Please select how many months you want to pay:"
    )

    # Create inline keyboard with month options
    builder = InlineKeyboardBuilder()
    for i in range(1, 7):
        builder.button(text=f"{i} month{'s' if i != 1 else ''}", callback_data=f"month_{i}")
    builder.adjust(2)
    builder.row(types.InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_payment"))

    await message.answer(
        "Select payment duration:",
        reply_markup=builder.as_markup()
    )
    
    # Set state
    await state.set_state(PayForm.months)


@user_router.callback_query(F.data.startswith("month_"), PayForm.months)
async def handle_month_choice(callback: types.CallbackQuery, state: FSMContext):
    """Handle month selection"""
    months = int(callback.data.split("_")[1])
    
    # Store selected months in state
    await state.update_data(months=months)
    
    await callback.message.edit_text(
        f"✅ You selected **{months} month{'s' if months != 1 else ''}**\n\n"
        "📎 **Please upload your payment receipt** (screenshot or photo)\n\n"
        "💡 Accepted formats: JPG, PNG, PDF\n"
        "After uploading, your payment will be automatically processed."
    )
    
    await callback.answer()
    await state.set_state(PayForm.payment)


@user_router.callback_query(F.data == "cancel_payment")
async def cancel_payment(callback: types.CallbackQuery, state: FSMContext):
    """Cancel payment process"""
    await callback.message.edit_text("❌ Payment process cancelled.")
    await callback.answer()
    await state.clear()


@user_router.message(PayForm.payment, F.photo)
async def handle_photo_receipt(message: types.Message, state: FSMContext):
    """Handle photo receipt upload"""
    await process_receipt_upload(message, state)


@user_router.message(PayForm.payment, F.document)
async def handle_document_receipt(message: types.Message, state: FSMContext):
    """Handle document receipt upload (PDF, etc.)"""
    document = message.document
    
    # Check if it's a supported document type
    if document.mime_type not in ['application/pdf', 'image/jpeg', 'image/png']:
        await message.answer(
            "❌ Unsupported file type. Please upload:\n"
            "• Photo (JPG, PNG)\n"
            "• PDF document"
        )
        return
        
    await process_receipt_upload(message, state)


async def process_receipt_upload(message: types.Message, state: FSMContext):
    """Process the receipt upload and update payment status"""
    try:
        # Get stored data
        data = await state.get_data()
        months = data.get('months')
        
        if not months:
            await message.answer("❌ Error: Payment duration not found. Please start over with /pay")
            await state.clear()
            return

        user_id = message.from_user.id
        
        # Process payment in database
        success = await user.process_payment(user_id, months)
        
        if success:
            await message.answer(
                f"✅ **Payment Confirmed!**\n\n"
                f"💰 Paid for: {months} month{'s' if months != 1 else ''}\n"
                f"📅 Payment processed: {message.date.strftime('%Y-%m-%d %H:%M')}\n\n"
                f"Thank you for your payment! 🎉\n"
                f"Your subscription has been extended."
            )
            
            # Log successful payment
            logger.logger.info(f"Payment processed: User {user_id} paid for {months} months")
            
        else:
            await message.answer(
                "❌ **Payment Processing Failed**\n\n"
                "There was an error processing your payment.\n"
                "Please contact the admin or try again later."
            )
            logger.logger.error(f"Payment processing failed for user {user_id}")
            
        await state.clear()
        
    except Exception as e:
        await message.answer(
            "❌ **An error occurred**\n\n"
            "Please contact the admin or try again later."
        )
        logger.logger.error(f"Error in payment processing: {e}")
        await state.clear()


@user_router.message(PayForm.payment)
async def handle_invalid_receipt(message: types.Message):
    """Handle invalid receipt uploads"""
    await message.answer(
        "❌ **Invalid receipt format**\n\n"
        "Please upload a valid receipt:\n"
        "• 📷 Photo (JPG, PNG)\n"
        "• 📄 PDF document\n\n"
        "Or type /pay to start over."
    )


@user_router.message(Command("status"))
async def check_payment_status(message: types.Message):
    """Check user's payment status"""
    if message.chat.type != ChatType.PRIVATE:
        return  # Only process DMs

    user_id = message.from_user.id
    
    # Check if user is registered
    if not await user.is_registered(user_id):
        await message.answer(
            "❌ You are not registered in any payment group yet.\n"
            "Please contact the admin to be added to a group."
        )
        return

    # Get payment info
    payment_info = await user.get_payment_info(user_id)
    if not payment_info:
        await message.answer(
            "❌ Unable to retrieve your payment information.\n"
            "Please contact the admin."
        )
        return

    group_id, group_name, next_payment, last_paid = payment_info
    
    # Calculate days until payment
    today = datetime.now().date()
    next_payment_date = next_payment.date() if hasattr(next_payment, 'date') else next_payment
    days_diff = (next_payment_date - today).days
    
    # Prepare status message
    if days_diff > 0:
        status_emoji = "✅"
        status_text = f"Paid until {next_payment_date.strftime('%Y-%m-%d')}"
        days_text = f"({days_diff} days remaining)"
    elif days_diff == 0:
        status_emoji = "⚠️"
        status_text = "Payment due TODAY"
        days_text = ""
    else:
        status_emoji = "❌"
        status_text = "OVERDUE"
        days_text = f"({abs(days_diff)} days overdue)"
    
    await message.answer(
        f"{status_emoji} **Payment Status**\n\n"
        f"👥 Group: {group_name}\n"
        f"📅 Status: {status_text} {days_text}\n"
        f"💰 Last payment: {last_paid.strftime('%Y-%m-%d %H:%M') if last_paid else 'Never'}\n\n"
        f"{'💡 Use /pay to make a payment' if days_diff <= 3 else ''}"
    )


@user_router.message(Command("help"))
async def show_help(message: types.Message):
    """Show available commands"""
    if message.chat.type != ChatType.PRIVATE:
        return  # Only process DMs
    
    help_text = (
        "🤖 **Spotify Payment Bot Help**\n\n"
        "**Available Commands:**\n"
        "🏠 /start - Welcome message and status\n"
        "💳 /pay - Upload payment receipt\n"
        "📊 /status - Check your payment status\n"
        "👨‍💼 /contact_admin - Get admin contact info\n"
        "❓ /help - Show this help message\n\n"
        "**How to pay:**\n"
        "1. Use /pay command\n"
        "2. Select how many months to pay\n"
        "3. Upload your bank transfer receipt\n"
        "4. Payment will be automatically processed\n\n"
        "**Supported receipt formats:**\n"
        "• 📷 Photos (JPG, PNG)\n"
        "• 📄 PDF documents\n\n"
        "**Need help?** Contact the admin if you have any issues."
    )
    
    await message.answer(help_text)


@user_router.message(Command("contact_admin"))
async def contact_admin(message: types.Message):
    """Provide admin contact information"""
    if message.chat.type != ChatType.PRIVATE:
        return  # Only process DMs
    
    await message.answer(
        "👨‍💼 **Contact Admin**\n\n"
        "If you need assistance with:\n"
        "• Registration in a payment group\n"
        "• Payment issues or disputes\n"
        "• Technical problems with the bot\n"
        "• Account modifications\n\n"
        "Please contact the administrator directly.\n\n"
        "💡 Make sure to include your username and describe your issue clearly."
    )