from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

def main_menu():
    kb = [
        [InlineKeyboardButton(text="Мои команды", callback_data="teams")],
        
        [InlineKeyboardButton(text="Привязка чата", callback_data="bind_chat")],
        [InlineKeyboardButton(text="Создать команду", callback_data="create_team")],
        [InlineKeyboardButton(text="Вступить в команду", callback_data="join_team")],
        [InlineKeyboardButton(text="Игры", callback_data="games")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def games_menu():
    kb = [
        [InlineKeyboardButton(text="Список игр", callback_data="list_games")],
        [InlineKeyboardButton(text="Записать команду", callback_data="team_reg_game")],
        
        [InlineKeyboardButton(text="📝 Записаться на игру (игрок)", callback_data="player_signup_games")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)
