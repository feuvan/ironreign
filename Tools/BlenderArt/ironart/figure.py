"""Procedural portrait kit: sculpted head, eyes, brows, beards, helmets, armour, robes.

Coordinate frame (all builders): metres, head centre (between the ears, mid-height of the skull)
at the origin, the face looks towards **-Y**, +Z up.  ``head()`` returns *landmarks* (eye centres,
nose tip, mouth, chin, brow line, ears, crown, neck) that every other builder uses, so a helmet or
beard follows any head shape.

The head is sculpted numerically: a UV sphere is shaped into an egg skull, the lower face is
tapered to a jaw/chin profile, then facial features are added as anisotropic gaussian
displacements (brow ridge, sockets, nose bridge/tip/wings, cheekbones, lips, chin).  It is not a
likeness engine - it is a sturdy, controllable base that reads as a Koei painted bust after the
painterly pass.  :class:`HeadParams` exposes the knobs archetypes need (jaw, nose, brow, age...).

Material slot names used (provide them to ``MeshBuilder.build``):
    Skin, Eye, Brow, Hair, Beard, Iron, IronDark, Lamellar, Bronze, Gold, Leather, Silk,
    SilkInner, Plume, Cloth
"""

import math
import random
from dataclasses import dataclass

import numpy as np
from mathutils import Matrix, Vector

from . import geometry as geo

TAU = math.tau


@dataclass
class HeadParams:
    width: float = 0.150        # ear-to-ear skull width
    depth: float = 0.190        # forehead-to-back
    height: float = 0.232       # chin-to-crown
    jaw: float = 0.92           # jaw width factor (1 = as wide as the skull)
    chin: float = 1.0           # chin prominence
    brow: float = 1.0           # brow ridge strength
    cheekbone: float = 1.0
    nose_len: float = 1.0
    nose_width: float = 1.0
    nose_bridge: float = 1.0    # bridge height (aquiline > 1)
    eye_spacing: float = 1.0
    eye_size: float = 1.0
    socket: float = 1.0         # eye-socket depth
    lips: float = 1.0
    age: float = 0.3            # 0 young .. 1 old (sagging cheeks, deeper sockets)
    lid_upper: float = 0.25     # upper lid edge elevation (rad) above the eye axis at the centre
    lid_lower: float = 0.22     # lower lid edge elevation (rad) below the eye axis
    eye_tilt: float = 0.07      # outer-corner lift (rad per rad of azimuth)
    eye_width: float = 1.22     # half-width of the opening (rad of azimuth around the eyeball)
    eye_depth: float = 0.0025   # cornea front behind the un-carved face surface (m)
    seed: int = 0


def _g2(dx, dz, sx, sz):
    return np.exp(-0.5 * ((dx / sx) ** 2 + (dz / sz) ** 2))


def _exit_dist(d, c, R, rot_x=0.0):
    """Distance along unit rays ``d`` (N x 3, from the origin) to where they *exit* the ellipsoid
    (centre ``c``, radii ``R``, optionally rotated about X).  -inf where the ray misses."""
    c = np.asarray(c, np.float64)
    if rot_x:
        ca, sa = math.cos(rot_x), math.sin(rot_x)
        Rm = np.array([[1, 0, 0], [0, ca, sa], [0, -sa, ca]])     # world -> local (inverse rot)
        dl = d @ Rm.T
        cl = Rm @ c
    else:
        dl, cl = d, c
    D = dl / R
    C = cl / R
    a = (D * D).sum(1)
    b = (D * C).sum(1)
    cc = (C * C).sum() - 1.0
    disc = b * b - a * cc
    t = (b + np.sqrt(np.maximum(disc, 0))) / a
    return np.where(disc > 0, t, -np.inf)


def _smax(vals, k):
    """Smooth maximum (log-sum-exp) of a list of arrays; ``k`` = blend radius in metres."""
    v = np.stack(vals, 0)
    m = np.max(v, 0)
    m = np.where(np.isfinite(m), m, 0.0)
    return m + k * np.log(np.sum(np.exp(np.clip((v - m) / k, -60, 0)), 0))


def head_masses(p):
    """Anatomical masses (centre, radii, rot_x) for :class:`HeadParams` ``p`` (subject's left = +x)."""
    j, ch, cb, br = p.jaw, p.chin, p.cheekbone, p.brow
    nl, nw, nb = p.nose_len, p.nose_width, p.nose_bridge
    W = p.width / 0.150
    D = p.depth / 0.190
    Hh = p.height / 0.232
    m = [
        ((0, 0.012 * D, 0.022 * Hh), (0.074 * W, 0.097 * D, 0.100 * Hh), 0),        # cranium
        ((0, -0.026 * D, 0.026 * Hh), (0.066 * W, 0.068 * D, 0.062 * Hh), 0),       # forehead
        ((0, -0.020 * D, -0.030 * Hh), (0.058 * W, 0.074 * D, 0.060 * Hh), 0),      # mid face
        ((0, -0.030 * D, -0.062 * Hh), (0.054 * W * j, 0.062 * D, 0.052 * Hh), 0),  # mandible
        ((0.040 * W * j, 0.0, -0.066 * Hh), (0.022 * j, 0.036, 0.030), 0),          # jaw angle L
        ((-0.040 * W * j, 0.0, -0.066 * Hh), (0.022 * j, 0.036, 0.030), 0),         # jaw angle R
        ((0, -0.068 * D, -0.094 * Hh), (0.021 * ch, 0.020 * ch, 0.017), 0),         # chin
        ((0.042 * W, -0.048 * D, -0.004), (0.020 * cb, 0.024, 0.015), 0),           # cheekbone L
        ((-0.042 * W, -0.048 * D, -0.004), (0.020 * cb, 0.024, 0.015), 0),          # cheekbone R
        ((0, -0.072 * D, 0.025), (0.054 * W, 0.020 * br, 0.012), 0),                # brow ridge
        ((0, -0.066 * D, -0.064), (0.026, 0.020, 0.018 * p.lips), 0),               # muzzle
        ((0, -0.082 * D, -0.058), (0.0185, 0.0085, 0.0062 * p.lips), 0),            # upper lip
        ((0, -0.079 * D, -0.0705), (0.0165, 0.0085, 0.0058 * p.lips), 0),           # lower lip
        ((0, -0.077 * D - 0.004 * nb, -0.017 * nl), (0.0078 * nw, 0.0095 * nb, 0.026 * nl),
         math.radians(-28)),                                                         # nose bridge
        ((0, -0.097 * D - 0.003 * nl, -0.035 * nl), (0.0088 * nw, 0.0088, 0.0085), 0),  # nose tip
        ((0.012 * nw, -0.082 * D, -0.039 * nl), (0.0066 * nw, 0.0076, 0.0058), 0),   # ala L
        ((-0.012 * nw, -0.082 * D, -0.039 * nl), (0.0066 * nw, 0.0076, 0.0058), 0),  # ala R
    ]
    return m


def head(params=None, segments=320, rings=224, mat="Skin", blend=0.008):
    """Sculpt the head as a smooth union of anatomical masses evaluated along radial rays from
    the skull centre (the head is star-shaped from there), then carve eye sockets and add
    detail offsets.  Returns ``(MeshBuilder, landmarks)``."""
    p = params or HeadParams()
    mb = geo.MeshBuilder()
    s0 = mb.n
    mb.sphere((0, 0, 0), 1.0, mat, segments, rings, smooth=True)
    V = np.array([tuple(v) for v in mb.verts[s0:]], np.float64)
    d = V / np.maximum(np.linalg.norm(V, axis=1, keepdims=True), 1e-9)
    masses = head_masses(p)
    dists = [_exit_dist(d, c, np.array(R), rx) for (c, R, rx) in masses]
    r = _smax(dists, blend)
    P = d * r[:, None]
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    fw = np.clip((-d[:, 1] - 0.35) / 0.4, 0, 1)                 # front weight
    es = 0.031 * p.eye_spacing
    ez = 0.004
    off = np.zeros_like(r)
    # --- eyes: eyeball centres from the un-carved face; lids = skin conforming to a sphere
    #     slightly larger than the eyeball, with an almond opening pushed in behind the eyeball
    r_eye = 0.0118 * p.eye_size
    front_dir = d[:, 1] < -0.2
    eye_specs = []
    for sgn in (1, -1):
        k = np.argmin(np.where(front_dir, (x - sgn * es) ** 2 + (z - ez) ** 2, np.inf))
        c = np.array([sgn * es, y[k] + p.eye_depth + r_eye, ez])
        eye_specs.append((Vector(c), r_eye, sgn))
    for (c, re_, sgn) in eye_specs:
        c = np.array(c)
        rl = re_ * 1.05
        t_lid = _exit_dist(d, c, np.array([rl, rl, rl]))
        hit = np.isfinite(t_lid)
        tl = np.where(hit, t_lid, 0.0)
        q = (d * tl[:, None] - c) / rl
        yaw = sgn * 0.10                                      # eyes look slightly outward
        qx = q[:, 0] * math.cos(yaw) - q[:, 1] * math.sin(yaw)
        qy = q[:, 0] * math.sin(yaw) + q[:, 1] * math.cos(yaw)
        az = np.arctan2(qx, -qy)
        el = np.arcsin(np.clip(q[:, 2], -1, 1))
        ang = np.sqrt((az / (p.eye_width + 0.25)) ** 2 + (el / 1.05) ** 2)
        w = np.where(hit & (qy < 0.35), 1.0 - np.clip((ang - 0.72) / 0.32, 0, 1), 0.0)
        w = w * w * (3 - 2 * w)
        r = r * (1 - w) + tl * w
        kk = np.cos(np.clip(az / p.eye_width, -1, 1) * math.pi / 2) ** 0.75
        tilt = p.eye_tilt * az * sgn
        e_top = p.lid_upper * kk + tilt - 0.02
        e_bot = -p.lid_lower * kk + tilt + 0.02
        m = 0.07
        o = (np.clip((e_top - el) / m + 0.5, 0, 1) * np.clip((el - e_bot) / m + 0.5, 0, 1)
             * np.clip((p.eye_width - np.abs(az)) / m + 0.5, 0, 1)) * (w > 0.5)
        r = r - o * rl * 1.3
    P = d * r[:, None]
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    for sgn in (1, -1):
        # brow-to-lid concavity and the cheek pad under the lower lid
        off -= 0.004 * p.socket * (1 + 0.25 * p.age) * _g2(x - sgn * (es + 0.002), z - ez - 0.016, 0.014, 0.006) * fw
        off += 0.0012 * _g2(x - sgn * (es + 0.004), z - ez + 0.02, 0.012, 0.004) * fw
    off -= 0.0035 * _g2(x, z - 0.008, 0.006, 0.006) * fw          # nasion dip
    off -= 0.0018 * _g2(x, z + 0.064, 0.02, 0.0014) * fw          # mouth line
    for sgn in (1, -1):
        off -= 0.0020 * _g2(x - sgn * 0.021, z + 0.064, 0.004, 0.005) * fw    # mouth corners
        off += (0.0012 + 0.0025 * p.age) * _g2(x - sgn * 0.025, z + 0.048, 0.0035, 0.012) * fw  # naso-labial
        off -= (0.002 + 0.003 * p.age) * _g2(x - sgn * 0.045, z + 0.045, 0.013, 0.013)  # cheek hollow
        off -= 0.003 * _g2(np.abs(x) - 0.064, z - 0.03, 0.01, 0.018) * (np.sign(x) == sgn)  # temples
    off -= 0.0025 * _g2(x, z + 0.083, 0.014, 0.004) * fw          # mentolabial sulcus
    rng = np.random.default_rng(p.seed)
    ph = rng.uniform(0, TAU, 2)
    off += 0.0005 * np.sin(x * 120 + ph[0]) * np.sin(z * 90 + ph[1]) * fw
    r2 = r + off
    newV = d * r2[:, None]
    for i, co in enumerate(newV):
        mb.verts[s0 + i] = Vector(co)
    x, y, z = newV[:, 0], newV[:, 1], newV[:, 2]
    tip_z = -0.034 * p.nose_len
    bl = np.clip(_g2(np.abs(x) - 0.042, z + 0.022, 0.016, 0.014) * 0.8
                 + _g2(x, z - tip_z, 0.01, 0.01) * 0.6, 0, 1)
    for i, val in enumerate(bl):
        mb.vattr.setdefault("blush", {})[s0 + i] = float(val)

    front = newV[:, 1] < 0

    def surf_y(px, pz):
        """Front skin y at (x, z) (nearest front vertex)."""
        F = newV[front]
        k = np.argmin((F[:, 0] - px) ** 2 + (F[:, 2] - pz) ** 2)
        return float(F[k, 1])

    def surf_x(py, pz, sign):
        m = np.sign(newV[:, 0]) == sign
        S = newV[m]
        k = np.argmin((S[:, 1] - py) ** 2 + (S[:, 2] - pz) ** 2)
        return float(S[k, 0])

    rz_top = float(newV[:, 2].max())
    rz_bot = float(-newV[:, 2].min())
    mz = -0.064
    lm = {
        "params": p,
        "eye_l": eye_specs[0][0],                                      # subject's left = +x
        "eye_r": eye_specs[1][0],
        "eye_specs": eye_specs,
        "nose_tip": Vector((0, surf_y(0, tip_z), tip_z)),
        "mouth": Vector((0, surf_y(0, mz), mz)),
        "chin": Vector((0, surf_y(0, -0.095), -0.095)),
        "brow_z": 0.024,
        "forehead": Vector((0, surf_y(0, 0.06), 0.06)),
        "crown": Vector((0, 0.012, rz_top)),
        "ear_l": Vector((surf_x(0.008, -0.002, 1), 0.008, -0.002)),
        "ear_r": Vector((surf_x(0.008, -0.002, -1), 0.008, -0.002)),
        "neck": Vector((0, 0.02, -0.075)),
        "rx": float(np.abs(newV[:, 0]).max()), "ry": float(np.abs(newV[:, 1]).max()),
        "rz_top": rz_top, "rz_bot": rz_bot,
        "verts": newV,
        "surf_y": surf_y,
    }
    return mb, lm


def ears(mb, lm, mat="Skin", size=1.0):
    """Simple ears: flattened, slightly cupped ellipsoids at the sides."""
    for key, sgn in (("ear_l", 1), ("ear_r", -1)):
        c = lm[key]
        s = mb.n
        mb.sphere((0, 0, 0), 1.0, mat, 14, 10, smooth=True, scale=(0.006 * size, 0.017 * size, 0.029 * size))
        m = (Matrix.Translation(c + Vector((sgn * 0.002, 0.012, -0.006)))
             @ Matrix.Rotation(sgn * 0.25, 4, "Z") @ Matrix.Rotation(-0.12, 4, "X"))
        mb.transform(s, m)


def eyes(mb, lm, lash_mat="Brow", lash=1.0):
    """Lash line: a thin dark tapered tube along the upper-lid edge (the crisp painted eye line).
    The lids themselves are part of the head surface (see :func:`head`).  Returns the eye specs
    ``[(centre, radius, side_sign), ...]`` for :func:`eyeballs`."""
    p = lm["params"]
    for (c, r, sgn) in lm["eye_specs"]:
        rl = r * 1.07
        pts = []
        for u in np.linspace(-0.92, 0.95, 16):
            az = u * p.eye_width
            kk = math.cos(min(1.0, abs(az) / p.eye_width) * math.pi / 2) ** 0.75
            e = p.lid_upper * kk + p.eye_tilt * az * sgn - 0.02
            yaw = sgn * 0.10
            dx, dy = math.sin(az) * math.cos(e), -math.cos(az) * math.cos(e)
            v = Vector((dx * math.cos(yaw) + dy * math.sin(yaw), -dx * math.sin(yaw) + dy * math.cos(yaw),
                        math.sin(e)))
            pts.append(tuple(c + v * rl))
        if lash > 0:
            mb.tube(pts, r * 0.075 * lash, lash_mat, 5,
                    radius_fn=lambda t: 0.35 + 0.9 * math.sin(math.pi * min(1.0, 0.15 + t * 0.95)))
    return lm["eye_specs"]


def eyeballs(eye_specs, material, look=(0.0, 0.0), name="Eye"):
    """Create one object per eyeball (unit sphere scaled to the radius, origin at the centre) so
    :func:`ironart.materials.eye`'s object-space iris works.  ``look`` = (yaw, pitch) radians,
    positive yaw turns the gaze towards the subject's left (+x)."""
    import bpy
    objs = []
    for (c, r, sgn) in eye_specs:
        emb = geo.MeshBuilder()
        emb.sphere((0, 0, 0), 1.0, "Eye", 32, 20, smooth=True)
        o = emb.build("%s_%s" % (name, "L" if sgn > 0 else "R"), {"Eye": material},
                      auto_smooth_deg=None)
        o.location = c
        o.scale = (r, r, r)
        o.rotation_euler = (look[1], 0.0, look[0] + sgn * 0.05)
        objs.append(o)
    bpy.context.view_layer.update()
    return objs


def brows(mb, lm, mat="Brow", thickness=1.0, arch=1.0, angle=0.18):
    """Bushy brows as tapered flattened tubes along the brow ridge (warrior: thick, angled)."""
    p = lm["params"]
    es = 0.031 * p.eye_spacing
    for sgn in (1, -1):
        pts = []
        for t in np.linspace(0, 1, 10):
            xx = sgn * (es - 0.017 + 0.036 * t)
            zz = lm["brow_z"] + 0.004 + 0.006 * arch * math.sin(math.pi * min(1, t * 1.2)) + angle * 0.02 * (1 - t)
            yy = lm["surf_y"](xx, zz) - 0.0015
            pts.append((xx, yy, zz))
        s = mb.n
        mb.tube(pts, 0.0032 * thickness, mat, 6, radius_fn=lambda t: 0.75 + 0.6 * math.sin(math.pi * (0.25 + 0.7 * t)) - 0.5 * t)
        # flatten against the skin
        for i in range(s, mb.n):
            v = mb.verts[i]
            mb.verts[i] = Vector((v.x, v.y + 0.0, v.z))


def beard(mb, lm, length=0.16, width=1.0, fullness=1.0, mat="Beard", style="full",
          strands=90, rng=None, fork=0.0):
    """Full beard: a shell hugging cheeks/jaw/chin that flows down into a spade/point, plus
    tapered strand clumps on top for a painterly, clumpy silhouette.

    style  'full' (cheeks + chin, Zhang Fei / general), 'chin' (goatee + jaw line),
           'long' (thin long chin beard, scholar/elder)
    """
    rng = rng or random.Random(7)
    V = lm["verts"]
    rx, rzb = lm["rx"], lm["rz_bot"]
    chin = lm["chin"]
    mouth = lm["mouth"]
    top_z = {"full": lm["nose_tip"].z - 0.004, "chin": mouth.z - 0.004, "long": mouth.z - 0.01}[style]
    side_az = {"full": 1.75, "chin": 1.0, "long": 0.55}[style] * width
    tip = Vector((0, chin.y - 0.035 * fullness, chin.z - length))

    def skin_point(az, zz):
        """Point on the head surface at azimuth ``az`` (0 = front, + = subject left) and height zz."""
        dirs = np.stack([np.sin(az) * np.ones(1), -np.cos(az) * np.ones(1)], 1)[0]
        m = np.abs(V[:, 2] - zz) < 0.006
        P = V[m]
        if len(P) == 0:
            return Vector((0, 0, zz))
        proj = P[:, 0] * dirs[0] + P[:, 1] * dirs[1]
        perp = np.abs(P[:, 0] * dirs[1] - P[:, 1] * dirs[0])
        k = np.argmax(proj - 4 * perp)
        return Vector(P[k])

    thick = 0.007 * fullness

    def fn(u, v):
        az = (-1 + 2 * u) * side_az
        # v: 0 = top edge (cheek), 1 = beard tip
        jaw_v = 0.55
        if v <= jaw_v:
            zz = top_z + (min(lm["chin"].z - 0.02, -rzb * 0.55) - top_z) * (v / jaw_v)
            # side parts end at the jaw line higher up (follow the jaw)
            zz = zz + (abs(az) / max(side_az, 1e-6)) ** 2 * 0.03 * (v / jaw_v)
            sp = skin_point(az, zz)
            n = Vector((sp.x, sp.y, 0)).normalized() if sp.length > 0 else Vector((0, -1, 0))
            off = thick * (0.35 + 0.65 * (v / jaw_v)) * (1 - 0.5 * (abs(az) / side_az) ** 3)
            return tuple(sp + n * off)
        t = (v - jaw_v) / (1 - jaw_v)
        zz0 = min(lm["chin"].z - 0.02, -rzb * 0.55) + (abs(az) / max(side_az, 1e-6)) ** 2 * 0.03
        sp = skin_point(az, zz0)
        n = Vector((sp.x, sp.y, 0)).normalized()
        start = sp + n * thick
        # converge towards the tip; keep volume (bulge forward) in the middle
        q = start.lerp(tip + Vector((math.sin(az) * 0.012 * fork, 0, 0)), t ** 1.2)
        q += Vector((0, -0.018 * fullness * math.sin(math.pi * t) * math.cos(az * 0.6), 0))
        return tuple(q)

    mb.grid(fn, 22, 18, mat, smooth=True)
    # strand clumps
    for i in range(strands):
        u = rng.random()
        v0 = rng.uniform(0.0, 0.7)
        pts = []
        steps = 7
        lenv = rng.uniform(0.35, 1.0)
        for k in range(steps):
            vv = min(1.0, v0 + lenv * k / (steps - 1) * (1 - v0))
            q = Vector(fn(u + rng.uniform(-0.01, 0.01), vv))
            n = Vector((q.x, q.y, 0)).normalized()
            pts.append(tuple(q + n * 0.0025 + Vector((0, -0.002, 0)) +
                             Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), 0)) * 0.0015))
        mb.tube(pts, rng.uniform(0.0022, 0.0042), mat, 5, radius_fn=lambda t: 1.0 - 0.85 * t)


def mustache(mb, lm, length=1.0, droop=1.0, mat="Beard", thickness=1.0):
    """Two tapered tubes from under the nose drooping past the mouth corners."""
    tip = lm["nose_tip"]
    mouth = lm["mouth"]
    for sgn in (1, -1):
        pts = []
        for t in np.linspace(0, 1, 10):
            xx = sgn * (0.003 + 0.030 * length * t)
            zz = (tip.z - 0.013) - 0.004 * t - 0.03 * droop * max(0.0, t - 0.45) ** 1.5 * length
            yy = lm["surf_y"](xx, zz) - 0.004 - 0.002 * math.sin(math.pi * t)
            pts.append((xx, yy, zz))
        mb.tube(pts, 0.0048 * thickness, mat, 7, radius_fn=lambda t: 0.75 + 0.45 * math.sin(math.pi * (0.15 + 0.6 * t)) - 0.7 * t ** 2)


def neck(mb, lm, mat="Skin", radius=0.052, length=0.12):
    n = lm["neck"]
    mb.cylinder(n + Vector((0, 0.0, 0.03)), n + Vector((0, 0.01, -length)), radius, radius * 1.15, mat,
                segments=24, caps=False)


# ---------------------------------------------------------------------------------------------
# helmets & headwear
# ---------------------------------------------------------------------------------------------
def helmet(mb, lm, style="dome", plume=True, mat="Iron", trim="Gold", plume_mat="Plume",
           neck_guard="Lamellar", ribs=12, brim_z=None, scale=1.0, rng=None):
    """Chinese general's helmet (兜鍪): ribbed dome, gold brim band with a brow peak, spike finial
    with a red tassel plume, and lamellar neck/cheek guards that cover the ears.
    """
    rng = rng or random.Random(3)
    rx, ry, rzt = lm["rx"] * scale, lm["ry"] * scale, lm["rz_top"] * scale
    bz = lm["brow_z"] + 0.03 if brim_z is None else brim_z
    cx, cy = 0.0, 0.004
    sx, sy = rx * 1.04 + 0.006, ry * 1.0 + 0.006
    # dome profile (r, z) normalised: slightly pointed top
    prof = []
    for k in range(13):
        t = k / 12.0
        a = t * math.pi / 2
        r = math.cos(a) ** 0.9
        z = bz + (rzt + 0.012 - bz) * (math.sin(a) ** 0.85) + 0.008 * t ** 6
        prof.append((r, z))
    s = mb.n
    rings = mb.lathe(prof, mat, 48, center=(cx, cy, 0), smooth=True, scale_xy=(sx, sy))
    # ribs: raised gold/iron strips along meridians
    for i in range(ribs):
        a = TAU * i / ribs
        pts = []
        for (r, z) in prof[:-1]:
            pts.append((cx + math.cos(a) * r * sx * 1.012, cy + math.sin(a) * r * sy * 1.012, z))
        mb.tube(pts, 0.0026, trim if i % 3 == 0 else mat, 5)
    # brim band
    band = [(1.0, bz - 0.008), (1.025, bz - 0.006), (1.028, bz + 0.006), (1.0, bz + 0.009)]
    mb.lathe(band, trim, 48, center=(cx, cy, 0), smooth=True, scale_xy=(sx, sy))
    # brow peak (visor) at the front
    def peak(u, v):
        a = -math.pi / 2 + (-1 + 2 * u) * 0.9
        rr = 1.0 + 0.11 * v * math.cos((-1 + 2 * u) * 1.4)
        return (cx + math.cos(a) * sx * rr, cy + math.sin(a) * sy * rr, bz - 0.008 - 0.004 * v)
    mb.grid(peak, 16, 2, trim, smooth=True)
    mb.grid(peak, 16, 2, trim, smooth=True, flip=True)
    # front crest plate (small gold flame/ruyi shape)
    top_front = Vector((0, cy - sy * 0.98, bz + 0.03))
    mb.sphere(top_front + Vector((0, -0.002, 0)), 0.008, trim, 12, 8, scale=(1.0, 0.35, 1.4))
    # finial spike + tassel
    tz = rzt + 0.034
    mb.lathe([(0.012, tz - 0.004), (0.014, tz + 0.004), (0.006, tz + 0.012), (0.009, tz + 0.02),
              (0.004, tz + 0.03), (0.0, tz + 0.06)], trim, 12, center=(cx, cy, 0))
    if plume:
        # horsehair tassel (红缨): strands spray out of the finial cup and droop around the spike
        for i in range(140):
            a = rng.uniform(0, TAU)
            l = rng.uniform(0.045, 0.075)
            start = Vector((cx, cy, tz + 0.026))
            out = Vector((math.cos(a), math.sin(a), 0.0))
            pts = []
            for k in range(6):
                t = k / 5
                pts.append(tuple(start + out * (l * (0.15 + 0.6 * t)) +
                                 Vector((0, 0, 0.012 * math.sin(math.pi * t * 0.8) - l * 0.75 * t ** 1.6))))
            mb.tube(pts, rng.uniform(0.0016, 0.0028), plume_mat, 4, radius_fn=lambda t: 1.0 - 0.75 * t)
    # neck & cheek guards: lamellar skirt hanging from the brim, open at the face
    def guard(u, v):
        a = math.radians(-60 + 300 * u)          # from front-left round the back to front-right
        a = -math.pi / 2 + math.radians(60) + math.radians(240) * u
        rr = 1.03 + 0.16 * v ** 1.3
        z = bz - 0.008 - 0.075 * v
        return (cx + math.cos(a) * sx * rr, cy + math.sin(a) * sy * rr, z)
    mb.grid(guard, 40, 6, neck_guard, lambda u, v: (u * 0.5, v * 0.09), smooth=True)
    mb.grid(guard, 40, 6, neck_guard, lambda u, v: (u * 0.5, v * 0.09), smooth=True, flip=True)
    mb.tube([guard(u, 1.0) for u in np.linspace(0, 1, 40)], 0.0025, trim, 5)
    return {"start": s, "finial_z": tz + 0.022, "brim_z": bz}


def topknot(mb, lm, mat="Hair", pin="Gold"):
    """Hair cap + topknot bun with a pin (no-helmet archetypes)."""
    rx, ry, rzt = lm["rx"], lm["ry"], lm["rz_top"]
    prof = []
    for k in range(10):
        a = (k / 9) * math.pi / 2
        prof.append((math.cos(a), lm["brow_z"] + 0.035 + (rzt + 0.006 - lm["brow_z"] - 0.035) * math.sin(a)))
    mb.lathe(prof, mat, 40, center=(0, 0.004, 0), scale_xy=(rx * 1.04, ry * 1.04))
    mb.sphere((0, 0.01, rzt + 0.012), 0.022, mat, 16, 10, scale=(1, 1, 0.8))
    mb.cylinder((-0.04, 0.01, rzt + 0.016), (0.04, 0.01, rzt + 0.016), 0.0025, mat=pin, segments=6)


# ---------------------------------------------------------------------------------------------
# torso: armour & robes
# ---------------------------------------------------------------------------------------------
def torso(mb, lm, shoulder_w=0.44, chest_d=0.24, mat="Lamellar", segments=48, slope=1.0):
    """Upper body: neck base -> sloping trapezius -> rounded shoulders -> chest, as stacked
    superellipse rings (boxy but soft).  Returns the shoulder-line z."""
    top = lm["neck"].z - 0.045
    hw, hd = shoulder_w / 2, chest_d / 2
    # (half-width, half-depth, dz, superellipse exponent)
    prof = [(0.060, 0.055, 0.0, 2.0), (0.085, 0.070, -0.012 * slope, 2.2),
            (0.135, 0.085, -0.032 * slope, 2.6), (0.180, 0.100, -0.055 * slope, 3.0),
            (hw * 0.97, hd * 0.95, -0.085 * slope, 3.2), (hw, hd, -0.125, 3.2),
            (hw * 0.98, hd, -0.20, 3.0), (hw * 0.93, hd * 0.98, -0.32, 2.8)]
    rings = []
    for (sx, sy, dz, e) in prof:
        ring = []
        for i in range(segments):
            a = TAU * i / segments
            ca, sa = math.cos(a), math.sin(a)
            r = (abs(ca) ** e + abs(sa) ** e) ** (-1 / e)
            ring.append(mb.v((ca * r * sx, 0.02 + sa * r * sy, top + dz)))
        rings.append(ring)
    for k in range(len(rings) - 1):
        mb.quad_strip(rings[k], rings[k + 1], mat, True, True)
    return top - 0.055 * slope


def robe_collar(mb, lm, mat="SilkInner", outer="Silk", width=0.04):
    """Crossed (jiaoling) collar: two bands forming a V from the neck down the chest."""
    n = lm["neck"]
    z0 = n.z - 0.03
    for sgn in (1, -1):
        def fn(u, v, s=sgn):
            # u across the band, v down
            x = s * (0.045 - 0.05 * v) + (u - 0.5) * width * s * -1
            z = z0 - 0.13 * v
            y = -0.055 - 0.06 * v - 0.012 * math.sin(math.pi * u)
            return (x, y, z)
        mb.grid(fn, 4, 10, outer if sgn > 0 else outer, smooth=True)
    # inner collar (white/red) ring around the neck
    mb.lathe([(0.058, z0 - 0.02), (0.062, z0 + 0.012), (0.056, z0 + 0.03)], mat, 32,
             center=(0, 0.018, 0), scale_xy=(1.0, 0.95))


def neck_scarf(mb, lm, mat="Silk", inner="SilkInner", radius=0.064, height=0.04, folds=9):
    """Silk scarf wrapped around the neck base (general's red neckerchief) with soft folds, over a
    cream inner collar."""
    nz = lm["neck"].z - 0.03
    cy = 0.018
    prof = []
    for k in range(7):
        t = k / 6
        prof.append((radius * (1.0 + 0.22 * math.sin(math.pi * t)), nz - height * 0.5 + height * t))
    s0 = mb.n
    mb.lathe(prof, mat, 48, center=(0, cy, 0), smooth=True)
    for i in range(s0, mb.n):
        v = mb.verts[i]
        a = math.atan2(v.y - cy, v.x)
        k = 1.0 + 0.06 * math.sin(a * folds) * math.sin((v.z - nz) * 60)
        mb.verts[i] = Vector((v.x * k, cy + (v.y - cy) * k, v.z))
    mb.lathe([(radius * 0.92, nz + height * 0.45), (radius * 0.86, nz + height * 0.75),
              (radius * 0.80, nz + height * 0.9)], inner, 40, center=(0, cy, 0), smooth=True)


def cape(mb, lm, shoulder_w=0.44, mat="Silk", length=0.4, folds=7, spread=1.0):
    """Cloak hanging behind the shoulders (visible at the sides and behind the neck)."""
    top = lm["neck"].z - 0.05

    def fn(u, v):
        # phi: 0 = subject's left side (+x), 90 deg = the back (+y), 180 deg = right side
        a = math.radians(-15 + 210 * u)
        rx = shoulder_w / 2 * (1.05 + 0.15 * v) * spread
        ry = 0.12 * (1.0 + 0.2 * v)
        fold = 1.0 + 0.05 * v * math.sin(u * folds * TAU)
        x = math.cos(a) * rx * fold
        y = 0.04 + math.sin(a) * ry * fold
        z = top + 0.02 - length * v - 0.03 * math.cos(math.pi * (u - 0.5)) * (1 - v)
        return (x, y, z)
    mb.grid(fn, 40, 10, mat, smooth=True)
    mb.grid(fn, 40, 10, mat, smooth=True, flip=True)


def pauldrons(mb, lm, shoulder_w=0.44, tiers=3, mat="Lamellar", trim="Bronze", size=1.0):
    """Layered shoulder guards (披膊): overlapping ellipsoidal bands over each shoulder, each with
    a metal edge, stepping down the upper arm."""
    top = lm["neck"].z - 0.045
    for sgn in (1, -1):
        c0 = Vector((sgn * (shoulder_w / 2 - 0.035), 0.02, top - 0.05))
        for t in range(tiers):
            c = c0 + Vector((sgn * 0.012 * t, 0.0, -0.034 * t))
            R = Vector((0.07 + 0.008 * t, 0.095 + 0.006 * t, 0.06)) * size
            th0, th1 = math.radians(25 + 14 * t), math.radians(70 + 14 * t)

            def fn(u, v, c=c, R=R, th0=th0, th1=th1):
                ph = math.radians(-75 + 150 * u)
                th = th0 + (th1 - th0) * v
                return (c.x + sgn * R.x * math.sin(th) * math.cos(ph) * 1.0,
                        c.y + R.y * math.sin(th) * math.sin(ph),
                        c.z + R.z * math.cos(th))
            mb.grid(fn, 20, 5, mat, lambda u, v: (u * 0.25, v * 0.06), smooth=True,
                    flip=(sgn < 0))
            mb.grid(fn, 20, 5, mat, lambda u, v: (u * 0.25, v * 0.06), smooth=True,
                    flip=(sgn > 0))
            mb.tube([fn(u, 1.0) for u in np.linspace(0, 1, 20)], 0.0032, trim, 5)


def mirror_plate(mb, lm, radius=0.055, mat="Bronze", rim="Gold", z_offset=-0.17, y=-0.125,
                 tilt_deg=12.0):
    """Round chest mirror (护心镜): domed bronze disc with a raised gold rim, facing -Y."""
    n = lm["neck"]
    c = Vector((0, y, n.z + z_offset))
    s = mb.n
    mb.lathe([(0.0, radius * 0.16), (radius * 0.12, radius * 0.16), (radius * 0.2, radius * 0.11),
              (radius * 0.85, radius * 0.06), (radius, 0.0)], mat, 32)
    mb.lathe([(radius, 0.0), (radius * 1.05, radius * 0.07), (radius * 1.12, radius * 0.05),
              (radius * 1.14, -0.004)], rim, 32)
    mb.transform(s, Matrix.Translation(c) @ Matrix.Rotation(math.radians(90 - tilt_deg), 4, "X"))


# ---------------------------------------------------------------------------------------------
# hair strands (render with geometry.hair_curves + materials.hair_strands)
# ---------------------------------------------------------------------------------------------
def _bezier(p0, p1, p2, p3, n):
    out = []
    for i in range(n):
        t = i / (n - 1)
        u = 1 - t
        out.append(p0 * u ** 3 + p1 * 3 * u * u * t + p2 * 3 * u * t * t + p3 * t ** 3)
    return out


def _skin_normal(V, i, center=Vector((0, 0.0, -0.01))):
    return (Vector(V[i]) - center).normalized()


def beard_strands(lm, count=4000, length=0.15, spread=1.0, converge=0.75, bulge=1.0,
                  side_extent=1.0, mouth_gap=True, rng=None, clumps=140, wave=0.002,
                  sideburns=True):
    """Strand polylines for a full general's beard (cheeks + jaw + chin -> spade point).

    length     chin strand length (m); cheek strands are shorter
    converge   0 = straight curtain, 1 = all tips meet on the centre line (pointed beard)
    bulge      forward volume of the beard body
    """
    rng = rng or random.Random(5)
    V = lm["verts"]
    tip_z = lm["nose_tip"].z
    mz = lm["mouth"].z
    x, y, z = V[:, 0], V[:, 1], V[:, 2]
    az = np.arctan2(x, -y)                                  # 0 = front
    zmax = np.where(np.abs(az) < 0.5, tip_z - 0.012, tip_z + 0.012 if sideburns else tip_z - 0.01)
    region = (z < zmax) & (z > -0.13) & (np.abs(az) < 1.85 * side_extent) & (y < 0.012)
    if mouth_gap:
        region &= ~((np.abs(x) < 0.02) & (z > mz - 0.01) & (z < mz + 0.005))
    region &= ~((np.abs(x) < 0.012) & (z > mz + 0.004) & (z < tip_z - 0.008))   # philtrum (mustache covers)
    idx = np.nonzero(region)[0]
    if len(idx) == 0:
        return []
    chin_z = lm["chin"].z
    centre_tip = Vector((0, lm["chin"].y - 0.03 * bulge, chin_z - length))
    # clump guides
    guides = [Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), 0)) * 0.006 for _ in range(clumps)]
    strands = []
    for k in range(count):
        i = int(idx[rng.randrange(len(idx))])
        root = Vector(V[i]) + Vector((rng.uniform(-1, 1), 0, rng.uniform(-1, 1))) * 0.0015
        nrm = _skin_normal(V, i)
        a = float(az[i])
        side = min(1.0, abs(a) / 1.8)
        # strand length: long at the chin, short on the cheeks/sideburns
        L = length * (0.38 + 0.62 * (1 - side) ** 1.3) * rng.uniform(0.75, 1.05)
        L *= 0.6 + 0.4 * np.clip((tip_z - root.z) / 0.08, 0, 1)
        end = Vector((root.x * (1 - converge * (0.6 + 0.4 * (1 - side))),
                      root.y - 0.02 * bulge * (1 - side) - 0.01,
                      root.z - L))
        if side < 0.6:
            end = end.lerp(centre_tip + Vector((root.x * (1 - converge), 0, 0)), 0.35 * (1 - side) * converge)
        g = guides[hash((round(root.x * 60), round(root.z * 60))) % clumps]
        end += g * (1.5 + 4 * (1 - side))
        p1 = root + nrm * (0.010 + 0.012 * bulge * (1 - side)) + Vector((0, 0, -0.004))
        p2 = end + Vector((0, -0.012 * bulge * (1 - side), L * 0.35)) + g
        n = 10
        pts = _bezier(root - nrm * 0.0015, p1, p2, end, n)
        ph = rng.uniform(0, TAU)
        pts = [q + Vector((math.sin(ph + t * 9) * wave * t, 0, 0)) for t, q in
               zip(np.linspace(0, 1, n), pts)]
        strands.append(pts)
    return strands


def mustache_strands(lm, count=700, length=0.05, droop=1.0, rng=None, spread=1.0):
    """Two drooping mustache locks rooted on the upper lip, sweeping out and down past the
    mouth corners."""
    rng = rng or random.Random(6)
    tip = lm["nose_tip"]
    mz = lm["mouth"].z
    strands = []
    for k in range(count):
        sgn = 1 if k % 2 else -1
        t0 = rng.random()
        rx = sgn * (0.002 + 0.02 * t0 * spread)
        rz = tip.z - 0.011 - 0.004 * t0 + rng.uniform(-0.002, 0.002)
        ry = lm["surf_y"](rx, rz) + 0.0005
        root = Vector((rx, ry, rz))
        L = length * rng.uniform(0.7, 1.05) * (0.6 + 0.4 * t0)
        end = Vector((sgn * (0.026 + 0.012 * t0) * spread, ry - 0.002 + 0.006 * t0,
                      mz - 0.012 - L * 0.5 * droop))
        p1 = root + Vector((sgn * 0.01, -0.006, -0.002))
        p2 = end + Vector((sgn * -0.004, -0.004, 0.012))
        strands.append(_bezier(root, p1, p2, end, 8))
    return strands


def brow_strands(lm, count=500, thickness=1.0, angle=0.3, rng=None, length=0.011):
    """Short strands lying on the brow ridge, combed outwards (warrior brows: thick, angled up
    towards the temples when ``angle`` > 0)."""
    rng = rng or random.Random(8)
    p = lm["params"]
    es = 0.031 * p.eye_spacing
    strands = []
    for k in range(count):
        sgn = 1 if k % 2 else -1
        t = rng.random()
        bx = sgn * (es - 0.018 + 0.038 * t)
        bz = lm["brow_z"] + 0.002 + 0.006 * math.sin(math.pi * min(1.0, t * 1.15)) \
            + angle * 0.012 * t + rng.uniform(-1, 1) * 0.0028 * thickness * (1 - 0.5 * t)
        by = lm["surf_y"](bx, bz) + 0.0003
        root = Vector((bx, by, bz))
        d = Vector((sgn * 1.0, -0.15, 0.25 + angle * 0.4 - 0.5 * t)).normalized()
        L = length * rng.uniform(0.6, 1.0) * (1.15 - 0.4 * t)
        mid = root + d * L * 0.5 + Vector((0, -0.0012, 0))
        end = root + d * L + Vector((0, -0.0004, -0.001))
        strands.append([root, mid, end])
    return strands


def plume_strands(lm, count=900, length=0.07, rng=None, top=None, radius=0.034):
    """Horsehair tassel (红缨) bursting from the helmet finial and falling around it like a
    loose mop onto the dome (uneven lengths and spread so it never reads as a cylinder)."""
    rng = rng or random.Random(9)
    tz = (top if top is not None else lm["rz_top"] + 0.06)
    start = Vector((0, 0.004, tz))
    strands = []
    for k in range(count):
        a = rng.uniform(0, TAU)
        L = length * rng.uniform(0.45, 1.15)
        R = radius * rng.uniform(0.35, 1.25)
        out = Vector((math.cos(a), math.sin(a), 0))
        lift = rng.uniform(0.0, 0.016)
        sway = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), 0)) * 0.006
        pts = []
        for i in range(9):
            t = i / 8
            r = R * math.sin(min(1.0, t * 1.4) * math.pi / 2) ** 0.7
            zz = lift * math.sin(math.pi * min(1.0, t * 1.6)) - L * max(0.0, t - 0.2) ** 1.3
            pts.append(start + out * r + sway * t * t + Vector((0, 0, zz)))
        strands.append(pts)
    return strands
