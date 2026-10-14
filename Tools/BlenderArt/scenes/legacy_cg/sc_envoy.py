"""Event: Envoy - a carriage and its escort approach a great city gate.

A paved road leads from the foreground to the gate tower of a walled city; a lacquered carriage
drawn by two horses rolls towards it between mounted standard-bearers and spearmen; guards and
banners line the gate; morning sun from the left rakes across the walls, a light dust trails
the procession, soft clouds in a clear sky.
"""

import math
import random

import numpy as np
from mathutils import Matrix, Vector

from ironart import materials as M
from ironart import scenes_arch as A
from ironart import scenes_flora as F
from ironart import scenes_look as L
from ironart import scenes_people as P
from ironart import scenes_sky as S
from ironart import scenes_terrain as T
from ironart import world_kit as WK
from ironart.geometry import MeshBuilder

SPEC = dict(name="Envoy", art="Art/Events/Envoy.png", master="Events/Envoy@2x.png",
            size=(1280, 720), ss=1, spp=20, preview_spp=12, seed=71)

SUN = (200.0, 17.0)
GATE = (0.0, 150.0)


def ground_h(X, Y):
    road = np.abs(X - 0.0) < 9.0
    h = 0.8 * T.fbm2(X, Y, 30.0, 4, seed=1) + T.smoothstep(14.0, 60.0, np.abs(X)) * 3.0 * T.fbm2(X, Y, 80.0, 3, seed=2)
    h += T.smoothstep(300.0, 900.0, Y) * 160.0 * T.ridged2(X, Y, 500.0, 5, seed=3)
    return h


def carriage(mb):
    """Lacquered envoy carriage: cabin with a curved overhanging roof, two big wheels, shafts.
    Faces -Y, origin on the ground under the axle."""
    mb.box((0, 0, 1.0), (1.7, 2.4, 0.12), "W_LacquerDark")
    mb.box((0, 0, 1.12), (1.6, 2.2, 1.45), "W_Lacquer")
    for sx in (-1, 1):
        mb.box((sx * 0.81, -0.2, 1.45), (0.02, 1.0, 0.6), "W_Lattice")
        s1 = mb.n
        mb.lathe([(0.0, -0.07), (0.8, -0.07), (0.86, -0.05), (0.86, 0.05), (0.8, 0.07), (0.0, 0.07)], "W_WoodDark", 20)
        mb.transform(s1, Matrix.Translation((sx * 1.0, 0.0, 0.86)) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
    mb.box((0, -1.11, 1.25), (0.9, 0.02, 1.1), "Curtain")
    WK.roof(mb, (0, 0, 2.57), 1.7, 2.3, 0.75, WK.RoofSpec(style="hip", overhang=0.45, lift=0.25,
                                                         flare=0.1, thick=0.1, tiles=False,
                                                         mat="W_TileGold", chiwen=False))
    mb.cylinder((0, 0, 3.3), (0, 0, 3.7), 0.06, 0.0, "W_Gold", 8)
    for sx in (-1, 1):
        mb.cylinder((sx * 0.5, -1.2, 1.0), (sx * 0.45, -4.6, 1.0), 0.05, 0.045, "W_WoodDark", 6)


def build(r):
    import bpy
    pv = r["preview"]
    rng = random.Random(71)
    S.build(dict(
        stops=[(0.0, "#D8DCE0"), (0.05, "#BCC8D8"), (0.15, "#90AED4"), (0.4, "#5A84C0"),
               (1.0, "#2A5498")],
        strength=1.2,
        glows=[dict(dir=SUN, color="#FFE2B8", lobes=[(6, 0.5), (200, 5.0)], horizon=(0.4, 0.08, 2.0))],
        clouds=[dict(height=2200, scale=2600, coverage=0.42, softness=0.2, lit="#FFF6EC",
                     shadow="#8C98AC", rim=1.0, rim_power=4.0, opacity=0.9, stretch=(1.0, 0.6),
                     fade=0.12, shade=9.0, seed=12.0, haze=0.5)],
        light=dict(strength=0.75, tint="#D8E2F4"),
        fog=dict(haze=5.0e-5, haze_falloff=0.002, haze_max=0.85, haze_zmax=0.1, haze_tint="#E8E8EE",
                 mist=0.0),
    ))
    S.sun(SUN[0], SUN[1], energy=5.5, color="#FFE8CC", angle_deg=1.0)
    gm = T.terrain_material("EnvoyGround", grass=("#46682A", "#6E8A36"), dry="#9A9450",
                            dirt="#8E7A5A", slope=(0.7, 0.85), grass_scale=0.03, dry_amt=0.4)
    g = T.field_from(ground_h, -400, 400, -30, 1200, 1.0 if pv else 0.6)
    g.build("Ground", gm)
    # paved road
    wk = A.wk_materials()
    pm = P.materials(cloth=["#7A2A1E", "#2E3E5E", "#C8A050", "#3A3A30", "#6A4A2A", "#D8CCB0",
                            "#5A2E44", "#2E5A58", "#4A3628", "#E8DCC0", "#9A3020", "#24344A"],
                     banners=["#A8221A", "#C8962E", "#2F4A7A", "#E0D8C8", "#1E1E22", "#3E6A44"],
                     horse_coats=("#E8E0D2", "#6A4A30", "#2A2420", "#8A7A68"))
    mats = dict(wk)
    mats.update(pm)
    mats["Curtain"] = P.cloth_material("ECurtain", "#C8962E", sheen=0.6)
    city = MeshBuilder()
    for i in range(70):
        y = -20 + i * 2.0
        city.box((0, y, g.z(0, y) - 0.3), (12.0, 2.02, 0.42), "W_Paving")
    # ---- walls and gate -----------------------------------------------------------------------
    gx, gy = GATE
    s0 = city.n
    top = WK.gate_base(city, 46, 26, 16, 8, 10, skirt=4.0)
    city.transform(s0, WK.T(gx, gy, 0.0, 0.0))
    WK.hall(city, (gx, gy, top), WK.HallSpec(bays=(7, 3), double=True, plat_h=0.0, steps=False,
                                              bay=4.6, col_h=4.8, upper_h=3.4,
                                              roof=WK.RoofSpec(beasts=5)))
    for sx in (-1, 1):
        for k in range(14):
            x = sx * (23 + 10 + k * 20)
            s0 = city.n
            WK.wall_segment(city, 20.6, 13.0, 11.0, skirt=4.0)
            city.transform(s0, WK.T(x, gy + 2.0, 0.0, 0.0))
        for k in (1, 5, 9):
            x = sx * (23 + k * 20 + 10)
            s0 = city.n
            t2 = WK.gate_base(city, 13, 15, 15, 0.1, 0.1, doors=False, skirt=4.0)
            city.transform(s0, WK.T(x, gy - 1.0, 0.0, 0.0))
            WK.hall(city, (x, gy - 1.0, t2), WK.HallSpec(bays=(3, 3), bay=3.2, col_h=3.4, plat_h=0.0,
                                                          steps=False, brackets=False, front="wall"))
    # roofs of the city beyond the wall
    hb = []
    for i in range(6):
        rr_ = random.Random(200 + i)
        hb.append(lambda mb, rr_=rr_: WK.house(mb, (0, 0, 0), WK.HouseSpec(
            w=rr_.uniform(9, 13), d=rr_.uniform(6, 8), h=rr_.uniform(3.4, 4.2),
            roof=WK.RoofSpec(style="gable", overhang=0.75, lift=0.25, flare=0.1, thick=0.2,
                             mat="W_TileDark" if i % 2 else "W_Tile", chiwen=False, ridge_ends="curl"))))
    hcol = A.wk_prototypes(hb, mats, "EHouses")
    hp = []
    for _ in range(140 if pv else 300):
        x = rng.uniform(-320, 320)
        y = rng.uniform(gy + 22, gy + 260)
        if abs(x) < 30 and y < gy + 60:
            continue
        hp.append((x, y, g.z(x, y) - 0.4, rng.choice([0, math.pi]) + rng.uniform(-0.1, 0.1), rng.uniform(0.9, 1.1), rng.randrange(6)))
    F.instance("EHouses", hp, hcol)
    for (x, y, bays) in ((0, gy + 120, (9, 5)), (-120, gy + 90, (5, 3)), (130, gy + 140, (5, 3))):
        WK.hall(city, (x, y, g.z(x, y)), WK.HallSpec(bays=bays, bay=4.6, col_h=5.2, plat_h=1.8,
                                                      double=bays[0] > 6, tiers=2 if bays[0] > 6 else 1,
                                                      roof=WK.RoofSpec(style="hip" if bays[0] > 6 else "hip_gable",
                                                                       beasts=5)))
    WK.pagoda(city, (-200, gy + 180, g.z(-200, gy + 180)), tiers=9, R=4.6, base_h=6.0, tier_h=3.2)
    # banners on the wall top
    for k in range(-9, 10):
        if abs(k) < 2:
            continue
        x = k * 14.0
        A.banner_pole(city, random.Random(k + 50), color=[0, 1, 0, 2][k % 4], height=7.5,
                      cloth=(2.0, 3.6), at=(x, gy - 2.0, 13.0))
    A.wk_build(city, "City", mats)
    # ---- the procession -----------------------------------------------------------------------
    pro = MeshBuilder()
    cy_ = 36.0
    c = MeshBuilder()
    carriage(c)
    pro.extend(c, Matrix.Translation((0.0, cy_, g.z(0, cy_))) @ Matrix.Rotation(math.pi, 4, "Z"))
    for sx in (-1, 1):
        h = MeshBuilder()
        P.horse(h, random.Random(10 + sx), "walk", coat="HorseCoat0", saddle=None)
        pro.extend(h, Matrix.Translation((sx * 0.75, cy_ + 3.8, g.z(0, cy_ + 3.8))) @ Matrix.Rotation(math.pi, 4, "Z"))
    # mounted escort with standards, two files
    for k in range(5):
        for sx in (-1, 1):
            y = cy_ - 12.0 + k * 7.0 + (3.0 if k > 1 else 0.0)
            if abs(y - cy_) < 3.5:
                y += 6.0
            h = MeshBuilder()
            P.rider(h, random.Random(30 + k * 2 + sx), "walk", "ride_spear" if k % 2 else "ride",
                    weapon="standard" if k % 2 == 0 else "spear", hat="helmet_plume", cloth=0 if k % 2 else 1,
                    cloth2=4, coat="HorseCoat%d" % ((k + sx) % 4), banner=(k + (sx > 0)) % 3)
            pro.extend(h, Matrix.Translation((sx * 4.2, y, g.z(sx * 4.2, y))) @ Matrix.Rotation(math.pi + rng.uniform(-0.05, 0.05), 4, "Z"))
    # foot soldiers following
    for k in range(4):
        for sx in (-1, 1):
            y = cy_ - 14.0 - k * 2.2
            f = MeshBuilder()
            P.figure(f, random.Random(400 + k * 2 + sx), "march_spear", "armored", cloth=0, cloth2=4,
                     weapon="spear", hat="helmet", jitter=3.0)
            pro.extend(f, Matrix.Translation((sx * 2.2 + rng.uniform(-0.2, 0.2), y, g.z(0, y))) @ Matrix.Rotation(math.pi, 4, "Z"))
    # gate guards lining the road
    for k in range(6):
        for sx in (-1, 1):
            y = gy - 20 - k * 6.0
            f = MeshBuilder()
            P.figure(f, random.Random(600 + k * 2 + sx), "stand", "armored", cloth=1, cloth2=4,
                     weapon="halberd", hat="helmet_plume", jitter=2.0)
            pro.extend(f, Matrix.Translation((sx * 7.0, y, g.z(sx * 7, y))) @ Matrix.Rotation(-sx * math.pi / 2, 4, "Z"))
    # onlookers at the roadside bowing as the envoy passes (both sides, muted clothes)
    for k in range(12):
        sx = -1 if k < 8 else 1
        x = sx * (10.5 + rng.uniform(0, 3.5))
        y = 16 + (k % 8) * 3.2 + rng.uniform(-0.8, 0.8)
        f = MeshBuilder()
        P.figure(f, random.Random(650 + k), rng.choice(["kneel_bow", "bow_stand", "kneel_bow", "stand_hands"]),
                 rng.choice(["peasant", "robe", "lady"]), cloth=rng.choice([3, 4, 7, 8, 11, 5]),
                 cloth2=rng.choice([5, 9, 3]), hat=rng.choice([None, "straw", "topknot"]))
        pro.extend(f, Matrix.Translation((x, y, g.z(x, y))) @ Matrix.Rotation(sx * math.radians(90 + rng.uniform(-15, 15)), 4, "Z"))
    pro.build("Procession", mats)
    # trees along the moat/road
    fm = {"Leaves": F.foliage_material("ELeaves", ("#3E5A2C", "#7A8A3E"), translucency=0.3),
          "LeavesCore": F.foliage_material("ELeavesCore", ("#2A3A20", "#44542C"), core=True, translucency=0.0),
          "WLeaves": F.foliage_material("EWillow", ("#5E7A30", "#9AAA48"), translucency=0.45, vary=0.4),
          "WLeavesCore": F.foliage_material("EWillowCore", ("#34461E", "#4A5A28"), core=True, translucency=0.0),
          "Bark": F.bark_material("EBark")}
    tcol = F.prototypes([lambda mb: F.broadleaf(mb, random.Random(1), 12, leaves=70, leaf=0.24, clumps=12),
                         lambda mb: F.broadleaf(mb, random.Random(2), 10, leaves=70, leaf=0.22, clumps=11),
                         lambda mb: F.willow(mb, random.Random(5), 10.5, mat="WLeaves", core=None, strands=16, leaf=0.24, droop=0.62),
                         lambda mb: F.willow(mb, random.Random(6), 9.0, mat="WLeaves", core=None, strands=16, leaf=0.24, droop=0.62)],
                        fm, "ETrees")
    tp = []
    # an avenue of weeping willows lining the approach (the farewell trees of the capital)
    for k in range(14):
        for sx in (-1, 1):
            y = 24 + k * 8.0
            x = sx * (20 + rng.uniform(0, 3))
            tp.append((x, y, g.z(x, y) - 0.2, rng.uniform(0, math.tau), rng.uniform(0.85, 1.1), 2 + rng.randrange(2)))
    for _ in range(1500 if pv else 3000):
        x = rng.uniform(-400, 400)
        y = rng.uniform(400, 1200)
        tp.append((x, y, g.z(x, y) - 0.3, rng.uniform(0, math.tau), rng.uniform(0.8, 1.3), rng.randrange(2)))
    F.instance("ETrees", tp, tcol)
    # grass tufts and a few wild flowers on the verges near the camera
    gmats = {"Grass": F.foliage_material("EGrass", ("#4A6A26", "#86983E"), translucency=0.4, vary=0.5),
             "Flower": F.foliage_material("EFlower", ("#E8D890", "#F2EEDC"), translucency=0.3, vary=0.5)}
    gcol = F.prototypes([lambda mb, i=i: F.grass_tuft(mb, random.Random(i), 0.32, 14, "Grass" if i < 3 else "Flower", 0.1)
                         for i in range(4)], gmats, "EGrass")
    gp = []
    for _ in range(9000 if pv else 26000):
        x = rng.uniform(-40, 40)
        y = rng.uniform(-6, 70)
        if abs(x) < 6.8:
            continue
        kind = 3 if rng.random() < 0.06 else rng.randrange(3)
        gp.append((x, y, g.z(x, y) - 0.02, rng.uniform(0, math.tau), rng.uniform(0.7, 1.4), kind))
    F.instance("EGrassTufts", gp, gcol)
    # dust trailing the procession
    for i in range(3):
        dm = T.mist_material("EDust%d" % i, "#DCCBB0", strength=1.05, density=0.22, seed=float(i),
                             softness=0.6, stretch=2.0, edge=0.3)
        T.card("EDust%d" % i, (rng.uniform(-4, 4), cy_ + 10 + i * 9, 1.4), (22, 3), dm)
    cam = L.camera((-5.0, -8.0, 3.6), (1.0, gy, 12.0), focal_mm=32.0, dof=(44.0, 11.0))
    return dict(camera=cam, beams=None,
                glow=dict(threshold=1.2, mix=-0.88, size=8),
                grade=dict(saturation=1.14, contrast=1.2, shadows=(0.0, 0.004, 0.018),
                           highlights=(0.02, 0.01, -0.012), clarity=0.12, vignette=0.22,
                           canvas=0.012, sharpen=0.3))
