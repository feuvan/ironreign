"""Tab.png / Tab_Active.png (160x48 9-slice, margins l 18, t 14, r 18, b 10): light silk-paper
tabs edged with brocade along the top and sides, concave (委角) top corners, open bottom.

Cross-section from the top / side edges (d, target px):
    0.0-1.1   ink outline
    1.1-4.5   brocade edge: azurite (inactive) / cinnabar (active), 晕染 to both edges,
              lengthwise threads; a mud-gold thread at 3.7-4.25 (active: brighter)
    4.5-5.05  ink hairline
    field     light silk paper with a soft vertical wash (paler at the top); the inactive tab
              ends in an ink-brown hairline 1.2 px above the bottom edge (it sits *behind* the
              page), the active tab stays open at the bottom (joined to the page)
The Slate code tints the inactive tab x0.78 (normal) and shows it unmodified on hover.
Labels must be dark: Ink (#2A2119) on both, Lacquer or bold Ink on the active tab - the
light silk does not carry TextLight / Gold labels.
"""

import numpy as np

from ironart import ui_chrome_paint as P
from ironart import ui_chrome_sdf as S

NAME = "Tab"
SPEC = dict(size=(160, 48), ss=4, margins=(18, 14, 18, 10), seed=31)
W, H = 160, 48
VARIANTS = ("inactive", "active")
FILE = {"inactive": "Tab", "active": "Tab_Active"}
EXT = 24.0          # the shape continues below the image (open bottom)


def paint(G, variant="inactive", seed=None):
    seed = SPEC["seed"] if seed is None else seed
    active = variant == "active"
    # plaque taller than the image: only its top corners are in frame
    box = S.sd_round_box(G, W / 2.0, (H + EXT) / 2.0, W / 2.0 - 1.0, (H + EXT) / 2.0 - 1.0, 0.0)
    q = None
    for x in (1.0, W - 1.0):
        c = np.hypot(G.X - x, G.Y - 1.0) - 4.0
        q = c if q is None else np.minimum(q, c)
    sd = np.maximum(box, -q)
    d = -sd
    C = P.Canvas(G)
    shape = P.aa(sd, G)

    # ---- field ----------------------------------------------------------------------------------
    v = np.broadcast_to((G.Y - 1.0) / (H - 2.0), G.shape)
    top, low = ("#F3EBD8", "#E6DBC2") if active else ("#EDE3CC", "#DED1B5")
    fcol = P.mix(top, low, P.smoothstep(0.1, 1.0, v))
    rim = 1.0 - P.smoothstep(4.8, 10.0, d)
    fcol = P.mix(fcol, "silk_dark", 0.35 * rim ** 1.5)
    C.over(shape, fcol)

    # ---- brocade edge -------------------------------------------------------------------------
    t = 1.0 - np.abs(d - 2.8) / 1.7
    if active:
        bcol = P.mix("#7A2018", "cinnabar", P.smoothstep(0.0, 0.8, t))
    else:
        bcol = P.mix("brocade_blue_deep", "brocade_blue", P.smoothstep(0.0, 0.8, t))
    bcol = bcol * (1.0 + 0.06 * P.noise1d(d, 0.3, seed + 3, 1))[..., None]
    C.over(P.band(d, 0.9, 4.5, G), bcol)
    gold = P.strip_color(d, "gold_light" if active else "gold", seed + 4, amp=0.05)
    C.over(P.band(d, 3.7, 4.25, G), gold, 0.95)
    C.over(P.band(d, 4.5, 5.05, G), "ink_ui")
    C.over(P.band(d, -3.0, 1.1, G) * shape, "ink")
    if not active:
        y = np.broadcast_to(G.Y, G.shape)
        C.over(P.band(y, H - 1.8, H - 1.2, G) * P.aa(1.0 - d, G), "ink_soft", 0.85)
    return C.rgba()
