"""Frame_Portrait.png (212x260, transparent 192x240 window at (10, 10)): carved rosewood frame
with gilded cloud-scroll corners.

Cross-section (d from the outer edge, px = mm; the frame is never stretched, so the wood carries
real figure that wanders along the rails):
    0-0.8    outer lip
    0.8-3.7  carved rope-twist bead (diagonal cuts every 2.2 px)
    3.7-6.4  rosewood ogee with clear coat
    6.4-8.5  gilt bead
    8.5-10   black-lacquer sight edge falling to the portrait
Inside the window a shadow catcher (the portrait plane) records the frame's own cast shadow and
contact darkening as a soft translucent shade over the top/left portrait edge.
Corners: gilt xiangyun corner pieces - a ruyi head on the mitre pointing into the window and two
cloud scrolls running along the rails - overlapping the portrait corner by up to 14 px.
"""

import numpy as np

import kit
from ironart import ui_chrome_motifs as MO
from ironart import ui_chrome_sdf as S
from ironart.ui_chrome_maps import Maps, L

NAME = "Frame_Portrait"
SPEC = dict(size=(212, 260), ss=4, spp=40, seed=41)
W, H = 212, 260
B = 10.0
CORNER = 48


def corner_piece(ss):
    """Top-left gilt corner on a local CORNER x CORNER grid (folded about the diagonal).
    Returns (height, mask, engraving mask)."""
    G = S.Grid(CORNER, CORNER, ss)
    u, v = MO.corner_fold(G)
    strokes = []
    # scroll along the rail (in the folded frame the rail is the u axis, v across it)
    stem = S.bezier((8.0, 4.8), (16.0, 3.9), (26.0, 3.7), (33.5, 5.6), n=48)
    curl = S.spiral(34.2, 10.0, 4.5, 0.7, 1.1, -90.0 + 10.0, cw=True, n=90)
    path = np.concatenate([stem, curl[1:]], 0)
    rad = S.taper(len(path), 1.85, 0.5, power=0.85)
    strokes.append((path, rad))
    sd = MO.strokes_sd(G, strokes, pad=3.0)
    # mirror the strokes to the other rail: evaluate on swapped coords and union
    sd_sw = MO.strokes_sd(S.Grid(CORNER, CORNER, ss), [(p[:, ::-1].copy(), r) for p, r in strokes], pad=3.0)
    sd = np.minimum(sd, sd_sw)
    ry, ry_eng = MO.ruyi(kit.Folded(G.X, G.Y), 13.6, 13.6, 17.0, rot=-45.0)
    boss = np.hypot(G.X - 5.0, G.Y - 5.0) - 3.4
    shape = S.smooth_union(S.smooth_union(sd, ry, 0.7), boss, 0.8)
    z = MO.dome(shape, 1.4, 0.95)
    z = S.blur(z, 0.3 * ss)
    eng = np.where(ry < -0.3, ry_eng, 9.0)
    z = z + S.groove(eng, 0.36, 0.22)
    z = z + MO.dome(boss + 0.9, 1.0, 0.45)
    return z.astype(np.float32), S.aa_mask(shape, G), S.aa_mask(eng - 0.22, G)


def build(G, variant=None):
    d = S.inset_distance(G, W, H, r=2.0)
    m = Maps(G.shape, base="#4A2318")
    pts = [(-1, 0.0), (0.0, 0.3), (0.4, 1.3), (0.8, 1.7)]
    pts += kit.bead(2.25, 1.45, 1.55, n=11, flat=0.85)
    pts += [(3.75, 1.6), (4.3, 2.3), (5.2, 2.55), (6.0, 2.35), (6.4, 1.9)]
    pts += kit.bead(7.45, 1.05, 1.75)
    pts += [(8.55, 1.7), (8.9, 1.25), (9.6, 0.6), (10.0, 0.35), (10.4, 0.3)]
    z = S.Profile(pts, round_px=0.12)(d)

    rope = S.band(d, 0.8, 3.7, G)
    wood = S.band(d, -5, 6.45, G)
    gold = S.band(d, 6.45, 8.5, G)
    sight = S.band(d, 8.5, 99, G)

    # along-rail coordinate (for the rope twist and the wood figure)
    along = np.where(np.minimum(G.X, W - G.X) < np.minimum(G.Y, H - G.Y), G.Y, G.X)
    # rope twist: diagonal cuts, period 2.2 px, direction flips per side for a continuous twist
    side_sign = np.where(G.X < W / 2, 1.0, -1.0) * np.where(G.Y < H / 2, 1.0, -1.0)
    ph = (along + side_sign * (d - 2.25) * 1.1) / 2.2
    cut = np.abs((ph - np.floor(ph)) - 0.5) * 2.0          # 0 at the cut, 1 mid-strand
    z = z - rope * 0.55 * (1 - kit.smoothstep(0.0, 0.45, cut))
    g = kit.grain2d(along, d, 17, freq=0.75, wave=0.5, ss=G.ss)
    m.paint(wood, "rosewood", base=L("#5E2C1D"))
    m.tint(wood, g)
    m.tint(rope, 0.75 + 0.25 * kit.smoothstep(0.0, 0.6, cut))
    m.paint(wood, rough=0.32)
    m.paint(gold, "gold")
    m.paint(sight, "lacquer_black", base=L("#1F1510"))

    # gilt corners (local 40 x 40, stamped); they lie over the frame and the window corner
    cz, cm, ce = (kit.stamp(G, a) for a in corner_piece(G.ss))
    zc = 1.6 + cz
    z = z * (1 - cm) + np.maximum(z, zc) * cm
    m.paint(cm, "gold")
    m.tint(cm, kit.recess_shade(cz, G.ss, radius=1.6, k=1.6))
    wf, wr = kit.edge_wear(cz, G.ss, radius=1.0, k=1.5)
    m.tint(cm, wf)
    m.rough = m.rough + wr * cm
    m.tint(cm * ce, 0.62)
    m.paint(cm * ce, rough=0.45)

    m.height = z.astype(np.float32)
    frame = S.aa_mask(-d, G) * (1 - S.aa_mask(B - d, G))
    m.alpha = np.clip(frame + cm, 0, 1).astype(np.float32)
    return m


def extras(variant, G):
    """The portrait plane as a shadow catcher inside the window (frame shadow + occlusion).
    Only a 16 px ring along the window edge is modelled - the shadow never reaches further and
    an empty centre costs nothing to render."""
    import bpy
    from ironart.ui_chrome_render import MM
    hw, hh = (W / 2 - B + 0.5) * MM, (H / 2 - B + 0.5) * MM
    iw, ih = hw - 16 * MM, hh - 16 * MM
    verts = [(-hw, -hh, 0.0), (hw, -hh, 0.0), (hw, hh, 0.0), (-hw, hh, 0.0),
             (-iw, -ih, 0.0), (iw, -ih, 0.0), (iw, ih, 0.0), (-iw, ih, 0.0)]
    faces = [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    me = bpy.data.meshes.new("Catcher")
    me.from_pydata(verts, [], faces)
    ob = bpy.data.objects.new("Catcher", me)
    bpy.context.scene.collection.objects.link(ob)
    ob.is_shadow_catcher = True
    return ob
