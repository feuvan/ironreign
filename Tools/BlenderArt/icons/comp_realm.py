"""Icons family (gongbi), compositions: the realm's economy - Farm, Commerce, Gold, Food,
Population, Transport, Move, Market.

Each builder ``<Name>(M, cam)`` models its subject in the family conventions (+Z up, front -Y,
~2 units across) and returns ``dict(objs=[...], fill=1.0, offset=(dx, dy))``: ``fill`` < 1
balances the optical size of compact subjects, ``offset`` nudges the subject inside the keyline
(fractions of the box).  Objects default to the ``ink`` line set; ``gb.put(objs, 'soft')`` gives
finer grey lines (grain, steam), ``'none'`` no lines.
"""

import math

from common import _rows, _straw
from ironart import icons_gongbi as gb
from ironart import icons_kit as K
from ironart import icons_props as P

FACE = P.FACE
TILT = P.TILT
TAU = math.tau


# ---------------------------------------------------------------------------------------------
def _panicles(M, n=11, r0=0.22, z0=1.1, seed=5):
    """Ripe rice heads drooping from the top of a sheaf: per panicle a thin arching stalk and
    ~30 grains (small ellipsoids along the stalk, alternate sides, pointing outwards) joined into
    one mesh, so the ink draws every grain as a small granular stroke."""
    import random
    import bmesh
    import bpy
    from mathutils import Matrix, Vector
    rng = random.Random(seed)
    out = []
    for i in range(n):
        a = TAU * i / n + 0.35 + rng.uniform(-0.12, 0.12)
        ca, sa = math.cos(a), math.sin(a)
        L = 0.66 + rng.uniform(-0.08, 0.1)
        pts = []
        for k in range(12):
            t = k / 11.0
            rr = r0 + 0.52 * L * t
            z = z0 + 0.34 * math.sin(t * math.pi * 0.62) - 0.7 * L * t * t
            pts.append(Vector((ca * rr, sa * rr, z)))
        stalk = K.curve_tube("stalk%d" % i, [tuple(p) for p in pts], 0.012, M["straw"], 3, 8)
        bm = bmesh.new()
        ng = 30
        for g in range(ng):
            t = 0.32 + 0.66 * g / (ng - 1.0)
            f = t * 11.0
            k0 = min(10, int(f))
            p = pts[k0].lerp(pts[k0 + 1], f - k0)
            d = (pts[k0 + 1] - pts[k0]).normalized()
            side = Vector((-sa, ca, 0.0)) * (1 if g % 2 else -1)
            up = d.cross(side).normalized()
            gd = (d * 0.8 + side * 0.45 + up * rng.uniform(-0.2, 0.3)).normalized()
            gl = 0.07 * (1.0 - 0.35 * (g / ng)) * rng.uniform(0.9, 1.1)
            centre = p + side * 0.03 + gd * gl * 0.5
            ret = bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=5, radius=1.0)
            q = gd.to_track_quat("Z", "Y")
            mtx = Matrix.Translation(centre) @ q.to_matrix().to_4x4() @ \
                Matrix.Diagonal(Vector((gl * 0.42, gl * 0.36, gl * 0.62, 1.0)))
            bmesh.ops.transform(bm, matrix=mtx, verts=ret["verts"])
        me = bpy.data.meshes.new("grains%d" % i)
        bm.to_mesh(me)
        bm.free()
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
        o = K.link(bpy.data.objects.new("grains%d" % i, me))
        o.data.materials.append(M["grain"])
        out += [stalk, o]
    return out


def Farm(M, cam):
    """A rice sheaf tied at the waist, ripe heads drooping, a sickle leaning against it."""
    objs = []
    straw = gb.pigment("I_Sheaf", "#E8CF8E", "#A8843E", fen=0.65, ink=_straw(30.0, 0.07, 0.45))
    prof = [(0.0, 0.0), (0.36, 0.0), (0.33, 0.12), (0.24, 0.38), (0.17, 0.56), (0.2, 0.7),
            (0.3, 0.92), (0.36, 1.06), (0.3, 1.12), (0.0, 1.14)]
    body = K.lathe("sheaf", prof, straw, 48)
    objs.append(body)
    for k, dz in enumerate((0.0, 0.06)):
        tie = K.torus("tie%d" % k, 0.18, 0.028, M["rope_straw"], 48, 10)
        tie.location = (0, 0, 0.53 + dz)
        objs.append(tie)
    # drooping heads (panicles): a fine stalk arching over, hung with rice grains in pairs
    heads = _panicles(M, n=11, r0=0.22, z0=1.1, seed=5)
    objs += heads
    gb.put(heads, "soft")
    # sickle: crescent iron blade on a wooden handle, leaning on the front right
    outer = []
    inner = []
    for k in range(25):
        t = k / 24.0
        a = math.radians(-10 + 190 * t)
        outer.append((0.42 * math.cos(a), 0.42 * math.sin(a)))
        w = 0.1 * math.sin(math.pi * min(1.0, t * 1.05)) ** 0.6 + 0.004
        inner.append(((0.42 - w) * math.cos(a) + 0.03 * t, (0.42 - w) * math.sin(a) - 0.02 * t))
    blade = K.outline_mesh("sickle_blade", outer + inner[::-1], 0.03, M["steel"], plane="XZ")
    handle = K.lathe("sickle_handle", [(0.0, -0.58), (0.045, -0.58), (0.05, 0.0), (0.04, 0.04),
                                       (0.0, 0.04)], M["wood"], 16)
    handle.location = (0.41, 0, -0.02)
    sk = [blade, handle]
    sk = P.group("sickle", sk, (0.32, -0.42, 0.62), (0, -28, FACE + 8), 0.95)
    objs += sk
    return dict(objs=objs, fill=1.0, offset=(0.0, 0.0))


# ---------------------------------------------------------------------------------------------
def Commerce(M, cam):
    """An abacus standing tilted back, two copper cash on a red cord before it."""
    objs = []
    W, H, T = 1.3, 1.0, 0.1
    fr = M["wood_dark"]
    for k, (sx, sz, x, z) in enumerate(((W, 0.1, 0, H / 2), (W, 0.1, 0, -H / 2),
                                        (0.1, H + 0.1, -W / 2, 0), (0.1, H + 0.1, W / 2, 0))):
        b = K.box("frame%d" % k, (sx, T, sz), fr)
        b.location = (x, 0, z)
        objs.append(b)
    beam_z = H / 2 - 0.3
    beam = K.box("beam", (W, T * 0.8, 0.06), fr)
    beam.location = (0, 0, beam_z)
    objs.append(beam)
    rods = 6
    pushed_up = [1, 0, 1, 1, 0, 1]
    pushed_lo = [0, 1, 3, 2, 0, 1]
    for i in range(rods):
        x = -W / 2 + (i + 1) * W / (rods + 1)
        rod = K.cylinder("rod%d" % i, 0.014, H, M["bamboo"], 8, z0=-H / 2)
        rod.location = (x, 0, 0)
        objs.append(rod)
        bead_prof = [(0.0, -0.05), (0.03, -0.05), (0.088, 0.0), (0.03, 0.05), (0.0, 0.05)]
        up = [beam_z + 0.08, H / 2 - 0.1] if pushed_up[i] else [H / 2 - 0.2, H / 2 - 0.1]
        lo = []
        for j in range(5):
            if j < pushed_lo[i]:
                lo.append(beam_z - 0.09 - 0.1 * j)
            else:
                lo.append(-H / 2 + 0.07 + 0.1 * (4 - j))
        for j, z in enumerate(up + lo):
            bd = K.lathe("bead%d_%d" % (i, j), bead_prof,
                         M["lacquer_red"] if j < 2 else M["wood"], 20)
            bd.location = (x, 0, z)
            objs.append(bd)
    out = list(P.group("abacus", objs, (-0.1, 0.25, 0.78), (-14, 0, FACE + 6)))
    coins = []
    for k, (x, z, rz, rx) in enumerate(((-0.12, 0.2, -6, 10), (0.3, 0.12, 12, 12))):
        c = P.coin("coin%d" % k, M["bronze"], 0.3, 0.05, 0.08)
        coins += P.group("coinG%d" % k, c, (x, -0.62 - 0.05 * k, z), (rx, 0, rz + FACE))
    cordp = [(-0.5, -0.56, 0.32), (-0.12, -0.66, 0.2), (0.3, -0.74, 0.12), (0.62, -0.74, 0.0)]
    cd = P.cord("cord", M["rope_red"], cordp, 0.03)
    out += coins + [cd]
    out += P.tassel("cash_ts", M["tassel_red"], (-0.52, -0.56, 0.32), 0.4, 0.07)
    return dict(objs=out, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Gold(M, cam):
    """Gold yuanbao (元宝): two boat-shaped ingots with high flaring ends in front, a third set
    on top behind them."""
    objs = []
    kw = dict(L=1.0, W=0.78, rim=0.3, wing=0.3, trough=0.2, dome=(0.26, 0.22, 0.24),
              flare=0.18, lip=(0.12, 0.06), sq=2.6, boss_lift=0.55)
    objs += P.group("ingotA", P.yuanbao("ingA", M["gold"], **kw), (-0.52, 0.0, 0.0), (0, 0, -14))
    objs += P.group("ingotB", P.yuanbao("ingB", M["gold"], **kw), (0.54, 0.08, 0.0), (0, 0, 12))
    objs += P.group("ingotC", P.yuanbao("ingC", M["gold"], **kw), (0.02, 0.36, 0.42), (0, 0, -3),
                    1.08)
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Food(M, cam):
    """A tied hemp rice sack with a gathered, ruffled mouth, and a blue-and-white bowl heaped
    with rice."""
    objs = []
    hemp = gb.pigment("I_Sack", "#DCC497", "#8E7048", fen=0.75, ink=_rows(2, 8.0, 0.05, 0.2))

    def sack(u, v):
        a = TAU * u
        # profile: v 0 bottom .. 1 top of the ruffle
        prof = [(0.0, 0.42, 0.0), (0.1, 0.56, 0.06), (0.35, 0.6, 0.42), (0.6, 0.48, 0.78),
                (0.75, 0.24, 0.98), (0.8, 0.15, 1.05), (0.85, 0.2, 1.12), (0.93, 0.32, 1.26),
                (1.0, 0.36, 1.32)]
        for i in range(len(prof) - 1):
            if prof[i][0] <= v <= prof[i + 1][0]:
                t = (v - prof[i][0]) / (prof[i + 1][0] - prof[i][0])
                t = t * t * (3 - 2 * t)
                r = prof[i][1] + (prof[i + 1][1] - prof[i][1]) * t
                z = prof[i][2] + (prof[i + 1][2] - prof[i][2]) * t
                break
        fold = 1.0 + (0.12 * math.sin(a * 9) if v > 0.78 else 0.03 * math.sin(a * 5 + v * 3))
        if v < 0.02:
            r *= v / 0.02
        return (r * fold * math.cos(a), r * fold * math.sin(a) * 0.88, z)
    sk = K.grid("sack", sack, 72, 40, hemp)
    objs.append(sk)
    tie = K.torus("sack_tie", 0.17, 0.035, M["rope_red"], 32, 8)
    tie.location = (0, 0, 1.05)
    objs.append(tie)
    lab = gb.pigment("I_SackLabel", "#CC5038", "#8A2A20", fen=0.3,
                     image=P.glyph_image("SackGlyph", "米", gb_font(), 256, 0.72,
                                         color=(240, 232, 216)), image_color="#F0E8D8")
    label = K.grid("sack_label", lambda u, v: (
        0.32 * math.sin((u - 0.5) * 1.1), -0.585 * 0.88 * math.cos((u - 0.5) * 1.1) - 0.01,
        0.26 + v * 0.34), 8, 2, lab)
    objs.append(label)
    out = P.group("sackG", objs, (-0.32, 0.22, 0), (0, 0, 12))
    blue = gb.pigment("I_BowlBW", "#F6F2E8", "#B8C0C8", fen=0.7)
    bw = P.bowl("bowl", blue, 0.48, 0.32, 0.16)
    band = K.lathe("bowl_band", [(0.44, 0.255), (0.47, 0.27), (0.48, 0.3), (0.46, 0.3),
                                 (0.43, 0.27), (0.42, 0.26)], M["silk_azure"], 64)
    heap = K.lathe("rice", [(0.0, 0.5), (0.2, 0.48), (0.35, 0.41), (0.45, 0.31), (0.0, 0.3)],
                   M["rice"], 48)
    out += P.group("bowlG", [bw, band, heap], (0.5, -0.45, 0.0), (0, 0, 0))
    return dict(objs=out, fill=1.0)


def gb_font():
    from common import FONT_BRUSH
    return FONT_BRUSH


# ---------------------------------------------------------------------------------------------
def Population(M, cam):
    """Tiled houses (界画): a hall behind, two cottages before it."""
    objs = []
    objs += P.group("h1", P.house("h1", M, 1.2, 0.75, 0.5, 0.42, 0.17), (0.3, 0.55, 0.0),
                    (0, 0, 0))
    objs += P.group("h2", P.house("h2", M, 0.85, 0.6, 0.42, 0.34, 0.14), (-0.6, -0.2, 0.0),
                    (0, 0, 0))
    objs += P.group("h3", P.house("h3", M, 0.75, 0.55, 0.38, 0.3, 0.13), (0.55, -0.6, 0.0),
                    (0, 0, 0))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def _wheel(name, M, r=0.42, spokes=12, w=0.08):
    objs = []
    rim = K.torus(name + "_rim", r, w * 0.5, M["wood"], 64, 10, scale_minor=(1.0, 1.2))
    objs.append(rim)
    hub = K.cylinder(name + "_hub", 0.08, 0.16, M["wood_dark"], 20, z0=-0.08)
    objs.append(hub)
    for i in range(spokes):
        a = TAU * i / spokes
        sp = K.tube(name + "_sp%d" % i, [(0.06 * math.cos(a), 0.06 * math.sin(a), 0),
                                        ((r - 0.02) * math.cos(a), (r - 0.02) * math.sin(a), 0)],
                    0.018, M["wood"], 8)
        objs.append(sp)
    return objs


def _ox(name, M):
    """A placid ox in profile facing -X (metaballs): barrel body, shoulder hump, deep chest and
    dewlap, lowered head with a broad muzzle, crescent horns, dark hooves, tail."""
    els = [
        dict(type="ELLIPSOID", co=(-1.25, 0, 0.86), radius=0.6, size=(1.25, 0.72, 0.66)),
        dict(type="BALL", co=(-1.68, 0, 0.95), radius=0.42),
        dict(type="ELLIPSOID", co=(-1.78, 0, 0.7), radius=0.45, size=(0.8, 0.8, 1.0)),
        dict(type="BALL", co=(-0.78, 0, 0.84), radius=0.46),
        dict(type="ELLIPSOID", co=(-2.05, 0, 0.82), radius=0.32, size=(1.2, 0.8, 0.9),
             rot=(0, 30, 0)),
        dict(type="ELLIPSOID", co=(-2.3, 0, 0.62), radius=0.28, size=(0.85, 0.72, 1.25),
             rot=(0, -25, 0)),
        dict(type="BALL", co=(-2.38, 0, 0.42), radius=0.18),
        dict(type="ELLIPSOID", co=(-2.0, 0, 0.5), radius=0.2, size=(0.8, 0.5, 1.3)),
    ]
    legs = ((-1.78, -0.2), (-1.66, 0.2), (-0.86, -0.2), (-0.74, 0.2))
    out = [K.metaball(name, els, M["ox"], resolution=0.022, threshold=0.6)]
    # legs: separate jointed forms (forearm / cannon) so the ink draws knees and hocks
    for k, (x, y) in enumerate(legs):
        front = x < -1.2
        knee = (x + (0.03 if front else -0.06), y, 0.36)
        pts = [(x + (0.0 if front else 0.08), y, 0.72), knee, (x, y, 0.06)]
        out.append(K.curve_tube(name + "_leg%d" % k, pts, 0.1, M["ox"], 6, 10,
                                radius_fn=lambda t: 1.0 - 0.45 * t))
        h = K.cylinder(name + "_hoof%d" % k, 0.065, 0.08, M["iron_dark"], 12)
        h.location = (x, y, 0.0)
        out.append(h)
    for sy in (-1, 1):
        out.append(K.curve_tube(name + "_horn%d" % sy, [(-2.22, sy * 0.1, 0.88),
                                                        (-2.18, sy * 0.3, 0.96),
                                                        (-2.28, sy * 0.4, 1.12)], 0.05,
                                M["bone"], 3, 8, radius_fn=lambda t: 1.0 - 0.8 * t))
    out.append(K.curve_tube(name + "_tail", [(-0.5, 0, 1.02), (-0.44, 0.0, 0.76),
                                            (-0.46, 0.0, 0.46)], 0.03, M["wood_dark"], 3, 8))
    return out


def Transport(M, cam):
    """Army supply: a sturdy ox (metaballs) drawing a big two-wheeled cart piled with hemp
    grain sacks lashed down with red rope, turned towards the viewer."""
    objs = []
    cart = []
    bed = K.box("bed", (1.2, 0.85, 0.08), M["wood"])
    bed.location = (0.6, 0, 0.55)
    cart.append(bed)
    for sy in (-1, 1):
        rail = K.box("rail%d" % sy, (1.2, 0.05, 0.18), M["wood_dark"])
        rail.location = (0.6, sy * 0.42, 0.68)
        cart.append(rail)
    prof = [(0.0, 0.0), (0.2, 0.0), (0.26, 0.08), (0.27, 0.22), (0.2, 0.34), (0.08, 0.38),
            (0.1, 0.44), (0.0, 0.44)]
    for k, (x, y, z, s) in enumerate(((0.3, 0.16, 0.59, 1.15), (0.9, -0.14, 0.59, 1.1),
                                      (0.36, -0.2, 0.59, 1.05), (0.9, 0.2, 0.59, 1.05),
                                      (0.6, 0.0, 0.98, 1.1))):
        sk = K.lathe("load%d" % k, prof, M["hemp"], 32, scale_xy=(1.0, 0.85))
        sk.location = (x, y, z)
        sk.scale = (s, s, s)
        cart.append(sk)
    for k, x in enumerate((0.36, 0.86)):
        cart.append(P.cord("lash%d" % k, M["rope_red"], [(x, -0.44, 0.7), (x, -0.36, 1.12),
                                                       (x - 0.04, 0.0, 1.42), (x, 0.36, 1.12),
                                                       (x, 0.44, 0.7)], 0.022))
    cart += P.group("wheel", _wheel("wh", M, 0.48, 12, 0.1), (0.6, -0.5, 0.48), (90, 0, 0))
    S_ = 1.3
    objs += P.group("cartG", cart, (0.0, 0.0, 0.0), (0, 0, 0), S_)
    for sy in (-1, 1):
        objs.append(K.tube("shaft%d" % sy, [(0.05, sy * 0.36 * S_, 0.56 * S_),
                                            (-0.9, sy * 0.4, 0.95), (-1.75, sy * 0.42, 1.2)],
                           0.04, M["wood_dark"], 8))
    objs += _ox("ox", M)
    yoke = K.tube("yoke", [(-1.72, -0.44, 1.22), (-1.72, 0.44, 1.22)], 0.055, M["wood_dark"], 8)
    objs.append(yoke)
    out = P.group("cart", objs, (0.0, 0, 0), (0, 0, -50))
    return dict(objs=out, fill=1.0)


# ---------------------------------------------------------------------------------------------
def _sandal(name, M, side=1):
    objs = []
    n = 40
    pts = []
    for i in range(n):
        a = TAU * i / n
        x = 0.17 * math.cos(a) * (1.0 + 0.12 * math.sin(a) * side * 0)
        y = 0.42 * math.sin(a)
        # foot shape: wider at the ball, narrow at the waist
        if y > 0:
            x *= 1.08
        elif y > -0.2:
            x *= 0.9
        pts.append((x, y))
    weave = gb.pigment("I_SandalSole", "#E2C88A", "#9E7E44", fen=0.45,
                       ink=_rows(1, 12.0, 0.08, 0.4))
    sole = K.outline_mesh(name + "_sole", pts, 0.06, weave, plane="XY")
    objs.append(sole)
    # toe loop and side straps (straw rope)
    st = M["rope_straw"]
    objs.append(P.cord(name + "_toe", st, [(-0.06, 0.34, 0.03), (0.0, 0.3, 0.12),
                                           (0.06, 0.34, 0.03)], 0.025))
    for sx in (-1, 1):
        objs.append(P.cord(name + "_st%d" % sx, st, [(sx * 0.15, -0.05, 0.03),
                                                     (sx * 0.1, 0.08, 0.14),
                                                     (0.0, 0.22, 0.15)], 0.022))
        objs.append(P.cord(name + "_hl%d" % sx, st, [(sx * 0.15, -0.22, 0.03),
                                                     (sx * 0.12, -0.32, 0.14),
                                                     (0.0, -0.38, 0.16)], 0.022))
    return objs


def Move(M, cam):
    """Setting out on the road: a pair of straw sandals (草鞋) one ahead of the other, and a
    vermilion brush-stroke arrow sweeping onwards above them."""
    from ironart import icons_shapes as S
    objs = []
    # each sandal turned on the ground, then the pair tipped towards the painter (the sole
    # plates of an encyclopedia show the top of a flat object, not its edge)
    pair = []
    pair += P.group("sandL", _sandal("sl", M, -1), (-0.46, 0.2, 0.0), (0, 0, 70), 1.75)
    pair += P.group("sandR", _sandal("sr", M, 1), (0.3, -0.26, 0.0), (0, 0, 60), 1.75)
    objs += P.group("pair", pair, (0, 0, 0), (34, 0, 0))
    cv = S.Canvas((-1.3, -0.6, 1.3, 1.3), 900)

    def path(t):
        a = math.radians(205 - 160 * t)
        return (1.0 * math.cos(a), 0.15 + 0.62 * math.sin(a) + 0.08 * t)
    S.brush_arrow(cv, path, 0.04, 0.2, 0.42, 0.24)
    mat = gb.pigment("I_MoveArrow", "#E0784A", "#A8321F", fen=0.55, formk=0.0,
                     grad=lambda b: b.maprange(b.sep(gb.obj_coord(b))[0], -1.0, 1.0, 0.5, 0.0))
    arr = S.shape_mesh("arrow", cv, 0.06, mat)
    objs += P.group("arrowG", arr, (0.0, 0.5, 0.55), (-TILT, 0, FACE))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Market(M, cam):
    """A merchant's balance (天平): turned post on a base, beam, two hanging pans (one holding an
    ingot, one a weight)."""
    objs = []
    base = K.box("base", (0.8, 0.5, 0.12), M["wood_dark"])
    base.location = (0, 0, 0.06)
    objs.append(base)
    post = K.lathe("post", [(0.0, 0.12), (0.06, 0.12), (0.045, 0.2), (0.04, 1.42), (0.06, 1.46),
                            (0.0, 1.5)], M["wood"], 20)
    objs.append(post)
    beam_z = 1.46
    beam = K.tube("beam", [(-0.88, 0, beam_z), (0.88, 0, beam_z)], 0.028, M["bronze"], 12,
                  radius_fn=lambda t: 0.7 + 0.3 * math.sin(math.pi * t))
    objs.append(beam)
    fin = K.lathe("pointer", [(0.0, 0.0), (0.035, 0.0), (0.0, 0.2)], M["bronze"], 12)
    fin.location = (0, 0, beam_z + 0.02)
    objs.append(fin)
    for sx in (-1, 1):
        x = sx * 0.84
        pz = 0.55
        pan = K.lathe("pan%d" % sx, [(0.0, 0.0), (0.18, 0.005), (0.3, 0.05), (0.33, 0.09),
                                     (0.31, 0.09), (0.18, 0.03), (0.0, 0.02)], M["bronze"], 48)
        pan.location = (x, 0, pz)
        objs.append(pan)
        for k in range(3):
            a = TAU * k / 3 + 0.5
            c = K.tube("str%d%d" % (sx, k), [(x + 0.3 * math.cos(a), 0.3 * math.sin(a), pz + 0.09),
                                            (x, 0, beam_z - 0.02)], 0.008, M["rope_red"], 6)
            objs.append(c)
        gb.put(objs[-3:], "soft")
    ing = P.yuanbao("mk_ing", M["gold"], L=0.36, W=0.24, rim=0.05, wing=0.13, trough=0.03,
                    dome=(0.09, 0.08, 0.1), lip=(0.03, 0.015), flare=0.25)
    ing = P.group("mk_ingG", ing, (-0.84, 0, 0.6), (0, 0, 0))
    objs += ing
    wt = K.lathe("weight", [(0.0, 0.0), (0.1, 0.0), (0.12, 0.08), (0.06, 0.14), (0.08, 0.17),
                            (0.04, 0.2), (0.0, 0.21)], M["iron"], 24)
    wt.location = (0.84, 0, 0.6)
    objs.append(wt)
    objs = P.group("scale", objs, (0, 0, 0), (0, 0, FACE + 4))
    return dict(objs=objs, fill=1.0)
