"""Strand hair for the portraits: brows, lashes, beards and moustaches, combed scalp hair with
topknots / buns, plus the shaded hair-cap mesh beneath (bpy + numpy).

All grooms are generated as numpy polylines, kept off the skin with a BVH push-out, clumped, and
built into one Blender ``Curves`` object per groom rendered with the Principled Hair BSDF.
"""

import math

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import head as H
import regions as R
from nodes import NB, sock

# ---------------------------------------------------------------------------------- materials
def hair_material(name, melanin=0.9, redness=0.3, grey=0.0, roughness=0.32, radial=0.3,
                  random_color=0.15, random_rough=0.1, coat=0.0, tint=None):
    """Principled Hair (Chiang).  ``grey`` mixes in unpigmented strands per strand (salt and
    pepper) via the Random input."""
    m = bpy.data.materials.new(name)
    nb = NB(m)
    hn = nb.node("ShaderNodeBsdfHairPrincipled", parametrization="MELANIN")
    sock(hn.inputs, "Melanin Redness").default_value = redness
    sock(hn.inputs, "Roughness").default_value = roughness
    sock(hn.inputs, "Radial Roughness").default_value = radial
    sock(hn.inputs, "Random Color").default_value = random_color
    sock(hn.inputs, "Random Roughness").default_value = random_rough
    sock(hn.inputs, "Coat").default_value = coat
    if tint is not None:
        sock(hn.inputs, "Tint").default_value = tint
    if grey > 0:
        info = nb.node("ShaderNodeHairInfo")
        r = info.outputs["Random"]
        # fraction ``grey`` of strands lose their pigment; the rest keep a reduced melanin
        white = nb.math("LESS_THAN", r, grey)
        mel = nb.mixf(melanin, 0.04, white)
        nb.link(mel, sock(hn.inputs, "Melanin"))
    else:
        sock(hn.inputs, "Melanin").default_value = melanin
    nb.output(hn.outputs[0])
    return m


def cap_material(name, rgb=(0.05, 0.04, 0.035), sheen=0.4, grey=0.0, scale=420.0):
    """Hair-cap mesh: strand stripes along the comb direction (UV v), anisotropic highlight."""
    m = bpy.data.materials.new(name)
    nb = NB(m)
    uv = nb.coord("UV")
    stripes = nb.noise(nb.mapping(uv, scale=(scale, 3.0, 1.0)), scale=1.0, detail=3.0)[0]
    base = tuple(c + (0.62 - c) * grey for c in rgb)
    col = nb.mix(tuple(c * 0.55 for c in base), tuple(min(1, c * 1.7 + 0.01) for c in base), stripes)
    p = nb.principled(Base_Color=col, Roughness=0.42, Specular_IOR_Level=0.5,
                      Anisotropic=0.8, Sheen_Weight=sheen, Sheen_Tint=(1, 1, 1, 1),
                      Normal=nb.bump(stripes, 0.5, 0.0006))
    nb.output(p.outputs[0])
    return m


# ------------------------------------------------------------------------------------- curves
def curves_object(name, strands, radius_root, radius_tip=None, material=None, collection=None,
                  pass_index=3):
    """strands: (N,K,3) array or list of (k,3) arrays."""
    if isinstance(strands, np.ndarray):
        strands = list(strands)
    strands = [s for s in strands if len(s) >= 2 and np.isfinite(s).all()]
    c = bpy.data.hair_curves.new(name)
    c.add_curves([len(s) for s in strands])
    pos = np.concatenate(strands).astype(np.float32)
    c.position_data.foreach_set("vector", pos.ravel())
    rt = radius_tip if radius_tip is not None else radius_root * 0.25
    rad = []
    rr = np.atleast_1d(radius_root)
    for k, s in enumerate(strands):
        r0 = float(rr[k % len(rr)])
        t = np.linspace(0, 1, len(s))
        rad.append(r0 + (rt * r0 / float(rr[0]) - r0) * t ** 1.2)
    ra = c.attributes.get("radius") or c.attributes.new("radius", "FLOAT", "POINT")
    ra.data.foreach_set("value", np.concatenate(rad).astype(np.float32))
    if material is not None:
        c.materials.append(material)
    ob = bpy.data.objects.new(name, c)
    (collection or bpy.context.scene.collection).objects.link(ob)
    ob.pass_index = pass_index
    return ob


# ----------------------------------------------------------------------------- surface helpers
class Surface:
    """Evaluated head mesh (+ optional extra colliders) for sampling roots and push-out."""

    def __init__(self, head_obj, colliders=()):
        self.P, self.T, self.N, self.A = H.evaluated_mesh_arrays(head_obj)
        dg = bpy.context.evaluated_depsgraph_get()
        self.bvh = BVHTree.FromPolygons(self.P.tolist(), self.T.tolist())
        self.extra = [BVHTree.FromObject(o, dg) for o in colliders]

    def roots(self, count, density_fn, rng):
        return H.sample_surface(self.P, self.T, self.N, self.A, count, density_fn, rng)

    def push_out(self, pts, offset, roots_fixed=1, iters=1):
        """Move points that are closer than ``offset`` to the skin (or inside it) out along the
        surface normal.  pts (N,K,3) modified in place; first ``roots_fixed`` points untouched."""
        N, K, _ = pts.shape
        off = np.broadcast_to(np.asarray(offset, np.float64), (K,)) if np.ndim(offset) <= 1 else offset
        for _ in range(iters):
            for i in range(N):
                for k in range(roots_fixed, K):
                    p = Vector(pts[i, k])
                    o = off[k] if np.ndim(off) == 1 else off[i, k]
                    for tree in [self.bvh] + self.extra:
                        loc, nrm, _, dist = tree.find_nearest(p)
                        if loc is None:
                            continue
                        d = p - loc
                        side = d.dot(nrm)
                        if side < o:
                            p = loc + nrm * o
                    pts[i, k] = p
        return pts


def _norm(v):
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-12)


def _slerp_dirs(a, b, t):
    """Spherical interpolation of unit vectors a,b (N,3) at t (K,) -> (N,K,3)."""
    dot = np.clip((a * b).sum(-1), -0.9999, 0.9999)[:, None]
    om = np.arccos(dot)
    so = np.sin(om)
    t = t[None, :]
    w0 = np.sin((1 - t) * om) / so
    w1 = np.sin(t * om) / so
    return a[:, None, :] * w0[..., None] + b[:, None, :] * w1[..., None]


def clump(strands, rng, n_clumps, amount=0.6, power=1.0, keep_root=0.0):
    """Pull strands toward clump guides (mean of members), stronger toward the tip."""
    N, K, _ = strands.shape
    if N == 0:
        return strands
    roots = strands[:, 0]
    n_clumps = max(1, min(n_clumps, N))
    cent = roots[rng.choice(N, n_clumps, replace=False)]
    d = ((roots[:, None, :] - cent[None, :, :]) ** 2).sum(-1)
    lab = d.argmin(1)
    out = strands.copy()
    t = (np.linspace(0, 1, K) ** power)[None, :, None]
    for c in range(n_clumps):
        sel = lab == c
        if sel.sum() < 2:
            continue
        g = strands[sel].mean(0)
        a = amount * (0.7 + 0.6 * rng.random())
        out[sel] = strands[sel] + (g[None] - strands[sel]) * t * a * (1 - keep_root)
    return out


def frizz(strands, rng, amount, freq=3.0):
    N, K, _ = strands.shape
    t = np.linspace(0, 1, K)[None, :, None]
    ph = rng.random((N, 1, 3)) * 6.28
    w = np.sin(t * freq * 6.28 + ph) * amount * t
    w += rng.standard_normal((N, K, 3)) * amount * 0.25 * t
    return strands + w


# -------------------------------------------------------------------------------------- brows
def brows(surf, b, mat, rng, count=900, thick=1.0, arch=1.0, length=1.0, angle=0.0, hair_len=0.009,
          lift=0.0, droop=0.0, coll=None):
    """Eyebrows: short strands lying on the skin, inner hairs rising, the body sweeping outward.
    ``droop`` > 0 grows long trailing hairs at the tail (old sages' 'longevity brows')."""
    F = b["F"]
    lm = b["lm"]

    def dens(a):
        d, t, _ = R.brow(a["fc"], F, thick, arch, length, angle)
        return d
    pos, nrm, at = surf.roots(count, dens, rng)
    if len(pos) == 0:
        return None
    _, t, cy = R.brow(at["fc"], F, thick, arch, length, angle)
    side = np.sign(at["fc"][:, 0])
    ex, ez = np.array(lm["ex"]), np.array(lm["ez"])
    # direction: inner third points up and slightly out, the rest outward with a small downward tail
    tt = np.clip(t, 0, 1)[:, None]
    up_w = np.clip(1.0 - tt * 3.0, 0, 1) * 0.9 + 0.15 - np.clip(tt - 0.7, 0, 1) * 0.8
    d = side[:, None] * ex[None] * (0.4 + tt) + ez[None] * (up_w + lift)
    # hairs above the centre line lean down, below lean up (they converge to the brow line)
    dy = (at["fc"][:, 1] - cy)[:, None]
    d -= ez[None] * np.clip(dy * 6.0, -0.6, 0.6)
    d = d - nrm * (d * nrm).sum(1, keepdims=True)
    d = _norm(d)
    K = 5
    L = hair_len * (0.7 + 0.6 * rng.random(len(pos)))[:, None]
    if droop > 0:
        L = L * (1 + droop * 4.0 * np.clip(tt - 0.6, 0, 1) * 2.5)
    s = np.linspace(0, 1, K)[None, :, None]
    pts = pos[:, None, :] - nrm[:, None, :] * 0.0004 + d[:, None, :] * L[..., None] * s
    pts += nrm[:, None, :] * (0.0012 * np.sin(s * np.pi * 0.8))  # arc off the skin then back
    if droop > 0:
        g = -ez[None, None, :] * (s ** 2) * L[..., None] * 0.6 * droop * np.clip(tt[..., None] - 0.5, 0, 1) * 2
        pts += g
    pts = frizz(pts, rng, 0.0003)
    return curves_object("Brows", pts, 0.00006, 0.000015, mat, coll, pass_index=8)


# ------------------------------------------------------------------------------------- lashes
def lashes(surf, b, eyes, mat, rng, upper=70, lower=25, length=0.0075, coll=None):
    """Lashes rooted on the lid margin ring found where the skin meets each eyeball."""
    P, N = surf.P, surf.N
    fc = surf.A["fc"]
    lm = b["lm"]
    ez = np.array(lm["ez"])
    fwd = np.array(lm["ey"])
    out = []
    for eo in eyes:
        c = np.array(eo.matrix_world.translation)
        r = b["lm"]["eye_radius"]
        dist = np.linalg.norm(P - c, axis=1)
        rel = P - c
        front = (rel @ fwd) > r * 0.25
        ring = np.where((dist < r + 0.0016) & (dist > r - 0.002) & front)[0]
        if len(ring) < 8:
            continue
        rp = rel[ring]
        ex = np.array(lm["ex"])
        ang = np.arctan2(rp @ ez, rp @ ex)
        # keep the outermost (most forward) point per angular bin = the lid margin
        bins = np.linspace(-np.pi, np.pi, 73)
        margin, mang = [], []
        for i in range(len(bins) - 1):
            sel = (ang >= bins[i]) & (ang < bins[i + 1])
            if not sel.any():
                continue
            j = ring[sel][np.argmax((rel[ring[sel]] @ fwd))]
            margin.append(P[j])
            mang.append((bins[i] + bins[i + 1]) / 2)
        margin = np.array(margin)
        mang = np.array(mang)
        for which, n_l, L0, up in (("up", upper, length, 1.0), ("lo", lower, length * 0.45, -1.0)):
            sel = (np.sin(mang) > 0.15) if up > 0 else (np.sin(mang) < -0.25)
            if sel.sum() < 3:
                continue
            mp = margin[sel]
            ma = mang[sel]
            order = np.argsort(np.cos(ma))
            mp = mp[order]
            # resample along the margin
            seg = np.linalg.norm(np.diff(mp, axis=0), axis=1)
            cl = np.concatenate([[0], np.cumsum(seg)])
            tt = np.sort(rng.random(n_l)) * cl[-1]
            roots = np.stack([np.interp(tt, cl, mp[:, k]) for k in range(3)], 1)
            u = tt / max(cl[-1], 1e-9)
            centre_w = np.sin(np.pi * np.clip(u, 0, 1)) ** 0.6
            Ls = L0 * (0.55 + 0.45 * centre_w) * (0.8 + 0.4 * rng.random(n_l))
            radial = _norm(roots - c)
            K = 5
            s = np.linspace(0, 1, K)[None, :, None]
            d0 = _norm(fwd[None] * 0.8 + radial * 0.5 + ez[None] * 0.15 * up)
            curl = ez[None] * up
            pts = roots[:, None, :] + d0[:, None, :] * Ls[:, None, None] * s + curl[:, None, :] * Ls[:, None, None] * 0.55 * s ** 2
            out.append(pts)
    if not out:
        return None
    pts = np.concatenate(out)
    pts = frizz(pts, rng, 0.0002)
    return curves_object("Lashes", pts, 0.00007, 0.00002, mat, coll, pass_index=8)


# -------------------------------------------------------------------------------------- beard
def beard(surf, b, style, mat, rng, count=9000, coll=None, push=True):
    """Beard/moustache from a :func:`regions.beard` style.  Extra style keys:
        length (m, chin beard), must_len, cheek_len, curl, clumps, spread (forward bulge),
        gravity (0..1), taper (pointed/forked chin), fork (0..1)"""
    F = b["F"]
    lm = b["lm"]
    ex, ez, fwd = np.array(lm["ex"]), np.array(lm["ez"]), np.array(lm["ey"])

    def dens(a):
        return R.beard(a["fc"], F, style)
    pos, nrm, at = surf.roots(count, dens, rng)
    if len(pos) == 0:
        return None
    fc = at["fc"]
    x, y, z = fc[:, 0], fc[:, 1], fc[:, 2]
    ax = np.abs(x)
    side = np.sign(x + 1e-6)
    n = len(pos)
    # zone weights
    must = R.sstep(F.mouth_y - 0.02, F.mouth_y + 0.1, y) * R.sstep(F.nose_y - 0.02, F.nose_y - 0.1, y)
    chinz = 1 - R.sstep(F.mouth_y - 0.15, F.mouth_y + 0.05, y)
    L_chin = style.get("length", 0.08)
    L_must = style.get("must_len", 0.035)
    L_cheek = style.get("cheek_len", L_chin * 0.6)
    # beard length grows toward the chin centre (and shrinks up the cheeks)
    centre = 1.0 - R.sstep(0.2, 1.2, ax)
    L = L_cheek + (L_chin - L_cheek) * (centre ** 0.8) * chinz
    L = L * (1 - must) + L_must * must * (0.8 + 0.4 * R.sstep(0.0, F.mouth_w, ax))
    L *= (0.75 + 0.5 * rng.random(n))
    # sideburn/cheek hairs shorter near the top
    L *= 0.45 + 0.55 * R.sstep(F.nose_y + 0.3, F.mouth_y, y) * (1 - must) + must * 0.55
    # growth directions
    down = -ez[None]
    out_ = side[:, None] * ex[None]
    d_must = _norm(down * 0.9 + out_ * (0.55 + 0.4 * R.sstep(0.0, F.mouth_w, ax))[:, None] + fwd[None] * 0.25)
    d_beard = _norm(down * 1.0 + fwd[None] * (0.35 + style.get("spread", 0.3)) - out_ * 0.08)
    d = d_must * must[:, None] + d_beard * (1 - must[:, None])
    d = _norm(d + nrm * 0.25)
    K = int(style.get("points", 14))
    grav = style.get("gravity", 0.6)
    pts = np.zeros((n, K, 3))
    pts[:, 0] = pos - nrm * 0.0005
    v = d.copy()
    step = (L / (K - 1))[:, None]
    for k in range(1, K):
        tk = k / (K - 1)
        # bend toward gravity; moustache tips droop around the mouth
        v = _norm(v + down * grav * 0.12 * (0.5 + tk) + nrm * 0.03 * (1 - tk))
        pts[:, k] = pts[:, k - 1] + v * step
    # taper / fork the chin beard: pull tips toward one or two points under the chin
    taper = style.get("taper", 0.0)
    if taper > 0:
        tip_c = np.array(lm["chin"]) - ez * L_chin * 0.95 + fwd * L_chin * 0.25
        fork = style.get("fork", 0.0)
        tgt = np.tile(tip_c, (n, 1)) + out_ * fork * L_chin * 0.18
        t = (np.linspace(0, 1, K) ** 2)[None, :, None]
        w = (taper * chinz * (1 - must))[:, None, None]
        tipline = pts[:, :1] + (tgt[:, None, :] - pts[:, :1]) * np.linspace(0, 1, K)[None, :, None]
        pts = pts + (tipline - pts) * t * w * 0.85
    pts = clump(pts, rng, int(n / style.get("clump_size", 22)), amount=style.get("clump", 0.55),
                power=1.3)
    pts = frizz(pts, rng, style.get("frizz", 0.0012) * (L[:, None, None] / max(L_chin, 1e-3)) ** 0.5, 2.5)
    if push:
        offs = np.linspace(0.0005, 0.0045, K)
        surf.push_out(pts, offs, roots_fixed=1)
    rad = np.full(n, style.get("radius", 0.000075))
    return curves_object("Beard", pts, rad, style.get("radius", 0.000075) * 0.3, mat, coll)


# ---------------------------------------------------------------------------------- scalp hair
def skull_frame(surf, b):
    """Cranium centre (world) used for combing paths: the middle of the scalp vertices' bbox,
    nudged to the ear line."""
    F = b["F"]
    sc = R.scalp(surf.A["fc"], F, 0.0) > 0.5
    P = surf.P[sc]
    c = (P.min(0) + P.max(0)) / 2
    c[2] = P[:, 2].min() + 0.45 * (P[:, 2].max() - P[:, 2].min())
    return c


def comb(surf, b, mat, rng, waypoints_fn, count=7000, K=18, recede=0.0, lift=0.0016, volume=0.004,
         density_fn=None, coll=None, name="Hair", radius=0.00006, clump_n=None, clump_amt=0.35,
         push=True):
    """Scalp hair combed along spherical paths through per-strand waypoints.

    ``waypoints_fn(root_pos, root_fc, centre)`` -> list of (N,3) world points the strands pass
    through (the last is where they end).  Paths are spherical interpolations about the cranium
    centre, lifted ``lift`` + ``volume``*sin(pi t) off the scalp, then pushed out of the skin."""
    F = b["F"]
    C = skull_frame(surf, b)
    dfn = density_fn or (lambda a: R.scalp(a["fc"], F, recede, soft=1.5))
    pos, nrm, at = surf.roots(count, dfn, rng)
    n = len(pos)
    if n == 0:
        return None, C
    wps = waypoints_fn(pos, at["fc"], C)
    pts_all = [pos]
    segs = len(wps)
    per = max(2, (K - 1) // segs)
    cur = pos
    chain = [pos[:, None, :]]
    for w in wps:
        a = _norm(cur - C)
        bdir = _norm(w - C)
        t = np.linspace(0, 1, per + 1)[1:]
        dirs = _slerp_dirs(a, bdir, t)
        ra = np.linalg.norm(cur - C, axis=1)[:, None]
        rb = np.linalg.norm(w - C, axis=1)[:, None]
        rad = ra + (rb - ra) * t[None, :]
        seg = C[None, None, :] + dirs * rad[..., None]
        chain.append(seg)
        cur = w
    pts = np.concatenate(chain, 1)
    Kp = pts.shape[1]
    tt = np.linspace(0, 1, Kp)
    # lift off the scalp: strands from far away ride on top (layering)
    layer = (np.linalg.norm(pos - wps[-1], axis=1) / 0.25)[:, None]
    off = lift + volume * np.sin(np.pi * np.clip(tt * 1.15, 0, 1))[None, :] * (0.4 + 0.6 * np.clip(layer, 0, 1))
    radial = _norm(pts - C)
    pts = pts + radial * off[..., None] * np.clip(tt * 6, 0, 1)[None, :, None]
    if clump_n:
        pts = clump(pts, rng, clump_n, clump_amt, power=0.7)
    pts = frizz(pts, rng, 0.0005, 2.0)
    if push:
        surf.push_out(pts, np.linspace(0.0008, lift + 0.0005, Kp), roots_fixed=1)
    rad = np.full(n, radius)
    ob = curves_object(name, pts, rad, radius * 0.5, mat, coll)
    return ob, C


def bun_strands(centre, axis, radius, height, count, rng, K=24, turns=1.2, tight=0.15):
    """A coiled bun: strands spiral around ``axis`` on a squashed sphere."""
    axis = axis / np.linalg.norm(axis)
    tmp = np.array([1.0, 0, 0]) if abs(axis[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(axis, tmp)
    u /= np.linalg.norm(u)
    v = np.cross(axis, u)
    out = []
    for i in range(count):
        a0 = rng.random() * 2 * np.pi
        h0 = rng.uniform(-0.85, 0.85)
        dh = rng.uniform(-0.4, 0.4)
        tw = turns * (0.6 + 0.8 * rng.random())
        t = np.linspace(0, 1, K)
        a = a0 + t * tw * 2 * np.pi
        h = np.clip(h0 + dh * t, -0.95, 0.95)
        r = radius * np.sqrt(1 - h ** 2) * (1.0 + tight * rng.standard_normal() * 0.3) + 0.0008
        p = centre[None] + (np.cos(a)[:, None] * u + np.sin(a)[:, None] * v) * r[:, None] + axis[None] * (h * height)[:, None]
        out.append(p)
    return np.array(out)


def hair_cap(surf, b, mat, recede=0.0, offset=0.0012, coll=None, name="HairCap", density=None):
    """Thin shell over the scalp (hairline-shaped) under the strands: no skin shows through."""
    F = b["F"]
    fc = surf.A["fc"]
    w = density(surf.A) if density is not None else R.scalp(fc, F, recede, soft=1.0)
    keepv = w > 0.5
    T = surf.T
    keept = keepv[T].all(1)
    vids = np.unique(T[keept])
    remap = -np.ones(len(surf.P), np.int64)
    remap[vids] = np.arange(len(vids))
    P = surf.P[vids] + surf.N[vids] * offset
    faces = remap[T[keept]]
    me = bpy.data.meshes.new(name)
    me.from_pydata(P.tolist(), [], faces.tolist())
    # UV: (azimuth, elevation) around the cranium so stripes run hairline -> crown
    C = skull_frame(surf, b)
    rel = P - C
    az = np.arctan2(rel[:, 0], -rel[:, 1])
    el = np.arctan2(rel[:, 2], np.hypot(rel[:, 0], rel[:, 1]))
    uvl = me.uv_layers.new(name="UVMap")
    loop_v = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", loop_v)
    uvs = np.stack([az[loop_v] / 6.283, el[loop_v] / 3.1416], 1).astype(np.float32)
    uvl.data.foreach_set("uv", uvs.ravel())
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    (coll or bpy.context.scene.collection).objects.link(ob)
    ob.pass_index = 3
    return ob
