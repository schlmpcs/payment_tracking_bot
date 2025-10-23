"""
Admin command handlers for the Spotify Payment Bot
"""

import logging
from datetime import datetime, timedelta
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.enums import ChatType

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
        await message.answer("❌ Access denied. Admin only command.")
        return
    
    if not db or not db.pool:
        await message.answer("❌ Database is currently unavailable.")
        return
    
    await message.answer(
        "🔧 **Admin Panel**\n\n"
        "Choose an action:",
        reply_markup=get_admin_main_keyboard(),
        parse_mode="Markdown"
    )


@admin_router.callback_query(F.data == "admin_view_groups")
async def view_groups(callback: types.CallbackQuery):
    """View all payment groups"""
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Access denied", show_alert=True)
        return
    
    groups = await db.get_all_groups()
    
    if not groups:
        await callback.message.edit_text("📭 No payment groups found.")
        return
    
    response = "👥 **All Payment Groups:**\n\n"
    
    for group in groups:
        days_until = calculate_days_until(group.next_payment_date)
        emoji = get_payment_status_emoji(days_until)
        
        response += (
            f"{emoji} **{group.group_name}** (ID: {group.group_id})\n"
            f"📅 Next payment: {format_date(group.next_payment_date)}\n"
            f"📊 Status: {get_payment_status_text(days_until)}\n\n"
        )
    
    await callback.message.edit_text(response, parse_mode="Markdown")
    await callback.answer()


@admin_router.callback_query(F.data == "admin_overdue_users")
async def view_overdue_users(callback: types.CallbackQuery):
    """View users with overdue payments"""
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Access denied", show_alert=True)
        return
    
    overdue_users = await db.get_overdue_users()
    
    if not overdue_users:
        await callback.message.edit_text("✅ No overdue payments found!")
        return
    
    response = "❌ **Overdue Payments:**\n\n"
    
    for status in overdue_users:
        days_overdue = abs(calculate_days_until(status.next_payment_date))
        
        response += (
            f"👤 User ID: {status.user_id}\n"
            f"👥 Group: {status.group_name}\n"
            f"📅 Due date: {format_date(status.next_payment_date)}\n"
            f"⏰ Overdue: {days_overdue} days\n\n"
        )
    
    await callback.message.edit_text(response, parse_mode="Markdown")
    await callback.answer()


@admin_router.callback_query(F.data == "admin_create_group")
async def create_group_start(callback: types.CallbackQuery, state: FSMContext):
    """Start group creation process"""
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Access denied", show_alert=True)
        return
    
    await callback.message.edit_text(
        "➕ **Create New Group**\n\n"
        "Please enter the group name:"
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
        await message.answer("❌ Group name cannot be empty. Please try again.")
        return
    
    # Check if group already exists
    existing_group = await db.get_group_by_name(group_name)
    if existing_group:
        await message.answer(f"❌ Group '{group_name}' already exists.")
        await state.clear()
        return
    
    # Create group with next payment date set to next month
    next_payment_date = datetime.now() + timedelta(days=30)
    group_id = await db.create_group(group_name, next_payment_date)
    
    if group_id:
        await message.answer(
            f"✅ **Group Created Successfully!**\n\n"
            f"👥 Group name: {group_name}\n"
            f"🆔 Group ID: {group_id}\n"
            f"📅 Next payment date: {format_date(next_payment_date)}",
            parse_mode="Markdown"
        )
        logger.info(f"Admin {user_id} created group '{group_name}' (ID: {group_id})")
    else:
        await message.answer("❌ Failed to create group. Please try again.")
    
    await state.clear()


@admin_router.callback_query(F.data == "admin_add_user")
async def add_user_start(callback: types.CallbackQuery, state: FSMContext):
    """Start user addition process"""
    user_id = callback.from_user.id
    if not is_admin(user_id, settings.tg_admin_ids):
        await callback.answer("Access denied", show_alert=True)
        return
    
    await callback.message.edit_text(
        "👤 **Add User to Group**\n\n"
        "Please enter the user's Telegram ID (numeric):"
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


# Handle any unrecognized admin callback
@admin_router.callback_query(F.data.startswith("admin_"))
async def handle_unknown_admin_action(callback: types.CallbackQuery):
    """Handle unknown admin actions"""
    await callback.answer("This feature is not implemented yet.", show_alert=True)
