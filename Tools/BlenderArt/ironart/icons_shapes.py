"""Icons family (gongbi): flat motif shapes drawn in 2D and extruded.

Some icon subjects are painted motifs rather than objects - auspicious clouds (祥云), flame
tongues (火焰纹), the tiger of a tally (虎符), a slash of wind.  Their outlines are easiest to
*draw*: a builder paints the silhouette with Pillow (unions of discs, spline polygons, strokes),
:func:`trace` turns the mask into smooth outlines (marching squares on the blurred mask, holes
assigned to their outer loop) and :func:`shape_mesh` extrudes them with
:func:`ironart.icons_kit.outline_mesh` so Freestyle inks them like any modelled part.

Pure numpy / Pillow except :func:`shape_mesh` (bpy).
"""

import math

import numpy as np

TAU = math.tau


# ---------------------------------------------------------------------------------------------
# marching squares
# ---------------------------------------------------------------------------------------------
def _blur(a, r):
    from .icons_gongbi import blur
    return blur(np.asarray(a, np.float32), r, pad_zero=True)


def contours(field, level=0.5):
    """Closed iso-lines of ``field`` (H x W float) at ``level`` as lists of (x, y) pixel
    coordinates (x right, y down).  The field is padded with 0, so every loop closes.  Loops
    run with the inside on the left in image space (outer loops counter-clockwise on screen)."""
    f = np.pad(np.asarray(field, np.float32), 1, constant_values=0.0)
    H, W = f.shape
    b = (f > level).astype(np.uint8)
    case = (b[:-1, :-1] * 1 + b[:-1, 1:] * 2 + b[1:, 1:] * 4 + b[1:, :-1] * 8)
    ii, jj = np.nonzero((case > 0) & (case < 15))

    def pt(edge):
        kind, i, j = edge
        if kind == "h":                       # between (i, j) and (i, j + 1)
            a, c = f[i, j], f[i, j + 1]
            t = (level - a) / (c - a) if c != a else 0.5
            return (j + t - 1.0, i - 1.0)
        a, c = f[i, j], f[i + 1, j]           # between (i, j) and (i + 1, j)
        t = (level - a) / (c - a) if c != a else 0.5
        return (j - 1.0, i + t - 1.0)

    # edges of cell (i, j): T = h(i, j), R = v(i, j + 1), B = h(i + 1, j), L = v(i, j)
    # segment table: direction keeps the inside (value > level) on the left (image coords)
    table = {
        1: [("L", "T")], 2: [("T", "R")], 3: [("L", "R")], 4: [("R", "B")],
        6: [("T", "B")], 7: [("L", "B")], 8: [("B", "L")], 9: [("B", "T")],
        11: [("B", "R")], 12: [("R", "L")], 13: [("R", "T")], 14: [("T", "L")],
    }
    nxt = {}
    for i, j in zip(ii.tolist(), jj.tolist()):
        c = int(case[i, j])
        E = {"T": ("h", i, j), "R": ("v", i, j + 1), "B": ("h", i + 1, j), "L": ("v", i, j)}
        if c in (5, 10):
            centre = (f[i, j] + f[i, j + 1] + f[i + 1, j] + f[i + 1, j + 1]) / 4.0
            if c == 5:
                segs = [("L", "B"), ("R", "T")] if centre > level else [("L", "T"), ("R", "B")]
            else:
                segs = [("T", "L"), ("B", "R")] if centre > level else [("T", "R"), ("B", "L")]
        else:
            segs = table[c]
        for s, e in segs:
            nxt[E[s]] = E[e]
    loops = []
    seen = set()
    for start in list(nxt):
        if start in seen:
            continue
        loop = []
        e = start
        while e not in seen and e in nxt:
            seen.add(e)
            loop.append(pt(e))
            e = nxt[e]
        if len(loop) >= 6:
            loops.append(loop)
    return loops


def area(loop):
    a = 0.0
    for (x0, y0), (x1, y1) in zip(loop, loop[1:] + loop[:1]):
        a += x0 * y1 - x1 * y0
    return a / 2.0


def resample(loop, step):
    """Even spacing (``step`` px) along a closed loop."""
    p = np.asarray(loop + loop[:1], np.float64)
    seg = np.sqrt(((p[1:] - p[:-1]) ** 2).sum(1))
    s = np.concatenate([[0.0], np.cumsum(seg)])
    n = max(8, int(s[-1] / step))
    t = np.linspace(0.0, s[-1], n, endpoint=False)
    x = np.interp(t, s, p[:, 0])
    y = np.interp(t, s, p[:, 1])
    return list(zip(x.tolist(), y.tolist()))


def smooth(loop, k=2, it=2):
    p = np.asarray(loop, np.float64)
    for _ in range(it):
        q = np.zeros_like(p)
        for d in range(-k, k + 1):
            q += np.roll(p, d, axis=0)
        p = q / (2 * k + 1)
    return [tuple(v) for v in p.tolist()]


def _inside(pt, loop):
    x, y = pt
    c = False
    n = len(loop)
    for i in range(n):
        x0, y0 = loop[i]
        x1, y1 = loop[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0 + 1e-12) + x0:
            c = not c
    return c


def trace(mask, blur_px=1.2, step=2.0, smooth_k=1, min_area=30.0):
    """Mask (H x W, 0..1) -> [(outer, [holes...]), ...] in pixel coordinates (x right, y down),
    smoothed and evenly resampled."""
    fld = _blur(mask, blur_px) if blur_px else mask
    loops = [smooth(resample(lp, step), smooth_k, 2) for lp in contours(fld)]
    outers, holes = [], []
    for lp in loops:
        a = area(lp)
        if abs(a) < min_area:
            continue
        # inside-on-the-left in y-down coordinates -> outer loops have negative shoelace area
        (outers if a < 0 else holes).append(lp)
    res = [(o, []) for o in outers]
    for h in holes:
        for o, hs in res:
            if _inside(h[0], o):
                hs.append(h)
                break
    return res


# ---------------------------------------------------------------------------------------------
# drawing helpers (Pillow, pixel space)
# ---------------------------------------------------------------------------------------------
class Canvas:
    """A square drawing surface mapped onto the box (x0, z0, x1, z1) of the motif plane."""

    def __init__(self, box, res=768):
        from PIL import Image, ImageDraw
        self.box = box
        x0, z0, x1, z1 = box
        self.W = res
        self.H = max(8, int(round(res * (z1 - z0) / (x1 - x0))))
        self.im = Image.new("L", (self.W, self.H), 0)
        self.d = ImageDraw.Draw(self.im)

    def px(self, x, z):
        x0, z0, x1, z1 = self.box
        return ((x - x0) / (x1 - x0) * self.W, (z1 - z) / (z1 - z0) * self.H)

    def unit(self, r):
        x0, _, x1, _ = self.box
        return r / (x1 - x0) * self.W

    def disc(self, x, z, r, fill=255):
        cx, cy = self.px(x, z)
        rr = self.unit(r)
        self.d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=fill)

    def poly(self, pts, fill=255):
        self.d.polygon([self.px(x, z) for x, z in pts], fill=fill)

    def stroke(self, pts, width, fill=255):
        """A round-capped stroke of constant ``width`` (world units) through ``pts``."""
        w = self.unit(width)
        p = [self.px(x, z) for x, z in pts]
        self.d.line(p, fill=fill, width=max(1, int(round(w))), joint="curve")
        for (cx, cy) in (p[0], p[-1]):
            self.d.ellipse([cx - w / 2, cy - w / 2, cx + w / 2, cy + w / 2], fill=fill)

    def brush(self, pts, widths, fill=255):
        """A stroke whose width varies along the points (discs + quads)."""
        q = [self.px(x, z) for x, z in pts]
        ws = [self.unit(w) / 2.0 for w in widths]
        for (cx, cy), r in zip(q, ws):
            self.d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)
        for (ax, ay), (bx, by), ra, rb in zip(q[:-1], q[1:], ws[:-1], ws[1:]):
            dx, dy = bx - ax, by - ay
            L = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / L, dx / L
            self.d.polygon([(ax + nx * ra, ay + ny * ra), (bx + nx * rb, by + ny * rb),
                            (bx - nx * rb, by - ny * rb), (ax - nx * ra, ay - ny * ra)], fill=fill)

    def mask(self):
        return np.asarray(self.im, np.float32) / 255.0

    def to_world(self, loop):
        x0, z0, x1, z1 = self.box
        return [(x0 + x / self.W * (x1 - x0), z1 - y / self.H * (z1 - z0)) for x, y in loop]


def spiral_band(cx, cz, r0, r1, turns, w0, w1, start=0.0, n=80, cw=False):
    """A ruyi-curl band: centre line spiralling out from (cx, cz); returns (points, widths)."""
    pts, ws = [], []
    for k in range(n + 1):
        t = k / n
        a = start + (-1 if cw else 1) * TAU * turns * t
        r = r0 + (r1 - r0) * t
        pts.append((cx + r * math.cos(a), cz + r * math.sin(a)))
        ws.append(w0 + (w1 - w0) * t)
    return pts, ws


# ---------------------------------------------------------------------------------------------
# Blender: extrude the traced shape
# ---------------------------------------------------------------------------------------------
def shape_mesh(name, canvas, depth, mat, bevel_w=0.012, segments=2, plane="XZ", blur_px=1.2,
               step=2.0):
    """Trace ``canvas`` and extrude every island (with its holes) -> list of mesh objects."""
    from . import icons_kit as K
    out = []
    for k, (outer, holes) in enumerate(trace(canvas.mask(), blur_px, step)):
        o = canvas.to_world(outer)                             # CCW in the motif plane
        hs = [canvas.to_world(h) for h in holes]
        out.append(K.outline_mesh("%s%d" % (name, k), o, depth, mat, bevel_w=bevel_w,
                                  segments=segments, plane=plane, holes=hs))
    return out


def brush_arrow(cv, path, w0, w1, head_len, head_w, n=60):
    """A calligraphic arrow along ``path`` (callable t -> (x, z), t 0..1): a stroke that starts
    thin (the brush touching down), swells towards the head and ends in a barbed arrowhead whose
    point is path(1).  Widths in world units."""
    pts, ws = [], []
    # the shaft stops where the head begins
    L = 0.0
    prev = path(0.0)
    lens = [0.0]
    for k in range(1, n + 1):
        p = path(k / n)
        L += math.hypot(p[0] - prev[0], p[1] - prev[1])
        lens.append(L)
        prev = p
    t_head = 1.0
    for k in range(n + 1):
        if L - lens[k] < head_len * 0.75:
            t_head = k / n
            break
    for k in range(n + 1):
        t = k / n
        if t > t_head:
            break
        pts.append(path(t))
        u = t / max(t_head, 1e-6)
        ws.append(w0 + (w1 - w0) * u ** 0.8)
    cv.brush(pts, ws)
    tip = path(1.0)
    base = path(t_head)
    dx, dz = tip[0] - base[0], tip[1] - base[1]
    ln = math.hypot(dx, dz) or 1.0
    dx, dz = dx / ln, dz / ln
    nx, nz = -dz, dx
    back = (tip[0] - dx * head_len, tip[1] - dz * head_len)
    notch = (tip[0] - dx * head_len * 0.72, tip[1] - dz * head_len * 0.72)
    cv.poly([tip, (back[0] + nx * head_w, back[1] + nz * head_w), notch,
             (back[0] - nx * head_w, back[1] - nz * head_w)])
