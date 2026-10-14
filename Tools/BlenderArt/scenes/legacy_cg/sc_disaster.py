"""Event: Disaster - a locust swarm darkens the sky over withered fields.

A farmer kneels in despair at the edge of his blighted field; dead stalks and cracked earth run
to a lone farmhouse and a dead tree; from the right a vast, roiling swarm of locusts pours across
the sky, swallowing the sun into a sickly ochre glow with rays breaking through its gaps.
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

SPEC = dict(name="Disaster", art="Art/Events/Disaster.png", master="Events/Disaster@2x.png",
            size=(1280, 720), ss=1, spp=20, preview_spp=12, seed=121)

SUN = (102.0, 12.0)


def cracked_material():
    """Parched field: cracked earth (Voronoi edges) with dry stubble patches."""
    from ironart.scenes_sky import G, lin4
    from ironart.scenes_terrain import _fin, noise
    mat, nb, created = M.new("Parched")
    if not created:
        return mat
    b = G(nb.tree)
    P_ = nb.node("ShaderNodeNewGeometry").outputs["Position"]
    v = nb.node("ShaderNodeTexVoronoi", voronoi_dimensions="2D", feature="DISTANCE_TO_EDGE")
    v.inputs["Scale"].default_value = 1.6
    v.inputs["Randomness"].default_value = 0.9
    b.link(P_, v.inputs["Vector"])
    crack = b.smooth(v.outputs["Distance"], 0.03, 0.0)
    n1 = noise(nb, P_, 0.08, 5, 0.6)
    n2 = noise(nb, P_, 1.5, 3, 0.6)
    col = b.mix(lin4("#8A7450"), lin4("#B09468"), b.smooth(n1, 0.3, 0.7))
    col = b.mix(col, lin4("#6E6036"), b.math("MULTIPLY", b.smooth(n2, 0.55, 0.75), 0.5))
    col = b.mix(col, lin4("#2E2418"), b.math("MULTIPLY", crack, b.smooth(n1, 0.35, 0.5)))
    p = b.principled(Base_Color=col, Roughness=0.95, Specular_IOR_Level=0.2,
                     Normal=b.bump(b.math("ADD", b.math("MULTIPLY", crack, -1.0), b.math("MULTIPLY", n2, 0.3)), 0.6, 0.03))
    return _fin(mat, nb, p.outputs[0])


def build(r):
    import bpy
    pv = r["preview"]
    rng = random.Random(121)
    S.build(dict(
        stops=[(0.0, "#C08A58"), (0.05, "#A07048"), (0.18, "#705446"), (0.45, "#46383A"),
               (1.0, "#2A2228")],
        strength=0.9,
        glows=[dict(dir=SUN, color="#FF9A3A", lobes=[(4, 0.6), (40, 1.8), (400, 8.0)],
                    horizon=(0.8, 0.07, 2.0))],
        discs=[dict(dir=SUN, radius_deg=1.0, color="#FFD08A", strength=12.0, edge=0.15)],
        clouds=[dict(height=1500, scale=1700, coverage=0.5, softness=0.3, lit="#B07450",
                     shadow="#2A201E", rim_color="#FF9A50", rim=3.0, rim_power=6.0, opacity=0.9,
                     stretch=(1.0, 0.6), fade=0.08, shade=7.0, core_dark=0.55, seed=41.0, haze=0.5)],
        light=dict(strength=0.6, tint="#C8B498"),
        fog=dict(haze=4.0e-4, haze_falloff=0.002, haze_max=0.9, haze_zmax=0.1, haze_tint="#D8C8A8",
                 mist=0.004, mist_falloff=0.1, mist_max=0.4, mist_color="#B89868"),
    ))
    S.sun(SUN[0], SUN[1], energy=3.2, color="#FFB860", angle_deg=2.0)
    def hfn(X, Y):
        h = 0.8 * T.fbm2(X, Y, 40.0, 4, seed=1)
        h += T.smoothstep(600.0, 2200.0, Y) * 180.0 * T.ridged2(X, Y, 700.0, 5, seed=2, warp=300.0)
        # furrows
        h += 0.12 * np.sin(X * 1.6) * T.smoothstep(300.0, 0.0, Y)
        return h
    # fine near field (cracks, furrows) + coarse far field (overlap sunk 5 cm: no z-fight)
    g = T.field_from(hfn, -500, 700, -20, 330, 1.0 if pv else 0.5)
    g.build("Field", cracked_material())
    T.field_from(lambda X, Y: hfn(X, Y) - 0.05 * (Y < 332.0), -1500, 1700, 320, 3000, 3.0).build("FieldFar", cracked_material())
    # dead stalks (instanced brown tufts) in rows
    sm = {"Grass": F.foliage_material("DeadStalk", ("#6A5232", "#9A7E50"), translucency=0.2, vary=0.5),
          "BarkDead": F.bark_material("DBark", ("#3A3028", "#5A4A3C"))}
    scol = F.prototypes([lambda mb, i=i: F.grass_tuft(mb, random.Random(i), 1.1, 9, "Grass", 0.15) for i in range(4)],
                        sm, "Stalks")
    sp = []
    for row in range(-60, 140):
        x = row * 0.65
        for k in range(70 if not pv else 35):
            y = rng.uniform(4, 150)
            if rng.random() < 0.45:
                continue
            sp.append((x + rng.uniform(-0.1, 0.1), y, g.z(x, y) - 0.05, rng.uniform(0, math.tau),
                       rng.uniform(0.6, 1.1), rng.randrange(4)))
    F.instance("Stalks", sp, scol)
    # farmhouse, dead trees
    am = A.materials(thatch="#7A6440", plaster="#B8A88A")
    pm = P.materials(cloth=["#4A4034", "#5E5040", "#7A6A50", "#2E2C28", "#6A4A30", "#B8AA8A",
                            "#4A3A2E", "#5A5A48", "#5A3022", "#C8BCA0", "#7A3A26", "#3A4A4E"])
    mats = dict(am)
    mats.update(pm)
    vil = MeshBuilder()
    vil.extend(A.scaled(A.thatched_house(random.Random(3), 1.0, foundation=0.3), 7.5, (-70, 160, g.z(-70, 160)), rot_z=0.4))
    vil.extend(A.scaled(A.thatched_house(random.Random(4), 0.8, foundation=0.3), 7.5, (-40, 190, g.z(-40, 190)), rot_z=-0.2))
    vil.build("Farm", mats)
    tcol = F.prototypes([lambda mb: F.dead_tree(mb, random.Random(5), 10.0, depth=5),
                         lambda mb: F.dead_tree(mb, random.Random(6), 7.0, depth=4)], sm, "DTrees")
    F.instance("DTrees", [(-22, 120, g.z(-22, 120) - 0.2, 0.3, 1.2, 0), (60, 260, g.z(60, 260), 1.0, 1.0, 1),
                          (-110, 210, g.z(-110, 210), 2.0, 0.9, 1)], tcol)
    # the farmer in despair (foreground left of centre) with a dropped basket
    f = MeshBuilder()
    P.figure(f, random.Random(9), "despair", "farmer", cloth=1, cloth2=5, hat=None)
    fo = f.build("Farmer", mats)
    fo.location = (-3.0, 4.5, g.z(-3.0, 4.5) - 0.02)
    fo.rotation_euler = (0, 0, math.radians(200))
    hat = MeshBuilder()
    hat.lathe([(0.36, 0.0), (0.26, 0.03), (0.12, 0.07), (0.0, 0.1)], "Straw", 16)
    ho = hat.build("Hat", mats)
    ho.location = (-1.9, 3.7, g.z(-1.9, 3.7) + 0.02)
    ho.rotation_euler = (0.35, 0.2, 0.0)
    # ---- the swarm --------------------------------------------------------------------------
    # dense core as dark rolling banks (cards) + a cloud of individual locusts (instanced)
    for i in range(36):
        x = rng.uniform(60, 520)
        y = rng.uniform(220, 700)
        z = rng.uniform(60, 260) - max(0.0, 60 - x) * 0.5
        dm = T.mist_material("Swarm%d" % i, rng.choice(["#1C1814", "#221C16", "#18140F"]), strength=1.0,
                             density=rng.uniform(0.9, 1.2), seed=float(i * 9), softness=0.4, stretch=1.6,
                             edge=0.3)
        T.card("Swarm%d" % i, (x, y, z), (rng.uniform(220, 420), rng.uniform(90, 190)), dm,
               rot_z=rng.uniform(-0.4, 0.4), shadow=True)
    lm = {"Locust": M.principled("DLocust", "#1E1A14", 0.9, specular=0.1),
          "LocustWing": M.principled("DWing", "#2E2820", 0.9, specular=0.1)}
    lcol = F.prototypes([lambda mb: (mb.sphere((0, 0, 0), 0.5, "Locust", 6, 3, scale=(0.35, 1.0, 0.3)),
                                     mb.face([mb.v((0, 0.0, 0.05)), mb.v((1.2, 0.3, 0.1)), mb.v((1.0, -0.4, 0.05))], "LocustWing"),
                                     mb.face([mb.v((0, 0.0, 0.05)), mb.v((-1.2, 0.3, 0.1)), mb.v((-1.0, -0.4, 0.05))], "LocustWing"))],
                        lm, "Locust")
    n = 25000 if pv else 70000
    nr = np.random.default_rng(121)
    M_ = 600000
    xs = nr.uniform(-150, 500, M_)
    ys = nr.uniform(20, 700, M_)
    zs = nr.uniform(4, 220, M_)
    dens = T.smoothstep(0, 320, xs) * T.smoothstep(2.0, 40.0, zs) * T.smoothstep(260.0, 140.0, zs - 0.25 * (xs - 100))
    dens *= T.smoothstep(0.35, 0.6, T.fbm2(xs + zs * 0.7, ys + zs * 0.4, 70.0, 3, seed=5))
    keep = np.nonzero(nr.random(M_) < dens)[0][:n]
    lp = []
    for i in keep:
        s_ = rng.uniform(0.12, 0.2) * (1.0 + ys[i] / 400.0)
        lp.append((float(xs[i]), float(ys[i]), float(zs[i]),
                   (rng.uniform(-0.5, 0.5), rng.uniform(-0.3, 0.3), rng.uniform(0, math.tau)), s_, 0))
    F.instance("Locusts", lp, lcol)
    cam = L.camera((-9.0, -6.0, 1.7), (40.0, 200.0, 32.0), focal_mm=28.0, dof=(16.0, 5.6))
    return dict(camera=cam, beams=tuple(S.dir_from(*SUN) * 20000.0),
                beams_cfg=dict(ray_length=0.32, strength=0.35, threshold=0.9),
                glow=dict(threshold=0.9, mix=-0.75, size=9),
                grade=dict(saturation=0.98, contrast=1.1, shadows=(0.01, 0.0, -0.01),
                           highlights=(0.03, 0.004, -0.018), clarity=0.14, vignette=0.32,
                           canvas=0.012, sharpen=0.3))
