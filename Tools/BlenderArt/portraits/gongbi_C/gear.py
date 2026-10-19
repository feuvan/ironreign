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
    if cos.get("beads"):
        beads(st, spec, cos["beads"])
    if cos.get("kasaya"):
        kasaya(st, spec, cos["kasaya"])


# =============================================================================================
# helpers
# =============================================================================================
def hair_mat(st, color="hair"):
    c = PL.srgb(color)
    light = PL.mix(c, "ink_grey", 0.30) if sum(c) < 0.6 else c
    deep = PL.deepen(c, 0.55) if sum(c) >= 0.6 else PL.srgb("ink_d")
    return st.mat("Hair_" + PL.to_hex(c), light, deep, power=0.9, blend=0.5, lo=0.0, hi=1.0,
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
    hg = spec.get("headgear", {})
    covered = hg.get("kind") in ("helmet", "dongpo", "futou")
    if covered:
        # under a helmet / hat only the hair at the temples and the nape shows: stop the cap
        # just above the headgear's rim so it can never poke through
        rim = hg.get("brim_z", hg.get("base_z", 0.2))
        z1 = np.maximum(z0 + 0.02, np.full(C, rim + 0.06))
    vol = hp.get("volume", 0.02)
    top_vol = hp.get("top_volume", vol * 1.5)
    side_puff = hp.get("side_puff", 0.0)           # ladies: hair puffed over the temples (鬓)

    def off(a, z, tt):
        edge = geo.smoothstep(0.0, hp.get("edge_ramp", 0.32), a)   # thin at the hairline
        pe = geo.smoothstep(0.0, 0.55, a)            # the temple puff swells in gradually
        side = side_puff * np.exp(-((np.abs(tt) - hp.get("puff_t", 1.4)) / 0.42) ** 2) * \
            np.exp(-((z - hp.get("puff_z", 0.06)) / 0.16) ** 2)
        return 0.002 + edge * (vol + (top_vol - vol) * a) + side * pe
    if covered:
        vol = min(vol, 0.012)
        top_vol = min(top_vol, 0.012)
        side_puff = 0.0
    G = shell(L, (t, z0, z1), off, 22)
    cap = st.grid_mesh("HairCap", G, "hair", hm, closed=True, cap_top=not covered, M=st.M_head)
    st.fit.append(cap)
    st.hair_shell = (t, z0, z1, off)
    # hair-flow curves (combed strands) for the 2D stage: from the hairline up to the knot
    knot = np.array(hp.get("knot_at", (0.0, 0.10, crown - 0.02)))
    nfl = hp.get("flow_n", 46)
    for k in range(0 if covered else nfl):
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
    for i, b in enumerate([] if covered else hp.get("buns", default_buns(kind, crown))):
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
    hm = st.mat("Helmet", PL.mix(col, "steel_l", 0.2), PL.deepen(col, 0.72), power=2.2,
                blend=0.35, lo=0.25, hi=1.0)
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
    gm = flat_mat(st, "Hat", PL.mix(col, "ink_grey", 0.12), PL.deepen(col, 0.7), power=1.6,
                  blend=0.45,
                  pattern=pattern_for(hg.get("pattern", dict(kind="gauze", color="ink_grey",
                                                                     alpha=0.22, period=0.014))))
    base_z = hg.get("base_z", 0.19)
    back_drop = hg.get("back_drop", 0.07)
    C = 96
    t = np.linspace(-math.pi, math.pi, C, endpoint=False)
    zb = base_z - back_drop * (1 - np.cos(t)) * 0.5
    base = L.point(zb, t) + L.normal(zb, t) * 0.022
    cxy = np.array([0.0, 0.03])
    sq = hg.get("square", 3.6)
    d = base[:, :2] - cxy
    ang = np.arctan2(d[:, 1], d[:, 0])
    r0 = np.linalg.norm(d, axis=1)
    c_, s_ = np.cos(ang), np.sin(ang)
    rs = 1.0 / (np.abs(c_) ** sq + np.abs(s_) ** sq) ** (1 / sq)
    # half extents of the square section, from the head ring
    ex = np.abs(d[:, 0]).max() * hg.get("width_k", 0.97)
    ey = np.abs(d[:, 1]).max() * hg.get("depth_k", 0.92)
    rr = np.hypot(c_ * rs * ex, s_ * rs * ey)
    rr = np.maximum(rr, r0 + 0.012)            # the square section always encloses the head
    sqr = np.stack([c_ * rr, s_ * rr], -1)

    def ring(k, z, flare=1.0):
        P = np.zeros((C, 3))
        P[:, :2] = cxy + (d * (1 - k) + sqr * k) * flare
        P[:, 2] = z
        return P
    h_in = hg.get("h", 0.40)
    rows = [np.concatenate([base[:, :2], base[:, 2:]], 1),
            ring(0.7, base_z + 0.05, 1.0), ring(1.0, base_z + h_in * 0.5, 1.03),
            ring(1.0, base_z + h_in, 1.06)]
    rows[0] = base.copy()
    G = np.array(rows)
    sl = np.cumsum(np.r_[0, np.linalg.norm(np.diff(G[-1], axis=0), axis=1)])
    uv = np.stack(np.broadcast_arrays(sl[None, :], G[:, :1, 2] * np.ones((1, C))), -1)
    ob = st.grid_mesh("HatInner", G, "hard", gm, closed=True, cap_top=True, uv=uv, M=M)
    st.fit.append(ob)
    # outer wall: a little larger and lower, with a shallow notch at the front
    h_out = hg.get("h_out", 0.26)
    b2 = base.copy()
    b2[:, :2] = cxy + (b2[:, :2] - cxy) * 1.05
    b2[:, 2] -= 0.004
    rows = [b2, ring(0.75, base_z + 0.05, 1.06), ring(1.0, base_z + h_out, 1.10)]
    G2 = np.array(rows)
    front = np.abs(t) < 0.45
    G2[-1, front, 2] -= hg.get("notch", 0.035) * (1 - np.abs(t[front]) / 0.45)
    uv2 = np.stack(np.broadcast_arrays(sl[None, :], G2[:, :1, 2] * np.ones((1, C))), -1)
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


def headband(st, spec, hg):
    """抹额: a cloth band round the forehead (warriors, rogues, women warriors)."""
    L = st.head_loft
    M = st.M_head
    col = hg.get("color", "cinnabar")
    bm = flat_mat(st, "Headband", col, PL.deepen(col, 0.6), power=1.2, blend=0.5,
                  pattern=pattern_for(hg.get("pattern")))
    C = 96
    t = np.linspace(-math.pi, math.pi, C, endpoint=False)
    z0 = hg.get("z", 0.20) - 0.03 * (1 - np.cos(t)) * 0.5
    h = hg.get("h", 0.055)
    lift = hg.get("lift", 0.03)
    P0 = L.point(z0, t) + L.normal(z0, t) * lift
    P1 = L.point(z0 + h, t) + L.normal(z0 + h, t) * lift
    st.grid_mesh("Headband", np.stack([P0, P1], 0), "band", bm, closed=True, M=M)
    if hg.get("knot", True):
        # two tails behind the head
        for k, side in enumerate((-1, 1)):
            a = np.linspace(0, 1, 10)
            tt = math.pi * 0.92 * side
            base = L.point(np.array([z0[0] + h * 0.5]), np.array([tt]))[0] + np.array([0, 0.03, 0])
            P = base + np.stack([side * 0.05 * a, 0.06 * a, -0.30 * a ** 1.3], -1)
            A = P + np.array([0.0, 0.0, 0.0])
            Bp = P + np.array([side * 0.0, 0.0, 0.0]) + np.stack([np.full(10, 0.035), np.zeros(10), np.zeros(10)], -1)
            st.strip("BandTail%d" % k, A, Bp, "band", bm, M=M)
    if hg.get("jewel"):
        jc = hg["jewel"]
        jm = flat_mat(st, "Jewel_" + PL.to_hex(jc), jc, PL.deepen(jc, 0.6), power=1.0, blend=0.4)
        c = L.point(np.array([hg.get("z", 0.20) + h * 0.5]), np.array([0.0]))[0]
        c = c + L.normal(np.array([hg.get("z", 0.20) + h * 0.5]), np.array([0.0]))[0] * (lift + 0.012)
        st.ellipsoid("Jewel", c, (0.03, 0.012, 0.035), "hard", jm, M=M, n=(10, 14))


def fur_hat(st, spec, hg):
    """Steppe hat: a rounded felt crown with a thick fur brim and a tassel."""
    L = st.head_loft
    M = st.M_head
    col = hg.get("color", "ochre_d")
    fur = hg.get("fur", "#8A6A48")
    cm = flat_mat(st, "FeltCrown", col, PL.deepen(col, 0.6), power=1.4, blend=0.5)
    fm = flat_mat(st, "Fur", fur, PL.deepen(fur, 0.55), power=0.9, blend=0.55)
    base_z = hg.get("base_z", 0.17)
    C = 96
    t = np.linspace(-math.pi, math.pi, C, endpoint=False)
    crown = spec.get("head", {}).get("crown", 0.5)
    rows = []
    for i, z in enumerate(np.linspace(base_z, crown - 0.004, 14)):
        a = i / 13
        P = L.point(np.full(C, z), t) + L.normal(np.full(C, z), t) * (0.05 + 0.03 * math.sin(a * math.pi))
        P[:, 2] += hg.get("peak", 0.10) * a ** 1.8
        rows.append(P)
    G = np.array(rows)
    ob = st.grid_mesh("FeltCrown", G, "hard", cm, closed=True, cap_top=True, M=M)
    st.fit.append(ob)
    # fur brim: a fat rolled ring
    zr = base_z + 0.02
    ring = L.point(np.full(C, zr), t) + L.normal(np.full(C, zr), t) * 0.07
    ring = np.concatenate([ring, ring[:1]])
    st.tube("FurBrim", ring, hg.get("brim_r", 0.06), "hair", fm, n=12, M=M)
    st.add_curve("fur", "fur", st.xf(M, ring), r=hg.get("brim_r", 0.06), color=fur)
    top = G[-1].mean(0)
    if hg.get("tassel", True):
        st.add_curve("tassel", "tassel", st.xf(M, (top + np.array([0, 0, 0.02]))[None]),
                     color=hg.get("tassel_color", "cinnabar"), length=hg.get("tassel_len", 0.14))
        st.fit.append(st.xf(M, (top + np.array([0, 0, 0.12]))[None]))


HEADGEAR = dict(helmet=helmet, dongpo=dongpo, futou=futou, guan=guan, headband=headband,
                fur_hat=fur_hat)


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
    top_z = ap.get("top_z", -0.80)
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
    ring2 = Lt.point(np.full(C, top_z + 0.13), t) + Lt.normal(np.full(C, top_z + 0.13), t) * 0.022
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
    """披帛: a long silk shawl over the shoulders, falling down the front of the arms."""
    Lt = st.torso_loft
    M = st.M_body
    col = sp.get("color", "malachite_l")
    sm = flat_mat(st, "Shawl", col, PL.deepen(col, 0.62), power=1.3, blend=0.55,
                  pattern=pattern_for(sp.get("pattern")))
    w = sp.get("w", 0.28)
    tp = dict(geo.TORSO_DEFAULT, **spec.get("torso", {}))
    sz = tp["shoulder_z"]
    for side in (-1, 1):
        k = 34
        a = np.linspace(0, 1, k)
        t = side * geo.pchip([0, 0.35, 0.6, 1.0], [2.5, 1.62, 1.32, 1.08], a)
        z = geo.pchip([0, 0.35, 0.6, 1.0], [sz + 0.12, sz + 0.06, sz - 0.18, -1.95], a)
        P = Lt.point(z, t)
        N = Lt.normal(z, t)
        T = np.gradient(P, axis=0)
        T /= np.linalg.norm(T, axis=1, keepdims=True)
        S = np.cross(N, T)
        S /= np.linalg.norm(S, axis=1, keepdims=True)
        lift = sp.get("lift", 0.035) + 0.03 * a
        ww = w * (0.75 + 0.25 * np.sin(a * math.pi))
        A = P + N * lift[:, None] + S * (ww * 0.5)[:, None]
        Bp = P + N * lift[:, None] - S * (ww * 0.5)[:, None]
        st.strip("Shawl%+d" % side, A, Bp, "cloth", sm, M=M)


def beads(st, spec, bp):
    """Prayer beads (念珠) round the neck: a 3D loop the 2D stage draws as beads."""
    Lt = st.torso_loft
    M = st.M_body
    n = 90
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    # a loop round the neck base hanging lower at the front
    t = a - math.pi
    z = -0.78 - bp.get("drop", 0.42) * (0.5 + 0.5 * np.cos(t)) ** 1.5
    P = Lt.point(z, t) + Lt.normal(z, t) * 0.05
    st.add_curve("beads", "beads", st.xf(M, P), r=bp.get("r", 0.028),
                 color=bp.get("color", "#5A3A26"))


def kasaya(st, spec, kp):
    """袈裟: a patched mantle over the left shoulder, crossing the chest diagonally."""
    Lt = st.torso_loft
    M = st.M_body
    col = kp.get("color", "cinnabar")
    km = flat_mat(st, "Kasaya", col, PL.deepen(col, 0.6), power=1.3, blend=0.55,
                  pattern=pattern_for(dict(kind="lamellar", w=0.22, h=0.18, light=col,
                                           lace=col, lace_a=0.0, seam="gold_d", seam_a=0.6,
                                           plate_shade=0.08)))
    k = 30
    a = np.linspace(0, 1, k)
    s = kp.get("side", 1)
    # upper edge: from the back over the +X shoulder, down across the chest to the -X side
    t_up = s * geo.pchip([0, 0.3, 1.0], [2.4, 1.2, -1.2], a)
    z_up = geo.pchip([0, 0.3, 1.0], [-0.95, -0.92, -1.75], a)
    P = Lt.point(z_up, t_up) + Lt.normal(z_up, t_up) * 0.03
    Q = P.copy()
    Q[:, 2] -= 0.9
    st.strip("Kasaya", P, Q, "cloth", km, M=M)
