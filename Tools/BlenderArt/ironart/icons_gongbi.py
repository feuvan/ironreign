"""Icons family (gongbi 工笔): the family recipe, camera, pigment materials, ink, passes and the
2D finishing chain that turns a 3D still life into a small ink-and-colour painting.

Every ``Icon_<Name>`` is a subject modelled in 3D (``icons/comp_*.py``) and rendered *flat*, the
way the coloured object plates of a Ming encyclopedia (三才图会 / 天工开物) are painted:

* camera     ONE orthographic 3/4 view for the whole set (elevation 28 deg, azimuth -24 deg: the
             parallel projection of 界画 / encyclopedia plates), fitted per icon so the subject
             fills the keyline box (:func:`fit`)
* colour     emission "pigments" (no lights, no shadows, no speculars): a flat mineral wash
             (DESIGN.md palette) deepening towards the silhouette (晕染 / 分染, facing ratio) and
             very gently on the planes turned away from the painter's light (top-left, the studio
             sun); texture strokes (wood grain, weave, tile rows) are painted into the ``ic_ink``
             AOV by the materials
* ink        Freestyle as a separate pass: a tapered outer contour and finer inner lines
             (creases, borders, material boundaries) with a tapered, calligraphic brush, strokes
             broken at sharp corners (each side one stroke, 铁线描);
             one line set per ink collection (``ink`` warm black, ``soft`` ink grey, ``red`` deep
             cinnabar for flames, ``none``); thicknesses are in 64 px icon pixels
* passes     EXR: colour (premultiplied), Freestyle, object / material index, ``ic_ink``,
             ``ic_nofen``
* finishing  (numpy; runs in Blender or system python3 from the saved ``.npz`` passes)
             region 分染 (each colour area deepens towards its own outline, more on the side away
             from the light; a pigment can soften it through the ``ic_nofen`` AOV), the washes
             laid on silk (a little of the silk tone multiplied in, its warp / weft showing),
             pigment granulation, ink tinted by the colour it bounds, with dry-brush breaks and a
             hint of bleed, premultiplied Lanczos to 128 / 64, a mild unsharp, then the faint
             silk-tone wash halo (#EADDBE, soft, slightly mottled) that lets the ink read on
             parchment, black lacquer and the cinnabar buttons alike; clear 1 px border

All look numbers live in :data:`RECIPE`.  ``bpy`` is imported lazily: the 2D half runs anywhere.
"""

import json
import math
import os

import numpy as np

# =============================================================================================
# palette (sRGB): DESIGN.md section 8 mineral pigments + the mixed tones the icons need
# =============================================================================================
PAL = {
    "silk": "#E6D6B0", "silk_edge": "#D8C39A", "ink": "#1E1A16",
    "malachite": "#3E8E6E", "malachite_l": "#8CBFA0", "malachite_d": "#2A6A52",
    "azurite": "#2B5C8A", "azurite_l": "#7FA6C8", "azurite_d": "#1E4468",
    "cinnabar": "#B5382A", "cinnabar_d": "#8A2A20", "vermilion": "#D0643C",
    "ochre": "#A0643A", "ochre_l": "#C9A274", "ochre_d": "#7A4A2A",
    "rouge": "#9E3B4A", "rouge_l": "#C27080",
    "gold": "#C9A24B", "gold_l": "#E2C67E", "gold_d": "#9A7A34",
    "white": "#F0E8D8", "white_d": "#D9CDB2",
    "ink_grey_l": "#B9B1A2", "ink_grey": "#7E766A", "ink_wash": "#4A443C",
}

#: the 40 icons of DESIGN.md section 8, in manifest order
ICONS = ("Farm", "Commerce", "Walls", "Patrol", "Draft", "Train", "Search", "Recruit", "Move",
         "Transport", "SectTraining", "Alliance", "Truce", "Gift", "March", "Market", "Tavern",
         "Officers", "Factions", "Save", "Load", "EndTurn", "Gold", "Food", "Troops", "Population",
         "Order", "Defense", "Training", "Loyalty", "Settings", "Delegate", "Prisoner", "Fire",
         "Confuse", "Rally", "Duel", "Attack", "Wait", "Undo")

#: the family look numbers (ONE place).  Sizes in "64 px" are icon pixels of the 64 px game icon
#: (the @2x master doubles them, the render multiplies them by render / 64).
RECIPE = dict(
    sizes=(64, 128),                 # game icon, ArtSource @2x master
    render=1024, preview_render=512,  # square render: 16 x 64 / 8 x 128 (preview 8 x 64)
    spp=16, preview_spp=6, filter_width=1.2,
    camera=dict(elevation=28.0, azimuth=-24.0, distance=30.0),
    # keyline box at 64 px (left, top, right, bottom) the subject's geometry fills; the ink and
    # the halo grow ~3.5 px beyond it, the outer 1 px ring stays clear
    keyline=(5.0, 5.0, 59.0, 59.0),
    # painter's light (screen angle CCW from right, elevation towards the viewer)
    light=dict(angle=135.0, elev=40.0),
    form=0.20,                       # wash value change between lit and turned-away planes
    facing=dict(blend=0.30, lo=0.08, hi=0.92, amount=0.55),
    # Freestyle ink (64 px units): outer contour, inner lines; brush feel
    ink=dict(
        ink=dict(color="#1E1A16", alpha=1.0, outer=1.25, inner=0.62, taper=0.45, calli=0.35,
                 smooth=3.5, crease=134.0),
        soft=dict(color="#5E564C", alpha=0.95, outer=0.95, inner=0.5, taper=0.45, calli=0.3,
                  smooth=3.5, crease=150.0),
        red=dict(color="#7A2418", alpha=1.0, outer=1.1, inner=0.6, taper=0.45, calli=0.35,
                 smooth=3.5, crease=150.0),
    ),
    # 2D 分染: each colour region deepens towards its outline over `px` (64 px units); `dir` adds
    # more on the side away from the light; `amount` = max darkening (linear multiply)
    fenran=dict(px=9.0, amount=0.58, dir=0.8, power=1.6),
    granulation=0.06,
    shader_ink=0.9,                  # strength of the material texture strokes (ic_ink AOV)
    ink_dry=0.06, ink_bleed=0.25,
    ink_split=125.0,                  # break strokes at 2D corners sharper than this (deg, 0 off)
    # pigment laid on silk: washes multiply a little of the silk tone (`tint`) and show its
    # warp / weft fibre (`fibre`, +- value); `period` in 64 px units
    silk=dict(tint=0.3, fibre=0.06, period=0.75),
    # line colour: ink takes a little of the pigment it bounds (gongbi lines are ground into the
    # colour, never a printer's black): k = mix towards the local deep pigment, `deep` = its value
    line_tint=dict(k=0.35, deep=0.38, sigma=1.4),
    # silk-tone wash halo (64 px units): blur sigma, gain (how far it carries), max alpha
    halo=dict(color="#EADDBE", edge="#DCC9A2", sigma=0.9, gain=4.5, alpha=0.62, mottle=0.13),
    unsharp={64: (0.6, 0.30), 128: (0.8, 0.22)},
    # review backgrounds: DESIGN.md tokens and the measured UI chrome fields
    backgrounds=dict(parchment="#E9DCC0", panel="#EBDEC2", lacquer="#1B1712",
                     paneldark="#251E18", button="#BB402F"),
)

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
ART_SOURCE = os.path.join(REPO, "ArtSource")
MASTER_DIR = "UI/Icons"                         # ArtSource/UI/Icons/Icon_<Name>@2x.png
AOVS = (("ic_ink", "VALUE"), ("ic_nofen", "VALUE"))


# =============================================================================================
# colour helpers
# =============================================================================================
def srgb(c):
    """Token / '#hex' / sRGB tuple -> sRGB float triple."""
    if isinstance(c, str):
        c = PAL.get(c, c).lstrip("#")
        return tuple(int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return tuple(float(x) for x in c[:3])


def to_lin(x):
    x = np.asarray(x, np.float64)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def to_srgb(x):
    x = np.clip(np.asarray(x, np.float32), 0.0, None)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055).astype(np.float32)


def lin(c):
    return tuple(float(v) for v in to_lin(srgb(c)))


def mixc(a, b, t):
    """Mix two colours in sRGB (painter's mixing) -> sRGB tuple."""
    a, b = srgb(a), srgb(b)
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def shade(c, k):
    """Deepen (k < 1) or lighten towards lead white (k > 1) -> sRGB tuple."""
    c = srgb(c)
    if k <= 1.0:
        return tuple(x * k for x in c)
    w = srgb(PAL["white"])
    t = min(1.0, k - 1.0)
    return tuple(x + (y - x) * t for x, y in zip(c, w))


# =============================================================================================
# Blender: render settings, camera, fit
# =============================================================================================
def setup(preview=False, spp=None, seed=0):
    """Cycles CPU, Standard view, film transparent, emission only, square render, passes."""
    import bpy
    from . import scene
    r = RECIPE
    sc = scene.setup_cycles(samples=spp or (r["preview_spp"] if preview else r["spp"]),
                            transparent=True, preset="sprite", view="Standard", look="None",
                            adaptive_threshold=0.02, seed=seed, filter_width=r["filter_width"],
                            clamp_indirect=1.0)
    cy = sc.cycles
    cy.max_bounces = 1
    cy.diffuse_bounces = 0
    cy.glossy_bounces = 0
    cy.transmission_bounces = 0
    cy.volume_bounces = 0
    cy.transparent_max_bounces = 4
    cy.use_light_tree = False
    n = r["preview_render"] if preview else r["render"]
    sc.render.resolution_x = sc.render.resolution_y = n
    sc.render.resolution_percentage = 100
    sc.render.dither_intensity = 0.0
    sc["ironart_target"] = (64, 64)
    sc["ironart_supersample"] = n // 64
    vl = sc.view_layers[0]
    vl.use_pass_object_index = True
    vl.use_pass_material_index = True
    for nm, t in AOVS:
        if nm not in [a.name for a in vl.aovs]:
            a = vl.aovs.add()
            a.name = nm
            a.type = t
    wd = bpy.data.worlds.new("IC_World")
    wd.use_nodes = True
    bg = wd.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0, 0, 0, 1)
    bg.inputs["Strength"].default_value = 0.0
    sc.world = wd
    return sc


def camera(name="CamIcon"):
    """The family camera: orthographic, fixed 3/4 pose (:func:`fit` sets scale + shift)."""
    import bpy
    from mathutils import Vector
    c = RECIPE["camera"]
    cd = bpy.data.cameras.new(name)
    cd.type = "ORTHO"
    cd.ortho_scale = 3.0
    cd.sensor_fit = "HORIZONTAL"
    cd.clip_start = 0.1
    cd.clip_end = 200.0
    cam = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    el, az = math.radians(c["elevation"]), math.radians(c["azimuth"])
    offs = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    cam.location = offs * c["distance"]
    q = (-offs).normalized().to_track_quat("-Z", "Y")
    cam.rotation_mode = "XYZ"
    cam.rotation_euler = q.to_euler()
    bpy.context.view_layer.update()
    set_light(cam)
    return cam


def _points(objs):
    import bpy
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objs:
        if o.type not in {"MESH", "CURVE", "SURFACE", "FONT", "META"}:
            continue
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        mw = ev.matrix_world
        pts.extend(mw @ v.co for v in me.vertices)
        ev.to_mesh_clear()
    return pts


def fit(cam, objs, fill=1.0, offset=(0.0, 0.0), keyline=None):
    """Solve ortho scale and shift so the projected bounds of ``objs`` fill the keyline box.

    ``fill`` < 1 shrinks a compact subject (optical size balance across the set); ``offset``
    nudges it (fractions of the box, x right, y down).  Returns (w, h) in 64 px units."""
    import bpy
    kl = keyline or RECIPE["keyline"]
    pts = _points(objs)
    if not pts:
        raise ValueError("fit: no geometry")
    inv = cam.matrix_world.inverted()
    uv = [(q.x, q.y) for q in (inv @ p for p in pts)]
    u0 = min(p[0] for p in uv); u1 = max(p[0] for p in uv)
    v0 = min(p[1] for p in uv); v1 = max(p[1] for p in uv)
    bw = (kl[2] - kl[0]) / 64.0
    bh = (kl[3] - kl[1]) / 64.0
    S = max((u1 - u0) / bw, (v1 - v0) / bh) / fill
    cam.data.ortho_scale = S
    bcx = ((kl[0] + kl[2]) / 2.0) / 64.0 - 0.5 + offset[0] * bw
    bcy = 0.5 - ((kl[1] + kl[3]) / 2.0) / 64.0 - offset[1] * bh
    cam.data.shift_x = ((u0 + u1) / 2.0) / S - bcx
    cam.data.shift_y = ((v0 + v1) / 2.0) / S - bcy
    bpy.context.view_layer.update()
    return (u1 - u0) / S * 64.0, (v1 - v0) / S * 64.0


# =============================================================================================
# Blender: pigment materials (emission washes + the ic_ink AOV)
# =============================================================================================
def _G(tree):
    from .scenes_sky import G
    return G(tree)


def _form_group():
    """Shared node group: painter's light 0..1 = N.L * 0.5 + 0.5 (direction set by
    :func:`set_light`)."""
    import bpy
    from .scenes_sky import new_group
    g = bpy.data.node_groups.get("IC_Form")
    if g is not None:
        return g
    g, gb, gi, go = new_group("IC_Form", [], [("Light", "NodeSocketFloat")])
    geo = gb.node("ShaderNodeNewGeometry")
    L = gb.node("ShaderNodeCombineXYZ", name="IC_LightDir")
    L.inputs["X"].default_value = -0.5
    L.inputs["Y"].default_value = -0.5
    L.inputs["Z"].default_value = 0.7
    d = gb.vmath("DOT_PRODUCT", geo.outputs["Normal"], L.outputs[0])
    f = gb.math("ADD", gb.math("MULTIPLY", d.outputs["Value"], 0.5), 0.5, clamp=True)
    gb.link(f, go.inputs["Light"])
    return g


def set_light(cam):
    """Point the painter's light from the screen top-left (RECIPE light) for the camera."""
    from . import lights
    L = RECIPE["light"]
    d = lights.screen_dir(cam, L["angle"], L["elev"])
    n = _form_group().nodes["IC_LightDir"]
    for i, k in enumerate("XYZ"):
        n.inputs[k].default_value = d[i]


_MAT_INDEX = [0]


def new_material(name):
    """(material, G builder, created) - a fresh emission material with a unique pass index."""
    import bpy
    from .materials import new
    mat, nb, created = new(name)
    if created:
        _MAT_INDEX[0] = len([m for m in bpy.data.materials if m.get("ic")]) + 1
        mat.pass_index = _MAT_INDEX[0]
        mat["ic"] = 1
    return mat, _G(nb.tree), created


def _aov(b, name, value):
    a = b.node("ShaderNodeOutputAOV")
    if hasattr(a, "aov_name"):
        a.aov_name = name
    else:
        a.name = name
    b.set(a.inputs["Value"], value)
    return a


def facing(b, blend=None, lo=None, hi=None):
    """0 facing the camera -> 1 at the silhouette (the 分染 deepening towards the outline)."""
    f = RECIPE["facing"]
    lw = b.node("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = f["blend"] if blend is None else blend
    return b.smooth(lw.outputs["Facing"], f["lo"] if lo is None else lo,
                    f["hi"] if hi is None else hi)


def form(b):
    """0 turned to the painter's light -> 1 turned away."""
    fg = b.node("ShaderNodeGroup")
    fg.node_tree = _form_group()
    return b.math("SUBTRACT", 1.0, fg.outputs["Light"])


def pigment(name, light, deep=None, fen=None, formk=None, grad=None, ink=None, hi=None,
            image=None, image_color=None, image_ink=0.0, image_box=None, image_plane="XZ",
            fen2d=1.0):
    """A mineral wash: ``light`` deepening to ``deep`` (default light x 0.62).

    fen     amount of the facing 分染 (default RECIPE facing amount)
    formk   value change on planes turned from the painter's light (default RECIPE form)
    grad    callable(b) -> 0..1 socket: extra deepening (e.g. along a blade, up a flame)
    ink     callable(b) -> 0..1 socket: texture strokes painted into the ``ic_ink`` AOV
    hi      (colour, width): a lighter tone (提白 / 罩染) where the surface faces the viewer
    fen2d   strength of the 2D region 分染 on this pigment (1 = RECIPE, 0 = none: luminous
            motifs such as flames and sword-wind keep their own gradient); written to the
            ``ic_nofen`` AOV as 1 - fen2d
    image   a bpy image (UV mapped) whose alpha lays ``image_color`` (or its own colour) over the
            wash - glyphs, seal impressions, painted motifs; ``image_ink`` also writes it into
            the ic_ink AOV (so it gets the ink treatment); ``image_box`` = (x0, z0, x1, z1)
            maps the image onto the object's local XZ plane instead of the UVs
    """
    mat, b, created = new_material(name)
    if not created:
        return mat
    lc = lin(light)
    dc = lin(deep) if deep is not None else tuple(x * 0.55 for x in lc)
    fen = RECIPE["facing"]["amount"] if fen is None else fen
    formk = RECIPE["form"] if formk is None else formk
    g = None
    if fen > 0:
        g = b.math("MULTIPLY", facing(b), fen)
    if formk > 0:
        fo = b.math("MULTIPLY", form(b), formk * 2.0)
        g = fo if g is None else b.math("ADD", g, fo)
    if grad is not None:
        gg = grad(b)
        g = gg if g is None else b.math("ADD", g, gg)
    if g is None:
        col = b.rgb(lc + (1.0,))
    else:
        col = b.mix(lc + (1.0,), dc + (1.0,), b.clamp01(g))
    if hi is not None:
        hc, hw = hi
        lw = b.node("ShaderNodeLayerWeight")
        lw.inputs["Blend"].default_value = 0.3
        t = b.smooth(lw.outputs["Facing"], 0.0, hw, 1.0, 0.0)
        col = b.mix(col, lin(hc) + (1.0,), t)
    ia = None
    if image is not None:
        tx = b.node("ShaderNodeTexImage")
        tx.image = image
        tx.interpolation = "Cubic"
        tx.extension = "CLIP"
        if image_box is not None:
            x0, z0, x1, z1 = image_box
            co = b.sep(obj_coord(b))
            ax = {"XZ": (0, 2), "XY": (0, 1)}[image_plane]
            u = b.maprange(co[ax[0]], x0, x1, 0.0, 1.0, clamp=False)
            v = b.maprange(co[ax[1]], z0, z1, 0.0, 1.0, clamp=False)
            b.link(b.comb(u, v, 0.0), tx.inputs["Vector"])
        else:
            uv = b.node("ShaderNodeUVMap")
            b.link(uv.outputs["UV"], tx.inputs["Vector"])
        ia = tx.outputs["Alpha"]
        ic = (lin(image_color) + (1.0,)) if image_color is not None else tx.outputs["Color"]
        col = b.mix(col, ic, ia)
    em = b.node("ShaderNodeEmission")
    b.set(em.inputs["Color"], col)
    em.inputs["Strength"].default_value = 1.0
    b.output(em.outputs[0])
    inks = []
    if ink is not None:
        inks.append(ink(b))
    if ia is not None and image_ink > 0:
        inks.append(b.math("MULTIPLY", ia, image_ink))
    if inks:
        v = inks[0] if len(inks) == 1 else b.math("MAXIMUM", inks[0], inks[1])
        _aov(b, "ic_ink", v)
    if fen2d < 1.0:
        _aov(b, "ic_nofen", 1.0 - fen2d)
    return mat


def flat(name, color):
    """Perfectly flat colour (seal paste, ink, lacquer black)."""
    return pigment(name, color, color, fen=0.0, formk=0.0)


def attr(b, name):
    n = b.node("ShaderNodeAttribute", attribute_type="GEOMETRY")
    n.attribute_name = name
    return n.outputs["Fac"]


def obj_coord(b):
    return b.node("ShaderNodeTexCoord").outputs["Object"]


def stripes(b, coord, freq, width=0.10, wobble=0.0, wscale=2.0, vec=None):
    """Thin ink lines across ``coord`` (a float socket) every 1/freq units: 0..1 ink."""
    c = coord
    if wobble and vec is not None:
        n = b.node("ShaderNodeTexNoise", noise_dimensions="3D")
        n.inputs["Scale"].default_value = wscale
        n.inputs["Detail"].default_value = 1.0
        b.link(vec, n.inputs["Vector"])
        c = b.math("ADD", c, b.math("MULTIPLY", b.math("SUBTRACT", n.outputs["Fac"], 0.5), wobble))
    s = b.math("SINE", b.math("MULTIPLY", c, 2 * math.pi * freq))
    return b.smooth(s, 1.0 - width * 2.0, 1.0 - width * 0.4)


# =============================================================================================
# Blender: Freestyle ink (one pair of line sets per ink collection)
# =============================================================================================
def collections():
    import bpy
    sc = bpy.context.scene
    out = {}
    for k in list(RECIPE["ink"]) + ["none"]:
        nm = "IC_" + k
        c = bpy.data.collections.get(nm)
        if c is None:
            c = bpy.data.collections.new(nm)
            sc.collection.children.link(c)
        out[k] = c
    return out


def put(objs, kind="ink"):
    """Move objects into an ink collection ('ink', 'soft', 'red', 'none')."""
    cols = collections()
    for o in objs if isinstance(objs, (list, tuple)) else [objs]:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        cols[kind].objects.link(o)
    return objs


#: Freestyle draws a line ~1.6x the line style thickness in this build (measured on a box at
#: 2 and 1 px x 4: P10 widths 12 / 6, medians 15 / 8): thicknesses are corrected so RECIPE
#: numbers are true widths in 64 px icon pixels
FREESTYLE_SCALE = 1.0 / 1.6


def _style(name, spec, px, which, seed):
    import bpy
    st = bpy.data.linestyles.new(name)
    st.color = lin(spec["color"])
    st.alpha = spec["alpha"]
    t = spec[which] * px * FREESTYLE_SCALE
    st.thickness = t
    st.thickness_position = "CENTER"
    st.use_chaining = True
    st.chaining = "PLAIN"
    st.use_same_object = True
    st.caps = "ROUND"
    st.use_length_min = True
    st.length_min = (2.0 if which == "outer" else 1.6) * px
    split = RECIPE.get("ink_split", 0.0)
    if split:
        # one brush stroke per side: chains break at sharp 2D corners so each stroke starts,
        # swells and lifts (the corners of 铁线描 / 兰叶描 are separate strokes)
        st.use_angle_min = True
        st.angle_min = math.radians(split)
    g = st.geometry_modifiers.new("Smooth", "BEZIER_CURVE")
    g.error = spec["smooth"] * px * 0.5
    # the outer contour is mostly one closed chain whose start point Freestyle picks per run
    # (memory order, not bit-reproducible): a softer taper there keeps that seam invisible
    tp = spec["taper"] * (0.55 if which == "outer" else 1.0)
    m = st.thickness_modifiers.new("Taper", "ALONG_STROKE")
    m.blend = "MULTIPLY"
    m.mapping = "CURVE"
    cm = m.curve
    pts = cm.curves[0].points
    lo = max(0.15, 1.0 - tp * 2.0)
    pts[0].location = (0.0, lo)
    pts[1].location = (1.0, lo * 0.85)
    pts.new(min(0.4, tp * 0.55), 1.0)
    pts.new(max(0.6, 1.0 - tp * 0.7), 0.9)
    cm.update()
    m = st.thickness_modifiers.new("Brush", "CALLIGRAPHY")
    m.blend = "MULTIPLY"
    m.orientation = math.radians(50.0)
    m.thickness_min = 1.0 - spec["calli"] * 0.6
    m.thickness_max = 1.0 + spec["calli"] * 0.25
    # (no NOISE thickness modifier: in this build it breaks the line into ragged blobs)
    return st


def setup_ink(render_px):
    """Freestyle as a render pass; ``render_px`` = render pixels per 64 px icon pixel."""
    import bpy
    from . import ink as _ink
    _ink._patch_freestyle()
    sc = bpy.context.scene
    sc.render.use_freestyle = True
    sc.render.line_thickness_mode = "ABSOLUTE"
    sc.render.line_thickness = 1.0
    vl = sc.view_layers[0]
    vl.use_freestyle = True
    fs = vl.freestyle_settings
    fs.mode = "EDITOR"
    fs.as_render_pass = True
    fs.crease_angle = math.radians(RECIPE["ink"]["ink"]["crease"])
    fs.use_culling = False
    fs.use_smoothness = True
    while len(fs.linesets) > 0:
        fs.linesets.remove(fs.linesets[0])
    cols = collections()
    seed = 3
    for kind, spec in RECIPE["ink"].items():
        for which in ("outer", "inner"):
            st = _style("IC_%s_%s" % (kind, which), spec, render_px, which, seed)
            seed += 7
            ls = fs.linesets.new("IC_%s_%s" % (kind, which))
            ls.linestyle = st
            ls.select_by_visibility = True
            ls.visibility = "VISIBLE"
            ls.select_by_edge_types = True
            ls.select_silhouette = which == "inner"
            ls.select_border = which == "inner"
            ls.select_crease = which == "inner"
            ls.select_material_boundary = which == "inner"
            ls.select_external_contour = which == "outer"
            ls.select_edge_mark = which == "inner"
            ls.select_by_collection = True
            ls.collection = cols[kind]
            ls.collection_negation = "INCLUSIVE"


# =============================================================================================
# Blender: passes
# =============================================================================================
PASSES = (("color", "Image"), ("line", "Freestyle"), ("obj", "IndexOB"), ("mat", "IndexMA"),
          ("ic_ink", "ic_ink"), ("ic_nofen", "ic_nofen"))


def render_passes(out_dir):
    """Render the colour / Freestyle / index / AOV passes as EXRs into ``out_dir`` and return
    ({pass: H x W x 4 float array}, seconds)."""
    import time
    import bpy
    from . import scene
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.endswith(".exr"):
            os.remove(os.path.join(out_dir, f))
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
    names = []
    for fname, sock in PASSES:
        if sock not in rl.outputs:
            continue
        fo.file_slots.new(fname)
        nt.links.new(rl.outputs[sock], fo.inputs[fname])
        names.append(fname)
    sc.render.filepath = os.path.join(out_dir, "beauty.png")
    scene.check_render_settings()
    t0 = time.time()
    bpy.ops.render.render(write_still=False)
    secs = time.time() - t0
    out = {}
    for f in sorted(os.listdir(out_dir)):
        if f.endswith(".exr"):
            key = f[:-8] if f[-8:-4].isdigit() else f[:-4]
            if key in names:
                out[key] = load_exr(os.path.join(out_dir, f))
    return out, secs


def load_exr(path):
    """Linear float RGBA (H x W x 4, top row first) of an EXR via Blender's image loader."""
    import bpy
    img = bpy.data.images.load(path, check_existing=False)
    img.colorspace_settings.name = "Non-Color"
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    return np.ascontiguousarray(a.reshape(h, w, 4)[::-1])


def save_npz(ps, path):
    """Compact pass archive (float16) so the 2D finishing can be re-run without Blender."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    keep = {}
    for k, v in ps.items():
        if k in ("obj", "mat"):
            keep[k] = np.round(v[..., 0]).astype(np.int16)
        elif k.startswith("ic_"):
            keep[k] = v[..., 0].astype(np.float16)
        else:
            keep[k] = v.astype(np.float16)
    np.savez_compressed(path, **keep)
    return path


def load_npz(path):
    d = np.load(path)
    out = {}
    for k in d.files:
        a = d[k]
        if k in ("obj", "mat"):
            out[k] = a.astype(np.float32)[..., None].repeat(4, -1)
        elif k.startswith("ic_"):
            out[k] = a.astype(np.float32)[..., None].repeat(4, -1)
        else:
            out[k] = a.astype(np.float32)
    return out


# =============================================================================================
# 2D finishing (numpy only)
# =============================================================================================
def box_blur(a, r):
    """Edge-clamped box blur of integer radius ``r`` along both axes (O(N))."""
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


def blur(a, sigma, pad_zero=False):
    """Gaussian-like blur (3 box passes), sigma in px.  ``pad_zero`` treats the outside as 0."""
    if sigma <= 0.3:
        return a
    r = max(1, int(round(sigma * 0.85)))
    if pad_zero:
        p = 3 * r + 2
        widths = [(p, p), (p, p)] + [(0, 0)] * (a.ndim - 2)
        out = np.pad(a, widths)
        for _ in range(3):
            out = box_blur(out, r)
        return out[p:-p, p:-p]
    out = a
    for _ in range(3):
        out = box_blur(out, r)
    return out


def value_noise(h, w, cell, seed, octaves=1, gain=0.5):
    """Smooth value noise in [0, 1] (bicubic lattice), ``cell`` px."""
    from PIL import Image
    rng = np.random.default_rng(seed)
    acc = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        c = max(1.0, cell / (2 ** o))
        gh, gw = int(h / c) + 3, int(w / c) + 3
        g = rng.random((gh, gw), np.float32)
        im = Image.fromarray(g, "F").resize((int(gw * c), int(gh * c)), Image.BICUBIC)
        a = np.asarray(im, np.float32)
        acc += amp * a[:h, :w]
        tot += amp
        amp *= gain
    return np.clip(acc / tot, 0.0, 1.0)


def silk_fibre(h, w, period, seed):
    """Plain-weave silk: fine warp (vertical) and weft (horizontal) threads with slubs, roughly
    zero-mean in [-1, 1]; ``period`` = thread spacing in px."""
    from PIL import Image
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    for ax in (0, 1):
        n = int(max(h, w) / max(period, 1.0)) + 4
        # thread brightness varies along its length slowly (slubs) and between threads
        g = rng.random((n, 24), np.float32)
        a = np.asarray(Image.fromarray(g, "F").resize((max(h, w), max(h, w)), Image.BICUBIC),
                       np.float32)
        x = np.arange(max(h, w), dtype=np.float32)
        ridge = 0.5 + 0.5 * np.cos(x / period * 2 * np.pi)
        t = (a - 0.5) * 1.2 + (ridge[:, None] - 0.5) * 0.8
        t = t[:h, :w] if ax == 0 else t.T[:h, :w]
        out += t
    return np.clip(out * 0.5, -1, 1)


def lanczos(img, size):
    from PIL import Image
    if img.ndim == 2:
        return np.asarray(Image.fromarray(np.ascontiguousarray(img, np.float32), "F")
                          .resize(size, Image.LANCZOS), np.float32)
    return np.dstack([lanczos(img[..., c], size) for c in range(img.shape[2])])


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _blur_coarse(a, sigma):
    """Zero-padded blur of a large ``sigma``: computed at 1/q resolution (area mean down,
    bilinear up) - the 分染 field is smooth, so this is exact enough and ~q^2 faster."""
    from PIL import Image
    q = max(1, int(sigma / 10.0))
    if q <= 1:
        return blur(a, sigma, pad_zero=True)
    h, w = a.shape
    H, W = -(-h // q) * q, -(-w // q) * q
    p = np.zeros((H, W), np.float32)
    p[:h, :w] = a
    small = p.reshape(H // q, q, W // q, q).mean(axis=(1, 3))
    small = blur(small, sigma / q, pad_zero=True)
    up = np.asarray(Image.fromarray(np.ascontiguousarray(small, np.float32), "F")
                    .resize((W, H), Image.BILINEAR), np.float32)
    # bilinear resize samples pixel centres: shift is < q / 2 px, negligible at this sigma
    return up[:h, :w]


def fenran(col_lin, A, ids, px, seed=0, nofen=None):
    """Region 分染: every colour region (object x material) deepens towards its own outline,
    more on the side turned away from the painter's light.  ``col_lin`` straight linear RGB."""
    f = RECIPE["fenran"]
    L = RECIPE["light"]
    s = f["px"] * px
    la = math.radians(L["angle"])
    ldir = np.array([math.cos(la), -math.sin(la)], np.float32)   # image x right, y down
    deep = np.zeros(A.shape, np.float32)
    solid = A > 0.5
    for u in np.unique(ids[solid]):
        m = ((ids == u) & solid).astype(np.float32)
        if m.sum() < 4:
            continue
        ys, xs = np.nonzero(m)
        y0, y1 = max(0, ys.min() - int(4 * s)), min(m.shape[0], ys.max() + int(4 * s) + 1)
        x0, x1 = max(0, xs.min() - int(4 * s)), min(m.shape[1], xs.max() + int(4 * s) + 1)
        sub = m[y0:y1, x0:x1]
        bm = _blur_coarse(sub, s * 0.6)
        edge = np.clip(2.0 - 2.0 * bm, 0.0, 1.0) ** f["power"]
        gy, gx = np.gradient(bm)
        gn = np.sqrt(gx * gx + gy * gy) + 1e-6
        # inward direction pointing at the light = an edge on the shadow side
        d = (gx * ldir[0] + gy * ldir[1]) / gn
        k = (1.0 - f["dir"]) + f["dir"] * (0.5 + 0.5 * d)
        e = edge * k
        deep[y0:y1, x0:x1] = np.where(sub > 0, np.maximum(deep[y0:y1, x0:x1], e), deep[y0:y1, x0:x1])
    if nofen is not None:
        deep = deep * (1.0 - nofen)
    return col_lin * (1.0 - f["amount"] * deep)[..., None], deep


def paint(ps, seed=0):
    """Passes (render size) -> straight sRGB RGBA float of the painted subject + its ink."""
    C = ps["color"]
    H, W = C.shape[:2]
    px = W / 64.0
    A = np.clip(C[..., 3], 0.0, 1.0)
    inv = np.where(A > 1e-4, 1.0 / np.maximum(A, 1e-4), 0.0)[..., None]
    col = np.clip(C[..., :3] * inv, 0, None)
    ids = (np.round(ps["obj"][..., 0]).astype(np.int64) * 256
           + np.round(ps["mat"][..., 0]).astype(np.int64)) if "obj" in ps else np.zeros((H, W), np.int64)
    # 分染 (linear), granulation, material texture strokes
    nofen = np.clip(ps["ic_nofen"][..., 0] * inv[..., 0], 0, 1) if "ic_nofen" in ps else None
    col, deep = fenran(col, A, ids, px, seed, nofen)
    sk_ = RECIPE["silk"]
    if sk_["tint"] > 0:
        silk_l = to_lin(srgb(PAL["silk"])).astype(np.float32)
        col = col * (1.0 - sk_["tint"] + sk_["tint"] * silk_l)
    col = to_srgb(col)
    g = (value_noise(H, W, 0.7 * px, seed + 51, 2, 0.6) - 0.5) * 0.7 \
        + (value_noise(H, W, 3.0 * px, seed + 53, 2, 0.5) - 0.5) * 0.5
    col = col * (1.0 - RECIPE["granulation"] * 2.0 * g)[..., None]
    if sk_["fibre"] > 0:
        col = col * (1.0 + sk_["fibre"] * silk_fibre(H, W, sk_["period"] * px, seed + 7))[..., None]
    ink = np.array(srgb(PAL["ink"]), np.float32)
    if "ic_ink" in ps:
        sk = np.clip(ps["ic_ink"][..., 0] * inv[..., 0], 0, 1) * RECIPE["shader_ink"]
        col = col * (1 - sk[..., None]) + ink * 0.85 * sk[..., None] + col * 0.15 * sk[..., None]
    # Freestyle ink: dry-brush breaks + a hint of bleed
    la = np.zeros((H, W), np.float32)
    lc = np.zeros((H, W, 3), np.float32) + ink
    if "line" in ps:
        Lp = ps["line"]
        la = np.clip(Lp[..., 3], 0, 1)
        lcol = to_srgb(np.clip(Lp[..., :3] / np.maximum(la, 1e-4)[..., None], 0, None))
        lc = np.where(la[..., None] > 1e-4, lcol, lc)
        lt = RECIPE["line_tint"]
        if lt["k"] > 0:
            # the pigment the line bounds: colour of the solid area around it (line excluded)
            wgt = A * (1.0 - la)
            sg = lt["sigma"] * px
            num = blur(col * wgt[..., None], sg, pad_zero=True)
            den = blur(wgt, sg, pad_zero=True)
            local = num / np.maximum(den, 1e-4)[..., None]
            cover = np.clip(den * 3.0, 0, 1)[..., None]
            tinted = lc * (1 - lt["k"]) + local * lt["deep"] * lt["k"]
            lc = lc * (1 - cover) + tinted * cover
        bl = blur(la, 0.35 * px) * RECIPE["ink_bleed"]
        la = np.clip(np.maximum(la, bl * 0.6 * (A > 0.5)), 0, 1)
        dry = value_noise(H, W, 0.6 * px, seed + 41, 2, 0.6)
        la = la * (1 - RECIPE["ink_dry"] * smoothstep(0.55, 0.95, dry))
    # premultiplied "over": ink over pigment
    prem = col * A[..., None]
    rgb = lc * la[..., None] + prem * (1 - la[..., None])
    a = la + A * (1 - la)
    out = np.dstack([rgb / np.maximum(a, 1e-5)[..., None], a]).astype(np.float32)
    out[..., :3] = np.clip(out[..., :3], 0, 1)
    return out, deep


def halo_layer(alpha, px, seed=0):
    """The faint silk-tone wash behind the subject: (straight sRGB colour, alpha)."""
    h = RECIPE["halo"]
    H, W = alpha.shape
    b = blur(alpha, h["sigma"] * px, pad_zero=True)
    a = np.clip(b * h["gain"], 0, 1)
    a = smoothstep(0.0, 1.0, a)
    n = value_noise(H, W, 6.0 * px, seed + 71, 3, 0.55)
    a = a * (1.0 - h["mottle"] * (n - 0.3))
    a = np.clip(a, 0, 1) * h["alpha"]
    c0 = np.array(srgb(h["color"]), np.float32)
    c1 = np.array(srgb(h["edge"]), np.float32)
    t = np.clip(1.0 - b * h["gain"], 0, 1)[..., None] * 0.7 + (n[..., None] - 0.5) * 0.4
    col = c0 * (1 - np.clip(t, 0, 1)) + c1 * np.clip(t, 0, 1)
    return col.astype(np.float32), a.astype(np.float32)


def unsharp(img, sigma, amount):
    b = blur(img, sigma)
    return img + (img - b) * amount


def finish(painted, size, seed=0):
    """Painted subject (render size, straight sRGB RGBA) -> finished ``size`` px icon with the
    silk halo: premultiplied Lanczos, unsharp, halo under, clear 1 px border."""
    R = painted.shape[0]
    a = painted[..., 3]
    prem = painted[..., :3] * a[..., None]
    hc, ha = halo_layer(a, R / 64.0, seed)
    # subject over halo (premultiplied)
    rgb = prem + hc * (ha * (1 - a))[..., None]
    al = a + ha * (1 - a)
    small = lanczos(np.dstack([rgb, al]), (size, size))
    al = np.clip(small[..., 3], 0, 1)
    rgb = np.clip(small[..., :3], 0, None)
    us = RECIPE["unsharp"][size]
    rgb = np.clip(unsharp(rgb, us[0], us[1]), 0, None)
    rgb = np.minimum(rgb, al[..., None])           # keep premultiplied valid
    al = np.where(al < 0.012, 0.0, al)
    out = np.dstack([np.where(al[..., None] > 1e-5, rgb / np.maximum(al, 1e-5)[..., None], 0), al])
    out = np.clip(out, 0, 1).astype(np.float32)
    # bleed colour into fully transparent pixels (no dark fringes under filtering)
    out = _bleed(out)
    out[0, :, 3] = out[-1, :, 3] = 0.0
    out[:, 0, 3] = out[:, -1, 3] = 0.0
    return out


def _bleed(img, n=3):
    a = img[..., 3]
    rgb = img[..., :3].copy()
    known = a > 0.02
    for _ in range(n):
        acc = np.zeros_like(rgb)
        cnt = np.zeros(a.shape, np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            sh = np.roll(np.roll(rgb * known[..., None], dy, 0), dx, 1)
            kn = np.roll(np.roll(known, dy, 0), dx, 1)
            acc += sh
            cnt += kn
        new = (~known) & (cnt > 0)
        rgb[new] = acc[new] / cnt[new][..., None]
        known = known | new
    out = img.copy()
    out[..., :3] = rgb
    return out


def compose(ps, seed=0, sizes=None):
    """Passes -> {size: finished icon (straight sRGB RGBA float)} + the painted render."""
    painted, deep = paint(ps, seed)
    icons = {s: finish(painted, s, seed) for s in (sizes or RECIPE["sizes"])}
    return icons, painted


# =============================================================================================
# QA, outputs, review sheets
# =============================================================================================
def over_bg(img, color):
    c = np.array(srgb(color), np.float32)
    a = img[..., 3:4]
    return np.dstack([img[..., :3] * a + c * (1 - a), np.ones(a.shape[:2], np.float32)])


def luma8(img):
    return (img[..., :3] * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1) * 255.0


def subject_bbox(painted, size, thresh=0.5):
    a = painted[..., 3]
    s = painted.shape[0] / float(size)
    ys, xs = np.nonzero(a > thresh)
    if len(xs) == 0:
        return None
    return (xs.min() / s, ys.min() / s, (xs.max() + 1) / s, (ys.max() + 1) / s)


def qa(name, painted, icons):
    """Measured contract of one icon.  Returns [(label, ok, text)]."""
    rows = []

    def rng(label, v, lo, hi):
        ok = lo <= v <= hi
        rows.append((label, ok, "%s = %.3g (%g..%g)" % (label, v, lo, hi)))

    for size, img in icons.items():
        rng("size %d" % size, img.shape[0], size, size)
        ring = np.concatenate([img[0, :, 3], img[-1, :, 3], img[:, 0, 3], img[:, -1, 3]])
        rng("border alpha %d" % size, float(ring.max()), 0.0, 0.0)
    bb = subject_bbox(painted, 64)
    if bb:
        rng("ink left", bb[0], 2.5, 64)
        rng("ink top", bb[1], 2.5, 64)
        rng("ink right", bb[2], 0, 61.5)
        rng("ink bottom", bb[3], 0, 61.5)
        rng("extent", max(bb[2] - bb[0], bb[3] - bb[1]), 40.0, 58.0)
    img = icons[64]
    a = img[..., 3]
    rng("coverage", float((a > 0.5).mean()), 0.14, 0.85)
    # dark-fringe check: mean luma of half-transparent edge pixels must not be darker than the
    # halo / subject would explain (premultiplied-correct edges)
    b = RECIPE["backgrounds"]
    for bgname in ("parchment", "lacquer", "button"):
        comp = over_bg(img, b[bgname])
        lum = luma8(comp)
        bgl = luma8(np.array([[srgb(b[bgname])]], np.float32))[0, 0]
        solid = a > 0.9
        rng("contrast on %s" % bgname, float(np.abs(lum[solid] - bgl).mean()) if solid.any() else 0,
            20.0, 255.0)
    return rows


def save_icon(name, icons):
    """Write ``Content/Data/Art/UI/Icon_<name>.png`` (64, manifest-validated) and the 128 px
    master ``ArtSource/UI/Icons/Icon_<name>@2x.png``.  Returns {label: (path, (w, h), kB)}."""
    from PIL import Image
    from . import post
    rel = "Art/UI/Icon_%s.png" % name
    p1 = post.save_asset(icons[64], rel)
    p2 = os.path.join(ART_SOURCE, MASTER_DIR, "Icon_%s@2x.png" % name)
    save_png(icons[128], p2)
    rep = {}
    for k, p in (("64", p1), ("128", p2)):
        with Image.open(p) as im:
            rep[k] = (p, im.size, os.path.getsize(p) / 1024.0)
    return rep


def to8(img):
    return (np.clip(img, 0, 1) * 255.0 + 0.5).astype(np.uint8)


def save_png(img, path):
    from PIL import Image
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    Image.fromarray(to8(img), "RGBA").save(path, optimize=True)
    return path


def load_png(path):
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGBA"), np.float32) / 255.0


def manifest_add(rel_paths, bump=False):
    """Add ``rel_paths`` (relative to ArtSource) to ``ArtSource/manifest.json`` and bump the
    version when anything was added - or always with ``bump`` (the files were re-exported with
    new content) - under a flock shared with the other families."""
    import fcntl
    import tempfile
    os.makedirs(ART_SOURCE, exist_ok=True)
    path = os.path.join(ART_SOURCE, "manifest.json")
    lock = open(os.path.join(tempfile.gettempdir(), "ironreign_artsource_manifest.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = {"version": 0, "files": []}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                txt = f.read().strip()
            if txt:
                data = json.loads(txt)
        files = data.setdefault("files", [])
        have = set(x if isinstance(x, str) else x.get("path", "") for x in files)
        added = [p for p in rel_paths if p not in have]
        if added or bump:
            files.extend(added)
            data["version"] = int(data.get("version", 0)) + 1
            tmp = path + ".tmp%d" % os.getpid()
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            os.replace(tmp, path)
        return data["version"], added
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def _font(px, which="Body-Regular.ttf"):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(os.path.join(REPO, "Content", "Data", "Fonts", which), px)
    except OSError:
        return ImageFont.load_default()


def _scaled(icon64, icon128, s):
    """What Slate shows at ``s`` px: the 64 px icon (or the 128 master above 64) resampled
    bilinearly with premultiplied alpha (mip-less, like an SImage brush)."""
    from PIL import Image
    src = icon128 if s > 64 else icon64
    if s == src.shape[0]:
        return src
    prem = np.dstack([src[..., :3] * src[..., 3:4], src[..., 3]])
    meth = Image.BILINEAR if s >= src.shape[0] / 2 else Image.BOX
    out = np.dstack([np.asarray(Image.fromarray(np.ascontiguousarray(prem[..., c]), "F")
                                .resize((s, s), meth), np.float32) for c in range(4)])
    a = np.clip(out[..., 3], 0, 1)
    rgb = np.where(a[..., None] > 1e-5, out[..., :3] / np.maximum(a, 1e-5)[..., None], 0)
    return np.dstack([np.clip(rgb, 0, 1), a]).astype(np.float32)


def review_sheet(items, path, sizes=(20, 26, 32, 64), bgs=("parchment", "paneldark", "button"),
                 cols=8, label=True, zoom=1):
    """Grid: for every icon one row per background with the icon at every review size."""
    from PIL import Image, ImageDraw
    b = RECIPE["backgrounds"]
    cell_w = sum(s * zoom for s in sizes) + 5 * (len(sizes) - 1) + 14
    row_h = max(sizes) * zoom + 6
    cell_h = row_h * len(bgs) + (15 if label else 0) + 6
    rows = int(math.ceil(len(items) / float(cols)))
    W, H = cols * cell_w + 8, rows * cell_h + 8
    sheet = Image.new("RGBA", (W, H), (58, 50, 42, 255))
    d = ImageDraw.Draw(sheet)
    f = _font(12)
    for k, (name, icons) in enumerate(items):
        cx = 8 + (k % cols) * cell_w
        cy = 8 + (k // cols) * cell_h
        for j, bgname in enumerate(bgs):
            y = cy + j * row_h
            d.rectangle([cx - 3, y - 3, cx + cell_w - 12, y + max(sizes) * zoom + 2],
                        fill=tuple(int(round(v * 255)) for v in srgb(b[bgname])) + (255,))
            x = cx
            for s in sizes:
                im = _scaled(icons[64], icons[128], s)
                if zoom != 1:
                    im = np.repeat(np.repeat(im, zoom, 0), zoom, 1)
                sheet.alpha_composite(Image.fromarray(to8(im), "RGBA"),
                                      (x, y + (max(sizes) - s) * zoom // 2))
                x += s * zoom + 5
        if label:
            d.text((cx, cy + len(bgs) * row_h - 1), name, fill=(233, 220, 192, 255), font=f)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    sheet.save(path)
    return path
