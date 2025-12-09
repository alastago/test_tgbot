from aiogram.fsm.state import StatesGroup, State

class CreateTeam(StatesGroup):
    name = State()
    email = State()
    phone = State()
    captain_name = State()
    auto_signup = State()
    signup_mode = State()
    keywords = State()

class JoinTeam(StatesGroup):
    name = State()

class RegisterGame(StatesGroup):
    select_game = State()

class TeamRegisterGame(StatesGroup):
    select_game = State()
