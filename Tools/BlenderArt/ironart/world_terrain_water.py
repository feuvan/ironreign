"""World Terrain family - water textures (numpy only).

    water_normal(size)   ArtSource/Textures/Water_Normal.png: tileable tangent-space normal map of
                         gentle wind ripples (OpenGL convention: +X right, +Y up; Unreal flips green
                         on import - ArtSource/manifest.json "normalMapConvention": "opengl")
    water_foam(size)     ArtSource/Textures/Water_Foam.png: tileable greyscale foam/surf pattern
    sea_colour(...)      the 2D map's painted sea (depth-tinted, surf line), on the albedo texel grid

Everything tileable is synthesised on a periodic domain with an FFT (integer wave numbers), so the
textures repeat seamlessly.
"""

import math

import numpy as np

from . import terrain as T


def _spectrum_height(n, seed, k_lo, k_hi, slope=2.0, wind_deg=30.0, directional=0.55, spread=2):
    rng = np.random.default_rng(seed)
    k = np.fft.fftfreq(n, 1.0 / n)
    kx, ky = np.meshgrid(k, k)
    kk = np.hypot(kx, ky)
    kk[0, 0] = 1.0
    amp = kk ** (-slope)
    amp *= T.smoothstep(k_lo * 0.6, k_lo, kk) * T.smoothstep(k_hi, k_hi * 0.6, kk)
    th = np.arctan2(ky, kx)
    w = math.radians(wind_deg)
    amp *= (1.0 - directional) + directional * np.abs(np.cos(th - w)) ** spread
    amp[0, 0] = 0.0
    ph = rng.uniform(0, 2 * np.pi, (n, n))
    spec = amp * np.exp(1j * ph)
    hgt = np.fft.ifft2(spec).real
    dx = np.fft.ifft2(spec * (2j * np.pi * kx / n)).real
    dy = np.fft.ifft2(spec * (2j * np.pi * ky / n)).real
    s = hgt.std() + 1e-12
    return hgt / s, dx / s, dy / s


def water_normal(n=1024, seed=31, tilt_deg=11.0):
    """RGB uint8 tileable normal map. Two ripple bands (long swell + short chop), RMS tilt
    ``tilt_deg``.  Returns (rgb uint8, info dict)."""
    _h1, dx1, dy1 = _spectrum_height(n, seed, 4, 24, 2.4, 25.0, 0.8, spread=4)
    _h2, dx2, dy2 = _spectrum_height(n, seed + 1, 16, 64, 2.3, 50.0, 0.5, spread=2)
    dx = dx1 + 0.4 * dx2
    dy = dy1 + 0.4 * dy2
    g = np.sqrt(dx * dx + dy * dy)
    k = math.tan(math.radians(tilt_deg)) / (np.sqrt((g ** 2).mean()) + 1e-9)
    # rows grow downwards; texture +V is up -> dh/dv = -dh/drow
    nx = -dx * k
    ny = dy * k
    nz = np.ones_like(nx)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    nrm = np.stack([nx / ln, ny / ln, nz / ln], -1)
    rgb = np.round((nrm * 0.5 + 0.5) * 255.0).clip(0, 255).astype(np.uint8)
    ang = np.degrees(np.arccos(np.clip(nrm[..., 2], -1, 1)))
    info = {"rms_tilt_deg": float(np.sqrt((ang ** 2).mean())), "max_tilt_deg": float(ang.max()),
            "mean_rgb": [float(c) for c in rgb.reshape(-1, 3).mean(0)]}
    return rgb, info


def _periodic_worley(n, cells, seed):
    """F2-F1 cellular edges on a periodic domain (foam cell borders): one feature point per
    cell, 3x3 neighbour search with wrap-around."""
    rng = np.random.default_rng(seed)
    pts = rng.random((cells, cells, 2))
    cs = n / cells
    ys, xs = np.mgrid[0:n, 0:n].astype(np.float32)
    ci = (xs // cs).astype(np.int64)
    cj = (ys // cs).astype(np.int64)
    best1 = np.full((n, n), 1e9, np.float32)
    best2 = np.full((n, n), 1e9, np.float32)
    for oj in (-1, 0, 1):
        for oi in (-1, 0, 1):
            ni = (ci + oi) % cells
            nj = (cj + oj) % cells
            px = (ci + oi + pts[nj, ni, 0]) * cs
            py = (cj + oj + pts[nj, ni, 1]) * cs
            d = np.sqrt((xs - px) ** 2 + (ys - py) ** 2)
            m = d < best1
            best2 = np.where(m, best1, np.minimum(best2, d))
            best1 = np.where(m, d, best1)
    return best2 - best1


def water_foam(n=1024, seed=41):
    """Greyscale uint8 tileable foam: bubbly cell borders broken up by streaky noise."""
    edges = _periodic_worley(n // 2, 60, seed)
    from PIL import Image
    edges = np.asarray(Image.fromarray(edges.astype(np.float32), "F").resize((n, n), Image.BICUBIC))
    h, _, _ = _spectrum_height(n, seed + 2, 3, 40, 1.6, 20.0, 0.5)
    h2, _, _ = _spectrum_height(n, seed + 3, 30, 200, 1.4, 0.0, 0.0)
    lace = T.smoothstep(3.0, 0.6, edges)
    patch = T.smoothstep(-0.2, 1.0, h)
    foam = np.clip(lace * patch * (0.75 + 0.25 * T.smoothstep(-1, 1, h2)) + 0.25 * T.smoothstep(1.2, 2.2, h), 0, 1)
    return np.round(foam * 255.0).astype(np.uint8)


def hexc(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


def sea_colour(painter, rec):
    """Painted sea for the 2D map (sRGB float, texel grid): depth tint from the bathymetry, the
    sea floor showing through the first metre, a broken surf line and a faint second swell."""
    h = painter.h
    dep = np.clip(-h, 0.0, 60.0)
    n = painter.vn(90.0, 401, 3)
    n2 = painter.vn(4.0, 402, 2)
    sh, mid, deep, aby = (hexc(rec[k]) for k in ("shallow", "mid", "deep", "abyss"))
    t1 = T.smoothstep(0.2, 8.0, dep + 0.5 * n)
    t2 = T.smoothstep(5.0, 26.0, dep + 1.2 * n)
    t3 = T.smoothstep(24.0, 40.0, dep + 1.5 * n)
    col = sh + (mid - sh) * t1[..., None]
    col = col + (deep - col) * t2[..., None]
    col = col + (aby - col) * t3[..., None]
    # sea floor visible through clear shallow water
    see = np.exp(-dep / 1.4)[..., None] * 0.55
    col = col * (1 - see) + painter.base * hexc("#9FC7C0") * see
    # surf: a broken white line at the waterline and a faint second line ~1 m deep
    foam = hexc(rec["foam"])
    surf = np.exp(-((dep - 0.12) / 0.16) ** 2) * T.smoothstep(-0.6, 0.4, n2)
    swell = 0.35 * np.exp(-((dep - 1.1 - 0.3 * n) / 0.22) ** 2) * T.smoothstep(0.2, 1.2, n2)
    col = col + (foam - col) * np.clip(surf * 0.85 + swell, 0, 1)[..., None]
    col *= (1.0 + 0.012 * n2)[..., None]
    return np.clip(col, 0, 1)
