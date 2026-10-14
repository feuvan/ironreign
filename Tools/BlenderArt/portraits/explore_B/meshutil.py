"""Small numpy mesh helpers (bpy for object creation only)."""

import bpy
import numpy as np


def make_mesh(name, V, F, col=None, smooth=True, mats=None, mat_index=None, uv=None, attrs=None):
    """V (N,3) Blender coords; F list/array of index tuples (tris/quads, any mix) or (F,4) array
    where tris repeat the last index.  ``uv``: per-vertex (N,2) -> UV layer 'UVMap'.
    ``attrs``: {name: (N,) float per vertex}."""
    V = np.asarray(V, np.float32)
    if isinstance(F, np.ndarray) and F.ndim == 2:
        if F.shape[1] == 4:
            n = np.where(F[:, 3] == F[:, 2], 3, 4)
        else:
            n = np.full(len(F), F.shape[1])
        loops = np.concatenate([f[:k] for f, k in zip(F, n)]) if len(F) else np.zeros(0, np.int32)
    else:
        n = np.array([len(f) for f in F])
        loops = np.array([i for f in F for i in f], np.int32)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", V.ravel())
    me.loops.add(len(loops))
    me.loops.foreach_set("vertex_index", loops.astype(np.int32))
    me.polygons.add(len(n))
    ls = np.concatenate([[0], np.cumsum(n)[:-1]]).astype(np.int32)
    me.polygons.foreach_set("loop_start", ls)
    me.polygons.foreach_set("loop_total", n.astype(np.int32))
    if uv is not None:
        uvl = me.uv_layers.new(name="UVMap")
        uvl.data.foreach_set("uv", np.asarray(uv, np.float32)[loops].ravel())
    if mat_index is not None:
        me.polygons.foreach_set("material_index", np.asarray(mat_index, np.int32))
    for k, v in (attrs or {}).items():
        a = me.attributes.new(k, "FLOAT", "POINT")
        a.data.foreach_set("value", np.asarray(v, np.float32))
    me.update(calc_edges=True)
    if smooth:
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    ob = bpy.data.objects.new(name, me)
    (col or bpy.context.scene.collection).objects.link(ob)
    for m in (mats or []):
        me.materials.append(m)
    return ob


def mesh_arrays(ob, evaluated=False, world=True):
    if evaluated:
        dg = bpy.context.evaluated_depsgraph_get()
        o = ob.evaluated_get(dg)
        me = o.to_mesh()
    else:
        me = ob.data
    V = np.zeros(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", V)
    V = V.reshape(-1, 3)
    if world:
        mw = np.array(ob.matrix_world, np.float32)
        V = V @ mw[:3, :3].T + mw[:3, 3]
    ls = np.zeros(len(me.polygons), np.int32)
    lt = np.zeros(len(me.polygons), np.int32)
    me.polygons.foreach_get("loop_start", ls)
    me.polygons.foreach_get("loop_total", lt)
    lv = np.zeros(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", lv)
    F = [lv[s:s + t] for s, t in zip(ls, lt)]
    if evaluated:
        o.to_mesh_clear()
    return V, F


def faces_to_quads(F):
    out = np.zeros((len(F), 4), np.int32)
    for i, f in enumerate(F):
        if len(f) == 3:
            out[i] = (f[0], f[1], f[2], f[2])
        else:
            out[i] = f[:4]
    return out


def vertex_normals(V, Q):
    """Q (F,4) quads/tris (last repeated)."""
    a, b, c, d = (V[Q[:, i]] for i in range(4))
    fn = np.cross(c - a, d - b)
    tri = Q[:, 3] == Q[:, 2]
    fn[tri] = np.cross(b[tri] - a[tri], c[tri] - a[tri])
    vn = np.zeros_like(V)
    for i in range(4):
        np.add.at(vn, Q[:, i], fn * np.where((i == 3) & tri, 0, 1)[:, None])
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)


def adjacency(Q, n):
    e = np.concatenate([Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]])
    e = e[e[:, 0] != e[:, 1]]
    e = np.concatenate([e, e[:, ::-1]])
    e = np.unique(e, axis=0)
    return e[:, 0], e[:, 1]


def laplacian(V, rows, cols, iters=5, lam=0.5, fixed=None):
    n = len(V)
    deg = np.bincount(rows, minlength=n).astype(np.float32)
    deg[deg == 0] = 1
    V = V.copy()
    for _ in range(iters):
        acc = np.zeros_like(V)
        for k in range(3):
            acc[:, k] = np.bincount(rows, weights=V[cols, k], minlength=n)
        avg = acc / deg[:, None]
        nv = V + lam * (avg - V)
        if fixed is not None:
            nv[fixed] = V[fixed]
        V = nv
    return V


def boundary_verts(Q):
    e = np.concatenate([Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]])
    e = e[e[:, 0] != e[:, 1]]
    k = np.sort(e, axis=1)
    u, c = np.unique(k, axis=0, return_counts=True)
    return np.unique(u[c == 1].ravel())


def submesh(V, Q, keep_face):
    Q = Q[keep_face]
    used = np.unique(Q.ravel())
    rm = -np.ones(len(V), np.int32)
    rm[used] = np.arange(len(used), dtype=np.int32)
    return V[used], rm[Q], used
