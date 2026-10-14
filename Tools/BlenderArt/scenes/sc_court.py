"""Event: Court - the grand throne hall.

From the entrance, down the red carpet between two rows of kneeling officials towards the
throne on its marble dais; colossal red lacquered pillars, a painted coffered ceiling, silk
banners; shafts of late-morning sun slant through the high lattice windows on the left into
incense haze (a real volume), pooling on the polished floor.
"""

import math
import random

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

SPEC = dict(name="Court", art="Art/Events/Court.png", master="Events/Court@2x.png",
            size=(1280, 720), ss=1, spp=160, preview_spp=24, seed=11)

HW = 19.0          # half width of the hall interior
LEN = 64.0         # hall length (y from 0)
H = 17.0           # ceiling height
COLS_Y = [4.0 + 7.5 * i for i in range(8)]
SUN = (200.0, 38.0)   # from the left (west) and above, a little behind the camera


def floor_material():
    """Polished dark 'golden brick' floor: large square tiles, subtle variation, glossy."""
    from ironart.scenes_sky import G, lin4
    from ironart.scenes_terrain import _fin, noise
    mat, nb, created = M.new("CourtFloor")
    if not created:
        return mat
    b = G(nb.tree)
    P_ = nb.node("ShaderNodeNewGeometry").outputs["Position"]
    br = nb.node("ShaderNodeTexBrick")
    br.offset = 0.0
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = 0.012
    br.inputs["Brick Width"].default_value = 1.2
    br.inputs["Row Height"].default_value = 1.2
    br.inputs["Color1"].default_value = lin4("#3A3530")
    br.inputs["Color2"].default_value = lin4("#2C2824")
    br.inputs["Mortar"].default_value = lin4("#1A1714")
    b.link(P_, br.inputs["Vector"])
    n = noise(nb, P_, 0.8, 4, 0.6)
    col = b.mix(br.outputs["Color"], b.cmul(br.outputs["Color"], 1.25), b.smooth(n, 0.4, 0.7))
    rough = b.maprange(n, 0.3, 0.7, 0.08, 0.22)
    p = b.principled(Base_Color=col, Roughness=rough, Specular_IOR_Level=0.55,
                     Normal=b.bump(br.outputs["Fac"], 0.2, 0.01))
    return _fin(mat, nb, p.outputs[0])


def carpet_material():
    from ironart.scenes_sky import G, lin4
    from ironart.scenes_terrain import _fin, noise
    mat, nb, created = M.new("CourtCarpet")
    if not created:
        return mat
    b = G(nb.tree)
    P_ = nb.node("ShaderNodeNewGeometry").outputs["Position"]
    x = b.math("ABSOLUTE", b.sep(P_)[0])
    border = b.smooth(x, 1.55, 1.6)
    inner = b.smooth(x, 1.35, 1.4)
    col = b.mix(lin4("#7A1A14"), lin4("#B08A3A"), b.math("SUBTRACT", inner, border))
    col = b.mix(col, lin4("#5A1210"), border)
    # woven medallions along the run
    w = nb.node("ShaderNodeTexWave", wave_type="RINGS")
    w.inputs["Scale"].default_value = 0.4
    w.inputs["Distortion"].default_value = 2.0
    b.link(b.vmath("MULTIPLY", P_, b.vec((1.0, 0.5, 1.0))).outputs[0], w.inputs["Vector"])
    col = b.mix(col, b.cmul(col, 1.18), b.math("MULTIPLY", b.smooth(w.outputs["Fac"], 0.6, 0.9),
                                               b.math("SUBTRACT", 1.0, inner)))
    n = noise(nb, b.vmath("SCALE", P_, scale=40.0).outputs[0], 1.0, 3, 0.5)
    p = b.principled(Base_Color=col, Roughness=0.9, Sheen_Weight=0.6, Sheen_Roughness=0.3,
                     Normal=b.bump(n, 0.2, 0.005))
    return _fin(mat, nb, p.outputs[0])


def screen_material():
    """Gilt dragon-and-cloud screen behind the throne: gold with embossed swirls."""
    from ironart.scenes_sky import G, lin4
    from ironart.scenes_terrain import _fin, noise
    mat, nb, created = M.new("CourtScreen")
    if not created:
        return mat
    b = G(nb.tree)
    P_ = nb.node("ShaderNodeNewGeometry").outputs["Position"]
    w = nb.node("ShaderNodeTexWave", wave_type="RINGS", rings_direction="SPHERICAL")
    w.inputs["Scale"].default_value = 0.9
    w.inputs["Distortion"].default_value = 9.0
    w.inputs["Detail"].default_value = 4.0
    b.link(b.vmath("MULTIPLY", P_, b.vec((1.0, 1.0, 1.4))).outputs[0], w.inputs["Vector"])
    f = b.smooth(w.outputs["Fac"], 0.45, 0.7)
    col = b.mix(lin4("#6A4A1A"), lin4("#D2A448"), f)
    p = b.principled(Base_Color=col, Metallic=0.9, Roughness=b.maprange(f, 0, 1, 0.45, 0.25),
                     Normal=b.bump(f, 0.6, 0.02))
    return _fin(mat, nb, p.outputs[0])


def build(r):
    import bpy
    pv = r["preview"]
    rng = random.Random(11)
    # world: bright daylight outside (seen through the door behind the camera = cool fill)
    S.build(dict(stops=[(0.0, "#C8D4E0"), (0.3, "#9AB0CC"), (1.0, "#6A88B0")], strength=1.2,
                 glows=[dict(dir=SUN, color="#FFE8C8", lobes=[(8, 1.0)])],
                 light=dict(strength=0.9, tint="#B8C8E8"),
                 fog=dict(haze=0.0, mist=0.0)))
    sun = S.sun(SUN[0], SUN[1], energy=9.0, color="#FFDDB0", angle_deg=0.6)
    wk = A.wk_materials()
    pm = P.materials(cloth=["#7A1E1A", "#2A3A5E", "#2E4A3A", "#1E1C1A", "#6A4A2A", "#D6C8A8",
                            "#4A2A3E", "#8A6A2A", "#3A2A20", "#C8B890", "#A0281E", "#20304A"],
                     banners=["#A8221A", "#C89A38", "#1E2A44", "#E6D8B8"])
    mats = dict(wk)
    mats.update(pm)
    mats["Floor"] = floor_material()
    mats["Carpet"] = carpet_material()
    mats["Screen"] = screen_material()
    mats["Ceiling"] = mats["W_BeamPaint"]
    hall = MeshBuilder()
    # floor + carpet
    hall.box((0, LEN / 2 - 6, -0.3), (HW * 2 + 6, LEN + 20, 0.3), "Floor")
    hall.box((0, 24, 0.0), (3.2, 50.0, 0.025), "Carpet")
    # walls: left wall with tall lattice window openings, right wall solid with lattice panels
    win_y = [7.5 + 7.5 * i for i in range(7)]
    for side in (-1, 1):
        x = side * (HW + 0.5)
        # wall pieces between openings
        ys = [-6.0] + sum([[wy - 2.2, wy + 2.2] for wy in win_y], []) + [LEN]
        for k in range(0, len(ys), 2):
            y0, y1 = ys[k], ys[k + 1]
            hall.box((x, (y0 + y1) / 2, 0), (1.0, y1 - y0, H), "W_RedWall")
        for wy in win_y:
            hall.box((x, wy, 0), (1.0, 4.4, 7.0), "W_RedWall")
            hall.box((x, wy, 13.6), (1.0, 4.4, H - 13.6), "W_RedWall")
            if side == 1:
                hall.box((x, wy, 7.0), (0.6, 4.4, 6.6), "W_Lattice")       # closed lattice panel
            else:
                # open lattice: thin bars so the sun streams through
                for k in range(9):
                    hall.box((x, wy - 2.2 + 4.4 * (k + 0.5) / 9, 7.0), (0.25, 0.06, 6.6), "W_WoodDark")
                for k in range(7):
                    hall.box((x, wy, 7.0 + 6.6 * (k + 0.5) / 7), (0.25, 4.4, 0.06), "W_WoodDark")
    # back wall
    hall.box((0, LEN + 0.5, 0), (HW * 2 + 2, 1.0, H), "W_RedWall")
    # front wall with the great door opening behind the camera
    for side in (-1, 1):
        hall.box((side * (HW + 3.5) / 2 + side * 2.5, -6.5, 0), (HW - 3.5, 1.0, H), "W_RedWall")
    hall.box((0, -6.5, 9.0), (8.0, 1.0, H - 9.0), "W_RedWall")
    # ceiling: beams + coffers
    hall.box((0, LEN / 2 - 3, H), (HW * 2 + 2, LEN + 8, 0.6), "W_WoodDark")
    for cy in COLS_Y + [COLS_Y[-1] + 7.5]:
        WK.beam(hall, (-HW, cy), (HW, cy), H - 1.4, 1.4, 0.9, "W_BeamPaint")
    for x in (-13.0, -7.0, 7.0, 13.0):
        WK.beam(hall, (x, -6), (x, LEN), H - 1.1, 1.1, 0.7, "W_BeamPaint")
    for i in range(-8, 9):
        x = i * 2.3
        hall.box((x, LEN / 2 - 3, H - 0.6), (0.18, LEN + 6, 0.6), "W_Bracket")
    for j in range(0, 30):
        y = -5 + j * 2.3
        hall.box((0, y, H - 0.6), (HW * 2, 0.18, 0.6), "W_Bracket")
    # columns: inner rows + outer rows, gilt bands
    for x in (-7.0, 7.0, -13.0, 13.0):
        for y in COLS_Y:
            r = 0.75 if abs(x) < 10 else 0.62
            WK.column(hall, x, y, 0.0, H - 1.0, r, "W_Lacquer", seg=20)
            for z in (1.0, H - 3.2):
                hall.cylinder((x, y, z), (x, y, z + 0.35), r + 0.05, r + 0.05, "W_Gold", 20)
    # dais: three marble terraces with steps and balustrades, throne, screen
    dais = MeshBuilder()
    dz = 0.0
    for t, (w, d, hgt) in enumerate(((24.0, 15.0, 0.85), (17.0, 10.5, 0.85), (10.0, 7.0, 0.85))):
        WK.platform(dais, w, d, hgt, "W_Marble", "W_Marble", z0=dz, skirt=0.2)
        WK.steps(dais, 0, -d / 2 - 5 * 0.36 + 0.02, dz, 4.0, hgt, 5, 0.36, "W_Marble")
        if t < 2:
            WK.balustrade_rect(dais, w - 0.4, d - 0.4, dz + hgt, gap=5.0, mat="W_Marble")
        dz += hgt
    # throne: high-backed chair with gilt crest + footstool
    tz = dz
    dais.box((0, 0.5, tz), (2.6, 1.8, 1.2), "W_Lacquer")
    dais.box((0, 1.25, tz + 1.2), (3.0, 0.35, 2.4), "W_Lacquer")
    dais.box((0, 1.2, tz + 3.6), (3.4, 0.45, 0.5), "W_Gold")
    for sx in (-1, 1):
        dais.box((sx * 1.35, 0.5, tz + 1.2), (0.3, 1.6, 0.9), "W_Gold")
    dais.box((0, -0.7, tz), (2.0, 0.8, 0.35), "W_Lacquer")
    # gilt screen behind (7 panels)
    for k in range(7):
        x = (k - 3) * 1.7
        yk = 3.2 + abs(k - 3) * 0.35
        dais.box((x, yk, tz), (1.66, 0.25, 6.2 - abs(k - 3) * 0.6), "Screen")
        dais.box((x, yk, tz + 6.2 - abs(k - 3) * 0.6), (1.7, 0.35, 0.3), "W_Gold")
    # ceremonial fans on poles and cranes / incense burners
    for sx in (-1, 1):
        dais.cylinder((sx * 4.2, 2.8, tz), (sx * 4.2, 2.8, tz + 6.5), 0.06, 0.06, "W_Gold", 8)
        dais.sphere((sx * 4.2, 2.8, tz + 7.3), 1.0, "W_Lacquer", 16, 6, scale=(1.0, 0.12, 1.15))
        for (x, y, zz) in ((sx * 6.0, -3.0, 0.85 * 2), (sx * 9.5, -6.5, 0.0)):
            dais.lathe([(0.6, 0.0), (0.7, 0.5), (0.9, 0.9), (0.8, 1.6), (0.55, 1.8), (0.0, 1.85)],
                       "W_Bronze" if "W_Bronze" in mats else "W_Iron", 12, center=(x, y, zz), cap_top=True)
    dais.transform(0, Matrix.Translation((0, 52.5, 0)))
    hall.extend(dais)
    # hanging silk banners between the columns
    for x in (-10.0, 10.0):
        for y in COLS_Y[1:-1:2]:
            c = rng.randrange(4)
            s0 = hall.n
            hall.grid(lambda u, v, x=x, y=y: (x + (u - 0.5) * 1.6, y + 0.15 * math.sin(u * 3 + v * 2),
                                              H - 1.6 - v * 8.5), 6, 8, "Banner%d" % c, smooth=True)
    A.wk_build(hall, "Hall", mats)
    # ---- people ----------------------------------------------------------------------------
    crowd = MeshBuilder()
    for side in (-1, 1):
        for row in range(2):
            for k in range(7):
                x = side * (2.6 + row * 2.2) + rng.uniform(-0.15, 0.15)
                y = 6.0 + k * 5.4 + rng.uniform(-0.3, 0.3)
                f = MeshBuilder()
                cl = rng.choice([0, 1, 2, 3, 6, 10, 11])
                P.figure(f, random.Random(k * 7 + row * 3 + side), "kneel_bow", "official",
                         cloth=cl, cloth2=9, hat="official", jitter=4.0)
                crowd.extend(f, Matrix.Translation((x, y, 0)) @ Matrix.Rotation(math.pi + rng.uniform(-0.08, 0.08), 4, "Z"))
    # guards along the outer columns with halberds
    for side in (-1, 1):
        for y in COLS_Y[:6]:
            f = MeshBuilder()
            P.figure(f, random.Random(int(y * 10) + side), "stand", "armored", cloth=1, cloth2=4,
                     weapon="halberd", hat="helmet_plume", jitter=2.0)
            crowd.extend(f, Matrix.Translation((side * 11.2, y + 1.5, 0)) @
                         Matrix.Rotation(-side * math.pi / 2, 4, "Z") @ Matrix.Scale(1.05, 4))
    # the sovereign on the throne
    f = MeshBuilder()
    P.figure(f, random.Random(3), "sit", "noble", cloth=7, cloth2=4, hat="crown", jitter=0)
    crowd.extend(f, Matrix.Translation((0, 53.0, 0.85 * 3 + 0.15)) @ Matrix.Scale(1.1, 4))
    # officials standing on the dais steps
    for sx in (-1, 1):
        f = MeshBuilder()
        P.figure(f, random.Random(20 + sx), "bow_stand", "official", cloth=1 if sx < 0 else 0,
                 cloth2=9, hat="official", weapon=None)
        crowd.extend(f, Matrix.Translation((sx * 3.2, 45.5, 0.0)) @ Matrix.Rotation(math.pi + sx * 0.5, 4, "Z"))
    crowd.build("Court", mats)
    # ---- haze volume (light shafts) + lights -----------------------------------------------
    vm = bpy.data.materials.new("IR_NoFogHaze")
    vm.use_nodes = True
    nt = vm.node_tree
    nt.nodes.clear()
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Color"].default_value = (1.0, 0.92, 0.82, 1)
    vol.inputs["Density"].default_value = 0.022
    vol.inputs["Anisotropy"].default_value = 0.35
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(vol.outputs[0], out.inputs["Volume"])
    mb = MeshBuilder()
    mb.box((0, LEN / 2 - 3, 0.02), (HW * 2 - 0.2, LEN + 5, H - 0.7), "Haze")
    hz = mb.build("Haze", {"Haze": vm})
    # warm candle / lantern glows near the dais, cool fill from the doorway
    for sx in (-1, 1):
        S.point((sx * 6.0, 49.5, 3.6), 600.0, "#FFB060", 0.4)
        S.point((sx * 9.5, 46.0, 2.0), 300.0, "#FFA050", 0.4)
    S.area((0, -8.0, 7.0), (0, 20, 2), power=9000.0, size=8.0, color="#B8C8E8")
    S.area((0, 30, H - 2.5), (0, 30, 0), power=6000.0, size=12.0, color="#FFE0C0", shadow=False)
    cam = L.camera((0.6, -4.5, 2.25), (0.0, 50.0, 3.1), focal_mm=24.0, dof=(30.0, 8.0))
    return dict(camera=cam, beams=None,
                glow=dict(threshold=1.0, mix=-0.8, size=8),
                grade=dict(saturation=1.04, contrast=1.06, shadows=(0.01, 0.0, -0.005),
                           highlights=(0.02, 0.01, -0.015), clarity=0.14, vignette=0.28,
                           canvas=0.018, sharpen=0.3))
