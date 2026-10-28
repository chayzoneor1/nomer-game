# server.py — FastAPI-сервер NomerGame
# Запуск: uvicorn server:app --host 0.0.0.0 --port 8000
# Требования: pip install fastapi uvicorn aiosqlite python-dotenv

import os, json, hashlib, secrets, time, io
from pathlib import Path
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

# ---------- API ----------
@app.post("/api/score")
async def post_score(p: ScorePayload):
    uid = verify_telegram_initdata(p.initData)
    if not uid:
        raise HTTPException(401, "invalid initData")
    db: aiosqlite.Connection = app.state.db
    now = int(time.time())
    await db.execute("""
        INSERT INTO players (uid,name,level,spins,score_value,best_number_value,best_number,collection_json,rare,updated)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(uid) DO UPDATE SET
          name=excluded.name, level=excluded.level, spins=excluded.spins,
          score_value=excluded.score_value, best_number_value=excluded.best_number_value,
          best_number=excluded.best_number, collection_json=excluded.collection_json,
          rare=excluded.rare, updated=excluded.updated
    """, (str(uid), p.displayName[:32], p.level, p.spins, p.scoreValue,
          p.bestNumberValue, p.bestNumber, json.dumps(p.collection, ensure_ascii=False),
          p.rare, now))
    await db.commit()
    return {"ok": True}

@app.get("/api/leaderboard")
async def leaderboard(mode: str = "value", limit: int = 50):
    db: aiosqlite.Connection = app.state.db
    order = {"value": "score_value DESC",
             "rare": "rare DESC, score_value DESC",
             "expensive": "best_number_value DESC"}.get(mode, "score_value DESC")
    cur = await db.execute(f"SELECT * FROM players ORDER BY {order} LIMIT ?", (limit,))
    rows = await cur.fetchall()
    items = []
    for r in rows:
        try:
            coll = json.loads(r["collection_json"] or "[]")
        except Exception:
            coll = []
        items.append({
            "id": r["uid"], "name": r["name"] or "Игрок",
            "level": r["level"], "spins": r["spins"],
            "scoreValue": r["score_value"], "rare": r["rare"],
            "bestNumberValue": r["best_number_value"],
            "bestNumber": r["best_number"],
            "collection": coll,
        })
    return {"items": items}

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
    if body.get("secret") != os.getenv("NG_NOTIFY_SECRET", "dev"):
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

# ---------- Карточка номера для шаринга ----------
@app.post("/api/share")
async def share_card(body: dict):
    """Возвращает ссылку на бота с deep-link на карточку номера."""
    num = str(body.get("number", ""))[:20]
    rar = int(body.get("rarity", 0))
    val = int(body.get("value", 0))
    op  = str(body.get("op", ""))[:30]
    owner = str(body.get("owner", "Игрок"))[:32]
    token = secrets.token_urlsafe(8)
    return {
        "ok": True,
        "url": f"https://t.me/{BOT_USERNAME}?start=share_{token}",
        "preview": {
            "number": num, "rarity": rar, "value": val, "op": op, "owner": owner,
        },
        "text": (f"📞 <b>{num}</b>\n"
                 f"Оператор: {op}\n"
                 f"Редкость: {['Обычный','Необычный','Редкий','Эпический','Легендарный'][max(0,min(4,rar))]}\n"
                 f"Стоимость: <b>{val:,} ₽</b>\n"
                 f"Владелец: {owner}\n\n"
                 f"Играть: @{BOT_USERNAME}"),
    }


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
    bonus = {}
    if ref.isdigit() and ref != str(uid):  # новый игрок пришёл по ссылке друга
        c = await db.execute("INSERT OR IGNORE INTO referrals VALUES (?,?,?)", (str(uid), ref, int(time.time())))
        await db.commit()
        if c.rowcount:
            bonus = {"en": 50}
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
    await db.commit()
    return {"ok": True, "ts": ts}


@app.get("/api/friends")
async def friends(initData: str):
    uid = verify_telegram_initdata(initData)
    if not uid:
        raise HTTPException(401, "invalid initData")
    cur = await app.state.db.execute("SELECT COUNT(*) c FROM referrals WHERE inviter=?", (str(uid),))
    return {"count": (await cur.fetchone())["c"]}


# ---------- Карточка номера (картинка для сторис / чата) ----------
RAR_COL = ["#b8bec8", "#76c8ff", "#4b8dff", "#b86bff", "#ffc857"]
RAR_NAME = ["Обычный", "Необычный", "Редкий", "Эпический", "Легендарный"]


def _font(size):
    from PIL import ImageFont
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf",
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf"):
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


@app.get("/card.png")
async def card(num: str = "+7 999 000-00-00", r: int = 0, v: int = 0, why: str = "", op: str = ""):
    from PIL import Image, ImageDraw
    from fastapi.responses import Response
    r = max(0, min(4, r)); col = RAR_COL[r]
    W, H = 1080, 1920
    im = Image.new("RGB", (W, H), "#0b0b0d"); d = ImageDraw.Draw(im)
    for y in range(900):  # мягкое свечение цвета редкости сверху
        a = int(38 * (1 - y / 900)); d.line([(0, y), (W, y)], fill=tuple(int(int(col[i:i+2], 16) * a / 255) + 11 for i in (1, 3, 5)))
    def ctext(t, y, size, fill="#f2f0ec"):
        f = _font(size); w = d.textlength(t, font=f); d.text(((W - w) / 2, y), t, font=f, fill=fill)
    ctext("Н О М Е Р А", 330, 56)
    d.rounded_rectangle([70, 640, 1010, 900], 34, fill="#f1f1ee", outline="#2a2a2a", width=8)
    size = 104
    while d.textlength(num[:24], font=_font(size)) > 840: size -= 4
    ctext(num[:24], 700 + (104 - size) // 2, size, "#16161a")
    ctext(op[:30], 830, 40, "#555")
    ctext(RAR_NAME[r], 1010, 82, col)
    ctext(f"{v:,}".replace(",", " ") + " ₽", 1130, 150)
    ctext(why[:48], 1330, 44, "#9a9aa2")
    ctext("@" + BOT_USERNAME, 1700, 64)
    buf = io.BytesIO(); im.save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/s")
async def share_page(request: Request, to: str = ""):
    from fastapi.responses import HTMLResponse
    from html import escape
    qs = str(request.url.query).split("&to=")[0]
    num = escape(request.query_params.get("num", "Номер")); v = int(request.query_params.get("v", 0) or 0)
    img = f"{request.base_url}card.png?{qs}"
    t = f"{num} · {v:,} ₽".replace(",", " ")
    link = escape(to if to.startswith("https://t.me/") else f"https://t.me/{BOT_USERNAME}")
    return HTMLResponse(f'<meta charset=utf-8><title>{t}</title><meta property="og:title" content="{t}">'
        f'<meta property="og:description" content="А какой выпадет тебе?"><meta property="og:image" content="{escape(img)}">'
        f'<meta name="twitter:card" content="summary_large_image"><meta http-equiv="refresh" content="0;url={link}">')


# ---------- Игра раздаётся с того же домена (ВАЖНО: монтировать последним) ----------
from fastapi.staticfiles import StaticFiles
_GAME = Path(__file__).parent / "NomerGame_FULL_Project" / "game"
if _GAME.exists():
    app.mount("/", StaticFiles(directory=str(_GAME), html=True), name="game")
