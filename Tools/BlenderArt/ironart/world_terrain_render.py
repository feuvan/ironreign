"""World Terrain family - Blender scene: terrain mesh, instanced trees, water, cameras, renders.

Blender world space for this family: 1 unit = 1 m, X = map x - 1200 (east), Y = 750 - map y
(north up), Z = height.  The terrain grid maps image row 0 (map y = 0, north) to +Y.

    build_terrain(h, albedo_png, water_png, normal_png, step)   displaced grid, image material
    build_sea(sea_png, normal_png)                               opaque painted sea plane at z = 0
    tree_prototypes()                                            Tree_Broad / Pine / Bamboo meshes
    instance_trees(trees, h)                                     one GN-instanced point cloud per type
    camera_top() / camera_persp(focus, distance)                 2D map / Unreal-like 3/4 view
    light_top(cam) / light_persp()                               studio sun / Unreal-like sun

The tree prototypes are the 2D map's stand-ins for SM_Tree_* (the 3D models come from the World
Models family); they match the contract sizes (broad ~20 m, pine ~24 m, bamboo ~19 m at s = 1).
"""

import math
import random

import bpy
import numpy as np
from mathutils import Vector, noise as mnoise

from . import palette, scene
from . import world_terrain_fields as F
from . import world_terrain_recipe as R

OX, OY = F.MAP_W / 2.0, F.MAP_H / 2.0


def to_blender(x, y, z=0.0):
    return (x - OX, OY - y, z)


# ---------------------------------------------------------------------------------------------
# images / materials
# ---------------------------------------------------------------------------------------------
def load_image(path, colorspace="sRGB"):
    img = bpy.data.images.load(path, check_existing=True)
    img.colorspace_settings.name = colorspace
    return img


def _nodes(mat):
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    return nt, nt.nodes, nt.links


def terrain_material(albedo_png, water_png, normal_png, name="TerrainMat", ripple_m=9.0):
    """Albedo image on the map UVs; water (mask) is glossy with a tiled ripple normal map."""
    mat = bpy.data.materials.new(name)
    nt, N, L = _nodes(mat)
    out = N.new("ShaderNodeOutputMaterial")
    p = N.new("ShaderNodeBsdfPrincipled")
    uv = N.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    tex = N.new("ShaderNodeTexImage")
    tex.image = load_image(albedo_png, "sRGB")
    tex.interpolation = "Linear"
    tex.extension = "EXTEND"
    L.new(uv.outputs[0], tex.inputs[0])
    wt = N.new("ShaderNodeTexImage")
    wt.image = load_image(water_png, "Non-Color")
    wt.interpolation = "Linear"
    wt.extension = "EXTEND"
    L.new(uv.outputs[0], wt.inputs[0])
    sep = N.new("ShaderNodeSeparateColor")
    L.new(wt.outputs["Color"], sep.inputs[0])
    water = sep.outputs[0]
    # base colour: water a touch deeper (like M_IronTerrain WaterDarken)
    mixc = N.new("ShaderNodeMix")
    mixc.data_type = "RGBA"
    L.new(water, mixc.inputs[0])
    L.new(tex.outputs["Color"], mixc.inputs[6])
    mul = N.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    L.new(tex.outputs["Color"], mul.inputs[6])
    mul.inputs[7].default_value = (0.86, 0.9, 0.92, 1.0)
    L.new(mul.outputs[2], mixc.inputs[7])
    L.new(mixc.outputs[2], p.inputs["Base Color"])
    rough = N.new("ShaderNodeMapRange")
    L.new(water, rough.inputs["Value"])
    rough.inputs["To Min"].default_value = 0.9
    rough.inputs["To Max"].default_value = 0.07
    L.new(rough.outputs[0], p.inputs["Roughness"])
    spec = N.new("ShaderNodeMapRange")
    L.new(water, spec.inputs["Value"])
    spec.inputs["To Min"].default_value = 0.3
    spec.inputs["To Max"].default_value = 0.55
    L.new(spec.outputs[0], p.inputs["Specular IOR Level"])
    if normal_png:
        tc = N.new("ShaderNodeTexCoord")
        mp = N.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (1.0 / ripple_m, 1.0 / ripple_m, 1.0)
        L.new(tc.outputs["Object"], mp.inputs[0])
        nimg = N.new("ShaderNodeTexImage")
        nimg.image = load_image(normal_png, "Non-Color")
        nimg.interpolation = "Linear"
        L.new(mp.outputs[0], nimg.inputs[0])
        nm = N.new("ShaderNodeNormalMap")
        nm.uv_map = "UVMap"
        L.new(nimg.outputs["Color"], nm.inputs["Color"])
        st = N.new("ShaderNodeMath")
        st.operation = "MULTIPLY"
        L.new(water, st.inputs[0])
        st.inputs[1].default_value = 0.55
        L.new(st.outputs[0], nm.inputs["Strength"])
        L.new(nm.outputs[0], p.inputs["Normal"])
    L.new(p.outputs[0], out.inputs["Surface"])
    return mat


def sea_material(sea_png, normal_png, name="SeaMat", ripple_m=22.0):
    mat = bpy.data.materials.new(name)
    nt, N, L = _nodes(mat)
    out = N.new("ShaderNodeOutputMaterial")
    p = N.new("ShaderNodeBsdfPrincipled")
    uv = N.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    tex = N.new("ShaderNodeTexImage")
    tex.image = load_image(sea_png, "sRGB")
    tex.interpolation = "Linear"
    tex.extension = "EXTEND"
    L.new(uv.outputs[0], tex.inputs[0])
    L.new(tex.outputs["Color"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.1
    p.inputs["Specular IOR Level"].default_value = 0.5
    if normal_png:
        tc = N.new("ShaderNodeTexCoord")
        mp = N.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (1.0 / ripple_m, 1.0 / ripple_m, 1.0)
        L.new(tc.outputs["Object"], mp.inputs[0])
        nimg = N.new("ShaderNodeTexImage")
        nimg.image = load_image(normal_png, "Non-Color")
        L.new(mp.outputs[0], nimg.inputs[0])
        nm = N.new("ShaderNodeNormalMap")
        nm.uv_map = "UVMap"
        nm.inputs["Strength"].default_value = 0.5
        L.new(nimg.outputs["Color"], nm.inputs["Color"])
        L.new(nm.outputs[0], p.inputs["Normal"])
    L.new(p.outputs[0], out.inputs["Surface"])
    return mat


def foliage_material(name, spec):
    """Canopy: per-instance colour variation (Object Info random), leafy clumps, light SSS."""
    mat = bpy.data.materials.new(name)
    nt, N, L = _nodes(mat)
    out = N.new("ShaderNodeOutputMaterial")
    p = N.new("ShaderNodeBsdfPrincipled")
    oi = N.new("ShaderNodeObjectInfo")
    tc = N.new("ShaderNodeTexCoord")
    # per instance: hue/value variation between the two greens and the dark tone
    ramp = N.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.elements[0].position = 0.0
    cr.elements[0].color = palette.lin4(spec["color"])
    cr.elements[1].position = 1.0
    cr.elements[1].color = palette.lin4(spec["color2"])
    L.new(oi.outputs["Random"], ramp.inputs[0])
    # leaf clumps: object-space noise -> darker gaps, lighter tufts
    mp = N.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.9, 0.9, 0.9)
    L.new(tc.outputs["Object"], mp.inputs[0])
    nz = N.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 1.0
    nz.inputs["Detail"].default_value = 4.0
    nz.inputs["Roughness"].default_value = 0.6
    L.new(mp.outputs[0], nz.inputs["Vector"])
    gap = N.new("ShaderNodeMix")
    gap.data_type = "RGBA"
    cl = N.new("ShaderNodeMapRange")
    L.new(nz.outputs["Fac"], cl.inputs["Value"])
    cl.inputs["From Min"].default_value = 0.35
    cl.inputs["From Max"].default_value = 0.62
    L.new(cl.outputs[0], gap.inputs[0])
    gap.inputs[6].default_value = palette.lin4(spec["dark"])
    L.new(ramp.outputs[0], gap.inputs[7])
    L.new(gap.outputs[2], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.85
    p.inputs["Specular IOR Level"].default_value = 0.25
    try:
        p.inputs["Subsurface Weight"].default_value = 0.0
    except KeyError:
        pass
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.45
    bump.inputs["Distance"].default_value = 0.4
    L.new(nz.outputs["Fac"], bump.inputs["Height"])
    L.new(bump.outputs[0], p.inputs["Normal"])
    tr = N.new("ShaderNodeBsdfTranslucent")
    L.new(gap.outputs[2], tr.inputs["Color"])
    mx = N.new("ShaderNodeMixShader")
    mx.inputs[0].default_value = 0.12
    L.new(p.outputs[0], mx.inputs[1])
    L.new(tr.outputs[0], mx.inputs[2])
    L.new(mx.outputs[0], out.inputs["Surface"])
    return mat


def simple_material(name, color, roughness=0.8):
    mat = bpy.data.materials.new(name)
    nt, N, L = _nodes(mat)
    out = N.new("ShaderNodeOutputMaterial")
    p = N.new("ShaderNodeBsdfPrincipled")
    p.inputs["Base Color"].default_value = palette.lin4(color)
    p.inputs["Roughness"].default_value = roughness
    L.new(p.outputs[0], out.inputs["Surface"])
    return mat


# ---------------------------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------------------------
def grid_mesh(name, heights, step=1.0, uv_size=None):
    """Grid object from a master-grid-aligned height array sampled every ``step`` metres:
    vertex (i, j) at map (i * step, j * step).  UVs: u = x / 2400, v = 1 - y / 1500."""
    Hh, Ww = heights.shape
    xs = np.arange(Ww, dtype=np.float32) * step
    ys = np.arange(Hh, dtype=np.float32) * step
    gx, gy = np.meshgrid(xs, ys)
    co = np.stack([gx - OX, OY - gy, heights.astype(np.float32)], -1).reshape(-1)
    me = bpy.data.meshes.new(name)
    me.vertices.add(Ww * Hh)
    me.vertices.foreach_set("co", co)
    ii, jj = np.meshgrid(np.arange(Ww - 1), np.arange(Hh - 1))
    v0 = (jj * Ww + ii).reshape(-1)
    quads = np.stack([v0 + Ww, v0 + Ww + 1, v0 + 1, v0], -1).reshape(-1).astype(np.int32)
    nq = (Ww - 1) * (Hh - 1)
    me.loops.add(nq * 4)
    me.loops.foreach_set("vertex_index", quads)
    me.polygons.add(nq)
    me.polygons.foreach_set("loop_start", np.arange(0, nq * 4, 4, dtype=np.int32))
    me.polygons.foreach_set("loop_total", np.full(nq, 4, dtype=np.int32))
    me.polygons.foreach_set("use_smooth", np.ones(nq, dtype=bool))
    uvl = me.uv_layers.new(name="UVMap")
    vx = (quads % Ww).astype(np.float32) * step
    vy = (quads // Ww).astype(np.float32) * step
    uvs = np.stack([vx / F.MAP_W, 1.0 - vy / F.MAP_H], -1).reshape(-1).astype(np.float32)
    uvl.data.foreach_set("uv", uvs)
    me.update(calc_edges=True)
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def build_terrain(h, albedo_png, water_png, normal_png=None, step=1):
    """``h`` = master grid (1501, 2401) metres; ``step`` decimates (2 = the Height.png grid)."""
    hh = np.asarray(h[::step, ::step], np.float32)
    obj = grid_mesh("Terrain", hh, float(step))
    obj.data.materials.append(terrain_material(albedo_png, water_png, normal_png))
    return obj


def build_sea(sea_png, normal_png=None, margin=0.0):
    """Opaque painted sea plane at z = 0 over the whole map rectangle (land covers it)."""
    hh = np.zeros((2, 2), np.float32)
    obj = grid_mesh("Sea", hh, step=float(F.MAP_W))
    # grid_mesh with step 2400 -> 2x2 vertices spanning x 0..2400, y 0..2400: fix y extent
    me = obj.data
    co = np.zeros(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    co[:, 1] = np.where(co[:, 1] > 0, OY + margin, -OY - margin)
    co[:, 0] = np.where(co[:, 0] > 0, OX + margin, -OX - margin)
    me.vertices.foreach_set("co", co.reshape(-1))
    uvl = me.uv_layers["UVMap"]
    uv = np.zeros(len(uvl.data) * 2, np.float32)
    uvl.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    uv[:, 0] = np.where(uv[:, 0] > 0.5, 1.0, 0.0)
    uv[:, 1] = np.where(uv[:, 1] > 0.5, 1.0, 0.0)
    uvl.data.foreach_set("uv", uv.reshape(-1))
    me.update()
    obj.data.materials.append(sea_material(sea_png, normal_png))
    return obj


# ---------------------------------------------------------------------------------------------
# tree prototypes (bmesh)
# ---------------------------------------------------------------------------------------------
def _bm_to_obj(bm, name, mats):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    for poly in me.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _blob(bm, center, radius, scale, rng, mat_index, subdiv=2, lump=0.22, freq=1.6):
    import bmesh
    ret = bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=radius)
    off = Vector((rng.uniform(0, 100), rng.uniform(0, 100), rng.uniform(0, 100)))
    for v in ret["verts"]:
        d = v.co.normalized()
        n = mnoise.noise(d * freq + off) * 0.6 + mnoise.noise(d * freq * 2.3 + off * 1.7) * 0.4
        v.co = Vector((d.x * scale[0], d.y * scale[1], d.z * scale[2])) * radius * (1.0 + lump * n)
        v.co += Vector(center)
    faces = {f for v in ret["verts"] for f in v.link_faces}
    for f in faces:
        f.material_index = mat_index


def proto_broad(seed=3):
    import bmesh
    t = R.TREES["broad"]
    rng = random.Random(seed)
    bm = bmesh.new()
    H, D = t["height"], t["crown"]
    bmesh.ops.create_cone(bm, cap_ends=True, segments=7, radius1=0.55, radius2=0.3, depth=H * 0.5,
                          matrix=__import__("mathutils").Matrix.Translation((0, 0, H * 0.25)))
    for f in bm.faces:
        f.material_index = 1
    cz = H - D * 0.42
    _blob(bm, (0, 0, cz), D * 0.36, (1, 1, 0.85), rng, 0)
    for i in range(7):
        a = 2 * math.pi * i / 7 + rng.uniform(-0.3, 0.3)
        r = D * rng.uniform(0.2, 0.3)
        _blob(bm, (math.cos(a) * r, math.sin(a) * r, cz - D * rng.uniform(0.02, 0.16)),
              D * rng.uniform(0.2, 0.27), (1, 1, 0.8), rng, 0)
    for i in range(3):
        a = 2 * math.pi * i / 3 + rng.uniform(-0.5, 0.5)
        _blob(bm, (math.cos(a) * D * 0.12, math.sin(a) * D * 0.12, cz + D * 0.17),
              D * 0.19, (1, 1, 0.85), rng, 0)
    return bm


def proto_pine(seed=5):
    """Chinese pine: a leaning trunk with flat, layered foliage pads (open crown, seen from above
    as a cluster of dark pads with gaps)."""
    import bmesh
    from mathutils import Matrix
    t = R.TREES["pine"]
    rng = random.Random(seed)
    bm = bmesh.new()
    H, D = t["height"], t["crown"]
    ret = bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.5, radius2=0.22, depth=H * 0.85,
                                matrix=Matrix.Translation((0, 0, H * 0.42)))
    for f in {f for v in ret["verts"] for f in v.link_faces}:
        f.material_index = 1
    pads = 11
    for k in range(pads):
        f = k / (pads - 1)
        z = H * (0.42 + 0.5 * f) + rng.uniform(-0.6, 0.6)
        reach = D * 0.5 * (1.0 - 0.6 * f)
        a = k * 2.4 + rng.uniform(-0.4, 0.4)
        r = reach * rng.uniform(0.35, 0.75)
        pr = D * rng.uniform(0.15, 0.22) * (1.0 - 0.35 * f)
        _blob(bm, (math.cos(a) * r, math.sin(a) * r, z), pr, (1.25, 1.25, 0.38), rng, 0, subdiv=2, lump=0.3)
    _blob(bm, (0, 0, H * 0.96), D * 0.14, (1.1, 1.1, 0.5), rng, 0, subdiv=2, lump=0.3)
    return bm


def proto_bamboo(seed=7):
    import bmesh
    from mathutils import Matrix
    t = R.TREES["bamboo"]
    rng = random.Random(seed)
    bm = bmesh.new()
    H, D = t["height"], t["crown"]
    for i in range(16):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(0, D * 0.18)
        base = Vector((math.cos(a) * d, math.sin(a) * d, 0))
        lean = Vector((math.cos(a) * rng.uniform(0.08, 0.22), math.sin(a) * rng.uniform(0.08, 0.22), 1)).normalized()
        hh = H * rng.uniform(0.75, 1.0)
        top = base + lean * hh
        mid = (base + top) / 2
        rot = lean.to_track_quat("Z", "Y").to_matrix().to_4x4()
        ret = bmesh.ops.create_cone(bm, cap_ends=False, segments=5, radius1=0.12, radius2=0.06,
                                    depth=hh, matrix=Matrix.Translation(mid) @ rot)
        for f in {f for v in ret["verts"] for f in v.link_faces}:
            f.material_index = 1
        for k in range(3):
            c = base + lean * hh * (0.62 + 0.15 * k) + Vector((math.cos(a), math.sin(a), 0)) * (0.6 + 0.5 * k)
            _blob(bm, c, D * rng.uniform(0.13, 0.19), (1.25, 1.25, 0.55), rng, 0, subdiv=1, lump=0.3)
    return bm


def tree_prototypes():
    mats = {}
    for kind in ("broad", "pine", "bamboo"):
        mats[kind] = foliage_material("Foliage_" + kind, R.TREES[kind])
    trunk = simple_material("Trunk", "#4A3A2A", 0.85)
    stem = simple_material("BambooStem", "#7D8A4E", 0.6)
    protos = {
        "broad": _bm_to_obj(proto_broad(), "Proto_Broad", [mats["broad"], trunk]),
        "pine": _bm_to_obj(proto_pine(), "Proto_Pine", [mats["pine"], trunk]),
        "bamboo": _bm_to_obj(proto_bamboo(), "Proto_Bamboo", [mats["bamboo"], stem]),
    }
    for o in protos.values():
        o.location = (0, 0, -5000)          # out of every view; instanced via geometry nodes
    return protos


def instance_trees(trees, h, protos):
    """One point cloud per tree type with attributes s / r, instanced by geometry nodes."""
    objs = []
    for kind, proto in protos.items():
        pts = [t for t in trees if t["t"] == kind]
        if not pts:
            continue
        x = np.array([t["x"] for t in pts], np.float32)
        y = np.array([t["y"] for t in pts], np.float32)
        s = np.array([t["s"] for t in pts], np.float32)
        r = np.radians(np.array([t["r"] for t in pts], np.float32))
        z = F.sample(h, x, y) - 0.4 * s
        me = bpy.data.meshes.new("TreePts_" + kind)
        me.vertices.add(len(pts))
        me.vertices.foreach_set("co", np.stack([x - OX, OY - y, z], -1).reshape(-1))
        for nm, arr in (("s", s), ("r", r)):
            at = me.attributes.new(nm, "FLOAT", "POINT")
            at.data.foreach_set("value", arr)
        obj = bpy.data.objects.new("Trees_" + kind, me)
        bpy.context.scene.collection.objects.link(obj)
        ng = bpy.data.node_groups.new("TreeInst_" + kind, "GeometryNodeTree")
        ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        N, L = ng.nodes, ng.links
        gi = N.new("NodeGroupInput")
        go = N.new("NodeGroupOutput")
        iop = N.new("GeometryNodeInstanceOnPoints")
        oi = N.new("GeometryNodeObjectInfo")
        oi.inputs["Object"].default_value = proto
        oi.transform_space = "ORIGINAL"
        sa = N.new("GeometryNodeInputNamedAttribute")
        sa.data_type = "FLOAT"
        sa.inputs["Name"].default_value = "s"
        ra = N.new("GeometryNodeInputNamedAttribute")
        ra.data_type = "FLOAT"
        ra.inputs["Name"].default_value = "r"
        cx = N.new("ShaderNodeCombineXYZ")
        L.new(ra.outputs["Attribute"], cx.inputs["Z"])
        L.new(gi.outputs[0], iop.inputs["Points"])
        L.new(oi.outputs["Geometry"], iop.inputs["Instance"])
        L.new(cx.outputs[0], iop.inputs["Rotation"])
        L.new(sa.outputs["Attribute"], iop.inputs["Scale"])
        # proto sits at z = -5000 (ORIGINAL space keeps its local geometry, not its location)
        L.new(iop.outputs["Instances"], go.inputs[0])
        mod = obj.modifiers.new("Instances", "NODES")
        mod.node_group = ng
        objs.append(obj)
    return objs


# ---------------------------------------------------------------------------------------------
# cameras and lights
# ---------------------------------------------------------------------------------------------
def camera_top(x0=0.0, y0=0.0, x1=F.MAP_W, y1=F.MAP_H):
    """Ortho top-down camera framing map rect [x0, x1] x [y0, y1] exactly (screen-up = north).
    The render resolution must already have the rect's aspect."""
    cd = bpy.data.cameras.new("CamTop")
    cd.type = "ORTHO"
    cd.ortho_scale = max(x1 - x0, y1 - y0)
    cd.clip_start = 1.0
    cd.clip_end = 3000.0
    cam = bpy.data.objects.new("CamTop", cd)
    bpy.context.scene.collection.objects.link(cam)
    cx, cy, _ = to_blender(0.5 * (x0 + x1), 0.5 * (y0 + y1))
    cam.location = (cx, cy, 1200.0)
    cam.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.scene.camera = cam
    return cam


def camera_persp(focus, distance, h, tilt=55.0, fov=40.0, yaw=0.0):
    """Unreal strategy camera: looking north, tilted ``tilt`` deg down, horizontal FOV."""
    fx, fy = focus
    fz = float(F.sample(h, np.array([fx]), np.array([fy]))[0])
    cd = bpy.data.cameras.new("CamPersp")
    cd.type = "PERSP"
    cd.sensor_fit = "HORIZONTAL"
    cd.angle = math.radians(fov)
    cd.clip_start = 5.0
    cd.clip_end = 20000.0
    cam = bpy.data.objects.new("CamPersp", cd)
    bpy.context.scene.collection.objects.link(cam)
    t = math.radians(tilt)
    a = math.radians(yaw)
    bx, by, _ = to_blender(fx, fy)
    back = Vector((-math.sin(a), -math.cos(a), 0.0))      # camera south of the focus
    loc = Vector((bx, by, fz)) + back * distance * math.cos(t) + Vector((0, 0, distance * math.sin(t)))
    cam.location = loc
    d = Vector((bx, by, fz)) - loc
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam
    return cam


def _sun(name, direction, strength, color, angle_deg):
    ld = bpy.data.lights.new(name, "SUN")
    ld.color = palette.lin(color)
    ld.energy = strength
    ld.angle = math.radians(angle_deg)
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    d = Vector(direction).normalized()
    ob.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    return ob


def world_color(color, strength):
    w = bpy.data.worlds.get("WTWorld") or bpy.data.worlds.new("WTWorld")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = palette.lin4(color)
    bg.inputs["Strength"].default_value = strength
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    return w


def light_top(cam, rec=None):
    """Studio sun from the screen top-left (STYLE.md section 4) + neutral sky."""
    from . import lights
    rec = rec or R.WORLDMAP
    s = rec["sun"]
    d = lights.screen_dir(cam, s["screen_angle"], s["elevation"])
    sun = _sun("Sun", d, s["strength"], s["color"], s["softness"])
    world_color(rec["sky"]["color"], rec["sky"]["strength"])
    return sun


def light_persp(rec=None):
    """Like AIronEnvironment: sun from the south-west at ~32 deg, sky fill."""
    rec = rec or R.PREVIEW3D
    s = rec["sun"]
    az = math.radians(s["azimuth_from_north"])
    el = math.radians(s["elevation"])
    d = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
    sun = _sun("Sun", d, s["strength"], s["color"], s["softness"])
    w = bpy.data.worlds.get("WTWorld") or bpy.data.worlds.new("WTWorld")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = el
    sky.sun_rotation = math.radians(180.0 - s["azimuth_from_north"])
    sky.sun_disc = False
    sky.altitude = 200.0
    sky.air_density = 1.0
    sky.dust_density = 1.6
    nt.links.new(sky.outputs[0], bg.inputs[0])
    bg.inputs["Strength"].default_value = 0.22
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    return sun
