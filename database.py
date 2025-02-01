# database.py
import sqlite3
import os

# Инициализация базы данных
def init_db():
    db_file = "users.db"
    if not os.path.exists(db_file):  # Если файла базы данных нет, создаем её
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,         -- ID пользователя (уникальный)
                username TEXT,                  -- Имя пользователя в Telegram (@username)
                first_name TEXT                 -- Имя пользователя (first_name)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS download_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                video_title TEXT,
                video_url TEXT,
                file_path TEXT,
                download_date TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)

        conn.commit()
        conn.close()
        print("✅ База данных создана!")
    else:
        print("⚙️ База данных уже существует.")

# Добавление нового пользователя
def add_user(user_id, username, first_name):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO users (id, username, first_name) 
        VALUES (?, ?, ?)
    """, (user_id, username, first_name))
    conn.commit()
    conn.close()

# Добавление истории скачивания
def add_download_to_history(user_id, video_title, video_url, file_path):
    from datetime import datetime
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO download_history (user_id, video_title, video_url, file_path, download_date)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, video_title, video_url, file_path, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()