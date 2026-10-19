"""Title background: an epic blue-green landscape (青绿山水, after the panoramic manner of
"A Thousand Li of Rivers and Mountains") - seen from high above a great river: a walled fortress
city on its terrace by the water (the World Models tier-3 capital in the ruled-line 界画 manner,
banners on the walls), a towering massif of azurite and malachite peaks rising behind it in tiers
separated by bands of bare-silk mist, pines along every ridge, far ranges fading into the silk.
A rocky bank with ancient pines frames the right edge.  The left ~40 % (menu side) stays calm:
open water with a few sails, a low far shore (平远) and a skein of geese.

Composition is authored in screen space (:class:`ironart.scenes_gongbi_kit.ScreenMap`): every
peak is placed by where its summit should sit in the frame and how far away it stands."""

import math
import random

import numpy as np
from mathutils import Matrix, Vector

from ironart import scenes_gongbi as GB
from ironart import scenes_gongbi_kit as K
from ironart import scenes_gongbi_land as LD
from ironart import scenes_look as L
from ironart.geometry import MeshBuilder

SPEC = dict(name="Title", art="Art/UI/Title_Background.png", master="UI/Title_Background@2x.png",
            size=(1920, 1080), k=2, m=2, seed=7, spp=6, preview_spp=4)

CAM = (0.0, -900.0, 330.0)
TARGET = (250.0, 900.0, 150.0)
FOCAL = 36.0
SM = K.ScreenMap(CAM, TARGET, FOCAL)
CITY_SCR = (0.60, 0.70)
CITY_SCALE = 2.8
CITY_RZ = -24.0
SHORE_SX = 0.47

# (sx, sy of the summit, horizontal distance m, radius m, shape)
PEAKS = [
    # the massif (高远): a tall central peak and its tiers
    (0.745, 0.035, 3000, 560, 0.7), (0.865, 0.10, 2750, 470, 0.8), (0.625, 0.115, 2950, 480, 0.85),
    (0.965, 0.17, 2450, 420, 0.9), (0.535, 0.215, 3150, 430, 1.0), (0.685, 0.20, 2350, 300, 0.85),
    (0.805, 0.235, 2100, 290, 0.95),
    # lower shoulders in front of it
    (0.585, 0.33, 1950, 250, 1.3), (0.905, 0.315, 1750, 270, 1.15), (0.745, 0.355, 1700, 220, 1.35),
    (0.995, 0.39, 1450, 240, 1.3), (0.505, 0.395, 2050, 200, 1.6), (0.66, 0.40, 2100, 170, 1.5),
    # low hills right behind the city
    (0.745, 0.49, 1650, 160, 1.9), (0.53, 0.515, 1750, 140, 1.9), (0.88, 0.47, 1350, 170, 1.7),
    # far ranges glimpsed behind the massif
    (0.42, 0.21, 7600, 1500, 1.0), (1.02, 0.07, 7200, 1500, 1.0), (0.30, 0.285, 8200, 1500, 1.2),
    # far shore on the left (平远) - low, wide
    (0.10, 0.375, 5600, 950, 2.2), (0.24, 0.36, 6800, 1200, 2.0), (0.36, 0.385, 5000, 700, 2.0),
    (0.02, 0.355, 7800, 1300, 1.8),
]


def city_center():
    p = SM.ground(CITY_SCR[0], CITY_SCR[1], z=18.0)
    return Vector(p)


def height(X, Y):
    peaks = SM.peaks(PEAKS)
    Hh = LD.peak_field(X, Y, peaks, seed=7, ridge=0.55, ridge_scale=180.0, softmax=4.0, roughness=0.8)
    from ironart.scenes_terrain import fbm2
    sx = SM.sx(X, Y)
    d = SM.dist(X, Y)
    n = fbm2(X, Y, 260.0, 4, seed=11) - 0.5
    # land / water: water left of the shore line near and middle distance; far on, the river
    # winds away between the far shore and the massif
    shore = SHORE_SX + n * 0.09 + 0.025 * np.sin(d / 380.0 + 1.3) - 0.025 * np.clip((d - 700) / 900, 0, 1)
    land_near = np.clip((sx - shore) / 0.07, 0, 1) ** 1.4
    rv = 0.44 + 0.03 * np.sin(d / 900.0) + n * 0.02
    river = 1.0 - np.clip((np.abs(sx - rv) - 0.012 * 3000 / np.maximum(d, 1)) / 0.01, 0, 1)
    far_land = np.clip((d - 3200.0) / 600.0, 0, 1) * (1.0 - river)
    land = np.maximum(land_near, far_land)
    plain = 4.0 + np.clip(fbm2(X, Y, 300.0, 3, seed=5) - 0.42, 0, 1) * 40.0 * land_near
    base = plain * land - 6.0 * (1.0 - land)
    Hh = np.maximum(base, Hh * np.maximum(land, (Hh > 40).astype(np.float64)) + base * (Hh <= 40))
    # the city terrace
    c = city_center()
    rc = np.sqrt((X - c.x) ** 2 + (Y - c.y) ** 2)
    R0 = 60.0 * CITY_SCALE
    f = np.clip((rc - R0) / 110.0, 0.0, 1.0)
    f = f * f * (3 - 2 * f)
    Hh = Hh * f + 16.0 * (1 - f)
    return Hh


def sail_boat(mb, at, rz, s=1.0):
    """River junk: hull, deck hut of matting, a mast with a battened matting sail."""
    x, y, z = at
    b = MeshBuilder()
    b.box((0, 0, 0.0), (3.2, 11.0, 1.0), "Wood", taper=(0.0, 0.0))
    b.box((0, -5.2, 0.6), (2.0, 1.8, 0.6), "Wood")
    b.box((0, 1.5, 1.0), (2.4, 3.6, 1.4), "Straw")
    b.cylinder((0, -1.5, 1.0), (0, -1.5, 9.5), 0.12, 0.08, "Wood", 6)
    b.box((0.0, -1.2, 2.4), (0.12, 6.0, 7.6), "Sail")
    mb.extend(b, Matrix.Translation((x, y, z)) @ Matrix.Rotation(rz, 4, "Z") @ Matrix.Scale(s, 4))


def build(r):
    rng = random.Random(7)
    pv = r["preview"]
    cols = GB.collections()
    yaw = math.degrees(SM.yaw)
    mats = K.materials(arch=dict(lacquer="vermilion"),
                       banners=["cinnabar", "gold", "cinnabar", "white", "vermilion", "malachite"])
    mats["Sail"] = GB.lattice("GB_Title_Sail", "#C8A878")
    land = LD.qinglv("GB_Title_Land", z0=12.0, z1=820.0, cun=0.95, cun_px=6.0, cun_len=120.0,
                     moss_px=9.0, moss=0.8, var_scale=0.002, near=300.0, far=6000.0, plain_h=0.025,
                     plain=("#C8CCA0", "#D4CA9E"), plain_bare=0.35, steep=(0.1, 0.4), shadow_cun=0.45,
                     ribs=True, z1_near=(1000.0, 3000.0, 210.0))
    fpx = FOCAL / 36.0 * 1920.0
    peaks_w = SM.peaks(PEAKS)
    na, nd = (560, 360) if pv else (1000, 640)
    LD.fan_terrain("Land", CAM[:2], yaw, 58.0, 250.0, 12000.0, na, nd, height, land, cols["land"],
                   attrs={"rib": lambda X, Y: LD.peak_ribs(X, Y, peaks_w, CAM[:2], fpx, 6.0)})
    water = LD.water("GB_Title_Water", cover=0.32, spacing_px=9.0, wave_px=170.0, amp=0.4, gaps=0.85,
                     gap_len=180.0, lines=0.38, near=300.0, far=6000.0, grade=(700.0, 3000.0),
                     cam_h=CAM[2], d_ref=1300.0, net=0.25)
    wm = MeshBuilder()
    wm.box((0, 4000, -0.2), (16000, 11000, 0.2), "Water", skip=("bottom",))
    wm.build("Water", {"Water": water}, col=cols["water"])

    def ground(x, y):
        return float(height(np.array([[x]]), np.array([[y]]))[0, 0])

    # ---- the fortress city on its terrace ----------------------------------------------------
    c = city_center()
    CITY = (c.x, c.y, 16.0)
    cmb, ctrees = K.city(3, at=CITY, rz=math.radians(CITY_RZ), scale=CITY_SCALE)
    K.emit(cmb, "City", mats, "arch")
    cam_dir = Vector(TARGET) - Vector(CAM)
    tmb = MeshBuilder()
    K.trees(tmb, ctrees, rng, cam_dir=cam_dir, size=1.0, low=True)
    bmb = MeshBuilder()
    M = Matrix.Translation(Vector(CITY)) @ Matrix.Rotation(math.radians(CITY_RZ), 4, "Z") @ Matrix.Scale(CITY_SCALE, 4)
    for i, x in enumerate((-46, -36, -26, 26, 36, 46)):
        p = M @ Vector((x, -44.0, 10.0))
        K.banner(bmb, rng, color=[0, 2, 4][i % 3], at=tuple(p), height=16.0, cloth=(5.5, 9.0))
    for x in (-50, 50):
        for y in (-25, 0, 25):
            p = M @ Vector((x, y, 10.0))
            K.banner(bmb, rng, color=0, at=tuple(p), height=14.0, cloth=(5.0, 8.0))
    for x in (-14, 14):
        p = M @ Vector((x, -66.0, 0.0))
        K.banner(bmb, rng, color=1, at=tuple(p), height=24.0, cloth=(6.0, 10.0))
    K.emit(bmb, "Banners", mats, "fig")
    # ---- groves and pines --------------------------------------------------------------------
    pl = []
    for (sx, sy, d, rad, n) in ((0.80, 0.585, 1180, 70, 18), (0.47, 0.60, 1400, 50, 10),
                                (0.72, 0.50, 1500, 90, 16), (0.88, 0.53, 1250, 80, 16),
                                (0.58, 0.47, 1750, 80, 14), (0.97, 0.60, 1000, 60, 12),
                                (0.66, 0.58, 1350, 60, 12)):
        x, y, _ = SM.at(sx, sy, d)
        if pv:
            n = max(3, n // 2)
        pl += K.grove(rng, (x, y), rad, n, ground=ground, kinds=("Leaf", "LeafDark", "pine", "LeafDark"))
    # pines in clusters along the ridges of the massif
    for _ in range(46 if not pv else 20):
        sx, sy = rng.uniform(0.48, 1.0), rng.uniform(0.06, 0.45)
        cx_, cy_, _ = SM.at(sx, sy, rng.uniform(1600, 3000))
        if ground(cx_, cy_) < 120:
            continue
        for k in range(rng.randint(4, 9)):
            x, y = cx_ + rng.uniform(-45, 45), cy_ + rng.uniform(-30, 30)
            z = ground(x, y)
            if z > 100:
                pl.append((rng.choice(("pine", "pine", "LeafDark")), (x, y, z - 1.0), rng.uniform(0.9, 1.5)))
    for (sx, sy, d, rad, n) in ((0.80, 0.70, 950, 60, 14), (0.70, 0.80, 850, 50, 10), (0.88, 0.62, 1050, 60, 12)):
        x, y, _ = SM.at(sx, sy, d)
        pl += K.grove(rng, (x, y), rad, n if not pv else n // 2, ground=ground, kinds=("Leaf", "LeafDark", "pine"))
    # a riverside village with willows below the city
    vil = MeshBuilder()
    for k in range(14 if not pv else 7):
        p = SM.ground(rng.uniform(0.48, 0.56), rng.uniform(0.80, 0.92), z=0.0)
        z = ground(p[0], p[1])
        if z < 2.0:
            continue
        K.cottage(vil, at=(p[0], p[1], z), rz=math.radians(CITY_RZ) + rng.choice((0.0, math.pi / 2)),
                  w=rng.uniform(9.0, 13.0), d=6.5, h=4.0, thatch=rng.random() < 0.5)
        pl.append(("willow", (p[0] + rng.uniform(-12, 12), p[1] + rng.uniform(-12, 12), z), rng.uniform(1.0, 1.3)))
    K.emit(vil, "Village", mats, "arch")
    K.trees(tmb, pl, rng, cam_dir=cam_dir, size=1.3, low=True)
    # the foreground bank: big gnarled pines reaching over the water
    # the foreground crag on the right edge: lumpy rocks rising to a ledge with gnarled pines
    crag = []
    for (sx, d, sz, seed) in ((0.975, 930.0, (150, 120, 230), 1), (1.04, 900.0, (160, 120, 300), 2),
                              (0.92, 960.0, (110, 90, 120), 3), (0.95, 880.0, (130, 100, 90), 4),
                              (1.08, 1000.0, (170, 130, 360), 5), (0.89, 900.0, (90, 70, 55), 6)):
        x, y, _ = SM.at(sx, 0.5, d)
        crag.append((x, y, sz, seed))
    for (x, y, s_, reach, dz) in ((crag[0][0], crag[0][1], 1.7, (-1.0, 0.1), 225.0),
                                  (crag[1][0] - 20, crag[1][1], 1.4, (-1.0, -0.3), 290.0),
                                  (crag[2][0], crag[2][1], 1.2, (-1.0, 0.3), 115.0)):
        from ironart import scenes_gongbi_flora as F
        F.pine(tmb, random.Random(int(abs(x))), height=34.0 * s_, lean=0.8, limbs=6,
               at=(x, y, ground(x, y) - 10.0 + dz), cam_dir=cam_dir, reach=reach, crown=1.2)
    K.emit(tmb, "Trees", mats, "tree")
    # the foreground bank: a cluster of lumpy 青绿 rocks (ochre below, malachite on the tops)
    rk = LD.rock("GB_Title_Rock", color="#CDB48C", deep="#8E7458", cun=0.85, scale=0.09, freq=4.0,
                 ochre=0.35, moss=0.6, near=200.0, far=1600.0, top="malachite", top_amount=0.9)
    rmb = MeshBuilder()
    for (x, y, sz, seed) in crag:
        LD.boulder(rmb, (x, y, ground(x, y) - 10.0), sz, random.Random(seed), "Rock", lumps=7,
                   seg=(22, 16), spread=0.45, rough=0.16)
    # an islet with a pavilion on the calm water
    smb = MeshBuilder()
    ix, iy, _ = SM.at(0.33, 0.5, 2100)
    rr = random.Random(9)
    for (dx, dy, h, rad) in ((0, 0, 26, 32), (36, 10, 14, 20), (-30, 6, 10, 16)):
        LD.boulder(rmb, (ix + dx, iy + dy, -6.0), (rad * 2.0, rad * 1.6, h + 6.0), rr, "Rock", lumps=5, seg=(18, 10))
    K.pavilion(smb, at=(ix, iy, 24.0), n=6, R=5.0, col_h=5.5, roof_h=4.5)
    isl = []
    for (dx, dz, sc) in ((-16, 20, 1.2), (18, 20, 1.0), (38, 12, 0.9)):
        isl.append(("pine", (ix + dx, iy + 4, dz), sc))
    tmb2 = MeshBuilder()
    K.trees(tmb2, isl, rr, cam_dir=cam_dir, size=1.0)
    K.emit(tmb2, "IsletTrees", mats, "tree")
    K.emit(rmb, "Rocks", dict(Rock=rk), "land")
    # sails on the river
    for (sx, sy, rz, s) in ((0.22, 0.80, 1.45, 2.6), (0.37, 0.66, -1.3, 2.3), (0.08, 0.62, 1.6, 2.1)):
        p = SM.ground(sx, sy, z=0.0)
        sail_boat(smb, (p[0], p[1], -0.4), rz, s)
    K.emit(smb, "Boats", mats, "arch")
    cam = L.camera(CAM, TARGET, focal_mm=FOCAL)
    look = dict(
        sky=dict(stops=[(0.0, "azurite_l", 0.24), (0.12, "azurite_l", 0.08), (0.3, "silk", 0.0)]),
        fade=dict(d0=1100.0, d1=8000.0, color=GB.mixc("silk", "azurite_l", 0.2), amount=0.8,
                  gamma=0.8, cover=0.5),
        mist=[
            # across the foot of the massif, behind the city
            dict(y=(0.425, 0.50), soft=0.02, jitter=0.02, dist_min=1400.0, x=(0.44, 1.2), amount=1.0,
                 noise_px=220, holes=0.15),
            # half-way up the massif
            dict(y=(0.255, 0.31), soft=0.018, jitter=0.02, dist_min=2000.0, x=(0.45, 1.2), amount=0.95,
                 noise_px=200, holes=0.3),
            # the far shore and the river's vanishing reach
            dict(y=(0.345, 0.41), soft=0.02, jitter=0.015, dist_min=3800.0, amount=1.0, noise_px=260,
                 holes=0.1),
            # the far ranges' feet
            dict(y=(0.16, 0.22), soft=0.025, jitter=0.02, dist_min=5000.0, amount=0.9, noise_px=240,
                 holes=0.2),
        ],
        shore=dict(z=0.0, width=1.0, alpha=0.65, eps=0.08),
        ink=1.0,
        kinds={"land": dict(near=500.0, far=8000.0, w=1.15, wfar=0.5, afar=0.45, t_sil=0.012),
               "tree": dict(near=500.0, far=4000.0, w=0.7, wfar=0.6, afar=0.5),
               "arch": dict(near=600.0, far=2500.0, w=0.62, wfar=0.75, afar=0.75),
               "fig": dict(near=600.0, far=2500.0, w=0.55, wfar=0.75, afar=0.75)},
    )

    def paint2d(cv, r):
        # a skein of wild geese crossing the calm sky on the left
        rr = np.random.default_rng(5)
        with cv.paint("sky", "ink", 0.75) as d:
            for i in range(11):
                x = 0.12 + i * 0.015 + rr.uniform(-0.003, 0.003)
                y = 0.15 + abs(i - 4) * 0.008 + rr.uniform(-0.002, 0.002)
                s = 0.004
                d.stroke([(x - s, y - s * 0.9), (x, y), (x + s, y - s * 1.0)], 1.2, "flat")
    return dict(camera=cam, look=look, paint2d=paint2d,
                notes="menu area: left 40% (x < 768 px at 1x) is open water, mist, low far hills and geese")
