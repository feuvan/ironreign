"""Icons family (gongbi), compositions: the court and its documents - Recruit, Save, Load,
Order, Loyalty, Delegate, Officers, Settings, Undo, EndTurn.

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

TEXT = ["天下大势", "分久必合", "合久必分", "群雄并起", "英雄辈出"]


# ---------------------------------------------------------------------------------------------
def _spiral_end(name, light="#F4ECD8"):
    """The end of a rolled scroll: paper turns drawn as an ink spiral round the roller."""
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pts = []
    for k in range(400):
        t = k / 399.0
        a = TAU * 3.2 * t
        r = 70 + 170 * t
        pts.append((256 + r * math.cos(a), 256 + r * math.sin(a)))
    d.line(pts, fill=(60, 48, 36, 255), width=7, joint="curve")
    return K.pil_image(name, im)


def Save(M, cam):
    """Saving the record: a closed scroll mounted in azurite brocade with a pale title slip,
    tied with red cord and sealed with a cinnabar clay seal (封泥) stamped 封; the near end
    shows the rolled paper and a jade roller knob."""
    from PIL import Image, ImageDraw
    L, R = 1.75, 0.26
    br = Image.new("RGBA", (256, 860), (0, 0, 0, 0))
    d = ImageDraw.Draw(br)
    for row in range(14):
        for col in range(5):
            x = 26 + col * 52 + (26 if row % 2 else 0)
            y = 30 + row * 62
            d.ellipse([x - 11, y - 11, x + 11, y + 11], outline=(226, 196, 118, 255), width=5)
            d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(226, 196, 118, 255))
    brocade = gb.pigment("I_SaveBrocade", "#4E7EAE", "#1E4468", fen=0.6, formk=0.25,
                         image=K.pil_image("SaveBrocadeImg", br), image_box=(-R, -L / 2, R, L / 2))
    M["silk_brocade"] = brocade
    objs = P.scroll_rolled("sv", M, L, R, outer="silk_brocade", knob="jade", tie="rope_red")
    endimg = _spiral_end("ScrollEnd")
    endm = gb.pigment("I_ScrollEnd", "#F6EEDA", "#CDB98E", fen=0.3, formk=0.0, image=endimg,
                      image_color="#4A3A2A", image_box=(-0.26, -0.26, 0.26, 0.26),
                      image_plane="XY")
    for sgn in (-1, 1):
        e = K.lathe("sv_endpaper%d" % sgn, [(0.0, 0.0), (0.257, 0.0), (0.257, 0.006),
                                            (0.0, 0.006)], endm, 64)
        K.place(e, (sgn * (1.75 / 2 + 0.002), 0, 0), (0, 90 * sgn, 0))
        objs.append(e)
    img = P.seal_image("SaveSeal", "封", FONT_BRUSH, 256, invert=True)
    sm = gb.pigment("I_SaveSeal", "#C04A34", "#7A2418", fen=0.5, image=img,
                    image_color="#F0E2C8")
    disc = K.lathe("seal", [(0.0, 0.0), (0.22, 0.0), (0.25, 0.04), (0.24, 0.08), (0.0, 0.085)],
                   M["lacquer_red"], 48)
    face = K.grid("seal_face", lambda u, v: ((u - 0.5) * 0.32, (v - 0.5) * 0.32, 0.086), 8, 8, sm)
    sg = P.group("sealG", [disc, face], (0.3, -0.24, -0.04), (90 - 14, 0, -10))
    objs += sg
    objs = P.group("save", objs, (0, 0, 0), (0, 14, -78))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Load(M, cam):
    """An open handscroll: calligraphy columns on paper between azurite silk borders."""
    pm = P.paper_text("I_LoadPaper", TEXT[:3], FONT_BRUSH, 1.2 / 0.95)
    objs = P.handscroll_open("ld", M, 1.2, 0.95, pm, 0.06, knob="jade", border="silk_blue")
    objs = P.group("load", objs, (0, 0, 0), (-18, 0, FACE * 0.8))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Recruit(M, cam):
    """A decree inviting talent: an open sheet with calligraphy and a large vermilion seal, a
    writing brush laid across it."""
    objs = []
    W, H = 1.3, 1.0
    img = P.glyph_image("RecTxt", None, FONT_BRUSH, 512, 0.84,
                        columns=["招贤纳士", "唯才是举", "天下英雄"], aspect=W / H, color=(42, 36, 30))
    pm = gb.pigment("I_RecPaper", "#F6F0E2", "#D4C4A2", fen=0.4, formk=0.12, image=img,
                    image_color="#3A322A")

    def sheet(u, v):
        return (-W / 2 + u * W, 0.04 * math.sin(u * math.pi * 1.2), -H / 2 + v * H)
    s = K.grid("rec_sheet", sheet, 24, 2, pm)
    objs.append(s)
    st = P.seal_image("RecStamp", "令", FONT_BRUSH, 256, invert=False, rotate=4)
    sm = gb.pigment("I_RecStamp", "#F6F0E2", "#E6D8B8", fen=0.0, formk=0.0, image=st,
                    image_color="#B5382A")
    card = K.grid("rec_stamp", lambda u, v: (-0.56 + u * 0.4, 0.04 * math.sin((-0.56 + u * 0.4 + W / 2) / W * math.pi * 1.2) - 0.004,
                                             -0.46 + v * 0.4), 4, 4, sm)
    objs.append(card)
    gb.put([card], "none")
    objs = P.group("rec", objs, (0, 0.15, 0.1), (-28, 0, FACE * 0.6))
    b = P.brush("rb", M, 1.5)
    objs += P.group("rec_b", b, (0.15, -0.45, -0.35), (0, -58, -8))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Order(M, cam):
    """The seal of office (官印): a mud-gold seal cast with a tortoise knob standing on a slip of
    paper that carries its cinnabar impression (令, 朱文), a red silk cord looped through the
    knob and trailing in a tassel."""
    objs = []
    objs += P.group("ordG", P.tortoise_seal("ord", M, 0.8, 0.52, "gold"), (-0.12, 0.3, 0.04),
                    (0, 0, FACE + 14), 1.15)
    st = P.seal_image("OrdStamp", "令", FONT_BRUSH, 256, invert=False, rotate=-3)
    sm = gb.pigment("I_OrdSlip", "#F6F0E2", "#D8C8A4", fen=0.35, formk=0.1, image=st,
                    image_color="#B5382A", image_box=(-0.2, -0.78, 0.38, -0.2), image_plane="XY")
    slip = K.grid("ord_slip", lambda u, v: (-0.32 + u * 0.78, -0.86 + v * 0.74,
                                            0.01 * math.sin(u * 3.0)), 8, 8, sm)
    objs.append(slip)
    cord = [(0.3, 0.3, 0.7), (0.55, 0.16, 0.66), (0.7, 0.0, 0.5), (0.74, -0.08, 0.36)]
    objs.append(P.cord("ord_cord", M["rope_red"], cord, 0.026))
    objs += P.tassel("ord_t", M["tassel_red"], (0.74, -0.08, 0.38), 0.42, 0.08)
    objs = P.group("ord", objs, (0, 0, 0), (0, 0, 6))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Loyalty(M, cam):
    """A round cinnabar plaque with a raised mud-gold 忠 (loyalty) in a gold rim, a knotted cord
    above and a short tassel below."""
    objs = []
    R = 0.72
    disc = K.lathe("loy_disc", [(0.0, -0.07), (R, -0.07), (R, 0.07), (0.0, 0.07)],
                   M["lacquer_red"], 96)
    rim = K.torus("loy_rim", R, 0.055, M["gold"], 96, 12)
    ring2 = K.torus("loy_rim2", R * 0.8, 0.018, M["gold"], 96, 8)
    ring2.location = (0, 0, 0.07)
    g = K.text("loy_glyph", "忠", FONT_BRUSH, size=0.95, depth=0.03, mat=M["gold"])
    g.location = (0, -0.02, 0.08)
    parts = [disc, rim, ring2, g]
    for o in parts:
        o.rotation_euler = (math.radians(90), 0, 0)
        o.location = (o.location.x, -o.location.z, o.location.y)
    objs += parts
    objs.append(P.cord("loy_cord", M["rope_red"], [(-0.08, 0, R + 0.0), (-0.12, 0, R + 0.16),
                                                   (0.0, 0, R + 0.24), (0.12, 0, R + 0.16),
                                                   (0.08, 0, R + 0.0)], 0.026))
    objs += P.tassel("loy_t", M["tassel_red"], (0, 0, -R - 0.04), 0.36, 0.08)
    objs = P.group("loy", objs, (0, 0, 0), (-8, 0, FACE * 0.8))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def _sleeve(name, mat, length=1.0, r0=0.2, r1=0.36, hang=0.45, n=14):
    """A wide official's sleeve along +X (shoulder at x = -length, cuff at x = 0): a tube
    widening to the cuff with its pocket hanging below."""
    secs = []
    for k in range(n):
        t = k / (n - 1.0)
        x = -length + t * length
        r = r0 + (r1 - r0) * t ** 1.2
        ring = []
        for j in range(40):
            a = TAU * j / 40
            ca, sa = math.cos(a), math.sin(a)
            low = max(0.0, -sa)
            h = hang * t ** 1.5 * low ** 1.8
            ring.append((x - 0.18 * t * low ** 2, r * ca * 0.85, r * sa - h))
        secs.append(ring)

    def folds(b):
        co = b.sep(gb.obj_coord(b))
        ang = b.math("ARCTAN2", co[2], co[1])
        return b.math("MULTIPLY", gb.stripes(b, ang, 4.0 / TAU, 0.05, wobble=0.35, wscale=1.4,
                                             vec=gb.obj_coord(b)), 0.4)
    return K.loft(name, secs, mat, cap0=True, cap1=False), secs[-1]


def _hand_pinch(name, mat, s=1.0):
    """A hand reaching out along +X from the wrist (origin), back of the hand up, fingers
    curled under, holding a cord between thumb and index finger; returns (objects, pinch)."""
    objs = []
    palm = K.sphere(name + "_palm", 1.0, mat, 32, 16, (0.2 * s, 0.13 * s, 0.075 * s))
    palm.location = (0.16 * s, 0.0, 0.0)
    objs.append(palm)
    wrist = K.tube(name + "_wrist", [(-0.12 * s, 0, 0.0), (0.06 * s, 0, 0.0)], 0.08 * s, mat, 16)
    objs.append(wrist)
    for k, (y, L) in enumerate(((-0.085, 0.25), (-0.028, 0.27), (0.03, 0.25), (0.085, 0.2))):
        y *= s
        if k == 0:
            pts = [(0.3 * s, y, 0.01 * s), (0.3 * s + L * 0.55 * s, y - 0.01 * s, -0.01 * s),
                   (0.3 * s + L * 0.8 * s, y - 0.02 * s, -0.08 * s)]
        else:
            pts = [(0.3 * s, y, 0.01 * s), (0.3 * s + L * 0.5 * s, y, -0.01 * s),
                   (0.3 * s + L * 0.72 * s, y, -0.09 * s), (0.3 * s + L * 0.5 * s, y, -0.15 * s)]
        objs.append(K.curve_tube("%s_f%d" % (name, k), pts, 0.033 * s, mat, 6, 8,
                                 radius_fn=lambda t: 1.0 - 0.18 * t))
    th = [(0.08 * s, -0.11 * s, -0.02 * s), (0.24 * s, -0.15 * s, -0.06 * s),
          (0.4 * s, -0.12 * s, -0.08 * s), (0.47 * s, -0.1 * s, -0.08 * s)]
    objs.append(K.curve_tube(name + "_thumb", th, 0.037 * s, mat, 6, 8,
                             radius_fn=lambda t: 1.0 - 0.2 * t))
    return objs, (0.49 * s, -0.1 * s, -0.09 * s)


def _hand_palm_up(name, mat, s=1.0):
    """A hand held out palm up along +X from the wrist (origin), fingers together and gently
    cupped, thumb on the near side (-Y): separate finger forms so the ink draws each one."""
    objs = []
    palm = K.sphere(name + "_palm", 1.0, mat, 32, 16, (0.2 * s, 0.14 * s, 0.065 * s))
    palm.location = (0.15 * s, 0.0, 0.0)
    objs.append(palm)
    heel = K.sphere(name + "_heel", 1.0, mat, 24, 12, (0.1 * s, 0.11 * s, 0.07 * s))
    heel.location = (0.02 * s, -0.04 * s, -0.01 * s)
    objs.append(heel)
    for k, (y, L) in enumerate(((-0.075, 0.25), (-0.025, 0.28), (0.028, 0.265), (0.08, 0.22))):
        y *= s
        pts = [(0.28 * s, y, 0.0), (0.28 * s + L * 0.55 * s, y, 0.015 * s),
               (0.28 * s + L * s, y, 0.07 * s)]
        objs.append(K.curve_tube("%s_f%d" % (name, k), pts, 0.031 * s, mat, 6, 8,
                                 radius_fn=lambda t: 1.0 - 0.2 * t))
    th = [(0.06 * s, -0.12 * s, 0.0), (0.2 * s, -0.19 * s, 0.04 * s),
          (0.32 * s, -0.2 * s, 0.1 * s)]
    objs.append(K.curve_tube(name + "_thumb", th, 0.036 * s, mat, 6, 8,
                             radius_fn=lambda t: 1.0 - 0.25 * t))
    return objs


def _sleeve_diag(name, mat, S, C, r0=0.2, r1=0.36, hang=0.5, n=16, pleats=6):
    """A wide official's sleeve from the shoulder ``S`` to the cuff ``C`` (world points): rings
    square to the arm, widening to the cuff, the pocket hanging straight down below the arm,
    soft pleats in the cloth so the ink draws its folds."""
    from mathutils import Vector
    S, C = Vector(S), Vector(C)
    ax = (C - S).normalized()
    u = Vector((0.0, 1.0, 0.0))
    w = ax.cross(u).normalized()
    if w.z < 0:
        w = -w
    u = w.cross(ax).normalized()
    secs = []
    for k in range(n):
        t = k / (n - 1.0)
        c = S + (C - S) * t
        r = r0 + (r1 - r0) * t ** 1.2
        ring = []
        for j in range(48):
            a = TAU * j / 48
            ca, sa = math.cos(a), math.sin(a)
            rr = r * (1.0 + 0.045 * math.sin(a * pleats) * t)
            p = c + u * (rr * ca * 0.9) + w * (rr * sa)
            low = max(0.0, -sa)
            p.z -= hang * t ** 1.6 * low ** 1.6
            ring.append(tuple(p))
        secs.append(ring)
    o = K.loft(name, secs, mat, cap0=True, cap1=False)
    # ring angle per vertex (0..1) for the painted fold lines (cap centre gets 0)
    # vertices keep the loft order (ring k, point j -> k * 48 + j); the cap adds none
    n_v = len(o.data.vertices)
    vals = [(i % 48) / 48.0 if i < n * 48 else 0.0 for i in range(n_v)]
    K.vattr(o, "ring_u", vals)
    return o


def _fold_ink(b):
    """Painted fold lines running along a sleeve (vertex attribute ``ring_u``)."""
    u = gb.attr(b, "ring_u")
    return b.math("MULTIPLY", gb.stripes(b, u, 7.0, 0.05, wobble=0.06, wscale=2.0,
                                         vec=gb.obj_coord(b)), 0.55)


def Delegate(M, cam):
    """Delegation (授印): a hand reaching down out of an azurite official's sleeve (gold cuff,
    white lining) hands over the seal of office - the gold tortoise-knob seal hanging from the
    red cord pinched in its fingers, its tassel swinging."""
    from mathutils import Vector
    objs = []
    sleeve_mat = gb.pigment("I_Sleeve", "#8AAED0", "#2B5C8A", fen=0.6, formk=0.25,
                            ink=_fold_ink)
    S, C = (-0.85, 0.42, 0.95), (-0.15, -0.12, 0.45)
    objs.append(_sleeve_diag("sleeve", sleeve_mat, S, C, 0.2, 0.34, 0.75))
    ax = (Vector(C) - Vector(S)).normalized()
    pitch = math.degrees(math.atan2(-ax.z, ax.x))
    cuff = K.torus("cuff", 0.3, 0.045, M["gold"], 48, 8)
    K.place(cuff, C, (0, 90 + pitch, 0))
    cuff.scale = (1.0, 0.9, 1.0)
    objs.append(cuff)
    lining = K.lathe("lining", [(0.0, -0.01), (0.29, -0.01), (0.29, 0.0), (0.0, 0.0)],
                     M["silk_white"], 32)
    K.place(lining, tuple(Vector(C) - ax * 0.02), (0, 90 + pitch, 0))
    lining.scale = (1.0, 0.9, 1.0)
    objs.append(lining)
    skin = gb.pigment("I_HandSkin", "#F0D6B8", "#BE8460", fen=0.6, formk=0.2)
    hand, pinch = _hand_pinch("hand", skin, 1.6)
    gb.put(hand, "soft")
    hp = Vector(C) - ax * 0.12
    objs += P.group("handG", hand, tuple(hp), (0, pitch * 0.8, 0))
    # pinch point in world space (the group pitch rotates the hand about its wrist)
    pr = math.radians(pitch * 0.8)
    px = hp.x + pinch[0] * math.cos(pr) + pinch[2] * math.sin(pr)
    pz = hp.z - pinch[0] * math.sin(pr) + pinch[2] * math.cos(pr)
    py = hp.y + pinch[1]
    sz = -0.92
    objs += P.group("dlG", P.tortoise_seal("dl", M, 0.6, 0.42, "gold", cord=None),
                    (px + 0.02, py + 0.02, sz), (0, 0, 20))
    knob_top = sz + 0.42 * 0.9 + 0.6 * 0.26
    objs.append(P.cord("dl_cord", M["rope_red"], [(px, py, pz), (px + 0.02, py, (pz + knob_top) / 2),
                                                  (px + 0.03, py + 0.01, knob_top - 0.02)], 0.02))
    tx, ty, tz = px + 0.42, py - 0.2, sz + 0.3
    objs += P.tassel("dl_t", M["tassel_red"], (tx, ty, tz), 0.44, 0.065)
    objs.append(P.cord("dl_cord2", M["rope_red"], [(px + 0.03, py + 0.01, knob_top - 0.02),
                                                   (px + 0.25, py - 0.12, knob_top - 0.04),
                                                   (tx, ty, tz)], 0.017))
    objs = P.group("dg", objs, (0, 0, 0), (0, 0, FACE + 4))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Officers(M, cam):
    """Civil and military officers: a general's Ming helmet with its red horsehair tassel, and
    a large writing brush laid across in front of it."""
    objs = P.helmet_ming("hm", M, 0.5)
    objs = P.group("hmG", objs, (-0.1, 0.25, 0.32), (0, 0, FACE + 10))
    b = P.brush("ob", M, 1.85, 0.055, tip_len=0.36)
    objs += P.group("obG", b, (0.62, -0.62, 0.0), (0, -66, -8))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def _gear_outline(teeth=10, r_out=0.62, r_in=0.5, n=10):
    pts = []
    for i in range(teeth):
        a0 = TAU * i / teeth
        da = TAU / teeth
        for k in range(n):
            t = k / n
            a = a0 + da * t
            # trapezoid tooth profile: up 0.15-0.3, top 0.3-0.6, down 0.6-0.75
            if t < 0.15 or t >= 0.75:
                r = r_in
            elif t < 0.3:
                r = r_in + (r_out - r_in) * (t - 0.15) / 0.15
            elif t < 0.6:
                r = r_out
            else:
                r = r_out - (r_out - r_in) * (t - 0.6) / 0.15
            pts.append((r * math.cos(a), r * math.sin(a)))
    return pts


def Settings(M, cam):
    """A cast bronze gear wheel (the workings of state), its face chased with a ring of cloud
    scrolls, a jade hub, a red cord and tassel hanging from the lowest tooth."""
    from PIL import Image, ImageDraw
    objs = []
    box = (-0.7, -0.7, 0.7, 0.7)
    im = Image.new("RGBA", (768, 768), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    ink = (42, 30, 18, 255)

    def px(x, z):
        return ((x - box[0]) / 1.4 * 768, (box[3] - z) / 1.4 * 768)
    for rr, wd in ((0.47, 6), (0.27, 6)):
        x0, y0 = px(-rr, rr)
        x1, y1 = px(rr, -rr)
        d.ellipse([x0, y0, x1, y1], outline=ink, width=wd)
    for k in range(8):
        a = TAU * k / 8 + 0.2
        cx, cy = px(0.37 * math.cos(a), 0.37 * math.sin(a))
        r = 0.06 / 1.4 * 768
        d.arc([cx - r, cy - r, cx + r, cy + r], math.degrees(-a) - 40, math.degrees(-a) + 220,
              fill=ink, width=6)
    img = K.pil_image("GearChase", im)
    mat = gb.pigment("I_GearBronze", "#D2AE6A", "#7A5626", fen=0.75, formk=0.2, image=img,
                     image_color="#5A3E1E", image_box=box)
    hole = [(0.12 * math.cos(TAU * k / 32), 0.12 * math.sin(TAU * k / 32)) for k in range(32)]
    g = K.outline_mesh("gear", _gear_outline(10, 0.66, 0.54, 12), 0.16, mat, plane="XZ",
                       holes=[hole[::-1]], bevel_w=0.015, segments=2)
    objs.append(g)
    hub = K.torus("hub", 0.15, 0.045, M["jade"], 48, 8)
    K.place(hub, (0, -0.085, 0), (90, 0, 0))
    objs.append(hub)
    objs.append(P.cord("cord", M["rope_red"], [(0.0, -0.02, -0.56), (0.03, -0.06, -0.72),
                                               (0.02, -0.08, -0.86)], 0.022))
    objs += P.tassel("ts", M["tassel_red"], (0.02, -0.08, -0.84), 0.46, 0.075)
    objs = P.group("set", objs, (0, 0, 0), (-TILT * 0.6, 0, FACE + 10))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Undo(M, cam):
    """Undo: one azurite brush stroke that sets off to the right, turns back over the top and
    returns to the left in a barbed arrowhead - shaded from a deep root to a pale head."""
    from ironart import icons_shapes as S
    cv = S.Canvas((-1.2, -1.2, 1.2, 1.2), 900)

    def path(t):
        a = math.radians(-35 + 245 * t)
        r = 0.72 - 0.06 * t
        return (r * math.cos(a) + 0.05, r * math.sin(a) - 0.05)
    S.brush_arrow(cv, path, 0.07, 0.3, 0.5, 0.3)
    mat = gb.pigment("I_UndoStroke", "#7FA6C8", "#1E4468", fen=0.55, formk=0.0,
                     grad=lambda b: b.maprange(b.sep(gb.obj_coord(b))[2], -0.7, 0.8, 0.7, 0.0))
    parts = S.shape_mesh("undo", cv, 0.08, mat)
    objs = P.group("undo", parts, (0, 0, 0), (-TILT, 0, FACE))
    return dict(objs=objs, fill=0.96)


# ---------------------------------------------------------------------------------------------
def EndTurn(M, cam):
    """The bronze gong (锣) hanging in a lacquered frame, the beater leaning against it."""
    objs = []
    R = 0.55
    prof = [(0.0, 0.03), (R * 0.3, 0.03), (R * 0.55, 0.0), (R * 0.9, -0.01), (R, -0.06),
            (R * 1.02, -0.12), (R * 0.97, -0.12), (R * 0.9, -0.05), (R * 0.5, -0.03),
            (0.0, -0.02)]
    gong = K.lathe("gong", prof, M["bronze"], 96)
    boss = K.sphere("gboss", 0.15, M["gold"], 32, 16, (1, 1, 0.45))
    boss.location = (0, 0, 0.03)
    gp = P.group("gongG", [gong, boss], (0, 0, 0.95), (90, 0, 0))
    objs += gp
    # frame: two posts on feet and a crossbar with upturned ends
    for sx in (-1, 1):
        post = K.box("post%d" % sx, (0.09, 0.09, 1.75), M["lacquer_red"])
        post.location = (sx * 0.78, 0.0, 0.875)
        foot = K.box("foot%d" % sx, (0.12, 0.6, 0.1), M["wood_dark"])
        foot.location = (sx * 0.78, 0.0, 0.05)
        objs += [post, foot]
        cord = P.cord("gcord%d" % sx, M["rope_red"], [(sx * 0.78, 0.0, 1.62),
                                                      (sx * 0.4, 0.0, 1.55),
                                                      (sx * 0.38, 0.0, 1.42)], 0.016)
        objs.append(cord)
    bar = K.tube("bar", [(-0.98, 0, 1.76), (-0.8, 0, 1.72), (0.8, 0, 1.72), (0.98, 0, 1.76)],
                 0.055, M["lacquer_red"], 12)
    objs.append(bar)
    for sx in (-1, 1):
        cap = K.sphere("cap%d" % sx, 0.07, M["gold"], 16, 8)
        cap.location = (sx * 1.0, 0, 1.78)
        objs.append(cap)
    beater = [K.lathe("bt", [(0.0, 0.0), (0.03, 0.0), (0.026, 0.95), (0.0, 0.95)], M["wood"], 12)]
    hd = K.sphere("bth", 0.1, M["silk_red"], 24, 12, (1, 1, 1.2))
    hd.location = (0, 0, 0.98)
    beater.append(hd)
    objs += P.group("btG", beater, (0.42, -0.4, 0.0), (0, 22, 0))
    objs = P.group("et", objs, (0, 0, 0), (0, 0, FACE))
    return dict(objs=objs, fill=1.0)
