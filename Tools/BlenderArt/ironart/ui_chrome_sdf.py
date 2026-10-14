"""UI chrome family: numpy signed-distance toolkit for relief ornaments (no bpy, no scipy).

Every UI chrome piece is a *relief plate*: a height field plus PBR material layers, sampled on the
render grid (``ss`` x the target size) and turned into a real displaced mesh by
:mod:`ironart.ui_chrome_render`.  Shapes are authored as signed distance fields in **target
pixels** (1 px = 1 mm, image convention: origin top-left, +y down), so a 9-slice moulding is just a
1D profile of the distance to the outer edge, and an ornament is a union of variable-width strokes
(spirals, S-curves, ruyi heads) whose bevelled cross-section comes from the distance itself.

Conventions
    sd < 0 inside a shape, > 0 outside (exact for strokes/circles/boxes; bounded elsewhere)
    ``G`` = :class:`Grid` (pixel-centre sample coordinates of one piece at ``ss`` x)
    heights in mm (= target px), materials as weight arrays 0..1
"""

import math

import numpy as np

BIG = 1.0e4


# =============================================================================================
# sampling grid
# =============================================================================================
class Grid:
    """Pixel-centre sample grid of a ``w`` x ``h`` (target px) piece at ``ss`` samples per px.

    ``xs`` / ``ys`` are 1D axes (target px), ``X`` / ``Y`` the 2D arrays (lazily built).  ``px``
    is the size of one sample in target px (the anti-aliasing width of every mask).
    """

    def __init__(self, w, h, ss, x0=0.0, y0=0.0):
        self.w, self.h, self.ss = float(w), float(h), int(ss)
        self.nx, self.ny = int(round(w * ss)), int(round(h * ss))
        self.px = 1.0 / ss
        self.x0, self.y0 = x0, y0
        self.xs = (x0 + (np.arange(self.nx, dtype=np.float32) + 0.5) * self.px).astype(np.float32)
        self.ys = (y0 + (np.arange(self.ny, dtype=np.float32) + 0.5) * self.px).astype(np.float32)
        self._X = self._Y = None

    @property
    def shape(self):
        return (self.ny, self.nx)

    @property
    def X(self):
        if self._X is None:
            self._X, self._Y = np.meshgrid(self.xs, self.ys)
        return self._X

    @property
    def Y(self):
        if self._Y is None:
            self._X, self._Y = np.meshgrid(self.xs, self.ys)
        return self._Y

    def empty(self, value=BIG):
        return np.full(self.shape, value, np.float32)

    def window(self, x0, y0, x1, y1):
        """Index slices + local coordinate arrays of the sub-rectangle (target px)."""
        i0 = max(0, int(math.floor((x0 - self.x0) * self.ss)))
        i1 = min(self.nx, int(math.ceil((x1 - self.x0) * self.ss)) + 1)
        j0 = max(0, int(math.floor((y0 - self.y0) * self.ss)))
        j1 = min(self.ny, int(math.ceil((y1 - self.y0) * self.ss)) + 1)
        if i1 <= i0 or j1 <= j0:
            return None
        X, Y = np.meshgrid(self.xs[i0:i1], self.ys[j0:j1])
        return (slice(j0, j1), slice(i0, i1)), X, Y


# =============================================================================================
# primitives (sd in target px)
# =============================================================================================
def sd_round_box(G, cx, cy, hw, hh, r=0.0):
    """Rounded box centred at (cx, cy), half sizes (hw, hh), corner radius r."""
    qx = np.abs(G.X - cx) - hw + r
    qy = np.abs(G.Y - cy) - hh + r
    out = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r
    return out.astype(np.float32)


def sd_round_box_uv(U, V, cx, cy, hw, hh, r=0.0):
    """:func:`sd_round_box` on arbitrary coordinate arrays (e.g. corner-folded (u, v))."""
    qx = np.abs(U - cx) - hw + r
    qy = np.abs(V - cy) - hh + r
    out = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r
    return out.astype(np.float32)


def inset_distance(G, w, h, r=0.0, inset=0.0):
    """Distance *into* a w x h rectangle from its outer edge (positive inside): the 9-slice
    profile coordinate.  Iso-lines are mitred (like a picture-frame joint) once d > r."""
    return -sd_round_box(G, w / 2.0, h / 2.0, w / 2.0 - inset, h / 2.0 - inset, r)


def _apply(G, out, bbox, fn, pad):
    x0, y0, x1, y1 = bbox
    win = G.window(x0 - pad, y0 - pad, x1 + pad, y1 + pad)
    if win is None:
        return out
    sl, X, Y = win
    out[sl] = np.minimum(out[sl], fn(X, Y))
    return out


def sd_circle(G, cx, cy, r, out=None, pad=6.0):
    out = G.empty() if out is None else out
    return _apply(G, out, (cx - r, cy - r, cx + r, cy + r),
                  lambda X, Y: np.hypot(X - cx, Y - cy) - r, pad)


def sd_polyline(G, pts, radii, out=None, pad=6.0, closed=False):
    """Union of capsules along ``pts`` (N x 2) with per-point radius (N or scalar): a stroke
    whose width varies along its length (brush taper, spiral scrolls)."""
    pts = np.asarray(pts, np.float32)
    n = len(pts)
    r = np.broadcast_to(np.asarray(radii, np.float32), (n,)).astype(np.float32)
    out = G.empty() if out is None else out
    segs = list(range(n - 1)) + ([n - 1] if closed else [])
    for i in segs:
        a, b = pts[i], pts[(i + 1) % n]
        ra, rb = float(r[i]), float(r[(i + 1) % n])
        rm = max(ra, rb)
        ab = b - a
        L2 = float(ab @ ab) or 1e-12

        def fn(X, Y, a=a, ab=ab, L2=L2, ra=ra, rb=rb):
            t = np.clip(((X - a[0]) * ab[0] + (Y - a[1]) * ab[1]) / L2, 0.0, 1.0)
            dx = X - (a[0] + t * ab[0])
            dy = Y - (a[1] + t * ab[1])
            return np.sqrt(dx * dx + dy * dy) - (ra + t * (rb - ra))
        bb = (min(a[0], b[0]) - rm, min(a[1], b[1]) - rm, max(a[0], b[0]) + rm, max(a[1], b[1]) + rm)
        _apply(G, out, bb, fn, pad)
    return out


def sd_polygon(G, poly, out=None, pad=6.0):
    """Filled polygon (N x 2, any winding, even-odd rule): exact signed distance."""
    P = np.asarray(poly, np.float32)
    out = G.empty() if out is None else out
    x0, y0 = P.min(0)
    x1, y1 = P.max(0)

    def fn(X, Y):
        d = np.full(X.shape, BIG, np.float32)
        inside = np.zeros(X.shape, bool)
        n = len(P)
        for i in range(n):
            a, b = P[i], P[(i + 1) % n]
            ab = b - a
            L2 = float(ab @ ab) or 1e-12
            t = np.clip(((X - a[0]) * ab[0] + (Y - a[1]) * ab[1]) / L2, 0, 1)
            dx = X - (a[0] + t * ab[0])
            dy = Y - (a[1] + t * ab[1])
            d = np.minimum(d, dx * dx + dy * dy)
            cond = (a[1] > Y) != (b[1] > Y)
            xc = a[0] + (Y - a[1]) * (b[0] - a[0]) / ((b[1] - a[1]) if b[1] != a[1] else 1e-12)
            inside ^= cond & (X < xc)
        d = np.sqrt(d)
        return np.where(inside, -d, d)
    return _apply(G, out, (x0, y0, x1, y1), fn, pad)


def union(*fields):
    out = fields[0]
    for f in fields[1:]:
        out = np.minimum(out, f)
    return out


def smooth_union(a, b, k):
    """Polynomial smooth minimum (fillets of radius ~k where two shapes meet)."""
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b + (a - b) * h - k * h * (1 - h)


def subtract(a, b):
    return np.maximum(a, -b)


# =============================================================================================
# curves (ornament vocabulary)
# =============================================================================================
def spiral(cx, cy, r0, r1, turns, a0=0.0, cw=True, n=None):
    """Archimedean spiral from radius r0 (outer start) to r1 (inner end) over ``turns``; a0 in
    degrees (0 = +x, image y down so positive angles turn clockwise on screen when cw)."""
    n = n or max(16, int(64 * turns))
    t = np.linspace(0, 1, n, dtype=np.float32)
    ang = math.radians(a0) + (1 if cw else -1) * t * turns * 2 * math.pi
    rad = r0 + (r1 - r0) * t
    return np.stack([cx + rad * np.cos(ang), cy + rad * np.sin(ang)], 1)


def bezier(p0, p1, p2, p3, n=48):
    t = np.linspace(0, 1, n, dtype=np.float32)[:, None]
    p0, p1, p2, p3 = (np.asarray(p, np.float32) for p in (p0, p1, p2, p3))
    return ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3 * p3


def taper(n, w0, w1, w_mid=None, power=1.0):
    """Per-point radii along a stroke: w0 -> (w_mid) -> w1."""
    t = np.linspace(0, 1, n, dtype=np.float32)
    if w_mid is None:
        return w0 + (w1 - w0) * t ** power
    return np.where(t < 0.5, w0 + (w_mid - w0) * np.sin(t * math.pi) ** power,
                    w1 + (w_mid - w1) * np.sin(t * math.pi) ** power)


def transform(pts, sx=1.0, sy=1.0, rot=0.0, tx=0.0, ty=0.0):
    """Scale (mirror with negative), rotate (deg), translate point arrays."""
    p = np.asarray(pts, np.float32) * np.array([sx, sy], np.float32)
    if rot:
        c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        p = p @ np.array([[c, s], [-s, c]], np.float32)
    return p + np.array([tx, ty], np.float32)


# =============================================================================================
# profiles, masks
# =============================================================================================
def aa_mask(sd, G, soft=1.0):
    """Anti-aliased inside mask of an sd field (one sample wide edge x ``soft``)."""
    return np.clip(0.5 - sd / (G.px * soft), 0.0, 1.0).astype(np.float32)


def band(d, d0, d1, G, soft=1.0):
    """Mask of d0 <= d < d1 (anti-aliased) - a ring of a 9-slice profile."""
    a = np.clip((d - d0) / (G.px * soft) + 0.5, 0, 1)
    b = np.clip((d1 - d) / (G.px * soft) + 0.5, 0, 1)
    return (a * b).astype(np.float32)


class Profile:
    """Cross-section z(d) of a moulding from control points [(d, z), ...] (target px / mm),
    piecewise linear then rounded by a gaussian of ``round_px`` (crisp but never razor-edged).
    Evaluated through a 1D lookup table, so it is cheap on millions of samples."""

    def __init__(self, pts, round_px=0.25, step=0.01):
        pts = sorted(pts)
        self.d0, self.d1 = pts[0][0] - 4, pts[-1][0] + 4
        self.step = step
        ds = np.arange(self.d0, self.d1, step, dtype=np.float64)
        z = np.interp(ds, [p[0] for p in pts], [p[1] for p in pts])
        if round_px > 0:
            r = int(round_px * 3 / step)
            k = np.exp(-0.5 * (np.arange(-r, r + 1) * step / round_px) ** 2)
            k /= k.sum()
            z = np.convolve(np.pad(z, r, mode="edge"), k, mode="valid")
        self.ds, self.z = ds, z

    def __call__(self, d):
        return np.interp(d, self.ds, self.z).astype(np.float32)


def round_relief(sd, width, height, cap=None, power=0.5):
    """Bevelled relief from an sd field: 0 outside, rising over ``width`` px to ``height``.
    ``power`` 0.5 = quarter-circle shoulder (rounded carving), 1 = straight chamfer, 2 = soft
    pillow; ``cap`` limits the plateau height."""
    t = np.clip(-sd / max(width, 1e-6), 0.0, 1.0)
    if power == 0.5:
        z = height * np.sqrt(np.clip(1.0 - (1.0 - t) ** 2, 0, 1))
    elif power == 1:
        z = height * t
    else:
        z = height * (1.0 - (1.0 - t) ** power)
    if cap is not None:
        z = np.minimum(z, cap)
    return z.astype(np.float32)


def groove(sd_line, width, depth):
    """V/U groove along a centre-line distance field (``sd_line`` = distance to the line)."""
    t = np.clip(1.0 - np.abs(sd_line) / max(width, 1e-6), 0, 1)
    return (-depth * np.sin(t * math.pi / 2) ** 1.5).astype(np.float32)


# =============================================================================================
# deterministic noise
# =============================================================================================
def value_noise(shape, cell, seed, aniso=(1.0, 1.0)):
    """Smooth value noise (bicubic-interpolated lattice), ``cell`` samples per lattice cell,
    ``aniso`` stretches cells (x, y).  Returns float32 in ~[0, 1]."""
    from PIL import Image
    rng = np.random.default_rng(seed)
    h, w = shape
    cx, cy = max(cell * aniso[0], 1.0), max(cell * aniso[1], 1.0)
    gw, gh = int(math.ceil(w / cx)) + 3, int(math.ceil(h / cy)) + 3
    lat = rng.random((gh, gw)).astype(np.float32)
    im = Image.fromarray(lat, "F").resize((int(gw * cx), int(gh * cy)), Image.BICUBIC)
    a = np.asarray(im, np.float32)
    oy, ox = int(cy), int(cx)
    return a[oy:oy + h, ox:ox + w]


def fbm(shape, cell, seed, octaves=4, gain=0.5, aniso=(1.0, 1.0)):
    acc = np.zeros(shape, np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        acc += amp * value_noise(shape, cell / (2 ** o), seed + 101 * o, aniso)
        tot += amp
        amp *= gain
    return acc / tot


def blur(a, sigma):
    """Separable gaussian (edge clamped), float32."""
    if sigma <= 0:
        return a.astype(np.float32)
    r = max(1, int(math.ceil(sigma * 3)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2).astype(np.float32)
    k /= k.sum()
    out = a.astype(np.float32)
    for axis in (0, 1):
        pad = [(0, 0)] * out.ndim
        pad[axis] = (r, r)
        p = np.pad(out, pad, mode="edge")
        acc = np.zeros_like(out)
        n = out.shape[axis]
        for i, w in enumerate(k):
            sl = [slice(None)] * out.ndim
            sl[axis] = slice(i, i + n)
            acc += w * p[tuple(sl)]
        out = acc
    return out


def fibres(shape, count, length, width, seed, curl=0.6, lo=0.0, hi=1.0):
    """Random thin curved fibres (paper, silk slubs): returns a 0..1 coverage map.  Fibres are
    drawn anti-aliased with Pillow at 2x then box-downsampled."""
    from PIL import Image, ImageDraw
    rng = np.random.default_rng(seed)
    h, w = shape
    im = Image.new("F", (w * 2, h * 2), 0.0)
    dr = ImageDraw.Draw(im)
    for _ in range(int(count)):
        x, y = rng.random() * w * 2, rng.random() * h * 2
        ang = rng.random() * 2 * math.pi
        L = length * (0.4 + rng.random() * 1.2) * 2
        n = 8
        pts = []
        for i in range(n):
            pts.append((x, y))
            ang += (rng.random() - 0.5) * curl
            x += math.cos(ang) * L / n
            y += math.sin(ang) * L / n
        val = lo + (hi - lo) * rng.random()
        dr.line(pts, fill=float(val), width=max(1, int(round(width * 2))))
    a = np.asarray(im, np.float32)
    return a.reshape(h, 2, w, 2).mean((1, 3))
