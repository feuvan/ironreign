"""Strand hair for portraits: beards, moustaches, brows, lashes, pulled-back scalp hair, buns.

Every groom is a set of numpy polylines (S strands x P points) turned into one Blender ``Curves``
object, rendered in Cycles with the Principled Hair BSDF (see :func:`hair_material`).

Roots are sampled on the *evaluated* bust (subdivided once) weighted by the zone masks of
:mod:`zones`; strands are integrated with a direction field (surface normal, gravity, combing
target), clumped into locks around guide strands (painters paint hair as locks, not as fuzz) and
kept outside the skin / costume with BVH nearest-surface queries.

Blender coords: metres, +Z up, the face looks towards -Y, the character's left is +X.
"""

import math

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .nodes import NB, lin, material, output, sock


# ---------------------------------------------------------------------------------------------
# surface sampling
# ---------------------------------------------------------------------------------------------
class Surface:
    """Evaluated triangle mesh of one or more objects + per-vertex float attributes + a BVH."""

    def __init__(self, objs, attrs=()):
        dg = bpy.context.evaluated_depsgraph_get()
        V, T, A = [], [], {k: [] for k in attrs}
        off = 0
        for o in objs:
            ev = o.evaluated_get(dg)
            me = ev.to_mesh()
            me.calc_loop_triangles()
            n = len(me.vertices)
            co = np.zeros(n * 3, np.float32)
            me.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3)
            mw = np.array(o.matrix_world, np.float32)
            co = co @ mw[:3, :3].T + mw[:3, 3]
            tri = np.zeros(len(me.loop_triangles) * 3, np.int32)
            me.loop_triangles.foreach_get("vertices", tri)
            V.append(co)
            T.append(tri.reshape(-1, 3) + off)
            for k in attrs:
                a = me.attributes.get(k)
                arr = np.zeros(n, np.float32)
                if a is not None and a.domain == "POINT":
                    a.data.foreach_get("value", arr)
                A[k].append(arr)
            off += n
            ev.to_mesh_clear()
        self.V = np.concatenate(V)
        self.T = np.concatenate(T)
        self.A = {k: np.concatenate(v) for k, v in A.items()}
        fn = np.cross(self.V[self.T[:, 1]] - self.V[self.T[:, 0]], self.V[self.T[:, 2]] - self.V[self.T[:, 0]])
        self.area = 0.5 * np.linalg.norm(fn, axis=1)
        vn = np.zeros_like(self.V)
        for i in range(3):
            np.add.at(vn, self.T[:, i], fn)
        self.N = vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
        self.bvh = BVHTree.FromPolygons(self.V.tolist(), self.T.tolist(),
                                        all_triangles=True, epsilon=0.0)

    def sample(self, weight, n, rng):
        """``n`` random points with density proportional to ``weight`` (per vertex)."""
        wt = weight[self.T].mean(1) * self.area
        tot = wt.sum()
        if tot <= 0 or n <= 0:
            return None
        p = wt / tot
        ti = rng.choice(len(self.T), size=n, p=p)
        r1, r2 = rng.random(n), rng.random(n)
        s = np.sqrt(r1)
        b = np.stack([1 - s, s * (1 - r2), s * r2], 1).astype(np.float32)
        tv = self.T[ti]
        pos = (self.V[tv] * b[..., None]).sum(1)
        nor = (self.N[tv] * b[..., None]).sum(1)
        nor /= np.linalg.norm(nor, axis=1, keepdims=True)
        attrs = {k: (a[tv] * b).sum(1) for k, a in self.A.items()}
        return pos, nor, attrs

    def push_out(self, pts, offset, max_dist=0.08):
        """Keep points at least ``offset`` (per point or scalar) outside the surface."""
        out = pts.copy()
        off = np.broadcast_to(np.asarray(offset, np.float32), (len(pts),))
        for i in range(len(pts)):
            loc, nor, idx, d = self.bvh.find_nearest(Vector(pts[i]), max_dist)
            if loc is None:
                continue
            rel = Vector(pts[i]) - loc
            h = rel.dot(nor)
            if h < off[i]:
                out[i] = np.array(loc + nor * off[i], np.float32)
        return out

    def nearest(self, pts, max_dist=0.2):
        loc = np.zeros_like(pts)
        nor = np.zeros_like(pts)
        for i in range(len(pts)):
            l, n, _, _ = self.bvh.find_nearest(Vector(pts[i]), max_dist)
            if l is None:
                loc[i], nor[i] = pts[i], (0, 0, 1)
            else:
                loc[i], nor[i] = l, n
        return loc, nor


def _norm(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)


# ---------------------------------------------------------------------------------------------
# curves object
# ---------------------------------------------------------------------------------------------
def curves_object(name, strands, r_root, r_tip, mat=None, col=None, attrs=None, taper=0.8):
    """strands (S,P,3); r_root/r_tip scalars or (S,) arrays (metres). ``attrs``: per-curve floats."""
    S, P, _ = strands.shape
    c = bpy.data.hair_curves.new(name)
    c.add_curves([P] * S)
    c.position_data.foreach_set("vector", strands.astype(np.float32).ravel())
    t = np.linspace(0, 1, P, dtype=np.float32) ** taper
    rr = np.broadcast_to(np.asarray(r_root, np.float32), (S,))[:, None]
    rt = np.broadcast_to(np.asarray(r_tip, np.float32), (S,))[:, None]
    rad = rr + (rt - rr) * t[None, :]
    ra = c.attributes.new("radius", "FLOAT", "POINT")
    ra.data.foreach_set("value", rad.astype(np.float32).ravel())
    for k, v in (attrs or {}).items():
        a = c.attributes.new(k, "FLOAT", "CURVE")
        a.data.foreach_set("value", np.asarray(v, np.float32))
    if mat is not None:
        c.materials.append(mat)
    ob = bpy.data.objects.new(name, c)
    (col or bpy.context.scene.collection).objects.link(ob)
    return ob


def hair_material(name, melanin=0.9, redness=0.2, grey=0.0, grey_melanin=0.08, roughness=0.42,
                  radial=0.5, coat=0.1, tint=(1, 1, 1), random_color=0.12, key_dir=None,
                  rim_boost=0.0):
    """Principled Hair (Chiang) with salt-and-pepper greying: a per-curve random value above
    ``1 - grey`` switches the strand to ``grey_melanin``.  AOV ``hair`` for the compositor."""
    m, nb = material(name)

    def hb(mel, red):
        h = nb.node("ShaderNodeBsdfHairPrincipled", parametrization="MELANIN")
        nb.set(sock(h.inputs, "Melanin"), mel)
        nb.set(sock(h.inputs, "Melanin Redness"), red)
        nb.set(sock(h.inputs, "Tint"), tint)
        nb.set(sock(h.inputs, "Roughness"), roughness)
        nb.set(sock(h.inputs, "Radial Roughness"), radial)
        nb.set(sock(h.inputs, "Coat"), coat)
        nb.set(sock(h.inputs, "Random Color"), random_color)
        nb.set(sock(h.inputs, "Random Roughness"), 0.2)
        return h
    dark = hb(melanin, redness)
    if grey > 0:
        light = hb(grey_melanin, 0.3)
        info = nb.node("ShaderNodeHairInfo")
        # grey more at the strand tips? no: per-strand (salt and pepper), slight extra on the
        # per-curve attribute 'greyness' if present (temples / chin go grey first)
        ga = nb.attr("greyness")
        r = nb.math("ADD", info.outputs["Random"], nb.math("MULTIPLY", ga, 0.6))
        sw = nb.math("GREATER_THAN", r, 1.0 - grey)
        mix = nb.node("ShaderNodeMixShader")
        nb.set(mix.inputs[0], sw)
        nb.set(mix.inputs[1], dark.outputs[0])
        nb.set(mix.inputs[2], light.outputs[0])
        sh = mix.outputs[0]
    else:
        sh = dark.outputs[0]
    output(nb, sh)
    nb.aov("hair", 1.0)
    return m


# ---------------------------------------------------------------------------------------------
# generic strand integrator
# ---------------------------------------------------------------------------------------------
def grow(roots, dirs, lengths, P, gravity=0.0, stiff=0.6, curl=0.0, curl_freq=3.0, rng=None,
         bend_to=None, bend=0.0, noise=0.0):
    """Integrate strands from ``roots`` along ``dirs``; direction blends towards -Z by
    ``gravity`` (more towards the tip when ``stiff`` is high) and towards ``bend_to`` (S,3) by
    ``bend``.  Returns (S,P,3)."""
    S = len(roots)
    rng = rng or np.random.default_rng(0)
    pts = np.zeros((S, P, 3), np.float32)
    pts[:, 0] = roots
    d = _norm(dirs.astype(np.float32))
    step = (lengths / (P - 1)).astype(np.float32)[:, None]
    down = np.array([0, 0, -1], np.float32)
    ph = rng.random((S, 1)) * 6.283
    side = _norm(np.cross(d, down + 1e-3))
    for i in range(1, P):
        t = i / (P - 1)
        g = gravity * (t ** stiff)
        nd = _norm(d * (1 - g) + down * g)
        if bend_to is not None and bend > 0:
            nd = _norm(nd + bend * t * bend_to)
        if curl > 0:
            ang = ph + t * curl_freq * 6.283
            up = _norm(np.cross(side, nd))
            nd = _norm(nd + curl * (side * np.cos(ang) + up * np.sin(ang)))
        if noise > 0:
            nd = _norm(nd + noise * rng.normal(size=(S, 3)).astype(np.float32))
        pts[:, i] = pts[:, i - 1] + nd * step
        d = nd
    return pts


def clump(strands, n_guides, amount, rng, power=1.2, spread=0.0):
    """Pull strands towards their nearest guide strand (guides = a random subset)."""
    S, P, _ = strands.shape
    if n_guides <= 0 or amount <= 0:
        return strands
    gi = rng.choice(S, size=min(n_guides, S), replace=False)
    roots = strands[:, 0]
    # nearest guide by root distance (chunked brute force)
    gid = np.zeros(S, np.int64)
    G = roots[gi]
    for a in range(0, S, 4096):
        d = np.linalg.norm(roots[a:a + 4096, None, :] - G[None], axis=2)
        gid[a:a + 4096] = np.argmin(d, 1)
    g = strands[gi[gid]]
    t = np.linspace(0, 1, P, dtype=np.float32)[None, :, None] ** power
    amt = amount * (0.75 + 0.5 * rng.random((S, 1, 1)))
    out = strands + (g - strands) * np.clip(amt * t, 0, 0.97)
    if spread > 0:
        # keep a little of the root offset so locks are not lines
        out += (strands[:, :1] - g[:, :1]) * spread * t
    return out.astype(np.float32)


def collide(surf, strands, offset=0.0015, start=1):
    S, P, _ = strands.shape
    out = strands.copy()
    for i in range(start, P):
        # push this point out and carry the correction to the rest of the strand
        moved = surf.push_out(out[:, i], offset)
        delta = moved - out[:, i]
        out[:, i:] += delta[:, None, :]
    return out


# ---------------------------------------------------------------------------------------------
# grooms
# ---------------------------------------------------------------------------------------------
def _outward(pos, center):
    h = pos - center
    h[:, 2] = 0
    return _norm(h)


def beard(surf, lm, rng, density=1.0, chin_len=0.12, cheek_len=0.05, neck_len=0.06, curl=0.08,
          clumping=0.55, P=14, droop=0.85, width_scale=1.0, forward=0.25, style="full",
          r_root=0.00016, r_tip=0.00006, count=7000):
    """Full beard: length grows towards the chin; strands fall forward and down over the chest."""
    w = surf.A["z_beard"].copy()
    if style == "goatee":
        w = surf.A["z_goatee"] * 1.0 + w * 0.08
    elif style == "chin":
        w = np.maximum(surf.A["z_goatee"], w * 0.35)
    n = int(count * density)
    smp = surf.sample(w, n, rng)
    if smp is None:
        return None
    pos, nor, at = smp
    chin = np.asarray(lm["chin"], np.float32)
    jaw_c = np.asarray(lm["eye_c"], np.float32) + np.array([0, 0.02, -0.06], np.float32)
    # region factor: 1 at the chin, 0 on the upper cheeks / sideburns
    dx = np.abs(pos[:, 0] - chin[0])
    dz = np.clip((pos[:, 2] - chin[2]) / 0.08, 0, 1)
    chin_f = np.exp(-(dx / (0.045 * width_scale)) ** 2) * (1 - 0.6 * dz)
    under = np.clip((chin[2] + 0.01 - pos[:, 2]) / 0.03, 0, 1) * (pos[:, 1] > chin[1] + 0.01)
    L = cheek_len + (chin_len - cheek_len) * chin_f
    L = L * (1 - 0.35 * dz) + neck_len * under * 0.5
    L *= 0.7 + 0.6 * rng.random(n)
    out = _outward(pos, jaw_c)
    down = np.array([0, 0, -1], np.float32)
    fwd = np.array([0, -1, 0], np.float32)
    d = nor * 0.55 + down * 0.6 + out * 0.15 + fwd * forward * chin_f[:, None]
    pts = grow(pos, d, L, P, gravity=droop, stiff=0.8, curl=curl, curl_freq=2.0, rng=rng,
               noise=0.04)
    pts = clump(pts, max(8, n // 40), clumping, rng, power=1.3, spread=0.15)
    pts = collide(surf, pts, 0.002)
    grey = np.clip(1 - chin_f, 0, 1) * 0.3
    return pts, dict(r_root=r_root, r_tip=r_tip, attrs={"greyness": grey})


def moustache(surf, lm, rng, length=0.045, droop=0.6, density=1.0, P=10, clumping=0.5,
              r_root=0.00015, r_tip=0.00005, count=1600, spread=1.0):
    w = surf.A["z_moustache"]
    n = int(count * density)
    smp = surf.sample(w, n, rng)
    if smp is None:
        return None
    pos, nor, at = smp
    sub = np.asarray(lm["subnasale"], np.float32)
    lat = np.sign(pos[:, 0] - sub[0])[:, None] * np.array([1, 0, 0], np.float32)
    down = np.array([0, 0, -1], np.float32)
    rel = np.abs(pos[:, 0] - sub[0]) / 0.03
    L = length * (0.55 + 0.6 * np.clip(rel, 0, 1)) * (0.75 + 0.5 * rng.random(n))
    d = lat * (0.75 * spread) + down * 0.55 + nor * 0.35
    pts = grow(pos, d, L, P, gravity=droop, stiff=1.0, rng=rng, noise=0.03)
    pts = clump(pts, max(6, n // 30), clumping, rng)
    pts = collide(surf, pts, 0.0018)
    return pts, dict(r_root=r_root, r_tip=r_tip, attrs={"greyness": np.zeros(len(pts))})


def brows(surf, lm, rng, length=0.011, density=1.0, P=6, lift=0.25, droop=0.0, tail_len=1.0,
          r_root=0.00011, r_tip=0.00004, count=900, thickness=1.0, angle=0.0):
    """Brow strands lie along the skin: medial ones point up, the body points lateral, the tail
    slightly down.  ``angle`` > 0 raises the lateral end (fierce), < 0 drops it (worried/sage)."""
    w = surf.A["z_brow"] * thickness
    n = int(count * density)
    smp = surf.sample(w, n, rng)
    if smp is None:
        return None
    pos, nor, at = smp
    c = np.asarray(lm["eye_c"], np.float32)
    sx = np.sign(pos[:, 0] - c[0])
    ax = np.abs(pos[:, 0] - c[0])
    lat = np.stack([sx, np.zeros_like(sx), np.zeros_like(sx)], 1).astype(np.float32)
    up = np.array([0, 0, 1], np.float32)
    medial = np.clip((0.028 - ax) / 0.012, 0, 1)[:, None]
    tail = np.clip((ax - 0.045) / 0.015, 0, 1)[:, None]
    d = lat * (1 - medial * 0.7) + up * (lift + medial * 0.9 - tail * 0.25 + angle * (ax[:, None] / 0.05))
    # flatten onto the skin
    d = d - nor * np.sum(d * nor, 1, keepdims=True) + nor * 0.12
    L = length * (0.6 + 0.4 * rng.random(n)) * (1 + (tail_len - 1) * tail[:, 0])
    pts = grow(pos, d, L, P, gravity=droop, stiff=1.0, rng=rng, noise=0.05)
    pts = collide(surf, pts, 0.0007)
    return pts, dict(r_root=r_root, r_tip=r_tip, attrs={"greyness": np.zeros(len(pts))})


def lashes(surf, lm, rng, length=0.0075, count=70, P=6, r_root=0.00009, r_tip=0.00003, lower=0.3):
    out = []
    w = surf.A["z_lash"]
    smp = surf.sample(w, count * 2, rng)
    if smp is None:
        return None
    pos, nor, at = smp
    c = np.asarray(lm["eye_c"], np.float32)
    up = np.array([0, 0, 1], np.float32)
    fwd = np.array([0, -1, 0], np.float32)
    sx = np.sign(pos[:, 0] - c[0])
    lat = np.stack([sx, np.zeros_like(sx), np.zeros_like(sx)], 1).astype(np.float32)
    ec = np.where(sx[:, None] > 0, np.asarray(lm["eye_l"], np.float32), np.asarray(lm["eye_r"], np.float32))
    outer = np.clip((np.abs(pos[:, 0] - ec[:, 0]) * np.sign(pos[:, 0] - ec[:, 0]) * sx) / 0.012, -1, 1)
    d = fwd * 0.8 + up * 0.55 + lat * 0.25 * np.clip(outer, 0, 1)[:, None]
    L = length * (0.7 + 0.3 * rng.random(len(pos))) * (0.8 + 0.4 * np.clip(outer, 0, 1))
    pts = grow(pos, d, L, P, bend_to=np.tile(up, (len(pos), 1)), bend=0.9, rng=rng)
    out.append(pts)
    return np.concatenate(out), dict(r_root=r_root, r_tip=r_tip, attrs={"greyness": np.zeros(len(pts))})


def scalp_to_knot(surf, lm, rng, knot, count=14000, P=14, layer=(0.0008, 0.005), part=None,
                  r_root=0.00012, r_tip=0.00008, comb_noise=0.15, stop=0.02):
    """Hair combed from the hairline towards ``knot`` (top-knot / bun base), following the scalp.

    ``part``: None (all combed back) or 'center' (parted on the midline, combed sideways first).
    """
    w = surf.A["z_scalp"]
    smp = surf.sample(w, count, rng)
    if smp is None:
        return None
    pos, nor, at = smp
    knot = np.asarray(knot, np.float32)
    S = len(pos)
    off = (layer[0] + (layer[1] - layer[0]) * rng.random(S) ** 1.5).astype(np.float32)
    dist = np.linalg.norm(pos - knot, axis=1)
    step = (dist * 1.25 / (P - 1))[:, None]
    pts = np.zeros((S, P, 3), np.float32)
    pts[:, 0] = pos
    cur = pos + nor * off[:, None] * 0.3
    # low-frequency comb field: per-strand lateral wobble seeded by root position (grooves)
    phase = (pos[:, 0] * 180.0 + pos[:, 2] * 60.0)
    lat_amp = comb_noise * np.sin(phase)[:, None]
    for i in range(1, P):
        t = i / (P - 1)
        loc, nn = surf.nearest(cur)
        to = knot - cur
        tang = to - nn * np.sum(to * nn, 1, keepdims=True)
        side = _norm(np.cross(nn, _norm(tang)))
        dvec = _norm(tang) + side * lat_amp * (1 - t)
        if part == "center":
            # first sweep away from the midline, then back to the knot
            sw = np.sign(cur[:, 0] - knot[0])[:, None] * np.array([1, 0, 0], np.float32)
            dvec = _norm(dvec + sw * 0.8 * (1 - t) ** 2)
        nxt = cur + _norm(dvec) * np.minimum(step, np.linalg.norm(to, axis=1, keepdims=True) * 0.6)
        l2, n2 = surf.nearest(nxt)
        h = off[:, None] * (0.4 + 0.6 * min(1.0, t * 3)) + 0.0006
        nxt = l2 + n2 * h
        # near the knot lift into it
        near = np.linalg.norm(nxt - knot, axis=1) < stop
        nxt[near] = (nxt[near] + knot) * 0.5
        pts[:, i] = nxt
        cur = nxt
    return pts, dict(r_root=r_root, r_tip=r_tip, attrs={"greyness": np.clip(1 - at["z_scalp"], 0, 1)})


def bun(center, rng, radius=0.035, height=0.03, count=3000, P=18, turns=1.2, axis=(0, 0, 1),
        r_root=0.00014, r_tip=0.0001, flat=1.0):
    """Wound bun: strands wrap around an ellipsoid (latitude swirls with drift)."""
    c = np.asarray(center, np.float32)
    S = count
    a0 = rng.random(S) * 6.283
    lat0 = rng.uniform(-0.9, 0.9, S)
    pts = np.zeros((S, P, 3), np.float32)
    span = turns * 6.283 * (0.6 + 0.4 * rng.random(S))
    lat_drift = rng.uniform(-0.5, 0.5, S)
    shell = 1.0 + 0.08 * rng.random(S)
    for i in range(P):
        t = i / (P - 1)
        a = a0 + span * t
        la = np.clip(lat0 + lat_drift * t, -1.2, 1.2)
        r = radius * np.cos(la) * shell
        pts[:, i, 0] = c[0] + r * np.cos(a)
        pts[:, i, 1] = c[1] + r * np.sin(a) * flat
        pts[:, i, 2] = c[2] + height * np.sin(la) * shell
    return pts, dict(r_root=r_root, r_tip=r_tip, attrs={"greyness": rng.random(S) * 0.3})


def side_locks(surf, lm, rng, count=120, length=0.16, P=16, r_root=0.0001, r_tip=0.00005):
    """Two thin locks falling from the temples in front of the ears (court-lady styling)."""
    outp = []
    for side in (1, -1):
        ear = np.asarray(lm["ear_l" if side > 0 else "ear_r"], np.float32)
        root = ear + np.array([0.004 * side, -0.022, 0.035], np.float32)
        roots = root + rng.normal(size=(count, 3)).astype(np.float32) * 0.003
        d = np.tile(np.array([0.05 * side, -0.25, -1.0], np.float32), (count, 1))
        L = length * (0.85 + 0.3 * rng.random(count))
        pts = grow(roots, d, L, P, gravity=0.9, stiff=1.0, curl=0.06, curl_freq=1.0, rng=rng, noise=0.02)
        pts = clump(pts, 4, 0.7, rng)
        outp.append(pts)
    pts = np.concatenate(outp)
    pts = collide(surf, pts, 0.004)
    return pts, dict(r_root=r_root, r_tip=r_tip, attrs={"greyness": np.zeros(len(pts))})


def make(name, res, mat, col=None):
    if res is None:
        return None
    pts, kw = res
    return curves_object(name, pts, kw["r_root"], kw["r_tip"], mat, col, kw.get("attrs"))
