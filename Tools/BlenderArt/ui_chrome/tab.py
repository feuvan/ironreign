"""Tab.png / Tab_Active.png (160x48 9-slice, margins l 18, t 14, r 18, b 10): light silk-paper
tabs edged with silk brocade along the top and sides, concave (海棠) top corners, open bottom.

Cross-section from the top / side edges (``d``, target px of the @1x art; functions of d only
inside the strips):

    d 0.0-1.0   ink binding
    d 1.0-4.0   brocade edge: azurite (inactive) / cinnabar (active), lengthwise threads, 晕染
                deepening to both edges
    d 4.0-5.0   mud-gold rule (active: brighter)
    d 5.0-5.5   ink hairline (60 %)
    field       light silk paper (Paper, paler towards the top); the inactive tab ends in an
                ink-brown hairline 1 px above its bottom edge (it sits *behind* the page), the
                active tab stays open at the bottom (it joins the page below)

The Slate code tints the inactive tab x0.78 (normal) and shows it unmodified on hover.
Labels must be dark: Ink (#2A2119) on both, Lacquer or bold Ink on the active tab - the light
silk does not carry TextLight / Gold labels.
"""

import numpy as np

from ironart import ui_chrome_gongbi as GB
from ironart import ui_chrome_paint as P
from ironart import ui_chrome_sdf as S

NAME = "Tab"
SPEC = dict(size=(160, 48), ss=4, margins=(18, 14, 18, 10), seed=31)
W, H = 160, 48
VARIANTS = ("inactive", "active")
FILE = {"inactive": "Tab", "active": "Tab_Active"}
EXT = 24.0          # the shape continues below the image (open bottom)
CORNER = 4.0

EDGES = {
    "inactive": dict(blue="#46667F", deep="#223B53", gold="#B8934A", field="#E9DCC0",
                     top="#F1E8D4"),
    "active": dict(blue="#B23A2B", deep="#76201A", gold="#D2AE5C", field="#E9DCC0",
                   top="#F4ECDB"),
}


def paint(G, variant="inactive", seed=None):
    variant = variant or "inactive"
    e = EDGES[variant]
    seed = SPEC["seed"] if seed is None else seed
    # the plaque continues EXT px below the image, so its bottom is open
    sd = P.plaque_sd(_ext_grid(G), W, H + EXT, inset=1.0, notch=CORNER)[: G.ny]
    d = -sd
    C = P.Canvas(G)
    inside = S.aa_mask(sd, G)
    # strip orientation: top strip (y) vs side strips (x), switching on the mitre diagonals
    axis = (np.minimum(G.Y, 99.0) <= np.minimum(G.X, W - G.X)).astype(np.float32)

    # ---- silk field: paler towards the top, Paper towards the bottom ------------------------
    v = np.clip((G.Y - 5.0) / (H - 5.0), 0, 1)
    fcol = P.mix(e["top"], e["field"], P.smoothstep(0.0, 0.9, v))
    C.over(inside, fcol)

    # ---- brocade edge -------------------------------------------------------------------------
    t = np.minimum(d - 1.0, 4.0 - d)
    base = P.mix(e["deep"], e["blue"], P.smoothstep(0.0, 1.4, t) ** 0.8)
    thr = GB.strip_threads(d, seed, pitch=0.42, amp=0.06, gap=0.45, slow=0.02, slow_period=1.4)
    thr2 = GB.strip_threads(d + 0.19, seed + 3, pitch=0.42, amp=0.06, gap=0.45, slow=0.02,
                            slow_period=1.4)
    thr = thr * axis + thr2 * (1.0 - axis)
    C.over(GB.band(d, 0.7, 4.0, G) * inside, base * thr[..., None])
    gthr = GB.strip_threads(d, seed + 5, pitch=0.5, amp=0.04, gap=0.15)
    gold = P.rgb(e["gold"]) * gthr[..., None]
    C.over(GB.band(d, 4.0, 5.0, G), gold)
    C.over(GB.band(d, 5.0, 5.5, G), "#2A2119", 0.6)
    C.over(GB.band(d, -2.0, 1.0, G) * inside, "#1E1A16")
    if variant == "inactive":
        # a hairline where the tab tucks behind the page
        C.over(GB.band(G.Y * np.ones_like(d), H - 1.0, H, G) * S.aa_mask(-(d - 1.0), G),
               "#6B5844", 0.8)
    C.erase(1.0 - inside)
    return C.rgba()


class _ext_grid:
    """Grid view extended EXT px downwards (same sampling) for the open-bottom plaque."""

    def __new__(cls, G):
        return S.Grid(G.w, G.h + EXT, G.ss)
