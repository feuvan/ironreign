"""Shared helpers for the world-map / battle art generators (Iron Reign).

Owned by the world & battle artist. Other generators in Tools/ArtGen use their own helper modules;
everything here is prefixed/namespaced so it does not clash.

Only numpy, scipy and Pillow are required. Everything is deterministic (explicit seeds).
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "Content" / "Data"
ART_MAP = DATA / "Art" / "Map"
ART_BATTLE = DATA / "Art" / "Battle"
SCENARIO = DATA / "Scenarios" / "BrokenMandate.json"


# ----------------------------------------------------------------------------------------------
# colour
# ----------------------------------------------------------------------------------------------
def hexcol(s: str) -> np.ndarray:
    s = s.lstrip("#")
    return np.array([int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)


def rgb8(c) -> tuple:
    c = np.clip(np.asarray(c, dtype=np.float32), 0, 1)
    return tuple(int(round(v * 255)) for v in c[:3])


def rgba8(c, a=1.0) -> tuple:
    return rgb8(c) + (int(round(np.clip(a, 0, 1) * 255)),)


PAL = {
    "paper": hexcol("E9DCC0"),
    "paper_dark": hexcol("CDB990"),
    "ink": hexcol("2A2119"),
    "ink_soft": hexcol("5A4A3A"),
    "lacquer": hexcol("7E1F17"),
    "lacquer_dark": hexcol("4A120D"),
    "gold": hexcol("C9A24A"),
    "jade": hexcol("3F6E5A"),
    "indigo": hexcol("2E3F5C"),
    "night": hexcol("1B1712"),
}


def mix(a, b, t):
    """Linear interpolation; t may be an array (broadcast over the colour axis)."""
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    t = np.asarray(t, dtype=np.float32)
    if t.ndim and a.ndim == 1 and b.ndim == 1:
        t = t[..., None]
    elif t.ndim and t.ndim < max(a.ndim, b.ndim):
        t = t[..., None]
    return a + (b - a) * t


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, dtype=np.float32) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def clamp01(x):
    return np.clip(x, 0.0, 1.0)


# ----------------------------------------------------------------------------------------------
# noise
# ----------------------------------------------------------------------------------------------
def value_noise(h: int, w: int, cell: float, rng: np.random.Generator) -> np.ndarray:
    """Smooth (cubic spline) value noise, roughly unit variance, feature size ~cell pixels."""
    cell = max(float(cell), 1.0)
    gh = int(math.ceil(h / cell)) + 5
    gw = int(math.ceil(w / cell)) + 5
    g = rng.standard_normal((gh, gw)).astype(np.float32)
    z = ndimage.zoom(g, cell, order=3, mode="mirror", prefilter=False)
    oy = int(rng.integers(0, max(1, z.shape[0] - h)))
    ox = int(rng.integers(0, max(1, z.shape[1] - w)))
    z = z[oy:oy + h, ox:ox + w]
    if z.shape != (h, w):  # extremely small cells can round down; pad defensively
        z = np.pad(z, ((0, h - z.shape[0]), (0, w - z.shape[1])), mode="reflect")
    s = float(z.std()) or 1.0
    return ((z - z.mean()) / s).astype(np.float32)


def fbm(h, w, cell, octaves=5, persistence=0.5, lacunarity=2.0, seed=0, min_cell=1.5):
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, c, total = 1.0, float(cell), 0.0
    for _ in range(octaves):
        if c < min_cell:
            break
        out += amp * value_noise(h, w, c, rng)
        total += amp * amp
        amp *= persistence
        c /= lacunarity
    return out / math.sqrt(total)


def ridged(h, w, cell, octaves=5, persistence=0.55, seed=0):
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, c, total = 1.0, float(cell), 0.0
    for _ in range(octaves):
        if c < 1.5:
            break
        n = value_noise(h, w, c, rng)
        out += amp * (1.0 - np.abs(n) * 0.8)
        total += amp
        amp *= persistence
        c /= 2.0
    return out / total


# ----------------------------------------------------------------------------------------------
# rasterising / distance fields
# ----------------------------------------------------------------------------------------------
def poly_mask(w, h, polys, scale=1.0, offset=(0.0, 0.0)) -> np.ndarray:
    """Boolean mask of polygons (list of [[x,y],...]) on a w x h grid at the given scale."""
    im = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(im)
    ox, oy = offset
    for p in polys:
        pts = [((x + ox) * scale, (y + oy) * scale) for x, y in p]
        if len(pts) >= 3:
            d.polygon(pts, fill=255)
    return np.asarray(im) > 127


def signed_distance(mask: np.ndarray, px: float = 1.0) -> np.ndarray:
    """Signed distance (positive inside) in units where one grid pixel = px."""
    din = ndimage.distance_transform_edt(mask)
    dout = ndimage.distance_transform_edt(~mask)
    sd = np.where(mask, din - 0.5, -(dout - 0.5))
    return (sd * px).astype(np.float32)


def resample_polyline(pts, step):
    """Return points spaced ~step apart along a polyline (keeps the endpoints)."""
    pts = np.asarray(pts, dtype=np.float64)
    seg = np.diff(pts, axis=0)
    seglen = np.hypot(seg[:, 0], seg[:, 1])
    total = seglen.sum()
    n = max(2, int(math.ceil(total / step)) + 1)
    s = np.linspace(0, total, n)
    cum = np.concatenate([[0], np.cumsum(seglen)])
    x = np.interp(s, cum, pts[:, 0])
    y = np.interp(s, cum, pts[:, 1])
    return np.stack([x, y], axis=1), s / max(total, 1e-6)


def catmull_rom(pts, samples_per_seg=12, closed=False):
    """Smooth a polyline with a centripetal-ish Catmull-Rom spline."""
    P = np.asarray(pts, dtype=np.float64)
    if len(P) < 3:
        return P
    if closed:
        P = np.vstack([P[-1], P, P[0], P[1]])
    else:
        P = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        t = np.linspace(0, 1, samples_per_seg, endpoint=False)[:, None]
        t2, t3 = t * t, t * t * t
        c = 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                   (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
        out.append(c)
    out.append(P[-2][None, :])
    return np.vstack(out)


def bezier(p0, p1, p2, p3, n=24):
    t = np.linspace(0, 1, n)[:, None]
    p0, p1, p2, p3 = (np.asarray(p, dtype=np.float64) for p in (p0, p1, p2, p3))
    return ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3 * p3


def path(*segs, n=20):
    """Build a polyline from a list of segments.  Each seg is either a point (x,y) (line-to) or a
    tuple of 3 points (cubic bezier control1, control2, end) continuing from the previous point."""
    pts = []
    cur = None
    for s in segs:
        if len(s) == 2 and np.isscalar(s[0]):
            cur = np.asarray(s, dtype=np.float64)
            pts.append(cur[None, :])
        else:
            c1, c2, e = s
            b = bezier(cur, c1, c2, e, n)
            pts.append(b[1:])
            cur = np.asarray(e, dtype=np.float64)
    return np.vstack(pts)


def brush_polygon(points, widths):
    """Polygon outline of a variable-width stroke along `points` (N x 2) with per-point widths."""
    P = np.asarray(points, dtype=np.float64)
    W = np.broadcast_to(np.asarray(widths, dtype=np.float64), (len(P),))
    if len(P) < 2:
        return []
    d = np.gradient(P, axis=0)
    ln = np.hypot(d[:, 0], d[:, 1])
    ln[ln == 0] = 1
    nrm = np.stack([-d[:, 1] / ln, d[:, 0] / ln], axis=1)
    left = P + nrm * (W[:, None] / 2)
    right = P - nrm * (W[:, None] / 2)
    poly = np.vstack([left, right[::-1]])
    return [tuple(p) for p in poly]


# ----------------------------------------------------------------------------------------------
# supersampled RGBA canvas (premultiplied float) for sprites
# ----------------------------------------------------------------------------------------------
class Canvas:
    """Supersampled painting surface. Coordinates are in final (1x) pixels."""

    def __init__(self, w, h, ss=4):
        self.w, self.h, self.ss = w, h, ss
        self.W, self.H = w * ss, h * ss
        self.rgb = np.zeros((self.H, self.W, 3), np.float32)  # premultiplied
        self.a = np.zeros((self.H, self.W), np.float32)
        ys, xs = np.mgrid[0:self.H, 0:self.W].astype(np.float32)
        self.X = (xs + 0.5) / ss  # 1x coordinates of each subpixel
        self.Y = (ys + 0.5) / ss

    # -- masks -------------------------------------------------------------------------------
    def _img(self):
        im = Image.new("L", (self.W, self.H), 0)
        return im, ImageDraw.Draw(im)

    def poly(self, pts):
        im, d = self._img()
        s = self.ss
        d.polygon([(x * s, y * s) for x, y in pts], fill=255)
        return np.asarray(im, dtype=np.float32) / 255.0

    def ellipse(self, cx, cy, rx, ry=None):
        ry = rx if ry is None else ry
        im, d = self._img()
        s = self.ss
        d.ellipse([(cx - rx) * s, (cy - ry) * s, (cx + rx) * s, (cy + ry) * s], fill=255)
        return np.asarray(im, dtype=np.float32) / 255.0

    def line(self, pts, width, round_caps=True):
        im, d = self._img()
        s = self.ss
        P = [(x * s, y * s) for x, y in pts]
        d.line(P, fill=255, width=max(1, int(round(width * s))), joint="curve")
        if round_caps:
            r = width * s / 2
            for (x, y) in (P[0], P[-1]):
                d.ellipse([x - r, y - r, x + r, y + r], fill=255)
        return np.asarray(im, dtype=np.float32) / 255.0

    def stroke(self, pts, widths):
        return self.poly(brush_polygon(pts, widths))

    def rect(self, x0, y0, x1, y1):
        return self.poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])

    # -- painting ----------------------------------------------------------------------------
    def paint(self, mask, color, alpha=1.0):
        m = np.clip(mask * alpha, 0, 1).astype(np.float32)
        col = np.asarray(color, dtype=np.float32)
        if col.ndim == 1:
            col = col[None, None, :3]
        self.rgb *= (1 - m)[..., None]
        self.rgb += col[..., :3] * m[..., None]
        self.a = self.a * (1 - m) + m

    def shade(self, mask, factor_map, alpha=1.0):
        """Multiply existing colour inside mask by factor_map (array or scalar)."""
        m = np.clip(mask * alpha, 0, 1)
        f = 1 + (np.asarray(factor_map, dtype=np.float32) - 1) * m
        self.rgb *= f[..., None] if np.ndim(f) == 2 else f

    def outline(self, mask, width, color, alpha=1.0, inside=False):
        """Ink outline around a coverage mask (dilated ring)."""
        r = width * self.ss
        hard = mask > 0.5
        if inside:
            dist = ndimage.distance_transform_edt(hard)
            ring = clamp01(1 - (dist - r) / 1.5) * clamp01(mask)
        else:
            dist = ndimage.distance_transform_edt(~hard)
            ring = clamp01(1 - (dist - r) / 1.5) * (1 - clamp01(mask)) + 0 * mask
            ring = np.maximum(ring, 0)
        self.paint(ring, color, alpha)

    def lin_grad(self, c0, c1, x0, y0, x1, y1):
        """Linear gradient colour field from c0 at (x0,y0) to c1 at (x1,y1) (1x coords)."""
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy or 1.0
        t = clamp01(((self.X - x0) * dx + (self.Y - y0) * dy) / L2)
        return mix(c0, c1, t)

    def rad_grad(self, c0, c1, cx, cy, r):
        t = clamp01(np.hypot(self.X - cx, self.Y - cy) / r)
        return mix(c0, c1, t)

    def noise(self, cell, seed, octaves=3):
        return fbm(self.H, self.W, cell * self.ss, octaves=octaves, seed=seed)

    def composite_under(self, other: "Canvas"):
        """Put `other` beneath self."""
        self.rgb = self.rgb + other.rgb * (1 - self.a)[..., None]
        self.a = self.a + other.a * (1 - self.a)

    def composite_over(self, other: "Canvas"):
        self.rgb = other.rgb + self.rgb * (1 - other.a)[..., None]
        self.a = other.a + self.a * (1 - other.a)

    def image(self) -> Image.Image:
        s = self.ss
        rgb = self.rgb.reshape(self.h, s, self.w, s, 3).mean(axis=(1, 3))
        a = self.a.reshape(self.h, s, self.w, s).mean(axis=(1, 3))
        out = np.zeros((self.h, self.w, 4), np.float32)
        nz = a > 1e-5
        out[..., :3][nz] = rgb[nz] / a[nz][:, None]
        out[..., 3] = a
        return Image.fromarray((clamp01(out) * 255 + 0.5).astype(np.uint8), "RGBA")


def save_png(img: Image.Image, path: Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)
    return path


def report(path: Path):
    path = Path(path)
    im = Image.open(path)
    try:
        name = path.resolve().relative_to(ROOT)
    except ValueError:
        name = path
    print(f"  {name}  {im.size[0]}x{im.size[1]} {im.mode}  {os.path.getsize(path) / 1024:.0f} KB")
