import sqlite3
from datetime import datetime
from config import DB_PATH, LOGFILE

def log(text: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(f"[DB {ts}] {text}\n")
    
    conn.commit()
    conn.close()
    log("DB initialized")
    
# ==========================
# ИНИЦИАЛИЗАЦИЯ БАЗЫ
# ==========================
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

# ==========================
# ФУНКЦИЯ: получить ID существующих игр
# ==========================

def get_existing_ids(game_ids: list) -> set:
    if not game_ids:
        return set()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    q_marks = ",".join("?" for _ in game_ids)
    cur.execute(f"SELECT id FROM games WHERE id IN ({q_marks})", game_ids)
    rows = cur.fetchall()

    conn.close()

    return {row[0] for row in rows}


# ==========================
# ПРОВЕРКА СУЩЕСТВОВАНИЯ ИГРЫ
# ==========================

def filter_new_games(parsed_games: list) -> list:
    """
    Возвращает игры, которых нет в базе.
    """

    ids = [int(g["id"]) for g in parsed_games if g.get("id")]

    log(f"Received {len(parsed_games)} games, checking IDs: {len(ids)}")

    existing_ids = get_existing_ids(ids)

    log(f"Existing in DB: {len(existing_ids)}")

    new_games = [g for g in parsed_games if int(g["id"]) not in existing_ids]

    log(f"New games found: {len(new_games)}")

    return new_games    
    
# ==========================
# ФУНКЦИЯ: массовая вставка новых игр
# ==========================

def insert_games_bulk(games: list):
    if not games:
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    insert_data = [
        (
            int(g.get("id")),
            g.get("date"),
            g.get("title"),
            g.get("bar"),
            g.get("price"),
            g.get("url"),
            datetime.now().isoformat()
        )
        for g in games
    ]

    cur.executemany("""
        INSERT INTO games (id, date, title, bar, price, url, added_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, insert_data)

    conn.commit()
    conn.close()

    log(f"Inserted {len(games)} games")
