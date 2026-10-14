"""Costume builders: cross-collar robes (交领右衽), armour, shawls.

All garments are torso shells (shells.Torso) with exact collar cuts, so the collar edges are clean
brush lines.  Robes close 右衽: the wearer's left lapel crosses over the right, so the viewer
sees a 'y': the outer lapel edge runs from the wearer's left neck (+X) down to the wearer's right
(-X).
"""

import math

import numpy as np

import geo
import patterns as pat
import shade
import shells


def torso(C):
    if getattr(C, "torso", None) is None:
        C.torso = shells.Torso(C.H)
        C.torsoR = C.torso.radius(2.0, 2.0, z_sh=C.H.eye_z - C.spec.get("shoulder_dz", 0.2),
                                  drop=C.spec.get("arm_drop", 0.25))
    return C.torso, C.torsoR


def _line(p, q):
    (x0, z0), (x1, z1) = p, q
    k = (z1 - z0) / (x1 - x0)
    return lambda x: z0 + k * (x - x0)


def collar_cut(C, T, R, L, ease):
    """Return top_fn(a) for a robe layer: neck collar height at the back and sides, and the
    右衽 V opening in front (front-view lines L1: left neck -> bottom, L2: right neck -> bottom)."""
    ez = C.H.eye_z
    zb = ez - L["z_back"]
    pl = (L["v_left"][0], ez - L["v_left"][1])
    pb = (L["v_bottom"][0], ez - L["v_bottom"][1])
    pr = (L["v_right"][0], ez - L["v_right"][1])
    l1 = _line(pl, pb)
    l2 = _line(pr, pb)

    def top(a):
        if math.cos(a) < 0.1:
            return zb
        z = zb
        for _ in range(4):
            r = T.sample(R, a, z) + ease
            x = r * math.sin(a)
            z = min(zb, max(l1(x), l2(x)))
        # soften the join between the neck collar and the V lines
        return z
    return top, l1, pb


def robe_layer(C, L, parent):
    """One robe layer with its collar band.  L: dict(color, pattern, ease, z_back, v_left,
    v_bottom, v_right, band=dict(w, color, pattern, lift), ext=(x, dz) lapel continuation)."""
    T, R = torso(C)
    ease = L.get("ease", 0.012)
    top, l1, pb = collar_cut(C, T, R, L, ease)
    col = C.cols["robe"]
    mat = shade.flat(L.get("name", "Robe"), L["color"], L.get("tint"),
                     ao=L.get("ao", 0.5), ao_dist=0.04, edge=L.get("edge", 0.3),
                     pattern=L.get("pattern"))

    def off(a, z, v):
        o = ease + L.get("ease_low", 0.01) * v
        fa = L.get("folds", 0.0)
        if fa:
            o = o + fa * v ** 1.5 * np.sin(a * L.get("fold_n", 9) + 1.3) * np.cos(a) ** 2
        return o
    ob = T.shell(L.get("name", "Robe"), col, mat, R, top, offset_fn=off, nu=160, nv=40,
                 parent=parent)
    out = [ob]
    if L.get("fold_lines", None) != []:
        out += fold_strokes(C, ob, L)
    b = L.get("band")
    if b:
        out += collar_band(C, T, R, top, L, b, ease, parent)
        if L.get("ext") is not None:
            out += lapel_ext(C, ob, L, b, pb, parent)
    return out


DEFAULT_FOLDS = [
    # (front-view x as a fraction of the shoulder half-width, depth below the eye in metres)
    [(0.34, 0.2), (0.52, 0.228), (0.7, 0.28), (0.76, 0.33)],
    [(0.44, 0.245), (0.58, 0.285), (0.64, 0.345)],
    [(0.62, 0.225), (0.74, 0.25), (0.8, 0.3)],
    [(0.8, 0.24), (0.88, 0.285), (0.9, 0.35)],
    [(0.95, 0.21), (1.0, 0.25), (1.03, 0.31)],
    [(0.2, 0.3), (0.24, 0.35)],
]


def fold_strokes(C, robe_ob, L):
    """兰叶描 fold lines painted on the robe: tension folds from the collar toward the arms,
    and the hanging folds of the upper sleeves.  Front-view paths projected onto the robe."""
    T, R = torso(C)
    ez = C.H.eye_z
    sw = 0.5 * (T.sample(R, math.pi / 2, ez - 0.21) + T.sample(R, -math.pi / 2, ez - 0.21))
    surf = geo.Surface([robe_ob])
    mat = shade.ink(L.get("name", "Robe") + "Fold", L.get("fold_ink", "ink"), 1.0)
    rng = C.rng
    out = []
    lines = L.get("fold_lines") or DEFAULT_FOLDS
    for side in (1, -1):
        for k, ln in enumerate(lines):
            pts = np.array([(side * (x + rng.normal(0, 0.03)) * sw, ez - dz + rng.normal(0, 0.004))
                            for x, dz in ln])
            path = geo.resample(geo.catmull(pts, per=10), 36)
            w = geo.brush_profile(len(path), head=0.25, tail=0.45, start=0.15, end=0.05,
                                  swell=0.45) * L.get("fold_w", 0.0017)
            out.append(geo.decal_strip(L.get("name", "Robe") + "Fold", surf, path, w,
                                       C.cols["nolines"], mat, offset=0.0015, parent=C.root))
    return out


def collar_band(C, T, R, top, L, b, ease, parent):
    nu = 200
    aa = np.linspace(0, 2 * math.pi, nu, endpoint=False)
    tops = np.array([top(a) for a in aa])
    rr = np.array([T.sample(R, a, z) for a, z in zip(aa, tops)]) + ease
    xs = rr * np.sin(aa)
    dz = np.gradient(tops)
    dx = np.gradient(xs)
    slope = np.where(np.abs(dx) > 1e-6, dz / np.where(np.abs(dx) > 1e-6, dx, 1), 0.0)
    w = b["w"] * np.minimum(np.sqrt(1 + slope ** 2), 2.6)
    w = shells.gauss1d(w[None], 2.0, 1, True)[0]
    lift = b.get("lift", 0.0035)
    nv = 8
    V, UV = [], []
    for j in range(nv):
        v = j / (nv - 1)
        zz = tops - w * v
        P = T.point(R, aa, zz, ease + L.get("ease_low", 0.01) * 0.0 + lift * (1 - 0.3 * v))
        V.append(P)
        seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
        s = np.r_[0, np.cumsum(seg)]
        UV.append(np.stack([s, np.full(nu, v)], 1))
    V = np.vstack(V)
    UV = np.vstack(UV)
    F = [f[::-1] for f in geo.grid_faces(nu, nv, wrap_u=True)]
    mat = shade.flat(L.get("name", "Robe") + "Band", b["color"], b.get("tint"), ao=0.4,
                     ao_dist=0.03, edge=0.25, pattern=b.get("pattern"))
    ob = geo.mesh_obj(L.get("name", "Robe") + "Band", V, F, C.cols["robe"], mat, smooth=True,
                      uvs=UV, parent=parent)
    return [ob]


def lapel_ext(C, robe_ob, L, b, pb, parent):
    """The outer lapel band continuing below the V along L1 (to the wearer's right side)."""
    ez = C.H.eye_z
    x1, dz1 = L["ext"]
    p0 = np.array([pb[0] + 0.004, pb[1] + 0.012])
    p1 = np.array([x1, ez - dz1])
    path = np.stack([np.linspace(p0[0], p1[0], 40), np.linspace(p0[1], p1[1], 40)], 1)
    # the band lies on the outer-lapel side (above/left of L1 in front view = toward +x? no:
    # the outer lapel is to the right of the edge (+x side), so shift the centreline that way)
    d = p1 - p0
    d /= np.linalg.norm(d)
    nrm = np.array([d[1], -d[0]])
    if nrm[0] < 0:
        nrm = -nrm
    path = path + nrm * b["w"] * 0.5
    surf = geo.Surface([robe_ob])
    mat = shade.flat(L.get("name", "Robe") + "BandExt", b["color"], b.get("tint"), ao=0.4,
                     ao_dist=0.03, edge=0.25, pattern=b.get("pattern"))
    ob = geo.decal_strip(L.get("name", "Robe") + "BandExt", surf, path,
                         np.full(len(path), b["w"]), C.cols["robe"], mat,
                         offset=b.get("lift", 0.0035), parent=parent)
    # strip UVs: u along, v across -> rescale u for the band pattern repeat
    me = ob.data
    uv = me.uv_layers[0].data
    L_m = float(np.linalg.norm(p1 - p0))
    for lp in uv:
        lp.uv = (lp.uv[0] * L_m, lp.uv[1])
    return [ob]


# --------------------------------------------------------------------------------- armour
def cuirass(C, A, parent):
    """Lamellar cuirass over the robe: round neck opening, painted plates, gilt trim band."""
    T, R = torso(C)
    ez = C.H.eye_z
    ease = A.get("ease", 0.03)
    zn = ez - A.get("z_neck", 0.175)
    dip = A.get("front_dip", 0.035)

    def top(a):
        return zn - dip * max(0.0, math.cos(a)) ** 2

    def off(a, z, v):
        return ease + 0.008 * v
    mat = shade.flat("Cuirass", A.get("plate", "iron"), "#1E2228", ao=0.5, ao_dist=0.04,
                     edge=0.35, pattern=A.get("pattern") or pat.lamellar(
                         A.get("plate", "iron"), A.get("plate_light", "iron_light"),
                         rep_u=A.get("rep_u", 64.0), rows_per_m=A.get("rows", 30.0),
                         lacing=A.get("lacing", "cinnabar")))
    ob = T.shell("Cuirass", C.cols["robe"], mat, R, top, offset_fn=off, nu=160, nv=36,
                 parent=parent)
    # gilt neck trim band
    b = dict(w=A.get("trim_w", 0.022), color=A.get("trim", "gold"),
             pattern=pat.band("ochre", "ochre", rep=50, amount=0.5, kind="diamond"))
    L = dict(name="CuirassTrim", ease_low=0.0)
    out = [ob] + collar_band(C, T, R, top, L, b, ease + 0.002, parent)
    return out


def pauldrons(C, A, parent):
    """披膊 shoulder guards: lamellar flaps over the shoulders and upper arms with a rounded,
    gilt-hemmed lower edge, so they read apart from the cuirass."""
    import patterns as pat
    T, R = torso(C)
    ez = C.H.eye_z
    out = []
    span = math.radians(A.get("span", 62))
    for side in (1, -1):
        a_c = side * math.pi / 2 + side * math.radians(A.get("shift", 6))

        def top(a, a_c=a_c):
            k = (a - a_c) / span
            return ez - A.get("z_top", 0.165) - 0.03 * k * k

        def bot(a, a_c=a_c):
            k = (a - a_c) / span
            return ez - A.get("z_bot", 0.3) + 0.05 * k * k

        def off(a, z, v, a_c=a_c):
            return A.get("p_ease", 0.044) + 0.01 * v

        mat = shade.flat("Pauldron", A.get("p_plate", A.get("plate", "iron")), "#1E2228", ao=0.5,
                         ao_dist=0.04, edge=0.35, pattern=pat.lamellar(
                             A.get("p_plate", A.get("plate", "iron")),
                             A.get("p_plate_light", A.get("plate_light", "iron_light")),
                             rep_u=A.get("rep_u", 64.0) * 0.8, rows_per_m=A.get("rows", 30.0) * 0.9,
                             lacing=A.get("lacing", "cinnabar")))
        ob = T.shell("Pauldron", C.cols["robe"], mat, R, top, bot_z=bot, offset_fn=off, nu=48,
                     nv=24, a0=a_c - span, a1=a_c + span, parent=parent, closed=False)
        out.append(ob)
        # gilt hem along the rounded lower edge
        hw = A.get("hem_w", 0.016)

        def htop(a, bot=bot):
            return bot(a) + hw
        hm = shade.flat("PauldronHem", A.get("trim", "gold"), "#6B4A1A", ao=0.3, edge=0.35,
                        pattern=pat.band("ochre", "ochre", rep=70, amount=0.45, kind="dots"))
        ob2 = T.shell("PauldronHem", C.cols["robe"], hm, R, htop, bot_z=bot,
                      offset_fn=lambda a, z, v: A.get("p_ease", 0.044) + 0.0125, nu=48, nv=4,
                      a0=a_c - span, a1=a_c + span, parent=parent, closed=False)
        out.append(ob2)
    return out


def chest_discs(C, A, parent):
    """護心鏡 chest mirrors: polished round plates with gilt rims (明光铠)."""
    T, R = torso(C)
    ez = C.H.eye_z
    out = []
    surf_objs = [o for o in parent.children if o.name.startswith("Cuirass")]
    surf = geo.Surface(surf_objs[:1])
    rad = A.get("disc_r", 0.042)
    for side in (1, -1):
        cx, cz = side * A.get("disc_x", 0.068), ez - A.get("disc_dz", 0.255)
        p, n = surf.hit(cx, cz)
        if n[1] > 0:
            n = -n
        # disc: lens profile lathe oriented to the surface normal
        prof = [(0.0, 0.006), (rad * 0.5, 0.0055), (rad * 0.85, 0.004), (rad, 0.0025),
                (rad * 1.0, 0.0), (rad * 0.95, -0.002)]
        vv, ff = geo.lathe(prof, 48)
        z = n / np.linalg.norm(n)
        x = np.cross([0, 0, 1.0], z)
        x /= np.linalg.norm(x)
        y = np.cross(z, x)
        M = np.stack([x, y, z], 1)
        vv = vv @ M.T + p + z * 0.002
        F = [f[::-1] for f in ff]
        mat = shade.flat("Disc", A.get("disc", "#4E565E"), "#2A3038", ao=0.2, edge=0.5,
                         edge0=0.2, pattern=_disc_pattern(A))
        ob = geo.mesh_obj("Disc", vv, F, C.cols["robe"], mat, smooth=True, parent=parent)
        out.append(ob)
    return out


def _disc_pattern(A):
    def f(nb, p):
        P = nb.coord("Object")
        # radial rings from the per-object centre: use generated coords
        g = nb.sep(nb.coord("Generated"))
        cu = nb.math("SUBTRACT", g[0], 0.5)
        cv = nb.math("SUBTRACT", g[1], 0.5)
        d = nb.math("SQRT", nb.math("ADD", nb.math("MULTIPLY", cu, cu), nb.math("MULTIPLY", cv, cv)))
        rim = nb.smooth(d, 0.4, 0.44)
        col = nb.mix(nb.smooth(d, 0.0, 0.42), shade.rgb("#8E979E"), p)
        ring2 = nb.math("SUBTRACT", 1.0, nb.smooth(nb.math("ABSOLUTE", nb.math("SUBTRACT", d, 0.3)),
                                                   0.01, 0.03))
        col = nb.mix(nb.math("MULTIPLY", ring2, 0.8), col, shade.rgb("gold"))
        col = nb.mix(rim, col, shade.rgb(A.get("trim", "gold")))
        return col
    return f


def scarf(C, S, parent):
    """A thick silk neck scarf (领巾) / collar roll: a tube around the neck base."""
    T, R = torso(C)
    ez = C.H.eye_z
    z = ez - S.get("dz", 0.155)
    aa = np.linspace(0, 2 * math.pi, 64, endpoint=False)
    rr = np.array([T.sample(R, a, z) for a in aa]) + S.get("ease", 0.012)
    sag = S.get("sag", 0.012) * np.maximum(0, np.cos(aa)) ** 3
    ctr = np.stack([rr * np.sin(aa), T.yc - rr * np.cos(aa), z - sag], 1)
    tube_r = S.get("r", 0.012)
    V = []
    nr = 12
    for i in range(len(aa)):
        a = aa[i]
        out = np.array([math.sin(a), -math.cos(a), 0.0])
        up = np.array([0, 0, 1.0])
        for k in range(nr):
            t = 2 * math.pi * k / nr
            V.append(ctr[i] + tube_r * (math.cos(t) * out * 1.0 + math.sin(t) * up * 0.8))
    V = np.array(V)
    F = []
    n = len(aa)
    for i in range(n):
        i1 = (i + 1) % n
        for k in range(nr):
            k1 = (k + 1) % nr
            F.append((i * nr + k, i * nr + k1, i1 * nr + k1, i1 * nr + k))
    mat = shade.flat("Scarf", S.get("color", "cinnabar"), None, ao=0.6, ao_dist=0.02, edge=0.4)
    return [geo.mesh_obj("Scarf", V, F, C.cols["robe"], mat, smooth=True, parent=parent)]


def shawl(C, S, parent):
    """披帛 shawl: a long silk ribbon lying across the back of the shoulders, over the shoulder
    tops and falling in front of the upper arms."""
    T, R = torso(C)
    ez = C.H.eye_z
    out = []
    for side in (1, -1):
        ctrl = S.get("ctrl", [(135, 0.17, 0.004), (102, 0.175, 0.006), (80, 0.205, 0.012),
                              (66, 0.25, 0.02), (58, 0.3, 0.03), (66, 0.36, 0.034),
                              (76, 0.43, 0.03)])
        pts = np.array([T.point(R, side * a * math.pi / 180.0, ez - dz, S.get("ease", 0.02) + e)
                        for a, dz, e in ctrl])
        pts = geo.resample(geo.catmull(pts, per=8), 60)
        n = len(pts)
        w = S.get("w", 0.045) * (0.85 + 0.3 * np.sin(np.linspace(0, math.pi, n)))
        V, UV = [], []
        s_acc = 0.0
        for i in range(n):
            p = pts[i]
            d = pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]
            d /= np.linalg.norm(d)
            radial = p - np.array([0, T.yc, p[2]])
            radial[2] = 0
            radial /= np.linalg.norm(radial) + 1e-9
            across = np.cross(d, radial)
            across /= np.linalg.norm(across)
            twist = S.get("twist", 0.5) * math.sin(i / n * math.pi * 1.5)
            across = across * math.cos(twist) + radial * math.sin(twist)
            if i:
                s_acc += float(np.linalg.norm(pts[i] - pts[i - 1]))
            V += [p - across * w[i] / 2, p + across * w[i] / 2]
            UV += [(s_acc, 0.0), (s_acc, 1.0)]
        F = [(2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1) for i in range(n - 1)]
        mat = shade.flat("Shawl", S.get("color", "malachite3"), None, ao=0.4, edge=0.2,
                         pattern=S.get("pattern"))
        ob = geo.mesh_obj("Shawl", np.array(V), F, C.cols["robe"], mat, smooth=True,
                          uvs=np.array(UV), parent=parent)
        mod = ob.modifiers.new("Solid", "SOLIDIFY")
        mod.thickness = 0.0015
        out.append(ob)
    return out


def prayer_beads(C, P, parent):
    """念珠: a loop of beads hanging round the neck onto the chest."""
    import gear
    T, R = torso(C)
    ez = C.H.eye_z
    n = P.get("n", 44)
    out = []
    mat = shade.flat("Bead", P.get("color", "#6E4630"), "#2A1A10", ao=0.2, edge=0.55, edge0=0.2)
    for i in range(n):
        a = 2 * math.pi * i / n
        sag = max(0.0, math.cos(a)) ** 1.5 * P.get("drop", 0.12)
        z = ez - P.get("dz", 0.15) - sag
        p = T.point(R, a, z, P.get("ease", 0.024))
        V, F = gear.ellipsoid(p, (0.0055, 0.0055, 0.0055), n=10, m=8)
        out.append(geo.mesh_obj("Bead", V, F, C.cols["fine"], mat, parent=parent))
    return out
