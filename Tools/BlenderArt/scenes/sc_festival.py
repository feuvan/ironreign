"""Event: Festival - a lantern-lit town square at night, fireworks overhead.

Lantern Festival night: a square of two-storey shops with balconies and hanging lanterns, strings
of red lanterns across the square, a painted gateway (paifang) and a drum tower behind; a gilt
dragon dance winds through the crowd of townsfolk carrying lanterns; fireworks open over the
roofs as painted chrysanthemum bursts of gold, vermilion and lead white."""

import math
import random

import numpy as np
from mathutils import Matrix, Vector

from ironart import scenes_gongbi as GB
from ironart import scenes_gongbi_kit as K
from ironart import scenes_look as L
from ironart import world_city as WC
from ironart import world_kit as WK
from ironart.geometry import MeshBuilder

SPEC = dict(name="Festival", art="Art/Events/Festival.png", master="Events/Festival@2x.png",
            size=(640, 360), k=4, m=2, seed=91, spp=12, preview_spp=6)

CAM = (0.0, -24.0, 11.0)
TARGET = (0.0, 40.0, 3.5)
FOCAL = 28.0
SQ = (13.0, 46.0)        # half width of the square, depth of the square


def shopfront(mb, x, y, rz, w=8.0, d=7.0, rng=None):
    """Two-storey shop: brick ground floor with an open lattice front, plaster upper floor with a
    balcony railing, tiled gable roof; lanterns under the eaves."""
    s0 = mb.n
    hs = WK.HouseSpec(w=w, d=d, h=3.3, wall="W_Brick", upper="W_Plaster", front="lattice")
    WK.house(mb, (0, 0, 0), hs)
    s1 = mb.n
    hs2 = WK.HouseSpec(w=w * 0.95, d=d * 0.85, h=2.8, wall="W_Plaster", upper="W_PlasterWarm", front="lattice")
    WK.house(mb, (0, 0.4, 0), hs2)
    mb.transform(s1, Matrix.Translation((0, 0, 3.3)))
    WK.railing(mb, (-w * 0.45, -d * 0.5 - 0.1), (w * 0.45, -d * 0.5 - 0.1), 3.3, h=0.9, mat="W_Lacquer")
    for i in range(3):
        lx = -w * 0.3 + i * w * 0.3
        mb.cylinder((lx, -d * 0.5 - 0.5, 3.2), (lx, -d * 0.5 - 0.5, 2.7), 0.01, 0.01, "Rope", 3)
        mb.sphere((lx, -d * 0.5 - 0.5, 2.45), 0.3, "LanternPaper", 10, 7, scale=(1, 1, 1.15))
        mb.cylinder((lx, -d * 0.5 - 0.5, 2.1), (lx, -d * 0.5 - 0.5, 1.8), 0.05, 0.01, "W_Tassel", 5)
    mb.transform(s0, Matrix.Translation((x, y, 0)) @ Matrix.Rotation(rz, 4, "Z"))


def dragon(mb, rng, pts, mats_prefix=""):
    """Dragon-dance body: a gilt scaled tube along ``pts`` held up on poles, a head at the front."""
    from ironart import scenes_people as P
    body = []
    for i, p in enumerate(pts):
        body.append(Vector(p) + Vector((0, 0, 2.3 + 0.35 * math.sin(i * 1.3))))
    mb.tube([tuple(p) for p in body], 0.42, "DragonBody", 10, radius_fn=lambda t: 1.0 - 0.6 * t * t)
    # a red dorsal fin line
    mb.tube([tuple(p + Vector((0, 0, 0.42))) for p in body], 0.08, "DragonFin", 5)
    hd = body[0]
    mb.sphere(tuple(hd + Vector((0, -0.4, 0.2))), 0.75, "DragonBody", 14, 10, scale=(0.9, 1.4, 0.8))
    mb.sphere(tuple(hd + Vector((0, -1.3, 0.1))), 0.35, "DragonFin", 10, 6, scale=(1.0, 1.0, 0.7))
    for sd in (-1, 1):
        mb.tube([tuple(hd + Vector((sd * 0.3, -0.2, 0.8))), tuple(hd + Vector((sd * 0.6, 0.6, 1.5)))], 0.06, "W_Gold", 4)
    # dancers on poles under the body
    for i, p in enumerate(body[::2]):
        g = Vector(p) - Vector((0, 0, 2.3))
        mb.cylinder(tuple(g + Vector((0, 0, 1.2))), tuple(p), 0.03, 0.03, "Wood", 5)
        f = MeshBuilder()
        P.figure(f, random.Random(500 + i), "cheer" if i % 2 else "walk", "peasant", cloth=10 if i % 2 else 0,
                 cloth2=4, hat="band", jitter=4)
        d = (Vector(body[max(0, 2 * i - 1)]) - Vector(body[min(len(body) - 1, 2 * i + 1)]))
        rz = math.atan2(d.x, -d.y) if d.length > 1e-3 else 0.0
        mb.extend(f, Matrix.Translation(g) @ Matrix.Rotation(rz, 4, "Z"))


def build(r):
    rng = random.Random(91)
    pv = r["preview"]
    cols = GB.collections()
    mats = K.materials(cloth=["cinnabar", "azurite", "malachite", "#3A3530", "gold_l", "#E2D6BC",
                              "rouge", "teal", "#7A5A3A", "white", "vermilion", "indigo"])
    mats["DragonBody"] = GB.lamellar("GB_DragonScales", "#D8A848", lace="cinnabar", scale=(0.12, 0.14))
    mats["DragonFin"] = GB.cloth("GB_DragonFin", "cinnabar")
    mats["Square"] = GB.wash("GB_Festival_Paving", "#C8BCA4", "#A89C84", grad="none", form=0.0)
    arch = MeshBuilder()
    W_, D_ = SQ
    arch.box((0, D_ / 2, -0.2), (120, 140, 0.2), "Square", skip=("bottom",))
    for i in range(5):
        y = 6.0 + i * 8.6
        shopfront(arch, -W_ - 4.0, y, math.pi / 2, rng=rng)
        shopfront(arch, W_ + 4.0, y, -math.pi / 2, rng=rng)
    # the gateway and the drum tower at the back of the square
    WK.paifang(arch, w=12.0, h=8.0, center=(0, D_ - 4.0, 0))
    dt = WC.p_drum_tower(roof="W_TileDark", W=18.0, D=13.0, H=8.0)
    arch.extend(dt, Matrix.Translation((0, D_ + 14.0, 0)))
    for sd in (-1, 1):
        for i in range(3):
            shopfront(arch, sd * (7.0 + i * 9.0), D_ + 2.0 + i * 0.5, 0.0, rng=rng)
    K.emit(arch, "Town", mats, "arch")
    # lantern strings across the square
    lm = MeshBuilder()
    from ironart import scenes_arch as A
    for i in range(6):
        y = 6.0 + i * 7.0
        A.lantern_string(lm, (-W_ - 0.8, y, 6.6), (W_ + 0.8, y + 2.0, 6.6), n=9, sag=1.4, mat="LanternPaper",
                         rope="Rope", size=0.32)
    K.emit(lm, "Lanterns", mats, "fig", thin=("Rope",))
    # the dragon dance and the crowd
    ppl = MeshBuilder()
    path = [(math.sin(t * 0.55) * 6.0 - 1.0, 10.0 + t * 1.4) for t in np.linspace(0, 14, 16)]
    dragon(ppl, rng, [(x, y, 0.0) for (x, y) in path])
    n = 90 if not pv else 50
    for i in range(n):
        x = rng.uniform(-W_ + 1.0, W_ - 1.0)
        y = 1.0 + (rng.random() ** 1.4) * (D_ - 8.0)
        near = min(math.hypot(x - px, y - py) for (px, py) in path)
        if near < 2.4:
            continue
        pose = rng.choice(["walk", "stand", "point", "cheer", "stand_hands", "walk"])
        outfit = rng.choice(["robe", "lady", "peasant", "robe", "lady"])
        wpn = "lantern" if rng.random() < 0.35 else None
        rz = math.atan2(-x, -(y - 22.0)) + rng.uniform(-0.6, 0.6)
        K.person(ppl, random.Random(i), pose, outfit, at=(x, y, 0.0), rz=rz,
                 cloth=rng.choice([0, 1, 2, 4, 5, 6, 7, 9, 10]), cloth2=rng.choice([5, 9, 3]),
                 hat=rng.choice([None, "guan", "topknot", None]) if outfit != "lady" else None,
                 hair_long=outfit == "lady", weapon=wpn, jitter=4.0)
    K.emit(ppl, "Crowd", mats, "fig", thin=K.THIN)
    cam = L.camera(CAM, TARGET, focal_mm=FOCAL)
    look = dict(
        sky=dict(stops=[(0.0, "#141C2C", 0.88), (0.25, "#1E2638", 0.82), (0.45, "#2E3446", 0.72), (1.0, "#2E3446", 0.6)]),
        fade=dict(d0=30.0, d1=120.0, color="#6A6458", amount=0.35, gamma=1.0, cover=0.0),
        tone=(0.88, 0.84, 0.82),
        shader_ink_color="#14100E",
    )
    lanterns = []
    for i in range(6):
        y = 6.0 + i * 7.0
        for j in range(9):
            t = (j + 0.5) / 9
            a = Vector((-W_ - 0.8, y, 6.6))
            b_ = Vector((W_ + 0.8, y + 2.0, 6.6))
            p = a + (b_ - a) * t - Vector((0, 0, 1.4 * 4 * t * (1 - t) + 0.4))
            lanterns.append(tuple(p))
    for i in range(5):
        for sd in (-1, 1):
            for k in range(3):
                y = 6.0 + i * 8.6 - 2.4 + k * 2.4
                lanterns.append((sd * (W_ + 0.0), y, 2.45))

    def paint2d(cv, r):
        from ironart import scenes_gongbi_2d as G2
        # lantern glow: warm soft washes (painted, no bloom)
        for p in lanterns:
            sx, sy, sz = L.screen_pos(cam, p)
            if sz <= 0:
                continue
            c = (sx, 1.0 - sy)
            rad = 260.0 / max(sz, 6.0)
            with cv.paint("front", "#F0A050", 0.16, soft=rad * 0.8) as d:
                d.disc(c, rad)
        # fireworks over the roofs
        for (c, rad, cols_, seed) in (((0.30, 0.16), 46.0, ("gold", "vermilion"), 1),
                                      ((0.62, 0.10), 56.0, ("vermilion", "white"), 2),
                                      ((0.80, 0.24), 36.0, ("gold", "white"), 3),
                                      ((0.12, 0.28), 30.0, ("white", "gold"), 4),
                                      ((0.48, 0.27), 26.0, ("gold", "vermilion"), 5)):
            G2.firework(cv, c, rad, colors=cols_, rays=40, seed=seed)
        # trails rising to the bursts
        with cv.paint("sky", "#E8C080", 0.55) as d:
            for (x0, y0, x1, y1) in ((0.31, 0.40, 0.30, 0.22), (0.63, 0.42, 0.62, 0.17), (0.81, 0.45, 0.80, 0.29)):
                d.stroke([(x0, y0), ((x0 + x1) / 2 + 0.004, (y0 + y1) / 2), (x1, y1)], 0.8, "head")
    return dict(camera=cam, look=look, paint2d=paint2d, notes="fireworks across the top third")
