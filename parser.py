
# parser.py

import aiohttp
from html.parser import HTMLParser
from config import SCHEDULE_URL

URL = SCHEDULE_URL

class GameHTMLParser(HTMLParser):
    """
    Простой HTML парсер для блока <div class="schedule-column" id="...">
    """

    def __init__(self):
        super().__init__()
        self.games = []
        self.in_game_block = False
        self.current_game = {}
        self.current_tag = ""
        self.buffer = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        # Блок игры
        if tag == "div" and "class" in attrs and "schedule-column" in attrs["class"]:
            self.in_game_block = True
            self.current_game = {"id": attrs.get("id")}

        if not self.in_game_block:
            return

        # Запоминаем текущий тег
        if tag in ["div", "a", "img"]:
            self.current_tag = attrs.get("class", "")

        # Ловим картинку
        if tag == "img" and self.in_game_block:
            self.current_game["image"] = attrs.get("src")

        # Ловим ссылку
        if tag == "a" and self.in_game_block:
            href = attrs.get("href")
            if href and href.startswith("/"):
                self.current_game["url"] = "https://quizplease.ru" + href

    def handle_endtag(self, tag):
        if self.in_game_block and tag == "div":
            if self.current_game and self.current_game.get("title"):
                self.games.append(self.current_game)
            self.in_game_block = False
            self.current_game = {}
            self.buffer = ""

    def handle_data(self, data):
        if not self.in_game_block:
            return

        text = data.strip()
        if not text:
            return

        # Анализируем данные в зависимости от класса div
        if "game-title" in self.current_tag:
            self.current_game["title"] = text

        elif "game-date" in self.current_tag:
            self.current_game["date"] = text

        elif "game-bar-title" in self.current_tag:
            self.current_game["bar"] = text

        elif "game-price" in self.current_tag:
            self.current_game["price"] = text

        elif "game-type" in self.current_tag:
            self.current_game["type"] = text


async def fetch_games():
    async with aiohttp.ClientSession() as session:
        async with session.get(URL) as response:
            html_text = await response.text()

    parser = GameHTMLParser()
    parser.feed(html_text)

    return parser.games
