import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN', '8445298102:AAHCcDhK9HC6Tp7OkhEKfVazfKwwJWF3P_E')
ADMIN_IDS = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '451294137').split(',')]

# Настройки базы данных
DATABASE_NAME = 'tasks.db'

# Настройки времени
MOSCOW_TZ = 'Europe/Moscow'
NOTIFICATION_TIME = '09:00'  # Время отправки уведомлений