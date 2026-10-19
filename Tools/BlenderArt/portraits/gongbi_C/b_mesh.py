"""Blender mesh helpers for the gongbi_C portrait bust (numpy in, objects out).

Everything is built from parametric grids: a *loft* is an (rows, cols, 3) array of points, rows
running top -> bottom, columns around (optionally closed).  UVs are the grid parameters in metres
(arc length around, height), so shader patterns (lamellae, brocade, hair streaks) keep their real
size on every piece.
"""

import math

import bpy
import numpy as np

# ---------------------------------------------------------------------------------------------
# small maths
# ---------------------------------------------------------------------------------------------


def pchip(xk, yk, x):
    """Monotone cubic (Fritsch-Carlson) interpolation; xk ascending."""
    xk = np.asarray(xk, np.float64)
    yk = np.asarray(yk, np.float64)
    x = np.asarray(x, np.float64)
    h = np.diff(xk)
    d = np.diff(yk) / h
    m = np.zeros_like(yk)
    m[0], m[-1] = d[0], d[-1]
    for i in range(1, len(xk) - 1):
        if d[i - 1] * d[i] <= 0:
            m[i] = 0.0
        else:
            w1 = 2 * h[i] + h[i - 1]
            w2 = h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    i = np.clip(np.searchsorted(xk, x) - 1, 0, len(xk) - 2)
    t = (x - xk[i]) / h[i]
    t2, t3 = t * t, t * t * t
    return ((2 * t3 - 3 * t2 + 1) * yk[i] + (t3 - 2 * t2 + t) * h[i] * m[i]
            + (-2 * t3 + 3 * t2) * yk[i + 1] + (t3 - t2) * h[i] * m[i + 1])


def spow(s, e):
    """sign(s) |s|^e"""
    return np.sign(s) * np.abs(s) ** e


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, np.float64) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def resample(P, n):
    """Resample a polyline (N x D) to ``n`` points evenly spaced by arc length."""
    P = np.asarray(P, np.float64)
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    L = np.concatenate([[0], np.cumsum(seg)])
    if L[-1] < 1e-12:
        return np.repeat(P[:1], n, axis=0)
    t = np.linspace(0, L[-1], n)
    return np.stack([np.interp(t, L, P[:, k]) for k in range(P.shape[1])], -1)


def bezier(p0, p1, p2, p3, n=24):
    t = np.linspace(0, 1, n)[:, None]
    p0, p1, p2, p3 = (np.asarray(p, np.float64) for p in (p0, p1, p2, p3))
    return ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3 * p3


# ---------------------------------------------------------------------------------------------
# objects
# ---------------------------------------------------------------------------------------------


def link(obj, col):
    col.objects.link(obj)
    return obj


def mesh_object(name, verts, faces, col, smooth=True, uvs=None, mat=None, face_mats=None,
                mats=None, parent=None):
    """verts (N, 3), faces list/array of index tuples, uvs (N, 2) per-vertex (optional)."""
    me = bpy.data.meshes.new(name)
    verts = np.asarray(verts, np.float64)
    me.from_pydata(verts.tolist(), [], [list(map(int, f)) for f in faces])
    me.update(calc_edges=True)
    n = len(me.polygons)
    me.polygons.foreach_set("use_smooth", [bool(smooth)] * n)
    if uvs is not None:
        uvs = np.asarray(uvs, np.float32)
        lay = me.uv_layers.new(name="UVMap")
        li = np.empty(len(me.loops), np.int64)
        me.loops.foreach_get("vertex_index", li)
        lay.data.foreach_set("uv", uvs[li].reshape(-1))
    for m in (mats or ([mat] if mat is not None else [])):
        me.materials.append(m)
    if face_mats is not None:
        me.polygons.foreach_set("material_index", [int(i) for i in face_mats])
    me.update()
    obj = bpy.data.objects.new(name, me)
    col.objects.link(obj)
    if parent is not None:
        obj.parent = parent
    return obj


def grid_faces(nr, nc, wrap=False, flip=False):
    """Quad faces of an (nr, nc) vertex grid, optionally wrapping columns."""
    idx = np.arange(nr * nc).reshape(nr, nc)
    cols = nc if wrap else nc - 1
    f = []
    for i in range(nr - 1):
        for j in range(cols):
            j2 = (j + 1) % nc
            q = (idx[i, j], idx[i + 1, j], idx[i + 1, j2], idx[i, j2])
            f.append(q[::-1] if flip else q)
    return f


def grid_object(name, P, col, wrap=False, flip=False, cap_top=False, cap_bottom=False, uv=None,
                mat=None, mats=None, face_mat_fn=None, smooth=True, parent=None):
    """Object from an (nr, nc, 3) grid.  ``uv`` (nr, nc, 2); ``face_mat_fn(i, j) -> slot``;
    caps close a wrapped grid with a fan to the centroid of its first / last row."""
    nr, nc = P.shape[:2]
    V = P.reshape(-1, 3)
    F = grid_faces(nr, nc, wrap, flip)
    fm = None
    if face_mat_fn is not None:
        fm = []
        cols = nc if wrap else nc - 1
        for i in range(nr - 1):
            for j in range(cols):
                fm.append(face_mat_fn(i, j))
    UV = uv.reshape(-1, 2) if uv is not None else None
    extra = []
    if cap_top or cap_bottom:
        V = list(V)
        if UV is not None:
            UV = list(UV)
        for flag, row, rev in ((cap_top, 0, not flip), (cap_bottom, nr - 1, flip)):
            if not flag:
                continue
            c = P[row].mean(0)
            ci = len(V)
            V.append(c)
            if UV is not None:
                UV.append(uv[row].mean(0))
            for j in range(nc):
                j2 = (j + 1) % nc
                tri = (ci, row * nc + j2, row * nc + j) if rev else (ci, row * nc + j, row * nc + j2)
                extra.append(tri)
                if fm is not None:
                    fm.append(fm[-1] if fm else 0)
        V = np.array(V)
        if UV is not None:
            UV = np.array(UV)
    return mesh_object(name, V, list(F) + extra, col, smooth=smooth, uvs=UV, mat=mat, mats=mats,
                       face_mats=fm, parent=parent)


def strip(name, left, right, col, mat=None, uv_len=True, smooth=True, parent=None, mats=None,
          face_mats=None):
    """Ribbon between two polylines (N, 3) sampled at the same parameters."""
    left = np.asarray(left, np.float64)
    right = np.asarray(right, np.float64)
    n = len(left)
    P = np.stack([left, right], 1)          # (n, 2, 3)
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff((left + right) / 2, axis=0), axis=1))])
    w = np.linalg.norm(right - left, axis=1).mean()
    uv = np.zeros((n, 2, 2))
    uv[:, 0, 0] = s
    uv[:, 1, 0] = s
    uv[:, 0, 1] = 0.0
    uv[:, 1, 1] = w
    return grid_object(name, P, col, uv=uv, mat=mat, mats=mats, smooth=smooth, parent=parent,
                       face_mat_fn=(lambda i, j: face_mats[i]) if face_mats is not None else None)


def tube(name, path, radius, col, n_around=10, mat=None, cap=True, parent=None, smooth=True):
    """Tube along ``path`` (N, 3) with radius scalar or (N,) array."""
    path = np.asarray(path, np.float64)
    n = len(path)
    r = np.broadcast_to(np.asarray(radius, np.float64), (n,))
    T = np.gradient(path, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
    up = np.array([0, 0, 1.0]) if abs(T[0, 2]) < 0.9 else np.array([1.0, 0, 0])
    N = np.cross(T, up)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    B = np.cross(T, N)
    a = np.linspace(0, 2 * math.pi, n_around, endpoint=False)
    P = path[:, None, :] + r[:, None, None] * (np.cos(a)[None, :, None] * N[:, None, :]
                                               + np.sin(a)[None, :, None] * B[:, None, :])
    return grid_object(name, P, col, wrap=True, cap_top=cap, cap_bottom=cap, mat=mat,
                       parent=parent, smooth=smooth)


def lathe(name, profile, col, n_around=32, mat=None, center=(0, 0, 0), axis_scale=(1, 1),
          parent=None, cap_top=True, cap_bottom=False, smooth=True, uv=True):
    """Surface of revolution of ``profile`` [(r, z), ...] (top first) around +Z."""
    prof = np.asarray(profile, np.float64)
    a = np.linspace(0, 2 * math.pi, n_around, endpoint=False)
    P = np.zeros((len(prof), n_around, 3))
    P[..., 0] = prof[:, 0:1] * np.cos(a)[None] * axis_scale[0] + center[0]
    P[..., 1] = prof[:, 0:1] * np.sin(a)[None] * axis_scale[1] + center[1]
    P[..., 2] = prof[:, 1:2] + center[2]
    UV = None
    if uv:
        UV = np.zeros((len(prof), n_around, 2))
        rm = max(prof[:, 0].max(), 1e-6)
        UV[..., 0] = a[None] * rm
        s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(prof, axis=0), axis=1))])
        UV[..., 1] = -s[:, None]
    return grid_object(name, P, col, wrap=True, cap_top=cap_top, cap_bottom=cap_bottom, mat=mat,
                       parent=parent, uv=UV, flip=True, smooth=smooth)


def ellipsoid(name, center, radii, col, mat=None, n=(24, 16), parent=None, rot=None):
    """UV ellipsoid; ``rot`` optional 3x3 matrix applied before translation."""
    nu, nv = n
    th = np.linspace(0, math.pi, nv)
    ph = np.linspace(0, 2 * math.pi, nu, endpoint=False)
    P = np.zeros((nv, nu, 3))
    P[..., 0] = np.sin(th)[:, None] * np.cos(ph)[None] * radii[0]
    P[..., 1] = np.sin(th)[:, None] * np.sin(ph)[None] * radii[1]
    P[..., 2] = np.cos(th)[:, None] * radii[2] * np.ones_like(ph)[None]
    if rot is not None:
        P = P @ np.asarray(rot).T
    P += np.asarray(center)
    P = P[1:-1]
    top = np.asarray(center) + (np.asarray(rot) @ np.array([0, 0, radii[2]]) if rot is not None
                                else np.array([0, 0, radii[2]]))
    UV = np.zeros(P.shape[:2] + (2,))
    UV[..., 0] = ph[None] * max(radii[0], radii[1])
    UV[..., 1] = -th[1:-1, None] * radii[2]
    return grid_object(name, P, col, wrap=True, cap_top=True, cap_bottom=True, mat=mat,
                       parent=parent, uv=UV, flip=True)


def rot_xyz(rx=0.0, ry=0.0, rz=0.0):
    """3x3 rotation (radians), applied X then Y then Z."""
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def fix_normals(obj, outward_from=None):
    """Make face normals point away from ``outward_from`` (world point) on average."""
    import bmesh
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    if outward_from is not None:
        c = np.asarray(outward_from)
        s = 0.0
        for f in bm.faces:
            fc = np.array(f.calc_center_median())
            s += float(np.dot(np.array(f.normal), fc - c)) * f.calc_area()
        if s < 0:
            for f in bm.faces:
                f.normal_flip()
    bm.to_mesh(me)
    bm.free()
    me.update()
