import sqlite3
import os

# путь к базе в подпапке data
DB_PATH = os.path.join("data", "database.db")

def get_db():
    # если папки data нет — создадим
    os.makedirs("data", exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER UNIQUE,
            name TEXT
        )
    """)
    return conn

def add_user(tg_id, name):
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO users (tg_id, name) VALUES (?, ?)", (tg_id, name))
    conn.commit()

def get_user(tg_id):
    conn = get_db()
    cursor = conn.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
    return cursor.fetchone()
