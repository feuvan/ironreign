"""Icons family (gongbi), compositions: war - Walls, Patrol, Draft, Train, March, Troops,
Defense, Training, Rally, Duel, Attack, Fire, Confuse, Prisoner.

Builders follow the conventions of ``comp_realm`` (``<Name>(M, cam) -> dict(objs, fill,
offset)``).
"""

import math

from common import FONT_BRUSH, cloud_material, flame_material
from ironart import icons_gongbi as gb
from ironart import icons_kit as K
from ironart import icons_props as P

FACE = P.FACE
TILT = P.TILT
TAU = math.tau


# ---------------------------------------------------------------------------------------------
def _arch_door(name, M, w=0.44, h=0.64, y=0.0, mat="lacquer_red"):
    ol = [(-w / 2, 0.0), (w / 2, 0.0), (w / 2, h - w / 2)]
    for k in range(1, 12):
        a = math.pi * k / 12
        ol.append((w / 2 * math.cos(a), h - w / 2 + w / 2 * math.sin(a)))
    ol.append((-w / 2, h - w / 2))
    d = K.outline_mesh(name, ol, 0.02, M[mat], plane="XZ")
    d.location = (0.0, y, 0.0)
    return d


def Walls(M, cam):
    """A crenellated city-wall segment with an arched, red-lacquered gate and a small gate
    tower (界画) above it."""
    L, D, H = 1.9, 0.5, 1.0
    objs = []
    wall = K.box("wall", (L, D, H), M["masonry"])
    wall.location = (0, 0, H / 2)
    objs.append(wall)
    cop = K.box("coping", (L + 0.08, D + 0.08, 0.07), M["stone"])
    cop.location = (0, 0, H + 0.035)
    objs.append(cop)
    w = 0.17
    for i, x in enumerate((-0.86, -0.56, 0.56, 0.86)):
        m = K.box("merlon%d" % i, (w, 0.18, 0.24), M["masonry"])
        m.location = (x, -D / 2 + 0.05, H + 0.07 + 0.12)
        objs.append(m)
    objs.append(_arch_door("door", M, 0.44, 0.64, -D / 2 - 0.011))
    tw = P.house("tw", M, 0.78, 0.4, 0.3, 0.3, 0.14, wall="plaster", door=False)
    keep = [o for o in tw if not o.name.startswith("tw_base")]
    for o in tw:
        if o not in keep:
            bpy_remove(o)
    objs += P.group("twG", keep, (0, 0.0, H - 0.01), (0, 0, 0))
    return dict(objs=objs, fill=1.0)


def bpy_remove(o):
    import bpy
    bpy.data.objects.remove(o, do_unlink=True)


# ---------------------------------------------------------------------------------------------
def Patrol(M, cam):
    """Night watch: a red paper lantern hung from a spear carried on the shoulder."""
    objs = []
    sp = P.spear("sp", M, 2.2, r=0.045)
    objs += P.group("spG", sp, (0.42, 0.15, -0.2), (0, -32, FACE))
    hook = P.cord("hook", M["rope_red"], [(-0.2, 0.12, 1.5), (-0.24, 0.1, 1.38),
                                          (-0.24, 0.1, 1.26)], 0.018)
    objs.append(hook)
    lt = P.lantern("lt", M, 0.56, 0.86, "silk_red")
    objs += P.group("ltG", lt, (-0.24, 0.1, 0.8), (0, 0, 0))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def _banner_cloth(name, glyph, light="#CC5038", deep="#8A2A20", glyph_color="#F0E8D8",
                  aspect=0.62, fill=0.7):
    img = P.glyph_image(name + "_g", glyph, FONT_BRUSH, 512, fill, aspect=aspect,
                        color=(240, 232, 216))
    return gb.pigment(name, light, deep, fen=0.55, image=img, image_color=glyph_color)


def _vbanner(name, M, cloth_mat, w=0.62, h=1.0, pole_h=2.3, border="gold", wave=0.05):
    """A vertical banner (旗) hanging from a crossbar at the top of a pole: the cloth hangs down
    beside the pole with a border and a fringe of flame-tongues at the free edge."""
    objs = []
    pr = 0.035
    objs.append(K.lathe(name + "_pole", [(0.0, 0.0), (pr, 0.0), (pr * 0.85, pole_h),
                                         (0.0, pole_h)], M["wood_dark"], 16))
    fin = K.lathe(name + "_fin", [(0.0, 0.0), (pr * 1.7, 0.0), (pr * 2.0, 0.05), (pr * 1.2, 0.1),
                                  (pr * 0.9, 0.16), (pr * 1.7, 0.21), (0.0, 0.36)], M["gold"], 20)
    fin.location = (0, 0, pole_h)
    objs.append(fin)
    top = pole_h - 0.08
    bar = K.tube(name + "_bar", [(0.0, 0.0, top), (w + 0.08, 0.0, top)], 0.022, M["wood_dark"], 8)
    objs.append(bar)

    def fn(u, v):
        x = 0.04 + u * w
        y = wave * math.sin(v * math.pi * 1.6 + u * 1.5) * (1 - v) * 0.8
        z = top - (1 - v) * h
        return (x, y, z)
    c = K.grid(name + "_cloth", fn, 12, 24, cloth_mat)
    objs.append(c)
    # border strips (gold) down both long sides
    for k, (u0, u1) in enumerate(((0.0, 0.07), (0.93, 1.0))):
        bd = K.grid(name + "_bd%d" % k, lambda u, v, u0=u0, u1=u1: (
            0.04 + (u0 + u * (u1 - u0)) * w,
            wave * math.sin(v * math.pi * 1.6 + (u0 + u * (u1 - u0)) * 1.5) * (1 - v) * 0.8 - 0.004,
            top - (1 - v) * h), 2, 24, M[border])
        objs.append(bd)
    # flame-tongue fringe at the bottom (牙)
    n = 4
    for i in range(n):
        x0 = 0.04 + i * w / n
        pts = [(x0, top - h), (x0 + w / n, top - h), (x0 + w / (2 * n), top - h - 0.13)]
        tg = K.outline_mesh(name + "_tg%d" % i, pts, 0.01, M[border], plane="XZ")
        y = wave * math.sin(0 * math.pi * 1.6) * 0.8
        tg.location = (0, y, 0)
        objs.append(tg)
    return objs


def Draft(M, cam):
    """Conscription: a mud-gold recruiting banner painted 募, three spears crossed behind it."""
    objs = []
    for k, (x, ry) in enumerate(((-0.2, -16), (0.3, 14), (0.05, -1))):
        sp = P.spear("sp%d" % k, M, 2.3, tassel=True, r=0.038)
        objs += P.group("spG%d" % k, sp, (x, 0.35, 0.0), (0, ry, FACE))
    cl = _banner_cloth("I_DraftCloth", "募", light="#E8CC80", deep="#A8843C",
                       glyph_color="#1E1A16", aspect=0.8 / 1.1, fill=0.78)
    bn = _vbanner("bn", M, cl, 0.8, 1.1, 2.15, border="silk_red")
    objs += P.group("bnG", bn, (-0.62, -0.25, 0.0), (0, 0, FACE))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Train(M, cam):
    """Drill: two wooden practice staves crossed behind a lacquered drill drum on its stand."""
    objs = []
    for k, ry in enumerate((-40, 40)):
        st = []
        st.append(K.lathe("staff%d" % k, [(0.0, -1.1), (0.055, -1.1), (0.05, 1.1), (0.0, 1.1)],
                          M["wood_pale"], 16))
        for j, z in enumerate((-0.45, -0.25, 0.95)):
            st.append(K.lathe("wrap%d%d" % (k, j), [(0.0, z), (0.062, z), (0.062, z + 0.1),
                                                     (0.0, z + 0.1)], M["silk_red"], 16))
        objs += P.group("stG%d" % k, st, (0, 0.3, 1.0), (0, ry, FACE))
    dr = P.drum("dr", M, 0.46, 0.52)
    objs += P.group("drG", dr, (0, -0.3, 0.6), (90 - 15, 0, FACE + 90 - 55))
    for sx in (-1, 1):
        leg = K.tube("leg%d" % sx, [(sx * 0.42, -0.4, 0.0), (-sx * 0.1, -0.3, 0.55)], 0.04,
                     M["wood_dark"], 8)
        objs.append(leg)
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def March(M, cam):
    """A war banner (牙旗) flying from a spear-tipped pole: cinnabar cloth with a mud-gold
    border and flame-tongue fringe, painted 征."""
    objs = []
    pole_h = 2.3
    pr = 0.045
    objs.append(K.lathe("pole", [(0.0, 0.0), (pr, 0.0), (pr * 0.85, pole_h), (0.0, pole_h)],
                        M["wood_dark"], 16))
    head = P.spear("tip", M, 0.5, tassel=False, r=0.03)
    for o in head:
        o.location = (0, 0, pole_h - 0.14)
    objs += head[2:]
    objs += P.tassel("ts", M["tassel_red"], (0.0, 0.0, pole_h + 0.02), 0.3, 0.07)
    W, H = 1.45, 1.1
    top = pole_h - 0.12
    img = P.glyph_image("MarchG", "征", FONT_BRUSH, 512, 0.62, aspect=W / H, color=(30, 26, 22))
    cl = gb.pigment("I_MarchCloth", "#CC5038", "#8A2A20", fen=0.55, image=img,
                    image_color="#2A1E18", image_ink=0.0)

    def fn(u, v):
        x = pr + u * W
        y = 0.12 * math.sin(u * math.pi * 1.8 + 0.3) * u ** 0.8
        z = top - (1 - v) * H - 0.12 * u ** 1.5
        return (x, y, z)
    objs.append(K.grid("cloth", fn, 40, 16, cl))
    # gold border along the top and bottom edges and the fly
    for k, (v0, v1) in enumerate(((0.0, 0.08), (0.92, 1.0))):
        objs.append(K.grid("bd%d" % k, lambda u, v, v0=v0, v1=v1: (
            pr + u * W, 0.12 * math.sin(u * math.pi * 1.8 + 0.3) * u ** 0.8 - 0.004,
            top - (1 - (v0 + v * (v1 - v0))) * H - 0.12 * u ** 1.5), 40, 1, M["gold"]))
    # flame tongues along the fly edge (牙)
    n = 5
    for i in range(n):
        v0, v1 = i / n, (i + 1) / n
        u = 1.0
        def P3(vv):
            return (pr + u * W, 0.12 * math.sin(u * math.pi * 1.8 + 0.3) * u ** 0.8,
                    top - (1 - vv) * H - 0.12 * u ** 1.5)
        a, b = P3(v0), P3(v1)
        mid = P3((v0 + v1) / 2)
        tip = (mid[0] + 0.16, mid[1], mid[2] - 0.05)
        tg = K.outline_mesh("tg%d" % i, [(a[0], a[2]), (tip[0], tip[2]), (b[0], b[2])], 0.01,
                            M["gold"], plane="XZ")
        tg.location = (0, a[1], 0)
        objs.append(tg)
    objs = P.group("march", objs, (0, 0, 0), (0, 0, FACE + 10))
    return dict(objs=objs, fill=1.0, offset=(0.0, 0.0))


# ---------------------------------------------------------------------------------------------
def Troops(M, cam):
    """A bundle of spears tied with red cord, a general's helmet resting before them."""
    objs = []
    for k, (ry, x) in enumerate(((-16, -0.2), (-5, -0.07), (6, 0.06), (17, 0.2))):
        sp = P.spear("sp%d" % k, M, 2.3, tassel=(k % 2 == 0), r=0.04)
        objs += P.group("spG%d" % k, sp, (x * 0.4, 0.35 + 0.03 * k, 0.0), (0, ry, FACE))
    band = K.torus("band", 0.13, 0.035, M["rope_red"], 32, 8)
    band.location = (0, 0.38, 1.0)
    objs.append(band)
    hm = P.helmet_ming("hm", M, 0.44)
    objs += P.group("hmG", hm, (0.0, -0.42, 0.28), (0, 0, FACE + 10))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def _shield_motif(name, S=512):
    """Gold rosette and studded ring on the cinnabar shield face (Pillow, alpha = gold)."""
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    gold = (226, 194, 112, 255)
    ink = (30, 26, 22, 255)
    c = S / 2
    d.ellipse([c - 214, c - 214, c + 214, c + 214], outline=gold, width=20)
    for k in range(16):
        a = TAU * k / 16
        x, y = c + 182 * math.cos(a), c + 182 * math.sin(a)
        d.ellipse([x - 10, y - 10, x + 10, y + 10], fill=gold, outline=ink, width=2)
    for k in range(8):
        a = TAU * k / 8 + TAU / 16
        pts = [(c + 70 * math.cos(a - 0.3), c + 70 * math.sin(a - 0.3)),
               (c + 120 * math.cos(a - 0.12), c + 120 * math.sin(a - 0.12)),
               (c + 150 * math.cos(a), c + 150 * math.sin(a)),
               (c + 120 * math.cos(a + 0.12), c + 120 * math.sin(a + 0.12)),
               (c + 70 * math.cos(a + 0.3), c + 70 * math.sin(a + 0.3))]
        d.polygon(pts, fill=gold, outline=ink, width=3)
    return K.pil_image(name, im)


def Defense(M, cam):
    """A round cinnabar war shield with a gold rosette, studded ring and bronze boss, set up
    before a crenellated wall."""
    objs = P.wall_segment("w", M, 1.9, 0.45, 0.85, 4)
    for o in objs:
        o.location.y += 0.35
    R = 0.68
    face = gb.pigment("I_ShieldFace", "#CC5038", "#7A2018", fen=0.6,
                      image=_shield_motif("ShieldMotif"), image_box=(-R, -R, R, R),
                      image_plane="XY")
    prof = [(0.0, 0.14), (R * 0.4, 0.12), (R * 0.8, 0.06), (R, 0.0), (R * 0.95, -0.02),
            (0.0, -0.02)]
    sh = K.lathe("shield", prof, face, 64)
    rim = K.torus("rim", R, 0.05, M["wood_dark"], 64, 10)
    boss = K.sphere("boss", 0.16, M["bronze"], 32, 16, (1, 1, 0.7))
    boss.location = (0, 0, 0.13)
    for o in (sh, rim, boss):
        o.rotation_euler = (math.radians(90), 0, 0)
        o.location = (o.location.x, -o.location.z, o.location.y)
    objs += P.group("shG", [sh, rim, boss], (0.1, -0.3, 0.64), (0, 0, FACE + 4))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def arrow(name, M, length=1.15, r=0.016, fletch="feather", band="silk_red", head=True):
    """An arrow along +Z (nock at z = 0, point at z = length): bamboo shaft, three barred
    feathers, a red binding at the nock and, if ``head``, an iron point."""
    out = [K.lathe(name + "_shaft", [(0.0, 0.0), (r, 0.0), (r, length - 0.1), (0.0, length - 0.1)],
                   M["bamboo"], 10)]

    def bars(b):
        co = b.sep(gb.obj_coord(b))
        return b.math("MULTIPLY", gb.stripes(b, co[2], 9.0, 0.16), 0.5)
    fm = gb.pigment("I_Fletch", "#F4EEE0", "#B8AC94", fen=0.4, formk=0.1, ink=bars)
    for j in range(3):
        f = K.outline_mesh("%s_fl%d" % (name, j), [(0.0, 0.05), (0.075, 0.09), (0.085, 0.30),
                                                   (0.03, 0.34), (0.0, 0.33)],
                           0.004, fm, plane="XZ")
        f.rotation_euler = (0, 0, TAU * j / 3 + 0.4)
        out.append(f)
    bd = K.lathe(name + "_band", [(0.0, 0.0), (r * 1.5, 0.0), (r * 1.5, 0.05), (0.0, 0.05)],
                 M[band], 10)
    bd.location = (0, 0, 0.34)
    out.append(bd)
    if head:
        hd = K.lathe(name + "_head", [(0.0, length - 0.12), (r * 1.6, length - 0.12),
                                      (r * 2.6, length - 0.06), (0.0, length)], M["iron"], 8)
        out.append(hd)
    return out


def Training(M, cam):
    """Archery practice: a coiled-straw target boss with a paper face (an ink ring round a
    cinnabar bull) on a wooden easel, two arrows standing in the centre."""
    objs = []
    R = 0.74

    def coils(b):
        co = b.sep(gb.obj_coord(b))
        rr = b.math("SQRT", b.math("ADD", b.math("MULTIPLY", co[0], co[0]),
                                   b.math("MULTIPLY", co[1], co[1])))
        return b.math("MULTIPLY", gb.stripes(b, rr, 15.0, 0.09, wobble=0.04, wscale=3.0,
                                             vec=gb.obj_coord(b)), 0.55)
    straw = gb.pigment("I_TargetStraw", "#E2C887", "#A07E40", fen=0.55, formk=0.18, ink=coils)
    tg = [K.lathe("boss", [(0.0, -0.12), (R * 0.98, -0.12), (R * 1.04, -0.07), (R * 1.05, 0.0),
                           (R * 1.02, 0.06), (R * 0.95, 0.09), (0.0, 0.09)], straw, 96)]
    face = [("target_white", 0.62, 0.0), ("ink", 0.47, 0.002), ("target_white", 0.40, 0.004),
            ("target_red", 0.22, 0.006)]
    for k, (m, f, dz) in enumerate(face):
        d = K.lathe("face%d" % k, [(0.0, 0.09 + dz), (R * f, 0.09 + dz), (R * f, 0.093 + dz),
                                   (0.0, 0.093 + dz)], M[m], 96)
        tg.append(d)
    # arrows in target space: shafts leave the face (+Z) slightly askew
    for k, (dx, dy, rx, ry) in enumerate(((0.04, 0.05, -38, 50), (-0.06, -0.05, -20, 64))):
        ar = arrow("ar%d" % k, M, 1.0, head=False)
        # nock end out, the shaft entering the face at (dx, dy)
        tg += P.group("arG%d" % k, ar, (dx, dy, 0.09), (rx, ry, 0))
    objs += P.group("tgG", tg, (0.0, 0.0, 1.12), (78, 0, FACE + 8))
    # easel: two splayed front legs and a back leg showing under the boss, a cross rail
    for sx in (-1, 1):
        objs.append(K.tube("leg%d" % sx, [(sx * 0.66, -0.22, 0.0), (sx * 0.22, 0.12, 1.6)],
                           0.035, M["wood_dark"], 8))
    objs.append(K.tube("legb", [(0.05, 0.78, 0.0), (0.0, 0.25, 1.5)], 0.032, M["wood_dark"], 8))
    objs.append(K.tube("rail", [(-0.52, -0.02, 0.3), (0.52, -0.02, 0.3)], 0.03, M["wood_dark"], 8))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Rally(M, cam):
    """The war drum: a big barrel drum on a red stand, two drumsticks with ribbons."""
    objs = []
    dr = P.drum("dr", M, 0.62, 0.72)
    objs += P.group("drG", dr, (0, 0.05, 0.95), (90 - 12, 0, FACE + 90 - 40))
    # stand: four splayed legs and a cradle ring
    for k, (x, y) in enumerate(((-0.55, -0.3), (0.55, -0.3), (-0.5, 0.4), (0.5, 0.4))):
        lg = K.tube("leg%d" % k, [(x, y, 0.0), (x * 0.6, y * 0.6, 0.62)], 0.04, M["lacquer_red"], 8)
        objs.append(lg)
    # drumsticks crossed above the front head
    for k, (rz, x) in enumerate(((28, -0.2), (-28, 0.2))):
        st = [K.lathe("stick%d" % k, [(0.0, 0.0), (0.03, 0.0), (0.026, 0.9), (0.0, 0.9)],
                      M["wood"], 12)]
        kn = K.sphere("knob%d" % k, 0.06, M["lacquer_red"], 16, 8)
        kn.location = (0, 0, 0.92)
        st.append(kn)
        st += P.tassel("rb%d" % k, M["tassel_red"], (0, 0, 0.0), 0.22, 0.045, knot=False)
        objs += P.group("stG%d" % k, st, (x, -0.65, 1.05), (0, 180 + rz, FACE))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Duel(M, cam):
    """Two straight swords (剑) crossed, blades up, red tassels hanging from the pommels."""
    objs = []
    for k, ry in enumerate((-38, 38)):
        sw = P.jian("sw%d" % k, M, 2.0, 0.11)
        objs += P.group("swG%d" % k, sw, (0.0, 0.05 * k, 0.0), (0, ry, FACE))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Attack(M, cam):
    """A sabre (刀) cutting through the air: the blade drawn large on the rising diagonal, ring
    pommel and red tassel at the hilt, and behind it the sweep of the cut - one broad pale
    crescent of sword-wind (剑气) shaded from vermilion at its head to bare silk at its tail,
    with two fine trailing strokes."""
    from ironart import icons_shapes as S
    objs = []
    hx, hz = -0.62, -0.62                  # hilt (centre of the swing) in the motif plane
    ang = 48.0                             # blade direction (deg, motif plane)
    sw = P.dao("dao", M, 2.15, 0.18)
    rg = K.torus("dao_ring", 0.08, 0.022, M["gold"], 32, 8)
    K.place(rg, (0.0, 0.0, -0.44), (90, 0, 0))
    sw.append(rg)
    sw += P.tassel("dao_ts", M["tassel_red"], (0.0, 0.0, -0.52), 0.38, 0.06)
    blade = P.group("daoB", sw, (0, 0, 0), (0, 90 - ang, 0))
    cv = S.Canvas((-2.4, -2.4, 2.4, 2.4), 1200)
    for (R, a0, a1, w) in ((1.45, 150, 57, 0.32), (1.78, 128, 60, 0.07), (1.12, 140, 62, 0.06)):
        pts, ws = [], []
        for j in range(61):
            t = j / 60.0
            a = math.radians(a0 + (a1 - a0) * t)
            pts.append((hx + R * math.cos(a), hz + R * math.sin(a)))
            # the brush lands thin at the tail of the cut and swells towards the blade
            ws.append(w * t ** 1.2 * min(1.0, (1.0 - t) * 10.0) ** 0.4 + 0.005)
        cv.brush(pts, ws)
    wind = gb.pigment("I_Wind", "#F4D2B8", "#C44A2E", fen=0.4, formk=0.0, fen2d=0.5,
                      grad=lambda b: b.maprange(b.sep(gb.obj_coord(b))[0], -1.9, 0.4, 0.0, 0.85))
    parts = S.shape_mesh("wind", cv, 0.06, wind)
    # boneless (没骨) strokes: the sword-wind is painted with the brush alone, no outline
    gb.put(parts, "none")
    # blade and wind share the motif plane, the wind a little behind
    objs += P.group("atk", P.group("bladeG", blade, (hx, -0.05, hz), (0, 0, 0)) +
                    P.group("windG", parts, (0, 0.12, 0), (0, 0, 0)),
                    (0, 0, 0), (-TILT, 0, FACE))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def _tongue(cv, x, z, h, w, lean=0.0, bend=0.0, hook=0.0, n=48):
    """One flame tongue (火焰纹) on canvas ``cv``: a brush stroke rising from (x, z) whose
    heading leans, bends through an S and hooks over at the tip, swelling low and drawn to a
    point."""
    pts, ws = [], []
    px, pz = x, z
    ds = h / n
    for k in range(n + 1):
        t = k / n
        th = lean + bend * math.sin(math.pi * t) + hook * max(0.0, (t - 0.55) / 0.45) ** 2
        pts.append((px, pz))
        ws.append(2.0 * w * max(0.0, 1.0 - t) ** 0.85 * min(1.0, 0.55 + t * 2.2) + 0.004)
        px += -math.sin(th) * ds
        pz += math.cos(th) * ds
    cv.brush(pts, ws)


def _flame_layer(cv, s=1.0, dx=0.0, dz=0.0, licks=True):
    """The flame mass: a tall S-curving centre tongue and leaning side tongues whose tips all
    curl the same way (the turning flame of a 火焰宝珠), low licks and a round root - scaled by
    ``s`` for the inner layers."""
    T = [(0.0, 1.0, 0.30, 0.0, -0.28, 1.6),         # x, h, w, lean, bend, hook
         (0.30, 0.78, 0.22, -0.55, 0.15, 2.3),
         (-0.28, 0.66, 0.21, 0.55, -0.35, 1.1)]
    if licks:
        T += [(0.50, 0.40, 0.15, -0.95, 0.1, 2.2), (-0.50, 0.36, 0.14, 0.95, -0.2, 0.9)]
    for (x, h, w, lean, bend, hook) in T:
        _tongue(cv, dx + x * s, dz + 0.12 * s, h * 2.1 * s, w * s, lean * 0.8, bend, hook)
    cv.poly([(dx + math.cos(a) * 0.46 * s, dz + (0.2 + math.sin(a) * 0.26) * s)
             for a in [TAU * k / 48 for k in range(48)]])


def Fire(M, cam):
    """Fire attack: painted flames (火焰纹) as in Buddhist and battle scrolls - a cinnabar flame
    mass of hooked, S-curving tongues, a vermilion layer inside it and a gold heart, each layer
    outlined in deep cinnabar and shaded from its root to its tips."""
    from common import _zgrad_up
    from ironart import icons_shapes as S
    objs = []
    layers = [  # scale, dz, depth offset, light, deep, licks
        (1.0, 0.0, 0.16, "#D86A40", "#A8321F", True),
        (0.70, 0.0, 0.0, "#F0A452", "#CC5432", False),
        (0.44, 0.02, -0.16, "#FAE6A8", "#ECAE58", False)]
    for k, (s, dz, y, light, deep, licks) in enumerate(layers):
        cv = S.Canvas((-1.2, -0.6, 1.2, 2.4), 900)
        _flame_layer(cv, s, 0.0, dz, licks)
        mat = gb.pigment("I_Flame%d" % k, light, deep, fen=0.35, formk=0.0,
                         grad=_zgrad_up(-0.3, 2.2 * s + 0.1, 0.8), fen2d=0.35)
        parts = S.shape_mesh("flame%d_" % k, cv, 0.06, mat)
        for o in parts:
            K.place(o, (0.0, y, 0.0), (0, 0, 0))
        objs += parts
    gb.put(objs, "red")
    objs = P.group("fire", objs, (0, 0, 0), (-TILT, 0, FACE))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def _cloud_ink(name, box, spirals, res=768):
    """Ink texture for a cloud: tapered spiral curls (alpha = ink) mapped onto the motif box."""
    from PIL import Image
    from ironart import icons_shapes as S
    cv = S.Canvas(box, res)
    for (cx, cz, r1, turns, start, cw) in spirals:
        pts, ws = S.spiral_band(cx, cz, r1 * 0.08, r1, turns, 0.004, 0.032, start, 90, cw)
        # thin at the eye, full in the middle, lifting off at the end
        n = len(ws)
        ws = [w * min(1.0, (n - 1 - i) / (n * 0.18) + 0.25) for i, w in enumerate(ws)]
        cv.brush(pts, ws)
    a = cv.im
    rgba = Image.merge("RGBA", (a.point(lambda v: 30), a.point(lambda v: 26),
                                a.point(lambda v: 22), a))
    return K.pil_image(name, rgba)


def _ruyi_cloud(cv, cx, cz, ang, size=1.0, tail=True, cw=True):
    """A ruyi cloud head (three lobes) at (cx, cz) facing ``ang`` with a tail sweeping round
    the centre; returns the spiral specs of its lobes for :func:`_cloud_ink`."""
    sg = -1.0 if cw else 1.0
    lobes = [(0.0, 0.0, 0.27, 1.35), (0.24, 0.66, 0.17, 0.7), (0.22, -0.74, 0.16, 0.7)]
    spirals = []
    for (dr, da, r, turns) in lobes:
        a = ang + sg * da
        x = cx + math.cos(a) * dr * size
        z = cz + math.sin(a) * dr * size
        cv.disc(x, z, r * size)
        spirals.append((x, z, r * size * 0.74, turns, a + math.pi, not cw))
    if tail:
        pts, ws = [], []
        r0 = math.hypot(cx, cz)
        a0 = math.atan2(cz, cx)
        for k in range(31):
            t = k / 30.0
            a = a0 + sg * math.radians(15 + 105 * t)
            r = r0 * (1.0 - 0.55 * t)
            pts.append((math.cos(a) * r, math.sin(a) * r))
            ws.append((0.30 * (1 - t) ** 1.3 + 0.02) * size)
        cv.brush(pts, ws)
    return spirals


def Confuse(M, cam):
    """Confusion: three auspicious clouds (祥云) chasing one another round a centre - lead-white
    cloud heads with ink spiral curls, shaded at their edges with azurite and with a pale rouge
    (紫) wash, their tails sweeping into the vortex."""
    from ironart import icons_shapes as S
    objs = []
    box = (-1.15, -1.15, 1.15, 1.15)
    specs = [(90.0, "#DCE6EE", "#5E86B0", 0.0), (210.0, "#EADAE2", "#9A6488", 0.08),
             (330.0, "#DCEAE0", "#4E8E74", 0.16)]
    for k, (deg, light, deep, y) in enumerate(specs):
        a = math.radians(deg)
        cv = S.Canvas(box, 900)
        sp = _ruyi_cloud(cv, 0.52 * math.cos(a), 0.52 * math.sin(a), a, 1.0)
        img = _cloud_ink("CloudInk%d" % k, box, sp)
        mat = gb.pigment("I_Cloud%d" % k, light, deep, fen=0.5, formk=0.0, fen2d=0.75, image=img,
                         image_color="#2A241E", image_ink=0.0, image_box=box)
        parts = S.shape_mesh("cloud%d_" % k, cv, 0.06, mat)
        for o in parts:
            K.place(o, (0.0, y, 0.0), (0, 0, 0))
        objs += parts
    # the eye of the vortex: one more curl
    cv = S.Canvas(box, 900)
    cv.disc(0.0, 0.0, 0.17)
    img = _cloud_ink("CloudInkEye", box, [(0.0, 0.0, 0.14, 1.4, 0.0, True)])
    mat = gb.pigment("I_CloudEye", "#F4EEE2", "#7FA6C8", fen=0.9, formk=0.0, image=img,
                     image_color="#2A241E", image_box=box)
    eye = S.shape_mesh("cloud_eye", cv, 0.06, mat)
    for o in eye:
        K.place(o, (0.0, -0.08, 0.0), (0, 0, 0))
    objs += eye
    gb.put(objs, "soft")
    objs = P.group("cl", objs, (0, 0, 0), (-TILT, 0, FACE))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Prisoner(M, cam):
    """The wooden cangue (枷): a heavy square board in two halves with a neck hole, iron bands and
    a chain with a lock."""
    objs = []
    S, T = 1.3, 0.12
    half = []
    for k, sgn in enumerate((-1, 1)):
        # each half: a rectangle with a half-circle bite at the joint
        pts = []
        if sgn < 0:
            pts = [(-S / 2, -S / 2), (0.0, -S / 2), (0.0, 0.05 - 0.22)]
            for j in range(1, 16):
                a = -math.pi / 2 - math.pi * j / 16
                pts.append((0.22 * math.cos(a), 0.05 + 0.22 * math.sin(a)))
            pts += [(0.0, 0.05 + 0.22), (0.0, S / 2), (-S / 2, S / 2)]
        else:
            pts = [(0.0, -S / 2), (S / 2, -S / 2), (S / 2, S / 2), (0.0, S / 2), (0.0, 0.27)]
            for j in range(1, 16):
                a = math.pi / 2 - math.pi * j / 16
                pts.append((0.22 * math.cos(a), 0.05 + 0.22 * math.sin(a)))
            pts.append((0.0, 0.05 - 0.22))
        b = K.outline_mesh("half%d" % k, pts, T, M["wood_x"], plane="XY")
        b.location = (sgn * 0.015, 0, 0)
        half.append(b)
    objs += half
    # iron bands across the joint and nails
    for k, y in enumerate((-0.45, 0.45)):
        bd = K.box("band%d" % k, (0.34, 0.1, T + 0.03), M["iron_dark"])
        bd.location = (0, y, 0)
        objs.append(bd)
    objs = P.group("cg", objs, (0, 0, 0.4), (62, 0, FACE + 8))
    # chain hanging from the front with a padlock
    ch = []
    for k in range(5):
        lk = K.torus("lk%d" % k, 0.07, 0.018, M["iron"], 20, 6, scale_minor=(1, 1))
        K.place(lk, (0.0, -0.66, 0.08 - k * 0.11), (0 if k % 2 else 90, 90, 0))
        ch.append(lk)
    lock = K.box("lock", (0.22, 0.08, 0.16), M["bronze"])
    lock.location = (0.0, -0.66, -0.52)
    ch.append(lock)
    shk = K.torus("shackle", 0.07, 0.02, M["bronze"], 20, 6, arc=math.pi)
    K.place(shk, (0.0, -0.66, -0.44), (90, 0, 0))
    ch.append(shk)
    objs += P.group("chG", ch, (0.25, 0.0, 0.25), (0, 0, FACE))
    return dict(objs=objs, fill=1.0)
