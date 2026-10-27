"""NomerGame Telegram Mini App leaderboard starter.
Run: set BOT_TOKEN=123:abc, then python NomerGame_Leaderboard_Server.py
Serve NomerGame_Fixed.html from this same Flask app on HTTPS in production.
"""
import os, json, hmac, hashlib, sqlite3, time
from urllib.parse import parse_qsl
from flask import Flask, request, jsonify, send_file

BOT_TOKEN = os.environ.get('BOT_TOKEN', '').strip()
DB_PATH = os.environ.get('NOMERGAME_DB', 'nomergame.sqlite3')
app = Flask(__name__, static_folder=None)

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute('''CREATE TABLE IF NOT EXISTS players (
        user_id TEXT PRIMARY KEY, name TEXT NOT NULL,
        score_value INTEGER NOT NULL DEFAULT 0, rare INTEGER NOT NULL DEFAULT 0,
        best_number_value INTEGER NOT NULL DEFAULT 0,
        level INTEGER NOT NULL DEFAULT 1, spins INTEGER NOT NULL DEFAULT 0,
        collection_json TEXT NOT NULL DEFAULT '[]',
        updated_at INTEGER NOT NULL DEFAULT 0)''')
    # Upgrade existing databases created by older versions.
    cols = {row[1] for row in con.execute('PRAGMA table_info(players)').fetchall()}
    if 'best_number_value' not in cols:
        con.execute('ALTER TABLE players ADD COLUMN best_number_value INTEGER NOT NULL DEFAULT 0')
    if 'collection_json' not in cols:
        con.execute("ALTER TABLE players ADD COLUMN collection_json TEXT NOT NULL DEFAULT '[]'")
    return con

def telegram_user(init_data):
    if not BOT_TOKEN or not init_data:
        return None
    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    supplied = fields.pop('hash', '')
    if not supplied:
        return None
    check = '\n'.join(f'{k}={v}' for k, v in sorted(fields.items()))
    secret = hmac.new(b'WebAppData', BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, supplied):
        return None
    try:
        if int(time.time()) - int(fields.get('auth_date', '0')) > 86400:
            return None
        user = json.loads(fields['user'])
        if not user.get('id'):
            return None
        return user
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None

@app.get('/')
def index():
    return send_file('NomerGame_Fixed.html' if os.path.exists('NomerGame_Fixed.html') else 'index.html')


def _safe_collection(raw):
    try:
        items = json.loads(raw or '[]')
        if not isinstance(items, list): return []
        out = []
        for n in items[:12]:
            if not isinstance(n, dict): continue
            number = str(n.get('number', ''))[:40]
            try: value = max(0, min(1_000_000_000, int(n.get('value', 0))))
            except (ValueError, TypeError): value = 0
            try: rarity = max(0, min(4, int(n.get('rarity', 0))))
            except (ValueError, TypeError): rarity = 0
            out.append({'number': number, 'value': value, 'rarity': rarity, 'tag': bool(n.get('tag'))})
        return out
    except (ValueError, TypeError): return []

@app.get('/api/leaderboard')
def leaderboard():
    mode = request.args.get('mode', 'value')
    field = 'rare' if mode == 'rare' else ('best_number_value' if mode == 'expensive' else 'score_value')
    with db() as con:
        rows = con.execute(f'''SELECT name, score_value, rare, best_number_value, level, spins, collection_json FROM players
          ORDER BY {field} DESC, level DESC, spins DESC LIMIT 50''').fetchall()
    return jsonify(items=[{'name': r['name'], 'scoreValue': r['score_value'], 'rare': r['rare'], 'bestNumberValue': r['best_number_value'], 'level': r['level'], 'spins': r['spins'], 'collection': _safe_collection(r['collection_json'])} for r in rows])

@app.post('/api/score')
def submit_score():
    payload = request.get_json(silent=True) or {}
    user = telegram_user(payload.get('initData', ''))
    if not user:
        return jsonify(error='invalid_telegram_auth'), 401
    # Starter version: scores come from the client and are not cheat-proof.
    # Production should validate game actions server-side before accepting score updates.
    fallback_name = (' '.join(filter(None, [user.get('first_name', ''), user.get('last_name', '')])) or 'Игрок')[:48]
    requested_name = payload.get('displayName', '')
    # The Telegram identity is still validated server-side; display name is only a public nickname.
    name = (' '.join(str(requested_name).split())[:16] if isinstance(requested_name, str) and len(requested_name.strip()) >= 2 else fallback_name)
    def safe_int(k, low=0, high=10_000_000):
        try: return max(low, min(high, int(payload.get(k, low))))
        except (ValueError, TypeError): return low
    score_value, rare = safe_int('scoreValue'), safe_int('rare')
    best_number_value = safe_int('bestNumberValue')
    safe_collection = _safe_collection(payload.get('collection', []))
    collection_json = json.dumps(safe_collection, ensure_ascii=False)
    score_value = sum(n['value'] for n in safe_collection)
    level, spins = safe_int('level', 1, 10000), safe_int('spins')
    with db() as con:
        old = con.execute('SELECT score_value, rare, best_number_value, level, spins, collection_json FROM players WHERE user_id=?', (str(user['id']),)).fetchone()
        if old:
            # Collection value reflects the current collection (selling numbers lowers it).
            # Lifetime counters remain monotonic across stale device syncs.
            rare = max(rare, old['rare'])
            best_number_value = max(best_number_value, old['best_number_value'])
            level = max(level, old['level'])
            spins = max(spins, old['spins'])
        con.execute('''INSERT INTO players(user_id,name,score_value,rare,best_number_value,level,spins,collection_json,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET name=excluded.name,
          score_value=excluded.score_value, rare=excluded.rare, best_number_value=excluded.best_number_value, level=excluded.level,
          spins=excluded.spins, collection_json=excluded.collection_json, updated_at=excluded.updated_at''',
          (str(user['id']), name, score_value, rare, best_number_value, level, spins, collection_json, int(time.time())))
    return jsonify(ok=True)

if __name__ == '__main__':
    if not BOT_TOKEN:
        raise SystemExit('Set BOT_TOKEN environment variable to your Telegram bot token.')
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '8080')), debug=False)
