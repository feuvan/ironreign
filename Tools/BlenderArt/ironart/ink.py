"""Freestyle brush-ink outlines.

Crash fix (Blender 4.0 headless): in an *empty* factory scene the default line set has no line
style; rendering with Freestyle then segfaults.  :func:`enable` always assigns a fresh line style.

Thickness is given in **target pixels** and multiplied by the scene supersample factor, so the
same number gives the same look at any render scale (STYLE.md table "Ink thickness per size").

Brush feel comes from line-style modifiers:
* along-stroke thickness taper (thin -> full -> thin, like a brush lifting at both ends)
* calligraphy thickness (thicker on strokes running at ~45 deg, like a held brush)
* 1D Perlin noise on thickness (pressure wobble) and a tiny geometric wobble
* chaining + Bezier smoothing so polyline edges become flowing strokes

Recommended use: ``as_pass=True`` and let :mod:`ironart.post` lay the ink over the painted image
*after* the Kuwahara pass, so outlines stay crisp while the colour is painterly.
"""

import math

import bpy

from . import palette, scene as _scene


def enable(thickness_px=1.0, color="Ink", alpha=1.0, crease_angle=140.0, silhouette=True,
           border=True, crease=True, contour=False, external_contour=True, material_boundary=False,
           taper=True, calligraphy=0.5, pressure_noise=0.25, wobble=0.0, smooth=True,
           as_pass=False, collection=None, exclude_collection=None, name="Ink", scene=None):
    """Enable Freestyle on the active view layer with one brush-ink line set.

    thickness_px     base stroke width in final (target) pixels
    calligraphy      0..1 strength of the orientation-based thickness variation
    pressure_noise   0..1 fraction of thickness modulated by 1D noise along the stroke
    wobble           geometric noise amplitude in target pixels (0 = clean)
    as_pass          render lines into a separate "Freestyle" pass instead of the beauty image
    collection       restrict lines to objects in this collection (others get no lines)
    exclude_collection  objects in this collection get no lines
    Returns the line set.
    """
    sc = scene or bpy.context.scene
    ss = _scene.supersample_factor(sc)
    sc.render.use_freestyle = True
    sc.render.line_thickness_mode = "ABSOLUTE"
    sc.render.line_thickness = 1.0
    vl = bpy.context.view_layer
    vl.use_freestyle = True
    fs = vl.freestyle_settings
    fs.mode = "EDITOR"
    fs.as_render_pass = as_pass
    fs.crease_angle = math.radians(crease_angle)
    fs.use_culling = False
    fs.use_smoothness = True
    # remove default/old line sets, then create ours with a fresh line style (crash fix)
    while len(fs.linesets) > 0:
        fs.linesets.remove(fs.linesets[0])
    ls = fs.linesets.new(name)
    ls.linestyle = bpy.data.linestyles.new(name + "Style")
    ls.select_by_visibility = True
    ls.visibility = "VISIBLE"
    ls.select_by_edge_types = True
    ls.select_silhouette = silhouette
    ls.select_border = border
    ls.select_crease = crease
    ls.select_contour = contour
    ls.select_external_contour = external_contour
    ls.select_material_boundary = material_boundary
    ls.select_suggestive_contour = False
    ls.select_ridge_valley = False
    if collection is not None or exclude_collection is not None:
        ls.select_by_collection = True
        ls.collection = collection or exclude_collection
        ls.collection_negation = "INCLUSIVE" if collection is not None else "EXCLUSIVE"

    st = ls.linestyle
    st.color = palette.lin(color)
    st.alpha = alpha
    st.thickness = thickness_px * ss
    st.thickness_position = "CENTER"
    st.use_chaining = True
    st.chaining = "PLAIN"
    st.use_same_object = True
    st.caps = "ROUND"
    if smooth:
        g = st.geometry_modifiers.new("Smooth", "BEZIER_CURVE")
        g.error = 2.0 * ss
    if wobble > 0:
        g = st.geometry_modifiers.new("Wobble", "PERLIN_NOISE_1D")
        g.frequency = 12.0
        g.amplitude = wobble * ss
        g.octaves = 2
    if taper:
        m = st.thickness_modifiers.new("Taper", "ALONG_STROKE")
        m.blend = "MULTIPLY"
        m.mapping = "CURVE"
        cm = m.curve
        crv = cm.curves[0]
        pts = crv.points
        pts[0].location = (0.0, 0.25)
        pts[1].location = (1.0, 0.25)
        pts.new(0.15, 1.0)
        pts.new(0.85, 1.0)
        cm.update()
    if calligraphy > 0:
        m = st.thickness_modifiers.new("Brush", "CALLIGRAPHY")
        m.blend = "MULTIPLY"
        m.orientation = math.radians(45.0)
        m.thickness_min = 1.0 - calligraphy * 0.6
        m.thickness_max = 1.0 + calligraphy * 0.4
    if pressure_noise > 0:
        # NOISE yields 0..amplitude (absolute px) -> ADD it, and drop the base by half of it
        m = st.thickness_modifiers.new("Pressure", "NOISE")
        m.blend = "ADD"
        m.amplitude = pressure_noise * thickness_px * ss
        st.thickness = thickness_px * ss * (1.0 - pressure_noise * 0.5)
        m.period = 18.0 * ss
        m.seed = int(sc.get("ironart_seed", 0)) % 512
    return ls


def disable(scene=None):
    sc = scene or bpy.context.scene
    sc.render.use_freestyle = False
    bpy.context.view_layer.use_freestyle = False


def thickness_for(target_px):
    """Recommended base ink thickness (target px) for an asset whose short side is ``target_px``.

    Keeps the outline weight visually consistent across families (see STYLE.md table).
    """
    if target_px <= 64:
        return 0.75
    if target_px <= 128:
        return 1.0
    if target_px <= 256:
        return 1.25
    if target_px <= 720:
        return 1.6
    return 2.0
