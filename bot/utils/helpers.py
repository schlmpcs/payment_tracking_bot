"""
Utility functions for the bot
"""

from datetime import datetime
from typing import List
import logging
import pytz
from bot.config.settings import Settings

# Initialize settings
settings = Settings()

# Get timezone from settings
TIMEZONE = pytz.timezone(settings.bot_timezone)


def get_now() -> datetime:
    """Get current datetime in configured timezone (as naive datetime)"""
    # Get timezone-aware datetime, then convert to naive
    # Database expects naive datetimes
    return datetime.now(TIMEZONE).replace(tzinfo=None)


def get_today() -> datetime:
    """Get today's date (as datetime) in configured timezone"""
    return get_now().replace(hour=0, minute=0, second=0, microsecond=0)


def format_date(date: datetime) -> str:
    """Format date for display (dd.mm.yyyy)"""
    if isinstance(date, datetime):
        return date.strftime("%d.%m.%Y")
    return date.strftime("%d.%m.%Y")


def format_datetime(date: datetime) -> str:
    """Format datetime for display (dd.mm.yyyy HH:MM)"""
    return date.strftime("%d.%m.%Y %H:%M")


def format_display_id(number: int) -> str:
    """Format number as 3-digit display ID (001, 002, etc.)"""
    return f"{number:03d}"


def parse_display_id(display_id: str) -> int:
    """Parse 3-digit display ID back to integer"""
    try:
        return int(display_id)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid display ID format: {display_id}")


def format_group_name(display_id: str) -> str:
    """Format group name as 'spotify 001' pattern"""
    return f"spotify {display_id}"


def extract_group_display_id(group_name: str) -> str:
    """Extract display ID from group name like 'spotify 001' -> '001'"""
    if group_name.startswith("spotify "):
        return group_name[8:]  # Remove "spotify " prefix
    raise ValueError(f"Invalid group name format: {group_name}")


def calculate_days_until(target_date) -> int:
    """Calculate days until target date"""
    from datetime import datetime, date

    # Handle both datetime and date objects
    if isinstance(target_date, datetime):
        target_date = target_date.date()
    elif isinstance(target_date, date):
        pass  # Already a date object
    else:
        raise TypeError(
            f"Expected datetime or date object, got {type(target_date)}"
        )

    return (target_date - get_now().date()).days


def add_months_to_date(base_date: datetime, months: int, payment_day: int) -> datetime:
    """Add months to a date and set to specific payment day

    Args:
        base_date: Starting date
        months: Number of months to add
        payment_day: Day of month for payment (1-28)

    Returns:
        New datetime with added months on the payment day
    """
    # Calculate target month/year
    new_month = base_date.month + months
    new_year = base_date.year + (new_month - 1) // 12
    new_month = ((new_month - 1) % 12) + 1

    # Set to payment day (guaranteed 1-28, safe for all months)
    return base_date.replace(year=new_year, month=new_month, day=payment_day)


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
        'application/pdf',
        'application/x-pdf',
        'application/acrobat',
        'application/x-download',
        'application/octet-stream'
    ]

    if mime_type in allowed_types:
        return True

    return False
