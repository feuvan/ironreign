"""UI chrome family: relief plates -> real displaced meshes + the family studio rig (bpy).

``plate(maps, w, h)`` turns a :class:`ironart.ui_chrome_maps.Maps` into a mesh object: a grid
with one vertex per texel (or per ``step`` texels) displaced by ``maps.height`` (mm), UV-mapped
1:1 to four packed float images (albedo+alpha, metal/rough/coat/spec, emission+mother-of-pearl)
read by one generic Principled material.  Cycles then does the physics: cast shadows of raised
mouldings, inter-reflection, clear-coat and metal reflections of the studio environment.

Scene units: 1 target px = 1 mm (STYLE.md section 3); the piece spans x 0..w, y 0..h mm with
the image's top-left at (-w/2, +h/2) in world space and the camera looking straight down.

The rig (:func:`rig_chrome`) keeps the studio's one sun (screen 135 deg) and the UI calibration
(flat face-up diffuse = albedo, white key + white ambient), and adds a *glossy-only* studio
environment so lacquer, gold and shell get believable reflections: a round warm softbox behind
the key, a cool fill opposite, a warm horizon ring (rim glints on every bevel) and a dim ceiling.
"""

import math

import bpy
import numpy as np

from . import palette

MM = 0.001


# =============================================================================================
# images
# =============================================================================================
def image(name, arr, float_buffer=True, srgb=False):
    """float32 (rows, cols, 4) array (row 0 = top) -> packed image.  ``float_buffer=False``
    stores 8 bits per channel (4x less memory, much faster texture fetches in Cycles);
    ``srgb=True`` then encodes RGB with the sRGB curve (the image is tagged sRGB, so Cycles
    decodes it back to linear) - full precision where the eye needs it, in the darks."""
    h, w = arr.shape[:2]
    old = bpy.data.images.get(name)
    if old is not None:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(name, w, h, alpha=True, float_buffer=float_buffer)
    a = np.ascontiguousarray(arr[::-1], dtype=np.float32).copy()
    if srgb:
        rgb = np.clip(a[..., :3], 0, None)
        a[..., :3] = np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * np.power(rgb, 1 / 2.4) - 0.055)
        img.colorspace_settings.name = "sRGB"
    else:
        img.colorspace_settings.name = "Non-Color"
    img.alpha_mode = "CHANNEL_PACKED"
    img.pixels.foreach_set(np.clip(a, 0, None).ravel() if not float_buffer else a.ravel())
    img.pack()
    return img


def pack_images(name, m):
    c = np.dstack([m.base, m.alpha])
    p = np.dstack([m.metal, m.rough, m.coat, m.spec])
    e = np.dstack([m.emit, m.mop])
    return (image(name + "_C", c, float_buffer=False, srgb=True),
            image(name + "_P", np.clip(p, 0, 1), float_buffer=False),
            image(name + "_E", e, float_buffer=False, srgb=True))


# =============================================================================================
# material
# =============================================================================================
def relief_material(name, imgs, coat_roughness=0.045, interpolation="Linear", emission=1.0,
                    detail=None, shader_alpha=True):
    """Generic material driven by the packed maps (see module doc).  ``detail``: optional
    float image of residual relief (mm) below the mesh resolution, applied as a bump."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    N, Lk = nt.nodes, nt.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial")
    bsdf = N.new("ShaderNodeBsdfPrincipled")
    tc = N.new("ShaderNodeTexCoord")
    tex = []
    for img in imgs:
        t = N.new("ShaderNodeTexImage")
        t.image = img
        t.interpolation = interpolation
        t.extension = "EXTEND"
        Lk.new(tc.outputs["UV"], t.inputs["Vector"])
        tex.append(t)
    tC, tP, tE = tex
    sp = N.new("ShaderNodeSeparateColor")
    Lk.new(tP.outputs["Color"], sp.inputs[0])
    # mother-of-pearl: pastel interference colours driven by the facing angle (normals of the
    # relief + a fine shell-layer noise), mixed over the body colour by the mop weight
    lw = N.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.35
    nz = N.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 900.0
    nz.inputs["Detail"].default_value = 3.0
    nz.inputs["Distortion"].default_value = 2.5
    Lk.new(tc.outputs["Object"], nz.inputs["Vector"])
    add = N.new("ShaderNodeMath")
    add.operation = "MULTIPLY_ADD"
    Lk.new(lw.outputs["Facing"], add.inputs[0])
    add.inputs[1].default_value = 2.2
    Lk.new(nz.outputs["Fac"], add.inputs[2])
    fr = N.new("ShaderNodeMath")
    fr.operation = "FRACT"
    Lk.new(add.outputs[0], fr.inputs[0])
    ramp = N.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.interpolation = "B_SPLINE"
    stops = [(0.0, "#E9F1EC"), (0.2, "#F3D9E2"), (0.42, "#D8E6F4"), (0.62, "#DDF0E0"),
             (0.8, "#F6EBD2"), (1.0, "#E9F1EC")]
    while len(cr.elements) < len(stops):
        cr.elements.new(0.5)
    for el, (pos, col) in zip(cr.elements, stops):
        el.position = pos
        el.color = palette.lin4(col)
    Lk.new(fr.outputs[0], ramp.inputs[0])
    mix = N.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    Lk.new(tE.outputs["Alpha"], mix.inputs[0])
    Lk.new(tC.outputs["Color"], mix.inputs[6])
    Lk.new(ramp.outputs[0], mix.inputs[7])
    Lk.new(mix.outputs[2], bsdf.inputs["Base Color"])
    if shader_alpha:
        # (costs ~30 % render time: shadow rays must evaluate the shader for transparency)
        Lk.new(tC.outputs["Alpha"], bsdf.inputs["Alpha"])
    Lk.new(sp.outputs[0], bsdf.inputs["Metallic"])
    Lk.new(sp.outputs[1], bsdf.inputs["Roughness"])
    Lk.new(sp.outputs[2], bsdf.inputs["Coat Weight"])
    Lk.new(tP.outputs["Alpha"], bsdf.inputs["Specular IOR Level"])
    bsdf.inputs["Coat Roughness"].default_value = coat_roughness
    Lk.new(tE.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = emission
    if detail is not None:
        td = N.new("ShaderNodeTexImage")
        td.image = detail
        td.interpolation = "Linear"
        td.extension = "EXTEND"
        Lk.new(tc.outputs["UV"], td.inputs["Vector"])
        bump = N.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 1.0
        bump.inputs["Distance"].default_value = MM
        Lk.new(td.outputs["Color"], bump.inputs["Height"])
        for k in ("Normal", "Coat Normal"):
            Lk.new(bump.outputs[0], bsdf.inputs[k])
    Lk.new(bsdf.outputs[0], out.inputs["Surface"])
    mat.blend_method = "HASHED"
    return mat


# =============================================================================================
# meshes
# =============================================================================================
def grid_mesh(name, height, w, h, alpha=None, step=1, x0=0.0, y0=0.0, cut=True, cut_mode="any"):
    """Displaced grid: vertices at texel centres (every ``step`` texels; the outermost ring
    snapped to the exact piece edge), z = height (mm).  Quads whose four corners all have alpha 0
    are dropped (``cut``).  UVs map the piece 0..1 onto the texel images."""
    H = height
    if step > 1:
        ny, nx = H.shape
        ny2, nx2 = ny // step, nx // step
        H = H[:ny2 * step, :nx2 * step].reshape(ny2, step, nx2, step).mean((1, 3))
        if alpha is not None:
            alpha = alpha[:ny2 * step, :nx2 * step].reshape(ny2, step, nx2, step).max((1, 3))
    ny, nx = H.shape
    xs = (np.arange(nx, dtype=np.float64) + 0.5) / nx * w
    ys = (np.arange(ny, dtype=np.float64) + 0.5) / ny * h
    xs[0], xs[-1], ys[0], ys[-1] = 0.0, w, 0.0, h
    X, Y = np.meshgrid(xs, ys)
    co = np.stack([(X + x0 - w / 2) * MM, (h / 2 - Y - y0) * MM, H.astype(np.float64) * MM], -1)
    vid = np.arange(nx * ny).reshape(ny, nx)
    a = vid[:-1, :-1].ravel()
    b = vid[:-1, 1:].ravel()
    c = vid[1:, 1:].ravel()
    d = vid[1:, :-1].ravel()
    quads = np.stack([d, c, b, a], 1)          # CCW seen from above (+z): rows go down in y
    if cut and alpha is not None:
        al = alpha
        if cut_mode == "half":
            # silhouette from the mesh itself (no shader alpha): keep quads whose corner alphas
            # average >= 0.5, i.e. the edge is exact to half a render pixel
            keep = ((al[:-1, :-1] + al[:-1, 1:] + al[1:, 1:] + al[1:, :-1]) >= 2.0).ravel()
        else:
            keep = ((al[:-1, :-1] > 0) | (al[:-1, 1:] > 0) | (al[1:, 1:] > 0) | (al[1:, :-1] > 0)).ravel()
        quads = quads[keep]
    used = np.unique(quads)
    remap = np.full(nx * ny, -1, np.int64)
    remap[used] = np.arange(len(used))
    quads = remap[quads]
    verts = co.reshape(-1, 3)[used]
    u = ((X.ravel() / w))[used]
    v = (1.0 - Y.ravel() / h)[used]
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    nq = len(quads)
    me.loops.add(nq * 4)
    me.loops.foreach_set("vertex_index", quads.astype(np.int32).ravel())
    me.polygons.add(nq)
    me.polygons.foreach_set("loop_start", (np.arange(nq) * 4).astype(np.int32))
    me.polygons.foreach_set("loop_total", np.full(nq, 4, np.int32))
    me.polygons.foreach_set("use_smooth", np.ones(nq, bool))
    uvl = me.uv_layers.new(name="UVMap")
    li = quads.ravel()
    uvl.data.foreach_set("uv", np.stack([u[li], v[li]], 1).astype(np.float32).ravel())
    me.update(calc_edges=True)
    me.validate(clean_customdata=False)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def plate(name, m, w, h, step=1, x0=0.0, y0=0.0, cut=True, shader_alpha=True, **matkw):
    """Maps -> displaced, textured mesh object (see module doc).  With ``step`` > 1 the mesh
    carries the relief box-averaged over step x step texels and the residual goes to a bump."""
    imgs = pack_images(name, m)
    ob = grid_mesh(name, m.height, w, h, alpha=m.alpha if cut else None, step=step, x0=x0, y0=y0,
                   cut=cut, cut_mode="any" if shader_alpha else "half")
    detail = None
    if step > 1:
        from PIL import Image
        H = m.height
        ny, nx = H.shape
        ny2, nx2 = ny // step, nx // step
        coarse = H[:ny2 * step, :nx2 * step].reshape(ny2, step, nx2, step).mean((1, 3))
        up = np.asarray(Image.fromarray(coarse.astype(np.float32), "F").resize((nx, ny),
                        Image.BILINEAR), np.float32)
        res = (H - up).astype(np.float32)
        detail = image(name + "_D", np.dstack([res, res, res, np.ones_like(res)]))
    ob.data.materials.append(relief_material(name + "_Mat", imgs, detail=detail,
                                             shader_alpha=shader_alpha, **matkw))
    return ob


# =============================================================================================
# camera + rig
# =============================================================================================
def camera(w, h, ss, name="CamChrome"):
    """Top-down ortho camera framing the w x h mm piece exactly (render = ss x target)."""
    sc = bpy.context.scene
    sc.render.resolution_x = int(round(w * ss))
    sc.render.resolution_y = int(round(h * ss))
    sc.render.resolution_percentage = 100
    sc["ironart_target"] = (int(round(w)), int(round(h)))
    sc["ironart_supersample"] = int(ss)
    cd = bpy.data.cameras.new(name)
    cd.type = "ORTHO"
    cd.ortho_scale = max(w, h) * MM
    cd.clip_start = 0.001
    cd.clip_end = 10.0
    cam = bpy.data.objects.new(name, cd)
    sc.collection.objects.link(cam)
    cam.location = (0.0, 0.0, 1.0)
    sc.camera = cam
    return cam


def _dir(angle_deg, elev_deg):
    """Top-down camera: screen +x = world +x, screen up = world +y."""
    a, e = math.radians(angle_deg), math.radians(elev_deg)
    return (math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e))


#: the family look numbers (one place; STYLE.md "UI chrome" table is written from this)
RIG = dict(key_angle=135.0, key_elev=50.0, key_soft=2.5, ambient=0.2, flat_gain=1.0,
           arc=1.6, arc_half=62.0, arc_z0=24.0, arc_z1=56.0,
           box_angle=135.0, box_elev=40.0, box_radius=13.0, box=2.4,
           fill_angle=-45.0, fill_half=55.0, fill=0.38,
           top=1.3, top_angle=90.0, top_half=38.0, top_z0=64.0, top_z1=79.0,
           ring=0.3, ceiling=0.08, floor=0.02)


def _ss(e0, e1, x):
    """Blender MapRange SMOOTHSTEP (from e0 -> 0 to e1 -> 1, either order)."""
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def env_map(r, width=1024):
    """The glossy studio environment as an equirectangular linear RGB array (numpy):
    horizon ring, arc softbox above the top-left, round key softbox, overhead strip, cool fill
    arc opposite, dim ceiling, dark floor.  Mapping (our own, evaluated by the world nodes of
    :func:`rig_chrome`): u = atan2(y, x) / 2pi + 0.5, v = asin(z) / pi + 0.5; row 0 of the
    returned array is the top of the image (v = 1, the zenith)."""
    h = width // 2
    u = (np.arange(width) + 0.5) / width
    v = 1.0 - (np.arange(h) + 0.5) / h
    phi = (u - 0.5) * 2 * math.pi
    th = (v - 0.5) * math.pi
    PH, TH = np.meshgrid(phi, th)
    x = np.cos(PH) * np.cos(TH)
    y = np.sin(PH) * np.cos(TH)
    z = np.sin(TH)
    hxy = np.maximum(np.hypot(x, y), 1e-6)
    hx, hy = x / hxy, y / hxy

    def col(c):
        return np.array(palette.lin(c), np.float32).reshape(1, 1, 3)

    def arc(angle, half, soft, z0, z1, zs):
        a = math.radians(angle)
        dt = hx * math.cos(a) + hy * math.sin(a)
        az = _ss(math.cos(math.radians(half + soft)), math.cos(math.radians(max(0.5, half - soft))), dt)
        lo = _ss(math.sin(math.radians(z0 - zs)), math.sin(math.radians(z0 + zs)), z)
        hi = _ss(math.sin(math.radians(z1 + zs)), math.sin(math.radians(z1 - zs)), z)
        return az * lo * hi

    def lobe(angle, elev, radius, soft):
        d = _dir(angle, elev)
        dt = x * d[0] + y * d[1] + z * d[2]
        return _ss(math.cos(math.radians(radius + soft)), math.cos(math.radians(max(0.1, radius - soft))), dt)

    above = _ss(-0.05, 0.02, z)
    ring = _ss(0.55, 0.12, z) * above
    c = ring[..., None] * r["ring"] * col("#FFE9C8")
    c += arc(r["box_angle"], r["arc_half"], 18.0, r["arc_z0"], r["arc_z1"], 5.0)[..., None] * r["arc"] * col("#FFF0DC")
    c += lobe(r["box_angle"], r["box_elev"], r["box_radius"], 4.0)[..., None] * r["box"] * col("#FFF6EA")
    c += arc(r["fill_angle"], r["fill_half"], 20.0, 12.0, 40.0, 6.0)[..., None] * r["fill"] * col("#CCD8EC")
    c += arc(r["top_angle"], r["top_half"], 15.0, r["top_z0"], r["top_z1"], 3.0)[..., None] * r["top"] * col("#FFF4E6")
    c += above[..., None] * r["ceiling"] * col("#FFF6EA")
    c += (1.0 - above)[..., None] * r["floor"] * col("#6B5845")
    return c.astype(np.float32)


def rig_chrome(**over):
    """Calibrated sun + white diffuse ambient + glossy-only studio environment (module doc).
    The environment is baked once into an equirectangular float image (:func:`env_map`): one
    texture lookup per escaping ray instead of a 60-node procedural world (measured 1.6x faster
    per sample, identical look)."""
    r = dict(RIG)
    r.update(over)
    sc = bpy.context.scene
    e = math.radians(r["key_elev"])
    S = (r["flat_gain"] - r["ambient"]) * math.pi / math.sin(e)
    ld = bpy.data.lights.new("Key", "SUN")
    ld.energy = S
    ld.angle = math.radians(r["key_soft"])
    ld.color = (1.0, 1.0, 1.0)
    key = bpy.data.objects.new("Key", ld)
    sc.collection.objects.link(key)
    from mathutils import Vector
    key.rotation_euler = Vector(_dir(r["key_angle"], r["key_elev"])).to_track_quat("Z", "Y").to_euler()

    env = env_map(r)
    img = image("ChromeEnv", np.dstack([env, np.ones(env.shape[:2], np.float32)]))
    w = bpy.data.worlds.new("ChromeWorld")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    N, Lk = nt.nodes, nt.links
    N.clear()
    out = N.new("ShaderNodeOutputWorld")
    amb = N.new("ShaderNodeBackground")
    amb.inputs["Color"].default_value = (1, 1, 1, 1)
    amb.inputs["Strength"].default_value = r["ambient"]
    # direction -> (u, v) exactly as env_map() lays the image out
    tc = N.new("ShaderNodeTexCoord")
    nv = N.new("ShaderNodeVectorMath")
    nv.operation = "NORMALIZE"
    Lk.new(tc.outputs["Generated"], nv.inputs[0])
    sp = N.new("ShaderNodeSeparateXYZ")
    Lk.new(nv.outputs[0], sp.inputs[0])
    at = N.new("ShaderNodeMath")
    at.operation = "ARCTAN2"
    Lk.new(sp.outputs["Y"], at.inputs[0])
    Lk.new(sp.outputs["X"], at.inputs[1])
    uu = N.new("ShaderNodeMath")
    uu.operation = "MULTIPLY_ADD"
    Lk.new(at.outputs[0], uu.inputs[0])
    uu.inputs[1].default_value = 1.0 / (2 * math.pi)
    uu.inputs[2].default_value = 0.5
    asn = N.new("ShaderNodeMath")
    asn.operation = "ARCSINE"
    Lk.new(sp.outputs["Z"], asn.inputs[0])
    vv = N.new("ShaderNodeMath")
    vv.operation = "MULTIPLY_ADD"
    Lk.new(asn.outputs[0], vv.inputs[0])
    vv.inputs[1].default_value = 1.0 / math.pi
    vv.inputs[2].default_value = 0.5
    cv = N.new("ShaderNodeCombineXYZ")
    Lk.new(uu.outputs[0], cv.inputs["X"])
    Lk.new(vv.outputs[0], cv.inputs["Y"])
    et = N.new("ShaderNodeTexImage")
    et.image = img
    et.interpolation = "Linear"
    et.extension = "REPEAT"
    Lk.new(cv.outputs[0], et.inputs["Vector"])
    ref = N.new("ShaderNodeBackground")
    Lk.new(et.outputs["Color"], ref.inputs["Color"])
    ref.inputs["Strength"].default_value = 1.0
    lp = N.new("ShaderNodeLightPath")
    mix = N.new("ShaderNodeMixShader")
    Lk.new(lp.outputs["Is Glossy Ray"], mix.inputs[0])
    Lk.new(amb.outputs[0], mix.inputs[1])
    Lk.new(ref.outputs[0], mix.inputs[2])
    Lk.new(mix.outputs[0], out.inputs["Surface"])
    return {"key": key, "world": w, "params": r, "env": env}


def setup(ss=4, spp=64, transparent=True, view="Standard", look="None", seed=0, adaptive=0.01):
    """Cycles CPU settings for the family (no denoiser: supersampling + adaptive sampling)."""
    from . import scene
    sc = scene.setup_cycles(samples=spp, transparent=transparent, preset="ui", view=view,
                            look=look, seed=seed, clamp_indirect=6.0, adaptive_threshold=adaptive)
    sc.cycles.max_bounces = 4
    sc.cycles.diffuse_bounces = 2
    sc.cycles.glossy_bounces = 3
    sc.cycles.transparent_max_bounces = 8
    sc.cycles.filter_width = 1.2
    return sc
