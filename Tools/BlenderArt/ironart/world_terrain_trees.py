"""World Terrain family - tree instances for Content/Data/Art3D/Terrain/Trees.json (numpy only).

DESIGN.md 12.2: ``[{"t": "pine|broad|bamboo", "x": m, "y": m, "s": scale, "r": yawDegrees}, ...]``,
under ~25k instances, none within 25 m of a city point (we keep whole city pads clear) and none on
roads or water.  ``s`` multiplies the native size of SM_Tree_Pine / Broad / Bamboo (18-35 m tall);
the spacing follows their crowns (:data:`CROWN_R`).

Where trees grow (a painting's trees: dense clumped woods, groves, lines along the water):
    forests      the scenario forest circles (lobed, with satellite groves) and the copses:
                 a closed canopy (crowns overlap by ~40 %) with a few clearings, thinning to
                 scattered outliers at the edge
    south        y > 900: bamboo groves in the humid southern woods and along the rivers
    north        y < 500 and the mountains: pines dominate
    hills        groves of 3-15 trees on the hill ranges, open ground between them
    mountains    pine groves on the flanks below the ~125 m tree line, on spurs and shoulders
    riparian     broken lines of trees along the plain rivers and lake shores
    lone trees   a few single trees and pairs in the open countryside
"""

import math

import numpy as np

from . import terrain as T
from . import world_terrain_fields as F

#: visual crown radius (m) of SM_Tree_* at s = 1 (ArtSource/Models: Broad ~22 m wide,
#: Pine ~23 m with open pads, Bamboo ~14 m)
CROWN_R = {"broad": 10.5, "pine": 9.5, "bamboo": 6.2}
#: centre spacing in crown radii by category: < 2 means overlapping crowns
SPACING = {"forest": 1.15, "grove": 1.3, "mountain": 1.35, "hill": 1.4, "riparian": 1.5,
           "lone": 2.4}
#: keep clear of the city sites (m): the flat pad plus a margin (contract: >= 25 m)
CITY_CLEAR = {1: 44.0, 2: 60.0, 3: 82.0}


def road_distance(world, radius=16.0):
    """Distance (m) from the edge of the painted road tracks (inf beyond ``radius``)."""
    d = np.full(world.shape, np.inf, np.float32)
    for r in world.roads:
        pts = np.asarray(r["pts"], np.float64)
        sy, sx, org = F.window(pts, radius, world.shape)
        shp = (sy.stop - sy.start, sx.stop - sx.start)
        dd = F.polyline_field(pts, radius, want_t=False, shape=shp, origin=org)
        dd = dd - 0.5 * r["width"]
        d[sy, sx] = np.minimum(d[sy, sx], dd)
    return d


def _fields_master(fieldm):
    if fieldm is None:
        return None
    fm = F.box_down(np.asarray(fieldm, np.float32), 2)
    out = np.zeros((F.MAP_H + 1, F.MAP_W + 1), np.float32)
    out[:fm.shape[0], :fm.shape[1]] = fm
    return out


def scatter(world, fieldm=None, seed=None, log=print, budget=24000, **_):
    """Returns a list of tree dicts (map metres) and per-category counts."""
    f = world.f
    seed = (seed if seed is not None else world.seed) + 7000
    rng = np.random.default_rng(seed)
    H, W = world.shape
    xs, ys = world.xs, world.ys
    h = f["h"]
    hs = F.fast_blur(h, 1.5)
    gy, gx = np.gradient(hs)
    slope = np.sqrt(gx * gx + gy * gy)
    form = (h - F.fast_blur(h, 20.0)) / 10.0             # + spurs / shoulders, - gullies
    rd = road_distance(world)
    river_edge = np.where(np.isfinite(f["river_d"]), f["river_d"] - f["river_hw"], 1e4)
    clump = 0.5 + 0.5 * T.fbm_at(xs, ys, 34.0, 3, seed=seed + 1)
    clearing = 0.5 + 0.5 * T.fbm_at(xs, ys, 22.0, 2, seed=seed + 5)
    bamboo_n = 0.5 + 0.5 * T.fbm_at(xs, ys, 45.0, 2, seed=seed + 2)
    pine_n = 0.5 + 0.5 * T.fbm_at(xs, ys, 60.0, 2, seed=seed + 3)
    forest = f["forest"]
    city_ok = np.ones(world.shape, bool)
    for (_k, cx, cy, size) in world.cities:
        city_ok &= np.hypot(xs - cx, ys - cy) >= CITY_CLEAR[size]
    fm = _fields_master(fieldm)
    in_field = (fm >= 0.25) if fm is not None else np.zeros(world.shape, bool)
    eligible = ((h > 1.5) & (f["sd"] > 10.0) & (river_edge > 5.0) & (f["lake_sd"] < -6.0)
                & (rd > 4.5) & city_ok & (slope < 1.25) & (h < 128.0))
    mtn = f["mtn_foot"]
    # ---- acceptance probability per category
    p_forest = 0.97 * T.smoothstep(0.25, 0.65, forest) * (1.0 - 0.85 * T.smoothstep(0.74, 0.86, clearing))
    p_edge = 0.32 * T.smoothstep(0.06, 0.25, forest) * (1 - T.smoothstep(0.25, 0.5, forest)) \
        * T.smoothstep(0.45, 0.7, clump)
    p_mtn = (0.85 * T.smoothstep(0.15, 0.45, mtn) * T.smoothstep(18.0, 30.0, h)
             * (1.0 - T.smoothstep(108.0, 126.0, h)) * T.smoothstep(0.48, 0.6, clump + 0.12 * np.clip(form, -1, 1))
             * (1.0 - T.smoothstep(0.85, 1.2, slope)))
    p_hill = (0.75 * T.smoothstep(0.2, 0.55, f["hill_env"]) * T.smoothstep(0.5, 0.62, clump)
              * T.smoothstep(10.0, 22.0, h) * (1 - T.smoothstep(0.3, 0.5, mtn)))
    p_rip = (0.55 * T.smoothstep(18.0, 7.0, river_edge) * T.smoothstep(0.44, 0.58, clump)
             * (1 - f["mtn_core"]) + 0.4 * T.smoothstep(-18.0, -9.0, f["lake_sd"])
             * T.smoothstep(0.44, 0.58, clump))
    p_lone = 0.012 * (forest < 0.05) * (f["desert"] < 0.25) * T.smoothstep(0.55, 0.75, clump)
    cats = [("forest", p_forest), ("grove", p_edge), ("mountain", p_mtn), ("hill", p_hill),
            ("riparian", p_rip), ("lone", p_lone)]
    cell = 3.0
    gy_n, gx_n = int(H // cell), int(W // cell)
    jx = (np.arange(gx_n)[None, :] + rng.random((gy_n, gx_n))) * cell
    jy = (np.arange(gy_n)[:, None] + rng.random((gy_n, gx_n))) * cell
    ix = np.clip(jx.astype(int), 0, W - 1)
    iy = np.clip(jy.astype(int), 0, H - 1)
    el = eligible[iy, ix] & ~in_field[iy, ix]
    u = rng.random((gy_n, gx_n))
    chosen = np.full((gy_n, gx_n), -1, np.int8)
    acc = np.zeros((gy_n, gx_n), np.float32)
    for k, (_name, p) in enumerate(cats):
        pk = np.minimum(np.asarray(p, np.float32)[iy, ix], 1.0 - acc)
        hit = (u >= acc) & (u < acc + pk) & el & (chosen < 0)
        chosen[hit] = k
        acc += pk
    sel = np.nonzero(chosen >= 0)
    px, py = jx[sel], jy[sel]
    cat = chosen[sel]
    # forests first (densest packing), then the others; random order inside a category
    order = np.lexsort((rng.random(len(px)), cat))
    px, py, cat = px[order], py[order], cat[order]
    out = []
    counts = {}
    grid = {}
    gcell = 8.0
    for x, y, c in zip(px, py, cat):
        name = cats[c][0]
        i, j = int(x), int(y)
        hh = float(h[j, i])
        south = y > 900.0
        north = y < 500.0
        high = hh > 38.0 or mtn[j, i] > 0.45
        if name == "mountain" or (high and name in ("forest", "grove", "hill")):
            t = "pine" if (pine_n[j, i] > 0.22 or hh > 55.0) else "broad"
        elif name == "riparian":
            t = "bamboo" if (south and bamboo_n[j, i] > 0.5) else "broad"
        elif name == "lone":
            t = "pine" if (north and pine_n[j, i] > 0.55) else "broad"
        elif name == "hill":
            t = "pine" if (pine_n[j, i] > (0.45 if north else 0.62)) else "broad"
        else:   # forest / grove
            if south and bamboo_n[j, i] > 0.56:
                t = "bamboo"
            elif north:
                t = "pine" if pine_n[j, i] > 0.36 else "broad"
            else:
                t = "pine" if pine_n[j, i] > 0.68 else "broad"
        if t == "broad":
            s = rng.uniform(0.62, 0.9)
        elif t == "pine":
            s = rng.uniform(0.62, 0.95) * (1.0 - 0.25 * T.smoothstep(45.0, 125.0, hh))
        else:
            s = rng.uniform(0.8, 1.08)
        if name == "forest":
            s *= 0.86 + 0.18 * float(min(1.0, forest[j, i]))      # edge trees a little smaller
        rmin = SPACING[name] * CROWN_R[t] * s
        gx_, gy_ = int(x // gcell), int(y // gcell)
        ok = True
        for ddx in (-2, -1, 0, 1, 2):
            for ddy in (-2, -1, 0, 1, 2):
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
    """The Trees.json payload (drops the private category field), sorted north to south so
    the file diffs and streams in a stable order."""
    rows = [{k: v for k, v in t.items() if not k.startswith("_")} for t in trees]
    rows.sort(key=lambda t: (round(t["y"] / 50.0), t["x"], t["y"]))
    return rows


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
