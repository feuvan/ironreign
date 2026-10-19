"""Event: Envoy - a carriage and its escort approach a city gate.

A morning view from a low rise outside the capital (the World Models tier-3 city, painted in the
ruled-line 界画 manner): the double-eaved gate tower above the crenellated wall, the moat with
an arched marble bridge and willows along its banks; down the winding road come outriders with
tall banners, standard bearers, the envoy's lacquered carriage under a gilt canopy drawn by two
horses, a parasol bearer and attendants, a mounted rear guard.  Officials wait bowing at the
bridge between two files of guards.  Palace roofs and pagodas rise behind the wall; blue-green
mountains and bands of mist close the view."""

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

SPEC = dict(name="Envoy", art="Art/Events/Envoy.png", master="Events/Envoy@2x.png",
            size=(640, 360), k=4, m=2, seed=81, spp=6, preview_spp=4)

CAM = (-60.0, -152.0, 30.0)
TARGET = (6.0, -58.0, 9.0)
FOCAL = 31.0
SM = K.ScreenMap(CAM, TARGET, FOCAL)
MOAT_Y = -61.0
ROAD = [(0.0, -50.0), (0.0, -64.0), (-1.5, -74.0), (-7.0, -88.0), (-17.0, -101.0), (-31.0, -114.0),
        (-49.0, -127.0), (-72.0, -139.0), (-100.0, -150.0)]
MOUNTAINS = [(0.04, 0.10, 800, 300, 1.6), (0.27, 0.06, 1400, 520, 1.4), (0.60, 0.04, 2300, 800, 1.3),
             (0.93, 0.08, 1000, 360, 1.7)]


def height(X, Y):
    from ironart.scenes_terrain import fbm2
    peaks = SM.peaks(MOUNTAINS)
    far = LD.peak_field(X, Y, peaks, seed=81, ridge=0.35, ridge_scale=220.0, softmax=4.0)
    near = (fbm2(X, Y, 60.0, 3, seed=2) - 0.5) * 1.2
    # flat ground round the city, a gentle rise towards the camera
    city = np.clip(1.0 - np.maximum(np.abs(X) - 60.0, 0) / 40.0, 0, 1) * np.clip(1.0 - np.maximum(Y + 70.0, 0) / 1.0, 0, 1)
    near = near * (1.0 - 0.8 * city) + np.clip(-(Y + 110.0) / 60.0, 0, 1) * 2.5
    moat = np.clip(1.0 - np.abs(Y - MOAT_Y) / 4.5, 0, 1) * (np.abs(X) < 140.0)
    near = near * (1 - moat) - 2.4 * np.clip(moat * 1.8, 0, 1)
    return np.where(far > 0.5, np.maximum(far, near), near)


def carriage(mb, rng, coats=("HorseCoat0", "HorseCoat3")):
    """Envoy's carriage (local: facing -y, wheels on z=0): lacquer cabin with lattice windows,
    gilt trim, a cloth canopy roof with a gilt finial, shafts forward to two horses."""
    from ironart import scenes_people as P
    for sd in (-1, 1):
        mb.cylinder((sd * 1.0, 0.2, 0.85), (sd * 1.14, 0.2, 0.85), 0.85, 0.85, "Wood", 24)
        mb.cylinder((sd * 0.95, 0.2, 0.85), (sd * 1.2, 0.2, 0.85), 0.14, 0.14, "W_Gold", 8)
        for k in range(8):
            a = k / 8 * math.tau
            mb.cylinder((sd * 1.07, 0.2, 0.85), (sd * 1.07, 0.2 + math.cos(a) * 0.78, 0.85 + math.sin(a) * 0.78),
                        0.025, 0.025, "Wood", 4)
    mb.box((0, 0.2, 1.0), (1.8, 2.4, 0.15), "W_LacquerDark")
    mb.box((0, 0.2, 1.15), (1.6, 2.1, 1.35), "W_Lacquer")
    for sd in (-1, 1):
        mb.box((sd * 0.81, 0.2, 1.45), (0.04, 1.2, 0.75), "W_Lattice")
    mb.box((0, -0.86, 1.4), (1.0, 0.04, 0.9), "W_Lattice")
    mb.box((0, 0.2, 2.5), (1.7, 2.2, 0.1), "W_Gold")
    WK.roof(mb, (0, 0.2, 2.6), 1.6, 2.0, 0.9, WK.RoofSpec(style="hip", overhang=0.45, lift=0.25, flare=0.1,
                                                          tiles=False, mat="Canopy", ridge_mat="W_Gold",
                                                          chiwen=False, thick=0.08, fascia_mat="W_Gold",
                                                          under_mat="Canopy", gable_mat="Canopy"))
    mb.cylinder((0, 0.2, 3.5), (0, 0.2, 3.9), 0.08, 0.02, "W_Gold", 8)
    for sd in (-1, 1):
        mb.cylinder((sd * 0.45, -1.0, 1.0), (sd * 0.5, -4.6, 1.15), 0.05, 0.05, "Wood", 6)
        hm = MeshBuilder()
        P.horse(hm, rng, gait="walk", coat=coats[0 if sd < 0 else 1], saddle="Saddle", cloth="Banner1")
        mb.extend(hm, Matrix.Translation((sd * 0.75, -3.6, 0.0)))


def parasol(mb, at, h=3.0, r=1.0, mat="Canopy"):
    """Ceremonial parasol (华盖): pole, a shallow canopy with a hanging valance."""
    x, y, z = at
    mb.cylinder((x, y, z), (x, y, z + h), 0.03, 0.03, "Wood", 5)
    mb.lathe([(0.0, 0.28), (r * 0.6, 0.14), (r, 0.0), (r, -0.32)], mat, 20, center=(x, y, z + h - 0.2), cap_top=True,
             smooth=False)
    mb.cylinder((x, y, z + h + 0.05), (x, y, z + h + 0.3), 0.06, 0.01, "W_Gold", 6)


def build(r):
    rng = random.Random(81)
    cols = GB.collections()
    mats = K.materials(cloth=["cinnabar", "azurite", "malachite", "#3A3530", "gold_l", "#E2D6BC",
                              "rouge", "teal", "#7A5A3A", "white", "vermilion", "indigo"],
                       banners=["cinnabar", "gold", "azurite", "white", "malachite", "vermilion"])
    mats["Canopy"] = GB.cloth("GB_Canopy", "gold", deep="#A07A30")
    hills = LD.qinglv("GB_Envoy_Land", z0=4.0, z1=300.0, cun=0.7, cun_px=7.0, cun_len=60.0,
                      moss_px=10.0, var_scale=0.004, near=150.0, far=5000.0, plain_h=0.03,
                      plain=("#CFCB9E", "#D8C9A0"), plain_bare=0.4, ribs=True)
    fpx = FOCAL / 36.0 * 640.0
    peaks_w = SM.peaks(MOUNTAINS)
    yaw = math.degrees(SM.yaw)
    LD.fan_terrain("Land", CAM[:2], yaw, 62.0, 8.0, 9000.0, 560, 400, height, hills, cols["land"],
                   attrs={"rib": lambda X, Y: LD.peak_ribs(X, Y, peaks_w, CAM[:2], fpx, 7.0)})
    water = LD.water("GB_Envoy_Moat", cover=0.5, spacing_px=4.0, wave_px=36.0, amp=0.25, gaps=0.7,
                     gap_len=8.0, lines=0.45, near=5.0, far=400.0, grade=(30.0, 160.0))
    wm = MeshBuilder()
    wm.box((0, MOAT_Y, -1.6), (300, 8.4, 0.1), "Water", skip=("bottom",))
    wm.build("Moat", {"Water": water}, col=cols["none"])

    def ground(x, y):
        return float(height(np.array([[x]]), np.array([[y]]))[0, 0])
    # ---- road: a pale earth band with fine wheel ruts -----------------------------------------
    road = LD.ground("GB_Envoy_Road", color="#E8DCC0", deep="#D6C6A2", cover=0.9, grass=0.0, blotch=0.15)
    rmb = MeshBuilder()
    pts = [Vector((x, y, 0)) for (x, y) in ROAD]
    for i in range(len(pts) - 1):
        a, b_ = pts[i], pts[i + 1]
        if a.y > MOAT_Y - 4.5 and b_.y > MOAT_Y - 4.5:
            continue
        d = (b_ - a).normalized()
        side = Vector((-d.y, d.x, 0)) * (3.0 + 0.04 * i * i)
        za, zb = ground(a.x, a.y) + 0.06, ground(b_.x, b_.y) + 0.06
        ids = [rmb.v((a.x - side.x, a.y - side.y, za)), rmb.v((a.x + side.x, a.y + side.y, za)),
               rmb.v((b_.x + side.x, b_.y + side.y, zb)), rmb.v((b_.x - side.x, b_.y - side.y, zb))]
        rmb.face(ids, "Road", smooth=True)
    rmb.build("Road", {"Road": road}, col=cols["fine"])
    # ---- the capital: tier-3 city without its barbican, the gate facing the road ---------------
    city, ctrees = K.city(3, at=(0.0, 0.0, 0.0), skip=("arrow", "bwall"))
    s0 = city.n
    WK.bridge(city, L=12.0, W=7.0, rise=1.0, z_bank=-0.2)
    city.transform(s0, Matrix.Translation((0.0, MOAT_Y, -0.4)))
    K.emit(city, "City", mats, "arch")
    tm = MeshBuilder()
    K.trees(tm, ctrees, random.Random(5), cam_dir=Vector(TARGET) - Vector(CAM), size=1.0, low=True)
    # ---- the procession -----------------------------------------------------------------------
    from ironart import scenes_people as P
    ppl = MeshBuilder()
    flags = MeshBuilder()

    def road_at(t):
        """point and heading (rz turning a -Y-facing figure towards the gate) t metres from the
        bridge along the road."""
        acc = 0.0
        for i in range(1, len(ROAD) - 1):
            a, b_ = Vector(ROAD[i] + (0,)), Vector(ROAD[i + 1] + (0,))
            Lg = (b_ - a).length
            if acc + Lg >= t:
                p = a + (b_ - a) * ((t - acc) / Lg)
                d = (a - b_).normalized()             # walking direction: towards the gate
                return p, math.atan2(d.x, -d.y) + math.pi
            acc += Lg
        return Vector(ROAD[-1] + (0,)), 0.0
    order = [(9.0, "rider_b", -1.5), (9.0, "rider_b", 1.5), (14.5, "foot_b", -1.6), (14.5, "foot_b", 1.6),
             (19.0, "foot", -1.5), (19.0, "foot", 1.5), (26.5, "carriage", 0.0), (33.5, "parasol", 0.3),
             (33.0, "attend", -1.7), (33.0, "attend", 1.9), (37.0, "attend2", -1.2), (37.0, "attend2", 1.4),
             (42.5, "rider", -1.5), (42.5, "rider", 1.5), (48.0, "rider_b", -1.5), (48.0, "rider", 1.5),
             (53.5, "foot", -1.5), (53.5, "foot", 1.5)]
    for k, (dt, kind, off) in enumerate(order):
        p, rz = road_at(dt)
        side = Vector((math.cos(rz), math.sin(rz), 0.0))
        q = p + side * off
        z = ground(q.x, q.y)
        M = Matrix.Translation((q.x, q.y, z)) @ Matrix.Rotation(rz + rng.uniform(-0.05, 0.05), 4, "Z")
        f = MeshBuilder()
        if kind.startswith("rider"):
            P.rider(f, random.Random(k), gait="walk", pose="ride", outfit="armored",
                    weapon="spear" if kind == "rider" else None, hat="helmet_plume", cloth=0, cloth2=3,
                    coat="HorseCoat%d" % [1, 0, 3, 2, 4][k % 5],
                    banner=[0, 1][k % 2] if kind == "rider_b" else None, saddle_cloth="Banner%d" % (k % 2))
        elif kind == "carriage":
            carriage(f, random.Random(k))
        elif kind == "parasol":
            P.figure(f, random.Random(k), "walk", "robe", cloth=0, cloth2=9, hat="topknot", jitter=2.0)
            parasol(f, (-0.25, -0.15, 0.0), h=3.0, r=1.15)
        elif kind.startswith("attend"):
            P.figure(f, random.Random(k), "walk", "robe" if kind == "attend" else "official",
                     cloth=[4, 6, 10, 1][k % 4], cloth2=9, hat="topknot" if kind == "attend" else "official",
                     jitter=3.0)
        else:
            P.figure(f, random.Random(k), "walk" if kind == "foot_b" else "march_spear", "soldier",
                     cloth=0, cloth2=3, hat="helmet",
                     weapon="standard" if kind == "foot_b" else "spear",
                     banner=[1, 0][k % 2] if kind == "foot_b" else None, jitter=3.0)
        ppl.extend(f, M)
    # the welcome at the gate: two files of guards along the bridge approach, officials bowing
    for i in range(7):
        for sd in (-1, 1):
            p, rz = road_at(-2.0 + i * 1.7) if i else (Vector((0.0, MOAT_Y - 4.0, 0.0)), math.pi)
            x, y = sd * (4.6 + 0.0), MOAT_Y - 5.0 - i * 1.8
            K.person(ppl, random.Random(200 + i * 2 + sd), "stand", "soldier", at=(x, y, ground(x, y)),
                     rz=math.radians(-90 * sd), cloth=1, cloth2=11, hat="helmet", weapon="spear", jitter=1.0)
    for i, x in enumerate((-2.2, 0.0, 2.2)):
        y = MOAT_Y - 5.5 - abs(x) * 0.3
        K.person(ppl, random.Random(300 + i), "bow_stand", "official", at=(x, y, ground(x, y)), rz=math.radians(180),
                 cloth=[1, 0, 2][i], cloth2=9, hat="official")
    # banners on the wall walk either side of the gate
    for i in range(8):
        x = -40.0 + i * 11.4 if i < 4 else -40.0 + i * 11.4 + 0.0
        if abs(x) < 14:
            continue
        K.banner(flags, rng, color=[0, 1][i % 2], at=(x, -44.5, 10.0), height=5.5, cloth=(1.4, 2.6))
    K.emit(ppl, "Procession", mats, "fig", thin=K.THIN)
    K.emit(flags, "Flags", mats, "fig", thin=K.THIN)
    # willows along the moat, trees framing the road
    for i in range(13):
        x = -70.0 + i * 11.0 + rng.uniform(-2, 2)
        if abs(x) < 10:
            continue
        F.willow(tm, random.Random(i), height=rng.uniform(8.0, 10.0), at=(x, MOAT_Y - 7.0, ground(x, MOAT_Y - 7.0)))
    pl = [("pine", (-40.0, -92.0, ground(-40.0, -92.0)), 0.55), ("LeafDark", (-52.0, -84.0, ground(-52.0, -84.0)), 0.6),
          ("Leaf", (26.0, -100.0, ground(26.0, -100.0)), 0.55), ("pine", (34.0, -88.0, ground(34.0, -88.0)), 0.5),
          ("LeafDark", (-62.0, -70.0, ground(-62.0, -70.0)), 0.5)]
    # the roadside pavilion (长亭) where envoys are met, in a grove on the right
    pv_ = MeshBuilder()
    K.pavilion(pv_, at=(30.0, -108.0, ground(30.0, -108.0)), n=6, R=2.6, col_h=3.0, roof_h=2.4)
    K.emit(pv_, "Pavilion", mats, "arch")
    for (x, y, kind, sz) in ((40.0, -100.0, "Leaf", 0.55), (46.0, -114.0, "pine", 0.55), (22.0, -96.0, "LeafDark", 0.45),
                             (52.0, -92.0, "Leaf", 0.5), (38.0, -124.0, "LeafDark", 0.5)):
        pl.append((kind, (x, y, ground(x, y)), sz))
    for (x, y, kind, sz) in ((70.0, -70.0, "Leaf", 0.5), (80.0, -84.0, "LeafDark", 0.55), (62.0, -58.0, "pine", 0.45),
                             (95.0, -66.0, "Leaf", 0.5), (-80.0, -100.0, "LeafDark", 0.55)):
        pl.append((kind, (x, y, ground(x, y)), sz))
    K.trees(tm, pl, rng, cam_dir=Vector(TARGET) - Vector(CAM), size=1.0)
    K.emit(tm, "Trees", mats, "tree", thin=("Willow",))
    cam = L.camera(CAM, TARGET, focal_mm=FOCAL)
    look = dict(
        sky=dict(stops=[(0.0, "azurite_l", 0.28), (0.12, "azurite_l", 0.1), (0.22, "silk", 0.0)]),
        fade=dict(d0=180.0, d1=4000.0, color=GB.mixc("silk", "azurite_l", 0.15), amount=0.75, gamma=0.75, cover=0.4),
        mist=[dict(z=(0.0, 14.0), soft=6.0, jitter=6.0, dist=(130.0, 220.0), amount=0.85, noise_px=120, holes=0.3),
              dict(y=(0.36, 0.44), x=(0.7, 1.1), soft=0.03, jitter=0.03, dist_min=120.0, amount=0.7, noise_px=90, holes=0.35),
              dict(y=(0.12, 0.30), soft=0.03, jitter=0.03, dist_min=400.0, amount=0.95, noise_px=120, holes=0.25)],
        shore=dict(z=-1.5, width=0.8, alpha=0.6, eps=0.08),
    )
    return dict(camera=cam, look=look, notes="gate at centre-right; procession lower left to centre")
