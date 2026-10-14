"""Panel.png (128x128 9-slice, 24 px margins): a gongbi painting mount (装裱).

An aged silk field mounted like an album leaf: a slim border of azurite silk brocade, a
mud-gold rule, a ruled ink line and an ivory separating strip (隔水), with square-notched
(委角) corners - the ruled lines step around each corner, and a mud-gold four-petal flower
(柿蒂) with a cinnabar centre sits on the brocade in the notch.

Cross-section (target px).  ``d`` = mitred distance from the outer edge, ``dw`` = Chebyshev
distance outside the notched window (= 10.2 - d along the strips), so every ring is a function
of the distance across its strip and the 9-slice strips stretch cleanly:
    d  0.0-1.05  ink binding (outer corner r 2)
    d  1.05- / dw > 3.8   azurite brocade: lengthwise threads, 晕染 deepening to both edges
    dw 2.8-3.8   mud-gold rule
    dw 2.2-2.8   ink rule
    dw 0.6-2.2   ivory 隔水 strip
    dw 0.0-0.6   ink-brown hairline
    dw < 0       silk field (Paper): a soft ageing wash under the mount fading out by
                 dw -7; a faint, large ageing mottle only in the 9-slice centre (no fine
                 fibre texture: Slate stretches the centre up to ~8x)
Corners: window notch 5.2 px; flower centred 6.3 px from both edges (radius 3.3 px).
The Slate code pads panel content 14-18 px (10 px top in the log panel): nothing but the
corner steps reaches past d 10.2.
"""

import math

import numpy as np

from ironart import ui_chrome_paint as P
from ironart import ui_chrome_sdf as S

NAME = "Panel"
SPEC = dict(size=(128, 128), ss=4, margins=(24, 24, 24, 24), seed=11)
W = H = 128

INSET = 10.2        # window edge (the hairline's inner side) along the strips
NOTCH = 5.2
EDGE = 1.05


def brocade_color(G, d, t, seed, deep="brocade_blue_deep", blue="brocade_blue"):
    """Azurite silk brocade: 晕染 from ``deep`` at the band edges (t = 0) to ``blue`` mid-band,
    lengthwise threads as a function of ``d`` only."""
    base = P.mix(deep, blue, P.smoothstep(0.0, 2.3, t))
    n = 0.06 * P.noise1d(d, 0.30, seed, octaves=1) + 0.04 * P.noise1d(d, 1.2, seed + 1, 1)
    return base * (1.0 + n)[..., None]


def flower(C, G, cx, cy, r, seed, gold="gold", heart="cinnabar", rot=0.0):
    """Mud-gold four-petal flower (柿蒂) with a cinnabar heart."""
    sd = G.empty()
    for k in range(4):
        a = math.radians(rot + 90.0 * k)
        S.sd_circle(G, cx + 0.48 * r * math.cos(a), cy + 0.48 * r * math.sin(a), 0.46 * r, out=sd)
    g = P.gold_field(G, seed, flecks=0.0)
    C.over(P.aa(sd, G), P.mix(g * 0.8, g, P.smoothstep(0.0, 0.5, -sd)))
    C.over(P.aa(np.abs(sd) - 0.1 * r, G), "gold_deep", 0.9)
    dot = G.empty()
    S.sd_circle(G, cx, cy, 0.22 * r, out=dot)
    C.over(P.aa(dot, G), heart)


def paint(G, variant=None, seed=None):
    seed = SPEC["seed"] if seed is None else seed
    d = S.inset_distance(G, W, H, r=2.0)
    dw = P.notched_window(G, W, H, INSET, NOTCH)
    C = P.Canvas(G)
    shape = P.aa(-d, G)

    # ---- silk field -------------------------------------------------------------------------
    cw = P.centre_weight(G, SPEC["margins"], fade=10.0)
    tex = P.silk_texture(G, seed, weave=0.0, slub=0.0, mottle=0.009, mottle_cell=40.0)
    tex = 1.0 + (tex - 1.0) * cw
    age = 1.0 - P.smoothstep(0.0, 7.0, -dw)
    fcol = P.rgb("paper") * tex[..., None]
    fcol = P.mix(fcol, P.mix("paper", "silk_dark", 0.55), 0.5 * age ** 1.6)
    C.over(shape, fcol)

    # ---- mount ------------------------------------------------------------------------------
    t = np.minimum(d - EDGE, dw - 3.8)
    C.over(P.aa(3.8 - dw, G) * P.aa(EDGE - 0.15 - d, G), brocade_color(G, d, t, seed + 10))
    C.over(P.band(dw, 2.8, 3.8, G), P.strip_color(dw, "gold", seed + 12, amp=0.05, period=0.5))
    C.over(P.band(dw, 2.2, 2.8, G), "ink_ui")
    C.over(P.band(dw, 0.6, 2.2, G), P.strip_color(dw, "ivory", seed + 20, amp=0.015))
    C.over(P.band(dw, 0.0, 0.6, G), "ink_soft", 0.9)
    C.over(P.band(d, -5, EDGE, G) * shape, "ink")

    # ---- corner flowers ---------------------------------------------------------------------
    c = 6.3
    for (x, y) in ((c, c), (W - c, c), (c, H - c), (W - c, H - c)):
        flower(C, G, x, y, 3.3, seed + 30)
    return C.rgba()
