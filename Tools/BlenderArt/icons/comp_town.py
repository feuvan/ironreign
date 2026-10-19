"""Icons family (gongbi), compositions: diplomacy and town - Alliance, Truce, Gift, Tavern,
Factions, SectTraining, Search, Wait.

Builders follow the conventions of ``comp_realm`` (``<Name>(M, cam) -> dict(objs, fill,
offset)``).
"""

import math

from common import FONT_BRUSH
from ironart import icons_gongbi as gb
from ironart import icons_kit as K
from ironart import icons_props as P

FACE = P.FACE
TAU = math.tau


# ---------------------------------------------------------------------------------------------
TIGER = [(-1.0, 0.62), (-1.0, 0.5), (-0.92, 0.46), (-0.9, 0.38), (-0.78, 0.36), (-0.74, 0.26),
         (-0.86, 0.1), (-0.92, 0.0), (-0.62, 0.0), (-0.58, 0.16), (-0.3, 0.2), (0.2, 0.2),
         (0.32, 0.12), (0.28, 0.0), (0.66, 0.0), (0.72, 0.18), (0.86, 0.36), (0.9, 0.6),
         (0.9, 0.7), (1.02, 0.86), (1.08, 1.04), (1.02, 1.16), (0.96, 1.1), (0.99, 0.98),
         (0.86, 0.84), (0.6, 0.78), (0.2, 0.74), (-0.2, 0.78), (-0.42, 0.88), (-0.5, 1.0),
         (-0.6, 1.08), (-0.68, 0.98), (-0.8, 0.93), (-0.92, 0.84), (-0.98, 0.74)]


def _tiger_inlay(name, box):
    """Gold-inlaid stripes, eye and inscription of the tally (Pillow, alpha = inlay)."""
    from PIL import Image, ImageDraw
    x0, z0, x1, z1 = box
    W, H = 640, int(640 * (z1 - z0) / (x1 - x0))
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def px(x, z):
        return ((x - x0) / (x1 - x0) * W, (1 - (z - z0) / (z1 - z0)) * H)
    g = (226, 196, 120, 255)
    for x in (-0.3, -0.05, 0.2, 0.45, 0.68):
        pts = [px(x - 0.08 + 0.03 * math.sin(t * 3.0), 0.74 - 0.36 * t) for t in
               [k / 8.0 for k in range(9)]]
        d.line(pts, fill=g, width=15, joint="curve")
    d.ellipse([*px(-0.84, 0.8), *px(-0.74, 0.72)], fill=g)
    d.line([px(-0.94, 0.56), px(-0.8, 0.6)], fill=g, width=8)
    d.line([px(-0.55, 0.3), px(0.6, 0.3)], fill=g, width=7)
    return K.pil_image(name, im)


def Alliance(M, cam):
    """Two halves of a tiger tally (虎符) fitted together: a crouching tiger in profile, the
    front half bronze inlaid with gold, the back half gold, tied with a red cord."""
    objs = []
    ol = K.spline_outline(TIGER, 6)
    box = (-1.1, 0.0, 1.15, 1.2)
    inl = _tiger_inlay("TigerInlay", box)
    front = gb.pigment("I_TallyBronze", "#B8925A", "#5E4420", fen=0.7, image=inl,
                       image_color="#E2C67E", image_box=box)
    a = K.outline_mesh("tallyA", ol, 0.22, front, plane="XZ", bevel_w=0.08, segments=4)
    a.location = (-0.12, -0.07, -0.12)
    b = K.outline_mesh("tallyB", ol, 0.22, M["gold"], plane="XZ", bevel_w=0.08, segments=4)
    b.location = (0.3, 0.22, 0.42)
    objs += [b, a]
    cord = P.cord("cord", M["rope_red"], [(-0.1, -0.16, 0.5), (-0.05, -0.2, 0.3),
                                          (0.05, -0.16, 0.12)], 0.03)
    ring = K.torus("cring", 0.16, 0.03, M["rope_red"], 32, 8)
    K.place(ring, (-0.05, 0.0, 0.47), (0, 90, 0))
    ring.scale = (1.0, 1.4, 1.0)
    objs += [cord, ring]
    objs += P.tassel("ts", M["tassel_red"], (0.05, -0.17, 0.12), 0.42, 0.07)
    objs = P.group("al", objs, (0, 0, 0), (0, 0, FACE + 6))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Truce(M, cam):
    """A white silk flag of truce on a dark pole with a mud-gold finial."""
    objs = P.flag_on_pole("tf", M, M["silk_white"], 1.15, 0.85, 2.3, wave=0.1, droop=0.18,
                          tassel=False)
    objs = P.group("truce", objs, (0, 0, 0), (0, 0, FACE + 10))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Gift(M, cam):
    """A black-lacquer gift box with mud-gold rims and corner fittings, tied with a cinnabar
    silk ribbon and bow; a smaller azurite brocade box behind."""
    objs = []

    def roundel(name):
        from PIL import Image, ImageDraw
        im = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        g = (226, 194, 112, 255)
        d.ellipse([28, 28, 228, 228], outline=g, width=12)
        for k in range(4):
            a = math.pi / 2 * k + math.pi / 4
            cx, cy = 128 + 52 * math.cos(a), 128 + 52 * math.sin(a)
            d.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], fill=g)
        d.ellipse([104, 104, 152, 152], fill=(30, 26, 22, 255), outline=g, width=8)
        return K.pil_image(name, im)

    def box(name, s, h, mat, x=0.0, y=0.0, ribbon="silk_red", motif=False):
        out = []
        bm = M[mat]
        if motif:
            bm = gb.pigment("I_GiftLacquer", "#5A5048", "#1E1A16", fen=0.5, hi=("#7A7068", 0.35),
                            image=roundel("GiftRoundel"),
                            image_box=(-s * 0.2, -s * 0.2, s * 0.2, s * 0.2))
        b = K.box(name, (s, s, h * 0.72), bm)
        b.location = (x, y, h * 0.36)
        out.append(b)
        ld = K.box(name + "_lid", (s * 1.05, s * 1.05, h * 0.3), M[mat])
        ld.location = (x, y, h * 0.72 + h * 0.15 - 0.02)
        out.append(ld)
        rim = K.box(name + "_rim", (s * 1.06, s * 1.06, h * 0.05), M["gold"])
        rim.location = (x, y, h * 0.72 - 0.01)
        out.append(rim)
        rim2 = K.box(name + "_rim2", (s * 1.065, s * 1.065, h * 0.04), M["gold"])
        rim2.location = (x, y, h * 1.0 - 0.06)
        out.append(rim2)
        for ax in (0, 1):
            sz = (s * 1.08, 0.11, h * 1.05) if ax == 0 else (0.11, s * 1.08, h * 1.05)
            rb = K.box(name + "_rb%d" % ax, sz, M[ribbon])
            rb.location = (x, y, h * 0.52)
            out.append(rb)
        return out
    objs += box("b2", 0.72, 0.58, "silk_blue", x=0.48, y=0.58, ribbon="gold")
    objs += box("b1", 1.05, 0.8, "lacquer_black", x=-0.12, y=-0.1, motif=True)
    top = 0.8 + 0.02
    cx, cy = -0.12, -0.1
    for sx in (-1, 1):
        loop = P.cord("loop%d" % sx, M["silk_red"], [(cx, cy, top), (cx + sx * 0.14, cy - 0.04, top + 0.2),
                                                     (cx + sx * 0.34, cy - 0.02, top + 0.16),
                                                     (cx + sx * 0.3, cy, top + 0.03),
                                                     (cx + sx * 0.06, cy, top)], 0.04)
        objs.append(loop)
        tail = P.cord("tail%d" % sx, M["silk_red"], [(cx, cy - 0.02, top), (cx + sx * 0.12, cy - 0.3, top - 0.02),
                                                     (cx + sx * 0.2, cy - 0.56, top - 0.2)], 0.035)
        objs.append(tail)
    kn = K.sphere("knot", 0.08, M["silk_red"], 16, 8)
    kn.location = (cx, cy, top + 0.03)
    objs.append(kn)
    objs = P.group("gift", objs, (0, 0, 0), (0, 0, 8))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Tavern(M, cam):
    """A stoneware wine jar (酒坛) with a red paper label and a cloth-tied mouth, and a small cup."""
    objs = []
    prof = [(0.0, 0.0), (0.3, 0.0), (0.34, 0.05), (0.5, 0.35), (0.56, 0.62), (0.5, 0.92),
            (0.32, 1.1), (0.24, 1.14), (0.24, 1.2), (0.28, 1.22), (0.0, 1.22)]
    jar = K.lathe("jar", prof, M["stoneware"], 64)
    objs.append(jar)
    # cloth cover over the mouth, tied
    cov = K.lathe("cover", [(0.0, 1.36), (0.18, 1.34), (0.3, 1.26), (0.34, 1.18), (0.3, 1.12),
                            (0.26, 1.14), (0.0, 1.14)], M["silk_red"], 48)
    objs.append(cov)
    tie = K.torus("tie", 0.27, 0.025, M["rope_straw"], 48, 8)
    tie.location = (0, 0, 1.17)
    objs.append(tie)
    # diamond red paper label with 酒
    img = P.glyph_image("WineG", "酒", FONT_BRUSH, 256, 0.62, color=(30, 26, 22))
    lab = gb.pigment("I_WineLabel", "#D8583C", "#A43424", fen=0.25, image=img,
                     image_color="#1E1A16")
    s = 0.24

    def fn(u, v):
        # a square rotated 45 deg wrapped on the belly
        du, dv = u - 0.5, v - 0.5
        x = (du - dv) * s * 1.4
        z = 0.62 + (du + dv) * s * 1.4
        r = 0.565
        a = x / r
        return (r * math.sin(a), -r * math.cos(a), z)
    label = K.grid("label", fn, 8, 8, lab)
    objs.append(label)
    objs = P.group("jarG", objs, (-0.2, 0.15, 0), (0, 0, FACE))
    cup = K.lathe("cup", [(0.0, 0.0), (0.09, 0.0), (0.1, 0.03), (0.12, 0.05), (0.2, 0.2),
                          (0.21, 0.22), (0.19, 0.22), (0.11, 0.08), (0.0, 0.07)], M["porcelain"], 48)
    wine = K.lathe("wine", [(0.0, 0.17), (0.175, 0.17), (0.175, 0.172), (0.0, 0.172)], M["wine"], 48)
    objs += P.group("cupG", [cup, wine], (0.55, -0.45, 0.0), (0, 0, 0))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Factions(M, cam):
    """Three banners of the contending houses - cinnabar, azurite, malachite - planted in a fan."""
    objs = []
    for k, (mat, ry, x, h) in enumerate((("silk_blue", -16, -0.42, 2.0), ("silk_green", 16, 0.42, 2.0),
                                         ("silk_red", 0, 0.0, 2.3))):
        f = P.flag_on_pole("f%d" % k, M, M[mat], 0.72, 0.55, h, wave=0.06, droop=0.1, tassel=False)
        objs += P.group("fG%d" % k, f, (x, 0.08 * (2 - k), 0.0), (0, ry, FACE + 8))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def _peak(name, mat, r, h, seed=0, lumps=7):
    """A blue-green (青绿) mountain: a lathe cone with a lumpy, stepped profile."""
    prof = [(0.0, 0.0)]
    for k in range(lumps + 1):
        t = k / lumps
        z = h * t
        rr = r * (1 - t) ** 0.85 * (1.0 + 0.08 * math.sin(k * 2.3 + seed))
        prof.append((max(rr, 0.02), z))
    prof.append((0.0, h * 1.02))
    return K.lathe(name, prof, mat, 32)


def SectTraining(M, cam):
    """A sect's mountain retreat: blue-green peaks with a small temple hall, a sword planted
    upright before them."""
    objs = []
    green = gb.pigment("I_Peak", "#8CBFA0", "#2B5C8A", fen=0.5, grad=None, formk=0.25)
    green2 = gb.pigment("I_Peak2", "#A8CCAE", "#3E8E6E", fen=0.5, formk=0.25)
    objs.append(_peak("pk1", green, 0.62, 1.35, 0))
    p2 = _peak("pk2", green2, 0.48, 0.95, 1)
    p2.location = (0.62, 0.3, 0)
    objs.append(p2)
    p3 = _peak("pk3", green2, 0.4, 0.7, 2)
    p3.location = (-0.6, 0.25, 0)
    objs.append(p3)
    # foothill ochre band (赭石 at the foot, as in 青绿 landscape)
    base = K.lathe("foot", [(0.0, 0.0), (1.1, 0.0), (0.95, 0.12), (0.0, 0.14)], M["earth"], 48)
    base.scale = (1.0, 0.6, 1.0)
    objs.append(base)
    hall = P.house("hall", M, 0.5, 0.36, 0.22, 0.2, 0.09, wall="plaster", door=False)
    objs += P.group("hallG", hall, (-0.18, -0.38, 0.55), (0, 0, 0))
    sw = P.jian("sw", M, 2.0, 0.09)
    objs += P.group("swG", sw, (0.45, -0.75, 0.55), (0, 4, FACE))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Search(M, cam):
    """Searching the land: a white paper lantern on its stick held over an unrolled map."""
    objs = []
    W, H = 1.4, 0.95
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (512, 348), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    ink = (42, 36, 30, 255)
    for (x, y, sz) in ((90, 120, 44), (150, 100, 58), (215, 125, 40), (400, 95, 48)):
        d.polygon([(x - sz, y + sz * 0.6), (x, y - sz * 0.55), (x + sz, y + sz * 0.6)],
                  fill=(62, 142, 110, 255), outline=ink, width=6)
    d.line([(20, 268), (120, 238), (220, 278), (330, 228), (490, 258)], fill=(43, 92, 138, 255),
           width=14, joint="curve")
    d.rectangle([300, 150, 370, 200], fill=(181, 56, 42, 255), outline=ink, width=5)
    img = K.pil_image("MapImg", im)
    pm = gb.pigment("I_MapPaper", "#F2E8CE", "#CDB98E", fen=0.35, formk=0.12, image=img)

    def sheet(u, v):
        return (-W / 2 + u * W, -H / 2 + v * H, 0.03 * math.sin(u * math.pi * 2))
    objs.append(K.grid("map", sheet, 24, 2, pm))
    for sx in (-1, 1):
        rod = K.lathe("rod%d" % sx, [(0.0, -H / 2 - 0.06), (0.07, -H / 2 - 0.06),
                                     (0.07, H / 2 + 0.06), (0.0, H / 2 + 0.06)], M["wood_dark"], 24)
        K.place(rod, (sx * (W / 2 + 0.05), 0, 0.05), (90, 0, 0))
        objs.append(rod)
    objs = P.group("mapG", objs, (0.25, 0.25, 0.0), (0, 0, 8))
    lt = P.lantern("lt", M, 0.42, 0.66, "white")
    stick = K.tube("stick", [(-0.85, -0.2, 0.3), (-0.55, -0.3, 1.5), (-0.3, -0.32, 1.66),
                             (-0.22, -0.32, 1.55)], 0.03, M["bamboo"], 8)
    objs.append(stick)
    objs.append(P.cord("lcord", M["rope_red"], [(-0.22, -0.32, 1.55), (-0.22, -0.32, 1.38)], 0.015))
    objs += P.group("ltG", lt, (-0.22, -0.32, 1.0), (0, 0, 0))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Wait(M, cam):
    """Rest: a celadon tea bowl on its saucer, steam rising in two soft strokes."""
    objs = []
    cup = K.lathe("cup", [(0.0, 0.0), (0.2, 0.0), (0.22, 0.03), (0.24, 0.06), (0.36, 0.3),
                          (0.44, 0.52), (0.45, 0.55), (0.42, 0.55), (0.41, 0.52),
                          (0.33, 0.32), (0.0, 0.3)], M["celadon"], 64)
    tea = K.lathe("tea", [(0.0, 0.47), (0.405, 0.47), (0.405, 0.475), (0.0, 0.475)], M["tea"], 64)
    sau = K.lathe("saucer", [(0.0, 0.0), (0.28, 0.0), (0.3, -0.04), (0.62, 0.0), (0.66, 0.06),
                             (0.63, 0.07), (0.3, 0.02), (0.0, 0.02)], M["celadon"], 64)
    sau.location = (0, 0, -0.06)
    objs += [cup, tea, sau]
    steam = []
    for i, (x, ph) in enumerate(((-0.1, 0.0), (0.12, 1.3))):
        pts = [(x + 0.08 * math.sin(ph + t * 4.0), 0.0, 0.62 + t * 0.7) for t in
               [k / 8.0 for k in range(9)]]
        steam.append(K.curve_tube("steam%d" % i, pts, 0.02, M["white"], 4, 12,
                                  radius_fn=lambda t: 1.0 - 0.7 * t))
    gb.put(steam, "soft")
    objs += steam
    return dict(objs=objs, fill=0.95)
