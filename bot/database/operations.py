"""
Database operations for the Spotify Payment Bot
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
import asyncpg
from asyncpg import Pool

# Database operations - settings passed from main
from .models import (
    User, Group, Payment, PaymentStatus,
    USERS_TABLE, GROUPS_TABLE, PAYMENTS_TABLE, USER_GROUP_TABLE, INDEXES
)


class Database:
    """Database operations manager"""
    
    def __init__(self, settings):
        self.settings = settings
        self.pool: Optional[Pool] = None
        self.logger = logging.getLogger(__name__)
    
    async def connect(self, retries: int = 3) -> bool:
        """Connect to the database with retry logic"""
        
        for attempt in range(retries):
            try:
                self.logger.info(f"🔄 Database connection attempt {attempt + 1}/{retries}")
                
                # Configure SSL for Koyeb
                import ssl
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                self.pool = await asyncpg.create_pool(
                    host=self.settings.db_host,
                    port=self.settings.db_port or 5432,
                    user=self.settings.db_username.get_secret_value(),
                    password=self.settings.db_password.get_secret_value(),
                    database=self.settings.db_database,
                    ssl=ssl_context,
                    min_size=1,
                    max_size=5,
                    command_timeout=60,
                    server_settings={
                        'application_name': 'spotify_payment_bot',
                    }
                )
                
                # Test connection
                async with self.pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                
                self.logger.info("✅ Database connected successfully!")
                return True
                
            except Exception as e:
                self.logger.error(f"❌ Database connection failed (attempt {attempt + 1}): {e}")
                
                if "does not exist" in str(e).lower():
                    self.logger.error("💡 Database does not exist. Please create it first.")
                    break
                    
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        return False
    
    async def close(self):
        """Close database connection"""
        if self.pool:
            await self.pool.close()
            self.logger.info("🔌 Database connection closed")
    
    async def initialize_tables(self) -> bool:
        """Initialize database tables"""
        if not self.pool:
            self.logger.error("No database connection available")
            return False
        
        try:
            async with self.pool.acquire() as conn:
                # Create tables
                await conn.execute(USERS_TABLE)
                await conn.execute(GROUPS_TABLE)
                await conn.execute(PAYMENTS_TABLE)
                await conn.execute(USER_GROUP_TABLE)
                
                # Create indexes
                for index_sql in INDEXES:
                    await conn.execute(index_sql)
                
                self.logger.info("✅ Database tables initialized successfully")
                return True
                
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize tables: {e}")
            return False
    
    # User operations
    async def add_user(self, user_id: int, username: str, first_name: Optional[str] = None) -> bool:
        """Add or update user"""
        if not self.pool:
            return False
        
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO users (user_id, username, first_name) 
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET username = $2, first_name = $3
                    """,
                    user_id, username, first_name
                )
                return True
        except Exception as e:
            self.logger.error(f"Failed to add user {user_id}: {e}")
            return False
    
    async def get_user(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        if not self.pool:
            return None
        
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT user_id, username, first_name, created_at FROM users WHERE user_id = $1",
                    user_id
                )
                return User(*row) if row else None
        except Exception as e:
            self.logger.error(f"Failed to get user {user_id}: {e}")
            return None
    
    # Group operations
    async def create_group(self, group_name: str, next_payment_date: datetime) -> Optional[int]:
        """Create a new payment group"""
        if not self.pool:
            return None
        
        try:
            async with self.pool.acquire() as conn:
                group_id = await conn.fetchval(
                    """
                    INSERT INTO groups (group_name, next_payment_date) 
                    VALUES ($1, $2) 
                    RETURNING group_id
                    """,
                    group_name, next_payment_date
                )
                self.logger.info(f"Created group '{group_name}' with ID {group_id}")
                return group_id
        except Exception as e:
            self.logger.error(f"Failed to create group '{group_name}': {e}")
            return None
    
    async def get_all_groups(self) -> List[Group]:
        """Get all payment groups"""
        if not self.pool:
            return []
        
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT group_id, group_name, next_payment_date, created_at FROM groups ORDER BY group_name"
                )
                return [Group(*row) for row in rows]
        except Exception as e:
            self.logger.error(f"Failed to get groups: {e}")
            return []
    
    async def get_group_by_name(self, group_name: str) -> Optional[Group]:
        """Get group by name"""
        if not self.pool:
            return None
        
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT group_id, group_name, next_payment_date, created_at FROM groups WHERE group_name = $1",
                    group_name
                )
                return Group(*row) if row else None
        except Exception as e:
            self.logger.error(f"Failed to get group '{group_name}': {e}")
            return None
    
    async def update_group_due_date(self, group_id: int, new_due_date: datetime) -> bool:
        """Update group's next payment due date"""
        if not self.pool:
            return False
        
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE groups 
                    SET next_payment_date = $1 
                    WHERE group_id = $2
                    """,
                    new_due_date.date(), group_id
                )
                
                # Check if any row was updated
                rows_affected = int(result.split()[-1])  # Extract number from "UPDATE 1"
                
                if rows_affected > 0:
                    self.logger.info(f"Updated due date for group {group_id} to {new_due_date.date()}")
                    return True
                else:
                    self.logger.warning(f"No group found with ID {group_id}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Failed to update due date for group {group_id}: {e}")
            return False
    
    async def get_groups_with_member_count(self) -> List[dict]:
        """Get all groups with member counts for user selection"""
        if not self.pool:
            return []
        
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT 
                        g.group_id,
                        g.group_name,
                        g.next_payment_date,
                        g.created_at,
                        COUNT(ug.user_id) as member_count
                    FROM groups g
                    LEFT JOIN user_groups ug ON g.group_id = ug.group_id
                    GROUP BY g.group_id, g.group_name, g.next_payment_date, g.created_at
                    ORDER BY g.group_name
                """)
                
                return [
                    {
                        'group_id': row['group_id'],
                        'group_name': row['group_name'],
                        'next_payment_date': row['next_payment_date'],
                        'created_at': row['created_at'],
                        'member_count': row['member_count']
                    }
                    for row in rows
                ]
        except Exception as e:
            self.logger.error(f"Failed to get groups with member count: {e}")
            return []
    
    # User-Group associations
    async def add_user_to_group(self, user_id: int, group_id: int) -> bool:
        """Add user to a payment group"""
        if not self.pool:
            return False
        
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO user_groups (user_id, group_id) 
                    VALUES ($1, $2) 
                    ON CONFLICT (user_id, group_id) DO NOTHING
                    """,
                    user_id, group_id
                )
                return True
        except Exception as e:
            self.logger.error(f"Failed to add user {user_id} to group {group_id}: {e}")
            return False
    
    async def get_user_group(self, user_id: int) -> Optional[Group]:
        """Get user's payment group"""
        if not self.pool:
            return None
        
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT g.group_id, g.group_name, g.next_payment_date, g.created_at
                    FROM groups g
                    JOIN user_groups ug ON g.group_id = ug.group_id
                    WHERE ug.user_id = $1
                    """,
                    user_id
                )
                return Group(*row) if row else None
        except Exception as e:
            self.logger.error(f"Failed to get user group for {user_id}: {e}")
            return None
    
    # Payment operations
    async def add_payment(self, user_id: int, group_id: int, months_paid: int, receipt_file_id: Optional[str] = None) -> bool:
        """Record a payment"""
        if not self.pool:
            return False
        
        try:
            async with self.pool.acquire() as conn:
                # Calculate next payment date
                current_payment_date = datetime.now()
                next_payment_date = current_payment_date + timedelta(days=30 * months_paid)
                
                await conn.execute(
                    """
                    INSERT INTO payments (user_id, group_id, months_paid, payment_date, next_payment_date, receipt_file_id)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    user_id, group_id, months_paid, current_payment_date, next_payment_date, receipt_file_id
                )
                
                self.logger.info(f"Payment recorded: User {user_id}, Group {group_id}, {months_paid} months")
                return True
        except Exception as e:
            self.logger.error(f"Failed to add payment for user {user_id}: {e}")
            return False
    
    async def get_user_payment_status(self, user_id: int) -> Optional[PaymentStatus]:
        """Get user's current payment status"""
        if not self.pool:
            return None
        
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT 
                        ug.user_id,
                        g.group_id,
                        g.group_name,
                        COALESCE(
                            (SELECT next_payment_date FROM payments 
                             WHERE user_id = ug.user_id AND group_id = g.group_id 
                             ORDER BY payment_date DESC LIMIT 1),
                            g.next_payment_date
                        ) as next_payment_date,
                        (SELECT payment_date FROM payments 
                         WHERE user_id = ug.user_id AND group_id = g.group_id 
                         ORDER BY payment_date DESC LIMIT 1) as last_payment_date
                    FROM user_groups ug
                    JOIN groups g ON ug.group_id = g.group_id
                    WHERE ug.user_id = $1
                    """,
                    user_id
                )
                
                if not row:
                    return None
                
                next_payment = row['next_payment_date']
                is_overdue = next_payment < datetime.now()
                
                # Calculate months remaining (rough estimate)
                days_diff = (next_payment - datetime.now()).days
                months_remaining = max(0, days_diff // 30)
                
                return PaymentStatus(
                    user_id=row['user_id'],
                    group_id=row['group_id'],
                    group_name=row['group_name'],
                    next_payment_date=next_payment,
                    last_payment_date=row['last_payment_date'],
                    months_remaining=months_remaining,
                    is_overdue=is_overdue
                )
                
        except Exception as e:
            self.logger.error(f"Failed to get payment status for user {user_id}: {e}")
            return None
    
    async def get_overdue_users(self) -> List[PaymentStatus]:
        """Get all users with overdue payments"""
        if not self.pool:
            return []
        
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT 
                        ug.user_id,
                        g.group_id,
                        g.group_name,
                        COALESCE(
                            (SELECT next_payment_date FROM payments 
                             WHERE user_id = ug.user_id AND group_id = g.group_id 
                             ORDER BY payment_date DESC LIMIT 1),
                            g.next_payment_date
                        ) as next_payment_date,
                        (SELECT payment_date FROM payments 
                         WHERE user_id = ug.user_id AND group_id = g.group_id 
                         ORDER BY payment_date DESC LIMIT 1) as last_payment_date
                    FROM user_groups ug
                    JOIN groups g ON ug.group_id = g.group_id
                    WHERE COALESCE(
                        (SELECT next_payment_date FROM payments 
                         WHERE user_id = ug.user_id AND group_id = g.group_id 
                         ORDER BY payment_date DESC LIMIT 1),
                        g.next_payment_date
                    ) < NOW()
                    ORDER BY next_payment_date
                    """
                )
                
                result = []
                for row in rows:
                    next_payment = row['next_payment_date']
                    days_diff = (next_payment - datetime.now()).days
                    months_remaining = max(0, days_diff // 30)
                    
                    result.append(PaymentStatus(
                        user_id=row['user_id'],
                        group_id=row['group_id'],
                        group_name=row['group_name'],
                        next_payment_date=next_payment,
                        last_payment_date=row['last_payment_date'],
                        months_remaining=months_remaining,
                        is_overdue=True
                    ))
                
                return result
                
        except Exception as e:
            self.logger.error(f"Failed to get overdue users: {e}")
            return []
    
    async def get_users_needing_reminders(self, days_before: int = 3) -> List[PaymentStatus]:
        """Get users who need payment reminders (X days before due date)"""
        if not self.pool:
            return []
        
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT 
                        ug.user_id,
                        g.group_id,
                        g.group_name,
                        COALESCE(
                            (SELECT next_payment_date FROM payments 
                             WHERE user_id = ug.user_id AND group_id = g.group_id 
                             ORDER BY payment_date DESC LIMIT 1),
                            g.next_payment_date
                        ) as next_payment_date,
                        (SELECT payment_date FROM payments 
                         WHERE user_id = ug.user_id AND group_id = g.group_id 
                         ORDER BY payment_date DESC LIMIT 1) as last_payment_date
                    FROM user_groups ug
                    JOIN groups g ON ug.group_id = g.group_id
                    WHERE COALESCE(
                        (SELECT next_payment_date FROM payments 
                         WHERE user_id = ug.user_id AND group_id = g.group_id 
                         ORDER BY payment_date DESC LIMIT 1),
                        g.next_payment_date
                    ) = CURRENT_DATE + INTERVAL '%s day'
                    ORDER BY next_payment_date
                    """ % days_before
                )
                
                result = []
                for row in rows:
                    next_payment = row['next_payment_date']
                    days_diff = (next_payment - datetime.now().date()).days
                    months_remaining = max(0, days_diff // 30)
                    
                    result.append(PaymentStatus(
                        user_id=row['user_id'],
                        group_id=row['group_id'],
                        group_name=row['group_name'],
                        next_payment_date=next_payment,
                        last_payment_date=row['last_payment_date'],
                        months_remaining=months_remaining,
                        is_overdue=False
                    ))
                
                return result
                
        except Exception as e:
            self.logger.error(f"Failed to get users needing reminders: {e}")
            return []
    
    async def get_users_overdue_for_admin_warning(self, days_after: int = 3) -> List[PaymentStatus]:
        """Get users who are overdue for X days (for admin warnings)"""
        if not self.pool:
            return []
        
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT 
                        ug.user_id,
                        u.username,
                        u.first_name,
                        g.group_id,
                        g.group_name,
                        COALESCE(
                            (SELECT next_payment_date FROM payments 
                             WHERE user_id = ug.user_id AND group_id = g.group_id 
                             ORDER BY payment_date DESC LIMIT 1),
                            g.next_payment_date
                        ) as next_payment_date,
                        (SELECT payment_date FROM payments 
                         WHERE user_id = ug.user_id AND group_id = g.group_id 
                         ORDER BY payment_date DESC LIMIT 1) as last_payment_date
                    FROM user_groups ug
                    JOIN groups g ON ug.group_id = g.group_id
                    JOIN users u ON ug.user_id = u.user_id
                    WHERE COALESCE(
                        (SELECT next_payment_date FROM payments 
                         WHERE user_id = ug.user_id AND group_id = g.group_id 
                         ORDER BY payment_date DESC LIMIT 1),
                        g.next_payment_date
                    ) = CURRENT_DATE - INTERVAL '%s day'
                    ORDER BY next_payment_date
                    """ % days_after
                )
                
                result = []
                for row in rows:
                    next_payment = row['next_payment_date']
                    days_diff = (datetime.now().date() - next_payment).days
                    
                    # Create extended PaymentStatus with user info for admin warnings
                    status = PaymentStatus(
                        user_id=row['user_id'],
                        group_id=row['group_id'],
                        group_name=row['group_name'],
                        next_payment_date=next_payment,
                        last_payment_date=row['last_payment_date'],
                        months_remaining=0,
                        is_overdue=True
                    )
                    # Add user info as attributes
                    status.username = row['username']
                    status.first_name = row['first_name']
                    status.days_overdue = days_diff
                    
                    result.append(status)
                
                return result
                
        except Exception as e:
            self.logger.error(f"Failed to get users overdue for admin warning: {e}")
            return []
    
    async def is_user_registered(self, user_id: int) -> bool:
        """Check if user is registered in any group"""
        if not self.pool:
            return False
        
        try:
            async with self.pool.acquire() as conn:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM user_groups WHERE user_id = $1",
                    user_id
                )
                return count > 0
        except Exception as e:
            self.logger.error(f"Failed to check user registration for {user_id}: {e}")
            return False