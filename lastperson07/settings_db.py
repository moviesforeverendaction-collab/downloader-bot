"""
Settings Database - JSON-based user settings storage.
"""

import json
import os
from config import settings

DB_FILE = os.path.join(settings.DOWNLOAD_DIR, "user_settings.json")

# In-memory cache
_user_settings: dict = {}
_db_loaded = False


def _ensure_loaded():
    """Ensure database is loaded into memory."""
    global _db_loaded, _user_settings
    if _db_loaded:
        return
    load_db()
    _db_loaded = True


def load_db() -> None:
    """Load settings from JSON file."""
    global _user_settings
    
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    _user_settings = json.loads(content)
                else:
                    _user_settings = {}
            print(f"[settings] Loaded {len(_user_settings)} user settings")
        except json.JSONDecodeError as e:
            print(f"[settings] JSON decode error: {e}")
            _user_settings = {}
        except Exception as e:
            print(f"[settings] Load error: {e}")
            _user_settings = {}
    else:
        _user_settings = {}


def save_db() -> None:
    """Save settings to JSON file."""
    try:
        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(_user_settings, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[settings] Save error: {e}")


def get_user_setting(user_id: int, key: str, default=None):
    """Get a setting value for a user."""
    _ensure_loaded()
    user_id_str = str(user_id)
    if user_id_str in _user_settings:
        return _user_settings[user_id_str].get(key, default)
    return default


def set_user_setting(user_id: int, key: str, value) -> None:
    """Set a setting value for a user."""
    _ensure_loaded()
    user_id_str = str(user_id)
    if user_id_str not in _user_settings:
        _user_settings[user_id_str] = {}
    _user_settings[user_id_str][key] = value
    save_db()


def get_dump_channel(user_id: int):
    """Get user's dump channel."""
    return get_user_setting(user_id, "dump_channel")


def set_dump_channel(user_id: int, channel_id: int) -> None:
    """Set user's dump channel."""
    set_user_setting(user_id, "dump_channel", channel_id)


def get_custom_caption(user_id: int):
    """Get user's custom caption."""
    return get_user_setting(user_id, "custom_caption")


def set_custom_caption(user_id: int, caption: str) -> None:
    """Set user's custom caption."""
    set_user_setting(user_id, "custom_caption", caption)


def get_custom_thumb(user_id: int):
    """Get user's custom thumbnail."""
    return get_user_setting(user_id, "custom_thumb")


def set_custom_thumb(user_id: int, thumb_file_id: str) -> None:
    """Set user's custom thumbnail."""
    set_user_setting(user_id, "custom_thumb", thumb_file_id)


# Ensure download dir exists on import
os.makedirs(settings.DOWNLOAD_DIR, exist_ok=True)
