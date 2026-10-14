"""Event: Battle - two armies clash on an open plain.

Low camera inside the charging (left) army: spearmen and a standard bearer run past in the
foreground towards the clash line that recedes diagonally to the right; the enemy host with
cavalry pours in from the far side; dust rises along the line, glowing in the low sun ahead;
a volley of arrows arcs across the hazy sky; banners everywhere.
"""

import math
import random

from mathutils import Matrix, Vector

from ironart import scenes_flora as F
from ironart import scenes_look as L
from ironart import scenes_people as P
from ironart import scenes_sky as S
from ironart import scenes_terrain as T
from ironart.geometry import MeshBuilder

SPEC = dict(name="Battle", art="Art/Events/Battle.png", master="Events/Battle@2x.png",
            size=(1280, 720), ss=1, spp=128, preview_spp=20, seed=21)

SUN = (118.0, 15.0)


def face(dx, dy):
    """Rotation (rad) turning a -Y facing figure towards (dx, dy)."""
    return math.atan2(dx, -dy)


def line_y(x):
    """The clash line (receding to the right)."""
    return 70.0 + 0.42 * x


def build(r):
    import bpy
    pv = r["preview"]
    rng = random.Random(21)
    S.build(dict(
        stops=[(0.0, "#E8C49A"), (0.04, "#DDB08A"), (0.15, "#B8A898"), (0.4, "#8C98AC"),
               (1.0, "#5A6C88")],
        strength=1.3,
        glows=[dict(dir=SUN, color="#FFC07A", lobes=[(5, 1.2), (40, 3.0), (600, 18.0)],
                    horizon=(1.5, 0.06, 2.0))],
        discs=[dict(dir=SUN, radius_deg=0.6, color="#FFF0D8", strength=70.0)],
        clouds=[dict(height=2400, scale=3800, coverage=0.55, softness=0.22, lit="#F8D2A4",
                     shadow="#6E6464", rim=3.0, opacity=0.9, stretch=(1.0, 0.45), fade=0.06,
                     shade=8.0, seed=4.0, haze=0.55, core_dark=0.45)],
        light=dict(strength=0.6, tint="#D8DCE8"),
        fog=dict(haze=2.4e-4, haze_falloff=0.002, haze_max=0.9, haze_zmax=0.1,
                 mist=0.006, mist_falloff=0.09, mist_h0=0.0, mist_max=0.7,
                 mist_color="#D8B48A", mist_strength=1.1),
    ))
    S.sun(SUN[0], SUN[1], energy=5.5, color="#FFD0A0", angle_deg=1.0)
    # ---- ground -----------------------------------------------------------------------------
    gm = T.terrain_material("BattleGround", grass=("#6A6A3A", "#8A7E48"), dry="#A08A5A",
                            dirt="#7E6A4E", rock=("#6E665A", "#8E8676"), slope=(0.7, 0.85),
                            grass_scale=0.02, dry_amt=0.6)

    def hfn(X, Y):
        import numpy as np
        h = 2.5 * T.fbm2(X, Y, 120.0, 4, seed=2)
        hills = T.ridged2(X, Y, 700.0, 5, seed=3, warp=300.0)
        far = T.smoothstep(400.0, 1600.0, Y)
        return h + hills * 220.0 * far + T.smoothstep(900.0, 3000.0, Y) * 150.0
    g = T.field_from(hfn, -1500, 2500, -80, 3200, 4.0 if pv else 2.0)
    g.build("Plain", gm)
    rmat = T.terrain_material("BattleRange", grass=("#5E6A48", "#7A7656"), rock=("#6A6660", "#8A8478"),
                              slope=(0.72, 0.86), grass_scale=0.002)

    def rfn(X, Y):
        r_ = T.ridged2(X, Y, 1800.0, 7, sharp=1.8, seed=8, warp=900.0)
        return r_ ** 1.3 * 1500.0
    T.field_from(rfn, -9000, 12000, 4000, 14000, 60.0).build("Range", rmat)
    # ---- armies (instanced prototypes) ------------------------------------------------------
    mats = P.materials(cloth=["#5A1E18", "#2A2A2E", "#6A5A3A", "#3A3A30", "#7A6A50", "#4A3A2A",
                              "#2E3A4E", "#6E2A1E", "#8A7A5A", "#B8A888", "#9A3020", "#3A4430"],
                       banners=["#A82018", "#C8942E", "#1E1E22", "#E2D6BE", "#8E1A14", "#3A3A44"],
                       armor="#3A3632", armor_dark="#221E1C")
    A_specs = [("charge", "armored", dict(weapon="spear", hat="helmet", cloth=0, cloth2=3)),
               ("charge", "soldier", dict(weapon="spear", hat="helmet", cloth=7, cloth2=5)),
               ("thrust", "armored", dict(weapon="spear", hat="helmet_plume", cloth=0, cloth2=3)),
               ("charge", "soldier", dict(weapon="halberd", hat="helmet", cloth=10, cloth2=4, shield=True)),
               ("slash_high", "armored", dict(weapon="sword", hat="helmet", cloth=0, cloth2=3, shield=True)),
               ("charge", "soldier", dict(weapon="spear", hat="helmet", cloth=7, cloth2=3, banner=0)),
               ("guard", "armored", dict(weapon="sword", hat="helmet", cloth=0, cloth2=5, shield=True)),
               ("charge", "armored", dict(weapon="standard", hat="helmet", cloth=0, cloth2=3, banner=4))]
    B_specs = [("charge", "armored", dict(weapon="spear", hat="helmet", cloth=1, cloth2=4)),
               ("charge", "soldier", dict(weapon="halberd", hat="helmet", cloth=2, cloth2=1)),
               ("thrust", "armored", dict(weapon="spear", hat="helmet", cloth=11, cloth2=1)),
               ("slash_high", "soldier", dict(weapon="sword", hat="helmet", cloth=2, cloth2=1, shield=True)),
               ("charge", "soldier", dict(weapon="spear", hat="helmet", cloth=1, cloth2=8, banner=1)),
               ("guard", "armored", dict(weapon="sword", hat="helmet_plume", cloth=11, cloth2=1, shield=True)),
               ("charge", "armored", dict(weapon="standard", hat="helmet", cloth=1, cloth2=4, banner=2))]
    builders = []
    for (pose, outfit, kw) in A_specs + B_specs:
        builders.append(lambda mb, pose=pose, outfit=outfit, kw=kw:
                        P.figure(mb, random.Random(hash((pose, outfit, str(kw))) & 0xFFFF), pose, outfit, jitter=6.0, **kw))
    for i, (pose, wpn, ban, cl) in enumerate([("ride_charge", "spear", None, 0), ("ride_spear", "halberd", 4, 7),
                                              ("ride_charge", "spear", None, 1), ("ride_spear", "spear", 2, 11)]):
        builders.append(lambda mb, pose=pose, wpn=wpn, ban=ban, cl=cl, i=i:
                        P.rider(mb, random.Random(50 + i), "gallop", pose, weapon=wpn, hat="helmet_plume",
                                cloth=cl, cloth2=3, coat="HorseCoat%d" % (i % 4), banner=ban))
    pcol = F.prototypes(builders, mats, "BattleFigures")
    nA, nB = len(A_specs), len(B_specs)
    pts = []
    # army A: from the foreground (left) up to the clash line, facing up-right
    dA = Vector((0.45, 1.0)).normalized()
    dB = Vector((-0.55, -1.0)).normalized()
    count = 900 if pv else 2600
    for _ in range(count):
        x = rng.uniform(-260, 420)
        y = rng.uniform(-10, line_y(x) - 2)
        if y < 8 and x > -20:
            continue
        # thinner far from the line
        dl = line_y(x) - y
        if rng.random() > 0.25 + 0.75 * math.exp(-dl / 45.0):
            continue
        k = rng.choices(range(nA), weights=[4, 4, 2, 2, 2, 1, 1, 0.6])[0]
        if rng.random() < 0.06:
            k = nA + nB + rng.choice([0, 1])
        ang = face(dA.x, dA.y) + rng.uniform(-0.35, 0.35)
        pts.append((x, y, g.z(x, y) - 0.03, ang, rng.uniform(0.94, 1.06), k))
    for _ in range(int(count * 1.1)):
        x = rng.uniform(-300, 700)
        y = rng.uniform(line_y(x) + 1, line_y(x) + 260)
        dl = y - line_y(x)
        if rng.random() > 0.25 + 0.75 * math.exp(-dl / 60.0):
            continue
        k = nA + rng.choices(range(nB), weights=[4, 3, 2, 2, 1, 1, 0.6])[0]
        if rng.random() < (0.12 if x > 80 else 0.04):
            k = nA + nB + rng.choice([2, 3])
        ang = face(dB.x, dB.y) + rng.uniform(-0.35, 0.35)
        pts.append((x, y, g.z(x, y) - 0.03, ang, rng.uniform(0.94, 1.06), k))
    F.instance("Armies", pts, pcol)
    # foreground heroes (army A) close to the camera, unique meshes
    fg = MeshBuilder()
    for i, (x, y, pose, kw) in enumerate([
            (-9.0, 10.0, "charge", dict(weapon="spear", hat="helmet", cloth=0, cloth2=3)),
            (-3.0, 16.0, "charge", dict(weapon="standard", hat="helmet_plume", cloth=0, cloth2=3, banner=0)),
            (-14.0, 19.0, "charge", dict(weapon="halberd", hat="helmet", cloth=7, cloth2=3, shield=True)),
            (6.0, 24.0, "thrust", dict(weapon="spear", hat="helmet", cloth=0, cloth2=5)),
            (-7.5, 27.0, "slash_high", dict(weapon="sword", hat="helmet_plume", cloth=0, cloth2=3, cape=True))]):
        f = MeshBuilder()
        P.figure(f, random.Random(300 + i), pose, "armored", jitter=3.0, **kw)
        fg.extend(f, Matrix.Translation((x, y, g.z(x, y))) @ Matrix.Rotation(face(dA.x, dA.y) + rng.uniform(-0.2, 0.2), 4, "Z"))
    fg.build("Heroes", mats)
    # trampled debris: dropped spears and shields
    deb = MeshBuilder()
    for _ in range(140 if not pv else 60):
        x = rng.uniform(-80, 260)
        y = line_y(x) + rng.uniform(-30, 25)
        z = g.z(x, y) + 0.04
        a = rng.uniform(0, math.tau)
        L_ = rng.uniform(2.0, 3.2)
        deb.cylinder((x, y, z), (x + math.cos(a) * L_, y + math.sin(a) * L_, z + 0.02), 0.018, 0.018, "Wood", 5)
    deb.build("Debris", mats)
    # ---- arrows: a volley arcing over the line ----------------------------------------------
    ar = MeshBuilder()
    for _ in range(420 if not pv else 200):
        cx = rng.gauss(60, 70)
        cy = line_y(cx) + rng.gauss(40, 30)
        cz = rng.uniform(28, 70)
        d = Vector((-0.45 + rng.uniform(-0.06, 0.06), -0.7, -0.35 + rng.uniform(-0.06, 0.06))).normalized()
        p0 = Vector((cx, cy, cz))
        ar.cylinder(tuple(p0), tuple(p0 + d * 1.0), 0.012, 0.012, "Wood", 4)
        ar.cylinder(tuple(p0 + d * 1.0), tuple(p0 + d * 1.1), 0.02, 0.0, "Metal", 4)
        ar.cylinder(tuple(p0 - d * 0.05), tuple(p0 + d * 0.18), 0.03, 0.03, "Feather", 3)
    ar.build("Arrows", mats)
    # ---- dust ---------------------------------------------------------------------------------
    for i in range(26 if not pv else 14):
        x = rng.uniform(-120, 420)
        y = line_y(x) + rng.uniform(-15, 35)
        w = rng.uniform(40, 110)
        h = rng.uniform(14, 34)
        dm = T.mist_material("Dust%d" % i, rng.choice(["#D2AA80", "#C89C74", "#DDB890"]),
                             strength=rng.uniform(0.9, 1.25), density=rng.uniform(0.45, 0.7),
                             seed=float(i), softness=0.5, stretch=2.0, edge=0.25)
        T.card("Dust%d" % i, (x, y, g.z(x, y) + h * 0.42), (w, h), dm, rot_z=rng.uniform(-0.3, 0.3))
    # camera: low, behind the left army's flank
    cam = L.camera((-6.0, -14.0, 3.6), (24.0, 120.0, 9.0), focal_mm=30.0, dof=(30.0, 9.0))
    return dict(camera=cam, beams=tuple(S.dir_from(*SUN) * 20000.0),
                beams_cfg=dict(ray_length=0.28, strength=0.3, threshold=1.2),
                glow=dict(threshold=1.0, mix=-0.8, size=8),
                grade=dict(saturation=1.03, contrast=1.08, shadows=(0.01, 0.0, -0.01),
                           highlights=(0.03, 0.01, -0.025), clarity=0.14, vignette=0.26,
                           canvas=0.02, sharpen=0.3))
