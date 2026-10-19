"""Illustrated Scenes (gongbi): painted trees and plants built for ink outlines.

Real-scale (metres) builders into :class:`ironart.geometry.MeshBuilder`, origin at the foot of
the plant.  Shapes are kept *clean* (smooth trunks, a few lumpy canopy masses, flat blades) so the
Freestyle 'tree' ink set draws calligraphic outlines; leaf / needle texture comes from the
materials' ``gb_ink`` strokes:

* pine      crooked trunk with 鳞皴 scale bark, near-horizontal limbs, needle pads drawn as
            radiating needle fans (松针) facing the viewer
* broadleaf trunk + limbs + lumpy canopy masses with 点叶 leaf dots
* willow    trunk + long hanging strands
* bamboo    jointed stems + 双钩 outlined leaf blades in clusters
* dead      bare branching tree with crab-claw twigs (蟹爪)
* plum      gnarled branches with lead-white / rouge blossoms
* reeds / grass / rice tufts (blades)

Slot names (see :func:`materials`): Bark, PineBark, Needles, Leaf, LeafDark, LeafAutumn, Willow,
Bamboo, BambooLeaf, Blossom, BlossomRed, Reed, Rice, DeadBark.
"""

import math
import random

from mathutils import Matrix, Vector

from . import scenes_gongbi as GB


# =============================================================================================
# materials
# =============================================================================================
def bark(name, color="#8A6A4A", deep="#5A4430", scales=0.0, scale=4.0):
    mat, b, created = GB._builder(name)
    if not created:
        return mat
    g = GB.facing(b, 0.4, 0.1, 1.0)
    col = b.mix(GB.lin4(color), GB.lin4(deep), g)
    ink = 0.0
    if scales > 0:
        P = GB.wpos(b)
        v = b.node("ShaderNodeTexVoronoi", voronoi_dimensions="3D", feature="DISTANCE_TO_EDGE")
        v.inputs["Scale"].default_value = scale
        b.link(b.vmath("MULTIPLY", P, b.vec((1.0, 1.0, 0.55))).outputs[0], v.inputs["Vector"])
        e = b.smooth(v.outputs["Distance"], 0.06, 0.02)
        ink = b.math("MULTIPLY", e, scales)
    return GB.finish(mat, b, col, ink=ink)


def needles(name="GB_Needles", color="#3F7A5E", deep="#24503E", lines=1.0, n=11.0, fans=2.2):
    """Pine needle clusters (松针): a dark malachite wash under wheels of needles - in each pad's
    view plane (vertex attributes pu / pv, offsets normalised to the pad radius) a Voronoi grid
    of fan centres, each radiating ``n`` needle strokes; the wash deepens towards the pad rim and
    underneath."""
    mat, b, created = GB._builder(name)
    if not created:
        return mat
    pu = b.attr("pu").outputs["Fac"]
    pv = b.attr("pv").outputs["Fac"]
    r = b.math("SQRT", b.math("ADD", b.math("MULTIPLY", pu, pu), b.math("MULTIPLY", pv, pv)))
    vec = b.comb(b.math("MULTIPLY", pu, 1.0), b.math("MULTIPLY", pv, 1.35), 0.0)
    vo = b.node("ShaderNodeTexVoronoi", voronoi_dimensions="2D", feature="F1", distance="EUCLIDEAN")
    vo.inputs["Scale"].default_value = fans
    vo.inputs["Randomness"].default_value = 0.85
    b.link(vec, vo.inputs["Vector"])
    cx, cy, _ = b.sep(vo.outputs["Position"])
    px, py, _ = b.sep(b.vmath("MULTIPLY", vec, b.vec((fans, fans, 1.0))).outputs[0])
    ang = b.math("ARCTAN2", b.math("SUBTRACT", py, cy), b.math("SUBTRACT", px, cx))
    dd = vo.outputs["Distance"]
    # needles fan upwards: strongest in the upper half of each wheel
    ln = b.smooth(b.math("ABSOLUTE", b.math("SINE", b.math("MULTIPLY", ang, n))), 0.3, 0.1)
    ring_m = b.math("MULTIPLY", b.smooth(dd, 0.08, 0.2), b.smooth(dd, 0.62, 0.48))
    up = b.smooth(b.math("SINE", ang), -0.6, 0.2)
    ink = b.math("MULTIPLY", b.math("MULTIPLY", ln, ring_m), b.math("ADD", 0.35, b.math("MULTIPLY", up, 0.65)))
    ink = b.math("MULTIPLY", b.math("MULTIPLY", ink, b.smooth(r, 1.15, 0.85)), lines)
    nz = b.sep(b.node("ShaderNodeNewGeometry").outputs["Normal"])[2]
    g = b.math("MAXIMUM", b.math("MAXIMUM", b.smooth(r, 0.45, 1.05), b.smooth(nz, 0.3, -0.5)),
               GB.facing(b, 0.3, 0.35, 1.0))
    g = b.math("MAXIMUM", g, b.math("MULTIPLY", b.smooth(dd, 0.15, 0.5), 0.35))
    col = b.mix(GB.lin4(color), GB.lin4(deep), g)
    return GB.finish(mat, b, col, ink=ink, form=0.06)


def foliage(name, color="malachite", deep="malachite_d", dots=0.85, spacing=2.6, size=0.3,
            light=None):
    """Canopy clump: wash deepening downwards and at the clump outline (分染), lighter on top
    (``light``), and 点叶 leaf dabs in ``gb_ink``: dabs ``spacing`` game px apart on screen (so
    they read at every distance), denser on the lit upper part of each clump, broken into
    groups."""
    mat, b, created = GB._builder(name)
    if not created:
        return mat
    nz = b.sep(b.node("ShaderNodeNewGeometry").outputs["Normal"])[2]
    g = b.math("MAXIMUM", b.smooth(nz, 0.55, -0.55), GB.facing(b, 0.35, 0.3, 1.0))
    col = b.mix(GB.lin4(color), GB.lin4(deep), g)
    if light:
        col = b.mix(col, GB.lin4(light), b.math("MULTIPLY", b.smooth(nz, 0.3, 0.9), 0.45))
    sx, sy = GB.screen(b)
    P = GB.wpos(b)
    jit = b.math("MULTIPLY", GB.wnoise(b, P, 0.8, 2.0, 0.5), 1.5)
    vec = b.comb(b.math("ADD", sx, jit), b.math("MULTIPLY", sy, 1.25), 0.0)
    vo = b.node("ShaderNodeTexVoronoi", voronoi_dimensions="2D", feature="F1", distance="EUCLIDEAN")
    vo.inputs["Scale"].default_value = 1.0 / spacing
    vo.inputs["Randomness"].default_value = 1.0
    b.link(vec, vo.inputs["Vector"])
    d = b.smooth(vo.outputs["Distance"], size, size * 0.5)
    brk = b.smooth(GB.wnoise(b, P, 0.9, 2.0, 0.5), 0.34, 0.54)
    top = b.smooth(nz, -0.6, 0.5)
    ink = b.math("MULTIPLY", b.math("MULTIPLY", b.math("MULTIPLY", d, brk), dots),
                 b.math("ADD", 0.3, b.math("MULTIPLY", top, 0.7)))
    return GB.finish(mat, b, col, ink=ink, form=0.08)


def materials(**over):
    """Default slot -> material dict (override any slot with ``over``)."""
    m = {
        "Bark": bark("GB_Bark", "#8A6E50", "#5A4632"),
        "PineBark": bark("GB_PineBark", "#9A6E4A", "#5E4030", scales=0.55, scale=5.0),
        "DeadBark": bark("GB_DeadBark", "#6E5E4E", "#3E342A", scales=0.3, scale=3.0),
        "Needles": needles("GB_Needles"),
        "Leaf": foliage("GB_Leaf", "malachite", "malachite_d", light="malachite_l"),
        "LeafDark": foliage("GB_LeafDark", "#2E6A5A", "#1E4A3E", light="#4E8A70"),
        "LeafLight": foliage("GB_LeafLight", "malachite_l", "malachite", light="#B8D4B0"),
        "LeafAutumn": foliage("GB_LeafAutumn", "#C08A3A", "vermilion", light="#D8B060"),
        "Willow": GB.wash("GB_Willow", "#9CC49A", "#5E9A72", blend=0.3, form=0.0),
        "Bamboo": GB.wash("GB_Bamboo", "#6FA07A", "#3E7A58", blend=0.4),
        "BambooLeaf": GB.wash("GB_BambooLeaf", "#4E8E66", "#2A5E44", blend=0.3, form=0.05),
        "Blossom": GB.wash("GB_Blossom", "white", "#E8C8C0", blend=0.3, form=0.0, nomist=0.5),
        "BlossomRed": GB.wash("GB_BlossomRed", "#E2A0A0", "rouge", blend=0.3, form=0.0, nomist=0.5),
        "Reed": GB.wash("GB_Reed", "#B8A46A", "#8A7448", blend=0.3, form=0.0),
        "Rice": GB.wash("GB_Rice", "#D8B050", "#B08030", blend=0.3, form=0.0),
        "Grass": GB.wash("GB_Grass", "#8AA670", "#5E7E4E", blend=0.3, form=0.0),
    }
    m.update(over)
    return m


# =============================================================================================
# helpers
# =============================================================================================
def _path(p0, d, length, n, rng, bend=0.15, up=0.0):
    """Crooked polyline from p0 along direction d."""
    pts = [Vector(p0)]
    d = Vector(d).normalized()
    step = length / n
    for i in range(n):
        d = (d + Vector((rng.uniform(-bend, bend), rng.uniform(-bend, bend), rng.uniform(-bend, bend) * 0.5 + up))).normalized()
        pts.append(pts[-1] + d * step)
    return pts


def _tube(mb, pts, r0, r1, mat, seg=7):
    n = len(pts)
    mb.tube([tuple(p) for p in pts], r0, mat, seg, caps=True,
            radius_fn=lambda t: (r0 + (r1 - r0) * t) / r0)


def _pad_attrs(mb, start, center, radius, right, up, lift=0.35):
    """Write pu / pv (view-plane offsets / radius) for the vertices from ``start``; the fan
    centre sits ``lift`` x radius below the pad centre so the needles radiate up and out."""
    pu = mb.vattr.setdefault("pu", {})
    pv = mb.vattr.setdefault("pv", {})
    c = Vector(center) - Vector(up) * radius * lift
    for i in range(start, mb.n):
        d = mb.verts[i] - c
        pu[i] = d.dot(right) / radius
        pv[i] = d.dot(up) / radius


def view_axes(cam_dir):
    """(right, up) unit vectors of a view looking along ``cam_dir`` (world +Z up)."""
    f = Vector(cam_dir).normalized()
    right = f.cross(Vector((0, 0, 1))).normalized()
    up = right.cross(f).normalized()
    return right, up


# =============================================================================================
# trees
# =============================================================================================
def _needle_cloud(mb, rng, c, r, right, up, n=4, flat=0.3, seg=(12, 6)):
    """A cloud of needle pads around ``c``: a main pad and ``n - 1`` smaller ones, overlapping
    like the layered needle masses of a painted pine."""
    pads = [(Vector(c), r)]
    for k in range(n - 1):
        a = rng.uniform(0, math.tau)
        o = Vector((math.cos(a) * r * 0.75, math.sin(a) * r * 0.6, rng.uniform(-0.25, 0.2) * r))
        pads.append((Vector(c) + o, r * rng.uniform(0.5, 0.75)))
    for (pc, pr) in pads:
        s0 = mb.n
        mb.sphere(tuple(pc), pr, "Needles", seg[0], seg[1], scale=(1.3, 1.1, flat))
        # lobed rim: push the rim in / out a little so the silhouette is a scalloped cloud
        ph = rng.uniform(0, math.tau)
        for vi in range(s0, mb.n):
            v = mb.verts[vi] - pc
            ang = math.atan2(v.y, v.x)
            mb.verts[vi] = pc + Vector((v.x, v.y, v.z)) * (1.0 + 0.12 * math.sin(5 * ang + ph))
        _pad_attrs(mb, s0, pc, pr * 1.3, right, up)


def pine(mb, rng, height=12.0, lean=0.15, limbs=5, pad=None, cam_dir=(0, 1, 0), at=(0, 0, 0),
         trunk_r=None, flat=0.3, seg=7, pad_seg=(12, 6), crown=1.0, reach=None):
    """Gnarled Chinese pine (松) as painters draw it: a crooked, scaly trunk; long, nearly level
    limbs that kink and droop; layered clouds of needle pads at the limb ends and a flat crown.
    ``reach`` = (x, y) horizontal direction the tree leans and stretches its limbs towards (a
    cliff pine reaching over the drop)."""
    right, up = view_axes(cam_dir)
    o = Vector(at)
    H = height
    tr = trunk_r or H * 0.042
    if reach is not None:
        d0 = Vector((reach[0] * lean, reach[1] * lean, 1.0))
    else:
        d0 = Vector((rng.uniform(-lean, lean), rng.uniform(-lean, lean), 1.0))
    trunk = _path(o, d0, H * 0.9, 7, rng, bend=0.2, up=0.12 if reach is None else 0.0)
    _tube(mb, trunk, tr, tr * 0.32, "PineBark", seg)
    pr = pad or H * 0.13
    side = 1 if rng.random() < 0.5 else -1
    for i in range(limbs):
        t = 0.38 + 0.55 * i / max(1, limbs - 1) + rng.uniform(-0.03, 0.03)
        k = min(len(trunk) - 2, int(t * (len(trunk) - 1)))
        base = trunk[k].lerp(trunk[k + 1], (t * (len(trunk) - 1)) % 1.0)
        side = -side
        if reach is not None:
            ang = math.atan2(reach[1], reach[0]) + rng.uniform(-0.9, 0.9)
        else:
            ang = math.atan2(right.y, right.x) * 0 + (0.0 if side > 0 else math.pi) + rng.uniform(-0.8, 0.8)
            ang += math.atan2(right.y, right.x)
        d = Vector((math.cos(ang), math.sin(ang), rng.uniform(-0.05, 0.2)))
        L = H * (0.46 - 0.3 * t) * crown * rng.uniform(0.85, 1.2)
        limb = _path(base, d, L, 4, rng, bend=0.3, up=-0.02)
        _tube(mb, limb, tr * (0.6 - 0.35 * t), tr * 0.16, "PineBark", 6)
        _needle_cloud(mb, rng, limb[-1] + Vector((0, 0, pr * 0.25)), pr * (1.15 - 0.35 * t), right, up,
                      n=rng.randint(3, 5), flat=flat, seg=pad_seg)
        if rng.random() < 0.55:
            _needle_cloud(mb, rng, limb[2] + Vector((0, 0, pr * 0.3)), pr * 0.7, right, up, n=2, flat=flat,
                          seg=pad_seg)
    _needle_cloud(mb, rng, trunk[-1] + Vector((0, 0, pr * 0.15)), pr * 1.1, right, up, n=4, flat=flat * 0.9,
                  seg=pad_seg)
    return trunk[-1]


def broadleaf(mb, rng, height=10.0, crown=0.42, masses=7, at=(0, 0, 0), leaf="Leaf", lean=0.1,
               trunk_r=None, seg=7, mass_seg=(14, 9), lump=0.18, flat=0.75):
    """Broadleaf tree in the painted manner: a trunk forking into crooked limbs and twigs, the
    foliage as many separate clumps at the branch ends (each outlined, deeper underneath), with
    the branches showing between them.  ``masses`` scales the number of clumps."""
    o = Vector(at)
    H = height
    tr = trunk_r or H * 0.032
    d0 = Vector((rng.uniform(-lean, lean), rng.uniform(-lean, lean), 1.0))
    trunk = _path(o, d0, H * 0.5, 4, rng, bend=0.16, up=0.2)
    _tube(mb, trunk, tr, tr * 0.62, "Bark", seg)
    top = trunk[-1]
    R = H * crown
    tips = []

    def grow(p, d, L, r, lvl):
        pts = _path(p, d, L, 3, rng, bend=0.22, up=0.06)
        _tube(mb, pts, r, r * 0.6, "Bark", 6 if lvl < 2 else 4)
        if lvl >= 2:
            tips.append(pts[-1])
            return
        for j in range(2 if lvl else 3):
            a = rng.uniform(0, math.tau)
            nd = (d * 0.55 + Vector((math.cos(a) * 0.8, math.sin(a) * 0.8, rng.uniform(0.15, 0.7)))).normalized()
            grow(pts[-1], nd, L * rng.uniform(0.55, 0.75), r * 0.6, lvl + 1)
    for j in range(3):
        a = j / 3 * math.tau + rng.uniform(-0.5, 0.5)
        d = Vector((math.cos(a) * 0.65, math.sin(a) * 0.65, 1.0)).normalized()
        grow(top, d, H * 0.24, tr * 0.6, 0)
    n_cl = max(6, int(masses * 2.0))
    cc = top + Vector((0, 0, R * 0.55))
    for i in range(n_cl):
        # clumps spread over a rounded dome (and a few inside it), each near a branch tip
        az = rng.uniform(0, math.tau)
        el = rng.uniform(-0.35, 1.25)
        dirv = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el) * 0.8))
        c = cc + dirv * R * rng.uniform(0.45, 0.72)
        if tips:
            near = min(tips, key=lambda q: (q - c).length)
            c = c.lerp(near + Vector((0, 0, R * 0.1)), 0.25)
        r = R * rng.uniform(0.3, 0.42)
        s = mb.n
        mb.sphere(tuple(c), r, leaf, mass_seg[0], mass_seg[1], scale=(1.15, 1.1, flat))
        ph = [rng.uniform(0, math.tau) for _ in range(3)]
        for vi in range(s, mb.n):
            v = mb.verts[vi] - c
            if v.length < 1e-6:
                continue
            ang = math.atan2(v.y, v.x)
            el = math.atan2(v.z, math.hypot(v.x, v.y))
            f = 1.0 + lump * (math.sin(4 * ang + ph[0]) * 0.5 + math.sin(7 * ang + 2 * el + ph[1]) * 0.3
                              + math.sin(2 * el + ph[2]) * 0.3)
            # flatter underside: clumps sit on their branches
            if v.z < 0:
                v = Vector((v.x, v.y, v.z * 0.6))
            mb.verts[vi] = c + v * f
    return cc


def willow(mb, rng, height=9.0, at=(0, 0, 0), strands=110, length=0.6):
    o = Vector(at)
    H = height
    tr = H * 0.035
    trunk = _path(o, Vector((rng.uniform(-0.2, 0.2), 0, 1)), H * 0.6, 4, rng, bend=0.2, up=0.1)
    _tube(mb, trunk, tr, tr * 0.6, "Bark", 7)
    top = trunk[-1]
    tips = []
    for i in range(5):
        a = rng.uniform(0, math.tau)
        limb = _path(top, Vector((math.cos(a), math.sin(a), 1.4)), H * 0.35, 3, rng, bend=0.15)
        _tube(mb, limb, tr * 0.45, tr * 0.15, "Bark", 6)
        tips += limb[1:]
    for i in range(strands):
        p = rng.choice(tips) + Vector((rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6), rng.uniform(-0.2, 0.3)))
        L = H * length * rng.uniform(0.6, 1.1)
        pts = [p, p + Vector((rng.uniform(-0.3, 0.3), 0, 0.15)), p + Vector((rng.uniform(-0.4, 0.4), rng.uniform(-0.2, 0.2), -L * 0.5)),
               p + Vector((rng.uniform(-0.5, 0.5), rng.uniform(-0.2, 0.2), -L))]
        mb.tube([tuple(q) for q in pts], 0.022 * H / 9, "Willow", 4, radius_fn=lambda t: 1.0 - 0.6 * t)
        # leaves along the strand: small pale blades
        for j in range(5):
            t = (j + 1) / 6.0
            q = pts[2] + (pts[3] - pts[2]) * t if t > 0.5 else pts[1] + (pts[2] - pts[1]) * (t * 2)
            d = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), -1.6))
            blade(mb, q, d, H * 0.035, H * 0.008, "Willow", rng, droop=0.1, n=2)


def bamboo(mb, rng, height=8.0, stems=7, at=(0, 0, 0), radius=1.0, cam_dir=(0, 1, 0), leaves=6,
           lean=0.12):
    """Bamboo clump: jointed stems, leaf blades in fans of 3-5 at the upper nodes."""
    o = Vector(at)
    for s in range(stems):
        a = rng.uniform(0, math.tau)
        base = o + Vector((math.cos(a), math.sin(a), 0)) * rng.uniform(0, radius)
        H = height * rng.uniform(0.6, 1.1)
        d = Vector((rng.uniform(-lean, lean), rng.uniform(-lean, lean), 1.0)).normalized()
        r = 0.035 * height / 8.0 * rng.uniform(0.8, 1.2)
        nodes = int(6 + H / 1.2)
        prev = base
        for k in range(nodes):
            nxt = prev + d * (H / nodes)
            mb.cylinder(tuple(prev), tuple(nxt), r, r, "Bamboo", 7, caps=False)
            mb.cylinder(tuple(nxt - d * 0.03), tuple(nxt + d * 0.03), r * 1.18, r * 1.18, "Bamboo", 7)
            if k > nodes * 0.45 and rng.random() < 0.75:
                bamboo_leaves(mb, rng, nxt, H * 0.09, rng.randint(3, leaves))
            prev = nxt
            d = (d + Vector((rng.uniform(-0.02, 0.02), rng.uniform(-0.02, 0.02), 0))).normalized()


def blade(mb, base, direction, length, width, mat, rng, droop=0.25, n=4):
    """Pointed leaf blade (flat ribbon with a curved midrib, sharp tip)."""
    d = Vector(direction).normalized()
    side = d.cross(Vector((0, 0, 1)))
    if side.length < 1e-4:
        side = Vector((1, 0, 0))
    side.normalize()
    tw = Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), 1.0)).normalized()
    pts, ws = [], []
    for i in range(n + 1):
        t = i / n
        p = Vector(base) + d * length * t + Vector((0, 0, -droop * length * t * t))
        pts.append(p)
        ws.append(width * math.sin(math.pi * min(1.0, t * 1.15 + 0.08)) * (1.0 - t) ** 0.35)
    ids_l, ids_r = [], []
    for p, w in zip(pts, ws):
        s2 = side.lerp(tw, 0.35).normalized() * w * 0.5
        ids_l.append(mb.v(tuple(p - s2)))
        ids_r.append(mb.v(tuple(p + s2)))
    for i in range(n):
        mb.face((ids_l[i], ids_r[i], ids_r[i + 1], ids_l[i + 1]), mat)


def bamboo_leaves(mb, rng, at, length, n, mat="BambooLeaf"):
    a0 = rng.uniform(0, math.tau)
    for i in range(n):
        a = a0 + (i - n / 2) * 0.45 + rng.uniform(-0.15, 0.15)
        d = Vector((math.cos(a), math.sin(a), rng.uniform(-0.6, 0.2)))
        blade(mb, at, d, length * rng.uniform(0.8, 1.2), length * 0.16, mat, rng, droop=0.35)


def dead_tree(mb, rng, height=8.0, at=(0, 0, 0), depth=4, mat="DeadBark", spread=0.8):
    """Bare tree: forked limbs ending in crab-claw twigs (蟹爪)."""
    def grow(p, d, L, r, lvl):
        pts = _path(p, d, L, 3, rng, bend=0.25, up=0.05 if lvl < 2 else -0.05)
        _tube(mb, pts, r, r * 0.6, mat, 6 if lvl < 2 else 4)
        if lvl >= depth:
            return
        k = 2 if lvl > 0 else 3
        for j in range(k):
            a = rng.uniform(0, math.tau)
            nd = (d * 0.6 + Vector((math.cos(a) * spread, math.sin(a) * spread, rng.uniform(-0.1, 0.5)))).normalized()
            grow(pts[-1], nd, L * rng.uniform(0.55, 0.75), r * 0.6, lvl + 1)
    tr = height * 0.035
    grow(Vector(at), Vector((rng.uniform(-0.1, 0.1), 0, 1)), height * 0.45, tr, 0)


def plum(mb, rng, height=4.0, at=(0, 0, 0), depth=4, blossoms=60, red=0.3, blossom_r=None):
    """Gnarled plum in blossom (white / rouge flowers as tiny spheres)."""
    tips = []

    def grow(p, d, L, r, lvl):
        pts = _path(p, d, L, 3, rng, bend=0.35, up=0.08)
        _tube(mb, pts, r, r * 0.55, "Bark", 5)
        tips.extend(pts[1:])
        if lvl >= depth:
            return
        for j in range(2):
            a = rng.uniform(0, math.tau)
            nd = (d * 0.5 + Vector((math.cos(a), math.sin(a), rng.uniform(0.0, 0.7)))).normalized()
            grow(pts[-1], nd, L * rng.uniform(0.55, 0.75), r * 0.6, lvl + 1)
    grow(Vector(at), Vector((0.2, 0, 1)), height * 0.4, height * 0.03, 0)
    for i in range(blossoms):
        p = rng.choice(tips) + Vector((rng.uniform(-0.1, 0.1), rng.uniform(-0.1, 0.1), rng.uniform(-0.05, 0.1)))
        mb.sphere(tuple(p), blossom_r or height * 0.018, "BlossomRed" if rng.random() < red else "Blossom", 8, 5,
                  scale=(1.0, 1.0, 0.8))


def tuft(mb, rng, at, height=0.8, blades=9, mat="Grass", spread=0.35, width=0.035):
    """Grass / reed tuft: arching blades from one base."""
    o = Vector(at)
    for i in range(blades):
        a = rng.uniform(0, math.tau)
        d = Vector((math.cos(a) * spread, math.sin(a) * spread, 1.0))
        blade(mb, o, d, height * rng.uniform(0.6, 1.1), width * height, mat, rng, droop=0.25 + spread)
