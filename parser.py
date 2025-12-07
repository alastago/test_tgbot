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

def log(text: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {text}\n")

def looks_like_bot_block(html: str) -> bool:
    lower = html.lower()
    checks = [
        "подтвердите, что запросы", "captcha", "вы не робот",
        "verify", "are you human", "requests from your device look like automated"
    ]
    return any(ch in lower for ch in checks)

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
            if tag == "div":
                self._div_stack += 1
            if tag == "div" and "class" in attrs:
                cls = attrs["class"]
                if "h2-game-card" in cls:
                    self.current_field = "title"
                elif "h3" in cls and "date" not in self.current_game:
                    self.current_field = "date"
                elif "schedule-block-info-bar" in cls:
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
                    self.games.append(self.current_game)
                    log(f"Saved game: {self.current_game.get('title')}")
                self.current_game = {}
                self.current_field = None
        else:
            self.current_field = None

    def handle_data(self, data):
        if self.in_game and self.current_field:
            text = data.strip()
            if text:
                prev = self.current_game.get(self.current_field)
                self.current_game[self.current_field] = prev + " " + text if prev else text

async def fetch_games():
    log("Start fetch_games()")
    async with aiohttp.ClientSession() as session:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://quizplease.ru/",
            "Connection": "keep-alive",
        }
        try:
            async with session.get(SCHEDULE_URL, headers=headers, timeout=30) as resp:
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
        time.sleep(CRAWL_DELAY)

        return parser.games
