"""Event: Battle - two armies clash on an open plain.

From a low rise: the cinnabar-bannered cavalry of one host charges in from the left into the
azurite-bannered spear wall of the other; forests of banners above both, generals under their
standards, a volley of arrows arcing over, dust rising as pale ochre washes; low blue-green hills
and far ranges behind, mist along their feet."""

import math
import random

import numpy as np
from mathutils import Matrix, Vector

from ironart import scenes_gongbi as GB
from ironart import scenes_gongbi_kit as K
from ironart import scenes_gongbi_land as LD
from ironart import scenes_look as L
from ironart.geometry import MeshBuilder

SPEC = dict(name="Battle", art="Art/Events/Battle.png", master="Events/Battle@2x.png",
            size=(640, 360), k=4, m=2, seed=21, spp=12, preview_spp=6)

CAM = (-3.0, -19.0, 8.0)
TARGET = (4.0, 46.0, 0.5)
FOCAL = 28.0
SM = K.ScreenMap(CAM, TARGET, FOCAL)
HILLS = [(0.12, 0.25, 700, 220, 2.2), (0.40, 0.21, 1100, 330, 1.8), (0.74, 0.19, 1300, 380, 1.6),
         (0.97, 0.26, 650, 200, 2.0), (0.58, 0.10, 3000, 900, 1.2), (0.22, 0.12, 3500, 1000, 1.3),
         (0.90, 0.08, 3900, 1100, 1.1)]


def height(X, Y):
    from ironart.scenes_terrain import fbm2
    peaks = SM.peaks(HILLS)
    Hh = LD.peak_field(X, Y, peaks, seed=21, ridge=0.35, ridge_scale=160.0, softmax=4.0)
    roll = (fbm2(X, Y, 90.0, 3, seed=4) - 0.5) * 2.5
    near = np.clip(1.0 - (Y - 60.0) / 200.0, 0, 1)
    return Hh + roll * near + np.clip(Y - 120.0, 0, None) * 0.004


def build(r):
    rng = random.Random(21)
    pv = r["preview"]
    cols = GB.collections()
    mats = K.materials(cloth=["cinnabar", "azurite", "#5A564E", "#3A3530", "ochre", "#E2D6BC",
                              "rouge", "teal", "#7A5A3A", "white", "vermilion", "indigo"],
                       banners=["cinnabar", "gold", "azurite", "white", "#2E2A28", "vermilion"],
                       armor="#6A6258")
    mats["ArmorRed"] = GB.lamellar("GB_ArmorRed", "#A8604A", lace="gold")
    mats["ArmorBlue"] = GB.lamellar("GB_ArmorBlue", "#5E7286", lace="white")
    mats["MetalRed"] = mats["Metal"]
    land = LD.qinglv("GB_Battle_Land", z0=5.0, z1=240.0, cun=0.7, cun_px=7.0, cun_len=60.0,
                     moss_px=10.0, var_scale=0.004, near=40.0, far=5000.0, plain_h=0.02,
                     plain=("#D6CBA2", "#CDBB8E"), plain_bare=0.3, ribs=True)
    fpx = FOCAL / 36.0 * 640.0
    peaks_w = SM.peaks(HILLS)
    yaw = math.degrees(SM.yaw)
    LD.fan_terrain("Land", CAM[:2], yaw, 56.0, 15.0, 9000.0, 520, 340, height, land, cols["land"],
                   attrs={"rib": lambda X, Y: LD.peak_ribs(X, Y, peaks_w, CAM[:2], fpx, 7.0)})

    def ground(x, y):
        return float(height(np.array([[x]]), np.array([[y]]))[0, 0])

    def put(mb, x, y, rz, fn, side="red", **kw):
        z = ground(x, y)
        f = MeshBuilder()
        fn(f, **kw)
        K.rename(f, {"Armor": "ArmorRed" if side == "red" else "ArmorBlue",
                     "Metal": "MetalRed" if side == "red" else "Metal"})
        mb.extend(f, Matrix.Translation((x, y, z)) @ Matrix.Rotation(rz, 4, "Z"))

    from ironart import scenes_people as P
    army = MeshBuilder()
    flags = MeshBuilder()
    def at(sx, sy):
        p = SM.ground(sx, sy)
        return p[0], p[1]

    # ---- the red host: a cavalry wedge charging in from the left foreground --------------------
    n_cav = 34 if not pv else 16
    for i in range(n_cav):
        sx = rng.uniform(-0.05, 0.42) - 0.0
        sy = rng.uniform(0.56, 0.98)
        # wedge: the further right, the narrower the band
        sy = 0.6 + (sy - 0.6) * (1.0 - max(0.0, sx - 0.1) * 1.2)
        x, y = at(sx, sy)
        rz = math.pi / 2 + rng.uniform(-0.35, 0.05)
        coat = "HorseCoat%d" % rng.randrange(4)
        put(army, x, y, rz, lambda f: P.rider(f, random.Random(i), gait="gallop", pose="ride_charge",
                                                outfit="armored", weapon="spear" if i % 4 else "halberd",
                                                hat="helmet_plume" if i % 3 == 0 else "helmet",
                                                cloth=0, cloth2=3, coat=coat,
                                                banner=0 if i % 6 == 1 else None))
    for i in range(46 if not pv else 20):
        x, y = at(rng.uniform(0.0, 0.3), rng.uniform(0.47, 0.6))
        put(army, x, y, math.pi / 2 + rng.uniform(-0.2, 0.2),
            lambda f: P.figure(f, random.Random(100 + i), rng.choice(["charge", "thrust", "slash_high"]),
                               "soldier", cloth=0, cloth2=3, weapon=rng.choice(["spear", "spear", "sword"]),
                               hat="helmet", jitter=6.0))
    # the red general under his standard, reining in on the left
    gx, gy = at(0.08, 0.5)
    put(army, gx, gy, math.pi / 2 - 0.35,
        lambda f: P.rider(f, random.Random(7), gait="rear", pose="ride_spear", outfit="general",
                          weapon="halberd", hat="helmet_plume", cloth=0, cloth2=3, coat="HorseCoat1",
                          cape=True))
    # ---- the blue host: a spear wall braced against the charge, archers behind -----------------
    for i in range(80 if not pv else 36):
        rank = i // 16
        sx = 0.43 + rank * 0.045 + rng.uniform(-0.01, 0.01) + (i % 16) * 0.004
        sy = 0.50 + (i % 16) * 0.024 - rank * 0.012 + rng.uniform(-0.006, 0.006)
        sx += max(0.0, sy - 0.62) * 0.35
        x, y = at(sx, sy)
        pose = "thrust" if rank < 2 else ("guard" if rank < 3 else "march_spear")
        put(army, x, y, -math.pi / 2 + 0.3 + rng.uniform(-0.12, 0.12), side="blue", fn=
            lambda f: P.figure(f, random.Random(300 + i), pose, "soldier", cloth=1, cloth2=11,
                               weapon="spear", hat="helmet", shield=rank == 0, jitter=5.0))
    for i in range(44 if not pv else 18):
        x, y = at(rng.uniform(0.62, 1.05), rng.uniform(0.62, 0.97))
        put(army, x, y, -math.pi / 2 - 0.35 + rng.uniform(-0.15, 0.15), side="blue", fn=
            lambda f: P.figure(f, random.Random(900 + i), rng.choice(["charge", "march_spear", "charge"]),
                               "soldier", cloth=1, cloth2=11, weapon=rng.choice(["spear", "halberd", "sword"]),
                               hat="helmet", shield=rng.random() < 0.3, jitter=6.0))
    for i in range(30 if not pv else 12):
        x, y = at(rng.uniform(0.70, 0.96), rng.uniform(0.43, 0.5))
        put(army, x, y, -math.pi / 2 - 0.1, side="blue", fn=
            lambda f: P.figure(f, random.Random(500 + i), "aim_up", "soldier", cloth=11, cloth2=1,
                               weapon="bow", hat="band", jitter=4.0))
    bgx, bgy = at(0.86, 0.53)
    put(army, bgx, bgy, -math.pi / 2 + 0.5, side="blue", fn=
        lambda f: P.rider(f, random.Random(9), gait="walk", pose="ride_spear", outfit="general",
                          weapon="spear", hat="helmet_plume", cloth=1, cloth2=11, coat="HorseCoat2",
                          cape=True))
    # melee: a few duels right at the clash line
    for i in range(10):
        x, y = at(rng.uniform(0.36, 0.46), rng.uniform(0.52, 0.66))
        red = i % 2 == 0
        put(army, x, y, (math.pi / 2 if red else -math.pi / 2) + rng.uniform(-0.4, 0.4), side="red" if red else "blue", fn=
            lambda f: P.figure(f, random.Random(700 + i), rng.choice(["slash_high", "thrust", "guard"]),
                               "soldier", cloth=0 if red else 1, cloth2=3 if red else 11,
                               weapon=rng.choice(["sword", "spear"]), hat="helmet", jitter=6.0))
    # reserves: ranks further back on both sides, half lost in the dust
    for i in range(60 if not pv else 24):
        red = i % 2 == 0
        x, y = at(rng.uniform(0.0, 0.36) if red else rng.uniform(0.6, 1.0), rng.uniform(0.39, 0.45))
        put(army, x, y, (math.pi / 2 if red else -math.pi / 2) + rng.uniform(-0.1, 0.1),
            side="red" if red else "blue", fn=
            lambda f: P.figure(f, random.Random(1200 + i), "march_spear", "soldier",
                               cloth=0 if red else 1, cloth2=3 if red else 11, weapon="spear",
                               hat="helmet", jitter=3.0))
    # banners: forests of poles above both hosts
    for i in range(12):
        x, y = at(rng.uniform(0.0, 0.33), rng.uniform(0.47, 0.62))
        K.banner(flags, rng, color=[0, 5, 1][i % 3], at=(x, y, ground(x, y)), height=rng.uniform(5.0, 6.5), cloth=(1.3, 2.2))
    for i in range(12):
        x, y = at(rng.uniform(0.52, 0.95), rng.uniform(0.43, 0.52))
        K.banner(flags, rng, color=[2, 4, 3][i % 3], at=(x, y, ground(x, y)), height=rng.uniform(5.0, 6.5), cloth=(1.3, 2.2))
    K.banner(flags, rng, color=0, at=(gx + 1.5, gy + 1.0, ground(gx, gy)), height=8.0, cloth=(2.0, 3.2))
    K.banner(flags, rng, color=2, at=(bgx + 1.5, bgy + 1.0, ground(bgx, bgy)), height=8.0, cloth=(2.0, 3.2))
    K.emit(army, "Armies", mats, "fig", thin=K.THIN + ("MetalRed",))
    K.emit(flags, "Banners", mats, "fig", thin=K.THIN)
    # a few trees on the rise and the hills
    tmb = MeshBuilder()
    pl = []
    for (sx, sy, d, rad, n) in ((0.30, 0.31, 420, 30, 8), (0.66, 0.30, 520, 40, 9)):
        x, y, _ = SM.at(sx, sy, d)
        pl += K.grove(rng, (x, y), rad, n, ground=ground, kinds=("pine", "pine", "LeafDark"))
    K.trees(tmb, pl, rng, cam_dir=Vector(TARGET) - Vector(CAM), size=0.5, low=True)
    K.emit(tmb, "Trees", mats, "tree")
    cam = L.camera(CAM, TARGET, focal_mm=FOCAL)
    look = dict(
        sky=dict(stops=[(0.0, "ochre_l", 0.18), (0.25, "silk", 0.05), (0.4, "silk", 0.0)]),
        fade=dict(d0=120.0, d1=4000.0, color=GB.mixc("silk", "ochre_l", 0.25), amount=0.8, gamma=0.7, cover=0.45),
        mist_tint=("#E2D0A8", 0.55),
        mist=[dict(y=(0.36, 0.46), soft=0.025, jitter=0.03, dist_min=55.0, amount=0.85, noise_px=90, holes=0.35),
              dict(y=(0.27, 0.34), soft=0.02, jitter=0.02, dist_min=300.0, amount=1.0, noise_px=120, holes=0.2),
              dict(y=(0.13, 0.19), soft=0.02, jitter=0.02, dist_min=2500.0, amount=0.9, noise_px=120, holes=0.3)],
        ink=1.0,
    )

    def paint2d(cv, r):
        rr = np.random.default_rng(3)
        # dust raised by the charge and the melee: pale ochre washes (front, partly transparent)
        for (cx, cy, rx, ry, a) in ((0.40, 0.50, 120, 30, 0.42), (0.22, 0.47, 160, 26, 0.35),
                                    (0.58, 0.44, 110, 22, 0.3), (0.12, 0.62, 130, 30, 0.22)):
            G2wash(cv, "front", "#DCC8A0", a, (cx, cy), rx, ry, rr)
        # a volley of arrows arcing from the blue archers over the clash: fine parallel strokes
        with cv.paint("front", "ink", 0.6, soft=0.0) as d:
            for k in range(110):
                t0 = rr.uniform(0.0, 1.0)
                x0 = 0.30 + 0.36 * t0 + rr.uniform(-0.02, 0.02)
                y0 = 0.27 + 0.13 * (2 * t0 - 1) ** 2 + rr.uniform(-0.025, 0.025)
                vx, vy = -0.36 * cv.W, -0.52 * (2 * t0 - 1) * cv.H
                n_ = math.hypot(vx, vy)
                L_ = rr.uniform(4.5, 6.0) * cv.k
                d.stroke([(x0, y0), (x0 + vx / n_ * L_ / cv.W, y0 + vy / n_ * L_ / cv.H)], 0.28, "flat")
    return dict(camera=cam, look=look, paint2d=paint2d, notes="no UI keep-out; clash centred at x ~45%")


def G2wash(cv, where, color, alpha, c, rx, ry, rr):
    """Irregular soft wash made of a few overlapping blobs."""
    with cv.paint(where, color, alpha, soft=min(rx, ry) * 0.6) as d:
        for k in range(6):
            dx = rr.uniform(-0.6, 0.6) * rx / cv.W * cv.k
            dy = rr.uniform(-0.5, 0.5) * ry / cv.H * cv.k
            d.ellipse((c[0] + dx, c[1] + dy), rx * rr.uniform(0.4, 0.7), ry * rr.uniform(0.5, 0.8))
