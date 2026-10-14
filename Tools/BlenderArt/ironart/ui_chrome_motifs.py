"""UI chrome family: Chinese ornament vocabulary as signed distance fields (numpy, no bpy).

Coordinates are target px of a *local* grid (``ui_chrome_sdf.Grid``) - corner pieces are built
once for the top-left corner and stamped into the other corners by mirroring (exact, because the
pixel-centre lattice is symmetric).  All functions return float32 sd arrays (< 0 inside).

Vocabulary
    volute        tapered spiral stroke (the curl of a cloud scroll)
    cloud_scroll  xiangyun: a large volute + a counter-curl + a tail, mirrored about an axis
    ruyi          three-lobed lingzhi/ruyi head with a pointed waist
    fret          square meander (hui wen) stroke
    corner_fold   (u, v) folded about the diagonal (symmetric corner pieces)
"""

import math

import numpy as np

from . import ui_chrome_sdf as S


def volute(cx, cy, r0, turns, a0_deg, cw=True, r1=None, w0=0.9, w1=0.35, n=None):
    """Points + radii of a curl starting on radius r0 at angle a0 and winding inwards to r1."""
    r1 = r0 * 0.18 if r1 is None else r1
    pts = S.spiral(cx, cy, r0, r1, turns, a0_deg, cw, n)
    rad = S.taper(len(pts), w0, w1, power=0.8)
    return pts, rad


def strokes_sd(G, strokes, pad=4.0):
    """Union of tapered strokes [(pts, radii), ...] on grid G."""
    out = G.empty()
    for pts, rad in strokes:
        S.sd_polyline(G, pts, rad, out=out, pad=pad)
    return out


def arc(cx, cy, r, a0, a1, n=32):
    t = np.radians(np.linspace(a0, a1, n))
    return np.stack([cx + r * np.cos(t), cy + r * np.sin(t)], 1).astype(np.float32)


def cloud_scroll(scale=1.0, w=0.75, turns=1.15):
    """A symmetric xiangyun cloud in its own frame: axis along +y (pointing down the image),
    origin at the top centre, overall about 16 x 10 units at scale 1.  Returns strokes."""
    s = scale
    strokes = []
    for side in (-1, 1):
        # big volute curling inwards, its outer arc forming the cloud's shoulder
        cx, cy = side * 4.2 * s, 4.6 * s
        a0 = 180.0 if side < 0 else 0.0
        pts, rad = volute(cx, cy, 3.6 * s, turns, a0, cw=(side > 0), w0=w * s, w1=0.32 * w * s)
        strokes.append((pts, rad))
        # outer tail sweeping out and down from the shoulder
        tail = S.bezier((side * 7.8 * s, 4.6 * s), (side * 8.6 * s, 7.6 * s),
                        (side * 6.4 * s, 9.6 * s), (side * 3.4 * s, 9.4 * s), n=28)
        strokes.append((tail, S.taper(len(tail), w * s, 0.25 * w * s, power=1.2)))
    # small central counter-curl on top (the crest)
    pts, rad = volute(0.0, 1.5 * s, 1.5 * s, 0.85, 90.0, cw=True, w0=0.8 * w * s, w1=0.3 * w * s)
    strokes.append((pts, rad))
    return strokes


def _local(G, cx, cy, size, rot):
    c, s_ = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    X, Y = G.X - cx, G.Y - cy
    return (c * X + s_ * Y) / size, (-s_ * X + c * Y) / size


def _lines_sd(u, v, polylines):
    """Distance (local units) from (u, v) to a set of polylines."""
    out = np.full(u.shape, 9.0, np.float32)
    Gl = _UVGrid(u, v)
    for pts in polylines:
        S.sd_polyline(Gl, pts, 0.0, out=out, pad=0.3)
    return out


def _curl(cx, cy, r, a0, turns=1.25, cw=True, inner=0.16, n=80):
    """Spiral polyline from radius r (angle a0 deg) inwards to inner*r."""
    return S.spiral(cx, cy, r, r * inner, turns, a0, cw, n)


def ruyi(G, cx, cy, size, rot=0.0):
    """Ruyi (lingzhi) head: a trefoil heart - big top lobe, two side lobes - narrowing to a point
    (the point is along +v; ``rot`` degrees turns it).  Returns (shape_sd, engraving_sd): the
    engraving is an inner outline plus a curl in each side lobe (distance to the lines)."""
    u, v = _local(G, cx, cy, size, rot)
    top = np.hypot(u, v + 0.30) - 0.40
    left = np.hypot(u + 0.47, v + 0.02) - 0.29
    right = np.hypot(u - 0.47, v + 0.02) - 0.29
    lobes = S.smooth_union(S.smooth_union(top, left, 0.10), right, 0.10)
    tip = np.maximum(np.abs(u) - 0.55 * np.clip(0.80 - v, 0, 1) ** 1.25, v - 0.80)
    tip = np.maximum(tip, -v - 0.1)
    shape = S.smooth_union(lobes, tip, 0.14)
    eng = np.abs(shape + 0.10)
    curls = [_curl(sx * 0.47, -0.02, 0.17, 90.0 + sx * 0.0, 1.1, cw=(sx < 0)) for sx in (-1, 1)]
    curls.append(_curl(0.0, -0.32, 0.20, 90.0, 1.2, cw=True))
    eng = np.minimum(eng, _lines_sd(u, v, curls))
    return (shape * size).astype(np.float32), (eng * size).astype(np.float32)


def cloud(G, cx, cy, size, rot=0.0, mirror=False, lobes=None, tail=True):
    """Xiangyun cloud: a cluster of round lobes (smooth union) with a curl engraved in each, on a
    flat floor, with a tapering tail.  Frame: +u along the tail; ``mirror`` flips v.
    Returns (shape_sd, engraving_sd) in target px."""
    u, v = _local(G, cx, cy, size, rot)
    if mirror:
        v = -v
    lobes = lobes or [(-0.42, -0.05, 0.36, 1), (0.05, -0.28, 0.30, 1), (0.40, -0.06, 0.24, -1)]
    shape = None
    curls = []
    for (lx, ly, lr, d) in lobes:
        c = np.hypot(u - lx, v - ly) - lr
        shape = c if shape is None else S.smooth_union(shape, c, 0.09)
        curls.append(_curl(lx, ly, lr * 0.72, 90.0 if d > 0 else 90.0, 1.3, cw=(d > 0)))
    base = S.sd_round_box_uv(u, v, 0.0, 0.16, 0.62, 0.12, 0.12)
    shape = S.smooth_union(shape, base, 0.12)
    if tail:
        pts = S.bezier((0.55, 0.18), (0.85, 0.30), (1.05, 0.10), (1.25, -0.12), n=24)
        rad = S.taper(len(pts), 0.11, 0.025, power=1.0)
        tail_sd = np.full(u.shape, 9.0, np.float32)
        S.sd_polyline(_UVGrid(u, v), pts, rad, out=tail_sd, pad=0.5)
        shape = S.smooth_union(shape, tail_sd, 0.08)
    eng = _lines_sd(u, v, curls)
    return (shape * size).astype(np.float32), (eng * size).astype(np.float32)


def dome(sd, width, height):
    """Smooth domed (repousse) relief: C-infinity, no plateau crease."""
    return (height * np.tanh(np.clip(-sd, 0, None) * 1.6 / max(width, 1e-6))).astype(np.float32)


class _UVGrid:
    """Adapter so sd_polyline can run on arbitrary (non-lattice) coordinate arrays."""

    def __init__(self, U, V):
        self.U, self.V = U, V

    def window(self, x0, y0, x1, y1):
        m = (self.U >= x0) & (self.U <= x1) & (self.V >= y0) & (self.V <= y1)
        if not m.any():
            return None
        ys, xs = np.nonzero(m)
        sl = (slice(ys.min(), ys.max() + 1), slice(xs.min(), xs.max() + 1))
        return sl, self.U[sl], self.V[sl]


def corner_fold(G):
    """(u, v) = (max, min) of the local coordinates: shapes defined for v <= u are mirrored
    about the diagonal."""
    return np.maximum(G.X, G.Y), np.minimum(G.X, G.Y)


def stamp_corners(full, local, fn=np.maximum, flip_ok=True):
    """Paste a top-left ``local`` array into the four corners of ``full`` (mirrored) with
    ``fn`` (np.maximum for heights/masks, or a custom combine)."""
    h, w = local.shape[:2]
    H, W = full.shape[:2]
    views = [
        (slice(0, h), slice(0, w), local),
        (slice(0, h), slice(W - w, W), local[:, ::-1]),
        (slice(H - h, H), slice(0, w), local[::-1, :]),
        (slice(H - h, H), slice(W - w, W), local[::-1, ::-1]),
    ]
    for sy, sx, arr in views:
        full[sy, sx] = fn(full[sy, sx], arr)
    return full


def hillshade(z, px, light=(135.0, 45.0)):
    """Quick numpy shading of a height field (look-dev previews without Blender)."""
    gy, gx = np.gradient(z, px)
    nx, ny, nz = -gx, gy, np.ones_like(z)
    n = np.sqrt(nx * nx + ny * ny + nz * nz)
    a, e = math.radians(light[0]), math.radians(light[1])
    lx, ly, lz = math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e)
    return np.clip((nx * lx + ny * ly + nz * lz) / n, 0, 1)
