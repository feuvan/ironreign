"""Relief-map terrain: numpy heightfields, biome albedo painting and the Blender terrain build.

The RTK IX world-map look = a real 3D relief lit from the top-left, with a hand-painted albedo
(soft natural colours, no photographic noise) and tiny 3D tree clusters for forests.

Pure-numpy part (works in Blender's python and the system python3):
    perlin_at / fbm_at / ridged_at  gradient noise evaluated at arbitrary coordinates (domain warp)
    polyline_distance               distance field to a polyline (rivers, mountain spines, roads)
    meander                         noisy resampled polyline (natural river courses)
    slope / normals                 from a heightfield
    paint_albedo                    biome painter -> sRGB float image (see BIOME_DEFAULTS)

Blender part (imports bpy lazily):
    build_terrain     heightfield -> displaced grid with the albedo image material
    scatter_forest    3D tree clusters from a forest mask (MeshBuilder)

Conventions: arrays are indexed [row, col] = [y_down, x] like images; coordinates passed to the
noise functions are in *map pixels*; heights are normalised so 0 = sea level, 1 = highest peak.
"""

import math

import numpy as np

# ---------------------------------------------------------------------------------------------
# noise
# ---------------------------------------------------------------------------------------------
_GRAD_N = 256


def _grads(seed):
    rng = np.random.default_rng(seed)
    a = rng.uniform(0, 2 * np.pi, (_GRAD_N, _GRAD_N))
    return np.cos(a).astype(np.float32), np.sin(a).astype(np.float32)


_GCACHE = {}


def perlin_at(x, y, seed=0):
    """2D gradient (Perlin) noise at float coordinate arrays; output roughly in [-1, 1]."""
    g = _GCACHE.get(seed)
    if g is None:
        g = _GCACHE[seed] = _grads(seed)
    gx, gy = g
    x = np.asarray(x, np.float32)
    y = np.asarray(y, np.float32)
    x0 = np.floor(x)
    y0 = np.floor(y)
    fx = x - x0
    fy = y - y0
    ix = x0.astype(np.int64) % _GRAD_N
    iy = y0.astype(np.int64) % _GRAD_N
    ix1 = (ix + 1) % _GRAD_N
    iy1 = (iy + 1) % _GRAD_N

    def d(iy_, ix_, dx, dy):
        return gx[iy_, ix_] * dx + gy[iy_, ix_] * dy

    n00 = d(iy, ix, fx, fy)
    n10 = d(iy, ix1, fx - 1, fy)
    n01 = d(iy1, ix, fx, fy - 1)
    n11 = d(iy1, ix1, fx - 1, fy - 1)
    u = fx * fx * fx * (fx * (fx * 6 - 15) + 10)
    v = fy * fy * fy * (fy * (fy * 6 - 15) + 10)
    return ((n00 + (n10 - n00) * u) * (1 - v) + (n01 + (n11 - n01) * u) * v) * 1.4142


def fbm_at(x, y, scale=64.0, octaves=5, gain=0.5, lacunarity=2.0, seed=0):
    """Fractal Brownian motion of Perlin noise; ``scale`` = feature size in pixels. ~[-1, 1]."""
    acc = np.zeros(np.shape(x), np.float32)
    amp, tot, f = 1.0, 0.0, 1.0 / scale
    for i in range(octaves):
        acc += amp * perlin_at(np.asarray(x) * f + 17.3 * i, np.asarray(y) * f - 9.1 * i, seed + i)
        tot += amp
        amp *= gain
        f *= lacunarity
    return acc / tot


def ridged_at(x, y, scale=64.0, octaves=5, gain=0.5, lacunarity=2.1, seed=0, sharpness=2.0):
    """Ridged multifractal (sharp mountain crests). Output ~[0, 1]."""
    acc = np.zeros(np.shape(x), np.float32)
    amp, tot, f = 1.0, 0.0, 1.0 / scale
    weight = np.ones(np.shape(x), np.float32)
    for i in range(octaves):
        n = 1.0 - np.abs(perlin_at(np.asarray(x) * f + 5.7 * i, np.asarray(y) * f + 3.3 * i, seed + 31 * i))
        n = n ** sharpness
        n *= weight
        weight = np.clip(n * 1.6, 0, 1)
        acc += amp * n
        tot += amp
        amp *= gain
        f *= lacunarity
    return acc / tot


def grid(h, w, scale=1.0):
    """Pixel-centre coordinate arrays (x, y) for an ``h x w`` image, multiplied by ``scale``."""
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    return (xs + 0.5) * scale, (ys + 0.5) * scale


def warp(x, y, amount=20.0, scale=120.0, seed=0):
    """Domain-warp coordinates (organic coastlines and ranges)."""
    return (x + amount * fbm_at(x, y, scale, 3, seed=seed + 101),
            y + amount * fbm_at(x, y, scale, 3, seed=seed + 202))


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, np.float32) - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------------------------------
# polylines
# ---------------------------------------------------------------------------------------------
def meander(points, step=6.0, amount=10.0, scale=60.0, seed=0):
    """Resample a polyline every ``step`` px and push it sideways with 1D noise (rivers)."""
    pts = np.asarray(points, np.float32)
    out = [pts[0]]
    for a, b in zip(pts[:-1], pts[1:]):
        L = float(np.hypot(*(b - a)))
        n = max(1, int(L / step))
        for k in range(1, n + 1):
            out.append(a + (b - a) * k / n)
    out = np.array(out, np.float32)
    t = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(out, axis=0).T))])
    tang = np.gradient(out, axis=0)
    tang /= np.maximum(np.linalg.norm(tang, axis=1, keepdims=True), 1e-6)
    nrm = np.stack([-tang[:, 1], tang[:, 0]], 1)
    off = amount * perlin_at(t / scale, np.full_like(t, 0.5), seed)
    fade = np.minimum(1, np.minimum(t, t[-1] - t) / (2 * step + 1e-6))
    return out + nrm * (off * fade)[:, None]


def polyline_distance(h, w, points, scale=1.0, return_t=False):
    """Distance (px) from every pixel centre to a polyline; optionally the arc parameter 0..1."""
    x, y = grid(h, w, scale)
    pts = np.asarray(points, np.float32)
    best = np.full((h, w), np.inf, np.float32)
    best_t = np.zeros((h, w), np.float32)
    seglen = np.hypot(*np.diff(pts, axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seglen)])
    total = max(cum[-1], 1e-6)
    for i, (a, b) in enumerate(zip(pts[:-1], pts[1:])):
        d = b - a
        L2 = float(d @ d) + 1e-9
        t = np.clip(((x - a[0]) * d[0] + (y - a[1]) * d[1]) / L2, 0, 1)
        px = a[0] + t * d[0] - x
        py = a[1] + t * d[1] - y
        dist = np.sqrt(px * px + py * py)
        m = dist < best
        best = np.where(m, dist, best)
        if return_t:
            best_t = np.where(m, (cum[i] + t * seglen[i]) / total, best_t)
    return (best, best_t) if return_t else best


# ---------------------------------------------------------------------------------------------
# analysis
# ---------------------------------------------------------------------------------------------
def slope(height, px_size=1.0, z_scale=1.0):
    """Slope magnitude (rise / run) of a heightfield."""
    gy, gx = np.gradient(height * z_scale, px_size)
    return np.sqrt(gx * gx + gy * gy)


def resize(arr, size):
    """Bicubic resize of a 2D float array to ``size`` = (w, h) (Pillow 'F' mode)."""
    from PIL import Image
    return np.asarray(Image.fromarray(arr.astype(np.float32), "F").resize(size, Image.BICUBIC),
                      np.float32)


def blur(arr, sigma):
    from . import post
    return post.gaussian(arr, sigma)


# ---------------------------------------------------------------------------------------------
# biome painting
# ---------------------------------------------------------------------------------------------
BIOME_DEFAULTS = {
    "hill_start": 0.10,       # normalised height where lowland turns to hill colour
    "rock_start": 0.30,       # mountain rock begins
    "snow_start": 0.66,       # snow line (with noise +-0.05)
    "beach_px": 2.5,          # sand rim width along the coast
    "shallow_px": 26.0,       # width (px) of the light coastal shallows; deep sea beyond ~4x
    "paint_scale": 90.0,      # size of the hand-painted colour blotches (px)
    "paint_amount": 0.09,     # strength of blotches
    "brush_amount": 0.05,     # strength of the streaky brush-stroke texture
}


def _c(token):
    from . import palette
    return np.array(palette.srgb(token), np.float32)


def _lerp(a, b, t):
    return a + (b - a) * np.asarray(t, np.float32)[..., None]


def paint_albedo(height, land, moisture=None, steppe=None, forest=None, river=None, lake=None,
                 seed=0, params=None):
    """Hand-painted biome albedo (sRGB float HxWx3) for a relief map.

    height    normalised heights (0 sea level .. 1 peak), land only matters
    land      0..1 land mask (anti-aliased coast)
    moisture  0..1 (dry ochre plains -> sage grass); default: noise
    steppe    0..1 sandy steppe/desert mask
    forest    0..1 forest-floor mask (darker green under the 3D trees)
    river     0..1 river water mask (clear blue ribbon), ``lake`` likewise
    """
    p = dict(BIOME_DEFAULTS, **(params or {}))
    h, w = height.shape
    x, y = grid(h, w)
    if moisture is None:
        moisture = 0.5 + 0.5 * fbm_at(x, y, 180, 4, seed=seed + 7)
    paint = fbm_at(x, y, p["paint_scale"], 4, seed=seed + 11)
    brush = fbm_at(x * 0.35, y, p["paint_scale"] * 0.35, 3, seed=seed + 12)  # streaky strokes
    sl = slope(height, 1.0, 60.0)

    plain = _c("plain")
    grass = _c("grass")
    meadow = _c("meadow")
    col = _lerp(plain, grass, smoothstep(0.35, 0.7, moisture))
    col = _lerp(col, meadow, smoothstep(0.55, 0.9, moisture + 0.2 * paint) * 0.5)
    if steppe is not None:
        st = _lerp(_c("steppe"), _c("desert"), smoothstep(0.3, 0.9, 0.5 + 0.5 * paint))
        col = _lerp(col, st, steppe)
    # hills: olive/ochre, mountains: blue-grey rock, snow caps
    hn = height + 0.04 * paint
    col = _lerp(col, _c("hill"), smoothstep(p["hill_start"], p["hill_start"] + 0.15, hn) * 0.75)
    rock = _lerp(_c("mountain"), _c("rock"), smoothstep(-0.3, 0.5, brush))
    rock = _lerp(rock, _c("mountain_dark"), smoothstep(1.0, 2.5, sl) * 0.35)
    col = _lerp(col, rock, smoothstep(p["rock_start"], p["rock_start"] + 0.14, hn))
    sn = p["snow_start"] + 0.05 * fbm_at(x, y, 30, 3, seed=seed + 13)
    snow = smoothstep(sn, sn + 0.07, height) * (1 - 0.6 * smoothstep(1.2, 2.6, sl))
    col = _lerp(col, _c("snow"), snow)
    if forest is not None:
        col = _lerp(col, _c("forest_dark"), np.clip(forest, 0, 1) * 0.85)
    # hand-painted blotches + brush streaks
    col = col * (1 + p["paint_amount"] * paint[..., None] + p["brush_amount"] * brush[..., None])
    # coast: beach rim then sea shallows -> deep
    near_sea = coast_proximity(1 - land, p["beach_px"] * 0.6)
    beach = smoothstep(0.35, 0.8, near_sea) * (height < 0.08)
    col = _lerp(col, _c("beach"), beach * 0.8)
    shallow = coast_proximity(land, p["shallow_px"] * 0.5)
    shallow = np.clip(shallow + 0.12 * fbm_at(x, y, 40, 3, seed=seed + 17), 0, 1)
    sea = _lerp(_c("sea"), _c("sea_shallow"), smoothstep(0.25, 0.9, shallow))
    deep = coast_proximity(land, p["shallow_px"] * 2.0)
    sea = _lerp(_c("sea_deep"), sea, smoothstep(0.02, 0.5, deep))
    sea = sea * (1 + 0.035 * paint[..., None])
    col = _lerp(sea, col, land)
    if lake is not None:
        col = _lerp(col, _c("lake"), lake)
    if river is not None:
        col = _lerp(col, _c("river"), river)
    return np.clip(col, 0, 1)


def coast_proximity(land, sigma):
    """0..1 proximity to land for sea pixels (and vice versa with ``1 - land``): a gaussian of the
    land mask.  Smooth and painterly - used for shallows and beaches instead of a hard distance."""
    from . import post
    return np.clip(post.gaussian((np.asarray(land) > 0.5).astype(np.float32), sigma) * 2.0, 0, 1)


# ---------------------------------------------------------------------------------------------
# Blender build
# ---------------------------------------------------------------------------------------------
def build_terrain(height, albedo_png, size_xy, z_scale, name="Terrain", grid_step=1,
                  roughness=0.9, sea_level=0.0):
    """Displaced grid from ``height`` (normalised; land >= 0, sea clamped to ``sea_level``)
    textured with ``albedo_png`` mapped to the full extent.  Returns the object."""
    from . import geometry, materials
    hh = np.maximum(height[::grid_step, ::grid_step], sea_level)
    mat = materials.image(name + "Albedo", albedo_png, roughness=roughness, specular=0.2)
    return geometry.terrain_grid(name, hh, size_xy[0], size_xy[1], z_scale, mat=mat)


def scatter_forest(mb, mask, size_xy, height_fn, rng, density=0.012, min_dist_px=4.0,
                   tree_px=(3.5, 6.0), leaves=("Foliage", "FoliageDark", "FoliageLight"),
                   pine_ratio=0.25, thresh=0.5):
    """Scatter tiny 3D trees where ``mask`` > ``thresh`` (mask in map pixels, row 0 = north).

    size_xy     terrain size in metres; mask spans it exactly
    height_fn   (px_x, px_y) -> terrain z in metres (to sit trees on the relief)
    density     candidate trees per mask pixel
    tree_px     canopy radius range in map pixels
    """
    from . import geometry
    H, W = mask.shape
    sx, sy = size_xy[0] / W, size_xy[1] / H
    idx = np.argwhere(mask > thresh)
    if len(idx) == 0:
        return 0
    n = int(len(idx) * density)
    placed = []
    cell = {}
    cs = min_dist_px
    for k in rng.sample(range(len(idx)), min(n, len(idx))):
        py, px = idx[k]
        px = px + rng.random()
        py = py + rng.random()
        key = (int(px // cs), int(py // cs))
        ok = True
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for q in cell.get((key[0] + dx, key[1] + dy), ()):
                    if (q[0] - px) ** 2 + (q[1] - py) ** 2 < min_dist_px ** 2:
                        ok = False
                        break
        if not ok:
            continue
        cell.setdefault(key, []).append((px, py))
        placed.append((px, py))
        x = -size_xy[0] / 2 + px * sx
        y = size_xy[1] / 2 - py * sy
        z = height_fn(px, py)
        r = rng.uniform(*tree_px) * sx
        if rng.random() < pine_ratio:
            geometry.tree_pine(mb, (x, y, z), height=r * 3.2, radius=r, rng=rng,
                               leaf=leaves[1 % len(leaves)], tiers=2, detail=0)
        else:
            geometry.tree_broadleaf(mb, (x, y, z), height=r * 2.4, radius=r, rng=rng,
                                    leaf=rng.choice(leaves), blobs=4, detail=0)
    return len(placed)
