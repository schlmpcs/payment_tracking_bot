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
    confirming_group = State()


class AdminStates(StatesGroup):
    """Admin operation states"""
    creating_group = State()
    creating_group_date = State()
    adding_user_username = State()
    adding_user_group = State()
    deleting_group_select = State()
    deleting_group_confirm = State()
    removing_user_select_group = State()
    removing_user_select_user = State()
    updating_due_date_group = State()
    updating_due_date_date = State()
    importing_groups_file = State()
    importing_groups_confirm = State()
    fraud_check_date = State()
    fraud_check_file = State()
    broadcasting_message = State()
    broadcasting_confirm = State()
