"""Battle family: numpy gongbi painter for the hex-tile ground textures (no bpy).

The battle board's hex tiles are miniature terrain pieces whose **top surface is a heightfield**
``z = h(x, y)`` over the flat-top hexagon (circumradius :data:`R` = 4 m, corners on +-x, Blender
frame).  Their ground texture is planar (u = (x + 4) / 8, v = (y + 4) / 8), so the texture is a
top-down painting of the tile: every texel knows its 3D point (x, y, h(x, y)) and normal
analytically, and the paint is laid like a gongbi painter lays it - flat mineral washes,
soft 晕染 gradients, then ink and colour marks (grass strokes, moss dots, wave lines, ruts).

Seamless joins (DESIGN.md 12.3; the board rotates natural tiles by random multiples of 60 deg):

* every terrain has a **rim**: within ``RIM`` metres of the hexagon boundary its paint is a
  function of the distance to the boundary only (identical on all six edges and mirror
  symmetric about each edge), so two tiles of the same terrain meet without a seam in any
  rotation; terrains of the meadow family (plain, forest, hill, mountain, road...) share one
  rim colour so they also meet softly
* marks near the rim (grass strokes, dots) are scattered in the 1/12 fundamental wedge and
  replicated with the hexagon's 12 symmetries (:func:`sym12`), and never cross the boundary.

Colours are sRGB floats in 0..1 (painted like pigments, composited in sRGB).
"""

import math

import numpy as np

SQ3 = math.sqrt(3.0)
#: hex circumradius (m), apothem
R = 4.0
APO = R * SQ3 / 2.0
#: edge normals of the flat-top hexagon (angles 30, 90, ... deg)
EDGE_ANG = np.radians(np.arange(6) * 60.0 + 30.0)


# ---------------------------------------------------------------------------------------------
# colours
# ---------------------------------------------------------------------------------------------
def c(hexstr):
    h = hexstr.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


#: the gongbi palette of the battle board (sRGB)
P = {k: c(v) for k, v in {
    "ink": "#1E1A16", "ink_green": "#24382E", "ink_blue": "#1F3550", "ink_umber": "#4A3324",
    "silk": "#E6D6B0", "silk_d": "#D8C39A",
    "malachite": "#3E8E6E", "mal_light": "#8CBFA0", "mal_deep": "#2C6E56",
    "azurite": "#2B5C8A", "azu_light": "#7FA6C8", "azu_deep": "#23496F",
    "cinnabar": "#B5382A", "vermilion": "#D0643C", "ochre": "#A0643A", "gold": "#C9A24B",
    "white": "#F0E8D8",
    # meadow family (pale silk-green washes, after the world terrain's plain_green #B9C29E)
    "meadow": "#BCC49A", "meadow_l": "#CBCCA6", "meadow_d": "#A8B78D", "meadow_blue": "#AABCA2",
    "meadow_silk": "#D3CBA4", "grass_mark": "#5E8462", "grass_mark_d": "#3F6650",
    "earth": "#C9B48A", "earth_d": "#AE9670", "earth_l": "#D8C8A0", "rut": "#8C7656",
    "forest_floor": "#A4B38A", "forest_floor_d": "#8FA47E", "leaf_litter": "#B39A6A",
    "foot_ochre": "#C8A57A", "hill_green": "#A6BC8A",
    "water": "#93B1C6", "water_d": "#7A9CB8", "water_l": "#AAC2D0", "wave": "#33577C",
    "bank": "#B49A72", "bank_d": "#8E7656", "bank_ink": "#5A4632",
    "pave": "#CFC6B0", "pave_line": "#8C8474",
}.items()}


def mix(a, b, t):
    t = np.asarray(t, np.float32)
    if t.ndim and t.shape[-1] not in (1, 3):
        t = t[..., None]
    return a * (1.0 - t) + b * t


def smooth(e0, e1, x):
    t = np.clip((np.asarray(x, np.float32) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


# ---------------------------------------------------------------------------------------------
# noise (vectorised, any points)
# ---------------------------------------------------------------------------------------------
def _hash(ix, iy, iz, seed):
    h = (ix.astype(np.int64) * 73856093) ^ (iy.astype(np.int64) * 19349663) ^ \
        (iz.astype(np.int64) * 83492791) ^ np.int64((seed * 2654435761) & 0x7FFFFFFF)
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float32) / float(0xFFFFFF)


def vnoise(x, y, z=None, seed=0):
    """Value noise in [0, 1] at arbitrary points (2D, or 3D when ``z`` is given)."""
    x = np.asarray(x, np.float32)
    y = np.asarray(y, np.float32)
    xi = np.floor(x)
    yi = np.floor(y)
    fx = x - xi
    fy = y - yi
    ux = fx * fx * (3 - 2 * fx)
    uy = fy * fy * (3 - 2 * fy)
    xi = xi.astype(np.int64)
    yi = yi.astype(np.int64)
    if z is None:
        zi = np.zeros_like(xi)
        h00 = _hash(xi, yi, zi, seed)
        h10 = _hash(xi + 1, yi, zi, seed)
        h01 = _hash(xi, yi + 1, zi, seed)
        h11 = _hash(xi + 1, yi + 1, zi, seed)
        return (h00 * (1 - ux) + h10 * ux) * (1 - uy) + (h01 * (1 - ux) + h11 * ux) * uy
    z = np.asarray(z, np.float32)
    zf = np.floor(z)
    fz = z - zf
    uz = fz * fz * (3 - 2 * fz)
    zi = zf.astype(np.int64)
    out = 0.0
    for dz, wz in ((0, 1 - uz), (1, uz)):
        h00 = _hash(xi, yi, zi + dz, seed)
        h10 = _hash(xi + 1, yi, zi + dz, seed)
        h01 = _hash(xi, yi + 1, zi + dz, seed)
        h11 = _hash(xi + 1, yi + 1, zi + dz, seed)
        out = out + ((h00 * (1 - ux) + h10 * ux) * (1 - uy) + (h01 * (1 - ux) + h11 * ux) * uy) * wz
    return out


def fbm(x, y, z=None, scale=1.0, octaves=4, gain=0.5, lac=2.03, seed=0):
    """Fractal value noise, normalised to about [0, 1] (mean 0.5)."""
    x = np.asarray(x, np.float32) * scale
    y = np.asarray(y, np.float32) * scale
    zz = None if z is None else np.asarray(z, np.float32) * scale
    tot = 0.0
    amp = 1.0
    norm = 0.0
    for o in range(octaves):
        # rotate each octave a little (no axis-aligned artefacts)
        a = 0.5 + o * 1.1
        ca, sa = math.cos(a), math.sin(a)
        xr = x * ca - y * sa + o * 17.3
        yr = x * sa + y * ca - o * 9.1
        tot = tot + amp * vnoise(xr, yr, None if zz is None else zz + o * 5.7, seed + o * 101)
        norm += amp
        amp *= gain
        x = x * lac
        y = y * lac
        if zz is not None:
            zz = zz * lac
    return tot / norm


def ridged(x, y, scale=1.0, octaves=4, seed=0):
    """Ridged fbm in [0, 1] (sharp crests at 1)."""
    x = np.asarray(x, np.float32) * scale
    y = np.asarray(y, np.float32) * scale
    tot = 0.0
    amp = 1.0
    norm = 0.0
    w = 1.0
    for o in range(octaves):
        a = 0.3 + o * 0.9
        ca, sa = math.cos(a), math.sin(a)
        n = vnoise(x * ca - y * sa + o * 31.7, x * sa + y * ca - o * 7.3, None, seed + o * 57)
        r = 1.0 - np.abs(2.0 * n - 1.0)
        r = r * r * w
        w = np.clip(r * 1.6, 0.0, 1.0)
        tot = tot + amp * r
        norm += amp
        amp *= 0.5
        x = x * 2.1
        y = y * 2.1
    return tot / norm


# ---------------------------------------------------------------------------------------------
# hexagon frame
# ---------------------------------------------------------------------------------------------
def hex_d(x, y):
    """Distance (m) from (x, y) to the hexagon boundary, positive inside."""
    x = np.asarray(x, np.float32)
    y = np.asarray(y, np.float32)
    t = np.max(np.stack([x * math.cos(a) + y * math.sin(a) for a in EDGE_ANG]), axis=0)
    return APO - t


def edge_frame(x, y):
    """(d, s, k): distance inside from the nearest edge, signed position along it from its
    midpoint, edge index 0..5."""
    x = np.asarray(x, np.float32)
    y = np.asarray(y, np.float32)
    proj = np.stack([x * math.cos(a) + y * math.sin(a) for a in EDGE_ANG])
    k = np.argmax(proj, axis=0)
    t = np.take_along_axis(proj, k[None], 0)[0]
    ang = EDGE_ANG[k]
    s = -x * np.sin(ang) + y * np.cos(ang)
    return APO - t, s, k


def sym12(pts):
    """Replicate points (N, 2) given in the fundamental wedge with the 12 symmetries of the
    hexagon (6 rotations x mirror).  Returns (12N, 2) and the symmetry index per point."""
    pts = np.asarray(pts, np.float32)
    out = []
    idx = []
    for m in (1.0, -1.0):
        q = pts * np.array([1.0, m], np.float32)
        for k in range(6):
            a = math.radians(60.0 * k)
            ca, sa = math.cos(a), math.sin(a)
            out.append(np.stack([q[:, 0] * ca - q[:, 1] * sa, q[:, 0] * sa + q[:, 1] * ca], -1))
            idx.append(np.full(len(q), k + (0 if m > 0 else 6)))
    return np.concatenate(out), np.concatenate(idx)


def sym12_dirs(dirs, sym):
    """Transform direction angles (rad) with the symmetry indices from :func:`sym12`."""
    dirs = np.asarray(dirs, np.float32)
    n = len(sym) // 12
    d = np.tile(dirs, 12)
    mirror = sym >= 6
    d = np.where(mirror, -d, d)
    return d + np.radians(60.0 * (sym % 6))


def wedge_points(rng, n, d_min, d_max):
    """``n`` random points in the 1/12 wedge (between the edge-midpoint direction at 30 deg and
    the corner direction at 0 deg) whose distance to the boundary is in [d_min, d_max]."""
    out = []
    while len(out) < n:
        a = math.radians(rng.uniform(0.0, 30.0))
        r = rng.uniform(1.5, R)
        x, y = r * math.cos(a), r * math.sin(a)
        d = float(hex_d(np.float32(x), np.float32(y)))
        if d_min <= d <= d_max:
            out.append((x, y))
    return np.array(out, np.float32)


# ---------------------------------------------------------------------------------------------
# canvas: the planar ground texture (top region) as a top-down painting
# ---------------------------------------------------------------------------------------------
class Canvas:
    """RGB + height painting on the tile's planar texture: pixel (i, j) of the ``size`` x ``size``
    texture is the point x = -4 + 8 (j + 0.5) / size, y = 4 - 8 (i + 0.5) / size (image rows
    top-down; Blender v = 1 - row)."""

    def __init__(self, size=2048, ext=4.0):
        self.size = size
        self.ext = ext
        self.ppm = size / (2.0 * ext)
        g = (np.arange(size, dtype=np.float32) + 0.5) / self.ppm - ext
        self.X, self.Y = np.meshgrid(g, -g)
        self.rgb = np.zeros((size, size, 3), np.float32)
        self.h = np.zeros((size, size), np.float32)

    # -- coordinates
    def to_px(self, x, y):
        return (np.asarray(x) + self.ext) * self.ppm - 0.5, (self.ext - np.asarray(y)) * self.ppm - 0.5

    # -- layers
    def wash(self, color, alpha=1.0):
        a = np.asarray(alpha, np.float32)
        if a.ndim == 2:
            a = a[..., None]
        self.rgb = self.rgb * (1 - a) + np.asarray(color, np.float32) * a

    def glaze(self, color, alpha):
        """Transparent wash: multiplies by the colour (晕染 / ink glazes)."""
        a = np.asarray(alpha, np.float32)
        if a.ndim == 2:
            a = a[..., None]
        col = np.asarray(color, np.float32)
        self.rgb = self.rgb * (1 - a + a * col)

    def strokes(self, strokes, mode="over"):
        """Rasterise tapered brush strokes.  Each stroke is a dict: ``pts`` (N, 2) metres,
        ``w`` width at the belly (m), ``color`` (3,), ``alpha``, optional ``taper`` (head, tail
        fractions), ``dry`` (0..1 dry-brush streaking), ``h`` (bump height added), ``seed``."""
        for st in strokes:
            self._stroke(st, mode)

    def _stroke(self, st, mode):
        pts = np.asarray(st["pts"], np.float32)
        w = float(st["w"])
        col = np.asarray(st["color"], np.float32)
        alpha = float(st.get("alpha", 1.0))
        head, tail = st.get("taper", (0.25, 0.45))
        dry = float(st.get("dry", 0.0))
        hh = float(st.get("h", 0.0))
        seed = int(st.get("seed", 0))
        px, py = self.to_px(pts[:, 0], pts[:, 1])
        pad = w * self.ppm * 0.5 + 2
        x0 = int(max(0, math.floor(px.min() - pad)))
        x1 = int(min(self.size - 1, math.ceil(px.max() + pad)))
        y0 = int(max(0, math.floor(py.min() - pad)))
        y1 = int(min(self.size - 1, math.ceil(py.max() + pad)))
        if x1 < x0 or y1 < y0:
            return
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1, dtype=np.float32), np.arange(y0, y1 + 1, dtype=np.float32))
        # cumulative length for the along-stroke parameter
        seg = np.hypot(np.diff(px), np.diff(py))
        cum = np.concatenate([[0.0], np.cumsum(seg)])
        L = max(cum[-1], 1e-3)
        best = np.full(gx.shape, 1e9, np.float32)
        bt = np.zeros(gx.shape, np.float32)
        for i in range(len(px) - 1):
            ax, ay, bx, by = px[i], py[i], px[i + 1], py[i + 1]
            dx, dy = bx - ax, by - ay
            ll = dx * dx + dy * dy + 1e-9
            t = np.clip(((gx - ax) * dx + (gy - ay) * dy) / ll, 0, 1)
            qx, qy = ax + t * dx, ay + t * dy
            dist = np.hypot(gx - qx, gy - qy)
            sel = dist < best
            best = np.where(sel, dist, best)
            bt = np.where(sel, (cum[i] + t * seg[i]) / L, bt)
        # width profile: tapered head and tail, a belly in between
        prof = np.minimum(smooth(0.0, head, bt) if head > 0 else 1.0, smooth(1.0, 1.0 - tail, bt) if tail > 0 else 1.0)
        prof = 0.25 + 0.75 * prof
        half = 0.5 * w * self.ppm * prof
        cov = np.clip(half + 0.6 - best, 0.0, 1.0) * np.clip((half + 0.6) / 1.2, 0.0, 1.0)
        if dry > 0:
            # streaks along the stroke: noise across it, varying a little along it
            across = (best / np.maximum(half, 0.5))
            n = vnoise(across * 4.0 + bt * 0.7, bt * 3.0, None, seed)
            cov = cov * (1.0 - dry * smooth(0.45, 0.8, n) * smooth(0.15, 0.5, bt))
        a = cov * alpha
        if a.max() <= 0:
            return
        sl = (slice(y0, y1 + 1), slice(x0, x1 + 1))
        if mode == "over":
            self.rgb[sl] = self.rgb[sl] * (1 - a[..., None]) + col * a[..., None]
        else:  # glaze
            self.rgb[sl] = self.rgb[sl] * (1 - a[..., None] + a[..., None] * col)
        if hh:
            self.h[sl] = self.h[sl] + hh * cov

    def dots(self, xy, radius, color, alpha=1.0, h=0.0, squash=1.0, angle=0.0):
        """Ink dots (苔点 / 点叶): soft-edged ellipses of ``radius`` (m, scalar or per dot)."""
        xy = np.asarray(xy, np.float32)
        rad = np.broadcast_to(np.asarray(radius, np.float32), (len(xy),))
        ang = np.broadcast_to(np.asarray(angle, np.float32), (len(xy),))
        col = np.asarray(color, np.float32)
        al = np.broadcast_to(np.asarray(alpha, np.float32), (len(xy),))
        for (x, y), r, an, aa in zip(xy, rad, ang, al):
            px, py = self.to_px(x, y)
            rp = r * self.ppm
            x0, x1 = int(max(0, px - rp - 2)), int(min(self.size - 1, px + rp + 2))
            y0, y1 = int(max(0, py - rp - 2)), int(min(self.size - 1, py + rp + 2))
            if x1 < x0 or y1 < y0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1, dtype=np.float32) - px,
                                 np.arange(y0, y1 + 1, dtype=np.float32) - py)
            ca, sa = math.cos(an), math.sin(an)
            u = gx * ca + gy * sa
            v = (-gx * sa + gy * ca) / max(squash, 1e-3)
            dist = np.hypot(u, v)
            cov = np.clip(rp + 0.6 - dist, 0, 1)
            a = cov * aa
            sl = (slice(y0, y1 + 1), slice(x0, x1 + 1))
            self.rgb[sl] = self.rgb[sl] * (1 - a[..., None]) + col * a[..., None]
            if h:
                self.h[sl] = self.h[sl] + h * cov


# ---------------------------------------------------------------------------------------------
# brush marks
# ---------------------------------------------------------------------------------------------
def grass_marks(rng, centers, length=(0.07, 0.13), width=0.016, color=None, alpha=0.75, lean=None, h=0.004,
                blades=(2, 4), dirs=None):
    """Short tapered grass strokes (2-4 blades from a point, splayed upward-ish): the painter's
    shorthand for a meadow.  ``dirs``: per-centre base direction (rad) or None (random)."""
    col = P["grass_mark"] if color is None else color
    out = []
    for i, (x, y) in enumerate(centers):
        base = dirs[i] if dirs is not None else rng.uniform(0, math.tau)
        nb = rng.randint(*blades)
        for b in range(nb):
            a = base + (b - (nb - 1) / 2.0) * rng.uniform(0.25, 0.45)
            L = rng.uniform(*length)
            bend = rng.uniform(-0.35, 0.35)
            p0 = np.array([x, y])
            p1 = p0 + 0.5 * L * np.array([math.cos(a), math.sin(a)])
            p2 = p0 + L * np.array([math.cos(a + bend), math.sin(a + bend)])
            out.append(dict(pts=np.array([p0, p1, p2]), w=width * rng.uniform(0.8, 1.2),
                            color=col * rng.uniform(0.9, 1.08), alpha=alpha * rng.uniform(0.7, 1.0),
                            taper=(0.1, 0.7), h=h, seed=rng.randint(0, 99999)))
    return out


def grass_clumps(rng, centers, n=(3, 6), length=(0.05, 0.11), width=0.013, color=None, alpha=0.6, h=0.004,
                 dirs=None, spread=1.0):
    """Grass clumps seen from above: 5-9 short tapered strokes radiating from one root (each a
    little curved), the way a meadow is dotted in a painted map.  ``dirs``: rotation per clump."""
    col = P["grass_mark"] if color is None else color
    out = []
    for i, (x, y) in enumerate(centers):
        rot = dirs[i] if dirs is not None else rng.uniform(0, math.tau)
        k = rng.randint(*n)
        fan = rng.uniform(1.6, 3.4)                  # a fan, not a star: the clump leans one way
        for b in range(k):
            a = rot + fan * (b / max(k - 1, 1) - 0.5) + rng.uniform(-0.2, 0.2)
            L = rng.uniform(*length) * spread
            bend = rng.uniform(-0.4, 0.4)
            p0 = np.array([x, y]) + 0.012 * np.array([math.cos(a), math.sin(a)])
            p1 = p0 + 0.5 * L * np.array([math.cos(a), math.sin(a)])
            p2 = p0 + L * np.array([math.cos(a + bend), math.sin(a + bend)])
            out.append(dict(pts=np.array([p0, p1, p2]), w=width * rng.uniform(0.75, 1.15),
                            color=col * rng.uniform(0.92, 1.06), alpha=alpha * rng.uniform(0.65, 1.0),
                            taper=(0.08, 0.75), h=h, seed=rng.randint(0, 99999)))
    return out


def wave_line(rng, x0, y0, length, amp, wavelength, angle, width, color, alpha, seed=0, crest=True):
    """One 水纹 wave line: a gently undulating stroke whose crests curl (gongbi water)."""
    n = max(8, int(length / 0.04))
    t = np.linspace(0, 1, n)
    ph = rng.uniform(0, math.tau)
    xs = t * length
    ys = amp * np.sin(xs / wavelength * math.tau + ph) * np.sin(t * math.pi) ** 0.6
    ca, sa = math.cos(angle), math.sin(angle)
    pts = np.stack([x0 + xs * ca - ys * sa, y0 + xs * sa + ys * ca], -1)
    out = [dict(pts=pts, w=width, color=color, alpha=alpha, taper=(0.3, 0.35), seed=seed)]
    if crest:
        # curling crest hooks at the wave tops
        for k in range(1, n - 1):
            if ys[k] > ys[k - 1] and ys[k] >= ys[k + 1] and ys[k] > 0.6 * amp and rng.random() < 0.7:
                hx, hy = pts[k]
                hook = []
                for j in range(6):
                    aa = angle + math.pi * 0.5 + j * 0.45
                    rr = amp * 0.55 * (1 - j / 7.0)
                    hook.append((hx + rr * math.cos(aa) - amp * 0.4 * ca, hy + rr * math.sin(aa) - amp * 0.4 * sa))
                out.append(dict(pts=np.array(hook), w=width * 0.8, color=color, alpha=alpha * 0.85,
                                taper=(0.05, 0.8), seed=seed + k))
    return out


# ---------------------------------------------------------------------------------------------
# normal map from the painted height (planar UV: tangent = +x, bitangent = +y)
# ---------------------------------------------------------------------------------------------
def normal_map(height, ppm, strength=1.0, size=None):
    """Tangent-space normal map (0..1 RGB, OpenGL / glTF convention) from a height field in
    metres sampled at ``ppm`` px per metre (image rows top-down = -y)."""
    h = np.asarray(height, np.float32)
    gy, gx = np.gradient(h)
    dx = gx * ppm * strength          # dh/dx
    dy = -gy * ppm * strength         # dh/dy (rows go down = -y)
    n = np.dstack([-dx, -dy, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    out = n * 0.5 + 0.5
    if size and size != h.shape[0]:
        from PIL import Image
        chans = [np.asarray(Image.fromarray(out[..., k].astype(np.float32), "F").resize((size, size), Image.BILINEAR))
                 for k in range(3)]
        out = np.dstack(chans)
        nn = out * 2 - 1
        nn /= np.maximum(np.linalg.norm(nn, axis=-1, keepdims=True), 1e-6)
        out = nn * 0.5 + 0.5
    return out


def blur(a, sigma):
    """Separable gaussian blur (numpy, edge-clamped)."""
    if sigma <= 0:
        return a
    r = int(max(1, round(sigma * 3)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    out = np.asarray(a, np.float32)
    for ax in (0, 1):
        pad = [(0, 0)] * out.ndim
        pad[ax] = (r, r)
        p = np.pad(out, pad, mode="edge")
        acc = np.zeros_like(out)
        for i, kv in enumerate(k):
            sl = [slice(None)] * out.ndim
            sl[ax] = slice(i, i + out.shape[ax])
            acc += kv * p[tuple(sl)]
        out = acc
    return out
