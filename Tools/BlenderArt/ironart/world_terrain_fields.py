"""World Terrain family - the Nine Provinces heightfield and feature fields (numpy only).

Builds the world of the scenario ``map`` block (DESIGN.md section 12.2: map units are metres, map
x east, map y south, heights -40..180 m) on the *master grid*: one sample per metre at integer map
points, ``(1501, 2401)`` = rows y 0..1500, columns x 0..2400.  ``Height.png`` is this grid
decimated by ``gridStep`` 2 (pixel (i, j) = map point (2i, 2j)); the albedo/masks painter
(:mod:`ironart.world_terrain_paint`) upsamples the fields to the 0.5 m texel grid.

Pipeline (:func:`build_world`)::

    coast       signed distance to the land polygons (map-border edges are not coast), domain
                warped -> land / sea, beaches, a 2.5 m surf shelf and a -40 m sea floor
    base        plains 2-15 m rising inland, gentle rolling noise, dune swells in the deserts
    hills       rounded 20-60 m hills along the hill strokes
    mountains   eroded ridged multifractal along the mountain strokes, peaks 150-180 m, saddles
                where roads cross them, suppressed around city sites
    rivers      meandered, deflected around city pads, tributaries snapped onto their main river;
                monotonic bed profiles to the sea / lakes, channels 2-4 m below the banks, gorges
                where a river cuts a range
    lakes       flat basins at (surface - 1 m) with soft shores
    pads        flat city pads (radius by city size) blended into the land
    forests     organic forest density (scenario circles + copses), used by trees and the painter

Everything is deterministic for a seed.  Units: metres everywhere.
"""

import json
import math
import os

import numpy as np

from . import terrain as T

MAP_W, MAP_H = 2400, 1500
MIN_H, MAX_H, SEA_LEVEL = -40.0, 180.0, 0.0
GRID_STEP = 2

#: flat pad radius / blend ring (m) per city size; City_1..3 footprints are ~45 / 75 / 120 m
PAD_RADIUS = {1: 38.0, 2: 52.0, 3: 68.0}
PAD_BLEND = 55.0
#: no trees closer than this to a city point (DESIGN.md: 25 m; we keep the whole pad clear)
TREE_CITY_CLEAR = {1: 50.0, 2: 64.0, 3: 80.0}

PARAMS = {
    "seed": 1212,
    # coast
    "coast_warp": 30.0, "coast_warp_scale": 230.0, "coast_detail": 10.0,
    "shelf_depth": 2.6, "shelf_width": 24.0, "sea_floor": -40.0, "sea_slope_width": 300.0,
    # plains
    "plain_coast": 1.4, "plain_inland": 12.5, "plain_rise": 520.0, "plain_roll": 2.4,
    # hills
    "hill_height": 66.0,
    # mountains
    "mtn_base": 112.0, "mtn_per_width": 0.62, "mtn_ridge_scale": 150.0, "mtn_peak": 179.0,
    # rivers
    "river_bank": 3.0, "river_meander": 1.0,
}


# ---------------------------------------------------------------------------------------------
# scenario
# ---------------------------------------------------------------------------------------------
def scenario_path():
    from . import REPO_DIR
    return os.path.join(REPO_DIR, "Content", "Data", "Scenarios", "BrokenMandate.json")


def load_scenario(path=None):
    with open(path or scenario_path(), encoding="utf-8") as f:
        d = json.load(f)
    m = d["map"]
    if (m["width"], m["height"]) != (MAP_W, MAP_H):
        raise ValueError("map block is %sx%s, the terrain contract is %dx%d"
                         % (m["width"], m["height"], MAP_W, MAP_H))
    cities = {c["key"]: c for c in d["cities"]}
    return {"map": m, "cities": cities, "roads": d["roads"]}


# ---------------------------------------------------------------------------------------------
# grids and fast noise
# ---------------------------------------------------------------------------------------------
def master_shape():
    return (MAP_H + 1, MAP_W + 1)


def master_xy():
    """Coordinate arrays (x, y) of the master grid (integer metres), float32."""
    ys, xs = np.mgrid[0:MAP_H + 1, 0:MAP_W + 1].astype(np.float32)
    return xs, ys


def vnoise(shape, cell, seed, octaves=1, gain=0.5, lacunarity=2.0, normalise=True):
    """Fast fractal value noise (bicubic-upsampled random lattices, Pillow C code).

    ``cell`` = feature size in pixels of the output grid.  Zero mean, ~unit std when
    ``normalise``.  Used for colour/texture layers where perlin_at would be too slow."""
    from PIL import Image
    h, w = shape
    rng = np.random.default_rng(seed)
    acc = np.zeros(shape, np.float32)
    amp = 1.0
    c = float(cell)
    for o in range(octaves):
        cs = max(c, 1.0)
        gh, gw = int(math.ceil(h / cs)) + 4, int(math.ceil(w / cs)) + 4
        lat = rng.standard_normal((gh, gw)).astype(np.float32)
        oh, ow = int(round(gh * cs)), int(round(gw * cs))
        big = np.asarray(Image.fromarray(lat, "F").resize((ow, oh), Image.BICUBIC), np.float32)
        oy = int(rng.integers(0, max(1, int(cs * 2))))
        ox = int(rng.integers(0, max(1, int(cs * 2))))
        acc += amp * big[oy:oy + h, ox:ox + w]
        amp *= gain
        c /= lacunarity
    if normalise:
        acc -= acc.mean()
        acc /= max(1e-6, float(acc.std()))
    return acc


def upsample2(f):
    """Master-grid field (1501, 2401) -> 0.5 m texel grid (3000, 4800), exact bilinear.

    Texel (j, i) has its centre at map point ((i + 0.5) / 2, (j + 0.5) / 2)."""
    f = np.asarray(f, np.float32)

    def axis(a, ax):
        a0 = np.take(a, np.arange(a.shape[ax] - 1), axis=ax)
        a1 = np.take(a, np.arange(1, a.shape[ax]), axis=ax)
        even = 0.75 * a0 + 0.25 * a1
        odd = 0.25 * a0 + 0.75 * a1
        out_shape = list(a0.shape)
        out_shape[ax] *= 2
        out = np.empty(out_shape, np.float32)
        sl_e = [slice(None)] * a.ndim
        sl_o = [slice(None)] * a.ndim
        sl_e[ax] = slice(0, None, 2)
        sl_o[ax] = slice(1, None, 2)
        out[tuple(sl_e)] = even
        out[tuple(sl_o)] = odd
        return out
    return axis(axis(f, 0), 1)


def sample(f, x, y):
    """Bilinear sample of a master-grid field at map points (arrays)."""
    x = np.clip(np.asarray(x, np.float64), 0, MAP_W - 1e-4)
    y = np.clip(np.asarray(y, np.float64), 0, MAP_H - 1e-4)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    fx = (x - x0).astype(np.float32)
    fy = (y - y0).astype(np.float32)
    a = f[y0, x0] * (1 - fx) + f[y0, x0 + 1] * fx
    b = f[y0 + 1, x0] * (1 - fx) + f[y0 + 1, x0 + 1] * fx
    return a * (1 - fy) + b * fy


def gaussian(a, sigma):
    from . import post
    return post.gaussian(a, sigma)


def box_down(a, k):
    """Average-pool by an integer factor (crops to a multiple)."""
    h, w = a.shape[0] // k * k, a.shape[1] // k * k
    return a[:h, :w].reshape(h // k, k, w // k, k).mean(axis=(1, 3))


def smooth_up(a, shape):
    """Bicubic resize of a 2D float field to ``shape`` (h, w)."""
    from PIL import Image
    return np.asarray(Image.fromarray(np.asarray(a, np.float32), "F")
                      .resize((shape[1], shape[0]), Image.BICUBIC), np.float32)


# ---------------------------------------------------------------------------------------------
# polylines
# ---------------------------------------------------------------------------------------------
def resample(points, step):
    pts = np.asarray(points, np.float64)
    out = [pts[0]]
    for a, b in zip(pts[:-1], pts[1:]):
        L = float(np.hypot(*(b - a)))
        n = max(1, int(math.ceil(L / step)))
        for k in range(1, n + 1):
            out.append(a + (b - a) * k / n)
    return np.array(out)


def arclen(pts):
    return np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))])


def normals(pts):
    tg = np.gradient(pts, axis=0)
    tg /= np.maximum(np.linalg.norm(tg, axis=1, keepdims=True), 1e-9)
    return np.stack([-tg[:, 1], tg[:, 0]], 1), tg


def smooth_line(pts, sigma, fixed_ends=True):
    """Gaussian smoothing along a polyline (samples), endpoints kept."""
    if sigma <= 0:
        return pts
    r = int(math.ceil(3 * sigma))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    p = np.pad(pts, ((r, r), (0, 0)), mode="edge")
    out = np.stack([np.convolve(p[:, c], k, mode="valid") for c in range(2)], 1)
    if fixed_ends:
        out[0], out[-1] = pts[0], pts[-1]
    return out


def polyline_field(pts, radius, want_t=True, shape=None, want_side=False, origin=(0, 0)):
    """Distance (m) from master-grid points to a polyline within ``radius`` (else +inf), and the
    arc length (m) of the nearest point (and with ``want_side`` the side, +1 = left of the
    direction of travel in map axes).  Each segment only touches its own window, so dense river
    polylines stay cheap."""
    H, W = shape or master_shape()
    best = np.full((H, W), np.inf, np.float32)
    bt = np.zeros((H, W), np.float32) if want_t else None
    bs = np.zeros((H, W), np.float32) if want_side else None
    pts = np.asarray(pts, np.float64) - np.asarray(origin, np.float64)
    cum = arclen(pts)
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        x0 = int(max(0, math.floor(min(a[0], b[0]) - radius)))
        x1 = int(min(W - 1, math.ceil(max(a[0], b[0]) + radius)))
        y0 = int(max(0, math.floor(min(a[1], b[1]) - radius)))
        y1 = int(min(H - 1, math.ceil(max(a[1], b[1]) + radius)))
        if x1 < x0 or y1 < y0:
            continue
        xs = np.arange(x0, x1 + 1, dtype=np.float32)[None, :]
        ys = np.arange(y0, y1 + 1, dtype=np.float32)[:, None]
        d = b - a
        L2 = float(d @ d) + 1e-9
        t = np.clip(((xs - a[0]) * d[0] + (ys - a[1]) * d[1]) / L2, 0.0, 1.0)
        px = a[0] + t * d[0] - xs
        py = a[1] + t * d[1] - ys
        dist = np.sqrt(px * px + py * py).astype(np.float32)
        sub = best[y0:y1 + 1, x0:x1 + 1]
        m = dist < sub
        np.copyto(sub, dist, where=m)
        if want_t:
            st = bt[y0:y1 + 1, x0:x1 + 1]
            np.copyto(st, (cum[i] + t * (cum[i + 1] - cum[i])).astype(np.float32), where=m)
        if want_side:
            ss_ = bs[y0:y1 + 1, x0:x1 + 1]
            cr = d[0] * (ys - a[1]) - d[1] * (xs - a[0])
            np.copyto(ss_, np.where(cr >= 0, 1.0, -1.0).astype(np.float32), where=m)
    if want_side:
        return best, bt, bs
    return (best, bt) if want_t else best


def window(pts, radius, shape=None):
    """(slice_y, slice_x, origin) of the master-grid window around a polyline +- radius."""
    H, W = shape or master_shape()
    pts = np.asarray(pts, np.float64)
    x0 = int(max(0, math.floor(pts[:, 0].min() - radius)))
    x1 = int(min(W, math.ceil(pts[:, 0].max() + radius) + 1))
    y0 = int(max(0, math.floor(pts[:, 1].min() - radius)))
    y1 = int(min(H, math.ceil(pts[:, 1].max() + radius) + 1))
    return slice(y0, y1), slice(x0, x1), (x0, y0)


def segment_distance_full(segs, shape=None, block=256):
    """Unbounded distance from every master-grid point to a list of segments ((x0,y0),(x1,y1))."""
    H, W = shape or master_shape()
    best = np.full((H, W), np.inf, np.float32)
    xs = np.arange(W, dtype=np.float32)[None, :]
    for r0 in range(0, H, block):
        r1 = min(H, r0 + block)
        ys = np.arange(r0, r1, dtype=np.float32)[:, None]
        bb = best[r0:r1]
        for (a, b) in segs:
            a = np.asarray(a, np.float32)
            b = np.asarray(b, np.float32)
            d = b - a
            L2 = float(d @ d) + 1e-9
            t = np.clip(((xs - a[0]) * d[0] + (ys - a[1]) * d[1]) / L2, 0, 1)
            px = a[0] + t * d[0] - xs
            py = a[1] + t * d[1] - ys
            np.minimum(bb, np.sqrt(px * px + py * py), out=bb)
    return best


def polygon_inside(poly, shape=None, ss=1):
    """Coverage of a polygon on the master grid (point (i, j) = pixel centre), 0/1 float."""
    from PIL import Image, ImageDraw
    H, W = shape or master_shape()
    im = Image.new("L", (W * ss, H * ss), 0)
    ImageDraw.Draw(im).polygon([((x + 0.5) * ss, (y + 0.5) * ss) for x, y in poly], fill=255)
    a = np.asarray(im, np.float32) / 255.0
    if ss > 1:
        a = box_down(a, ss)
    return a


def _on_border(a, b, eps=1.0):
    for k, lim in ((0, 0.0), (0, float(MAP_W)), (1, 0.0), (1, float(MAP_H))):
        if abs(a[k] - lim) < eps and abs(b[k] - lim) < eps:
            return True
    return False


# ---------------------------------------------------------------------------------------------
# rivers (polyline preparation)
# ---------------------------------------------------------------------------------------------
def city_list(sc):
    return [(c["key"], float(c["x"]), float(c["y"]), int(c.get("size", 1))) for c in sc["cities"].values()]


def deflect(pts, cities, clear_fn, iters=8, sigma=6.0, fixed=(True, True)):
    """Push a polyline out of city keep-out discs, smoothing the detour along the line."""
    p = pts.copy()
    for _ in range(iters):
        moved = False
        for (_k, cx, cy, size) in cities:
            R = clear_fn(size)
            v = p - np.array([cx, cy])
            d = np.hypot(v[:, 0], v[:, 1])
            m = d < R
            if fixed[0]:
                m[0] = False
            if fixed[1]:
                m[-1] = False
            if not m.any():
                continue
            moved = True
            nrm, _tg = normals(p)
            # direction: away from the centre; for points near the centre use the line normal on
            # the side the line already lies on (so the river keeps flowing past, not back)
            side = np.sign(np.sum(v[m] * nrm[m], axis=1))
            side[side == 0] = 1.0
            dirv = np.where(d[m, None] > 4.0, v[m] / np.maximum(d[m, None], 1e-6), nrm[m] * side[:, None])
            p[m] = np.array([cx, cy]) + dirv * (R + 2.0)
        p = smooth_line(p, sigma, fixed_ends=True)
        if not moved:
            break
    return p


def meander(pts, amount, seed, step=4.0, fade=40.0):
    """Natural lateral meander (two noise octaves), endpoints pinned."""
    p = resample(pts, step)
    t = arclen(p)
    nrm, _ = normals(p)
    n1 = T.perlin_at((t / 95.0).astype(np.float32), np.full(len(t), 0.37, np.float32), seed)
    n2 = T.perlin_at((t / 31.0).astype(np.float32), np.full(len(t), 0.71, np.float32), seed + 1)
    off = amount * (0.78 * n1 + 0.32 * n2)
    f = np.minimum(1.0, np.minimum(t, t[-1] - t) / fade)
    f = f * f * (3 - 2 * f)
    return p + nrm * (off * f)[:, None]


def snap_onto(trib, main, overrun=6.0):
    """End the tributary exactly on the main river (plus a short overrun into its channel)."""
    trib = np.asarray(trib, np.float64)
    q, _ = T.nearest_on_polyline(main.astype(np.float32), trib[-1])
    q = np.asarray(q, np.float64)
    out = np.vstack([trib[:-1], q])
    d = q - out[-2]
    d /= np.linalg.norm(d) + 1e-9
    out = resample(np.vstack([out, q + d * overrun]), 4.0)
    return out


def extend(pts, start=0.0, end=0.0):
    p = np.asarray(pts, np.float64)
    if start > 0:
        d = p[0] - p[1]
        d /= np.linalg.norm(d) + 1e-9
        p = np.vstack([p[0] + d * start, p])
    if end > 0:
        d = p[-1] - p[-2]
        d /= np.linalg.norm(d) + 1e-9
        p = np.vstack([p, p[-1] + d * end])
    return resample(p, 4.0)


# ---------------------------------------------------------------------------------------------
# the world
# ---------------------------------------------------------------------------------------------
class World:
    """All master-grid fields + vector data of the generated world (see module doc)."""

    def __init__(self, sc, params=None, log=print):
        self.sc = sc
        self.m = sc["map"]
        self.p = dict(PARAMS, **(params or {}))
        self.log = log
        self.seed = int(self.p["seed"])
        self.shape = master_shape()
        self.xs, self.ys = master_xy()
        self.cities = city_list(sc)
        self.f = {}          # fields (master grid)
        self.rivers = []     # dicts: pts, width, bed, ...
        self.lakes = []
        self.roads = []

    # -- helpers -------------------------------------------------------------------------------
    def noise(self, scale, octaves, seed, warp=None):
        x, y = (self.xs, self.ys) if warp is None else warp
        return T.fbm_at(x, y, scale, octaves, seed=self.seed + seed)

    def warp(self, amount, scale, seed):
        return (self.xs + amount * T.fbm_at(self.xs, self.ys, scale, 3, seed=self.seed + seed),
                self.ys + amount * T.fbm_at(self.xs, self.ys, scale, 3, seed=self.seed + seed + 1))

    def city_distance(self):
        d = np.full(self.shape, np.inf, np.float32)
        near = np.zeros(self.shape, np.int16) - 1
        for k, (_key, cx, cy, _s) in enumerate(self.cities):
            dd = np.hypot(self.xs - cx, self.ys - cy)
            m = dd < d
            d[m] = dd[m]
            near[m] = k
        return d, near

    # -- 1. coast ------------------------------------------------------------------------------
    def build_coast(self):
        p = self.p
        land_polys = self.m["land"]
        inside = np.zeros(self.shape, np.float32)
        segs = []
        for poly in land_polys:
            inside = np.maximum(inside, polygon_inside(poly, self.shape, ss=1))
            for a, b in zip(poly, poly[1:] + poly[:1]):
                if not _on_border(a, b):
                    segs.append((a, b))
        d = segment_distance_full(segs, self.shape)
        sd = np.where(inside > 0.5, d, -d)
        # organic coastline: big bays/headlands + small coves (warp only near the coast)
        n = (self.p["coast_warp"] * self.noise(p["coast_warp_scale"], 3, 11)
             + p["coast_detail"] * self.noise(64.0, 3, 12)
             + 2.2 * self.noise(14.0, 2, 13))
        sdw = sd + n * T.smoothstep(260.0, 60.0, np.abs(sd))
        land = sdw > 0
        # sea pockets cut off from the open sea become land, tiny islets stay (natural rocks)
        land = self._fill_pockets(land)
        self.f["sd"] = sdw.astype(np.float32)
        self.f["land0"] = land
        self.log("[world] coast: %d segments, land %.1f %%" % (len(segs), 100 * land.mean()))

    def _fill_pockets(self, land):
        """Water not connected to the map's open sea (east part) -> land.  Iterative dilation
        on a 4 m grid, then exact on the master grid inside the reached area."""
        sea = ~land
        k = 4
        sc = box_down(sea.astype(np.float32), k) > 0.99      # conservative coarse sea
        reach = np.zeros_like(sc)
        reach[:, -1] = sc[:, -1]
        for _ in range(4000):
            g = reach.copy()
            g[1:] |= reach[:-1]
            g[:-1] |= reach[1:]
            g[:, 1:] |= reach[:, :-1]
            g[:, :-1] |= reach[:, 1:]
            g &= sc
            if (g == reach).all():
                break
            reach = g
        # back to full res: every fine sea pixel within 2 coarse cells of reached sea is open sea
        rf = np.repeat(np.repeat(reach, k, 0), k, 1)
        full = np.zeros(self.shape, bool)
        full[:rf.shape[0], :rf.shape[1]] = rf
        grown = gaussian(full.astype(np.float32), 6.0) > 0.01
        open_sea = sea & grown
        # flood the fine sea pixels connected to the coarse open sea (few iterations)
        cur = open_sea & full
        for _ in range(40):
            g = cur.copy()
            g[1:] |= cur[:-1]
            g[:-1] |= cur[1:]
            g[:, 1:] |= cur[:, :-1]
            g[:, :-1] |= cur[:, 1:]
            g &= sea
            if (g == cur).all():
                break
            cur = g
        pockets = sea & ~cur
        self.log("[world] sea pockets filled: %d px" % int(pockets.sum()))
        return land | pockets

    # -- 2. base relief ------------------------------------------------------------------------
    def build_base(self):
        p = self.p
        sd = self.f["sd"]
        din = np.maximum(sd, 0.0)
        rise = T.smoothstep(0.0, p["plain_rise"], din) ** 0.8
        roll = (p["plain_roll"] * self.noise(260.0, 4, 21) + 0.9 * self.noise(70.0, 3, 22)
                + 0.25 * self.noise(18.0, 2, 23))
        base = p["plain_coast"] + p["plain_inland"] * rise + roll * T.smoothstep(0, 120, din)
        # deserts: low dune swells (5-9 m) and a slightly raised steppe plateau
        des = np.zeros(self.shape, np.float32)
        wx, wy = self.warp(40.0, 160.0, 31)
        for dz in self.m["deserts"]:
            dd = np.hypot(wx - dz["x"], wy - dz["y"])
            des = np.maximum(des, T.smoothstep(dz["r"] * 1.15, dz["r"] * 0.55, dd))
        dune = 0.5 + 0.5 * np.sin((self.xs * 0.8 + self.ys * 0.6) / 23.0
                                  + 3.0 * self.noise(90.0, 2, 32))
        base = base + des * (2.5 + 5.0 * dune * (0.6 + 0.4 * self.noise(140.0, 2, 33)))
        self.f["desert"] = des.astype(np.float32)
        # sea floor: 2.5 m surf shelf, then down to -40 m
        dsea = np.maximum(-sd, 0.0)
        floor = -(p["shelf_depth"] * T.smoothstep(0.0, p["shelf_width"], dsea)
                  + (abs(p["sea_floor"]) - p["shelf_depth"])
                  * T.smoothstep(p["shelf_width"] * 0.4, p["sea_slope_width"], dsea) ** 1.25)
        floor = floor + 1.2 * self.noise(60.0, 3, 24) * T.smoothstep(10, 60, dsea)
        # beach: land within ~2 m of sea level near the shore
        h = np.where(self.f["land0"], np.maximum(base, 0.35), np.minimum(floor, -0.3))
        self.f["base"] = h.astype(np.float32)
        self.log("[world] base: plains %.1f..%.1f m" % (float(base[self.f["land0"]].min()),
                                                       float(base[self.f["land0"]].max())))

    # -- 3. hills and mountains -----------------------------------------------------------------
    def _stroke(self, s, reach, smooth=7.0):
        """Smoothed stroke polyline in its own window: distance, blurred arc length (no bisector
        seams) and side, all cropped to ``win = (sy, sx)``."""
        pts = smooth_line(resample(s["points"], 4.0), smooth)
        R = reach * s["width"]
        sy, sx, org = window(pts, R, self.shape)
        shp = (sy.stop - sy.start, sx.stop - sx.start)
        d, t, side = polyline_field(pts, R, want_t=True, shape=shp, want_side=True, origin=org)
        ok = np.isfinite(d)
        # blur the arc parameter: on the inner side of a bend the nearest segment switches and
        # raw t jumps (that would draw a straight seam through the spurs)
        u = gaussian(np.where(ok, t, 0.0), 14.0)
        wsum = gaussian(ok.astype(np.float32), 14.0)
        u = np.where(wsum > 1e-3, u / np.maximum(wsum, 1e-3), 0.0)
        sv = gaussian(np.where(ok, side, 0.0), 6.0)
        d = np.where(ok, d, 1e5).astype(np.float32)
        return pts, (sy, sx), d, u.astype(np.float32), sv.astype(np.float32), float(arclen(pts)[-1])

    def build_relief(self):
        p = self.p
        cityd, _ = self.city_distance()
        self.f["city_d"] = cityd
        city_r = np.zeros(self.shape, np.float32)
        for (_k, cx, cy, s) in self.cities:
            dd = np.hypot(self.xs - cx, self.ys - cy)
            city_r = np.maximum(city_r, T.smoothstep(PAD_RADIUS[s] + 150.0, PAD_RADIUS[s], dd))
        keep_city = 1.0 - city_r          # 0 at city sites, 1 away from them
        road_d = self._road_corridor_distance()
        self.f["road_d0"] = road_d
        # ---- hills: a chain of rounded tops along each stroke + billowy lumps
        wx, wy = self.warp(22.0, 90.0, 41)
        lumps = 0.5 + 0.5 * T.fbm_at(wx, wy, 64.0, 4, seed=self.seed + 42)
        bill = 1.0 - np.abs(T.fbm_at(wx, wy, 38.0, 3, seed=self.seed + 43))
        hill_env = np.zeros(self.shape, np.float32)
        hills = np.zeros(self.shape, np.float32)
        for k, s in enumerate(self.m["hills"]):
            _pts, wn, d, u, sv, L = self._stroke(s, 2.8)
            xs, ys = self.xs[wn], self.ys[wn]
            w = s["width"]
            e = np.exp(-(d / (1.0 * w)) ** 2)
            chain = 0.5 + 0.5 * np.cos(2 * np.pi * u / (0.95 * w + 40.0)
                                       + 2.2 * T.fbm_at(xs, ys, 80.0, 2, seed=self.seed + 44 + k))
            hk = p["hill_height"] * e ** 1.2 * (0.30 + 0.38 * chain + 0.32 * lumps[wn] ** 1.3
                                                + 0.16 * bill[wn])
            hills[wn] = np.maximum(hills[wn], hk)
            hill_env[wn] = np.maximum(hill_env[wn], e)
        saddle_h = 1.0 - 0.45 * np.exp(-(road_d / 26.0) ** 2)
        hills = hills * saddle_h * keep_city
        # ---- mountains: a sharp continuous crest per stroke, spurs running down from it
        #      (ridged noise in stroke-aligned coordinates), summits along the crest, then
        #      a global ridged massif and derivative-damped erosion detail
        wx, wy = self.warp(30.0, 130.0, 51)
        ridged = T.ridged_at(wx, wy, p["mtn_ridge_scale"], 4, 0.5, seed=self.seed + 52, sharpness=1.6)
        mtn = np.zeros(self.shape, np.float32)
        core_env = np.zeros(self.shape, np.float32)
        foot_env = np.zeros(self.shape, np.float32)
        for k, s in enumerate(self.m["mountains"]):
            pts, wn, d, u, sv, L = self._stroke(s, 3.4, smooth=9.0)
            xs, ys = self.xs[wn], self.ys[wn]
            w = float(s["width"])
            jit = 1.0 + 0.14 * T.fbm_at(xs, ys, 110.0, 2, seed=self.seed + 60 + k)
            v = sv * d                                  # signed across-range coordinate
            wu = u + 14.0 * T.fbm_at(xs, ys, 45.0, 2, seed=self.seed + 61 + k)
            n_sp = T.perlin_at(wu / 46.0, v / 130.0 + 7.0 * k, self.seed + 62 + k)
            spur = (1.0 - np.abs(n_sp)) ** 1.6           # ridges running across the range
            summit = 0.80 + 0.20 * T.perlin_at(u / 160.0, np.full_like(u, 0.3 + k), self.seed + 63 + k)
            taper = 0.62 + 0.38 * T.smoothstep(0.0, 0.9 * w, u) * T.smoothstep(L, L - 0.9 * w, u)
            dw = d / jit
            crest = 0.5 * np.exp(-(dw / (0.85 * w)) ** 2) + 0.5 * np.exp(-dw / (0.40 * w))
            core = np.exp(-(dw / (0.80 * w)) ** 2)
            foot = np.exp(-(dw / (1.8 * w)) ** 2)
            peak = p["mtn_base"] + p["mtn_per_width"] * w
            body = crest ** 0.9 * (0.52 + 0.30 * spur + 0.26 * ridged[wn])
            mk = peak * summit * taper * body + 30.0 * foot * (0.35 + 0.65 * lumps[wn])
            mtn[wn] = np.maximum(mtn[wn], mk)
            core_env[wn] = np.maximum(core_env[wn], core)
            foot_env[wn] = np.maximum(foot_env[wn], foot)
        saddle_m = 1.0 - 0.72 * np.exp(-(road_d / 46.0) ** 2)
        mtn = mtn * saddle_m * keep_city
        mtn = self._erode_detail(mtn, core_env)
        land = self.f["land0"]
        lift = (np.maximum(hills, 0) + np.maximum(mtn, 0)) * T.smoothstep(-6.0, 30.0, self.f["sd"])
        h = self.f["base"] + lift
        # islands: a wooded central hill on each small island
        for poly in self.m["land"][1:]:
            cx = float(np.mean([q[0] for q in poly]))
            cy = float(np.mean([q[1] for q in poly]))
            r = 0.5 * max(np.ptp([q[0] for q in poly]), np.ptp([q[1] for q in poly]))
            dd = np.hypot(self.xs - cx, self.ys - cy)
            isl = np.exp(-(dd / (0.55 * r)) ** 2) * (0.6 + 0.4 * lumps)
            h = h + (12.0 + 0.16 * r) * isl * T.smoothstep(-2.0, 25.0, self.f["sd"])
        # soft ceiling: peaks land at 165-180 m, nothing clips flat
        top = p["mtn_peak"]
        knee = top - 26.0
        h = np.where(h > knee, knee + 26.0 * np.tanh((h - knee) / 26.0), h)
        self.f["h_pre"] = np.where(land, h, self.f["base"]).astype(np.float32)
        self.f["hill_env"] = hill_env.astype(np.float32)
        self.f["mtn_core"] = core_env.astype(np.float32)
        self.f["mtn_foot"] = foot_env.astype(np.float32)
        self.f["mtn_h"] = mtn.astype(np.float32)
        self.f["hill_h"] = hills.astype(np.float32)
        self.log("[world] relief: max %.1f m, hills max %.1f m, p99.9 mountains %.1f m"
                 % (float(self.f["h_pre"].max()), float(hills.max()),
                    float(np.percentile(self.f["h_pre"][core_env > 0.5], 99.9))))

    def _erode_detail(self, mtn, env):
        """Add 4 octaves of detail whose amplitude is damped where the accumulated surface is
        already steep (IQ-style 'eroded fbm'): crisp ridges, smooth gullies, no noise pimples."""
        h = mtn.copy()
        amp = 15.0
        scale = 44.0
        for o in range(4):
            n = T.perlin_at(self.xs / scale + 3.1 * o, self.ys / scale - 1.7 * o, self.seed + 70 + o)
            gy, gx = np.gradient(gaussian(h, 1.5))
            g2 = gx * gx + gy * gy
            damp = 1.0 / (1.0 + 2.0 * g2)
            ridge = 1.0 - np.abs(n)               # ridged detail
            h = h + amp * (ridge - 0.55) * damp * env ** 0.7
            amp *= 0.48
            scale *= 0.5
        return np.maximum(h, 0.0)

    def _road_corridor_distance(self):
        """Distance to the straight city-to-city road/pass lines (river routes excluded)."""
        segs = []
        for r in self.sc["roads"]:
            if r.get("kind") == "river":
                continue
            a, b = self.sc["cities"][r["a"]], self.sc["cities"][r["b"]]
            segs.append(((a["x"], a["y"]), (b["x"], b["y"])))
        d = np.full(self.shape, np.inf, np.float32)
        for a, b in segs:
            dd = polyline_field(np.array([a, b], np.float64), 160.0, want_t=False, shape=self.shape)
            np.minimum(d, dd, out=d)
        return d

    # -- 4. lakes ------------------------------------------------------------------------------
    def build_lakes(self):
        h = self.f["h_pre"]
        sdl_all = np.full(self.shape, -np.inf, np.float32)
        for k, poly in enumerate(self.m["lakes"]):
            pts = resample(poly + poly[:1], 6.0)
            pts = smooth_line(pts, 2.0, fixed_ends=False)
            inside = polygon_inside([tuple(q) for q in pts], self.shape, ss=1)
            d = polyline_field(pts, 220.0, want_t=False, shape=self.shape)
            sd = np.where(inside > 0.5, d, -d)
            sd = sd + 6.0 * T.fbm_at(self.xs, self.ys, 46.0, 3, seed=self.seed + 90 + k) \
                + 2.0 * T.fbm_at(self.xs, self.ys, 12.0, 2, seed=self.seed + 95 + k)
            ring = (sd < -6) & (sd > -45)
            level = float(np.percentile(h[ring], 8)) - 2.6
            basin = level - 1.0
            self.lakes.append({"poly": pts, "level": level, "basin": basin, "index": k})
            # basin floor flat; the shore rises over 12 m to the bank (+1.6 m above the surface),
            # then gently (10 %) into the surrounding land
            rise = T.smoothstep(0.0, 12.0, -sd)
            prof = basin + (level + 1.6 - basin) * rise + 0.10 * np.maximum(-sd - 12.0, 0.0)
            prof = np.where(sd > 0, basin, prof)
            win = sd > -80
            h = np.where(win, np.minimum(h, prof), h)
            sdl_all = np.maximum(sdl_all, sd)
            self.log("[world] lake %d: surface %.2f m, basin %.2f m" % (k, level, basin))
        self.f["h_pre"] = h.astype(np.float32)
        self.f["lake_sd"] = sdl_all.astype(np.float32)

    # -- 5. rivers -----------------------------------------------------------------------------
    def prepare_rivers(self):
        """Vector river courses: meander, city detours, tributary snapping, ends into sea/lakes."""
        rv = self.m["rivers"]

        def clear(size):
            return PAD_RADIUS[size] + 16.0

        courses = []
        for k, r in enumerate(rv):
            pts = np.asarray(r["points"], np.float64)
            amt = self.p["river_meander"] * (7.0 + 0.6 * r["width"])
            mp = meander(pts, amt, self.seed + 200 + 7 * k)
            courses.append({"raw": pts, "pts": mp, "width": float(r["width"]), "index": k})
        # main rivers first (those that do not end on another river)
        ends = {}
        for c in courses:
            end = c["raw"][-1]
            ends[c["index"]] = None
            for o in courses:
                if o is c:
                    continue
                if np.min(np.hypot(*(o["raw"] - end).T)) < 3.0 and not np.allclose(o["raw"][-1], end):
                    ends[c["index"]] = o["index"]
        order = sorted(courses, key=lambda c: ends[c["index"]] is not None)
        for c in order:
            hw = 0.5 * c["width"] * 1.3

            def clr(size, hw=hw):
                return clear(size) + hw
            c["pts"] = deflect(c["pts"], self.cities, clr)
            parent = ends[c["index"]]
            if parent is not None:
                main = next(o for o in courses if o["index"] == parent)
                c["pts"] = snap_onto(c["pts"], main["pts"], overrun=0.5 * main["width"])
                c["joins"] = parent
            else:
                c["joins"] = None
            # mouths: into the sea / a lake; sources inside a lake are pulled back into it
            endp = c["pts"][-1]
            if c["joins"] is None:
                c["pts"] = extend(c["pts"], end=45.0)
            c["ends_lake"] = None
            c["starts_lake"] = None
            for lk in self.lakes:
                if _dist_to_poly(endp, lk["poly"]) < 25.0:
                    c["ends_lake"] = lk["index"]
                if _dist_to_poly(c["pts"][0], lk["poly"]) < 25.0:
                    c["starts_lake"] = lk["index"]
                    c["pts"] = extend(c["pts"], start=30.0)
        self.rivers = sorted(courses, key=lambda c: c["index"])
        for c in self.rivers:
            self.log("[world] river %d: %.0f m, width %.0f, joins %s, lake end %s, lake start %s"
                     % (c["index"], arclen(c["pts"])[-1], c["width"], c["joins"], c["ends_lake"],
                        c["starts_lake"]))

    def carve_rivers(self):
        """Bed profiles (monotonic to the sea / lake / parent river) and channel carving."""
        h = self.f["h_pre"].copy()
        bank = self.p["river_bank"]
        # valley half-width beyond the banks: narrow on the plains, wide gorges in the ranges
        wv = (34.0 + 60.0 * self.f["hill_env"] + 110.0 * self.f["mtn_core"]
              + 40.0 * self.f["mtn_foot"]).astype(np.float32)
        hsm = gaussian(h, 3.0)
        river_d = np.full(self.shape, np.inf, np.float32)
        river_hw = np.zeros(self.shape, np.float32)
        river_bed = np.zeros(self.shape, np.float32)
        river_id = np.full(self.shape, -1, np.int16)
        # process parents before tributaries (a tributary ends at its parent's bed)
        done = {}
        order = sorted(self.rivers, key=lambda c: c["joins"] is not None)
        for c in order:
            pts = c["pts"]
            t = arclen(pts)
            L = t[-1]
            raw = sample(hsm, pts[:, 0], pts[:, 1]) - bank
            # end constraint
            if c["joins"] is not None:
                par = done[c["joins"]]
                q, _ = T.nearest_on_polyline(par["pts"].astype(np.float32), pts[-1])
                tq = _arc_at(par["pts"], np.asarray(q))
                end_level = float(np.interp(tq, par["t"], par["bed"])) + 0.2
            elif c["ends_lake"] is not None:
                end_level = self.lakes[c["ends_lake"]]["basin"]
            else:
                end_level = -1.6
            start_level = None
            if c["starts_lake"] is not None:
                start_level = self.lakes[c["starts_lake"]]["basin"]
            bed = np.minimum.accumulate(raw)
            if start_level is not None:
                bed = np.minimum(bed, start_level)
            # tilt so the bed meets the end level exactly, keep a minimum fall of 0.9 m / km
            bed = bed + 0.0009 * (L - t)
            delta = bed[-1] - end_level
            bed = bed - delta * (t / L)
            bed = np.minimum.accumulate(bed)
            bed = np.maximum(bed, end_level)
            if c["joins"] is None and c["ends_lake"] is None:
                # last 45 m (extension) slopes into the sea
                bed = np.minimum(bed, np.interp(t, [0, L - 60, L], [1e9, 0.3, -3.0]))
            bed = smooth_1d(bed, 3)
            bed = np.minimum.accumulate(bed)
            # width: narrow at the source, full width downstream
            wdt = c["width"] * (0.55 + 0.6 * np.clip(t / max(L, 1), 0, 1))
            src_fade = T.smoothstep(0.0, 70.0, t) if c["starts_lake"] is None else np.ones_like(t)
            wdt = wdt * (0.35 + 0.65 * src_fade)
            c["t"], c["bed"], c["w"], c["src_fade"] = t, bed, wdt, src_fade
            done[c["index"]] = c
            # ---- carve
            reach = 420.0
            wy_, wx_, org = window(pts, reach, self.shape)
            shp = (wy_.stop - wy_.start, wx_.stop - wx_.start)
            d_w, tt_w = polyline_field(pts, reach, want_t=True, shape=shp, origin=org)
            d = np.full(self.shape, np.inf, np.float32)
            tt = np.zeros(self.shape, np.float32)
            d[wy_, wx_] = d_w
            tt[wy_, wx_] = tt_w
            del d_w, tt_w
            m = np.isfinite(d)
            bed_g = np.interp(tt[m], t, bed).astype(np.float32)
            hw_g = (0.5 * np.interp(tt[m], t, wdt)).astype(np.float32)
            dep = (bank * np.interp(tt[m], t, src_fade)).astype(np.float32)
            dd = d[m]
            bankw = 5.0 + 0.35 * hw_g
            # channel: slightly dished bed; banks rise 'dep' over bankw; valley walls at k_slope
            dish = 0.6 * np.clip(1.0 - (dd / np.maximum(hw_g, 0.5)) ** 2, 0, 1)
            top = bed_g + dep                                   # bank top
            chan = bed_g - dish + dep * T.smoothstep(hw_g - 0.5, hw_g + bankw, dd)
            hv = h[m]
            excess = np.maximum(hv - top, 0.0)
            wvm = np.minimum(wv[m] + 1.0 * excess, reach - hw_g - bankw - 30.0)  # higher -> wider
            g = T.smoothstep(0.0, 1.0, (dd - hw_g - bankw) / wvm) ** 0.85
            valley = top + excess * g
            prof = np.where(dd < hw_g + bankw, chan, valley)
            hn = np.minimum(hv, prof)
            # containment: the banks never drop below the water (no spills on low ground)
            band = (dd > hw_g) & (dd < hw_g + bankw + 3.0)
            hn = np.where(band, np.maximum(hn, bed_g + np.minimum(dep, 1.2)
                                           * T.smoothstep(hw_g, hw_g + bankw, dd)), hn)
            h[m] = hn
            # bookkeeping for painting
            closer = dd < river_d[m]
            rd = river_d[m]
            rd[closer] = dd[closer]
            river_d[m] = rd
            for arr, val in ((river_hw, hw_g), (river_bed, bed_g)):
                a = arr[m]
                a[closer] = val[closer]
                arr[m] = a
            ri = river_id[m]
            ri[closer] = c["index"]
            river_id[m] = ri
            self.log("[world] river %d bed %.1f -> %.1f m (end %.1f)" % (c["index"], bed[0], bed[-1],
                                                                         end_level))
        self.f["h_riv"] = h.astype(np.float32)
        self.f["river_d"] = river_d
        self.f["river_hw"] = river_hw
        self.f["river_bed"] = river_bed
        self.f["river_id"] = river_id

    # -- 6. city pads --------------------------------------------------------------------------
    def build_pads(self):
        h = self.f["h_riv"].copy()
        self.pads = []
        for (key, cx, cy, s) in self.cities:
            R = PAD_RADIUS[s]
            dd = np.hypot(self.xs - cx, self.ys - cy)
            disc = dd < R
            level = float(np.median(h[disc]))
            near_r = (dd < R + 70) & (self.f["river_d"] < self.f["river_hw"] + 2.0)
            if near_r.any():
                level = max(level, float(self.f["river_bed"][near_r].max()) + 3.2)
            level = max(level, 3.0)
            w = T.smoothstep(R + PAD_BLEND, R, dd)
            w = w * w * (3 - 2 * w)
            h = h * (1 - w) + level * w
            self.pads.append({"key": key, "x": cx, "y": cy, "size": s, "radius": R, "level": level})
        self.f["h"] = np.clip(h, MIN_H, MAX_H).astype(np.float32)
        self.log("[world] pads: " + ", ".join("%s %.1f" % (p["key"], p["level"]) for p in self.pads))

    # -- 7. roads (vector) ---------------------------------------------------------------------
    def build_roads(self):
        """Packed-earth tracks: straight city-to-city segments with a slight meander (the UI
        draws its dashed road line on the straight segment, so the track stays within ~5 m)."""
        self.roads = []
        for k, r in enumerate(self.sc["roads"]):
            a, b = self.sc["cities"][r["a"]], self.sc["cities"][r["b"]]
            kind = r.get("kind", "road")
            pa, pb = np.array([a["x"], a["y"]], float), np.array([b["x"], b["y"]], float)
            pts = resample(np.array([pa, pb]), 4.0)
            t = arclen(pts)
            L = t[-1]
            nrm, _ = normals(pts)
            n = (0.75 * T.perlin_at((t / 85.0).astype(np.float32), np.full(len(t), 0.21, np.float32),
                                    self.seed + 300 + k)
                 + 0.35 * T.perlin_at((t / 23.0).astype(np.float32), np.full(len(t), 0.63, np.float32),
                                      self.seed + 340 + k))
            fade = np.clip(np.minimum(t, L - t) / 60.0, 0, 1)
            pts = pts + nrm * (5.0 * n * fade)[:, None]
            self.roads.append({"a": r["a"], "b": r["b"], "kind": kind, "pts": pts,
                               "width": 4.6 if kind == "road" else 3.6})

    # -- 8. forests ------------------------------------------------------------------------------
    def build_forests(self):
        """Forest density 0..1: organic lobed shapes around the scenario circles plus copses."""
        rng = np.random.default_rng(self.seed + 400)
        wx, wy = self.warp(18.0, 40.0, 401)
        dens = np.zeros(self.shape, np.float32)
        for k, fz in enumerate(self.m["forests"]):
            cx, cy, r = fz["x"], fz["y"], fz["r"]
            ang = np.arctan2(wy - cy, wx - cx)
            # lobed outline: radius varies with angle (3-5 lobes) + small satellite groves
            lob = (0.18 * np.sin(3 * ang + rng.uniform(0, 6.3)) + 0.10 * np.sin(5 * ang + rng.uniform(0, 6.3))
                   + 0.06 * np.sin(8 * ang + rng.uniform(0, 6.3)))
            rr = r * (1.08 + lob)
            dd = np.hypot(wx - cx, wy - cy)
            dens = np.maximum(dens, T.smoothstep(rr + 14.0, rr - 10.0, dd))
            for _ in range(int(rng.integers(3, 6))):
                a = rng.uniform(0, 2 * np.pi)
                rd = r * rng.uniform(1.05, 1.45)
                sx, sy = cx + rd * np.cos(a), cy + rd * np.sin(a)
                sr = r * rng.uniform(0.18, 0.32)
                dd = np.hypot(wx - sx, wy - sy)
                dens = np.maximum(dens, T.smoothstep(sr + 8, sr - 6, dd))
        # copses on the open plains (6-14 m radius groves), away from cities and water
        h = self.f["h"]
        cityd = self.f["city_d"]
        copses = []
        tries = 0
        while len(copses) < 70 and tries < 4000:
            tries += 1
            x, y = rng.uniform(30, MAP_W - 30), rng.uniform(30, MAP_H - 30)
            ix, iy = int(x), int(y)
            if (h[iy, ix] < 2.0 or h[iy, ix] > 60.0 or cityd[iy, ix] < 160
                    or self.f["river_d"][iy, ix] < 30 or self.f["desert"][iy, ix] > 0.2
                    or dens[iy, ix] > 0.1 or self.f["lake_sd"][iy, ix] > -30):
                continue
            if any((x - a) ** 2 + (y - b) ** 2 < 90 ** 2 for a, b, _ in copses):
                continue
            copses.append((x, y, rng.uniform(9.0, 22.0)))
        for (x, y, r) in copses:
            x0, x1 = int(max(0, x - r - 30)), int(min(MAP_W, x + r + 30))
            y0, y1 = int(max(0, y - r - 30)), int(min(MAP_H, y + r + 30))
            sub = np.hypot(wx[y0:y1 + 1, x0:x1 + 1] - x, wy[y0:y1 + 1, x0:x1 + 1] - y)
            dens[y0:y1 + 1, x0:x1 + 1] = np.maximum(dens[y0:y1 + 1, x0:x1 + 1],
                                                    T.smoothstep(r + 8, r - 6, sub))
        self.copses = copses
        self.f["forest"] = dens.astype(np.float32)
        self.log("[world] forests: %d circles, %d copses, cover %.1f %%"
                 % (len(self.m["forests"]), len(copses), 100 * float((dens > 0.5).mean())))

    # -- 9. derived ----------------------------------------------------------------------------
    def build_derived(self):
        h = self.f["h"]
        gy, gx = np.gradient(h)
        self.f["slope"] = np.sqrt(gx * gx + gy * gy).astype(np.float32)
        hs = gaussian(h, 4.0)
        lap = (np.roll(hs, 1, 0) + np.roll(hs, -1, 0) + np.roll(hs, 1, 1) + np.roll(hs, -1, 1) - 4 * hs)
        self.f["curv"] = lap.astype(np.float32)          # > 0 concave (gully), < 0 convex (ridge)
        self.f["sea"] = (h < SEA_LEVEL) & ~(self.f["lake_sd"] > -2)
        self.f["land"] = h >= SEA_LEVEL

    # -- run -----------------------------------------------------------------------------------
    def build(self):
        import time
        steps = [("coast", self.build_coast), ("base", self.build_base), ("relief", self.build_relief),
                 ("lakes", self.build_lakes), ("rivers", self.prepare_rivers),
                 ("carve", self.carve_rivers), ("pads", self.build_pads), ("roads", self.build_roads),
                 ("forests", self.build_forests), ("derived", self.build_derived)]
        self.times = {}
        for name, fn in steps:
            t0 = time.time()
            fn()
            self.times[name] = time.time() - t0
            self.log("[world] %-8s %.1fs" % (name, self.times[name]))
        return self

    # -- export --------------------------------------------------------------------------------
    def height_png16(self):
        """Height.png samples (751, 1201) as uint16 per DESIGN.md 12.2 (pixel (i, j) = map
        point (2i, 2j)); the master grid is lightly low-passed first (no aliasing)."""
        h = gaussian(self.f["h"], 0.7)[::GRID_STEP, ::GRID_STEP]
        v = np.clip((h - MIN_H) / (MAX_H - MIN_H), 0, 1)
        return np.round(v * 65535.0).astype(np.uint16)

    def terrain_json(self):
        return {"width": MAP_W, "height": MAP_H, "gridStep": GRID_STEP, "minHeight": MIN_H,
                "maxHeight": MAX_H, "seaLevel": SEA_LEVEL}

    def vector_data(self):
        """Rivers / roads / lakes / pads as plain lists (for the painter and the tree scatter)."""
        return {
            "rivers": [{"index": c["index"], "pts": c["pts"].tolist(), "t": c["t"].tolist(),
                        "bed": c["bed"].tolist(), "w": c["w"].tolist()} for c in self.rivers],
            "roads": [{"a": r["a"], "b": r["b"], "kind": r["kind"], "width": r["width"],
                       "pts": r["pts"].tolist()} for r in self.roads],
            "lakes": [{"index": lk["index"], "level": lk["level"], "basin": lk["basin"],
                       "poly": lk["poly"].tolist()} for lk in self.lakes],
            "pads": self.pads,
            "copses": [list(c) for c in self.copses],
        }


def smooth_1d(a, r):
    if r <= 0:
        return a
    k = np.ones(2 * r + 1) / (2 * r + 1)
    p = np.pad(a, r, mode="edge")
    return np.convolve(p, k, mode="valid")


def _arc_at(pts, q):
    """Arc length of the point on polyline ``pts`` nearest to ``q``."""
    best, bt = 1e18, 0.0
    cum = arclen(pts)
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        d = b - a
        t = float(np.clip(((q - a) @ d) / (d @ d + 1e-9), 0, 1))
        p = a + t * d
        dd = float(((p - q) ** 2).sum())
        if dd < best:
            best, bt = dd, cum[i] + t * (cum[i + 1] - cum[i])
    return bt


def _point_in_poly(pt, poly):
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            if x < (x1 - x0) * (y - y0) / (y1 - y0 + 1e-12) + x0:
                inside = not inside
    return inside


def _dist_to_poly(pt, poly):
    if _point_in_poly(pt, poly):
        return 0.0
    q, _ = T.nearest_on_polyline(np.vstack([poly, poly[:1]]).astype(np.float32), np.asarray(pt))
    return float(np.hypot(*(np.asarray(q) - np.asarray(pt))))


def build_world(params=None, log=print, scenario=None):
    return World(scenario or load_scenario(), params, log).build()


# ---------------------------------------------------------------------------------------------
# quick numpy previews (no Blender): hillshade x hypsometric colour
# ---------------------------------------------------------------------------------------------
def hillshade(h, az_deg=315.0, alt_deg=45.0, z=1.0):
    gy, gx = np.gradient(h * z)
    az, alt = math.radians(az_deg), math.radians(alt_deg)
    # map y grows south: light from the north-west = (-x, -y)
    lx, ly, lz = -math.cos(math.radians(45)) * math.cos(alt), -math.sin(math.radians(45)) * math.cos(alt), math.sin(alt)
    n = np.sqrt(gx * gx + gy * gy + 1.0)
    return np.clip((-gx * lx - gy * ly + lz) / n, 0, 1)


def preview_rgb(world, scale=1):
    h = world.f["h"]
    if scale > 1:
        h = box_down(h, scale)
    sh = hillshade(h, z=1.0 / scale)
    c = np.zeros(h.shape + (3,), np.float32)
    land = h >= 0
    t = np.clip(h / 180.0, 0, 1)[..., None]
    lowc = np.array([0.55, 0.64, 0.38])
    midc = np.array([0.62, 0.58, 0.40])
    hic = np.array([0.55, 0.53, 0.50])
    snow = np.array([0.95, 0.95, 0.96])
    col = np.where(t < 0.25, lowc + (midc - lowc) * (t / 0.25),
                   np.where(t < 0.75, midc + (hic - midc) * ((t - 0.25) / 0.5), hic + (snow - hic) * ((t - 0.75) / 0.25)))
    sea = np.array([0.16, 0.33, 0.45]) + np.array([0.25, 0.3, 0.25]) * np.clip(1 + h / 40.0, 0, 1)[..., None] ** 3
    c = np.where(land[..., None], col * (0.35 + 0.8 * sh[..., None]), sea)
    return np.clip(c, 0, 1)
