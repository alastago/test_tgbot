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
    
def _looks_like_yandex_captcha(resp: aiohttp.ClientResponse, body: str) -> bool:
    if resp.headers.get("x-yandex-captcha", "").lower() == "captcha":
        return True
    url = str(resp.url)
    if "/tmgrdfrend/showcaptcha" in url or "/tmgrdfrend/" in url:
        return True
    t = (body or "").lower()
    return ("вы не робот" in t) or ("smartcaptcha" in t) or ("captcha" in t and "yandex" in t)
    
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
    save_dir: str = "data/quizplease_http",
) -> dict:
    os.makedirs(save_dir, exist_ok=True)

    base = "https://krs.quizplease.ru"
    game_url = f"{base}/game-page?id={game_id}"

    stamp = _now_stamp()
    prefix = f"{stamp}__game_{game_id}__{_safe_filename(team_name)}"
    request_path = os.path.join(save_dir, f"{prefix}__request.txt")
    response_path = os.path.join(save_dir, f"{prefix}__response.txt")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/143.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/avif,image/webp,image/apng,*/*;q=0.8,"
                  "application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-RU,en;q=0.9,ru-RU;q=0.8,ru;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Referer": f"{base}/",
    }

    payload = {
        "QpRecord[teamName]": team_name,
        "QpRecord[captainName]": captain_name,
        "QpRecord[email]": email,
        "QpRecord[phone]": phone,
        "QpRecord[count]": str(players_count),
        "QpRecord[comment]": comment or "",
        "QpRecord[game_id]": str(game_id),
    }

    async def dump(req_meta: Dict[str, Any], resp_meta: Dict[str, Any], body: str) -> None:
        with open(request_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(req_meta, ensure_ascii=False, indent=2))
        with open(response_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(resp_meta, ensure_ascii=False, indent=2))
            f.write("\n\n--- BODY (first 200000 chars) ---\n\n")
            f.write((body or "")[:200000])

    last_error: Optional[str] = None

    for attempt in range(1, retries + 2):
        jar = aiohttp.CookieJar()
        # ключевое отличие: city cookie как у тебя
        jar.update_cookies({"city": "krs"})

        try:
            log(f"[reg] attempt={attempt} start, game_id={game_id}")

            async with aiohttp.ClientSession(cookie_jar=jar, headers=headers) as session:
                # 1) прогрев /
                log("[reg] warmup GET /")
                async with session.get(f"{base}/", timeout=20, allow_redirects=True) as r0:
                    t0 = await r0.text(errors="ignore")
                    log(f"[reg] warmup status={r0.status} url={str(r0.url)} len={len(t0)}")

                    if _looks_like_yandex_captcha(r0, t0):
                        await dump(
                            {"attempt": attempt, "stage": "WARMUP", "url": f"{base}/", "headers": headers, "cookies": {"city":"krs"}},
                            {"stage": "WARMUP", "status": r0.status, "final_url": str(r0.url), "headers": dict(r0.headers), "captcha": True},
                            t0,
                        )
                        return {"ok": False, "antibot": True, "status": r0.status, "error": "Captcha on warmup", "captcha_url": str(r0.url),
                                "request_file": request_path, "response_file": response_path}

                await asyncio.sleep(random.uniform(1.5, 3.5))

                # 2) GET game-page
                log(f"[reg] GET game-page {game_url}")
                async with session.get(game_url, timeout=25, allow_redirects=True) as r1:
                    t1 = await r1.text(errors="ignore")
                    log(f"[reg] game-page status={r1.status} url={str(r1.url)} len={len(t1)}")

                    if _looks_like_yandex_captcha(r1, t1):
                        await dump(
                            {"attempt": attempt, "stage": "GET_GAME", "url": game_url, "headers": headers, "cookies": {c.key: c.value for c in session.cookie_jar}},
                            {"stage": "GET_GAME", "status": r1.status, "final_url": str(r1.url), "headers": dict(r1.headers), "captcha": True},
                            t1,
                        )
                        return {"ok": False, "antibot": True, "status": r1.status, "error": "Captcha on game-page", "captcha_url": str(r1.url),
                                "request_file": request_path, "response_file": response_path}

                await asyncio.sleep(random.uniform(0.8, 1.8))

                # 3) POST регистрация (важно: referer на game-page)
                post_headers = dict(headers)
                post_headers["Referer"] = game_url
                post_headers["Content-Type"] = "application/x-www-form-urlencoded"

                log(f"[reg] POST register {game_url}")
                async with session.post(game_url, headers=post_headers, data=payload, timeout=30, allow_redirects=True) as r2:
                    t2 = await r2.text(errors="ignore")
                    log(f"[reg] POST status={r2.status} url={str(r2.url)} len={len(t2)}")

                    await dump(
                        {"attempt": attempt, "stage": "POST", "url": game_url, "headers": post_headers,
                         "payload": payload, "cookies": {c.key: c.value for c in session.cookie_jar}},
                        {"stage": "POST", "status": r2.status, "final_url": str(r2.url), "headers": dict(r2.headers),
                         "captcha": _looks_like_yandex_captcha(r2, t2)},
                        t2,
                    )

                    if _looks_like_yandex_captcha(r2, t2):
                        return {"ok": False, "antibot": True, "status": r2.status, "error": "Captcha on POST",
                                "captcha_url": str(r2.url), "request_file": request_path, "response_file": response_path}

                    if r2.status in (200, 302, 303):
                        return {"ok": True, "antibot": False, "status": r2.status, "error": None,
                                "request_file": request_path, "response_file": response_path}

                    last_error = f"Unexpected status {r2.status}"
                    log(f"[reg] {last_error}")

        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            log(f"[reg] ERROR {last_error}")

        if attempt < retries + 2:
            delay = 1.5 * attempt + random.uniform(0.2, 0.8)
            log(f"[reg] retry in {delay:.1f}s")
            await asyncio.sleep(delay)

    return {"ok": False, "antibot": False, "status": None, "error": last_error,
            "request_file": request_path if os.path.exists(request_path) else None,
            "response_file": response_path if os.path.exists(response_path) else None}
