import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pytz
from config import DATABASE_NAME, MOSCOW_TZ

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_name: str = DATABASE_NAME):
        self.db_name = db_name
        self.moscow_tz = pytz.timezone(MOSCOW_TZ)
        self.init_database()

    def get_connection(self):
        return sqlite3.connect(self.db_name, check_same_thread=False)

    def init_database(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица задач
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                assignee_username TEXT NOT NULL,
                assignee_id INTEGER,
                deadline TIMESTAMP NOT NULL,
                status TEXT DEFAULT 'todo',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                comment TEXT,
                FOREIGN KEY (assignee_id) REFERENCES users (user_id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ База данных инициализирована")

    def add_user(self, user_id: int, username: str, first_name: str, last_name: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name))
        conn.commit()
        conn.close()
        logger.info(f"✅ Пользователь {user_id} добавлен в базу")

    def create_task(self, description: str, assignee_username: str, deadline: datetime):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Находим ID пользователя по username
        cursor.execute('SELECT user_id FROM users WHERE username = ?', (assignee_username.lstrip('@'),))
        result = cursor.fetchone()
        assignee_id = result[0] if result else None
        
        cursor.execute('''
            INSERT INTO tasks (description, assignee_username, assignee_id, deadline, status)
            VALUES (?, ?, ?, ?, 'todo')
        ''', (description, assignee_username, assignee_id, deadline))
        
        task_id = cursor.lastrowid
        conn.commit()
        conn.close()
        logger.info(f"✅ Задача #{task_id} создана для {assignee_username}")
        return task_id

    def get_user_tasks(self, user_id: int) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, description, assignee_username, deadline, status, created_at, completed_at, comment
            FROM tasks 
            WHERE assignee_id = ? OR assignee_username = (SELECT username FROM users WHERE user_id = ?)
            ORDER BY deadline ASC
        ''', (user_id, user_id))
        
        tasks = []
        for row in cursor.fetchall():
            deadline = datetime.fromisoformat(row[3]) if row[3] else None
            created_at = datetime.fromisoformat(row[5]) if row[5] else None
            completed_at = datetime.fromisoformat(row[6]) if row[6] else None
            
            tasks.append({
                'id': row[0],
                'description': row[1],
                'assignee_username': row[2],
                'deadline': deadline,
                'status': row[4],
                'created_at': created_at,
                'completed_at': completed_at,
                'comment': row[7]
            })
        
        conn.close()
        return tasks

    def get_all_tasks(self) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, description, assignee_username, deadline, status, created_at, completed_at, comment
            FROM tasks 
            ORDER BY deadline ASC
        ''')
        
        tasks = []
        for row in cursor.fetchall():
            deadline = datetime.fromisoformat(row[3]) if row[3] else None
            created_at = datetime.fromisoformat(row[5]) if row[5] else None
            completed_at = datetime.fromisoformat(row[6]) if row[6] else None
            
            tasks.append({
                'id': row[0],
                'description': row[1],
                'assignee_username': row[2],
                'deadline': deadline,
                'status': row[4],
                'created_at': created_at,
                'completed_at': completed_at,
                'comment': row[7]
            })
        
        conn.close()
        return tasks

    def complete_task(self, task_id: int, comment: str = None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE tasks 
            SET status = 'done', completed_at = CURRENT_TIMESTAMP, comment = ?
            WHERE id = ?
        ''', (comment, task_id))
        conn.commit()
        conn.close()
        logger.info(f"✅ Задача #{task_id} выполнена")

    def delete_task(self, task_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        conn.commit()
        conn.close()
        logger.info(f"✅ Задача #{task_id} удалена")

    def get_all_users(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, username, first_name, last_name, registered_at FROM users')
        users = cursor.fetchall()
        conn.close()
        return users

    def get_tasks_for_notification(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        now = datetime.now(self.moscow_tz)
        seven_days = now + timedelta(days=7)
        one_day = now + timedelta(days=1)
        
        cursor.execute('''
            SELECT t.id, t.description, t.assignee_username, t.deadline, u.user_id
            FROM tasks t
            LEFT JOIN users u ON t.assignee_username = u.username
            WHERE t.status = 'todo' 
            AND (
                (date(t.deadline) = date(?) AND strftime('%H:%M', t.deadline) = '09:00') OR
                (date(t.deadline) = date(?) AND strftime('%H:%M', t.deadline) = '09:00')
            )
        ''', (seven_days.strftime('%Y-%m-%d'), one_day.strftime('%Y-%m-%d')))
        
        tasks = cursor.fetchall()
        conn.close()
        return tasks
    
    def get_user_by_username(self, username: str):
        """Находит пользователя по username"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, username, first_name, last_name FROM users WHERE username = ?', (username.lstrip('@'),))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            return {
                'user_id': user[0],
                'username': user[1],
                'first_name': user[2],
                'last_name': user[3]
            }
        return None

    def get_task_by_id(self, task_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, description, assignee_username, deadline, status, created_at, completed_at, comment
            FROM tasks WHERE id = ?
        ''', (task_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
            
        deadline = datetime.fromisoformat(row[3]) if row[3] else None
        created_at = datetime.fromisoformat(row[5]) if row[5] else None
        completed_at = datetime.fromisoformat(row[6]) if row[6] else None
        
        return {
            'id': row[0],
            'description': row[1],
            'assignee_username': row[2],
            'deadline': deadline,
            'status': row[4],
            'created_at': created_at,
            'completed_at': completed_at,
            'comment': row[7]
        }

# Создаем глобальный экземпляр базы данных
db = Database()