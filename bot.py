import asyncio
import logging
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

import pytz
from config import BOT_TOKEN, ADMIN_IDS, MOSCOW_TZ
from database import db  # Импортируем глобальный экземпляр

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Часовой пояс Москвы
moscow_tz = pytz.timezone(MOSCOW_TZ)

# Состояния FSM
class TaskStates(StatesGroup):
    waiting_for_task_selection = State()
    waiting_for_comment = State()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def format_task(task: Dict) -> str:
    """Форматирует задачу в читаемый вид"""
    status_emoji = "✅" if task['status'] == 'done' else "⏳"
    status_text = "Выполнена" if task['status'] == 'done' else "В работе"
    
    text = f"{status_emoji} Задача #{task['id']}\n"
    text += f"📝 Описание: {task['description']}\n"
    text += f"👤 Исполнитель: {task['assignee_username']}\n"
    text += f"⏰ Дедлайн: {task['deadline'].strftime('%d.%m.%Y %H:%M')}\n"
    text += f"📊 Статус: {status_text}\n"
    text += f"📅 Дата создания: {task['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
    
    if task['completed_at']:
        text += f"✅ Дата исполнения: {task['completed_at'].strftime('%d.%m.%Y %H:%M')}\n"
    if task['comment']:
        text += f"💬 Комментарий: {task['comment']}\n"
    
    return text

# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    last_name = message.from_user.last_name or ""
    
    logger.info(f"👤 Новый пользователь: {user_id} @{username}")
    
    db.add_user(user_id, username, first_name, last_name)
    
    welcome_text = "👋 Добро пожаловать в бота управления задачами!\n\n"
    welcome_text += "📋 Основные команды:\n"
    welcome_text += "/tasks - показать мои задачи\n\n"
    
    if is_admin(user_id):
        welcome_text += "⚡ Команды администратора:\n"
        welcome_text += "/create_task - создать задачу\n"
        welcome_text += "/all_tasks - все задачи\n"
        welcome_text += "/delete_task - удалить задачу\n"
        welcome_text += "/users - список пользователей\n\n"
        welcome_text += "📝 Формат создания задачи:\n"
        welcome_text += "/create_task @username DD.MM.YYYY HH:MM Описание задачи\n\n"
        welcome_text += "❌ Формат удаления задачи:\n"
        welcome_text += "/delete_task id_задачи"
    
    await message.answer(welcome_text)
    logger.info(f"✅ Пользователь {user_id} получил приветствие")

# Команда /tasks
@dp.message(Command("tasks"))
async def cmd_tasks(message: Message):
    user_id = message.from_user.id
    logger.info(f"📋 Пользователь {user_id} запросил задачи")
    
    tasks = db.get_user_tasks(user_id)
    
    if not tasks:
        await message.answer("📭 У вас нет задач")
        return
    
    text = "📋 Ваши задачи:\n\n"
    for task in tasks:
        text += format_task(task)
        text += "─" * 30 + "\n"
    
    # Кнопка для выполнения задачи (только если есть задачи в статусе todo)
    todo_tasks = [task for task in tasks if task['status'] == 'todo']
    if todo_tasks:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выполнить задачу", callback_data="complete_task")]
        ])
        await message.answer(text, reply_markup=keyboard)
    else:
        await message.answer(text)
    
    logger.info(f"✅ Пользователь {user_id} получил {len(tasks)} задач")

# Обработка кнопки "Выполнить задачу"
@dp.callback_query(F.data == "complete_task")
async def complete_task_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"🔄 Пользователь {user_id} начал выполнение задачи")
    
    tasks = db.get_user_tasks(user_id)
    
    # Фильтруем только задачи со статусом 'todo'
    todo_tasks = [task for task in tasks if task['status'] == 'todo']
    
    if not todo_tasks:
        await callback.answer("У вас нет задач для выполнения", show_alert=True)
        return
    
    # Создаем клавиатуру с задачами
    keyboard_buttons = []
    for task in todo_tasks:
        button_text = f"#{task['id']}: {task['description'][:30]}..."
        keyboard_buttons.append([InlineKeyboardButton(
            text=button_text, 
            callback_data=f"select_task_{task['id']}"
        )])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await callback.message.answer("Выберите задачу для выполнения:", reply_markup=keyboard)
    await state.set_state(TaskStates.waiting_for_task_selection)
    await callback.answer()

# Выбор задачи для выполнения
@dp.callback_query(TaskStates.waiting_for_task_selection, F.data.startswith("select_task_"))
async def select_task_callback(callback: CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split("_")[2])
    logger.info(f"🎯 Пользователь {callback.from_user.id} выбрал задачу #{task_id}")
    
    await state.update_data(selected_task_id=task_id)
    await callback.message.answer("Напишите комментарий к выполнению задачи:")
    await state.set_state(TaskStates.waiting_for_comment)
    await callback.answer()

# Получение комментария и завершение задачи
@dp.message(TaskStates.waiting_for_comment)
async def process_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = data['selected_task_id']
    comment = message.text
    
    logger.info(f"✅ Пользователь {message.from_user.id} завершает задачу #{task_id}")
    
    db.complete_task(task_id, comment)
    
    # Получаем обновленную задачу для отображения
    task = db.get_task_by_id(task_id)
    
    await message.answer(
        f"✅ Задача выполнена!\n\n"
        f"{format_task(task)}"
    )
    await state.clear()

# Команда /create_task (только для администраторов)
@dp.message(Command("create_task"))
async def cmd_create_task(message: Message, command: CommandObject):
    user_id = message.from_user.id
    logger.info(f"📝 Админ {user_id} создает задачу: {command.args}")
    
    if not is_admin(user_id):
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return
    
    if not command.args:
        await message.answer(
            "📝 Формат команды:\n"
            "/create_task @username DD.MM.YYYY HH:MM Описание задачи\n\n"
            "📌 Пример:\n"
            "/create_task @user1 25.12.2024 15:30 Разработать новый функционал"
        )
        return
    
    try:
        args = command.args.split()
        if len(args) < 4:
            raise ValueError("Недостаточно аргументов")
        
        username = args[0]
        date_str = args[1]
        time_str = args[2]
        description = " ".join(args[3:])
        
        # Парсим дату и время
        deadline_str = f"{date_str} {time_str}"
        deadline = datetime.strptime(deadline_str, "%d.%m.%Y %H:%M")
        deadline = moscow_tz.localize(deadline)
        
        # Проверяем, что дедлайн в будущем
        if deadline <= datetime.now(moscow_tz):
            await message.answer("❌ Дедлайн должен быть в будущем")
            return
        
        # Создаем задачу
        task_id = db.create_task(description, username, deadline)
        
        response_text = (
            f"✅ Задача создана!\n\n"
            f"ID задачи: {task_id}\n"
            f"Описание: {description}\n"
            f"Исполнитель: {username}\n"
            f"Дедлайн: {deadline.strftime('%d.%m.%Y %H:%M')}\n"
            f"Статус: To do"
        )
        
        await message.answer(response_text)
        logger.info(f"✅ Задача #{task_id} создана для {username}")
        
        # УВЕДОМЛЕНИЕ ИСПОЛНИТЕЛЮ
        try:
            # Находим пользователя по username
            users = db.get_all_users()
            assignee_user_id = None
            
            for user in users:
                user_id, user_username, first_name, last_name, registered_at = user
                # Сравниваем username без @
                if user_username and user_username.lower() == username.lstrip('@').lower():
                    assignee_user_id = user_id
                    break
            
            if assignee_user_id:
                notification_text = (
                    f"📋 Вам назначена новая задача!\n\n"
                    f"🆔 ID задачи: {task_id}\n"
                    f"📝 Описание: {description}\n"
                    f"⏰ Дедлайн: {deadline.strftime('%d.%m.%Y %H:%M')}\n"
                    f"📊 Статус: To do\n\n"
                    f"Для просмотра задач используйте команду /tasks"
                )
                
                await bot.send_message(assignee_user_id, notification_text)
                logger.info(f"✅ Уведомление отправлено исполнителю {username} (ID: {assignee_user_id})")
            else:
                logger.warning(f"⚠️ Исполнитель {username} не найден в базе пользователей")
                
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке уведомления исполнителю {username}: {e}")
        
    except ValueError as e:
        await message.answer(f"❌ Ошибка формата: {e}\n\nПравильный формат:\n/create_task @username DD.MM.YYYY HH:MM Описание задачи")

# Команда /all_tasks (только для администраторов)
@dp.message(Command("all_tasks"))
async def cmd_all_tasks(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return
    
    tasks = db.get_all_tasks()
    
    if not tasks:
        await message.answer("📭 Нет задач в базе данных")
        return
    
    # Разбиваем на сообщения, если задач много
    text = "📋 Все задачи в системе:\n\n"
    for task in tasks:
        task_text = format_task(task)
        if len(text + task_text + "─" * 40 + "\n") > 4000:
            await message.answer(text)
            text = task_text + "─" * 40 + "\n"
        else:
            text += task_text + "─" * 40 + "\n"
    
    await message.answer(text)

# Команда /delete_task (только для администраторов)
@dp.message(Command("delete_task"))
async def cmd_delete_task(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return
    
    if not command.args:
        await message.answer("❌ Формат команды: /delete_task id_задачи")
        return
    
    try:
        task_id = int(command.args.strip())
        task = db.get_task_by_id(task_id)
        
        if not task:
            await message.answer(f"❌ Задача с ID {task_id} не найдена")
            return
        
        db.delete_task(task_id)
        await message.answer(f"✅ Задача #{task_id} удалена")
        
    except ValueError:
        await message.answer("❌ Неверный формат ID задачи")
    except Exception as e:
        await message.answer(f"❌ Ошибка при удалении задачи: {e}")

# Команда /users (только для администраторов)
@dp.message(Command("users"))
async def cmd_users(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return
    
    users = db.get_all_users()
    
    if not users:
        await message.answer("📭 Нет зарегистрированных пользователей")
        return
    
    text = "👥 Пользователи бота:\n\n"
    for user in users:
        user_id, username, first_name, last_name, registered_at = user
        text += f"🆔 ID: {user_id}\n"
        text += f"👤 Username: @{username}\n" if username else "👤 Username: не указан\n"
        text += f"📛 Имя: {first_name} {last_name}\n"
        text += f"📅 Зарегистрирован: {datetime.fromisoformat(registered_at).strftime('%d.%m.%Y %H:%M')}\n"
        text += "─" * 30 + "\n"
    
    await message.answer(text)

# Функция для отправки уведомлений
async def send_notifications():
    while True:
        try:
            now = datetime.now(moscow_tz)
            logger.info(f"🔔 Проверка уведомлений в {now.strftime('%d.%m.%Y %H:%M:%S')}")
            
            # Проверяем, что сейчас 9:00 по Москве
            if now.hour == 9 and now.minute == 0:
                logger.info("⏰ Время отправки уведомлений - 9:00")
                tasks_for_notification = db.get_tasks_for_notification()
                logger.info(f"📨 Найдено задач для уведомления: {len(tasks_for_notification)}")
                
                for task in tasks_for_notification:
                    task_id, description, assignee_username, deadline, user_id = task
                    deadline_dt = datetime.fromisoformat(deadline)
                    days_left = (deadline_dt.date() - now.date()).days
                    
                    if user_id:
                        try:
                            if days_left == 7:
                                message_text = (
                                    f"🔔 Напоминание о задаче!\n\n"
                                    f"Задача #{task_id}: {description}\n"
                                    f"Дедлайн: {deadline_dt.strftime('%d.%m.%Y %H:%M')}\n"
                                    f"⏰ До дедлайна осталось 7 дней"
                                )
                            elif days_left == 1:
                                message_text = (
                                    f"🔔 Срочное напоминание!\n\n"
                                    f"Задача #{task_id}: {description}\n"
                                    f"Дедлайн: {deadline_dt.strftime('%d.%m.%Y %H:%M')}\n"
                                    f"⏰ До дедлайна остался 1 день!"
                                )
                            else:
                                continue
                            
                            await bot.send_message(user_id, message_text)
                            logger.info(f"✅ Отправлено уведомление пользователю {assignee_username} о задаче #{task_id}")
                            
                        except Exception as e:
                            logger.error(f"❌ Не удалось отправить уведомление пользователю {user_id}: {e}")
                
                # Ждем 1 минуту, чтобы не отправлять уведомления несколько раз
                await asyncio.sleep(60)
            
            # Проверяем каждую минуту
            await asyncio.sleep(60)
            
        except Exception as e:
            logger.error(f"❌ Ошибка в функции отправки уведомлений: {e}")
            await asyncio.sleep(60)

async def main():
    try:
        logger.info("🚀 ЗАПУСК БОТА УПРАВЛЕНИЯ ЗАДАЧАМИ...")
        logger.info(f"👑 Администраторы: {ADMIN_IDS}")
        
        # Запускаем задачу для отправки уведомлений
        asyncio.create_task(send_notifications())
        
        # Удаляем вебхук и запускаем polling
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Бот запущен и готов к работе!")
        
        # Запускаем polling
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске бота: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())