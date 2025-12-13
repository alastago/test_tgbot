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
        
def save_dump(prefix: str, data: dict | str):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{DUMP_DIR}/{prefix}_{ts}.json"

    try:
        with open(filename, "w", encoding="utf-8") as f:
            if isinstance(data, str):
                f.write(data)
            else:
                json.dump(data, f, ensure_ascii=False, indent=2)
        log(f"Дамп сохранён: {filename}")
    except Exception as e:
        log(f"❌ Ошибка сохранения дампа {filename}: {e}")


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
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
    comment: str = "Автозапись"
) -> dict:

    url = "https://krs.quizplease.ru/ajax/save-record"
    referer = "https://krs.quizplease.ru/schedule"

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

    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ru,en;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": referer,
        "Origin": "https://krs.quizplease.ru",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/143.0.0.0 Safari/537.36"
        )
    }

    log(f"▶ Регистрация команды '{team_name}' на игру {game_id}")

    cookie_jar = aiohttp.CookieJar(unsafe=True)

    async with aiohttp.ClientSession(
        headers=headers,
        cookie_jar=cookie_jar
    ) as session:

        # 🔹 предварительный GET — сервер часто кладёт нужные cookies
        log("GET /schedule для получения cookies")
        async with session.get(referer) as r:
            log(f"GET /schedule status={r.status}")
            raw_text = await r.text()
            save_dump("quizplease_schedule_response", raw_text)
            
        encoded_payload = urlencode(payload)

        save_dump(
            prefix="quizplease_request",
            data={
                "url": url,
                "headers": headers,
                "payload": payload
            }
        )

        log("POST /ajax/save-record")
        async with session.post(
            url,
            data=encoded_payload
        ) as resp:

            raw_text = await resp.text()
            log(f"POST status={resp.status}")
            save_dump("quizplease_raw_response", raw_text)

            try:
                json_response = await resp.json()
            except Exception as e:
                log(f"❌ Ошибка парсинга JSON: {e}")
                raise

    save_dump("quizplease_parsed_response", json_response)

    if json_response.get("success"):
        log("✅ Успешная регистрация")
    else:
        log(f"❌ Ошибка регистрации: {json_response}")

    return json_response
