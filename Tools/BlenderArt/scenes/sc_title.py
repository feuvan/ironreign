"""Title background: an epic blue-green landscape (青绿山水) - a fortress city on the shore of a
river below a towering massif, bands of bare-silk mist, banners on the walls, far ranges fading
into the silk.  The left ~40 % (menu side) stays calm: open water, a far shore of low hills
(平远), mist and a skein of geese.

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
            size=(1920, 1080), k=2, m=2, seed=7, spp=10, preview_spp=6)

CAM = (0.0, -800.0, 170.0)
TARGET = (180.0, 600.0, 120.0)
FOCAL = 40.0
SM = K.ScreenMap(CAM, TARGET, FOCAL)
CITY_S = (0.615, 0.60, 1050.0)
CITY_RZ = -16.0
SHORE_SX = 0.455

# (sx, sy of the summit, horizontal distance m, radius m, shape)
PEAKS = [
    # the massif (高远)
    (0.70, 0.08, 2700, 560, 0.85), (0.835, 0.15, 2350, 460, 0.9), (0.585, 0.19, 2300, 430, 1.0),
    (0.95, 0.25, 2050, 380, 1.0), (0.50, 0.31, 2600, 420, 1.2), (0.765, 0.27, 2000, 300, 1.1),
    (0.66, 0.35, 1750, 330, 1.5), (0.89, 0.38, 1550, 300, 1.4), (0.54, 0.40, 1800, 260, 1.6),
    # shoulders right behind the city
    (0.74, 0.50, 1300, 220, 1.9), (0.52, 0.505, 1350, 180, 1.8),
    # the foreground bank (rocks and pines on it, see build)
    (0.97, 0.74, 640, 170, 2.6),
    # far shore on the left (平远) - low, wide
    (0.10, 0.385, 5400, 950, 2.2), (0.25, 0.37, 6600, 1200, 2.0), (0.36, 0.40, 4800, 700, 2.0),
    (0.02, 0.36, 7600, 1300, 1.8),
    # far ranges glimpsed behind the massif
    (0.42, 0.22, 7200, 1500, 1.0), (1.0, 0.10, 6800, 1500, 1.0),
]


def height(X, Y):
    peaks = SM.peaks(PEAKS)
    Hh = LD.peak_field(X, Y, peaks, seed=7, ridge=0.4, ridge_scale=200.0, softmax=4.0)
    from ironart.scenes_terrain import fbm2
    sx = SM.sx(X, Y)
    d = SM.dist(X, Y)
    n = fbm2(X, Y, 260.0, 4, seed=11) - 0.5
    # land / water: water left of the shore line near and middle distance; far on, a river
    # winding away between the far shore and the massif
    shore = SHORE_SX + n * 0.05 - 0.02 * np.clip((d - 600) / 900, 0, 1)
    land_near = np.clip((sx - shore) / 0.025, 0, 1)
    rv = 0.43 + 0.03 * np.sin(d / 900.0) + n * 0.02
    river = 1.0 - np.clip((np.abs(sx - rv) - 0.012 * 3000 / np.maximum(d, 1)) / 0.01, 0, 1)
    far_land = np.clip((d - 3000.0) / 600.0, 0, 1) * (1.0 - river)
    land = np.maximum(land_near, far_land)
    plain = 6.0 + np.clip(fbm2(X, Y, 400.0, 3, seed=5) - 0.45, 0, 1) * 30.0
    base = plain * land - 6.0 * (1.0 - land)
    Hh = np.maximum(base, Hh * np.maximum(land, (Hh > 40).astype(np.float64)) + base * (Hh <= 40))
    # city terrace
    cx, cy, cz = SM.at(CITY_S[0], CITY_S[1], CITY_S[2])
    rc = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
    f = np.clip((rc - 165.0) / 80.0, 0.0, 1.0)
    f = f * f * (3 - 2 * f)
    Hh = Hh * f + 12.0 * (1 - f)
    return Hh


def build(r):
    rng = random.Random(7)
    pv = r["preview"]
    cols = GB.collections()
    yaw = math.degrees(SM.yaw)
    mats = K.materials(arch=dict(lacquer="vermilion"),
                       banners=["cinnabar", "gold", "cinnabar", "white", "vermilion", "malachite"])
    land = LD.qinglv("GB_Title_Land", z0=15.0, z1=650.0, cun=0.75, cun_px=7.0, cun_len=110.0,
                     moss_px=10.0, var_scale=0.002, near=300.0, far=5000.0, plain_h=0.03, ribs=True)
    fpx = FOCAL / 36.0 * 1920.0
    peaks_w = SM.peaks(PEAKS)
    na, nd = (520, 320) if pv else (900, 560)
    LD.fan_terrain("Land", CAM[:2], yaw, 50.0, 200.0, 12000.0, na, nd, height, land, cols["land"],
                   attrs={"rib": lambda X, Y: LD.peak_ribs(X, Y, peaks_w, CAM[:2], fpx, 7.0)})
    water = LD.water("GB_Title_Water", cover=0.3, spacing_px=8.0, wave_px=150.0, amp=0.45, gaps=0.85,
                     gap_len=160.0, lines=0.55, near=300.0, far=5000.0, grade=(600.0, 2500.0),
                     cam_h=CAM[2], d_ref=1200.0)
    wm = MeshBuilder()
    wm.box((0, 4000, -0.2), (16000, 11000, 0.2), "Water", skip=("bottom",))
    wm.build("Water", {"Water": water}, col=cols["none"])

    def ground(x, y):
        return float(height(np.array([[x]]), np.array([[y]]))[0, 0])

    # ---- the fortress city on its terrace ----------------------------------------------------
    cx, cy, _ = SM.at(CITY_S[0], CITY_S[1], CITY_S[2])
    CITY = (cx, cy, 12.0)
    cmb, ctrees = K.city(3, at=CITY, rz=math.radians(CITY_RZ), scale=1.9)
    K.emit(cmb, "City", mats, "arch")
    cam_dir = Vector(TARGET) - Vector(CAM)
    tmb = MeshBuilder()
    K.trees(tmb, ctrees, rng, cam_dir=cam_dir, size=1.0, low=True)
    bmb = MeshBuilder()
    M = Matrix.Translation(Vector(CITY)) @ Matrix.Rotation(math.radians(CITY_RZ), 4, "Z") @ Matrix.Scale(1.9, 4)
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
    for (sx, sy, d, rad, n) in ((0.78, 0.55, 1150, 70, 16), (0.50, 0.555, 1250, 60, 12),
                                (0.70, 0.47, 1500, 90, 14), (0.86, 0.50, 1250, 80, 14),
                                (0.60, 0.44, 1700, 80, 12), (0.97, 0.56, 1000, 70, 12),
                                (0.34, 0.48, 1900, 25, 5)):
        x, y, _ = SM.at(sx, sy, d)
        if pv:
            n = max(3, n // 2)
        pl += K.grove(rng, (x, y), rad, n, ground=ground, kinds=("Leaf", "LeafDark", "pine", "LeafDark"))
    for _ in range(90 if not pv else 40):
        sx, sy = rng.uniform(0.5, 1.0), rng.uniform(0.15, 0.45)
        x, y, _ = SM.at(sx, sy, rng.uniform(1700, 2600))
        z = ground(x, y)
        if z > 150:
            pl.append(("pine", (x, y, z - 1.0), rng.uniform(1.0, 1.5)))
    K.trees(tmb, pl, rng, cam_dir=cam_dir, size=1.3, low=True)
    # the foreground crag: big gnarled pines
    fg = []
    for (sx, d, s, dz) in ((0.965, 620, 2.0, 76.0), (0.90, 650, 1.6, 52.0), (0.86, 700, 1.5, 0.0), (1.03, 640, 1.4, 57.0)):
        x, y, _ = SM.at(sx, 0.5, d)
        fg.append(("pine", (x, y, ground(x, y) + dz), s))
    K.trees(tmb, fg, rng, cam_dir=cam_dir, size=1.0)
    K.emit(tmb, "Trees", mats, "tree")
    # the foreground bank: a cluster of rocks (斧劈 facets, malachite on the tops) among the pines
    rk = LD.rock("GB_Title_Rock", color="#C8AE88", deep="#8E7458", cun=0.8, scale=0.12, freq=4.0,
                 ochre=0.4, moss=0.6, near=200.0, far=1600.0, top="malachite", top_amount=0.85)
    rmb = MeshBuilder()
    for (sx, d, h, rad, seed) in ((0.90, 650, 55, 38, 1), (0.965, 620, 80, 45, 2), (1.03, 640, 60, 40, 3),
                                  (0.84, 700, 28, 26, 4), (0.93, 600, 30, 22, 5), (0.995, 590, 34, 24, 6)):
        x, y, _ = SM.at(sx, 0.5, d)
        g = ground(x, y)
        rr = random.Random(seed)
        n = 14
        outline = []
        for i in range(n):
            a = -i / n * math.tau
            rad_i = rad * rr.uniform(0.8, 1.15)
            outline.append((x + math.cos(a) * rad_i, y + math.sin(a) * rad_i * 0.8))
        LD.rock_mass(rmb, outline, g - 4.0, g + h, "Rock", rr, rings=6, jag=0.22, taper=0.35,
                     lean=(0.0, 0.0), bulge=0.12)
    # a pavilion on the islet, and a lone boat on the calm water
    smb = MeshBuilder()
    from ironart import world_kit as WK
    ix, iy, _ = SM.at(0.335, 0.5, 1900)
    irb = MeshBuilder()
    rr = random.Random(9)
    for (dx, dy, h, rad) in ((0, 0, 26, 30), (34, 10, 14, 20), (-28, 6, 10, 16)):
        outline = [(ix + dx + math.cos(-i / 12 * math.tau) * rad * rr.uniform(0.8, 1.15),
                    iy + dy + math.sin(-i / 12 * math.tau) * rad * 0.8 * rr.uniform(0.8, 1.15)) for i in range(12)]
        LD.rock_mass(irb, outline, -4.0, h, "Rock", rr, rings=5, jag=0.2, taper=0.3, bulge=0.15)
    s0 = smb.n
    WK.hall(smb, (0, 0, 0), WK.HallSpec(bays=(1, 1), bay=6.0, col_h=4.5, plat_h=0.8, front="open",
                                        brackets=False, roof=WK.RoofSpec(style="pyramid", overhang=1.6, tiles=False)))
    smb.transform(s0, Matrix.Translation((ix, iy, 26.0)) @ Matrix.Scale(1.4, 4))
    isl = []
    for (dx, dz, sc) in ((-14, 22, 1.2), (16, 22, 1.0), (36, 13, 0.9)):
        isl.append(("pine", (ix + dx, iy + 4, dz), sc))
    K.trees(tmb2 := MeshBuilder(), isl, rr, cam_dir=cam_dir, size=1.0)
    K.emit(tmb2, "IsletTrees", mats, "tree")
    rmb.extend(irb)
    K.emit(rmb, "Crag", dict(Rock=rk), "land")
    bx, by, _ = SM.at(0.24, 0.72, 820)
    smb.box((bx, by, 0.0), (3.0, 9.0, 1.2), "Wood")
    smb.box((bx, by - 0.5, 1.2), (2.4, 3.2, 1.6), "Straw")
    smb.box((bx, by + 3.6, 1.2), (0.15, 0.15, 3.2), "Wood")
    K.emit(smb, "Boats", mats, "arch")
    cam = L.camera(CAM, TARGET, focal_mm=FOCAL)
    look = dict(
        sky=dict(stops=[(0.0, "azurite_l", 0.22), (0.14, "azurite_l", 0.08), (0.36, "silk", 0.0)]),
        fade=dict(d0=1000.0, d1=7500.0, color=GB.mixc("silk", "azurite_l", 0.22), amount=0.82,
                  gamma=0.75, cover=0.5),
        mist=[
            # across the foot of the massif, behind the city
            dict(y=(0.405, 0.47), soft=0.02, jitter=0.02, dist_min=1250.0, x=(0.42, 1.2), amount=1.0,
                 noise_px=220, holes=0.15),
            # half-way up the massif
            dict(y=(0.255, 0.30), soft=0.018, jitter=0.02, dist_min=1900.0, x=(0.45, 1.2), amount=0.95,
                 noise_px=200, holes=0.3),
            # far shore and the river's vanishing reach
            dict(y=(0.355, 0.41), soft=0.02, jitter=0.015, dist_min=3500.0, amount=1.0, noise_px=260,
                 holes=0.1),
            # the far ranges' feet
            dict(y=(0.18, 0.235), soft=0.025, jitter=0.02, dist_min=5000.0, amount=0.9, noise_px=240,
                 holes=0.2),
        ],
        shore=dict(z=0.0, width=1.1, alpha=0.7, eps=0.05),
        ink=1.0,
    )

    def paint2d(cv, r):
        # a skein of wild geese crossing the calm sky on the left
        rr = np.random.default_rng(5)
        with cv.paint("sky", "ink", 0.75) as d:
            for i in range(9):
                x = 0.12 + i * 0.016 + rr.uniform(-0.003, 0.003)
                y = 0.17 + abs(i - 3) * 0.009 + rr.uniform(-0.002, 0.002)
                s = 0.0045
                d.stroke([(x - s, y - s * 0.9), (x, y), (x + s, y - s * 1.0)], 1.3, "flat")
    return dict(camera=cam, look=look, paint2d=paint2d,
                ink={"land": dict(dist=(300.0, 8000.0, 0.55, 0.5), t=1.6),
                     "tree": dict(dist=(300.0, 4000.0, 0.6, 0.5))},
                notes="menu area: left 40% (x < 768 px at 1x) is open water, mist, low far hills and geese")
