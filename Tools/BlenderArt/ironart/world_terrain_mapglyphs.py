"""World Terrain family - the pictorial peaks, hills and trees of the 2D painted map (WorldMap.png).

The painted map is a plan view (land, coast, rivers and lakes keep their exact map positions), but
its mountains, hills and trees are drawn *pictorially*, as seen from the south in slight elevation,
like the peaks of a Ming/Qing court map (舆图) painted in the blue-green manner.  The projection
and the Blender helpers (shear, holdout ground, camera, AOV passes) are those of
:mod:`ironart.world_terrain_glyphs`; this module adds the peak *layout* on the 3D ranges and the
peak / tree *forms*:

layout     every range of the 3D map (:mod:`ironart.world_terrain_relief`) becomes a painted range:
           a row of main peaks on the summits of its crest (heights from the 3D crest, so a col or
           a water gap in 3D is a gap in the painting), taller and paler peaks staggered behind
           them, lower peaks on the spur roots in front and a row of rounded foot hills; hills are
           rows of round mounds (馒头山); every island gets a peak or two.  Peaks are shrunk or
           dropped where they would cover a city site (the game draws the city, its banner and its
           label there).
peaks      a painted peak: rounded crown, steep concave flanks flaring at the foot, an irregular
           lobed outline, 4-9 folds (披麻 ridges) radiating from below the crown and curving down,
           shoulder summits; archetypes spire / dome / stepped cliff / twin.
trees      broadleaf crowns of clustered lumps, pines with layered flat needle pads, bamboo clumps.

Every surface carries attributes the painter (:mod:`ironart.world_terrain_mappaint`) reads from
three AOVs: ``gA`` = (hn: height fraction, rho: radius fraction, rand), ``gB`` = (fold: sin of
the fold phase * 0.5 + 0.5, fold_w, kind / 2), ``gC`` = (row / 4 + 0.5, page height / 160, tree
crown flag).
"""

import math

import numpy as np

from . import terrain as T
from . import world_terrain_fields as F
from . import world_terrain_glyphs as G

K, CE, SE = G.K, G.CE, G.SE
KIND_MOUNTAIN, KIND_HILL, KIND_TREE = 0, 1, 2

#: peak design numbers (page px of WorldMap.png at 1x)
PEAK = dict(page_per_m=0.74, max_page=150.0, min_page=20.0, width=(0.55, 0.8), depth=0.55,
            folds=(5, 9), fold_amp=(0.16, 0.24), lean=0.16, wobble=(0.05, 0.13))
HILL = dict(page_per_m=0.6, max_page=32.0, min_page=10.0, width=(1.35, 1.8), depth=0.6,
            folds=(3, 5), fold_amp=(0.05, 0.09), lean=0.05, wobble=(0.03, 0.07))
#: page clearance (px) kept around each city point: no glyph may cover it
CITY_CLEAR_PX = {1: 30.0, 2: 38.0, 3: 46.0}


# ---------------------------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------------------------
def _summits(u, h, min_gap):
    """Indices of the local maxima of ``h`` along arc ``u`` at least ``min_gap`` apart."""
    hs = F.smooth_1d(np.asarray(h, np.float64), 3)
    cand = [i for i in range(1, len(hs) - 1) if hs[i] >= hs[i - 1] and hs[i] >= hs[i + 1]]
    cand.sort(key=lambda i: -hs[i])
    out = []
    for i in cand:
        if all(abs(u[i] - u[j]) >= min_gap for j in out):
            out.append(i)
    return sorted(out)


def _peak(kind, x, y, H, rng, row, spec, rx=None, **over):
    lo, hi = spec["width"]
    rx = rx if rx is not None else H * rng.uniform(lo, hi)
    p = dict(kind=kind, x=float(x), y=float(y), H=float(H), rx=float(rx),
             ry=float(rx * spec["depth"] * rng.uniform(0.85, 1.15)),
             lean=float(rng.uniform(-1, 1) * spec["lean"]),
             folds=int(rng.integers(spec["folds"][0], spec["folds"][1] + 1)),
             fold_amp=float(rng.uniform(*spec["fold_amp"])),
             phase=float(rng.uniform(0, 2 * np.pi)), twist=float(rng.uniform(-0.9, 0.9)),
             wobble=float(rng.uniform(*spec["wobble"])), row=int(row),
             seed=int(rng.integers(1 << 30)))
    if kind == "mountain":
        p.update(_archetype(rng))
        p["shoulders"] = [(float(rng.uniform(0.3, 0.62)) * float(rng.choice([-1, 1])),
                           float(rng.uniform(0.45, 0.75))) for _ in range(int(rng.integers(1, 3)))]
    else:
        p.update(dict(sharp=2.2, waist=0.62, tip=0.0, step=0.0))
        p["shoulders"] = []
    p.update(over)
    return p


def _archetype(rng):
    """Per-peak form: spire, domed crown, stepped cliff or plain peak."""
    r = rng.random()
    if r < 0.2:       # spire
        return dict(sharp=float(rng.uniform(2.6, 3.2)), waist=float(rng.uniform(0.28, 0.36)),
                    tip=float(rng.uniform(0.05, 0.12)), step=0.0)
    if r < 0.45:      # domed crown
        return dict(sharp=float(rng.uniform(3.8, 4.8)), waist=float(rng.uniform(0.42, 0.52)),
                    tip=0.0, step=0.0)
    if r < 0.6:       # stepped cliff
        return dict(sharp=float(rng.uniform(3.2, 4.0)), waist=float(rng.uniform(0.36, 0.46)),
                    tip=0.0, step=float(rng.uniform(0.45, 0.65)))
    return dict(sharp=float(rng.uniform(3.0, 3.7)), waist=float(rng.uniform(0.34, 0.46)),
                tip=float(rng.uniform(0.0, 0.06)), step=0.0)


def layout(world, seed=4242):
    """All painted peaks and mounds (dicts, see :func:`_peak`), back to front."""
    rng = np.random.default_rng(seed)
    peaks = []
    for rg in world.ranges:
        peaks.extend(_range_peaks(rg, rng, world))
    for rg in world.hill_ranges:
        peaks.extend(_hill_mounds(rg, rng, world))
    # islands: a blue-green peak (or two) rising from each island
    for poly in world.m["land"][1:]:
        xs_ = [q[0] for q in poly]
        ys_ = [q[1] for q in poly]
        cx, cy = float(np.mean(xs_)), float(np.mean(ys_))
        rad = 0.5 * max(np.ptp(xs_), np.ptp(ys_))
        n_pk = 1 if rad < 55 else 2
        for k in range(n_pk):
            ox = (k - 0.5 * (n_pk - 1)) * 0.55 * rad
            H = rad * rng.uniform(0.75, 0.95) * (1.0 - 0.3 * k)
            peaks.append(_peak("mountain", cx + ox, cy + 0.2 * rad, H, rng, 0, PEAK,
                               rx=rad * (0.42 if n_pk == 1 else 0.34)))
    # keep the cities clear: shrink (or drop) a glyph whose page footprint covers a city
    kept = []
    for p in peaks:
        for (_k, cx, cy, s) in world.cities:
            p = G._clear_city(p, cx, cy, CITY_CLEAR_PX[s])
            if p is None:
                break
        if p is not None and p["H"] >= 8.0:
            kept.append(p)
    kept.sort(key=lambda p: (p["y"], p["x"]))
    for i, p in enumerate(kept):
        p["id"] = i
        p["rand"] = float(np.random.default_rng(p["seed"]).random())
    return kept


def _clip_page(H, y, rx, depth):
    """No summit closer than 8 px to the top edge of the page."""
    return min(H, (y - 8.0) / 1.05)


def _range_peaks(rg, rng, world):
    """Painted peaks of one 3D range: a hierarchy, not a hedge.  The main peaks stand on the
    summits of the 3D crest (the highest one, the 主峰, a little taller still), lower peaks fill
    the cols between them, narrow peaks rise behind (paler, the back row), broad lower peaks sit
    on the spur roots in front and a few low foot hills fade into the mist."""
    sp = PEAK
    pts, hc = rg.crest, np.asarray(rg.crest_h, np.float64)
    u = F.arclen(pts)
    nrm, tg = F.normals(pts)
    w = rg.width
    out = []
    page = np.clip(hc * sp["page_per_m"], 0, sp["max_page"])
    idx = _summits(u, page, 0.9 * w)
    if not idx:
        return out
    top = max(idx, key=lambda i: page[i])
    mains = []
    for i in idx:
        H = page[i] * (1.1 if i == top else rng.uniform(0.86, 1.0))
        if H < sp["min_page"]:
            continue
        jit = tg[i] * rng.uniform(-0.1, 0.1) * w
        p = _peak("mountain", *(pts[i] + jit), H, rng, 0, sp, rx=H * rng.uniform(0.62, 0.85))
        out.append(p)
        mains.append((i, p))
    # cols: lower peaks where two main peaks leave a gap
    for (a, pa), (b, pb) in zip(mains[:-1], mains[1:]):
        gap = u[b] - u[a]
        free = gap - 0.8 * (pa["rx"] + pb["rx"])
        n_in = int(max(0.0, free) // (0.9 * w)) + (1 if free > 0.25 * w else 0)
        for k in range(1, n_in + 1):
            i = int(np.searchsorted(u, u[a] + gap * k / (n_in + 1)))
            H = max(page[i], 0.6 * min(pa["H"], pb["H"])) * rng.uniform(0.7, 0.85)
            if H >= sp["min_page"]:
                out.append(_peak("mountain", *(pts[i] + tg[i] * rng.uniform(-0.1, 0.1) * w), H, rng, 0, sp,
                                 rx=H * rng.uniform(0.6, 0.8)))
    # the ends: smaller peaks out to where the crest falls into the foothills
    for i0, step in ((mains[0][0], -1), (mains[-1][0], 1)):
        uu = u[i0]
        while True:
            uu += step * 0.85 * w
            if uu < 0 or uu > u[-1]:
                break
            j = int(np.clip(np.searchsorted(u, uu), 0, len(u) - 1))
            if page[j] < sp["min_page"]:
                break
            out.append(_peak("mountain", *pts[j], page[j] * rng.uniform(0.75, 0.9), rng, 0, sp,
                             rx=page[j] * rng.uniform(0.65, 0.85)))
    # back = north (the painting looks from the south), front = south, whatever the range's run
    back = np.tile(np.array([0.0, -1.0]), (len(pts), 1))
    # back row: narrow, paler peaks peeking out between the main ones
    for (a, pa), (b, pb) in zip(mains[:-1], mains[1:]):
        if rng.random() < 0.3:
            continue
        i = (a + b) // 2
        H = max(pa["H"], pb["H"]) * rng.uniform(0.82, 1.0)
        q = pts[i] + back[i] * rng.uniform(0.25, 0.4) * w
        out.append(_peak("mountain", q[0], q[1], H, rng, -1, sp, rx=H * rng.uniform(0.5, 0.65)))
    # front row: broad lower peaks on the spur roots (south side) and a few foot hills
    front = -back
    L = u[-1]
    s = rng.uniform(0.2, 0.6) * w
    while s < L:
        i = min(int(np.searchsorted(u, s)), len(u) - 1)
        if page[i] > 1.5 * sp["min_page"]:
            H = page[i] * rng.uniform(0.4, 0.55)
            q = pts[i] + front[i] * rng.uniform(0.4, 0.6) * w + tg[i] * rng.uniform(-0.2, 0.2) * w
            out.append(_peak("mountain", q[0], q[1], H, rng, 1, sp, rx=H * rng.uniform(0.9, 1.2)))
            if rng.random() < 0.22:
                H2 = max(page[i] * rng.uniform(0.15, 0.22), 9.0)
                q2 = pts[i] + front[i] * rng.uniform(0.85, 1.1) * w + tg[i] * rng.uniform(-0.3, 0.3) * w
                out.append(_peak("hill", q2[0], q2[1], H2, rng, 2, HILL, rx=H2 * rng.uniform(2.0, 2.6)))
        s += w * rng.uniform(0.8, 1.1)
    # near the top edge of the page the peaks must stay low: keep their breadth (broad, domed
    # massifs instead of a hedge of small cones) and drop the crowded small ones
    kept = []
    for p in out:
        H0 = p["H"]
        p["H"] = _clip_page(p["H"], p["y"], p["rx"], PEAK["depth"])
        if p["H"] < 0.8 * H0:
            if p["row"] != 0 or rng.random() < 0.3:
                continue
            p["sharp"] = max(p.get("sharp", 3.0), 3.8)        # the rx of the full peak: broad
        if p["H"] >= 8.0:
            kept.append(p)
    return kept


def _hill_mounds(rg, rng, world):
    """Rows of round mounds (馒头山) along a hill chain."""
    sp = HILL
    pts, hc = rg.crest, np.asarray(rg.crest_h, np.float64)
    u = F.arclen(pts)
    nrm, tg = F.normals(pts)
    w = rg.width
    page = np.clip(hc * sp["page_per_m"], 0, sp["max_page"])
    back = nrm.copy()
    back[back[:, 1] > 0] *= -1
    out = []
    for row, off, hf, step in ((-1, 0.25, 0.85, 1.0), (0, 0.0, 1.0, 0.85)):
        s = rng.uniform(0.1, 0.5) * w
        while s < u[-1]:
            i = min(int(np.searchsorted(u, s)), len(u) - 1)
            H = page[i] * hf * rng.uniform(0.85, 1.1)
            if H >= sp["min_page"]:
                q = pts[i] + back[i] * off * w + tg[i] * rng.uniform(-0.15, 0.15) * w
                out.append(_peak("hill", q[0], q[1], H, rng, row, sp))
            s += w * step * rng.uniform(0.8, 1.2)
    # the mountain ranges' foothill knolls of the 3D map
    for p in out:
        p["H"] = _clip_page(p["H"], p["y"], p["rx"], sp["depth"])
    return [p for p in out if p["H"] >= 8.0]


# ---------------------------------------------------------------------------------------------
# glyph surfaces
# ---------------------------------------------------------------------------------------------
def _ribs(p, rng=None):
    """The ribs (folds) of a painted peak: (angle, start, end, top fraction, width0, width1,
    fall exponent) in units of the peak radius, mostly on the visible (south) side."""
    rng = np.random.default_rng(p["seed"])
    n = p["folds"]
    out = []
    span = math.radians(125.0)
    for k in range(n):
        t = (k + 0.5) / n
        th = math.pi / 2 + (2 * t - 1) * span + rng.uniform(-0.18, 0.18)
        out.append((th, rng.uniform(0.04, 0.16), rng.uniform(0.85, 1.08), rng.uniform(0.72, 0.93),
                    rng.uniform(0.08, 0.13), rng.uniform(0.24, 0.36), rng.uniform(1.1, 1.8)))
    for k in range(2):                           # the back: two ribs for the outline
        th = -math.pi / 2 + (k - 0.5) * 1.6 + rng.uniform(-0.3, 0.3)
        out.append((th, 0.1, 1.0, 0.85, 0.12, 0.4, 1.4))
    return out


def peak_height(p, dx, dy):
    """Height (true m; page = K z) of one glyph at plan offsets (dx, dy) from its base centre,
    plus (rho, rib id fraction, fold weight).

    Mountains: a narrow crown (bell) wrapped in ribs - rounded folds that leave the crown just
    below the summit and fall, widening, to the foot (the 披麻 folds of a blue-green peak); the
    ribs meet in sharp grooves (Freestyle draws them as fold lines) and make the outline lobed.
    Hills: a round mound with shallow folds."""
    kind = p["kind"]
    zt = p["H"] / K
    u = dx / p["rx"]
    v = dy / p["ry"]
    u = u - p["lean"] * np.clip(1.0 - np.hypot(u, v), 0.0, 1.0)
    th = np.arctan2(v, u)
    rho = np.hypot(u, v)
    ph1, ph2, ph3 = p["phase"], p["phase"] * 1.7 + 1.3, p["phase"] * 2.3 + 0.4
    rho = rho * (1.0 + p["wobble"] * (0.55 * np.sin(2 * th + ph1) + 0.3 * np.sin(3 * th + ph2)
                                      + 0.2 * np.sin(5 * th + ph3)))
    u2, v2 = rho * np.cos(th), rho * np.sin(th)
    if kind == "hill":
        z = np.clip(1.0 - rho * rho, 0.0, None) ** 0.75
        rib = np.zeros_like(z)
        fold_w = np.clip(rho, 0, 1) ** 0.7
        psi = 0.5 * p["folds"] * np.arctan2(u, v) + p["phase"] + p["twist"] * rho
        z = z * (1.0 + p["fold_amp"] * (np.abs(np.cos(psi)) ** 0.5 - 0.6) * fold_w)
        return np.maximum(z, 0.0) * zt, rho, (np.sin(psi) * 0.5 + 0.5), fold_w
    wa, ex = p["waist"] * 0.8, p["sharp"]
    b = 1.0 / (1.0 + (rho / wa) ** ex)
    b1 = 1.0 / (1.0 + (1.0 / wa) ** ex)
    z = np.clip((b - b1) / (1.0 - b1), 0.0, None)
    z = z * (1.0 + p.get("tip", 0.0) * np.exp(-(rho / 0.15) ** 2))
    rib = np.full(z.shape, -1.0, np.float32)
    for i, (a, r0, r1, h0, w0, w1, fe) in enumerate(_ribs(p)):
        ca, sa = math.cos(a + p["twist"] * 0.0), math.sin(a)
        al = u2 * ca + v2 * sa
        cr = np.abs(-u2 * sa + v2 * ca)
        t = np.clip((al - r0) / (r1 - r0), 0.0, 1.0)
        # the rib bends a little as it falls (twist)
        cr = np.abs(cr - p["twist"] * 0.12 * t * t)
        wd = w0 + (w1 - w0) * t
        xs = np.sqrt(np.clip(1.0 - (cr / wd) ** 2, 0.0, 1.0))
        hr = h0 * (1.0 - t) ** fe * (1.0 + 0.25 * t * (1.0 - t))
        zr = hr * xs ** 0.7 * T.smoothstep(r0 - 0.1, r0 + 0.02, al)
        win = zr > z
        z = np.where(win, zr, z)
        rib = np.where(win, float(i), rib)
    if p.get("step", 0.0) > 0:
        side = 0.5 + 0.5 * np.cos(th - p["phase"])
        z = np.maximum(z, np.minimum(z + 0.2, p["step"] * T.smoothstep(0.85, 0.45, rho)) * side)
    for (ox, hs) in p["shoulders"]:
        uu, vv = u - ox, v * 1.1
        r2 = np.hypot(uu, vv) / 0.55
        zs = hs * np.clip(1.0 - r2, 0.0, None) ** 1.2 * (1.0 + 0.5 * r2)
        rib = np.where(zs > z, 20.0 + (ox > 0), rib)
        z = np.maximum(z, zs)
    fold_w = T.smoothstep(0.05, 0.3, rho)
    return np.maximum(z, 0.0) * zt, rho, (rib + 1.0) / 24.0, fold_w


RASTER_MARGIN = G.RASTER_MARGIN


def rasterize(peaks, cell=0.5, pad=2, margin=RASTER_MARGIN):
    """Max-composite of all glyph surfaces on a plan grid (``cell`` m): height (true m), glyph
    index, height fraction, rho, fold phase, fold weight."""
    M = float(margin)
    Hn, Wn = int((F.MAP_H + 2 * M) / cell) + 1, int((F.MAP_W + 2 * M) / cell) + 1
    z = np.zeros((Hn, Wn), np.float32)
    idx = np.full((Hn, Wn), -1, np.int32)
    hn = np.zeros((Hn, Wn), np.float32)
    rh = np.zeros((Hn, Wn), np.float32)
    fo = np.zeros((Hn, Wn), np.float32)
    fw = np.zeros((Hn, Wn), np.float32)
    for k, p in enumerate(peaks):
        R = 1.25 * max(p["rx"], p["ry"]) + pad
        x0, x1 = max(0, int((p["x"] + M - R) / cell)), min(Wn, int((p["x"] + M + R) / cell) + 1)
        y0, y1 = max(0, int((p["y"] + M - R) / cell)), min(Hn, int((p["y"] + M + R) / cell) + 1)
        if x1 <= x0 or y1 <= y0:
            continue
        ys, xs = np.mgrid[y0:y1, x0:x1].astype(np.float32) * cell - M
        zz, rr, ff, ww = peak_height(p, xs - p["x"], ys - p["y"])
        sub = z[y0:y1, x0:x1]
        msk = zz > sub
        sub[msk] = zz[msk]
        idx[y0:y1, x0:x1][msk] = k
        hn[y0:y1, x0:x1][msk] = (zz / (p["H"] / K))[msk]
        rh[y0:y1, x0:x1][msk] = rr[msk]
        fo[y0:y1, x0:x1][msk] = ff[msk]
        fw[y0:y1, x0:x1][msk] = ww[msk]
    return {"z": z, "idx": idx, "hn": hn, "rho": rh, "fold": fo, "fold_w": fw,
            "cell": cell, "origin": -M}


# ---------------------------------------------------------------------------------------------
# Blender
# ---------------------------------------------------------------------------------------------
AOVS = (("gA", "COLOR"), ("gB", "COLOR"), ("gC", "COLOR"), ("gD", "COLOR"), ("gE", "COLOR"))
ATTRS = (("gA", ("hn", "rho", "rand")), ("gB", ("fold", "fold_w", "kind")), ("gC", ("row", "hpage", "crown")),
         ("gD", ("oid", "oid2", "crown")), ("gE", ("sx", "sy", "crown")))


def glyph_material(name="MapGlyphMat"):
    """Flat white emission (coverage) + the attribute AOVs the painter reads."""
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    N, L = nt.nodes, nt.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial")
    em = N.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.0
    em.inputs["Color"].default_value = (1, 1, 1, 1)
    L.new(em.outputs[0], out.inputs["Surface"])
    attr = {}
    for _aov, names in ATTRS:
        for nm in names:
            a = N.new("ShaderNodeAttribute")
            a.attribute_type = "GEOMETRY"
            a.attribute_name = nm
            attr[nm] = a.outputs["Fac"]
    for aov_name, (c0, c1, c2) in ATTRS:
        comb = N.new("ShaderNodeCombineXYZ")
        L.new(attr[c0], comb.inputs[0])
        L.new(attr[c1], comb.inputs[1])
        L.new(attr[c2], comb.inputs[2])
        aov = N.new("ShaderNodeOutputAOV")
        if hasattr(aov, "aov_name"):
            aov.aov_name = aov_name
        else:
            aov.name = aov_name
        L.new(comb.outputs[0], aov.inputs["Color"])
    return mat


def setup_aovs():
    import bpy
    vl = bpy.context.view_layer
    have = [a.name for a in vl.aovs]
    for nm, ty in AOVS:
        if nm not in have:
            a = vl.aovs.add()
            a.name = nm
            a.type = ty
    vl.use_pass_z = True


def build_relief_glyphs(r, peaks, mat, name="Glyphs", box=None):
    """Mesh of the rasterised glyph surfaces, sheared into the oblique view."""
    z, cell = r["z"], r["cell"]
    on = z > 0.01
    ring = on.copy()
    ring[1:] |= on[:-1]
    ring[:-1] |= on[1:]
    ring[:, 1:] |= on[:, :-1]
    ring[:, :-1] |= on[:, 1:]
    if box is not None:
        x0, y0, x1, y1 = box
        o = r["origin"]
        m = np.zeros_like(ring)
        m[max(0, int((y0 - o) / cell)):max(0, int((y1 - o) / cell) + 1),
          max(0, int((x0 - o) / cell)):max(0, int((x1 - o) / cell) + 1)] = True
        ring &= m
    ys, xs = np.mgrid[0:z.shape[0], 0:z.shape[1]].astype(np.float32) * cell + r["origin"]
    X, Y, Z = G.shear(xs, ys, np.where(on, z, -3.0))
    idx = r["idx"]
    idx2 = idx.copy()
    for _ in range(2):
        for sy, sx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = np.roll(np.roll(idx2, sy, 0), sx, 1)
            idx2 = np.where(idx2 < 0, nb, idx2)
    rand = np.array([p["rand"] for p in peaks] + [0.0], np.float32)
    kind = np.array([KIND_MOUNTAIN if p["kind"] == "mountain" else KIND_HILL for p in peaks] + [0], np.float32)
    row = np.array([p["row"] for p in peaks] + [0], np.float32)
    hpage = np.array([p["H"] / 160.0 for p in peaks] + [0.0], np.float32)
    attrs = {"hn": r["hn"], "rho": r["rho"], "rand": rand[idx2], "fold": r["fold"],
             "fold_w": r["fold_w"], "kind": kind[idx2] / 2.0, "row": row[idx2] / 4.0 + 0.5,
             "hpage": hpage[idx2], "crown": np.zeros_like(r["hn"])}
    return G._mesh_from_grid(name, X, Y, Z, ring, attrs, mat)


def build_peak_objects(peaks, mat, collection, box=None, cell_div=42.0):
    """One mesh object per glyph (so Freestyle's per-object *contour* outlines every peak, also
    where it stands in front of another one), sheared into the oblique view.  The foot ring dips
    below the holdout ground, so a peak meets the ground without an outline."""
    import bpy
    objs = []
    for k, p in enumerate(peaks):
        R = 1.25 * max(p["rx"], p["ry"]) + 2.0
        if box is not None:
            x0, y0, x1, y1 = box
            if p["x"] + R < x0 or p["x"] - R > x1 or p["y"] + R < y0 or p["y"] - 1.3 * p["H"] - R > y1:
                continue
        cell = max(0.4, min(p["rx"], p["ry"] * 1.6) / cell_div)
        n = int(math.ceil(R / cell))
        g = (np.arange(-n, n + 1, dtype=np.float32)) * cell
        dy, dx = np.meshgrid(g, g, indexing="ij")
        z, rho, fold, fw = peak_height(p, dx, dy)
        on = z > 0.004 * p["H"] / K
        if on.sum() < 9:
            continue
        ring = on.copy()
        ring[1:] |= on[:-1]
        ring[:-1] |= on[1:]
        ring[:, 1:] |= on[:, :-1]
        ring[:, :-1] |= on[:, 1:]
        X, Y, Z = G.shear(p["x"] + dx, p["y"] + dy, np.where(on, z, -3.0))
        hn = z / (p["H"] / K)
        jm = np.unravel_index(int(np.argmax(z)), z.shape)
        sx = p["x"] + float(dx[jm])                   # the summit on the page
        sy = p["y"] + float(dy[jm]) - K * float(z[jm])
        kind = KIND_MOUNTAIN if p["kind"] == "mountain" else KIND_HILL
        full = np.ones_like(z)
        attrs = {"hn": hn, "rho": rho, "rand": full * p["rand"], "fold": fold, "fold_w": fw,
                 "kind": full * kind / 2.0, "row": full * (p["row"] / 4.0 + 0.5),
                 "hpage": full * p["H"] / 160.0, "crown": full * 0.0,
                 "oid": full * ((k % 997) + 1) / 1000.0, "oid2": full * ((k // 997) + 1) / 8.0,
                 "sx": full * sx / F.MAP_W, "sy": full * sy / F.MAP_H}
        ob = G._mesh_from_grid("Peak_%04d" % k, X, Y, Z, ring, attrs, mat)
        for c in ob.users_collection:
            c.objects.unlink(ob)
        collection.objects.link(ob)
        objs.append(ob)
    return objs


# ---------------------------------------------------------------------------------------------
# painted trees
# ---------------------------------------------------------------------------------------------
#: page size of the tree glyphs at s = 1 (crown width, total height in px of WorldMap.png)
TREE_GLYPH = {"broad": (12.0, 14.0), "pine": (11.0, 16.0), "bamboo": (7.0, 15.0)}
TREE_VARIANTS = 6


def _tree_parts(kind, rng):
    """Painted tree as a few solids in *page* units (1 = 1 px of WorldMap.png)."""
    cw, ht = TREE_GLYPH[kind]
    E = G._ellipsoid
    parts = []
    if kind == "broad":
        trunk_h = rng.uniform(0.25, 0.38) * ht
        lean = rng.uniform(-0.1, 0.1) * cw
        parts.append(("trunk", E(0.5 * lean, 0, 0.5 * trunk_h, 0.55, 0.55, 0.55 * trunk_h, 8, 4)))
        n = int(rng.integers(4, 7))
        for k in range(n):
            a = 2 * np.pi * k / n + rng.uniform(-0.5, 0.5)
            rr = rng.uniform(0.16, 0.25) * cw
            cx = lean + np.cos(a) * rng.uniform(0.15, 0.3) * cw
            cy = np.sin(a) * 0.1 * cw
            cz = trunk_h + rng.uniform(0.2, 0.62) * (ht - trunk_h)
            parts.append(("crown", E(cx, cy, cz, rr, 0.8 * rr, 0.8 * rr, 10, 6, 0.15, rng)))
        parts.append(("crown", E(lean, 0, ht - 0.26 * cw, 0.26 * cw, 0.2 * cw, 0.24 * cw, 10, 6, 0.15, rng)))
    elif kind == "pine":
        lean = rng.uniform(-0.18, 0.18) * cw
        parts.append(("trunk", E(0.5 * lean, 0, 0.5 * ht, 0.5, 0.5, 0.5 * ht, 8, 4)))
        n = int(rng.integers(3, 5))
        for k in range(n):
            t = 0.4 + 0.6 * k / max(1, n - 1)
            wd = cw * (0.5 - 0.28 * t + rng.uniform(-0.05, 0.05))
            side = rng.uniform(-0.22, 0.22) * cw
            parts.append(("crown", E(lean * t + side, 0, t * ht * 0.93, wd, 0.7 * wd, 0.14 * cw, 12, 4, 0.12, rng)))
    else:   # bamboo: a clump of narrow leaf masses on thin culms
        n = int(rng.integers(3, 5))
        for k in range(n):
            ox = (k - 0.5 * (n - 1)) * 0.24 * cw + rng.uniform(-0.1, 0.1) * cw
            hh = ht * rng.uniform(0.7, 1.0)
            parts.append(("trunk", E(ox, 0, 0.5 * hh, 0.3, 0.3, 0.5 * hh, 6, 4)))
            parts.append(("crown", E(ox + rng.uniform(-0.8, 0.8), 0, 0.66 * hh, 0.2 * cw,
                                     0.16 * cw, 0.32 * hh, 10, 7, 0.2, rng)))
    return parts


def tree_prototypes(collection, seed=77):
    """Pre-sheared painted tree prototypes {(kind, variant): object} with the glyph attributes."""
    import bpy
    protos = {}
    mat = bpy.data.materials.get("MapGlyphMat") or glyph_material()
    rng = np.random.default_rng(seed)
    for kind in ("broad", "pine", "bamboo"):
        for vi in range(TREE_VARIANTS):
            verts, faces, hn, crown = [], [], [], []
            ht = TREE_GLYPH[kind][1]
            for (part, (v, f)) in _tree_parts(kind, rng):
                base = len(verts)
                v = np.asarray(v, np.float32)
                verts.extend(v.tolist())
                faces.extend([tuple(base + i for i in q) for q in f])
                hn.extend((np.clip(v[:, 2] / ht, 0, 1)).tolist())
                crown.extend([0.0 if part == "trunk" else 1.0] * len(v))
            v = np.asarray(verts, np.float32)
            dx, dy, dz = v[:, 0], v[:, 1], v[:, 2] / K
            X = dx
            Y = -(dy - K * dz)
            Z = dy * CE + dz * SE
            me = bpy.data.meshes.new("MTree_%s_%d" % (kind, vi))
            me.from_pydata(np.stack([X, Y, Z], -1).tolist(), [], faces)
            me.update()
            r_ = float(rng.random())
            spc = {"broad": 0.2, "pine": 0.5, "bamboo": 0.8}[kind]
            nv = len(v)
            for nm, arr in (("hn", hn), ("rho", [spc] * nv), ("rand", [r_] * nv), ("fold", [0.5] * nv),
                            ("fold_w", [0.0] * nv), ("kind", [KIND_TREE / 2.0] * nv),
                            ("row", [0.5] * nv), ("hpage", [0.0] * nv), ("crown", crown),
                            ("oid", [0.0] * nv), ("oid2", [0.0] * nv), ("sx", [0.0] * nv),
                            ("sy", [0.0] * nv)):
                at = me.attributes.new(nm, "FLOAT", "POINT")
                at.data.foreach_set("value", np.asarray(arr, np.float32))
            # the ellipsoid poles are rings of coincident vertices: degenerate quads give
            # Freestyle undefined normals (a stray straight stroke across the map) - weld them
            import bmesh
            bm = bmesh.new()
            bm.from_mesh(me)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
            bmesh.ops.dissolve_degenerate(bm, dist=1e-4, edges=bm.edges)
            bm.to_mesh(me)
            bm.free()
            me.update()
            for poly in me.polygons:
                poly.use_smooth = True
            me.materials.append(mat)
            ob = bpy.data.objects.new(me.name, me)
            collection.objects.link(ob)
            ob.location = (0.0, 0.0, -10000.0)
            ob.hide_render = True
            protos[(kind, vi)] = ob
    return protos


def instance_trees(trees, protos, collection, seed=5):
    """One geometry-nodes point cloud per prototype; instances keep the prototype's sheared shape
    (no yaw: a rotation would not commute with the shear) and scale by ``ps``."""
    import bpy
    rng = np.random.default_rng(seed)
    groups = {}
    for t in trees:
        vi = int(rng.integers(TREE_VARIANTS))
        groups.setdefault((t["t"], vi), []).append(t)
    objs = []
    for key, pts in groups.items():
        proto = protos[key]
        x = np.array([t["x"] for t in pts], np.float32)
        y = np.array([t["y"] for t in pts], np.float32)
        s = np.array([t.get("ps", t["s"]) for t in pts], np.float32)
        z = np.array([t.get("z", 0.0) for t in pts], np.float32)
        X, Y, Z = G.shear(x, y, z)
        me = bpy.data.meshes.new("MTreePts_%s_%d" % key)
        me.vertices.add(len(pts))
        me.vertices.foreach_set("co", np.stack([X, Y, Z], -1).reshape(-1))
        at = me.attributes.new("s", "FLOAT", "POINT")
        at.data.foreach_set("value", s)
        ob = bpy.data.objects.new(me.name, me)
        collection.objects.link(ob)
        ng = bpy.data.node_groups.new("MTreeGlyph_%s_%d" % key, "GeometryNodeTree")
        ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        N, L = ng.nodes, ng.links
        gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
        iop = N.new("GeometryNodeInstanceOnPoints")
        oi = N.new("GeometryNodeObjectInfo")
        oi.inputs["Object"].default_value = proto
        oi.transform_space = "ORIGINAL"
        sa = N.new("GeometryNodeInputNamedAttribute")
        sa.data_type = "FLOAT"
        sa.inputs["Name"].default_value = "s"
        real = N.new("GeometryNodeRealizeInstances")
        L.new(gi.outputs[0], iop.inputs["Points"])
        L.new(oi.outputs["Geometry"], iop.inputs["Instance"])
        L.new(sa.outputs["Attribute"], iop.inputs["Scale"])
        L.new(iop.outputs["Instances"], real.inputs[0])
        L.new(real.outputs[0], go.inputs[0])
        mod = ob.modifiers.new("Instances", "NODES")
        mod.node_group = ng
        objs.append(ob)
    return objs


def map_trees(world, trees, seed=91):
    """The trees the painting shows: the scenario woods and copses (thinned to a painter's
    density), the hill and mountain groves, some riverside trees; the open land stays open.
    ``ps`` = page scale, ``z`` = the glyph surface under a tree on a painted peak (set later)."""
    rng = np.random.default_rng(seed)
    out = []
    for t in trees:
        cat = t.get("_cat", "forest")
        if cat == "lone" and rng.random() < 0.7:
            continue
        if cat == "riparian" and rng.random() < 0.5:
            continue
        if cat == "mountain" and rng.random() < 0.55:
            continue
        if cat == "forest" and rng.random() < (0.7 if t["s"] < 0.66 else 0.22):
            continue                      # a painter's wood: groups of trees, silk between them
        out.append(dict(t, ps=round(float(max(t["s"], 0.55)) * 1.25, 3)))
    return out


def raster_z(r, x, y):
    """Glyph surface height (true m) at map point (x, y) (nearest raster cell)."""
    j = int(round((y - r["origin"]) / r["cell"]))
    i = int(round((x - r["origin"]) / r["cell"]))
    if 0 <= j < r["z"].shape[0] and 0 <= i < r["z"].shape[1]:
        return float(r["z"][j, i])
    return 0.0


def ink_lines(ss, contour_px=1.3, fold_px=0.0, tree_px=0.7, relief_collection=None, tree_collection=None):
    """Freestyle brush ink as a render pass: the bold tapered calligraphic contour of the peaks
    (silhouettes), lighter fold lines along the grooves between the ribs (creases) and the fine
    outline of the trees."""
    import bpy
    from . import ink as INK
    INK._patch_freestyle()
    sc = bpy.context.scene
    sc.render.use_freestyle = True
    sc.render.line_thickness_mode = "ABSOLUTE"
    sc.render.line_thickness = 1.0
    vl = bpy.context.view_layer
    vl.use_freestyle = True
    fs = vl.freestyle_settings
    fs.mode = "EDITOR"
    fs.as_render_pass = True
    fs.crease_angle = math.radians(150.0)
    fs.use_culling = False
    fs.use_smoothness = True
    while len(fs.linesets) > 0:
        fs.linesets.remove(fs.linesets[0])

    def style(name, px, alpha, calligraphy, noise, tip=(0.15, 0.1), min_len=0.0, seed=7):
        st = INK._style(name, "Ink", alpha, px, ss, True, calligraphy, noise, 0.0, True, seed)
        st.color = (1.0, 1.0, 1.0)
        if min_len > 0:
            st.use_length_min = True
            st.length_min = min_len * ss
        for m in st.thickness_modifiers:
            if m.type == "ALONG_STROKE":
                pts = m.curve.curves[0].points
                pts[0].location = (0.0, tip[0])
                pts[-1].location = (1.0, tip[1])
                m.curve.update()
        return st

    def lineset(name, st, sil, crease, ext, coll):
        ls = fs.linesets.new(name)
        ls.linestyle = st
        ls.select_by_visibility = True
        ls.visibility = "VISIBLE"
        ls.select_by_edge_types = True
        ls.select_silhouette = sil
        ls.select_border = False
        ls.select_crease = crease
        ls.select_contour = ext
        ls.select_external_contour = False
        ls.select_suggestive_contour = False
        ls.select_material_boundary = False
        if coll is not None:
            ls.select_by_collection = True
            ls.collection = coll
            ls.collection_negation = "INCLUSIVE"
        return ls

    lineset("Contour", style("InkContour", contour_px, 1.0, 0.5, 0.45, min_len=3.0), True, False, True,
            relief_collection)
    if fold_px > 0:
        lineset("Folds", style("InkFold", fold_px, 0.8, 0.4, 0.5, tip=(0.05, 0.25), min_len=4.0, seed=11),
                False, True, False, relief_collection)
    if tree_collection is not None:
        lineset("Trees", style("InkTree", tree_px, 0.9, 0.2, 0.2, seed=13), True, False, True,
                tree_collection)


def comp_passes(out_dir, tag):
    """Compositor: write Image, Freestyle, the AOVs and Depth as float EXRs."""
    import bpy
    import os
    sc = bpy.context.scene
    sc.use_nodes = True
    nt = sc.node_tree
    nt.nodes.clear()
    rl = nt.nodes.new("CompositorNodeRLayers")
    comp = nt.nodes.new("CompositorNodeComposite")
    nt.links.new(rl.outputs["Image"], comp.inputs["Image"])
    fo = nt.nodes.new("CompositorNodeOutputFile")
    fo.base_path = out_dir
    fo.format.file_format = "OPEN_EXR"
    fo.format.color_depth = "32"
    fo.format.exr_codec = "ZIP"
    fo.file_slots.clear()
    names = []
    for sock in ("Image", "Freestyle", "gA", "gB", "gC", "gD", "gE", "Depth"):
        if sock not in rl.outputs:
            continue
        fo.file_slots.new("%s_%s_" % (tag, sock))
        nt.links.new(rl.outputs[sock], fo.inputs[len(fo.inputs) - 1])
        names.append(sock)
    return [os.path.join(out_dir, "%s_%s_0001.exr" % (tag, s)) for s in names], names
