import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode

from parser import fetch_games
from states import *
from keyboards import *
from dataset.database import *
from registration import register_team_on_quizplease

from datetime import datetime
from config import TOKEN, LOGFILE

def log(text: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {text}\n")


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
        cur.execute("INSERT INTO players (user_id, username) VALUES (?, ?)",
                    (message.from_user.id, message.from_user.username))
        conn.commit()

    await message.answer("Привет! Выберите действие:", reply_markup=main_menu())


# --------------------------
#Парсер игр
# --------------------------
async def parser_worker():
    """
    Фоновая задача: каждые 60 секунд парсит игры.
    Добавляет новые в БД.
    Автоматически записывает команды.
    Рассылает уведомления игрокам.
    """
    await asyncio.sleep(3)      # чтобы бот успел запуститься

    while True:
        try:
            log("Запуск автоматического парсера")

            # 1) Получаем игры
            games = await fetch_games()
            newgames = filter_new_games(games)

            if not newgames:
                log("Новых игр нет")
            else:
                log(f"Найдено новых игр: {len(newgames)}")
                await insert_games_bulk(newgames)
                log("Новые игры добавлены в БД")

            # 2. Автозапись команд
            await auto_register_teams()

            # 3. Уведомления пользователей
            await notify_players_about_games()

        except Exception as e:
            log(f"Ошибка в parser_worker: {e}")

        await asyncio.sleep(60)
    
# --------------------------
#Автозапись команд на новые игры
# --------------------------

async def auto_register_teams():
    """
    Команды с auto_signup=1 автоматически записываются на все новые игры.
    """
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM teams WHERE auto_auto_signup=1")
    teams = cur.fetchall()

    if not teams:
        return

    cur.execute("SELECT id FROM games ORDER BY id DESC")
    games = cur.fetchall()

    for team in teams:
        team_id = team["id"]
        team_name = team["name"]
        captain_name = team["captainName"] or "-"
        email = team["email"] or "-"
        phone = team["phone"] or "+"
        whitelist = team.get("whitelist", "").split(",")  # ключевые слова белого списка
        blacklist = team.get("blacklist", "").split(",")  # ключевые слова черного списка
        # Получаем игры, на которые команда ещё не записана
        cur.execute("""
            SELECT * FROM games g
            WHERE g.id NOT IN (SELECT game_id FROM team_games WHERE team_id=?)
        """, (team_id,))
        available_games = cur.fetchall()
        for g in available_games:
            title = g["title"]

            # Проверка whitelist / blacklist
            if whitelist and not any(w.lower() in title.lower() for w in whitelist):
                continue  # пропускаем, если есть белый список и нет совпадений
            if blacklist and any(b.lower() in title.lower() for b in blacklist):
                continue  # пропускаем, если есть черный список и есть совпадения

            # Пытаемся зарегистрировать
            code, message = await register_team_on_quizplease(
                game_id=g["id"],
                team_name=team_name,
                captain_name=captain_name,
                email=email,
                phone=phone,
                players_count=5,
                comment="Автозапись"
            )
            if code in ("1", "4", "5"):  # успешные варианты
                # Запись в БД о регистрации команды на игру
                cur.execute(
                    "INSERT OR IGNORE INTO team_games (team_id, game_id) VALUES (?, ?)",
                    (team_id, g["id"])
                )
                conn.commit()
            
            else:
                log(f"Регистрация команды '{team_name}' на игру '{title}' не удалась: {message}")

    conn.close()
    log("Автозапись команд выполнена")

# --------------------------
#Рассылка уведомлений в чат
# --------------------------

async def notify_players_about_games():
    """
    Находит игры, на которые команда записалась недавно, и сообщает игрокам.
    """
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT tg.team_id, tg.game_id, g.title, g.date
        FROM team_games tg
        JOIN games g ON g.id = tg.game_id
        WHERE tg.notification_status = 0
    """)
    events = cur.fetchall()

    if not events:
        return

    for e in events:
        team_id = e["team_id"]
        game_id = e["game_id"]

        cur.execute("SELECT user_id FROM players WHERE team_id=?", (team_id,))
        users = cur.fetchall()

        for u in users:
            try:
                await bot.send_message(
                    u["user_id"],
                    f"📢 Ваша команда записана на игру!\n"
                    f"🎮 {e['title']}\n"
                    f"📅 {e['date']}"
                )
            except:
                pass

        cur.execute("UPDATE team_games SET notification_status=1 WHERE team_id=? AND game_id=?", (team_id, game_id))

    conn.commit()
    log(f"Разослано уведомлений: {len(events)}")


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
    asyncio.create_task(parser_worker())  # запускаем фоновый процесс
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
