"""Event: Omen - a blood-red comet over the dark capital.

From high above the palace the viewer looks out over the night-time capital: the gilt roofs of a
great gate tower in the foreground and the halls of the palace axis stepping away catch the red
light, the city spreads to the far walls with a few lit windows and lanterns; low over the
mountains a great red comet rises, its tails sweeping up across a starry sky and staining thin
clouds crimson.
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
from ironart import world_kit as WK
from ironart.geometry import MeshBuilder

SPEC = dict(name="Omen", art="Art/Events/Omen.png", master="Events/Omen@2x.png",
            size=(1280, 720), ss=1, spp=28, preview_spp=12, seed=111)

COMET = (110.0, 8.0)
CAM = (0.0, -10.0, 36.0)


def lattice_glow(name, color="#FF9A48", strength=1.2, light=0.12):
    """Lit paper lattice doors / windows: emission between dark lattice bars (MetreUV)."""
    from ironart.scenes_sky import G, lin4
    from ironart.scenes_sky import fog_node
    mat, nb, created = M.new(name)
    if not created:
        return mat
    b = G(nb.tree)
    u, v, _ = b.sep(nb.node("ShaderNodeTexCoord").outputs["UV"])
    def bars(x, k):
        f = b.math("FRACT", b.math("MULTIPLY", x, k))
        return b.math("ABSOLUTE", b.math("SUBTRACT", f, 0.5))
    g = b.math("MAXIMUM", bars(u, 4.0), bars(v, 4.0))
    paper = b.smooth(g, 0.42, 0.36)
    p = b.principled(Base_Color=lin4("#3A2214"), Roughness=0.7)
    em = nb.node("ShaderNodeEmission")
    em.inputs["Color"].default_value = lin4(color)
    lp = nb.node("ShaderNodeLightPath")
    k = b.math("ADD", light, b.math("MULTIPLY", lp.outputs["Is Camera Ray"], 1.0 - light))
    b.link(b.math("MULTIPLY", b.math("MULTIPLY", paper, strength), k), em.inputs["Strength"])
    ad = nb.node("ShaderNodeAddShader")
    b.link(p.outputs[0], ad.inputs[0])
    b.link(em.outputs[0], ad.inputs[1])
    nb.output(fog_node(nb, ad.outputs[0]))
    mat["ir_fog"] = 1
    return mat


def build(r):
    import bpy
    pv = r["preview"]
    rng = random.Random(111)
    S.build(dict(
        stops=[(0.0, "#4A2830"), (0.04, "#33202E"), (0.15, "#1C1A30"), (0.45, "#0C0E22"),
               (1.0, "#060814")],
        strength=0.7,
        glows=[dict(dir=COMET, color="#FF4A2A", lobes=[(10, 0.06), (80, 0.16)], horizon=(0.22, 0.05, 2.0))],
        stars=dict(density=300.0, size=0.05, strength=5.0, power=9.0, color="#E8E4FF", milky=0.03),
        comet=dict(head=COMET, tail_angle=30.0, length_deg=48.0, width_deg=0.12, fan=0.075,
                   tails=[(0.0, 1.0, 1.0), (0.05, 0.45, 2.3)], tail_color="#FF3A1E",
                   tail_strength=1.5, head_color="#FFE4D0", head_deg=0.17, head_strength=30.0,
                   coma_strength=0.7),
        clouds=[dict(height=2600, scale=3200, coverage=0.2, softness=0.35, lit="#3A2232",
                     shadow="#1A1420", rim_color="#FF5A3A", rim=0.4, rim_power=24.0, opacity=0.35,
                     stretch=(1.0, 0.45), fade=0.12, shade=6.0, seed=17.0, haze=0.5)],
        light=dict(strength=0.6, tint="#A06070"),
        fog=dict(haze=2.6e-4, haze_falloff=0.003, haze_max=0.85, haze_zmax=0.1, haze_tint="#C8A0A8",
                 mist=0.003, mist_falloff=0.05, mist_h0=0.0, mist_max=0.4, mist_color="#3A2430"),
    ))
    S.sun(COMET[0], COMET[1] + 4.0, energy=0.75, color="#FF5A3A", angle_deg=4.0, name="CometLight")
    S.sun(250.0, 40.0, energy=0.1, color="#4A5AA0", angle_deg=20.0, name="NightFill", shadow=False)
    def hfn(X, Y):
        return 0.5 * T.fbm2(X, Y, 80.0, 3, seed=1) + T.smoothstep(1900.0, 3000.0, Y) * 300.0 * T.ridged2(X, Y, 700.0, 5, seed=2)
    g = T.field_from(hfn, -2600, 2600, -60, 5200, 6.0 if pv else 4.0)
    gm = T.terrain_material("OmenGround", grass=("#2A2E22", "#3A3A2A"), dirt="#3A3228",
                            rock=("#34302E", "#4A4440"), grass_scale=0.01)
    g.build("Ground", gm)
    wk = A.wk_materials()
    pm = P.materials(cloth=["#5A1E1A", "#1E2A44", "#3A2A1E", "#1A1A1C", "#5A4430", "#B8AC90",
                            "#3A2030", "#1E3434", "#4A3426", "#C8BC9C", "#6A2A1E", "#1A2434"])
    mats = dict(wk)
    mats.update(pm)
    mats["Window"] = A.glow_material("OWindow", "#FF9040", strength=1.4)
    mats["W_Lattice"] = lattice_glow("OLattice", strength=0.5)
    city = MeshBuilder()
    z_ = lambda x, y: float(hfn(np.array([float(x)]), np.array([float(y)]))[0])
    # ---- the palace gate tower in the left foreground --------------------------------------------
    s0 = city.n
    top = WK.gate_base(city, 64, 26, 13, 7, 9, n_arches=3, spacing=16, skirt=3.0)
    city.transform(s0, WK.T(-62.0, 70.0, z_(-62, 70), -0.32))
    WK.hall(city, (-62.0, 70.0, z_(-62, 70) + top), WK.HallSpec(
        bays=(9, 3), bay=5.2, col_h=6.2, plat_h=0.0, steps=False, double=True, upper_h=4.0,
        roof=WK.RoofSpec(style="hip", mat="W_TileGold", ridge_mat="W_RidgeGold", beasts=7)), rz=-0.32)
    # palace walls running from the gate tower
    for k in range(-6, 14):
        s0 = city.n
        WK.wall_segment(city, 20.5, 10.0, 6.0, skirt=1.5)
        x = -62.0 + math.cos(-0.32) * (k * 20.0 + (44.0 if k >= 0 else -44.0 + 20.0))
        y = 70.0 + math.sin(-0.32) * (k * 20.0 + (44.0 if k >= 0 else -44.0 + 20.0))
        city.transform(s0, WK.T(x, y, z_(x, y), -0.32))
    # ---- the palace axis: halls stepping away, right of centre -----------------------------------
    for k, (y, bays, dbl) in enumerate(((150, (9, 5), True), (280, (7, 3), False), (410, (11, 5), True),
                                        (560, (7, 3), False), (700, (5, 3), False))):
        x = 60.0 + (y - 150) * 0.02
        WK.hall(city, (x, y, z_(x, y)), WK.HallSpec(
            bays=bays, bay=5.0, col_h=6.0, plat_h=2.0, tiers=2 if dbl else 1, balustrade=dbl,
            double=dbl, upper_h=3.4, roof=WK.RoofSpec(style="hip" if dbl else "hip_gable",
                                                      mat="W_TileGold", ridge_mat="W_RidgeGold",
                                                      beasts=5)))
        for sx in (-1, 1):
            WK.hall(city, (x + sx * 52, y + 20, z_(x + sx * 52, y + 20)), WK.HallSpec(
                bays=(5, 3), bay=4.4, col_h=5.0, plat_h=1.2, roof=WK.RoofSpec(mat="W_TileGold",
                                                                               ridge_mat="W_RidgeGold")),
                    rz=-sx * math.pi / 2)
    for sx in (-1, 1):
        for k in range(32):
            y = 110 + k * 20
            x = 60.0 + sx * 92.0
            s0 = city.n
            WK.wall_segment(city, 20.5, 7.0, 4.0, skirt=1.0, earth=True)
            city.transform(s0, WK.T(x, y, z_(x, y), math.pi / 2))
    WK.pagoda(city, (-230, 640, z_(-230, 640)), tiers=13, R=5.5, base_h=7.0, tier_h=3.6)
    WK.pagoda(city, (330, 1150, z_(330, 1150)), tiers=9, R=4.6, base_h=6.0, tier_h=3.2)
    # ---- the city: houses (instanced), a third with lit windows ---------------------------------
    hb = []
    for i in range(6):
        rr_ = random.Random(300 + i)
        hb.append(lambda mb, rr_=rr_, i=i: (WK.house(mb, (0, 0, 0), WK.HouseSpec(
            w=rr_.uniform(9, 13), d=rr_.uniform(6, 8), h=rr_.uniform(3.4, 4.2),
            roof=WK.RoofSpec(style="gable", overhang=0.75, lift=0.25, flare=0.1, thick=0.2,
                             mat="W_TileDark", chiwen=False, ridge_ends="curl"))),
            [mb.box((sx * 2.2, -3.25, 1.0), (1.2, 0.08, 1.1), "Window") for sx in (-1, 1)] if i % 2 == 0 else None))
    hcol = A.wk_prototypes(hb, mats, "OHouses")
    hp = []
    for _ in range(3000 if pv else 9000):
        x = rng.uniform(-1300, 1300)
        y = rng.uniform(60, 1660)
        if -10 < x < 140 and y < 780:
            continue
        if abs(y - 70.0 - (x + 62.0) * math.tan(-0.32)) < 40 and x < 40:
            continue
        hp.append((x, y, z_(x, y) - 0.4,
                   rng.choice([0, math.pi, math.pi / 2]) + rng.uniform(-0.05, 0.05), rng.uniform(0.9, 1.1), rng.randrange(6)))
    F.instance("OHouses", hp, hcol)
    # ---- the outer city wall far away, with gate towers -------------------------------------------
    for k in range(-34, 35):
        s0 = city.n
        WK.wall_segment(city, 50.5, 12.0, 10.0, skirt=2.0)
        city.transform(s0, WK.T(k * 50.0, 1700.0, z_(k * 50.0, 1700.0), 0.0))
    for x in (-700.0, 0.0, 700.0):
        s0 = city.n
        top2 = WK.gate_base(city, 40, 22, 14, 7, 9)
        city.transform(s0, WK.T(x, 1700.0, z_(x, 1700.0), 0.0))
        WK.hall(city, (x, 1700.0, z_(x, 1700.0) + top2), WK.HallSpec(bays=(5, 2), double=True, plat_h=0.0, steps=False))
    A.wk_build(city, "Capital", mats)
    # ---- lanterns: a few warm points in the streets and on the gate ------------------------------
    lan = MeshBuilder()
    for _ in range(160 if pv else 320):
        x = rng.uniform(-900, 900)
        y = rng.uniform(100, 1500)
        lan.sphere((x, y, z_(x, y) + 3.0), 0.5, "Lantern", 6, 4)
    for k in range(-4, 5):
        x = -62.0 + math.cos(-0.32) * k * 6.5
        y = 70.0 + math.sin(-0.32) * k * 6.5 - 14.0
        lan.sphere((x, y, z_(-62, 70) + top + 4.5), 0.35, "Lantern", 8, 5)
    lan.build("Lanterns", {"Lantern": P.lantern_material("OLantern", "#FF8A3A", 6.0, light=0.0)})
    S.point((-62.0, 50.0, top + 6.0), 400.0, "#FF8A40", 2.0, name="GateGlow")
    tgt = (CAM[0] + math.cos(math.radians(92.0)) * 400.0, CAM[1] + 400.0, CAM[2] + math.tan(math.radians(2.0)) * 400.0)
    cam = L.camera(CAM, tgt, focal_mm=24.0)
    return dict(camera=cam, beams=None,
                glow=dict(threshold=0.7, mix=-0.7, size=9),
                grade=dict(saturation=1.06, contrast=1.1, shadows=(0.0, -0.004, 0.02),
                           highlights=(0.03, 0.0, -0.01), clarity=0.14, vignette=0.32,
                           canvas=0.012, sharpen=0.3))
