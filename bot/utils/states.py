"""
FSM States for the bot
"""

from aiogram.fsm.state import State, StatesGroup


class PaymentStates(StatesGroup):
    """Payment flow states"""
    selecting_months = State()
    uploading_receipt = State()


class JoinStates(StatesGroup):
    """Group joining states"""
    selecting_group = State()


class AdminStates(StatesGroup):
    """Admin operation states"""
    creating_group = State()
    adding_user_username = State()
    adding_user_group = State()
    deleting_confirmation = State()
    updating_due_date_group = State()
    updating_due_date_date = State()
    importing_groups_file = State()
    importing_groups_confirm = State()