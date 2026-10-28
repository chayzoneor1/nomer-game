import os, asyncio, logging
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.types import (Message, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton,
                           FSInputFile, BotCommand)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
load_dotenv()
TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("NG_BOT_TOKEN") or "").strip()
GAME_URL = os.getenv("GAME_URL", "https://chayzoneor1.github.io/nomer-game/").strip()
BANNER = Path(__file__).parent / "assets" / "welcome.png"
if not TOKEN:
    raise SystemExit("Ошибка: укажи BOT_TOKEN в файле .env")

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

WELCOME = (
    "👋 <b>Привет, {name}!</b>\n\n"
    "Добро пожаловать в <b>НомерГрам</b> — симулятор красивых номеров 📱\n\n"
    "<blockquote>"
    "🎰 <b>Крути</b> номера: от обычных до легендарных\n"
    "💰 <b>Продавай</b> находки или копи коллекцию\n"
    "🔍 <b>Узнавай</b>, почему номер так дорого стоит\n"
    "🎁 <b>Забирай</b> подарок дня и награды за задания\n"
    "🏆 <b>Побеждай</b> в рейтинге самых богатых"
    "</blockquote>\n\n"
    "👥 Позови друга — ему бонус на старт, а тебе подарки.\n"
    "☁️ Прогресс общий на телефоне и ПК.\n\n"
    "Нажми <b>«Играть»</b> и выбей свой первый номер 👇"
)
HELP = (
    "ℹ️ <b>Как играть</b>\n\n"
    "• Каждая прокрутка тратит ⚡ энергию, она восстанавливается сама.\n"
    "• Выпавший номер можно оставить или сразу продать.\n"
    "• Цена зависит от красоты цифр, оператора и города — причины видны под ценой.\n"
    "• В рейтинге считается капитал: рубли + стоимость всех номеров.\n"
    "• Кнопка со стрелкой делится номером в сторис или чате."
)


def kb(ref: str = ""):
    url = GAME_URL + ((("&" if "?" in GAME_URL else "?") + f"ref={ref}") if ref.isdigit() else "")
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Играть", web_app=WebAppInfo(url=url))]])


@dp.message(CommandStart())
async def start(m: Message, command: CommandObject):
    ref = (command.args or "").removeprefix("ref_")
    if ref == str(m.from_user.id):
        ref = ""
    text = WELCOME.format(name=m.from_user.first_name or "друг")
    if BANNER.exists():
        await m.answer_photo(FSInputFile(BANNER), caption=text, reply_markup=kb(ref))
    else:
        await m.answer(text, reply_markup=kb(ref))


@dp.message(Command("help"))
async def help_(m: Message):
    await m.answer(HELP, reply_markup=kb())


@dp.message(F.text)
async def fallback(m: Message):
    await m.answer("Я запускаю игру <b>НомерГрам</b> 👇", reply_markup=kb())


async def main():
    await bot.set_my_commands([BotCommand(command="start", description="🚀 Запустить игру"),
                               BotCommand(command="help", description="ℹ️ Как играть")])
    await bot.set_my_short_description("Симулятор красивых номеров: крути, собирай, продавай и стань самым богатым!")
    await bot.set_my_description("📱 НомерГрам — крути номера, лови редкие и легендарные, продавай и борись за топ. "
                                 "Прогресс общий на всех устройствах. Нажми «Начать»!")
    print("✅ Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")
