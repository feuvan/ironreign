"""UI chrome family: drawn ornament vocabulary (numpy, no bpy) - gongbi 白描 outlines.

Every motif is authored as closed outlines (cubic Bezier paths -> polygons) in a unit frame and
turned into an exact signed distance field on the grid (``sd`` < 0 inside, target px), so a
piece can fill it (mud-gold, mineral colour), stroke it (ink contour) and engrave it (inner
contour = iso-line of the same field).  Parts are kept *separate* (petals, lobes) so the
silhouettes stay readable at 10-20 px.

Vocabulary
    petal / rosette     pointed persimmon-calyx petal and the four-petal rosette (柿蒂)
    ruyi_head           trefoil cloud head (如意云头) with a pointed waist
    cloud_scroll        xiangyun cloud strokes (volutes with tails) as tapered polylines
    volute              tapered spiral stroke
"""

import math

import numpy as np

from . import ui_chrome_sdf as S


# =============================================================================================
# paths
# =============================================================================================
def cubic(p0, p1, p2, p3, n=24):
    t = np.linspace(0.0, 1.0, n, dtype=np.float64)[:, None]
    p0, p1, p2, p3 = (np.asarray(p, np.float64) for p in (p0, p1, p2, p3))
    return ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3 * p3


def path(segments, n=20):
    """Join cubic segments [(p0, c1, c2, p3), ...] (each p0 = previous p3) into a polyline."""
    pts = []
    for i, seg in enumerate(segments):
        c = cubic(*seg, n=n)
        pts.append(c if i == 0 else c[1:])
    return np.concatenate(pts, 0)


def xform(pts, scale=1.0, rot=0.0, tx=0.0, ty=0.0, sx=1.0, sy=1.0):
    """Scale (sx, sy mirror), rotate (deg, clockwise on screen with y down), translate."""
    p = np.asarray(pts, np.float64) * np.array([sx, sy]) * scale
    if rot:
        a = math.radians(rot)
        c, s = math.cos(a), math.sin(a)
        p = np.stack([p[:, 0] * c - p[:, 1] * s, p[:, 0] * s + p[:, 1] * c], 1)
    return (p + np.array([tx, ty])).astype(np.float32)


def mirror_closed(half):
    """Close a right-half outline (from the top of the axis x = 0 down to the bottom of the
    axis) with its mirror image."""
    left = half[::-1].copy()
    left[:, 0] *= -1.0
    return np.concatenate([half, left[1:-1]], 0)


def sd_polys(G, polys, out=None, pad=2.0):
    """Union of filled polygons (exact sd)."""
    out = G.empty() if out is None else out
    for p in polys:
        S.sd_polygon(G, p, out=out, pad=pad)
    return out


# =============================================================================================
# petals, rosette
# =============================================================================================
def petal_outline(n=18):
    """Persimmon-calyx petal pointing along +x, base at the origin, length 1: narrow waist,
    full rounded shoulders, a pointed tip."""
    half = path([
        ((0.0, 0.0), (0.05, -0.10), (0.20, -0.30), (0.45, -0.36)),
        ((0.45, -0.36), (0.68, -0.42), (0.86, -0.30), (0.88, -0.16)),
        ((0.88, -0.16), (0.90, -0.08), (0.96, -0.03), (1.0, 0.0)),
    ], n)
    other = half[::-1].copy()
    other[:, 1] *= -1.0
    return np.concatenate([half, other[1:-1]], 0)


def rosette(G, cx, cy, r, rot=45.0, petal_from=0.18, heart=0.24, out=None):
    """Four separate petals (柿蒂) around a round heart: returns (petals_sd, heart_sd)."""
    base = petal_outline()
    polys = []
    for k in range(4):
        L = r * (1.0 - petal_from)
        p = xform(base, scale=L, rot=rot + 90.0 * k)
        a = math.radians(rot + 90.0 * k)
        p = p + np.array([cx + r * petal_from * math.cos(a), cy + r * petal_from * math.sin(a)],
                         np.float32)
        polys.append(p)
    pet = sd_polys(G, polys, out=out)
    hrt = G.empty()
    S.sd_circle(G, cx, cy, heart * r, out=hrt)
    return pet, hrt


# =============================================================================================
# ruyi head
# =============================================================================================
def ruyi_outline(n=16):
    """Trefoil cloud head (如意) in a unit frame: the point (waist) at (0, 1), the central
    lobe's crown at (0, -1), side lobes curling down and in at x = +-1.  y down."""
    half = path([
        ((0.0, -1.00), (0.28, -1.00), (0.46, -0.86), (0.46, -0.62)),     # central lobe crown
        ((0.46, -0.62), (0.46, -0.50), (0.40, -0.44), (0.36, -0.38)),    # into the notch
        ((0.36, -0.38), (0.55, -0.56), (0.92, -0.52), (0.98, -0.18)),    # side lobe top
        ((0.98, -0.18), (1.04, 0.14), (0.80, 0.34), (0.58, 0.26)),       # side lobe outer curl
        ((0.58, 0.26), (0.46, 0.22), (0.40, 0.30), (0.36, 0.42)),        # tuck under
        ((0.36, 0.42), (0.28, 0.66), (0.10, 0.84), (0.0, 1.00)),         # waist to the point
    ], n)
    return mirror_closed(half)


def ruyi_curls(n=40):
    """Engraved curl lines inside a ruyi head (unit frame): one in each side lobe and a
    heart line in the central lobe, as polylines."""
    out = []
    for sx in (1.0, -1.0):
        t = np.linspace(0.0, 1.0, n)
        ang = np.radians(200.0 - 330.0 * t) if sx > 0 else np.radians(-20.0 + 330.0 * t)
        rad = 0.30 * (1.0 - 0.75 * t)
        cx, cy = 0.66 * sx, -0.10
        out.append(np.stack([cx + rad * np.cos(ang) * sx * (1 if sx > 0 else -1),
                             cy + rad * np.sin(ang)], 1))
    heart = path([((0.0, 0.55), (0.0, 0.20), (0.0, -0.20), (0.0, -0.62))], n // 2)
    out.append(heart)
    return out


def ruyi(G, cx, cy, size, rot=0.0, curls=True, out=None):
    """A ruyi head of half-size ``size`` px centred at (cx, cy), point direction = +y rotated
    by ``rot``.  Returns (shape_sd, curl_line_distance)."""
    poly = xform(ruyi_outline(), scale=size, rot=rot, tx=cx, ty=cy)
    sd = sd_polys(G, [poly], out=out)
    lines = G.empty()
    if curls:
        for c in ruyi_curls():
            S.sd_polyline(G, xform(c, scale=size, rot=rot, tx=cx, ty=cy), 0.0, out=lines, pad=1.0)
    return sd, lines


# =============================================================================================
# strokes
# =============================================================================================
def volute(cx, cy, r0, r1, turns, a0, cw=True, w0=1.0, w1=0.35, n=None):
    """Tapered spiral stroke (points, radii) from radius r0 at angle a0 (deg) inwards to r1."""
    n = n or max(24, int(72 * turns))
    t = np.linspace(0.0, 1.0, n, dtype=np.float32)
    ang = math.radians(a0) + (1.0 if cw else -1.0) * t * turns * 2.0 * math.pi
    rad = r0 + (r1 - r0) * t
    pts = np.stack([cx + rad * np.cos(ang), cy + rad * np.sin(ang)], 1).astype(np.float32)
    w = (w0 + (w1 - w0) * t ** 0.9) * 0.5
    return pts, w.astype(np.float32)


def taper(n, w0, wm, w1):
    """Brush profile: entry w0 -> body wm -> exit w1 (radii)."""
    t = np.linspace(0.0, 1.0, n, dtype=np.float32)
    a = np.clip(t / 0.25, 0, 1)
    b = np.clip((1.0 - t) / 0.45, 0, 1)
    r = np.where(t < 0.25, w0 + (wm - w0) * np.sin(a * math.pi / 2),
                 w1 + (wm - w1) * np.sin(b * math.pi / 2))
    return (r * 0.5).astype(np.float32)


def strokes_sd(G, strokes, out=None, pad=2.0):
    out = G.empty() if out is None else out
    for pts, rad in strokes:
        S.sd_polyline(G, pts, rad, out=out, pad=pad)
    return out


# =============================================================================================
# xiangyun cloud (祥云)
# =============================================================================================
def xiangyun(G, cx, cy, size, flip=False, out_shape=None, out_lines=None):
    """A 'auspicious cloud' head: three lobes on a flat floor (a big central lobe, a smaller
    lobe on each side) with an inward spiral engraved in each, and a tapering tail sweeping
    out from the right lobe (``flip`` mirrors it to the left).  ``size`` = half width in px.
    Returns (shape_sd, line_distance) - fill the shape, draw the lines inside it."""
    s = size
    sx = -1.0 if flip else 1.0
    lobes = [(-0.50, 0.08, 0.36, False), (0.0, -0.12, 0.46, True), (0.50, 0.10, 0.33, True)]
    shape = G.empty() if out_shape is None else out_shape
    lines = G.empty() if out_lines is None else out_lines
    sd_l = None
    for (lx, ly, lr, cw) in lobes:
        c = np.hypot(G.X - (cx + sx * lx * s), G.Y - (cy + ly * s)) - lr * s
        sd_l = c if sd_l is None else S.smooth_union(sd_l, c, 0.10 * s)
    floor = S.sd_round_box(G, cx, cy + 0.30 * s, 0.70 * s, 0.13 * s, 0.12 * s)
    sd_l = S.smooth_union(sd_l, floor, 0.12 * s)
    # tail: a tapered stroke leaving the right lobe's base and curling down/out
    tail = cubic((cx + sx * 0.62 * s, cy + 0.36 * s), (cx + sx * 0.95 * s, cy + 0.50 * s),
                 (cx + sx * 1.25 * s, cy + 0.42 * s), (cx + sx * 1.50 * s, cy + 0.18 * s), 24)
    t_sd = G.empty()
    S.sd_polyline(G, tail.astype(np.float32), taper(len(tail), 0.26 * s, 0.22 * s, 0.03 * s),
                  out=t_sd, pad=1.0)
    sd_l = S.smooth_union(sd_l, t_sd, 0.06 * s)
    np.minimum(shape, sd_l, out=shape)
    for (lx, ly, lr, cw) in lobes:
        cw_ = cw if not flip else (not cw)
        pts, _ = volute(cx + sx * lx * s, cy + ly * s, lr * s * 0.66, lr * s * 0.08, 1.15,
                        200.0 if sx * (1 if cw else -1) > 0 else -20.0, cw=cw_, n=48)
        S.sd_polyline(G, pts, 0.0, out=lines, pad=1.0)
    # the floor line separating the lobes from the floor
    fl = np.array([[cx - 0.55 * s, cy + 0.27 * s], [cx + 0.55 * s, cy + 0.27 * s]], np.float32)
    S.sd_polyline(G, fl, 0.0, out=lines, pad=1.0)
    return shape, lines
