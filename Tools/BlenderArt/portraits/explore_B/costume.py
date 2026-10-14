"""Period costume builders fitted to the MakeHuman bust: garment shells, lamellar armour,
pauldrons, crossed-collar robes, helmets, hats, hairpins, fur trims, chest mirror.

Fitting strategy
    * ``body_shell`` offsets the (arms-down) MakeHuman torso along its normals, irons the anatomy
      out with Laplacian smoothing and pushes it back outside the body: every garment layer starts
      from this shell, so costumes fit any body the identity sliders make.
    * Ornament (plates, lames, collar bands, trims) is placed on a shell by ray casting in
      cylindrical coordinates around the body axis.

Each builder returns Blender objects with material slots already filled from the ``mats`` dict
(see :func:`shading.costume_materials`).  Coordinates: Blender metres, face towards -Y.
"""

import math

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import meshutil as MU


def _norm(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)


def _ss(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


class Shell:
    """A smooth closed-ish surface around the body with a BVH for ray casts."""

    def __init__(self, V, Q, name="Shell"):
        self.V, self.Q = V.astype(np.float32), Q
        self.name = name
        tris = []
        for q in Q:
            if q[3] == q[2]:
                tris.append((int(q[0]), int(q[1]), int(q[2])))
            else:
                tris.append((int(q[0]), int(q[1]), int(q[2])))
                tris.append((int(q[0]), int(q[2]), int(q[3])))
        self.bvh = BVHTree.FromPolygons(self.V.tolist(), tris, all_triangles=True)
        self.N = MU.vertex_normals(self.V, self.Q)

    def hit(self, origin_axis, direction, far=0.6):
        """Ray from far outside towards the axis point; first hit = outer surface."""
        d = Vector(direction).normalized()
        o = Vector(origin_axis) + d * far
        loc, nor, idx, dist = self.bvh.ray_cast(o, -d, far * 1.5)
        if loc is None:
            return None, None
        # reject hits on the far side of the axis (the ray missed this side and went through)
        rel = loc - Vector(origin_axis)
        if rel.x * d.x + rel.y * d.y < 0:
            return None, None
        if nor.dot(d) < 0:
            nor = -nor
        return np.array(loc, np.float32), np.array(nor, np.float32)

    def obj(self, mats, col=None, solidify=0.0, subdiv=1, uv=None, name=None, mat_index=None):
        if uv is None:
            # cylindrical UVs in metres (arc length around the body axis, height): fabric
            # patterns get a physical scale on every garment
            cy = float(self.V[:, 1].mean())
            th = np.arctan2(self.V[:, 0], -(self.V[:, 1] - cy))
            uv = np.stack([th * 0.16, self.V[:, 2]], 1).astype(np.float32)
        ob = MU.make_mesh(name or self.name, self.V, self.Q, col=col, mats=mats, uv=uv,
                          mat_index=mat_index)
        if solidify:
            m = ob.modifiers.new("Solid", "SOLIDIFY")
            m.thickness = solidify
            m.offset = -1.0
            m.use_even_offset = True
        if subdiv:
            m = ob.modifiers.new("Subdiv", "SUBSURF")
            m.levels = 1
            m.render_levels = subdiv
        return ob


def body_shell(bust, body_surf, lm, thickness=0.018, neck_z=None, front_dip=0.02, smooth=4,
               rounds=4, name="Shell", min_z=None, keep_fn=None, widen=0.0):
    """Garment base shell from the bust mesh (non-subdivided, world coords)."""
    V, F = MU.mesh_arrays(bust, evaluated=False)
    Q = MU.faces_to_quads(F)
    N = MU.vertex_normals(V, Q)
    nz = neck_z if neck_z is not None else float(lm["j_neck"][2]) - 0.018
    cy = float(lm["j_neck"][1])
    th = np.arctan2(V[:, 0], -(V[:, 1] - cy))  # 0 = front
    zc = nz - front_dip * np.clip(np.cos(th), 0, 1) ** 2
    ok_v = V[:, 2] < zc
    if min_z is not None:
        ok_v &= V[:, 2] > min_z
    if keep_fn is not None:
        ok_v &= keep_fn(V)
    keep = ok_v[Q].all(1)
    Vs, Qs, used = MU.submesh(V, Q, keep)
    Ns = N[used]
    Vo = Vs + Ns * thickness
    if widen:
        Vo[:, 0] *= 1.0 + widen * _ss(nz - 0.02, nz - 0.12, Vo[:, 2])
    rows, cols = MU.adjacency(Qs, len(Vo))
    bnd = MU.boundary_verts(Qs)
    for _ in range(rounds):
        Vo = MU.laplacian(Vo, rows, cols, iters=smooth, lam=0.5)
        Vo = body_surf.push_out(Vo, thickness * 0.75, max_dist=0.15)
    return Shell(Vo, Qs, name)


# ---------------------------------------------------------------------------------------------
# lamellar plates
# ---------------------------------------------------------------------------------------------
def _plate_grid(w, h, nu=4, nv=6, round_bottom=0.45, dome=0.0015, bend=0.0):
    """Local plate vertices (nu*nv, 3) in (u right, v up, n out) and quads; rounded bottom."""
    us = np.linspace(-0.5, 0.5, nu)
    vs = np.linspace(-0.5, 0.5, nv)
    P = []
    for j, v in enumerate(vs):
        for i, u in enumerate(us):
            uu = u
            if v < 0:
                t = (-v / 0.5)
                uu = u * (1 - round_bottom * t ** 3)
            n = dome * (1 - (2 * u) ** 2) * (1 - 0.3 * (2 * v) ** 2) + bend * (0.5 - v)
            P.append((uu * w, v * h, n))
    Fq = []
    for j in range(nv - 1):
        for i in range(nu - 1):
            a = j * nu + i
            Fq.append((a, a + 1, a + nu + 1, a + nu))
    uv = np.array([((i / (nu - 1)), (j / (nv - 1))) for j in range(nv) for i in range(nu)], np.float32)
    return np.array(P, np.float32), np.array(Fq, np.int32), uv


def lamellar(shell, axis_xy, z_rows, theta_range, plate_w=0.021, plate_h=0.052, overlap_u=0.42,
             row_out=0.0016, tilt=0.004, name="Lamellar", mats=None, col=None, rng=None,
             extra_out=0.0, mat_index_fn=None, scale_fn=None):
    """Rows of overlapping plates on ``shell``.  ``z_rows`` top-to-bottom row centre heights;
    ``theta_range`` (deg) around the vertical axis through ``axis_xy`` (0 = front, + = left)."""
    rng = rng or np.random.default_rng(0)
    gV, gF, guv = _plate_grid(plate_w, plate_h, dome=0.0002, round_bottom=0.3)
    Vall, Fall, UVall, MI, RID = [], [], [], [], []
    off = 0
    nrows = len(z_rows)
    for k, z in enumerate(z_rows):
        t0, t1 = theta_range
        # walk along the row at constant arc spacing
        th = math.radians(t0)
        stagger = 0.5 if k % 2 else 0.0
        first = True
        while th < math.radians(t1):
            d = (math.sin(th), -math.cos(th), 0.0)
            p, n = shell.hit((axis_xy[0], axis_xy[1], z), d)
            if p is None:
                th += 0.05
                continue
            r = math.hypot(p[0] - axis_xy[0], p[1] - axis_xy[1])
            sw, sh = (scale_fn(p) if scale_fn else (1.0, 1.0))
            dth = plate_w * sw * (1 - overlap_u) / max(r, 0.03)
            if first:
                th += dth * stagger
                first = False
                continue
            n = _norm(n)
            up = np.array([0, 0, 1], np.float32)
            up = _norm(up - n * np.dot(up, n))
            right = np.cross(up, n)
            # hand-made irregularity: a few degrees of twist per plate
            a = rng.normal() * 0.035
            up, right = up * math.cos(a) + right * math.sin(a), right * math.cos(a) - up * math.sin(a)
            # plates overlap to the right: alternate tiny depth so neighbours do not z-fight
            ln = gV.copy()
            ln[:, 0] *= sw
            ln[:, 1] *= sh
            depth = (extra_out + row_out * (nrows - k) + 0.0004 * ((len(Vall)) % 2)
                     + tilt * (0.5 - (gV[:, 1] / plate_h)) ** 2 * 0.5 + tilt * np.clip(-gV[:, 1] / plate_h, 0, 1))
            pv = p[None, :] + right[None, :] * ln[:, 0:1] + up[None, :] * ln[:, 1:2] + n[None, :] * (ln[:, 2:3] + depth[:, None])
            Vall.append(pv)
            Fall.append(gF + off)
            UVall.append(guv + np.array([rng.random() * 7, k * 3.0], np.float32) * 0)
            MI.append(np.full(len(gF), mat_index_fn(p) if mat_index_fn else 0, np.int32))
            RID.append(np.full(len(pv), rng.random(), np.float32))
            off += len(pv)
            th += dth
    if not Vall:
        return None
    V = np.concatenate(Vall)
    Fq = np.concatenate(Fall)
    ob = MU.make_mesh(name, V, Fq, col=col, mats=mats, uv=np.concatenate(UVall),
                      mat_index=np.concatenate(MI), attrs={"plate_rand": np.concatenate(RID)})
    m = ob.modifiers.new("Solid", "SOLIDIFY")
    m.thickness = 0.0018
    m.offset = -1
    m.use_rim = True
    b = ob.modifiers.new("Bevel", "BEVEL")
    b.width = 0.0006
    b.segments = 1
    b.limit_method = "ANGLE"
    return ob


def lacing_rows(shell, axis_xy, z_list, theta_range, out=0.006, width=0.004, name="Lacing",
                mats=None, col=None, wobble=0.0006, rng=None):
    """Horizontal cord bands following the shell (between lamellar rows)."""
    rng = rng or np.random.default_rng(1)
    V, F = [], []
    off = 0
    for z in z_list:
        pts, nors = [], []
        for th in np.radians(np.arange(theta_range[0], theta_range[1], 2.0)):
            p, n = shell.hit((axis_xy[0], axis_xy[1], z), (math.sin(th), -math.cos(th), 0))
            if p is not None:
                pts.append(p)
                nors.append(_norm(n))
        if len(pts) < 2:
            continue
        pts = np.array(pts)
        nors = np.array(nors)
        k = len(pts)
        zz = np.array([0, 0, 1], np.float32)
        ph = np.arange(k) * 1.7
        top = pts + nors * (out + wobble * np.sin(ph)[:, None]) + zz * width / 2
        bot = pts + nors * (out + wobble * np.cos(ph)[:, None]) - zz * width / 2
        V += [top, bot]
        for i in range(k - 1):
            F.append((off + i, off + i + 1, off + k + i + 1, off + k + i))
        off += 2 * k
    if not V:
        return None
    ob = MU.make_mesh(name, np.concatenate(V), F, col=col, mats=mats)
    m = ob.modifiers.new("Solid", "SOLIDIFY")
    m.thickness = 0.0015
    return ob


# ---------------------------------------------------------------------------------------------
# banded surfaces (collars, trims, pauldron lames)
# ---------------------------------------------------------------------------------------------
def ribbon(path, normals, width, up=None, name="Ribbon", mats=None, col=None, thickness=0.002,
           subdiv=1, twist_out=0.0, rows=2, uv_len=True):
    """Flat band along ``path`` (K,3) lying on a surface with ``normals`` (K,3); ``width`` scalar or
    (K,); band extends along ``up`` (K,3) (defaults to binormal).  Returns object."""
    path = np.asarray(path, np.float32)
    nrm = _norm(np.asarray(normals, np.float32))
    K = len(path)
    tan = np.gradient(path, axis=0)
    tan = _norm(tan)
    if up is None:
        up = _norm(np.cross(nrm, tan))
    up = _norm(np.asarray(up, np.float32))
    w = np.broadcast_to(np.asarray(width, np.float32), (K,))
    V, F, UV = [], [], []
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))])
    for r in range(rows + 1):
        f = r / rows
        V.append(path + up * (w * (f - 0.5))[:, None] + nrm * (twist_out * f))
        UV.append(np.stack([s / max(s[-1], 1e-6), np.full(K, f)], 1))
    V = np.concatenate(V)
    UV = np.concatenate(UV)
    for r in range(rows):
        for i in range(K - 1):
            a = r * K + i
            F.append((a, a + 1, a + K + 1, a + K))
    ob = MU.make_mesh(name, V, F, col=col, mats=mats, uv=UV)
    if thickness:
        m = ob.modifiers.new("Solid", "SOLIDIFY")
        m.thickness = thickness
        m.offset = -1
    if subdiv:
        m = ob.modifiers.new("Subdiv", "SUBSURF")
        m.levels = 1
        m.render_levels = subdiv
    return ob


def shell_curve(shell, axis_xy, z_fn, theta_deg, out=0.0):
    """Sample the shell along theta with height z_fn(theta) -> (pts, normals)."""
    P, N = [], []
    for t in theta_deg:
        th = math.radians(t)
        z = z_fn(t)
        p, n = shell.hit((axis_xy[0], axis_xy[1], z), (math.sin(th), -math.cos(th), 0))
        if p is not None:
            P.append(p + _norm(n) * out)
            N.append(_norm(n))
    return np.array(P, np.float32), np.array(N, np.float32)


def pauldrons(shell, lm, mats, col=None, lames=4, lame_h=0.030, overlap=0.35, flare=0.006,
              span=(25, 155), name="Pauldron", sides=(1, -1), start_drop=0.0, out0=0.010):
    """Shoulder guards: overlapping curved lames hugging the shoulder cap (lowest lame outermost
    at the bottom edge so each lame casts a shadow line on the next)."""
    objs = []
    for side in sides:
        sh = np.asarray(lm["j_l-shoulder" if side > 0 else "j_r-shoulder"], np.float32)
        # axis of the upper arm (arms lowered): slightly outward-down
        top_z = sh[2] + 0.060 - start_drop
        for k in range(lames):
            z0 = top_z - k * lame_h * (1 - overlap)
            # the lame is an arc around the shoulder, sampled by casting rays in the plane
            # perpendicular to the (approx vertical) arm axis around a centre inside the arm
            centre = sh + np.array([side * -0.01, 0.0, 0.0], np.float32)
            P0, P1 = [], []
            angs = np.radians(np.linspace(span[0], span[1], 28))
            for a in angs:
                # a = 0 front, 90 outward side, 180 back
                d = np.array([side * math.sin(a), -math.cos(a), 0.0], np.float32)
                top_pts = []
                for zz in (z0, z0 - lame_h):
                    p, n = shell.hit((centre[0], centre[1], zz), d, far=0.4)
                    if p is None:
                        p, n = centre + d * 0.06, d
                    top_pts.append((p, _norm(n)))
                (pa, na), (pb, nb) = top_pts
                o = out0 + 0.004 * k
                P0.append(pa + na * o)
                P1.append(pb + nb * (o + flare))
            P0, P1 = np.array(P0), np.array(P1)
            K = len(P0)
            rows = 4
            V = []
            UV = []
            for r in range(rows + 1):
                f = r / rows
                bulge = 0.004 * math.sin(math.pi * f)
                mid = P0 + (P1 - P0) * f
                nn = _norm(np.cross(np.gradient(mid, axis=0), (P1 - P0)))
                if side < 0:
                    nn = -nn
                V.append(mid + nn * bulge)
                UV.append(np.stack([np.linspace(0, 1, K), np.full(K, 1 - f)], 1))
            V = np.concatenate(V)
            F = [(r * K + i, r * K + i + 1, (r + 1) * K + i + 1, (r + 1) * K + i)
                 for r in range(rows) for i in range(K - 1)]
            ob = MU.make_mesh("%s_%s%d" % (name, "l" if side > 0 else "r", k), V, F, col=col,
                              mats=mats, uv=np.concatenate(UV))
            m = ob.modifiers.new("Solid", "SOLIDIFY")
            m.thickness = 0.0025
            m.offset = 1 if side > 0 else -1
            m.use_rim = True
            s = ob.modifiers.new("Subdiv", "SUBSURF")
            s.levels = 1
            s.render_levels = 2
            objs.append(ob)
    return objs


# ---------------------------------------------------------------------------------------------
# helmet
# ---------------------------------------------------------------------------------------------
def head_extents(bust, lm):
    V, F = MU.mesh_arrays(bust)
    sel = V[:, 2] > float(lm["brow_mid"][2]) - 0.01
    H = V[sel]
    return H.min(0), H.max(0)


def helmet(bust, lm, mats, col=None, clearance=0.016, rim_front=0.024, rim_side=0.02,
           rim_back=-0.02, peak=0.035, ribs=8, name="Helmet", neck_guard=True, rng=None,
           guard_rows=3, crest=True):
    """Chinese iron bowl helmet: ellipsoid bowl with a raised point, bronze rim band, ribs, a
    brow plaque, a finial with a tassel socket and a lamellar neck guard.

    mats: dict with keys iron, bronze, gold, leather, lacing.
    Returns (objects, info) where info has 'finial' (tassel root) and 'rim' heights."""
    lo, hi = head_extents(bust, lm)
    c = (lo + hi) / 2
    rx = (hi[0] - lo[0]) / 2 + clearance
    ry = (hi[1] - lo[1]) / 2 + clearance
    brow = float(lm["brow_mid"][2])
    z0 = brow + 0.005
    rz = hi[2] - z0 + clearance + 0.004
    cy = c[1] + 0.004

    def rim_z(th):  # th: 0 front, pi back
        f = (1 + math.cos(th)) / 2   # 1 front, 0 back
        side = math.sin(th) ** 2
        return z0 + rim_front * f + rim_side * side * 0.8 + rim_back * (1 - f) * (1 - side)

    NU, NV = 64, 22
    V, UV = [], []
    for j in range(NV):
        s = j / (NV - 1)
        for i in range(NU):
            th = 2 * math.pi * i / NU
            zr = rim_z(th)
            # profile: from the rim up to the crown; p in [0,1] latitude
            lat = s * math.pi / 2
            r = math.cos(lat) ** 0.85
            ztop = z0 + rz
            z = zr + (ztop - zr) * math.sin(lat) ** 1.1 + peak * max(0.0, s - 0.55) ** 2 / 0.2
            x = c[0] + rx * r * math.sin(th)
            y = cy - ry * r * math.cos(th)
            V.append((x, y, z))
            UV.append((i / NU, s))
    F = []
    for j in range(NV - 1):
        for i in range(NU):
            a = j * NU + i
            b = j * NU + (i + 1) % NU
            F.append((a, b, b + NU, a + NU))
    bowl = MU.make_mesh(name + "_bowl", np.array(V), F, col=col, mats=[mats["iron"]], uv=np.array(UV))
    m = bowl.modifiers.new("Solid", "SOLIDIFY")
    m.thickness = 0.003
    m.offset = 1
    s = bowl.modifiers.new("Subdiv", "SUBSURF")
    s.levels = 1
    s.render_levels = 2
    objs = [bowl]
    Vb = np.array(V, np.float32).reshape(NV, NU, 3)
    # rim band (bronze) - a ribbon around the rim, slightly proud
    ring = Vb[0]
    nr = _norm(np.stack([ring[:, 0] - c[0], ring[:, 1] - cy, np.zeros(NU)], 1))
    ring2 = np.concatenate([ring, ring[:1]])
    nr2 = np.concatenate([nr, nr[:1]])
    up = np.tile(np.array([0, 0, 1], np.float32), (len(ring2), 1))
    objs.append(ribbon(ring2 + nr2 * 0.0035 + up * 0.009, nr2, 0.02, up=up, name=name + "_rim",
                       mats=[mats["bronze"]], col=col, thickness=0.003, rows=3))
    # ribs from rim to crown
    for i in range(ribs):
        iu = int(round(i * NU / ribs)) % NU
        path = Vb[:, iu]
        n = _norm(path - np.array([c[0], cy, z0], np.float32))
        path = path + n * 0.0035
        tang = _norm(np.gradient(path, axis=0))
        side = _norm(np.cross(n, tang))
        objs.append(ribbon(path[:-2], n[:-2], 0.007, up=side[:-2], name=name + "_rib%d" % i,
                           mats=[mats["bronze"]], col=col, thickness=0.0025, rows=2))
    # finial (stacked turned profile) at the crown
    top = Vb[-1].mean(0)
    prof = [(0.0, 0.000), (0.016, 0.000), (0.018, 0.005), (0.010, 0.009), (0.006, 0.016),
            (0.010, 0.022), (0.012, 0.026), (0.004, 0.030), (0.0025, 0.046), (0.0, 0.050)]
    objs.append(lathe(prof, top, name + "_finial", [mats["gold"]], col))
    # brow plaque
    front = Vb[0, 0]
    objs.append(plaque(front + np.array([0, -0.005, 0.024], np.float32), name + "_plaque",
                       [mats["gold"]], col, w=0.026, h=0.032))
    info = {"finial": top + np.array([0, 0, 0.027], np.float32), "top": top, "c": c, "rx": rx,
            "ry": ry, "rim": Vb[0], "cy": cy}
    if neck_guard:
        objs += neck_guard_lamellar(Vb[0], c, cy, mats, col, rows=guard_rows, rng=rng, name=name)
    return objs, info


def lathe(profile, base, name, mats, col, seg=24):
    V, F = [], []
    n = len(profile)
    for j, (r, z) in enumerate(profile):
        for i in range(seg):
            a = 2 * math.pi * i / seg
            V.append((base[0] + r * math.cos(a), base[1] + r * math.sin(a), base[2] + z))
    for j in range(n - 1):
        for i in range(seg):
            a = j * seg + i
            b = j * seg + (i + 1) % seg
            F.append((a, b, b + seg, a + seg))
    ob = MU.make_mesh(name, np.array(V), F, col=col, mats=mats)
    s = ob.modifiers.new("Subdiv", "SUBSURF")
    s.levels = 1
    s.render_levels = 1
    return ob


def plaque(center, name, mats, col, w=0.034, h=0.04):
    """Flame/cloud brow plaque: a pointed shield outline with a raised border, facing -Y."""
    K = 40
    pts = []
    for i in range(K):
        t = i / K * 2 * math.pi
        x = math.sin(t)
        z = -math.cos(t)
        # pointed top, rounded bottom lobes
        sh = 1.0 + 0.35 * max(0.0, -z) ** 3
        pts.append((x * w / 2 * (1 - 0.55 * max(0.0, z) ** 1.5), z * h / 2 * sh))
    V = [(center[0], center[1] - 0.004, center[2])]
    for (x, z) in pts:
        V.append((center[0] + x, center[1], center[2] + z))
    for (x, z) in pts:
        V.append((center[0] + x * 0.8, center[1] - 0.002, center[2] + z * 0.8))
    F = []
    for i in range(K):
        a, b = 1 + i, 1 + (i + 1) % K
        a2, b2 = 1 + K + i, 1 + K + (i + 1) % K
        F.append((a, b, b2, a2))
        F.append((0, a2, b2))
    ob = MU.make_mesh(name, np.array(V), F, col=col, mats=mats)
    m = ob.modifiers.new("Solid", "SOLIDIFY")
    m.thickness = 0.002
    return ob


def neck_guard_lamellar(rim, c, cy, mats, col, rows=3, rng=None, name="Helmet", drop=0.085,
                        flare=0.022, theta=(62, 298)):
    """Flared skirt of plates hanging from the helmet rim at the sides and back."""
    rng = rng or np.random.default_rng(2)
    NU = len(rim)
    objs = []
    # skirt surface
    V, F = [], []
    NV = 6
    ths = np.arange(NU)
    for j in range(NV):
        f = j / (NV - 1)
        for i in range(NU):
            p = rim[i]
            d = _norm(np.array([p[0] - c[0], p[1] - cy, 0.0], np.float32))
            V.append(p + d * (0.004 + flare * f ** 1.3) + np.array([0, 0, -drop * f], np.float32))
    for j in range(NV - 1):
        for i in range(NU):
            a = j * NU + i
            b = j * NU + (i + 1) % NU
            F.append((a, b, b + NU, a + NU))
    V = np.array(V, np.float32)
    sk = Shell(V, MU.faces_to_quads(F), name + "_skirt")
    zt = rim[:, 2].mean()
    plate_h = drop / rows * 1.45
    z_rows = [zt - plate_h * 0.45 - k * drop / rows for k in range(rows)]
    pl = lamellar(sk, (c[0], cy), z_rows, theta, plate_w=0.02, plate_h=plate_h, overlap_u=0.35,
                  name=name + "_guard", mats=[mats.get("guard", mats["iron"])], col=col, rng=rng, row_out=0.002,
                  tilt=0.003)
    if pl is not None:
        objs.append(pl)
    return objs


# ---------------------------------------------------------------------------------------------
# misc ornaments
# ---------------------------------------------------------------------------------------------
def disc(center, normal, radius, name, mats, col, dome=0.006, rings=6, seg=48, rim=0.004):
    """Convex round plate (chest mirror / boss) with a raised rim."""
    n = _norm(np.asarray(normal, np.float32))
    up = np.array([0, 0, 1], np.float32)
    u = _norm(np.cross(up, n))
    v = np.cross(n, u)
    V = [tuple(center + n * dome)]
    F = []
    for j in range(1, rings + 1):
        r = radius * j / rings
        h = dome * (1 - (j / rings) ** 2)
        if j == rings - 1:
            h += rim * 0.3
        if j == rings:
            h += rim
        for i in range(seg):
            a = 2 * math.pi * i / seg
            V.append(tuple(center + n * h + (u * math.cos(a) + v * math.sin(a)) * r))
    for i in range(seg):
        F.append((0, 1 + i, 1 + (i + 1) % seg))
    for j in range(rings - 1):
        for i in range(seg):
            a = 1 + j * seg + i
            b = 1 + j * seg + (i + 1) % seg
            F.append((a, b, b + seg, a + seg))
    uv = np.array([(0.5, 0.5)] + [(0.5 + 0.5 * (j / rings) * math.cos(2 * math.pi * i / seg),
                                    0.5 + 0.5 * (j / rings) * math.sin(2 * math.pi * i / seg))
                                   for j in range(1, rings + 1) for i in range(seg)], np.float32)
    ob = MU.make_mesh(name, np.array(V), F, col=col, mats=mats, uv=uv)
    m = ob.modifiers.new("Solid", "SOLIDIFY")
    m.thickness = 0.003
    m.offset = -1
    return ob


# ---------------------------------------------------------------------------------------------
# robes
# ---------------------------------------------------------------------------------------------
def push_outside(shell, inner, gap=0.004):
    """Move ``shell`` vertices so they stay at least ``gap`` outside ``inner`` (in place)."""
    V = shell.V.copy()
    for i in range(len(V)):
        loc, nor, idx, d = inner.bvh.find_nearest(Vector(V[i]), 0.1)
        if loc is None:
            continue
        rel = Vector(V[i]) - loc
        # BVH face normals follow the (outward) winding of the body-derived shells
        h = rel.dot(nor)
        if h < gap:
            V[i] = np.array(loc + nor * gap, np.float32)
    shell.__init__(V, shell.Q, shell.name)
    return shell


def robe_folds(shell, lm, amount=0.004, count=9, seed=0):
    """Displace a robe shell with soft vertical drape folds that start under the collar and
    deepen towards the chest / arms (in place)."""
    rng = np.random.default_rng(seed)
    V = shell.V
    N = shell.N
    cy = float(lm["j_neck"][1])
    nz = float(lm["j_neck"][2])
    th = np.arctan2(V[:, 0], -(V[:, 1] - cy))
    ph = rng.random(3) * 6.28
    f = (np.sin(th * count + ph[0] + 2.0 * np.sin(V[:, 2] * 25 + ph[1]))
         + 0.5 * np.sin(th * count * 2.3 + ph[2]))
    depth = _ss(nz - 0.02, nz - 0.12, V[:, 2])
    shell.V = (V + N * (amount * f * depth)[:, None]).astype(np.float32)
    shell.__init__(shell.V, shell.Q, shell.name)
    return shell


def beads(path, normals, radius, name, mats, col, gap=1.05, big_every=0, big_scale=1.4):
    """String of spheres along a polyline (prayer beads)."""
    path = np.asarray(path, np.float32)
    seg = np.linalg.norm(np.diff(path, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    step = 2 * radius * gap
    centers = []
    nrm = []
    k = 0
    t = 0.0
    while t < s[-1]:
        i = np.searchsorted(s, t) - 1
        i = max(0, min(i, len(seg) - 1))
        f = (t - s[i]) / max(seg[i], 1e-9)
        centers.append(path[i] + (path[i + 1] - path[i]) * f)
        nrm.append(normals[i])
        r = radius * (big_scale if big_every and k % big_every == 0 else 1.0)
        t += step * (r / radius)
        k += 1
    V, F = [], []
    seg_u, seg_v = 10, 7
    for c, n in zip(centers, nrm):
        r = radius
        c = np.asarray(c) + np.asarray(n) * r * 0.9
        base = len(V)
        for j in range(seg_v + 1):
            phi = math.pi * j / seg_v
            for i in range(seg_u):
                a = 2 * math.pi * i / seg_u
                V.append((c[0] + r * math.sin(phi) * math.cos(a), c[1] + r * math.sin(phi) * math.sin(a),
                          c[2] + r * math.cos(phi)))
        for j in range(seg_v):
            for i in range(seg_u):
                a = base + j * seg_u + i
                b = base + j * seg_u + (i + 1) % seg_u
                F.append((a, b, b + seg_u, a + seg_u))
    if not V:
        return None
    return MU.make_mesh(name, np.array(V), F, col=col, mats=mats)


def crown(top, name, mats, col, scale=1.0, pin_mat=None, pin_len=0.11, tilt=0.0):
    """Small lotus / scholar's crown (xiaoguan) on the top-knot with a hairpin through it."""
    s = scale
    prof = [(0.0, 0.0), (0.019 * s, 0.0), (0.021 * s, 0.004 * s), (0.017 * s, 0.012 * s),
            (0.019 * s, 0.020 * s), (0.014 * s, 0.028 * s), (0.008 * s, 0.031 * s), (0.0, 0.032 * s)]
    objs = [lathe(prof, top, name, mats, col, seg=32)]
    # front ridge (lotus petal plates)
    if pin_mat is not None:
        a = np.array(top, np.float32) + np.array([0, 0, 0.015 * s], np.float32)
        d = np.array([1.0, 0.0, tilt], np.float32)
        d /= np.linalg.norm(d)
        p0, p1 = a - d * pin_len / 2, a + d * pin_len / 2
        objs += rod(p0, p1, 0.0018, name + "_pin", [pin_mat], col, head=0.0045)
    return objs


def rod(p0, p1, r, name, mats, col, seg=10, head=0.0, head_end=1):
    p0, p1 = np.asarray(p0, np.float32), np.asarray(p1, np.float32)
    d = p1 - p0
    L = float(np.linalg.norm(d))
    d /= L
    up = np.array([0, 0, 1.0], np.float32) if abs(d[2]) < 0.9 else np.array([1.0, 0, 0], np.float32)
    u = _norm(np.cross(d, up))
    v = np.cross(d, u)
    V, F = [], []
    rings = 8
    for j in range(rings + 1):
        t = j / rings
        rr = r * (1 - 0.6 * t ** 3) if head_end == 1 else r
        c = p0 + d * L * t
        for i in range(seg):
            a = 2 * math.pi * i / seg
            V.append(tuple(c + (u * math.cos(a) + v * math.sin(a)) * rr))
    for j in range(rings):
        for i in range(seg):
            a = j * seg + i
            b = j * seg + (i + 1) % seg
            F.append((a, b, b + seg, a + seg))
    objs = MU.make_mesh(name, np.array(V), F, col=col, mats=mats)
    if head > 0:
        sph = sphere(p0 - d * head * 0.6, head, name + "_head", mats, col)
        return [objs, sph]
    return [objs]


def sphere(c, r, name, mats, col, seg=14, rings=9, squash=1.0):
    V, F = [], []
    for j in range(rings + 1):
        phi = math.pi * j / rings
        for i in range(seg):
            a = 2 * math.pi * i / seg
            V.append((c[0] + r * math.sin(phi) * math.cos(a), c[1] + r * math.sin(phi) * math.sin(a),
                      c[2] + r * squash * math.cos(phi)))
    for j in range(rings):
        for i in range(seg):
            a = j * seg + i
            b = j * seg + (i + 1) % seg
            F.append((a, b, b + seg, a + seg))
    ob = MU.make_mesh(name, np.array(V), F, col=col, mats=mats)
    return ob


def flower(c, normal, r, name, mats, col, petals=5, center_mat=None):
    """Five-petal silk flower facing ``normal``."""
    n = _norm(np.asarray(normal, np.float32))
    up = np.array([0, 0, 1.0], np.float32)
    u = _norm(np.cross(n, up if abs(n[2]) < 0.9 else np.array([1.0, 0, 0], np.float32)))
    v = np.cross(n, u)
    V = [tuple(c + n * r * 0.25)]
    F = []
    K = petals * 8
    for i in range(K):
        a = 2 * math.pi * i / K
        rr = r * (0.55 + 0.45 * abs(math.cos(petals * a / 2)) ** 0.7)
        cup = r * 0.25 * (rr / r) ** 2
        V.append(tuple(c + (u * math.cos(a) + v * math.sin(a)) * rr + n * cup))
    for i in range(K):
        F.append((0, 1 + i, 1 + (i + 1) % K))
    ob = MU.make_mesh(name, np.array(V), F, col=col, mats=mats)
    m = ob.modifiers.new("Solid", "SOLIDIFY")
    m.thickness = 0.0008
    objs = [ob]
    if center_mat is not None:
        objs.append(sphere(c + n * r * 0.3, r * 0.22, name + "_c", [center_mat], col))
    return objs


def dangle(top, length, name, mats, col, n_beads=6, r=0.0018, sway=(0.0, 0.0)):
    """Bead strand hanging from ``top`` (buyao pendant)."""
    V = []
    out = []
    for k in range(n_beads):
        t = (k + 1) / n_beads
        p = np.asarray(top, np.float32) + np.array([sway[0] * t * t, sway[1] * t * t, -length * t], np.float32)
        out.append(sphere(p, r * (1.4 if k == n_beads - 1 else 1.0), "%s_%d" % (name, k), mats, col, seg=8, rings=6))
    return out
