"""Event: Plague - a fog-shrouded village with closed doors.

A narrow village street sinks into grey fog: every door shut, yellow paper charms pasted on the
leaves, an abandoned handcart, a withered tree where crows wait; far down the street a lone
mourner in white and a physician with a lantern are half dissolved in the mist.  The palette is
drained to ink greys and pale ochre."""

import math
import random

import numpy as np
from mathutils import Matrix, Vector

from ironart import scenes_gongbi as GB
from ironart import scenes_gongbi_kit as K
from ironart import scenes_gongbi_flora as F
from ironart import scenes_gongbi_land as LD
from ironart import scenes_look as L
from ironart import world_kit as WK
from ironart.geometry import MeshBuilder

SPEC = dict(name="Plague", art="Art/Events/Plague.png", master="Events/Plague@2x.png",
            size=(640, 360), k=4, m=2, seed=101, spp=12, preview_spp=6)

CAM = (0.6, -6.0, 3.4)
TARGET = (-0.5, 40.0, 1.8)
FOCAL = 30.0


def house(mb, x, y, rz, w, d, h, rng, charm=True):
    hs = WK.HouseSpec(w=w, d=d, h=h, wall="W_Brick", upper="W_Plaster", front="wall")
    s0 = mb.n
    WK.house(mb, (0, 0, 0), hs)
    # closed double door with paper charms
    mb.box((0, -d / 2 - 0.05, 0.3), (1.6, 0.12, 2.3), "Door")
    mb.box((0, -d / 2 - 0.12, 0.3), (0.04, 0.03, 2.3), "W_Dark")
    if charm:
        for sd in (-1, 1):
            mb.box((sd * 0.4, -d / 2 - 0.13, 1.3), (0.22, 0.02, 0.6), "Charm")
    mb.transform(s0, Matrix.Translation((x, y, 0)) @ Matrix.Rotation(rz, 4, "Z"))


def build(r):
    rng = random.Random(101)
    pv = r["preview"]
    cols = GB.collections()
    mats = K.materials(cloth=["#6A665E", "#4A4844", "#9A8A70", "#3A3530", "ochre", "#E2D6BC",
                              "rouge", "teal", "#7A5A3A", "white", "vermilion", "indigo"],
                       arch=dict(plaster="#E0D6C2"))
    mats["Door"] = GB.wash("GB_Plague_Door", "#6A5A48", "#4A3E32")
    mats["Charm"] = GB.flat("GB_Plague_Charm", "#E0C060")
    mats["Street"] = LD.ground("GB_Plague_Street", color="#C8BCA4", deep="#A89C84", cover=0.7, blotch=0.3)
    arch = MeshBuilder()
    arch.box((0, 40, -0.2), (60, 120, 0.2), "Street", skip=("bottom",))
    y = 2.0
    i = 0
    while y < 70.0:
        w = rng.uniform(6.5, 8.5)
        for sd in (-1, 1):
            house(arch, sd * (5.0 + rng.uniform(0.0, 0.6)), y + rng.uniform(-0.4, 0.4), -sd * math.pi / 2,
                  w, rng.uniform(5.0, 6.0), rng.uniform(3.0, 3.6), rng, charm=rng.random() < 0.7)
        y += w + rng.uniform(0.3, 1.2)
        i += 1
    K.emit(arch, "Village", mats, "arch")
    # handcart, baskets
    pm = MeshBuilder()
    s0 = pm.n
    for sd in (-1, 1):
        pm.cylinder((sd * 0.6, 0, 0.5), (sd * 0.68, 0, 0.5), 0.5, 0.5, "Wood", 14)
    pm.box((0, 0.3, 0.55), (1.1, 1.6, 0.12), "Wood")
    pm.box((0, 0.3, 0.67), (1.0, 1.4, 0.35), "Straw")
    pm.cylinder((-0.4, 1.1, 0.6), (-0.45, 2.4, 0.1), 0.04, 0.04, "Wood", 5)
    pm.cylinder((0.4, 1.1, 0.6), (0.45, 2.4, 0.1), 0.04, 0.04, "Wood", 5)
    pm.transform(s0, Matrix.Translation((1.8, 9.0, 0)) @ Matrix.Rotation(0.6, 4, "Z") @ Matrix.Rotation(0.12, 4, "Y"))
    pm.lathe([(0.0, 0.0), (0.28, 0.02), (0.36, 0.45), (0.0, 0.45)], "Straw", 10, center=(-3.2, 6.0, 0.0))
    pm.lathe([(0.0, 0.0), (0.22, 0.02), (0.28, 0.35), (0.0, 0.35)], "Straw", 10, center=(-3.6, 6.8, 0.0))
    K.emit(pm, "Props", mats, "fig", thin=("Wood",))
    # the withered tree by the street
    tm = MeshBuilder()
    F.dead_tree(tm, random.Random(4), height=7.0, at=(3.6, 15.0, 0.0), depth=4)
    K.emit(tm, "Tree", mats, "tree")
    # figures far down the street
    ppl = MeshBuilder()
    K.person(ppl, random.Random(1), "kneel_bow", "robe", at=(-1.2, 22.0, 0.0), rz=math.radians(-30),
             cloth=9, cloth2=5, hat="hood")
    K.person(ppl, random.Random(2), "walk", "robe", at=(1.0, 28.0, 0.0), rz=math.radians(170),
             cloth=3, cloth2=1, hat="guan", weapon="lantern")
    K.person(ppl, random.Random(3), "stand", "peasant", at=(-2.0, 40.0, 0.0), rz=math.radians(160),
             cloth=1, cloth2=5, hat="hood")
    K.emit(ppl, "People", mats, "fig", thin=K.THIN)
    cam = L.camera(CAM, TARGET, focal_mm=FOCAL)
    look = dict(
        sky=dict(stops=[(0.0, "#6A6A68", 0.45), (0.3, "#8A8A84", 0.3), (0.5, "silk", 0.1)]),
        fade=dict(d0=8.0, d1=55.0, color=GB.mixc("silk", "#C8C4BC", 0.5), amount=0.92, gamma=0.8, cover=0.75),
        mist=[dict(y=(0.30, 0.72), soft=0.06, jitter=0.04, dist_min=20.0, amount=0.85, noise_px=80, holes=0.4),
              dict(y=(0.55, 1.2), soft=0.08, jitter=0.04, dist_min=11.0, amount=0.45, noise_px=60, holes=0.5)],
        mist_tint=("#D8D4CC", 0.45),
        tone=(0.94, 0.94, 0.93),
        age=dict(desat=0.3),
    )

    def paint2d(cv, r):
        # crows on the bare branches and circling over the roofs
        rr = np.random.default_rng(101)
        sx0, sy0, _ = L.screen_pos(cam, (3.6, 15.0, 5.5))
        with cv.paint("front", "ink", 0.85) as d:
            for i in range(4):
                c = (sx0 + rr.uniform(-0.04, 0.03), 1.0 - sy0 + rr.uniform(-0.06, 0.04))
                d.ellipse(c, 2.2, 1.6)
                d.disc((c[0] + 0.004, c[1] - 0.004), 1.1)
            for i in range(6):
                x = 0.35 + rr.uniform(-0.15, 0.2)
                y = 0.12 + rr.uniform(-0.06, 0.06)
                s = 0.006
                d.stroke([(x - s, y - s * 0.3), (x - s * 0.3, y - s * 0.6), (x, y), (x + s * 0.3, y - s * 0.6), (x + s, y - s * 0.3)], 1.3, "flat")
    return dict(camera=cam, look=look, paint2d=paint2d, notes="no UI keep-out")
