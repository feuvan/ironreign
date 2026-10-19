"""Event: Wanderer - a lone swordsman on a cliff path under a full moon.

Night in the high mountains: a narrow stone path clings to a cliff on the right, a gnarled pine
leans out over the drop; the wanderer in a straw hat and travelling cloak, sword on his back,
stands at the turn of the path looking out to a full moon left as bare silk in an ink-blue sky
(烘云托月).  Below him a sea of moonlit mist with blue-green peaks rising through it."""

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

SPEC = dict(name="Wanderer", art="Art/Events/Wanderer.png", master="Events/Wanderer@2x.png",
            size=(640, 360), k=4, m=2, seed=51, spp=12, preview_spp=6)

CAM = (0.0, -32.0, 3.0)
TARGET = (-6.0, 80.0, 1.0)
FOCAL = 32.0
SM = K.ScreenMap(CAM, TARGET, FOCAL)
MOON = (0.28, 0.2)
# far peaks rising out of the sea of mist below the path
PEAKS = [(0.08, 0.52, 900, 220, 1.0), (0.22, 0.47, 1500, 380, 1.0), (0.40, 0.56, 700, 160, 1.1),
         (0.52, 0.50, 1300, 300, 1.0), (0.02, 0.45, 2600, 700, 1.2), (0.40, 0.44, 3200, 900, 1.2)]


BASE = 600.0          # the valley floor lies far below the path (hidden in the mist)


def peaks_b():
    return [(x, y, z + BASE, r, sh) for (x, y, z, r, sh) in SM.peaks(PEAKS)]


def height(X, Y):
    return LD.peak_field(X, Y, peaks_b(), seed=51, ridge=0.45, ridge_scale=120.0, softmax=4.0) - BASE


def build(r):
    rng = random.Random(51)
    pv = r["preview"]
    cols = GB.collections()
    mats = K.materials(cloth=["#5A6470", "#3A4250", "#8A7A60", "#3A3530", "ochre", "#C8C0B0",
                              "rouge", "teal", "#6A5A4A", "#D8D0C0", "vermilion", "indigo"],
                       flora=dict(Needles=F.needles("GB_Needles_Night", "#2E5A50", "#1A3A34"),
                                  PineBark=F.bark("GB_PineBark_Night", "#6A5444", "#3E3028", scales=0.55, scale=5.0)))
    night_land = LD.qinglv("GB_Wanderer_Peaks", z0=-500.0, z1=60.0, cun=0.7, cun_px=6.0, cun_len=50.0,
                           moss_px=9.0, var_scale=0.004, near=100.0, far=4000.0, plain_h=0.0,
                           foot="#6E6A5E", low="#626A64", mid="#3E6662", top="#3A5674",
                           light_top="#8EA6B8", ribs=True)
    fpx = FOCAL / 36.0 * 640.0
    peaks_w = SM.peaks(PEAKS)
    yaw = math.degrees(SM.yaw)
    LD.fan_terrain("Peaks", CAM[:2], yaw, 64.0, 150.0, 9000.0, 420, 220, height, night_land, cols["land"],
                   attrs={"rib": lambda X, Y: LD.peak_ribs(X, Y, peaks_b(), CAM[:2], fpx, 6.0)})
    # ---- the promontory: piled lumpy rock rising out of the mist on the right, a spur of it
    # jutting out towards the moon where the path ends ------------------------------------------
    rk = LD.rock("GB_Wanderer_Rock", color="#8E8C80", deep="#4E504C", cun=0.55, scale=1.4, freq=5.0,
                 ochre=0.2, moss=0.0, near=10.0, far=200.0, top="#3E6A62", top_amount=0.85)
    cm = MeshBuilder()
    rr = random.Random(9)
    lx, ly, lz = SM.at(0.60, 0.66, 17.0)
    LEDGE = Vector((lx, ly, lz))
    # the spur under the wanderer's feet, stepping down into the mist
    LD.crag_stack(cm, (lx + 0.3, ly + 0.6), lz - 40.0, lz, 2.0, 1.5, rr, "Rock", seg=(20, 12), squash=1.15)
    for (dx, dy, dz, r0, r1) in ((1.8, 1.2, -1.2, 1.8, 1.3), (-1.2, 1.8, -3.0, 1.5, 1.0), (3.6, 2.2, -0.4, 2.0, 1.5)):
        LD.crag_stack(cm, (lx + dx, ly + dy), lz - 40.0, lz + dz, r0, r1, rr, "Rock", flat_top=False, seg=(18, 12),
                      squash=1.15)
    # the cliff wall on the right, rising out of frame, its path coming round to the spur
    for (sx, d, top, r0, r1) in ((0.72, 19.0, 0.6, 2.4, 2.0), (0.80, 20.0, 3.5, 3.0, 2.4), (0.89, 21.0, 8.0, 3.6, 2.8),
                                 (0.98, 21.0, 14.0, 4.2, 3.2), (1.06, 22.0, 20.0, 4.6, 3.6), (0.86, 30.0, 12.0, 5.0, 3.8),
                                 (0.96, 32.0, 20.0, 5.5, 4.0)):
        x, y, z = SM.at(sx, 0.66, d)
        LD.crag_stack(cm, (x, y), lz - 40.0, lz + top, r0, r1, rr, "Rock", flat_top=top < 1.0, seg=(22, 14),
                      squash=1.15)
    K.emit(cm, "Cliff", dict(Rock=rk), "land")
    # ---- the wanderer at the end of the path, looking out at the moon --------------------------
    ppl = MeshBuilder()
    K.person(ppl, random.Random(7), "stand", "wanderer", at=(lx, ly, lz), rz=math.radians(122),
             cloth=0, cloth2=1, hat="straw", weapon="sword_back", cape=True, cape_wind=(0.9, 0.2))
    K.emit(ppl, "Wanderer", mats, "fig", thin=("Rope",))
    # ---- gnarled pines reaching out over the drop ------------------------------------------------
    tm = MeshBuilder()
    cam_dir = Vector(TARGET) - Vector(CAM)
    tx, ty, _ = SM.at(0.89, 0.66, 21.0)
    F.pine(tm, random.Random(3), height=6.0, lean=1.0, limbs=7, at=(tx, ty, lz + 7.6), cam_dir=cam_dir,
           crown=1.3, reach=(-1.0, -0.1))
    tx2, ty2, _ = SM.at(0.80, 0.66, 20.0)
    F.pine(tm, random.Random(4), height=3.2, lean=0.8, limbs=5, at=(tx2, ty2, lz + 3.2), cam_dir=cam_dir,
           reach=(-1.0, 0.1))
    K.emit(tm, "Pines", mats, "tree")
    cam = L.camera(CAM, TARGET, focal_mm=FOCAL)
    look = dict(
        sky=dict(stops=[(0.0, "#1E2838", 0.84), (0.3, "#2A364A", 0.74), (0.5, "#4A5668", 0.55), (0.7, "#6A7484", 0.4),
                        (1.0, "#6A7484", 0.4)]),
        fade=dict(d0=200.0, d1=4000.0, color="#A8B0B8", amount=0.7, gamma=0.8, cover=0.35),
        mist=[dict(y=(0.53, 1.3), soft=0.05, jitter=0.03, dist_min=300.0, amount=1.0, noise_px=110, holes=0.25),
              dict(y=(0.84, 1.3), soft=0.05, jitter=0.03, dist_min=0.0, amount=0.85, noise_px=90, holes=0.3),
              dict(y=(0.42, 0.47), soft=0.02, jitter=0.02, dist_min=1800.0, amount=0.8, noise_px=120, holes=0.3)],
        mist_tint=("#B8C0C8", 0.5),
        tone=(0.92, 0.94, 1.0),
        shader_ink_color="#1A1E24",
    )

    def paint2d(cv, r):
        from ironart import scenes_gongbi_2d as G2
        G2.moon(cv, MOON, 30.0, sky_cut=0.95, halo=3.0, color="#F2EEDC", rim_alpha=0.3)
        # thin clouds drifting across the moon, outlined
        with cv.paint("sky", "#8A94A4", 0.35, soft=4.0) as d:
            d.ellipse((0.20, 0.25), 70, 6)
            d.ellipse((0.34, 0.27), 50, 4)
    return dict(camera=cam, look=look, paint2d=paint2d, notes="moon upper left (28%, 20%); figure at right third")
