# -*- coding: utf-8 -*-
"""Админ-панель «Лови Номер» внутри Telegram-бота (aiogram 3).

Открывается командой /admin, доступна только ID из переменной NG_ADMIN_IDS (через запятую) в .env.
Возможности: статистика · массовая рассылка (любое сообщение: текст/фото/видео, с кнопкой «Играть») ·
выдача энергии/рублей/билетов одному игроку или всем · поиск игрока, карточка, бан/разбан · топ · история рассылок.

Работает при запуске через main.py (бот и сервер в одном процессе: общая база). Если запускать bot.py отдельно,
модуль сам подключит server.py к той же базе nomergram.db.
"""
import asyncio, html, logging, os, re, time
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import BaseFilter, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

import server as core

log = logging.getLogger("admin")
ADMINS = {int(x) for x in re.split(r"[,\s;]+", os.getenv("NG_ADMIN_IDS") or os.getenv("ADMIN_IDS") or "") if x.strip().lstrip("-").isdigit()}
GAME_URL = ""
MSK = timezone(timedelta(hours=3))


def setup(game_url):
    global GAME_URL
    GAME_URL = game_url
    if not ADMINS:
        print("ℹ️  Админ-панель выключена: укажи NG_ADMIN_IDS=твой_telegram_id в .env (узнать ID — бот @userinfobot).")
    else:
        print(f"🛠  Админ-панель включена для: {', '.join(map(str, sorted(ADMINS)))} (команда /admin)")


class IsAdmin(BaseFilter):
    async def __call__(self, event) -> bool:
        u = getattr(event, "from_user", None)
        return bool(u and u.id in ADMINS)


router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


class BC(StatesGroup):
    content = State()


class GR(StatesGroup):
    amounts = State()


class FIND(StatesGroup):
    query = State()


class MSG(StatesGroup):
    text = State()


# ------------------------------------------------------------------ утилиты
def n(x):
    return f"{int(x or 0):,}".replace(",", " ")


def e(x):
    return html.escape(str(x or ""))


def when(ts):
    return datetime.fromtimestamp(ts, MSK).strftime("%d.%m %H:%M") if ts else "—"


def kb(*rows):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows])


def play_kb():
    if GAME_URL.startswith("https://"):
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎰 Играть", web_app=WebAppInfo(url=GAME_URL))]])
    return None


async def show(cb: CallbackQuery, text, markup=None):
    try:
        await cb.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as ex:
        if "not modified" not in str(ex):
            await cb.message.answer(text, reply_markup=markup)
    await cb.answer()


MENU_TEXT = "🛠 <b>Админ-панель · Лови Номер</b>\nВыбери действие:"
MENU_KB = kb([("📊 Статистика", "adm:stats"), ("🏆 Топ игроков", "adm:top")],
             [("📣 Рассылка", "adm:bc"), ("🎁 Выдать ресурсы", "adm:gr")],
             [("🔎 Найти игрока", "adm:find"), ("📜 История рассылок", "adm:hist")],
             [("✖️ Закрыть", "adm:close")])
BACK = [("« В меню", "adm:home")]


def _label(w):
    w = w.lower()
    if w.startswith(("энерг", "en")) or w == "⚡":
        return "en"
    if w.startswith(("руб", "cash", "деньг")) or w in ("р", "₽"):
        return "cash"
    if w.startswith(("биле", "tk", "ticket")) or w == "🎟":
        return "tk"
    return None


def parse_amounts(text):
    """«10 50000 1» → энергия, рубли, билеты; или с подписями: «энергия 10 рубли 50000», «10⚡ 2🎟». Минус — списать."""
    res, pos, lab = {"en": 0, "cash": 0, "tk": 0}, [], False
    num = label = None
    for tok in re.findall(r"[+-]?\d+|[^\W\d_]+|[⚡₽🎟]", text.replace("\u00a0", " ")):
        if re.fullmatch(r"[+-]?\d+", tok):
            if label:
                res[label] = int(tok); label = None; lab = True
            else:
                if num is not None:
                    pos.append(num)
                num = int(tok)
        else:
            k = _label(tok)
            if not k:
                continue
            if num is not None:
                res[k] = num; num = None; lab = True
            else:
                label = k
    if num is not None:
        pos.append(num)
    if not lab:
        for k, v in zip(("en", "cash", "tk"), pos):
            res[k] = v
    return res


def amounts_text(a, signs=True):
    parts = []
    for k, ic in (("en", "⚡"), ("cash", "₽"), ("tk", "🎟")):
        if a[k]:
            parts.append(f"{a[k]:+,}".replace(",", " ") + f" {ic}")
    return " · ".join(parts) or "ничего"


# ------------------------------------------------------------------ меню
@router.message(Command("admin"))
async def cmd_admin(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(MENU_TEXT, reply_markup=MENU_KB)


@router.message(Command("cancel"), StateFilter("*"))
async def cmd_cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Отменено.", reply_markup=kb(BACK))


@router.callback_query(F.data == "adm:home")
async def cb_home(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await show(cb, MENU_TEXT, MENU_KB)


@router.callback_query(F.data == "adm:close")
async def cb_close(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.delete()
    except TelegramBadRequest:
        pass
    await cb.answer()


# ------------------------------------------------------------------ статистика, топ, история
@router.callback_query(F.data == "adm:stats")
async def cb_stats(cb: CallbackQuery):
    s = await asyncio.to_thread(core.admin_stats)
    t = s["top1"]
    text = (f"📊 <b>Статистика</b>\n\n"
            f"👥 Игроков: <b>{n(s['players'])}</b> (новых за 24 ч: {n(s['new24'])}, за 7 дн: {n(s['new7'])})\n"
            f"🟢 Активны: за 24 ч — <b>{n(s['act24'])}</b>, за 7 дней — <b>{n(s['act7'])}</b>\n"
            f"🤖 Нажали /start: {n(s['botUsers'])} · заблокировали бота: {n(s['botBlocked'])}\n"
            f"🎰 Прокруток всего: {n(s['spins'])}\n"
            f"💰 Общий капитал игроков: {n(s['wealth'])} ₽\n"
            f"👫 Приглашений: {n(s['refs'])}\n"
            f"🚫 Забанено: {n(s['banned'])} · 📣 Рассылок: {n(s['bc'])}\n"
            + (f"🥇 Лидер: {e(t['name'])} — {n(t['v'])} ₽\n" if t else "")
            + f"🗄 База: {s['dbMb']} МБ\n\n<i>«Новых» считаются с момента обновления; у старых игроков дата первого входа неизвестна.</i>")
    await show(cb, text, kb([("🔄 Обновить", "adm:stats")], BACK))


@router.callback_query(F.data == "adm:top")
async def cb_top(cb: CallbackQuery):
    rows = await asyncio.to_thread(core.admin_top, 10)
    lines = [f"{i}. <b>{e(r['name'])}</b> · ур. {r['level']} · {n(r['score_value'])} ₽ · <code>{r['uid']}</code>" for i, r in enumerate(rows, 1)]
    btns = [[(f"{i}. {r['name'][:18]}", f"adm:pl:{r['uid']}")] for i, r in enumerate(rows[:5], 1)]
    await show(cb, "🏆 <b>Топ-10 по капиталу</b>\n\n" + ("\n".join(lines) or "Пока пусто") + "\n\nНажми на имя, чтобы открыть карточку.", kb(*btns, BACK))


@router.callback_query(F.data == "adm:hist")
async def cb_hist(cb: CallbackQuery):
    rows = await asyncio.to_thread(core.bc_history, 8)
    icon = {"done": "✅", "stopped": "⏹", "running": "⏳", "error": "⚠️"}
    lines = [f"{icon.get(r['status'], '•')} #{r['id']} · {when(r['ts'])} · {core.AUDIENCES.get(r['audience'], r['audience'])}\n    доставлено {n(r['sent'])} из {n(r['total'])} · блок {n(r['blocked'])} · ошибок {n(r['failed'])}" for r in rows]
    await show(cb, "📜 <b>История рассылок</b>\n\n" + ("\n".join(lines) or "Рассылок ещё не было."), kb(BACK))


# ------------------------------------------------------------------ игрок: поиск и карточка
@router.callback_query(F.data == "adm:find")
async def cb_find(cb: CallbackQuery, state: FSMContext):
    await state.set_state(FIND.query)
    await show(cb, "🔎 Пришли <b>Telegram-ID</b> игрока или часть его ника.\n/cancel — отмена.", kb(BACK))


@router.message(FIND.query, F.text, ~F.text.startswith("/"))
async def msg_find(m: Message, state: FSMContext):
    rows = await asyncio.to_thread(core.admin_find, m.text)
    if not rows:
        return await m.answer("Никого не нашёл. Попробуй другой запрос или /cancel.")
    await state.clear()
    if len(rows) == 1:
        return await send_card(m, rows[0]["uid"])
    await m.answer("Найдено несколько:", reply_markup=kb(*[[(f"{r['name'][:24]} · {n(r['score_value'])} ₽", f"adm:pl:{r['uid']}")] for r in rows], BACK))


async def card_parts(uid):
    p = await asyncio.to_thread(core.admin_player, uid)
    if not p:
        return "Игрок не найден.", kb(BACK)
    tag = f" @{e(p['username'])}" if p["username"] else ""
    text = (f"👤 <b>{e(p['name'])}</b>{tag}\n<code>{p['id']}</code>\n\n"
            f"Уровень {p['level']} · прокруток {n(p['spins'])}\n"
            f"💰 Капитал: <b>{n(p['wealth'])} ₽</b> (на руках {n(p['cash'])} ₽)\n"
            f"⚡ Энергия: {n(p['en'])} · 🎟 Билетов: {n(p['tk'])}\n"
            f"📱 Номеров: {n(p['nums'])} · лучший {n(p['best'])} ₽\n"
            f"👫 Друзей: {n(p['friends'])}" + (f" · пригласил: <code>{p['inviter']}</code>" if p["inviter"] else "") + "\n"
            f"🕒 Первый вход: {when(p['first'])} · последняя синхронизация: {when(p['updated'])}\n"
            + ("🚫 <b>Забанен</b>\n" if p["banned"] else "") + ("🤖 Заблокировал бота\n" if p["botBlocked"] else ""))
    ban = ("✅ Разбанить", f"adm:ban:{uid}:0") if p["banned"] else ("🚫 Забанить", f"adm:ban:{uid}:1")
    return text, kb([("🎁 Выдать", f"adm:gp:{uid}"), ("✉️ Написать", f"adm:mp:{uid}")], [ban], BACK)


async def send_card(m: Message, uid):
    text, markup = await card_parts(uid)
    await m.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("adm:pl:"))
async def cb_player(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    text, markup = await card_parts(cb.data.split(":")[2])
    await show(cb, text, markup)


@router.callback_query(F.data.startswith("adm:ban:"))
async def cb_ban(cb: CallbackQuery):
    _, _, uid, on = cb.data.split(":")
    await asyncio.to_thread(core.admin_ban, uid, on == "1", f"by {cb.from_user.id}")
    text, markup = await card_parts(uid)
    await show(cb, ("🚫 Игрок забанен: доступ к игре закрыт, из рейтинга убран.\n\n" if on == "1" else "✅ Бан снят.\n\n") + text, markup)


# ------------------------------------------------------------------ сообщение одному игроку
@router.callback_query(F.data.startswith("adm:mp:"))
async def cb_msg_player(cb: CallbackQuery, state: FSMContext):
    uid = cb.data.split(":")[2]
    await state.set_state(MSG.text)
    await state.update_data(uid=uid)
    await show(cb, f"✉️ Пришли сообщение для игрока <code>{uid}</code> (текст, фото — что угодно). /cancel — отмена.", kb(BACK))


@router.message(MSG.text, ~F.text.startswith("/"))
async def msg_to_player(m: Message, state: FSMContext, bot: Bot):
    uid = (await state.get_data()).get("uid")
    await state.clear()
    try:
        await bot.copy_message(chat_id=int(uid), from_chat_id=m.chat.id, message_id=m.message_id, reply_markup=play_kb())
        await m.answer("✅ Отправлено.", reply_markup=kb(BACK))
    except TelegramForbiddenError:
        await asyncio.to_thread(core.mark_blocked, uid)
        await m.answer("Игрок заблокировал бота.", reply_markup=kb(BACK))
    except Exception as ex:
        await m.answer(f"Не отправилось: {e(ex)}", reply_markup=kb(BACK))


# ------------------------------------------------------------------ движок рассылки (общий для рассылки и уведомления о подарке)
RUN = {"task": None, "cancel": None}


async def deliver(ids, send_one, progress=None, cancel: asyncio.Event = None):
    """Шлёт по одному с паузой ≈20 сообщений/сек (лимит Telegram — 30). Возвращает (доставлено, ошибок, заблокировали, остановлено)."""
    sent = failed = blocked = 0
    last = time.monotonic()
    for i, uid in enumerate(ids, 1):
        if cancel is not None and cancel.is_set():
            return sent, failed, blocked, True
        for _ in range(5):
            try:
                await send_one(uid)
                sent += 1
            except TelegramRetryAfter as ex:
                await asyncio.sleep(ex.retry_after + 1)
                continue
            except TelegramForbiddenError:
                blocked += 1
                await asyncio.to_thread(core.mark_blocked, uid)
            except TelegramBadRequest as ex:
                if any(s in str(ex).lower() for s in ("chat not found", "deactivated", "user not found")):
                    blocked += 1
                    await asyncio.to_thread(core.mark_blocked, uid)
                else:
                    failed += 1
                    log.warning("рассылка → %s: %s", uid, ex)
            except Exception as ex:
                failed += 1
                log.warning("рассылка → %s: %r", uid, ex)
            break
        await asyncio.sleep(0.05)
        if progress and time.monotonic() - last > 3:
            last = time.monotonic()
            try:
                await progress(i, len(ids), sent, failed, blocked)
            except Exception:
                pass
    return sent, failed, blocked, False


# ------------------------------------------------------------------ рассылка
def bc_text(d, count):
    return ("📣 <b>Рассылка</b>\n\n"
            f"Аудитория: <b>{core.AUDIENCES[d['aud']]}</b> — получателей: <b>{n(count)}</b>\n"
            f"Кнопка «🎰 Играть» под сообщением: <b>{'да' if d['btn'] else 'нет'}</b>\n\n"
            "Проверь превью выше. Можно сменить аудиторию, затем нажать «Отправить».")


def bc_kb(d):
    aud = [[(("✅ " if d["aud"] == k else "") + v, f"adm:bca:{k}")] for k, v in core.AUDIENCES.items()]
    return kb(*aud, [(("✅" if d["btn"] else "☐") + " Кнопка «Играть»", "adm:bct"), ("👁 Превью", "adm:bcp")],
              [("🚀 Отправить", "adm:bcs")], [("✖️ Отмена", "adm:home")])


@router.callback_query(F.data == "adm:bc")
async def cb_bc(cb: CallbackQuery, state: FSMContext):
    if RUN["task"] and not RUN["task"].done():
        return await cb.answer("Сейчас уже идёт рассылка — дождись окончания или останови её.", show_alert=True)
    await state.set_state(BC.content)
    await show(cb, "📣 <b>Новая рассылка</b>\n\nПришли сообщение, которое получат игроки: текст, фото, видео, GIF — "
                   "оформление (жирный, ссылки) сохранится. Скопируется как есть.\n/cancel — отмена.", kb(BACK))


@router.message(BC.content, ~F.text.startswith("/"))
async def msg_bc(m: Message, state: FSMContext, bot: Bot):
    d = {"chat": m.chat.id, "mid": m.message_id, "aud": "all", "btn": True}
    await state.update_data(**d)
    await state.set_state(None)
    await bot.copy_message(chat_id=m.chat.id, from_chat_id=m.chat.id, message_id=m.message_id, reply_markup=play_kb())
    cnt = len(await asyncio.to_thread(core.audience_ids, d["aud"], m.from_user.id))
    await m.answer(bc_text(d, cnt), reply_markup=bc_kb(d))


async def bc_state(state: FSMContext):
    d = await state.get_data()
    return d if d.get("mid") else None


@router.callback_query(F.data.startswith("adm:bca:"))
async def cb_bc_aud(cb: CallbackQuery, state: FSMContext):
    d = await bc_state(state)
    if not d:
        return await cb.answer("Начни заново: сообщение не найдено.", show_alert=True)
    d["aud"] = cb.data.split(":")[2]
    await state.update_data(aud=d["aud"])
    cnt = len(await asyncio.to_thread(core.audience_ids, d["aud"], cb.from_user.id))
    await show(cb, bc_text(d, cnt), bc_kb(d))


@router.callback_query(F.data == "adm:bct")
async def cb_bc_btn(cb: CallbackQuery, state: FSMContext):
    d = await bc_state(state)
    if not d:
        return await cb.answer("Начни заново.", show_alert=True)
    d["btn"] = not d["btn"]
    await state.update_data(btn=d["btn"])
    cnt = len(await asyncio.to_thread(core.audience_ids, d["aud"], cb.from_user.id))
    await show(cb, bc_text(d, cnt), bc_kb(d))


@router.callback_query(F.data == "adm:bcp")
async def cb_bc_preview(cb: CallbackQuery, state: FSMContext, bot: Bot):
    d = await bc_state(state)
    if not d:
        return await cb.answer("Начни заново.", show_alert=True)
    await bot.copy_message(chat_id=cb.from_user.id, from_chat_id=d["chat"], message_id=d["mid"], reply_markup=play_kb() if d["btn"] else None)
    await cb.answer("Превью отправлено")


@router.callback_query(F.data == "adm:bcs")
async def cb_bc_confirm(cb: CallbackQuery, state: FSMContext):
    d = await bc_state(state)
    if not d:
        return await cb.answer("Начни заново.", show_alert=True)
    cnt = len(await asyncio.to_thread(core.audience_ids, d["aud"], cb.from_user.id))
    if not cnt:
        return await cb.answer("В этой аудитории никого нет.", show_alert=True)
    await show(cb, f"⚠️ <b>Отправить рассылку?</b>\n\nАудитория: {core.AUDIENCES[d['aud']]}\nПолучателей: <b>{n(cnt)}</b>\n"
                   f"Примерное время: ~{max(1, round(cnt * 0.055 / 60))} мин.\n\nВернуть отправленное нельзя. Остановить можно в любой момент.",
               kb([("✅ Да, отправить", "adm:bcgo")], [("« Назад", "adm:bca:" + d["aud"])]))


@router.callback_query(F.data == "adm:bcgo")
async def cb_bc_go(cb: CallbackQuery, state: FSMContext, bot: Bot):
    d = await bc_state(state)
    if not d:
        return await cb.answer("Начни заново.", show_alert=True)
    if RUN["task"] and not RUN["task"].done():
        return await cb.answer("Рассылка уже идёт.", show_alert=True)
    ids = await asyncio.to_thread(core.audience_ids, d["aud"], cb.from_user.id)
    if not ids:
        return await cb.answer("Получателей нет.", show_alert=True)
    bid = await asyncio.to_thread(core.bc_start, cb.from_user.id, d["aud"], len(ids))
    cancel = asyncio.Event()
    msg = cb.message
    markup = play_kb() if d["btn"] else None
    stop_kb = kb([("⏹ Остановить", "adm:bcstop")])
    await state.clear()
    await show(cb, f"⏳ Рассылка #{bid} запущена: 0 / {n(len(ids))}", stop_kb)

    async def send_one(uid):
        await bot.copy_message(chat_id=uid, from_chat_id=d["chat"], message_id=d["mid"], reply_markup=markup)

    async def progress(i, total, sent, failed, blocked):
        try:
            await msg.edit_text(f"⏳ Рассылка #{bid}: {n(i)} / {n(total)}\n✅ {n(sent)} · 🤖 блок {n(blocked)} · ⚠️ {n(failed)}", reply_markup=stop_kb)
        except TelegramBadRequest:
            pass

    async def job():
        status, sent, failed, blocked = "error", 0, 0, 0
        try:
            sent, failed, blocked, stopped = await deliver(ids, send_one, progress, cancel)
            status = "stopped" if stopped else "done"
        except Exception as ex:
            log.exception("рассылка упала")
            await asyncio.to_thread(core.bc_finish, bid, sent, failed, blocked, "error", repr(ex))
            return await msg.answer(f"⚠️ Рассылка #{bid} прервана ошибкой: {e(ex)}")
        await asyncio.to_thread(core.bc_finish, bid, sent, failed, blocked, status)
        head = "⏹ Остановлена" if status == "stopped" else "✅ Готово"
        text = f"{head} · рассылка #{bid}\n\nДоставлено: <b>{n(sent)}</b> из {n(len(ids))}\n🤖 Заблокировали бота: {n(blocked)}\n⚠️ Ошибок: {n(failed)}"
        try:
            await msg.edit_text(text, reply_markup=kb(BACK))
        except TelegramBadRequest:
            await msg.answer(text, reply_markup=kb(BACK))

    RUN["cancel"] = cancel
    RUN["task"] = asyncio.create_task(job())


@router.callback_query(F.data == "adm:bcstop")
async def cb_bc_stop(cb: CallbackQuery):
    if RUN["cancel"]:
        RUN["cancel"].set()
    await cb.answer("Останавливаю…")


# ------------------------------------------------------------------ выдача ресурсов
GR_HELP = ("Пришли числа: <code>энергия рубли билеты</code>\n"
           "Например: <code>10 50000 1</code> — +10 ⚡, +50 000 ₽, +1 🎟\n"
           "Можно с подписями: <code>рубли 100000</code> или <code>5⚡ 2🎟</code>. Минус — списать.\n/cancel — отмена.")


@router.callback_query(F.data == "adm:gr")
async def cb_gr(cb: CallbackQuery):
    await show(cb, "🎁 <b>Выдать ресурсы</b>\n\nОдному игроку: «Найти игрока» → карточка → «Выдать».\nВсем игрокам — кнопка ниже.",
               kb([("🌍 Всем игрокам", "adm:ga")], [("🔎 Найти игрока", "adm:find")], BACK))


@router.callback_query(F.data.in_({"adm:ga"}) | F.data.startswith("adm:gp:"))
async def cb_gr_target(cb: CallbackQuery, state: FSMContext):
    target = "all" if cb.data == "adm:ga" else cb.data.split(":")[2]
    await state.set_state(GR.amounts)
    await state.update_data(target=target)
    who = "<b>ВСЕМ игрокам</b>" if target == "all" else f"игроку <code>{target}</code>"
    await show(cb, f"🎁 Выдача {who}\n\n{GR_HELP}", kb(BACK))


@router.message(GR.amounts, F.text, ~F.text.startswith("/"))
async def msg_gr(m: Message, state: FSMContext):
    a = parse_amounts(m.text)
    if not any(a.values()):
        return await m.answer("Не вижу чисел. Пример: <code>10 50000 1</code>\n\n" + GR_HELP)
    if any(abs(v) > 10**9 for v in a.values()):
        return await m.answer("Слишком большое число (максимум 1 000 000 000).")
    d = await state.get_data()
    await state.update_data(amt=a)
    who = "ВСЕМ игрокам" if d["target"] == "all" else f"игроку {d['target']}"
    await m.answer(f"Выдать {who}:\n<b>{amounts_text(a)}</b>\n\nИгрок получит это в течение ~15 секунд после открытия игры.",
                   reply_markup=kb([("✅ Выдать + уведомить", "adm:gok:1")], [("🤫 Выдать тихо", "adm:gok:0")], [("✖️ Отмена", "adm:home")]))


@router.callback_query(F.data.startswith("adm:gok:"))
async def cb_gr_go(cb: CallbackQuery, state: FSMContext, bot: Bot):
    d = await state.get_data()
    a, target = d.get("amt"), d.get("target")
    if not a or not target:
        return await cb.answer("Начни заново.", show_alert=True)
    notify = cb.data.endswith(":1")
    await state.clear()
    done = await asyncio.to_thread(core.admin_grant, target, a["en"], a["cash"], a["tk"])
    if not done:
        return await show(cb, "Никому не начислено: у игрока нет сохранения (не открывал игру) или он забанен.", kb(BACK))
    text = f"✅ Начислено игрокам: <b>{n(len(done))}</b>\n{amounts_text(a)}"
    if notify and (a["en"] > 0 or a["cash"] > 0 or a["tk"] > 0):
        pos = " · ".join(f"+{n(a[k])} {ic}" for k, ic in (("en", "⚡"), ("cash", "₽"), ("tk", "🎟")) if a[k] > 0)
        note = f"🎁 <b>Подарок от администрации!</b>\nНачислено: <b>{pos}</b>\nОткрой игру — баланс обновится сам."
        markup = play_kb()

        async def one(uid):
            await bot.send_message(int(uid), note, reply_markup=markup)

        if len(done) == 1:
            await deliver(done, one)
        else:
            asyncio.create_task(deliver(done, one))
            text += "\nУведомления рассылаются в фоне."
    await show(cb, text, kb(BACK))
