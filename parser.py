# parser.py

import aiohttp
from lxml import html
from config import SCHEDULE_URL

URL = SCHEDULE_URL

async def fetch_games():
    async with aiohttp.ClientSession() as session:
        async with session.get(URL) as response:
            page = await response.text()

    tree = html.fromstring(page)

    # Каждый блок игры — div.schedule-column
    game_blocks = tree.xpath('//div[contains(@class, "schedule-column")]')

    games = []

    for g in game_blocks:
        game_id = g.attrib.get("id", "")

        # Название игры
        title = g.xpath('.//div[contains(@class, "game-title")]/text()')
        title = title[0].strip() if title else None

        # Дата
        date = g.xpath('.//div[contains(@class, "game-date")]/text()')
        date = date[0].strip() if date else None

        # Бар
        bar = g.xpath('.//div[contains(@class, "game-bar-title")]/text()')
        bar = bar[0].strip() if bar else None

        # Цена
        price = g.xpath('.//div[contains(@class, "game-price")]/text()')
        price = price[0].strip() if price else None

        # Тип
        game_type = g.xpath('.//div[contains(@class, "game-type")]/text()')
        game_type = game_type[0].strip() if game_type else None

        # Картинка
        img = g.xpath('.//img/@src')
        img = img[0] if img else None

        # Ссылка
        link = g.xpath('.//a/@href')
        link = "https://quizplease.ru" + link[0] if link else None

        games.append({
            "id": game_id,
            "title": title,
            "date": date,
            "bar": bar,
            "price": price,
            "type": game_type,
            "image": img,
            "url": link,
        })

    return games
