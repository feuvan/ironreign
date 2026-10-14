"""Camera, cinematic three-point light rig, Cycles settings and compositor pass outputs (bpy)."""

import math
import os

import bpy
from mathutils import Vector

# pass indices used by the compositor masks
PASS = {"skin": 1, "eyes": 2, "hair": 3, "metal": 4, "cloth": 5, "fur": 6, "orn": 7, "brow": 8}


def setup_render(w=384, h=480, ss=2, samples=96, threshold=0.02, view="Filmic", look="Medium High Contrast",
                 exposure=0.0, threads=None):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.device = "CPU"
    cy.samples = samples
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = threshold
    cy.adaptive_min_samples = 24
    cy.use_denoising = False
    cy.max_bounces = 4
    cy.diffuse_bounces = 1
    cy.glossy_bounces = 2
    cy.transmission_bounces = 2
    cy.transparent_max_bounces = 6
    cy.volume_bounces = 0
    cy.sample_clamp_direct = 0.0
    cy.sample_clamp_indirect = 3.0
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.blur_glossy = 1.0
    cy.pixel_filter_type = "BLACKMAN_HARRIS"
    cy.filter_width = 1.5
    cy.use_auto_tile = True
    cy.tile_size = 2048
    cy.seed = 7
    try:
        sc.cycles_curves.shape = "RIBBONS"
        sc.cycles_curves.subdivisions = 2
    except AttributeError:
        pass
    sc.render.film_transparent = True
    sc.render.resolution_x = w * ss
    sc.render.resolution_y = h * ss
    sc.render.resolution_percentage = 100
    th = threads or os.environ.get("IRONART_THREADS")
    if th:
        sc.render.threads_mode = "FIXED"
        sc.render.threads = int(th)
    sc.display_settings.display_device = "sRGB"
    sc.view_settings.view_transform = view
    sc.view_settings.look = look
    sc.view_settings.exposure = exposure
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.image_settings.color_depth = "8"
    sc.render.dither_intensity = 0.0
    vl = sc.view_layers[0]
    vl.use_pass_object_index = True
    vl.use_pass_z = True
    vl.use_pass_normal = True
    vl.use_pass_diffuse_color = True
    return sc


def camera(lm, yaw=20.0, pitch=-3.0, head_frac=0.47, eye_line=0.38, focal=85.0, x_off=0.0,
           head_height=None, dof=None):
    """85 mm bust camera.  The eye point lands at ``eye_line`` from the top; the chin-to-crown
    height fills ``head_frac`` of the frame.  ``yaw`` > 0 puts the camera on the subject's left
    (the face turns toward screen-left, into the key)."""
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cd.lens = focal
    cd.sensor_fit = "VERTICAL"
    cd.sensor_height = 36.0
    cd.sensor_width = 36.0
    eye = Vector(lm["eye_c"])
    hh = head_height or float(lm["crown"][2] - lm["chin"][2])
    half = math.atan(18.0 / focal)
    dist = hh / (head_frac * 2.0 * math.tan(half))
    yw, pt = math.radians(yaw), math.radians(pitch)
    offs = Vector((math.sin(yw) * math.cos(pt), -math.cos(yw) * math.cos(pt), -math.sin(pt)))
    cam.location = eye + offs * dist
    cam.rotation_euler = (-offs).to_track_quat("-Z", "Y").to_euler()
    cd.shift_y = -(0.5 - eye_line)
    cd.shift_x = x_off
    cd.clip_start = 0.05
    cd.clip_end = 20
    if dof:
        cd.dof.use_dof = True
        cd.dof.focus_distance = dist
        cd.dof.aperture_fstop = dof
        cd.dof.aperture_blades = 0
    bpy.context.view_layer.update()
    cam["dist"] = dist
    return cam


def screen_dir(cam, angle_deg, elev_deg):
    """Unit vector from the subject toward a light placed at screen angle (CCW from screen-right)
    and elevation toward the viewer (negative = behind the subject)."""
    m = cam.matrix_world
    right = (m.to_3x3() @ Vector((1, 0, 0))).normalized()
    up = (m.to_3x3() @ Vector((0, 1, 0))).normalized()
    toward = (m.to_3x3() @ Vector((0, 0, 1))).normalized()
    a, e = math.radians(angle_deg), math.radians(elev_deg)
    d = (right * math.cos(a) + up * math.sin(a)) * math.cos(e) + toward * math.sin(e)
    return d.normalized()


def _area(name, pos, target, power, size, size_y=None, color=(1, 1, 1), shadow=True, spread=180):
    L = bpy.data.lights.new(name, "AREA")
    L.energy = power
    L.color = color
    if size_y:
        L.shape = "RECTANGLE"
        L.size = size
        L.size_y = size_y
    else:
        L.shape = "DISK"
        L.size = size
    L.cycles.cast_shadow = shadow
    L.spread = math.radians(spread)
    o = bpy.data.objects.new(name, L)
    bpy.context.scene.collection.objects.link(o)
    o.location = pos
    o.rotation_euler = (Vector(target) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
    return o


KEY_WARM = (1.0, 0.80, 0.60)
FILL_COOL = (0.62, 0.74, 1.0)
RIM_COOL = (0.70, 0.82, 1.0)
BOUNCE_WARM = (1.0, 0.66, 0.42)


def lights(cam, target, key=62.0, fill=1.2, rim=70.0, kicker=10.0, bounce=1.2, key_angle=160.0,
           key_elev=5.0, key_size=0.32, dist=1.5, world=0.008, eyes=None, eye_light=3.0):
    t = Vector(target)
    rig = {}
    rig["key"] = _area("Key", t + screen_dir(cam, key_angle, key_elev) * dist, t, key, key_size,
                       color=KEY_WARM)
    rig["fill"] = _area("Fill", t + screen_dir(cam, -8.0, 30.0) * dist * 1.3, t, fill, 1.8,
                        color=FILL_COOL, shadow=False)
    # cool rim from behind-right-above: edges the shadow side of the face, beard and helmet
    rig["rim"] = _area("Rim", t + screen_dir(cam, 28.0, -52.0) * dist, t + Vector((0, 0, 0.02)), rim,
                       0.35, size_y=1.0, color=RIM_COOL)
    # warm kicker from behind-left: separates hair/helmet on the lit side
    if kicker:
        rig["kick"] = _area("Kick", t + screen_dir(cam, 150.0, -48.0) * dist, t, kicker, 0.4,
                            color=(1.0, 0.78, 0.55))
    if bounce:
        rig["bounce"] = _area("Bounce", t + screen_dir(cam, -95.0, 20.0) * dist + Vector((0, 0, -0.2)),
                              t + Vector((0, 0, -0.1)), bounce, 1.0, color=BOUNCE_WARM, shadow=False)
    wd = bpy.data.worlds.new("World")
    if eyes:
        # catchlight: a small soft light by the camera that only the eyeballs see (light linking)
        col = bpy.data.collections.new("EyeLightReceivers")
        for e in eyes:
            col.objects.link(e)
        cpos = cam.location + (cam.matrix_world.to_3x3() @ Vector((-0.12, 0.18, 0.0)))
        el = _area("EyeLight", cpos, t, eye_light, 0.035, color=(1.0, 0.92, 0.82))
        el.light_linking.receiver_collection = col
        rig["eye"] = el
    wd.use_nodes = True
    bg = wd.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.20, 0.17, 0.14, 1)
    bg.inputs[1].default_value = world
    bpy.context.scene.world = wd
    return rig


def compositor(outdir, tag, masks=("skin", "eyes", "hair", "metal", "cloth", "fur", "orn", "brow")):
    """File outputs: <tag>_beauty (RGBA, view transform), <tag>_m_<name> masks (Standard view),
    <tag>_depth (normalised depth)."""
    sc = bpy.context.scene
    sc.use_nodes = True
    nt = sc.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    rl = nt.nodes.new("CompositorNodeRLayers")
    comp = nt.nodes.new("CompositorNodeComposite")
    nt.links.new(rl.outputs["Image"], comp.inputs["Image"])
    nt.links.new(rl.outputs["Alpha"], comp.inputs["Alpha"])
    fo = nt.nodes.new("CompositorNodeOutputFile")
    fo.base_path = outdir
    fo.format.file_format = "PNG"
    fo.format.color_mode = "BW"
    fo.format.color_depth = "8"
    try:
        fo.format.color_management = "OVERRIDE"
        fo.format.view_settings.view_transform = "Standard"
    except Exception:
        pass
    fo.file_slots.clear()
    for name in masks:
        idm = nt.nodes.new("CompositorNodeIDMask")
        idm.index = PASS[name]
        idm.use_antialiasing = True
        nt.links.new(rl.outputs["IndexOB"], idm.inputs[0])
        slot = "%s_m_%s" % (tag, name)
        fo.file_slots.new(slot)
        nt.links.new(idm.outputs[0], fo.inputs[slot])
    # alpha
    fo.file_slots.new("%s_m_alpha" % tag)
    nt.links.new(rl.outputs["Alpha"], fo.inputs["%s_m_alpha" % tag])
    # depth: map 0.6 .. 2.6 m to 0..1
    mr = nt.nodes.new("CompositorNodeMapRange")
    mr.inputs[1].default_value = 0.6
    mr.inputs[2].default_value = 2.6
    mr.inputs[3].default_value = 0.0
    mr.inputs[4].default_value = 1.0
    mr.use_clamp = True
    nt.links.new(rl.outputs["Depth"], mr.inputs[0])
    fo.file_slots.new("%s_depth" % tag)
    nt.links.new(mr.outputs[0], fo.inputs["%s_depth" % tag])
    # normals (camera-independent world normals -> 0..1)
    fo2 = nt.nodes.new("CompositorNodeOutputFile")
    fo2.base_path = outdir
    fo2.format.file_format = "PNG"
    fo2.format.color_mode = "RGB"
    fo2.format.color_depth = "8"
    try:
        fo2.format.color_management = "OVERRIDE"
        fo2.format.view_settings.view_transform = "Standard"
    except Exception:
        pass
    fo2.file_slots.clear()
    mx = nt.nodes.new("CompositorNodeMixRGB")
    mx.blend_type = "MULTIPLY"
    mx.inputs[0].default_value = 1.0
    mx.inputs[2].default_value = (0.5, 0.5, 0.5, 1)
    nt.links.new(rl.outputs["Normal"], mx.inputs[1])
    add = nt.nodes.new("CompositorNodeMixRGB")
    add.blend_type = "ADD"
    add.inputs[0].default_value = 1.0
    add.inputs[2].default_value = (0.5, 0.5, 0.5, 1)
    nt.links.new(mx.outputs[0], add.inputs[1])
    fo2.file_slots.new("%s_normal" % tag)
    nt.links.new(add.outputs[0], fo2.inputs["%s_normal" % tag])
    fo2.file_slots.new("%s_albedo" % tag)
    nt.links.new(rl.outputs["DiffCol"], fo2.inputs["%s_albedo" % tag])
    return nt


def render(path):
    sc = bpy.context.scene
    sc.render.filepath = path
    import time
    t = time.time()
    bpy.ops.render.render(write_still=True)
    return time.time() - t
