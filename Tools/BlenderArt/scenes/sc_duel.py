"""Duel background: two swordsmen face each other on a cliff edge at sunset, petals in the wind.

Seen from a little above and behind, the challenger stands in the left third and the defender in
the right third right at the brink, cloaks streaming in the same wind; beyond the edge a sea of
clouds far below runs to peaks on the horizon and the sun sits between them (the centre stays
open and low in detail for the duel UI); a flowering plum leans in from the far left and its
petals drift across the frame; dry grass on the cliff top in the foreground.
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

SPEC = dict(name="Duel", art="Art/Duel/Background.png", master=None,
            size=(1280, 720), ss=1, spp=24, preview_spp=12, seed=131)

SUN = (90.0, 2.2)
CLOUD_Z = 300.0


def build(r):
    import bpy
    pv = r["preview"]
    rng = random.Random(131)
    S.build(dict(
        stops=[(0.0, "#F8A070"), (0.025, "#F08A64"), (0.07, "#D07872"), (0.16, "#8E6A8C"),
               (0.36, "#50588A"), (1.0, "#222A56")],
        strength=1.0,
        glows=[dict(dir=SUN, color="#FF5A30", lobes=[(3, 0.4), (24, 1.0), (600, 4.5)],
                    horizon=(1.2, 0.05, 1.6))],
        discs=[dict(dir=SUN, radius_deg=0.85, color="#FFD098", strength=16.0, edge=0.06)],
        clouds=[dict(height=2400, scale=3600, coverage=0.38, softness=0.24, lit="#FFB088",
                     shadow="#6A4A68", rim_color="#FFD0A0", rim=3.0, rim_power=5.0, opacity=0.85,
                     stretch=(1.0, 0.35), fade=0.14, shade=7.0, seed=71.0, haze=0.6)],
        light=dict(strength=0.5, tint="#B8A8D0"),
        fog=dict(haze=3.5e-4, haze_falloff=0.001, haze_h0=CLOUD_Z, haze_max=0.9, haze_zmax=0.08),
    ))
    S.sun(SUN[0], SUN[1] + 2.5, energy=4.0, color="#FFA868", angle_deg=1.5)
    # cloud sea far below
    from sc_sect import cloud_material
    def cs(X, Y):
        # billowing heaps (inverted ridged noise) + small puffs, as in the Sect scene
        heaps = 1.0 - T.ridged2(X, Y, 260.0, 4, sharp=1.0, seed=13)
        return CLOUD_Z + 50.0 * heaps ** 1.6 + 12.0 * T.fbm2(X, Y, 50.0, 3, seed=14)
    T.field_from(cs, -6000, 6000, 150, 9000, 24.0 if pv else 12.0).build("CloudSea", cloud_material(CLOUD_Z, "DuelCloudSea"))
    # soft layers of sunset-coloured mist over the cloud heaps: the sea reads as cloud, not dunes
    for i, (dz, colr, dens) in enumerate([(14.0, "#9C7E9E", 0.8), (28.0, "#C48E9C", 0.75), (42.0, "#E4A29A", 0.7),
                                          (56.0, "#F6BA9C", 0.6), (70.0, "#FFD4B4", 0.45)]):
        mm = T.mist_material("DuelCloudMist%d" % i, colr, strength=1.0, density=dens, scale=26.0,
                             seed=float(7 + i * 5), softness=0.55, stretch=1.6, edge=0.12)
        T.flat_card("DuelCloudMist%d" % i, (0.0, 5200.0, CLOUD_Z + dz), (12000.0, 10000.0), mm)
    # distant peaks breaking the cloud sea (silhouettes against the glow)
    def peaks(X, Y):
        b = 0.0 * X
        for (px, py, w, k) in ((-1400, 3200, 500, 1.0), (-2600, 4200, 700, 0.8), (1500, 2800, 450, 0.9),
                               (2700, 4600, 800, 1.0), (-500, 6000, 900, 0.5)):
            b = b + k * np.exp(-(((X - px) / w) ** 2 + ((Y - py) / w) ** 2))
        return CLOUD_Z - 100 + b * 700.0 * (0.6 + 0.4 * T.ridged2(X, Y, 300.0, 5, seed=15))
    pm_ = T.rock_material("DuelPeaks", ("#3A3440", "#5A5058"), scale=0.01, strata=0.4, vertical=True)
    T.field_from(peaks, -5000, 5000, 1500, 7500, 20.0).build("Peaks", pm_)
    # the cliff top: a ridge running left-right, edge towards +Y (the void)
    def cliff(X, Y):
        edge = 7.0 + 1.5 * np.sin(X / 9.0) + 2.0 * (T.fbm2(X, Y, 6.0, 3, seed=1) - 0.5)
        top = 500.0 + 0.4 * T.fbm2(X, Y, 5.0, 4, seed=2) - 0.012 * (X * X) * 0.02
        drop = T.smoothstep(edge - 1.0, edge + 6.0, Y)
        return top - drop * (240.0 * T.smoothstep(edge, edge + 120.0, Y) + 8.0) + \
            (T.ridged2(X, Y, 4.0, 4, seed=3) - 0.5) * 0.8 * drop
    c = T.field_from(cliff, -60, 60, -30, 60, 0.3 if pv else 0.18)
    rm = T.terrain_material("DuelCliff", grass=("#5E5A36", "#8A7A44"), dry="#A88E58", dirt="#6A5640",
                            rock=("#5A4E48", "#8A7A6C"), slope=(0.82, 0.92), grass_scale=0.15,
                            dry_amt=0.5)
    c.build("Cliff", rm)
    # dry grass tufts on the cliff top
    gm = {"Grass": F.foliage_material("DuelGrass", ("#7A6A3A", "#B89A58"), translucency=0.45, vary=0.5)}
    gcol = F.prototypes([lambda mb, i=i: F.grass_tuft(mb, random.Random(i), 0.38, 16, "Grass", 0.12) for i in range(4)],
                        gm, "DuelGrass")
    gp = []
    for _ in range(6000 if pv else 16000):
        x = rng.uniform(-20, 20)
        y = rng.uniform(-14, 9)
        if c.nz_at(x, y, 0.2) < 0.85:
            continue
        if min(math.hypot(x + 4.0, y - 4.0), math.hypot(x - 4.0, y - 4.4)) < 0.9:
            continue
        near = T.smoothstep(4.0, -10.0, y)
        gp.append((x, y, c.z(x, y) - 0.03, rng.uniform(0, math.tau), rng.uniform(0.45, 0.8) + 0.5 * near * rng.random(),
                   rng.randrange(4)))
    F.instance("Grass", gp, gcol)
    # the duellists
    mats = P.materials(cloth=["#1E2230", "#6A1E1A", "#2A2A2E", "#C8BCA0", "#4A3A2E", "#E2D8C4",
                              "#3A2A3A", "#2E3A3E", "#5A3A2A", "#D8D0C0", "#8A2A20", "#1E2A3A"])
    duo = MeshBuilder()
    f = MeshBuilder()
    P.figure(f, random.Random(1), "guard", "wanderer", cloth=0, cloth2=3, hat="band",
             weapon="sword", cape=True, cape_wind=(1.6, 0.2), jitter=0.0)
    duo.extend(f, Matrix.Translation((-4.0, 4.0, c.z(-4.0, 4.0) - 0.02)) @ Matrix.Rotation(math.radians(-90), 4, "Z") @ Matrix.Scale(1.1, 4))
    f = MeshBuilder()
    P.figure(f, random.Random(2), "sword_ready", "general", cloth=1, cloth2=4, hat="topknot",
             weapon="sword", cape=True, cape_wind=(1.6, 0.2), jitter=0.0, hair_long=True)
    duo.extend(f, Matrix.Translation((4.0, 4.4, c.z(4.0, 4.4) - 0.02)) @ Matrix.Rotation(math.radians(90), 4, "Z") @ Matrix.Scale(1.06, 4))
    duo.build("Duellists", mats)
    # flowering plum on the far left
    fm = {"Leaves": F.foliage_material("Blossom", ("#E8B0BC", "#FFE0E4"), translucency=0.5, vary=0.6),
          "LeavesCore": F.foliage_material("BlossomCore", ("#B07A88", "#D8A0AC"), core=True, translucency=0.2),
          "Bark": F.bark_material("PlumBark", ("#1E1614", "#3A2C26"))}
    tr = MeshBuilder()
    F.plum_tree(tr, random.Random(8), 6.0, depth=4, density=1.2)
    to = tr.build("Plum", fm, auto_smooth_deg=None)
    to.location = (-8.2, 6.5, c.z(-8.2, 6.5) - 0.2)
    to.rotation_euler = (0.0, 0.25, 0.4)
    # drifting petals (instanced tiny quads), denser near the tree, streaming right on the wind
    pcol = F.prototypes([lambda mb: (mb.face([mb.v((-0.012, 0, 0)), mb.v((0, -0.016, 0.002)),
                                              mb.v((0.012, 0, 0)), mb.v((0, 0.016, 0.002))], "Leaves"))],
                        fm, "Petal")
    pp = []
    for _ in range(2500 if pv else 6000):
        x = rng.uniform(-10, 12)
        t = (x + 10) / 22.0
        if rng.random() < t * 0.7:
            continue
        y = rng.uniform(-4, 12)
        z = c.z(-8.2, 6.5) + 0.6 + rng.uniform(-0.5, 4.5) + 1.2 * math.sin(x / 3.5) * t
        pp.append((x, y, z, (rng.uniform(0, math.tau), rng.uniform(0, math.tau), rng.uniform(0, math.tau)),
                   rng.uniform(1.0, 2.2), 0))
    F.instance("Petals", pp, pcol, hide_shadow=True)
    cz = c.z(0.0, -20.0) + 4.2
    cam = L.camera((0.0, -20.0, cz), (0.0, 80.0, cz - 100.0 * math.tan(math.radians(4.0))), focal_mm=50.0,
                   dof=(24.0, 8.0))
    return dict(camera=cam, beams=tuple(S.dir_from(*SUN) * 30000.0),
                beams_cfg=dict(ray_length=0.22, strength=0.25, threshold=1.4),
                glow=dict(threshold=1.0, mix=-0.8, size=9),
                grade=dict(saturation=1.06, contrast=1.06, shadows=(0.0, -0.004, 0.02),
                           highlights=(0.03, -0.004, 0.0), clarity=0.12, vignette=0.26,
                           canvas=0.012, sharpen=0.25))
