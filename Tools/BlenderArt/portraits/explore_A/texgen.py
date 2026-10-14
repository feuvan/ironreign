"""Numpy texture helpers: UV-space rasterisation, value noise / fbm, blur, padding.

No bpy and no scipy (runs inside Blender's python 3.12 with numpy only).
"""

import numpy as np


# ------------------------------------------------------------------------------------ rasteriser
def rasterize(uv_tris, vals, res, chans):
    """Barycentric fill of triangles in UV space (vectorised in buckets of bbox size).

    uv_tris  (T,3,2) uv in [0,1] (v up)
    vals     (T,3,C) per-corner values
    Returns (img (res,res,C) float32, cov (res,res) bool).  Row 0 = v=1 (image convention)."""
    img = np.zeros((res, res, chans), np.float32)
    cov = np.zeros((res, res), bool)
    P = uv_tris.astype(np.float64).copy()
    P[..., 0] = P[..., 0] * res - 0.5
    P[..., 1] = (1.0 - P[..., 1]) * res - 0.5
    x0 = np.floor(P[..., 0].min(1)).astype(int)
    y0 = np.floor(P[..., 1].min(1)).astype(int)
    span = np.maximum(np.ceil(P[..., 0].max(1)).astype(int) - x0,
                      np.ceil(P[..., 1].max(1)).astype(int) - y0) + 1
    a, b, c = P[:, 0], P[:, 1], P[:, 2]
    den = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    ok = np.abs(den) > 1e-12
    lo = 0
    for S in (4, 8, 16, 32, 64, 128, 256, 512, 2048):
        sel = np.where(ok & (span > lo) & (span <= S))[0]
        lo = S
        if len(sel) == 0:
            continue
        oy, ox = np.meshgrid(np.arange(S), np.arange(S), indexing="ij")
        oy, ox = oy.ravel(), ox.ravel()
        step = max(1, int(4_000_000 // (S * S)))
        for k in range(0, len(sel), step):
            t = sel[k:k + step]
            xs = x0[t][:, None] + ox[None, :]
            ys = y0[t][:, None] + oy[None, :]
            ax_, ay_ = a[t, 0][:, None], a[t, 1][:, None]
            bx_, by_ = b[t, 0][:, None], b[t, 1][:, None]
            cx_, cy_ = c[t, 0][:, None], c[t, 1][:, None]
            d = den[t][:, None]
            w0 = ((by_ - cy_) * (xs - cx_) + (cx_ - bx_) * (ys - cy_)) / d
            w1 = ((cy_ - ay_) * (xs - cx_) + (ax_ - cx_) * (ys - cy_)) / d
            w2 = 1.0 - w0 - w1
            e = -0.02
            inside = (w0 >= e) & (w1 >= e) & (w2 >= e) & (xs >= 0) & (ys >= 0) & (xs < res) & (ys < res)
            ti, pi = np.nonzero(inside)
            if len(ti) == 0:
                continue
            v = vals[t[ti]]  # (k,3,C)
            ww = np.stack([w0[ti, pi], w1[ti, pi], w2[ti, pi]], 1)[..., None]
            img[ys[ti, pi], xs[ti, pi]] = (v * ww).sum(1)
            cov[ys[ti, pi], xs[ti, pi]] = True
    return img, cov


def pad(img, cov, iters=6):
    """Bleed covered texels into uncovered neighbours (avoids seams under filtering)."""
    img = img.copy()
    cov = cov.copy()
    for _ in range(iters):
        acc = np.zeros_like(img)
        cnt = np.zeros(cov.shape, np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            sh = np.roll(np.roll(cov, dy, 0), dx, 1)
            acc += np.roll(np.roll(img, dy, 0), dx, 1) * sh[..., None]
            cnt += sh
        new = (~cov) & (cnt > 0)
        img[new] = acc[new] / cnt[new, None]
        cov = cov | new
    return img, cov


# ---------------------------------------------------------------------------------------- noise
def _fade(t):
    return t * t * t * (t * (t * 6 - 15) + 10)


def value_noise(h, w, cell, rng, offset=(0.0, 0.0)):
    """Smooth value noise in [0,1] with feature size ``cell`` pixels."""
    gh, gw = int(h / cell) + 3, int(w / cell) + 3
    g = rng.random((gh, gw)).astype(np.float32)
    y = (np.arange(h, dtype=np.float32) + offset[0]) / cell
    x = (np.arange(w, dtype=np.float32) + offset[1]) / cell
    yi = np.floor(y).astype(int) % (gh - 1)
    xi = np.floor(x).astype(int) % (gw - 1)
    fy = _fade(y - np.floor(y))[:, None]
    fx = _fade(x - np.floor(x))[None, :]
    a = g[yi][:, xi]
    b = g[yi][:, xi + 1]
    c = g[yi + 1][:, xi]
    d = g[yi + 1][:, xi + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def fbm(h, w, cell, octaves, rng, gain=0.5, lac=2.0):
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    c = cell
    for _ in range(octaves):
        out += amp * value_noise(h, w, max(c, 1.0), rng)
        tot += amp
        amp *= gain
        c /= lac
    return out / tot


def noise_at(px, py, cell, rng, octaves=1, gain=0.5):
    """Value noise sampled at arbitrary float pixel coordinates (1-D arrays)."""
    out = np.zeros(px.shape, np.float32)
    amp, tot = 1.0, 0.0
    c = cell
    for _ in range(octaves):
        n = 257
        g = rng.random((n, n)).astype(np.float32)
        x, y = px / c, py / c
        xi, yi = np.floor(x).astype(int), np.floor(y).astype(int)
        fx, fy = _fade(x - xi), _fade(y - yi)
        xi %= n - 1
        yi %= n - 1
        v = ((g[yi, xi] * (1 - fx) + g[yi, xi + 1] * fx) * (1 - fy)
             + (g[yi + 1, xi] * (1 - fx) + g[yi + 1, xi + 1] * fx) * fy)
        out += amp * v
        tot += amp
        amp *= gain
        c /= 2.0
    return out / tot


def blur(img, sigma):
    """Separable gaussian blur (numpy, reflect edges)."""
    if sigma <= 0:
        return img
    r = int(3 * sigma + 0.5)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2).astype(np.float32)
    k /= k.sum()
    squeeze = img.ndim == 2
    a = img[..., None] if squeeze else img
    a = np.pad(a, ((r, r), (0, 0), (0, 0)), mode="reflect")
    a = sum(k[i] * a[i:i + a.shape[0] - 2 * r] for i in range(2 * r + 1))
    a = np.pad(a, ((0, 0), (r, r), (0, 0)), mode="reflect")
    a = sum(k[i] * a[:, i:i + a.shape[1] - 2 * r] for i in range(2 * r + 1))
    return a[..., 0] if squeeze else a


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    t = np.asarray(t)
    if t.ndim == a.ndim - 1:
        t = t[..., None]
    return a + (b - a) * t
