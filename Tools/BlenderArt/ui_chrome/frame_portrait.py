"""Frame_Portrait.png (212x260, transparent window for a 192x240 portrait at x 10-202,
y 10-250): the portrait mounted like a painting - a silk brocade border woven with a running
cloud scroll (卷云纹) in gold thread on azurite, a mud-gold rule, an ink rule and an ivory 隔水
strip that frames the portrait's silk.

Cross-section (d = mitred distance from the outer edge, target px of the @1x art):
    0.0-1.0    ink binding (outer corner r 1)
    1.0-7.0    azurite brocade (twill ground) woven with a running cloud scroll in gold thread
               (weft floats, dark contour thread), 晕染 at both edges; the scroll's period is
               fitted so each edge holds a whole number of repeats, symmetric about its centre
    corners    9 x 9 px corner blocks of deep indigo brocade with a woven gold rosette (柿蒂)
    7.0-8.0    mud-gold rule (around the window, and closing the corner blocks)
    8.0-8.6    ink rule
    8.6-10.4   ivory 隔水 strip (lead white silk)
    10.4-11.0  ink hairline - lies 0.4-1.0 px over the portrait's edge
    > 11.0     transparent window
The frame is an overlay (drawn over the portrait), scaled uniformly with the portrait height.
"""

import math

import numpy as np

from ironart import ui_chrome_gongbi as GB
from ironart import ui_chrome_ornament as O
from ironart import ui_chrome_paint as P
from ironart import ui_chrome_sdf as S
import panel

NAME = "Frame_Portrait"
SPEC = dict(size=(212, 260), ss=4, seed=51)
W, H = 212, 260
B0, B1 = 1.0, 7.0          # brocade band
BLOCK = 9.0                # corner block size
WINDOW = 11.0

GROUND = "#3E5F7E"
GROUND_DEEP = "#22405C"
THREAD = "#CFAE68"
THREAD_DEEP = "#8E6C34"
CONTOUR = "#182A40"


def scroll_strokes(length, period, width, lw=1.0, r0=1.55, off=0.95):
    """Running cloud scroll (卷云纹) along a band in local (s, t) coordinates (s along
    0..length, t across 0..width): spirals alternately above and below the centre line, each
    linked to the next by an S-shaped stem.  The period is fitted to an even number of half
    repeats and the pattern is symmetric about the band's centre (mirror pairs).
    Returns [(pts, radii)]."""
    n = max(2, int(round(length / period)))
    p = length / n
    mid = width / 2.0
    out = []
    for k in range(-1, 2 * n + 1):
        s = k * p / 2.0 + p / 4.0
        sg = 1.0 if k % 2 == 0 else -1.0
        cy = mid + sg * off
        spiral, _ = O.volute(s, cy, r0, 0.3, 1.0, 90.0 * sg, cw=(sg > 0), n=40)
        s2 = s + p / 2.0
        p0 = spiral[0]
        p3 = (s2, mid - sg * off - sg * r0)
        conn = O.path([(p0, (p0[0] + p * 0.19, p0[1]), (p3[0] - p * 0.19, p3[1]), p3)], 20)
        pts = np.concatenate([conn[::-1], spiral[1:]], 0)
        out.append((pts.astype(np.float32), O.taper(len(pts), lw * 0.9, lw, lw * 0.45)))
    return out


def band_figure(G, seed):
    """sd of the running scroll on all four bands (in image coordinates)."""
    mid = 0.5 * (B0 + B1)
    sd = G.empty()
    bands = [
        # (s0, s1, fixed coordinate, horizontal?)
        (BLOCK, W - BLOCK, mid, True),
        (BLOCK, W - BLOCK, H - mid, True),
        (BLOCK, H - BLOCK, mid, False),
        (BLOCK, H - BLOCK, W - mid, False),
    ]
    width = B1 - B0
    for (s0, s1, c, horiz) in bands:
        L = s1 - s0
        for pts, rad in scroll_strokes(L, 16.0, width, lw=1.05):
            q = pts.copy()
            q[:, 1] += c - width / 2.0
            if horiz:
                q[:, 0] += s0
            else:
                q = np.stack([q[:, 1], q[:, 0] + s0], 1)
            S.sd_polyline(G, q, rad, out=sd, pad=1.5)
    # clip to the band between the corner blocks
    along = np.where(np.minimum(G.X, W - G.X) < np.minimum(G.Y, H - G.Y), G.Y, G.X)
    del along
    return sd


def paint(G, variant=None, seed=None):
    seed = SPEC["seed"] if seed is None else seed
    d = S.inset_distance(G, W, H, r=1.0)
    C = P.Canvas(G)
    shape = S.aa_mask(-d, G)
    corner = (np.minimum(G.X, W - G.X) < BLOCK) & (np.minimum(G.Y, H - G.Y) < BLOCK)
    corner = corner.astype(np.float32)

    # opaque underlay of the whole border (abutting anti-aliased bands would leave alpha seams)
    C.over(S.aa_mask(d - WINDOW, G) * shape, "#2A2119")

    # ---- brocade band with the woven scroll -------------------------------------------------
    fig_sd = band_figure(G, seed)
    fig = S.aa_mask(fig_sd, G) * (1.0 - corner)
    contour = S.aa_mask(np.abs(fig_sd) - 0.65, G) * (1.0 - fig) * (1.0 - corner)
    col = GB.brocade(G, fig, ground=GROUND, ground_deep=GROUND_DEEP, fig=THREAD,
                     fig_deep=THREAD_DEEP, seed=seed + 1, outline=contour * 0.55)
    # 晕染: the brocade deepens towards both band edges
    t = np.minimum(d - B0, B1 - d)
    col = col * (0.80 + 0.20 * P.smoothstep(0.0, 1.6, t))[..., None]
    C.over(GB.band(d, B0 - 0.3, B1, G) * shape, col)

    # ---- corner blocks ------------------------------------------------------------------------
    blk = GB.brocade(G, np.zeros(G.shape, np.float32), ground="#2A4866", ground_deep="#172B42",
                     seed=seed + 2)
    tb = np.minimum(np.minimum(G.X, W - G.X), np.minimum(G.Y, H - G.Y)) - B0
    blk = blk * (0.85 + 0.15 * P.smoothstep(0.0, 1.5, tb))[..., None]
    C.over(corner * GB.band(d, B0 - 0.3, 99, G) * shape, blk)
    c = 0.5 * (B0 + BLOCK) + 0.1
    for (x, y) in ((c, c), (W - c, c), (c, H - c), (W - c, H - c)):
        panel.woven_rosette(C, G, x, y, 3.5, seed + 3)
    # gold thread closing each corner block towards the bands
    cb = np.maximum(np.abs(np.minimum(G.X, W - G.X) - BLOCK), 0)
    edge_x = S.aa_mask(np.abs(np.minimum(G.X, W - G.X) - BLOCK + 0.3) - 0.3, G) \
        * (np.minimum(G.Y, H - G.Y) < BLOCK) * (d > B0)
    edge_y = S.aa_mask(np.abs(np.minimum(G.Y, H - G.Y) - BLOCK + 0.3) - 0.3, G) \
        * (np.minimum(G.X, W - G.X) < BLOCK) * (d > B0)
    del cb
    C.over(np.maximum(edge_x, edge_y), "#B8934A")

    # ---- rules and ivory strip ----------------------------------------------------------------
    gthr = GB.strip_threads(d, seed + 4, pitch=0.5, amp=0.04, gap=0.15)
    C.over(GB.band(d, 7.0, 8.0, G), P.rgb("#C9A24B") * gthr[..., None])
    C.over(GB.band(d, 8.0, 8.6, G), "#2A2119")
    ivory = P.rgb("#F0E8D6") * GB.strip_threads(d, seed + 5, pitch=0.4, amp=0.012, gap=0.3,
                                               slow=0.0)[..., None]
    ivory = P.mix(ivory, P.rgb("#DDD0B4"), 0.35 * P.smoothstep(9.6, 10.4, d))
    C.over(GB.band(d, 8.6, 10.4, G), ivory)
    C.over(GB.band(d, 10.4, 11.0, G), "#3A2E24", 0.85)
    C.over(GB.band(d, -5.0, B0, G) * shape, "#1E1A16")
    C.erase(S.aa_mask(WINDOW - d, G))
    return C.rgba()
