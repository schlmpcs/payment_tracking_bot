"""
Configuration settings for the Spotify Payment Bot
"""

from typing import List, Optional
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Simplified configuration - all settings in one class


class Settings(BaseSettings):
    """Main settings class"""

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'
    )

    # Telegram settings
    tg_token: SecretStr = Field(..., description="Telegram bot token")
    tg_admin_ids: List[int] = Field(
        ..., description="List of admin user IDs"
    )
    tg_receipt_storage_chat_id: Optional[int] = Field(
        None,
        description="Chat ID for storing receipt copies (audit trail)"
    )

    # Database settings
    db_host: str = Field(..., description="Database host")
    db_port: Optional[int] = Field(5432, description="Database port")
    db_username: SecretStr = Field(..., description="Database username")
    db_password: SecretStr = Field(..., description="Database password")
    db_database: str = Field(..., description="Database name")
    db_ssl_mode: str = Field(
        "require", description="SSL mode for connection"
    )

    # Bot settings
    bot_default_payment_price: float = Field(
        700, description="Default monthly payment amount"
    )
    bot_max_months_payment: int = Field(
        6, description="Maximum months that can be paid at once"
    )
    bot_payment_reminder_days: int = Field(
        3, description="Days before payment due to send reminder"
    )
    bot_timezone: str = Field(
        "UTC",
        description="Timezone for date/time operations (e.g., 'Asia/Almaty')"
    )
    bot_payment_link: str = Field(
        "https://pay.kaspi.kz/pay/besmk1m9",
        description="Payment link for Kaspi Bank or other payment system"
    )

    # Russia payment settings
    bot_ru_payment_price: float = Field(
        200, description="Monthly payment amount for Russia (in rubles)"
    )
    bot_ru_payment_card: str = Field(
        "", description="Card number for Russia payments"
    )
    bot_ru_payment_bank: str = Field(
        "VTB Bank", description="Bank name for Russia payments"
    )
    bot_ru_payment_recipient: str = Field(
        "", description="Recipient name for Russia card transfers"
    )

    @property
    def database_dsn(self) -> str:
        """Build database connection string"""
        dsn_parts = [
            f"host={self.db_host}",
            f"dbname={self.db_database}",
            f"user={self.db_username.get_secret_value()}",
            f"password={self.db_password.get_secret_value()}",
            f"sslmode={self.db_ssl_mode}"
        ]

        if self.db_port:
            dsn_parts.append(f"port={self.db_port}")

        return " ".join(dsn_parts)
