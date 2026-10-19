"""UI chrome family: motifs authored on the @1x pixel grid (numpy only, no bpy).

Small woven and painted details of the gongbi mounting (装裱) - key-fret (回纹) bands, brocade
corner blocks with a 柿蒂 rosette, cloud-thunder (云雷纹) corner brackets, the woven cross-section
of a 9-slice mount strip - only read at 1x when every line sits on whole pixels.  They are
authored here as @1x bitmaps / colour layers and nearest-upscaled to the render grid, so the box
downsample of the render gives exactly these pixels at @1x and the same lines 2 px wide at @2x
(:func:`sub_weave` adds thread detail that only the @2x master resolves).

Conventions: image coordinates (row 0 = top), straight sRGB float colours, ``k`` = the integer
Chebyshev distance of a pixel from the outer edge of its piece (0 = outermost pixel ring).
"""

import numpy as np

from . import ui_chrome_paint as P


# =============================================================================================
# grids
# =============================================================================================
def up(a, ss):
    """Nearest upscale of a @1x layer (H, W[, C]) to the render grid (ss samples per px)."""
    return np.repeat(np.repeat(a, ss, axis=0), ss, axis=1)


def cheb_k(w, h):
    """Integer Chebyshev distance of each @1x pixel from the outer edge (0 = outer ring)."""
    y, x = np.mgrid[0:h, 0:w]
    return np.minimum(np.minimum(x, w - 1 - x), np.minimum(y, h - 1 - y))


def strip_axis(w, h):
    """1 where a pixel belongs to a horizontal (top/bottom) strip, 0 for a vertical one
    (split on the mitre diagonals)."""
    y, x = np.mgrid[0:h, 0:w]
    return (np.minimum(y, h - 1 - y) <= np.minimum(x, w - 1 - x)).astype(np.float32)


def rgba_layer(h, w):
    return np.zeros((h, w, 4), np.float32)


def put(layer, mask, color, alpha=1.0):
    """Paint ``color`` over ``layer`` (straight RGBA, @1x) where ``mask`` (bool or 0..1)."""
    m = np.asarray(mask, np.float32) * alpha
    if m.ndim == 0:
        m = np.full(layer.shape[:2], float(m), np.float32)
    c = P.rgb(color)
    a0 = layer[..., 3]
    a = m + a0 * (1.0 - m)
    safe = np.maximum(a, 1e-6)[..., None]
    rgb = (c * m[..., None] + layer[..., :3] * (a0 * (1.0 - m))[..., None]) / safe
    layer[..., :3] = np.where(a[..., None] > 1e-6, rgb, layer[..., :3])
    layer[..., 3] = a
    return layer


def parse(art, palette):
    """ASCII art (one row per line, one character per pixel) -> straight RGBA (h, w, 4);
    characters missing from ``palette`` (e.g. ' ') are transparent."""
    rows = [r for r in art.strip("\n").splitlines()]
    rows = [r.strip() for r in rows if r.strip()]
    h, w = len(rows), max(len(r) for r in rows)
    out = rgba_layer(h, w)
    for j, r in enumerate(rows):
        for i, ch in enumerate(r):
            if ch in palette:
                out[j, i, :3] = P.rgb(palette[ch])
                out[j, i, 3] = 1.0
    return out


def draw_path(mask, path, dx=0, dy=0):
    """1 px axis-aligned polyline ``path`` [(x, y), ...] into a boolean mask (in place)."""
    for (x0, y0), (x1, y1) in zip(path[:-1], path[1:]):
        if x0 == x1:
            ys = range(min(y0, y1), max(y0, y1) + 1)
            for y in ys:
                if 0 <= y + dy < mask.shape[0] and 0 <= x0 + dx < mask.shape[1]:
                    mask[y + dy, x0 + dx] = True
        elif y0 == y1:
            for x in range(min(x0, x1), max(x0, x1) + 1):
                if 0 <= y0 + dy < mask.shape[0] and 0 <= x + dx < mask.shape[1]:
                    mask[y0 + dy, x + dx] = True
        else:
            raise ValueError("draw_path: segments must be axis-aligned")
    return mask


# =============================================================================================
# woven texture that only the @2x master resolves
# =============================================================================================
def sub_weave(h, w, ss, seed, amp=0.035):
    """Multiplicative thread texture on the render grid (h*ss, w*ss): random per @2x pixel
    (ss/2 samples), made zero-mean inside every @1x pixel, so the @1x art keeps its exact pixel
    colours while the @2x master shows the threads.  Returns 1 + amp * t (float32)."""
    if ss < 2 or ss % 2:
        return np.ones((h * ss, w * ss), np.float32)
    rng = np.random.default_rng(seed)
    t = rng.standard_normal((h * 2, w * 2)).astype(np.float32)
    # weave bias: alternate warp / weft crowns in a 2x2 checker inside each @1x pixel
    t += 0.8 * (np.indices((h * 2, w * 2)).sum(0) % 2 * 2 - 1)
    t = t.reshape(h, 2, w, 2)
    t -= t.mean(axis=(1, 3), keepdims=True)
    t = t.reshape(h * 2, w * 2) / (t.std() + 1e-6)
    t = up(t, ss // 2)
    return (1.0 + amp * t).astype(np.float32)


# =============================================================================================
# key-fret (回纹) bands
# =============================================================================================
#: one 8 px period of the squared-spiral key-fret (连续回纹), 6 px tall: each unit is a 回 spiral
#: hung from a top thread, x = 0..7, y = 0..5
FRET_PATHS = [[(0, 0), (6, 0), (6, 5), (2, 5), (2, 2), (4, 2), (4, 3)], [(0, 0), (0, 5)]]
FRET_PERIOD, FRET_HEIGHT = 8, 6


def fret_unit(mirror=False):
    m = np.zeros((FRET_HEIGHT, FRET_PERIOD), bool)
    for p in FRET_PATHS:
        draw_path(m, p)
    return m[:, ::-1] if mirror else m


def fret_band(length, phase=0, flip_v=False, centre=None):
    """Boolean (6, length) key-fret band.  ``centre`` (pixel x, may be fractional) makes the band
    mirror-symmetric about that point (the right half is the mirror of the left half) so a
    side between two corner blocks starts and ends the same way; else it repeats from
    ``phase``."""
    unit = fret_unit()
    reps = length // FRET_PERIOD + 3
    row = np.tile(unit, (1, reps))
    if centre is None:
        out = row[:, phase:phase + length]
    else:
        half = int(np.ceil(length / 2.0))
        left = np.tile(unit, (1, half // FRET_PERIOD + 2))
        # align so that a unit boundary sits at the band centre
        n = left.shape[1]
        left = left[:, n - half:]
        out = np.concatenate([left, left[:, ::-1]], 1)[:, :length]
    return out[::-1] if flip_v else out


# =============================================================================================
# brocade corner block with a 柿蒂 rosette (10 x 10)
# =============================================================================================
#: k = ink contour, . = deep azurite brocade ground, G = mud-gold, g = ochre-gold 分染 (the
#: shaded side of each petal), R = cinnabar heart (2 x 2)
ROSETTE_BLOCK = """
kkkkkkkkkk
k...GG...k
k..GGGg..k
k.g.kk.g.k
kGGkRRkGgk
kGGkRRkggk
k.G.kk.g.k
k..gGgg..k
k...gg...k
kkkkkkkkkk
"""

BLOCK_PAL = {"k": "#1E1A16", ".": "#22476B", "G": "#C9A24B", "g": "#A47C3A", "R": "#B5382A",
             "a": "#2B5C8A"}


def rosette_block(palette=None):
    pal = dict(BLOCK_PAL)
    pal.update(palette or {})
    return parse(ROSETTE_BLOCK, pal)


# =============================================================================================
# cloud-thunder (云雷纹) corner bracket, 16 x 16, top-left corner
# =============================================================================================
#: 1 px gold lines with 2 px gaps: an outer L along both edges, a squared spiral in the corner
#: and a hook at the end of each arm (pitch 3 px)
BRACKET_PATHS = [[(12, 3), (15, 3), (15, 0), (0, 0), (0, 15), (3, 15), (3, 3), (9, 3), (9, 9),
                  (6, 9), (6, 6)]]


def bracket(n=16):
    m = np.zeros((n, n), bool)
    for p in BRACKET_PATHS:
        draw_path(m, p)
    return m


def mirror4_place(canvas_mask, motif, x0, y0):
    """Place ``motif`` (bool, top-left corner orientation) at (x0, y0) from each corner of
    ``canvas_mask`` (mirrored into the other three corners), in place."""
    h, w = canvas_mask.shape
    mh, mw = motif.shape
    tl = np.zeros_like(canvas_mask)
    tl[y0:y0 + mh, x0:x0 + mw] = motif
    canvas_mask |= tl | tl[:, ::-1] | tl[::-1, :] | tl[::-1, ::-1]
    return canvas_mask
