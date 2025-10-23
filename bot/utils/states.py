"""
FSM States for the bot
"""

from aiogram.fsm.state import State, StatesGroup


class PaymentStates(StatesGroup):
    """Payment flow states"""
    selecting_months = State()
    uploading_receipt = State()


class AdminStates(StatesGroup):
    """Admin operation states"""
    creating_group = State()
    adding_user_username = State()
    adding_user_group = State()
    deleting_confirmation = State()