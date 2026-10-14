"""Display list of painted primitives (pure numpy, no bpy).

A gongbi painting is built up as an ordered stack of thin layers on silk.  Every call on
:class:`Canvas` appends one primitive *above* everything drawn before it.  Each primitive is a
small 2D mesh with per-vertex opacity and one of two blend modes, which the Blender backend
(:mod:`backend`) renders flat in an orthographic Cycles camera:

``paint``  opaque mineral colour / ink:      out = a * colour + (1 - a) * below   (Emission over)
``glaze``  transparent wash (water colour):  out = lerp(1, colour, a) * below     (Transparent filter)

Primitives
* :meth:`stroke`  tapered calligraphic brush line (ribbon) with a pressure profile
* :meth:`fill`    flat colour region (any simple polygon)
* :meth:`band`    gradient region between two curves (eye white, lips, folds, plates ...)
* :meth:`radial`  gradient region from a centre to a closed boundary (face 晕染, blobs ...)
* :meth:`blob`    soft elliptical wash (rouge on cheeks)
* :meth:`edge`    one-sided graded wash along a line (分染: deepest at the line, fading away)

Coordinates are *target* pixels of the final 384x480 portrait (x right, y down); the backend
renders them at any supersample factor.
"""

import math

import numpy as np

import geom2d as g
import palette as pal

DZ = 0.002            # depth step between successive primitives (world units = target px)

# ------------------------------------------------------------------------------------------
# brush pressure profiles (描法).  t in [0, 1] along the stroke -> width multiplier.


def _ramp(t, a):
    if a <= 0:
        return np.ones_like(t)
    return np.clip(t / a, 0, 1) ** 0.6


def profile(kind, t, taper=None):
    t = np.asarray(t, float)
    if kind == "iron":            # 铁线描: even, firm, short tapers
        a, b = taper or (0.08, 0.10)
        return 0.25 + 0.75 * np.minimum(_ramp(t, a), _ramp(1 - t, b))
    if kind == "silk":            # 高古游丝描: gossamer, even, long soft tapers
        a, b = taper or (0.18, 0.22)
        return 0.15 + 0.85 * np.minimum(_ramp(t, a), _ramp(1 - t, b))
    if kind == "orchid":          # 兰叶描: swelling in the middle, fine at both ends
        a, b = taper or (0.35, 0.65)
        pk = a / (a + b)
        u = np.where(t < pk, t / pk, (1 - t) / (1 - pk))
        return 0.12 + 0.88 * np.sin(0.5 * math.pi * np.clip(u, 0, 1)) ** 0.8
    if kind == "nail":            # 钉头鼠尾: blunt heavy head, long rat-tail
        a, b = taper or (0.06, 0.9)
        head = np.exp(-((t - a * 0.6) / (a + 1e-6)) ** 2) * 0.25
        tail = np.clip(1 - (t - a) / b, 0, 1) ** 0.9
        return np.clip(0.06 + 0.94 * np.where(t < a, 0.8 + 0.2 * t / a, tail) + head, 0, 1.3)
    if kind == "tail":            # full at start, tapering away (beard strand, hair tip)
        a, b = taper or (0.05, 0.75)
        return np.minimum(_ramp(t, a), np.clip((1 - t) / b, 0, 1) ** 0.8) * 0.97 + 0.03
    if kind == "hair":            # fine strand, tapered both ends, heavier near root
        a, b = taper or (0.12, 0.6)
        return (np.minimum(_ramp(t, a), np.clip((1 - t) / b, 0, 1) ** 0.9) * 0.95 + 0.05)
    if kind == "flat":
        return np.ones_like(t)
    raise KeyError(kind)


class Prim:
    __slots__ = ("V", "Al", "col", "mode", "tris", "ngon", "z", "C")

    def __init__(self, V, Al, col, mode, tris=None, ngon=False, C=None):
        self.V = V
        self.Al = Al
        self.col = col
        self.mode = mode
        self.tris = tris
        self.ngon = ngon
        self.C = C          # optional per-vertex linear colours (N, 3)
        self.z = 0.0


class Canvas:
    def __init__(self, W=384, H=480, seed=0):
        self.W, self.H = W, H
        self.prims = []
        self.rng = np.random.default_rng(seed)
        self._seed = seed * 1000 + 17

    # -- bookkeeping ---------------------------------------------------------------------
    def _push(self, p):
        p.z = len(self.prims) * DZ
        self.prims.append(p)
        return p

    def next_seed(self):
        self._seed += 1
        return self._seed

    def stats(self):
        nv = sum(len(p.V) for p in self.prims)
        return "%d primitives, %d vertices" % (len(self.prims), nv)

    # -- primitives ----------------------------------------------------------------------
    def stroke(self, P, width, color="ink", alpha=1.0, mode="paint", prof="iron", taper=None,
               noise=0.10, step=0.3, caps=True, alpha_along=None, wobble=0.0, seed=None,
               widths=None):
        """Tapered brush line through dense polyline ``P`` (use g.catmull first).

        width        full brush width in target px
        prof         pressure profile (see :func:`profile`)
        noise        relative pressure wobble
        alpha_along  optional callable t -> opacity multiplier (dry-brush fade)
        widths       optional explicit width array (overrides prof, resampled along)
        """
        P = g.A(P)
        if len(P) < 2 or g.length(P) < 1e-3:
            return None
        Ltot = g.length(P)
        P = g.resample(P, step=max(step, min(0.9, Ltot / 60.0)))
        n = len(P)
        if n < 3:
            P = g.resample(P, 3)
            n = 3
        t = np.linspace(0, 1, n)
        sd = seed if seed is not None else self.next_seed()
        if wobble:
            Nn = g.normals(P)
            P = P + Nn * (wobble * g.smooth_noise(n, sd + 7, scale=3.0))[:, None]
        if widths is not None:
            wa = np.interp(t, np.linspace(0, 1, len(widths)), np.asarray(widths, float))
        else:
            wa = width * profile(prof, t, taper)
        if noise:
            wa = wa * (1 + noise * g.smooth_noise(n, sd, scale=2.5 + g.length(P) / 40.0))
        wa = np.maximum(wa, 0.02)
        N = g.normals(P)
        L = P + N * (wa / 2)[:, None]
        R = P - N * (wa / 2)[:, None]
        V = np.empty((2 * n, 2))
        V[0::2] = L
        V[1::2] = R
        al = np.full(2 * n, float(alpha))
        if alpha_along is not None:
            aa = np.asarray(alpha_along(t), float)
            al[0::2] *= aa
            al[1::2] *= aa
        i = 2 * np.arange(n - 1)
        tris = list(np.concatenate([np.stack([i, i + 1, i + 2], 1),
                                    np.stack([i + 1, i + 3, i + 2], 1)]))
        if caps:
            extra_v = []
            extra_a = []
            base = len(V)
            for end in (0, n - 1):
                r = wa[end] / 2
                if r < 0.15:
                    continue
                T = g.tangents(P)[end] * (-1 if end == 0 else 1)
                c0 = P[end]
                ia, ib = (2 * end, 2 * end + 1)
                # semicircle from L side to R side bulging along T
                k = 6
                ang0 = math.atan2(N[end][1], N[end][0])
                sgn = 1 if (N[end][0] * T[1] - N[end][1] * T[0]) > 0 else -1
                ci = base + len(extra_v)
                extra_v.append(c0)
                extra_a.append(al[ia])
                prev = ia
                for j in range(1, k):
                    a_ = ang0 + sgn * math.pi * j / k
                    extra_v.append(c0 + r * np.array([math.cos(a_), math.sin(a_)]))
                    extra_a.append(al[ia])
                    cur = base + len(extra_v) - 1
                    tris.append((ci, prev, cur))
                    prev = cur
                tris.append((ci, prev, ib))
            if extra_v:
                V = np.vstack([V, np.array(extra_v)])
                al = np.concatenate([al, np.array(extra_a)])
        return self._push(Prim(V, al, pal.lin(color), mode, np.array(tris, np.int32)))

    def line(self, pts, width, color="ink", n=10, closed=False, **kw):
        """Stroke through sparse ``pts`` (Catmull-Rom)."""
        return self.stroke(g.catmull(pts, n=n, closed=closed), width, color, **kw)

    def fill(self, poly, color, alpha=1.0, mode="paint"):
        poly = g.A(poly)
        if len(poly) < 3:
            return None
        if g.area(poly) < 0:
            poly = poly[::-1]
        return self._push(Prim(poly, np.full(len(poly), float(alpha)), pal.lin(color), mode,
                               ngon=True))

    def band(self, Acurve, Bcurve, color, alpha=1.0, mode="glaze", cols=None, rows=6,
             colors=None):
        """Region between two curves (same direction).  ``alpha`` scalar or f(s, t) where s runs
        along the curves (0..1) and t across from A (0) to B (1).  ``colors`` optional
        f(s, t) -> (N, 3) sRGB."""
        Acurve = g.A(Acurve)
        Bcurve = g.A(Bcurve)
        if cols is None:
            cols = int(max(8, min(160, max(g.length(Acurve), g.length(Bcurve)) / 1.5)))
        Ar = g.resample(Acurve, cols)
        Br = g.resample(Bcurve, cols)
        s = np.linspace(0, 1, cols)
        t = np.linspace(0, 1, rows + 1)
        S, T = np.meshgrid(s, t)                 # (rows+1, cols)
        V = Ar[None, :, :] * (1 - T[..., None]) + Br[None, :, :] * T[..., None]
        V = V.reshape(-1, 2)
        if callable(alpha):
            al = np.asarray(alpha(S, T), float).reshape(-1)
        else:
            al = np.full(len(V), float(alpha))
        rr, cc = np.meshgrid(np.arange(rows), np.arange(cols - 1), indexing="ij")
        a = (rr * cols + cc).reshape(-1)
        tris = np.concatenate([np.stack([a, a + 1, a + cols + 1], 1),
                               np.stack([a, a + cols + 1, a + cols], 1)])
        C = None
        if colors is not None:
            C = pal.lin_arr(colors(S, T)).reshape(-1, 3)
        return self._push(Prim(V, al, pal.lin(color), mode, np.array(tris, np.int32), C=C))

    def radial(self, boundary, center, color, alpha, mode="glaze", rings=10, n=None,
               colors=None, alpha_xy=None):
        """Region from ``center`` out to closed ``boundary`` with opacity ``alpha(r, u)``
        (r: 0 centre .. 1 boundary, u: 0..1 around).  Boundary must be star-shaped."""
        B = g.A(boundary)
        if n:
            B = g.resample(B, n, closed=True)
        K = len(B)
        c = np.asarray(center, float)
        r = np.linspace(0, 1, rings + 1)[1:]
        u = np.arange(K) / K
        R, U = np.meshgrid(r, u, indexing="ij")          # (rings, K)
        V = c[None, None, :] + R[..., None] * (B[None, :, :] - c[None, None, :])
        V = np.vstack([c[None], V.reshape(-1, 2)])
        if callable(alpha):
            al = np.concatenate([[float(np.mean(alpha(np.zeros(1), np.zeros(1))))],
                                 np.asarray(alpha(R, U), float).reshape(-1)])
        else:
            al = np.full(len(V), float(alpha))
        if alpha_xy is not None:
            al = al * np.asarray(alpha_xy(V), float)
        k = np.arange(K)
        k2 = (k + 1) % K
        tl = [np.stack([np.zeros(K, int), 1 + k, 1 + k2], 1)]
        for j in range(rings - 1):
            a = 1 + j * K + k
            b = 1 + j * K + k2
            d = a + K
            e = b + K
            tl.append(np.stack([a, d, e], 1))
            tl.append(np.stack([a, e, b], 1))
        tris = np.concatenate(tl)
        C = None
        if colors is not None:
            cc = pal.lin_arr(colors(R, U)).reshape(-1, 3)
            c0 = pal.lin_arr(colors(np.zeros(1), np.zeros(1))).reshape(-1, 3)[:1]
            C = np.vstack([c0, cc])
        return self._push(Prim(V, al, pal.lin(color), mode, np.array(tris, np.int32), C=C))

    def blob(self, c, rx, ry, color, alpha, rot=0.0, mode="glaze", power=1.6, rings=10):
        """Soft elliptical wash, opacity falls smoothly to 0 at the ellipse."""
        B = g.ellipse(c, rx, ry, rot, n=40)
        return self.radial(B, c, color,
                           lambda r, u: alpha * (1 - g.smoothstep(0, 1, r)) ** power * 1.0
                           + 0 * u, mode, rings)

    def edge(self, P, width, color, alpha, side=1, mode="glaze", rows=6, end_fade=0.2,
             power=1.5, closed=False, width_along=None):
        """One-sided graded wash (分染) along polyline P: opacity ``alpha`` at the line falling
        to 0 at distance ``width`` on ``side`` (+1 = left normal in screen space)."""
        P = g.A(P)
        if closed:
            P = np.vstack([P, P[:1]])
        P = g.resample(P, step=1.2)
        n = len(P)
        w = np.full(n, float(width))
        if width_along is not None:
            w = w * np.asarray(width_along(np.linspace(0, 1, n)), float)
        Q = g.offset(P, side * w, closed=False)

        def al(S, T):
            a = alpha * (1 - g.smoothstep(0, 1, T)) ** power
            if end_fade and not closed:
                a = a * g.smoothstep(0, end_fade, S) * g.smoothstep(0, end_fade, 1 - S)
            return a
        return self.band(P, Q, color, al, mode, cols=n, rows=rows)

    def dot(self, c, r, color, alpha=1.0, mode="paint", n=16):
        return self.fill(g.ellipse(c, r, r, n=n), color, alpha, mode)
