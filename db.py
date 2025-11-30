import sqlite3

def get_db():
    conn = sqlite3.connect("database.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
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
    cur = conn.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
    return cur.fetchone()
