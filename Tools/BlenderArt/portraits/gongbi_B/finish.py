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


def grade(a, weave=None):
    a = a.astype(np.float32) / 255.0
    if weave is not None:
        a = a * weave[..., None]
    lum = (a * np.array([0.299, 0.587, 0.114])).sum(-1, keepdims=True)
    a = lum + (a - lum) * 0.92                       # slight pigment fade
    ink = np.array([0.130, 0.100, 0.080])            # darkest value: warm ink, not pure black
    a = ink + (1 - ink) * a
    return np.clip(a * 255 + 0.5, 0, 255).astype(np.uint8)


def weave_map(w, h, seed=7, strength=0.35):
    """isotropic fine grain of the silk (no weft streaks on faces)"""
    rng = np.random.default_rng(seed)
    n = rng.standard_normal((h, w))
    n = _blur(n, 0.6 * w / 384)
    n = n / (n.std() + 1e-6)
    return 1 + 0.018 * strength * n


def finish(raw_path, out384, out192):
    im = Image.open(raw_path).convert("RGB")
    a = np.asarray(im.resize((384, 480), Image.LANCZOS))
    Image.fromarray(grade(a, weave_map(384, 480))).save(out384)
    b = np.asarray(im.resize((192, 240), Image.LANCZOS))
    Image.fromarray(grade(b, weave_map(192, 240, strength=0.5))).save(out192)
