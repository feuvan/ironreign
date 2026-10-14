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


def preview(objs, path, res=(1280, 720), samples=24, pitch=45.0, yaw=-20.0, fill=0.85, target=None, dist=None,
            sky=0.78, key=1.1, sun_angle=135.0, sun_elev=50.0, ink_px=1.2, ground=True, ss=1, cut=True):
    """Gongbi review render of ``objs`` (already imported) to ``path``.  ``cut``: drop the parts
    below z = 0 first (they are under the terrain in the game)."""
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
    sc.use_nodes = False
    matte(objs)
    for o in objs:
        mark_no_ink(o)
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
        me.materials.append(silk_material())
        mark_no_ink(g)
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
    ink_lines(ink_px * ss)
    return scene.render(path)
