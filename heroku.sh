#!/bin/bash

# Start aria2c with RPC server enabled and MAX SPEED daemon settings
# Heroku assigns PORT dynamically, but aria2 needs a different port
aria2c \
  --enable-rpc \
  --rpc-listen-all=true \
  --rpc-allow-origin-all=true \
  --rpc-listen-port=6800 \
  --dir=/tmp/downloads \
  --continue=true \
  --max-connection-per-server=32 \
  --split=32 \
  --min-split-size=1M \
  --max-concurrent-downloads=10 \
  --max-tries=20 \
  --retry-wait=3 \
  --timeout=300 \
  --connect-timeout=60 \
  --bt-max-peers=200 \
  --seed-time=0 \
  --allow-overwrite=true \
  --user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
  > /dev/null 2>&1 &

# Wait a moment for aria2c to start
sleep 2

# Start the bot
python bot.py
