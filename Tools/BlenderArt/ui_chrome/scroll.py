"""Scroll.png (1024x640, 9-slice with 80 px margins; the event dialog draws it ~1040 wide with
content padding 100 / 60 / 100 / 56): an unrolled silk handscroll with rosewood rollers capped in
pale jade.

Layout (target px):
    rollers   axes at x 24 / 1000, radius 12: the silk wound on the rod (y 28-612, indigo with
              its gold edge line and dark binding), rosewood rod ends, gold ferrules and pale
              jade knobs (y 4.6-17 and 623-635.4) - real 3D lathe meshes, SSS jade
    sheet     silk from roller to roller, y 30-610
    brocade   indigo silk, a satin xiangyun damask outlined in gold thread: top y 30-54, bottom 586-610,
              left x 36-66, right 958-988; dark binding at the sheet edge
    gold line 1.4 px gold thread + hairline where the brocade meets the writing silk
    field     cream juan silk (Paper), fine weave, aged slightly darker towards the mount
The damask/weave are subtle enough that the 9-slice's mild stretches (1.02 x in width, up to
~1.5 x in height in practice) never show seams.
"""

import math

import numpy as np

import kit
from ironart import ui_chrome_motifs as MO
from ironart import ui_chrome_sdf as S
from ironart.ui_chrome_maps import Maps, L

NAME = "Scroll"
SPEC = dict(size=(1024, 640), ss=3, spp=16, adaptive=0.02, margins=(80, 80, 80, 80), seed=71,
            mesh_step=3)
W, H = 1024, 640
RX = (24.0, 1000.0)
RR = 12.0
SHEET = (24.0, 30.0, 1000.0, 610.0)
BRO = (36.0, 54.0, 988.0, 586.0)          # inner edge of the brocade (x0 is the visible start)
FIELD = (68.0, 56.0, 956.0, 584.0)
CAL_PAPER = (1.0, 1.0, 1.0)


def damask_tile(ss, pw=20.0, ph=14.0):
    """One period of the cloud damask on a local grid: (pattern mask, gold-thread outline)."""
    G = S.Grid(pw, ph, ss)
    sd, eng = MO.cloud(kit.Folded(G.X, G.Y), pw * 0.5, ph * 0.52, 6.6, rot=0.0, tail=True)
    body = S.aa_mask(sd, G) * (1 - 0.8 * S.aa_mask(eng - 0.2, G))
    line = S.aa_mask(np.abs(sd + 0.2) - 0.22, G)
    return body.astype(np.float32), line.astype(np.float32)


def tile_pattern(G, tile, pw, ph, x0, y0):
    """Stagger-tile a local pattern over the whole grid (rows offset by half a period)."""
    th, tw = tile.shape
    ys = ((G.ys - y0) * G.ss).astype(np.int64)
    xs = ((G.xs - x0) * G.ss).astype(np.int64)
    row = np.floor_divide(ys, th)
    out = np.empty(G.shape, np.float32)
    for parity in (0, 1):
        rr = (row % 2) == parity
        xi = np.mod(xs + parity * tw // 2, tw)
        yi = np.mod(ys, th)
        sub = tile[np.ix_(yi[rr], xi)]
        out[rr] = sub
    return out


def build(G, variant=None):
    X, Y = G.X, G.Y
    m = Maps(G.shape, base="#E9DCC0", alpha=0.0)
    sx0, sy0, sx1, sy1 = SHEET
    sheet = (S.band(X, sx0, sx1, G) * S.band(Y, sy0, sy1, G)).astype(np.float32)
    # distance into the sheet from its visible top/bottom edges and from the rollers
    dy = np.minimum(Y - sy0, sy1 - Y)
    bx0, by0, bx1, by1 = BRO
    fx0, fy0, fx1, fy1 = FIELD
    field = (S.band(X, fx0, fx1, G) * S.band(Y, fy0, fy1, G))
    gold_l = (S.band(X, fx0 - 1.9, fx1 + 1.9, G) * S.band(Y, fy0 - 1.9, fy1 + 1.9, G)) - \
             (S.band(X, fx0 - 0.5, fx1 + 0.5, G) * S.band(Y, fy0 - 0.5, fy1 + 0.5, G))
    gold_l = np.clip(gold_l, 0, 1)
    brocade = np.clip(sheet - field - gold_l, 0, 1)

    # ---- brocade: indigo ground + gold-thread damask --------------------------------------------
    body, line = damask_tile(G.ss)
    pat = tile_pattern(G, body, 20.0, 14.0, 6.0, 4.0)
    pline = tile_pattern(G, line, 20.0, 14.0, 6.0, 4.0)
    weave = 0.5 + 0.5 * np.sin(X * math.pi * 2 / 0.5) * np.sin(Y * math.pi * 2 / 0.5)
    ground = dict(base=L("#25324B"), metal=0.0, rough=0.55, coat=0.0, spec=0.4)
    m.paint(brocade, ground)
    m.tint(brocade, 0.95 + 0.08 * weave)
    # damask: the figure is woven satin (lighter, glossier), outlined in a fine gold thread
    satin = dict(base=L("#33456A"), metal=0.0, rough=0.32, coat=0.0, spec=0.6)
    m.paint(brocade * pat, satin)
    m.paint(brocade * pline, dict(base=L("#A88446"), metal=0.6, rough=0.4, coat=0.0, spec=0.5))
    # dark binding along the sheet's top/bottom edge and the roller side
    bind = brocade * (1 - kit.smoothstep(1.2, 2.2, dy))
    m.paint(bind, dict(base=L("#15100C"), metal=0.0, rough=0.55, coat=0.0, spec=0.3))

    # ---- gold thread line ----------------------------------------------------------------------
    m.paint(gold_l, "gold_satin")

    # ---- writing silk ----------------------------------------------------------------------------
    edge = np.minimum(np.minimum(X - fx0, fx1 - X), np.minimum(Y - fy0, fy1 - Y))
    age = 1.0 - kit.smoothstep(0.0, 26.0, edge)
    base = kit.lerp3(L("#E9DCC0"), L("#D6C49E"), age * 0.85) * np.array(CAL_PAPER, np.float32)
    m.paint(field, dict(base=base, metal=0.0, rough=0.62, coat=0.0, spec=0.32))
    tex, rel = kit.xuan(G.shape, G.ss, seed=9, fibre=0.55, formation=1.4)
    silk_weave = 0.5 + 0.25 * np.sin(X * math.pi * 2 / 0.42) + 0.25 * np.sin(Y * math.pi * 2 / 0.42)
    m.tint(field, tex * (0.99 + 0.02 * silk_weave))

    # ---- heights ---------------------------------------------------------------------------------
    z = 0.35 * sheet + 0.05 * brocade * pat + 0.04 * brocade * pline + 0.05 * gold_l + rel * field * 0.6
    # the sheet edges roll slightly (thicker hem)
    z = z + 0.12 * sheet * (1 - kit.smoothstep(0.0, 2.0, dy))
    m.height = z.astype(np.float32)
    m.alpha = sheet.astype(np.float32)
    return m


# =============================================================================================
# rollers (real 3D)
# =============================================================================================
def _mat_rosewood():
    import bpy
    from ironart import palette
    mat = bpy.data.materials.new("RollerWood")
    mat.use_nodes = True
    nt = mat.node_tree
    N, Lk = nt.nodes, nt.links
    p = N["Principled BSDF"]
    tc = N.new("ShaderNodeTexCoord")
    mp = N.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (900.0, 900.0, 18.0)
    Lk.new(tc.outputs["Object"], mp.inputs["Vector"])
    nz = N.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 1.0
    nz.inputs["Detail"].default_value = 6.0
    nz.inputs["Distortion"].default_value = 0.6
    Lk.new(mp.outputs[0], nz.inputs["Vector"])
    rp = N.new("ShaderNodeValToRGB")
    rp.color_ramp.elements[0].position = 0.35
    rp.color_ramp.elements[0].color = palette.lin4("#241009")
    rp.color_ramp.elements[1].position = 0.68
    rp.color_ramp.elements[1].color = palette.lin4("#6E3423")
    Lk.new(nz.outputs["Fac"], rp.inputs[0])
    Lk.new(rp.outputs[0], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.35
    p.inputs["Coat Weight"].default_value = 0.9
    p.inputs["Coat Roughness"].default_value = 0.06
    p.inputs["Specular IOR Level"].default_value = 0.15
    return mat


def _mat_jade():
    import bpy
    from ironart import palette
    mat = bpy.data.materials.new("Jade")
    mat.use_nodes = True
    nt = mat.node_tree
    N, Lk = nt.nodes, nt.links
    p = N["Principled BSDF"]
    tc = N.new("ShaderNodeTexCoord")
    nz = N.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 160.0
    nz.inputs["Detail"].default_value = 5.0
    Lk.new(tc.outputs["Object"], nz.inputs["Vector"])
    rp = N.new("ShaderNodeValToRGB")
    rp.color_ramp.elements[0].position = 0.3
    rp.color_ramp.elements[0].color = palette.lin4("#8FAE8C")
    rp.color_ramp.elements[1].position = 0.75
    rp.color_ramp.elements[1].color = palette.lin4("#C9D8BE")
    Lk.new(nz.outputs["Fac"], rp.inputs[0])
    Lk.new(rp.outputs[0], p.inputs["Base Color"])
    p.inputs["Subsurface Weight"].default_value = 0.6
    p.inputs["Subsurface Radius"].default_value = (1.0, 1.6, 1.0)
    p.inputs["Subsurface Scale"].default_value = 0.003
    p.inputs["Roughness"].default_value = 0.25
    p.inputs["Coat Weight"].default_value = 1.0
    p.inputs["Coat Roughness"].default_value = 0.04
    return mat


def _mat_gold():
    import bpy
    from ironart import palette
    mat = bpy.data.materials.new("Ferrule")
    mat.use_nodes = True
    p = mat.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = palette.lin4("#F0C873")
    p.inputs["Metallic"].default_value = 1.0
    p.inputs["Roughness"].default_value = 0.22
    return mat


def _mat_silk_roll():
    """The silk wound on the roller: the indigo mounting seen edge-on, satin sheen, faint turns."""
    import bpy
    from ironart import palette
    mat = bpy.data.materials.new("SilkRoll")
    mat.use_nodes = True
    nt = mat.node_tree
    N, Lk = nt.nodes, nt.links
    p = N["Principled BSDF"]
    tc = N.new("ShaderNodeTexCoord")
    sep = N.new("ShaderNodeSeparateXYZ")
    Lk.new(tc.outputs["Object"], sep.inputs[0])
    # local z = along the roller (px units): dark binding rings near both ends of the roll
    rp = N.new("ShaderNodeValToRGB")
    cr = rp.color_ramp
    stops = [(0.0, "#141019"), (0.012, "#141019"), (0.02, "#9C7B40"), (0.026, "#9C7B40"),
             (0.034, "#26334D"), (0.966, "#26334D"), (0.974, "#9C7B40"), (0.98, "#9C7B40"),
             (0.988, "#141019"), (1.0, "#141019")]
    while len(cr.elements) < len(stops):
        cr.elements.new(0.5)
    for el, (pos, col) in zip(cr.elements, stops):
        el.position = pos
        el.color = palette.lin4(col)
    mr = N.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = 28.0
    mr.inputs["From Max"].default_value = 612.0
    Lk.new(sep.outputs["Z"], mr.inputs["Value"])
    Lk.new(mr.outputs[0], rp.inputs[0])
    nz = N.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 0.35
    nz.inputs["Detail"].default_value = 4.0
    mp = N.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 1.0, 0.05)
    Lk.new(tc.outputs["Object"], mp.inputs["Vector"])
    Lk.new(mp.outputs[0], nz.inputs["Vector"])
    mx = N.new("ShaderNodeMix")
    mx.data_type = "RGBA"
    mx.blend_type = "MULTIPLY"
    mx.inputs[0].default_value = 0.25
    Lk.new(rp.outputs[0], mx.inputs[6])
    Lk.new(nz.outputs["Color"], mx.inputs[7])
    Lk.new(mx.outputs[2], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.42
    p.inputs["Sheen Weight"].default_value = 0.6
    p.inputs["Sheen Roughness"].default_value = 0.35
    p.inputs["Specular IOR Level"].default_value = 0.35
    return mat


def extras(variant, G):
    """The two rollers: silk wound on a rosewood rod (the roll spans the sheet height), the rod
    ends with gold ferrules and pale jade knobs (lathe meshes, SSS jade)."""
    from mathutils import Matrix
    from ironart import geometry as geo
    from ironart.ui_chrome_render import MM
    mats = {"Silk": _mat_silk_roll(), "Wood": _mat_rosewood(), "Jade": _mat_jade(),
            "Gold": _mat_gold()}
    r = RR
    for k, ax in enumerate(RX):
        mb = geo.MeshBuilder()
        # rolled silk (y 28-612): slightly fuller in the middle, rounded edges
        roll = [(0.0, 28.0), (r - 1.2, 28.0), (r - 0.3, 28.4), (r, 29.4), (r + 0.25, 320.0),
                (r, 610.6), (r - 0.3, 611.6), (r - 1.2, 612.0), (0.0, 612.0)]
        mb.lathe(roll, "Silk", segments=48, smooth=True)
        # rod ends
        for (a, b) in ((17.5, 28.5), (611.5, 622.5)):
            mb.lathe([(0.0, a), (5.6, a), (6.0, a + 0.4), (6.0, b - 0.4), (5.6, b), (0.0, b)],
                     "Wood", segments=32, smooth=True)
        for (z0, z1) in ((17.0, 20.2), (619.8, 623.0)):
            mb.lathe([(0.0, z0), (6.8, z0), (7.4, z0 + 0.5), (7.4, z1 - 0.5), (6.8, z1), (0.0, z1)],
                     "Gold", segments=40, smooth=True)
        cap = [(0.0, 0.0), (5.0, 0.0), (7.6, 0.5), (8.9, 1.6), (9.3, 3.4), (9.3, 7.0),
               (8.7, 7.6), (8.7, 8.4), (9.3, 9.0), (9.3, 11.0), (8.6, 12.2), (7.2, 12.6),
               (0.0, 12.6)]
        top = [(rr, 4.6 + t) for rr, t in cap]                       # knob tip at y 4.6
        bot = [(rr, 635.4 - t) for rr, t in reversed(cap)]           # knob tip at y 635.4
        mb.lathe(top, "Jade", segments=48, smooth=True)
        mb.lathe(bot, "Jade", segments=48, smooth=True)
        ob = mb.build("Roller%d" % k, mats)
        # local z (along the axis) = image y (down) -> world -y; local y -> world z
        ob.matrix_world = (Matrix.Translation(((ax - W / 2) * MM, (H / 2) * MM, r * MM)) @
                           Matrix.Rotation(math.radians(90.0), 4, "X") @
                           Matrix.Diagonal((MM, MM, MM, 1.0)))
    return None
