"""Divider.png (512x16, plain image, stretched by Slate to the column width and drawn 8-12 px
high): a fine calligraphic ink rule between two mud-gold hairlines, knotted in the middle by a
painted ruyi cloud knot - a cinnabar lozenge jewel set in mud-gold, flanked by mud-gold cloud
volutes (卷云) that draw a ruyi (如意) heart in outline on each side.

    ink rule      y 8 (centre), 2 px thick beside the knot, tapering to a hair by x 12 / 500
                  and fading out (calligraphic entry and exit, slight loading variation)
    gold lines    y 5.3 and 10.7, 0.95 px, tapering out sooner (x 40 / 472) - they carry the
                  divider on dark panels, where the ink line disappears
    knot          x 233-279, y 1-15: a cinnabar lozenge 11.6 x 13.2 px at the centre, set in
                  mud-gold, between two pairs of cloud volutes (a ruyi heart in outline) and
                  two smaller outer curl pairs
The art keeps clear of the outer 1 px ring (alpha 0) so bilinear stretching never smears it.
"""

import math

import numpy as np

from ironart import ui_chrome_gongbi as GB
from ironart import ui_chrome_ornament as O
from ironart import ui_chrome_paint as P
from ironart import ui_chrome_sdf as S

NAME = "Divider"
SPEC = dict(size=(512, 16), ss=4, seed=61)
W, H = 512, 16
CX, CY = 256.0, 8.0


def line_profile(x, x_end, w_max, w_min, power=1.6):
    """Half-width of a calligraphic rule along x: full beside the knot, tapering to a hair."""
    t = np.clip((np.abs(x - CX) - 20.0) / (x_end - 20.0), 0.0, 1.0)
    return (w_min + (w_max - w_min) * (1.0 - t) ** power) * 0.5


def paint(G, variant=None, seed=None):
    seed = SPEC["seed"] if seed is None else seed
    C = P.Canvas(G)
    X, Y = G.X, G.Y
    # ---- ink rule ---------------------------------------------------------------------------
    hw = line_profile(X, CX - 12.0, 2.0, 0.3, 1.1)
    fade = P.smoothstep(12.0, 46.0, np.minimum(X, W - X))
    wob = 0.05 * P.noise1d(G.xs, 40.0, seed, octaves=2)[None, :]
    ink_sd = np.abs(Y - CY - wob) - hw
    ink = GB.ink_density(G, seed + 1, "#1E1A16", var=0.25, cell=30.0)
    C.over(S.aa_mask(ink_sd, G) * fade, ink, 0.95)
    # ---- gold hairlines ---------------------------------------------------------------------
    ghw = line_profile(X, CX - 40.0, 0.95, 0.3, 1.0)
    gfade = P.smoothstep(40.0, 110.0, np.minimum(X, W - X))
    gold = GB.mud_gold(G, None, seed + 2, base="#D0AA55", gran=0.03, flecks=0.0)
    for gy in (CY - 2.7, CY + 2.7):
        g = S.aa_mask(np.abs(Y - gy) - ghw, G) * gfade * (np.abs(X - CX) > 15.5)
        C.over(g, gold, 0.95)

    # ---- knot: cinnabar jewel between two pairs of cloud volutes ------------------------------
    strokes = []
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            # a branch leaves the jewel's side tip, sweeps out and away from the rule, and
            # curls back inwards (a cloud volute) - the pair reads as a ruyi heart in outline
            c = (CX + sx * 12.4, CY + sy * 2.55)
            r0 = 2.35
            a0 = -90.0 * sy if sx > 0 else -90.0 * sy
            spiral, _ = O.volute(c[0], c[1], r0, 0.35, 1.0, a0, cw=(sx * sy > 0), n=50)
            p0 = (CX + sx * 5.6, CY)
            lead = O.path([(p0, (CX + sx * 8.0, CY + sy * 0.2), (spiral[0][0] - sx * 2.0,
                            spiral[0][1]), tuple(spiral[0]))], 16)
            st = np.concatenate([lead[:-1], spiral], 0)
            strokes.append((st.astype(np.float32), O.taper(len(st), 1.5, 1.25, 0.45)))
        # small outer curl pair continuing the rhythm along the rule
        for sy in (-1.0, 1.0):
            c = (CX + sx * 19.6, CY + sy * 2.2)
            spiral, _ = O.volute(c[0], c[1], 1.5, 0.3, 0.9, 90.0 * sy, cw=(sx * sy < 0), n=36)
            p0 = (CX + sx * 15.2, CY)
            lead = O.path([(p0, (CX + sx * 16.6, CY + sy * 0.1), (spiral[0][0] - sx * 1.2,
                            spiral[0][1]), tuple(spiral[0]))], 12)
            st = np.concatenate([lead[:-1], spiral], 0)
            strokes.append((st.astype(np.float32), O.taper(len(st), 1.0, 0.85, 0.35)))
    heads = O.strokes_sd(G, strokes, pad=1.5)
    loz = np.array([[CX - 5.8, CY], [CX, CY - 6.6], [CX + 5.8, CY], [CX, CY + 6.6]], np.float32)
    jewel = G.empty()
    S.sd_polygon(G, loz, out=jewel)
    knot = np.minimum(heads, jewel)
    # ink contour around the whole knot, then gold, then the cinnabar jewel
    C.over(S.aa_mask(knot - 0.6, G), "#1E1A16", 0.95)
    C.over(S.aa_mask(knot, G), GB.mud_gold(G, knot, seed + 3, base="#CFA855", yun=0.0,
                                           pool=0.12, gran=0.03))
    inner = jewel + 1.15
    C.over(S.aa_mask(inner + 0.0, G), "#3A1A10", 0.9)
    C.over(S.aa_mask(inner + 0.45, G), GB.mineral(G, inner + 0.45, "#C0402E", "#7E2318",
                                                   light="#D45A3E", seed=seed + 4, yun=2.0,
                                                   gran=0.03, pool=0.0))
    # a lead-white highlight stroke (提白) on the jewel's upper left facet
    hl = np.array([[CX - 2.5, CY - 0.5], [CX - 0.5, CY - 3.2]], np.float32)
    hsd = G.empty()
    S.sd_polyline(G, hl, np.array([0.33, 0.14], np.float32), out=hsd)
    C.over(S.aa_mask(hsd, G), "#F0E2C8", 0.5)
    # keep the outer ring clear
    ring = (X > 1.0) & (X < W - 1.0) & (Y > 1.0) & (Y < H - 1.0)
    C.erase(1.0 - ring.astype(np.float32))
    return C.rgba()
