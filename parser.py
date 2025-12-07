# parser.py

import aiohttp
from html.parser import HTMLParser
import traceback
from datetime import datetime

from config import SCHEDULE_URL, LOGFILE, HTML_DUMP


def log(text: str):
    """Пишем лог в /tmp/parser_quizplease.log"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {text}\n")


class GamesParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.games = []
        self.in_game = False
        self.current_game = {}
        self.current_field = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        # === Начало игры ===
        if tag == "div" and "class" in attrs and "schedule-column" in attrs["class"]:
            self.in_game = True
            self.current_game = {"id": attrs.get("id")}
            log(f"Найдена игра id={attrs.get('id')}")

        if not self.in_game:
            return

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

        if tag == "a" and "href" in attrs:
            if attrs["href"].startswith("/game-page"):
                self.current_game["url"] = "https://quizplease.ru" + attrs["href"]

    def handle_endtag(self, tag):
        if self.in_game and tag == "div":
            if "title" in self.current_game:
                self.games.append(self.current_game)
                log(f"Игра записана: {self.current_game}")

        self.current_field = None

    def handle_data(self, data):
        if not self.in_game or not self.current_field:
            return

        text = data.strip()
        if text:
            self.current_game[self.current_field] = text


async def fetch_games():
    log("Старт парсера")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(SCHEDULE_URL, timeout=30) as response:
                html = await response.text()

        # Дамп HTML в файл
        with open(HTML_DUMP, "w", encoding="utf-8") as f:
            f.write(html)

        log("HTML сохранён в дамп")
        log(f"Размер HTML: {len(html)} символов")

        parser = GamesParser()
        parser.feed(html)

        log(f"Парсер завершён. Найдено игр: {len(parser.games)}")

        return parser.games

    except Exception as e:
        error_msg = f"Ошибка парсера: {e}\n{traceback.format_exc()}"
        log(error_msg)
        return []
