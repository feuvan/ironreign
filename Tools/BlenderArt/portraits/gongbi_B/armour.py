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


# armour palettes (plate, plate light, pauldron, pauldron light, lacing, trim, scarf, style)
ARMOUR = {
    "black_lacquer": dict(plate="#2b2827", light="#6a625c", pauldron="#8e2a22", p_light="#c0604a",
                          lace="#b3301f", trim="gold", scarf="#b3301f", style="shanwen",
                          p_style="scale"),
    "red_lacquer": dict(plate="#7a2a22", light="#b0503e", pauldron="#2e2b2a", p_light="#6a625c",
                        lace="#c9a040", trim="gold", scarf="#2a2520", style="lacquer",
                        p_style="lamellar"),
    "bronze": dict(plate="#7d6034", light="#c09858", pauldron="#4d5e70", p_light="#7d90a4",
                   lace="#2f7457", trim="gold_l", scarf="#2f7457", style="scale",
                   p_style="lamellar"),
    "azure_iron": dict(plate="#4a5a6c", light="#7f93a8", pauldron="#8c3a2a", p_light="#c0684e",
                       lace="#9a3a28", trim="gold", scarf="#b3301f", style="lamellar",
                       p_style="scale"),
    "green_iron": dict(plate="#4b574e", light="#7e8f82", pauldron="#7a5a36", p_light="#b08a58",
                       lace="#8e2a22", trim="gold", scarf="#8e2a22", style="scale",
                       p_style="lamellar"),
    "steel": dict(plate="#44505c", light="#b9c3c9", pauldron="#8e2a22", p_light="#c0604a",
                  lace="#b3301f", trim="gold", scarf="#b3301f", style="shanwen",
                  p_style="scale", glint="gold_l"),
    "leather": dict(plate="#6d4630", light="#a07454", pauldron="#5a3a26", p_light="#8a6448",
                    lace="#c9a040", trim="#8a6326", scarf="#2c3e55", style="lacquer",
                    p_style="lacquer"),
}


def _xp(T, x0, y, dr):
    """chest coordinates (x0 across, y down; head units) -> canvas."""
    x0 = np.atleast_1d(np.asarray(x0, float))
    y = np.atleast_1d(np.asarray(y, float))
    x0, y = np.broadcast_arrays(x0, y)
    return T.P(T.u_of_x(x0, y), y, dr).reshape(-1, 2)


def _clip_runs(P, poly):
    m = g.poly_contains(poly, P)
    out, cur = [], []
    for p, k in zip(P, m):
        if k:
            cur.append(p)
        elif cur:
            if len(cur) > 1:
                out.append(np.array(cur))
            cur = []
    if len(cur) > 1:
        out.append(np.array(cur))
    return out


def cuirass(cv, T, palette="azure_iron", style=None, neck_y=1.10, neck_depth=0.13,
            neck_u=0.50, y_bot=2.3, rows=None, cols=None, rng=None, color=None, trim=None,
            lace=None, collar_plate=True, scale=1.0, **_):
    """Body armour with a round neckline.  Plate styles: 'shanwen' 山文甲 (interlocking Y plates),
    'scale' 鱼鳞甲, 'lacquer' 皮甲 (lacquered bands with gilt rivets), 'lamellar' 札甲."""
    s = T.s
    A = dict(ARMOUR[palette])
    if color:
        A["plate"] = color
    if trim:
        A["trim"] = trim
    if lace:
        A["lace"] = lace
    style = style or A["style"]
    rng = rng or np.random.default_rng(3)
    ys_sh = 1.30
    un = T.sil_u(ys_sh, -1)
    uf = T.sil_u(ys_sh, +1)
    us = np.linspace(-neck_u, neck_u, 24)
    neck = np.stack([us, neck_y + neck_depth * np.cos(us / neck_u * math.pi / 2) ** 1.5], 1)
    left_sh = np.stack([np.linspace(un, -neck_u, 10), np.linspace(ys_sh, neck_y, 10)], 1)
    right_sh = np.stack([np.linspace(neck_u, uf, 10), np.linspace(neck_y, ys_sh, 10)], 1)
    top_uv = np.vstack([left_sh, neck[1:-1], right_sh])
    top = T.Puv(top_uv, 0.02)
    ub = np.linspace(T.sil_u(y_bot, -1), T.sil_u(y_bot, +1), 40)
    bot = T.P(ub, np.full_like(ub, y_bot), 0.02)
    ys = np.linspace(ys_sh, y_bot, 20)
    lside = T.P(np.array([T.sil_u(y, -1) for y in ys]), ys, 0.02)
    rside = T.P(np.array([T.sil_u(y, +1) for y in ys]), ys, 0.02)
    poly = np.vstack([top, rside[1:], bot[::-1][1:], lside[::-1][1:-1]])
    cv.fill(poly, A["plate"], 1.0, "paint", grain=1.0)
    plates(cv, T, poly, A, style, y0=neck_y - 0.02, y1=y_bot, rng=rng, scale=scale,
           rows=rows, cols=cols, top=top, bot=bot)
    # body modelling: dark towards the silhouettes, a broad lit plane on the near chest
    cv.wash(rside, s * 0.20, "ink", 0.45, side=_inward(rside, poly), rows=6, passes=2)
    cv.wash(lside, s * 0.15, "ink", 0.32, side=_inward(lside, poly), rows=6, passes=2)
    for side_, line_ in ((1, np.vstack([top[-10:], rside[1:]])), (-1, np.vstack([top[:10][::-1], lside[1:]]))):
        cv.brush(line_, s * 0.011, "ink", style="orchid", alpha=0.92, dry=0.4)
    nk = T.Puv(neck, 0.025)
    if collar_plate:
        gorget(cv, T, neck, A)
    else:
        nk_o = T.Puv(np.stack([neck[:, 0] * 1.18, neck[:, 1] + 0.055], 1), 0.025)
        cv.band(nk, nk_o, "leather", 1.0, mode="paint", rows=2)
        cv.band(nk, nk_o, A["trim"], lambda S, Tt: 0.9 * (Tt > 0.62), mode="paint", rows=4)
        cv.brush(nk, s * 0.006, "ink", style="iron")
        cv.brush(nk_o, s * 0.006, "ink", style="iron")
    return dict(poly=poly, neck=nk, top=top, palette=A)


def gorget(cv, T, neck, A):
    """护项: a gilt crescent plate round the neckline of the armour, with a chased scroll."""
    s = T.s
    nk = T.Puv(neck, 0.03)
    o = np.stack([neck[:, 0] * 1.30, neck[:, 1] + 0.085], 1)
    nk_o = T.Puv(o, 0.03)
    gold = A["trim"]
    cv.band(nk, nk_o, gold, 1.0, mode="paint", rows=3, grain=1.0)
    # lit upper rim, darker lower rim (a curved plate)
    cv.band(nk, nk_o, "white", lambda S, Tt: 0.35 * (1 - Tt) ** 3 * np.sin(np.pi * S) ** 0.5,
            mode="paint", rows=4)
    cv.band(nk, nk_o, "gold_d", lambda S, Tt: 0.55 * Tt ** 2, rows=4)
    mid = nk + (nk_o - nk) * 0.5
    # chased scroll: a running wave of small spirals
    n = 7
    for k in range(n):
        u = (k + 0.5) / n
        c = g.at(mid, u)
        r = s * 0.012
        ph = np.linspace(0, 1.7 * math.pi, 12)
        rr = r * (1 - 0.6 * ph / (1.7 * math.pi))
        sp = c + np.stack([rr * np.cos(ph + k), rr * np.sin(ph + k) * 0.8], 1)
        cv.stroke(sp, s * 0.0035, "gold_d", 0.85, prof="silk")
    cv.brush(nk, s * 0.0065, "ink", style="iron", alpha=0.9)
    cv.brush(nk_o, s * 0.0085, "ink", style="reed", alpha=0.92, dry=0.2)
    for k in range(1, 12):
        p = g.at(nk_o, k / 12) + (g.at(nk, k / 12) - g.at(nk_o, k / 12)) * 0.18
        cv.dot(p, s * 0.0055, "gold_d", 0.9)
        cv.dot(p - s * 0.0015, s * 0.0022, "gold_l", 0.9)


def plates(cv, T, poly, A, style, y0, y1, rng, scale=1.0, rows=None, cols=None, top=None,
           bot=None):
    s = T.s
    plate, light, lace = A["plate"], A["light"], A["lace"]
    dark = pal.hexs(pal.mix(plate, "ink", 0.55))
    if style == "shanwen":
        R = 0.068 * scale
        dx = math.sqrt(3) * R
        row = 0
        y = y0
        while y < y1 + R:
            a = float(T.a(min(y, 2.2)))
            x = -a - dx + (dx / 2) * (row % 2)
            while x < a + dx:
                ang = np.radians([210, 150, 90, 30])
                cx, cy = x, y
                vx = cx + R * np.cos(ang)
                vy = cy - R * np.sin(ang)
                Pc = _xp(T, vx, vy, 0.024)
                ctr = _xp(T, cx, cy, 0.024)[0]
                if g.poly_contains(poly, ctr[None])[0]:
                    tone = rng.uniform(-0.06, 0.06)
                    # each plate: lit along its upper edges, shaded at the bottom
                    up = _xp(T, cx + 0.78 * R * np.cos(np.radians([160, 90, 20])),
                             cy - 0.78 * R * np.sin(np.radians([160, 90, 20])), 0.025)
                    cv.stroke(g.catmull(up, 5), s * R * 0.17, light, 0.62 + tone * 3,
                              prof="orchid", grain=1.0, noise=0.12)
                    if A.get("glint") and rng.uniform() < 0.55:
                        cv.stroke(g.catmull(up, 5)[3:-3], s * R * 0.07, A["glint"], 0.75,
                                  prof="orchid", grain=0.8)
                    lo = _xp(T, cx + 0.62 * R * np.cos(np.radians([215, 270, 325])),
                             cy - 0.62 * R * np.sin(np.radians([215, 270, 325])), 0.025)
                    cv.stroke(g.catmull(lo, 5), s * R * 0.30, dark, 0.30, mode="glaze",
                              prof="orchid", grain=1.0)
                for seg in _clip_runs(g.catmull(Pc, 4), poly):
                    cv.stroke(seg, s * 0.0045, "ink", 0.88, prof="nail", taper=(0.15, 0.85),
                              noise=0.12, grain=0.6)
                x += dx
            y += 1.5 * R
            row += 1
        return
    if style == "scale":
        r = 0.058 * scale
        dx = 1.55 * r
        row = 0
        y = y0
        while y < y1 + r:
            a = float(T.a(min(y, 2.2)))
            x = -a - dx + (dx / 2) * (row % 2)
            while x < a + dx:
                ph = np.linspace(math.pi * 1.02, math.pi * 1.98, 12)   # lower arc (y down)
                vx = x + r * np.cos(ph)
                vy = y - r * np.sin(ph) * 0.95
                arc = _xp(T, vx, vy, 0.024)
                ctr = _xp(T, x, y, 0.024)[0]
                if g.poly_contains(poly, ctr[None])[0]:
                    tone = rng.uniform(-0.08, 0.08)
                    hl = _xp(T, x + 0.45 * r * np.cos(ph[2:-2]), y - 0.45 * r * np.sin(ph[2:-2]) * 0.95 - 0.25 * r, 0.025)
                    cv.stroke(hl, s * r * 0.20, light, 0.45 + 2 * tone, prof="orchid", grain=1.0)
                    cv.stroke(arc, s * r * 0.30, dark, 0.35, mode="glaze", prof="orchid", grain=1.0)
                for seg in _clip_runs(arc, poly):
                    cv.stroke(seg, s * 0.0042, "ink", 0.85, prof="orchid", taper=(0.2, 0.8),
                              noise=0.12, grain=0.6)
                x += dx
            y += 0.72 * r
            row += 1
        return
    if style == "lacquer":
        # 皮甲: overlapping lacquered leather lames; each lame lies under the one above it
        # (soft shadow at its top), has a rolled, lit lower edge, gilt rivets, and is laced to
        # its neighbours with short paired cords
        h = 0.10 * scale
        y = y0 + 0.06
        k = 0
        lit = pal.hexs(pal.mix(plate, "white", 0.40))
        while y < y1:
            yb = min(y + h, y1)
            us_ = np.linspace(T.sil_u(y, -1), T.sil_u(y, 1), 40)
            band_top = T.P(us_, np.full_like(us_, y), 0.024)
            band_bot = T.P(us_, np.full_like(us_, yb), 0.024)
            inside = g.poly_contains(poly, (band_top + band_bot) / 2)
            if inside.sum() > 3:
                i0, i1 = np.where(inside)[0][[0, -1]]
                bt, bb = band_top[i0:i1 + 1], band_bot[i0:i1 + 1]
                tone = rng.uniform(-0.05, 0.05)
                if abs(tone) > 0.02:
                    cv.band(bt, bb, "white" if tone > 0 else "ink", abs(tone) * 3, mode="paint", rows=1)
                cv.band(bt, bb, "ink", lambda S, Tt: 0.40 * (1 - Tt) ** 3, rows=4, grain=1.0)
                cv.band(bt, bb, lit, lambda S, Tt: 0.55 * np.exp(-((Tt - 0.80) / 0.07) ** 2)
                        * (0.4 + 0.6 * np.sin(np.pi * S) ** 0.5), mode="paint", rows=8, grain=1.0)
                cv.stroke(bb, s * 0.0048, "ink", 0.9, prof="orchid", taper=(0.2, 0.8), noise=0.14)
                for j, xx in enumerate(np.linspace(0.06 + 0.05 * (k % 2), 0.94, 8)):
                    p = g.at(bt, xx) * 0.45 + g.at(bb, xx) * 0.55
                    cv.dot(p, s * 0.0060, A["trim"], 1.0)
                    cv.dot(p - s * 0.0018, s * 0.0022, "gold_l", 0.9)
                    q0 = g.at(bb, xx + 0.03) + (g.at(bt, xx) - g.at(bb, xx)) * 0.12
                    q1 = q0 + (g.at(bb, xx) - g.at(bt, xx)) * 0.30
                    for dx in (-0.006, 0.006):
                        cv.stroke(np.array([q0, q1]) + np.array([s * dx, 0]), s * 0.004, lace, 0.9,
                                  prof="flat", noise=0.1)
            y += h
            k += 1
        return
    # lamellar: rows of small plates, each plate with its own slight tone
    Tt = g.resample(top, 60)
    Bb = g.resample(bot, 60)
    lamellar(cv, Tt, Bb, rows or 9, cols or 16, plate, s, lace=lace, rng=rng, light=light)


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


def _patch(top, bot, u, t):
    """bilinear point between two curves: u along (0..1), t across (0 top .. 1 bottom)."""
    return g.at(top, u) * (1 - t) + g.at(bot, u) * t


def scale_patch(cv, top, bot, rows, cols, color, light, s, rng, line="ink"):
    """鱼鳞: overlapping scale rows between two curves (lower rows first, upper rows over)."""
    dark = pal.hexs(pal.mix(color, "ink", 0.55))
    for r in range(rows - 1, -1, -1):
        t_top = r / rows
        t_bot = (r + 1.25) / rows
        off = 0.5 * (r % 2)
        k = cols + r
        for c in range(-1, k + 1):
            u0 = (c + off) / k
            u1 = (c + 1 + off) / k
            if u1 <= 0 or u0 >= 1:
                continue
            u0c, u1c = max(0.0, u0), min(1.0, u1)
            um = 0.5 * (u0c + u1c)
            ph = np.linspace(0, 1, 9)
            pts = [_patch(top, bot, u0c + (u1c - u0c) * p_, t_top + (t_bot - t_top) * (0.55 + 0.45 * math.sin(math.pi * p_)))
                   for p_ in ph]
            arc = np.array(pts)
            body = np.vstack([_patch(top, bot, u0c, t_top), _patch(top, bot, u1c, t_top), arc[::-1]])
            tone = rng.uniform(-0.05, 0.05)
            cv.fill(body, pal.hexs(pal.mix(color, "white" if tone > 0 else "ink", abs(tone) * 2)), 1.0,
                    "paint", grain=1.0)
            hl = np.array([_patch(top, bot, u0c + (u1c - u0c) * p_, t_top + (t_bot - t_top) * 0.35)
                           for p_ in (0.2, 0.5, 0.8)])
            cv.stroke(g.catmull(hl, 4), s * 0.010, light, 0.55, prof="orchid", grain=1.0)
            cv.stroke(arc, s * 0.012, dark, 0.35, mode="glaze", prof="orchid")
            cv.stroke(arc, s * 0.0042, line, 0.88, prof="orchid", taper=(0.25, 0.75), noise=0.12)


def pauldron(cv, T, side, palette="azure_iron", style=None, rows=4, size=1.0, rng=None,
             color=None, trim=None, lace=None, lining="cinnabar", **_):
    """披膊: a cape of plates draped over the shoulder and upper arm (Tang/Song style), its top
    following the shoulder slope, flaring out at the hem, gilt-hemmed over a brocade lining.
    Lacquer colour and plate style come from the armour palette (red lacquer guards over black
    armour, iron over red, ...)."""
    s = T.s
    A = dict(ARMOUR[palette])
    col = color or A["pauldron"]
    light = A["p_light"]
    trim = trim or A["trim"]
    lace = lace or A["lace"]
    style = style or A["p_style"]
    rng = rng or np.random.default_rng(5)
    n = 30
    t = np.linspace(0, 1, n)
    u_out_top = T.sil_u(1.30, side)
    u_out_bot = T.sil_u(1.75, side)
    tu = side * (0.40 + (abs(u_out_top) + 0.10 - 0.40) * t)
    ty = 1.10 + 0.20 * g.smoothstep(0.0, 1.0, t) ** 1.2
    tdr = 0.03 + 0.04 * t
    bu = side * (0.50 + (abs(u_out_bot) + 0.15 - 0.50) * t)
    by = 1.33 + 0.45 * t ** 1.3 * size
    bdr = 0.05 + 0.10 * t
    top = np.vstack([T.P(a, b, c) for a, b, c in zip(tu, ty, tdr)])
    bot = np.vstack([T.P(a, b, c) for a, b, c in zip(bu, by, bdr)])
    poly = np.vstack([top, bot[::-1]])
    # brocade lining peeking under the hem
    lin_b = bot + (bot - top) * 0.10
    cv.band(bot, lin_b, lining, 1.0, mode="paint", rows=1)
    cv.stroke(lin_b, s * 0.006, "ink", 0.85, prof="orchid")
    cv.fill(poly, col, 1.0, "paint", grain=1.0)
    hem_a = top + (bot - top) * 0.86
    if style == "scale":
        scale_patch(cv, top, hem_a, rows, 4, col, light, s, rng)
    elif style == "lacquer":
        for k in range(rows - 1, -1, -1):
            A_ = top + (hem_a - top) * (k / rows)
            B_ = top + (hem_a - top) * min(1.0, (k + 1.08) / rows)
            cv.band(A_, B_, "ink", lambda S, Tt: 0.40 * (1 - Tt) ** 3, rows=4)
            cv.band(A_, B_, light, lambda S, Tt: 0.5 * np.exp(-((Tt - 0.8) / 0.08) ** 2), mode="paint", rows=6)
            cv.stroke(B_, s * 0.0045, "ink", 0.9, prof="iron")
            for j in range(1, 6):
                p = g.at(A_, j / 6) * 0.5 + g.at(B_, j / 6) * 0.5
                cv.dot(p, s * 0.006, trim, 1.0)
    else:
        for k in range(rows - 1, -1, -1):
            t0, t1 = k / rows, (k + 1) / rows + 0.03
            A_ = top + (hem_a - top) * t0
            B_ = top + (hem_a - top) * min(t1, 1.0)
            lamellar(cv, A_, B_, 1, 6 + 2 * k, col, s, lace=lace, rng=rng, row_light=0.28, light=light)
            cv.stroke(B_, s * 0.0045, "ink", 0.9, prof="iron")
    # gilt hem with a running scroll
    cv.band(hem_a, bot, trim, 1.0, mode="paint", rows=2, grain=1.0)
    cv.band(hem_a, bot, "gold_d", lambda S, Tt: 0.5 * Tt ** 2, rows=3)
    cv.band(hem_a, bot, "white", lambda S, Tt: 0.35 * (1 - Tt) ** 3, mode="paint", rows=3)
    m = int(g.length(bot) / (s * 0.035))
    for k in range(m):
        u = (k + 0.5) / max(1, m)
        c = g.at(hem_a, u) * 0.5 + g.at(bot, u) * 0.5
        cv.dot(c, s * 0.0055, "gold_d", 0.9)
    # modelling: light on the shoulder top, dark under the arm side
    cv.band(top, top + (bot - top) * 0.5, "white", lambda S, Tt: 0.18 * (1 - Tt) ** 2
            * np.sin(np.pi * S) ** 0.5, mode="paint", rows=4)
    cv.wash(bot, s * 0.10, "ink", 0.28, side=_inward(bot, poly), rows=4, passes=2)
    cv.brush(top, s * 0.010, "ink", style="reed", alpha=0.92, dry=0.35)
    cv.brush(bot, s * 0.011, "ink", style="orchid", alpha=0.92, dry=0.45)
    cv.brush(hem_a, s * 0.005, "ink", style="iron", alpha=0.8)
    cv.brush(np.array([top[-1], bot[-1]]), s * 0.009, "ink", style="iron", alpha=0.9)
    return poly


def scarf(cv, T, fd, color="#b3301f", y=1.05, knot=(0.06, 1.20)):
    """领巾: a silk scarf round the neck, knotted in front, its two ends hanging over the
    armour collar."""
    s = T.s
    dark = pal.hexs(pal.mix(color, "ink", 0.45))
    light = pal.hexs(pal.mix(color, "white", 0.30))
    us = np.linspace(-0.95, 0.95, 40)
    yt = y - 0.005 + 0.03 * np.cos(us * math.pi / 2) ** 2
    yb = y + 0.065 + 0.05 * np.cos(us * math.pi / 2) ** 2
    A_ = T.Puv(np.stack([us, yt], 1), 0.030)
    B_ = T.Puv(np.stack([us, yb], 1), 0.036)
    cv.band(A_, B_, color, 1.0, mode="paint", rows=2, grain=1.0)
    cv.band(A_, B_, dark, lambda S, Tt: 0.5 * (1 - np.sin(np.pi * S)) ** 1.5 + 0.25 * Tt ** 2, rows=4)
    for k in range(3):
        f = 0.25 + 0.22 * k
        C = A_ * (1 - f) + B_ * f
        cv.stroke(g.sub(C, 0.15 + 0.05 * k, 0.85 - 0.04 * k), s * 0.004, dark, 0.7, prof="orchid")
    cv.brush(A_, s * 0.0075, "ink", style="orchid", alpha=0.9)
    cv.brush(B_, s * 0.0085, "ink", style="orchid", alpha=0.9)
    # knot and hanging ends
    kc = T.P(knot[0], knot[1], 0.10)
    for j, (dx, ln, sw) in enumerate(((-0.05, 0.30, -1), (0.07, 0.24, 1))):
        p0 = kc
        p1 = kc + np.array([s * dx * 0.6, s * ln * 0.45])
        p2 = kc + np.array([s * (dx + 0.02 * sw), s * ln])
        C = g.catmull([p0, p1, p2], 8)
        wv = s * np.linspace(0.05, 0.075, len(C))
        L = C + g.normals(C) * (wv / 2)[:, None]
        R = C - g.normals(C) * (wv / 2)[:, None]
        cv.band(L, R, color, 1.0, mode="paint", rows=2, grain=1.0)
        cv.band(L, R, dark, lambda S, Tt: 0.45 * (np.abs(Tt - 0.5) * 2) ** 2 + 0.2 * S, rows=4)
        cv.stroke(g.sub(C, 0.1, 0.9), s * 0.004, dark, 0.7, prof="orchid")
        cv.brush(L, s * 0.0065, "ink", style="orchid", alpha=0.88)
        cv.brush(R, s * 0.0065, "ink", style="orchid", alpha=0.88)
        # cut end of the silk with a short fringe
        cv.brush(np.array([L[-1], R[-1]]), s * 0.0055, "ink", style="iron", alpha=0.85)
        d = C[-1] - C[-2]
        d = d / (np.linalg.norm(d) + 1e-9)
        for f_ in np.linspace(0.1, 0.9, 6):
            p = L[-1] * (1 - f_) + R[-1] * f_
            cv.stroke(np.array([p, p + d * s * 0.025]), s * 0.004, dark, 0.8, prof="hair")
    K = g.ellipse(kc, s * 0.045, s * 0.035, 0.3, n=20)
    cv.fill(K, color, 1.0, "paint", grain=1.0)
    cv.blob(kc + np.array([-s * 0.01, -s * 0.01]), s * 0.022, s * 0.015, light, 0.6, mode="paint")
    cv.edge(K, s * 0.015, dark, 0.5, side=_inward(K, K), rows=3, closed=True)
    cv.brush(np.vstack([K, K[:1]]), s * 0.0075, "ink", style="orchid", alpha=0.9, caps=False)


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
