import aiohttp
import asyncio
from datetime import datetime
from config import *
from dataset.database import *
import re
import json
import urllib.parse
import random
import time
from html.parser import HTMLParser


def log(text: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {text}\n")

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
) -> bool:
    """
    Регистрирует команду на игру QuizPlease
    Возвращает True при успехе
    """

    url = "https://krs.quizplease.ru/ajax/save-record"

    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "User-Agent": random.choice(USER_AGENTS),
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://krs.quizplease.ru/schedule",
        "Origin": "https://krs.quizplease.ru",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
    }

    # custom_fields_values — оставляем как в браузере
    custom_fields = [
        {
            "name": "d2302012-a826-49ab-904f-ee98548c7226",
            "type": "text",
            "label": "ID/номер в Telegram",
            "placeholder": "",
            "value": ""
        }
    ]

    payload = {
        "record-from-form": "1",
        "QpRecord[teamName]": team_name,
        "QpRecord[captainName]": captain_name,
        "QpRecord[email]": email,
        "QpRecord[phone]": phone,
        "QpRecord[count]": str(players_count),
        "QpRecord[custom_fields_values]": json.dumps(custom_fields, ensure_ascii=False),
        "QpRecord[comment]": comment,
        "QpRecord[game_id]": str(game_id),
        "QpRecord[reserve]": "0",
        "reservation": "",
        "QpRecord[site_content_id]": "",
        "have_cert": "1",
        "certificates[]": "",
        "QpRecord[payment_type]": "2",
        "QpRecord[is_agreed_to_mailing]": "1",
    }

    encoded_payload = urllib.parse.urlencode(payload)

    log(f"Регистрация команды '{team_name}' на игру {game_id}")

    timeout = aiohttp.ClientTimeout(total=20)

    async with aiohttp.ClientSession(
        headers=headers,
        timeout=timeout,
        cookie_jar=aiohttp.CookieJar()
    ) as session:
        try:
            async with session.post(url, data=encoded_payload) as response:
                log(f"HTTP статус: {response.status}")

                if response.status != 200:
                    log("Ошибка HTTP при регистрации")
                    return False

                data = await response.json()
                log(f"Ответ сервера: {data}")

                if data.get("success"):
                    log("✅ Команда успешно зарегистрирована")
                    return True

                log("❌ Сервер вернул success=false")
                return False

        except aiohttp.ClientError as e:
            log(f"❌ Ошибка сети: {e}")
            return False
        except Exception as e:
            log(f"❌ Неизвестная ошибка: {e}")
            return False
