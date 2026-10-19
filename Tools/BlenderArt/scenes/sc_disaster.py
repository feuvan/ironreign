"""Event: Disaster - a locust swarm over withered fields.

A wide, parched plain under a sick ochre sky: cracked earth, millet stalks bent and brown, a bare
tree, a farmhouse with its gate open; a farmer kneels in despair in the foreground while his wife
looks up.  The swarm pours down from the upper right as a dark cloud of countless painted
insects, thinning to single locusts over the field."""

import math
import random

import numpy as np
from mathutils import Matrix, Vector

from ironart import scenes_gongbi as GB
from ironart import scenes_gongbi_kit as K
from ironart import scenes_gongbi_land as LD
from ironart import scenes_gongbi_flora as F
from ironart import scenes_look as L
from ironart.geometry import MeshBuilder

SPEC = dict(name="Disaster", art="Art/Events/Disaster.png", master="Events/Disaster@2x.png",
            size=(640, 360), k=4, m=2, seed=41, spp=12, preview_spp=6)

CAM = (0.0, -10.0, 4.2)
TARGET = (0.0, 60.0, 2.6)
FOCAL = 30.0
SM = K.ScreenMap(CAM, TARGET, FOCAL)
HILLS = [(0.06, 0.40, 1400, 500, 2.4), (0.30, 0.41, 2200, 700, 2.4), (0.62, 0.395, 1800, 600, 2.2),
         (0.90, 0.40, 1500, 500, 2.4)]


def height(X, Y):
    from ironart.scenes_terrain import fbm2
    peaks = SM.peaks(HILLS)
    far = LD.peak_field(X, Y, peaks, seed=41, ridge=0.25, ridge_scale=200.0, softmax=4.0)
    roll = (fbm2(X, Y, 60.0, 3, seed=4) - 0.5) * 1.2
    return np.maximum(far, roll)


def earth_material():
    """Parched earth: pale ochre wash partly bare, cracked in an ink net (constant on screen),
    darker furrows where the fields were."""
    mat, b, created = GB._builder("GB_Disaster_Earth")
    if not created:
        return mat
    P = GB.wpos(b)
    x, y, z = b.sep(P)
    n = GB.wnoise(b, P, 0.05, 3.0, 0.55)
    col = b.mix(GB.lin4("#D4BC8C"), GB.lin4("#B89A68"), b.smooth(n, 0.35, 0.7))
    v = b.node("ShaderNodeTexVoronoi", voronoi_dimensions="3D", feature="DISTANCE_TO_EDGE")
    v.inputs["Scale"].default_value = 1.1
    v.inputs["Randomness"].default_value = 1.0
    nz = b.node("ShaderNodeTexNoise", noise_dimensions="3D")
    nz.inputs["Scale"].default_value = 0.8
    b.link(P, nz.inputs["Vector"])
    warped = b.vmath("ADD", P, b.vmath("SCALE", nz.outputs["Color"], scale=0.6).outputs[0]).outputs[0]
    b.link(warped, v.inputs["Vector"])
    cr = b.smooth(v.outputs["Distance"], 0.03, 0.01)
    cr = b.math("MULTIPLY", cr, b.smooth(GB.wnoise(b, P, 0.08, 2.0, 0.5), 0.42, 0.55))
    dist = b.node("ShaderNodeCameraData").outputs["View Distance"]
    cr = b.math("MULTIPLY", cr, b.smooth(dist, 45.0, 6.0))
    fur = GB.stripes(b, b.math("DIVIDE", x, 1.2), 1.0, width=0.05)
    fur = b.math("MULTIPLY", fur, b.smooth(dist, 80.0, 10.0))
    ink = b.math("MAXIMUM", b.math("MULTIPLY", cr, 0.5), b.math("MULTIPLY", fur, 0.12))
    bare = b.math("MULTIPLY", b.smooth(n, 0.55, 0.8), 0.35)
    return GB.finish(mat, b, col, ink=ink, bare=bare, form=0.0)


def build(r):
    rng = random.Random(41)
    pv = r["preview"]
    cols = GB.collections()
    mats = K.materials(cloth=["#8A7A60", "#6A6A5A", "#B8A888", "#5A5650", "ochre", "#E2D6BC",
                              "rouge", "teal", "#7A5A3A", "white", "vermilion", "indigo"],
                       flora=dict(Reed=GB.wash("GB_Withered", "#A88E60", "#7A6040", blend=0.3, form=0.0)))
    mats["Earth"] = earth_material()
    mats["Thatch"] = GB.wash("GB_Thatch", "#BFA676", "#94784A", blend=0.4)
    hills = LD.qinglv("GB_Disaster_Hills", z0=10.0, z1=600.0, cun=0.5, cun_px=7.0, cun_len=60.0,
                      moss_px=11.0, var_scale=0.003, near=200.0, far=4000.0, plain_h=0.02,
                      foot="#C8A878", low="#B49870", mid="#8E9A78", top="#7A8C8A", ribs=True)
    fpx = FOCAL / 36.0 * 640.0
    peaks_w = SM.peaks(HILLS)
    yaw = math.degrees(SM.yaw)
    LD.fan_terrain("Hills", CAM[:2], yaw, 66.0, 300.0, 9000.0, 420, 160, height, hills, cols["land"],
                   attrs={"rib": lambda X, Y: LD.peak_ribs(X, Y, peaks_w, CAM[:2], fpx, 7.0)})
    from ironart.scenes_terrain import fbm2
    LD.fan_terrain("Field", CAM[:2], yaw, 66.0, 2.0, 320.0, 420, 260,
                   lambda X, Y: (fbm2(X, Y, 60.0, 3, seed=4) - 0.5) * 0.6, mats["Earth"], cols["none"])

    def at(sx, sy):
        p = SM.ground(sx, sy, 0.0)
        return p[0], p[1]

    from ironart import scenes_people as P
    ppl = MeshBuilder()
    x, y = at(0.34, 0.88)
    K.person(ppl, random.Random(1), "despair", "peasant", at=(x, y, 0.0), rz=math.radians(160),
             cloth=0, cloth2=5, hat="band")
    x, y = at(0.44, 0.83)
    K.person(ppl, random.Random(2), "point", "lady", at=(x, y, 0.0), rz=math.radians(200),
             cloth=6, cloth2=5, hair_long=True)
    x, y = at(0.485, 0.815)
    K.person(ppl, random.Random(3), "stand", "peasant", at=(x, y, 0.0), rz=math.radians(185),
             cloth=2, cloth2=9, height=1.15)
    for (sx, sy, rz) in ((0.80, 0.58, 0.3), (0.86, 0.585, -0.4)):
        x, y = at(sx, sy)
        K.person(ppl, random.Random(int(sx * 100)), "walk", "peasant", at=(x, y, 0.0), rz=rz,
                 cloth=1, cloth2=5, hat="straw", weapon="staff")
    K.emit(ppl, "People", mats, "fig", thin=K.THIN)
    # withered millet in the fields: rows of bent brown tufts, densest in the foreground
    fl = MeshBuilder()
    nt = 260 if not pv else 120
    for i in range(nt):
        sx = rng.uniform(-0.05, 1.05)
        sy = 0.56 + (rng.random() ** 0.7) * 0.46
        if 0.28 < sx < 0.54 and sy > 0.76:
            continue
        x, y = at(sx, sy)
        F.tuft(fl, rng, (x, y, 0.0), height=rng.uniform(0.8, 1.4), blades=rng.randint(4, 7), mat="Reed",
               spread=0.35, width=0.025)
    # a bare tree on the left, its crab-claw twigs against the sky
    x, y = at(0.12, 0.66)
    F.dead_tree(fl, random.Random(5), height=7.5, at=(x, y, 0.0), depth=4)
    x, y = at(0.93, 0.52)
    F.dead_tree(fl, random.Random(6), height=5.5, at=(x, y, 0.0), depth=3)
    tr_, tufts = K.split(fl, ("Reed",))
    K.emit(tr_, "DeadTrees", mats, "tree")
    K.emit(tufts, "Withered", mats, "fine")
    # the farmhouse with a low wall
    hm = MeshBuilder()
    x, y = at(0.70, 0.535)
    K.cottage(hm, (x, y, 0.0), rz=-0.35, w=8.0, d=5.0)
    x2, y2 = at(0.60, 0.53)
    K.cottage(hm, (x2, y2, 0.0), rz=-0.2, w=5.0, d=4.0)
    K.emit(hm, "Farm", mats, "arch")
    cam = L.camera(CAM, TARGET, focal_mm=FOCAL)
    look = dict(
        sky=dict(stops=[(0.0, "#8A7048", 0.55), (0.22, "#A88A58", 0.42), (0.38, "#C8A878", 0.3),
                        (0.45, "#D8C098", 0.12)], x_tilt=(0.75, 1.15)),
        fade=dict(d0=60.0, d1=3000.0, color=GB.mixc("silk", "#C8A878", 0.4), amount=0.75, gamma=0.7, cover=0.4),
        mist=[dict(y=(0.40, 0.45), soft=0.02, jitter=0.015, dist_min=250.0, amount=0.9, noise_px=120, holes=0.2)],
        mist_tint=("#D8C090", 0.5),
        tone=(1.0, 0.97, 0.9),
    )

    def paint2d(cv, r):
        from ironart import scenes_gongbi_2d as G2
        H, W = cv.H, cv.W
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        u, v = xx / W, yy / H
        # the swarm: a dense cloud upper right streaming down-left over the field
        core = np.exp(-(((u - 0.80) / 0.28) ** 2 + ((v - 0.12) / 0.16) ** 2))
        tail = np.exp(-((((u - 0.55) - (v - 0.30) * 0.9) / 0.16) ** 2)) * np.exp(-((v - 0.32) / 0.2) ** 2)
        n = GB.value_noise(H, W, 40 * cv.k, 9, 3, 0.55)
        dens = np.clip(core * 1.2 + tail * 0.7, 0, 1) * (0.55 + 0.9 * n)
        dens = np.clip(dens, 0, 1.5)
        # the cloud's body: an ochre-ink wash under the insects
        G2_mask = np.clip(dens * 0.75, 0, 1) ** 1.3
        cv.add_mask("sky", GB.blur(G2_mask, 6 * cv.k), "#4E3E28", 0.62)
        cv.add_mask("sky", GB.blur(np.clip(dens - 0.6, 0, 1), 3 * cv.k), "#2E2418", 0.5)
        G2.swarm(cv, 4500 if not r["preview"] else 2500, dens ** 1.5 + 0.01 * (v < 0.6), size=(1.0, 1.8),
                 alpha=0.85, seed=4, where="sky")
        # single locusts over the field and close to the viewer
        near = np.clip(1.0 - np.abs(v - 0.62) / 0.3, 0, 1) * np.clip(u * 1.4, 0, 1) * 0.3 + 0.002
        G2.swarm(cv, 160, near, size=(1.6, 3.2), alpha=0.9, seed=5, where="front")
        # a dull, veiled sun
        G2.sun(cv, (0.24, 0.17), 11.0, color="#E0B070", alpha=0.45, halo_color="#E8C890", halo=0.2)
    return dict(camera=cam, look=look, paint2d=paint2d, notes="swarm upper right; no UI keep-out")
