"""Battle family: hex-tile construction, texturing, export (DESIGN.md 12.3 / 12.4).

A tile (``Hex_<Terrain>.glb``) is ONE mesh with two materials:

``Ground``  the top heightfield over the flat-top hexagon (circumradius 4 m, corners on +-x,
            top at z = 0 along the boundary; water tiles at :data:`WATER_Z`), plus the skirt down
            to z = -1 and a bottom cap.  Planar UVs (u = (x + 4) / 8, v = (y + 4) / 8) on a
            2048 px painted texture (:mod:`ironart.battle_paint`, numpy), the skirt in two
            strips of the free band below the hexagon.  Normal map from the painted height.
``Props``   everything standing on the ground (grass tufts, stones, trees, rocks, walls,
            houses...), built with :class:`ironart.geometry.MeshBuilder` and ``W_*`` /
            ``B_*`` procedural gongbi materials, Smart-UV unwrapped into one atlas and baked with
            Cycles (:func:`ironart.world_bake.bake`: base colour without light, tangent normal;
            roughness / metallic are constant factors - matte pigment).

No baked AO, no cast shadows in any texture.  Unreal adds the ink outlines and the silk grade.
"""

import math
import os
import time

import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import battle_paint as BP
from . import world_bake as WB
from . import world_gongbi as WG
from .geometry import MeshBuilder

R = BP.R
APO = BP.APO
SKIRT_Z = -1.0
#: water surface of Water / Ford / Bridge tiles (m): the land tiles' skirts show as banks
WATER_Z = -0.32
#: ground texture size (px) and normal map size
GROUND_PX = 2048
NORMAL_PX = 1024
#: matte pigment (glTF roughness factor; UE's painted look overrides it with 0.95 anyway)
ROUGH = 0.9
#: skirt strips in the texture's free band below the hexagon (v ranges)
STRIPS = ((0.004, 0.030), (0.036, 0.062))
STRIP_LEN = 12.0


# ---------------------------------------------------------------------------------------------
# ground mesh
# ---------------------------------------------------------------------------------------------
def lattice(n):
    """Triangular lattice over the hexagon (spacing R / n, edges and corners on lattice
    points).  Returns (pts (N, 2), triangles (M, 3), boundary loop indices CCW)."""
    s = R / n
    a1 = np.array([s, 0.0])
    a2 = np.array([s * 0.5, s * BP.SQ3 / 2])
    idx = {}
    pts = []
    for j in range(-2 * n, 2 * n + 1):
        for i in range(-2 * n, 2 * n + 1):
            p = i * a1 + j * a2
            if BP.hex_d(np.float32(p[0]), np.float32(p[1])) >= -2e-3:
                idx[(i, j)] = len(pts)
                pts.append(p)
    pts = np.array(pts)
    tris = []
    for j in range(-2 * n - 1, 2 * n + 1):
        for i in range(-2 * n - 1, 2 * n + 1):
            k, a, b, c = idx.get((i, j)), idx.get((i + 1, j)), idx.get((i, j + 1)), idx.get((i + 1, j + 1))
            if a is None or b is None:
                continue
            if k is not None:
                tris.append((k, a, b))
            if c is not None:
                tris.append((a, c, b))
    d = BP.hex_d(pts[:, 0], pts[:, 1])
    bnd = np.where(np.abs(d) < 2e-3)[0]
    ang = np.arctan2(pts[bnd, 1], pts[bnd, 0])
    bnd = bnd[np.argsort(ang)]
    # start the loop at the +x corner
    start = int(np.argmin(np.hypot(pts[bnd, 0] - R, pts[bnd, 1])))
    bnd = np.roll(bnd, -start)
    return pts, np.array(tris), bnd


def _uv_top(x, y):
    return ((x + 4.0) / 8.0, (y + 4.0) / 8.0)


def _uv_skirt(p, z, z_top):
    """Skirt texel: perimeter position p (m from the +x corner, CCW), height z."""
    k = min(int(p // STRIP_LEN), 1)
    u = 0.006 + 0.988 * (p - k * STRIP_LEN) / STRIP_LEN
    v0, v1 = STRIPS[k]
    t = (z - SKIRT_Z) / max(z_top - SKIRT_Z, 1e-3)
    return (u, v0 + (v1 - v0) * t)


def ground_object(name, hfn, n=40, mat="Ground"):
    """Top heightfield (``hfn(x, y) -> z`` vectorised), skirt to :data:`SKIRT_Z`, bottom cap."""
    pts, tris, bnd = lattice(n)
    z = np.asarray(hfn(pts[:, 0].astype(np.float32), pts[:, 1].astype(np.float32)), np.float64)
    mb = MeshBuilder()
    vid = [mb.v((float(x), float(y), float(zz))) for (x, y), zz in zip(pts, z)]
    for a, b, c in tris:
        mb.face((vid[a], vid[b], vid[c]), mat, [_uv_top(*pts[a]), _uv_top(*pts[b]), _uv_top(*pts[c])], smooth=True)
    # skirt: one quad per boundary segment (outward facing), perimeter-parametrised UVs
    loop = list(bnd) + [bnd[0]]
    per = 0.0
    bottom = []
    zb = SKIRT_Z
    for k in range(len(loop) - 1):
        a, b = loop[k], loop[k + 1]
        pa, pb = pts[a], pts[b]
        L = float(np.hypot(*(pb - pa)))
        p0, p1 = per, per + L
        if int(p0 // STRIP_LEN) != int(min(p1, 23.999) // STRIP_LEN) and p0 < STRIP_LEN:
            p1u = STRIP_LEN - 1e-3          # do not wrap a quad across the strip split
        else:
            p1u = p1
        ta, tb = float(z[a]), float(z[b])
        va = mb.v((pa[0], pa[1], ta))
        vb = mb.v((pb[0], pb[1], tb))
        wa = mb.v((pa[0], pa[1], zb))
        wb = mb.v((pb[0], pb[1], zb))
        # CCW loop seen from above -> outward face is (a_bottom, b_bottom, b_top, a_top)
        mb.face((wa, wb, vb, va), mat, [_uv_skirt(p0, zb, ta), _uv_skirt(p1u, zb, tb),
                                        _uv_skirt(p1u, tb, tb), _uv_skirt(p0, ta, ta)])
        bottom.append(wa)
        per = p1
    # bottom cap (never seen; keeps the mesh closed for distance fields)
    cu = (0.5, 0.002)
    mb.face(bottom[::-1], mat, [cu] * len(bottom))
    obj = mb.build(name, auto_smooth_deg=60.0, merge_dist=0.0)
    return obj


# ---------------------------------------------------------------------------------------------
# ground texture
# ---------------------------------------------------------------------------------------------
def skirt_coords(size=GROUND_PX):
    """Per strip: (row slice, p (W,), z (H,)) of the skirt texels (image rows top-down)."""
    out = []
    for k, (v0, v1) in enumerate(STRIPS):
        r0 = int(math.floor((1 - v1) * size)) - 2
        r1 = int(math.ceil((1 - v0) * size)) + 2
        rows = np.arange(r0, r1)
        v = 1 - (rows + 0.5) / size
        t = (v - v0) / (v1 - v0)
        cols = np.arange(size)
        u = (cols + 0.5) / size
        p = k * STRIP_LEN + (u - 0.006) / 0.988 * STRIP_LEN
        out.append((slice(r0, r1), p.astype(np.float32), t.astype(np.float32)))
    return out


def skirt_xy(p):
    """Boundary point (x, y) at perimeter position p (CCW from the +x corner)."""
    p = np.mod(np.asarray(p, np.float32), 6 * R)
    k = np.floor(p / R).astype(int)
    f = (p - k * R) / R
    a0 = np.radians(60.0 * k)
    a1 = np.radians(60.0 * (k + 1))
    x = R * (np.cos(a0) * (1 - f) + np.cos(a1) * f)
    y = R * (np.sin(a0) * (1 - f) + np.sin(a1) * f)
    return x, y


def paint_skirt(cv, top_z=0.0, kind="land", seed=0):
    """Paint the skirt strips: an earthen bank (ochre wash deepening downwards, soft ruled strata
    in ink-umber, a meadow lip with hanging grass marks at the top) or, under water, an azurite
    wash.  Writes into ``cv.rgb`` / ``cv.h``."""
    rng = np.random.default_rng(seed)
    for rows, p, t in skirt_coords(cv.size):
        Pg, T = np.meshgrid(p, t)
        z = SKIRT_Z + (top_z - SKIRT_Z) * T                     # metres (rows top-down: lip first)
        depth = top_z - z                                      # 0 at the lip
        if kind == "water":
            col = BP.mix(BP.P["water_d"], BP.P["azu_deep"], BP.smooth(0.0, 0.7, depth))
            cv.rgb[rows] = col
            cv.h[rows] = 0.0
            continue
        n = BP.fbm(Pg, z, scale=1.3, octaves=3, seed=seed + 5)
        col = BP.mix(BP.P["bank"], BP.P["bank_d"], BP.smooth(0.05, 0.9, depth) * 0.85 + (n - 0.5) * 0.25)
        # strata: soft horizontal ink-umber lines, broken
        zz = z + (BP.fbm(Pg * 0.6, z * 0.0, scale=0.9, octaves=2, seed=seed + 9) - 0.5) * 0.12
        ph = np.mod(zz / 0.17, 1.0)
        line = BP.smooth(0.10, 0.0, np.minimum(ph, 1 - ph)) * BP.smooth(0.42, 0.62, BP.vnoise(Pg * 1.7, zz * 3.0, None, seed + 3))
        col = BP.mix(col, BP.P["bank_ink"], line[..., None] * 0.45 * BP.smooth(0.08, 0.2, depth)[..., None])
        # meadow lip
        lip = BP.smooth(0.07, 0.025, depth + (BP.vnoise(Pg * 9.0, 0 * Pg, None, seed + 11) - 0.5) * 0.03)
        col = BP.mix(col, BP.P["meadow_d"], lip[..., None])
        cv.rgb[rows] = col
        cv.h[rows] = line * 0.004


def save_ground(cv, out_dir, name, normal_strength=1.0, jpeg=True):
    """Write ``<name>_Base.jpg`` (sRGB) and ``<name>_Normal.png`` from a painted canvas."""
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    rgb = np.clip(cv.rgb, 0, 1)
    base = Image.fromarray((rgb * 255 + 0.5).astype(np.uint8), "RGB")
    bp = os.path.join(out_dir, name + "_Base." + ("jpg" if jpeg else "png"))
    if jpeg:
        base.save(bp, quality=92, subsampling=0, optimize=True)
    else:
        base.save(bp, optimize=True)
    nm = BP.normal_map(cv.h, cv.ppm, normal_strength, size=NORMAL_PX)
    npth = os.path.join(out_dir, name + "_Normal.png")
    Image.fromarray((np.clip(nm, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB").save(npth, optimize=True)
    return {"base": bp, "normal": npth}


def ground_material(name, maps):
    return WB.pbr_material(name, base=maps["base"], normal=maps["normal"], roughness=ROUGH)


# ---------------------------------------------------------------------------------------------
# props atlas
# ---------------------------------------------------------------------------------------------
#: blade-like props share one gradient strip of the props atlas (MetreUV v = 0..1 along the
#: blade): material -> (u0, u1); all strips sit at v in STRIP_V, under the world_bake trims
GRADIENT_STRIPS = {"B_Grass": (0.004, 0.196), "B_Reed": (0.204, 0.396), "B_GrassDry": (0.404, 0.596)}
STRIP_V = (0.778, 0.812)


def gradient_strip_uvs(objs):
    """UV0 of every gradient-strip face: u spread over the material's strip, v = along the blade."""
    for o in objs:
        me = o.data
        mats = [m.name if m else "" for m in me.materials]
        slots = list(o.get("slots") or mats)
        uv0 = me.uv_layers["UV0"].data
        mu = me.uv_layers["MetreUV"].data
        v0, v1 = STRIP_V
        for p in me.polygons:
            nm = WB.base_name(slots[p.material_index]) if p.material_index < len(slots) else ""
            if nm not in GRADIENT_STRIPS:
                continue
            u0, u1 = GRADIENT_STRIPS[nm]
            for li in p.loop_indices:
                m = mu[li].uv
                uu = u0 + (u1 - u0) * (0.1 + 0.8 * ((m.x * 0.618) % 1.0))
                vv = v0 + (v1 - v0) * (0.06 + 0.88 * min(1.0, max(0.0, m.y)))
                uv0[li].uv = (uu, vv)


def atlas_density(objs, size):
    """Texel density (px / m) of the packed islands: sqrt(UV area x size^2 / 3D area) over every
    face that is not a gradient strip, trim or swatch (small props included)."""
    a3 = 0.0
    a2 = 0.0
    for o in objs:
        me = o.data
        slots = list(o.get("slots") or [m.name if m else "" for m in me.materials])
        uv = me.uv_layers["UV0"].data
        for p in me.polygons:
            nm = slots[p.material_index] if p.material_index < len(slots) else ""
            if WB.base_name(nm) in GRADIENT_STRIPS or nm.endswith(WB.SUFFIXES) or WB.base_name(nm) in WB.TRIMS:
                continue
            pts = [uv[li].uv for li in p.loop_indices]
            s = 0.0
            for i in range(1, len(pts) - 1):
                (x0, y0), (x1, y1), (x2, y2) = pts[0], pts[i], pts[i + 1]
                s += abs((x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)) * 0.5
            a2 += s
            a3 += p.area
    return math.sqrt(a2 * size * size / a3) if a3 > 0 else WG.density()


def half_normal(path):
    """Halve a baked normal map in place (the painted look halves normal strength; the base colour
    keeps the full atlas resolution), renormalised."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    a = np.asarray(im, np.float32) / 255.0 * 2.0 - 1.0
    h, w = a.shape[:2]
    a = a.reshape(h // 2, 2, w // 2, 2, 3).mean(axis=(1, 3))
    a /= np.maximum(np.linalg.norm(a, axis=-1, keepdims=True), 1e-6)
    Image.fromarray(((a * 0.5 + 0.5) * 255 + 0.5).clip(0, 255).astype(np.uint8), "RGB").save(path, optimize=True)


def bake_props(objs, size, out_dir, name, materials_fn, samples=4, angle_deg=60.0, margin_px=6):
    """Smart-UV unwrap ``objs`` into one atlas, (re)build their materials for the measured texel
    density with ``materials_fn(density) -> {slot: material}``, bake base + normal (no AO, no
    cavity), and give every slot the ``Props`` material.  Returns (maps, material, density)."""
    t0 = time.time()
    for o in objs:
        WB.prepare(o)
    WB.spread(objs, gap=3.0)
    old_v = WB.PACKED_V
    WB.PACKED_V = STRIP_V[0] - 0.004
    try:
        WB.unwrap(objs, size=size, margin_px=margin_px, angle_deg=angle_deg, method="smart",
                  skip_mats=("Tint",) + tuple(GRADIENT_STRIPS), trims=True)
    finally:
        WB.PACKED_V = old_v
    gradient_strip_uvs(objs)
    dens = atlas_density(objs, size)
    WG.set_density(dens)
    slots_of = {o.name: list(o.get("slots") or [m.name if m else "" for m in o.data.materials]) for o in objs}
    lib = materials_fn(dens)
    for o in objs:
        me = o.data
        for i, sl in enumerate(slots_of[o.name]):
            base = WB.base_name(sl)
            if base in lib:
                me.materials[i] = lib[base]
    # cover-tile rows (``~row``) sample the baked roof under them (world_bake.atlas_bake's way)
    rows = {o.name: WB.separate_rows(o) for o in objs}
    maps = WB.bake(objs, size, out_dir, name, ao=False, cavity=0.0, samples=samples,
                   const={"rough": ROUGH, "metal": 0.0}, jpeg=True, skip_mats=("Tint",))
    for o in objs:
        r = rows.get(o.name)
        if r is not None:
            WB.transfer_row_uvs(r, o)
            WB.join(o, [r])
    if size >= 2048:
        half_normal(maps["normal"])
    mat = WB.pbr_material(name, base=maps["base"], normal=maps["normal"], roughness=ROUGH)
    WB.assign(objs, mat, keep=("Tint",))
    for o in objs:
        o.location = (0, 0, 0)
    bpy.context.view_layer.update()
    print("[battle] props atlas %s %dpx, %.1f px/m, %.1fs" % (name, size, dens, time.time() - t0))
    return maps, mat, dens


def finalize(name, parts):
    """Join ``parts`` into ONE mesh object named ``name`` (transforms applied, slots merged,
    only the export UV layer kept)."""
    for o in parts:
        if "UV0" in o.data.uv_layers:
            WB.strip_uvs(o, "UV0")
        elif "UVMap" in o.data.uv_layers and len(o.data.uv_layers) > 1:
            WB.strip_uvs(o, "UVMap")
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    obj = parts[0]
    obj.name = name
    obj.data.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    WB.merge_slots(obj)
    # attributes the GLB does not need
    for a in list(obj.data.attributes):
        if not a.name.startswith(".") and a.name not in ("position", "material_index", "sharp_face",
                                                          "UVMap") and a.domain == "POINT":
            try:
                obj.data.attributes.remove(a)
            except RuntimeError:
                pass
    return obj
