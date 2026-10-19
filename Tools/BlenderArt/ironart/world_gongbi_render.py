"""World Models family: gongbi review renders of the 3D models (an approximation of Unreal's look).

Unreal draws the World Models with ink outlines (``M_IronInk`` edge post-process), silk grading
and soft light.  :func:`preview` approximates that on the re-imported GLB: a perspective
strategy camera (:func:`ironart.world_render.game_camera`), a soft uniform sky plus a weak
shadowless key from the studio sun direction (no cast shadows, no speculars), Freestyle ink on
silhouettes and creases (alpha-cut leaf cards are excluded with Freestyle face marks - the leaf
atlases carry their own painted outlines), on an aged-silk ground.  Review only, not game art.
"""

import math

import bpy
from mathutils import Vector

from . import ink, lights, palette, scene
from .materials import NB
from . import world_render as WR


def silk_material(name="SilkGround", color="#E6D8B8", dark="#D9C8A2"):
    """Aged silk: warm ground, fine warp / weft fibres, faint mottling (emission-free diffuse)."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nb = NB(m.node_tree)
    for n in list(nb.nodes):
        if n.bl_idname != "ShaderNodeOutputMaterial":
            nb.nodes.remove(n)
    o = nb.coord("Object")
    mott = nb.noise(nb.mapping(o, scale=(0.012, 0.012, 0.012)), scale=1.0, detail=3, roughness=0.5)
    warp = nb.noise(nb.mapping(o, scale=(9.0, 0.25, 1.0)), scale=1.0, detail=2)
    weft = nb.noise(nb.mapping(o, scale=(0.25, 9.0, 1.0)), scale=1.0, detail=2)
    col = nb.ramp(mott.outputs["Fac"], [(0.3, dark), (0.7, color)])
    f = nb.math("MULTIPLY", nb.math("ADD", warp.outputs["Fac"], weft.outputs["Fac"]), 0.5)
    fib = nb.ramp(f, [(0.35, (0.95, 0.95, 0.94, 1)), (0.65, (1.03, 1.03, 1.02, 1))])
    col = nb.mix(col, fib, 1.0, blend="MULTIPLY")
    p = nb.principled(Base_Color=col, Roughness=1.0, Specular_IOR_Level=0.0)
    nb.output(p.outputs[0])
    return m


def mark_no_ink(obj, prefixes=("Leaves", "Silk")):
    """Freestyle face marks on faces whose material starts with ``prefixes`` (the line sets
    exclude marked faces: alpha-cut cards must not be outlined as squares)."""
    me = obj.data
    idx = {i for i, m in enumerate(me.materials) if m and m.name.startswith(prefixes)}
    if not idx:
        return 0
    marks = [p.material_index in idx for p in me.polygons]
    me.polygons.foreach_set("use_freestyle_mark", marks)
    me.update()
    return sum(marks)


def matte(objs):
    """Matte pigment for review: zero specular on every material (Unreal's soft painted pass has
    no highlights either)."""
    for o in objs:
        for m in o.data.materials:
            if m and m.use_nodes:
                for n in m.node_tree.nodes:
                    if n.bl_idname == "ShaderNodeBsdfPrincipled":
                        n.inputs["Specular IOR Level"].default_value = 0.0
                        n.inputs["Roughness"].default_value = 1.0
                        for lk in list(n.inputs["Roughness"].links):
                            m.node_tree.links.remove(lk)


def ink_lines(thickness_px=1.2, inner_scale=0.55, inner_alpha=0.65, crease_angle=115.0, scene_=None):
    """Ruled ink outlines for review renders: silhouettes (outer) + creases (inner), leaf cards and
    the silk ground excluded by face marks."""
    sets = ink.enable(thickness_px=thickness_px, color="#1E1A16", alpha=0.92, inner_scale=inner_scale, inner_alpha=inner_alpha, crease_angle=crease_angle,
                      border=False, crease=True, taper=True, calligraphy=0.25, pressure_noise=0.08, smooth=False,
                      as_pass=False, outer_select="silhouette", scene=scene_)
    for ls in (sets["outer"], sets["inner"]):
        if ls is None:
            continue
        ls.select_by_face_marks = True
        ls.face_mark_negation = "EXCLUSIVE"
        ls.face_mark_condition = "ONE"
    return sets


def cut_below(obj, z=0.0):
    """Bisect away everything below ``z`` (skirts under the terrain: no stray ink at the ground)."""
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.bisect(plane_co=(0, 0, z), plane_no=(0, 0, 1), clear_inner=True, clear_outer=False)
    bpy.ops.object.mode_set(mode="OBJECT")


NOINK_AOV = "NoInk"


def _noink_aov(mat, value=1.0):
    """Make ``mat`` write ``value`` into the NoInk AOV (leaf cards 1, silk ground 0.5: no edge lines)."""
    nt = mat.node_tree
    a = nt.nodes.new("ShaderNodeOutputAOV")
    if hasattr(a, "aov_name"):
        a.aov_name = NOINK_AOV
    else:
        a.name = NOINK_AOV       # Blender 4.0: the AOV name property shadows Node.name
    a.inputs["Value"].default_value = value


def exr_pixels(path, remove=True):
    """EXR (or any image) -> float32 H x W x 4, top-down."""
    import numpy as np
    img = bpy.data.images.load(path)
    a = np.empty(img.size[0] * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(a)
    out = a.reshape(img.size[1], img.size[0], 4)[::-1].copy()
    bpy.data.images.remove(img)
    if remove:
        import os
        os.remove(path)
    return out


def _sh(a, dy, dx, fill):
    import numpy as np
    out = np.full_like(a, fill)
    H, W = a.shape[:2]
    ys0, ys1 = max(0, dy), H + min(0, dy)
    xs0, xs1 = max(0, dx), W + min(0, dx)
    out[ys0:ys1, xs0:xs1] = a[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
    return out


def edge_lines(depth, normal, solid, valid, px_m, thr_px=2.5, thr_min=0.3, crease_dot=0.3, view_dir=None):
    """Ruled ink from the depth / normal buffers - what Unreal's edge post-process draws:

    * ``contour``: pixels of ``solid`` on the front side of a depth step deeper than
      max(``thr_min``, ``thr_px`` pixel sizes) that is not the continuation of a sloped plane
      (second difference), against any ``valid`` neighbour (background = invalid: the outer
      contour is drawn separately);
    * ``crease``: sharp creases, normals turning by more than acos(``crease_dot``) (~73 deg).
    Round tile rows (0.2 m, ~50 deg facets) and leaf cards (not ``solid``) never draw.
    ``px_m`` is the pixel footprint in metres (scalar or per pixel); ``view_dir`` (world, camera
    forward): a step whose front pixel faces away at a grazing angle is a silhouette even when the
    surface itself recedes steeply (rock flanks, round towers).  Returns two bool masks."""
    import numpy as np
    z = np.where(valid, depth, 1e6)
    thr = np.maximum(thr_min, thr_px * px_m)
    grazing = np.zeros(z.shape, bool)
    if view_dir is not None:
        v = np.asarray(view_dir, np.float32)
        grazing = np.abs((normal[..., :3] * v).sum(-1)) < 0.35
    contour = np.zeros(z.shape, bool)
    for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0)):
        zn = _sh(z, dy, dx, 1e6)
        zo = _sh(z, -dy, -dx, 1e6)
        step = zn - z
        bend = zn + np.minimum(zo, z + thr) - 2 * z
        contour |= solid & (step > thr) & ((bend > thr) | grazing) & _sh(valid, dy, dx, False)
    crease = np.zeros(z.shape, bool)
    n = normal[..., :3]
    for dy, dx in ((0, 1), (1, 0)):
        nn = _sh(n, dy, dx, 0.0)
        zn = _sh(z, dy, dx, 1e6)
        crease |= solid & _sh(solid, dy, dx, False) & ((n * nn).sum(-1) < crease_dot) & (np.abs(zn - z) < thr)
    return contour, crease


def ink_over(rgb, mask, color, alpha, width=1.0):
    """Lay a 1 px edge mask as a soft ink line of ~``width`` px over ``rgb`` (float, 0..1)."""
    import numpy as np
    from . import post
    e = np.clip(post.gaussian(mask.astype(np.float32), 0.45 * width) * (1.5 + 0.4 * width), 0, 1)
    e = e[..., None] * alpha
    c = np.array(palette.srgb(color), np.float32)[:3] if isinstance(color, str) else np.array(color, np.float32)
    return rgb * (1 - e) + c * e


def preview(objs, path, res=(1280, 720), samples=24, pitch=45.0, yaw=-20.0, fill=0.85, target=None, dist=None,
            sky=0.78, key=1.1, sun_angle=135.0, sun_elev=50.0, ink_px=1.2, ground=True, ss=1, cut=True):
    """Gongbi review render of ``objs`` (already imported) to ``path``: soft shadowless light,
    matte pigment, and ink drawn in post from the depth / normal buffers (contours ``ink_px`` px,
    creases lighter; leaf cards and the silk ground excluded through the NoInk AOV, tree masses
    outlined in ink-green), like Unreal's painted post-process.  ``cut``: drop the parts below
    z = 0 first (they are under the terrain in the game)."""
    import math as _m
    import os
    import numpy as np
    from . import post
    sc = bpy.context.scene
    if cut:
        for o in objs:
            cut_below(o)
    scene.setup_cycles(samples=samples, transparent=False, preset="sprite", view="Standard", look="None",
                       clamp_indirect=4.0)
    sc.cycles.max_bounces = 3
    sc.cycles.diffuse_bounces = 2
    sc.cycles.glossy_bounces = 0
    sc.cycles.transparent_max_bounces = 16
    sc.render.resolution_x, sc.render.resolution_y = res[0] * ss, res[1] * ss
    sc.render.resolution_percentage = 100
    sc.render.use_freestyle = False
    matte(objs)
    leafy = set()
    for o in objs:
        for m in o.data.materials:
            if m and m.name.startswith("Leaves") and m.name not in leafy:
                _noink_aov(m)
                leafy.add(m.name)
    cam = WR.game_camera(objs, pitch, yaw, fill=fill, target=target, dist=dist)
    lo, hi = WR._bounds(objs)
    if ground:
        size = max(hi.x - lo.x, hi.y - lo.y) * 14 + 300
        me = bpy.data.meshes.new("SilkGround")
        h = size / 2
        z = 0.0 if cut else (lo.z if lo.z > -0.01 else -0.02)
        me.from_pydata([(-h, -h, z), (h, -h, z), (h, h, z), (-h, h, z)], [], [(0, 1, 2, 3)])
        g = bpy.data.objects.new("SilkGround", me)
        sc.collection.objects.link(g)
        sm = silk_material()
        if not any(n.bl_idname == "ShaderNodeOutputAOV" for n in sm.node_tree.nodes):
            _noink_aov(sm, 0.5)
        me.materials.append(sm)
    w = bpy.data.worlds.new("SoftSky")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    bg.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    bg.inputs["Strength"].default_value = sky
    # camera rays see bare silk (the horizon of low views), everything else is lit by white sky
    lp = nt.nodes.new("ShaderNodeLightPath")
    bg2 = nt.nodes.new("ShaderNodeBackground")
    bg2.inputs["Color"].default_value = palette.lin4("#E6D8B8")
    bg2.inputs["Strength"].default_value = 1.0
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    nt.links.new(bg.outputs[0], mix.inputs[1])
    nt.links.new(bg2.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], nt.nodes["World Output"].inputs["Surface"])
    d = lights.screen_dir(cam, sun_angle, sun_elev)
    lights.sun("SoftKey", d, key, (1.0, 1.0, 1.0), 8.0, shadow=False)
    sc["ironart_seed"] = 7
    # passes for the ink
    vl = bpy.context.view_layer
    vl.use_pass_z = True
    vl.use_pass_normal = True
    if NOINK_AOV not in [a.name for a in vl.aovs]:
        a = vl.aovs.add()
        a.name = NOINK_AOV
        a.type = "VALUE"
    sc.use_nodes = True
    ct = sc.node_tree
    for n in list(ct.nodes):
        ct.nodes.remove(n)
    rl = ct.nodes.new("CompositorNodeRLayers")
    comp = ct.nodes.new("CompositorNodeComposite")
    ct.links.new(rl.outputs["Image"], comp.inputs["Image"])
    tmp = os.path.join(os.path.dirname(os.path.abspath(path)), "_passes")
    fo = ct.nodes.new("CompositorNodeOutputFile")
    fo.base_path = tmp
    fo.format.file_format = "OPEN_EXR"
    fo.format.color_depth = "32"
    fo.format.color_mode = "RGBA"
    fo.file_slots.clear()
    for slot, sock in (("depth", rl.outputs["Depth"]), ("normal", rl.outputs["Normal"]),
                       ("noink", rl.outputs[NOINK_AOV])):
        fo.file_slots.new(slot)
        ct.links.new(sock, fo.inputs[slot])
    secs = scene.render(path)
    depth = exr_pixels(os.path.join(tmp, "depth0001.exr"))[..., 0]
    normal = exr_pixels(os.path.join(tmp, "normal0001.exr"))
    ni = exr_pixels(os.path.join(tmp, "noink0001.exr"))[..., 0]
    noink = ni > 0.25
    rgb = post.load(path)[..., :3]
    H, W = depth.shape
    px_m = depth * 2.0 * _m.tan(cam.data.angle / 2.0) / float(max(W, H))
    valid = depth < 1e5
    solid = valid & ~noink
    fwd = cam.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))
    contour, crease = edge_lines(depth, normal, solid, valid, px_m, thr_px=2.0, thr_min=0.2, view_dir=tuple(fwd))
    # tree masses: the leaf region where it stands in front of what is behind it
    leaf = valid & (ni > 0.75)
    lc, _ = edge_lines(depth, normal, leaf, valid, px_m, thr_px=2.0, thr_min=0.2)
    rgb = post.srgb_to_linear(rgb)
    rgb = ink_over(rgb, crease, palette.lin("#3A2E26"), 0.7, ink_px * 1.1)
    rgb = ink_over(rgb, contour, palette.lin("#1E1A16"), 0.97, ink_px * 1.5)
    rgb = ink_over(rgb, lc, palette.lin("#1C3328"), 0.75, ink_px * 1.1)
    rgb = post.linear_to_srgb(np.clip(rgb, 0, 1))
    post.save(np.dstack([rgb, np.ones((H, W), np.float32)]), path, opaque=True)
    try:
        os.rmdir(tmp)
    except OSError:
        pass
    return secs
