from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

def main_menu():
    kb = [
        [InlineKeyboardButton(text="Создать команду", callback_data="create_team")],
        [InlineKeyboardButton(text="Вступить в команду", callback_data="join_team")],
        [InlineKeyboardButton(text="🔍 Запустить парсер", callback_data="run_parser")],
        [InlineKeyboardButton(text="Игры", callback_data="games")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def games_menu():
    kb = [
        [InlineKeyboardButton(text="Список игр", callback_data="list_games")],
        [InlineKeyboardButton(text="Записать команду", callback_data="team_reg_game")],
        [InlineKeyboardButton(text="Записаться игроком", callback_data="player_reg_game")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)
