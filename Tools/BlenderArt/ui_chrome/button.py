"""Button.png, Button_Hover.png, Button_Pressed.png, Button_Disabled.png (192x64 9-slice,
margins 20 / 16): cinnabar painted plaques (牌) with concave quarter-round corners (委角),
a calligraphic-weight ink outline and a mud-gold inner rule.

Cross-section (d = distance inside the plaque outline, target px; the plaque is inset 1 px):
    0.0-1.45  ink outline
    1.45-7.5  晕染: the cinnabar wash deepens into the outline
    4.1-5.05  mud-gold inner rule (pressed: 5.1-6.05, plus an ink hairline at 3.6-4.15)
    field     cinnabar with a soft vertical wash (paler band at 36 % of the height, deeper
              towards the bottom)
States
    normal    cinnabar #B5382A field
    hover     brighter: towards vermilion, with a soft mud-gold wash across the middle and a
              brighter gold rule (TextLight label stays >= 3:1)
    pressed   deeper cinnabar, wash inverted (paler low), inset double rule
    disabled  ink-grey wash (墨灰), greyed rule, soft ink outline
Labels: Body-Bold 16, TextLight with the 1 px dark shadow the Slate code draws.
"""

import numpy as np

from ironart import ui_chrome_paint as P
from ironart import ui_chrome_sdf as S

NAME = "Button"
SPEC = dict(size=(192, 64), ss=4, margins=(20, 16, 20, 16), seed=41)
W, H = 192, 64
VARIANTS = ("normal", "hover", "pressed", "disabled")
FILE = {"normal": "Button", "hover": "Button_Hover", "pressed": "Button_Pressed",
        "disabled": "Button_Disabled"}

#: field, deep edge, pale wash colours per state
COLS = {
    "normal": ("cinnabar", "#7A2018", "#C44A35"),
    "hover": ("#BF412D", "#86271B", "#CD563B"),
    "pressed": ("#962A1F", "#5A1711", "#A93629"),
    "disabled": ("#6B635B", "#423C37", "#7B726A"),
}


def paint(G, variant="normal", seed=None):
    seed = SPEC["seed"] if seed is None else seed
    variant = variant or "normal"
    sd = P.plaque_sd(G, W, H, inset=1.0, notch=4.5)
    d = -sd
    C = P.Canvas(G)
    shape = P.aa(sd, G)
    mid, edge, pale = COLS[variant]
    v = (G.Y - 1.0) / (H - 2.0)
    v = np.broadcast_to(v, G.shape)

    # ---- the wash -----------------------------------------------------------------------------
    if variant == "pressed":
        wash = np.exp(-((v - 0.62) / 0.32) ** 2)
        low = 0.45 * (1.0 - P.smoothstep(0.0, 0.45, v))
    else:
        wash = np.exp(-((v - 0.36) / 0.30) ** 2)
        low = 0.35 * P.smoothstep(0.55, 1.0, v)
    fcol = P.mix(mid, pale, 0.55 * wash)
    fcol = P.mix(fcol, edge, low)
    rim = 1.0 - P.smoothstep(1.2, 7.5, d)
    fcol = P.mix(fcol, edge, 0.85 * rim ** 1.5)
    C.over(shape, fcol)
    if variant == "hover":
        glow = np.exp(-((v - 0.45) / 0.28) ** 2) * P.smoothstep(3.0, 9.0, d)
        C.over(glow, "gold_light", 0.13)

    # ---- mud-gold inner rule ------------------------------------------------------------------
    gold = P.strip_color(d, "gold", seed + 2, amp=0.06, period=0.45)
    if variant == "disabled":
        gold = P.mix(gold, "#8E8576", 0.85)
    elif variant == "hover":
        gold = P.mix(gold, "gold_light", 0.35)
    if variant == "pressed":
        C.over(P.rule(d, 5.58, 0.95, G), gold)
        C.over(P.rule(d, 3.88, 0.55, G), "#3A0F0B", 0.9)
    else:
        C.over(P.rule(d, 4.58, 0.95, G), gold)

    # ---- ink outline --------------------------------------------------------------------------
    ink = "#3B3632" if variant == "disabled" else "ink"
    C.over(P.band(d, -3.0, 1.45, G) * shape, ink)
    return C.rgba()
