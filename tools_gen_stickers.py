# -*- coding: utf-8 -*-
"""Генератор единого набора SVG-стикеров (31 шт.) для «Лови Номер».
Правила стиля, общие для всех стикеров:
  • сетка 64×64, фигура целиком внутри 6…58 (ничего не обрезается);
  • белая «вырубка» вокруг силуэта (как у наклейки);
  • тело: градиент сверху вниз (светлый → насыщенный) + тёмная обводка того же цвета, одинаковой толщины;
  • один и тот же глянец сверху на каждой цветной фигуре;
  • детали — белые / тёмные того же оттенка, без чужих цветов."""
import math, re, sys

SW = 2.6          # толщина цветной обводки (снаружи фигуры)
CUT = 3.6         # ширина белой «вырубки» за обводкой

# цвет: (верх, середина, низ, обводка)
PAL = {
    'gold':   ('#fff3b0', '#ffc93c', '#f09a00', '#9a5300'),
    'orange': ('#ffd878', '#ff8f2e', '#e23a1c', '#92200f'),
    'red':    ('#ffa093', '#ef4b5b', '#c61e3a', '#7d1127'),
    'rose':   ('#ffb4d0', '#f4588e', '#d2204f', '#82112f'),
    'purple': ('#e0b8ff', '#9d5ef2', '#6a2bd6', '#3b1488'),
    'blue':   ('#bcd6ff', '#5d8ff6', '#2a54d8', '#142f78'),
    'cyan':   ('#bdf2ff', '#4fc5f1', '#2394d8', '#0f5887'),
    'green':  ('#bbf8cb', '#40d480', '#17a15b', '#0a5c33'),
    'mint':   ('#c0fbe9', '#52e2b8', '#20b48c', '#0a6a52'),
    'gray':   ('#ffffff', '#d3d9e6', '#8f99af', '#464f64'),
    'brown':  ('#f4bd82', '#c47e3f', '#8b4c21', '#4d260c'),
    'slate':  ('#62708f', '#37415e', '#1a2036', '#080b17'),
    'cream':  ('#fffcee', '#f7df9f', '#dcab4c', '#85590f'),
    'navy':   ('#2c3556', '#1a2140', '#0c1226', '#05070f'),
}


def defs():
    out = []
    for k, (a, b, c, _) in PAL.items():
        out.append(f'<linearGradient id="sg-{k}" gradientUnits="userSpaceOnUse" x1="0" y1="6" x2="0" y2="58">'
                   f'<stop offset="0" stop-color="{a}"/><stop offset=".5" stop-color="{b}"/><stop offset="1" stop-color="{c}"/></linearGradient>')
    out.append('<linearGradient id="sg-gloss" gradientUnits="userSpaceOnUse" x1="0" y1="6" x2="0" y2="58">'
               '<stop offset="0" stop-color="#fff" stop-opacity=".55"/><stop offset=".42" stop-color="#fff" stop-opacity=".08"/><stop offset=".5" stop-color="#fff" stop-opacity="0"/></linearGradient>')
    return '\n'.join(out)


def f(x):
    return ('%.2f' % x).rstrip('0').rstrip('.')


class Sticker:
    def __init__(self, sid, rot=0):
        self.sid, self.rot, self.items = sid, rot, []

    # заливная фигура(ы): несколько путей одного цвета сливаются в единый силуэт
    def shape(self, ds, col, gloss=True, rule=None):
        self.items.append(('shape', ds if isinstance(ds, list) else [ds], col, gloss, rule))
        return self

    # линия с обводкой (ручки, дужки, стебли)
    def line(self, d, col, w=4.5):
        self.items.append(('line', d, col, w))
        return self

    # детали поверх (готовый svg)
    def detail(self, svg):
        self.items.append(('detail', svg))
        return self

    def render(self):
        o, b = [], []
        for it in self.items:
            if it[0] == 'shape':
                _, ds, col, gloss, rule = it
                r = f' fill-rule="{rule}"' if rule else ''
                for d in ds:
                    o.append(f'<path d="{d}" fill="#fff" stroke="#fff" stroke-width="{f(2*(SW+CUT))}" stroke-linejoin="round"{r}/>')
                st = PAL[col][3]
                for d in ds:   # обводка снаружи: толстый штрих под заливкой
                    b.append(f'<path d="{d}" fill="{st}" stroke="{st}" stroke-width="{f(2*SW)}" stroke-linejoin="round"{r}/>')
                for d in ds:
                    b.append(f'<path d="{d}" fill="url(#sg-{col})"{r}/>')
                if gloss:
                    for d in ds:
                        b.append(f'<path d="{d}" fill="url(#sg-gloss)"{r}/>')
            elif it[0] == 'line':
                _, d, col, w = it
                o.append(f'<path d="{d}" fill="none" stroke="#fff" stroke-width="{f(w+2*(SW+CUT))}" stroke-linecap="round" stroke-linejoin="round"/>')
                b.append(f'<path d="{d}" fill="none" stroke="{PAL[col][3]}" stroke-width="{f(w+2*SW)}" stroke-linecap="round" stroke-linejoin="round"/>')
                b.append(f'<path d="{d}" fill="none" stroke="url(#sg-{col})" stroke-width="{f(w)}" stroke-linecap="round" stroke-linejoin="round"/>')
            else:
                b.append(it[1])
        # линии обводки (линии не должны перекрывать цветные тела следующих слоёв): рисуем в порядке добавления
        body = ''.join(o) + ''.join(b)
        # порядок: сначала вся белая вырубка, затем слои по порядку
        if self.rot:
            body = f'<g transform="rotate({self.rot} 32 32)">{body}</g>'
        return f'<symbol id="k-{self.sid}" viewBox="0 0 64 64" overflow="visible">{body}</symbol>'


def dk(col):
    return PAL[col][3]


def star_path(cx, cy, ro, ri, n=5, rot=-90):
    pts = []
    for i in range(n * 2):
        r = ro if i % 2 == 0 else ri
        a = math.radians(rot + i * 180 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return 'M' + 'L'.join(f'{f(x)} {f(y)}' for x, y in pts) + 'Z'


def gear_path(cx, cy, ro, ri, n=8):
    pts = []
    step = 2 * math.pi / n
    for i in range(n):
        a = i * step - math.pi / 2
        for da, r in ((-0.30, ri), (-0.17, ro), (0.17, ro), (0.30, ri)):
            pts.append((cx + r * math.cos(a + da * step * 2 / 1.2 * .6), cy + r * math.sin(a + da * step * 2 / 1.2 * .6)))
    return 'M' + 'L'.join(f'{f(x)} {f(y)}' for x, y in pts) + 'Z'


def crescent(c1, r1, c2, r2):
    (x1, y1), (x2, y2) = c1, c2
    d = math.hypot(x2 - x1, y2 - y1)
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h = math.sqrt(r1 * r1 - a * a)
    xm, ym = x1 + a * (x2 - x1) / d, y1 + a * (y2 - y1) / d
    p1 = (xm + h * (y2 - y1) / d, ym - h * (x2 - x1) / d)
    p2 = (xm - h * (y2 - y1) / d, ym + h * (x2 - x1) / d)
    return f'M{f(p1[0])} {f(p1[1])}A{r1} {r1} 0 1 0 {f(p2[0])} {f(p2[1])}A{r2} {r2} 0 0 1 {f(p1[0])} {f(p1[1])}Z'


W = 'fill="#fff"'
S = []

# ---------- валюта и предметы ----------
S.append(Sticker('bolt').shape('M37 6 16 35h13l-4 23 24-32H34z', 'gold')
         .detail('<path d="M35 12 22 31" stroke="#fff" stroke-opacity=".7" stroke-width="2.4" stroke-linecap="round" fill="none"/>'))

S.append(Sticker('coin').shape('M32 7a25 25 0 1 0 0 50 25 25 0 1 0 0-50z', 'gold')
         .detail(f'<circle cx="32" cy="32" r="17.5" fill="none" stroke="{dk("gold")}" stroke-opacity=".55" stroke-width="2"/>'
                 f'<path d="M26 44V21h9.500a6.500 6.500 0 0 1 0 13H26M22 38.500h14" fill="none" stroke="{dk("gold")}" stroke-width="3.400" stroke-linecap="round" stroke-linejoin="round"/>'))

S.append(Sticker('chest').shape('M8 32V27a17 17 0 0 1 17-17h14a17 17 0 0 1 17 17v5z', 'brown')
         .shape('M8 32h48v18a5 5 0 0 1-5 5H13a5 5 0 0 1-5-5z', 'brown')
         .detail(f'<path d="M27 10v45M37 10v45" stroke="{dk("brown")}" stroke-opacity=".0"/>'
                 f'<rect x="26" y="10" width="12" height="45" fill="url(#sg-gold)" stroke="{dk("gold")}" stroke-width="2"/>'
                 f'<path d="M8 32h48" stroke="{dk("brown")}" stroke-width="2.400"/>'
                 f'<rect x="27.500" y="28" width="9" height="11" rx="3" fill="url(#sg-gold)" stroke="{dk("gold")}" stroke-width="2"/>'
                 f'<circle cx="32" cy="33" r="2" fill="{dk("gold")}"/>'))

S.append(Sticker('gift').shape('M11 29h42v23a4 4 0 0 1-4 4H15a4 4 0 0 1-4-4z', 'rose')
         .shape('M8 21a4 4 0 0 1 4-4h40a4 4 0 0 1 4 4v8H8z', 'rose')
         .detail(f'<rect x="28" y="17" width="8" height="39" fill="url(#sg-gold)" stroke="{dk("gold")}" stroke-width="2"/>')
         .shape(['M32 17C26 5 14 6 15 13c1 6 11 4 17 4z', 'M32 17C38 5 50 6 49 13c-1 6-11 4-17 4z'], 'gold'))

S.append(Sticker('ticket', rot=-9)
         .shape('M10 16h44a4 4 0 0 1 4 4v7a5 5 0 0 0 0 10v7a4 4 0 0 1-4 4H10a4 4 0 0 1-4-4v-7a5 5 0 0 0 0-10v-7a4 4 0 0 1 4-4z', 'purple')
         .detail(f'<path d="M43 20v24" stroke="#fff" stroke-opacity=".7" stroke-width="2" stroke-dasharray="3 3.200" fill="none"/>'
                 f'<path d="{star_path(24, 32.500, 9.500, 4.200)}" fill="url(#sg-gold)" stroke="{dk("gold")}" stroke-width="1.800" stroke-linejoin="round"/>'))

S.append(Sticker('trophy')
         .line('M20 14H12v4a10 10 0 0 0 10 10', 'gold', 4)
         .line('M44 14h8v4a10 10 0 0 1-10 10', 'gold', 4)
         .shape('M17 8h30v15a15 15 0 0 1-30 0z', 'gold')
         .shape('M28 37h8v9h-8z', 'gold', gloss=False)
         .shape('M19 46h26a3 3 0 0 1 3 3v5a3 3 0 0 1-3 3H19a3 3 0 0 1-3-3v-5a3 3 0 0 1 3-3z', 'gold')
         .detail(f'<path d="{star_path(32, 21, 7, 3.100)}" fill="#fff" fill-opacity=".85" stroke="{dk("gold")}" stroke-opacity=".7" stroke-width="1.400" stroke-linejoin="round"/>'))

S.append(Sticker('battery').shape('M14 18h28a8 8 0 0 1 8 8v12a8 8 0 0 1-8 8H14a8 8 0 0 1-8-8V26a8 8 0 0 1 8-8z', 'slate')
         .shape('M52 26h3a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-3z', 'slate', gloss=False)
         .detail(f'<rect x="11" y="23" width="8" height="18" rx="3" fill="url(#sg-green)" stroke="{dk("green")}" stroke-width="1.400"/>'
                 f'<rect x="22" y="23" width="8" height="18" rx="3" fill="url(#sg-green)" stroke="{dk("green")}" stroke-width="1.400"/>'
                 f'<rect x="33" y="23" width="8" height="18" rx="3" fill="#fff" fill-opacity=".18" stroke="#fff" stroke-opacity=".3" stroke-width="1.200"/>'))

def circ(cx, cy, r):
    return f'M{f(cx-r)} {f(cy)}a{r} {r} 0 1 0 {2*r} 0a{r} {r} 0 1 0 {-2*r} 0z'


S.append(Sticker('charm').line('M32 33q1 13 9 21', 'green', 4)
         .shape([circ(23.5, 21.5, 11), circ(40.5, 21.5, 11), circ(23.5, 36, 11), circ(40.5, 36, 11)], 'green')
         .detail('<path d="M17 19c1-4 5-6 9-5M34 19c1-4 5-6 9-5" stroke="#fff" stroke-opacity=".6" stroke-width="2.200" stroke-linecap="round" fill="none"/>'
                 f'<path d="M32 29v14M26 29.500 38 42.500M38 29.500 26 42.500" stroke="{dk("green")}" stroke-opacity=".35" stroke-width="1.600" stroke-linecap="round" fill="none"/>'))

S.append(Sticker('auto').shape([gear_path(32, 32, 26, 19.500, 8) + 'M32 21.500a10.500 10.500 0 1 0 0 21 10.500 10.500 0 1 0 0-21z'], 'cyan', rule='evenodd')
         .detail(f'<circle cx="32" cy="32" r="6.500" fill="url(#sg-slate)" stroke="{dk("cyan")}" stroke-width="2"/><circle cx="32" cy="32" r="2" fill="#fff" fill-opacity=".8"/>'))

S.append(Sticker('craft').shape('M29 9Q31 29 53 33Q31 37 29 57Q27 37 5 33Q27 29 29 9z', 'gold')
         .shape('M50 6Q51.500 13 58 14.500Q51.500 16 50 23Q48.500 16 42 14.500Q48.500 13 50 6z', 'gold'))

S.append(Sticker('friends')
         .shape(['M41 11a8 8 0 1 0 0 16 8 8 0 1 0 0-16z', 'M27 56v-3a14 14 0 0 1 14-14h2a14 14 0 0 1 14 14v3z'], 'rose')
         .shape(['M23 15a9 9 0 1 0 0 18 9 9 0 1 0 0-18z', 'M7 57v-4a15 15 0 0 1 15-15h2a15 15 0 0 1 15 15v4z'], 'cyan'))

# ---------- редкость ----------
S.append(Sticker('r0').shape('M10 40C8 26 18 17 32 17s24 9 22 23c-1 10-10 14-22 14S11 50 10 40z', 'gray')
         .detail(f'<circle cx="23" cy="42" r="2.400" fill="{dk("gray")}" fill-opacity=".45"/><circle cx="38" cy="45" r="1.800" fill="{dk("gray")}" fill-opacity=".45"/>'))

S.append(Sticker('r1').shape('M32 6 54 19v26L32 58 10 45V19z', 'green')
         .detail('<path d="M10 19 32 32l22-13M32 32v26" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="2" stroke-linejoin="round"/>'
                 '<path d="M32 6 54 19 32 32 10 19z" fill="#fff" fill-opacity=".28"/>'))

S.append(Sticker('r2').shape('M17 10h30l11 15L32 57 6 25z', 'blue')
         .detail('<path d="M6 25h52M17 10l8 15 7 32 7-32 8-15M25 25l7-15 7 15" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="2" stroke-linejoin="round"/>'
                 '<path d="M17 10h30l-8 15H25z" fill="#fff" fill-opacity=".25"/>'))

S.append(Sticker('r3').shape(['M32 5 45 18v26L32 58 19 44V18z', 'M13 28l8 8v14l-8 6-7-6V36z', 'M51 28l8 8v14l-7 6-8-6V36z'][:1], 'purple')
         .shape('M12 29 19 36v13l-7 5-7-5V36z', 'purple')
         .shape('M52 29 59 36v13l-7 5-7-5V36z', 'purple')
         .detail('<path d="M32 5v53M19 18l13 10 13-10M19 44l13-10 13 10" fill="none" stroke="#fff" stroke-opacity=".5" stroke-width="2" stroke-linejoin="round"/>'
                 '<path d="M32 5 45 18 32 28 19 18z" fill="#fff" fill-opacity=".28"/>'))

S.append(Sticker('r4').shape(['M7 46 10 17l14 14 8-21 8 21 14-14 3 29z', 'M7 46h50v7a3 3 0 0 1-3 3H10a3 3 0 0 1-3-3z'], 'gold')
         .detail(f'<circle cx="10" cy="16" r="3.400" fill="url(#sg-rose)" stroke="{dk("rose")}" stroke-width="1.600"/><circle cx="32" cy="9" r="3.400" fill="url(#sg-rose)" stroke="{dk("rose")}" stroke-width="1.600"/><circle cx="54" cy="16" r="3.400" fill="url(#sg-rose)" stroke="{dk("rose")}" stroke-width="1.600"/>'
                 f'<circle cx="20" cy="51" r="2.200" fill="url(#sg-blue)"/><circle cx="32" cy="51" r="2.200" fill="url(#sg-rose)"/><circle cx="44" cy="51" r="2.200" fill="url(#sg-green)"/>'))

# ---------- интерфейс ----------
red7 = dk('red'); gr7 = dk('green')
S.append(Sticker('reels').shape('M16 14h32a10 10 0 0 1 10 10v16a10 10 0 0 1-10 10H16A10 10 0 0 1 6 40V24a10 10 0 0 1 10-10z', 'slate')
         .detail(''.join(f'<rect x="{x}" y="20" width="13" height="24" rx="4" fill="url(#sg-gray)" stroke="{dk("gray")}" stroke-width="1.400"/>'
                         f'<path d="M{x+3.200} 26.500h6.600l-3.600 11" fill="none" stroke="{c}" stroke-width="2.800" stroke-linecap="round" stroke-linejoin="round"/>'
                         for x, c in ((11, red7), (25.500, gr7), (40, red7)))))

S.append(Sticker('palette').shape('M32 7C16 7 6 18 6 31c0 14 11 26 25 26 7 0 8-6 5-10-3-3-1-8 5-8h6c7 0 11-5 11-11C58 16 47 7 32 7z', 'cream')
         .detail(f'<circle cx="19" cy="31" r="4.600" fill="url(#sg-red)" stroke="{dk("red")}" stroke-width="1.600"/><circle cx="27" cy="19" r="4.600" fill="url(#sg-gold)" stroke="{dk("gold")}" stroke-width="1.600"/>'
                 f'<circle cx="41" cy="18" r="4.600" fill="url(#sg-green)" stroke="{dk("green")}" stroke-width="1.600"/><circle cx="50" cy="29" r="4.600" fill="url(#sg-blue)" stroke="{dk("blue")}" stroke-width="1.600"/>'))

S.append(Sticker('check').shape('M32 7a25 25 0 1 0 0 50 25 25 0 1 0 0-50z', 'green')
         .detail(f'<path d="M20 33.500 28.500 42 44 25" fill="none" stroke="{dk("green")}" stroke-opacity=".55" stroke-width="9" stroke-linecap="round" stroke-linejoin="round" transform="translate(0 1.400)"/>'
                 '<path d="M20 33.500 28.500 42 44 25" fill="none" stroke="#fff" stroke-width="6.400" stroke-linecap="round" stroke-linejoin="round"/>'))

S.append(Sticker('arrow').shape('M8 24h26V11l24 21-24 21V40H8z', 'gold'))

S.append(Sticker('fire').shape('M33 5c3 12 17 17 17 35 0 11-8 18-18 18S14 51 14 40c0-8 5-12 8-18 2 6 5 8 7 8-1-9-1-17 4-25z', 'orange')
         .shape('M32 31c3 8 10 10 10 17 0 6-5 9-10 9s-10-3-10-9c0-6 7-9 10-17z', 'gold'))

S.append(Sticker('star').shape(star_path(32, 33, 27, 12.400), 'gold'))

S.append(Sticker('lock')
         .line('M20 29V22a12 12 0 0 1 24 0v7', 'gray', 5)
         .shape('M14 28h36a4 4 0 0 1 4 4v20a5 5 0 0 1-5 5H15a5 5 0 0 1-5-5V32a4 4 0 0 1 4-4z'.replace('M14 28h36', 'M16 28h32'), 'gold')
         .detail(f'<circle cx="32" cy="40" r="4.200" fill="{dk("gold")}"/><path d="M32 41v8" stroke="{dk("gold")}" stroke-width="3.400" stroke-linecap="round"/>'))

S.append(Sticker('medal')
         .shape('M17 6h12l7 25-12 5z', 'red').shape('M47 6H35l-7 25 12 5z', 'red')
         .shape('M32 25a16 16 0 1 0 0 32 16 16 0 1 0 0-32z', 'gold')
         .detail(f'<circle cx="32" cy="41" r="10.500" fill="none" stroke="{dk("gold")}" stroke-opacity=".55" stroke-width="1.800"/>'
                 f'<path d="{star_path(32, 41, 6.600, 2.900)}" fill="#fff" fill-opacity=".9" stroke="{dk("gold")}" stroke-opacity=".6" stroke-width="1.200" stroke-linejoin="round"/>'))

S.append(Sticker('chart').shape('M12 30h12a4 4 0 0 1 4 4v20H8V34a4 4 0 0 1 4-4z'.replace('M12 30h12a4 4 0 0 1 4 4v20H8V34a4 4 0 0 1 4-4z', 'M12 34h10a4 4 0 0 1 4 4v16H8V38a4 4 0 0 1 4-4z'), 'cyan')
         .shape('M30 22h10a4 4 0 0 1 4 4v28H26V26a4 4 0 0 1 4-4z', 'green')
         .shape('M48 10h4a4 4 0 0 1 4 4v40H44V14a4 4 0 0 1 4-4z'.replace('M48 10h4a4 4 0 0 1 4 4v40H44V14a4 4 0 0 1 4-4z', 'M48 12h6a4 4 0 0 1 4 4v38H44V16a4 4 0 0 1 4-4z'), 'gold'))

S.append(Sticker('ghost').shape('M12 56V30a20 20 0 0 1 40 0v26l-7-6-6.500 6-6.500-6-6.500 6-6.500-6z', 'cyan')
         .detail(f'<circle cx="25" cy="30" r="4.600" fill="#fff"/><circle cx="39" cy="30" r="4.600" fill="#fff"/><circle cx="26" cy="31" r="2.200" fill="{dk("cyan")}"/><circle cx="40" cy="31" r="2.200" fill="{dk("cyan")}"/>'
                 f'<path d="M28 39q4 3.600 8 0" fill="none" stroke="{dk("cyan")}" stroke-width="2.200" stroke-linecap="round"/>'))

S.append(Sticker('moon').shape(crescent((28, 32), 23, (41, 24), 19), 'purple')
         .shape('M50 38Q51.200 44.800 58 46Q51.200 47.200 50 54Q48.800 47.200 42 46Q48.800 44.800 50 38z', 'gold'))

# ---------- маскот ----------
MAS_BODY = 'M25 7h14a10 10 0 0 1 10 10v30a10 10 0 0 1-10 10H25A10 10 0 0 1 15 47V17A10 10 0 0 1 25 7z'
MAS_SCREEN = 'M23 13h18a6 6 0 0 1 6 6v22a6 6 0 0 1-6 6H23a6 6 0 0 1-6-6V19a6 6 0 0 1 6-6z'


def mascot(sid, face):
    s = Sticker(sid).shape(MAS_BODY, 'mint')
    s.detail(f'<path d="{MAS_SCREEN}" fill="url(#sg-navy)" stroke="{dk("mint")}" stroke-width="1.800"/>'
             f'<path d="M20 20a4 4 0 0 1 4-4h5" fill="none" stroke="#fff" stroke-opacity=".28" stroke-width="2" stroke-linecap="round"/>'
             f'<circle cx="32" cy="53" r="2.200" fill="{dk("mint")}" fill-opacity=".6"/>' + face)
    return s


cheeks = '<circle cx="22.500" cy="38" r="2.800" fill="#ff7aa8" fill-opacity=".65"/><circle cx="41.500" cy="38" r="2.800" fill="#ff7aa8" fill-opacity=".65"/>'
S.append(mascot('mascot', '<circle cx="26" cy="27" r="3.600" fill="#fff"/><circle cx="38" cy="27" r="3.600" fill="#fff"/><circle cx="26.600" cy="27.600" r="1.700" fill="#0c1226"/><circle cx="38.600" cy="27.600" r="1.700" fill="#0c1226"/>'
                + cheeks + '<path d="M27 36q5 5 10 0" fill="none" stroke="#fff" stroke-width="2.400" stroke-linecap="round"/>'))
S.append(mascot('mascot-wow', '<circle cx="26" cy="26" r="4.800" fill="#fff"/><circle cx="38" cy="26" r="4.800" fill="#fff"/><circle cx="26" cy="26" r="2.300" fill="#0c1226"/><circle cx="38" cy="26" r="2.300" fill="#0c1226"/>'
                + cheeks + '<ellipse cx="32" cy="37.500" rx="3" ry="3.800" fill="#fff"/>'
                '<path d="M54 14l1.200 3.200 3.200 1.200-3.200 1.200L54 23l-1.200-3.400-3.200-1.200 3.200-1.200z" fill="#ffc93c" stroke="#9a5300" stroke-width="1" stroke-linejoin="round"/>'))
S.append(mascot('mascot-sleep', '<path d="M22 28q4 3.600 8 0M34 28q4 3.600 8 0" fill="none" stroke="#fff" stroke-width="2.400" stroke-linecap="round"/>'
                + cheeks + '<path d="M29 37.500h6" stroke="#fff" stroke-width="2.400" stroke-linecap="round"/>'
                '<path d="M50 10h6l-6 7h6" fill="none" stroke="#bdf2ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'))
S.append(mascot('mascot-sad', '<circle cx="26" cy="29" r="3.200" fill="#fff"/><circle cx="38" cy="29" r="3.200" fill="#fff"/><circle cx="26" cy="29.800" r="1.600" fill="#0c1226"/><circle cx="38" cy="29.800" r="1.600" fill="#0c1226"/>'
                '<path d="M21 22l8 2.200M43 22l-8 2.200" fill="none" stroke="#fff" stroke-width="2.200" stroke-linecap="round"/>'
                + cheeks + '<path d="M27 40q5-4.600 10 0" fill="none" stroke="#fff" stroke-width="2.400" stroke-linecap="round"/>'))

ORDER = ['bolt', 'coin', 'chest', 'gift', 'ticket', 'trophy', 'battery', 'charm', 'auto', 'craft', 'friends',
         'r0', 'r1', 'r2', 'r3', 'r4', 'reels', 'palette', 'check', 'arrow', 'fire', 'star', 'lock', 'medal', 'chart', 'ghost', 'moon',
         'mascot', 'mascot-wow', 'mascot-sleep', 'mascot-sad']


def build():
    by = {s.sid: s for s in S}
    assert sorted(by) == sorted(ORDER), set(ORDER) ^ set(by)
    return defs(), '\n'.join(by[i].render() for i in ORDER)


if __name__ == '__main__':
    d, sy = build()
    open(sys.argv[1], 'w', encoding='utf-8').write(d)
    open(sys.argv[2], 'w', encoding='utf-8').write(sy)
    print(len(d) + len(sy), 'bytes')
