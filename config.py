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


def _get_absolute_download_dir() -> str:
    """Get absolute path for download directory, suitable for Render/container environments."""
    raw_dir = os.environ.get("DOWNLOAD_DIR", "").strip()
    
    if not raw_dir:
        raw_dir = "./downloads"
    
    # Always convert to absolute path
    abs_dir = os.path.abspath(raw_dir)
    
    return abs_dir


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Telegram API credentials
    API_ID: int = Field(default=0, description="Telegram API ID from my.telegram.org")
    API_HASH: str = Field(default="", description="Telegram API Hash from my.telegram.org")
    BOT_TOKEN: str = Field(default="", description="Bot token from @BotFather")
    
    # Bot settings
    OWNER_ID: int = Field(default=0, description="Telegram user ID of bot owner")
    
    # Web server settings
    SELF_PING_URL: str = Field(
        default="",
        description="URL to ping for keeping service alive (Render/Heroku)"
    )
    PORT: int = Field(default=8080, description="Port for web server")
    
    # Download settings - use absolute path
    DOWNLOAD_DIR: str = Field(
        default_factory=_get_absolute_download_dir,
        description="Directory for downloads (always absolute path)"
    )
    # 1.9 GB in bytes — safe margin below Telegram's 2 GB limit
    SPLIT_SIZE: int = Field(
        default=1900 * 1024 * 1024,
        description="Maximum file size before splitting"
    )
    
    @field_validator("DOWNLOAD_DIR", mode="before")
    @classmethod
    def validate_download_dir(cls, v):
        """Ensure download directory is absolute and exists."""
        if not v:
            v = "./downloads"
        # Always convert to absolute path
        abs_dir = os.path.abspath(str(v))
        os.makedirs(abs_dir, exist_ok=True)
        return abs_dir
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()

# Ensure download directory exists with absolute path
os.makedirs(settings.DOWNLOAD_DIR, exist_ok=True)
print(f"[config] Download directory: {settings.DOWNLOAD_DIR}")
