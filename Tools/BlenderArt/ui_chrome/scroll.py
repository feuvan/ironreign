"""Scroll.png (1024x640, 9-slice with 80 px margins): the event dialog as an unrolled hand
scroll (手卷) - a silk painting ground in a brocade mount, between two painted wooden rollers.

Plate (numpy, flat emission pass):
    mount     silk x 26-998, y 20-620, ink binding along its top and bottom edges
    top/bot   brocade borders y 21-46 / 594-619: azurite woven with a row of mud-gold xiangyun
              clouds (祥云, alternating direction, 22 repeats symmetric about x 512) between
              mud-gold threads and pearl rows (联珠); the dialog is always ~1040 px wide, so
              these strips stretch by <= 1.02x
    sides     x 32-56 / 968-992: azurite silk | mud-gold thread | pale celadon silk, uniform
              along y (the 9-slice side strips stretch with the dialog height)
    window    x 60-964, y 50-590 with square-notched corners (委角, as Panel.png): mud-gold
              rule, ink rule, ivory 隔水 strip, hairline; a mud-gold 柿蒂 flower in each notch
    field     silk (Paper +-2) with weft/warp striation, slubs and soft mottle, an ageing wash
              under the mount
Rollers (Blender 3D, toon + Freestyle): x 6-32 / 992-1018, red-sandalwood rods (radius 13)
with lathe-turned jade caps (y 3-17 / 623-637) and wood collars; unlit toon emission graded by
the facing ratio (a 晕染 wash deepening into the outline) with a fine lengthwise grain, inked
by Freestyle (silhouettes + creases, calligraphy, no taper so the strip stays uniform).
Content box (field): x 64-960, y 54-586 at 1024x640; the Slate dialog pads 100/60/100/56.
"""

import math

import numpy as np

from ironart import ui_chrome_motifs as MO
from ironart import ui_chrome_paint as P
from ironart import ui_chrome_sdf as S
import panel

NAME = "Scroll"
SPEC = dict(size=(1024, 640), ss=4, spp=8, margins=(80, 80, 80, 80), seed=91)
W, H = 1024, 640
MX0, MX1, MY0, MY1 = 26.0, 998.0, 20.0, 620.0      # silk mount
TB = (21.1, 46.0)                                 # top brocade band (y)
SIDE = 56.0                                       # side band inner edge (x from the left)
WIN = (60.0, 50.0, 964.0, 590.0)                  # window (x0, y0, x1, y1)
NOTCH = 6.0
SPLIT = 18.5                                      # side band: azurite | celadon (xl from mount end)
ROLL = dict(cx=19.0, r=13.0, y0=17.0, y1=623.0)   # left roller (the right one is mirrored)
JADE = ("#C9DDC8", "#9DBFA4", "#5F8A73")
#: Freestyle ink of the rollers (no taper / pressure: the line must not vary along the strip)
INK = dict(thickness_px=1.1, inner_scale=0.5, calligraphy=0.0, pressure_noise=0.0, taper=False,
           crease_angle=118.0, bezier=False, smooth_silhouettes=False)
SEGMENTS = 128
WOOD = ("#8A5A3E", "#63382A", "#2F1A13")


def window_dw(G):
    x0, y0, x1, y1 = WIN
    a = P.cheb_box(G, x0, y0 + NOTCH, x1, y1 - NOTCH)
    b = P.cheb_box(G, x0 + NOTCH, y0, x1 - NOTCH, y1)
    return np.minimum(a, b)


def cloud_band(seed, y0, y1, flip=False):
    """Painted brocade strip y0..y1 (full width) on its own sub-grid: returns (rgba, y0)."""
    ss = SPEC["ss"]
    Gb = S.Grid(W, y1 - y0, ss, x0=0.0, y0=y0)
    C = P.Canvas(Gb)
    t = np.broadcast_to((Gb.Y - y0) if not flip else (y1 - Gb.Y), Gb.shape)
    h = y1 - y0
    base = P.mix("brocade_blue_deep", "brocade_blue", P.smoothstep(0.0, 3.0, np.minimum(t, h - t)))
    base = base * (1.0 + 0.04 * P.noise1d(Gb.ys, 0.3, seed, 1)[:, None])[..., None]
    base = base * (1.0 + 0.03 * P.fine_grain(Gb, seed + 1, 0.4))[..., None]
    C.over(1.0, base)
    gold = P.mix(P.gold_field(Gb, seed + 2, flecks=0.0), "brocade_ochre", 0.3)
    # mud-gold threads + pearl rows near both edges
    for a_, b_ in ((1.3, 2.1), (h - 2.1, h - 1.3)):
        C.over(P.band(t, a_, b_, Gb), gold)
    pearls = Gb.empty()
    n = int(round((MX1 - MX0) / 5.0))
    for k in range(n + 1):
        x = MX0 + (MX1 - MX0) * k / n
        for yy in (3.4, h - 3.4):
            S.sd_circle(Gb, x, y0 + (yy if not flip else h - yy), 0.82, out=pearls)
    C.over(P.aa(pearls, Gb), P.mix("ivory", "gold_light", 0.25), 0.9)
    # xiangyun clouds, alternating direction, symmetric about the centre
    reps = 22
    span = (MX1 - MX0 - 16.0)
    sd_all = Gb.empty()
    eng_all = Gb.empty()
    cy = y0 + h * 0.5 + (0.6 if not flip else -0.6)
    for k in range(reps):
        cx = MX0 + 8.0 + span * (k + 0.5) / reps
        right = (k % 2 == 0) ^ (k >= reps // 2)
        win = Gb.window(cx - 14, y0, cx + 14, y1)
        if win is None:
            continue
        sl, X, Y = win
        sub = _SubGrid(X, Y, ss)
        rot = 0.0 if right else 180.0
        shape, eng = MO.cloud(sub, cx - (3.0 if right else -3.0), cy, 10.8, rot, mirror=not right)
        sd_all[sl] = np.minimum(sd_all[sl], shape)
        eng_all[sl] = np.minimum(eng_all[sl], eng)
    C.over(P.aa(sd_all - 0.5, Gb), "brocade_blue_deep")
    C.over(P.aa(sd_all, Gb), gold)
    C.over(P.aa(eng_all - 0.3, Gb) * P.aa(sd_all + 0.4, Gb), "#6E5528", 0.9)
    # small mud-gold four-petal flowers between the clouds
    for k in range(reps + 1):
        cx = MX0 + 8.0 + span * k / reps
        fl = Gb.empty()
        for q in range(4):
            a = math.radians(45.0 + 90.0 * q)
            S.sd_circle(Gb, cx + 1.25 * math.cos(a), cy + 1.25 * math.sin(a), 1.15, out=fl)
        C.over(P.aa(fl - 0.4, Gb), "brocade_blue_deep")
        C.over(P.aa(fl, Gb), gold)
        dot = Gb.empty()
        S.sd_circle(Gb, cx, cy, 0.6, out=dot)
        C.over(P.aa(dot, Gb), "cinnabar")
    xin = P.aa(np.maximum(MX0 - Gb.X, Gb.X - MX1), Gb)
    C.erase(1.0 - np.broadcast_to(xin, Gb.shape))
    return C.rgba(), Gb


class _SubGrid:
    """Grid-like view on explicit coordinate arrays (for motif functions)."""

    def __init__(self, X, Y, ss):
        self.X, self.Y, self.ss = X, Y, ss
        self.px = 1.0 / ss
        self.shape = X.shape


def paste(C, G, rgba, Gb):
    j0 = int(round((Gb.y0 - 0.0) * G.ss))
    i0 = int(round((Gb.x0 - 0.0) * G.ss))
    sl = (slice(j0, j0 + Gb.ny), slice(i0, i0 + Gb.nx))
    a = rgba[..., 3]
    C.P[sl] = C.P[sl] * (1 - a)[..., None] + rgba[..., :3] * a[..., None]
    C.A[sl] = C.A[sl] * (1 - a) + a


def roller_2d(C, G, seed):
    """numpy stand-in for the Blender rollers (look-dev only)."""
    for side in (0, 1):
        cx = ROLL["cx"] if side == 0 else W - ROLL["cx"]
        r = ROLL["r"]
        u = (G.X - cx) / r
        body = P.aa(np.abs(G.X - cx) - r, G) * P.band(np.broadcast_to(G.Y, G.shape), ROLL["y0"], ROLL["y1"], G)
        f = np.clip(np.abs(u), 0, 1)
        col = P.mix(P.mix(WOOD[0], WOOD[1], P.smoothstep(0.0, 0.55, f)), WOOD[2], P.smoothstep(0.55, 1.0, f))
        C.over(body, col)
        C.over(P.aa(np.abs(np.abs(G.X - cx) - r) - 0.6, G) * P.band(np.broadcast_to(G.Y, G.shape), ROLL["y0"], ROLL["y1"], G), "ink")
        for yc in (10.0, H - 10.0):
            e = ((G.X - cx) / 11.0) ** 2 + ((G.Y - yc) / 7.0) ** 2
            C.over(P.aa((np.sqrt(e) - 1.0) * 7.0, G), JADE[1])
            C.over(P.aa(np.abs(np.sqrt(e) - 1.0) * 7.0 - 0.6, G), "ink")


def paint(G, variant=None, seed=None, rollers_2d=False):
    seed = SPEC["seed"] if seed is None else seed
    C = P.Canvas(G)
    X, Y = G.X, G.Y
    mount = P.aa(P.cheb_box(G, MX0, MY0, MX1, MY1), G)
    dw = window_dw(G)

    # ---- silk field ---------------------------------------------------------------------------
    tex = P.silk_texture(G, seed, weave=0.009, slub=0.016, mottle=0.011, mottle_cell=90.0)
    age = 1.0 - P.smoothstep(0.0, 14.0, -dw)
    fcol = P.rgb("paper") * tex[..., None]
    fcol = P.mix(fcol, P.mix("paper", "silk_dark", 0.6), 0.55 * age ** 1.5)
    C.over(mount, fcol)

    # ---- side bands (uniform along y) ------------------------------------------------------------
    xl = np.minimum(X - MX0, MX1 - X)                       # distance from the roller end
    side = P.aa(3.8 - dw, G) * mount
    inner = WIN[0] - 3.8 - MX0                          # xl where the window rings begin
    t = np.minimum(xl - 6.0, SPLIT - xl)
    scol = P.mix("brocade_blue_deep", "brocade_blue", P.smoothstep(0.0, 3.0, t))
    t2 = np.minimum(xl - SPLIT, inner - xl)
    jcol = P.mix("#9DAF9A", "#BFCDB6", P.smoothstep(0.0, 4.0, t2))     # pale celadon silk
    scol = np.where((xl < SPLIT)[..., None], scol, jcol)
    scol = scol * (1.0 + 0.045 * P.noise1d(xl, 0.3, seed + 3, 1) + 0.025 * P.noise1d(xl, 1.4, seed + 4, 1))[..., None]
    C.over(side, scol)
    for a_, b_ in ((7.4, 8.2), (SPLIT - 0.4, SPLIT + 0.45)):
        C.over(P.band(xl, a_, b_, G) * mount * P.aa(3.8 - dw, G), P.strip_color(xl, "gold", seed + 5, amp=0.05))

    # ---- window rings (as Panel.png) --------------------------------------------------------------
    C.over(P.band(dw, 2.8, 3.8, G) * mount, P.strip_color(dw, "gold", seed + 6, amp=0.05, period=0.5))
    C.over(P.band(dw, 2.2, 2.8, G), "ink_ui")
    C.over(P.band(dw, 0.6, 2.2, G), P.strip_color(dw, "ivory", seed + 7, amp=0.015))
    C.over(P.band(dw, 0.0, 0.6, G), "ink_soft", 0.9)

    # ---- brocade borders (top / bottom) -------------------------------------------------------------
    for flip, (y0, y1) in ((False, TB), (True, (H - TB[1], H - TB[0]))):
        rgba, Gb = cloud_band(seed + (20 if not flip else 30), y0, y1, flip)
        paste(C, G, rgba, Gb)
    # ink binding along the mount's top and bottom edges
    yb = np.broadcast_to(Y, G.shape)
    C.over((P.band(yb, MY0, TB[0], G) + P.band(yb, H - TB[0], MY1, G)) * mount, "ink")

    # ---- flowers in the window notches ------------------------------------------------------------
    x0, y0, x1, y1 = WIN
    for (x, y) in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        panel.flower(C, G, x, y, 3.4, seed + 40)
    if rollers_2d:
        roller_2d(C, G, seed)
    return C.rgba()


def paint_lookdev(G, variant=None):
    """numpy-only look-dev: the plate with flat stand-ins for the 3D rollers."""
    return paint(G, variant, rollers_2d=True)


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
            f = bm.faces.new((rows[i][k], rows[i][(k + 1) % segments], rows[i + 1][(k + 1) % segments],
                              rows[i + 1][k]))
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


def roller_profile():
    """(y, r) rows from the top tip of the jade cap to the bottom tip (image px)."""
    y0, y1, r = ROLL["y0"], ROLL["y1"], ROLL["r"]
    cap = [(2.2, 0.4), (2.5, 4.0), (3.1, 7.2), (4.1, 9.6), (5.6, 11.2), (7.4, 11.8),
           (9.7, 11.8), (10.1, 11.35), (10.5, 11.8), (13.6, 11.8), (14.2, 11.2), (14.6, 11.2),
           (14.65, 13.9), (16.4, 13.9), (16.45, r)]
    prof = list(cap) + [(y0 + 4.0, r), (H / 2.0, r), (y1 - 4.0, r)]
    prof += [(H - y, rr) for (y, rr) in reversed(cap)]
    return prof


def roller_mat(y):
    """0 = wood (rod and collars), 1 = jade (the caps)."""
    return 1 if (y < 14.62 or y > H - 14.62) else 0


def extras(variant, G):
    """Blender: two lathe-turned rollers, toon emission + Freestyle ink (roller collection)."""
    import bpy
    from ironart import ui_chrome_flat as F
    wood = F.toon_material("ToonWood", None, None, None, stops=[
        (0.0, "#9C6B4A"), (0.10, "#80503A"), (0.42, "#5E3426"), (1.0, "#29150E")])
    # fine lengthwise grain on the wood (a painted wood grain, dark streaks along the rod)
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
    mr.inputs["To Min"].default_value = 0.82
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
        (0.0, "#D8E6D2"), (0.18, "#B3CDB3"), (0.55, "#8DB096"), (1.0, "#4E7462")])
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
