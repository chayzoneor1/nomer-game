"""Генерация картинок НомерГрам: карточка номера (для «Поделиться») и приветственный баннер бота.
Используется и сервером (server.py), и ботом (bot.py). Нужен только Pillow.
Шрифт лежит в assets/fonts, поэтому всё одинаково выглядит на любом сервере."""
import io, math, random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

ASSETS = Path(__file__).parent / "assets"
RAR_COL = ["#aeb6c4", "#5ec2ff", "#4b8dff", "#b86bff", "#ffc857"]
RAR_NAME = ["Обычный", "Необычный", "Редкий", "Эпический", "Легендарный"]
BOT_DEFAULT = "RandomNumberPhoneBot"


def _font(size, bold=True):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for p in (ASSETS / "fonts" / name, Path("/usr/share/fonts/truetype/dejavu") / name,
              Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf")):
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _money(v):
    return f"{int(v):,}".replace(",", " ") + " ₽"


def _vgrad(w, h, top, bottom):
    base = Image.new("RGB", (1, h))
    px = base.load()
    for y in range(h):
        px[0, y] = _mix(top, bottom, y / max(1, h - 1))
    return base.resize((w, h))


def _glow(size, center, radius, color, strength=1.0):
    """Мягкое радиальное свечение (RGBA-слой)."""
    w, h = size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = center
    d.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=color + (int(255 * strength),))
    return layer.filter(ImageFilter.GaussianBlur(radius * 0.55))


def _fit(d, text, max_w, size, step=4, bold=True):
    while size > 12 and d.textlength(text, font=_font(size, bold)) > max_w:
        size -= step
    return _font(size, bold)


def _ctext(d, W, text, y, font, fill, shadow=None):
    w = d.textlength(text, font=font)
    if shadow:
        d.text(((W - w) / 2 + shadow[0], y + shadow[1]), text, font=font, fill=shadow[2])
    d.text(((W - w) / 2, y), text, font=font, fill=fill)


def _stars(im, seed, n, region):
    rnd = random.Random(seed)
    d = ImageDraw.Draw(im, "RGBA")
    x0, y0, x1, y1 = region
    for _ in range(n):
        x, y = rnd.randint(x0, x1), rnd.randint(y0, y1)
        r = rnd.choice((1, 1, 2, 2, 3))
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, rnd.randint(25, 90)))


def _plate(num, width, height, accent, scale=1.0):
    """Номерной знак как отдельный RGBA-слой (чтобы его можно было вращать)."""
    S = 2  # суперсэмплинг
    W, H = int(width * S), int(height * S)
    pad = 40 * S
    lay = Image.new("RGBA", (W + pad * 2, H + pad * 2), (0, 0, 0, 0))
    # тень + свечение цвета редкости
    sh = Image.new("RGBA", lay.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([pad, pad + 14 * S, pad + W, pad + H + 14 * S], 34 * S, fill=(0, 0, 0, 170))
    lay.alpha_composite(sh.filter(ImageFilter.GaussianBlur(18 * S)))
    gl = Image.new("RGBA", lay.size, (0, 0, 0, 0))
    ImageDraw.Draw(gl).rounded_rectangle([pad, pad, pad + W, pad + H], 34 * S, fill=_rgb(accent) + (120,))
    lay.alpha_composite(gl.filter(ImageFilter.GaussianBlur(26 * S)))
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle([pad, pad, pad + W, pad + H], 32 * S, fill="#14141a")
    d.rounded_rectangle([pad + 5 * S, pad + 5 * S, pad + W - 5 * S, pad + H - 5 * S], 28 * S, fill="#f4f4f1")
    d.rounded_rectangle([pad + 16 * S, pad + 16 * S, pad + W - 16 * S, pad + H - 16 * S], 20 * S, outline="#1b1b22", width=4 * S)
    # цветная полоса-акцент слева
    d.rounded_rectangle([pad + 16 * S, pad + 16 * S, pad + 70 * S, pad + H - 16 * S], 20 * S, fill=accent)
    d.rectangle([pad + 50 * S, pad + 16 * S, pad + 70 * S, pad + H - 16 * S], fill=accent)
    f = _font(int(22 * S), True)
    d.text((pad + 43 * S - d.textlength("RUS", font=f) / 2, pad + H / 2 - 14 * S), "RUS", font=f, fill="#0f0f13")
    # номер
    txt = num[:24]
    fnt = _fit(d, txt, W - 160 * S, int(height * 0.50 * S), step=4 * S)
    tw = d.textlength(txt, font=fnt)
    tx = pad + 70 * S + (W - 86 * S - tw) / 2
    bbox = d.textbbox((0, 0), txt, font=fnt)
    ty = pad + (H - (bbox[3] - bbox[1])) / 2 - bbox[1]
    d.text((tx, ty), txt, font=fnt, fill="#15151a")
    out = lay.resize((lay.width // S, lay.height // S), Image.LANCZOS)
    if scale != 1.0:
        out = out.resize((int(out.width * scale), int(out.height * scale)), Image.LANCZOS)
    return out


def _bg(W, H, accent, seed=1):
    acc = _rgb(accent)
    im = _vgrad(W, H, (13, 12, 22), (6, 6, 10)).convert("RGBA")
    im.alpha_composite(_glow((W, H), (W // 2, int(H * 0.30)), int(W * 0.62), acc, 0.34))
    im.alpha_composite(_glow((W, H), (int(W * 0.12), int(H * 0.88)), int(W * 0.5), (80, 60, 220), 0.20))
    im.alpha_composite(_glow((W, H), (int(W * 0.95), int(H * 0.72)), int(W * 0.45), (46, 230, 197), 0.10))
    _stars(im, seed, 130, (0, 0, W, H))
    return im


def _pill(d, cx, y, text, font, fg, bg, padx=34, pady=14, outline=None):
    w = d.textlength(text, font=font)
    bb = d.textbbox((0, 0), text, font=font)
    h = bb[3] - bb[1]
    x0, x1 = cx - w / 2 - padx, cx + w / 2 + padx
    d.rounded_rectangle([x0, y, x1, y + h + pady * 2], (h + pady * 2) // 2, fill=bg, outline=outline, width=3 if outline else 0)
    d.text((cx - w / 2, y + pady - bb[1]), text, font=font, fill=fg)
    return y + h + pady * 2


def render_number_card(num, r=0, v=0, why="", op="", bot=BOT_DEFAULT, story=False):
    """Карточка номера. story=False → 1080×1350 (для чата), True → 1080×1920 (для сторис)."""
    r = max(0, min(4, int(r)))
    acc = RAR_COL[r]
    W, H = (1080, 1920) if story else (1080, 1350)
    im = _bg(W, H, acc, seed=r + 7)
    d = ImageDraw.Draw(im)
    k = H / 1350.0
    # шапка
    _ctext(d, W, "Н О М Е Р Г Р А М", int(70 * k), _font(40), "#f2f0ec")
    _ctext(d, W, "симулятор красивых номеров", int(128 * k), _font(26, False), "#8d8da0")
    # плашка редкости
    _pill(d, W // 2, int(230 * k), RAR_NAME[r].upper(), _font(38), "#101014", acc, padx=46, pady=14)
    # знак
    plate = _plate(num, 940, 250, acc)
    im.alpha_composite(plate, ((W - plate.width) // 2, int(370 * k)))
    d = ImageDraw.Draw(im)
    if op:
        _ctext(d, W, op[:34], int(370 * k) + 250 + 62, _font(36, False), "#c9c9d6")
    # цена
    py = int(760 * k)
    _ctext(d, W, "СТОИМОСТЬ", py, _font(30), "#8d8da0")
    gold_a, gold_b = _rgb("#ffe08a"), _rgb("#ff9f1c")
    price = _money(v)
    pf = _fit(d, price, 900, 168, step=6)
    pw = d.textlength(price, font=pf)
    # свечение под ценой
    im.alpha_composite(_glow((W, H), (W // 2, py + 150), 300, _rgb("#ffb300"), 0.22))
    d = ImageDraw.Draw(im)
    tmp = Image.new("L", (W, H), 0)
    ImageDraw.Draw(tmp).text(((W - pw) / 2, py + 52), price, font=pf, fill=255)
    gradient = _vgrad(W, H, gold_a, gold_b).convert("RGBA")
    im.paste(gradient, (0, 0), tmp)
    d = ImageDraw.Draw(im)
    # причины цены
    if why:
        _ctext(d, W, why[:52], py + 270, _font(32, False), "#a8a8b8")
    # низ: юзернейм бота
    by = int(1150 * k) if not story else int(1560 * k) + 40
    d.line([(160, by - 38), (W - 160, by - 38)], fill=(58, 58, 74), width=2)
    _ctext(d, W, "А какой выпадет тебе?", by - 4, _font(34, False), "#c9c9d6")
    _pill(d, W // 2, by + 62, "@" + bot, _font(50), "#0b0b10", "#2ee6c5", padx=54, pady=18)
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()


def render_welcome(bot=BOT_DEFAULT):
    """Баннер приветствия бота, 1280×720."""
    W, H = 1280, 720
    im = _bg(W, H, "#8b5cf6", seed=42)
    d = ImageDraw.Draw(im)
    # левый блок текста
    d.text((72, 92), "НОМЕРГРАМ", font=_font(84), fill="#f6f4ef")
    d.rounded_rectangle([74, 196, 214, 204], 4, fill="#2ee6c5")
    d.text((72, 236), "Крути номера.", font=_font(40, False), fill="#d9d9e6")
    d.text((72, 288), "Лови редкие номера.", font=_font(40, False), fill="#d9d9e6")
    d.text((72, 340), "Стань самым богатым.", font=_font(40), fill="#ffd36e")
    y = 452
    for t in ("Продавай и копи коллекцию", "Рейтинг самых богатых", "Зови друзей — получай подарки"):
        f = _font(26, False)
        w = d.textlength(t, font=f)
        d.rounded_rectangle([72, y, 72 + w + 44, y + 52], 26, fill="#2d2a4a", outline="#4a4580", width=2)
        d.text((94, y + 9), t, font=f, fill="#e8e6ff")
        y += 66
    # правый блок: три знака друг под другом, разной редкости
    items = [("+7 925 123-45-67", 0, -5, (700, 112)), ("+7 977 555-55-55", 3, 3, (708, 262)), ("+7 999 777-77-77", 4, -4, (696, 412))]
    for n, rr, ang, (x, y0) in items:
        pl = _plate(n, 470, 130, RAR_COL[rr])
        pl = pl.rotate(ang, expand=True, resample=Image.BICUBIC)
        im.alpha_composite(pl, (x, y0))
    d = ImageDraw.Draw(im)
    _pill(d, 940, 590, "25 000 000 ₽", _font(36), "#14110a", "#ffc857", padx=40, pady=10)
    _pill(d, 1020, 30, "@" + bot, _font(24), "#0b0b10", "#2ee6c5", padx=24, pady=8)
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()


if __name__ == "__main__":
    (ASSETS / "welcome.png").write_bytes(render_welcome())
    print("welcome.png обновлён")
