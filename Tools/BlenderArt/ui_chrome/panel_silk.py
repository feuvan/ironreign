"""Panel_Silk.png / PanelDark_Silk.png (256x256, opaque, seamless; Slate Image brush with
Tiling = Both): the silk grounds of the two panels as tiling fills, drawn *under* the Border-type
frames Panel_Frame.png / PanelDark_Frame.png (see panel_frame.py) so the panel field keeps its
weave at any size instead of being stretched like the Box centre of Panel.png.

Plain-weave silk on a 256 px period (every component wraps, so the tile repeats seamlessly):

    threads    one weft per pixel row, one warp per pixel column, each with its own tone, the
               interlacing checker deciding which shows (+-2 levels)
    slubs      thick spots spun into single weft threads: 3-11 px streaks, lighter or darker
               (+-4 levels)
    mottle     the ageing of the silk: soft, soft-clipped blooms 8-24 px across (+-2 levels);
               nothing larger than 64 px and no stand-out spot, so the repeat does not show
    light      Paper #E9DCC0 on average (the Panel.png field), +-4 levels overall
    dark       ink silk #1E1A16 (Night +-4), +-2 levels
The @2x master resolves the threads at twice the density (two threads per @1x pixel).
"""

import numpy as np

from ironart import ui_chrome_paint as P

NAME = "Panel_Silk"
SPEC = dict(size=(256, 256), ss=4, seed=15)
W = H = 256
VARIANTS = ("light", "dark")
FILE = {"light": "Panel_Silk", "dark": "PanelDark_Silk"}
LOOK = {
    "light": dict(base="#E9DCC0", thread=3.0, slub=4.0, mottle=1.8, warm="#D9C69E"),
    "dark": dict(base="#1E1A16", thread=1.4, slub=2.0, mottle=1.0, warm="#2B2119"),
}


def periodic_noise(n, sigma, seed):
    """Seamless (period n) gaussian-filtered white noise on an n x n grid, unit std.  ``sigma``
    in grid samples."""
    rng = np.random.default_rng(seed)
    wn = rng.standard_normal((n, n))
    f = np.fft.fftfreq(n)
    k2 = f[:, None] ** 2 + f[None, :] ** 2
    flt = np.exp(-2.0 * (np.pi * sigma) ** 2 * k2)
    out = np.real(np.fft.ifft2(np.fft.fft2(wn) * flt))
    return ((out - out.mean()) / (out.std() + 1e-9)).astype(np.float32)


def periodic_1d(n, sigma, seed):
    rng = np.random.default_rng(seed)
    wn = rng.standard_normal(n)
    f = np.fft.fftfreq(n)
    out = np.real(np.fft.ifft(np.fft.fft(wn) * np.exp(-2.0 * (np.pi * sigma) ** 2 * f * f)))
    return ((out - out.mean()) / (out.std() + 1e-9)).astype(np.float32)


def silk_levels(n, ss, seed, thread=2.0, slub=4.0, mottle=3.0):
    """Seamless silk texture in 8-bit levels (zero mean) on an n x n grid (n = W * ss)."""
    rng = np.random.default_rng(seed)
    tp = ss // 2                                     # thread pitch: 2 threads per @1x pixel
    nt = n // tp
    weft = rng.standard_normal(nt).astype(np.float32)
    warp = rng.standard_normal(nt).astype(np.float32)
    # slow thickness drift along each thread
    drift_w = periodic_1d(n, 18.0 * ss, seed + 1)
    iy = np.arange(n) // tp
    ix = np.arange(n) // tp
    chk = ((iy[:, None] + ix[None, :]) % 2).astype(np.float32)
    top = chk * (weft[iy][:, None] + 0.35 * drift_w[None, :]) + (1.0 - chk) * warp[ix][None, :]
    fy = (np.arange(n) % tp + 0.5) / tp
    prof = 0.5 * np.cos(2 * np.pi * fy)
    tex = top + 0.6 * (prof[:, None] + prof[None, :])
    tex = tex / (tex.std() + 1e-9) * thread
    # slubs: short thick spots along single weft threads (wrapping)
    sl = np.zeros((n, n), np.float32)
    count = int(n * n / (ss * ss) / 90)
    for _ in range(count):
        y = int(rng.integers(nt)) * tp
        x0 = int(rng.integers(n))
        L = int(rng.integers(3 * ss, 11 * ss))
        a = rng.choice([1.0, -0.8]) * rng.uniform(0.6, 1.0)
        xs = (x0 + np.arange(L)) % n
        env = np.sin(np.linspace(0, np.pi, L)) ** 0.7
        sl[y:y + tp, xs] += a * env[None, :]
    tex = tex + slub * sl
    # ageing mottle: blooms 24-64 px
    m = 0.55 * periodic_noise(n, 6.0 * ss, seed + 2) + 0.45 * periodic_noise(n, 2.5 * ss, seed + 3)
    m = m / (m.std() + 1e-9)
    # no landmarks: soft-clip the blooms so no single spot stands out of the repeat
    m = np.tanh(m / 1.6) * 1.6
    return tex + mottle * m, m


def paint(G, variant="light", seed=None):
    variant = variant or "light"
    lk = LOOK[variant]
    seed = (SPEC["seed"] if seed is None else seed) + (0 if variant == "light" else 50)
    n = G.nx
    lv, m = silk_levels(n, G.ss, seed, lk["thread"], lk["slub"], lk["mottle"])
    base = P.rgb(lk["base"])
    # the mottle also shifts the hue a little towards a warmer, older silk
    warm = P.rgb(lk["warm"]) - base
    wm = np.clip(m, 0, None)
    wm = wm - wm.mean()
    col = base[None, None, :] + lv[..., None] / 255.0 + 0.10 * wm[..., None] * warm
    col = np.clip(col, 0, 1)
    out = np.ones(G.shape + (4,), np.float32)
    out[..., :3] = col
    return out
