"""Raster helpers for the procedural portrait generator (see portraits.py).

All geometry is expressed in *final* pixel units (the 192x240 output); the
canvas is rendered at SCALE x that size and downsampled at the end.  Masks are
float32 arrays in [0, 1] at working resolution.
"""
import math

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

W, H = 192, 240
SCALE = 3
WW, HH = W * SCALE, H * SCALE
SS = 2  # extra supersampling used when rasterising polygons

# Light comes from the top-left, slightly in front of the subject.
LIGHT = np.array([-0.48, -0.56, 0.68], dtype=np.float32)
LIGHT /= np.linalg.norm(LIGHT)

_GRID = None


def grid():
    """Pixel-centre coordinates (in final units) of the working canvas."""
    global _GRID
    if _GRID is None:
        xs = (np.arange(WW, dtype=np.float32) + 0.5) / SCALE
        ys = (np.arange(HH, dtype=np.float32) + 0.5) / SCALE
        _GRID = np.meshgrid(xs, ys)
    return _GRID


def hexc(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)


def mix(a, b, t):
    return a + (b - a) * t


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def clamp01(x):
    return np.clip(x, 0.0, 1.0)


def blur(a, sigma):
    """Gaussian blur, sigma in final units."""
    if sigma <= 0:
        return a
    return ndi.gaussian_filter(a, sigma * SCALE, mode='nearest')


def blur_dir(a, sigma_along, sigma_across, angle):
    """Anisotropic blur (approximated by rotating, blurring, rotating back)."""
    deg = math.degrees(angle)
    r = ndi.rotate(a, deg, reshape=True, order=1, mode='nearest')
    r = ndi.gaussian_filter(r, (sigma_across * SCALE, sigma_along * SCALE), mode='nearest')
    r = ndi.rotate(r, -deg, reshape=True, order=1, mode='nearest')
    oy = (r.shape[0] - a.shape[0]) // 2
    ox = (r.shape[1] - a.shape[1]) // 2
    return r[oy:oy + a.shape[0], ox:ox + a.shape[1]]


# --------------------------------------------------------------------------
# Curves
# --------------------------------------------------------------------------

def catmull(points, n=10, closed=False):
    """Centripetal-ish Catmull-Rom through points -> dense polyline (list of xy)."""
    p = [np.asarray(q, dtype=np.float64) for q in points]
    if len(p) < 2:
        return [tuple(q) for q in p]
    if closed:
        pts = [p[-1]] + p + [p[0], p[1]]
        segs = len(p)
    else:
        pts = [p[0] * 2 - p[1]] + p + [p[-1] * 2 - p[-2]]
        segs = len(p) - 1
    out = []
    for i in range(segs):
        p0, p1, p2, p3 = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            q = 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                       + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
            out.append((float(q[0]), float(q[1])))
    if not closed:
        out.append((float(p[-1][0]), float(p[-1][1])))
    return out


def bezier(p0, p1, p2, p3, n=16):
    p0, p1, p2, p3 = (np.asarray(v, dtype=np.float64) for v in (p0, p1, p2, p3))
    out = []
    for k in range(n + 1):
        t = k / n
        q = ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3 * p3
        out.append((float(q[0]), float(q[1])))
    return out


def resample(poly, n):
    """Resample an open polyline to n points evenly spaced by arc length."""
    a = np.asarray(poly, dtype=np.float64)
    seg = np.sqrt(((a[1:] - a[:-1]) ** 2).sum(1))
    s = np.concatenate([[0], np.cumsum(seg)])
    if s[-1] <= 1e-9:
        return [tuple(a[0])] * n
    t = np.linspace(0, s[-1], n)
    x = np.interp(t, s, a[:, 0])
    y = np.interp(t, s, a[:, 1])
    return list(zip(x.tolist(), y.tolist()))


# --------------------------------------------------------------------------
# Masks
# --------------------------------------------------------------------------

def _to_px(points, f):
    return [(x * f, y * f) for x, y in points]


def poly(points):
    """Filled polygon (final-unit coords) -> antialiased mask."""
    return polys([points])


def polys(list_of_points):
    f = SCALE * SS
    im = Image.new('L', (WW * SS, HH * SS), 0)
    d = ImageDraw.Draw(im)
    for pts in list_of_points:
        if len(pts) >= 3:
            d.polygon(_to_px(pts, f), fill=255)
    im = im.resize((WW, HH), Image.BOX)
    return np.asarray(im, dtype=np.float32) / 255.0


def ellipse(cx, cy, rx, ry, ang=0.0):
    X, Y = grid()
    c, s = math.cos(ang), math.sin(ang)
    u = (X - cx) * c + (Y - cy) * s
    v = -(X - cx) * s + (Y - cy) * c
    r = np.sqrt((u / rx) ** 2 + (v / ry) ** 2)
    d = (r - 1.0) * min(rx, ry)
    return clamp01(0.5 - d * SCALE).astype(np.float32)


def stroke_outline(points, widths):
    """Polygon outlining a polyline with per-vertex widths (final units)."""
    a = np.asarray(points, dtype=np.float64)
    n = len(a)
    if np.isscalar(widths):
        widths = [widths] * n
    widths = np.asarray(widths, dtype=np.float64)
    if len(widths) != n:
        widths = np.interp(np.linspace(0, 1, n), np.linspace(0, 1, len(widths)), widths)
    if n < 2:
        return []
    tang = np.zeros_like(a)
    tang[1:-1] = a[2:] - a[:-2]
    tang[0] = a[1] - a[0]
    tang[-1] = a[-1] - a[-2]
    ln = np.sqrt((tang ** 2).sum(1)) + 1e-9
    tang /= ln[:, None]
    nrm = np.stack([-tang[:, 1], tang[:, 0]], 1)
    left = a + nrm * (widths[:, None] * 0.5)
    right = a - nrm * (widths[:, None] * 0.5)
    return [tuple(p) for p in left] + [tuple(p) for p in right[::-1]]


def taper(n, w0, w1, wmid=None, power=1.0):
    """Width profile for a brush stroke: w0 at start, wmid in the middle, w1 at the end."""
    t = np.linspace(0, 1, n)
    if wmid is None:
        return w0 + (w1 - w0) * t
    # quadratic through three points
    bell = np.sin(np.pi * t) ** power
    base = w0 + (w1 - w0) * t
    return base + (wmid - (w0 + w1) * 0.5) * bell


def stroke(points, widths):
    return poly(stroke_outline(points, widths))


def strokes(list_of_strokes):
    """Union of many strokes [(points, widths), ...] drawn in one pass."""
    return polys([stroke_outline(p, w) for p, w in list_of_strokes])


class StrokeLayer:
    """Accumulates many thin strokes with individual intensities into one map.

    Each stroke is drawn with value `v` (0..1); overlapping strokes take the
    max (PIL draws in order, so later strokes simply overwrite).  Used for hair
    strands, brush texture and fine linework.
    """

    def __init__(self):
        self.f = SCALE * SS
        self.im = Image.new('L', (WW * SS, HH * SS), 0)
        self.d = ImageDraw.Draw(self.im)

    def add(self, points, widths, v=1.0):
        pts = stroke_outline(points, widths)
        if len(pts) >= 3:
            self.d.polygon(_to_px(pts, self.f), fill=int(np.clip(v, 0, 1) * 255))

    def add_poly(self, pts, v=1.0):
        if len(pts) >= 3:
            self.d.polygon(_to_px(pts, self.f), fill=int(np.clip(v, 0, 1) * 255))

    def result(self):
        im = self.im.resize((WW, HH), Image.BOX)
        return np.asarray(im, dtype=np.float32) / 255.0


# --------------------------------------------------------------------------
# Noise / texture
# --------------------------------------------------------------------------

def _upsample(g, w, h):
    im = Image.fromarray(g.astype(np.float32), 'F')
    return np.asarray(im.resize((w, h), Image.BICUBIC), dtype=np.float32)


def value_noise(rng, scale, octaves=3, persistence=0.5):
    """Smooth fractal noise, roughly unit amplitude; `scale` = feature size in final px."""
    out = np.zeros((HH, WW), dtype=np.float32)
    amp, tot = 1.0, 0.0
    sc = scale
    for _ in range(octaves):
        gh = max(2, int(math.ceil(H / sc)) + 1)
        gw = max(2, int(math.ceil(W / sc)) + 1)
        g = rng.standard_normal((gh, gw)).astype(np.float32)
        out += _upsample(g, WW, HH) * amp
        tot += amp
        amp *= persistence
        sc *= 0.5
    return out / tot


def fiber_noise(rng, length, angle, density=1.0):
    """Directional streaky noise (paper fibres / brush drag), roughly unit variance."""
    n = rng.standard_normal((HH, WW)).astype(np.float32) * density
    r = blur_dir(n, length, 0.25, angle)
    return r / (r.std() + 1e-6)


# --------------------------------------------------------------------------
# Shading
# --------------------------------------------------------------------------

def normals_from_height(h, strength=1.0):
    """Height in final px -> unit normals (x right, y down, z to viewer)."""
    gy, gx = np.gradient(h * strength)
    nx = -gx * SCALE
    ny = -gy * SCALE
    nz = np.ones_like(h)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    return nx / ln, ny / ln, nz / ln


def lambert(nx, ny, nz, light=LIGHT, wrap=0.25):
    d = nx * light[0] + ny * light[1] + nz * light[2]
    return clamp01((d + wrap) / (1.0 + wrap))


def pillow(mask, radius, strength=1.0, light=LIGHT, wrap=0.3):
    """Soft 'inflated' shading of a 2D mask: returns lighting in [0, 1]."""
    m = (mask > 0.5).astype(np.float32)
    d = ndi.distance_transform_edt(m) / SCALE
    h = np.sqrt(clamp01(d / radius)) * radius * 0.9 * strength
    h = blur(h, radius * 0.15 + 0.3)
    nx, ny, nz = normals_from_height(h)
    return lambert(nx, ny, nz, light, wrap)


def edge_distance(mask):
    """Inside distance to the mask edge (final px)."""
    m = mask > 0.5
    return ndi.distance_transform_edt(m).astype(np.float32) / SCALE


def outside_distance(mask):
    m = mask <= 0.5
    return ndi.distance_transform_edt(m).astype(np.float32) / SCALE


def ink_outline(mask, width, rng=None, var=0.35, light_bias=0.6, scale=6.0):
    """Ink line hugging the inside of a mask edge.

    Width varies with noise and is thicker on the side facing away from the light.
    Returns an alpha map.
    """
    d = edge_distance(mask)
    wmap = np.full(mask.shape, width, dtype=np.float32)
    if light_bias:
        mb = blur(mask, 2.0)
        gy, gx = np.gradient(mb)
        ln = np.sqrt(gx * gx + gy * gy) + 1e-6
        # outward normal = -grad; facing light if dot(outward, light2d) > 0
        facing = (-(gx / ln) * LIGHT[0] - (gy / ln) * LIGHT[1]) / math.hypot(LIGHT[0], LIGHT[1])
        wmap *= 1.0 - light_bias * 0.5 * facing
    if rng is not None and var:
        wmap *= 1.0 + var * np.clip(value_noise(rng, scale, 2), -1.5, 1.5)
    a = clamp01((wmap - d) * SCALE + 0.5) * clamp01(mask * 2.0)
    return a


# --------------------------------------------------------------------------
# Canvas
# --------------------------------------------------------------------------

class Canvas:
    def __init__(self, bg=None):
        self.rgb = np.zeros((HH, WW, 3), dtype=np.float32)
        if bg is not None:
            self.rgb[:] = bg

    def paint(self, mask, color, alpha=1.0):
        """Normal blend.  color: rgb triple or HxWx3 array."""
        m = (mask * alpha)[..., None]
        c = np.asarray(color, dtype=np.float32)
        self.rgb += (c - self.rgb) * m

    def multiply(self, mask, color, alpha=1.0):
        m = (mask * alpha)[..., None]
        c = np.asarray(color, dtype=np.float32)
        self.rgb *= 1.0 + (c - 1.0) * m

    def screen(self, mask, color, alpha=1.0):
        m = (mask * alpha)[..., None]
        c = np.asarray(color, dtype=np.float32)
        scr = 1.0 - (1.0 - self.rgb) * (1.0 - c)
        self.rgb += (scr - self.rgb) * m

    def image(self, out_w=W, out_h=H):
        a = np.clip(self.rgb, 0, 1)
        # linear-ish downsample in gamma space is fine for painterly output
        im = Image.fromarray((a * 255.0 + 0.5).astype(np.uint8), 'RGB')
        return im.resize((out_w, out_h), Image.LANCZOS)


def shade_ramp(light, dark, mid, lite, gamma=1.0):
    """Map lighting value (0..1) to colour via a three-stop ramp (HxWx3)."""
    t = np.linspace(0, 1, 256, dtype=np.float32)
    if gamma != 1.0:
        t = t ** gamma
    t = t[:, None]
    dark, mid, lite = (np.asarray(c, np.float32) for c in (dark, mid, lite))
    lut = np.where(t < 0.5, dark + (mid - dark) * np.clip(t * 2, 0, 1),
                   mid + (lite - mid) * np.clip(t * 2 - 1, 0, 1)).astype(np.float32)
    idx = (np.clip(light, 0, 1) * 255.0 + 0.5).astype(np.int32)
    return lut[idx]
