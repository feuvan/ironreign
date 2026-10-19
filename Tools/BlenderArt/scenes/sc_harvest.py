"""Event: Harvest - terraced rice fields at sunset.

A hillside of terraces curving round the valley: ripe gold rice above, flooded terraces below
catching the evening sky; farmers in straw hats bent with sickles, others carrying sheaves past
stooks; a thatched hamlet among the trees; pale blue-green hills fading into a rouge sunset with
a low vermilion sun."""

import math
import random

import numpy as np
from mathutils import Matrix, Vector

from ironart import scenes_gongbi as GB
from ironart import scenes_gongbi_kit as K
from ironart import scenes_gongbi_land as LD
from ironart import scenes_look as L
from ironart.geometry import MeshBuilder

SPEC = dict(name="Harvest", art="Art/Events/Harvest.png", master="Events/Harvest@2x.png",
            size=(640, 360), k=4, m=2, seed=31, spp=12, preview_spp=6)

CAM = (0.0, -14.0, 25.0)
TARGET = (4.0, 86.0, 3.7)
FOCAL = 24.0
SM = K.ScreenMap(CAM, TARGET, FOCAL)
STEP = 1.8
HILLS = [(0.10, 0.21, 900, 300, 2.0), (0.32, 0.19, 1300, 420, 1.8), (0.66, 0.20, 1100, 360, 1.7),
         (0.92, 0.18, 1400, 480, 1.6), (0.50, 0.12, 3200, 1000, 1.4), (0.80, 0.11, 3800, 1200, 1.3)]
SUN = (0.71, 0.11)


def base_height(X, Y):
    """A small valley: the near slope falls away from the viewer to a stream at y ~ 70, the far
    slope climbs again; contours are bowed so the terraces curve."""
    from ironart.scenes_terrain import fbm2
    n = (fbm2(X, Y, 40.0, 3, seed=5) - 0.5) * 5.0 + np.sin(X / 19.0) * 2.0
    yb = Y - (X / 45.0) ** 2 * 10.0
    near = np.clip(64.0 - yb, 0, None) * 0.30
    far = np.clip(yb - 82.0, 0, None) * 0.20
    h = near + far + n * np.clip(np.abs(yb - 72.0) / 20.0, 0, 1)
    return np.minimum(h, 30.0 + (fbm2(X, Y, 90.0, 2, seed=8) - 0.5) * 8)


def terraced(X, Y):
    h = base_height(X, Y)
    q = h / STEP
    fl = np.floor(q)
    fr = q - fl
    riser = np.clip((fr - 0.88) / 0.12, 0, 1)
    return (fl + riser) * STEP


def height(X, Y):
    """Beyond the terraces: the untilled upper slope and the far hills."""
    peaks = SM.peaks(HILLS)
    far = LD.peak_field(X, Y, peaks, seed=31, ridge=0.3, ridge_scale=200.0, softmax=4.0)
    return np.maximum(base_height(X, Y) + 0.6, far)


def field_material():
    """Terraces: ripe gold rice in rows on the flats (晕染 paler at the lips), grass-green risers,
    flooded lower terraces left as pale water; ink rows and ear dots in gb_ink."""
    mat, b, created = GB._builder("GB_Harvest_Field")
    if not created:
        return mat
    P = GB.wpos(b)
    x, y, z = b.sep(P)
    q = b.math("FRACT", b.math("DIVIDE", b.math("ADD", z, 0.02), STEP))
    # flats sit exactly on multiples of STEP; the risers are everything in between
    flat = b.math("SUBTRACT", 1.0, b.smooth(q, 0.02, 0.06))
    terr = b.math("FLOOR", b.math("DIVIDE", z, STEP))
    rnd = b.math("FRACT", b.math("MULTIPLY", b.math("SINE", b.math("MULTIPLY", terr, 12.9898)), 43758.5453))
    wet = b.math("MULTIPLY", b.smooth(z, 2.2, 1.4), 1.0)                         # valley-floor paddies flooded
    cut = b.math("MULTIPLY", b.smooth(rnd, 0.74, 0.76), b.math("SUBTRACT", 1.0, wet))   # harvested stubble
    vn = GB.wnoise(b, P, 0.04, 3.0, 0.5)
    rice = b.mix(GB.lin4("#DDBA60"), GB.lin4("#C49040"), b.smooth(vn, 0.35, 0.7))
    stub = b.mix(GB.lin4("#D8C08A"), GB.lin4("#C4A468"), b.smooth(vn, 0.35, 0.7))
    col = b.mix(rice, stub, cut)
    col = b.mix(col, GB.lin4("#C8C2A4"), wet)
    col = b.mix(GB.lin4("#B4A47A"), col, flat)
    sx, sy = GB.screen(b)
    # rice stalks: short vertical strokes, constant on screen, broken into clumps; ear dots
    stalk = GB.stripes(b, b.math("ADD", b.math("DIVIDE", sx, 3.2), b.math("MULTIPLY", GB.wnoise(b, P, 0.6, 2.0, 0.5), 1.5)), 1.0, width=0.08)
    clump = b.smooth(GB.wnoise(b, b.vmath("MULTIPLY", P, b.vec((1.0, 1.0, 0.2))).outputs[0], 0.9, 2.0, 0.5), 0.5, 0.6)
    stalk = b.math("MULTIPLY", stalk, clump)
    d, _ = GB.dots(b, b.comb(sx, sy, 0.0), 1.0 / 3.5, size=0.12)
    alive = b.math("SUBTRACT", 1.0, b.math("MAXIMUM", cut, wet))
    ink = b.math("MULTIPLY", b.math("MAXIMUM", b.math("MULTIPLY", stalk, 0.35), b.math("MULTIPLY", d, 0.5)), alive)
    ink = b.math("MULTIPLY", ink, flat)
    # flooded paddies: a few short ripple strokes
    rip = GB.stripes(b, b.math("ADD", b.math("DIVIDE", sy, 5.0), b.math("MULTIPLY", GB.wnoise(b, P, 0.3, 2.0, 0.5), 1.0)), 1.0, width=0.06)
    rip = b.math("MULTIPLY", rip, b.smooth(GB.wnoise(b, b.vmath("MULTIPLY", P, b.vec((0.6, 3.0, 1.0))).outputs[0], 0.5, 2.0, 0.5), 0.55, 0.62))
    ink = b.math("MAXIMUM", ink, b.math("MULTIPLY", b.math("MULTIPLY", rip, wet), 0.4))
    bare = b.math("MULTIPLY", wet, 0.55)
    return GB.finish(mat, b, col, ink=ink, bare=bare, form=0.05)


def build(r):
    rng = random.Random(31)
    pv = r["preview"]
    cols = GB.collections()
    mats = K.materials(cloth=["#8A9A7A", "azurite_l", "#B8A888", "#5A5650", "ochre", "#E2D6BC",
                              "rouge", "teal", "#7A5A3A", "white", "vermilion", "indigo"],
)
    mats["Field"] = field_material()
    mats["Thatch"] = GB.wash("GB_Thatch", "#C8AE78", "#9A804E", blend=0.4)
    mats["Sheaf"] = GB.wash("GB_Sheaf", "#D8B862", "#A8823C", blend=0.4, form=0.05)
    hills = LD.qinglv("GB_Harvest_Hills", z0=20.0, z1=700.0, cun=0.6, cun_px=7.0, cun_len=60.0,
                      moss_px=10.0, var_scale=0.003, near=80.0, far=5000.0, plain_h=0.02,
                      top="azurite", mid="malachite", ribs=True)
    fpx = FOCAL / 36.0 * 640.0
    peaks_w = SM.peaks(HILLS)
    yaw = math.degrees(SM.yaw)
    # far hills (land ink) and the terraced near ground (fine ink: the terrace lips are ruled)
    LD.fan_terrain("Hills", CAM[:2], yaw, 80.0, 245.0, 9000.0, 420, 200, height, hills, cols["land"],
                   attrs={"rib": lambda X, Y: LD.peak_ribs(X, Y, peaks_w, CAM[:2], fpx, 7.0)})
    LD.fan_terrain("Terraces", CAM[:2], yaw, 80.0, 3.0, 260.0, 640 if not pv else 420, 420 if not pv else 260,
                   terraced, mats["Field"], cols["fine"])

    def ground(x, y):
        return float(terraced(np.array([[x]]), np.array([[y]]))[0, 0])

    def at(sx, sy):
        # walk down the view ray until it meets the terraces
        for d in np.linspace(5.0, 260.0, 700):
            ax = math.atan((sx - 0.5) / SM.fn)
            beta = SM.pitch + math.atan(((0.5 - sy) / SM.aspect) / SM.fn)
            a = SM.yaw + ax
            x = CAM[0] + d * math.sin(a)
            y = CAM[1] + d * math.cos(a)
            z = CAM[2] + d / math.cos(ax) * math.tan(beta)
            if z <= ground(x, y):
                return x, y
        return None
    from ironart import scenes_people as P
    ppl = MeshBuilder()
    for i, (sx, sy, pose, wpn, rz) in enumerate((
            (0.24, 0.84, "farm_bend", "sickle", 0.5), (0.38, 0.93, "farm_bend", "sickle", -0.4),
            (0.62, 0.80, "walk", None, 1.4), (0.13, 0.72, "farm_bend", "sickle", 0.9),
            (0.77, 0.73, "farm_bend", "sickle", -0.8), (0.50, 0.69, "carry", None, 1.6),
            (0.88, 0.88, "carry", None, -1.2), (0.32, 0.67, "farm_bend", "sickle", 0.2),
            (0.68, 0.66, "farm_bend", "sickle", 2.4), (0.06, 0.92, "stand", "staff", 0.6),
            (0.45, 0.645, "farm_bend", "sickle", 1.0))):
        p = at(sx, sy)
        if p is None:
            continue
        x, y = p
        f = MeshBuilder()
        sk = P.figure(f, random.Random(i), pose, "farmer", cloth=[0, 2, 4, 9, 8][i % 5], cloth2=[5, 9, 3][i % 3],
                      hat="straw", weapon=wpn, jitter=4.0)
        if pose == "carry":
            # carrying pole (扁担) on the shoulder with a sheaf hanging at each end
            sh = sk.arm[1]["shoulder"] + Vector((0, 0, 0.06))
            for e in (-1, 1):
                end = sh + Vector((0, e * 0.85, -0.04))
                f.cylinder(tuple(sh), tuple(end), 0.018, 0.016, "Wood", 5)
                f.cylinder(tuple(end), tuple(end + Vector((0, 0, -0.35))), 0.004, 0.004, "Rope", 3)
                f.lathe([(0.0, -0.05), (0.22, 0.0), (0.16, 0.35), (0.1, 0.5), (0.18, 0.65), (0.24, 0.9), (0.0, 1.0)],
                        "Sheaf", 9, center=tuple(end + Vector((0, 0, -1.05))), cap_top=True)
        ppl.extend(f, Matrix.Translation((x, y, ground(x, y))) @ Matrix.Rotation(rz, 4, "Z"))
    K.emit(ppl, "Farmers", mats, "fig", thin=K.THIN)
    # stooks of sheaves on the harvested terraces
    st = MeshBuilder()
    for i in range(26 if not pv else 14):
        p = at(rng.uniform(0.02, 0.98), rng.uniform(0.6, 0.76))
        if p is None:
            continue
        x, y = p
        z = ground(x, y)
        st.lathe([(0.0, 0.0), (0.42, 0.02), (0.3, 0.4), (0.16, 0.7), (0.24, 0.85), (0.3, 1.05), (0.0, 1.2)],
                 "Sheaf", 10, center=(x, y, z), cap_top=True)
    K.emit(st, "Stooks", mats, "fig")
    # a thatched hamlet among trees on the left, a big tree on the right
    hm = MeshBuilder()
    for (sx, sy, rz, s_) in ((0.13, 0.42, 0.3, 1.0), (0.21, 0.41, -0.2, 0.9), (0.06, 0.40, 0.1, 0.85), (0.86, 0.41, -0.3, 1.0)):
        p = at(sx, sy)
        if p is None:
            continue
        x, y = p
        K.cottage(hm, (x, y, ground(x, y)), rz, w=7.0 * s_, d=4.6 * s_)
    K.emit(hm, "Hamlet", mats, "arch")
    tm = MeshBuilder()
    pl = []
    for (sx, sy, n, rad) in ((0.15, 0.40, 7, 12.0), (0.42, 0.37, 6, 14.0), (0.80, 0.39, 6, 12.0), (0.96, 0.46, 4, 8.0)):
        p = at(sx, sy)
        if p is not None:
            pl += K.grove(rng, p, rad, n, ground=ground, kinds=("Leaf", "LeafAutumn", "LeafDark"), size=(0.5, 0.8))

    K.trees(tm, pl, rng, cam_dir=Vector(TARGET) - Vector(CAM), size=0.6)
    K.emit(tm, "Trees", mats, "tree")
    cam = L.camera(CAM, TARGET, focal_mm=FOCAL)
    look = dict(
        sky=dict(stops=[(0.0, "#C8A070", 0.25), (0.16, "#E0A070", 0.28), (0.27, "vermilion", 0.32),
                        (0.33, "#E8B890", 0.2), (0.45, "silk", 0.0)]),
        fade=dict(d0=200.0, d1=4500.0, color=GB.mixc("silk", "#E8B890", 0.4), amount=0.8, gamma=0.7, cover=0.45),
        mist=[dict(y=(0.27, 0.33), soft=0.02, jitter=0.02, dist_min=300.0, amount=1.0, noise_px=110, holes=0.2),
              dict(y=(0.17, 0.22), soft=0.02, jitter=0.015, dist_min=2000.0, amount=0.85, noise_px=120, holes=0.3)],
        mist_tint=("#F0D8B8", 0.4),
        tone=(1.0, 0.985, 0.95),
    )

    def paint2d(cv, r):
        from ironart import scenes_gongbi_2d as G2
        G2.sun(cv, SUN, 13.0, color="vermilion", alpha=0.85, halo_color="#E8A070", halo=0.3)
        # homing birds
        rr = np.random.default_rng(31)
        with cv.paint("sky", "ink", 0.7) as d:
            for i in range(6):
                x = 0.36 + i * 0.03 + rr.uniform(-0.01, 0.01)
                y = 0.10 + rr.uniform(-0.02, 0.02)
                s = 0.005
                d.stroke([(x - s, y - s * 0.8), (x, y), (x + s, y - s * 0.9)], 1.0, "flat")
    return dict(camera=cam, look=look, paint2d=paint2d, notes="sun at (73%, 25%)")
