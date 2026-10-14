"""Event: Sect - a cliff temple above the sea of clouds at dawn.

Disciples in pale robes drill sword forms in ranks on a stone terrace at the top of a karst
pillar; across the void a temple of red halls and a pagoda crowns the next pillar, linked by a
plank bridge; more pillars with pines rise from the cloud sea; the sun breaks the horizon on the
left, rose-gold light on every left face, cool blue shadows on the right.
"""

import math
import random

import numpy as np
from mathutils import Matrix, Vector

from ironart import scenes_arch as A
from ironart import scenes_flora as F
from ironart import scenes_look as L
from ironart import scenes_people as P
from ironart import scenes_sky as S
from ironart import scenes_terrain as T
from ironart import world_kit as WK
from ironart.geometry import MeshBuilder

SPEC = dict(name="Sect", art="Art/Events/Sect.png", master="Events/Sect@2x.png",
            size=(1280, 720), ss=1, spp=128, preview_spp=16, seed=51)

SUN = (128.0, 1.6)
CLOUD_Z = 600.0


def pillar(mb, rng, base, top_z, radius, mat="Rock", top_flat=True, flare=0.15, seg=20):
    """Karst pillar from below the cloud sea up to ``top_z``: irregular rings with vertical
    fluting, a slight waist and an overhanging cap; returns the top centre."""
    bx, by = base
    z0 = CLOUD_Z - 120.0
    n = 18
    ph = [rng.uniform(0, math.tau) for _ in range(6)]
    flute = rng.randint(5, 9)
    rings = []
    for i in range(n + 1):
        t = i / n
        z = z0 + (top_z - z0) * t
        rr = radius * (1.0 - 0.18 * math.sin(t * math.pi) + flare * t ** 6)
        ids = []
        for k in range(seg):
            a = math.tau * k / seg
            f = 1.0 + 0.12 * math.sin(flute * a + ph[0] + t * 1.5) + 0.07 * math.sin(3 * a + ph[1]) \
                + 0.05 * math.sin(11 * a + ph[2] + t * 4.0)
            ox = 0.12 * radius * math.sin(t * 3.0 + ph[3])
            oy = 0.12 * radius * math.cos(t * 2.3 + ph[4])
            ids.append(mb.v((bx + ox + math.cos(a) * rr * f, by + oy + math.sin(a) * rr * f, z)))
        rings.append(ids)
    for i in range(n):
        mb.quad_strip(rings[i], rings[i + 1], mat, True, True)
    # cap: domed with a little relief
    top = rings[-1]
    c = mb.v((bx + 0.12 * radius * math.sin(3.0 + ph[3]), by + 0.12 * radius * math.cos(2.3 + ph[4]),
              top_z + (2.0 if top_flat else radius * 0.25)))
    for k in range(seg):
        mb.face((top[k], top[(k + 1) % seg], c), mat, smooth=True)
    return Vector((mb.verts[c].x, mb.verts[c].y, top_z))


def cloud_material():
    """Sea of clouds seen from above: bright translucent tops, rose light on the sun side."""
    from ironart import materials as M
    from ironart.scenes_sky import G, lin4
    from ironart.scenes_terrain import _fin, noise
    mat, nb, created = M.new("CloudSea")
    if not created:
        return mat
    b = G(nb.tree)
    P_ = nb.node("ShaderNodeNewGeometry").outputs["Position"]
    n = noise(nb, P_, 0.004, 6, 0.6, 0.4)
    col = b.mix(lin4("#C8C0CC"), lin4("#F4ECEC"), b.smooth(n, 0.35, 0.7))
    p = b.principled(Base_Color=col, Roughness=1.0, Specular_IOR_Level=0.1,
                     Subsurface_Weight=0.0, Sheen_Weight=0.8, Sheen_Roughness=0.6,
                     Sheen_Tint=lin4("#FFD8D0"), Normal=b.bump(n, 0.4, 2.0))
    tr = nb.node("ShaderNodeBsdfTranslucent")
    b.link(col, tr.inputs["Color"])
    mx = nb.node("ShaderNodeMixShader")
    mx.inputs[0].default_value = 0.35
    b.link(p.outputs[0], mx.inputs[1])
    b.link(tr.outputs[0], mx.inputs[2])
    return _fin(mat, nb, mx.outputs[0])


def build(r):
    import bpy
    pv = r["preview"]
    rng = random.Random(51)
    S.build(dict(
        stops=[(0.0, "#FFD2A0"), (0.025, "#FBB898"), (0.07, "#E8A8B0"), (0.16, "#B0A4C4"),
               (0.38, "#6E80B0"), (1.0, "#2E3E70")],
        strength=1.05,
        glows=[dict(dir=SUN, color="#FFB070", lobes=[(4, 0.9), (30, 2.6), (500, 18.0)],
                    horizon=(1.6, 0.05, 1.8))],
        discs=[dict(dir=SUN, radius_deg=0.8, color="#FFE8C0", strength=70.0)],
        clouds=[dict(height=3500, scale=5200, coverage=0.36, softness=0.26, lit="#FFC8B0",
                     shadow="#7E7090", rim_color="#FFD8B0", rim=2.0, rim_power=4.0, opacity=0.8,
                     stretch=(1.0, 0.4), fade=0.14, shade=7.0, seed=9.0, haze=0.55)],
        light=dict(strength=0.6, tint="#C8D0F0"),
        fog=dict(haze=9e-5, haze_falloff=0.0006, haze_h0=CLOUD_Z, haze_max=0.88, haze_zmax=0.08,
                 mist=0.0, mist_falloff=0.02),
    ))
    S.sun(SUN[0], SUN[1] + 2.0, energy=5.0, color="#FFB884", angle_deg=1.0)
    # ---- cloud sea ----------------------------------------------------------------------------
    def cs(X, Y):
        return CLOUD_Z + 30.0 * T.fbm2(X, Y, 260.0, 5, seed=3) + 14.0 * T.fbm2(X, Y, 60.0, 3, seed=4)
    T.field_from(cs, -6000, 6000, -400, 9000, 30.0 if pv else 16.0).build("CloudSea", cloud_material())
    # ---- pillars -------------------------------------------------------------------------------
    rm = T.rock_material("SRock", ("#6A6058", "#9A8E80"), scale=0.05, strata=0.45, moss="#4E5E36",
                         moss_amt=0.7, vertical=True)
    rocks = MeshBuilder()
    mats = {"Rock": rm}
    # the terrace pillar (camera) and the temple pillar
    tz = 980.0
    terrace_c = pillar(rocks, random.Random(1), (0.0, 20.0), tz, 46.0, flare=0.1)
    temple_c = pillar(rocks, random.Random(2), (150.0, 200.0), 1010.0, 52.0, flare=0.2)
    tops = []
    for i in range(26):
        x = rng.uniform(-1600, 2200)
        y = rng.uniform(250, 3200)
        if math.hypot(x - 150, y - 200) < 140 or math.hypot(x, y - 20) < 130:
            continue
        top = CLOUD_Z + rng.uniform(120, 520) * (1.0 if y < 1500 else 1.3)
        c = pillar(rocks, random.Random(10 + i), (x, y), top, rng.uniform(25, 70), flare=rng.uniform(0.0, 0.3))
        tops.append((c, rng.uniform(25, 60)))
    rocks.build("Pillars", mats)
    # ---- terrace (paving, balustrade) + temple -------------------------------------------------
    wk = A.wk_materials()
    pm = P.materials(cloth=["#E6E0D2", "#C8C0AE", "#8A8478", "#3A3A3E", "#6A2A22", "#D8D0BC",
                            "#4A5A6A", "#A89A80", "#5A4A3A", "#EEE8DC", "#9A3020", "#2E3A4A"])
    mats2 = dict(wk)
    mats2.update(pm)
    ar = MeshBuilder()
    WK.platform(ar, 64.0, 58.0, 2.0, "W_Stone", "W_Paving", z0=terrace_c.z - 0.6, skirt=6.0)
    ar.transform(0, Matrix.Translation((terrace_c.x, terrace_c.y + 6.0, 0)))
    s0 = ar.n
    WK.balustrade_rect(ar, 63.0, 57.0, terrace_c.z + 1.4, gap=0.0, mat="W_Marble")
    ar.transform(s0, Matrix.Translation((terrace_c.x, terrace_c.y + 6.0, 0)))
    # temple on the far pillar
    WK.hall(ar, (temple_c.x + 8, temple_c.y + 18, temple_c.z), WK.HallSpec(
        bays=(5, 3), bay=4.0, col_h=4.6, plat_h=1.6, double=True, upper_h=3.0,
        roof=WK.RoofSpec(style="hip_gable", beasts=3, ridge_ends="curl")), rz=-0.35)
    WK.hall(ar, (temple_c.x - 26, temple_c.y + 4, temple_c.z), WK.HallSpec(
        bays=(3, 2), bay=3.6, col_h=3.8, plat_h=1.0, roof=WK.RoofSpec(style="hip_gable", ridge_ends="curl")),
        rz=0.4)
    WK.pagoda(ar, (temple_c.x + 30, temple_c.y - 12, temple_c.z - 0.5), tiers=7, R=3.6, base_h=4.5, tier_h=2.8)
    A.wk_build(ar, "Temple", mats2)
    # the temple platform must sit at the temple pillar: platform() builds at the origin
    plat = MeshBuilder()
    WK.platform(plat, 92.0, 82.0, 1.2, "W_Stone", "W_Paving", z0=temple_c.z - 0.6, skirt=10.0)
    plat.transform(0, Matrix.Translation((temple_c.x, temple_c.y + 4, 0)))
    A.wk_build(plat, "TemplePlat", mats2)
    # plank bridge between the pillars (sagging)
    br = MeshBuilder()
    a = Vector((terrace_c.x + 30, terrace_c.y + 26, terrace_c.z + 1.0))
    b = Vector((temple_c.x - 40, temple_c.y - 26, temple_c.z + 0.8))
    for i in range(60):
        t = i / 59
        p = a + (b - a) * t - Vector((0, 0, 9.0 * 4 * t * (1 - t)))
        d = (b - a).normalized()
        side = Vector((-d.y, d.x, 0)).normalized()
        br.box(tuple(p), (2.6, 0.5, 0.12), "W_Wood", rot_z=math.atan2(side.y, side.x))
    for sgn in (-1, 1):
        pts = []
        for i in range(25):
            t = i / 24
            d = (b - a).normalized()
            side = Vector((-d.y, d.x, 0)).normalized()
            pts.append(tuple(a + (b - a) * t - Vector((0, 0, 9.0 * 4 * t * (1 - t) - 1.1)) + side * 1.3 * sgn))
        br.tube(pts, 0.05, "Rope", 4, caps=False)
    A.wk_build(br, "Bridge", mats2)
    # ---- vegetation on the pillar tops ---------------------------------------------------------
    fm = {"Needles": F.foliage_material("SNeedles", ("#24342A", "#44583C"), translucency=0.25),
          "NeedlesCore": F.foliage_material("SNeedlesCore", ("#18241C", "#2E3E2A"), core=True, translucency=0.0),
          "Bark": F.bark_material("SBark")}
    tcol = F.prototypes([lambda mb: F.chinese_pine(mb, random.Random(1), 12),
                         lambda mb: F.chinese_pine(mb, random.Random(2), 9),
                         lambda mb: F.chinese_pine(mb, random.Random(3), 15)], fm, "SPines")
    tp = []
    for (c, rad) in tops + [(temple_c, 50.0)]:
        for k in range(int(rad * 0.5)):
            a_ = rng.uniform(0, math.tau)
            d = rad * math.sqrt(rng.uniform(0.3, 1.0)) * 0.95
            x, y = c.x + math.cos(a_) * d, c.y + math.sin(a_) * d
            if (c is temple_c) and d < 42:
                continue
            tp.append((x, y, c.z - 1.0, rng.uniform(0, math.tau), rng.uniform(0.8, 1.4), rng.randrange(3)))
    # pines clinging to the terrace pillar edge
    for k in range(10):
        a_ = rng.uniform(math.pi * 0.1, math.pi * 0.9)
        tp.append((terrace_c.x + math.cos(a_) * 44, terrace_c.y + 6 + math.sin(a_) * 40, terrace_c.z - 6,
                   rng.uniform(0, math.tau), rng.uniform(0.8, 1.2), rng.randrange(3)))
    F.instance("SPines", tp, tcol)
    # ---- disciples ------------------------------------------------------------------------------
    crowd = MeshBuilder()
    poses = ["sword_ready", "guard", "slash_high", "thrust"]
    form = rng.choice(poses)
    for row in range(3):
        for col in range(5):
            x = terrace_c.x - 2.0 + col * 3.4 + rng.uniform(-0.2, 0.2)
            y = terrace_c.y + 2.0 + row * 3.6 + rng.uniform(-0.2, 0.2)
            f = MeshBuilder()
            P.figure(f, random.Random(row * 10 + col), form, "disciple", cloth=0 if (row + col) % 3 else 1,
                     cloth2=3, hat="topknot", weapon="sword", jitter=4.0)
            crowd.extend(f, Matrix.Translation((x, y, terrace_c.z + 1.4)) @ Matrix.Rotation(math.radians(-62), 4, "Z"))
    # the master facing them
    f = MeshBuilder()
    P.figure(f, random.Random(99), "stand_hands", "monk", cloth=3, cloth2=0, hat="topknot")
    crowd.extend(f, Matrix.Translation((terrace_c.x - 12.0, terrace_c.y + 9.0, terrace_c.z + 1.4)) @
                 Matrix.Rotation(math.radians(110), 4, "Z"))
    crowd.build("Disciples", mats2)
    # thin mist wisps around the pillars just above the cloud sea
    for i in range(8):
        x = rng.uniform(-800, 1600)
        y = rng.uniform(300, 2500)
        mm = T.mist_material("SMist%d" % i, "#F2D8D4", strength=1.0, density=0.5, seed=float(i),
                             softness=0.5, stretch=3.5)
        T.card("SMist%d" % i, (x, y, CLOUD_Z + rng.uniform(40, 120)), (rng.uniform(300, 700), rng.uniform(60, 140)), mm)
    cz = terrace_c.z + 1.4 + 2.2
    cam = L.camera((terrace_c.x + 22.0, terrace_c.y - 26.0, cz),
                   (terrace_c.x - 60.0, terrace_c.y + 200.0, cz - 30.0), focal_mm=30.0, dof=(40.0, 11.0))
    return dict(camera=cam, beams=tuple(S.dir_from(*SUN) * 30000.0),
                beams_cfg=dict(ray_length=0.25, strength=0.3, threshold=1.3),
                glow=dict(threshold=1.0, mix=-0.82, size=8),
                grade=dict(saturation=1.05, contrast=1.05, shadows=(-0.005, 0.0, 0.02),
                           highlights=(0.03, 0.01, -0.01), clarity=0.12, vignette=0.24,
                           canvas=0.02, sharpen=0.3))
