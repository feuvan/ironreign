"""Hair, headgear and costume pieces for the gongbi_C bust (Blender side).

Everything is parametric and shares two surfaces: the head (:class:`b_body.Head`, head-local,
parented to the head rig so it follows the pose) and the torso (:class:`b_body.Torso`, bust
space).  Pieces sit on those surfaces with an offset, so any head shape or body build wears any
hat, hair style or armour.

Hair      cap (hairline from the canon), topknot, ladies' high buns / loops / temple puffs
Headgear  helmet (兜鍪: bowl, brow band, ridge, finial, red tassel plume, neck guard), scholar's
          Dongpo hat (东坡巾), futou (幞头), small crown (小冠) with hairpin, monk / taoist caps
Costume   lamellar armour (札甲) with shoulder guards (披膊) and chest mirrors (护心镜), cloak
          (披风), lady's shawl (披帛), earrings, hairpins, combs, dangling 步摇
"""

import math

import numpy as np

import b_body as BB
import b_mats as MT
import b_mesh as M
from looks import PAL, deepen, mix


# =============================================================================================
# head surface helpers (head-local)
# =============================================================================================
def head_pt(H, alpha, z, off=0.0):
    """Head-local point(s) on the head at angle alpha / height z, pushed ``off`` along the normal."""
    alpha = np.asarray(alpha, np.float64)
    z = np.broadcast_to(np.asarray(z, np.float64), alpha.shape)
    P = _ring_pts(H, alpha, z)
    if np.any(np.asarray(off) != 0):
        e = 1e-3
        Pa = _ring_pts(H, alpha + e, z) - _ring_pts(H, alpha - e, z)
        zt = np.clip(z + e, None, H.K[0, 0] * H.s - 1e-4)
        zb = z - e
        Pz = _ring_pts(H, alpha, zt) - _ring_pts(H, alpha, zb)
        N = np.cross(Pz, Pa)
        N /= np.maximum(np.linalg.norm(N, axis=-1, keepdims=True), 1e-12)
        # outward check: away from the head axis
        outv = P - np.stack([np.zeros_like(z), np.zeros_like(z), z], -1)
        sgn = np.sign(np.sum(N * outv, -1, keepdims=True))
        sgn[sgn == 0] = 1
        N = N * sgn
        P = P + N * np.asarray(off)[..., None]
    return P


def _ring_pts(H, alpha, z):
    alpha = np.asarray(alpha, np.float64)
    z = np.broadcast_to(np.asarray(z, np.float64), alpha.shape)
    return H.ring(z, alpha)


def hairline_z(H, alpha, hl, ears=True):
    """Height of the hair edge round the head (head-local, scaled) at angle alpha.

    hl: top (front centre), temple_u, temple_v (temple corner), side_v (sideburn bottom),
    nape (back), ear (hair line above the ear)"""
    s = H.s
    a = np.abs(np.asarray(alpha, np.float64))
    top = hl.get("top", 0.075)
    tv = hl.get("temple_v", 0.028)
    sv = hl.get("side_v", -0.020)
    ear = hl.get("ear_z", 0.016 if ears else sv)
    nape = hl.get("nape", -0.075)
    knots_a = np.radians([0, 22, 40, 52, 60, 66, 74, 84, 96, 108, 122, 140, 180])
    knots_z = np.array([top, top - 0.004, top - 0.020, tv + 0.008, tv, (tv + sv) / 2, sv,
                        ear, ear, (ear + nape) / 2 + 0.01, nape + 0.01, nape, nape])
    if hl.get("widow"):
        knots_z[0] -= hl["widow"]
    return M.pchip(knots_a, knots_z, np.clip(a, 0, math.pi)) * s


def hair_cap(st, H, hl, mat, name="HairCap", thick=0.006, crown_extra=0.012, back_extra=0.010,
             na=120, ns=26, ears=True, part=0.0):
    """Hair cap from the hairline up to the crown, conforming to the head (smooth edge)."""
    a = np.linspace(-math.pi, math.pi, na, endpoint=False)
    zt = H.K[0, 0] * H.s
    zh = hairline_z(H, a, hl, ears)
    s = np.linspace(0, 1, ns)
    S_, A_ = np.meshgrid(s, a, indexing="ij")
    Z = zh[None, :] + (zt - 0.002 - zh[None, :]) * (1 - (1 - S_) ** 1.6)
    edge = M.smoothstep(0.0, 0.18, S_)
    back = M.smoothstep(0.3, 1.0, -np.cos(A_))
    top = M.smoothstep(0.4, 1.0, S_)
    off = (0.0008 + thick * edge + crown_extra * top * edge + back_extra * back * edge)
    if part:
        # a centre parting: a shallow groove along alpha = 0 on the top
        off = off - part * np.exp(-(A_ / 0.08) ** 2) * top
    P = head_pt(H, A_, Z, off)
    UV = np.stack([A_ * 0.08, S_ * 0.15], -1)
    obj = M.grid_object(name, P, st.col("hair"), wrap=True, cap_bottom=True, uv=UV, mat=mat,
                        parent=st.rig)
    # close the crown hole
    M.fix_normals(obj, (0, 0, 0))
    return obj


def hair_mat(color="hair", name="PC_Hair", streak=0.22):
    light = {"hair": "#3A3430", "grey": "#8A847C", "white": "#E4DED2", "brown": "#4A3A2E"}.get(color, color)
    deep = {"hair": "#141110", "grey": "#5A554E", "white": "#A8A298", "brown": "#241A14"}.get(color, deepen(light, 0.5))
    sc = {"hair": "#6E665E", "grey": "#B8B2A8", "white": "#FFFFFF", "brown": "#7A6A5A"}.get(color, "#6E665E")
    return MT.wash(name + "_" + str(color).strip("#"), light, deep, region="hair", hair=1, blend=0.35,
                   lo=0.05, hi=1.0, power=0.8, form=0.06,
                   pattern=MT.streaks(freq=200.0, color=sc, alpha=streak, mode="uv", warp=0.15))


def gold_mat(name="PC_Gold", light="gold", deep="gold_d"):
    return MT.wash(name, light, deep, region="gold", blend=0.45, lo=0.05, hi=1.0, form=0.10)


def flat_mat(name, color, region, deep=None, blend=0.45, **kw):
    return MT.wash(name, color, deep or deepen(color, 0.62), region=region, blend=blend, lo=0.06,
                   hi=1.0, **kw)


# =============================================================================================
# hair styles
# =============================================================================================
def hair(st, H, h, spec):
    style = h.get("style", "none")
    if style == "none":
        return
    f = spec.get("face", {})
    hl = dict(f.get("hairline", {}))
    hl.update(h.get("hairline", {}))
    col = h.get("color", "hair")
    mat = hair_mat(col)
    gear = spec.get("headgear", {}).get("kind")
    if style in ("topknot", "lady_high", "lady_loops", "bun_low", "loose", "elder_bun"):
        hair_cap(st, H, hl, mat, thick=h.get("thick", 0.005), crown_extra=h.get("crown", 0.010),
                 back_extra=h.get("back", 0.008), ears=h.get("ears_free", True), part=h.get("part", 0.0))
    s = H.s
    if style != "none" and gear != "helmet":
        # the hairline for the 2D temple strokes: on the head, and a little way up the scalp
        a = np.linspace(-1.32, 1.32, 90)
        zh = hairline_z(H, a, hl, h.get("ears_free", True))
        # strokes lie just over the cap (its edge thickens over the first few mm)
        th = h.get("thick", 0.005)
        base = head_pt(H, a, zh + 0.0004 * s, 0.0016 * s)
        up = head_pt(H, a, zh + h.get("strand_len", 0.012) * s, (0.0008 + th + 0.0022) * s)
        hc = {"hair": "#1C1814", "grey": "#6E6860", "white": "#F2EEE6", "brown": "#2A1E16"}.get(col, col)
        st.add_curve("hairline", "hairline", base, head_local=True, color=hc, light=col in ("white", "grey"),
                     n=h.get("strands", 170))
        st.add_curve("hairline_up", "hairline_up", up, head_local=True)
    if style == "bun_low":
        bc = np.array([0.0, 0.080 * s, -0.004 * s])
        M.ellipsoid("BunLow", bc, (0.036 * s, 0.028 * s, 0.030 * s), st.col("hair"), mat=mat, parent=st.rig)
        if h.get("pin", True):
            pin = np.stack([bc + np.array([-0.05, -0.004, 0.01]) * s, bc + np.array([0.05, 0.004, 0.02]) * s])
            M.tube("BunPin", M.resample(pin, 6), 0.0018 * s, st.col("gear"), n_around=8,
                   mat=gold_mat() if h.get("pin") != "jade" else jade_mat(), parent=st.rig)
    if style in ("topknot", "elder_bun"):
        if gear in ("dongpo", "futou", "helmet", "hood", "fur_hat"):
            return
        c = np.array([0.0, 0.012, H.top + 0.010 * s])
        M.ellipsoid("TopKnot", c, (0.024 * s, 0.022 * s, 0.020 * s), st.col("hair"), mat=mat,
                    parent=st.rig)
    elif style in ("lady_high", "lady_loops"):
        lady_hair(st, H, h, mat)


def lady_hair(st, H, h, mat):
    """High court hairstyle: temple puffs (鬓), a high bun and two loops, comb, pins, 步摇."""
    s = H.s
    col = st.col("hair")
    top = H.top
    # temple puffs (鬓): soft volumes over the upper ear, sweeping back into the cap
    for side in (-1, 1):
        c = head_pt(H, np.array([side * 1.30]), np.array([0.016 * s]), np.array([0.006 * s]))[0]
        M.ellipsoid("Puff%+d" % side, c + np.array([side * 0.004, 0.008, 0.0]) * s,
                    (0.022 * s, 0.042 * s, 0.032 * s), col, mat=mat, parent=st.rig,
                    rot=M.rot_xyz(0.30, side * -0.30, side * 0.20))
    # high bun (高髻): a broad lower bun and a smaller upper knot leaning forward
    bun_c = np.array([0.0, 0.016 * s, top + 0.020 * s])
    M.ellipsoid("Bun", bun_c, (0.050 * s, 0.044 * s, 0.034 * s), col, mat=mat, parent=st.rig,
                rot=M.rot_xyz(-0.30, 0, 0))
    up_c = bun_c + np.array([0.0, -0.006, 0.032]) * s
    M.ellipsoid("BunTop", up_c, (0.040 * s, 0.034 * s, 0.036 * s), col, mat=mat, parent=st.rig,
                rot=M.rot_xyz(0.40, 0, 0))
    if h.get("loops"):
        for side in (-1, 1):
            t = np.linspace(0.0, math.pi, 28)
            R = 0.026 * s
            base = up_c + np.array([side * 0.016 * s, 0.0, 0.010 * s])
            path = np.stack([side * (R * 0.6 - np.cos(t) * R * 0.6), np.sin(t) * R * 0.1, np.sin(t) * R * 1.1], -1)
            path = path @ M.rot_xyz(-0.2, side * 0.35, 0).T + base
            M.tube("Loop%+d" % side, path, 0.012 * s * (1 - 0.2 * np.sin(t)), col, n_around=14,
                   mat=mat, parent=st.rig)
    orn = h.get("ornaments", {})
    gold = gold_mat()
    # comb (梳) on the front of the bun: a gold half disc with a pattern band
    if orn.get("comb", True):
        cc = bun_c + np.array([0.0, -0.040 * s, 0.004 * s])
        ang = np.linspace(0.15, math.pi - 0.15, 30)
        inner = cc + np.stack([np.cos(ang) * 0.016, np.full_like(ang, -0.002), np.sin(ang) * 0.010 - 0.004], -1) * s / 1.0
        outer = cc + np.stack([np.cos(ang) * 0.032, np.full_like(ang, -0.004), np.sin(ang) * 0.024 - 0.004], -1) * s / 1.0
        M.strip("Comb", outer, inner, st.col("gear"), parent=st.rig,
                mat=MT.wash("PC_Comb", "gold_l", "gold_d", region="gold", blend=0.45, lo=0.05, hi=1.0,
                            pattern=MT.brocade(period=0.008, width=0.018, motif="#B5382A", edge="#8A6A2A",
                                               kind="dots", size=0.35)))
    # hairpins (簪): long gold pins with flower heads, slanting through the bun
    pins = orn.get("pins", [(-1, 0.6), (1, 0.5), (1, -0.4)])
    for i, (side, ang) in enumerate(pins):
        a0 = bun_c + np.array([side * 0.034 * s, -0.012 * s, 0.016 * s])
        d = np.array([side * math.cos(ang) * 0.8, -0.25, math.sin(ang) * 0.6])
        d /= np.linalg.norm(d)
        path = np.stack([a0 - d * 0.03 * s, a0 + d * 0.035 * s])
        M.tube("Pin%d" % i, M.resample(path, 6), 0.0016 * s, st.col("gear"), n_around=8, mat=gold,
               parent=st.rig)
        head = a0 + d * 0.037 * s
        flower(st, head, 0.012 * s, orn.get("flower_color", "cinnabar"), "Pf%d" % i, d)
        if orn.get("buyao", True) and i == 0:
            # dangling strings of beads (步摇) from the first pin head
            for j in range(3):
                start = head + np.array([side * 0.004 * (j - 1), -0.002, -0.004]) * s
                pts = [start + np.array([0, 0, -0.008 * k]) * s for k in range(6)]
                st.add_curve("buyao%d_%d" % (i, j), "chain", np.array(pts), head_local=True,
                             color="#C9A24B", w=0.55)
                for k in (2, 4, 5):
                    M.ellipsoid("Bead%d%d%d" % (i, j, k), pts[k], (0.0022 * s,) * 3, st.col("fine"),
                                mat=pearl_mat() if k != 5 else jade_mat(), parent=st.rig, n=(10, 8))
    # a peony beside the bun
    if orn.get("peony", True):
        ps_ = orn.get("peony_side", -1)
        pc = bun_c + np.array([ps_ * 0.046 * s, -0.020 * s, -0.004 * s])
        flower(st, pc, 0.030 * s, orn.get("peony_color", "rouge"), "Peony", np.array([ps_ * 0.5, -0.85, 0.25]),
               petals=8, layers=3)


def pearl_mat():
    return MT.wash("PC_Pearl", "pearl", "#C8C0B4", region="pearl", blend=0.5, lo=0.05, hi=1.0, form=0.12)


def jade_mat():
    return MT.wash("PC_Jade", "jade", "malachite_d", region="jade", blend=0.5, lo=0.05, hi=1.0, form=0.1)


def flower(st, c, r, color, name, normal, petals=5, layers=2):
    """A small flower of petal ellipsoids around a centre (hairpin heads, peonies)."""
    n = np.asarray(normal, np.float64)
    n /= np.linalg.norm(n)
    a = np.cross(n, [0, 0, 1.0])
    if np.linalg.norm(a) < 1e-6:
        a = np.array([1.0, 0, 0])
    a /= np.linalg.norm(a)
    b = np.cross(n, a)
    light = PAL.get(color, color)
    mat = MT.wash("PC_Flower_" + str(color).strip("#"), mix(light, "white", 0.35), light,
                  region="flower", blend=0.55, lo=0.0, hi=1.0, form=0.06)
    for L in range(layers):
        rr = r * (1 - 0.3 * L)
        for i in range(petals):
            t = 2 * math.pi * (i + 0.5 * L) / petals
            d = a * math.cos(t) + b * math.sin(t)
            pc = c + d * rr * 0.55 + n * (0.15 * rr * L)
            R = np.stack([d, np.cross(n, d), n], 1)
            M.ellipsoid("%s_p%d_%d" % (name, L, i), pc, (rr * 0.55, rr * 0.34, rr * 0.12),
                        st.col("fine"), mat=mat, parent=st.rig, n=(12, 8), rot=R)
    M.ellipsoid(name + "_c", c + n * r * 0.3, (r * 0.2,) * 3, st.col("fine"), mat=gold_mat(),
                parent=st.rig, n=(10, 8))


# =============================================================================================
# headgear
# =============================================================================================
def headgear(st, H, g, spec):
    k = g["kind"]
    if k == "helmet":
        helmet(st, H, g)
    elif k == "dongpo":
        dongpo(st, H, g)
    elif k == "crown":
        small_crown(st, H, g)
    elif k == "headband":
        headband(st, H, g)
    elif k == "fur_hat":
        fur_hat(st, H, g)
    elif k == "futou":
        futou(st, H, g)


def headband(st, H, g):
    """抹额 / 头巾: a cloth band round the forehead tied at the back, the tails hanging."""
    s = H.s
    col = g.get("color", "cinnabar")
    mat = MT.wash("PC_Headband_" + str(col).strip("#"), col, deepen(col, 0.6), region="hat", blend=0.45,
                  lo=0.05, hi=1.0, form=0.08)
    a = np.linspace(-math.pi, math.pi, 96, endpoint=False)
    zc = (g.get("z", 0.040) - 0.022 * M.smoothstep(0.3, 2.6, np.abs(a))) * s
    w = g.get("width", 0.016) * s
    top = head_pt(H, a, zc + w / 2, 0.0060 * s)
    bot = head_pt(H, a, zc - w / 2, 0.0065 * s)
    M.strip("Headband", np.concatenate([top, top[:1]]), np.concatenate([bot, bot[:1]]), st.col("band"),
            mat=mat, parent=st.rig)
    knot = head_pt(H, np.array([math.pi]), np.array([zc.min()]), np.array([0.008 * s]))[0]
    for side in (-1, 1):
        pts = np.array([knot + np.array([side * 0.003 * k, 0.004 * k * (1 - k / 10), -0.014 * k]) * s
                        for k in range(8)])
        ww = np.array([0, 0, 1.0]) * w * 0.4
        M.strip("BandTail%+d" % side, pts - ww + np.array([side * 0.004 * s, 0, 0]), pts + ww, st.col("band"),
                mat=mat, parent=st.rig)


def fur_hat(st, H, g):
    """Steppe hat: a thick rolled fur brim and a cloth crown with a tassel."""
    s = H.s
    fur = MT.wash("PC_Fur", g.get("fur", "#8A6A4A"), "#4A3424", region="fur", blend=0.4, lo=0.0, hi=1.0,
                  form=0.12, pattern=MT.streaks(freq=320.0, color="#C8A880", alpha=0.4, warp=0.2))
    cloth = MT.wash("PC_FurCrown", g.get("color", "#9A3A2A"), deepen(g.get("color", "#9A3A2A"), 0.55),
                    region="hat", blend=0.45, lo=0.05, hi=1.0, form=0.1)
    a = np.linspace(-math.pi, math.pi, 72, endpoint=False)
    zc = (0.040 - 0.016 * M.smoothstep(0.3, 2.6, np.abs(a))) * s
    path = head_pt(H, a, zc, 0.014 * s)
    path = np.concatenate([path, path[:1]])
    M.tube("FurBrim", path, 0.017 * s, st.col("hair"), n_around=14, mat=fur, parent=st.rig, cap=False)
    ring0 = head_pt(H, a, zc + 0.012 * s, 0.016 * s)
    rows = []
    for t in np.linspace(0, 1, 14):
        c = ring0.mean(0)
        r = (1 - t ** 2.2) * 1.0 + 0.0
        P = ring0.copy()
        P[:, :2] = c[:2] + (ring0[:, :2] - c[:2]) * max(r, 0.02)
        P[:, 2] = ring0[:, 2] * (1 - t) + (H.top + 0.040 * s) * t
        rows.append(P)
    Pm = np.stack(rows)
    M.grid_object("FurCrown", Pm, st.col("gear"), wrap=True, mat=cloth, parent=st.rig)


def futou(st, H, g):
    """幞头: an official's black cap with a raised back and two long stiff wings."""
    s = H.s
    lac = MT.wash("PC_Futou", g.get("color", "#2E2A28"), "#0E0C0C", region="hat", blend=0.4, lo=0.05,
                  hi=1.0, form=0.12)
    na = 96
    a = np.linspace(-math.pi, math.pi, na, endpoint=False)
    zb = (0.040 - 0.020 * M.smoothstep(0.4, 1.6, np.abs(a))) * s
    zt = H.K[0, 0] * s
    rows = []
    for t in np.linspace(0, 1, 18):
        z = zb + (zt - zb) * (1 - (1 - t) ** 1.5)
        rows.append(head_pt(H, a, np.minimum(z, zt - 0.001), (0.006 + 0.004 * t) * s))
    P = np.stack(rows)
    M.grid_object("FutouCap", P, st.col("gear"), wrap=True, cap_top=True, mat=lac, parent=st.rig)
    # raised back knot
    kc = np.array([0.0, 0.040 * s, H.top + 0.008 * s])
    M.ellipsoid("FutouKnot", kc, (0.040 * s, 0.026 * s, 0.040 * s), st.col("gear"), mat=lac, parent=st.rig)
    for side in (-1, 1):
        root = kc + np.array([side * 0.030, 0.012, -0.012]) * s
        tip = root + np.array([side * g.get("wing", 0.14), 0.02, 0.004]) * s
        path = M.resample(np.stack([root, tip]), 10)
        w = np.array([0, 0, 0.012]) * s
        M.strip("FutouWing%+d" % side, path - w, path + w, st.col("gear"), mat=lac, parent=st.rig)


def helmet(st, H, g):
    """兜鍪: iron bowl over the brow band, gold rims and ridge, finial with a red tassel, flaring
    neck guard (顿项) of lamellae over the ears and nape."""
    s = H.s
    iron = MT.wash("PC_HelmIron", g.get("color", "#59646E"), g.get("deep", "#2A3038"), region="helmet",
                   blend=0.40, lo=0.05, hi=1.0, power=0.9, form=0.12)
    gold = gold_mat()
    na, ns = 120, 30
    a = np.linspace(-math.pi, math.pi, na, endpoint=False)
    # rim: low over the brows, lower at the sides and back
    rim = (0.040 - 0.020 * M.smoothstep(0.3, 1.6, np.abs(a)) - 0.012 * M.smoothstep(1.6, 2.6, np.abs(a))) * s
    zt = H.K[0, 0] * H.s
    S_ = np.linspace(0, 1, ns)[:, None]
    Z = rim[None, :] + (zt - 0.001 - rim[None, :]) * (1 - (1 - S_) ** 1.5)
    A_ = np.broadcast_to(a[None, :], Z.shape)
    off = (0.014 + 0.010 * M.smoothstep(0.5, 1.0, S_)) * s * np.ones_like(Z)
    P = head_pt(H, A_, Z, off)
    # a slight peak on top
    P[..., 2] += 0.014 * s * M.smoothstep(0.55, 1.0, S_) ** 2
    bowl = M.grid_object("HelmBowl", P, st.col("gear"), wrap=True, cap_bottom=True, mat=iron,
                         parent=st.rig, uv=np.stack([A_ * 0.09, Z], -1))
    # brow band (眉庇) and rim band in gold
    band_top = head_pt(H, a, rim + 0.012 * s, 0.0165 * s)
    band_bot = head_pt(H, a, rim - 0.001 * s, 0.0175 * s)
    M.strip("HelmBand", np.concatenate([band_top, band_top[:1]]), np.concatenate([band_bot, band_bot[:1]]),
            st.col("gear"), mat=gold)
    # visor: a narrow brim over the brows
    fa = np.linspace(-1.15, 1.15, 40)
    rimf = np.interp(fa, a, rim)
    v_in = head_pt(H, fa, rimf, 0.017 * s)
    v_out = v_in + np.stack([np.sin(fa) * 0.012 * s, -np.cos(fa) * 0.020 * s, np.full_like(fa, -0.004 * s)], -1)
    M.strip("HelmVisor", v_in, v_out, st.col("gear"), mat=gold)
    # ridge front-to-back over the top
    rz = np.linspace(rim[na // 2] + 0.01 * s, zt - 0.003, 26)
    rp = head_pt(H, np.zeros_like(rz), rz, 0.026 * s)
    rp[:, 2] += 0.014 * s * M.smoothstep(0.55, 1.0, (rz - rz[0]) / (rz[-1] - rz[0])) ** 2
    M.tube("HelmRidge", rp, 0.0032 * s, st.col("gear"), n_around=8, mat=gold, parent=st.rig)
    # finial and plume holder
    top = np.array([0.0, 0.006 * s, zt + 0.034 * s])
    prof = [(0.0, 0.052), (0.004, 0.050), (0.006, 0.040), (0.012, 0.030), (0.010, 0.022),
            (0.016, 0.014), (0.018, 0.006), (0.020, 0.0)]
    prof = [(r * s, z * s) for r, z in prof]
    M.lathe("HelmFinial", prof, st.col("gear"), n_around=24, mat=gold,
            center=(0, 0.006 * s, zt + 0.004 * s), parent=st.rig)
    # red tassel plume (盔缨): a cone of hair bursting from the finial, drooping back
    plume(st, H, top + np.array([0, 0, 0.046 * s]), g.get("plume", "cinnabar"), s)
    # neck guard (顿项): a bell skirt of lamellae hanging from the rim at the sides and back,
    # its front edges falling straight down beside the cheeks
    open_front = g.get("open", 1.12)
    ga = np.linspace(open_front, 2 * math.pi - open_front, 90)
    ga = np.where(ga > math.pi, ga - 2 * math.pi, ga)
    zr = np.interp(ga, a, rim) - 0.004 * s
    rim_p = head_pt(H, ga, zr, 0.018 * s)
    radial = np.stack([np.sin(ga), -np.cos(ga), np.zeros_like(ga)], -1)
    nz = 16
    t = np.linspace(0, 1, nz)[:, None]
    back = M.smoothstep(1.3, 2.6, np.abs(ga))[None, :]
    drop = (0.112 + 0.035 * back) * s
    flare = (0.008 + 0.034 * t ** 1.4 + 0.010 * back * t) * s
    Pg = rim_p[None] + radial[None] * flare[..., None] - np.array([0, 0, 1.0]) * (drop * t)[..., None]
    lam = MT.wash("PC_HelmGuard", g.get("guard", "#4E5A66"), "#262C34", region="helmet", blend=0.4,
                  lo=0.05, hi=1.0, form=0.10,
                  pattern=MT.lamellae(ph=0.020, pw=0.014, lace=g.get("lace", "#A8382A")))
    seg = np.linalg.norm(np.diff(Pg[0], axis=0), axis=1)
    U = np.concatenate([[0], np.cumsum(seg)])[None, :] * np.ones((nz, 1))
    M.grid_object("HelmGuard", Pg, st.col("armour"), wrap=False, mat=lam, parent=st.rig,
                  uv=np.stack([U, Pg[..., 2]], -1))
    # gold edge along the guard's hem and front edges
    hem_i = Pg[-1]
    hem_o = Pg[-1] - np.array([0, 0, 0.010 * s]) + radial * 0.004 * s
    M.strip("HelmGuardHem", hem_i, hem_o, st.col("gear"), mat=gold, parent=st.rig)
    return bowl


def plume(st, H, base, color, s, n=90, seed=3):
    """Red tassel (盔缨): strands burst from the finial and fall back and down like a fountain,
    painted in 2D over a soft red core."""
    rng = np.random.default_rng(seed)
    core = MT.wash("PC_Plume", color, deepen(color, 0.55), region="plume", blend=0.5, lo=0.0, hi=1.0, form=0.05)
    M.ellipsoid("PlumeCore", base + np.array([0, 0.010, 0.006]) * s, (0.020 * s, 0.026 * s, 0.014 * s),
                st.col("none"), mat=core, parent=st.rig)
    for i in range(n):
        ang = rng.uniform(-math.pi, math.pi)
        L = rng.uniform(0.045, 0.075) * s
        d0 = np.array([math.cos(ang) * 0.55, 0.25 + math.sin(ang) * 0.45, rng.uniform(0.55, 0.9)])
        d0 /= np.linalg.norm(d0)
        p = base + np.array([math.cos(ang), math.sin(ang), 0]) * 0.004 * s
        pts = [p.copy()]
        v = d0 * L / 12
        for k in range(12):
            v = v + np.array([0, 0.0012, -0.0024]) * s * (0.4 + k / 12)
            p = p + v
            pts.append(p.copy())
        r = rng.random()
        col = color if r > 0.35 else (deepen(color, 0.62) if r > 0.1 else mix(color, "white", 0.3))
        st.add_curve("plume%d" % i, "strand", np.array(pts), head_local=True, color=col,
                     w=rng.uniform(0.8, 1.2), a=0.92, test=True)


def _squared(ring, k=0.5, n=4.0):
    """Push a closed ring (N, 3) towards a rounded box of the same extents (k = 0..1)."""
    c = ring.mean(0)
    d = ring[:, :2] - c[:2]
    hx, hy = np.abs(d[:, 0]).max(), np.abs(d[:, 1]).max()
    th = np.arctan2(d[:, 1], d[:, 0])
    rb = 1.0 / ((np.abs(np.cos(th)) / hx) ** n + (np.abs(np.sin(th)) / hy) ** n) ** (1.0 / n)
    r = np.linalg.norm(d, axis=1)
    rr = r + (rb - r) * k
    out = ring.copy()
    out[:, 0] = c[0] + np.cos(th) * rr
    out[:, 1] = c[1] + np.sin(th) * rr
    return out


def dongpo(st, H, g):
    """Scholar's tall square hat (东坡巾): an inner tall crown and a lower outer panel of black
    gauze over a dark band (both fitted to this head), two ribbons hanging behind."""
    s = H.s
    gauze = MT.wash("PC_Gauze", g.get("color", "#3A3634"), "#121010", region="hat", blend=0.38,
                    lo=0.05, hi=1.0, form=0.10, pattern=MT.gauze(color="#6A6460", alpha=0.16))
    band = MT.wash("PC_HatBand", "#2A2624", "#0E0C0C", region="hat", blend=0.4, lo=0.05, hi=1.0, form=0.08)
    na = 96
    a = np.linspace(-math.pi, math.pi, na, endpoint=False)
    zb = (g.get("front", 0.036) - 0.020 * M.smoothstep(0.4, 1.5, np.abs(a))
          - 0.004 * M.smoothstep(1.6, 3.0, np.abs(a))) * s
    base = head_pt(H, a, zb, 0.004 * s)
    btop = head_pt(H, a, zb + 0.016 * s, 0.0055 * s)
    M.strip("HatBand", np.concatenate([btop, btop[:1]]), np.concatenate([base, base[:1]]),
            st.col("gear"), mat=band, parent=st.rig)
    top_z = zb.max() + 0.016 * s + g.get("height", 0.095) * s
    ring0 = _squared(head_pt(H, a, zb + 0.016 * s, 0.0050 * s), 0.35)
    rows = []
    for t in np.linspace(0, 1, 16):
        c = ring0.mean(0)
        r = 1.0 - 0.10 * t
        P = ring0.copy()
        P[:, :2] = c[:2] + (ring0[:, :2] - c[:2]) * r
        P[:, 2] = ring0[:, 2] * (1 - t) + top_z * t
        rows.append(P)
    Pm = np.stack(rows)
    M.grid_object("HatCrown", Pm, st.col("gear"), wrap=True, cap_top=True, mat=gauze, parent=st.rig,
                  uv=np.stack([np.broadcast_to(a * 0.09, Pm.shape[:2]), Pm[..., 2]], -1))
    # outer panel: front and sides, lower, a little larger, open at the back
    keep = np.abs(a) < 2.25
    oa = a[keep]
    order = np.argsort(oa)
    ring1 = _squared(head_pt(H, a, zb + 0.012 * s, 0.0090 * s), 0.4)[keep][order]
    ptop = zb.max() + 0.016 * s + g.get("panel", 0.036) * s
    rows = []
    front = np.cos(oa[order])
    ptop_a = ptop - (1 - np.clip(front, 0, 1)) * 0.014 * s
    for t in np.linspace(0, 1, 12):
        P = ring1.copy()
        P[:, 2] = ring1[:, 2] * (1 - t) + ptop_a * t
        rows.append(P)
    Pm = np.stack(rows)
    M.grid_object("HatPanel", Pm, st.col("gear"), wrap=False, mat=gauze, parent=st.rig,
                  uv=np.stack([np.broadcast_to(oa[order] * 0.09, Pm.shape[:2]), Pm[..., 2]], -1))
    # ribbons (巾带) hanging behind
    for side in ((-1, 1) if g.get("ribbons", False) else ()):
        p0 = head_pt(H, np.array([side * 2.7]), np.array([zb.min() + 0.004 * s]), np.array([0.008 * s]))[0]
        pts = np.array([p0 + np.array([side * 0.003 * k, 0.006 * k, -0.011 * k]) * s for k in range(9)])
        w = np.array([side * 0.009, 0.0, 0.0]) * s
        M.strip("Ribbon%+d" % side, pts - w / 2, pts + w / 2, st.col("band"), mat=band, parent=st.rig)


def small_crown(st, H, g):
    """小冠: a small gold / lacquer crown over the topknot with a jade hairpin."""
    s = H.s
    gold = gold_mat()
    c = np.array([0.0, 0.010 * s, H.top + 0.006 * s])
    prof = [(0.0, 0.040), (0.010, 0.040), (0.020, 0.034), (0.024, 0.020), (0.022, 0.006), (0.018, 0.0)]
    prof = [(r * s, z * s) for r, z in prof]
    M.lathe("Crown", prof, st.col("gear"), n_around=28, mat=MT.wash("PC_Crown", g.get("color", "#2A2624"),
            "#0E0C0C", region="hat", blend=0.4, lo=0.05, hi=1.0), center=tuple(c), parent=st.rig,
            axis_scale=(0.75, 1.0))
    pin = np.stack([c + np.array([-0.045, 0, 0.018]) * s, c + np.array([0.045, 0, 0.018]) * s])
    M.tube("CrownPin", M.resample(pin, 6), 0.0022 * s, st.col("gear"), n_around=8,
           mat=jade_mat() if g.get("pin", "jade") == "jade" else gold, parent=st.rig)


# =============================================================================================
# costume
# =============================================================================================
def _conform(torso, a, z_top, z_bot, off, nz=60):
    """Grid on the torso from a top edge z_top(a) down to z_bot."""
    t = np.linspace(0, 1, nz)[:, None]
    Z = z_top[None, :] * (1 - t) + z_bot * t
    A = np.broadcast_to(a[None, :], Z.shape)
    return torso.point(A, Z, off), A, Z


def armour(st, torso, a_spec):
    """Lamellar cuirass with a gold-trimmed neck opening, shoulder guards and chest mirrors."""
    col = a_spec.get("color", "#6A7884")
    lam = MT.wash("PC_Armour", col, a_spec.get("deep", "#262C34"), region="armour", blend=0.42, lo=0.05,
                  hi=1.0, form=0.12, pattern=MT.lamellae(ph=a_spec.get("ph", 0.024), pw=a_spec.get("pw", 0.016),
                                                          lace=a_spec.get("lace", "#A8382A")))
    gold = gold_mat()
    na = 160
    a = np.linspace(-math.pi, math.pi, na, endpoint=False)
    # neck opening: round at the back, a U in front
    zt = -0.168 - 0.050 * np.exp(-(a / 0.55) ** 2) * a_spec.get("v", 1.0)
    off = 0.016 + 0.004 * a_spec.get("bulk", 0.0)
    P, A, Z = _conform(torso, a, zt, -0.53, off, nz=70)
    # u = angle x a fixed radius: the plate columns stay aligned from row to row
    U = (A + math.pi) * 0.17
    M.grid_object("Cuirass", P, st.col("armour"), wrap=True, mat=lam, uv=np.stack([U, Z], -1))
    # gold trim round the opening (a raised band)
    t_in = torso.point(a, zt + 0.002, off + 0.003)
    t_out = torso.point(a, zt - 0.016, off + 0.003)
    M.strip("CuirassTrim", np.concatenate([t_in, t_in[:1]]), np.concatenate([t_out, t_out[:1]]),
            st.col("band"), mat=MT.wash("PC_ArmTrim", a_spec.get("trim", "gold"), "gold_d", region="gold",
                                        blend=0.45, lo=0.05, hi=1.0,
                                        pattern=MT.brocade(period=0.018, width=0.018, motif="#8A6A2A",
                                                           edge="#7A5A24", kind="dots", size=0.3)))
    # chest strap (甲绊): a leather band from the neck trim down the sternum, studded in gold
    if a_spec.get("strap", True):
        z0 = float(zt[na // 2]) - 0.012
        zs = np.linspace(z0, -0.50, 40)
        w = a_spec.get("strap_w", 0.017)
        L = torso.point(torso.alpha_of_x(np.full_like(zs, -w), zs), zs, off + 0.004)
        R = torso.point(torso.alpha_of_x(np.full_like(zs, w), zs), zs, off + 0.004)
        M.strip("ChestStrap", L, R, st.col("band"),
                mat=MT.wash("PC_Strap", a_spec.get("strap_color", "#8A2A20"), "#4A140E", region="leather",
                            blend=0.45, lo=0.05, hi=1.0,
                            pattern=MT.brocade(period=0.030, width=0.036, motif="gold", edge="gold",
                                               edge_w=0.0018, kind="dots", size=0.28)))
    # chest mirrors (护心镜)
    if a_spec.get("mirrors", True):
        for side in (-1, 1):
            al, zc = side * 0.40, -0.280
            c = torso.point(np.array(al), np.array(zc), off + 0.010)
            nrm = torso.normal(np.array(al), np.array(zc))
            u = np.cross(nrm, [0, 0, 1.0])
            u /= np.linalg.norm(u)
            v = np.cross(u, nrm)
            R = 0.036
            ring_t = np.linspace(0, 2 * math.pi, 48)
            dome = []
            for rr, hh in ((0.0, 0.006), (0.4, 0.0055), (0.75, 0.004), (1.0, 0.0)):
                dome.append(c + nrm * hh + (np.outer(np.cos(ring_t), u) + np.outer(np.sin(ring_t), v)) * R * rr)
            Pm = np.stack(dome)
            UVm = np.stack([np.broadcast_to(ring_t[None] * R, Pm.shape[:2]),
                            np.broadcast_to(np.array([0.0, 0.4, 0.75, 1.0])[:, None] * R, Pm.shape[:2])], -1)
            M.grid_object("Mirror%+d" % side, Pm, st.col("armour"), wrap=True, uv=UVm,
                          mat=MT.wash("PC_Mirror", "#8C9CAA", "#46525E", region="armour", blend=0.6, lo=0.0,
                                      hi=1.0, form=0.20,
                                      pattern=MT.stripes_uv(freq=70.0, color="#DCE4EA", alpha=0.30, along="v", warp=0.0)))
            rim_i = c + nrm * 0.004 + (np.outer(np.cos(ring_t), u) + np.outer(np.sin(ring_t), v)) * R * 0.98
            rim_o = c + nrm * 0.001 + (np.outer(np.cos(ring_t), u) + np.outer(np.sin(ring_t), v)) * R * 1.18
            M.strip("MirrorRim%+d" % side, np.concatenate([rim_i, rim_i[:1]]), np.concatenate([rim_o, rim_o[:1]]),
                    st.col("band"), mat=gold)
    # shoulder guards (披膊)
    if a_spec.get("pauldrons", True):
        for side in (-1, 1):
            pauldron(st, torso, side, a_spec, gold)


def pauldron(st, torso, side, a_spec, gold):
    """A shoulder guard: an open bell of fish-scale plates over the shoulder cap."""
    sh = torso.point(np.array(side * math.pi / 2), np.array(-0.215), 0.0)
    rows = []
    nt, nr = 16, 40
    th = np.linspace(-2.3, 2.3, nr)                 # around the arm, open on the inner side
    for k, t in enumerate(np.linspace(0, 1, nt)):
        z = -0.175 - 0.150 * t
        r = 0.050 + 0.048 * t ** 0.7
        cx = sh[0] + side * (0.004 + 0.022 * t)
        cy = sh[1] + 0.004
        x = cx + side * np.cos(th) * r * 0.85
        y = cy - np.sin(th) * r * 1.05
        zz = z + 0.020 * (np.cos(th) - 1) * (1 - t) * 0.4
        rows.append(np.stack([x, y, np.full_like(th, 0) + zz], -1))
    P = np.stack(rows)
    # dome the top rows over the shoulder
    P[:4, :, 2] += np.linspace(0.016, 0.0, 4)[:, None] * np.cos(th)[None] ** 2
    U = np.broadcast_to((th * 0.07)[None], P.shape[:2])
    lam = MT.wash("PC_Pauldron", a_spec.get("color2", a_spec.get("color", "#56616C")),
                  a_spec.get("deep", "#262C34"), region="armour", blend=0.42, lo=0.05, hi=1.0, form=0.12,
                  pattern=MT.scales(ph=0.016, pw=0.016))
    obj = M.grid_object("Pauldron%+d" % side, P, st.col("armour"), wrap=False, mat=lam,
                        uv=np.stack([U, P[..., 2]], -1))
    hem_i = P[-1]
    hem_o = P[-1] + (P[-1] - P[-2]) * 0.9
    M.strip("PauldronHem%+d" % side, hem_i, hem_o, st.col("band"), mat=gold)
    # a gold beast-head boss on the shoulder (simplified to a domed rosette)
    top = P[2, nr // 2] + np.array([side * 0.006, -0.002, 0.004])
    M.ellipsoid("PauldronBoss%+d" % side, top, (0.014, 0.012, 0.010), st.col("gear"), mat=gold)
    return obj


def cloak(st, torso, c):
    """Cloak (披风) over the shoulders and back: offset shell with vertical folds."""
    color = c.get("color", "cinnabar")
    mat = MT.wash("PC_Cloak", color, c.get("deep", deepen(color, 0.55)), region="cloak", blend=0.45,
                  lo=0.05, hi=1.0, form=0.10)
    na = 120
    a = np.linspace(-math.pi, math.pi, na, endpoint=False)
    keep = np.abs(a) > c.get("open", 1.20)
    a = np.concatenate([a[keep & (a > 0)], a[keep & (a < 0)]])
    zt = -0.150 - 0.025 * M.smoothstep(2.4, 1.3, np.abs(a))
    nz = 50
    t = np.linspace(0, 1, nz)[:, None]
    Z = zt[None, :] * (1 - t) - 0.53 * t
    A = np.broadcast_to(a[None, :], Z.shape)
    off = c.get("off", 0.058) * M.smoothstep(-0.15, -0.24, Z) + 0.008
    # vertical folds hanging from the shoulders
    folds = 0.006 * np.sin(A * 9.0) * M.smoothstep(-0.20, -0.34, Z)
    P = torso.point(A, Z, off + folds)
    M.grid_object("Cloak", P, st.col("robe"), wrap=False, mat=mat, uv=np.stack([A * 0.15, Z], -1))
    # cloak collar band round the neck
    ci = torso.point(a, zt + 0.018, 0.010)
    co = torso.point(a, zt - 0.004, off[0] * 0.6 + 0.008)
    M.strip("CloakCollar", ci, co, st.col("band"),
            mat=MT.wash("PC_CloakCollar", c.get("collar", "gold"), "gold_d", region="gold", blend=0.45,
                        lo=0.05, hi=1.0, pattern=MT.brocade(period=0.02, width=0.025, motif="#8A2A20",
                                                            edge="#7A5A24", kind="lozenge")))


def shawl(st, torso, sp):
    """披帛: a long gauze scarf over the shoulders, hanging in front of the upper arms."""
    color = sp.get("color", "malachite_l")
    mat = MT.wash("PC_Shawl", color, deepen(color, 0.72), region="shawl", blend=0.5, lo=0.05, hi=1.0,
                  form=0.08, pattern=MT.roundels(period=0.05, color=sp.get("motif", "#F4EEE2"), alpha=0.35, r=0.2))
    for side in (-1, 1):
        al = np.array([side * 2.5, side * 1.95, side * 1.62, side * 1.40, side * 1.28, side * 1.22])
        zz = np.array([-0.165, -0.180, -0.205, -0.25, -0.32, -0.45])
        path = M.resample(np.stack([al, zz], -1), 30)
        w = sp.get("width", 0.07)
        P0 = torso.point(path[:, 0], path[:, 1], 0.010 + 0.006 * M.smoothstep(-0.2, -0.3, path[:, 1]))
        nrm = torso.normal(path[:, 0], path[:, 1])
        d = np.gradient(P0, axis=0)
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        across = np.cross(nrm, d)
        twist = np.sin(np.linspace(0, math.pi * 1.5, len(P0)))[:, None] * 0.3
        across = across * (1 - np.abs(twist)) + nrm * twist
        L = P0 - across * w / 2
        R = P0 + across * w / 2
        M.strip("Shawl%+d" % side, L, R, st.col("band"), mat=mat)


def earrings(st, H, e):
    s = H.s
    gold = gold_mat()
    for side in (-1, 1):
        o, back, up, out = BB.ear_frame(H, side)
        lobe = o + back * 0.008 * s - up * 0.031 * s + out * 0.004 * s
        pts = np.array([lobe, lobe - up * 0.008 * s, lobe - up * 0.014 * s])
        st.add_curve("earring%+d" % side, "chain", pts, head_local=True, color="#B08A3A", w=0.5)
        M.ellipsoid("EarPearl%+d" % side, lobe - up * 0.018 * s, (0.0035 * s,) * 3, st.col("fine"),
                    mat=pearl_mat() if e.get("kind", "pearl") == "pearl" else jade_mat(), parent=st.rig,
                    n=(12, 8))


def beads(st, torso, b):
    """Prayer beads (念珠) hanging round the neck onto the chest."""
    mat = MT.wash("PC_Beads", b.get("color", "#6A3A24"), "#2A160C", region="orna", blend=0.5, lo=0.0,
                  hi=1.0, form=0.15)
    t = np.linspace(-1, 1, b.get("n", 34))
    al = t * 1.05
    z = -0.150 - 0.115 * (1 - t ** 2) ** 0.9
    P = torso.point(al, z, 0.022)
    for i, p in enumerate(P):
        r = 0.0085 if i != len(P) // 2 else 0.012
        M.ellipsoid("Bead%d" % i, p, (r, r, r), st.col("fine"), mat=mat, n=(10, 8))
