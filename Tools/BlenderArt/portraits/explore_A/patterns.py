"""Textile motif tiles drawn with Pillow (cloud scrolls, roundels, key-fret borders, lattices,
lamellar plates) -> bpy images.  Grayscale masks: 1 = thread / raised, 0 = ground."""

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def _to_arr(im, blur=0.8):
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    return np.asarray(im, np.float32) / 255.0


def clouds(size=512, seed=0):
    """Auspicious cloud scrolls (xiangyun) on a staggered grid."""
    rng = np.random.default_rng(seed)
    im = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(im)
    w = max(3, size // 90)
    cells = [(0.25, 0.25), (0.75, 0.75)]
    for cx, cy in cells:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                ox, oy = (cx + dx) * size, (cy + dy) * size
                s = size * 0.2
                # three-lobed cloud head: spirals
                for k, (lx, ly, rr, sgn) in enumerate(((-0.55, 0.0, 0.42, 1), (0.0, -0.35, 0.5, -1), (0.55, 0.0, 0.42, 1))):
                    pts = []
                    for t in np.linspace(0, 2.6 * math.pi, 60):
                        r = rr * s * (1 - t / (3.2 * math.pi))
                        pts.append((ox + lx * s + sgn * r * math.cos(t), oy + ly * s + r * math.sin(t)))
                    d.line(pts, fill=255, width=w, joint="curve")
                # trailing tail
                tail = [(ox + s * 0.55 + s * t * 1.2, oy + s * 0.3 + s * 0.25 * math.sin(t * 3.0)) for t in np.linspace(0, 1, 20)]
                d.line(tail, fill=255, width=w, joint="curve")
    return _to_arr(im)


def roundels(size=512, seed=0, petals=8):
    """Tuanhua medallions: concentric rings with petals and a centre boss."""
    im = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(im)
    w = max(2, size // 120)
    for cx, cy in ((0.5, 0.5), (0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)):
        ox, oy = cx * size, cy * size
        R = size * 0.3
        d.ellipse((ox - R, oy - R, ox + R, oy + R), outline=255, width=w)
        d.ellipse((ox - R * 0.82, oy - R * 0.82, ox + R * 0.82, oy + R * 0.82), outline=255, width=w)
        for k in range(petals):
            a = 2 * math.pi * k / petals
            px, py = ox + math.cos(a) * R * 0.5, oy + math.sin(a) * R * 0.5
            rr = R * 0.24
            d.ellipse((px - rr, py - rr, px + rr, py + rr), outline=255, width=w)
        rr = R * 0.18
        d.ellipse((ox - rr, oy - rr, ox + rr, oy + rr), fill=255)
    # small scattered dots between
    for cx, cy in ((0.5, 0.0), (0.0, 0.5), (1.0, 0.5), (0.5, 1.0)):
        ox, oy = cx * size, cy * size
        rr = size * 0.025
        d.ellipse((ox - rr, oy - rr, ox + rr, oy + rr), fill=255)
    return _to_arr(im)


def fret(size=256, rows=1):
    """Key-fret (huiwen) border running along u; the tile is square, repeat along u."""
    im = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(im)
    w = max(3, size // 28)
    m = size * 0.12
    s = size - 2 * m
    # border lines
    d.line([(0, m * 0.5), (size, m * 0.5)], fill=255, width=w)
    d.line([(0, size - m * 0.5), (size, size - m * 0.5)], fill=255, width=w)
    # meander
    x0, y0 = m * 0.5, m
    pts = [(x0, y0 + s), (x0, y0), (x0 + s * 0.8, y0), (x0 + s * 0.8, y0 + s * 0.6), (x0 + s * 0.3, y0 + s * 0.6),
           (x0 + s * 0.3, y0 + s * 0.3), (x0 + s * 0.55, y0 + s * 0.3)]
    d.line(pts, fill=255, width=w, joint="curve")
    d.line([(x0 + s * 0.8 + w, y0 + s), (size, y0 + s)], fill=255, width=w)
    return _to_arr(im, 0.6)


def lattice(size=256):
    im = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(im)
    w = max(2, size // 64)
    for k in (-1, 0, 1):
        d.line([(k * size, 0), (k * size + size, size)], fill=255, width=w)
        d.line([(k * size + size, 0), (k * size, size)], fill=255, width=w)
    rr = size * 0.06
    for cx, cy in ((0.5, 0.0), (0.0, 0.5), (1.0, 0.5), (0.5, 1.0)):
        d.ellipse((cx * size - rr, cy * size - rr, cx * size + rr, cy * size + rr), fill=255)
    return _to_arr(im)


def plates(size=512, cols=4, rows=4, seed=0):
    """Lamellar plate field: (height, holes, lacing) masks as RGB channels.
    R: plate relief (rounded rectangles with bevelled edges), G: lacing cords, B: rivets/holes."""
    rng = np.random.default_rng(seed)
    H = np.zeros((size, size), np.float32)
    lace = Image.new("L", (size, size), 0)
    holes = Image.new("L", (size, size), 0)
    dl = ImageDraw.Draw(lace)
    dh = ImageDraw.Draw(holes)
    pw, ph = size / cols, size / rows
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    for r in range(rows):
        off = (r % 2) * pw * 0.5
        for c in range(-1, cols + 1):
            x0 = c * pw + off
            y0 = r * ph
            cx, cy = x0 + pw / 2, y0 + ph / 2
            hx, hy = pw * 0.46, ph * 0.52
            # rounded-top plate: superellipse distance
            dx = np.abs(xx - cx) / hx
            dy = np.abs(yy - cy) / hy
            dd = (dx ** 4 + dy ** 4) ** 0.25
            prof = np.clip((1.0 - dd) * 6.0, 0, 1)
            # plates overlap: later rows over earlier (lower rows sit on top)
            H = np.maximum(H * (1 - (prof > 0.01)) + prof * (0.75 + 0.25 * rng.random()) * (prof > 0.01), H * (prof <= 0.01))
            # lacing holes and the cord running across each row at 25% and 70% height
            for fy in (0.22, 0.72):
                yh = y0 + ph * fy
                for fx in (0.3, 0.7):
                    xh = x0 + pw * fx
                    rr = size * 0.008
                    dh.ellipse((xh - rr, yh - rr, xh + rr, yh + rr), fill=255)
        for fy in (0.22, 0.72):
            yh = r * ph + ph * fy
            dl.line([(0, yh), (size, yh)], fill=255, width=max(2, int(size * 0.012)))
    L = _to_arr(lace, 1.0)
    Hl = _to_arr(holes, 0.6)
    return np.dstack([H, L, Hl])


def to_image(name, arr, colorspace="Non-Color"):
    import bpy
    if arr.ndim == 2:
        arr = np.dstack([arr, arr, arr])
    h, w = arr.shape[:2]
    rgba = np.dstack([arr[..., :3], np.ones((h, w), np.float32)])
    img = bpy.data.images.new(name, w, h, alpha=False, float_buffer=False)
    img.colorspace_settings.name = colorspace
    img.pixels.foreach_set(np.ascontiguousarray(rgba[::-1]).ravel().astype(np.float32))
    img.update()
    img.pack()
    return img
