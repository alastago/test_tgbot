from aiogram import types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from dataset.database import get_db
from keyboards import main_menu

# --------------------------
# СОЗДАНИЕ КОМАНДЫ
# --------------------------
class CreateTeam(StatesGroup):
    name = State()
    email = State()
    phone = State()
    captain_name = State()
    auto_signup = State()
    signup_mode = State()
    keywords = State()

def register_team_handlers(dp):

    @dp.callback_query(F.data == "create_team")
    async def ask_team_name(callback: types.CallbackQuery, state: FSMContext):
        await callback.message.answer("Введите название команды:")
        await state.set_state(CreateTeam.name)
        await callback.answer()


    @dp.message(CreateTeam.name)
    async def ask_team_email(message: types.Message, state: FSMContext):
        await state.update_data(name=message.text)
        await message.answer("Введите email команды (для регистрации на игры):")
        await state.set_state(CreateTeam.email)


    @dp.message(CreateTeam.email)
    async def ask_team_phone(message: types.Message, state: FSMContext):
        await state.update_data(email=message.text)
        await message.answer("Введите телефон команды (для регистрации на игры):")
        await state.set_state(CreateTeam.phone)


    @dp.message(CreateTeam.phone)
    async def ask_captain_name(message: types.Message, state: FSMContext):
        await state.update_data(phone=message.text)
        await message.answer("Введите имя капитана (для регистрации на игры):")
        await state.set_state(CreateTeam.captain_name)


    @dp.message(CreateTeam.captain_name)
    async def ask_auto_signup(message: types.Message, state: FSMContext):
        await state.update_data(captain_name=message.text)
        await message.answer("Включить авто-запись на игры? (да/нет)")
        await state.set_state(CreateTeam.auto_signup)


    @dp.message(CreateTeam.auto_signup)
    async def ask_signup_mode(message: types.Message, state: FSMContext):
        answer = message.text.lower()
        auto_signup = 1 if answer in ("да", "yes", "y") else 0
        await state.update_data(auto_signup=auto_signup)

        await message.answer("Выберите режим записи на игры: white / black")
        await state.set_state(CreateTeam.signup_mode)


    @dp.message(CreateTeam.signup_mode)
    async def ask_keywords(message: types.Message, state: FSMContext):
        answer = message.text.lower()
        if answer not in ("white", "black"):
            answer = "white"
        await state.update_data(signup_mode=answer)

        await message.answer("Введите ключевые слова команды (через запятую, можно оставить пустым):")
        await state.set_state(CreateTeam.keywords)


    @dp.message(CreateTeam.keywords)
    async def finish_team(message: types.Message, state: FSMContext):
        data = await state.get_data()
        user_id = message.from_user.id

        name = data["name"]
        email = data["email"]
        phone = data.get("phone", "")
        captain_name = data["captain_name"]
        auto_signup = data.get("auto_signup", 0)
        signup_mode = data.get("signup_mode", "white")
        keywords = message.text.strip()

        conn = get_db()
        cur = conn.cursor()

        try:
            cur.execute(
                """INSERT INTO teams 
                   (name, email, phone, captainName, captain_id, auto_signup, signup_mode, keywords)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, email, phone, captain_name, user_id, auto_signup, signup_mode, keywords)
            )
            team_id = cur.lastrowid

            cur.execute(
                "INSERT INTO player_teams (user_id, team_id, is_capitan) VALUES (?, ?, ?)",
                (user_id, team_id, 1)
            )

            conn.commit()

        except Exception as e:
            conn.rollback()
            await message.answer(f"Ошибка при создании команды: {e}")
            return

        await message.answer(f"Команда '{name}' успешно создана!\nДля добавления участников необходимо создать командный чат, и добавить в него бота", reply_markup=main_menu())
        await state.clear()
        
# Привязка чата к команде
    @dp.message(Command("bind_chat"))
    async def bind_team_chat(message: types.Message, state: FSMContext):
        """
        Капитан привязывает текущий чат к своей команде.
        Использование: /bind_chat <название команды>
        """
        if message.chat.type not in ("group", "supergroup"):
            await message.answer("Привязка чата возможна только из группового чата!")
            return
            
        user_id = message.from_user.id
        args = message.get_args()  # получаем текст после команды
        
        if not args:
            await message.answer("Укажите название команды: /bind_chat <название вашей команды>")
            return
    
        team_name = args.strip()
    
        conn = get_db()
        cur = conn.cursor()
        # Проверяем, что пользователь капитан указанной команды
        cur.execute(
            "SELECT id FROM teams WHERE name = ? AND captain_id = ?",
            (team_name, user_id)
        )
        team = cur.fetchone()
        if not team:
            await message.answer("Вы не являетесь капитаном команды с таким названием.")
            return
    
        team_id = team[0]
        chat_id = message.chat.id
    
        # Привязываем чат к команде
        cur.execute(
            "UPDATE teams SET chat_id = ? WHERE id = ?",
            (chat_id, team_id)
        )
        conn.commit()
    
        await message.answer(f"Командный чат для команды '{team_name}' успешно привязан! ✅")

# --------------------------
# ВСТУПЛЕНИЕ В КОМАНДУ
# --------------------------



