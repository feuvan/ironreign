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
    sp = P.spear("sp", M, 2.5, r=0.04)
    objs += P.group("spG", sp, (0.25, 0.15, -0.15), (0, -22, FACE))
    hook = P.cord("hook", M["rope_red"], [(-0.17, 0.12, 1.6), (-0.2, 0.1, 1.45),
                                          (-0.2, 0.1, 1.32)], 0.016)
    objs.append(hook)
    lt = P.lantern("lt", M, 0.46, 0.72, "silk_red")
    objs += P.group("ltG", lt, (-0.2, 0.1, 0.92), (0, 0, 0))
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
    hm = P.helmet("hm", M, 0.42)
    objs += P.group("hmG", hm, (0.0, -0.4, 0.3), (0, 0, FACE + 10))
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
def Training(M, cam):
    """An archery target (straw boss with painted rings) on a stand, two arrows in the gold."""
    objs = []
    R = 0.72
    rings = [("target_white", 1.0), ("target_red", 0.8), ("target_white", 0.6),
             ("target_blue", 0.42), ("gold", 0.22)]
    tg = []
    straw = K.lathe("boss", [(0.0, -0.1), (R * 1.04, -0.1), (R * 1.08, -0.02), (R * 1.04, 0.05),
                             (0.0, 0.05)], M["straw"], 64)
    tg.append(straw)
    for k, (m, f) in enumerate(rings):
        d = K.lathe("ring%d" % k, [(0.0, 0.05 + 0.004 * k), (R * f, 0.05 + 0.004 * k),
                                   (R * f, 0.054 + 0.004 * k), (0.0, 0.054 + 0.004 * k)], M[m], 64)
        tg.append(d)
    # arrows in target space: shafts leave the face (+Z) slightly askew
    for k, (dx, dy, rx, ry) in enumerate(((0.04, 0.06, 18, -24), (-0.1, -0.05, 26, -8))):
        ar = [K.lathe("ash%d" % k, [(0.0, 0.0), (0.022, 0.0), (0.022, 0.95), (0.0, 0.95)],
                      M["bamboo"], 8)]
        for j in range(3):
            f = K.outline_mesh("fl%d%d" % (k, j), [(0.0, 0.62), (0.1, 0.7), (0.11, 0.93),
                                                   (0.0, 0.9)], 0.004, M["feather"], plane="XZ")
            f.rotation_euler = (0, 0, TAU * j / 3)
            ar.append(f)
        nock = K.sphere("nock%d" % k, 0.03, M["silk_red"], 12, 6)
        nock.location = (0, 0, 0.95)
        ar.append(nock)
        tg += P.group("arG%d" % k, ar, (dx, dy, 0.05), (rx, ry, 0))
    objs += P.group("tgG", tg, (0, 0, 1.05), (80, 0, FACE + 6))
    for sx in (-1, 1):
        leg = K.tube("leg%d" % sx, [(sx * 0.5, 0.25, 0.0), (sx * 0.12, 0.08, 1.2)], 0.04,
                     M["wood_dark"], 8)
        objs.append(leg)
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
    """A sabre (刀) cutting down from the upper right, the stroke drawn as one broad crescent of
    pale azurite wind."""
    objs = []
    sw = P.dao("dao", M, 2.0, 0.2)
    objs += P.group("daoG", sw, (0.3, -0.15, 0.1), (0, -42, FACE))
    outer, inner = [], []
    n = 32
    for k in range(n + 1):
        t = k / n
        a = math.radians(165 - 150 * t)
        R = 1.05
        w = 0.22 * math.sin(math.pi * t ** 0.8) ** 1.2 + 0.004
        outer.append((R * math.cos(a), R * math.sin(a)))
        inner.append(((R - w) * math.cos(a) + 0.12 * math.sin(math.pi * t),
                      (R - w) * math.sin(a) - 0.1 * math.sin(math.pi * t)))
    slash = gb.pigment("I_Slash", "#F2F4F0", "#7FA6C8", fen=0.0, formk=0.0,
                       grad=lambda b: b.maprange(b.sep(gb.obj_coord(b))[2], 0.2, 1.05, 1.0, 0.0))
    sl = K.outline_mesh("slash", outer + inner[::-1], 0.01, slash, plane="XZ")
    gb.put([sl], "soft")
    objs += P.group("slG", [sl], (-0.05, 0.35, 0.3), (0, 0, FACE), 1.05)
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def _flame_outline(h=1.0, w=0.5, curl=0.25, n=40, lean=0.0):
    left, right = [], []
    for i in range(n + 1):
        t = i / n
        z = t * h
        width = w * (math.sin(math.pi * min(t, 0.999) ** 0.75) ** 1.2) * (1.0 - t) ** 0.35
        cx = lean * t * t + curl * math.sin(t * math.pi * 1.5) * t
        left.append((cx - width, z))
        right.append((cx + width, z))
    return left + right[::-1][1:-1]


def Fire(M, cam):
    """Fire attack: layered painted flames (gold heart, vermilion tongues, cinnabar tips) rising
    from crossed logs."""
    objs = []
    fm = flame_material("I_Flame", 0.0, 1.6)
    specs = [(0.0, 1.6, 0.42, 0.16, -0.1, 0.0),
             (-0.42, 1.0, 0.3, -0.12, -0.25, 0.08),
             (0.44, 1.15, 0.3, 0.12, 0.28, 0.08),
             (-0.12, 0.72, 0.22, 0.1, 0.1, -0.1)]
    fl = []
    for i, (x, h, w, curl, lean, dy) in enumerate(specs):
        o = K.outline_mesh("flame%d" % i, _flame_outline(h, w, curl, 40, lean), 0.16, fm,
                           plane="XZ")
        K.place(o, (x, dy, 0), (0, 0, FACE))
        fl.append(o)
    gb.put(fl, "red")
    objs += fl
    for i, (x, rz) in enumerate(((-0.25, 30), (0.25, -30))):
        lg = K.cylinder("log%d" % i, 0.09, 1.1, M["wood_dark"], 16)
        K.place(lg, (x, 0.1, 0.0), (90, 0, rz + FACE))
        objs.append(lg)
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def _spiral(n=60, turns=1.6, r0=0.05, r1=0.45, w0=0.03, w1=0.13, start=0.0):
    """A ruyi-cloud curl: a spiral band (outline) widening outwards."""
    outer, inner = [], []
    for k in range(n + 1):
        t = k / n
        a = start + TAU * turns * t
        r = r0 + (r1 - r0) * t
        w = w0 + (w1 - w0) * t
        outer.append(((r + w / 2) * math.cos(a), (r + w / 2) * math.sin(a)))
        inner.append(((r - w / 2) * math.cos(a), (r - w / 2) * math.sin(a)))
    return outer[::-1] + inner


def Confuse(M, cam):
    """Confusion: swirling auspicious clouds (祥云) - curling lead-white scrolls shaded with
    azurite, coiling round each other."""
    objs = []
    cm = cloud_material("I_Cloud", "#F6F0E4", "#7FA6C8")
    cm2 = cloud_material("I_Cloud2", "#EEF0F0", "#9E8EB8")
    for k, (x, z, s, rot, mat, turns) in enumerate((
            (-0.3, 0.2, 1.0, 0, cm, 1.55), (0.42, 0.45, 0.8, 140, cm2, 1.45),
            (0.15, -0.3, 0.7, 250, cm, 1.4))):
        ol = _spiral(70, turns, 0.04, 0.5, 0.06, 0.2, math.radians(rot))
        o = K.outline_mesh("cloud%d" % k, ol, 0.1, mat, plane="XZ")
        K.place(o, (x, -0.1 * k, z), (0, 0, FACE), s)
        objs.append(o)
    # a soft cloud body under the curls
    body = K.metaball("cbody", [dict(type="BALL", co=(x, 0.1, z), radius=r) for x, z, r in
                                ((-0.55, -0.45, 0.28), (-0.2, -0.5, 0.32), (0.18, -0.55, 0.26),
                                 (0.5, -0.45, 0.22))], cm, 0.03, 0.6)
    body.scale = (1.0, 0.4, 0.7)
    objs.append(body)
    objs = P.group("cl", objs, (0, 0, 0), (0, 0, 0))
    gb.put(objs, "soft")
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
