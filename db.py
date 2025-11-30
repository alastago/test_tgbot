import sqlite3
import os

DB_PATH = os.path.join("data", "database.db")


def get_db():
    os.makedirs("data", exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER UNIQUE,
            name TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            captain_tg_id INTEGER,
            team_name TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER,
            game_id INTEGER
        )
    """)

    return conn


# -----------------------
# USERS
# -----------------------
def add_user(tg_id, name):
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO users (tg_id, name) VALUES (?, ?)", (tg_id, name))
    conn.commit()

def get_user(tg_id):
    conn = get_db()
    cur = conn.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
    return cur.fetchone()



# -----------------------
# TEAMS
# -----------------------
def create_team(captain_tg_id, team_name):
    conn = get_db()
    conn.execute("INSERT INTO teams (captain_tg_id, team_name) VALUES (?, ?)", 
                 (captain_tg_id, team_name))
    conn.commit()

def team_exists(team_name):
    conn = get_db()
    cur = conn.execute("SELECT * FROM teams WHERE team_name = ?", (team_name,))
    return cur.fetchone()



# -----------------------
# GAMES
# -----------------------
def create_game(title):
    conn = get_db()
    conn.execute("INSERT INTO games (title) VALUES (?)", (title,))
    conn.commit()

def get_games():
    conn = get_db()
    cur = conn.execute("SELECT * FROM games")
    return cur.fetchall()



# -----------------------
# PLAYERS REGISTRATION
# -----------------------
def register_to_game(tg_id, game_id):
    conn = get_db()
    conn.execute("INSERT INTO players (tg_id, game_id) VALUES (?, ?)", (tg_id, game_id))
    conn.commit()
