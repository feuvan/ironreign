"""Battle family: the soldier figures and squads of the board units (DESIGN.md 12.3).

A figure is posed with :class:`ironart.scenes_people.Skeleton` (joint angles, facing -Y, feet on
z = 0) and dressed here at a higher level of detail than the illustrated scenes: baggy trousers
and leg wraps, boots, a lamellar cuirass (or a padded archer's coat) with metre UVs for the
painted plates, lamellar tassets over the hips, a **Tint** tabard front and back, layered
shoulder guards, sleeves and leather bracers, a face with painted brows and eyes, an iron
helmet with brim and neck guard crowned by a **Tint** tassel, and the arms: spears with Tint
tassels, round shields, recurve bows with quivers, swords, standards with a Tint banner.
Horses are the court-painting horses of :func:`ironart.scenes_people.horse` with a Tint saddle
cloth and tassels.

Material slots (:func:`ironart.battle_unit_mats.library`): U_Lamellar, U_LamellarRed, U_Coat,
U_Trousers, U_Wrap, U_Sleeve, U_Leather, U_Skin, U_Face, U_Helm, U_Steel, U_Gold, U_Wood,
U_Shield, U_Dark, U_Feather, U_Horse*, U_Mane, Hoof, Rope, Leather, Saddle, Tint.
"""

import math

from mathutils import Matrix, Vector

from . import scenes_people as SP

TAU = math.tau
#: length of a standard's pole (m); the 2D icons use a shorter one so the figures stay large
STANDARD_LEN = [3.5]


# ---------------------------------------------------------------------------------------------
# lofting with metre UVs
# ---------------------------------------------------------------------------------------------
def frame_along(pts, i):
    a = Vector(pts[max(0, i - 1)])
    b = Vector(pts[min(len(pts) - 1, i + 1)])
    d = (b - a)
    if d.length < 1e-8:
        d = Vector((0, 0, 1))
    d.normalize()
    ref = Vector((0, -1, 0)) if abs(d.y) < 0.9 else Vector((1, 0, 0))
    ex = ref.cross(d).normalized()
    ey = d.cross(ex).normalized()
    return ex, ey


def loft(mb, rings, mat, closed=True, smooth=True, cap0=False, cap1=False, arc_uv=True):
    """Quads between point rings (lists of Vectors, equal length); MetreUV u = arc length around
    the ring, v = distance along the loft (metres)."""
    n = len(rings[0])
    ids = [[mb.v(tuple(p)) for p in r] for r in rings]
    vs = [0.0]
    for k in range(1, len(rings)):
        ca = sum((Vector(p) for p in rings[k - 1]), Vector()) / n
        cb = sum((Vector(p) for p in rings[k]), Vector()) / n
        vs.append(vs[-1] + (cb - ca).length)
    us = []
    for r in rings:
        u = [0.0]
        for i in range(1, n + (1 if closed else 0)):
            u.append(u[-1] + (Vector(r[i % n]) - Vector(r[i - 1])).length)
        us.append(u)
    for k in range(len(rings) - 1):
        for i in range(n if closed else n - 1):
            j = (i + 1) % n
            q = (ids[k][i], ids[k][j], ids[k + 1][j], ids[k + 1][i])
            uj0 = us[k][i + 1]
            uj1 = us[k + 1][i + 1]
            uv = [(us[k][i], vs[k]), (uj0, vs[k]), (uj1, vs[k + 1]), (us[k + 1][i], vs[k + 1])]
            mb.face(q, mat, uv, smooth)
    if cap0:
        mb.face(ids[0][::-1], mat, smooth=smooth)
    if cap1:
        mb.face(ids[-1], mat, smooth=smooth)
    return ids


def ring_pts(c, ex, ey, rx, ry, n, a0=0.0, a1=TAU, closed=True, bulge=None):
    out = []
    m = n if closed else n + 1
    for i in range(m):
        a = a0 + (a1 - a0) * i / n
        k = bulge(a) if bulge else 1.0
        out.append(Vector(c) + ex * (math.cos(a) * rx * k) + ey * (math.sin(a) * ry * k))
    return out


def tube(mb, pts, radii, mat, sides=10, cap0=True, cap1=True, scale=(1.0, 1.0)):
    rings = []
    for i, p in enumerate(pts):
        ex, ey = frame_along(pts, i)
        rings.append(ring_pts(p, ex, ey, radii[i] * scale[0], radii[i] * scale[1], sides))
    return loft(mb, rings, mat, cap0=cap0, cap1=cap1)


def ellipsoid_uv(mb, c, r, mat, seg=14, rings=10, rot=None):
    """Ellipsoid with UV (u = angle / 2pi from +x counter-clockwise, v = 0 bottom .. 1 top):
    the face material finds the features from it (front = -y = u 0.75)."""
    rot = rot or Matrix.Identity(3)
    verts = []
    for k in range(rings + 1):
        t = math.pi * k / rings
        row = []
        for i in range(seg + 1):
            a = TAU * i / seg
            p = Vector((math.sin(t) * math.cos(a) * r[0], math.sin(t) * math.sin(a) * r[1], -math.cos(t) * r[2]))
            row.append((mb.v(tuple(Vector(c) + rot @ p)), (i / seg, k / rings)))
        verts.append(row)
    for k in range(rings):
        for i in range(seg):
            a, b, cc, d = verts[k][i], verts[k][i + 1], verts[k + 1][i + 1], verts[k + 1][i]
            mb.face((a[0], b[0], cc[0], d[0]), mat, [a[1], b[1], cc[1], d[1]], smooth=True)


def lathe_at(mb, profile, mat, M, seg=14, smooth=True, cap_top=False, angle_range=(0.0, TAU)):
    s = mb.n
    mb.lathe(profile, mat, seg, smooth=smooth, cap_top=cap_top, angle_range=angle_range)
    mb.transform(s, M)


# ---------------------------------------------------------------------------------------------
# extra poses
# ---------------------------------------------------------------------------------------------
POSES = {
    "brace": dict(drop=0.12, bend=12, twist=-10, armL=(70, 22, 72), armR=(48, 16, 64),
                  legL=(34, 10, 34), legR=(-24, 10, 16), head=(-6, 0)),
    "thrust2": dict(drop=0.14, bend=16, twist=-12, armL=(72, 10, 30), armR=(62, 14, 58),
                    legL=(44, 8, 50), legR=(-30, 6, 10), head=(-8, 0)),
    "advance": dict(drop=0.04, bend=8, twist=-6, armL=(55, 14, 70), armR=(38, 10, 70),
                    legL=(26, 6, 18), legR=(-20, 6, 26), head=(-2, 0)),
    "draw": dict(drop=0.04, bend=4, twist=-68, armL=(90, 0, 0), armR=(88, 18, 148),
                 legL=(18, 16, 10), legR=(-14, 16, 8), head=(-2, -66)),
    "draw_up": dict(drop=0.04, bend=-6, twist=-62, armL=(112, 0, 0), armR=(106, 16, 150),
                    legL=(18, 16, 10), legR=(-14, 16, 8), head=(-16, -60)),
    "kneel_draw": dict(drop=0.42, bend=6, twist=-64, armL=(98, 0, 0), armR=(94, 18, 148),
                       legL=(92, 10, 150), legR=(-8, 12, 92), head=(-6, -62), kneel=True),
    "standard": dict(drop=0.02, bend=2, armL=(40, 10, 70), armR=(28, 12, 60), legL=(10, 6, 6),
                     legR=(-8, 6, 10), head=(-4, 0)),
    "command": dict(drop=0.02, bend=2, twist=8, armL=(20, 18, 40), armR=(118, 26, 10),
                    legL=(16, 8, 8), legR=(-10, 8, 12), head=(-6, 8)),
    "ride_lance": dict(drop=0.0, bend=18, armL=(48, 12, 46), armR=(78, 18, 30), legL=(70, 38, 75),
                       legR=(70, 38, 75), head=(-10, 0), ride=True),
    "ride_up": dict(drop=0.0, bend=6, armL=(42, 12, 50), armR=(64, 16, 64), legL=(70, 38, 75),
                    legR=(70, 38, 75), head=(-4, 0), ride=True),
}


def skeleton(pose, height, rng, jitter):
    p = POSES.get(pose, pose)
    return SP.Skeleton(p if not isinstance(p, str) else p, height, rng, jitter)


# ---------------------------------------------------------------------------------------------
# soldier
# ---------------------------------------------------------------------------------------------
def soldier(mb, rng, pose="advance", kind="infantry", weapon="spear", shield=False, height=1.74, jitter=3.0,
            plume=True, banner=False, quiver=False, sword=True, spear_dir=None, coat=None):
    """One dressed, armed figure into ``mb`` (origin between the feet, facing -Y).  ``kind``:
    'infantry' (iron lamellar), 'cavalry' (lacquered lamellar), 'archer' (padded coat,
    lamellar shoulders), 'officer'.  Returns the Skeleton."""
    sk = skeleton(pose, height, rng, jitter)
    s = sk.s
    R = sk.R
    up = sk.up
    ex, ey = R @ Vector((1, 0, 0)), R @ Vector((0, 1, 0))
    fwd = -ey
    armour = {"infantry": "U_Lamellar", "cavalry": "U_LamellarRed", "archer": "U_Coat",
              "officer": "U_LamellarRed"}[kind]
    if coat:
        armour = coat
    pel = sk.pelvis
    riding = bool(sk.p.get("ride"))
    # ---- legs ----------------------------------------------------------------------------
    for side in (1, -1):
        L = sk.leg[side]
        hip, kn, an = L["hip"], L["knee"], L["ankle"]
        tube(mb, [hip + up * 0.03 * s, (hip + kn) * 0.5, kn], [0.092 * s, 0.084 * s, 0.066 * s], "U_Trousers", 10,
             cap0=False, cap1=False)
        tube(mb, [kn - (kn - hip).normalized() * 0.03 * s, kn + (an - kn) * 0.5, an + Vector((0, 0, 0.02 * s))],
             [0.064 * s, 0.056 * s, 0.047 * s], "U_Wrap", 9, cap0=False, cap1=False)
        # boot: from the ankle along the foot
        fw = Vector((0, -1, 0))
        if sk.p.get("kneel") and side == 1:
            fw = (an - kn).normalized()
        if riding:
            fw = Vector((0, -0.6, -0.5)).normalized()
        heel = an - fw * 0.05 * s + Vector((0, 0, -0.05 * s))
        toe = an + fw * 0.19 * s + Vector((0, 0, -0.055 * s))
        tube(mb, [an + Vector((0, 0, 0.05 * s)), an - Vector((0, 0, 0.02 * s)), (an + toe) * 0.5 - Vector((0, 0, 0.02 * s)), toe],
             [0.05 * s, 0.054 * s, 0.045 * s, 0.03 * s], "U_Leather", 9, scale=(1.0, 1.0))
        tube(mb, [heel, an - Vector((0, 0, 0.03 * s))], [0.035 * s, 0.045 * s], "U_Leather", 8)
    # ---- torso ---------------------------------------------------------------------------
    rings = []
    spec = [(-0.05, 0.165, 0.118), (0.06, 0.152, 0.106), (0.2, 0.158, 0.112), (0.34, 0.178, 0.125),
            (0.44, 0.192, 0.13), (0.5, 0.17, 0.11)]
    tor_pts = []
    for (t, rx, ry) in spec:
        c = pel + up * (t * s / 0.5 * 0.5)
        if t > 0.42:
            c = sk.neck - up * (0.5 - t) * s
        tor_pts.append((c, rx * s * 1.07, ry * s * 1.07))
    rings = [ring_pts(c, ex, ey, rx, ry, 16) for (c, rx, ry) in tor_pts]
    loft(mb, rings, armour, cap1=True)
    # collar + neck
    nk = sk.neck
    tube(mb, [nk - up * 0.04 * s, nk + up * 0.03 * s], [0.085 * s, 0.075 * s], "U_Sleeve", 12, cap0=False)
    tube(mb, [nk, sk.head - sk.Rh @ Vector((0, 0, 0.08 * s))], [0.052 * s, 0.048 * s], "U_Skin", 10, cap0=False)
    # ---- tabard (Tint): front and back panels over the cuirass, hanging into flaps ------------
    waist = pel + up * 0.06 * s
    for side in (-1, 1):                         # -1 front (-y), +1 back
        ctr = -math.pi / 2 if side < 0 else math.pi / 2
        a0, a1 = ctr - 0.95, ctr + 0.95
        panel = []
        for (c, rx, ry) in tor_pts[1:5]:
            panel.append(ring_pts(c, ex, ey, rx + 0.016 * s, ry + 0.016 * s, 8, a0, a1, closed=False))
        # flap below the belt: straight down (slightly flared, follows the body lean)
        base = panel[0]
        cfl = waist - up * 0.0
        for k, dz in enumerate((0.16, 0.34)):
            fl = []
            for i, p in enumerate(base):
                q = p - Vector((0, 0, dz * s)) + ey * side * 0.03 * s * (k + 1)
                w = (i / (len(base) - 1)) - 0.5
                q += ex * w * 0.02 * s * (k + 1)
                fl.append(q)
            panel.insert(0, fl)
        loft(mb, panel, "Tint", closed=False)
        loft(mb, [r[::-1] for r in panel], "Tint", closed=False)       # back side of the cloth
    # belt + buckle
    tube(mb, [waist - up * 0.03 * s, waist + up * 0.03 * s], [0.178 * s * 1.07, 0.178 * s * 1.07], "U_Leather", 16,
         cap0=False, cap1=False, scale=(1.0, 0.72))
    mb.sphere(tuple(waist - ey * 0.135 * s), 0.028 * s, "U_Gold", 8, 5, scale=(1.3, 0.6, 1.0))
    # ---- tassets: lamellar skirt panels over the hips -----------------------------------------
    for side in (1, -1):
        L = sk.leg[side]
        dirx = ex * side
        top = []
        bot = []
        thigh = (L["knee"] - L["hip"]).normalized()
        for i in range(7):
            a = -1.05 + 2.1 * i / 6
            dvec = (dirx * math.cos(a) + fwd * math.sin(a) * 0.9).normalized()
            pt = waist - up * 0.02 * s + dvec * 0.185 * s + ey * 0.0
            top.append(pt)
            bot.append(L["hip"] + dvec * 0.13 * s + thigh * 0.27 * s + dirx * 0.03 * s)
        mid = [(a + b) * 0.5 + (a - (waist - up * 0.02 * s)).normalized() * 0.02 * s for a, b in zip(top, bot)]
        loft(mb, [top, mid, bot], armour if kind != "archer" else "U_Lamellar", closed=False)
        loft(mb, [bot[::-1], mid[::-1], top[::-1]], armour if kind != "archer" else "U_Lamellar", closed=False)
    # ---- arms ----------------------------------------------------------------------------
    for side in (1, -1):
        A = sk.arm[side]
        sh, el, wr, hd = A["shoulder"], A["elbow"], A["wrist"], A["hand"]
        tube(mb, [sh + (sh - sk.neck).normalized() * 0.01, (sh + el) * 0.5, el], [0.072 * s, 0.066 * s, 0.056 * s],
             "U_Sleeve", 10, cap0=True, cap1=False)
        tube(mb, [el - (el - sh).normalized() * 0.03 * s, (el + wr) * 0.5, wr], [0.058 * s, 0.054 * s, 0.045 * s],
             "U_Leather" if kind != "archer" else "U_Sleeve", 10, cap0=False, cap1=True)
        mb.sphere(tuple(hd), 0.042 * s, "U_Skin", 8, 6, scale=(0.85, 0.7, 1.15))
        # shoulder guard: layered lamellar caps
        d_out = (sh - sk.neck).normalized()
        q = (d_out * 0.62 + up * 0.38).normalized().to_track_quat("Z", "Y")
        for k, (r0, h0) in enumerate(((0.135, 0.0), (0.12, 0.05))):
            lathe_at(mb, [(r0 * s, -0.11 * s), (r0 * 0.92 * s, -0.03 * s), (r0 * 0.7 * s, 0.04 * s), (0.02 * s, 0.07 * s)],
                     "U_Lamellar" if kind == "archer" else armour,
                     Matrix.Translation(sh + d_out * (0.035 + 0.02 * k) * s + up * (0.02 + h0) * s) @ q.to_matrix().to_4x4(),
                     seg=12)
    # ---- head ----------------------------------------------------------------------------
    Rh = sk.Rh
    hr = sk.B["head_r"]
    hc = sk.head
    hup = Rh @ Vector((0, 0, 1))
    ellipsoid_uv(mb, hc, (hr * 0.84, hr * 0.92, hr * 1.1), "U_Face", 16, 11, Rh)
    # helmet bowl (iron, gilt rim), brim, neck guard flaps, spike with a Tint tassel
    hb = hc + hup * hr * 0.46          # the brim sits above the brows: the face shows
    M = Matrix.Translation(hb) @ Rh.to_4x4()
    lathe_at(mb, [(hr * 1.02, -hr * 0.18), (hr * 1.05, hr * 0.25), (hr * 0.92, hr * 0.62), (hr * 0.6, hr * 0.9),
                  (hr * 0.22, hr * 1.02), (0.0, hr * 1.05)], "U_Helm", M, seg=16)
    lathe_at(mb, [(hr * 1.06, -hr * 0.22), (hr * 1.12, -hr * 0.16), (hr * 1.07, -hr * 0.1)], "U_Gold", M, seg=16)
    # neck guard (顿项): a flared skirt round the back and sides
    lathe_at(mb, [(hr * 1.05, -hr * 0.15), (hr * 1.18, -hr * 0.55), (hr * 1.32, -hr * 0.95)], "U_Lamellar", M,
             seg=12, angle_range=(math.radians(-15), math.radians(195)))
    lathe_at(mb, [(hr * 1.32, -hr * 0.95), (hr * 1.18, -hr * 0.55), (hr * 1.05, -hr * 0.15)], "U_Lamellar", M,
             seg=12, angle_range=(math.radians(-15), math.radians(195)))
    spike0 = hb + hup * hr * 1.02
    mb.cylinder(tuple(spike0), tuple(spike0 + hup * hr * 0.55), 0.012 * s, 0.006 * s, "U_Gold", 6)
    if plume:
        tp = spike0 + hup * hr * 0.42
        # tassel (红缨): a cone of cords falling from the spike
        lathe_at(mb, [(0.0, 0.0), (0.03 * s, -0.025 * s), (0.065 * s, -0.09 * s), (0.08 * s, -0.15 * s),
                      (0.06 * s, -0.17 * s), (0.0, -0.13 * s)], "Tint",
                 Matrix.Translation(tp) @ Rh.to_4x4(), seg=12)
    # ---- weapons -------------------------------------------------------------------------
    hand = sk.arm[-1]["hand"]
    handL = sk.arm[1]["hand"]
    info = {"sk": sk}
    if weapon in ("spear", "lance", "standard"):
        if spear_dir is not None:
            d = Vector(spear_dir).normalized()
        else:
            d = (handL - hand)
            d = d.normalized() if d.length > 0.05 else Vector((0.05, -0.1, 1.0)).normalized()
            if d.z < -0.2:
                d = (d + Vector((0, 0, 0.3))).normalized()
        Lp = {"spear": 2.9, "lance": 2.5, "standard": STANDARD_LEN[0]}[weapon] * s
        back = 0.32 * Lp if weapon != "standard" else 0.12 * Lp
        p0 = hand - d * back
        p1 = hand + d * (Lp - back)
        if p0.z < 0.02 and not riding:
            p0 = p0 + d * ((0.02 - p0.z) / max(d.z, 0.05)) if d.z > 0.05 else p0
        mb.cylinder(tuple(p0), tuple(p1), 0.016 * s, 0.014 * s, "U_Wood", 7)
        if weapon != "standard":
            ex2 = d.cross(Vector((0, 0, 1)))
            if ex2.length < 1e-3:
                ex2 = Vector((1, 0, 0))
            ex2.normalize()
            ey2 = d.cross(ex2).normalized()
            tip = p1 + d * 0.3 * s
            bw = 0.04 * s
            ring = [p1 + d * 0.07 * s + ex2 * bw, p1 + d * 0.07 * s + ey2 * 0.012 * s, p1 + d * 0.07 * s - ex2 * bw,
                    p1 + d * 0.07 * s - ey2 * 0.012 * s]
            ids0 = mb.v(tuple(p1 - d * 0.01))
            idr = [mb.v(tuple(q)) for q in ring]
            idt = mb.v(tuple(tip))
            for i in range(4):
                j = (i + 1) % 4
                mb.face((ids0, idr[j], idr[i]), "U_Steel")
                mb.face((idr[i], idr[j], idt), "U_Steel")
            # Tint tassel under the blade
            lathe_at(mb, [(0.0, 0.0), (0.03 * s, -0.02 * s), (0.05 * s, -0.08 * s), (0.04 * s, -0.11 * s), (0.0, -0.09 * s)],
                     "Tint", Matrix.Translation(p1 - d * 0.02) @ d.to_track_quat("Z", "Y").to_matrix().to_4x4(), seg=10)
        else:
            flag(mb, rng, p1 - d * 0.05, d, s)
            mb.cylinder(tuple(p1), tuple(p1 + d * 0.22 * s), 0.02 * s, 0.0, "U_Gold", 6)
        info["spear_tip"] = p1
    elif weapon == "bow":
        A = sk.arm[1]
        c = A["hand"]
        d = A["dir"]
        upb = (R @ Vector((0, 0, 1)))
        upb = (upb - d * upb.dot(d)).normalized()
        pts = []
        for k in range(13):
            t = (k / 12) * 2 - 1
            curve = 0.16 * s * (1 - t * t) - 0.05 * s * (abs(t) ** 3)
            pts.append(c + upb * t * 0.62 * s + d * curve)
        tube(mb, pts, [0.014 * s * (1.2 - 0.5 * abs((k / 12) * 2 - 1)) for k in range(13)], "U_Wood", 6)
        mb.cylinder(tuple(c - upb * 0.06 * s), tuple(c + upb * 0.06 * s), 0.02 * s, 0.02 * s, "U_Gold", 6)
        nock = sk.arm[-1]["hand"]
        mb.cylinder(tuple(pts[0]), tuple(nock), 0.0035 * s, 0.0035 * s, "U_Dark", 4)
        mb.cylinder(tuple(nock), tuple(pts[-1]), 0.0035 * s, 0.0035 * s, "U_Dark", 4)
        # nocked arrow
        ad = (c - nock).normalized()
        a1 = c + ad * 0.12 * s
        mb.cylinder(tuple(nock - ad * 0.02), tuple(a1), 0.006 * s, 0.006 * s, "U_Wood", 5)
        mb.cylinder(tuple(a1), tuple(a1 + ad * 0.07 * s), 0.012 * s, 0.0, "U_Steel", 5)
        for k in range(3):
            a = TAU * k / 3
            fv = (upb * math.cos(a) + d.cross(upb) * math.sin(a)) * 0.02 * s
            mb.cylinder(tuple(nock + ad * 0.02 * s + fv * 0.2), tuple(nock + ad * 0.12 * s + fv), 0.004 * s, 0.002 * s,
                        "U_Feather", 3)
    if shield:
        A = sk.arm[1]
        c = A["wrist"] + (R @ Vector((0.05 * s, -0.09 * s, 0.03 * s)))
        nrm = (R @ Vector((0.35, -1.0, 0.0))).normalized()
        q = nrm.to_track_quat("Z", "Y").to_matrix().to_4x4()
        r = 0.34 * s
        lathe_at(mb, [(0.0, 0.05 * s), (r * 0.25, 0.048 * s), (r * 0.7, 0.03 * s), (r, 0.0), (r, -0.02 * s),
                      (r * 0.92, -0.02 * s), (0.0, -0.01 * s)], "U_Shield", Matrix.Translation(c) @ q, seg=20)
        mb.sphere(tuple(c + nrm * 0.055 * s), 0.05 * s, "U_Gold", 10, 6, scale=(1, 1, 0.6))
    if quiver:
        b0 = sk.chest + (R @ Vector((0.1 * s, 0.17 * s, -0.22 * s)))
        b1 = sk.chest + (R @ Vector((0.03 * s, 0.2 * s, 0.22 * s)))
        tube(mb, [b0, b1], [0.055 * s, 0.065 * s], "U_Leather", 10)
        for k in range(6):
            off = (R @ Vector(((k % 3 - 1) * 0.025 * s, 0.0, 0.0))) + (R @ Vector((0, (k // 3) * 0.02 * s, 0)))
            mb.cylinder(tuple(b1 + off), tuple(b1 + off + (b1 - b0).normalized() * 0.16 * s), 0.006 * s, 0.006 * s,
                        "U_Wood", 4)
            mb.cylinder(tuple(b1 + off + (b1 - b0).normalized() * 0.1 * s), tuple(b1 + off + (b1 - b0).normalized() * 0.2 * s),
                        0.018 * s, 0.004 * s, "U_Feather", 4)
    if sword and weapon not in ("standard",) and not riding:
        # scabbarded sword at the left hip
        h0 = waist + ex * 0.19 * s - ey * 0.02 * s
        mb.cylinder(tuple(h0 + up * 0.08 * s - ey * 0.08 * s), tuple(h0 - up * 0.55 * s + ey * 0.25 * s), 0.02 * s,
                    0.018 * s, "U_Dark", 6)
        mb.cylinder(tuple(h0 + up * 0.08 * s - ey * 0.08 * s), tuple(h0 + up * 0.22 * s - ey * 0.14 * s), 0.016 * s,
                    0.016 * s, "U_Gold", 6)
    return info


def flag(mb, rng, top, pole_dir, s, w=0.62, h=1.05):
    """Tall rectangular war banner (Tint) hanging from a crossbar, waving; mud-gold border
    tongues along the free edge."""
    ph = rng.uniform(0, TAU)
    W, H = w * s, h * s
    side = Vector((1, 0, 0))
    top = Vector(top)
    mb.cylinder(tuple(top - side * 0.03), tuple(top + side * W * 0.95), 0.012 * s, 0.012 * s, "U_Wood", 5)

    def fp(u, v):
        p = top + side * (u * W * 0.94) - Vector((0, 0, v * H))
        p += Vector((0, 0.1 * math.sin(u * 5.0 + ph + v * 1.4) * (0.25 + u) * s, 0))
        p += Vector((0, 0.05 * s * v * u, -0.04 * s * u * u))
        return tuple(p)
    mb.grid(fp, 8, 8, "Tint", uv_fn=lambda u, v: (u, v), smooth=True)
    mb.grid(fp, 8, 8, "Tint", uv_fn=lambda u, v: (u, v), smooth=True, flip=True)
    # border tongues (flame-shaped teeth) along the free edge and the hem, mud-gold
    for k in range(5):
        v0, v1 = k / 5, (k + 0.6) / 5
        a, b = Vector(fp(1.0, v0)), Vector(fp(1.0, v1))
        tip = (a + b) * 0.5 + side * 0.09 * s
        ids = [mb.v(tuple(a)), mb.v(tuple(b)), mb.v(tuple(tip))]
        mb.face(ids, "U_Gold")
        mb.face(ids[::-1], "U_Gold")
    for k in range(4):
        u0, u1 = k / 4, (k + 0.6) / 4
        a, b = Vector(fp(u0, 1.0)), Vector(fp(u1, 1.0))
        tip = (a + b) * 0.5 - Vector((0, 0, 0.09 * s))
        ids = [mb.v(tuple(a)), mb.v(tuple(b)), mb.v(tuple(tip))]
        mb.face(ids, "U_Gold")
        mb.face(ids[::-1], "U_Gold")


def horseman(mb, rng, at=(0, 0, 0), yaw=0.0, gait="trot", coat="U_HorseBay", pose="ride_lance", weapon="lance",
             scale=0.9, pennant=False, lance_dir=None):
    """A horse (court-painting horse, Tint saddle cloth and tassels) with an armoured rider."""
    from .geometry import MeshBuilder
    hm = MeshBuilder()
    sp = SP.horse(hm, rng, gait, coat=coat, mane="U_Mane", saddle="Saddle", tack="Tint", cloth="Tint", scale=1.0)
    fm = MeshBuilder()
    if lance_dir is None:
        lance_dir = (0.06, -1.0, 0.06) if pose == "ride_lance" else (0.04, -0.28, 1.0)
    info = soldier(fm, rng, pose, kind="cavalry", weapon=weapon if not pennant else "standard", sword=False,
                   jitter=2.0, spear_dir=Vector(lance_dir) if not pennant else Vector((0.03, 0.05, 1.0)))
    sk = info["sk"]
    hm.extend(fm, Matrix.Translation(sp - sk.pelvis + Vector((0, 0, -0.04))))
    mb.extend(hm, Matrix.Translation(Vector(at)) @ Matrix.Rotation(yaw, 4, "Z") @ Matrix.Scale(scale, 4))


# ---------------------------------------------------------------------------------------------
# squads (facing -Y, footprint <= 6 m, figures on z = 0 = the plinth top)
# ---------------------------------------------------------------------------------------------
def squad_infantry(mb, rng):
    """Seven spearmen: a front rank of three shield-bearers bracing levelled spears, a second
    rank advancing with spears slanted forward, the standard-bearer behind with the Tint
    banner."""
    fwd_low = Vector((0.0, -1.0, 0.12))
    rows = [((-1.05, -0.85), "brace", fwd_low, True), ((0.0, -1.0), "thrust2", Vector((0.05, -1.0, 0.08)), True),
            ((1.05, -0.8), "brace", Vector((-0.05, -1.0, 0.14)), True),
            ((-0.6, 0.35), "advance", Vector((0.05, -0.6, 0.8)), False),
            ((0.6, 0.3), "advance", Vector((-0.04, -0.55, 0.82)), False),
            ((-1.45, 0.55), "advance", Vector((0.0, -0.4, 0.9)), False)]
    for (x, y), pose, d, sh in rows:
        from .geometry import MeshBuilder
        sub = MeshBuilder()
        soldier(sub, rng, pose, "infantry", "spear", shield=sh, spear_dir=d, jitter=4.0)
        mb.extend(sub, Matrix.Translation(Vector((x, y, 0))) @ Matrix.Rotation(rng.uniform(-0.08, 0.08), 4, "Z"))
    from .geometry import MeshBuilder
    sub = MeshBuilder()
    soldier(sub, rng, "standard", "officer", "standard", spear_dir=Vector((0.06, 0.05, 1.0)), jitter=1.0)
    mb.extend(sub, Matrix.Translation(Vector((0.95, 1.25, 0))))


#: yaw (degrees) that turns each draw pose so its nocked arrow points along -Y (measured: the
#: unrotated arrows point 129 / 111 / 119 degrees from +X)
DRAW_YAW = {"draw": 36.0, "draw_up": 22.0, "kneel_draw": 29.0}


def squad_archers(mb, rng):
    """Seven archers: a kneeling front rank and a standing rank drawing their bows (shooting
    over), quivers on their backs, an officer behind with a Tint banner."""
    from .geometry import MeshBuilder
    spots = [((-1.1, -0.75), "kneel_draw"), ((0.0, -0.9), "kneel_draw"), ((1.1, -0.7), "kneel_draw"),
             ((-0.55, 0.35), "draw_up"), ((0.6, 0.3), "draw"), ((-1.6, 0.5), "draw_up")]
    for (x, y), pose in spots:
        sub = MeshBuilder()
        soldier(sub, rng, pose, "archer", "bow", quiver=True, sword=True, jitter=3.0)
        # the draw poses turn the body sideways (left shoulder to the target); turn each archer so
        # the nocked arrow points at the enemy (front, -Y)
        mb.extend(sub, Matrix.Translation(Vector((x, y, 0))) @ Matrix.Rotation(math.radians(DRAW_YAW[pose]) + rng.uniform(-0.06, 0.06), 4, "Z"))
    sub = MeshBuilder()
    soldier(sub, rng, "command", "officer", "standard", spear_dir=Vector((-0.05, 0.08, 1.0)), jitter=1.0)
    mb.extend(sub, Matrix.Translation(Vector((1.25, 1.2, 0))))


def squad_cavalry(mb, rng):
    """Five horsemen in a wedge: two leading with levelled lances, three behind (lances up,
    one carrying the Tint pennant), coats of bay, white, dun, chestnut and black."""
    spots = [((-0.62, -0.62), "U_HorseWhite", "ride_lance", "lance", False, "trot"),
             ((0.66, -0.5), "U_HorseBay", "ride_lance", "lance", False, "walk"),
             ((-1.5, 1.1), "U_HorseDun", "ride_up", "lance", False, "walk"),
             ((0.0, 1.3), "U_HorseChestnut", "ride_up", "lance", True, "stand"),
             ((1.5, 1.1), "U_HorseBlack", "ride_up", "lance", False, "trot")]
    for (x, y), coat, pose, wpn, pen, gait in spots:
        horseman(mb, rng, (x, y, 0.0), rng.uniform(-0.05, 0.05), gait, coat, pose, wpn, scale=0.86, pennant=pen)


# ---------------------------------------------------------------------------------------------
# 2D icon groups (Unit_<Type>.png): the same figures, fewer, so they read at 96 px
# ---------------------------------------------------------------------------------------------
def icon_infantry(mb, rng):
    """Two shield-bearers bracing spears, the standard-bearer between and behind them."""
    from .geometry import MeshBuilder
    for (x, y), pose, d in (((-0.5, -0.25), "brace", Vector((0.15, -1.0, 0.35))),
                            ((0.55, -0.1), "thrust2", Vector((0.1, -1.0, 0.3)))):
        sub = MeshBuilder()
        soldier(sub, rng, pose, "infantry", "spear", shield=True, spear_dir=d, jitter=2.0)
        mb.extend(sub, Matrix.Translation(Vector((x, y, 0))))
    sub = MeshBuilder()
    soldier(sub, rng, "standard", "officer", "standard", spear_dir=Vector((0.05, 0.05, 1.0)), jitter=1.0)
    mb.extend(sub, Matrix.Translation(Vector((0.05, 0.75, 0))))


def icon_archers(mb, rng):
    """A kneeling archer in front, a standing one drawing behind, a small banner."""
    from .geometry import MeshBuilder
    for (x, y), pose in (((-0.35, -0.3), "kneel_draw"), ((0.45, 0.35), "draw_up")):
        sub = MeshBuilder()
        soldier(sub, rng, pose, "archer", "bow", quiver=True, jitter=1.5)
        mb.extend(sub, Matrix.Translation(Vector((x, y, 0))) @ Matrix.Rotation(math.radians(DRAW_YAW[pose]), 4, "Z"))
    sub = MeshBuilder()
    soldier(sub, rng, "command", "officer", "standard", spear_dir=Vector((-0.05, 0.08, 1.0)), jitter=1.0)
    mb.extend(sub, Matrix.Translation(Vector((-0.75, 0.95, 0))))


def icon_cavalry(mb, rng):
    """A charging horseman with a levelled lance and a second with the pennant behind."""
    horseman(mb, rng, (0.35, -0.35, 0.0), 0.0, "trot", "U_HorseWhite", "ride_lance", "lance", scale=0.86)
    horseman(mb, rng, (-0.75, 0.9, 0.0), 0.0, "walk", "U_HorseBay", "ride_up", "lance", scale=0.86, pennant=True)
