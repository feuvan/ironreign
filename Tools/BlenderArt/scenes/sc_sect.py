"""Event: Sect - a cliff temple above the clouds, disciples training at dawn.

A sea of 祥云 clouds at sunrise.  Left of centre a great crag of piled, lumpy 青绿 rock (ochre
stone, malachite and azurite on its tops, pines in its clefts) rises out of the clouds and carries
the sect's temple on its levelled summit: halls with green-glazed roofs, a seven-tier pagoda, a
gate.  In the right foreground, on a paved terrace with a marble balustrade on its own crag,
rows of disciples in pale robes practise sword forms before their master.  Further pinnacles
stand in the cloud sea, paler with distance; the vermilion sun lifts out of the clouds; cranes
cross the sky."""

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
            size=(640, 360), k=4, m=2, seed=61, spp=6, preview_spp=4)

CAM = (0.0, -40.0, 12.0)
TARGET = (-10.0, 100.0, 12.0)
FOCAL = 30.0
SM = K.ScreenMap(CAM, TARGET, FOCAL)
SUN = (0.79, 0.36)
# pinnacles in the cloud sea: (screen x, screen y of the summit, distance m, foot radius m)
PINNACLES = [(0.05, 0.25, 330.0, 22.0), (0.57, 0.30, 420.0, 20.0), (0.65, 0.39, 700.0, 36.0),
             (0.94, 0.27, 520.0, 26.0), (0.47, 0.37, 1100.0, 55.0), (0.86, 0.40, 1500.0, 70.0),
             (0.19, 0.37, 1300.0, 60.0), (0.10, 0.42, 2000.0, 90.0)]


def build(r):
    rng = random.Random(61)
    pv = r["preview"]
    cols = GB.collections()
    mats = K.materials(cloth=["white", "#C8C8C0", "azurite", "#3A3530", "ochre", "#E2D6BC",
                              "rouge", "teal", "#7A5A3A", "#ECE4D4", "vermilion", "indigo"],
                       arch=dict(lacquer="vermilion"))
    near_rock = LD.rock("GB_Sect_Rock", color="#CDB088", deep="#8A6E4E", cun=0.85, scale=0.12, freq=4.0,
                        ochre=0.35, moss=0.6, near=20.0, far=600.0, top="malachite", top_amount=0.9)
    mid_rock = LD.rock("GB_Sect_RockMid", color="#BCB490", deep="#7A7660", cun=0.7, scale=0.05, freq=4.0,
                       ochre=0.3, moss=0.5, near=60.0, far=1500.0, top="#4E9488", top_amount=0.9)
    far_rock = LD.rock("GB_Sect_RockFar", color="#B4B8A0", deep="#7C8A80", cun=0.5, scale=0.025, freq=4.0,
                       ochre=0.2, moss=0.3, near=100.0, far=2500.0, top="#5E86A0", top_amount=0.9)
    cam_dir = Vector(TARGET) - Vector(CAM)
    # ---- the temple crag ----------------------------------------------------------------------
    tx, ty, tz = SM.at(0.31, 0.22, 125.0)
    cm_ = MeshBuilder()
    rr = random.Random(11)
    top = LD.crag_stack(cm_, (tx, ty), tz - 200.0, tz, 21.0, 17.0, rr, "Rock", lean=(-3.0, 0.0), seg=(24, 16),
                        squash=1.25)
    # shoulders: lower crags leaning on its flanks
    for (dx, dy, zt, r0, r1) in ((-20.0, 8.0, tz - 30.0, 13.0, 8.0), (19.0, 10.0, tz - 44.0, 14.0, 9.0),
                                 (-11.0, -12.0, tz - 62.0, 12.0, 8.0), (12.0, -13.0, tz - 82.0, 11.0, 7.0)):
        LD.crag_stack(cm_, (tx + dx, ty + dy), tz - 200.0, zt, r0, r1, rr, "Rock", flat_top=False, seg=(20, 12),
                      squash=1.25)
    K.emit(cm_, "TempleCrag", dict(Rock=near_rock), "land")
    # the temple on the summit
    tm = MeshBuilder()
    s0 = tm.n
    hs = WK.HallSpec(bays=(3, 2), bay=3.4, col_h=3.6, plat_h=0.9, double=True, upper_h=2.4)
    hs.roof = WK.RoofSpec(style="hip_gable", mat="W_TileGreen", ridge_mat="W_RidgeGreen", overhang=1.3, lift=0.6,
                          flare=0.3)
    WK.hall(tm, (2.0, 4.0, 0), hs)
    WK.pagoda(tm, (-10.0, 6.0, 0), tiers=7, R=2.2, base_h=2.4, tier_h=1.8)
    for sx_ in (-1, 1):
        s1 = tm.n
        hs2 = WK.HallSpec(bays=(2, 1), bay=3.0, col_h=2.8, plat_h=0.5, steps=False)
        hs2.roof = WK.RoofSpec(style="hip_gable", mat="W_TileGreen", ridge_mat="W_RidgeGreen", overhang=1.0, lift=0.4)
        WK.hall(tm, (0, 0, 0), hs2)
        tm.transform(s1, Matrix.Translation((2.0 + sx_ * 9.5, -4.0, 0)) @ Matrix.Rotation(sx_ * math.pi / 2, 4, "Z"))
    s1 = tm.n
    WK.gatehouse_small(tm, w=4.6, d=3.0, h=3.0)
    tm.transform(s1, Matrix.Translation((2.0, -12.5, 0.0)))
    tm.transform(s0, Matrix.Translation(top) @ Matrix.Rotation(math.radians(-12), 4, "Z"))
    K.emit(tm, "Temple", mats, "arch")
    # ---- pinnacles in the cloud sea -------------------------------------------------------------
    pn = MeshBuilder()
    pf = MeshBuilder()
    for i, (sx, sy, d, r0) in enumerate(PINNACLES):
        x, y, z = SM.at(sx, sy, d)
        target = pn if d < 800 else pf
        LD.crag_stack(target, (x, y), z - d * 0.9, z, r0, r0 * rng.uniform(0.5, 0.7), random.Random(100 + i),
                      "Rock", lean=(rng.uniform(-0.6, 0.6) * r0, 0.0), flat_top=False,
                      seg=(18, 12) if d > 800 else (22, 14), squash=1.3)
    K.emit(pn, "PinnaclesMid", dict(Rock=mid_rock), "land")
    K.emit(pf, "PinnaclesFar", dict(Rock=far_rock), "land")
    # ---- the training terrace on its own crag (right foreground) -------------------------------
    cx, cy, cz = SM.at(0.72, 0.80, 26.0)
    cy += 8.0
    tr_ = MeshBuilder()
    rr = random.Random(3)
    LD.crag_stack(tr_, (cx, cy), cz - 140.0, cz - 0.4, 22.0, 15.5, rr, "Rock", seg=(28, 18))
    # rock bulging out under the edges of the terrace
    RZ0 = math.radians(-20)
    R0 = Matrix.Rotation(RZ0, 4, "Z")
    for (lx, ly, sz) in ((-8.5, -8.0, (9.0, 7.0, 7.5)), (1.0, -9.0, (11.0, 7.0, 6.5)), (9.5, -7.0, (8.0, 6.0, 7.0)),
                         (-11.5, 1.0, (7.0, 9.0, 7.0)), (11.5, 2.0, (7.0, 9.0, 6.0))):
        p = Vector((cx, cy, 0.0)) + R0 @ Vector((lx, ly, 0.0))
        LD.boulder(tr_, (p.x, p.y, cz - sz[2] - 0.6), sz, rr, "Rock", lumps=5, seg=(20, 12), spread=0.45,
                   flat_top=cz - 0.7, rough=0.16)
    K.emit(tr_, "TerraceCrag", dict(Rock=near_rock), "land")
    ter = MeshBuilder()
    WK.platform(ter, 22.0, 17.0, 1.2, "W_Marble", "W_Paving", z0=-1.2, skirt=0.3)
    WK.balustrade_rect(ter, 21.6, 16.6, 0.0, gap=3.0, mat="W_Marble", h=0.9)
    RZ = math.radians(-20)
    ter.transform(0, Matrix.Translation((cx, cy, cz)) @ Matrix.Rotation(RZ, 4, "Z"))
    K.emit(ter, "Terrace", mats, "arch")
    # disciples in rows, their master facing them
    ppl = MeshBuilder()
    R = Matrix.Rotation(RZ, 4, "Z")
    poses = ["sword_ready", "slash_high", "guard", "thrust"]
    for row in range(3):
        for col_ in range(4):
            lx = -5.4 + col_ * 3.6 + (row % 2) * 0.6
            ly = 0.0 + row * 2.9
            p = Vector((cx, cy, cz)) + R @ Vector((lx, ly, 0))
            pose = poses[row % 2] if row != 1 else poses[2 + col_ % 2]
            K.person(ppl, random.Random(row * 10 + col_), pose, "disciple", at=tuple(p),
                     rz=RZ + math.radians(-35), cloth=9 if row % 2 == 0 else 0, cloth2=2,
                     hat="topknot", weapon="sword", jitter=2.0)
    p = Vector((cx, cy, cz)) + R @ Vector((-0.5, -5.0, 0))
    K.person(ppl, random.Random(99), "stand_hands", "robe", at=tuple(p), rz=RZ + math.pi + math.radians(-20),
             cloth=2, cloth2=9, hat="guan", jitter=0.0)
    K.emit(ppl, "Disciples", mats, "fig", thin=K.THIN)
    # pines in the clefts of the crags
    pm = MeshBuilder()
    for (dx, dy, dz, h, reach) in ((-15.0, 0.0, -12.0, 13.0, (-1, -0.3)), (13.0, 3.0, -22.0, 11.0, (1, -0.3)),
                                   (6.0, -12.0, -2.0, 8.0, (0.3, -1))):
        F.pine(pm, random.Random(int(dx * 10) % 97), height=h, lean=0.8, limbs=5,
               at=(tx + dx, ty + dy, tz + dz), cam_dir=cam_dir, crown=1.2, reach=reach)
    tp = Vector((cx, cy, cz)) + R @ Vector((11.0, 5.0, 0))
    F.pine(pm, random.Random(5), height=10.0, lean=0.9, limbs=6, at=(tp.x, tp.y, cz - 0.6), cam_dir=cam_dir, crown=1.3,
           reach=(1.0, 0.2))
    tp = Vector((cx, cy, cz)) + R @ Vector((-10.5, 6.5, 0))
    F.pine(pm, random.Random(6), height=7.0, lean=0.7, limbs=5, at=(tp.x, tp.y, cz - 0.6), cam_dir=cam_dir,
           reach=(-1.0, 0.3))
    K.emit(pm, "Pines", mats, "tree")
    cam = L.camera(CAM, TARGET, focal_mm=FOCAL)
    look = dict(
        sky=dict(stops=[(0.0, "azurite_l", 0.32), (0.16, "#C8CCC4", 0.16), (0.28, "#F0C890", 0.34),
                        (0.36, "#E8A070", 0.4), (0.44, "#F0D0A8", 0.22), (0.6, "silk", 0.0)]),
        fade=dict(d0=120.0, d1=2200.0, color=GB.mixc("silk", "#F0D8B8", 0.4), amount=0.78, gamma=0.75, cover=0.45),
        mist=[dict(y=(0.95, 1.3), scallop=20.0, dist_min=0.0, line=0.55, line_px=1.0),
              dict(y=(0.72, 1.3), scallop=26.0, dist_min=55.0, line=0.55, line_px=1.0),
              dict(y=(0.58, 0.74), scallop=18.0, dist_min=170.0, line=0.45, line_px=0.9),
              dict(y=(0.47, 0.58), scallop=12.0, dist_min=420.0, line=0.35, line_px=0.8),
              dict(y=(0.40, 0.46), soft=0.02, jitter=0.02, dist_min=900.0, amount=0.9, noise_px=120, holes=0.3)],
        mist_tint=("#F6E8D2", 0.3),
        kinds={"land": dict(w=0.9, near=40.0, far=2000.0, wfar=0.5, afar=0.4)},
    )

    def paint2d(cv, r):
        from ironart import scenes_gongbi_2d as G2
        G2.sun(cv, SUN, 15.0, color="#E07040", alpha=0.85, halo_color="#F0B880", halo=0.3)
        rr = np.random.default_rng(61)
        # cranes: white bodies with ink wing tips, necks stretched, crossing towards the temple
        for i in range(5):
            x = 0.52 + i * 0.045 + rr.uniform(-0.01, 0.01)
            y = 0.13 + i * 0.012 + rr.uniform(-0.01, 0.01)
            s = 0.012
            with cv.paint("sky", "white", 0.95) as d:
                d.stroke([(x - s * 1.2, y - s * 0.5), (x, y), (x + s * 1.2, y - s * 0.6)], 1.4, "flat")
            with cv.paint("sky", "ink", 0.85) as d:
                d.stroke([(x - s * 1.2, y - s * 0.5), (x - s * 0.8, y - s * 0.32)], 1.2, "flat")
                d.stroke([(x + s * 1.2, y - s * 0.6), (x + s * 0.8, y - s * 0.4)], 1.2, "flat")
                d.stroke([(x, y), (x - s * 1.0, y + s * 0.15)], 0.6, "flat")
    return dict(camera=cam, look=look, paint2d=paint2d,
                notes="temple crag left of centre, disciples' terrace lower right, sun right")
