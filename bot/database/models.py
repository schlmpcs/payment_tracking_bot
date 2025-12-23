"""
Database models and schema definitions
"""

from datetime import datetime
from typing import Optional, NamedTuple


class User(NamedTuple):
    """User model"""
    user_id: int
    username: str
    display_id: str  # 3-digit display ID like "001"
    first_name: Optional[str] = None
    created_at: Optional[datetime] = None


class Group(NamedTuple):
    """Payment group model"""
    group_id: int
    group_name: str
    display_id: str  # 3-digit display ID like "001"
    payment_day_of_month: int  # Day of month for payments (1-28)
    next_payment_date: datetime
    created_at: Optional[datetime] = None


class Payment(NamedTuple):
    """Payment record model"""
    payment_id: Optional[int]
    user_id: int
    group_id: int
    months_paid: int
    payment_date: datetime
    next_payment_date: datetime
    receipt_file_id: Optional[str] = None


class PaymentStatus(NamedTuple):
    """User payment status"""
    user_id: int
    user_display_id: str  # User's 3-digit display ID
    group_id: int
    group_name: str
    group_display_id: str  # Group's 3-digit display ID 
    next_payment_date: datetime
    last_payment_date: Optional[datetime]
    months_remaining: int
    is_overdue: bool


# SQL Schema
USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(100),
    display_id VARCHAR(3) UNIQUE NOT NULL,
    first_name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

GROUPS_TABLE = """
CREATE TABLE IF NOT EXISTS groups (
    group_id SERIAL PRIMARY KEY,
    group_name VARCHAR(100) UNIQUE NOT NULL,
    display_id VARCHAR(3) UNIQUE NOT NULL,
    payment_day_of_month INTEGER NOT NULL CHECK (payment_day_of_month BETWEEN 1 AND 28),
    next_payment_date TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

PAYMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS payments (
    payment_id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    group_id INTEGER NOT NULL,
    months_paid INTEGER NOT NULL DEFAULT 1,
    payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    next_payment_date TIMESTAMP NOT NULL,
    receipt_file_id VARCHAR(200),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE
);
"""

USER_GROUP_TABLE = """
CREATE TABLE IF NOT EXISTS user_groups (
    user_id BIGINT NOT NULL,
    group_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, group_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE
);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_payments_group_id ON payments(group_id);",
    "CREATE INDEX IF NOT EXISTS idx_payments_next_payment_date ON payments(next_payment_date);",
    "CREATE INDEX IF NOT EXISTS idx_user_groups_user_id ON user_groups(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_user_groups_group_id ON user_groups(group_id);",
    "CREATE INDEX IF NOT EXISTS idx_users_display_id ON users(display_id);",
    "CREATE INDEX IF NOT EXISTS idx_groups_display_id ON groups(display_id);"
]