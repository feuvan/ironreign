"""Icons family: object-level modelling kit for small still-life props.

Every helper builds one mesh object in its **own local frame** and places it with an object
transform (location / rotation / scale stay on the object, unapplied), so the icon materials'
``Object`` texture space follows the part (wood grain along a shaft, blade streaks along a
blade).  Smoothness comes from real modelling: bevel modifiers with harden-normals on hard
props, subdivision on soft ones, enough segments that silhouettes stay round at 512 px.

Conventions: +Z up, the prop's front faces -Y (towards the camera), a composition is ~2 units
across.  Angles are in degrees.
"""

import math

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

from .geometry import MeshBuilder

TAU = math.tau


# ---------------------------------------------------------------------------------------------
# object plumbing
# ---------------------------------------------------------------------------------------------
def link(obj):
    bpy.context.scene.collection.objects.link(obj)
    return obj


def place(obj, loc=(0, 0, 0), rot=(0, 0, 0), scale=1.0):
    obj.location = Vector(loc)
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = Euler(tuple(math.radians(a) for a in rot))
    obj.scale = (scale, scale, scale) if isinstance(scale, (int, float)) else tuple(scale)
    return obj


def mesh_obj(name, mb, mats, smooth=True, auto_smooth=None):
    """MeshBuilder -> object; ``mats`` maps slot names to materials (or one material)."""
    if isinstance(mats, bpy.types.Material):
        mats = {n: mats for n in mb.mat_names}
    o = mb.build(name, mats, auto_smooth_deg=auto_smooth)
    me = o.data
    if smooth:
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
        me.update()
    return o


def subsurf(obj, levels=2):
    m = obj.modifiers.new("Subsurf", "SUBSURF")
    m.levels = levels
    m.render_levels = levels
    return m


def bevel(obj, width=0.01, segments=3, angle=40.0, harden=True, clamp=True):
    m = obj.modifiers.new("Bevel", "BEVEL")
    m.width = width
    m.segments = segments
    m.limit_method = "ANGLE"
    m.angle_limit = math.radians(angle)
    m.use_clamp_overlap = clamp
    m.harden_normals = harden
    if harden:
        obj.data.use_auto_smooth = True
        obj.data.auto_smooth_angle = math.radians(angle)
        obj.data.polygons.foreach_set("use_smooth", [True] * len(obj.data.polygons))
    return m


def solidify(obj, thickness=0.01, offset=0.0):
    m = obj.modifiers.new("Solidify", "SOLIDIFY")
    m.thickness = thickness
    m.offset = offset
    m.use_even_offset = True
    return m


def weighted_normals(obj):
    obj.data.use_auto_smooth = True
    m = obj.modifiers.new("WN", "WEIGHTED_NORMAL")
    m.keep_sharp = True
    return m


def set_mat(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return obj


def apply_all(obj):
    """Apply the modifier stack (needed before booleans or vertex edits)."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev)
    obj.modifiers.clear()
    obj.data = me
    return obj


def join(objs, name=None):
    """Join objects into the first (transforms applied relative to it)."""
    base = objs[0]
    ctx = bpy.context
    for o in ctx.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    ctx.view_layer.objects.active = base
    bpy.ops.object.join()
    if name:
        base.name = name
    return base


def vattr(obj, name, values):
    """Per-vertex float attribute (read by materials through an Attribute node)."""
    me = obj.data
    a = me.attributes.get(name) or me.attributes.new(name, "FLOAT", "POINT")
    a.data.foreach_set("value", list(values))
    return a


# ---------------------------------------------------------------------------------------------
# primitives
# ---------------------------------------------------------------------------------------------
def lathe(name, profile, mat, segments=48, smooth=True, cap_top=False, cap_bottom=False,
          scale_xy=(1.0, 1.0)):
    """Surface of revolution around local Z; ``profile`` = [(radius, z), ...] bottom to top.
    A radius of 0 closes the end at the axis."""
    mb = MeshBuilder()
    mb.lathe(profile, "M", segments, smooth=smooth, cap_top=cap_top, cap_bottom=cap_bottom,
             scale_xy=scale_xy)
    o = mesh_obj(name, mb, {"M": mat}, smooth)
    _merge(o)
    return o


def _merge(o, dist=1e-5):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(o.data)
    bm.free()
    o.data.update()


def tube(name, points, radius, mat, segments=16, caps=True, radius_fn=None, smooth=True):
    mb = MeshBuilder()
    mb.tube(points, radius, "M", segments, caps, smooth, radius_fn)
    return mesh_obj(name, mb, {"M": mat}, smooth)


def cylinder(name, r, h, mat, segments=32, z0=0.0, r_top=None, bevel_w=0.0):
    rt = r if r_top is None else r_top
    prof = [(0.0, z0), (r, z0), (rt, z0 + h), (0.0, z0 + h)]
    o = lathe(name, prof, mat, segments, smooth=True)
    o.data.use_auto_smooth = True
    o.data.auto_smooth_angle = math.radians(40)
    if bevel_w:
        bevel(o, bevel_w, 3)
    return o


def sphere(name, r, mat, segments=32, rings=16, scale=(1, 1, 1)):
    mb = MeshBuilder()
    mb.sphere((0, 0, 0), r, "M", segments, rings, True, scale)
    o = mesh_obj(name, mb, {"M": mat})
    _merge(o)
    return o


def torus(name, R, r, mat, seg=48, rseg=16, arc=TAU, scale_minor=(1.0, 1.0)):
    """Torus in the local XY plane (ring around Z); ``arc`` < 2 pi makes an open ring."""
    mb = MeshBuilder()
    full = abs(arc - TAU) < 1e-6
    nu = seg if full else seg + 1
    rings = []
    for i in range(nu):
        a = arc * i / seg
        c, s = math.cos(a), math.sin(a)
        ring = []
        for j in range(rseg):
            b = TAU * j / rseg
            rr = R + r * scale_minor[0] * math.cos(b)
            ring.append(mb.v((rr * c, rr * s, r * scale_minor[1] * math.sin(b))))
        rings.append(ring)
    for i in range(nu if full else nu - 1):
        a, b = rings[i], rings[(i + 1) % nu]
        for j in range(rseg):
            k = (j + 1) % rseg
            mb.face((a[j], b[j], b[k], a[k]), "M", smooth=True)
    if not full:
        mb.face(rings[0][::-1], "M")
        mb.face(rings[-1], "M")
    return mesh_obj(name, mb, {"M": mat})


def box(name, size, mat, bevel_w=0.0, segments=3, subdiv=0):
    """Box centred on the origin (``size`` = full extents)."""
    sx, sy, sz = size
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = link(bpy.data.objects.new(name, me))
    o.data.materials.append(mat)
    _box_uv(o)
    if bevel_w:
        bevel(o, bevel_w, segments)
    if subdiv:
        subsurf(o, subdiv)
        o.data.polygons.foreach_set("use_smooth", [True] * len(o.data.polygons))
    return o


def _box_uv(o):
    me = o.data
    uvl = me.uv_layers.new(name="UVMap")
    for p in me.polygons:
        n = p.normal
        ax = max(range(3), key=lambda k: abs(n[k]))
        for li in p.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            uvl.data[li].uv = (co.y, co.z) if ax == 0 else ((co.x, co.z) if ax == 1 else (co.x, co.y))


def outline_mesh(name, outline, depth, mat, bevel_w=0.0, segments=3, plane="XZ",
                 holes=(), center_depth=True, smooth_angle=40.0):
    """Extrude a 2D outline [(a, b), ...] (CCW) by ``depth``.

    ``plane`` 'XZ': the shape faces -Y (towards the camera), extruded along +Y;
    'XY': lies flat, extruded along +Z.  ``holes`` are inner outlines (CW or CCW) cut through.
    A bevel modifier with harden normals rounds the edges."""
    bm = bmesh.new()

    def to3(p, d):
        return (p[0], d, p[1]) if plane == "XZ" else (p[0], p[1], d)

    d0 = -depth / 2.0 if center_depth else 0.0
    loops = [outline] + list(holes)
    edges = []
    for lp in loops:
        vs = [bm.verts.new(to3(p, d0)) for p in lp]
        for i in range(len(vs)):
            edges.append(bm.edges.new((vs[i], vs[(i + 1) % len(vs)])))
    res = bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=True, edges=edges)
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(1.0), verts=bm.verts[:],
                             edges=bm.edges[:])
    faces = [f for f in bm.faces]
    ext = bmesh.ops.extrude_face_region(bm, geom=faces)
    vec = (0, depth, 0) if plane == "XZ" else (0, 0, depth)
    bmesh.ops.translate(bm, vec=vec, verts=[e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = link(bpy.data.objects.new(name, me))
    o.data.materials.append(mat)
    _box_uv(o)
    if bevel_w:
        bevel(o, bevel_w, segments, smooth_angle)
    return o


def loft(name, sections, mat, cap0=True, cap1=True, smooth=True, closed=True):
    """Skin a list of rings (each a list of 3D points, same count) into a surface."""
    mb = MeshBuilder()
    rings = [[mb.v(p) for p in sec] for sec in sections]
    n = len(sections[0])
    for a, b in zip(rings[:-1], rings[1:]):
        for i in range(n if closed else n - 1):
            j = (i + 1) % n
            mb.face((a[i], a[j], b[j], b[i]), "M", smooth=smooth)
    if cap0:
        mb.face(rings[0][::-1], "M", smooth=smooth)
    if cap1:
        mb.face(rings[-1], "M", smooth=smooth)
    o = mesh_obj(name, mb, {"M": mat}, smooth)
    _merge(o)
    return o


def grid(name, fn, nu, nv, mat, thickness=0.0, smooth=True, uv=True):
    """Parametric sheet ``fn(u, v) -> (x, y, z)``; optional solidify."""
    mb = MeshBuilder()
    mb.grid(fn, nu, nv, "M", uv_fn=(lambda u, v: (u, v)) if uv else None, smooth=smooth)
    o = mesh_obj(name, mb, {"M": mat}, smooth)
    if thickness:
        solidify(o, thickness)
    return o


def curve_tube(name, points, radius, mat, bevel_res=6, resolution=12, radius_fn=None,
               caps=True, smooth=True):
    """Smooth NURBS-like tube through ``points`` (a Bezier spline with auto handles and a round
    bevel), converted to a mesh.  ``radius_fn(t)`` sets per-point radius (t 0..1)."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.resolution_u = resolution
    cu.bevel_depth = radius
    cu.bevel_resolution = bevel_res
    cu.use_fill_caps = caps
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(points) - 1)
    for i, p in enumerate(points):
        bp = sp.bezier_points[i]
        bp.co = Vector(p)
        bp.handle_left_type = bp.handle_right_type = "AUTO"
        if radius_fn:
            bp.radius = radius_fn(i / max(1, len(points) - 1))
    ob = link(bpy.data.objects.new(name + "_cu", cu))
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob, do_unlink=True)
    o = link(bpy.data.objects.new(name, me))
    o.data.materials.clear()
    o.data.materials.append(mat)
    if smooth:
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    return o


def text(name, string, font_path, size=1.0, depth=0.02, mat=None, bevel_depth=0.0,
         align="CENTER", resolution=12):
    """Extruded text (e.g. a brush glyph) as a mesh, centred, lying in local XY (faces +Z)."""
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = string
    cu.font = bpy.data.fonts.load(font_path, check_existing=True)
    cu.size = size
    cu.extrude = depth
    cu.bevel_depth = bevel_depth
    cu.align_x = align
    cu.align_y = "CENTER"
    cu.resolution_u = resolution
    ob = link(bpy.data.objects.new(name + "_txt", cu))
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob, do_unlink=True)
    o = link(bpy.data.objects.new(name, me))
    if mat is not None:
        o.data.materials.append(mat)
    return o


# ---------------------------------------------------------------------------------------------
# images (2D textures painted with Pillow: calligraphy, seals, labels)
# ---------------------------------------------------------------------------------------------
def pil_image(name, pil_img):
    """Pillow RGBA image -> packed bpy image (sRGB colour, alpha channel kept)."""
    import numpy as np
    w, h = pil_img.size
    arr = np.asarray(pil_img.convert("RGBA"), dtype=np.float32) / 255.0
    old = bpy.data.images.get(name)
    if old is not None:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(name, w, h, alpha=True)
    img.pixels.foreach_set(np.ascontiguousarray(arr[::-1]).ravel())
    img.alpha_mode = "STRAIGHT"
    img.pack()
    return img


def glyph_image(name, chars, font_path, size=512, fill=0.82, columns=None, rotate=0.0,
                line_gap=1.05):
    """Calligraphy texture: ``chars`` drawn in black with alpha = ink (white transparent).
    ``columns`` = list of strings written top-to-bottom, right-to-left (scroll text)."""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if columns:
        ncol = len(columns)
        nrow = max(len(c) for c in columns)
        cell = int(min(size / (ncol * line_gap), size / (nrow * line_gap)) * fill)
        f = ImageFont.truetype(font_path, cell)
        for ci, col in enumerate(columns):
            x = size - (ci + 0.5) * size / ncol
            for ri, ch in enumerate(col):
                y = (ri + 0.5) * size / nrow
                d.text((x, y), ch, font=f, fill=(0, 0, 0, 255), anchor="mm")
    else:
        f = ImageFont.truetype(font_path, int(size * fill))
        d.text((size / 2, size / 2), chars, font=f, fill=(0, 0, 0, 255), anchor="mm")
    if rotate:
        im = im.rotate(rotate, resample=Image.BICUBIC)
    return pil_image(name, im)


# ---------------------------------------------------------------------------------------------
# metaballs (smooth organic volumes -> mesh)
# ---------------------------------------------------------------------------------------------
def metaball(name, elements, mat, resolution=0.03, threshold=0.6, smooth=True):
    """Polygonise metaball ``elements`` into a mesh object.

    element dict: type ('BALL', 'ELLIPSOID', 'CAPSULE', 'CUBE', 'PLANE'), co, radius,
    size (x, y, z for ELLIPSOID/CAPSULE/CUBE), rot (degrees XYZ), negative, stiffness."""
    mb = bpy.data.metaballs.new(name)
    mb.resolution = resolution
    mb.render_resolution = resolution
    mb.threshold = threshold
    for e in elements:
        el = mb.elements.new(type=e.get("type", "BALL"))
        el.co = Vector(e["co"])
        el.radius = e.get("radius", 1.0)
        el.stiffness = e.get("stiffness", 2.0)
        el.use_negative = e.get("negative", False)
        sz = e.get("size")
        if sz is not None:
            el.size_x, el.size_y, el.size_z = sz
        r = e.get("rot")
        if r is not None:
            el.rotation = Euler(tuple(math.radians(a) for a in r)).to_quaternion()
    ob = link(bpy.data.objects.new(name + "_mb", mb))
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.metaballs.remove(mb)
    o = link(bpy.data.objects.new(name, me))
    o.data.materials.append(mat)
    if smooth:
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    return o


def smooth_mesh(obj, iterations=4, factor=0.5):
    m = obj.modifiers.new("Smooth", "SMOOTH")
    m.iterations = iterations
    m.factor = factor
    return m
