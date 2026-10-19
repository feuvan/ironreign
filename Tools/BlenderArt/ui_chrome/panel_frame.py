"""Panel_Frame.png / PanelDark_Frame.png (128x128, 24 px margins, transparent middle): the panel
mounts as Slate **Border** brushes (ESlateBrushDrawType::Border: corners 1:1, the sides *tile*,
the middle is not drawn), to be drawn over the tiling silk fills Panel_Silk.png /
PanelDark_Silk.png.  Because the sides tile instead of stretching, the brocade carries a real
repeating pattern: an 8 px key-fret (回纹) whose period divides the 80 px side segment
(x / y 24-103), so the repeats join seamlessly.

Panel_Frame (k = whole pixels from the outer edge):
    k 0        ink binding
    k 1        deep azurite #22476B
    k 2-7      key-fret band: 1 px mud-gold #C9A24B lines on azurite #2B5C8A, 8 px period,
               on the @1x pixel grid (2 px lines at @2x), the fret's top thread outermost
    k 8        deep azurite
    k 9        ink rule
    k 10       ivory 隔水 strip #F0E8D8
    k 11-22    transparent, with an ageing glaze (umber, 12 % at k 11 fading out by k 22) that
               deepens the silk fill under it towards the mount, as on Panel.png
    corners    the 10 x 10 brocade block with the 柿蒂 rosette (as Panel.png)
PanelDark_Frame: PanelDark.png's umber edge, ink silk and double mud-gold rule (k 0-5), the
cloud-thunder brackets in the corners, the field transparent with a faint umber haze glaze.
"""

import numpy as np

from ironart import ui_chrome_paint as P
from ironart import ui_chrome_pixel as X
from ironart import ui_chrome_sdf as S
import panel
import panel_dark

NAME = "Panel_Frame"
SPEC = dict(size=(128, 128), ss=4, margins=(24, 24, 24, 24), seed=17)
W = H = 128
VARIANTS = ("light", "dark")
FILE = {"light": "Panel_Frame", "dark": "PanelDark_Frame"}
INK, AZ_DEEP, AZ, GOLD, IVORY = panel.INK, panel.AZ_DEEP, panel.AZ, panel.GOLD, panel.IVORY
STRIP = [INK, AZ_DEEP, AZ, AZ, AZ, AZ, AZ, AZ, AZ_DEEP, INK, IVORY]
THREADS = [0.0, 0.05, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.0, 0.012]
FRET_K = 2                    # first row of the fret band
BLOCK = 10


def fret_mask(w, h, k0=FRET_K, start=BLOCK):
    """Boolean @1x mask of the key-fret on all four strips, between the corner blocks; the
    phase is anchored at ``start`` on every side (period 8 divides the 80 px tile segment)."""
    m = np.zeros((h, w), bool)
    L = w - 2 * start
    band = X.fret_band(L)                             # (6, L), top thread in row 0
    m[k0:k0 + 6, start:start + L] |= band
    m[h - k0 - 6:h - k0, start:start + L] |= band[::-1]
    Lv = h - 2 * start
    bandv = X.fret_band(Lv).T                         # (Lv, 6), top thread in column 0
    m[start:start + Lv, k0:k0 + 6] |= bandv
    m[start:start + Lv, w - k0 - 6:w - k0] |= bandv[:, ::-1]
    return m


def corner_blocks(lay, w, h):
    blk = X.rosette_block()
    for fy in (False, True):
        for fx in (False, True):
            b = blk[::-1] if fy else blk
            b = b[:, ::-1] if fx else b
            lay[(slice(h - BLOCK, h) if fy else slice(0, BLOCK)),
                (slice(w - BLOCK, w) if fx else slice(0, BLOCK))] = b
    return lay


def paint(G, variant="light", seed=None):
    variant = variant or "light"
    seed = SPEC["seed"] if seed is None else seed
    d = S.inset_distance(G, W, H)
    if variant == "light":
        lay, k = panel.strip_layer(W, H, STRIP, IVORY)
        fm = fret_mask(W, H)
        lay[fm, :3] = P.rgb(GOLD)
        corner_blocks(lay, W, H)
        lay[k >= len(STRIP), 3] = 0.0
        big = X.up(lay, G.ss)
        rgb = big[..., :3] * panel.across_threads(G, W, H, THREADS)[..., None]
        a = big[..., 3]
        glaze = (1.0 - P.smoothstep(11.0, 22.0, d)) ** 1.4 * 0.12 * (d >= len(STRIP))
        rgb = np.where(a[..., None] > 0, rgb, P.rgb("#6E5232"))
        a = np.maximum(a, glaze)
    else:
        lay, k = panel.strip_layer(W, H, panel_dark.STRIP, panel_dark.FIELD)
        m = np.zeros((H, W), bool)
        X.mirror4_place(m, X.bracket(), panel_dark.BRACKET_AT, panel_dark.BRACKET_AT)
        lay[m, :3] = P.rgb(panel_dark.GOLD)
        lay[(k >= len(panel_dark.STRIP)) & ~m, 3] = 0.0
        big = X.up(lay, G.ss)
        rgb = big[..., :3] * panel.across_threads(G, W, H, panel_dark.THREADS)[..., None]
        a = big[..., 3]
        haze = (1.0 - P.smoothstep(6.0, 11.0, d)) * 0.35 * (d >= len(panel_dark.STRIP))
        rgb = np.where(a[..., None] > 0, rgb, P.rgb("#2E2219"))
        a = np.maximum(a, haze)
    out = np.concatenate([np.clip(rgb, 0, 1), a[..., None]], -1)
    return out.astype(np.float32)
