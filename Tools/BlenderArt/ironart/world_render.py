"""World Models family: review renders of 3D models (not game assets) and 2D sprite renders.

``beauty`` / ``turntable`` approximate how the model reads in Unreal on the strategy map:
perspective camera with the game's 40 deg field of view at the game pitch (45-55 deg), the studio
sun from the top-left of the screen (``lights.SUN``), a Nishita sky for ambient, a terrain-like
ground that receives shadows and Filmic Medium Contrast (close to Unreal's filmic tonemapper).

``sprite`` renders the 2D fallbacks through the shared ``recipes`` (sprite / tint_plate).
"""

import math
import os
import time

import bpy
from mathutils import Vector

from . import lights, palette, scene
from .materials import NB


def _bounds(objs):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for o in objs:
        for c in o.bound_box:
            p = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, p))
            hi = Vector(map(max, hi, p))
    return lo, hi


def ground_material(name="PreviewGround", color="#6F7E4A", dry="#8E8460"):
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
    n1 = nb.noise(nb.mapping(o, scale=(0.02, 0.02, 0.02)), scale=1.0, detail=6, roughness=0.6)
    n2 = nb.noise(nb.mapping(o, scale=(0.3, 0.3, 0.3)), scale=1.0, detail=4)
    col = nb.ramp(n1.outputs["Fac"], [(0.35, color), (0.7, dry)])
    col = nb.mix(col, nb.ramp(n2.outputs["Fac"], [(0.3, (0.82, 0.82, 0.8, 1)), (0.7, (1.08, 1.08, 1.04, 1))]),
                 1.0, blend="MULTIPLY")
    p = nb.principled(Base_Color=col, Roughness=0.95, Specular_IOR_Level=0.3,
                      Normal=nb.bump(n2.outputs["Fac"], 0.3, 0.05))
    nb.output(p.outputs[0])
    return m


def sky_world(strength=0.9, sun_dir=None):
    w = bpy.data.worlds.get("PreviewSky") or bpy.data.worlds.new("PreviewSky")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_disc = False
    if sun_dir is not None:
        d = Vector(sun_dir).normalized()
        sky.sun_elevation = math.asin(max(0.05, d.z))
        sky.sun_rotation = math.atan2(d.x, d.y)
    sky.air_density = 1.0
    sky.dust_density = 2.0
    sky.ozone_density = 1.0
    bg.inputs["Strength"].default_value = strength * 0.08
    nt.links.new(sky.outputs[0], bg.inputs["Color"])
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    return w


def setup_beauty(samples=64, res=(1280, 720), ss=1):
    sc = bpy.context.scene
    scene.setup_cycles(samples=samples, transparent=False, preset="sprite", view="Filmic",
                       look="Medium Contrast", clamp_indirect=6.0)
    sc.cycles.max_bounces = 6
    sc.cycles.diffuse_bounces = 3
    sc.cycles.glossy_bounces = 2
    sc.cycles.transparent_max_bounces = 16
    sc.render.resolution_x, sc.render.resolution_y = res[0] * ss, res[1] * ss
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.use_nodes = False
    return sc


def game_camera(objs, pitch=50.0, yaw=-25.0, fov=40.0, fill=0.8, target=None, dist=None, name="CamGame"):
    """Perspective camera like the strategy camera: looking at the model from the front (-y)
    rotated by ``yaw`` deg, pitched down ``pitch`` deg, distance so the model fills ``fill`` of
    the frame width."""
    lo, hi = _bounds(objs)
    c = (lo + hi) / 2 if target is None else Vector(target)
    c.z = lo.z + (hi.z - lo.z) * 0.3 if target is None else c.z
    rad = max((hi - lo).length / 2, 1e-3)
    cd = bpy.data.cameras.new(name)
    cd.lens_unit = "FOV"
    cd.angle = math.radians(fov)
    cd.clip_start = 0.5
    cd.clip_end = 20000
    cam = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    if dist is None:
        dist = rad / math.tan(math.radians(fov) / 2) / fill
    p, y = math.radians(pitch), math.radians(yaw)
    off = Vector((math.sin(y) * math.cos(p), -math.cos(y) * math.cos(p), math.sin(p)))
    cam.location = c + off * dist
    cam.rotation_euler = (-off).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()
    return cam


def ground_plane(size, z=0.0):
    me = bpy.data.meshes.new("PreviewGround")
    h = size / 2
    me.from_pydata([(-h, -h, z), (h, -h, z), (h, h, z), (-h, h, z)], [], [(0, 1, 2, 3)])
    o = bpy.data.objects.new("PreviewGround", me)
    bpy.context.scene.collection.objects.link(o)
    me.materials.append(ground_material())
    return o


def beauty(objs, path, res=(1280, 720), samples=64, pitch=50.0, yaw=-25.0, fill=0.85,
           sun_angle=135.0, sun_elev=48.0, sun=4.2, sky=1.0, ground=True, ss=1, target=None, dist=None):
    """Daylight review render of ``objs`` as the strategy camera would see them."""
    sc = setup_beauty(samples, res, ss)
    cam = game_camera(objs, pitch, yaw, fill=fill, target=target, dist=dist)
    lo, hi = _bounds(objs)
    if ground:
        ground_plane(max(hi.x - lo.x, hi.y - lo.y) * 12 + 200, lo.z if lo.z > -0.01 else 0.0)
    d = lights.screen_dir(cam, sun_angle, sun_elev)
    lights.sun("PreviewSun", d, sun, "#FFF1DE", 1.2)
    sky_world(sky, d)
    t = scene.render(path)
    return t


def turntable(objs, path, res=(640, 400), samples=40, yaws=(-30, 30, 150, -150), pitch=50.0, fill=0.85,
              cols=2, label=True):
    """Contact sheet of ``yaws`` views (written to ``path``)."""
    import numpy as np
    from PIL import Image, ImageDraw
    tiles = []
    base = os.path.splitext(path)[0]
    sc = setup_beauty(samples, res)
    lo, hi = _bounds(objs)
    gp = ground_plane(max(hi.x - lo.x, hi.y - lo.y) * 12 + 200, 0.0)
    for k, yw in enumerate(yaws):
        cam = game_camera(objs, pitch, yw, fill=fill, name="CamTT%d" % k)
        for o in [o for o in bpy.context.scene.objects if o.type == "LIGHT"]:
            bpy.data.objects.remove(o, do_unlink=True)
        d = lights.screen_dir(cam, 135.0, 48.0)
        lights.sun("PreviewSun", d, 4.2, "#FFF1DE", 1.2)
        sky_world(1.0, d)
        p = "%s_%d.png" % (base, k)
        scene.render(p, quiet=True)
        im = Image.open(p).convert("RGB")
        if label:
            ImageDraw.Draw(im).text((8, 6), "yaw %+d" % yw, fill=(255, 255, 255))
        tiles.append(im)
        os.remove(p)
    w, h = tiles[0].size
    rows = int(math.ceil(len(tiles) / cols))
    sheet = Image.new("RGB", (w * cols, h * rows), (30, 26, 22))
    for k, im in enumerate(tiles):
        sheet.paste(im, ((k % cols) * w, (k // cols) * h))
    sheet.save(path)
    return path
