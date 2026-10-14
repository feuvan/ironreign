"""Shared builders of the UI chrome pieces (numpy only): wood grain, beads, xuan paper, folded
corner helpers, the 9-slice centre mask and the corner-stamp plumbing."""

import math

import numpy as np

from ironart import ui_chrome_motifs as MO
from ironart import ui_chrome_sdf as S


class Folded:
    """Grid-like wrapper exposing (folded / local) coordinate arrays as X / Y (motif functions
    take any object with X and Y)."""

    def __init__(self, u, v):
        self.X, self.Y = u, v


def fold_poly(G, poly):
    """Polygon sd in the diagonal-folded frame (u >= v), via both mirror images."""
    a = S.sd_polygon(G, poly)
    b = S.sd_polygon(G, [(y, x) for x, y in poly])
    return np.where(G.X >= G.Y, a, b)


def grain1d(d, seed, freq=0.7, lo=0.5, hi=1.3):
    """Straight wood grain as a function of one coordinate only (stretch-safe along a rail)."""
    rng = np.random.default_rng(seed)
    n = 8192
    lat = rng.random(n).astype(np.float32)
    x = np.clip(d * freq + 7.0, 0, n - 2)
    i = np.floor(x).astype(np.int32)
    f = x - i
    f = f * f * (3 - 2 * f)
    v = lat[i] * (1 - f) + lat[i + 1] * f
    streak = np.clip((v - 0.35) / 0.5, 0, 1) ** 1.6
    x2 = np.clip(d * 0.35 + 50.0, 0, n - 1002)
    i2 = np.floor(x2).astype(np.int32)
    f2 = x2 - i2
    slow = lat[i2 + 1000] * (1 - f2) + lat[i2 + 1001] * f2
    return (lo + (hi - lo) * (0.65 * streak + 0.35 * slow)).astype(np.float32)


def grain2d(along, across, seed, freq=0.7, wave=0.35, lo=0.5, hi=1.3, ss=4):
    """Wood figure for pieces that are never stretched: grain lines along ``along`` whose
    position wanders slowly (``wave`` px), plus pores."""
    shape = along.shape
    wob = S.fbm(shape, 30.0 * ss, seed + 3, octaves=3, aniso=(3.0, 0.4)) - 0.5
    g = grain1d(across + wave * 6.0 * wob, seed, freq, lo, hi)
    pores = S.value_noise(shape, 0.8 * ss, seed + 5, aniso=(4.0, 0.6))
    return (g * (0.94 + 0.12 * pores)).astype(np.float32)


def bead(c, r, z0, n=9, flat=0.75):
    """Profile points of a round bead centred at d = c (radius r) standing on z0."""
    a = np.linspace(np.pi, 0, n)
    return [(c + r * np.cos(t), z0 + r * flat * np.sin(t)) for t in a]


def centre_mask(G, W, H, margins, fade=8.0):
    """1 inside the 9-slice centre, fading to 0 at its boundary over ``fade`` px (texture that
    is only allowed where the image is stretched in both directions)."""
    l, t, r, b = margins
    cx = np.minimum(G.X - l, (W - r) - G.X)
    cy = np.minimum(G.Y - t, (H - b) - G.Y)
    c = np.clip(np.minimum(cx, cy) / fade, 0, 1)
    return (c * c * (3 - 2 * c)).astype(np.float32)


def xuan(shape, ss, seed=0, fibre=1.0, formation=1.0):
    """Xuan paper albedo multiplier (mean 1) + relief (mm): cloudy formation + bast fibres."""
    h, w = shape
    form = S.fbm(shape, 22.0 * ss, seed, octaves=4, gain=0.55)
    form = (form - form.mean()) / (form.std() + 1e-6)
    fib = S.fibres(shape, count=w * h / (ss * ss) * 0.10, length=9 * ss, width=0.22 * ss,
                   seed=seed + 7, curl=0.5, lo=0.4, hi=1.0)
    fib2 = S.fibres(shape, count=w * h / (ss * ss) * 0.02, length=22 * ss, width=0.3 * ss,
                    seed=seed + 9, curl=0.35, lo=0.5, hi=1.0)
    fibs = S.blur(fib + 0.6 * fib2, 0.35 * ss / 4)
    fibs = fibs - fibs.mean()
    tex = 1.0 + 0.012 * formation * form + 0.035 * fibre * fibs
    rel = 0.025 * fibre * fibs + 0.01 * formation * form
    return tex.astype(np.float32), rel.astype(np.float32)


def stamp(G, local):
    """Top-left local array -> full-size array with the four mirrored corners."""
    return MO.stamp_corners(np.zeros(G.shape, np.float32), local)


def stamp_x(G, local, y0=0):
    """Paste a left-edge local array at the left and (mirrored) right edge, rows from y0."""
    out = np.zeros(G.shape, np.float32)
    h, w = local.shape
    out[y0:y0 + h, :w] = np.maximum(out[y0:y0 + h, :w], local)
    out[y0:y0 + h, -w:] = np.maximum(out[y0:y0 + h, -w:], local[:, ::-1])
    return out


def recess_shade(z, ss, radius=1.2, k=2.2, floor=0.55):
    """Albedo multiplier darkening recesses (patina / dirt collects where the relief is low
    relative to its neighbourhood)."""
    rec = np.clip(S.blur(z, radius * ss) - z, 0, None)
    return np.clip(1.0 - k * rec, floor, 1.0).astype(np.float32)


def carved_cloud(ss, size, w, h, cx, cy, rot=0.0, mirror=False, height=0.55, lobes=None,
                 tail=True):
    """A carved (relief) xiangyun on a local w x h grid: returns (height, mask, groove_mask)."""
    G = S.Grid(w, h, ss)
    sd, eng = MO.cloud(G, cx, cy, size, rot=rot, mirror=mirror, lobes=lobes, tail=tail)
    z = MO.dome(sd, 0.9, height)
    z = S.blur(z, 0.25 * ss)
    z = z + S.groove(eng, 0.30, height * 0.45) * (sd < -0.2)
    return z.astype(np.float32), S.aa_mask(sd, G), S.aa_mask(eng - 0.18, G) * (sd < -0.2)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return (t * t * (3 - 2 * t)).astype(np.float32)


def lerp3(a, b, t):
    """Per-pixel lerp of two RGB colours (arrays of 3) by t (H x W)."""
    a = np.asarray(a, np.float32).reshape(1, 1, 3)
    b = np.asarray(b, np.float32).reshape(1, 1, 3)
    return a + (b - a) * t[..., None]


def vgrad(G, H, k=0.12):
    """Vertical-only gradient multiplier (top brighter) - safe to 9-slice."""
    return (1.0 + k * (0.5 - G.Y / H) * 2.0).astype(np.float32)


def deg(a):
    return math.radians(a)
