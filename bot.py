import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from db import add_user, get_user

API_TOKEN = "7666485376:AAGLUa58hLcVzu99yOJSHAzYPalRno98pTA"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    add_user(message.from_user.id, message.from_user.full_name)
    await message.answer(f"Привет, {message.from_user.full_name}! Ты добавлен в базу.")

@dp.message(Command("me"))
async def cmd_me(message: types.Message):
    user = get_user(message.from_user.id)
    if user:
        _, tg_id, name = user
        await message.answer(f"Ты в базе:\nID: {tg_id}\nИмя: {name}")
    else:
        await message.answer("Тебя нет в базе. Нажми /start")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
