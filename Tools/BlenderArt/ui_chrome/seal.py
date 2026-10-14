"""Seal.png (128x128, transparent): a cinnabar seal impression 铁血 (baiwen 白文: the characters
are cut into the stone, so they print as bare paper - transparent here).

    block     a 104 px square impression rotated -3 deg, centred; its edge wanders by ~0.8 px
              and has a few chips; a slightly lighter, drier corner where the stone met less
              pressure
    glyphs    铁 (right column) and 血 (left column), read top-to-bottom, right-to-left.
              Seal-script look from Brush.ttf: each glyph is skeletonised, its spurs pruned,
              stretched to fill its column and re-stroked with an even, round-ended line
              (the uniform weight of 篆书), then the cut edges are roughened like carved stone
    ink pad   印泥 texture: cinnabar #B5382A, deeper where the paste lies thick, more orange
              where thin; fine specks of bare paper and a granular coverage
Also used by Title_Logo (:func:`impression`).
"""

import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ironart import ui_chrome_paint as P
from ironart import ui_chrome_sdf as S

NAME = "Seal"
SPEC = dict(size=(128, 128), ss=4, seed=71)
W = H = 128
SIDE = 104.0
ROT = -3.0
CHARS = (("铁", 1), ("血", 0))          # (char, column 1 = right)


def _font():
    from common import font
    return font("Brush.ttf")


def zhang_suen(img):
    """Binary thinning (Zhang-Suen) - vectorised numpy."""
    a = img.astype(np.uint8).copy()
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            p = np.pad(a, 1)
            P2, P3, P4 = p[:-2, 1:-1], p[:-2, 2:], p[1:-1, 2:]
            P5, P6, P7 = p[2:, 2:], p[2:, 1:-1], p[2:, :-2]
            P8, P9 = p[1:-1, :-2], p[:-2, :-2]
            nb = [P2, P3, P4, P5, P6, P7, P8, P9]
            B = sum(n.astype(np.int32) for n in nb)
            seq = nb + [P2]
            A = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.int32) for i in range(8))
            if step == 0:
                c = (P2 * P4 * P6 == 0) & (P4 * P6 * P8 == 0)
            else:
                c = (P2 * P4 * P8 == 0) & (P2 * P6 * P8 == 0)
            rm = (a == 1) & (B >= 2) & (B <= 6) & (A == 1) & c
            if rm.any():
                a[rm] = 0
                changed = True
    return a


def _neighbours(a):
    p = np.pad(a, 1).astype(np.int32)
    return sum(p[1 + dy:p.shape[0] - 1 + dy, 1 + dx:p.shape[1] - 1 + dx]
               for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0))


def prune(sk, n):
    """Remove spurs shorter than ~n px, then regrow the surviving branches to full length."""
    a = sk.copy()
    for _ in range(n):
        ends = (a == 1) & (_neighbours(a) == 1)
        a[ends] = 0
    for _ in range(n):
        grow = (sk == 1) & (a == 0) & (_neighbours(a) >= 1)
        a = a.copy()
        a[grow] = 1
    return a


def glyph_skeleton(ch, px=360):
    """Skeleton (binary array) of a Brush.ttf glyph rendered ``px`` high, cropped to its box."""
    f = ImageFont.truetype(_font(), px)
    im = Image.new("L", (px * 2, px * 2), 0)
    ImageDraw.Draw(im).text((px // 2, px // 2), ch, font=f, fill=255)
    im = im.crop(im.getbbox())
    b = (np.asarray(im, np.float32) > 127).astype(np.uint8)
    b = np.pad(b, 4)
    return prune(zhang_suen(b), int(px * 0.05))


def stroke_mask(sk, box, out_shape, width, ss, max_stretch=None):
    """Stretch skeleton ``sk`` into ``box`` (x0, y0, x1, y1 in output samples) and re-stroke
    it with an even round-ended line ``width`` samples wide.  Returns coverage (float)."""
    x0, y0, x1, y1 = box
    ys, xs = np.nonzero(sk)
    h, w = sk.shape
    pad = width * 0.5
    sx = (x1 - x0 - 2 * pad) / max(1, xs.max() - xs.min())
    sy = (y1 - y0 - 2 * pad) / max(1, ys.max() - ys.min())
    if max_stretch is not None and sy > sx * max_stretch:
        sy_new = sx * max_stretch
        y0 = y0 + 0.5 * (sy - sy_new) * (ys.max() - ys.min())
        sy = sy_new
    im = Image.new("L", (out_shape[1], out_shape[0]), 0)
    dr = ImageDraw.Draw(im)
    r = width * 0.5
    # connect skeleton neighbours with line segments in the stretched space (keeps strokes
    # continuous under anisotropic scaling), dots at every pixel for round joints
    pts = {(int(y), int(x)) for y, x in zip(ys, xs)}
    for (y, x) in pts:
        X = x0 + pad + (x - xs.min()) * sx
        Y = y0 + pad + (y - ys.min()) * sy
        for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
            if (y + dy, x + dx) in pts:
                X2 = x0 + pad + (x + dx - xs.min()) * sx
                Y2 = y0 + pad + (y + dy - ys.min()) * sy
                dr.line([(X, Y), (X2, Y2)], fill=255, width=max(1, int(round(width))))
        dr.ellipse([X - r, Y - r, X + r, Y + r], fill=255)
    a = np.asarray(im.filter(ImageFilter.GaussianBlur(ss * 0.35)), np.float32) / 255.0
    return a


def impression(G, cx, cy, side, rot, seed, chars=CHARS, width=5.0, stretch=2.2, gap=4.0,
               margin=6.5):
    """Seal impression on grid G: returns (alpha, colour field)."""
    ss = G.ss
    # local coordinates of the (rotated) seal square
    a = math.radians(rot)
    ca, sa = math.cos(a), math.sin(a)
    X, Y = G.X - cx, G.Y - cy
    u = ca * X + sa * Y
    v = -sa * X + ca * Y
    half = side / 2.0
    rng = np.random.default_rng(seed)
    # ---- block edge: wandering, chipped ------------------------------------------------------
    sq = np.maximum(np.abs(u), np.abs(v)) - half + 1.2
    sq = sq - 1.2                                  # sharp corners slightly rounded below
    wob = 0.75 * P.fbm2(G, 6.0, seed + 1, octaves=3) + 0.35 * P.fbm2(G, 1.6, seed + 2, octaves=2)
    corner = np.hypot(np.maximum(np.abs(u) - half + 3.0, 0), np.maximum(np.abs(v) - half + 3.0, 0))
    block = sq + 0.45 * wob + 0.25 * corner
    chips = G.empty()
    for _ in range(9):
        side_i = rng.integers(4)
        t = rng.uniform(-0.9, 0.9) * half
        r = rng.uniform(0.6, 1.6)
        px_, py_ = [(t, -half), (half, t), (t, half), (-half, t)][side_i]
        wx = cx + ca * px_ - sa * py_
        wy = cy + sa * px_ + ca * py_
        S.sd_circle(G, wx, wy, r, out=chips)
    block = np.maximum(block, -chips)
    cover = P.aa(block, G)
    # ---- glyphs (cut away) ---------------------------------------------------------------------
    inner = half - margin
    colw = (2 * inner - gap) / 2.0
    cut = np.zeros(G.shape, np.float32)
    # glyphs are drawn axis-aligned on a local canvas then rotated with the block
    n = int(round(side * ss)) + 8 * ss
    loc = np.zeros((n, n), np.float32)
    o = n / 2.0
    for ch, col in chars:
        sk = glyph_skeleton(ch)
        gx0 = o + (-inner + col * (colw + gap)) * ss
        box = (gx0, o - inner * ss, gx0 + colw * ss, o + inner * ss)
        loc = np.maximum(loc, stroke_mask(sk, box, (n, n), width * ss, ss, stretch))
    im = Image.fromarray(loc, "F").rotate(-rot, Image.BICUBIC, center=(o, o))
    big = np.zeros(G.shape, np.float32)
    ox, oy = int(round(cx * ss - o)), int(round(cy * ss - o))
    arr = np.asarray(im, np.float32)
    ys0, xs0 = max(0, oy), max(0, ox)
    ys1, xs1 = min(G.ny, oy + n), min(G.nx, ox + n)
    big[ys0:ys1, xs0:xs1] = arr[ys0 - oy:ys1 - oy, xs0 - ox:xs1 - ox]
    # carved edges: roughen the cut with fine noise
    rough = 0.10 * P.fbm2(G, 1.2, seed + 3, octaves=2)
    cut = P.smoothstep(0.38, 0.62, big + rough)
    # ---- ink pad texture -----------------------------------------------------------------------
    grain = P.fine_grain(G, seed + 4, 0.45)
    blot = P.fbm2(G, 14.0, seed + 5, octaves=3)
    dry = P.smoothstep(0.3, 1.6, blot + 0.03 * (u - v))       # a drier corner (top-right)
    clump = P.fbm2(G, 3.0, seed + 6, octaves=2)
    specks = P.smoothstep(2.3, 2.9, grain + 0.9 * dry + 0.5 * clump)
    alpha = cover * (1.0 - cut) * (1.0 - 0.92 * specks) * (1.0 - 0.18 * dry)
    thick = P.smoothstep(-0.5, 1.2, -blot)
    col = P.mix("#C4462F", "#A52E23", 0.35 + 0.45 * thick)
    col = col * (1.0 + 0.05 * grain)[..., None]
    return np.clip(alpha, 0, 1), col


def paint(G, variant=None, seed=None):
    seed = SPEC["seed"] if seed is None else seed
    alpha, col = impression(G, W / 2.0, H / 2.0, SIDE, ROT, seed)
    C = P.Canvas(G)
    C.over(alpha, col)
    return C.rgba()
