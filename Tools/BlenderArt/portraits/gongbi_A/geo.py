"""Geometry helpers for the gongbi bust: numpy meshes, decal projection, brush ribbons, strands.

Everything is built in the *frontal head frame* (metres, +Z up, the face looks toward -Y) with
identity object transforms; the whole bust is parented to one root empty that carries the pose.
"""

import math

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


# ------------------------------------------------------------------------------------- objects
def collection(name):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
    return c


def mesh_obj(name, verts, faces, col, mat=None, smooth=True, uvs=None, parent=None):
    """verts (N,3); faces list of index tuples or (F,k) array; uvs (N,2) per-vertex optional."""
    verts = np.asarray(verts, np.float64)
    if isinstance(faces, np.ndarray):
        faces = [tuple(int(i) for i in f) for f in faces]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts.tolist(), [], faces)
    if uvs is not None:
        uvs = np.asarray(uvs, np.float32)
        ul = me.uv_layers.new(name="UVMap")
        li = np.zeros(len(me.loops), np.int64)
        me.loops.foreach_get("vertex_index", li)
        ul.data.foreach_set("uv", uvs[li].ravel())
    me.polygons.foreach_set("use_smooth", [smooth] * len(me.polygons))
    me.update()
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    if mat is not None:
        me.materials.append(mat)
    if parent is not None:
        ob.parent = parent
    return ob


def grid_faces(nu, nv, wrap_u=False):
    """Quad faces for an (nv, nu) vertex grid (row-major, v rows of u columns)."""
    f = []
    cu = nu if wrap_u else nu - 1
    for j in range(nv - 1):
        for i in range(cu):
            i1 = (i + 1) % nu
            f.append((j * nu + i, j * nu + i1, (j + 1) * nu + i1, (j + 1) * nu + i))
    return f


def add_vattr(ob, name, values):
    """Per-vertex float attribute (readable in shaders via the Attribute node)."""
    me = ob.data
    a = me.attributes.new(name, "FLOAT", "POINT")
    a.data.foreach_set("value", np.asarray(values, np.float32))


def add_vcolor(ob, name, rgba):
    me = ob.data
    a = me.color_attributes.new(name, "FLOAT_COLOR", "POINT")
    a.data.foreach_set("color", np.asarray(rgba, np.float32).ravel())


# ----------------------------------------------------------------------------------- curves 2D
def catmull(points, n=None, per=12, closed=False):
    """Centripetal-ish Catmull-Rom through 2D/3D control points -> dense polyline."""
    P = np.asarray(points, np.float64)
    if closed:
        P = np.vstack([P[-1:], P, P[:2]])
    else:
        P = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    segs = len(P) - 3
    for i in range(segs):
        p0, p1, p2, p3 = P[i], P[i + 1], P[i + 2], P[i + 3]
        m = per if n is None else max(2, int(round(n / segs)))
        for k in range(m):
            t = k / m
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    if not closed:
        out.append(P[-2])
    return np.array(out)


def resample(path, n):
    """Arc-length resample a polyline to n points."""
    path = np.asarray(path, np.float64)
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
    t = np.linspace(0, d[-1], n)
    return np.stack([np.interp(t, d, path[:, k]) for k in range(path.shape[1])], 1)


def brush_profile(n, head=0.18, tail=0.35, swell=0.0, start=0.15, end=0.0, power=1.0):
    """Width multipliers along a brush stroke: press-in head, body (optionally swelling in the
    middle like a 兰叶描 orchid-leaf stroke), lifted tapering tail."""
    t = np.linspace(0, 1, n)
    w = np.ones(n)
    if head > 0:
        h = np.clip(t / head, 0, 1)
        w *= start + (1 - start) * np.sin(h * math.pi / 2) ** power
    if tail > 0:
        q = np.clip((1 - t) / tail, 0, 1)
        w *= end + (1 - end) * np.sin(q * math.pi / 2) ** power
    if swell:
        w *= 1 + swell * np.sin(t * math.pi)
    return w


def ribbon2d(path, widths):
    """2D polyline + per-point full widths -> (left, right) outline arrays and u (0..1)."""
    path = np.asarray(path, np.float64)
    d = np.gradient(path, axis=0)
    d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-12)
    nrm = np.stack([-d[:, 1], d[:, 0]], 1)
    hw = np.asarray(widths)[:, None] * 0.5
    L = path + nrm * hw
    R = path - nrm * hw
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
    return L, R, s / max(s[-1], 1e-9)


# ------------------------------------------------------------------------------- projection
class Surface:
    """Ray-projection target: a set of meshes in the head frame.  2D decal coordinates (x, z) are
    projected along +Y (front to back) onto the first surface hit."""

    def __init__(self, objs):
        vs, ps = [], []
        off = 0
        dg = bpy.context.evaluated_depsgraph_get()
        for ob in objs:
            ev = ob.evaluated_get(dg)
            me = ev.to_mesh()
            mw = ob.matrix_world
            v = np.zeros(len(me.vertices) * 3)
            me.vertices.foreach_get("co", v)
            v = v.reshape(-1, 3)
            M = np.array(mw)
            v = v @ M[:3, :3].T + M[:3, 3]
            vs.append(v)
            for p in me.polygons:
                ps.append([i + off for i in p.vertices])
            off += len(v)
            ev.to_mesh_clear()
        self.verts = np.vstack(vs)
        self.bvh = BVHTree.FromPolygons(self.verts.tolist(), ps)

    def hit(self, x, z, y0=-1.0, direction=(0, 1, 0)):
        loc, nrm, idx, dist = self.bvh.ray_cast(Vector((x, y0, z)), Vector(direction))
        if loc is None:
            loc, nrm, idx, dist = self.bvh.find_nearest(Vector((x, -0.3, z)))
        return np.array(loc), np.array(nrm)

    def project(self, pts2, offset=0.0003, y0=-1.0):
        """(N,2) x/z -> (N,3) points on the surface pushed out along the normal."""
        out = np.zeros((len(pts2), 3))
        for i, (x, z) in enumerate(pts2):
            p, n = self.hit(x, z, y0)
            if n[1] > 0:
                n = -n
            out[i] = p + n * offset
        return out

    def depth(self, x, z):
        p, _ = self.hit(x, z)
        return p[1]


def decal_strip(name, surf, path2, widths, col, mat, offset=0.00035, parent=None, uv=True):
    """A brush stroke: 2D centreline + widths -> projected ribbon mesh (2 rows).  UV u runs
    along the stroke 0..1, v across 0..1 (shaders draw soft edges / dry-brush from it)."""
    L, R, u = ribbon2d(path2, widths)
    n = len(u)
    rows = 5
    verts, uvs = [], []
    for k in range(rows):
        f = k / (rows - 1)
        verts.append(surf.project(R + (L - R) * f, offset))
        uvs.append(np.stack([u, np.full(n, f)], 1))
    verts = np.vstack(verts)
    uvs = np.vstack(uvs)
    faces = [(k * n + i, k * n + i + 1, (k + 1) * n + i + 1, (k + 1) * n + i)
             for k in range(rows - 1) for i in range(n - 1)]
    return mesh_obj(name, verts, faces, col, mat, smooth=True, uvs=uvs if uv else None,
                    parent=parent)


def decal_fill(name, surf, outline2, col, mat, offset=0.0003, rings=6, parent=None,
               local=None, center=None):
    """Fill a closed 2D outline with a radial ring grid (centre fan) and project it.
    UVs = ``local`` (same-length outline in the decal's own frame, interpolated like the
    outline) if given.  Vertex attribute ``ring`` = 0 at the centre .. 1 on the outline."""
    outline2 = np.asarray(outline2, np.float64)
    c = outline2.mean(0) if center is None else np.asarray(center, np.float64)
    n = len(outline2)
    pts = [c]
    ring = [0.0]
    if local is not None:
        local = np.asarray(local, np.float64)
        lc = local.mean(0) if center is None else local[0] * 0 + _map_center(outline2, local, c)
        lpts = [lc]
    for r in range(1, rings + 1):
        f = r / rings
        pts.extend(c + (outline2 - c) * f)
        ring.extend([f] * n)
        if local is not None:
            lpts.extend(lc + (local - lc) * f)
    pts = np.array(pts)
    faces = []
    for i in range(n):
        faces.append((0, 1 + i, 1 + (i + 1) % n))
    for r in range(1, rings):
        a = 1 + (r - 1) * n
        b = 1 + r * n
        for i in range(n):
            i1 = (i + 1) % n
            faces.append((a + i, b + i, b + i1, a + i1))
    P = surf.project(pts, offset)
    uvs = np.array(lpts) if local is not None else None
    ob = mesh_obj(name, P, faces, col, mat, smooth=True, uvs=uvs, parent=parent)
    add_vattr(ob, "ring", ring)
    return ob


def _map_center(outline2, local, c):
    """Affine map outline -> local (least squares), applied to the centre point."""
    A = np.hstack([outline2, np.ones((len(outline2), 1))])
    M, *_ = np.linalg.lstsq(A, local, rcond=None)
    return np.array([c[0], c[1], 1.0]) @ M


# --------------------------------------------------------------------------------- strands
def strands_obj(name, strands, radii, col, mat, parent=None):
    """Curves (hair) object from polylines; radii: per-strand array of per-point radii."""
    strands = [np.asarray(s, np.float32) for s in strands if len(s) >= 2]
    c = bpy.data.hair_curves.new(name)
    c.add_curves([len(s) for s in strands])
    pos = np.vstack(strands)
    c.position_data.foreach_set("vector", pos.ravel())
    ra = c.attributes.get("radius") or c.attributes.new("radius", "FLOAT", "POINT")
    ra.data.foreach_set("value", np.concatenate([np.asarray(r, np.float32) for r in radii]))
    c.materials.append(mat)
    ob = bpy.data.objects.new(name, c)
    col.objects.link(ob)
    if parent is not None:
        ob.parent = parent
    return ob


# ------------------------------------------------------------------------------ solids
def lathe(profile, n=48, closed_top=False):
    """Revolve (r, z) profile around Z -> verts, faces (u = angle columns, v = profile rows)."""
    profile = np.asarray(profile, np.float64)
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    V = []
    for r, z in profile:
        V.extend(np.stack([r * np.cos(a), r * np.sin(a), np.full(n, z)], 1))
    F = grid_faces(n, len(profile), wrap_u=True)
    return np.array(V), F


def smooth_field(nb, vals, mask, iters=10):
    """Laplacian-smooth per-vertex values over a neighbour table (masked vertices only)."""
    v = vals.copy()
    valid = nb >= 0
    cnt = valid.sum(1, keepdims=True).clip(1)
    for _ in range(iters):
        s = np.where(valid[..., None], v[np.where(valid, nb, 0)], 0).sum(1) / cnt
        v[mask] = s[mask]
    return v


def neighbours(nverts, faces):
    """(N, 8) padded neighbour table from quads/tris."""
    import collections
    adj = collections.defaultdict(set)
    for f in faces:
        f = list(dict.fromkeys(int(i) for i in f))
        for k in range(len(f)):
            a, b = f[k], f[(k + 1) % len(f)]
            adj[a].add(b)
            adj[b].add(a)
    m = max((len(s) for s in adj.values()), default=1)
    nb = -np.ones((nverts, m), np.int64)
    for k, s in adj.items():
        nb[k, :len(s)] = sorted(s)
    return nb
