"""2D brush engine of gongbi_C (numpy + Pillow; system python3).

* :class:`Proj`   head-local / world points -> work-canvas pixels (+ depth test against the
  Blender depth pass), using the camera and pose matrices exported by the 3D stage.
* :class:`Canvas` the painting at work resolution (``ss`` x the portrait): tapered brush
  strokes (polygons rasterised with Pillow, softened), washes (blurred polygons), and the two
  pigment modes - ``paint`` (opaque mineral colour / ink) and ``glaze`` (transparent dye,
  multiplied).  ``ink_a`` accumulates the ink coverage for the silk finish.

Stroke widths are given in FINAL (1x) pixels; the canvas multiplies by ``ss``.
"""

import math

import numpy as np
from PIL import Image, ImageDraw

import palette as PL

try:
    from scipy.ndimage import gaussian_filter as _gf
except Exception:  # pragma: no cover
    _gf = None


class Patch:
    """A mask living in a sub-rectangle of the canvas: rows y0.., cols x0.. (``a`` float32)."""

    __array_priority__ = 100

    def __init__(self, y0, x0, a, shape):
        self.y0, self.x0 = int(y0), int(x0)
        self.a = a
        self.shape = shape                     # full canvas (h, w)

    @property
    def box(self):
        return (self.y0, self.x0, self.y0 + self.a.shape[0], self.x0 + self.a.shape[1])

    def full(self):
        out = np.zeros(self.shape, np.float32)
        y0, x0, y1, x1 = self.box
        out[y0:y1, x0:x1] = self.a
        return out

    def _with(self, other, op):
        if isinstance(other, Patch):
            if op == "mul":
                y0, x0 = max(self.y0, other.y0), max(self.x0, other.x0)
                y1 = min(self.box[2], other.box[2])
                x1 = min(self.box[3], other.box[3])
                if y1 <= y0 or x1 <= x0:
                    return Patch(0, 0, np.zeros((1, 1), np.float32), self.shape)
                A = self.a[y0 - self.y0:y1 - self.y0, x0 - self.x0:x1 - self.x0]
                Bm = other.a[y0 - other.y0:y1 - other.y0, x0 - other.x0:x1 - other.x0]
                return Patch(y0, x0, A * Bm, self.shape)
            y0, x0 = min(self.y0, other.y0), min(self.x0, other.x0)
            y1 = max(self.box[2], other.box[2])
            x1 = max(self.box[3], other.box[3])
            A = np.zeros((y1 - y0, x1 - x0), np.float32)
            Bm = np.zeros_like(A)
            A[self.y0 - y0:self.box[2] - y0, self.x0 - x0:self.box[3] - x0] = self.a
            Bm[other.y0 - y0:other.box[2] - y0, other.x0 - x0:other.box[3] - x0] = other.a
            r = {"add": A + Bm, "sub": A - Bm, "max": np.maximum(A, Bm)}[op]
            return Patch(y0, x0, r, self.shape)
        if isinstance(other, np.ndarray) and other.ndim == 2 and other.shape == tuple(self.shape):
            y0, x0, y1, x1 = self.box
            o = other[y0:y1, x0:x1]
        else:
            o = other
        r = {"mul": lambda: self.a * o, "add": lambda: self.a + o, "sub": lambda: self.a - o,
             "max": lambda: np.maximum(self.a, o)}[op]()
        return Patch(self.y0, self.x0, np.asarray(r, np.float32), self.shape)

    def __mul__(self, o):
        return self._with(o, "mul")

    __rmul__ = __mul__

    def __add__(self, o):
        return self._with(o, "add")

    __radd__ = __add__

    def __sub__(self, o):
        return self._with(o, "sub")

    def maximum(self, o):
        return self._with(o, "max")

    def clip(self, lo=0.0, hi=1.0):
        return Patch(self.y0, self.x0, np.clip(self.a, lo, hi), self.shape)

    def mean(self):
        return float(self.a.mean())


def blur(a, sigma):
    if isinstance(a, Patch):
        if sigma <= 0.05:
            return a
        m = int(math.ceil(sigma * 3)) + 1
        h, w = a.shape
        y0, x0, y1, x1 = a.box
        Y0, X0, Y1, X1 = max(0, y0 - m), max(0, x0 - m), min(h, y1 + m), min(w, x1 + m)
        A = np.zeros((Y1 - Y0, X1 - X0), np.float32)
        A[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0] = a.a
        return Patch(Y0, X0, blur(A, sigma), a.shape)
    if sigma <= 0.05:
        return a
    if _gf is not None:
        return _gf(a, sigma, mode="nearest").astype(np.float32)
    from ironart.scenes_gongbi import blur as _b
    return _b(a, sigma)


def resample(P, n):
    """Resample a polyline to n points evenly by arc length (any trailing dims kept)."""
    P = np.asarray(P, np.float64)
    if len(P) < 2:
        return np.repeat(P[:1], n, 0)
    d = np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(d)])
    if s[-1] <= 1e-9:
        return np.repeat(P[:1], n, 0)
    t = np.linspace(0, s[-1], n)
    return np.stack([np.interp(t, s, P[:, k]) for k in range(P.shape[1])], -1)


def bezier(pts, n=32):
    """Cubic Bezier chain through control points [P0, C1, C2, P3, C4, C5, P6, ...]."""
    pts = np.asarray(pts, np.float64)
    out = []
    t = np.linspace(0, 1, n)[:, None]
    for k in range(0, len(pts) - 3, 3):
        a, b, c, d = pts[k:k + 4]
        seg = ((1 - t) ** 3) * a + 3 * ((1 - t) ** 2) * t * b + 3 * (1 - t) * t * t * c + t ** 3 * d
        out.append(seg if not out else seg[1:])
    return np.concatenate(out, 0)


def catmull(pts, n=40):
    """Centripetal-ish Catmull-Rom spline through the points, resampled to n."""
    P = np.asarray(pts, np.float64)
    if len(P) < 3:
        return resample(P, n)
    Q = np.concatenate([2 * P[:1] - P[1:2], P, 2 * P[-1:] - P[-2:-1]], 0)
    out = []
    m = max(4, n // (len(P) - 1) + 2)
    t = np.linspace(0, 1, m)[:, None]
    for k in range(1, len(Q) - 2):
        p0, p1, p2, p3 = Q[k - 1], Q[k], Q[k + 1], Q[k + 2]
        seg = 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                     + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)
        out.append(seg if not out else seg[1:])
    return resample(np.concatenate(out, 0), n)


def profile(n, head=0.15, tail=0.35, kind="nail", pressure=0.0, seed=0, lo=0.15):
    """Brush pressure profile along a stroke (0..1): ``nail`` = blunt start (钉头), ``leaf`` =
    swelling middle (兰叶), ``even`` = iron-wire (铁线), ``silk`` = gossamer (游丝)."""
    t = np.linspace(0, 1, n)
    if kind == "even":
        w = np.ones(n)
        w *= np.clip(t / max(head, 1e-3), 0, 1) ** 0.5 * 0.4 + 0.6
        w *= np.clip((1 - t) / max(tail, 1e-3), 0, 1) ** 0.5 * 0.4 + 0.6
    elif kind == "leaf":
        w = np.sin(np.clip(t, 0, 1) * math.pi) ** 0.7
        w = lo + (1 - lo) * w
    elif kind == "silk":
        w = 0.65 + 0.35 * np.sin(t * math.pi)
        w *= np.clip(t / max(head, 1e-3), 0, 1) ** 0.6
        w *= np.clip((1 - t) / max(tail, 1e-3), 0, 1) ** 0.8
        w = lo + (1 - lo) * w
    else:   # nail: a pressed blunt head, long body, tapering tail
        w = np.ones(n)
        hd = np.clip(t / max(head, 1e-3), 0, 1)
        w *= 0.55 + 0.45 * np.sin(hd * math.pi / 2)
        w += 0.25 * np.exp(-((t - head * 0.6) / max(head * 0.5, 1e-3)) ** 2)
        tl = np.clip((1 - t) / max(tail, 1e-3), 0, 1)
        w *= lo + (1 - lo) * np.sin(tl * math.pi / 2) ** 0.8
    if pressure > 0:
        rng = np.random.default_rng(seed)
        k = rng.normal(size=6)
        x = np.linspace(0, 1, 6)
        w *= 1 + pressure * np.interp(t, x, k) * 0.5
    return np.clip(w, 0.0, 2.0)


# =============================================================================================
# projection
# =============================================================================================
class Proj:
    def __init__(self, meta, depth=None):
        self.V = np.array(meta["view"])
        self.scale = meta["ortho"]
        self.W, self.H, self.ss = meta["W"], meta["H"], meta["ss"]
        self.Mh = np.array(meta["M_head"])
        self.Mb = np.array(meta["M_body"])
        self.depth = depth
        self.look = np.array(meta["look"])

    def world(self, Pw):
        Pw = np.asarray(Pw, np.float64)
        c = Pw @ self.V[:3, :3].T + self.V[:3, 3]
        Wr, Hr = self.W * self.ss, self.H * self.ss
        sx = self.scale * self.W / self.H
        return np.stack([(c[..., 0] / sx + 0.5) * Wr, (0.5 - c[..., 1] / self.scale) * Hr,
                         -c[..., 2]], -1)

    def head(self, P):
        P = np.asarray(P, np.float64)
        return self.world(P @ self.Mh[:3, :3].T + self.Mh[:3, 3])

    def body(self, P):
        P = np.asarray(P, np.float64)
        return self.world(P @ self.Mb[:3, :3].T + self.Mb[:3, 3])

    def px_per_unit(self):
        return self.H * self.ss / self.scale

    def visible(self, Q, tol=0.02, soft=0.02):
        """Per-point visibility (0..1) of projected points Q (px, px, depth) vs the depth pass."""
        if self.depth is None:
            return np.ones(len(Q))
        h, w = self.depth.shape
        x = np.clip(np.round(Q[:, 0]).astype(int), 0, w - 1)
        y = np.clip(np.round(Q[:, 1]).astype(int), 0, h - 1)
        d = self.depth[y, x]
        v = np.clip(1 - (Q[:, 2] - d - tol) / soft, 0, 1)
        inside = (Q[:, 0] >= 0) & (Q[:, 0] < w) & (Q[:, 1] >= 0) & (Q[:, 1] < h)
        return np.where(inside, v, 0.0)


# =============================================================================================
# canvas
# =============================================================================================
class Canvas:
    def __init__(self, img, ss):
        self.img = np.ascontiguousarray(img, np.float32)
        self.h, self.w = img.shape[:2]
        self.ss = ss
        self.ink_a = np.zeros((self.h, self.w), np.float32)

    def k(self, px):
        return px * self.ss

    # ----------------------------------------------------------------------- rasterising
    def new_mask(self):
        return np.zeros((self.h, self.w), np.float32)

    def stroke_poly(self, P, widths):
        """Outline polygon of a variable-width stroke (P in work px, widths in work px)."""
        P = np.asarray(P, np.float64)[:, :2]
        n = len(P)
        if n < 2:
            return None
        d = np.gradient(P, axis=0)
        L = np.linalg.norm(d, axis=1, keepdims=True)
        d = d / np.maximum(L, 1e-9)
        nrm = np.stack([-d[:, 1], d[:, 0]], -1)
        hw = np.asarray(widths, np.float64)[:, None] * 0.5
        left = P + nrm * hw
        right = P - nrm * hw
        # round caps
        cap0 = [P[0] - d[0] * hw[0, 0] * 0.6 * math.sin(a) + nrm[0] * hw[0, 0] * math.cos(a)
                for a in np.linspace(math.pi / 2, math.pi * 1.5, 5)[1:-1]]
        cap1 = [P[-1] + d[-1] * hw[-1, 0] * 0.6 * math.sin(a) - nrm[-1] * hw[-1, 0] * math.cos(a)
                for a in np.linspace(math.pi / 2, math.pi * 1.5, 5)[1:-1]]
        poly = np.concatenate([left, np.array(cap1).reshape(-1, 2), right[::-1],
                               np.array(cap0).reshape(-1, 2)], 0)
        return poly

    def raster(self, polys, values=None, mask=None, sub=1, pad=2):
        """Rasterise polygons (work px) into a :class:`Patch` covering their bounds."""
        ps = [np.asarray(p, np.float64)[:, :2] for p in polys if p is not None and len(p) >= 3]
        if not ps:
            return Patch(0, 0, np.zeros((1, 1), np.float32), (self.h, self.w))
        allp = np.concatenate(ps, 0)
        y0 = int(max(0, math.floor(allp[:, 1].min()) - pad))
        x0 = int(max(0, math.floor(allp[:, 0].min()) - pad))
        y1 = int(min(self.h, math.ceil(allp[:, 1].max()) + pad + 1))
        x1 = int(min(self.w, math.ceil(allp[:, 0].max()) + pad + 1))
        if y1 <= y0 or x1 <= x0:
            return Patch(0, 0, np.zeros((1, 1), np.float32), (self.h, self.w))
        im = Image.new("L", ((x1 - x0) * sub, (y1 - y0) * sub), 0)
        dr = ImageDraw.Draw(im)
        k = 0
        for i, p in enumerate(polys):
            if p is None or len(p) < 3:
                continue
            v = 255 if values is None else int(round(np.clip(values[i], 0, 1) * 255))
            if v <= 0:
                continue
            q = (np.asarray(p, np.float64)[:, :2] - [x0, y0]) * sub
            dr.polygon([tuple(xy) for xy in q.tolist()], fill=v)
            k += 1
        a = np.asarray(im, np.float32) / 255.0
        if sub > 1:
            a = a.reshape(y1 - y0, sub, x1 - x0, sub).mean((1, 3))
        return Patch(y0, x0, a, (self.h, self.w))

    def strokes_mask(self, strokes, soft=0.35, sub=1):
        """strokes = [(P work px, widths 1x px, alpha)] -> soft coverage mask."""
        polys, vals = [], []
        for P, wid, a in strokes:
            wid = np.asarray(wid, np.float64) * self.ss
            if np.isscalar(a) or np.ndim(a) == 0:
                polys.append(self.stroke_poly(P, wid))
                vals.append(float(a))
            else:
                # varying alpha: split into short pieces
                a = np.asarray(a, np.float64)
                n = len(P)
                step = 4
                for i0 in range(0, n - 1, step):
                    i1 = min(n, i0 + step + 1)
                    aa = float(a[i0:i1].mean())
                    if aa < 0.02:
                        continue
                    polys.append(self.stroke_poly(P[i0:i1], wid[i0:i1]))
                    vals.append(aa)
        m = self.raster(polys, vals, sub=sub)
        return blur(m, soft * self.ss) if soft > 0 else m

    # ------------------------------------------------------------------------- compositing
    def apply(self, mask, color, mode="paint", alpha=1.0, ink=0.0, clip=None):
        if isinstance(mask, Patch):
            y0, x0, y1, x1 = mask.box
            a = np.clip(mask.a * alpha, 0, 1)
            if clip is not None:
                if isinstance(clip, Patch):
                    a = (Patch(y0, x0, a, mask.shape) * clip).full()[y0:y1, x0:x1]
                elif np.ndim(clip) == 2:
                    a = a * clip[y0:y1, x0:x1]
                else:
                    a = a * clip
        else:
            y0, x0, y1, x1 = 0, 0, self.h, self.w
            a = np.clip(mask * alpha, 0, 1)
            if clip is not None:
                a = a * (clip.full() if isinstance(clip, Patch) else clip)
        if a.size == 0 or float(a.max()) <= 0:
            return
        c = np.array(PL.srgb(color), np.float32)
        img = self.img[y0:y1, x0:x1]
        if mode == "glaze":
            img *= (1 - a[..., None] * (1 - c[None, None, :]))
        elif mode == "screen":
            img[:] = 1 - (1 - img) * (1 - a[..., None] * c[None, None, :])
        else:
            img[:] = img * (1 - a[..., None]) + c[None, None, :] * a[..., None]
        if ink > 0:
            ia = self.ink_a[y0:y1, x0:x1]
            np.maximum(ia, a * ink, out=ia)

    def stroke(self, P, widths, color="ink", alpha=1.0, mode="paint", soft=0.35, ink=1.0,
               clip=None, sub=1):
        m = self.strokes_mask([(P, widths, alpha if np.ndim(alpha) == 0 else alpha)], soft, sub)
        self.apply(m, color, mode, 1.0, ink, clip)

    def fill(self, poly, color, alpha=1.0, soft=0.0, mode="paint", clip=None, ink=0.0):
        m = self.raster([np.asarray(poly)[:, :2]])
        if soft > 0:
            m = blur(m, soft * self.ss)
        self.apply(m, color, mode, alpha, ink, clip)

    def radial(self, c, r, color, alpha, mode="glaze", power=1.6, clip=None, aspect=1.0,
               angle=0.0):
        """Soft radial wash centred at c (work px) with radius r (work px)."""
        x0, y0 = c[0], c[1]
        R = int(r * max(1, aspect) + 3)
        ya, yb = max(0, int(y0 - R)), min(self.h, int(y0 + R + 1))
        xa, xb = max(0, int(x0 - R)), min(self.w, int(x0 + R + 1))
        if ya >= yb or xa >= xb:
            return
        yy, xx = np.mgrid[ya:yb, xa:xb].astype(np.float32)
        dx, dy = xx - x0, yy - y0
        ca, sa = math.cos(angle), math.sin(angle)
        u = (dx * ca + dy * sa) / aspect
        v = -dx * sa + dy * ca
        d = np.sqrt(u * u + v * v) / r
        a = np.clip(1 - d, 0, 1) ** power
        self.apply(Patch(ya, xa, a.astype(np.float32), (self.h, self.w)), color, mode, alpha,
                   0.0, clip)
