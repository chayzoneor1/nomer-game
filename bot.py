# -*- coding: utf-8 -*-
"""НомерГрам — Telegram-бот (aiogram 3). Единственная точка входа в игру — кнопка меню «Играть»."""
import asyncio, hashlib, logging, os
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import BotCommand, FSInputFile, MenuButtonWebApp, Message, WebAppInfo

logging.basicConfig(level=logging.INFO)
BASE = Path(__file__).resolve().parent


def _load_env():
    f = BASE / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()
TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("NG_BOT_TOKEN") or "").strip()
PUBLIC_URL = (os.getenv("PUBLIC_URL") or "https://nomergram-bot.duckdns.org").rstrip("/")
GAME_URL = (os.getenv("GAME_URL") or PUBLIC_URL + "/").strip()       # игру отдаёт сам сервер (тот же домен, что и API)
BANNER = next((p for p in (BASE / "assets" / "welcome.png", BASE / "welcome.png") if p.exists()), None)
if not TOKEN:
    raise SystemExit("Ошибка: укажи BOT_TOKEN в файле .env")
SECRET = os.getenv("NG_NOTIFY_SECRET") or hashlib.sha256(("ng-internal:" + TOKEN).encode()).hexdigest()

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

WELCOME = (
    "👋 <b>Привет, {name}!</b>\n\n"
    "Добро пожаловать в <b>НомерГрам</b> — симулятор красивых телефонных номеров 📱\n\n"
    "<blockquote>"
    "🎰 <b>Крути</b> номера: от обычных до легендарных\n"
    "⚒ <b>Крафти</b>: объединяй номера в более редкие — но удача не гарантирована\n"
    "🔍 <b>Узнавай</b>, почему номер стоит столько\n"
    "💰 <b>Копи капитал</b>: рубли + стоимость всех номеров\n"
    "🏆 <b>Поднимайся</b> в рейтинге самых богатых\n"
    "🎁 <b>Выполняй</b> задания и крути колесо удачи"
    "</blockquote>\n\n"
    "👥 Позови 3 друзей — получишь <b>гарантированный редкий номер</b>, а друзьям — бонус на старт.\n"
    "☁️ Прогресс общий на телефоне и ПК.\n\n"
    "Нажми кнопку <b>«Играть»</b> слева от поля ввода 👇"
)
HELP = (
    "ℹ️ <b>Как играть в НомерГрам</b>\n\n"
    "• Прокрутка тратит ⚡ энергию (10 за раз). Энергия восстанавливается сама: 1 каждые 5 минут.\n"
    "• Выпавший номер можно оставить, продать (мгновенно) или посмотреть повтор выпадения.\n"
    "• Дорогие номера нужно добиваться: шансы низкие, но есть гарант — «Редкий» не позже чем через 60 прокруток, «Эпический» — через 1000.\n"
    "• «Номера» → «Крафт»: 5 обычных → необычный, 4 необычных → редкий, 4 редких → эпический, 4 эпических → легендарный. "
    "Успех не гарантирован (85 / 70 / 55 / 40%), при неудаче получишь номер прежней редкости.\n"
    "• Пакет энергии стоит 90 000 ₽ — береги рубли.\n"
    "• Цена зависит от рисунка цифр, оператора и города — причины видны у каждого номера.\n"
    "• В рейтинге считается капитал: рубли + стоимость всех номеров.\n"
    "• Из коллекции можно отправить красивую карточку номера другу.\n"
    "• Приглашай друзей по ссылке из профиля: 3 друга — гарантированный «Редкий» номер."
)


async def remember_ref(friend: int, inviter: str):
    """Сообщаем серверу, кто кого пригласил (ссылка t.me/бот?start=ref_ID)."""
    if not inviter.isdigit():
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as http:
            await http.post(f"{PUBLIC_URL}/api/ref-pending", json={"secret": SECRET, "friend": str(friend), "inviter": inviter})
    except Exception as e:
        logging.warning("ref-pending не отправлен: %s", e)


@dp.message(CommandStart())
async def start(m: Message, command: CommandObject):
    ref = (command.args or "").removeprefix("ref_")
    if ref and ref != str(m.from_user.id):
        await remember_ref(m.from_user.id, ref)
    text = WELCOME.format(name=(m.from_user.first_name or "друг").replace("<", "").replace(">", ""))
    if BANNER:
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
    await bot.set_my_commands([BotCommand(command="start", description="Начать"), BotCommand(command="help", description="Как играть")])
    await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Играть", web_app=WebAppInfo(url=GAME_URL)))
    await bot.set_my_short_description("Симулятор красивых номеров: крути, крафти, копи капитал и стань самым богатым!")
    await bot.set_my_description("📱 НомерГрам — крути номера, лови редкие и легендарные, крафти и борись за топ самых богатых. "
                                 "Прогресс общий на всех устройствах. Нажми «Начать»!")
    me = await bot.get_me()
    print(f"✅ Бот @{me.username} запущен. Игра: {GAME_URL}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")
