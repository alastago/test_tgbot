import sqlite3
from datetime import datetime
from config import DB_PATH, LOGFILE

def log(text: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(f"[DB {ts}] {text}\n")
    
# ==========================
# ИНИЦИАЛИЗАЦИЯ БАЗЫ
# ==========================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS players (
        user_id INTEGER PRIMARY KEY,
        username TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS teams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        email TEXT,
        phone TEXT,
        captainName TEXT,
        captain_id INTEGER,
        auto_signup INTEGER DEFAULT 0,
        signup_mode TEXT DEFAULT 'white',
        keywords TEXT DEFAULT ''
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS games (
        id INTEGER PRIMARY KEY,
        datetext TEXT,
        date DATETIME,
        title TEXT,
        bar TEXT,
        price TEXT,
        url TEXT,
        added_at DATETIME
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS team_games (
        team_id INTEGER,
        game_id INTEGER,
        signup_status INTEGER DEFAULT 0,
        notification_status INTEGER DEFAULT 0,
        PRIMARY KEY (team_id, game_id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS player_teams (
        user_id INTEGER,
        team_id INTEGER,
        is_capitan INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, team_id)
    );
    """)
    conn.commit()
    conn.close()
    log("DB initialized")
    
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
    log("insert_games_bulk() called")

    if not games:
        log("No games to insert — exiting")
        return

    log(f"Trying to insert {len(games)} games")
    log(f"DB_PATH = {DB_PATH}")

    # Проверяем что файл базы есть
    import os
    log(f"DB file exists: {os.path.exists(DB_PATH)}")

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # Логируем структуру таблицы games
        cur.execute("PRAGMA table_info(games)")
        table_info = cur.fetchall()
        log(f"Table structure: {table_info}")

        insert_data = []
        for g in games:
            try:
                now = datetime.now().isoformat(sep=' ', timespec='milliseconds')
                item = (
                    int(g.get("id")),
                    g.get("datetext"),
                    "",
                    g.get("title"),
                    g.get("bar"),
                    g.get("price"),
                    g.get("url"),
                    now
                )
                insert_data.append(item)
            except Exception as e:
                log(f"Error preparing game for insert: {g}, error: {e}")

        log(f"Prepared {len(insert_data)} rows for insert")
        if insert_data:
            log(f"Sample row: {insert_data[0]}")

        # Выполнение запроса
        cur.executemany("""
            INSERT INTO games (id, datetext, date, title, bar, price, url, added_at)
            VALUES (?, ?, ?, ?, ?, ?, ?,?)
        """, insert_data)

        conn.commit()
        log(f"Successfully inserted {len(insert_data)} games into DB")

    except sqlite3.Error as e:
        log(f"SQLite error during insert_games_bulk: {e}")

    except Exception as e:
        log(f"Unexpected error in insert_games_bulk: {e}")

    finally:
        if conn:
            conn.close()
            log("DB connection closed")
