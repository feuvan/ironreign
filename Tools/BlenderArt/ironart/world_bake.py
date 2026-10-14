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
    me = obj.data
    for layer in list(me.uv_layers):
        if layer.name != keep:
            me.uv_layers.remove(layer)
    me.uv_layers[keep].name = "UVMap"


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


def unwrap(objs, size=2048, margin_px=6, angle_deg=62.0, weights=None, skip_mats=("Foliage", "Water", "Tint")):
    """One shared atlas for all ``objs``: Smart UV Project of every face whose material is not
    in ``skip_mats`` (those keep their preset UV0), optional per-object texel weights
    (``{name: k}`` scales that object's islands by k before the final pack)."""
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    import bmesh
    for o in objs:
        bm = bmesh.from_edit_mesh(o.data)
        mats = [m.name if m else "" for m in o.data.materials]
        for f in bm.faces:
            f.select = not any(mats[f.material_index].startswith(s) for s in skip_mats) if mats else True
        bmesh.update_edit_mesh(o.data)
    margin = margin_px / float(size)
    t0 = time.time()
    bpy.ops.uv.smart_project(angle_limit=np.radians(angle_deg), island_margin=margin,
                             area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
    if weights:
        for o in objs:
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
        bpy.ops.uv.select_all(action="SELECT")
        bpy.ops.uv.pack_islands(udim_source="CLOSEST_UDIM", rotate=True, margin_method="FRACTION",
                                margin=margin, shape_method="AABB", scale=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    print("[ironart] unwrap %d objects in %.1fs" % (len(objs), time.time() - t0))


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
         margin=16, cavity=0.22, skip_mats=("Foliage", "Water", "Tint"), height=None,
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
    for key, sock, srgb in (("base", "Base Color", True), ("rough", "Roughness", False),
                            ("metal", "Metallic", False)):
        img = _image("%s_%s" % (name, key), size, h, srgb)
        _set_target(mats, img)
        saved = _rewire(mats, sock)
        try:
            bpy.ops.object.bake(type="EMIT", margin=margin)
        finally:
            _restore(saved)
        res[key] = _pixels(img)
    img = _image("%s_normal" % name, size, h, False)
    _set_target(mats, img)
    bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT", margin=margin)
    res["normal"] = _pixels(img)
    if ao:
        sc.cycles.samples = ao_samples
        img = _image("%s_ao" % name, size, h, False)
        _set_target(mats, img)
        bpy.ops.object.bake(type="AO", margin=margin)
        res["ao"] = np.clip(_pixels(img)[..., 0], 0.0, 1.0)
    else:
        res["ao"] = np.ones((h, size), np.float32)
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
    print("[ironart] baked %s %dx%d in %.1fs" % (name, size, h, paths["secs"]))
    return paths


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


def assign(objs, mat, keep=("Foliage", "Water", "Tint")):
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
    cx = (lo.x + hi.x) / 2
    if footprint:
        for k, (want, got) in enumerate(zip(footprint, (hi.x - lo.x, hi.y - lo.y))):
            if want and not (0.8 * want <= got <= 1.2 * want):
                probs.append("footprint %s %.1f m vs %.1f m" % ("xy"[k], got, want))
    if height and not (0.8 * height <= hi.z <= 1.2 * height):
        probs.append("height %.1f m vs %.1f m" % (hi.z, height))
    if abs(cx) > max(1.0, 0.08 * (hi.x - lo.x)):
        probs.append("origin not at the base centre (bbox centre x %.2f)" % cx)
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
