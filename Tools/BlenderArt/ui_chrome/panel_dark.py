"""PanelDark.png (128x128 9-slice, 24 px margins, Slate Box brush): ink-dark silk with a thin
mud-gold (泥金) painted border and cloud-thunder (云雷纹) brackets in the corners - every line on
whole @1x pixels, the gold at full #C9A24B.

Cross-section (``k`` = whole pixels from the outer edge, identical along the strips):

    k 0        deep umber edge #33261C (the silk turned over the board)
    k 1        ink silk
    k 2        mud-gold rule
    k 3-4      ink silk
    k 5        mud-gold rule
    k >= 6     ink-dark silk field #1E1A16 (Night +-4): a faint umber 晕染 under the rules
               (+4 levels at k 6, gone by k 11) and a large faint mottle (+-2 levels) in the
               9-slice centre only - no glow

Corners: a 16 x 16 cloud-thunder bracket (k 8-23): an L of 1 px mud-gold lines along both edges
with a hook at each arm's end and a squared spiral (回) in the corner, lines on a 3 px pitch
(1 px gold, 2 px gaps) like the rules (ironart.ui_chrome_pixel.bracket).
Text on it: TextLight / Gold.
"""

import numpy as np

from ironart import ui_chrome_paint as P
from ironart import ui_chrome_pixel as X
from ironart import ui_chrome_sdf as S
import panel

NAME = "PanelDark"
SPEC = dict(size=(128, 128), ss=4, margins=(24, 24, 24, 24), seed=21)
W = H = 128
FIELD = "#1E1A16"
UMBER = "#33261C"
GOLD = "#C9A24B"
STRIP = [UMBER, FIELD, GOLD, FIELD, FIELD, GOLD]
THREADS = [0.04, 0.0, 0.035, 0.0, 0.0, 0.035]
BRACKET_AT = 8


def paint(G, variant=None, seed=None):
    seed = SPEC["seed"] if seed is None else seed
    lay, k = panel.strip_layer(W, H, STRIP, FIELD)
    m = np.zeros((H, W), bool)
    X.mirror4_place(m, X.bracket(), BRACKET_AT, BRACKET_AT)
    lay[m, :3] = P.rgb(GOLD)
    big = X.up(lay, G.ss)
    d = S.inset_distance(G, W, H)
    haze = (1.0 - P.smoothstep(6.0, 11.0, d)) * (d >= len(STRIP))
    field = P.mix(FIELD, "#2A2119", 0.45 * haze)
    cw = P.centre_weight(G, SPEC["margins"], fade=10.0)
    mott = P.fbm2(G, 40.0, seed + 1, octaves=2, gain=0.45)
    field = field * (1.0 + 0.06 * np.clip(mott, -2.2, 2.2) / 2.2 * cw)[..., None]
    plain = X.up((k >= len(STRIP)) & ~m, G.ss)
    rgb = np.where(plain[..., None], field, big[..., :3])
    rgb = rgb * panel.across_threads(G, W, H, THREADS)[..., None]
    out = np.concatenate([np.clip(rgb, 0, 1), big[..., 3:4]], -1)
    return out.astype(np.float32)
