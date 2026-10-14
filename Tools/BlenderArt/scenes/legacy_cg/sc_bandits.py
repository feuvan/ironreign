"""Event: Bandits - an ambush on a forest road at dusk.

The road runs away from the viewer through a tall dark forest towards the last orange glow of
the sunset; a merchant's ox cart has halted mid-road, its people cowering; bandits with
torches and blades spill out of the trees on both sides, one torch-bearer silhouetted in the
left foreground; torchlight paints the trunks orange against the blue dusk mist.
"""

import math
import random

import numpy as np
from mathutils import Matrix, Vector

from ironart import materials as M
from ironart import scenes_flora as F
from ironart import scenes_look as L
from ironart import scenes_people as P
from ironart import scenes_sky as S
from ironart import scenes_terrain as T
from ironart.geometry import MeshBuilder

SPEC = dict(name="Bandits", art="Art/Events/Bandits.png", master="Events/Bandits@2x.png",
            size=(1280, 720), ss=1, spp=28, preview_spp=12, seed=61)

GLOW = (92.0, -1.0)
ROAD = [(0, -20), (2, 20), (-4, 60), (6, 110), (0, 170), (10, 260), (4, 400)]


def road_d(X, Y):
    d, _ = T.polyline_dist(X, Y, T.smooth_path(ROAD, 6))
    return d


def ground_h(X, Y):
    d = road_d(X, Y)
    h = 1.2 * T.fbm2(X, Y, 25.0, 4, seed=1) + T.smoothstep(4.0, 40.0, d) * 4.0 * T.fbm2(X, Y, 60.0, 3, seed=2)
    h -= T.smoothstep(4.5, 1.5, d) * 0.25
    return h


def ground_material():
    from ironart.scenes_sky import G, lin4
    from ironart.scenes_terrain import _fin, noise
    mat, nb, created = M.new("ForestFloor")
    if not created:
        return mat
    b = G(nb.tree)
    P_ = nb.node("ShaderNodeNewGeometry").outputs["Position"]
    x, y, _ = b.sep(P_)
    n1 = noise(nb, P_, 0.15, 5, 0.6)
    n2 = noise(nb, P_, 2.0, 3, 0.6)
    floor = b.mix(lin4("#2E2A1E"), lin4("#4A4228"), b.smooth(n1, 0.3, 0.7))
    floor = b.mix(floor, lin4("#3A4A26"), b.math("MULTIPLY", b.smooth(n2, 0.5, 0.75), 0.6))
    road = b.mix(lin4("#7A684A"), lin4("#9A8662"), b.smooth(n2, 0.3, 0.7))
    # road mask from an attribute written per vertex
    rm = nb.node("ShaderNodeAttribute", attribute_name="road").outputs["Fac"]
    col = b.mix(floor, road, rm)
    # wheel ruts
    p = b.principled(Base_Color=col, Roughness=0.9, Specular_IOR_Level=0.25,
                     Normal=b.bump(b.math("ADD", n2, n1), 0.4, 0.05))
    return _fin(mat, nb, p.outputs[0])


def cart(mb, at, rot):
    """Two-wheeled covered cart with crates and sacks (faces -Y, origin at the axle on ground)."""
    s0 = mb.n
    mb.box((0, 0, 0.75), (1.8, 3.2, 0.14), "Wood")
    for sx in (-1, 1):
        mb.box((sx * 0.9, 0, 0.89), (0.08, 3.2, 0.5), "Wood")
        # wheel
        s1 = mb.n
        mb.lathe([(0.0, -0.06), (0.62, -0.06), (0.68, -0.04), (0.68, 0.04), (0.62, 0.06), (0.0, 0.06)], "Wood", 18)
        mb.transform(s1, Matrix.Translation((sx * 1.02, 0.2, 0.68)) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
    # shafts
    for sx in (-1, 1):
        mb.cylinder((sx * 0.55, -1.5, 0.82), (sx * 0.5, -3.6, 0.7), 0.05, 0.04, "Wood", 6)
    # canvas hood over hoops
    def hood(u, v):
        a = math.pi * u
        return (-0.85 * math.cos(a), -0.6 + 2.0 * v, 1.15 + 0.85 * math.sin(a))
    mb.grid(hood, 10, 6, "Canvas", smooth=True)
    mb.grid(hood, 10, 6, "Canvas", smooth=True, flip=True)
    for k in range(4):
        mb.box((rng_off(k) * 0.5, 1.15, 0.89 + 0.2), (0.5, 0.5, 0.42), "Crate")
    mb.sphere((0.4, 1.3, 1.2), 0.35, "Canvas", 10, 6, scale=(1.0, 1.0, 0.7))
    mb.transform(s0, Matrix.Translation(at) @ Matrix.Rotation(rot, 4, "Z"))


def rng_off(k):
    return (-1.2, -0.4, 0.4, 1.2)[k % 4]


def build(r):
    import bpy
    pv = r["preview"]
    rng = random.Random(61)
    S.build(dict(
        stops=[(-0.02, "#E89060"), (0.0, "#E89060"), (0.02, "#C87A68"), (0.06, "#7A6A88"),
               (0.16, "#3E4A78"), (0.4, "#1E2A52"), (1.0, "#0E1430")],
        strength=0.7,
        glows=[dict(dir=GLOW, color="#FF8A40", lobes=[(4, 0.5), (40, 1.4)], horizon=(0.9, 0.05, 2.0))],
        stars=dict(density=300.0, size=0.04, strength=2.5, power=10.0),
        clouds=[dict(height=2000, scale=2600, coverage=0.4, softness=0.3, lit="#C88A78",
                     shadow="#2A2A44", rim=1.5, rim_power=6.0, opacity=0.85, stretch=(1, 0.5),
                     fade=0.1, shade=6.0, seed=5.0)],
        light=dict(strength=0.55, tint="#7088C8"),
        fog=dict(haze=0.0026, haze_falloff=0.02, haze_max=0.85, haze_zmax=0.06, haze_tint="#8090B0",
                 mist=0.02, mist_falloff=0.5, mist_h0=0.0, mist_max=0.5, mist_color="#38425E"),
    ))
    S.sun(GLOW[0], 4.0, energy=0.35, color="#FF9A60", angle_deg=4.0, name="Afterglow")
    gm = ground_material()
    g = T.field_from(ground_h, -60, 60, -20, 420, 0.5 if pv else 0.35)
    X, Y = T.grid_xy(-60, 60, -20, 420, 0.5 if pv else 0.35)
    road = T.smoothstep(3.6, 2.2, road_d(X, Y))
    g.build("Ground", gm, attrs={"road": road})
    # ---- forest -------------------------------------------------------------------------------
    fm = {"Leaves": F.foliage_material("BLeaves", ("#1E2A18", "#3A4826"), translucency=0.2),
          "LeavesCore": F.foliage_material("BLeavesCore", ("#141C10", "#222C18"), core=True, translucency=0.0),
          "Needles": F.foliage_material("BNeedles", ("#141E18", "#26322A"), translucency=0.1),
          "NeedlesCore": F.foliage_material("BNeedlesCore", ("#0E1410", "#1A221C"), core=True, translucency=0.0),
          "Bark": F.bark_material("BBark", ("#2A221C", "#4A3E34"), scale=4.0)}
    tcol = F.prototypes([lambda mb: F.broadleaf(mb, random.Random(1), 22, crown=0.22, lean=0.04, trunk=0.6,
                                                leaves=60, leaf=0.3),
                         lambda mb: F.broadleaf(mb, random.Random(2), 18, crown=0.24, lean=0.06, trunk=0.55,
                                                leaves=60, leaf=0.3),
                         lambda mb: F.fir(mb, random.Random(3), 26, width=0.2),
                         lambda mb: F.chinese_pine(mb, random.Random(4), 20),
                         lambda mb: F.bush(mb, random.Random(5), 2.2),
                         lambda mb: F.bush(mb, random.Random(6), 1.6)], fm, "BTrees")
    tp = []
    for _ in range(2600 if pv else 5200):
        x = rng.uniform(-60, 60)
        y = rng.uniform(-15, 420)
        d = road_d(np.array([x]), np.array([y]))[0]
        if d < 8.5:
            continue
        k = rng.choices([0, 1, 2, 3, 4, 5], weights=[2, 2, 6, 2, 3, 3])[0]
        if k < 4 and d < 11.0:
            k = rng.choice([4, 5])
        tp.append((x, y, g.z(x, y) - 0.2, rng.uniform(0, math.tau), rng.uniform(0.8, 1.25), k))
    F.instance("Forest", tp, tcol)
    # ---- people + cart ------------------------------------------------------------------------
    mats = P.materials(cloth=["#2A2622", "#4A3A2A", "#5A4A38", "#26282C", "#6A3A26", "#8A7A60",
                              "#3A2E2A", "#2E3632", "#7A2A1E", "#C8B898", "#5E2E22", "#2E3A48"],
                       horse_coats=("#3A2A1E", "#5A4430", "#22201E", "#6A5E50"))
    mats["Canvas"] = M.principled("BCanvas", "#A89878", 0.9, vary=0.1, vary_scale=3.0)
    mats["Crate"] = M.principled("BCrate", "#5A4430", 0.8, vary=0.1)
    ppl = MeshBuilder()
    cart(ppl, (1.2, 17.0, g.z(1.2, 17.0)), 0.12)
    h = MeshBuilder()
    P.horse(h, random.Random(3), "stand", coat="HorseCoat1", saddle=None)
    ppl.extend(h, Matrix.Translation((0.7, 13.0, g.z(0.7, 13.0))) @ Matrix.Rotation(0.12, 4, "Z"))
    victims = [(3.3, 14.0, "kneel", None, 0.8, "robe", 8), (-1.2, 12.0, "bow_stand", None, 2.6, "robe", 1),
               (4.4, 19.5, "guard", "spear", 1.6, "soldier", 4)]
    bandits = [(-5.5, 13.0, "torch_high", "torch", -1.2), (-5.0, 19.0, "slash_high", "sword", -1.3),
               (7.0, 11.0, "torch_high", "torch", 1.6), (8.0, 16.5, "guard", "halberd", 1.7),
               (-7.5, 26.0, "torch_high", "torch", -1.0), (6.5, 24.0, "charge", "sword", 2.2),
               (-3.4, 7.0, "charge", "sword", -0.8), (9.5, 30.0, "torch_high", "torch", 2.0)]
    lights = []
    for i, (x, y, pose, w, rz, outfit, cl) in enumerate(victims):
        f = MeshBuilder()
        P.figure(f, random.Random(700 + i), pose, outfit, cloth=cl, cloth2=9, weapon=w,
                 hat="topknot" if outfit != "soldier" else "helmet")
        ppl.extend(f, Matrix.Translation((x, y, g.z(x, y))) @ Matrix.Rotation(rz, 4, "Z"))
    for i, (x, y, pose, w, rz) in enumerate(bandits):
        f = MeshBuilder()
        sk = P.figure(f, random.Random(800 + i), pose, "bandit", cloth=rng.choice([0, 1, 3, 6, 7]),
                      cloth2=rng.choice([2, 4, 5]), weapon=w, hat=rng.choice(["band", "hood", None]))
        m = Matrix.Translation((x, y, g.z(x, y))) @ Matrix.Rotation(rz, 4, "Z")
        ppl.extend(f, m)
        if w == "torch":
            hand = sk.arm[-1]["hand"]
            d = (sk.arm[-1]["dir"] + Vector((0, 0, 1.2))).normalized()
            fl = m @ (hand + d * 0.45 + Vector((0, 0, 0.2)))
            lights.append(fl)
    # foreground torch-bearer (left, back to camera)
    f = MeshBuilder()
    sk = P.figure(f, random.Random(901), "torch_high", "bandit", cloth=0, cloth2=1, weapon="torch",
                  hat="hood", cape=True, cape_wind=(0.3, 0.1))
    m = Matrix.Translation((-2.6, 1.5, g.z(-2.6, 1.5))) @ Matrix.Rotation(math.radians(195), 4, "Z")
    ppl.extend(f, m)
    hand = sk.arm[-1]["hand"]
    d = (sk.arm[-1]["dir"] + Vector((0, 0, 1.2))).normalized()
    lights.append(m @ (hand + d * 0.45 + Vector((0, 0, 0.2))))
    ppl.build("People", mats)
    for i, p in enumerate(lights):
        S.point(tuple(p), 900.0 if i < len(lights) - 1 else 520.0, "#FF8A3A", 0.25, name="Torch%d" % i)
    # mist banks between the trunks (blue dusk)
    for i in range(10):
        x = rng.choice([-1, 1]) * rng.uniform(8, 40)
        y = rng.uniform(20, 220)
        mm = T.mist_material("BMist%d" % i, "#4A5678", strength=0.8, density=0.5, seed=float(i * 3),
                             softness=0.5, stretch=2.5)
        T.card("BMist%d" % i, (x, y, 2.5), (rng.uniform(25, 60), rng.uniform(5, 9)), mm,
               rot_z=rng.uniform(-0.3, 0.3))
    cam = L.camera((0.4, -6.0, 1.7), (2.0, 80.0, 9.5), focal_mm=28.0, dof=(20.0, 4.0))
    return dict(camera=cam, beams=None,
                glow=dict(threshold=0.9, mix=-0.72, size=9),
                grade=dict(saturation=1.04, contrast=1.08, shadows=(-0.01, 0.0, 0.025),
                           highlights=(0.035, 0.012, -0.02), clarity=0.12, vignette=0.34,
                           canvas=0.012, sharpen=0.3))
