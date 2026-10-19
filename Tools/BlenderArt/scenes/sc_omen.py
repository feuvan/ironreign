"""Event: Omen - a red comet over a dark capital.

Night over the imperial capital (the World Models tier-3 city in the ruled-line 界画 manner,
its minerals dimmed by an ink-blue night wash): halls, gate towers and pagodas with a few lit
windows; dark mountains beyond.  A great broom star in cinnabar sweeps across the ink-blue sky,
staining it red.  On the observatory terrace in the right foreground, beside a bronze armillary
sphere, the court astronomer points it out to anxious officials and a guard."""

import math
import random

import numpy as np
from mathutils import Matrix, Vector

from ironart import scenes_gongbi as GB
from ironart import scenes_gongbi_kit as K
from ironart import scenes_gongbi_land as LD
from ironart import scenes_look as L
from ironart import world_kit as WK
from ironart.geometry import MeshBuilder

SPEC = dict(name="Omen", art="Art/Events/Omen.png", master="Events/Omen@2x.png",
            size=(640, 360), k=4, m=2, seed=121, spp=6, preview_spp=4)

CAM = (-150.0, -205.0, 37.0)
TARGET = (5.0, 10.0, 23.0)
FOCAL = 30.0
SM = K.ScreenMap(CAM, TARGET, FOCAL)
OBS = None          # observatory terrace centre (set in build)
HILLS = [(0.04, 0.27, 1800, 700, 1.6), (0.30, 0.22, 2800, 1000, 1.4), (0.62, 0.25, 2300, 800, 1.5),
         (0.95, 0.24, 2000, 750, 1.6)]
CITY_S = 1.3


def obs_point():
    p = SM.ground(0.79, 0.84, z=27.0)
    return Vector(p)


def height(X, Y):
    from ironart.scenes_terrain import fbm2
    peaks = SM.peaks(HILLS)
    far = LD.peak_field(X, Y, peaks, seed=121, ridge=0.3, ridge_scale=300.0, softmax=4.0)
    o = obs_point()
    d = np.sqrt((X - o.x) ** 2 + (Y - o.y) ** 2)
    hill = 19.0 * np.clip(1.0 - d / 70.0, 0, 1) ** 1.6
    near = hill + (fbm2(X, Y, 50.0, 3, seed=5) - 0.5) * 1.5 * (1 - np.clip(1.0 - np.maximum(np.abs(X), np.abs(Y)) / 90.0, 0, 1))
    return np.where(far > 0.5, np.maximum(far, near), near)


def armillary(mb, at, r=1.25):
    """Bronze armillary sphere (浑仪) on a dragon-pillar stand: meridian, equator and ecliptic
    rings, a sighting tube, four splayed legs on a cross base."""
    x, y, z = at
    c = Vector((x, y, z + 2.2))

    def ring(axis_rot, rad, mat="W_Bronze"):
        pts = []
        for k in range(41):
            a = k / 40 * math.tau
            v = Vector((math.cos(a) * rad, math.sin(a) * rad, 0.0))
            pts.append(tuple(c + axis_rot @ v))
        mb.tube(pts, 0.045, mat, 6, caps=False)
    R = Matrix.Rotation
    ring(R(math.radians(90), 3, "X"), r)                                   # meridian
    ring(R(math.radians(90), 3, "X") @ R(math.radians(90), 3, "Y"), r * 0.96)  # prime vertical
    ring(R(math.radians(35), 3, "X"), r * 0.92)                            # equator
    ring(R(math.radians(58), 3, "X") @ R(math.radians(20), 3, "Z"), r * 0.86)  # ecliptic
    ring(Matrix.Identity(3), r * 1.08, "W_Gold")                           # horizon ring
    mb.cylinder(tuple(c + Vector((0, -0.2, -r * 0.9))), tuple(c + Vector((0, 0.25, r * 0.9))), 0.05, 0.05, "W_Bronze", 6)
    for k in range(4):
        a = k / 4 * math.tau + math.pi / 4
        foot = Vector((x + math.cos(a) * 1.1, y + math.sin(a) * 1.1, z))
        mb.tube([tuple(foot), tuple(c + Vector((math.cos(a) * r * 0.75, math.sin(a) * r * 0.75, -r * 0.7)))],
                0.06, "W_Bronze", 6)
    mb.box((x, y, z), (2.6, 0.3, 0.2), "W_Bronze")
    mb.box((x, y, z), (0.3, 2.6, 0.2), "W_Bronze")


def build(r):
    rng = random.Random(121)
    cols = GB.collections()
    # night: the mineral colours dimmed by an ink-blue wash
    mats = K.materials(cloth=["#8A3A30", "#2E4462", "#3E5E50", "#2A2622", "#A08850", "#C8BCA8",
                              "#6A3440", "#2E5050", "#5A4434", "#D8D0BC", "#9A4430", "#2A3048"],
                       arch=dict(lacquer="#8E3A2C", lacquer_d="#5C2218", wall="#6E2C24", bracket="#2E5446",
                                 beam="#2C4464", tile="#3A4246", stone="#706A60", stone_dark="#5E5A52",
                                 plaster="#9C9486", marble="#A8A498", paving="#8A8478", brick="#6A6458"),
                       skin="#E2D2BC")
    land = LD.qinglv("GB_Omen_Land", z0=0.0, z1=700.0, cun=0.55, cun_px=7.0, cun_len=60.0, moss_px=10.0,
                     var_scale=0.003, near=60.0, far=5000.0, plain_h=0.01, foot="#4E5048", low="#465048",
                     mid="#2C4A46", top="#26344C", light_top="#465A6E", plain=("#3E4A48", "#4A5048"),
                     plain_bare=0.0, ribs=False)
    yaw = math.degrees(SM.yaw)
    LD.fan_terrain("Land", CAM[:2], yaw, 64.0, 6.0, 9000.0, 520, 340, height, land, cols["land"])
    # the capital
    cmb, ctrees = K.city(3, at=(0.0, 0.0, 0.0), rz=0.0, scale=CITY_S)
    K.emit(cmb, "Capital", mats, "arch")
    tm = MeshBuilder()
    K.trees(tm, ctrees, rng, cam_dir=Vector(TARGET) - Vector(CAM), size=1.0, low=True)
    # the observatory terrace on its hill
    o = obs_point()
    z_top = o.z
    obs = MeshBuilder()
    s0 = obs.n
    WK.platform(obs, 18.0, 15.0, 8.0, "W_StoneDark", "W_Paving", z0=0.0, skirt=10.0)
    obs.transform(s0, Matrix.Translation((o.x, o.y, z_top - 8.0)))
    s1 = obs.n
    WK.balustrade_rect(obs, 17.4, 14.4, 0.0, gap=3.0, mat="W_Marble", h=0.9)
    obs.transform(s1, Matrix.Translation((o.x, o.y, z_top)))
    armillary(obs, (o.x + 3.5, o.y + 1.5, z_top))
    # a small hall for the instruments at the back of the terrace
    # a bronze celestial globe on its stand and two lantern posts
    obs.sphere((o.x - 4.8, o.y + 3.8, z_top + 1.7), 0.75, "W_Bronze", 18, 10)
    obs.cylinder((o.x - 4.8, o.y + 3.8, z_top), (o.x - 4.8, o.y + 3.8, z_top + 1.0), 0.5, 0.25, "W_Bronze", 12)
    for (lx, ly) in ((-7.5, -5.8), (7.5, -5.8)):
        obs.cylinder((o.x + lx, o.y + ly, z_top), (o.x + lx, o.y + ly, z_top + 2.6), 0.06, 0.06, "W_Lacquer", 6)
        obs.lathe([(0.0, 0.0), (0.22, 0.05), (0.3, 0.25), (0.3, 0.6), (0.22, 0.8), (0.0, 0.85)], "LanternPaper", 8,
                  center=(o.x + lx, o.y + ly, z_top + 2.6), cap_top=True, smooth=False)
    K.emit(obs, "Observatory", mats, "arch")
    # figures on the terrace: the astronomer points at the comet, officials and a guard watch
    ppl = MeshBuilder()
    face = math.radians(150)
    K.person(ppl, random.Random(1), "point", "official", at=(o.x - 2.0, o.y - 1.0, z_top), rz=face + 0.5,
             cloth=10, cloth2=9, hat="guan")
    for i, (dx, dy, pose, cl, hat) in enumerate(((-4.5, -3.0, "bow_stand", 1, "official"),
                                                 (-0.2, -3.6, "stand_hands", 0, "official"),
                                                 (1.6, -2.4, "stand", 2, "official"),
                                                 (-6.5, 0.5, "stand", 3, "helmet"),
                                                 (2.8, 0.6, "kneel_bow", 1, "official"))):
        K.person(ppl, random.Random(10 + i), pose, "official" if cl != 3 else "armored",
                 at=(o.x + dx, o.y + dy, z_top), rz=face + rng.uniform(-0.3, 0.3), cloth=cl, cloth2=9,
                 hat=hat, weapon="halberd" if cl == 3 else None)
    K.emit(ppl, "Watchers", mats, "fig", thin=K.THIN)
    for (x, y, kind, s) in ((o.x - 16.0, o.y + 4.0, "pine", 0.5), (o.x + 14.0, o.y - 6.0, "pine", 0.45),
                            (o.x - 22.0, o.y - 8.0, "LeafDark", 0.45)):
        z = float(height(np.array([[x]]), np.array([[y]]))[0, 0])
        K.trees(tm, [(kind, (x, y, z), s)], rng, cam_dir=Vector(TARGET) - Vector(CAM), size=1.0)
    # villages and groves on the plain outside the walls
    vil = MeshBuilder()
    for (cx, cy, n) in ((-140.0, -40.0, 6), (120.0, -90.0, 5), (-110.0, 110.0, 5), (150.0, 60.0, 4)):
        for k in range(n):
            x, y = cx + rng.uniform(-22, 22), cy + rng.uniform(-16, 16)
            z = float(height(np.array([[x]]), np.array([[y]]))[0, 0])
            K.cottage(vil, at=(x, y, z), rz=rng.choice((0.0, math.pi / 2)) + rng.uniform(-0.1, 0.1),
                      w=rng.uniform(6.0, 8.0), d=4.6, thatch=rng.random() < 0.4)
        pl = K.grove(rng, (cx + 10, cy + 12), 26.0, 7, ground=lambda x, y: float(height(np.array([[x]]), np.array([[y]]))[0, 0]),
                     kinds=("LeafDark", "pine", "Leaf"), size=(0.5, 0.75))
        K.trees(tm, pl, rng, cam_dir=Vector(TARGET) - Vector(CAM), size=1.0, low=True)
    K.emit(vil, "Villages", mats, "arch")
    K.emit(tm, "Trees", mats, "tree")
    cam = L.camera(CAM, TARGET, focal_mm=FOCAL)
    look = dict(
        sky=dict(stops=[(0.0, "#121A2E", 0.96), (0.18, "#18223A", 0.93), (0.3, "#202C44", 0.88),
                        (0.4, "#2E3A50", 0.78), (0.5, "#34404E", 0.62), (1.0, "#2A3038", 0.5)]),
        fade=dict(d0=150.0, d1=3500.0, color="#4A4448", amount=0.65, gamma=0.8, cover=0.2),
        mist=[dict(y=(0.33, 0.42), soft=0.025, jitter=0.025, dist_min=600.0, amount=0.75, noise_px=110, holes=0.3),
              dict(z=(-2.0, 6.0), soft=3.0, jitter=4.0, dist=(260.0, 420.0), amount=0.5, noise_px=100, holes=0.4)],
        mist_tint=("#4C5A6C", 0.85),
        tone=(0.8, 0.81, 0.9),
        shader_ink_color="#141210",
        kinds={"arch": dict(color="#120F0C"), "fig": dict(color="#120F0C"), "land": dict(color="#120F0C", w=0.8)},
        ink=0.95,
    )

    def paint2d(cv, r):
        from ironart import scenes_gongbi_2d as G2
        rr = np.random.default_rng(121)
        # the red stain the comet throws on the sky, then the broom star itself
        with cv.paint("sky", "#7A2A26", 0.3, soft=45.0) as d:
            d.ellipse((0.36, 0.17), 200, 46)
        G2.comet(cv, (0.15, 0.09), (0.94, 0.30), 0.78, 11.0, color="cinnabar", core="#F6D8A0", rays=15, seed=7)
        with cv.paint("sky", "#D8D0C0", 0.5) as d:
            for i in range(80):
                d.disc((rr.uniform(0, 1), rr.uniform(0, 0.36)), rr.uniform(0.3, 0.75))
        # lit windows and lanterns in the city (warm dabs, no glow)
        for i in range(60):
            x = rr.uniform(-60, 60) * CITY_S
            y = rr.uniform(-60, 50) * CITY_S
            sx, sy, sz = L.screen_pos(cam, (x, y, rr.uniform(1.5, 5.0)))
            if sz <= 0 or not (0 < sx < 1 and 0 < sy < 1):
                continue
            with cv.paint("front", "#E8A050", 0.55, soft=0.8) as d:
                d.disc((sx, 1 - sy), rr.uniform(0.8, 1.3))
    return dict(camera=cam, look=look, paint2d=paint2d,
                notes="comet across the top-left; observatory terrace lower right; no UI keep-out")
