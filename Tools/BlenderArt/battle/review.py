"""Gongbi review renders of the battle models (an approximation of Unreal's painted look:
soft shadowless light, matte pigment, ink from the depth / normal buffers, on silk).

:func:`preview` is :func:`ironart.world_gongbi_render.preview` with an explicit silk-ground
height (tiles sit on it with their skirts) and an explicit camera, so the same function renders
one tile, a unit, or a whole board patch from the game's board camera (FOV 38 deg, pitch 50).
"""

import math
import os

import bpy
import numpy as np
from mathutils import Vector

from ironart import lights, palette, post, scene
from ironart import world_gongbi_render as GR
from ironart import world_render as WR


def camera(objs=None, pitch=50.0, yaw=0.0, fov=38.0, fill=0.9, target=None, dist=None):
    if objs is None:
        objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    return WR.game_camera(objs, pitch, yaw, fov=fov, fill=fill, target=target, dist=dist)


def preview(objs, path, res=(960, 640), samples=16, cam=None, ground_z=-1.0, sky=0.78, key=1.1,
            sun_angle=135.0, sun_elev=50.0, ink_px=1.1, ss=1, ground=True, ortho=None):
    sc = bpy.context.scene
    scene.setup_cycles(samples=samples, transparent=False, preset="sprite", view="Standard", look="None",
                       clamp_indirect=4.0)
    sc.cycles.max_bounces = 3
    sc.cycles.diffuse_bounces = 2
    sc.cycles.glossy_bounces = 0
    sc.cycles.transparent_max_bounces = 8
    sc.render.resolution_x, sc.render.resolution_y = res[0] * ss, res[1] * ss
    sc.render.resolution_percentage = 100
    sc.render.use_freestyle = False
    GR.matte(objs)
    if cam is None:
        cam = camera(objs)
    sc.camera = cam
    if ground:
        me = bpy.data.meshes.new("SilkGround")
        h = 2000.0
        me.from_pydata([(-h, -h, ground_z), (h, -h, ground_z), (h, h, ground_z), (-h, h, ground_z)], [], [(0, 1, 2, 3)])
        g = bpy.data.objects.new("SilkGround", me)
        sc.collection.objects.link(g)
        sm = GR.silk_material()
        if not any(n.bl_idname == "ShaderNodeOutputAOV" for n in sm.node_tree.nodes):
            GR._noink_aov(sm, 0.5)
        me.materials.append(sm)
    w = bpy.data.worlds.new("SoftSky")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    bg.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    bg.inputs["Strength"].default_value = sky
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
    vl = bpy.context.view_layer
    vl.use_pass_z = True
    vl.use_pass_normal = True
    if GR.NOINK_AOV not in [a.name for a in vl.aovs]:
        a = vl.aovs.add()
        a.name = GR.NOINK_AOV
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
                       ("noink", rl.outputs[GR.NOINK_AOV])):
        fo.file_slots.new(slot)
        ct.links.new(sock, fo.inputs[slot])
    secs = scene.render(path)
    depth = GR.exr_pixels(os.path.join(tmp, "depth0001.exr"))[..., 0]
    normal = GR.exr_pixels(os.path.join(tmp, "normal0001.exr"))
    ni = GR.exr_pixels(os.path.join(tmp, "noink0001.exr"))[..., 0]
    noink = ni > 0.25
    rgb = post.load(path)[..., :3]
    H, W = depth.shape
    if cam.data.type == "ORTHO":
        px_m = np.full(depth.shape, cam.data.ortho_scale / float(max(W, H)), np.float32)
    else:
        px_m = depth * 2.0 * math.tan(cam.data.angle / 2.0) / float(max(W, H))
    valid = depth < 1e5
    solid = valid & ~noink
    fwd = cam.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))
    contour, crease = GR.edge_lines(depth, normal, solid, valid, px_m, thr_px=2.0, thr_min=0.12,
                                    view_dir=tuple(fwd))
    rgb = post.srgb_to_linear(rgb)
    rgb = GR.ink_over(rgb, crease, palette.lin("#3A2E26"), 0.6, ink_px * ss * 1.0)
    rgb = GR.ink_over(rgb, contour, palette.lin("#1E1A16"), 0.95, ink_px * ss * 1.4)
    rgb = post.linear_to_srgb(np.clip(rgb, 0, 1))
    img = np.dstack([rgb, np.ones((H, W), np.float32)])
    if ss > 1:
        img = post.downsample(img, ss)
    post.save(img, path, opaque=True)
    try:
        os.rmdir(tmp)
    except OSError:
        pass
    return secs


def tile_preview(objs, path, fast=False, pitch=50.0, yaw=-18.0, fill=0.92, res=(960, 640)):
    cam = camera(objs, pitch, yaw, fill=fill)
    return preview(objs, path, res=res, samples=10 if fast else 20, cam=cam, ground_z=-1.0)


def turntable(path_glb, out_png, yaws=(-30.0, 60.0, 150.0, 240.0), pitch=42.0, res=(480, 360), samples=10):
    """Re-import a GLB into a clean scene and render it from four sides (gongbi review look),
    side by side in one strip: the orientation / scale / material check of the export."""
    from ironart import scene as _scene
    from PIL import Image
    tiles = []
    for i, yaw in enumerate(yaws):
        _scene.reset(5)
        bpy.ops.import_scene.gltf(filepath=path_glb)
        objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
        for o in list(bpy.context.scene.objects):
            if o.type != "MESH":
                bpy.data.objects.remove(o)
        lo_z = min((o.matrix_world @ Vector(c)).z for o in objs for c in o.bound_box)
        cam = camera(objs, pitch=pitch, yaw=yaw, fill=0.9)
        tmp = out_png[:-4] + "_%d.png" % i
        preview(objs, tmp, res=res, samples=samples, cam=cam, ground_z=lo_z)
        tiles.append(Image.open(tmp).convert("RGB"))
        os.remove(tmp)
    strip = Image.new("RGB", (res[0] * len(tiles), res[1]))
    for i, t in enumerate(tiles):
        strip.paste(t, (i * res[0], 0))
    strip.save(out_png)
    return out_png
