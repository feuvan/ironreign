"""Armour and cloaks on the torso frame: lamellar cuirass (札甲) with a round neckline,
lamellar pauldrons (披膊), a chest mirror (护心镜), and a cloak (披风) behind the shoulders."""

import math

import numpy as np

import geom2d as g
import palette as pal
from headgear import lamellar, _inward


class TShell:
    """Ellipsoid in torso space (projected with the torso yaw)."""

    def __init__(self, T, c, r):
        self.T = T
        self.c = np.asarray(c, float)
        self.r = np.asarray(r, float)

    def xyz(self, lon, lat, dr=0.0):
        lon = np.asarray(lon, float)
        lat = np.asarray(lat, float)
        rx, ry, rz = self.r + dr
        return (self.c[0] + rx * np.cos(lat) * np.sin(lon), self.c[1] - ry * np.sin(lat),
                self.c[2] + rz * np.cos(lat) * np.cos(lon))

    def proj(self, x, y, z):
        return self.T.proj(x, y, z)

    def P(self, lon, lat, dr=0.0):
        return self.proj(*self.xyz(lon, lat, dr))

    def facing(self, lon, lat):
        x, y, z = self.xyz(lon, lat)
        nx = (x - self.c[0]) / self.r[0] ** 2
        nz = (z - self.c[2]) / self.r[2] ** 2
        return -nx * math.sin(self.T.yaw) + nz * math.cos(self.T.yaw)

    def outline(self, n=72, keep=None):
        lon, lat = np.meshgrid(np.linspace(-math.pi, math.pi, 90), np.linspace(-1.5, 1.5, 46))
        x, y, z = self.xyz(lon, lat)
        if keep is not None:
            m = keep(lon, lat)
            x, y, z = x[m], y[m], z[m]
        Pp = self.proj(x.ravel(), y.ravel(), z.ravel())
        c = Pp.mean(0)
        ang = np.arctan2(Pp[:, 1] - c[1], Pp[:, 0] - c[0])
        rad = np.linalg.norm(Pp - c, axis=1)
        bins = np.linspace(-math.pi, math.pi, n + 1)
        out = []
        for i in range(n):
            m = (ang >= bins[i]) & (ang < bins[i + 1])
            if m.any():
                out.append(Pp[np.argmax(np.where(m, rad, -1))])
        return np.array(out)


def cloak(cv, T, color="carmine", y_top=1.02, spread=0.16, y_bot=2.3, lining=None):
    """披风 behind the shoulders: wider than the body, standing collar behind the neck."""
    s = T.s
    ys = np.linspace(y_top + 0.12, y_bot, 30)
    right = T.P(np.array([T.sil_u(y, +1) for y in ys]), ys, spread)
    left = T.P(np.array([T.sil_u(y, -1) for y in ys]), ys, spread)
    # collar behind the neck
    back = T.P(np.linspace(1.6, 2.4, 12) * 1, np.full(12, y_top), 0.05)
    nl = T.P(-1.3, y_top + 0.04, 0.06)
    nr = T.P(1.3, y_top + 0.04, 0.06)
    top = g.catmull([left[0], nl, T.P(2.0, y_top - 0.02, 0.0), nr, right[0]], 8)
    poly = np.vstack([top, right[1:], left[::-1][:-1]])
    dark = pal.hexs(pal.mix(color, "ink", 0.5))
    cv.fill(poly, color, 1.0, "paint")
    cv.edge(right, s * 0.12, dark, 0.5, side=_inward(right, poly), rows=5)
    cv.edge(left, s * 0.12, dark, 0.5, side=_inward(left, poly), rows=5)
    cv.edge(top, s * 0.10, dark, 0.45, side=_inward(top, poly), rows=5)
    # a few long folds
    for side in (-1, 1):
        for k in range(2):
            y0 = 1.35 + 0.15 * k
            u0 = T.sil_u(y0, side)
            p0 = T.P(u0, y0, spread * 0.6)
            p1 = T.P(u0, y_bot, spread * (0.9 + 0.2 * k))
            cv.stroke(np.array([p0, (p0 + p1) / 2 + [side * s * 0.02, 0], p1]), s * 0.006, "ink",
                      0.6, prof="orchid")
    cv.stroke(np.vstack([top, right[1:]]), s * 0.006, "ink", 0.9, prof="iron")
    cv.stroke(np.vstack([top[::-1], left[1:]]), s * 0.006, "ink", 0.9, prof="iron")
    return poly


def cuirass(cv, T, color="iron", trim="gold", lace="cinnabar", neck_y=1.10, neck_depth=0.13,
            neck_u=0.50, y_bot=2.3, rows=10, cols=16, rng=None, edge="leather"):
    """Lamellar body armour with a round neckline."""
    s = T.s
    rng = rng or np.random.default_rng(3)
    # top boundary: near silhouette shoulder -> neckline -> far silhouette shoulder
    ys_sh = 1.30
    un = T.sil_u(ys_sh, -1)
    uf = T.sil_u(ys_sh, +1)
    us = np.linspace(-neck_u, neck_u, 24)
    neck = np.stack([us, neck_y + neck_depth * np.cos(us / neck_u * math.pi / 2) ** 1.5], 1)
    left_sh = np.stack([np.linspace(un, -neck_u, 10), np.linspace(ys_sh, neck_y, 10)], 1)
    right_sh = np.stack([np.linspace(neck_u, uf, 10), np.linspace(neck_y, ys_sh, 10)], 1)
    top_uv = np.vstack([left_sh, neck[1:-1], right_sh])
    top = T.Puv(top_uv, 0.02)
    # bottom: across the body at y_bot, from near to far silhouette
    ub = np.linspace(T.sil_u(y_bot, -1), T.sil_u(y_bot, +1), 40)
    bot = T.P(ub, np.full_like(ub, y_bot), 0.02)
    ys = np.linspace(ys_sh, y_bot, 20)
    lside = T.P(np.array([T.sil_u(y, -1) for y in ys]), ys, 0.02)
    rside = T.P(np.array([T.sil_u(y, +1) for y in ys]), ys, 0.02)
    poly = np.vstack([top, rside[1:], bot[::-1][1:], lside[::-1][1:-1]])
    cv.fill(poly, color, 1.0, "paint")
    # rows: interpolate from the top boundary to the bottom
    n = 60
    Tt = g.resample(top, n)
    Bb = g.resample(bot, n)
    lamellar(cv, Tt, Bb, rows, cols, color, s, lace=lace, rng=rng)
    # body modelling: dark towards the silhouettes
    cv.edge(rside, s * 0.18, "ink", 0.40, side=_inward(rside, poly), rows=6)
    cv.edge(lside, s * 0.14, "ink", 0.30, side=_inward(lside, poly), rows=6)
    # neckline: leather/brocade edging with gold trim
    nk = T.Puv(neck, 0.025)
    nk_o = T.Puv(np.stack([neck[:, 0] * 1.18, neck[:, 1] + 0.055], 1), 0.025)
    cv.band(nk, nk_o, edge, 1.0, mode="paint", rows=2)
    cv.band(nk, nk_o, trim, lambda S, Tt: 0.9 * (Tt > 0.62), mode="paint", rows=4)
    cv.stroke(nk, s * 0.005, "ink", 0.95, prof="iron")
    cv.stroke(nk_o, s * 0.005, "ink", 0.95, prof="iron")
    return dict(poly=poly, neck=nk, top=top)


def chest_mirror(cv, T, u=0.0, y=1.62, r=0.13, metal="iron", trim="gold"):
    """护心镜: round polished plate with a gold rim, bright reflection."""
    s = T.s
    ph = np.linspace(0, 2 * math.pi, 48, endpoint=False)
    # circle on the chest surface: u offset ~ x / a
    a = float(T.a(y))
    pts = np.stack([u + (r * np.cos(ph)) / a / (math.pi / 2), y + r * np.sin(ph) * 0.95], 1)
    C = T.Puv(pts, 0.045)
    c = T.P(u, y, 0.045)
    cv.fill(C, trim, 1.0, "paint")
    Ci = c + (C - c) * 0.80
    cv.fill(Ci, "iron_l", 1.0, "paint")
    cv.radial(Ci, c, "ink", lambda rr, uu: 0.55 * g.smoothstep(0.2, 1.0, rr) + 0 * uu, rings=6)
    cv.blob(c + (C[30] - c) * 0.35, s * 0.035, s * 0.022, "white", 0.85, rot=-0.6, mode="paint")
    cv.edge(C, s * 0.012, "gold_d", 0.7, side=_inward(C, C), rows=3, closed=True)
    cv.stroke(np.vstack([C, C[:1]]), s * 0.005, "ink", 0.95, prof="iron", caps=False)
    cv.stroke(np.vstack([Ci, Ci[:1]]), s * 0.004, "ink", 0.8, prof="iron", caps=False)
    # rivets on the rim
    for k in range(0, 48, 6):
        p = c + (C[k] - c) * 0.9
        cv.dot(p, s * 0.006, "gold_d", 1.0)
    return C


def _tproj(T, x, y, z):
    return T.proj(x, y, z)


def pauldron(cv, T, side, color="iron", trim="gold", lace="cinnabar", rows=4, size=1.0,
             rng=None, lining="cinnabar"):
    """披膊: a lamellar cape draped over the shoulder and upper arm (Tang/Song style), its top
    following the shoulder slope, flaring out at the hem, gilded and brocade-edged."""
    s = T.s
    rng = rng or np.random.default_rng(5)
    n = 30
    t = np.linspace(0, 1, n)
    u_out_top = T.sil_u(1.30, side)
    u_out_bot = T.sil_u(1.75, side)
    # top edge: from the neck side over the shoulder to just past the silhouette
    tu = side * (0.40 + (abs(u_out_top) + 0.10 - 0.40) * t)
    ty = 1.10 + 0.20 * g.smoothstep(0.0, 1.0, t) ** 1.2
    tdr = 0.03 + 0.04 * t
    # hem: from the chest side of the shoulder down and out to the arm
    bu = side * (0.50 + (abs(u_out_bot) + 0.15 - 0.50) * t)
    by = 1.33 + 0.45 * t ** 1.3
    bdr = 0.05 + 0.10 * t
    top = np.vstack([T.P(a, b, c) for a, b, c in zip(tu, ty, tdr)])
    bot = np.vstack([T.P(a, b, c) for a, b, c in zip(bu, by, bdr)])
    poly = np.vstack([top, bot[::-1]])
    cv.fill(poly, color, 1.0, "paint")
    # rows: lower rows first, upper rows overlap them
    for k in range(rows - 1, -1, -1):
        t0, t1 = k / rows, (k + 1) / rows + 0.03
        A_ = top + (bot - top) * t0
        B_ = top + (bot - top) * min(t1, 1.0)
        lamellar(cv, A_, B_, 1, 7 + 2 * k, color, s, lace=lace, rng=rng, row_light=0.28)
        cv.stroke(B_, s * 0.0045, "ink", 0.9, prof="iron")
    # brocade hem: red band with gold edge and dots
    hem_a = top + (bot - top) * 0.90
    cv.band(hem_a, bot, lining, 1.0, mode="paint", rows=1)
    cv.band(hem_a, bot, trim, lambda S, Tt: 1.0 * (Tt > 0.7), mode="paint", rows=5)
    for k in range(int(g.length(bot) / (s * 0.04))):
        u = (k + 0.5) / max(1, int(g.length(bot) / (s * 0.04)))
        c = g.at(hem_a, u) * 0.6 + g.at(bot, u) * 0.4
        cv.dot(c, s * 0.006, "gold_l", 0.9)
    # modelling: light on the shoulder top, dark under the arm side
    cv.band(top, top + (bot - top) * 0.5, "white", lambda S, Tt: 0.22 * (1 - Tt) ** 2
            * np.sin(np.pi * S) ** 0.5, mode="paint", rows=4)
    cv.edge(bot, s * 0.10, "ink", 0.25, side=_inward(bot, poly), rows=4)
    cv.stroke(np.vstack([poly, poly[:1]]), s * 0.0055, "ink", 0.95, prof="iron", caps=False)
    return poly


def mingguang(cv, T, u=0.34, y=1.56, r=0.125, strap="cinnabar", trim="gold", metal="iron"):
    """明光铠 chest: two round mirrors either side of a vertical strap, shoulder straps."""
    s = T.s
    # straps: neckline centre down between the mirrors, and over the shoulders
    for (ua, ya), (ub, yb) in (((0.0, 1.22), (0.0, 2.2)), ((-0.42, 1.12), (-u, y - r)),
                               ((0.42, 1.12), (u, y - r))):
        n = 20
        us = np.linspace(ua, ub, n)
        ys_ = np.linspace(ya, yb, n)
        w = 0.025
        A_ = T.Puv(np.stack([us - w, ys_], 1), 0.035)
        B_ = T.Puv(np.stack([us + w, ys_], 1), 0.035)
        cv.band(A_, B_, strap, 1.0, mode="paint", rows=2)
        cv.band(A_, B_, "ink", lambda S, Tt: 0.35 * np.abs(Tt - 0.5) * 2, rows=4)
        cv.stroke(A_, s * 0.004, "ink", 0.9, prof="iron")
        cv.stroke(B_, s * 0.004, "ink", 0.9, prof="iron")
    for uu in (-u, u):
        chest_mirror(cv, T, u=uu, y=y, r=r, metal=metal, trim=trim)
