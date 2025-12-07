# parser.py

import requests
from bs4 import BeautifulSoup
from config import SCHEDULE_URL

URL = SCHEDULE_URL

def fetch_games():
    response = requests.get(URL, timeout=10)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    game_blocks = soup.find_all("div", class_="schedule-column")

    games = []

    for g in game_blocks:
        game_id = g.get("id", "")

        title_el = g.find("div", class_="game-title")
        title = title_el.get_text(strip=True) if title_el else None

        date_el = g.find("div", class_="game-date")
        date = date_el.get_text(strip=True) if date_el else None

        bar_el = g.find("div", class_="game-bar-title")
        bar = bar_el.get_text(strip=True) if bar_el else None

        price_el = g.find("div", class_="game-price")
        price = price_el.get_text(strip=True) if price_el else None

        type_el = g.find("div", class_="game-type")
        game_type = type_el.get_text(strip=True) if type_el else None

        img_el = g.find("img")
        img = img_el["src"] if img_el else None

        link_el = g.find("a")
        link = "https://quizplease.ru" + link_el["href"] if link_el else None

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

