"""Seal.png (128x128, transparent): a cinnabar seal impression 铁血 (白文 baiwen: the characters
are cut into the stone, so they print as bare paper - transparent here).

    block     a 106 px square impression rotated -2 deg, centred; the stone's edge wanders by
              ~0.6 px, its corners are worn round and a few chips are missing
    glyphs    铁 (right column) and 血 (left column), read top-to-bottom, right-to-left, in
              the studio brush hand (Brush.ttf): each glyph is thickened (FreeType stroker),
              stretched to fill its column like a seal's 2-character layout, and its cut
              edges are softened and roughened like carved stone
    ink pad   印泥 texture: cinnabar #B5382A, deeper where the paste lies thick, more orange
              and broken where it is thin (a drier corner), fine specks of bare paper, paste
              squeezed darker along every edge, the silk weave faintly printing through
Also used by Title_Logo (:func:`impression`).
"""

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ironart import ui_chrome_gongbi as GB
from ironart import ui_chrome_paint as P
from ironart import ui_chrome_sdf as S

NAME = "Seal"
SPEC = dict(size=(128, 128), ss=4, seed=71)
W = H = 128
SIDE = 106.0
ROT = -2.0
CHARS = (("铁", 1), ("血", 0))          # (char, column 1 = right)


def _font():
    from common import font
    return font("Brush.ttf")


def glyph_box(ch, w, h, stroke=0.0, px=480):
    """Coverage (0..1, h x w samples) of a Brush.ttf glyph thickened by ``stroke`` (fraction
    of the glyph height) and stretched to fill a w x h box."""
    f = ImageFont.truetype(_font(), px)
    sw = int(round(stroke * px))
    im = Image.new("L", (px * 2, px * 2), 0)
    ImageDraw.Draw(im).text((px // 2, px // 2), ch, font=f, fill=255, stroke_width=sw,
                            stroke_fill=255)
    im = im.crop(im.getbbox())
    im = im.resize((max(1, int(round(w))), max(1, int(round(h)))), Image.LANCZOS)
    return np.asarray(im, np.float32) / 255.0


def impression(G, cx, cy, side, rot, seed, chars=CHARS, margin=8.5, gap=5.5, stroke=0.022,
               dry_dir=(1.0, -1.0), base="#B5382A"):
    """Seal impression on grid G centred at (cx, cy): returns (alpha, colour field)."""
    ss = G.ss
    a = math.radians(rot)
    ca, sa = math.cos(a), math.sin(a)
    X, Y = G.X - cx, G.Y - cy
    u = ca * X + sa * Y
    v = -sa * X + ca * Y
    half = side / 2.0
    rng = np.random.default_rng(seed)

    # ---- the stone's face: square, worn corners, wandering edge, chips -----------------------
    rc = 3.2
    q = np.maximum(np.abs(u), np.abs(v))
    corner = np.hypot(np.maximum(np.abs(u) - half + rc, 0), np.maximum(np.abs(v) - half + rc, 0))
    block = np.where((np.abs(u) > half - rc) & (np.abs(v) > half - rc), corner - rc, q - half)
    wob = 0.55 * P.fbm2(G, 7.0, seed + 1, octaves=3) + 0.14 * P.fbm2(G, 1.6, seed + 2, octaves=2)
    block = block + wob
    chips = G.empty()
    for _ in range(11):
        k = rng.integers(4)
        t = rng.uniform(-0.92, 0.92) * half
        r = rng.uniform(0.5, 1.5)
        px_, py_ = [(t, -half), (half, t), (t, half), (-half, t)][k]
        S.sd_circle(G, cx + ca * px_ - sa * py_, cy + sa * px_ + ca * py_, r, out=chips)
    block = np.maximum(block, -chips)
    cover = S.aa_mask(block, G)

    # ---- the cut characters -----------------------------------------------------------------
    inner = half - margin
    colw = (2.0 * inner - gap) / 2.0
    n = int(round(side * ss)) + 8 * ss
    loc = np.zeros((n, n), np.float32)
    o = n / 2.0
    for ch, col in chars:
        gw, gh = colw * ss, 2.0 * inner * ss
        g = glyph_box(ch, gw, gh, stroke)
        x0 = int(round(o + (-inner + col * (colw + gap)) * ss))
        y0 = int(round(o - inner * ss))
        loc[y0:y0 + g.shape[0], x0:x0 + g.shape[1]] = np.maximum(
            loc[y0:y0 + g.shape[0], x0:x0 + g.shape[1]], g)
    im = Image.fromarray(loc, "F").rotate(-rot, Image.BICUBIC, center=(o, o))
    big = np.zeros(G.shape, np.float32)
    ox, oy = int(round((cx - G.x0) * ss - o)), int(round((cy - G.y0) * ss - o))
    arr = np.asarray(im, np.float32)
    ys0, xs0 = max(0, oy), max(0, ox)
    ys1, xs1 = min(G.ny, oy + n), min(G.nx, ox + n)
    big[ys0:ys1, xs0:xs1] = arr[ys0 - oy:ys1 - oy, xs0 - ox:xs1 - ox]
    # carved edges: soften the font's hairline tapers, roughen the cut like stone
    big = S.blur(big, 0.35 * ss)
    rough = 0.16 * P.fbm2(G, 1.1, seed + 3, octaves=2) + 0.08 * P.fbm2(G, 4.0, seed + 4)
    cut = P.smoothstep(0.40, 0.60, big + rough)

    # ---- ink pad (印泥) -----------------------------------------------------------------------
    paste = cover * (1.0 - cut)
    grain = GB.grain(G, seed + 5, 0.42)
    blot = P.fbm2(G, 16.0, seed + 6, octaves=3)
    dx, dy = dry_dir
    ramp = (dx * u + dy * v) / (side * 0.7)
    dry = np.clip(P.smoothstep(-0.2, 1.4, 0.55 * blot + 0.9 * ramp), 0, 1)
    clump = P.fbm2(G, 2.6, seed + 7, octaves=2)
    weave = GB.silk_weave(G, seed + 8, pitch=0.55, slub=0.6)
    specks = P.smoothstep(2.1, 2.7, grain + 1.25 * dry + 0.45 * clump)
    # paste squeezed out along every edge of the printed area prints darker
    edge = 1.0 - P.smoothstep(0.0, 1.0, S.blur(paste, 0.9 * ss) * 1.0 - 0.0)
    edge = np.clip((paste - S.blur(paste, 0.9 * ss)) * 2.5, 0, 1)
    alpha = paste * (1.0 - 0.95 * specks) * (1.0 - 0.22 * dry) * (1.0 + 0.04 * weave)
    alpha = alpha * (0.93 + 0.07 * (1.0 - dry))
    thick = P.smoothstep(-0.6, 1.2, -blot)
    col = P.mix(P.mix(base, "#C9503A", 0.55), P.mix(base, "#962A20", 0.5), 0.25 + 0.55 * thick)
    col = P.mix(col, P.rgb("#C85A42"), 0.35 * dry)
    col = col * (1.0 + 0.05 * grain + 0.02 * weave)[..., None]
    col = P.mix(col, P.rgb("#8A2219"), 0.45 * edge)
    return np.clip(alpha, 0, 1).astype(np.float32), np.clip(col, 0, 1).astype(np.float32)


def paint(G, variant=None, seed=None):
    seed = SPEC["seed"] if seed is None else seed
    alpha, col = impression(G, W / 2.0, H / 2.0, SIDE, ROT, seed)
    C = P.Canvas(G)
    C.over(alpha, col)
    return C.rgba()
