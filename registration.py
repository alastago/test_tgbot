import aiohttp
import asyncio
import re
import json
import urllib.parse
import random
import time
from html.parser import HTMLParser
import os
from datetime import datetime

from config import *
from dataset.database import *


def log(text: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {text}\n")
        
def dump_file(prefix: str, content, ext="json"):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = f"{DUMP_DIR}/{prefix}_{ts}.{ext}"

    try:
        with open(path, "w", encoding="utf-8") as f:
            if isinstance(content, str):
                f.write(content)
            else:
                json.dump(content, f, ensure_ascii=False, indent=2)
        log(f"📝 dump → {path}")
    except Exception as e:
        log(f"❌ dump error: {e}")

def dump_cookies(session, label: str):
    cookies = {
        c.key: c.value
        for c in session.cookie_jar
    }
    dump_file(f"quizplease_cookies_{label}", cookies)


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.1 Safari/605.1.15",
]

# --------------------------
#Автозапись команд на новые игры
# --------------------------

async def auto_register_teams():
    """
    Команды с auto_signup=1 автоматически записываются на все новые игры.
    """
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM teams WHERE auto_signup=1")
    teams = cur.fetchall()

    if not teams:
        return

    cur.execute("SELECT id FROM games ORDER BY id DESC")
    games = cur.fetchall()

    for team in teams:
        team_id = team["id"]
        team_name = team["name"]
        captain_name = team["captainName"] or "-"
        email = team["email"] or "-"
        phone = team["phone"] or "+"
        whitelist = (team["whitelist"] or "").split(",")  # ключевые слова белого списка
        blacklist = (team["blacklist"] or "").split(",")  # ключевые слова черного списка
        # Получаем игры, на которые команда ещё не записана
        cur.execute("""
            SELECT * FROM games g
            WHERE g.id NOT IN (SELECT game_id FROM team_games WHERE team_id=?)
        """, (team_id,))
        available_games = cur.fetchall()
        for g in available_games:
            title = g["title"]

            # Проверка whitelist / blacklist
            if whitelist and not any(w.lower() in title.lower() for w in whitelist):
                continue  # пропускаем, если есть белый список и нет совпадений
            if blacklist and any(b.lower() in title.lower() for b in blacklist):
                continue  # пропускаем, если есть черный список и есть совпадения

            # Пытаемся зарегистрировать
            code, message = await register_team_on_quizplease(
                game_id=g["id"],
                team_name=team_name,
                captain_name=captain_name,
                email=email,
                phone=phone,
                players_count=5,
                comment="Автозапись"
            )
            if code in ("1", "4", "5"):  # успешные варианты
                # Запись в БД о регистрации команды на игру
                cur.execute(
                    "INSERT OR IGNORE INTO team_games (team_id, game_id) VALUES (?, ?)",
                    (team_id, g["id"])
                )
                conn.commit()
            
            else:
                log(f"Регистрация команды '{team_name}' на игру '{title}' не удалась: {message}")

    conn.close()
    log("Автозапись команд выполнена")

# --------------------------
#запись команды на игру
# --------------------------  
async def register_team_on_quizplease(
    game_id: int,
    team_name: str,
    captain_name: str,
    email: str,
    phone: str,
    players_count: int = 5,
    comment: str = "Автозапись",
    retries: int = 2
) -> dict:

    base_url = "https://krs.quizplease.ru"
    schedule_url = f"{base_url}/schedule"
    game_page_url = f"{base_url}/game-page?id={game_id}"
    post_url = f"{base_url}/ajax/save-record"
    
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ru,en;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": base_url,
        "Referer": base_url,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/143.0.0.0 Safari/537.36"
        )
    }

    payload = {
        "record-from-form": "1",
        "QpRecord[teamName]": team_name,
        "QpRecord[captainName]": captain_name,
        "QpRecord[email]": email,
        "QpRecord[phone]": phone,
        "QpRecord[count]": str(players_count),
        "QpRecord[comment]": comment,
        "QpRecord[game_id]": str(game_id),
        "QpRecord[reserve]": "0",
        "reservation": "",
        "QpRecord[site_content_id]": "",
        "have_cert": "1",
        "certificates[]": "",
        "QpRecord[payment_type]": "1",
        "QpRecord[surcharge]": "1",
        "QpRecord[is_agreed_to_mailing]": "1",
        "QpRecord[custom_fields_values]": (
            '[{"name":"494837f9-ed38-42d0-b923-8beb3f324fa9",'
            '"type":"text","label":"ID/номер в Telegram",'
            '"placeholder":"","value":"-"}]'
        )
    }

    dump_file("quizplease_request", payload)

    cookie_jar = aiohttp.CookieJar(unsafe=True)

    async with aiohttp.ClientSession(
        headers=headers,
        cookie_jar=cookie_jar
    ) as session:

        # 🔥 1. Прогрев: schedule
        log("GET /schedule")
        async with session.get(schedule_url) as r:
            log(f"/schedule status={r.status}")
        dump_cookies(session, "after_schedule")
        raw = await r.text()
        dump_file("quizplease_schedule_response", raw, ext="txt")
        # 🔥 2. Прогрев: game-page (КЛЮЧЕВО)
        log(f"GET /game-page?id={game_id}")
        async with session.get(game_page_url) as r:
            log(f"/game-page status={r.status}")
        dump_cookies(session, "after_game_page")

        encoded_payload = urlencode(payload)

        for attempt in range(1, retries + 2):
            log(f"POST /ajax/save-record (attempt {attempt})")

            async with session.post(
                post_url,
                data=encoded_payload
            ) as resp:

                raw = await resp.text()
                dump_file("quizplease_raw_response", raw, ext="txt")

                try:
                    data = await resp.json()
                except Exception:
                    log("❌ JSON parse failed")
                    raise

                dump_file("quizplease_parsed_response", data)

                if data.get("success"):
                    log("✅ Успешная регистрация")
                    return data

                log(f"⚠ Неуспех: {data}")

        raise RuntimeError("❌ Не удалось зарегистрировать команду после retry")
