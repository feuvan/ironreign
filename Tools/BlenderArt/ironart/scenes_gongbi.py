"""Illustrated Scenes family: gongbi ink-and-colour painting on silk (工笔重彩 / 界画 / 青绿山水).

The scenes are built in 3D (metres, +Z up) with the family kits (``scenes_people``,
``world_kit``, ``scenes_gongbi_flora``, ``scenes_gongbi_land``) and rendered as a painting:

* **Colour** is *flat mineral washes*: every material is an emission shader (no lights, no cast
  shadows, no speculars) whose colour is a pigment mixed from the DESIGN.md mineral palette,
  graded by a soft 晕染 term (facing ratio = 分染 deepening towards the outlines, optional height or
  slope gradients) and a very gentle "painter's light" (one direction for the whole picture).
  Colours are authored *as they look painted on the reference silk* ``SILK_REF``.
* **Ink** is Freestyle, one line set per collection kind (:data:`INK`): ``arch`` ruled even lines
  (界画), ``fig`` fine tapered lines for figures (游丝 / 铁线描), ``land`` looser pressure-varied
  strokes for rocks and mountains, ``tree`` for trunks / canopies, ``fine`` for light inner detail.
  Texture strokes that Freestyle cannot draw (皴 on rock faces, 点苔 moss dots, pine-needle wheels,
  water 水纹, armour lamellae) are painted by the materials into the ``gb_ink`` AOV.
* **Passes** (EXR): colour (premultiplied, film transparent), Freestyle, depth, AOVs ``gb_ink``,
  ``gb_bare`` (how much of the surface is left as bare silk), ``gb_nomist`` and ``gb_pos`` (world
  position, for mist that lies in the valleys).
* **Composite** (numpy, :func:`composite`): sky wash (screen-space gradient, painted 2D elements
  from :mod:`ironart.scenes_gongbi_2d`), distance fade to paler washes, mist bands of bare silk,
  pigment granulation and edge pooling, ink with a hint of bleed, and the aged silk ground (warp /
  weft fibres, slubs, mottling, darker edges) multiplied through everything.

No bloom, no depth of field, no photographic light anywhere.  Every look number lives in
:data:`RECIPE` / :data:`INK` (and in the scene modules' ``look`` dicts).
"""

import math
import os

import numpy as np

# =============================================================================================
# palette (sRGB) - DESIGN.md section 8 + a few mixed tones used by the scenes
# =============================================================================================
PAL = {
    "silk": "#E6D6B0", "silk_edge": "#D8C39A", "ink": "#1E1A16",
    "malachite": "#3E8E6E", "malachite_l": "#8CBFA0",
    "azurite": "#2B5C8A", "azurite_l": "#7FA6C8",
    "cinnabar": "#B5382A", "vermilion": "#D0643C", "ochre": "#A0643A", "rouge": "#9E3B4A",
    "gold": "#C9A24B", "white": "#F0E8D8",
    # mixed tones
    "ochre_l": "#C9A274", "ochre_d": "#7A4A2A", "ink_grey": "#6E665C", "ink_grey_l": "#A79E8E",
    "ink_wash": "#4A443C", "indigo": "#2E3F5C", "indigo_d": "#1E2838", "teal": "#2F6A6A",
    "malachite_d": "#2A6A52", "azurite_d": "#1E4468", "cinnabar_d": "#8A2A20",
    "gold_l": "#DCC07A", "gold_d": "#9A7A34", "skin": "#EAD8BC", "skin_d": "#D4B08C",
    "straw": "#C8AA6E", "earth": "#B89A70", "wood": "#7A5236", "wood_d": "#4A3424",
    "plaster": "#E8DCC4", "stone": "#B4AA98", "stone_d": "#8A8070", "tile": "#5A6A6E",
    "tile_d": "#3A464A", "jade": "#6FA38A",
}

#: reference silk the pigment colours are authored on (the composite divides it out)
SILK_REF = PAL["silk"]

RECIPE = dict(
    ss=2,                        # render = ss x master (events: 2560x1440 for a 1280x720 master)
    # every size below is in GAME (1x) px: the code multiplies by k (render px per game px) or
    # m (master px per game px)
    spp=12, preview_spp=6, adaptive_threshold=0.03, filter_width=1.2,
    form=0.10,                   # painter's light: value range of the (N.L) term
    light_dir=(-0.55, -0.45, 0.70),
    # composite
    silk=dict(fibre=0.035, slub=0.03, mottle=0.045, stain=0.03, edge=0.13, edge_px=0.18,
              pitch=0.85),
    granulation=0.10, pooling=0.22, pooling_px=1.1, streak=0.035, mottle=0.16,
    ink_bleed=0.35, ink_dry=0.18, ink_strength=0.94,
    shader_ink=0.85,
    age=dict(yellow=0.035, desat=0.06),
    rim=0.55, rim_px=2.6,         # 分染: colour deepening along the outlines (image-space ink)
)

#: Freestyle ink per collection kind: thickness in GAME (1x) px (scaled by the render px per game
#: px, ``k`` in :func:`setup_ink`), alpha, brush feel, distance fall-off (metres)
INK = {
    #         thick  alpha  taper  calli  noise  wobble  dist (near, far, thick@far, alpha@far)
    "arch": dict(t=1.25, a=0.92, taper=0.08, calli=0.0, noise=0.0, wobble=0.0, smooth=False,
                 edges=("silhouette", "border", "crease", "external_contour"), lmin=3.0,
                 dist=(20.0, 400.0, 0.55, 0.55), color="ink"),
    "fig": dict(t=0.95, a=0.92, taper=0.35, calli=0.25, noise=0.12, wobble=0.0, smooth=True,
                edges=("silhouette", "border", "crease", "external_contour", "material_boundary"),
                lmin=1.5, dist=(8.0, 200.0, 0.55, 0.7), color="ink"),
    "land": dict(t=1.9, a=0.9, taper=0.3, calli=0.55, noise=0.45, wobble=0.35, smooth=True,
                 edges=("silhouette", "external_contour"), lmin=6.0,
                 dist=(40.0, 2500.0, 0.35, 0.25), color="ink"),
    "tree": dict(t=1.15, a=0.9, taper=0.3, calli=0.35, noise=0.3, wobble=0.15, smooth=True,
                 edges=("silhouette", "border", "external_contour"), lmin=2.0,
                 dist=(20.0, 1500.0, 0.4, 0.35), color="ink"),
    "fine": dict(t=0.6, a=0.5, taper=0.2, calli=0.0, noise=0.1, wobble=0.0, smooth=False,
                 edges=("silhouette", "crease", "border", "external_contour"), lmin=2.0,
                 dist=(20.0, 400.0, 0.5, 0.4), color="ink"),
    # interior folds of the land (ridges / suggestive contours): off unless a scene enables it
    "land_fold": dict(t=1.0, a=0.6, taper=0.4, calli=0.5, noise=0.4, wobble=0.3, smooth=True,
                      edges=("suggestive", "ridge"), lmin=10.0, dist=(40.0, 2500.0, 0.35, 0.2),
                      color="ink", col="land", off=True),
    # faces and hands: fine reddish-brown line (赭线), the classical way flesh is outlined
    "skin": dict(t=0.55, a=0.75, taper=0.3, calli=0.0, noise=0.0, wobble=0.0, smooth=True,
                 edges=("silhouette", "external_contour"), lmin=0.5, dist=(5.0, 120.0, 0.6, 0.6),
                 color="#8A5A40"),
    "cloud": dict(t=1.0, a=0.55, taper=0.4, calli=0.3, noise=0.25, wobble=0.2, smooth=True,
                  edges=("silhouette", "external_contour"), lmin=4.0,
                  dist=(40.0, 3000.0, 0.5, 0.4), color="ink_grey"),
}

AOVS = (("gb_ink", "VALUE"), ("gb_bare", "VALUE"), ("gb_nomist", "VALUE"), ("gb_pos", "COLOR"))

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))


# =============================================================================================
# colour helpers
# =============================================================================================
def _hex(c):
    c = PAL.get(c, c)
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def srgb(c):
    """Token / '#hex' / sRGB tuple -> sRGB float triple."""
    if isinstance(c, str):
        return _hex(c)
    return tuple(float(x) for x in c[:3])


def to_lin(x):
    x = np.asarray(x, np.float64)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def to_srgb(x):
    x = np.clip(np.asarray(x, np.float32), 0.0, None)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055).astype(np.float32)


def lin(c):
    """Token / '#hex' -> linear RGB tuple (what emission sockets need)."""
    return tuple(float(v) for v in to_lin(srgb(c)))


def lin4(c):
    return lin(c) + (1.0,)


def deepen(col, s, ref=None):
    """Layer more of the same pigment: col_rel ** (1 + s) relative to the silk (darker and
    richer, never grey).  ``s`` H x W (0..1) or scalar."""
    ref = np.array(srgb(ref or SILK_REF), np.float32)
    rel = np.clip(col / ref[None, None, :], 1e-4, 1.5)
    s = np.asarray(s, np.float32)
    if s.ndim == 2:
        s = s[..., None]
    return (ref[None, None, :] * rel ** (1.0 + s)).astype(np.float32)


def mixc(a, b, t):
    """Mix two colours in sRGB (painter's mixing) -> sRGB tuple."""
    a, b = srgb(a), srgb(b)
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def shade(c, k):
    """Deepen (k < 1) / lighten towards lead white (k > 1) a colour, sRGB tuple out."""
    c = srgb(c)
    if k <= 1.0:
        return tuple(x * k for x in c)
    w = srgb(PAL["white"])
    t = min(1.0, k - 1.0)
    return tuple(x + (y - x) * t for x, y in zip(c, w))


# =============================================================================================
# materials (emission washes + AOVs)
# =============================================================================================
def _aov(nb, name, value):
    a = nb.node("ShaderNodeOutputAOV")
    if hasattr(a, "aov_name"):
        a.aov_name = name
    else:
        a.name = name
    if name == "gb_pos":
        nb.set(a.inputs["Color"], value)
    else:
        nb.set(a.inputs["Value"], value)
    return a


def _form_group():
    """Shared node group: painter's light term 0..1 = clamp(N.L * 0.5 + 0.5)."""
    import bpy
    from .scenes_sky import new_group
    g = bpy.data.node_groups.get("GB_Form")
    if g is not None:
        return g
    g, gb, gi, go = new_group("GB_Form", [], [("Light", "NodeSocketFloat"), ("Up", "NodeSocketFloat")])
    geo = gb.node("ShaderNodeNewGeometry")
    L = gb.node("ShaderNodeCombineXYZ", name="GB_LightDir")
    v = RECIPE["light_dir"]
    n = math.sqrt(sum(x * x for x in v))
    for i, k in enumerate("XYZ"):
        L.inputs[k].default_value = v[i] / n
    d = gb.vmath("DOT_PRODUCT", geo.outputs["Normal"], L.outputs[0])
    f = gb.math("ADD", gb.math("MULTIPLY", d.outputs["Value"], 0.5), 0.5, clamp=True)
    gb.link(f, go.inputs["Light"])
    gb.link(gb.sep(geo.outputs["Normal"])[2], go.inputs["Up"])
    return g


def _screen_group():
    """Shared node group: screen position of the shaded point in GAME px from the image centre
    (x right, y up) = view vector / z x focal length in game px (set by :func:`set_screen`), so
    texture strokes can keep a constant on-screen spacing at any distance."""
    import bpy
    from .scenes_sky import new_group
    g = bpy.data.node_groups.get("GB_Screen")
    if g is not None:
        return g
    g, gb, gi, go = new_group("GB_Screen", [], [("X", "NodeSocketFloat"), ("Y", "NodeSocketFloat")])
    cd = gb.node("ShaderNodeCameraData")
    v = gb.sep(cd.outputs["View Vector"])
    f = gb.node("ShaderNodeValue", name="GB_FocalPx")
    f.outputs[0].default_value = 1000.0
    # Cycles' camera-space view vector looks down +z
    inv = gb.math("DIVIDE", f.outputs[0], gb.math("MAXIMUM", v[2], 1e-4))
    gb.link(gb.math("MULTIPLY", v[0], inv), go.inputs["X"])
    gb.link(gb.math("MULTIPLY", v[1], inv), go.inputs["Y"])
    return g


def set_screen(focal_px):
    """Focal length in game px (lens / sensor width x game width) for :func:`screen` (and every
    node group holding a ``GB_FocalPx`` value)."""
    import bpy
    _screen_group().nodes["GB_FocalPx"].outputs[0].default_value = float(focal_px)
    for g in bpy.data.node_groups:
        n = g.nodes.get("GB_FocalPx")
        if n is not None:
            n.outputs[0].default_value = float(focal_px)


def screen(b):
    """(x, y) sockets: screen position in game px (see :func:`_screen_group`)."""
    gn = b.node("ShaderNodeGroup")
    gn.node_tree = _screen_group()
    return gn.outputs["X"], gn.outputs["Y"]


def set_light(direction):
    """Point the painter's light (world vector *towards* the light) for every material."""
    g = _form_group()
    L = g.nodes["GB_LightDir"]
    n = math.sqrt(sum(x * x for x in direction)) or 1.0
    for i, k in enumerate("XYZ"):
        L.inputs[k].default_value = direction[i] / n


def _builder(name):
    from .materials import new
    from .scenes_sky import G
    mat, nb, created = new(name)
    return mat, G(nb.tree), created


def finish(mat, b, col, ink=0.0, bare=0.0, nomist=0.0, form=None):
    """Emission output of colour socket/linear tuple ``col`` (x painter's light) + the AOVs."""
    form = RECIPE["form"] if form is None else form
    if form > 0:
        fg = b.node("ShaderNodeGroup")
        fg.node_tree = _form_group()
        k = b.maprange(fg.outputs["Light"], 0.0, 1.0, 1.0 - form, 1.0 + form * 0.25)
        col = b.cmul(col if not isinstance(col, tuple) else b.rgb(col + (1.0,)), k)
    em = b.node("ShaderNodeEmission")
    b.set(em.inputs["Color"], col)
    em.inputs["Strength"].default_value = 1.0
    b.output(em.outputs[0])
    for nm, v in (("gb_ink", ink), ("gb_bare", bare), ("gb_nomist", nomist)):
        if isinstance(v, (int, float)) and v == 0:
            continue
        _aov(b, nm, v)
    geo = b.node("ShaderNodeNewGeometry")
    _aov(b, "gb_pos", geo.outputs["Position"])
    mat["gb"] = 1
    return mat


def facing(b, blend=0.35, lo=0.0, hi=1.0, power=1.0):
    """0 facing the camera -> 1 at the silhouette (分染 deepening towards the outline)."""
    lw = b.node("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = blend
    f = lw.outputs["Facing"]
    if power != 1.0:
        f = b.math("POWER", f, power)
    return b.smooth(f, lo, hi)


def wpos(b):
    return b.node("ShaderNodeNewGeometry").outputs["Position"]


def wnoise(b, vec, scale, detail=3.0, rough=0.5, dist=0.0):
    n = b.node("ShaderNodeTexNoise", noise_dimensions="3D")
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = rough
    n.inputs["Distortion"].default_value = dist
    b.link(vec, n.inputs["Vector"])
    return n.outputs["Fac"]


def wash(name, light, deep=None, grad="facing", amount=1.0, blend=0.35, lo=0.05, hi=0.95,
         ink=0.0, bare=0.0, nomist=0.0, form=None, ao=0.0, ao_dist=1.0, zgrad=None):
    """Flat mineral wash ``light`` deepening to ``deep`` (default: light x 0.72).

    grad    'facing' (分染 towards the silhouette), 'none', or a callable (b) -> 0..1 socket
    zgrad   (z0, z1, k): extra gradient deepening *downwards* from z1 to z0 by ``k``
    ao      0..1 deepening in recesses (Cycles AO node, ``ao_dist`` metres)
    """
    mat, b, created = _builder(name)
    if not created:
        return mat
    lc = lin(light)
    dc = lin(deep) if deep is not None else tuple(x * 0.62 for x in lc)
    if callable(grad):
        g = grad(b)
    elif grad == "facing":
        g = facing(b, blend, lo, hi)
    else:
        g = 0.0
    if zgrad is not None:
        z0, z1, kz = zgrad
        zz = b.maprange(b.sep(wpos(b))[2], z0, z1, kz, 0.0)
        g = b.math("MAXIMUM", g, zz) if not isinstance(g, float) else zz
    if ao > 0:
        a = b.node("ShaderNodeAmbientOcclusion")
        a.samples = 8
        a.inputs["Distance"].default_value = ao_dist
        occ = b.math("MULTIPLY", b.math("SUBTRACT", 1.0, a.outputs["AO"]), ao)
        g = b.math("MAXIMUM", g, occ) if not isinstance(g, float) else occ
    if isinstance(g, float):
        col = b.rgb(tuple(x + (y - x) * g * amount for x, y in zip(lc, dc)) + (1.0,))
    else:
        if amount != 1.0:
            g = b.math("MULTIPLY", g, amount)
        col = b.mix(lc + (1.0,), dc + (1.0,), g)
    return finish(mat, b, col, ink=ink, bare=bare, nomist=nomist, form=form)


def flat(name, color, ink=0.0, bare=0.0, nomist=0.0, form=0.0):
    """Perfectly flat colour (no gradient, no light)."""
    return wash(name, color, color, grad="none", ink=ink, bare=bare, nomist=nomist, form=form)


# ---------------------------------------------------------------------------------------------
# texture-stroke helpers (all return 0..1 ink sockets)
# ---------------------------------------------------------------------------------------------
def stripes(b, coord, freq, width=0.12, warp=0.0, warp_scale=1.0):
    """Thin lines where sin(2 pi freq coord + warp) crosses 1: returns 0..1 ink."""
    c = coord
    if warp:
        c = b.math("ADD", c, b.math("MULTIPLY", b.math("SUBTRACT", warp_scale, 0.5), warp))
    s = b.math("SINE", b.math("MULTIPLY", c, 2 * math.pi * freq))
    return b.smooth(s, 1.0 - width * 2.0, 1.0 - width * 0.4)


def dots(b, vec, scale, size=0.18, randomness=1.0):
    """Ink dots on a Voronoi grid (点苔 / 点叶)."""
    v = b.node("ShaderNodeTexVoronoi", voronoi_dimensions="3D", feature="F1", distance="EUCLIDEAN")
    v.inputs["Scale"].default_value = scale
    v.inputs["Randomness"].default_value = randomness
    b.link(vec, v.inputs["Vector"])
    return b.smooth(v.outputs["Distance"], size, size * 0.6), v.outputs["Color"]


# =============================================================================================
# a standard material library (slot names used by the people / world kits)
# =============================================================================================
#: robe dyes for crowds (gongbi mineral & vegetable colours)
CLOTH = ["cinnabar", "azurite", "malachite", "#3A3530", "ochre", "#E2D6BC", "rouge", "teal",
         "#7A5A3A", "white", "vermilion", "indigo", "#5E6E4A", "gold"]
BANNERS = ["cinnabar", "gold", "#2E2A28", "azurite", "white", "malachite"]


def cloth(name, color, deep=None, form=None, ink=0.0, folds=0.75, fold_w=0.13):
    """Garment wash: 分染 towards the silhouette plus 衣纹 drapery lines and a deeper tone along
    each fold, read from the ``fold_*`` attributes the people kit writes on robes and sleeves
    (meshes without them get no lines)."""
    c = srgb(color)
    d = deep if deep is not None else tuple(x * 0.66 for x in c)
    mat, b, created = _builder(name)
    if not created:
        return mat
    lc, dc = lin(c), lin(d)
    g = facing(b, 0.42, 0.08, 1.0)
    col = b.mix(lc + (1.0,), dc + (1.0,), g)
    fx = b.attr("fold_x").outputs["Fac"]
    fy = b.attr("fold_y").outputs["Fac"]
    fn = b.attr("fold_n").outputs["Fac"]
    fp = b.attr("fold_p").outputs["Fac"]
    ft = b.attr("fold_t").outputs["Fac"]
    fw = b.attr("fold_w").outputs["Fac"]
    ang = b.math("ARCTAN2", fy, fx)
    sv = b.math("ABSOLUTE", b.math("SINE", b.math("ADD", b.math("MULTIPLY", ang, fn), fp)))
    line = b.smooth(sv, fold_w, fold_w * 0.35)
    # lines start below the waist / shoulder and thin out just above the hem
    gate = b.math("MULTIPLY", b.math("MULTIPLY", fw, b.smooth(ft, 0.1, 0.32)), b.smooth(ft, 1.02, 0.9))
    ink_l = b.math("MULTIPLY", b.math("MULTIPLY", line, gate), folds)
    # 分染 along the folds: the cloth deepens towards each fold line
    fold_shade = b.math("MULTIPLY", b.math("MULTIPLY", b.smooth(sv, 0.55, 0.05), gate), 0.45)
    col = b.mix(col, dc + (1.0,), fold_shade)
    if isinstance(ink, (int, float)) and ink == 0:
        ink_s = ink_l
    else:
        ink_s = b.math("MAXIMUM", ink_l, ink)
    return finish(mat, b, col, ink=ink_s, form=form)


def lamellar(name="GB_Armor", color="#5A5852", lace="cinnabar", scale=(0.05, 0.075)):
    """Armour: ink-grey wash with lamellae drawn as fine ink rows (gb_ink) and red lacing."""
    mat, b, created = _builder(name)
    if not created:
        return mat
    P = b.node("ShaderNodeNewGeometry").outputs["Position"]
    x, y, z = b.sep(P)
    rows = stripes(b, z, 1.0 / scale[1], width=0.10)
    cols = stripes(b, b.math("ADD", x, y), 1.0 / scale[0], width=0.07)
    ink = b.math("MULTIPLY", b.math("MAXIMUM", rows, b.math("MULTIPLY", cols, 0.6)), 0.55)
    g = facing(b, 0.4, 0.05, 1.0)
    base = b.mix(lin4(color), tuple(v * 0.6 for v in lin(color)) + (1.0,), g)
    lace_m = stripes(b, z, 1.0 / scale[1], width=0.22)
    col = b.mix(base, lin4(lace), b.math("MULTIPLY", lace_m, 0.45))
    return finish(mat, b, col, ink=ink)


def people_materials(cloth_colors=None, banner_colors=None, skin=None, armor="#6A665E",
                     horse=("#EDE4D2", "#9A5A34", "#3E3632", "#B89468", "#C8C2B4")):
    """Every slot :func:`ironart.scenes_people.figure` / ``horse`` / ``rider`` use, gongbi style."""
    cc = cloth_colors or CLOTH
    bc = banner_colors or BANNERS
    m = {}
    for i, c in enumerate(cc):
        m["Cloth%d" % i] = cloth("GB_Cloth%d_%s" % (i, str(c).strip("#")), c)
    for i, c in enumerate(bc):
        m["Banner%d" % i] = cloth("GB_Banner%d_%s" % (i, str(c).strip("#")), c,
                                  deep=tuple(x * 0.8 for x in srgb(c)))
    # flesh: lead white warmed with a touch of rouge, deepening to a rosy ochre at the outline
    sk = skin or "#F2E2CE"
    m["Skin"] = wash("GB_Skin_" + sk.strip("#"), sk, "#D8A88E", blend=0.3, lo=0.3, hi=1.0, form=0.03)
    m["Hair"] = flat("GB_Hair", "#2A2420", form=0.0)
    m["Armor"] = lamellar("GB_Armor", armor)
    m["ArmorDark"] = wash("GB_ArmorDark", "#4A4640", "#2E2A26")
    m["Metal"] = wash("GB_Metal", "#8A8A84", "#5A5A54")
    m["Blade"] = wash("GB_Blade", "#C8CCC8", "#8A908C", form=0.0)
    m["Bronze"] = wash("GB_Bronze", "#9A7A44", "#5E4A2A")
    m["Gold"] = wash("GB_Gold", PAL["gold"], PAL["gold_d"])
    m["Wood"] = wash("GB_Wood", "#9A7A58", "#7A5A40")
    m["Leather"] = wash("GB_Leather", "#6A4A32", "#3E2A1C")
    m["Straw"] = wash("GB_Straw", PAL["straw"], "#9A7A48")
    m["HatBlack"] = flat("GB_HatBlack", "#2A2622", form=0.0)
    m["Plume"] = cloth("GB_Plume", "cinnabar")
    m["Rope"] = wash("GB_Rope", "#9A8460", "#6A5840")
    m["Feather"] = wash("GB_Feather", "white", "#C8BEA8")
    m["ShieldFace"] = wash("GB_Shield", "cinnabar_d", "#5A1A14")
    m["Hoof"] = flat("GB_Hoof", "#3A322A")
    m["SleeveDark"] = wash("GB_SleeveDark", "#E8DCC4", "#C8B898")
    for i, c in enumerate(horse):
        # white / grey coats deepen to a cool ink grey, the others to a deeper same-hue
        d = mixc(c, "#8C8478", 0.55) if sum(srgb(c)) > 2.0 else tuple(x * 0.68 for x in srgb(c))
        m["HorseCoat%d" % i] = wash("GB_Horse%d_%s" % (i, c.strip("#")), c, d, blend=0.42, lo=0.1, hi=1.0)
    m["Saddle"] = wash("GB_Saddle", "cinnabar", "cinnabar_d", blend=0.4)
    m["HorseCoat"] = m["HorseCoat0"]
    m["HorseMane"] = flat("GB_Mane", "#2E2824")
    m["Flame"] = flame()
    m["LanternPaper"] = lantern()
    return m


def flame(name="GB_Flame"):
    """Painted flame: gold core to vermilion / cinnabar tongues (no glow)."""
    return wash(name, PAL["gold_l"], PAL["vermilion"], blend=0.5, lo=0.0, hi=0.85, form=0.0,
                nomist=0.6)


def lantern(name="GB_Lantern", color="vermilion"):
    return wash(name, mixc(color, "gold_l", 0.25), PAL["cinnabar"], blend=0.45, lo=0.1, hi=1.0,
                form=0.0, nomist=0.6)


def arch_materials(variant=None):
    """Gongbi versions of every ``W_*`` slot the world kit uses (界画 colouring)."""
    v = dict(variant or {})

    def c(k, d):
        return v.get(k, d)
    m = {}
    m["W_Lacquer"] = wash("GB_W_Lacquer", c("lacquer", "vermilion"), c("lacquer_d", "cinnabar"),
                          blend=0.45, lo=0.05, hi=1.0)
    m["W_LacquerDark"] = wash("GB_W_LacquerDark", "cinnabar", "cinnabar_d")
    m["W_RedWall"] = wash("GB_W_RedWall", c("wall", mixc("vermilion", "cinnabar", 0.6)),
                          "cinnabar_d", grad="none", ao=0.4, ao_dist=2.0)
    m["W_Gold"] = wash("GB_W_Gold", "gold", "gold_d")
    m["W_Wood"] = wash("GB_W_Wood", PAL["wood"], PAL["wood_d"])
    m["W_WoodDark"] = wash("GB_W_WoodDark", "#5A3E2C", "#3A2A1E", ao=0.3)
    m["W_Dark"] = flat("GB_W_Dark", "#3A322A")
    m["W_Bracket"] = wash("GB_W_Bracket", c("bracket", "malachite"), "malachite_d", ao=0.35,
                          ao_dist=1.0)
    m["W_BeamPaint"] = wash("GB_W_BeamPaint", c("beam", "azurite"), "azurite_d", ao=0.3)
    m["W_Fascia"] = wash("GB_W_Fascia", "malachite", "malachite_d")
    m["W_Trim"] = wash("GB_W_Trim", "gold", "gold_d")
    m["W_Lattice"] = lattice("GB_W_Lattice", c("lattice", "cinnabar_d"))
    m["W_GateDoor"] = wash("GB_W_GateDoor", "cinnabar", "cinnabar_d")
    m["W_Tile"] = tile("GB_W_Tile", c("tile", "tile"))
    m["W_TileDark"] = tile("GB_W_TileDark", "tile_d")
    m["W_TileGreen"] = tile("GB_W_TileGreen", "malachite")
    m["W_TileGold"] = tile("GB_W_TileGold", "gold")
    m["W_Ridge"] = wash("GB_W_Ridge", "tile_d", "#2A3236")
    m["W_RidgeGreen"] = wash("GB_W_RidgeGreen", "malachite_d", "#1E4A3A")
    m["W_RidgeGold"] = wash("GB_W_RidgeGold", "gold", "gold_d")
    m["W_Gable"] = wash("GB_W_Gable", "cinnabar", "cinnabar_d")
    m["W_Marble"] = wash("GB_W_Marble", c("marble", "white"), "#C8C0B0", ao=0.3, ao_dist=1.0)
    m["W_Paving"] = wash("GB_W_Paving", c("paving", "#D6CCB8"), "#B8AE9A", grad="none")
    m["W_Stone"] = masonry("GB_W_Stone", c("stone", "stone"), "stone_d")
    m["W_StoneDark"] = masonry("GB_W_StoneDark", c("stone_dark", "#9C9384"), "#6E665A")
    m["W_Brick"] = masonry("GB_W_Brick", c("brick", "#A89C88"), "#7E7462", course=0.3, block=0.6, ink=0.22, far=120.0)
    m["W_BrickWarm"] = wash("GB_W_BrickWarm", "#B49A7A", "#86705A")
    m["W_Plaster"] = wash("GB_W_Plaster", c("plaster", "plaster"), "#C8B898", ao=0.3)
    m["W_PlasterWarm"] = wash("GB_W_PlasterWarm", "#E6D2B0", "#C8AE88")
    m["W_Iron"] = wash("GB_W_Iron", "#5A5650", "#3A3632")
    m["W_Tassel"] = cloth("GB_W_Tassel", "cinnabar")
    m["W_Rock"] = wash("GB_W_Rock", "stone", "stone_d")
    m["W_Earth"] = wash("GB_W_Earth", "earth", "#8A7050")
    m["W_Bronze"] = wash("GB_W_Bronze", "#9A7A44", "#5E4A2A")
    m["Water"] = wash("GB_W_Water", "azurite_l", "#6A90B0", grad="none", bare=0.45, form=0.0)
    m["Tint"] = wash("GB_W_Tint", "cinnabar", "cinnabar_d")
    m["Ground"] = wash("GB_W_Ground", "#D8CCAE", "#C0B090", grad="none", form=0.0)
    m["Thatch"] = thatch("GB_W_Thatch", c("thatch", "#B89A62"), c("thatch_d", "#7E6238"))
    return m


def masonry(name, color, deep, course=0.55, block=1.1, ink=0.32, near=20.0, far=220.0, ao=0.3):
    """Stone / brick wall: the wash with fine ruled courses (horizontal every ``course`` m,
    staggered joints every ``block`` m) in ink, fading with distance."""
    mat, b, created = _builder(name)
    if not created:
        return mat
    x, y, z = b.sep(wpos(b))
    nz = b.math("ABSOLUTE", b.sep(b.node("ShaderNodeNewGeometry").outputs["Normal"])[2])
    side = b.smooth(nz, 0.6, 0.3)
    row = b.math("FLOOR", b.math("DIVIDE", z, course))
    h = stripes(b, b.math("DIVIDE", z, course), 1.0, width=0.06)
    u = b.math("ADD", b.math("ADD", x, y), b.math("MULTIPLY", b.math("FRACT", b.math("MULTIPLY", row, 0.5)), block))
    v = stripes(b, b.math("DIVIDE", u, block), 1.0, width=0.03)
    lines = b.math("MULTIPLY", b.math("MAXIMUM", h, b.math("MULTIPLY", v, 0.8)), side)
    dist = b.node("ShaderNodeCameraData").outputs["View Distance"]
    lines = b.math("MULTIPLY", b.math("MULTIPLY", lines, ink), b.smooth(dist, far, near))
    g = facing(b, 0.35, 0.05, 0.95)
    a = b.node("ShaderNodeAmbientOcclusion")
    a.samples = 6
    a.inputs["Distance"].default_value = 2.0
    g = b.math("MAXIMUM", g, b.math("MULTIPLY", b.math("SUBTRACT", 1.0, a.outputs["AO"]), ao))
    n = wnoise(b, wpos(b), 0.15, 3.0, 0.55)
    base = b.mix(lin4(color), lin4(mixc(color, deep, 0.35)), b.smooth(n, 0.4, 0.7))
    col = b.mix(base, lin4(deep), g)
    return finish(mat, b, col, ink=lines)


def tile(name, color):
    """Roof tiles: tile-grey wash, darker towards the eaves (UV v = metres up the slope)."""
    mat, b, created = _builder(name)
    if not created:
        return mat
    c = srgb(color)
    d = tuple(x * 0.62 for x in c)
    uv = b.node("ShaderNodeUVMap")
    uv.uv_map = "MetreUV"
    v = b.sep(uv.outputs["UV"])[1]
    g = b.math("MAXIMUM", b.maprange(v, 0.0, 2.5, 0.7, 0.0), facing(b, 0.3, 0.2, 1.0))
    col = b.mix(lin4(c), lin4(d), g)
    return finish(mat, b, col)


def thatch(name, color="#B89A62", deep="#7E6238"):
    """Thatched roof: straw wash deepening to the eaves, fine ink strokes down the slope (UV u =
    metres along the eave), broken by noise."""
    mat, b, created = _builder(name)
    if not created:
        return mat
    uv = b.node("ShaderNodeUVMap")
    uv.uv_map = "MetreUV"
    u, v, _ = b.sep(uv.outputs["UV"])
    n = wnoise(b, wpos(b), 1.5, 2.0, 0.5)
    lines = stripes(b, b.math("ADD", b.math("DIVIDE", u, 0.22), b.math("MULTIPLY", n, 1.5)), 1.0, width=0.1)
    brk = b.smooth(wnoise(b, wpos(b), 0.6, 2.0, 0.5), 0.4, 0.6)
    ink = b.math("MULTIPLY", b.math("MULTIPLY", lines, brk), 0.4)
    dist = b.node("ShaderNodeCameraData").outputs["View Distance"]
    ink = b.math("MULTIPLY", ink, b.smooth(dist, 160.0, 20.0))
    g = b.math("MAXIMUM", b.maprange(v, 0.0, 2.0, 0.6, 0.0), facing(b, 0.3, 0.2, 1.0))
    col = b.mix(lin4(color), lin4(deep), g)
    return finish(mat, b, col, ink=ink)


def lattice(name, color):
    """Door / window lattice (格扇): a wash with a fine square lattice drawn in ink."""
    mat, b, created = _builder(name)
    if not created:
        return mat
    P = wpos(b)
    x, y, z = b.sep(P)
    k = 1.0 / 0.32
    h = stripes(b, z, k, width=0.1)
    w = stripes(b, b.math("ADD", x, y), k, width=0.1)
    ink = b.math("MULTIPLY", b.math("MAXIMUM", h, w), 0.6)
    c = srgb(color)
    col = b.mix(lin4(c), lin4(mixc(c, "gold", 0.35)), b.math("SUBTRACT", 1.0, b.math("MAXIMUM", h, w)))
    return finish(mat, b, col, ink=ink)


# =============================================================================================
# scene setup: render settings, collections, Freestyle ink, passes
# =============================================================================================
def setup(w, h, ss=None, spp=None, preview=False, seed=0):
    """Cycles CPU, Standard view, film transparent (alpha = painted coverage), emission only."""
    import bpy
    from . import scene
    ss = RECIPE["ss"] if ss is None else ss
    samples = spp or (RECIPE["preview_spp"] if preview else RECIPE["spp"])
    sc = scene.setup_cycles(samples=samples, transparent=True, preset="sprite", view="Standard",
                            look="None", adaptive_threshold=RECIPE["adaptive_threshold"], seed=seed,
                            filter_width=RECIPE["filter_width"], clamp_indirect=1.0)
    cy = sc.cycles
    cy.max_bounces = 1
    cy.diffuse_bounces = 0
    cy.glossy_bounces = 0
    cy.transmission_bounces = 0
    cy.volume_bounces = 0
    cy.transparent_max_bounces = 4
    cy.use_light_tree = False
    scene.set_resolution(w, h, ss)
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.image_settings.color_depth = "16"
    sc.render.dither_intensity = 0.0
    vl = sc.view_layers[0]
    vl.use_pass_z = True
    # image-space ink (scenes_gongbi_ink) reads these sample-0 passes
    vl.use_pass_object_index = True
    vl.use_pass_material_index = True
    vl.use_pass_normal = True
    for nm, t in AOVS:
        if nm not in [a.name for a in vl.aovs]:
            a = vl.aovs.add()
            a.name = nm
            a.type = t
    # world: nothing (background = bare silk, alpha 0)
    wd = bpy.data.worlds.new("GB_World")
    wd.use_nodes = True
    bg = wd.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0, 0, 0, 1)
    bg.inputs["Strength"].default_value = 0.0
    sc.world = wd
    set_light(RECIPE["light_dir"])
    return dict(size=(w, h), ss=ss, samples=samples, preview=preview, seed=seed)


def collections():
    """One collection per ink kind (+ 'none'): objects are linked into these by the builders."""
    import bpy
    sc = bpy.context.scene
    out = {}
    from .scenes_gongbi_ink import CODES
    kinds = [k for k in INK if "col" not in INK[k]] + ["none"]
    kinds += [k for k in CODES if k not in kinds]
    for k in kinds:
        nm = "GB_" + k
        c = bpy.data.collections.get(nm)
        if c is None:
            c = bpy.data.collections.new(nm)
            sc.collection.children.link(c)
        out[k] = c
    return out


def col(kind):
    return collections()[kind]


def _linestyle(name, spec, k, scale, seed):
    import bpy
    st = bpy.data.linestyles.new(name)
    st.color = lin(spec.get("color", "ink"))
    st.alpha = spec["a"]
    ss = k
    t = spec["t"] * k * scale
    st.thickness = t * (1.0 - spec["noise"] * 0.5)
    st.thickness_position = "CENTER"
    st.use_chaining = True
    st.chaining = "PLAIN"
    st.use_same_object = True
    st.caps = "ROUND"
    if spec.get("lmin"):
        st.use_length_min = True
        st.length_min = spec["lmin"] * ss * scale
    if spec.get("smooth"):
        g = st.geometry_modifiers.new("Smooth", "BEZIER_CURVE")
        g.error = 1.2 * ss * scale
    if spec.get("wobble", 0) > 0:
        g = st.geometry_modifiers.new("Wobble", "PERLIN_NOISE_1D")
        g.frequency = 8.0
        g.amplitude = spec["wobble"] * ss * scale
        g.octaves = 2
        g.seed = seed % 512
    tp = spec.get("taper", 0.0)
    if tp > 0:
        m = st.thickness_modifiers.new("Taper", "ALONG_STROKE")
        m.blend = "MULTIPLY"
        m.mapping = "CURVE"
        cm = m.curve
        pts = cm.curves[0].points
        lo = max(0.05, 1.0 - tp * 2.2)
        pts[0].location = (0.0, lo)
        pts[1].location = (1.0, lo * 0.8)
        pts.new(min(0.45, tp * 0.6), 1.0)
        pts.new(max(0.55, 1.0 - tp * 0.75), 0.92)
        cm.update()
    if spec.get("calli", 0) > 0:
        m = st.thickness_modifiers.new("Brush", "CALLIGRAPHY")
        m.blend = "MULTIPLY"
        m.orientation = math.radians(50.0)
        m.thickness_min = 1.0 - spec["calli"] * 0.6
        m.thickness_max = 1.0 + spec["calli"] * 0.3
    if spec.get("noise", 0) > 0:
        m = st.thickness_modifiers.new("Pressure", "NOISE")
        m.blend = "ADD"
        m.amplitude = spec["noise"] * t
        m.period = 22.0 * ss * scale
        m.seed = (seed + 7) % 512
    near, far, tfar, afar = spec["dist"]
    m = st.thickness_modifiers.new("Far", "DISTANCE_FROM_CAMERA")
    m.blend = "MULTIPLY"
    m.range_min, m.range_max = near, far
    m.value_min, m.value_max = 1.0, tfar
    m.mapping = "LINEAR"
    a = st.alpha_modifiers.new("FarA", "DISTANCE_FROM_CAMERA")
    a.blend = "MULTIPLY"
    a.range_min, a.range_max = near, far
    a.mapping = "CURVE"
    cm = a.curve
    pts = cm.curves[0].points
    pts[0].location = (0.0, 1.0)
    pts[1].location = (1.0, afar)
    cm.update()
    return st


def setup_ink(k=4, scale=1.0, overrides=None, crease_deg=140.0):
    """Freestyle as a render pass with one line set per ink collection (see :data:`INK`).

    ``k`` = render px per game (1x) px (events: master 2x, rendered at 2x the master -> 4);
    ``scale`` multiplies every thickness; ``overrides`` = {kind: {key: value}}."""
    import bpy
    from . import ink as _ink
    _ink._patch_freestyle()
    sc = bpy.context.scene
    seed = int(sc.get("ironart_seed", 0))
    sc.render.use_freestyle = True
    sc.render.line_thickness_mode = "ABSOLUTE"
    sc.render.line_thickness = 1.0
    vl = sc.view_layers[0]
    vl.use_freestyle = True
    fs = vl.freestyle_settings
    fs.mode = "EDITOR"
    fs.as_render_pass = True
    fs.crease_angle = math.radians(crease_deg)
    fs.use_culling = True
    fs.use_smoothness = True
    while len(fs.linesets) > 0:
        fs.linesets.remove(fs.linesets[0])
    cols = collections()
    out = {}
    for kind, spec in INK.items():
        spec = dict(spec, **((overrides or {}).get(kind, {})))
        if spec.get("off"):
            continue
        st = _linestyle("GB_Ink_" + kind, spec, k, scale, seed + len(out) * 11)
        ls = fs.linesets.new("GB_" + kind)
        ls.linestyle = st
        ls.select_by_visibility = True
        ls.visibility = "VISIBLE"
        ls.select_by_edge_types = True
        e = spec["edges"]
        ls.select_silhouette = "silhouette" in e
        ls.select_border = "border" in e
        ls.select_crease = "crease" in e
        ls.select_contour = "contour" in e
        ls.select_external_contour = "external_contour" in e
        ls.select_material_boundary = "material_boundary" in e
        ls.select_suggestive_contour = "suggestive" in e
        ls.select_ridge_valley = "ridge" in e
        ls.select_by_collection = True
        ls.collection = cols[spec.get("col", kind)]
        ls.collection_negation = "INCLUSIVE"
        out[kind] = ls
    return out


def passes(out_dir):
    """Compositor: write colour / Freestyle / depth / AOV passes as float EXRs into ``out_dir``."""
    import bpy
    sc = bpy.context.scene
    sc.use_nodes = True
    sc.render.use_compositing = True
    nt = sc.node_tree
    nt.nodes.clear()
    rl = nt.nodes.new("CompositorNodeRLayers")
    comp = nt.nodes.new("CompositorNodeComposite")
    comp.use_alpha = True
    nt.links.new(rl.outputs["Image"], comp.inputs["Image"])
    fo = nt.nodes.new("CompositorNodeOutputFile")
    fo.base_path = out_dir
    fo.format.file_format = "OPEN_EXR"
    fo.format.color_depth = "32"
    fo.format.exr_codec = "ZIP"
    fo.format.color_mode = "RGBA"
    fo.file_slots.clear()
    names = [("color", "Image"), ("depth", "Depth"), ("index_ob", "IndexOB"),
             ("index_ma", "IndexMA"), ("normal", "Normal")]
    if sc.render.use_freestyle:
        names.append(("line", "Freestyle"))
    names += [(n, n) for n, _ in AOVS]
    for fname, sock in names:
        if sock not in rl.outputs:
            continue
        fo.file_slots.new(fname)
        nt.links.new(rl.outputs[sock], fo.inputs[fname])
    return [n for n, s in names if s in rl.outputs]


def render(out_dir):
    """Render the passes into ``out_dir`` (EXR) and return {pass: array}."""
    import time
    import bpy
    from . import scene
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.endswith(".exr"):
            os.remove(os.path.join(out_dir, f))
    from . import scenes_gongbi_ink as GI
    GI.tag_objects()
    names = passes(out_dir)
    sc = bpy.context.scene
    sc.render.filepath = os.path.join(out_dir, "beauty.png")
    scene.check_render_settings()
    t0 = time.time()
    bpy.ops.render.render(write_still=False)
    secs = time.time() - t0
    return load_passes(out_dir, names), secs


def load_passes(out_dir, names=None):
    from .scenes_look import load_exr
    out = {}
    for f in sorted(os.listdir(out_dir)):
        if not f.endswith(".exr"):
            continue
        key = f[:-8] if f[-8:-4].isdigit() else f[:-4]
        if names and key not in names:
            continue
        out[key] = load_exr(os.path.join(out_dir, f))
    return out


# =============================================================================================
# numpy helpers
# =============================================================================================
def box_blur(a, r):
    """Edge-clamped box blur of radius ``r`` (float ok) along both axes (O(N))."""
    r = int(round(r))
    if r <= 0:
        return a
    out = a
    for ax in (0, 1):
        pad = [(0, 0)] * out.ndim
        pad[ax] = (r + 1, r)
        p = np.pad(out, pad, mode="edge")
        c = np.cumsum(p, axis=ax, dtype=np.float64)
        n = out.shape[ax]
        hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=ax)
        lo = np.take(c, np.arange(0, n), axis=ax)
        out = ((hi - lo) / (2 * r + 1)).astype(np.float32)
    return out


def blur(a, sigma):
    """Gaussian-like blur (3 box passes) with sigma in px."""
    if sigma <= 0.3:
        return a
    r = max(1, int(round(sigma * 0.85)))
    out = a
    for _ in range(3):
        out = box_blur(out, r)
    return out


def value_noise(h, w, cell, seed, octaves=1, gain=0.5, aniso=(1.0, 1.0)):
    """Smooth value noise in [0, 1] (bicubic-interpolated lattice), ``cell`` px, optional
    anisotropy (cell multipliers along y, x)."""
    from PIL import Image
    rng = np.random.default_rng(seed)
    acc = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        cy = max(1.0, cell * aniso[0] / (2 ** o))
        cx = max(1.0, cell * aniso[1] / (2 ** o))
        gh, gw = int(h / cy) + 3, int(w / cx) + 3
        g = rng.random((gh, gw), np.float32)
        im = Image.fromarray(g, "F").resize((int(gw * cx), int(gh * cy)), Image.BICUBIC)
        a = np.asarray(im, np.float32)
        oy, ox = rng.integers(0, max(1, int(cy))), rng.integers(0, max(1, int(cx)))
        acc += amp * a[oy:oy + h, ox:ox + w]
        tot += amp
        amp *= gain
    return np.clip(acc / tot, 0.0, 1.0)


def lanczos(img, size):
    """Lanczos resize of a float H x W x C (or H x W) array to ``size`` (w, h)."""
    from PIL import Image
    if img.ndim == 2:
        return np.asarray(Image.fromarray(np.ascontiguousarray(img, np.float32), "F")
                          .resize(size, Image.LANCZOS), np.float32)
    return np.dstack([lanczos(img[..., c], size) for c in range(img.shape[2])])


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# =============================================================================================
# silk
# =============================================================================================
def silk(h, w, seed=0, m=2.0, **over):
    """Aged silk ground at master resolution: returns (colour H x W x 3 sRGB, texture H x W ~1).

    colour  = warm #E6D6B0 centre to #D8C39A edges, faint mottling and old stains
    texture = multiplicative fibre structure (warp / weft threads, slubs) with mean 1
    """
    s = dict(RECIPE["silk"], **over)
    rng = np.random.default_rng(seed + 101)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    # ---- threads: weft (horizontal) dominant, warp finer; thread pitch in game px x m ---------
    p = s["pitch"] * m
    row_id = np.floor(yy / p).astype(np.int64)
    col_id = np.floor(xx / (p * 0.8)).astype(np.int64)
    rv = rng.random(row_id.max() + 2).astype(np.float32)
    cv = rng.random(col_id.max() + 2).astype(np.float32)
    weft = (rv[row_id] - 0.5)
    warp = (cv[col_id] - 0.5)
    # thread-level thickness wobble along the thread
    wob = value_noise(h, w, 12 * m, seed + 3, 1, aniso=(0.12, 1.0)) - 0.5
    weave = np.sin(yy / p * math.pi) ** 2 * 0.5 + np.sin(xx / (p * 0.8) * math.pi) ** 2 * 0.5
    fib = 0.55 * weft + 0.30 * warp + 0.35 * wob + 0.25 * (weave - 0.5)
    # slubs: occasional thicker weft threads
    slub_rows = (rng.random(row_id.max() + 2) < 0.035).astype(np.float32)
    slub = slub_rows[row_id] * (value_noise(h, w, 20 * m, seed + 5, 1, aniso=(0.1, 1.0)) - 0.35)
    tex = 1.0 + s["fibre"] * fib + s["slub"] * slub
    # ---- ground colour: centre -> edges, mottling, stains -----------------------------------
    c0 = np.array(srgb(PAL["silk"]), np.float32)
    c1 = np.array(srgb(PAL["silk_edge"]), np.float32)
    nx, ny = (xx / w - 0.5) * 2, (yy / h - 0.5) * 2
    e = np.sqrt((nx * 0.92) ** 2 + (ny * 1.0) ** 2)
    edge = smoothstep(0.45, 1.45, e)
    big = max(h, w) / 1280.0
    mott = value_noise(h, w, 160 * big, seed + 7, 4, 0.55) - 0.5
    stain = value_noise(h, w, 420 * big, seed + 9, 3, 0.5)
    stain = smoothstep(0.62, 0.9, stain)
    t = np.clip(edge * 0.85 + mott * 0.9 * s["mottle"] / 0.045 * 0.35 + stain * 0.4, 0, 1)
    col = c0[None, None, :] * (1 - t[..., None]) + c1[None, None, :] * t[..., None]
    # darker rim (old mounting) and overall edge fall-off
    rim = smoothstep(1.0 - s["edge_px"] * 0.5, 1.0, np.maximum(np.abs(nx), np.abs(ny)))
    col *= (1.0 - s["edge"] * (edge * 0.6 + rim * 0.4))[..., None]
    col *= (1.0 - s["stain"] * stain)[..., None]
    return col.astype(np.float32), tex.astype(np.float32)


# =============================================================================================
# composite
# =============================================================================================
def sky_layer(h, w, sky):
    """Screen-space sky wash: ``sky`` = dict(stops=[(y 0 top..1 bottom, colour, alpha), ...])."""
    yy = np.linspace(0.0, 1.0, h, dtype=np.float32)
    stops = sky.get("stops", [])
    if not stops:
        return np.zeros((h, w, 3), np.float32), np.zeros((h, w), np.float32)
    ys = np.array([s[0] for s in stops], np.float32)
    cs = np.array([srgb(s[1]) for s in stops], np.float32)
    al = np.array([s[2] for s in stops], np.float32)
    col = np.stack([np.interp(yy, ys, cs[:, k]) for k in range(3)], -1)
    a = np.interp(yy, ys, al)
    col = np.repeat(col[:, None, :], w, axis=1)
    a = np.repeat(a[:, None], w, axis=1)
    if sky.get("x_tilt"):
        # horizontal variation: colour/alpha multiplier from left to right
        k0, k1 = sky["x_tilt"]
        a = a * np.linspace(k0, k1, w, dtype=np.float32)[None, :]
    return col.astype(np.float32), a.astype(np.float32)


def mist_field(P, A, Z, h, w, bands, seed, k):
    """Mist of bare silk -> 0..1 (H x W).  Bands are continuous with wavy, broken edges (the
    band limits are displaced by horizontally stretched noise), like painted mist bands.

    World band: dict(z=(z0, z1), soft, jitter (m), dist=(d0, d1) fade-in by horizontal distance
    from the origin of ``dist_from``, y_range=(y0, y1) screen limits, amount, noise_px, aniso,
    holes=0..1 (breaks inside the band)).  Screen band: dict(y=(y0, y1), soft, x=(x0, x1))."""
    m = np.zeros((h, w), np.float32)
    outline = np.zeros((h, w), np.float32)
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    xx = np.linspace(0, 1, w, dtype=np.float32)[None, :]
    for i, b in enumerate(bands):
        amt = b.get("amount", 1.0)
        an = b.get("aniso", (0.18, 1.0))
        npx = b.get("noise_px", 90) * k
        n1 = value_noise(h, w, npx, seed + 31 * i, 4, 0.55, aniso=an) - 0.5
        n2 = value_noise(h, w, npx, seed + 31 * i + 7, 4, 0.55, aniso=an) - 0.5
        hole = value_noise(h, w, npx * 0.8, seed + 31 * i + 13, 3, 0.5, aniso=an)
        if "z" in b:
            z0, z1 = b["z"]
            soft = b.get("soft", (z1 - z0) * 0.3)
            jit = b.get("jitter", (z1 - z0) * 0.6)
            z = P[..., 2]
            lo = z0 + n1 * jit * 2
            hi = z1 + n2 * jit * 2
            f = smoothstep(lo - soft, lo, z) * (1 - smoothstep(hi, hi + soft, z))
            if "dist" in b:
                d0, d1 = b["dist"]
                ox, oy = b.get("dist_from", (0.0, 0.0))
                dd = np.sqrt((P[..., 0] - ox) ** 2 + (P[..., 1] - oy) ** 2)
                f = f * smoothstep(d0, d1, dd)
            if "y_range" in b:
                y0, y1 = b["y_range"]
                f = f * (smoothstep(y0 - 0.05, y0 + 0.05, yy) * (1 - smoothstep(y1 - 0.05, y1 + 0.05, yy)))
            f = f * (A > 0.001)
        elif b.get("scallop"):
            # 祥云 band: the top edge is a row of round cloud heads (arcs), outlined in ink
            y0, y1 = b["y"]
            rng = np.random.default_rng(seed + 97 * i)
            rpx = b["scallop"] * k                       # head radius in render px
            x0b, x1b = b.get("x", (-0.1, 1.1))
            edge = np.full(w, np.inf, np.float32)
            xs = np.arange(w, dtype=np.float32)
            cx = x0b * w
            while cx < x1b * w:
                rr = rpx * rng.uniform(0.6, 1.3)
                lift = rng.uniform(-0.6, 0.4) * rpx
                inside = np.abs(xs - cx) < rr
                arc = y0 * h + lift - np.sqrt(np.clip(rr * rr - (xs - cx) ** 2, 0, None))
                edge = np.where(inside, np.minimum(edge, arc), edge)
                cx += rr * rng.uniform(1.1, 1.6)
            edge = np.where(np.isinf(edge), y0 * h, edge)
            pix = np.arange(h, dtype=np.float32)[:, None]
            sharp = max(1.0, 0.6 * k)
            top = smoothstep(edge[None, :] - sharp, edge[None, :] + sharp, pix)
            bottom = 1 - smoothstep(y1 * h - b.get("soft", 0.05) * h, y1 * h + b.get("soft", 0.05) * h, pix)
            f = top * bottom
            if "x" in b:
                x0, x1 = b["x"]
                sx = b.get("soft_x", 0.04)
                f = f * smoothstep(x0 - sx, x0 + sx, xx) * (1 - smoothstep(x1 - sx, x1 + sx, xx))
            if "dist_min" in b:
                dm = b["dist_min"]
                f = f * np.maximum(smoothstep(dm * 0.92, dm * 1.08, Z), 1.0 - (A > 0.01))
            lw = b.get("line_px", 0.9) * k * 0.5
            ln = 1 - smoothstep(lw * 0.5, lw * 1.5, np.abs(pix - edge[None, :]))
            ln = ln * (bottom > 0.5) * b.get("line", 0.5)
            if "x" in b:
                ln = ln * smoothstep(x0 - sx, x0 + sx, xx) * (1 - smoothstep(x1 - sx, x1 + sx, xx))
            outline = np.maximum(outline, ln * b.get("amount", 1.0))
            m = np.maximum(m, np.clip(f * b.get("amount", 1.0), 0, 1))
            continue
        else:
            y0, y1 = b["y"]
            soft = b.get("soft", 0.04)
            jy = b.get("jitter", 0.03)
            f = smoothstep(y0 + n1 * jy * 2 - soft, y0 + n1 * jy * 2 + soft, yy) * \
                (1 - smoothstep(y1 + n2 * jy * 2 - soft, y1 + n2 * jy * 2 + soft, yy))
            if "x" in b:
                x0, x1 = b["x"]
                sx = b.get("soft_x", 0.08)
                f = f * smoothstep(x0 - sx, x0 + sx, xx) * (1 - smoothstep(x1 - sx, x1 + sx, xx))
            f = np.broadcast_to(f, (h, w))
            if "dist_min" in b:
                dm = b["dist_min"]
                f = f * smoothstep(dm * 0.92, dm * 1.08, Z)
        hk = b.get("holes", 0.25)
        f = f * (1 - hk * smoothstep(0.55, 0.75, hole))
        m = np.maximum(m, np.clip(f * amt, 0, 1))
    return m, outline


def _shift(a, dy, dx):
    h, w = a.shape
    out = np.zeros_like(a)
    ys0, ys1 = max(0, dy), min(h, h + dy)
    xs0, xs1 = max(0, dx), min(w, w + dx)
    out[ys0:ys1, xs0:xs1] = a[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
    return out


def dilate(mask, r):
    """Binary dilation with a disc of radius ``r`` px."""
    r = int(math.ceil(r))
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r and (dx or dy):
                out |= _shift(mask, dy, dx)
    return out


def shore_line(P, A, spec, k, seed=0):
    """Ink line along the water's edge: land pixels touching water-plane pixels (screen space).

    spec = dict(z=water level, width=game px, alpha, eps=metres)."""
    z0 = spec.get("z", 0.0)
    eps = spec.get("eps", 0.02)
    solid = A > 0.5
    water = solid & (np.abs(P[..., 2] - z0) < eps)
    land = solid & (P[..., 2] > z0 + eps * 2)
    r = max(1.0, spec.get("width", 1.0) * k * 0.5)
    line = (land & dilate(water, r)).astype(np.float32)
    line = blur(line, 0.3 * k)
    line = np.clip(line * 1.6, 0, 1)
    n = value_noise(*line.shape, 14 * k, seed + 77, 2, 0.5)
    return line * spec.get("alpha", 0.8) * (0.55 + 0.45 * smoothstep(0.3, 0.7, n))


def composite(ps, look, seed=0, overlays=None, master_size=None, k=4, m=2):
    """Turn the passes into the painting.  Returns dict(master=H x W x 3 sRGB float, ...).

    look keys (all optional):
      sky      dict(stops=[(y, colour, alpha)], x_tilt=(k0, k1))   wash on the bare silk
      fade     dict(d0, d1, color, amount, cover)    distance -> paler wash (cover: coverage loss)
      mist     [band dicts] (see :func:`mist_field`)
      ink      ink strength multiplier, shader_ink multiplier
      silk     overrides of RECIPE['silk']; tone: final multiply (sRGB triple)
    overlays  :class:`ironart.scenes_gongbi_2d.Canvas` (sky and front layers)
    k, m      render px and master px per game (1x) px
    """
    C = ps["color"]
    H, W = C.shape[:2]
    A = np.clip(C[..., 3], 0.0, 1.0)
    inv = np.where(A > 1e-4, 1.0 / np.maximum(A, 1e-4), 0.0)[..., None]
    col = to_srgb(np.clip(C[..., :3] * inv, 0, None))
    col = np.clip(col, 0, 1)
    P = ps["gb_pos"][..., :3] * inv if "gb_pos" in ps else np.zeros((H, W, 3), np.float32)
    Z = ps["depth"][..., 0] if "depth" in ps else np.zeros((H, W), np.float32)
    Z = np.where(A > 1e-3, Z, 1e6)
    bare = np.clip(ps["gb_bare"][..., 0] * inv[..., 0], 0, 1) if "gb_bare" in ps else 0.0
    nomist = np.clip(ps["gb_nomist"][..., 0] * inv[..., 0], 0, 1) if "gb_nomist" in ps else 0.0
    sink = np.clip(ps["gb_ink"][..., 0], 0, 1) if "gb_ink" in ps else np.zeros((H, W), np.float32)
    silk_ref = np.array(srgb(SILK_REF), np.float32)
    # ---- image-space ink (no Freestyle pass): lines + the 分染 band along them ------------------
    edge_ink = None
    if "line" not in ps and "index_ob" in ps:
        from . import scenes_gongbi_ink as GI
        tab = GI.kind_table(look.get("kinds"))
        la_e, lc_e, E, code = GI.ink(ps, tab, k, seed)
        edge_ink = (la_e, lc_e)
        rk = look.get("rim", RECIPE["rim"])
        if rk > 0:
            band = GI.rim(E, code, tab, A, k, look.get("rim_px", RECIPE["rim_px"]))
            col = deepen(col, band * rk)
    # ---- distance: paler, thinner washes ------------------------------------------------------
    fd = look.get("fade")
    fade = np.zeros((H, W), np.float32)
    if fd:
        fade = smoothstep(fd["d0"], fd["d1"], Z) ** fd.get("gamma", 1.0) * fd.get("amount", 0.8)
        fade = fade * (A > 1e-3)
        fc = np.array(srgb(fd.get("color", SILK_REF)), np.float32)
        col = col * (1 - fade[..., None]) + fc * fade[..., None]
    cover = A * (1.0 - bare) * (1.0 - fade * (fd or {}).get("cover", 0.0))
    # ---- mist ---------------------------------------------------------------------------------
    mist = np.zeros((H, W), np.float32)
    mist_line = np.zeros((H, W), np.float32)
    if look.get("mist"):
        mist, mist_line = mist_field(P, A, Z, H, W, look["mist"], seed, k)
        mist = mist * (1 - nomist)
    cover = cover * (1.0 - mist)
    # ---- sky wash under everything, 2D sky overlays -------------------------------------------
    skc, ska = sky_layer(H, W, look.get("sky", {}))
    if overlays is not None:
        skc, ska = overlays.under(skc, ska)
    # mist in front of the sky clears the sky wash too (clouds are bare silk)
    ska = ska * (1.0 - mist * look.get("mist_sky", 1.0) * (A < 0.999))
    # ---- layer: silk_ref <- sky <- objects ----------------------------------------------------
    paint = skc * (ska * (1 - cover))[..., None] + col * cover[..., None]
    pa = cover + ska * (1 - cover)
    img = silk_ref[None, None, :] * (1 - pa[..., None]) + paint
    # mist itself can carry a faint wash (cool / warm) so it is not paper-white everywhere
    if look.get("mist_tint"):
        mt, ma = look["mist_tint"]
        img = img * (1 - (mist * ma)[..., None]) + np.array(srgb(mt), np.float32) * (mist * ma)[..., None]
    # ---- ink ------------------------------------------------------------------------------------
    ink_k = look.get("ink", 1.0) * RECIPE["ink_strength"]
    la = np.zeros((H, W), np.float32)
    lc = np.zeros((H, W, 3), np.float32) + np.array(srgb(PAL["ink"]), np.float32)
    if "line" in ps:
        L = ps["line"]
        la = np.clip(L[..., 3], 0, 1)
        lcol = to_srgb(np.clip(L[..., :3] / np.maximum(la, 1e-4)[..., None], 0, None))
        lc = np.where(la[..., None] > 1e-4, lcol, lc)
    elif edge_ink is not None:
        la, lc = edge_ink
        # distant lines fade with the washes
        la = la * (1.0 - fade * look.get("fade_ink", 0.6))
    if look.get("shore"):
        la = np.maximum(la, shore_line(P, A, look["shore"], k, seed) * (1 - fade * 0.8))
    shader_k = look.get("shader_ink", 1.0) * RECIPE["shader_ink"]
    sink = sink * shader_k * (1 - fade * look.get("shader_fade", 0.9))
    sa = sink * (1 - mist)
    la = la * (1 - mist * look.get("mist_ink", 1.0))
    la = np.maximum(la, mist_line * (1 - nomist))
    # bleed: a soft halo of thinned ink around every line
    bl = blur(la, 0.45 * k) * RECIPE["ink_bleed"]
    la2 = np.clip(np.maximum(la, bl * 0.6), 0, 1)
    # dry brush: break the ink with fibre noise
    dry = value_noise(H, W, 0.8 * k, seed + 41, 2, 0.6)
    la2 = la2 * (1 - RECIPE["ink_dry"] * smoothstep(0.55, 0.95, dry))
    shader_col = np.array(srgb(look.get("shader_ink_color", PAL["ink"])), np.float32)
    img = img * (1 - sa[..., None]) + shader_col * sa[..., None]
    img = img * (1 - (la2 * ink_k)[..., None]) + lc * (la2 * ink_k)[..., None]
    if overlays is not None:
        img = overlays.over(img)
    # ---- to master resolution -----------------------------------------------------------------
    mw, mh = master_size or (int(W * m / k), int(H * m / k))
    if (mw, mh) != (W, H):
        img = lanczos(img, (mw, mh))
        la_m = lanczos(np.maximum(la2, sa), (mw, mh))
    else:
        la_m = np.maximum(la2, sa)
    img = np.clip(img, 0, 1)
    out = finish_silk(img, np.clip(la_m, 0, 1), look, seed, m)
    out["mist"] = mist
    out["cover"] = cover
    return out


def finish_silk(img, ink_a, look, seed=0, m=2.0):
    """Pigment granulation, edge pooling, brush streaks and the aged silk ground (master px)."""
    h, w = img.shape[:2]
    ref = np.array(srgb(SILK_REF), np.float32)
    # pigment density relative to bare silk (0 = bare)
    dens = np.clip(1.0 - img / ref[None, None, :], 0.0, 1.0).mean(-1)
    # edge pooling: a wash dries darker at its rim (unsharp mask on the density)
    pk = look.get("pooling", RECIPE["pooling"])
    if pk > 0:
        bd = blur(dens, RECIPE["pooling_px"] * m)
        pool = np.clip(dens - bd, 0, 1) * pk * 3.0
        img = img * (1.0 - pool[..., None] * (1 - ink_a[..., None]))
    # uneven washes: the pigment was laid in several thin coats, so its density drifts softly
    # across every painted area (deeper / paler, never greyer)
    mk = look.get("mottle", RECIPE["mottle"])
    if mk > 0:
        n1 = value_noise(h, w, 22 * m, seed + 61, 3, 0.55) - 0.5
        n2 = value_noise(h, w, 7 * m, seed + 63, 2, 0.5) - 0.5
        var = (n1 * 1.0 + n2 * 0.45) * mk * 2.0 * np.clip(dens * 3.0, 0, 1)
        rel = np.clip(img / ref[None, None, :], 1e-4, 1.5)
        img = ref[None, None, :] * rel ** (1.0 + var[..., None])
    # granulation: pigment particles settle in the silk (only where there is pigment)
    gk = look.get("granulation", RECIPE["granulation"])
    if gk > 0:
        g1 = value_noise(h, w, 0.8 * m, seed + 51, 2, 0.6) - 0.5
        g2 = value_noise(h, w, 4.5 * m, seed + 53, 2, 0.5) - 0.5
        g = (g1 * 0.7 + g2 * 0.5) * gk * np.sqrt(dens) * 2.0
        img = img * (1.0 - g[..., None])
    # brush streaks in the big washes (mostly horizontal)
    sk = look.get("streak", RECIPE["streak"])
    if sk > 0:
        st = value_noise(h, w, 30 * m, seed + 57, 3, 0.55, aniso=(0.12, 1.0)) - 0.5
        img = img * (1.0 - (st * sk * 2.0 * np.clip(dens * 2.0, 0, 1))[..., None])
    # silk ground and fibres multiplied through (ink hides some of the texture)
    sc, tex = silk(h, w, seed, m, **look.get("silk", {}))
    ratio = sc / ref[None, None, :]
    texw = 1.0 - 0.55 * ink_a
    img = img * ratio * (tex ** texw)[..., None]
    # age: a touch of yellowing and desaturation
    ag = dict(RECIPE["age"], **look.get("age", {}))
    lum = (img * np.array([0.299, 0.587, 0.114], np.float32)).sum(-1, keepdims=True)
    img = img * (1 - ag["desat"]) + lum * ag["desat"]
    img = img * np.array([1.0, 1.0 - ag["yellow"] * 0.4, 1.0 - ag["yellow"]], np.float32)
    if look.get("tone"):
        img = img * np.array(look["tone"], np.float32)
    return dict(master=np.clip(img, 0, 1).astype(np.float32))


def downsample_1x(master, size):
    """Master -> game size (Lanczos), then a light unsharp so the ink stays crisp."""
    one = np.clip(lanczos(master, size), 0, 1)
    b = blur(one, 0.9)
    return np.clip(one + (one - b) * 0.35, 0, 1)


def to_png8(img, seed=0):
    """Float sRGB -> uint8 RGBA (alpha 255) with triangular dither."""
    rng = np.random.default_rng(seed + 17)
    n = (rng.random(img.shape, np.float32) - rng.random(img.shape, np.float32)) / 255.0
    a8 = (np.clip(img + n, 0, 1) * 255.0 + 0.5).astype(np.uint8)
    return np.dstack([a8, np.full(a8.shape[:2], 255, np.uint8)])


def save_png(img, path, seed=0):
    from PIL import Image
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    Image.fromarray(to_png8(img, seed), "RGBA").save(path, optimize=True)
    return path
