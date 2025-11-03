#!/bin/bash
echo "🛑 Останавливаю все процессы бота..."
pkill -f "python bot.py"
sleep 3
echo "🚀 Запускаю бота..."
python bot.py