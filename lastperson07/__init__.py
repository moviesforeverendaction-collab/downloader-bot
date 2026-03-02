"""
lastperson07 - Core modules for TG Leecher Bot.
"""

from .aria2_client import add_download, monitor_download, aria2_rpc, get_download_status
from .settings_db import (
    get_dump_channel, set_dump_channel,
    get_custom_caption, set_custom_caption,
    get_custom_thumb, set_custom_thumb
)
from .split_utils import split_large_file, get_part_info

__all__ = [
    "add_download",
    "monitor_download",
    "aria2_rpc",
    "get_download_status",
    "get_dump_channel",
    "set_dump_channel",
    "get_custom_caption",
    "set_custom_caption",
    "get_custom_thumb",
    "set_custom_thumb",
    "split_large_file",
    "get_part_info",
]
