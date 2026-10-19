"""Event: Envoy - a carriage and its escort approach a city gate.

Morning before a great city gate: the gate tower's double eaves above crenellated walls, a marble
bridge over the moat lined with willows; down the road come outriders with tall banners, the
envoy's lacquered carriage drawn by two horses under a parasol, attendants and a rear guard;
officials and a file of guards wait at the gate.  Blue-green hills fade behind the walls."""

import math
import random

import numpy as np
from mathutils import Matrix, Vector

from ironart import scenes_gongbi as GB
from ironart import scenes_gongbi_kit as K
from ironart import scenes_gongbi_land as LD
from ironart import scenes_gongbi_flora as F
from ironart import scenes_look as L
from ironart import world_city as WC
from ironart import world_kit as WK
from ironart.geometry import MeshBuilder

SPEC = dict(name="Envoy", art="Art/Events/Envoy.png", master="Events/Envoy@2x.png",
            size=(640, 360), k=4, m=2, seed=81, spp=12, preview_spp=6)

CAM = (-22.0, -14.0, 7.5)
TARGET = (6.0, 60.0, 8.0)
FOCAL = 32.0
SM = K.ScreenMap(CAM, TARGET, FOCAL)
GATE = (8.0, 62.0, 0.0)
MOAT_Y = 44.0
ROAD = [(-40.0, -40.0), (-24.0, -10.0), (-6.0, 16.0), (4.0, 34.0), (8.0, 52.0), (8.0, 70.0)]
HILLS = [(0.10, 0.20, 900, 300, 1.8), (0.30, 0.17, 1500, 500, 1.5), (0.88, 0.15, 1200, 400, 1.6),
         (0.62, 0.12, 2600, 900, 1.3)]


def height(X, Y):
    from ironart.scenes_terrain import fbm2
    peaks = SM.peaks(HILLS)
    far = LD.peak_field(X, Y, peaks, seed=81, ridge=0.35, ridge_scale=200.0, softmax=4.0)
    near = (fbm2(X, Y, 40.0, 3, seed=2) - 0.5) * 0.8
    moat = np.clip(1.0 - np.abs(Y - MOAT_Y) / 5.0, 0, 1)
    near = near * (1 - moat) - 2.2 * np.clip(moat * 1.6, 0, 1)
    return np.maximum(near, far)


def carriage(mb, rng):
    """Envoy's carriage (local: facing -y, wheels on z=0): lacquer cabin, gilt trim, a cloth
    canopy roof with a gilt finial, shafts forward; two horses in the shafts."""
    from ironart import scenes_people as P
    for sd in (-1, 1):
        mb.cylinder((sd * 1.0, 0.2, 0.85), (sd * 1.14, 0.2, 0.85), 0.85, 0.85, "Wood", 20)
        mb.cylinder((sd * 0.95, 0.2, 0.85), (sd * 1.2, 0.2, 0.85), 0.14, 0.14, "W_Gold", 8)
    mb.box((0, 0.2, 1.0), (1.8, 2.4, 0.15), "W_LacquerDark")
    mb.box((0, 0.2, 1.15), (1.6, 2.1, 1.35), "W_Lacquer")
    mb.box((0, -0.86, 1.4), (1.0, 0.04, 0.9), "W_Lattice")
    mb.box((0, 0.2, 2.5), (1.7, 2.2, 0.1), "W_Gold")
    # canopy: a shallow four-sided cloth roof
    s0 = mb.n
    WK.roof(mb, (0, 0.2, 2.6), 1.6, 2.0, 0.9, WK.RoofSpec(style="hip", overhang=0.45, lift=0.25, flare=0.1,
                                                          tiles=False, mat="Canopy", ridge_mat="W_Gold",
                                                          chiwen=False, thick=0.08, fascia_mat="W_Gold",
                                                          under_mat="Canopy", gable_mat="Canopy"))
    mb.cylinder((0, 0.2, 3.5), (0, 0.2, 3.9), 0.08, 0.02, "W_Gold", 8)
    for sd in (-1, 1):
        mb.cylinder((sd * 0.45, -1.0, 1.0), (sd * 0.5, -4.6, 1.15), 0.05, 0.05, "Wood", 6)
    for sd in (-1, 1):
        hm = MeshBuilder()
        P.horse(hm, rng, gait="walk", coat="HorseCoat%d" % (1 if sd < 0 else 3), saddle=None)
        mb.extend(hm, Matrix.Translation((sd * 0.75, -3.2, 0.0)))


def parasol(mb, at, h=3.0, r=1.0, mat="Canopy"):
    x, y, z = at
    mb.cylinder((x, y, z), (x, y, z + h), 0.03, 0.03, "Wood", 5)
    s0 = mb.n
    mb.lathe([(0.0, 0.25), (r * 0.6, 0.12), (r, 0.0), (r, -0.25)], mat, 16, center=(x, y, z + h - 0.2), cap_top=True,
             smooth=False)


def build(r):
    rng = random.Random(81)
    pv = r["preview"]
    cols = GB.collections()
    mats = K.materials(cloth=["cinnabar", "azurite", "malachite", "#3A3530", "gold_l", "#E2D6BC",
                              "rouge", "teal", "#7A5A3A", "white", "vermilion", "indigo"],
                       banners=["cinnabar", "gold", "azurite", "white", "malachite", "vermilion"])
    mats["Canopy"] = GB.cloth("GB_Canopy", "gold", deep="#A07A30")
    hills = LD.qinglv("GB_Envoy_Land", z0=5.0, z1=500.0, cun=0.7, cun_px=7.0, cun_len=60.0,
                      moss_px=10.0, var_scale=0.004, near=100.0, far=5000.0, plain_h=0.02,
                      plain=("#C8C49C", "#D2C49A"), plain_bare=0.35, ribs=True)
    fpx = FOCAL / 36.0 * 640.0
    peaks_w = SM.peaks(HILLS)
    yaw = math.degrees(SM.yaw)
    LD.fan_terrain("Land", CAM[:2], yaw, 64.0, 5.0, 9000.0, 520, 360, height, hills, cols["land"],
                   attrs={"rib": lambda X, Y: LD.peak_ribs(X, Y, peaks_w, CAM[:2], fpx, 7.0)})
    water = LD.water("GB_Envoy_Moat", cover=0.45, spacing_px=5.0, wave_px=40.0, amp=0.25, gaps=0.7,
                     gap_len=8.0, lines=0.5, near=5.0, far=300.0, grade=(20.0, 120.0))
    wm = MeshBuilder()
    wm.box((0, MOAT_Y, -0.6), (400, 10, 0.1), "Water", skip=("bottom",))
    wm.build("Moat", {"Water": water}, col=cols["none"])

    def ground(x, y):
        return float(height(np.array([[x]]), np.array([[y]]))[0, 0])
    # ---- road (pale paving band) ----------------------------------------------------------
    road = GB.wash("GB_Envoy_Road", "#DCCCAA", "#C8B48C", grad="none", form=0.0)
    rmb = MeshBuilder()
    pts = [Vector((x, y, 0)) for (x, y) in ROAD]
    for i in range(len(pts) - 1):
        a, b_ = pts[i], pts[i + 1]
        if a.y > MOAT_Y - 6 and b_.y > MOAT_Y - 6:
            continue
        d = (b_ - a).normalized()
        side = Vector((-d.y, d.x, 0)) * 3.0
        za, zb = ground(a.x, a.y) + 0.05, ground(b_.x, b_.y) + 0.05
        ids = [rmb.v((a.x - side.x, a.y - side.y, za)), rmb.v((a.x + side.x, a.y + side.y, za)),
               rmb.v((b_.x + side.x, b_.y + side.y, zb)), rmb.v((b_.x - side.x, b_.y - side.y, zb))]
        rmb.face(ids, "Road")
    rmb.build("Road", {"Road": road}, col=cols["none"])
    # ---- the gate, walls, bridge -----------------------------------------------------------
    arch = MeshBuilder()
    g = WC.p_gate(26.0, 15.0, 10.0, 5.6, 7.4, tower=(5, 2), bay=4.2, col_h=4.8, beasts=3)
    arch.extend(g, Matrix.Translation(GATE))
    w = WC.p_wall(8.0, 9.0, 7.0)
    for i in range(1, 7):
        for sd in (-1, 1):
            arch.extend(w, Matrix.Translation((GATE[0] + sd * (13.0 + 8.0 * (i - 0.5)), GATE[1], 0.0)))
    for sd in (-1, 1):
        t = WC.p_corner_tower(11.0, 9.5, double=False)
        arch.extend(t, Matrix.Translation((GATE[0] + sd * 66.0, GATE[1] + 1.0, 0.0)))
    s0 = arch.n
    WK.bridge(arch, L=14.0, W=7.0, rise=1.4, z_bank=0.0)
    arch.transform(s0, Matrix.Translation((GATE[0], MOAT_Y, -0.6)))
    K.emit(arch, "Gate", mats, "arch")
    # ---- the procession -------------------------------------------------------------------------
    ppl = MeshBuilder()
    flags = MeshBuilder()
    from ironart import scenes_people as P

    def road_at(t):
        """point and heading along the road polyline (t in metres from its start)"""
        acc = 0.0
        for i in range(len(ROAD) - 1):
            a, b_ = Vector(ROAD[i] + (0,)), Vector(ROAD[i + 1] + (0,))
            Lg = (b_ - a).length
            if acc + Lg >= t:
                p = a + (b_ - a) * ((t - acc) / Lg)
                d = (b_ - a).normalized()
                return p, math.atan2(-d.x, d.y) + math.pi
            acc += Lg
        return Vector(ROAD[-1] + (0,)), 0.0
    head = 66.0
    for k, (dt, kind) in enumerate(((0.0, "rider_b"), (0.0, "rider_b2"), (6.0, "foot_b"), (6.0, "foot_b2"),
                                    (11.0, "carriage"), (17.0, "parasol"), (17.0, "attend"), (21.0, "rider"),
                                    (21.0, "rider2"), (26.0, "foot"), (26.0, "foot2"))):
        p, rz = road_at(head - dt)
        off = 1.6 if kind.endswith("2") else (-1.6 if kind in ("rider_b", "foot_b", "rider", "foot", "attend") else 0.0)
        side = Vector((math.cos(rz), math.sin(rz), 0.0))
        q = p + side * off
        z = ground(q.x, q.y)
        M = Matrix.Translation((q.x, q.y, z)) @ Matrix.Rotation(rz, 4, "Z")
        f = MeshBuilder()
        if kind.startswith("rider"):
            P.rider(f, random.Random(k), gait="walk", pose="ride", outfit="armored", weapon="spear",
                    hat="helmet_plume", cloth=0, cloth2=3, coat="HorseCoat%d" % (k % 4),
                    banner=0 if kind.startswith("rider_b") else None)
        elif kind == "carriage":
            carriage(f, random.Random(k))
        elif kind == "parasol":
            P.figure(f, random.Random(k), "walk", "robe", cloth=4, cloth2=9, hat="topknot", weapon="staff")
            parasol(f, (0.25, -0.1, 0.0), h=2.9, r=1.1)
        else:
            P.figure(f, random.Random(k), "walk", "soldier" if kind.startswith("foot") else "robe",
                     cloth=0 if kind.startswith("foot") else 6, cloth2=3 if kind.startswith("foot") else 9,
                     hat="helmet" if kind.startswith("foot") else "official",
                     weapon="standard" if kind.startswith("foot_b") else ("spear" if kind.startswith("foot") else None),
                     banner=1 if kind.startswith("foot_b") else None)
        ppl.extend(f, M)
    # the welcome at the gate: officials and a file of guards
    for i in range(8):
        for sd in (-1, 1):
            x = GATE[0] + sd * (4.5 + i * 1.6)
            y = MOAT_Y + 3.5 + (i % 2) * 0.4
            K.person(ppl, random.Random(200 + i * 2 + sd), "stand", "soldier", at=(x, y, ground(x, y)),
                     rz=math.radians(180 + sd * 10), cloth=1, cloth2=11, hat="helmet", weapon="spear", jitter=1.0)
    for i, x in enumerate((GATE[0] - 2.0, GATE[0], GATE[0] + 2.0)):
        K.person(ppl, random.Random(300 + i), "bow_stand", "official", at=(x, MOAT_Y + 8.5, 0.0), rz=math.radians(185),
                 cloth=[0, 1, 2][i], cloth2=9, hat="official")
    for i in range(6):
        x = GATE[0] - 10.0 + i * 4.0
        K.banner(flags, rng, color=[0, 1][i % 2], at=(x, GATE[1] - 6.0, 10.0), height=5.0, cloth=(1.4, 2.6))
    K.emit(ppl, "Procession", mats, "fig", thin=K.THIN)
    K.emit(flags, "Flags", mats, "fig", thin=K.THIN)
    # willows along the moat, a few trees by the road
    tm = MeshBuilder()
    for i in range(10):
        x = GATE[0] - 60.0 + i * 12.0 + rng.uniform(-2, 2)
        if abs(x - GATE[0]) < 9:
            continue
        F.willow(tm, random.Random(i), height=rng.uniform(8.0, 10.0), at=(x, MOAT_Y - 6.0, ground(x, MOAT_Y - 6.0)))
    pl = [("Leaf", (-30.0, 6.0, ground(-30.0, 6.0)), 0.6), ("LeafDark", (-36.0, 14.0, ground(-36.0, 14.0)), 0.7),
          ("pine", (22.0, 20.0, ground(22.0, 20.0)), 0.5)]
    K.trees(tm, pl, rng, cam_dir=Vector(TARGET) - Vector(CAM), size=1.0)
    K.emit(tm, "Trees", mats, "tree", thin=("Willow",))
    cam = L.camera(CAM, TARGET, focal_mm=FOCAL)
    look = dict(
        sky=dict(stops=[(0.0, "azurite_l", 0.25), (0.2, "azurite_l", 0.08), (0.35, "silk", 0.0)]),
        fade=dict(d0=150.0, d1=4000.0, color=GB.mixc("silk", "azurite_l", 0.2), amount=0.8, gamma=0.75, cover=0.45),
        mist=[dict(y=(0.20, 0.27), soft=0.02, jitter=0.02, dist_min=250.0, amount=1.0, noise_px=110, holes=0.2)],
        shore=dict(z=-0.6, width=0.9, alpha=0.6, eps=0.05),
    )
    return dict(camera=cam, look=look, notes="gate at centre-right; procession lower left to centre")
