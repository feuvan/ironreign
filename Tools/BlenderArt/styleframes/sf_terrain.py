"""Style frame (a): 512x320 crop of the relief world map (RTK IX look).

    Tools/BlenderArt/render.sh Tools/BlenderArt/styleframes/sf_terrain.py [out_dir]

Contents: sandy steppe (top-left), a snow-capped mountain range with foothills, ochre/sage plains,
a forest cluster of tiny 3D trees, a river ribbon running to the sea, beach, coastal shallows and
deep teal-indigo sea.  1 map pixel = 1 cm in the scene; the heightfield and the painted albedo are
computed at 2x (the render resolution) by :mod:`ironart.terrain`.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import numpy as np  # noqa: E402

from ironart import cameras, geometry as geo, lights, materials as M, post, scene  # noqa: E402
from ironart import terrain as T  # noqa: E402

W, H = 512, 320            # target pixels
SS = 2                     # supersample
PX = 0.01                  # metres per target pixel
Z = 0.42                   # metres for normalised height 1.0 (relief exaggeration)
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
    # --- mountain range along a spine (upper middle), foothills, lower-left hills
    spine = T.meander([(30, 175), (110, 120), (200, 92), (300, 70), (370, 36)], 6, 12, 80, SEED)
    d_sp, t_sp = T.polyline_distance(h, w, spine, 1.0 / SS, return_t=True)
    width = 30 + 12 * np.sin(t_sp * 9.0) + 10 * T.fbm_at(x, y, 60, 3, seed=4)
    rng_mask = np.exp(-(d_sp / width) ** 2)
    ridges = T.ridged_at(wx, wy, 44, 6, 0.55, seed=SEED + 5, sharpness=2.2)
    massif = 0.7 + 0.3 * np.sin(t_sp * 7.0 + 1.0)
    mountains = rng_mask * (0.2 + 0.95 * ridges) * massif * (0.8 + 0.2 * T.fbm_at(x, y, 120, 2, seed=5))
    # a second, lower range in the south-west (no snow)
    spine2 = T.meander([(-10, 300), (40, 268), (95, 262), (135, 290)], 6, 8, 50, SEED + 3)
    d2 = T.polyline_distance(h, w, spine2, 1.0 / SS)
    mountains += np.exp(-(d2 / 22.0) ** 2) * (0.15 + 0.4 * ridges) * 0.75
    foot = np.exp(-(d_sp / 75.0) ** 2) * (0.5 + 0.5 * T.fbm_at(wx, wy, 26, 4, seed=SEED + 6)) * 0.22
    hills_c = np.exp(-(np.hypot(x - 170, y - 275) / 45.0) ** 2) * (0.5 + 0.5 * T.fbm_at(wx, wy, 16, 4, seed=7)) * 0.16
    hills_c += np.exp(-(np.hypot(x - 345, y - 120) / 35.0) ** 2) * (0.5 + 0.5 * T.fbm_at(wx, wy, 14, 4, seed=8)) * 0.14
    plains = 0.012 + 0.012 * T.fbm_at(x, y, 60, 4, seed=SEED + 8)
    height = plains + foot + hills_c + mountains
    # --- river: from the range down to the bay, widening downstream
    river_pts = T.meander([(212, 104), (232, 150), (262, 200), (318, 228), (360, 250), (398, 262)],
                          5, 9, 45, SEED + 2)
    d_rv, t_rv = T.polyline_distance(h, w, river_pts, 1.0 / SS, return_t=True)
    half_w = 0.7 + 1.5 * t_rv
    river = T.smoothstep(half_w + 0.6, half_w - 0.4, d_rv)
    trib = T.meander([(105, 200), (150, 222), (205, 230), (262, 212)], 5, 7, 40, SEED + 9)
    d_tr, t_tr = T.polyline_distance(h, w, trib, 1.0 / SS, return_t=True)
    river = np.maximum(river, T.smoothstep(0.9 + 0.7 * t_tr + 0.5, 0.5 + 0.7 * t_tr, d_tr))
    river = river * T.smoothstep(0.3, 0.7, land)
    valley = np.exp(-(np.minimum(d_rv, d_tr) / 7.0) ** 2)
    height = height * (1 - 0.65 * valley) - 0.004 * river
    height = np.where(land > 0.5, np.maximum(height, 0.004), -0.02)
    # --- biomes
    steppe = T.smoothstep(150, 70, np.hypot(wx * 0.9, wy * 1.3) + 25 * T.fbm_at(x, y, 50, 3, seed=11))
    moisture = 0.5 + 0.5 * T.fbm_at(x, y, 150, 4, seed=12) + 0.35 * valley - 0.3 * steppe
    forest = T.smoothstep(0.5, 0.62, np.exp(-(np.hypot((wx - 262) * 0.8, wy - 262) / 60) ** 2)
                          + 0.25 * T.fbm_at(x, y, 22, 3, seed=13))
    forest2 = T.smoothstep(0.55, 0.65, np.exp(-(np.hypot(wx - 340, (wy - 150) * 1.2) / 30) ** 2)
                           + 0.2 * T.fbm_at(x, y, 15, 3, seed=14))
    forest = np.maximum(forest, forest2) * (1 - river) * (land > 0.5) * (height < 0.18)
    return dict(height=height.astype(np.float32), land=land, river=river, steppe=steppe,
                moisture=np.clip(moisture, 0, 1), forest=forest)


def main():
    out = scene.args()[0] if scene.args() else os.path.join(os.environ["IRONART_OUT"], "styleframes")
    os.makedirs(out, exist_ok=True)
    times = {}
    scene.reset(seed=SEED)
    rng = random.Random(SEED)
    with scene.timer("fields", times):
        f = make_fields()
        hn = f["height"] / max(1e-6, f["height"].max())
        albedo = T.paint_albedo(hn, f["land"], f["moisture"], f["steppe"], f["forest"] * 0.6,
                                f["river"], seed=SEED)
        alb_path = os.path.join(out, "terrain_albedo.png")
        a4 = np.dstack([albedo, np.ones(albedo.shape[:2], np.float32)])
        post.save(a4, alb_path, opaque=True)
    scene.setup_cycles(samples=40, transparent=False, preset="map", view="Standard")
    scene.set_resolution(W, H, SS)
    with scene.timer("build", times):
        terr = T.build_terrain(np.maximum(hn, 0.0), alb_path, (W * PX, H * PX), Z)
        mats = {"Foliage": M.foliage("Foliage", "#557546", translucency=0.05),
                "FoliageDark": M.foliage("FoliageDark", "#40603E", translucency=0.05),
                "FoliageLight": M.foliage("FoliageLight", "#7A8C50", translucency=0.05),
                "Trunk": M.principled("Trunk", "trunk")}
        mb = geo.MeshBuilder()
        hh, ww = hn.shape

        def zf(px, py):
            return float(hn[min(hh - 1, int(py * SS)), min(ww - 1, int(px * SS))]) * Z

        fmask = f["forest"][::SS, ::SS]
        n = T.scatter_forest(mb, fmask, (W * PX, H * PX), zf, rng, density=0.09, min_dist_px=3.2,
                             tree_px=(1.9, 2.8), leaves=("Foliage", "FoliageDark", "FoliageLight"))
        trees = mb.build("Forest", mats)
        print("[ironart] trees", n, "faces", len(trees.data.polygons))
    cam = cameras.ortho_top_down((0, 0), width=W * PX)
    lights.rig_map(cam, key=3.4, sky=0.62, elevation_deg=36, softness_deg=10)
    post.comp_painterly(size=7, sharpness=0.45, eccentricity=1.2, amount=0.75, ink=False)
    raw = os.path.join(out, "terrain_raw_%dx.png" % SS)
    times["render"] = scene.render(raw)
    with scene.timer("post", times):
        img = post.load(raw)
        img = post.downsample(img, SS)
        img = post.grade(img, saturation=1.04, contrast=1.04, warmth=0.012)
        # coast ink line (DESIGN.md: "coast ink line"), drawn crisp at final resolution
        land1 = T.resize(f["land"], (W, H))
        edge = post.gaussian((land1 > 0.5).astype(np.float32), 0.7)
        line = np.clip(1.0 - np.abs(edge - 0.5) * 3.2, 0, 1) ** 1.5
        ink = post.solid(W, H, "InkSoft", 0.0)
        ink[..., 3] = line * 0.55
        img = post.over(ink, img)
        img = post.apply_paper(img, post.paper_texture(W, H, SEED), strength=0.05)
        final = os.path.join(out, "sf_terrain_512x320.png")
        post.save(img, final, opaque=True)
    print("[ironart] TIMES", {k: round(v, 2) for k, v in times.items()})


main()
