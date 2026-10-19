"""UI chrome family: the painting canvas and colour/noise/mount basics - numpy only, no bpy.

The UI chrome is painted like a classical Chinese mounting (装裱).  Every piece is authored as
layers on a :class:`Canvas` sampled on the render grid (``ui_chrome_sdf.Grid``: ``ss`` samples
per target px, image convention, +y down); the materials (silk, brocade, mud-gold, mineral
colours, glyphs, brush) live in :mod:`ironart.ui_chrome_gongbi`, the drawn ornaments in
:mod:`ironart.ui_chrome_ornament`, and :mod:`ironart.ui_chrome_flat` renders the result through
Cycles as a flat orthographic emission plate (plus toon-shaded 3D parts with Freestyle ink where
a piece has them).

Painting model (sRGB, straight colours; the canvas keeps premultiplied colour internally)
    over(mask, colour)        opaque mineral pigment / ink laid over what is there
    glaze(mask, colour, k)    transparent wash: multiplies the painted colour (晕染, ink washes)
    tone(mask, factor)        darken / lighten what is painted by a factor
Colours are hex strings, palette names (:data:`PAL`) or arrays (per-pixel colour fields).

9-slice rule: anything in a 9-slice border strip must be a function of the distance across the
strip only (``inset_distance``), so Slate can stretch it; 2D texture lives in the corners and in
the centre, faded out before the 9-slice boundary (:func:`centre_weight`).
"""

import math

import numpy as np

from . import ui_chrome_sdf as S

#: gongbi mineral palette (DESIGN.md section 8) + UI tokens + mounting colours, sRGB hex
PAL = {
    # grounds
    "silk": "#E6D6B0", "silk_dark": "#D8C39A", "paper": "#E9DCC0", "paper_dark": "#CDB990",
    "lead_white": "#F0E8D8", "ivory": "#EEE4CC",
    # ink
    "ink": "#1E1A16", "ink_ui": "#2A2119", "ink_soft": "#5A4A3A", "night": "#1B1712",
    "umber": "#3A2C21",
    # minerals
    "malachite": "#3E8E6E", "malachite_light": "#8CBFA0",
    "azurite": "#2B5C8A", "azurite_light": "#7FA6C8",
    "cinnabar": "#B5382A", "vermilion": "#D0643C", "ochre": "#A0643A", "rouge": "#9E3B4A",
    "gold": "#C9A24B", "gold_light": "#E0C47E", "gold_deep": "#9C7A32",
    # mounting silks (muted minerals as dyed silk)
    "brocade_blue": "#3B5D7C", "brocade_blue_deep": "#24405A", "brocade_ochre": "#B08A4E",
    "lacquer": "#7E1F17", "lacquer_dark": "#4A120D",
}


def rgb(c):
    """'#rrggbb' / palette name / triple / array -> float32 sRGB (array passes through)."""
    if isinstance(c, str):
        h = PAL.get(c, c).lstrip("#")
        return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)
    return np.asarray(c, np.float32)


def mix(a, b, t):
    """Lerp two colours (or colour fields) by t (scalar or field)."""
    a, b = rgb(a), rgb(b)
    t = np.asarray(t, np.float32)
    if t.ndim >= 1 and t.shape[-1:] != (3,):
        t = t[..., None]
    return a + (b - a) * t


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, np.float32) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def srgb_to_linear(x):
    x = np.clip(x, 0.0, None)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)


def linear_to_srgb(x):
    x = np.clip(x, 0.0, None)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055).astype(np.float32)


# =============================================================================================
# canvas
# =============================================================================================
class Canvas:
    """Premultiplied sRGB RGBA layer stack on grid ``G``."""

    def __init__(self, G, color=None, alpha=1.0):
        self.G = G
        self.P = np.zeros(G.shape + (3,), np.float32)
        self.A = np.zeros(G.shape, np.float32)
        if color is not None:
            self.over(np.ones(G.shape, np.float32), color, alpha)

    @staticmethod
    def _m(mask, shape):
        m = np.asarray(mask, np.float32)
        if m.ndim == 0:
            m = np.full(shape, float(m), np.float32)
        return np.clip(m, 0.0, 1.0)

    def over(self, mask, color, opacity=1.0):
        """Opaque paint (pigment / ink) of coverage ``mask`` x ``opacity`` over the canvas."""
        a = self._m(mask, self.G.shape) * opacity
        c = rgb(color)
        self.P *= (1.0 - a)[..., None]
        self.P += c * a[..., None]
        self.A *= (1.0 - a)
        self.A += a
        return self

    def under(self, mask, color, opacity=1.0):
        """Paint *behind* what is there (fills only the transparent part)."""
        a = self._m(mask, self.G.shape) * opacity * (1.0 - self.A)
        self.P += rgb(color) * a[..., None]
        self.A += a
        return self

    def glaze(self, mask, color, strength=1.0):
        """Transparent wash: multiply the painted colour by ``color`` with weight mask x strength."""
        k = (self._m(mask, self.G.shape) * strength)[..., None]
        c = rgb(color)
        self.P *= 1.0 - k * (1.0 - c)
        return self

    def tone(self, mask, factor):
        """Multiply the painted colour by ``factor`` (scalar or field) where ``mask``."""
        m = self._m(mask, self.G.shape)
        f = 1.0 + (np.asarray(factor, np.float32) - 1.0) * m
        self.P *= f[..., None]
        return self

    def erase(self, mask):
        """Cut the canvas away (alpha and colour) by ``mask``."""
        k = 1.0 - self._m(mask, self.G.shape)
        self.P *= k[..., None]
        self.A *= k
        return self

    def rgba(self):
        """Straight-alpha float32 RGBA (sRGB)."""
        out = np.zeros(self.G.shape + (4,), np.float32)
        a = self.A
        safe = np.maximum(a, 1e-6)[..., None]
        out[..., :3] = np.where(a[..., None] > 1e-6, self.P / safe, 0.0)
        out[..., 3] = a
        return np.clip(out, 0.0, 1.0)

    def color(self):
        return self.rgba()[..., :3]


# =============================================================================================
# deterministic noise
# =============================================================================================
def noise1d(coord, period, seed, octaves=2, gain=0.5):
    """Smooth zero-mean, unit-std 1D noise evaluated at ``coord`` (any array, target px).
    ``period`` is the feature size of the first octave in target px."""
    rng = np.random.default_rng(seed)
    c = np.asarray(coord, np.float32)
    lo, hi = float(c.min()) - 4 * period, float(c.max()) + 4 * period
    acc = np.zeros(c.shape, np.float32)
    tot = 0.0
    amp = 1.0
    for o in range(octaves):
        p = period / (2 ** o)
        step = p / 8.0
        n = int((hi - lo) / step) + 2
        xs = lo + np.arange(n, dtype=np.float64) * step
        wn = rng.standard_normal(n)
        sig = 8.0 / 2.5
        r = int(sig * 3) + 1
        k = np.exp(-0.5 * (np.arange(-r, r + 1) / sig) ** 2)
        k /= k.sum()
        sm = np.convolve(np.pad(wn, r, mode="wrap"), k, mode="valid")
        sm = (sm - sm.mean()) / (sm.std() + 1e-9)
        acc += amp * np.interp(c, xs, sm).astype(np.float32)
        tot += amp * amp
        amp *= gain
    return acc / math.sqrt(tot)


def fbm2(G, cell, seed, octaves=4, gain=0.5, aniso=(1.0, 1.0)):
    """Zero-mean, unit-std 2D fbm on grid ``G``; ``cell`` in target px."""
    n = S.fbm(G.shape, cell * G.ss, seed, octaves, gain, aniso)
    return ((n - n.mean()) / (n.std() + 1e-6)).astype(np.float32)


# =============================================================================================
# 9-slice helpers
# =============================================================================================
def centre_weight(G, margins, fade=8.0):
    """0 inside the 9-slice margins, rising to 1 over ``fade`` px inside the centre region."""
    l, t, r, b = margins
    w, h = G.w, G.h
    dx = np.minimum(G.xs - l, (w - r) - G.xs)
    dy = np.minimum(G.ys - t, (h - b) - G.ys)
    fx = smoothstep(0.0, fade, dx)[None, :]
    fy = smoothstep(0.0, fade, dy)[:, None]
    return (fx * fy).astype(np.float32)


# =============================================================================================
# mount geometry
# =============================================================================================
def cheb_box(G, x0, y0, x1, y1):
    """Chebyshev (square-offset) signed distance of an axis-aligned box: its iso-lines are
    mitred rectangles, the ruled lines of a mount (jiehua)."""
    cx, cy, hw, hh = 0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (x1 - x0), 0.5 * (y1 - y0)
    return np.maximum(np.abs(G.X - cx) - hw, np.abs(G.Y - cy) - hh).astype(np.float32)


def notched_window(G, w, h, inset, notch):
    """Chebyshev distance (> 0 outside, exact) to the window of a mount with square-notched
    (委角) corners: the rectangle inset by ``inset`` minus a ``notch`` square at each corner,
    i.e. the union of a wide and a tall rectangle.  Its iso-lines (dw = const) are ruled lines
    that step around each corner."""
    a = cheb_box(G, inset, inset + notch, w - inset, h - inset - notch)
    b = cheb_box(G, inset + notch, inset, w - inset - notch, h - inset)
    return np.minimum(a, b)


def plaque_sd(G, w, h, inset=1.0, notch=4.5):
    """Plaque with concave quarter-circle corners (海棠/委角 tablet), sd < 0 inside."""
    box = S.sd_round_box(G, w / 2.0, h / 2.0, w / 2.0 - inset, h / 2.0 - inset, 0.0)
    q = None
    for (x, y) in ((inset, inset), (w - inset, inset), (inset, h - inset), (w - inset, h - inset)):
        c = np.hypot(G.X - x, G.Y - y) - notch
        q = c if q is None else np.minimum(q, c)
    return np.maximum(box, -q).astype(np.float32)
