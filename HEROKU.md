# Heroku Deployment Guide

This guide will help you deploy the TG Leecher Bot to Heroku.

## Prerequisites

- A Heroku account (free tier works)
- Heroku CLI installed
- Git installed
- Telegram API credentials (API ID and Hash from my.telegram.org)
- Bot token from @BotFather

## Step-by-Step Deployment

### 1. Fork and Clone the Repository

```bash
git clone https://github.com/yourusername/tg-leecher-bot.git
cd tg-leecher-bot
```

### 2. Create a Heroku App

```bash
heroku create your-app-name
```

### 3. Configure Buildpacks

The bot requires `aria2` and `ffmpeg` system packages, which are installed using the Apt buildpack.

```bash
# Add the Apt buildpack first (must be before Python)
heroku buildpacks:add -a your-app-name https://github.com/heroku/heroku-buildpack-apt.git
heroku buildpacks:add -a your-app-name heroku/python
```

Verify buildpacks are in correct order:
```bash
heroku buildpacks -a your-app-name
```

Output should show:
```
1. https://github.com/heroku/heroku-buildpack-apt.git
2. heroku/python
```

### 4. Set Environment Variables

Replace the values with your actual credentials:

```bash
# Required variables
heroku config:set API_ID=12345678 -a your-app-name
heroku config:set API_HASH=abcdefgh12345678 -a your-app-name
heroku config:set BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11 -a your-app-name

# Optional variables (with defaults)
heroku config:set PORT=8080 -a your-app-name
heroku config:set DOWNLOAD_DIR=/tmp/downloads -a your-app-name
heroku config:set OWNER_ID=0 -a your-app-name  # Space-separated for multiple owners (e.g., "123456 789012")
```

**Important**: Get your credentials from:
- **API_ID & API_HASH**: Visit https://my.telegram.org
- **BOT_TOKEN**: Start a chat with @BotFather on Telegram

### 5. Deploy to Heroku

```bash
# If you haven't set the Heroku remote
heroku git:remote -a your-app-name

# Push and deploy
git push heroku main
```

The deployment process will:
1. Install system packages (aria2, ffmpeg) via Apt buildpack
2. Install Python dependencies from requirements.txt
3. Start the application using the Procfile

### 6. Verify Deployment

Check the logs to ensure everything is running:

```bash
heroku logs --tail -a your-app-name
```

You should see:
- Aria2 starting up
- Bot starting and connecting to Telegram

### 7. Test the Bot

- Search for your bot in Telegram
- Send `/start` to initialize
- Try downloading a file with a URL or magnet link

## File Structure for Heroku

The following files are included for Heroku deployment:

- **Procfile**: Tells Heroku how to run the app (`web: bash heroku.sh`)
- **runtime.txt**: Specifies Python 3.11
- **Aptfile**: Lists system packages to install (aria2, ffmpeg)
- **.buildpacks**: Documents required buildpacks
- **heroku.sh**: Startup script that runs aria2c in background then starts the bot

## Troubleshooting

### Build Fails with "aria2: command not found"

Make sure the Apt buildpack is listed **before** the Python buildpack:
```bash
heroku buildpacks:clear -a your-app-name
heroku buildpacks:add -a your-app-name https://github.com/heroku/heroku-buildpack-apt.git
heroku buildpacks:add -a your-app-name heroku/python
git push heroku main
```

### Bot Crashes on Startup

Check logs for error messages:
```bash
heroku logs --tail -a your-app-name
```

Common issues:
- Missing or incorrect environment variables
- Invalid API credentials
- Bot token revoked

### Download/Upload Not Working

Verify that aria2 is running by checking logs:
```bash
heroku logs --tail -a your-app-name | grep aria2
```

### Need to Restart the App

```bash
heroku restart -a your-app-name
```

## Scaling

On the free tier, you get 1 web dyno which is sufficient for moderate usage. If you need more capacity:

```bash
heroku ps:scale web=2 -a your-app-name
```

Note: Each dyno runs independently with its own aria2 instance.

## Ephemeral Filesystem

Heroku's filesystem is ephemeral - files in `/tmp` are cleared when the dyno restarts. The bot is configured to use `/tmp/downloads` for downloads, which is appropriate for this architecture.

## Web UI Access

The web UI is accessible at:
```
https://your-app-name.herokuapp.com/
```

Use this interface to:
- Download via URL/magnet link
- Monitor progress in real-time
- Configure your Telegram ID for receiving files

## Cost

- Free tier: 550 hours/month (sufficient for always-on bot)
- Paid dynos: Starting at $5/month for 24/7 uptime

For most users, the free tier with occasional sleep cycles works well.

## Support

If you encounter issues:
1. Check Heroku logs: `heroku logs --tail`
2. Verify all environment variables are set correctly
3. Ensure buildpacks are in correct order
4. Check the README for general setup instructions
