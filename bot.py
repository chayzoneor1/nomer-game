import os
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import MenuButtonWebApp
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "").strip()
GAME_URL = os.getenv("GAME_URL", "https://chayzoneor1.github.io/nomer-game/").strip()

if not TOKEN or TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
    raise SystemExit("Укажи токен в файле .env (BOT_TOKEN=...) и запусти снова.")

bot = Bot(TOKEN)
dp = Dispatcher()

def game_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🎮 Играть", web_app=WebAppInfo(url=GAME_URL))]],
        resize_keyboard=True,
        input_field_placeholder="Открой игру кнопкой ниже"
    )

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "🎮 Генератор телефонных номеров\\n\\nНажми «Играть», чтобы открыть игру внутри Telegram.",
        reply_markup=game_keyboard()
    )

@dp.message(F.text == "🎮 Играть")
async def play(message: Message):
    await message.answer("Нажми кнопку ниже, чтобы открыть игру:", reply_markup=game_keyboard())

async def main():
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="Играть", web_app=WebAppInfo(url=GAME_URL))
    )
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
