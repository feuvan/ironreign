"""Illustrated Scenes (gongbi): 青绿 mountains, rocks and cliffs with 皴 texture strokes, water with
水纹 wave lines, fields, ground, 祥云 clouds.

Materials follow :mod:`ironart.scenes_gongbi` (emission washes + ``gb_ink`` / ``gb_bare`` AOVs).
Geometry is built in world metres (+Z up); heightfields go through
:func:`ironart.scenes_terrain.grid`.
"""

import math
import random

import numpy as np

from . import scenes_gongbi as GB


# =============================================================================================
# materials
# =============================================================================================
def _aniso_noise(b, P, s, stretch=(1.0, 1.0, 0.22), detail=2.0, dist=0.0):
    v = b.vmath("MULTIPLY", P, b.vec((s * stretch[0], s * stretch[1], s * stretch[2]))).outputs[0]
    return GB.wnoise(b, v, 1.0, detail, 0.5, dist)


def _slope(b):
    """0 flat .. 1 vertical (world normal)."""
    nz = b.sep(b.node("ShaderNodeNewGeometry").outputs["Normal"])[2]
    return b.math("SUBTRACT", 1.0, b.math("ABSOLUTE", nz))


def _cam_dist(b):
    cd = b.node("ShaderNodeCameraData")
    return cd.outputs["View Distance"]


def qinglv(name, z0, z1, foot="ochre_l", low="#B9A06A", mid="malachite", top="azurite",
           light_top="azurite_l", cun=0.6, cun_px=6.0, cun_len=40.0, moss=0.7,
           moss_px=9.0, var_scale=0.006, blue=0.5, near=60.0, far=900.0, bare=0.0,
           seed=0.0, plain=("#C4C29A", "#D6C49A"), plain_bare=0.35, plain_h=0.12, shadow_cun=0.55,
           steep=(0.12, 0.45), ribs=False, z1_near=None):
    """Blue-green landscape (青绿山水) mountain wash.

    Height fraction h = (z - z0) / (z1 - z0) (+ noise) runs ochre foot -> malachite slopes ->
    azurite peaks; steep faces take deeper mineral, gentle tops are paler (晕染), flat lowlands a
    thin green-ochre wash partly left as silk.  Texture strokes in ``gb_ink``: 披麻皴 hemp-fibre
    lines running down the steep faces (near-vertical, wavy, ``cun_px`` game px apart on screen
    whatever the distance, broken into lengths of ``cun_len`` m, mostly on the side away from the
    light) and 点苔 moss dots (``moss_px`` apart on screen) on gentle tops.  Both fade with camera
    distance (near..far)."""
    mat, b, created = GB._builder(name)
    if not created:
        return mat
    P = GB.wpos(b)
    x, y, z = b.sep(P)
    nz_off = b.vmath("ADD", P, b.vec((seed * 13.1, seed * 7.7, 0.0))).outputs[0]
    hn = GB.wnoise(b, nz_off, var_scale * 2.5, 3.0, 0.55)
    if z1_near is not None:
        # nearer hills turn blue-green at a lower height (d0, d1, z1 at d0): the painter keys
        # the mineral layers to each hill, not to one altitude for the whole picture
        d0, d1, zn = z1_near
        zt = b.maprange(_cam_dist(b), d0, d1, zn, z1)
        hz = b.math("DIVIDE", b.math("SUBTRACT", z, z0), b.math("SUBTRACT", zt, z0))
    else:
        hz = b.maprange(z, z0, z1, 0.0, 1.0, clamp=False)
    h = b.math("ADD", hz, b.math("MULTIPLY", b.math("SUBTRACT", hn, 0.5), 0.35))
    h = b.clamp01(h)
    # blue vs green: large-scale variation per massif
    bv = b.smooth(GB.wnoise(b, nz_off, var_scale, 2.0, 0.5), 0.35, 0.65)
    bv = b.math("ADD", b.math("MULTIPLY", bv, 0.7), blue * 0.3)
    topc = b.mix(GB.lin4(mid), GB.lin4(top), bv)
    midc = b.mix(GB.lin4(GB.mixc(mid, "malachite_l", 0.3)), GB.lin4(GB.mixc(mid, top, 0.35)), bv)
    lowc = GB.lin4(low)
    footc = GB.lin4(foot)
    c1 = b.mix(footc, lowc, b.smooth(h, 0.0, 0.22))
    c2 = b.mix(c1, midc, b.smooth(h, 0.18, 0.5))
    col = b.mix(c2, topc, b.smooth(h, 0.5, 0.9))
    # slope: steep -> deeper mineral; flat -> paler
    sl = _slope(b)
    deep = b.smooth(sl, 0.35, 0.85)
    col = b.mix(col, b.cmul(col, 0.74), b.math("MULTIPLY", deep, 0.5))
    flatc = b.smooth(sl, 0.25, 0.05)
    col = b.mix(col, b.mix(col, GB.lin4(light_top), 0.5), b.math("MULTIPLY", flatc, b.smooth(h, 0.4, 0.9)))
    # flat lowlands: thin pale green-ochre washes, partly bare silk
    pl = b.math("MULTIPLY", b.smooth(sl, 0.22, 0.08), b.smooth(h, plain_h * 1.6, plain_h * 0.5))
    pn = GB.wnoise(b, nz_off, var_scale * 6.0, 3.0, 0.55)
    plc = b.mix(GB.lin4(plain[0]), GB.lin4(plain[1]), b.smooth(pn, 0.4, 0.62))
    col = b.mix(col, plc, pl)
    # 分染 towards the silhouettes
    col = b.mix(col, b.cmul(col, 0.8), b.math("MULTIPLY", GB.facing(b, 0.35, 0.3, 1.0), 0.6))
    # ---- texture strokes -----------------------------------------------------------------
    dist = _cam_dist(b)
    dfade = b.smooth(dist, far, near)
    sxp, syp = GB.screen(b)
    wn = _aniso_noise(b, nz_off, 1.0 / (cun_len * 1.5), (1.0, 1.0, 0.5), 2.0, 0.0)
    if ribs:
        c = b.math("ADD", b.attr("rib").outputs["Fac"], b.math("MULTIPLY", wn, 1.6))
    else:
        c = b.math("ADD", b.math("DIVIDE", sxp, cun_px), b.math("MULTIPLY", wn, 4.0))
    lines = GB.stripes(b, c, 1.0, width=0.07)
    seg = _aniso_noise(b, b.vmath("ADD", nz_off, b.vec((31.0, 17.0, 5.0))).outputs[0],
                       1.0 / cun_len, (2.5, 2.5, 0.6), 2.0, 0.0)
    segm = b.smooth(seg, 0.47, 0.57)
    fg = b.node("ShaderNodeGroup")
    fg.node_tree = GB._form_group()
    shadow = b.math("ADD", 1.0 - shadow_cun, b.math("MULTIPLY", b.smooth(fg.outputs["Light"], 0.6, 0.35), shadow_cun))
    cun_m = b.math("MULTIPLY", b.math("MULTIPLY", lines, segm), b.smooth(sl, steep[0], steep[1]))
    cun_m = b.math("MULTIPLY", cun_m, shadow)
    # strokes come in groups: thin out whole patches (lit faces read cleaner)
    grp = GB.wnoise(b, b.vmath("ADD", nz_off, b.vec((71.0, 3.0, 11.0))).outputs[0], 1.0 / (cun_len * 2.5), 2.0, 0.5)
    cun_m = b.math("MULTIPLY", cun_m, b.smooth(grp, 0.36, 0.56))
    d, _ = GB.dots(b, b.comb(sxp, syp, 0.0), 1.0 / moss_px, size=0.13)
    mm = b.math("MULTIPLY", d, b.smooth(sl, 0.45, 0.15))
    mm = b.math("MULTIPLY", mm, b.smooth(GB.wnoise(b, nz_off, 1.0 / (cun_len * 1.2), 2.0, 0.5), 0.5, 0.6))
    mm = b.math("MULTIPLY", mm, b.smooth(h, 0.15, 0.35))
    ink = b.math("MAXIMUM", b.math("MULTIPLY", cun_m, cun), b.math("MULTIPLY", mm, moss))
    ink = b.math("MULTIPLY", ink, dfade)
    br = b.math("ADD", bare, b.math("MULTIPLY", pl, b.math("MULTIPLY", b.smooth(pn, 0.35, 0.7), plain_bare)))
    return GB.finish(mat, b, col, ink=ink, bare=br)


def rock(name, color="stone", deep="stone_d", cun=0.8, scale=0.6, freq=5.0, axe=(0.6, 0.0, 1.0),
         ochre=0.35, moss=0.0, near=20.0, far=400.0, top=None, top_amount=0.8):
    """Rock / cliff wash with 斧劈皴 axe-cut strokes (iso-lines of a noise stretched along
    ``axe``), ochre in the hollows, darker on steep faces."""
    mat, b, created = GB._builder(name)
    if not created:
        return mat
    P = GB.wpos(b)
    sl = _slope(b)
    g = b.math("MAXIMUM", GB.facing(b, 0.35, 0.2, 1.0), b.math("MULTIPLY", b.smooth(sl, 0.4, 0.95), 0.7))
    base = b.mix(GB.lin4(color), GB.lin4(deep), g)
    on = GB.wnoise(b, P, scale * 0.3, 2.0, 0.5)
    base = b.mix(base, b.mix(base, GB.lin4("ochre"), 0.5), b.math("MULTIPLY", b.smooth(on, 0.45, 0.7), ochre))
    if top is not None:
        nz = b.sep(b.node("ShaderNodeNewGeometry").outputs["Normal"])[2]
        tm = b.math("MULTIPLY", b.smooth(nz, 0.35, 0.75), top_amount)
        base = b.mix(base, GB.lin4(top), tm)
    ax = axe
    st = (1.0 / max(0.15, ax[0]), 1.0 / max(0.15, ax[1] if ax[1] else 1.0), 1.0 / max(0.15, ax[2]))
    f = _aniso_noise(b, P, scale, (1.0, 1.0, 0.3), 2.0, 0.8)
    lines = GB.stripes(b, f, freq, width=0.09)
    brk = b.smooth(GB.wnoise(b, P, scale * 1.9, 2.0, 0.5), 0.42, 0.6)
    ink = b.math("MULTIPLY", b.math("MULTIPLY", lines, brk), b.smooth(sl, 0.2, 0.7))
    if moss > 0:
        d, _ = GB.dots(b, P, scale * 6.0, size=0.15)
        ink = b.math("MAXIMUM", ink, b.math("MULTIPLY", b.math("MULTIPLY", d, b.smooth(sl, 0.4, 0.1)), moss))
    ink = b.math("MULTIPLY", b.math("MULTIPLY", ink, cun), b.smooth(_cam_dist(b), far, near))
    return GB.finish(mat, b, base, ink=ink)


def water(name, color="azurite_l", deep="#5E86A8", cover=0.45, lines=0.7, spacing_px=7.0,
          wave_px=70.0, amp=0.35, gaps=0.8, gap_len=60.0, near=10.0, far=3000.0, net=0.0,
          grade=(10.0, 300.0), cam_h=None, d_ref=None):
    """Water: pale azurite wash (partly bare silk) with 水纹 wave lines in ``gb_ink``.

    Undulating horizontal lines (crests ``wave_px`` game px long, ``amp`` line spacings high,
    amplitude varying along the water), broken into lengths by world-space noise (``gaps``),
    optionally crossed by a second family (``net``, 网巾纹).  Spacing: ``spacing_px`` game px on
    screen; with ``cam_h`` (camera height above the water, m) and ``d_ref`` the lines are indexed
    by log(distance) instead, so they open up towards the viewer (spacing_px at d_ref) the way a
    painter widens them in the foreground without strict perspective.  The wash deepens towards
    the viewer (``grade`` = distances of deep..pale)."""
    mat, b, created = GB._builder(name)
    if not created:
        return mat
    P = GB.wpos(b)
    sx, sy = GB.screen(b)
    dist = _cam_dist(b)
    n = GB.wnoise(b, b.vmath("MULTIPLY", P, b.vec((1.0 / gap_len, 1.0 / gap_len, 0.0))).outputs[0], 1.0, 2.0, 0.5)
    na = GB.wnoise(b, b.vmath("MULTIPLY", P, b.vec((0.5 / gap_len, 0.5 / gap_len, 0.0))).outputs[0], 1.0, 2.0, 0.5)
    ampv = b.math("MULTIPLY", b.maprange(na, 0.3, 0.7, 0.3, 1.4), amp)
    wav = b.math("MULTIPLY", b.math("SINE", b.math("ADD", b.math("MULTIPLY", sx, 2 * math.pi / wave_px),
                                                   b.math("MULTIPLY", na, 6.0))), ampv)
    if cam_h is not None:
        kk = cam_h / (spacing_px * d_ref)          # x focal px (shared group value)
        base = b.math("MULTIPLY", b.math("LOGARITHM", b.math("MAXIMUM", dist, 1.0), math.e), -1.0)
        fv = b.node("ShaderNodeGroup")
        fv.node_tree = _focal_value_group()
        c0 = b.math("MULTIPLY", base, b.math("MULTIPLY", fv.outputs[0], kk))
    else:
        c0 = b.math("DIVIDE", sy, spacing_px)
    c1 = b.math("ADD", b.math("ADD", c0, wav), b.math("MULTIPLY", n, 1.2))
    ink = GB.stripes(b, c1, 1.0, width=0.08)
    if net > 0:
        wav2 = b.math("MULTIPLY", b.math("SINE", b.math("ADD", b.math("MULTIPLY", sx, 2 * math.pi / wave_px), 2.2)), b.math("MULTIPLY", ampv, -1.0))
        c2 = b.math("ADD", b.math("ADD", c0, wav2), b.math("MULTIPLY", n, 1.2))
        ink = b.math("MAXIMUM", ink, b.math("MULTIPLY", GB.stripes(b, c2, 1.0, width=0.08), net))
    g2 = GB.wnoise(b, b.vmath("MULTIPLY", P, b.vec((2.5 / gap_len, 2.5 / gap_len, 0.0))).outputs[0], 1.0, 3.0, 0.55)
    ink = b.math("MULTIPLY", ink, b.math("SUBTRACT", 1.0, b.math("MULTIPLY", b.smooth(g2, 0.42, 0.52), gaps)))
    ink = b.math("MULTIPLY", b.math("MULTIPLY", ink, lines), b.smooth(dist, far, near))
    g = b.smooth(dist, grade[0], grade[1])
    col = b.mix(GB.lin4(deep), GB.lin4(color), g)
    br = b.math("ADD", 1.0 - cover, b.math("MULTIPLY", g, cover * 0.5))
    return GB.finish(mat, b, col, ink=ink, bare=br, form=0.0)


def _focal_value_group():
    """Node group exposing the shared focal length in game px (GB_Screen's value)."""
    import bpy
    from .scenes_sky import new_group
    g = bpy.data.node_groups.get("GB_FocalValue")
    if g is not None:
        return g
    g, gb, gi, go = new_group("GB_FocalValue", [], [("F", "NodeSocketFloat")])
    # driven copy: GB.set_screen also writes this node
    v = gb.node("ShaderNodeValue", name="GB_FocalPx")
    v.outputs[0].default_value = 1000.0
    gb.link(v.outputs[0], go.inputs["F"])
    return g


def ground(name, color="#D2C29C", deep="#B8A47C", cover=0.75, grass=0.0, scale=0.5,
           near=5.0, far=120.0, blotch=0.25):
    """Earth / plain: a thin ochre wash partly left as bare silk, with blotches and optional
    ink grass flecks."""
    mat, b, created = GB._builder(name)
    if not created:
        return mat
    P = GB.wpos(b)
    n = GB.wnoise(b, P, 0.03, 3.0, 0.55)
    col = b.mix(GB.lin4(color), GB.lin4(deep), b.math("MULTIPLY", b.smooth(n, 0.4, 0.7), blotch * 2.0))
    ink = 0.0
    if grass > 0:
        f = _aniso_noise(b, P, scale, (1.0, 1.0, 0.1), 1.0, 0.0)
        d, _ = GB.dots(b, b.vmath("MULTIPLY", P, b.vec((1.0, 1.0, 1.0))).outputs[0], scale * 8, size=0.08)
        ink = b.math("MULTIPLY", b.math("MULTIPLY", d, b.smooth(n, 0.5, 0.7)), grass)
        ink = b.math("MULTIPLY", ink, b.smooth(_cam_dist(b), far, near))
    br = b.math("SUBTRACT", 1.0 - cover, b.math("MULTIPLY", b.smooth(n, 0.45, 0.75), 0.2))
    return GB.finish(mat, b, col, ink=ink, bare=b.clamp01(br), form=0.0)


def cloud(name="GB_Cloud", color="white", deep="azurite_l", tint=0.35):
    """祥云 cloud: lead white with a pale azurite 晕染 underneath and at the silhouettes."""
    mat, b, created = GB._builder(name)
    if not created:
        return mat
    nz = b.sep(b.node("ShaderNodeNewGeometry").outputs["Normal"])[2]
    g = b.math("MAXIMUM", b.smooth(nz, 0.2, -0.6), GB.facing(b, 0.3, 0.45, 1.0))
    col = b.mix(GB.lin4(color), GB.lin4(GB.mixc(color, deep, 0.75)), b.math("MULTIPLY", g, tint * 2.0))
    return GB.finish(mat, b, col, nomist=1.0, form=0.0)


# =============================================================================================
# geometry
# =============================================================================================
def peak_field(X, Y, peaks, seed=0, ridge=0.25, ridge_scale=60.0, roughness=0.5, softmax=6.0):
    """Height field of steep 青绿 peaks.

    peaks = [(x, y, height, radius, shape)], shape > 1 = rounder shoulders (馒头), < 1 = spikier.
    Peaks are combined with a smooth maximum (p-norm, ``softmax`` = p), then textured by ridged
    noise that grows with the local height fraction (crags at the top, smooth feet)."""
    from .scenes_terrain import ridged2, fbm2
    acc = np.zeros_like(X, dtype=np.float64)
    top = max(p[2] for p in peaks)
    for (px, py, ph, pr, shape) in peaks:
        d = np.sqrt((X - px) ** 2 + (Y - py) ** 2) / pr
        t = np.clip(1.0 - d, 0.0, 1.0)
        prof = (1.0 - (1.0 - t) ** (1.0 + shape)) * t ** (0.6 / max(0.3, shape))
        acc += (ph * prof / top) ** softmax
    acc = top * acc ** (1.0 / softmax)
    frac = acc / top
    rn = ridged2(X, Y, scale=ridge_scale, octaves=5, seed=seed, sharp=1.6)
    fn = fbm2(X, Y, scale=ridge_scale * 0.7, octaves=4, seed=seed + 1)
    acc = acc * (1.0 + ridge * (rn - 0.5) * (0.3 + frac)) + roughness * ridge_scale * 0.04 * (fn - 0.5) * frac
    return np.maximum(acc, 0.0).astype(np.float32)


def heightfield(name, x0, x1, y0, y1, nx, ny, fn, mat, col, base=0.0):
    """Grid mesh of ``fn(X, Y)`` heights (+ base) through :func:`scenes_terrain.grid`."""
    from .scenes_terrain import grid
    X, Y = np.meshgrid(np.linspace(x0, x1, nx), np.linspace(y0, y1, ny))
    Hh = fn(X, Y).astype(np.float32) + base
    o = grid(name, Hh, x0, x1, y0, y1, mat=mat, col=col)
    return o, Hh


def rock_mass(mb, outline, z0, z1, mat, rng, rings=6, jag=0.18, top_noise=0.25, taper=0.15,
              lean=(0.0, 0.0), top_mat=None, bulge=0.0):
    """Extruded rock (cliff, crag, boulder): ``outline`` = CCW (x, y) polygon at the base;
    side walls in ``rings`` bands with jagged per-vertex offsets (斧劈 facets), tapering by
    ``taper`` towards the top and leaning by ``lean`` (dx, dy at the top); a noisy top cap."""
    from mathutils import Vector
    n = len(outline)
    cx = sum(p[0] for p in outline) / n
    cy = sum(p[1] for p in outline) / n
    H = z1 - z0
    ids = []
    for j in range(rings + 1):
        t = j / rings
        row = []
        for i, (x, y) in enumerate(outline):
            k = 1.0 - taper * t + bulge * math.sin(t * math.pi)
            jx = rng.uniform(-jag, jag) * (0.3 + 0.7 * math.sin(t * math.pi + 0.3)) if 0 < j < rings else 0
            jy = rng.uniform(-jag, jag) * (0.3 + 0.7 * math.sin(t * math.pi + 0.3)) if 0 < j < rings else 0
            px = cx + (x - cx) * k + lean[0] * t + jx * H * 0.15
            py = cy + (y - cy) * k + lean[1] * t + jy * H * 0.15
            pz = z0 + H * t + (rng.uniform(-1, 1) * H * 0.02 if 0 < j < rings else 0)
            row.append(mb.v((px, py, pz)))
        ids.append(row)
    for j in range(rings):
        for i in range(n):
            a, b_ = ids[j][i], ids[j][(i + 1) % n]
            c, d = ids[j + 1][(i + 1) % n], ids[j + 1][i]
            mb.face((a, b_, c, d), mat)
    # top cap: fan to a slightly raised, noisy centre ring
    top = ids[-1]
    tx = sum(mb.verts[i].x for i in top) / n
    ty = sum(mb.verts[i].y for i in top) / n
    inner = []
    for i in top:
        v = mb.verts[i]
        inner.append(mb.v((tx + (v.x - tx) * 0.6, ty + (v.y - ty) * 0.6,
                           z1 + min(H * 0.02, 0.6) + rng.uniform(0, top_noise) * min(H * 0.05, 1.5))))
    cid = mb.v((tx, ty, z1 + min(H * 0.03, 0.8)))
    tm = top_mat or mat
    for i in range(n):
        mb.face((top[i], top[(i + 1) % n], inner[(i + 1) % n], inner[i]), tm)
        mb.face((inner[i], inner[(i + 1) % n], cid), tm)
    return ids


def blob_cloud(mb, center, size, rng, mat="Cloud", n=7, flat=0.45, curl=True):
    """祥云-like cloud: a cluster of flattened spheres along a gentle arc (outlined by the
    'cloud' ink set, lead white wash).  ``size`` = (length, depth, height) metres."""
    L, D, Hh = size
    cx, cy, cz = center
    for i in range(n):
        t = (i + 0.5) / n
        r = Hh * (0.55 + 0.45 * math.sin(t * math.pi)) * rng.uniform(0.8, 1.15)
        x = cx + (t - 0.5) * L + rng.uniform(-0.05, 0.05) * L
        y = cy + rng.uniform(-0.5, 0.5) * D
        z = cz + math.sin(t * math.pi) * Hh * 0.25 + rng.uniform(-0.1, 0.1) * Hh
        mb.sphere((x, y, z), r, mat, 18, 10, scale=(1.25, 1.0, flat))
        if curl and rng.random() < 0.5:
            mb.sphere((x + r * 0.6, y - r * 0.3, z + r * flat * 0.6), r * 0.5, mat, 14, 8, scale=(1.2, 1.0, flat))


def strip_field(mb, x0, x1, y0, y1, z, mat, rows=0):
    mb.box(((x0 + x1) / 2, (y0 + y1) / 2, z - 0.05), (x1 - x0, y1 - y0, 0.05), mat, skip=("bottom",))


def fan_terrain(name, cam_xy, yaw_deg, fov_deg, d0, d1, n_ang, n_dist, fn, mat, col, margin_deg=6.0,
                smooth=True, attrs=None):
    """Heightfield on a camera-centred polar grid (rows log-spaced in distance, columns uniform
    in angle) so vertices have a roughly uniform *screen* density from the foreground to the far
    ranges.  ``yaw_deg`` 0 = looking +Y, positive towards +X.  ``fn(X, Y) -> Z``."""
    import bpy
    cx, cy = cam_xy
    a0 = math.radians(yaw_deg - fov_deg / 2 - margin_deg)
    a1 = math.radians(yaw_deg + fov_deg / 2 + margin_deg)
    angs = np.linspace(a0, a1, n_ang)
    ds = np.geomspace(d0, d1, n_dist)
    A, D = np.meshgrid(angs, ds)
    X = cx + D * np.sin(A)
    Y = cy + D * np.cos(A)
    Z = fn(X, Y).astype(np.float64)
    W, H = n_ang, n_dist
    co = np.stack([X, Y, Z], -1).reshape(-1).astype(np.float32)
    me = bpy.data.meshes.new(name)
    me.vertices.add(W * H)
    me.vertices.foreach_set("co", co)
    ii, jj = np.meshgrid(np.arange(W - 1), np.arange(H - 1))
    v0 = (jj * W + ii).reshape(-1)
    # angle increases clockwise seen from above -> (i+1 first) keeps faces pointing up
    quads = np.stack([v0, v0 + W, v0 + W + 1, v0 + 1], -1).reshape(-1).astype(np.int32)
    nq = (W - 1) * (H - 1)
    me.loops.add(nq * 4)
    me.loops.foreach_set("vertex_index", quads)
    me.polygons.add(nq)
    me.polygons.foreach_set("loop_start", np.arange(0, nq * 4, 4, dtype=np.int32))
    me.polygons.foreach_set("loop_total", np.full(nq, 4, dtype=np.int32))
    me.polygons.foreach_set("use_smooth", np.full(nq, smooth, dtype=bool))
    for k, f in (attrs or {}).items():
        at = me.attributes.new(k, "FLOAT", "POINT")
        at.data.foreach_set("value", np.asarray(f(X, Y), np.float32).reshape(-1))
    me.update(calc_edges=True)
    me.validate()
    if me.polygons[0].normal.z < 0:
        me.flip_normals()
    obj = bpy.data.objects.new(name, me)
    col.objects.link(obj)
    if mat is not None:
        me.materials.append(mat)
    return obj, (X, Y, Z)


def river_dist(X, Y, pts):
    """Distance from (X, Y) to the polyline ``pts`` (numpy, any shape)."""
    from .scenes_terrain import polyline_dist
    return polyline_dist(X, Y, pts)


def peak_ribs(X, Y, peaks, cam_xy, focal_px, spacing_px=7.0):
    """Rib coordinate for 披麻皴 lines that radiate from each summit down its slopes.

    For every point the dominant peak (largest individual profile) is found; the coordinate is
    the angle around that summit scaled so that, at mid-slope, neighbouring ribs are
    ``spacing_px`` game px apart on screen.  Stripes of this coordinate (``qinglv(ribs=True)``)
    converge towards the summits like brush strokes do."""
    best = np.full(X.shape, -1.0)
    rib = np.zeros(X.shape)
    cx, cy = cam_xy
    for (px, py, ph, pr, shape) in peaks:
        d = np.sqrt((X - px) ** 2 + (Y - py) ** 2) / pr
        t = np.clip(1.0 - d, 0.0, 1.0)
        prof = ph * (1.0 - (1.0 - t) ** (1.0 + shape)) * t ** (0.6 / max(0.3, shape))
        m = prof > best
        best = np.where(m, prof, best)
        D = max(1.0, math.hypot(px - cx, py - cy))
        th = np.arctan2(Y - py, X - px)
        per_rad = pr * 0.55 * focal_px / D
        rib = np.where(m, th * per_rad / spacing_px + (px * 0.013 % 1.0), rib)
    return rib


def pinnacle(mb, center, base_r, top_r, z0, z1, rng, mat="Rock", subs=5, sides=11, jag=0.12):
    """A 斧劈-faceted rock pinnacle: a main tapering column (flat top at ``z1``, radius ``top_r``)
    with lower satellite columns crowding its flanks, all rising from ``z0``."""
    cx, cy = center[0], center[1]

    def column(x, y, r0, r1, top, seed_lean):
        outline = [(x + math.cos(-i / sides * math.tau) * r0 * rng.uniform(0.8, 1.15),
                    y + math.sin(-i / sides * math.tau) * r0 * rng.uniform(0.8, 1.15)) for i in range(sides)]
        taper = 1.0 - r1 / max(r0, 1e-6)
        rock_mass(mb, outline, z0, top, mat, rng, rings=12, jag=jag, taper=taper,
                  lean=(rng.uniform(-1, 1) * r0 * 0.15 * seed_lean, rng.uniform(-1, 1) * r0 * 0.1 * seed_lean),
                  bulge=rng.uniform(-0.05, 0.08), top_noise=0.0)
    column(cx, cy, base_r, top_r, z1, 0.0)
    H = z1 - z0
    for i in range(subs):
        a = rng.uniform(0, math.tau)
        d = base_r * rng.uniform(0.55, 0.9)
        r0 = base_r * rng.uniform(0.35, 0.6)
        top = z1 - H * rng.uniform(0.12, 0.45)
        column(cx + math.cos(a) * d, cy + math.sin(a) * d, r0, r0 * rng.uniform(0.3, 0.55), top, 1.0)


def boulder(mb, center, size, rng, mat="Rock", lumps=6, seg=(18, 12), flat_top=None, squash=1.0,
            spread=0.45, rough=0.12):
    """Lumpy painted rock: a cluster of overlapping, noise-dented ellipsoids.  Where the lumps
    overlap the 'land' ink draws the folds of the stone (the contour lines of a 青绿 rock).
    ``size`` = (sx, sy, sz) metres; ``flat_top`` clamps vertices above that z (a ledge to stand on)."""
    from mathutils import Vector
    cx, cy, cz = center
    sx, sy, sz = size
    for i in range(lumps):
        if i == 0:
            c = Vector((cx, cy, cz + sz * 0.45))
            r = (sx * 0.5, sy * 0.5, sz * 0.55)
        else:
            a = rng.uniform(0, math.tau)
            c = Vector((cx + math.cos(a) * sx * spread * rng.uniform(0.3, 1.0),
                        cy + math.sin(a) * sy * spread * rng.uniform(0.3, 1.0),
                        cz + sz * rng.uniform(0.15, 0.6)))
            k = rng.uniform(0.45, 0.75)
            r = (sx * 0.5 * k, sy * 0.5 * k, sz * 0.5 * k * squash)
        s0 = mb.n
        mb.sphere(tuple(c), 1.0, mat, seg[0], seg[1], scale=r)
        ph = [rng.uniform(0, math.tau) for _ in range(4)]
        for vi in range(s0, mb.n):
            v = mb.verts[vi] - c
            if v.length < 1e-6:
                continue
            n = v.normalized()
            ang = math.atan2(n.y, n.x)
            el = math.asin(max(-1.0, min(1.0, n.z)))
            f = 1.0 + rough * (math.sin(3 * ang + ph[0]) * 0.6 + math.sin(5 * ang + 3 * el + ph[1]) * 0.4
                               + math.sin(2 * el + ph[2]) * 0.5 + math.sin(7 * ang + ph[3]) * 0.2)
            p = c + v * f
            if flat_top is not None and p.z > flat_top:
                p.z = flat_top + (p.z - flat_top) * 0.05
            mb.verts[vi] = p


def crag_stack(mb, center, z0, z1, r0, r1, rng, mat="Rock", lean=(0.0, 0.0), flat_top=True,
               seg=(20, 14), lumps=5, rough=0.15, squash=0.9):
    """A 青绿 rock pinnacle built as a stack of lumpy boulders (rounded rock forms one above the
    other, the way painters pile up a crag): radius ``r0`` at the foot (z0) to ``r1`` at the
    top (z1), leaning by ``lean`` (dx, dy at the top); ``flat_top`` levels the summit so
    buildings or figures can stand on it.  Returns the summit point."""
    cx, cy = center[0], center[1]
    H = z1 - z0
    ravg = (r0 + r1) * 0.5
    n = max(2, int(round(H / (ravg * 1.15))))
    h = H / n
    top = None
    for i in range(n):
        t = i / max(1, n - 1)
        r = r0 + (r1 - r0) * t
        jx, jy = rng.uniform(-0.18, 0.18) * r, rng.uniform(-0.12, 0.12) * r
        x = cx + lean[0] * t + jx
        y = cy + lean[1] * t + jy
        zc = z0 + i * h - h * 0.25
        sz = h * 1.55 if i < n - 1 else (z1 - zc) / 0.92
        last = i == n - 1
        boulder(mb, (x, y, zc), (2.0 * r, 2.0 * r * 0.88, sz), rng, mat, lumps=lumps, seg=seg,
                flat_top=z1 if (last and flat_top) else None, squash=squash, spread=0.42, rough=rough)
        top = (x, y, z1)
    return top
