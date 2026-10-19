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

CAM = (-4.0, -24.0, 1.6)
TARGET = (-14.0, 80.0, 1.0)
FOCAL = 32.0
SM = K.ScreenMap(CAM, TARGET, FOCAL)
MOON = (0.27, 0.21)
# far peaks rising out of the sea of mist below the path
PEAKS = [(0.10, 0.50, 900, 260, 1.3), (0.24, 0.45, 1500, 420, 1.2), (0.38, 0.55, 700, 200, 1.4),
         (0.50, 0.49, 1300, 330, 1.2), (0.03, 0.43, 2600, 700, 1.3), (0.40, 0.42, 3200, 900, 1.2)]


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
    # ---- the cliff top and its path (right): a rock heightfield dropping into the void ----------
    from ironart.scenes_terrain import fbm2, ridged2
    rk = LD.qinglv("GB_Wanderer_Cliff", z0=-40.0, z1=26.0, cun=0.85, cun_px=4.0, cun_len=6.0,
                   moss_px=8.0, var_scale=0.03, near=3.0, far=300.0, plain_h=0.0, steep=(0.2, 0.6),
                   foot="#6A6656", low="#7A7462", mid="#4E6E62", top="#3E5E6E", light_top="#8EA6A8",
                   shadow_cun=0.4)

    # the ledge and the cliff behind it: piles of lumpy rocks (the ink draws their folds)
    cm = MeshBuilder()
    rr = random.Random(9)
    tops = []
    for (sx, d, top, w, h, lumps) in ((0.64, 13.0, 0.0, 6.0, 7.0, 7), (0.74, 12.5, -0.8, 5.0, 6.0, 6),
                                      (0.56, 15.0, -2.4, 4.0, 5.0, 5), (0.84, 15.0, 5.0, 7.0, 12.0, 7),
                                      (0.95, 14.0, 11.0, 7.0, 18.0, 8), (0.78, 20.0, 9.0, 7.0, 16.0, 7),
                                      (1.04, 16.0, 16.0, 8.0, 24.0, 8), (0.70, 18.0, 2.0, 5.0, 8.0, 6)):
        x, y, _ = SM.at(sx, 0.5, d)
        LD.boulder(cm, (x, y, top - h), (w, w * 0.8, h), rr, mat="Rock", lumps=lumps,
                   flat_top=top if top <= 0.5 else None, squash=1.1, rough=0.1)
        # the column continues down into the mist
        LD.boulder(cm, (x + rr.uniform(-1, 1), y + 1.0, top - h - 14.0), (w * 0.9, w * 0.75, 15.0), rr, mat="Rock",
                   lumps=4, squash=1.2, rough=0.08)
        tops.append((x, y, top, w))
    K.emit(cm, "Cliff", dict(Rock=rk), "land")

    def ground(x, y):
        best = -90.0
        for (cx_, cy_, top, w) in tops:
            if math.hypot(x - cx_, y - cy_) < w * 0.3:
                best = max(best, top)
        return best
    # ---- the wanderer at the edge -------------------------------------------------------------
    px, py, _ = SM.at(0.635, 0.5, 12.5)
    ppl = MeshBuilder()
    K.person(ppl, random.Random(7), "stand", "wanderer", at=(px, py, ground(px, py) - 0.05), rz=math.radians(135),
             cloth=0, cloth2=1, hat="straw", weapon="sword_back", cape=True, cape_wind=(0.9, 0.2))
    K.emit(ppl, "Wanderer", mats, "fig", thin=("Rope",))
    # ---- a gnarled pine reaching out over the drop -------------------------------------------
    tm = MeshBuilder()
    cam_dir = Vector(TARGET) - Vector(CAM)
    tx, ty, _ = SM.at(0.72, 0.5, 18.0)
    F.pine(tm, random.Random(3), height=6.0, lean=1.0, limbs=7, at=(tx, ty, 1.0), cam_dir=cam_dir,
           crown=1.3, trunk_r=0.2, reach=(-1.0, 0.2), pad=0.62)
    tx2, ty2, _ = SM.at(0.96, 0.5, 15.0)
    F.pine(tm, random.Random(4), height=4.5, lean=0.6, limbs=5, at=(tx2, ty2, 10.5), cam_dir=cam_dir, pad=0.5,
           reach=(-1.0, 0.0))
    K.emit(tm, "Pines", mats, "tree")
    cam = L.camera(CAM, TARGET, focal_mm=FOCAL)
    look = dict(
        sky=dict(stops=[(0.0, "#1E2838", 0.84), (0.3, "#2A364A", 0.74), (0.5, "#4A5668", 0.55), (0.7, "#6A7484", 0.4),
                        (1.0, "#6A7484", 0.4)]),
        fade=dict(d0=200.0, d1=4000.0, color="#A8B0B8", amount=0.7, gamma=0.8, cover=0.35),
        mist=[dict(y=(0.52, 0.80), soft=0.05, jitter=0.03, dist_min=300.0, amount=1.0, noise_px=110, holes=0.25),
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
    return dict(camera=cam, look=look, paint2d=paint2d, notes="moon upper left (27%, 21%); figure at right third")
