# TG Leecher Bot

A high-performance Telegram bot for downloading files from URLs, magnet links, and torrents, then uploading them to Telegram.

## Features

- **Multiple Source Support**: Direct links, magnet links, and torrent files
- **Auto File Splitting**: Automatically splits files > 1.9GB to comply with Telegram limits
- **Real-time Progress**: Visual progress bars with speed and ETA
- **Web UI**: Modern web interface with WebSocket real-time updates
- **Custom Settings**: Dump channels, custom captions, and thumbnails
- **Owner-based Access**: Secure access control

## Tech Stack

- **Python 3.11** with asyncio
- **Pyrogram** - Telegram MTProto client
- **Aria2** - High-performance download engine
- **Aiohttp** - Async web server
- **Tailwind CSS** - Modern UI styling

## Setup

### Environment Variables

```bash
API_ID=your_telegram_api_id
API_HASH=your_telegram_api_hash
BOT_TOKEN=your_bot_token
OWNER_ID=your_telegram_user_id
DOWNLOAD_DIR=./downloads
PORT=8080
SELF_PING_URL=optional_url_for_render/heroku
```

### Docker

```bash
docker build -t tg-leecher .
docker run -e API_ID=xxx -e API_HASH=xxx -e BOT_TOKEN=xxx tg-leecher
```

### Commands

- `/start` - Show welcome message
- `/help` - Show help
- `/setdump <channel_id>` - Set auto-upload channel
- `/setcaption <text>` - Set custom caption
- `/setthumb` (reply to image) - Set thumbnail

## Project Structure

```
.
├── bot.py                 # Main bot with Telegram & Web handlers
├── config.py             # Settings management
├── utils.py              # Formatting utilities
├── requirements.txt      # Python dependencies
├── static/
│   └── index.html       # Web UI
└── lastperson07/
    ├── aria2_client.py   # Aria2 RPC client
    ├── settings_db.py    # User settings storage
    └── split_utils.py    # File splitting utilities
```

## License

MIT
