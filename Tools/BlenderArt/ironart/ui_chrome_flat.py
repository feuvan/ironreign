"""UI chrome family (gongbi): flat orthographic emission / toon passes in Cycles (bpy).

Every UI chrome piece is painted as layers on a :class:`ironart.ui_chrome_paint.Canvas` and
rendered here:

* :func:`plate` - the painted layers as one unlit **emission plate** (a quad framing the camera
  exactly, its image sampled texel-for-pixel with Closest interpolation, alpha through a
  transparent mix): flat colour, no light, no shadow, no specular - the painting's own values.
* :func:`toon_material` - **toon pass** for the few real 3D parts (scroll rollers and knobs):
  emission only, the colour graded by the facing ratio like a gongbi 晕染 wash (pale where the
  form faces the viewer, deepening into the outline), never lit, never glossy.
* :func:`ink` - **Freestyle ink** on those 3D parts only (the plate is excluded), with the
  studio calligraphic line style of :mod:`ironart.ink`.

Scene units: 1 target px = 1 mm.  The piece spans x 0..w, y 0..h (image convention) mapped to
world (-w/2..w/2, +h/2..-h/2) mm, camera looking down -Z.  :func:`to_world` converts.
"""

import bpy
import numpy as np

from . import ui_chrome_paint as P

MM = 0.001


def setup(ss=4, spp=1, transparent=True, filter_width=None, seed=0):
    """Cycles CPU for flat passes: Standard view (colours exact), no denoiser, Box filter.
    With ``spp=1`` the pixel filter is shrunk so each pixel samples exactly its texel (an exact
    pass-through of the painted plate); with 3D parts use ``spp`` >= 16 and a 1 px box."""
    from . import scene
    sc = scene.setup_cycles(samples=spp, transparent=transparent, preset="ui", view="Standard",
                            look="None", seed=seed, adaptive_threshold=0, clamp_indirect=0.0)
    cy = sc.cycles
    cy.max_bounces = 2
    cy.diffuse_bounces = 0
    cy.glossy_bounces = 0
    cy.transmission_bounces = 0
    cy.transparent_max_bounces = 16
    cy.pixel_filter_type = "BOX"
    cy.filter_width = filter_width if filter_width is not None else (0.01 if spp <= 1 else 1.0)
    sc.render.dither_intensity = 0.0 if spp <= 1 else 0.5
    w = bpy.data.worlds.new("Flat") if sc.world is None else sc.world
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs["Strength"].default_value = 0.0
    return sc


def camera(w, h, ss, name="CamFlat"):
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


def to_world(x, y, w, h, z=0.0):
    """Target px (image convention) -> world metres."""
    return ((x - w / 2.0) * MM, (h / 2.0 - y) * MM, z * MM)


def image(name, rgba_srgb):
    """Straight sRGB RGBA float array (row 0 = top) -> packed float image holding *linear* RGB
    (Non-Color, so Cycles reads the values as they are) + alpha."""
    h, w = rgba_srgb.shape[:2]
    old = bpy.data.images.get(name)
    if old is not None:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(name, w, h, alpha=True, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    img.alpha_mode = "STRAIGHT"
    a = np.empty((h, w, 4), np.float32)
    a[..., :3] = P.srgb_to_linear(rgba_srgb[::-1, :, :3])
    a[..., 3] = rgba_srgb[::-1, :, 3]
    img.pixels.foreach_set(np.ascontiguousarray(a).ravel())
    img.pack()
    return img


def plate_material(name, img):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Closest"
    tex.extension = "EXTEND"
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.0
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    L = nt.links
    L.new(tex.outputs["Color"], em.inputs["Color"])
    L.new(tex.outputs["Alpha"], mix.inputs["Fac"])
    L.new(tr.outputs[0], mix.inputs[1])
    L.new(em.outputs[0], mix.inputs[2])
    L.new(mix.outputs[0], out.inputs["Surface"])
    mat.blend_method = "BLEND"
    return mat


def plate(name, rgba_srgb, w, h, z=0.0, x0=0.0, y0=0.0, pw=None, ph=None):
    """Emission plate showing ``rgba_srgb`` over the rectangle (x0, y0, pw, ph) target px of a
    w x h piece (default: the whole frame)."""
    pw = w if pw is None else pw
    ph = h if ph is None else ph
    img = image(name + "_img", rgba_srgb)
    me = bpy.data.meshes.new(name)
    v = [to_world(x0, y0 + ph, w, h, z), to_world(x0 + pw, y0 + ph, w, h, z),
         to_world(x0 + pw, y0, w, h, z), to_world(x0, y0, w, h, z)]
    me.from_pydata(v, [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for i, co in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))):
        uv.data[i].uv = co
    me.materials.append(plate_material(name + "_mat", img))
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.visible_shadow = False
    return ob


def toon_material(name, light, base, dark, edge=0.55, power=1.0, stops=None):
    """Gongbi toon pass: unlit emission whose colour follows the facing ratio (Layer Weight
    'Facing': 0 = facing the camera, 1 = at the silhouette) through a colour ramp
    light -> base (at ``edge``) -> dark, i.e. a 晕染 wash deepening into the outline.
    ``stops`` = [(pos, colour), ...] overrides the three-stop ramp."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    pw = nt.nodes.new("ShaderNodeMath")
    pw.operation = "POWER"
    pw.inputs[1].default_value = power
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.interpolation = "EASE"
    stops = stops or [(0.0, light), (edge, base), (1.0, dark)]
    while len(cr.elements) < len(stops):
        cr.elements.new(0.5)
    for el, (pos, c) in zip(cr.elements, stops):
        el.position = pos
        lin = P.srgb_to_linear(P.rgb(c))
        el.color = (float(lin[0]), float(lin[1]), float(lin[2]), 1.0)
    em = nt.nodes.new("ShaderNodeEmission")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    L = nt.links
    L.new(lw.outputs["Facing"], pw.inputs[0])
    L.new(pw.outputs[0], ramp.inputs["Fac"])
    L.new(ramp.outputs["Color"], em.inputs["Color"])
    L.new(em.outputs[0], out.inputs["Surface"])
    return mat


def ink(collection, thickness_px=1.2, inner_scale=0.6, calligraphy=0.45, pressure_noise=0.15,
        taper=True, color="#1E1A16", crease_angle=150.0, bezier=True, smooth_silhouettes=True):
    """Freestyle calligraphic ink restricted to ``collection`` (the 3D parts; never the plate).
    ``bezier`` = Bezier chain smoothing of the line style; ``smooth_silhouettes`` = Freestyle's
    smooth-normal silhouettes (off: face silhouettes, unbroken on dense lathe meshes)."""
    from . import ink as I
    sets = I.enable(thickness_px=thickness_px, color=color, alpha=1.0, inner_scale=inner_scale,
                    inner_alpha=0.9, crease_angle=crease_angle, border=False, crease=True,
                    material_boundary=True, taper=taper, calligraphy=calligraphy,
                    pressure_noise=pressure_noise, wobble=0.0, smooth=bezier, as_pass=False,
                    collection=collection, outer_select="silhouette")
    bpy.context.view_layer.freestyle_settings.use_smoothness = smooth_silhouettes
    return sets
