"""Procedural portrait kit: sculpted head, eyes, brows, beards, helmets, armour, robes.

Coordinate frame (all builders): metres, head centre (between the ears, mid-height of the skull)
at the origin, the face looks towards **-Y**, +Z up.  ``head()`` returns *landmarks* (eye centres,
nose tip, mouth, chin, brow line, ears, crown, neck) that every other builder uses, so a helmet or
beard follows any head shape.

The head is sculpted numerically: rays from the skull centre find the surface of a smooth SDF
union of anatomical masses (:func:`head_masses`: skull, forehead, face/jaw, chin, jaw angles), then
smooth relief adds the features (:func:`face_relief`: brow ridge, cheekbones, nose, philtrum,
lips, mouth line, chin), the lids conform to spheres around the eyeballs and the opening is carved
behind them.  It is not a likeness engine - it is a sturdy, controllable base that reads as a Koei
painted bust after the painterly pass.  :class:`HeadParams` exposes the knobs archetypes need, and
:data:`ARCHETYPES` / :func:`bust` build complete warrior / scholar / female busts.

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
#: mouth line height (m) relative to the head centre; subnasale ~ -0.036, philtrum 14 mm
MOUTH_Z = -0.0575


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
    lower: float = 1.0          # lower-face length (mouth, chin, jaw angles) - female ~0.9
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


def _ray_sphere(d, c, R):
    """(t_in, t_out) of unit rays ``d`` from the origin through the sphere (c, R); +inf/-inf
    (an empty interval) where they miss."""
    b = d @ c
    disc = b * b - (c @ c - R * R)
    sq = np.sqrt(np.maximum(disc, 0.0))
    return np.where(disc > 0, b - sq, np.inf), np.where(disc > 0, b + sq, -np.inf)


def _smax(vals, k):
    """Smooth maximum (log-sum-exp) of a list of arrays; ``k`` = blend radius in metres."""
    v = np.stack(vals, 0)
    m = np.max(v, 0)
    m = np.where(np.isfinite(m), m, 0.0)
    return m + k * np.log(np.sum(np.exp(np.clip((v - m) / k, -60, 0)), 0))


def head_masses(p):
    """Base skull/face masses for :class:`HeadParams` ``p`` (subject's left = +x) as
    ``(centre, radii, blend_k)``: the head surface is their smooth SDF union (polynomial smooth
    minimum, ``blend_k`` metres), so masses merge without the creases an ellipsoid union leaves.
    Facial features are *not* masses: they are smooth additive relief (:func:`face_relief`).

    Proportions (head height 232 mm): face mass narrows from 128 mm at the cheekbones to a
    ~100 mm jaw angle and a ~45 mm chin; the chin sits ~6 mm behind the lower lip."""
    j, ch, lo = p.jaw, p.chin, p.lower
    W = p.width / 0.150
    D = p.depth / 0.190
    Hh = p.height / 0.232
    return [
        ((0, 0.012 * D, 0.022 * Hh), (0.074 * W, 0.097 * D, 0.100 * Hh), 0.0),       # cranium
        ((0, -0.022 * D, 0.030 * Hh), (0.066 * W, 0.064 * D, 0.064 * Hh), 0.012),    # forehead
        ((0, -0.016 * D, -0.034 * Hh), (0.063 * W * (0.55 + 0.45 * j), 0.074 * D, 0.077 * Hh),
         0.016),                                                                      # face + jaw
        ((0, -0.045 * D, -0.086 * Hh * lo), (0.027 * ch, 0.040 * ch, 0.024 * Hh), 0.018),  # chin
        ((0.041 * W * j, -0.004 * D, -0.067 * Hh * lo), (0.012, 0.026, 0.015), 0.022),  # jaw angles
        ((-0.041 * W * j, -0.004 * D, -0.067 * Hh * lo), (0.012, 0.026, 0.015), 0.022),
    ]


def _ell_sdf(P, c, R):
    """Bound-correct approximate signed distance to an axis-aligned ellipsoid (negative inside)."""
    q = (P - np.asarray(c)) / np.asarray(R)
    k0 = np.linalg.norm(q, axis=1)
    k1 = np.linalg.norm(q / np.asarray(R), axis=1)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


def _smin(a, b, k):
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


def head_sdf(P, masses):
    f = None
    for (c, R, k) in masses:
        e = _ell_sdf(P, c, R)
        f = e if f is None else _smin(f, e, k)
    return f


def _ray_radius(d, masses, lo=0.01, hi=0.25, iters=34):
    """Radius along each unit ray ``d`` (from the skull centre) where the SDF union crosses 0
    (bisection; the head is star-shaped from the centre)."""
    a = np.full(len(d), lo)
    b = np.full(len(d), hi)
    for _ in range(iters):
        m = 0.5 * (a + b)
        inside = head_sdf(d * m[:, None], masses) < 0
        a = np.where(inside, m, a)
        b = np.where(inside, b, m)
    return 0.5 * (a + b)


def face_relief(p, x, z, d):
    """Smooth additive relief (radial metres) of the facial features at base-surface points
    (x, z) with unit ray directions ``d``: brow ridge, cheekbones, nose (bridge rising from the
    root to a 20 mm tip, rounded tip, alae on the cheeks, sharp fall-off to the subnasale),
    philtrum, lips, chin boss.  Proportions: brow to nose base ~58 mm, philtrum ~14 mm, mouth
    50 mm wide at z -56 mm."""
    fw = np.clip((-d[:, 1] - 0.35) / 0.4, 0, 1)
    fs = np.clip((-d[:, 1] - 0.05) / 0.4, 0, 1)
    nl, nw, nb = p.nose_len, p.nose_width, p.nose_bridge
    ax = np.abs(x)
    off = np.zeros_like(x)
    # brow ridge (broad, soft) + nasion dip
    off += 0.0032 * p.brow * _g2(x, z - 0.024, 0.040, 0.0075) * fw
    off -= 0.0030 * _g2(x, z - 0.011, 0.006, 0.005) * fw
    # cheekbones (front-side)
    off += 0.0055 * p.cheekbone * _g2(ax - 0.044, z + 0.006, 0.016, 0.011) * fs
    # nose
    z_root, z_tip = 0.009, -0.029 * nl
    span = z_root - z_tip
    s = (z_root - z) / span
    h_bridge = (0.0025 + 0.0165 * nb * np.clip(s, 0, 1) ** 1.2) * np.clip(s / 0.15 + 1.0, 0, 1)
    below = np.clip((s - 1.0) * span, 0, None)
    h_bridge = h_bridge * np.exp(-(below / 0.0042) ** 2)
    wid = (0.0050 + 0.0034 * np.clip(s, 0, 1.1) ** 2) * nw
    off += h_bridge * np.exp(-0.5 * (x / wid) ** 2) * fw
    off += 0.0015 * _g2(x, z - (z_tip + 0.0005), 0.0056 * nw, 0.0050) * fw            # tip ball
    off += 0.0050 * _g2(ax - 0.0110 * nw, z - (z_tip - 0.0035), 0.0048 * nw, 0.0044) * fw  # alae
    off -= 0.0014 * _g2(ax - 0.0170 * nw, z - (z_tip - 0.002), 0.0016, 0.0052) * fw  # alar crease
    # mouth (50 mm wide at MZ): maxillary fullness, 14 mm philtrum, lips, a crisp mouth line that
    # stops at the corners, mentolabial sulcus, chin boss
    MZ = MOUTH_Z * p.height / 0.232 * p.lower
    cut = np.clip((0.0255 - ax) / 0.004, 0, 1)                    # nothing past the mouth corners
    off += 0.0035 * _g2(x, z - (MZ + 0.002), 0.022, 0.016) * fw
    off -= 0.0007 * _g2(x, z - (MZ + 0.013), 0.0030, 0.0050) * fw              # philtrum groove
    off += 0.0004 * _g2(ax - 0.0045, z - (MZ + 0.013), 0.0015, 0.0050) * fw    # philtral ridges
    off += 0.0022 * p.lips * _g2(x, z - (MZ + 0.0036), 0.0160, 0.0032) * fw * cut
    off += 0.0028 * p.lips * _g2(x, z - (MZ - 0.0046), 0.0135, 0.0038) * fw * cut
    off -= 0.0020 * _g2(x * 0.0, z - MZ, 1.0, 0.0010) * fw * cut                # mouth line
    off -= 0.0010 * _g2(ax - 0.0255, z - MZ, 0.0030, 0.0032) * fw              # corners
    off -= 0.0012 * _g2(x, z - (MZ - 0.0150), 0.0120, 0.0032) * fw             # sulcus
    off += 0.0030 * p.chin * _g2(x, z + 0.089 * p.height / 0.232 * p.lower, 0.013, 0.010) * fw  # chin
    return off


def head(params=None, segments=320, rings=224, mat="Skin", blend=0.014):
    """Sculpt the head as a smooth union of anatomical masses evaluated along radial rays from
    the skull centre (the head is star-shaped from there), then carve eye sockets and add
    detail offsets.  Returns ``(MeshBuilder, landmarks)``."""
    p = params or HeadParams()
    mb = geo.MeshBuilder()
    s0 = mb.n
    mb.sphere((0, 0, 0), 1.0, mat, segments, rings, smooth=True)
    V = np.array([tuple(v) for v in mb.verts[s0:]], np.float64)
    d = V / np.maximum(np.linalg.norm(V, axis=1, keepdims=True), 1e-9)
    r = _ray_radius(d, head_masses(p))
    P = d * r[:, None]
    r = r + face_relief(p, P[:, 0], P[:, 2], d)
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
    # socket concavity above the lid and the cheek pad under it go in *before* the lids conform
    # to the eyeballs (applied after, they pushed the upper lid through the eyeball)
    P = d * r[:, None]
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    for sgn in (1, -1):
        r = r - 0.0028 * p.socket * (1 + 0.25 * p.age) * _g2(x - sgn * (es + 0.002), z - ez - 0.015, 0.014, 0.006) * fw
        r = r + 0.0012 * _g2(x - sgn * (es + 0.004), z - ez + 0.02, 0.012, 0.004) * fw
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
        e_in, _e_out = _ray_sphere(d, c, re_ * 1.04)
        r = np.where(o > 0, r * (1 - o) + o * np.minimum(r, e_in - 0.0005), r)
    P = d * r[:, None]
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    for sgn in (1, -1):
        off += (0.0008 + 0.0020 * p.age) * _g2(x - sgn * 0.026, z + 0.044, 0.0032, 0.011) * fw  # naso-labial
        off -= (0.0008 + 0.0020 * p.age) * _g2(x - sgn * 0.046, z + 0.042, 0.012, 0.012)  # cheek hollow
        off -= 0.003 * _g2(np.abs(x) - 0.064, z - 0.03, 0.01, 0.018) * (np.sign(x) == sgn)  # temples
    rng = np.random.default_rng(p.seed)
    ph = rng.uniform(0, TAU, 2)
    off += 0.0005 * np.sin(x * 120 + ph[0]) * np.sin(z * 90 + ph[1]) * fw
    r2 = r + off
    # no skin inside the eyeballs: a vertex between a ray's entry and exit of the (1.04 r) eye
    # sphere moves to the exit (lid in front of the eye) - crisp lid edges, nothing pokes through
    for (c, re_, sgn) in eye_specs:
        t_in, t_out = _ray_sphere(d, np.array(c), re_ * 1.04)
        inside = (r2 > t_in) & (r2 < t_out)
        r2 = np.where(inside, np.where(r2 - t_in < t_out - r2, t_in - 0.0005, t_out), r2)
    newV = d * r2[:, None]
    for i, co in enumerate(newV):
        mb.verts[s0 + i] = Vector(co)
    x, y, z = newV[:, 0], newV[:, 1], newV[:, 2]
    tip_z = -0.029 * p.nose_len
    bl = np.clip(_g2(np.abs(x) - 0.042, z + 0.022, 0.016, 0.014) * 0.8
                 + _g2(x, z - tip_z, 0.01, 0.01) * 0.6, 0, 1)
    fr = (newV[:, 1] < -0.04).astype(np.float64)
    cut = np.clip((0.0255 - np.abs(x)) / 0.004, 0, 1) * fr
    MZ = MOUTH_Z * p.height / 0.232 * p.lower
    lip = np.clip(1.6 * (_g2(x, z - (MZ + 0.0036), 0.0160, 0.0030)
                         + _g2(x, z - (MZ - 0.0046), 0.0135, 0.0036)), 0, 1) * cut
    mouth = np.clip(1.3 * _g2(0.0, z - MZ, 1.0, 0.0015), 0, 1) * cut
    bva = mb.vattr.setdefault("blush", {})
    lva = mb.vattr.setdefault("lip", {})
    mva = mb.vattr.setdefault("mouth", {})
    for i in range(len(bl)):
        bva[s0 + i] = float(bl[i])
        lva[s0 + i] = float(lip[i])
        mva[s0 + i] = float(mouth[i])

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
    mz = MOUTH_Z * p.height / 0.232 * p.lower
    lm = {
        "params": p,
        "eye_l": eye_specs[0][0],                                      # subject's left = +x
        "eye_r": eye_specs[1][0],
        "eye_specs": eye_specs,
        "nose_tip": Vector((0, surf_y(0, tip_z), tip_z)),
        "mouth": Vector((0, surf_y(0, mz), mz)),
        "chin": Vector((0, surf_y(0, -0.092), -0.092)),
        "subnasale": Vector((0, surf_y(0, tip_z - 0.007), tip_z - 0.007)),
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


def eyeballs(eye_specs, material, look=(0.0, 0.0), name="Eye", look_at=None, look_weight=1.0):
    """Create one object per eyeball (unit sphere scaled to the radius, origin at the centre) so
    :func:`ironart.materials.eye`'s object-space iris works.  ``look`` = (yaw, pitch) radians,
    positive yaw turns the gaze towards the subject's left (+x), positive pitch looks down.
    ``look_at`` (a world point, e.g. ``cam.location``) aims both eyes at it instead - the studio
    portrait gaze: the general stares at the viewer.  ``look_weight`` < 1 blends towards straight
    ahead."""
    import bpy
    objs = []
    for (c, r, sgn) in eye_specs:
        emb = geo.MeshBuilder()
        emb.sphere((0, 0, 0), 1.0, "Eye", 32, 20, smooth=True)
        o = emb.build("%s_%s" % (name, "L" if sgn > 0 else "R"), {"Eye": material},
                      auto_smooth_deg=None)
        o.location = c
        o.scale = (r, r, r)
        if look_at is not None:
            d = Vector(look_at) - Vector(c)
            yaw = math.atan2(d.x, -d.y) * look_weight
            pitch = -math.atan2(d.z, math.hypot(d.x, d.y)) * look_weight
            o.rotation_euler = (pitch, 0.0, yaw)
        else:
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
    rzb = lm["rz_bot"]
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
           neck_guard="Lamellar", ribs=12, brim_z=None, scale=1.0, rng=None, guard_len=0.075,
           visor=0.11, finial="cup", guard_flare=0.16):
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
    mb.lathe(prof, mat, 48, center=(cx, cy, 0), smooth=True, scale_xy=(sx, sy))
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
        rr = 1.0 + visor * v * math.cos((-1 + 2 * u) * 1.4)
        return (cx + math.cos(a) * sx * rr, cy + math.sin(a) * sy * rr, bz - 0.008 - 0.004 * v)
    mb.grid(peak, 16, 2, trim, smooth=True)
    # front crest plate (small gold flame/ruyi shape)
    top_front = Vector((0, cy - sy * 0.98, bz + 0.03))
    mb.sphere(top_front + Vector((0, -0.002, 0)), 0.008, trim, 12, 8, scale=(1.0, 0.35, 1.4))
    # finial: 'cup' (compact plume cup - the portrait standard, fits the 192x240 frame with the
    # eyes at 38 %) or 'spike' (tall spike, battle sprites / events)
    if finial == "spike":
        tz = rzt + 0.034
        mb.lathe([(0.012, tz - 0.004), (0.014, tz + 0.004), (0.006, tz + 0.012), (0.009, tz + 0.02),
                  (0.004, tz + 0.03), (0.0, tz + 0.06)], trim, 12, center=(cx, cy, 0))
        fz = tz + 0.022
    else:
        tz = rzt + 0.016
        mb.lathe([(0.011, tz - 0.006), (0.013, tz + 0.002), (0.008, tz + 0.006), (0.011, tz + 0.012),
                  (0.0, tz + 0.013)], trim, 12, center=(cx, cy, 0))
        fz = tz + 0.010
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
        rr = 1.03 + guard_flare * v ** 1.3
        z = bz - 0.008 - guard_len * v
        return (cx + math.cos(a) * sx * rr, cy + math.sin(a) * sy * rr, z)
    mb.grid(guard, 40, 6, neck_guard, lambda u, v: (u * 0.5, v * 0.09), smooth=True)
    mb.tube([guard(u, 1.0) for u in np.linspace(0, 1, 40)], 0.0025, trim, 5)
    return {"start": s, "finial_z": fz, "brim_z": bz}


def topknot(mb, lm, mat="Hair", pin="Gold"):
    """Hair cap + topknot bun with a pin (no-helmet archetypes)."""
    hair_cap(mb, lm, mat)
    bun(mb, lm, mat, pin=pin)


def _hairline_z(az, front=0.072, temple=0.050, side=0.028, nape=-0.045):
    """Hairline height (m) at azimuth ``az`` (0 = front centre, +-pi = back)."""
    t = abs(az)
    if t < 0.75:                                    # forehead -> temple recess
        u = t / 0.75
        return front + (temple - front) * (u * u * (3 - 2 * u))
    if t < 1.75:                                    # temple -> above the ear
        u = (t - 0.75) / 1.0
        return temple + (side - temple) * u
    u = min(1.0, (t - 1.75) / (math.pi - 1.75))     # behind the ear -> nape
    return side + (nape - side) * (u * u * (3 - 2 * u))


def hair_cap(mb, lm, mat="Hair", thickness=0.004, crown=0.012, nu=64, nv=18, hairline=None,
             part=0.0):
    """Hair shell conforming to the skull (ray-cast against :func:`head_masses`) from a natural
    hairline (forehead, temple recesses, above the ears, nape) up to the crown, ``thickness`` at
    the hairline growing to ``crown`` on top (volume).  UV: u around, v from hairline to crown
    (use ``materials.hair_mesh(direction='UV')`` for strands combed back).  ``part`` > 0 adds a
    centre parting groove."""
    p = lm["params"]
    masses = head_masses(p)
    hl = hairline or {}

    def fn(u, v):
        az = (u - 0.5) * TAU                       # u = 0.5 -> front centre
        zh = _hairline_z(az, **hl)
        el0 = math.asin(max(-0.95, min(0.95, (zh - 0.0) / 0.105)))
        el = el0 + (math.pi / 2 - 0.02 - el0) * v
        dvec = np.array([[math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)]])
        r = float(_ray_radius(dvec, masses)[0])
        th = 0.0006 + (thickness - 0.0006) * min(1.0, v * 6.0) + (crown - thickness) * (v ** 0.7)
        th *= 1.0 - part * math.exp(-((az / 0.08) ** 2)) * (v > 0.05)
        return tuple(dvec[0] * (r + th))
    mb.grid(fn, nu, nv, mat, lambda u, v: (u * 0.6, v * 0.25), smooth=True)


def bun(mb, lm, mat="Hair", size=0.026, pos=(0.0, 0.012, 0.0), pin="Gold", pin_len=0.09,
        tilt=0.0, double=False):
    """Hair bun (topknot) on the crown with a hairpin through it; ``double`` = two side buns
    (young women)."""
    rzt = lm["rz_top"]
    centres = [(pos[0], pos[1], rzt + pos[2] + size * 0.45)]
    if double:
        centres = [(s * 0.045, pos[1] + 0.01, rzt + pos[2] - 0.004) for s in (-1, 1)]
    for c in centres:
        mb.sphere(c, size, mat, 18, 12, scale=(1.0, 1.0, 0.85))
        mb.tube([(c[0] - 0.008, c[1] - 0.004, c[2] + size * 0.55),
                 (c[0], c[1] - 0.007, c[2] + size * 0.72), (c[0] + 0.008, c[1] - 0.004, c[2] + size * 0.55)],
                size * 0.22, mat, 6)
        if pin:
            mb.cylinder((c[0] - pin_len / 2, c[1], c[2] + size * 0.15 + tilt),
                        (c[0] + pin_len / 2, c[1], c[2] + size * 0.15 - tilt), 0.0022, mat=pin, segments=6)
            mb.sphere((c[0] + pin_len / 2, c[1], c[2] + size * 0.15 - tilt), 0.005, pin, 8, 6)


def guan(mb, lm, mat="Guan", pin="Gold", height=0.05):
    """Scholar's small crown cap (小冠) over the topknot: a black gauze/lacquer cap open at the
    sides, with a hairpin through it."""
    rzt = lm["rz_top"]
    c = Vector((0.0, 0.016, rzt + 0.004))
    w, d = 0.030, 0.050
    prof = [(1.0, 0.0), (1.02, height * 0.5), (0.92, height * 0.9), (0.6, height), (0.0, height * 1.02)]
    mb.lathe([(r, c.z + z) for r, z in prof], mat, 24, center=(c.x, c.y, 0), smooth=True,
             scale_xy=(w, d))
    mb.lathe([(1.04, c.z - 0.002), (1.06, c.z + 0.004), (1.03, c.z + 0.008)], pin, 24,
             center=(c.x, c.y, 0), smooth=True, scale_xy=(w, d))
    mb.cylinder((-0.055, c.y, c.z + height * 0.45), (0.055, c.y, c.z + height * 0.45), 0.0024,
                mat=pin, segments=6)


# ---------------------------------------------------------------------------------------------
# torso: armour & robes
# ---------------------------------------------------------------------------------------------
def _torso_profile(shoulder_w=0.44, chest_d=0.24, slope=1.0):
    """(half-width, half-depth, dz, superellipse exponent) rings from the neck base down."""
    hw, hd = shoulder_w / 2, chest_d / 2
    k = hw / 0.22                       # trapezius/shoulder widths follow the shoulder width
    return [(0.060, 0.055, 0.0, 2.0), (0.085 * k ** 0.5, 0.070, -0.012 * slope, 2.2),
            (0.135 * k, 0.085, -0.032 * slope, 2.6), (0.180 * k, 0.100, -0.055 * slope, 3.0),
            (hw * 0.97, hd * 0.95, max(-0.085 * slope, -0.112), 3.2), (hw, hd, -0.125 - 0.01 * (slope - 1), 3.2),
            (hw * 0.98, hd, -0.20, 3.0), (hw * 0.93, hd * 0.98, -0.32, 2.8)]


def torso_surface(lm, shoulder_w=0.44, chest_d=0.24, slope=1.0):
    """``f(a, z, off=0) -> Vector``: point on the :func:`torso` surface at angle ``a`` (radians;
    -pi/2 = front centre, 0 = subject's left side, pi/2 = back) and height ``z``, pushed ``off``
    metres outward - for collars, straps and anything that must lie on the chest."""
    top = lm["neck"].z - lm.get("torso_drop", 0.045)
    prof = _torso_profile(shoulder_w, chest_d, slope)
    zs = [top + q[2] for q in prof]

    def f(a, z, off=0.0):
        z = min(zs[0], max(zs[-1], z))
        k = 0
        while k < len(zs) - 2 and z < zs[k + 1]:
            k += 1
        t = (zs[k] - z) / max(1e-9, zs[k] - zs[k + 1])
        sx, sy, _dz, e = [prof[k][i] + (prof[k + 1][i] - prof[k][i]) * t for i in range(4)]
        ca, sa = math.cos(a), math.sin(a)
        r = (abs(ca) ** e + abs(sa) ** e) ** (-1 / e)
        n = Vector((ca / sx, sa / sy, 0.0)).normalized()
        return Vector((ca * r * sx, 0.02 + sa * r * sy, z)) + n * off
    return f


def torso(mb, lm, shoulder_w=0.44, chest_d=0.24, mat="Lamellar", segments=48, slope=1.0,
          collar=0.0, collar_mat=None, trim="Bronze", top_mat=None, top_rings=2, collar_r=0.074,
          folds=0.0, fold_count=9):
    """Upper body: neck base -> sloping trapezius -> rounded shoulders -> chest, as stacked
    superellipse rings (boxy but soft).  ``top_mat`` (e.g. 'SilkInner') covers the first
    ``top_rings`` ring strips around the neck base: the robe under the armour, which shows inside
    a :func:`cross_collar` V.  Returns the shoulder-line z."""
    top = lm["neck"].z - lm.get("torso_drop", 0.045)
    prof = _torso_profile(shoulder_w, chest_d, slope)
    rings = []
    for k, (sx, sy, dz, e) in enumerate(prof):
        ring = []
        # cloth folds (robes): soft vertical ridges growing from the shoulders down
        fa = folds * min(1.0, max(0.0, (k - 3) / 3.0))
        for i in range(segments):
            a = TAU * i / segments
            ca, sa = math.cos(a), math.sin(a)
            r = (abs(ca) ** e + abs(sa) ** e) ** (-1 / e)
            if fa:
                r *= 1.0 + fa * (0.6 * math.sin(a * fold_count + 0.7) + 0.4 * math.sin(a * fold_count * 2.3 + 2.1))
            ring.append(mb.v((ca * r * sx, 0.02 + sa * r * sy, top + dz)))
        rings.append(ring)
    for k in range(len(rings) - 1):
        m = top_mat if (top_mat and k < top_rings) else mat
        mb.quad_strip(rings[k + 1], rings[k], m, True, True)     # outward winding
    if collar > 0:
        # high stand-up collar (lamellar neck guard) hiding the neck: ``collar`` = height in m
        cr = collar_r
        mb.lathe([(cr, top - 0.01), (cr + 0.004, top + collar * 0.5), (cr + 0.009, top + collar)],
                 collar_mat or mat, 40, center=(0, 0.02, 0), scale_xy=(1.0, 0.92))
        mb.lathe([(cr + 0.007, top + collar), (cr + 0.012, top + collar + 0.004),
                  (cr + 0.006, top + collar + 0.007)],
                 trim, 40, center=(0, 0.02, 0), scale_xy=(1.0, 0.92))
    return top - 0.055 * slope


def cross_collar(mb, lm, outer="Silk", inner="SilkInner", width=0.018, inner_width=0.006,
                 cross_z=-0.085, end_z=-0.12, shoulder_w=0.44, chest_d=0.24, slope=1.0,
                 lift=0.005, neck_x=0.060, stand=0.0, neck_r=0.060):
    """Crossed jiaoling collar (交领右衽): two lapel bands from the back of the neck over the
    trapezius, down the front in a symmetric V that crosses on the sternum at ``cross_z``
    (relative to the neck base), the subject's left lapel on top (right-over-left is reserved
    for the dead).

    Each lapel = an ``inner`` (cream) edge band ``inner_width`` wide along the V edge plus the
    ``outer`` (silk red) band ``width`` wide outside it - the bust's colour accent beside the
    beard.  Lies ``lift`` m above the :func:`torso` surface (same shape args)."""
    surf = torso_surface(lm, shoulder_w, chest_d, slope)
    top = lm["neck"].z - lm.get("torso_drop", 0.045)

    def front_angle(x, z):
        # angle on the front half of the torso surface whose x equals ``x`` (bisection)
        lo, hi = -math.pi, 0.0
        for _ in range(40):
            m = 0.5 * (lo + hi)
            if surf(m, z).x < x:
                lo = m
            else:
                hi = m
        return 0.5 * (lo + hi)

    # V edge of the subject's-left lapel as (x, dz): round the back of the neck, then down the
    # front from the side of the neck to the crossing and a little past it
    back = [(math.radians(a), dz) for a, dz in ((100, 0.004), (70, 0.002), (40, 0.0), (10, -0.004))]
    frontpts = [(neck_x, -0.010), (neck_x * 0.80, -0.024), (neck_x * 0.55, cross_z * 0.55),
                (neck_x * 0.28, cross_z * 0.80), (0.0, cross_z), (-neck_x * 0.22, (cross_z + end_z) / 2),
                (-neck_x * 0.42, end_z)]

    def edge_pts(s):
        pts = []
        for a, dz in back:
            pts.append((a if s > 0 else math.pi - a, top + dz))
        for x, dz in frontpts:
            z = top + dz
            pts.append((front_angle(s * x, z), z))
        return pts

    def band(P, s, w0, w1, off, mat):
        R = 0.12
        rows = []
        for i, (a, z) in enumerate(P):
            a0, z0 = P[max(0, i - 1)]
            a1, z1 = P[min(len(P) - 1, i + 1)]
            du, dz_ = (a1 - a0) * R * s, (z1 - z0)
            ln = math.hypot(du, dz_) or 1.0
            nu, nz = -dz_ / ln, du / ln          # away from the V opening: down / outwards
            if nz > 0:
                nu, nz = -nu, -nz
            fade = min(1.0, (len(P) - 1 - i) / 1.5)          # tuck the band end in
            row = []
            for w in (w0, (w0 + w1) / 2, w1):
                aa = a + (nu * w / R) * s
                zz = z + nz * w
                bulge = 0.0012 * math.sin(math.pi * (w - w0) / max(1e-6, w1 - w0))
                row.append(mb.v(tuple(surf(aa, zz, (off + bulge) * fade))))
            rows.append(row)
        for i in range(len(rows) - 1):
            for j in range(2):
                q = (rows[i][j], rows[i][j + 1], rows[i + 1][j + 1], rows[i + 1][j])
                mb.face(q if s > 0 else q[::-1], mat, None, True)

    if stand > 0:
        # low standing inner collar hugging the neck base (hides the neck/torso junction)
        mb.lathe([(neck_r + 0.004, top - 0.012), (neck_r + 0.006, top + stand * 0.6),
                  (neck_r + 0.003, top + stand)], inner, 32, center=(0, 0.014, 0), smooth=True,
                 scale_xy=(1.0, 0.95))
    for s in (-1, 1):                       # right lapel first (under), left lapel on top
        P = edge_pts(s)
        lf = lift + (0.0025 if s > 0 else 0.0)
        band(P, s, 0.0, inner_width, lf, inner)
        band(P, s, inner_width, inner_width + width, lf + 0.0008, outer)


def robe_collar(mb, lm, mat="SilkInner", outer="Silk", width=0.04):
    """Deprecated (flat bands that do not follow the torso): use :func:`cross_collar`."""
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


def neck_scarf(mb, lm, mat="Silk", inner="SilkInner", radius=0.068, height=0.055, folds=9):
    """Silk scarf wrapped around the neck base with soft folds, over a cream inner collar.
    Deprecated for portraits (at 192 px it reads as a lump on the neck): use :func:`cross_collar`
    and the torso's lamellar ``collar``."""
    nz = lm["neck"].z - 0.012
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
    """Cloak hanging behind the shoulders.  Not used by the portrait busts (in a 3/4 bust it
    shows as a colour band behind the head); keep for full figures / events."""
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


def pauldrons(mb, lm, shoulder_w=0.44, tiers=3, mat="Lamellar", trim="Bronze", size=1.0, slope=1.0):
    """Layered shoulder guards (披膊): overlapping ellipsoidal caps over each shoulder, each tier
    a little larger and lower so they read as stacked lamellar layers with a bronze edge."""
    top = lm["neck"].z - lm.get("torso_drop", 0.045)
    for sgn in (1, -1):
        c0 = Vector((sgn * (shoulder_w / 2 - 0.05), 0.02, top - 0.035 * slope - 0.03))
        for t in range(tiers):
            c = c0 + Vector((sgn * 0.010 * t, 0.0, -0.030 * t))
            R = Vector((0.080 + 0.006 * t, 0.105 + 0.006 * t, 0.060)) * size
            th0 = math.radians(0 if t == 0 else 30 + 6 * t)
            th1 = math.radians(78 + 3 * t)

            def fn(u, v, c=c, R=R, th0=th0, th1=th1):
                ph = math.radians(-80 + 160 * u)
                th = th0 + (th1 - th0) * v
                return (c.x + sgn * R.x * math.sin(th) * math.cos(ph),
                        c.y + R.y * math.sin(th) * math.sin(ph),
                        c.z + R.z * math.cos(th))
            mb.grid(fn, 22, 6, mat, lambda u, v: (u * 0.28, v * 0.07), smooth=True,
                    flip=(sgn < 0))
            mb.tube([fn(u, 1.0) for u in np.linspace(0, 1, 22)], 0.0035, trim, 6)


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
                  sideburns=True, top=None):
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
    # mouth zone (|x| < 3.2 cm): the beard starts under the lower lip so the lips and the mouth
    # line stay visible between it and the mustache; cheeks/sideburns from the nose-tip level
    zmax = np.where(np.abs(x) < 0.032, mz - 0.010, tip_z + 0.006 if sideburns else tip_z - 0.01)
    if top is not None:                          # e.g. a goatee from under the lower lip
        zmax = np.minimum(zmax, top)
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
    """Two mustache locks hanging from under the nostrils (either side of the philtrum), running
    out along the upper lip *above* the vermilion and drooping down beside the mouth corners - the
    lips and the mouth line stay visible between them."""
    rng = rng or random.Random(6)
    tip = lm["nose_tip"]
    mz = lm["mouth"].z
    sy = lm["surf_y"]
    strands = []
    for k in range(count):
        sgn = 1 if k % 2 else -1
        t0 = rng.random()
        rx = sgn * (0.0065 + 0.0145 * t0 * spread)
        rz = tip.z - 0.009 - 0.003 * t0 + rng.uniform(-0.0015, 0.0015)
        root = Vector((rx, sy(rx, rz) + 0.0004, rz))
        L = length * rng.uniform(0.75, 1.05) * (0.7 + 0.3 * t0)
        cx = sgn * (0.026 + 0.004 * t0) * spread                  # just outside the mouth corner
        p1x = sgn * (0.016 + 0.008 * t0) * spread
        p1z = max(mz + 0.0085, rz - 0.004)
        p1 = Vector((p1x, sy(p1x, p1z) - 0.0035, p1z))
        p2 = Vector((cx, sy(cx, mz + 0.002) - 0.003, mz + 0.002))
        ez = mz - 0.006 - L * 0.45 * droop
        ex = cx + sgn * 0.004 * t0
        end = Vector((ex, sy(ex, ez) - 0.002, ez))
        strands.append(_bezier(root, p1, p2, end, 9))
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
        bz = lm["brow_z"] - 0.003 + 0.003 * math.sin(math.pi * min(1.0, t * 1.15)) \
            + angle * 0.012 * t + rng.uniform(-1, 1) * 0.0028 * thickness * (1 - 0.5 * t)
        by = lm["surf_y"](bx, bz) + 0.0003
        root = Vector((bx, by, bz))
        d = Vector((sgn * 1.0, -0.15, 0.25 + angle * 0.4 - 0.5 * t)).normalized()
        L = length * rng.uniform(0.6, 1.0) * (1.15 - 0.4 * t)
        mid = root + d * L * 0.5 + Vector((0, -0.0012, 0))
        end = root + d * L + Vector((0, -0.0004, -0.001))
        strands.append([root, mid, end])
    return strands


def plume_strands(lm, count=900, length=0.07, rng=None, top=None, radius=0.034, lift_max=0.012):
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
        lift = rng.uniform(0.0, lift_max)
        sway = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), 0)) * 0.006
        pts = []
        for i in range(9):
            t = i / 8
            r = R * math.sin(min(1.0, t * 1.4) * math.pi / 2) ** 0.7
            zz = lift * math.sin(math.pi * min(1.0, t * 1.6)) - L * max(0.0, t - 0.2) ** 1.3
            pts.append(start + out * r + sway * t * t + Vector((0, 0, zz)))
        strands.append(pts)
    return strands


# ---------------------------------------------------------------------------------------------
# archetypes: one call builds a complete bust (the studio portrait families)
# ---------------------------------------------------------------------------------------------
#: Portrait archetypes.  ``head`` = :class:`HeadParams` overrides; colours are sRGB hex.  Every
#: officer portrait starts from one of these and varies seed / params / colours.
ARCHETYPES = {
    "warrior": dict(
        head=dict(jaw=1.15, chin=1.1, brow=1.12, cheekbone=1.2, nose_len=0.9, nose_width=0.88,
                  nose_bridge=1.05, socket=1.6, eye_size=0.95, lid_upper=0.31, lid_lower=0.26,
                  age=0.5),
        skin="#A26A4C", iris="#2E1C10", hair="#17120F", melanin=0.88, lash=1.3,
        headwear="helmet", beard="full", mustache="full",
        brows=dict(count=700, thickness=1.4, angle=0.5),
        body="armour", collar=("#8A2A20", "#D8CBB0"), robe=None, shoulder_w=0.44, chest_d=0.24,
        slope=1.3, neck_r=0.068),
    "scholar": dict(
        head=dict(jaw=0.97, chin=1.0, brow=0.95, cheekbone=1.05, nose_len=1.04, nose_width=0.84,
                  nose_bridge=1.08, eye_size=0.95, lid_upper=0.30, lid_lower=0.24, age=0.35,
                  eye_tilt=0.10),
        skin="#B07E5E", iris="#2A1A10", hair="#1A1512", melanin=0.9, lash=1.0,
        headwear="guan", beard="goatee", mustache="thin",
        brows=dict(count=420, thickness=0.9, angle=0.25),
        body="robe", collar=("#22303A", "#E6DCC6"), robe="#3A5260", shoulder_w=0.42,
        chest_d=0.22, slope=1.35, neck_r=0.056),
    "female": dict(
        head=dict(width=0.142, depth=0.182, height=0.218, jaw=0.80, chin=0.85, brow=0.45,
                  cheekbone=1.0, nose_len=0.80, nose_width=0.78, nose_bridge=0.82, eye_size=1.04,
                  lid_upper=0.36, lid_lower=0.26, lips=1.5, age=0.0, eye_tilt=0.12, socket=0.7,
                  eye_width=1.3, lower=0.9),
        skin="#C8977A", lip_color="#A23C34", lip=0.85, blush=0.6, pores=0.03, torso_drop=0.035, iris="#2A1A10", hair="#15110E", melanin=0.92, lash=1.35,
        headwear="bun", beard=None, mustache=None,
        brows=dict(count=300, thickness=0.55, angle=0.12),
        body="robe", collar=("#8A2A20", "#E8DCC6"), robe="#5A2A3A", shoulder_w=0.37,
        chest_d=0.20, slope=1.5, neck_r=0.046),
}


def archetype(kind, **over):
    """Deep copy of an archetype with top-level overrides (``head=dict(...)`` merges)."""
    import copy
    if kind not in ARCHETYPES:
        raise KeyError("unknown archetype %r (have %s)" % (kind, ", ".join(ARCHETYPES)))
    a = copy.deepcopy(ARCHETYPES[kind])
    for k, v in over.items():
        if k == "head":
            a["head"].update(v)
        else:
            a[k] = v
    return a


def portrait_materials(kind="warrior", **over):
    """Material slots every :func:`bust` part uses, coloured for the archetype."""
    from . import materials as M
    A = archetype(kind, **over)
    outer, inner = A["collar"]
    return {
        "Skin": M.skin("Skin", A["skin"], sss=0.18, roughness=0.55, blush=A.get("blush", 0.45),
                       vary=0.10, pores=A.get("pores", 0.08), pore_scale=90.0,
                       lip_color=A.get("lip_color", "#8A4436"), lip=A.get("lip", 0.7)),
        "Eye": M.eye("Eye", iris=A["iris"], sclera="#B4A894"),
        "Brow": M.principled("Brow", "#1C1714", 0.6),
        "Iron": M.iron("Iron", "#565C65", roughness=0.32),
        "Gold": M.gold_leaf("Gold", "#A88238", roughness=0.35),
        "Bronze": M.gold_leaf("Bronze", "#8A6A3A", roughness=0.35),
        "Lamellar": M.lamellar("Lamellar", "#5A606A", lacing="#4A1510", plate=(0.008, 0.016),
                               metallic=0.45, roughness=0.34, specular=0.5, bump=0.6,
                               lacing_width=0.03, band_every=7, band_color="#6E5A3E"),
        "Plume": M.hair_strands("Plume", "#8A1A10", roughness=0.5, random_color=0.2,
                                reflection=0.5),
        "Silk": M.cloth("Silk", outer, sheen=0.5, roughness=0.55),
        "SilkInner": M.cloth("SilkInner", inner, sheen=0.3, roughness=0.7),
        "Robe": M.cloth("Robe", A["robe"] or outer, sheen=0.45, roughness=0.65),
        "Hair": M.hair_mesh("Hair", A["hair"], strand_scale=260.0, direction="UV",
                            roughness=0.38),
        "Guan": M.principled("Guan", "#15120F", 0.35),
        "HairBlack": M.hair_strands("HairBlack", melanin=A["melanin"], redness=0.3,
                                    roughness=0.42, random_color=0.12, reflection=0.55),
    }


def bust(kind="warrior", rng=None, mats=None, **over):
    """Build a complete portrait bust for an archetype (see :data:`ARCHETYPES`).

    Returns ``{"lm", "head", "specs", "gear", "hair": [curves...], "face": [objects for the fine
    face Kuwahara], "top_z"}``.  Eyeballs are *not* created (they aim at the camera):
    call ``eyeballs(r["specs"], mats["Eye"], look_at=cam.location)`` once the camera exists.
    Face objects get ``pass_index = 1`` (``post.comp_painterly(detail_index=1)``).
    """
    A = archetype(kind, **over)
    rng = rng or random.Random(A.get("seed", 0))
    mats = mats or portrait_materials(kind, **over)
    p = HeadParams(**A["head"], seed=A.get("seed", 0))
    mb, lm = head(p)
    lm["torso_drop"] = A.get("torso_drop", 0.045)
    ears(mb, lm)
    specs = eyes(mb, lm, lash=A["lash"])
    neck(mb, lm, radius=A["neck_r"])
    head_obj = mb.build("Head", mats)
    import bpy
    mod = head_obj.modifiers.new("Subsurf", "SUBSURF")
    mod.levels = mod.render_levels = 1
    head_obj.pass_index = 1
    gb = geo.MeshBuilder()
    top_z = lm["rz_top"]
    helm = None
    hw = A["headwear"]
    if hw == "helmet":
        helm = helmet(gb, lm, plume=False, rng=rng, brim_z=lm["brow_z"] + 0.037, guard_len=0.112,
                      visor=0.07, guard_flare=0.30)
        top_z = helm["finial_z"]
    elif hw == "guan":
        hair_cap(gb, lm, "Hair", hairline=dict(front=0.07, temple=0.052))
        bun(gb, lm, "Hair", size=0.021, pin=None)
        guan(gb, lm)
        top_z = lm["rz_top"] + 0.06
    elif hw == "bun":
        hair_cap(gb, lm, "Hair", hairline=dict(front=0.062, temple=0.040, side=-0.004),
                 part=0.5, crown=0.018, thickness=0.006)
        bun(gb, lm, "Hair", size=0.03, pos=(0.0, 0.025, -0.006), pin="Gold", pin_len=0.11,
            tilt=0.01)
        top_z = lm["rz_top"] + 0.05
    sw, cd, sl = A["shoulder_w"], A["chest_d"], A["slope"]
    if A["body"] == "armour":
        torso(gb, lm, shoulder_w=sw, chest_d=cd, slope=sl, mat="Lamellar", top_mat="SilkInner",
              top_rings=1, collar=0.045, collar_mat="Lamellar", trim="Bronze",
              collar_r=A["neck_r"] + 0.012)
        cross_collar(gb, lm, shoulder_w=sw, chest_d=cd, slope=sl, stand=0.0, width=0.016,
                     neck_r=A["neck_r"], neck_x=A["neck_r"] + 0.004)
        pauldrons(gb, lm, shoulder_w=sw, tiers=3, slope=sl)
        mirror_plate(gb, lm, radius=0.028, z_offset=-0.205, y=-0.118)
    else:
        torso(gb, lm, shoulder_w=sw, chest_d=cd, slope=sl, mat="Robe", top_mat="SilkInner",
              top_rings=1, folds=0.025, segments=96)
        cross_collar(gb, lm, shoulder_w=sw, chest_d=cd, slope=sl, width=0.018, inner_width=0.008,
                     cross_z=-0.10, end_z=-0.135, neck_x=A["neck_r"] + 0.004, stand=0.016,
                     neck_r=A["neck_r"])
    gear = gb.build("Gear", mats)
    hair, face = [], [head_obj]
    hb = A["brows"]
    br = geo.hair_curves("Brows", brow_strands(lm, hb["count"], thickness=hb["thickness"],
                                               angle=hb["angle"], rng=rng),
                         mats["HairBlack"], 0.00035, 0.00012)
    hair.append(br)
    face.append(br)
    if A["beard"] == "full":
        hair.append(geo.hair_curves("Beard", beard_strands(
            lm, 7500, length=0.095, converge=0.75, bulge=1.0, rng=rng), mats["HairBlack"],
            0.00042, 0.0001))
    elif A["beard"] == "goatee":
        hair.append(geo.hair_curves("Beard", beard_strands(
            lm, 2200, length=0.12, converge=0.92, bulge=0.5, side_extent=0.3, sideburns=False,
            top=lm["mouth"].z - 0.012, rng=rng, clumps=40), mats["HairBlack"], 0.00036, 0.00008))
    if A["mustache"]:
        thin = A["mustache"] == "thin"
        mu = geo.hair_curves("Mustache", mustache_strands(
            lm, 500 if thin else 900, length=0.04 if thin else 0.05, droop=1.0 if thin else 1.2,
            spread=0.85 if thin else 1.0, rng=rng), mats["HairBlack"],
            0.00028 if thin else 0.0004, 0.0001)
        hair.append(mu)
        face.append(mu)
    if hw == "helmet":
        hair.append(geo.hair_curves("Plume", plume_strands(
            lm, 3200, length=0.055, rng=rng, radius=0.046, top=helm["finial_z"]), mats["Plume"],
            0.00045, 0.00012))
        top_z = helm["finial_z"] + 0.02
    for o in face:
        o.pass_index = 1
    return {"lm": lm, "head": head_obj, "specs": specs, "gear": gear, "hair": hair, "face": face,
            "top_z": top_z, "helmet": helm, "archetype": A}
