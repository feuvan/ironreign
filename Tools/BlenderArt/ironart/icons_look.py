"""Icons family (premium still-life icons): the family recipe, camera, light rig, studio
environment, render settings and the 2D finishing chain.

Every ``Icon_<Name>`` is a small 3D still life (real geometry, PBR materials) shot with ONE
camera and ONE light rig, so the 40 icons read as a set:

* camera     perspective, 3/4 from the front-left (elevation 28 deg, azimuth -24 deg) at a fixed
             distance, so every prop shares the same mild perspective; the lens and the shift are
             solved per icon so the prop fills the keyline box exactly (:func:`fit`)
* light      warm soft area key from the top-left of the screen (screen 135 deg, the studio
             sun) placed 4.5 bounding radii away (a natural falloff across the prop), cool broad fill from the right, a warm-white rim from behind / top-right and a cool
             kicker from behind / left that cut the silhouette out of a black background, a
             shadowless top light, low warm ambient
* reflection glossy rays see a baked studio environment (big warm softbox top-left, rim strip,
             cool fill card, warm horizon ring) so bronze, gold, lacquer and glaze get believable
             highlights; diffuse rays see only the dim ambient (calibrated, no colour cast)
* render     Cycles CPU, Filmic Medium High Contrast, 512 x 512 (= 4 x the 128 px @2x master,
             8 x the 64 px game icon), adaptive sampling, indirect clamp, no denoiser
* finishing  (numpy, works in Blender's python and the system python3) a soft dark outline and a
             drop shadow towards the bottom-right built from the alpha at render size, then
             premultiplied Lanczos to 128 and 64, grade, unsharp, alpha clean-up, clear 1 px ring

All look numbers live in :data:`RECIPE` (this module is the "icon_still_life" family recipe; the
shared ``recipes.RECIPES["icon"]`` painterly recipe is left untouched for other users).

``bpy`` is imported lazily: the 2D half (:func:`finish`, :func:`qa`, sheets) runs anywhere.
"""

import json
import math
import os

import numpy as np

from . import post

#: the family look numbers (ONE place)
RECIPE = dict(
    sizes=(64, 128),                   # game icon, ArtSource @2x master
    render=512,                        # square render (8 x 64, 4 x 128)
    spp=80, preview_spp=20, preview_render=256,
    adaptive=0.008, clamp_indirect=3.0, filter_width=1.5,
    view="Filmic", look="Medium High Contrast", exposure=0.0,
    # camera: elevation / azimuth in degrees (azimuth < 0 = camera to the front-left of the prop,
    # the prop's front faces -Y), fixed distance in scene units (props are built ~2 units wide)
    camera=dict(elevation=28.0, azimuth=-24.0, distance=14.0),
    # keyline box at 64 px (left, top, right, bottom): the prop's projected bounds fill this box
    # (the shorter side is centred); outline + shadow stay inside a 2 px clear border
    keyline=(4.5, 4.0, 58.5, 58.0),
    # lights: screen angle (deg CCW from screen-right), elevation (deg towards the viewer;
    # negative = behind the prop), strength (sun W/m2), colour (sRGB), soft (sun angle, deg)
    key=dict(angle=135.0, elev=42.0, strength=3.8, color="#FFE2BE", dist=4.5, size=1.6),
    fill=dict(angle=-30.0, elev=18.0, strength=0.55, color="#B9CCEA", soft=40.0),
    rim=dict(angle=48.0, elev=-38.0, strength=4.4, color="#FFEBD0", dist=4.0, size=1.0),
    kick=dict(angle=168.0, elev=-28.0, strength=1.6, color="#BCD0F2", soft=14.0),
    top=dict(strength=0.45, color="#FFF4E6"),
    ambient=dict(color="#8A7A68", strength=0.16),
    # glossy studio environment (lobes in screen space of the camera; strength x colour)
    env=dict(
        softbox=dict(angle=135.0, elev=38.0, radius=24.0, soft=10.0, strength=3.2, color="#FFF0DC"),
        rimstrip=dict(angle=45.0, elev=-25.0, radius=14.0, soft=8.0, strength=4.0, color="#FFF3E2"),
        kickcard=dict(angle=180.0, elev=-10.0, radius=16.0, soft=10.0, strength=1.3, color="#D6E2F6"),
        fillcard=dict(angle=-35.0, elev=12.0, radius=34.0, soft=14.0, strength=0.55, color="#C9D6EC"),
        topstrip=dict(angle=90.0, elev=10.0, radius=18.0, soft=10.0, strength=0.9, color="#FFF6EA"),
        front=dict(angle=120.0, elev=68.0, radius=42.0, soft=16.0, strength=0.75, color="#FFEEDA"),
        horizon=0.45, horizon_color="#FFE6C4", ceiling=0.32, floor=0.12,
        floor_color="#7A5E40"),
    # 2D finishing (per output size): outline radius / alpha, drop shadow offset / blur / opacity
    outline=dict(color="#140D08", alpha=0.82, radius={64: 0.85, 128: 1.35}),
    shadow=dict(color="#0B0705", opacity=0.42, offset={64: (0.7, 1.1), 128: (1.3, 2.0)},
                blur={64: 0.9, 128: 1.6}),
    grade=dict(saturation=1.05, contrast=1.03, warmth=0.006),
    unsharp={64: (0.55, 0.40), 128: (0.75, 0.30)},
    # review backgrounds (DESIGN.md tokens) and the in-game button field
    backgrounds=dict(parchment="#E9DCC0", lacquer="#1B1712", button="#7E1F17"),
)

#: the 40 icons of DESIGN.md section 8, in manifest order
ICONS = ("Farm", "Commerce", "Walls", "Patrol", "Draft", "Train", "Search", "Recruit", "Move",
         "Transport", "SectTraining", "Alliance", "Truce", "Gift", "March", "Market", "Tavern",
         "Officers", "Factions", "Save", "Load", "EndTurn", "Gold", "Food", "Troops", "Population",
         "Order", "Defense", "Training", "Loyalty", "Settings", "Delegate", "Prisoner", "Fire",
         "Confuse", "Rally", "Duel", "Attack", "Wait", "Undo")

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
ART_SOURCE = os.path.join(REPO, "ArtSource")
MASTER_DIR = "UI/Icons"                         # ArtSource/UI/Icons/Icon_<Name>@2x.png


# =============================================================================================
# Blender side
# =============================================================================================
def setup(preview=False, spp=None, seed=0):
    """Cycles CPU + colour management + resolution for one icon render."""
    import bpy
    from . import scene
    r = RECIPE
    sc = scene.setup_cycles(samples=spp or (r["preview_spp"] if preview else r["spp"]),
                            transparent=True, preset="sprite", view=r["view"], look=r["look"],
                            exposure=r["exposure"], adaptive_threshold=r["adaptive"], seed=seed,
                            filter_width=r["filter_width"], clamp_indirect=r["clamp_indirect"])
    cy = sc.cycles
    cy.max_bounces = 6
    cy.diffuse_bounces = 2
    cy.glossy_bounces = 3
    cy.transmission_bounces = 4
    cy.transparent_max_bounces = 16
    cy.volume_bounces = 0
    try:
        cy.film_transparent_glass = False
    except AttributeError:
        pass
    n = r["preview_render"] if preview else r["render"]
    sc.render.resolution_x = sc.render.resolution_y = n
    sc.render.resolution_percentage = 100
    sc["ironart_target"] = (n, n)
    sc["ironart_supersample"] = 1
    return sc


def camera(name="CamIcon"):
    """The family camera (perspective, fixed pose; :func:`fit` sets lens + shift)."""
    import bpy
    from mathutils import Vector
    c = RECIPE["camera"]
    cd = bpy.data.cameras.new(name)
    cd.type = "PERSP"
    cd.sensor_fit = "HORIZONTAL"
    cd.sensor_width = 36.0
    cd.lens = 50.0
    cd.clip_start = 0.05
    cd.clip_end = 200.0
    cam = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    el, az = math.radians(c["elevation"]), math.radians(c["azimuth"])
    offs = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    cam.location = offs * c["distance"]
    q = (-offs).normalized().to_track_quat("-Z", "Y")
    cam.rotation_mode = "XYZ"
    cam.rotation_euler = q.to_euler()
    bpy.context.view_layer.update()
    return cam


def _points(objs):
    import bpy
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objs:
        if o.type not in {"MESH", "CURVE", "SURFACE", "FONT", "META"}:
            continue
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        mw = ev.matrix_world
        pts.extend(mw @ v.co for v in me.vertices)
        ev.to_mesh_clear()
    return pts


def project(cam, pts):
    """World points -> (u, v) on the image plane in units of the frame width, centred, for the
    camera's current lens with shift 0 (u right, v up)."""
    inv = cam.matrix_world.inverted()
    f = cam.data.lens / cam.data.sensor_width
    uv = []
    for p in pts:
        q = inv @ p
        z = -q.z
        uv.append((f * q.x / z, f * q.y / z))
    return uv


def fit(cam, objs, fill=1.0, keyline=None, offset=(0.0, 0.0)):
    """Solve lens and shift so the projected bounds of ``objs`` fill the keyline box.

    ``fill`` < 1 shrinks a compact prop inside the box (optical size balance across the set);
    ``offset`` nudges it (fractions of the box). Returns the bounds in 64 px units."""
    kl = keyline or RECIPE["keyline"]
    size = 64.0
    cam.data.shift_x = cam.data.shift_y = 0.0
    cam.data.lens = 50.0
    pts = _points(objs)
    if not pts:
        raise ValueError("fit: no geometry")
    uv = project(cam, pts)
    u0 = min(p[0] for p in uv); u1 = max(p[0] for p in uv)
    v0 = min(p[1] for p in uv); v1 = max(p[1] for p in uv)
    bw = (kl[2] - kl[0]) / size
    bh = (kl[3] - kl[1]) / size
    k = min(bw / (u1 - u0), bh / (v1 - v0)) * fill
    cam.data.lens = 50.0 * k
    # box centre in frame units (u right from the centre, v up from the centre)
    bcx = ((kl[0] + kl[2]) / 2.0) / size - 0.5 + offset[0] * bw
    bcy = 0.5 - ((kl[1] + kl[3]) / 2.0) / size - offset[1] * bh
    cam.data.shift_x = k * (u0 + u1) / 2.0 - bcx
    cam.data.shift_y = k * (v0 + v1) / 2.0 - bcy
    import bpy
    bpy.context.view_layer.update()
    W = k * (u1 - u0) * size
    H = k * (v1 - v0) * size
    return W, H


def screen_dir(cam, angle_deg, elev_deg):
    from . import lights
    return lights.screen_dir(cam, angle_deg, elev_deg)


def _env_array(cam, width=1024):
    """Equirectangular studio environment (linear RGB, row 0 = zenith) in WORLD directions,
    lobes placed in the camera's screen space.  Mapping u = atan2(y, x)/2pi + 0.5,
    v = asin(z)/pi + 0.5 (the world node graph of :func:`rig` reads it the same way)."""
    from . import palette
    e = RECIPE["env"]
    h = width // 2
    u = (np.arange(width) + 0.5) / width
    v = 1.0 - (np.arange(h) + 0.5) / h
    PH, TH = np.meshgrid((u - 0.5) * 2 * math.pi, (v - 0.5) * math.pi)
    x = np.cos(PH) * np.cos(TH)
    y = np.sin(PH) * np.cos(TH)
    z = np.sin(TH)

    def col(c):
        return np.array(palette.lin(c), np.float32).reshape(1, 1, 3)

    def ss(e0, e1, t):
        t = np.clip((t - e0) / (e1 - e0), 0.0, 1.0)
        return t * t * (3 - 2 * t)

    out = np.zeros((h, width, 3), np.float32)
    for key in ("softbox", "rimstrip", "kickcard", "fillcard", "topstrip", "front"):
        L = e[key]
        d = screen_dir(cam, L["angle"], L["elev"])
        dt = x * d.x + y * d.y + z * d.z
        lobe = ss(math.cos(math.radians(L["radius"] + L["soft"])),
                  math.cos(math.radians(max(0.5, L["radius"] - L["soft"]))), dt)
        out += lobe[..., None] * L["strength"] * col(L["color"])
    above = ss(-0.05, 0.03, z)
    ring = ss(0.45, 0.06, z) * above
    out += ring[..., None] * e["horizon"] * col(e["horizon_color"])
    out += above[..., None] * e["ceiling"] * col("#FFF4E6")
    out += (1.0 - above)[..., None] * e["floor"] * col(e["floor_color"])
    return out


def bounds_sphere(objs):
    """(centre, radius) of the evaluated vertices of ``objs`` (world space)."""
    from mathutils import Vector
    pts = _points(objs)
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    c = (lo + hi) / 2.0
    return c, max((p - c).length for p in pts)


def rig(cam, objs):
    """Area key + area rim (placed on the prop's bounding sphere, so every prop gets the same
    falloff from the top-left), sun fill / kicker / top, diffuse ambient, glossy studio
    environment."""
    import bpy
    from . import lights, palette
    r = RECIPE
    out = {}
    c, R = bounds_sphere(objs)
    for k in ("key", "rim"):
        L = r[k]
        d = screen_dir(cam, L["angle"], L["elev"])
        dist = L["dist"] * R
        # irradiance at the centre ~ power / (pi d^2): keep the recipe strength in W/m2
        power = L["strength"] * math.pi * dist * dist
        out[k] = lights.area(k.title(), c + d * dist, c, power, size=L["size"] * R,
                             color=L["color"], shadow=True)
    for k in ("fill", "kick"):
        L = r[k]
        out[k] = lights.sun(k.title(), screen_dir(cam, L["angle"], L["elev"]), L["strength"],
                            L["color"], L["soft"], shadow=False)
    from mathutils import Vector
    out["top"] = lights.sun("Top", Vector((0.0, 0.15, 1.0)), r["top"]["strength"],
                            r["top"]["color"], 30.0, shadow=False)
    env = _env_array(cam)
    hh, ww = env.shape[:2]
    old = bpy.data.images.get("IconEnv")
    if old is not None:
        bpy.data.images.remove(old)
    img = bpy.data.images.new("IconEnv", ww, hh, alpha=True, float_buffer=True)
    a = np.dstack([env, np.ones((hh, ww), np.float32)])[::-1].astype(np.float32)
    img.pixels.foreach_set(np.ascontiguousarray(a).ravel())
    img.colorspace_settings.name = "Non-Color"
    img.pack()
    w = bpy.data.worlds.new("IconWorld")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    N, Lk = nt.nodes, nt.links
    N.clear()
    o = N.new("ShaderNodeOutputWorld")
    amb = N.new("ShaderNodeBackground")
    amb.inputs["Color"].default_value = palette.lin4(r["ambient"]["color"])
    amb.inputs["Strength"].default_value = r["ambient"]["strength"]
    tc = N.new("ShaderNodeTexCoord")
    nv = N.new("ShaderNodeVectorMath"); nv.operation = "NORMALIZE"
    Lk.new(tc.outputs["Generated"], nv.inputs[0])
    sp = N.new("ShaderNodeSeparateXYZ"); Lk.new(nv.outputs[0], sp.inputs[0])
    at = N.new("ShaderNodeMath"); at.operation = "ARCTAN2"
    Lk.new(sp.outputs["Y"], at.inputs[0]); Lk.new(sp.outputs["X"], at.inputs[1])
    uu = N.new("ShaderNodeMath"); uu.operation = "MULTIPLY_ADD"
    Lk.new(at.outputs[0], uu.inputs[0])
    uu.inputs[1].default_value = 1.0 / (2 * math.pi); uu.inputs[2].default_value = 0.5
    asn = N.new("ShaderNodeMath"); asn.operation = "ARCSINE"
    Lk.new(sp.outputs["Z"], asn.inputs[0])
    vv = N.new("ShaderNodeMath"); vv.operation = "MULTIPLY_ADD"
    Lk.new(asn.outputs[0], vv.inputs[0])
    vv.inputs[1].default_value = 1.0 / math.pi; vv.inputs[2].default_value = 0.5
    cv = N.new("ShaderNodeCombineXYZ")
    Lk.new(uu.outputs[0], cv.inputs["X"]); Lk.new(vv.outputs[0], cv.inputs["Y"])
    et = N.new("ShaderNodeTexImage"); et.image = img
    et.interpolation = "Linear"; et.extension = "REPEAT"
    Lk.new(cv.outputs[0], et.inputs["Vector"])
    ref = N.new("ShaderNodeBackground")
    Lk.new(et.outputs["Color"], ref.inputs["Color"])
    ref.inputs["Strength"].default_value = 1.0
    lp = N.new("ShaderNodeLightPath")
    mix = N.new("ShaderNodeMixShader")
    Lk.new(lp.outputs["Is Glossy Ray"], mix.inputs[0])
    Lk.new(amb.outputs[0], mix.inputs[1])
    Lk.new(ref.outputs[0], mix.inputs[2])
    Lk.new(mix.outputs[0], o.inputs["Surface"])
    out["world"] = w
    return out


# =============================================================================================
# 2D finishing (numpy only)
# =============================================================================================
def _disk_max(a, radius):
    """Grey dilation of a 2D array by a disk of ``radius`` px (anti-aliased rim)."""
    r = int(math.ceil(radius))
    out = a.copy()
    H, W = a.shape
    p = np.pad(a, r)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            d = math.hypot(dx, dy)
            if d > radius + 0.5 or (dx == 0 and dy == 0):
                continue
            w = min(1.0, radius + 0.5 - d)
            sl = p[r + dy:r + dy + H, r + dx:r + dx + W]
            out = np.maximum(out, sl * w)
    return out


def _shift(a, dx, dy):
    """Sub-pixel shift (bilinear, zero fill) of a 2D array: content moves by (+dx, +dy)."""
    return post._shift(a, dx, dy)


def compose(raw, size):
    """Raw render (float RGBA, straight alpha, render size) -> finished ``size`` px icon.

    shadow (bottom) -> outline -> prop, all premultiplied at render size, then premultiplied
    Lanczos to ``size``, grade, unsharp, alpha clean-up and a clear 1 px border."""
    from . import palette
    R = raw.shape[0]
    s = R / float(size)                           # render px per output px
    a = raw[..., 3].astype(np.float32)
    o = RECIPE["outline"]
    sh = RECIPE["shadow"]
    # outline: alpha dilated by the radius (render px), feathered by half an output pixel
    rad = o["radius"][size] * s
    dil = _disk_max(a, rad)
    dil = post.gaussian(dil, 0.35 * s)
    out_a = np.clip(dil, 0, 1) * o["alpha"]
    # drop shadow: blurred alpha (incl. the outline) pushed to the bottom-right
    sa = post.gaussian(np.maximum(a, dil * 0.9), sh["blur"][size] * s)
    sa = _shift(sa, sh["offset"][size][0] * s, sh["offset"][size][1] * s) * sh["opacity"]
    oc = np.array(palette.srgb(o["color"]), np.float32)
    sc = np.array(palette.srgb(sh["color"]), np.float32)
    # premultiplied "over" stack in sRGB space (what Slate does when it draws the PNG)
    prem = raw[..., :3] * a[..., None]
    rgb = sc[None, None, :] * sa[..., None]
    alpha = sa.copy()
    rgb = oc[None, None, :] * out_a[..., None] + rgb * (1 - out_a[..., None])
    alpha = out_a + alpha * (1 - out_a)
    rgb = prem + rgb * (1 - a[..., None])
    alpha = a + alpha * (1 - a)
    img = np.dstack([rgb, alpha]).astype(np.float32)
    img = post.unpremultiply(img)
    img = post.resize(img, (size, size), "lanczos")
    g = RECIPE["grade"]
    img = post.grade(img, **g)
    us = RECIPE["unsharp"][size]
    img = post.unsharp(img, us[0], us[1])
    img = post.alpha_cleanup(img, lo=0.02, hi=0.985, bleed=3)
    img[0, :, 3] = img[-1, :, 3] = 0.0
    img[:, 0, 3] = img[:, -1, 3] = 0.0
    return img


def prop_bbox(raw, size, thresh=0.5):
    """Bounds of the prop itself (no outline / shadow) in ``size`` px units."""
    a = raw[..., 3]
    s = raw.shape[0] / float(size)
    ys, xs = np.nonzero(a > thresh)
    if len(xs) == 0:
        return None
    return (xs.min() / s, ys.min() / s, (xs.max() + 1) / s, (ys.max() + 1) / s)


def over_bg(img, color):
    """Composite an icon over a solid background colour (review sheets / QA)."""
    from . import palette
    bg = post.solid(img.shape[1], img.shape[0], palette.srgb(color) if isinstance(color, str)
                    else color)
    return post.over(img, bg)


def qa(name, raw, icons, strict=True):
    """Measured contract of one icon: canvas sizes, clear 1 px border, prop inside the keyline,
    silhouette contrast on parchment and on black lacquer.  Returns the QA object."""
    q = post.QA(name, strict=False)
    for size, img in icons.items():
        q.range("size %d" % size, img.shape[0], size, size)
        q.max("border alpha %d" % size, post.border_alpha_max(img), 0.0)
    bb = prop_bbox(raw, 64)
    kl = RECIPE["keyline"]
    if bb:
        q.range("prop left", bb[0], kl[0] - 0.6, 64)
        q.range("prop top", bb[1], kl[1] - 0.6, 64)
        q.range("prop right", bb[2], 0, kl[2] + 0.6)
        q.range("prop bottom", bb[3], 0, kl[3] + 0.6)
        q.range("prop extent (px)", max(bb[2] - bb[0], bb[3] - bb[1]), 40.0, 56.0)
    img = icons[64]
    a = img[..., 3]
    q.range("coverage", float((a > 0.5).mean()), 0.16, 0.80)
    # silhouette contrast: a 1.5 px band just outside the prop must differ from the background
    b = RECIPE["backgrounds"]
    for bgname in ("parchment", "lacquer"):
        comp = over_bg(img, b[bgname])
        lum = post.luma8(comp)
        bgl = float(post.luma8(post.solid(1, 1, b[bgname]))[0, 0])
        inner = (a > 0.9)
        ring = _disk_max(inner.astype(np.float32), 1.5) > 0.5
        edge = ring & ~_erode(inner, 1)
        if edge.any():
            q.range("edge contrast on %s" % bgname, float(np.abs(lum[edge] - bgl).mean()),
                    18.0, 255.0)
    q.check() if strict else None
    return q


def _erode(m, r):
    return _disk_max((~m).astype(np.float32), r) < 0.5


# =============================================================================================
# outputs
# =============================================================================================
def save_icon(name, icons):
    """Write ``Content/Data/Art/UI/Icon_<name>.png`` (64, manifest-validated) and the 128 px
    master ``ArtSource/UI/Icons/Icon_<name>@2x.png``.  Returns {label: (path, (w, h), kB)}."""
    from PIL import Image
    rel = "Art/UI/Icon_%s.png" % name
    p1 = post.save_asset(icons[64], rel)
    p2 = os.path.join(ART_SOURCE, MASTER_DIR, "Icon_%s@2x.png" % name)
    post.save(icons[128], p2)
    rep = {}
    for k, p in (("64", p1), ("128", p2)):
        with Image.open(p) as im:
            rep[k] = (p, im.size, os.path.getsize(p) / 1024.0)
    return rep


def manifest_add(rel_paths):
    """Add ``rel_paths`` (relative to ArtSource) to ``ArtSource/manifest.json`` and bump the
    version when anything changed.  Same flock as the other families (scenes, ui_chrome), so
    concurrent artists never lose each other's entries."""
    import fcntl
    import tempfile
    os.makedirs(ART_SOURCE, exist_ok=True)
    path = os.path.join(ART_SOURCE, "manifest.json")
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
            files.extend(added)
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


# =============================================================================================
# review sheets
# =============================================================================================
def _font(px):
    from PIL import ImageFont
    for p in (os.path.join(REPO, "Content", "Data", "Fonts", "Body-Regular.ttf"),):
        try:
            return ImageFont.truetype(p, px)
        except OSError:
            pass
    return ImageFont.load_default()


def review_sheet(items, path, sizes=(32, 64), bgs=("parchment", "lacquer", "button"), cols=10,
                 label=True, zoom=1):
    """Grid of icons: for every icon one cell per (background, size).  ``items`` = [(name,
    {64: img, 128: img})].  32 px is the 64 px icon scaled the way Slate draws it (bilinear,
    premultiplied)."""
    from PIL import Image, ImageDraw
    from . import palette
    b = RECIPE["backgrounds"]
    cell_w = sum(sizes) * zoom + 6 * (len(sizes) - 1) + 12
    cell_h = (max(sizes) * zoom + 8) * len(bgs) + (14 if label else 0) + 6
    rows = int(math.ceil(len(items) / float(cols)))
    W, H = cols * cell_w + 8, rows * cell_h + 8
    sheet = Image.new("RGBA", (W, H), (40, 34, 28, 255))
    d = ImageDraw.Draw(sheet)
    f = _font(11)
    for k, (name, icons) in enumerate(items):
        cx = 8 + (k % cols) * cell_w
        cy = 8 + (k // cols) * cell_h
        for j, bgname in enumerate(bgs):
            y = cy + j * (max(sizes) * zoom + 8)
            d.rectangle([cx - 4, y - 4, cx + cell_w - 12, y + max(sizes) * zoom + 3],
                        fill=palette.srgb8(b[bgname]) + (255,))
            x = cx
            for s in sizes:
                im = icons[s] if s in icons else post.resize(icons[64], (s, s), "bilinear")
                if zoom != 1:
                    im = post.resize(im, (s * zoom, s * zoom), "nearest")
                sheet.alpha_composite(post.to_pil(im), (x, y + (max(sizes) - s) * zoom))
                x += s * zoom + 6
        if label:
            d.text((cx, cy + len(bgs) * (max(sizes) * zoom + 8) - 2), name,
                   fill=(233, 220, 192, 255), font=f)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    sheet.save(path)
    return path
