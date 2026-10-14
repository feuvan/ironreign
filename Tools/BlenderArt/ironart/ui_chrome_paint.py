"""UI chrome family: gongbi (工笔) painting toolkit - numpy only, no bpy.

The UI chrome is painted like a classical Chinese mounting (装裱): aged silk grounds, patterned
brocade borders, ruled ink lines, mineral-colour washes with soft 晕染 gradients and mud-gold
(泥金) rules.  Every piece is authored here as layers on a :class:`Canvas` sampled on the render
grid (``ui_chrome_sdf.Grid``: ``ss`` samples per target px, image convention, +y down), then
handed to :mod:`ironart.ui_chrome_flat`, which renders it through Cycles as a flat orthographic
emission plate (plus toon-shaded 3D parts with Freestyle ink where a piece has them).

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


def fine_grain(G, seed, size=0.5):
    """Pigment grain: blurred white noise with features of ``size`` target px, unit std."""
    rng = np.random.default_rng(seed)
    n = rng.standard_normal(G.shape).astype(np.float32)
    n = S.blur(n, max(0.35, size * G.ss * 0.5))
    return (n - n.mean()) / (n.std() + 1e-6)


# =============================================================================================
# grounds
# =============================================================================================
def silk_texture(G, seed, weave=0.012, slub=0.02, mottle=0.02, mottle_cell=36.0):
    """Multiplicative silk texture (~1.0): fine weft/warp striation, sparse slubs (thicker
    threads) along the weft, and soft ageing mottle.  Amplitudes are fractions of the value."""
    ys = G.ys[:, None]
    xs = G.xs[None, :]
    # weft threads (horizontal) and warp (vertical): 1D striation modulated by a slow field
    weft = noise1d(G.ys, 0.9, seed + 1, octaves=1)[:, None]
    warp = noise1d(G.xs, 0.9, seed + 2, octaves=1)[None, :]
    mod = 0.6 + 0.4 * fbm2(G, 14.0, seed + 3, octaves=2)
    t = weave * (0.75 * weft + 0.45 * warp) * mod
    # slubs: elongated horizontal flecks (cells 1 px tall, 14 px long), thresholded
    if slub > 0:
        sl = S.value_noise(G.shape, 0.9 * G.ss, seed + 4, aniso=(16.0, 1.0))
        sl = smoothstep(0.70, 0.86, sl) - smoothstep(0.70, 0.86, 1.0 - sl)
        t = t + slub * sl
    if mottle > 0:
        t = t + mottle * fbm2(G, mottle_cell, seed + 5, octaves=4, gain=0.55)
    del ys, xs
    return (1.0 + t).astype(np.float32)


def silk_field(G, seed, base="paper", texture=None, **kw):
    """Silk ground colour field (rows, cols, 3)."""
    tex = silk_texture(G, seed, **kw) if texture is None else texture
    return rgb(base) * tex[..., None]


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
# lines
# =============================================================================================
def aa(sd, G, soft=1.0):
    return S.aa_mask(sd, G, soft)


def rule(d, at, width, G):
    """Mask of a ruled line of ``width`` px centred on the iso-line d == at (mitred frame rule
    when ``d`` is an inset distance)."""
    return S.aa_mask(np.abs(d - at) - width * 0.5, G)


def band(d, d0, d1, G):
    return S.band(d, d0, d1, G)


def stroke(G, pts, radii, out=None, pad=3.0):
    """sd of a tapered brush stroke along ``pts`` (per-point radii)."""
    return S.sd_polyline(G, pts, radii, out=out, pad=pad)


def brush_radii(n, w, start=0.55, end=0.25, press=1.15, power=0.8, seed=None, wobble=0.0):
    """Gongbi line profile: a pressed entry (起笔), even body, tapered exit (收笔)."""
    t = np.linspace(0.0, 1.0, n, dtype=np.float32)
    entry = start + (press - start) * smoothstep(0.0, 0.12, t)
    body = np.where(t < 0.18, entry, 1.0 + (press - 1.0) * (1.0 - smoothstep(0.12, 0.35, t)))
    tail = 1.0 - (1.0 - end) * smoothstep(0.62, 1.0, t) ** power
    r = w * 0.5 * body * tail
    if seed is not None and wobble > 0:
        r = r * (1.0 + wobble * noise1d(t * n, max(4.0, n / 6.0), seed, octaves=1))
    return r.astype(np.float32)


# =============================================================================================
# mud-gold / pigment colour fields
# =============================================================================================
def gold_field(G, seed, base="gold", grain=0.05, flecks=0.06, shade=None):
    """Matte mud-gold (泥金) colour field: base colour with fine powder grain and sparse
    paler flecks (gold powder catching the light); never metallic, never glossy."""
    g = fine_grain(G, seed, 0.45)
    c = rgb(base) * (1.0 + grain * g)[..., None]
    if flecks > 0:
        f = smoothstep(1.6, 2.6, fine_grain(G, seed + 1, 0.4))
        c = c + (rgb("gold_light") - rgb(base)) * (flecks * 6.0 * f)[..., None]
    if shade is not None:
        c = c * shade[..., None]
    return np.clip(c, 0, 1)


def strip_color(d, base, seed, amp=0.04, period=0.6, octaves=1):
    """A colour field that only depends on the across-coordinate ``d`` (9-slice strips):
    lengthwise silk threads / pigment streaks."""
    n = noise1d(d, period, seed, octaves=octaves)
    return rgb(base) * (1.0 + amp * n)[..., None]


# =============================================================================================
# motifs (target px; lists of (points, radii) strokes or sd fields)
# =============================================================================================
def curl(cx, cy, r0, turns, a0, cw=True, w0=0.6, w1=0.25, inner=0.22, n=None):
    """A cloud curl: tapered spiral stroke winding inwards (points, radii)."""
    pts = S.spiral(cx, cy, r0, r0 * inner, turns, a0, cw, n)
    rad = S.taper(len(pts), w0 * 0.5, w1 * 0.5, power=0.9)
    return pts, rad


def strokes_sd(G, strokes, pad=3.0):
    out = G.empty()
    for pts, rad in strokes:
        S.sd_polyline(G, pts, rad, out=out, pad=pad)
    return out


def rotate(pts, deg, cx=0.0, cy=0.0):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    p = np.asarray(pts, np.float32) - [cx, cy]
    return np.stack([p[:, 0] * c - p[:, 1] * s, p[:, 0] * s + p[:, 1] * c], 1) + [cx, cy]


def mirror_x(pts, cx):
    p = np.asarray(pts, np.float32).copy()
    p[:, 0] = 2 * cx - p[:, 0]
    return p


def mirror_y(pts, cy):
    p = np.asarray(pts, np.float32).copy()
    p[:, 1] = 2 * cy - p[:, 1]
    return p


def corner_copies(strokes, w, h):
    """The four mirrored copies of top-left corner strokes [(pts, radii)] on a w x h piece."""
    out = []
    for pts, rad in strokes:
        out.append((pts, rad))
        out.append((mirror_x(pts, w / 2.0), rad))
        out.append((mirror_y(pts, h / 2.0), rad))
        out.append((mirror_y(mirror_x(pts, w / 2.0), h / 2.0), rad))
    return out


def stamp_corners(full, local):
    """Paste a top-left local array (rows, cols[, c]) into the four corners of ``full`` with
    mirroring (max-combine for masks)."""
    h, w = local.shape[:2]
    H, W = full.shape[:2]
    views = [(slice(0, h), slice(0, w), local), (slice(0, h), slice(W - w, W), local[:, ::-1]),
             (slice(H - h, H), slice(0, w), local[::-1, :]),
             (slice(H - h, H), slice(W - w, W), local[::-1, ::-1])]
    for sy, sx, arr in views:
        full[sy, sx] = np.maximum(full[sy, sx], arr)
    return full


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


def paint_ruyi(C, G, cx, cy, size, rot, seed, halo=None, halo_w=0.8, deep=0.72,
               engrave="#3A2C1E", outline=None, outline_w=0.32):
    """A painted mud-gold ruyi cloud head (trefoil + point) with engraved curls: gold wash that
    deepens towards its edge (晕染), engraved lines in ``engrave``, optional ink ``outline`` and
    a ``halo`` of ground colour that interrupts the rules behind it."""
    from . import ui_chrome_motifs as MO
    shape, eng = MO.ruyi(G, cx, cy, size, rot)
    if halo is not None:
        C.over(aa(shape - halo_w, G), halo)
    g = gold_field(G, seed, flecks=0.0)
    sh = smoothstep(0.0, 0.17 * size, -shape)
    C.over(aa(shape, G), mix(g * deep, g, sh))
    C.over(aa(eng - 0.026 * size, G) * aa(shape + 0.033 * size, G), engrave, 0.9)
    if outline is not None:
        C.over(aa(np.abs(shape) - outline_w, G), outline)
    return shape
