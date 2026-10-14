"""Divider.png (512x16, transparent): a fine gongbi ink line with a painted ruyi cloud knot.

    knot      a cinnabar ruyi head (如意, tip down) at x 256, 晕染 deepening to its rim, mud-gold
              engraved curls and a fine ink outline; flanked by two mud-gold cloud curls
              (卷云) that spring from its side lobes and turn back towards it
    line      one ink stroke each way, pressed where it leaves the cloud curl (1.5 px) and
              lifting off to a hair at the ends (x 12 / 500); a mud-gold hairline runs beside
              it (y +2.1) the whole way, so the rule reads on light silk and on ink-dark panels
The UI stretches the image to the width of its column and 8-16 px high: the knot is kept
compact (x 228-284) so a 0.6-1.8x horizontal stretch still reads.
"""

import math

import numpy as np

from ironart import ui_chrome_motifs as MO
from ironart import ui_chrome_paint as P
from ironart import ui_chrome_sdf as S

NAME = "Divider"
SPEC = dict(size=(512, 16), ss=4, seed=61)
W, H = 512, 16
CX, CY = 256.0, 8.0


def curls():
    """Mud-gold cloud curls on both sides of the knot: [(pts, radii)]."""
    out = []
    for side in (1, -1):
        r0 = 3.1
        cx, cy = CX + side * 13.6, CY - 0.6
        # spiral starting at its bottom, turning up and back towards the knot
        a0 = 90.0
        pts = S.spiral(cx, cy, r0, r0 * 0.24, 1.1, a0, cw=(side < 0), n=70)
        # lead-in from the ruyi's side lobe
        lead = S.bezier((CX + side * 6.4, CY + 1.4), (CX + side * 8.5, CY + 3.4),
                        (cx - side * 1.5, cy + r0 + 0.2), (cx, cy + r0), n=18)
        path = np.concatenate([lead, pts[1:]])
        rad = P.brush_radii(len(path), 1.05, start=0.55, end=0.42, press=1.12)
        out.append((path, rad))
    return out


def line_strokes():
    out = []
    for side in (1, -1):
        x0, x1 = CX + side * 15.0, CX + side * 244.0
        n = 260
        xs = np.linspace(x0, x1, n)
        ys = CY + 2.45 + 0.0 * xs
        # the line leaves the curl's base tangentially and settles on y = 8 + 0.4
        ys = CY + 0.4 + 2.05 * np.exp(-np.abs(xs - x0) / 6.0)
        pts = np.stack([xs, ys], 1).astype(np.float32)
        t = np.linspace(0, 1, n)
        rad = 0.75 * (1.0 - 0.82 * P.smoothstep(0.05, 1.0, t) ** 0.8) * \
            (0.85 + 0.15 * P.smoothstep(0.0, 0.05, t))
        out.append((pts, rad.astype(np.float32)))
    return out


def gold_under():
    """A mud-gold hairline beside the ink line along its whole length: the double rule reads
    as ink on light silk and as gold on the ink-dark panels."""
    out = []
    for side in (1, -1):
        xs = np.linspace(CX + side * 19.0, CX + side * 236.0, 260)
        ys = np.full_like(xs, CY + 2.55)
        t = np.linspace(0, 1, len(xs))
        rad = 0.42 * (1.0 - 0.8 * P.smoothstep(0.05, 1.0, t) ** 0.8) * P.smoothstep(0.0, 0.04, t)
        out.append((np.stack([xs, ys], 1).astype(np.float32), rad.astype(np.float32)))
    return out


def paint(G, variant=None, seed=None):
    seed = SPEC["seed"] if seed is None else seed
    C = P.Canvas(G)
    gold = P.gold_field(G, seed, flecks=0.0)

    # ---- line + under-line --------------------------------------------------------------------
    C.over(P.aa(P.strokes_sd(G, gold_under()), G), gold, 0.95)
    C.over(P.aa(P.strokes_sd(G, line_strokes()), G), "ink")

    # ---- cloud curls (ink-outlined mud-gold strokes) ---------------------------------------------
    sd_c = P.strokes_sd(G, curls())
    C.over(P.aa(sd_c - 0.42, G), "ink")
    C.over(P.aa(sd_c, G), gold)

    # ---- ruyi knot ------------------------------------------------------------------------------
    shape, eng = MO.ruyi(G, CX, CY - 0.4, 8.0, 0.0)
    C.over(P.aa(shape - 0.45, G), "ink")
    sh = P.smoothstep(0.0, 1.8, -shape)
    C.over(P.aa(shape, G), P.mix("#7E2219", "cinnabar", sh))
    C.over(P.aa(eng - 0.24, G) * P.aa(shape + 0.35, G), gold)
    # a lead-white highlight dot in the top lobe (the jewel of the ruyi)
    dot = G.empty()
    S.sd_circle(G, CX, CY - 3.0, 0.7, out=dot)
    C.over(P.aa(dot, G), "gold_light", 0.9)
    return C.rgba()
