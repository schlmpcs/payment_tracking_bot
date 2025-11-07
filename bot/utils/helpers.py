"""
Utility functions for the bot
"""

from datetime import datetime, timedelta
from typing import List
import logging


def format_date(date: datetime) -> str:
    """Format date for display"""
    return date.strftime("%Y-%m-%d")


def format_datetime(date: datetime) -> str:
    """Format datetime for display"""
    return date.strftime("%Y-%m-%d %H:%M")


def calculate_days_until(target_date) -> int:
    """Calculate days until target date"""
    from datetime import datetime, date
    
    # Handle both datetime and date objects
    if isinstance(target_date, datetime):
        target_date = target_date.date()
    elif isinstance(target_date, date):
        pass  # Already a date object
    else:
        raise TypeError(f"Expected datetime or date object, got {type(target_date)}")
    
    return (target_date - datetime.now().date()).days


def get_payment_status_emoji(days_until: int) -> str:
    """Get emoji based on payment status"""
    if days_until > 3:
        return "✅"  # Paid
    elif days_until >= 0:
        return "⚠️"  # Due soon
    else:
        return "❌"  # Overdue


def get_payment_status_text(days_until: int) -> str:
    """Get status text based on days until payment"""
    if days_until > 0:
        return f"Оплачено ({days_until} дней осталось)"
    elif days_until == 0:
        return "Платёж сегодня"
    else:
        return f"ПРОСРОЧЕНО ({abs(days_until)} дней)"


def is_admin(user_id: int, admin_ids: List[int]) -> bool:
    """Check if user is admin"""
    return user_id in admin_ids


def setup_logging() -> logging.Logger:
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('bot.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


def validate_file_type(mime_type: str) -> bool:
    """Validate if file type is acceptable for receipts"""
    allowed_types = [
        'image/jpeg',
        'image/png',
        'image/jpg',
        'application/pdf'
    ]
    return mime_type in allowed_types