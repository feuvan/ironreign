"""Aged silk ground (numpy + Pillow only; cached PNG per size/seed).

Warm tea-toned silk: base tone, soft tea-stain mottling, a fine isotropic warp/weft thread
grain (per-thread thickness variation, no streaks), the faintest weft slubs, pigment-grain
flecks, a darker handled rim and a few foxing specks.  Kept low-contrast so it never fights the
painting.
"""

import os

import numpy as np

CACHE = os.environ.get("GONGBI_CACHE", "/tmp/claude-0/-home-user-ironreign/"
                       "7c9c7cee-d827-5b3c-8cb6-e644913e9b45/scratchpad/portraits/gongbi_B/cache")


def _noise(h, w, rng, sy, sx):
    """Gaussian-filtered white noise via FFT, sigma (sy, sx) in pixels, unit std."""
    n = rng.standard_normal((h, w))
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.rfftfreq(w)[None, :]
    k = np.exp(-2 * (np.pi ** 2) * ((fy * sy) ** 2 + (fx * sx) ** 2))
    out = np.fft.irfft2(np.fft.rfft2(n) * k, s=(h, w))
    return out / (out.std() + 1e-9)


def silk_array(w, h, seed=1, base="#d9c6a0"):
    rng = np.random.default_rng(seed)
    b = np.array([int(base[i:i + 2], 16) / 255.0 for i in (1, 3, 5)])
    s = w / 384.0
    img = np.ones((h, w, 3)) * b[None, None, :]
    # tea-stain mottling (large, soft) and a warmer/cooler drift
    m1 = _noise(h, w, rng, 60 * s, 60 * s)
    m2 = _noise(h, w, rng, 18 * s, 18 * s)
    tone = 0.022 * m1 + 0.010 * m2
    img *= (1 + tone)[..., None]
    warm = _noise(h, w, rng, 90 * s, 90 * s)
    img[..., 0] *= 1 + 0.008 * warm
    img[..., 2] *= 1 - 0.018 * warm
    # weft slubs: only a whisper (the old streaks read as a texture, not as silk)
    sl = _noise(h, w, rng, 0.55 * s, 22 * s)
    img *= (1 + 0.0035 * sl)[..., None]
    # warp / weft threads: per-thread thickness variation in both directions (isotropic)
    per = max(1, int(round(0.85 * s)))
    rows = rng.standard_normal(h // per + 2)
    cols = rng.standard_normal(w // per + 2)
    yy0, xx0 = np.mgrid[0:h, 0:w]
    thr = rows[yy0 // per] * 0.0035 + cols[xx0 // per] * 0.0035
    img *= (1 + thr)[..., None]
    # fine grain and pigment-sized flecks
    gr = _noise(h, w, rng, 0.45 * s, 0.45 * s)
    img *= (1 + 0.009 * gr)[..., None]
    fl = _noise(h, w, rng, 1.6 * s, 1.6 * s)
    img *= (1 - 0.010 * np.clip(fl - 1.2, 0, None))[..., None]
    # aged edges: darker and browner towards the border
    yy, xx = np.mgrid[0:h, 0:w]
    u = (xx + 0.5) / w * 2 - 1
    v = (yy + 0.5) / h * 2 - 1
    r = np.sqrt((u * 0.95) ** 2 + (v * 0.9) ** 2)
    vig = np.clip((r - 0.55) / 0.75, 0, 1) ** 1.6
    edge = _noise(h, w, rng, 25 * s, 25 * s)
    vig = np.clip(vig * (1 + 0.35 * edge), 0, 1.2)
    img[..., 0] *= 1 - 0.10 * vig
    img[..., 1] *= 1 - 0.13 * vig
    img[..., 2] *= 1 - 0.19 * vig
    # foxing specks
    for _ in range(int(14 * s)):
        cy, cx = rng.uniform(0, h), rng.uniform(0, w)
        rad = rng.uniform(0.6, 2.2) * s
        d = ((yy - cy) ** 2 + (xx - cx) ** 2) / (rad * rad)
        f = np.exp(-d) * rng.uniform(0.04, 0.10)
        img[..., 0] *= 1 - 0.6 * f
        img[..., 1] *= 1 - 0.9 * f
        img[..., 2] *= 1 - 1.4 * f
    return np.clip(img, 0, 1)


def silk_png(w, h, seed=1, base="#d9c6a0"):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, "silk2_%dx%d_%d_%s.png" % (w, h, seed, base.lstrip("#")))
    if not os.path.exists(p):
        from PIL import Image
        a = silk_array(w, h, seed, base)
        Image.fromarray((a * 255 + 0.5).astype(np.uint8)).save(p)
    return p
