# ⚡ TG Leecher Bot - MAX SPEED Edition

A high-performance Telegram bot for downloading files from URLs, magnet links, and torrents, then uploading them to Telegram with **MAXIMUM SPEED** optimization for Heroku.

## ✨ Features

- **🚀 MAX SPEED Downloads**: 32 connections per server, optimized for Heroku
- **📤 MAX SPEED Uploads**: Fastest possible Telegram uploads
- **Multiple Source Support**: Direct links, magnet links, and torrent files
- **Auto File Splitting**: Automatically splits files > 1.9GB to comply with Telegram limits
- **Real-time Progress**: Visual progress bars with speed and ETA
- **Web UI**: Modern, interactive web interface with WebSocket real-time updates
- **Free for All Users**: No owner restrictions - anyone can use the bot!
- **Custom Telegram ID**: Users can set their own Telegram ID to receive web uploads
- **Custom Settings**: Dump channels, custom captions, and thumbnails

## 🚀 MAX SPEED Optimizations

### Download (Aria2)
- 32 max connections per server
- 32 split connections
- No speed limits
- 200 BitTorrent max peers
- HTTP gzip compression enabled
- Optimized timeouts and retries

### Upload (Pyrogram)
- Force document mode for speed
- Retry logic with minimal delays
- Notification disabled for reduced overhead
- Maximum concurrent uploads

## 🛠 Tech Stack

- **Python 3.11** with asyncio
- **Pyrogram** - Telegram MTProto client
- **Aria2** - High-performance download engine
- **Aiohttp** - Async web server
- **Tailwind CSS** - Modern UI styling

## ⚙️ Setup

### Environment Variables

```bash
API_ID=your_telegram_api_id          # Required - from my.telegram.org
API_HASH=your_telegram_api_hash      # Required - from my.telegram.org
BOT_TOKEN=your_bot_token             # Required - from @BotFather
OWNER_ID=your_telegram_user_id       # Optional - for notifications only (space-separated for multiple owners)
DOWNLOAD_DIR=./downloads             # Optional - defaults to /tmp/downloads
PORT=8080                            # Optional - defaults to 8080
SELF_PING_URL=optional_url           # Optional - for Heroku/Render keep-alive
```

### Heroku Deployment

1. Fork this repository
2. Create a new Heroku app:
   ```bash
   heroku create your-app-name
   ```
3. Add the Apt buildpack (required for aria2 and ffmpeg):
   ```bash
   heroku buildpacks:add -a your-app-name https://github.com/heroku/heroku-buildpack-apt.git
   heroku buildpacks:add -a your-app-name heroku/python
   ```
4. Set environment variables in Heroku dashboard or via CLI:
   ```bash
   heroku config:set API_ID=your_telegram_api_id -a your-app-name
   heroku config:set API_HASH=your_telegram_api_hash -a your-app-name
   heroku config:set BOT_TOKEN=your_bot_token -a your-app-name
   heroku config:set PORT=8080 -a your-app-name
   ```
5. Deploy to Heroku:
   ```bash
   git push heroku main
   ```

**Note**: The bot is optimized for Heroku's ephemeral filesystem and network constraints. The `heroku.sh` script automatically starts aria2c with RPC enabled before launching the bot.

### Docker

```bash
docker build -t tg-leecher .
docker run -e API_ID=xxx -e API_HASH=xxx -e BOT_TOKEN=xxx -p 8080:8080 tg-leecher
```

## 🤖 Bot Commands

- `/start` - Show welcome message
- `/help` - Show help
- `/setid <telegram_id>` - Set your Telegram ID for web uploads
- `/setdump <channel_id>` - Set auto-upload channel
- `/setcaption <text>` - Set custom caption
- `/setthumb` (reply to image) - Set thumbnail
- `/status` - Check bot status
- `/cancel` - Cancel active download

## 🌐 Web UI

The web interface is available at the root URL (`/`). Features:

- Modern, interactive glass-morphism design
- Real-time download/upload progress
- Drag & drop torrent file support
- Telegram ID configuration (saved in browser)
- Activity logging
- Mobile responsive

**Note**: To receive files from the Web UI, you must:
1. Start the bot in Telegram (`/start`)
2. Set your Telegram ID in the Web UI settings (get it from @userinfobot)

## 📁 Project Structure

```
.
├── bot.py                 # Main bot with Telegram & Web handlers
├── config.py             # Settings management
├── utils.py              # Formatting utilities
├── requirements.txt      # Python dependencies
├── Dockerfile           # Container configuration
├── static/
│   └── index.html       # Web UI with MAX SPEED branding
└── lastperson07/
    ├── aria2_client.py   # Aria2 RPC client (MAX SPEED settings)
    ├── settings_db.py    # User settings storage
    └── split_utils.py    # File splitting utilities
```

## 🔥 Key Improvements in MAX Edition

1. **No Access Restrictions**: Bot is now open for all users
2. **User-configurable Target ID**: Each user can set where web uploads go
3. **Maximum Speed**: Both download and upload are fully optimized
4. **Better UI**: Interactive, polished web interface
5. **Heroku Ready**: Optimized for Heroku's environment

## 📜 License

MIT

---

**Made with ⚡ for speed demons!**
