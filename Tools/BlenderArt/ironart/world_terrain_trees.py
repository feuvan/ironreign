"""World Terrain family - tree instances for Content/Data/Art3D/Terrain/Trees.json (numpy only).

DESIGN.md 12.2: ``[{"t": "pine|broad|bamboo", "x": m, "y": m, "s": scale, "r": yawDegrees}, ...]``,
under ~25k instances, none within 25 m of a city point (we keep whole city pads clear) and none on
roads or water.  ```s`` multiplies the native size of SM_Tree_Pine / Broad / Bamboo (18-35 m tall); the spacing
follows their measured crowns (:data:`CROWN_R`), so neighbouring crowns overlap by ~20 %.

Where trees grow:
    forests      the scenario forest circles (organic lobes + satellite groves) and plain copses:
                 dense, ~7 m spacing, thinning at the edges
    southern     y > 900: bamboo groves (clustered) mixed into the broadleaf forests and river banks
    north        y < 500 and mountains: pines dominate
    hills        sparse clumps on the hill ranges
    mountains    pine groves on the flanks between ~20 m and the 130 m tree line, not on bare rock
    riparian     loose lines of broadleaf trees along the plain rivers
    lone trees   a few single trees in the open countryside (never inside farm parcels)
"""

import math

import numpy as np

#: visual crown radius (m) of SM_Tree_* at s = 1 (ArtSource/Models: Broad 22 m wide x 23 m tall,
#: Pine 23 x 27 m with open pads, Bamboo 14 x 18.5 m); spacing = SPACING x crown radius x s
CROWN_R = {"broad": 10.5, "pine": 9.5, "bamboo": 6.2}
SPACING = 1.22

from . import terrain as T
from . import world_terrain_fields as F


def road_distance(world, radius=14.0):
    d = np.full(world.shape, np.inf, np.float32)
    for r in world.roads:
        pts = np.asarray(r["pts"], np.float64)
        sy, sx, org = F.window(pts, radius, world.shape)
        shp = (sy.stop - sy.start, sx.stop - sx.start)
        dd = F.polyline_field(pts, radius, want_t=False, shape=shp, origin=org)
        dd = dd - 0.5 * r["width"]
        d[sy, sx] = np.minimum(d[sy, sx], dd)
    return d


def scatter(world, fieldm=None, seed=None, log=print, budget=24000, bankm=None):
    """Returns a list of tree dicts (map metres) and per-category counts."""
    f = world.f
    seed = (seed if seed is not None else world.seed) + 7000
    rng = np.random.default_rng(seed)
    H, W = world.shape
    h, slope = f["h"], f["slope"]
    hs = F.gaussian(h, 1.5)
    gy, gx = np.gradient(hs)
    slope_s = np.sqrt(gx * gx + gy * gy)
    rd = road_distance(world)
    river_edge = np.where(np.isfinite(f["river_d"]), f["river_d"] - f["river_hw"], 1e4)
    xs, ys = world.xs, world.ys
    clump = 0.5 + 0.5 * T.fbm_at(xs, ys, 38.0, 3, seed=seed + 1)
    bamboo_n = 0.5 + 0.5 * T.fbm_at(xs, ys, 28.0, 2, seed=seed + 2)
    pine_n = 0.5 + 0.5 * T.fbm_at(xs, ys, 60.0, 2, seed=seed + 3)
    forest = f["forest"]
    clear_city = np.zeros(world.shape, bool)
    for (_k, cx, cy, size) in world.cities:
        clear_city |= np.hypot(xs - cx, ys - cy) < F.TREE_CITY_CLEAR[size]
    # ---- probability per category, per 4 m cell candidate
    eligible = ((h > 1.2) & (f["sd"] > 8.0) & (river_edge > 4.5) & (f["lake_sd"] < -5.0)
                & (rd > 4.0) & ~clear_city & (slope_s < 1.35) & (h < 132.0))
    in_field = np.zeros(world.shape, bool)
    if fieldm is not None:
        fm = F.box_down(fieldm, 2)                       # texel grid -> master-ish grid
        fmm = np.zeros(world.shape, np.float32)
        fmm[:fm.shape[0], :fm.shape[1]] = fm
        in_field = fmm >= 0.35
    bank = np.zeros(world.shape, np.float32)
    if bankm is not None:
        bk = F.box_down(bankm, 2)
        bank[:bk.shape[0], :bk.shape[1]] = bk
        bank = np.clip(F.gaussian(bank, 1.5) * 3.0, 0, 1)      # 1 m banks -> ~4 m corridors
    rock_like = T.smoothstep(0.75, 1.2, slope_s)
    p_forest = 0.62 * T.smoothstep(0.2, 0.7, forest)
    p_hill = (0.16 * f["hill_env"] ** 1.1 * T.smoothstep(0.5, 0.75, clump) * (forest < 0.25)
              * T.smoothstep(8.0, 20.0, h))
    p_mtn = (0.42 * T.smoothstep(0.1, 0.45, f["mtn_foot"]) * T.smoothstep(16.0, 28.0, h)
             * (1.0 - T.smoothstep(105.0, 128.0, h)) * T.smoothstep(0.48, 0.64, clump)
             * (1.0 - rock_like) * (forest < 0.25))
    p_rip = (0.26 * T.smoothstep(18.0, 6.0, river_edge) * T.smoothstep(0.3, 0.55, clump)
             * (1 - f["mtn_core"]) * (forest < 0.25))
    p_lone = 0.011 * (forest < 0.1) * (f["desert"] < 0.3) * T.smoothstep(0.4, 0.7, clump)
    p_desert_edge = 0.006 * T.smoothstep(0.15, 0.3, f["desert"]) * (1 - T.smoothstep(0.35, 0.5, f["desert"]))
    # avenues: broken lines of trees 6-9 m beside some road stretches (not on passes)
    road_line = np.zeros(world.shape, np.float32)
    for r in world.roads:
        if r["kind"] != "road":
            continue
        pts = np.asarray(r["pts"], np.float64)
        sy, sx, org = F.window(pts, 12.0, world.shape)
        shp = (sy.stop - sy.start, sx.stop - sx.start)
        dd = F.polyline_field(pts, 12.0, want_t=False, shape=shp, origin=org)
        band = np.exp(-((dd - 7.5) / 1.3) ** 2)
        road_line[sy, sx] = np.maximum(road_line[sy, sx], np.where(np.isfinite(dd), band, 0.0))
    avenue = 0.5 + 0.5 * T.fbm_at(xs, ys, 70.0, 2, seed=seed + 4)
    p_road = 1.0 * road_line * T.smoothstep(0.36, 0.5, avenue) * (f["mtn_foot"] < 0.3)
    # hedgerow trees on some of the grassy banks between the farm parcels
    p_hedge = 0.22 * T.smoothstep(0.3, 0.7, bank) * T.smoothstep(0.42, 0.68, clump) * in_field
    no_field = ~in_field
    cats = [("forest", p_forest * no_field), ("hill", p_hill * no_field), ("mountain", p_mtn * no_field),
            ("riparian", p_rip * no_field), ("lone", p_lone * no_field), ("steppe", p_desert_edge * no_field),
            ("hedge", p_hedge), ("avenue", p_road)]
    cell = 4.0
    gy_n, gx_n = int(H // cell), int(W // cell)
    jx = (np.arange(gx_n)[None, :] + rng.random((gy_n, gx_n))) * cell
    jy = (np.arange(gy_n)[:, None] + rng.random((gy_n, gx_n))) * cell
    ix = np.clip(jx.astype(int), 0, W - 1)
    iy = np.clip(jy.astype(int), 0, H - 1)
    el = eligible[iy, ix]
    u = rng.random((gy_n, gx_n))
    chosen = np.full((gy_n, gx_n), -1, np.int8)
    acc = np.zeros((gy_n, gx_n), np.float32)
    for k, (_name, p) in enumerate(cats):
        pk = np.asarray(p, np.float32)[iy, ix] if np.ndim(p) else np.full((gy_n, gx_n), p, np.float32)
        hit = (u >= acc) & (u < acc + pk) & el & (chosen < 0)
        chosen[hit] = k
        acc += pk
    sel = np.nonzero(chosen >= 0)
    px, py = jx[sel], jy[sel]
    cat = chosen[sel]
    order = rng.permutation(len(px))
    px, py, cat = px[order], py[order], cat[order]
    # ---- species and size
    out = []
    counts = {}
    grid = {}
    gcell = 6.0
    for x, y, c in zip(px, py, cat):
        name = cats[c][0]
        i, j = int(x), int(y)
        hh = float(h[j, i])
        south = y > 900.0
        north = y < 520.0
        if name == "mountain":
            t = "pine"
        elif name == "riparian":
            t = "bamboo" if (south and bamboo_n[j, i] > 0.6) else "broad"
        elif name in ("lone", "steppe", "hedge", "avenue"):
            t = "pine" if (north and pine_n[j, i] > 0.6) else "broad"
        elif name == "hill":
            t = "pine" if (pine_n[j, i] + 0.006 * hh > 0.75 or north and pine_n[j, i] > 0.5) else "broad"
        else:   # forest
            if south and bamboo_n[j, i] > 0.62:
                t = "bamboo"
            elif north:
                t = "pine" if pine_n[j, i] > 0.42 else "broad"
            else:
                t = "pine" if (pine_n[j, i] > 0.7 or hh > 40.0) else "broad"
        if t == "broad":
            s = rng.uniform(0.56, 0.86)
        elif t == "pine":
            s = rng.uniform(0.58, 0.9) * (1.0 - 0.22 * T.smoothstep(40.0, 125.0, hh))
        else:
            s = rng.uniform(0.75, 1.05)
        if name == "forest":
            s *= 0.85 + 0.2 * float(forest[j, i])      # edge trees a little smaller
        # spacing: crowns may touch but not stack (bamboo clumps a bit tighter)
        rmin = SPACING * CROWN_R[t] * s
        if name in ("lone", "hill", "mountain", "riparian", "steppe"):
            rmin *= 1.15
        if name in ("hedge", "avenue"):
            s *= 0.85
            rmin *= 1.25 if name == "avenue" else 1.6
        gx_, gy_ = int(x // gcell), int(y // gcell)
        ok = True
        for ddx in (-1, 0, 1):
            for ddy in (-1, 0, 1):
                for (qx, qy, qr) in grid.get((gx_ + ddx, gy_ + ddy), ()):
                    if (qx - x) ** 2 + (qy - y) ** 2 < (0.5 * (rmin + qr)) ** 2:
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                break
        if not ok:
            continue
        grid.setdefault((gx_, gy_), []).append((x, y, rmin))
        out.append({"t": t, "x": round(float(x), 2), "y": round(float(y), 2),
                    "s": round(float(s), 3), "r": round(float(rng.uniform(0, 360)), 1),
                    "_cat": name})
        counts[name] = counts.get(name, 0) + 1
        counts[t] = counts.get(t, 0) + 1
        if len(out) >= budget:
            log("[trees] budget reached")
            break
    log("[trees] %d trees: %s" % (len(out), ", ".join("%s %d" % kv for kv in sorted(counts.items()))))
    return out, counts


def to_json(trees):
    """The Trees.json payload (drops the private category field)."""
    return [{k: v for k, v in t.items() if not k.startswith("_")} for t in trees]


def check(world, trees):
    """QA problems (empty = ok): trees near cities, on water/roads, out of the map."""
    probs = []
    rd = road_distance(world, 8.0)
    f = world.f
    for t in trees:
        x, y = t["x"], t["y"]
        if not (0 <= x <= F.MAP_W and 0 <= y <= F.MAP_H):
            probs.append("tree outside the map at (%.1f, %.1f)" % (x, y))
            continue
        i, j = int(x), int(y)
        for (k, cx, cy, _s) in world.cities:
            if math.hypot(x - cx, y - cy) < 25.0:
                probs.append("tree %.1f m from city %s" % (math.hypot(x - cx, y - cy), k))
        if f["h"][j, i] < 0.5:
            probs.append("tree in the water at (%.1f, %.1f)" % (x, y))
        rv = f["river_d"][j, i] - f["river_hw"][j, i]
        if np.isfinite(rv) and rv < 2.0:
            probs.append("tree in a river at (%.1f, %.1f)" % (x, y))
        if f["lake_sd"][j, i] > 0:
            probs.append("tree in a lake at (%.1f, %.1f)" % (x, y))
        if rd[j, i] < 1.0:
            probs.append("tree on a road at (%.1f, %.1f)" % (x, y))
    return probs
