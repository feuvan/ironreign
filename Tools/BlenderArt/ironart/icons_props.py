"""Icons family (gongbi): reusable prop builders shared by several icons.

Each builder returns a list of mesh objects built around its own origin in the icon conventions
of :mod:`ironart.icons_kit` (+Z up, front -Y, ~1-2 units).  Callers place the result with
:func:`group` (parent empty).  Materials come from the family pigment library
(``icons/common.py``: ``M[key]``); props that need their own pigment (brush hair, glyph paper,
banner cloth with a painted character) build it with :func:`ironart.icons_gongbi.pigment`.

Modelling rules for the gongbi look: no bevels on hard edges (the ink draws every edge as a
crease, 界画), enough segments that curves stay round at 512 px, real separate parts where a
painter would draw a line.
"""

import math
import random

import bpy
from mathutils import Vector

from . import icons_gongbi as gb
from . import icons_kit as K

TAU = math.tau
FACE = -24.0          # yaw that turns a prop's -Y face square to the family camera


def group(name, objs, loc=(0, 0, 0), rot=(0, 0, 0), scale=1.0):
    """Parent ``objs`` to a new empty placed at loc/rot/scale (degrees). Returns the objects."""
    e = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(e)
    roots = []
    for o in objs:
        r = o
        while r.parent is not None:
            r = r.parent
        if r not in roots:
            roots.append(r)
    for r in roots:
        r.parent = e
    K.place(e, loc, rot, scale)
    bpy.context.view_layer.update()
    return list(objs)


def _rng(seed):
    return random.Random(seed)


def _zgrad(z0, z1, k=1.0):
    def fn(b):
        co = b.sep(gb.obj_coord(b))
        return b.maprange(co[2], z0, z1, k, 0.0)
    return fn


# ---------------------------------------------------------------------------------------------
# images (Pillow) for glyphs and seal impressions
# ---------------------------------------------------------------------------------------------
def glyph_image(name, chars, font, size=512, fill=0.82, columns=None, aspect=1.0, color=(0, 0, 0)):
    """Calligraphy texture: alpha = ink.  ``columns`` = strings written top-to-bottom,
    right-to-left (scroll text); ``aspect`` = width / height of the surface it maps onto."""
    from PIL import Image, ImageDraw, ImageFont
    W, H = (size, int(size / aspect)) if aspect >= 1 else (int(size * aspect), size)
    im = Image.new("RGBA", (W, H), color + (0,))
    d = ImageDraw.Draw(im)
    if columns:
        ncol = len(columns)
        nrow = max(len(c) for c in columns)
        cell = int(min(W / (ncol * 1.15), H / (nrow * 1.05)) * fill)
        f = ImageFont.truetype(font, cell)
        for ci, col in enumerate(columns):
            x = W - (ci + 0.5) * W / ncol
            for ri, ch in enumerate(col):
                y = (ri + 0.5) * H / nrow
                d.text((x, y), ch, font=f, fill=color + (255,), anchor="mm")
    else:
        f = ImageFont.truetype(font, int(min(W, H) * fill))
        d.text((W / 2, H / 2), chars, font=f, fill=color + (255,), anchor="mm")
    return K.pil_image(name, im)


def seal_image(name, glyph, font, size=256, invert=True, border=0.07, rotate=2.0, seed=3):
    """Seal impression texture (alpha = paste): 白文 (``invert``: carved glyph shows the paper)
    or 朱文 (raised glyph and frame).  Worn speckles knock the paste out here and there."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    im = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(im)
    b = int(size * border)
    f = ImageFont.truetype(font, int(size * (0.74 if invert else 0.68)))
    if invert:
        d.rounded_rectangle([b, b, size - b, size - b], radius=size * 0.04, fill=255)
        d.text((size / 2, size / 2), glyph, font=f, fill=0, anchor="mm")
    else:
        w = max(3, int(size * 0.06))
        d.rounded_rectangle([b, b, size - b, size - b], radius=size * 0.04, outline=255, width=w)
        d.text((size / 2, size / 2 + size * 0.02), glyph, font=f, fill=255, anchor="mm")
    a = np.asarray(im, np.float32) / 255.0
    rng = np.random.default_rng(seed)
    a *= (rng.random(a.shape) > 0.04)
    im = Image.fromarray((a * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(0.7))
    if rotate:
        im = im.rotate(rotate, resample=Image.BICUBIC)
    rgba = Image.merge("RGBA", (im.point(lambda v: 181), im.point(lambda v: 56),
                                im.point(lambda v: 42), im))
    return K.pil_image(name, rgba)


# ---------------------------------------------------------------------------------------------
# gold ingot (yuanbao / sycee)
# ---------------------------------------------------------------------------------------------
def yuanbao(name, mat, L=1.0, W=0.62, rim=0.2, wing=0.2, trough=0.1, dome=(0.26, 0.24, 0.17),
            lip=(0.07, 0.035), flare=0.22, sq=2.6, nu=96, nv=64, boss_mat=None, boss_lift=0.15):
    """A boat-shaped ingot: a closed parametric shell (bowl outside, rolled lip, trough inside)
    with high flaring ends, plus a domed boss in the middle of the trough."""
    lw, lh = lip

    def fn(u, v):
        phi = TAU * u
        c, s = math.cos(phi), math.sin(phi)
        end = abs(c) ** 2.5
        rz = rim + wing * end
        if v <= 0.5:
            t = v / 0.5
            r = 0.72 * t ** 0.45 + 0.28 * t ** 2.0
            z = rz * t ** 1.35
            fx = 1.0 + flare * end * t ** 2
        elif v <= 0.62:
            t = (v - 0.5) / 0.12
            th = math.pi * t
            r = 1.0 - lw * (1 - math.cos(th)) / 2.0
            z = rz + lh * math.sin(th)
            fx = 1.0 + flare * end
        else:
            t = (v - 0.62) / 0.38
            r = (1.0 - lw) * (1.0 - t) ** 0.8
            z = rz - (rz - trough) * (1.0 - (1.0 - t) ** 2.2)
            fx = 1.0 + flare * end * (1.0 - t) ** 2
        sc = math.copysign(abs(c) ** (2.0 / sq), c)
        sn = math.copysign(abs(s) ** (2.0 / sq), s)
        return (L / 2.0 * r * sc * fx, W / 2.0 * r * sn, z)

    shell = K.grid(name + "_shell", fn, nu, nv, mat, smooth=True, uv=True)
    K._merge(shell, 1e-6)
    boss = K.sphere(name + "_boss", 1.0, boss_mat or mat, 48, 24, scale=dome)
    boss.location = (0, 0, trough + dome[2] * boss_lift)
    return [shell, boss]


# ---------------------------------------------------------------------------------------------
# small helpers: tassel, cord, coin
# ---------------------------------------------------------------------------------------------
def tassel(name, mat, top=(0, 0, 0), length=0.45, radius=0.06, cap_mat=None, sway=0.0,
           knot=True):
    """A silk tassel hanging from ``top`` (-Z) as ONE soft volume (a painter draws a tassel as a
    shape with a few inner strokes, not as hairs): knot bead, wrapped head, flaring skirt."""
    t = Vector(top)
    L = length
    prof = [(0.0, 0.0), (radius * 1.15, 0.02 * L), (radius * 1.25, 0.1 * L),
            (radius * 0.98, 0.42 * L), (radius * 0.72, 0.62 * L), (radius * 0.62, 0.7 * L),
            (radius * 0.75, 0.74 * L), (radius * 0.72, 0.8 * L), (radius * 0.45, 0.86 * L),
            (0.0, 0.88 * L)]
    body = K.lathe(name + "_skirt", prof, mat, 32)
    body.location = t + Vector((0, 0, -L))
    if sway:
        body.rotation_euler = (0.0, math.radians(sway), 0.0)
    out = [body]
    if knot:
        kb = K.sphere(name + "_knot", radius * 0.7, cap_mat or mat, 24, 12)
        kb.location = t + Vector((0, 0, -0.04 * L))
        out.append(kb)
    return out


def cord(name, mat, points, r=0.012, res=10):
    return K.curve_tube(name, points, r, mat, bevel_res=4, resolution=res)


def coin(name, mat, r=0.2, t=0.035, hole=0.055):
    """Copper cash coin (圆形方孔): disc with a raised rim and a square hole, faces -Y."""
    n = 64
    outer = [(r * math.cos(TAU * i / n), r * math.sin(TAU * i / n)) for i in range(n)]
    h = hole
    sq = [(-h, -h), (h, -h), (h, h), (-h, h)]
    disc = K.outline_mesh(name, outer, t, mat, plane="XZ", holes=[sq])
    rim = K.torus(name + "_rim", r * 0.93, t * 0.35, mat, 64, 8)
    K.place(rim, (0, -t / 2, 0), (90, 0, 0))
    return [disc, rim]


# ---------------------------------------------------------------------------------------------
# scrolls, brush, seals
# ---------------------------------------------------------------------------------------------
def scroll_rolled(name, M, length=1.5, r=0.15, outer="silk_blue", knob="jade", tie="rope_red",
                  label=True):
    """A rolled scroll along local X: silk-mounted roll, a pale title slip, two turns of cord
    and turned knobs at both ends."""
    objs = []
    body = K.lathe(name + "_roll", [(0.0, -length / 2), (r, -length / 2), (r, length / 2),
                                   (0.0, length / 2)], M[outer], 64)
    K.place(body, (0, 0, 0), (0, 90, 0))
    objs.append(body)
    for sgn in (-1, 1):
        kn = K.lathe(name + "_knob%d" % sgn, [(0.0, 0.0), (r * 0.5, 0.0), (r * 0.62, 0.05),
                                              (r * 0.66, 0.1), (r * 0.56, 0.15),
                                              (r * 0.3, 0.18), (0.0, 0.185)], M[knob], 32)
        K.place(kn, (sgn * (length / 2), 0, 0), (0, 90 * sgn, 0))
        objs.append(kn)
        endp = K.lathe(name + "_end%d" % sgn, [(r * 0.5, 0.0), (r * 0.985, 0.0),
                                               (r * 0.985, 0.004), (r * 0.5, 0.004)],
                       M["paper"], 48)
        K.place(endp, (sgn * (length / 2 + 0.001), 0, 0), (0, 90 * sgn, 0))
        objs.append(endp)
    if label:
        slip = K.grid(name + "_slip", lambda u, v: (
            -length * 0.38 + u * length * 0.34,
            -math.cos((v - 0.5) * 1.2) * r * 1.012,
            math.sin((v - 0.5) * 1.2) * r * 1.012), 8, 8, M["paper"])
        K.place(slip, (0, 0, 0), (-30, 0, 0))
        objs.append(slip)
    if tie:
        for k, dx in enumerate((0.0, 0.045)):
            ring = K.torus(name + "_tie%d" % k, r * 1.02, 0.016, M[tie], 64, 10)
            K.place(ring, (length * 0.14 + dx, 0, 0), (0, 90, 0))
            objs.append(ring)
    return objs


def paper_text(name, columns, font, aspect, light="#F6F0E2", deep="#D4C4A2"):
    """Paper pigment carrying calligraphy columns (ink glyphs through the ic_ink AOV)."""
    img = glyph_image(name + "_txt", None, font, 512, 0.86, columns=columns, aspect=aspect,
                      color=(42, 36, 30))
    return gb.pigment(name, light, deep, fen=0.4, formk=0.12, image=img, image_color="#3A322A")


def handscroll_open(name, M, w=1.5, h=0.9, paper=None, curl=0.06, roller="wood_dark",
                    knob="jade", border="silk_blue", r=0.07):
    """An unrolled scroll standing in local XZ facing -Y: paper field framed by silk borders
    (upper / lower), a roller with knobs at each end, a gentle wave."""
    objs = []
    pm = paper or M["paper"]

    def wave(u):
        return curl * math.sin(u * math.pi * 1.6 + 0.4) * 0.6

    s = K.grid(name + "_sheet", lambda u, v: (-w / 2 + u * w, wave(u), -h / 2 + v * h),
               48, 2, pm, thickness=0.0)
    objs.append(s)
    bh = 0.11
    for k, z0 in enumerate((-h / 2 - bh, h / 2)):
        b = K.grid(name + "_band%d" % k, lambda u, v, z0=z0: (-w / 2 + u * w, wave(u),
                                                              z0 + v * bh), 48, 1, M[border])
        objs.append(b)
    for sgn in (-1, 1):
        u = 0.0 if sgn < 0 else 1.0
        y0 = wave(u)
        H2 = h / 2 + bh + 0.03
        rod = K.lathe(name + "_rod%d" % sgn, [(0.0, -H2), (r, -H2), (r, H2), (0.0, H2)],
                      M[roller], 32)
        rod.location = (sgn * (w / 2 + r * 0.8), y0, 0)
        objs.append(rod)
        for zs in (-1, 1):
            kn = K.lathe(name + "_kn%d%d" % (sgn, zs), [(0.0, 0.0), (r * 0.8, 0.0),
                                                         (r * 1.05, 0.035), (r * 0.95, 0.08),
                                                         (r * 0.55, 0.1), (0.0, 0.105)],
                         M[knob], 24)
            K.place(kn, (sgn * (w / 2 + r * 0.8), y0, zs * H2), (0 if zs > 0 else 180, 0, 0))
            objs.append(kn)
    return objs


def brush(name, M, length=1.2, r=0.035, handle="bamboo", tip_len=0.28, loop=True):
    """Writing brush along local +Z (tip at z = 0): bamboo handle with nodes, dark ferrule, a full
    hair head pale at the root and ink-black at the point, a hanging loop."""
    objs = []
    hair = gb.pigment("I_BrushHair_" + name, "#EFE6D0", "#2A241E", fen=0.25, formk=0.05,
                      grad=_zgrad(tip_len * 0.15, tip_len * 0.75, 1.0))
    head = K.lathe(name + "_hair", [(0.0, 0.0), (r * 0.3, 0.025), (r * 0.95, tip_len * 0.35),
                                    (r * 1.3, tip_len * 0.62), (r * 1.2, tip_len * 0.88),
                                    (r * 1.05, tip_len)], hair, 32)
    objs.append(head)
    fer = K.lathe(name + "_ferrule", [(0.0, tip_len), (r * 1.2, tip_len),
                                      (r * 1.2, tip_len + 0.07), (0.0, tip_len + 0.07)],
                  M["lacquer_black"], 32)
    objs.append(fer)
    h = K.lathe(name + "_handle", [(0.0, tip_len + 0.07), (r, tip_len + 0.07),
                                   (r * 0.92, length - 0.07), (0.0, length - 0.07)],
                M[handle], 32)
    objs.append(h)
    cap = K.lathe(name + "_cap", [(0.0, length - 0.07), (r * 1.12, length - 0.07),
                                  (r * 1.12, length), (0.0, length)], M["lacquer_black"], 32)
    objs.append(cap)
    if loop:
        lp = K.torus(name + "_loop", 0.055, 0.009, M["rope_red"], 32, 8)
        K.place(lp, (0, 0, length + 0.05), (90, 0, 0))
        objs.append(lp)
    return objs


def seal_block(name, M, size=0.5, height=0.42, mat="jade", knob_mat=None, tassel_mat="tassel_red",
               knob="beast"):
    """A square seal of office: stepped block with a crouching-beast knob (metaballs) and a cord
    ring for the tassel."""
    objs = []
    base = K.box(name + "_base", (size, size, height * 0.55), M[mat])
    base.location = (0, 0, height * 0.275)
    objs.append(base)
    top = K.box(name + "_top", (size * 0.86, size * 0.86, height * 0.09), M[mat])
    top.location = (0, 0, height * 0.55 + height * 0.045)
    objs.append(top)
    km = M[knob_mat or mat]
    s = size
    z0 = height * 0.64
    if knob == "tortoise":
        els = [dict(type="ELLIPSOID", co=(0.0, 0.0, z0 + 0.02 * s), radius=0.3 * s,
                    size=(1.0, 0.8, 0.45)),
               dict(type="ELLIPSOID", co=(-0.3 * s, 0.0, z0 + 0.04 * s), radius=0.09 * s,
                    size=(1.3, 0.9, 0.8))]
        objs.append(K.metaball(name + "_knob", els, km, resolution=0.012 * s / 0.5,
                               threshold=0.6))
        if tassel_mat:
            ring = K.torus(name + "_cord", 0.06 * s, 0.018 * s, M[tassel_mat], 32, 8)
            K.place(ring, (0.3 * s, 0.0, z0 + 0.04 * s), (0, 90, 0))
            objs.append(ring)
        return objs
    els = [
        dict(type="ELLIPSOID", co=(0.03 * s, 0.05 * s, z0 + 0.12 * s), radius=0.3 * s,
             size=(0.85, 0.5, 0.42)),
        dict(type="BALL", co=(-0.2 * s, -0.08 * s, z0 + 0.2 * s), radius=0.19 * s),
        dict(type="BALL", co=(-0.27 * s, -0.17 * s, z0 + 0.17 * s), radius=0.1 * s),
        dict(type="ELLIPSOID", co=(-0.12 * s, -0.12 * s, z0 + 0.04 * s), radius=0.12 * s,
             size=(0.8, 1.3, 0.6)),
        dict(type="ELLIPSOID", co=(0.2 * s, -0.12 * s, z0 + 0.04 * s), radius=0.12 * s,
             size=(0.9, 1.3, 0.6)),
        dict(type="ELLIPSOID", co=(0.28 * s, 0.14 * s, z0 + 0.18 * s), radius=0.1 * s,
             size=(1.6, 0.6, 0.6), rot=(0, -30, 0)),
        dict(type="ELLIPSOID", co=(0.02 * s, 0.05 * s, z0 + 0.0 * s), radius=0.32 * s,
             size=(1.0, 0.7, 0.25)),
    ]
    beast = K.metaball(name + "_knob", els, km, resolution=0.014 * s / 0.5, threshold=0.6)
    objs.append(beast)
    if tassel_mat:
        ring = K.torus(name + "_cord", 0.07 * s, 0.02 * s, M[tassel_mat], 32, 8)
        K.place(ring, (0.06 * s, 0.05 * s, z0 + 0.03 * s), (0, 90, 0))
        objs.append(ring)
    return objs


# ---------------------------------------------------------------------------------------------
# weapons
# ---------------------------------------------------------------------------------------------
def jian(name, M, length=1.9, blade_w=0.085, guard="gold", grip="silk_ink", tassel=True,
         blade="steel"):
    """Straight double-edged sword along local +Z (tip up, edge planes facing -Y): a diamond
    section blade with a ridge, a winged gold guard, cord-wrapped grip, gold pommel, tassel."""
    objs = []
    gl = 0.36                         # grip length
    bl = length - gl - 0.06
    secs = []
    for k in range(13):
        t = k / 12.0
        z = 0.06 + t * bl
        w = blade_w * (1.0 - 0.12 * t) if t < 0.86 else blade_w * 0.88 * max(0.0, 1 - (t - 0.86) / 0.14) ** 0.8
        w = max(w, 0.002)
        d = w * 0.22
        secs.append([(-w, 0.0, z), (0.0, -d, z), (w, 0.0, z), (0.0, d, z)])
    secs[-1] = [(0.0, 0.0, 0.06 + bl)] * 4
    b = K.loft(name + "_blade", secs, M[blade], cap0=True, cap1=False, smooth=False)
    objs.append(b)
    # guard: a winged bar
    g = K.outline_mesh(name + "_guard", [(-0.2, -0.02), (-0.13, -0.055), (0.0, -0.035),
                                         (0.13, -0.055), (0.2, -0.02), (0.13, 0.05),
                                         (0.0, 0.08), (-0.13, 0.05)], 0.09, M[guard],
                       plane="XZ")
    g.location = (0, 0, 0.03)
    objs.append(g)
    gr = K.lathe(name + "_grip", [(0.0, -gl), (0.036, -gl), (0.04, -gl * 0.5), (0.036, 0.0),
                                  (0.0, 0.0)], M[grip], 24)
    objs.append(gr)
    pm = K.lathe(name + "_pommel", [(0.0, -gl - 0.075), (0.03, -gl - 0.075),
                                    (0.058, -gl - 0.045), (0.05, -gl - 0.01), (0.03, -gl),
                                    (0.0, -gl)], M[guard], 24)
    objs.append(pm)
    if tassel:
        objs += tassel_fn(name + "_ts", M["tassel_red"], (0, 0, -gl - 0.075), 0.32, 0.05)
    return objs


tassel_fn = tassel


def dao(name, M, length=1.8, blade_w=0.13):
    """Sabre (刀) along +Z: single-edged blade curving back towards the tip, ring guard, grip."""
    objs = []
    gl = 0.36
    bl = length - gl
    n = 16
    secs = []
    for k in range(n + 1):
        t = k / n
        z = 0.03 + t * bl
        bend = 0.18 * t ** 2
        w = blade_w * (1.0 + 0.25 * t) if t < 0.82 else blade_w * 1.25 * max(0.0, 1 - (t - 0.82) / 0.18) ** 0.7
        w = max(w, 0.002)
        back = bend
        edge = bend - w
        d = 0.018 * (1 - t * 0.6)
        secs.append([(back, 0.0, z), (back - w * 0.5, -d, z), (edge, 0.0, z), (back - w * 0.5, d, z)])
    secs[-1] = [(secs[-1][0][0] - 0.02, 0.0, 0.03 + bl + 0.03)] * 4
    objs.append(K.loft(name + "_blade", secs, M["steel"], cap0=True, cap1=False, smooth=False))
    gd = K.torus(name + "_guard", 0.07, 0.018, M["gold"], 32, 8, scale_minor=(1.0, 1.0))
    K.place(gd, (-0.06, 0, 0.0), (0, 0, 0))
    objs.append(gd)
    objs.append(K.lathe(name + "_grip", [(0.0, -gl), (0.034, -gl), (0.038, 0.0), (0.0, 0.0)],
                        M["silk_ink"], 20))
    return objs


def spear(name, M, length=2.4, head="steel", shaft="wood", tassel=True, r=0.028):
    """Spear along +Z (head up): shaft, socket, leaf-shaped head with a ridge, red horsehair
    tassel (红缨) under the head, a small butt cap."""
    objs = []
    hl = 0.34
    sl = length - hl
    objs.append(K.lathe(name + "_shaft", [(0.0, 0.0), (r, 0.0), (r * 0.9, sl), (0.0, sl)],
                        M[shaft], 16))
    objs.append(K.lathe(name + "_butt", [(0.0, -0.06), (r * 1.15, -0.06), (r * 1.15, 0.04),
                                         (0.0, 0.04)], M["iron"], 16))
    objs.append(K.lathe(name + "_socket", [(0.0, sl - 0.04), (r * 1.25, sl - 0.04),
                                           (r * 1.1, sl + 0.07), (0.0, sl + 0.07)],
                        M["iron"], 16))
    secs = []
    for k in range(11):
        t = k / 10.0
        z = sl + 0.06 + t * (hl - 0.06)
        w = 0.085 * math.sin(math.pi * min(1.0, 0.25 + t * 0.95)) ** 0.9 * (1 - t) ** 0.25
        w = max(w, 0.003)
        d = max(w * 0.25, 0.012 * (1 - t))
        secs.append([(-w, 0.0, z), (0.0, -d, z), (w, 0.0, z), (0.0, d, z)])
    secs[-1] = [(0.0, 0.0, sl + hl)] * 4
    objs.append(K.loft(name + "_head", secs, M[head], cap0=True, cap1=False, smooth=False))
    if tassel:
        prof = [(0.0, 0.0), (0.05, 0.01), (0.09, 0.07), (0.115, 0.15), (0.1, 0.2),
                (0.05, 0.215), (0.0, 0.22)]
        t = K.lathe(name + "_ying", prof, M["tassel_red"], 24)
        t.location = (0, 0, sl - 0.24)
        objs.append(t)
    return objs


# ---------------------------------------------------------------------------------------------
# cloth: flags and banners
# ---------------------------------------------------------------------------------------------
def cloth(name, mat, w, h, wave=0.08, waves=1.3, droop=0.0, nu=40, nv=20, phase=0.0,
          swallow=0.0):
    """A flag sheet in local XZ (attached at x = 0 along the pole, flying towards +x), rippling
    along x; ``droop`` sags the free end; ``swallow`` cuts a swallow-tail notch at the fly."""
    def fn(u, v):
        x = u * w
        y = wave * math.sin(u * math.pi * waves * 2 + phase) * u ** 0.7
        z = h * (v - 1.0) - droop * u ** 1.6
        if swallow:
            # fold the notch: pull the middle of the fly edge back
            notch = swallow * max(0.0, 1.0 - abs(v - 0.5) * 2.0) * u ** 6
            x -= notch * w
        return (x, y, z)
    return K.grid(name, fn, nu, nv, mat, thickness=0.0)


def flag_on_pole(name, M, cloth_mat, w=0.9, h=0.62, pole_h=2.0, wave=0.07, finial="gold",
                 border=None, droop=0.08, swallow=0.0, tassel=True):
    """A pole (+Z) with a flag hanging from the top towards +X (rotate the group to face)."""
    objs = []
    pr = 0.035
    objs.append(K.lathe(name + "_pole", [(0.0, 0.0), (pr, 0.0), (pr * 0.85, pole_h),
                                         (0.0, pole_h)], M["wood_dark"], 16))
    fin = K.lathe(name + "_fin", [(0.0, 0.0), (pr * 1.6, 0.0), (pr * 1.9, 0.05),
                                  (pr * 1.2, 0.09), (pr * 0.9, 0.16), (pr * 1.5, 0.2),
                                  (0.0, 0.32)], M[finial], 20)
    fin.location = (0, 0, pole_h)
    objs.append(fin)
    top = pole_h - 0.02
    c = cloth(name + "_cloth", cloth_mat, w, h, wave, droop=droop, swallow=swallow)
    c.location = (pr, 0, top)
    objs.append(c)
    if border is not None:
        bw = 0.07
        b = cloth(name + "_edge", M[border], bw, h, wave * 0.4, nu=4, nv=20)
        b.location = (pr, -0.002, top)
        objs.append(b)
    if tassel:
        objs += tassel_fn(name + "_ts", M["tassel_red"], (0.0, 0.0, pole_h + 0.02), 0.26, 0.05)
    return objs


# ---------------------------------------------------------------------------------------------
# drum, lantern, helmet, bowl, sack, house, wall
# ---------------------------------------------------------------------------------------------
def drum(name, M, r=0.5, h=0.62, body="lacquer_red", studs=True, seg=64):
    """A barrel war drum (堂鼓) on its side axis Z: lacquered staves bulging in the middle, hide
    heads, two rings of gold studs."""
    objs = []
    prof = []
    for k in range(9):
        t = k / 8.0
        z = -h / 2 + t * h
        rr = r * (1.0 + 0.16 * math.sin(math.pi * t))
        prof.append((rr, z))
    prof = [(0.0, -h / 2)] + prof + [(0.0, h / 2)]
    objs.append(K.lathe(name + "_body", prof, M[body], seg))
    for sgn in (-1, 1):
        hd = K.lathe(name + "_head%d" % sgn, [(0.0, 0.0), (r * 0.985, 0.0), (r * 1.01, 0.012),
                                              (0.0, 0.016)], M["hide"], seg)
        K.place(hd, (0, 0, sgn * h / 2), (0 if sgn > 0 else 180, 0, 0))
        objs.append(hd)
        if studs:
            ns = 18
            for i in range(ns):
                a = TAU * i / ns
                st = K.sphere("%s_st%d_%d" % (name, sgn, i), 0.022, M["gold"], 10, 6)
                st.location = (math.cos(a) * r * 1.01, math.sin(a) * r * 1.01, sgn * (h / 2 - 0.05))
                objs.append(st)
    return objs


def lantern(name, M, r=0.32, h=0.5, paper="silk_red", caps="gold", ribs=8):
    """Oval paper lantern (灯笼) on axis Z: paper body with rib lines (ink AOV), turned caps top and
    bottom, a short hanging cord loop and a tassel."""
    objs = []
    def rib_ink(b):
        co = b.sep(gb.obj_coord(b))
        ang = b.math("ARCTAN2", co[1], co[0])
        return b.math("MULTIPLY", gb.stripes(b, ang, ribs / TAU, 0.06), 0.55)
    pm = gb.pigment("I_Lantern_" + name, **_lantern_colors(paper), ink=rib_ink)
    prof = []
    for k in range(17):
        t = k / 16.0
        z = -h / 2 + t * h
        rr = r * math.sin(math.pi * (0.12 + 0.76 * t)) ** 0.85
        prof.append((rr, z))
    prof = [(0.0, -h / 2)] + prof + [(0.0, h / 2)]
    objs.append(K.lathe(name + "_paper", prof, pm, 48))
    for sgn in (-1, 1):
        cp = K.lathe(name + "_cap%d" % sgn, [(0.0, 0.0), (r * 0.45, 0.0), (r * 0.42, 0.06),
                                             (r * 0.3, 0.075), (0.0, 0.075)], M[caps], 32)
        K.place(cp, (0, 0, sgn * (h / 2 - 0.02)), (0 if sgn > 0 else 180, 0, 0))
        objs.append(cp)
    objs += tassel_fn(name + "_ts", M["tassel_red"], (0, 0, -h / 2 - 0.06), 0.3, 0.06)
    return objs


def _lantern_colors(key):
    return dict(silk_red=dict(light="#D85A3C", deep="#9A2A1E", fen=0.75),
                white=dict(light="#F8F2E4", deep="#C8B890", fen=0.7))[key]


def helmet(name, M, r=0.36, bowl="iron", trim="gold", plume=True):
    """General's helmet (兜鍪), front towards -Y: an ogival bowl with mud-gold ribs and brow band,
    a flame-shaped gold crest plate over the brow, lamellar earflaps and neck guard (open at the
    face), a gold finial carrying a red horsehair plume."""
    objs = []
    prof = [(r, 0.0)]
    for k in range(1, 15):
        t = k / 14.0
        a = (math.pi / 2) * t
        rr = r * math.cos(a) * (1.0 - 0.08 * t)
        z = r * 0.12 + r * 0.98 * math.sin(a) ** 0.9
        prof.append((max(rr, 0.0), z))
    prof[-1] = (0.0, prof[-1][1])
    objs.append(K.lathe(name + "_bowl", prof, M[bowl], 48))
    for k in range(4):
        rib = K.torus(name + "_rib%d" % k, r * 1.0, r * 0.035, M[trim], 48, 6, arc=math.pi)
        K.place(rib, (0, 0, r * 0.12), (90, 0, 45 + 90 * k))
        rib.scale = (1.0, 1.04, 1.0)
        objs.append(rib)
    band = K.lathe(name + "_band", [(r * 1.0, -0.02), (r * 1.07, -0.01), (r * 1.07, r * 0.16),
                                    (r * 1.0, r * 0.19)], M[trim], 48)
    objs.append(band)
    # crest plate (flame / ruyi shape) rising from the brow band at the front
    cr = K.spline_outline([(-0.42, 0.0), (0.42, 0.0), (0.3, 0.35), (0.12, 0.55), (0.0, 0.95),
                           (-0.12, 0.55), (-0.3, 0.35)], 6)
    crest = K.outline_mesh(name + "_crest", [(x * r, z * r) for x, z in cr], r * 0.04, M[trim],
                           plane="XZ")
    K.place(crest, (0, -r * 1.06, r * 0.1), (-12, 0, 0))
    objs.append(crest)
    # earflaps + neck guard: a flared lamellar skirt open at the face
    def lam(b):
        co = b.sep(gb.obj_coord(b))
        return b.math("MULTIPLY", gb.stripes(b, co[2], 1.0 / (r * 0.16), 0.08), 0.5)
    lm = gb.pigment("I_Lamellar_" + name, "#8E928E", "#4A4E50", fen=0.6, ink=lam)

    def guard(u, v):
        a = math.radians(-125 + u * 250) - math.pi / 2 + math.pi
        rr = r * (1.03 + 0.28 * v)
        return (math.cos(a) * rr, math.sin(a) * rr, r * 0.02 - v * r * 0.72)
    g = K.grid(name + "_guard", guard, 40, 4, lm, thickness=0.0)
    objs.append(g)
    fin = K.lathe(name + "_fin", [(0.0, 0.0), (r * 0.14, 0.0), (r * 0.08, r * 0.3),
                                  (r * 0.13, r * 0.38), (r * 0.07, r * 0.6), (0.0, r * 0.62)],
                  M[trim], 20)
    fin.location = (0, 0, r * 1.06)
    objs.append(fin)
    if plume:
        prof = [(0.0, 0.0), (r * 0.12, r * 0.05), (r * 0.26, r * 0.28), (r * 0.3, r * 0.5),
                (r * 0.22, r * 0.75), (0.0, r * 0.86)]
        p = K.lathe(name + "_plume", prof, M["tassel_red"], 24)
        p.location = (0, 0, r * 1.06 + r * 0.55)
        objs.append(p)
    return objs


def bowl(name, mat, r=0.42, h=0.3, foot=0.16, seg=64):
    prof = [(0.0, 0.0), (foot, 0.0), (foot * 1.05, 0.04), (foot * 0.95, 0.05),
            (r * 0.82, h * 0.55), (r, h), (r * 0.94, h), (r * 0.78, h * 0.6), (0.0, h * 0.22)]
    return K.lathe(name, prof, mat, seg)


def house(name, M, w=1.0, d=0.7, h=0.5, roof_h=0.38, eave=0.16, wall="plaster", door=True):
    """A small tiled house (jiehua): plaster walls on a stone footing, red posts at the corners,
    a gabled tile roof with upturned eave corners and a ridge."""
    objs = []
    base = K.box(name + "_base", (w + 0.06, d + 0.06, 0.08), M["stone"])
    base.location = (0, 0, 0.04)
    objs.append(base)
    body = K.box(name + "_wall", (w, d, h), M[wall])
    body.location = (0, 0, 0.08 + h / 2)
    objs.append(body)
    for sx in (-1, 1):
        for sy in (-1, 1):
            p = K.box(name + "_post%d%d" % (sx, sy), (0.06, 0.06, h), M["pillar"])
            p.location = (sx * (w / 2 - 0.0), sy * (d / 2 - 0.0), 0.08 + h / 2)
            objs.append(p)
    if door:
        dr = K.box(name + "_door", (w * 0.26, 0.02, h * 0.66), M["lacquer_red"])
        dr.location = (0, -d / 2 - 0.01, 0.08 + h * 0.33)
        objs.append(dr)
        win = K.box(name + "_win", (w * 0.2, 0.02, h * 0.3), M["wood_dark"])
        for sx in (-1, 1):
            ww = K.box(name + "_win%d" % sx, (w * 0.18, 0.02, h * 0.28), M["wood_dark"])
            ww.location = (sx * w * 0.32, -d / 2 - 0.01, 0.08 + h * 0.58)
            objs.append(ww)
        bpy.data.objects.remove(win, do_unlink=True)
    # roof: two slopes along X with upturned corners
    z0 = 0.08 + h
    L = w + 2 * eave
    D = d / 2 + eave

    def slope(sgn):
        def fn(u, v):
            x = -L / 2 + u * L
            yy = v * D
            curve = 0.12 * (1 - v) ** 2          # concave slope
            up = 0.12 * (abs(2 * u - 1) ** 4) * (1 - v)   # corners lift
            z = z0 + roof_h * v - curve * roof_h * 1.2 + up - 0.06 * (1 - v)
            return (x, sgn * (D - yy), z)
        return fn
    for sgn in (-1, 1):
        rf = K.grid(name + "_roof%d" % sgn, slope(sgn), 24, 8, M["roof"], thickness=0.04)
        objs.append(rf)
    ridge = K.box(name + "_ridge", (L * 0.92, 0.07, 0.07), M["roof_ridge"])
    ridge.location = (0, 0, z0 + roof_h - 0.01)
    objs.append(ridge)
    for sx in (-1, 1):
        orn = K.lathe(name + "_orn%d" % sx, [(0.0, 0.0), (0.045, 0.0), (0.03, 0.1), (0.0, 0.12)],
                      M["roof_ridge"], 12)
        orn.location = (sx * L * 0.46, 0, z0 + roof_h + 0.02)
        objs.append(orn)
    return objs


def wall_segment(name, M, L=2.0, D=0.5, H=1.0, merlons=5, mat="masonry"):
    """City wall: masonry block, coping, crenellations (merlons) along the front edge."""
    objs = []
    wall = K.box(name + "_wall", (L, D, H), M[mat])
    wall.location = (0, 0, H / 2)
    objs.append(wall)
    cop = K.box(name + "_coping", (L + 0.08, D + 0.08, 0.07), M["stone"])
    cop.location = (0, 0, H + 0.035)
    objs.append(cop)
    n = merlons
    w = L / (2 * n - 1)
    for i in range(n):
        x = -L / 2 + w / 2 + i * 2 * w
        m = K.box(name + "_merlon%d" % i, (w, 0.18, 0.26), M[mat])
        m.location = (x, -D / 2 + 0.05, H + 0.07 + 0.13)
        objs.append(m)
    return objs
