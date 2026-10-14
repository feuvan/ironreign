"""PanelDark.png (128x128 9-slice, 24 px margins): ink-dark silk with a painted mud-gold (泥金)
border and mud-gold ruyi cloud heads (如意云头) in the corners.

Cross-section (d = mitred distance from the outer edge, target px; rings depend on d only):
    0.0-0.9   ink edge
    0.9-4.0   deep-umber edge silk, 晕染 lighter towards its middle, lengthwise threads
    4.0-5.1   mud-gold rule (gold powder grain along the rule)
    5.1-6.3   ink silk
    6.3-6.8   mud-gold hairline (75 %)
    6.8-      ink-dark silk field #1E1A16 (Night +-3) with a faint deep-umber glow and silk
              texture in the 9-slice centre only
Corners: ruyi heads 12 px, centred 9 px from both edges, pointing into the panel, painted in
mud-gold with engraved curls; a halo of field colour interrupts the rules behind them.
Text on it: TextLight / Gold.
"""

import numpy as np

from ironart import ui_chrome_paint as P
from ironart import ui_chrome_sdf as S

NAME = "PanelDark"
SPEC = dict(size=(128, 128), ss=4, margins=(24, 24, 24, 24), seed=21)
W = H = 128
FIELD = "#1E1A16"
GLOW = "#2A2119"
RUYI = dict(c=9.0, size=12.0, rot=315.0)


def paint(G, variant=None, seed=None):
    seed = SPEC["seed"] if seed is None else seed
    d = S.inset_distance(G, W, H, r=1.5)
    C = P.Canvas(G)
    shape = P.aa(-d, G)

    # ---- field: ink silk with a faint umber glow in the centre ------------------------------
    cw = P.centre_weight(G, SPEC["margins"], fade=14.0)
    tex = P.silk_texture(G, seed, weave=0.0, slub=0.0, mottle=0.018, mottle_cell=40.0)
    u = (G.X - W / 2) / (W / 2 - 24)
    v = (G.Y - H / 2) / (H / 2 - 24)
    glow = np.clip(1.0 - (u * u + v * v) / 2.0, 0, 1) ** 1.5 * cw
    fcol = P.mix(FIELD, GLOW, 0.55 * glow) * (1.0 + (tex - 1.0) * cw)[..., None]
    C.over(shape, fcol)

    # ---- border -----------------------------------------------------------------------------
    t = 1.0 - np.abs(d - 2.45) / 1.55
    edge = P.mix("#241C15", "#3A2C21", P.smoothstep(0.0, 0.9, t))
    edge = edge * (1.0 + 0.06 * P.noise1d(d, 0.3, seed + 3, 1))[..., None]
    C.over(P.band(d, 0.8, 4.0, G), edge)
    C.over(P.band(d, 4.0, 5.1, G), P.strip_color(d, "gold", seed + 4, amp=0.06, period=0.45))
    C.over(P.band(d, 6.3, 6.8, G), P.strip_color(d, "gold", seed + 5, amp=0.05), 0.75)
    C.over(P.band(d, -5, 0.9, G) * shape, "#110E0B")

    # ---- corners: ruyi cloud heads -----------------------------------------------------------
    c, size, rot = RUYI["c"], RUYI["size"], RUYI["rot"]
    for (x, y, r) in ((c, c, rot), (W - c, c, rot + 90), (W - c, H - c, rot + 180),
                      (c, H - c, rot + 270)):
        P.paint_ruyi(C, G, x, y, size, r, seed + 7, halo=FIELD, halo_w=0.9, engrave="#2E2318")
    return C.rgba()
