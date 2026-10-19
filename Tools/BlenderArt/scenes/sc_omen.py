"""Event: Omen - a red comet over a dark capital.

Night over the imperial capital seen from the palace wall: the roofs of halls, gate towers and a
pagoda stand as dark ink-washed shapes with a few lit lanterns; a great broom star in cinnabar
sweeps across an ink-blue sky stained red around it; on the wall walk in the foreground the court
astronomer points it out to anxious officials."""

import math
import random

import numpy as np
from mathutils import Matrix, Vector

from ironart import scenes_gongbi as GB
from ironart import scenes_gongbi_kit as K
from ironart import scenes_gongbi_land as LD
from ironart import scenes_look as L
from ironart import world_city as WC
from ironart import world_kit as WK
from ironart.geometry import MeshBuilder

SPEC = dict(name="Omen", art="Art/Events/Omen.png", master="Events/Omen@2x.png",
            size=(640, 360), k=4, m=2, seed=121, spp=12, preview_spp=6)

CAM = (-10.0, -70.0, 26.0)
TARGET = (10.0, 120.0, 16.0)
FOCAL = 30.0
SM = K.ScreenMap(CAM, TARGET, FOCAL)
HILLS = [(0.10, 0.36, 2500, 900, 1.6), (0.45, 0.35, 3500, 1100, 1.5), (0.85, 0.34, 2800, 900, 1.6)]


def height(X, Y):
    peaks = SM.peaks(HILLS)
    return np.maximum(LD.peak_field(X, Y, peaks, seed=121, ridge=0.3, ridge_scale=300.0, softmax=4.0), 0.0)


def build(r):
    rng = random.Random(121)
    pv = r["preview"]
    cols = GB.collections()
    # night versions of the architecture colours: ink-dimmed minerals
    mats = K.materials(cloth=["#5A3A34", "#2E3A4E", "#3E4E44", "#2A2622", "#8A7040", "#B8B0A0",
                              "#5A2E38", "#2E4A4A", "#4A3A2A", "#C8C0B0", "#8A3A28", "#22283A"],
                       arch=dict(lacquer="#8A3A2A", lacquer_d="#5A2018", wall="#6A2A22", bracket="#2E4A40",
                                 beam="#2A3E58", tile="#3A4044", stone="#6A665E", plaster="#9A9284",
                                 marble="#A8A498", paving="#8A8478", brick="#6A6458"))
    land = LD.qinglv("GB_Omen_Land", z0=0.0, z1=900.0, cun=0.6, cun_px=7.0, cun_len=60.0, moss_px=10.0,
                     var_scale=0.003, near=200.0, far=5000.0, plain_h=0.01, foot="#4E4A40", low="#4A4A42",
                     mid="#2E4440", top="#2A3448", light_top="#4E5A66", plain=("#5A5848", "#4E4C40"),
                     plain_bare=0.0, ribs=False)
    yaw = math.degrees(SM.yaw)
    LD.fan_terrain("Land", CAM[:2], yaw, 60.0, 20.0, 9000.0, 420, 260, height, land, cols["land"])
    # the capital: palace city and districts (world model tier 3), and the wall we stand on
    cmb, ctrees = K.city(3, at=(18.0, 150.0, 0.0), rz=math.radians(-8.0), scale=1.35)
    K.emit(cmb, "Capital", mats, "arch")
    tm = MeshBuilder()
    K.trees(tm, ctrees, rng, cam_dir=Vector(TARGET) - Vector(CAM), size=1.0, low=True)
    K.emit(tm, "Trees", mats, "tree")
    wall = MeshBuilder()
    w = WC.p_wall(8.0, 12.0, 10.0, mat="W_StoneDark")
    for i in range(-6, 7):
        wall.extend(w, Matrix.Translation((i * 8.0, -40.0, 12.0)) @ Matrix.Rotation(math.pi, 4, "Z") @ Matrix.Translation((0, 0, -12.0)))
    t = WC.p_corner_tower(12.0, 12.0)
    wall.extend(t, Matrix.Translation((-36.0, -40.0, 0.0)))
    K.emit(wall, "Wall", mats, "arch")
    # figures on the wall walk
    ppl = MeshBuilder()
    walk = 12.0 + 0.0
    K.person(ppl, random.Random(1), "point", "official", at=(-6.0, -42.0, walk), rz=math.radians(195),
             cloth=10, cloth2=9, hat="guan")
    for i, (x, y, pose, cl) in enumerate(((-3.5, -43.0, "bow_stand", 1), (-1.5, -41.6, "stand_hands", 0),
                                          (0.8, -42.6, "stand", 2), (-9.0, -41.0, "stand", 3))):
        K.person(ppl, random.Random(10 + i), pose, "official" if cl != 3 else "armored", at=(x, y, walk),
                 rz=math.radians(185 + rng.uniform(-20, 20)), cloth=cl, cloth2=9,
                 hat="official" if cl != 3 else "helmet", weapon="halberd" if cl == 3 else None)
    K.emit(ppl, "Watchers", mats, "fig", thin=K.THIN)
    cam = L.camera(CAM, TARGET, focal_mm=FOCAL)
    look = dict(
        sky=dict(stops=[(0.0, "#141A28", 0.92), (0.25, "#1E2434", 0.88), (0.42, "#3A2E36", 0.78), (0.55, "#4A3430", 0.6),
                        (1.0, "#2A2420", 0.55)]),
        fade=dict(d0=100.0, d1=3000.0, color="#5A5050", amount=0.6, gamma=0.8, cover=0.25),
        mist=[dict(y=(0.36, 0.42), soft=0.02, jitter=0.02, dist_min=600.0, amount=0.6, noise_px=110, holes=0.3)],
        mist_tint=("#6A5850", 0.7),
        tone=(0.9, 0.86, 0.86),
        shader_ink_color="#141210",
        ink=0.9,
    )

    def paint2d(cv, r):
        from ironart import scenes_gongbi_2d as G2
        # red stain in the sky around the comet
        with cv.paint("sky", "#8A2A20", 0.35, soft=60.0) as d:
            d.ellipse((0.42, 0.22), 230, 70)
        G2.comet(cv, (0.24, 0.12), (0.92, 0.28), 0.62, 9.0, color="cinnabar", core="#F6D8A0", rays=11, seed=7)
        # stars, faint
        rr = np.random.default_rng(121)
        with cv.paint("sky", "#D8D0C0", 0.55) as d:
            for i in range(70):
                d.disc((rr.uniform(0, 1), rr.uniform(0, 0.38)), rr.uniform(0.35, 0.8))
        # a few lit windows / lanterns in the city
        for i in range(24):
            x = rr.uniform(-20, 70)
            y = rr.uniform(110, 230)
            sx, sy, sz = L.screen_pos(cam, (x, y, rr.uniform(2.0, 6.0)))
            if sz <= 0 or not (0 < sx < 1 and 0 < sy < 1):
                continue
            with cv.paint("front", "#E8A050", 0.5, soft=1.5) as d:
                d.disc((sx, 1 - sy), 1.4)
    return dict(camera=cam, look=look, paint2d=paint2d, notes="comet across the top; no UI keep-out")
