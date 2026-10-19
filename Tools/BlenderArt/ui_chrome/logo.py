"""Title_Logo.png (1200x400, transparent; the title screen draws it at 960x320).

Back to front:
    calligraphy  铁血王座 in large flowing brush calligraphy (Brush.ttf = Ma Shan Zheng) across
                 the width, each character with its own scale, tilt and baseline (a written
                 line, not a typeset row): dense warm-black ink (#1A1612) in the wet cores,
                 browner and broken in the dry patches, flying-white (飞白) bristle streaks that
                 follow each stroke (line-integral convolution of bristle noise along the
                 stroke-direction field), the stroke edges roughened by the same bristles
    seal         the 铁血 baiwen impression of Seal.png, smaller, lower right
    letters      "IRON REIGN" (Heading.ttf = Marcellus) in mud-gold (泥金): gold powder with a
                 soft 晕染 (paler at the top, deeper ochre towards the bottom and into the
                 outline), sparse paler flakes, a fine ink outline; around it the calligraphy
                 is knocked out (a narrow transparent keyline), so the word reads over the
                 black ink and over any background
No shading, no shine, no shadow: a painted title block on a transparent ground.
"""

import math

import numpy as np

from ironart import ui_chrome_gongbi as GB
from ironart import ui_chrome_paint as P
from ironart import ui_chrome_sdf as S
import seal

NAME = "Title_Logo"
SPEC = dict(size=(1200, 400), ss=4, seed=81)
W, H = 1200, 400
TEXT = "IRON REIGN"
TEXT_SIZE = 168.0          # Marcellus size (px)
TEXT_CY = 226.0            # vertical centre of the word
TRACK = 12.0               # extra letter spacing (px)
OUTLINE = 2.6              # ink outline of the letters (px)
KEYLINE = 4.6              # calligraphy knocked out this far outside the letters (px)
#: calligraphy: (char, cx, cy, height px, rotation deg ccw)
CALLI = [("铁", 205.0, 186.0, 318.0, 4.0), ("血", 458.0, 212.0, 292.0, -2.0),
         ("王", 712.0, 176.0, 250.0, 3.0), ("座", 958.0, 206.0, 312.0, -3.0)]
SEAL = (1112.0, 318.0, 66.0, -4.0)


def _font(name):
    from common import font
    return font(name)


def brush_ink(G, mask, seed, length=40.0, dry_amount=1.0):
    """Ink density (0..1) and colour of brush calligraphy covering ``mask``: solid wet cores,
    bristle streaks and 飞白 breaks in dry patches and along the stroke edges."""
    ss = G.ss
    ux, uy, _ = GB.direction_field(mask, 10.0 * ss)
    rng = np.random.default_rng(seed)
    n = rng.standard_normal(G.shape).astype(np.float32)
    n = S.blur(n, 0.30 * ss)
    sel = mask > 0.02
    streak = GB.lic(n, ux, uy, length * ss, step=2.0, sel=sel)
    streak = streak / (streak[sel].std() + 1e-6)
    ed = GB.edge_distance(mask, G, max_px=16)
    hw = np.maximum(S.blur(ed, 4 * ss) * 1.6, 1.0)
    rel = np.clip(ed / hw, 0, 1)                      # 0 at the edge, ~1 in the core
    patch = P.fbm2(G, 55.0, seed + 1, octaves=3)
    dryzone = P.smoothstep(0.35, 1.2, patch) * dry_amount
    edgezone = 1.0 - P.smoothstep(0.15, 0.55, rel)
    dry = np.clip(0.85 * dryzone + 0.55 * edgezone * (0.3 + 0.7 * dryzone), 0, 1)
    gap = P.smoothstep(1.4 - 2.2 * dry, 1.9 - 2.2 * dry, streak)
    dens = mask * (1.0 - gap * P.smoothstep(0.05, 0.25, dry))
    dens = dens * (0.92 + 0.08 * rel)
    col = P.mix("#3B332B", "#1A1612", P.smoothstep(0.0, 0.5, rel) * (1.0 - 0.5 * dryzone))
    return np.clip(dens, 0, 1).astype(np.float32), col


def calligraphy(G, seed):
    """Density + colour of the whole calligraphy line, built character by character on
    sub-grids (the brush fields are expensive)."""
    dens = np.zeros(G.shape, np.float32)
    col = np.zeros(G.shape + (3,), np.float32)
    font = _font("Brush.ttf")
    for k, (ch, cx, cy, hgt, rot) in enumerate(CALLI):
        half = hgt * 0.75
        x0, y0 = max(0.0, cx - half), max(0.0, cy - half)
        x1, y1 = min(float(W), cx + half), min(float(H), cy + half)
        i0, j0 = int(round(x0 * G.ss)), int(round(y0 * G.ss))
        i1, j1 = int(round(x1 * G.ss)), int(round(y1 * G.ss))
        Gs = S.Grid((i1 - i0) / G.ss, (j1 - j0) / G.ss, G.ss, x0=i0 / G.ss, y0=j0 / G.ss)
        m = GB.glyph_mask(Gs, ch, font, hgt * 1.04, cx, cy, anchor="mm", rotate=rot)
        d, c = brush_ink(Gs, m, seed + 10 * k)
        sl = (slice(j0, j1), slice(i0, i1))
        # union of overlapping characters: the denser ink wins, colours blend by density
        a0 = dens[sl]
        a = np.maximum(a0, d)
        w = d / np.maximum(a0 + d, 1e-6)
        col[sl] = col[sl] * (1.0 - w[..., None]) + c * w[..., None]
        dens[sl] = a
    return dens, col


def letters(G):
    """Coverage of the gold word, its ink outline and the knock-out zone."""
    f = _font("Heading.ttf")
    kw = dict(anchor="mm", tracking=TRACK)
    fill = GB.glyph_mask(G, TEXT, f, TEXT_SIZE, W / 2.0, TEXT_CY, **kw)
    ink = GB.glyph_mask(G, TEXT, f, TEXT_SIZE, W / 2.0, TEXT_CY, stroke_px=OUTLINE, **kw)
    knock = GB.glyph_mask(G, TEXT, f, TEXT_SIZE, W / 2.0, TEXT_CY, stroke_px=OUTLINE + KEYLINE,
                          **kw)
    return fill, ink, knock


def gold_letters(G, fill, seed):
    """Mud-gold colour of the word: paler at the top, deeper ochre towards the bottom, 晕染
    into the outline (from a blurred coverage), powder grain and sparse flakes."""
    rows = np.nonzero(fill.max(1) > 0.5)[0]
    top, bot = G.ys[rows[0]], G.ys[rows[-1]]
    v = np.clip((G.Y - top) / max(bot - top, 1.0), 0, 1)
    base = P.mix("#E2C478", "#B98F3E", P.smoothstep(0.05, 1.0, v))
    inner = S.blur(fill, 2.2 * G.ss)
    k = P.smoothstep(0.45, 0.95, inner)
    col = P.mix(P.rgb("#9C7630") * (0.95 + 0.05 * v[..., None]), base, k)
    g = GB.grain(G, seed, 0.40)
    col = col * (1.0 + 0.05 * g)[..., None]
    fl = GB.speckle(G, seed + 1, 0.012, 0.6, 0.6)
    col = P.mix(col, P.rgb("#F0DA9C"), 0.6 * fl)
    return np.clip(col, 0, 1).astype(np.float32)


def paint(G, variant=None, seed=None):
    seed = SPEC["seed"] if seed is None else seed
    C = P.Canvas(G)
    dens, ccol = calligraphy(G, seed)
    fill, ink, knock = letters(G)
    # the calligraphy, knocked out around the gold word
    C.over(dens * (1.0 - knock), ccol)
    # seal
    sx, sy, side, rot = SEAL
    Cs = GB.subcanvas(C, sx - side, sy - side, sx + side, sy + side)
    a, c = seal.impression(Cs.G, sx, sy, side, rot, seed + 5, margin=side * 0.085,
                           gap=side * 0.055)
    Cs.over(a * 0.97, c)
    # the word: ink outline, then the gold
    C.over(ink, GB.ink_density(G, seed + 6, "#1E1A16", var=0.10, cell=40.0))
    C.over(fill, gold_letters(G, fill, seed + 7))
    return C.rgba()
