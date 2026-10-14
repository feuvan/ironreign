"""Title_Logo.png (1200x400, transparent; the title screen draws it at 960x320):
3D extruded, chisel-bevelled antique-gold "IRON REIGN" (Heading.ttf = Marcellus) under dramatic
studio light, over large flowing brush calligraphy 铁血王座 (Brush.ttf = Ma Shan Zheng) in ink
with gold-leaf flecks, and a red seal.

Layers (back to front):
    calligraphy  a thin ink relief plate: glyphs set as a dynamic composition (sizes, tilt, a
                 rising wave), dry-brush "flying white" streaks from a line-integral convolution
                 along each stroke, feathered ink edges, gold-leaf flakes (tilted metal facets that
                 glint) scattered on and around the strokes
    seal         the 铁血 baiwen impression of Seal.png, smaller, under the last character
    shadow       the gold letters float 14 mm above a shadow catcher, so their soft shadow is part
                 of the logo (legible over light mist and dark backgrounds alike)
    letters      Blender text, extrude 3 mm + 3.6 mm round bevel, antique gold (polished
                 faces, satin bevels, faint wear), lit by a large softbox above the left letters
                 (a highlight sweep across the word), a warm rim from the right and the family
                 studio environment in every bevel
"""

import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import kit
import seal
from ironart import ui_chrome_sdf as S
from ironart.ui_chrome_maps import Maps, L

NAME = "Title_Logo"
SPEC = dict(size=(1200, 400), ss=4, spp=64, seed=81, view="Filmic", look="Medium High Contrast",
            mesh_step=2)
W, H = 1200, 400
TEXT = "IRON REIGN"
TEXT_W = 1000.0            # target width of the gold word (px)
TEXT_CY = 212.0            # its vertical centre (px)
LIFT = 14.0
#: calligraphy layout: (char, cx, cy, height px, rotation deg, shear)
CALLI = [("铁", 188.0, 186.0, 300.0, -6.0, 0.10), ("血", 460.0, 210.0, 255.0, 3.0, 0.06),
         ("王", 738.0, 186.0, 240.0, -3.0, 0.10), ("座", 1010.0, 200.0, 290.0, 5.0, 0.08)]
SEAL = (1132.0, 318.0, 74.0, -4.0)


def font(name):
    from common import FONTS
    return os.path.join(FONTS, name)


def glyph_layer(G):
    """Anti-aliased coverage of the calligraphy composition on the render grid."""
    ss = G.ss
    big = 600
    f = ImageFont.truetype(font("Brush.ttf"), big)
    canvas = Image.new("L", (G.nx, G.ny), 0)
    for ch, cx, cy, hgt, rot, shear in CALLI:
        im = Image.new("L", (big * 2, big * 2), 0)
        ImageDraw.Draw(im).text((big // 2, big // 2), ch, font=f, fill=255)
        im = im.crop(im.getbbox())
        k = hgt * ss / im.height
        im = im.resize((max(1, int(im.width * k)), int(im.height * k)), Image.LANCZOS)
        # italic lean (calligraphic momentum) then tilt
        w0, h0 = im.size
        im = im.transform((w0 + int(abs(shear) * h0), h0), Image.AFFINE,
                          (1, shear, -shear * h0 if shear > 0 else 0, 0, 1, 0), Image.BICUBIC)
        im = im.rotate(rot, Image.BICUBIC, expand=True)
        canvas.paste(Image.new("L", im.size, 255), (int(cx * ss - im.width / 2),
                                                    int(cy * ss - im.height / 2)), im)
    return np.asarray(canvas, np.float32) / 255.0


def lic(noise, angle, length, step):
    """Line integral convolution of ``noise`` along per-pixel directions ``angle`` (radians):
    straight-line samples +-length (pixels) - streaks that follow each brush stroke."""
    h, w = noise.shape
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    ca, sa = np.cos(angle), np.sin(angle)
    acc = np.zeros_like(noise)
    n = 0
    for t in np.arange(-length, length + 1e-3, step):
        x = np.clip(xs + ca * t, 0, w - 1).astype(np.int32)
        y = np.clip(ys + sa * t, 0, h - 1).astype(np.int32)
        acc += noise[y, x]
        n += 1
    return acc / n


def _down(a, k):
    h, w = a.shape
    return a[:h // k * k, :w // k * k].reshape(h // k, k, w // k, k).mean((1, 3))


def _up(a, shape):
    return np.asarray(Image.fromarray(a.astype(np.float32), "F").resize((shape[1], shape[0]),
                      Image.BILINEAR), np.float32)


def stroke_angle(mask, sigma_px, ss):
    """Stroke direction (radians, along the stroke) from the structure tensor of the blurred
    glyph mask, computed at 1 sample per target px and upsampled (tensor components, so the
    interpolation never wraps the angle)."""
    lo = _down(mask, ss)
    b = S.blur(lo, sigma_px)
    gy, gx = np.gradient(b)
    jxx = S.blur(gx * gx, sigma_px * 1.5)
    jyy = S.blur(gy * gy, sigma_px * 1.5)
    jxy = S.blur(gx * gy, sigma_px * 1.5)
    c2 = _up(jxx - jyy, mask.shape)
    s2 = _up(2 * jxy, mask.shape)
    theta = 0.5 * np.arctan2(s2, c2)                     # gradient direction
    return theta + math.pi / 2


def build(G, variant=None):
    ss = G.ss
    m = Maps(G.shape, base="#141110", alpha=0.0)
    g = glyph_layer(G)
    # ---- dry brush ----------------------------------------------------------------------------
    rng = np.random.default_rng(5)
    ang = stroke_angle(g, 5.0, ss)
    noise = rng.random(G.shape).astype(np.float32)
    noise = S.blur(noise, 0.6 * ss)
    streak = lic(noise, ang, 9.0 * ss, 1.0 * ss)
    streak = (streak - streak.mean()) / (streak.std() + 1e-6)
    inner = _up(S.blur(_down(g, ss), 2.2), G.shape)        # ~ distance into the stroke
    patch = S.fbm(G.shape, 55.0 * ss, 9, octaves=3)        # where the brush ran dry
    dry = kit.smoothstep(0.52, 0.75, patch) * (1 - kit.smoothstep(0.55, 0.95, inner)) + \
        0.25 * kit.smoothstep(0.6, 0.8, patch)
    gaps = kit.smoothstep(0.2, 1.1, streak * 0.9 + dry * 1.6 - 0.2)
    cover = g * (1 - 0.92 * gaps * kit.smoothstep(0.15, 0.4, dry + 0.05 * streak))
    # feathered ink edge (bleed into fibres)
    feather = S.blur(cover, 0.35 * ss)
    cover = np.maximum(cover, 0.6 * feather * (S.fibres(G.shape, G.w * G.h * 0.01, 3 * ss,
                                                        0.25 * ss, 13, 0.8, 0.6, 1.0) > 0.2))
    cover = np.clip(cover, 0, 1) * 0.9
    tone = 0.85 + 0.3 * kit.smoothstep(0.3, 0.9, inner)     # wet strokes are blacker
    m.paint(np.ones(G.shape, np.float32), "ink")
    m.tint(np.ones(G.shape, np.float32), 1.6 - 0.6 * tone)
    m.paint(cover, rough=0.32 + 0.25 * (1 - inner))
    z = 0.08 * cover * inner

    # ---- gold-leaf flakes ---------------------------------------------------------------------
    flakes = np.zeros(G.shape, np.float32)
    fz = np.zeros(G.shape, np.float32)
    fl = Image.new("L", (G.nx, G.ny), 0)
    fd = ImageDraw.Draw(fl)
    near = S.blur(_down(g, ss), 18.0)
    idx = 1
    tilt = {}
    for _ in range(1400):
        x, y = 6 + rng.random() * (G.w - 12), 6 + rng.random() * (G.h - 12)
        p = near[min(int(y), near.shape[0] - 1), min(int(x), near.shape[1] - 1)]
        on = g[min(int(y * ss), G.ny - 1), min(int(x * ss), G.nx - 1)]
        if rng.random() > 0.01 + 0.25 * p + 0.35 * on:
            continue
        r = (0.5 + rng.random() ** 2 * 3.2) * (1.0 if rng.random() > 0.1 else 2.0)
        pts = []
        npt = 5 + int(rng.random() * 4)
        for k in range(npt):
            a = 2 * math.pi * k / npt + rng.random() * 0.6
            rr = r * (0.55 + rng.random() * 0.6)
            pts.append(((x + rr * math.cos(a)) * ss, (y + rr * math.sin(a)) * ss))
        fd.polygon(pts, fill=idx)
        tilt[idx] = (rng.random() - 0.5, rng.random() - 0.5, x, y, r)
        idx = idx + 1 if idx < 255 else 1
    lab = np.asarray(fl, np.int32)
    has = lab > 0
    tab = np.zeros((256, 5), np.float32)
    for k, v in tilt.items():
        tab[k] = v
    t = tab[lab]
    fm = has.astype(np.float32)
    fm = S.blur(fm, 0.35)
    flakes = np.clip(fm * 1.4, 0, 1)
    # each flake is a small flat facet tilted at random (up to ~25 deg): they glint one by one
    fz = np.where(has, 0.14 + 0.45 * (t[..., 0] * (G.X - t[..., 2]) + t[..., 1] * (G.Y - t[..., 3])),
                  0.0).astype(np.float32)
    m.paint(flakes, "gold", rough=0.25)
    z = np.maximum(z, fz * flakes)
    alpha = np.clip(cover + flakes, 0, 1)

    # ---- seal ------------------------------------------------------------------------------------
    sx, sy, side, srot = SEAL
    half = side * 0.75
    x0, y0 = int((sx - half)), int((sy - half))
    Gs = S.Grid(2 * half, 2 * half, ss, x0=float(x0), y0=float(y0))
    sm = seal.build(Gs, side=side, rot=srot, seed=63, cx=sx, cy=sy)
    j0, i0 = y0 * ss, x0 * ss
    sl = (slice(j0, j0 + Gs.ny), slice(i0, i0 + Gs.nx))
    sa = sm.alpha
    m.base[sl] = m.base[sl] * (1 - sa[..., None]) + sm.base * sa[..., None]
    for k in ("metal", "rough", "coat", "spec"):
        getattr(m, k)[sl] = getattr(m, k)[sl] * (1 - sa) + getattr(sm, k) * sa
    alpha[sl] = np.maximum(alpha[sl], sa)
    z[sl] = np.maximum(z[sl], sm.height)
    m.height = z.astype(np.float32)
    m.alpha = alpha.astype(np.float32)
    return m


# =============================================================================================
# 3D letters, catcher, lights
# =============================================================================================
def _gold_material():
    import bpy
    from ironart import palette
    mat = bpy.data.materials.new("AntiqueGold")
    mat.use_nodes = True
    nt = mat.node_tree
    N, Lk = nt.nodes, nt.links
    p = N["Principled BSDF"]
    tc = N.new("ShaderNodeTexCoord")
    nz = N.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 18.0
    nz.inputs["Detail"].default_value = 6.0
    Lk.new(tc.outputs["Object"], nz.inputs["Vector"])
    rr = N.new("ShaderNodeMapRange")
    rr.inputs["To Min"].default_value = 0.14
    rr.inputs["To Max"].default_value = 0.34
    Lk.new(nz.outputs["Fac"], rr.inputs["Value"])
    Lk.new(rr.outputs[0], p.inputs["Roughness"])
    col = N.new("ShaderNodeValToRGB")
    col.color_ramp.elements[0].position = 0.3
    col.color_ramp.elements[0].color = palette.lin4("#D9A955")
    col.color_ramp.elements[1].position = 0.75
    col.color_ramp.elements[1].color = palette.lin4("#F2CF85")
    Lk.new(nz.outputs["Fac"], col.inputs[0])
    Lk.new(col.outputs[0], p.inputs["Base Color"])
    p.inputs["Metallic"].default_value = 1.0
    # fine wear (micro scratches) as a bump
    sc = N.new("ShaderNodeTexNoise")
    sc.inputs["Scale"].default_value = 900.0
    sc.inputs["Detail"].default_value = 2.0
    Lk.new(tc.outputs["Object"], sc.inputs["Vector"])
    bp = N.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = 0.08
    Lk.new(sc.outputs["Fac"], bp.inputs["Height"])
    Lk.new(bp.outputs[0], p.inputs["Normal"])
    return mat


def extras(variant, G):
    import bpy
    from mathutils import Vector
    from ironart.ui_chrome_render import MM
    cu = bpy.data.curves.new("Word", "FONT")
    cu.font = bpy.data.fonts.load(font("Heading.ttf"))
    cu.body = TEXT
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.size = 1.0
    cu.space_character = 1.04
    cu.extrude = 0.0
    ob = bpy.data.objects.new("Word", cu)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    dims = ob.dimensions
    k = TEXT_W * MM / max(dims.x, 1e-6)
    cu.size = k
    cu.extrude = 3.0 * MM
    cu.bevel_depth = 3.6 * MM
    cu.bevel_resolution = 4
    cu.offset = -2.0 * MM
    ob.location = (0.0, (H / 2 - TEXT_CY) * MM, (LIFT + 4.0) * MM)
    ob.data.materials.append(_gold_material())
    bpy.context.view_layer.update()
    # shadow catcher under the word
    me = bpy.data.meshes.new("Catcher")
    hw, hh = W / 2 * MM, H / 2 * MM
    me.from_pydata([(-hw, -hh, 0.0), (hw, -hh, 0.0), (hw, hh, 0.0), (-hw, hh, 0.0)], [],
                   [(0, 1, 2, 3)])
    c = bpy.data.objects.new("Catcher", me)
    bpy.context.scene.collection.objects.link(c)
    c.is_shadow_catcher = True
    return ob


def rig(variant):
    """Family studio environment + logo drama: big softbox above the left letters (highlight
    sweep), warm rim from the right, cool kicker from the lower left."""
    import bpy
    from mathutils import Vector
    from ironart import palette
    from ironart import ui_chrome_render as R
    from ironart.ui_chrome_render import MM
    R.rig_chrome(ambient=0.12, top=0.6, box=3.0, arc=1.9, ring=0.6)

    def area(name, loc, size, power, col, target=(0, 0, 0), size_y=None):
        ld = bpy.data.lights.new(name, "AREA")
        ld.shape = "RECTANGLE"
        ld.size = size * MM
        ld.size_y = (size_y or size) * MM
        ld.energy = power
        ld.color = palette.lin(col)
        ob = bpy.data.objects.new(name, ld)
        bpy.context.scene.collection.objects.link(ob)
        ob.location = Vector(loc) * MM
        d = Vector(target) * MM - ob.location
        ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        return ob
    area("Softbox", (-330.0, 110.0, 620.0), 520.0, 260.0, "#FFF1DC", (-330.0, 60.0, 0.0), 260.0)
    area("Rim", (900.0, 60.0, 160.0), 140.0, 90.0, "#FFC98A", (200.0, 0.0, 20.0), 500.0)
    area("Kick", (-800.0, -260.0, 220.0), 160.0, 30.0, "#BFD3FF", (-200.0, 0.0, 20.0), 400.0)
