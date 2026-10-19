"""Finish: Lanczos downsample of the 3x render, the silk weave picked up by the paint, and a
gentle aged-pigment grade (ink reads warm dark brown on old silk, colours fade a touch).
Outputs 384x480 + 192x240."""
import numpy as np
from PIL import Image

import silk


def _blur(a, sigma):
    h, w = a.shape[:2]
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.rfftfreq(w)[None, :]
    k = np.exp(-2 * (np.pi ** 2) * ((fy * sigma) ** 2 + (fx * sigma) ** 2))
    if a.ndim == 2:
        return np.fft.irfft2(np.fft.rfft2(a) * k, s=(h, w))
    return np.stack([np.fft.irfft2(np.fft.rfft2(a[..., c]) * k, s=(h, w))
                     for c in range(a.shape[2])], -1)


def grade(a, weave=None, silk_tex=None):
    a = a.astype(np.float32) / 255.0
    if weave is not None:
        a = a * weave[..., None]
    if silk_tex is not None:
        # the painting sits ON the silk: every pigment takes up the silk's mottling and threads
        a = a * silk_tex[..., None]
    lum = (a * np.array([0.299, 0.587, 0.114])).sum(-1, keepdims=True)
    a = lum + (a - lum) * 0.90                       # slight pigment fade
    # warm patina: lights go to old cream (never paper-white), as aged silk and size do
    a = a * (1 - 0.04 * lum * np.array([0.0, 0.25, 1.0]))
    ink = np.array([0.130, 0.100, 0.080])            # darkest value: warm ink, not pure black
    a = ink + (1 - ink) * a
    return np.clip(a * 255 + 0.5, 0, 255).astype(np.uint8)


def silk_texture(w, h, seed=1, k=0.6):
    """normalised silk luminance texture (mean 1) at the target size, strength k."""
    s = silk.silk_array(w * 2, h * 2, seed)
    s = s.reshape(h, 2, w, 2, 3).mean((1, 3)).mean(-1)
    # remove the vignette (the painting keeps its own values), keep mottle and threads
    lo = _blur(s, 18.0 * w / 384)
    tex = s / np.maximum(lo, 1e-3)
    return np.clip(1 + k * (tex - 1), 0.96, 1.04)


def weave_map(w, h, seed=7, strength=0.35):
    """isotropic fine grain of the silk (no weft streaks on faces)"""
    rng = np.random.default_rng(seed)
    n = rng.standard_normal((h, w))
    n = _blur(n, 0.6 * w / 384)
    n = n / (n.std() + 1e-6)
    return 1 + 0.018 * strength * n


def finish(raw_path, out384, out192, out96=None):
    im = Image.open(raw_path).convert("RGB")
    a = np.asarray(im.resize((384, 480), Image.LANCZOS))
    Image.fromarray(grade(a, weave_map(384, 480), silk_texture(384, 480, k=1.6))).save(out384)
    b = np.asarray(im.resize((192, 240), Image.LANCZOS))
    Image.fromarray(grade(b, weave_map(192, 240, strength=0.5), silk_texture(192, 240, k=1.2))).save(out192)
    if out96:
        c = np.asarray(im.resize((96, 120), Image.LANCZOS))
        Image.fromarray(grade(c)).save(out96)
