"""
FSM States for the bot
"""

from aiogram.fsm.state import State, StatesGroup


class PaymentStates(StatesGroup):
    """Payment flow states"""
    selecting_group = State()    # multi-group: user picks which group to pay for
    selecting_months = State()
    uploading_receipt = State()


class JoinStates(StatesGroup):
    """Group joining states"""
    selecting_group = State()
    confirming_group = State()


class BuyStates(StatesGroup):
    """New subscription purchase flow states"""
    selecting_region = State()      # User picks KZ or RU
    selecting_plan = State()        # User selects plan (months)
    uploading_receipt = State()     # User uploads the receipt
    entering_login = State()        # User enters Spotify email/username
    entering_password = State()     # User enters temporary password
    confirming_request = State()    # User reviews and confirms the summary
    waiting_approval = State()      # Request sent; waiting for admin to assign group
    # Admin side (state lives in admin channel chat context)
    admin_entering_group_id = State()  # Admin typing group ID after Accept


class AdminStates(StatesGroup):
    """Admin operation states"""
    creating_group = State()
    creating_group_date = State()
    adding_user_username = State()
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
    setting_slots_group = State()
    setting_slots_user = State()
    ru_fraud_check_date = State()
