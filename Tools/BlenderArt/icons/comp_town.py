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
TILT = P.TILT
TAU = math.tau


# ---------------------------------------------------------------------------------------------
TIGER_BOX = (-1.25, -0.1, 1.25, 1.2)


def _tiger_shape(cv):
    """A crouching tiger in profile facing left, the shape of a tiger tally (虎符): long low
    body, round head with ears and muzzle, forelegs and hind legs folded with the paws forward,
    the tail rising and curling over the back."""
    body = [(-0.62, 0.62), (-0.3, 0.7), (0.15, 0.66), (0.55, 0.64), (0.8, 0.56), (0.86, 0.38),
            (0.78, 0.22), (0.5, 0.18), (0.0, 0.2), (-0.45, 0.22), (-0.7, 0.28), (-0.78, 0.48)]
    cv.poly(K.spline_outline(body, 8))
    cv.disc(-0.8, 0.66, 0.21)
    cv.poly(K.spline_outline([(-0.98, 0.72), (-1.07, 0.6), (-1.05, 0.49), (-0.9, 0.45),
                              (-0.76, 0.5)], 6))
    for ex, ez in ((-0.86, 0.86), (-0.68, 0.86)):
        cv.disc(ex, ez, 0.07)
    cv.brush([(-0.6, 0.38), (-0.74, 0.14), (-1.0, 0.07)], [0.24, 0.16, 0.12])
    cv.brush([(-0.36, 0.34), (-0.46, 0.13), (-0.68, 0.06)], [0.22, 0.15, 0.11])
    cv.brush([(0.62, 0.38), (0.42, 0.13), (0.16, 0.07)], [0.3, 0.17, 0.12])
    cv.brush([(0.78, 0.38), (0.66, 0.13), (0.44, 0.06)], [0.28, 0.15, 0.11])
    pts = K.spline_outline([(0.82, 0.5), (0.98, 0.58), (1.07, 0.75), (1.05, 0.93), (0.95, 1.02),
                            (0.86, 0.96)], 6, closed=False)
    cv.brush(pts, [0.11 - 0.06 * i / len(pts) for i in range(len(pts))])


def _tiger_inlay(name, box, seed=0):
    """Gold inlay of the tally (Pillow, alpha = inlay): tiger stripes, the eye, a line of
    inscription along the back."""
    from PIL import Image, ImageDraw, ImageFont
    x0, z0, x1, z1 = box
    W = 1024
    H = int(W * (z1 - z0) / (x1 - x0))
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def px(x, z):
        return ((x - x0) / (x1 - x0) * W, (1 - (z - z0) / (z1 - z0)) * H)
    g = (232, 200, 122, 255)
    for x in (-0.42, -0.18, 0.06, 0.3, 0.54):
        pts = [px(x + 0.06 * math.sin(t * 2.6) - 0.05 * t, 0.66 - 0.34 * t) for t in
               [k / 10.0 for k in range(11)]]
        for (ax, ay), (bx, by), k in zip(pts[:-1], pts[1:], range(10)):
            d.line([(ax, ay), (bx, by)], fill=g, width=max(3, int(16 * (1 - k / 11.0))))
    ex, ey = px(-0.86, 0.7)
    d.ellipse([ex - 13, ey - 9, ex + 13, ey + 9], fill=g)
    f = ImageFont.truetype(FONT_BRUSH, 46)
    for k, ch in enumerate("甲兵之符"):
        cx, cy = px(-0.5 + k * 0.2, 0.58)
        d.text((cx, cy), ch, font=f, fill=g, anchor="mm")
    return K.pil_image(name, im)


def Alliance(M, cam):
    """Two halves of a tiger tally (虎符) slid together: crouching tigers cast in bronze, the
    near half green with patina, the far half bright gold-bronze, both inlaid with gold stripes
    and an inscription, a red cord knotted through them."""
    from ironart import icons_shapes as S
    objs = []
    cv = S.Canvas(TIGER_BOX, 900)
    _tiger_shape(cv)
    inl = _tiger_inlay("TigerInlay", TIGER_BOX)
    near = gb.pigment("I_TallyPatina", "#8CB496", "#3A6450", fen=0.75, formk=0.25, image=inl,
                      image_color="#E8C87A", image_box=TIGER_BOX)
    far = gb.pigment("I_TallyBronze", "#D8B46A", "#8A6228", fen=0.75, formk=0.25, image=inl,
                     image_color="#F4DE9A", image_box=TIGER_BOX)
    a = S.shape_mesh("tallyA", cv, 0.24, near, bevel_w=0.07, segments=3)
    b = S.shape_mesh("tallyB", cv, 0.24, far, bevel_w=0.07, segments=3)
    objs += P.group("tbG", b, (0.32, 0.3, 0.46), (0, 0, 0))
    objs += P.group("taG", a, (0.0, 0.0, 0.0), (0, 0, 0))
    cord = P.cord("cord", M["rope_red"], [(0.05, -0.16, 0.72), (0.0, -0.2, 0.5),
                                          (0.05, -0.2, 0.25), (0.12, -0.18, 0.05)], 0.03)
    ring = K.torus("cring", 0.15, 0.03, M["rope_red"], 32, 8)
    K.place(ring, (0.03, 0.04, 0.72), (0, 90, 0))
    ring.scale = (1.0, 1.6, 1.0)
    objs += [cord, ring]
    objs += P.tassel("ts", M["tassel_red"], (0.12, -0.18, 0.05), 0.4, 0.07)
    objs = P.group("al", objs, (0, 0, 0), (0, 0, FACE + 8))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Truce(M, cam):
    """A white silk flag of truce streaming from a dark pole: deep folds shaded with ink grey,
    a mud-gold finial and a red tassel at the top."""
    objs = []
    pr = 0.04
    H = 2.3
    objs.append(K.lathe("tr_pole", [(0.0, 0.0), (pr, 0.0), (pr * 0.85, H), (0.0, H)],
                        M["wood_dark"], 16))
    fin = K.lathe("tr_fin", [(0.0, 0.0), (pr * 1.6, 0.0), (pr * 1.9, 0.05), (pr * 1.2, 0.09),
                             (pr * 0.9, 0.16), (pr * 1.6, 0.21), (0.0, 0.36)], M["gold"], 20)
    fin.location = (0, 0, H)
    objs.append(fin)
    w, h = 1.55, 1.08
    fold = gb.pigment("I_TruceSilk", "#F6F0E2", "#B8AE9C", fen=0.75, formk=0.3)

    def fn(u, v):
        x = u * w
        y = 0.16 * math.sin(u * math.pi * 2.3 + 0.3) * u ** 0.6 + 0.05 * math.sin(v * 3.0) * u
        z = h * (v - 1.0) - 0.28 * u ** 1.5 + 0.06 * math.sin(u * 7.0) * u * (1 - v)
        return (x + pr, y, z)
    cl = K.grid("tr_cloth", fn, 60, 24, fold, thickness=0.0)
    cl.location = (0, 0, H - 0.04)
    objs.append(cl)
    for k, zz in enumerate((H - 0.06, H - 0.04 - h * 0.5, H - 0.02 - h)):
        rg = K.torus("tr_ring%d" % k, pr * 1.3, 0.012, M["rope_red"], 16, 6)
        rg.location = (0, 0, zz)
        objs.append(rg)
    objs += P.tassel("tr_ts", M["tassel_red"], (0.0, -0.02, H + 0.02), 0.36, 0.06)
    objs = P.group("truce", objs, (0, 0, 0), (0, 0, FACE + 14))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def _gift_motif(name):
    """Mud-gold painted lid / front motif: a round 寿 medallion inside a cloud border."""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    g = (228, 196, 116, 255)
    d.ellipse([86, 86, 426, 426], outline=g, width=16)
    for k in range(8):
        a = TAU * k / 8
        cx, cy = 256 + 200 * math.cos(a), 256 + 200 * math.sin(a)
        d.arc([cx - 40, cy - 40, cx + 40, cy + 40], math.degrees(a) - 100, math.degrees(a) + 100,
              fill=g, width=12)
    f = ImageFont.truetype(FONT_BRUSH, 250)
    d.text((256, 262), "寿", font=f, fill=g, anchor="mm")
    return K.pil_image(name, im)


def Gift(M, cam):
    """A cinnabar-lacquer gift box (礼盒): a deep lid with mud-gold rims and a painted 寿
    medallion, bound with a malachite silk cord that crosses the lid and ties in a looped knot,
    two tassels falling over the front."""
    objs = []
    s, h, lid = 1.08, 0.72, 0.24
    img = _gift_motif("GiftMotif")
    body = gb.pigment("I_GiftBody", "#C8503A", "#7E2018", fen=0.55, formk=0.22, image=img,
                      image_box=(-0.2, -0.2, 0.2, 0.2))
    b = K.box("gb_body", (s, s, h - lid), body)
    b.location = (0, 0, (h - lid) / 2)
    objs.append(b)
    ld = K.box("gb_lid", (s * 1.05, s * 1.05, lid), M["lacquer_black"])
    ld.location = (0, 0, h - lid / 2 + 0.01)
    objs.append(ld)

    def frame(name, size, z, t, w=0.035):
        out = []
        for k, (dx, dy, sx, sy) in enumerate(((0, -1, 1, 0), (0, 1, 1, 0), (-1, 0, 0, 1),
                                              (1, 0, 0, 1))):
            bx = K.box("%s%d" % (name, k), (size * sx + w * (1 - sx), size * sy + w * (1 - sy), t),
                       M["gold"])
            bx.location = (dx * (size - w) / 2, dy * (size - w) / 2, z)
            out.append(bx)
        return out
    objs += frame("gb_rimA", s * 1.062, h - lid + 0.012, 0.035)
    objs += frame("gb_rimB", s * 1.062, h + 0.012 - 0.012, 0.03)
    objs += frame("gb_rimC", s * 1.012, 0.02, 0.04)
    cord = gb.pigment("I_GiftCord", "#6EAE8C", "#2A6A52", fen=0.45, formk=0.15)
    top = h + 0.025
    for ax in (0, 1):
        sz = (s * 1.075, 0.075, h + 0.05) if ax == 0 else (0.075, s * 1.075, h + 0.05)
        cb = K.box("gb_cord%d" % ax, sz, cord)
        cb.location = (0, 0, (h + 0.05) / 2)
        objs.append(cb)
    # the knot: a flat button knot and two loops lying on the lid, two tails to the front
    kn = K.sphere("gb_knot", 0.1, cord, 24, 12, (1.0, 1.0, 0.6))
    kn.location = (0, 0, top + 0.03)
    objs.append(kn)
    for sx in (-1, 1):
        lp = K.torus("gb_loop%d" % sx, 0.16, 0.032, cord, 40, 8)
        K.place(lp, (sx * 0.2, 0.04, top + 0.04), (0, -sx * 18, sx * 28))
        lp.scale = (1.0, 0.62, 1.0)
        objs.append(lp)
    for k, (dx, ln) in enumerate(((-0.1, 0.5), (0.1, 0.42))):
        objs.append(P.cord("gb_tail%d" % k, cord, [(0.0, 0.0, top + 0.03),
                                                   (dx * 0.6, -s * 0.3, top + 0.02),
                                                   (dx, -s * 0.54, top - 0.04),
                                                   (dx * 1.1, -s * 0.56, top - 0.2)], 0.028))
        objs += P.tassel("gb_ts%d" % k, M["tassel_red"], (dx * 1.1, -s * 0.56, top - 0.2), ln,
                         0.065)
    objs = P.group("gift", objs, (0, 0, 0), (0, 0, FACE + 4))
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
        f = P.flag_on_pole("f%d" % k, M, M[mat], 0.72, 0.55, h, wave=0.06, droop=0.1,
                           tassel=(k == 2), border="gold", swallow=0.32 if k == 2 else 0.0)
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
def _map_image(name):
    """A painted map for the Search scroll: blue-green peaks, a winding river, a red-walled
    town and a dotted route in ink (Pillow, RGBA)."""
    from PIL import Image, ImageDraw
    W, H = 768, 640
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    ink = (42, 36, 30, 255)
    d.line([(0, 470), (130, 420), (250, 480), (390, 400), (520, 450), (768, 380)],
           fill=(70, 118, 160, 255), width=26, joint="curve")
    for (x, y, sz, c) in ((120, 230, 92, (62, 142, 110)), (250, 200, 120, (50, 120, 96)),
                          (380, 250, 80, (62, 142, 110)), (620, 190, 104, (78, 150, 120))):
        d.polygon([(x - sz, y + sz * 0.7), (x - sz * 0.2, y - sz * 0.5), (x, y - sz * 0.62),
                   (x + sz * 0.3, y - sz * 0.35), (x + sz, y + sz * 0.7)],
                  fill=c + (255,), outline=ink, width=7)
    d.rectangle([520, 520, 610, 590], fill=(181, 56, 42, 255), outline=ink, width=7)
    for k in range(9):
        x = 150 + k * 42
        y = 560 - int(40 * math.sin(k * 0.6))
        d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=ink)
    return K.pil_image(name, im)


def Search(M, cam):
    """Searching the land: an unrolled map scroll held upright (peaks, river, a town, the
    dotted route) and, before it, a white paper lantern hanging from a bent bamboo stick."""
    objs = []
    W, H = 1.5, 1.15
    pm = gb.pigment("I_MapPaper", "#F2E8CE", "#CDB98E", fen=0.35, formk=0.12,
                    image=_map_image("MapImg"))
    objs += P.handscroll_open("mp", M, W, H, pm, 0.05, knob="jade", border="silk_green")
    objs = P.group("mapG", objs, (0.28, 0.45, 0.82), (-10, 0, FACE + 6))
    lt = P.lantern("lt", M, 0.38, 0.6, "white")
    objs += P.group("ltG", lt, (-0.5, -0.5, 0.85), (0, 0, 0))
    objs.append(K.tube("stick", [(-1.05, -0.45, 0.05), (-0.95, -0.5, 1.2), (-0.75, -0.52, 1.5),
                                 (-0.52, -0.5, 1.48)], 0.03, M["bamboo"], 8))
    objs.append(P.cord("lcord", M["rope_red"], [(-0.52, -0.5, 1.48), (-0.5, -0.5, 1.16)], 0.016))
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
