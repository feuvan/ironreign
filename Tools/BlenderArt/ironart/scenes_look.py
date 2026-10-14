"""Illustrated Scenes family (Title background, event illustrations, duel background): the look.

This is the family recipe module for the *painted-realism key art* look (modern Koei key art:
Romance of the Three Kingdoms XIV / 8 Remake).  It adds a new family next to the ones in
:mod:`ironart.recipes` without changing them:

* **Render**: Cycles CPU, Filmic / Medium Contrast, path-traced at the @2x master size (the 1x
  game asset is a Lanczos downsample, i.e. 4 samples per output pixel on top of the spp).
* **Atmosphere** (:mod:`ironart.scenes_sky`): an art-directed sky dome with perspective cloud decks,
  sun / moon discs, stars and comets, plus in-shader aerial perspective and valley mist (exponential
  height fog whose colour is the sky along the view ray) on every material, and real volumes only
  where light shafts must be seen (throne hall).
* **Compositor**: sun-beam light shafts from the sun position, fog-glow bloom, a light anisotropic
  Kuwahara "brush" pass (strokes in master pixels) mixed over the clean render.
* **Finish** (numpy, 16-bit master): split-tone grade, saturation, clarity (large-radius local
  contrast), canvas grain, vignette, final sharpen, dithered 8-bit output.

No Freestyle ink: modern key art is painted, not outlined.

Every look number of this family lives in :data:`RECIPE` (and in the per-scene ``grade`` dicts of
``Tools/BlenderArt/scenes/sc_*.py``).
"""

import math
import os
import time

import numpy as np

#: the family recipe (master = @2x size; 1x = Lanczos downsample)
RECIPE = dict(
    view="Filmic", look="Medium Contrast",
    spp=32, preview_spp=12, adaptive_threshold=0.02,
    light_paths=dict(max_bounces=4, diffuse_bounces=2, glossy_bounces=1, transmission_bounces=2,
                     volume_bounces=0, transparent_max_bounces=24),
    clamp_direct=0.0, clamp_indirect=5.0, filter_width=1.5,
    # compositor brush pass (sizes in MASTER px; scaled with the render)
    kuwahara=dict(size=1.6, far_size=3.4, near_m=40.0, far_m=1500.0, sharpness=0.8,
                  eccentricity=1.0, uniformity=4, amount=0.6),
    glow=dict(threshold=1.0, mix=-0.86, size=8),
    beams=dict(ray_length=0.18, strength=0.30, threshold=1.6),
    # numpy finish defaults (scene grades override)
    grade=dict(saturation=1.04, contrast=1.04, pivot=0.45, shadows=(0.0, 0.0, 0.0),
               highlights=(0.0, 0.0, 0.0), clarity=0.10, clarity_px=40, canvas=0.022,
               vignette=0.20, sharpen=0.30),
)

#: art root (Content/Data) and master root (ArtSource)
_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
ART_SOURCE = os.path.join(REPO, "ArtSource")


# =============================================================================================
# render settings
# =============================================================================================
def setup(w, h, ss=1, spp=None, preview=False, seed=0, light_paths=None, **over):
    """Cycles CPU + Filmic for a ``w`` x ``h`` master rendered at ``ss`` x.  Returns the recipe.
    ``light_paths`` overrides individual bounce limits (interiors want more diffuse bounces)."""
    import bpy
    from . import scene
    r = dict(RECIPE)
    r.update(over)
    r["light_paths"] = dict(RECIPE["light_paths"], **(light_paths or {}))
    samples = spp or (r["preview_spp"] if preview else r["spp"])
    sc = scene.setup_cycles(samples=samples, transparent=False, preset="portrait", view=r["view"],
                            look=r["look"], adaptive_threshold=r["adaptive_threshold"], seed=seed,
                            filter_width=r["filter_width"], clamp_indirect=r["clamp_indirect"])
    for k, v in r["light_paths"].items():
        setattr(sc.cycles, k, v)
    sc.cycles.sample_clamp_direct = r["clamp_direct"]
    sc.cycles.volume_step_rate = 4.0 if preview else 2.0
    sc.cycles.volume_max_steps = 256
    sc.cycles.use_light_tree = True
    scene.set_resolution(w, h, ss)
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.image_settings.color_depth = "16"
    sc.render.dither_intensity = 0.0
    sc.view_layers[0].use_pass_z = True
    r["size"] = (w, h)
    r["ss"] = ss
    r["samples"] = samples
    r["preview"] = preview
    return r


def camera(location, target, focal_mm=35.0, sensor=36.0, roll_deg=0.0, dof=None, name="Cam",
           shift=(0.0, 0.0), clip=(0.1, 20000.0)):
    """Perspective camera at ``location`` looking at ``target`` (world +Z is screen-up).

    ``dof`` = (focus_distance_m or a world point, f_stop) enables Cycles depth of field.
    """
    import bpy
    from mathutils import Vector
    cd = bpy.data.cameras.new(name)
    cd.type = "PERSP"
    cd.lens = focal_mm
    cd.sensor_fit = "HORIZONTAL"
    cd.sensor_width = sensor
    cd.clip_start, cd.clip_end = clip
    cd.shift_x, cd.shift_y = shift
    cam = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    cam.location = location
    d = Vector(target) - Vector(location)
    q = d.to_track_quat("-Z", "Y")
    cam.rotation_mode = "XYZ"
    cam.rotation_euler = q.to_euler()
    if roll_deg:
        cam.rotation_euler.rotate_axis("Z", math.radians(roll_deg))
    if dof is not None:
        focus, fstop = dof
        cd.dof.use_dof = True
        if isinstance(focus, (int, float)):
            cd.dof.focus_distance = float(focus)
        else:
            cd.dof.focus_distance = (Vector(focus) - Vector(location)).length
        cd.dof.aperture_fstop = fstop
        cd.dof.aperture_blades = 7
    bpy.context.view_layer.update()
    return cam


def screen_pos(cam, co):
    """Normalised screen position (x right, y up, 0..1) of world point ``co`` (for sun beams)."""
    import bpy
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector
    p = world_to_camera_view(bpy.context.scene, cam, Vector(co))
    return float(p.x), float(p.y), float(p.z)


# =============================================================================================
# compositor
# =============================================================================================
def compositor(r, beams_source=None, beams=None, glow=None, kuwahara=None, lens=0.0, source=None,
               scene=None, depth=None):
    """[Render Layers | ``source`` image node] -> [sun beams] -> [fog glow] -> Kuwahara brush
    mix -> Composite.  ``beams_source`` = (x, y) normalised screen position of the sun / light
    (None = no beams).  All sizes in master px (scaled by ``r['ss']``)."""
    import bpy
    sc = scene or bpy.context.scene
    sc.use_nodes = True
    sc.render.use_compositing = True
    nt = sc.node_tree
    nt.nodes.clear()
    L = nt.links
    if source is None:
        rl = nt.nodes.new("CompositorNodeRLayers")
        cur = rl.outputs["Image"]
    else:
        im = nt.nodes.new("CompositorNodeImage")
        im.image = source
        cur = im.outputs["Image"]
    comp = nt.nodes.new("CompositorNodeComposite")
    comp.use_alpha = False
    ss = r["ss"]
    b = dict(RECIPE["beams"])
    b.update(beams or {})
    if beams_source is not None and b.get("strength", 0) > 0:
        # bright-pass -> radial sun beams -> add (screen) over the image
        bw = nt.nodes.new("CompositorNodeRGBToBW")
        L.new(cur, bw.inputs[0])
        thr = nt.nodes.new("CompositorNodeMath")
        thr.operation = "SUBTRACT"
        thr.use_clamp = True
        L.new(bw.outputs[0], thr.inputs[0])
        thr.inputs[1].default_value = b["threshold"]
        msk = nt.nodes.new("CompositorNodeMixRGB")
        msk.blend_type = "MULTIPLY"
        msk.inputs[0].default_value = 1.0
        L.new(cur, msk.inputs[1])
        L.new(thr.outputs[0], msk.inputs[2])
        sb = nt.nodes.new("CompositorNodeSunBeams")
        sb.source = (float(beams_source[0]), float(beams_source[1]))
        sb.ray_length = b["ray_length"]
        L.new(msk.outputs[0], sb.inputs[0])
        add = nt.nodes.new("CompositorNodeMixRGB")
        add.blend_type = "ADD"
        add.inputs[0].default_value = b["strength"]
        L.new(cur, add.inputs[1])
        L.new(sb.outputs[0], add.inputs[2])
        cur = add.outputs[0]
    g = dict(RECIPE["glow"])
    g.update(glow or {})
    if g.get("mix", -1) > -1:
        gl = nt.nodes.new("CompositorNodeGlare")
        gl.glare_type = "FOG_GLOW"
        gl.quality = "HIGH"
        gl.threshold = g["threshold"]
        gl.mix = g["mix"]
        gl.size = int(min(9, max(6, g["size"] + (1 if ss > 1 else 0))))
        L.new(cur, gl.inputs[0])
        cur = gl.outputs[0]
    k = dict(RECIPE["kuwahara"])
    k.update(kuwahara or {})
    if k.get("amount", 0) > 0 and k.get("size", 0) > 0:
        def kuwa(size):
            kn = nt.nodes.new("CompositorNodeKuwahara")
            kn.variation = "ANISOTROPIC"
            kn.size = max(1, int(round(size * ss * r.get("brush_scale", 1.0))))
            kn.uniformity = int(k["uniformity"])
            kn.sharpness = k["sharpness"]
            kn.eccentricity = k["eccentricity"]
            L.new(cur, kn.inputs[0])
            return kn.outputs[0]
        painted = kuwa(k["size"])
        if depth is not None and k.get("far_size"):
            # painters simplify the distance: bigger strokes with depth
            far = kuwa(k["far_size"])
            dn = nt.nodes.new("CompositorNodeImage")
            dn.image = depth
            mr = nt.nodes.new("CompositorNodeMapRange")
            mr.use_clamp = True
            L.new(dn.outputs["Image"], mr.inputs["Value"])
            mr.inputs["From Min"].default_value = k.get("near_m", 30.0)
            mr.inputs["From Max"].default_value = k.get("far_m", 1500.0)
            mr.inputs["To Min"].default_value = 0.0
            mr.inputs["To Max"].default_value = 1.0
            md = nt.nodes.new("CompositorNodeMixRGB")
            md.blend_type = "MIX"
            L.new(mr.outputs[0], md.inputs[0])
            L.new(painted, md.inputs[1])
            L.new(far, md.inputs[2])
            painted = md.outputs[0]
        mx = nt.nodes.new("CompositorNodeMixRGB")
        mx.blend_type = "MIX"
        mx.inputs[0].default_value = k["amount"]
        L.new(cur, mx.inputs[1])
        L.new(painted, mx.inputs[2])
        cur = mx.outputs[0]
    if lens:
        ld = nt.nodes.new("CompositorNodeLensdist")
        ld.use_fit = True
        ld.inputs["Dispersion"].default_value = lens
        L.new(cur, ld.inputs["Image"])
        cur = ld.outputs[0]
    L.new(cur, comp.inputs["Image"])
    return nt


def passes_compositor(out_dir):
    """Stage 1 compositor: write the raw beauty and the denoising guides as float EXRs
    (``beauty0001.exr``, ``albedo0001.exr``, ``normal0001.exr``, ``depth0001.exr``)."""
    import bpy
    sc = bpy.context.scene
    vl = sc.view_layers[0]
    vl.cycles.denoising_store_passes = True
    vl.use_pass_z = True
    sc.use_nodes = True
    sc.render.use_compositing = True
    nt = sc.node_tree
    nt.nodes.clear()
    rl = nt.nodes.new("CompositorNodeRLayers")
    comp = nt.nodes.new("CompositorNodeComposite")
    nt.links.new(rl.outputs["Image"], comp.inputs["Image"])
    fo = nt.nodes.new("CompositorNodeOutputFile")
    fo.base_path = out_dir
    fo.format.file_format = "OPEN_EXR"
    fo.format.color_depth = "32"
    fo.format.exr_codec = "ZIP"
    fo.file_slots.clear()
    for name, sock in (("beauty", "Image"), ("albedo", "Denoising Albedo"),
                       ("normal", "Denoising Normal"), ("depth", "Depth")):
        fo.file_slots.new(name)
        nt.links.new(rl.outputs[sock], fo.inputs[name])
    return fo


def post_render(exr_path, out_png, r, depth_path=None, **comp_kw):
    """Stage 3: run the painterly compositor on the denoised linear EXR in a throw-away scene
    (1 spp, no objects) and write the Filmic display-referred 16-bit PNG."""
    import bpy
    main = bpy.context.scene
    ps = bpy.data.scenes.new("IR_Post")
    ps.render.engine = "CYCLES"
    ps.cycles.device = "CPU"
    ps.cycles.samples = 1
    ps.cycles.use_denoising = False
    ps.cycles.use_adaptive_sampling = False
    ps.render.resolution_x = main.render.resolution_x
    ps.render.resolution_y = main.render.resolution_y
    ps.render.resolution_percentage = 100
    ps.display_settings.display_device = "sRGB"
    ps.view_settings.view_transform = main.view_settings.view_transform
    ps.view_settings.look = main.view_settings.look
    ps.view_settings.exposure = main.view_settings.exposure
    ps.render.image_settings.file_format = "PNG"
    ps.render.image_settings.color_mode = "RGB"
    ps.render.image_settings.color_depth = "16"
    ps.render.dither_intensity = 0.0
    ps.render.threads_mode = main.render.threads_mode
    cd = bpy.data.cameras.new("IR_PostCam")
    co = bpy.data.objects.new("IR_PostCam", cd)
    ps.collection.objects.link(co)
    ps.camera = co
    img = bpy.data.images.load(exr_path, check_existing=False)
    for cs in ("Linear Rec.709", "Linear"):
        try:
            img.colorspace_settings.name = cs
            break
        except TypeError:
            continue
    dimg = None
    if depth_path:
        dimg = bpy.data.images.load(depth_path, check_existing=False)
        dimg.colorspace_settings.name = "Non-Color"
    compositor(r, source=img, scene=ps, depth=dimg, **comp_kw)
    ps.render.filepath = out_png
    t0 = time.time()
    bpy.ops.render.render(write_still=True, scene=ps.name)
    secs = time.time() - t0
    bpy.data.scenes.remove(ps)
    return secs


# =============================================================================================
# numpy finishing
# =============================================================================================
def load16(path):
    """16-bit PNG render -> float32 H x W x 3 display values (via Blender's image loader when
    running inside Blender; Pillow 8-bit fallback otherwise)."""
    try:
        import bpy
        img = bpy.data.images.load(path, check_existing=False)
        img.colorspace_settings.name = "Non-Color"
        w, h = img.size
        a = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(a)
        bpy.data.images.remove(img)
        return np.ascontiguousarray(a.reshape(h, w, 4)[::-1, :, :3])
    except ImportError:
        from PIL import Image
        return np.asarray(Image.open(path).convert("RGB"), np.float32) / 255.0


def box_blur(a, r):
    """Box blur (radius ``r`` px, edge-clamped) along both axes with cumulative sums: O(N) for
    any radius.  Three passes approximate a gaussian of sigma ~ r."""
    r = int(max(1, r))
    out = a.astype(np.float32)
    for axis in (0, 1):
        pad = [(0, 0)] * out.ndim
        pad[axis] = (r + 1, r)
        p = np.pad(out, pad, mode="edge")
        c = np.cumsum(p, axis=axis, dtype=np.float64)
        n = out.shape[axis]
        hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
        lo = np.take(c, np.arange(0, n), axis=axis)
        out = ((hi - lo) / (2 * r + 1)).astype(np.float32)
    return out


def soft_blur(a, sigma):
    """Gaussian-like blur (3 box passes)."""
    r = max(1, int(round(sigma * 0.9)))
    for _ in range(3):
        a = box_blur(a, r)
    return a


def luma(rgb):
    return (rgb * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1, keepdims=True)


def canvas_texture(h, w, seed=0, scale=1.0):
    """Painter's canvas/paper grain centred on 0 (fine tooth + soft blotches + faint weave)."""
    rng = np.random.default_rng(seed)
    g = rng.normal(0.0, 1.0, (h, w)).astype(np.float32)
    tooth = soft_blur(g, 0.8 * scale)
    tooth /= max(1e-6, float(tooth.std()))
    blot = soft_blur(rng.normal(0.0, 1.0, (h // 8 + 2, w // 8 + 2)).astype(np.float32), 3)
    from PIL import Image
    blot = np.array(Image.fromarray(blot, "F").resize((w, h), Image.BICUBIC), np.float32)
    blot /= max(1e-6, float(blot.std()))
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    weave = np.sin(xs * (2.1 / scale)) * np.sin(ys * (2.1 / scale))
    return (0.55 * tooth + 0.35 * blot + 0.18 * weave).astype(np.float32)


def finish(rgb, grade=None, seed=0, master_scale=1.0):
    """Painterly finishing of a display-referred float RGB master.

    grade keys: saturation, contrast, pivot, shadows / highlights (additive RGB split tone,
    e.g. (0.02, 0.0, -0.03)), clarity (local contrast amount) at clarity_px (master px),
    canvas (grain amplitude), vignette, sharpen, plus optional ``curve`` (gamma), ``lift``.
    """
    g = dict(RECIPE["grade"])
    g.update(grade or {})
    img = np.clip(rgb.astype(np.float32), 0.0, 1.0)
    h, w = img.shape[:2]
    Y = luma(img)
    # split toning (weighted by luminance)
    sh = np.array(g["shadows"], np.float32)
    hi = np.array(g["highlights"], np.float32)
    ws = np.clip(1.0 - Y / 0.55, 0, 1) ** 1.5
    wh = np.clip((Y - 0.45) / 0.55, 0, 1) ** 1.2
    img = img + ws * sh + wh * hi
    if g.get("lift"):
        img = img + np.array(g["lift"], np.float32) * (1.0 - img)
    # saturation and contrast
    Y = luma(img)
    img = Y + (img - Y) * g["saturation"]
    img = (img - g["pivot"]) * g["contrast"] + g["pivot"]
    if g.get("curve", 1.0) != 1.0:
        img = np.clip(img, 0, 1) ** (1.0 / g["curve"])
    img = np.clip(img, 0.0, 1.0)
    # clarity: large radius local contrast on luminance only
    if g["clarity"] > 0:
        Y = luma(img)
        Yb = soft_blur(Y, g["clarity_px"] * master_scale)
        d = (Y - Yb) * g["clarity"]
        # protect the extremes (no halos on skies / blacks)
        d *= 4.0 * Y * (1.0 - Y)
        img = np.clip(img + d, 0, 1)
    # vignette (elliptical, soft)
    if g["vignette"] > 0:
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        cx, cy = g.get("vignette_center", (0.5, 0.5))
        d = np.sqrt(((xs / w - cx) / 0.62) ** 2 + ((ys / h - cy) / 0.62) ** 2)
        v = 1.0 - g["vignette"] * np.clip(d - 0.35, 0, 1.2) ** 1.6
        img *= v[..., None]
    # canvas grain (mid-tones mostly)
    if g["canvas"] > 0:
        t = canvas_texture(h, w, seed, master_scale)
        Y = luma(img)
        img = img + (t[..., None] * g["canvas"]) * (0.35 + 2.6 * Y * (1 - Y))
    # final sharpen
    if g["sharpen"] > 0:
        b = soft_blur(img, 1.0 * master_scale)
        img = img + (img - b) * g["sharpen"]
    return np.clip(img, 0.0, 1.0).astype(np.float32)


def downsample(rgb, size):
    """Lanczos resize of a float RGB image to ``size`` (w, h)."""
    from PIL import Image
    out = []
    for c in range(3):
        im = Image.fromarray(np.ascontiguousarray(rgb[..., c]), "F")
        out.append(np.asarray(im.resize(size, Image.LANCZOS), np.float32))
    return np.clip(np.dstack(out), 0.0, 1.0)


def to_rgba8(rgb, seed=0):
    """Float RGB -> uint8 RGBA (alpha 255) with triangular dither (no banding in skies)."""
    rng = np.random.default_rng(seed + 17)
    n = (rng.random(rgb.shape, np.float32) - rng.random(rgb.shape, np.float32)) / 255.0
    a = np.clip(rgb + n, 0, 1)
    a8 = (a * 255.0 + 0.5).astype(np.uint8)
    return np.dstack([a8, np.full(a8.shape[:2], 255, np.uint8)])


def save_png(rgba8, path):
    from PIL import Image
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    Image.fromarray(rgba8, "RGBA").save(path, optimize=True)
    return path


def save_outputs(master, art_rel, master_rel=None, preview_dir=None, seed=0):
    """Write the master (``ArtSource/<master_rel>``) and the 1x game asset
    (``Content/Data/<art_rel>`` through ``post.save_asset``'s manifest validation).

    Returns {name: (path, (w, h), kB)}."""
    from . import manifest, post
    e = manifest.entry(art_rel)
    W, H = e["size"]
    out = {}
    one = master if master.shape[1] == W else downsample(master, (W, H))
    rgba1 = to_rgba8(one, seed).astype(np.float32) / 255.0
    path1 = post.save_asset(rgba1, art_rel)
    out["asset"] = path1
    if master_rel:
        pm = os.path.join(ART_SOURCE, master_rel)
        save_png(to_rgba8(master, seed), pm)
        out["master"] = pm
    if preview_dir:
        os.makedirs(preview_dir, exist_ok=True)
        save_png(to_rgba8(one, seed), os.path.join(preview_dir, os.path.basename(art_rel)))
    rep = {}
    for k, p in out.items():
        from PIL import Image
        with Image.open(p) as im:
            rep[k] = (p, im.size, os.path.getsize(p) / 1024.0)
    return rep


# =============================================================================================
# ArtSource/manifest.json (shared with the 3D families - read-modify-write under a lock)
# =============================================================================================
def manifest_add(rel_paths):
    """Add ``rel_paths`` (relative to ArtSource, '/'-separated) to ``ArtSource/manifest.json``
    ``files`` and bump ``version`` when anything changed.  Uses an flock so concurrent artists
    never lose each other's entries."""
    import fcntl
    import json
    os.makedirs(ART_SOURCE, exist_ok=True)
    path = os.path.join(ART_SOURCE, "manifest.json")
    import tempfile
    lock = open(os.path.join(tempfile.gettempdir(), "ironreign_artsource_manifest.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = {"version": 0, "files": []}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                txt = f.read().strip()
            if txt:
                data = json.loads(txt)
        files = data.setdefault("files", [])
        have = set(x if isinstance(x, str) else x.get("path", "") for x in files)
        added = [p for p in rel_paths if p not in have]
        if added:
            for p in added:
                files.append(p)
            data["version"] = int(data.get("version", 0)) + 1
            tmp = path + ".tmp%d" % os.getpid()
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            os.replace(tmp, path)
        return data["version"], added
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


class Timer:
    def __init__(self):
        self.t = {}
        self._t0 = time.time()

    def lap(self, name):
        now = time.time()
        self.t[name] = round(now - self._t0, 1)
        self._t0 = now
        return self.t[name]


# =============================================================================================
# denoising (Cycles here has no OpenImageDenoise): edge-avoiding a-trous wavelet filter
# =============================================================================================
def load_exr(path):
    """Linear float RGBA (H x W x 4, top row first) of an EXR via Blender's image loader."""
    import bpy
    img = bpy.data.images.load(path, check_existing=False)
    img.colorspace_settings.name = "Non-Color"
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    return np.ascontiguousarray(a.reshape(h, w, 4)[::-1])


def save_exr(rgb, path):
    """Save linear float RGB as a 32-bit EXR through Blender (for the post compositor)."""
    import bpy
    h, w = rgb.shape[:2]
    img = bpy.data.images.new("IR_Denoised", w, h, alpha=True, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    a = np.ones((h, w, 4), np.float32)
    a[..., :3] = rgb
    img.pixels.foreach_set(np.ascontiguousarray(a[::-1]).reshape(-1))
    img.filepath_raw = path
    img.file_format = "OPEN_EXR"
    sc = bpy.context.scene
    old = (sc.render.image_settings.file_format, sc.render.image_settings.color_depth)
    img.save()
    bpy.data.images.remove(img)
    return path


def _shift(a, dy, dx):
    """Shift with edge clamping (no wrap)."""
    h, w = a.shape[:2]
    ys = np.clip(np.arange(h) + dy, 0, h - 1)
    xs = np.clip(np.arange(w) + dx, 0, w - 1)
    return a[ys][:, xs]


def despeckle(img, k=2.2, floor=0.04, iters=2):
    """Firefly suppression: a pixel brighter than ``k`` x the mean of its 8 neighbours (+ floor)
    is replaced by that mean (isolated speckles from glossy / small-emitter paths)."""
    out = img.copy()
    for _ in range(iters):
        acc = np.zeros_like(out)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx or dy:
                    acc += _shift(out, dy, dx)
        mean = acc / 8.0
        Lc = luma(out)
        Lm = luma(mean)
        bad = Lc > (Lm * k + floor)
        out = np.where(bad, mean, out)
    return out


def denoise(color, albedo, normal, depth, passes=5, sigma_c=0.55, sigma_n=0.35, sigma_z=0.04,
            strength=1.0, speckle=2.2, sigma_a=0.035):
    """Edge-avoiding a-trous wavelet filter (Dammertz et al. 2010) on the albedo-demodulated
    radiance, guided by normals and relative depth.  ``strength`` < 1 blends the original back
    (keeps a little grain for the painterly finish).  All inputs H x W x C float32 (linear)."""
    eps = 1e-4
    if speckle:
        color = np.concatenate([despeckle(color[..., :3], speckle), color[..., 3:]], -1) \
            if color.shape[-1] > 3 else despeckle(color, speckle)
    A = np.clip(albedo[..., :3], 0.0, None)
    a_l = luma(A)
    # demodulate only bright, diffuse-looking albedo (dark glossy floors would explode)
    useA = np.clip((a_l - 0.1) / 0.1, 0.0, 1.0).astype(np.float32)
    Ad = A * useA + (1.0 - useA)
    I = color[..., :3] / np.maximum(Ad, 0.05)
    N = normal[..., :3]
    Z = depth[..., :1] if depth.ndim == 3 else depth[..., None]
    Z = np.where(np.isfinite(Z), Z, 1e6).astype(np.float32)
    lz = np.log(np.maximum(Z, 1e-3))
    Asq = np.sqrt(A).astype(np.float32)            # perceptual-ish albedo for edge stopping
    k1 = np.array([1 / 16, 1 / 4, 3 / 8, 1 / 4, 1 / 16], np.float32)
    out = I.copy()
    # variance guidance: where the local relative noise is high, the colour edge-stopping
    # loosens (noisy flat areas blend, clean edges stay)
    L0 = luma(I)
    m1 = box_blur(L0, 2)
    m2 = box_blur(L0 * L0, 2)
    rel = np.sqrt(np.clip(m2 - m1 * m1, 0, None)) / (m1 + 1e-3)
    sc = np.clip(sigma_c * (1.0 + 1.5 * rel), sigma_c, 2.0).astype(np.float32)
    for it in range(passes):
        step = 1 << it
        acc = np.zeros_like(out)
        wsum = np.zeros(out.shape[:2] + (1,), np.float32)
        Lp = luma(out)
        for j, ky in enumerate(k1):
            for i, kx in enumerate(k1):
                dy, dx = (j - 2) * step, (i - 2) * step
                q = _shift(out, dy, dx)
                Lq = luma(q)
                dc = (Lp - Lq) / (Lp + Lq + eps)
                w = np.exp(-(dc * dc) / (sc * sc))
                if dy or dx:
                    nq = _shift(N, dy, dx)
                    dn = ((N - nq) ** 2).sum(-1, keepdims=True)
                    w *= np.exp(-dn / (sigma_n * sigma_n))
                    zq = _shift(lz, dy, dx)
                    dzz = lz - zq
                    w *= np.exp(-(dzz * dzz) / (sigma_z * sigma_z * step))
                    aq = _shift(Asq, dy, dx)
                    da = ((Asq - aq) ** 2).sum(-1, keepdims=True)
                    w *= np.exp(-da / (sigma_a * sigma_a))
                w *= kx * ky
                acc += q * w
                wsum += w
        out = acc / np.maximum(wsum, 1e-8)
        sc = sc * 0.6
    res = out * Ad
    if strength < 1.0:
        res = color[..., :3] * (1.0 - strength) + res * strength
    return res.astype(np.float32)


# =============================================================================================
# QA
# =============================================================================================
def qa(rgb, name=""):
    """Measured values of a finished 1x image (float RGB 0..1): mean luma, clipped / crushed
    fractions, NaN check, and detail energy (mean |Laplacian| of luma, 8-bit) per column third -
    used to verify the calm UI zones (Title: left 40 %, Duel: centre)."""
    Y = (rgb[..., :3] * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1) * 255.0
    lap = np.abs(4 * Y[1:-1, 1:-1] - Y[:-2, 1:-1] - Y[2:, 1:-1] - Y[1:-1, :-2] - Y[1:-1, 2:])
    w = lap.shape[1]
    out = dict(mean_luma=round(float(Y.mean()), 1), p02=round(float(np.percentile(Y, 2)), 1),
               p98=round(float(np.percentile(Y, 98)), 1),
               clipped_pct=round(float((Y >= 254.5).mean() * 100), 2),
               crushed_pct=round(float((Y <= 1.5).mean() * 100), 2),
               nan=bool(np.isnan(rgb).any()))
    out["detail_left40"] = round(float(lap[:, :int(w * 0.4)].mean()), 2)
    out["detail_right60"] = round(float(lap[:, int(w * 0.4):].mean()), 2)
    out["detail_centre30"] = round(float(lap[:, int(w * 0.35):int(w * 0.65)].mean()), 2)
    out["detail_sides"] = round(float(np.concatenate([lap[:, :int(w * 0.3)], lap[:, int(w * 0.7):]], 1).mean()), 2)
    return out
