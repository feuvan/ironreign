#!/usr/bin/env python3
"""2D finish of a gongbi portrait (system python3: numpy, scipy, Pillow).

    python3 finish.py passes.npz out.png [--size 384x480] [--seed N] [--silk HEX]

Layers, bottom to top:
  1. aged silk (绢): warm ground, low-frequency ageing mottle and stains, darker edges, a fine
     warp/weft thread texture
  2. mineral / plant washes: the flat ``paint`` colour, glazed toward ``tint`` by ``shade``
     (晕染 soft shading), laid with slight pigment grain and the silk showing through a little;
     wash edges pool slightly darker like water-borne pigment
  3. decal ink (eyes, brows, lips, beards) is already in ``paint``; it gets no silk show-through
  4. Freestyle brush lines, with a faint bleed into the silk
Then a Lanczos downsample to the target size and a gentle unsharp mask.
"""

import argparse
import os

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage as ndi


def hex_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


def lin2srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def fbm(shape, rng, scales, amps):
    """Sum of blurred white noises; large scales are made at low resolution and zoomed."""
    out = np.zeros(shape, np.float32)
    for s, a in zip(scales, amps):
        k = max(1, int(s // 3))
        sh = (shape[0] // k + 2, shape[1] // k + 2)
        n = rng.standard_normal(sh).astype(np.float32)
        n = ndi.gaussian_filter(n, s / k, mode="wrap")
        if k > 1:
            n = ndi.zoom(n, k, order=1)
        n = n[:shape[0], :shape[1]]
        n /= n.std() + 1e-6
        out += a * n
    return out


def silk(h, w, ss, rng, base="#DCCAA4"):
    c = hex_rgb(base)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    # ageing mottle + a few stains
    m = fbm((h, w), rng, (60 * ss, 18 * ss, 5 * ss), (0.022, 0.012, 0.006))
    st = fbm((h, w), rng, (25 * ss,), (1.0,))
    stains = np.clip(st - 2.0, 0, None) * 0.03
    # darker toward the edges (handled, aged border)
    cx, cy = (x / w - 0.5) * 2, (y / h - 0.5) * 2
    vig = np.clip(np.sqrt((cx * 0.9) ** 2 + (cy * 0.75) ** 2) - 0.55, 0, None) ** 1.6 * 0.22
    lum = 1.0 + m - stains - vig
    img = c[None, None, :] * lum[..., None]
    img = img * (1 - stains[..., None] * np.array([0.0, 0.6, 1.4], np.float32))
    # warp / weft threads: per-row and per-column thickness variation
    per = max(1, int(round(0.9 * ss)))
    rows = rng.standard_normal(h // per + 2).astype(np.float32)
    cols = rng.standard_normal(w // per + 2).astype(np.float32)
    rows = ndi.gaussian_filter1d(rows, 0.6)
    cols = ndi.gaussian_filter1d(cols, 0.6)
    weave = rows[(y // per).astype(int)] * 0.003 + cols[(x // per).astype(int)] * 0.0025
    weave = weave + fbm((h, w), rng, (0.6 * ss, 1.5 * ss), (0.006, 0.004))
    img = img * (1 + weave[..., None])
    return np.clip(img, 0, 1), weave


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("npz")
    ap.add_argument("out")
    ap.add_argument("--size", default="384x480")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--silk", default="#DCCAA4")
    ap.add_argument("--opacity", type=float, default=0.93)
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()
    tw, th = (int(v) for v in a.size.split("x"))
    d = np.load(a.npz)
    img = d["Image"].astype(np.float32)
    H, W = img.shape[:2]
    ss = W // tw
    alpha = img[..., 3]
    inv = 1.0 / np.maximum(alpha, 1e-4)
    paint = d["paint"][..., :3].astype(np.float32) * inv[..., None]
    tint = d["tint"][..., :3].astype(np.float32) * inv[..., None]
    sh = np.clip(d["shade"][..., 0].astype(np.float32) * inv, 0, 1)
    if "AO" in d and "aok" in d:
        ao = np.clip(d["AO"][..., 0].astype(np.float32) * inv, 0, 1)
        aok = np.clip(d["aok"][..., 0].astype(np.float32) * inv, 0, 1)
        sh = np.clip(sh + aok * (1.0 - ao), 0, 1)
    inkm = np.clip(d["ink"][..., 0].astype(np.float32) * inv, 0, 1)
    # where coverage is tiny the un-premultiplied values are noise: take them from the inside
    edge = alpha < 0.5
    if edge.any():
        # push inside values outward by a few normalised blurs (cheap 'inpaint')
        wgt = (~edge).astype(np.float32)
        for arr in (paint, tint):
            for c in range(3):
                num = ndi.gaussian_filter(arr[..., c] * wgt, 2.0 * ss)
                den = ndi.gaussian_filter(wgt, 2.0 * ss)
                arr[..., c] = np.where(edge, num / np.maximum(den, 1e-4), arr[..., c])
        den = ndi.gaussian_filter(wgt, 2.0 * ss)
        sh = np.where(edge, ndi.gaussian_filter(sh * wgt, 2.0 * ss) / np.maximum(den, 1e-4), sh)
        inkm = np.where(edge, ndi.gaussian_filter(inkm * wgt, 2.0 * ss) / np.maximum(den, 1e-4),
                        inkm)
    # soften the (noisy) AO shading a touch - within the figure only
    sh = ndi.gaussian_filter(sh * alpha, 0.8 * ss) / np.maximum(ndi.gaussian_filter(alpha, 0.8 * ss), 1e-3)
    rng = np.random.default_rng(a.seed)
    ground, weave = silk(H, W, ss, rng, a.silk)
    # 晕染: glaze toward the tint colour by the shade amount
    wash = paint * (1.0 - sh[..., None] + sh[..., None] * np.clip(tint, 0, 1))
    # pigment grain (mineral colours granulate a little)
    grain = fbm((H, W), rng, (0.7 * ss, 2.0 * ss), (0.008, 0.005))
    wash = wash * (1 + grain[..., None] * (1 - inkm[..., None]))
    # silk shows through the washes a little (not through ink)
    op = a.opacity + (1 - a.opacity) * inkm
    figure = wash * op[..., None] + ground * (1 - op[..., None]) * (wash / np.maximum(
        wash.max(-1, keepdims=True), 1e-3)) ** 0.0
    figure = figure * (1 + weave[..., None] * 0.6 * (1 - inkm[..., None]))
    # wash-edge pooling: a slightly darker rim just inside the figure silhouette
    rim = np.clip(alpha - ndi.gaussian_filter(alpha, 1.6 * ss), 0, 1)
    figure = figure * (1 - rim[..., None] * 0.35)
    out = ground * (1 - alpha[..., None]) + figure * alpha[..., None]
    # Freestyle lines (premultiplied linear RGBA)
    if "Freestyle" in d:
        fs = d["Freestyle"].astype(np.float32)
        la = np.clip(fs[..., 3], 0, 1)
        if "veil" in d:
            veil = np.clip(d["veil"][..., 0].astype(np.float32), 0, 1)
            veil = np.clip(ndi.gaussian_filter(veil, 0.6 * ss) * 1.6, 0, 1)
            la = la * (1 - veil)
        lc = lin2srgb(fs[..., :3] / np.maximum(la[..., None], 1e-4))
        bleed = ndi.gaussian_filter(la, 0.9 * ss) * 0.18
        out = out * (1 - bleed[..., None] * 0.6)
        out = out * (1 - la[..., None]) + lc * la[..., None]
    out = np.clip(out, 0, 1)
    big = Image.fromarray((out * 255 + 0.5).astype(np.uint8))
    if a.debug:
        big.save(a.out.replace(".png", "_big.png"))
    im = big.resize((tw, th), Image.LANCZOS)
    im = im.filter(ImageFilter.UnsharpMask(radius=0.8, percent=45, threshold=1))
    im.save(a.out)
    im.resize((tw // 2, th // 2), Image.LANCZOS).filter(
        ImageFilter.UnsharpMask(radius=0.6, percent=30, threshold=1)).save(
        a.out.replace(".png", "_192.png"))
    im.resize((tw // 4, th // 4), Image.LANCZOS).save(a.out.replace(".png", "_96.png"))
    print("[finish] %s (%dx%d from %dx%d, ss %d)" % (a.out, tw, th, W, H, ss))


if __name__ == "__main__":
    main()
