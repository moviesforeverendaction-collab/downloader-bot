import os
import asyncio
from pyrogram import Client
from config import settings
from typing import Optional

# Initialize Pyrogram client (will be started/stopped per upload)
app = Client(
    "leech_bot",
    api_id=settings.API_ID,
    api_hash=settings.API_HASH,
    bot_token=settings.BOT_TOKEN
)

async def upload_to_telegram(filepath: str, progress_callback=None, cancel_flag: Optional[asyncio.Event] = None):
    """Upload a file to Telegram using Pyrogram.

    Args:
        filepath: Path to the local file.
        progress_callback: Optional coroutine called with (action, current, total).
        cancel_flag: Optional asyncio.Event that, when set, aborts the upload.

    Returns:
        The sent Message object.
    """

    async def pyrogram_progress(current, total):
        if cancel_flag and cancel_flag.is_set():
            raise asyncio.CancelledError("Upload cancelled by user")
        if progress_callback:
            await progress_callback("uploading", current, total)

    # Start the client explicitly
    await app.start()
    try:
        message = await app.send_document(
            chat_id=settings.OWNER_ID,
            document=filepath,
            progress=pyrogram_progress
        )
        return message
    finally:
        await app.stop()

def cleanup(filepath: str):
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        print(f"Cleanup error: {e}")
