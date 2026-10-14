"""Icons family: reusable prop builders (one look for props shared by several icons).

Each builder returns a list of objects (or one object) built around its own origin in the
icon conventions of :mod:`ironart.icons_kit` (+Z up, front -Y, ~1-2 units).  Callers place
the result with :func:`group` (parent empty) so a whole prop can be moved / rotated.
Materials come from the family library (``icons/common.py``: ``M[key]``).
"""

import math
import random

import bpy
from mathutils import Euler, Matrix, Vector

from . import icons_kit as K

TAU = math.tau


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


def _ss(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------------------------------
# gold ingot (yuanbao / sycee)
# ---------------------------------------------------------------------------------------------
def yuanbao(name, mat, L=1.0, W=0.62, rim=0.2, wing=0.2, trough=0.1, dome=(0.26, 0.24, 0.17),
            lip=(0.07, 0.035), flare=0.22, sq=2.6, nu=96, nv=64):
    """A boat-shaped silver/gold ingot: a closed parametric shell (bowl outside, rolled lip,
    trough inside) with high flaring ends, plus a domed boss in the middle of the trough."""
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
    boss = K.sphere(name + "_boss", 1.0, mat, 48, 24, scale=dome)
    boss.location = (0, 0, trough + dome[2] * 0.15)
    return [shell, boss]


# ---------------------------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------------------------
def _rng(seed):
    return random.Random(seed)


def tassel(name, mat, top=(0, 0, 0), length=0.45, radius=0.06, strands=40, seed=1, cap=None,
           spread=1.6, sway=(0.0, 0.0), cap_mat=None):
    """Silk / horsehair tassel hanging from ``top`` (-Z): a wrapped head + ``strands`` thin
    tubes that fan out and fall, with slight random sway."""
    rng = _rng(seed)
    from .geometry import MeshBuilder
    mb = MeshBuilder()
    t = Vector(top)
    for i in range(strands):
        a = rng.uniform(0, TAU)
        rr = radius * math.sqrt(rng.uniform(0.05, 1.0))
        L = length * rng.uniform(0.78, 1.0)
        pts = []
        for k in range(7):
            f = k / 6.0
            r = rr * (0.35 + spread * f ** 1.3)
            pts.append(t + Vector((math.cos(a) * r + sway[0] * f * f,
                                   math.sin(a) * r + sway[1] * f * f, -L * f)))
        mb.tube(pts, radius * 0.07, "S", 4, False, True, lambda f: 1.0 - 0.5 * f)
    o = K.mesh_obj(name, mb, {"S": mat})
    head = K.lathe(name + "_head", [(0.0, 0.0), (radius * 0.75, 0.0), (radius * 0.9, 0.06 * length),
                                    (radius * 0.55, 0.14 * length), (radius * 0.35, 0.2 * length),
                                    (0.0, 0.22 * length)], cap_mat or mat, 24)
    head.location = t + Vector((0, 0, -0.2 * length))
    return [o, head]


def cord(name, mat, points, r=0.012, res=10):
    return K.curve_tube(name, points, r, mat, bevel_res=4, resolution=res)


# ---------------------------------------------------------------------------------------------
# scrolls, brush, seals
# ---------------------------------------------------------------------------------------------
def scroll_rolled(name, M, length=1.5, r=0.15, outer="silk_blue", knob="jade", rod="wood_dark",
                  tie="rope_red", label=True, tie_ends=True):
    """A rolled hanging scroll lying along local X: a silk-mounted roll with a pale title slip,
    a cord tied round the middle with hanging ends, and turned rod knobs at both ends."""
    objs = []
    body = K.lathe(name + "_roll", [(0.0, -length / 2), (r * 0.97, -length / 2),
                                   (r, -length / 2 + 0.01), (r, length / 2 - 0.01),
                                   (r * 0.97, length / 2), (0.0, length / 2)], M[outer], 64)
    body.data.use_auto_smooth = True
    body.data.auto_smooth_angle = math.radians(50)
    K.place(body, (0, 0, 0), (0, 90, 0))
    objs.append(body)
    # visible end of the outer wrap: a thin step running along the roll
    lip = K.lathe(name + "_lip", [(r * 1.0, -length / 2 + 0.004), (r * 1.025, -length / 2 + 0.004),
                                  (r * 1.025, length / 2 - 0.004), (r * 1.0, length / 2 - 0.004)],
                  M[outer], 64)
    K.place(lip, (0, 0, 0), (0, 90, 0))
    lip.data.use_auto_smooth = True
    objs.append(lip)
    # paper end faces (the rolled sheet shows at both ends inside the knobs)
    for sgn in (-1, 1):
        endp = K.lathe(name + "_end%d" % sgn, [(0.0, 0.0), (r * 0.98, 0.0), (r * 0.98, 0.006),
                                               (0.0, 0.006)], M["paper"], 48)
        K.place(endp, (sgn * (length / 2 + 0.0), 0, 0), (0, 90 * sgn, 0))
        objs.append(endp)
        kn = K.lathe(name + "_knob%d" % sgn, [(0.0, 0.0), (r * 0.42, 0.0), (r * 0.48, 0.03),
                                              (r * 0.62, 0.06), (r * 0.66, 0.1), (r * 0.6, 0.14),
                                              (r * 0.4, 0.165), (0.0, 0.17)], M[knob], 32)
        K.place(kn, (sgn * (length / 2 + 0.004), 0, 0), (0, 90 * sgn, 0))
        objs.append(kn)
    if label:
        slip = K.grid(name + "_slip", lambda u, v: (
            -length * 0.32 + u * length * 0.42,
            -math.cos((v - 0.5) * 0.9) * r * 1.03,
            math.sin((v - 0.5) * 0.9) * r * 1.03 + 0.0), 12, 6, M["paper"], thickness=0.004)
        K.place(slip, (0, 0, 0), (-25, 0, 0))
        objs.append(slip)
    if tie:
        ring = K.torus(name + "_tie", r * 1.03, 0.012, M[tie], 64, 10)
        K.place(ring, (length * 0.16, 0, 0), (0, 90, 0))
        ring2 = K.torus(name + "_tie2", r * 1.03, 0.012, M[tie], 64, 10)
        K.place(ring2, (length * 0.16 + 0.03, 0, 0), (0, 90, 0))
        objs += [ring, ring2]
        if tie_ends:
            x = length * 0.16 + 0.015
            objs.append(cord(name + "_end_a", M[tie], [(x, -r * 0.9, -r * 0.4),
                                                       (x - 0.04, -r * 1.25, -r * 1.0),
                                                       (x - 0.02, -r * 1.3, -r * 1.7),
                                                       (x + 0.05, -r * 1.2, -r * 2.2)], 0.011))
            objs.append(cord(name + "_end_b", M[tie], [(x, -r * 0.9, -r * 0.4),
                                                       (x + 0.06, -r * 1.3, -r * 0.9),
                                                       (x + 0.12, -r * 1.35, -r * 1.5),
                                                       (x + 0.13, -r * 1.25, -r * 2.0)], 0.011))
    return objs


def handscroll_open(name, M, w=1.5, h=0.85, image=None, curl=0.08, roller="wood_dark",
                    knob="jade", border="silk_gold", r=0.07):
    """A horizontally unrolled scroll: paper field (with an optional calligraphy ``image``)
    framed by narrow silk borders, a roller at each end with knobs; lies in local XZ facing -Y
    with a gentle wave so the light rolls over it."""
    objs = []
    from . import icons_mats as im
    pm = im.paper("I_Paper_%s" % name, image=image) if image is not None else M["paper"]

    def sheet(u, v):
        x = -w / 2 + u * w
        y = curl * math.sin(u * math.pi * 1.6 + 0.4) * 0.6
        z = -h / 2 + v * h
        return (x, y, z)

    s = K.grid(name + "_sheet", sheet, 48, 8, pm, thickness=0.006)
    objs.append(s)
    for vv, hh in ((0.0, 0.07), (1.0 - 0.07, 0.07)):
        b = K.grid(name + "_band%.0f" % (vv * 10), lambda u, v, vv=vv, hh=hh: (
            -w / 2 + u * w, curl * math.sin(u * math.pi * 1.6 + 0.4) * 0.6 - 0.004,
            -h / 2 + (vv + v * hh) * h), 48, 2, M[border], thickness=0.004)
        objs.append(b)
    for sgn in (-1, 1):
        u = 0.0 if sgn < 0 else 1.0
        y0 = curl * math.sin(u * math.pi * 1.6 + 0.4) * 0.6
        rod = K.lathe(name + "_rod%d" % sgn, [(0.0, -h / 2 - 0.02), (r, -h / 2 - 0.02),
                                              (r, h / 2 + 0.02), (0.0, h / 2 + 0.02)],
                      M[roller], 32)
        rod.data.use_auto_smooth = True
        rod.location = (sgn * (w / 2 + r * 0.6), y0, 0)
        objs.append(rod)
        for zs in (-1, 1):
            kn = K.lathe(name + "_kn%d%d" % (sgn, zs), [(0.0, 0.0), (r * 0.7, 0.0),
                                                         (r * 0.95, 0.03), (r * 0.9, 0.08),
                                                         (r * 0.6, 0.1), (0.0, 0.105)],
                         M[knob], 24)
            K.place(kn, (sgn * (w / 2 + r * 0.6), y0, zs * (h / 2 + 0.02)),
                    (0 if zs > 0 else 180, 0, 0))
            objs.append(kn)
    return objs


def brush(name, M, length=1.2, r=0.032, handle="bamboo", tip_len=0.26, loop=True):
    """Writing brush along local +Z (tip at z = 0): bamboo handle, horn ferrule, a full hair
    head that is pale at the root and ink-black at the point, a hanging loop at the end."""
    from . import icons_mats as im
    objs = []
    hair = im.straw("I_BrushHair", color="#D8CDB4", tip="#1A1612", base_col="#EDE6D6",
                    zlo=tip_len, zhi=0.0, rough=0.5)
    head = K.lathe(name + "_hair", [(0.0, 0.0), (r * 0.25, 0.02), (r * 0.9, tip_len * 0.35),
                                    (r * 1.25, tip_len * 0.62), (r * 1.15, tip_len * 0.88),
                                    (r * 1.0, tip_len)], hair, 32)
    objs.append(head)
    fer = K.lathe(name + "_ferrule", [(r * 1.0, tip_len - 0.005), (r * 1.18, tip_len),
                                      (r * 1.18, tip_len + 0.06), (r * 1.05, tip_len + 0.07)],
                  M["lacquer_black"], 32)
    objs.append(fer)
    h = K.lathe(name + "_handle", [(r * 1.05, tip_len + 0.07), (r, tip_len + 0.08),
                                   (r * 0.92, length - 0.06), (r * 1.08, length - 0.05),
                                   (r * 1.08, length), (0.0, length + 0.003)], M[handle], 32)
    objs.append(h)
    if loop:
        lp = K.torus(name + "_loop", 0.05, 0.007, M["rope_red"], 32, 8)
        K.place(lp, (0, 0, length + 0.045), (90, 0, 0))
        objs.append(lp)
    return objs


def seal_block(name, M, size=0.5, height=0.42, mat="jade", knob_mat=None, tassel_mat="silk_red",
               glyph=None, font=None, face_mat="vermilion"):
    """A square seal of office: bevelled block, an arched beast-knob handle with a tassel cord
    threaded through, the carved face (``glyph``) on the underside left clean (not visible)."""
    objs = []
    base = K.box(name + "_base", (size, size, height * 0.55), M[mat], bevel_w=size * 0.05,
                 segments=4)
    base.location = (0, 0, height * 0.275)
    objs.append(base)
    # stepped top
    top = K.box(name + "_top", (size * 0.86, size * 0.86, height * 0.1), M[mat],
                bevel_w=size * 0.04, segments=3)
    top.location = (0, 0, height * 0.55 + height * 0.05)
    objs.append(top)
    # crouching beast knob (stylised: body, head, mane, paws) via metaballs
    km = M[knob_mat or mat]
    s = size
    z0 = height * 0.62
    els = [
        dict(type="ELLIPSOID", co=(0.02 * s, 0.05 * s, z0 + 0.12 * s), radius=0.3 * s,
             size=(0.85, 0.5, 0.42)),
        dict(type="BALL", co=(-0.2 * s, -0.08 * s, z0 + 0.2 * s), radius=0.2 * s),
        dict(type="BALL", co=(-0.27 * s, -0.17 * s, z0 + 0.18 * s), radius=0.1 * s),
        dict(type="ELLIPSOID", co=(-0.12 * s, -0.12 * s, z0 + 0.05 * s), radius=0.12 * s,
             size=(0.8, 1.3, 0.6)),
        dict(type="ELLIPSOID", co=(0.2 * s, -0.12 * s, z0 + 0.05 * s), radius=0.12 * s,
             size=(0.9, 1.3, 0.6)),
        dict(type="ELLIPSOID", co=(0.28 * s, 0.14 * s, z0 + 0.18 * s), radius=0.1 * s,
             size=(1.6, 0.6, 0.6), rot=(0, -30, 0)),
        dict(type="ELLIPSOID", co=(0.02 * s, 0.05 * s, z0 + 0.0 * s), radius=0.32 * s,
             size=(1.0, 0.7, 0.25)),
    ]
    beast = K.metaball(name + "_knob", els, km, resolution=0.012 * s / 0.5, threshold=0.6)
    objs.append(beast)
    if tassel_mat:
        ring = K.torus(name + "_cord", 0.07 * s, 0.018 * s, M[tassel_mat], 32, 8)
        K.place(ring, (0.06 * s, 0.05 * s, z0 + 0.02 * s), (0, 90, 0))
        objs.append(ring)
    return objs


def stamp_image(name, glyph, font, size=256, color=(176, 36, 24), border=0.08, invert=False,
                rotate=2.0):
    """Red seal impression texture: square frame + glyph (alpha = ink; colour = vermilion)."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    b = int(size * border)
    ink = color + (255,)
    if invert:
        d.rectangle([b, b, size - b, size - b], fill=ink)
        f = ImageFont.truetype(font, int(size * 0.7))
        d.text((size / 2, size / 2), glyph, font=f, fill=(0, 0, 0, 0), anchor="mm")
    else:
        w = max(3, int(size * 0.05))
        d.rectangle([b, b, size - b, size - b], outline=ink, width=w)
        f = ImageFont.truetype(font, int(size * 0.68))
        d.text((size / 2, size / 2 + size * 0.02), glyph, font=f, fill=ink, anchor="mm")
    # worn stamp: knock out speckles
    import numpy as np
    rng = np.random.default_rng(len(name))
    a = np.asarray(im, dtype=np.float32)
    noise = rng.random((size, size))
    a[..., 3] *= (noise > 0.06)
    im = Image.fromarray(a.astype(np.uint8), "RGBA").filter(ImageFilter.GaussianBlur(0.6))
    if rotate:
        im = im.rotate(rotate, resample=Image.BICUBIC)
    return K.pil_image(name, im)
