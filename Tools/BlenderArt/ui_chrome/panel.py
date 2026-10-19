"""Panel.png (128x128 9-slice, 24 px margins, Slate Box brush): an aged silk leaf in a woven
brocade mount (装裱), every rule on whole @1x pixels.

Cross-section of the mount strip, ``k`` = whole pixels from the outer edge (identical along the
strip, so Slate can stretch it; the @2x master splits some stripes into two threads):

    k 0        ink binding #1E1A16
    k 1-2      deep azurite brocade #22476B (two threads at @2x)
    k 3        mud-gold thread #C9A24B
    k 4-6      azurite brocade #2B5C8A with a raised rib (k 5, +5 levels)
    k 7        mud-gold thread #C9A24B
    k 8        deep azurite #22476B
    k 9        ink rule #1E1A16
    k 10       ivory 隔水 strip, lead white #F0E8D8
    k >= 11    silk field (Paper #E9DCC0): an ageing wash deepens it towards the mount
               (about -10 levels at k 11, gone by k 22); a large faint mottle (+-4 levels,
               features >= 16 px) only in the 9-slice centre, which Slate stretches

Corners: a 10 x 10 brocade block (k 0-9 on both axes, its inner contour on the k 9 ink rule)
with a woven 柿蒂 rosette - mud-gold petals with an ochre 分染 side, ink contour, a 2 x 2
cinnabar heart (ironart.ui_chrome_pixel); the ivory strip turns the corner around it.
Everything is inside the 24 px margins; content padding of 11 px or more clears the mount.
A real repeating brocade needs Border (tiled) strips: see panel_frame.py / Panel_Frame.png.
"""

import numpy as np

from ironart import ui_chrome_paint as P
from ironart import ui_chrome_pixel as X
from ironart import ui_chrome_sdf as S

NAME = "Panel"
SPEC = dict(size=(128, 128), ss=4, margins=(24, 24, 24, 24), seed=11)
W = H = 128

INK = "#1E1A16"
AZ_DEEP = "#22476B"
AZ = "#2B5C8A"
AZ_RIB = "#30618F"            # +5 levels
GOLD = "#C9A24B"
IVORY = "#F0E8D8"
PAPER = "#E9DCC0"
#: the woven mount, outermost pixel first
STRIP = [INK, AZ_DEEP, AZ_DEEP, GOLD, AZ, AZ_RIB, AZ, GOLD, AZ_DEEP, INK, IVORY]
#: per stripe: (amplitude of the two-thread split the @2x master shows, 0 = none)
THREADS = [0.0, 0.05, 0.05, 0.025, 0.04, 0.03, 0.04, 0.025, 0.05, 0.0, 0.012]
AGE = "#CDB68C"               # the ageing wash's colour at full strength
BLOCK = 10


def strip_layer(w, h, strip, field):
    """@1x RGBA: the mount stripes by Chebyshev ring + ``field`` (RGB array or colour) inside."""
    k = X.cheb_k(w, h)
    out = X.rgba_layer(h, w)
    out[..., :3] = P.rgb(field) if np.ndim(field) <= 1 else field
    out[..., 3] = 1.0
    for i, c in enumerate(strip):
        out[k == i, :3] = P.rgb(c)
    return out, k


def across_threads(G, w, h, amps):
    """Multiplicative two-thread split of each stripe across the strip (render grid): the
    sample's position inside its @1x pixel, measured across the strip, darkens one half and
    lightens the other - zero-mean per @1x pixel, constant along the strip."""
    d = S.inset_distance(G, w, h)
    k = np.floor(d).astype(np.int32)
    fr = d - k
    amp = np.zeros(G.shape, np.float32)
    for i, a in enumerate(amps):
        amp[k == i] = a
    return 1.0 + amp * np.where(fr < 0.5, -1.0, 1.0)


def silk_field(G, w, h, margins, seed, base=PAPER, age=AGE, age_at=(11, 22), age_k=0.30,
               mottle=0.018, cell=40.0):
    """Silk field on the render grid: the ageing wash as a function of the mitred distance only
    (stretch-safe in the margins), plus a large faint mottle in the 9-slice centre."""
    d = S.inset_distance(G, w, h)
    a0, a1 = age_at
    wash = (1.0 - P.smoothstep(a0, a1, np.maximum(d, a0))) ** 1.4 * age_k
    col = P.mix(base, age, wash)
    cw = P.centre_weight(G, margins, fade=10.0)
    m = P.fbm2(G, cell, seed + 1, octaves=2, gain=0.45)
    col = col * (1.0 + mottle * np.clip(m, -2.2, 2.2) / 2.2 * cw)[..., None]
    return col.astype(np.float32)


def paint(G, variant=None, seed=None):
    seed = SPEC["seed"] if seed is None else seed
    lay, k = strip_layer(W, H, STRIP, PAPER)
    blk = X.rosette_block()
    for flip_y in (False, True):
        for flip_x in (False, True):
            b = blk[::-1] if flip_y else blk
            b = b[:, ::-1] if flip_x else b
            ys = slice(H - BLOCK, H) if flip_y else slice(0, BLOCK)
            xs = slice(W - BLOCK, W) if flip_x else slice(0, BLOCK)
            lay[ys, xs] = b
    big = X.up(lay, G.ss)
    field = silk_field(G, W, H, SPEC["margins"], seed)
    inside = X.up(k >= len(STRIP), G.ss)
    rgb = np.where(inside[..., None], field, big[..., :3])
    rgb = rgb * across_threads(G, W, H, THREADS)[..., None]
    # the corner blocks are not stretched: they carry the woven thread texture
    corner = X.up((np.minimum(np.indices((H, W))[0], H - 1 - np.indices((H, W))[0]) < BLOCK)
                  & (np.minimum(np.indices((H, W))[1], W - 1 - np.indices((H, W))[1]) < BLOCK),
                  G.ss)
    wv = X.sub_weave(H, W, G.ss, seed + 3, amp=0.04)
    rgb = np.where(corner[..., None], rgb * wv[..., None], rgb)
    out = np.concatenate([np.clip(rgb, 0, 1), big[..., 3:4]], -1)
    return out.astype(np.float32)
