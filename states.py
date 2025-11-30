from aiogram.fsm.state import StatesGroup, State

class CreateTeam(StatesGroup):
    name = State()
    email = State()

class JoinTeam(StatesGroup):
    name = State()

class RegisterGame(StatesGroup):
    select_game = State()

class TeamRegisterGame(StatesGroup):
    select_game = State()
