"""Costume extras (Blender side): hair masses, helmets, hats, armour, cloaks, ornaments.

``build(st, spec)`` dispatches on ``spec["hair"]["kind"]``, ``spec["headgear"]["kind"]`` and
the ``spec["costume"]`` keys.  Everything is lofted analytic geometry in head units; the hair
cap and the helmet are offset shells of the same analytic head (:mod:`geo`), so they always fit
whatever skull / jaw the canon chose.
"""

import math

import numpy as np

import geo
import palette as PL
from bust import pattern_for
from gear_math import hairline


def build(st, spec):
    hair(st, spec)
    hg = spec.get("headgear", {})
    if hg.get("kind"):
        HEADGEAR[hg["kind"]](st, spec, hg)
    cos = spec.get("costume", {})
    if cos.get("armour"):
        armour(st, spec, cos["armour"])
    if cos.get("cloak"):
        cloak(st, spec, cos["cloak"])
    if cos.get("shawl"):
        shawl(st, spec, cos["shawl"])


# =============================================================================================
# helpers
# =============================================================================================
def hair_mat(st, color="hair"):
    c = PL.srgb(color)
    light = PL.mix(c, "ink_grey", 0.18) if sum(c) < 0.6 else c
    deep = PL.deepen(c, 0.55) if sum(c) >= 0.6 else PL.srgb("ink_d")
    return st.mat("Hair_" + PL.to_hex(c), light, deep, power=1.2, blend=0.55, lo=0.0, hi=1.0,
                  mask=(0, 1, 0))


def flat_mat(st, name, color, deep=None, power=1.4, blend=0.5, pattern=None, mask=(0, 0, 0)):
    return st.mat(name, color, deep if deep is not None else PL.deepen(color, 0.68),
                  power=power, blend=blend, pattern=pattern, mask=mask)


def shell(L, zt_pairs, offset_fn, n_rows=24):
    """Offset shell of a loft between per-column z ranges.  ``zt_pairs`` = (t (C,), z0 (C,),
    z1 (C,)); returns a (rows, C, 3) grid in head-local space."""
    t, z0, z1 = zt_pairs
    rows = []
    for i in range(n_rows):
        a = i / (n_rows - 1)
        z = z0 + (z1 - z0) * a
        P = L.point(z, t)
        N = L.normal(z, t)
        rows.append(P + N * offset_fn(a, z, t)[..., None])
    return np.array(rows)


def hair(st, spec):
    hp = dict(spec.get("hair", {}))
    kind = hp.get("kind", "topknot")
    if kind in ("none", "bald"):
        return
    L = st.head_loft
    col = hp.get("color", "hair")
    hm = hair_mat(st, col)
    # ---- cap ----------------------------------------------------------------------------
    C = 112
    t = np.linspace(-math.pi, math.pi, C, endpoint=False)
    z0 = hairline(hp, t)
    crown = spec.get("head", {}).get("crown", 0.5)
    z1 = np.full(C, crown - 0.004)
    vol = hp.get("volume", 0.03)
    top_vol = hp.get("top_volume", vol * 1.4)
    side_puff = hp.get("side_puff", 0.0)           # ladies: hair puffed over the temples (鬓)

    def off(a, z, tt):
        edge = geo.smoothstep(0.0, 0.18, a)          # thin at the hairline
        side = side_puff * np.exp(-((np.abs(tt) - 1.35) / 0.35) ** 2) * \
            np.exp(-((z - 0.08) / 0.14) ** 2)
        return 0.002 + edge * (vol + (top_vol - vol) * a) + side * edge
    G = shell(L, (t, z0, z1), off, 22)
    cap = st.grid_mesh("HairCap", G, "hair", hm, closed=True, cap_top=True, M=st.M_head)
    st.fit.append(cap)
    st.hair_shell = (t, z0, z1, off)
    # hair-flow curves (combed strands) for the 2D stage: from the hairline up to the knot
    knot = np.array(hp.get("knot_at", (0.0, 0.10, crown - 0.02)))
    nfl = hp.get("flow_n", 46)
    for k in range(nfl):
        tk = -math.pi + 2 * math.pi * (k + 0.5) / nfl
        zz0 = float(hairline(hp, np.array([tk]))[0]) + 0.01
        zz = np.linspace(zz0, crown - 0.05, 14)
        tt = np.full(14, tk)
        P = L.point(zz, tt) + L.normal(zz, tt) * (np.array([off(i / 13, zz[i], tk) for i in range(14)])[:, None] + 0.004)
        # bend the upper part towards the knot
        w = geo.smoothstep(0.55, 1.0, np.linspace(0, 1, 14))[:, None]
        P = P * (1 - w * 0.5) + knot * (w * 0.5)
        st.add_curve("hairflow%d" % k, "hairflow", st.xf(st.M_head, P),
                     color=hp.get("strand", None))
    # ---- buns / knots ---------------------------------------------------------------------
    for i, b in enumerate(hp.get("buns", default_buns(kind, crown))):
        bun(st, b, hm, "Bun%d" % i)
    # hairpin / band ornaments
    for i, o in enumerate(hp.get("ornaments", [])):
        ornament(st, o, "Orn%d" % i)


def default_buns(kind, crown):
    if kind == "topknot":
        return [dict(kind="ellipsoid", c=(0.0, 0.07, crown + 0.06), r=(0.085, 0.085, 0.085))]
    if kind == "elder":
        return [dict(kind="ellipsoid", c=(0.0, 0.10, crown + 0.035), r=(0.075, 0.07, 0.065))]
    return []


def bun(st, b, hm, name):
    kind = b.get("kind", "ellipsoid")
    M = st.M_head
    if kind == "ellipsoid":
        rot = None
        if b.get("tilt"):
            a = math.radians(b["tilt"])
            rot = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
        ob = st.ellipsoid(name, b["c"], b["r"], "hair", hm, M=M, rot=rot)
        st.fit.append(ob)
        # strands wrapping round the bun
        c = np.array(b["c"])
        r = np.array(b["r"])
        for k in range(b.get("flow_n", 10)):
            a0 = 2 * math.pi * k / b.get("flow_n", 10)
            th = np.linspace(-1.2, 1.25, 14)
            P = np.stack([np.cos(th) * np.sin(a0), -np.cos(th) * np.cos(a0), np.sin(th)], -1) * r * 1.03
            if rot is not None:
                P = P @ rot.T
            st.add_curve(name + "_flow%d" % k, "hairflow", st.xf(M, P + c))
    elif kind == "loop":
        # a hair loop (髻环): a torus segment standing on the head
        c = np.array(b["c"])
        R, rr = b.get("R", 0.10), b.get("r", 0.035)
        yaw = math.radians(b.get("yaw", 0.0))
        tilt = math.radians(b.get("tilt", 0.0))
        a = np.linspace(b.get("a0", -0.15), b.get("a1", 1.15), 26) * math.pi
        center = np.stack([R * np.cos(a), np.zeros_like(a), R * np.sin(a)], -1)
        # rotate: tilt about x, yaw about z
        Rx = np.array([[1, 0, 0], [0, math.cos(tilt), -math.sin(tilt)], [0, math.sin(tilt), math.cos(tilt)]])
        Rz = np.array([[math.cos(yaw), -math.sin(yaw), 0], [math.sin(yaw), math.cos(yaw), 0], [0, 0, 1]])
        center = center @ Rx.T @ Rz.T + c
        rad = rr * (0.75 + 0.25 * np.sin(np.linspace(0, math.pi, len(a))))
        ob = st.tube(name, center, rad, "hair", hm, n=14, M=M)
        st.fit.append(ob)
        for k in range(5):
            off = (k - 2) / 2.5 * rr * 0.6
            P = center + np.array([0, 0, 0]) + (center - c) / np.maximum(
                np.linalg.norm(center - c, axis=1, keepdims=True), 1e-9) * (rr * 0.95 + off * 0.2)
            P = P + np.array([0, -1, 0]) @ Rz.T * off
            st.add_curve(name + "_flow%d" % k, "hairflow", st.xf(M, P))


def ornament(st, o, name):
    """Hairpins (簪 / 钗), flowers, combs, crowns: small solid pieces + 2D dangles."""
    M = st.M_head
    kind = o.get("kind", "pin")
    if kind == "pin":
        a = np.array(o["a"], float)
        b = np.array(o["b"], float)
        P = a + (b - a) * np.linspace(0, 1, 12)[:, None]
        gm = flat_mat(st, "Gold", "gold", "gold_d", power=1.0, blend=0.4)
        st.tube(name, P, o.get("r", 0.008), "hard", gm, n=8, M=M)
        if o.get("head"):
            hc = o.get("head_color", "gold")
            hm = flat_mat(st, "OrnHead_" + PL.to_hex(hc), hc, power=1.0, blend=0.4)
            st.ellipsoid(name + "_h", b, (o["head"],) * 3, "hard", hm, M=M, n=(12, 16))
        if o.get("dangles"):
            for k in range(o["dangles"]):
                st.add_curve(name + "_d%d" % k, "dangle", st.xf(M, b[None]),
                             n=k, total=o["dangles"], length=o.get("dangle_len", 0.10),
                             color=o.get("dangle_color", "gold"))
    elif kind == "flower":
        c = np.array(o["c"], float)
        col = o.get("color", "lotus")
        fm = flat_mat(st, "Flower_" + PL.to_hex(col), col, PL.deepen(col, 0.75), power=1.2)
        n = o.get("petals", 6)
        r = o.get("r", 0.04)
        for k in range(n):
            a = 2 * math.pi * k / n
            pc = c + np.array([math.cos(a) * r * 0.6, -0.01, math.sin(a) * r * 0.6])
            st.ellipsoid(name + "_p%d" % k, pc, (r * 0.55, r * 0.25, r * 0.55), "fine", fm,
                         M=M, n=(8, 12))
        cm = flat_mat(st, "Gold", "gold", "gold_d", power=1.0, blend=0.4)
        st.ellipsoid(name + "_c", c + np.array([0, -0.02, 0]), (r * 0.3,) * 3, "fine", cm,
                     M=M, n=(8, 12))
    elif kind == "comb":
        # a crescent comb (梳篦) on top of the hair
        c = np.array(o["c"], float)
        w, h = o.get("w", 0.12), o.get("h", 0.045)
        a = np.linspace(-1, 1, 20)
        top = np.stack([a * w, np.zeros(20), h * np.sqrt(1 - a ** 2 * 0.9)], -1)
        bot = np.stack([a * w, np.zeros(20), np.zeros(20)], -1)
        cm = flat_mat(st, "Comb_" + PL.to_hex(o.get("color", "gold")), o.get("color", "gold"),
                      power=1.0, blend=0.4, pattern=pattern_for(o.get("pattern")))
        yaw = math.radians(o.get("yaw", 0))
        tilt = math.radians(o.get("tilt", -20))
        Rx = np.array([[1, 0, 0], [0, math.cos(tilt), -math.sin(tilt)], [0, math.sin(tilt), math.cos(tilt)]])
        Rz = np.array([[math.cos(yaw), -math.sin(yaw), 0], [math.sin(yaw), math.cos(yaw), 0], [0, 0, 1]])
        G = np.stack([bot, top], 0) @ Rx.T @ Rz.T + c
        G2 = G + np.array([0, 0.006, 0])
        G = np.concatenate([G, G2[::-1]], 0)
        st.grid_mesh(name, G, "hard", cm, closed=False, M=M)
    elif kind == "crown":
        # small hair crown (发冠) round a topknot
        c = np.array(o["c"], float)
        r, h = o.get("r", 0.075), o.get("h", 0.07)
        col = o.get("color", "gold")
        cm = flat_mat(st, "Crown_" + PL.to_hex(col), col, PL.deepen(col, 0.7), power=1.1, blend=0.45)
        t = np.linspace(0, 2 * math.pi, 40, endpoint=False)
        rows = []
        for k, (zz, rk) in enumerate([(0, 1.0), (h * 0.5, 1.03), (h, 0.96)]):
            rows.append(np.stack([np.sin(t) * r * rk, -np.cos(t) * r * rk * 0.95, np.full(40, zz)], -1))
        G = np.array(rows) + c
        st.grid_mesh(name, G, "hard", cm, closed=True, M=M)
        P = c + np.array([[-r * 1.6, 0, h * 0.55], [r * 1.6, 0, h * 0.55]])
        gm = flat_mat(st, "Gold", "gold", "gold_d", power=1.0, blend=0.4)
        st.tube(name + "_pin", np.linspace(P[0], P[1], 10), 0.007, "hard", gm, n=8, M=M)


# =============================================================================================
# headgear
# =============================================================================================
def helmet(st, spec, hg):
    """兜鍪: a domed iron helmet with a brim band, ribs, a finial with a red tassel (缨) and a
    lamellar neck guard (顿项) hanging to the shoulders."""
    L = st.head_loft
    M = st.M_head
    col = hg.get("color", "steel")
    hm = flat_mat(st, "Helmet", col, PL.deepen(col, 0.55), power=1.1, blend=0.5)
    gold = flat_mat(st, "Gold", "gold", "gold_d", power=1.0, blend=0.4)
    brim_z = hg.get("brim_z", 0.20)
    C = 112
    t = np.linspace(-math.pi, math.pi, C, endpoint=False)
    crown = spec.get("head", {}).get("crown", 0.5)
    lift = hg.get("lift", 0.045)
    peak = hg.get("peak", 0.10)                  # pointed dome height above the skull

    def dome(z, tt, extra=0.0):
        P = L.point(np.minimum(z, crown - 0.003), tt)
        N = L.normal(np.minimum(z, crown - 0.003), tt)
        return P + N * (lift + extra)
    rows = []
    zs = np.linspace(brim_z, crown - 0.004, 18)
    for i, z in enumerate(zs):
        a = i / (len(zs) - 1)
        P = dome(np.full(C, z), t)
        P[:, 2] += peak * a ** 2.2
        # narrow towards the top for a slightly pointed silhouette
        cxy = np.array([0.0, 0.05])
        P[:, :2] = cxy + (P[:, :2] - cxy) * (1 - 0.18 * a ** 1.5)
        rows.append(P)
    G = np.array(rows)
    ob = st.grid_mesh("Helmet", G, "hard", hm, closed=True, cap_top=True, M=M)
    st.fit.append(ob)
    top = G[-1].mean(0)
    # brim band (a raised gold band round the rim, with a peak over the brow)
    Pb = dome(np.full(C, brim_z), t, 0.012)
    Pb2 = dome(np.full(C, brim_z + hg.get("band_h", 0.05)), t, 0.012)
    Pb2[:, 2] += peak * 0.0
    st.grid_mesh("HelmetBand", np.stack([Pb, Pb2], 0), "hard", gold, closed=True, M=M)
    # visor peak over the brow (眉庇)
    if hg.get("visor", True):
        tv = np.linspace(-0.95, 0.95, 30)
        Pv0 = dome(np.full(30, brim_z), tv, 0.014)
        Pv1 = Pv0 + L.normal(np.full(30, brim_z), tv) * 0.06 * np.cos(tv / 0.95 * math.pi / 2)[:, None] ** 0.6
        Pv1[:, 2] -= 0.01
        vm = flat_mat(st, "HelmetVisor", col, PL.deepen(col, 0.5), power=1.0, blend=0.5)
        st.grid_mesh("HelmetVisor", np.stack([Pv0, Pv1], 0), "hard", vm, closed=False, M=M)
    # ribs
    for k in range(hg.get("ribs", 6)):
        tk = -math.pi + 2 * math.pi * (k + 0.5) / hg.get("ribs", 6)
        zr = np.linspace(brim_z + 0.05, crown - 0.01, 12)
        Pr = np.array([dome(np.array([z]), np.array([tk]), 0.008)[0] for z in zr])
        a = np.linspace(0, 1, 12) * (crown - 0.01 - brim_z - 0.05) / (crown - 0.004 - brim_z)
        Pr[:, 2] += peak * a ** 2.2
        cxy = np.array([0.0, 0.05])
        Pr[:, :2] = cxy + (Pr[:, :2] - cxy) * (1 - 0.18 * a[:, None] ** 1.5)
        st.tube("HelmetRib%d" % k, Pr, 0.009, "hard", gold, n=6, M=M)
    # finial and tassel
    fin = top + np.array([0, 0, 0.03])
    st.tube("HelmetPost", np.linspace(top - np.array([0, 0, 0.01]), fin + np.array([0, 0, 0.05]), 6),
            0.014, "hard", gold, n=8, M=M)
    st.ellipsoid("HelmetKnob", fin + np.array([0, 0, 0.06]), (0.026, 0.026, 0.03), "hard", gold,
                 M=M, n=(10, 14))
    st.anchors["tassel"] = st.xf(M, fin + np.array([0, 0, 0.085])).tolist()
    st.fit.append(st.xf(M, (fin + np.array([0, 0, 0.06 + hg.get("tassel_len", 0.22) * 0.55]))[None]))
    if hg.get("tassel", True):
        st.add_curve("tassel", "tassel", st.xf(M, (fin + np.array([0, 0, 0.08]))[None]),
                     color=hg.get("tassel_color", "cinnabar"), length=hg.get("tassel_len", 0.22))
    # neck guard (顿项): a skirt from the rim at the sides / back, flaring to the shoulders
    if hg.get("neck_guard", True):
        ng_col = hg.get("guard_color", col)
        pat = hg.get("guard_pattern", dict(kind="lamellar", w=0.045, h=0.06, light="steel_l",
                                             lace="cinnabar"))
        gm = flat_mat(st, "NeckGuard", ng_col, PL.deepen(ng_col, 0.55), power=1.2, blend=0.5,
                      pattern=pattern_for(pat))
        open_t = hg.get("open_t", 1.05)      # face opening half angle
        tg = np.linspace(open_t, 2 * math.pi - open_t, 64)
        tg = np.where(tg > math.pi, tg - 2 * math.pi, tg)
        top_ring = dome(np.full(64, brim_z + 0.01), tg, 0.0)
        rows = [top_ring]
        drop = hg.get("guard_drop", 0.62)
        for k in range(1, 9):
            a = k / 8
            z = brim_z - drop * a
            # flare outwards with the drop (over the jaw and on to the shoulders)
            ring = top_ring.copy()
            ring[:, 2] = z + 0.02 * np.cos(tg)
            cxy = np.array([0.0, 0.08])
            fl = 1 + hg.get("guard_flare", 0.55) * a ** 1.6
            ring[:, :2] = cxy + (top_ring[:, :2] - cxy) * fl
            rows.append(ring)
        Gg = np.array(rows)
        s = np.cumsum(np.r_[0, np.linalg.norm(np.diff(Gg[0], axis=0), axis=1)])
        uv = np.stack(np.broadcast_arrays(s[None, :], -np.linspace(0, drop, 9)[:, None]), -1)
        st.grid_mesh("NeckGuard", Gg, "hard", gm, closed=False, uv=uv, M=M)
        # gold edging along the front opening and the hem
        for side in (0, -1):
            P = Gg[:, side]
            st.tube("GuardEdge%d" % side, P + (P - np.array([0, 0.08, P[:, 2].mean()])) * 0.0,
                    0.010, "hard", gold, n=6, M=M)


def dongpo(st, spec, hg):
    """东坡巾: a tall square cap of black gauze with a lower outer wall."""
    L = st.head_loft
    M = st.M_head
    col = hg.get("color", "ink")
    gm = flat_mat(st, "Hat", col, PL.deepen(col, 0.6), power=1.0, blend=0.5,
                  pattern=pattern_for(hg.get("pattern", dict(kind="gauze", color="ink_grey",
                                                                     alpha=0.28, period=0.016))),
                  mask=(0, 0, 0))
    base_z = hg.get("base_z", 0.23)
    # inner wall: rounded square tube following the skull at the base, rising straight up
    C = 96
    t = np.linspace(-math.pi, math.pi, C, endpoint=False)
    base = L.point(np.full(C, base_z), t) + L.normal(np.full(C, base_z), t) * 0.03
    cxy = np.array([0.0, 0.03])
    h_in = hg.get("h", 0.42)
    sq = hg.get("square", 4.0)

    def squarish(P, k):
        d = P[:, :2] - cxy
        ang = np.arctan2(d[:, 1], d[:, 0])
        r = np.linalg.norm(d, axis=1)
        c, s = np.cos(ang), np.sin(ang)
        rs = 1.0 / (np.abs(c) ** sq + np.abs(s) ** sq) ** (1 / sq)
        out = P.copy()
        out[:, :2] = cxy + np.stack([c, s], -1) * (r * (1 - k) + r.mean() * rs * 0.92 * k)[:, None]
        return out
    rows = []
    for k, (dz, kk, sc) in enumerate([(0.0, 0.0, 1.0), (0.06, 0.6, 1.0), (h_in * 0.5, 1.0, 1.0),
                                      (h_in, 1.0, 1.02)]):
        P = squarish(base, kk)
        P[:, :2] = cxy + (P[:, :2] - cxy) * sc
        P[:, 2] = base_z + dz + (0.0 if k == 0 else 0.0)
        rows.append(P)
    G = np.array(rows)
    s = np.cumsum(np.r_[0, np.linalg.norm(np.diff(G[-1], axis=0), axis=1)])
    uv = np.stack(np.broadcast_arrays(s[None, :], G[:, :1, 2] * np.ones((1, C))), -1)
    ob = st.grid_mesh("HatInner", G, "hard", gm, closed=True, cap_top=True, uv=uv, M=M)
    st.fit.append(ob)
    # outer wall: a little larger, lower, its front corners cut (the 东坡 silhouette)
    h_out = hg.get("h_out", 0.28)
    rows = []
    for dz, kk, sc in [(-0.005, 0.0, 1.06), (0.06, 0.65, 1.07), (h_out, 1.0, 1.08)]:
        P = squarish(base, kk)
        P[:, :2] = cxy + (P[:, :2] - cxy) * sc
        P[:, 2] = base_z + dz
        rows.append(P)
    G2 = np.array(rows)
    # cut a shallow V at the front of the outer wall
    front = np.abs(t) < 0.5
    G2[-1, front, 2] -= 0.07 * (1 - np.abs(t[front]) / 0.5)
    uv2 = np.stack(np.broadcast_arrays(s[None, :], G2[:, :1, 2] * np.ones((1, C))), -1)
    ob2 = st.grid_mesh("HatOuter", G2, "hard", gm, closed=True, uv=uv2, M=M)
    st.fit.append(ob2)


def futou(st, spec, hg):
    """幞头: a black cap with a rounded back lobe and two stiff horizontal wings."""
    L = st.head_loft
    M = st.M_head
    col = hg.get("color", "ink")
    gm = flat_mat(st, "Hat", col, PL.deepen(col, 0.6), power=1.0, blend=0.5,
                  pattern=pattern_for(dict(kind="gauze", color="ink_grey", alpha=0.25,
                                           period=0.016)))
    base_z = hg.get("base_z", 0.22)
    C = 96
    t = np.linspace(-math.pi, math.pi, C, endpoint=False)
    crown = spec.get("head", {}).get("crown", 0.5)
    zs = np.linspace(base_z, crown - 0.004, 14)
    rows = []
    for i, z in enumerate(zs):
        P = L.point(np.full(C, z), t) + L.normal(np.full(C, z), t) * 0.035
        rows.append(P)
    G = np.array(rows)
    ob = st.grid_mesh("HatCap", G, "hard", gm, closed=True, cap_top=True, M=M)
    st.fit.append(ob)
    # raised back lobe
    lobe_c = np.array([0.0, 0.16, crown + 0.03])
    ob2 = st.ellipsoid("HatLobe", lobe_c, (0.2, 0.17, 0.14), "hard", gm, M=M)
    st.fit.append(ob2)
    if hg.get("wings", True):
        for side in (-1, 1):
            a = np.linspace(0, 1, 10)
            P0 = np.array([side * 0.2, 0.25, base_z + 0.08])
            P = P0 + np.stack([side * a * hg.get("wing_len", 0.55), 0.04 * a, 0.02 * a], -1)
            st.tube("Wing%+d" % side, P, 0.012 + 0.0 * a, "hard", gm, n=6, M=M)


def guan(st, spec, hg):
    """A small crown (冠) over the topknot - officials, princes, Daoists."""
    crown = spec.get("head", {}).get("crown", 0.5)
    ornament(st, dict(kind="crown", c=(0.0, 0.07, crown + 0.0), r=hg.get("r", 0.08),
                      h=hg.get("h", 0.085), color=hg.get("color", "gold")), "Guan")


HEADGEAR = dict(helmet=helmet, dongpo=dongpo, futou=futou, guan=guan)


# =============================================================================================
# armour and cloak
# =============================================================================================
def armour(st, spec, ap):
    """Lamellar cuirass (札甲) over the robe with shoulder guards (披膊), chest mirrors (护心镜)
    and a padded collar (项护)."""
    Lt = st.torso_loft
    M = st.M_body
    col = ap.get("color", "steel")
    pat = dict(kind="lamellar", w=ap.get("plate_w", 0.05), h=ap.get("plate_h", 0.075),
               light=ap.get("light", "steel_l"), lace=ap.get("lace", "cinnabar"))
    am = flat_mat(st, "Armour", col, PL.deepen(col, 0.5), power=1.2, blend=0.55,
                  pattern=pattern_for(pat))
    gold = flat_mat(st, "Gold", "gold", "gold_d", power=1.0, blend=0.4)
    top_z = ap.get("top_z", -0.86)
    C = 120
    t = np.linspace(-math.pi, math.pi, C, endpoint=False)
    zs = np.linspace(-2.1, top_z, 22)
    rows = []
    for z in zs:
        P = Lt.point(np.full(C, z), t) + Lt.normal(np.full(C, z), t) * ap.get("lift", 0.03)
        rows.append(P)
    G = np.array(rows)
    s = np.cumsum(np.r_[0, np.linalg.norm(np.diff(G[-6], axis=0), axis=1)])
    uv = np.stack(np.broadcast_arrays(s[None, :], zs[:, None]), -1)
    st.grid_mesh("Cuirass", G, "hard", am, closed=True, uv=uv, M=M)
    # padded collar round the neck opening (gold-edged cinnabar roll)
    cc = ap.get("collar_color", "cinnabar")
    cm = flat_mat(st, "ArmCollar", cc, PL.deepen(cc, 0.6), power=1.2, blend=0.5,
                  pattern=pattern_for(ap.get("collar_pattern")))
    ring = Lt.point(np.full(C, top_z), t) + Lt.normal(np.full(C, top_z), t) * (ap.get("lift", 0.03) + 0.01)
    ring2 = Lt.point(np.full(C, top_z + 0.09), t) + Lt.normal(np.full(C, top_z + 0.09), t) * 0.025
    Gc = np.stack([ring, (ring + ring2) * 0.5 + np.array([0, 0, 0.0]), ring2], 0)
    Gc[1, :, :2] = Gc[1, :, :2] * 1.0
    st.grid_mesh("ArmCollar", Gc, "band", cm, closed=True, M=M)
    st.tube("ArmCollarEdge", np.concatenate([ring, ring[:1]]), 0.012, "hard", gold, n=6, M=M)
    # shoulder guards: wide curved lamellar plates over each shoulder and upper arm
    if ap.get("shoulders", True):
        sm = flat_mat(st, "ShoulderGuard", ap.get("shoulder_color", col),
                      PL.deepen(ap.get("shoulder_color", col), 0.5), power=1.2, blend=0.55,
                      pattern=pattern_for(dict(pat, w=pat["w"] * 1.1)))
        for side in (-1, 1):
            rows = []
            tz = np.linspace(-0.05, 0.85, 14)
            for k, zz in enumerate(np.linspace(-0.92, -1.55, 10)):
                a = k / 9
                tt = side * (math.pi / 2 + (tz - 0.4) * (1.3 - 0.2 * a))
                P = Lt.point(np.full(14, zz), tt) + Lt.normal(np.full(14, zz), tt) * (0.06 + 0.07 * a)
                rows.append(P)
            Gs = np.array(rows)
            s = np.cumsum(np.r_[0, np.linalg.norm(np.diff(Gs[3], axis=0), axis=1)])
            uv = np.stack(np.broadcast_arrays(s[None, :], np.linspace(-0.92, -1.55, 10)[:, None]), -1)
            st.grid_mesh("Shoulder%+d" % side, Gs, "hard", sm, closed=False, uv=uv, M=M)
            st.tube("ShoulderEdge%+d" % side, Gs[:, 0], 0.012, "hard", gold, n=6, M=M)
            st.tube("ShoulderHem%+d" % side, Gs[-1], 0.012, "hard", gold, n=6, M=M)
    # chest mirrors (护心镜) with gold rims, joined by a strap
    if ap.get("mirrors", True):
        mc = ap.get("mirror_color", "steel_l")
        mm = flat_mat(st, "Mirror", mc, PL.deepen(mc, 0.55), power=0.9, blend=0.45)
        for side in (-1, 1):
            zc = ap.get("mirror_z", -1.36)
            xc = side * ap.get("mirror_x", 0.36)
            tc = float(Lt.t_of_x(xc, zc))
            Pc = Lt.point(zc, tc)
            Nc = Lt.normal(zc, tc)
            r = ap.get("mirror_r", 0.17)
            up = np.array([0, 0, 1.0])
            e1 = np.cross(up, Nc)
            e1 /= np.linalg.norm(e1)
            e2 = np.cross(Nc, e1)
            a = np.linspace(0, 2 * math.pi, 40, endpoint=False)
            rows = []
            for rk, hk in [(1.0, 0.045), (0.92, 0.06), (0.5, 0.075), (0.0, 0.08)]:
                rows.append(Pc + Nc * (ap.get("lift", 0.03) + hk) + r * rk *
                            (np.cos(a)[:, None] * e1 + np.sin(a)[:, None] * e2))
            Gm = np.array(rows)
            st.grid_mesh("Mirror%+d" % side, Gm[::-1], "hard", mm, closed=True, cap_top=False, M=M)
            st.tube("MirrorRim%+d" % side, np.concatenate([Gm[0], Gm[0][:1]]), 0.016, "hard", gold,
                    n=6, M=M)
            st.add_curve("mirror%+d" % side, "mirror", st.xf(M, Pc[None] + Nc[None] * 0.12),
                         r=r)
    # belt / strap across the chest (束甲绊)
    if ap.get("strap", True):
        sc = ap.get("strap_color", "cinnabar_d")
        smat = flat_mat(st, "Strap", sc, PL.deepen(sc, 0.6), power=1.2, blend=0.5)
        x = np.linspace(-0.62, 0.62, 30)
        z = ap.get("mirror_z", -1.36) + 0.21 + 0.06 * (x / 0.62) ** 2
        tt = Lt.t_of_x(x, z)
        P = Lt.point(z, tt) + Lt.normal(z, tt) * (ap.get("lift", 0.03) + 0.022)
        P2 = P + np.array([0, 0, -0.05])
        st.strip("Strap", P, P2, "band", smat, M=M)


def cloak(st, spec, cp):
    """A cloak (披风) over the shoulders: visible behind the shoulders and over the back."""
    Lt = st.torso_loft
    M = st.M_body
    col = cp.get("color", "cinnabar")
    cm = flat_mat(st, "Cloak", col, PL.deepen(col, 0.55), power=1.3, blend=0.55,
                  pattern=pattern_for(cp.get("pattern")))
    C = 80
    t0 = cp.get("t0", 1.25)
    t = np.linspace(t0, 2 * math.pi - t0, C)
    t = np.where(t > math.pi, t - 2 * math.pi, t)
    rows = []
    zs = np.linspace(-0.80, -2.1, 14)
    for k, z in enumerate(zs):
        a = k / (len(zs) - 1)
        P = Lt.point(np.full(C, z), t) + Lt.normal(np.full(C, z), t) * (0.09 + 0.10 * a)
        rows.append(P)
    G = np.array(rows)
    st.grid_mesh("Cloak", G, "cloth", cm, closed=False, M=M)


def shawl(st, spec, sp):
    """披帛: a long silk shawl over the shoulders, falling down the front at both sides."""
    Lt = st.torso_loft
    M = st.M_body
    col = sp.get("color", "malachite_l")
    sm = flat_mat(st, "Shawl", col, PL.deepen(col, 0.62), power=1.3, blend=0.55,
                  pattern=pattern_for(sp.get("pattern")))
    w = sp.get("w", 0.22)
    for side in (-1, 1):
        # centre line in (z, t): from behind the neck over the shoulder, down the front
        k = 30
        a = np.linspace(0, 1, k)
        t = side * (2.2 - 1.45 * a ** 0.9)
        z = -0.86 - 0.22 * np.sin(a * math.pi * 0.5) ** 1.5 - 0.75 * a ** 2.2
        P = Lt.point(z, t)
        N = Lt.normal(z, t)
        T = np.gradient(P, axis=0)
        T /= np.linalg.norm(T, axis=1, keepdims=True)
        S = np.cross(N, T)
        S /= np.linalg.norm(S, axis=1, keepdims=True)
        lift = 0.07 + 0.05 * a
        twist = np.cos(a * math.pi * 0.6)
        A = P + N * lift[:, None] + S * (w * 0.5 * twist)[:, None]
        Bp = P + N * lift[:, None] - S * (w * 0.5 * twist)[:, None]
        st.strip("Shawl%+d" % side, A, Bp, "cloth", sm, M=M)
