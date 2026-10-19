"""Panel.png (128x128 9-slice, 24 px margins): an aged silk leaf in a brocade mount (装裱).

Layout (target px of the @1x art).  ``d`` = mitred distance from the outer edge, ``dw`` =
Chebyshev distance outside the window, which has square-notched (委角) corners; along the strips
``dw`` = 6 - d, so every ring is a function of the distance across its strip and Slate can stretch
the strips cleanly:

    d  0.0-1.0     ink-umber binding (the board edge the brocade is turned over)
    dw > 0         azurite silk brocade (d 1-6 along the strips): lengthwise threads, 晕染
                   deepening to both edges; in each corner the brocade
                   widens into a 13 px corner block (the window notch) carrying a woven
                   mud-gold rosette (柿蒂) with a cinnabar heart
    dw  0.0..-1.0  mud-gold (泥金) rule        (d 6-7: rules sit on the @1x pixel grid)
    dw -1.0..-2.0  fine ink rule              (d 7-8)
    dw -2.0..-3.5  ivory 隔水 silk strip
    dw -3.5..-4.0  ink-brown hairline
    dw < -4.0      silk field (Paper): an ageing wash under the mount fading out by dw -14, a
                   large faint mottle only in the 9-slice centre (Slate stretches it ~8x)

Everything but the corner blocks and the steps of the rules stays within d 10 (Slate pads
panel content 10-28 px).
"""

import math

import numpy as np

from ironart import ui_chrome_gongbi as GB
from ironart import ui_chrome_ornament as O
from ironart import ui_chrome_paint as P
from ironart import ui_chrome_sdf as S

NAME = "Panel"
SPEC = dict(size=(128, 128), ss=4, margins=(24, 24, 24, 24), seed=11)
W = H = 128

EDGE = 1.0          # binding
INSET = 6.0         # window edge along the strips (brocade 1..6)
NOTCH = 7.0         # corner block reaches INSET + NOTCH = 13 px from the outer edge
GOLD = (0.0, -1.0)  # in dw (d 6-7 along the strips: one @1x pixel)
INK = (-1.0, -2.0)  # d 7-8
IVORY = (-2.0, -3.5)
HAIR = (-3.5, -4.0)

BLUE = "#3E5F7E"
BLUE_DEEP = "#203A55"
GUARD = "#B48F55"
CONTOUR = "#16263A"


def brocade_band(G, d, axis, seed, d0, d1, blue=BLUE, deep=BLUE_DEEP, guard=GUARD,
                 guard_at=(0.6, 0.6), guard_w=0.42, tdist=None):
    """Colour of a mitred brocade band between d0 and d1: lengthwise threads (per strip
    orientation), 晕染 deepening to both edges (``tdist`` overrides the distance-to-edge
    field), an ochre guard thread near each edge."""
    t = np.minimum(d - d0, d1 - d) if tdist is None else tdist
    base = P.mix(deep, blue, P.smoothstep(0.0, 1.9, t) ** 0.8)
    thr = GB.strip_threads(d, seed, pitch=0.42, amp=0.06, gap=0.45, slow=0.025, slow_period=1.6)
    thr2 = GB.strip_threads(d + 0.21, seed + 7, pitch=0.42, amp=0.06, gap=0.45, slow=0.025,
                            slow_period=1.6)
    thr = thr * axis + thr2 * (1.0 - axis)
    col = base * thr[..., None]
    if guard_w > 0:
        g0 = GB.ruled(d, d0 + guard_at[0], guard_w, G)
        g1 = GB.ruled(d, d1 - guard_at[1], guard_w, G)
        gcol = P.rgb(guard) * thr[..., None]
        col = col + (gcol - col) * np.maximum(g0, g1)[..., None]
    return col


def woven_rosette(C, G, cx, cy, r, seed, contour=CONTOUR, heart="#B5382A"):
    """Mud-gold rosette woven into brocade: separate petals with a dark contour thread and a
    cinnabar heart."""
    pet, hrt = O.rosette(G, cx, cy, r)
    C.over(S.aa_mask(pet - 0.42, G), contour, 0.9)
    fl, _ = GB.weft_floats(G, seed, pitch=0.4, float_len=1.6)
    col = GB.mud_gold(G, pet, seed + 1, yun=0.35 * r, gran=0.03, flecks=0.0, pool=0.08)
    C.over(S.aa_mask(pet, G), col * (1.0 + 0.05 * fl)[..., None])
    C.over(S.aa_mask(hrt - 0.32, G), contour, 0.9)
    C.over(S.aa_mask(hrt, G), GB.mineral(G, hrt, heart, "#7E2318", seed=seed + 2, yun=0.3 * r,
                                         gran=0.02, pool=0.0))


def paint(G, variant=None, seed=None):
    seed = SPEC["seed"] if seed is None else seed
    d = S.inset_distance(G, W, H, r=1.0)
    dw = P.notched_window(G, W, H, INSET, NOTCH)
    axis = GB.strip_axis(G, W, H)
    C = P.Canvas(G)
    shape = S.aa_mask(-d, G)

    # ---- silk field -------------------------------------------------------------------------
    cw = P.centre_weight(G, SPEC["margins"], fade=10.0)
    mott = P.fbm2(G, 46.0, seed + 1, octaves=3, gain=0.5)
    tex = 1.0 + 0.010 * mott * cw
    age = (1.0 - P.smoothstep(-HAIR[1], 14.0, -dw)) ** 1.7
    fcol = P.rgb("paper") * tex[..., None]
    fcol = P.mix(fcol, P.rgb("#D3BF96"), 0.55 * age)
    C.over(shape, fcol)

    # ---- mount ------------------------------------------------------------------------------
    # brocade: along the strips a function of d; in the corner blocks the 晕染 follows the
    # distance to the block's inner (window) edge as well
    tdist = np.minimum(d - EDGE, dw)
    C.over(S.aa_mask(-dw, G) * GB.band(d, EDGE - 0.3, 99.0, G) * shape,
           brocade_band(G, d, axis, seed + 10, EDGE, INSET, tdist=tdist, guard_w=0.0))

    gold = GB.mud_gold(G, None, seed + 20, gran=0.0, flecks=0.0)
    gold = gold * GB.strip_threads(dw, seed + 21, pitch=0.5, amp=0.04, gap=0.2)[..., None]
    gold = gold * (1.0 - 0.10 * (1.0 - P.smoothstep(-0.4, 0.0, dw))
                   - 0.10 * P.smoothstep(-1.0, -0.6, dw))[..., None]
    C.over(GB.band(-dw, -GOLD[0], -GOLD[1], G), gold)
    C.over(GB.band(-dw, -INK[0], -INK[1], G), "#2A2119")
    C.over(GB.band(-dw, -IVORY[0], -IVORY[1], G), P.rgb("#EFE6D0")
           * GB.strip_threads(dw, seed + 30, pitch=0.4, amp=0.012, gap=0.3, slow=0.0)[..., None])
    C.over(GB.band(-dw, -HAIR[0], -HAIR[1], G), "#6B5844", 0.75)
    C.over(GB.band(d, -5.0, EDGE, G) * shape, "#231C16")

    # ---- corner rosettes ---------------------------------------------------------------------
    c = 0.5 * (EDGE + INSET + NOTCH) + 0.05
    for (x, y) in ((c, c), (W - c, c), (c, H - c), (W - c, H - c)):
        woven_rosette(C, G, x, y, 4.6, seed + 40)
    return C.rgba()
