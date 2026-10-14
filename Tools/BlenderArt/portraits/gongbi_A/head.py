"""The bust's head and shoulders from the MakeHuman base mesh (neutral race blend, see mh.py),
reshaped by the canon's feature targets, plus closed eye surfaces and landmarks.

The head is only a *form* for Freestyle contours and soft 晕染; every facial feature is drawn
as a brush decal (face.py), so the MakeHuman eyelids, lips and nostrils are face-marked and never
produce lines.
"""

import math

import bpy
import numpy as np

import geo
import mh


class Head:
    pass


def build(canon, col_skin, col_hidden, skin_mat, parent):
    """canon: dict with gender, years, muscle, weight, mods.  Returns Head with obj, eyes,
    landmarks and a projection Surface."""
    v, f, j = mh.body_verts(canon["gender"], canon["years"], canon.get("muscle", 0.5),
                            canon.get("weight", 0.5), canon.get("mods"))
    H = Head()
    eL, eR = j["joint-l-eye"], j["joint-r-eye"]
    H.eye_l, H.eye_r = eL, eR
    eye_z = 0.5 * (eL[2] + eR[2])
    H.eye_z = eye_z
    # crop: head, neck and shoulders down to the upper chest
    cut = eye_z - canon.get("crop", 0.34)
    keep = np.all(v[f][:, :, 2] > cut, axis=1) & np.all(np.abs(v[f][:, :, 0]) < 0.26, axis=1)
    keep &= ~pocket_mask()
    F = f[keep]
    used = np.unique(F)
    remap = -np.ones(len(v), np.int64)
    remap[used] = np.arange(len(used))
    V = v[used]
    F = remap[F]
    faces = [tuple(q) if q[2] != q[3] else tuple(q[:3]) for q in F]
    V, faces = close_eyes(V, faces, (eL, eR), canon.get("eyeball_r", 0.0125))
    # the rendered skin: head, neck and the upper chest only (arms and torso are always
    # clothed; the full crop is kept in H.faces for fitting the garments)
    zc = eye_z - canon.get("skin_crop", 0.21)
    vis = [f for f in faces if V[list(f), 2].min() > zc and np.abs(V[list(f), 0]).max() < 0.09]
    ob = geo.mesh_obj("Head", V, vis, col_skin, skin_mat, smooth=True, parent=parent)
    H.obj = ob
    H.verts = V
    H.faces = faces
    eyes = []
    H.eyeballs = eyes
    # face marks: eyelids, lips and nostrils never get Freestyle lines
    me = ob.data
    cen = np.zeros(len(me.polygons) * 3)
    me.polygons.foreach_get("center", cen)
    cen = cen.reshape(-1, 3)
    H.surf = geo.Surface([ob] + eyes)
    lm = landmarks(H)
    H.lm = lm
    mark = np.zeros(len(cen), bool)
    for c in (eL, eR):
        d = (cen - c) / np.array([0.024, 0.03, 0.017])
        mark |= (np.einsum("ij,ij->i", d, d) < 1.0) & (cen[:, 1] < c[1] + 0.006)
    mz = lm["mouth"][2]
    d = (cen - np.array([0, lm["mouth"][1], mz])) / np.array([0.032, 0.03, 0.011])
    mark |= np.einsum("ij,ij->i", d, d) < 1.0
    nt = lm["nose_tip"]
    d = (cen - np.array([0, nt[1] + 0.012, nt[2] - 0.009])) / np.array([0.021, 0.022, 0.011])
    mark |= np.einsum("ij,ij->i", d, d) < 1.0
    me.polygons.foreach_set("use_freestyle_mark", mark.tolist())
    me.update()
    jaw_marks(H, canon)
    return H


def _dijkstra(nverts, edges, cost, src, dst):
    import heapq
    adj = [[] for _ in range(nverts)]
    for k, (a, b) in enumerate(edges):
        adj[a].append((b, k))
        adj[b].append((a, k))
    dist = np.full(nverts, np.inf)
    prev = -np.ones(nverts, np.int64)
    pe = -np.ones(nverts, np.int64)
    dist[src] = 0.0
    hq = [(0.0, src)]
    while hq:
        d, u = heapq.heappop(hq)
        if u == dst:
            break
        if d > dist[u]:
            continue
        for v, k in adj[u]:
            nd = d + cost[k]
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                pe[v] = k
                heapq.heappush(hq, (nd, v))
    path = []
    u = dst
    while u != src and u >= 0:
        path.append(pe[u])
        u = prev[u]
    return path


def jaw_curve(H, n=41, span_deg=78.0):
    """The mandible's lower border as a smooth 3D curve: for each azimuth around the head axis
    the border is where the horizontal radius drops fastest going down (jaw -> neck)."""
    from mathutils import Vector
    lm = H.lm
    s = H.surf
    k = (H.eye_z - lm["menton"][2]) / 0.108
    yc = lm["nose_tip"][1] + 0.112 * k
    z0, z1 = lm["menton"][2] - 0.012 * k, lm["mouth"][2] - 0.004
    zs = np.arange(z0, z1, 0.0008)
    phis = np.radians(np.linspace(-span_deg, span_deg, n))
    zb, rb = [], []
    for ph in phis:
        d = np.array([np.sin(ph), -np.cos(ph), 0.0])
        rr = []
        for z in zs:
            o = np.array([0.0, yc, z]) + d * 0.3
            hit = s.bvh.ray_cast(Vector(o), Vector(-d), 0.3)
            rr.append(0.3 - hit[3] if hit[0] is not None else np.nan)
        rr = np.array(rr)
        ok = ~np.isnan(rr)
        rr = np.interp(zs, zs[ok], rr[ok]) if ok.any() else np.full(len(zs), 0.05)
        g = np.gradient(rr, zs)          # dr/dz: large positive where the jaw overhangs
        g = np.convolve(g, np.ones(5) / 5, mode="same")
        i = int(np.argmax(g))
        zb.append(zs[i])
        rb.append(rr[i])
    zb = np.array(zb)
    rb = np.array(rb)
    ker = np.exp(-0.5 * (np.arange(-4, 5) / 2.0) ** 2)
    ker /= ker.sum()
    pad = lambda x: np.r_[[x[0]] * 4, x, [x[-1]] * 4]
    zb = np.convolve(pad(zb), ker, mode="valid")
    rb = np.convolve(pad(rb), ker, mode="valid")
    pts = np.stack([np.sin(phis) * rb, yc - np.cos(phis) * rb, zb], 1)
    return pts


def jaw_marks(H, canon):
    """Freestyle edge marks along the mandible: the gongbi jaw line is an anatomical line, so
    it is traced once on the mesh as the shortest edge path that hugs the smooth jaw curve."""
    me = H.obj.data
    V = H.verts
    nv = len(V)
    E = np.zeros(len(me.edges) * 2, np.int64)
    me.edges.foreach_get("vertices", E)
    E = E.reshape(-1, 2)
    curve = jaw_curve(H, span_deg=canon.get("jaw_span", 70.0))
    H.jaw_curve = curve
    # distance of each vertex to the curve polyline (dense resample)
    dense = geo.resample(curve, 400)
    from mathutils.kdtree import KDTree
    kd = KDTree(len(dense))
    for i, p in enumerate(dense):
        kd.insert(p, i)
    kd.balance()
    near = np.full(nv, 1.0)
    cand = np.nonzero(np.linalg.norm(V - curve.mean(0), axis=1) < 0.15)[0]
    for i in cand:
        near[i] = kd.find(V[i])[2]
    L = np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1)
    dd = 0.5 * (near[E[:, 0]] + near[E[:, 1]])
    cost = L * (0.02 + (dd / 0.0025) ** 2)
    src = int(np.argmin(np.linalg.norm(V - curve[0], axis=1)))
    dst = int(np.argmin(np.linalg.norm(V - curve[-1], axis=1)))
    path = _dijkstra(nv, E, cost, src, dst)
    em = np.zeros(len(me.edges), bool)
    em[path] = True
    # drop the ragged ends (where the mandible meets the neck below the ear)
    ends = np.minimum(np.linalg.norm(V[E[:, 0]] - curve[0], axis=1),
                      np.linalg.norm(V[E[:, 0]] - curve[-1], axis=1))
    em &= ends > canon.get("jaw_trim", 0.008)
    me.edges.foreach_set("use_freestyle_mark", em.tolist())
    me.update()
    H.jaw_edges = em
    jv = np.unique(E[em].ravel())
    H.jaw_pts = V[jv][np.argsort(V[jv][:, 0])]


def _boundary_loops(faces):
    from collections import Counter, defaultdict
    cnt = Counter()
    for f in faces:
        for k in range(len(f)):
            a, b = f[k], f[(k + 1) % len(f)]
            cnt[(min(a, b), max(a, b))] += 1
    adj = defaultdict(list)
    for (a, b), c in cnt.items():
        if c == 1:
            adj[a].append(b)
            adj[b].append(a)
    loops, seen = [], set()
    for s0 in list(adj):
        if s0 in seen:
            continue
        loop = [s0]
        seen.add(s0)
        prev, cur = None, s0
        while True:
            nxt = [x for x in adj[cur] if x != prev and x not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            loop.append(cur)
            seen.add(cur)
        loops.append(loop)
    return loops


_POCKET = None


def pocket_mask():
    """Faces of the MakeHuman eye-pocket lining.  The base mesh topology never changes, so the
    lining is found once on the neutral male (where it is clean) and reused for every face."""
    global _POCKET
    if _POCKET is not None:
        return _POCKET
    v, f, j = mh.body_verts(1.0, 30.0)
    q = v[f]
    fc = q.mean(1)
    fn = np.cross(q[:, 2] - q[:, 0], q[:, 3] - q[:, 1])
    drop = np.zeros(len(f), bool)
    for c in (j["joint-l-eye"], j["joint-r-eye"]):
        d = fc - c
        r = np.linalg.norm(d, axis=1)
        cosang = np.einsum("ij,ij->i", d, fn) / np.maximum(r * np.linalg.norm(fn, axis=1), 1e-12)
        drop |= (r < 0.021) & (cosang < -0.5)
    _POCKET = drop
    return drop


def pocket_pad(pocket, n):
    out = np.zeros(n, bool)
    out[:len(pocket)] = pocket
    return out


def close_eyes(V, faces, centers, R):
    """Replace the MakeHuman eye pockets by a smooth closed lid surface.

    The pocket lining (behind the eyeball's front) is deleted, the hole is capped with rings
    lying on the eyeball sphere, and lids + cap are Laplacian-smoothed into one calm dome: the
    painted eye (face.py) then sits on a clean surface that makes no stray Freestyle lines."""
    V = np.asarray(V, np.float64)
    region = np.zeros(len(V), bool)
    for c in centers:
        region |= np.linalg.norm((V - c) / np.array([1.0, 1.4, 1.0]), axis=1) < 0.019
    keepf = list(faces)
    alive = np.zeros(len(V), bool)
    for f in keepf:
        alive[list(f)] = True
    pocket = ~alive
    faces = keepf
    all_loops = _boundary_loops(faces)
    loops = [lp for lp in all_loops if len(lp) > 20]
    newV = [V]
    nV = len(V)
    nV0 = nV
    free = list(np.nonzero(region & ~pocket)[0])
    # small leftover holes (canthus folds): fan-fill them
    directed = set()
    for f in faces:
        for k in range(len(f)):
            directed.add((f[k], f[(k + 1) % len(f)]))
    for lp in [lp for lp in all_loops if len(lp) <= 20]:
        m = V[lp].mean(0)
        if len(lp) >= 3 and min(np.linalg.norm(m - c) for c in centers) < 0.03:
            lp2 = list(lp)
            if (lp2[0], lp2[1]) in directed:
                lp2 = lp2[::-1]
            newV.append(m[None])
            for i in range(len(lp2)):
                faces.append((lp2[i], lp2[(i + 1) % len(lp2)], nV))
            free.append(nV)
            nV += 1
    V = np.vstack(newV)
    newV = [V]
    for c in centers:
        # the loop around this eye
        best = None
        bd = 0.02
        for lp in loops:
            dd = np.linalg.norm(V[lp].mean(0) - c)
            if dd < bd:
                best, bd = lp, dd
        if best is None:
            continue
        lp = list(best)
        directed = set()
        for f in faces:
            for k in range(len(f)):
                directed.add((f[k], f[(k + 1) % len(f)]))
        if (lp[0], lp[1]) in directed:
            lp = lp[::-1]
        P = V[lp]
        cen = P.mean(0)
        n = len(lp)
        rings = 4
        base = nV
        pts = []
        for k in range(1, rings + 1):
            f = 1.0 - k / (rings + 0.6)
            Q = cen + (P - cen) * f
            dx, dz = Q[:, 0] - c[0], Q[:, 2] - c[2]
            Q[:, 1] = c[1] - np.sqrt(np.clip(R * R - dx * dx - dz * dz, 1e-8, None))
            pts.append(Q)
        ctr = np.array([cen[0], c[1] - R, cen[2]])
        allp = np.vstack(pts + [ctr[None]])
        newV.append(allp)
        idx_ring = [lp] + [list(range(base + k * n, base + (k + 1) * n)) for k in range(rings)]
        for k in range(rings):
            a, b = idx_ring[k], idx_ring[k + 1]
            for i in range(n):
                i1 = (i + 1) % n
                faces.append((a[i], a[i1], b[i1], b[i]))
                # loop runs opposite to the lid faces' edge direction -> outward normals
        cidx = base + rings * n
        last = idx_ring[-1]
        for i in range(n):
            faces.append((last[i], last[(i + 1) % n], cidx))
        free.extend(range(base, base + rings * n + 1))
        nV += len(allp)
    V = np.vstack(newV)
    # keep the winding consistent with the neighbouring lid faces (outward normals)
    # (cap faces were appended loop->inner; flip them if they face inward)
    nb = geo.neighbours(len(V), faces)
    mask = np.zeros(len(V), bool)
    mask[np.array(free, np.int64)] = True
    Vs = geo.smooth_field(nb, V, mask, iters=40)
    # fade the smoothing out toward the region edge (no kink where it stops)
    w = np.zeros(len(V))
    for c in centers:
        r = np.linalg.norm((V - c) / np.array([1.0, 1.4, 1.0]), axis=1)
        w = np.maximum(w, np.clip((0.019 - r) / 0.005, 0, 1))
    cap = np.zeros(len(V), bool)
    cap[nV0:] = True
    w = np.where(cap | pocket_pad(pocket, len(V)), 1.0, w)
    w = w * w * (3 - 2 * w)
    V = V + (Vs - V) * w[:, None]
    # drop unused vertices (deleted pocket)
    used = np.unique(np.concatenate([np.array(f) for f in faces]))
    remap = -np.ones(len(V), np.int64)
    remap[used] = np.arange(len(used))
    faces = [tuple(int(remap[i]) for i in f) for f in faces]
    return V[used], faces


def landmarks(H):
    """Midline profile by ray casting (robust to any target mix)."""
    s = H.surf
    ez = H.eye_z
    zs = np.arange(ez - 0.16, ez + 0.14, 0.0005)
    ys = np.array([s.hit(0.0, z)[0][1] for z in zs])
    lm = {}

    def front(z0, z1):
        m = (zs >= z0) & (zs <= z1)
        i = np.argmin(np.where(m, ys, 9))
        return np.array([0.0, ys[i], zs[i]])

    def back(z0, z1):
        m = (zs >= z0) & (zs <= z1)
        i = np.argmax(np.where(m, ys, -9))
        return np.array([0.0, ys[i], zs[i]])

    lm["nose_tip"] = front(ez - 0.06, ez - 0.02)
    nt = lm["nose_tip"]
    lm["nasion"] = back(ez - 0.012, ez + 0.012)
    lm["subnasale"] = back(nt[2] - 0.022, nt[2] - 0.006)
    sn = lm["subnasale"]
    lm["upper_lip"] = front(sn[2] - 0.02, sn[2] - 0.004)
    ul = lm["upper_lip"]
    lm["mouth"] = back(ul[2] - 0.012, ul[2] - 0.002)
    mo = lm["mouth"]
    lm["lower_lip"] = front(mo[2] - 0.016, mo[2] - 0.002)
    ll = lm["lower_lip"]
    lm["chin_dent"] = back(ll[2] - 0.022, ll[2] - 0.006)
    lm["chin"] = front(lm["chin_dent"][2] - 0.03, lm["chin_dent"][2] - 0.004)
    # menton: lowest point of the face on the midline (ray down from in front of the chin)
    from mathutils import Vector
    ch = lm["chin"]
    loc = s.bvh.ray_cast(Vector((0, ch[1] + 0.012, ch[2] - 0.08)), Vector((0, 0, 1)))[0]
    lm["menton"] = np.array(loc) if loc is not None else ch - np.array([0, -0.01, 0.02])
    lm["forehead"] = front(ez + 0.03, ez + 0.06)
    top = s.bvh.ray_cast(Vector((0, -0.03, ez + 0.4)), Vector((0, 0, -1)))[0]
    lm["crown"] = np.array(top)
    lm["eye_l"], lm["eye_r"] = H.eye_l, H.eye_r
    return lm
