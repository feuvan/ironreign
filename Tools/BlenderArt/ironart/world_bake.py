"""World Models family: atlas unwrap, Cycles texture bakes, glTF export and verification.

Workflow (see ``Tools/BlenderArt/world_models/build.py``)::

    protos = [MeshBuilder(...).build(...) ...]          # W_* procedural materials, MetreUV
    for o in protos: world_bake.prepare(o)                # MetreUV kept for the patterns, UV0 = atlas
    world_bake.spread(protos)                             # apart in space (no cross-AO)
    world_bake.unwrap(protos, size=2048)                  # one packed atlas for all prototypes
    maps = world_bake.bake(protos, 2048, out_dir, "City_2_Atlas")   # base / orm / normal PNGs
    mat = world_bake.pbr_material("Atlas", maps)          # glTF-exportable Principled material
    world_bake.assign(protos, mat, keep=("Foliage",))     # every atlas face -> the one material
    city = world_bake.instance_join(placements)           # shared-UV instances -> ONE object
    world_bake.export_glb(city, ArtSource/Models/City_2.glb)
    info = world_bake.verify_glb(path, expect=...)         # re-import in a clean scene + checks

Channels are baked by rewiring each material's Principled inputs into an Emission shader (base
colour, roughness, metallic; exact values, no lighting) plus Cycles' tangent-space NORMAL bake
(procedural bump included) and AO (``ao_distance`` metres).  ORM = (AO, roughness, metallic),
the glTF / Unreal packing; AO goes to the glTF occlusion slot through the
``glTF Material Output`` group, which Blender's exporter reads.  A little cavity AO is also
multiplied into the base colour (``cavity``) so small parts keep definition under Lumen.
"""

import fcntl
import math
import json
import os
import struct
import time

import bpy
import numpy as np

from . import REPO_DIR

ART_SOURCE = os.path.join(REPO_DIR, "ArtSource")
MODELS_DIR = os.path.join(ART_SOURCE, "Models")
UV_EXPORT = "UV0"


# ---------------------------------------------------------------------------------------------
# UV layers
# ---------------------------------------------------------------------------------------------
def prepare(obj, export_uv=UV_EXPORT):
    """MeshBuilder's ``UVMap`` (metres) -> ``MetreUV``; add the (empty) export/atlas layer and
    make it active (unwrap and bake both use the active layer)."""
    me = obj.data
    uvs = me.uv_layers
    if "UVMap" in uvs and "MetreUV" not in uvs:
        uvs["UVMap"].name = "MetreUV"
    if export_uv not in uvs:
        uvs.new(name=export_uv)
    uvs.active = uvs[export_uv]
    uvs[export_uv].active_render = True
    return obj


def copy_uv(obj, src, dst=UV_EXPORT, scale=1.0, offset=(0.0, 0.0), faces=None):
    """Copy UV layer ``src`` into ``dst`` (optionally only for ``faces`` indices)."""
    me = obj.data
    a = me.uv_layers[src].data
    b = me.uv_layers[dst].data
    n = len(a)
    buf = np.zeros(n * 2, np.float32)
    a.foreach_get("uv", buf)
    buf = buf.reshape(-1, 2) * scale + np.array(offset, np.float32)
    if faces is None:
        b.foreach_set("uv", buf.reshape(-1))
    else:
        cur = np.zeros(n * 2, np.float32)
        b.foreach_get("uv", cur)
        cur = cur.reshape(-1, 2)
        for fi in faces:
            p = me.polygons[fi]
            cur[p.loop_start:p.loop_start + p.loop_total] = buf[p.loop_start:p.loop_start + p.loop_total]
        b.foreach_set("uv", cur.reshape(-1))


def strip_uvs(obj, keep=UV_EXPORT):
    """Keep only ``keep`` (renamed ``UVMap``): the GLB carries exactly one UV set."""
    me = obj.data
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for nm in [l.name for l in me.uv_layers]:
        if nm == keep:
            continue
        try:
            me.uv_layers.remove(me.uv_layers[nm])
        except RuntimeError:
            a = me.attributes.get(nm)
            if a is not None:
                me.attributes.remove(a)
    me.uv_layers[keep].name = "UVMap"
    me.uv_layers.active = me.uv_layers["UVMap"]


def spread(objs, gap=8.0):
    """Lay prototypes out in a row along +x, ``gap`` metres apart (no cross occlusion in the AO
    bake).  Returns their original matrices."""
    x = 0.0
    for o in objs:
        lo = min(v.co.x for v in o.data.vertices)
        hi = max(v.co.x for v in o.data.vertices)
        o.location = (x - lo, 0.0, 0.0)
        x += (hi - lo) + gap
    bpy.context.view_layer.update()


#: slot-name suffixes written by the kit:
#:   ``~row``  cover-tile rows: no atlas island of their own; after the bake they take the UVs of
#:             the roof surface right under them (:func:`transfer_row_uvs`) and they are left out of
#:             the bake itself (they still occlude the AO bake of the surface)
#:   ``~d``    tiny repeated details (brackets, posts, caps, rings, beasts): mapped into one small
#:             per-material swatch at the top of the atlas (the bake margin fills the swatch)
SUFFIXES = ("~row", "~d")


def base_name(slot):
    for sfx in SUFFIXES:
        if slot.endswith(sfx):
            return slot[:-len(sfx)]
    return slot


def alias_mats(mats):
    """``mats`` + every ``name~row`` / ``name~d`` alias pointing at the same material."""
    out = dict(mats)
    for k, m in mats.items():
        for sfx in SUFFIXES:
            out[k + sfx] = m
    return out


def build(mb, name, mats, **kw):
    """MeshBuilder.build with the suffix aliases; remembers the builder slot names on the object
    (``obj['slots']``), which the unwrap / row transfer read."""
    obj = mb.build(name, alias_mats(mats), **kw)
    obj["slots"] = list(mb.mat_names)
    return obj


def _slots(obj):
    return list(obj.get("slots") or [m.name if m else "" for m in obj.data.materials])


#: trim strips (patterned repeated parts share one strip of the atlas; all instances overlap):
#: base material -> (u0, v0, u1, v1) atlas rectangle, metres represented across (u, v) (None =
#: per-face normalised), u wrap period (pattern-continuous) or None
TRIMS = {
    "W_Fascia": ((0.0, 0.822, 1.0, 0.858), (8.0, None), 8.0),
    "W_BeamPaint": ((0.0, 0.862, 1.0, 0.905), (1.0, 0.75), None),
    "W_Lattice": ((0.0, 0.91, 0.30, 1.0), (5.0, 6.0), None),
}
PACKED_V = 0.815               # unique islands are packed into v in [0, PACKED_V]
REPACK = "AABB"                # pack_islands shape method after Smart UV Project ('' = keep its packing)
SWATCH_RECT = (0.31, 0.91, 1.0, 1.0)


def unwrap(objs, size=2048, margin_px=6, angle_deg=62.0, weights=None, skip_mats=("Leaves", "Bark", "Water", "Tint"),
           swatch=0.045, trims=True, method="metre"):
    """One shared atlas for all ``objs`` (a production-style modular atlas):

    * regular faces: the kit's metre UVs (``method='metre'``, default; or Smart UV Project with
      ``'smart'`` for meshes without good UVs, e.g. the sect rock), jointly packed with the 4.x
      island packer, squeezed into v in [0, PACKED_V]
    * :data:`TRIMS` materials: mapped into their trim strip (every instance shares it)
    * ``~d`` faces: per-material swatch cells in :data:`SWATCH_RECT` (the bake margin fills them)
    * ``~row`` and ``skip_mats`` faces keep their UVs (rows get theirs from the roof later)
    ``weights`` = {object name: k} scales that object's islands before a final repack."""
    import bmesh
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    trim_names = tuple(TRIMS) if trims else ()

    def kind(sl, mats, f):
        nm = sl[f.material_index] if f.material_index < len(sl) else ""
        mn = mats[f.material_index] if f.material_index < len(mats) else ""
        if nm.endswith("~row") or any(mn.startswith(k) for k in skip_mats):
            return "keep", mn
        if nm.endswith("~d"):
            return "swatch", mn
        if base_name(nm) in trim_names:
            return "trim", base_name(nm)
        return "pack", mn

    for o in objs:
        bm = bmesh.from_edit_mesh(o.data)
        sl = _slots(o)
        mats = [m.name if m else "" for m in o.data.materials]
        for f in bm.faces:
            f.select = kind(sl, mats, f)[0] == "pack"
        bmesh.update_edit_mesh(o.data)
    margin = margin_px / float(size)
    t0 = time.time()
    if method == "smart":
        bpy.ops.uv.smart_project(angle_limit=np.radians(angle_deg), island_margin=margin,
                                 area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
    else:
        # the kit's own metre UVs: undistorted, roof slopes / wall runs as single islands, true
        # relative size (uniform texel density after packing)
        for o in objs:
            bm = bmesh.from_edit_mesh(o.data)
            uvl = bm.loops.layers.uv.active
            mlay = bm.loops.layers.uv.get("MetreUV")
            if mlay is None:
                continue
            for f in bm.faces:
                if f.select:
                    for lp in f.loops:
                        lp[uvl].uv = lp[mlay].uv * 0.01
            bmesh.update_edit_mesh(o.data)
    for o in objs if weights else ():
        k = weights.get(o.name)
        if not k or k == 1.0:
            continue
        bm = bmesh.from_edit_mesh(o.data)
        uvl = bm.loops.layers.uv.active
        for f in bm.faces:
            if f.select:
                for lp in f.loops:
                    lp[uvl].uv = lp[uvl].uv * k
        bmesh.update_edit_mesh(o.data)
    # Smart UV Project's own packer wastes ~70 % of the square with thousands of islands: repack
    # with the 4.x island packer (rotation, exact margins), into the rectangle we keep for them
    if REPACK or method != "smart":
        bpy.ops.uv.select_all(action="SELECT")
        bpy.ops.uv.pack_islands(udim_source="CLOSEST_UDIM", rotate=True, rotate_method="CARDINAL",
                                margin_method="FRACTION", margin=margin, shape_method=REPACK or "AABB", scale=True,
                                merge_overlap=False)
    sw_index = {}
    ncol = int((SWATCH_RECT[2] - SWATCH_RECT[0]) / swatch)
    for o in objs:
        bm = bmesh.from_edit_mesh(o.data)
        uvl = bm.loops.layers.uv.active
        mlay = bm.loops.layers.uv.get("MetreUV")
        sl = _slots(o)
        mats = [m.name if m else "" for m in o.data.materials]
        for f in bm.faces:
            k, key = kind(sl, mats, f)
            if k == "pack":
                for lp in f.loops:
                    lp[uvl].uv = (lp[uvl].uv.x, lp[uvl].uv.y * PACKED_V)
            elif k == "swatch":
                if key not in sw_index:
                    sw_index[key] = len(sw_index)
                i = sw_index[key]
                cu = SWATCH_RECT[0] + swatch * (i % ncol) + swatch / 2
                cv = SWATCH_RECT[3] - swatch / 2 - swatch * (i // ncol)
                for lp in f.loops:
                    m = lp[mlay].uv if mlay is not None else lp.vert.co.xy
                    lp[uvl].uv = (cu + ((m.x * 0.37) % 1.0 - 0.5) * swatch * 0.25,
                                  cv + ((m.y * 0.37) % 1.0 - 0.5) * swatch * 0.25)
            elif k == "trim":
                (u0, v0, u1, v1), (su, sv), wrap = TRIMS[key]
                ms = [lp[mlay].uv.copy() for lp in f.loops]
                umin = min(m.x for m in ms)
                umax = max(m.x for m in ms)
                vmin = min(m.y for m in ms)
                vmax = max(m.y for m in ms)
                if wrap:
                    base = wrap * math.floor(umin / wrap)
                    if umax - base > wrap:
                        base = umin
                else:
                    base = 0.0 if umin >= -1e-6 and umax <= su + 1e-6 else umin
                for lp, m in zip(f.loops, ms):
                    uu = min(1.0, max(0.0, (m.x - base) / su))
                    if sv is None:
                        vv = (m.y - vmin) / max(vmax - vmin, 1e-6)
                    else:
                        vv = min(1.0, max(0.0, (m.y - (0.0 if vmin >= -1e-6 else vmin)) / sv))
                    lp[uvl].uv = (u0 + (u1 - u0) * (0.004 + 0.992 * uu), v0 + (v1 - v0) * (0.04 + 0.92 * vv))
        bmesh.update_edit_mesh(o.data)
    bpy.ops.object.mode_set(mode="OBJECT")
    print("[ironart] unwrap %d objects in %.1fs (%d swatches)" % (len(objs), time.time() - t0, len(sw_index)))


def separate_rows(obj):
    """Move the ``~row`` faces of ``obj`` into a new object (returned, or None)."""
    import bmesh
    sl = _slots(obj)
    idx = {i for i, nm in enumerate(sl) if nm.endswith("~row")}
    if not idx:
        return None
    me = obj.data
    mi = np.zeros(len(me.polygons), np.int32)
    me.polygons.foreach_get("material_index", mi)
    if not np.isin(mi, list(idx)).any():
        return None
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(me)
    for f in bm.faces:
        f.select = f.material_index in idx
    bmesh.update_edit_mesh(me)
    bpy.ops.mesh.separate(type="SELECTED")
    bpy.ops.object.mode_set(mode="OBJECT")
    rows = [o for o in bpy.context.selected_objects if o is not obj][0]
    rows.name = obj.name + "_rows"
    rows["slots"] = list(sl)
    return rows


def transfer_row_uvs(rows, surface):
    """Give every ``~row`` loop the atlas UV of the closest point on the matching roof surface
    faces of ``surface`` (same base material, non-row) - rows sample the baked roof under them."""
    from mathutils.bvhtree import BVHTree
    from mathutils.interpolate import poly_3d_calc
    sme = surface.data
    ssl = _slots(surface)
    rsl = _slots(rows)
    suv = sme.uv_layers[UV_EXPORT].data
    verts = [v.co.copy() for v in sme.vertices]
    by_mat = {}
    for p in sme.polygons:
        nm = ssl[p.material_index] if p.material_index < len(ssl) else ""
        if nm.endswith(SUFFIXES):
            continue
        by_mat.setdefault(nm, []).append(p.index)
    trees = {}
    for nm, faces in by_mat.items():
        polys = [list(sme.polygons[i].vertices) for i in faces]
        trees[nm] = (BVHTree.FromPolygons(verts, polys, all_triangles=False), faces)
    rme = rows.data
    ruv = rme.uv_layers[UV_EXPORT].data
    for p in rme.polygons:
        nm = base_name(rsl[p.material_index]) if p.material_index < len(rsl) else ""
        tr = trees.get(nm)
        if tr is None:
            continue
        tree, faces = tr
        for li in p.loop_indices:
            co = rme.vertices[rme.loops[li].vertex_index].co
            hit = tree.find_nearest(co)
            if hit[0] is None:
                continue
            sp = sme.polygons[faces[hit[2]]]
            pts = [verts[v] for v in sp.vertices]
            w = poly_3d_calc(pts, hit[0])
            n = len(w)
            w = [0.8 * wi + 0.2 / n for wi in w]          # stay inside the island (no edge bleed)
            u = sum(wi * suv[l].uv.x for wi, l in zip(w, sp.loop_indices))
            v = sum(wi * suv[l].uv.y for wi, l in zip(w, sp.loop_indices))
            ruv[li].uv = (u, v)


def join(target, others):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in others:
        o.select_set(True)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    slots = target.get("slots")
    bpy.ops.object.join()
    if slots is not None:
        target["slots"] = slots
    return target


# ---------------------------------------------------------------------------------------------
# bakes
# ---------------------------------------------------------------------------------------------
def _principled(mat):
    return next((n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)


def _output(mat):
    return next((n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeOutputMaterial"
                 and n.is_active_output), None) or \
        next((n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeOutputMaterial"), None)


def _bake_mats(objs, skip_mats):
    seen = []
    for o in objs:
        for m in o.data.materials:
            if m and m not in seen and not m.name.startswith(skip_mats) and m.use_nodes:
                seen.append(m)
    return seen


def _set_target(mats, img):
    for m in mats:
        nt = m.node_tree
        n = nt.nodes.get("_BakeTarget")
        if n is None:
            n = nt.nodes.new("ShaderNodeTexImage")
            n.name = "_BakeTarget"
        n.image = img
        for x in nt.nodes:
            x.select = False
        n.select = True
        nt.nodes.active = n


def _rewire(mats, socket):
    saved = []
    for m in mats:
        nt = m.node_tree
        p = _principled(m)
        out = _output(m)
        if p is None or out is None:
            continue
        old = out.inputs["Surface"].links[0].from_socket if out.inputs["Surface"].is_linked else None
        em = nt.nodes.new("ShaderNodeEmission")
        em.name = "_BakeEmit"
        if socket is None:                       # coverage mask: constant white
            em.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
            nt.links.new(em.outputs[0], out.inputs["Surface"])
            saved.append((m, old, em))
            continue
        s = p.inputs[socket]
        if s.is_linked:
            nt.links.new(s.links[0].from_socket, em.inputs["Color"])
        else:
            v = s.default_value
            em.inputs["Color"].default_value = tuple(v) if hasattr(v, "__len__") else (v, v, v, 1.0)
        nt.links.new(em.outputs[0], out.inputs["Surface"])
        saved.append((m, old, em))
    return saved


def _restore(saved):
    for m, old, em in saved:
        nt = m.node_tree
        out = _output(m)
        if old is not None:
            nt.links.new(old, out.inputs["Surface"])
        nt.nodes.remove(em)


def _image(name, w, h, srgb=False, alpha=False):
    """Float, Non-Color bake target: the pixels are exactly the baked (scene linear) values;
    sRGB encoding happens in numpy when the PNG is written."""
    old = bpy.data.images.get(name)
    if old is not None:
        bpy.data.images.remove(old)
    im = bpy.data.images.new(name, w, h, alpha=alpha, float_buffer=True)
    im.colorspace_settings.name = "Non-Color"
    return im


def _pixels(img):
    a = np.empty(img.size[0] * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(img.size[1], img.size[0], 4)


def bake(objs, size, out_dir, name, ao=True, ao_samples=24, ao_distance=2.5, samples=4,
         margin=16, cavity=0.22, skip_mats=("Leaves", "Bark", "Water", "Tint"), height=None,
         ao_floor=0.35, select=None, jpeg=False):
    """Bake base / roughness / metallic / normal (+ AO) of every non-skipped material on
    ``objs`` (all selected, one shared atlas via their active UV layer).  Writes
    ``<name>_Base.png`` (sRGB; ``.jpg`` 4:4:4 q93 when ``jpeg``), ``<name>_ORM.png`` (linear: AO,
    roughness, metallic) and
    ``<name>_Normal.png`` into ``out_dir``; returns {'base', 'orm', 'normal': path, 'secs'}.
    Other objects in the scene still occlude the AO bake (ground plates use that)."""
    sc = bpy.context.scene
    h = height or size
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()
    if sc.world is None:
        sc.world = bpy.data.worlds.new("BakeWorld")
    sc.world.light_settings.distance = ao_distance
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.use_denoising = False
    sc.render.bake.margin = margin
    sc.render.bake.margin_type = "EXTEND"
    sc.render.bake.use_clear = True
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in (select or objs):
        o.select_set(True)
    bpy.context.view_layer.objects.active = (select or objs)[0]
    mats = _bake_mats(objs, skip_mats)
    res = {}
    sc.cycles.samples = samples
    # NB every pass bakes with margin 0: Blender extends the margin per object, so with several
    # objects in one atlas a later object's margin paints over earlier objects' islands.  The
    # coverage mask pass + dilate() below make one correct margin for the whole atlas.
    sc.render.bake.margin = 0
    for key, sock, srgb in (("mask", None, False), ("base", "Base Color", True), ("rough", "Roughness", False),
                            ("metal", "Metallic", False)):
        img = _image("%s_%s" % (name, key), size, h, srgb)
        _set_target(mats, img)
        sc.cycles.samples = 1 if key == "mask" else samples
        saved = _rewire(mats, sock)
        try:
            bpy.ops.object.bake(type="EMIT", margin=0)
        finally:
            _restore(saved)
        res[key] = _pixels(img)
    covered = res.pop("mask")[..., 0] > 0.5
    img = _image("%s_normal" % name, size, h, False)
    _set_target(mats, img)
    bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT", margin=0)
    res["normal"] = _pixels(img)
    if ao:
        sc.cycles.samples = ao_samples
        img = _image("%s_ao" % name, size, h, False)
        _set_target(mats, img)
        bpy.ops.object.bake(type="AO", margin=0)
        res["ao"] = np.clip(_pixels(img)[..., 0], 0.0, 1.0)
    else:
        res["ao"] = np.ones((h, size), np.float32)
    stack = np.dstack([res["base"][..., :3], res["rough"][..., :1], res["metal"][..., :1],
                       res["normal"][..., :3], res["ao"][..., None]])
    stack = dilate(stack, covered, margin, fill=(0.5, 0.5, 0.5, 0.8, 0.0, 0.5, 0.5, 1.0, 1.0))
    res["base"] = stack[..., 0:3]
    res["rough"] = stack[..., 3:4]
    res["metal"] = stack[..., 4:5]
    res["normal"] = stack[..., 5:8]
    res["ao"] = stack[..., 8]
    res["coverage"] = float(covered.mean())
    for m in mats:
        n = m.node_tree.nodes.get("_BakeTarget")
        if n:
            m.node_tree.nodes.remove(n)
    # images: Blender pixels are bottom-up linear floats; PIL wants top-down
    from PIL import Image
    ao_ = np.clip(ao_floor + (1.0 - ao_floor) * res["ao"], 0.0, 1.0)
    base_lin = res["base"][..., :3] * (1.0 - cavity + cavity * res["ao"][..., None])
    base = _lin_to_srgb(np.clip(base_lin, 0.0, 1.0))
    orm = np.dstack([ao_, res["rough"][..., 0], res["metal"][..., 0]])
    nrm = res["normal"][..., :3]
    paths = {}
    for key, arr in (("Base", base), ("ORM", orm), ("Normal", nrm)):
        im = Image.fromarray((np.clip(arr[::-1], 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")
        if key == "Base" and jpeg:
            p = os.path.join(out_dir, "%s_%s.jpg" % (name, key))
            im.save(p, quality=93, subsampling=0, optimize=True)
        else:
            p = os.path.join(out_dir, "%s_%s.png" % (name, key))
            im.save(p, optimize=True)
        paths[key.lower()] = p
    paths["secs"] = time.time() - t0
    paths["coverage"] = res["coverage"]
    print("[ironart] baked %s %dx%d in %.1fs (%.0f %% texels covered)" % (name, size, h, paths["secs"],
                                                                         100 * res["coverage"]))
    return paths


def dilate(arr, known, iters, fill=None):
    """Grow ``arr`` (H x W x C) out of the ``known`` texels by ``iters`` px (mean of known
    8-neighbours per step, no wrap-around); texels still unknown get ``fill`` (per channel)."""
    out = arr.copy()
    known = known.copy()
    H, W = known.shape
    for _ in range(int(iters)):
        kp = np.pad(known, 1, mode="constant", constant_values=False)
        ap = np.pad(out, ((1, 1), (1, 1), (0, 0)), mode="edge")
        acc = np.zeros_like(out)
        cnt = np.zeros((H, W), np.float32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                k = kp[1 + dy:1 + dy + H, 1 + dx:1 + dx + W]
                acc += ap[1 + dy:1 + dy + H, 1 + dx:1 + dx + W] * k[..., None]
                cnt += k
        grow = (~known) & (cnt > 0)
        if not grow.any():
            break
        out[grow] = acc[grow] / cnt[grow][:, None]
        known = known | grow
    if fill is not None:
        out[~known] = np.array(fill, np.float32)[:out.shape[-1]]
    return out


def _lin_to_srgb(x):
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(np.maximum(x, 0.0031308), 1 / 2.4) - 0.055)


# ---------------------------------------------------------------------------------------------
# export materials
# ---------------------------------------------------------------------------------------------
def _gltf_group():
    g = bpy.data.node_groups.get("glTF Material Output")
    if g is None:
        g = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        g.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
        g.interface.new_socket("Thickness", in_out="INPUT", socket_type="NodeSocketFloat")
    return g


def _load(path, colorspace):
    img = bpy.data.images.load(path, check_existing=False)
    img.colorspace_settings.name = colorspace
    return img


def pbr_material(name, maps=None, base=None, orm=None, normal=None, alpha=False, double_sided=False,
                 normal_strength=1.0, color=None, roughness=0.5, metallic=0.0, cutoff=0.5):
    """glTF-exportable Principled material from baked PNGs (or plain factors).
    ``maps`` = the dict returned by :func:`bake`.  ``alpha``: base PNG alpha -> MASK cut-out."""
    if maps:
        base, orm, normal = maps.get("base"), maps.get("orm"), maps.get("normal")
    old = bpy.data.materials.get(name)
    if old is not None:
        old.name = name + "_old"
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Roughness"].default_value = roughness
    p.inputs["Metallic"].default_value = metallic
    if color is not None:
        p.inputs["Base Color"].default_value = tuple(color) + (1.0,) if len(color) == 3 else tuple(color)
    if base:
        b = nt.nodes.new("ShaderNodeTexImage")
        b.image = _load(base, "sRGB")
        nt.links.new(b.outputs["Color"], p.inputs["Base Color"])
        if alpha:
            nt.links.new(b.outputs["Alpha"], p.inputs["Alpha"])
    if orm:
        o = nt.nodes.new("ShaderNodeTexImage")
        o.image = _load(orm, "Non-Color")
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(o.outputs["Color"], sep.inputs[0])
        nt.links.new(sep.outputs["Green"], p.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], p.inputs["Metallic"])
        g = nt.nodes.new("ShaderNodeGroup")
        g.node_tree = _gltf_group()
        nt.links.new(sep.outputs["Red"], g.inputs["Occlusion"])
    if normal:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = _load(normal, "Non-Color")
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = normal_strength
        nt.links.new(n.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], p.inputs["Normal"])
    if alpha:
        m.blend_method = "CLIP"
        m.alpha_threshold = cutoff
        try:
            m.shadow_method = "CLIP"
        except AttributeError:
            pass
    m.use_backface_culling = not (double_sided or alpha)
    return m


def tint_material(name="Tint", roughness=0.85):
    """The runtime-tinted slot: pure white, no texture (M_IronTint multiplies the faction
    colour).  Double sided (banner / pennant cloth)."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    p.inputs["Roughness"].default_value = roughness
    p.inputs["Metallic"].default_value = 0.0
    m.use_backface_culling = False
    return m


def assign(objs, mat, keep=("Leaves", "Bark", "Water", "Tint")):
    """Replace every material slot of ``objs`` by ``mat`` except slots whose name starts with
    one of ``keep`` (those stay for their own export material)."""
    for o in objs:
        me = o.data
        for i, m in enumerate(me.materials):
            if m is None or not m.name.startswith(keep):
                me.materials[i] = mat


def merge_slots(obj):
    """Collapse duplicate material slots (same material) into one."""
    me = obj.data
    mats = list(me.materials)
    first = {}
    remap = []
    for i, m in enumerate(mats):
        key = m.name if m else ""
        if key not in first:
            first[key] = len(first)
        remap.append(first[key])
    idx = np.zeros(len(me.polygons), np.int32)
    me.polygons.foreach_get("material_index", idx)
    idx = np.array(remap, np.int32)[idx]
    uniq = [None] * len(first)
    for i, m in enumerate(mats):
        uniq[remap[i]] = m
    me.materials.clear()
    for m in uniq:
        me.materials.append(m)
    me.polygons.foreach_set("material_index", idx)
    me.update()


# ---------------------------------------------------------------------------------------------
# instancing / joining
# ---------------------------------------------------------------------------------------------
def instance_join(name, placements, extra=()):
    """``placements`` = [(proto object, Matrix world), ...] -> ONE mesh object (instances share
    the prototype's UVs, so the atlas is reused).  ``extra`` objects are joined as they are."""
    col = bpy.context.scene.collection
    objs = []
    for proto, mw in placements:
        o = proto.copy()
        o.data = proto.data
        o.matrix_world = mw
        col.objects.link(o)
        objs.append(o)
    objs.extend(extra)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    target = objs[0]
    # the join target must own its mesh (the others are copied in)
    target.data = target.data.copy()
    bpy.context.view_layer.objects.active = target
    t0 = time.time()
    bpy.ops.object.join()
    target.name = name
    target.data.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    merge_slots(target)
    print("[ironart] joined %s: %d instances, %d tris in %.1fs" % (name, len(objs), tri_count(target),
                                                                     time.time() - t0))
    return target


def tri_count(obj):
    me = obj.data
    lt = np.zeros(len(me.polygons), np.int32)
    me.polygons.foreach_get("loop_total", lt)
    return int((lt - 2).sum())


# ---------------------------------------------------------------------------------------------
# glTF
# ---------------------------------------------------------------------------------------------
def export_glb(obj, path):
    """Export ONE object as GLB (metres, +Y up glTF, applied transforms, PNG textures)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    t0 = time.time()
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True,
                              export_apply=True, export_yup=True, export_image_format="AUTO",
                              export_texcoords=True, export_normals=True, export_tangents=False,
                              export_materials="EXPORT", export_colors=False, export_cameras=False,
                              export_lights=False, export_extras=False, export_animations=False,
                              export_skins=False, export_morph=False,
                              export_draco_mesh_compression_enable=False)
    print("[ironart] exported %s (%.0f KB) in %.1fs" % (os.path.relpath(path, REPO_DIR),
                                                         os.path.getsize(path) / 1024.0, time.time() - t0))
    return path


def glb_json(path):
    data = open(path, "rb").read()
    magic, ver, length = struct.unpack("<III", data[:12])
    if magic != 0x46546C67:
        raise ValueError("%s is not a GLB" % path)
    ln, kind = struct.unpack("<II", data[12:20])
    js = json.loads(data[20:20 + ln])
    bin_off = 20 + ln
    bln, bkind = struct.unpack("<II", data[bin_off:bin_off + 8])
    return js, data[bin_off + 8:bin_off + 8 + bln]


def inspect_glb(path):
    """Summary of a GLB: mesh nodes, triangles, materials (name, alpha mode, textures, factors),
    images (name, size), bounds (glTF space, +Y up)."""
    js, binary = glb_json(path)
    from PIL import Image
    import io
    tris = 0
    lo = np.array([1e9] * 3)
    hi = np.array([-1e9] * 3)
    for mesh in js.get("meshes", []):
        for prim in mesh["primitives"]:
            acc = js["accessors"][prim["indices"]] if "indices" in prim else js["accessors"][prim["attributes"]["POSITION"]]
            tris += acc["count"] // 3
            pa = js["accessors"][prim["attributes"]["POSITION"]]
            lo = np.minimum(lo, pa["min"])
            hi = np.maximum(hi, pa["max"])
    images = []
    for im in js.get("images", []):
        bv = js["bufferViews"][im["bufferView"]]
        raw = binary[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]]
        pil = Image.open(io.BytesIO(raw))
        images.append({"name": im.get("name"), "size": pil.size, "mode": pil.mode, "kb": len(raw) / 1024.0})
    mats = []
    for m in js.get("materials", []):
        pbr = m.get("pbrMetallicRoughness", {})
        mats.append({"name": m["name"], "alpha": m.get("alphaMode", "OPAQUE"),
                     "double": m.get("doubleSided", False),
                     "base_factor": pbr.get("baseColorFactor", [1, 1, 1, 1]),
                     "base_tex": "baseColorTexture" in pbr, "mr_tex": "metallicRoughnessTexture" in pbr,
                     "normal": "normalTexture" in m, "occlusion": "occlusionTexture" in m})
    nodes_with_mesh = [n for n in js.get("nodes", []) if "mesh" in n]
    return {"mesh_nodes": len(nodes_with_mesh), "triangles": tris, "materials": mats, "images": images,
            "bounds_gltf": (lo.tolist(), hi.tolist()), "kb": os.path.getsize(path) / 1024.0}


def reimport(path):
    """Import a GLB into a fresh empty scene; returns the mesh objects."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    bpy.context.view_layer.update()
    return objs


def verify_glb(path, footprint=None, height=None, tint=None, max_tris=150000, front_feature=None):
    """Contract checks on an exported GLB (DESIGN.md 12.3), by JSON inspection **and** a Blender
    re-import into a clean scene:

    * exactly one mesh node; triangles <= ``max_tris``
    * re-imported bounds: metres, +Z up, base on the ground (min z >= -2.6, 0 inside the box),
      origin at the base centre (|centre x| small), ``footprint`` (x, y) / ``height`` within 20 %
    * Tint slots pure white with no texture (``tint`` True requires one, False forbids it)
    * every non-Tint material has base / ORM / normal textures (or is a plain factor material)
    Returns (info dict, list of problems)."""
    info = inspect_glb(path)
    probs = []
    if info["mesh_nodes"] != 1:
        probs.append("%d mesh nodes (the importer uses only the largest)" % info["mesh_nodes"])
    if info["triangles"] > max_tris:
        probs.append("%d triangles > %d" % (info["triangles"], max_tris))
    tints = [m for m in info["materials"] if m["name"].lower().startswith("tint")]
    for m in tints:
        if m["base_tex"] or any(abs(c - 1.0) > 1e-6 for c in m["base_factor"][:3]):
            probs.append("Tint material %s is not pure white" % m["name"])
    if tint is True and not tints:
        probs.append("no Tint material")
    if tint is False and tints:
        probs.append("unexpected Tint material")
    objs = reimport(path)
    if len(objs) != 1:
        probs.append("re-import gave %d mesh objects" % len(objs))
    o = objs[0]
    from mathutils import Vector
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    info["bounds"] = (tuple(round(v, 3) for v in lo), tuple(round(v, 3) for v in hi))
    info["size"] = tuple(round(v, 2) for v in (hi - lo))
    if not (-2.6 <= lo.z <= 0.01):
        probs.append("min z %.2f (base should sit at z = 0, skirts down to -2.5 m)" % lo.z)
    # origin = base centre: the centroid of the lowest 0.6 m of the model (trunk foot, wall and
    # gate skirts) must sit on the origin; the crown / barbican may be asymmetric
    me = o.data
    co = np.zeros(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    base = co[co[:, 2] < co[:, 2].min() + 0.6]
    bc = base[:, :2].mean(0) if len(base) else np.zeros(2)
    info["base_centre"] = (round(float(bc[0]), 2), round(float(bc[1]), 2))
    ext = max(hi.x - lo.x, hi.y - lo.y)
    if abs(bc[0]) > max(0.8, 0.06 * ext) or abs(bc[1]) > max(0.8, 0.1 * ext):
        probs.append("origin not at the base centre (base centroid %.2f, %.2f)" % (bc[0], bc[1]))
    if footprint:
        for k, (want, got) in enumerate(zip(footprint, (hi.x - lo.x, hi.y - lo.y))):
            if want and not (0.8 * want <= got <= 1.2 * want):
                probs.append("footprint %s %.1f m vs %.1f m" % ("xy"[k], got, want))
    if height and not (0.8 * height <= hi.z <= 1.2 * height):
        probs.append("height %.1f m vs %.1f m" % (hi.z, height))
    info["reimport_materials"] = [s.material.name if s.material else None for s in o.material_slots]
    info["obj"] = o
    return info, probs


# ---------------------------------------------------------------------------------------------
# ArtSource/manifest.json (shared with other artists: locked read-modify-write)
# ---------------------------------------------------------------------------------------------
def manifest_add(paths, root=ART_SOURCE):
    """Add ``paths`` (absolute or ArtSource-relative) to ArtSource/manifest.json
    ``{"version": N, "files": [...]}`` and bump the version, under an exclusive file lock so
    concurrent artists never lose each other's entries.  Returns the new version."""
    os.makedirs(root, exist_ok=True)
    mpath = os.path.join(root, "manifest.json")
    lock = open(os.path.join(root, ".manifest.lock"), "a+")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        data = {"version": 0, "files": []}
        if os.path.isfile(mpath):
            with open(mpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        files = list(data.get("files", []))
        for p in paths:
            rel = os.path.relpath(p, root) if os.path.isabs(p) else p
            rel = rel.replace(os.sep, "/")
            if rel not in files:
                files.append(rel)
        data["files"] = sorted(files)
        data["version"] = int(data.get("version", 0)) + 1
        tmp = mpath + ".tmp%d" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, mpath)
        return data["version"]
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


# ---------------------------------------------------------------------------------------------
# one-call atlas for a set of prototypes
# ---------------------------------------------------------------------------------------------
def atlas_bake(protos, size, out_dir, name, preview=False, weights=None, angle_deg=62.0, ao_distance=2.0,
               ao_samples=24, jpeg=True, keep=("Leaves", "Bark", "Water", "Tint"), gap=6.0):
    """prepare -> spread -> unwrap (rows / details handled) -> separate rows -> bake -> row UVs
    from the roof under them -> rejoin -> every atlas slot = the ``Atlas`` material -> back to the
    origin.  Returns (maps, material)."""
    for o in protos:
        prepare(o)
    spread(protos, gap=gap)
    unwrap(protos, size=size, margin_px=4 if preview else 6, angle_deg=angle_deg, weights=weights)
    rows = {o.name: separate_rows(o) for o in protos}
    maps = bake(protos, size, out_dir, name, ao_samples=8 if preview else ao_samples, ao_distance=ao_distance,
                jpeg=jpeg)
    for o in protos:
        r = rows.get(o.name)
        if r is not None:
            transfer_row_uvs(r, o)
            join(o, [r])
    mat = pbr_material("Atlas", maps)
    assign(protos, mat, keep=keep)
    for o in protos:
        o.location = (0, 0, 0)
    bpy.context.view_layer.update()
    return maps, mat
