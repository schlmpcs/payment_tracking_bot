"""Config tools.

This module allows to effectively conduct
configurations without data leakage
using Pydanctic library.

Attributes:
    HOME_DIR (str): a path to the app directory/
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic.types import SecretStr
from pydantic import Field
from typing import Optional

import os
from typing import List


HOME_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

class ConfigBase(BaseSettings):
    """Config base class.

    This class is used as preliminary settings
    for all config classes.

    Attributes:
        model_config (SettingsConfigDict): the model config.
    """

    model_config = SettingsConfigDict(
        env_file=os.path.join(HOME_DIR, 'settings', '.env'),
        env_file_encoding='utf-8',
        extra='ignore',
        case_sensitive=False,
    )


class TelegramConfig(ConfigBase):
    """Telegram config.

    Config class for Telegram specifically.

    Attributes:
        model_config (SettingsConfigDict): the model config.
        token (SecretStr): telegram token.
        admin_id (List[SecretStr]): telegram admin id.
    """

    model_config = SettingsConfigDict(env_prefix='TG_')

    token: SecretStr
    admin_id: List[SecretStr]


class DatabaseConfig(ConfigBase):
    """Database config.

    Config class for Database specific.

    Attributes:
        model_config (SettingsConfigDict): the model config.
        username (SecretStr): database username.
        password (SecretStr): database password.
        host (str): database host.
        port (int): database port (optional, defaults to 5432).
        database (str): database database.
    """

    model_config = SettingsConfigDict(env_prefix='DB_')

    username: SecretStr
    password: SecretStr
    host: str
    port: Optional[int] = None  # Optional port, will use default if not specified
    database: str


class Config(BaseSettings):
    """Config class.

    This class includes all config classes in one entity.

    Attributes:
        tg (TelegramConfig): telegram config.
        db (DatabaseConfig): database config.
    """

    tg: TelegramConfig = Field(default_factory=TelegramConfig)
    db: DatabaseConfig = Field(default_factory=DatabaseConfig)

    @classmethod
    def load(cls) -> 'Config':
        """Load config.

        Loads each config by () operation.

        Returns:
            'Config': loaded config.
        """

        return cls()
