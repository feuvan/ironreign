"""World Terrain family - mountain RANGES and hill chains as ridge networks (numpy only).

A range is built the way a geologist would sketch it, not as a blob of noise:

    crest      the scenario stroke, smoothed, gently meandered and extended past both ends so the
               range tapers into foothills; along it summits and cols (two noise octaves), lowered
               into saddles where a road or pass crosses
    spurs      side ridges leaving the crest every ~0.6 reach on alternating sides, curving
               down and out at 25-45 degrees off the normal, falling from ~85 % of the crest to the
               plain; each carries one or two sub-spurs; spurs that would reach a city stop short
    profile    every ridge line is a tent ``h(s) * (1 - d / W(s)) ** p`` with a rounded crest; the
               ridges are joined with a smooth maximum, so V valleys open between the spurs and
               the main crest stays continuous
    detail     ridged multifractal crags and gullies scaled by the height (none on the plains)
    foothills  a billowy apron of 15-45 m knolls in front of the flanks, and lone knolls

Hill chains use the same machinery with low, round profiles.  Everything is in metres on the
master grid of :mod:`ironart.world_terrain_fields` (1 m, rows = map y).  Deterministic for a seed.

The networks are returned as plain data (``Range``) so the 2D painted map
(:mod:`ironart.world_terrain_glyphs`) can place its pictorial peaks on the same summits.
"""

import math

import numpy as np

from . import terrain as T
from . import world_terrain_fields as F

#: shape numbers per kind (metres or fractions; ``w`` = the stroke width of the scenario)
SPEC = {
    "mountain": dict(
        peak0=128.0, peak_per_w=0.62, peak_max=178.0,     # crest summit height
        reach_per_w=1.15, reach_per_peak=0.66,            # flank reach R = max(.. w, .. peak)
        extend=0.55,                                      # crest extension past the ends (x R)
        meander=0.10, crest_w=0.62, crest_p=1.3, crest_round=4.0,
        summit=(0.86, 0.14, 0.07), summit_len=(85.0, 32.0), end_h=0.22,
        spur_gap=0.27, spur_len=(0.7, 1.6), spur_h=(0.84, 0.96), spur_w=(0.44, 0.24),
        spur_p=1.3, spur_fall=1.3, spur_angle=(4.0, 50.0), spur_bend=40.0,
        sub=(1, 3), sub_len=(0.35, 0.6), sub_angle=(30.0, 55.0), sub_h=0.86,
        smooth_k=10.0, crag=16.0, crag_scale=26.0, crag2=3.5,
        gully=0.30, gully_t=26.0, gully_v=55.0,
        foot=14.0, foot_reach=1.9, knolls=(0, 0), knoll_h=(16.0, 42.0)),
    "hill": dict(
        peak0=44.0, peak_per_w=0.18, peak_max=60.0,
        reach_per_w=1.25, reach_per_peak=0.0,
        extend=0.45, meander=0.12, crest_w=0.85, crest_p=1.9, crest_round=14.0,
        summit=(0.82, 0.18, 0.08), summit_len=(70.0, 30.0), end_h=0.30,
        spur_gap=0.45, spur_len=(0.6, 1.1), spur_h=(0.66, 0.84), spur_w=(0.55, 0.40),
        spur_p=1.7, spur_fall=1.0, spur_angle=(10.0, 45.0), spur_bend=30.0,
        sub=(0, 1), sub_len=(0.35, 0.55), sub_angle=(30.0, 60.0), sub_h=0.8,
        smooth_k=16.0, crag=3.0, crag_scale=40.0, crag2=1.0,
        gully=0.18, gully_t=24.0, gully_v=80.0,
        foot=8.0, foot_reach=1.6, knolls=(0, 0), knoll_h=(10.0, 24.0)),
}


class Ridge:
    """One ridge line: points (N, 2) every ~4 m, crest height h (N,), tent half-width W (N,),
    profile exponent p, crest rounding r0 (m), level (0 crest, 1 spur, 2 sub-spur)."""

    __slots__ = ("pts", "h", "W", "p", "r0", "level")

    def __init__(self, pts, h, W, p, r0, level):
        self.pts = np.asarray(pts, np.float64)
        self.h = np.asarray(h, np.float32)
        self.W = np.asarray(W, np.float32)
        self.p = float(p)
        self.r0 = float(r0)
        self.level = int(level)


class Range:
    """A whole range / hill chain: its crest (points, heights), ridges, reach R and kind."""

    def __init__(self, kind, index, crest, crest_h, ridges, R, width, knolls):
        self.kind = kind
        self.index = index
        self.crest = crest
        self.crest_h = crest_h
        self.ridges = ridges
        self.R = R
        self.width = width
        self.knolls = knolls          # [(x, y, radius, height)]


# ---------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------
def smax(a, b, k):
    """Polynomial smooth maximum with rounding band ``k`` (m) that leaves zero ground at zero."""
    m = np.maximum(a, b)
    g = np.clip(1.0 - np.abs(a - b) / k, 0.0, 1.0)
    lo = np.clip(np.minimum(a, b) / k, 0.0, 1.0)
    return m + g * g * (0.25 * k) * lo


def smin(a, b, k):
    """Polynomial smooth minimum (band ``k`` m)."""
    m = np.minimum(a, b)
    g = np.clip(1.0 - np.abs(a - b) / k, 0.0, 1.0)
    return m - g * g * (0.25 * k)


def _noise1(t, scale, seed, off=0.37):
    t = np.asarray(t, np.float32)
    return T.perlin_at(t / scale, np.full_like(t, off), seed)


def _rot(v, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([c * v[0] - s * v[1], s * v[0] + c * v[1]])


def _bent_line(p0, d0, length, bend_deg, rng, step=4.0):
    """A gently curving polyline from ``p0`` in direction ``d0`` (unit), turning ``bend_deg``
    in total with a little wobble."""
    n = max(2, int(math.ceil(length / step)) + 1)
    pts = [np.asarray(p0, np.float64)]
    d = np.asarray(d0, np.float64) / (np.linalg.norm(d0) + 1e-9)
    turn = math.radians(bend_deg) / max(1, n - 1)
    wob = rng.uniform(0, 6.28)
    for i in range(1, n):
        a = turn + 0.05 * math.sin(wob + 0.7 * i)
        c, s = math.cos(a), math.sin(a)
        d = np.array([c * d[0] - s * d[1], s * d[0] + c * d[1]])
        pts.append(pts[-1] + d * (length / (n - 1)))
    return np.array(pts)


def _dist_to_cities(pts, cities):
    if not cities:
        return np.full(len(pts), 1e9)
    c = np.array([(cx, cy) for (_k, cx, cy, _s) in cities])
    d = np.hypot(pts[:, None, 0] - c[None, :, 0], pts[:, None, 1] - c[None, :, 1])
    return d.min(1)


def _poly_dist(p, poly):
    poly = np.asarray(poly, float)
    d = np.full(len(p), 1e9)
    for a, b in zip(poly[:-1], poly[1:]):
        d = np.minimum(d, _seg_dist(p, a, b))
    return d


def _river_segs(river_lines):
    out = []
    for rl in river_lines:
        rl = np.asarray(rl, float)
        out.extend(zip(rl[:-1], rl[1:]))
    return out


def _seg_dist(p, a, b):
    """Distance from points p (N, 2) to segment a-b."""
    d = b - a
    L2 = float(d @ d) + 1e-9
    t = np.clip(((p - a) @ d) / L2, 0, 1)
    q = a + t[:, None] * d
    return np.hypot(*(p - q).T)


# ---------------------------------------------------------------------------------------------
# networks
# ---------------------------------------------------------------------------------------------
def build_range(stroke, kind, index, seed, cities, city_clear, road_lines=(), pass_lines=(),
                river_lines=()):
    """The ridge network of one scenario stroke (see the module doc).

    ``city_clear(size)`` = radius (m) around a city no ridge may enter; ``road_lines`` /
    ``pass_lines`` = [(a, b)] straight road segments that lower the crest into saddles."""
    sp = SPEC[kind]
    rng = np.random.default_rng(seed)
    w = float(stroke["width"])
    peak = min(sp["peak_max"], sp["peak0"] + sp["peak_per_w"] * w)
    R = max(sp["reach_per_w"] * w, sp["reach_per_peak"] * peak)
    pts = F.smooth_line(F.resample(stroke["points"], 4.0), 6.0)
    ext = sp["extend"] * R
    pts = F.extend(pts, start=ext, end=ext)
    pts = F.meander(pts, sp["meander"] * R, seed + 1, step=4.0, fade=0.6 * R)
    pts = F.smooth_line(pts, 2.0)
    u = F.arclen(pts)
    L = float(u[-1])
    # crest height: summits and cols, tapering into foothills past the stroke ends
    c0, c1, c2 = sp["summit"]
    s1, s2 = sp["summit_len"]
    n = c0 + c1 * _noise1(u, s1, seed + 2) + c2 * _noise1(u, s2, seed + 3, 0.71)
    te = ext + 0.55 * R
    taper = sp["end_h"] + (1.0 - sp["end_h"]) * (T.smoothstep(0.0, te, u) * T.smoothstep(L, L - te, u))
    # the crest ends drop to nothing over the last stretch of the extension
    taper = taper * T.smoothstep(0.0, 0.5 * ext, u) * T.smoothstep(L, L - 0.5 * ext, u)
    hc = peak * n * taper
    # saddles where roads / passes cross the crest
    sad = np.ones(len(pts))
    for (a, b) in road_lines:
        dd = _seg_dist(pts, np.asarray(a, float), np.asarray(b, float))
        sad *= 1.0 - 0.45 * np.exp(-(dd / 45.0) ** 2)
    for (a, b) in pass_lines:
        dd = _seg_dist(pts, np.asarray(a, float), np.asarray(b, float))
        sad *= 1.0 - 0.38 * np.exp(-(dd / 55.0) ** 2)
    for rl in river_lines:
        dd = _poly_dist(pts, rl)
        sad *= 1.0 - 0.62 * np.exp(-(dd / 70.0) ** 2)
    hc = hc * sad
    # the crest never runs into a city
    dc = np.full(len(pts), 1e9)
    for (_k, cx, cy, s) in cities:
        dc = np.minimum(dc, np.hypot(pts[:, 0] - cx, pts[:, 1] - cy) - city_clear(s))
    hc = hc * T.smoothstep(0.0, 0.6 * R, dc)
    Wc = sp["crest_w"] * R * (0.55 + 0.45 * np.sqrt(np.clip(hc / max(peak, 1), 0, 1)))
    ridges = [Ridge(pts, hc, Wc, sp["crest_p"], sp["crest_round"], 0)]
    nrm, tg = F.normals(pts)
    # ---- spurs
    gap = sp["spur_gap"] * R
    pos = rng.uniform(0.2, 0.7) * gap
    side = 1.0 if rng.random() < 0.5 else -1.0
    while pos < L - 0.15 * gap:
        i = int(np.searchsorted(u, pos))
        i = min(max(i, 1), len(pts) - 2)
        h0 = float(hc[i])
        if h0 > 0.12 * peak:
            ang = rng.uniform(*sp["spur_angle"]) * (1 if rng.random() < 0.5 else -1)
            d0 = _rot(nrm[i] * side, ang)
            ln = rng.uniform(*sp["spur_len"]) * R * (0.6 + 0.4 * h0 / peak)
            sp_pts = _bent_line(pts[i], d0, ln, rng.uniform(-1, 1) * sp["spur_bend"], rng)
            ridges.extend(_spur(sp_pts, h0, R, peak, sp, rng, cities, city_clear, 1, road_lines,
                                list(pass_lines) + _river_segs(river_lines)))
        side = -side
        if rng.random() < 0.18:           # now and then two spurs on the same side
            side = -side
        pos += gap * rng.uniform(0.7, 1.3)
    # ---- knolls (foothill domes) in front of the flanks
    knolls = []
    nk = int(rng.integers(sp["knolls"][0], sp["knolls"][1] + 1))
    for _ in range(nk * 3):
        if len(knolls) >= nk:
            break
        i = int(rng.integers(0, len(pts)))
        sd = 1.0 if rng.random() < 0.5 else -1.0
        q = pts[i] + nrm[i] * sd * R * rng.uniform(1.05, sp["foot_reach"]) + tg[i] * rng.uniform(-0.3, 0.3) * R
        rad = rng.uniform(0.28, 0.5) * R
        if _dist_to_cities(q[None], cities)[0] < rad + 70.0:
            continue
        knolls.append((float(q[0]), float(q[1]), float(rad), float(rng.uniform(*sp["knoll_h"]))))
    return Range(kind, index, pts, hc, ridges, R, w, knolls)


def _spur(pts, h0, R, peak, sp, rng, cities, city_clear, level, road_lines, pass_lines):
    """One spur (and its sub-spurs): heights fall from ``spur_h`` x the crest to the plain."""
    out = []
    s = F.arclen(pts)
    ln = float(s[-1])
    # stop short of cities (and keep clear of passes)
    clear = np.full(len(pts), 1e9)
    for (_k, cx, cy, sz) in cities:
        clear = np.minimum(clear, np.hypot(pts[:, 0] - cx, pts[:, 1] - cy) - city_clear(sz) - 0.3 * R)
    for (a, b) in pass_lines:
        clear = np.minimum(clear, _seg_dist(pts, np.asarray(a, float), np.asarray(b, float)) - 25.0)
    bad = np.nonzero(clear < 0)[0]
    if len(bad):
        cut = int(bad[0])
        if cut < 3:
            return out
        pts, s = pts[:cut], s[:cut]
        ln = float(s[-1])
    hr = rng.uniform(*sp["spur_h"]) * h0 if level == 1 else sp["sub_h"] * h0
    f = np.clip(s / max(ln, 1.0), 0, 1)
    # convex-then-concave fall with a shoulder knob part way down
    knob = 1.0 + 0.10 * math.exp(0) * np.exp(-((f - rng.uniform(0.35, 0.6)) / 0.12) ** 2) * (level == 1)
    h = hr * (1.0 - f) ** sp["spur_fall"] * knob
    h = h * T.smoothstep(-0.02, 0.15, 1.0 - f) + 0.0
    wa, wb = sp["spur_w"]
    W = R * (wa + (wb - wa) * f) * (0.75 if level == 2 else 1.0)
    W = W * (0.6 + 0.4 * np.sqrt(np.clip(h / max(peak, 1), 0, 1) / max(hr / peak, 1e-3)))
    out.append(Ridge(pts, h, W, sp["spur_p"], sp["crest_round"] * 0.6, level))
    if level == 1:
        nsub = int(rng.integers(sp["sub"][0], sp["sub"][1] + 1))
        nrm, tg = F.normals(pts)
        for k in range(nsub):
            j = int(len(pts) * rng.uniform(0.3, 0.65))
            j = min(max(j, 1), len(pts) - 2)
            sd = 1.0 if (k % 2 == 0) == (rng.random() < 0.5) else -1.0
            d0 = _rot(tg[j], sd * rng.uniform(*sp["sub_angle"]))
            sub_pts = _bent_line(pts[j], d0, rng.uniform(*sp["sub_len"]) * ln,
                                 rng.uniform(-1, 1) * sp["spur_bend"], rng)
            out.extend(_spur(sub_pts, float(h[j]), R, peak, sp, rng, cities, city_clear, 2,
                             road_lines, pass_lines))
    return out


# ---------------------------------------------------------------------------------------------
# rasterisation
# ---------------------------------------------------------------------------------------------
def rasterize(rng_list, shape, kind_k=None, seed=0):
    """Smooth-max union of all ridge tents of ``rng_list`` (Ranges) on the master grid.

    Every tent is dissected by side gullies: ridged noise in the ridge's own coordinates
    (stretched across the ridge, so the gullies run straight down its flanks and never cut the
    ridge line itself), two octaves so they branch.

    Returns (height, ridge_level, ridge_dist): the relief (m), which ridge level wins each point
    (0 crest, 1 spur, 2 sub-spur, -1 none) and the distance to that ridge line (m) - the albedo
    painter uses them for crest / spur / valley colouring."""
    out = np.zeros(shape, np.float32)
    lev = np.full(shape, -1, np.int8)
    rdist = np.full(shape, 1e4, np.float32)
    for gi, rg in enumerate(rng_list):
        sp = SPEC[rg.kind]
        k = kind_k or sp["smooth_k"]
        for ri, rd in enumerate(rg.ridges):
            Wm = float(rd.W.max())
            sy, sx, org = F.window(rd.pts, Wm + 2.0, shape)
            shp = (sy.stop - sy.start, sx.stop - sx.start)
            if shp[0] <= 0 or shp[1] <= 0:
                continue
            d, t, side = F.polyline_field(rd.pts, Wm + 2.0, want_t=True, shape=shp, origin=org,
                                          want_side=True)
            ok = np.isfinite(d)
            cum = F.arclen(rd.pts)
            hh = np.where(ok, np.interp(t, cum, rd.h), 0.0).astype(np.float32)
            ww = np.where(ok, np.interp(t, cum, rd.W), 0.0).astype(np.float32)
            tt = np.where(ok, t, 0.0).astype(np.float32)
            # the arc parameter jumps / fans out on the outside of bends: blur the interpolated
            # crest height, width and arc length (normalised by the valid area)
            okf = ok.astype(np.float32)
            den = np.maximum(F.fast_blur(okf, 5.0), 1e-3)
            hh = F.fast_blur(hh, 5.0) / den
            ww = np.maximum(F.fast_blur(ww, 5.0) / den, 1.0)
            tt = F.fast_blur(tt, 5.0) / den
            dd = np.where(ok, d, 1e4).astype(np.float32)
            dr = np.sqrt(dd * dd + rd.r0 * rd.r0) - rd.r0
            q = np.clip(dr / np.maximum(ww, 1.0), 0.0, 1.0)
            c = hh * (1.0 - q) ** rd.p
            # side gullies (ridge coordinates: along = tt, across = dd)
            gs = seed + 1000 * gi + 17 * ri
            sg = np.where(side > 0, 0.0, 53.7).astype(np.float32)
            lt, lv = sp["gully_t"], sp["gully_v"]
            lt = lt * (0.8 + 0.4 * ((ri * 0.618) % 1.0))
            tw = tt + 0.45 * lt * T.perlin_at(dd / 37.0 + sg, tt / 53.0, gs + 2)
            n1 = T.perlin_at(tw / lt + sg, dd / lv, gs)
            n2 = T.perlin_at(tw / (0.42 * lt) - sg, dd / (0.45 * lv) + 3.3, gs + 1)
            r1 = np.clip(np.abs(n1) / 0.55, 0, 1) ** 0.75
            r2 = np.clip(np.abs(n2) / 0.55, 0, 1) ** 0.75
            ridge = r1 * (0.55 + 0.45 * r2)
            cut = sp["gully"] * T.smoothstep(0.06, 0.45, q) * (1.0 - 0.6 * T.smoothstep(0.75, 1.0, q))
            c = c * (1.0 - cut * (1.0 - ridge))
            c = np.where(ok, c, 0.0).astype(np.float32)
            sub = out[sy, sx]
            win = (c > sub) & (c > 0.5)
            ls = lev[sy, sx]
            ls[win] = rd.level
            rs = rdist[sy, sx]
            rs[win] = dd[win]
            out[sy, sx] = smax(sub, c, k)
    return out, lev, rdist


def detail(h, xs, ys, kind, seed):
    """Ridged crags and gullies scaled by the relief (zero on flat ground)."""
    sp = SPEC[kind]
    m = h > 0.5
    if not m.any():
        return h
    rows = np.nonzero(m.any(1))[0]
    cols = np.nonzero(m.any(0))[0]
    y0, y1 = int(rows[0]), int(rows[-1]) + 1
    x0, x1 = int(cols[0]), int(cols[-1]) + 1
    hw = h[y0:y1, x0:x1]
    X, Y = xs[y0:y1, x0:x1], ys[y0:y1, x0:x1]
    wx = X + 14.0 * T.fbm_at(X, Y, 70.0, 2, seed=seed + 1)
    wy = Y + 14.0 * T.fbm_at(X, Y, 70.0, 2, seed=seed + 2)
    r1 = T.ridged_at(wx, wy, scale=sp["crag_scale"], octaves=4, seed=seed + 3, sharpness=1.7)
    r2 = T.fbm_at(wx, wy, 9.0, 2, seed=seed + 4)
    s = T.smoothstep(2.0, 60.0, hw) * np.clip(hw / 120.0, 0.25, 1.0)
    out = h.copy()
    out[y0:y1, x0:x1] = hw + sp["crag"] * (r1 - 0.42) * s + sp["crag2"] * r2 * s
    return np.maximum(out, 0.0)


def foothills(rg, xs, ys, shape, seed):
    """Billowy foothill apron along the range plus its knolls (m, master grid window max-composed
    into a full field)."""
    sp = SPEC[rg.kind]
    out = np.zeros(shape, np.float32)
    R = rg.R
    reach = sp["foot_reach"] * R + 30.0
    sy, sx, org = F.window(rg.crest, reach, shape)
    shp = (sy.stop - sy.start, sx.stop - sx.start)
    d, t = F.polyline_field(rg.crest, reach, want_t=True, shape=shp, origin=org)
    ok = np.isfinite(d)
    u = F.arclen(rg.crest)
    L = float(u[-1])
    # the arc parameter fans out on the outside of bends: blur it hard (it only modulates)
    okf = ok.astype(np.float32)
    den = np.maximum(F.fast_blur(okf, 30.0), 1e-3)
    t = F.fast_blur(np.where(ok, t, 0.0).astype(np.float32), 30.0) / den
    hcr = np.interp(t, u, rg.crest_h)
    X, Y = xs[sy, sx], ys[sy, sx]
    bill = 0.5 + 0.5 * T.fbm_at(X, Y, 0.9 * R, 3, seed=seed + 11)
    tf = T.smoothstep(0.0, 0.25 * L, t) * T.smoothstep(L, 0.75 * L, t)
    dd = np.where(ok, d, 1e4)
    env = np.exp(-(np.maximum(dd - 0.35 * R, 0.0) / (0.62 * sp["foot_reach"] * R)) ** 2)
    env = env * T.smoothstep(reach, 0.7 * reach, dd)
    pk = max(float(rg.crest_h.max()), 1.0)
    a = sp["foot"] * (0.45 + 0.55 * np.clip(hcr / pk, 0, 1)) * env * (0.35 + 0.65 * bill) * (0.5 + 0.5 * tf)
    out[sy, sx] = np.maximum(out[sy, sx], np.where(ok, a, 0.0))
    for (kx, ky, kr, kh) in rg.knolls:
        x0, x1 = int(max(0, kx - 1.6 * kr)), int(min(shape[1], kx + 1.6 * kr + 1))
        y0, y1 = int(max(0, ky - 1.6 * kr)), int(min(shape[0], ky + 1.6 * kr + 1))
        if x1 <= x0 or y1 <= y0:
            continue
        Xs, Ys = xs[y0:y1, x0:x1], ys[y0:y1, x0:x1]
        wn = 0.25 * kr * T.fbm_at(Xs, Ys, 0.8 * kr, 2, seed=seed + 21)
        dd = np.hypot(Xs - kx, Ys - ky) + wn
        dome = kh * np.clip(1.0 - (dd / kr) ** 2, 0, 1) ** 1.5
        out[y0:y1, x0:x1] = np.maximum(out[y0:y1, x0:x1], dome)
    return out
