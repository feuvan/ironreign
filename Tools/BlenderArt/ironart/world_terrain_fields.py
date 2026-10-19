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
    hills       rolling 20-60 m hill chains along the hill strokes (:func:`range_relief`)
    mountains   RANGES along the mountain strokes (:func:`range_relief`): a continuous meandering
                crest with summits and cols (150-180 m), spurs and V side valleys from an
                anisotropic |noise| field in crest coordinates (they run downhill and never cut
                the crest), shoulder knobs, crags, a foothill apron; ends taper into foothills;
                saddles where roads and passes cross; eased down over a long domain-warped
                falloff around every city (:meth:`World.city_keep`: cities sit in open basins)
    rivers      meandered, deflected around city pads, sources and confluences kept out of the
                pads, tributaries snapped onto their main river; monotonic bed profiles to the
                sea / lakes, channels 2-4 m below the banks, narrow gorges where a river cuts a
                range
    lakes       flat basins at (surface - 1 m) with soft shores
    pads        flat where the city model stands (``PAD_FLAT``), then a long gaussian feather on a
                warped distance (``PAD_FEATHER``): no visible disc; never over the shore
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
#: radius (m) kept exactly flat for the city model (half its footprint + 8 m) and the gaussian
#: feather length (m) of the blend back into the land
PAD_FLAT = {1: 26.0, 2: 42.0, 3: 66.0}
PAD_FEATHER = 75.0

PARAMS = {
    "seed": 1212,
    # coast
    "coast_warp": 30.0, "coast_warp_scale": 230.0, "coast_detail": 14.0,
    "shelf_depth": 2.6, "shelf_width": 24.0, "sea_floor": -40.0, "sea_slope_width": 300.0,
    # plains
    "plain_coast": 1.4, "plain_inland": 10.0, "plain_rise": 520.0, "plain_roll": 2.0,
    # hills
    "hill_height": 66.0,
    # mountains
    "mtn_base": 140.0, "mtn_per_width": 0.6, "mtn_ridge_scale": 150.0, "mtn_peak": 179.0,
    # rivers
    "river_bank": 3.0, "river_meander": 1.0,
    # erosion: droplets per 2 m cell of relief
    "erosion_droplets": 0.0,
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


def vnoise_box(full_shape, box, cell, seed, octaves=1, gain=0.5, lacunarity=2.0):
    """:func:`vnoise`-style fractal value noise defined on ``full_shape`` but evaluated only in
    ``box`` = (x0, y0, x1, y1) (pixels): a crop is bit-identical to the same window of the full
    evaluation.  Normalised with fixed constants (bicubic lattice std 0.814), zero mean, ~unit
    std."""
    from PIL import Image
    h, w = full_shape
    x0, y0, x1, y1 = box
    rng = np.random.default_rng(seed)
    acc = np.zeros((y1 - y0, x1 - x0), np.float32)
    amp, tot = 1.0, 0.0
    c = float(cell)
    for o in range(octaves):
        cs = max(c, 1.0)
        gh, gw = int(math.ceil(h / cs)) + 4, int(math.ceil(w / cs)) + 4
        lat = rng.standard_normal((gh, gw)).astype(np.float32)
        oh, ow = int(round(gh * cs)), int(round(gw * cs))
        oy = int(rng.integers(0, max(1, int(cs * 2))))
        ox = int(rng.integers(0, max(1, int(cs * 2))))
        sx, sy = gw / ow, gh / oh
        bx = ((ox + x0) * sx, (oy + y0) * sy, (ox + x1) * sx, (oy + y1) * sy)
        big = np.asarray(Image.fromarray(lat, "F").resize((x1 - x0, y1 - y0), Image.BICUBIC, box=bx),
                         np.float32)
        acc += amp * big
        tot += amp * amp
        amp *= gain
        c /= lacunarity
    return acc / (0.814 * math.sqrt(tot))


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


def _chaikin_coast(poly, iters=3):
    """Round the corners of a land polygon (Chaikin) but keep map-border edges straight, so the
    coastline has no polygon kinks while the land still meets the map edges."""
    pts = np.asarray(poly, np.float64)
    for _ in range(iters):
        out = []
        n = len(pts)
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            if _on_border(a, b):
                out.append(a)
                continue
            out.append(0.75 * a + 0.25 * b if not _on_border(pts[i - 1], a) else a)
            out.append(0.25 * a + 0.75 * b if not _on_border(b, pts[(i + 2) % n]) else b)
        pts = np.array(out)
    return resample(np.vstack([pts, pts[:1]]), 6.0)[:-1]


def _on_border(a, b, eps=1.0):
    for k, lim in ((0, 0.0), (0, float(MAP_W)), (1, 0.0), (1, float(MAP_H))):
        if abs(a[k] - lim) < eps and abs(b[k] - lim) < eps:
            return True
    return False


# ---------------------------------------------------------------------------------------------
# erosion
# ---------------------------------------------------------------------------------------------
def erode_droplets(h, spawn, n_droplets, seed, unit=100.0, batch=8000, steps=56, inertia=0.06,
                   capacity=5.0, min_capacity=0.002, erode_speed=0.32, deposit_speed=0.28,
                   evaporate=0.022, gravity=4.0, max_step=0.004, log=None):
    """Vectorised droplet hydraulic erosion (after H. T. Beyer 2015 / S. Lague) on a height grid.

    ``h`` metres (any grid), ``spawn`` >= 0 weights where droplets start, ``unit`` metres per
    normalised height unit (sets the slope scale the parameters see).  Erosion uses a 3x3 brush,
    deposition goes to the 4 bilinear corners.  Deterministic for ``seed``."""
    H, W = h.shape
    g = (np.asarray(h, np.float64) / unit).ravel().copy()
    rng = np.random.default_rng(seed)
    cdf = np.cumsum(np.asarray(spawn, np.float64).ravel())
    if cdf[-1] <= 0:
        return np.asarray(h, np.float32)
    bx = np.array([-1, 0, 1, -1, 0, 1, -1, 0, 1])
    by = np.array([-1, -1, -1, 0, 0, 0, 1, 1, 1])
    bw = np.array([1, 2, 1, 2, 4, 2, 1, 2, 1], np.float64)
    bw /= bw.sum()
    done = 0
    while done < n_droplets:
        n = min(batch, n_droplets - done)
        done += n
        idx = np.searchsorted(cdf, rng.random(n) * cdf[-1])
        py = (idx // W).astype(np.float64) + rng.random(n)
        px = (idx % W).astype(np.float64) + rng.random(n)
        np.clip(px, 1.0, W - 2.001, out=px)
        np.clip(py, 1.0, H - 2.001, out=py)
        dx = np.zeros(n)
        dy = np.zeros(n)
        vel = np.ones(n)
        water = np.ones(n)
        sed = np.zeros(n)
        alive = np.ones(n, bool)
        for _ in range(steps):
            ix = px.astype(np.int64)
            iy = py.astype(np.int64)
            fx = px - ix
            fy = py - iy
            i00 = iy * W + ix
            h00, h10, h01, h11 = g[i00], g[i00 + 1], g[i00 + W], g[i00 + W + 1]
            gx = (h10 - h00) * (1 - fy) + (h11 - h01) * fy
            gy = (h01 - h00) * (1 - fx) + (h11 - h10) * fx
            hc = (h00 * (1 - fx) + h10 * fx) * (1 - fy) + (h01 * (1 - fx) + h11 * fx) * fy
            dx = dx * inertia - gx * (1 - inertia)
            dy = dy * inertia - gy * (1 - inertia)
            nrm = np.sqrt(dx * dx + dy * dy)
            still = nrm < 1e-12
            alive &= ~still
            nrm = np.where(still, 1.0, nrm)
            dx /= nrm
            dy /= nrm
            npx = px + dx
            npy = py + dy
            alive &= (npx >= 1.0) & (npx < W - 2.0) & (npy >= 1.0) & (npy < H - 2.0)
            npx = np.clip(npx, 1.0, W - 2.001)
            npy = np.clip(npy, 1.0, H - 2.001)
            jx = npx.astype(np.int64)
            jy = npy.astype(np.int64)
            gx2 = npx - jx
            gy2 = npy - jy
            j00 = jy * W + jx
            hn = ((g[j00] * (1 - gx2) + g[j00 + 1] * gx2) * (1 - gy2)
                  + (g[j00 + W] * (1 - gx2) + g[j00 + W + 1] * gx2) * gy2)
            dh = hn - hc
            cap = np.maximum(-dh * vel * water * capacity, min_capacity)
            depo_m = (sed > cap) | (dh > 0)
            dep = np.where(dh > 0, np.minimum(dh, sed), (sed - cap) * deposit_speed)
            dep = np.where(depo_m & alive, np.maximum(dep, 0.0), 0.0)
            ero = np.minimum((cap - sed) * erode_speed, -dh)
            ero = np.where(~depo_m & alive, np.maximum(ero, 0.0), 0.0)
            sed = sed + ero - dep
            # deposition: bilinear corners of the old position; erosion: 3x3 brush around it
            ii = np.concatenate([i00, i00 + 1, i00 + W, i00 + W + 1]
                                + [i00 + oy * W + ox for ox, oy in zip(bx, by)])
            ww = np.concatenate([dep * (1 - fx) * (1 - fy), dep * fx * (1 - fy), dep * (1 - fx) * fy,
                                 dep * fx * fy] + [-ero * wk for wk in bw])
            delta = np.bincount(ii, weights=ww, minlength=H * W)
            # droplets of one batch move in parallel and do not see each other's changes:
            # bound the change per cell and step so crowded channels cannot run away
            np.clip(delta, -max_step, max_step, out=delta)
            g += delta
            vel = np.sqrt(np.maximum(vel * vel + dh * gravity, 0.0))
            water *= (1.0 - evaporate)
            px, py = npx, npy
            if not alive.any():
                break
        if log:
            log("[world] erosion %d / %d droplets" % (done, n_droplets))
    return (g.reshape(H, W) * unit).astype(np.float32)


def thermal(h, talus=0.9, rate=0.25, iters=8, cell=1.0):
    """Talus relaxation: material above the repose slope slides to the lower neighbours."""
    a = np.asarray(h, np.float32).copy()
    lim = talus * cell
    for _ in range(iters):
        delta = np.zeros_like(a)
        for sy, sx in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            nb = np.roll(np.roll(a, sy, 0), sx, 1)
            diff = a - nb - lim
            move = np.where(diff > 0, diff * rate * 0.25, 0.0)
            delta -= move
            delta += np.roll(np.roll(move, -sy, 0), -sx, 1)
        a += delta
    return a


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
# relief helpers
# ---------------------------------------------------------------------------------------------
def smax(a, b, k):
    """Smooth maximum (rounded valley floors where two ridge flanks meet), width ~1/k metres.
    The rounding fades out where either side is ~0, so empty ground stays exactly 0."""
    m = np.maximum(a, b)
    lo = np.clip(np.minimum(a, b) * 0.5, 0.0, 1.0)
    return m + lo * np.log1p(np.exp(-k * np.abs(a - b))) / k


def RL_smin(a, b, k):
    """Polynomial smooth minimum (band ``k``)."""
    m = np.minimum(a, b)
    g = np.clip(1.0 - np.abs(a - b) / k, 0.0, 1.0)
    return m - g * g * (0.25 * k)


def fast_blur(a, sigma):
    """Gaussian-like blur for any sigma in O(N): three box passes per axis (cumulative sums)."""
    a = np.asarray(a, np.float32)
    if sigma <= 0:
        return a
    w = int(round(math.sqrt(4.0 * sigma * sigma + 1.0)))
    r = max(1, w // 2)
    out = a
    for axis in (0, 1):
        for _ in range(3):
            out = _box1d(out, r, axis)
    return out


def _box1d(a, r, axis):
    b = np.moveaxis(a, axis, 0)
    n = b.shape[0]
    p = np.concatenate([np.repeat(b[:1], r + 1, 0), b, np.repeat(b[-1:], r, 0)], 0)
    c = np.cumsum(p, axis=0, dtype=np.float64)
    out = (c[2 * r + 1:2 * r + 1 + n] - c[:n]) / (2 * r + 1)
    return np.moveaxis(out.astype(np.float32), 0, axis)


#: range shapes (metres).  ``a`` = flank fall-off length of the crest (also sets the range width:
#: the massif reaches ~2.2 a from the crest, foothills ~3 a).  Spurs are ridged noise stretched
#: across the crest (feature ``spur_u`` along the crest x ``spur_v`` down the flank), so they
#: run downhill from a continuous crest and side valleys open between them.
RANGE = {
    "mountain": dict(peak=158.0, peak_per_w=0.2, a_per_w=1.0, a_min_per_peak=0.48, power=1.25,
                     crest_noise=(0.80, 0.16, 0.08), summit_scale=(150.0, 50.0), spur_u=0.9,
                     spur_v=2.0, spur_depth=0.74, crag=0.045, foot=32.0, foot_reach=2.4, meander=0.2,
                     extend=0.55, knobs=0.22),
    "hill": dict(peak=64.0, peak_per_w=0.0, a_per_w=0.8, a_min_per_peak=0.0, power=1.8,
                 crest_noise=(0.70, 0.22, 0.10), summit_scale=(120.0, 46.0), spur_u=1.0,
                 spur_v=1.8, spur_depth=0.35, crag=0.0, foot=12.0, foot_reach=1.9, meander=0.25,
                 extend=0.5, knobs=0.15),
}


def range_relief(stroke, kind, seed, p=None):
    """Relief of one hill or mountain stroke in its own window.

    Returns ``(sy, sx, height, core_env[, foot_env])`` (``foot_env`` for mountains only).
    The stroke is smoothed, meandered and extended past its ends so the range tapers into
    foothills instead of ending in a round cap; along the crest the height varies with summits
    and cols; across it the profile falls as ``exp(-(q / a) ** power)``; spurs and valleys
    (anisotropic ridged multifractal in crest coordinates, domain warped) dissect the flanks
    but never the crest line itself."""
    rc = RANGE[kind]
    w = float(stroke["width"])
    peak = rc["peak"] + rc["peak_per_w"] * w
    a = max(rc["a_per_w"] * w, rc["a_min_per_peak"] * peak)
    pts = smooth_line(resample(stroke["points"], 4.0), 7.0)
    pts = extend(pts, start=rc["extend"] * a, end=rc["extend"] * a)
    pts = meander(pts, rc["meander"] * a, seed + 1, step=4.0, fade=a)
    pts = smooth_line(pts, 3.0)
    R = 3.4 * a + 20.0
    sy, sx, org = window(pts, R, master_shape())
    shp = (sy.stop - sy.start, sx.stop - sx.start)
    d, t, side = polyline_field(pts, R, want_t=True, shape=shp, want_side=True, origin=org)
    ok = np.isfinite(d)
    # arc parameter blurred more the farther from the crest: on the outside of a bend the
    # nearest point is one vertex for a whole wedge and raw t would draw straight streaks
    t0 = np.where(ok, t, 0.0).astype(np.float32)
    wok = ok.astype(np.float32)
    us = []
    for sg in (8.0, 0.5 * a, 1.2 * a):
        num, den = fast_blur(t0, sg), fast_blur(wok, sg)
        us.append(np.where(den > 1e-3, num / np.maximum(den, 1e-3), 0.0))
    dd0 = np.where(ok, d, 1e5)
    m1 = T.smoothstep(0.15 * a, 0.8 * a, dd0)
    m2 = T.smoothstep(0.9 * a, 2.2 * a, dd0)
    u = (us[0] * (1 - m1) + us[1] * m1) * (1 - m2) + us[2] * m2
    u = u.astype(np.float32)
    sv = gaussian(np.where(ok, side, 0.0), 4.0)
    d = np.where(ok, d, 1e5).astype(np.float32)
    v = d * np.where(sv >= 0, 1.0, -1.0).astype(np.float32)
    L = float(arclen(pts)[-1])
    ys, xs = np.mgrid[sy, sx].astype(np.float32)
    # crest height: summits and cols along the range, tapering at both ends
    c0, c1, c2 = rc["crest_noise"]
    s1, s2 = rc["summit_scale"]
    n1 = T.perlin_at(u / s1, np.full_like(u, 0.37), seed + 2)
    n2 = T.perlin_at(u / s2, np.full_like(u, 0.71), seed + 3)
    te = rc["extend"] * a + 0.9 * a
    taper = T.smoothstep(0.0, te, u) * T.smoothstep(L, L - te, u)
    hc = peak * (c0 + c1 * n1 + c2 * n2) * taper
    # profile across the crest (rounded over ~4 m)
    q = np.sqrt(v * v + 16.0) - 4.0
    prof = np.exp(-(q / a) ** rc["power"])
    # spurs / side valleys
    wu = 0.32 * a * T.fbm_at(xs, ys, 1.4 * a, 3, seed=seed + 4)
    wv = 0.25 * a * T.fbm_at(xs, ys, 1.4 * a, 3, seed=seed + 5)
    lu, lv = rc["spur_u"] * a, rc["spur_v"] * a
    # |noise| creases = sharp V valleys, rounded spurs between them; a second octave cuts
    # side gullies into the spurs (branching)
    uu, vv = u + wu, (v + wv) * (lu / lv)
    n1_ = T.perlin_at(uu / lu, vv / lu, seed + 6)
    n2_ = T.perlin_at(uu / (0.45 * lu) + 3.1, vv / (0.45 * lu) - 1.7, seed + 9)
    n3_ = T.perlin_at(uu / (0.2 * lu) - 2.3, vv / (0.2 * lu) + 0.9, seed + 10)
    s1 = np.sqrt(n1_ * n1_ + 0.004) - 0.063          # |n| with a rounded valley floor
    s2 = np.sqrt(n2_ * n2_ + 0.004) - 0.063
    s3 = np.sqrt(n3_ * n3_ + 0.004) - 0.063
    spur = (np.clip(s1 / 0.5, 0, 1) ** 0.8 * (0.42 + 0.58 * np.clip(s2 / 0.5, 0, 1) ** 0.8)
            * (0.72 + 0.28 * np.clip(s3 / 0.5, 0, 1)))
    # knobs: the spurs rise into secondary summits on their way down
    knob = 1.0 + rc["knobs"] * T.perlin_at(uu / (0.7 * lu) + 7.7, (v + wv) / (0.55 * a), seed + 11) \
        * T.smoothstep(0.2 * a, 0.7 * a, np.abs(v))
    depth = rc["spur_depth"] * T.smoothstep(0.05 * a, 0.8 * a, np.abs(v))
    body = hc * prof * (1.0 - depth * (1.0 - spur)) * knob
    if rc["crag"] > 0:
        crag = T.ridged_at(xs, ys, scale=16.0, octaves=2, seed=seed + 7, sharpness=1.6) - 0.35
        body = body * (1.0 + rc["crag"] * crag * T.smoothstep(0.25, 0.6, prof))
    # foothill apron (billowy lumps), reaching a little past the crest taper
    lump = 1.0 - np.abs(T.fbm_at(xs + 0.6 * wu, ys + 0.6 * wv, 0.9 * a, 3, seed=seed + 8))
    tf = T.smoothstep(0.0, 0.8 * te, u) * T.smoothstep(L, L - 0.8 * te, u)
    fr = rc["foot_reach"] * a
    foot = rc["foot"] * np.exp(-(q / fr) ** 2) * (0.3 + 0.7 * lump ** 1.5) * tf
    hgt = smax(body, foot, 0.25)
    fade = T.smoothstep(R, 0.82 * R, d)
    hgt = (hgt * fade).astype(np.float32)
    core = (np.exp(-(q / (1.15 * a)) ** 2) * taper * fade).astype(np.float32)
    if kind == "hill":
        return sy, sx, hgt, core
    footenv = (np.exp(-(q / (2.6 * a)) ** 2) * tf * fade).astype(np.float32)
    return sy, sx, hgt, core, footenv


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
            ring = _chaikin_coast(poly, 3)
            inside = np.maximum(inside, polygon_inside([tuple(q) for q in ring], self.shape, ss=1))
            for a, b in zip(ring, np.roll(ring, -1, axis=0)):
                if not _on_border(a, b):
                    segs.append((tuple(a), tuple(b)))
        d = segment_distance_full(segs, self.shape)
        sd = np.where(inside > 0.5, d, -d)
        # organic coastline: big bays/headlands + small coves (warp only near the coast)
        n = (self.p["coast_warp"] * self.noise(p["coast_warp_scale"], 3, 11)
             + p["coast_detail"] * self.noise(70.0, 3, 12)
             + 5.0 * self.noise(24.0, 2, 13) + 1.6 * self.noise(7.0, 2, 14))
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
        floor = -(p["shelf_depth"] * (1.0 - np.exp(-dsea / p["shelf_width"]))
                  + (abs(p["sea_floor"]) - p["shelf_depth"])
                  * T.smoothstep(p["shelf_width"] * 0.4, p["sea_slope_width"], dsea) ** 1.25)
        floor = floor + 1.2 * self.noise(60.0, 3, 24) * T.smoothstep(10, 60, dsea)
        # shore: from the waterline the land rises ~9 % (beaches) before joining the plains
        shore = 0.09 * din + 0.6 * T.smoothstep(0.0, 30.0, din) * (0.5 + 0.5 * self.noise(40.0, 2, 25))
        land_h = shore + (base - shore) * T.smoothstep(6.0, 48.0, din)
        h = np.where(self.f["land0"], np.maximum(land_h, 0.02), np.minimum(floor, -0.02))
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
        """Hills and mountain RANGES along the scenario strokes as ridge networks
        (:mod:`ironart.world_terrain_relief`): a continuous crest with summits and cols, spurs
        and sub-spurs running down from it with V valleys and side gullies between them, a
        foothill apron; rolling hill chains built the same way with round profiles.  Saddles where
        roads and passes cross; ridges stop short of the cities, and around every city the land
        may rise only gently (:meth:`city_cap`), so a city sits on open ground at the foot of
        the hills, never in a crater."""
        from . import world_terrain_relief as RL
        p = self.p
        cityd, _ = self.city_distance()
        self.f["city_d"] = cityd
        road_d = self._road_corridor_distance()
        self.f["road_d0"] = road_d
        roads, passes = [], []
        for r in self.sc["roads"]:
            a, b = self.sc["cities"][r["a"]], self.sc["cities"][r["b"]]
            seg = ((a["x"], a["y"]), (b["x"], b["y"]))
            if r.get("kind") == "pass":
                passes.append(seg)
            elif r.get("kind") == "road":
                roads.append(seg)

        def clear(size):
            return PAD_FLAT[size] + 25.0
        rivers = [np.asarray(r["points"], float) for r in self.m["rivers"]]
        self.ranges = [RL.build_range(s_, "mountain", k, self.seed + 500 + 37 * k, self.cities, clear,
                                      roads, passes, rivers) for k, s_ in enumerate(self.m["mountains"])]
        self.hill_ranges = [RL.build_range(s_, "hill", k, self.seed + 600 + 41 * k, self.cities, clear,
                                           roads, passes, rivers) for k, s_ in enumerate(self.m["hills"])]
        mtn, mlev, mrd = RL.rasterize(self.ranges, self.shape, seed=self.seed + 5)
        hills, hlev, hrd = RL.rasterize(self.hill_ranges, self.shape, seed=self.seed + 6)
        mtn = RL.detail(mtn, self.xs, self.ys, "mountain", self.seed + 77)
        hills = RL.detail(hills, self.xs, self.ys, "hill", self.seed + 78)
        foot = np.zeros(self.shape, np.float32)
        for rg in self.ranges + self.hill_ranges:
            foot = np.maximum(foot, RL.foothills(rg, self.xs, self.ys, self.shape,
                                                 self.seed + 900 + 13 * rg.index + (50 if rg.kind == "hill" else 0)))
        lift = RL.smax(RL.smax(mtn, hills, 12.0), foot, 14.0)
        # a gentle domain warp bends every straight spur and gully line
        m = lift > 0.05
        rows, cols = np.nonzero(m.any(1))[0], np.nonzero(m.any(0))[0]
        y0, y1 = max(0, rows[0] - 12), min(self.shape[0], rows[-1] + 13)
        x0, x1 = max(0, cols[0] - 12), min(self.shape[1], cols[-1] + 13)
        X, Y = self.xs[y0:y1, x0:x1], self.ys[y0:y1, x0:x1]
        wx = X + 8.0 * T.fbm_at(X, Y, 48.0, 3, seed=self.seed + 81)
        wy = Y + 8.0 * T.fbm_at(X, Y, 48.0, 3, seed=self.seed + 82)
        warped = lift.copy()
        warped[y0:y1, x0:x1] = sample(lift, wx, wy)
        lift = warped
        if self.p["erosion_droplets"] > 0:
            lift = self._erode_lift(lift)
        lift = lift * T.smoothstep(-6.0, 40.0, self.f["sd"])
        h = self.f["base"] + lift
        # islands: a wooded central hill on each small island
        lumps = 0.5 + 0.5 * T.fbm_at(self.xs, self.ys, 60.0, 3, seed=self.seed + 42)
        for poly in self.m["land"][1:]:
            cx = float(np.mean([q[0] for q in poly]))
            cy = float(np.mean([q[1] for q in poly]))
            r = 0.5 * max(np.ptp([q[0] for q in poly]), np.ptp([q[1] for q in poly]))
            dd = np.hypot(self.xs - cx, self.ys - cy)
            isl = np.exp(-(dd / (0.55 * r)) ** 2) * (0.6 + 0.4 * lumps)
            h = h + (12.0 + 0.16 * r) * isl * T.smoothstep(-2.0, 25.0, self.f["sd"])
        # soft ceiling: summits land at 160-179 m, nothing clips flat
        knee = p["mtn_peak"] - 26.0
        h = np.where(h > knee, knee + 26.0 * np.tanh((h - knee) / 26.0), h)
        h = self.city_cap(h)
        land = self.f["land0"]
        self.f["h_pre"] = np.where(land, h, self.f["base"]).astype(np.float32)
        # envelopes for the rivers, the painter and the trees
        self.f["mtn_h"] = mtn.astype(np.float32)
        self.f["hill_h"] = hills.astype(np.float32)
        self.f["foot_h"] = foot.astype(np.float32)
        self.f["mtn_core"] = T.smoothstep(25.0, 90.0, fast_blur(mtn, 6.0)).astype(np.float32)
        self.f["mtn_foot"] = T.smoothstep(3.0, 30.0, fast_blur(np.maximum(mtn, foot), 10.0)).astype(np.float32)
        self.f["hill_env"] = T.smoothstep(4.0, 22.0, fast_blur(hills, 8.0)).astype(np.float32)
        self.f["ridge_lev"] = np.where(mlev >= 0, mlev, np.where(hlev >= 0, hlev + 3, -1)).astype(np.int8)
        self.f["ridge_d"] = np.minimum(mrd, hrd).astype(np.float32)
        self.f["city_keep"] = np.ones(self.shape, np.float32)
        self.log("[world] relief: %d mountain ridges, %d hill ridges; max %.1f m, hills max %.1f m, "
                 "p99.9 mountains %.1f m" % (sum(len(r.ridges) for r in self.ranges),
                                             sum(len(r.ridges) for r in self.hill_ranges),
                                             float(self.f["h_pre"].max()), float(hills.max()),
                                             float(np.percentile(self.f["h_pre"][self.f["mtn_core"] > 0.5], 99.9))))

    def _erode_lift(self, lift, k=2):
        """Droplet hydraulic erosion of the relief on a ``k`` m grid (no talus step: the ranges
        are meant to be steep)."""
        lk = box_down(lift, k)
        spawn = np.where(lk > 6.0, lk, 0.0) ** 0.6
        n = int((lk > 6.0).sum() * self.p["erosion_droplets"])
        e = erode_droplets(lk, spawn, n, self.seed + 77, unit=100.0, inertia=0.3, erode_speed=0.3,
                           deposit_speed=0.15, steps=56, max_step=0.008, capacity=5.0, log=None)
        delta = gaussian(e - lk, 0.5)
        up = smooth_up(delta, (lk.shape[0] * k, lk.shape[1] * k))
        out = lift.copy()
        out[:up.shape[0], :up.shape[1]] += up
        self.log("[world] erosion: %d droplets, change p1/p99 %.1f / %.1f m"
                 % (n, float(np.percentile(delta, 1)), float(np.percentile(delta, 99))))
        return np.maximum(out, 0.0)

    def city_cap(self, h):
        """Around every city the land may rise only gently from the city's ground level (a smooth
        minimum with a cone of slope ~0.3 on a domain-warped distance): a city sits on open
        ground or a gentle bench at the foot of the hills, never in a round crater."""
        hs = fast_blur(h, 10.0)
        warp = (16.0 * T.fbm_at(self.xs, self.ys, 90.0, 3, seed=self.seed + 71)
                + 6.0 * T.fbm_at(self.xs, self.ys, 28.0, 2, seed=self.seed + 72))
        base = self.f["base"]
        self.city_levels = {}
        for (key, cx, cy, s) in self.cities:
            rf = PAD_FLAT[s]
            reach = rf + 420.0
            x0, x1 = int(max(0, cx - reach)), int(min(MAP_W + 1, cx + reach + 1))
            y0, y1 = int(max(0, cy - reach)), int(min(MAP_H + 1, cy + reach + 1))
            sl = (slice(y0, y1), slice(x0, x1))
            dd = np.hypot(self.xs[sl] - cx, self.ys[sl] - cy)
            ring = (dd >= 0.5 * rf) & (dd < rf + 30.0)
            b0 = float(np.median(base[sl][ring]))
            terr = self.sc["cities"][key].get("terrain", "plains")
            allow = 26.0 if terr in ("mountains", "hills") else 7.0
            level = min(float(np.median(hs[sl][ring])), b0 + allow)
            self.city_levels[key] = level
            slope = 0.40 if terr in ("mountains", "hills") else 0.28
            dw = np.maximum(dd + warp[sl] * T.smoothstep(0.3 * rf, rf + 20.0, dd), 0.0)
            x = np.maximum(dw - rf - 8.0, 0.0)
            cap = level + 1.5 + slope * x + 0.004 * x * x
            h[sl] = RL_smin(h[sl], cap, 10.0)
        return h

    def _road_corridor_distance(self):
        """Distance to the straight city-to-city road lines (river routes excluded); the passes'
        own distance goes to ``f['pass_d']`` (they cut real saddles through the ranges)."""
        d = np.full(self.shape, np.inf, np.float32)
        dp = np.full(self.shape, np.inf, np.float32)
        for r in self.sc["roads"]:
            if r.get("kind") == "river":
                continue
            a, b = self.sc["cities"][r["a"]], self.sc["cities"][r["b"]]
            pts = np.array([(a["x"], a["y"]), (b["x"], b["y"])], np.float64)
            sy, sx, org = window(pts, 160.0, self.shape)
            shp = (sy.stop - sy.start, sx.stop - sx.start)
            dd = polyline_field(pts, 160.0, want_t=False, shape=shp, origin=org)
            d[sy, sx] = np.minimum(d[sy, sx], dd)
            if r.get("kind") == "pass":
                dp[sy, sx] = np.minimum(dp[sy, sx], dd)
        self.f["pass_d"] = dp
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
            prof = basin + (level + 1.6 - basin) * rise + 0.12 * np.maximum(-sd - 12.0, 0.0)
            prof = np.where(sd > 0, basin, prof)
            low = np.minimum(h, prof)
            h = h + (low - h) * T.smoothstep(-110.0, -45.0, sd)
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
            # a source inside a city keep-out starts just outside it instead
            pts = c["pts"]
            while len(pts) > 8 and any(math.hypot(pts[0][0] - cx, pts[0][1] - cy) < clr(sz) + 4.0
                                       for (_k, cx, cy, sz) in self.cities):
                pts = pts[1:]
            c["pts"] = deflect(pts, self.cities, clr)
            parent = ends[c["index"]]
            if parent is not None:
                main = next(o for o in courses if o["index"] == parent)
                c["pts"] = snap_onto(c["pts"], self._confluence(c["pts"], main["pts"], clr),
                                     overrun=0.5 * main["width"])
                c["pts"] = deflect(c["pts"], self.cities, clr)
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

    def _confluence(self, trib, main, clr):
        """The part of the main river a tributary may join: its points clear of every city
        keep-out (a confluence never lies under a city model)."""
        ok = np.ones(len(main), bool)
        for (_k, cx, cy, sz) in self.cities:
            ok &= np.hypot(main[:, 0] - cx, main[:, 1] - cy) > clr(sz) + 6.0
        if ok.all():
            return main
        end = np.asarray(trib[-1])
        idx = np.nonzero(ok)[0]
        j = int(idx[np.argmin(np.hypot(main[idx, 0] - end[0], main[idx, 1] - end[1]))])
        lo, hi = j, j
        while lo > 0 and ok[lo - 1]:
            lo -= 1
        while hi < len(main) - 1 and ok[hi + 1]:
            hi += 1
        return main[lo:hi + 1]

    def carve_rivers(self):
        """Bed profiles (monotonic to the sea / lake / parent river) and channel carving."""
        h = self.f["h_pre"].copy()
        bank = self.p["river_bank"]
        # valley half-width beyond the banks: narrow on the plains, wide gorges in the ranges
        wv = (42.0 + 6.0 * self.f["hill_env"] - 24.0 * self.f["mtn_core"]).astype(np.float32)
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
            reach = 200.0
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
            wvm = wv[m] + np.minimum(2.0 * excess, 40.0) * (1.0 - 0.7 * self.f["mtn_core"][m])
            g = T.smoothstep(0.0, 1.0, (dd - hw_g - bankw) / wvm)
            valley = top + excess * g
            prof = np.where(dd < hw_g + bankw, chan, valley)
            hn = np.minimum(hv, prof)
            # containment: the banks never drop below the water (no spills on low ground)
            band = (dd > hw_g) & (dd < hw_g + bankw + 3.0)
            hn = np.where(band, np.maximum(hn, bed_g + np.minimum(dep, 1.2)
                                           * T.smoothstep(hw_g, hw_g + bankw, dd)), hn)
            hn = np.where(self.f["lake_sd"][m] > 1.0, hv, hn)     # no channels on lake floors
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
        """City pads, invisible in shape: the ground under the city model (``PAD_FLAT``: half the
        model's footprint + a few metres, on a domain-warped, non-circular outline) becomes a
        plane fitted to the surrounding land (its gentle regional tilt is kept, at most 1.5 %),
        and the plane fades back into the untouched land over a long gaussian feather
        (``PAD_FEATHER``).  Carved river channels and the shore are left alone."""
        h = self.f["h_riv"].copy()
        hs = fast_blur(h, 10.0)
        warp = (0.20 * T.fbm_at(self.xs, self.ys, 34.0, 2, seed=self.seed + 73)
                + 0.08 * T.fbm_at(self.xs, self.ys, 12.0, 2, seed=self.seed + 74))
        rd = np.where(np.isfinite(self.f["river_d"]), self.f["river_d"] - self.f["river_hw"], 1e4)
        self.pads = []
        for (key, cx, cy, s) in self.cities:
            rf, fe = PAD_FLAT[s], PAD_FEATHER
            reach = rf + 3.2 * fe
            x0, x1 = int(max(0, cx - reach)), int(min(MAP_W + 1, cx + reach + 1))
            y0, y1 = int(max(0, cy - reach)), int(min(MAP_H + 1, cy + reach + 1))
            sl = (slice(y0, y1), slice(x0, x1))
            X, Y = self.xs[sl] - cx, self.ys[sl] - cy
            dd = np.hypot(X, Y)
            # weighted least-squares plane through the smoothed land around the site
            wfit = np.exp(-(dd / (rf + 45.0)) ** 2) * (self.f["sd"][sl] > 8.0) * (rd[sl] > 6.0)
            A = np.stack([np.ones_like(X), X, Y], -1).reshape(-1, 3).astype(np.float64)
            wv = wfit.reshape(-1).astype(np.float64)
            zv = hs[sl].reshape(-1).astype(np.float64)
            M = A.T @ (A * wv[:, None]) + np.diag([1e-6, 1.0, 1.0])
            c0, gx, gy = np.linalg.solve(M, A.T @ (wv * zv))
            g = math.hypot(gx, gy)
            if g > 0.015:
                gx, gy = gx * 0.015 / g, gy * 0.015 / g
            near_r = (dd < rf + 60) & (rd[sl] < 2.0)
            if near_r.any():
                c0 = max(c0, float(self.f["river_bed"][sl][near_r].max()) + 3.2)
            c0 = max(c0, 3.0)
            plane = (c0 + gx * X + gy * Y).astype(np.float32)
            dw = dd * (1.0 + warp[sl])
            wgt = np.exp(-(np.maximum(dw - rf, 0.0) / fe) ** 2)
            wgt *= T.smoothstep(reach, reach - 30.0, dd)
            wgt *= T.smoothstep(1.0, 9.0, rd[sl])
            # never over the sea or the shore: the coastline stays where the map draws it
            wgt *= T.smoothstep(4.0, 24.0, self.f["sd"][sl])
            # low frequencies blend to the plane over the long feather; the fine relief is only
            # removed under the model itself (so no smooth disc shows in the land's grain)
            prot = T.smoothstep(1.0, 9.0, rd[sl]) * T.smoothstep(4.0, 24.0, self.f["sd"][sl])
            core = T.smoothstep(rf + 24.0, rf - 2.0, dw) * prot
            h[sl] = h[sl] - wgt * (hs[sl] - plane) - core * (h[sl] - hs[sl])
            self.pads.append({"key": key, "x": cx, "y": cy, "size": s, "radius": PAD_RADIUS[s], "flat": rf,
                              "level": round(float(c0), 2), "tilt": round(math.hypot(gx, gy) * 100, 2)})
        self.f["h"] = np.clip(h, MIN_H, MAX_H).astype(np.float32)
        self.log("[world] pads: " + ", ".join("%s %.1f m (%.1f %%)" % (p["key"], p["level"], p["tilt"])
                                               for p in self.pads))

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
                               "width": 4.0 if kind == "road" else 3.2})

    # -- 8. forests ------------------------------------------------------------------------------
    def build_forests(self):
        """Forest density 0..1: organic lobed shapes around the scenario circles plus copses."""
        rng = np.random.default_rng(self.seed + 400)
        wx, wy = self.warp(18.0, 40.0, 401)
        dens = np.zeros(self.shape, np.float32)
        big = []
        for k, fz in enumerate(self.m["forests"]):
            cx, cy, r = fz["x"], fz["y"], fz["r"]
            ang = np.arctan2(wy - cy, wx - cx)
            # lobed outline: radius varies with angle (3-5 lobes) + small satellite groves
            lob = (0.18 * np.sin(3 * ang + rng.uniform(0, 6.3)) + 0.10 * np.sin(5 * ang + rng.uniform(0, 6.3))
                   + 0.06 * np.sin(8 * ang + rng.uniform(0, 6.3)))
            rr = r * (1.22 + lob)
            dd = np.hypot(wx - cx, wy - cy)
            dens = np.maximum(dens, T.smoothstep(rr + 14.0, rr - 10.0, dd))
            big.append((cx, cy, r))
            for _ in range(int(rng.integers(3, 6))):
                a = rng.uniform(0, 2 * np.pi)
                rd = r * rng.uniform(1.05, 1.45)
                sx, sy = cx + rd * np.cos(a), cy + rd * np.sin(a)
                sr = r * rng.uniform(0.18, 0.32)
                dd = np.hypot(wx - sx, wy - sy)
                dens = np.maximum(dens, T.smoothstep(sr + 8, sr - 6, dd))
        # copses: small groves where trees grow in a painting - along the rivers and lake shores,
        # on the hill flanks and the mountain feet - not sprinkled evenly over the plain
        h = self.f["h"]
        cityd = self.f["city_d"]
        rdist = np.where(np.isfinite(self.f["river_d"]), self.f["river_d"], 1e4)
        road_d = self.f.get("road_d0", np.full(self.shape, 1e4, np.float32))
        pref = (0.9 * np.exp(-((rdist - 70.0) / 55.0) ** 2)
                + 0.8 * np.exp(-((self.f["lake_sd"] + 60.0) / 40.0) ** 2)
                + 0.9 * T.smoothstep(0.15, 0.5, self.f["hill_env"]) * (1 - T.smoothstep(0.6, 0.9, self.f["hill_env"]))
                + 0.7 * T.smoothstep(0.2, 0.5, self.f["mtn_foot"]) * (1 - T.smoothstep(0.1, 0.4, self.f["mtn_core"]))
                + 0.06)
        copses = []
        tries = 0
        while len(copses) < 38 and tries < 20000:
            tries += 1
            x, y = rng.uniform(30, MAP_W - 30), rng.uniform(30, MAP_H - 30)
            ix, iy = int(x), int(y)
            if rng.random() > pref[iy, ix] / 1.2:
                continue
            if (h[iy, ix] < 2.0 or h[iy, ix] > 70.0 or cityd[iy, ix] < 150 or rdist[iy, ix] < 28
                    or road_d[iy, ix] < 30 or self.f["desert"][iy, ix] > 0.2 or dens[iy, ix] > 0.05
                    or self.f["lake_sd"][iy, ix] > -25):
                continue
            if any((x - a_) ** 2 + (y - b_) ** 2 < 130 ** 2 for a_, b_, _ in copses):
                continue
            copses.append((x, y, rng.uniform(10.0, 22.0)))
        for (x, y, r) in copses:
            # a grove: an elongated main clump plus 1-3 smaller lobes
            lobes = [(x, y, r, rng.uniform(0, np.pi), rng.uniform(1.2, 1.9))]
            for _ in range(int(rng.integers(1, 4))):
                a_ = rng.uniform(0, 2 * np.pi)
                rr = r * rng.uniform(0.4, 0.7)
                lobes.append((x + (r + 0.3 * rr) * np.cos(a_), y + (r + 0.3 * rr) * np.sin(a_), rr,
                              rng.uniform(0, np.pi), rng.uniform(1.0, 1.5)))
            R = 2.2 * r + 30
            x0, x1 = int(max(0, x - R)), int(min(MAP_W, x + R))
            y0, y1 = int(max(0, y - R)), int(min(MAP_H, y + R))
            sx_, sy_ = wx[y0:y1 + 1, x0:x1 + 1], wy[y0:y1 + 1, x0:x1 + 1]
            for (lx, ly, lr, la, le) in lobes:
                ca_, sa_ = np.cos(la), np.sin(la)
                du = ((sx_ - lx) * ca_ + (sy_ - ly) * sa_) / le
                dv = (-(sx_ - lx) * sa_ + (sy_ - ly) * ca_) * le ** 0.5
                sub = np.hypot(du, dv)
                dens[y0:y1 + 1, x0:x1 + 1] = np.maximum(dens[y0:y1 + 1, x0:x1 + 1],
                                                        T.smoothstep(lr + 7, lr - 5, sub))
        # glades: a few open clearings inside the big woods (never at their edge)
        gl = T.smoothstep(0.62, 0.9, 0.5 + 0.5 * T.fbm_at(wx, wy, 34.0, 2, seed=self.seed + 405))
        inner = T.smoothstep(0.9, 1.0, dens)
        dens = dens * (1.0 - 0.85 * gl * inner)
        # no wood on the city sites, in the river channels or in the lakes
        for (_k, cx, cy, sz) in self.cities:
            r0 = PAD_FLAT[sz]
            x0, x1 = int(max(0, cx - r0 - 70)), int(min(MAP_W + 1, cx + r0 + 71))
            y0, y1 = int(max(0, cy - r0 - 70)), int(min(MAP_H + 1, cy + r0 + 71))
            dd = np.hypot(self.xs[y0:y1, x0:x1] - cx, self.ys[y0:y1, x0:x1] - cy)
            dens[y0:y1, x0:x1] *= T.smoothstep(r0 + 12.0, r0 + 55.0, dd)
        rgap = np.where(np.isfinite(self.f["river_d"]), self.f["river_d"] - self.f["river_hw"], 1e4)
        dens *= T.smoothstep(1.0, 7.0, rgap) * T.smoothstep(-1.0, -8.0, self.f["lake_sd"])
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

    # -- cache ---------------------------------------------------------------------------------
    def save(self, path):
        import pickle
        with open(path, "wb") as f:
            pickle.dump({"p": self.p, "f": self.f, "rivers": self.rivers, "lakes": self.lakes,
                         "roads": self.roads, "pads": self.pads, "copses": self.copses,
                         "ranges": self.ranges, "hill_ranges": self.hill_ranges,
                         "city_levels": self.city_levels, "groves": getattr(self, "groves", []),
                         "times": getattr(self, "times", {})}, f, protocol=4)

    @classmethod
    def load(cls, path, sc=None, log=print):
        import pickle
        with open(path, "rb") as f:
            d = pickle.load(f)
        w = cls(sc or load_scenario(), d["p"], log)
        for k in ("f", "rivers", "lakes", "roads", "pads", "copses", "ranges", "hill_ranges",
                  "city_levels", "groves", "times"):
            setattr(w, k, d.get(k))
        return w

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
    return preview_rgb_from_h(h, float(scale))


def preview_rgb_from_h(h, cell=1.0):
    """Hypsometric tint x hillshade of a height grid with ``cell`` metres per sample."""
    sh = hillshade(h, z=1.0 / cell)
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
