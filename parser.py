# parser.py

import aiohttp
import asyncio
import random
import time
from html.parser import HTMLParser
from datetime import datetime
from config import SCHEDULE_URL, HTML_DUMP, LOGFILE


# =========================
# Заголовки как в браузере
# =========================


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.1 Safari/605.1.15",
]

CRAWL_DELAY = 10  # из robots.txt

MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12
}

def log(text: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {text}\n")

async def warmup_session(session, headers):
    log("Session warmup: GET /")
    async with session.get(
        "https://krs.quizplease.ru/",
        headers=headers,
        timeout=20
    ) as resp:
        await resp.text()
        
def looks_like_bot_block(html: str) -> bool:
    lower = html.lower()
    checks = [
        "подтвердите, что запросы", "captcha", "вы не робот",
        "verify", "are you human", "requests from your device look like automated"
    ]
    return any(ch in lower for ch in checks)

def parse_datetext_to_datetime(datetext: str):
    """
    datetext: '10 декабря, Среда в 19:30'
    Возвращает datetime. Если дата уже прошла, переносим на следующий год.
    """
    try:
        now = datetime.now()

        # отделяем дату от времени
        date_part, time_part = datetext.rsplit("в", 1)
        date_part = date_part.strip()  # '10 декабря, Среда'
        time_part = time_part.strip()  # '19:30'

        # извлекаем день и месяц
        day_str, month_str, *_ = date_part.replace(",", "").split()
        day = int(day_str)
        month = MONTHS[month_str.lower()]

        # извлекаем часы и минуты
        hour, minute = map(int, time_part.split(":"))

        # создаем datetime с текущим годом
        dt = datetime(year=now.year, month=month, day=day, hour=hour, minute=minute)

        # если дата уже прошла, переносим на следующий год
        if dt < now:
            dt = datetime(year=now.year + 1, month=month, day=day, hour=hour, minute=minute)

        return dt

    except Exception as e:
        log(f"Failed to parse datetext '{datetext}': {e}")
        return None




class GamesParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.games = []
        self.in_game = False
        self.current_game = {}
        self.current_field = None
        self._div_stack = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div" and "class" in attrs and "schedule-column" in attrs["class"]:
            self.in_game = True
            self._div_stack = 1
            self.current_game = {"id": attrs.get("id")}
            log(f"Found schedule-column id={attrs.get('id')}")
            return
            
        if self.in_game:
            if self.current_field == "bar" and tag == "a":
                # пропускаем ссылки “Где это?”
                return
            
            if tag == "div":
                self._div_stack += 1
            if tag == "div" and "class" in attrs:
                cls = attrs["class"]
                if "h2-game-card" in cls:
                    self.current_field = "title"
                elif "h3" in cls or cls.strip() == "techtext":
                    self.current_field = "datetext"
                elif "schedule-block-info-bar" in cls or "techtext techtext-halfwhite" in cls:
                    self.current_field = "bar"
                elif "price" in cls:
                    self.current_field = "price"
                else:
                    self.current_field = None
            if tag == "a" and "href" in attrs:
                href = attrs["href"]
                # не посещаем /game-page (Disallow)
                if href.startswith("/game-page"):
                    self.current_game["url"] = "https://quizplease.ru" + href

    def handle_endtag(self, tag):
        if self.in_game and tag == "div":
            self._div_stack -= 1
            if self._div_stack <= 0:
                self.in_game = False
                if "title" in self.current_game:
                    if "datetext" in self.current_game:
                        self.current_game["date"] = parse_datetext_to_datetime(self.current_game["datetext"])
                    self.games.append(self.current_game)
                    log(f"Saved game: {self.current_game.get('title')}")
                   
                self.current_game = {}
                self.current_field = None
        else:
            self.current_field = None

    def handle_data(self, data):
        if self.in_game and self.current_field:
            text = data.strip()
            if not text:
                return
    
            if self.current_field == "bar":
                # удаляем лишнее
                if text in ("Информация о площадке", "Где это?"):
                    return
                text = text.replace("Информация о площадке", "")
                text = text.replace("Где это?", "")
                text = text.strip()
    
            prev = self.current_game.get(self.current_field)
            self.current_game[self.current_field] = (prev + " " + text).strip() if prev else text

async def fetch_games():
    log("Start fetch_games()")
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
        
            "Referer": "https://krs.quizplease.ru/",
    }
    jar = aiohttp.CookieJar()
    jar.update_cookies({
        "city": "krs",   # 👈 обязательно
    })
    async with aiohttp.ClientSession(
        cookie_jar=jar,
        headers=headers
    ) as session:
        try:
            # 1️⃣ прогрев — главная страница
            log("Warmup: GET /")
            async with session.get(
                "https://krs.quizplease.ru/",
                timeout=20
            ) as resp:
                await resp.text()
    
            await asyncio.sleep(random.uniform(1.5, 3.5))
            # 2️⃣ реальный запрос расписания
            log("Fetching /schedule")
            async with session.get(SCHEDULE_URL, timeout=30) as resp:
                html = await resp.text()
                status = resp.status
        except Exception as e:
            log(f"HTTP error: {e}")
            return []

        log(f"HTTP status={status}, length={len(html)}")

        # сохраняем дамп
        try:
            with open(HTML_DUMP, "w", encoding="utf-8") as f:
                f.write(f"<!-- fetched: {datetime.utcnow().isoformat()} UTC -->\n")
                f.write(html)
            log(f"Saved HTML dump: {HTML_DUMP}")
        except Exception as e:
            log(f"Failed saving HTML dump: {e}")

        # проверка на блокировку/капчу
        if status in (403, 429) or looks_like_bot_block(html):
            log("Detected bot-block/captcha, aborting parse")
            return []

        # парсим страницу
        parser = GamesParser()
        parser.feed(html)
        log(f"Parsed games count: {len(parser.games)}")

        # соблюдаем Crawl-delay
        log(f"Sleeping {CRAWL_DELAY}s to respect robots.txt")
        await asyncio.sleep(CRAWL_DELAY)

        return parser.games



