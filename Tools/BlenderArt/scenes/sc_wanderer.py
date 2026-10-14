"""Event: Wanderer - a lone swordsman on a cliff path under the full moon.

Low camera on the narrow mountain path; the wanderer (straw hat, cloak stirring in the wind,
sword across the back) stands on the edge, silhouetted against an enormous full moon with a
silver halo; a gnarled pine leans out over the void; below, a sea of moonlit mist fills the
valleys between dark peaks; cold blue night with a faint warm lantern at his belt.
"""

import math
import random

import numpy as np
from mathutils import Matrix, Vector

from ironart import scenes_flora as F
from ironart import scenes_look as L
from ironart import scenes_people as P
from ironart import scenes_sky as S
from ironart import scenes_terrain as T
from ironart.geometry import MeshBuilder

SPEC = dict(name="Wanderer", art="Art/Events/Wanderer.png", master="Events/Wanderer@2x.png",
            size=(1280, 720), ss=1, spp=128, preview_spp=16, seed=41)

MOON = (87.0, 9.0)


def build(r):
    import bpy
    pv = r["preview"]
    rng = random.Random(41)
    S.build(dict(
        stops=[(0.0, "#5A6E92"), (0.06, "#3E5078"), (0.2, "#25345A"), (0.5, "#141E3A"),
               (1.0, "#0A0F22")],
        strength=0.55,
        glows=[dict(dir=MOON, color="#B8CCF0", lobes=[(6, 0.25), (60, 0.9), (1600, 6.0)],
                    horizon=(0.2, 0.08, 2.0))],
        discs=[dict(dir=MOON, radius_deg=3.2, color="#F2F0E6", strength=9.0, texture=0.45, edge=0.02)],
        stars=dict(density=320.0, size=0.05, strength=5.0, power=9.0, color="#E0E8FF", milky=0.05),
        clouds=[dict(height=2400, scale=3400, coverage=0.36, softness=0.3, lit="#9EB0D0",
                     shadow="#28324E", rim_color="#E8F0FF", rim=4.0, rim_power=30.0, opacity=0.85,
                     stretch=(1.0, 0.4), fade=0.12, shade=6.0, seed=3.0, haze=0.6)],
        light=dict(strength=0.6, tint="#90A8D8"),
        fog=dict(haze=1.1e-4, haze_falloff=0.0009, haze_max=0.9, haze_zmax=0.1,
                 mist=0.0035, mist_falloff=0.012, mist_h0=0.0, mist_max=0.92,
                 mist_color="#5E7098", mist_strength=1.0),
    ))
    S.sun(MOON[0], MOON[1] + 3, energy=0.9, color="#A8C0F0", angle_deg=1.5, name="Moon")
    # ---- terrain: the cliff path (near), dark peaks rising from the mist (far) ------------
    def near_h(X, Y):
        # a ledge path running left-right at z ~ 400, cliff dropping in front (towards +Y)
        edge = 11.0 + 5.0 * np.sin(X / 18.0 + 0.6) + 6.0 * (T.fbm2(X, Y, 15.0, 3, seed=1) - 0.5)
        plateau = 400.0 + 1.5 * T.fbm2(X, Y, 6.0, 4, seed=2)
        drop = T.smoothstep(edge - 2.0, edge + 10.0, Y)
        h = plateau - drop * (400.0 * T.smoothstep(edge, edge + 160.0, Y) + 30.0)
        # rising rock wall behind/left of the path
        wall = T.smoothstep(-15.0, -45.0, Y) * 60.0 * (0.6 + 0.4 * T.ridged2(X, Y, 25.0, 4, seed=3))
        wall += T.smoothstep(-25.0, -70.0, X) * 50.0 * T.ridged2(X, Y, 30.0, 4, seed=4)
        rough = (T.ridged2(X, Y, 8.0, 4, seed=5) - 0.5) * 2.0 * drop
        return h + wall + rough
    near = T.field_from(near_h, -110, 110, -60, 120, 0.6 if pv else 0.35)
    rm = T.rock_material("WRock", ("#3A3C44", "#5E606A"), scale=0.12, strata=0.4, moss="#3A4638",
                         moss_amt=0.5, vertical=True)
    near.build("Cliff", rm)

    def peaks(X, Y):
        r_ = T.ridged2(X, Y, 420.0, 7, sharp=2.2, seed=11, warp=260.0)
        bump = 0.25 + 0.0 * X
        for (px, py, w, k) in ((-700, 1500, 300, 1.2), (420, 1900, 260, 1.4), (1100, 1200, 240, 0.9),
                               (-1500, 2600, 500, 1.1), (1900, 3000, 600, 1.0), (0, 3500, 700, 0.8)):
            bump = bump + k * np.exp(-(((X - px) / w) ** 2 + ((Y - py) / w) ** 2))
        return r_ ** 1.4 * 900.0 * bump - 60.0
    pk = T.field_from(peaks, -4500, 4500, 400, 6000, 8.0 if pv else 5.0)
    pm = T.rock_material("WPeaks", ("#2E3240", "#4A4E5C"), scale=0.02, strata=0.4, moss="#28302E",
                         moss_amt=0.6, vertical=True)
    pk.build("Peaks", pm)
    # ---- pines on the peaks and the hero pine on the ledge ---------------------------------
    fm = {"Needles": F.foliage_material("WNeedles", ("#18241E", "#2A3A2E"), translucency=0.1),
          "NeedlesCore": F.foliage_material("WNeedlesCore", ("#101814", "#1E2A22"), core=True, translucency=0.0),
          "Bark": F.bark_material("WBark", ("#201A16", "#3A302A"))}
    tcol = F.prototypes([lambda mb: F.chinese_pine(mb, random.Random(1), 14),
                         lambda mb: F.chinese_pine(mb, random.Random(2), 10)], fm, "WPines")
    tp = F.scatter_on(pk, 2500 if pv else 7000, rng, (-4500, 4500), (500, 6000), [(0, 1), (1, 1)],
                      scale=(0.9, 1.5), min_nz=0.55, zmin=80.0)
    F.instance("Pines", tp, tcol)
    hp = MeshBuilder()
    F.chinese_pine(hp, random.Random(9), 13.0, leaves=80, leaf=0.6)
    o = hp.build("HeroPine", fm, auto_smooth_deg=None)
    o.location = (-8.5, 10.0, near.z(-8.5, 10.0) - 0.4)
    o.rotation_euler = (0.25, -0.35, 0.9)
    # ---- the wanderer -----------------------------------------------------------------------
    mats = P.materials(cloth=["#2A2E36", "#4A4038", "#3A3428", "#1C1E22", "#6A5A44", "#8A8070",
                              "#3A2A26", "#2E3A3E", "#5A3A2A", "#C8BCA0", "#6A2A22", "#24303A"])
    f = MeshBuilder()
    P.figure(f, random.Random(7), "sword_ready", "wanderer", cloth=0, cloth2=1, hat="straw",
             weapon="sword_back", cape=True, cape_wind=(1.4, 0.3), jitter=0.0)
    # lantern at the belt (tiny warm accent)
    f.sphere((0.22, -0.05, 0.95), 0.07, "LanternPaper", 10, 7, scale=(1, 1, 1.2))
    wx, wy = -0.3, 7.6
    wo = f.build("Wanderer", mats)
    wo.location = (wx, wy, near.z(wx, wy) - 0.02)
    wo.rotation_euler = (0, 0, math.radians(165))
    S.point((wx + 0.2, wy - 0.3, near.z(wx, wy) + 0.95), 6.0, "#FFA050", 0.05)
    # ---- mist sea ---------------------------------------------------------------------------
    for i, (x, y, z, w, h) in enumerate([(0, 900, 120, 2600, 200), (-900, 1700, 150, 3000, 260),
                                         (900, 2300, 170, 3400, 300), (0, 3200, 220, 5200, 360)]):
        mm = T.mist_material("WMist%d" % i, "#8EA2C8", strength=0.75, density=0.7, seed=float(i * 7),
                             softness=0.5, stretch=4.0)
        T.card("WMist%d" % i, (x, y, z), (w, h), mm)
    # camera low on the path, looking up slightly at the figure against the moon
    cz = near.z(-6.0, -14.0) + 1.5
    cam = L.camera((-6.0, -14.0, cz), (-6.0 + 100 * math.cos(math.radians(80)),
                                        -14.0 + 100 * math.sin(math.radians(80)), cz - 6.1),
                   focal_mm=50.0, dof=(22.5, 4.0))
    return dict(camera=cam, beams=tuple(S.dir_from(*MOON) * 20000.0),
                beams_cfg=dict(ray_length=0.2, strength=0.35, threshold=0.6),
                glow=dict(threshold=0.7, mix=-0.75, size=9),
                grade=dict(saturation=1.0, contrast=1.08, shadows=(-0.005, 0.0, 0.02),
                           highlights=(0.0, 0.005, 0.02), clarity=0.12, vignette=0.32,
                           canvas=0.02, sharpen=0.3))
