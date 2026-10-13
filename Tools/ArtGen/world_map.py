#!/usr/bin/env python3
"""Generate Content/Data/Art/Map/WorldMap.png (2400x1500) from the `map` block of the scenario.

Painted parchment & ink campaign map: warm paper land, green-ochre plains, sandy steppe, hill-shaded
hills, ink-wash mountains with crest/spur strokes, forests of painted tree crowns, blue-green rivers
and lakes, indigo-teal sea with shallows and water lines, ink coastline. Map units == pixels, so the
runtime can draw cities/roads/labels on top at the JSON coordinates. No cities, roads or labels here.

Usage:  python3 Tools/ArtGen/world_map.py [--scenario path] [--out path]
Deterministic: all randomness comes from fixed seeds. Takes ~2-3 minutes and ~4 GB RAM.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.interpolate import CubicSpline

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artlib_world import (ART_MAP, SCENARIO, PAL, clamp01, catmull_rom, brush_polygon, fbm, hexcol,
                          mix, poly_mask, report, resample_polyline, rgba8, save_png,
                          signed_distance, smoothstep, value_noise)

S = 2  # supersampling factor (render at 2x, box-downsample)

# ---------------------------------------------------------------------------------------------
# palette for the map (sRGB 0..1)
# ---------------------------------------------------------------------------------------------
C = {
    "paper": PAL["paper"],
    "plain_dry": hexcol("D5C493"),
    "plain_mid": hexcol("C2BE8A"),
    "plain_green": hexcol("A8B27C"),
    "plain_lush": hexcol("94A670"),
    "sand": hexcol("E0C794"),
    "sand_dark": hexcol("CDB07C"),
    "steppe": hexcol("D3BF88"),
    "hill": hexcol("A9A76C"),
    "hill_lit": hexcol("C4C088"),
    "foot": hexcol("B3A274"),
    "rock_lit": hexcol("D4C59C"),
    "rock_mid": hexcol("A39579"),
    "rock_shadow": hexcol("6B6152"),
    "rock_deep": hexcol("3F3830"),
    "rock_cool": hexcol("6F7768"),
    "forest_floor": hexcol("8E9C66"),
    "water_light": hexcol("8FB0A6"),
    "water_mid": hexcol("5D8A8C"),
    "water_dark": hexcol("3A6170"),
    "bank": hexcol("2F4A52"),
    "sea_deep": hexcol("223A52"),
    "sea_mid": hexcol("33576A"),
    "sea_shallow": hexcol("5F8C8C"),
    "sea_coast": hexcol("8DAEA2"),
    "foam": hexcol("C2D2C0"),
    "beach": hexcol("E2D5AC"),
    "ink": PAL["ink"],
}

LIGHT = np.array([-0.62, -0.72, 0.95], np.float32)
LIGHT /= np.linalg.norm(LIGHT)


def log(msg, t0=[time.time()]):
    print(f"[{time.time() - t0[0]:6.1f}s] {msg}", flush=True)


def load_map(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return d["map"], d.get("cities", [])


def noise_up(GH, GW, cell_map, octaves=5, persistence=0.5, seed=0):
    """fBm generated at 1x map resolution and bilinearly upsampled to the 2x grid (fast)."""
    h, w = GH // S, GW // S
    n = fbm(h, w, cell_map, octaves=octaves, persistence=persistence, seed=seed)
    return ndimage.zoom(n, S, order=1)[:GH, :GW]


def noise1d(length, scale, seed):
    """Smooth (cubic) 1-D noise sampler f(s), unit-ish amplitude, feature size ~scale."""
    rng = np.random.default_rng(seed)
    k = int(length / scale) + 8
    cs = CubicSpline(np.arange(k), rng.standard_normal(k))
    return lambda s: cs(np.asarray(s, dtype=np.float64) / scale + 3)


# ---------------------------------------------------------------------------------------------
# relief: smooth base forms from the strokes, then erosion-like gullies (Gabor stripes that run
# down the slope of the base form) -> believable ridges, spurs and valleys without seams.
# ---------------------------------------------------------------------------------------------
def relief_base(Hgrid, strokes, X, Y, kind, seed):
    """Massif along each stroke + elongated summits. Returns the list of summits."""
    GH, GW = Hgrid.shape
    rng = np.random.default_rng(seed)
    summits = []
    for si, st in enumerate(strokes):
        w = float(st.get("width", 70))
        P = catmull_rom(np.asarray(st["points"], float), 16)
        hw = (0.62 if kind == "mtn" else 0.70) * w
        mg = hw + 0.7 * w
        x0 = int(max(0, (P[:, 0].min() - mg) * S)); x1 = int(min(GW, (P[:, 0].max() + mg) * S))
        y0 = int(max(0, (P[:, 1].min() - mg) * S)); y1 = int(min(GH, (P[:, 1].max() + mg) * S))
        Xb, Yb = X[y0:y1, x0:x1], Y[y0:y1, x0:x1]
        im = Image.new("L", (x1 - x0, y1 - y0), 0)
        ImageDraw.Draw(im).line([(x * S - x0, y * S - y0) for x, y in P], fill=255, width=2)
        dist = ndimage.distance_transform_edt(np.asarray(im) < 128) / S
        n = fbm(y1 - y0, x1 - x0, 22 * S, octaves=3, seed=seed + 50 + si)
        q = clamp01((dist + 0.12 * w * n) / hw)
        if kind == "mtn":
            H = 0.48 * w * np.power(1 - q, 1.2)
        else:
            H = 0.07 * w * 0.5 * (1 + np.cos(np.pi * q))
        pts, t = resample_polyline(P, (0.42 if kind == "mtn" else 0.40) * w)
        for i, (p, tt) in enumerate(zip(pts, t)):
            j = min(len(pts) - 1, i + 1); k = j - 1
            tv = pts[j] - pts[k]; tv = tv / (np.hypot(*tv) + 1e-9)
            taper = 0.55 + 0.45 * math.sin(math.pi * (0.06 + 0.88 * tt))
            cx, cy = p + rng.normal(0, 0.08 * w, 2)
            du = (Xb - cx) * tv[0] + (Yb - cy) * tv[1]
            dv = -(Xb - cx) * tv[1] + (Yb - cy) * tv[0]
            if kind == "mtn":
                h = w * rng.uniform(0.35, 0.62) * taper
                R = w * rng.uniform(0.50, 0.62)
                f = 0.45 * w * taper * np.power(clamp01(1 - np.hypot(du / 1.6, dv) / R), 1.3) + \
                    h * np.power(clamp01(1 - np.hypot(du / 1.15, dv) / R), 1.6)
                top = 0.45 * w * taper + h
            else:
                h = w * rng.uniform(0.08, 0.14) * taper
                R = w * rng.uniform(0.55, 0.72)
                qq = clamp01(np.hypot(du / 1.3, dv) / R)
                f = h * 0.5 * (1 + np.cos(np.pi * qq))
                top = h
            H = np.maximum(H, f)
            summits.append(dict(x=float(cx), y=float(cy), h=float(top), w=w, stroke=si, t=float(tt)))
        Hgrid[y0:y1, x0:x1] = np.maximum(Hgrid[y0:y1, x0:x1], H.astype(np.float32))
    return summits


def gullies(H, X, Y, octaves, seed, sharp=True, tile=640):
    """Add downslope-aligned Gabor stripes to H (in place, only where H has relief)."""
    GH, GW = H.shape
    for o, (freq, amp) in enumerate(octaves):
        Hs = ndimage.gaussian_filter(H, 2.0 * S)
        gy, gx = np.gradient(Hs, 1.0 / S)
        gl = np.hypot(gx, gy) + 1e-6
        tx, ty = (-gy / gl).astype(np.float32), (gx / gl).astype(np.float32)
        cs = 1.0 / freq
        rng = np.random.default_rng(seed + o)
        nci, ncj = int(GW / S / cs) + 8, int(GH / S / cs) + 8
        phase = rng.uniform(0, 2 * np.pi, (ncj, nci)).astype(np.float32)
        jx = rng.uniform(-0.35, 0.35, (ncj, nci)).astype(np.float32)
        jy = rng.uniform(-0.35, 0.35, (ncj, nci)).astype(np.float32)
        add = np.zeros_like(H)
        for ty0 in range(0, GH, tile):
            for tx0 in range(0, GW, tile):
                sl = (slice(ty0, min(GH, ty0 + tile)), slice(tx0, min(GW, tx0 + tile)))
                if Hs[sl].max() < 0.5:
                    continue
                Xb, Yb = X[sl], Y[sl]
                ci = np.floor(Xb / cs).astype(np.int32); cj = np.floor(Yb / cs).astype(np.int32)
                acc = np.zeros(Xb.shape, np.float32); ws = np.full(Xb.shape, 1e-6, np.float32)
                for oj in (-1, 0, 1, 2):
                    for oi in (-1, 0, 1, 2):
                        I = np.clip(ci + oi + 2, 0, nci - 1); J = np.clip(cj + oj + 2, 0, ncj - 1)
                        cx = (ci + oi + 0.5 + jx[J, I]) * cs
                        cy = (cj + oj + 0.5 + jy[J, I]) * cs
                        pxi = np.clip((cx * S).astype(np.int32), 0, GW - 1)
                        pyi = np.clip((cy * S).astype(np.int32), 0, GH - 1)
                        dtx, dty = tx[pyi, pxi], ty[pyi, pxi]
                        dx, dy = Xb - cx, Yb - cy
                        wgt = np.exp(-(dx * dx + dy * dy) / (2 * (0.75 * cs) ** 2))
                        acc += wgt * np.cos(2 * np.pi * freq * (dx * dtx + dy * dty) + phase[J, I])
                        ws += wgt
                g = acc / ws
                r = (0.5 * g + 0.5 * (1 - 2 * np.abs(g) * 0.9)) if sharp else g
                add[sl] = amp * smoothstep(0.05, 0.6, gl[sl]) * r * smoothstep(0.5, 6.0, Hs[sl])
        H += add
        del Hs, gy, gx, gl, tx, ty, add


def relshade(Hx, px):
    gy, gx = np.gradient(Hx, px)
    nz = 1.0 / np.sqrt(gx * gx + gy * gy + 1)
    return (-gx * LIGHT[0] - gy * LIGHT[1] + LIGHT[2]) * nz - LIGHT[2]


# ---------------------------------------------------------------------------------------------
def build(scenario_path: Path, out_path: Path):
    m, cities = load_map(scenario_path)
    W, H = int(m["width"]), int(m["height"])
    GW, GH = W * S, H * S
    px = 1.0 / S  # map units per grid pixel
    log(f"map {W}x{H}, grid {GW}x{GH}")

    ys = (np.arange(GH, dtype=np.float32) + 0.5) * px
    xs = (np.arange(GW, dtype=np.float32) + 0.5) * px
    X = np.broadcast_to(xs[None, :], (GH, GW))
    Y = np.broadcast_to(ys[:, None], (GH, GW))

    # ---- calm zones around cities (keep the board readable under icons/plaques) ------------
    calm = np.zeros((GH, GW), np.float32)
    city_pts = []
    for c in cities:
        cx, cy, sz = float(c["x"]), float(c["y"]), int(c.get("size", 1))
        city_pts.append((cx, cy, sz))
        rin = 22 + 5 * sz
        rout = rin + 26
        x0, x1 = int(max(0, (cx - rout) * S)), int(min(GW, (cx + rout) * S))
        y0, y1 = int(max(0, (cy - 16 - rout * 1.1) * S)), int(min(GH, (cy - 16 + rout * 1.1) * S))
        d = np.hypot(X[y0:y1, x0:x1] - cx, (Y[y0:y1, x0:x1] - (cy - 16)) / 1.1)
        calm[y0:y1, x0:x1] = np.maximum(calm[y0:y1, x0:x1], smoothstep(rout, rin, d))
    log("calm zones")

    # ---- land / sea ------------------------------------------------------------------------
    land0 = poly_mask(GW, GH, m["land"], scale=S)
    sd0 = signed_distance(land0, px)
    n_coast = noise_up(GH, GW, 85, octaves=7, persistence=0.56, seed=101)
    field = sd0 + 12.0 * (1 - 0.65 * calm) * n_coast
    del n_coast
    land = field > 0
    for target in (True, False):  # remove specks of land, then pinholes of sea
        msk = land if target else ~land
        lab, n = ndimage.label(msk)
        if n:
            sizes = ndimage.sum(msk, lab, index=np.arange(1, n + 1))
            small = np.zeros(n + 1, bool)
            small[1:] = sizes < 900
            land = np.where(small[lab], not target, land)
    for cx, cy, sz in city_pts:
        yy, xx = int(cy * S), int(cx * S)
        if 0 <= yy < GH and 0 <= xx < GW and not land[yy, xx]:
            print(f"warning: city at {cx},{cy} in sea after perturbation")
    sd_coast = signed_distance(land, px)  # + on land
    del field, sd0, land0
    log("land mask")

    # ---- lakes ------------------------------------------------------------------------------
    lake0 = poly_mask(GW, GH, m.get("lakes", []), scale=S)
    sdl0 = signed_distance(lake0, px)
    lake = ((sdl0 + 5.0 * noise_up(GH, GW, 40, octaves=5, persistence=0.55, seed=202)) > 0) & land
    sd_lake = signed_distance(lake, px)  # + inside lakes
    del sdl0, lake0
    log("lakes")

    # ---- rivers -----------------------------------------------------------------------------
    cl_mask = np.zeros((GH, GW), bool)
    cl_hw = np.zeros((GH, GW), np.float32)
    water_any = (~land) | lake
    river_lines = []
    for ri, r in enumerate(m.get("rivers", [])):
        P = np.asarray(r["points"], dtype=np.float64)
        w = float(r.get("width", 10))

        def in_water(p, rad=30):
            xx, yy = int(p[0] * S), int(p[1] * S)
            rr = int(rad * S)
            return bool(water_any[max(0, yy - rr):min(GH, yy + rr), max(0, xx - rr):min(GW, xx + rr)].any())

        start_wet, end_wet = in_water(P[0]), in_water(P[-1])
        if end_wet:
            v = P[-1] - P[-2]
            P = np.vstack([P, P[-1] + v / np.hypot(*v) * 28])
        if start_wet:
            v = P[0] - P[1]
            P = np.vstack([P[0] + v / np.hypot(*v) * 22, P])
        smooth = catmull_rom(P, samples_per_seg=24)
        pts, t = resample_polyline(smooth, 0.2)
        seglen = float(np.hypot(*np.diff(pts, axis=0).T).sum())
        s = t * seglen
        off = 4.2 * noise1d(seglen, 34, 400 + ri)(s) + 0.9 * noise1d(seglen, 11, 500 + ri)(s)
        env = np.minimum(1, np.minimum(s, seglen - s) / 40.0)
        d = np.gradient(pts, axis=0)
        ln = np.hypot(d[:, 0], d[:, 1]); ln[ln == 0] = 1
        nrm = np.stack([-d[:, 1] / ln, d[:, 0] / ln], 1)
        pts = pts + nrm * (off * env)[:, None]
        hw = w / 2 * ((0.82 + 0.18 * t) if start_wet else (0.30 + 0.70 * np.power(t, 0.55)))
        hw = hw * (1 + 0.12 * noise1d(seglen, 40, 600 + ri)(s))
        river_lines.append((pts, hw))
        ix = np.clip((pts[:, 0] * S).astype(int), 0, GW - 1)
        iy = np.clip((pts[:, 1] * S).astype(int), 0, GH - 1)
        cl_mask[iy, ix] = True
        cl_hw[iy, ix] = np.maximum(cl_hw[iy, ix], hw)
    dist_r, inds = ndimage.distance_transform_edt(~cl_mask, return_indices=True)
    D_riv = (dist_r * px).astype(np.float32)
    HW = cl_hw[inds[0], inds[1]]
    del inds, dist_r, cl_mask, cl_hw
    river_cov = clamp01((HW - D_riv) * S + 0.5) * land
    log("rivers")

    # ---- deserts / steppe -------------------------------------------------------------------
    n_des = noise_up(GH, GW, 70, octaves=5, seed=404)
    desert = np.zeros((GH, GW), np.float32)
    steppe = np.zeros((GH, GW), np.float32)
    for dz in m.get("deserts", []):
        cx, cy, r = float(dz["x"]), float(dz["y"]), float(dz["r"])
        v = 1 - np.hypot(X - cx, Y - cy) / r + 0.22 * n_des
        desert = np.maximum(desert, smoothstep(0.0, 0.45, v))
        steppe = np.maximum(steppe, smoothstep(-0.45, 0.05, v))
    log("deserts")

    # ---- forests ----------------------------------------------------------------------------
    n_for = noise_up(GH, GW, 30, octaves=4, seed=505)
    forest_v = np.full((GH, GW), -9.0, np.float32)
    for fz in m.get("forests", []):
        cx, cy, r = float(fz["x"]), float(fz["y"]), float(fz["r"])
        v = 1 - np.hypot(X - cx, Y - cy) / r + 0.28 * n_for
        forest_v = np.maximum(forest_v, v)
    del n_for
    forest_ground = smoothstep(-0.25, 0.15, forest_v) * land * (1 - lake)
    log("forests")

    # ---- relief: mountains & hills ----------------------------------------------------------
    carve = smoothstep(0.0, 1.0, (D_riv - HW) / (8 + 3 * HW))  # river valleys cut through relief
    Hm = np.zeros((GH, GW), np.float32)
    msum = relief_base(Hm, m.get("mountains", []), X, Y, "mtn", 606)
    Hm *= carve
    gullies(Hm, X, Y, [(1 / 17.0, 5.5), (1 / 8.5, 2.0)], 650, sharp=True)
    np.maximum(Hm, 0, out=Hm)
    log("mountains")
    Hh = np.zeros((GH, GW), np.float32)
    hsum = relief_base(Hh, m.get("hills", []), X, Y, "hill", 707)
    Hh *= carve * (1 - 0.6 * calm)
    gullies(Hh, X, Y, [(1 / 20.0, 1.3)], 750, sharp=False)
    np.maximum(Hh, 0, out=Hh)
    log("hills")

    # ---- hillshade: big forms (washes) + detail (texture strokes) ----------------------------
    Hp = 1.6 * noise_up(GH, GW, 180, octaves=3, seed=809) * (1 - 0.6 * desert)
    Hrel = (Hm + Hh) * smoothstep(-2, 6, sd_coast)
    rel = 0.65 * relshade(ndimage.gaussian_filter(Hrel, 5 * S), px) + 0.45 * relshade(Hrel + Hp, px)
    lap = ndimage.laplace(ndimage.gaussian_filter(Hm, 1.0 * S)) * (S * S)
    cun = smoothstep(-0.25, -0.8, lap) * smoothstep(10, 35, Hm)  # ink on sharp convex ridges
    del Hrel, Hp, lap
    log("hillshade")

    # ---- base land colour -------------------------------------------------------------------
    n_moist = noise_up(GH, GW, 260, octaves=4, seed=901)
    near_water = np.maximum(np.exp(-np.maximum(D_riv - HW, 0) / 55.0), np.exp(-np.maximum(-sd_lake, 0) / 70.0))
    moist = 0.42 + 0.17 * n_moist + 0.30 * near_water + 0.30 * (Y / H - 0.5) - 0.18 * (1 - X / W) * smoothstep(1050, 650, Y)
    moist = clamp01(moist - 0.5 * steppe)
    del n_moist, near_water
    col = mix(C["plain_dry"], C["plain_mid"], smoothstep(0.15, 0.45, moist))
    col = mix(col, C["plain_green"], smoothstep(0.45, 0.72, moist))
    col = mix(col, C["plain_lush"], smoothstep(0.75, 1.0, moist) * 0.7)
    del moist
    col = mix(col, C["paper"], clamp01(0.16 + 0.08 * noise_up(GH, GW, 70, octaves=3, seed=902)))
    # steppe / desert
    sand = mix(C["sand"], C["sand_dark"], clamp01(0.5 + 0.5 * n_des))
    dune_w = noise_up(GH, GW, 90, octaves=3, seed=903)
    dunes = np.sin((X * 0.55 + Y * 0.83 + 26 * dune_w) * (2 * math.pi / 19.0))
    sand *= (1 + 0.03 * dunes * desert)[..., None]
    col = mix(col, C["steppe"], steppe * 0.75)
    col = mix(col, sand, desert)
    del dunes, dune_w, sand, n_des
    # hills: greener-ochre, lit crests lighter
    hill_m = smoothstep(0.5, 5.0, Hh)
    hcol = mix(C["hill"], C["hill_lit"], smoothstep(0.0, 0.25, rel))
    col = mix(col, hcol, hill_m * 0.7)
    del hcol
    # forest ground
    col = mix(col, C["forest_floor"], forest_ground * 0.7)
    # shading on soft terrain
    col *= (1 + np.where(rel > 0, 0.7, 1.15) * np.clip(rel, -0.45, 0.22))[..., None]
    # mountains (ink wash): lit / shadow / deep-shadow washes, base dissolving into mist
    col = mix(col, C["foot"], smoothstep(0.3, 6.0, Hm) * 0.35)
    mtn = smoothstep(0.3, 14.0, Hm)
    s = rel
    rock = mix(C["rock_mid"], C["rock_lit"], smoothstep(0.0, 0.20, s))
    rock = mix(rock, C["rock_shadow"], smoothstep(-0.02, -0.25, s))
    rock = mix(rock, C["rock_deep"], smoothstep(-0.35, -0.8, s) * 0.7)
    rock = mix(rock, C["rock_cool"], clamp01(Hm / 50.0) * 0.30 * smoothstep(0.0, -0.1, s))
    mist = 1 - smoothstep(1.0, 22.0, Hm)
    rock = mix(rock, mix(C["rock_lit"], C["paper"], 0.4), mist * 0.5)
    col = mix(col, rock, mtn)
    col = mix(col, C["ink"], cun * 0.40)
    del rock, s, mist, cun
    log("land colour")

    # ---- rivers -----------------------------------------------------------------------------
    band = D_riv - HW
    riparian = smoothstep(4.0, 0.0, band) * (band > -0.5) * land
    col = mix(col, col * np.array([0.82, 0.88, 0.80], np.float32), riparian * 0.5)
    inner = clamp01((HW - D_riv) / np.maximum(HW, 0.5))
    rcol = mix(C["water_mid"], C["water_light"], smoothstep(0.35, 1.0, inner) * 0.5)
    rcol = mix(rcol, C["bank"], smoothstep(1.3, 0.0, HW - D_riv) * 0.75)
    col = mix(col, rcol, river_cov)
    del band, riparian, inner, rcol, river_cov
    log("river paint")

    # ---- lakes ------------------------------------------------------------------------------
    lake_cov = clamp01(sd_lake * S + 0.5)
    lcol = mix(C["water_light"], C["water_mid"], smoothstep(0.0, 9.0, sd_lake))
    lcol = mix(lcol, C["water_dark"], smoothstep(10.0, 45.0, sd_lake) * 0.7)
    for k, dk in enumerate((5.5, 11.0, 18.0)):
        lcol = mix(lcol, C["foam"], np.exp(-((sd_lake - dk) / 0.55) ** 2) * (0.35 - 0.09 * k))
    col = mix(col, lcol, lake_cov)
    lake_ink = np.exp(-(sd_lake / 0.75) ** 2)
    del lcol
    log("lakes paint")

    # ---- sea --------------------------------------------------------------------------------
    d_sea = np.maximum(-sd_coast, 0)
    n_sea = noise_up(GH, GW, 160, octaves=4, seed=1001)
    sea = mix(C["sea_deep"], C["sea_mid"], clamp01(np.exp(-d_sea / 120.0) + 0.12 * n_sea))
    sea = mix(sea, C["sea_shallow"], np.exp(-d_sea / 38.0) * 0.85)
    sea = mix(sea, C["sea_coast"], np.exp(-d_sea / 9.0) * 0.6)
    n_brk = noise_up(GH, GW, 45, octaves=3, seed=1002)
    for k, dk in enumerate((6.0, 13.0, 21.0, 30.0, 41.0)):
        wl = np.exp(-((d_sea - dk) / 0.6) ** 2) * (0.55 - 0.1 * k) * smoothstep(-0.6, 0.2, n_brk)
        sea = mix(sea, C["foam"], wl)
    rngs = np.random.default_rng(1004)
    g = rngs.standard_normal((GH // (6 * S) + 2, GW // (60 * S) + 2)).astype(np.float32)
    streaks = ndimage.zoom(g, (6 * S, 60 * S), order=3, prefilter=False)[:GH, :GW]
    sea *= (1 + 0.035 * streaks * smoothstep(20, 80, d_sea))[..., None]
    land_cov = clamp01(sd_coast * S + 0.5)
    beach = smoothstep(2.6, 0.0, sd_coast) * (sd_coast > 0)
    col = mix(col, C["beach"], beach * 0.40 * (1 - lake_cov))
    col = mix(sea, col, land_cov)
    del sea, n_sea, n_brk, streaks, g, wl
    n_ink = noise_up(GH, GW, 40, octaves=3, seed=1101)
    coast_ink = clamp01((0.95 + 0.35 * n_ink - np.abs(sd_coast)) * S + 0.5)
    col = mix(col, C["ink"], coast_ink * 0.82)
    col = mix(col, C["ink"] * 1.3, lake_ink * 0.6)
    del n_ink, coast_ink, lake_ink
    log("sea + coast")

    F = dict(sd_coast=sd_coast, D_riv=D_riv, HW=HW, lake=lake, calm=calm, forest_v=forest_v,
             desert=desert, steppe=steppe, Hm=Hm, Hh=Hh, d_sea=d_sea, rel=rel)
    img = Image.fromarray((clamp01(col) * 255 + 0.5).astype(np.uint8), "RGB")
    del col
    overlays(img, m, F, W, H, city_pts, msum, hsum)
    log("overlays")

    # ---- paper texture: stains, fibres, edge wear ---------------------------------------------
    a = np.asarray(img, dtype=np.float32) / 255.0
    stains = 0.030 * noise_up(GH, GW, 320, octaves=3, seed=1201) + 0.016 * noise_up(GH, GW, 50, octaves=3, seed=1202)
    a *= (1 + stains)[..., None]
    edge = np.minimum(np.minimum(X, W - X), np.minimum(Y, H - Y)) + 14 * noise_up(GH, GW, 60, 3, seed=1203)
    burn = smoothstep(60.0, 0.0, edge)
    a = mix(a, a * np.array([0.72, 0.62, 0.50], np.float32), burn * 0.55)
    del stains, edge, burn
    img = Image.fromarray((clamp01(a) * 255 + 0.5).astype(np.uint8), "RGB")
    del a
    fibres(img, GW, GH)
    log("paper texture")

    out = img.resize((W, H), Image.BOX)
    a = np.asarray(out, dtype=np.float32)
    a += np.random.default_rng(1301).normal(0, 1.0, a.shape[:2]).astype(np.float32)[..., None]
    out = Image.fromarray(np.clip(a + 0.5, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    save_png(out, out_path)
    log("saved")
    report(out_path)


# ---------------------------------------------------------------------------------------------
def overlays(img, m, F, W, H, city_pts, msum, hsum):
    """Brush-work drawn with PIL on the 2x image: mountain ink, forests, steppe tufts, waves."""
    dr = ImageDraw.Draw(img, "RGBA")
    GH, GW = F["sd_coast"].shape
    ink = tuple(int(v * 255) for v in C["ink"])

    def at(arr, x, y):
        return arr[min(GH - 1, max(0, int(y * S))), min(GW - 1, max(0, int(x * S)))]

    def calm_at(x, y):
        return at(F["calm"], x, y)

    def ok_ground(x, y, margin=2.5):
        if at(F["sd_coast"], x, y) < 3.0 or at(F["lake"], x, y):
            return False
        return at(F["D_riv"], x, y) >= at(F["HW"], x, y) + margin

    def river_gap(x, y, extra=1.0):
        return at(F["D_riv"], x, y) < at(F["HW"], x, y) + extra

    def runs_of(keep):
        runs, cur = [], []
        for i, k in enumerate(keep):
            if k:
                cur.append(i)
            elif cur:
                runs.append(cur); cur = []
        if cur:
            runs.append(cur)
        return runs

    def ink_stroke(xy, widths, alpha, gap=2.5):
        keep = [not river_gap(x, y, gap) for x, y in xy]
        for run in runs_of(keep):
            if len(run) >= 3:
                dr.polygon(brush_polygon(xy[run] * S, np.asarray(widths)[run] * S), fill=ink + (int(alpha * 255),))

    SHADOW_DIR = np.array([0.7071, 0.7071])
    # ---- mountain ink: crest strokes between summits + summit accents ------------------------
    rng = np.random.default_rng(3001)
    by_stroke = {}
    for pk in msum:
        by_stroke.setdefault(pk["stroke"], []).append(pk)
    for si, lst in by_stroke.items():
        lst.sort(key=lambda p: p["t"])
        for a_, b_ in zip(lst[:-1], lst[1:]):
            pa, pb = np.array([a_["x"], a_["y"]]), np.array([b_["x"], b_["y"]])
            dvec = pb - pa
            nrm = np.array([-dvec[1], dvec[0]]) / (np.hypot(*dvec) + 1e-6)
            mid = (pa + pb) / 2 + nrm * rng.normal(0, 0.04 * a_["w"])
            P = catmull_rom(np.array([pa, mid, pb]), 10)
            u = np.linspace(0, 1, len(P))
            ha, hb = min(1, a_["h"] / (0.9 * a_["w"])), min(1, b_["h"] / (0.9 * b_["w"]))
            widths = (0.45 + 1.7 * ((1 - u) ** 2 * ha + u ** 2 * hb)) * (0.8 + 0.2 * a_["w"] / 80)
            ink_stroke(P, widths, 0.55, gap=3.5)
        for p in lst:  # summit accent: small dark wedge on the shadow side
            if p["h"] < 0.6 * p["w"] or river_gap(p["x"], p["y"], 4):
                continue
            r = 1.4 + p["h"] / 34
            cx, cy = p["x"] * S, p["y"] * S
            dr.polygon([(cx, cy), (cx + r * 1.7 * S, cy + r * 0.5 * S), (cx + r * 0.5 * S, cy + r * 1.7 * S)],
                       fill=ink + (95,))

    # ---- hills: soft ink contour on the shadow shoulder of each hill top --------------------
    for pk in hsum:
        if calm_at(pk["x"], pk["y"]) > 0.2 or pk["h"] < 0.07 * pk["w"]:
            continue
        rr = pk["w"] * 0.22
        arc = np.array([(pk["x"] + math.cos(a) * rr, pk["y"] + math.sin(a) * rr * 0.8)
                        for a in np.linspace(math.radians(-25), math.radians(115), 14)])
        widths = np.sin(np.linspace(0, math.pi, len(arc))) * 1.3 + 0.15
        ink_stroke(arc, widths, 0.22, gap=2)

    # ---- trees --------------------------------------------------------------------------------
    rng = np.random.default_rng(2201)
    greens = [hexcol(h) for h in ("4D6340", "57683E", "47603F", "5E6E42", "4A5E44", "647441", "53653F")]
    trees = []
    fv = F["forest_v"]
    for fz in m.get("forests", []):
        cx, cy, r = float(fz["x"]), float(fz["y"]), float(fz["r"])
        sp = 6.6
        for row, gy in enumerate(np.arange(cy - r * 1.5, cy + r * 1.5, sp * 0.8)):
            for gx in np.arange(cx - r * 1.5, cx + r * 1.5, sp):
                x = gx + rng.uniform(-0.4, 0.4) * sp + (sp / 2 if row % 2 else 0)
                y = gy + rng.uniform(-0.35, 0.35) * sp
                if not (0 <= x < W and 0 <= y < H):
                    continue
                v = at(fv, x, y)
                if v < -0.22:
                    continue
                dens = smoothstep(-0.22, 0.25, v)
                if rng.random() > 0.15 + 0.85 * dens ** 1.5:
                    continue
                if not ok_ground(x, y) or calm_at(x, y) > 0.25:
                    continue
                trees.append((x, y, rng.uniform(4.0, 6.0) * (0.7 + 0.3 * dens), dens))
    trees.sort(key=lambda t: t[1])
    shadow = (36, 42, 26)
    for (x, y, r, dens) in trees:
        g = greens[int(rng.integers(0, len(greens)))] * rng.uniform(0.93, 1.07)
        dark = g * 0.58
        light = mix(g, hexcol("CFCB92"), 0.42)
        X0, Y0, R = x * S, y * S, r * S
        dr.ellipse([X0 - R * 0.9 + 1.6 * S, Y0 - R * 0.7 + 2.0 * S, X0 + R * 1.05 + 1.6 * S, Y0 + R * 0.95 + 2.0 * S],
                   fill=shadow + (70,))
        blobs = [(rng.uniform(-0.32, 0.32) * R, rng.uniform(-0.3, 0.3) * R, R * rng.uniform(0.60, 0.76)) for _ in range(4)]
        for bx, by, br in blobs:
            dr.ellipse([X0 + bx - br, Y0 + by - br, X0 + bx + br, Y0 + by + br], fill=rgba8(dark, 1.0))
        for bx, by, br in blobs:
            bx2, by2, br2 = bx - 0.13 * R, by - 0.15 * R, br * 0.80
            dr.ellipse([X0 + bx2 - br2, Y0 + by2 - br2, X0 + bx2 + br2, Y0 + by2 + br2], fill=rgba8(g, 1.0))
        for _ in range(2):
            hx = X0 - rng.uniform(0.2, 0.45) * R
            hy = Y0 - rng.uniform(0.25, 0.5) * R
            hr = R * rng.uniform(0.25, 0.38)
            dr.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=rgba8(light, 0.5))

    # ---- steppe tufts --------------------------------------------------------------------------
    rng = np.random.default_rng(2301)
    tuft_col = rgba8(hexcol("6E6440"), 0.30)
    for _ in range(1400):
        x, y = rng.uniform(0, 700), rng.uniform(0, 1000)
        st, de = at(F["steppe"], x, y), at(F["desert"], x, y)
        if st < 0.25 or rng.random() > st * (1 - 0.7 * de) or not ok_ground(x, y, 3) or calm_at(x, y) > 0.1:
            continue
        X0, Y0 = x * S, y * S
        for a in (-0.5, 0.0, 0.5):
            L = rng.uniform(2.0, 3.4) * S
            dr.line([(X0, Y0), (X0 + math.sin(a) * L, Y0 - math.cos(a) * L)], fill=tuft_col, width=max(1, S // 2 + 1))

    # ---- stylised wave crests in deep water ---------------------------------------------------
    rng = np.random.default_rng(2401)
    wave = rgba8(C["foam"], 0.20)
    for gy in np.arange(10, H, 24):
        for gx in np.arange(1900 + (gy % 48) * 0.5, W, 46):
            x, y = gx + rng.uniform(-10, 10), gy + rng.uniform(-5, 5)
            if at(F["d_sea"], x, y) < 48 or rng.random() < 0.35:
                continue
            L = rng.uniform(6, 11)
            arc = np.array([(x + u * L, y - math.sin((u + 0.5) * math.pi) * L * 0.28) for u in np.linspace(-0.5, 0.5, 9)])
            widths = np.sin(np.linspace(0.15, math.pi - 0.15, len(arc))) * 1.3 * S
            dr.polygon(brush_polygon(arc * S, widths), fill=wave)


def fibres(img, GW, GH):
    """Faint paper fibres: short slightly curved strands, light and dark."""
    dr = ImageDraw.Draw(img, "RGBA")
    rng = np.random.default_rng(2501)
    n = int(GW * GH / 260)
    xs = rng.uniform(0, GW, n)
    ys = rng.uniform(0, GH, n)
    ang = rng.normal(0.25, 0.9, n)
    lens = rng.uniform(4, 16, n)
    bend = rng.normal(0, 0.35, n)
    light = rng.random(n) < 0.55
    alphas = rng.uniform(8, 22, n).astype(int)
    for i in range(n):
        a, L, x, y = ang[i], lens[i], xs[i], ys[i]
        mx, my = x + math.cos(a) * L * 0.5, y + math.sin(a) * L * 0.5
        a2 = a + bend[i]
        ex, ey = mx + math.cos(a2) * L * 0.5, my + math.sin(a2) * L * 0.5
        c = (255, 250, 236, int(alphas[i])) if light[i] else (96, 76, 52, int(alphas[i] * 0.8))
        dr.line([(x, y), (mx, my), (ex, ey)], fill=c, width=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default=str(SCENARIO))
    ap.add_argument("--out", default=str(ART_MAP / "WorldMap.png"))
    a = ap.parse_args()
    build(Path(a.scenario), Path(a.out))


if __name__ == "__main__":
    main()
