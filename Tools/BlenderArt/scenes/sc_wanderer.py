"""Event: Wanderer - a lone swordsman on a cliff path under the full moon.

The wanderer (straw hat, cloak stirring in the wind, sword across the back, a small lantern at
his belt) stands at the tip of a rock spur that runs out into the void, beside an enormous full
moon with a silver halo; below, a sea of moonlit mist fills the valleys between dark peaks;
cold blue night, the only warm note is his lantern.
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
            size=(1280, 720), ss=1, spp=28, preview_spp=12, seed=41)

MOON = (79.0, 3.6)


def build(r):
    import bpy
    pv = r["preview"]
    rng = random.Random(41)
    S.build(dict(
        stops=[(0.0, "#3E4E72"), (0.06, "#2C3A60"), (0.2, "#1C284A"), (0.5, "#101830"),
               (1.0, "#080C1E")],
        strength=0.34,
        glows=[dict(dir=MOON, color="#B8CCF0", lobes=[(6, 0.05), (60, 0.3), (1600, 3.0)],
                    horizon=(0.2, 0.08, 2.0))],
        discs=[dict(dir=MOON, radius_deg=2.1, color="#F2F0E6", strength=1.5, texture=0.6, edge=0.03)],
        stars=dict(density=320.0, size=0.05, strength=9.0, power=8.0, color="#E0E8FF", milky=0.05),
        clouds=[dict(height=2400, scale=3400, coverage=0.3, softness=0.3, lit="#6E80A6",
                     shadow="#1C2440", rim_color="#E8F0FF", rim=4.0, rim_power=30.0, opacity=0.85,
                     stretch=(1.0, 0.4), fade=0.12, shade=6.0, seed=3.0, haze=0.6)],
        light=dict(strength=0.6, tint="#90A8D8"),
        fog=dict(haze=5.0e-5, haze_falloff=0.0009, haze_max=0.85, haze_zmax=0.1,
                 mist=0.0035, mist_falloff=0.012, mist_h0=0.0, mist_max=0.9,
                 mist_color="#5E7098", mist_strength=1.0),
    ))
    S.sun(MOON[0], MOON[1] + 3, energy=0.9, color="#A8C0F0", angle_deg=1.5, name="Moon")
    # ---- terrain: the cliff path (near), dark peaks rising from the mist (far) ------------
    def near_h(X, Y):
        # a narrow rock spur running out into the void from the right-back to its tip at
        # (0, 20) (where the wanderer stands, z ~404.6) and the rock the viewer stands on at
        # (-6, 0); everything else falls away in cliffs to the mist far below
        ax, ay, bx, by = 0.0, 20.0, 46.0, 52.0
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = np.clip(((X - ax) * dx + (Y - ay) * dy) / L2, 0.0, 1.0)
        d = np.hypot(X - (ax + t * dx), Y - (ay + t * dy))
        rough = T.ridged2(X, Y, 3.0, 4, seed=5)
        top = 404.6 + 7.0 * t + 0.4 * (T.fbm2(X, Y, 4.0, 3, seed=2) - 0.5)
        spur = top - 1.4 * np.clip(d - 2.2, 0, None) ** 2 - 2.0 * (rough - 0.5) * T.smoothstep(2.0, 4.0, d)
        rc = np.hypot(X + 6.0, Y + 1.0)
        cam_rock = 404.2 + 0.3 * (T.fbm2(X, Y, 3.0, 3, seed=3) - 0.5) - 1.2 * np.clip(rc - 5.5, 0, None) ** 2
        base = 330.0 + 30.0 * T.ridged2(X, Y, 25.0, 4, seed=4) - 0.4 * np.hypot(X, Y)
        return np.maximum(np.maximum(spur, cam_rock), base)
    near = T.field_from(near_h, -40, 80, -20, 80, 0.25 if pv else 0.15)
    rm = T.rock_material("WRock", ("#3A3C44", "#5E606A"), scale=0.12, strata=0.4, moss="#3A4638",
                         moss_amt=0.5, vertical=True)
    near.build("Cliff", rm)

    def peaks(X, Y):
        r_ = T.ridged2(X, Y, 420.0, 7, sharp=2.2, seed=11, warp=260.0)
        bump = 0.25 + 0.0 * X
        for (px, py, w, k) in ((-700, 1500, 300, 1.2), (1000, 1600, 260, 1.4), (1300, 900, 240, 0.9),
                               (-1500, 2600, 500, 1.1), (1900, 3000, 600, 1.0), (0, 3500, 700, 0.8)):
            bump = bump + k * np.exp(-(((X - px) / w) ** 2 + ((Y - py) / w) ** 2))
        return r_ ** 1.4 * 520.0 * bump - 60.0
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
    # ---- the wanderer -----------------------------------------------------------------------
    mats = P.materials(cloth=["#2A2E36", "#4A4038", "#3A3428", "#1C1E22", "#6A5A44", "#8A8070",
                              "#3A2A26", "#2E3A3E", "#5A3A2A", "#C8BCA0", "#6A2A22", "#24303A"])
    f = MeshBuilder()
    P.figure(f, random.Random(7), "sword_ready", "wanderer", cloth=0, cloth2=1, hat="straw",
             weapon="sword_back", cape=True, cape_wind=(1.4, 0.3), jitter=0.0)
    # lantern at the belt (tiny warm accent)
    f.sphere((0.22, -0.05, 0.95), 0.07, "LanternPaper", 10, 7, scale=(1, 1, 1.2))
    wx, wy = 0.0, 20.0
    wo = f.build("Wanderer", mats)
    wo.location = (wx, wy, near.z(wx, wy) - 0.02)
    wo.rotation_euler = (0, 0, math.radians(165))
    S.point((wx + 0.2, wy - 0.3, near.z(wx, wy) + 0.95), 6.0, "#FFA050", 0.05)
    # ---- mist sea ---------------------------------------------------------------------------
    for i, (x, y, z, w, h) in enumerate([(0, 500, 345, 2400, 110), (-700, 1300, 355, 3200, 140),
                                         (900, 1800, 365, 3600, 160), (0, 2800, 380, 6000, 200),
                                         (400, 260, 330, 1200, 90)]):
        mm = T.mist_material("WMist%d" % i, "#7286B0", strength=0.62, density=0.75, seed=float(i * 7),
                             softness=0.45, stretch=4.0)
        T.card("WMist%d" % i, (x, y, z), (w, h), mm)
    mf = T.mist_material("WMistSheet", "#6C80AA", strength=0.55, density=0.85, seed=3.0, softness=0.5,
                         stretch=1.0, edge=0.12)
    T.flat_card("WMistSheet", (0.0, 2500.0, 340.0), (9000.0, 5000.0), mf)
    # camera low on the path, looking up slightly at the figure against the moon
    cz = near.z(-6.0, -1.0) + 1.7
    cam = L.camera((-6.0, -1.0, cz), (-6.0 + 100 * math.cos(math.radians(80)),
                                      -1.0 + 100 * math.sin(math.radians(80)), cz - 100 * math.tan(math.radians(1.5))),
                   focal_mm=50.0, dof=(21.0, 5.6))
    return dict(camera=cam, beams=tuple(S.dir_from(*MOON) * 20000.0),
                beams_cfg=dict(ray_length=0.2, strength=0.35, threshold=0.6),
                glow=dict(threshold=0.7, mix=-0.75, size=9),
                grade=dict(saturation=1.0, contrast=1.08, shadows=(-0.005, 0.0, 0.02),
                           highlights=(0.0, 0.005, 0.02), clarity=0.12, vignette=0.32,
                           canvas=0.012, sharpen=0.3))
