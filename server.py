#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
НомерГрам — сервер (только стандартная библиотека Python 3.9+, плюс Pillow для картинок-карточек).

Что делает:
  • отдаёт игру (папка game/) и API на ОДНОМ домене — никаких проблем с CORS и смешанным контентом;
  • /api/state      — облачное сохранение, синхронизация телефон ⇄ ПК (версии rev, без «затирания» чужого прогресса);
  • /api/leaderboard — общий рейтинг по капиталу (баланс + стоимость номеров);
  • /api/friends…   — рефералы и награды;
  • /api/share, /api/share/send, /card.png, /s — карточка номера: фото в любой чат / в чат с ботом / ссылка с превью;
  • /api/health, /api/diag — быстрая проверка, что всё настроено;
  • HTTPS на порту 443 напрямую (SSL_CERT / SSL_KEY), если хостинг не даёт готовый HTTPS.

Запуск:  python3 server.py      (настройки берутся из файла .env рядом со скриптом)
"""
import hashlib, hmac, html, json, mimetypes, os, re, secrets, sqlite3, ssl, sys, threading, time, urllib.request, uuid
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse

BASE = Path(__file__).resolve().parent


def load_env():
    f = BASE / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()
E = os.getenv
BOT_TOKEN = (E("BOT_TOKEN") or E("NG_BOT_TOKEN") or "").strip()
BOT_USERNAME = (E("NG_BOT_USERNAME") or E("BOT_USERNAME") or "RandomNumberPhoneBot").lstrip("@")
PUBLIC_URL = (E("PUBLIC_URL") or "").rstrip("/")
HOST = E("HOST", "0.0.0.0")
PORT = int(E("PORT") or E("SERVER_PORT") or 8000)
def _p(x):
    return str((BASE / x) if x and not os.path.isabs(x) else x) if x else ""


SSL_CERT, SSL_KEY = _p(E("SSL_CERT", "")), _p(E("SSL_KEY", ""))
DB_PATH = E("NG_DB", str(BASE / "nomergram.db"))
INITDATA_MAX_AGE = int(E("INITDATA_MAX_AGE", str(14 * 86400)))
# Меняешь эту строку (или переменную окружения) — у ВСЕХ игроков один раз начинается чистый аккаунт.
DATA_EPOCH = E("DATA_EPOCH", "2026-10-30-reset-1")
HIDDEN_IDS = {x.strip() for x in E("NG_HIDE_IDS", "").split(",") if x.strip()}
INTERNAL_SECRET = E("NG_NOTIFY_SECRET") or hashlib.sha256(("ng-internal:" + BOT_TOKEN).encode()).hexdigest()
for cand in (E("GAME_DIR"), BASE / "game", BASE / "NomerGame_FULL_Project" / "game", BASE):
    if cand and (Path(cand) / "index.html").exists():
        GAME_DIR = Path(cand)
        break
else:
    GAME_DIR = BASE / "game"

REF_FRIEND_BONUS = {"en": 50, "cash": 25000}                      # новичку по ссылке
REF_INVITER_REWARD = {"en": 30, "cash": 20000, "tk": 0}           # пригласившему за каждого активного друга
REF_MILESTONES = {3: {"cash": 100000, "tk": 1}, 10: {"cash": 400000, "tk": 3, "en": 100}, 25: {"cash": 1500000, "tk": 10, "en": 200}}
REF_ACTIVE_SPINS = 5
REF_GUARANTEE = {"friends": 3, "rarity": 2}                       # 3 друга → гарантированный «Редкий» номер

LOCK = threading.RLock()
DB = sqlite3.connect(DB_PATH, check_same_thread=False)
DB.row_factory = sqlite3.Row
DB.executescript("""
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS saves(uid TEXT PRIMARY KEY, payload TEXT NOT NULL, rev INTEGER NOT NULL DEFAULT 0, updated INTEGER);
CREATE TABLE IF NOT EXISTS players(uid TEXT PRIMARY KEY, name TEXT, level INTEGER DEFAULT 1, spins INTEGER DEFAULT 0, score_value INTEGER DEFAULT 0, updated INTEGER);
CREATE INDEX IF NOT EXISTS idx_players_score ON players(score_value DESC);
CREATE TABLE IF NOT EXISTS referrals(friend TEXT PRIMARY KEY, inviter TEXT, created INTEGER, rewarded INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS pending_refs(friend TEXT PRIMARY KEY, inviter TEXT, created INTEGER);
CREATE TABLE IF NOT EXISTS ref_rewards(id INTEGER PRIMARY KEY AUTOINCREMENT, inviter TEXT, friend TEXT, en INTEGER DEFAULT 0, cash INTEGER DEFAULT 0, tk INTEGER DEFAULT 0, claimed INTEGER DEFAULT 0, created INTEGER);
CREATE TABLE IF NOT EXISTS ref_milestones(uid TEXT, m INTEGER, PRIMARY KEY(uid, m));
""")


def epoch_reset():
    """Единоразовая очистка: если DATA_EPOCH изменился — все аккаунты начинаются с нуля."""
    with LOCK:
        cur = DB.execute("SELECT v FROM meta WHERE k='epoch'").fetchone()
        if cur and cur["v"] == DATA_EPOCH:
            return False
        had = DB.execute("SELECT COUNT(*) c FROM saves").fetchone()["c"]
        for t in ("saves", "players", "referrals", "pending_refs", "ref_rewards", "ref_milestones"):
            DB.execute(f"DELETE FROM {t}")
        DB.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('epoch',?)", (DATA_EPOCH,))
        DB.commit()
        print(f"[reset] эпоха данных → {DATA_EPOCH}; очищено сохранений: {had}")
        return True


epoch_reset()


# ------------------------------------------------------------------ Telegram
def verify_init(init_data):
    if not BOT_TOKEN or not init_data:
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        got = pairs.pop("hash", "")
        check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(hmac.new(secret, check.encode(), hashlib.sha256).hexdigest(), got):
            return None
        if time.time() - int(pairs.get("auth_date", "0")) > INITDATA_MAX_AGE:
            return None
        return int(json.loads(pairs.get("user", "{}")).get("id", 0)) or None
    except Exception:
        return None


def tg_api(method, payload, timeout=15):
    req = urllib.request.Request(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def tg_send_photo(chat_id, png, caption):
    b = uuid.uuid4().hex
    parts = []
    for k, v in (("chat_id", str(chat_id)), ("caption", caption), ("parse_mode", "HTML")):
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="photo"; filename="number.png"\r\nContent-Type: image/png\r\n\r\n'.encode() + png + b"\r\n")
    parts.append(f"--{b}--\r\n".encode())
    req = urllib.request.Request(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto", data=b"".join(parts),
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


# ------------------------------------------------------------------ игровая логика сервера
def wealth_of(st):
    try:
        cash = max(0, min(10**12, int(st.get("cash") or 0)))
        return cash + sum(max(0, min(10**9, int(n.get("v") or 0))) for n in (st.get("col") or []) if isinstance(n, dict))
    except Exception:
        return 0


def touch_player(uid, st):
    name = re.sub(r"[\x00-\x1f<>]", "", str((st.get("user") or {}).get("name") or "Игрок")).strip()[:32] or "Игрок"
    DB.execute("INSERT INTO players(uid,name,level,spins,score_value,updated) VALUES(?,?,?,?,?,?) ON CONFLICT(uid) DO UPDATE SET "
               "name=excluded.name,level=excluded.level,spins=excluded.spins,score_value=excluded.score_value,updated=excluded.updated",
               (uid, name, int(st.get("lv") or 1), int(st.get("spins") or 0), wealth_of(st), int(time.time())))


def check_ref_activation(uid, st):
    if int(st.get("spins") or 0) < REF_ACTIVE_SPINS:
        return
    row = DB.execute("SELECT inviter FROM referrals WHERE friend=? AND COALESCE(rewarded,0)=0", (uid,)).fetchone()
    if row:
        DB.execute("UPDATE referrals SET rewarded=1 WHERE friend=?", (uid,))
        r = REF_INVITER_REWARD
        DB.execute("INSERT INTO ref_rewards(inviter,friend,en,cash,tk,created) VALUES(?,?,?,?,?,?)", (row["inviter"], uid, r["en"], r["cash"], r["tk"], int(time.time())))


def get_state(uid, ref):
    with LOCK:
        row = DB.execute("SELECT payload,rev FROM saves WHERE uid=?", (uid,)).fetchone()
        if row:
            return {"exists": True, "rev": row["rev"], "state": json.loads(row["payload"])}
        inviter = ref if ref.isdigit() else ""
        if not inviter:
            p = DB.execute("SELECT inviter FROM pending_refs WHERE friend=?", (uid,)).fetchone()
            inviter = p["inviter"] if p else ""
        bonus = {}
        if inviter and inviter != uid and DB.execute("SELECT 1 FROM players WHERE uid=?", (inviter,)).fetchone():
            c = DB.execute("INSERT OR IGNORE INTO referrals(friend,inviter,created,rewarded) VALUES(?,?,?,0)", (uid, inviter, int(time.time())))
            if c.rowcount:
                bonus = dict(REF_FRIEND_BONUS)
        DB.execute("DELETE FROM pending_refs WHERE friend=?", (uid,))
        DB.commit()
        return {"exists": False, "rev": 0, "bonus": bonus}


def put_state(uid, state, base_rev):
    with LOCK:
        row = DB.execute("SELECT payload,rev FROM saves WHERE uid=?", (uid,)).fetchone()
        cur = row["rev"] if row else 0
        if row and int(base_rev or 0) != cur:      # устройство отстало → отдаём актуальное сохранение, ничего не затираем
            return {"ok": False, "conflict": True, "rev": cur, "state": json.loads(row["payload"])}
        rev = cur + 1
        state = dict(state)
        state["rev"] = rev
        DB.execute("INSERT INTO saves(uid,payload,rev,updated) VALUES(?,?,?,?) ON CONFLICT(uid) DO UPDATE SET payload=excluded.payload,rev=excluded.rev,updated=excluded.updated",
                   (uid, json.dumps(state, ensure_ascii=False, separators=(",", ":")), rev, int(time.time())))
        if state.get("user"):
            touch_player(uid, state)
        check_ref_activation(uid, state)
        DB.commit()
        return {"ok": True, "rev": rev}


def leaderboard(uid, limit):
    limit = max(1, min(200, limit))
    hid = tuple(HIDDEN_IDS)
    where = f"WHERE uid NOT IN ({','.join('?' * len(hid))})" if hid else ""
    with LOCK:
        rows = DB.execute(f"SELECT uid,name,level,spins,score_value FROM players {where} ORDER BY score_value DESC, updated ASC LIMIT ?", (*hid, limit)).fetchall()
        items = [{"id": r["uid"], "name": r["name"] or "Игрок", "level": r["level"], "spins": r["spins"], "scoreValue": r["score_value"]} for r in rows]
        me = None
        if uid and str(uid) not in HIDDEN_IDS:
            mine = DB.execute("SELECT score_value FROM players WHERE uid=?", (str(uid),)).fetchone()
            if mine:
                gt = DB.execute(f"SELECT COUNT(*) c FROM players {where + ' AND' if where else 'WHERE'} score_value > ?", (*hid, mine["score_value"])).fetchone()["c"]
                me = {"rank": gt + 1, "scoreValue": mine["score_value"]}
        total = DB.execute(f"SELECT COUNT(*) c FROM players {where}", hid).fetchone()["c"]
    return {"items": items, "me": me, "total": total}


def ref_summary(uid):
    with LOCK:
        r = DB.execute("SELECT COUNT(*) c, COALESCE(SUM(COALESCE(rewarded,0)),0) a FROM referrals WHERE inviter=?", (uid,)).fetchone()
        fr = DB.execute("SELECT COALESCE(p.name,'Игрок') n, COALESCE(r.rewarded,0) a FROM referrals r LEFT JOIN players p ON p.uid=r.friend WHERE r.inviter=? ORDER BY r.created DESC LIMIT 20", (uid,)).fetchall()
        p = DB.execute("SELECT COALESCE(SUM(en),0) en, COALESCE(SUM(cash),0) cash, COALESCE(SUM(tk),0) tk FROM ref_rewards WHERE inviter=? AND claimed=0", (uid,)).fetchone()
        got = DB.execute("SELECT 1 FROM ref_milestones WHERE uid=? AND m=?", (uid, 1000 + REF_GUARANTEE["friends"])).fetchone() is not None
    nxt = next((m for m in sorted(REF_MILESTONES) if m > r["a"]), None)
    return {"count": r["c"], "active": r["a"], "friends": [{"name": x["n"], "active": bool(x["a"])} for x in fr],
            "guarantee": {"need": REF_GUARANTEE["friends"], "rarity": REF_GUARANTEE["rarity"], "claimed": got},
            "pending": {"en": p["en"], "cash": p["cash"], "tk": p["tk"]}, "perFriend": REF_INVITER_REWARD, "friendBonus": REF_FRIEND_BONUS,
            "activeSpins": REF_ACTIVE_SPINS, "milestones": {str(k): v for k, v in REF_MILESTONES.items()}, "nextMilestone": nxt}


def friends_claim(uid):
    tot = {"en": 0, "cash": 0, "tk": 0, "nums": []}
    with LOCK:
        for r in DB.execute("SELECT id,en,cash,tk FROM ref_rewards WHERE inviter=? AND claimed=0", (uid,)).fetchall():
            if DB.execute("UPDATE ref_rewards SET claimed=1 WHERE id=? AND claimed=0", (r["id"],)).rowcount:
                for k in ("en", "cash", "tk"):
                    tot[k] += r[k]
        active = DB.execute("SELECT COALESCE(SUM(COALESCE(rewarded,0)),0) a FROM referrals WHERE inviter=?", (uid,)).fetchone()["a"]
        for m, rew in sorted(REF_MILESTONES.items()):
            if active >= m and DB.execute("INSERT OR IGNORE INTO ref_milestones(uid,m) VALUES(?,?)", (uid, m)).rowcount:
                for k, v in rew.items():
                    tot[k] += v
        if active >= REF_GUARANTEE["friends"] and DB.execute("INSERT OR IGNORE INTO ref_milestones(uid,m) VALUES(?,?)", (uid, 1000 + REF_GUARANTEE["friends"])).rowcount:
            tot["nums"].append(REF_GUARANTEE["rarity"])
        DB.commit()
    return {"ok": True, "reward": tot}


# ------------------------------------------------------------------ карточки
_cardgen = None
try:
    sys.path.insert(0, str(BASE))
    import cardgen as _cardgen
except Exception as e:                                   # нет Pillow — всё остальное продолжит работать
    print("cardgen недоступен:", e)


@lru_cache(maxsize=256)
def render_card(num, r, v, why, op, story):
    return _cardgen.render_number_card(num, r, v, why, op, bot=BOT_USERNAME, story=story)


def card_args(src):
    g = lambda k, d="": src.get(k, d)
    def i(k, lo, hi):
        try:
            return max(lo, min(hi, int(g(k, 0) or 0)))
        except (TypeError, ValueError):
            return lo
    return (str(g("num", g("number", "+7 999 000-00-00")))[:24], i("r", 0, 4) if "r" in (src or {}) else i("rarity", 0, 4), i("v", 0, 10**10) if "v" in (src or {}) else i("value", 0, 10**10),
            str(g("why", ""))[:90], str(g("op", ""))[:34])


def base_url(h):
    if PUBLIC_URL:
        return PUBLIC_URL
    host = h.headers.get("X-Forwarded-Host") or h.headers.get("Host") or f"localhost:{PORT}"
    proto = h.headers.get("X-Forwarded-Proto") or ("http" if host.startswith(("localhost", "127.")) else "https")
    return f"{proto}://{host}"


def caption_for(num, value):
    return f"📞 <b>{html.escape(num)}</b>\n💰 Стоимость: <b>{value:,} ₽</b>\n\nА какой выпадет тебе?\n@{BOT_USERNAME}".replace(",", " ")


# ------------------------------------------------------------------ HTTP
class H(BaseHTTPRequestHandler):
    server_version = "NomerGram/2.0"
    protocol_version = "HTTP/1.1"
    timeout = 30

    def log_message(self, f, *a):
        if E("QUIET") != "1":
            super().log_message(f, *a)

    def cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def out(self, code, body, ctype="application/json; charset=utf-8", cache="no-store"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.cors()
        self.end_headers()
        self.wfile.write(body)

    def err(self, code, msg):
        self.out(code, {"ok": False, "error": msg})

    def body(self, limit=2_000_000):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > limit:
            return None
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return None

    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        p, q = u.path, parse_qs(u.query)
        one = lambda k, d="": (q.get(k) or [d])[0]
        try:
            if p == "/api/health":
                return self.out(200, {"ok": True, "epoch": DATA_EPOCH})
            if p == "/api/config":
                return self.out(200, {"epoch": DATA_EPOCH, "botUsername": BOT_USERNAME})
            if p == "/api/diag":
                d = {"ok": True, "epoch": DATA_EPOCH, "botTokenSet": bool(BOT_TOKEN), "publicUrl": PUBLIC_URL or base_url(self),
                     "publicUrlIsHttps": (PUBLIC_URL or base_url(self)).startswith("https://"), "cardgen": _cardgen is not None,
                     "tls": bool(getattr(self.server, "tls", False)), "gameDir": str(GAME_DIR), "players": DB.execute("SELECT COUNT(*) c FROM players").fetchone()["c"]}
                if BOT_TOKEN:
                    try:
                        me = tg_api("getMe", {}, 6)
                        d["bot"] = ("@" + me["result"]["username"]) if me.get("ok") else me
                    except Exception as e:
                        d["bot"] = f"нет связи с Telegram API: {e}"
                return self.out(200, d)
            if p == "/api/state":
                uid = verify_init(one("initData"))
                return self.err(401, "invalid initData") if not uid else self.out(200, get_state(str(uid), one("ref")))
            if p == "/api/leaderboard":
                uid = verify_init(one("initData")) if one("initData") else None
                return self.out(200, leaderboard(uid, int(one("limit", "100") or 100)))
            if p == "/api/friends":
                uid = verify_init(one("initData"))
                return self.err(401, "invalid initData") if not uid else self.out(200, ref_summary(str(uid)))
            if p == "/card.png":
                if _cardgen is None:
                    return self.err(503, "Pillow не установлен")
                num, r, v, why, op = card_args({k: x[0] for k, x in q.items()})
                return self.out(200, render_card(num, r, v, why, op, bool(one("story"))), "image/png", "public, max-age=86400")
            if p == "/s":
                num, r, v, why, op = card_args({k: x[0] for k, x in q.items()})
                img = f"{base_url(self)}/card.png?{urlencode({'num': num, 'r': r, 'v': v, 'why': why, 'op': op})}"
                t = f"{num} · {v:,} ₽".replace(",", " ")
                to = one("to")
                link = to if to.startswith("https://t.me/") else f"https://t.me/{BOT_USERNAME}"
                page = (f'<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>{html.escape(t)}</title>'
                        f'<meta property="og:title" content="{html.escape(t)}"><meta property="og:description" content="А какой выпадет тебе? @{BOT_USERNAME}">'
                        f'<meta property="og:image" content="{html.escape(img)}"><meta name="twitter:card" content="summary_large_image">'
                        f'<body style="margin:0;background:#080808;color:#fff;font:16px system-ui;display:grid;place-items:center;min-height:100vh;text-align:center">'
                        f'<div><img src="{html.escape(img)}" style="max-width:92vw;max-height:70vh;border-radius:18px"><br>'
                        f'<a href="{html.escape(link)}" style="display:inline-block;margin-top:16px;padding:14px 26px;border-radius:24px;background:#fff;color:#111;font-weight:800;text-decoration:none">Играть в НомерГрам</a></div>')
                return self.out(200, page, "text/html; charset=utf-8", "public, max-age=300")
            return self.static(p)
        except Exception as e:
            print("GET error:", p, repr(e))
            return self.err(500, "server error")

    def static(self, p):
        rel = "index.html" if p in ("/", "") else p.lstrip("/")
        f = (GAME_DIR / rel).resolve()
        if not str(f).startswith(str(GAME_DIR.resolve())) or not f.is_file():
            return self.err(404, "not found")
        ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript") or ctype.endswith("json"):
            ctype += "; charset=utf-8"
        data = f.read_bytes()
        if f.name == "index.html":           # единая эпоха данных: сервер подставляет её в игру
            data = data.replace(b"__NG_EPOCH__", DATA_EPOCH.encode())
        return self.out(200, data, ctype, "no-cache")

    def do_POST(self):
        p = urlparse(self.path).path
        b = self.body()
        if b is None:
            return self.err(400, "bad request")
        try:
            if p == "/api/ref-pending":
                if b.get("secret") != INTERNAL_SECRET:
                    return self.err(403, "forbidden")
                fr, inv = str(b.get("friend", "")), str(b.get("inviter", ""))
                if not (fr.isdigit() and inv.isdigit()) or fr == inv:
                    return self.err(400, "bad request")
                with LOCK:
                    DB.execute("INSERT OR IGNORE INTO pending_refs(friend,inviter,created) VALUES(?,?,?)", (fr, inv, int(time.time())))
                    DB.commit()
                return self.out(200, {"ok": True})
            uid = verify_init(b.get("initData", ""))
            if not uid:
                return self.err(401, "invalid initData")
            uid = str(uid)
            if p == "/api/state":
                st = b.get("state")
                if not isinstance(st, dict):
                    return self.err(400, "bad state")
                return self.out(200, put_state(uid, st, b.get("baseRev", 0)))
            if p == "/api/friends/claim":
                return self.out(200, friends_claim(uid))
            if p in ("/api/share", "/api/share/send"):
                return self.share(uid, b, p.endswith("/send"))
            if p == "/api/score":
                return self.out(200, {"ok": True})
            return self.err(404, "not found")
        except Exception as e:
            print("POST error:", p, repr(e))
            return self.err(500, "server error")

    def share(self, uid, b, send):
        if not BOT_TOKEN:
            return self.err(503, "BOT_TOKEN не настроен на сервере")
        num, r, v, why, op = card_args(b)
        if send:                       # фото уходит в личный чат игрока с ботом — потом его можно переслать кому угодно
            if _cardgen is None:
                return self.err(503, "Pillow не установлен на сервере")
            try:
                res = tg_send_photo(uid, render_card(num, r, v, why, op, False), caption_for(num, v))
            except Exception as e:
                return self.err(502, f"Telegram: {e}")
            return self.out(200, {"ok": bool(res.get("ok"))} if res.get("ok") else {"ok": False, "error": str(res.get("description", ""))[:160]})
        pub = PUBLIC_URL or base_url(self)
        if not pub.startswith("https://"):
            return self.err(503, "PUBLIC_URL должен быть https-адресом сервера")
        photo = f"{pub}/card.png?{urlencode({'num': num, 'r': r, 'v': v, 'why': why, 'op': op})}"
        res = {"type": "photo", "id": secrets.token_hex(8), "photo_url": photo, "thumbnail_url": photo, "photo_width": 1080, "photo_height": 1350,
               "caption": caption_for(num, v), "parse_mode": "HTML",
               "reply_markup": {"inline_keyboard": [[{"text": "Крутить свой номер", "url": f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"}]]}}
        try:
            d = tg_api("savePreparedInlineMessage", {"user_id": int(uid), "result": res, "allow_user_chats": True, "allow_bot_chats": False,
                                                     "allow_group_chats": True, "allow_channel_chats": True})
        except Exception as e:
            return self.err(502, f"Telegram: {e}")
        if not d.get("ok"):
            return self.err(502, str(d.get("description", "telegram error"))[:200])
        return self.out(200, {"ok": True, "id": d["result"]["id"]})


def make_server():
    srv = ThreadingHTTPServer((HOST, PORT), H)
    srv.daemon_threads = True
    srv.tls = False
    if SSL_CERT and SSL_KEY and Path(SSL_CERT).exists() and Path(SSL_KEY).exists():
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(SSL_CERT, SSL_KEY)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True, do_handshake_on_connect=False)
        srv.tls = True

        def reload_cert():                       # подхватываем продлённый сертификат без перезапуска
            last = Path(SSL_CERT).stat().st_mtime
            while True:
                time.sleep(3600)
                try:
                    m = Path(SSL_CERT).stat().st_mtime
                    if m != last:
                        ctx.load_cert_chain(SSL_CERT, SSL_KEY)
                        last = m
                        print("[tls] сертификат обновлён")
                except Exception as e:
                    print("[tls] не удалось обновить сертификат:", e)
        threading.Thread(target=reload_cert, daemon=True).start()
    return srv


def main():
    if not BOT_TOKEN:
        print("ВНИМАНИЕ: BOT_TOKEN не задан — вход через Telegram работать не будет.")
    srv = make_server()
    print(f"НомерГрам: {'https' if srv.tls else 'http'}://{HOST}:{PORT}  игра: {GAME_DIR}  БД: {DB_PATH}  эпоха данных: {DATA_EPOCH}")
    if not srv.tls and PORT == 443:
        print("ВНИМАНИЕ: порт 443 без SSL_CERT/SSL_KEY — это обычный HTTP. Telegram откроет игру только по HTTPS (см. README).")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
