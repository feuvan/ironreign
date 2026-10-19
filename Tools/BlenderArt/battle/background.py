"""Art/Battle/Background.png (1920x1080, opaque): the war table behind the 2D hex board.

    Tools/BlenderArt/render.sh Tools/BlenderArt/battle/background.py      (or system python3)

A campaign map of aged silk laid on a dark rosewood war table: the silk sheet is mounted like a
painting (azurite brocade band with mud-gold rules and a woven rosette row, an ivory 隔水 strip,
an ink rule), its field calm in the centre where the board lies, painted only at the margins -
blue-green (青绿) mountain ranges dissolving into bare-silk mist in the top corners, ruled
wave lines in the bottom corners, faint xiangyun clouds, a column of calligraphy (兵者國之大事,
Sunzi; Ma Shan Zheng has simplified forms only: 兵者国之大事) and a cinnabar seal (战) at the lower right.  No cast shadow, no light: a painting.

Slate scales the image to cover the widget, so nothing important sits within ~100 px of an edge.
"""

import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from ironart import REPO_DIR, post  # noqa: E402
from ironart import ui_chrome_gongbi as GB  # noqa: E402
from ironart import ui_chrome_ornament as O  # noqa: E402
from ironart import ui_chrome_paint as P  # noqa: E402
from ironart import ui_chrome_sdf as S  # noqa: E402

W, H = 1920, 1080
SHEET = (58.0, 34.0, 1862.0, 1046.0)
FONT_BRUSH = os.path.join(REPO_DIR, "Content", "Data", "Fonts", "Brush.ttf")


def rgb(h):
    return P.rgb(h)


def over(col, mask, c, a=1.0):
    m = np.clip(mask * a, 0, 1)[..., None]
    c = np.asarray(c, np.float32)
    return col * (1 - m) + c * m


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def table(G):
    """Dark rosewood: warm umber with long grain and a soft lacquer bloom."""
    g1 = S.fbm(G.shape, 90.0, 3, octaves=4, aniso=(6.0, 0.35))
    g2 = S.fbm(G.shape, 18.0, 4, octaves=3, aniso=(10.0, 0.25))
    t = np.clip(0.35 + 0.5 * (g1 - 0.5) + 0.4 * (g2 - 0.5), 0, 1)
    col = P.mix("#2C1D14", "#46301F", t)
    lines = np.clip((g2 - 0.62) * 6, 0, 1)
    col = col * (1 - 0.18 * lines[..., None])
    return col


def mountains(col, G, corner, seed, sheet):
    """Blue-green peaks (青绿) in a top corner, painted peak by peak from the back: tall
    mantou-topped peaks with steep flanks, each its own shape - azurite summit over malachite
    shoulders over an ochre foot - with its own ink contour and two or three fold lines, so the
    overlaps read; three ranges (a pale far one, the main one, a lower near one), each
    dissolving downwards into bare-silk mist and fading towards the centre (the board stays
    calm)."""
    X, Y = G.X, G.Y
    rng = np.random.default_rng(seed)
    sgn = 1 if corner == "left" else -1
    ex = 70.0 if corner == "left" else W - 70.0
    xs = G.xs
    fall = (1 - smooth(260, 640, np.abs(X - ex))) * sheet
    ranges = (  # base y, max height, peaks, opacity, (summit, shoulder, foot) colours, ink
        (292.0, 205.0, 5, 0.42, ("#8EA9C4", "#A9C3BC", "#D3C6A4"), 0.25),
        (338.0, 215.0, 4, 0.82, ("#3E6E98", "#3F8E70", "#BC966C"), 0.6),
        (392.0, 150.0, 3, 0.88, ("#4A79A0", "#4C9A78", "#C4A074"), 0.6),
    )
    for layer, (base, hmax, n_pk, alpha, cols, ink) in enumerate(ranges):
        pk = []
        x = ex + sgn * rng.uniform(10, 40) + sgn * layer * 35
        for k in range(n_pk):
            h = hmax * rng.uniform(0.6, 1.0) * (1.0 - 0.12 * k)
            w = h * rng.uniform(0.5, 0.68)
            pk.append((x, h, w, rng.uniform(-0.12, 0.12)))
            x += sgn * (w * rng.uniform(0.75, 1.15))
        # the tallest at the back, then the others in front
        for (px, h, w, lean) in sorted(pk, key=lambda q: -q[1]):
            u = (xs - px) / w
            f = np.clip(1.0 - np.clip(np.abs(u - lean * (1 - np.abs(u))), 0, 1) ** 2.2, 0, 1) ** 1.1
            jag = S.fbm((1, len(xs)), 9.0, seed + int(px), octaves=2)[0]
            y_top = base - h * f * (0.94 + 0.12 * (jag - 0.5))
            y_top = np.where(f > 0.004, y_top, base + 1000)[None, :]
            rel = (Y - y_top) / max(h, 1.0)
            body = ((rel > 0) & (Y < base)).astype(np.float32)
            if not body.any():
                continue
            n = S.fbm(G.shape, 26.0, seed + 9 + layer + int(px) % 97, octaves=3)
            q = rel + (n - 0.5) * 0.18
            # 晕染: deep azurite at the summit grading into malachite, the ochre foot below; the
            # peak dissolves into a common mist line above the range's base
            c = P.mix(cols[0], cols[1], smooth(0.04, 0.3, q))
            c = P.mix(c, cols[2], smooth(0.42, 0.75, q)[..., None] * np.ones(3))
            mist = 1 - smooth(base - 0.5 * hmax, base, Y)
            m = body * mist * fall * alpha
            col = over(col, m, c)
            if ink <= 0:
                continue
            # contour of this peak (fading down the flanks into the mist)
            below_summit = 1.0 - (base - y_top) / max(h, 1.0)       # 0 at the summit, 1 at the foot
            edge = (np.abs(Y - y_top) < 1.3) * (1 - smooth(0.25, 0.75, below_summit))
            col = over(col, edge.astype(np.float32) * fall, rgb("#22302C"), ink * 0.9)
            # fold lines from below the summit down the body
            for sfold in (-0.42, 0.18, 0.55)[: 2 + int(h > 150)]:
                t = np.linspace(0, 1, 18, dtype=np.float32)
                x0 = px + sfold * w * 0.25
                x1 = px + sfold * w * 0.85
                fx = x0 + (x1 - x0) * t ** 0.8
                ytop_at = float(base - h * 0.96)
                fy = ytop_at + h * (0.12 + 0.5 * t)
                rr = (0.8 * np.sin(np.pi * np.clip(t * 0.9 + 0.1, 0, 1)) + 0.15).astype(np.float32)
                sd = S.sd_polyline(G, np.stack([fx, fy], 1), rr, pad=2)
                col = over(col, S.aa_mask(sd, G) * body * fall * mist, rgb("#22302C"), ink * 0.45)
            # a few 皴 strokes on the flanks
            for _ in range(int(6 + h / 25)):
                uu = rng.uniform(-0.8, 0.8)
                j = int(np.clip(px + uu * w, 0, W - 1))
                if fall[min(H - 1, int(base)), j] < 0.05:
                    continue
                yt = float(y_top[0, j])
                if yt > base:
                    continue
                y0 = yt + rng.uniform(0.1, 0.45) * (base - yt)
                L = rng.uniform(8, 18)
                dx = np.sign(uu) * L * 0.25                              # outward and down
                pnts = np.array([[j, y0], [j + dx * 0.5, y0 + L * 0.5], [j + dx, y0 + L]], np.float32)
                sd = S.sd_polyline(G, pnts, np.array([0.8, 0.6, 0.2], np.float32), pad=2)
                col = over(col, S.aa_mask(sd, G) * fall * mist, rgb("#22302C"), ink * 0.4)
    return col


def waves(col, G, corner, seed):
    """Ruled wave lines (水纹) in a bottom corner: rows of gently undulating ink-blue lines."""
    X, Y = G.X, G.Y
    cx = 230.0 if corner == "left" else W - 230.0
    rng = np.random.default_rng(seed)
    lines = G.empty()
    for r in range(9):
        y = 905 + r * 13
        for seg in range(5):
            xa = cx - 300 + seg * 130 + rng.uniform(-30, 30)
            L = rng.uniform(70, 120)
            xs = np.linspace(xa, xa + L, 30)
            ys = y + 3.0 * np.sin(xs / 22.0 + r * 1.3 + seed) + rng.uniform(-2, 2)
            S.sd_polyline(G, np.stack([xs, ys], 1).astype(np.float32), (0.35 + 0.55 * np.sin(np.linspace(0, np.pi, 30))).astype(np.float32), out=lines, pad=2)
    fall = (1 - smooth(200, 520, np.abs(X - cx))) * smooth(860, 940, Y) * S.aa_mask(S.sd_round_box(G, W / 2, H / 2, W / 2 - 100, H / 2 - 76, 3), G)
    col = over(col, S.aa_mask(lines, G), rgb("#4E6E90"), 0.5 * fall)
    wash = (1 - smooth(150, 520, np.abs(X - cx))) * smooth(880, 990, Y) * 0.22
    col = col * (1 - wash[..., None] + wash[..., None] * rgb("#9DB6CA") / rgb("#E6D6B0"))
    return col


def clouds(col, G, seed):
    shape = G.empty()
    lines = G.empty()
    for (cx, cy, s, fl) in ((760, 120, 34, False), (1180, 104, 30, True), (980, 150, 22, False)):
        O.xiangyun(G, cx, cy, s, flip=fl, out_shape=shape, out_lines=lines)
    m = S.aa_mask(shape, G)
    col = over(col, m, rgb("#EEE6D2"), 0.55)
    col = over(col, S.band(shape, -0.7, 0.5, G), rgb("#8A7A62"), 0.35)
    col = over(col, np.clip(0.5 - (lines - 0.5), 0, 1) * m, rgb("#9A8A70"), 0.3)
    return col


def calligraphy(col, G):
    text = "兵者国之大事"
    x = W - 214.0
    y = 540.0
    for i, ch in enumerate(text):
        m = GB.glyph_mask(G, ch, FONT_BRUSH, 46, x, y + i * 52, anchor="ms")
        col = over(col, m, rgb("#2A2119"), 0.62)
    return col


def seal(col, G):
    cx, cy, s = W - 214.0, 900.0, 66.0
    sd = S.sd_round_box(G, cx, cy, s / 2, s / 2, 5.0)
    m = S.aa_mask(sd, G)
    n = S.fbm(G.shape, 6.0, 77, octaves=2)
    ink = m * np.clip(0.75 + (n - 0.5) * 0.9, 0, 1)
    col = over(col, ink, rgb("#B5382A"), 0.88)
    g = GB.glyph_mask(G, "战", FONT_BRUSH, 50, cx, cy + 18, anchor="ms")
    inner = S.aa_mask(sd + 6.0, G)
    col = over(col, g * inner, rgb("#E6D6B0"), 0.92)
    col = over(col, S.band(sd, 4.0, 6.0, G), rgb("#E6D6B0"), 0.85)
    return col


def mount(col, G):
    """Brocade mounting band round the silk field (functions of the distance in from the edge)."""
    x0, y0, x1, y1 = SHEET
    d = -S.sd_round_box(G, (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2, 3.0)
    inside = S.aa_mask(-d, G)
    # brocade: azurite twill 0..24 px with a woven rosette row
    fig = G.empty()
    step = 34.0
    for x in np.arange(x0 + step / 2, x1, step):
        for y in (y0 + 12, y1 - 12):
            S.sd_circle(G, float(x), float(y), 3.6, out=fig, pad=2)
    for y in np.arange(y0 + step / 2, y1, step):
        for x in (x0 + 12, x1 - 12):
            S.sd_circle(G, float(x), float(y), 3.6, out=fig, pad=2)
    figm = S.aa_mask(fig, G) * (d < 24)
    brocade = GB.brocade(G, figm, ground="#3E5F7E", ground_deep="#24405C", fig="#CFAE68", fig_deep="#8E6C34", seed=5)
    band = S.band(d, 0.0, 24.0, G)
    col = over(col, band * inside, brocade)
    col = over(col, S.band(d, 1.0, 2.6, G), rgb("#CFAE68"), 0.9)
    col = over(col, S.band(d, 21.5, 23.5, G), rgb("#CFAE68"), 0.9)
    col = over(col, S.band(d, 24.0, 33.0, G), rgb("#E8DEC4"), 1.0)          # ivory 隔水 strip
    col = over(col, S.band(d, 33.0, 34.6, G), rgb("#2A2119"), 0.85)          # ink rule
    return col, d


def paint():
    G = S.Grid(W, H, 1)
    col = table(G)
    x0, y0, x1, y1 = SHEET
    d = -S.sd_round_box(G, (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2, 3.0)
    silk = GB.silk_ground(G, 21, light="#E6D6B0", dark="#D5BF94", weave=0.02, mottle=0.3, mottle_cell=160.0,
                          stain=0.16, foxing=0.03, edge=np.maximum(d - 34.0, 0.0), edge_k=0.45)
    sheet = S.aa_mask(-d, G)
    col = over(col, sheet, silk)
    col = mountains(col, G, "left", 11, sheet)
    col = mountains(col, G, "right", 23, sheet)
    col = waves(col, G, "left", 3)
    col = waves(col, G, "right", 5)
    col = clouds(col, G, 7)
    col = calligraphy(col, G)
    col = seal(col, G)
    col, _ = mount(col, G)
    # the sheet's own edge: a thin deeper line where silk meets the table
    col = over(col, S.band(d, -1.2, 0.6, G), rgb("#1E1A16"), 0.6)
    return np.clip(col, 0, 1)


def main():
    col = paint()
    img = np.dstack([col, np.ones(col.shape[:2], np.float32)]).astype(np.float32)
    p = post.save_asset(img, "Art/Battle/Background.png")
    print("[battle] wrote %s" % p)
    return p


if __name__ == "__main__":
    main()
