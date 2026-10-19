"""Event: Bandits - an ambush on a forest road at dusk.

A road winds into a dark wood under an ember-coloured dusk; a merchant's cart has been stopped,
its horse rearing, a merchant fallen back; bandits in headbands burst from the trees on both
sides with torches and blades, one blocks the road ahead; torchlight blooms as warm washes."""

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

SPEC = dict(name="Bandits", art="Art/Events/Bandits.png", master="Events/Bandits@2x.png",
            size=(640, 360), k=4, m=2, seed=71, spp=12, preview_spp=6)

CAM = (1.5, -9.0, 2.6)
TARGET = (-1.0, 40.0, 2.0)
FOCAL = 28.0
SM = K.ScreenMap(CAM, TARGET, FOCAL)
ROAD = [(3.0, -12.0), (1.5, 4.0), (-1.0, 14.0), (-1.5, 24.0), (1.0, 36.0), (5.0, 50.0), (6.0, 70.0)]


def height(X, Y):
    from ironart.scenes_terrain import fbm2
    d, _ = LD.river_dist(X, Y, ROAD)
    banks = np.clip((d - 2.4) / 6.0, 0, 1) ** 1.5 * (1.2 + (fbm2(X, Y, 14.0, 3, seed=2) - 0.3) * 2.0)
    return banks + (fbm2(X, Y, 30.0, 3, seed=7) - 0.5) * 0.6


def road_material():
    mat, b, created = GB._builder("GB_Bandits_Ground")
    if not created:
        return mat
    P = GB.wpos(b)
    x, y, z = b.sep(P)
    n = GB.wnoise(b, P, 0.2, 3.0, 0.55)
    nz = b.sep(b.node("ShaderNodeNewGeometry").outputs["Normal"])[2]
    road = b.smooth(z, 0.35, 0.15)
    col = b.mix(GB.lin4("#6E7A58"), GB.lin4("#4E5A40"), b.smooth(n, 0.4, 0.7))
    col = b.mix(col, b.mix(GB.lin4("#B49A70"), GB.lin4("#9A8058"), n), road)
    sx, sy = GB.screen(b)
    ruts = b.math("MULTIPLY", GB.stripes(b, b.math("DIVIDE", x, 0.9), 1.0, width=0.04), road)
    ruts = b.math("MULTIPLY", ruts, b.smooth(GB.wnoise(b, P, 0.25, 2.0, 0.5), 0.45, 0.6))
    d, _ = GB.dots(b, b.comb(sx, sy, 0.0), 1.0 / 5.0, size=0.12)
    grass = b.math("MULTIPLY", d, b.math("SUBTRACT", 1.0, road))
    ink = b.math("MAXIMUM", b.math("MULTIPLY", ruts, 0.12), b.math("MULTIPLY", grass, 0.5))
    return GB.finish(mat, b, col, ink=ink, form=0.0)


def cart(mb, at, rz, rng):
    """Two-wheeled merchant cart with bales and a tilted shaft."""
    s0 = mb.n
    for sd in (-1, 1):
        mb.cylinder((sd * 0.95, 0, 0.72), (sd * 1.08, 0, 0.72), 0.72, 0.72, "Wood", 18)
        mb.cylinder((sd * 0.9, 0, 0.72), (sd * 1.12, 0, 0.72), 0.12, 0.12, "W_Iron", 8)
    mb.cylinder((-1.0, 0, 0.72), (1.0, 0, 0.72), 0.05, 0.05, "Wood", 6)
    mb.box((0, 0.1, 0.8), (1.7, 2.6, 0.18), "Wood")
    for sd in (-1, 1):
        mb.box((sd * 0.82, 0.1, 0.98), (0.08, 2.6, 0.45), "Wood")
    for i in range(5):
        mb.sphere((rng.uniform(-0.5, 0.5), rng.uniform(-0.8, 1.0), 1.25), 0.38, "Bale", 10, 7, scale=(1.0, 1.3, 0.75))
    mb.box((0, 0.6, 1.5), (1.0, 0.9, 0.7), "W_Lacquer")
    for sd in (-1, 1):
        mb.cylinder((sd * 0.5, -1.1, 0.95), (sd * 0.55, -3.4, 0.45), 0.05, 0.04, "Wood", 6)
    mb.transform(s0, Matrix.Translation(at) @ Matrix.Rotation(rz, 4, "Z"))


def build(r):
    rng = random.Random(71)
    pv = r["preview"]
    cols = GB.collections()
    mats = K.materials(cloth=["#5A4A3A", "#3A3530", "#7A3A2A", "#4A5040", "ochre", "#E2D6BC",
                              "rouge", "teal", "#6A5A4A", "white", "vermilion", "indigo"])
    mats["Ground"] = road_material()
    mats["Bale"] = GB.wash("GB_Bale", "#C8B080", "#9A8050")
    yaw = math.degrees(SM.yaw)
    LD.fan_terrain("Ground", CAM[:2], yaw, 80.0, 1.0, 400.0, 420, 280, height, mats["Ground"], cols["none"])

    def ground(x, y):
        return float(height(np.array([[x]]), np.array([[y]]))[0, 0])

    def at(sx, sy):
        for d in np.linspace(1.0, 120.0, 600):
            ax = math.atan((sx - 0.5) / SM.fn)
            beta = SM.pitch + math.atan(((0.5 - sy) / SM.aspect) / SM.fn)
            a = SM.yaw + ax
            x = CAM[0] + d * math.sin(a)
            y = CAM[1] + d * math.cos(a)
            z = CAM[2] + d / math.cos(ax) * math.tan(beta)
            if z <= ground(x, y):
                return x, y
        return None
    # ---- the wood: a tunnel of trees on both banks -----------------------------------------
    tm = MeshBuilder()
    cam_dir = Vector(TARGET) - Vector(CAM)
    pl = []
    for i in range(70 if not pv else 36):
        y = rng.uniform(4.0, 75.0)
        side = rng.choice((-1, 1))
        dx = side * rng.uniform(5.0, 16.0 + y * 0.15)
        cx = np.interp(y, [p[1] for p in ROAD], [p[0] for p in ROAD])
        x = cx + dx
        pl.append((rng.choice(["LeafDark", "Leaf", "pine", "LeafDark"]), (x, y, ground(x, y) - 0.3), rng.uniform(0.45, 0.75)))
    # two big trees framing the foreground
    pl.append(("LeafDark", (-6.5, 4.0, ground(-6.5, 4.0)), 0.75))
    pl.append(("pine", (9.0, 8.0, ground(9.0, 8.0)), 0.6))
    K.trees(tm, pl, rng, cam_dir=cam_dir, size=1.0, low=pv)
    K.emit(tm, "Wood", mats, "tree")
    # ---- the ambush ---------------------------------------------------------------------------
    ppl = MeshBuilder()
    torches = []
    cx, cy = at(0.47, 0.70)
    cart(ppl, (cx, cy, ground(cx, cy)), math.radians(170), rng)
    hm = MeshBuilder()
    from ironart import scenes_people as P
    P.horse(hm, random.Random(2), gait="rear", coat="HorseCoat3")
    ppl.extend(hm, Matrix.Translation((cx + 0.3, cy - 4.4, ground(cx, cy - 4.4))) @ Matrix.Rotation(math.radians(165), 4, "Z"))
    # merchants
    for (sx, sy, pose, rz, cl) in ((0.40, 0.80, "fall", 200, 4), (0.55, 0.76, "cheer", 150, 5), (0.35, 0.72, "guard", 120, 3)):
        p = at(sx, sy)
        K.person(ppl, random.Random(int(sx * 100)), pose, "robe" if cl != 3 else "soldier", at=(p[0], p[1], ground(*p)),
                 rz=math.radians(rz), cloth=cl, cloth2=5, hat="guan" if cl == 4 else ("helmet" if cl == 3 else None),
                 weapon="spear" if cl == 3 else None)
    # bandits bursting from the trees
    for i, (sx, sy, pose, wpn, rz) in enumerate(((0.16, 0.80, "torch_high", "torch", -70), (0.25, 0.70, "charge", "sword", -60),
                                                (0.75, 0.82, "slash_high", "sword", 70), (0.84, 0.70, "torch_high", "torch", 60),
                                                (0.62, 0.62, "charge", "halberd", 120), (0.48, 0.58, "torch_high", "torch", 175),
                                                (0.08, 0.64, "thrust", "spear", -80), (0.92, 0.60, "torch_high", "torch", 80))):
        p = at(sx, sy)
        if p is None:
            continue
        K.person(ppl, random.Random(30 + i), pose, "bandit", at=(p[0], p[1], ground(*p)), rz=math.radians(rz),
                 cloth=[0, 1, 2, 3][i % 4], cloth2=[3, 8, 1][i % 3], hat="band", weapon=wpn, jitter=5.0)
        if wpn == "torch":
            torches.append((p[0], p[1], ground(*p) + 2.3))
    K.emit(ppl, "Ambush", mats, "fig", thin=K.THIN)
    cam = L.camera(CAM, TARGET, focal_mm=FOCAL)
    look = dict(
        sky=dict(stops=[(0.0, "#3A2E2A", 0.75), (0.15, "#7A4A30", 0.6), (0.3, "#C87848", 0.5), (0.42, "#E0A070", 0.4),
                        (0.55, "#7A5A48", 0.5), (1.0, "#3A3028", 0.6)]),
        fade=dict(d0=15.0, d1=90.0, color="#B89070", amount=0.55, gamma=0.8, cover=0.2),
        mist=[dict(y=(0.48, 0.58), soft=0.03, jitter=0.02, dist_min=35.0, amount=0.7, noise_px=80, holes=0.3)],
        mist_tint=("#C8A080", 0.6),
        tone=(0.86, 0.80, 0.74),
    )

    def paint2d(cv, r):
        # torchlight: warm soft washes around every flame (no bloom - a painted glow)
        for (x, y, z) in torches:
            sx, sy, sz = L.screen_pos(cam, (x, y, z))
            if sz <= 0:
                continue
            c = (sx, 1.0 - sy)
            with cv.paint("front", "#F0A050", 0.22, soft=26.0) as d:
                d.disc(c, 30.0)
            with cv.paint("front", "#F8C878", 0.25, soft=8.0) as d:
                d.disc(c, 9.0)
    return dict(camera=cam, look=look, paint2d=paint2d, notes="no UI keep-out")
