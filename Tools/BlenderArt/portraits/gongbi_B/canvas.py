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
    if kind == "reed":            # 折芦描: pressed (顿笔) entry, long firm body, sharp tip
        a, b = taper or (0.05, 0.55)
        head = 1.0 + 0.35 * np.exp(-((t - a * 0.5) / (a + 1e-6)) ** 2)
        body = np.where(t < a, 0.75 + 0.25 * t / a, 1.0)
        tail = np.clip((1 - t) / b, 0, 1) ** 0.7
        return np.clip(0.05 + 0.95 * body * np.minimum(1.0, tail) * head / 1.35 * 1.2, 0, 1.3)
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
    __slots__ = ("V", "Al", "col", "mode", "tris", "ngon", "z", "C", "grain")

    def __init__(self, V, Al, col, mode, tris=None, ngon=False, C=None, grain=None):
        self.V = V
        self.Al = Al
        self.col = col
        self.mode = mode
        self.tris = tris
        self.ngon = ngon
        self.C = C          # optional per-vertex linear colours (N, 3)
        self.z = 0.0
        # pigment granulation / silk show-through amount (shader noise), per primitive
        self.grain = (0.45 if mode == "paint" else 1.0) if grain is None else grain


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
               widths=None, pool=0.0, bleed=0.0, dry=0.0, grain=None, density=0.10):
        """Tapered brush line through dense polyline ``P`` (use g.catmull first).

        width        full brush width in target px
        prof         pressure profile (see :func:`profile`)
        noise        relative pressure wobble (plus a finer bristle jitter)
        alpha_along  optional callable t -> opacity multiplier
        widths       optional explicit width array (overrides prof, resampled along)
        pool         ink pooling: denser ink where the brush lands (and lifts, on blunt ends)
        bleed        faint ink halo soaking into the silk around the line (glaze)
        dry          飞白 dry-brush tail: the last part of the stroke breaks into bristle marks
        density      uneven ink density along the stroke (opacity variation)
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
            wa = wa * (1 + noise * g.smooth_noise(n, sd, scale=2.5 + Ltot / 40.0)
                       + 0.45 * noise * g.smooth_noise(n, sd + 3, scale=4.0 + Ltot / 6.0))
        wa = np.maximum(wa, 0.02)
        aa = np.ones(n)
        if alpha_along is not None:
            aa = aa * np.asarray(alpha_along(t), float)
        if density:
            aa = aa * (1 - density * (0.5 + 0.5 * g.smooth_noise(n, sd + 11, scale=1.5 + Ltot / 50.0)))
        if bleed:
            # ink soaking into the silk: a wide faint halo, strongest where the brush was wettest
            self._ribbon(P, wa * (1.0 + 1.2 * bleed) + 0.6, aa * alpha * 0.07 * bleed
                         * (1 - 0.6 * t), color, "glaze", caps, grain=1.0)
        if dry and n >= 8 and Ltot > 6 * width:
            rng = np.random.default_rng(sd + 29)
            t0 = 1.0 - 0.55 * dry
            k0 = int(np.searchsorted(t, t0))
            k1 = min(n, int(np.searchsorted(t, t0 + 0.10)) + 1)
            fade = np.clip(1 - (t - t0) / 0.10, 0, 1)
            prim = self._ribbon(P[:k1], wa[:k1], (aa * fade * alpha)[:k1], color, mode, caps,
                                grain=grain, cap_end=False)
            m = 4 + int(round(3 * dry))
            N = g.normals(P)
            for j in range(m):
                off = (j + 0.5) / m - 0.5 + rng.normal(0, 0.06)
                frac = 0.85 / m * rng.uniform(0.7, 1.4)
                tend = t0 + (1 - t0) * rng.uniform(0.25, 1.0)
                ks = max(0, k0 - 2)
                ke = min(n, int(np.searchsorted(t, tend)) + 1)
                if ke - ks < 3:
                    continue
                tt = (t[ks:ke] - t[ks]) / max(t[ke - 1] - t[ks], 1e-6)
                Pj = P[ks:ke] + N[ks:ke] * (off * wa[ks:ke])[:, None]
                wj = wa[ks:ke] * frac * (1 - 0.7 * tt ** 1.5)
                aj = (aa * alpha)[ks:ke] * rng.uniform(0.55, 0.95) * (1 - 0.55 * tt) \
                    * g.smoothstep(0.0, 0.25, tt + 0.1)
                self._ribbon(Pj, wj, aj, color, mode, False, grain=grain)
        else:
            prim = self._ribbon(P, wa, aa * alpha, color, mode, caps, grain=grain)
        if pool:
            # where the brush lands the ink pools: denser start (and end when the end is blunt)
            k = max(3, int(n * 0.07))
            self._ribbon(P[:k], wa[:k] * 0.96, alpha * pool * 0.45 * (1 - np.linspace(0, 1, k)) ** 0.7,
                         color, mode, False, grain=grain)
            if wa[-1] > 0.6 * wa.max() and not dry:
                self._ribbon(P[-k:], wa[-k:] * 0.96, alpha * pool * 0.40 * np.linspace(0, 1, k) ** 0.7,
                             color, mode, False, grain=grain)
        return prim

    def _ribbon(self, P, wa, al_pts, color, mode, caps, grain=None, cap_start=True, cap_end=True):
        n = len(P)
        if n < 2:
            return None
        al_pts = np.broadcast_to(np.asarray(al_pts, float), (n,))
        N = g.normals(P)
        L = P + N * (wa / 2)[:, None]
        R = P - N * (wa / 2)[:, None]
        V = np.empty((2 * n, 2))
        V[0::2] = L
        V[1::2] = R
        al = np.repeat(al_pts, 2)
        i = 2 * np.arange(n - 1)
        tris = list(np.concatenate([np.stack([i, i + 1, i + 2], 1),
                                    np.stack([i + 1, i + 3, i + 2], 1)]))
        if caps:
            extra_v = []
            extra_a = []
            base = len(V)
            TT = g.tangents(P)
            for end in (0, n - 1):
                if (end == 0 and not cap_start) or (end == n - 1 and not cap_end):
                    continue
                r = wa[end] / 2
                if r < 0.15:
                    continue
                T = TT[end] * (-1 if end == 0 else 1)
                c0 = P[end]
                ia, ib = (2 * end, 2 * end + 1)
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
        return self._push(Prim(V, al, pal.lin(color), mode, np.array(tris, np.int32), grain=grain))

    def brush(self, P, width, color="ink", style="orchid", alpha=0.95, **kw):
        """Costume line work with brush character (lines of robes, armour, headgear).

        style  'orchid' 兰叶描 (swelling, fine ends), 'reed' 折芦描 (pressed entry, sharp tip),
               'nail' 钉头鼠尾, 'iron' 铁线描 (even, firm)."""
        d = dict(orchid=dict(prof="orchid", taper=(0.35, 0.65), pool=0.6, bleed=0.8, dry=0.45,
                             noise=0.16),
                 reed=dict(prof="reed", pool=0.8, bleed=0.8, dry=0.55, noise=0.14),
                 nail=dict(prof="nail", pool=0.7, bleed=0.8, dry=0.6, noise=0.14),
                 iron=dict(prof="iron", pool=0.15, bleed=0.6, dry=0.0, noise=0.10))[style]
        d.update(kw)
        return self.stroke(P, width, color, alpha, **d)

    def line(self, pts, width, color="ink", n=10, closed=False, **kw):
        """Stroke through sparse ``pts`` (Catmull-Rom)."""
        return self.stroke(g.catmull(pts, n=n, closed=closed), width, color, **kw)

    def fill(self, poly, color, alpha=1.0, mode="paint", grain=None, rim=0.0):
        """Flat colour region.  ``rim`` lays a faint darker pool of pigment just inside the edge
        (water-borne colour collects at the boundary of a flat wash)."""
        poly = g.A(poly)
        if len(poly) < 3:
            return None
        if g.area(poly) < 0:
            poly = poly[::-1]
        p = self._push(Prim(poly, np.full(len(poly), float(alpha)), pal.lin(color), mode,
                            ngon=True, grain=grain))
        if rim:
            dark = pal.hexs(pal.mix(color, "ink", 0.55))
            # inside of a positive-area polygon is the +1 normal side (see geom2d.normals)
            self.edge(poly, 2.2, dark, 0.22 * rim, side=1, rows=3, end_fade=0, power=1.2,
                      closed=True, irregular=0.5)
        return p

    def band(self, Acurve, Bcurve, color, alpha=1.0, mode="glaze", cols=None, rows=6,
             colors=None, alpha_xy=None, grain=None):
        """Region between two curves (same direction).  ``alpha`` scalar or f(s, t) where s runs
        along the curves (0..1) and t across from A (0) to B (1).  ``colors`` optional
        f(s, t) -> (N, 3) sRGB.  ``alpha_xy`` optional f(V) multiplier on vertex positions."""
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
        if alpha_xy is not None:
            al = al * np.asarray(alpha_xy(V), float)
        rr, cc = np.meshgrid(np.arange(rows), np.arange(cols - 1), indexing="ij")
        a = (rr * cols + cc).reshape(-1)
        tris = np.concatenate([np.stack([a, a + 1, a + cols + 1], 1),
                               np.stack([a, a + cols + 1, a + cols], 1)])
        C = None
        if colors is not None:
            C = pal.lin_arr(colors(S, T)).reshape(-1, 3)
        return self._push(Prim(V, al, pal.lin(color), mode, np.array(tris, np.int32), C=C,
                               grain=grain))

    def radial(self, boundary, center, color, alpha, mode="glaze", rings=10, n=None,
               colors=None, alpha_xy=None, grain=None):
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
        return self._push(Prim(V, al, pal.lin(color), mode, np.array(tris, np.int32), C=C,
                               grain=grain))

    def blob(self, c, rx, ry, color, alpha, rot=0.0, mode="glaze", power=1.6, rings=10,
             irregular=0.18, grain=None):
        """Soft elliptical wash, opacity falls smoothly to 0 at the (slightly blooming,
        uneven) boundary."""
        sd = self.next_seed()
        B = g.ellipse(c, rx, ry, rot, n=40)
        if irregular and mode == "glaze":
            rng = np.random.default_rng(sd)
            th = np.linspace(0, 2 * math.pi, 40, endpoint=False)
            k = 1 + irregular * sum(rng.uniform(0.3, 1.0) / j * np.sin(j * th + rng.uniform(0, 6.3))
                                    for j in (2, 3, 5)) / 1.2
            B = np.asarray(c, float) + (B - np.asarray(c, float)) * k[:, None]
        mott = None
        if irregular and mode == "glaze":
            sc = max(4.0, 0.8 * min(rx, ry))
            mott = lambda V: np.clip(1 + 0.9 * irregular * g.vnoise(V, sc, sd + 1), 0.3, 1.6)
        return self.radial(B, c, color,
                           lambda r, u: alpha * (1 - g.smoothstep(0, 1, r)) ** power * 1.0
                           + 0 * u, mode, rings, alpha_xy=mott, grain=grain)

    def edge(self, P, width, color, alpha, side=1, mode="glaze", rows=6, end_fade=0.2,
             power=1.5, closed=False, width_along=None, irregular=0.25, grain=None):
        """One-sided graded wash (分染) along polyline P: opacity ``alpha`` at the line falling
        to 0 at distance ``width`` on ``side`` (+1 = left normal in screen space).  ``irregular``
        makes the wash edge bloom unevenly and its pigment lie a little unevenly, as a hand-laid
        wash does."""
        P = g.A(P)
        if closed:
            P = np.vstack([P, P[:1]])
        P = g.resample(P, step=1.2)
        n = len(P)
        if n < 2:
            return None
        sd = self.next_seed()
        w = np.full(n, float(width))
        if width_along is not None:
            w = w * np.asarray(width_along(np.linspace(0, 1, n)), float)
        if irregular:
            L = g.length(P)
            w = w * (1 + irregular * g.smooth_noise(n, sd, octaves=3, scale=1.0 + L / max(width * 3, 6)))
        Q = g.offset(P, side * w, closed=False)

        def al(S, T):
            a = alpha * (1 - g.smoothstep(0, 1, T)) ** power
            if end_fade and not closed:
                a = a * g.smoothstep(0, end_fade, S) * g.smoothstep(0, end_fade, 1 - S)
            return a
        mott = None
        if irregular and mode == "glaze":
            sc = max(4.0, float(width) * 0.9)
            mott = lambda V: np.clip(1 + 0.8 * irregular * g.vnoise(V, sc, sd + 5), 0.3, 1.7)
        return self.band(P, Q, color, al, mode, cols=n, rows=rows, alpha_xy=mott, grain=grain)

    def wash(self, P, width, color, alpha, side=1, passes=3, **kw):
        """Layered 分染: several thin glazes of decreasing reach, each with its own uneven edge,
        building the tone up the way a painter lays wash over dried wash."""
        reach = [1.0, 0.62, 0.34][:passes]
        share = [0.42, 0.33, 0.25][:passes]
        tot = sum(share)
        for r_, a_ in zip(reach, share):
            self.edge(P, width * r_, color, alpha * a_ / tot * 1.25, side=side, **kw)

    def dot(self, c, r, color, alpha=1.0, mode="paint", n=16, grain=None):
        return self.fill(g.ellipse(c, r, r, n=n), color, alpha, mode, grain=grain)
