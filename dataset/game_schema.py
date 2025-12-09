# game_schema.py
from datetime import datetime

GAME_SCHEMA = {
    "id": str,        # уникальный id игры (из div id)
    "datetext": str,      # дата игры
    "date": datetime,
    "title": str,     # название игры
    "bar": str,       # место проведения
    "price": str,     # цена
    "url": str        # ссылка на игру
}
