"""Geometric wrinkles and folds (numpy): a height field over the base-mesh rest positions,
applied as real displacement on the subdivided head so creases catch the key light and cast
tiny shadows (bump alone reads as CG at portrait scale).

All lengths in metres in base-mesh Blender coordinates (``mh.to_blender(base.verts)``):
eyes at z 0.728, brows 0.75, hairline ~0.805, mouth corners (+-0.0245, 0.660).
"""

import numpy as np


def _ss(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _groove(d, w):
    """Crease profile across a line at signed distance d: sharp V-ish groove of half-width w."""
    return np.exp(-(d / w) ** 2)


def _seg_dist(P, a, b):
    """Signed-ish distance (in the plane spanned by the segment and the face normal -Y) to
    segment a-b; returns (unsigned distance, t along segment, side sign)."""
    a, b = np.asarray(a, np.float32), np.asarray(b, np.float32)
    ab = b - a
    t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
    pr = a + t[:, None] * ab
    d = np.linalg.norm(P - pr, axis=1)
    return d, t


def _poly(P, pts):
    best = np.full(len(P), 1e9, np.float32)
    bt = np.zeros(len(P), np.float32)
    n = len(pts) - 1
    for i in range(n):
        d, t = _seg_dist(P, pts[i], pts[i + 1])
        m = d < best
        best[m] = d[m]
        bt[m] = (i + t[m]) / n
    return best, bt


def _noise1(x, seed, freq):
    rng = np.random.default_rng(seed)
    ph = rng.random(4) * 6.283
    return (np.sin(x * freq + ph[0]) + 0.5 * np.sin(x * freq * 2.3 + ph[1]) + 0.25 * np.sin(x * freq * 5.1 + ph[2])) / 1.75


def height(R, Z, age_w=0.5, frown=0.0, smile=0.0, gaunt=0.0, seed=0):
    """Per-vertex displacement (m, + outward) for rest positions R (N,3) and zone dict Z."""
    x, y, z = R[:, 0], R[:, 1], R[:, 2]
    ax = np.abs(x)
    side = np.sign(x) + (x == 0)
    h = np.zeros(len(R), np.float32)
    front = _ss(-0.10, -0.13, y)          # on the face (y more negative = more frontal)
    w = age_w
    # ---- forehead lines: 3-4 horizontal creases, shorter towards the temples, wavy, broken
    if w > 0:
        fh = Z.get("forehead", np.ones(len(R)))
        for k, zc in enumerate((0.767, 0.777, 0.788, 0.799)):
            wav = 0.0012 * _noise1(x * 1.0, seed + k, 90.0) + 0.0018 * (ax / 0.05) ** 2
            depth = 0.0012 * w * (1.0 - 0.18 * k) * _ss(0.055 - 0.006 * k, 0.025, ax)
            brk = 0.55 + 0.45 * _noise1(x, seed + 10 + k, 160.0)
            h -= depth * brk * _groove(z - zc - wav, 0.0012) * front * _ss(0.0, 0.2, fh)
            # soft bulge between creases
            h += depth * 0.35 * _groove(z - zc - 0.005 - wav, 0.0028) * front * _ss(0.0, 0.2, fh)
    # ---- glabella / frown lines (stern officers): two vertical creases + brow knot
    fr = max(frown, 0.0)
    if fr > 0 or w > 0.4:
        amt = fr + 0.4 * max(0.0, w - 0.4)
        for sx in (1, -1):
            d = np.abs(x - sx * (0.0055 + 0.0012 * (z - 0.745) / 0.01))
            band = _ss(0.736, 0.742, z) * _ss(0.764, 0.755, z)
            h -= 0.0008 * amt * _groove(d, 0.0010) * band * front
        # corrugator bulge above the inner brow
        knot = np.exp(-(((ax - 0.014) / 0.008) ** 2 + ((z - 0.752) / 0.006) ** 2))
        h += 0.0012 * amt * knot * front
        # horizontal crease across the nose root
        h -= 0.0004 * amt * _groove(z - 0.737, 0.0012) * _ss(0.012, 0.004, ax) * front
    # ---- crow's feet: 3-4 fanning lines from the outer eye corner
    if w > 0:
        cx, cz = 0.049, 0.728
        dx = ax - cx
        dz = z - cz
        ang = np.arctan2(dz, dx)
        r = np.sqrt(dx ** 2 + dz ** 2)
        lines = 0.5 + 0.5 * np.cos(ang * 9.0 + 0.4)
        lines = lines ** 6
        m = _ss(0.003, 0.007, r) * _ss(0.024, 0.012, r) * (dx > -0.002) * (y > -0.12) * (y < -0.06)
        h -= 0.00045 * w * lines * m
    # ---- under-eye: tear trough groove + bag bulge
    if w > 0:
        for sx in (1, -1):
            ex = sx * 0.0308
            d, t = _poly(R, [(ex - sx * 0.012, -0.1345, 0.7195), (ex, -0.137, 0.7135), (ex + sx * 0.014, -0.130, 0.7165)])
            h += 0.0011 * w * _groove(d - 0.0025, 0.0028)          # bag
            h -= 0.0009 * w * _groove(d - 0.0065, 0.0016)          # trough below the bag
    # ---- nasolabial fold: groove from the nose wing past the mouth corner, cheek bulge above
    nl = max(w, smile * 0.8)
    if nl > 0:
        for sx in (1, -1):
            pts = [(sx * 0.0195, -0.149, 0.684), (sx * 0.0265, -0.147, 0.672), (sx * 0.0315, -0.142, 0.660),
                   (sx * 0.0335, -0.136, 0.648)]
            d, t = _poly(R, pts)
            # which side of the line: cheek (outer) side gets the bulge
            outer = (ax - np.interp(z, [0.648, 0.660, 0.672, 0.684], [0.0335, 0.0315, 0.0265, 0.0195])) > 0
            fade = _ss(0.0, 0.15, t) * _ss(1.0, 0.8, t)
            h -= 0.0014 * nl * _groove(d, 0.0016) * fade
            h += 0.0016 * nl * _groove(d - 0.004, 0.004) * fade * outer
    # ---- marionette lines (old) and mouth-corner creases
    if w > 0.3:
        for sx in (1, -1):
            d, t = _poly(R, [(sx * 0.0265, -0.142, 0.658), (sx * 0.0275, -0.139, 0.645), (sx * 0.026, -0.135, 0.632)])
            h -= 0.0008 * (w - 0.3) * _groove(d, 0.0015) * _ss(1.0, 0.7, t)
    # ---- gaunt cheeks: hollow under the cheekbone
    if gaunt > 0:
        hol = np.exp(-(((ax - 0.050) / 0.012) ** 2 + ((z - 0.680) / 0.012) ** 2)) * (y < -0.09)
        h -= 0.0035 * gaunt * hol
    # ---- neck lines (old)
    if w > 0.4:
        nk = Z.get("neck", np.zeros(len(R)))
        for k, zc in enumerate((0.585, 0.570)):
            h -= 0.0006 * (w - 0.4) * _groove(z - zc - 0.004 * _noise1(x, seed + 30 + k, 60.0), 0.0015) * nk
    return h.astype(np.float32)
