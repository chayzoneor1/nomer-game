import asyncio
import os
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, MenuButtonWebApp
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
WEBAPP_URL = 'https://chayzoneor1.github.io/nomer-game/'
router = Router()


def game_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='🎮 Играть', web_app=WebAppInfo(url=WEBAPP_URL))]],
        resize_keyboard=True,
        is_persistent=True,
    )


@router.message(CommandStart())
async def start(message: Message):
    await message.answer(
        '🎮 Генератор телефонных номеров\n\nОткрывай игру кнопкой ниже и собирай редкие игровые номера!',
        reply_markup=game_keyboard(),
    )


@router.message(Command('app'))
async def app_command(message: Message):
    await message.answer('Нажми кнопку, чтобы открыть игру:', reply_markup=game_keyboard())


async def main():
    if not BOT_TOKEN or BOT_TOKEN == 'PASTE_YOUR_BOT_TOKEN_HERE':
        raise SystemExit('Не указан BOT_TOKEN. Открой файл .env и вставь токен от BotFather.')

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    # Adds the Mini App to the bot's chat menu for all users.
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text='🎮 Играть', web_app=WebAppInfo(url=WEBAPP_URL))
    )
    print('Бот запущен. Нажми Ctrl+C для остановки.')
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == '__main__':
    asyncio.run(main())
