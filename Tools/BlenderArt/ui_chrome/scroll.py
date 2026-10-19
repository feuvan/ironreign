"""Scroll.png (1024x640, 9-slice with 80 px margins): the event dialog as an unrolled hand
scroll (手卷) - a silk painting ground (画心) in a brocade mount, between two turned wooden
rollers.

Plate (numpy, flat emission pass), target px of the @1x art:
    mount       silk x 30-994, y 18-622 (its ends run under the rollers)
    top/bottom  brocade borders y 18-48 / 592-622: azurite twill woven with a row of gold
                xiangyun clouds (祥云, facing pairs) and small rosettes, between gold guard
                threads and pearl rows (联珠).  The Slate dialog is always 1040 px wide, so
                these strips stretch by <= 1.02x and may carry a pattern.
    sides       x 31-60 / 964-993: azurite brocade | mud-gold thread | pale celadon 隔水 silk,
                functions of x only (the 9-slice side strips stretch with the dialog height)
    rules       around the window (notched 委角 corners, as Panel.png): mud-gold rule, ink rule,
                ivory 隔水 strip, hairline; a woven rosette in each notch
    field       x 64-960, y 58-582: aged silk (Paper) with a fine weave, slubs and a soft
                ageing mottle (the field stretches <= 1.4x in use), deeper towards the mount
Rollers (Blender 3D, toon + Freestyle): x 7-31 / 993-1017, red-sandalwood rods with
lathe-turned jade caps (y 2-18 / 622-638); unlit toon emission graded by the facing ratio (a
晕染 wash deepening into the outline) with a lengthwise grain, inked by Freestyle (even line,
so the strip stays uniform along y).
Content box (field): x 64-960, y 58-582 at 1024x640; the Slate dialog pads 100/60/100/56.
"""

import math

import numpy as np

from ironart import ui_chrome_gongbi as GB
from ironart import ui_chrome_ornament as O
from ironart import ui_chrome_paint as P
from ironart import ui_chrome_sdf as S
import panel

NAME = "Scroll"
SPEC = dict(size=(1024, 640), ss=4, spp=8, margins=(80, 80, 80, 80), seed=91)
W, H = 1024, 640
MX0, MX1, MY0, MY1 = 30.0, 994.0, 18.0, 622.0      # silk mount
TB = (18.0, 48.0)                                 # top brocade band (y)
WIN = (60.0, 52.0, 964.0, 588.0)                  # window outer edge (gold rule starts here)
NOTCH = 7.0
SIDE_B = (31.0, 45.0)                             # side brocade (x from the left)
SIDE_J = (46.0, 60.0)                             # celadon 隔水 silk
ROLL = dict(cx=19.0, r=12.0, y0=16.0, y1=624.0)   # left roller (the right one is mirrored)
#: Freestyle ink of the rollers (no taper / pressure: the line must not vary along the strip)
INK = dict(thickness_px=1.15, inner_scale=0.5, calligraphy=0.0, pressure_noise=0.0, taper=False,
           crease_angle=118.0, bezier=False, smooth_silhouettes=False)
SEGMENTS = 128

BLUE = "#3E5F7E"
BLUE_DEEP = "#22405C"
THREAD = "#CFAE68"
THREAD_DEEP = "#8E6C34"


def window_dw(G):
    x0, y0, x1, y1 = WIN
    a = P.cheb_box(G, x0, y0 + NOTCH, x1, y1 - NOTCH)
    b = P.cheb_box(G, x0 + NOTCH, y0, x1 - NOTCH, y1)
    return np.minimum(a, b)


# =============================================================================================
# brocade border (top / bottom)
# =============================================================================================
def cloud_band(seed, y0, y1, flip=False):
    """Painted brocade strip y0..y1 (full width) on its own sub-grid: returns (rgba, grid)."""
    ss = SPEC["ss"]
    h = y1 - y0
    Gb = S.Grid(W, h, ss, x0=0.0, y0=y0)
    t = (Gb.Y - y0) if not flip else (y1 - Gb.Y)        # 0 at the outer (mount) edge
    shape = Gb.empty()
    lines = Gb.empty()
    # facing cloud pairs, symmetric about the centre; whole repeats between the window posts
    x_a, x_b = MX0 + 12.0, MX1 - 12.0
    pair = 58.0
    n = max(2, int(round((x_b - x_a) / pair)))
    step = (x_b - x_a) / n
    cy = y0 + (h * 0.52 if not flip else h * 0.48)
    for k in range(n):
        xc = x_a + step * (k + 0.5)
        for sgn in (-1.0, 1.0):
            O.xiangyun(Gb, xc + sgn * step * 0.24, cy, 8.6, flip=(sgn > 0), out_shape=shape,
                       out_lines=lines)
    fig = S.aa_mask(shape, Gb)
    rose_sd = Gb.empty()
    heart = Gb.empty()
    for k in range(n + 1):
        xc = x_a + step * k
        pet, hrt = O.rosette(Gb, xc, cy, 3.6)
        rose_sd = np.minimum(rose_sd, pet)
        heart = np.minimum(heart, hrt)
    # pearl rows (联珠) and guard threads near both edges
    pearls = Gb.empty()
    m = int(round((MX1 - MX0) / 6.0))
    for k in range(m + 1):
        x = MX0 + (MX1 - MX0) * k / m
        for tt in (4.3, h - 4.3):
            yy = y0 + (tt if not flip else h - tt)
            S.sd_circle(Gb, x, yy, 0.95, out=pearls)
    guards = np.minimum(np.abs(t - 2.0) - 0.42, np.abs(t - (h - 2.0)) - 0.42)
    figure_sd = np.minimum(np.minimum(shape, rose_sd), np.minimum(pearls, guards))
    figure = S.aa_mask(figure_sd, Gb)
    contour = S.aa_mask(np.abs(np.minimum(shape, rose_sd)) - 0.6, Gb) * (1.0 - figure)
    col = GB.brocade(Gb, figure, ground=BLUE, ground_deep=BLUE_DEEP, fig=THREAD,
                     fig_deep=THREAD_DEEP, seed=seed, outline=contour * 0.7)
    # 晕染: the band deepens towards both edges (the cloth turning over / under)
    edge = np.minimum(t, h - t)
    col = col * (0.82 + 0.18 * P.smoothstep(0.0, 3.5, edge))[..., None]
    C = P.Canvas(Gb, col)
    C.over(S.aa_mask(lines - 0.30, Gb) * S.aa_mask(shape + 0.45, Gb), BLUE_DEEP, 0.9)
    C.over(S.aa_mask(heart, Gb), GB.mineral(Gb, heart, "#B5382A", "#7E2318", seed=seed + 3,
                                            yun=1.0, gran=0.02, pool=0.0))
    xin = S.aa_mask(np.maximum(MX0 - Gb.X, Gb.X - MX1), Gb)
    C.erase(1.0 - xin)
    del fig
    return C.rgba(), Gb


def paste(C, G, rgba, Gb):
    j0 = int(round(Gb.y0 * G.ss))
    i0 = int(round(Gb.x0 * G.ss))
    sl = (slice(j0, j0 + Gb.ny), slice(i0, i0 + Gb.nx))
    a = rgba[..., 3]
    C.P[sl] = C.P[sl] * (1 - a)[..., None] + rgba[..., :3] * a[..., None]
    C.A[sl] = C.A[sl] * (1 - a) + a


# =============================================================================================
# plate
# =============================================================================================
def paint(G, variant=None, seed=None, rollers_2d=False):
    seed = SPEC["seed"] if seed is None else seed
    C = P.Canvas(G)
    X, Y = G.X, G.Y
    mount = S.aa_mask(P.cheb_box(G, MX0, MY0, MX1, MY1), G)
    dw = window_dw(G)

    # ---- silk field: woven aged silk, deeper under the mount --------------------------------
    field = GB.silk_ground(G, seed, light="#EBDFC4", dark="#DCCBA3", weave=0.022, mottle=0.30,
                           mottle_cell=110.0, stain=0.18, foxing=0.0)
    # keep the field on the Paper token on average (text contrast, QA)
    field = field * (P.rgb("paper") / field[G.ny // 4: 3 * G.ny // 4, G.nx // 4: 3 * G.nx // 4]
                     .reshape(-1, 3).mean(0))
    age = (1.0 - P.smoothstep(0.0, 22.0, -dw)) ** 1.6
    field = P.mix(field, field * P.rgb("#D2BC90") / P.rgb("paper"), 0.6 * age)
    C.over(mount, field)

    # ---- side bands (functions of x only) ---------------------------------------------------
    xl = np.minimum(X - MX0, MX1 - X) + MX0                  # x measured from the left end
    vert = (np.abs(Y - H / 2.0) < (H / 2.0 - TB[1])).astype(np.float32)
    # celadon 隔水 silk all around the window (under the rules), then the side brocade
    jt = np.minimum(xl - SIDE_J[0], np.abs(Y - H / 2.0) * -1.0 + (H / 2.0 - TB[1]))
    jcol = P.mix("#A9B9A3", "#C8D3BE", P.smoothstep(0.0, 3.5, jt))
    jthr = GB.strip_threads(xl, seed + 4, pitch=0.42, amp=0.025, gap=0.4, slow=0.01)
    jcol = jcol * jthr[..., None]
    C.over(S.aa_mask(-dw, G) * GB.band(xl, SIDE_J[0], 999.0, G) * mount * vert, jcol)
    sb = GB.band(xl, SIDE_B[0], SIDE_B[1], G) * mount * vert
    tb = np.minimum(xl - SIDE_B[0], SIDE_B[1] - xl)
    bcol = P.mix(BLUE_DEEP, BLUE, P.smoothstep(0.0, 2.6, tb) ** 0.8)
    bcol = bcol * GB.strip_threads(xl, seed + 3, pitch=0.42, amp=0.06, gap=0.45, slow=0.02,
                                   slow_period=1.6)[..., None]
    C.over(sb, bcol)
    gold = GB.mud_gold(G, None, seed + 5, gran=0.0, flecks=0.0)
    C.over(GB.band(xl, SIDE_B[1], SIDE_J[0], G) * mount * vert, gold)
    C.over(GB.band(xl, SIDE_B[0] - 0.6, SIDE_B[0], G) * mount * vert, "#1E1A16")

    # ---- window rules (as Panel.png) ---------------------------------------------------------
    gthr = GB.strip_threads(dw, seed + 6, pitch=0.5, amp=0.04, gap=0.2)
    C.over(GB.band(-dw, 0.0, 1.0, G) * mount, gold * gthr[..., None])
    C.over(GB.band(-dw, 1.0, 2.0, G), "#2A2119")
    C.over(GB.band(-dw, 2.0, 5.0, G), P.rgb("#EFE6D0")
           * GB.strip_threads(dw, seed + 7, pitch=0.4, amp=0.012, gap=0.3, slow=0.0)[..., None])
    C.over(GB.band(-dw, 5.0, 5.5, G), "#6B5844", 0.75)

    # ---- brocade borders (top / bottom) -----------------------------------------------------
    for flip, (y0, y1) in ((False, TB), (True, (H - TB[1], H - TB[0]))):
        rgba, Gb = cloud_band(seed + (20 if not flip else 30), y0, y1, flip)
        paste(C, G, rgba, Gb)
    # ink binding along the mount's top and bottom edges
    yb = np.broadcast_to(Y, G.shape)
    C.over((GB.band(yb, MY0 - 0.5, MY0 + 0.6, G) + GB.band(yb, MY1 - 0.6, MY1 + 0.5, G))
           * mount, "#1E1A16")
    # brocade blocks filling the window notches
    x0, y0, x1, y1 = WIN
    for (x, y) in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        cxn = x + (NOTCH / 2.0 if x < W / 2 else -NOTCH / 2.0)
        cyn = y + (NOTCH / 2.0 if y < H / 2 else -NOTCH / 2.0)
        Cs = GB.subcanvas(C, cxn - 6.0, cyn - 6.0, cxn + 6.0, cyn + 6.0)
        sq = P.cheb_box(Cs.G, cxn - NOTCH / 2.0, cyn - NOTCH / 2.0, cxn + NOTCH / 2.0,
                        cyn + NOTCH / 2.0)
        Cs.over(S.aa_mask(sq, Cs.G), P.rgb(BLUE_DEEP) * 1.05)
        panel.woven_rosette(Cs, Cs.G, cxn, cyn, 3.0, seed + 40)
    if rollers_2d:
        roller_2d(C, G, seed)
    return C.rgba()


def paint_lookdev(G, variant=None):
    """numpy-only look-dev: the plate with flat stand-ins for the 3D rollers."""
    return paint(G, variant, rollers_2d=True)


def roller_2d(C, G, seed):
    """numpy stand-in for the Blender rollers (look-dev only): a painted cylinder."""
    for side in (0, 1):
        cx = ROLL["cx"] if side == 0 else W - ROLL["cx"]
        r = ROLL["r"]
        Cs = GB.subcanvas(C, cx - r - 2, 0, cx + r + 2, H)
        Gs = Cs.G
        yb = np.broadcast_to(Gs.Y, Gs.shape)
        body = S.aa_mask(np.abs(Gs.X - cx) - r, Gs) * GB.band(yb, ROLL["y0"], ROLL["y1"], Gs)
        f = np.clip(np.abs(Gs.X - cx) / r, 0, 1)
        col = P.mix(P.mix("#9C6B4A", "#5E3426", P.smoothstep(0.0, 0.6, f)), "#29150E",
                    P.smoothstep(0.6, 1.0, f))
        Cs.over(body, col)
        Cs.over(S.aa_mask(np.abs(np.abs(Gs.X - cx) - r) - 0.6, Gs)
                * GB.band(yb, ROLL["y0"], ROLL["y1"], Gs), "#1E1A16")
        for yc in (10.0, H - 10.0):
            e = np.sqrt(((Gs.X - cx) / 11.0) ** 2 + ((Gs.Y - yc) / 7.0) ** 2)
            Cs.over(S.aa_mask((e - 1.0) * 7.0, Gs), "#9DBFA4")
            Cs.over(S.aa_mask(np.abs(e - 1.0) * 7.0 - 0.6, Gs), "#1E1A16")


# =============================================================================================
# Blender: the rollers
# =============================================================================================
def _lathe(name, profile, mat_for, mats, segments=SEGMENTS):
    """Mesh revolved about the image-y axis.  ``profile`` = [(y_px, r_px), ...] from one end to
    the other; each face gets material index ``mat_for(y_mid)``.  Built in world orientation
    (image y down = world -Y), normals recalculated outwards."""
    import bmesh
    import bpy
    bm = bmesh.new()
    rows = []
    for (y, r) in profile:
        row = []
        for k in range(segments):
            a = 2 * math.pi * k / segments
            row.append(bm.verts.new((r * math.cos(a) * 0.001, -y * 0.001, r * math.sin(a) * 0.001)))
        rows.append(row)
    for i in range(len(profile) - 1):
        mi = mat_for(0.5 * (profile[i][0] + profile[i + 1][0]))
        for k in range(segments):
            f = bm.faces.new((rows[i][k], rows[i][(k + 1) % segments],
                              rows[i + 1][(k + 1) % segments], rows[i + 1][k]))
            f.material_index = mi
            f.smooth = True
    for row, y in ((rows[0], profile[0][0]), (rows[-1], profile[-1][0])):
        f = bm.faces.new(row)
        f.material_index = mat_for(y)
        f.smooth = True
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    return bpy.data.objects.new(name, me)


#: turned jade cap profile from its tip (y, r) in image px; the wood collar follows
CAP = [(2.0, 0.5), (2.3, 3.6), (2.9, 6.4), (3.9, 8.6), (5.3, 10.0), (7.0, 10.6), (8.8, 10.6),
       (9.2, 10.15), (9.6, 10.6), (12.6, 10.6), (13.3, 9.8), (13.7, 9.8)]
COLLAR = [(13.75, 13.0), (15.4, 13.0), (15.9, 12.4), (16.0, 12.0)]


def roller_profile():
    """(y, r) rows from the top tip of the jade cap to the bottom tip (image px)."""
    y0, y1, r = ROLL["y0"], ROLL["y1"], ROLL["r"]
    top = CAP + COLLAR
    prof = list(top) + [(y0 + 4.0, r), (H / 2.0, r), (y1 - 4.0, r)]
    prof += [(H - y, rr) for (y, rr) in reversed(top)]
    return prof


def roller_mat(y):
    """0 = wood (rod and collars), 1 = jade (the caps)."""
    return 1 if (y < 13.72 or y > H - 13.72) else 0


def extras(variant, G):
    """Blender: two lathe-turned rollers, toon emission + Freestyle ink (roller collection)."""
    import bpy
    from ironart import ui_chrome_flat as F
    wood = F.toon_material("ToonWood", None, None, None, stops=[
        (0.0, "#8E5A3C"), (0.12, "#76452F"), (0.45, "#5A2E21"), (1.0, "#26130D")])
    # fine lengthwise grain on the wood (painted dark streaks along the rod)
    nt = wood.node_tree
    ramp = [n for n in nt.nodes if n.type == "VALTORGB"][0]
    em = [n for n in nt.nodes if n.type == "EMISSION"][0]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (900.0, 0.0, 900.0)   # grain along the rod only
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 3.0
    nz.inputs["Detail"].default_value = 4.0
    mul = nt.nodes.new("ShaderNodeMixRGB")
    mul.blend_type = "MULTIPLY"
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = 0.35
    mr.inputs["From Max"].default_value = 0.65
    mr.inputs["To Min"].default_value = 0.80
    mr.inputs["To Max"].default_value = 1.0
    L = nt.links
    L.new(tc.outputs["Object"], mp.inputs["Vector"])
    L.new(mp.outputs["Vector"], nz.inputs["Vector"])
    L.new(nz.outputs["Fac"], mr.inputs["Value"])
    L.new(ramp.outputs["Color"], mul.inputs[1])
    L.new(mr.outputs["Result"], mul.inputs[2])
    mul.inputs["Fac"].default_value = 1.0
    L.new(mul.outputs["Color"], em.inputs["Color"])
    jade = F.toon_material("ToonJade", None, None, None, stops=[
        (0.0, "#DCE8D4"), (0.20, "#B6CFB5"), (0.58, "#8DB096"), (1.0, "#4C7260")])
    col = bpy.data.collections.new("Rollers")
    bpy.context.scene.collection.children.link(col)
    prof = roller_profile()
    for side in (0, 1):
        ob = _lathe("Roller%d" % side, prof, roller_mat, [wood, jade])
        cx = ROLL["cx"] if side == 0 else W - ROLL["cx"]
        # mesh y = -image y; lift it a radius above the plate so its silhouette is clear of it
        ob.location = ((cx - W / 2.0) * 0.001, (H / 2.0) * 0.001, (ROLL["r"] + 1.0) * 0.001)
        col.objects.link(ob)
        ob.visible_shadow = False
    F.ink(col, **INK)
