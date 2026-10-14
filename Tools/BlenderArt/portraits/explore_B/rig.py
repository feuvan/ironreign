"""Scene, camera and the art-directed light rig (one light group per light for the compositor)."""

import math
import os

import bpy
from mathutils import Vector

from .nodes import lin


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.render.use_freestyle = False
    for vl in sc.view_layers:
        fs = vl.freestyle_settings
        while len(fs.linesets) > 0:
            fs.linesets.remove(fs.linesets[0])
    return sc


def cycles(samples=40, w=384, h=480, ss=2, adaptive=0.03, clamp_direct=0.0, clamp_indirect=3.0,
           threads=None, view="Filmic", look="Medium Contrast", exposure=0.0, transparent=True):
    sc = bpy.context.scene
    cy = sc.cycles
    cy.device = "CPU"
    cy.samples = samples
    cy.use_denoising = False
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = adaptive
    cy.adaptive_min_samples = max(8, samples // 6)
    cy.seed = 7
    cy.sample_clamp_direct = clamp_direct
    cy.sample_clamp_indirect = clamp_indirect
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.blur_glossy = 1.0
    cy.max_bounces = 4
    cy.diffuse_bounces = 1
    cy.glossy_bounces = 1
    cy.transmission_bounces = 2
    cy.transparent_max_bounces = 8
    cy.volume_bounces = 0
    cy.pixel_filter_type = "BLACKMAN_HARRIS"
    cy.filter_width = 1.5
    cy.use_auto_tile = True
    cy.tile_size = 512
    sc.render.film_transparent = transparent
    th = threads or os.environ.get("IRONART_THREADS")
    if th:
        sc.render.threads_mode = "FIXED"
        sc.render.threads = int(th)
    sc.render.resolution_x = w * ss
    sc.render.resolution_y = h * ss
    sc.render.resolution_percentage = 100
    sc["ss"] = ss
    sc.display_settings.display_device = "sRGB"
    sc.view_settings.view_transform = view
    sc.view_settings.look = look
    sc.view_settings.exposure = exposure
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.image_settings.color_depth = "8"
    sc.render.dither_intensity = 0.0
    try:
        sc.cycles_curves.shape = "RIBBONS"
        sc.cycles_curves.subdivisions = 2
    except AttributeError:
        pass
    return sc


def portrait_camera(eye_point, head_height=0.232, yaw_deg=22.0, pitch_deg=-3.0, focal_mm=85.0,
                    eye_line=0.38, head_frac=0.48, roll_deg=0.0):
    cd = bpy.data.cameras.new("Cam")
    cd.lens = focal_mm
    cd.sensor_fit = "VERTICAL"
    cd.sensor_height = 36.0
    cd.sensor_width = 36.0
    cd.clip_start = 0.05
    cd.clip_end = 50
    cam = bpy.data.objects.new("Cam", cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    half = math.atan(18.0 / focal_mm)
    dist = head_height / (head_frac * 2.0 * math.tan(half))
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    offs = Vector((math.sin(yaw) * math.cos(pitch), -math.cos(yaw) * math.cos(pitch), -math.sin(pitch)))
    cam.location = Vector(eye_point) + offs * dist
    q = (-offs).to_track_quat("-Z", "Y")
    cam.rotation_mode = "QUATERNION"
    if roll_deg:
        from mathutils import Quaternion
        q = q @ Quaternion((0, 0, 1), math.radians(roll_deg))
    cam.rotation_quaternion = q
    sc = bpy.context.scene
    aspect = sc.render.resolution_x / sc.render.resolution_y
    frac = 1.0 if aspect <= 1.0 else 1.0 / aspect
    cd.shift_y = -(0.5 - eye_line) * frac
    bpy.context.view_layer.update()
    cam["dist"] = dist
    return cam


def screen_dir(cam, angle_deg, elev_deg):
    m = cam.matrix_world.to_3x3()
    right, up, toward = m @ Vector((1, 0, 0)), m @ Vector((0, 1, 0)), m @ Vector((0, 0, 1))
    a, e = math.radians(angle_deg), math.radians(elev_deg)
    return ((right * math.cos(a) + up * math.sin(a)) * math.cos(e) + toward * math.sin(e)).normalized()


def world_to_px(cam, co):
    from bpy_extras.object_utils import world_to_camera_view
    sc = bpy.context.scene
    p = world_to_camera_view(sc, cam, Vector(co))
    return p.x * sc.render.resolution_x, (1 - p.y) * sc.render.resolution_y, p.z


def area_light(name, loc, target, power, size, size_y=None, color="#FFFFFF", shadow=True,
               spread=180.0, group=None):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = power
    ld.color = lin(color)[:3]
    ld.shape = "RECTANGLE" if size_y else "SQUARE"
    ld.size = size
    if size_y:
        ld.size_y = size_y
    ld.spread = math.radians(spread)
    ld.cycles.cast_shadow = shadow
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = Vector(loc)
    d = (Vector(target) - Vector(loc)).normalized()
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = d.to_track_quat("-Z", "Y")
    if group:
        ob.lightgroup = group
    return ob


def ensure_lightgroups(names):
    vl = bpy.context.view_layer
    have = {lg.name for lg in vl.lightgroups}
    for n in names:
        if n not in have:
            vl.lightgroups.add(name=n)


def light_rig(cam, target, key=46.0, fill=6.0, rim=34.0, rim2=10.0, bounce=3.0, world=0.05,
              key_angle=140.0, key_elev=30.0, key_size=0.45, key_color="#FFE6C8",
              fill_color="#8FA6CC", rim_color="#BFD4FF", rim2_color="#FFD7A8",
              bounce_color="#B07850", world_color="#40382F", dist=1.5):
    """Koei painted-bust lighting, every light in its own light group:

    key     warm soft area from the screen upper-left (140 deg, 30 deg towards the viewer)
    fill    broad cool fill from screen right, shadowless (keeps shadow sides readable, cool)
    rim     cool hard-ish strip from behind upper right: the blue edge on the shadow side
    rim2    warm kicker from behind upper left (hair / helmet edge on the lit side)
    bounce  warm low fill from below (armour/robe bounce under the chin)
    world   very dark warm ambient
    """
    t = Vector(target)
    groups = ["key", "fill", "rim", "rim2", "bounce", "world"]
    ensure_lightgroups(groups)
    rig = {}
    kd = screen_dir(cam, key_angle, key_elev)
    rig["key"] = area_light("Key", t + kd * dist, t, key, key_size, color=key_color, group="key")
    fd = screen_dir(cam, -10.0, 35.0)
    rig["fill"] = area_light("Fill", t + fd * dist * 1.3, t, fill, 1.8, color=fill_color, shadow=False,
                             group="fill")
    # the broad fill would paint every metal plate the same flat silver: diffuse only
    rig["fill"].visible_glossy = False
    rd = screen_dir(cam, 30.0, -50.0)
    rig["rim"] = area_light("Rim", t + rd * dist, t, rim, 0.25, 1.0, color=rim_color, group="rim")
    r2 = screen_dir(cam, 160.0, -45.0)
    rig["rim2"] = area_light("Rim2", t + r2 * dist, t, rim2, 0.3, 0.8, color=rim2_color, group="rim2")
    if bounce > 0:
        bd = screen_dir(cam, -95.0, 20.0)
        rig["bounce"] = area_light("Bounce", t + bd * dist + Vector((0, 0, -0.2)), t + Vector((0, 0, -0.1)),
                                   bounce, 1.0, color=bounce_color, shadow=False, group="bounce")
    w = bpy.data.worlds.new("World")
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = lin(world_color)
    bg.inputs[1].default_value = world
    w.lightgroup = "world"
    bpy.context.scene.world = w
    rig["key_dir"] = kd
    return rig
