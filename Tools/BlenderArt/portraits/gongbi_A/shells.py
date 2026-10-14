"""Parametric shells fitted to the MakeHuman form by ray casting.

* Torso shells: cylindrical (angle a, height z) around the neck axis.  a = 0 is the front (-Y),
  a = +90 deg the wearer's left (+X).  Rays are cast from outside toward the axis, so the shell
  wraps torso, shoulders and upper arms together like a robe with wide sleeves.
* Head shells: spherical (azimuth p, polar t from the top) around the skull centre for hair,
  caps and helmets.
Both give natural UVs (u = angle / 2pi, v = height) for painted patterns, and an exact top
boundary (each column starts at a given cut height), so collars and hairlines are crisp curves
instead of stair-stepped grid edges.
"""

import math

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import geo


def gauss1d(x, s, axis, wrap):
    if s <= 0:
        return x
    r = int(3 * s) + 1
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / s) ** 2)
    k /= k.sum()
    x = np.moveaxis(x, axis, -1)
    if wrap:
        xp = np.concatenate([x[..., -r:], x, x[..., :r]], -1)
    else:
        xp = np.concatenate([np.repeat(x[..., :1], r, -1), x, np.repeat(x[..., -1:], r, -1)], -1)
    out = np.zeros_like(x)
    for i, kv in enumerate(k):
        out += kv * xp[..., i:i + x.shape[-1]]
    return np.moveaxis(out, -1, axis)


class Torso:
    """Radius field of the body below the jaw: R[i, j] at angle a_i, height z_j."""

    def __init__(self, H, na=144, z_top=None, z_bot=None, dz=0.004):
        V = np.asarray(H.verts)
        lm = H.lm
        self.H = H
        ez = H.eye_z
        self.z_top = z_top if z_top is not None else ez - 0.10
        self.z_bot = z_bot if z_bot is not None else ez - 0.36
        chin_z = lm["menton"][2]
        # body BVH: everything below the jaw line (plus the back of the neck)
        polys = []
        for f in H.faces:
            p = V[list(f)]
            if p[:, 2].max() < chin_z - 0.004 or (p[:, 1].min() > lm["menton"][1] + 0.05 and
                                                 p[:, 2].max() < ez - 0.04):
                polys.append(list(f))
        self.bvh = BVHTree.FromPolygons(V.tolist(), polys)
        # neck axis
        m = np.abs(V[:, 2] - (ez - 0.14)) < 0.006
        nk = V[m & (np.abs(V[:, 0]) < 0.07)]
        self.yc = float(0.5 * (nk[:, 1].min() + nk[:, 1].max())) if len(nk) else -0.03
        self.a = np.linspace(0, 2 * math.pi, na, endpoint=False)
        self.z = np.arange(self.z_bot, self.z_top + 1e-9, dz)
        R = np.zeros((na, len(self.z)))
        for i, a in enumerate(self.a):
            d = np.array([math.sin(a), -math.cos(a), 0.0])
            for j, z in enumerate(self.z):
                o = np.array([0.0, self.yc, z]) + d * 0.6
                loc, n, idx, dist = self.bvh.ray_cast(Vector(o), Vector(-d), 0.6)
                R[i, j] = 0.6 - dist if loc is not None else np.nan
        # fill misses upward/downward
        for i in range(na):
            col = R[i]
            ok = ~np.isnan(col)
            if ok.any():
                R[i] = np.interp(self.z, self.z[ok], col[ok])
            else:
                R[i] = 0.05
        self.R0 = R

    def radius(self, smooth_a=2.0, smooth_z=2.0, z_sh=None, drop=0.22):
        """Smoothed radius field.  Below the shoulder line the arms are let *down*: the radius
        may grow by at most ``drop`` per metre of depth, so sleeves hang instead of following
        the MakeHuman A-pose outward."""
        R = self.R0.copy()
        if z_sh is not None:
            j0 = int(np.argmin(np.abs(self.z - z_sh)))
            cap = R[:, j0][:, None] + drop * np.clip(z_sh - self.z, 0, None)[None, :]
            R = np.minimum(R, cap)
        Rs = gauss1d(gauss1d(R, smooth_a, 0, True), smooth_z, 1, False)
        # never inside the body (bust, shoulder blades): smoothing must not let it poke out
        return np.maximum(Rs, R + 0.002)

    def sample(self, R, a, z):
        """Bilinear R at arbitrary (a, z) arrays."""
        na = len(self.a)
        fa = (np.asarray(a) % (2 * math.pi)) / (2 * math.pi) * na
        fz = (np.asarray(z) - self.z[0]) / (self.z[1] - self.z[0])
        fz = np.clip(fz, 0, len(self.z) - 1.001)
        i0 = np.floor(fa).astype(int) % na
        i1 = (i0 + 1) % na
        j0 = np.floor(fz).astype(int)
        ta = fa - np.floor(fa)
        tz = fz - j0
        return ((R[i0, j0] * (1 - tz) + R[i0, j0 + 1] * tz) * (1 - ta)
                + (R[i1, j0] * (1 - tz) + R[i1, j0 + 1] * tz) * ta)

    def arc_u(self, R, a, z):
        """Arc length from the front (a = 0) along the horizontal section at height z."""
        a = np.asarray(a, np.float64)
        aw = (a + math.pi) % (2 * math.pi) - math.pi        # -pi..pi
        n = 48
        out = np.zeros_like(aw)
        for k in range(len(aw)):
            t = np.linspace(0.0, aw[k], n)
            zz = np.full(n, z[k] if np.ndim(z) else z)
            r = self.sample(R, t, zz)
            out[k] = np.trapz(r, t)
        return out

    def point(self, R, a, z, extra=0.0):
        r = self.sample(R, a, z) + extra
        a = np.asarray(a)
        return np.stack([r * np.sin(a), self.yc - r * np.cos(a), np.asarray(z) + 0 * r], -1)

    def shell(self, name, col, mat, R, top_fn, bot_z=None, nu=144, nv=36, a0=0.0,
              a1=2 * math.pi, offset_fn=None, parent=None, closed=None):
        """Mesh between the cut curve z = top_fn(a) and bot_z.  offset_fn(a, z, v) adds radius.
        UV: u = a / 2pi (unwrapped), v = z (metres)."""
        closed = (a1 - a0) >= 2 * math.pi - 1e-6 if closed is None else closed
        aa = np.linspace(a0, a1, nu, endpoint=not closed)
        tops = np.array([top_fn(a) for a in aa])
        if callable(bot_z):
            bot = np.array([bot_z(a) for a in aa])
        else:
            bot = np.full(nu, self.z_bot if bot_z is None else bot_z)
        V, UV = [], []
        i0 = int(np.argmin(np.abs(((aa + math.pi) % (2 * math.pi)) - math.pi)))
        for j in range(nv):
            v = j / (nv - 1)
            # rows denser near the top (collars) : v^1.6
            zz = tops + (bot - tops) * v ** 1.5
            ex = offset_fn(aa, zz, v) if offset_fn is not None else 0.0
            P = self.point(R, aa, zz, ex)
            V.append(P)
            # u = arc length along the *horizontal* section through each point (metres, 0 at
            # the front): motifs stay undistorted even where rows slant along a V collar
            UV.append(np.stack([self.arc_u(R, aa, zz), zz], 1))
        Va = np.array(V)                       # (nv, nu, 3)
        UVa = np.array(UV)
        # v = arc length up each column from the (level) bottom row: no stretch on slopes
        dv = np.linalg.norm(np.diff(Va, axis=0), axis=2)          # (nv-1, nu)
        acc = np.vstack([np.cumsum(dv[::-1], axis=0)[::-1], np.zeros((1, nu))])
        UVa[..., 1] = bot[None, :] + acc
        V = Va.reshape(-1, 3)
        UV = UVa.reshape(-1, 2)
        F = geo.grid_faces(nu, nv, wrap_u=closed)
        F = [f[::-1] for f in F]
        ob = geo.mesh_obj(name, V, F, col, mat, smooth=True, uvs=UV, parent=parent)
        ob["nu"], ob["nv"] = nu, nv
        return ob


class Skull:
    """Radius field of the head around the skull centre: R[i, k] at azimuth p_i (0 = front,
    +90 deg = wearer's left), polar t_k (0 = straight up)."""

    def __init__(self, H, npz=96, nt=60, t_max=150.0):
        lm = H.lm
        ez = H.eye_z
        V = np.asarray(H.verts)
        self.c = np.array([0.0, lm["nose_tip"][1] + 0.098, ez + 0.012])
        polys = []
        for f in H.faces:
            p = V[list(f)]
            if p[:, 2].min() > lm["menton"][2] - 0.03:
                polys.append(list(f))
        self.bvh = BVHTree.FromPolygons(V.tolist(), polys)
        self.p = np.linspace(0, 2 * math.pi, npz, endpoint=False)
        self.t = np.radians(np.linspace(0, t_max, nt))
        R = np.zeros((npz, nt))
        for i, p in enumerate(self.p):
            for k, t in enumerate(self.t):
                d = self.dir(p, t)
                o = self.c + d * 0.4
                loc, n, idx, dist = self.bvh.ray_cast(Vector(o), Vector(-d), 0.4)
                R[i, k] = 0.4 - dist if loc is not None else np.nan
        for i in range(npz):
            ok = ~np.isnan(R[i])
            R[i] = np.interp(self.t, self.t[ok], R[i][ok]) if ok.any() else 0.09
        self.R0 = R

    @staticmethod
    def dir(p, t):
        return np.stack([np.sin(t) * np.sin(p), -np.sin(t) * np.cos(p), np.cos(t) + 0 * p], -1)

    def radius(self, sp=1.5, st=1.5):
        return gauss1d(gauss1d(self.R0, sp, 0, True), st, 1, False)

    def sample(self, R, p, t):
        n = len(self.p)
        fp = (np.asarray(p) % (2 * math.pi)) / (2 * math.pi) * n
        ft = (np.asarray(t) - self.t[0]) / (self.t[1] - self.t[0])
        ft = np.clip(ft, 0, len(self.t) - 1.001)
        i0 = np.floor(fp).astype(int) % n
        i1 = (i0 + 1) % n
        k0 = np.floor(ft).astype(int)
        tp = fp - np.floor(fp)
        tt = ft - k0
        return ((R[i0, k0] * (1 - tt) + R[i0, k0 + 1] * tt) * (1 - tp)
                + (R[i1, k0] * (1 - tt) + R[i1, k0 + 1] * tt) * tp)

    def point(self, R, p, t, extra=0.0):
        r = self.sample(R, p, t) + extra
        return self.c + self.dir(np.asarray(p), np.asarray(t)) * np.asarray(r)[..., None]

    def shell(self, name, col, mat, R, bot_fn, nu=96, nv=30, offset_fn=None, parent=None,
              t_top=0.0, cap=True):
        """Dome from the top (t_top) down to the cut t = bot_fn(p).  offset_fn(p, t, v)."""
        pp = np.linspace(0, 2 * math.pi, nu, endpoint=False)
        bots = np.array([bot_fn(p) for p in pp])
        V, UV = [], []
        rows = []
        t0 = max(t_top, 1e-3)
        for j in range(nv):
            v = j / (nv - 1)
            tt = t0 + (bots - t0) * v
            ex = offset_fn(pp, tt, v) if offset_fn is not None else 0.0
            V.append(self.point(R, pp, tt, ex))
            UV.append(np.stack([pp / (2 * math.pi), tt], 1))
        V = np.vstack(V)
        UV = np.vstack(UV)
        F = geo.grid_faces(nu, nv, wrap_u=True)
        if cap and t_top <= 1e-3:
            top = self.point(R, np.array([0.0]), np.array([0.0]),
                             offset_fn(np.array([0.0]), np.array([0.0]), 0.0)
                             if offset_fn is not None else 0.0)
            ci = len(V)
            V = np.vstack([V, top])
            UV = np.vstack([UV, [[0.0, 0.0]]])
            F += [(ci, i, (i + 1) % nu) for i in range(nu)]
        F = [f[::-1] if len(f) == 4 else f for f in F]
        ob = geo.mesh_obj(name, V, F, col, mat, smooth=True, uvs=UV, parent=parent)
        return ob
