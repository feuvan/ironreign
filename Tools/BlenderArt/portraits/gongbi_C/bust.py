"""Bust builders (Blender side): head, ears, neck, torso with the crossed collar, folds.

All builders take the :class:`b3d.Stage` and the character spec (see :mod:`specs`).  Costume
extras live in :mod:`gear` (armour, cloaks, helmets, hats, hair).
"""

import math

import numpy as np

import geo
import palette as PL


# =============================================================================================
# skin
# =============================================================================================
def skin_mats(st, spec):
    light, deep = PL.SKIN[spec.get("skin", "warm")]
    face = st.mat("Skin_Face", light, deep, power=2.2, blend=0.42, lo=0.15, hi=1.0,
                  mask=(1, 0, 0))
    body = st.mat("Skin_Body", light, deep, power=2.0, blend=0.42, lo=0.15, hi=1.0,
                  mask=(0, 0, 1))
    return face, body


def build_head(st, spec):
    hp = spec.get("head", {})
    L = geo.head_loft(hp)
    face_m, skin_m = skin_mats(st, spec)
    zs = np.concatenate([np.linspace(hp.get("chin_z", -0.5), 0.14, 52),
                         np.linspace(0.16, hp.get("crown", 0.5) - 0.002, 22)])
    G = L.grid(zs, 96)
    head = st.grid_mesh("Head", G, "face", face_m, closed=True, cap_top=True, cap_bot=True,
                        M=st.M_head)
    st.head_loft = L
    st.anchors["head"] = head.name
    # ears
    if spec.get("ears", True):
        for side in (-1, 1):
            build_ear(st, L, side, skin_m, spec.get("ear", {}))
    # neck
    nk = dict(spec.get("neck", {}))
    NL = geo.neck_loft(nk)
    zs = np.linspace(nk.get("bottom", -1.05), nk.get("top", -0.18), 14)
    Gn = NL.grid(zs, 48)
    # the top of the neck sits in the head: bake through a blend of body / head matrices so a
    # turned head still meets the neck (top rows follow the head, bottom rows the body)
    w = geo.smoothstep(-0.75, -0.3, zs)
    Gb = st.xf(st.M_body, Gn)
    Gh = st.xf(st.M_head, Gn)
    Gw = Gb * (1 - w)[:, None, None] + Gh * w[:, None, None]
    st.grid_mesh("Neck", Gw, "skin", skin_m, closed=True)
    st.neck_loft = NL
    return head


def build_ear(st, L, side, mat, ep):
    h = ep.get("h", 0.27)
    w = ep.get("w", 0.13)
    zc = ep.get("z", -0.075)
    out = geo.ear_outline(40, h, w)                 # (a back, b up)
    # rings from the back (attached, inside the head) to the rolled rim and the bowl
    rings = [(0.80, -0.035), (0.95, -0.01), (1.0, 0.012), (0.93, 0.03), (0.80, 0.022),
             (0.55, 0.008), (0.25, 0.0)]
    cx = np.array([0.18 * w, 0.0])
    G = []
    for k, off in rings:
        ab = cx + (out - cx) * k
        G.append(np.stack([np.full(len(ab), off), ab[:, 0], ab[:, 1]], -1))
    G = np.array(G)                                 # (rings, n, [out, back, up])
    # place: attach point on the head side, flare the back edge outwards, tilt the top back
    yat = ep.get("y", 0.015)
    Wz = float(L.width(zc))
    flare = math.radians(ep.get("flare", 30.0))
    tilt = math.radians(ep.get("tilt", 14.0))
    o, a, b = G[..., 0], G[..., 1], G[..., 2]
    # tilt (rotate a/b about the out axis: top goes back)
    a2 = a * math.cos(tilt) + b * math.sin(tilt)
    b2 = -a * math.sin(tilt) + b * math.cos(tilt)
    # flare (rotate out/back about z: the back edge moves outwards)
    o2 = o + a2 * math.sin(flare)
    a3 = a2 * math.cos(flare)
    P = np.stack([side * (Wz - ep.get("inset", 0.02) + o2), yat + a3, zc + b2], -1)
    st.grid_mesh("Ear%+d" % side, P, "skin", mat, closed=True, cap_top=True, cap_bot=False,
                 M=st.M_head)
    # inner ear detail for the 2D stage: the helix fold following the rim, a concha curl
    def ear_pt(ka, kb, off):
        a2_ = ka * math.cos(tilt) + kb * math.sin(tilt)
        b2_ = -ka * math.sin(tilt) + kb * math.cos(tilt)
        o2_ = off + a2_ * math.sin(flare)
        a3_ = a2_ * math.cos(flare)
        return np.stack([side * (Wz - ep.get("inset", 0.02) + o2_), yat + a3_, zc + b2_], -1)
    i0, i1 = 2, 24
    seg = out[i0:i1]
    ab = cx + (seg - cx) * 0.80
    st.add_curve("ear_helix%+d" % side, "ear",
                 st.xf(st.M_head, ear_pt(ab[:, 0], ab[:, 1], 0.026)), w=0.6)
    t = np.linspace(0, 1, 16)
    ch = np.stack([0.10 * w + 0.20 * w * np.sin(t * math.pi * 0.9), 0.06 * h - 0.26 * h * t], -1)
    st.add_curve("ear_concha%+d" % side, "ear",
                 st.xf(st.M_head, ear_pt(ch[:, 0], ch[:, 1], 0.018)), w=0.5)
    er = st.spec.get("earrings") if hasattr(st, "spec") else None
    if er:
        lobe = ear_pt(np.array([0.12 * w]), np.array([-0.47 * h]), 0.012)
        st.add_curve("earring%+d" % side, "earring", st.xf(st.M_head, lobe),
                     color=er.get("color", "pearl"), metal=er.get("metal", "gold"),
                     length=er.get("len", 0.07))


# =============================================================================================
# torso, crossed collar (交领右衽) and folds
# =============================================================================================
def lapel_path(cp, side, offset=0.0, Lt=None, n=60):
    """Centre line of one lapel in torso (z, t) parameters: round the back of the neck, then a
    diagonal across the chest defined in front (x, z).  side +1 = the top lapel (the figure's
    left panel: leaves the neck on the +X side and crosses to -X), -1 = the under lapel.
    ``offset`` moves the line away from the opening (outer collar layers)."""
    Lt = Lt or geo.torso_loft()
    nz = cp.get("neck_z", -0.65) - offset * 0.2
    cz = cp.get("cross_z", -0.96) - offset * 1.45
    end_z = cp.get("end_z", -1.75)
    xn = cp.get("x_neck", 0.17) + offset * 0.9            # where the lapel leaves the neck
    k1 = 22
    # round the neck: from the back (t = pi) to the front-side point of the neck ring
    tn = float(Lt.t_of_x(xn, nz))
    tt = np.linspace(math.pi * 0.985, tn, k1)
    zz = np.full(k1, nz)
    # diagonal: (xn, nz) -> (0, cz) -> (x_end, end_z), slightly bowed
    k2 = n - k1
    u = np.linspace(0, 1, k2 + 1)[1:]
    x_end = -cp.get("x_end", 0.55)
    zc = cz
    # piecewise: neck point -> crossing -> end, as one smooth quadratic-ish curve
    P0 = np.array([xn, nz])
    P1 = np.array([0.0, zc])
    P2 = np.array([x_end, end_z])
    uc = 0.45
    seg1 = u < uc
    a1 = (u / uc)
    a2 = (u - uc) / (1 - uc)
    bow = cp.get("bow", 0.03)
    x = np.where(seg1, P0[0] + (P1[0] - P0[0]) * a1, P1[0] + (P2[0] - P1[0]) * a2)
    z = np.where(seg1, P0[1] + (P1[1] - P0[1]) * a1 ** 1.15, P1[1] + (P2[1] - P1[1]) * a2)
    x = x + bow * np.sin(np.clip(a1, 0, 1) * math.pi) * np.where(seg1, 1, 0)
    t2 = Lt.t_of_x(x, z)
    t_all = np.concatenate([tt, t2]) * side
    z_all = np.concatenate([zz, z])
    return z_all, t_all


def surface_band(Lt, z, t, width, lift, inner_side):
    """Inner / outer edges of a band of ``width`` along the (z, t) path, lifted off the surface.
    ``inner_side`` +1: the band grows towards the opening (decreasing |t| / up)."""
    P = Lt.point(z, t)
    N = Lt.normal(z, t)
    T = np.gradient(P, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    side = np.cross(N, T)
    side /= np.maximum(np.linalg.norm(side, axis=1, keepdims=True), 1e-9)
    # orient 'side' to point upwards / towards the neck
    s = np.sign(side[:, 2].mean() + 1e-9)
    side *= s
    A = P + N * lift + side * width * 0.5 * inner_side
    B = P + N * lift - side * width * 0.5 * inner_side
    return A, B, P, N


def collar_layers(cos):
    col = cos.get("collar", {})
    layers = col.get("layers", [dict(color="white", w=0.05)])
    return col, layers


def build_torso(st, spec):
    cos = spec.get("costume", {})
    Lt = geo.torso_loft(spec.get("torso", {}))
    st.torso_loft = Lt
    robe = cos.get("robe", {})
    rc = robe.get("color", "azurite")
    robe_m = st.mat("Robe", rc, robe.get("deep") or PL.deepen(rc, 0.62), power=1.4, blend=0.5,
                    lo=0.05, hi=1.0, pattern=pattern_for(robe.get("pattern")))
    col, layers = collar_layers(cos)
    inner = layers[0]
    inner_m = st.mat("Inner", inner.get("fill", inner["color"]),
                     PL.deepen(inner.get("fill", inner["color"]), 0.8), power=1.5, blend=0.5)
    # torso mesh with the face materials: robe, and the inner garment inside the innermost V
    zs = np.linspace(-2.2, dict(geo.TORSO_DEFAULT, **spec.get("torso", {}))["neck_base"], 48)
    nT = 120
    G = Lt.grid(zs, nT)
    tt = np.linspace(0, 2 * math.pi, nT, endpoint=False)
    tt = np.where(tt > math.pi, tt - 2 * math.pi, tt)
    # V test per vertex: above both lapels' inner edges (and in front)
    w0 = layers[0].get("w", 0.05)
    zA, tA = lapel_path(col, +1, 0.0, Lt)
    zB, tB = lapel_path(col, -1, 0.0, Lt)

    def lapel_z_at(tq, zp, tp):
        ts, zsd = tp[21:], zp[21:]
        order = np.argsort(ts)
        return np.interp(tq, ts[order], zsd[order], left=np.nan, right=np.nan)
    TT, ZZ = np.meshgrid(tt, zs)
    zt = np.nan_to_num(lapel_z_at(TT, zA, tA), nan=-9.0)
    zb = np.nan_to_num(lapel_z_at(TT, zB, tB), nan=-9.0)
    t_neck = float(Lt.t_of_x(col.get("x_neck", 0.17), col.get("neck_z", -0.65)))
    inside = (np.abs(TT) < t_neck + 0.05) & (ZZ > np.maximum(zt, zb) - w0 * 0.4)
    # build faces with per-face material index
    import bpy  # noqa: F401  (material slots)
    R, C = G.shape[:2]
    faces, fmat = [], []
    for i in range(R - 1):
        for j in range(C):
            j2 = (j + 1) % C
            faces.append((i * C + j, i * C + j2, (i + 1) * C + j2, (i + 1) * C + j))
            fmat.append(1 if inside[i:i + 2, [j, j2]].mean() > 0.5 else 0)
    s = np.cumsum(np.r_[0, np.linalg.norm(np.diff(G, axis=1), axis=2).mean(0)])
    uv = np.stack(np.broadcast_arrays(s[None, :], zs[:, None]), -1)
    ob = st.mesh("Torso", G.reshape(-1, 3), faces, "cloth", robe_m, uv=uv.reshape(-1, 2),
                 M=st.M_body)
    ob.data.materials.append(inner_m)
    ob.data.polygons.foreach_set("material_index", fmat)
    # collar bands, innermost first
    lift0 = 0.006
    for k, L in enumerate(layers):
        cm = st.mat("Collar%d" % k, L["color"], L.get("deep") or PL.deepen(L["color"], 0.78),
                    power=1.3, blend=0.5, pattern=pattern_for(L.get("pattern")))
        acc = sum(l2.get("w", 0.05) for l2 in layers[:k]) + L.get("w", 0.05) * 0.5
        for side in (+1, -1):
            z, t = lapel_path(col, side, acc - w0 * 0.5, Lt)
            lift = lift0 + 0.005 * k + (0.016 if side > 0 else 0.0)
            A, B, P, N = surface_band(Lt, z, t, L.get("w", 0.05), lift, +1)
            stand = L.get("stand", 0.03)
            up = geo.smoothstep(0.9, 1.6, np.abs(t))[:, None]
            A = A + np.array([0, 0, 1.0]) * stand * up
            st.strip("Collar%d_%+d" % (k, side), A, B, "band", cm, M=st.M_body)
    # folds: designed curves (x fraction of the shoulder half width, z) on the torso front ->
    # 2D 兰叶描 strokes with a 分染 wash beside them
    tp = dict(geo.TORSO_DEFAULT, **spec.get("torso", {}))
    sw = tp["shoulder_w"] * tp.get("bulk", 1.0)
    for i, f in enumerate(robe.get("folds", default_folds(spec))):
        pts = np.array(f["pts"], float)
        C = np.stack([np.interp(np.linspace(0, 1, 30), np.linspace(0, 1, len(pts)), pts[:, k])
                      for k in range(2)], -1)
        x = C[:, 0] * sw
        z = C[:, 1]
        t = Lt.t_of_x(x, z, front=f.get("front", True))
        P = Lt.point(z, t) + Lt.normal(z, t) * 0.006
        st.add_curve("fold%d" % i, "fold", st.xf(st.M_body, P), w=f.get("w", 1.0),
                     side=f.get("side", 1))
    return ob


def default_folds(spec):
    """Fold lines of a robe on a bust: the arm / body separation on both sides, the sleeve
    folds over the upper arm and two soft folds under the collar crossing."""
    return [
        dict(pts=[(0.80, -1.02), (0.75, -1.25), (0.73, -1.62)], w=1.1, side=-1),
        dict(pts=[(-0.80, -1.02), (-0.75, -1.25), (-0.73, -1.62)], w=1.1, side=1),
        dict(pts=[(0.93, -1.12), (0.89, -1.32), (0.90, -1.62)], w=0.8, side=-1),
        dict(pts=[(-0.93, -1.12), (-0.89, -1.32), (-0.90, -1.62)], w=0.8, side=1),
        dict(pts=[(0.30, -1.22), (0.35, -1.40), (0.33, -1.62)], w=0.7, side=-1),
        dict(pts=[(-0.42, -1.26), (-0.47, -1.44), (-0.45, -1.64)], w=0.7, side=1),
    ]


# =============================================================================================
# patterns (shader side): roundels / brocade / lamellae in UV space
# =============================================================================================
def pattern_for(p):
    if not p:
        return None
    kind = p.get("kind")
    if kind == "roundels":
        return lambda nt, col: roundels(nt, col, p)
    if kind == "brocade":
        return lambda nt, col: brocade(nt, col, p)
    if kind == "lamellar":
        return lambda nt, col: lamellar(nt, col, p)
    if kind == "gauze":
        return lambda nt, col: gauze(nt, col, p)
    return None


def _uv(nt):
    n = nt.nodes.new("ShaderNodeUVMap")
    n.uv_map = "UVMap"
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(n.outputs["UV"], sep.inputs[0])
    return sep.outputs["X"], sep.outputs["Y"]


def _math(nt, op, a, b=None, c=None):
    m = nt.nodes.new("ShaderNodeMath")
    m.operation = op
    for i, v in enumerate((a, b, c)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            m.inputs[i].default_value = float(v)
        else:
            nt.links.new(v, m.inputs[i])
    return m.outputs[0]


def _mix(nt, col, other, fac, blend="MIX"):
    m = nt.nodes.new("ShaderNodeMix")
    m.data_type = "RGBA"
    m.blend_type = blend
    nt.links.new(fac, m.inputs["Factor"])
    nt.links.new(col, m.inputs["A"])
    if isinstance(other, tuple):
        m.inputs["B"].default_value = other
    else:
        nt.links.new(other, m.inputs["B"])
    return m.outputs["Result"]


def _smooth(nt, x, e0, e1):
    m = nt.nodes.new("ShaderNodeMapRange")
    m.interpolation_type = "SMOOTHSTEP"
    m.inputs["From Min"].default_value = e0
    m.inputs["From Max"].default_value = e1
    nt.links.new(x, m.inputs["Value"])
    return m.outputs["Result"]


def roundels(nt, col, p):
    """Woven roundels (团花) on a staggered grid: a soft disc of motif colour with a ring."""
    u, v = _uv(nt)
    per = p.get("period", 0.16)
    U = _math(nt, "DIVIDE", u, per)
    V = _math(nt, "DIVIDE", v, per)
    row = _math(nt, "FLOOR", V)
    shift = _math(nt, "MULTIPLY", _math(nt, "FLOORED_MODULO", row, 2.0), 0.5)
    fu = _math(nt, "SUBTRACT", _math(nt, "FRACT", _math(nt, "ADD", U, shift)), 0.5)
    fv = _math(nt, "SUBTRACT", _math(nt, "FRACT", V), 0.5)
    r = _math(nt, "SQRT", _math(nt, "ADD", _math(nt, "MULTIPLY", fu, fu), _math(nt, "MULTIPLY", fv, fv)))
    size = p.get("size", 0.28)
    disc = _smooth(nt, _math(nt, "SUBTRACT", size, r), -0.012, 0.012)
    ring = _smooth(nt, _math(nt, "SUBTRACT", 0.018, _math(nt, "ABSOLUTE", _math(nt, "SUBTRACT", r, size * 0.72))), -0.006, 0.006)
    # petals: angular modulation
    ang = _math(nt, "ARCTAN2", fv, fu)
    pet = _math(nt, "ABSOLUTE", _math(nt, "SINE", _math(nt, "MULTIPLY", ang, p.get("petals", 6) / 2.0)))
    petal = _smooth(nt, _math(nt, "SUBTRACT", _math(nt, "MULTIPLY", pet, size * 0.55), r), -0.01, 0.01)
    a = p.get("alpha", 0.55)
    c1 = _mix(nt, col, PL.lin4(p.get("color", "gold")), _math(nt, "MULTIPLY", disc, a * 0.55))
    c2 = _mix(nt, c1, PL.lin4(p.get("color2", p.get("color", "gold"))), _math(nt, "MULTIPLY", petal, a))
    c3 = _mix(nt, c2, PL.lin4(p.get("line", "ink")), _math(nt, "MULTIPLY", ring, a * 0.6))
    return c3


def brocade(nt, col, p):
    """Collar band brocade: a row of lozenges / dots along the band, gold edge lines."""
    u, v = _uv(nt)
    per = p.get("period", 0.045)
    U = _math(nt, "DIVIDE", u, per)
    fu = _math(nt, "ABSOLUTE", _math(nt, "SUBTRACT", _math(nt, "FRACT", U), 0.5))
    fv = _math(nt, "ABSOLUTE", _math(nt, "SUBTRACT", v, 0.5))
    if p.get("motif", "lozenge") == "dots":
        d = _math(nt, "SQRT", _math(nt, "ADD", _math(nt, "MULTIPLY", fu, fu),
                                    _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", fv, 0.9), _math(nt, "MULTIPLY", fv, 0.9))))
        m = _smooth(nt, _math(nt, "SUBTRACT", p.get("size", 0.26), d), -0.03, 0.03)
    else:
        d = _math(nt, "ADD", fu, _math(nt, "MULTIPLY", fv, 1.1))
        m = _smooth(nt, _math(nt, "SUBTRACT", p.get("size", 0.36), d), -0.03, 0.03)
    edge = _smooth(nt, _math(nt, "SUBTRACT", fv, 0.40), -0.015, 0.015)
    c1 = _mix(nt, col, PL.lin4(p.get("color", "gold")), _math(nt, "MULTIPLY", m, p.get("alpha", 0.85)))
    c2 = _mix(nt, c1, PL.lin4(p.get("edge", "gold")), _math(nt, "MULTIPLY", edge, p.get("edge_a", 0.9)))
    return c2


def lamellar(nt, col, p):
    """Lamellar armour (札甲): staggered rows of small plates, dark seams, red lacing dots."""
    u, v = _uv(nt)
    pw, ph = p.get("w", 0.055), p.get("h", 0.085)
    U = _math(nt, "DIVIDE", u, pw)
    V = _math(nt, "DIVIDE", v, ph)
    row = _math(nt, "FLOOR", V)
    shift = _math(nt, "MULTIPLY", _math(nt, "FLOORED_MODULO", row, 2.0), 0.5)
    fu = _math(nt, "FRACT", _math(nt, "ADD", U, shift))
    fv = _math(nt, "FRACT", V)
    eu = _math(nt, "MINIMUM", fu, _math(nt, "SUBTRACT", 1.0, fu))
    seam_u = _smooth(nt, _math(nt, "SUBTRACT", 0.07, eu), -0.03, 0.03)
    # rounded bottom edge of each plate overlapping the row below
    curve = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", fu, 0.5),
                                         _math(nt, "SUBTRACT", fu, 0.5)), 0.6)
    ev = _math(nt, "SUBTRACT", fv, curve)
    seam_v = _smooth(nt, _math(nt, "SUBTRACT", 0.08, ev), -0.03, 0.03)
    seam = _math(nt, "MAXIMUM", seam_u, seam_v)
    # shading inside each plate: lighter at the top
    sh = _math(nt, "MULTIPLY", fv, p.get("plate_shade", 0.25))
    c0 = _mix(nt, col, PL.lin4(p.get("light", "steel_l")), sh)
    # lacing: two dots near the top of each plate
    du = _math(nt, "SUBTRACT", fu, 0.5)
    dv = _math(nt, "SUBTRACT", fv, 0.78)
    dd = _math(nt, "SQRT", _math(nt, "ADD", _math(nt, "MULTIPLY", du, du), _math(nt, "MULTIPLY", dv, dv)))
    lace = _smooth(nt, _math(nt, "SUBTRACT", 0.12, dd), -0.03, 0.03)
    c1 = _mix(nt, c0, PL.lin4(p.get("lace", "cinnabar")), _math(nt, "MULTIPLY", lace, p.get("lace_a", 0.85)))
    c2 = _mix(nt, c1, PL.lin4(p.get("seam", "ink")), _math(nt, "MULTIPLY", seam, p.get("seam_a", 0.85)))
    return c2


def gauze(nt, col, p):
    """Black gauze (纱) of a hat: a fine lighter mesh."""
    u, v = _uv(nt)
    per = p.get("period", 0.018)
    a = _math(nt, "ABSOLUTE", _math(nt, "SUBTRACT", _math(nt, "FRACT", _math(nt, "DIVIDE", u, per)), 0.5))
    b = _math(nt, "ABSOLUTE", _math(nt, "SUBTRACT", _math(nt, "FRACT", _math(nt, "DIVIDE", v, per)), 0.5))
    m = _math(nt, "MAXIMUM", _smooth(nt, a, 0.38, 0.5), _smooth(nt, b, 0.38, 0.5))
    return _mix(nt, col, PL.lin4(p.get("color", "ink_grey")), _math(nt, "MULTIPLY", m, p.get("alpha", 0.35)))
