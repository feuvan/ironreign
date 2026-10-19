"""Battle family: gongbi procedural materials for the board props (baked by Cycles).

Every material ends in ONE Principled BSDF (:class:`ironart.world_gongbi.GW` vocabulary), so
:func:`ironart.world_bake.bake` can bake its base colour (no light) and tangent normal.  Colours
are flat mineral washes with soft 晕染 gradients and painted ink marks; no AO, dirt or gloss.

``B_Rock``      blue-green landscape rock (青绿): ochre underpainting, malachite on the tops,
                ink 皴 texture strokes along strata and cracks
``B_Grass``     grass blades, deep malachite at the root to pale tips (MetreUV v = along blade)
``B_Trunk``     tree trunks and limbs: umber-ochre wash with ink bark marks
``B_Canopy``    dotted-leaf (点叶) crowns: malachite wash, pale on top, deep beneath, ink-green
                leaf dots; ``B_CanopyAz`` the azurite variant
``B_Pine``      pine needle pads: deep blue-green wash, radiating ink needle strokes from the
                pad centre (attributes ``pad_x`` / ``pad_y``), pale crown
``B_Earth``     packed earth / debris heaps: ochre wash with pebble dots
``B_Reed``      reeds and rushes
Plus the World Models architecture set (``W_*``, :func:`ironart.world_gongbi.library`).

Line widths follow the atlas texel density (:func:`ironart.world_gongbi.set_density`).
"""

import bpy

from . import world_gongbi as WG
from .world_gongbi import GW, G
from .world_mats import L


def _fresh(name):
    old = bpy.data.materials.get(name)
    if old is not None:
        old.name = name + "__old"
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    from .materials import NB
    nb = NB(m.node_tree)
    for n in list(nb.nodes):
        if n.bl_idname != "ShaderNodeOutputMaterial":
            nb.nodes.remove(n)
    return m, GW(nb)


def rock(name="B_Rock", base="#B8A486", deep="#8E7C64", top="#8FAE8C", top2="#6E9A7E", line="#3E3024",
         scale=1.0):
    mat, w = _fresh(name)
    o = w.obj()
    s = w.sep(o)
    nz = w.sep(w.nb.coord("Normal"))["Z"]
    n1 = w.noise(w.scale(o, 1.6 / scale), 1.0, 3, 0.5)
    col = w.mix(L(base), L(deep), w.mr(n1, 0.3, 0.75))
    col = w.wash(col, 0.05, 0.9 / scale, 0.03, 30.0)
    # mineral green laid on the up-facing parts (soft-edged wash)
    patch = w.noise(w.scale(o, 2.4 / scale), 1.0, 3, 0.5)
    up = w.mr(w.m("ADD", nz, w.m("MULTIPLY", w.m("SUBTRACT", patch, 0.5), 0.5)), 0.86, 1.02)
    up = w.m("MULTIPLY", up, 0.8)
    green = w.mix(L(top), L(top2), w.mr(patch, 0.35, 0.7))
    col = w.mix(col, green, up)
    # 皴: strata + cracks in thin graded ink, on the faces
    wob = w.noise(w.scale(o, 1.2 / scale), 1.0, 2)
    zz = w.m("ADD", s["Z"], w.m("MULTIPLY", wob, 0.12 * scale))
    strata = w.line(w.periodic_dist(zz, 0.11 * scale), 0.006 * scale)
    brk = w.noise(w.scale(o, (3.0 / scale, 3.0 / scale, 1.0 / scale)), 1.0, 2)
    strata = w.m("MULTIPLY", strata, w.mr(brk, 0.42, 0.58))
    cr = w.voronoi(w.scale(o, (2.2 / scale, 2.2 / scale, 3.5 / scale)), 1.0, "DISTANCE_TO_EDGE")
    crack = w.m("MULTIPLY", w.mr(cr, 0.0, 0.05, 1.0, 0.0), w.mr(brk, 0.3, 0.5))
    strokes = w.m("MAXIMUM", strata, crack)
    strokes = w.m("MULTIPLY", strokes, w.mr(nz, 0.8, 0.35))
    col = w.ink(col, strokes, line, 0.6)
    w.paint_out(col, w.m("SUBTRACT", 1.0, strokes), 0.25, 0.01)
    return mat


def grass(name="B_Grass", root="#6A9070", mid="#92B48E", tip="#CADAB2"):
    mat, w = _fresh(name)
    f = w.sep(w.uv())["Y"]                       # 0 at the root .. 1 at the tip
    col = w.mix(L(root), L(mid), w.mr(f, 0.0, 0.5))
    col = w.mix(col, L(tip), w.mr(f, 0.5, 1.0))
    col = w.wash(col, 0.06, 2.0, 0.02, 40.0)
    w.paint_out(col)
    return mat


def trunk(name="B_Trunk", color="#6E5038", deep="#4E3826", line="#22180F"):
    mat, w = _fresh(name)
    o = w.obj()
    n = w.noise(w.scale(o, (6.0, 6.0, 1.5)), 1.0, 3, 0.55)
    col = w.mix(L(color), L(deep), w.mr(n, 0.35, 0.7))
    col = w.wash(col, 0.05, 1.5, 0.03, 40.0)
    # ink bark marks: short broken rings / scales
    sc = w.voronoi(w.scale(o, (9.0, 9.0, 5.0)), 1.0, "DISTANCE_TO_EDGE")
    marks = w.m("MULTIPLY", w.mr(sc, 0.0, 0.07, 1.0, 0.0), w.mr(n, 0.4, 0.6))
    col = w.ink(col, marks, line, 0.65)
    w.paint_out(col, w.m("SUBTRACT", 1.0, marks), 0.3, 0.005)
    return mat


def pine_bark(name="B_PineBark", color="#86603F", deep="#5E4028", line="#2A1C12"):
    """Pine bark: warm umber wash with ink scale rings (龟甲 scales)."""
    mat, w = _fresh(name)
    o = w.obj()
    n = w.noise(w.scale(o, (5.0, 5.0, 1.2)), 1.0, 3, 0.55)
    col = w.mix(L(color), L(deep), w.mr(n, 0.3, 0.75))
    col = w.wash(col, 0.05, 1.5, 0.03, 40.0)
    sc = w.voronoi(w.scale(o, (14.0, 14.0, 9.0)), 1.0, "DISTANCE_TO_EDGE")
    marks = w.mr(sc, 0.0, 0.06, 1.0, 0.0)
    col = w.ink(col, marks, line, 0.7)
    w.paint_out(col, w.m("SUBTRACT", 1.0, marks), 0.35, 0.005)
    return mat


def canopy(name="B_Canopy", top="#7FAA84", side="#44825F", under="#22493A", dot="#13261C", dot2="#28503F",
           density=19.0):
    """点叶 crown: wash graded by the normal (pale crown, deep underside - a painted gradient, not
    light), two sizes of ink-green leaf dots, a few lighter dots on the crown."""
    mat, w = _fresh(name)
    o = w.obj()
    nz = w.sep(w.nb.coord("Normal"))["Z"]
    n = w.noise(w.scale(o, 2.2), 1.0, 3, 0.5)
    g = w.m("ADD", nz, w.m("MULTIPLY", w.m("SUBTRACT", n, 0.5), 0.5))
    col = w.mix(L(under), L(side), w.mr(g, -0.6, 0.15))
    col = w.mix(col, L(top), w.mr(g, 0.55, 1.05))
    col = w.wash(col, 0.05, 2.5, 0.025, 50.0)
    # leaf dots: voronoi cell centres (small round marks), denser in the shade
    v1 = w.voronoi(w.scale(o, density), 1.0)
    shade = w.mr(g, 0.7, -0.2, 0.0, 1.0)
    r1 = w.m("ADD", 0.2, w.m("MULTIPLY", shade, 0.14))
    d1 = w.mr(w.m("SUBTRACT", v1, r1), 0.025, -0.025)
    col = w.ink(col, d1, dot, 0.85)
    v2 = w.voronoi(w.scale(o, density * 1.8), 1.0)
    d2 = w.m("MULTIPLY", w.mr(w.m("SUBTRACT", v2, 0.2), 0.03, -0.03), w.mr(n, 0.4, 0.58))
    col = w.ink(col, d2, dot2, 0.75)
    w.paint_out(col, w.m("MAXIMUM", d1, d2), 0.3, 0.01)
    return mat


def pine(name="B_Pine", top="#5F9A86", mid="#2D6A5E", deep="#1C433E", needle="#10261F"):
    """Needle pads: a wash from the pale crown to the deep rim, needle strokes radiating from the
    pad centre (attributes pad_x / pad_y written by the builder)."""
    mat, w = _fresh(name)
    import math
    o = w.obj()
    s = w.sep(o)
    nz = w.sep(w.nb.coord("Normal"))["Z"]
    cx = w.nb.attr("pad_x").outputs["Fac"]
    cy = w.nb.attr("pad_y").outputs["Fac"]
    dx = w.m("SUBTRACT", s["X"], cx)
    dy = w.m("SUBTRACT", s["Y"], cy)
    ang = w.m("ARCTAN2", dy, dx)
    rad = w.m("SQRT", w.m("ADD", w.m("MULTIPLY", dx, dx), w.m("MULTIPLY", dy, dy)))
    col = w.mix(L(deep), L(mid), w.mr(nz, -0.3, 0.4))
    col = w.mix(col, L(top), w.m("MULTIPLY", w.mr(nz, 0.55, 0.95), w.mr(rad, 0.35, 0.05)))
    col = w.wash(col, 0.05, 3.0, 0.02, 50.0)
    # radiating needles: angular lines, broken along the radius
    k = 46.0
    a = w.m("MULTIPLY", w.m("ADD", ang, w.m("MULTIPLY", rad, 1.3)), k / (2 * math.pi))
    fa = w.m("FRACT", a)
    dist = w.m("MULTIPLY", w.m("MINIMUM", fa, w.m("SUBTRACT", 1.0, fa)), w.m("MULTIPLY", rad, 2 * math.pi / k))
    lines = w.line(dist, 0.004)
    brk = w.noise(w.scale(o, 9.0), 1.0, 2)
    lines = w.m("MULTIPLY", lines, w.mr(brk, 0.3, 0.5))
    lines = w.m("MULTIPLY", lines, w.mr(rad, 0.03, 0.09))
    col = w.ink(col, lines, needle, 0.75)
    w.paint_out(col, lines, 0.2, 0.005)
    return mat


def earth(name="B_Earth", color="#C2A880", deep="#A08460", dot="#6E5A44"):
    mat, w = _fresh(name)
    o = w.obj()
    n = w.noise(w.scale(o, 2.0), 1.0, 3, 0.5)
    col = w.mix(L(color), L(deep), w.mr(n, 0.3, 0.7))
    col = w.wash(col, 0.05, 1.2, 0.03, 40.0)
    v = w.voronoi(w.scale(o, 14.0), 1.0)
    pebble = w.m("MULTIPLY", w.mr(v, 0.16, 0.12), w.mr(w.noise(w.scale(o, 5.0), 1.0, 2), 0.5, 0.62))
    col = w.ink(col, pebble, dot, 0.6)
    w.paint_out(col, pebble, 0.2, 0.01)
    return mat


def reed(name="B_Reed", root="#5E7A50", tip="#C2B47E"):
    mat, w = _fresh(name)
    t = w.sep(w.uv())["Y"]
    col = w.mix(L(root), L(tip), w.mr(t, 0.15, 0.85))
    w.paint_out(w.wash(col, 0.04, 2.0, 0.02))
    return mat


def flat(name, color, amount=0.04):
    mat, w = _fresh(name)
    w.paint_out(w.wash(L(color), amount, 1.5, 0.02))
    return mat


def library(density=None, kit_scale=1.0):
    """The battle props set (B_*) + the World Models architecture set (W_*), for the texel density
    ``density`` px / m (painted line widths).  ``kit_scale``: the architecture is built in kit
    metres scaled by this factor (:data:`ironart.battle_arch.K`), so its patterns see
    ``density * kit_scale`` texels per MetreUV metre."""
    if density:
        WG.set_density(density * kit_scale)
    # world_gongbi materials are reused by name: rebuild them for this density
    for m in list(bpy.data.materials):
        if m.name.startswith("W_") and m.users == 0:
            bpy.data.materials.remove(m)
        elif m.name.startswith("W_"):
            m.name = m.name + "__old"
    lib = dict(WG.library())
    if density:
        WG.set_density(density)
    for fn, args, kw in (
            (rock, (), {}),
            (rock, ("B_RockBig",), dict(scale=2.6)),
            (rock, ("B_RockGrey", "#ADA598", "#857D72", "#96AE96", "#7A9884"), {}),
            (rock, ("B_StoneFlat", "#ABA496", "#8A8276", "#A2A898", "#8E9688"), {}),
            (grass, (), {}),
            (trunk, (), {}),
            (canopy, (), {}),
            (canopy, ("B_CanopyAz", "#78A098", "#3A6E70", "#1E4044", "#0E2428", "#285050"), {}),
            (canopy, ("B_CanopyOl", "#A4AE76", "#6A844C", "#3C5232", "#20301A", "#445A34"), {}),
            (pine_bark, (), {}),
            (pine, (), {}),
            (earth, (), {}),
            (reed, (), {}),
            (flat, ("B_Dark", "#3A2E26"), {}),
            (flat, ("B_Cinnabar", G["cinnabar"]), {}),
            (flat, ("B_Gold", G["gold"]), {}),
            (flat, ("B_White", "#EDE5D2"), {}),
    ):
        m = fn(*args, **kw)
        lib[m.name] = m
    return lib
