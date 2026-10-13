"""Freestyle brush-ink outlines.

Crash fix (Blender 4.0 headless): in an *empty* factory scene the default line set has no line
style; rendering with Freestyle then segfaults.  :func:`enable` always assigns a fresh line style.

Second crash (Blender 4.0 Freestyle python): any stroke vertex on an open mesh boundary of a
*smooth-shaded* face raises ``'FEdgeSmooth' object has no attribute 'normal_left'`` in
``parameter_editor.set_thickness`` and Blender then segfaults.  :func:`_patch_freestyle`
monkey-patches the two thickness setters to fall back to symmetric thickness (applied
automatically by :func:`enable`).

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


def _patch_freestyle():
    """Make Freestyle's thickness setters tolerate FEdgeSmooth border edges (see module doc)."""
    import os
    import sys
    p = os.path.join(bpy.utils.system_resource("SCRIPTS"), "freestyle", "modules")
    if p not in sys.path:
        sys.path.append(p)
    import parameter_editor as pe
    if getattr(pe, "_ironart_patched", False):
        return
    orig_set = pe.ThicknessModifierMixIn.set_thickness
    orig_asym = pe.ThicknessBlenderMixIn.blend_thickness_asymmetric

    def set_thickness(self, sv, outer, inner):
        try:
            orig_set(self, sv, outer, inner)
        except AttributeError:
            sv.attribute.thickness = (outer, inner)

    def blend_thickness_asymmetric(self, svert, right, left):
        try:
            orig_asym(self, svert, right, left)
        except AttributeError:
            old = svert.attribute.thickness
            svert.attribute.thickness = tuple(self.blend(o, n) for o, n in zip(old, (right, left)))

    pe.ThicknessModifierMixIn.set_thickness = set_thickness
    pe.ThicknessBlenderMixIn.blend_thickness_asymmetric = blend_thickness_asymmetric
    pe._ironart_patched = True


def _style(name, color, alpha, thickness, ss, taper, calligraphy, pressure_noise, wobble, smooth,
           seed):
    st = bpy.data.linestyles.new(name)
    st.color = palette.lin(color)
    st.alpha = alpha
    st.thickness = thickness * ss
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
        pts = cm.curves[0].points
        pts[0].location = (0.0, 0.3)
        pts[1].location = (1.0, 0.3)
        pts.new(0.12, 1.0)
        pts.new(0.88, 1.0)
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
        m.amplitude = pressure_noise * thickness * ss
        st.thickness = thickness * ss * (1.0 - pressure_noise * 0.5)
        m.period = 18.0 * ss
        m.seed = seed % 512
    return st


def _lineset(fs, name, style, silhouette, border, crease, contour, external_contour,
             material_boundary, collection, exclude_collection):
    ls = fs.linesets.new(name)
    ls.linestyle = style
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
    return ls


def enable(thickness_px=1.0, color="Ink", alpha=1.0, inner_scale=0.55, inner_alpha=0.7,
           inner_color=None, crease_angle=135.0, border=False, crease=True,
           material_boundary=False, taper=True, calligraphy=0.5, pressure_noise=0.25, wobble=0.0,
           smooth=True, as_pass=False, collection=None, exclude_collection=None, scene=None):
    """Enable Freestyle with the studio two-weight brush ink.

    Line set "Outer": the external contour (sprite/figure silhouette against the background) at
    ``thickness_px`` - this is what keeps small sprites readable.
    Line set "Inner": silhouettes + creases (+ material boundaries) inside the shape at
    ``thickness_px * inner_scale`` and ``alpha * inner_alpha`` (``inner_scale=0`` disables it).

    thickness_px     base stroke width in final (target) pixels (see :func:`thickness_for`)
    calligraphy      0..1 strength of the orientation-based thickness variation
    pressure_noise   0..1 fraction of thickness modulated by 1D noise along the stroke
    wobble           geometric noise amplitude in target pixels (0 = clean)
    as_pass          render lines into a separate "Freestyle" pass instead of the beauty image
                     (``post.comp_painterly(ink=True)`` lays it over the painted colour)
    collection       restrict lines to objects in this collection (others get no lines)
    exclude_collection  objects in this collection get no lines
    Returns ``{"outer": lineset, "inner": lineset or None}``.
    """
    sc = scene or bpy.context.scene
    ss = _scene.supersample_factor(sc)
    seed = int(sc.get("ironart_seed", 0))
    _patch_freestyle()
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
    # remove default/old line sets; every line set gets a fresh line style (crash fix)
    while len(fs.linesets) > 0:
        fs.linesets.remove(fs.linesets[0])
    out = {"inner": None}
    if inner_scale > 0:
        st = _style("InkInner", inner_color or color, alpha * inner_alpha, thickness_px * inner_scale,
                    ss, taper, calligraphy, pressure_noise, wobble, smooth, seed + 1)
        out["inner"] = _lineset(fs, "Inner", st, True, border, crease, False, False,
                                material_boundary, collection, exclude_collection)
    st = _style("InkOuter", color, alpha, thickness_px, ss, taper, calligraphy, pressure_noise,
                wobble, smooth, seed)
    out["outer"] = _lineset(fs, "Outer", st, False, False, False, False, True, False, collection,
                            exclude_collection)
    return out


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
