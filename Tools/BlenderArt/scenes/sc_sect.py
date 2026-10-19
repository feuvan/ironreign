"""Event: Sect - a cliff temple above the clouds, disciples training at dawn.

A sea of clouds at sunrise: on a pinnacle at the left a temple of vermilion halls and green tiles
with a pagoda clings to the summit; in the right foreground, on a paved terrace with a marble
balustrade on its own crag, rows of disciples in pale robes practise sword forms before their
master.  Far pinnacles rise through the clouds; the sun lifts out of the cloud sea."""

import math
import random

import numpy as np
from mathutils import Matrix, Vector

from ironart import scenes_gongbi as GB
from ironart import scenes_gongbi_kit as K
from ironart import scenes_gongbi_land as LD
from ironart import scenes_gongbi_flora as F
from ironart import scenes_look as L
from ironart import world_kit as WK
from ironart.geometry import MeshBuilder

SPEC = dict(name="Sect", art="Art/Events/Sect.png", master="Events/Sect@2x.png",
            size=(640, 360), k=4, m=2, seed=61, spp=12, preview_spp=6)

CAM = (2.0, -14.0, 6.0)
TARGET = (-6.0, 100.0, 14.0)
FOCAL = 30.0
SM = K.ScreenMap(CAM, TARGET, FOCAL)
BASE = 400.0
SUN = (0.80, 0.40)
TEMPLE_S = (0.32, 0.17, 170.0)          # summit of the temple crag (screen x, y, distance)
# pinnacles: (sx, sy of the summit, d, radius, shape)
PEAKS = [(0.08, 0.36, 300.0, 40.0, 0.6), (0.55, 0.30, 420.0, 50.0, 0.55),
         (0.64, 0.38, 650.0, 80.0, 0.6), (0.78, 0.34, 1000.0, 120.0, 0.6), (0.03, 0.30, 900.0, 110.0, 0.6),
         (0.94, 0.40, 1400.0, 180.0, 0.7), (0.44, 0.38, 1700.0, 220.0, 0.7)]


def peaks_b():
    return [(x, y, z + BASE, r, sh) for (x, y, z, r, sh) in SM.peaks(PEAKS)]


def height(X, Y):
    return LD.peak_field(X, Y, peaks_b(), seed=61, ridge=0.5, ridge_scale=40.0, softmax=5.0) - BASE


def build(r):
    rng = random.Random(61)
    pv = r["preview"]
    cols = GB.collections()
    mats = K.materials(cloth=["white", "#C8C8C0", "azurite", "#3A3530", "ochre", "#E2D6BC",
                              "rouge", "teal", "#7A5A3A", "#D8D4C8", "vermilion", "indigo"],
                       arch=dict(lacquer="vermilion"))
    mats["Cloud"] = LD.cloud("GB_Sect_Cloud", color="white", deep="#E8C8A8", tint=0.45)
    crag = LD.qinglv("GB_Sect_Crags", z0=-120.0, z1=40.0, cun=0.8, cun_px=6.0, cun_len=30.0,
                     moss_px=8.0, var_scale=0.01, near=20.0, far=3000.0, plain_h=0.0, steep=(0.15, 0.5),
                     ribs=True)
    fpx = FOCAL / 36.0 * 640.0
    yaw = math.degrees(SM.yaw)
    LD.fan_terrain("Crags", CAM[:2], yaw, 64.0, 60.0, 4000.0, 460, 300, height, crag, cols["land"],
                   attrs={"rib": lambda X, Y: LD.peak_ribs(X, Y, peaks_b(), CAM[:2], fpx, 6.0)})

    def ground(x, y):
        return float(height(np.array([[x]]), np.array([[y]]))[0, 0])
    # ---- the temple crag: stacked rock masses, faceted (斧劈), blue-green on the ledges ---------
    tx, ty, tz = SM.at(*TEMPLE_S)
    tz = tz - 1.0
    cragm = LD.qinglv("GB_Sect_TempleCrag", z0=tz - 160.0, z1=tz, cun=0.85, cun_px=5.0, cun_len=20.0,
                      moss_px=8.0, var_scale=0.02, near=20.0, far=2000.0, plain_h=0.0, steep=(0.1, 0.4),
                      shadow_cun=0.3)
    cm_ = MeshBuilder()
    rr = random.Random(11)
    LD.pinnacle(cm_, (tx, ty + 6.0), 26.0, 13.0, tz - 230.0, tz, rr, mat="Crag", subs=6, jag=0.1)
    K.emit(cm_, "TempleCrag", dict(Crag=cragm), "land")
    tm = MeshBuilder()
    s0 = tm.n
    WK.hall(tm, (0, 2.0, 0), WK.HallSpec(bays=(3, 2), bay=3.4, col_h=3.6, plat_h=0.9, double=True, upper_h=2.4,
                                         roof=WK.RoofSpec(style="hip_gable", mat="W_TileGreen", ridge_mat="W_RidgeGreen",
                                                          overhang=1.3, lift=0.6, flare=0.3)))
    WK.pagoda(tm, (-9.0, 6.0, 0), tiers=7, R=2.2, base_h=2.4, tier_h=1.7)
    for sx_ in (-1, 1):
        s1 = tm.n
        WK.hall(tm, (0, 0, 0), WK.HallSpec(bays=(2, 1), bay=3.0, col_h=2.8, plat_h=0.5, steps=False,
                                           roof=WK.RoofSpec(style="hip_gable", mat="W_TileGreen", ridge_mat="W_RidgeGreen",
                                                            overhang=1.0, lift=0.4)))
        tm.transform(s1, Matrix.Translation((sx_ * 9.0, -2.0, 0)) @ Matrix.Rotation(sx_ * 0.35, 4, "Z"))
    tm.transform(s0, Matrix.Translation((tx, ty, tz)) @ Matrix.Rotation(math.radians(-15), 4, "Z"))
    K.emit(tm, "Temple", mats, "arch")
    # ---- the training terrace on its own crag (right foreground) -----------------------------
    ter = MeshBuilder()
    cx, cy, _ = SM.at(0.72, 0.5, 24.0)
    cz = 0.0
    WK.platform(ter, 22.0, 15.0, 1.0, "W_Marble", "W_Paving", z0=cz - 1.0, skirt=0.3)
    WK.balustrade_rect(ter, 21.6, 14.6, cz, gap=0.0, mat="W_Marble", h=0.9)
    ter.transform(0, Matrix.Translation((cx, cy, 0.0)) @ Matrix.Rotation(math.radians(-25), 4, "Z"))
    K.emit(ter, "Terrace", mats, "arch")
    rock = LD.rock("GB_Sect_Rock", color="#B8A888", deep="#7A6A50", cun=0.85, scale=0.25, freq=4.0,
                   ochre=0.4, moss=0.6, near=10.0, far=400.0, top="malachite", top_amount=0.8)
    rm = MeshBuilder()
    rr = random.Random(3)
    outline = [(cx + math.cos(-i / 14 * math.tau) * 14.0 * rr.uniform(0.85, 1.1),
                cy + math.sin(-i / 14 * math.tau) * 11.0 * rr.uniform(0.85, 1.1)) for i in range(14)]
    LD.rock_mass(rm, outline, -140.0, -4.5, "Rock", rr, rings=9, jag=0.12, taper=-0.45, bulge=0.05, top_noise=0.0)
    K.emit(rm, "TerraceCrag", dict(Rock=rock), "land")
    # disciples in rows, their master facing them
    ppl = MeshBuilder()
    R = Matrix.Rotation(math.radians(-25), 4, "Z")
    poses = ["sword_ready", "slash_high", "guard", "thrust"]
    for row in range(3):
        for col_ in range(5):
            lx = -6.0 + col_ * 3.0
            ly = -2.0 + row * 2.8
            p = Vector((cx, cy, 0)) + R @ Vector((lx, ly, 0))
            pose = poses[(row + col_) % 2] if row != 1 else poses[2 + col_ % 2]
            K.person(ppl, random.Random(row * 10 + col_), pose, "disciple", at=tuple(p), rz=math.radians(-25 + 180 + 15),
                     cloth=0 if row % 2 == 0 else 9, cloth2=2, hat="topknot", weapon="sword", jitter=2.0)
    p = Vector((cx, cy, 0)) + R @ Vector((1.0, -5.6, 0))
    K.person(ppl, random.Random(99), "stand_hands", "robe", at=tuple(p), rz=math.radians(-25),
             cloth=2, cloth2=9, hat="guan", jitter=0.0)
    K.emit(ppl, "Disciples", mats, "fig", thin=K.THIN)
    # pines on the crags
    pm = MeshBuilder()
    cam_dir = Vector(TARGET) - Vector(CAM)
    for (x, y, z, h, reach) in ((tx - 11.0, ty + 4.0, tz - 0.6, 8.0, (-1, -0.2)), (tx + 12.0, ty + 8.0, tz - 0.6, 7.0, (1, -0.2)),
                                (tx - 3.0, ty - 8.0, tz - 0.6, 5.0, (0, -1))):
        F.pine(pm, random.Random(int(x * 10) % 97), height=h, lean=0.8, limbs=5, at=(x, y, z), cam_dir=cam_dir,
               crown=1.2, reach=reach, pad=h * 0.11)
    tp = Vector((cx, cy, 0)) + R @ Vector((10.5, 4.0, 0))
    F.pine(pm, random.Random(5), height=6.5, lean=0.9, limbs=6, at=(tp.x, tp.y, -0.6), cam_dir=cam_dir, crown=1.3,
           reach=(1.0, 0.3), pad=0.7)
    K.emit(pm, "Pines", mats, "tree")
    cam = L.camera(CAM, TARGET, focal_mm=FOCAL)
    look = dict(
        sky=dict(stops=[(0.0, "azurite_l", 0.3), (0.2, "#C8C8C0", 0.15), (0.34, "#F0C890", 0.35),
                        (0.42, "#E8A070", 0.38), (0.5, "#F0D0A8", 0.2), (0.7, "silk", 0.0)]),
        fade=dict(d0=200.0, d1=2500.0, color=GB.mixc("silk", "#F0D0A8", 0.4), amount=0.8, gamma=0.7, cover=0.5),
        mist=[dict(y=(0.56, 1.3), scallop=24.0, dist_min=50.0, line=0.55, line_px=1.0),
              dict(y=(0.48, 0.60), scallop=17.0, dist_min=150.0, line=0.45, line_px=0.9, x=(-0.1, 0.75)),
              dict(y=(0.41, 0.50), scallop=12.0, dist_min=400.0, line=0.35, line_px=0.8),
              dict(y=(0.31, 0.37), soft=0.02, jitter=0.02, dist_min=700.0, amount=0.9, noise_px=120, holes=0.3)],
        mist_tint=("#F6E8D2", 0.3),
    )

    def paint2d(cv, r):
        from ironart import scenes_gongbi_2d as G2
        G2.sun(cv, SUN, 16.0, color="#E07040", alpha=0.8, halo_color="#F0B880", halo=0.3)
        rr = np.random.default_rng(61)
        with cv.paint("sky", "ink", 0.65) as d:
            for i in range(5):
                x = 0.55 + i * 0.035 + rr.uniform(-0.01, 0.01)
                y = 0.16 + rr.uniform(-0.02, 0.02)
                s = 0.006
                d.stroke([(x - s, y - s * 0.6), (x, y), (x + s, y - s * 0.7)], 1.0, "flat")
    return dict(camera=cam, look=look, paint2d=paint2d, notes="temple upper left, disciples right, sun right")
