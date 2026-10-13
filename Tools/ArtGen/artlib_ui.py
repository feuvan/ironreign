"""Shared helpers for the Iron Reign UI art generators (Tools/ArtGen/ui_*.py).

Everything here is deterministic: all randomness comes from numpy Generators seeded by the
callers, and all rasterisation goes through Pillow at a supersampled resolution that is then
box-filtered down to the target size.

Conventions
-----------
* Colours are float RGB in 0..1 (sRGB, not linearised: we paint like a painter, not a renderer).
* Masks are float32 arrays in 0..1, shape (H, W).
* `Layer` is a premultiplied RGBA float canvas; `Layer.save()` un-premultiplies, dithers and
  writes an optimized PNG.
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
DATA = os.path.join(ROOT, "Content", "Data")
ART = os.path.join(DATA, "Art")
FONTS = os.path.join(DATA, "Fonts")

FONT_BODY = os.path.join(FONTS, "Body-Regular.ttf")
FONT_BOLD = os.path.join(FONTS, "Body-Bold.ttf")
FONT_HEADING = os.path.join(FONTS, "Heading.ttf")
FONT_BRUSH = os.path.join(FONTS, "Brush.ttf")


def hexc(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)


# Palette from docs/DESIGN.md section 8 plus a few derived UI tones.
PAL = {
    "paper": hexc("E9DCC0"),
    "paper_dark": hexc("CDB990"),
    "paper_light": hexc("F3EAD5"),
    "ink": hexc("2A2119"),
    "ink_soft": hexc("5A4A3A"),
    "lacquer": hexc("7E1F17"),
    "lacquer_dark": hexc("4A120D"),
    "lacquer_light": hexc("A3352A"),
    "gold": hexc("C9A24A"),
    "gold_light": hexc("F1D98E"),
    "gold_dark": hexc("7E6026"),
    "jade": hexc("3F6E5A"),
    "indigo": hexc("2E3F5C"),
    "night": hexc("1B1712"),
    "seal": hexc("B0281F"),
    "bronze": hexc("9A6B3A"),
}


def mix(a, b, t):
    """Linear interpolation that broadcasts colours (3,) against masks (H, W)."""
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    t = np.asarray(t, dtype=np.float32)
    if t.ndim == 2 and (a.ndim == 1 or b.ndim == 1 or a.ndim == 3 or b.ndim == 3):
        t = t[..., None]
    return a + (b - a) * t


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, dtype=np.float32) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def clamp01(x):
    return np.clip(x, 0.0, 1.0)


# ----------------------------------------------------------------------------------------------
# Noise
# ----------------------------------------------------------------------------------------------

def value_noise(h, w, cell_y, cell_x, rng):
    """Smooth value noise in 0..1 with feature size (cell_y, cell_x) pixels."""
    cell_y = max(1.0, float(cell_y))
    cell_x = max(1.0, float(cell_x))
    gh = int(math.ceil(h / cell_y)) + 4
    gw = int(math.ceil(w / cell_x)) + 4
    g = rng.random((gh, gw)).astype(np.float32)
    im = Image.fromarray(g, "F").resize((int(round(gw * cell_x)), int(round(gh * cell_y))),
                                        Image.BICUBIC)
    a = np.asarray(im, dtype=np.float32)
    oy = int(cell_y * 1.5)
    ox = int(cell_x * 1.5)
    return a[oy:oy + h, ox:ox + w]


def fbm(h, w, cell, rng, octaves=5, gain=0.5, aniso=(1.0, 1.0)):
    """Fractal noise roughly normalised to 0..1 (mean 0.5). aniso=(sy, sx) stretches cells."""
    total = np.zeros((h, w), np.float32)
    amp, norm, c = 1.0, 0.0, float(cell)
    for _ in range(octaves):
        total += amp * (value_noise(h, w, c * aniso[0], c * aniso[1], rng) - 0.5)
        norm += amp
        amp *= gain
        c = max(1.0, c / 2.0)
    return 0.5 + total / norm * 1.6


def noise1d(n, cell, rng, octaves=5, gain=0.5):
    """1-D fractal noise in roughly -1..1."""
    out = np.zeros(n, np.float32)
    amp, norm, c = 1.0, 0.0, float(cell)
    x = np.arange(n, dtype=np.float32)
    for _ in range(octaves):
        m = int(n / c) + 4
        pts = rng.uniform(-1, 1, m).astype(np.float32)
        xs = np.arange(m, dtype=np.float32) * c - c
        # cubic-ish interpolation via np.interp on a smoothed grid
        fine = np.interp(x, xs, pts)
        sig = c / 3.0
        if sig > 0.5:
            fine = ndimage.gaussian_filter1d(fine, sig, mode="nearest")
        out += amp * fine
        norm += amp
        amp *= gain
        c = max(1.0, c / 2.0)
    return out / norm * 1.8


def paper_grain(h, w, rng, scale=1.0):
    """Paper texture in roughly -1..1: mottling + horizontal/vertical fibres + fine grain."""
    mott = fbm(h, w, 180 * scale, rng, octaves=4) - 0.5
    wn = rng.standard_normal((h, w)).astype(np.float32)
    fib_h = ndimage.gaussian_filter(wn, (0.6 * scale, 7.0 * scale))
    wn2 = rng.standard_normal((h, w)).astype(np.float32)
    fib_v = ndimage.gaussian_filter(wn2, (6.0 * scale, 0.6 * scale))
    fine = ndimage.gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), 0.7 * scale)
    fib = fib_h / (fib_h.std() + 1e-6) + 0.6 * fib_v / (fib_v.std() + 1e-6)
    out = 1.4 * mott / (mott.std() + 1e-6) * 0.35 + 0.25 * fib + 0.2 * fine / (fine.std() + 1e-6)
    return out / 2.5


# ----------------------------------------------------------------------------------------------
# Geometry
# ----------------------------------------------------------------------------------------------

def grid(h, w):
    """Pixel-centre coordinates (y, x) as float32 arrays."""
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    return y + 0.5, x + 0.5


def rrect_sdf(h, w, x0, y0, x1, y1, r, top_only=False):
    """Signed distance to a rounded rectangle (negative inside). Pixel units.
    top_only: only the two top corners are rounded (tabs)."""
    y, x = grid(h, w)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    hx, hy = (x1 - x0) / 2.0, (y1 - y0) / 2.0
    px, py = np.abs(x - cx), np.abs(y - cy)
    rr = np.full((h, w), r, np.float32)
    if top_only:
        rr = np.where(y > cy, 0.0, r).astype(np.float32)
    qx = px - hx + rr
    qy = py - hy + rr
    outside = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0))
    inside = np.minimum(np.maximum(qx, qy), 0)
    return outside + inside - rr


def band(d, a, b, aa=1.0):
    """Mask for a <= d < b with antialiased edges (aa = edge width in pixels)."""
    return clamp01((d - a) / aa + 0.5) * clamp01((b - d) / aa + 0.5)


def emboss(height, light=(-1.0, -1.0), strength=1.0):
    """Lambert-ish shading in -1..1 from a height map, light from the top-left by default."""
    gy, gx = np.gradient(height.astype(np.float32))
    lx, ly = light
    n = math.hypot(lx, ly)
    lx, ly = lx / n, ly / n
    # surface normal ~ (-gx, -gy, 1); light direction in screen plane (lx, ly) plus up component
    s = (-gx * lx - gy * ly) * strength
    return np.clip(s, -1, 1)


def bez(p0, p1, p2, p3, n=24):
    t = np.linspace(0, 1, n)[:, None]
    p0, p1, p2, p3 = (np.array(p, dtype=np.float64) for p in (p0, p1, p2, p3))
    pts = ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * t * t * p2 + (t ** 3) * p3
    return [tuple(p) for p in pts]


def qbez(p0, p1, p2, n=20):
    t = np.linspace(0, 1, n)[:, None]
    p0, p1, p2 = (np.array(p, dtype=np.float64) for p in (p0, p1, p2))
    pts = ((1 - t) ** 2) * p0 + 2 * (1 - t) * t * p1 + (t ** 2) * p2
    return [tuple(p) for p in pts]


def arc_pts(cx, cy, rx, ry, a0, a1, n=32):
    """Points along an ellipse arc, angles in degrees (0 = +x, 90 = +y/down)."""
    a = np.radians(np.linspace(a0, a1, n))
    return [(cx + rx * math.cos(t), cy + ry * math.sin(t)) for t in a]


def stroke_poly(pts, w0, w1=None, closed=False):
    """Polygon outlining a polyline with width tapering from w0 to w1 (a brush stroke)."""
    if w1 is None:
        w1 = w0
    p = np.array(pts, dtype=np.float64)
    n = len(p)
    if n < 2:
        return []
    d = np.gradient(p, axis=0)
    ln = np.hypot(d[:, 0], d[:, 1]) + 1e-9
    nx, ny = -d[:, 1] / ln, d[:, 0] / ln
    t = np.linspace(0, 1, n)
    w = (w0 + (w1 - w0) * t) / 2.0
    left = np.stack([p[:, 0] + nx * w, p[:, 1] + ny * w], 1)
    right = np.stack([p[:, 0] - nx * w, p[:, 1] - ny * w], 1)
    return [tuple(q) for q in left] + [tuple(q) for q in right[::-1]]


class Mask:
    """Pillow-backed drawing surface returning float masks. Coordinates are given in *output*
    pixels and multiplied by `s` (the supersampling factor)."""

    def __init__(self, w, h, s=1.0):
        self.w, self.h, self.s = int(w), int(h), float(s)
        self.im = Image.new("L", (self.w, self.h), 0)
        self.d = ImageDraw.Draw(self.im)

    def _p(self, pts):
        return [(x * self.s, y * self.s) for x, y in pts]

    def poly(self, pts, v=255):
        if len(pts) >= 3:
            self.d.polygon(self._p(pts), fill=v)
        return self

    def ellipse(self, cx, cy, rx, ry, v=255):
        s = self.s
        self.d.ellipse([(cx - rx) * s, (cy - ry) * s, (cx + rx) * s, (cy + ry) * s], fill=v)
        return self

    def circle(self, cx, cy, r, v=255):
        return self.ellipse(cx, cy, r, r, v)

    def rect(self, x0, y0, x1, y1, v=255):
        s = self.s
        self.d.rectangle([x0 * s, y0 * s, x1 * s - 1, y1 * s - 1], fill=v)
        return self

    def rrect(self, x0, y0, x1, y1, r, v=255):
        s = self.s
        self.d.rounded_rectangle([x0 * s, y0 * s, x1 * s - 1, y1 * s - 1], radius=r * s, fill=v)
        return self

    def line(self, pts, width, v=255, round_caps=True):
        s = self.s
        pp = self._p(pts)
        self.d.line(pp, fill=v, width=max(1, int(round(width * s))), joint="curve")
        if round_caps:
            r = width * s / 2.0
            for (x, y) in (pp[0], pp[-1]):
                self.d.ellipse([x - r, y - r, x + r, y + r], fill=v)
        return self

    def brush(self, pts, w0, w1=None, v=255):
        """Tapered stroke polygon (true sub-pixel widths, unlike line())."""
        return self.poly(stroke_poly(pts, w0, w1), v)

    def text(self, xy, txt, font, v=255, anchor="mm", **kw):
        self.d.text((xy[0] * self.s, xy[1] * self.s), txt, font=font, fill=v, anchor=anchor, **kw)
        return self

    def arr(self):
        return np.asarray(self.im, dtype=np.float32) / 255.0


def font(path, size):
    return ImageFont.truetype(path, int(round(size)))


def dilate(m, r):
    if r <= 0:
        return m
    d = ndimage.distance_transform_edt(m < 0.5)
    return clamp01(r + 0.5 - d) if r > 0 else m


def inner_dist(m):
    """Distance (px) from each inside pixel to the outside of mask m (thresholded at 0.5)."""
    return ndimage.distance_transform_edt(m >= 0.5).astype(np.float32)


def outer_dist(m):
    return ndimage.distance_transform_edt(m < 0.5).astype(np.float32)


def blur(a, sigma):
    if sigma <= 0:
        return a
    if a.ndim == 3:
        return np.stack([ndimage.gaussian_filter(a[..., i], sigma) for i in range(a.shape[2])], -1)
    return ndimage.gaussian_filter(a, sigma)


def shift(a, dy, dx):
    return ndimage.shift(a, (dy, dx) + ((0,) if a.ndim == 3 else ()), order=1, mode="constant")


def reduce(a, f):
    """Box-filter downsample by an integer factor."""
    f = int(f)
    if f == 1:
        return a
    h, w = a.shape[:2]
    h2, w2 = h // f, w // f
    a = a[:h2 * f, :w2 * f]
    if a.ndim == 2:
        return a.reshape(h2, f, w2, f).mean(axis=(1, 3))
    return a.reshape(h2, f, w2, f, a.shape[2]).mean(axis=(1, 3))


# ----------------------------------------------------------------------------------------------
# Canvases
# ----------------------------------------------------------------------------------------------

class Layer:
    """Premultiplied RGBA float canvas."""

    def __init__(self, w, h, color=None, alpha=0.0):
        self.w, self.h = int(w), int(h)
        self.c = np.zeros((self.h, self.w, 3), np.float32)
        self.a = np.zeros((self.h, self.w), np.float32)
        if color is not None:
            self.a[:] = alpha
            self.c[:] = np.asarray(color, np.float32) * alpha

    def paint(self, color, mask, opacity=1.0):
        """Source-over composite of `color` ((3,) or (H,W,3), straight) through `mask`."""
        m = np.asarray(mask, np.float32) * opacity
        if m.ndim == 0:
            m = np.full((self.h, self.w), float(m), np.float32)
        col = np.asarray(color, np.float32)
        self.c = self.c * (1 - m[..., None]) + col * m[..., None]
        self.a = self.a * (1 - m) + m
        return self

    def paint_layer(self, other, opacity=1.0):
        m = other.a * opacity
        self.c = self.c * (1 - m[..., None]) + other.c * opacity
        self.a = self.a * (1 - m) + m
        return self

    def multiply(self, factor, mask=None):
        """Multiply colour (keeps alpha). factor: scalar, (H,W) or (H,W,3)."""
        f = np.asarray(factor, np.float32)
        if f.ndim == 2:
            f = f[..., None]
        if mask is None:
            self.c = self.c * f
        else:
            m = np.asarray(mask, np.float32)[..., None]
            self.c = self.c * (1 - m + m * f)
        return self

    def screen_add(self, color, mask):
        """Additive light (for glows); clamps to alpha."""
        col = np.asarray(color, np.float32)
        m = np.asarray(mask, np.float32)
        self.c = np.minimum(self.c + col * m[..., None] * self.a[..., None], self.a[..., None])
        return self

    def erase(self, mask):
        m = clamp01(np.asarray(mask, np.float32))
        self.c = self.c * (1 - m[..., None])
        self.a = self.a * (1 - m)
        return self

    def clip(self, mask):
        m = clamp01(np.asarray(mask, np.float32))
        self.c = self.c * m[..., None]
        self.a = self.a * m
        return self

    def straight(self):
        a = self.a[..., None]
        rgb = np.where(a > 1e-5, self.c / np.maximum(a, 1e-5), 0.0)
        return np.clip(rgb, 0, 1), np.clip(self.a, 0, 1)

    def reduced(self, f):
        out = Layer(self.w // f, self.h // f)
        out.c = reduce(self.c, f)
        out.a = reduce(self.a, f)
        return out

    def to_image(self, f=1, dither_seed=None, opaque=False):
        lay = self.reduced(f) if f > 1 else self
        rgb, a = lay.straight()
        return to_pil(rgb, None if opaque else a, dither_seed)

    def save(self, path, f=1, dither_seed=1234, opaque=False):
        im = self.to_image(f, dither_seed, opaque)
        save_png(im, path)
        return im


def to_pil(rgb, a=None, dither_seed=None):
    rgb = np.clip(rgb, 0, 1) * 255.0
    if dither_seed is not None:
        rng = np.random.default_rng(dither_seed)
        rgb = rgb + (rng.random(rgb.shape[:2], dtype=np.float32)[..., None]
                     - rng.random(rgb.shape[:2], dtype=np.float32)[..., None]) * 0.75
    rgb8 = np.clip(np.round(rgb), 0, 255).astype(np.uint8)
    if a is None:
        return Image.fromarray(rgb8, "RGB")
    a8 = np.clip(np.round(np.clip(a, 0, 1) * 255.0), 0, 255).astype(np.uint8)
    # fully transparent pixels: zero colour for clean files
    rgb8[a8 == 0] = 0
    return Image.fromarray(np.dstack([rgb8, a8]), "RGBA")


def save_png(im, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if im.mode == "RGB":
        im = im.convert("RGBA")  # manifest: sRGB RGBA everywhere
    im.save(path, optimize=True)
    print("wrote %s (%dx%d)" % (os.path.relpath(path, ROOT), im.width, im.height))


# ----------------------------------------------------------------------------------------------
# Painting toolkit (ink-wash landscapes)
# ----------------------------------------------------------------------------------------------

class Painting:
    """An opaque painting rendered at `ss` times the output size.

    All public coordinates are in output pixels; `self.s` converts to canvas pixels.
    """

    def __init__(self, w, h, ss=2, seed=1):
        self.ow, self.oh, self.s = w, h, ss
        self.W, self.H = w * ss, h * ss
        self.rgb = np.zeros((self.H, self.W, 3), np.float32)
        self.rng = np.random.default_rng(seed)
        self._y, self._x = None, None

    # --- coordinates -------------------------------------------------------------------------
    @property
    def Y(self):
        if self._y is None:
            self._y, self._x = grid(self.H, self.W)
            self._y /= self.s
            self._x /= self.s
        return self._y

    @property
    def X(self):
        _ = self.Y
        return self._x

    def mask(self):
        return Mask(self.W, self.H, self.s)

    def xs(self):
        """Output-pixel x coordinate of every canvas column."""
        return (np.arange(self.W, dtype=np.float32) + 0.5) / self.s

    # --- painting ----------------------------------------------------------------------------
    def paint(self, color, m, opacity=1.0):
        m = np.asarray(m, np.float32) * opacity
        col = np.asarray(color, np.float32)
        if m.ndim == 2:
            m = m[..., None]
        self.rgb = self.rgb + (col - self.rgb) * m
        return self

    def multiply(self, f, m=None):
        f = np.asarray(f, np.float32)
        if f.ndim == 2:
            f = f[..., None]
        if m is None:
            self.rgb *= f
        else:
            m = np.asarray(m, np.float32)[..., None]
            self.rgb = self.rgb * (1 - m + m * f)
        return self

    def add_light(self, color, m):
        col = np.asarray(color, np.float32)
        m = np.asarray(m, np.float32)[..., None]
        self.rgb = 1 - (1 - self.rgb) * (1 - col * m)  # screen
        return self

    def vgradient(self, stops):
        """Fill with a vertical gradient. stops: [(t 0..1, colour), ...]."""
        t = self.Y[:, :1] / self.oh
        ts = np.array([s[0] for s in stops], np.float32)
        cols = np.array([s[1] for s in stops], np.float32)
        out = np.stack([np.interp(t[:, 0], ts, cols[:, i]) for i in range(3)], -1)
        self.rgb[:] = out[:, None, :]
        return self

    def glow(self, cx, cy, r, color, strength=1.0, power=2.0):
        d = np.hypot(self.X - cx, self.Y - cy) / r
        m = np.exp(-d ** power) * strength
        return self.add_light(color, clamp01(m))

    def disc(self, cx, cy, r, color, opacity=1.0, soft=1.0):
        d = np.hypot(self.X - cx, self.Y - cy)
        m = clamp01((r - d) / soft + 0.5)
        return self.paint(color, m, opacity)

    # --- landscape elements --------------------------------------------------------------------
    def ridge(self, base, peaks=(), rough=0.0, rough_cell=60.0, jag=0.0, seed=0, smooth=8.0):
        """Ridge line y(x) in output px for every canvas column.

        base: baseline y. peaks: (x, height, half_width, kind) with kind in
        {'round','sharp','karst','dome'}. rough: fbm amplitude (px). jag: small-scale jitter."""
        rng = np.random.default_rng(seed)
        x = self.xs()
        lift = np.zeros_like(x)
        for pk in peaks:
            px, ph, pw = pk[0], pk[1], pk[2]
            kind = pk[3] if len(pk) > 3 else "round"
            u = np.abs(x - px) / pw
            if kind == "sharp":
                v = np.clip(1 - u, 0, 1) ** 1.6
            elif kind == "karst":
                v = np.clip(1 - u ** 2.6, 0, 1) ** 0.9
            elif kind == "dome":
                v = np.clip(1 - u ** 2, 0, 1) ** 0.5
            else:
                v = np.exp(-(u * 1.8) ** 2)
            # soft union of peaks
            lift = np.log(np.exp(lift / smooth) + np.exp(ph * v / smooth)) * smooth
        lift -= smooth * math.log(2)
        lift = np.maximum(lift, 0)
        n = noise1d(len(x), rough_cell * self.s, rng, octaves=6, gain=0.55)
        j = noise1d(len(x), 6 * self.s, rng, octaves=3, gain=0.5)
        hfac = 0.35 + lift / (lift.max() + 1e-6)
        return base - lift - rough * n * hfac - jag * j

    def mountain(self, ridge, dark, light, fade=120.0, texture=0.35, edge=0.6, edge_w=2.5,
                 seed=0, lit=0.12, alpha=1.0, streak_cell=40.0, folds=0, fold_depth=(25, 140),
                 fold_strength=0.45, mist_col=None, mist_from=None):
        """Paint an ink-wash mountain strip below ridge(x): darkest at the ridge and washing out
        towards `light` with depth; ridged 'cun' texture strokes near the top; extra fold lines
        (overlapping inner ridges) for form; darker brushed ridge outline; left-facing slopes lit
        (light from the top-left). mist_from=(y0, y1) dissolves the strip into mist_col."""
        rng = np.random.default_rng(seed)
        H, W, s = self.H, self.W, self.s
        y_top = max(0, int((ridge.min() - 4) * s))
        Y = self.Y[y_top:]
        r = ridge[None, :]
        depth = Y - r
        cov = clamp01(depth * s + 0.5)
        t = smoothstep(0, fade, depth) ** 0.8
        col = mix(dark, light, t)
        hh = H - y_top
        # tonal blots (wash unevenness)
        blot = fbm(hh, W, streak_cell * 3.0 * s, rng, octaves=3) - 0.5
        col = col * (1 + (blot * texture * 0.6 * (1 - 0.5 * t))[..., None])
        # ridged texture strokes ('cun'), concentrated near the ridge
        n = fbm(hh, W, streak_cell * s, rng, octaves=3, aniso=(2.8, 0.42))
        ridged = 1 - np.abs(2 * n - 1)
        cun = clamp01((ridged - 0.86) * 6.0) * np.exp(-depth / (fade * 0.4))
        n2 = fbm(hh, W, streak_cell * 0.45 * s, rng, octaves=2, aniso=(2.4, 0.45))
        cun2 = clamp01(((1 - np.abs(2 * n2 - 1)) - 0.88) * 7.0) * np.exp(-depth / (fade * 0.28))
        presence = clamp01((fbm(hh, W, streak_cell * 2.0 * s, rng, octaves=2) - 0.35) * 2.5)
        col = mix(col, np.asarray(dark) * 0.85, clamp01((cun + cun2 * 0.7) * presence * texture * 1.4))
        # fold lines: shifted inner ridges, dark at their top and washing out below
        for k in range(folds):
            dk = fold_depth[0] + (fold_depth[1] - fold_depth[0]) * (k + 0.5) / folds
            nk = noise1d(W, (80 + 40 * k) * s, rng, octaves=4, gain=0.55)
            rk = ridge + dk * (0.55 + 0.9 * clamp01(nk * 0.8 + 0.5))
            # follow the outer silhouette loosely
            rk = ndimage.gaussian_filter1d(rk, 10 * s) * 0.6 + (ridge + dk) * 0.4
            dd = Y - rk[None, :]
            g = np.where(dd > 0, np.exp(-dd / (fade * 0.18)), 0.0) * clamp01(dd * s + 0.5)
            vis = clamp01(noise1d(W, 60 * s, rng, octaves=3) * 1.6 + 0.35)
            g *= (fold_strength * (1 - smoothstep(0, fade * 1.4, rk - ridge)) * vis)[None, :]
            col = mix(col, np.asarray(dark) * 0.9, clamp01(g))
        # slope lighting (left-facing slopes lit)
        slope = np.gradient(ndimage.gaussian_filter1d(ridge, 6 * s)) * s
        litm = np.clip(-slope * 1.5, -1, 1)[None, :] * np.exp(-depth / (fade * 0.45))
        col = col + (np.asarray(light) - col) * (clamp01(litm) * lit * 3)[..., None]
        col = col * (1 - clamp01(-litm) * lit)[..., None]
        # brushed ridge outline
        wvar = 0.5 + 1.0 * clamp01(noise1d(W, 40 * s, rng, octaves=3) * 0.8 + 0.5)
        ew = edge_w * wvar[None, :]
        line = np.exp(-np.maximum(depth, 0) / np.maximum(ew, 0.3)) * edge
        col = mix(col, np.asarray(dark) * 0.7, clamp01(line))
        a = cov * alpha
        if mist_from is not None and mist_col is not None:
            col = mix(col, mist_col, smoothstep(mist_from[0], mist_from[1], Y))
        sub = self.rgb[y_top:]
        self.rgb[y_top:] = sub + (np.clip(col, 0, 1) - sub) * a[..., None]
        return self

    def mist(self, y, height, color, opacity=0.8, seed=0, cell=160.0, streak=True):
        """Horizontal mist band centred at y with soft ragged edges."""
        rng = np.random.default_rng(seed)
        H, W, s = self.H, self.W, self.s
        y0 = max(0, int((y - height * 1.6) * s))
        y1 = min(H, int((y + height * 1.6) * s) + 1)
        if y1 <= y0:
            return self
        n = fbm(y1 - y0, W, cell * s, rng, octaves=5, aniso=(0.35, 2.2) if streak else (1, 1))
        d = (self.Y[y0:y1] - y) / (height / 2.0)
        m = np.exp(-d ** 2 * 1.6) * clamp01((n - 0.25) * 1.6)
        sub = self.rgb[y0:y1]
        self.rgb[y0:y1] = sub + (np.asarray(color, np.float32) - sub) * (clamp01(m) * opacity)[..., None]
        return self

    def haze(self, y0, y1, color, opacity=0.6):
        """Flat atmospheric haze increasing towards y1 (e.g. valley fog)."""
        m = smoothstep(y0, y1, self.Y)
        return self.paint(color, m, opacity)

    def tree_dots(self, ridge, color, density=0.08, size=2.0, xr=None, seed=0, opacity=0.9,
                  min_depth=0.0):
        """Small vertical ink dabs along a ridge (distant trees / moss dots)."""
        rng = np.random.default_rng(seed)
        m = self.mask()
        x0, x1 = xr if xr else (0, self.ow)
        x = x0
        while x < x1:
            x += rng.exponential(1.0 / density)
            ix = int(np.clip(x * self.s, 0, self.W - 1))
            yy = ridge[ix] + min_depth + rng.uniform(0, size * 1.5)
            hh = size * rng.uniform(1.0, 2.4)
            ww = size * rng.uniform(0.35, 0.7)
            m.ellipse(x, yy - hh * 0.6, ww, hh)
        return self.paint(color, m.arr(), opacity)

    @staticmethod
    def pine_pad(m, cx, cy, w, h, rng, needle_w=None):
        """Pine needle cluster: overlapping flattened lobes with fine needle strokes radiating
        from their upper edges. (cx, cy) is the base centre of the pad."""
        k = int(rng.integers(3, 6))
        nw = needle_w if needle_w is not None else max(0.45, h * 0.035)
        lobes = []
        for i in range(k):
            t = (i + 0.5) / k
            ex = cx - w / 2 + w * t + rng.uniform(-w, w) * 0.04
            eh = h * (0.55 + 0.45 * math.sin(math.pi * t)) * rng.uniform(0.85, 1.1)
            ew = w / k * rng.uniform(0.7, 0.95) + h * 0.2
            ey = cy - eh * 0.45
            m.ellipse(ex, ey, ew, eh * 0.55)
            lobes.append((ex, ey, ew, eh * 0.55))
        for (ex, ey, ew, eh) in lobes:
            nn = int(ew * 1.4) + 6
            for j in range(nn):
                a = math.pi + math.pi * (j + rng.uniform(0, 1)) / nn
                px, py = ex + math.cos(a) * ew * 0.92, ey + math.sin(a) * eh * 0.92
                ang = math.atan2(math.sin(a) * ew, math.cos(a) * eh)
                L = h * rng.uniform(0.18, 0.34)
                m.line([(px, py), (px + math.cos(ang) * L, py + math.sin(ang) * L)], nw, round_caps=False)
        return m

    def pine(self, m, x, y, height, lean=0.0, seed=0, pads=None, spread=1.0):
        """Stylised Chinese pine silhouette into Mask m (trunk base at x, y): gnarled tapered trunk,
        angular near-horizontal limbs and bristly layered needle pads."""
        rng = np.random.default_rng(seed)
        h = height
        pts = []
        b1 = rng.uniform(-0.08, 0.08)
        for i in range(16):
            t = i / 15.0
            px = x + lean * h * t + math.sin(t * 2.6 + seed) * h * 0.05 + b1 * h * t * t * 3
            pts.append((px, y - h * t))
        m.brush(pts, h * 0.07, h * 0.022)
        # root flare
        m.poly([(x - h * 0.09, y + 1), (x - h * 0.02, y - h * 0.08), (x + h * 0.03, y - h * 0.08), (x + h * 0.1, y + 1)])
        top = pts[-1]
        npads = pads or int(rng.integers(4, 7))
        for k in range(npads):
            t = 0.35 + 0.62 * k / max(1, npads - 1) + rng.uniform(-0.03, 0.03)
            t = min(t, 0.97)
            ix = int(t * 15)
            bx, by = pts[ix]
            side = -1 if (k + seed) % 2 == 0 else 1
            if k == npads - 1:
                side = -1 if lean > 0 else 1
            blen = h * spread * (0.16 + 0.30 * (1 - t)) * rng.uniform(0.8, 1.15)
            ex = bx + side * blen
            ey = by - h * rng.uniform(-0.02, 0.06)
            kx = bx + side * blen * 0.45
            ky = by + h * rng.uniform(-0.02, 0.03)
            m.brush([(bx, by), (kx, ky), (ex, ey)], h * 0.028, h * 0.01)
            # pads: a main bristly dome plus one or two overlapping smaller ones
            pw = blen * rng.uniform(0.85, 1.15) + h * 0.07
            ph = h * rng.uniform(0.075, 0.095)
            cx = ex - side * pw * 0.12
            self.pine_pad(m, cx, ey + ph * 0.25, pw, ph * 1.3, rng)
            if rng.random() < 0.7:
                self.pine_pad(m, cx + side * pw * 0.18, ey - ph * 0.55, pw * 0.6, ph * 1.0, rng)
        # crown
        self.pine_pad(m, top[0], top[1] + h * 0.05, h * 0.3 * spread, h * 0.11, rng)
        return m

    def grass_tufts(self, m, x0, x1, ybase, rng, density=0.3, hmin=3, hmax=10):
        x = x0
        while x < x1:
            x += rng.exponential(1.0 / density)
            yb = ybase(x) if callable(ybase) else ybase
            for _ in range(int(rng.integers(2, 5))):
                hgt = rng.uniform(hmin, hmax)
                ang = rng.uniform(-0.5, 0.5)
                m.brush([(x, yb), (x + ang * hgt * 0.5, yb - hgt * 0.6), (x + ang * hgt, yb - hgt)],
                        1.2, 0.2)
        return m

    def paper(self, strength=0.05, seed=7, warm=None):
        rng = np.random.default_rng(seed)
        g = paper_grain(self.H, self.W, rng, scale=self.s)
        self.rgb = self.rgb * (1 + g[..., None] * strength)
        if warm is not None:
            self.rgb = mix(self.rgb, self.rgb * np.asarray(warm), 1.0)
        return self

    def vignette(self, strength=0.35, color=(0.10, 0.07, 0.05), power=2.2, inner=0.55):
        cx, cy = self.ow / 2, self.oh / 2
        d = np.hypot((self.X - cx) / (self.ow / 2), (self.Y - cy) / (self.oh / 2)) / math.sqrt(2)
        m = smoothstep(inner * 0.7, 1.0, d) ** (power / 2)
        return self.paint(color, m, strength)

    def grade(self, lift=0.0, gamma=1.0, sat=1.0, tint=None):
        rgb = np.clip(self.rgb, 0, 1)
        if sat != 1.0:
            l = (rgb @ np.array([0.299, 0.587, 0.114], np.float32))[..., None]
            rgb = l + (rgb - l) * sat
        if gamma != 1.0:
            rgb = np.clip(rgb, 0, 1) ** gamma
        if tint is not None:
            rgb = rgb * np.asarray(tint, np.float32)
        rgb = lift + rgb * (1 - lift)
        self.rgb = np.clip(rgb, 0, 1)
        return self

    def finish(self):
        return reduce(self.rgb, self.s)

    def save(self, path, dither_seed=99):
        im = to_pil(self.finish(), None, dither_seed)
        save_png(im, path)
        return im


# ----------------------------------------------------------------------------------------------
# Architecture & figures (silhouette builders used by the paintings)
# ----------------------------------------------------------------------------------------------

def roof_poly(cx, y, w, h, curl=0.35, n=16):
    """Chinese hip roof seen from the front: ridge at y, eaves at y+h with upturned tips.
    Returns a polygon (output px)."""
    hw = w / 2.0
    rw = hw * 0.55   # ridge half width
    tip = h * curl
    left = bez((cx - rw, y), (cx - rw - hw * 0.25, y + h * 0.55), (cx - hw * 0.85, y + h * 0.95),
               (cx - hw - h * 0.15, y + h - tip), n)
    right = bez((cx + hw + h * 0.15, y + h - tip), (cx + hw * 0.85, y + h * 0.95),
                (cx + rw + hw * 0.25, y + h * 0.55), (cx + rw, y), n)
    under = qbez((cx - hw - h * 0.15, y + h - tip), (cx, y + h * 1.12), (cx + hw + h * 0.15, y + h - tip), n)
    ridge_l = [(cx - rw - h * 0.12, y - h * 0.12), (cx + rw + h * 0.12, y - h * 0.12)]
    return [ridge_l[0]] + left + under[1:-1] + right + [ridge_l[1]]


def pavilion(m, cx, ybase, w, tiers=2, story_h=None, roof_h=None, body=True, roofs_only=False):
    """Multi-tier tower: returns list of (kind, polygon) parts; also paints all into m."""
    sh = story_h or w * 0.45
    rh = roof_h or w * 0.28
    parts = []
    y = ybase
    ww = w
    for i in range(tiers):
        bw = ww * 0.72
        if body and not roofs_only:
            body_poly = [(cx - bw / 2, y), (cx - bw / 2, y - sh), (cx + bw / 2, y - sh), (cx + bw / 2, y)]
            parts.append(("body", body_poly))
            m.poly(body_poly)
        y -= sh
        rp = roof_poly(cx, y - rh * 0.75, ww * 1.15, rh)
        parts.append(("roof", rp))
        m.poly(rp)
        y -= rh * 0.75
        ww *= 0.78
        sh *= 0.8
    return parts


POSES = {
    # joints relative to the feet (x right = facing direction, y up), in units of height h:
    # hip, shoulder, head, front/back foot, front/back knee, front/back hand
    "stand": dict(hip=(0, .47), sh=(0, .79), head=(0.01, .91), ff=(.05, 0), bf=(-.05, 0), fk=(.03, .24), bk=(-.03, .24),
                  fh=(.07, .5), bh=(-.07, .5)),
    "walk": dict(hip=(0, .46), sh=(.02, .78), head=(.04, .9), ff=(.15, 0), bf=(-.13, 0), fk=(.09, .24), bk=(-.05, .22),
                 fh=(.12, .52), bh=(-.1, .5)),
    "run": dict(hip=(0, .44), sh=(.08, .74), head=(.12, .85), ff=(.2, .04), bf=(-.2, .06), fk=(.16, .26), bk=(-.06, .18),
                fh=(.2, .6), bh=(-.14, .48)),
    "bow": dict(hip=(0, .45), sh=(.24, .6), head=(.33, .54), ff=(.04, 0), bf=(-.06, 0), fk=(.03, .23), bk=(-.04, .23),
                fh=(.3, .32), bh=(.24, .3)),
    "kneel": dict(hip=(-.06, .27), sh=(.1, .5), head=(.17, .55), ff=(.12, 0), bf=(-.2, 0), fk=(.14, .03), bk=(.0, .02),
                  fh=(.24, .1), bh=(.2, .08)),
    "stance": dict(hip=(0, .4), sh=(.03, .71), head=(.05, .83), ff=(.2, 0), bf=(-.18, 0), fk=(.15, .2), bk=(-.12, .2),
                   fh=(.24, .78), bh=(-.18, .55)),
    "salute": dict(hip=(0, .47), sh=(0, .79), head=(0.01, .91), ff=(.05, 0), bf=(-.05, 0), fk=(.03, .24), bk=(-.03, .24),
                   fh=(.1, .66), bh=(.08, .66)),
    "point": dict(hip=(0, .47), sh=(0, .79), head=(0.02, .91), ff=(.05, 0), bf=(-.06, 0), fk=(.03, .24), bk=(-.03, .24),
                  fh=(.24, 1.02), bh=(-.06, .5)),
}


def figure(m, x, yf, h, pose="stand", hat="topknot", weapon=None, facing=1, robe=False, cloak=False):
    """Ink silhouette of a person (feet at yf, height h) into Mask m.

    pose: stand walk run bow kneel stance salute point. hat: topknot straw guan helmet hood none.
    robe: long robe to the ankles (officials, scholars); otherwise tunic + trousers.
    weapon: spear sword_up staff banner pole (carrying pole on the shoulder) fan."""
    J = POSES[pose]
    f = facing

    def P(k):
        jx, jy = J[k]
        return (x + f * jx * h, yf - jy * h)
    hip, sh, head = P("hip"), P("sh"), P("head")
    lw = h * 0.065
    # legs
    for foot, knee in (("bf", "bk"), ("ff", "fk")):
        m.brush([hip, P(knee), P(foot)], lw * 1.2, lw * 0.8)
        fx, fy = P(foot)
        m.ellipse(fx + f * h * 0.02, fy - h * 0.012, h * 0.04, h * 0.018)
    # torso
    tw_s, tw_h = h * 0.085, h * 0.07
    dx, dy = sh[0] - hip[0], sh[1] - hip[1]
    L = math.hypot(dx, dy) + 1e-6
    nx, ny = -dy / L, dx / L
    m.poly([(hip[0] + nx * tw_h, hip[1] + ny * tw_h), (sh[0] + nx * tw_s, sh[1] + ny * tw_s),
            (sh[0] - nx * tw_s, sh[1] - ny * tw_s), (hip[0] - nx * tw_h, hip[1] - ny * tw_h)])
    m.circle(sh[0], sh[1], tw_s * 0.95)
    # skirt: tunic to the knees, robe to the ankles
    if pose != "kneel":
        bot = yf - (0.04 if robe else 0.25) * h
        spread = (0.17 if robe else 0.12) * h
        kx = (P("fk")[0] + P("bk")[0]) / 2
        m.poly([(hip[0] - tw_h * 1.1, hip[1] - h * 0.02), (hip[0] + tw_h * 1.1, hip[1] - h * 0.02),
                (kx + spread, bot), (kx - spread, bot)])
    else:
        m.poly([(hip[0] - h * 0.1, hip[1] - h * 0.02), (hip[0] + h * 0.08, hip[1] - h * 0.06), (P("fk")[0] + h * 0.04, yf),
                (P("bf")[0], yf)])
    if cloak:
        m.poly([(sh[0] - f * tw_s * 1.4, sh[1] - h * 0.02), (sh[0] + f * tw_s * 0.4, sh[1] - h * 0.04),
                (hip[0] - f * h * 0.08, yf - h * 0.2), (hip[0] - f * h * 0.22, yf - h * 0.16)])
    # arms
    for hand in ("bh", "fh"):
        hx, hy = P(hand)
        ex, ey = (sh[0] + hx) / 2 - f * h * 0.02, (sh[1] + hy) / 2 + h * 0.02
        m.brush([sh, (ex, ey), (hx, hy)], lw * 1.05, lw * 0.75)
        if robe:
            m.brush([(ex, ey), (hx, hy)], lw * 1.7, lw * 1.5)
    # neck and head
    m.brush([sh, head], lw * 0.9, lw * 0.9)
    hr = h * 0.062
    hx, hy = head
    m.ellipse(hx, hy, hr * 0.95, hr * 1.05)
    if hat == "straw":
        m.poly([(hx - hr * 2.7, hy - hr * 0.1), (hx, hy - hr * 2.0), (hx + hr * 2.7, hy - hr * 0.1), (hx, hy - hr * 0.5)])
    elif hat == "guan":
        m.poly([(hx - hr * 0.8, hy - hr * 0.6), (hx - hr * 0.7, hy - hr * 2.0), (hx + hr * 0.7, hy - hr * 2.0), (hx + hr * 0.8, hy - hr * 0.6)])
        m.brush([(hx - hr * 2.0, hy - hr * 1.6), (hx + hr * 2.0, hy - hr * 1.6)], hr * 0.35, hr * 0.35)
    elif hat == "helmet":
        m.poly([(hx - hr * 1.2, hy + hr * 0.5), (hx - hr * 1.15, hy - hr * 0.8), (hx, hy - hr * 1.6),
                (hx + hr * 1.15, hy - hr * 0.8), (hx + hr * 1.2, hy + hr * 0.5)])
        m.brush([(hx, hy - hr * 1.5), (hx - f * hr * 0.6, hy - hr * 2.8)], hr * 0.55, hr * 0.15)
    elif hat == "topknot":
        m.circle(hx - f * hr * 0.15, hy - hr * 1.15, hr * 0.5)
    elif hat == "hood":
        m.poly([(hx - hr * 1.3, hy + hr * 1.6), (hx - hr * 1.25, hy - hr * 0.6), (hx - f * hr * 0.2, hy - hr * 1.5),
                (hx + hr * 1.2, hy - hr * 0.5), (hx + hr * 1.3, hy + hr * 1.6)])
    # weapons / props held in the front hand
    fx_, fy_ = P("fh")
    if weapon == "spear":
        m.line([(fx_ - f * h * 0.02, fy_ + h * 0.45), (fx_ + f * h * 0.06, fy_ - h * 0.85)], max(0.6, h * 0.018), round_caps=False)
        tx, ty = fx_ + f * h * 0.06, fy_ - h * 0.85
        m.poly([(tx - h * 0.018, ty + h * 0.01), (tx + f * h * 0.006, ty - h * 0.09), (tx + h * 0.018, ty + h * 0.01)])
    elif weapon == "sword_up":
        m.brush([(fx_, fy_), (fx_ + f * h * 0.14, fy_ - h * 0.42)], h * 0.022, h * 0.008)
        m.brush([(fx_ - f * h * 0.03, fy_ + h * 0.01), (fx_ + f * h * 0.04, fy_ - h * 0.02)], h * 0.02, h * 0.02)
    elif weapon == "sword":
        m.brush([(fx_, fy_), (fx_ + f * h * 0.38, fy_ + h * 0.05)], h * 0.022, h * 0.008)
    elif weapon == "staff":
        m.line([(fx_ + f * h * 0.02, yf), (fx_ - f * h * 0.01, fy_ - h * 0.4)], max(0.6, h * 0.022), round_caps=False)
    elif weapon == "banner":
        m.line([(fx_, yf), (fx_, yf - h * 1.6)], max(0.6, h * 0.022), round_caps=False)
    elif weapon == "pole":
        m.line([(sh[0] - f * h * 0.42, sh[1] - h * 0.02), (sh[0] + f * h * 0.42, sh[1] - h * 0.02)], max(0.6, h * 0.022))
        for sx in (-1, 1):
            bx = sh[0] + sx * f * h * 0.38
            m.line([(bx, sh[1]), (bx, sh[1] + h * 0.25)], max(0.4, h * 0.01), round_caps=False)
            m.poly([(bx - h * 0.09, sh[1] + h * 0.25), (bx + h * 0.09, sh[1] + h * 0.25), (bx + h * 0.07, sh[1] + h * 0.38), (bx - h * 0.07, sh[1] + h * 0.38)])
    elif weapon == "fan":
        m.poly([(fx_, fy_)] + arc_pts(fx_, fy_, h * 0.14, h * 0.14, -120 if f > 0 else -60, -30 if f > 0 else -150, 8))
    return m


def horse(m, x, yf, h, facing=1, gallop=False):
    """Side-view horse silhouette, hooves at yf, height h (to the ears)."""
    # outline designed on a 100 x 80 box facing right, ground at y = 80
    body = [(20, 28), (35, 24), (55, 25), (66, 22), (74, 12), (82, 3), (85, 0), (87, 4), (94, 11), (101, 21),
            (99, 26), (91, 25), (84, 23), (80, 32), (79, 42), (70, 49), (58, 51), (44, 51), (33, 49),
            (24, 46), (18, 38), (17, 30)]
    tail = [(19, 29), (13, 40), (8, 55), (5, 58), (9, 46), (14, 32)]
    if gallop:
        legs = [[(74, 44), (84, 56), (92, 62)], [(68, 46), (72, 60), (66, 74)],
                [(30, 46), (20, 58), (10, 64)], [(36, 47), (40, 62), (46, 76)]]
    else:
        legs = [[(76, 44), (77, 62), (78, 79)], [(70, 46), (70, 62), (71, 79)],
                [(30, 46), (28, 62), (30, 79)], [(37, 47), (36, 62), (37, 79)]]
    sc = h / 80.0

    def tr(p):
        px, py = p
        if facing < 0:
            px = 100 - px
        return (x + (px - 50) * sc, yf - (80 - py) * sc)
    m.poly([tr(p) for p in body])
    m.poly([tr(p) for p in tail])
    for lg in legs:
        m.brush([tr(p) for p in lg], 5.5 * sc, 3.2 * sc)
    return m


def flag(m, px, py, w, h, wave=0.25, facing=1, phase=0.0, tail=True):
    """Waving banner attached at (px, py) top of the pole side."""
    n = 14
    top, bot = [], []
    for i in range(n + 1):
        t = i / n
        xx = px + facing * w * t
        dy = math.sin(t * 5.0 + phase) * h * wave * t
        top.append((xx, py + dy))
        bot.append((xx, py + h * (1 - 0.25 * t) + dy))
    poly = top + bot[::-1]
    m.poly(poly)
    return poly


# ----------------------------------------------------------------------------------------------
# Shared chrome helpers
# ----------------------------------------------------------------------------------------------

def shade(col, sh, hi, lo, k_hi=1.0, k_lo=1.0):
    """Apply signed shading sh (-1..1) by mixing towards hi (sh>0) or lo (sh<0)."""
    col = np.asarray(col, np.float32)
    if col.ndim == 1:
        col = np.broadcast_to(col, sh.shape + (3,)).copy()
    col = mix(col, hi, clamp01(sh) * k_hi)
    col = mix(col, lo, clamp01(-sh) * k_lo)
    return col


def make_seal(size=128, chars="铁血王座", seed=5, color=None, rot=-2.5, ss=4):
    """Red square seal stamp with carved (transparent) brush characters, 2x2 read right
    column first (traditional order). Returns a Layer at `size` px."""
    rng = np.random.default_rng(seed)
    S = ss
    W = size * S
    col = PAL["seal"] if color is None else color
    m = Mask(W, W, S)
    pad = size * 0.08
    m.rrect(pad, pad, size - pad, size - pad, size * 0.035)
    base = m.arr()
    # rough stamped edge
    n = fbm(W, W, 6 * S, rng, octaves=3) - 0.5
    edge = clamp01((inner_dist(base) / S - 0.0) / 1.2)
    base = clamp01(base * (0.6 + edge * 0.4) + n * 0.9 * (1 - edge))
    base = (base > 0.5).astype(np.float32)
    # carved border line
    inset = size * 0.075
    lw = size * 0.022
    carve = Mask(W, W, S)
    carve.d.rectangle([(pad + inset) * S, (pad + inset) * S, (size - pad - inset) * S, (size - pad - inset) * S],
                      outline=255, width=int(lw * S))
    # characters
    inner0 = pad + inset + lw * 1.6
    inner1 = size - pad - inset - lw * 1.6
    cell = (inner1 - inner0) / 2.0
    f = font(FONT_BRUSH, cell * 1.08 * S)
    order = [(1, 0), (1, 1), (0, 0), (0, 1)]  # (column, row): right column first, top to bottom
    for ch, (cx, cy) in zip(chars, order):
        x = inner0 + cell * (cx + 0.5)
        y = inner0 + cell * (cy + 0.5)
        carve.d.text((x * S, y * S + cell * 0.04 * S), ch, font=f, fill=255, anchor="mm")
    cm = carve.arr()
    cm = ndimage.grey_dilation(cm, size=(int(S * 0.6) + 1, int(S * 0.6) + 1))
    a = base * (1 - cm)
    # uneven ink: speckles and pressure
    speck = fbm(W, W, 2.5 * S, rng, octaves=2)
    press = fbm(W, W, 40 * S, rng, octaves=3)
    holes = (speck > 0.80).astype(np.float32) * 0.85
    dens = clamp01(0.82 + (press - 0.5) * 0.5) * (1 - holes)
    a = a * dens
    if rot:
        a = ndimage.rotate(a, rot, reshape=False, order=1, mode="constant")
    lay = Layer(W, W)
    tone = (press - 0.5)[..., None] * 0.12
    lay.paint(np.clip(col * (1 + tone), 0, 1), clamp01(a))
    return lay.reduced(S)
