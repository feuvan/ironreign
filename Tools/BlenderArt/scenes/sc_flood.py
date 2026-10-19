"""Event: Flood - a river bursts its banks in a storm.

From a hillside under a black storm sky: the swollen river has broken over its dyke and rolls
across the fields in great stylised waves (水纹) - ridged crests outlined in ink, curling white
foam, rows of wave lines between them; farmhouses stand roof-deep, trees bend in the wind,
villagers cling to a roof and to the hill; slanting rain is drawn over everything."""

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

SPEC = dict(name="Flood", art="Art/Events/Flood.png", master="Events/Flood@2x.png",
            size=(640, 360), k=4, m=2, seed=111, spp=12, preview_spp=6)

CAM = (-6.0, -20.0, 9.0)
TARGET = (4.0, 60.0, 0.0)
FOCAL = 30.0
SM = K.ScreenMap(CAM, TARGET, FOCAL)
HILLS = [(0.06, 0.30, 600, 220, 1.6), (0.30, 0.27, 1100, 360, 1.5), (0.70, 0.25, 1400, 420, 1.4),
         (0.95, 0.29, 700, 260, 1.6)]


def waves(X, Y):
    """Stylised flood surface: long ridged swells rolling towards the viewer (sharp crests,
    rounded troughs) broken up by cross-swells, calmer far away."""
    from ironart.scenes_terrain import fbm2
    d = np.hypot(X - CAM[0], Y - CAM[1])
    u = Y * 0.22 + (fbm2(X, Y, 25.0, 3, seed=3) - 0.5) * 6.0 + np.sin(X * 0.09) * 1.6
    crest = 1.0 - np.abs(np.sin(u)) ** 0.7                     # sharp crests
    cross = (1.0 - np.abs(np.sin(X * 0.13 + Y * 0.05 + 1.3))) * 0.35
    amp = 1.7 * np.clip(1.0 - (d - 30.0) / 160.0, 0.15, 1.0)
    return (crest * 0.8 + cross) * amp - 0.4


def hill(X, Y):
    """The hillside the viewer stands on (left foreground) and far hills."""
    from ironart.scenes_terrain import fbm2
    peaks = SM.peaks(HILLS)
    far = LD.peak_field(X, Y, peaks, seed=111, ridge=0.3, ridge_scale=180.0, softmax=4.0)
    near = (-(X + 4.0) * 0.6 - 0.6 + (Y + 10.0) * -0.09) + (fbm2(X, Y, 12.0, 3, seed=5) - 0.5) * 1.6
    near = np.minimum(near, 2.6 + (fbm2(X, Y, 8.0, 2, seed=6) - 0.5) * 1.2)
    return np.maximum(far, near)


def flood_water():
    """Muddy flood: ochre-grey wash, deeper in the troughs, white foam on the crests; wave lines
    (constant spacing on screen) and foam dots in gb_ink."""
    mat, b, created = GB._builder("GB_Flood_Water")
    if not created:
        return mat
    P = GB.wpos(b)
    x, y, z = b.sep(P)
    sx, sy = GB.screen(b)
    hgt = b.maprange(z, -0.4, 1.4, 0.0, 1.0)
    col = b.mix(GB.lin4("#7A6A48"), GB.lin4("#C2AE84"), hgt)
    # azurite-grey in the deep troughs (the storm sky in the water)
    col = b.mix(GB.lin4("#566468"), col, b.smooth(hgt, 0.0, 0.3))
    foam = b.smooth(hgt, 0.72, 0.86)
    col = b.mix(col, GB.lin4("white"), foam)
    n = GB.wnoise(b, P, 0.08, 2.0, 0.5)
    lines = GB.stripes(b, b.math("ADD", b.math("DIVIDE", sy, 4.5), b.math("MULTIPLY", b.math("SINE", b.math("DIVIDE", sx, 9.0)), 0.3)), 1.0, width=0.07)
    lines = b.math("MULTIPLY", lines, b.smooth(n, 0.38, 0.5))
    lines = b.math("MULTIPLY", lines, b.math("SUBTRACT", 1.0, foam))
    d, _ = GB.dots(b, b.comb(sx, sy, 0.0), 1.0 / 3.2, size=0.16)
    fdots = b.math("MULTIPLY", d, b.smooth(hgt, 0.6, 0.72))
    fdots = b.math("MULTIPLY", fdots, b.math("SUBTRACT", 1.0, b.smooth(hgt, 0.8, 0.9)))
    ink = b.math("MAXIMUM", b.math("MULTIPLY", lines, 0.5), b.math("MULTIPLY", fdots, 0.6))
    return GB.finish(mat, b, col, ink=ink, form=0.0)


def build(r):
    rng = random.Random(111)
    pv = r["preview"]
    cols = GB.collections()
    mats = K.materials(cloth=["#6A665E", "#4A4844", "#9A8A70", "#3A3530", "ochre", "#E2D6BC",
                              "rouge", "teal", "#7A5A3A", "white", "vermilion", "indigo"])
    mats["Thatch"] = GB.wash("GB_Thatch", "#A89470", "#7A6648", blend=0.4)
    land = LD.qinglv("GB_Flood_Land", z0=0.0, z1=160.0, cun=0.75, cun_px=6.0, cun_len=20.0,
                     moss_px=8.0, var_scale=0.01, near=5.0, far=3000.0, plain_h=0.0,
                     foot="#A88E62", low="#8E8A62", mid="#4E6E5E", top="#3E5468", ribs=False)
    yaw = math.degrees(SM.yaw)
    LD.fan_terrain("Hill", CAM[:2], yaw, 66.0, 3.0, 9000.0, 440, 300, hill, land, cols["land"])
    LD.fan_terrain("Flood", CAM[:2], yaw, 66.0, 3.0, 600.0, 520 if not pv else 360, 360 if not pv else 240,
                   waves, flood_water(), cols["land"])

    def wz(x, y):
        return float(waves(np.array([[x]]), np.array([[y]]))[0, 0])
    # farmhouses standing roof-deep in the flood, trees bending
    hm = MeshBuilder()
    for (sx, sy, rz, w) in ((0.56, 0.47, 0.3, 7.0), (0.68, 0.45, -0.2, 6.0), (0.84, 0.50, 0.5, 8.0), (0.40, 0.42, 0.1, 6.5)):
        p = SM.ground(sx, sy, 0.0)
        K.cottage(hm, (p[0], p[1], -2.0), rz=rz, w=w, d=w * 0.65, h=2.6)
    K.emit(hm, "Houses", mats, "arch")
    tm = MeshBuilder()
    for (sx, sy, h) in ((0.47, 0.44, 7.0), (0.62, 0.43, 8.0), (0.76, 0.46, 6.0), (0.93, 0.45, 7.0), (0.30, 0.40, 8.0)):
        p = SM.ground(sx, sy, 0.0)
        F.willow(tm, random.Random(int(sx * 100)), height=h, at=(p[0], p[1], -1.0), strands=22)
    F.dead_tree(tm, random.Random(9), height=6.0, at=(-9.0, 6.0, 0.0), depth=3)
    K.emit(tm, "Trees", mats, "tree")
    # people: on a roof, and on the hill in the foreground pointing at the water
    ppl = MeshBuilder()
    p = SM.ground(0.56, 0.47, 0.0)
    K.person(ppl, random.Random(1), "cheer", "peasant", at=(p[0], p[1], 2.6), rz=math.radians(200), cloth=2, cloth2=5)
    K.person(ppl, random.Random(2), "kneel", "lady", at=(p[0] + 1.2, p[1], 2.4), rz=math.radians(170), cloth=6, cloth2=5,
             hair_long=True)
    for (sx, sy, pose, rz, cl) in ((0.10, 0.80, "point", 40, 0), (0.17, 0.86, "stand", 20, 2), (0.05, 0.88, "despair", 60, 5)):
        p = SM.ground(sx, sy, 0.0)
        hz = float(hill(np.array([[p[0]]]), np.array([[p[1]]]))[0, 0])
        K.person(ppl, random.Random(int(sx * 100)), pose, "peasant", at=(p[0], p[1], max(hz, 0.0)), rz=math.radians(rz),
                 cloth=cl, cloth2=5, hat="straw" if cl == 0 else None)
    K.emit(ppl, "People", mats, "fig", thin=K.THIN)
    cam = L.camera(CAM, TARGET, focal_mm=FOCAL)
    look = dict(
        sky=dict(stops=[(0.0, "#2A2C30", 0.82), (0.2, "#3E4248", 0.7), (0.32, "#6A6C6C", 0.5), (0.45, "#9A9A90", 0.3)]),
        fade=dict(d0=60.0, d1=1200.0, color="#A8A8A0", amount=0.75, gamma=0.8, cover=0.4),
        mist=[dict(y=(0.33, 0.40), soft=0.02, jitter=0.02, dist_min=250.0, amount=0.9, noise_px=90, holes=0.3)],
        mist_tint=("#B8B8B0", 0.5),
        tone=(0.9, 0.91, 0.92),
        age=dict(desat=0.15),
    )

    def paint2d(cv, r):
        from ironart import scenes_gongbi_2d as G2
        rr = np.random.default_rng(111)
        # storm clouds: dark ink washes rolling over the hills
        for (cx, cy, rx, ry, a) in ((0.25, 0.10, 260, 50, 0.45), (0.65, 0.06, 300, 46, 0.5), (0.85, 0.18, 200, 34, 0.4),
                                    (0.45, 0.2, 220, 28, 0.35)):
            with cv.paint("sky", "#26282C", a, soft=ry * 0.6) as d:
                for k_ in range(5):
                    d.ellipse((cx + rr.uniform(-0.08, 0.08), cy + rr.uniform(-0.03, 0.03)), rx * rr.uniform(0.4, 0.7), ry * rr.uniform(0.5, 0.9))
        G2.rain(cv, 900 if not r["preview"] else 500, (-0.1, -0.05, 1.05, 1.0), length=34.0, angle=1.18, width=0.55,
                color="#3A3E44", alpha=0.32, seed=3)
    return dict(camera=cam, look=look, paint2d=paint2d, notes="no UI keep-out")
