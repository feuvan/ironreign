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

CAM = (-6.0, -52.0, 15.0)
TARGET = (2.0, 40.0, 1.0)
FOCAL = 34.0
SM = K.ScreenMap(CAM, TARGET, FOCAL)


def height(X, Y):
    from ironart.scenes_terrain import fbm2
    peaks = SM.peaks([
        (0.15, 0.28, 900, 260, 2.2), (0.42, 0.25, 1300, 380, 1.8), (0.78, 0.22, 1500, 420, 1.6),
        (0.98, 0.30, 800, 240, 2.0), (0.60, 0.15, 3200, 900, 1.2), (0.25, 0.17, 3800, 1000, 1.3),
        (0.90, 0.12, 4200, 1100, 1.1),
    ])
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
    land = LD.qinglv("GB_Battle_Land", z0=5.0, z1=420.0, cun=0.7, cun_px=7.0, cun_len=60.0,
                     moss_px=10.0, var_scale=0.004, near=40.0, far=5000.0, plain_h=0.02,
                     plain=("#D6CBA2", "#CDBB8E"), plain_bare=0.3, ribs=True)
    fpx = FOCAL / 36.0 * 640.0
    peaks_w = SM.peaks([(0.15, 0.28, 900, 260, 2.2), (0.42, 0.25, 1300, 380, 1.8), (0.78, 0.22, 1500, 420, 1.6),
                        (0.98, 0.30, 800, 240, 2.0), (0.60, 0.15, 3200, 900, 1.2), (0.25, 0.17, 3800, 1000, 1.3),
                        (0.90, 0.12, 4200, 1100, 1.1)])
    yaw = math.degrees(SM.yaw)
    LD.fan_terrain("Land", CAM[:2], yaw, 56.0, 15.0, 9000.0, 520, 340, height, land, cols["land"],
                   attrs={"rib": lambda X, Y: LD.peak_ribs(X, Y, peaks_w, CAM[:2], fpx, 7.0)})

    def ground(x, y):
        return float(height(np.array([[x]]), np.array([[y]]))[0, 0])

    def put(mb, x, y, rz, fn, **kw):
        z = ground(x, y)
        f = MeshBuilder()
        fn(f, **kw)
        mb.extend(f, Matrix.Translation((x, y, z)) @ Matrix.Rotation(rz, 4, "Z"))

    from ironart import scenes_people as P
    army = MeshBuilder()
    flags = MeshBuilder()
    # ---- the red host: cavalry wedge charging right, infantry following -------------------------
    n_cav = 26 if not pv else 14
    for i in range(n_cav):
        row = i // 6
        x = -6.0 - row * 4.2 + rng.uniform(-1.0, 1.0) - (i % 6) * 0.6
        y = 6.0 + (i % 6) * 3.1 - row * 1.0 + rng.uniform(-0.8, 0.8)
        rz = math.pi / 2 + rng.uniform(-0.2, 0.15)
        coat = "HorseCoat%d" % rng.randrange(4)
        put(army, x, y, rz, lambda f: P.rider(f, random.Random(i), gait="gallop", pose="ride_charge",
                                                outfit="armored", weapon="spear" if i % 4 else "halberd",
                                                hat="helmet_plume" if i % 3 == 0 else "helmet",
                                                cloth=0, cloth2=3, coat=coat,
                                                banner=0 if i % 5 == 1 else None))
    for i in range(40 if not pv else 18):
        x = -26.0 - (i % 8) * 1.6 + rng.uniform(-0.4, 0.4)
        y = 4.0 + (i // 8) * 3.4 + rng.uniform(-0.6, 0.6) + (i % 8) * 0.5
        put(army, x, y, math.pi / 2 + rng.uniform(-0.15, 0.15),
            lambda f: P.figure(f, random.Random(100 + i), "charge", "soldier", cloth=0, cloth2=3,
                               weapon="spear", hat="helmet", jitter=6.0))
    # red general under his standard on the rise at the left
    put(army, -20.0, -4.0, math.pi / 2 - 0.3,
        lambda f: P.rider(f, random.Random(7), gait="rear", pose="ride_spear", outfit="general",
                          weapon="halberd", hat="helmet_plume", cloth=0, cloth2=3, coat="HorseCoat1",
                          cape=True))
    # ---- the blue host: spear wall facing left, archers and banners behind --------------------
    for i in range(54 if not pv else 24):
        rank = i // 9
        x = 4.0 + rank * 1.5 + rng.uniform(-0.25, 0.25)
        y = 2.0 + (i % 9) * 2.6 + rank * 0.8 + rng.uniform(-0.3, 0.3)
        pose = "thrust" if rank < 2 else ("guard" if rank < 3 else "march_spear")
        put(army, x, y, -math.pi / 2 + rng.uniform(-0.12, 0.12),
            lambda f: P.figure(f, random.Random(300 + i), pose, "soldier", cloth=1, cloth2=11,
                               weapon="spear", hat="helmet", shield=rank == 0, jitter=5.0))
    for i in range(24 if not pv else 10):
        x = 14.0 + (i // 8) * 1.8 + rng.uniform(-0.3, 0.3)
        y = 6.0 + (i % 8) * 2.8 + rng.uniform(-0.4, 0.4)
        put(army, x, y, -math.pi / 2 - 0.2,
            lambda f: P.figure(f, random.Random(500 + i), "aim_up", "soldier", cloth=11, cloth2=1,
                               weapon="bow", hat="band", jitter=4.0))
    put(army, 22.0, 4.0, -math.pi / 2 + 0.4,
        lambda f: P.rider(f, random.Random(9), gait="walk", pose="ride_spear", outfit="general",
                          weapon="spear", hat="helmet_plume", cloth=1, cloth2=11, coat="HorseCoat2",
                          cape=True))
    # banners: tall poles above both hosts
    for i in range(9):
        x = -12.0 - i * 2.6 + rng.uniform(-0.8, 0.8)
        y = 8.0 + rng.uniform(-4, 9)
        K.banner(flags, rng, color=[0, 5, 1][i % 3], at=(x, y, ground(x, y)), height=rng.uniform(5.5, 7.0), cloth=(1.4, 2.3))
    for i in range(9):
        x = 9.0 + i * 1.9 + rng.uniform(-0.6, 0.6)
        y = 10.0 + rng.uniform(-5, 12)
        K.banner(flags, rng, color=[2, 4, 3][i % 3], at=(x, y, ground(x, y)), height=rng.uniform(5.5, 7.0), cloth=(1.4, 2.3))
    K.banner(flags, rng, color=0, at=(-21.5, -2.5, ground(-21.5, -2.5)), height=8.5, cloth=(2.0, 3.2))
    K.banner(flags, rng, color=2, at=(23.5, 5.0, ground(23.5, 5.0)), height=8.5, cloth=(2.0, 3.2))
    K.emit(army, "Armies", mats, "fig")
    K.emit(flags, "Banners", mats, "fig")
    # a few trees on the rise and the hills
    tmb = MeshBuilder()
    pl = []
    for (sx, sy, d, rad, n) in ((0.06, 0.55, 140, 14, 5), (0.97, 0.52, 160, 18, 6), (0.30, 0.43, 420, 30, 8),
                                (0.70, 0.42, 520, 40, 9)):
        x, y, _ = SM.at(sx, sy, d)
        pl += K.grove(rng, (x, y), rad, n, ground=ground, kinds=("Leaf", "LeafDark", "pine"))
    K.trees(tmb, pl, rng, cam_dir=Vector(TARGET) - Vector(CAM), size=0.5, low=True)
    K.emit(tmb, "Trees", mats, "tree")
    cam = L.camera(CAM, TARGET, focal_mm=FOCAL)
    look = dict(
        sky=dict(stops=[(0.0, "ochre_l", 0.18), (0.25, "silk", 0.05), (0.4, "silk", 0.0)]),
        fade=dict(d0=120.0, d1=4000.0, color=GB.mixc("silk", "ochre_l", 0.25), amount=0.8, gamma=0.7, cover=0.45),
        mist=[dict(y=(0.30, 0.37), soft=0.02, jitter=0.02, dist_min=500.0, amount=1.0, noise_px=120, holes=0.2),
              dict(y=(0.18, 0.24), soft=0.02, jitter=0.02, dist_min=2500.0, amount=0.9, noise_px=120, holes=0.3)],
        ink=1.0,
    )

    def paint2d(cv, r):
        rr = np.random.default_rng(3)
        # dust raised by the charge and the melee: pale ochre washes (front, partly transparent)
        for (cx, cy, rx, ry, a) in ((0.47, 0.52, 120, 40, 0.38), (0.30, 0.58, 150, 34, 0.32),
                                    (0.62, 0.50, 90, 30, 0.28), (0.20, 0.63, 110, 24, 0.25)):
            G2wash(cv, "front", "#D8C29A", a, (cx, cy), rx, ry, rr)
        # a volley of arrows arcing from the blue archers over the melee
        with cv.paint("sky", "ink", 0.8) as d:
            for i in range(26):
                x0 = rr.uniform(0.55, 0.78)
                y0 = rr.uniform(0.18, 0.30)
                L_ = rr.uniform(0.018, 0.026)
                a = math.radians(rr.uniform(160, 172))
                d.stroke([(x0, y0), (x0 + math.cos(a) * L_, y0 + math.sin(a) * L_ * 0.4 + 0.004)], 0.7, "flat")
    return dict(camera=cam, look=look, paint2d=paint2d, notes="no UI keep-out; clash centred at x ~45%")


def G2wash(cv, where, color, alpha, c, rx, ry, rr):
    """Irregular soft wash made of a few overlapping blobs."""
    with cv.paint(where, color, alpha, soft=min(rx, ry) * 0.6) as d:
        for k in range(6):
            dx = rr.uniform(-0.6, 0.6) * rx / cv.W * cv.k
            dy = rr.uniform(-0.5, 0.5) * ry / cv.H * cv.k
            d.ellipse((c[0] + dx, c[1] + dy), rx * rr.uniform(0.4, 0.7), ry * rr.uniform(0.5, 0.8))
