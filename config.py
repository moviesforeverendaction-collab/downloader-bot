"""
Configuration management for TG Leecher Bot.
Uses Pydantic for validation and environment variable loading.
"""

import os
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


# Clean environment variables - remove empty strings
_KEYS = ["API_ID", "API_HASH", "BOT_TOKEN", "PORT", "DOWNLOAD_DIR", "OWNER_ID", "SELF_PING_URL"]
for _k in _KEYS:
    if _k in os.environ and not os.environ[_k].strip():
        os.environ.pop(_k, None)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Telegram API credentials
    API_ID: int = Field(default=0, description="Telegram API ID from my.telegram.org")
    API_HASH: str = Field(default="", description="Telegram API Hash from my.telegram.org")
    BOT_TOKEN: str = Field(default="", description="Bot token from @BotFather")
    
    # Bot settings - OWNER_ID is now optional (for notifications only, not access control)
    OWNER_ID: int = Field(default=0, description="Telegram user ID of bot owner (optional, for notifications)")
    
    # Web server settings
    SELF_PING_URL: str = Field(
        default="",
        description="URL to ping for keeping service alive (Render/Heroku)"
    )
    PORT: int = Field(default=8080, description="Port for web server")
    
    # Download settings
    DOWNLOAD_DIR: str = Field(default="/tmp/downloads", description="Directory for downloads")
    # 1.9 GB in bytes — safe margin below Telegram's 2 GB limit
    SPLIT_SIZE: int = Field(
        default=1900 * 1024 * 1024,
        description="Maximum file size before splitting"
    )
    
    @field_validator("DOWNLOAD_DIR")
    @classmethod
    def validate_download_dir(cls, v):
        """Ensure download directory exists and return absolute path."""
        # Convert to absolute path
        abs_path = os.path.abspath(v)
        os.makedirs(abs_path, exist_ok=True)
        return abs_path
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()

# Ensure download directory exists
os.makedirs(settings.DOWNLOAD_DIR, exist_ok=True)
