# bot.py — Telegram-бот NomerGame
# pip install aiogram==3.* httpx python-dotenv
# .env:
#   NG_BOT_TOKEN=123456:ABC...
#   NG_BOT_USERNAME=nomer_game_bot
#   NG_WEBAPP_URL=https://your-domain.com/index.html
#   NG_API_BASE=https://your-domain.com
#   NG_NOTIFY_SECRET=dev

import os, asyncio, json, logging, html
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo, BotCommand,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
import httpx
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.environ["NG_BOT_TOKEN"]
WEBAPP_URL = os.getenv("NG_WEBAPP_URL", "https://example.com/index.html")
API_BASE = os.getenv("NG_API_BASE", "").rstrip("/")
BOT_USER = os.getenv("NG_BOT_USERNAME", "nomer_game_bot")

logging.basicConfig(level=logging.INFO)
bot = Bot(TOKEN)
dp = Dispatcher()

RARITY_NAMES = ["Обычный", "Необычный", "Редкий", "Эпический", "Легендарный"]
RARITY_EMOJI = ["⚪", "🔵", "🟣", "🟪", "🟡"]

# ---------- Утилиты ----------
def main_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎰 Играть", web_app=WebAppInfo(url=WEBAPP_URL))
    kb.button(text="🏆 Рейтинг", callback_data="lb:value")
    kb.button(text="📖 Правила", callback_data="rules")
    kb.button(text="📨 Поделиться ботом", url=f"https://t.me/share/url?url=https://t.me/{BOT_USER}&text=Собирай+редкие+номера+в+NomerGame")
    kb.adjust(1, 2, 1)
    return kb.as_markup()

def fmt_money(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n/1e9:.1f} млрд ₽".replace(".", ",")
    if n >= 1_000_000:
        return f"{n/1e6:.1f} млн ₽".replace(".", ",")
    return f"{n:,} ₽".replace(",", " ")

# ---------- /start ----------
@dp.message(CommandStart())
async def start(msg: Message):
    payload = (msg.text or "").split(maxsplit=1)
    payload = payload[1] if len(payload) > 1 else ""

    if payload.startswith("share_"):
        await handle_share(msg, payload[6:])
        return

    name = html.escape(msg.from_user.first_name or "игрок")
    text = (
        f"👋 <b>Привет, {name}!</b>\n\n"
        "Это <b>Генератор телефонных номеров</b> — коллекционная игра, "
        "где ты крутишь случайные номера, собираешь редкие находки "
        "и соревнуешься с другими игроками.\n\n"
        "💡 <b>Как играть:</b>\n"
        "• 🎰 Крути номера — 10 энергии за прокрутку\n"
        "• 🎁 Кейс за 50 энергии — только Редкий и выше\n"
        "• 💾 Оставляй ценные номера в коллекции\n"
        "• 💰 Продавай дубликаты за игровые рубли\n"
        "• 🏆 Поднимайся в глобальном рейтинге\n\n"
        "⚡ Энергия восстанавливается сама — 1 ед. каждые 5 минут.\n\n"
        "Все номера и деньги — <b>игровые</b>, не настоящие."
    )
    await msg.answer(text, reply_markup=main_kb(), parse_mode="HTML")

# ---------- Шаринг карточки ----------
async def handle_share(msg: Message, token: str):
    # В реальном проекте — достаём карточку из БД по token.
    # Здесь показываем красивый превью-заглушку.
    await msg.answer(
        "📨 <b>Тебе поделились номером</b>\n\n"
        "Нажми «Играть», чтобы открыть игру и увидеть полную карточку:\n"
        "• номер\n• оператора\n• редкость\n• стоимость\n• владельца\n\n"
        "И попробуй найти номер дороже!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🎰 Открыть игру", web_app=WebAppInfo(url=WEBAPP_URL))
        ]]),
        parse_mode="HTML",
    )

# ---------- /help ----------
@dp.message(Command("help"))
async def help_cmd(msg: Message):
    await msg.answer(
        "📖 <b>Команды</b>\n\n"
        "/start — открыть игру\n"
        "/help — эта справка\n"
        "/rules — правила игры\n"
        "/top — топ-10 игроков\n"
        "/me — мой профиль\n"
        "/bonus — ежедневный бонус\n",
        reply_markup=main_kb(), parse_mode="HTML",
    )

# ---------- /rules ----------
@dp.message(Command("rules"))
async def rules_cmd(msg: Message):
    text = (
        "📖 <b>Правила NomerGame</b>\n\n"
        "<b>1. Прокрутка</b>\n"
        "Обычная — 10 энергии, шанс редкого 4,3%, эпика 0,65%, легенды 0,05%.\n"
        "Кейс — 50 энергии, всегда Редкий или выше.\n\n"
        "<b>2. Коллекция</b>\n"
        "Оставляй номера — они повышают стоимость коллекции и рейтинг.\n\n"
        "<b>3. Продажа</b>\n"
        "Продавай дубликаты за игровые рубли. Быстрая продажа одной кнопкой "
        "убирает все Обычные и Необычные номера сразу.\n\n"
        "<b>4. Энергия</b>\n"
        "Максимум — 100 (улучшается). Восстановление: +1 за 5 минут. "
        "Пакет +50 энергии стоит 15 000 ₽ — не окупается прокруткой, "
        "это способ ускориться для тех, кто в рейтинге.\n\n"
        "<b>5. Рейтинг</b>\n"
        "Три режима: стоимость коллекции, редкие находки, самый дорогой номер.\n\n"
        "<b>6. Задания</b>\n"
        "Ежедневные, недельные и разовые. За каждое — энергия. "
        "Когда задание выполнено, придёт уведомление, и награду можно забрать в игре.\n\n"
        "<b>7. Поделиться</b>\n"
        "В профиле любого номера — кнопка «Поделиться». Она отправляет другу "
        "карточку с номером, стоимостью и username бота.\n\n"
        "⚠️ Всё это игра: номера, рубли и рейтинг — виртуальные."
    )
    await msg.answer(text, parse_mode="HTML", reply_markup=main_kb())

# ---------- /top ----------
async def fetch_leaderboard(mode="value", limit=10):
    if not API_BASE:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as cl:
            r = await cl.get(f"{API_BASE}/api/leaderboard",
                             params={"mode": mode, "limit": limit})
            if r.status_code != 200:
                return []
            return (r.json() or {}).get("items", [])
    except Exception:
        return []

@dp.message(Command("top"))
async def top_cmd(msg: Message):
    items = await fetch_leaderboard("value", 10)
    if not items:
        await msg.answer("🏆 <b>Топ пока пуст.</b>\nЗайди в игру и стань первым!",
                         parse_mode="HTML", reply_markup=main_kb())
        return
    lines = ["🏆 <b>Топ-10 по стоимости коллекции</b>\n"]
    for i, u in enumerate(items, 1):
        lines.append(
            f"{i}. <b>{html.escape(u['name'])}</b> — "
            f"{fmt_money(u['scoreValue'])}"
        )
    await msg.answer("\n".join(lines), parse_mode="HTML", reply_markup=main_kb())

# ---------- /me ----------
@dp.message(Command("me"))
async def me_cmd(msg: Message):
    # Узнаём профиль через сервер (можно и локально — для демо)
    items = await fetch_leaderboard("value", 500)
    me = next((x for x in items if str(x["id"]) == str(msg.from_user.id)), None)
    if not me:
        await msg.answer("👤 <b>Профиль не найден.</b>\n"
                         "Открой игру и сделай первую прокрутку — "
                         "я запомню твой результат.",
                         parse_mode="HTML", reply_markup=main_kb())
        return
    best = me.get("bestNumber") or "—"
    await msg.answer(
        f"👤 <b>{html.escape(me['name'])}</b>\n"
        f"Уровень: <b>{me['level']}</b>\n"
        f"Прокруток: <b>{me['spins']}</b>\n"
        f"Коллекция: <b>{fmt_money(me['scoreValue'])}</b>\n"
        f"Редких находок: <b>{me['rare']}</b>\n"
        f"Самый дорогой номер: <code>{html.escape(best)}</code>\n"
        f"Стоимость: <b>{fmt_money(me['bestNumberValue'])}</b>",
        parse_mode="HTML", reply_markup=main_kb(),
    )

# ---------- /bonus ----------
@dp.message(Command("bonus"))
async def bonus_cmd(msg: Message):
    await msg.answer(
        "🎁 <b>Ежедневный бонус</b>\n\n"
        "Бонус выдаётся в игре при заходе. Серия посещений "
        "даёт дополнительные награды: 2 дня подряд — +5 энергии, "
        "7 дней — +25 энергии и редкая находка.\n\n"
        "Открывай игру каждый день, чтобы не терять серию.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🎰 Открыть игру", web_app=WebAppInfo(url=WEBAPP_URL))
        ]]),
        parse_mode="HTML",
    )

# ---------- Callback-кнопки ----------
@dp.callback_query(F.data == "rules")
async def cb_rules(cq: CallbackQuery):
    await cq.message.answer(
        "📖 Правила — командой /rules.\nКратко: крути, оставляй, продавай, "
        "соревнуйся. Всё игровое.", reply_markup=main_kb())
    await cq.answer()

@dp.callback_query(F.data.startswith("lb:"))
async def cb_lb(cq: CallbackQuery):
    mode = cq.data.split(":", 1)[1]
    items = await fetch_leaderboard(mode, 10)
    if not items:
        await cq.message.answer("🏆 Пока пусто.")
        await cq.answer(); return
    title = {"value": "по стоимости", "rare": "по редким",
             "expensive": "по дорогому номеру"}.get(mode, "")
    lines = [f"🏆 <b>Топ-10 {title}</b>\n"]
    for i, u in enumerate(items, 1):
        if mode == "expensive":
            score = fmt_money(u["bestNumberValue"])
            extra = f" — <code>{html.escape(u['bestNumber'] or '')}</code>"
        elif mode == "rare":
            score = f"{u['rare']} находок"
            extra = ""
        else:
            score = fmt_money(u["scoreValue"])
            extra = ""
        lines.append(f"{i}. <b>{html.escape(u['name'])}</b> — {score}{extra}")
    await cq.message.answer("\n".join(lines), parse_mode="HTML")
    await cq.answer()

# ---------- Уведомление о выполненном задании ----------
async def push_quest_notification(uid: str, quest_name: str, reward: int):
    """Вызывается из внешней логики (например, из сервера при сохранении прогресса)."""
    try:
        await bot.send_message(
            int(uid),
            f"🎯 <b>Задание выполнено!</b>\n\n"
            f"«{html.escape(quest_name)}»\n"
            f"Награда: <b>+{reward} энергии</b>\n\n"
            f"Зайди в игру и забери награду во вкладке «Задания».",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🎁 Забрать награду",
                                     web_app=WebAppInfo(url=WEBAPP_URL))
            ]]),
            parse_mode="HTML",
        )
    except Exception as e:
        logging.warning("notify failed: %s", e)

# ---------- Запуск ----------
async def set_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="Открыть игру"),
        BotCommand(command="top",   description="Топ-10 игроков"),
        BotCommand(command="me",    description="Мой профиль"),
        BotCommand(command="rules", description="Правила игры"),
        BotCommand(command="bonus", description="Ежедневный бонус"),
    ])

async def main():
    await set_commands()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
