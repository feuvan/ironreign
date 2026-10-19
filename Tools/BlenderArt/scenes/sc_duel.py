"""Duel background: two swordsmen face each other on a cliff edge at sunset, petals in the wind.

A rock plateau runs along the bottom of the picture and breaks off into a sea of evening cloud;
far peaks stand in rouge and azurite against a vermilion sky with a low sun.  The two duellists
stand at the left and right thirds in profile, blades drawn, cloaks streaming; a plum tree at
the left edge sheds petals that drift across the scene.  The centre (where the duel UI sits) is
kept to sky, cloud and distant peaks."""

import math
import random

import numpy as np
from mathutils import Matrix, Vector

from ironart import scenes_gongbi as GB
from ironart import scenes_gongbi_kit as K
from ironart import scenes_gongbi_land as LD
from ironart import scenes_gongbi_flora as F
from ironart import scenes_look as L
from ironart.geometry import MeshBuilder

SPEC = dict(name="Duel", art="Art/Duel/Background.png", master="Duel/Background@2x.png",
            size=(1280, 720), k=2, m=2, seed=131, spp=12, preview_spp=6)

CAM = (0.0, -26.0, 2.4)
TARGET = (0.0, 60.0, 4.2)
FOCAL = 34.0
SM = K.ScreenMap(CAM, TARGET, FOCAL)
BASE = 500.0
SUN = (0.5, 0.47)
PEAKS = [(0.07, 0.30, 900, 160, 0.8), (0.20, 0.36, 1700, 330, 0.85), (0.33, 0.47, 700, 120, 1.1),
         (0.66, 0.46, 800, 140, 1.0), (0.81, 0.34, 1600, 300, 0.85), (0.94, 0.28, 1000, 180, 0.8),
         (0.45, 0.50, 2600, 600, 1.2), (0.58, 0.49, 3000, 700, 1.2)]


def peaks_b():
    return [(x, y, z + BASE, r, sh) for (x, y, z, r, sh) in SM.peaks(PEAKS)]


def far(X, Y):
    return LD.peak_field(X, Y, peaks_b(), seed=131, ridge=0.45, ridge_scale=140.0, softmax=4.0) - BASE


def build(r):
    rng = random.Random(131)
    pv = r["preview"]
    cols = GB.collections()
    mats = K.materials(cloth=["#E2D6BC", "#2A2C38", "cinnabar", "#3A3530", "ochre", "white",
                              "rouge", "teal", "#7A5A3A", "#C8C0B0", "vermilion", "indigo"])
    peaks_m = LD.qinglv("GB_Duel_Peaks", z0=-450.0, z1=150.0, cun=0.6, cun_px=6.0, cun_len=60.0, moss_px=10.0,
                        var_scale=0.004, near=100.0, far=6000.0, plain_h=0.0, foot="#C08A6A", low="#B08070",
                        mid="#7A8A80", top="#5A7A98", light_top="#C8A8A0", ribs=True)
    fpx = FOCAL / 36.0 * 1280.0
    yaw = math.degrees(SM.yaw)
    LD.fan_terrain("Peaks", CAM[:2], yaw, 60.0, 300.0, 9000.0, 520, 260, far, peaks_m, cols["land"],
                   attrs={"rib": lambda X, Y: LD.peak_ribs(X, Y, peaks_b(), CAM[:2], fpx, 6.0)})
    # ---- the plateau and its broken edge -------------------------------------------------------
    from ironart.scenes_terrain import fbm2, ridged2
    rock = LD.ground("GB_Duel_Ground", color="#D2B48C", deep="#B08A62", cover=0.85, grass=0.5, scale=0.6,
                     near=4.0, far=60.0, blotch=0.35)

    def plateau(X, Y):
        n = fbm2(X, Y, 6.0, 4, seed=7) - 0.5
        rg = ridged2(X, Y, scale=8.0, octaves=4, seed=8)
        edge_y = 9.0 + 2.5 * np.sin(X * 0.11) + n * 3.0
        drop = np.clip((Y - edge_y) / 2.5, 0, 1)
        top = (rg - 0.5) * 0.35 + n * 0.5 + np.clip(np.abs(X) - 16.0, 0, None) * 0.25
        return top * (1 - drop) - 60.0 * drop ** 1.3
    LD.fan_terrain("Plateau", CAM[:2], yaw, 60.0, 1.0, 120.0, 520 if not pv else 360, 260 if not pv else 180,
                   plateau, rock, cols["land"])

    def ground(x, y):
        return float(plateau(np.array([[x]]), np.array([[y]]))[0, 0])
    # ---- the duellists ----------------------------------------------------------------------------
    ppl = MeshBuilder()
    lx, ly, _ = SM.at(0.22, 0.5, 15.0)
    rx_, ry_, _ = SM.at(0.78, 0.5, 15.0)
    K.person(ppl, random.Random(1), "sword_ready", "wanderer", at=(lx, ly, ground(lx, ly)), rz=math.radians(90),
             cloth=0, cloth2=2, hat="topknot", weapon="sword", cape=True, cape_wind=(0.2, 1.0), jitter=0.0)
    K.person(ppl, random.Random(2), "guard", "wanderer", at=(rx_, ry_, ground(rx_, ry_)), rz=math.radians(-90),
             cloth=1, cloth2=3, hat="straw", weapon="sword", cape=True, cape_wind=(-0.6, 1.0), jitter=0.0)
    K.emit(ppl, "Duellists", mats, "fig", thin=("Rope",))
    # ---- the plum tree at the left edge, a few rocks ------------------------------------------
    tm = MeshBuilder()
    px_, py_, _ = SM.at(0.03, 0.5, 9.0)
    F.plum(tm, random.Random(4), height=6.5, at=(px_, py_, ground(px_, py_)), depth=4, blossoms=420 if not pv else 200,
           red=0.45, blossom_r=0.05)
    # rocks along the broken edge and at the corners of the picture (lumpy 青绿 stones)
    rk = LD.rock("GB_Duel_Stones", color="#B89878", deep="#7A6048", cun=0.8, scale=0.8, freq=5.0, ochre=0.35,
                 moss=0.6, near=5.0, far=150.0, top="#5E8A74", top_amount=0.8)
    st = MeshBuilder()
    rr = random.Random(17)
    for (sx, d, sz) in ((0.10, 16.0, (3.0, 2.4, 1.6)), (0.30, 22.0, (2.4, 2.0, 1.0)), (0.66, 23.0, (2.6, 2.0, 1.1)),
                        (0.93, 19.0, (3.0, 2.4, 1.5)), (1.04, 12.0, (3.4, 2.8, 2.2)), (0.44, 26.0, (1.8, 1.4, 0.7)),
                        (0.57, 25.0, (2.0, 1.6, 0.8))):
        x, y, _ = SM.at(sx, 0.5, d)
        LD.boulder(st, (x, y, ground(x, y) - sz[2] * 0.25), sz, rr, "Rock", lumps=5, seg=(18, 12), spread=0.45, rough=0.16)
    K.emit(st, "Stones", dict(Rock=rk), "land")
    for k in range(40 if not pv else 20):
        sx, d = rng.uniform(0.0, 1.0), rng.uniform(8.0, 24.0)
        if 0.3 < sx < 0.7 and d > 18.0:
            continue
        x, y, _ = SM.at(sx, 0.5, d)
        F.tuft(tm, rng, (x, y, ground(x, y)), height=rng.uniform(0.3, 0.6), blades=rng.randint(5, 8), mat="Grass")
    K.emit(tm, "Plum", mats, "tree")
    cam = L.camera(CAM, TARGET, focal_mm=FOCAL)
    look = dict(
        sky=dict(stops=[(0.0, "#C86848", 0.35), (0.18, "#E08858", 0.38), (0.34, "#E8A060", 0.42),
                        (0.45, "#F0C080", 0.4), (0.55, "#F0D0A0", 0.25), (0.8, "silk", 0.0)]),
        fade=dict(d0=200.0, d1=3500.0, color=GB.mixc("silk", "#F0C090", 0.45), amount=0.8, gamma=0.7, cover=0.5),
        mist=[dict(y=(0.52, 1.3), scallop=30.0, dist_min=30.0, line=0.45, line_px=1.0),
              dict(y=(0.44, 0.50), soft=0.02, jitter=0.015, dist_min=1500.0, amount=0.9, noise_px=140, holes=0.3)],
        mist_tint=("#F6DCC0", 0.45),
    )

    def paint2d(cv, r):
        from ironart import scenes_gongbi_2d as G2
        G2.sun(cv, SUN, 30.0, color="#D85A34", alpha=0.8, halo_color="#F0A070", halo=0.35)
        # petals drifting from the plum on the left across the scene
        G2.petals(cv, 140 if not r["preview"] else 80, (0.0, 0.15, 1.0, 0.9), size=(2.0, 3.6),
                  colors=("#F0C8C8", "white", "#E8A8B0"), seed=5, wind=(1.0, 0.25))
        rr = np.random.default_rng(13)
        with cv.paint("sky", "ink", 0.6) as d:
            for i in range(5):
                x = 0.62 + i * 0.03 + rr.uniform(-0.01, 0.01)
                y = 0.2 + rr.uniform(-0.02, 0.02)
                s = 0.005
                d.stroke([(x - s, y - s * 0.7), (x, y), (x + s, y - s * 0.8)], 1.3, "flat")
    return dict(camera=cam, look=look, paint2d=paint2d,
                notes="duellists at x ~21% and ~79%, feet at y ~62%; centre 30-70% x is sky, cloud and far peaks")
