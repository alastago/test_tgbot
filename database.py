import sqlite3

def get_db():
    conn = sqlite3.connect("bot.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS players (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        team_id INTEGER
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS teams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        email TEXT,
        phone TEXT,
        captainName TEXT,
        captain_id INTEGER
    );
    """) 

    cur.execute("""
    CREATE TABLE IF NOT EXISTS games (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        date TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS team_games (
        team_id INTEGER,
        game_id INTEGER,
        PRIMARY KEY (team_id, game_id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS player_games (
        user_id INTEGER,
        game_id INTEGER,
        PRIMARY KEY (user_id, game_id)
    );
    """)

    conn.commit()
    conn.close()
