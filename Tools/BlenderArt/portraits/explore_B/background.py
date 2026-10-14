"""Painted portrait ground (numpy + Pillow; runs in Blender's python and the system python3).

A dark warm umber ground, a soft lighter glow behind the head on the key side, and layers of
semi-transparent directional brush strokes - the same ground behind every portrait (only the
tint and seed vary) so a gallery reads as one set.
"""

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def value_noise(h, w, cell, rng):
    gh, gw = int(h / cell) + 3, int(w / cell) + 3
    g = rng.random((gh, gw)).astype(np.float32)
    y = np.arange(h, dtype=np.float32) / cell
    x = np.arange(w, dtype=np.float32) / cell
    y0 = np.floor(y).astype(int)
    x0 = np.floor(x).astype(int)
    fy = (y - y0)[:, None]
    fx = (x - x0)[None, :]
    fy = fy * fy * (3 - 2 * fy)
    fx = fx * fx * (3 - 2 * fx)
    a = g[y0][:, x0]
    b = g[y0][:, x0 + 1]
    c = g[y0 + 1][:, x0]
    d = g[y0 + 1][:, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def fbm(h, w, cell, octaves, rng, gain=0.5):
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        out += value_noise(h, w, max(2.0, cell / 2 ** o), rng) * amp
        tot += amp
        amp *= gain
    return out / tot


def strokes(w, h, rng, n=400, length=(0.08, 0.3), width=(0.01, 0.04), angle=-28.0, spread=18.0,
            alpha=(10, 40), dark=0.5):
    """Grey-centred stroke layer (128 = neutral): lighter and darker translucent strokes."""
    im = Image.new("L", (w, h), 128)
    dr = ImageDraw.Draw(im, "L")
    lay = Image.new("L", (w, h), 0)
    for i in range(n):
        x, y = rng.random() * w, rng.random() * h
        L = (length[0] + (length[1] - length[0]) * rng.random()) * w
        Wd = max(1, int((width[0] + (width[1] - width[0]) * rng.random()) * w))
        a = math.radians(angle + rng.normal() * spread)
        dx, dy = math.cos(a) * L / 2, math.sin(a) * L / 2
        v = 128 + (1 if rng.random() > dark else -1) * int(alpha[0] + (alpha[1] - alpha[0]) * rng.random())
        # a stroke = a few offset lines (bristle feel)
        for k in range(3):
            o = (rng.random() - 0.5) * Wd
            ox, oy = -math.sin(a) * o, math.cos(a) * o
            dr.line([(x - dx + ox, y - dy + oy), (x + dx + ox, y + dy + oy)], fill=v, width=max(1, Wd // 2))
    return im


def paint(path, W, H, opts=None, seed=1):
    o = dict(base=(0.018, 0.013, 0.009), mid=(0.055, 0.040, 0.026), glow=(0.13, 0.095, 0.06),
             glow_pos=(0.32, 0.26), glow_size=(0.55, 0.5), tint=None, tint_amt=0.0,
             strokes=1.0, vignette=0.55)
    o.update(opts or {})
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    u, v = x / W, y / H
    base = np.array(o["base"], np.float32)
    mid = np.array(o["mid"], np.float32)
    glow = np.array(o["glow"], np.float32)
    gx, gy = o["glow_pos"]
    sx, sy = o["glow_size"]
    g = np.exp(-(((u - gx) / sx) ** 2 + ((v - gy) / sy) ** 2))
    n1 = fbm(H, W, W * 0.35, 4, rng)
    n2 = fbm(H, W, W * 0.08, 3, rng)
    t = np.clip(g * (0.85 + 0.5 * (n1 - 0.5)), 0, 1)
    col = base + (mid - base) * np.clip(t * 1.6, 0, 1)[..., None] + (glow - mid) * np.clip(t * 1.6 - 0.6, 0, 1)[..., None]
    col *= (1 + 0.18 * (n1 - 0.5) + 0.08 * (n2 - 0.5))[..., None]
    if o["tint"] is not None and o["tint_amt"] > 0:
        tint = np.array(o["tint"], np.float32)
        col = col * (1 - o["tint_amt"]) + col * tint / max(tint.mean(), 1e-3) * o["tint_amt"]
    # vignette (darker corners and bottom)
    vg = ((u - 0.45) / 0.75) ** 2 + ((v - 0.40) / 0.8) ** 2
    col *= (1 - o["vignette"] * np.clip(vg, 0, 1) ** 1.5)[..., None]
    # strokes
    if o["strokes"] > 0:
        s1 = np.asarray(strokes(W, H, rng, n=int(260 * o["strokes"]), length=(0.12, 0.45),
                                width=(0.02, 0.06), alpha=(6, 22)).filter(ImageFilter.GaussianBlur(W / 300)),
                        np.float32) / 128.0 - 1.0
        s2 = np.asarray(strokes(W, H, rng, n=int(900 * o["strokes"]), length=(0.03, 0.12),
                                width=(0.004, 0.012), alpha=(5, 18), angle=-35, spread=25),
                        np.float32) / 128.0 - 1.0
        col *= (1 + 0.9 * s1 + 0.5 * s2)[..., None]
    # canvas grain
    grain = rng.normal(size=(H, W)).astype(np.float32)
    grain = np.asarray(Image.fromarray(np.clip(grain * 40 + 128, 0, 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(0.6)), np.float32) / 128.0 - 1.0
    col *= (1 + 0.05 * grain)[..., None]
    col = np.clip(col, 0, 1)
    srgb = np.where(col <= 0.0031308, col * 12.92, 1.055 * np.power(col, 1 / 2.4) - 0.055)
    Image.fromarray((np.clip(srgb, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB").save(path)
    return path
