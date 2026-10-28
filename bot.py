import os, asyncio, logging, hashlib
from pathlib import Path
from urllib.parse import urlparse
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.types import Message, WebAppInfo, FSInputFile, BotCommand, MenuButtonWebApp
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
_u = urlparse(GAME_URL)
SERVER = os.getenv("PUBLIC_URL") or (f"{_u.scheme}://{_u.netloc}" if _u.netloc else "")
# тот же секрет, что и на сервере (server.py): либо NG_NOTIFY_SECRET, либо производная от токена
SECRET = os.getenv("NG_NOTIFY_SECRET") or hashlib.sha256(("ng-internal:" + TOKEN).encode()).hexdigest()

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
    "Нажми кнопку <b>«Играть»</b> слева от поля ввода и выбей свой первый номер 👇"
)
HELP = (
    "ℹ️ <b>Как играть</b>\n\n"
    "• Каждая прокрутка тратит ⚡ энергию и небольшой взнос в ₽. Номер может стоить меньше (убыток) или намного больше (прибыль).\n"
    "• Выпавший номер можно оставить или сразу продать.\n"
    "• Цена зависит от красоты цифр, оператора и города — причины видны под ценой.\n"
    "• В рейтинге считается капитал: рубли + стоимость всех номеров.\n"
    "• Кнопка со стрелкой отправляет в чат картинку с номером и ценой.\n"
    "• В профиле — реферальная ссылка: зови друзей и получай подарки."
)


async def remember_ref(friend: int, inviter: str):
    """Сообщаем серверу, кто кого пригласил (кнопки «Играть» под сообщением больше нет, ссылка с ref теряется)."""
    if not (SERVER and inviter.isdigit()):
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as http:
            await http.post(f"{SERVER}/api/ref-pending", json={"secret": SECRET, "friend": str(friend), "inviter": inviter})
    except Exception as e:
        logging.warning("ref-pending не отправлен: %s", e)


@dp.message(CommandStart())
async def start(m: Message, command: CommandObject):
    ref = (command.args or "").removeprefix("ref_")
    if ref == str(m.from_user.id):
        ref = ""
    if ref:
        await remember_ref(m.from_user.id, ref)
    text = WELCOME.format(name=m.from_user.first_name or "друг")
    if BANNER.exists():
        await m.answer_photo(FSInputFile(BANNER), caption=text)
    else:
        await m.answer(text)


@dp.message(Command("help"))
async def help_(m: Message):
    await m.answer(HELP)


@dp.message(F.text)
async def fallback(m: Message):
    await m.answer("Игра <b>НомерГрам</b> открывается кнопкой <b>«Играть»</b> слева от поля ввода 👇")


async def main():
    await bot.set_my_commands([BotCommand(command="start", description="Начать"),
                               BotCommand(command="help", description="Как играть")])
    # единственная точка входа в игру — кнопка меню «Играть» (без эмодзи)
    await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Играть", web_app=WebAppInfo(url=GAME_URL)))
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
