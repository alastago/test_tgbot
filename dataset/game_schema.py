# game_schema.py

GAME_SCHEMA = {
    "id": str,        # уникальный id игры (из div id)
    "datetext": str,      # дата игры
    "date": datetime,
    "title": str,     # название игры
    "bar": str,       # место проведения
    "price": str,     # цена
    "url": str        # ссылка на игру
}

def validate_game(game: dict) -> tuple[bool, list[str]]:
    """
    Проверяет, соответствует ли объект game схеме.
    Возвращает: (True/False, список ошибок)
    """
    errors = []

    # 1. Проверка — есть ли все поля из схемы
    for field, field_type in GAME_SCHEMA.items():
        if field not in game:
            errors.append(f"Missing required field: {field}")
        else:
            if not isinstance(game[field], field_type):
                errors.append(
                    f"Field '{field}' has wrong type: {type(game[field]).__name__}, expected {field_type.__name__}"
                )

    # 2. Проверка — нет ли лишних полей
    for field in game.keys():
        if field not in GAME_SCHEMA:
            errors.append(f"Unknown field detected: {field}")

    return (len(errors) == 0, errors)
