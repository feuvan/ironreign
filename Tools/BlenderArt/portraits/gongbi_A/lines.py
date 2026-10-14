"""Freestyle brush lines for the gongbi bust, rendered as a separate pass.

Line families (each its own line set restricted to one collection):
  face     高古游丝描 'gossamer' line: thin, even, ochre-ink; silhouettes + outer contour of the
           skin (eyelids, lips and nostrils are face-marked out - they are drawn as decals)
  robe     兰叶描 'orchid leaf' line: bolder, swelling and tapering, black ink; silhouettes,
           borders and creases of garments, armour, headgear
  hair     fine dense-ink outline of hair masses
Thickness is given in final (target) pixels and multiplied by the supersample factor.
"""

import math

import bpy

from palette import hex_rgb


def _patch():
    from ironart import ink
    ink._patch_freestyle()


def _lin(c):
    r, g, b = hex_rgb(c)

    def f(x):
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    return (f(r), f(g), f(b))


def style(name, color, thickness, ss, alpha=1.0, head=0.12, tail=0.2, tip=0.25, swell=0.0,
          calligraphy=0.0, noise=0.0, smooth=2.0, min_len=3.0, seed=0, chain="PLAIN"):
    st = bpy.data.linestyles.new(name)
    st.color = _lin(color)
    st.alpha = alpha
    st.thickness = thickness * ss
    st.thickness_position = "CENTER"
    st.use_chaining = True
    st.chaining = chain
    st.use_same_object = True
    st.caps = "ROUND"
    if min_len:
        st.use_length_min = True
        st.length_min = min_len * ss
    if smooth:
        g = st.geometry_modifiers.new("Smooth", "BEZIER_CURVE")
        g.error = smooth * ss
    m = st.thickness_modifiers.new("Taper", "ALONG_STROKE")
    m.blend = "MULTIPLY"
    m.mapping = "CURVE"
    pts = m.curve.curves[0].points
    pts[0].location = (0.0, tip)
    pts[1].location = (1.0, tip * 0.8)
    pts.new(head, 1.0)
    if swell:
        pts.new(0.5, 1.0 + swell)
    pts.new(1.0 - tail, 1.0)
    m.curve.update()
    if calligraphy > 0:
        c = st.thickness_modifiers.new("Brush", "CALLIGRAPHY")
        c.blend = "MULTIPLY"
        c.orientation = math.radians(50.0)
        c.thickness_min = 1.0 - calligraphy * 0.55
        c.thickness_max = 1.0 + calligraphy * 0.35
    if noise > 0:
        nz = st.thickness_modifiers.new("Pressure", "NOISE")
        nz.blend = "ADD"
        nz.amplitude = noise * thickness * ss
        nz.period = 22.0 * ss
        nz.seed = seed % 512
        st.thickness = thickness * ss * (1.0 - noise * 0.5)
    # very thin strokes fade a little (brush lifting) - alpha follows thickness taper
    a = st.alpha_modifiers.new("Lift", "ALONG_STROKE")
    a.blend = "MULTIPLY"
    a.mapping = "CURVE"
    ap = a.curve.curves[0].points
    ap[0].location = (0.0, 0.55)
    ap[1].location = (1.0, 0.45)
    ap.new(0.1, 1.0)
    ap.new(0.85, 1.0)
    a.curve.update()
    return st


def lineset(fs, name, st, col, silhouette=True, border=False, crease=False, contour=False,
            external=True, face_marks=False, material_boundary=False):
    ls = fs.linesets.new(name)
    ls.linestyle = st
    ls.select_by_visibility = True
    ls.visibility = "VISIBLE"
    ls.select_by_edge_types = True
    ls.select_silhouette = silhouette
    ls.select_border = border
    ls.select_crease = crease
    ls.select_contour = contour
    ls.select_external_contour = external
    ls.select_material_boundary = material_boundary
    ls.select_suggestive_contour = False
    ls.select_ridge_valley = False
    ls.select_by_collection = True
    ls.collection = col
    ls.collection_negation = "INCLUSIVE"
    if face_marks:
        ls.select_by_face_marks = True
        ls.face_mark_negation = "EXCLUSIVE"
        ls.face_mark_condition = "ONE"
    return ls


def enable(cols, ss, cfg=None, crease_deg=128.0):
    """cols: {'skin': coll, 'robe': coll, 'hair': coll, 'fine': coll}.  cfg: per family overrides."""
    _patch()
    cfg = cfg or {}
    sc = bpy.context.scene
    sc.render.use_freestyle = True
    sc.render.line_thickness_mode = "ABSOLUTE"
    sc.render.line_thickness = 1.0
    vl = sc.view_layers[0]
    vl.use_freestyle = True
    fs = vl.freestyle_settings
    fs.mode = "EDITOR"
    fs.as_render_pass = True
    fs.crease_angle = math.radians(crease_deg)
    fs.use_culling = False
    fs.use_smoothness = True
    while len(fs.linesets) > 0:
        fs.linesets.remove(fs.linesets[0])
    sets = {}
    if "skin" in cols:
        c = dict(color="ink_ochre", thickness=1.05, head=0.15, tail=0.25, tip=0.2, smooth=1.5,
                 min_len=4.0)
        c.update(cfg.get("skin", {}))
        st = style("Face", ss=ss, **c)
        sets["skin"] = lineset(fs, "Face", st, cols["skin"], silhouette=True, border=False,
                               external=True, face_marks=True)
    if "robe" in cols:
        c = dict(color="ink", thickness=1.55, head=0.1, tail=0.22, tip=0.2, swell=0.25,
                 calligraphy=0.45, noise=0.2, smooth=2.0, min_len=3.0)
        c.update(cfg.get("robe", {}))
        st = style("Robe", ss=ss, **c)
        sets["robe"] = lineset(fs, "Robe", st, cols["robe"], silhouette=True, border=True,
                               crease=True, external=True)
    if "hair" in cols:
        c = dict(color="ink", thickness=0.9, head=0.2, tail=0.3, tip=0.15, smooth=2.0,
                 min_len=4.0)
        c.update(cfg.get("hair", {}))
        st = style("Hair", ss=ss, **c)
        sets["hair"] = lineset(fs, "Hair", st, cols["hair"], silhouette=True, border=True,
                               external=True)
    if "fine" in cols:
        c = dict(color="ink", thickness=0.85, head=0.1, tail=0.2, tip=0.3, smooth=1.0,
                 min_len=2.0)
        c.update(cfg.get("fine", {}))
        st = style("Fine", ss=ss, **c)
        sets["fine"] = lineset(fs, "Fine", st, cols["fine"], silhouette=True, border=True,
                               crease=True, external=True)
    return sets
