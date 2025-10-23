import aiopg
import asyncio
import sys
from datetime import datetime

import psycopg2
from dateutil.relativedelta import relativedelta
from typing import List, Tuple

from app.config import DatabaseConfig
from app.tools.functions import ErrorLogger

# Fix for Windows + aiopg
if sys.platform.startswith('win'):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logger = ErrorLogger()


class Database:

    def __init__(self):
        cfg = DatabaseConfig()
        # Build connection string
        dsn_parts = [
            f"dbname={cfg.database}",
            f"user={cfg.username.get_secret_value()}",
            f"password={cfg.password.get_secret_value()}",
            f"host={cfg.host}",
            "sslmode=require"  # Required for cloud databases like Koyeb
        ]
        
        # Only add port if it's explicitly specified in environment
        if cfg.port is not None:
            dsn_parts.append(f"port={cfg.port}")
            
        self.dsn = " ".join(dsn_parts)
        self.pool = None

    def __del__(self):
        # Note: close() is async, so we can't call it in __del__
        # The pool will be cleaned up automatically
        pass

    async def connect(self, retries: int = 3) -> bool:
        """
        Connect to database with retry logic
        :param retries: number of retry attempts
        :return: whether database connection was successful
        """
        for attempt in range(retries):
            try:
                print(f"🔄 Database connection attempt {attempt + 1}/{retries}...")
                self.pool = await aiopg.create_pool(self.dsn, timeout=30, minsize=1, maxsize=10)
                logger.logger.info("Database connection pool created successfully")
                print("✅ Database connected successfully!")
                return True
                
            except psycopg2.OperationalError as e:
                error_msg = str(e)
                logger.logger.error(f"Database connection failed (attempt {attempt + 1}): {error_msg}")
                
                if "database" in error_msg and "does not exist" in error_msg:
                    print(f"❌ Database 'spotify-payments' does not exist on the server")
                    print("💡 You may need to create the database first or use a different name")
                    break
                elif "sslmode=require" in error_msg or "SSL" in error_msg:
                    print(f"❌ SSL connection issue: {error_msg}")
                    break
                else:
                    print(f"❌ Connection failed (attempt {attempt + 1}): {error_msg}")
                    
            except asyncio.TimeoutError:
                logger.logger.error(f"Connection attempt {attempt + 1} timed out")
                print(f"❌ Connection timed out (attempt {attempt + 1})")
                
            except Exception as e:
                logger.logger.error(f"Connection error (attempt {attempt + 1}): {e}")
                print(f"❌ Unexpected error (attempt {attempt + 1}): {e}")
            
            if attempt < retries - 1:
                await asyncio.sleep(2)  # Wait 2 seconds between retries
                
        return self.pool is not None

    async def close(self) -> bool:
        """
        Close database connection
        :return: whether connection is closed
        """
        if self.pool:
            try:
                self.pool.close()
                await self.pool.wait_closed()
            except Exception as e:
                logger.logger.error("ON CONNECTION CLOSE: %s", e)
            return True

    async def initialize(self) -> bool:
        """
        Initialize tables in Database
        :return: True if tables were successfully initialized
        :throw:
            Exception: Database connection failed.
        """
        if not self.pool:
            raise AttributeError("Database connection pool is empty")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    # Groups table
                    await cursor.execute(
                        '''
                        CREATE TABLE IF NOT EXISTS groups (
                        group_id INTEGER PRIMARY KEY,
                        group_name VARCHAR(100) UNIQUE,
                        payment_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
                        '''
                    )

                    # Users table with relation to groups
                    await cursor.execute(
                        '''
                        CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username VARCHAR(100) UNIQUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
                        '''
                    )

                    # Payments table
                    await cursor.execute(
                        '''
                        CREATE TABLE IF NOT EXISTS payments (
                        group_id INT NOT NULL,
                        user_id INT UNIQUE NOT NULL,
                        payment_at TIMESTAMP NOT NULL,
                        paid_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (group_id, user_id),
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                        FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE);
                        '''
                    )
                    return True
                except Exception as e:
                    logger.logger.error("ON TABLE INITALIZATION: %s", e)
                    return False

    async def add_user(self, user_id: int, username: str) -> bool:
        """
        Add user to database
        :param user_id: a unique id of the user
        :param username: the username of the user
        :return: whether the user was added successfully (T/F)
        :throw:
            Exception: Database connection failed.
        """

        if not self.pool:
            raise AttributeError("Database connection pool is empty")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(
                        "INSERT INTO users (user_id, username) VALUES (%s, %s);",
                        (user_id, username.replace('@', ''))
                    )
                except Exception as e:
                    logger.logger.error("ON USER ADD: %s", e)
                return cursor.rowcount > 0

    async def get_user_by_id(self, user_id: int) -> Tuple[int, str]:
        """
        Get user from database table by ID
        :param user_id: a unique id of the user
        :return: (userID, username) tuple
        :throw:
            Exception: Database connection failed.
        """
        if not self.pool:
            raise AttributeError("Database connection pool is empty")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(
                        "SELECT user_id, username FROM users WHERE user_id = %s",
                        (user_id,)
                    )
                    return await cursor.fetchone()
                except Exception as e:
                    logger.logger.error("ON USER GET BY ID: %s", e)

    async def get_user_by_name(self, username: str) -> Tuple[int, str]:
        """
        Get user from database table by username
        :param username: username of the user
        :return: (userID, username) tuple
        :throw:
            Exception: Database connection failed.
        """

        if not self.pool:
            raise AttributeError("Database connection pool is empty")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(
                        "SELECT user_id, username FROM users WHERE username = %s",
                        (username.replace('@', ''),)
                    )
                    return await cursor.fetchone()
                except Exception as e:
                    logger.logger.error("ON USER GET BY USERNAME: %s", e)

    async def update_username(self, user_id: int, new_username: str) -> bool:
        """
        Update username in database table
        :param user_id: a unique id of the user
        :param new_username: the new username
        :return: whether the username was updated successfully (T/F)
        :throw:
            Exception: Database connection failed.
        """

        if not self.pool:
            raise AttributeError("Database connection pool is empty")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(
                        "UPDATE users SET username = %s WHERE user_id = %s",
                        (new_username.replace('@', ''), user_id)
                    )
                except Exception as e:
                    logger.logger.error("ON USERNAME UPDATE BY ID: %s", e)
                return cursor.rowcount > 0

    async def add_group(self, group_id: int, group_name: str, payment_at: datetime) -> bool:
        """
        Add group to database
        :param group_id: a unique id of the group
        :param group_name: a unique group name
        :param payment_at: a payment date
        :return: whether the group was added successfully (T/F)
        :throw:
            Exception: Database connection failed.
            Exception: Group already exists.
        """

        if not self.pool:
            raise AttributeError("Database connection pool is empty")
        try:
            if payment_at < datetime.now():
                delta = relativedelta(payment_at, datetime.now())
                total_months = delta.years * 12 + delta.months + 1
                payment_at += relativedelta(months=total_months)
        except Exception as e:
            logger.logger.error("ON GROUP ADD: %s", e)
            return False

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(
                        """
                        INSERT INTO groups (group_id, group_name, payment_at)
                        VALUES (%s, LOWER(%s), %s)
                        """,
                        (group_id, group_name, payment_at)
                    )
                except Exception as e:
                    logger.logger.error("ON GROUP ADD: %s", e)
                return cursor.rowcount > 0

    async def get_all_groups(self) -> List[Tuple[int, str, datetime, datetime]]:
        """Get all groups from Database table groups

        Returns:
            List of (group_id, group_name, payment_at, created_at) tuples
        Errors:
            Exception: Database connection failed.
        """

        if not self.pool:
            raise AttributeError("Database connection pool is empty")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(
                        "SELECT * FROM groups",
                    )
                    return await cursor.fetchall()
                except Exception as e:
                    logger.logger.error("ON GROUP GET: %s", e)

    async def get_group_by_id(self, group_id: int) -> Tuple[int, str, datetime, datetime]:
        """
        Get group from database table
        :param group_id: id of the group
        :return: (group_id, group_name, payment_at, created_at) tuple
        :throw:
            Exception: Database connection failed.
        """

        if not self.pool:
            raise AttributeError("Database connection pool is empty")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(
                        """
                        SELECT group_id, group_name, payment_at, created_at
                        FROM groups WHERE group_id = %s
                        """,
                        (group_id,)
                    )
                    return await cursor.fetchone()
                except Exception as e:
                    logger.logger.error("ON GROUP GET: %s", e)

    async def get_group_by_name(self, group_name: str) -> Tuple[int, str, datetime, datetime]:
        """
        Get group from database table by name
        :param group_name: name of the group
        :return: (group_id, group_name, payment_at, created_at) tuple
        :throw:
            Exception: Database connection failed.
        """

        if not self.pool:
            raise AttributeError("Database connection pool is empty")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(
                        """
                        SELECT group_id, group_name, payment_at, created_at
                        FROM groups WHERE group_name = LOWER(%s)
                        """,
                        (group_name,)
                    )
                    return await cursor.fetchone()
                except Exception as e:
                    logger.logger.error("ON GROUP GET BY NAME: %s", e)

    async def update_group_name(self, group_id: int, new_group_name: str) -> bool:
        """
        Update group name in database table
        :param group_id: a unique id of the group
        :param new_group_name: the new group name
        :return: whether the group name was updated successfully (T/F)
        :throw:
            Exception: Database connection failed.
        """
        if not self.pool:
            raise Exception("Database connection pool is empty")

        if isinstance(new_group_name, str) or len(new_group_name) == 0:
            logger.logger.error("ON GROUP NAME UPDATE BY ID: %s", new_group_name + " is empty or not a string")
            return False

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(
                        """
                        UPDATE groups SET group_name = LOWER(%s)
                        WHERE group_id = %s
                        """,
                        (new_group_name, group_id)
                    )
                except Exception as e:
                    logger.logger.error("ON GROUP NAME UPDATE BY ID: %s", e)
                return cursor.rowcount > 0

    async def add_payments(self, user_id: int, group_id: int, payment_at: datetime) -> bool:
        """
        Add User-group relation in the table
        :param user_id: user id
        :param group_id: group id
        :param payment_at: payment date
        :return: whether the relation was added successfully (T/F)
        :throw:
            Exception: Database connection failed.
        """

        if not self.pool:
            raise AttributeError("Database connection pool is empty")
        try:
            if payment_at < datetime.now():
                delta = relativedelta(payment_at, datetime.now())
                total_months = delta.years * 12 + delta.months + 1
                payment_at += relativedelta(months=total_months)
        except Exception as e:
            logger.logger.error("ON PAYMENT RELATION ADD: %s", e)
            return False

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(
                        """
                        INSERT INTO payments (user_id, group_id, payment_at)
                        VALUES (%s, %s, %s)
                        """,
                        (user_id, group_id, payment_at)
                    )
                except Exception as e:
                    logger.logger.error("ON PAYMENTS RELATION ADD: %s", e)
                return cursor.rowcount > 0

    async def get_user_group(self, user_id: int) -> int:
        """
        Get user's group from the table
        :param user_id:
        :return: Group id
        :throw:
            Exception: Database connection failed.
        """

        if not self.pool:
            raise AttributeError("Database connection pool is empty")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(
                        "SELECT group_id FROM payments WHERE user_id = %s",
                        (user_id,)
                    )
                    return await cursor.fetchone()
                except Exception as e:
                    logger.logger.error("ON USER'S GROUP GET: %s", e)

    async def get_group_users(self, group_id: int) -> List[int]:
        """
        Get group's users from the table
        :param group_id:
        :return: User id
        :throw:
            Exception: Database connection failed.
        """

        if not self.pool:
            raise AttributeError("Database connection pool is empty")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(
                        "SELECT user_id FROM payments WHERE group_id = %s",
                        (group_id,)
                    )
                    return await cursor.fetchall()
                except Exception as e:
                    logger.logger.error("ON GROUP USERS GET: %s", e)

    async def check_payments(self) -> List[Tuple[int, int, int]]:
        """
        Check whether the users paid
        :return: List[Tuple[int, int, int, bool]]: (groupID, userID, days until payment)
        :throw:
            Exception: Database connection failed.
        """

        if not self.pool:
            raise AttributeError("Database connection pool is empty")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(
                        """
                        SELECT group_id, user_id,
                        TIMESTAMPDIFF(DAY, payment_at, CURRENT_TIMESTAMP) as diff,
                        FROM groups
                        WHERE diff >= 0
                        """,
                    )
                    return await cursor.fetchall()
                except Exception as e:
                    logger.logger.error("ON CHECK PAYMENT: %s", e)

    async def mark_payment(self, user_id: int, month_paid: int) -> bool:
        """
        Add user payment into database table
        :param user_id: a unique id of the user
        :param month_paid: how many month in advance he paid
        :return: whether the user was added successfully (T/F)
        """

        if not self.pool:
            raise AttributeError("Database connection pool is empty")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    now = datetime.now().isoformat()
                    await cursor.execute(
                        """
                        UPDATE payments
                        SET payment_at = payment_at + (%s || ' months')::INTERVAL,
                            paid_on = %s
                        WHERE user_id = %s
                        """,
                        (month_paid, now, user_id)
                    )
                except Exception as e:
                    logger.logger.error("ON MARK PAYMENT: %s", e)
                return cursor.rowcount > 0

    async def get_unpaid_group(self) -> List[Tuple[str, str, datetime, bool, int]]:
        """Get statistic of payments per group that did not fully pay.

        Returns
            List[Tuple[str, str, datetime, bool, int]]:
                list of (group_name, username, next payment date, is paid, how many days later)

        Raises:
            Exception: Database connection failed.
        """
        if not self.pool:

            raise AttributeError("Database connection pool is empty")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(
                        """
                        SELECT group_name, username, payment_at, paid, diff
                        FROM (
                            SELECT 
                            g.group_name as group_name,
                            sub.username as username,
                            sub.payment_at as payment_at,
                            sub.diff < 0 as paid,
                            sub.diff as diff,
                            MAX(sub.diff) OVER (PARTITION BY sub.group_id) as max_diff_value
                            FROM groups g INNER JOIN
                            (
                                SELECT p.group_id, u.username, p.payment_at,
                                EXTRACT(DAY FROM CURRENT_DATE - p.payment_at) as diff
                                FROM payments p
                                INNER JOIN users u
                                ON p.user_id = u.user_id
                            ) as sub
                            ON g.group_id = sub.group_id
                        ) as sup
                        WHERE sup.max_diff_value >= 0
                        """,
                    )
                    return await cursor.fetchall()
                except Exception as e:
                    logger.logger.error("ON GROUP STATISTIC GET: %s", e)

    async def delete_user(self, username: str) -> bool:
        """Delete user from database table by username.

        Args:
            username (str): an username of the user.

        Returns:
            whether the user was deleted successfully (T/F).
        """

        if not self.pool:
            raise AttributeError("Database connection pool is empty")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(
                        "DELETE FROM users WHERE username = %s",
                        (username.replace('@', ''),)
                    )
                except Exception as e:
                    logger.logger.error("ON DELETE FROM USERS: %s", e)
                return cursor.rowcount > 0

    async def delete_group(self, group_name: str) -> bool:
        """Delete group from database table by group name.

        Args:
            group_name: name of the group.
        Returns:
            whether the group was deleted successfully (T/F).
        """

        if not self.pool:
            raise AttributeError("Database connection pool is empty")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(
                        "DELETE FROM groups WHERE group_name = LOWER(%s)",
                        (group_name,)
                    )
                except Exception as e:
                    logger.logger.error("ON DELETE FROM GROUPS: %s", e)
                return cursor.rowcount > 0

    async def drop_tables(self) -> bool:
        """
        Drop all tables for debug purposes
        :return: whether tables were dropped
        :throw:
            Exception: Database connection failed.
        """

        if not self.pool:
            raise AttributeError("Database connection pool is empty")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute("DROP TABLE IF EXISTS users CASCADE")
                    await cursor.execute("DROP TABLE IF EXISTS groups CASCADE")
                    await cursor.execute("DROP TABLE IF EXISTS payments")
                    return True
                except Exception as e:
                    logger.logger.error("ON DROP TABLE ERROR: %s", e)
                    return False

    async def get_user_payment_info(self, user_id: int) -> Tuple[int, str, datetime, datetime] | None:
        """
        Get user's payment information including group details
        :param user_id: a unique id of the user
        :return: (group_id, group_name, next_payment_date, last_paid) tuple or None if not found
        """
        if not self.pool:
            raise AttributeError("Database connection pool is empty")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(
                        """
                        SELECT p.group_id, g.group_name, p.payment_at, p.paid_on
                        FROM payments p
                        JOIN groups g ON p.group_id = g.group_id
                        WHERE p.user_id = %s
                        """,
                        (user_id,)
                    )
                    result = await cursor.fetchone()
                    return result if result else None
                except Exception as e:
                    logger.logger.error("ON GET USER PAYMENT INFO: %s", e)
                    return None

    async def is_user_registered(self, user_id: int) -> bool:
        """
        Check if user exists in the system and has a group assigned
        :param user_id: a unique id of the user
        :return: True if user exists and has a group, False otherwise
        """
        if not self.pool:
            raise AttributeError("Database connection pool is empty")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(
                        """
                        SELECT 1 FROM payments WHERE user_id = %s
                        """,
                        (user_id,)
                    )
                    result = await cursor.fetchone()
                    return result is not None
                except Exception as e:
                    logger.logger.error("ON CHECK USER REGISTRATION: %s", e)
                    return False
