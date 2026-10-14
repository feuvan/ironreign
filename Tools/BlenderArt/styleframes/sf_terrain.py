"""Style frame (a): 512x320 crop of the relief world map (RTK IX look).

    Tools/BlenderArt/render.sh Tools/BlenderArt/styleframes/sf_terrain.py [out_dir]

Contents: sandy steppe (top-left), a snow-capped mountain range with foothills, ochre/sage plains,
a forest cluster of tiny 3D trees, a river ribbon running to the sea, beach, coastal shallows and
deep teal-indigo sea.  1 map pixel = 1 cm in the scene; the heightfield and the painted albedo are
computed at 2x (the render resolution) by :mod:`ironart.terrain`.

QA (asserted): plains hue 70-90 (sage, not khaki), steppe ~#C7AC76, lit / shadow forest canopy
values and hue, snow 3-6 % of the range, no near-navy shadows, every river reaches the sea.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import numpy as np  # noqa: E402

from ironart import geometry as geo, materials as M, post, recipes, scene  # noqa: E402
from ironart import terrain as T  # noqa: E402

W, H = 512, 320            # target pixels
SS = 2                     # supersample (fields and render)
PX = 0.01                  # metres per target pixel
Z = 0.55                   # metres for normalised height 1.0 on the ranges (relief exaggeration)
LOW = 0.42 / 0.55          # lowland relief is kept at the old 0.42 m scale
SEED = 3


def make_fields():
    """All fields at render resolution (2x), coordinates in target pixels."""
    h, w = H * SS, W * SS
    x, y = T.grid(h, w, 1.0 / SS)
    wx, wy = T.warp(x, y, 18.0, 110.0, SEED)
    # --- land / sea: coast runs top-right -> bottom-right with a bay and a headland
    coast_x = (412 + 30 * np.sin(y / 55.0) - 0.18 * (y - 160) + 26 * T.fbm_at(wx, wy, 70, 4, seed=SEED)
               - 34 * np.exp(-((wy - 262) / 26.0) ** 2) + 22 * np.exp(-((wy - 175) / 20.0) ** 2))
    land_soft = T.smoothstep(-1.2, 1.2, coast_x - x)
    island = T.smoothstep(26, 22, np.hypot((wx - 478) * 1.1, wy - 62) + 6 * T.fbm_at(x, y, 20, 3, seed=9))
    land = np.maximum(land_soft, island)
    # --- ONE continuous range along a spine (upper middle): broad ridged massif, no t-modulation
    #     (raw polyline t jumps across bend bisectors and drew a straight cliff line before)
    spine = T.meander([(30, 175), (110, 120), (200, 92), (300, 70), (370, 36)], 6, 12, 80, SEED)
    d_sp = T.polyline_distance(h, w, spine, 1.0 / SS)
    width = 42 + 6 * T.fbm_at(x, y, 90, 2, seed=4)
    rng_mask = np.exp(-(d_sp / width) ** 2)
    ridges = T.ridged_at(wx, wy, 70, 4, 0.5, seed=SEED + 5, sharpness=1.5)
    massif = 0.85 + 0.15 * T.fbm_at(x, y, 140, 2, seed=5)
    mountains = rng_mask * (0.3 + 0.8 * ridges) * massif
    # a lower, rounded range in the south-west (no snow)
    spine2 = T.meander([(-10, 300), (40, 268), (95, 262), (135, 290)], 6, 8, 50, SEED + 3)
    d2 = T.polyline_distance(h, w, spine2, 1.0 / SS)
    mountains += np.exp(-(d2 / 24.0) ** 2) * (0.2 + 0.35 * ridges) * 0.7
    foot = np.exp(-(d_sp / 80.0) ** 2) * (0.5 + 0.5 * T.fbm_at(wx, wy, 40, 4, seed=SEED + 6)) * 0.12
    hills_c = np.exp(-(np.hypot(x - 170, y - 275) / 45.0) ** 2) * (0.5 + 0.5 * T.fbm_at(wx, wy, 30, 3, seed=7)) * 0.12
    hills_c += np.exp(-(np.hypot(x - 345, y - 120) / 35.0) ** 2) * (0.5 + 0.5 * T.fbm_at(wx, wy, 26, 3, seed=8)) * 0.11
    plains = 0.012 + 0.010 * T.fbm_at(x, y, 60, 4, seed=SEED + 8)
    height = (plains + foot + hills_c) * LOW + mountains
    # --- rivers: main river from the range to the bay, tributary snapped onto it
    river_pts = T.meander([(222, 128), (238, 158), (262, 200), (318, 228), (360, 250), (398, 262),
                           (416, 266)], 5, 9, 45, SEED + 2)
    d_rv, t_rv = T.polyline_distance(h, w, river_pts, 1.0 / SS, return_t=True)
    t_rv = T.smooth_t(t_rv, d_rv, 4.0)
    L = float(np.hypot(*np.diff(river_pts, axis=0).T).sum())
    flare = T.smoothstep(1.0 - 12.0 / L, 1.0, t_rv) * 1.7          # mouth: 6.4 -> ~9.8 px
    half_w = 1.0 + 2.2 * t_rv + flare
    river = T.smoothstep(half_w + 0.5, half_w - 0.5, d_rv)
    trib = T.meander([(105, 200), (150, 222), (205, 230), (262, 212)], 5, 7, 40, SEED + 9)
    trib = T.join_tributary(trib, river_pts, overrun=2.0)
    d_tr, t_tr = T.polyline_distance(h, w, trib, 1.0 / SS, return_t=True)
    tw = 0.8 + 0.8 * T.smooth_t(t_tr, d_tr, 4.0)
    river = np.maximum(river, T.smoothstep(tw + 0.5, tw - 0.5, d_tr))
    river = river * T.smoothstep(0.3, 0.7, land)
    # 1 px darker bank line just outside the water
    edge_main = np.clip(1.0 - np.abs(d_rv - (half_w + 0.6)) / 0.7, 0, 1)
    edge_trib = np.clip(1.0 - np.abs(d_tr - (tw + 0.6)) / 0.7, 0, 1)
    bank = np.maximum(edge_main, edge_trib) * (1 - river) * (land > 0.5)
    # valleys carve the lowland only (a carve inside the range made a black notch)
    valley = np.exp(-(np.minimum(d_rv, d_tr) / 7.0) ** 2) * (1 - T.smoothstep(0.2, 0.6, rng_mask))
    height = height * (1 - 0.65 * valley) - 0.004 * river
    height = np.where(land > 0.5, np.maximum(height, 0.004), -0.02)
    # clamp the height gradient (no spike vertices / one-pixel cliffs)
    height = np.minimum(height, post.gaussian(height, 1.0) + 0.06)
    # --- biomes
    steppe = T.smoothstep(150, 70, np.hypot(wx * 0.9, wy * 1.3) + 25 * T.fbm_at(x, y, 50, 3, seed=11))
    moisture = 0.5 + 0.5 * T.fbm_at(x, y, 150, 4, seed=12) + 0.35 * valley - 0.3 * steppe
    # forest: elongated lobes following the river south bank + a north-bank lobe, domain-warped
    # ragged edge (+-8 px), then 6-10 small copses on the plains
    fx, fy = T.warp(x, y, 8.0, 18.0, SEED + 21)
    core = np.zeros_like(x)
    for (cx, cy, ang, a, b) in [(245, 248, 0.25, 48, 20), (300, 255, 0.45, 40, 17),
                                (210, 262, 0.05, 30, 15), (330, 205, 0.55, 26, 13)]:
        ca, sa = np.cos(ang), np.sin(ang)
        u = (fx - cx) * ca + (fy - cy) * sa
        v = -(fx - cx) * sa + (fy - cy) * ca
        core = np.maximum(core, np.exp(-((u / a) ** 2 + (v / b) ** 2)))
    forest = T.smoothstep(0.42, 0.58, core + 0.22 * T.fbm_at(x, y, 12, 3, seed=13))
    rng = np.random.default_rng(SEED + 40)
    copses = []
    tries = 0
    while len(copses) < 8 and tries < 400:
        tries += 1
        cx, cy = rng.uniform(40, 400), rng.uniform(30, 300)
        iy, ix = int(cy * SS), int(cx * SS)
        if (land[iy, ix] < 0.9 or height[iy, ix] > 0.08 or steppe[iy, ix] > 0.3
                or d_rv[iy, ix] < 10 or d_tr[iy, ix] < 10 or core[iy, ix] > 0.05
                or any(np.hypot(cx - qx, cy - qy) < 40 for qx, qy, _ in copses)):
            continue
        copses.append((cx, cy, rng.uniform(3.5, 6.5)))
    for (cx, cy, r) in copses:
        forest = np.maximum(forest, T.smoothstep(r + 1.0, r - 1.0, np.hypot(fx - cx, fy - cy)))
    forest = forest * (1 - river) * (1 - bank) * (land > 0.5) * (height < 0.18)
    return dict(height=height.astype(np.float32), land=land, river=river, bank=bank, steppe=steppe,
                moisture=np.clip(moisture, 0, 1), forest=forest, mountains=rng_mask,
                copses=copses)


def qa_terrain(img, f, albedo):
    """Measured palette / structure checks (asserted)."""
    q = post.QA("terrain")
    land1 = T.resize(f["land"], (W, H)) > 0.5
    # open plains: lowland land pixels away from forest, rivers, steppe and hills
    def down(a):
        return T.resize(a, (W, H))
    hn = down(f["height"] / max(1e-6, f["height"].max()))
    plains = (land1 & (down(f["forest"]) < 0.02) & (down(f["river"]) < 0.02)
              & (down(f["steppe"]) < 0.05) & (hn < 0.05) & (down(f["mountains"]) < 0.05))
    pm = post.region_mean(img, mask=plains)
    print("[ironart] plains mean #%02X%02X%02X over %d px" % (tuple(int(round(c)) for c in pm)
                                                          + (int(plains.sum()),)))
    q.hue("open plains (mask)", pm, 75, 85)
    q.color("steppe patch", post.region_mean(img, (10, 10, 50, 40)), "#C7AC76", 14)
    fm = T.resize(f["forest"], (W, H)) > 0.8
    lum = post.luma8(img)
    lit = fm & (lum >= np.percentile(lum[fm], 75))
    shd = fm & (lum <= np.percentile(lum[fm], 25))
    q.hue("lit forest canopy", post.region_mean(img, mask=lit), 80, 115)
    q.range("lit canopy luma", float(lum[lit].mean()), 80, 125)
    q.range("shadow canopy luma", float(lum[shd].mean()), 30, 70)
    mt = T.resize(f["mountains"], (W, H)) > 0.5
    snow_frac = float(((lum > 205) & mt).sum() / max(1, mt.sum()))
    q.range("snow share of the range (%)", 100 * snow_frac, 3.0, 6.0)
    dark = (lum < 60) & mt
    q.max("near-navy shadow share of range (%)", 100 * float(dark.sum() / max(1, mt.sum())), 3.0)
    probs = T.check_rivers(f["river"], f["land"])
    q.range("rivers not reaching the sea", float(len(probs)), 0, 0)
    for pr in probs:
        print("[ironart] QA terrain", pr)
    del land1, albedo
    return q


def main():
    out = scene.args()[0] if scene.args() else os.path.join(os.environ["IRONART_OUT"], "styleframes")
    os.makedirs(out, exist_ok=True)
    times = {}
    scene.reset(seed=SEED)
    rng = random.Random(SEED)
    with scene.timer("fields", times):
        f = make_fields()
        hn = f["height"] / max(1e-6, f["height"].max())
        # snow line from the range's own height distribution: caps on the top ~15 % of the range
        # (shadowed flanks, noise and slope shedding leave 3-6 % reading as white)
        snow_start = float(np.percentile(hn[f["mountains"] > 0.5], 85))
        albedo = T.paint_albedo(hn, f["land"], f["moisture"], f["steppe"], f["forest"],
                                f["river"], seed=SEED, bank=f["bank"], px=SS,
                                params={"snow_start": snow_start})
        print("[ironart] snow line", round(snow_start, 3))
        alb_path = os.path.join(out, "terrain_albedo.png")
        a4 = np.dstack([albedo, np.ones(albedo.shape[:2], np.float32)])
        post.save(a4, alb_path, opaque=True)
    recipes.setup("map", W, H)
    with scene.timer("build", times):
        T.build_terrain(np.maximum(hn, 0.0), alb_path, (W * PX, H * PX), Z * f["height"].max())
        mats = {"Foliage": M.foliage("Foliage", "#52703F", vary=0.14, translucency=0.05),
                "FoliageDark": M.foliage("FoliageDark", "#405E3A", vary=0.14, translucency=0.05),
                "FoliageLight": M.foliage("FoliageLight", "#64804A", vary=0.14, translucency=0.05),
                "Trunk": M.principled("Trunk", "trunk")}
        for k in ("Foliage", "FoliageDark", "FoliageLight"):
            M.paint(mats[k], 0.3, 0.8, 0.1)
        mb = geo.MeshBuilder()
        hh, ww = hn.shape
        zmax = Z * f["height"].max()

        def zf(px_, py_):
            return float(hn[min(hh - 1, int(py_ * SS)), min(ww - 1, int(px_ * SS))]) * zmax

        fmask = f["forest"][::SS, ::SS]
        n = T.scatter_forest(mb, fmask, (W * PX, H * PX), zf, rng, density=0.1, min_dist_px=3.0,
                             tree_px=(1.8, 2.6), leaves=("Foliage", "FoliageDark", "FoliageLight"))
        trees = mb.build("Forest", mats)
        print("[ironart] trees", n, "faces", len(trees.data.polygons), "copses", len(f["copses"]))
    cam = recipes.camera("map", width=W * PX)
    recipes.light("map", cam)
    recipes.paint("map")
    raw = os.path.join(out, "terrain_raw_%dx.png" % SS)
    times["render"] = scene.render(raw)
    with scene.timer("post", times):
        land1 = T.resize(f["land"], (W, H))
        img = recipes.finish("map", raw, paper_mask=np.clip(land1, 0, 1), seed=SEED)
        # coast ink line (DESIGN.md: "coast ink line"), drawn crisp at final resolution
        edge = post.gaussian((land1 > 0.5).astype(np.float32), 0.7)
        line = np.clip(1.0 - np.abs(edge - 0.5) * 3.2, 0, 1) ** 1.5
        ink = post.solid(W, H, "InkSoft", 0.0)
        ink[..., 3] = line * 0.55
        img = post.over(ink, img)
        img[..., 3] = 1.0
        final = os.path.join(out, "sf_terrain_512x320.png")
        post.save(img, final)
        post.save(post.resize(img[100:260, 100:356], (768, 480), "nearest"),
                  os.path.join(out, "sf_terrain_zoom3x.png"))
    q = qa_terrain(img, f, albedo)
    print("[ironart] TIMES", {k: round(v, 2) for k, v in times.items()})
    q.check()


if __name__ == "__main__":
    main()
