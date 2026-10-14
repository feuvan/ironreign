"""Event: Flood - the river bursts its banks over the fields in a storm.

From a knoll where villagers have fled, the viewer looks across the drowned fields to the levee:
the swollen river pours through a breach in a white torrent that fans out over the paddies,
sweeping round half-submerged thatched houses and willows; men with sandbags on the levee ends;
low storm clouds with a pale break on the horizon, slanting rain, lightning over the far bank.
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

SPEC = dict(name="Flood", art="Art/Events/Flood.png", master="Events/Flood@2x.png",
            size=(1280, 720), ss=1, spp=28, preview_spp=12, seed=101)

PLAIN_W = 1.4          # flood level over the drowned fields
RIVER_W = 4.6          # the swollen river behind the levee (brimming)
XB = -25.0             # breach centre (x)
BOLT = (-150.0, 1080.0)
CAM = (12.0, 38.0, 13.0)


def lev_y(X):
    """Levee crest line y(x): runs diagonally (far on the left, near on the right)."""
    return 104.0 - 0.3 * X + 4.0 * np.sin(X / 50.0)


_TN = np.array([1.0, -0.3]) / math.hypot(1.0, 0.3)      # along the levee
_NN = np.array([0.3, 1.0]) / math.hypot(1.0, 0.3)       # across, towards the river


def local(X, Y):
    """(u along the levee from the breach, s across: + river side, - plain side)."""
    by = float(lev_y(np.array([XB]))[0])
    dx, dy = X - XB, Y - by
    u = dx * _TN[0] + dy * _TN[1]
    s = (Y - lev_y(X)) * 0.958
    return u, s


def breach_mask(X, Y):
    u, s = local(X, Y)
    rag = 5.0 * (T.fbm2(X, Y, 7.0, 3, seed=9) - 0.5)
    return T.smoothstep(24.0, 13.0, np.abs(u) + rag)


def land_h(X, Y):
    u, s = local(X, Y)
    d = np.abs(s)
    lev = 5.3 * T.smoothstep(13.0, 3.5, d) + 0.4 * T.fbm2(X, Y, 6.0, 3, seed=3)
    lev = lev * (1.0 - 0.97 * breach_mask(X, Y))
    plain = 0.5 * T.fbm2(X, Y, 40.0, 4, seed=2) - 0.25
    # paddy bunds just breaking the surface (washed out by the torrent)
    a = 0.35
    xr, yr = X * math.cos(a) + Y * math.sin(a), -X * math.sin(a) + Y * math.cos(a)
    bx = np.abs(np.mod(xr, 26.0) - 13.0)
    by = np.abs(np.mod(yr + 5.0, 19.0) - 9.5)
    bund = T.smoothstep(12.0, 12.8, np.maximum(bx, by * 13.0 / 9.5))
    plain = np.maximum(plain, (PLAIN_W + 0.22) * bund * (1.0 - torrent(X, Y)) - 0.1)
    # knoll in the right foreground (the villagers' refuge, the camera stands on its back)
    kd = np.hypot((X - 120.0) / 30.0, (Y - 40.0) / 24.0)
    knoll = 6.0 * np.exp(-kd * kd * 1.6) + 0.5 * T.fbm2(X, Y, 5.0, 3, seed=5) * T.smoothstep(1.2, 0.4, kd)
    h = np.maximum(plain, lev - 0.2)
    h = np.maximum(h, knoll - 0.3)
    # river bed behind the levee, the far bank and its hills
    fb = 470.0 + 40.0 * np.sin(X / 260.0) + 25.0 * T.fbm2(X, Y, 120.0, 3, seed=6)
    bed = T.smoothstep(8.0, 30.0, s)
    h = h * (1.0 - bed) + bed * (-3.0 + 9.0 * T.smoothstep(fb, fb + 70.0, Y))
    h = h + T.smoothstep(fb + 200.0, fb + 1400.0, Y) * 220.0 * T.ridged2(X, Y, 650.0, 5, seed=4)
    return h


def torrent(X, Y):
    """0..1 white-water mask: the chute through the breach and the fan spreading over the fields."""
    u, s = local(X, Y)
    v = np.maximum(-s, 0.0)
    half = 15.0 + 0.55 * v
    fan = T.smoothstep(half, 0.25 * half, np.abs(u)) * np.exp(-v / 75.0) * T.smoothstep(3.0, -3.0, s)
    up = 0.55 * T.smoothstep(60.0, 8.0, np.hypot(u * 0.8, s)) * T.smoothstep(-2.0, 4.0, s)
    chute = T.smoothstep(22.0, 12.0, np.abs(u)) * T.smoothstep(9.0, 3.0, np.abs(s))
    return np.clip(np.maximum(np.maximum(fan, up), chute), 0.0, 1.0)


def water_h(X, Y):
    u, s = local(X, Y)
    tor = torrent(X, Y)
    w = PLAIN_W + (RIVER_W - PLAIN_W) * T.smoothstep(-6.0, 6.0, s)
    v = np.maximum(-s, 0.0)
    # the jet carries a mound of water out over the fields, with standing waves
    jet = 0.9 * np.exp(-(u / (8.0 + 0.35 * v)) ** 2) * np.exp(-v / 45.0) * T.smoothstep(4.0, -6.0, s)
    waves = (T.ridged2(X, Y, 4.5, 3, seed=31) - 0.45) * 0.9 + (T.fbm2(X, Y, 1.6, 2, seed=32) - 0.5) * 0.35
    chop = (T.fbm2(X, Y, 2.2, 3, seed=33) - 0.5) * 0.12
    return w + jet + tor * waves * (0.35 + 0.65 * np.exp(-v / 30.0)) + chop


def flood_water():
    """Muddy flood water: ochre-brown, choppy, streaked along the flow, white water where the
    ``torrent`` attribute is high (the chute and the fan); rough enough that the storm sky only
    gives a soft sheen."""
    from ironart.scenes_sky import G, lin4
    from ironart.scenes_terrain import _fin, noise
    mat, nb, created = M.new("FloodWater")
    if not created:
        return mat
    b = G(nb.tree)
    P_ = nb.node("ShaderNodeNewGeometry").outputs["Position"]
    tor = nb.node("ShaderNodeAttribute", attribute_name="torrent").outputs["Fac"]
    # streaks along x (the river) / along y (the fan) blended by the torrent mask
    wa = noise(nb, b.vmath("MULTIPLY", P_, b.vec((0.08, 0.5, 0.2))).outputs[0], 1.0, 6, 0.62, 0.8)
    wb = noise(nb, b.vmath("MULTIPLY", P_, b.vec((0.45, 0.1, 0.2))).outputs[0], 1.0, 6, 0.62, 0.8)
    w1 = b.math("ADD", wa, b.math("MULTIPLY", b.math("SUBTRACT", wb, wa), tor))
    w2 = noise(nb, b.vmath("MULTIPLY", P_, b.vec((1.1, 1.1, 0.6))).outputs[0], 1.0, 4, 0.6, 0.6)
    h = b.math("ADD", w1, b.math("MULTIPLY", w2, 0.5))
    col = b.mix(lin4("#4A3620"), lin4("#7E6236"), b.smooth(noise(nb, P_, 0.015, 3, 0.5), 0.3, 0.75))
    col = b.mix(col, lin4("#8C7048"), b.math("MULTIPLY", tor, 0.6))
    scum = b.math("MULTIPLY", b.smooth(w2, 0.7, 0.82), b.smooth(w1, 0.58, 0.72))
    x = b.math("ADD", b.math("MULTIPLY", w1, 0.6), b.math("MULTIPLY", w2, 0.4))
    e0 = b.math("SUBTRACT", 0.64, b.math("MULTIPLY", tor, 0.32))
    white = b.math("MULTIPLY", b.math("POWER", tor, 0.7),
                   b.math("DIVIDE", b.math("SUBTRACT", x, e0), 0.12, clamp=True))
    foam = b.math("MAXIMUM", b.math("MULTIPLY", scum, 0.7), white)
    col = b.mix(col, lin4("#E8E2D6"), foam)
    rough = b.maprange(foam, 0, 1, 0.22, 0.9)
    p = b.principled(Base_Color=col, Roughness=rough, Specular_IOR_Level=0.32,
                     Normal=b.bump(h, 0.75, 0.35))
    return _fin(mat, nb, p.outputs[0])


def rain_material(name="Rain"):
    from ironart.scenes_sky import G, lin4
    mat, nb, created = M.new(name)
    if not created:
        return mat
    b = G(nb.tree)
    tc = nb.node("ShaderNodeTexCoord")
    u, v, _ = b.sep(tc.outputs["UV"])
    # streaks: high-frequency noise stretched along v (the card is tilted with the wind)
    n = nb.node("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 1.0
    n.inputs["Detail"].default_value = 2.0
    b.link(b.comb(b.math("MULTIPLY", u, 2400.0), b.math("MULTIPLY", v, 45.0), 0.0), n.inputs["Vector"])
    a = b.math("MULTIPLY", b.smooth(n.outputs["Fac"], 0.64, 0.74), 0.2)
    edge = b.math("MULTIPLY", b.smooth(u, 0.0, 0.1), b.smooth(u, 1.0, 0.9))
    a = b.math("MULTIPLY", a, edge)
    em = nb.node("ShaderNodeEmission")
    em.inputs["Color"].default_value = lin4("#9AA4B0")
    em.inputs["Strength"].default_value = 1.0
    tp = nb.node("ShaderNodeBsdfTransparent")
    mx = nb.node("ShaderNodeMixShader")
    b.link(a, mx.inputs[0])
    b.link(tp.outputs[0], mx.inputs[1])
    b.link(em.outputs[0], mx.inputs[2])
    nb.output(mx.outputs[0])
    mat["ir_fog"] = 1
    return mat


def build(r):
    import bpy
    pv = r["preview"]
    rng = random.Random(101)
    cam_az = 112.0
    S.build(dict(
        stops=[(0.0, "#8E8C80"), (0.03, "#6C6E6A"), (0.1, "#4C5254"), (0.35, "#30363A"),
               (1.0, "#1A1E22")],
        strength=1.15,
        glows=[dict(dir=(88.0, 1.0), color="#E2D2A6", lobes=[(8, 0.3), (60, 0.45)],
                    horizon=(0.7, 0.022, 3.0)),
               dict(dir=(math.degrees(math.atan2(BOLT[1] - CAM[1], BOLT[0] - CAM[0])), 16.0),
                    color="#C8D4F0", lobes=[(40, 0.7), (400, 2.2)])],
        clouds=[dict(height=900, scale=1500, coverage=0.78, softness=0.3, lit="#6A7076",
                     shadow="#202428", rim_color="#D8D0B8", rim=0.6, rim_power=6.0, opacity=0.96,
                     stretch=(1, 0.55), fade=0.05, shade=6.0, core_dark=0.55, seed=21.0, haze=0.35),
                dict(height=420, scale=700, coverage=0.4, softness=0.45, lit="#5A5E62",
                     shadow="#1C1E22", rim=0.0, opacity=0.75, stretch=(1, 0.4), fade=0.05,
                     seed=33.0, haze=0.5)],
        light=dict(strength=1.5, tint="#A8B4C0"),
        fog=dict(haze=0.0013, haze_falloff=0.004, haze_max=0.92, haze_zmax=0.06, haze_tint="#A8ACAA",
                 mist=0.006, mist_falloff=0.25, mist_h0=PLAIN_W, mist_max=0.45, mist_color="#6E7270"),
    ))
    S.sun(165.0, 24.0, energy=1.7, color="#D0CCC0", angle_deg=14.0, name="StormLight")
    S.sun(250.0, 50.0, energy=0.25, color="#9AA8B8", angle_deg=30.0, name="SkyFill", shadow=False)
    # ---- land ------------------------------------------------------------------------------------
    gm = T.terrain_material("FloodMud", grass=("#34401E", "#4E5228"), dry="#6A5A38", dirt="#5A4630",
                            rock=("#4E3E2C", "#6E5A40"), slope=(0.72, 0.86), grass_scale=0.05,
                            roughness=0.8, dry_amt=0.35)
    near = T.field_from(land_h, -320, 200, -40, 240, 0.8 if pv else 0.5)
    near.build("LandNear", gm)
    far = T.field_from(land_h, -4000, 4000, 225, 5000, 16.0 if pv else 10.0)
    far.build("LandFar", gm)
    # ---- water: displaced near patch (torrent) + flat river / plain beyond ----------------------
    X, Y = T.grid_xy(-320, 200, -40, 240, 0.7 if pv else 0.4)
    W = water_h(X, Y)
    W = W * T.smoothstep(240.0, 225.0, Y) + RIVER_W * T.smoothstep(225.0, 240.0, Y)
    wf = T.Field(W.astype(np.float32), -320, 200, -40, 240)
    wf.build("Flood", flood_water(), attrs={"torrent": torrent(X, Y) * T.smoothstep(240.0, 220.0, Y)})
    T.plane("River", -4000, 4000, 240, 2000, RIVER_W, flood_water())
    # ---- drowned hamlet, willows, debris -----------------------------------------------------
    am = A.materials(thatch="#5E5038", plaster="#9A8E78")
    pm = P.materials(cloth=["#3A3E44", "#5A4E40", "#6E6250", "#2A2C30", "#5A3A2A", "#A89C84",
                            "#3A3430", "#40484A", "#5A4A3E", "#7A6A4A", "#6A3A2E", "#2E3A40"])
    mats = dict(am)
    mats.update(pm)
    by = float(lev_y(np.array([XB]))[0])

    def at(u, v):
        """World (x, y) at u along the levee from the breach, v downstream onto the plain."""
        return XB + u * _TN[0] - v * _NN[0], by + u * _TN[1] - v * _NN[1]

    vil = MeshBuilder()
    houses = [(-34, 30, 0.3), (22, 44, -0.2), (-48, 70, 0.5), (34, 92, 0.1), (-12, 112, -0.4),
              (-90, 40, 0.2), (70, 40, 0.0), (-70, 110, -0.3), (-130, 60, 0.3), (-160, 120, 0.1),
              (90, 120, 0.2)]
    hpos = []
    for i, (u, v, rz) in enumerate(houses):
        x, y = at(u, v)
        z = PLAIN_W - 2.0 - rng.uniform(0, 1.1)
        hb = A.scaled(A.thatched_house(random.Random(i), 1.0), 7.5, (x, y, z), rot_z=rz + 0.3)
        vil.extend(hb)
        hpos.append((x, y, z))
    # floating debris: timbers, straw bundles, a broken cart wheel
    for _ in range(140):
        u, v = rng.uniform(-60, 80), rng.uniform(5, 150)
        x, y = at(u, v)
        if rng.random() < 0.7:
            vil.box((x, y, PLAIN_W + 0.02), (rng.uniform(0.6, 3.0), rng.uniform(0.15, 0.35), 0.18),
                    "Timber", rot_z=rng.uniform(0, math.pi))
        else:
            vil.sphere((x, y, PLAIN_W + 0.05), 0.5, "Thatch", 8, 4, scale=(1.4, 0.8, 0.35))
    # sandbags along the levee crest near the breach
    for side in (-1, 1):
        for k in range(26):
            u = side * (22.0 + k * 0.9 + rng.uniform(-0.2, 0.2))
            x, y = at(u, -0.5 + rng.uniform(-0.6, 0.6))
            vil.sphere((x, y, float(land_h(np.array([x]), np.array([y]))[0]) + 0.15), 0.42, "Straw", 8, 4,
                       scale=(1.0, 0.6, 0.38))
    vil.build("Hamlet", mats)
    # ---- people: refugees on the knoll (foreground), men fighting the breach on the levee ---------
    ppl = MeshBuilder()
    # a family stranded on the ridge of a drowned house in the foreground
    rx, ry, rrz = 13.0, 64.0, 0.45
    rbase = PLAIN_W - 3.0
    hb = A.scaled(A.thatched_house(random.Random(77), 1.0), 7.5, (rx, ry, rbase), rot_z=rrz)
    rh = MeshBuilder()
    rh.extend(hb)
    rh.build("RoofHouse", mats)
    ax_ = (math.cos(rrz), math.sin(rrz))
    for k, (t, pose, cl, hat, yaw) in enumerate([(-2.6, "sit", 1, "straw", 0.3), (-1.2, "cheer", 2, None, -0.3),
                                                 (0.4, "kneel", 4, "hood", 0.2), (1.9, "sit", 6, "straw", -0.1),
                                                 (3.0, "point", 8, "straw", 1.9)]):
        f = MeshBuilder()
        P.figure(f, random.Random(60 + k), pose, "peasant", cloth=cl, cloth2=9, hat=hat, cape=True,
                 cape_wind=(0.9, 0.3), height=1.62 if k != 2 else 1.3)
        z0 = rbase + 6.45 - (0.35 if pose == "sit" else 0.12)
        ppl.extend(f, Matrix.Translation((rx + ax_[0] * t, ry + ax_[1] * t, z0)) @
                   Matrix.Rotation(rrz + yaw, 4, "Z"))
    for side in (-1, 1):
        for k in range(4):
            u = side * (24.0 + k * 3.2 + rng.uniform(-0.8, 0.8))
            x, y = at(u, rng.uniform(-1.5, 1.5))
            f = MeshBuilder()
            P.figure(f, random.Random(80 + k + (side > 0) * 10), rng.choice(["carry", "walk", "point", "carry"]),
                     "peasant", cloth=rng.randrange(9), cloth2=5, hat="straw")
            ppl.extend(f, Matrix.Translation((x, y, float(land_h(np.array([x]), np.array([y]))[0]))) @
                       Matrix.Rotation(math.atan2(_TN[1], _TN[0]) + (math.pi / 2 if side > 0 else -math.pi / 2), 4, "Z"))
    ppl.build("Villagers", mats)
    # ---- trees: willows half drowned on the plain, a dark stand on the knoll, the far bank -----
    fm = {"Leaves": F.foliage_material("FLeaves", ("#2A3420", "#46502E"), translucency=0.1),
          "LeavesCore": F.foliage_material("FLeavesCore", ("#1A2216", "#2A3220"), core=True, translucency=0.0),
          "Bark": F.bark_material("FBark", ("#221E1A", "#3A322A"))}
    tcol = F.prototypes([lambda mb: F.broadleaf(mb, random.Random(1), 11, leaf=0.3, leaves=55),
                         lambda mb: F.broadleaf(mb, random.Random(2), 9, leaf=0.3, leaves=55),
                         lambda mb: F.broadleaf(mb, random.Random(3), 13, leaf=0.3, leaves=55, crown=0.4)],
                        fm, "FTrees")
    tp = []
    for (x, y, z) in hpos:
        for _ in range(rng.randint(1, 3)):
            a = rng.uniform(0, math.tau)
            tp.append((x + math.cos(a) * rng.uniform(7, 13), y + math.sin(a) * rng.uniform(7, 13),
                       PLAIN_W - 2.5 - rng.uniform(0, 1.5), rng.uniform(0, math.tau), rng.uniform(0.8, 1.15),
                       rng.randrange(3)))
    for _ in range(40):
        u, v = rng.uniform(-260, 160), rng.uniform(150, 260)
        x, y = at(u, v)
        if y < -30 or abs(local(np.array([x]), np.array([y]))[0][0]) < 50:
            continue
        tp.append((x, y, PLAIN_W - 2.5 - rng.uniform(0, 1.5), rng.uniform(0, math.tau), rng.uniform(0.8, 1.2),
                   rng.randrange(3)))
    for (x, y) in ((118.0, 38.0), (126.0, 44.0), (112.0, 46.0)):
        tp.append((x, y, float(land_h(np.array([x]), np.array([y]))[0]) - 0.3, rng.uniform(0, math.tau),
                   rng.uniform(1.0, 1.25), rng.randrange(3)))
    for _ in range(900 if pv else 1600):
        x = rng.uniform(-1800, 1400)
        fb = 470.0 + 40.0 * math.sin(x / 260.0)
        y = rng.uniform(fb + 60.0, fb + 420.0)
        tp.append((x, y, float(land_h(np.array([x]), np.array([y]))[0]) - 0.4, rng.uniform(0, math.tau),
                   rng.uniform(0.9, 1.5), rng.randrange(3)))
    F.instance("Trees", tp, tcol)
    # ---- rain + lightning ------------------------------------------------------------------------
    rm = rain_material()
    vd = (math.cos(math.radians(cam_az)), math.sin(math.radians(cam_az)))
    for i in range(12):
        d = 12.0 + i * i * 4.0 + i * 10.0
        c = (CAM[0] + vd[0] * d, CAM[1] + vd[1] * d)
        w = 2.0 * d * 0.75 + 30.0
        T.card("Rain%d" % i, (c[0] + rng.uniform(-5, 5), c[1], PLAIN_W + 40.0), (w, 80.0), rm,
               rot_z=math.radians(cam_az - 90.0) + rng.uniform(-0.1, 0.1),
               tilt=math.radians(rng.uniform(-14, -8)))
    bolt = MeshBuilder()
    p = Vector((BOLT[0], BOLT[1], 560.0))
    pts = [p.copy()]
    for k in range(15):
        p = p + Vector((rng.uniform(-28, 28), rng.uniform(-10, 10), -38.0))
        pts.append(p.copy())
    bolt.tube([tuple(q) for q in pts], 1.4, "Bolt", 5)
    for fk in (5, 9):
        fork = pts[fk]
        q = fork.copy()
        for k in range(5 if fk == 5 else 3):
            q = q + Vector((rng.uniform(8, 32), rng.uniform(-8, 8), -34.0))
            bolt.cylinder(tuple(fork), tuple(q), 0.8, 0.5, "Bolt", 5)
            fork = q
    bo = bolt.build("Bolt", {"Bolt": P.flame_material("FBolt", "#E0E8FF", strength=40.0)})
    bo.visible_glossy = False
    cz = CAM[2]
    tgt = (CAM[0] + vd[0] * 100.0, CAM[1] + vd[1] * 100.0, cz - 100.0 * math.tan(math.radians(9.0)))
    cam = L.camera((CAM[0], CAM[1], cz), tgt, focal_mm=28.0)
    import os
    if os.environ.get("FLOOD_DBG"):
        cam = L.camera((XB + 10.0, by - 70.0, 40.0), (XB, by, 0.0), focal_mm=28.0)
    return dict(camera=cam, beams=tuple(S.dir_from(88.0, 1.0) * 5000.0),
                beams_cfg=dict(ray_length=0.12, strength=0.12, threshold=0.8),
                glow=dict(threshold=0.95, mix=-0.75, size=9),
                grade=dict(saturation=0.95, contrast=1.12, shadows=(-0.01, 0.0, 0.015),
                           highlights=(0.015, 0.008, -0.005), clarity=0.16, vignette=0.34,
                           canvas=0.012, sharpen=0.3))
