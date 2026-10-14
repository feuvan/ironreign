"""Event: Harvest - golden terraced rice fields at sunset.

Curving terraces follow the contours of a valley; most hold ripe golden rice, some are flooded
and mirror the sunset sky, some are cut to stubble with sheaves stooked on them.  Farmers in
straw hats bend over the harvest in the foreground; a thatched hamlet sits on the far slope with
cooking smoke; hills fade into warm haze; the sun sets ahead-left.
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
from ironart.geometry import MeshBuilder

SPEC = dict(name="Harvest", art="Art/Events/Harvest.png", master="Events/Harvest@2x.png",
            size=(1280, 720), ss=1, spp=128, preview_spp=16, seed=31)

SUN = (150.0, 5.0)
STEP = 1.6          # terrace rise (m)


def base_height(X, Y):
    """Valley: hills rising on both sides and behind, a stream along the valley floor."""
    v = T.fbm2(X, Y, 220.0, 4, seed=4)
    side = np.abs(X - 40.0 - 60.0 * np.sin(Y / 160.0)) / 220.0
    h = 9.0 + 70.0 * side ** 1.6 + 35.0 * T.smoothstep(150.0, 700.0, Y) + 30.0 * (v - 0.5)
    h += 160.0 * T.smoothstep(500.0, 1100.0, Y) * T.ridged2(X, Y, 400.0, 5, seed=6)
    return h


def terraced(X, Y):
    h = base_height(X, Y)
    t = h / STEP
    fr = t - np.floor(t)
    q = (np.floor(t) + T.smoothstep(0.86, 1.0, fr)) * STEP
    w = T.smoothstep(560.0, 420.0, Y)          # only the near valley is terraced
    return (q * w + h * (1 - w)).astype(np.float32)


def paddy_material():
    """Terrace surfaces: per-terrace (floor(z / STEP)) choice of ripe rice / flooded mirror /
    stubble; bund walls (steep) are earth with grass."""
    from ironart.scenes_sky import G, lin4
    from ironart.scenes_terrain import _fin, noise
    mat, nb, created = M.new("Paddy")
    if not created:
        return mat
    b = G(nb.tree)
    geo = nb.node("ShaderNodeNewGeometry")
    P_ = geo.outputs["Position"]
    nz = b.sep(geo.outputs["Normal"])[2]
    z = b.sep(P_)[2]
    tid = b.math("FLOOR", b.math("DIVIDE", b.math("ADD", z, STEP * 0.07), STEP))
    wn = nb.node("ShaderNodeTexWhiteNoise", noise_dimensions="1D")
    b.link(tid, wn.inputs["W"])
    rnd = wn.outputs["Value"]
    # rice: golden with darker rows and sheen
    n1 = noise(nb, P_, 0.06, 4, 0.55)
    n2 = noise(nb, b.vmath("SCALE", P_, scale=3.0).outputs[0], 1.0, 4, 0.6)
    rice = b.mix(lin4("#A07A2A"), lin4("#D8B054"), b.smooth(n1, 0.3, 0.7))
    rice = b.mix(rice, b.cmul(rice, 0.72), b.smooth(n2, 0.55, 0.8))
    rice = b.mix(rice, lin4("#8E8A3A"), b.math("MULTIPLY", b.smooth(rnd, 0.75, 0.82), 0.6))
    stub = b.mix(lin4("#7A6038"), lin4("#9A7A48"), b.smooth(n2, 0.3, 0.7))
    is_stub = b.math("MULTIPLY", b.smooth(rnd, 0.62, 0.64), b.smooth(rnd, 0.76, 0.74))
    col = b.mix(rice, stub, is_stub)
    is_water = b.smooth(rnd, 0.86, 0.87)
    bund = b.smooth(nz, 0.93, 0.8)
    earth = b.mix(lin4("#5E5230"), lin4("#6E7038"), b.smooth(n1, 0.3, 0.7))
    col = b.mix(col, earth, bund)
    rough = b.mix((0.75, 0.75, 0.75, 1), (0.02, 0.02, 0.02, 1), b.math("MULTIPLY", is_water, b.math("SUBTRACT", 1.0, bund)))
    wcol = b.mix(col, lin4("#3A3A36"), b.math("MULTIPLY", is_water, b.math("SUBTRACT", 1.0, bund)))
    rgh = b.sep(rough)[0]
    p = b.principled(Base_Color=wcol, Roughness=rgh, Specular_IOR_Level=0.5, Sheen_Weight=0.5,
                     Sheen_Roughness=0.3, Sheen_Tint=lin4("#FFE0A0"),
                     Normal=b.bump(n2, 0.35, 0.05))
    return _fin(mat, nb, p.outputs[0])


def sheaf(mb, rng, at, mat="Straw"):
    """A stook: 6-8 sheaves leaning together."""
    x, y, z = at
    n = rng.randint(6, 8)
    for k in range(n):
        a = math.tau * k / n
        b0 = Vector((x + math.cos(a) * 0.35, y + math.sin(a) * 0.35, z))
        top = Vector((x + math.cos(a) * 0.05, y + math.sin(a) * 0.05, z + 1.15))
        mb.cylinder(tuple(b0), tuple(top), 0.16, 0.1, mat, 7)
        mb.cylinder(tuple(top), tuple(top + (top - b0).normalized() * 0.35 + Vector((0, 0, 0.05))), 0.1, 0.18, mat, 7)


def build(r):
    import bpy
    pv = r["preview"]
    rng = random.Random(31)
    S.build(dict(
        stops=[(0.0, "#FFC88A"), (0.03, "#F6B07C"), (0.1, "#E4A890"), (0.22, "#B4A4B4"),
               (0.45, "#7E8CB0"), (1.0, "#4A5A86")],
        strength=1.1,
        glows=[dict(dir=SUN, color="#FFA850", lobes=[(3, 0.9), (20, 2.4), (400, 16.0)],
                    horizon=(1.6, 0.06, 1.5))],
        discs=[dict(dir=SUN, radius_deg=0.7, color="#FFE6B8", strength=60.0)],
        clouds=[dict(height=2600, scale=3600, coverage=0.45, softness=0.24, lit="#FFC88E",
                     shadow="#8A6E78", rim_color="#FFDCA0", rim=2.5, rim_power=4.0, opacity=0.9,
                     stretch=(1.0, 0.5), fade=0.14, shade=8.0, seed=11.0, haze=0.55)],
        light=dict(strength=0.5, tint="#D8D4E8"),
        fog=dict(haze=1.4e-4, haze_falloff=0.0012, haze_max=0.9, haze_zmax=0.08,
                 mist=0.0016, mist_falloff=0.05, mist_h0=0.0, mist_max=0.6,
                 mist_color="#F0D2B0", mist_strength=1.0),
    ))
    S.sun(SUN[0], SUN[1] + 1.0, energy=5.0, color="#FFB874", angle_deg=1.0)
    # ---- terrain ----------------------------------------------------------------------------
    pm = paddy_material()
    near = T.field_from(terraced, -140, 220, -40, 140, 0.5 if pv else 0.3)
    near.build("PaddyNear", pm)
    mid = T.field_from(terraced, -520, 620, 138, 560, 1.2 if pv else 0.7)
    mid.build("PaddyMid", pm)
    gm = T.terrain_material("HarvestHills", grass=("#4E5E30", "#76703C"), dry="#9A8248",
                            rock=("#6A6058", "#8A8070"), slope=(0.7, 0.85), grass_scale=0.01)
    T.field_from(terraced, -1600, 1800, 556, 2600, 6.0).build("Hills", gm)
    rm = T.terrain_material("HarvestRange", grass=("#5A6048", "#6E6A50"), rock=("#5E5A58", "#7E7A74"),
                            slope=(0.72, 0.86), grass_scale=0.002)

    def rfn(X, Y):
        return T.ridged2(X, Y, 900.0, 6, sharp=1.8, seed=9, warp=500.0) ** 1.3 * 700.0 + 100.0
    T.field_from(rfn, -7000, 8000, 2500, 9000, 30.0).build("Range", rm)
    # ---- village on the far slope + trees -----------------------------------------------------
    am = A.materials(thatch="#8C744A")
    pmats = P.materials(cloth=["#3E4A5E", "#5A4A36", "#7A6A50", "#2E3A30", "#8A5A3A", "#B8AA8A",
                               "#4A3A2E", "#6A6E5A", "#5A3022", "#C8BCA0", "#7A3A26", "#3A4A4E"])
    mats = dict(am)
    mats.update(pmats)
    vil = MeshBuilder()
    for i in range(14):
        x = rng.uniform(-260, -60)
        y = rng.uniform(420, 520)
        z = T.sample(mid.h, mid.x0, mid.x1, mid.y0, mid.y1, x, min(y, 555)) if y < 556 else base_height(np.array([x]), np.array([y]))[0]
        hb = A.scaled(A.thatched_house(random.Random(i), 1.0, foundation=0.5), 6.0, (x, y, z - 0.6),
                      rot_z=rng.uniform(-0.4, 0.4))
        vil.extend(hb)
    vil.build("Village", mats)
    fm = {"Leaves": F.foliage_material("HLeaves", ("#3A4A24", "#7A7A34"), translucency=0.35),
          "LeavesCore": F.foliage_material("HLeavesCore", ("#2A3218", "#44482A"), core=True, translucency=0.0),
          "Needles": F.foliage_material("HNeedles", ("#24302A", "#3E4A34"), translucency=0.2),
          "NeedlesCore": F.foliage_material("HNeedlesCore", ("#1A2420", "#2C3A28"), core=True, translucency=0.0),
          "Bark": F.bark_material("HBark"),
          "Bamboo": M.principled("HBamboo", "#6E7A44", 0.5),
          "BambooLeaves": F.foliage_material("HBambooLeaves", ("#4E6230", "#8A9044"), translucency=0.35)}
    tcol = F.prototypes([lambda mb: F.broadleaf(mb, random.Random(1), 12),
                         lambda mb: F.broadleaf(mb, random.Random(2), 9),
                         lambda mb: F.bamboo(mb, random.Random(3), 10, stems=14),
                         lambda mb: F.chinese_pine(mb, random.Random(4), 12)], fm, "HTrees")
    hills = T.Field(np.zeros((2, 2)), 0, 1, 0, 1)
    tp = []
    for _ in range(3000 if pv else 9000):
        x = rng.uniform(-1600, 1800)
        y = rng.uniform(470, 2400)
        z = base_height(np.array([x]), np.array([y]))[0]
        if y < 556 and abs(x + 160) < 140:
            continue
        if z < 30 and y < 900:
            continue
        tp.append((x, y, z - 0.5, rng.uniform(0, math.tau), rng.uniform(0.8, 1.3), rng.choice([0, 0, 1, 3])))
    # bamboo groves around the hamlet
    for _ in range(40):
        x = rng.uniform(-300, -20)
        y = rng.uniform(430, 540)
        z = base_height(np.array([x]), np.array([y]))[0]
        tp.append((x, y, z - 0.3, rng.uniform(0, math.tau), rng.uniform(0.9, 1.2), 2))
    F.instance("Trees", tp, tcol)
    # ---- rice plants in the near terraces (texture close to the camera) --------------------
    rice_m = {"Grass": F.foliage_material("RiceStalk", ("#A8822E", "#E0BC5C"), translucency=0.4, vary=0.4)}
    rcol = F.prototypes([lambda mb, i=i: F.grass_tuft(mb, random.Random(i), 0.95, 22, "Grass", 0.18)
                         for i in range(4)], rice_m, "Rice")
    rp = []
    count = 12000 if pv else 60000
    cutw = lambda x, y: True
    for _ in range(count):
        x = rng.uniform(-60, 120)
        y = rng.uniform(-10, 70)
        z = near.z(x, y)
        nz = near.nz_at(x, y, 0.3)
        if nz < 0.97:
            continue
        tid = math.floor((z + STEP * 0.07) / STEP)
        rr = (math.sin(tid * 12.9898) * 43758.5453) % 1.0
        if rr > 0.62:
            continue                      # stubble / water terraces stay bare
        rp.append((x, y, z - 0.05, rng.uniform(0, math.tau), rng.uniform(0.8, 1.15), rng.randrange(4)))
    F.instance("RicePlants", rp, rcol)
    # ---- farmers and sheaves -----------------------------------------------------------------
    crowd = MeshBuilder()
    spots = [(8.0, 14.0, "farm_bend", "sickle", 0.4), (14.5, 18.0, "farm_bend", "sickle", -0.3),
             (-2.0, 22.0, "carry", None, 1.9), (24.0, 30.0, "farm_bend", "sickle", 0.2),
             (32.0, 26.0, "stand", None, 2.4), (-14.0, 34.0, "farm_bend", "sickle", 0.9),
             (44.0, 48.0, "farm_bend", None, -0.5), (58.0, 40.0, "walk", None, 1.2),
             (5.0, 60.0, "farm_bend", "sickle", 0.1), (70.0, 64.0, "carry", None, -1.0)]
    for i, (x, y, pose, w, rz) in enumerate(spots):
        f = MeshBuilder()
        P.figure(f, random.Random(500 + i), pose, "farmer", cloth=rng.choice([0, 1, 3, 4, 6, 11]),
                 cloth2=rng.choice([2, 5, 9]), hat="straw", weapon=w)
        crowd.extend(f, Matrix.Translation((x, y, near.z(x, y) - 0.02)) @ Matrix.Rotation(rz, 4, "Z"))
    for _ in range(26):
        x = rng.uniform(-30, 110)
        y = rng.uniform(10, 75)
        z = near.z(x, y)
        tid = math.floor((z + STEP * 0.07) / STEP)
        rr = (math.sin(tid * 12.9898) * 43758.5453) % 1.0
        if near.nz_at(x, y, 0.3) > 0.97:
            sheaf(crowd, rng, (x, y, z - 0.02))
    crowd.build("Farmers", mats)
    # hamlet cooking smoke
    for i in range(3):
        sm = T.mist_material("Smoke%d" % i, "#D8C8C0", strength=0.9, density=0.5, seed=float(i * 5),
                             softness=0.5, stretch=0.4, edge=0.3)
        T.card("Smoke%d" % i, (-200 + i * 50, 470 + i * 12, 60 + i * 6), (16, 60), sm, rot_z=0.1)
    cam = L.camera((-6.0, -22.0, 9.5), (60.0, 300.0, -8.0), focal_mm=28.0, dof=(40.0, 11.0))
    return dict(camera=cam, beams=tuple(S.dir_from(*SUN) * 20000.0),
                beams_cfg=dict(ray_length=0.25, strength=0.25, threshold=1.3),
                glow=dict(threshold=1.0, mix=-0.82, size=8),
                grade=dict(saturation=1.06, contrast=1.06, shadows=(0.012, 0.0, 0.01),
                           highlights=(0.03, 0.012, -0.02), clarity=0.12, vignette=0.24,
                           canvas=0.02, sharpen=0.3))
