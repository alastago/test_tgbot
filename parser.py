
# parser.py

import aiohttp
from html.parser import HTMLParser

# parser.py

import aiohttp
from html.parser import HTMLParser
from config import SCHEDULE_URL

URL = SCHEDULE_URL


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

        if not self.in_game:
            return

        # Название игры
        if tag == "div" and "class" in attrs:
            class_str = attrs["class"]

            if "h2-game-card" in class_str:
                self.current_field = "title"

            elif "h3-mb10" in class_str or "h3-green" in class_str:
                self.current_field = "date"

            elif "schedule-block-info-bar" in class_str:
                self.current_field = "bar"

            elif "price" in class_str:
                self.current_field = "price"

        # Ссылка на игру:
        if tag == "a" and "href" in attrs:
            if attrs["href"].startswith("/game-page"):
                self.current_game["url"] = "https://quizplease.ru" + attrs["href"]

    def handle_endtag(self, tag):
        # Конец блока игры
        if self.in_game and tag == "div":
            # Если игра заполнена — сохраняем
            if "title" in self.current_game:
                self.games.append(self.current_game)

        self.current_field = None

    def handle_data(self, data):
        if not self.in_game or not self.current_field:
            return

        text = data.strip()
        if not text:
            return

        # Записываем значение
        self.current_game[self.current_field] = text


async def fetch_games():
    async with aiohttp.ClientSession() as session:
        async with session.get(URL) as response:
            html = await response.text()

    parser = GamesParser()
    parser.feed(html)

    return parser.games
