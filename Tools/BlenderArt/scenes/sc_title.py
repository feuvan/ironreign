"""Title background: a mountain fortress city at golden hour above a misty river valley.

Composition (1920x1080, master 3840x2160): the city climbs a terraced massif in the right
half (walls, gate towers, hundreds of houses, a palace with gilt roofs on the summit, a tall
pagoda on the left shoulder, banners along the walls); the river winds through the valley in
front of it, mist lies in the valley, layered ranges fade into the warm haze; the left ~40 %
is calm (glowing sky, soft distant ridges, mist) for the menu; the top centre is open sky for
the logo.  Sun low ahead-left (golden rim on the city, long shadows to the right).
"""

import math
import random

import numpy as np
from mathutils import Vector

from ironart import scenes_arch as A
from ironart import scenes_flora as F
from ironart import scenes_look as L
from ironart import scenes_people as P
from ironart import scenes_sky as S
from ironart import scenes_terrain as T
from ironart import world_kit as WK
from ironart.geometry import MeshBuilder

SPEC = dict(name="Title", art="Art/UI/Title_Background.png", master="UI/Title_Background@2x.png",
            size=(3840, 2160), ss=1, spp=64, preview_spp=16, seed=7)

SUN = (194.0, 13.0)
CITY = (700.0, 2250.0)
RIVER = [(-2600, 3700), (-1700, 3150), (-900, 2450), (-300, 1850), (250, 1560), (800, 1560),
         (1350, 1680), (2000, 1450), (2700, 1300), (3600, 1400)]


# ---------------------------------------------------------------------------------------------
# terrain
# ---------------------------------------------------------------------------------------------
def massif(X, Y):
    """The city hill: a rounded mountain (rounded summit, steepest mid-slope) carved into many
    small terraces (9 m steps), a cliff under the pagoda knoll on the left."""
    cx, cy = CITY
    w = (T.fbm2(X, Y, 260.0, 3, seed=3) - 0.5)
    dx = (X - cx) / 520.0
    dy = (Y - cy) / 380.0
    r = np.sqrt(dx * dx + dy * dy) + w * 0.18
    prof = np.cos(np.clip(r, 0.0, 1.0) * math.pi / 2) ** 1.35
    h = 250.0 * prof
    # pagoda knoll on the left shoulder
    kx, ky = 470.0, 2170.0
    kd = ((X - kx) / 110.0) ** 2 + ((Y - ky) / 90.0) ** 2
    h = np.maximum(h, 236.0 * np.exp(-kd * 1.2) + 0.0 * X)
    # terraces: flat steps with short steep risers (retaining walls)
    step = 9.0
    t = h / step
    fr = t - np.floor(t)
    q = (np.floor(t) + T.smoothstep(0.78, 1.0, fr)) * step
    city = T.smoothstep(1.0, 0.85, r)
    h = q * 0.8 * city + h * (1 - 0.8 * city)
    rk = T.ridged2(X, Y, 50.0, 3, seed=5)
    h += (rk - 0.5) * 5.0 * (1 - city)
    return h


def height(X, Y):
    """Global height function (m)."""
    base = 3.0 + 7.0 * T.fbm2(X, Y, 420.0, 4, seed=1)
    # surrounding hills: high on the far left, lower behind / right of the city
    hills = T.ridged2(X, Y, 520.0, 6, sharp=1.6, seed=2, warp=300.0)
    left = T.smoothstep(-300.0, -1400.0, X) * T.smoothstep(900.0, 2200.0, Y)
    back = T.smoothstep(2900.0, 4000.0, Y)
    right = T.smoothstep(1500.0, 2600.0, X) * T.smoothstep(1600.0, 2600.0, Y)
    hm = hills * (380.0 * left + 260.0 * back + 200.0 * right)
    h = base + hm
    # the city massif
    h = np.maximum(h, massif(X, Y) + base * 0.5)
    # cliff-top the viewer stands on: plateau ~285 m for y < -70, a cliff to the valley by y ~ 200
    fg = T.smoothstep(120.0, -110.0, Y + 50.0 * (T.fbm2(X, Y, 160.0, 3, seed=12) - 0.5)) \
        * T.smoothstep(-1300.0, -500.0, X) * T.smoothstep(1500.0, 700.0, X)
    rough = T.fbm2(X, Y, 40.0, 5, seed=9)
    h = np.maximum(h, fg * (282.0 + 10.0 * rough) - (1 - fg) * 40.0)
    # rocky promontory on the right of the viewpoint (frames the city)
    pd = ((X - 95.0) / 85.0) ** 2 + ((Y + 20.0) / 75.0) ** 2
    h = np.maximum(h, (262.0 + 30.0 * T.ridged2(X, Y, 35.0, 4, seed=13)) * np.exp(-pd * 1.6) * (pd < 2.2))
    # river channel
    d, _ = T.polyline_dist(X, Y, T.smooth_path(RIVER, 6))
    ch = T.smoothstep(46.0, 14.0, d)
    bank = T.smoothstep(140.0, 40.0, d)
    h = h - bank * np.clip(h - 4.0, 0, None) * 0.85 * (1 - fg)
    h = h - ch * 6.5 * (1 - fg)
    return h.astype(np.float32)


def ranges(seed, y0, y1, x0, x1, step, base, peak, cell, peaks=()):
    """Distant range: ridged detail modulated by a few big massifs ``peaks`` = [(x, width, k)]."""
    def fn(X, Y):
        r = T.ridged2(X, Y, cell, 7, sharp=1.9, seed=seed, warp=cell * 0.6)
        f = T.fbm2(X, Y, cell * 2.0, 3, seed=seed + 3)
        v = (Y - y0) / (y1 - y0)
        prof = np.sin(np.clip(v, 0, 1) * math.pi) ** 0.5
        bump = 0.45 + 0.0 * X
        for (px, pw, k) in peaks:
            bump = bump + k * np.exp(-((X - px) / pw) ** 2)
        h = base + (0.75 * r + 0.25 * f) ** 1.3 * peak * prof * bump
        return h
    return T.field_from(fn, x0, x1, y0, y1, step)


def fields(b, col, P, nz, z):
    """Farmland patchwork on the valley floor (Voronoi plots with darker bunds)."""
    from ironart.scenes_sky import lin4
    v = b.node("ShaderNodeTexVoronoi", voronoi_dimensions="2D", feature="F1")
    v.inputs["Scale"].default_value = 0.011
    v.inputs["Randomness"].default_value = 0.85
    b.link(P, v.inputs["Vector"])
    r = b.sep(v.outputs["Color"])[0]
    fc = b.ramp(r, [(0.0, lin4("#5E7034")), (0.22, lin4("#7E8A40")), (0.42, lin4("#A89A50")),
                    (0.6, lin4("#8A7A4A")), (0.78, lin4("#6E7E3C")), (0.9, lin4("#B8A060"))],
                interpolation="CONSTANT")
    e = b.node("ShaderNodeTexVoronoi", voronoi_dimensions="2D", feature="DISTANCE_TO_EDGE")
    e.inputs["Scale"].default_value = 0.011
    e.inputs["Randomness"].default_value = 0.85
    b.link(P, e.inputs["Vector"])
    edge = b.smooth(e.outputs["Distance"], 0.012, 0.0)
    m = b.math("MULTIPLY", b.smooth(z, 13.0, 7.0), b.smooth(nz, 0.975, 0.995))
    col = b.mix(col, fc, b.math("MULTIPLY", m, 0.85))
    col = b.mix(col, b.cmul(col, 0.62), b.math("MULTIPLY", edge, m))
    return col


# ---------------------------------------------------------------------------------------------
def build(r):
    import bpy
    pv = r["preview"]
    rng = random.Random(7)
    # ---- sky --------------------------------------------------------------------------------
    S.build(dict(
        stops=[(0.0, "#F2D2AE"), (0.035, "#EAC6A8"), (0.09, "#D2B8B8"), (0.2, "#A8B0C8"),
               (0.42, "#7C94BC"), (1.0, "#4A6694")],
        strength=0.85,
        glows=[dict(dir=SUN, color="#FFB066", lobes=[(3, 0.6), (16, 1.4), (300, 10.0)],
                    horizon=(1.0, 0.07, 1.6))],
        discs=[dict(dir=SUN, radius_deg=0.55, color="#FFF2D8", strength=80.0)],
        clouds=[dict(height=3000, scale=4200, coverage=0.40, softness=0.22, lit="#FFDAB0",
                     shadow="#8E8494", rim_color="#FFE4B8", rim=1.6, rim_power=3.0, opacity=0.85,
                     stretch=(1.0, 0.55), fade=0.16, shade=7.0, detail=7, seed=2.0, haze=0.6),
                dict(height=8000, scale=9000, coverage=0.28, softness=0.32, lit="#FFE6CC",
                     shadow="#B4A6B4", rim=0.8, rim_power=3.0, opacity=0.5, stretch=(1.0, 0.3),
                     fade=0.2, detail=5, seed=7.0, haze=0.5)],
        light=dict(strength=0.5, tint="#D0D8F0"),
        fog=dict(haze=5.5e-5, haze_falloff=0.0006, haze_h0=0.0, haze_max=0.9, haze_tint="#C8C4C8",
                 haze_zmax=0.1, mist=0.00045, mist_falloff=0.022, mist_h0=0.0, mist_max=0.55,
                 mist_color="#C8BCB8", mist_strength=1.0),
    ))
    S.sun(SUN[0], SUN[1], energy=6.5, color="#FFC890", angle_deg=0.8)
    # ---- terrain ----------------------------------------------------------------------------
    gm = T.terrain_material("TitleGround", grass=("#4E6634", "#7A7E3E"), dry="#A08A52",
                            dirt="#7A6648", rock=("#6A645C", "#968E80"), slope=(0.72, 0.86),
                            grass_scale=0.008, dry_amt=0.45, extra=fields)
    step_v = 8.0 if pv else 4.0
    step_f = 4.0 if pv else 2.0
    valley = T.field_from(height, -2400.0, 3600.0, 690.0, 4400.0, step_v)
    valley.build("Valley", gm)
    near = T.field_from(height, -1000.0, 1300.0, -320.0, 700.0, step_f)
    near.build("Near", gm)
    rmat = T.terrain_material("TitleRange", grass=("#56683E", "#6E7446"), dry="#8A8058",
                              rock=("#5E5C5A", "#8A8680"), slope=(0.74, 0.86), grass_scale=0.002,
                              snow="#E8E6E2", snow_h=(1500, 1900))
    for i, (y0, y1, base, peak, cell, step, pk) in enumerate([
            (4200, 7600, 30, 420, 700, 20, [(-2600, 900, 0.9), (2300, 700, 0.5), (4200, 1200, 0.8)]),
            (7000, 12500, 0, 1000, 1300, 40, [(-5200, 1500, 1.0), (-1500, 900, 0.5), (4800, 1600, 0.9)]),
            (11500, 21000, -100, 1900, 2200, 70, [(-9500, 2600, 0.9), (-3200, 1800, 0.7), (9000, 2600, 0.8)]),
            (19000, 34000, -200, 2800, 3600, 120, [(-14000, 4000, 0.8), (13000, 4500, 0.9)])]):
        f = ranges(30 + i, y0, y1, -9000 - i * 5000, 11000 + i * 5000, step * (2 if pv else 1),
                   base, peak, cell, pk)
        f.build("Range%d" % i, rmat)
    # water
    wm = T.water_material("TitleRiver", deep="#3A4C58", shallow="#6E8088", roughness=0.03,
                          ripple=0.12, ripple_scale=0.08, stretch=(1.0, 6.0))
    T.plane("River", -3000, 4000, 700, 4400, 1.2, wm)
    # ---- city -------------------------------------------------------------------------------
    wk = A.wk_materials()
    pm = P.materials(banners=["#A8261E", "#C8962E", "#8E1E18", "#B03A22"])
    mats = dict(wk)
    mats.update(pm)
    city = MeshBuilder()
    cx, cy = CITY

    def gz(x, y):
        return valley.z(x, y)

    # outer wall ring (front gate at the south)
    ring = []
    for k in range(73):
        a = -math.pi / 2 + math.tau * k / 72
        rr = 1.0 + 0.06 * math.sin(3 * a + 1.0) + 0.04 * math.sin(5 * a)
        ring.append((cx + math.cos(a) * 470 * rr, cy + math.sin(a) * 345 * rr))
    gate_i = 0
    for k in range(len(ring) - 1):
        (x0, y0), (x1, y1) = ring[k], ring[k + 1]
        if k in (0, 71):
            continue                         # the gate stands here
        L_ = math.hypot(x1 - x0, y1 - y0)
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        z = min(gz(x0, y0), gz(x1, y1), gz(mx, my))
        s0 = city.n
        WK.wall_segment(city, L_ + 1.5, 13.0, 9.0, skirt=12.0)
        ang = math.atan2(y1 - y0, x1 - x0)
        city.transform(s0, WK.T(mx, my, z, ang))
    gx, gy = ring[0]
    gzz = gz(gx, gy)
    s0 = city.n
    top = WK.gate_base(city, 40, 22, 15, 7, 9, skirt=12.0)
    city.transform(s0, WK.T(gx, gy, gzz, 0.0))
    WK.hall(city, (gx, gy, gzz + top), WK.HallSpec(bays=(5, 2), double=True, plat_h=0.0, steps=False,
                                                   bay=4.6, col_h=4.6,
                                                   roof=WK.RoofSpec(beasts=3)))
    # towers every few segments
    for k in range(4, 70, 6):
        x, y = ring[k]
        z = gz(x, y)
        s0 = city.n
        t2 = WK.gate_base(city, 12, 12, 16, 0.1, 0.1, doors=False, skirt=12.0)
        a = math.atan2(y - cy, x - cx) + math.pi / 2
        city.transform(s0, WK.T(x, y, z, a))
        WK.hall(city, (x, y, z + t2), WK.HallSpec(bays=(3, 3), bay=3.2, col_h=3.6, plat_h=0.0,
                                                  steps=False, brackets=False, front="wall",
                                                  roof=WK.RoofSpec(style="hip_gable", beasts=0)), rz=a)
    # inner (palace) wall on the upper terrace
    inner = []
    for k in range(41):
        a = -math.pi / 2 + math.tau * k / 40
        inner.append((cx + 40 + math.cos(a) * 170, cy + 60 + math.sin(a) * 120))
    for k in range(len(inner) - 1):
        (x0, y0), (x1, y1) = inner[k], inner[k + 1]
        if k in (0, 39):
            continue
        L_ = math.hypot(x1 - x0, y1 - y0)
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        z = min(gz(x0, y0), gz(x1, y1), gz(mx, my))
        s0 = city.n
        WK.wall_segment(city, L_ + 1.0, 8.0, 6.0, skirt=10.0)
        city.transform(s0, WK.T(mx, my, z, math.atan2(y1 - y0, x1 - x0)))
    ix, iy = inner[0]
    s0 = city.n
    t3 = WK.gate_base(city, 26, 14, 10, 5, 6.5, skirt=10.0)
    city.transform(s0, WK.T(ix, iy, gz(ix, iy), 0.0))
    WK.hall(city, (ix, iy, gz(ix, iy) + t3), WK.HallSpec(bays=(5, 2), bay=3.8, col_h=4.0, plat_h=0.0,
                                                          steps=False, roof=WK.RoofSpec(mat="W_TileGold",
                                                          ridge_mat="W_RidgeGold", beasts=3)))
    # palace: main hall (double gilt roof, triple terrace) + flanking halls
    px, py = cx + 40, cy + 110
    WK.hall(city, (px, py, gz(px, py) - 1.0), WK.HallSpec(
        bays=(9, 5), bay=5.2, col_h=6.4, plat_h=2.2, tiers=3, balustrade=True, double=True,
        upper_h=3.6, roof=WK.RoofSpec(style="hip", mat="W_TileGold", ridge_mat="W_RidgeGold",
                                      beasts=5, overhang=1.8)))
    for sx in (-1, 1):
        hx, hy = px + sx * 95, py - 30
        WK.hall(city, (hx, hy, gz(hx, hy) - 0.5), WK.HallSpec(
            bays=(5, 3), bay=4.4, col_h=5.0, plat_h=1.4, double=False,
            roof=WK.RoofSpec(mat="W_TileGold", ridge_mat="W_RidgeGold", beasts=3)), rz=sx * 0.12)
    # mid-town halls (temples, yamen)
    for (hx, hy, rz, bays) in ((cx - 170, cy - 90, 0.15, (5, 3)), (cx + 230, cy - 60, -0.2, (5, 3)),
                               (cx - 40, cy - 150, 0.0, (7, 3)), (cx + 120, cy + 230, 0.1, (5, 3))):
        WK.hall(city, (hx, hy, gz(hx, hy) - 0.5), WK.HallSpec(bays=bays, bay=4.0, col_h=4.6,
                                                              plat_h=1.2, double=False), rz=rz)
    # pagoda on the left knoll
    pgx, pgy = 430.0, 2180.0
    WK.pagoda(city, (pgx, pgy, gz(pgx, pgy) - 1.0), tiers=13, R=5.2, base_h=6.5, tier_h=3.4)
    cobj = A.wk_build(city, "City", mats)
    # houses: instanced prototypes on the terraces
    hb = []
    for i in range(10):
        rr_ = random.Random(100 + i)
        w = rr_.uniform(9.0, 14.0)
        d = rr_.uniform(6.0, 8.0)
        h_ = rr_.uniform(3.2, 4.0)
        dark = i % 3 == 0
        hb.append(lambda mb, w=w, d=d, h_=h_, dark=dark: WK.house(
            mb, (0, 0, 0), WK.HouseSpec(w=w, d=d, h=h_, roof=WK.RoofSpec(
                style="gable", overhang=0.75, lift=0.25, flare=0.1, thick=0.2,
                mat="W_TileDark" if dark else "W_Tile", chiwen=False, ridge_ends="curl"))))
    hcol = A.wk_prototypes(hb, mats, "TitleHouses")
    pts = []
    tries = 0
    hr = random.Random(11)
    placed = []
    while len(pts) < (260 if pv else 520) and tries < 20000:
        tries += 1
        a = hr.uniform(0, math.tau)
        rad = math.sqrt(hr.random())
        x = cx + math.cos(a) * 440 * rad
        y = cy + math.sin(a) * 320 * rad
        if math.hypot((x - px) / 150, (y - py) / 110) < 1.0:
            continue
        if math.hypot(x - pgx, y - pgy) < 40:
            continue
        if math.hypot((x - cx - 40) / 175, (y - cy - 60) / 125) < 1.0 and math.hypot((x - cx - 40) / 160, (y - cy - 60) / 112) > 0.86:
            continue
        nz = valley.nz_at(x, y, 3.0)
        if nz < 0.93:
            continue
        if any((x - qx) ** 2 + (y - qy) ** 2 < 15.0 ** 2 for qx, qy in placed):
            continue
        z = gz(x, y)
        placed.append((x, y))
        rot = (math.pi if hr.random() < 0.15 else 0.0) + hr.uniform(-0.12, 0.12) + math.atan2(y - cy, x - cx) * 0.0
        pts.append((x, y, z - 0.6, rot, hr.uniform(0.9, 1.1), hr.randrange(10)))
    F.instance("Houses", pts, hcol)
    # ---- banners along the walls and on the palace ----------------------------------------
    bb = []
    for c in range(3):
        bb.append(lambda mb, c=c: A.banner_pole(mb, random.Random(40 + c), color=c, height=11.0,
                                                cloth=(2.6, 5.0)))
    bcol = F.prototypes(bb, mats, "TitleBanners")
    bpts = []
    for k in range(1, 71, 2):
        x, y = ring[k]
        bpts.append((x, y, gz(x, y) + 13.0, rng.uniform(-0.3, 0.3), 1.0, rng.randrange(3)))
    for k in range(2, 39, 3):
        x, y = inner[k]
        bpts.append((x, y, gz(x, y) + 8.0, rng.uniform(-0.3, 0.3), 0.9, rng.randrange(3)))
    for k in (-1, 1):
        bpts.append((gx + k * 16, gy - 4, gzz + top + 1.0, 0.0, 1.6, 0))
    F.instance("Banners", bpts, bcol)
    # ---- vegetation -------------------------------------------------------------------------
    fm = {"Leaves": F.foliage_material("TLeaves", ("#3E5A2C", "#7A8A3E"), translucency=0.3),
          "LeavesCore": F.foliage_material("TLeavesCore", ("#2E4424", "#4E6230"), core=True, translucency=0.0),
          "Needles": F.foliage_material("TNeedles", ("#25382A", "#44583A"), translucency=0.2),
          "NeedlesCore": F.foliage_material("TNeedlesCore", ("#1E2C22", "#33452E"), core=True, translucency=0.0),
          "Bark": F.bark_material("TBark")}
    tcol = F.prototypes([lambda mb: F.broadleaf(mb, random.Random(1), 14),
                         lambda mb: F.broadleaf(mb, random.Random(2), 11),
                         lambda mb: F.chinese_pine(mb, random.Random(3), 15),
                         lambda mb: F.fir(mb, random.Random(4), 18),
                         lambda mb: F.fir(mb, random.Random(5), 14)], fm, "TitleTrees")
    trng = random.Random(21)
    n_trees = 9000 if pv else 26000
    tp = []
    # forests on the hills (left, behind, right) and along the river banks
    def dens(x, y):
        z = valley.z(x, y)
        d_city = math.hypot((x - cx) / 520, (y - cy) / 390)
        if d_city < 1.0:
            return 0.04
        hill = min(1.0, max(0.0, (z - 25.0) / 60.0))
        n = T.fbm2(np.array([x]), np.array([y]), 260.0, 3, seed=44)[0]
        return hill * (0.25 + 0.75 * (n > 0.45)) + 0.95 * (n > 0.66)
    tp += F.scatter_on(valley, n_trees, trng, (-2400, 3600), (700, 4400),
                       [(0, 3), (1, 2), (2, 2), (3, 2), (4, 2)], scale=(0.8, 1.3), min_nz=0.75,
                       zmin=6.0, density=dens)
    # foreground hill: scattered pines and broadleaf, kept off the left calm zone
    tp += F.scatter_on(near, 500 if pv else 1400, trng, (-1000, 1300), (180, 700),
                       [(0, 2), (2, 3), (3, 1)], scale=(0.8, 1.2), min_nz=0.7,
                       density=lambda x, y: 0.15 + 0.85 * T.smoothstep(-200, 500, x))
    F.instance("Trees", tp, tcol)
    # hero pine framing the right edge + rocks
    hp = MeshBuilder()
    F.chinese_pine(hp, random.Random(77), 24.0, leaves=90, leaf=0.9)
    hpo = hp.build("HeroPine", fm, auto_smooth_deg=None)
    hx, hy = -24.0, -40.0
    hpo.location = (hx, hy, near.z(hx, hy) - 0.5)
    hpo.rotation_euler = (0.0, 0.08, 2.4)
    rm = T.rock_material("TitleRock", ("#5A5550", "#8A8276"), scale=0.15, strata=0.25,
                         moss="#5A6A3A", moss_amt=0.6, vertical=False)
    rb = MeshBuilder()
    from ironart.geometry import rock as rockgeo
    for i in range(16):
        x = hr.uniform(-60, 140)
        y = hr.uniform(-70, 90)
        if x < 10 and y < -20:
            continue
        sz = hr.uniform(2.0, 7.0)
        rockgeo(rb, (x, y, near.z(x, y) - sz * 0.3), sz, random.Random(i), "Rock", flatten=0.55, detail=1)
    rb.build("Rocks", {"Rock": rm})
    # ---- valley mist banks --------------------------------------------------------------------
    for i, (x, y, z, w, h_) in enumerate([(650, 1850, 26, 1600, 140), (-500, 2600, 30, 2200, 160),
                                          (1600, 2600, 40, 2000, 180), (200, 3600, 60, 3800, 260),
                                          (900, 1420, 14, 1200, 60)]):
        mm = T.mist_material("TitleMist%d" % i, "#F2DCC6", strength=1.2, density=0.55,
                             seed=float(i * 3), softness=0.45, stretch=4.0)
        T.card("MistCard%d" % i, (x, y, z), (w, h_), mm)
    # ---- camera -----------------------------------------------------------------------------
    cam = L.camera((-120.0, -150.0, 300.0), (-120 + 2450 * 0.167, -150 + 2450 * 0.986, 108.0),
                   focal_mm=50.0, dof=(2400.0, 22.0))
    return dict(camera=cam, beams=tuple(S.dir_from(*SUN) * 30000.0),
                beams_cfg=dict(ray_length=0.22, strength=0.22, threshold=1.4),
                glow=dict(threshold=1.2, mix=-0.85, size=8),
                grade=dict(saturation=1.06, contrast=1.05, shadows=(0.0, 0.004, 0.02),
                           highlights=(0.025, 0.008, -0.02), clarity=0.12, vignette=0.22,
                           vignette_center=(0.55, 0.5), canvas=0.018, sharpen=0.25))
