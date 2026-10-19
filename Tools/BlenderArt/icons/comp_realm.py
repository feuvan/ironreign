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
TAU = math.tau


# ---------------------------------------------------------------------------------------------
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
    # drooping heads (panicles) from the top, all round but heavier towards the viewer
    heads = []
    n = 9
    for i in range(n):
        a = TAU * i / n + 0.35
        ca, sa = math.cos(a), math.sin(a)
        r0 = 0.22
        L = 0.62 + 0.08 * math.sin(i * 2.1)
        pts = []
        for k in range(8):
            t = k / 7.0
            rr = r0 + 0.5 * L * t
            z = 1.1 + 0.32 * math.sin(t * math.pi * 0.62) - 0.65 * L * t * t
            pts.append((ca * rr, sa * rr, z))
        h = K.curve_tube("head%d" % i, pts, 0.05, M["grain"], 6, 10,
                         radius_fn=lambda t: 0.35 + 0.9 * math.sin(math.pi * min(1, 0.15 + t)) ** 0.7)
        heads.append(h)
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
    """Three gold yuanbao: two behind, one larger in front."""
    objs = []
    kw = dict(L=1.0, W=0.68, rim=0.24, wing=0.3, trough=0.16, dome=(0.24, 0.19, 0.22),
              flare=0.26, lip=(0.12, 0.06), sq=2.2, boss_lift=0.55)
    objs += P.group("ingotA", P.yuanbao("ingA", M["gold"], **kw), (-0.5, 0.05, 0.0), (0, 0, -10))
    objs += P.group("ingotB", P.yuanbao("ingB", M["gold"], **kw), (0.52, 0.12, 0.0), (0, 0, 10))
    objs += P.group("ingotC", P.yuanbao("ingC", M["gold"], **kw), (0.02, 0.32, 0.36), (0, 0, -2),
                    1.05)
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
        dict(type="ELLIPSOID", co=(-1.25, 0, 0.8), radius=0.62, size=(1.25, 0.72, 0.72)),
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
    legs = ((-1.78, -0.17), (-1.7, 0.17), (-0.84, -0.17), (-0.76, 0.17))
    for (x, y) in legs:
        els.append(dict(type="CAPSULE", co=(x, y, 0.34), radius=0.14, size=(0.2, 1, 1),
                        rot=(0, 90, 0)))
    out = [K.metaball(name, els, M["ox"], resolution=0.022, threshold=0.6)]
    for k, (x, y) in enumerate(legs):
        h = K.cylinder(name + "_hoof%d" % k, 0.08, 0.08, M["iron_dark"], 12)
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
    """An ox cart coming towards the viewer: a sturdy ox (metaballs) drawing a two-wheeled cart
    loaded with hemp sacks."""
    objs = []
    bed = K.box("bed", (1.2, 0.85, 0.08), M["wood"])
    bed.location = (0.6, 0, 0.55)
    objs.append(bed)
    for sy in (-1, 1):
        rail = K.box("rail%d" % sy, (1.2, 0.05, 0.18), M["wood_dark"])
        rail.location = (0.6, sy * 0.42, 0.68)
        objs.append(rail)
        shaft = K.tube("shaft%d" % sy, [(0.0, sy * 0.36, 0.56), (-0.9, sy * 0.4, 0.86),
                                        (-1.75, sy * 0.42, 1.2)], 0.035, M["wood_dark"], 8)
        objs.append(shaft)
    for k, (x, y, s) in enumerate(((0.4, 0.12, 1.1), (0.85, -0.12, 1.05), (0.7, 0.2, 0.9))):
        prof = [(0.0, 0.0), (0.2, 0.0), (0.26, 0.08), (0.27, 0.22), (0.2, 0.34), (0.08, 0.38),
                (0.1, 0.44), (0.0, 0.44)]
        sk = K.lathe("load%d" % k, prof, M["hemp"], 32, scale_xy=(1.0, 0.85))
        sk.location = (x, y, 0.59)
        sk.scale = (s, s, s)
        objs.append(sk)
    objs += P.group("wheel", _wheel("wh", M, 0.48, 12, 0.1), (0.6, -0.5, 0.48), (90, 0, 0))
    objs += _ox("ox", M)
    yoke = K.tube("yoke", [(-1.72, -0.44, 1.22), (-1.72, 0.44, 1.22)], 0.055, M["wood_dark"], 8)
    objs.append(yoke)
    out = P.group("cart", objs, (0.0, 0, 0), (0, 0, -36))
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
    """A pair of straw sandals (草鞋) setting out, an azurite arrow sweeping onwards."""
    objs = []
    objs += P.group("sandL", _sandal("sl", M, -1), (-0.36, 0.12, 0.0), (0, 0, 72), 1.45)
    objs += P.group("sandR", _sandal("sr", M, 1), (0.2, -0.35, 0.0), (0, 0, 62), 1.45)
    pts, inner = [], []
    n = 24
    for k in range(n + 1):
        t = k / n
        a = math.radians(200 - 150 * t)
        R = 0.9
        w = 0.08 + 0.05 * t
        pts.append(((R + w) * math.cos(a), (R + w) * math.sin(a) * 0.8))
        inner.append(((R - w) * math.cos(a), (R - w) * math.sin(a) * 0.8))
    a = math.radians(50)
    tip = (1.18 * math.cos(a) - 0.02, 0.8 * 1.0 * math.sin(a) + 0.24)
    hl = ((0.9 + 0.28) * math.cos(a), (0.9 + 0.28) * math.sin(a) * 0.8)
    hr = ((0.9 - 0.28) * math.cos(a), (0.9 - 0.28) * math.sin(a) * 0.8)
    outline = inner + [hr, tip, hl] + pts[::-1]
    arr = K.outline_mesh("arrow", outline, 0.07, M["silk_azure"], plane="XZ")
    arr.location = (0.1, 0.0, 0.25)
    objs += P.group("arrowG", [arr], (0.0, 0.25, 0.3), (0, 0, FACE))
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
