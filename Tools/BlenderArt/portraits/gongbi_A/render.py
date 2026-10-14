"""Scene, camera, Freestyle and pass output for the gongbi bust (Cycles CPU, no lighting)."""

import math
import os
import time

import bpy
import numpy as np

import shade

PASSES = ("Image", "paint", "tint", "shade", "ink", "mask", "Freestyle")


def setup(w, h, ss, samples=12, threads=None):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.device = "CPU"
    cy.samples = samples
    cy.use_adaptive_sampling = False
    cy.use_denoising = False
    cy.max_bounces = 1
    cy.diffuse_bounces = 1
    cy.glossy_bounces = 0
    cy.transmission_bounces = 0
    cy.transparent_max_bounces = 2
    cy.volume_bounces = 0
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.pixel_filter_type = "BLACKMAN_HARRIS"
    cy.filter_width = 1.5
    cy.use_auto_tile = True
    cy.tile_size = 512
    cy.seed = 7
    sc.render.film_transparent = True
    sc.render.resolution_x = w * ss
    sc.render.resolution_y = h * ss
    sc.render.resolution_percentage = 100
    sc["ss"] = ss
    th = threads or os.environ.get("IRONART_THREADS")
    if th:
        sc.render.threads_mode = "FIXED"
        sc.render.threads = int(th)
    sc.display_settings.display_device = "sRGB"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.use_compositing = True
    sc.render.use_sequencer = False
    shade.register_aovs(sc.view_layers[0])
    w0 = bpy.data.worlds.new("W")
    w0.use_nodes = True
    w0.node_tree.nodes["Background"].inputs[1].default_value = 0.0
    sc.world = w0
    return sc


def camera(center_x, eye_z, frame_h, eye_line=0.38, w=384, h=480):
    sc = bpy.context.scene
    cam = bpy.data.cameras.new("Cam")
    cam.type = "ORTHO"
    cam.sensor_fit = "VERTICAL"
    cam.ortho_scale = frame_h
    cam.clip_start = 0.1
    cam.clip_end = 10.0
    co = bpy.data.objects.new("Cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    co.rotation_euler = (math.radians(90), 0, 0)
    co.location = (center_x, -3.0, eye_z - (0.5 - eye_line) * frame_h)
    return co


def outputs(dirpath):
    """Compositor: render layer passes -> one EXR per pass in ``dirpath``."""
    sc = bpy.context.scene
    sc.use_nodes = True
    nt = sc.node_tree
    nt.nodes.clear()
    rl = nt.nodes.new("CompositorNodeRLayers")
    comp = nt.nodes.new("CompositorNodeComposite")
    nt.links.new(rl.outputs["Image"], comp.inputs["Image"])
    fo = nt.nodes.new("CompositorNodeOutputFile")
    fo.base_path = dirpath
    fo.format.file_format = "OPEN_EXR"
    fo.format.color_depth = "16"
    fo.format.exr_codec = "NONE"
    fo.format.color_mode = "RGBA"
    fo.file_slots.clear()
    for p in PASSES:
        if p not in rl.outputs:
            continue
        fo.file_slots.new(p + "_")
        nt.links.new(rl.outputs[p], fo.inputs[-1])
    return fo


def render(dirpath):
    sc = bpy.context.scene
    os.makedirs(dirpath, exist_ok=True)
    outputs(dirpath)
    sc.render.filepath = os.path.join(dirpath, "combined.png")
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    return time.time() - t0


def to_npz(dirpath, out):
    """EXR passes -> one float16 npz (read back through Blender's image loader)."""
    sc = bpy.context.scene
    W, H = sc.render.resolution_x, sc.render.resolution_y
    data = {}
    for p in PASSES:
        fn = None
        for f in os.listdir(dirpath):
            if f.startswith(p + "_") and f.endswith(".exr"):
                fn = os.path.join(dirpath, f)
        if fn is None:
            continue
        img = bpy.data.images.load(fn)
        a = np.empty(W * H * 4, np.float32)
        img.pixels.foreach_get(a)
        a = a.reshape(H, W, 4)[::-1]
        data[p] = a.astype(np.float16)
        bpy.data.images.remove(img)
    np.savez(out, **data)
    return out
