"""Battle family: prop builders for the hex tiles (metres, +Z up, MeshBuilder).

Grass tufts, stones and boulders, gongbi trees (dotted-leaf broadleaf crowns built from lumpy
lobes, pines with flat needle pads), reeds, shrubs.  Material slots are the ``B_*`` names of
:mod:`ironart.battle_mats`.  UVs: blades and reeds carry MetreUV v = metres along the blade
(the materials grade along it); everything else is Smart-UV unwrapped for the atlas bake.
"""

import math

from mathutils import Matrix, Vector, noise

TAU = math.tau


def _ring_verts(mb, c, ex, ey, r, n, phase=0.0):
    return [mb.v(tuple(c + ex * (math.cos(phase + TAU * k / n) * r) + ey * (math.sin(phase + TAU * k / n) * r)))
            for k in range(n)]


def _frame(d):
    d = Vector(d).normalized()
    ref = Vector((0, 0, 1)) if abs(d.z) < 0.95 else Vector((1, 0, 0))
    ex = d.cross(ref).normalized()
    ey = d.cross(ex).normalized()
    return ex, ey


def blade(mb, root, direction, length, width, mat="B_Grass", bend=0.35, sides=3, levels=3):
    """One tapered blade (triangular section) from ``root`` curving along ``direction``; MetreUV
    v = 0..1 from the root to the tip (the gradient strip of the atlas)."""
    root = Vector(root)
    d = Vector(direction).normalized()
    side = d.cross(Vector((0, 0, 1)))
    if side.length < 1e-4:
        side = Vector((1, 0, 0))
    side.normalize()
    down = d.cross(side).normalized()
    pts = []
    for k in range(levels + 1):
        t = k / levels
        p = root + d * (length * t) + down * (bend * length * t * t)
        pts.append((p, t))
    rings = []
    for k, (p, t) in enumerate(pts[:-1]):
        a = pts[min(k + 1, len(pts) - 1)][0] - pts[max(k - 1, 0)][0]
        ex, ey = _frame(a)
        r = width * 0.5 * (1.0 - 0.85 * t)
        ring = _ring_verts(mb, p, ex, ey, r, sides)
        rings.append((ring, t))
    tip = mb.v(tuple(pts[-1][0]))
    for k in range(len(rings) - 1):
        (ra, ta), (rb, tb) = rings[k], rings[k + 1]
        for i in range(sides):
            j = (i + 1) % sides
            mb.face((ra[i], ra[j], rb[j], rb[i]), mat,
                    [(i / sides, ta), ((i + 1) / sides, ta), ((i + 1) / sides, tb), (i / sides, tb)], smooth=True)
    ra, ta = rings[-1]
    for i in range(sides):
        j = (i + 1) % sides
        mb.face((ra[i], ra[j], tip), mat, [(i / sides, ta), ((i + 1) / sides, ta), ((i + 0.5) / sides, 1.0)],
                smooth=True)


def ribbon(mb, root, direction, length, width, mat="B_Grass", bend=0.4, levels=4, twist=0.0):
    """A flat leaf blade (two-sided ribbon with a slight V fold), tapered to a point, arching
    over; MetreUV v = 0..1 along the blade."""
    root = Vector(root)
    d = Vector(direction).normalized()
    side = d.cross(Vector((0, 0, 1)))
    if side.length < 1e-4:
        side = Vector((1, 0, 0))
    side.normalize()
    down = d.cross(side).normalized()
    rows = []
    for k in range(levels + 1):
        t = k / levels
        p = root + d * (length * t) + down * (bend * length * t * t)
        w = width * 0.5 * (math.sin(math.pi * min(1.0, 0.15 + t * 0.95)) if t < 1 else 0.0)
        sd = (side * math.cos(twist * t) + down * math.sin(twist * t))
        fold = -down * w * 0.35
        rows.append((mb.v(tuple(p - sd * w + fold)), mb.v(tuple(p + down * 0.0)), mb.v(tuple(p + sd * w + fold)), t))
    for k in range(levels):
        a, b = rows[k], rows[k + 1]
        for (i0, i1, u0, u1) in ((0, 1, 0.0, 0.5), (1, 2, 0.5, 1.0)):
            q = (a[i0], a[i1], b[i1], b[i0])
            uv = [(u0, a[3]), (u1, a[3]), (u1, b[3]), (u0, b[3])]
            mb.face(q, mat, uv, smooth=True)
            mb.face(q[::-1], mat, uv[::-1], smooth=True)


def grass_tuft(mb, rng, at, height=0.32, n=6, spread=0.06, mat="B_Grass"):
    """A clump of broad leaf blades fanning out and arching over from one root (orchid-like
    gongbi grass)."""
    at = Vector(at)
    a0 = rng.uniform(0, TAU)
    for i in range(n):
        a = a0 + TAU * i / n + rng.uniform(-0.35, 0.35)
        lean = math.radians(rng.uniform(12, 48))
        d = Vector((math.cos(a) * math.sin(lean), math.sin(a) * math.sin(lean), math.cos(lean)))
        r0 = at + Vector((math.cos(a) * rng.uniform(0, spread) * 0.5, math.sin(a) * rng.uniform(0, spread) * 0.5, -0.02))
        L = height * rng.uniform(0.6, 1.1)
        ribbon(mb, r0, d, L, rng.uniform(0.05, 0.075), mat, bend=rng.uniform(0.25, 0.55), twist=rng.uniform(-0.6, 0.6))


def lumpy(mb, center, size, mat, rng, seg=14, rings=9, rough=0.22, flat_bottom=0.0, freq=1.6, rot=0.0):
    """Lumpy ellipsoid (stones, canopy lobes, pads).  ``flat_bottom``: squash the lower half
    (0 = round, 1 = flat)."""
    sx, sy, sz = size
    off = Vector((rng.uniform(-50, 50), rng.uniform(-50, 50), rng.uniform(-50, 50)))

    def disp(v):
        n = noise.noise(v * freq + off) * 0.6 + noise.noise(v * freq * 2.3 + off) * 0.3
        return 1.0 + rough * n

    s = mb.n
    mb.sphere((0, 0, 0), 1.0, mat, seg, rings, displace=disp)
    for i in range(s, mb.n):
        v = mb.verts[i]
        z = v.z
        if z < 0 and flat_bottom:
            z = z * (1.0 - flat_bottom)
        mb.verts[i] = Vector((v.x * sx, v.y * sy, z * sz))
    mb.transform(s, Matrix.Translation(Vector(center)) @ Matrix.Rotation(rot, 4, "Z"))
    return s


def stone(mb, rng, at, size, mat="B_Rock", sink=0.35):
    """A boulder sunk into the ground by ``sink`` of its height."""
    sx = size * rng.uniform(0.8, 1.25)
    sy = size * rng.uniform(0.7, 1.1)
    sz = size * rng.uniform(0.45, 0.8)
    c = Vector(at) + Vector((0, 0, sz * (1.0 - 2.0 * sink) * 0.9))
    lumpy(mb, c, (sx, sy, sz), mat, rng, seg=12, rings=8, rough=0.28, flat_bottom=0.3, freq=1.3 / max(size, 0.05),
          rot=rng.uniform(0, TAU))


def facet_rock(mb, rng, at, size, mat="B_Rock", flat=0.6, n=18, sink=0.3, elong=(0.8, 1.25)):
    """Angular boulder: the convex hull of jittered points on a squashed ellipsoid - flat facets
    and sharp creases, like a rock drawn with axe-cut strokes (斧劈皴)."""
    import bmesh
    sx = size * rng.uniform(*elong)
    sy = size * rng.uniform(0.75, 1.05)
    sz = size * flat * rng.uniform(0.8, 1.2)
    bm = bmesh.new()
    for i in range(n):
        u = rng.uniform(-1, 1)
        a = rng.uniform(0, TAU)
        r = math.sqrt(max(0.0, 1 - u * u))
        k = rng.uniform(0.8, 1.05)
        z = u * k
        if z < 0:
            z *= 0.35
        bm.verts.new((r * math.cos(a) * k * sx, r * math.sin(a) * k * sy, z * sz))
    bmesh.ops.convex_hull(bm, input=bm.verts)
    bm.verts.ensure_lookup_table()
    rot = Matrix.Rotation(rng.uniform(0, TAU), 4, "Z") @ Matrix.Rotation(rng.uniform(-0.25, 0.25), 4, "X")
    base = Vector(at) + Vector((0, 0, -sz * sink))
    ids = {}
    for v in bm.verts:
        ids[v.index] = mb.v(tuple(base + (rot @ v.co)))
    for f in bm.faces:
        mb.face([ids[v.index] for v in f.verts], mat, smooth=False)
    bm.free()


def trunk_path(rng, base, height, lean=0.12, wiggle=0.08, n=6):
    a = rng.uniform(0, TAU)
    pts = []
    for k in range(n + 1):
        t = k / n
        off = Vector((math.cos(a), math.sin(a), 0)) * lean * height * t * t
        wob = Vector((math.sin(t * 5.1 + a) * wiggle, math.cos(t * 4.3 + a) * wiggle, 0)) * t
        pts.append(Vector(base) + Vector((0, 0, height * t)) + off + wob)
    return pts


def limb(mb, pts, r0, r1, mat="B_Trunk", sides=7):
    """Tapered tube along ``pts`` (root flare at the first point)."""
    n = len(pts)
    mb.tube([tuple(p) for p in pts], r0, mat, sides, caps=True, smooth=True,
            radius_fn=lambda t: (1.0 - t) + (r1 / r0) * t)


def _branch(rng, p0, direction, length, n=4, droop=0.0, curl=0.25):
    pts = [Vector(p0)]
    d = Vector(direction).normalized()
    for k in range(n):
        ax = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.3, 0.3)))
        if ax.length > 1e-3:
            d = (Matrix.Rotation(rng.uniform(-curl, curl), 3, ax.normalized()) @ d).normalized()
        d.z -= droop / n
        d.normalize()
        pts.append(pts[-1] + d * (length / n))
    return pts


def foliage_cluster(mb, rng, c, size, mat, n=4):
    """A painted foliage mass: one flattened core blob and 3-4 smaller scalloping blobs round
    its rim (an irregular, cloud-like outline), flat underside."""
    c = Vector(c)
    lumpy(mb, c, (size * 0.8, size * 0.72, size * 0.52), mat, rng, seg=12, rings=8, rough=0.18, flat_bottom=0.6,
          freq=2.0 / size, rot=rng.uniform(0, TAU))
    a0 = rng.uniform(0, TAU)
    for k in range(n):
        a = a0 + TAU * k / n + rng.uniform(-0.4, 0.4)
        r = size * rng.uniform(0.5, 0.62)
        s = size * rng.uniform(0.38, 0.5)
        q = c + Vector((math.cos(a) * r, math.sin(a) * r, rng.uniform(-0.12, 0.18) * size))
        lumpy(mb, q, (s, s * rng.uniform(0.8, 1.0), s * 0.68), mat, rng, seg=10, rings=7, rough=0.2,
              flat_bottom=0.6, freq=2.2 / s, rot=rng.uniform(0, TAU))


def broadleaf(mb, rng, at, height=3.8, crown=1.0, canopy="B_Canopy", clusters=9, trunk="B_Trunk"):
    """Gongbi dotted-leaf tree (点叶树): an S-curved trunk forking into two or three limbs that
    fork again; each twig tip carries a flattened foliage cluster, the clusters make a broad,
    open dome with the branch structure showing between them."""
    at = Vector(at)
    hf = height * rng.uniform(0.3, 0.36)
    tp = trunk_path(rng, at + Vector((0, 0, -0.12)), hf + 0.12, lean=0.12, wiggle=0.06, n=6)
    r0 = 0.10 * height / 3.8
    limb(mb, tp, r0, r0 * 0.72, trunk, sides=8)
    top = tp[-1]
    crown_c = Vector((top.x, top.y, at.z + height - crown * 0.62))
    tips = []
    nl = rng.randint(2, 3)
    a0 = rng.uniform(0, TAU)
    for i in range(nl):
        a = a0 + TAU * i / nl + rng.uniform(-0.4, 0.4)
        tgt = crown_c + Vector((math.cos(a) * crown * 0.55, math.sin(a) * crown * 0.55, rng.uniform(-0.1, 0.2)))
        d = (tgt - top).normalized()
        br = _branch(rng, top, d, (tgt - top).length, n=3, curl=0.2)
        limb(mb, br, r0 * 0.62, r0 * 0.35, trunk, sides=7)
        tips.append(br[-1])
        for j in range(2):
            b = a + rng.uniform(-1.1, 1.1)
            d2 = Vector((math.cos(b), math.sin(b), rng.uniform(0.3, 0.9))).normalized()
            p = br[rng.randint(1, len(br) - 1)]
            tw = _branch(rng, p, d2, crown * rng.uniform(0.45, 0.7), n=3, curl=0.3)
            limb(mb, tw, r0 * 0.3, r0 * 0.12, trunk, sides=5)
            tips.append(tw[-1])
    tips.append(crown_c + Vector((0, 0, crown * 0.25)))
    # foliage clusters at the twig tips plus fillers, flattened, flat-bottomed
    cl = list(tips)
    while len(cl) < clusters:
        a = rng.uniform(0, TAU)
        rr = crown * rng.uniform(0.2, 0.75)
        cl.append(crown_c + Vector((math.cos(a) * rr, math.sin(a) * rr, rng.uniform(-0.15, 0.35) * crown)))
    for c in cl[:clusters]:
        size = crown * rng.uniform(0.44, 0.58)
        foliage_cluster(mb, rng, c + Vector((0, 0, size * 0.15)), size, canopy)


def pine(mb, rng, at, height=4.0, mat_pad="B_Pine", tiers=6, bark="B_PineBark", first=0.32, lean=0.3):
    """Gongbi pine (松): a thick, strongly crooked trunk with scaly bark; near-horizontal,
    drooping branches in tiers, each holding one or two flat needle pads (pad centres in the
    ``pad_x`` / ``pad_y`` attributes for the radiating needle strokes); a small crown pad."""
    at = Vector(at)
    tp = trunk_path(rng, at + Vector((0, 0, -0.12)), height * 0.9, lean=lean, wiggle=0.14, n=9)
    # small pines keep the chunky proportions of a large one (bonsai-like cliff pines), so the
    # trunk, the branches and the pads do not thin out into a stalk
    ks = max(1.0, 2.9 / height)
    r0 = 0.12 * height * ks / 4.0
    limb(mb, tp, r0, r0 * 0.3, bark, sides=8)

    def pad(c, rx, rz):
        """A needle pad: a flat main lump with two smaller lobes overlapping its rim, so the
        silhouette is a scalloped fan rather than a disc; all lobes share the pad centre so the
        needle strokes radiate across them as one cluster."""
        s0 = mb.n
        lumpy(mb, c, (rx * 0.82, rx * 0.82 * rng.uniform(0.7, 0.9), rz), mat_pad, rng, seg=16, rings=7, rough=0.16,
              flat_bottom=0.7, freq=2.4 / rx, rot=rng.uniform(0, TAU))
        b0 = rng.uniform(0, TAU)
        for k in range(2):
            b = b0 + k * rng.uniform(2.0, 2.6)
            q = c + Vector((math.cos(b) * rx * 0.5, math.sin(b) * rx * 0.5, rng.uniform(-0.3, 0.5) * rz))
            s = rx * rng.uniform(0.5, 0.62)
            lumpy(mb, q, (s, s * rng.uniform(0.75, 0.95), rz * 0.85), mat_pad, rng, seg=12, rings=6, rough=0.18,
                  flat_bottom=0.7, freq=2.6 / s, rot=rng.uniform(0, TAU))
        mb.set_attr("pad_x", s0, mb.n, c.x)
        mb.set_attr("pad_y", s0, mb.n, c.y)

    fs = [first + (0.87 - first) * (k + rng.uniform(0.0, 0.6)) / tiers for k in range(tiers)]
    a = rng.uniform(0, TAU)
    for k, f in enumerate(fs):
        p = tp[min(len(tp) - 1, int(round(f * (len(tp) - 1))))]
        a += rng.uniform(1.6, 2.8)
        L = height * ks ** 0.5 * rng.uniform(0.2, 0.3) * (1.15 - f * 0.55)
        d = Vector((math.cos(a), math.sin(a), rng.uniform(0.0, 0.25)))
        br = _branch(rng, p, d, L, n=3, droop=0.25, curl=0.25)
        limb(mb, br, r0 * 0.38, r0 * 0.14, bark, sides=6)
        rx = height * ks * rng.uniform(0.11, 0.15) * (1.2 - f * 0.45)
        pad(br[-1] + Vector((0, 0, 0.05)), rx, height * ks * 0.035)
        if rng.random() < 0.6:
            q = br[len(br) // 2] + Vector((0, 0, 0.04))
            pad(q + Vector((math.cos(a + 1.3) * rx * 0.6, math.sin(a + 1.3) * rx * 0.6, 0.02)), rx * 0.65,
                height * ks * 0.028)
    top = tp[-1]
    pad(top + Vector((0, 0, 0.05)), height * ks * 0.12, height * ks * 0.04)


def shrub(mb, rng, at, size=0.45, canopy="B_Canopy"):
    at = Vector(at)
    for i in range(3):
        a = rng.uniform(0, TAU)
        c = at + Vector((math.cos(a) * size * 0.4, math.sin(a) * size * 0.4, size * rng.uniform(0.35, 0.6)))
        s = size * rng.uniform(0.5, 0.7)
        lumpy(mb, c, (s, s, s * 0.75), canopy, rng, seg=10, rings=7, rough=0.22, flat_bottom=0.5, freq=2.0 / s)


def reeds(mb, rng, at, n=9, height=0.7, mat="B_Reed"):
    at = Vector(at)
    for i in range(n):
        a = rng.uniform(0, TAU)
        lean = math.radians(rng.uniform(0, 18))
        d = Vector((math.cos(a) * math.sin(lean), math.sin(a) * math.sin(lean), math.cos(lean)))
        r0 = at + Vector((rng.uniform(-0.12, 0.12), rng.uniform(-0.12, 0.12), -0.05))
        blade(mb, r0, d, height * rng.uniform(0.6, 1.1), 0.02, mat, bend=0.1)
