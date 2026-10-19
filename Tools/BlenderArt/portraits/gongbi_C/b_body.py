"""Bust structure for gongbi_C: parametric head, ears, neck and clothed torso (Blender).

Coordinates (metres): the figure faces -Y (towards the camera at yaw 0), +Z up, +X is the
viewer's right in a frontal view.  The origin is the middle of the head at eye level.  Inside the
head rig (an empty that carries the head pose) the same axes hold; "fwd" below means -Y.

The head is a loft of superelliptic rings whose front / back / width follow the face canon
(三庭五眼: hairline-brow, brow-nose base, nose base-chin are equal thirds; the face is five eyes
wide).  It is deliberately *smooth*: no eyes, nose or mouth are modelled - those are drawn in 2D
by :mod:`face2d` on top of this surface, anchored to it through the height grid exported by
:mod:`b_stage`.  The head only gives the face its contour, its 分染 shading and its pose.
"""

import math

import numpy as np

import b_mesh as M

# =============================================================================================
# head
# =============================================================================================
#: neutral adult head knots: z, half width a, front F (fwd), back B (fwd; negative = behind)
HEAD_KNOTS = np.array([
    # z       a       F       B
    [0.1205, 0.020, 0.010, -0.040],
    [0.1150, 0.036, 0.034, -0.060],
    [0.1050, 0.052, 0.058, -0.082],
    [0.0850, 0.065, 0.075, -0.096],
    [0.0600, 0.071, 0.085, -0.102],
    [0.0350, 0.073, 0.090, -0.103],
    [0.0120, 0.0725, 0.0915, -0.100],
    [-0.0050, 0.0715, 0.0885, -0.095],
    [-0.0250, 0.0705, 0.0895, -0.085],
    [-0.0450, 0.0665, 0.0905, -0.070],
    [-0.0620, 0.0610, 0.0890, -0.055],
    [-0.0780, 0.0550, 0.0855, -0.033],
    [-0.0920, 0.0465, 0.0820, -0.004],
    [-0.1040, 0.0385, 0.0790, 0.022],
    [-0.1140, 0.0300, 0.0740, 0.040],
    [-0.1210, 0.0170, 0.0650, 0.050],
])
HEAD_TOP = 0.1235       # crown (pole)
#: the knots below the eye line are compressed so the chin sits one court (三庭) below the nose
#: base: hairline 0.075 / brow 0.015 / nose base -0.044 / chin -0.108
HEAD_KNOTS[:, 0] = np.where(HEAD_KNOTS[:, 0] < 0, HEAD_KNOTS[:, 0] * 0.893, HEAD_KNOTS[:, 0])
HEAD_CHIN = HEAD_KNOTS[-1, 0]


def head_params(p=None):
    """Fill defaults of the head shape parameters (see canon.HEAD)."""
    d = dict(scale=1.0, width=1.0, jaw=1.0, chin=1.0, chin_fwd=0.0, cheek=1.0, face_len=1.0,
             crown=1.0, n_face=2.25, n_back=2.05, temple=1.0, forehead=1.0)
    d.update(p or {})
    return d


def head_knots(hp):
    """Knots after the per-character shape parameters."""
    K = HEAD_KNOTS.copy()
    z = K[:, 0]
    lower = M.smoothstep(-0.02, -0.09, z)            # 0 above the cheek -> 1 at the jaw
    chinw = M.smoothstep(-0.085, -0.12, z)
    cheek = np.exp(-((z + 0.025) / 0.022) ** 2)
    temple = np.exp(-((z - 0.03) / 0.03) ** 2)
    K[:, 1] *= hp["width"] * (1 + (hp["jaw"] - 1) * lower) * (1 + (hp["chin"] - 1) * chinw)
    K[:, 1] *= (1 + (hp["cheek"] - 1) * cheek) * (1 + (hp["temple"] - 1) * temple)
    K[:, 2] += hp["chin_fwd"] * chinw
    # longer / shorter lower face: stretch z below the eye line
    K[:, 0] = np.where(z < 0, z * hp["face_len"], z * (1 + (hp["crown"] - 1) * M.smoothstep(0.03, 0.12, z)))
    K[:, 2] += (hp["forehead"] - 1) * 0.01 * M.smoothstep(0.0, 0.06, z) * (1 - M.smoothstep(0.08, 0.12, z))
    return K


class Head:
    """Analytic head surface (head-local coordinates, before the rig pose)."""

    def __init__(self, hp):
        self.hp = head_params(hp)
        self.K = head_knots(self.hp)
        s = self.hp["scale"]
        self.s = s
        self.top = HEAD_TOP * s * (1 + (self.hp["crown"] - 1) * 0.6)
        self.chin = self.K[-1, 0] * s

    def ring(self, z, alpha):
        """Points (x, y, z) on the ring at height z (scaled) for angles alpha (0 = front)."""
        s = self.s
        zz = np.clip(z / s, self.K[-1, 0], self.K[0, 0])
        a = M.pchip(self.K[::-1, 0], self.K[::-1, 1], zz) * s
        F = M.pchip(self.K[::-1, 0], self.K[::-1, 2], zz) * s
        B = M.pchip(self.K[::-1, 0], self.K[::-1, 3], zz) * s
        co = (F + B) / 2
        d = (F - B) / 2
        sn, cs = np.sin(alpha), np.cos(alpha)
        t = M.smoothstep(-0.35, 0.35, cs)
        n = self.hp["n_back"] + (self.hp["n_face"] - self.hp["n_back"]) * t
        x = a * M.spow(sn, 2.0 / n)
        fwd = co + d * M.spow(cs, 2.0 / n)
        return np.stack([x, -fwd, np.broadcast_to(z, np.shape(x))], -1)

    def grid(self, nz=84, na=104):
        zt = self.K[0, 0] * self.s
        zb = self.K[-1, 0] * self.s
        # denser rows on the face
        t = np.linspace(0, 1, nz)
        t = t + 0.08 * np.sin(t * math.pi * 2) / (2 * math.pi)
        z = zt + (zb - zt) * t
        a = np.linspace(-math.pi, math.pi, na, endpoint=False)
        P = np.stack([self.ring(zi, a) for zi in z], 0)
        return P, z, a


def build_head(hp, col, mat, rig):
    H = Head(hp)
    P, z, a = H.grid()
    obj = M.grid_object("Head", P, col, wrap=True, cap_top=True, cap_bottom=True, mat=mat,
                        parent=rig)
    # move the top cap's pole up to the crown so the skull is round, not flat
    me = obj.data
    nr, nc = P.shape[:2]
    top_i = nr * nc
    me.vertices[top_i].co.z = H.top
    me.vertices[top_i].co.y = 0.012 * H.s
    me.update()
    M.fix_normals(obj, (0, 0, 0))
    return obj, H


# =============================================================================================
# ears
# =============================================================================================
EAR_OUTLINE = np.array([
    (0.000, 0.020), (0.004, 0.028), (0.011, 0.033), (0.019, 0.032), (0.025, 0.026),
    (0.0285, 0.016), (0.029, 0.004), (0.026, -0.008), (0.021, -0.017), (0.016, -0.024),
    (0.012, -0.031), (0.006, -0.034), (0.001, -0.030), (-0.001, -0.022), (0.000, -0.010),
    (0.001, 0.004), (0.000, 0.012),
])
#: inner ear curves (ear plane coordinates) drawn by the 2D stage
EAR_CURVES = {
    "helix": [(0.006, 0.024), (0.013, 0.028), (0.020, 0.025), (0.024, 0.016), (0.0245, 0.004),
              (0.022, -0.007), (0.017, -0.015), (0.0135, -0.021)],
    "concha": [(0.008, 0.012), (0.014, 0.015), (0.018, 0.010), (0.0175, 0.000), (0.013, -0.008),
               (0.007, -0.010), (0.004, -0.006)],
}


def ear_frame(H, side, ep=None):
    """Origin, back, up, out axes of the ear on side (+1 = +X)."""
    ep = ep or {}
    s = H.s
    zc = (-0.017 + ep.get("dz", 0.0)) * s
    ring = H.ring(zc, np.array([side * math.pi / 2]))[0]
    origin = np.array([ring[0] - side * 0.003 * s, 0.006 * s, zc])
    tilt = math.radians(ep.get("tilt", 14.0))            # top leans back
    flare = math.radians(ep.get("flare", 18.0))          # stands out from the head
    up = np.array([0.0, math.sin(tilt), math.cos(tilt)])
    back = np.array([0.0, math.cos(tilt), -math.sin(tilt)])
    out = np.array([side * 1.0, 0.0, 0.0])
    back2 = back * math.cos(flare) + out * math.sin(flare)
    out2 = np.cross(up, back2) * side
    out2 = out2 * np.sign(out2[0] * side)
    return origin, back2, up, out2


def build_ear(H, side, col, mat, rig, ep=None):
    ep = ep or {}
    k = ep.get("size", 1.0) * H.s
    o, back, up, out = ear_frame(H, side, ep)
    ol = EAR_OUTLINE * k
    n = len(ol)
    th = 0.0075 * k
    c2 = ol.mean(0)
    verts = []
    for layer, off in ((0, th * 0.5), (1, -th * 0.5)):
        for (x, y) in ol:
            shrink = 0.85 if layer == 1 else 1.0
            px, py = c2 + (np.array([x, y]) - c2) * shrink
            verts.append(o + back * px + up * py + out * off)
    verts.append(o + back * c2[0] + up * c2[1] + out * (th * 0.15))
    verts.append(o + back * c2[0] + up * c2[1] - out * th * 0.5)
    ci_f, ci_b = 2 * n, 2 * n + 1
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces.append((ci_f, i, j) if side > 0 else (ci_f, j, i))
        faces.append((ci_b, n + j, n + i) if side > 0 else (ci_b, n + i, n + j))
        faces.append((i, n + i, n + j, j) if side > 0 else (j, n + j, n + i, i))
    obj = M.mesh_object("Ear%+d" % side, np.array(verts), faces, col, mat=mat, parent=rig)
    M.fix_normals(obj, o - out * 0.01)
    curves = {}
    for nm, pts in EAR_CURVES.items():
        p = np.array(pts) * k
        curves[nm] = [list(o + back * x + up * y + out * th * 0.55) for x, y in p]
    return obj, curves


# =============================================================================================
# neck and torso
# =============================================================================================
#: torso knots: z, half width a, front F, back B, superellipse exponent n (neutral man)
TORSO_KNOTS = np.array([
    [-0.135, 0.049, 0.033, -0.068, 2.0],
    [-0.148, 0.053, 0.038, -0.071, 2.0],
    [-0.162, 0.068, 0.052, -0.078, 2.1],
    [-0.180, 0.100, 0.068, -0.086, 2.4],
    [-0.200, 0.140, 0.080, -0.093, 2.8],
    [-0.222, 0.176, 0.092, -0.098, 3.2],
    [-0.250, 0.198, 0.102, -0.101, 3.5],
    [-0.290, 0.208, 0.110, -0.103, 3.6],
    [-0.340, 0.210, 0.115, -0.104, 3.6],
    [-0.420, 0.208, 0.118, -0.104, 3.6],
    [-0.520, 0.204, 0.118, -0.104, 3.6],
])


def body_params(p=None):
    d = dict(shoulder=1.0, chest=1.0, slope=1.0, neck=1.0, bulk=0.0, neck_len=1.0)
    d.update(p or {})
    return d


class Torso:
    """Clothed torso surface in bust coordinates: rings of superellipses."""

    def __init__(self, bp, head_scale=1.0):
        self.bp = body_params(bp)
        K = TORSO_KNOTS.copy()
        z = K[:, 0]
        sh = M.smoothstep(-0.17, -0.25, z)
        neck = 1 - M.smoothstep(-0.15, -0.19, z)
        K[:, 1] *= (1 + (self.bp["shoulder"] - 1) * sh) * (1 + (self.bp["neck"] - 1) * neck)
        K[:, 2] *= (1 + (self.bp["chest"] - 1) * sh)
        K[:, 1:4] += np.array([1, 1, -1]) * self.bp["bulk"] * sh[:, None]
        # slope > 1 drops the shoulders (ladies, elders)
        K[:, 0] = np.where(z < -0.15, -0.15 + (z + 0.15) * (1 + (self.bp["slope"] - 1) * (1 - M.smoothstep(-0.26, -0.36, z))), z)
        K[:, 0] -= (self.bp["neck_len"] - 1) * 0.03 * M.smoothstep(-0.12, -0.17, z)
        self.K = K
        self.top = K[0, 0]

    def coeffs(self, z):
        K = self.K
        zz = np.clip(z, K[-1, 0], K[0, 0])
        xs = K[::-1, 0]
        return [M.pchip(xs, K[::-1, i], zz) for i in (1, 2, 3, 4)]

    def point(self, alpha, z, off=0.0):
        """Surface point(s) at angle alpha (0 = front, +pi/2 = +X) and height z, pushed ``off``
        metres along the (approximate) normal."""
        alpha = np.asarray(alpha, np.float64)
        z = np.broadcast_to(np.asarray(z, np.float64), alpha.shape)
        a, F, B, n = self.coeffs(z)
        co = (F + B) / 2
        d = (F - B) / 2
        sn, cs = np.sin(alpha), np.cos(alpha)
        x = a * M.spow(sn, 2.0 / n)
        fwd = co + d * M.spow(cs, 2.0 / n)
        P = np.stack([x, -fwd, z], -1)
        if np.any(np.asarray(off) != 0):
            N = self.normal(alpha, z)
            P = P + N * np.asarray(off)[..., None]
        return P

    def normal(self, alpha, z, eps=1e-3):
        alpha = np.asarray(alpha, np.float64)
        z = np.broadcast_to(np.asarray(z, np.float64), alpha.shape)
        Pa1 = self.point(alpha + eps, z)
        Pa0 = self.point(alpha - eps, z)
        Pz1 = self.point(alpha, z + eps)
        Pz0 = self.point(alpha, z - eps)
        N = np.cross(Pa1 - Pa0, Pz1 - Pz0)
        N /= np.maximum(np.linalg.norm(N, axis=-1, keepdims=True), 1e-12)
        return N

    def alpha_of_x(self, x, z, back=False):
        """Front (or back) angle whose surface point has the given x at height z."""
        a, F, B, n = self.coeffs(np.asarray(z, np.float64))
        r = np.clip(np.asarray(x) / a, -0.999, 0.999)
        s = M.spow(r, n / 2.0)
        al = np.arcsin(s)
        if back:
            al = np.sign(al) * math.pi - al
        return al


# ---------------------------------------------------------------------------------------------
# folds: displacement ridges / valleys along curves in (alpha, z) space
# ---------------------------------------------------------------------------------------------
def fold_field(alpha, z, folds, torso):
    """Displacement (metres along the normal) at grid points from ``folds``.

    fold = dict(pts=[(alpha, z), ...], amp=+ridge / -valley (m), width (m), taper=(t0, t1))"""
    disp = np.zeros(np.shape(alpha))
    if not folds:
        return disp
    a_ref, _, _, _ = torso.coeffs(z)
    for f in folds:
        pts = M.resample(np.array(f["pts"], np.float64), 40)
        # work in metres: alpha * local half width ~ arc length
        za = pts[:, 1]
        aa = torso.coeffs(za)[0]
        X = pts[:, 0] * aa
        Z = pts[:, 1]
        gx = alpha * a_ref
        gz = z
        best = np.full(np.shape(alpha), 1e9)
        tpar = np.zeros(np.shape(alpha))
        L = np.concatenate([[0], np.cumsum(np.hypot(np.diff(X), np.diff(Z)))])
        L /= max(L[-1], 1e-9)
        for i in range(len(X) - 1):
            ax, az, bx, bz = X[i], Z[i], X[i + 1], Z[i + 1]
            dx, dz = bx - ax, bz - az
            l2 = dx * dx + dz * dz + 1e-12
            t = np.clip(((gx - ax) * dx + (gz - az) * dz) / l2, 0, 1)
            d = np.hypot(gx - (ax + t * dx), gz - (az + t * dz))
            m = d < best
            best = np.where(m, d, best)
            tpar = np.where(m, L[i] + t * (L[i + 1] - L[i]), tpar)
        w = f.get("width", 0.02)
        t0, t1 = f.get("taper", (0.15, 0.35))
        tap = M.smoothstep(0, t0, tpar) * (1 - M.smoothstep(1 - t1, 1.0, tpar))
        prof = np.cos(np.clip(best / w, 0, 1) * math.pi / 2) ** 2
        disp += f["amp"] * prof * tap
    return disp


def build_torso(torso, col, mats, region_fn, folds=None, name="Torso", z_bottom=-0.52, nz=110,
                na=144, off=0.0):
    """Torso loft; ``region_fn(x, z, alpha) -> material slot`` per face (face centres)."""
    z = np.linspace(torso.top, z_bottom, nz)
    a = np.linspace(-math.pi, math.pi, na, endpoint=False)
    AA, ZZ = np.meshgrid(a, z)
    disp = fold_field(AA, ZZ, folds, torso) + off
    P = torso.point(AA, ZZ, disp)
    # UV in metres: arc length around (front = 0), height
    seg = np.linalg.norm(np.diff(np.concatenate([P, P[:, :1]], 1), axis=1), axis=-1)
    U = np.concatenate([np.zeros((nz, 1)), np.cumsum(seg, 1)[:, :-1]], 1)
    U -= U[:, na // 2:na // 2 + 1]
    UV = np.stack([U, ZZ], -1)
    Fx = (P[:-1, :, 0] + P[1:, :, 0] + np.roll(P[:-1, :, 0], -1, 1) + np.roll(P[1:, :, 0], -1, 1)) / 4
    Fz = (ZZ[:-1] + ZZ[1:]) / 2
    Fa = (AA[:-1] + np.roll(AA[:-1], -1, 1)) / 2
    Fa[:, -1] = math.pi
    slots = region_fn(Fx, Fz, Fa)

    nr, nc = P.shape[:2]
    F = M.grid_faces(nr, nc, wrap=True)
    keep = [(f, int(slots[i // nc, i % nc])) for i, f in enumerate(F) if slots[i // nc, i % nc] >= 0]
    obj = M.mesh_object(name, P.reshape(-1, 3), [f for f, _ in keep], col, uvs=UV.reshape(-1, 2),
                        mats=mats, face_mats=[m for _, m in keep])
    M.fix_normals(obj, (0, 0.0, -0.3))
    return obj


def build_neck(H, torso, col, mat, z_top=-0.03, z_bot=-0.30, neck_k=1.0):
    """Skin neck from inside the head down into the chest opening."""
    zs = np.linspace(z_top, z_bot, 40)
    a = np.linspace(-math.pi, math.pi, 64, endpoint=False)
    rows = []
    for z in zs:
        # neck: slightly behind the head axis, flaring into the chest below the collar
        t = M.smoothstep(-0.15, -0.26, z)
        taper = 0.92 + 0.08 * M.smoothstep(-0.06, -0.15, z)
        ra = (0.057 * neck_k * taper + 0.07 * t) * H.s ** 0.5
        F = (0.046 * neck_k + 0.045 * t) * H.s ** 0.5
        B = -0.074 * neck_k * H.s ** 0.5
        co = (F + B) / 2 - 0.004
        d = (F - B) / 2
        x = ra * np.sin(a)
        fwd = co + d * np.cos(a)
        rows.append(np.stack([x, -fwd, np.full_like(a, z)], -1))
    P = np.stack(rows)
    obj = M.grid_object("Neck", P, col, wrap=True, mat=mat)
    M.fix_normals(obj, (0, 0.0, -0.15))
    return obj


# ---------------------------------------------------------------------------------------------
# crossed collar (交领右衽): nested V edges and the trim bands that lie on them
# ---------------------------------------------------------------------------------------------
def collar_layers(cp):
    """Collar geometry per layer (innermost first) in front-projection (x, z) terms.

    cp = dict(layers=[dict(color, band_w, ...)], neck_x, neck_z, cross_x, cross_z, step_x,
    step_z, armpit=(x, z), left=False).  The outer lapel (wearer's left) runs from the neck at
    +x down across to -x (右衽).  ``left=True`` mirrors it (左衽, steppe dress)."""
    out = []
    sgn = -1.0 if cp.get("left") else 1.0
    for k, L in enumerate(cp["layers"]):
        nx = cp["neck_x"] + cp["step_x"] * k
        nz = cp["neck_z"] - cp.get("step_nz", 0.004) * k
        cx = cp["cross_x"] - cp.get("cross_dx", 0.004) * k
        cz = cp["cross_z"] - cp["step_z"] * k
        ax, az = cp["armpit"]
        out.append(dict(k=k, nR=(sgn * nx, nz), nL=(-sgn * nx, nz), c=(sgn * cx, cz),
                        a=(sgn * ax, az), w=L.get("band_w", 0.016), L=L))
    return out


def _side(p, a, b):
    """Signed side of point(s) p relative to line a->b (2D)."""
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def inside_v(x, z, lay):
    """True where (x, z) lies inside the V opening of layer ``lay`` (front faces only)."""
    nR, nL, c = lay["nR"], lay["nL"], lay["c"]
    s1 = _side((x, z), nR, c)
    s2 = _side((x, z), nL, c)
    sR = _side((nL[0], nL[1] + 0.05), nR, c)
    sL = _side((nR[0], nR[1] + 0.05), nL, c)
    return (np.sign(s1) == np.sign(sR)) & (np.sign(s2) == np.sign(sL))


def band_paths(torso, lay, back=True, n_neck=28, n_front=36, stand=0.022):
    """Inner and outer edge curves (alpha, z) of a layer's collar band.

    Returns list of (name, inner (N, 2), outer (N, 2)) in (alpha, z) for the outer lapel (runs
    to the armpit) and the under lapel (ends at the crossing)."""
    res = []
    w = lay["w"]
    for nm, nk, end in (("outer", lay["nR"], lay["a"]), ("under", lay["nL"], lay["c"])):
        side = np.sign(nk[0]) or 1.0
        # front run: neck point -> crossing / armpit, in (x, z); outward normal away from the V
        if nm == "outer":
            pts = np.array([nk, lay["c"], end])
        else:
            pts = np.array([nk, end])
        fr = M.resample(pts, n_front)
        d = np.gradient(fr, axis=0)
        d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
        nrm = np.stack([d[:, 1], -d[:, 0]], -1)
        # outward = away from the opening (the opening is above / towards the other side)
        test = fr[len(fr) // 2] + nrm[len(fr) // 2] * 0.01
        if inside_v(np.array([test[0]]), np.array([test[1]]), lay)[0]:
            nrm = -nrm
        inner_xz = fr - nrm * 0.0025
        outer_xz = fr + nrm * w
        za_in = torso.alpha_of_x(inner_xz[:, 0], inner_xz[:, 1])
        za_out = torso.alpha_of_x(outer_xz[:, 0], outer_xz[:, 1])
        fin = np.stack([za_in, inner_xz[:, 1]], -1)
        fout = np.stack([za_out, outer_xz[:, 1]], -1)
        if back:
            # neck run: from the back centre round to the neck point, standing up the neck
            a0 = math.pi * side
            a1 = fin[0, 0]
            al = np.linspace(a0, a1, n_neck, endpoint=False)
            zt = nk[1] + stand * (1 - 0.35 * M.smoothstep(abs(a0), abs(a1), np.abs(al)))
            nin = np.stack([al, zt], -1)
            zo = nk[1] - 0.002 - (w * 0.5) * M.smoothstep(abs(a0) * 0.7, abs(a1), np.abs(al))
            nout = np.stack([np.linspace(a0, fout[0, 0], n_neck, endpoint=False), zo], -1)
            # blend the neck run into the front run
            fin = np.concatenate([nin, fin])
            fout = np.concatenate([nout, fout])
        res.append((nm, fin, fout))
    return res
