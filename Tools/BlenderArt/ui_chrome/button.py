"""Button.png, Button_Hover.png, Button_Pressed.png, Button_Disabled.png (192x64 9-slice,
margins 20 / 16): flat cinnabar painted plaques (牌) with true concave quarter-circle corners
(委角, r 6 px), an ink outline and a mud-gold inner rule that follows the notches.

Cross-section (``d`` = px inside the plaque outline; the plaque is inset 1 px from the canvas,
so every straight rule lands on whole @1x pixels):

    d 0-1      ink outline #1E1A16 (canvas row / column 1)
    d 1-4      晕染: the only gradient - the colour deepens over these 3 px into the outline
    d 4-5      mud-gold rule (pressed: an ink hairline here and the gold 1 px further in)
    field      flat colour, +-1.5 levels of horizontal brush streaks (a function of y only)

States (field, 晕染 edge colour, rule)
    normal    cinnabar #B5382A -> #8E2A20, mud-gold #C9A24B                      TextLight 4.8:1
    hover     a warmer, more saturated cinnabar of the *same* luminance (#BA3624, 4.7:1);
              the cue is at the rim: the 晕染 brightens towards vermilion, the rule is a
              paler gold and a 2 px mud-gold wash (35 %) lines the inside of the rule
    pressed   deeper cinnabar #962A20 -> #5E1A13, inset double rule                  6.4:1
    disabled  ink-grey #5E5750 -> #48423C, greyed rule, soft ink outline; the label is drawn
              #D8CFBF with no Slate DisabledEffect                                 4.6:1
Corners: a small mud-gold cloud-thunder hook (云雷纹, 1 px lines) in each corner pocket inside
the rule, mirrored.  Labels: Body-Bold 16; the QA asserts >= 4.5:1 for the worst pixel of the
label zone (x 24-168, y 26-38) in every state.
"""

import numpy as np

from ironart import ui_chrome_paint as P
from ironart import ui_chrome_pixel as X
from ironart import ui_chrome_sdf as S

NAME = "Button"
SPEC = dict(size=(192, 64), ss=4, margins=(20, 16, 20, 16), seed=41)
W, H = 192, 64
VARIANTS = ("normal", "hover", "pressed", "disabled")
FILE = {"normal": "Button", "hover": "Button_Hover", "pressed": "Button_Pressed",
        "disabled": "Button_Disabled"}

INSET = 1.0
NOTCH = 6.0
#: label colour per state (what the Slate code should draw; the QA measures against it)
LABEL = {"normal": (243, 232, 207), "hover": (243, 232, 207), "pressed": (243, 232, 207),
         "disabled": (216, 207, 191)}
STATES = {
    "normal": dict(field="#B5382A", edge="#8E2A20", outline="#1E1A16", gold="#C9A24B",
                   rule=(4.0, 5.0)),
    "hover": dict(field="#BA3624", edge="#D0643C", outline="#1E1A16", gold="#E0C47E",
                  rule=(4.0, 5.0), rim=0.35),
    "pressed": dict(field="#962A20", edge="#5E1A13", outline="#1E1A16", gold="#B8913F",
                    rule=(5.0, 6.0), inset_line=(4.0, 5.0)),
    "disabled": dict(field="#5E5750", edge="#48423C", outline="#3A322B", gold="#8F8670",
                     rule=(4.0, 5.0)),
}
#: corner hook (top-left orientation), 1 px lines, placed with its corner at (HOOK, HOOK)
HOOK_PATHS = [[(0, 4), (0, 0), (4, 0), (4, 4), (2, 4), (2, 2)]]
HOOK = 10


def plaque_d(G):
    """Distance inside the plaque outline (positive inside)."""
    return -P.plaque_sd(G, W, H, inset=INSET, notch=NOTCH)


def hooks():
    m = np.zeros((5, 5), bool)
    for p in HOOK_PATHS:
        X.draw_path(m, p)
    full = np.zeros((H, W), bool)
    return X.mirror4_place(full, m, HOOK, HOOK)


def paint(G, variant="normal", seed=None):
    variant = variant or "normal"
    st = STATES[variant]
    seed = SPEC["seed"] if seed is None else seed
    d = plaque_d(G)
    C = P.Canvas(G)
    inside = S.aa_mask(-d, G)
    # ---- flat field + horizontal brush streaks (y only: stretch-safe) ------------------------
    streak = P.noise1d(G.ys, 3.0, seed + 1, octaves=2) * 0.006
    col = P.rgb(st["field"]) * (1.0 + streak[:, None, None])
    col = np.broadcast_to(col, G.shape + (3,)).copy()
    # ---- 晕染 over the 3 px next to the outline -------------------------------------------
    k = P.smoothstep(1.0, 4.0, d)
    col = P.mix(st["edge"], col, k ** 0.8)
    C.over(inside, col)
    # ---- hover: a soft mud-gold wash lining the inside of the rule ---------------------------
    r0, r1 = st["rule"]
    if st.get("rim"):
        C.over(S.band(d, r1, r1 + 2.0, G), "#C9A24B", st["rim"])
    # ---- rules ---------------------------------------------------------------------------------
    if st.get("inset_line"):
        C.over(S.band(d, *st["inset_line"], G), "#2A120D", 0.9)
    C.over(S.band(d, r0, r1, G), st["gold"])
    # ---- corner hooks (pixel grid) --------------------------------------------------------------
    hk = X.up(hooks().astype(np.float32), G.ss)
    C.over(hk, st["gold"])
    # ---- ink outline -----------------------------------------------------------------------------
    C.over(S.band(d, -1.0, 1.0, G) * inside, st["outline"])
    C.erase(1.0 - inside)
    return C.rgba()
