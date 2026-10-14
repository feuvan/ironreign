"""Event: Battle - two armies clash on an open plain.

Low camera inside the charging (left) army: spearmen and a standard bearer run past in the
foreground towards the clash line that recedes diagonally to the right; the enemy host with
cavalry pours in from the far side; dust rises along the line, glowing in the low sun ahead;
a volley of arrows arcs across the hazy sky; banners everywhere.
"""

import math
import random

from mathutils import Matrix, Vector

from ironart import materials as M
from ironart import scenes_flora as F
from ironart import scenes_look as L
from ironart import scenes_people as P
from ironart import scenes_sky as S
from ironart import scenes_terrain as T
from ironart.geometry import MeshBuilder

SPEC = dict(name="Battle", art="Art/Events/Battle.png", master="Events/Battle@2x.png",
            size=(1280, 720), ss=1, spp=20, preview_spp=12, seed=21)

SUN = (102.0, 13.0)


def face(dx, dy):
    """Rotation (rad) turning a -Y facing figure towards (dx, dy)."""
    return math.atan2(dx, -dy)


def line_x(y):
    """The clash line runs away from the viewer, drifting right."""
    return 2.0 + 0.12 * y


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
        clouds=[dict(height=1800, scale=2800, coverage=0.58, softness=0.18, lit="#F8CC98",
                     shadow="#585260", rim=3.0, opacity=0.95, stretch=(1.0, 0.5), fade=0.08,
                     shade=9.0, seed=4.0, haze=0.5, core_dark=0.5)],
        light=dict(strength=0.6, tint="#D8DCE8"),
        fog=dict(haze=1.6e-4, haze_falloff=0.002, haze_max=0.9, haze_zmax=0.1,
                 mist=0.0025, mist_falloff=0.12, mist_h0=0.0, mist_max=0.5,
                 mist_color="#C8A47E", mist_strength=1.0),
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
        knoll = 11.0 * np.exp(-(((X + 42.0) / 38.0) ** 2 + ((Y + 34.0) / 30.0) ** 2))
        return h + hills * 220.0 * far + T.smoothstep(900.0, 3000.0, Y) * 150.0 + knoll
    g = T.field_from(hfn, -1500, 2500, -80, 3200, 4.0 if pv else 2.0)
    g.build("Plain", gm)
    rmat = T.terrain_material("BattleRange", grass=("#5E6A48", "#7A7656"), rock=("#6A6660", "#8A8478"),
                              slope=(0.72, 0.86), grass_scale=0.002)

    def rfn(X, Y):
        r_ = T.ridged2(X, Y, 1800.0, 7, sharp=1.8, seed=8, warp=900.0)
        return r_ ** 1.3 * 800.0
    T.field_from(rfn, -12000, 14000, 6000, 18000, 60.0).build("Range", rmat)
    # ---- armies (instanced prototypes) ------------------------------------------------------
    mats = P.materials(cloth=["#5A1E18", "#22304A", "#34445E", "#3A3A30", "#7A6A50", "#4A3A2A",
                              "#2E3A4E", "#6E2A1E", "#8A7A5A", "#B8A888", "#9A3020", "#1C2436"],
                       banners=["#A82018", "#D8A42E", "#1E2A44", "#E2D6BE", "#8E1A14", "#3A3A44"],
                       armor="#3A3632", armor_dark="#221E1C")
    mats["Metal"] = M.principled("BHelmet", "#4A4C50", 0.42, metallic=0.9)
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
    dA = Vector((1.0, 0.12)).normalized()                     # army A (left) charges right
    dB = Vector((-1.0, -0.12)).normalized()
    rows = 26 if not pv else 16
    for side, specs_n, base_k, dvec in ((-1, nA, 0, dA), (1, nB, nA, dB)):
        for row in range(rows):
            for k in range(int(440 / 1.2)):
                y = 2.0 + k * 1.2 + rng.uniform(-0.35, 0.35) + (0.6 if row % 2 else 0.0)
                depth = 0.7 + row * 1.5 + rng.uniform(-0.35, 0.35)
                x = line_x(y) + side * depth
                if y < 12.0 and row < 3:
                    continue                                   # the hero duel near the camera
                if row > 2 and rng.random() < 0.12 + 0.01 * row:
                    continue
                if side < 0:
                    kind = rng.choices(range(nA), weights=[4, 4, 2, 2, 2, 1, 1, 0.6])[0]
                else:
                    kind = nA + rng.choices(range(nB), weights=[4, 3, 2, 2, 1, 1, 0.6])[0]
                if row in (5, 6) and k % 10 == 0:
                    kind = base_k + specs_n - 1                # standard bearers
                if row > 8 and rng.random() < 0.18:
                    kind = nA + nB + (rng.choice([0, 1]) if side < 0 else rng.choice([2, 3]))
                ang = face(dvec.x, dvec.y) + rng.uniform(-0.35, 0.35)
                if row == 0:
                    x += rng.uniform(-0.8, 0.8)                # the melee mixes along the line
                pts.append((x, y, g.z(x, y) - 0.03, ang, rng.uniform(0.94, 1.06), kind))
    # a cavalry wedge of army A sweeping across the left foreground towards the line
    for i in range(46 if not pv else 30):
        row = int(math.sqrt(i * 2))
        k = i - row * (row + 1) // 2
        x = -14.0 - row * 5.0 + rng.uniform(-0.8, 0.8)
        y = -6.0 + (k - row / 2.0) * 3.4 + rng.uniform(-0.6, 0.6)
        if y > 1.0 and x > line_x(y) - 42.0:
            continue
        kind = nA + nB + rng.choice([0, 1])
        pts.append((x, y, g.z(x, y) - 0.05, face(dA.x, dA.y) + rng.uniform(-0.12, 0.12), rng.uniform(0.96, 1.04), kind))
    F.instance("Armies", pts, pcol)
    # foreground heroes (army A) close to the camera, unique meshes
    fg = MeshBuilder()
    heroes = [(-1.2, 3.0, "thrust", dA, dict(weapon="spear", hat="helmet_plume", cloth=0, cloth2=3, cape=True)),
              (1.6, 4.2, "guard", dB, dict(weapon="sword", hat="helmet", cloth=1, cloth2=4, shield=True)),
              (-3.4, 7.0, "charge", dA, dict(weapon="standard", hat="helmet", cloth=0, cloth2=3, banner=0)),
              (3.6, 8.5, "slash_high", dB, dict(weapon="sword", hat="helmet_plume", cloth=11, cloth2=1)),
              (-1.0, 10.0, "charge", dA, dict(weapon="halberd", hat="helmet", cloth=7, cloth2=3, shield=True)),
              (5.6, 5.0, "charge", dB, dict(weapon="spear", hat="helmet", cloth=2, cloth2=1)),
              (-5.6, 4.0, "charge", dA, dict(weapon="spear", hat="helmet", cloth=0, cloth2=5)),
              (-2.6, -1.0, "fall", dB, dict(weapon=None, hat="helmet", cloth=1, cloth2=4)),
              (2.8, 0.5, "thrust", dB, dict(weapon="halberd", hat="helmet", cloth=2, cloth2=1))]
    for i, (x, y, pose, dv, kw) in enumerate(heroes):
        f = MeshBuilder()
        P.figure(f, random.Random(300 + i), pose, "armored", jitter=3.0, **kw)
        fg.extend(f, Matrix.Translation((x, y, g.z(x, y))) @ Matrix.Rotation(face(dv.x, dv.y) + rng.uniform(-0.25, 0.25), 4, "Z"))
    fg.build("Heroes", mats)
    # trampled debris: dropped spears and shields
    deb = MeshBuilder()
    for _ in range(140 if not pv else 60):
        y = rng.uniform(5, 300)
        x = line_x(y) + rng.uniform(-20, 20)
        z = g.z(x, y) + 0.04
        a = rng.uniform(0, math.tau)
        L_ = rng.uniform(2.0, 3.2)
        deb.cylinder((x, y, z), (x + math.cos(a) * L_, y + math.sin(a) * L_, z + 0.02), 0.018, 0.018, "Wood", 5)
    deb.build("Debris", mats)
    # ---- arrows: a volley arcing over the line ----------------------------------------------
    ar = MeshBuilder()
    for _ in range(420 if not pv else 200):
        cy = rng.uniform(40, 220)
        cx = line_x(cy) + rng.gauss(0, 18)
        cz = rng.uniform(22, 60)
        d = Vector((-0.85 + rng.uniform(-0.06, 0.06), -0.25, -0.3 + rng.uniform(-0.08, 0.08))).normalized()
        p0 = Vector((cx, cy, cz))
        ar.cylinder(tuple(p0), tuple(p0 + d * 1.0), 0.012, 0.012, "Wood", 4)
        ar.cylinder(tuple(p0 + d * 1.0), tuple(p0 + d * 1.1), 0.02, 0.0, "Metal", 4)
        ar.cylinder(tuple(p0 - d * 0.05), tuple(p0 + d * 0.18), 0.03, 0.03, "Feather", 3)
    ar.build("Arrows", mats)
    # ---- dust ---------------------------------------------------------------------------------
    for i in range(26 if not pv else 14):
        y = rng.uniform(25, 420)
        x = line_x(y) + rng.uniform(-14, 14)
        w = rng.uniform(25, 70)
        h = rng.uniform(8, 22)
        dm = T.mist_material("Dust%d" % i, rng.choice(["#E0B88A", "#D6A87C", "#E8C49A"]),
                             strength=rng.uniform(1.05, 1.4), density=rng.uniform(0.8, 1.0),
                             seed=float(i), softness=0.5, stretch=2.0, edge=0.25)
        T.card("Dust%d" % i, (x, y, g.z(x, y) + h * 0.42), (w, h), dm, rot_z=rng.uniform(-0.25, 0.25) + 0.0)
    for i in range(5):
        dm = T.mist_material("WedgeDust%d" % i, "#DCB890", strength=1.15, density=0.7, seed=float(40 + i),
                             softness=0.55, stretch=2.0, edge=0.3)
        x = -36.0 - i * 5.0
        y = -10.0 + i * 4.0
        T.card("WedgeDust%d" % i, (x, y, g.z(x, y) + 3.2), (26.0, 7.0), dm, rot_z=math.radians(-24))
    # camera: low, behind the left army's flank
    # the commander and his guard watch from the knoll (foreground silhouettes)
    cmd = MeshBuilder()
    for i, (x, y, rz, wpn, ban) in enumerate([(-33.5, -22.0, -0.5, "spear", None), (-37.0, -24.5, -0.35, "standard", 0),
                                              (-30.5, -25.0, -0.6, "spear", None)]):
        h = MeshBuilder()
        P.rider(h, random.Random(70 + i), "stand", "ride" if i else "ride_spear", weapon=wpn,
                hat="helmet_plume", cloth=0, cloth2=3, coat="HorseCoat%d" % (i % 4), banner=ban, cape=(i == 0))
        cmd.extend(h, Matrix.Translation((x, y, g.z(x, y) - 0.12)) @ Matrix.Rotation(rz, 4, "Z"))
    cmd.build("Commander", mats)
    cam = L.camera((-44.0, -40.0, g.z(-44.0, -40.0) + 4.5), (14.0, 90.0, -2.0), focal_mm=35.0, dof=(22.0, 9.0))
    return dict(camera=cam, beams=tuple(S.dir_from(*SUN) * 20000.0),
                beams_cfg=dict(ray_length=0.28, strength=0.3, threshold=1.2),
                glow=dict(threshold=1.0, mix=-0.8, size=8),
                grade=dict(saturation=1.03, contrast=1.08, shadows=(0.01, 0.0, -0.01),
                           highlights=(0.03, 0.01, -0.025), clarity=0.14, vignette=0.26,
                           canvas=0.012, sharpen=0.3))
