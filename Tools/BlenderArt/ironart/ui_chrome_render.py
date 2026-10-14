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
def image(name, arr):
    """float32 (rows, cols, 4) array (row 0 = top) -> packed, linear (Non-Color) float image."""
    h, w = arr.shape[:2]
    old = bpy.data.images.get(name)
    if old is not None:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(name, w, h, alpha=True, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    img.alpha_mode = "CHANNEL_PACKED"
    img.pixels.foreach_set(np.ascontiguousarray(arr[::-1], dtype=np.float32).ravel())
    img.pack()
    return img


def pack_images(name, m):
    c = np.dstack([m.base, m.alpha])
    p = np.dstack([m.metal, m.rough, m.coat, m.spec])
    e = np.dstack([m.emit, m.mop])
    return image(name + "_C", c), image(name + "_P", p), image(name + "_E", e)


# =============================================================================================
# material
# =============================================================================================
def relief_material(name, imgs, coat_roughness=0.045, interpolation="Linear", emission=1.0,
                    detail=None):
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
        td.interpolation = "Cubic"
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
def grid_mesh(name, height, w, h, alpha=None, step=1, x0=0.0, y0=0.0, cut=True):
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


def plate(name, m, w, h, step=1, x0=0.0, y0=0.0, cut=True, **matkw):
    """Maps -> displaced, textured mesh object (see module doc).  With ``step`` > 1 the mesh
    carries the relief box-averaged over step x step texels and the residual goes to a bump."""
    imgs = pack_images(name, m)
    ob = grid_mesh(name, m.height, w, h, alpha=m.alpha if cut else None, step=step, x0=x0, y0=y0,
                   cut=cut)
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
    ob.data.materials.append(relief_material(name + "_Mat", imgs, detail=detail, **matkw))
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


def rig_chrome(**over):
    """Calibrated sun + white diffuse ambient + glossy-only studio environment (module doc)."""
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
    tc = N.new("ShaderNodeTexCoord")
    dirv = N.new("ShaderNodeVectorMath")
    dirv.operation = "NORMALIZE"
    Lk.new(tc.outputs["Generated"], dirv.inputs[0])

    def lobe(angle, elev, radius_deg, soft_deg):
        dv = N.new("ShaderNodeVectorMath")
        dv.operation = "DOT_PRODUCT"
        Lk.new(dirv.outputs[0], dv.inputs[0])
        dv.inputs[1].default_value = _dir(angle, elev)
        mr = N.new("ShaderNodeMapRange")
        mr.interpolation_type = "SMOOTHSTEP"
        mr.inputs["From Min"].default_value = math.cos(math.radians(radius_deg + soft_deg))
        mr.inputs["From Max"].default_value = math.cos(math.radians(max(0.1, radius_deg - soft_deg)))
        Lk.new(dv.outputs["Value"], mr.inputs["Value"])
        return mr.outputs[0]

    def scaled(sock, k, col):
        m = N.new("ShaderNodeMix")
        m.data_type = "RGBA"
        m.blend_type = "MULTIPLY"
        m.inputs[0].default_value = 1.0
        cm = N.new("ShaderNodeCombineColor")
        for ch in ("Red", "Green", "Blue"):
            mm = N.new("ShaderNodeMath")
            mm.operation = "MULTIPLY"
            Lk.new(sock, mm.inputs[0])
            mm.inputs[1].default_value = k
            Lk.new(mm.outputs[0], cm.inputs[ch])
        Lk.new(cm.outputs[0], m.inputs[6])
        m.inputs[7].default_value = palette.lin4(col)
        return m.outputs[2]

    def add(a, b):
        m = N.new("ShaderNodeMix")
        m.data_type = "RGBA"
        m.blend_type = "ADD"
        m.inputs[0].default_value = 1.0
        Lk.new(a, m.inputs[6])
        Lk.new(b, m.inputs[7])
        return m.outputs[2]

    sep = N.new("ShaderNodeSeparateXYZ")
    Lk.new(dirv.outputs[0], sep.inputs[0])
    # horizon ring (z 0 .. 0.45) and ceiling (z > 0.45); ground below
    ring = N.new("ShaderNodeMapRange")
    ring.interpolation_type = "SMOOTHSTEP"
    ring.inputs["From Min"].default_value = 0.55
    ring.inputs["From Max"].default_value = 0.12
    Lk.new(sep.outputs["Z"], ring.inputs["Value"])
    above = N.new("ShaderNodeMapRange")
    above.interpolation_type = "SMOOTHSTEP"
    above.inputs["From Min"].default_value = -0.05
    above.inputs["From Max"].default_value = 0.02
    Lk.new(sep.outputs["Z"], above.inputs["Value"])
    ringm = N.new("ShaderNodeMath")
    ringm.operation = "MULTIPLY"
    Lk.new(ring.outputs[0], ringm.inputs[0])
    Lk.new(above.outputs[0], ringm.inputs[1])
    c = scaled(ringm.outputs[0], r["ring"], "#FFE9C8")

    def arc(angle, half_deg, soft_deg, z0, z1, zsoft):
        """Azimuthal arc softbox: azimuth within +-half of ``angle``, elevation z0..z1 (deg)."""
        hv = N.new("ShaderNodeVectorMath")
        hv.operation = "MULTIPLY"
        Lk.new(dirv.outputs[0], hv.inputs[0])
        hv.inputs[1].default_value = (1.0, 1.0, 0.0)
        hn = N.new("ShaderNodeVectorMath")
        hn.operation = "NORMALIZE"
        Lk.new(hv.outputs[0], hn.inputs[0])
        dt = N.new("ShaderNodeVectorMath")
        dt.operation = "DOT_PRODUCT"
        Lk.new(hn.outputs[0], dt.inputs[0])
        a = math.radians(angle)
        dt.inputs[1].default_value = (math.cos(a), math.sin(a), 0.0)
        az = N.new("ShaderNodeMapRange")
        az.interpolation_type = "SMOOTHSTEP"
        az.inputs["From Min"].default_value = math.cos(math.radians(half_deg + soft_deg))
        az.inputs["From Max"].default_value = math.cos(math.radians(max(0.5, half_deg - soft_deg)))
        Lk.new(dt.outputs["Value"], az.inputs["Value"])
        lo = N.new("ShaderNodeMapRange")
        lo.interpolation_type = "SMOOTHSTEP"
        lo.inputs["From Min"].default_value = math.sin(math.radians(z0 - zsoft))
        lo.inputs["From Max"].default_value = math.sin(math.radians(z0 + zsoft))
        Lk.new(sep.outputs["Z"], lo.inputs["Value"])
        hi = N.new("ShaderNodeMapRange")
        hi.interpolation_type = "SMOOTHSTEP"
        hi.inputs["From Min"].default_value = math.sin(math.radians(z1 + zsoft))
        hi.inputs["From Max"].default_value = math.sin(math.radians(z1 - zsoft))
        Lk.new(sep.outputs["Z"], hi.inputs["Value"])
        m1 = N.new("ShaderNodeMath")
        m1.operation = "MULTIPLY"
        Lk.new(az.outputs[0], m1.inputs[0])
        Lk.new(lo.outputs[0], m1.inputs[1])
        m2 = N.new("ShaderNodeMath")
        m2.operation = "MULTIPLY"
        Lk.new(m1.outputs[0], m2.inputs[0])
        Lk.new(hi.outputs[0], m2.inputs[1])
        return m2.outputs[0]

    c = add(c, scaled(arc(r["box_angle"], r["arc_half"], 18.0, r["arc_z0"], r["arc_z1"], 5.0),
                      r["arc"], "#FFF0DC"))
    c = add(c, scaled(lobe(r["box_angle"], r["box_elev"], r["box_radius"], 4.0), r["box"], "#FFF6EA"))
    c = add(c, scaled(arc(r["fill_angle"], r["fill_half"], 20.0, 12.0, 40.0, 6.0), r["fill"],
                      "#CCD8EC"))
    c = add(c, scaled(arc(r["top_angle"], r["top_half"], 15.0, r["top_z0"], r["top_z1"], 3.0),
                      r["top"], "#FFF4E6"))
    c = add(c, scaled(above.outputs[0], r["ceiling"], "#FFF6EA"))
    flo = N.new("ShaderNodeMath")
    flo.operation = "SUBTRACT"
    flo.inputs[0].default_value = 1.0
    Lk.new(above.outputs[0], flo.inputs[1])
    c = add(c, scaled(flo.outputs[0], r["floor"], "#6B5845"))
    ref = N.new("ShaderNodeBackground")
    Lk.new(c, ref.inputs["Color"])
    ref.inputs["Strength"].default_value = 1.0
    lp = N.new("ShaderNodeLightPath")
    mix = N.new("ShaderNodeMixShader")
    Lk.new(lp.outputs["Is Glossy Ray"], mix.inputs[0])
    Lk.new(amb.outputs[0], mix.inputs[1])
    Lk.new(ref.outputs[0], mix.inputs[2])
    Lk.new(mix.outputs[0], out.inputs["Surface"])
    return {"key": key, "world": w, "params": r}


def setup(ss=4, spp=64, transparent=True, view="Standard", look="None", seed=0):
    """Cycles CPU settings for the family (no denoiser: supersampling + adaptive sampling)."""
    from . import scene
    sc = scene.setup_cycles(samples=spp, transparent=transparent, preset="ui", view=view,
                            look=look, seed=seed, clamp_indirect=6.0)
    sc.cycles.max_bounces = 6
    sc.cycles.glossy_bounces = 4
    sc.cycles.transparent_max_bounces = 8
    sc.cycles.filter_width = 1.2
    return sc
