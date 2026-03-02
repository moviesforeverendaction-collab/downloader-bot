"""
Telegram Leech Bot - Aria2 Powered
===================================
Downloads files from URLs/magnets/torrents and uploads to Telegram.
"""

import os
import json
import time
import asyncio
import random
import subprocess

from aiohttp import web
from pyrogram import Client, filters, idle, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from config import settings
from utils import format_progress, format_bytes

from lastperson07.settings_db import (
    get_dump_channel, set_dump_channel,
    get_custom_caption, set_custom_caption,
    get_custom_thumb, set_custom_thumb,
    get_user_telegram_id, set_user_telegram_id,
    get_web_upload_target
)
from lastperson07.aria2_client import add_download, monitor_download, aria2_rpc
from lastperson07.split_utils import split_large_file

# ---------------------------------------------------------------------------
# Pyrogram Bot Client
# ---------------------------------------------------------------------------
app = Client(
    "leech_bot",
    api_id=settings.API_ID,
    api_hash=settings.API_HASH,
    bot_token=settings.BOT_TOKEN,
)

# Anti-flood: track last edit time per message id
_last_edit_time: dict[int, float] = {}
FLOOD_COOLDOWN = 3.0

# Active downloads: maps message_id → {"gid": str, "cancelled": bool}
_active_downloads: dict[int, dict] = {}


def _cancel_keyboard(msg_id: int) -> InlineKeyboardMarkup:
    """Generate cancel button keyboard for a message."""
    return InlineKeyboardMarkup([[InlineKeyboardButton(
        "❌ Cancel Download", callback_data=f"cancel:{msg_id}"
    )]])


async def safe_edit(msg: Message, text: str, reply_markup=None) -> None:
    """Edit a message with flood protection (once per FLOOD_COOLDOWN seconds)."""
    now = time.time()
    msg_id = msg.id
    if now - _last_edit_time.get(msg_id, 0) < FLOOD_COOLDOWN:
        return
    try:
        await msg.edit_text(
            text,
            parse_mode=enums.ParseMode.MARKDOWN,
            reply_markup=reply_markup,
        )
        _last_edit_time[msg_id] = time.time()
    except Exception as e:
        print(f"[safe_edit] Failed to edit message {msg_id}: {e}")


# ---------------------------------------------------------------------------
# Boot up Aria2 Daemon
# ---------------------------------------------------------------------------
def start_aria2_daemon() -> None:
    """Start aria2c daemon with MAX SPEED settings for Heroku."""
    print("[aria2] Starting daemon with MAX SPEED settings...")
    # Ensure download directory exists with absolute path
    download_dir = os.path.abspath(settings.DOWNLOAD_DIR)
    os.makedirs(download_dir, exist_ok=True)
    print(f"[aria2] Download directory: {download_dir}")

    try:
        subprocess.Popen([
            "aria2c",
            "--enable-rpc",
            "--rpc-listen-all=false",
            "--rpc-listen-port=6800",
            "--daemon=true",
            f"--dir={download_dir}",
            # MAX SPEED SETTINGS - No limits
            "--max-overall-download-limit=0",
            "--max-overall-upload-limit=0",
            "--max-download-limit=0",
            "--max-upload-limit=0",
            # MAX CONNECTIONS for speed
            "--max-connection-per-server=32",
            "--split=32",
            "--min-split-size=1M",
            "--max-concurrent-downloads=10",
            # Performance optimizations
            "--disable-ipv6=true",
            "--disk-cache=256M",
            "--file-allocation=none",
            "--optimize-concurrent-downloads=true",
            # Connection reliability
            "--timeout=300",
            "--max-tries=20",
            "--retry-wait=3",
            "--connect-timeout=60",
            "--max-file-not-found=10",
            # BitTorrent optimizations
            "--seed-time=0",
            "--bt-stop-timeout=300",
            "--bt-max-peers=200",
            "--bt-request-peer-speed-limit=0",
            "--bt-hash-check-seed=false",
            "--bt-seed-unverified=false",
            "--bt-save-metadata=true",
            "--dht-listen-port=6881-6999",
            "--enable-dht=true",
            "--enable-dht6=false",
            "--enable-peer-exchange=true",
            # HTTP/FTP optimizations
            "--http-accept-gzip=true",
            "--http-no-cache=true",
            "--reuse-uri=true",
            # Logging
            "--console-log-level=warn",
            "--summary-interval=0",
            "--download-result=hide"
        ])
        time.sleep(3)
        print("[aria2] Daemon started successfully with MAX SPEED settings")
    except Exception as e:
        print(f"[aria2] Failed to start daemon: {e}")


# ---------------------------------------------------------------------------
# Bot Commands
# ---------------------------------------------------------------------------
@app.on_callback_query(filters.regex(r"^cancel:(\d+)$"))
async def cancel_callback(client: Client, callback_query: CallbackQuery) -> None:
    """Handle cancel button click."""
    msg_id = int(callback_query.matches[0].group(1))
    entry = _active_downloads.get(msg_id)
    
    if not entry:
        await callback_query.answer("Download already finished or cancelled.", show_alert=True)
        return

    entry["cancelled"] = True
    gid = entry.get("gid")
    
    if gid:
        await aria2_rpc("aria2.forceRemove", [gid])

    await callback_query.answer("🚫 Cancelling download...")
    try:
        await callback_query.message.edit_text(
            "🚫 **Download cancelled by user.**",
            parse_mode=enums.ParseMode.MARKDOWN,
        )
    except Exception:
        pass


@app.on_message(filters.command("start"))
async def start_handler(client: Client, message: Message) -> None:
    """Handle /start command."""
    user_id = message.from_user.id
    welcome_text = (
        "🚀 **TG Leecher Bot (Aria2 Powered)**\n\n"
        "Send me any downloadable link, magnet link, or upload a **.torrent** file!\n\n"
        "**✨ Features:**\n"
        "• Direct links, magnets, torrent files support\n"
        "• Auto-splits files **> 1.9 GB** natively\n"
        "• 🚀 **MAX SPEED** download & upload\n"
        "• Real-time progress tracking\n\n"
        "**🔧 Commands:**\n"
        "`/status` - Check bot status & disk space\n"
        "`/cancel` - Cancel active download\n"
        "`/setid <telegram_id>` - Set your Telegram ID for web uploads\n"
        "`/setdump <channel_id>` - Set dump channel\n"
        "`/setcaption <text>` - Set custom caption\n"
        "`/setthumb` (reply to image) - Set thumbnail\n"
        "`/help` - Show detailed help"
    )
    await message.reply_text(welcome_text, parse_mode=enums.ParseMode.MARKDOWN)


@app.on_message(filters.command("help"))
async def help_handler(client: Client, message: Message) -> None:
    """Handle /help command."""
    help_text = (
        "**📖 How to Use:**\n\n"
        "1️⃣ **Send a link:** Paste any direct URL or magnet link\n"
        "2️⃣ **Upload torrent:** Send a `.torrent` file directly\n"
        "3️⃣ **Monitor progress:** Watch real-time download/upload progress\n"
        "4️⃣ **Cancel:** Use `/cancel` or click the cancel button\n\n"
        "**🔧 Available Commands:**\n"
        "• `/start` - Show welcome message\n"
        "• `/status` - Check bot status and disk space\n"
        "• `/cancel` - Cancel your active download\n"
        "• `/setid <telegram_id>` - Set your Telegram ID for web uploads\n"
        "• `/setdump <channel_id>` - Set channel for auto-uploads\n"
        "• `/setcaption <text>` - Add custom caption to uploads\n"
        "• `/setthumb` (reply to image) - Set thumbnail\n"
        "• `/help` - Show this help message\n\n"
        "**💡 Tips:**\n"
        "• Files larger than 1.9GB are automatically split\n"
        "• Use the Web UI for a visual experience\n"
        "• Set a dump channel to auto-upload files there\n"
        "• 🚀 MAX SPEED optimized for Heroku hosting"
    )
    await message.reply_text(help_text, parse_mode=enums.ParseMode.MARKDOWN)


@app.on_message(filters.command("setdump"))
async def setdump_handler(client: Client, message: Message) -> None:
    """Handle /setdump command."""
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(
            "**Usage:** `/setdump -100XXXXX`\n\n"
            "Get your channel ID by forwarding a message from your channel to @userinfobot"
        )
        return
    try:
        channel_id = int(parts[1])
        set_dump_channel(message.from_user.id, channel_id)
        await message.reply_text(f"✅ **Dump channel set to:** `{channel_id}`")
    except ValueError:
        await message.reply_text("❌ **Invalid ID.** Please provide a valid number.")


@app.on_message(filters.command("setcaption"))
async def setcaption_handler(client: Client, message: Message) -> None:
    """Handle /setcaption command."""
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        set_custom_caption(message.from_user.id, "")
        await message.reply_text("✅ **Custom caption removed.**")
    else:
        caption = parts[1]
        set_custom_caption(message.from_user.id, caption)
        await message.reply_text(f"✅ **Custom caption set to:**\n{caption}")


@app.on_message(filters.command("setthumb"))
async def setthumb_handler(client: Client, message: Message) -> None:
    """Handle /setthumb command."""
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply_text("❌ **Reply to a photo** with `/setthumb` to set it as thumbnail.")
        return
        
    photo = message.reply_to_message.photo
    set_custom_thumb(message.from_user.id, photo.file_id)
    await message.reply_text("✅ **Custom thumbnail saved!**")


@app.on_message(filters.command("setid"))
async def setid_handler(client: Client, message: Message) -> None:
    """Handle /setid command - Set Telegram ID for web uploads."""
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        current_id = get_user_telegram_id(message.from_user.id)
        if current_id:
            await message.reply_text(
                f"📱 **Your current Telegram ID:** `{current_id}`\n\n"
                f"Web uploads will be sent to this ID.\n\n"
                f"**To change:** `/setid <your_telegram_id>`\n"
                f"**To remove:** `/setid 0`"
            )
        else:
            await message.reply_text(
                "📱 **Set your Telegram ID for Web UI uploads**\n\n"
                "When you use the Web UI, files will be sent to this Telegram ID.\n\n"
                "**Usage:** `/setid <your_telegram_id>`\n\n"
                "💡 **Get your ID:** Forward a message from yourself to @userinfobot"
            )
        return
    try:
        telegram_id = int(parts[1])
        if telegram_id == 0:
            set_user_telegram_id(message.from_user.id, 0)
            await message.reply_text("✅ **Telegram ID removed.** Web uploads will go to your chat ID.")
        else:
            set_user_telegram_id(message.from_user.id, telegram_id)
            await message.reply_text(
                f"✅ **Telegram ID set to:** `{telegram_id}`\n\n"
                f"📤 Files downloaded from Web UI will be sent to this ID."
            )
    except ValueError:
        await message.reply_text("❌ **Invalid ID.** Please provide a valid number.")


@app.on_message(filters.command("status"))
async def status_handler(client: Client, message: Message) -> None:
    """Handle /status command."""
    active_count = len(_active_downloads)
    download_dir = settings.DOWNLOAD_DIR
    
    # Calculate disk usage
    try:
        import shutil
        total, used, free = shutil.disk_usage(download_dir)
        disk_info = f"💾 Disk Free: `{format_bytes(free)}` / `{format_bytes(total)}`"
    except Exception:
        disk_info = "💾 Disk: Unknown"
    
    status_text = (
        "📊 **Bot Status**\n\n"
        f"⬇️ Active Downloads: `{active_count}`\n"
        f"📁 Download Dir: `{download_dir}`\n"
        f"{disk_info}\n"
        f"🚀 **MAX SPEED Mode Enabled**\n\n"
        f"✅ Bot is running normally"
    )
    await message.reply_text(status_text, parse_mode=enums.ParseMode.MARKDOWN)


@app.on_message(filters.command("cancel"))
async def cancel_cmd_handler(client: Client, message: Message) -> None:
    """Handle /cancel command."""
    # Find active download for this user
    user_active = None
    for msg_id, entry in _active_downloads.items():
        # Check if the status message belongs to this user
        try:
            msg = await client.get_messages(message.chat.id, msg_id)
            if msg and msg.from_user and msg.from_user.id == client.me.id:
                user_active = (msg_id, entry)
                break
        except Exception:
            continue
    
    if not user_active:
        await message.reply_text("ℹ️ No active download to cancel.")
        return
    
    msg_id, entry = user_active
    entry["cancelled"] = True
    gid = entry.get("gid")
    
    if gid:
        await aria2_rpc("aria2.forceRemove", [gid])
    
    await message.reply_text("🚫 **Download cancelled.**")


@app.on_message(filters.document)
async def torrent_handler(client: Client, message: Message) -> None:
    """Handle torrent file uploads."""
    # Check if it's a torrent file
    if not message.document or not message.document.file_name:
        return
        
    if not message.document.file_name.endswith('.torrent'):
        return
    
    status = await message.reply_text(
        "📥 **Received torrent file, downloading...**",
        parse_mode=enums.ParseMode.MARKDOWN,
    )
    
    try:
        # Download the torrent file
        torrent_path = await client.download_media(message.document)
        if not torrent_path:
            await safe_edit(status, "❌ **Failed to download torrent file.**")
            return
        
        # Convert to magnet or use as-is with aria2
        # For torrent files, we'll use the file path directly
        await safe_edit(status, "🔍 **Processing torrent...**")
        
        # Create a file:// URL for the torrent
        torrent_url = f"file://{os.path.abspath(torrent_path)}"
        
        # Now process as a regular download
        await process_download(client, message, torrent_url, status)
        
        # Cleanup torrent file
        try:
            if os.path.exists(torrent_path):
                os.remove(torrent_path)
        except Exception:
            pass
            
    except Exception as e:
        print(f"[torrent_handler] Error: {e}")
        await safe_edit(status, f"❌ **Error:** `{str(e)[:200]}`")


# ---------------------------------------------------------------------------
# Download Processing Logic
# ---------------------------------------------------------------------------
async def process_download(client: Client, message: Message, url: str, status: Message) -> None:
    """
    Process a download from URL/magnet and upload to Telegram.
    This is the core download/upload logic shared by URL and torrent handlers.
    """
    user_id = message.from_user.id
    target_chat_id = get_dump_channel(user_id) or message.chat.id
    custom_caption = get_custom_caption(user_id) or ""
    custom_thumb_id = get_custom_thumb(user_id)

    file_parts = []
    thumb_path = None
    filepath = None

    try:
        # 1. Add download to Aria2
        gid = await add_download(url, settings.DOWNLOAD_DIR)
        if not gid:
            await safe_edit(status, "❌ **Failed to add download.** Aria2 might be busy.")
            return

        # Setup progress callback
        start_time = time.time()

        async def dl_progress(action: str, current: int, total: int, t0: float, speed: float = 0, eta_seconds: float = 0):
            await safe_edit(
                status,
                format_progress(current, total, t0, action, speed=speed, eta_seconds=eta_seconds),
                reply_markup=_cancel_keyboard(status.id),
            )

        await safe_edit(status, "⬇️ **Starting download...**", reply_markup=_cancel_keyboard(status.id))

        # Register download for cancel functionality
        _active_downloads[status.id] = {"gid": gid, "cancelled": False}
        
        # Monitor download
        success, result = await monitor_download(gid, dl_progress, start_time)

        # Check if cancelled
        entry = _active_downloads.get(status.id, {})
        if entry.get("cancelled"):
            _active_downloads.pop(status.id, None)
            return
        
        if not success:
            await safe_edit(status, f"❌ **Download failed:** `{result}`")
            _active_downloads.pop(status.id, None)
            return
            
        filepath = result
        if not filepath or not os.path.exists(filepath):
            await safe_edit(status, "❌ **Error:** Download completed but file not found.")
            _active_downloads.pop(status.id, None)
            return

        filename = os.path.basename(filepath)
        size = os.path.getsize(filepath)

        await safe_edit(status, "✂️ **Processing file...**")
        _active_downloads.pop(status.id, None)

        # 2. Split file if > 1.9GB
        file_parts = await split_large_file(filepath)
        total_parts = len(file_parts)
        
        # 3. Download custom thumbnail if set
        if custom_thumb_id:
            try:
                thumb_path = await client.download_media(custom_thumb_id)
            except Exception as e:
                print(f"[thumb] Failed to download thumbnail: {e}")

        upload_start = time.time()

        # 4. Upload each part
        for idx, part in enumerate(file_parts, start=1):
            part_size = os.path.getsize(part)
            part_name = os.path.basename(part)
            part_label = f"Part {idx}/{total_parts}" if total_parts > 1 else filename

            last_update = [time.time()]

            async def up_progress(current: int, total: int, _label: str = part_label, _start: float = upload_start, _last: list = last_update):
                now = time.time()
                if now - _last[0] >= FLOOD_COOLDOWN:
                    await safe_edit(
                        status,
                        format_progress(current, total, _start, f"📤 Uploading {_label}"),
                    )
                    _last[0] = now

            # Build caption
            caption_lines = [
                f"📁 **{part_name}**",
                f"💾 Size: `{format_bytes(part_size)}`",
            ]
            if total_parts > 1:
                caption_lines.append(f"📂 Part **{idx}** of **{total_parts}**")
            
            if custom_caption:
                caption_lines.extend(["", custom_caption])
                
            caption = "\n".join(caption_lines)

            # Upload as document with MAX SPEED settings
            send_kwargs = {
                "chat_id": target_chat_id,
                "document": part,
                "caption": caption,
                "parse_mode": enums.ParseMode.MARKDOWN,
                "progress": up_progress,
                "force_document": True,  # Force as document for speed
                "disable_notification": True,  # Reduce overhead
            }
            
            if target_chat_id == message.chat.id:
                send_kwargs["reply_to_message_id"] = message.id
                
            if thumb_path and os.path.exists(thumb_path):
                send_kwargs["thumb"] = thumb_path

            # Upload with timeout and retry logic for max speed
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await client.send_document(**send_kwargs)
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        print(f"[upload] Retry {attempt + 1}/{max_retries} for {part_name}: {e}")
                        await asyncio.sleep(1)
                    else:
                        raise

            # Minimal delay between parts for max speed
            if idx < total_parts:
                await asyncio.sleep(0.5)

        await safe_edit(status, "✅ **Upload complete!** 🎉")

    except asyncio.CancelledError:
        await safe_edit(status, "🚫 **Download cancelled.**")

    except Exception as exc:
        print(f"[process_download] Error: {exc}")
        await safe_edit(status, f"❌ **Error:** `{str(exc)[:200]}`")

    finally:
        _active_downloads.pop(status.id, None)
        
        # Cleanup files
        try:
            for part in file_parts:
                if part != filepath and os.path.exists(part):
                    os.remove(part)
                    print(f"[cleanup] Removed part: {part}")
            
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
                print(f"[cleanup] Removed original: {filepath}")
                
            if thumb_path and os.path.exists(thumb_path):
                os.remove(thumb_path)
                print(f"[cleanup] Removed thumbnail: {thumb_path}")
        except Exception as e:
            print(f"[cleanup] Error: {e}")


# ---------------------------------------------------------------------------
# Main Leech Handler - Downloads and Uploads
# ---------------------------------------------------------------------------
@app.on_message(filters.text & filters.regex(r"(https?://\S+|magnet:\?xt=urn:btih:\S+)"))
async def leech_handler(client: Client, message: Message) -> None:
    """Handle download URLs and upload files to Telegram."""
    url = message.text.strip()
    status = await message.reply_text(
        "🔍 **Initializing download...**",
        parse_mode=enums.ParseMode.MARKDOWN,
    )
    
    await process_download(client, message, url, status)


# ---------------------------------------------------------------------------
# Web Server with WebSocket
# ---------------------------------------------------------------------------
async def ping_server():
    """Self-ping to keep Render/Heroku instance alive."""
    while True:
        await asyncio.sleep(600)
        if settings.SELF_PING_URL:
            try:
                from aiohttp import ClientSession, ClientTimeout
                async with ClientSession() as session:
                    async with session.get(
                        settings.SELF_PING_URL,
                        timeout=ClientTimeout(total=10),
                    ) as response:
                        print(f"[ping] Status: {response.status}")
            except Exception as e:
                print(f"[ping] Failed: {e}")


async def health_check(request):
    """Health check endpoint."""
    return web.json_response({
        "status": "ok",
        "service": "TG Leecher",
        "timestamp": time.time()
    })


async def web_download_task(ws, url: str, user_id: int = None, cleanup_torrent: str = None):
    """Handle download from Web UI via WebSocket."""
    filepath = None
    file_parts = []

    # Track last ping time for heartbeat
    last_ping_time = [time.time()]
    HEARTBEAT_INTERVAL = 15  # Send ping every 15 seconds to keep connection alive

    async def send_with_ping(data: dict):
        """Send data with heartbeat check."""
        try:
            await ws.send_json(data)
            last_ping_time[0] = time.time()
        except Exception as e:
            raise ConnectionError(f"Failed to send to WebSocket: {e}")

    async def heartbeat_checker():
        """Send periodic pings to keep WebSocket alive."""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                # Check if connection is still open
                if ws.closed:
                    break
                # Send a ping message
                await ws.send_json({"type": "ping", "timestamp": time.time()})
            except Exception:
                break

    try:
        # Start heartbeat task
        heartbeat_task = asyncio.create_task(heartbeat_checker())

        await send_with_ping({
            "status": "initializing",
            "message": "Adding to Aria2...",
            "percentage": 0
        })

        gid = await add_download(url, settings.DOWNLOAD_DIR)
        if not gid:
            await send_with_ping({
                "status": "error",
                "message": "Failed to add download to Aria2"
            })
            heartbeat_task.cancel()
            return

        start_time = time.time()

        async def ws_progress(action: str, current: int, total: int, t0: float, speed: float = 0, eta_seconds: float = 0):
            percent = int((current / total) * 100) if total > 0 else 0
            try:
                await send_with_ping({
                    "status": action.lower(),
                    "message": action,
                    "percentage": percent,
                    "current": current,
                    "total": total,
                    "speed": speed,
                    "eta": eta_seconds
                })
            except Exception:
                pass

        success, result = await monitor_download(gid, ws_progress, start_time)

        if not success:
            await send_with_ping({
                "status": "error",
                "message": f"Download failed: {result}"
            })
            heartbeat_task.cancel()
            return

        filepath = result

        await send_with_ping({
            "status": "processing",
            "message": "Splitting large files if needed...",
            "percentage": 100
        })

        # Split file if needed
        file_parts = await split_large_file(filepath)
        total_parts = len(file_parts)

        # Upload - Get target chat ID from user settings or use default
        if user_id:
            target_chat_id = get_web_upload_target(user_id)
        else:
            target_chat_id = settings.OWNER_ID if settings.OWNER_ID else None
        
        if not target_chat_id or target_chat_id == 0:
            await send_with_ping({
                "status": "error",
                "message": "No target Telegram ID configured. Use /setid command in bot to set your ID."
            })
            heartbeat_task.cancel()
            return

        # Verify the bot can send messages to this user
        try:
            await app.get_users(target_chat_id)
        except Exception as e:
            await send_with_ping({
                "status": "error",
                "message": f"Cannot access user {target_chat_id}. Make sure you've started the bot. Error: {str(e)[:100]}"
            })
            heartbeat_task.cancel()
            return

        for idx, part in enumerate(file_parts, start=1):
            await send_with_ping({
                "status": "uploading",
                "message": f"Uploading part {idx}/{total_parts}..." if total_parts > 1 else "Uploading...",
                "percentage": 100,
                "part": idx,
                "total_parts": total_parts
            })

            # Upload with MAX SPEED settings
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await app.send_document(
                        chat_id=target_chat_id,
                        document=part,
                        caption=f"📤 Uploaded via Web UI\n📁 {os.path.basename(part)}",
                        force_document=True,
                        disable_notification=True
                    )
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                    else:
                        raise

            # Minimal delay between parts for max speed
            if idx < total_parts:
                await asyncio.sleep(0.5)

        await send_with_ping({
            "status": "completed",
            "message": f"Successfully uploaded to Telegram! (User ID: {target_chat_id})",
            "percentage": 100,
            "target_id": target_chat_id
        })

        heartbeat_task.cancel()

    except ConnectionError:
        print("[web_download] WebSocket connection lost")
    except Exception as e:
        print(f"[web_download] Error: {e}")
        try:
            await ws.send_json({
                "status": "error",
                "message": str(e)[:200]
            })
        except Exception:
            pass
    finally:
        # Cleanup
        try:
            for part in file_parts:
                if part != filepath and os.path.exists(part):
                    os.remove(part)
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
            # Cleanup uploaded torrent file
            if cleanup_torrent and os.path.exists(cleanup_torrent):
                os.remove(cleanup_torrent)
                print(f"[web_cleanup] Removed torrent file: {cleanup_torrent}")
        except Exception as e:
            print(f"[web_cleanup] Error: {e}")


async def websocket_handler(request):
    """WebSocket handler for real-time updates."""
    ws = web.WebSocketResponse(
        max_msg_size=10*1024*1024,  # 10MB max for torrent files
        heartbeat=30.0,  # Send ping frame every 30 seconds to keep connection alive
        autoping=True,   # Automatically respond to ping frames
    )
    await ws.prepare(request)

    print(f"[ws] New WebSocket connection from {request.remote}")

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    msg_type = data.get("type")

                    # Handle client ping messages
                    if msg_type == "ping":
                        await ws.send_json({"type": "pong", "timestamp": data.get("timestamp")})
                        continue

                    url = data.get("url")
                    torrent_data = data.get("torrent_data")  # Base64 encoded torrent
                    torrent_name = data.get("torrent_name")
                    user_id = data.get("user_id")  # User's Telegram ID for uploads

                    if url:
                        asyncio.create_task(web_download_task(ws, url, user_id=user_id))
                    elif torrent_data and torrent_name:
                        # Handle torrent file upload
                        import base64
                        try:
                            torrent_bytes = base64.b64decode(torrent_data)
                            torrent_path = os.path.join(settings.DOWNLOAD_DIR, torrent_name)

                            # Save torrent file
                            with open(torrent_path, 'wb') as f:
                                f.write(torrent_bytes)

                            # Process as file:// URL
                            file_url = f"file://{os.path.abspath(torrent_path)}"
                            asyncio.create_task(web_download_task(ws, file_url, user_id=user_id, cleanup_torrent=torrent_path))
                        except Exception as e:
                            await ws.send_json({"status": "error", "message": f"Failed to process torrent: {str(e)}"})
                    else:
                        await ws.send_json({"status": "error", "message": "No URL or torrent provided"})

                except json.JSONDecodeError:
                    await ws.send_json({"status": "error", "message": "Invalid JSON"})
                except Exception as e:
                    await ws.send_json({"status": "error", "message": str(e)})
            elif msg.type == web.WSMsgType.ERROR:
                print(f"[ws] WebSocket error: {ws.exception()}")
                break
    except Exception as e:
        print(f"[ws] WebSocket handler error: {e}")
    finally:
        print(f"[ws] WebSocket connection closed")

    return ws


async def start_web_server():
    """Start the web server for health checks and Web UI."""
    web_app = web.Application()
    
    _here = os.path.dirname(os.path.abspath(__file__))
    _static_dir = os.path.join(_here, "static")
    
    if os.path.exists(_static_dir):
        async def serve_index(request):
            index_path = os.path.join(_static_dir, "index.html")
            if os.path.exists(index_path):
                return web.FileResponse(index_path)
            return web.Response(text="Web UI not available", status=404)
            
        web_app.router.add_get("/", serve_index)
        web_app.router.add_static("/static", _static_dir)
    else:
        web_app.router.add_get("/", health_check)
        
    web_app.router.add_get("/health", health_check)
    web_app.router.add_get("/ws", websocket_handler)
        
    runner = web.AppRunner(web_app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", settings.PORT).start()
    print(f"[web] Server started on port {settings.PORT}")
    
    asyncio.create_task(ping_server())


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
async def main():
    """Main entry point."""
    start_aria2_daemon()
    await start_web_server()
    await app.start()
    print("[bot] Started successfully. Listening for messages...")
    await idle()
    await app.stop()


if __name__ == "__main__":
    app.run(main())
