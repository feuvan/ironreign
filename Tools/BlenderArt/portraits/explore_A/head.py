"""Head + eyes from MakeHuman data, with landmarks and per-vertex region masks (bpy).

``build(identity)`` returns a dict:
    head      the cropped skin mesh object (bust down to the upper chest), subdivision modifier,
              float point attributes (region masks, see MASK_SOURCES) and ``fc`` face coordinates
    eyes      [left, right] eyeball objects (origin at the eyeball centre, MH high-poly eye + UVs)
    lm        landmarks in Blender metres (eye_l, eye_r, eye_c, ipd, nose_tip, chin, mouth_c,
              mouth_l, mouth_r, brow_c, crown, neck_base, ear_l, ear_r, axes ex/ey/ez)
    V         morphed MakeHuman vertices (MH units) - helpers included
Region masks are derived from how strongly a MakeHuman target moves each vertex, so they follow
every identity automatically (lip masks from the lip-volume targets, brows from the brow-raise
target, ...).
"""

import math
import os

import bpy
import numpy as np
from mathutils import Matrix, Vector

import mh

MASK_SOURCES = {
    "m_lip_u": ["mouth/mouth-upperlip-volume-incr"],
    "m_lip_l": ["mouth/mouth-lowerlip-volume-incr"],
    "m_brow": ["eyebrows/eyebrows-trans-up"],
    "m_nose": ["nose/nose-volume-incr"],
    "m_cheek": ["cheek/l-cheek-volume-incr", "cheek/r-cheek-volume-incr"],
    "m_bag": ["eyes/l-eye-bag-incr", "eyes/r-eye-bag-incr"],
    "m_ear": ["ears/l-ear-scale-incr", "ears/r-ear-scale-incr"],
    "m_chin": ["chin/chin-prominent-incr"],
    "m_neck": ["neck/neck-scale-horiz-incr"],
    "m_laugh": ["mouth/mouth-laugh-lines-in"],
    "m_lids": ["eyes/l-eye-height2-incr", "eyes/r-eye-height2-incr"],
}

CROP_Y = 4.0  # MH units: keep the bust above the upper chest


def region_masks():
    cp = os.path.join(mh.CACHE, "masks_v1.npz")
    if os.path.exists(cp):
        d = np.load(cp)
        return {k: d[k] for k in d.files}
    out = {}
    for name, rels in MASK_SOURCES.items():
        m = np.zeros(mh.N_BODY + 6000)
        for rel in rels:
            i, dl = mh.load_target(rel)
            mag = np.linalg.norm(dl, axis=1)
            mm = np.zeros_like(m)
            mm[i] = mag / max(mag.max(), 1e-9)
            m = np.maximum(m, mm)
        out[name] = m.astype(np.float32)
    np.savez(cp, **out)
    return out


def _new_obj(name, me, col=None):
    ob = bpy.data.objects.new(name, me)
    (col or bpy.context.scene.collection).objects.link(ob)
    return ob


def _attr(me, name, values, kind="FLOAT"):
    a = me.attributes.get(name) or me.attributes.new(name, kind, "POINT")
    if kind == "FLOAT":
        a.data.foreach_set("value", np.asarray(values, np.float32).ravel())
    else:
        a.data.foreach_set("vector", np.asarray(values, np.float32).ravel())


def landmarks(Vb, masks, eye_l, eye_r):
    """Landmarks in Blender coordinates from morphed verts (Blender coords, body only)."""
    lm = {}
    c = (eye_l + eye_r) / 2.0
    ex = eye_l - eye_r
    ipd = float(np.linalg.norm(ex))
    ex /= ipd
    up = np.array([0.0, 0.0, 1.0])
    up = up - ex * np.dot(up, ex)
    up /= np.linalg.norm(up)
    fwd = np.cross(up, ex)  # x right(char left), z up -> forward = -Y
    if fwd[1] > 0:
        fwd = -fwd
    lm.update(eye_l=eye_l, eye_r=eye_r, eye_c=c, ipd=ipd, ex=ex, ez=up, ey=fwd)
    body = Vb[:mh.N_BODY]
    rel = body - c
    fx, fz, fy = rel @ ex / ipd, rel @ up / ipd, rel @ fwd / ipd
    nm = masks["m_nose"][:mh.N_BODY] > 0.5
    lm["nose_tip"] = body[np.where(nm)[0][np.argmax(fy[nm])]]
    lip = np.maximum(masks["m_lip_u"], masks["m_lip_l"])[:mh.N_BODY]
    li = lip > 0.25
    w = lip[li]
    lm["mouth_c"] = (body[li] * w[:, None]).sum(0) / w.sum()
    lm["mouth_l"] = body[np.where(li)[0][np.argmax(fx[li])]]
    lm["mouth_r"] = body[np.where(li)[0][np.argmin(fx[li])]]
    # chin: lowest front midline point above the neck (|fx| < 0.08, fy > 0.3)
    mid = (np.abs(fx) < 0.08) & (fz < -1.4) & (fz > -3.0)
    cand = np.where(mid)[0]
    # menton: lowest midline point that is still within 0.8 IPD of the chin's front
    front = cand[fy[cand] > fy[cand].max() - 0.8]
    lm["chin"] = body[front[np.argmin(fz[front])]]
    bm = masks["m_brow"][:mh.N_BODY] > 0.5
    lm["brow_c"] = body[bm].mean(0)
    lm["crown"] = body[np.argmax(body[:, 2])]
    em = masks["m_ear"][:mh.N_BODY] > 0.3
    lm["ear_l"] = body[em & (fx > 0)].mean(0)
    lm["ear_r"] = body[em & (fx < 0)].mean(0)
    nk = masks["m_neck"][:mh.N_BODY] > 0.3
    lm["neck_c"] = body[nk].mean(0)
    lm["fc"] = np.stack([fx, fz, fy], -1)
    return lm


def face_coords(Vb, eye_l, eye_r):
    c = (eye_l + eye_r) / 2.0
    ex = eye_l - eye_r
    ipd = float(np.linalg.norm(ex))
    ex = ex / ipd
    up = np.array([0.0, 0.0, 1.0])
    up = up - ex * np.dot(up, ex)
    up /= np.linalg.norm(up)
    fwd = np.cross(up, ex)
    if fwd[1] > 0:
        fwd = -fwd
    rel = Vb - c
    return np.stack([rel @ ex, rel @ up, rel @ fwd], -1) / ipd


def _eye_centres(Vb_proxy):
    out = []
    for sel in (Vb_proxy[:, 0] > 0, Vb_proxy[:, 0] <= 0):
        verts = Vb_proxy[sel]
        A = np.c_[2 * verts, np.ones(len(verts))]
        sol = np.linalg.lstsq(A, (verts ** 2).sum(1), rcond=None)[0]
        out.append(sol[:3])
    return out


def build(idn, subdiv=2, collection=None):
    import regions
    base = mh.load_base()
    V_rest = mh.apply_targets(base.verts, idn.target_weights(expression=False))
    full = idn.target_weights()
    expr = {k: v for k, v in full.items() if k.startswith("expression/")}
    V = mh.apply_targets(V_rest, expr)
    masks = region_masks()
    Vb_all = mh.to_blender(V)
    # rest-face coordinates (features painted in fc ride with the skin under expressions)
    px0 = mh.eyes_proxy()
    el0, er0 = _eye_centres(mh.to_blender(px0.fit(V_rest)))
    fc_rest = face_coords(mh.to_blender(V_rest), el0, er0)
    lash_up = fc_rest[base.group_verts("helper-l-eyelashes-2", "helper-r-eyelashes-2")]
    lash_lo = fc_rest[base.group_verts("helper-l-eyelashes-1", "helper-r-eyelashes-1")]
    bm = {k: v[:mh.N_BODY] for k, v in masks.items()}
    F = regions.FaceFrame.from_masks(fc_rest[:mh.N_BODY], bm, lash_up, lash_lo)
    # ---- eyes (proxy fitted on the helper eyeballs)
    px = mh.eyes_proxy()
    ev, euv, ef, efu = px.load_obj()
    pv = mh.to_blender(px.fit(V))
    left = pv[:, 0] > 0
    eye_objs = []
    centres = []
    for side, sel in (("L", left), ("R", ~left)):
        idx = np.where(sel)[0]
        remap = {j: k for k, j in enumerate(idx)}
        fsel = [k for k, f in enumerate(ef) if all(sel[j] for j in f)]
        verts = pv[idx]
        # sphere centre: least squares fit (cornea bulge would bias a plain mean forward)
        A = np.c_[2 * verts, np.ones(len(verts))]
        bvec = (verts ** 2).sum(1)
        sol = np.linalg.lstsq(A, bvec, rcond=None)[0]
        ctr = sol[:3]
        centres.append(ctr)
        me = bpy.data.meshes.new("Eye" + side)
        me.from_pydata((verts - ctr).tolist(), [], [[remap[j] for j in ef[k]] for k in fsel])
        uvl = me.uv_layers.new(name="UVMap")
        loops_uv = []
        for k in fsel:
            for t in efu[k]:
                loops_uv.append(euv[t])
        uvl.data.foreach_set("uv", np.array(loops_uv, np.float32).ravel())
        for p in me.polygons:
            p.use_smooth = True
        ob = _new_obj("Eye" + side, me, collection)
        ob.location = Vector(ctr)
        eye_objs.append(ob)
    eye_l, eye_r = centres
    lm = landmarks(Vb_all, masks, np.array(eye_l), np.array(eye_r))
    lm["eye_radius"] = float(np.linalg.norm(pv[left] - eye_l, axis=1).max())
    # ---- skin mesh: body faces above the crop line
    body_faces = base.group_faces("body")
    keep = [i for i in body_faces if min(V[j, 1] for j in base.faces[i]) > CROP_Y]
    used = np.array(sorted({j for i in keep for j in base.faces[i]}), np.int64)
    remap = np.full(len(V), -1, np.int64)
    remap[used] = np.arange(len(used))
    me = bpy.data.meshes.new("Head")
    me.from_pydata(Vb_all[used].tolist(), [], [[int(remap[j]) for j in base.faces[i]] for i in keep])
    uvl = me.uv_layers.new(name="UVMap")
    uvs = np.array([base.uvs[t] for i in keep for t in base.face_uvs[i]], np.float32)
    uvl.data.foreach_set("uv", uvs.ravel())
    for p in me.polygons:
        p.use_smooth = True
    for name, m in masks.items():
        _attr(me, name, m[used])
    _attr(me, "fc", fc_rest[used], "FLOAT_VECTOR")
    me.update()
    head = _new_obj("Head", me, collection)
    if subdiv:
        sd = head.modifiers.new("Subdiv", "SUBSURF")
        sd.levels = subdiv
        sd.render_levels = subdiv
        sd.uv_smooth = "PRESERVE_BOUNDARIES"
    lm["used"] = used
    return dict(head=head, eyes=eye_objs, lm=lm, V=V, Vb=Vb_all, F=F, fc=fc_rest, masks=masks,
                keep=keep, used=used, base=base)


def aim_eyes(eyes, target, weight=1.0, lift=0.0):
    """Rotate each eyeball (MH eyes look along -Y) toward ``target`` (blend ``weight``)."""
    for ob in eyes:
        d = (Vector(target) - ob.location).normalized()
        fwd = Vector((0, -1, 0))
        d = fwd.lerp(d, weight).normalized()
        d.z += lift
        d.normalize()
        q = fwd.rotation_difference(d)
        ob.rotation_mode = "QUATERNION"
        ob.rotation_quaternion = q


def evaluated_mesh_arrays(obj):
    """World-space triangles of the evaluated (subdivided) object: (P (n,3), tris (m,3), N (n,3),
    attributes dict name->(n,) or (n,3))."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    n = len(me.vertices)
    P = np.empty(n * 3, np.float32)
    me.vertices.foreach_get("co", P)
    P = P.reshape(-1, 3)
    N = np.empty(n * 3, np.float32)
    me.vertices.foreach_get("normal", N)
    N = N.reshape(-1, 3)
    T = np.empty(len(me.loop_triangles) * 3, np.int32)
    me.loop_triangles.foreach_get("vertices", T)
    T = T.reshape(-1, 3)
    attrs = {}
    for a in me.attributes:
        if a.domain != "POINT" or a.name.startswith(".") or a.name in ("position",):
            continue
        if a.data_type == "FLOAT":
            arr = np.empty(n, np.float32)
            a.data.foreach_get("value", arr)
        elif a.data_type == "FLOAT_VECTOR":
            arr = np.empty(n * 3, np.float32)
            a.data.foreach_get("vector", arr)
            arr = arr.reshape(-1, 3)
        else:
            continue
        attrs[a.name] = arr
    mw = np.array(obj.matrix_world)
    P = P @ mw[:3, :3].T + mw[:3, 3]
    ev.to_mesh_clear()
    return P, T, N, attrs


def sample_surface(P, T, N, attrs, count, weight_fn, rng):
    """Area-weighted random points on triangles, accepted with probability weight_fn(attrs_at_pt).
    Returns positions (k,3), normals (k,3), attrs dict at the points."""
    a, b, c = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    # pre-evaluate weights at triangle centres to focus sampling
    ac = {k: (v[T[:, 0]] + v[T[:, 1]] + v[T[:, 2]]) / 3.0 for k, v in attrs.items()}
    wt = np.clip(weight_fn(ac), 0, None)
    pr = area * (wt > 1e-3)
    if pr.sum() <= 0:
        return np.zeros((0, 3)), np.zeros((0, 3)), {}
    pr = pr / pr.sum()
    n_try = int(count * 2.5)
    tri = rng.choice(len(T), n_try, p=pr)
    r1, r2 = rng.random(n_try), rng.random(n_try)
    s = np.sqrt(r1)
    u, v, w = 1 - s, s * (1 - r2), s * r2
    ti = T[tri]

    def interp(arr):
        if arr.ndim == 1:
            return arr[ti[:, 0]] * u + arr[ti[:, 1]] * v + arr[ti[:, 2]] * w
        return arr[ti[:, 0]] * u[:, None] + arr[ti[:, 1]] * v[:, None] + arr[ti[:, 2]] * w[:, None]
    pos = interp(P)
    nrm = interp(N)
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-9
    at = {k: interp(v) for k, v in attrs.items()}
    wp = np.clip(weight_fn(at), 0, 1)
    acc = rng.random(n_try) < wp
    idx = np.where(acc)[0][:count]
    return pos[idx], nrm[idx], {k: v[idx] for k, v in at.items()}
