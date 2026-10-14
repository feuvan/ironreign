"""Event: Harvest - golden terraced rice fields at sunset.

From the terraces on one side of a valley the viewer looks across at a great terraced hillside:
hundreds of curving terraces follow the contours over spurs and gullies; most hold ripe golden
rice, some are flooded and mirror the sunset sky, some are cut to stubble.  The low sun rakes in
from the left, gilding the rice and throwing the terrace walls into lines of shadow; mist lies
on the flooded paddies of the valley floor; a thatched hamlet with bamboo sits on the far ridge
under the warm sky.  In the foreground farmers in straw hats cut and stook the rice.
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
            size=(1280, 720), ss=1, spp=20, preview_spp=12, seed=31)

SUN = (208.0, 8.0)
STEP = 1.6          # terrace rise (m)
VALLEY_Z = 2.0
CAM = (10.0, -70.0)


def base_height(X, Y):
    """Valley along x at y ~ 100: the far slope rises away from the viewer over alternating
    spurs and gullies (so the terrace contours swing in long curves), the near slope rises
    gently towards the viewer; a ridge with a hamlet on top, mountains beyond."""
    w = T.fbm2(X, Y, 90.0, 3, seed=8)
    v = T.fbm2(X, Y, 260.0, 4, seed=4)
    far = np.maximum(Y - 120.0, 0.0) * 0.26 + 0.0004 * X * X * T.smoothstep(120.0, 300.0, Y)
    spurs = (13.0 * np.sin(X / 21.0 + 1.6 * np.sin(Y / 70.0)) + 7.0 * np.sin(X / 47.0 + 2.0)) * T.smoothstep(140.0, 300.0, Y)
    near = np.maximum(80.0 - Y, 0.0) * 0.25 + 4.0 * np.sin(X / 45.0) * T.smoothstep(60.0, -20.0, Y)
    h = VALLEY_Z + far + spurs + near + 6.0 * (w - 0.5) + 6.0 * (v - 0.5) * T.smoothstep(100.0, 260.0, Y)
    h = np.minimum(h, 128.0 + 6.0 * w)                     # the ridge top (hamlet)
    h += T.smoothstep(700.0, 1300.0, Y) * 280.0 * T.ridged2(X, Y, 520.0, 5, seed=6)
    return h


def terraced(X, Y):
    h = base_height(X, Y)
    t = h / STEP
    fr = t - np.floor(t)
    q = (np.floor(t) + T.smoothstep(0.84, 1.0, fr)) * STEP
    w = T.smoothstep(126.0, 118.0, h) * T.smoothstep(900.0, 700.0, np.abs(X)) * T.smoothstep(VALLEY_Z + 0.6, VALLEY_Z + 2.0, h)
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
    rice = b.mix(lin4("#B88E30"), lin4("#E6C25C"), b.smooth(n1, 0.3, 0.7))
    rice = b.mix(rice, b.cmul(rice, 0.85), b.smooth(n2, 0.55, 0.8))
    rice = b.mix(rice, lin4("#8E8A3A"), b.math("MULTIPLY", b.smooth(rnd, 0.75, 0.82), 0.6))
    stub = b.mix(lin4("#7A6038"), lin4("#9A7A48"), b.smooth(n2, 0.3, 0.7))
    is_stub = b.math("MULTIPLY", b.smooth(rnd, 0.52, 0.54), b.smooth(rnd, 0.66, 0.64))
    col = b.mix(rice, stub, is_stub)
    is_water = b.smooth(rnd, 0.66, 0.67)
    bund = b.smooth(nz, 0.93, 0.8)
    earth = b.mix(lin4("#4E5A28"), lin4("#6E7A34"), b.smooth(n1, 0.3, 0.7))
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
        stops=[(0.0, "#FFC08A"), (0.03, "#F8B486"), (0.1, "#E4AE98"), (0.22, "#B8A8B8"),
               (0.45, "#8090B4"), (1.0, "#4A5A88")],
        strength=1.1,
        glows=[dict(dir=SUN, color="#FFA850", lobes=[(3, 0.9), (20, 2.2), (300, 12.0)],
                    horizon=(1.4, 0.06, 1.5))],
        discs=[dict(dir=SUN, radius_deg=0.7, color="#FFE6B8", strength=60.0)],
        clouds=[dict(height=2600, scale=3600, coverage=0.45, softness=0.24, lit="#FFC88E",
                     shadow="#8A6E78", rim_color="#FFDCA0", rim=2.5, rim_power=4.0, opacity=0.9,
                     stretch=(1.0, 0.5), fade=0.14, shade=8.0, seed=11.0, haze=0.55)],
        light=dict(strength=0.55, tint="#C8CCE8"),
        fog=dict(haze=1.6e-4, haze_falloff=0.002, haze_max=0.9, haze_zmax=0.08,
                 mist=0.006, mist_falloff=0.12, mist_h0=VALLEY_Z, mist_max=0.55,
                 mist_color="#F0D4B4", mist_strength=1.0),
    ))
    S.sun(SUN[0], SUN[1] + 1.5, energy=5.5, color="#FFB470", angle_deg=1.0)
    # ---- terrain ----------------------------------------------------------------------------
    pm = paddy_material()
    near = T.field_from(terraced, -160, 180, -80, 92, 0.5 if pv else 0.3)
    near.build("PaddyNear", pm)
    far = T.field_from(lambda X, Y: terraced(X, Y) - 0.06 * (Y < 92.0), -900, 900, 88, 720, 1.2 if pv else 0.8)
    far.build("PaddyFar", pm)
    gm = T.terrain_material("HarvestHills", grass=("#4E5E30", "#76703C"), dry="#9A8248",
                            rock=("#6A6058", "#8A8070"), slope=(0.7, 0.85), grass_scale=0.01)
    T.field_from(lambda X, Y: terraced(X, Y) - 0.1 * (Y < 722.0), -2600, 2600, 716, 3600, 6.0).build("Hills", gm)
    for sx in (-1, 1):
        T.field_from(lambda X, Y: terraced(X, Y) - 0.1, (-2600 if sx < 0 else 880), (-880 if sx < 0 else 2600),
                     -300, 722, 4.0).build("Side%d" % (sx > 0), gm)
    T.field_from(lambda X, Y: terraced(X, Y) - 0.08, -900, 900, -300, -78, 2.0).build("Behind", gm)
    # flooded paddies on the valley floor mirror the sky
    wm = T.water_material("HarvestWater", deep="#3A3A40", shallow="#5A5A50", roughness=0.03, ripple=0.08)
    T.plane("ValleyWater", -2600, 2600, 40, 200, VALLEY_Z + 0.25, wm)
    rm = T.terrain_material("HarvestRange", grass=("#5A6048", "#6E6A50"), rock=("#5E5A58", "#7E7A74"),
                            slope=(0.72, 0.86), grass_scale=0.002)

    def rfn(X, Y):
        return T.ridged2(X, Y, 900.0, 6, sharp=1.8, seed=9, warp=500.0) ** 1.3 * 700.0 + 100.0
    T.field_from(rfn, -7000, 8000, 3000, 9000, 30.0).build("Range", rm)
    # ---- hamlet on the far ridge + trees -------------------------------------------------------
    am = A.materials(thatch="#8C744A")
    pmats = P.materials(cloth=["#3E4A5E", "#5A4A36", "#7A6A50", "#2E3A30", "#8A5A3A", "#B8AA8A",
                               "#4A3A2E", "#6A6E5A", "#5A3022", "#C8BCA0", "#7A3A26", "#3A4A4E"])
    mats = dict(am)
    mats.update(pmats)
    tz = lambda x, y: float(terraced(np.array([float(x)]), np.array([float(y)]))[0])
    vil = MeshBuilder()
    for i in range(18):
        x = rng.uniform(-260, 120)
        y = rng.uniform(610, 700)
        hb = A.scaled(A.thatched_house(random.Random(i), 1.0, foundation=0.6), 6.5, (x, y, tz(x, y) - 0.7),
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
    tcol = F.prototypes([lambda mb: F.broadleaf(mb, random.Random(1), 12, leaf=0.3, leaves=55),
                         lambda mb: F.broadleaf(mb, random.Random(2), 9, leaf=0.3, leaves=55),
                         lambda mb: F.bamboo(mb, random.Random(3), 10, stems=14),
                         lambda mb: F.chinese_pine(mb, random.Random(4), 12)], fm, "HTrees")
    tp = []
    for _ in range(4000 if pv else 10000):
        x = rng.uniform(-2600, 2600)
        y = rng.uniform(-300, 3200)
        z = tz(x, y)
        if abs(x) < 880 and -80 < y < 600 and z < 118:
            # on the terraced slopes only a few trees in the gullies
            g_ = math.sin(x / 21.0 + 1.6 * math.sin(y / 70.0))
            if not (g_ < -0.85 and y > 200 and rng.random() < 0.5):
                continue
        if z < 6:
            continue
        tp.append((x, y, z - 0.5, rng.uniform(0, math.tau), rng.uniform(0.8, 1.3), rng.choice([0, 0, 1, 3])))
    for _ in range(60):
        x = rng.uniform(-300, 160)
        y = rng.uniform(590, 720)
        tp.append((x, y, tz(x, y) - 0.3, rng.uniform(0, math.tau), rng.uniform(0.9, 1.2), 2))
    F.instance("Trees", tp, tcol)
    # ---- rice plants in the near terraces (texture close to the camera) --------------------
    rice_m = {"Grass": F.foliage_material("RiceStalk", ("#A8822E", "#E0BC5C"), translucency=0.4, vary=0.4)}
    rcol = F.prototypes([lambda mb, i=i: F.grass_tuft(mb, random.Random(i), 0.95, 22, "Grass", 0.18)
                         for i in range(4)], rice_m, "Rice")
    rp = []
    for _ in range(14000 if pv else 70000):
        x = rng.uniform(-90, 110)
        y = rng.uniform(-62, 40)
        z = near.z(x, y)
        if near.nz_at(x, y, 0.3) < 0.97:
            continue
        tid = math.floor((z + STEP * 0.07) / STEP)
        rr = (math.sin(tid * 12.9898) * 43758.5453) % 1.0
        if rr > 0.52:
            continue                      # stubble / water terraces stay bare
        rp.append((x, y, z - 0.05, rng.uniform(0, math.tau), rng.uniform(0.8, 1.15), rng.randrange(4)))
    F.instance("RicePlants", rp, rcol)
    # ---- farmers and sheaves -----------------------------------------------------------------
    crowd = MeshBuilder()
    spots = [(-4.0, -44.0, "farm_bend", "sickle", 0.4), (1.5, -41.0, "farm_bend", "sickle", -0.3),
             (14.0, -38.0, "carry", None, 1.9), (-16.0, -30.0, "farm_bend", "sickle", 0.2),
             (24.0, -32.0, "stand", None, 2.4), (6.0, -24.0, "farm_bend", "sickle", 0.9),
             (32.0, -18.0, "farm_bend", None, -0.5), (-24.0, -14.0, "walk", None, 1.2),
             (12.0, -6.0, "farm_bend", "sickle", 0.1), (-8.0, 6.0, "carry", None, -1.0),
             (40.0, 2.0, "farm_bend", "sickle", 0.6), (-34.0, -38.0, "farm_bend", "sickle", -0.2)]
    for i, (x, y, pose, w, rz) in enumerate(spots):
        if near.nz_at(x, y, 0.4) < 0.97:
            y += 1.2
        f = MeshBuilder()
        P.figure(f, random.Random(500 + i), pose, "farmer", cloth=rng.choice([0, 1, 3, 4, 6, 11]),
                 cloth2=rng.choice([2, 5, 9]), hat="straw", weapon=w)
        crowd.extend(f, Matrix.Translation((x, y, near.z(x, y) - 0.02)) @ Matrix.Rotation(rz, 4, "Z"))
    for _ in range(40):
        x = rng.uniform(-60, 70)
        y = rng.uniform(-56, 30)
        z = near.z(x, y)
        tid = math.floor((z + STEP * 0.07) / STEP)
        rr = (math.sin(tid * 12.9898) * 43758.5453) % 1.0
        if near.nz_at(x, y, 0.3) > 0.97 and 0.52 < rr < 0.66:
            sheaf(crowd, rng, (x, y, z - 0.02))
    crowd.build("Farmers", mats)
    # mist over the flooded valley floor, hamlet cooking smoke
    for i in range(5):
        mm = T.mist_material("VMist%d" % i, "#F4D8BC", strength=1.1, density=0.5, seed=float(i * 3),
                             softness=0.5, stretch=4.0)
        T.card("VMist%d" % i, (rng.uniform(-300, 300), 110.0 + i * 22.0, VALLEY_Z + rng.uniform(4, 9)),
               (rng.uniform(300, 600), rng.uniform(10, 18)), mm)
    for i in range(3):
        sm = T.mist_material("Smoke%d" % i, "#D8C8C0", strength=0.9, density=0.5, seed=float(i * 5),
                             softness=0.5, stretch=0.4, edge=0.3)
        x, y = -200 + i * 90, 640 + i * 15
        T.card("Smoke%d" % i, (x, y, tz(x, y) + 24), (12, 46), sm, rot_z=0.1)
    cx_, cy_ = CAM
    cz_ = tz(cx_, cy_) + 2.6
    az, pitch = 92.0, -2.5
    cam = L.camera((cx_, cy_, cz_), (cx_ + 300 * math.cos(math.radians(az)), cy_ + 300 * math.sin(math.radians(az)),
                                     cz_ + 300 * math.tan(math.radians(pitch))), focal_mm=28.0, dof=(60.0, 11.0))
    return dict(camera=cam, beams=tuple(S.dir_from(*SUN) * 20000.0),
                beams_cfg=dict(ray_length=0.25, strength=0.25, threshold=1.3),
                glow=dict(threshold=1.0, mix=-0.82, size=8),
                grade=dict(saturation=1.08, contrast=1.1, shadows=(0.0, -0.002, 0.016),
                           highlights=(0.035, 0.012, -0.025), clarity=0.14, vignette=0.26,
                           canvas=0.012, sharpen=0.3))
