"""Event: Festival - a lantern-lit town square at night, fireworks overhead.

Strings of red lanterns criss-cross a paved square framed by two-storey shop houses with glowing
windows; a crowd fills the square towards an opera stage under a hip-gable roof; fireworks
burst gold, red and white in the dark blue sky, their smoke drifting; a warm haze hangs over
the crowd.
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

SPEC = dict(name="Festival", art="Art/Events/Festival.png", master="Events/Festival@2x.png",
            size=(1280, 720), ss=1, spp=32, preview_spp=12, seed=81)


def spark_material(name, color, strength=12.0):
    from ironart.scenes_sky import G, lin4
    mat, nb, created = M.new(name)
    if not created:
        return mat
    b = G(nb.tree)
    em = nb.node("ShaderNodeEmission")
    em.inputs["Color"].default_value = lin4(color)
    tc = nb.node("ShaderNodeTexCoord")
    # fade along the streak (UV v from tail 0 to head 1)
    v = b.sep(tc.outputs["UV"])[1]
    b.link(b.math("MULTIPLY", b.math("POWER", b.clamp01(v), 2.0), strength), em.inputs["Strength"])
    tp = nb.node("ShaderNodeBsdfTransparent")
    mx = nb.node("ShaderNodeAddShader")
    b.link(em.outputs[0], mx.inputs[0])
    b.link(tp.outputs[0], mx.inputs[1])
    nb.output(mx.outputs[0])
    mat["ir_fog"] = 1
    return mat


def firework(mb, center, radius, n, rng, mat, droop=0.25, width=0.25):
    """A chrysanthemum burst: n streak ribbons radiating from ``center`` that droop at the
    tips; UV v runs tail -> head so the shader fades the trails."""
    c = Vector(center)
    for _ in range(n):
        u = rng.uniform(-1, 1)
        a = rng.uniform(0, math.tau)
        s = math.sqrt(1 - u * u)
        d = Vector((s * math.cos(a), s * math.sin(a) * 0.6, u))
        L_ = radius * rng.uniform(0.75, 1.05)
        pts = []
        for k in range(7):
            t = k / 6
            p = c + d * L_ * (0.35 + 0.65 * t) - Vector((0, 0, droop * L_ * t * t))
            pts.append(p)
        # camera-facing ribbon (camera looks +Y): widen along x/z perpendicular to the streak
        for k in range(6):
            p0, p1 = pts[k], pts[k + 1]
            dd = (p1 - p0).normalized()
            side = dd.cross(Vector((0, 1, 0))).normalized() * width * (0.4 + 0.6 * (k + 1) / 6)
            i0 = mb.v(tuple(p0 - side))
            i1 = mb.v(tuple(p0 + side))
            i2 = mb.v(tuple(p1 + side))
            i3 = mb.v(tuple(p1 - side))
            mb.face((i0, i1, i2, i3), mat, [(0, k / 6), (1, k / 6), (1, (k + 1) / 6), (0, (k + 1) / 6)])
        mb.sphere(tuple(pts[-1]), width * 1.6, mat + "Head", 6, 4)


def build(r):
    import bpy
    pv = r["preview"]
    rng = random.Random(81)
    S.build(dict(
        stops=[(0.0, "#3A3050"), (0.05, "#2A2A4E"), (0.2, "#18203E"), (0.5, "#0E142C"),
               (1.0, "#080A1A")],
        strength=0.6,
        stars=dict(density=260.0, size=0.04, strength=2.0, power=10.0),
        clouds=[dict(height=1800, scale=2400, coverage=0.3, softness=0.35, lit="#4A3A52",
                     shadow="#1A1828", rim=0.0, opacity=0.6, stretch=(1, 0.5), fade=0.1, seed=3.0)],
        light=dict(strength=0.35, tint="#5A68A0"),
        fog=dict(haze=0.0025, haze_falloff=0.02, haze_max=0.6, haze_zmax=0.1, haze_tint="#806878",
                 mist=0.01, mist_falloff=0.15, mist_h0=0.0, mist_max=0.4, mist_color="#6A3A30",
                 mist_strength=1.0),
    ))
    S.sun(120, 30, energy=0.08, color="#8090D0", angle_deg=5.0, name="SkyFill")
    wk = A.wk_materials()
    pm = P.materials(cloth=["#8A2A20", "#2E3E5E", "#C8963A", "#3A3A30", "#6A4A2A", "#D8CCB0",
                            "#5A2E44", "#2E5A58", "#B8402A", "#E8DCC0", "#C83A28", "#24344A"])
    mats = dict(wk)
    mats.update(pm)
    mats["Lantern"] = P.lantern_material("FLantern", "#D8301A", strength=3.2)
    mats["LanternGold"] = P.lantern_material("FLanternGold", "#E8902A", strength=3.0)
    mats["Window"] = A.glow_material("FWindow", "#FF9A48", strength=1.3)
    mats["Rope"] = M.principled("FRope", "#2A2018", 0.9)
    city = MeshBuilder()
    # paved square
    city.box((0, 40, -0.4), (90, 120, 0.4), "W_Paving")
    # shop houses on both sides (two storeys) + facing the stage
    hs_spec = []
    for side in (-1, 1):
        for k in range(8):
            y = -6 + k * 12.5
            w = rng.uniform(10.5, 12.0)
            s0 = city.n
            WK.house(city, (0, 0, 0), WK.HouseSpec(w=w, d=8.0, h=6.4, roof=WK.RoofSpec(
                style="gable", overhang=0.9, lift=0.35, flare=0.12, thick=0.2, mat="W_TileDark",
                chiwen=False, ridge_ends="curl")))
            # pent eave between the storeys + glowing shop front and upper windows
            WK.roof(city, (0, -3.2, 3.4), w - 0.4, 1.6, 0.5, WK.RoofSpec(style="gable", overhang=0.5,
                                                                         lift=0.1, flare=0.05, thick=0.12,
                                                                         mat="W_TileDark", chiwen=False,
                                                                         ridge_ends="plain"))
            for kx in (-1, 0, 1):
                city.box((kx * w * 0.3, -3.68, 4.4), (w * 0.2, 0.05, 1.5), "Window")
            city.box((0, -3.68, 0.6), (w * 0.5, 0.05, 2.3), "Window")
            city.transform(s0, Matrix.Translation((side * 22.0, y, 0)) @ Matrix.Rotation(-side * math.pi / 2, 4, "Z"))
    # opera stage at the far end
    WK.hall(city, (0, 100, 0), WK.HallSpec(bays=(5, 3), bay=4.2, col_h=5.0, plat_h=1.6, front="open",
                                            double=False, roof=WK.RoofSpec(style="hip_gable", beasts=3,
                                                                           ridge_ends="curl")))
    city.box((0, 103, 1.6), (18, 0.4, 5.0), "Window")
    # lantern strings criss-crossing above the square
    for k in range(9):
        y0 = 4 + k * 11.0
        A.lantern_string(city, (-17.5, y0, 8.6), (17.5, y0 + rng.uniform(-6, 6), 8.6), n=11, sag=1.6,
                         mat="Lantern" if k % 3 else "LanternGold", rope="Rope", size=0.26)
    for k in range(4):
        A.lantern_string(city, (-17.5, -4 + k * 26, 8.0), (17.5, 20 + k * 26, 8.0), n=13, sag=1.2,
                         mat="Lantern", rope="Rope", size=0.22)
    # lantern poles in the crowd
    for k in range(6):
        x = rng.choice([-1, 1]) * rng.uniform(6, 14)
        y = rng.uniform(10, 85)
        city.cylinder((x, y, 0), (x, y, 5.5), 0.08, 0.06, "W_WoodDark", 6)
        city.sphere((x, y, 5.9), 0.38, "Lantern", 12, 8, scale=(1, 1, 1.2))
    A.wk_build(city, "Town", mats)
    # ---- crowd (instanced) -----------------------------------------------------------------------
    specs = []
    for i in range(14):
        pose = ["stand", "cheer", "walk", "stand_hands", "point", "stand", "cheer"][i % 7]
        outfit = ["robe", "peasant", "lady", "noble", "robe", "peasant", "lady"][i % 7]
        hat = [None, "topknot", None, "guan", "band", None, None][i % 7]
        w = "lantern" if i in (3, 9) else None
        specs.append((pose, outfit, hat, i % 12, (i * 5 + 3) % 12, w))
    builders = [lambda mb, s=s, i=i: P.figure(mb, random.Random(900 + i), s[0], s[1], cloth=s[3], cloth2=s[4],
                                              hat=s[2], weapon=s[5], hair_long=s[1] == "lady", jitter=8.0)
                for i, s in enumerate(specs)]
    pcol = F.prototypes(builders, mats, "FCrowd")
    pts = []
    for _ in range(420 if pv else 900):
        x = rng.uniform(-15, 15)
        y = rng.uniform(4, 92)
        if abs(x) < 2.0 and y < 30:
            continue
        rz = math.pi + math.atan2(-x * 0.2, 1.0) + rng.uniform(-0.6, 0.6)
        pts.append((x, y, 0.0, rz, rng.uniform(0.9, 1.08), rng.randrange(len(specs))))
    F.instance("Crowd", pts, pcol)
    # a few big crowd figures in the foreground (backs to camera)
    fg = MeshBuilder()
    for i, (x, y, pose, outfit, cl) in enumerate([(-3.5, 2.0, "point", "noble", 0), (2.6, 3.2, "cheer", "lady", 8),
                                                   (5.0, 1.0, "stand", "robe", 1), (-6.5, 4.5, "stand_hands", "peasant", 4)]):
        f = MeshBuilder()
        P.figure(f, random.Random(950 + i), pose, outfit, cloth=cl, cloth2=9, hat=None if outfit == "lady" else "topknot",
                 hair_long=outfit == "lady")
        fg.extend(f, Matrix.Translation((x, y, 0)) @ Matrix.Rotation(math.pi + rng.uniform(-0.3, 0.3), 4, "Z"))
    fg.build("Foreground", mats)
    # ---- fireworks ----------------------------------------------------------------------------
    fw = MeshBuilder()
    fmats = {}
    for i, (c, col, rad, n) in enumerate([((-20, 190, 70), "#FFC860", 26, 160), ((28, 230, 88), "#FF5A3A", 30, 170),
                                          ((4, 260, 58), "#F0F0FF", 18, 120), ((52, 210, 50), "#FFD27A", 16, 90),
                                          ((-48, 240, 92), "#FF8A4A", 22, 130)]):
        nm = "Spark%d" % i
        fmats[nm] = spark_material("FSpark%d" % i, col, strength=14.0)
        fmats[nm + "Head"] = P.flame_material("FHead%d" % i, col, strength=30.0)
        firework(fw, c, rad, n if not pv else n // 2, random.Random(i), nm, droop=0.3, width=0.22)
    fo = fw.build("Fireworks", fmats, auto_smooth_deg=None)
    fo.visible_shadow = False
    # firework glow lights + smoke
    for (c, col) in (((-20, 190, 70), "#FFC860"), ((28, 230, 88), "#FF5A3A"), ((-48, 240, 92), "#FF8A4A")):
        S.point(c, 2.5e5, col, 6.0, shadow=False)
    for i in range(5):
        sm = T.mist_material("FSmoke%d" % i, "#5A4A58", strength=0.8, density=0.35, seed=float(i),
                             softness=0.5, stretch=2.0)
        T.card("FSmoke%d" % i, (rng.uniform(-40, 50), rng.uniform(170, 260), rng.uniform(50, 90)),
               (rng.uniform(60, 120), rng.uniform(30, 50)), sm)
    # warm fill from the lanterns over the crowd (cheap): area lights under the strings
    for k in range(5):
        S.area((0, 6 + k * 20, 7.5), (0, 6 + k * 20, 0), power=3500.0, size=14.0, color="#FF8A50", shadow=False)
    cam = L.camera((0.5, -16.0, 5.2), (0.0, 120.0, 22.0), focal_mm=26.0, dof=(28.0, 6.0))
    return dict(camera=cam, beams=None,
                glow=dict(threshold=0.8, mix=-0.62, size=9),
                grade=dict(saturation=1.08, contrast=1.06, shadows=(-0.005, 0.0, 0.02),
                           highlights=(0.03, 0.01, -0.01), clarity=0.12, vignette=0.3,
                           canvas=0.012, sharpen=0.3))
