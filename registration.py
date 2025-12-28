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
from typing import Any, Dict, Optional

from config import *
from dataset.database import *

def _now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def _safe_filename(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", s)[:120]


def _looks_like_antibot(html_or_text: str) -> bool:
    t = (html_or_text or "").lower()
    # Типичные маркеры челленджей/антибота
    markers = [
        "cloudflare",
        "/cdn-cgi/",
        "challenge-platform",
        "attention required",
        "verify you are human",
        "just a moment",
        "captcha",
        "turnstile",
        "ddos-guard",
    ]
    return any(m in t for m in markers)
    
def log(text: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {text}\n")
        
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
    retries: int = 2,
    *,
    base_host: str = "https://krs.quizplease.ru",
    timeout_sec: int = 30,
    save_dir: str = "data/quizplease_http",
    extra_cookies: Optional[Dict[str, str]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> dict:
    """
    Регистрирует команду на игру QuizPlease через POST на game-page?id=GAME_ID.
    Возвращает dict:
      ok: bool
      status: int | None
      antibot: bool
      error: str | None
      request_file: str | None
      response_file: str | None
      url: str
    """
    
    os.makedirs(save_dir, exist_ok=True)

    url = f"{base_host}/game-page?id={game_id}"
    stamp = _now_stamp()
    prefix = f"{stamp}__game_{game_id}__{_safe_filename(team_name)}"
    request_path = os.path.join(save_dir, f"{prefix}__request.txt")
    response_path = os.path.join(save_dir, f"{prefix}__response.txt")

    # Поля формы — как в твоём рабочем примере (UrlFetchApp)
    payload = {
        "QpRecord[teamName]": team_name,
        "QpRecord[captainName]": captain_name,
        "QpRecord[email]": email,
        "QpRecord[phone]": phone,
        "QpRecord[count]": str(players_count),
        "QpRecord[comment]": comment or "",
        "QpRecord[game_id]": str(game_id),
    }

    # Базовые заголовки "как браузер" (помогает, но антибот не гарантированно снимет)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.7,en;q=0.6",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": base_host,
        "Referer": url,
        "Connection": "keep-alive",
    }
    if extra_headers:
        headers.update(extra_headers)

    # CookieJar — чтобы GET->POST были в одной сессии
    timeout = aiohttp.ClientTimeout(total=timeout_sec)
    cookie_jar = aiohttp.CookieJar()

    async def _write_request_dump(attempt: int, cookies: Dict[str, str]) -> None:
        dump = {
            "attempt": attempt,
            "url": url,
            "method": "POST",
            "headers": headers,
            "payload": payload,
            "cookies": cookies,
            "ts": stamp,
        }
        with open(request_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(dump, ensure_ascii=False, indent=2))

    async def _write_response_dump(meta: Dict[str, Any], body_text: str) -> None:
        with open(response_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(meta, ensure_ascii=False, indent=2))
            f.write("\n\n--- BODY (first 200000 chars) ---\n\n")
            f.write((body_text or "")[:200000])

    last_error: Optional[str] = None

    for attempt in range(1, retries + 2):  # retries=2 => всего 3 попытки
        try:
            log(f"[quizplease] attempt={attempt} GET {url}")
            async with aiohttp.ClientSession(timeout=timeout, cookie_jar=cookie_jar) as session:
                # Доп. cookies (если ты вручную получил валидную сессию/челлендж пройден в браузере)
                if extra_cookies:
                    session.cookie_jar.update_cookies(extra_cookies, response_url=base_host)
                # 1) GET — чтобы получить cookies/сессию
                async with session.get(url, headers=headers, allow_redirects=True) as r_get:
                    get_text = await r_get.text(errors="ignore")
                    log(f"[quizplease] GET status={r_get.status} len={len(get_text)} final_url={str(r_get.url)}")

                    if _looks_like_antibot(get_text):
                        # Сохраним, чтобы видеть страницу челленджа
                        meta = {
                            "stage": "GET",
                            "status": r_get.status,
                            "final_url": str(r_get.url),
                            "headers": dict(r_get.headers),
                            "antibot": True,
                        }
                        await _write_response_dump(meta, get_text)
                        await _write_request_dump(attempt, {c.key: c.value for c in session.cookie_jar})
                        msg = "Anti-bot/challenge detected on GET (need valid browser cookies/session)."
                        log(f"[quizplease] {msg}")
                        return {
                            "ok": False,
                            "status": r_get.status,
                            "antibot": True,
                            "error": msg,
                            "request_file": request_path,
                            "response_file": response_path,
                            "url": url,
                        }

                # 2) POST — отправка формы
                # Снимем cookies для дампа
                cookies_dict = {c.key: c.value for c in session.cookie_jar}
                await _write_request_dump(attempt, cookies_dict)

                log(f"[quizplease] attempt={attempt} POST {url} payload_keys={list(payload.keys())}")
                async with session.post(url, headers=headers, data=payload, allow_redirects=True) as r_post:
                    body = await r_post.text(errors="ignore")
                    log(f"[quizplease] POST status={r_post.status} len={len(body)} final_url={str(r_post.url)}")

                    antibot = _looks_like_antibot(body)
                    meta = {
                        "stage": "POST",
                        "status": r_post.status,
                        "final_url": str(r_post.url),
                        "headers": dict(r_post.headers),
                        "cookies_after": {c.key: c.value for c in session.cookie_jar},
                        "antibot": antibot,
                    }
                    await _write_response_dump(meta, body)

                    # Критерий успеха.
                    # В твоём GAS-примере проверяли только responseCode.
                    # Здесь: считаем успехом 200/302 и отсутствие anti-bot.
                    ok = (r_post.status in (200, 302, 303)) and not antibot

                    if ok:
                        log(f"[quizplease] SUCCESS game_id={game_id} team='{team_name}' status={r_post.status}")
                        return {
                            "ok": True,
                            "status": r_post.status,
                            "antibot": False,
                            "error": None,
                            "request_file": request_path,
                            "response_file": response_path,
                            "url": url,
                        }

                    # Если антибот на POST
                    if antibot:
                        msg = "Anti-bot/challenge detected on POST (need valid browser cookies/session)."
                        log(f"[quizplease] {msg}")
                        return {
                            "ok": False,
                            "status": r_post.status,
                            "antibot": True,
                            "error": msg,
                            "request_file": request_path,
                            "response_file": response_path,
                            "url": url,
                        }

                    # Иначе — сервер вернул что-то неожиданное
                    last_error = f"Unexpected status/body. status={r_post.status}"
                    log(f"[quizplease] {last_error}")

        except asyncio.TimeoutError:
            last_error = f"Timeout after {timeout_sec}s"
            log(f"[quizplease] ERROR: {last_error}")
        except aiohttp.ClientError as e:
            last_error = f"aiohttp.ClientError: {type(e).__name__}: {e}"
            log(f"[quizplease] ERROR: {last_error}")
        except Exception as e:
            last_error = f"Unhandled: {type(e).__name__}: {e}"
            log(f"[quizplease] ERROR: {last_error}")

        # Backoff перед следующей попыткой
        if attempt < retries + 2:
            sleep_s = 1.5 * attempt
            log(f"[quizplease] retrying in {sleep_s:.1f}s ...")
            await asyncio.sleep(sleep_s)

    return {
        "ok": False,
        "status": None,
        "antibot": False,
        "error": last_error or "Unknown error",
        "request_file": request_path if os.path.exists(request_path) else None,
        "response_file": response_path if os.path.exists(response_path) else None,
        "url": url,
    }

