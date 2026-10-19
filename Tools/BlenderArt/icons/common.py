"""Icons family (gongbi): the shared pigment set - one palette for all 40 icons.

``M()`` returns a lazily-filled dict-like accessor: ``M()["gold"]`` builds the pigment material
on first use and caches it for the scene (``scene.reset`` wipes it between icons).  Colours are
DESIGN.md mineral pigments (``ironart.icons_gongbi.PAL``) and mixes of them; every material is
an emission wash (no light, no specular) with the facing 分染 and the painter's light term.
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from ironart import REPO_DIR  # noqa: E402
from ironart import icons_gongbi as gb  # noqa: E402

FONT_BRUSH = os.path.join(REPO_DIR, "Content", "Data", "Fonts", "Brush.ttf")


# ---------------------------------------------------------------------------------------------
# texture strokes (ic_ink AOV) - kept sparse: they must survive a 64 px downsample
# ---------------------------------------------------------------------------------------------
def _grain(axis="Z", freq=7.0, width=0.07, amount=0.55):
    """Wood grain: wavy lines running along local ``axis``."""
    def fn(b):
        co = b.sep(gb.obj_coord(b))
        across = co[0] if axis != "X" else co[1]
        return b.math("MULTIPLY", gb.stripes(b, across, freq, width, wobble=0.22, wscale=1.6,
                                             vec=gb.obj_coord(b)), amount)
    return fn


def _straw(freq=16.0, width=0.08, amount=0.4):
    def fn(b):
        co = b.sep(gb.obj_coord(b))
        ang = b.math("ARCTAN2", co[1], co[0])
        return b.math("MULTIPLY", gb.stripes(b, ang, freq / math.tau, width), amount)
    return fn


def _weave(scale=9.0, amount=0.28):
    """Hemp weave: a faint chequer of short strokes."""
    def fn(b):
        n = b.node("ShaderNodeTexChecker")
        n.inputs["Scale"].default_value = scale
        b.link(gb.obj_coord(b), n.inputs["Vector"])
        n.inputs["Color1"].default_value = (1, 1, 1, 1)
        n.inputs["Color2"].default_value = (0, 0, 0, 1)
        return b.math("MULTIPLY", n.outputs["Fac"], amount)
    return fn


def _bricks(scale=(1.0, 1.0, 1.0), amount=0.75, brick=(0.5, 0.25), mortar=0.03):
    """Ruled masonry lines (界画): the Brick texture's mortar in object space."""
    def fn(b):
        n = b.node("ShaderNodeTexBrick")
        n.inputs["Scale"].default_value = 1.0
        n.inputs["Mortar Size"].default_value = mortar
        n.inputs["Mortar Smooth"].default_value = 0.2
        n.inputs["Brick Width"].default_value = brick[0]
        n.inputs["Row Height"].default_value = brick[1]
        n.offset = 0.5
        m = b.node("ShaderNodeMapping")
        m.inputs["Scale"].default_value = scale
        # bricks in the XZ (front) and YZ (side) planes: use x + y as the horizontal run
        co = b.sep(gb.obj_coord(b))
        hx = b.math("ADD", co[0], co[1])
        b.link(b.comb(hx, co[2], 0.0), m.inputs["Vector"])
        b.link(m.outputs["Vector"], n.inputs["Vector"])
        return b.math("MULTIPLY", n.outputs["Fac"], amount)
    return fn


def _rows(axis=2, freq=8.0, width=0.08, amount=0.6):
    def fn(b):
        co = b.sep(gb.obj_coord(b))
        return b.math("MULTIPLY", gb.stripes(b, co[axis], freq, width), amount)
    return fn


def _zgrad(z0, z1, k=1.0):
    """Deepen from z1 (0) down to z0 (k) in object space."""
    def fn(b):
        co = b.sep(gb.obj_coord(b))
        return b.maprange(co[2], z0, z1, k, 0.0)
    return fn


def _zgrad_up(z0, z1, k=1.0):
    def fn(b):
        co = b.sep(gb.obj_coord(b))
        return b.maprange(co[2], z0, z1, 0.0, k)
    return fn


# ---------------------------------------------------------------------------------------------
# the library: key -> (factory, kwargs)
# ---------------------------------------------------------------------------------------------
P = gb.pigment
LIBRARY = {
    # metals: mud-gold, bronze, iron as painted washes (no speculars)
    "gold": (P, dict(name="I_Gold", light="#E4C77C", deep="#A07A30", fen=0.75, formk=0.22)),
    "gold_dark": (P, dict(name="I_GoldDark", light="#C9A24B", deep="#7E5E24", fen=0.7)),
    "bronze": (P, dict(name="I_Bronze", light="#C09A5A", deep="#6E4E24", fen=0.75, formk=0.24)),
    "patina": (P, dict(name="I_Patina", light="#8CBFA0", deep="#3E8E6E", fen=0.6)),
    "steel": (P, dict(name="I_Steel", light="#DCE0DA", deep="#7C8A90", fen=0.8, formk=0.22)),
    "iron": (P, dict(name="I_Iron", light="#8E928E", deep="#4A4E50", fen=0.6)),
    "iron_dark": (P, dict(name="I_IronDark", light="#5E605C", deep="#2E302E", fen=0.5)),
    # woods (ochre / ink-brown washes with sparse grain)
    "wood": (P, dict(name="I_Wood", light="#B88452", deep="#6E4426", ink=_grain("Z"))),
    "wood_x": (P, dict(name="I_WoodX", light="#B88452", deep="#6E4426", ink=_grain("X"))),
    "wood_plain": (P, dict(name="I_WoodPlain", light="#B88452", deep="#6E4426")),
    "wood_dark": (P, dict(name="I_WoodDark", light="#80563A", deep="#3E2818", fen=0.5)),
    "wood_pale": (P, dict(name="I_WoodPale", light="#D8B484", deep="#9A7044", ink=_grain("Z", 6.0))),
    "wood_pale_x": (P, dict(name="I_WoodPaleX", light="#D8B484", deep="#9A7044",
                            ink=_grain("X", 6.0))),
    "bamboo": (P, dict(name="I_Bamboo", light="#C9BA78", deep="#8A7A3E")),
    "bamboo_green": (P, dict(name="I_BambooGreen", light="#A9C08A", deep="#5E7E48")),
    # lacquer, silk, paper
    "lacquer_red": (P, dict(name="I_LacquerRed", light="#C64A34", deep="#7A1E16", fen=0.6)),
    "lacquer_black": (P, dict(name="I_LacquerBlack", light="#4E463E", deep="#1E1A16", fen=0.5,
                              hi=("#7A7068", 0.35))),
    "silk_red": (P, dict(name="I_SilkRed", light="#CC5038", deep="#8A2A20")),
    "silk_rouge": (P, dict(name="I_SilkRouge", light="#B85A66", deep="#7A2A38")),
    "silk_blue": (P, dict(name="I_SilkBlue", light="#7FA6C8", deep="#2B5C8A")),
    "silk_azure": (P, dict(name="I_SilkAzure", light="#4E7EAE", deep="#1E4468")),
    "silk_green": (P, dict(name="I_SilkGreen", light="#8CBFA0", deep="#3E8E6E")),
    "silk_gold": (P, dict(name="I_SilkGold", light="#E2C67E", deep="#A88438")),
    "silk_white": (P, dict(name="I_SilkWhite", light="#F6F0E2", deep="#CFC2A4", fen=0.6)),
    "silk_ink": (P, dict(name="I_SilkInk", light="#5A5248", deep="#2A241E")),
    "paper": (P, dict(name="I_Paper", light="#F6F0E2", deep="#D4C4A2", fen=0.45, formk=0.14)),
    "paper_old": (P, dict(name="I_PaperOld", light="#EADBB8", deep="#C2A87A", fen=0.45)),
    # fibres, food, ceramics
    "straw": (P, dict(name="I_Straw", light="#E6CC8A", deep="#A6843E")),
    "straw_lines": (P, dict(name="I_StrawLines", light="#E6CC8A", deep="#A6843E",
                            ink=_rows(2, 14.0, 0.07, 0.35))),
    "rice": (P, dict(name="I_Rice", light="#F4ECD4", deep="#C8B080", fen=0.6)),
    "grain": (P, dict(name="I_Grain", light="#E8C870", deep="#B08A34", fen=0.6)),
    "hemp": (P, dict(name="I_Hemp", light="#DCC79E", deep="#9A7E54", fen=0.6)),
    "celadon": (P, dict(name="I_Celadon", light="#BCD8C0", deep="#5E8E74", fen=0.7)),
    "porcelain": (P, dict(name="I_Porcelain", light="#F8F4EA", deep="#BEC2BA", fen=0.7)),
    "stoneware": (P, dict(name="I_Stoneware", light="#A86E44", deep="#4E301C", fen=0.75)),
    "tea": (P, dict(name="I_Tea", light="#B88A3E", deep="#7A5420", fen=0.2, formk=0.0)),
    "wine": (P, dict(name="I_Wine", light="#C4A060", deep="#8A6A34", fen=0.2, formk=0.0)),
    # building
    "stone": (P, dict(name="I_Stone", light="#D2CAB4", deep="#8E8672", fen=0.5)),
    "masonry": (P, dict(name="I_Masonry", light="#CFC6AE", deep="#8A826C", fen=0.35,
                        ink=_bricks((1.0, 1.0, 1.0), 0.55, (0.42, 0.2), 0.035))),
    "plaster": (P, dict(name="I_Plaster", light="#F2EADA", deep="#CDBF9E", fen=0.4)),
    "roof": (P, dict(name="I_Roof", light="#7E9094", deep="#3A4A50", fen=0.5)),
    "roof_ridge": (P, dict(name="I_RoofRidge", light="#5E6E72", deep="#2C383C", fen=0.4)),
    "pillar": (P, dict(name="I_Pillar", light="#C8503A", deep="#8A2A20", fen=0.5)),
    "earth": (P, dict(name="I_Earth", light="#C8A878", deep="#8A6A44", fen=0.5)),
    # misc
    "rope_red": (P, dict(name="I_RopeRed", light="#C8503A", deep="#7A2018", fen=0.5)),
    "rope_straw": (P, dict(name="I_RopeStraw", light="#D2B47A", deep="#8A6E3A", fen=0.5)),
    "rope_gold": (P, dict(name="I_RopeGold", light="#E2C67E", deep="#9A7A34", fen=0.5)),
    "tassel_red": (P, dict(name="I_TasselRed", light="#C84A36", deep="#8A2418", fen=0.3)),
    "hide": (P, dict(name="I_Hide", light="#F0E2C2", deep="#BEA070", fen=0.65)),
    "leather": (P, dict(name="I_Leather", light="#9A6A42", deep="#4E3020", fen=0.6)),
    "ox": (P, dict(name="I_Ox", light="#B87A48", deep="#5E3418", fen=0.75)),
    "bone": (P, dict(name="I_Bone", light="#F0E6CC", deep="#B8A47C", fen=0.6)),
    "jade": (P, dict(name="I_Jade", light="#9ACCAE", deep="#3E8E6E", fen=0.7)),
    "skin": (P, dict(name="I_Skin", light="#F4E2C8", deep="#CC9C78", fen=0.6, formk=0.12)),
    "ink": (gb.flat, dict(name="I_Ink", color="#2A241E")),
    "seal": (gb.flat, dict(name="I_Seal", color="#B5382A")),
    "white": (P, dict(name="I_White", light="#F8F4EA", deep="#D2C6AA", fen=0.5)),
    "feather": (P, dict(name="I_Feather", light="#F6F0E2", deep="#C8BCA0", fen=0.5)),
    "target_red": (P, dict(name="I_TargetRed", light="#C8503A", deep="#9A3424", fen=0.15)),
    "target_white": (P, dict(name="I_TargetWhite", light="#F4EEE0", deep="#D8CCB0", fen=0.15)),
    "target_blue": (P, dict(name="I_TargetBlue", light="#5E86B0", deep="#2B5C8A", fen=0.15)),
}


class _Lib(dict):
    def __missing__(self, key):
        fn, kw = LIBRARY[key]
        m = fn(**kw)
        self[key] = m
        return m


def M():
    return _Lib()


def flame_material(name="I_Flame", z0=0.0, z1=1.0):
    """Flame: gold heart rising into vermilion and cinnabar tongues (gradient up the flame) -
    the painted flames of Buddhist halos and battle scrolls."""
    def grad(b):
        co = b.sep(gb.obj_coord(b))
        return b.maprange(co[2], z0, z1, 0.0, 1.0)
    mat, b, created = gb.new_material(name)
    if not created:
        return mat
    t = grad(b)
    lw = b.node("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.35
    f = b.smooth(lw.outputs["Facing"], 0.05, 0.95)
    k = b.clamp01(b.math("ADD", b.math("MULTIPLY", t, 0.75), b.math("MULTIPLY", f, 0.55)))
    ramp = b.ramp(k, [(0.0, gb.lin("#F2D47A") + (1.0,)), (0.35, gb.lin("#E89A48") + (1.0,)),
                      (0.7, gb.lin("#D0643C") + (1.0,)), (1.0, gb.lin("#A42E20") + (1.0,))])
    em = b.node("ShaderNodeEmission")
    b.set(em.inputs["Color"], ramp)
    b.output(em.outputs[0])
    return mat


def cloud_material(name="I_Cloud", light="#F4EEE2", deep="#7FA6C8"):
    """Auspicious cloud (祥云): lead white body, azurite 晕染 into the scroll edges."""
    return gb.pigment(name, light, deep, fen=0.95, formk=0.1)
