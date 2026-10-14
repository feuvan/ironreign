"""Illustrated Scenes: vegetation prototypes + geometry-nodes instancing.

Prototypes are built with :class:`ironart.geometry.MeshBuilder` (origin at the base, metres):
leafy crowns are clusters of small leaf polygons around a darker core (broken, light-catching
silhouettes instead of blobs), Chinese pines carry flat needle pads on crooked branches.
:func:`instance` scatters any list of prototypes over points with per-point kind / rotation /
scale through a geometry-nodes *Instance on Points* modifier, so tens of thousands of trees cost
one small mesh each.  Foliage materials vary per instance (Object Info random) and are fogged.
"""

import math
import random

from mathutils import Matrix, Vector

TAU = math.tau


# =============================================================================================
# materials
# =============================================================================================
def foliage_material(name="Leaves", colors=("#3E5A2C", "#6E8A3C"), translucency=0.25,
                     roughness=0.7, vary=0.5, sheen=0.2, autumn=None, core=False):
    """Leaves: per-instance hue/value variation (Object Info random), soft translucency."""
    from .materials import new
    from .scenes_sky import G, lin4
    from .scenes_terrain import _fin, noise
    mat, nb, created = new(name)
    if not created:
        return mat
    b = G(nb.tree)
    oi = nb.node("ShaderNodeObjectInfo")
    rnd = oi.outputs["Random"]
    P = nb.node("ShaderNodeNewGeometry").outputs["Position"]
    n = noise(nb, P, 0.35, 3, 0.5)
    t = b.math("ADD", b.math("MULTIPLY", rnd, vary), b.math("MULTIPLY", n, 1.0 - vary))
    col = b.mix(lin4(colors[0]), lin4(colors[1]), b.smooth(t, 0.2, 0.85))
    if autumn:
        col = b.mix(col, lin4(autumn), b.math("MULTIPLY", b.smooth(rnd, 0.6, 0.9), 0.8))
    if core:
        col = b.cmul(col, 0.55)
    p = b.principled(Base_Color=col, Roughness=roughness, Specular_IOR_Level=0.25,
                     Sheen_Weight=sheen, Sheen_Roughness=0.4)
    sh = p.outputs[0]
    if translucency > 0:
        tr = nb.node("ShaderNodeBsdfTranslucent")
        b.link(b.cmul(col, 1.3), tr.inputs["Color"])
        mx = nb.node("ShaderNodeMixShader")
        mx.inputs[0].default_value = translucency
        b.link(p.outputs[0], mx.inputs[1])
        b.link(tr.outputs[0], mx.inputs[2])
        sh = mx.outputs[0]
    return _fin(mat, nb, sh)


def bark_material(name="Bark", color=("#3A2C22", "#5E4A3A"), scale=6.0):
    from .materials import new
    from .scenes_sky import G, lin4
    from .scenes_terrain import _fin, noise
    mat, nb, created = new(name)
    if not created:
        return mat
    b = G(nb.tree)
    P = nb.node("ShaderNodeNewGeometry").outputs["Position"]
    n = noise(nb, b.vmath("MULTIPLY", P, b.vec((scale * 3, scale * 3, scale * 0.6))).outputs[0], 1.0, 4, 0.6)
    col = b.mix(lin4(color[0]), lin4(color[1]), b.smooth(n, 0.3, 0.7))
    p = b.principled(Base_Color=col, Roughness=0.9, Specular_IOR_Level=0.2, Normal=b.bump(n, 0.5, 0.05))
    return _fin(mat, nb, p.outputs[0])


# =============================================================================================
# prototype builders (MeshBuilder, origin at base)
# =============================================================================================
def _leaf_cluster(mb, center, radius, rng, mat, n_leaves=40, leaf=0.32, flat=1.0, up_bias=0.25,
                  core_mat=None, core=0.7):
    """A clump of small leaf polygons on a lumpy ellipsoid shell (+ a darker core blob)."""
    cx, cy, cz = center
    if core_mat:
        from .geometry import _lumpy
        mb.sphere((cx, cy, cz), radius * core, core_mat, 8, 5, scale=(1, 1, flat),
                  displace=_lumpy(rng, 0.22, 2.5))
    for _ in range(n_leaves):
        # point on the upper-biased shell
        u = rng.uniform(-1.0 + up_bias, 1.0)
        a = rng.uniform(0, TAU)
        s = math.sqrt(max(0.0, 1 - u * u))
        nrm = Vector((s * math.cos(a), s * math.sin(a), u))
        rr = radius * rng.uniform(0.75, 1.05)
        p = Vector((cx, cy, cz)) + Vector((nrm.x * rr, nrm.y * rr, nrm.z * rr * flat))
        # leaf plane roughly tangent, tilted randomly
        t1 = nrm.cross(Vector((0, 0, 1)))
        if t1.length < 1e-3:
            t1 = Vector((1, 0, 0))
        t1.normalize()
        t2 = nrm.cross(t1).normalized()
        ang = rng.uniform(0, TAU)
        ax = (t1 * math.cos(ang) + t2 * math.sin(ang))
        ay = nrm.cross(ax).normalized()
        tilt = rng.uniform(-0.6, 0.6)
        ay = (ay * math.cos(tilt) + nrm * math.sin(tilt)).normalized()
        L = leaf * rng.uniform(0.7, 1.3)
        W = L * rng.uniform(0.4, 0.6)
        pts = [p - ax * L * 0.5, p - ay * W * 0.5, p + ax * L * 0.5, p + ay * W * 0.5]
        idx = [mb.v(tuple(q)) for q in pts]
        mb.face(idx, mat, smooth=False)


def broadleaf(mb, rng, height=12.0, crown=0.45, mat="Leaves", core="LeavesCore", bark="Bark",
              clumps=None, leaves=40, leaf=0.45, lean=0.08):
    """Deciduous tree ~``height`` m: bent trunk, a few limbs, leaf-polygon clumps."""
    trunk_h = height * rng.uniform(0.38, 0.5)
    lean_v = Vector((rng.uniform(-lean, lean), rng.uniform(-lean, lean), 1.0)).normalized()
    pts = []
    for i in range(6):
        t = i / 5
        off = Vector((math.sin(t * 2.5 + rng.uniform(0, 3)) * 0.04 * height, 0, 0))
        pts.append(lean_v * trunk_h * t + off)
    r0 = height * 0.03
    mb.tube([tuple(p) for p in pts], r0, bark, 7, caps=False, radius_fn=lambda t: 1.0 - 0.45 * t)
    top = pts[-1]
    cr = height * crown
    ccz = top.z + cr * 0.55
    n = clumps or rng.randint(7, 11)
    for k in range(n):
        a = TAU * k / n + rng.uniform(-0.3, 0.3)
        d = cr * rng.uniform(0.35, 0.75)
        z = ccz + rng.uniform(-0.35, 0.45) * cr
        c = Vector((top.x + math.cos(a) * d, top.y + math.sin(a) * d, z))
        # limb from trunk top to clump
        mid = (top + c) * 0.5 + Vector((0, 0, cr * 0.1))
        mb.tube([tuple(top), tuple(mid), tuple(c)], r0 * 0.45, bark, 5, caps=False,
                radius_fn=lambda t: 1.0 - 0.6 * t)
        _leaf_cluster(mb, tuple(c), cr * rng.uniform(0.42, 0.6), rng, mat, leaves, leaf,
                      flat=0.8, core_mat=core)
    _leaf_cluster(mb, (top.x, top.y, ccz + cr * 0.35), cr * 0.55, rng, mat, leaves, leaf,
                  flat=0.75, core_mat=core)


def chinese_pine(mb, rng, height=14.0, mat="Needles", core="NeedlesCore", bark="Bark",
                 pads=None, leaves=60, leaf=0.7):
    """Huangshan-style pine: crooked trunk, layered horizontal branches with flat needle pads."""
    pts = []
    x = y = 0.0
    dx, dy = rng.uniform(-1, 1), rng.uniform(-1, 1)
    for i in range(8):
        t = i / 7
        x += dx * height * 0.025 * math.sin(t * 3.0 + rng.uniform(0, 1))
        y += dy * height * 0.02 * math.cos(t * 2.0)
        pts.append(Vector((x, y, height * 0.85 * t)))
    r0 = height * 0.028
    mb.tube([tuple(p) for p in pts], r0, bark, 7, caps=False, radius_fn=lambda t: 1.0 - 0.6 * t)
    n = pads or rng.randint(5, 8)
    for k in range(n):
        t = 0.35 + 0.65 * k / max(1, n - 1)
        base = pts[min(7, int(t * 7))]
        a = rng.uniform(0, TAU)
        reach = height * (0.42 * (1 - t) + 0.12) * rng.uniform(0.8, 1.2)
        end = base + Vector((math.cos(a) * reach, math.sin(a) * reach, rng.uniform(-0.05, 0.1) * height))
        mid = (base + end) * 0.5 + Vector((0, 0, height * 0.04))
        mb.tube([tuple(base), tuple(mid), tuple(end)], r0 * 0.35, bark, 5, caps=False,
                radius_fn=lambda t: 1.0 - 0.6 * t)
        pr = height * rng.uniform(0.2, 0.27) * (1.15 - 0.35 * t)
        # a pad = 2-3 overlapping flat clumps along the branch end
        for j in range(3):
            off = Vector((math.cos(a + 1.5 * (j - 1)) * pr * 0.45, math.sin(a + 1.5 * (j - 1)) * pr * 0.45,
                          pr * 0.08 * j))
            _leaf_cluster(mb, tuple(end + off + Vector((0, 0, pr * 0.12))), pr * rng.uniform(0.6, 0.8),
                          rng, mat, leaves, leaf, flat=0.3, up_bias=0.45, core_mat=core, core=0.8)
    tip = pts[-1]
    for j in range(2):
        _leaf_cluster(mb, tuple(tip + Vector((0.3 * j, 0, height * 0.06))), height * 0.17, rng, mat,
                      leaves, leaf, flat=0.38, up_bias=0.45, core_mat=core, core=0.8)


def fir(mb, rng, height=16.0, mat="Needles", core="NeedlesCore", bark="Bark", tiers=8,
        width=0.24, leaves=26, leaf=0.6):
    """Natural conifer: trunk + whorls of drooping needle clumps narrowing to a spire."""
    mb.cylinder((0, 0, 0), (0, 0, height * 0.95), height * 0.02, height * 0.006, bark, 6)
    for t in range(tiers):
        f = t / (tiers - 1)
        z0 = height * (0.16 + 0.74 * f)
        r = height * width * (1.0 - 0.82 * f) * rng.uniform(0.85, 1.1)
        n = max(3, int(7 - 4 * f))
        for k in range(n):
            a = TAU * k / n + rng.uniform(-0.3, 0.3) + t * 0.7
            d = r * rng.uniform(0.55, 0.85)
            c = (math.cos(a) * d, math.sin(a) * d, z0 - r * 0.25)
            _leaf_cluster(mb, c, r * rng.uniform(0.5, 0.65), rng, mat, leaves, leaf * (1 - 0.4 * f),
                          flat=0.55, up_bias=0.2, core_mat=core, core=0.8)
    _leaf_cluster(mb, (0, 0, height * 0.97), height * 0.05, rng, mat, 12, leaf * 0.5, flat=1.6,
                  core_mat=core)


def bamboo(mb, rng, height=9.0, stems=9, mat="Bamboo", leaf_mat="BambooLeaves", radius=1.2):
    for i in range(stems):
        a = rng.uniform(0, TAU)
        d = rng.uniform(0, radius)
        b0 = Vector((math.cos(a) * d, math.sin(a) * d, 0))
        lean = Vector((rng.uniform(-0.12, 0.12), rng.uniform(-0.12, 0.12), 1.0)).normalized()
        h = height * rng.uniform(0.7, 1.05)
        pts = [b0 + lean * h * t + Vector((0, 0, 0)) * t for t in (0, 0.33, 0.66, 1.0)]
        pts[-1] += Vector((lean.x, lean.y, 0)) * h * 0.15
        mb.tube([tuple(p) for p in pts], 0.05 * height / 9, mat, 6, caps=False)
        for k in range(6):
            c = b0 + lean * h * (0.5 + 0.09 * k) + Vector((rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), 0))
            _leaf_cluster(mb, tuple(c), h * 0.11, rng, leaf_mat, 26, h * 0.045, flat=0.7, up_bias=-0.3)


def dead_tree(mb, rng, height=9.0, bark="BarkDead", depth=4):
    """Bare branching tree (drought / plague)."""
    def branch(p, d, length, r, lvl):
        end = p + d * length
        mid = (p + end) * 0.5 + Vector((rng.uniform(-0.1, 0.1), rng.uniform(-0.1, 0.1), 0)) * length
        mb.tube([tuple(p), tuple(mid), tuple(end)], r, bark, 5, caps=False,
                radius_fn=lambda t: 1.0 - 0.5 * t)
        if lvl >= depth:
            return
        for _ in range(rng.randint(2, 3)):
            nd = (d + Vector((rng.uniform(-0.9, 0.9), rng.uniform(-0.9, 0.9), rng.uniform(-0.1, 0.5)))).normalized()
            branch(end, nd, length * rng.uniform(0.55, 0.75), r * 0.55, lvl + 1)
    branch(Vector((0, 0, 0)), Vector((0, 0, 1)), height * 0.4, height * 0.045, 0)


def bush(mb, rng, size=1.5, mat="Leaves", core="LeavesCore", leaves=30, leaf=0.25):
    for k in range(rng.randint(3, 5)):
        a = rng.uniform(0, TAU)
        d = size * rng.uniform(0.1, 0.45)
        _leaf_cluster(mb, (math.cos(a) * d, math.sin(a) * d, size * rng.uniform(0.35, 0.6)),
                      size * rng.uniform(0.35, 0.55), rng, mat, leaves, leaf, flat=0.7,
                      core_mat=core)


def grass_tuft(mb, rng, height=0.6, blades=14, mat="Grass", spread=0.25):
    for _ in range(blades):
        a = rng.uniform(0, TAU)
        d = rng.uniform(0, spread)
        b0 = Vector((math.cos(a) * d, math.sin(a) * d, 0))
        lean = Vector((math.cos(a) * rng.uniform(0.1, 0.5), math.sin(a) * rng.uniform(0.1, 0.5), 1.0)).normalized()
        h = height * rng.uniform(0.6, 1.1)
        side = Vector((-lean.y, lean.x, 0)).normalized() if abs(lean.z) < 0.999 else Vector((1, 0, 0))
        w = height * 0.035
        tip = b0 + lean * h + Vector((lean.x, lean.y, 0)) * h * 0.3
        i0 = mb.v(tuple(b0 - side * w))
        i1 = mb.v(tuple(b0 + side * w))
        i2 = mb.v(tuple(b0 + lean * h * 0.5 + side * w * 0.6))
        i3 = mb.v(tuple(b0 + lean * h * 0.5 - side * w * 0.6))
        i4 = mb.v(tuple(tip))
        mb.face((i0, i1, i2, i3), mat, smooth=True)
        mb.face((i3, i2, i4), mat, smooth=True)


# =============================================================================================
# instancing
# =============================================================================================
_proto_count = [0]


def prototypes(builders, materials, name="Protos"):
    """Build prototype objects into an unlinked collection.  ``builders`` = list of callables
    ``fn(mb)``; returns the collection (children named P000.. so the pick index is the order)."""
    import bpy
    from .geometry import MeshBuilder
    col = bpy.data.collections.new(name + "_%d" % _proto_count[0])
    _proto_count[0] += 1
    for i, fn in enumerate(builders):
        mb = MeshBuilder()
        fn(mb)
        o = mb.build("P%03d_%s" % (i, name), materials, col=col, auto_smooth_deg=None)
    return col


def _named(ng, name, dtype):
    na = ng.nodes.new("GeometryNodeInputNamedAttribute")
    na.data_type = dtype
    na.inputs["Name"].default_value = name
    out = [o for o in na.outputs if o.enabled and o.name == "Attribute"][0]
    return out


def instance(name, points, proto_col, col=None, hide_shadow=False):
    """Instance ``proto_col`` children on ``points`` = list of (x, y, z, rot_z, scale, kind)
    (rot_z radians, scale uniform or (sx, sy, sz), kind = child index).  Returns the object."""
    import bpy
    import numpy as np
    n = len(points)
    me = bpy.data.meshes.new(name)
    me.vertices.add(n)
    co = np.array([(p[0], p[1], p[2]) for p in points], np.float32).reshape(-1)
    me.vertices.foreach_set("co", co)
    rot = np.zeros((n, 3), np.float32)
    scl = np.ones((n, 3), np.float32)
    kind = np.zeros(n, np.int32)
    for i, p in enumerate(points):
        r = p[3]
        if isinstance(r, (tuple, list)):
            rot[i] = r
        else:
            rot[i, 2] = r
        s = p[4]
        scl[i] = s if isinstance(s, (tuple, list)) else (s, s, s)
        kind[i] = p[5]
    a = me.attributes.new("rot", "FLOAT_VECTOR", "POINT")
    a.data.foreach_set("vector", rot.reshape(-1))
    a = me.attributes.new("scl", "FLOAT_VECTOR", "POINT")
    a.data.foreach_set("vector", scl.reshape(-1))
    a = me.attributes.new("kind", "INT", "POINT")
    a.data.foreach_set("value", kind)
    me.update()
    obj = bpy.data.objects.new(name, me)
    (col or bpy.context.scene.collection).objects.link(obj)
    ng = bpy.data.node_groups.new("IR_Inst_" + name, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gi = ng.nodes.new("NodeGroupInput")
    go = ng.nodes.new("NodeGroupOutput")
    iop = ng.nodes.new("GeometryNodeInstanceOnPoints")
    ci = ng.nodes.new("GeometryNodeCollectionInfo")
    ci.transform_space = "ORIGINAL"
    ci.inputs["Collection"].default_value = proto_col
    ci.inputs["Separate Children"].default_value = True
    ci.inputs["Reset Children"].default_value = True
    L = ng.links
    L.new(gi.outputs[0], iop.inputs["Points"])
    L.new(ci.outputs[0], iop.inputs["Instance"])
    iop.inputs["Pick Instance"].default_value = True
    L.new(_named(ng, "kind", "INT"), iop.inputs["Instance Index"])
    L.new(_named(ng, "rot", "FLOAT_VECTOR"), iop.inputs["Rotation"])
    L.new(_named(ng, "scl", "FLOAT_VECTOR"), iop.inputs["Scale"])
    L.new(iop.outputs[0], go.inputs[0])
    mod = obj.modifiers.new("Instances", "NODES")
    mod.node_group = ng
    if hide_shadow:
        obj.visible_shadow = False
    return obj


def scatter_on(field, n, rng, x_range, y_range, kinds, scale=(0.8, 1.2), min_nz=0.0, max_nz=1.0,
               zmin=-1e9, zmax=1e9, mask=None, density=None, sink=0.15, tries=8):
    """Random points on a :class:`scenes_terrain.Field`.  ``kinds`` = list of (kind, weight)
    or an int count; ``mask(x, y)`` -> bool keeps a point; ``density(x, y)`` -> 0..1 thins.
    Returns [(x, y, z, rot, scale, kind), ...]."""
    if isinstance(kinds, int):
        kinds = [(k, 1.0) for k in range(kinds)]
    tot = sum(w for _, w in kinds)
    pts = []
    for _ in range(n):
        for _t in range(tries):
            x = rng.uniform(*x_range)
            y = rng.uniform(*y_range)
            if mask is not None and not mask(x, y):
                continue
            if density is not None and rng.random() > density(x, y):
                continue
            nz = field.nz_at(x, y)
            if nz < min_nz or nz > max_nz:
                continue
            z = field.z(x, y)
            if z < zmin or z > zmax:
                continue
            r = rng.random() * tot
            kind = kinds[-1][0]
            for k, w in kinds:
                r -= w
                if r <= 0:
                    kind = k
                    break
            s = rng.uniform(*scale)
            pts.append((x, y, z - sink * s, rng.uniform(0, TAU), s, kind))
            break
    return pts
