"""numpy/Pillow finishing of an approach-B render (runs in Blender's python or system python3).

    render (2x, painted in the compositor, over the painted ground)
      -> brush-texture overlay (strong in the darks and on costume, faint on skin)
      -> painted-out bottom edge (the bust dissolves into the ground with ragged strokes)
      -> grade (warm darks, gentle S, saturation)
      -> Lanczos to 384x480 (@2x) and 192x240, masked unsharp on the eyes / face
"""

import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import background as BG


def _load(path, mode="RGBA"):
    return np.asarray(Image.open(path).convert(mode), np.float32) / 255.0


def _ss(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _blur(a, r):
    if r <= 0:
        return a
    if a.ndim == 2:
        im = Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8), "L")
        return np.asarray(im.filter(ImageFilter.GaussianBlur(r)), np.float32) / 255.0
    im = Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.GaussianBlur(r)), np.float32) / 255.0


def brush_layer(W, H, rng, density=1.0, angle=-32.0):
    a = np.asarray(BG.strokes(W, H, rng, n=int(1800 * density), length=(0.015, 0.06),
                              width=(0.003, 0.009), alpha=(14, 40), angle=angle, spread=22), np.float32)
    b = np.asarray(BG.strokes(W, H, rng, n=int(500 * density), length=(0.05, 0.16),
                              width=(0.008, 0.02), alpha=(8, 22), angle=angle + 8, spread=30), np.float32)
    s = (a - 128) / 128.0 + 0.6 * (b - 128) / 128.0
    return _blur(np.clip(s * 0.5 + 0.5, 0, 1), 0.7) * 2 - 1


def finish(raw, masks, eye, bg, out_png, out_small=None, opts=None, seed=1):
    o = dict(brush=1.0, brush_skin=0.25, dissolve=0.9, sat=1.04, warm_shadows=0.03, contrast=1.06,
             sharpen=0.6, lift=0.012)
    o.update(opts or {})
    rng = np.random.default_rng(seed + 99)
    img = _load(raw)[..., :3]
    H, W = img.shape[:2]
    m = _load(masks)
    skin, hairm, cost, alpha = m[..., 0], m[..., 1], m[..., 2], m[..., 3]
    eyem = _load(eye, "L")
    bgi = _load(bg, "RGB")
    lum = img @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    # ---- brush texture
    br = brush_layer(W, H, rng, o["brush"])
    k = 0.10 * (1 - _ss(0.15, 0.7, lum)) + 0.035
    k = k * (1 - skin * (1 - o["brush_skin"])) * (1 - eyem)
    img = img * (1 + (k * br)[..., None])
    # ---- painted-out bottom: ragged dissolve of the figure into the ground
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    xx = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    n = BG.fbm(H, W, W * 0.12, 3, rng)
    st = (brush_layer(W, H, rng, 0.6, angle=-20) + 1) * 0.5
    edge = _ss(0.80, 1.02, yy + 0.10 * (n - 0.5) + 0.08 * (st - 0.5))
    side = _ss(0.86, 1.04, np.abs(xx - 0.5) * 2 + 0.1 * (n - 0.5)) * _ss(0.55, 0.9, yy)
    d = np.clip(np.maximum(edge, side) * o["dissolve"], 0, 1) * (1 - skin)
    img = img * (1 - d[..., None]) + bgi * d[..., None]
    # ---- grade
    img = np.clip(img, 0, 1)
    lum = img @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    grey = lum[..., None]
    img = grey + (img - grey) * o["sat"]
    img = 0.5 + (img - 0.5) * o["contrast"]
    shadow = (1 - _ss(0.0, 0.45, lum))[..., None]
    img = img + shadow * np.array([o["warm_shadows"], o["warm_shadows"] * 0.4, -o["warm_shadows"] * 0.3], np.float32)
    img = img + o["lift"]
    img = np.clip(img, 0, 1)
    big = Image.fromarray((img * 255 + 0.5).astype(np.uint8), "RGB")
    ss = W // 384
    out = big.resize((384, 480), Image.LANCZOS) if ss > 1 else big
    # masked unsharp on eyes (and a little on skin)
    sm = np.asarray(out.filter(ImageFilter.UnsharpMask(radius=1.2, percent=int(160 * o["sharpen"]), threshold=1)),
                    np.float32) / 255.0
    base = np.asarray(out, np.float32) / 255.0
    em = np.asarray(Image.fromarray((eyem * 255).astype(np.uint8)).resize((384, 480), Image.BILINEAR)
                    .filter(ImageFilter.GaussianBlur(3)), np.float32) / 255.0
    sk = np.asarray(Image.fromarray((skin * 255).astype(np.uint8)).resize((384, 480), Image.BILINEAR),
                    np.float32) / 255.0
    w = np.clip(em * 1.5 + sk * 0.35, 0, 1)[..., None]
    fin = base * (1 - w) + sm * w
    fin_im = Image.fromarray((np.clip(fin, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")
    fin_im.save(out_png)
    if out_small:
        small = fin_im.resize((192, 240), Image.LANCZOS)
        small = small.filter(ImageFilter.UnsharpMask(radius=0.6, percent=35, threshold=1))
        small.save(out_small)
    return out_png
