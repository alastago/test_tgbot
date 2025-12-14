import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, CommandStart
from aiogram.enums import ParseMode

from parser import fetch_games
from states import *
from keyboards import *
from dataset.database import *
from handlers.team import *

from registration import *

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
    await asyncio.sleep(10)      # чтобы бот успел запуститься

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
# handlers.team
# --------------------------
register_team_handlers(dp)

# --------------------------
# ВСТУПЛЕНИЕ В КОМАНДУ
# handlers.team
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
    log("team_reg_game: вход в хендлер")

    conn = get_db()
    cur = conn.cursor()

    try:
        # проверяем наличие команды
        log(f"Проверяем команду для user_id={callback.from_user.id}")
        cur.execute("SELECT team_id FROM player_teams WHERE user_id=?", (callback.from_user.id,))
        t = cur.fetchone()
        log(f"Результат запроса команды: {t}")

        if not t or not t["team_id"]:
            log("Команда не найдена")
            await callback.message.answer("Вы не в команде.")
            return

        # список игр
        log("Получаем список игр...")
        cur.execute("SELECT * FROM games")
        games = cur.fetchall()
        log(f"Найдено игр: {len(games)}")

        kb = [
            [types.InlineKeyboardButton(text=f"{g['title']}", callback_data=f"team_game_{g['id']}")]
            for g in games
        ]

        await callback.message.answer("Выберите игру:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
        await callback.answer()
        log("Клавиатура с играми отправлена")

    except Exception as e:
        log(f"Ошибка в team_reg_game: {e}")
        await callback.message.answer("Произошла ошибка.")
        await callback.answer()


@dp.callback_query(F.data.startswith("team_game_"))
async def register_team(callback: types.CallbackQuery):
    log("team_game_: вход в хендлер register_team")

    try:
        game_id = int(callback.data.split("_")[2])
        log(f"Выбран game_id={game_id}")

        conn = get_db()
        cur = conn.cursor()

        log(f"Проверяем команду для user_id={callback.from_user.id}")
        cur.execute("SELECT * FROM teams WHERE id IN (SELECT team_id FROM player_teams WHERE user_id=?)", (callback.from_user.id,))
        team = cur.fetchone()
        log(f"Результат запроса команды: {team}")

       
        team_id = team["id"]
        team_name = team["name"]
        captain_name = team["captainName"] or "-"
        email = team["email"] or "-"
        phone = team["phone"] or "+"
                

        log(f"Пытаемся записать team_id={team_id} на game_id={game_id}")
        # Пытаемся зарегистрировать
        await register_team_on_quizplease(
            game_id,
            team_name,
            captain_name,
            email=email,
            phone=phone,
            players_count=5,
            comment="Тестовая запись. Команды не существует."
        )
        await callback.message.answer("Команда записана!")
        await callback.answer()

    except Exception as e:
        log(f"Ошибка в team_game_: {e}")
        await callback.message.answer("Произошла ошибка при записи.")
        await callback.answer()

# --------------------------
# Игрок записывается на игру
# --------------------------

async def get_available_games_for_player(conn, user_id: int):
    cur = conn.cursor()

    cur.execute("""
        SELECT DISTINCT
            g.id,
            g.datetext,
            g.title,
            g.bar,
            t.name
        FROM games g
        JOIN team_games tg ON tg.game_id = g.id AND tg.signup_status = 1
        JOIN player_teams pt ON pt.team_id = tg.team_id
        JOIN teams t ON t.id = tg.team_id
        LEFT JOIN player_games pg
            ON pg.game_id = g.id AND pg.user_id = ?
        WHERE
            pt.user_id = ?
            AND pg.user_id IS NULL
        ORDER BY g.date
    """, (user_id, user_id))

    return cur.fetchall()


@router.callback_query(F.data == "player_signup_games")
async def show_games_for_signup(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    games = await get_available_games_for_player(db, user_id)

    if not games:
        await callback.answer(
            "❌ Нет доступных игр для записи",
            show_alert=True
        )
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"📅 {g[1]} | {g[2]} | {g[4]}",
                callback_data=f"player_join_game_{g[0]}"
            )
        ]
        for g in games
    ])

    await callback.message.answer(
        "Выберите игру для записи:",
        reply_markup=keyboard
    )
    await callback.answer()
    
@router.callback_query(F.data.startswith("player_join_game_"))
async def player_join_game(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    game_id = int(callback.data.split("_")[-1])

    success, message = await register_player_on_game(
        conn=db,
        user_id=user_id,
        game_id=game_id
    )

    await callback.answer(message, show_alert=not success)

    if success:
        await callback.message.edit_text(
            "✅ Вы успешно записались на игру!"
        )

# --------------------------
# RUN
# --------------------------
async def main():
    asyncio.create_task(parser_worker())  # запускаем фоновый процесс
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
