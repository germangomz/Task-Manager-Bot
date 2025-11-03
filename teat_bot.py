import asyncio
import logging

# Настройка логирования для отладки
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_bot():
    print("🤖 Тестирование запуска бота...")
    
    try:
        from aiogram import Bot
        from config import BOT_TOKEN
        
        bot = Bot(token=BOT_TOKEN)
        me = await bot.get_me()
        print(f"✅ Бот успешно подключен: @{me.username} ({me.first_name})")
        await bot.session.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка подключения бота: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_bot())