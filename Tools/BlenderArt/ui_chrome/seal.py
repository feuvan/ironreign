"""Seal.png (128x128, transparent): the impression of a carved cinnabar seal on paper - a
baiwen (intaglio) seal: the square field prints red, the carved characters 铁 (right column)
and 血 (left column) stay paper-white (transparent here, so the impression sits on whatever
paper the UI stamps it on).

Glyphs: Brush.ttf (Ma Shan Zheng) drawn large, stretched to fill their tall cells and turned
"seal-script-like" (strokes evened out by a blur + threshold, corners softened, strokes touching
the cell edges are kept).  The impression: square 104 px rotated 3 deg, edges worn by noise and
chips, paste coverage broken by paper fibres and uneven pressure, a little paste build-up
(relief) at the stroke edges - rendered as a thin paste layer so it catches the same light as the
rest of the UI.
"""

import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import kit
from ironart import ui_chrome_sdf as S
from ironart.ui_chrome_maps import Maps

NAME = "Seal"
SPEC = dict(shader_alpha=True, size=(128, 128), ss=4, spp=32, seed=61)
W = H = 128
SIDE = 104.0
ROT = 3.0
GLYPHS = "铁血"


def font_path(name):
    from common import FONTS
    return os.path.join(FONTS, name)


def glyph_mask(ch, w, h, ss, weight=0.235, soften=0.85):
    """A glyph stretched to fill a w x h cell (target px) at ss samples/px, seal-styled."""
    big = 512
    f = ImageFont.truetype(font_path("Brush.ttf"), big)
    im = Image.new("L", (big * 2, big * 2), 0)
    dr = ImageDraw.Draw(im)
    dr.text((big // 2, big // 2), ch, font=f, fill=255)
    bb = im.getbbox()
    im = im.crop(bb)
    tw, th = int(round(w * ss)), int(round(h * ss))
    im = im.resize((tw, th), Image.LANCZOS)
    a = np.asarray(im, np.float32) / 255.0
    # even out the brush (thick/thin) towards seal-script strokes: blur, then threshold low
    a = S.blur(a, soften * ss)
    a = np.clip((a - weight) / 0.05 + 0.5, 0, 1)
    return a


def build(G, variant=None, side=SIDE, rot=ROT, seed=61, cx=W / 2, cy=H / 2):
    rng = np.random.default_rng(seed)
    ss = G.ss
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    X, Y = G.X - cx, G.Y - cy
    u = c * X + s * Y          # seal-local coordinates (target px), origin at the centre
    v = -s * X + c * Y
    hs = side / 2
    # worn outline: rounded square + low-frequency edge wobble + chips
    wob = (S.fbm(G.shape, 9.0 * ss, seed + 1, octaves=3) - 0.5) * 2.2
    sq = S.sd_round_box_uv(u, v, 0.0, 0.0, hs, hs, 3.0) + wob
    # chips: irregular bites along the edge (noise-shaped, not circles)
    chipn = S.fbm(G.shape, 2.2 * ss, seed + 11, octaves=2)
    for _ in range(7):
        t = (rng.random() - 0.5) * side * 0.9
        side_k = rng.integers(4)
        px_, py_ = [(t, -hs), (hs, t), (t, hs), (-hs, t)][side_k]
        r = 0.7 + rng.random() * 1.4
        sq = np.maximum(sq, -(np.hypot(u - px_, v - py_) - r * (0.6 + 0.8 * chipn)))
    field = S.aa_mask(sq, G)

    # characters (carved = white) in two tall cells, right column first
    margin, gap = 8.5, 5.0
    cw = (side - 2 * margin - gap) / 2
    ch_ = side - 2 * margin
    carve = np.zeros(G.shape, np.float32)
    for k, chh in enumerate(GLYPHS):
        gm = glyph_mask(chh, cw, ch_, ss)
        x0 = (hs - margin - cw) if k == 0 else (-hs + margin)
        y0 = -hs + margin
        # sample the glyph mask in seal-local coordinates (bilinear)
        gx = (u - x0) * ss - 0.5
        gy = (v - y0) * ss - 0.5
        inside = (gx >= 0) & (gy >= 0) & (gx < gm.shape[1] - 1) & (gy < gm.shape[0] - 1)
        ix = np.clip(np.floor(gx).astype(np.int32), 0, gm.shape[1] - 2)
        iy = np.clip(np.floor(gy).astype(np.int32), 0, gm.shape[0] - 2)
        fx, fy = gx - ix, gy - iy
        val = (gm[iy, ix] * (1 - fx) * (1 - fy) + gm[iy, ix + 1] * fx * (1 - fy)
               + gm[iy + 1, ix] * (1 - fx) * fy + gm[iy + 1, ix + 1] * fx * fy)
        carve = np.maximum(carve, np.where(inside, val, 0.0))
    # stroke edges of a carved seal are slightly irregular
    edge_n = (S.value_noise(G.shape, 1.6 * ss, seed + 3) - 0.5) * 0.5
    carve = np.clip(carve + edge_n * (carve > 0.05) * (carve < 0.95), 0, 1)

    # paste coverage: fibres and pressure leave voids
    fib = S.fibres(G.shape, count=G.w * G.h * 0.035, length=4 * ss, width=0.22 * ss, seed=seed + 5,
                   curl=0.7, lo=0.5, hi=1.0)
    press = S.fbm(G.shape, 26.0 * ss, seed + 7, octaves=4)
    voids = np.clip((fib - 0.35) * 1.0, 0, 1) * kit.smoothstep(0.5, 0.7, press)
    speck = (S.value_noise(G.shape, 0.55 * ss, seed + 9) > 0.9).astype(np.float32)
    speck = S.blur(speck, 0.25 * ss) * kit.smoothstep(0.45, 0.65, press)
    cover = field * (1 - carve) * np.clip(1 - 0.6 * voids - 0.8 * speck, 0, 1)
    cover = np.clip(cover * (0.9 + 0.1 * kit.smoothstep(0.25, 0.6, press)), 0, 1)

    m = Maps(G.shape, base="#B0281C", alpha=0.0)
    # paste colour: thicker paste (strong pressure) is deeper red
    tone = 0.85 + 0.25 * kit.smoothstep(0.3, 0.8, press)
    m.paint(np.ones(G.shape, np.float32), "seal_paste")
    m.tint(np.ones(G.shape, np.float32), tone)
    # paste ridges along the carved edges (the paste squeezes against the cut)
    ridge = np.clip(S.blur(carve, 0.6 * ss) - carve, 0, 1)
    m.height = (0.05 * cover + 0.06 * ridge * cover).astype(np.float32)
    m.paint(ridge * 2.0, rough=0.45)
    m.alpha = cover.astype(np.float32)
    return m
