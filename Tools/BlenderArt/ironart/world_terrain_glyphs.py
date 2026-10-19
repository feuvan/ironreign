"""World Terrain family - pictorial mountains, hills and trees of the 2D gongbi map (WorldMap.png).

The painted map is a plan view (land, coast, rivers, lakes keep their exact map positions), but
mountains, hills and trees are drawn *pictorially*, as seen from the south in slight elevation,
like the peaks of a Ming/Qing court map (舆图) painted in the blue-green manner.

Projection.  An oblique parallel projection onto the ground plane: a point (x, y, z) of the map
(x east, y south, z up, metres) is drawn at image point (x, y - K * z) with K = cot(e), e = the
elevation of the view.  Ground points stay exactly where the map says; heights rise up the page.
Blender renders it with an ordinary top-down orthographic camera on *sheared* geometry
(:func:`shear`): the linear map (x, y, z) -> (x, y - K z, y cos e + z sin e) keeps the depth order
of the oblique view and maps its view direction onto the camera axis, so Freestyle finds exactly
the silhouettes of the oblique view.

Glyphs.
    peaks     along every mountain stroke: 2-3 staggered rows of steep peaks (folded faces that
              radiate from the summit, shoulder summits, a slight lean), sized by the 3D range
              under them (so the painted ranges and the Unreal relief agree: a gorge or a city
              basin in 3D is a gap or a low col in the painting) and kept clear of the cities
    hills     rows of low rounded mounds (馒头山) along the hill strokes
    trees     the plain trees of Trees.json as small painted trees (pine / broadleaf / bamboo)

The glyph surfaces carry attributes rendered as AOVs (normalised height within the glyph, the
angle/radius around its summit, an id and its kind); :mod:`ironart.world_terrain_gongbi` paints
the mineral washes, texture strokes and mist from them, and lays the Freestyle ink on top.
"""

import math

import numpy as np

from . import terrain as T
from . import world_terrain_fields as F

#: view elevation (deg) of the pictorial glyphs and the resulting height -> page factor
ELEV_DEG = 38.0
K = 1.0 / math.tan(math.radians(ELEV_DEG))
CE, SE = math.cos(math.radians(ELEV_DEG)), math.sin(math.radians(ELEV_DEG))

KIND_MOUNTAIN, KIND_HILL, KIND_TREE = 0, 1, 2

#: glyph design numbers (metres in plan; heights in *page* metres = pixels of WorldMap.png)
GLYPH = {
    "mountain": dict(rows=((-0.45, 1.0), (-0.08, 0.88), (0.3, 0.74), (0.62, 0.5)), spacing=0.55,
                     rx=(0.5, 0.85), ry_frac=0.5, page_per_m=0.82, min_page=30.0, max_page=150.0,
                     folds=(4, 7), fold_amp=0.12, lean=0.18, shoulder=(1, 2), waist=(0.36, 0.5)),
    "hill": dict(rows=((-0.25, 1.0), (0.3, 0.75)), spacing=0.7, rx=(0.55, 0.85), ry_frac=0.5,
                 page_per_m=0.55, min_page=12.0, max_page=34.0, folds=(3, 5), fold_amp=0.06,
                 lean=0.06, shoulder=(0, 1), waist=(0.4, 0.4)),
}
#: page clearance (px) kept around each city point: no glyph may cover it (the UI draws the
#: city icon, its banner and its label there)
CITY_CLEAR_PX = {1: 34.0, 2: 42.0, 3: 52.0}


def shear(x, y, z):
    """Map (x east, y south, z up) -> Blender (X, Y, Z) of the oblique-view scene (see doc)."""
    X = np.asarray(x, np.float32) - F.MAP_W / 2.0
    Y = F.MAP_H / 2.0 - (np.asarray(y, np.float32) - K * np.asarray(z, np.float32))
    Z = np.asarray(y, np.float32) * CE + np.asarray(z, np.float32) * SE
    return X, Y, Z


# ---------------------------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------------------------
def _ridge_height(world, pts, a):
    """Height of the 3D range under a stroke: max terrain height within ``a`` of each sample."""
    h = world.f["h"]
    nrm, _ = F.normals(pts)
    out = np.zeros(len(pts), np.float32)
    for off in np.linspace(-a, a, 9):
        q = pts + nrm * off
        out = np.maximum(out, F.sample(h, q[:, 0], q[:, 1]))
    return out


def layout(world, seed=4242):
    """All mountain and hill peaks: dicts with plan centre (x, y), radii rx / ry (m), page height
    H, lean, folds, shoulder summits, kind and id.  Deterministic for ``seed``."""
    rng = np.random.default_rng(seed)
    peaks = []
    cities = world.cities
    for kind, strokes in (("mountain", world.m["mountains"]), ("hill", world.m["hills"])):
        g = GLYPH[kind]
        for si, st in enumerate(strokes):
            w = float(st["width"])
            pts = F.smooth_line(F.resample(st["points"], 4.0), 7.0)
            L = float(F.arclen(pts)[-1])
            nrm, tg = F.normals(pts)
            base_h = _ridge_height(world, pts, 0.6 * w)
            cum = F.arclen(pts)
            # rows from the back (north side of the stroke) to the front
            for ri, (off, hf) in enumerate(g["rows"]):
                rx_mean = 0.5 * (g["rx"][0] + g["rx"][1]) * w
                step = g["spacing"] * rx_mean * 2.0
                u = rng.uniform(0.15, 0.65) * step
                while u < L - 0.1 * step:
                    i = int(np.searchsorted(cum, u))
                    i = min(i, len(pts) - 1)
                    n_ = nrm[i]
                    # "back" = towards the north (negative y) whatever the stroke direction
                    sgn = -1.0 if n_[1] > 0 else 1.0
                    if abs(n_[1]) < 0.25:              # a north-south stroke: rows east / west
                        sgn = 1.0 if ri % 2 else -1.0
                    c = pts[i] + n_ * sgn * off * w + tg[i] * rng.uniform(-0.15, 0.15) * step
                    th = float(base_h[i])
                    page = th * g["page_per_m"] * hf * rng.uniform(0.85, 1.12)
                    end = min(u, L - u) / max(1.0, 0.9 * w)
                    page *= 0.55 + 0.45 * min(1.0, end)
                    rx = rng.uniform(*g["rx"]) * w * (0.75 + 0.25 * hf)
                    # the whole glyph stays on the page (no peak cut by the map's top edge)
                    ry_est = rx * g["ry_frac"] * 1.15
                    page = min(page, (float(c[1]) - ry_est - 8.0) / 1.18)
                    if page >= g["min_page"] * (0.8 if ri == len(g["rows"]) - 1 else 1.0):
                        page = min(page, g["max_page"])
                        peaks.append(dict(kind=kind, x=float(c[0]), y=float(c[1]), rx=float(rx),
                                          ry=float(rx * g["ry_frac"] * rng.uniform(0.85, 1.15)),
                                          H=float(page), lean=float(rng.uniform(-1, 1) * g["lean"]),
                                          folds=int(rng.integers(g["folds"][0], g["folds"][1] + 1)),
                                          phase=float(rng.uniform(0, 2 * np.pi)),
                                          twist=float(rng.uniform(-0.8, 0.8)),
                                          shoulders=[(float(rng.uniform(0.3, 0.6)) * rng.choice([-1, 1]),
                                                      float(rng.uniform(0.5, 0.78)))
                                                     for _ in range(int(rng.integers(g["shoulder"][0],
                                                                                    g["shoulder"][1] + 1)))],
                                          waist=float(rng.uniform(*g["waist"])),
                                          **_archetype(kind, rng),
                                          row=ri, stroke=si, seed=int(rng.integers(1 << 30))))
                    u += step * rng.uniform(0.8, 1.2)
    # islands: a small blue-green peak (or two) rising from each island
    g = GLYPH["mountain"]
    for poly in world.m["land"][1:]:
        xs_ = [q[0] for q in poly]
        ys_ = [q[1] for q in poly]
        cx, cy = float(np.mean(xs_)), float(np.mean(ys_))
        rad = 0.5 * max(np.ptp(xs_), np.ptp(ys_))
        n_pk = 1 if rad < 55 else 2
        for k in range(n_pk):
            ox = (k - 0.5 * (n_pk - 1)) * 0.6 * rad
            rx = rad * (0.42 if n_pk == 1 else 0.36) * rng.uniform(0.9, 1.1)
            peaks.append(dict(kind="mountain", x=cx + ox, y=cy + 0.15 * rad, rx=float(rx),
                              ry=float(rx * 0.55), H=float(rad * rng.uniform(0.7, 0.9) * (1.0 - 0.25 * k)),
                              lean=float(rng.uniform(-1, 1) * g["lean"]),
                              folds=int(rng.integers(g["folds"][0], g["folds"][1] + 1)),
                              phase=float(rng.uniform(0, 2 * np.pi)), twist=float(rng.uniform(-0.8, 0.8)),
                              shoulders=[(float(rng.uniform(0.3, 0.6)) * rng.choice([-1, 1]), 0.6)],
                              waist=float(rng.uniform(*g["waist"])), **_archetype("mountain", rng),
                              row=0, stroke=-1, seed=int(rng.integers(1 << 30))))
    # keep the cities clear: shrink (or drop) a glyph whose page footprint covers a city
    kept = []
    for p in peaks:
        for (_k, cx, cy, s) in cities:
            p = _clear_city(p, cx, cy, CITY_CLEAR_PX[s])
            if p is None:
                break
        if p is not None:
            kept.append(p)
    # draw order / ids: back to front
    kept.sort(key=lambda p: (p["y"], p["x"]))
    for i, p in enumerate(kept):
        p["id"] = i
        p["rand"] = float(np.random.default_rng(p["seed"]).random())
    return kept


def _archetype(kind, rng):
    """Per-peak form: spire, domed crown, twin summit, stepped cliff or plain peak."""
    if kind == "hill":
        return dict(wobble=float(rng.uniform(0.03, 0.08)), sharp=2.0, tip=0.0, step=0.0, fold_k=1.0)
    r = rng.random()
    if r < 0.22:      # spire
        return dict(wobble=float(rng.uniform(0.04, 0.1)), sharp=float(rng.uniform(2.4, 3.0)),
                    tip=float(rng.uniform(0.05, 0.15)), step=0.0, fold_k=1.3, waist_mul=0.8)
    if r < 0.45:      # domed crown
        return dict(wobble=float(rng.uniform(0.06, 0.14)), sharp=float(rng.uniform(3.6, 4.6)),
                    tip=0.0, step=0.0, fold_k=0.9, waist_mul=1.15)
    if r < 0.62:      # stepped cliff
        return dict(wobble=float(rng.uniform(0.05, 0.12)), sharp=float(rng.uniform(3.0, 3.8)),
                    tip=0.0, step=float(rng.uniform(0.45, 0.65)), fold_k=1.1, waist_mul=1.0)
    return dict(wobble=float(rng.uniform(0.05, 0.13)), sharp=float(rng.uniform(2.8, 3.6)),
                tip=float(rng.uniform(0.0, 0.08)), step=0.0, fold_k=1.0, waist_mul=1.0)


def _clear_city(p, cx, cy, r):
    """Shrink the glyph until its page silhouette (an ellipse base + a triangle up to the
    summit) stays ``r`` px from the city point; None if it would become too small."""
    for _ in range(12):
        if not _covers(p, cx, cy, r):
            return p
        p = dict(p, H=p["H"] * 0.82, rx=p["rx"] * 0.9, ry=p["ry"] * 0.9)
        if p["H"] < 10.0 or p["rx"] < 10.0:
            return None
    return None if _covers(p, cx, cy, r) else p


def _covers(p, cx, cy, r):
    # page footprint bounding box: x +- rx, y from (base + ry) up to (base - ry - H)
    x0, x1 = p["x"] - p["rx"] - r, p["x"] + p["rx"] + r
    y0, y1 = p["y"] - p["ry"] - p["H"] - r, p["y"] + p["ry"] + r
    if not (x0 < cx < x1 and y0 < cy < y1):
        return False
    # finer: distance to the triangle (base corners, summit) and the base ellipse
    sx, sy = p["x"] + p["lean"] * p["rx"], p["y"] - p["H"]
    tri = [(p["x"] - p["rx"], p["y"]), (p["x"] + p["rx"], p["y"]), (sx, sy)]
    if _pt_in_tri((cx, cy), tri):
        return True
    for (a, b) in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
        if _seg_dist((cx, cy), a, b) < r:
            return True
    e = ((cx - p["x"]) / (p["rx"] + r)) ** 2 + ((cy - p["y"]) / (p["ry"] + r)) ** 2
    return e < 1.0


def _pt_in_tri(q, t):
    (x1, y1), (x2, y2), (x3, y3) = t
    d = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    if abs(d) < 1e-9:
        return False
    a = ((y2 - y3) * (q[0] - x3) + (x3 - x2) * (q[1] - y3)) / d
    b = ((y3 - y1) * (q[0] - x3) + (x1 - x3) * (q[1] - y3)) / d
    return a >= 0 and b >= 0 and a + b <= 1


def _seg_dist(q, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((q[0] - ax) * dx + (q[1] - ay) * dy) / (dx * dx + dy * dy + 1e-9)))
    return math.hypot(ax + t * dx - q[0], ay + t * dy - q[1])


# ---------------------------------------------------------------------------------------------
# glyph surfaces (numpy)
# ---------------------------------------------------------------------------------------------
def peak_height(p, dx, dy):
    """Height (true metres, page = K * z) of one glyph at plan offsets (dx, dy) from its base
    centre, plus (theta, rho) around its summit and the fold phase ``psi`` (a fold crest
    wherever psi = pi/2 + k pi; its branch cut lies on the hidden north face)."""
    kind = p["kind"]
    zt = p["H"] / K                                   # true height that draws H px tall
    u = dx / p["rx"]
    v = dy / p["ry"]
    # lean: the summit sits off-centre, the faces follow
    u = u - p["lean"] * np.clip(1.0 - np.hypot(u, v), 0.0, 1.0)
    th = np.arctan2(v, u)
    rho = np.hypot(u, v)
    # an irregular outline: the radius wanders with the angle (craggy, never a perfect cone)
    ph1, ph2 = p["phase"], p["phase"] * 1.7 + 1.3
    rho = rho * (1.0 + p.get("wobble", 0.0) * (0.65 * np.sin(2 * th + ph1) + 0.35 * np.sin(3 * th + ph2)))
    m = p["folds"]
    psi = 0.5 * m * np.arctan2(u, v) + p["phase"] + p["twist"] * rho
    if kind == "hill":
        z0 = np.clip(1.0 - rho * rho, 0.0, None) ** 0.9
        fold_w = np.clip(rho, 0, 1) ** 0.6
    else:
        # a painted peak: crown, steep faces, a short flared foot (normalised bell); the crown
        # sharpness and the waist vary per peak (spires .. domed crowns)
        wa = p.get("waist", 0.42) * p.get("waist_mul", 1.0)
        ex = p.get("sharp", 3.2)
        b = 1.0 / (1.0 + (rho / wa) ** ex)
        b1 = 1.0 / (1.0 + (1.0 / wa) ** ex)
        z0 = np.clip((b - b1) / (1.0 - b1), 0.0, None)
        tip = p.get("tip", 0.0)
        z0 = z0 * (1.0 + tip * np.exp(-(rho / 0.16) ** 2))
        fold_w = T.smoothstep(0.1, 0.4, rho)
        # a cliff step on one side (stepped peaks)
        if p.get("step", 0.0) > 0:
            side = 0.5 + 0.5 * np.cos(th - p["phase"])
            z0 = np.maximum(z0, np.minimum(z0 + 0.25, p["step"] * T.smoothstep(0.85, 0.45, rho)) * side)
    f = 1.0 - np.abs(np.sin(psi))
    z = z0 * (1.0 + GLYPH[kind]["fold_amp"] * p.get("fold_k", 1.0) * (f - 0.5) * fold_w * 2.0)
    for (ox, hs) in p["shoulders"]:
        uu, vv = u - ox, v * 1.1
        r2 = np.hypot(uu, vv) / 0.55
        zs = hs * np.clip(1.0 - r2, 0.0, None) ** 1.2 * (1.0 + 0.5 * r2)
        psi = np.where(zs > z, 0.0, psi)
        fold_w = np.where(zs > z, 0.0, fold_w)
        z = np.maximum(z, zs)
    return np.maximum(z, 0.0) * zt, th, rho, psi, fold_w


RASTER_MARGIN = 80.0       # the glyph raster reaches past the map edge: feet cut by the
                           # frame stay closed surfaces (no outline along the page border)


def rasterize(peaks, cell=1.0, pad=2, margin=RASTER_MARGIN):
    """Max-composite of all glyph surfaces on a plan grid (``cell`` m): height (true m), glyph
    index, its normalised height, theta, rho.  Grid point (j, i) is map point
    (i * cell - margin, j * cell - margin).  Returns a dict of arrays (+ ``origin``)."""
    M = float(margin)
    Hn, Wn = int((F.MAP_H + 2 * M) / cell) + 1, int((F.MAP_W + 2 * M) / cell) + 1
    z = np.zeros((Hn, Wn), np.float32)
    idx = np.full((Hn, Wn), -1, np.int32)
    hn = np.zeros((Hn, Wn), np.float32)
    th = np.zeros((Hn, Wn), np.float32)
    rh = np.zeros((Hn, Wn), np.float32)
    fo = np.zeros((Hn, Wn), np.float32)
    fw = np.zeros((Hn, Wn), np.float32)
    for k, p in enumerate(peaks):
        R = 1.2 * max(p["rx"], p["ry"]) + pad
        x0, x1 = max(0, int((p["x"] + M - R) / cell)), min(Wn, int((p["x"] + M + R) / cell) + 1)
        y0, y1 = max(0, int((p["y"] + M - R) / cell)), min(Hn, int((p["y"] + M + R) / cell) + 1)
        if x1 <= x0 or y1 <= y0:
            continue
        ys, xs = np.mgrid[y0:y1, x0:x1].astype(np.float32) * cell - M
        zz, tt, rr, ff, ww = peak_height(p, xs - p["x"], ys - p["y"])
        sub = z[y0:y1, x0:x1]
        m = zz > sub
        sub[m] = zz[m]
        idx[y0:y1, x0:x1][m] = k
        hn[y0:y1, x0:x1][m] = (zz / (p["H"] / K))[m]
        th[y0:y1, x0:x1][m] = tt[m]
        rh[y0:y1, x0:x1][m] = rr[m]
        fo[y0:y1, x0:x1][m] = ff[m]
        fw[y0:y1, x0:x1][m] = ww[m]
    return {"z": z, "idx": idx, "hn": hn, "theta": th, "rho": rh, "psi": fo, "fold_w": fw,
            "cell": cell, "origin": -M}


def raster_z(r, x, y):
    """Glyph surface height (true m) at map point (x, y) (nearest raster cell)."""
    j = int(round((y - r["origin"]) / r["cell"]))
    i = int(round((x - r["origin"]) / r["cell"]))
    if 0 <= j < r["z"].shape[0] and 0 <= i < r["z"].shape[1]:
        return float(r["z"][j, i])
    return 0.0


# ---------------------------------------------------------------------------------------------
# Blender: meshes, materials, ink, passes
# ---------------------------------------------------------------------------------------------
AOVS = (("gA", "COLOR"), ("gB", "COLOR"), ("gC", "COLOR"))


def glyph_material(name="GlyphMat"):
    """Flat emission (a debug wash) + the attribute AOVs the painter reads."""
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    N, L = nt.nodes, nt.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial")
    em = N.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.0
    attr = {}
    for nm in ("hn", "rho", "rand", "ct", "st", "kind", "psi", "fold_w", "hpage"):
        a = N.new("ShaderNodeAttribute")
        a.attribute_type = "GEOMETRY"
        a.attribute_name = nm
        attr[nm] = a.outputs["Fac"]
    ramp = N.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.45, 0.25, 0.1, 1)
    ramp.color_ramp.elements[1].color = (0.03, 0.12, 0.3, 1)
    L.new(attr["hn"], ramp.inputs[0])
    L.new(ramp.outputs[0], em.inputs["Color"])
    L.new(em.outputs[0], out.inputs["Surface"])
    for aov_name, (c0, c1, c2) in (("gA", ("hn", "rho", "rand")), ("gB", ("ct", "st", "kind")),
                                   ("gC", ("psi", "fold_w", "hpage"))):
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


def _mesh_from_grid(name, X, Y, Z, on, attrs, mat):
    """Quad mesh over the grid cells whose four corners are ``on``; per-vertex float attrs."""
    import bpy
    Hn, Wn = on.shape
    vid = np.full((Hn, Wn), -1, np.int64)
    nv = int(on.sum())
    vid[on] = np.arange(nv)
    co = np.stack([X[on], Y[on], Z[on]], -1).astype(np.float32).reshape(-1)
    q = on[:-1, :-1] & on[1:, :-1] & on[:-1, 1:] & on[1:, 1:]
    jj, ii = np.nonzero(q)
    # winding: the sheared surface faces +Z (towards the camera)
    quads = np.stack([vid[jj, ii], vid[jj, ii + 1], vid[jj + 1, ii + 1], vid[jj + 1, ii]], -1)
    me = bpy.data.meshes.new(name)
    me.vertices.add(nv)
    me.vertices.foreach_set("co", co)
    nq = len(quads)
    me.loops.add(nq * 4)
    me.loops.foreach_set("vertex_index", quads.reshape(-1).astype(np.int32))
    me.polygons.add(nq)
    me.polygons.foreach_set("loop_start", np.arange(0, nq * 4, 4, dtype=np.int32))
    me.polygons.foreach_set("loop_total", np.full(nq, 4, dtype=np.int32))
    me.polygons.foreach_set("use_smooth", np.ones(nq, dtype=bool))
    for nm, arr in attrs.items():
        at = me.attributes.new(nm, "FLOAT", "POINT")
        at.data.foreach_set("value", np.asarray(arr[on], np.float32))
    me.update(calc_edges=True)
    me.validate()
    if me.polygons and me.polygons[0].normal.z < 0:
        me.flip_normals()
    me.materials.append(mat)
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def build_relief_glyphs(r, peaks, mat, name="Glyphs", box=None):
    """Mesh of the rasterised glyph surfaces (only where they stand above the ground),
    sheared into the oblique view.  ``box`` = (x0, y0, x1, y1) map metres to limit it."""
    z, cell = r["z"], r["cell"]
    on = z > 0.02
    # one ring of ground vertices so the foot of each glyph reaches z = 0
    ring = on.copy()
    ring[1:] |= on[:-1]
    ring[:-1] |= on[1:]
    ring[:, 1:] |= on[:, :-1]
    ring[:, :-1] |= on[:, 1:]
    if box is not None:
        x0, y0, x1, y1 = box
        o = r.get("origin", 0.0)
        m = np.zeros_like(ring)
        m[max(0, int((y0 - o) / cell)):max(0, int((y1 - o) / cell) + 1),
          max(0, int((x0 - o) / cell)):max(0, int((x1 - o) / cell) + 1)] = True
        ring &= m
    ys, xs = np.mgrid[0:z.shape[0], 0:z.shape[1]].astype(np.float32) * cell + r.get("origin", 0.0)
    # the foot ring dips below the ground: the holdout ground plane (:func:`ground_plane`)
    # hides it, so a glyph meets the ground without an outline (its foot dissolves in mist)
    X, Y, Z = shear(xs, ys, np.where(on, z, -3.0))
    idx = r["idx"]
    # attributes of the ground ring come from the nearest glyph cell (no -1 ids at the foot)
    idx2 = idx.copy()
    for _ in range(2):
        for sy, sx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = np.roll(np.roll(idx2, sy, 0), sx, 1)
            idx2 = np.where(idx2 < 0, nb, idx2)
    rand = np.array([p["rand"] for p in peaks] + [0.0], np.float32)
    kind = np.array([KIND_MOUNTAIN if p["kind"] == "mountain" else KIND_HILL for p in peaks] + [0],
                    np.float32)
    hpage = np.array([p["H"] / 120.0 for p in peaks] + [0.0], np.float32)
    attrs = {"hn": r["hn"], "rho": r["rho"], "rand": rand[idx2], "hpage": hpage[idx2], "ct": np.cos(r["theta"]) * 0.5 + 0.5,
             "st": np.sin(r["theta"]) * 0.5 + 0.5, "kind": kind[idx2] / 2.0, "psi": r["psi"],
             "fold_w": r["fold_w"]}
    return _mesh_from_grid(name, X, Y, Z, ring, attrs, mat)


def ground_plane(margin=RASTER_MARGIN + 60.0):
    """The map ground at z = 0 as a holdout occluder (transparent in the render, but it hides
    what lies below the ground, Freestyle included)."""
    import bpy
    x0, y0, x1, y1 = -margin, -margin, F.MAP_W + margin, F.MAP_H + margin
    xs = np.array([x0, x1, x1, x0], np.float32)
    ys = np.array([y0, y0, y1, y1], np.float32)
    X, Y, Z = shear(xs, ys, np.zeros(4, np.float32))
    me = bpy.data.meshes.new("Ground")
    me.from_pydata([(float(a), float(b), float(c)) for a, b, c in zip(X, Y, Z)], [], [(0, 1, 2, 3)])
    me.update()
    if me.polygons[0].normal.z < 0:
        me.flip_normals()
    mat = bpy.data.materials.new("GroundHoldout")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    ho = nt.nodes.new("ShaderNodeHoldout")
    nt.links.new(ho.outputs[0], out.inputs["Surface"])
    me.materials.append(mat)
    obj = bpy.data.objects.new("Ground", me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def camera(box=None):
    """Top-down ortho camera over map rect ``box`` (default: the whole map)."""
    import bpy
    x0, y0, x1, y1 = box or (0.0, 0.0, float(F.MAP_W), float(F.MAP_H))
    cd = bpy.data.cameras.new("GlyphCam")
    cd.type = "ORTHO"
    cd.ortho_scale = max(x1 - x0, y1 - y0)
    cd.clip_start = 0.1
    cd.clip_end = 5000.0
    cam = bpy.data.objects.new("GlyphCam", cd)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = (0.5 * (x0 + x1) - F.MAP_W / 2.0, F.MAP_H / 2.0 - 0.5 * (y0 + y1), 2000.0)
    bpy.context.scene.camera = cam
    return cam


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


def ink_lines(ss, mountain_px=1.35, tree_px=0.75, tree_collection=None, relief_collection=None):
    """Freestyle brush ink as a render pass: peaks get the bold tapered calligraphic contour and
    lighter interior fold lines; trees a fine outline."""
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
    fs.crease_angle = math.radians(128.0)
    fs.use_culling = False
    fs.use_smoothness = True
    while len(fs.linesets) > 0:
        fs.linesets.remove(fs.linesets[0])
    seed = 7

    def style(name, px, alpha, calligraphy, noise, taper_ends=0.18, min_len=0.0):
        st = INK._style(name, "Ink", alpha, px, ss, True, calligraphy, noise, 0.0, True, seed)
        st.color = (1.0, 1.0, 1.0)
        if min_len > 0:
            st.use_length_min = True
            st.length_min = min_len * ss
        # stronger, longer taper than the sprite default: a brush entering and lifting
        for m in st.thickness_modifiers:
            if m.type == "ALONG_STROKE":
                pts = m.curve.curves[0].points
                pts[0].location = (0.0, 0.15)
                pts[-1].location = (1.0, 0.1)
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
        ls.select_contour = False
        ls.select_external_contour = ext
        ls.select_suggestive_contour = False
        ls.select_material_boundary = False
        if coll is not None:
            ls.select_by_collection = True
            ls.collection = coll
            ls.collection_negation = "INCLUSIVE"
        return ls

    lineset("Relief", style("InkRelief", mountain_px, 1.0, 0.5, 0.45, min_len=4.0), True, False, False,
            relief_collection)
    if tree_collection is not None:
        lineset("Trees", style("InkTree", tree_px, 0.9, 0.2, 0.2), True, False, True, tree_collection)


def comp_passes(out_dir, tag):
    """Compositor: write Image, the Freestyle pass and the AOVs as float EXRs."""
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
    for sock in ("Image", "Freestyle", "gA", "gB", "gC", "Depth"):
        if sock not in rl.outputs:
            continue
        fo.file_slots.new("%s_%s_" % (tag, sock))
        nt.links.new(rl.outputs[sock], fo.inputs[len(fo.inputs) - 1])
        names.append(sock)
    return [os.path.join(out_dir, "%s_%s_0001.exr" % (tag, s)) for s in names], names


def read_exr(path):
    """Float RGBA array (H, W, 4), top row first, from an EXR written by :func:`comp_passes`."""
    import bpy
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    return a.reshape(h, w, 4)[::-1].copy()


# ---------------------------------------------------------------------------------------------
# painted trees
# ---------------------------------------------------------------------------------------------
#: page size of the tree glyphs at s = 1 (crown width, total height in px of WorldMap.png)
TREE_GLYPH = {"broad": (13.0, 15.0), "pine": (11.0, 17.0), "bamboo": (7.5, 17.0)}
TREE_VARIANTS = 5


def _ellipsoid(cx, cy, cz, rx, ry, rz, nu=14, nv=8, lump=0.0, rng=None):
    """Vertices/faces of a (lumpy) ellipsoid in true map metres (x east, y south, z up)."""
    us = np.linspace(0, 2 * np.pi, nu, endpoint=False)
    vs = np.linspace(-0.5 * np.pi, 0.5 * np.pi, nv + 1)
    verts, faces = [], []
    ph = rng.uniform(0, 6.28, 3) if rng is not None else np.zeros(3)
    for v in vs:
        for u in us:
            k = 1.0 + lump * (np.sin(3 * u + ph[0]) * np.cos(2 * v + ph[1]) * 0.6 + np.sin(5 * u + ph[2]) * 0.4)
            verts.append((cx + rx * k * np.cos(v) * np.cos(u), cy + ry * k * np.cos(v) * np.sin(u),
                          cz + rz * k * np.sin(v)))
    for j in range(nv):
        for i in range(nu):
            a = j * nu + i
            b = j * nu + (i + 1) % nu
            faces.append((a, b, b + nu, a + nu))
    return verts, faces


def _tree_parts(kind, rng):
    """Painted tree as a few solids, in *page* units (1 = 1 px of WorldMap.png): crown blobs,
    pine pads, bamboo clumps, a short trunk.  z is page height (it is divided by K later)."""
    cw, ht = TREE_GLYPH[kind]
    parts = []
    if kind == "broad":
        trunk_h = 0.28 * ht
        parts.append(("trunk", _ellipsoid(0, 0, 0.5 * trunk_h, 0.7, 0.7, 0.55 * trunk_h, 8, 4)))
        n = int(rng.integers(3, 6))
        for k in range(n):
            a = 2 * np.pi * k / n + rng.uniform(-0.4, 0.4)
            r = rng.uniform(0.18, 0.3) * cw
            cx = np.cos(a) * 0.22 * cw
            cy = np.sin(a) * 0.12 * cw
            cz = trunk_h + rng.uniform(0.25, 0.55) * (ht - trunk_h)
            parts.append(("crown", _ellipsoid(cx, cy, cz, r, 0.8 * r, 0.85 * r, 14, 8, 0.12, rng)))
        parts.append(("crown", _ellipsoid(0, 0, ht - 0.3 * cw, 0.3 * cw, 0.24 * cw, 0.28 * cw, 14, 8, 0.12, rng)))
    elif kind == "pine":
        trunk_h = ht
        lean = rng.uniform(-0.12, 0.12) * cw
        parts.append(("trunk", _ellipsoid(0.5 * lean, 0, 0.5 * ht, 0.6, 0.6, 0.5 * ht, 8, 4)))
        n = int(rng.integers(3, 5))
        for k in range(n):
            t = 0.35 + 0.65 * k / max(1, n - 1)
            w = cw * (0.55 - 0.32 * t + rng.uniform(-0.05, 0.05))
            cx = lean * t + rng.uniform(-0.15, 0.15) * cw
            parts.append(("crown", _ellipsoid(cx, 0, t * ht * 0.92, w, 0.75 * w, 0.17 * cw, 16, 6, 0.1, rng)))
    else:   # bamboo: a clump of narrow leaf masses on thin culms
        n = int(rng.integers(2, 4))
        for k in range(n):
            ox = (k - 0.5 * (n - 1)) * 0.28 * cw + rng.uniform(-0.1, 0.1) * cw
            hh = ht * rng.uniform(0.75, 1.0)
            parts.append(("trunk", _ellipsoid(ox, 0, 0.5 * hh, 0.35, 0.35, 0.5 * hh, 6, 4)))
            parts.append(("crown", _ellipsoid(ox + rng.uniform(-0.6, 0.6), 0, 0.62 * hh, 0.22 * cw,
                                              0.18 * cw, 0.36 * hh, 12, 8, 0.18, rng)))
    return parts


def tree_prototypes(collection, seed=77):
    """Pre-sheared painted tree prototypes {(kind, variant): object} with the glyph attributes
    (hn = height fraction, rho = 0 trunk / 1 crown, rand, kind = tree)."""
    import bpy
    protos = {}
    mat = bpy.data.materials.get("GlyphMat") or glyph_material()
    rng = np.random.default_rng(seed)
    for kind in ("broad", "pine", "bamboo"):
        for vi in range(TREE_VARIANTS):
            verts, faces, hn, rho = [], [], [], []
            ht = TREE_GLYPH[kind][1]
            for (part, (v, f)) in _tree_parts(kind, rng):
                base = len(verts)
                v = np.asarray(v, np.float32)
                verts.extend(v.tolist())
                faces.extend([tuple(base + i for i in q) for q in f])
                hn.extend((np.clip(v[:, 2] / ht, 0, 1)).tolist())
                rho.extend([0.0 if part == "trunk" else 1.0] * len(v))
            v = np.asarray(verts, np.float32)
            # page units -> true metres (z / K) -> sheared offsets (linear part of shear())
            dx, dy, dz = v[:, 0], v[:, 1], v[:, 2] / K
            X = dx
            Y = -(dy - K * dz)
            Z = dy * CE + dz * SE
            me = bpy.data.meshes.new("Tree_%s_%d" % (kind, vi))
            me.from_pydata(np.stack([X, Y, Z], -1).tolist(), [], faces)
            me.update()
            r_ = float(rng.random())
            spc = {"broad": 0.2, "pine": 0.5, "bamboo": 0.8}[kind]
            for nm, arr in (("hn", hn), ("rho", rho), ("rand", [r_] * len(v)), ("ct", [spc] * len(v)),
                            ("st", [0.5] * len(v)), ("kind", [KIND_TREE / 2.0] * len(v)),
                            ("psi", [0.0] * len(v)), ("fold_w", [0.0] * len(v)),
                            ("hpage", [0.0] * len(v))):
                at = me.attributes.new(nm, "FLOAT", "POINT")
                at.data.foreach_set("value", np.asarray(arr, np.float32))
            for poly in me.polygons:
                poly.use_smooth = True
            me.materials.append(mat)
            ob = bpy.data.objects.new(me.name, me)
            collection.objects.link(ob)
            ob.location = (0.0, 0.0, -10000.0)
            ob.hide_render = True
            protos[(kind, vi)] = ob
    return protos


def instance_trees(trees, protos, collection, ground=None, seed=5):
    """One geometry-nodes point cloud per prototype; instances keep the prototype's sheared
    shape (no yaw: a rotation would not commute with the shear) and scale by ``s``."""
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
        X, Y, Z = shear(x, y, z)
        me = bpy.data.meshes.new("TreePts_%s_%d" % key)
        me.vertices.add(len(pts))
        me.vertices.foreach_set("co", np.stack([X, Y, Z], -1).reshape(-1))
        at = me.attributes.new("s", "FLOAT", "POINT")
        at.data.foreach_set("value", s)
        ob = bpy.data.objects.new(me.name, me)
        collection.objects.link(ob)
        ng = bpy.data.node_groups.new("TreeGlyph_%s_%d" % key, "GeometryNodeTree")
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
    """The trees the painting shows: every tree of the scenario woods, a third of the copses, the
    hill groves and some of the riverside trees - a painted map keeps its open land open.  The
    page scale ``ps`` makes them read at 1 px per metre."""
    rng = np.random.default_rng(seed)
    woods = [(f["x"], f["y"], f["r"] * 1.55) for f in world.m["forests"]]
    copses = list(getattr(world, "copses", []))
    keep_copse = [bool(rng.random() < 0.38) for _ in copses]
    out = []
    for t in trees:
        cat = t.get("_cat", "forest")
        x, y = t["x"], t["y"]
        if cat in ("mountain", "lone"):
            continue
        in_wood = any((x - a) ** 2 + (y - b) ** 2 < r * r for (a, b, r) in woods)
        on_island = any(F._point_in_poly((x, y), poly) for poly in world.m["land"][1:])
        if cat in ("forest", "grove") and not in_wood and not on_island:
            near = [i for i, (a, b, r) in enumerate(copses) if (x - a) ** 2 + (y - b) ** 2 < (2.4 * r) ** 2]
            if near and not keep_copse[near[0]]:
                continue
            if not near and rng.random() < 0.6:
                continue
        if cat == "riparian" and rng.random() < 0.55:
            continue
        out.append(dict(t, ps=round(float(t["s"]) * 1.3, 3)))
    return out
