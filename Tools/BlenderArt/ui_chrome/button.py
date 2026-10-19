"""Button.png, Button_Hover.png, Button_Pressed.png, Button_Disabled.png (192x64 9-slice,
margins 20 / 16): cinnabar painted plaques (牌) with concave quarter-round corners (海棠角),
an ink outline and a mud-gold inner rule.

Cross-section (``d`` = distance inside the plaque outline, target px of the @1x art; the plaque
is inset 1 px from the canvas, its corners are concave arcs of radius 5):

    d 0.0-1.4    ink outline (warm black, the corner arcs drawn with a touch more weight)
    d 1.4-9      晕染: the cinnabar deepens into the outline
    d 3.5-4.5    mud-gold inner rule following the outline (concave corners included)
    d 4.5-5.0    pale lead-white hairline (提白) inside the rule (normal / hover)
    field        cinnabar with a soft vertical wash (paler band above the middle, deeper
                 towards the bottom) and faint horizontal brush streaks - all functions of y
                 in the strips, so Slate can stretch the button to any width

States
    normal    cinnabar #B5382A
    hover     brighter, towards vermilion, with a soft mud-gold wash across the middle rows
    pressed   deeper cinnabar, the wash inverted (darker on top: pressed in), the gold rule
              inset by 1 px with an ink hairline outside it (an inset double rule)
    disabled  ink-grey wash (墨灰) with a greyed rule and a soft ink outline

Corners: a small mud-gold cloud curl sits in each corner pocket inside the rule.
Labels: Body-Bold 16, TextLight with the 1 px dark shadow the Slate code draws.
"""

import math

import numpy as np

from ironart import ui_chrome_gongbi as GB
from ironart import ui_chrome_ornament as O
from ironart import ui_chrome_paint as P
from ironart import ui_chrome_sdf as S

NAME = "Button"
SPEC = dict(size=(192, 64), ss=4, margins=(20, 16, 20, 16), seed=41)
W, H = 192, 64
VARIANTS = ("normal", "hover", "pressed", "disabled")
FILE = {"normal": "Button", "hover": "Button_Hover", "pressed": "Button_Pressed",
        "disabled": "Button_Disabled"}

INSET = 1.0
CORNER = 5.0
OUTLINE = 1.4

#: per state: field, deep (晕染 edge), pale (wash), outline, rule gold, highlight opacity
STATES = {
    "normal": dict(field="#B5382A", deep="#7C2118", pale="#C3493A", outline="#1E1A16",
                   gold="#C9A24B", hi=0.55, rule=(3.5, 4.5)),
    "hover": dict(field="#C4472F", deep="#86281B", pale="#D46446", outline="#1E1A16",
                  gold="#D8B565", hi=0.65, rule=(3.5, 4.5), wash=0.30),
    "pressed": dict(field="#982B20", deep="#5C1811", pale="#A93527", outline="#1E1A16",
                    gold="#B8913F", hi=0.0, rule=(4.5, 5.5), inset_line=(3.6, 4.1)),
    "disabled": dict(field="#6D655D", deep="#463F39", pale="#7A726A", outline="#3A322B",
                     gold="#9A9078", hi=0.25, rule=(3.5, 4.5)),
}


def plaque_d(G):
    """Distance inside the plaque outline (positive inside): a box inset 1 px with concave
    quarter-circle corners."""
    sd = P.plaque_sd(G, W, H, inset=INSET, notch=CORNER)
    return -sd


def corner_curl(G, variant):
    """sd of the four corner ornaments: a small ruyi head inside the rule's concave corner,
    pointing into the corner (built top-left, mirrored)."""
    st = STATES[variant]
    c = INSET + st["rule"][1] + 2.9
    sd, _ = O.ruyi(G, c, c, 2.5, rot=135.0, curls=False)
    return GB.mirror4(sd)


def paint(G, variant="normal", seed=None):
    variant = variant or "normal"
    st = STATES[variant]
    seed = SPEC["seed"] if seed is None else seed
    d = plaque_d(G)
    C = P.Canvas(G)
    inside = S.aa_mask(-d, G)
    y = G.Y
    # ---- the cinnabar wash: vertical wash x 晕染 into the outline, brush streaks along x ----
    v = (y - INSET) / (H - 2 * INSET)
    if variant == "pressed":
        wash = 0.35 * P.smoothstep(0.25, 0.85, v) - 0.35 * (1.0 - P.smoothstep(0.0, 0.35, v))
    else:
        wash = 0.55 * np.exp(-((v - 0.40) / 0.22) ** 2) - 0.30 * P.smoothstep(0.55, 1.0, v)
    col = P.mix(st["field"], st["pale"], np.clip(wash, 0, 1))
    col = P.mix(col, st["deep"], np.clip(-wash, 0, 1) * 0.6)
    k = P.smoothstep(0.0, 9.0, d - OUTLINE) ** 0.7
    col = P.mix(st["deep"], col, k)
    streak = P.noise1d(G.ys, 2.5, seed + 1, octaves=2) * 0.008 \
        + P.noise1d(G.ys, 0.6, seed + 2, octaves=1) * 0.004
    col = col * (1.0 + streak[:, None])[..., None]
    if st.get("wash"):
        # hover: a soft mud-gold glaze across the middle rows, fading in the end margins
        ends = P.smoothstep(4.0, 18.0, np.minimum(G.X, W - G.X))
        gw = st["wash"] * np.exp(-((v - 0.48) / 0.26) ** 2) * ends
        col = P.mix(col, P.rgb("#E2B866"), gw * 0.55)
    C.over(inside, col)

    # ---- inner rules --------------------------------------------------------------------------
    r0, r1 = st["rule"]
    gthr = GB.strip_threads(d, seed + 3, pitch=0.5, amp=0.04, gap=0.15, slow=0.02)
    gold = P.rgb(st["gold"]) * gthr[..., None]
    gold = gold * (1.0 - 0.12 * (1.0 - P.smoothstep(r0, r0 + 0.35, d))
                   - 0.12 * P.smoothstep(r1 - 0.35, r1, d))[..., None]
    if st.get("inset_line"):
        a, b = st["inset_line"]
        C.over(GB.band(d, a, b, G), "#3A140E", 0.85)
    C.over(GB.band(d, r0, r1, G), gold)
    if st["hi"] > 0:
        C.over(GB.band(d, r1 + 0.05, r1 + 0.55, G), "#F0E2C8", st["hi"] * 0.55)

    # ---- corner curls -----------------------------------------------------------------------
    curl = corner_curl(G, variant)
    C.over(S.aa_mask(curl, G), GB.mud_gold(G, curl, seed + 5, base=st["gold"], yun=0.0,
                                            gran=0.03, flecks=0.0, pool=0.12, pool_w=0.3))

    # ---- ink outline --------------------------------------------------------------------------
    ink = GB.ink_density(G, seed + 6, st["outline"], var=0.0)
    C.over(GB.band(d, -1.0, OUTLINE, G) * inside, ink)
    C.erase(1.0 - inside)
    return C.rgba()
