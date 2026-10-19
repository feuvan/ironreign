"""PanelDark.png (128x128 9-slice, 24 px margins): ink-dark silk with a painted mud-gold (泥金)
border and mud-gold cloud scrolls in the corners.

Cross-section (d = mitred distance from the outer edge, target px of the @1x art; the rings are
functions of d only, so the 9-slice strips stretch cleanly):

    d 0.0-1.0   deep-umber edge (the silk turned over the board), 晕染 into the field
    d 1.0-2.0   ink silk
    d 2.0-3.0   mud-gold rule (on the @1x pixel grid)
    d 3.0-4.0   ink silk with an umber 晕染
    d 4.0-4.7   mud-gold hairline (80 %)
    d > 4.7     ink-dark silk field #1E1A16 (Night +-3) with lengthwise silk threads in the
                strips and a faint deep-umber glow only in the 9-slice centre

Corners: a mud-gold ruyi cloud head (如意云头) on the diagonal pointing into the corner, with
engraved ink curls, and two tapered cloud tendrils (卷云) that leave its side lobes along the
edges and end in curls - all within 22 px of the corner.  Text on it: TextLight / Gold.
"""

import math

import numpy as np

from ironart import ui_chrome_gongbi as GB
from ironart import ui_chrome_ornament as O
from ironart import ui_chrome_paint as P
from ironart import ui_chrome_sdf as S

NAME = "PanelDark"
SPEC = dict(size=(128, 128), ss=4, margins=(24, 24, 24, 24), seed=21)
W = H = 128
FIELD = "#1E1A16"
EDGE_C = "#33261B"
GLOW = "#2B2219"

RULE = (2.0, 3.0)    # one @1x pixel
HAIR = (4.0, 4.7)
RUYI_C = 9.6       # ruyi centre on the diagonal (px from both edges)
RUYI_S = 4.8       # ruyi half size


def corner_strokes():
    """Cloud tendrils of the top-left corner (local px): from each side lobe of the ruyi along
    the edge, ending in an inward curl."""
    out = []
    for flip in (False, True):
        # along +x (top edge); the vertical one is the mirror about the diagonal
        start = (RUYI_C + 3.9, RUYI_C - 2.6)
        pts = O.path([(start, (RUYI_C + 6.5, RUYI_C - 4.4), (RUYI_C + 8.5, 5.9),
                       (RUYI_C + 10.6, 6.0))], 24)
        curl_c = (RUYI_C + 10.9, 8.3)
        spiral, _ = O.volute(curl_c[0], curl_c[1], 2.3, 0.45, 1.05, -90.0, cw=True, n=48)
        pts = np.concatenate([pts, spiral[1:]], 0)
        rad = O.taper(len(pts), 0.55, 1.0, 0.35)
        if flip:
            pts = pts[:, ::-1].copy()
        out.append((pts.astype(np.float32), rad))
    return out


def paint(G, variant=None, seed=None):
    seed = SPEC["seed"] if seed is None else seed
    d = S.inset_distance(G, W, H, r=1.0)
    axis = GB.strip_axis(G, W, H)
    C = P.Canvas(G)
    shape = S.aa_mask(-d, G)

    # ---- ink silk field ---------------------------------------------------------------------
    cw = P.centre_weight(G, SPEC["margins"], fade=12.0)
    glow = P.smoothstep(0.0, 1.0, cw) * (0.55 + 0.45 * P.fbm2(G, 50.0, seed + 1, octaves=2)
                                         .clip(-1, 1) * 0.5)
    thr = GB.strip_threads(d, seed + 2, pitch=0.42, amp=0.05, gap=0.4, slow=0.02)
    thr2 = GB.strip_threads(d + 0.19, seed + 3, pitch=0.42, amp=0.05, gap=0.4, slow=0.02)
    thr = thr * axis + thr2 * (1.0 - axis)
    edge = (1.0 - P.smoothstep(0.0, 9.0, d)) ** 1.5
    # lengthwise threads only show in the umber edge silk (the field must stay even)
    thr = 1.0 + (thr - 1.0) * (0.25 + 0.75 * edge) * (1.0 - cw)
    fcol = P.mix(FIELD, GLOW, 0.65 * glow) * thr[..., None]
    # umber 晕染 from the edge into the field
    fcol = P.mix(fcol, P.rgb(EDGE_C) * thr[..., None], 0.75 * edge)
    C.over(shape, fcol)

    # ---- painted mud-gold rules -------------------------------------------------------------
    gthr = GB.strip_threads(d, seed + 5, pitch=0.5, amp=0.035, gap=0.15, slow=0.03)
    gold = GB.mud_gold(G, None, seed + 6, gran=0.0, flecks=0.0) * gthr[..., None]
    rim_k = 1.0 - 0.14 * (1.0 - P.smoothstep(RULE[0], RULE[0] + 0.35, d)) \
        - 0.14 * P.smoothstep(RULE[1] - 0.35, RULE[1], d)
    C.over(GB.band(d, *RULE, G), gold * rim_k[..., None])
    C.over(GB.band(d, *HAIR, G), gold, 0.8)
    C.over(GB.band(d, -5.0, 1.0, G) * shape, P.rgb("#251B14") * thr[..., None], 0.9)

    # ---- corner cloud scrolls ---------------------------------------------------------------
    # top-left corner on the full grid, mirrored into the other three (exact: symmetric lattice)
    rot = 135.0                       # ruyi point towards the corner
    rsd, curls = O.ruyi(G, RUYI_C, RUYI_C, RUYI_S, rot=rot)
    ten = O.strokes_sd(G, corner_strokes())
    rsd, curls, ten = GB.mirror4(rsd), GB.mirror4(curls), GB.mirror4(ten)
    orn = np.minimum(rsd, ten)
    # a halo of field colour interrupts the hairline behind the ornament
    C.over(S.aa_mask(orn - 0.75, G) * P.smoothstep(3.0, 3.4, d), P.rgb(FIELD) * thr[..., None])
    C.over(S.aa_mask(orn, G), GB.mud_gold(G, orn, seed + 7, yun=1.3, pool=0.14, gran=0.04))
    C.over(S.aa_mask(curls - 0.24, G) * S.aa_mask(rsd + 0.55, G), "#3A2812", 0.85)
    return C.rgba()
