# server.py — FastAPI-сервер NomerGame
# Запуск: uvicorn server:app --host 0.0.0.0 --port 8000
# Требования: pip install fastapi uvicorn aiosqlite python-dotenv

import os, sys, json, hashlib, secrets, time, io
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse, urlencode
from dotenv import load_dotenv
load_dotenv()
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import aiosqlite
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DB_PATH = os.getenv("NG_DB", "nomergame.db")
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("NG_BOT_TOKEN", "")  # токен бота из @BotFather
BOT_USERNAME = os.getenv("NG_BOT_USERNAME", "RandomNumberPhoneBot")  # без @
_gu = urlparse(os.getenv("GAME_URL", "").strip())
PUBLIC_URL = os.getenv("PUBLIC_URL") or (f"{_gu.scheme}://{_gu.netloc}" if _gu.netloc else "")  # https-адрес сервера
# общий секрет бот↔сервер: можно задать NG_NOTIFY_SECRET, иначе берётся из токена бота
INTERNAL_SECRET = os.getenv("NG_NOTIFY_SECRET") or hashlib.sha256(("ng-internal:" + BOT_TOKEN).encode()).hexdigest()
HIDDEN_IDS = {x.strip() for x in os.getenv("NG_HIDE_IDS", "").split(",") if x.strip()}  # id, которых не показывать в рейтинге

sys.path.insert(0, str(Path(__file__).parent / "NomerGame_FULL_Project"))
import cardgen  # картинки (карточка номера, баннер)

# Награды за приглашённых друзей
REF_FRIEND_BONUS = {"en": 50, "cash": 25000}                 # новичку по ссылке
REF_INVITER_REWARD = {"en": 30, "cash": 20000, "tk": 0}      # пригласившему за каждого активного друга
REF_MILESTONES = {3: {"cash": 100000, "tk": 1}, 10: {"cash": 500000, "tk": 3, "en": 100}, 25: {"cash": 2000000, "tk": 10, "en": 200}}
REF_ACTIVE_SPINS = 3  # друг считается активным после N прокруток (защита от пустых аккаунтов)

# ---------- БД ----------
async def init_db(conn: aiosqlite.Connection):
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS players (
            uid TEXT PRIMARY KEY,
            name TEXT,
            level INTEGER DEFAULT 1,
            spins INTEGER DEFAULT 0,
            score_value INTEGER DEFAULT 0,
            best_number_value INTEGER DEFAULT 0,
            best_number TEXT,
            collection_json TEXT,
            rare INTEGER DEFAULT 0,
            updated INTEGER
        )""")
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            uid TEXT,
            created INTEGER
        )""")
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS saves (
            uid TEXT PRIMARY KEY,
            payload TEXT,
            updated INTEGER
        )""")
    await conn.execute("CREATE TABLE IF NOT EXISTS referrals (friend TEXT PRIMARY KEY, inviter TEXT, created INTEGER)")
    try:
        await conn.execute("ALTER TABLE referrals ADD COLUMN rewarded INTEGER DEFAULT 0")
    except Exception:
        pass
    await conn.execute("CREATE TABLE IF NOT EXISTS pending_refs (friend TEXT PRIMARY KEY, inviter TEXT, created INTEGER)")
    await conn.execute("""CREATE TABLE IF NOT EXISTS ref_rewards (
        id INTEGER PRIMARY KEY AUTOINCREMENT, inviter TEXT, friend TEXT,
        en INTEGER DEFAULT 0, cash INTEGER DEFAULT 0, tk INTEGER DEFAULT 0, claimed INTEGER DEFAULT 0, created INTEGER)""")
    await conn.execute("CREATE TABLE IF NOT EXISTS ref_milestones (uid TEXT, m INTEGER, PRIMARY KEY(uid, m))")
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT,
            text TEXT,
            claimed INTEGER DEFAULT 0,
            created INTEGER
        )""")
    await conn.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await aiosqlite.connect(DB_PATH)
    app.state.db.row_factory = aiosqlite.Row
    await init_db(app.state.db)
    yield
    await app.state.db.close()

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# ---------- Валидация initData Telegram ----------
def verify_telegram_initdata(init_data: str) -> Optional[int]:
    if not BOT_TOKEN or not init_data:
        return None
    try:
        from urllib.parse import parse_qsl, unquote
        import hmac
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = pairs.pop("hash", "")
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, received_hash):
            return None
        user = json.loads(pairs.get("user", "{}"))
        return int(user.get("id", 0)) or None
    except Exception:
        return None

# ---------- Модели ----------
class ScorePayload(BaseModel):
    initData: str
    displayName: str = "Игрок"
    scoreValue: int = 0
    bestNumberValue: int = 0
    bestNumber: Optional[str] = None
    rare: int = 0
    collection: list = []
    level: int = 1
    spins: int = 0

class SavePayload(BaseModel):
    initData: str
    payload: Dict[str, Any]

# ---------- вспомогательное ----------
def wealth_of(state: dict) -> int:
    """Капитал игрока = баланс + стоимость всех номеров в коллекции (считает сервер, не клиент)."""
    try:
        cash = max(0, min(10**12, int(state.get("cash") or 0)))
        col = state.get("col") or []
        total = sum(max(0, min(10**9, int(n.get("v") or 0))) for n in col if isinstance(n, dict))
        return cash + total
    except Exception:
        return 0


async def touch_player(db, uid: str, state: dict):
    name = str(((state.get("user") or {}).get("name")) or "Игрок")[:32]
    await db.execute("""
        INSERT INTO players (uid,name,level,spins,score_value,updated) VALUES (?,?,?,?,?,?)
        ON CONFLICT(uid) DO UPDATE SET name=excluded.name, level=excluded.level, spins=excluded.spins,
          score_value=excluded.score_value, updated=excluded.updated
    """, (uid, name, int(state.get("lv") or 1), int(state.get("spins") or 0), wealth_of(state), int(time.time())))


async def check_ref_activation(db, uid: str, state: dict):
    """Когда приглашённый друг немного поиграл — пригласившему начисляется награда."""
    if int(state.get("spins") or 0) < REF_ACTIVE_SPINS:
        return
    cur = await db.execute("SELECT inviter FROM referrals WHERE friend=? AND COALESCE(rewarded,0)=0", (uid,))
    row = await cur.fetchone()
    if not row:
        return
    await db.execute("UPDATE referrals SET rewarded=1 WHERE friend=?", (uid,))
    r = REF_INVITER_REWARD
    await db.execute("INSERT INTO ref_rewards (inviter,friend,en,cash,tk,created) VALUES (?,?,?,?,?,?)",
                     (row["inviter"], uid, r["en"], r["cash"], r["tk"], int(time.time())))


# ---------- API ----------
@app.post("/api/score")
async def post_score(p: ScorePayload):
    """Оставлено для совместимости: капитал теперь считается сервером из сохранения (/api/state)."""
    uid = verify_telegram_initdata(p.initData)
    if not uid:
        raise HTTPException(401, "invalid initData")
    return {"ok": True}


@app.get("/api/leaderboard")
async def leaderboard(initData: str = "", limit: int = 100):
    """Общий рейтинг всех игроков по капиталу: баланс + стоимость номеров в коллекции. Номера не отдаём."""
    db: aiosqlite.Connection = app.state.db
    limit = max(1, min(200, limit))
    hidden = tuple(HIDDEN_IDS)
    where = f"WHERE uid NOT IN ({','.join('?' * len(hidden))})" if hidden else ""
    cur = await db.execute(
        f"SELECT uid,name,level,spins,score_value FROM players {where} ORDER BY score_value DESC, updated ASC LIMIT ?",
        (*hidden, limit))
    items = [{"id": r["uid"], "name": r["name"] or "Игрок", "level": r["level"], "spins": r["spins"],
              "scoreValue": r["score_value"]} for r in await cur.fetchall()]
    me = None
    uid = verify_telegram_initdata(initData) if initData else None
    if uid and str(uid) not in HIDDEN_IDS:
        c = await db.execute("SELECT score_value FROM players WHERE uid=?", (str(uid),))
        mine = await c.fetchone()
        if mine:
            c2 = await db.execute(f"SELECT COUNT(*) c FROM players {where + ' AND' if where else 'WHERE'} score_value > ?",
                                  (*hidden, mine["score_value"]))
            me = {"rank": (await c2.fetchone())["c"] + 1, "scoreValue": mine["score_value"]}
    c3 = await db.execute(f"SELECT COUNT(*) c FROM players {where}", hidden)
    return {"items": items, "me": me, "total": (await c3.fetchone())["c"]}


# ---------- Синхронизация сохранений (ПК ↔ телефон) ----------
@app.post("/api/save")
async def push_save(p: SavePayload):
    uid = verify_telegram_initdata(p.initData)
    if not uid:
        raise HTTPException(401, "invalid initData")
    db: aiosqlite.Connection = app.state.db
    await db.execute("""
        INSERT INTO saves (uid,payload,updated) VALUES (?,?,?)
        ON CONFLICT(uid) DO UPDATE SET payload=excluded.payload, updated=excluded.updated
    """, (str(uid), json.dumps(p.payload, ensure_ascii=False), int(time.time())))
    await db.commit()
    return {"ok": True, "updated": int(time.time())}

@app.get("/api/save")
async def pull_save(initData: str):
    uid = verify_telegram_initdata(initData)
    if not uid:
        raise HTTPException(401, "invalid initData")
    db: aiosqlite.Connection = app.state.db
    cur = await db.execute("SELECT payload, updated FROM saves WHERE uid=?", (str(uid),))
    row = await cur.fetchone()
    if not row:
        return {"ok": True, "exists": False}
    return {"ok": True, "exists": True, "updated": row["updated"],
            "payload": json.loads(row["payload"])}

# ---------- Уведомления о заданиях ----------
@app.post("/api/notify")
async def notify(body: dict):
    # вызывается серверной частью бота
    if body.get("secret") != INTERNAL_SECRET:
        raise HTTPException(403, "forbidden")
    uid = str(body.get("uid"))
    text = str(body.get("text", ""))[:400]
    if not uid or not text:
        raise HTTPException(400, "bad request")
    db: aiosqlite.Connection = app.state.db
    await db.execute("INSERT INTO notifications (uid,text,created) VALUES (?,?,?)",
                     (uid, text, int(time.time())))
    await db.commit()
    return {"ok": True}

@app.get("/api/notify")
async def get_notify(initData: str):
    uid = verify_telegram_initdata(initData)
    if not uid:
        raise HTTPException(401, "invalid initData")
    db: aiosqlite.Connection = app.state.db
    cur = await db.execute(
        "SELECT id,text FROM notifications WHERE uid=? AND claimed=0 ORDER BY id LIMIT 20",
        (str(uid),))
    rows = await cur.fetchall()
    return {"items": [{"id": r["id"], "text": r["text"]} for r in rows]}

@app.post("/api/notify/claim")
async def claim_notify(body: dict):
    uid = verify_telegram_initdata(body.get("initData", ""))
    if not uid:
        raise HTTPException(401, "invalid initData")
    ids = body.get("ids", [])
    db: aiosqlite.Connection = app.state.db
    for i in ids:
        await db.execute("UPDATE notifications SET claimed=1 WHERE id=? AND uid=?",
                         (int(i), str(uid)))
    await db.commit()
    return {"ok": True}


# ---------- Поделиться номером: фото-карточка уходит в выбранный чат ----------
def _card_query(body: dict, story: bool = False) -> str:
    q = {"num": str(body.get("number", ""))[:24], "r": max(0, min(4, int(body.get("rarity", 0) or 0))),
         "v": max(0, min(10**10, int(body.get("value", 0) or 0))), "why": str(body.get("why", ""))[:52],
         "op": str(body.get("op", ""))[:34]}
    if story:
        q["story"] = 1
    return urlencode(q)


@app.post("/api/share")
async def share_prepared(body: dict):
    """Готовит сообщение-фото (savePreparedInlineMessage). Мини-апп вызывает Telegram.WebApp.shareMessage(id),
    и пользователю открывается список его чатов: в выбранный уходит фото номера + цена + @юзернейм бота."""
    uid = verify_telegram_initdata(body.get("initData", ""))
    if not uid:
        raise HTTPException(401, "invalid initData")
    if not (BOT_TOKEN and PUBLIC_URL):
        raise HTTPException(503, "PUBLIC_URL/GAME_URL или BOT_TOKEN не настроены")
    num = str(body.get("number", ""))[:24]
    value = max(0, min(10**10, int(body.get("value", 0) or 0)))
    photo = f"{PUBLIC_URL}/card.png?{_card_query(body)}"
    caption = (f"📞 <b>{num}</b>\n💰 Стоимость: <b>{value:,} ₽</b>\n\n".replace(",", " ")
               + f"А какой выпадет тебе?\n@{BOT_USERNAME}")
    result = {"type": "photo", "id": secrets.token_hex(8), "photo_url": photo, "thumbnail_url": photo,
              "photo_width": 1080, "photo_height": 1350, "caption": caption, "parse_mode": "HTML",
              "reply_markup": {"inline_keyboard": [[{"text": "Крутить свой номер",
                                                     "url": f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"}]]}}
    import aiohttp
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
            async with http.post(f"https://api.telegram.org/bot{BOT_TOKEN}/savePreparedInlineMessage",
                                 json={"user_id": uid, "result": result, "allow_user_chats": True,
                                       "allow_bot_chats": False, "allow_group_chats": True,
                                       "allow_channel_chats": True}) as resp:
                data = await resp.json()
    except Exception:
        raise HTTPException(502, "telegram unreachable")
    if not data.get("ok"):
        raise HTTPException(502, str(data.get("description", "telegram error"))[:200])
    return {"ok": True, "id": data["result"]["id"]}


# ---------- Синхронизация состояния ПК <-> телефон (last-write-wins по ts) ----------
@app.get("/api/state")
async def get_state(initData: str, ref: str = ""):
    uid = verify_telegram_initdata(initData)
    if not uid:
        raise HTTPException(401, "invalid initData")
    db = app.state.db
    cur = await db.execute("SELECT payload, updated FROM saves WHERE uid=?", (str(uid),))
    row = await cur.fetchone()
    if row:
        return {"exists": True, "ts": row["updated"], "state": json.loads(row["payload"])}
    # новый игрок: пригласитель берётся из ссылки (?ref=) или из того, что записал бот при /start ref_...
    inviter = ref if ref.isdigit() else ""
    if not inviter:
        c = await db.execute("SELECT inviter FROM pending_refs WHERE friend=?", (str(uid),))
        p = await c.fetchone()
        inviter = p["inviter"] if p else ""
    bonus = {}
    if inviter and inviter != str(uid):
        c = await db.execute("INSERT OR IGNORE INTO referrals (friend,inviter,created,rewarded) VALUES (?,?,?,0)",
                             (str(uid), inviter, int(time.time())))
        if c.rowcount:
            bonus = dict(REF_FRIEND_BONUS)
    await db.execute("DELETE FROM pending_refs WHERE friend=?", (str(uid),))
    await db.commit()
    return {"exists": False, "ts": 0, "bonus": bonus}


@app.post("/api/state")
async def put_state(body: dict):
    uid = verify_telegram_initdata(body.get("initData", ""))
    if not uid:
        raise HTTPException(401, "invalid initData")
    state, ts = body.get("state"), int(body.get("ts") or 0)
    if not isinstance(state, dict) or len(json.dumps(state)) > 2_000_000:
        raise HTTPException(400, "bad state")
    db = app.state.db
    cur = await db.execute("SELECT payload, updated FROM saves WHERE uid=?", (str(uid),))
    row = await cur.fetchone()
    if row and row["updated"] > ts:  # на сервере новее (играли с другого устройства)
        return {"ok": False, "ts": row["updated"], "state": json.loads(row["payload"])}
    await db.execute("""INSERT INTO saves (uid,payload,updated) VALUES (?,?,?)
        ON CONFLICT(uid) DO UPDATE SET payload=excluded.payload, updated=excluded.updated""",
                     (str(uid), json.dumps(state, ensure_ascii=False), ts))
    if state.get("user"):                        # в рейтинге только зарегистрированные игроки
        await touch_player(db, str(uid), state)  # капитал = баланс + стоимость номеров
    await check_ref_activation(db, str(uid), state)
    await db.commit()
    return {"ok": True, "ts": ts}


# ---------- Рефералка ----------
@app.post("/api/ref-pending")
async def ref_pending(body: dict):
    """Бот сообщает, что пользователь нажал /start ref_<id>: так реферал не теряется, даже если игра открыта через меню."""
    if body.get("secret") != INTERNAL_SECRET:
        raise HTTPException(403, "forbidden")
    friend, inviter = str(body.get("friend", "")), str(body.get("inviter", ""))
    if not (friend.isdigit() and inviter.isdigit()) or friend == inviter:
        raise HTTPException(400, "bad request")
    db = app.state.db
    await db.execute("INSERT OR IGNORE INTO pending_refs (friend,inviter,created) VALUES (?,?,?)",
                     (friend, inviter, int(time.time())))
    await db.commit()
    return {"ok": True}


async def _ref_summary(db, uid: str):
    c = await db.execute("SELECT COUNT(*) c, COALESCE(SUM(COALESCE(rewarded,0)),0) a FROM referrals WHERE inviter=?", (uid,))
    r = await c.fetchone()
    c = await db.execute("""SELECT COALESCE(p.name,'Игрок') n, COALESCE(r.rewarded,0) a FROM referrals r
                            LEFT JOIN players p ON p.uid=r.friend WHERE r.inviter=? ORDER BY r.created DESC LIMIT 20""", (uid,))
    friends = [{"name": x["n"], "active": bool(x["a"])} for x in await c.fetchall()]
    c = await db.execute("SELECT COALESCE(SUM(en),0) en, COALESCE(SUM(cash),0) cash, COALESCE(SUM(tk),0) tk FROM ref_rewards WHERE inviter=? AND claimed=0", (uid,))
    p = await c.fetchone()
    nxt = next((m for m in sorted(REF_MILESTONES) if m > r["a"]), None)
    return {"count": r["c"], "active": r["a"], "friends": friends,
            "pending": {"en": p["en"], "cash": p["cash"], "tk": p["tk"]},
            "perFriend": REF_INVITER_REWARD, "friendBonus": REF_FRIEND_BONUS, "activeSpins": REF_ACTIVE_SPINS,
            "milestones": {str(k): v for k, v in REF_MILESTONES.items()}, "nextMilestone": nxt}


@app.get("/api/friends")
async def friends(initData: str):
    uid = verify_telegram_initdata(initData)
    if not uid:
        raise HTTPException(401, "invalid initData")
    return await _ref_summary(app.state.db, str(uid))


@app.post("/api/friends/claim")
async def friends_claim(body: dict):
    """Забрать накопленные награды за друзей. Начисление делает клиент, а сервер гарантирует, что получить можно один раз."""
    uid = verify_telegram_initdata(body.get("initData", ""))
    if not uid:
        raise HTTPException(401, "invalid initData")
    uid = str(uid); db = app.state.db
    tot = {"en": 0, "cash": 0, "tk": 0}
    c = await db.execute("SELECT id,en,cash,tk FROM ref_rewards WHERE inviter=? AND claimed=0", (uid,))
    for r in await c.fetchall():
        res = await db.execute("UPDATE ref_rewards SET claimed=1 WHERE id=? AND claimed=0", (r["id"],))
        if res.rowcount:
            for k in tot:
                tot[k] += r[k]
    c = await db.execute("SELECT COALESCE(SUM(COALESCE(rewarded,0)),0) a FROM referrals WHERE inviter=?", (uid,))
    active = (await c.fetchone())["a"]
    for m, rew in sorted(REF_MILESTONES.items()):
        if active >= m:
            res = await db.execute("INSERT OR IGNORE INTO ref_milestones (uid,m) VALUES (?,?)", (uid, m))
            if res.rowcount:
                for k, v in rew.items():
                    tot[k] += v
    await db.commit()
    return {"ok": True, "reward": tot}


# ---------- Карточка номера (картинка для чата / сторис) ----------
@lru_cache(maxsize=256)
def _render_card(num, r, v, why, op, story):
    return cardgen.render_number_card(num, r, v, why, op, bot=BOT_USERNAME, story=story)


@app.get("/card.png")
async def card(num: str = "+7 999 000-00-00", r: int = 0, v: int = 0, why: str = "", op: str = "", story: int = 0):
    from fastapi.responses import Response
    png = _render_card(num[:24], max(0, min(4, r)), max(0, min(10**10, v)), why[:52], op[:34], bool(story))
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/s")
async def share_page(request: Request, to: str = ""):
    """Запасной вариант для старых клиентов: ссылка с превью-картинкой."""
    from fastapi.responses import HTMLResponse
    from html import escape
    qs = str(request.url.query).split("&to=")[0]
    num = escape(request.query_params.get("num", "Номер")); v = int(request.query_params.get("v", 0) or 0)
    img = f"{(PUBLIC_URL or str(request.base_url).rstrip('/'))}/card.png?{qs}"
    t = f"{num} · {v:,} ₽".replace(",", " ")
    link = escape(to if to.startswith("https://t.me/") else f"https://t.me/{BOT_USERNAME}")
    return HTMLResponse(f'<meta charset=utf-8><title>{t}</title><meta property="og:title" content="{t}">'
        f'<meta property="og:description" content="А какой выпадет тебе? @{BOT_USERNAME}"><meta property="og:image" content="{escape(img)}">'
        f'<meta name="twitter:card" content="summary_large_image"><meta http-equiv="refresh" content="0;url={link}">')


# ---------- Игра раздаётся с того же домена (ВАЖНО: монтировать последним) ----------
from fastapi.staticfiles import StaticFiles
_GAME = Path(__file__).parent / "NomerGame_FULL_Project" / "game"
if _GAME.exists():
    app.mount("/", StaticFiles(directory=str(_GAME), html=True), name="game")
