import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db import (
    add_user, get_user,
    create_team, team_exists,
    create_game, get_games,
    register_to_game
)

API_TOKEN = "7666485376:AAGLUa58hLcVzu99yOJSHAzYPalRno98pTA"
ADMIN_ID = 441329526  # ← Укажите ваш ID

bot = Bot(token=API_TOKEN)
dp = Dispatcher()


# --------------------------
# ГЛАВНОЕ МЕНЮ
# --------------------------
def main_menu(is_admin=False):
    kb = InlineKeyboardBuilder()

    kb.button(text="🆕 Создать команду", callback_data="create_team_btn")
    kb.button(text="🕹 Записаться на игру", callback_data="join_game_btn")

    if is_admin:
        kb.button(text="🛠 Админ-панель", callback_data="admin_panel")

    kb.adjust(1)
    return kb.as_markup()


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    add_user(message.from_user.id, message.from_user.full_name)

    is_admin = message.from_user.id == ADMIN_ID
    await message.answer(
        "Добро пожаловать! Выберите действие:",
        reply_markup=main_menu(is_admin)
    )


# --------------------------
# СОЗДАНИЕ КОМАНДЫ
# --------------------------
@dp.callback_query(F.data == "create_team_btn")
async def ask_team_name(callback: types.CallbackQuery):
    await callback.message.answer("Введите название команды:")
    await callback.answer()
    dp.workflow_data[callback.from_user.id] = "await_team_name"


@dp.message(F.text)
async def create_team_handler(message: types.Message):
    user_state = dp.workflow_data.get(message.from_user.id)

    if user_state == "await_team_name":
        team_name = message.text

        if team_exists(team_name):
            return await message.answer("Команда с таким названием уже существует.")

        create_team(message.from_user.id, team_name)
        dp.workflow_data[message.from_user.id] = None

        return await message.answer(f"Команда **{team_name}** создана!")



# --------------------------
# ЗАПИСАТЬСЯ НА ИГРУ
# --------------------------
@dp.callback_query(F.data == "join_game_btn")
async def choose_game(callback: types.CallbackQuery):
    games = get_games()

    if not games:
        return await callback.message.answer("Нет доступных игр!")

    kb = InlineKeyboardBuilder()
    for game_id, title in games:
        kb.button(text=title, callback_data=f"join_{game_id}")
    kb.adjust(1)

    await callback.message.answer("Выберите игру:", reply_markup=kb.as_markup())
    await callback.answer()


@dp.callback_query(F.data.startswith("join_"))
async def join_game(callback: types.CallbackQuery):
    game_id = int(callback.data.split("_")[1])
    register_to_game(callback.from_user.id, game_id)
    await callback.message.answer("Вы успешно записались на игру!")
    await callback.answer()



# --------------------------
# АДМИН-ПАНЕЛЬ
# --------------------------
def admin_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить игру", callback_data="admin_add_game")
    kb.button(text="📄 Список игр", callback_data="admin_list_games")
    kb.adjust(1)
    return kb.as_markup()


@dp.callback_query(F.data == "admin_panel")
async def open_admin_panel(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("Нет доступа", show_alert=True)

    await callback.message.answer("🛠 Админ-панель:", reply_markup=admin_menu())
    await callback.answer()


# ---- Добавление игры ----
@dp.callback_query(F.data == "admin_add_game")
async def admin_add_game(callback: types.CallbackQuery):
    dp.workflow_data[callback.from_user.id] = "await_game_title"
    await callback.message.answer("Введите название новой игры:")
    await callback.answer()


@dp.message(F.text)
async def add_game_handler(message: types.Message):
    user_state = dp.workflow_data.get(message.from_user.id)

    if user_state == "await_game_title":
        title = message.text
        create_game(title)
        dp.workflow_data[message.from_user.id] = None
        return await message.answer(f"Игра '{title}' успешно добавлена!")


# ---- Список игр ----
@dp.callback_query(F.data == "admin_list_games")
async def admin_list_games(callback: types.CallbackQuery):
    games = get_games()

    if not games:
        return await callback.message.answer("Игр пока нет.")

    text = "📄 *Список игр:*\n\n"
    for game_id, title in games:
        text += f"• {game_id}: {title}\n"

    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()



# --------------------------
# MAIN
# --------------------------
async def main():
    dp.workflow_data = {}  # простое хранилище состояний
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
