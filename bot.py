import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart
from states import *
from keyboards import *
from database import *
from config import TOKEN

bot = Bot(TOKEN)
dp = Dispatcher()

init_db()   # создаём базу при запуске


# --------------------------
# START
# --------------------------
@dp.message(CommandStart())
async def start(message: types.Message):
    conn = get_db()
    cur = conn.cursor()

    # Если игрока нет — добавляем
    cur.execute("SELECT * FROM players WHERE user_id=?", (message.from_user.id,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO players (user_id, username, team_id) VALUES (?, ?, ?)",
                    (message.from_user.id, message.from_user.username, None))
        conn.commit()

    await message.answer("Привет! Выберите действие:", reply_markup=main_menu())


# --------------------------
# СОЗДАНИЕ КОМАНДЫ
# --------------------------
@dp.callback_query(F.data == "create_team")
async def ask_team_name(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите название команды:")
    await state.set_state(CreateTeam.name)
    await callback.answer()


@dp.message(CreateTeam.name)
async def team_email(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите email команды:")
    await state.set_state(CreateTeam.email)


@dp.message(CreateTeam.email)
async def finish_team(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data["name"]
    email = message.text

    conn = get_db()
    cur = conn.cursor()

    # создаём команду
    cur.execute("INSERT INTO teams (name, email, captain_id) VALUES (?, ?, ?)",
                (name, email, message.from_user.id))
    conn.commit()

    # игрок = капитан
    cur.execute("UPDATE players SET team_id=(SELECT id FROM teams WHERE name=?) WHERE user_id=?",
                (name, message.from_user.id))
    conn.commit()

    await message.answer(f"Команда '{name}' создана!", reply_markup=main_menu())
    await state.clear()


# --------------------------
# ВСТУПЛЕНИЕ В КОМАНДУ
# --------------------------
@dp.callback_query(F.data == "join_team")
async def join_team(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите название команды для вступления:")
    await state.set_state(JoinTeam.name)
    await callback.answer()


@dp.message(JoinTeam.name)
async def join_team_finish(message: types.Message, state: FSMContext):
    team = message.text
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id FROM teams WHERE name=?", (team,))
    row = cur.fetchone()

    if not row:
        await message.answer("Команды не существует.")
        return

    cur.execute("UPDATE players SET team_id=? WHERE user_id=?", (row["id"], message.from_user.id))
    conn.commit()

    await message.answer(f"Вы вступили в команду {team}", reply_markup=main_menu())
    await state.clear()


# --------------------------
# ИГРЫ
# --------------------------
@dp.callback_query(F.data == "games")
async def games_menu_show(callback: types.CallbackQuery):
    await callback.message.answer("Меню игр:", reply_markup=games_menu())
    await callback.answer()


@dp.callback_query(F.data == "list_games")
async def list_games(callback: types.CallbackQuery):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM games")
    games = cur.fetchall()

    if not games:
        await callback.message.answer("Нет игр.")
    else:
        text = "\n".join([f"{g['id']}. {g['title']} — {g['date']}" for g in games])
        await callback.message.answer("Игры:\n" + text)

    await callback.answer()


# --------------------------
# Запись команды на игру
# --------------------------
@dp.callback_query(F.data == "team_reg_game")
async def team_choose_game(callback: types.CallbackQuery, state: FSMContext):
    conn = get_db()
    cur = conn.cursor()

    # проверяем наличие команды
    cur.execute("SELECT team_id FROM players WHERE user_id=?", (callback.from_user.id,))
    t = cur.fetchone()
    if not t or not t["team_id"]:
        await callback.message.answer("Вы не в команде.")
        return

    # список игр
    cur.execute("SELECT * FROM games")
    games = cur.fetchall()

    kb = [
        [types.InlineKeyboardButton(text=f"{g['title']}", callback_data=f"team_game_{g['id']}")]
        for g in games
    ]
    await callback.message.answer("Выберите игру:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data.startswith("team_game_"))
async def register_team(callback: types.CallbackQuery):
    game_id = int(callback.data.split("_")[2])

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT team_id FROM players WHERE user_id=?", (callback.from_user.id,))
    team = cur.fetchone()["team_id"]

    cur.execute("INSERT OR IGNORE INTO team_games (team_id, game_id) VALUES (?, ?)", (team, game_id))
    conn.commit()

    await callback.message.answer("Команда записана!")
    await callback.answer()


# --------------------------
# Игрок записывается на игру
# --------------------------
@dp.callback_query(F.data == "player_reg_game")
async def player_choose_game(callback: types.CallbackQuery):
    conn = get_db()
    cur = conn.cursor()

    # находим команду игрока
    cur.execute("SELECT team_id FROM players WHERE user_id=?", (callback.from_user.id,))
    t = cur.fetchone()["team_id"]

    if not t:
        await callback.message.answer("Вы не в команде.")
        return

    # игры, куда записана команда
    cur.execute("""
        SELECT g.id, g.title FROM games g
        JOIN team_games tg ON tg.game_id = g.id
        WHERE tg.team_id=?
    """, (t,))
    games = cur.fetchall()

    if not games:
        await callback.message.answer("Ваша команда не записана ни на одну игру.")
        return

    kb = [
        [types.InlineKeyboardButton(text=g['title'], callback_data=f"player_game_{g['id']}")]
        for g in games
    ]

    await callback.message.answer("Выберите игру:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data.startswith("player_game_"))
async def register_player(callback: types.CallbackQuery):
    game_id = int(callback.data.split("_")[2])

    conn = get_db()
    cur = conn.cursor()

    cur.execute("INSERT OR IGNORE INTO player_games (user_id, game_id) VALUES (?, ?)",
                (callback.from_user.id, game_id))
    conn.commit()

    await callback.message.answer("Вы записаны!")
    await callback.answer()


# --------------------------
# RUN
# --------------------------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
