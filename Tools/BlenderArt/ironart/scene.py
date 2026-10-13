"""Scene setup, Cycles CPU configuration and render helpers.

Environment facts this module encodes (Blender 4.0.2 Ubuntu build, headless, no GPU):

* Only **Cycles on CPU** works. EEVEE / Workbench crash headless - never select them.
* **No OpenImageDenoise** in this build: denoising is always off. Fight noise with enough samples,
  adaptive sampling and supersampling (render at ``supersample`` x the target size, then
  Lanczos-downsample with :func:`ironart.post.downsample`).
* View transforms available: ``Standard``, ``Filmic`` (looks: 'None', 'Medium Contrast',
  'Medium High Contrast', 'High Contrast'...), ``AgX`` (looks 'AgX - Punchy' ...), 'Raw'.
  The enum reports ``NONE`` when listed headless, but assigning the names works.

Typical use::

    sc = scene.reset(seed=7)
    scene.setup_cycles(samples=64, transparent=True, preset="sprite")
    scene.set_resolution(96, 96, supersample=4)
    ...
    secs = scene.render("/tmp/out_4x.png")
"""

import contextlib
import math
import os
import random
import sys
import time

import bpy

#: Light-path presets.  "fast" for previews, "sprite" for small props, "map" for terrain,
#: "portrait" adds SSS/transmission depth for skin and hair.
LIGHT_PATHS = {
    "fast": dict(max_bounces=3, diffuse_bounces=1, glossy_bounces=1, transmission_bounces=2,
                 volume_bounces=0, transparent_max_bounces=8),
    "sprite": dict(max_bounces=4, diffuse_bounces=2, glossy_bounces=2, transmission_bounces=2,
                   volume_bounces=0, transparent_max_bounces=8),
    "map": dict(max_bounces=3, diffuse_bounces=2, glossy_bounces=1, transmission_bounces=1,
                volume_bounces=0, transparent_max_bounces=4),
    "portrait": dict(max_bounces=6, diffuse_bounces=3, glossy_bounces=3, transmission_bounces=4,
                     volume_bounces=0, transparent_max_bounces=32),
    "ui": dict(max_bounces=4, diffuse_bounces=2, glossy_bounces=3, transmission_bounces=1,
               volume_bounces=0, transparent_max_bounces=4),
}


def args():
    """Arguments after ``--`` on the Blender command line (what render.sh forwards)."""
    argv = sys.argv
    return argv[argv.index("--") + 1:] if "--" in argv else []


def seed_all(seed):
    """Seed python ``random`` and numpy (if present). Returns a ``random.Random`` for local use."""
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed & 0xFFFFFFFF)
    except ImportError:
        pass
    return random.Random(seed)


def reset(seed=0):
    """Load an *empty* factory scene (no cube/camera/light), metric units, frame 1.

    Also clears orphan data so repeated builds inside one process stay deterministic.
    Returns the active scene.
    """
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.frame_set(1)
    # the factory state renders EEVEE (crashes headless) and keeps a Freestyle line set without
    # a line style (segfaults): switch to Cycles now and drop the dangling line sets, so a script
    # that forgets setup_cycles()/ink.enable() fails loudly in render() instead of crashing.
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.render.use_freestyle = False
    for vl in sc.view_layers:
        fs = vl.freestyle_settings
        while len(fs.linesets) > 0:
            fs.linesets.remove(fs.linesets[0])
    seed_all(seed)
    sc["ironart_seed"] = seed
    return sc


def setup_cycles(samples=64, transparent=False, preset="sprite", view="Standard", look="None",
                 exposure=0.0, gamma=1.0, adaptive_threshold=0.01, seed=0, filter_width=1.5,
                 clamp_indirect=4.0, threads=None, scene=None):
    """Configure Cycles for CPU rendering with studio defaults.

    samples            max samples per pixel (adaptive sampling stops earlier on flat areas)
    transparent        film transparency (RGBA output with alpha) - sprites, icons, UI pieces
    preset             light-path preset key of :data:`LIGHT_PATHS`
    view, look         colour management: 'Standard' (palette colours exact; map, sprites, UI)
                       or 'Filmic' + 'Medium Contrast' (portraits); see :data:`VIEW_LOOKS`
    clamp_indirect     fireflies clamp (we have no denoiser)
    threads            fixed thread count, or ``$IRONART_THREADS``, or auto
    """
    sc = scene or bpy.context.scene
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.device = "CPU"
    cy.samples = samples
    cy.preview_samples = min(samples, 16)
    cy.use_denoising = False
    cy.use_preview_denoising = False
    cy.use_adaptive_sampling = adaptive_threshold is not None and adaptive_threshold > 0
    if cy.use_adaptive_sampling:
        cy.adaptive_threshold = adaptive_threshold
        cy.adaptive_min_samples = max(8, samples // 8)
    cy.seed = seed
    cy.use_animated_seed = False
    cy.sample_clamp_direct = 0.0
    cy.sample_clamp_indirect = clamp_indirect
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.blur_glossy = 1.0
    cy.pixel_filter_type = "BLACKMAN_HARRIS"
    cy.filter_width = filter_width
    for k, v in LIGHT_PATHS[preset].items():
        setattr(cy, k, v)
    cy.use_auto_tile = True
    cy.tile_size = 256
    sc.render.film_transparent = transparent
    try:
        cy.film_transparent_glass = False
    except AttributeError:
        pass
    th = threads or os.environ.get("IRONART_THREADS")
    if th:
        sc.render.threads_mode = "FIXED"
        sc.render.threads = int(th)
    else:
        sc.render.threads_mode = "AUTO"
    set_color_management(view, look, exposure, gamma, sc)
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA" if transparent else "RGB"
    sc.render.image_settings.color_depth = "8"
    sc.render.dither_intensity = 0.5
    sc.render.use_compositing = True
    sc.render.use_sequencer = False
    return sc


#: allowed view transforms and the looks that belong to them (Blender accepts a Filmic look on
#: the Standard view silently - we do not).  AgX exists in this build but is not a studio view.
VIEW_LOOKS = {
    "Standard": ("None",),
    "Filmic": ("None", "Very Low Contrast", "Low Contrast", "Medium Low Contrast",
               "Medium Contrast", "Medium High Contrast", "High Contrast", "Very High Contrast"),
}


def set_color_management(view="Standard", look="None", exposure=0.0, gamma=1.0, scene=None):
    """Display sRGB, view ``Standard`` or ``Filmic``; ``look`` must belong to the view."""
    if view not in VIEW_LOOKS:
        raise ValueError("view %r not allowed (use %s)" % (view, ", ".join(VIEW_LOOKS)))
    if look not in VIEW_LOOKS[view]:
        raise ValueError("look %r does not belong to view %r (allowed: %s)"
                         % (look, view, ", ".join(VIEW_LOOKS[view])))
    sc = scene or bpy.context.scene
    sc.display_settings.display_device = "sRGB"
    sc.view_settings.view_transform = view
    sc.view_settings.look = look
    sc.view_settings.exposure = exposure
    sc.view_settings.gamma = gamma
    sc.sequencer_colorspace_settings.name = "sRGB"


def set_resolution(width, height, supersample=2, scene=None):
    """Set the render size to ``supersample`` x the *target* asset size.

    Returns the actual render size. Downsample afterwards with ``post.downsample(img, supersample)``.
    """
    if int(supersample) != supersample or supersample < 1:
        raise ValueError("supersample must be a positive integer (got %r): a fractional factor "
                         "renders a size the downsample silently rounds" % (supersample,))
    supersample = int(supersample)
    sc = scene or bpy.context.scene
    sc.render.resolution_x = int(round(width * supersample))
    sc.render.resolution_y = int(round(height * supersample))
    sc.render.resolution_percentage = 100
    sc.render.pixel_aspect_x = 1.0
    sc.render.pixel_aspect_y = 1.0
    sc["ironart_target"] = (int(width), int(height))
    sc["ironart_supersample"] = supersample
    return sc.render.resolution_x, sc.render.resolution_y


def supersample_factor(scene=None):
    """Integer supersample factor set by :func:`set_resolution` (1 if never set)."""
    sc = scene or bpy.context.scene
    return int(sc.get("ironart_supersample", 1))


def render(path, scene=None, quiet=False):
    """Render the active camera to ``path`` (PNG). Returns elapsed seconds.

    The compositor (if enabled with nodes) runs as part of the render; File Output nodes write
    their passes next to ``path`` (see :func:`ironart.post.comp_outputs`).
    """
    sc = scene or bpy.context.scene
    check_render_settings(sc)
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    sc.render.filepath = path
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    secs = time.time() - t0
    if not quiet:
        print("[ironart] rendered %s (%dx%d, %d spp) in %.2fs" % (
            os.path.basename(path), sc.render.resolution_x, sc.render.resolution_y,
            sc.cycles.samples, secs))
    return secs


def check_render_settings(scene=None):
    """Assert the only render configuration that works on this machine (called by :func:`render`):
    Cycles on CPU, no denoiser, Standard/Filmic view, Freestyle line sets all have a line style."""
    sc = scene or bpy.context.scene
    if sc.camera is None:
        raise RuntimeError("scene has no camera")
    if sc.render.engine != "CYCLES":
        raise RuntimeError("render engine is %s: only CYCLES works headless (call "
                           "scene.setup_cycles)" % sc.render.engine)
    if sc.cycles.device != "CPU":
        raise RuntimeError("Cycles device must be CPU")
    if sc.cycles.use_denoising:
        raise RuntimeError("denoising is on but this build has no OpenImageDenoise")
    vt = sc.view_settings.view_transform
    if vt not in VIEW_LOOKS or sc.view_settings.look not in VIEW_LOOKS[vt]:
        raise RuntimeError("colour management %r / %r not allowed" % (vt, sc.view_settings.look))
    if sc.render.use_freestyle:
        for vl in sc.view_layers:
            for ls in vl.freestyle_settings.linesets:
                if ls.linestyle is None:
                    raise RuntimeError("Freestyle line set %r has no line style (segfaults): use "
                                       "ink.enable()" % ls.name)


@contextlib.contextmanager
def timer(label, sink=None):
    """``with scene.timer('build'):`` prints the elapsed time; stores it in ``sink[label]``."""
    t0 = time.time()
    try:
        yield
    finally:
        dt = time.time() - t0
        print("[ironart] %-24s %.2fs" % (label, dt))
        if sink is not None:
            sink[label] = dt


# ---------------------------------------------------------------------------------------------
# object helpers
# ---------------------------------------------------------------------------------------------
def collection(name, parent=None):
    """Get or create a collection linked under ``parent`` (default: scene collection)."""
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(col)
    return col


def link(obj, col=None):
    (col or bpy.context.scene.collection).objects.link(obj)
    return obj


def mesh_object(name, mesh, col=None, location=(0, 0, 0)):
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    return link(obj, col)


def empty(name, location=(0, 0, 0), col=None):
    obj = bpy.data.objects.new(name, None)
    obj.location = location
    return link(obj, col)


def shade_smooth(obj, auto_smooth_deg=35.0):
    """Smooth-shade all faces; keep edges sharper than ``auto_smooth_deg`` crisp (None = all smooth)."""
    me = obj.data
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    if auto_smooth_deg is not None:
        me.use_auto_smooth = True
        me.auto_smooth_angle = math.radians(auto_smooth_deg)
    me.update()
    return obj


def shade_flat(obj):
    me = obj.data
    me.polygons.foreach_set("use_smooth", [False] * len(me.polygons))
    me.update()
    return obj


def add_modifier(obj, kind, name=None, **props):
    """Add a modifier and set attributes, e.g. ``add_modifier(o, 'BEVEL', width=0.02, segments=2)``."""
    m = obj.modifiers.new(name or kind.title(), kind)
    for k, v in props.items():
        setattr(m, k, v)
    return m


def apply_modifiers(obj):
    """Apply every modifier of ``obj`` (evaluated mesh replaces the data)."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev)
    old = obj.data
    obj.modifiers.clear()
    obj.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return obj


def select_only(obj):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def delete(obj):
    bpy.data.objects.remove(obj, do_unlink=True)


def world_bounds(objs):
    """Axis-aligned world bounds ``(min_xyz, max_xyz)`` of evaluated objects (modifiers included)."""
    from mathutils import Vector
    dg = bpy.context.evaluated_depsgraph_get()
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for o in objs:
        ev = o.evaluated_get(dg)
        for c in ev.bound_box:
            w = ev.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
    return lo, hi
