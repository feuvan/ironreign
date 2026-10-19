"""2D brush engine for gongbi_C (numpy + Pillow; runs in Blender's python or system python3).

* :class:`Proj`    world / face-space -> work-pixel projection from the exported camera, head pose
                   and height grids, with depth testing against the rendered depth pass
* :class:`Paper`   the work-resolution painting: ``paint`` (opaque mineral), ``glaze``
                   (transparent dye, multiplies) and ``ink`` layers, all clipped by optional masks
* strokes are capsule chains with per-sample radius and alpha (signed-distance coverage, so
  they are anti-aliased at any width); fills are supersampled Pillow polygons, optionally
  softened (晕染) with a blur.
"""

import json
import math
import os

import numpy as np

from looks import srgb


# =============================================================================================
# projection
# =============================================================================================
class Proj:
    def __init__(self, meta, npz):
        self.meta = meta
        self.W = meta["W"] * meta["ss"]
        self.H = meta["H"] * meta["ss"]
        self.ss = meta["ss"]
        self.V = np.array(meta["view"])
        self.P = np.array(meta["proj"])
        self.Mh = np.array(meta["head"])
        self.s = meta.get("head_scale", 1.0)
        self.us = np.array(meta["grid_u"])
        self.vs = np.array(meta["grid_v"])
        self.hh = np.array(npz["h_head"], np.float64)
        self.hf = np.array(npz["h_front"], np.float64)
        self.depth = np.array(npz["depth"], np.float64)
        self.look = np.array(meta["look_local"])
        self._fill_grids()

    def _fill_grids(self):
        """Extend the head height grid outwards (nearest valid along rows) so features near the
        contour still map; keep a validity mask."""
        self.hh_ok = np.isfinite(self.hh)
        hh = self.hh.copy()
        for i in range(hh.shape[0]):
            r = hh[i]
            ok = np.isfinite(r)
            if ok.sum() >= 2:
                idx = np.arange(len(r))
                hh[i] = np.interp(idx, idx[ok], r[ok])
        # rows with no data: copy nearest row
        okr = np.isfinite(hh).all(1)
        if okr.any():
            ii = np.arange(hh.shape[0])
            for i in ii[~okr]:
                j = ii[okr][np.argmin(np.abs(ii[okr] - i))]
                hh[i] = hh[j]
        self.hh_f = hh
        hf = self.hf.copy()
        for i in range(hf.shape[0]):
            r = hf[i]
            ok = np.isfinite(r)
            if ok.sum() >= 2:
                idx = np.arange(len(r))
                hf[i] = np.interp(idx, idx[ok], r[ok])
            elif ok.sum() == 0:
                hf[i] = np.nan
        self.hf_f = hf

    def _bilinear(self, G, u, v):
        u = np.asarray(u, np.float64)
        v = np.asarray(v, np.float64)
        fu = np.clip((u - self.us[0]) / (self.us[1] - self.us[0]), 0, len(self.us) - 1.001)
        fv = np.clip((v - self.vs[0]) / (self.vs[1] - self.vs[0]), 0, len(self.vs) - 1.001)
        i0 = np.floor(fv).astype(int)
        j0 = np.floor(fu).astype(int)
        tv, tu = fv - i0, fu - j0
        g00 = G[i0, j0]
        g01 = G[i0, j0 + 1]
        g10 = G[i0 + 1, j0]
        g11 = G[i0 + 1, j0 + 1]
        return (g00 * (1 - tu) * (1 - tv) + g01 * tu * (1 - tv) + g10 * (1 - tu) * tv + g11 * tu * tv)

    def h_face(self, u, v):
        return self._bilinear(self.hh_f, u, v)

    def h_front(self, u, v):
        return self._bilinear(self.hf_f, u, v)

    def local_to_world(self, L):
        L = np.asarray(L, np.float64)
        return L @ self.Mh[:3, :3].T + self.Mh[:3, 3]

    def world_px(self, Pw):
        """World points (..., 3) -> (..., 3) work px x, px y, view depth."""
        Pw = np.asarray(Pw, np.float64)
        h = np.concatenate([Pw, np.ones(Pw.shape[:-1] + (1,))], -1)
        c = h @ self.V.T
        clip = c @ self.P.T
        ndc = clip[..., :3] / clip[..., 3:4]
        return np.stack([(ndc[..., 0] + 1) / 2 * self.W, (1 - ndc[..., 1]) / 2 * self.H, -c[..., 2]], -1)

    def face_px(self, u, v, dh=0.0, scaled=True, h=None):
        """Face-space design coordinates (canon metres at scale 1 unless ``scaled=False``) ->
        work px (x, y, depth).  The point sits on the head surface + ``dh`` forward."""
        k = self.s if scaled else 1.0
        u = np.asarray(u, np.float64) * k
        v = np.asarray(v, np.float64) * k
        hh = self.h_face(u, v) if h is None else h
        L = np.stack([u, -(hh + np.asarray(dh, np.float64) * k), v], -1)
        return self.world_px(self.local_to_world(L))

    def px_per_m(self):
        a = self.face_px(0.0, 0.0)
        b = self.face_px(0.0, 0.01)
        return float(np.hypot(*(b[:2] - a[:2]))) / 0.01 / self.s

    def visible(self, pts, tol=0.004):
        """Per-point visibility (0/1) of projected points (x, y, depth) against the depth pass."""
        x = np.clip(pts[..., 0].astype(int), 0, self.W - 1)
        y = np.clip(pts[..., 1].astype(int), 0, self.H - 1)
        d = self.depth[y, x]
        return (pts[..., 2] <= d + tol).astype(np.float64)

    def gaze(self):
        """Direction from the head to the camera in head-local terms -> (yaw, pitch) radians,
        yaw + towards +u, pitch + up."""
        to_cam = -self.look
        yaw = math.atan2(to_cam[0], -to_cam[1])
        pitch = math.atan2(to_cam[2], math.hypot(to_cam[0], to_cam[1]))
        return yaw, pitch

    def far_sign(self):
        """+1 if the far side of the face is +u (the face turned towards -u... ) else -1."""
        yaw, _ = self.gaze()
        return -1.0 if yaw > 0 else 1.0


# =============================================================================================
# rasterisers
# =============================================================================================
def capsule_chain(H, W, P, R, A, region=None):
    """Coverage (bbox y0, x0, array) of a capsule chain: P (N, 2) px, R radius px, A alpha."""
    P = np.asarray(P, np.float64)
    R = np.broadcast_to(np.asarray(R, np.float64), (len(P),)).copy()
    A = np.broadcast_to(np.asarray(A, np.float64), (len(P),)).copy()
    if len(P) < 2:
        return None
    m = R.max() + 2
    x0 = int(max(0, math.floor(P[:, 0].min() - m)))
    x1 = int(min(W, math.ceil(P[:, 0].max() + m)))
    y0 = int(max(0, math.floor(P[:, 1].min() - m)))
    y1 = int(min(H, math.ceil(P[:, 1].max() + m)))
    if x1 <= x0 or y1 <= y0:
        return None
    cov = np.zeros((y1 - y0, x1 - x0), np.float32)
    for i in range(len(P) - 1):
        if A[i] <= 0 and A[i + 1] <= 0:
            continue
        a, b = P[i], P[i + 1]
        r0, r1 = R[i], R[i + 1]
        mm = max(r0, r1) + 1.5
        sx0 = int(max(x0, math.floor(min(a[0], b[0]) - mm)))
        sx1 = int(min(x1, math.ceil(max(a[0], b[0]) + mm)))
        sy0 = int(max(y0, math.floor(min(a[1], b[1]) - mm)))
        sy1 = int(min(y1, math.ceil(max(a[1], b[1]) + mm)))
        if sx1 <= sx0 or sy1 <= sy0:
            continue
        yy, xx = np.mgrid[sy0:sy1, sx0:sx1]
        xx = xx + 0.5
        yy = yy + 0.5
        ab = b - a
        l2 = ab @ ab + 1e-9
        t = np.clip(((xx - a[0]) * ab[0] + (yy - a[1]) * ab[1]) / l2, 0, 1)
        d = np.hypot(xx - a[0] - t * ab[0], yy - a[1] - t * ab[1])
        r = r0 + t * (r1 - r0)
        al = A[i] + t * (A[i + 1] - A[i])
        c = np.clip(r - d + 0.5, 0, 1) * al
        sub = cov[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0]
        np.maximum(sub, c.astype(np.float32), out=sub)
    return y0, x0, cov


def polygon_mask(H, W, pts, ovs=4, soft=0.0):
    """Anti-aliased polygon coverage in a bbox: (y0, x0, array).  ``soft`` = blur sigma px."""
    from PIL import Image, ImageDraw
    P = np.asarray(pts, np.float64)
    if len(P) < 3:
        return None
    m = int(math.ceil(soft * 3 + 2))
    x0 = int(max(0, math.floor(P[:, 0].min()) - m))
    x1 = int(min(W, math.ceil(P[:, 0].max()) + m))
    y0 = int(max(0, math.floor(P[:, 1].min()) - m))
    y1 = int(min(H, math.ceil(P[:, 1].max()) + m))
    if x1 <= x0 or y1 <= y0:
        return None
    w, h = x1 - x0, y1 - y0
    im = Image.new("L", (w * ovs, h * ovs), 0)
    q = [((x - x0) * ovs, (y - y0) * ovs) for x, y in P]
    ImageDraw.Draw(im).polygon(q, fill=255)
    a = np.asarray(im, np.float32).reshape(h, ovs, w, ovs).mean((1, 3)) / 255.0
    if soft > 0.3:
        a = blur(a, soft)
    return y0, x0, a


def ellipse_pts(c, rx, ry, rot=0.0, n=40):
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    x = np.cos(t) * rx
    y = np.sin(t) * ry
    cr, sr = math.cos(rot), math.sin(rot)
    return np.stack([c[0] + x * cr - y * sr, c[1] + x * sr + y * cr], -1)


def box_blur(a, r):
    r = int(round(r))
    if r <= 0:
        return a
    out = a
    for ax in (0, 1):
        pad = [(0, 0)] * out.ndim
        pad[ax] = (r + 1, r)
        p = np.pad(out, pad, mode="edge")
        c = np.cumsum(p, axis=ax, dtype=np.float64)
        n = out.shape[ax]
        hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=ax)
        lo = np.take(c, np.arange(0, n), axis=ax)
        out = ((hi - lo) / (2 * r + 1)).astype(np.float32)
    return out


def blur(a, sigma):
    if sigma <= 0.3:
        return a
    r = max(1, int(round(sigma * 0.85)))
    out = a
    for _ in range(3):
        out = box_blur(out, r)
    return out


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, np.float64) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def resample(P, n):
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


def catmull(pts, n=40):
    """Smooth curve through points (Catmull-Rom), resampled to n points."""
    P = np.asarray(pts, np.float64)
    if len(P) < 3:
        return resample(P, n)
    Q = np.concatenate([P[:1] * 2 - P[1:2], P, P[-1:] * 2 - P[-2:-1]])
    out = []
    for i in range(1, len(Q) - 2):
        p0, p1, p2, p3 = Q[i - 1], Q[i], Q[i + 1], Q[i + 2]
        t = np.linspace(0, 1, 12, endpoint=False)[:, None]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-1:])
    return resample(np.concatenate(out), n)


def brush_profile(n, head=0.15, tail=0.35, lo=0.25, kind="taper", pressure=None, seed=0):
    """Width multiplier along a stroke (0..1 param): 'taper' (both ends), 'nail' (钉头鼠尾: a
    pressed head then a long thinning tail), 'even' (铁线描), 'tail' (thick start)."""
    t = np.linspace(0, 1, n)
    if kind == "nail":
        w = 0.55 + 0.45 * np.exp(-((t - 0.06) / 0.07) ** 2) + 0.35 * (1 - t)
        w *= 1 - smoothstep(1 - tail, 1.0, t) * (1 - lo)
        w = np.minimum(w, smoothstep(0.0, head * 0.5, t) * 0.7 + 0.3)
    elif kind == "even":
        w = 0.85 + 0.15 * np.minimum(smoothstep(0, head, t), 1 - smoothstep(1 - tail, 1, t))
    elif kind == "tail":
        w = (1 - smoothstep(0.0, 1.0, t)) * (1 - lo) + lo
        w *= smoothstep(0.0, head * 0.4, t) * 0.6 + 0.4
    else:
        w = np.minimum(smoothstep(0, head, t) * (1 - lo) + lo, (1 - smoothstep(1 - tail, 1, t)) * (1 - lo) + lo)
    if pressure:
        rng = np.random.default_rng(seed)
        k = rng.normal(0, 1, 6)
        w = w * (1 + pressure * sum(k[i] * np.sin((i + 1) * math.pi * t + k[i] * 3) for i in range(3)) / 3)
    return np.clip(w, 0, 2)


# =============================================================================================
# the painting
# =============================================================================================
class Paper:
    """Work-resolution sRGB painting with paint / glaze / ink layers."""

    def __init__(self, img, ss):
        self.img = np.ascontiguousarray(img, np.float32)
        self.H, self.W = img.shape[:2]
        self.ss = ss
        self.ink_a = np.zeros((self.H, self.W), np.float32)

    def k(self, px):
        """final px -> work px"""
        return px * self.ss

    def apply(self, cov, color, mode="paint", alpha=1.0, clip=None, ink=False):
        if cov is None:
            return
        y0, x0, a = cov
        h, w = a.shape
        a = a * alpha
        if clip is not None:
            a = a * clip[y0:y0 + h, x0:x0 + w]
        sub = self.img[y0:y0 + h, x0:x0 + w]
        c = np.array(srgb(color), np.float32) if not isinstance(color, np.ndarray) else color
        if mode == "glaze":
            sub *= (1 - a[..., None] * (1 - c))
        elif mode == "lighten":
            sub[:] = sub + (np.maximum(sub, c) - sub) * a[..., None]
        else:
            sub[:] = sub * (1 - a[..., None]) + c * a[..., None]
        if ink:
            ia = self.ink_a[y0:y0 + h, x0:x0 + w]
            np.maximum(ia, a, out=ia)

    def stroke(self, P, width_px, color="ink", alpha=1.0, mode="paint", clip=None, prof=None,
               alphas=None, ink=True):
        """P (N, 2) work px; width in FINAL px (x prof)."""
        P = np.asarray(P, np.float64)
        n = len(P)
        if n < 2:
            return
        prof = np.ones(n) if prof is None else np.asarray(prof)
        R = 0.5 * self.k(width_px) * prof
        A = np.ones(n) if alphas is None else np.asarray(alphas)
        cov = capsule_chain(self.H, self.W, P[:, :2], R, A)
        self.apply(cov, color, mode, alpha, clip, ink=ink)

    def fill(self, pts, color, alpha=1.0, mode="paint", soft=0.0, clip=None):
        cov = polygon_mask(self.H, self.W, np.asarray(pts)[:, :2], soft=self.k(soft) if soft else 0.0)
        self.apply(cov, color, mode, alpha, clip)

    def blob(self, c, rx, ry, color, alpha, rot=0.0, mode="glaze", clip=None, soft=0.6):
        """Soft elliptic wash (radii in work px): Gaussian falloff."""
        m = int(max(rx, ry) * 2.2) + 2
        x0, x1 = int(max(0, c[0] - m)), int(min(self.W, c[0] + m))
        y0, y1 = int(max(0, c[1] - m)), int(min(self.H, c[1] + m))
        if x1 <= x0 or y1 <= y0:
            return
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float64)
        dx, dy = xx - c[0], yy - c[1]
        cr, sr = math.cos(rot), math.sin(rot)
        u = (dx * cr + dy * sr) / rx
        v = (-dx * sr + dy * cr) / ry
        a = np.exp(-(u * u + v * v) / (2 * soft * soft)).astype(np.float32)
        self.apply((y0, x0, a), color, mode, alpha, clip)

    def layer(self, cov_full, color, mode="glaze", alpha=1.0, clip=None):
        """Full-frame coverage array."""
        self.apply((0, 0, cov_full.astype(np.float32)), color, mode, alpha, clip)


def load_scene(d):
    with open(os.path.join(d, "scene.json")) as f:
        meta = json.load(f)
    npz = dict(np.load(os.path.join(d, "scene.npz")))
    return meta, npz
