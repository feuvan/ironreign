"""Event: Court - the grand throne hall, painted in the ruled-line 界画 manner.

Down the axis of the hall: vermilion lacquer pillars with gilt bands, dougong brackets carrying
painted beams, a coffered ceiling of azurite / malachite panels with gilt roundels, a white
marble dais of three terraces with the sovereign enthroned before a gilt dragon screen, and two
disciplined ranks of officials on each side of the red carpet - court robes in rank colours,
winged black hats, ivory hu tablets held before the chest.  The camera is level (verticals stay
parallel, as in 界画)."""

import math
import random

from mathutils import Matrix, Vector

from ironart import scenes_gongbi as GB
from ironart import scenes_gongbi_kit as K
from ironart import scenes_look as L
from ironart import scenes_people as P
from ironart import world_kit as WK
from ironart.geometry import MeshBuilder

SPEC = dict(name="Court", art="Art/Events/Court.png", master="Events/Court@2x.png",
            size=(640, 360), k=4, m=2, seed=11, spp=12, preview_spp=6)

HW = 17.0                     # half width of the hall interior
H = 15.0                      # ceiling height over the nave
COLS_Y = [7.0, 14.0, 21.0, 28.0]
COL_X = (6.0, 12.0)
COL_H = 11.4
DAIS_Y = 37.0                 # centre of the dais
BACK = 46.0


# ---------------------------------------------------------------------------------------------
# hall-specific materials
# ---------------------------------------------------------------------------------------------
def coffer_material(s=2.4):
    """天花 ceiling panels: azurite field, malachite ring, gilt roundel with a curled dragon
    suggested by ink scrolls, gilt corner motifs; ink lines on every border."""
    mat, b, created = GB._builder("GB_Court_Coffer")
    if not created:
        return mat
    x, y, z = b.sep(GB.wpos(b))
    u = b.math("SUBTRACT", b.math("FRACT", b.math("DIVIDE", x, s)), 0.5)
    v = b.math("SUBTRACT", b.math("FRACT", b.math("DIVIDE", y, s)), 0.5)
    r = b.math("SQRT", b.math("ADD", b.math("MULTIPLY", u, u), b.math("MULTIPLY", v, v)))
    sq = b.math("MAXIMUM", b.math("ABSOLUTE", u), b.math("ABSOLUTE", v))
    field = GB.lin4("azurite")
    ring = b.smooth(r, 0.33, 0.31)
    roundel = b.smooth(r, 0.21, 0.19)
    col = b.mix(field, GB.lin4("malachite"), ring)
    col = b.mix(col, GB.lin4("gold"), roundel)
    # corner leaves (岔角): gilt where the square corners are
    corner = b.math("MULTIPLY", b.smooth(r, 0.5, 0.55), b.smooth(sq, 0.38, 0.42))
    col = b.mix(col, GB.lin4("gold_d"), b.math("MULTIPLY", corner, 0.8))
    # ink: ring borders, square inset border, scroll curls inside the roundel
    def line(val, at, w=0.008):
        return b.math("SUBTRACT", 1.0, b.smooth(b.math("ABSOLUTE", b.math("SUBTRACT", val, at)), w * 0.5, w * 1.6))
    ink = b.math("MAXIMUM", line(r, 0.32), line(r, 0.20))
    ink = b.math("MAXIMUM", ink, line(sq, 0.44, 0.01))
    wv = b.node("ShaderNodeTexWave", wave_type="RINGS", rings_direction="SPHERICAL")
    wv.inputs["Scale"].default_value = 3.0
    wv.inputs["Distortion"].default_value = 6.0
    wv.inputs["Detail"].default_value = 2.0
    b.link(b.comb(u, v, 0.0), wv.inputs["Vector"])
    curls = b.math("MULTIPLY", b.smooth(wv.outputs["Fac"], 0.85, 0.95), roundel)
    ink = b.math("MAXIMUM", ink, b.math("MULTIPLY", curls, 0.7))
    return GB.finish(mat, b, col, ink=b.math("MULTIPLY", ink, 0.8), form=0.0)


def beam_paint_material():
    """和玺彩画 beams: alternating azurite / malachite panels with gilt borders and roundels."""
    mat, b, created = GB._builder("GB_Court_Beam")
    if not created:
        return mat
    x, y, z = b.sep(GB.wpos(b))
    t = b.math("ADD", x, y)
    seg = b.math("FRACT", b.math("DIVIDE", t, 2.4))
    alt = b.math("FRACT", b.math("DIVIDE", t, 4.8))
    col = b.mix(GB.lin4("azurite"), GB.lin4("malachite"), b.smooth(alt, 0.49, 0.51))
    border = b.smooth(b.math("ABSOLUTE", b.math("SUBTRACT", seg, 0.5)), 0.44, 0.46)
    col = b.mix(col, GB.lin4("gold"), border)
    # a gilt roundel (旋子) in the middle of every panel
    zc = b.math("SUBTRACT", b.math("FRACT", b.math("MULTIPLY", z, 1.0)), 0.5)
    rr = b.math("SQRT", b.math("ADD", b.math("MULTIPLY", b.math("MULTIPLY", b.math("SUBTRACT", seg, 0.5), 2.4), b.math("MULTIPLY", b.math("SUBTRACT", seg, 0.5), 2.4)), b.math("MULTIPLY", zc, zc)))
    col = b.mix(col, GB.lin4("gold_l"), b.math("SUBTRACT", b.smooth(rr, 0.3, 0.27), b.smooth(rr, 0.2, 0.17)))
    g = GB.facing(b, 0.3, 0.3, 1.0)
    col = b.mix(col, b.cmul(col, 0.75), g)
    ink = b.math("MULTIPLY", GB.stripes(b, seg, 1.0, width=0.03), 0.6)
    return GB.finish(mat, b, col, ink=ink)


def floor_material(s=1.3):
    """Golden bricks (金砖): pale grey-ochre squares ruled with fine ink lines."""
    mat, b, created = GB._builder("GB_Court_Floor")
    if not created:
        return mat
    x, y, z = b.sep(GB.wpos(b))
    lx = GB.stripes(b, b.math("DIVIDE", x, s), 1.0, width=0.025)
    ly = GB.stripes(b, b.math("DIVIDE", y, s), 1.0, width=0.025)
    n = GB.wnoise(b, GB.wpos(b), 0.6, 2.0, 0.5)
    col = b.mix(GB.lin4("#C4B8A0"), GB.lin4("#B0A388"), b.smooth(n, 0.4, 0.65))
    dist = b.node("ShaderNodeCameraData").outputs["View Distance"]
    ink = b.math("MULTIPLY", b.math("MAXIMUM", lx, ly), b.maprange(dist, 8.0, 40.0, 0.55, 0.15))
    return GB.finish(mat, b, col, ink=ink, form=0.0)


def carpet_material():
    mat, b, created = GB._builder("GB_Court_Carpet")
    if not created:
        return mat
    x, y, z = b.sep(GB.wpos(b))
    ax = b.math("ABSOLUTE", x)
    border = b.math("SUBTRACT", b.smooth(ax, 1.25, 1.3), b.smooth(ax, 1.5, 1.55))
    col = b.mix(GB.lin4("cinnabar"), GB.lin4("gold"), border)
    col = b.mix(col, GB.lin4("cinnabar_d"), b.smooth(ax, 1.5, 1.55))
    # roundels down the run
    v = b.math("SUBTRACT", b.math("FRACT", b.math("DIVIDE", y, 2.6)), 0.5)
    rr = b.math("SQRT", b.math("ADD", b.math("MULTIPLY", b.math("DIVIDE", x, 2.6), b.math("DIVIDE", x, 2.6)), b.math("MULTIPLY", v, v)))
    rd = b.math("SUBTRACT", b.smooth(rr, 0.2, 0.18), b.smooth(rr, 0.15, 0.13))
    col = b.mix(col, GB.lin4("gold"), b.math("MULTIPLY", rd, 0.8))
    ink = b.math("MULTIPLY", b.math("MAXIMUM", GB.stripes(b, b.math("DIVIDE", ax, 1.55), 1.0, width=0.01),
                                    b.math("MULTIPLY", rd, 0.0)), 0.5)
    return GB.finish(mat, b, col, ink=ink, form=0.0)


def screen_material():
    """Gilt dragon screen: gold ground with cloud scrolls and a coiling dragon body drawn in ink,
    vermilion and malachite accents."""
    mat, b, created = GB._builder("GB_Court_Screen")
    if not created:
        return mat
    P_ = GB.wpos(b)
    x, y, z = b.sep(P_)
    wv = b.node("ShaderNodeTexWave", wave_type="RINGS", rings_direction="SPHERICAL")
    wv.inputs["Scale"].default_value = 1.1
    wv.inputs["Distortion"].default_value = 7.0
    wv.inputs["Detail"].default_value = 3.0
    b.link(b.vmath("MULTIPLY", P_, b.vec((1.0, 1.0, 1.3))).outputs[0], wv.inputs["Vector"])
    scroll = b.smooth(wv.outputs["Fac"], 0.86, 0.95)
    # dragon body: a sinuous band (sine in x across the screen)
    body_c = b.math("ADD", b.math("MULTIPLY", b.math("SINE", b.math("MULTIPLY", x, 0.9)), 1.1), 4.3)
    dz = b.math("ABSOLUTE", b.math("SUBTRACT", z, body_c))
    body = b.smooth(dz, 0.55, 0.45)
    edge = b.math("SUBTRACT", 1.0, b.smooth(b.math("ABSOLUTE", b.math("SUBTRACT", dz, 0.5)), 0.03, 0.09))
    scales = GB.stripes(b, b.math("ADD", x, b.math("MULTIPLY", z, 0.5)), 3.0, width=0.12)
    col = b.mix(GB.lin4("gold"), GB.lin4("gold_d"), b.math("MULTIPLY", scroll, 0.5))
    col = b.mix(col, GB.lin4("#D8B060"), body)
    ink = b.math("MAXIMUM", b.math("MULTIPLY", scroll, b.math("SUBTRACT", 1.0, body)),
                 b.math("MAXIMUM", edge, b.math("MULTIPLY", b.math("MULTIPLY", scales, body), 0.5)))
    return GB.finish(mat, b, col, ink=b.math("MULTIPLY", ink, 0.65), form=0.05)


# ---------------------------------------------------------------------------------------------
# figures
# ---------------------------------------------------------------------------------------------
def official(rng, robe, hat="official", pose="stand_hands", tablet=True):
    """One court official (local frame, facing -Y) with an ivory hu tablet before the chest."""
    f = MeshBuilder()
    sk = P.figure(f, rng, pose, "official", cloth=robe, cloth2=9, hat=hat, jitter=1.5)
    if tablet:
        hl, hr = sk.arm[1]["hand"], sk.arm[-1]["hand"]
        c = (hl + hr) * 0.5 + Vector((0, -0.03, 0.02))
        up = (sk.neck - c).normalized()
        top = c + up * 0.36 + Vector((0, -0.06, 0))
        f.box(tuple(c - up * 0.04), (0.075, 0.02, 0.42), "Tablet")
        s0 = f.n - 8
        q = Vector((0, -0.18, 1.0)).normalized().to_track_quat("Z", "Y")
        f.transform(s0, Matrix.Translation(c) @ q.to_matrix().to_4x4() @ Matrix.Translation(-c))
    return f


def build(r):
    rng = random.Random(11)
    pv = r["preview"]
    cols = GB.collections()
    # rank colours: crimson (high), azurite (middle), malachite (low); imperial yellow for the throne
    cloth = ["cinnabar", "azurite", "malachite", "#3A3530", "gold_l", "#E2D6BC", "rouge", "teal",
             "#7A5A3A", "white", "vermilion", "indigo"]
    mats = K.materials(arch=dict(lacquer=GB.mixc("vermilion", "cinnabar", 0.45)), cloth=cloth,
                       banners=["cinnabar", "gold", "azurite", "white", "malachite", "vermilion"],
                       extra=dict(Tablet=GB.wash("GB_Tablet", "white", "#D8CCB4", form=0.0)))
    mats["W_BeamPaint"] = beam_paint_material()
    mats["Coffer"] = coffer_material()
    mats["Floor"] = floor_material()
    mats["Carpet"] = carpet_material()
    mats["Screen"] = screen_material()
    hall = MeshBuilder()
    # ---- floor, carpet ------------------------------------------------------------------------
    hall.box((0, BACK / 2 - 4, -0.3), (HW * 2 + 2, BACK + 10, 0.3), "Floor", skip=("bottom",))
    hall.box((0, 15.0, 0.0), (3.1, 30.0, 0.03), "Carpet", skip=("bottom",))
    # ---- walls: side walls with high lattice windows, back wall -------------------------------
    for side in (-1, 1):
        x = side * (HW + 0.5)
        hall.box((x, BACK / 2 - 4, 0), (1.0, BACK + 8, 4.2), "W_RedWall")
        hall.box((x, BACK / 2 - 4, 4.2), (0.2, BACK + 8, 0.25), "W_Gold")
        hall.box((x, BACK / 2 - 4, 4.45), (1.0, BACK + 8, 4.8), "W_Lattice")
        hall.box((x, BACK / 2 - 4, 9.25), (1.0, BACK + 8, H - 9.25), "W_RedWall")
    hall.box((0, BACK + 0.5, 0), (HW * 2 + 2, 1.0, H), "W_RedWall")
    # ---- columns, gilt bands, dougong frieze, beams ------------------------------------------
    for x in (-COL_X[1], -COL_X[0], COL_X[0], COL_X[1]):
        for y in COLS_Y:
            rr = 0.62 if abs(x) < 8 else 0.55
            WK.column(hall, x, y, 0.0, COL_H, rr, "W_Lacquer", seg=20)
            for z in (0.7, COL_H - 1.0):
                hall.cylinder((x, y, z), (x, y, z + 0.32), rr + 0.04, rr + 0.04, "W_Gold", 20)
    # longitudinal architraves on the column lines, a dougong frieze on the inner ones
    for x in (-COL_X[1], -COL_X[0], COL_X[0], COL_X[1]):
        WK.beam(hall, (x, -2.0), (x, BACK), COL_H - 0.1, 1.0, 0.75, "W_BeamPaint")
    for x in (-COL_X[0], COL_X[0]):
        hall.box((x, BACK / 2 - 1, COL_H + 0.9), (1.1, BACK + 2, 0.2), "W_WoodDark")
        y = -1.0
        while y < BACK:
            WK.bracket_set(hall, x, y, COL_H + 1.1, -1.0 if x > 0 else 1.0, 0.0, k=0.9, mat="W_Bracket")
            y += 1.75
        hall.box((x + (-0.55 if x > 0 else 0.55), BACK / 2 - 1, COL_H + 1.85), (1.6, BACK + 2, 0.35), "W_Fascia")
    # cross beams over the side aisles only (the nave stays open up to the coffers)
    for y in COLS_Y:
        for sd in (-1, 1):
            WK.beam(hall, (sd * COL_X[1], y), (sd * COL_X[0], y), COL_H - 0.1, 1.0, 0.6, "W_BeamPaint")
    # side-aisle ceiling (lower, plain painted boards)
    for sd in (-1, 1):
        hall.box((sd * (COL_X[0] + HW) / 2, BACK / 2 - 1, COL_H + 0.9), (HW - COL_X[0] + 1.0, BACK + 2, 0.3), "W_BeamPaint", skip=("top",))
    # coffered nave ceiling (天花): a grid of gilt-edged ribs framing painted panels
    hall.box((0, BACK / 2 - 1, H), (COL_X[0] * 2, BACK + 2, 0.2), "Coffer", skip=("top",))
    hall.box((0, BACK / 2 - 1, COL_H + 2.2), (COL_X[0] * 2 - 0.4, BACK + 2, H - COL_H - 2.2), "W_RedWall", skip=("top", "bottom"))
    for i in range(-2, 3):
        hall.box((i * 2.4, BACK / 2 - 1, H - 0.28), (0.18, BACK + 2, 0.28), "W_Fascia", skip=("top",))
    for j in range(0, 21):
        hall.box((0, -2.0 + j * 2.4, H - 0.28), (COL_X[0] * 2, 0.18, 0.28), "W_Fascia", skip=("top",))
    # palace lanterns (宫灯) hanging over the aisle
    for sx in (-1, 1):
        for y in (10.5, 17.5, 24.5):
            x = sx * 3.9
            hall.cylinder((x, y, H), (x, y, 9.6), 0.03, 0.03, "W_Gold", 4)
            hall.lathe([(0.0, 0.0), (0.34, 0.05), (0.46, 0.35), (0.46, 0.95), (0.34, 1.25), (0.0, 1.3)],
                       "LanternPaper", 6, center=(x, y, 8.3), cap_top=True, smooth=False)
            hall.cylinder((x, y, 9.55), (x, y, 9.7), 0.4, 0.4, "W_Gold", 6)
            hall.cylinder((x, y, 8.25), (x, y, 8.35), 0.4, 0.4, "W_Gold", 6)
            hall.cylinder((x, y, 8.25), (x, y, 7.5), 0.08, 0.02, "W_Tassel", 6)
    # ---- dais: three marble terraces, steps, balustrades --------------------------------------
    dais = MeshBuilder()
    dz = 0.0
    for t, (w, d, hgt) in enumerate(((20.0, 13.0, 0.8), (14.0, 9.5, 0.8), (8.5, 6.5, 0.8))):
        WK.platform(dais, w, d, hgt, "W_Marble", "W_Paving", z0=dz, skirt=0.2)
        WK.steps(dais, 0, -d / 2 - 5 * 0.34 + 0.02, dz, 3.6, hgt, 5, 0.34, "W_Marble")
        if t < 2:
            WK.balustrade_rect(dais, w - 0.4, d - 0.4, dz + hgt, gap=4.6, mat="W_Marble", h=0.9)
        dz += hgt
    tz = dz
    # throne: lacquer seat, high back with gilt crest, armrests, footstool
    dais.box((0, 0.6, tz), (2.4, 1.6, 1.0), "W_Lacquer")
    dais.box((0, 1.3, tz + 1.0), (2.8, 0.3, 2.0), "W_Lacquer")
    dais.box((0, 1.28, tz + 3.0), (3.2, 0.4, 0.45), "W_Gold")
    for sx in (-1, 1):
        dais.box((sx * 1.3, 0.6, tz + 1.0), (0.3, 1.4, 0.8), "W_Gold")
    dais.box((0, -0.55, tz), (1.8, 0.7, 0.32), "W_Lacquer")
    # gilt dragon screen: 7 panels stepping back, crested
    for k in range(7):
        x = (k - 3) * 1.55
        yk = 3.0 + abs(k - 3) * 0.3
        hk = 6.0 - abs(k - 3) * 0.55
        dais.box((x, yk, tz), (1.52, 0.22, hk), "Screen")
        dais.box((x, yk, tz + hk), (1.6, 0.34, 0.28), "W_Gold")
        dais.box((x, yk - 0.13, tz), (1.6, 0.06, 0.25), "W_Lacquer")
    # ceremonial fans on poles behind the throne, incense burners and cranes on the terraces
    for sx in (-1, 1):
        dais.cylinder((sx * 3.4, 2.2, tz), (sx * 3.4, 2.2, tz + 5.4), 0.06, 0.06, "W_Gold", 8)
        dais.sphere((sx * 3.4, 2.2, tz + 6.2), 0.95, "W_Lacquer", 18, 8, scale=(1.0, 0.1, 1.15))
        dais.sphere((sx * 3.4, 2.15, tz + 6.2), 0.55, "W_Gold", 14, 6, scale=(1.0, 0.1, 1.15))
        for (x, y, zz) in ((sx * 5.6, -2.6, 1.6), (sx * 8.6, -5.0, 0.8)):
            dais.lathe([(0.45, 0.0), (0.55, 0.35), (0.7, 0.7), (0.62, 1.2), (0.42, 1.35), (0.0, 1.4)],
                       "W_Bronze", 12, center=(x, y, zz), cap_top=True)
    dais.transform(0, Matrix.Translation((0, DAIS_Y, 0)))
    hall.extend(dais)
    K.emit(hall, "Hall", mats, "arch")
    # ---- people -----------------------------------------------------------------------------------
    crowd = MeshBuilder()
    rows = [(-2.55, 0), (-3.95, 1), (2.55, 0), (3.95, 1)]
    n = 11
    for (x0, row) in rows:
        side = -1 if x0 < 0 else 1
        robe = (0 if row == 0 else 1) if side < 0 else (0 if row == 0 else 2)
        for k in range(n):
            y = 4.0 + k * 2.25 + row * 0.45
            f = official(random.Random(int(abs(x0) * 10) + k * 13), robe)
            d = Vector((-side * 1.0, 0.35, 0.0))
            rz = math.atan2(d.x, -d.y)
            crowd.extend(f, Matrix.Translation((x0 + rng.uniform(-0.04, 0.04), y, 0)) @ Matrix.Rotation(rz, 4, "Z"))
    # palace guards in armour with halberds by the dais steps
    for sx in (-1, 1):
        for y in (DAIS_Y - 8.0, DAIS_Y - 4.6):
            f = MeshBuilder()
            P.figure(f, random.Random(int(y) + sx * 7), "stand", "armored", cloth=0, cloth2=3,
                     weapon="halberd", hat="helmet_plume", jitter=1.0)
            crowd.extend(f, Matrix.Translation((sx * 7.2, y, 0.0 if y < DAIS_Y - 6 else 0.8)) @
                         Matrix.Rotation(-sx * math.pi / 2, 4, "Z") @ Matrix.Scale(1.04, 4))
    # the sovereign on the throne
    f = MeshBuilder()
    P.figure(f, random.Random(3), "sit", "noble", cloth=4, cloth2=0, hat="crown", jitter=0)
    crowd.extend(f, Matrix.Translation((0, DAIS_Y + 0.55, tz + 0.12)) @ Matrix.Scale(1.12, 4))
    # two attendants with fly-whisks beside the throne
    for sx in (-1, 1):
        f = MeshBuilder()
        P.figure(f, random.Random(40 + sx), "stand_hands", "robe", cloth=6, cloth2=9, hat="topknot", jitter=1)
        crowd.extend(f, Matrix.Translation((sx * 2.3, DAIS_Y + 1.2, tz)) @ Matrix.Rotation(math.pi + sx * 0.4, 4, "Z") @ Matrix.Rotation(math.pi, 4, "Z"))
    # an official kneeling before the dais, presenting a memorial
    f = MeshBuilder()
    P.figure(f, random.Random(77), "kneel_bow", "official", cloth=0, cloth2=9, hat="official", jitter=0)
    crowd.extend(f, Matrix.Translation((0.0, DAIS_Y - 9.4, 0.03)) @ Matrix.Rotation(math.pi, 4, "Z"))
    K.emit(crowd, "Court", mats, "fig")
    cam = L.camera((0.0, -6.0, 5.6), (0.0, 30.0, 5.6), focal_mm=27.0, shift=(0.0, 0.02))
    look = dict(
        fade=dict(d0=14.0, d1=70.0, color=GB.mixc("silk", "#E8D8C0", 0.5), amount=0.28, cover=0.0),
        ink=1.0, granulation=0.09,
    )
    return dict(camera=cam, look=look, crease_deg=135.0,
                notes="symmetrical; throne at the centre (x 50%, y ~52%); no UI keep-out")
