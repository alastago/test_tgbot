import aiohttp
import asyncio
from datetime import datetime
from config import *
from dataset.database import *


def log(text: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {text}\n")


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
):
    url = f"https://quizplease.ru/game-page?id={game_id}"
    base_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Upgrade-Insecure-Requests": "1",
        "Referer": url,
        "Origin": "https://quizplease.ru",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-User": "?1",
        "Sec-Fetch-Dest": "document",
    }
    
    async with aiohttp.ClientSession() as session:
        # ---------- 1. GET HTML для получения cookie и CSRF ----------
        async with session.get(url, headers=base_headers) as r:
            log(f"GET page -> {r.status}")
            html = await r.text()
            cookies = session.cookie_jar.filter_cookies("https://quizplease.ru")
            log(f"Полученные куки: {cookies}")

        # ---------- 2. Достаём CSRF ----------
        m = re.search(r'name="csrf-token" content="(.+?)"', html)
        csrf = m.group(1) if m else None
        log(f"CSRF = {csrf}")

        if not csrf:
            log("❌ CSRF не найден — 100% будет капча")
        
        # ---------- 3. Формируем POST ----------
        post_headers = base_headers.copy()
        post_headers["Content-Type"] = "application/x-www-form-urlencoded"
        
        data = {
            "_csrf": csrf,
            "record-from-form": "1",
            "QpRecord[teamName]": team_name,
            "QpRecord[captainName]": captain_name,
            "QpRecord[email]": email,
            "QpRecord[phone]": phone,
            "QpRecord[count]": str(players_count),
            "QpRecord[comment]": comment,
            "QpRecord[custom_fields_values]": "[]",
            "QpRecord[first_time]": "0",
            "certificates[]": "",
            "QpRecord[is_agreed_to_mailing]": "1",
            "QpRecord[game_id]": str(game_id),
            "QpRecord[max_people_active]": "",
            "reservation": "",
            "QpRecord[site_content_id]": "",
        }
         # ---------- 4. Делаем POST ----------
        try:
            async with session.post(url, data=data, headers=post_headers, allow_redirects=False) as resp:
                log(f"POST -> {resp.status}")
                log(f"Location: {resp.headers.get('Location')}")
             # Проверяем success
                if "success=" in location:
                    code = location.split("success=")[1]
                    code_map = {
                        "1": "Спасибо, что записались! (Успех)",
                        "2": "Упс! Что-то пошло не так. (Запись не выполнена)",
                        "3": "Команда с таким названием уже зарегистрирована на один из дней пакета. (Запись не выполнена)",
                        "4": "Вы поставлены в очередь на регистрацию. (Запись выполнена, вид записи неизвестен)",
                        "5": "Отлично! Вы записаны в резерв. (Запись выполнена в резерв)",
                        "6": "Упс, места на игру уже закончились. (Запись не выполнена)"
                    }
                    message = code_map.get(code, f"Неизвестный код success={code}")
                    log(f"Результат регистрации: {message}")
                    return code, message
                else:
                    text = await resp.text()
                    log(f"Регистрация не прошла, нет success в Location - {location}. Ответ сервера: {text[:200]}...")
                    return None, "Нет success в Location"
        except Exception as e:
            log(f"Ошибка при регистрации команды: {e}")
            return None, str(e)
