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
    """Blue-green peaks (青绿) in a top corner: azurite summits over malachite shoulders over an
    ochre foot, ink contours and 皴 strokes, dissolving downwards into bare-silk mist and
    fading towards the centre (the board stays calm)."""
    X, Y = G.X, G.Y
    rng = np.random.default_rng(seed)
    sgn = 1 if corner == "left" else -1
    ex = 70.0 if corner == "left" else W - 70.0
    for layer, (base, hmax, n_pk, alpha) in enumerate(((300.0, 230.0, 4, 0.75), (370.0, 160.0, 5, 0.7))):
        ridge = np.full(G.shape[1], 1e9, np.float32)
        xs = G.xs
        jag = S.fbm((1, len(xs)), 22.0, seed + 3 + layer, octaves=3)[0]
        jag2 = S.fbm((1, len(xs)), 6.0, seed + 5 + layer, octaves=2)[0]
        for k in range(n_pk):
            px = ex + sgn * (40 + k * rng.uniform(85, 120) + layer * 50)
            h = hmax * rng.uniform(0.55, 1.0) * (1.0 - 0.13 * k)
            w = h * rng.uniform(0.62, 0.85)
            u = np.abs(xs - px) / w
            f = np.clip(1.0 - np.clip(u, 0, 1) ** 1.15, 0, 1) ** 1.7
            y = base - h * f * (0.86 + 0.36 * (jag - 0.5)) - 6.0 * (jag2 - 0.5) * f
            ridge = np.minimum(ridge, np.where(f > 0, y, 1e9))
        ridge = np.where(ridge > 1e8, base + 1000, ridge)
        Hloc = np.maximum(base - ridge, 1.0)[None, :]
        rel = (Y - ridge[None, :]) / Hloc
        body = (rel > 0) & (Hloc > 2)
        fall = (1 - smooth(260, 640, np.abs(X - ex))) * sheet
        mist = 1 - smooth(0.55, 1.15, rel)
        n = S.fbm(G.shape, 30.0, seed + 9 + layer, octaves=3)
        azu = P.mix("#3E6E98", "#7FA6C8", smooth(0.0, 0.35, rel + (n - 0.5) * 0.2))
        mal = P.mix("#3E8E6E", "#8CBFA0", smooth(0.3, 0.7, rel + (n - 0.5) * 0.2))
        och = P.mix("#B9926A", "#D8C39A", smooth(0.6, 1.0, rel))
        c = P.mix(azu, mal, smooth(0.22, 0.42, rel + (n - 0.5) * 0.25)[..., None] * np.ones(3))
        c = P.mix(c, och, smooth(0.55, 0.8, rel)[..., None] * np.ones(3))
        m = body * mist * fall * (alpha - 0.15 * layer)
        col = over(col, m, c)
        # ink contour along the ridge
        edge = body * (Y - ridge[None, :] < 2.0) * fall
        col = over(col, edge.astype(np.float32), rgb("#24302C"), 0.55)
        # 皴 strokes running down the slopes
        for _ in range(120):
            j = int(rng.uniform(0, W - 1))
            if ridge[j] > 1e3 or fall[min(int(ridge[j]) + 2, H - 1), j] < 0.05:
                continue
            if base - ridge[j] < 12:
                continue
            y0 = ridge[j] + rng.uniform(3, 0.6 * float(base - ridge[j]))
            slope = (ridge[min(j + 3, W - 1)] - ridge[max(j - 3, 0)]) / 6.0
            L = rng.uniform(8, 22)
            dx = np.sign(slope) * min(abs(slope), 1.5) * L * 0.6
            pnts = np.array([[j, y0], [j + dx * 0.5, y0 + L * 0.5], [j + dx, y0 + L]], np.float32)
            sd = S.sd_polyline(G, pnts, np.array([0.9, 0.7, 0.2], np.float32), pad=2)
            rr = (y0 - ridge[j]) / max(base - ridge[j], 1)
            col = over(col, S.aa_mask(sd, G), rgb("#24302C"), 0.3 * float(1 - smooth(0.4, 0.9, rr)) * float(fall[int(y0), j]))
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
    silk = GB.silk_ground(G, 21, light="#E6D6B0", dark="#D5BF94", weave=0.02, mottle=0.4, mottle_cell=160.0,
                          stain=0.3, foxing=0.04, edge=np.maximum(d - 34.0, 0.0), edge_k=0.45)
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
