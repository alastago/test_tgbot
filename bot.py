import logging
from aiogram import Bot, Dispatcher, executor, types
from db import add_user, get_user

API_TOKEN = "7666485376:AAGLUa58hLcVzu99yOJSHAzYPalRno98pTA"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    add_user(message.from_user.id, message.from_user.full_name)
    await message.answer(f"Привет, {message.from_user.full_name}! Ты добавлен в базу данных.")

@dp.message_handler(commands=['me'])
async def me(message: types.Message):
    user = get_user(message.from_user.id)
    if user:
        _, tg_id, name = user
        await message.answer(f"Ты есть в базе.\nID: {tg_id}\nИмя: {name}")
    else:
        await message.answer("Тебя нет в базе. Отправь /start")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
