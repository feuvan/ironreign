"""Event: Plague - a fog-shrouded village of closed doors in cold light.

A muddy lane between shuttered houses fades into thick blue-grey fog; doors are barred, white
mourning cloth and yellow paper charms hang on them; a covered handcart stands abandoned; a
lone hooded figure with a lantern (the only warm light) walks away into the fog; a dead tree
with crows; the sun is a pale disc in the murk.
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

SPEC = dict(name="Plague", art="Art/Events/Plague.png", master="Events/Plague@2x.png",
            size=(1280, 720), ss=1, spp=28, preview_spp=12, seed=91)

SUN = (100.0, 16.0)


def mud_material():
    from ironart.scenes_sky import G, lin4
    from ironart.scenes_terrain import _fin, noise
    mat, nb, created = M.new("Mud")
    if not created:
        return mat
    b = G(nb.tree)
    P_ = nb.node("ShaderNodeNewGeometry").outputs["Position"]
    n1 = noise(nb, P_, 0.3, 5, 0.6)
    n2 = noise(nb, P_, 3.0, 3, 0.6)
    col = b.mix(lin4("#3A3630"), lin4("#5A5244"), b.smooth(n1, 0.3, 0.7))
    wet = b.smooth(n1, 0.55, 0.6)
    col = b.mix(col, b.cmul(col, 0.55), wet)
    rough = b.maprange(wet, 0, 1, 0.85, 0.08)
    p = b.principled(Base_Color=col, Roughness=rough, Specular_IOR_Level=0.45,
                     Normal=b.bump(n2, 0.4, 0.05))
    return _fin(mat, nb, p.outputs[0])


def build(r):
    import bpy
    pv = r["preview"]
    rng = random.Random(91)
    S.build(dict(
        stops=[(0.0, "#9AA4A4"), (0.1, "#8C9898"), (0.3, "#748286"), (1.0, "#4E5C64")],
        strength=0.9,
        glows=[dict(dir=SUN, color="#C8D0C8", lobes=[(8, 0.25), (300, 1.0)])],
        discs=[dict(dir=SUN, radius_deg=1.4, color="#E8ECE0", strength=2.2, edge=0.35)],
        light=dict(strength=0.9, tint="#B8C8CC"),
        fog=dict(haze=0.011, haze_falloff=0.03, haze_max=0.96, haze_zmax=0.12, haze_tint="#9AA8A8",
                 mist=0.012, mist_falloff=0.35, mist_h0=0.0, mist_max=0.5, mist_color="#7E8E90"),
    ))
    S.sun(SUN[0], SUN[1], energy=0.7, color="#C8D4D0", angle_deg=8.0)
    # lane
    def hfn(X, Y):
        return 0.25 * T.fbm2(X, Y, 6.0, 4, seed=1) + T.smoothstep(4.0, 9.0, np.abs(X - 0.6 * np.sin(Y / 14.0))) * 0.35
    g = T.field_from(hfn, -30, 30, -10, 140, 0.25 if pv else 0.15)
    g.build("Lane", mud_material())
    am = A.materials(thatch="#6E6650", plaster="#A8A498", glaze=0.0, roof_rough=0.8)
    wk = A.wk_materials()
    pm = P.materials(cloth=["#3A3E40", "#5A564C", "#6A6458", "#2A2C2E", "#4A4038", "#B8B4A8",
                            "#3A3430", "#40484A", "#5A4A3E", "#D8D4C8", "#6A3A2E", "#2E3A40"])
    mats = dict(am)
    mats.update(wk)
    mats.update(pm)
    mats["MourningCloth"] = P.cloth_material("PMourn", "#E2E0D8", sheen=0.2)
    mats["Charm"] = M.principled("PCharm", "#C8A23A", 0.7)
    mats["Crow"] = M.principled("PCrow", "#0E0E10", 0.5)
    vil = MeshBuilder()
    for side in (-1, 1):
        y = -4.0
        k = 0
        while y < 130:
            w = rng.uniform(1.05, 1.35)
            ox = side * (6.0 + rng.uniform(0, 1.2) + 0.6 * math.sin(y / 14.0))
            builder = A.thatched_house(random.Random(k * 2 + (side > 0)), 1.0, foundation=0.3) if rng.random() < 0.55 \
                else A.house(random.Random(k * 3 + (side > 0)), "gable", 1.0, foundation=0.3)
            hb = A.scaled(builder, 7.0, (ox + side * 3.2, y + 4.0, hfn(np.array([ox]), np.array([y]))[0] - 0.2),
                          rot_z=-side * math.pi / 2 + rng.uniform(-0.06, 0.06))
            vil.extend(hb)
            # barred door: planks across + mourning cloth / charms facing the lane
            dx = ox + side * (-0.25 + 0.0)
            dz = hfn(np.array([ox]), np.array([y + 4.0]))[0]
            if rng.random() < 0.7:
                for j in range(2):
                    vil.box((ox - side * 0.12, y + 3.2 + rng.uniform(-0.3, 0.3), dz + 0.9 + j * 0.7), (0.06, 2.0, 0.16),
                            "W_WoodDark", rot_z=rng.uniform(-0.25, 0.25))
            if rng.random() < 0.5:
                vil.grid(lambda u, v, ox=ox, y=y, dz=dz: (ox - side * 0.2, y + 2.6 + u * 1.2,
                                                         dz + 2.4 - v * 1.6 - 0.1 * math.sin(u * 3.1)),
                         4, 4, "MourningCloth", smooth=True)
            for j in range(rng.randint(0, 2)):
                vil.box((ox - side * 0.16, y + 2.9 + j * 0.9, dz + 1.3), (0.02, 0.18, 0.55), "Charm")
            y += w * 7.0 + rng.uniform(1.5, 4.0)
            k += 1
    # abandoned handcart with a straw-covered load
    s0 = vil.n
    vil.box((0, 0, 0.55), (1.2, 2.2, 0.1), "W_Wood")
    for sx in (-1, 1):
        s1 = vil.n
        vil.lathe([(0.0, -0.05), (0.5, -0.05), (0.55, 0.0), (0.5, 0.05), (0.0, 0.05)], "W_WoodDark", 16)
        vil.transform(s1, Matrix.Translation((sx * 0.68, 0.3, 0.5)) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
        vil.cylinder((sx * 0.4, -1.1, 0.6), (sx * 0.45, -2.4, 0.1), 0.04, 0.04, "W_WoodDark", 5)
    vil.sphere((0, 0.1, 0.75), 0.75, "Thatch", 12, 6, scale=(0.75, 1.3, 0.45))
    vil.transform(s0, Matrix.Translation((-2.6, 14.0, hfn(np.array([-2.6]), np.array([14.0]))[0])) @ Matrix.Rotation(0.5, 4, "Z"))
    A.wk_build(vil, "Village", mats)
    # the lone lantern bearer walking away
    f = MeshBuilder()
    sk = P.figure(f, random.Random(5), "walk", "robe", cloth=0, cloth2=5, hat="hood", weapon="lantern",
                  cape=True, cape_wind=(0.1, 0.0))
    fx, fy = 0.6, 13.0
    m = Matrix.Translation((fx, fy, hfn(np.array([fx]), np.array([fy]))[0])) @ Matrix.Rotation(math.pi + 0.05, 4, "Z")
    o = f.build("Bearer", mats)
    o.matrix_world = m
    lp = m @ (sk.arm[-1]["hand"] + Vector((0, 0, -0.25)))
    S.point(tuple(lp), 130.0, "#FFA048", 0.08)
    # dead tree with crows
    fm = {"BarkDead": F.bark_material("PBark", ("#2A2622", "#4A443C"))}
    t = MeshBuilder()
    F.dead_tree(t, random.Random(3), 11.0, depth=5)
    for k in range(5):
        a = rng.uniform(0, math.tau)
        c = (math.cos(a) * rng.uniform(1.2, 2.8), math.sin(a) * rng.uniform(1.2, 2.8), rng.uniform(6.5, 9.5))
        t.sphere(c, 0.16, "Crow", 8, 5, scale=(0.7, 1.3, 0.8))
        t.sphere((c[0], c[1] - 0.2, c[2] + 0.12), 0.08, "Crow", 6, 4)
    fm["Crow"] = mats["Crow"]
    to = t.build("DeadTree", fm, auto_smooth_deg=None)
    to.location = (5.0, 9.0, hfn(np.array([5.0]), np.array([9.0]))[0] - 0.2)
    # fog banks drifting across the lane
    for i in range(9):
        mm = T.mist_material("PMist%d" % i, "#8E9C9E", strength=0.95, density=0.55, seed=float(i * 4),
                             softness=0.6, stretch=2.5)
        T.card("PMist%d" % i, (rng.uniform(-6, 6), 22 + i * 9.0, rng.uniform(0.8, 2.5)),
               (rng.uniform(14, 26), rng.uniform(2.5, 5.0)), mm, rot_z=rng.uniform(-0.2, 0.2))
    cam = L.camera((-1.2, -6.5, 1.35), (1.0, 60.0, 1.6), focal_mm=30.0, dof=(24.0, 5.6))
    return dict(camera=cam, beams=tuple(S.dir_from(*SUN) * 5000.0),
                beams_cfg=dict(ray_length=0.15, strength=0.15, threshold=0.6),
                glow=dict(threshold=0.9, mix=-0.8, size=8),
                grade=dict(saturation=0.85, contrast=1.16, pivot=0.42, shadows=(-0.012, 0.004, 0.014),
                           highlights=(-0.01, 0.005, 0.008), clarity=0.1, vignette=0.32,
                           canvas=0.012, sharpen=0.3))
