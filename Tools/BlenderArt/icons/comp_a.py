"""Icons family, compositions A: documents, seals and tokens.

Each builder ``<Name>(M, cam)`` creates its still life in the family conventions (front -Y,
+Z up, ~2 units across) and returns ``dict(objs=[...], fill=1.0, offset=(dx, dy))``:
``fill`` < 1 balances the optical size of compact props, ``offset`` nudges the prop inside
the keyline (fractions of the box).
"""

import math

from common import FONT_BRUSH
from ironart import icons_kit as K
from ironart import icons_mats as im
from ironart import icons_props as P

FACE = -24.0          # yaw that turns a prop's -Y face square to the camera


def Save(M, cam):
    """Closed scroll, tied, with a red clay seal on the knot."""
    objs = P.scroll_rolled("save", M, length=1.6, r=0.17, outer="silk_blue", knob="jade",
                           tie="rope_red")
    # clay seal (feng ni) pressed on the tie
    img = P.stamp_image("SealFeng", "封", FONT_BRUSH, invert=True, rotate=0)
    sm = im.decal("I_SealFace", img, color="#E9C9A0", base="#A82A1A", rough=0.45, coat=0.4)
    disc = K.lathe("save_seal", [(0.0, 0.0), (0.17, 0.0), (0.2, 0.03), (0.19, 0.06),
                                 (0.15, 0.075), (0.0, 0.08)], M["lacquer_red"], 48)
    face = K.grid("save_seal_face", lambda u, v: ((u - 0.5) * 0.24, (v - 0.5) * 0.24, 0.081),
                  8, 8, sm)
    for o in (disc, face):
        K.place(o, (0.27, -0.2, -0.02), (90 - 28, 0, -10))
    objs += [disc, face]
    objs = P.group("save", objs, (0, 0, 0), (0, 34, -20))
    return dict(objs=objs, fill=1.0)


def Load(M, cam):
    """Open handscroll with calligraphy columns, propped towards the viewer."""
    cols = ["天下大势", "分久必合", "合久必分", "群雄并起"]
    img = K.glyph_image("LoadText", None, FONT_BRUSH, size=512, columns=cols, fill=0.86)
    objs = P.handscroll_open("load", M, w=1.5, h=0.95, image=img, curl=0.06)
    objs = P.group("load", objs, (0, 0, 0), (-22, 0, FACE * 0.7))
    return dict(objs=objs, fill=1.0)


def Recruit(M, cam):
    """A decree with a large vermilion seal, a writing brush laid across it."""
    from PIL import Image
    cols = ["招贤纳士", "唯才是举", "天下英雄"]
    txt = K.glyph_image("RecruitText", None, FONT_BRUSH, size=512, columns=cols, fill=0.8)
    objs = P.handscroll_open("rec", M, w=1.25, h=0.95, image=txt, curl=0.05, knob="gold")
    # seal impression as a separate decal card lying on the paper (lower left)
    st = P.stamp_image("RecruitStamp", "令", FONT_BRUSH, size=256)
    sm = im.decal("I_RecruitStamp", st, color="#B02418", base="#EADFC4", rough=0.85)
    card = K.grid("rec_stamp", lambda u, v: (-0.5 + u * 0.36, -0.035, -0.4 + v * 0.36), 4, 4, sm)
    card.data.materials[0].blend_method = "OPAQUE"
    objs.append(card)
    objs = P.group("rec", objs, (0, 0.1, 0), (-24, 0, FACE * 0.6))
    b = P.brush("rec_brush", M, length=1.45)
    objs += P.group("rec_b", b, (0.1, -0.42, -0.42), (0, -62, -12))
    return dict(objs=objs, fill=1.0)


def Order(M, cam):
    """Seal of office: a gold seal with a crouching-beast knob and a red tassel, on a
    folded silk cloth."""
    objs = P.seal_block("ord", M, size=0.62, height=0.5, mat="gold", tassel_mat="rope_red")
    tz = 0.31 + 0.02
    objs += P.tassel("ord_t", M["silk_red"], top=(0.36, 0.05, tz), length=0.55, radius=0.07,
                     strands=60, seed=3, sway=(0.06, -0.05))
    cloth = K.box("ord_cloth", (1.15, 1.0, 0.07), M["silk_red"], bevel_w=0.03, segments=4)
    cloth.location = (0, 0, -0.035)
    objs.append(cloth)
    objs = P.group("ord", objs, (0, 0, 0), (0, 0, 18))
    return dict(objs=objs, fill=0.96)


def Loyalty(M, cam):
    """A round red-lacquer plaque with a raised gold 忠 (loyalty), hung from a knotted cord
    with a tassel."""
    objs = []
    R = 0.62
    disc = K.lathe("loy_disc", [(0.0, -0.06), (R * 0.96, -0.06), (R, -0.04), (R, 0.04),
                                (R * 0.96, 0.06), (R * 0.84, 0.06), (R * 0.82, 0.075),
                                (R * 0.8, 0.06), (0.0, 0.06)], M["lacquer_red"], 96)
    disc.data.use_auto_smooth = True
    disc.data.auto_smooth_angle = math.radians(35)
    rim = K.torus("loy_rim", R * 0.98, 0.035, M["gold"], 96, 12)
    ring2 = K.torus("loy_rim2", R * 0.8, 0.014, M["gold"], 96, 8)
    ring2.location = (0, 0, 0.06)
    g = K.text("loy_glyph", "忠", FONT_BRUSH, size=0.86, depth=0.03, mat=M["gold"],
               bevel_depth=0.006)
    g.location = (0, -0.02, 0.06)
    parts = [disc, rim, ring2, g]
    for o in parts:
        o.rotation_euler = (math.radians(90), 0, 0)
        o.location = (o.location.x, -o.location.z, o.location.y)
    objs += parts
    # cord loop above + knot + tassel below
    objs.append(P.cord("loy_cord", M["rope_red"], [(-0.08, 0, R + 0.0), (-0.12, 0, R + 0.18),
                                                   (0.0, 0, R + 0.3), (0.12, 0, R + 0.18),
                                                   (0.08, 0, R + 0.0)], 0.022))
    knot = K.sphere("loy_knot", 0.06, M["rope_red"], 24, 12, (1.0, 0.8, 1.2))
    knot.location = (0, 0, -R - 0.05)
    objs.append(knot)
    objs += P.tassel("loy_t", M["silk_red"], top=(0, 0, -R - 0.08), length=0.45, radius=0.06,
                     strands=50, seed=5)
    objs = P.group("loy", objs, (0, 0, 0), (-10, 0, FACE * 0.75))
    return dict(objs=objs, fill=1.0)
