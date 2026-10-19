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
TAU = math.tau

TEXT = ["天下大势", "分久必合", "合久必分", "群雄并起", "英雄辈出"]


# ---------------------------------------------------------------------------------------------
def Save(M, cam):
    """A closed scroll, tied with red cord and sealed with a clay seal (封泥) stamped 封."""
    objs = P.scroll_rolled("sv", M, 1.7, 0.21, outer="silk_azure", knob="jade", tie="rope_red")
    img = P.seal_image("SaveSeal", "封", FONT_BRUSH, 256, invert=True)
    sm = gb.pigment("I_SaveSeal", "#C04A34", "#7A2418", fen=0.5, image=img,
                    image_color="#F0E2C8")
    # seal: a thick disc pressed on the tie, its face square to the camera
    disc = K.lathe("seal", [(0.0, 0.0), (0.2, 0.0), (0.23, 0.035), (0.22, 0.07), (0.0, 0.075)],
                   M["lacquer_red"], 48)
    face = K.grid("seal_face", lambda u, v: ((u - 0.5) * 0.3, (v - 0.5) * 0.3, 0.076), 8, 8, sm)
    sg = P.group("sealG", [disc, face], (0.26, -0.2, -0.04), (90 - 18, 0, -12))
    objs += sg
    objs = P.group("save", objs, (0, 0, 0), (0, 28, -18))
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
    """The seal of office: a mud-gold seal with a crouching-beast knob, its red tassel trailing,
    on a folded cinnabar silk cloth."""
    objs = P.seal_block("ord", M, size=0.7, height=0.56, mat="gold", tassel_mat="rope_red",
                        knob="tortoise")
    objs += P.tassel("ord_t", M["tassel_red"], (0.45, -0.05, 0.42), 0.5, 0.075)
    cord = P.cord("ord_cord", M["rope_red"], [(0.06, 0.05, 0.58), (0.3, 0.0, 0.62),
                                             (0.45, -0.05, 0.42)], 0.02)
    objs.append(cord)
    cloth = K.box("ord_cloth", (1.3, 1.1, 0.08), M["silk_azure"])
    cloth.location = (0, 0, -0.04)
    objs.append(cloth)
    hem = K.box("ord_hem", (1.34, 1.14, 0.03), M["gold"])
    hem.location = (0, 0, -0.095)
    objs.append(hem)
    objs = P.group("ord", objs, (0, 0, 0), (0, 0, 18))
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
def _hand(name, mat):
    """A hand palm up, fingers together and gently curled, thumb towards the viewer (-Y):
    metaballs, wrist at the origin, pointing along +X."""
    els = [dict(type="ELLIPSOID", co=(0.2, 0.0, 0.0), radius=0.18, size=(1.0, 1.0, 0.36)),
           dict(type="ELLIPSOID", co=(0.03, 0.0, -0.01), radius=0.13, size=(0.9, 0.9, 0.55))]
    for k, y in enumerate((0.105, 0.04, -0.025, -0.09)):
        L = (0.2, 0.25, 0.26, 0.22)[k]
        x0 = 0.34
        els.append(dict(type="CAPSULE", co=(x0 + L * 0.3, y, 0.015), radius=0.045,
                        size=(L * 0.32, 1, 1)))
        els.append(dict(type="CAPSULE", co=(x0 + L * 0.8, y, 0.05), radius=0.04,
                        size=(L * 0.2, 1, 1), rot=(0, -35, 0)))
    els.append(dict(type="CAPSULE", co=(0.2, 0.15, 0.05), radius=0.05, size=(0.08, 1, 1),
                    rot=(0, -25, -30)))
    return K.metaball(name, els, mat, resolution=0.01, threshold=0.6)


def Delegate(M, cam):
    """Delegation (授印): a hand reaching from an azurite sleeve with a gold cuff, the gold seal
    of office resting on its open palm, the seal's red tassel hanging."""
    objs = []
    secs = []
    for k in range(12):
        t = k / 11.0
        x = -0.8 + t * 0.8
        r = 0.15 + 0.19 * t ** 1.3
        ring = []
        for j in range(40):
            a = TAU * j / 40
            ca, sa = math.cos(a), math.sin(a)
            low = max(0.0, -sa)
            hang = 0.42 * t ** 1.4 * low ** 1.6           # the sleeve's hanging pocket
            ring.append((x + 0.12 * t * low, r * ca * 0.9, r * sa - hang))
        secs.append(ring)

    def folds(b):
        co = b.sep(gb.obj_coord(b))
        ang = b.math("ARCTAN2", co[2], co[1])
        return b.math("MULTIPLY", gb.stripes(b, ang, 5.0 / TAU, 0.05, wobble=0.3, wscale=1.5,
                                             vec=gb.obj_coord(b)), 0.45)
    sleeve_mat = gb.pigment("I_Sleeve", "#7FA6C8", "#2B5C8A", fen=0.6, ink=folds)
    sl = K.loft("sleeve", secs, sleeve_mat, cap0=True, cap1=False)
    objs.append(sl)
    lining = K.lathe("lining", [(0.0, -0.01), (0.3, -0.01), (0.3, 0.0), (0.0, 0.0)],
                     M["silk_white"], 32)
    K.place(lining, (-0.01, 0, -0.02), (0, 90, 0))
    lining.scale = (1.0, 0.9, 1.0)
    objs.append(lining)
    cuff = K.torus("cuff", 0.33, 0.035, M["gold"], 48, 8)
    K.place(cuff, (0.0, 0, -0.02), (0, 90, 0))
    cuff.scale = (1.0, 0.92, 1.0)
    objs.append(cuff)
    hand = _hand("hand", M["skin"])
    hand.location = (0.02, 0.0, -0.02)
    hand.scale = (1.8, 1.8, 1.8)
    objs.append(hand)
    seal = P.seal_block("dl", M, size=0.36, height=0.32, mat="gold", tassel_mat="rope_red",
                        knob="tortoise")
    objs += P.group("dlG", seal, (0.58, 0.04, 0.06), (0, 0, 18))
    objs += P.tassel("dl_t", M["tassel_red"], (0.72, -0.14, 0.2), 0.5, 0.075)
    objs = P.group("dg", objs, (0, 0, 0), (0, 0, FACE - 18))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Officers(M, cam):
    """Civil and military officers: a general's helmet and a writing brush laid across it."""
    objs = P.helmet("hm", M, 0.5)
    objs = P.group("hmG", objs, (-0.15, 0.2, 0.0), (0, 0, FACE))
    b = P.brush("ob", M, 1.7, 0.05)
    objs += P.group("obG", b, (0.55, -0.55, -0.1), (0, -64, -14))
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
    """A bronze gear wheel cast with a cloud ring, a red tassel hanging from it."""
    objs = []
    hole = [(0.13 * math.cos(TAU * k / 32), 0.13 * math.sin(TAU * k / 32)) for k in range(32)]
    g = K.outline_mesh("gear", _gear_outline(10, 0.66, 0.53, 10), 0.16, M["bronze"],
                       plane="XZ", holes=[hole[::-1]])
    objs.append(g)
    ring = K.torus("ring", 0.36, 0.035, M["patina"], 64, 8)
    K.place(ring, (0, -0.085, 0), (90, 0, 0))
    objs.append(ring)
    hub = K.torus("hub", 0.155, 0.04, M["gold"], 48, 8)
    K.place(hub, (0, -0.085, 0), (90, 0, 0))
    objs.append(hub)
    for k in range(5):
        a = TAU * k / 5 + 0.3
        sp = K.box("spoke%d" % k, (0.06, 0.04, 0.2), M["bronze"])
        K.place(sp, (0.26 * math.cos(a), -0.08, 0.26 * math.sin(a)),
                (0, -math.degrees(a) + 90, 0))
        objs.append(sp)
    objs.append(P.cord("cord", M["rope_red"], [(0.0, -0.09, -0.2), (0.05, -0.12, -0.4),
                                               (0.02, -0.12, -0.62)], 0.022))
    objs += P.tassel("ts", M["tassel_red"], (0.02, -0.12, -0.6), 0.42, 0.075)
    objs = P.group("set", objs, (0, 0, 0), (0, 0, FACE))
    return dict(objs=objs, fill=1.0)


# ---------------------------------------------------------------------------------------------
def Undo(M, cam):
    """Undo: an azurite silk ribbon curling back counter-clockwise into an arrowhead."""
    outer, inner = [], []
    n = 36
    R = 0.62
    w = 0.2
    for k in range(n + 1):
        t = k / n
        a = math.radians(-50 + 255 * t)
        ww = w * (0.7 + 0.3 * t)
        outer.append(((R + ww / 2) * math.cos(a), (R + ww / 2) * math.sin(a)))
        inner.append(((R - ww / 2) * math.cos(a), (R - ww / 2) * math.sin(a)))
    a = math.radians(205)
    c, s_ = math.cos(a), math.sin(a)
    tc, ts_ = -math.sin(a), math.cos(a)            # tangent (counter-clockwise)
    hb = 0.27
    head = [((R + hb) * c, (R + hb) * s_), (R * c + tc * 0.4, R * s_ + ts_ * 0.4),
            ((R - hb) * c, (R - hb) * s_)]
    body = K.outline_mesh("undo_body", outer + head + inner[::-1], 0.12, M["silk_azure"],
                          plane="XZ")
    objs = P.group("undo", [body], (0, 0, 0), (0, 0, FACE))
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
