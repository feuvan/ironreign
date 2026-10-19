"""Illustrated Scenes: posable low-poly people, horses, weapons, banners, torches, lanterns.

A figure is a skeleton posed from a few joint angles (:data:`POSES`) dressed with lofted body
parts and clothing (robes with folds, wide sleeves, tunics, lamellar armour, capes, hats,
helmets) and props (spear, halberd, sword, bow, shield, torch, standard).  Everything is built
into a :class:`ironart.geometry.MeshBuilder` in *metres*, origin between the feet on the ground,
facing **-Y** (towards a camera looking +Y), so figures can be merged into a crowd mesh or built
as prototypes for :func:`ironart.scenes_flora.instance`.

Material slot names used (see :func:`materials`): Skin, Hair, Cloth0..ClothN (palette order),
Armor, ArmorDark, Metal, Bronze, Gold, Wood, Leather, Straw, HatBlack, Flame, Banner0..N, Rope.
"""

import math
import random

from mathutils import Matrix, Vector

TAU = math.tau

# ---------------------------------------------------------------------------------------------
# skeleton
# ---------------------------------------------------------------------------------------------
#: segment lengths (m) for a 1.72 m adult
BONES = dict(hip_h=0.93, pelvis_w=0.10, spine=0.50, neck=0.08, head_r=0.105, shoulder_w=0.185,
             upper_arm=0.30, forearm=0.27, hand=0.09, thigh=0.45, shin=0.45, foot=0.24)

#: pose = joint angles in degrees.  root: drop (m), bend (torso pitch forward), lean (sideways),
#: twist; arms L/R: (pitch forward from hanging, abduction out to the side, elbow bend, twist);
#: legs L/R: (pitch forward, abduction, knee bend); head (pitch down, yaw)
POSES = {
    "stand": dict(drop=0.0, bend=2, lean=0, twist=0, armL=(8, 10, 12), armR=(8, 10, 12),
                  legL=(0, 4, 2), legR=(0, 4, 2), head=(4, 0)),
    "stand_hands": dict(drop=0.0, bend=2, armL=(22, -4, 80, 44), armR=(22, -4, 80, 44),
                        legL=(0, 4, 2), legR=(0, 4, 2), head=(6, 0)),
    "walk": dict(drop=0.02, bend=6, armL=(-22, 8, 25), armR=(26, 8, 30), legL=(26, 2, 12),
                 legR=(-18, 2, 30), head=(5, 0)),
    "march_spear": dict(drop=0.02, bend=4, armL=(-15, 8, 25), armR=(30, 12, 80),
                        legL=(22, 2, 10), legR=(-16, 2, 28), head=(3, 0)),
    "charge": dict(drop=0.10, bend=24, armL=(70, 18, 60), armR=(55, 12, 35), legL=(48, 4, 40),
                   legR=(-34, 4, 20), head=(-12, 0)),
    "thrust": dict(drop=0.16, bend=18, twist=-14, armL=(80, 6, 15), armR=(65, 14, 70),
                   legL=(46, 8, 55), legR=(-30, 6, 8), head=(-10, 0)),
    "slash_high": dict(drop=0.08, bend=6, twist=22, armL=(150, 30, 40), armR=(160, 18, 50),
                       legL=(30, 10, 30), legR=(-24, 8, 10), head=(-8, 0)),
    "guard": dict(drop=0.12, bend=10, twist=-20, armL=(70, 20, 70), armR=(55, 18, 80),
                  legL=(30, 14, 40), legR=(-20, 14, 25), head=(-4, 0)),
    "sword_ready": dict(drop=0.10, bend=6, twist=-25, armL=(25, 18, 40), armR=(60, 10, 30),
                        legL=(28, 12, 34), legR=(-22, 12, 18), head=(-2, 0)),
    "kneel_bow": dict(drop=0.55, bend=58, armL=(80, 10, 30), armR=(80, 10, 30),
                      legL=(95, 6, 160), legR=(95, 6, 160), head=(15, 0), kneel=True),
    "kneel": dict(drop=0.50, bend=10, armL=(35, 8, 90), armR=(35, 8, 90), legL=(95, 6, 155),
                  legR=(95, 6, 155), head=(8, 0), kneel=True),
    "bow_stand": dict(drop=0.02, bend=40, armL=(75, 10, 95), armR=(75, 10, 95),
                      legL=(0, 4, 4), legR=(0, 4, 4), head=(18, 0)),
    "farm_bend": dict(drop=0.12, bend=72, armL=(95, 16, 30), armR=(80, 10, 45),
                      legL=(18, 10, 30), legR=(-6, 10, 20), head=(-30, 0)),
    "carry": dict(drop=0.02, bend=8, armL=(150, 20, 100), armR=(8, 12, 15), legL=(18, 2, 8),
                  legR=(-12, 2, 22), head=(4, 0)),
    "torch_high": dict(drop=0.06, bend=8, twist=10, armL=(20, 18, 40), armR=(150, 25, 30),
                       legL=(22, 8, 18), legR=(-14, 8, 16), head=(-6, 0)),
    "despair": dict(drop=0.50, bend=35, armL=(60, 10, 140), armR=(60, 10, 140),
                    legL=(95, 8, 150), legR=(95, 8, 150), head=(28, 0), kneel=True),
    "ride": dict(drop=0.0, bend=4, armL=(40, 12, 50), armR=(40, 12, 50), legL=(70, 38, 75),
                 legR=(70, 38, 75), head=(0, 0), ride=True),
    "ride_spear": dict(drop=0.0, bend=10, armL=(45, 12, 50), armR=(60, 14, 50), legL=(70, 38, 75),
                       legR=(70, 38, 75), head=(-4, 0), ride=True),
    "ride_charge": dict(drop=0.0, bend=26, armL=(50, 12, 45), armR=(95, 20, 20), legL=(70, 38, 75),
                        legR=(70, 38, 75), head=(-14, 0), ride=True),
    "draw_bow": dict(drop=0.04, bend=4, twist=-70, armL=(90, 0, 0), armR=(90, 20, 150),
                     legL=(16, 14, 8), legR=(-12, 14, 6), head=(0, -70)),
    "aim_up": dict(drop=0.03, bend=-10, twist=-60, armL=(130, 0, 0), armR=(125, 15, 150),
                   legL=(16, 14, 8), legR=(-12, 14, 6), head=(-25, -60)),
    "fall": dict(drop=0.35, bend=-30, lean=20, armL=(120, 40, 20), armR=(60, 60, 30),
                 legL=(40, 10, 50), legR=(10, 20, 20), head=(-20, 10)),
    "sit": dict(drop=0.46, bend=4, armL=(35, 10, 80), armR=(35, 10, 80), legL=(88, 8, 88),
                legR=(88, 8, 88), head=(2, 0)),
    "cheer": dict(drop=0.0, bend=-4, armL=(165, 25, 20), armR=(150, 30, 30), legL=(4, 6, 4),
                  legR=(0, 6, 4), head=(-20, 0)),
    "point": dict(drop=0.0, bend=0, armL=(10, 10, 15), armR=(100, 15, 5), legL=(10, 6, 4),
                  legR=(-6, 6, 8), head=(-5, 10)),
}


def _rot(axis, deg):
    return Matrix.Rotation(math.radians(deg), 3, axis)


class Skeleton:
    """Joint positions for a pose (local frame: facing -Y, figure's left = +X, up = +Z)."""

    def __init__(self, pose, height=1.72, rng=None, jitter=0.0):
        p = dict(POSES["stand"])
        p.update(POSES[pose] if isinstance(pose, str) else pose)
        rng = rng or random.Random(0)
        if jitter:
            for k in ("armL", "armR", "legL", "legR"):
                p[k] = tuple(v + rng.uniform(-jitter, jitter) for v in p[k])
            p["bend"] = p.get("bend", 0) + rng.uniform(-jitter, jitter) * 0.5
        self.p = p
        s = height / 1.72
        B = {k: v * s for k, v in BONES.items()}
        self.B = B
        self.s = s
        hip = Vector((0, 0, B["hip_h"] - p.get("drop", 0.0) * s))
        self.pelvis = hip
        bend, lean, twist = p.get("bend", 0), p.get("lean", 0), p.get("twist", 0)
        # torso frame: bend forward = rotate about X by -bend (towards -Y)
        R = _rot("Z", twist) @ _rot("Y", lean) @ _rot("X", bend)
        self.R = R
        up = R @ Vector((0, 0, 1))
        self.up = up
        self.chest = hip + up * B["spine"] * 0.62
        self.neck = hip + up * B["spine"]
        hp = p.get("head", (0, 0))
        Rh = R @ _rot("Z", hp[1]) @ _rot("X", hp[0])
        self.Rh = Rh
        self.head = self.neck + Rh @ Vector((0, 0, B["neck"] + B["head_r"] * 1.05))
        self.head_fwd = Rh @ Vector((0, -1, 0))
        # arms
        self.arm = {}
        for side, key in ((1, "armL"), (-1, "armR")):
            pitch, abd, elbow = p[key][:3]
            twist = p[key][3] if len(p[key]) > 3 else 0.0
            sh = self.neck + R @ Vector((side * B["shoulder_w"], 0, -0.05 * s))
            # upper arm: hanging down, pitched forward, abducted outwards
            d = Vector((0, 0, -1))
            d = _rot("X", -pitch) @ d
            d = _rot("Y", -side * abd) @ d
            d = (R @ d).normalized()
            el = sh + d * B["upper_arm"]
            # elbow bends the forearm forward/up relative to the upper arm plane
            fwd = (R @ Vector((0, -1, 0)))
            axis = d.cross(fwd)
            if axis.length < 1e-4:
                axis = R @ Vector((1, 0, 0))
            axis.normalize()
            # elbow flexion swings the forearm forward / up (towards the face)
            d2 = (Matrix.Rotation(math.radians(elbow), 3, axis) @ d).normalized()
            if twist:
                # rotate the forearm about the upper arm: + brings the hand in towards the midline
                d2 = (Matrix.Rotation(math.radians(side * twist), 3, d) @ d2).normalized()
            wr = el + d2 * B["forearm"]
            hand = wr + d2 * B["hand"] * 0.6
            self.arm[side] = dict(shoulder=sh, elbow=el, wrist=wr, hand=hand, dir=d2)
        # legs
        self.leg = {}
        for side, key in ((1, "legL"), (-1, "legR")):
            pitch, abd, knee = p[key][:3]
            hp_ = self.pelvis + Vector((side * B["pelvis_w"], 0, -0.03 * s))
            d = Vector((0, 0, -1))
            d = _rot("X", -pitch) @ d
            d = _rot("Y", -side * abd) @ d
            d.normalize()
            kn = hp_ + d * B["thigh"]
            axis = Vector((1, 0, 0))
            d2 = (Matrix.Rotation(math.radians(knee), 3, axis) @ d).normalized()
            an = kn + d2 * B["shin"]
            self.leg[side] = dict(hip=hp_, knee=kn, ankle=an)
        # ground the lowest point (feet / knees) at z = 0 unless riding
        if not p.get("ride"):
            low = min(min(l["ankle"].z - 0.06 * s for l in self.leg.values()),
                      min(l["knee"].z - 0.06 * s for l in self.leg.values()))
            dz = -low
            self.shift(Vector((0, 0, dz)))

    def shift(self, v):
        self.pelvis += v
        self.chest += v
        self.neck += v
        self.head += v
        for a in self.arm.values():
            for k in ("shoulder", "elbow", "wrist", "hand"):
                a[k] = a[k] + v
        for l in self.leg.values():
            for k in ("hip", "knee", "ankle"):
                l[k] = l[k] + v


# ---------------------------------------------------------------------------------------------
# mesh helpers
# ---------------------------------------------------------------------------------------------
def ring(mb, c, ex, ey, rx, ry, n=10, fn=None):
    ids = []
    for i in range(n):
        a = TAU * i / n
        k = fn(a) if fn else 1.0
        p = c + ex * (math.cos(a) * rx * k) + ey * (math.sin(a) * ry * k)
        ids.append(mb.v(tuple(p)))
    return ids


def fold_attrs(mb, ids, n_lines, phase, t, weight=1.0, a0=0.0):
    """Drapery-line (衣纹) attributes for one ring of ``ids`` (angle a_k = a0 + tau k / len):
    unit-circle position (fold_x, fold_y), lines per radian (fold_n), phase (fold_p), position
    down the garment (fold_t 0..1) and gate (fold_w).  The gongbi cloth material draws ink lines
    where |sin(fold_n * angle + fold_p)| is small (see scenes_gongbi.cloth)."""
    m = len(ids)
    for k, vid in enumerate(ids):
        a = a0 + TAU * k / m
        for nm, val in (("fold_x", math.cos(a)), ("fold_y", math.sin(a)), ("fold_n", n_lines),
                        ("fold_p", phase), ("fold_t", t), ("fold_w", weight)):
            mb.vattr.setdefault(nm, {})[vid] = val


def loft(mb, rings, mat, cap_bottom=False, cap_top=False, smooth=True):
    for i in range(len(rings) - 1):
        mb.quad_strip(rings[i], rings[i + 1], mat, True, smooth)
    if cap_bottom:
        mb.face(rings[0][::-1], mat, smooth=smooth)
    if cap_top:
        mb.face(rings[-1], mat, smooth=smooth)


def frame_from(d):
    d = Vector(d).normalized()
    ref = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
    ex = d.cross(ref).normalized()
    ey = d.cross(ex).normalized()
    return ex, ey


def limb(mb, pts, radii, mat, n=8, caps=True):
    """Tube through ``pts`` with per-point radii (smooth)."""
    rings = []
    for i, p in enumerate(pts):
        a = pts[max(0, i - 1)]
        b = pts[min(len(pts) - 1, i + 1)]
        ex, ey = frame_from(Vector(b) - Vector(a))
        rings.append(ring(mb, Vector(p), ex, ey, radii[i], radii[i], n))
    loft(mb, rings, mat, caps, caps)


def ellipsoid(mb, c, r, mat, seg=10, rings_=7, rot=None):
    s = mb.n
    mb.sphere((0, 0, 0), 1.0, mat, seg, rings_)
    m = Matrix.Diagonal((r[0], r[1], r[2], 1.0))
    if rot is not None:
        m = rot.to_4x4() @ m
    mb.transform(s, Matrix.Translation(Vector(c)) @ m)
    return s


# ---------------------------------------------------------------------------------------------
# figure
# ---------------------------------------------------------------------------------------------
OUTFITS = ("robe", "official", "soldier", "armored", "general", "peasant", "farmer", "wanderer",
           "monk", "bandit", "lady", "noble", "disciple")


def figure(mb, rng, pose="stand", outfit="soldier", cloth=0, cloth2=1, height=1.72, weapon=None,
           hat=None, cape=False, cape_wind=(0.6, 0.0), jitter=4.0, sleeves=None, skirt=None,
           banner=None, shield=False, hair_long=False, belt=True):
    """Build one dressed, posed figure into ``mb`` (origin between the feet, facing -Y).

    cloth / cloth2   indices of the main / secondary cloth materials ("Cloth<i>")
    weapon           None | 'spear' | 'halberd' | 'sword' | 'sword_back' | 'bow' | 'torch' |
                     'staff' | 'fan' | 'sickle' | 'lantern' | 'standard'
    hat              None | 'helmet' | 'helmet_plume' | 'straw' | 'official' | 'topknot' |
                     'hood' | 'band' | 'guan' | 'crown'
    banner           Banner material index carried on a back pole (or the standard's cloth)
    Returns the :class:`Skeleton` (hand positions for attaching extra props).
    """
    sk = Skeleton(pose, height, rng, jitter)
    s = sk.s
    C = "Cloth%d" % cloth
    C2 = "Cloth%d" % cloth2
    R = sk.R
    ex, ey = R @ Vector((1, 0, 0)), R @ Vector((0, 1, 0))
    up = sk.up
    long_robe = outfit in ("robe", "official", "monk", "lady", "noble", "wanderer", "disciple")
    armored = outfit in ("armored", "general")
    # ---- legs (trousers / leg wraps) -------------------------------------------------------
    for side in (1, -1):
        L = sk.leg[side]
        trouser = C2 if outfit in ("soldier", "armored", "general", "bandit", "peasant", "farmer") else C
        limb(mb, [L["hip"], (L["hip"] + L["knee"]) * 0.5, L["knee"], (L["knee"] + L["ankle"]) * 0.5,
                  L["ankle"]], [0.085 * s, 0.075 * s, 0.058 * s, 0.05 * s, 0.045 * s],
             trouser, n=8, caps=False)
        # feet / boots
        fwd = Vector((0, -1, 0))
        if sk.p.get("kneel"):
            fwd = (L["ankle"] - L["knee"]).normalized()
        toe = L["ankle"] + fwd * 0.17 * s + Vector((0, 0, -0.04 * s))
        heel = L["ankle"] - fwd * 0.05 * s + Vector((0, 0, -0.04 * s))
        limb(mb, [heel, L["ankle"] + Vector((0, 0, -0.02 * s)), toe], [0.045 * s, 0.05 * s, 0.035 * s],
             "Leather" if outfit not in ("peasant", "farmer") else "Straw", n=7)
    # ---- torso ------------------------------------------------------------------------------
    pel = sk.pelvis
    torso_pts = [pel - up * 0.04 * s, pel + up * 0.12 * s, pel + up * 0.28 * s, sk.chest,
                 sk.neck - up * 0.06 * s, sk.neck]
    rx = [0.165, 0.15, 0.155, 0.185, 0.19, 0.07]
    ry = [0.115, 0.10, 0.11, 0.13, 0.11, 0.065]
    bulk = 1.12 if armored else (1.08 if long_robe else 1.0)
    rings = [ring(mb, p, ex, ey, rx[i] * s * bulk, ry[i] * s * bulk, 12) for i, p in enumerate(torso_pts)]
    loft(mb, rings, "Armor" if armored else C, cap_top=False)
    # crossed collar (jiaoling) - a contrasting V on the chest
    if not armored:
        a = sk.neck + up * 0.0 - ey * 0.06 * s
        mb.tube([tuple(sk.neck + ex * 0.07 * s - ey * 0.02 * s), tuple(sk.chest - ey * 0.13 * s * bulk + ex * 0.02 * s),
                 tuple(pel + up * 0.25 * s - ey * 0.12 * s - ex * 0.05 * s)], 0.022 * s, C2, 5)
    # ---- skirts / robes ----------------------------------------------------------------------
    waist = pel + up * 0.06 * s
    if long_robe or skirt == "long":
        _robe(mb, sk, rng, waist, C, C2, bulk, length=1.0, train=outfit in ("noble", "lady", "official"))
    elif outfit in ("soldier", "armored", "general", "bandit", "peasant", "farmer") or skirt == "short":
        if armored:
            _robe(mb, sk, rng, waist, C, C2, bulk, length=0.62, ease=(0.03, 0.08), folds=0.05)
            _robe(mb, sk, rng, waist + up * 0.01 * s, "Armor", C2, bulk * 1.05, length=0.42,
                  ease=(0.035, 0.07), folds=0.0, hem_trim=None, segs=14)
        else:
            _robe(mb, sk, rng, waist, C, C2, bulk, length=0.55, ease=(0.03, 0.09), folds=0.06)
    if belt:
        bc = waist + up * 0.04 * s
        rr = [ring(mb, bc - up * 0.028 * s, ex, ey, 0.175 * s * bulk, 0.13 * s * bulk, 12),
              ring(mb, bc + up * 0.028 * s, ex, ey, 0.175 * s * bulk, 0.13 * s * bulk, 12)]
        loft(mb, rr, "Leather" if outfit in ("soldier", "armored", "general", "bandit") else C2)
        if outfit in ("robe", "official", "noble", "lady", "wanderer", "disciple"):
            # sash ends hanging at the front
            for k in (-1, 1):
                p0 = bc - ey * 0.13 * s * bulk + ex * 0.03 * k * s
                mb.tube([tuple(p0), tuple(p0 - up * 0.2 * s - ey * 0.02 * s + ex * 0.01 * k),
                         tuple(p0 - up * 0.42 * s - ey * 0.01 * s + ex * 0.02 * k)], 0.018 * s, C2, 4,
                        radius_fn=lambda t: 1.0 - 0.2 * t)
    # ---- arms (sleeves) ---------------------------------------------------------------------
    wide = sleeves if sleeves is not None else outfit in ("robe", "official", "lady", "noble", "monk", "disciple")
    for side in (1, -1):
        A = sk.arm[side]
        sh, el, wr, hd = A["shoulder"], A["elbow"], A["wrist"], A["hand"]
        if wide:
            _sleeve(mb, A, C, C2, s, width=0.13 if outfit in ("noble", "lady", "official") else 0.11)
        else:
            limb(mb, [sh, (sh + el) * 0.5, el, (el + wr) * 0.5, wr],
                 [0.07 * s, 0.064 * s, 0.054 * s, 0.047 * s, 0.042 * s],
                 "Armor" if armored else C, n=8, caps=False)
            if armored:
                limb(mb, [el + (wr - el) * 0.3, wr], [0.052 * s, 0.047 * s], "ArmorDark", n=8, caps=False)
        ellipsoid(mb, hd, (0.04 * s, 0.03 * s, 0.05 * s), "Skin", 8, 5)
        if armored:
            pd = sh + Vector((side * 0.035 * s, 0, 0.015 * s))
            s0 = mb.n
            mb.lathe([(0.0, 0.075 * s), (0.08 * s, 0.05 * s), (0.12 * s, -0.01 * s), (0.13 * s, -0.08 * s)],
                     "Armor", 12)
            ax = (sh - sk.neck).normalized()
            q = (ax * 0.6 + sk.up * 0.4).normalized().to_track_quat("Z", "Y")
            mb.transform(s0, Matrix.Translation(pd) @ q.to_matrix().to_4x4())
    # ---- neck + head ------------------------------------------------------------------------
    limb(mb, [sk.neck - up * 0.02 * s, sk.head - sk.up * sk.B["head_r"] * 0.7],
         [0.05 * s, 0.045 * s], "Skin", n=8, caps=False)
    hr = sk.B["head_r"]
    ellipsoid(mb, sk.head, (hr * 0.86, hr * 0.95, hr * 1.12), "Skin", 12, 9, rot=sk.Rh)
    # a small nose so a head seen in profile reads as a face, not a blank oval
    hf = sk.Rh @ Vector((0, -1, 0))
    hu = sk.Rh @ Vector((0, 0, 1))
    ellipsoid(mb, sk.head + hf * hr * 0.93 - hu * hr * 0.14, (hr * 0.13, hr * 0.22, hr * 0.26), "Skin", 8, 6, rot=sk.Rh)
    # hair / headwear
    Rh = sk.Rh
    hup = Rh @ Vector((0, 0, 1))
    hfwd = Rh @ Vector((0, -1, 0))
    crown = sk.head + hup * hr * 0.25 - hfwd * hr * 0.05
    if hat not in ("helmet", "helmet_plume", "hood"):
        # hair cap (top and back of the head): kept above the temples so its outline frames the
        # forehead instead of running down the cheeks
        ellipsoid(mb, sk.head + hup * hr * 0.3 - hfwd * hr * 0.16,
                  (hr * 0.9, hr * 0.9, hr * 0.92), "Hair", 12, 8, rot=Rh)
        # hair down the back of the head to the nape (reads in profile and from behind)
        ellipsoid(mb, sk.head - hfwd * hr * 0.32 - hup * hr * 0.12,
                  (hr * 0.84, hr * 0.7, hr * 0.86), "Hair", 12, 8, rot=Rh)
    if hat in (None, "topknot", "band", "guan", "crown"):
        ellipsoid(mb, sk.head + hup * hr * 1.08 - hfwd * hr * 0.1, (hr * 0.38, hr * 0.38, hr * 0.42),
                  "Hair", 8, 6, rot=Rh)
    if hat == "band":
        rr = [ring(mb, sk.head + hup * hr * 0.35, Rh @ Vector((1, 0, 0)), Rh @ Vector((0, 1, 0)), hr * 0.97, hr * 1.04, 12),
              ring(mb, sk.head + hup * hr * 0.55, Rh @ Vector((1, 0, 0)), Rh @ Vector((0, 1, 0)), hr * 0.93, hr * 1.0, 12)]
        loft(mb, rr, C2)
    elif hat == "guan":
        c = sk.head + hup * hr * 1.15 - hfwd * hr * 0.1
        ellipsoid(mb, c, (hr * 0.25, hr * 0.5, hr * 0.32), "HatBlack", 8, 6, rot=Rh)
        mb.cylinder(tuple(c - (Rh @ Vector((hr * 0.7, 0, 0)))), tuple(c + (Rh @ Vector((hr * 0.7, 0, 0)))),
                    0.006 * s, mat="Gold", segments=5)
    elif hat == "crown":
        c = sk.head + hup * hr * 1.05
        ellipsoid(mb, c, (hr * 0.55, hr * 0.6, hr * 0.35), "HatBlack", 10, 6, rot=Rh)
        # mian board
        mb.box(tuple(c + hup * hr * 0.4), (hr * 1.4, hr * 2.4, 0.012 * s), "HatBlack")
    elif hat == "official":
        c = sk.head + hup * hr * 0.55
        rr = [ring(mb, c - hup * hr * 0.2, Rh @ Vector((1, 0, 0)), Rh @ Vector((0, 1, 0)), hr * 1.0, hr * 1.06, 12),
              ring(mb, c + hup * hr * 0.55, Rh @ Vector((1, 0, 0)), Rh @ Vector((0, 1, 0)), hr * 0.85, hr * 0.9, 12)]
        loft(mb, rr, "HatBlack", cap_top=True)
        ellipsoid(mb, c + hup * hr * 0.75 + hfwd * -hr * 0.3, (hr * 0.5, hr * 0.45, hr * 0.45), "HatBlack", 8, 6, rot=Rh)
        # horizontal wings (wushamao)
        for sd in (1, -1):
            w0 = c + hup * hr * 0.5 - hfwd * hr * 0.75
            w1 = w0 + (Rh @ Vector((sd * hr * 3.0, 0, 0)))
            mb.box(tuple((w0 + w1) * 0.5), (abs((w1 - w0).x) + 0.01, 0.012 * s, hr * 0.38), "HatBlack")
    elif hat == "straw":
        c = sk.head + hup * hr * 0.55
        prof = [(hr * 3.3, -hr * 0.05), (hr * 2.4, hr * 0.25), (hr * 1.2, hr * 0.62), (hr * 0.2, hr * 0.95), (0.0, hr * 1.0)]
        s0 = mb.n
        mb.lathe(prof, "Straw", 18, smooth=True)
        mb.transform(s0, Matrix.Translation(c) @ Rh.to_4x4())
    elif hat in ("helmet", "helmet_plume"):
        c = sk.head + hup * hr * 0.25
        s0 = mb.n
        mb.lathe([(hr * 1.12, -hr * 0.55), (hr * 1.14, 0.0), (hr * 1.08, hr * 0.45), (hr * 0.8, hr * 0.9),
                  (hr * 0.35, hr * 1.12), (0.0, hr * 1.18)], "Metal", 14)
        mb.transform(s0, Matrix.Translation(c) @ Rh.to_4x4())
        # brim + neck guard flare
        s0 = mb.n
        mb.lathe([(hr * 1.16, -hr * 0.1), (hr * 1.38, -hr * 0.35), (hr * 1.4, -hr * 0.42)], "ArmorDark", 14,
                 angle_range=(math.pi * 0.15, math.pi * 0.85 + math.pi))
        mb.transform(s0, Matrix.Translation(c - hup * hr * 0.4) @ Rh.to_4x4() @ Matrix.Rotation(math.pi / 2, 4, "Z"))
        mb.cylinder(tuple(c + hup * hr * 1.15), tuple(c + hup * hr * 1.6), 0.008 * s, 0.002, "Gold", 5)
        if hat == "helmet_plume":
            tip = c + hup * hr * 1.55
            for k in range(7):
                a = TAU * k / 7
                end = tip + Vector((math.cos(a) * 0.06 * s, math.sin(a) * 0.06 * s + 0.08 * s, -0.12 * s))
                mb.tube([tuple(tip), tuple(tip + (end - tip) * 0.5 + Vector((0, 0, 0.03 * s))), tuple(end)],
                        0.012 * s, "Plume", 4, radius_fn=lambda t: 1.0 - 0.7 * t)
    elif hat == "hood":
        c = sk.head + hup * hr * 0.15 + hfwd * -hr * 0.12
        ellipsoid(mb, c, (hr * 1.08, hr * 1.12, hr * 1.14), C2, 12, 8, rot=Rh)
    if hair_long:
        b0 = sk.head - hfwd * hr * 0.7
        b1 = sk.neck - (R @ Vector((0, -1, 0))) * -0.0 + Vector((0, 0.10 * s, -0.12 * s))
        limb(mb, [b0, (b0 + b1) * 0.5 + Vector((0, 0.03 * s, 0)), b1], [hr * 0.6, hr * 0.45, hr * 0.15], "Hair", 8)
    # ---- cape -------------------------------------------------------------------------------
    if cape:
        wx, wy = cape_wind
        shL, shR = sk.arm[1]["shoulder"], sk.arm[-1]["shoulder"]
        top_l = shL + Vector((0.02, 0.06 * s, 0.02))
        top_r = shR + Vector((-0.02, 0.06 * s, 0.02))
        Lc = 1.1 * s
        nu, nv = 8, 8
        ph = rng.uniform(0, TAU)

        def cp(u, v):
            base = top_r + (top_l - top_r) * u
            w = 1.0 + 0.6 * v
            x = (u - 0.5) * (w - 1.0) * 0.35
            p = base + Vector((x, 0.0, 0.0)) - Vector((0, 0, 1)) * Lc * v
            # wind billow: push back (+y) and sideways, waves
            p += Vector((wx * v * v * 0.28, (0.1 + wy * 0.5) * v + 0.12 * v * v, 0.05 * v * v * abs(wx)))
            p += Vector((0.02 * math.sin(u * 9 + ph) * v, 0.06 * math.sin(u * 8 + ph + v * 3) * v,
                         0.03 * math.sin(u * 5 + v * 4 + ph) * v))
            return tuple(p)
        g = mb.grid(cp, nu, nv, C2, smooth=True)
        g2 = mb.grid(cp, nu, nv, C2, smooth=True, flip=True)
    # ---- weapons / props --------------------------------------------------------------------
    hand = sk.arm[-1]["hand"]
    handL = sk.arm[1]["hand"]
    adir = sk.arm[-1]["dir"]
    if weapon in ("spear", "halberd", "staff", "standard"):
        fwd_h = _rot("Z", sk.p.get("twist", 0)) @ Vector((0, -1, 0))
        if pose in ("charge", "thrust", "ride_charge", "ride_spear", "guard"):
            d = (fwd_h + Vector((0, 0, -0.06 if pose != "ride_spear" else 0.25))).normalized()
        elif pose in ("march_spear", "stand", "walk", "kneel", "stand_hands", "ride") or weapon == "standard":
            d = Vector((0.04, -0.1, 1.0)).normalized()
        else:
            d = (adir + Vector((0, 0, 0.6))).normalized()
        Lp = (3.2 if weapon != "staff" else 1.9) * s
        if weapon == "standard":
            Lp = 3.6 * s
        back = 0.35 * Lp if weapon != "staff" else 0.5 * Lp
        p0 = hand - d * back
        p1 = hand + d * (Lp - back)
        if pose in ("march_spear", "stand", "walk", "kneel") or weapon == "standard":
            p0.z = max(p0.z, 0.02)
        mb.cylinder(tuple(p0), tuple(p1), 0.016 * s, 0.014 * s, "Wood", 6)
        if weapon in ("spear", "halberd"):
            ex2, ey2 = frame_from(d)
            tip = p1 + d * 0.32 * s
            blade = [p1, p1 + d * 0.08 * s + ex2 * 0.035 * s, tip, p1 + d * 0.08 * s - ex2 * 0.035 * s]
            ids = [mb.v(tuple(q)) for q in blade]
            mb.face(ids, "Metal")
            mb.face(ids[::-1], "Metal")
            mb.cylinder(tuple(p1 - d * 0.02), tuple(p1 + d * 0.05 * s), 0.02 * s, 0.018 * s, "Plume" if weapon == "spear" else "Metal", 6)
            if weapon == "halberd":
                hb = [p1 - d * 0.05 * s, p1 - d * 0.05 * s + ex2 * 0.22 * s + d * 0.08 * s,
                      p1 + d * 0.12 * s + ex2 * 0.12 * s, p1 + d * 0.04 * s]
                ids = [mb.v(tuple(q)) for q in hb]
                mb.face(ids, "Metal")
                mb.face(ids[::-1], "Metal")
        if weapon == "standard" or banner is not None:
            pass
        if weapon == "standard":
            _flag(mb, p1 - d * 0.05, d, banner if banner is not None else 0, s, rng)
    elif weapon in ("sword", "sword_high"):
        d = adir
        if pose in ("sword_ready", "guard", "stand", "walk"):
            d = (adir + Vector((0, -0.2, 0.9))).normalized()
        bl = 0.85 * s
        _sword(mb, hand, d, bl, s)
    elif weapon == "sword_back":
        b0 = sk.chest + (R @ Vector((0.12 * s, 0.14 * s, -0.25 * s)))
        b1 = sk.chest + (R @ Vector((-0.2 * s, 0.14 * s, 0.38 * s)))
        mb.cylinder(tuple(b0), tuple(b1), 0.02 * s, 0.02 * s, "Wood", 6)
        mb.cylinder(tuple(b1), tuple(b1 + (b1 - b0).normalized() * 0.2 * s), 0.015 * s, 0.015 * s, "Leather", 6)
    elif weapon == "bow":
        c = handL
        d = sk.arm[1]["dir"]
        upb = (R @ Vector((0, 0, 1)))
        side = d.cross(upb).normalized()
        pts = []
        for k in range(9):
            t = (k / 8) * 2 - 1
            pts.append(tuple(c + upb * t * 0.65 * s + d * (0.18 * s * (1 - t * t)) * -1 + d * 0.15 * s))
        mb.tube(pts, 0.014 * s, "Wood", 5)
        mb.cylinder(pts[0], tuple(hand), 0.003, 0.003, "Rope", 3)
        mb.cylinder(tuple(hand), pts[-1], 0.003, 0.003, "Rope", 3)
    elif weapon == "torch":
        d = (adir + Vector((0, 0, 1.2))).normalized()
        t0 = hand - d * 0.2 * s
        t1 = hand + d * 0.45 * s
        mb.cylinder(tuple(t0), tuple(t1), 0.02 * s, 0.025 * s, "Wood", 6)
        fl = t1 + Vector((0, 0, 0.13 * s))
        ellipsoid(mb, fl, (0.07 * s, 0.07 * s, 0.16 * s), "Flame", 8, 6)
        ellipsoid(mb, fl + Vector((0.02, 0.0, 0.12 * s)), (0.04 * s, 0.04 * s, 0.11 * s), "Flame", 6, 5)
    elif weapon == "lantern":
        c = hand + Vector((0, 0, -0.25 * s))
        mb.cylinder(tuple(hand), tuple(c + Vector((0, 0, 0.12 * s))), 0.004, 0.004, "Rope", 3)
        ellipsoid(mb, c, (0.11 * s, 0.11 * s, 0.13 * s), "LanternPaper", 10, 7)
    elif weapon == "sickle":
        d = adir
        p1 = hand + d * 0.3 * s
        mb.cylinder(tuple(hand - d * 0.05), tuple(p1), 0.012 * s, 0.012 * s, "Wood", 5)
        ex2, ey2 = frame_from(d)
        pts = [tuple(p1 + (ex2 * math.sin(t * 2.4) + d * math.cos(t * 2.4) * -0.3) * 0.22 * s * (0.3 + 0.7 * t)) for t in [i / 6 for i in range(7)]]
        mb.tube(pts, 0.01 * s, "Metal", 4)
    elif weapon == "fan":
        c = hand + Vector((0, -0.05, 0.08)) * s
        mb.sphere(tuple(c), 0.13 * s, "Feather", 10, 4, scale=(1.0, 0.15, 1.0))
    if shield:
        A = sk.arm[1]
        c = A["wrist"] + (R @ Vector((0.06 * s, -0.08 * s, 0.0)))
        rot = R @ _rot("X", 90)
        s0 = mb.n
        mb.lathe([(0.0, 0.04 * s), (0.25 * s, 0.02 * s), (0.32 * s, 0.0), (0.32 * s, -0.015 * s), (0.0, -0.015 * s)],
                 "ShieldFace", 14)
        mb.transform(s0, Matrix.Translation(c) @ rot.to_4x4() @ Matrix.Diagonal((1.0, 1.25, 1.0, 1.0)))
        mb.sphere(tuple(c - (R @ Vector((0, 0.045 * s, 0)))), 0.045 * s, "Bronze", 8, 5)
    if banner is not None and weapon != "standard":
        # back-pole banner (standard bearer)
        b0 = sk.pelvis + (R @ Vector((0.0, 0.16 * s, 0.1 * s)))
        b1 = b0 + Vector((0, 0.05, 2.6 * s))
        mb.cylinder(tuple(b0), tuple(b1), 0.014 * s, 0.012 * s, "Wood", 6)
        _flag(mb, b1, Vector((0, 0, 1)), banner, s, rng)
    return sk


def _sword(mb, hand, d, bl, s):
    ex2, ey2 = frame_from(d)
    p1 = hand + d * 0.1 * s
    tip = hand + d * (bl + 0.1 * s)
    w = 0.028 * s
    pts = [p1 + ex2 * w, tip, p1 - ex2 * w]
    ids = [mb.v(tuple(q)) for q in pts]
    mb.face(ids, "Blade")
    mb.face(ids[::-1], "Blade")
    mb.cylinder(tuple(hand - d * 0.12 * s), tuple(p1), 0.016 * s, 0.016 * s, "Leather", 5)
    mb.box(tuple(p1 - Vector((0, 0, 0.0))), (0.1 * s, 0.03 * s, 0.025 * s), "Gold")


def _flag(mb, top, pole_dir, banner, s, rng, w=0.75, h=1.25, wind=(0.0, 1.0)):
    """Rectangular war banner hanging from a crossbar at ``top`` (waving)."""
    ph = rng.uniform(0, TAU)
    W, H = w * s, h * s
    side = Vector((1, 0, 0))
    top = Vector(top)
    mb.cylinder(tuple(top - side * 0.04), tuple(top + side * W * 0.9), 0.01 * s, 0.01 * s, "Wood", 5)

    def fp(u, v):
        x = u * W
        p = top + side * x * 0.92 - Vector((0, 0, v * H))
        p += Vector((0, 0.12 * math.sin(u * 5.5 + ph + v * 1.3) * (0.3 + u) * s, 0))
        p += Vector((0, 0.06 * s * v * u, -0.05 * s * u * u))
        return tuple(p)
    mat = "Banner%d" % banner
    mb.grid(fp, 8, 6, mat, smooth=True)
    mb.grid(fp, 8, 6, mat, smooth=True, flip=True)
    # tassels / border strip
    mb.grid(lambda u, v: tuple(Vector(fp(u, 1.0)) + Vector((0, 0, -0.06 * s * v))), 8, 1, "Gold", smooth=True)


def _leg_point(L, t):
    """Point at fraction t (0 hip .. 1 ankle) along a leg polyline."""
    if t <= 0.5:
        return L["hip"] + (L["knee"] - L["hip"]) * (t / 0.5)
    return L["knee"] + (L["ankle"] - L["knee"]) * ((t - 0.5) / 0.5)


def _robe(mb, sk, rng, waist, mat, trim, bulk=1.0, length=1.0, ease=(0.035, 0.13), folds=0.08,
          train=False, hem_trim=True, segs=20, rings_n=7):
    """Robe / tunic / armour skirt draped over the posed legs: every ring is the hull of the two
    leg cross-sections at that fraction of the leg plus an ease that grows to the hem; constant
    fold phases make vertical grooves; the hem undulates; kneeling robes pool on the ground."""
    s = sk.s
    kneel = sk.p.get("kneel", False)
    ride = sk.p.get("ride", False)
    ph = [rng.uniform(0, TAU) for _ in range(3)]
    nf = rng.randint(7, 10)
    Ls, Rs = sk.leg[1], sk.leg[-1]
    rings = []
    up = Vector((0, 0, 1))
    wr_x, wr_y = 0.165 * s * bulk, 0.125 * s * bulk
    ex0 = (sk.R @ Vector((1, 0, 0)))
    ex0.z = 0
    ex0.normalize()
    rings.append(ring(mb, waist, ex0, up.cross(ex0) * -1.0, wr_x, wr_y, segs))
    fold_attrs(mb, rings[-1], nf * 0.5, ph[0], 0.0)
    for i in range(1, rings_n + 1):
        t = i / rings_n
        tl = t * length
        pl, pr = _leg_point(Ls, tl), _leg_point(Rs, tl)
        if kneel:
            # kneeling: the cloth falls from the thighs to the floor and pools around the heels
            c = (pl + pr) * 0.5
            back = (Ls["ankle"] + Rs["ankle"]) * 0.5
            c = c * (1 - t) + ((Ls["knee"] + Rs["knee"]) * 0.25 + back * 0.5) * t
            c.z = max(0.015 * s, waist.z * (1 - t) ** 1.4 + 0.015 * s)
        else:
            c = (pl + pr) * 0.5
            c = waist * (1 - min(1.0, t * 3)) + c * min(1.0, t * 3) if t < 0.34 else c
        u = pl - pr
        u.z = 0
        half = u.length * 0.5
        if u.length < 1e-4:
            u = ex0.copy()
        u.normalize()
        v = up.cross(u)
        e = ease[0] + (ease[1] - ease[0]) * t ** 1.5
        rl = 0.08 * s * (1 - 0.4 * tl)
        a = max(wr_x * (1 - t), half + rl + e * s) if not kneel else half + 0.16 * s + 0.12 * s * t
        b = (rl * 1.25 + e * s * 0.9) if not kneel else 0.18 * s + 0.22 * s * t
        b = max(b, wr_y * (1 - t) * 0.9)
        if ride:
            b *= 1.3
        amp = folds * t ** 0.8

        def fn(ang, amp=amp, t=t):
            f = 1.0 + amp * (0.6 * abs(math.sin(nf * 0.5 * ang + ph[0])) - 0.3
                             + 0.35 * math.sin(nf * ang * 1.7 + ph[1]))
            return f
        ids = ring(mb, c, u, v, a, b, segs, fn)
        fold_attrs(mb, ids, nf * 0.5, ph[0], t)
        if i == rings_n:
            # hem: undulate, keep above the ground, train behind for court robes
            for k, vid in enumerate(ids):
                ang = TAU * k / segs
                p = mb.verts[vid]
                p.z += 0.02 * s * math.sin(3 * ang + ph[2]) * (1 if not kneel else 0.3)
                if train and length >= 1.0 and not kneel:
                    back = max(0.0, math.sin(ang)) if v.y > 0 else max(0.0, -math.sin(ang))
                    p += Vector((0, 0.18 * s * back ** 2, 0))
                p.z = max(p.z, 0.008 * s)
                mb.verts[vid] = p
        rings.append(ids)
    loft(mb, rings, mat, cap_bottom=kneel)
    if hem_trim and trim:
        # contrasting hem band
        last = rings[-1]
        band = []
        for vid in last:
            p = mb.verts[vid]
            band.append(mb.v(tuple(p + Vector((0, 0, 0.05 * s * length)))))
        # band ring slightly proud
        ctr = sum((mb.verts[v_] for v_ in last), Vector()) / len(last)
        for k, vid in enumerate(band):
            p = mb.verts[vid]
            d = p - ctr
            d.z = 0
            if d.length > 0:
                mb.verts[vid] = p + d.normalized() * 0.004 * s
        mb.quad_strip(last, band, trim, True, True)


def _sleeve(mb, A, mat, lining, s, width=0.12, droop=1.25, n=12):
    """Wide hanging hanfu sleeve (袂): a tube along the arm whose underside sags into a pouch
    that is deepest under the forearm and gathers again to a modest cuff at the wrist, so the
    opening never reads as a trumpet; the cuff is lined and closed by a dark disc."""
    sh, el, wr = A["shoulder"], A["elbow"], A["wrist"]
    end = wr + (wr - el).normalized() * 0.05 * s
    poly = [sh, el, wr, end]
    seg = [(poly[i + 1] - poly[i]).length for i in range(3)]
    tot = sum(seg)

    def at(t):
        d = t * tot
        for i in range(3):
            if d <= seg[i] or i == 2:
                return poly[i] + (poly[i + 1] - poly[i]) * min(1.0, d / max(seg[i], 1e-6))
            d -= seg[i]

    def sm(e0, e1, x):
        u = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
        return u * u * (3 - 2 * u)
    ts = [0.0, 0.18, 0.36, 0.5, 0.62, 0.74, 0.84, 0.92, 1.0]
    pts = [at(t) for t in ts]
    down = Vector((0, 0, -1))
    rings = []
    for i, (t, p) in enumerate(zip(ts, pts)):
        a = pts[max(0, i - 1)]
        b = pts[min(len(pts) - 1, i + 1)]
        d = (b - a).normalized()
        ex = d.cross(down)
        if ex.length < 1e-3:
            ex = d.cross(Vector((0, 1, 0)))
        ex.normalize()
        ey = d.cross(ex).normalized()
        if ey.dot(down) < 0:
            ey = -ey
        r = (0.072 + (width - 0.072) * sm(0.0, 0.7, t) - (width - 0.075) * 0.85 * sm(0.8, 1.0, t)) * s
        hz = 1.0 - min(1.0, abs(d.z) * 1.1)
        bag = sm(0.25, 0.68, t) * (1.0 - 0.75 * sm(0.78, 1.0, t))
        dr = 1.0 + droop * (0.35 + 0.65 * hz) * bag * 1.25
        c = p + ey * r * (dr - 1.0) * 0.8
        rings.append(ring(mb, c, ex, ey, r, r * dr, n))
        # two or three long folds along the hanging pouch of the sleeve
        fold_attrs(mb, rings[-1], 1.5, 0.6, 0.15 + 0.85 * t, 0.8)
    loft(mb, rings, mat, smooth=True)
    # cuff band + dark opening
    last = rings[-1]
    ctr = sum((mb.verts[v] for v in last), Vector()) / len(last)
    inner = [mb.v(tuple(ctr + (mb.verts[v] - ctr) * 0.9)) for v in last]
    mb.quad_strip(last, inner, lining, True, False)
    mb.face(inner[::-1], "SleeveDark")
    mb.face(inner, "SleeveDark")


# ---------------------------------------------------------------------------------------------
# horse
# ---------------------------------------------------------------------------------------------
#: leg chains per gait: front legs (shoulder, elbow, knee, fetlock) and hind legs (hip, stifle,
#: hock, fetlock) swing angles in degrees (+ = towards the head); neck / head raise in degrees;
#: lift = height of the lowest hoof above the ground (flying gallop)
HORSE_GAITS = {
    "stand": dict(FL=(0, 0, 0, 0), FR=(4, 0, 0, 0), HL=(0, 0, 0, 0), HR=(-4, 0, 0, 0),
                  neck=0, head=0, tail=0.0, lift=0.0),
    "walk": dict(FL=(18, 10, -55, -20), FR=(-8, 0, 0, 0), HL=(-14, 0, -10, 0), HR=(12, 0, 8, 5),
                 neck=-4, head=-4, tail=0.15, lift=0.0),
    "trot": dict(FL=(24, 15, -70, -30), FR=(-14, 0, 0, 0), HL=(-20, -5, -5, 0), HR=(16, 10, 25, 10),
                 neck=-6, head=-2, tail=0.35, lift=0.0),
    # the flying gallop of Chinese horse painting: forelegs reach forward, hind legs stretch back
    "gallop": dict(FL=(62, 25, -35, 10), FR=(48, 30, -55, 0), HL=(-38, -20, -25, -20),
                   HR=(-26, -25, -35, -25), neck=-16, head=18, tail=0.9, lift=0.25),
    "rear": dict(FL=(70, 40, -110, -30), FR=(55, 55, -120, -20), HL=(20, 0, 15, 10),
                 HR=(10, 5, 20, 5), neck=12, head=-10, tail=0.4, lift=0.0, pitch=28),
}

#: rest pose of the horse (local: facing -Y, side x = +-, z up; metres, withers ~1.55 m)
_BODY = [  # (y, z, half-width, half-height) along the spine, tail root -> poll
    (0.97, 1.31, 0.05, 0.05), (0.93, 1.29, 0.18, 0.21), (0.82, 1.27, 0.26, 0.28),
    (0.62, 1.26, 0.30, 0.29), (0.34, 1.245, 0.31, 0.28), (0.02, 1.225, 0.32, 0.305),
    (-0.30, 1.215, 0.31, 0.33), (-0.56, 1.235, 0.28, 0.325), (-0.75, 1.30, 0.24, 0.31),
    (-0.89, 1.45, 0.20, 0.27), (-1.0, 1.61, 0.165, 0.215), (-1.09, 1.76, 0.135, 0.17),
    (-1.15, 1.87, 0.115, 0.135), (-1.175, 1.925, 0.05, 0.05)]
_NECK0 = 8          # first spine ring that belongs to the neck (rotates with "neck")
_HEAD = [  # forehead -> muzzle (rotates with "head" about the poll)
    (-1.13, 1.95, 0.05, 0.045), (-1.18, 1.915, 0.105, 0.13), (-1.28, 1.815, 0.115, 0.15),
    (-1.40, 1.68, 0.093, 0.118), (-1.51, 1.55, 0.078, 0.096), (-1.585, 1.46, 0.074, 0.084),
    (-1.62, 1.41, 0.04, 0.045)]
_FRONT = [(-0.60, 1.12), (-0.57, 0.86), (-0.61, 0.50), (-0.61, 0.15), (-0.665, 0.035)]
_FRONT_R = [0.12, 0.085, 0.054, 0.037, 0.047]
_HIND = [(0.56, 1.2), (0.42, 0.88), (0.71, 0.52), (0.71, 0.15), (0.665, 0.035)]
_HIND_R = [0.17, 0.115, 0.06, 0.039, 0.047]


def _swing(deg):
    """Rotation about X that swings a downward vector towards -Y (the head) by ``deg``."""
    return Matrix.Rotation(math.radians(-deg), 3, "X")


def _spine_loft(mb, pts, mat, n=14, caps=True, squash=None):
    """Loft elliptic rings perpendicular to a YZ spine; pts = [(Vector centre, rx, rz)]."""
    rings = []
    m = len(pts)
    for i, (c, rx, rz) in enumerate(pts):
        a = pts[max(0, i - 1)][0]
        b = pts[min(m - 1, i + 1)][0]
        t = (b - a)
        t.x = 0.0
        t.normalize()
        ex = Vector((1, 0, 0))
        up = Vector((0, t.z, -t.y))
        if up.z < 0 and abs(t.z) < 0.95:
            up = -up
        fn = squash(i) if squash else None
        rings.append(ring(mb, c, ex, up, rx, rz, n, fn))
    loft(mb, rings, mat, caps, caps)
    return rings


def horse(mb, rng, gait="walk", coat="HorseCoat", mane="HorseMane", saddle=None, scale=1.0,
          barding=None, tack="Plume", cloth="Banner0"):
    """Horse in the manner of court horse painting (withers ~1.55 m) facing -Y, hooves on z = 0:
    deep round barrel, arched neck, wedge head, fine legs with knees / hocks / fetlocks, flowing
    mane and tail.  ``saddle`` = saddle material (adds saddle, saddle cloth ``cloth``, breast
    collar and crupper with ``tack`` tassels, bridle and reins).  Returns the saddle point."""
    g = dict(HORSE_GAITS["stand"])
    g.update(HORSE_GAITS.get(gait, {}))
    s = 1.0                       # built at unit scale, ``scale`` applied at the end
    start = mb.n
    piv_n = Vector((0, -0.72, 1.32))
    Rn = _swing(-g["neck"])           # + neck = raise (rotates the neck back / up)
    body = []
    for i, (y, z, rx, rz) in enumerate(_BODY):
        c = Vector((0, y, z))
        if i >= _NECK0:
            w = min(1.0, (i - _NECK0 + 1) / 3.0)
            R = Matrix.Rotation(math.radians(g["neck"]) * w, 3, "X")
            c = piv_n + R @ (c - piv_n)
        body.append((c, rx, rz))
    poll = body[-2][0]
    # neck crest is narrower than the throat: squash the top of the neck rings a little
    _spine_loft(mb, body, coat, 16)
    Rh = Matrix.Rotation(math.radians(g["neck"] + g["head"]), 3, "X")
    p0 = Vector((0, _BODY[-2][0], _BODY[-2][1]))
    head = [(poll + Rh @ (Vector((0, y, z)) - p0), rx, rz) for (y, z, rx, rz) in _HEAD]
    _spine_loft(mb, head, coat, 12)
    hdir = (head[-1][0] - head[1][0]).normalized()
    hup = Vector((0, hdir.z, -hdir.y))
    if hup.z < 0:
        hup = -hup
    # ears, eyes, nostril
    for sd in (1, -1):
        e0 = head[1][0] + Vector((sd * 0.055, 0, 0)) + hup * 0.06 - hdir * 0.02
        e1 = e0 + (hup * 0.13 - hdir * 0.05 + Vector((sd * 0.02, 0, 0)))
        mb.tube([tuple(e0), tuple((e0 + e1) * 0.5 + Vector((sd * 0.008, 0, 0))), tuple(e1)], 0.028, coat, 5,
                radius_fn=lambda t: 1.0 - 0.85 * t)
        ellipsoid(mb, head[2][0] + Vector((sd * 0.098, 0, 0)) + hup * 0.04, (0.012, 0.022, 0.016), "Hoof", 6, 4)
    # legs
    hooves = []
    for key, rest, radii, side, front in (("FL", _FRONT, _FRONT_R, 1, True), ("FR", _FRONT, _FRONT_R, -1, True),
                                          ("HL", _HIND, _HIND_R, 1, False), ("HR", _HIND, _HIND_R, -1, False)):
        ang = g[key]
        x = side * (0.15 if front else 0.165)
        pts = [Vector((x, y, z)) for (y, z) in rest]
        out = [pts[0]]
        acc = 0.0
        for j in range(1, len(pts)):
            acc += ang[j - 1] if j - 1 < len(ang) else 0.0
            seg = pts[j] - pts[j - 1]
            out.append(out[-1] + _swing(acc) @ seg)
        # knee / hock: a slight bulge; fetlock: a knob
        rr = [radii[0] * s, radii[1] * s, radii[2] * s, radii[3] * s, radii[3] * 1.05 * s]
        mid = [out[0], (out[0] + out[1]) * 0.5, out[1], out[1] + (out[2] - out[1]) * 0.55, out[2],
               out[2] + (out[3] - out[2]) * 0.5, out[3]]
        mr = [rr[0], (rr[0] + rr[1]) * 0.55, rr[1], rr[1] * 0.75, rr[2], rr[3], rr[3] * 1.28]
        limb(mb, mid, mr, coat, n=9)
        # pastern + hoof
        pd = (out[4] - out[3])
        limb(mb, [out[3], out[3] + pd * 0.6], [rr[3] * 1.1, rr[3] * 0.95], coat, n=8)
        hb = out[3] + pd * 0.55
        hz = (pd.normalized() + Vector((0, 0, -0.6))).normalized()
        mb.cylinder(tuple(hb), tuple(hb + hz * 0.1 * s), 0.042 * s, 0.058 * s, "Hoof", 9)
        hooves.append(hb + hz * 0.1 * s)
    # mane: a crest of tapered locks falling to the off side, forelock
    n0, n1 = body[_NECK0][0], body[-2][0]
    for kk in range(18):
        t = kk / 17.0
        c = n0 + (n1 - n0) * t
        up = Vector((0, 0.45, 1.0)).normalized()
        base = c + up * (0.27 - 0.13 * t) * s + Vector((-0.03, 0.0, 0.0))
        L = (0.26 - 0.08 * t) * s * rng.uniform(0.85, 1.15)
        sw = 0.08 + g["tail"] * 0.14
        tip = base + Vector((-0.11 * s, L * (0.5 + sw), -L * (0.8 - sw)))
        mb.tube([tuple(base), tuple(base + (tip - base) * 0.5 + Vector((-0.04, 0.02, 0.03))), tuple(tip)],
                0.05 * s, mane, 6, radius_fn=lambda u: 1.0 - 0.8 * u)
    fl = head[1][0] + hup * 0.09
    mb.tube([tuple(fl), tuple(fl - hdir * 0.09 + hup * 0.02), tuple(fl - hdir * 0.18 - hup * 0.03)], 0.04 * s,
            mane, 5, radius_fn=lambda u: 1.0 - 0.8 * u)
    # tail: one tapering mass from the root that splits into a few locks towards the end
    root = body[1][0] + Vector((0, 0.03, 0.1))
    st = g["tail"]
    L = 1.0 * s
    c1 = root + Vector((0, 0.12 + 0.22 * st, 0.03 + 0.12 * st))
    c2 = root + Vector((0, 0.2 + 0.55 * st, -L * (0.45 - 0.33 * st)))
    mb.tube([tuple(root), tuple(c1), tuple(c2)], 0.085 * s, mane, 8,
            radius_fn=lambda u: 0.75 + 0.35 * math.sin(math.pi * min(1.0, u * 0.9 + 0.1)))
    for kk in range(5):
        a = (kk - 2) * 0.045
        p3 = root + Vector((a * 1.4 + rng.uniform(-0.02, 0.02), 0.3 + 0.95 * st + rng.uniform(-0.05, 0.05),
                            -L * (0.95 - 0.6 * st) * rng.uniform(0.92, 1.05)))
        pm = (c2 + p3) * 0.5 + Vector((a * 0.5, 0.04 * st, 0.0))
        mb.tube([tuple(c2 + Vector((a * 0.6, -0.02, 0.05))), tuple(pm), tuple(p3)], 0.06 * s, mane, 6,
                radius_fn=lambda u: 1.0 - 0.85 * u)
    # tack
    saddle_pt = Vector((0, -0.2, 1.56))
    if saddle:
        sp = saddle_pt
        # saddle cloth (障泥) hanging on both flanks
        for sd in (1, -1):
            def fp(u, v, sd=sd):
                yy = -0.42 + 0.5 * u
                ang = math.radians(15 + 70 * v)
                return (sd * (0.33 * math.sin(ang) + 0.015), yy, 1.36 + 0.24 * math.cos(ang) - 0.18 * v)
            mb.grid(fp, 6, 4, cloth, smooth=True, flip=sd < 0)
            mb.grid(fp, 6, 4, cloth, smooth=True, flip=sd > 0)
        # saddle seat with raised pommel and cantle
        prof = []
        for i in range(7):
            u = i / 6
            yy = -0.42 + 0.48 * u
            lift = 0.11 * (math.exp(-((u - 0.0) / 0.16) ** 2) + math.exp(-((u - 1.0) / 0.16) ** 2))
            prof.append((Vector((0, yy, 1.5 + lift)), 0.2, 0.08 + lift * 0.4))
        _spine_loft(mb, prof, saddle, 10)
        # breast collar + crupper bands, with tassels
        for (y0, z0, rx_, rz_, n_t, back) in ((-0.62, 1.2, 0.29, 0.33, 3, False), (0.72, 1.24, 0.3, 0.31, 3, True)):
            cc = Vector((0, y0, z0))
            rr = []
            for kk in range(13):
                a = math.pi * (kk / 12.0) - math.pi / 2
                rr.append(cc + Vector((math.sin(a) * rx_ * 1.03, 0, math.cos(a) * rz_ * 1.0)) +
                          Vector((0, (0.05 if back else -0.05) * math.cos(a), 0)))
            mb.tube([tuple(p) for p in rr], 0.014 * s, saddle, 5)
            for kk in range(n_t):
                a = -0.9 + 1.8 * kk / max(1, n_t - 1)
                tp = cc + Vector((math.sin(a) * rx_ * 1.05, (0.08 if back else -0.08), math.cos(a) * rz_ * 0.98 - 0.02))
                if abs(math.sin(a)) < 0.2 and not back:
                    tp.z -= 0.15
                mb.cylinder(tuple(tp), tuple(tp + Vector((0, 0, -0.16 * s))), 0.012 * s, 0.045 * s, tack, 7)
        # bridle: noseband, cheek straps, reins to the saddle
        nb_c = head[4][0]
        mb.tube([tuple(nb_c + Vector((sd * 0.072, 0, 0)) + hup * k_) for sd, k_ in
                 ((1, -0.06), (1, 0.06), (-1, 0.06), (-1, -0.06))], 0.009 * s, saddle, 4, caps=False)
        for sd in (1, -1):
            mb.tube([tuple(head[1][0] + Vector((sd * 0.09, 0, 0)) + hup * 0.05),
                     tuple(head[3][0] + Vector((sd * 0.085, 0, 0))),
                     tuple(nb_c + Vector((sd * 0.07, 0, 0)))], 0.008 * s, saddle, 4)
            mb.tube([tuple(nb_c + Vector((sd * 0.07, 0, 0)) - hup * 0.03),
                     tuple((nb_c + sp) * 0.5 + Vector((sd * 0.13, 0, -0.12))),
                     tuple(sp + Vector((sd * 0.12, -0.3, 0.1)))], 0.008 * s, "Rope", 4)
        # stirrups
        for sd in (1, -1):
            top = Vector((sd * 0.3, -0.2, 1.45))
            bot = Vector((sd * 0.36, -0.22, 0.95))
            mb.cylinder(tuple(top), tuple(bot), 0.008, 0.008, "Leather", 4)
    if barding:
        rr = [ring(mb, Vector((0, y, 1.25)), Vector((1, 0, 0)), Vector((0, 0, 1)), 0.335, 0.34, 14)
              for y in (-0.6, 0.0, 0.6)]
        loft(mb, rr, barding)
    # pitch the whole horse (rearing) about the hind hooves, put the hooves on the ground, scale
    pitch = g.get("pitch", 0.0)
    M = Matrix.Identity(4)
    if pitch:
        pv = max(hooves[2:], key=lambda h: h.y)
        M = Matrix.Translation(pv) @ Matrix.Rotation(math.radians(-pitch), 4, "X") @ Matrix.Translation(-pv)
    low = min((M @ h).z for h in hooves)
    M = Matrix.Scale(scale, 4) @ Matrix.Translation((0, 0, g.get("lift", 0.0) - low)) @ M
    mb.transform(start, M)
    return M @ saddle_pt


def rider(mb, rng, gait="gallop", pose="ride_spear", outfit="armored", weapon="spear", hat="helmet",
          cloth=0, cloth2=1, coat="HorseCoat", banner=None, barding=None, cape=False,
          saddle="Saddle", saddle_cloth=None):
    """Horse + mounted figure (one MeshBuilder)."""
    from .geometry import MeshBuilder
    sc = saddle_cloth or ("Banner%d" % rng.randrange(6))
    sp = horse(mb, rng, gait, coat=coat, saddle=saddle, barding=barding, cloth=sc)
    fm = MeshBuilder()
    sk = figure(fm, rng, pose, outfit, cloth, cloth2, weapon=weapon, hat=hat, banner=banner,
                cape=cape, jitter=3)
    off = sp - sk.pelvis
    mb.extend(fm, Matrix.Translation(off))


# ---------------------------------------------------------------------------------------------
# materials
# ---------------------------------------------------------------------------------------------
#: muted dyes of the period (sRGB): indigo, madder red, ochre, olive, black, undyed, plum,
#: teal, brown, cream
CLOTH = ["#2E3E5E", "#7A2A22", "#A07A3A", "#5A6438", "#24221F", "#B8AE98", "#5A2E44", "#2E5A58",
         "#5E4430", "#D8CCB0", "#8C3020", "#3A4A3A"]
BANNERS = ["#9E2A22", "#C89A3A", "#26262A", "#2F4A7A", "#E0D8C8", "#3E6A44"]


def materials(cloth=None, banners=None, skin="#B07A5A", armor="#3A3E44", armor_dark="#24262A",
              horse_coats=("#4A3020", "#6A4A30", "#2A2420", "#8A7A68"), fogged=True):
    """Material dict for every slot figures/horses use (Cloth0..N, Banner0..N, ...)."""
    from . import materials as M
    from .scenes_sky import G, lin4
    cloth = cloth or CLOTH
    banners = banners or BANNERS
    m = {}
    for i, c in enumerate(cloth):
        m["Cloth%d" % i] = cloth_material("IRCloth%d" % i, c)
    for i, c in enumerate(banners):
        m["Banner%d" % i] = cloth_material("IRBanner%d" % i, c, sheen=0.6, translucency=0.25)
    m["Skin"] = M.principled("IRSkin", skin, 0.55, specular=0.35)
    m["Hair"] = M.principled("IRHair", "#16120F", 0.45, specular=0.4)
    m["Armor"] = M.lamellar("IRArmor", armor, plate=(0.035, 0.06), metallic=0.6, roughness=0.42,
                            bump=0.5, lacing="#5A1A14", band_every=0, lacing_width=0.06)
    m["ArmorDark"] = M.principled("IRArmorDark", armor_dark, 0.45, metallic=0.7)
    m["Metal"] = M.principled("IRMetal", "#8A8E94", 0.3, metallic=1.0)
    m["Blade"] = M.principled("IRBlade", "#C8CCD2", 0.15, metallic=1.0)
    m["Bronze"] = M.principled("IRBronze", "bronze", 0.35, metallic=1.0)
    m["Gold"] = M.principled("IRGold", "gold", 0.3, metallic=1.0)
    m["Wood"] = M.principled("IRWood", "#4A3424", 0.7)
    m["Leather"] = M.principled("IRLeather", "#3A2A1E", 0.6)
    m["Straw"] = M.principled("IRStraw", "#B49A62", 0.85, vary=0.15, vary_scale=40.0)
    m["HatBlack"] = M.principled("IRHatBlack", "#141210", 0.5, specular=0.4)
    m["Plume"] = cloth_material("IRPlume", "#8E1E18", sheen=0.6)
    m["Rope"] = M.principled("IRRope", "#6A5A44", 0.9)
    m["Feather"] = M.principled("IRFeather", "#E8E2D6", 0.8)
    m["ShieldFace"] = M.principled("IRShield", "#5A2A1E", 0.5, vary=0.12, vary_scale=8.0)
    m["Hoof"] = M.principled("IRHoof", "#1E1A16", 0.6)
    m["SleeveDark"] = M.principled("IRSleeveDark", "#2A221C", 0.9)
    for i, c in enumerate(horse_coats):
        m["HorseCoat%d" % i] = M.principled("IRHorse%d" % i, c, 0.5, specular=0.4, sheen=0.3)
    m["HorseCoat"] = m["HorseCoat0"]
    m["HorseMane"] = M.principled("IRMane", "#141110", 0.6)
    m["Flame"] = flame_material("IRFlame")
    m["LanternPaper"] = lantern_material("IRLantern", "#E04020")
    return m


def cloth_material(name, color, sheen=0.4, translucency=0.0, roughness=0.8):
    from .materials import new
    from .scenes_sky import G, lin4
    from .scenes_terrain import _fin, noise
    mat, nb, created = new(name)
    if not created:
        return mat
    b = G(nb.tree)
    oi = nb.node("ShaderNodeObjectInfo")
    P = nb.node("ShaderNodeNewGeometry").outputs["Position"]
    n = noise(nb, P, 2.0, 3, 0.5)
    base = lin4(color)
    col = b.mix(b.cmul(base, 0.82), b.cmul(base, 1.12), b.smooth(b.math("ADD", b.math("MULTIPLY", oi.outputs["Random"], 0.6), b.math("MULTIPLY", n, 0.4)), 0.2, 0.8))
    p = b.principled(Base_Color=col, Roughness=roughness, Sheen_Weight=sheen, Sheen_Roughness=0.35,
                     Specular_IOR_Level=0.3)
    sh = p.outputs[0]
    if translucency:
        tr = nb.node("ShaderNodeBsdfTranslucent")
        b.link(col, tr.inputs["Color"])
        mx = nb.node("ShaderNodeMixShader")
        mx.inputs[0].default_value = translucency
        b.link(sh, mx.inputs[1])
        b.link(tr.outputs[0], mx.inputs[2])
        sh = mx.outputs[0]
    return _fin(mat, nb, sh)


def flame_material(name="IRFlame", color="#FF9A3A", strength=18.0, camera_only=True):
    """Emissive flame: hot core to orange edges (facing ratio).  ``camera_only``: the flame is
    seen but does not light the scene (pair it with a point light) - small bright emitters hit
    by indirect rays are the main source of fireflies without a denoiser."""
    from .materials import new
    from .scenes_sky import G, lin4
    mat, nb, created = new(name)
    if not created:
        return mat
    b = G(nb.tree)
    lw = nb.node("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    f = lw.outputs["Facing"]
    col = b.mix(lin4("#FFE6A0"), lin4(color), b.smooth(f, 0.1, 0.8))
    em = nb.node("ShaderNodeEmission")
    b.link(col, em.inputs["Color"])
    k = b.math("MULTIPLY", b.math("SUBTRACT", 1.15, f), strength)
    if camera_only:
        lp = nb.node("ShaderNodeLightPath")
        k = b.math("MULTIPLY", k, b.math("MAXIMUM", lp.outputs["Is Camera Ray"], lp.outputs["Is Transmission Ray"]))
    b.link(k, em.inputs["Strength"])
    nb.output(em.outputs[0])
    mat["ir_fog"] = 1
    return mat


def lantern_material(name, color="#D83A20", strength=6.0, light=0.15):
    """Glowing red paper lantern (emission + a little diffuse so the ribs read).  Only
    ``light`` x the emission illuminates the scene (fireflies); the camera sees it all."""
    from .materials import new
    from .scenes_sky import G, lin4
    mat, nb, created = new(name)
    if not created:
        return mat
    b = G(nb.tree)
    lw = nb.node("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.4
    tc = nb.node("ShaderNodeTexCoord")
    z = b.sep(tc.outputs["Generated"])[2]
    ribs = b.math("ABSOLUTE", b.math("SINE", b.math("MULTIPLY", z, 60.0)))
    k = b.math("MULTIPLY", b.math("ADD", 0.55, b.math("MULTIPLY", ribs, 0.45)),
               b.math("SUBTRACT", 1.1, b.math("MULTIPLY", lw.outputs["Facing"], 0.6)))
    em = nb.node("ShaderNodeEmission")
    b.link(b.mix(lin4("#FF9A50"), lin4(color), b.smooth(lw.outputs["Facing"], 0.0, 0.45)), em.inputs["Color"])
    lp = nb.node("ShaderNodeLightPath")
    vis = b.math("ADD", light, b.math("MULTIPLY", lp.outputs["Is Camera Ray"], 1.0 - light))
    b.link(b.math("MULTIPLY", b.math("MULTIPLY", k, strength), vis), em.inputs["Strength"])
    nb.output(em.outputs[0])
    mat["ir_fog"] = 1
    return mat
