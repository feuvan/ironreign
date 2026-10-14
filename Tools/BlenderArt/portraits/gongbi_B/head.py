"""Construction frame of a turned head (the painter's armature, not anatomy).

A painter turning a head into 3/4 view first draws a construction: an egg for the skull, a
centre line curving round the face, and feature lines wrapped around it.  :class:`Head` is that
construction as numbers.  Head units: crown y=0, chin y=1, x0 = frontal offset from the centre
line (negative = viewer's left in a frontal view), z = depth towards the viewer.

Each height y has a superelliptic cross-section (half-width a, centre zc, half-depth d,
exponent k).  :meth:`P` wraps any frontal template point (x0, y) onto the surface and projects it
for the head's yaw; :meth:`silhouette` gives the outline.  Feature templates (eyes, brows, nose,
mouth, hairlines, helmet rims ...) are authored frontally and wrapped by :meth:`P`, which
foreshortens the far eye and curves the mouth exactly as a painter would.

yaw > 0 turns the face towards the viewer's right (the viewer's-left side of the face is then
the broad, near side).
"""

import math

import numpy as np

import geom2d as g


def _table(keys):
    """Smooth dense table through (y, value) keys (Catmull-Rom), sorted by y."""
    ys = np.array([k[0] for k in keys])
    vs = np.array([k[1] for k in keys])
    pts = g.catmull(np.stack([ys, vs], 1), n=24)
    order = np.argsort(pts[:, 0])
    return pts[order, 0], pts[order, 1]


class Head:
    def __init__(self, cx, crown_y, size, yaw_deg=20.0, roll_deg=0.0, shape=None):
        """cx: canvas x of the head's vertical axis; crown_y: canvas y of the crown;
        size: crown-to-chin height in px; shape: dict of proportion multipliers."""
        self.cx = cx
        self.cy = crown_y
        self.s = size
        self.yaw = math.radians(yaw_deg)
        self.roll = math.radians(roll_deg)
        self.sh = dict(width=1.0, jaw=1.0, chin=1.0, cheek=1.0, forehead=1.0, depth=1.0,
                       chin_len=1.0, chin_fwd=1.0, k_face=2.6)
        if shape:
            self.sh.update(shape)
        self._build()

    # ------------------------------------------------------------------------------------
    def _build(self):
        sh = self.sh
        w = sh["width"]
        jw = sh["jaw"]
        ch = sh["cheek"]
        fh = sh["forehead"]
        cw = sh["chin"]
        dep = sh["depth"]
        # half-width profile a(y)
        self.a_keys = [
            (0.00, 0.02), (0.04, 0.16 * w), (0.12, 0.262 * w), (0.22, 0.308 * w * fh),
            (0.32, 0.324 * w * fh), (0.42, 0.326 * w), (0.52, 0.320 * w * ch),
            (0.60, 0.308 * w * ch), (0.68, 0.290 * w * (0.5 + 0.5 * jw)),
            (0.76, 0.272 * w * jw), (0.82, 0.252 * w * jw), (0.87, 0.226 * w * jw),
            (0.91, 0.195 * w * (0.6 * jw + 0.4 * cw)), (0.945, 0.155 * w * (0.3 * jw + 0.7 * cw)),
            (0.975, 0.110 * w * cw), (1.00, 0.065 * w * cw),
        ]
        cf = sh["chin_fwd"]
        self.zc_keys = [
            (0.00, 0.00), (0.62, 0.00), (0.70, 0.002), (0.78, 0.012), (0.84, 0.035 * cf),
            (0.89, 0.075 * cf), (0.93, 0.125 * cf), (0.965, 0.19 * cf), (1.00, 0.27 * cf),
        ]
        self.d_keys = [
            (0.00, 0.05), (0.06, 0.25), (0.15, 0.40), (0.30, 0.46), (0.50, 0.465),
            (0.62, 0.46), (0.72, 0.43), (0.80, 0.375), (0.88, 0.30), (0.94, 0.22),
            (1.00, 0.10),
        ]
        self.d_keys = [(y, v * dep) for y, v in self.d_keys]
        self._ta = _table(self.a_keys)
        self._tz = _table(self.zc_keys)
        self._td = _table(self.d_keys)

    def a(self, y):
        return np.interp(y, *self._ta)

    def zc(self, y):
        return np.interp(y, *self._tz)

    def d(self, y):
        return np.interp(y, *self._td)

    def k(self, y):
        kf = self.sh["k_face"]
        return np.interp(y, [0.0, 0.3, 0.55, 0.85, 1.0], [2.0, 2.2, kf, kf, 2.2])

    def zsurf(self, x0, y):
        """Depth of the front surface at frontal offset x0, height y."""
        x0 = np.asarray(x0, float)
        y = np.asarray(y, float)
        a = self.a(y)
        k = self.k(y)
        r = np.clip(np.abs(x0) / np.maximum(a, 1e-4), 0, 1)
        return self.zc(y) + self.d(y) * (1 - r ** k) ** (1 / k)

    # ------------------------------------------------------------------------------------
    def proj(self, x0, y, z):
        """Head-unit 3D point -> canvas px."""
        x0 = np.asarray(x0, float)
        y = np.asarray(y, float)
        z = np.asarray(z, float)
        X = x0 * math.cos(self.yaw) + z * math.sin(self.yaw)
        Y = y
        # roll about the head centre (0, 0.5)
        if self.roll:
            c, s = math.cos(self.roll), math.sin(self.roll)
            X, Y = X * c - (Y - 0.5) * s, X * s + (Y - 0.5) * c + 0.5
        return np.stack([self.cx + self.s * X, self.cy + self.s * Y], -1)

    def P(self, pts, dz=0.0):
        """Wrap frontal template points (x0, y) [head units] onto the face surface (+ relief
        dz, scalar or per point) and project to canvas px."""
        pts = g.A(pts)
        z = self.zsurf(pts[:, 0], pts[:, 1]) + dz
        return self.proj(pts[:, 0], pts[:, 1], z)

    def Pz(self, pts3):
        """Explicit 3D points (x0, y, z) -> canvas px."""
        p = np.asarray(pts3, float).reshape(-1, 3)
        return self.proj(p[:, 0], p[:, 1], p[:, 2])

    def section(self, y, n=180, dr=0.0):
        """Cross-section points (x0, z) at height y (optionally expanded by dr)."""
        a = float(self.a(y)) + dr
        k = float(self.k(y))
        zc = float(self.zc(y))
        d = float(self.d(y)) + dr
        ph = np.linspace(0, 2 * math.pi, n, endpoint=False)
        c, s = np.cos(ph), np.sin(ph)
        x0 = a * np.sign(c) * np.abs(c) ** (2 / k)
        z = zc + d * np.sign(s) * np.abs(s) ** (2 / k)
        return x0, z

    def silhouette(self, y0=0.0, y1=1.0, n=80, side=+1, dr=0.0):
        """Outline on one screen side: side=+1 -> right (max X), -1 -> left (min X).
        dr may be a function of y (hair volume varying with height)."""
        ys = np.linspace(y0, y1, n)
        out = []
        cyaw, syaw = math.cos(self.yaw), math.sin(self.yaw)
        for y in ys:
            x0, z = self.section(y, dr=float(dr(y)) if callable(dr) else dr)
            X = x0 * cyaw + z * syaw
            i = np.argmax(X) if side > 0 else np.argmin(X)
            out.append((x0[i], y, z[i]))
        return self.Pz(out), np.array(out)

    # surface addressed by longitude: lon 0 = face centre, +-pi/2 = sides, pi = back
    def lon_xyz(self, lon, y, dr=0.0):
        lon = np.asarray(lon, float)
        y = np.asarray(y, float)
        a = self.a(y) + dr
        d = self.d(y) + dr
        k = self.k(y)
        sl, cl = np.sin(lon), np.cos(lon)
        x0 = a * np.sign(sl) * np.abs(sl) ** (2 / k)
        z = self.zc(y) + d * np.sign(cl) * np.abs(cl) ** (2 / k)
        return x0, y, z

    def Plon(self, lon, y, dr=0.0):
        x0, y, z = self.lon_xyz(lon, y, dr)
        return self.proj(x0, y, z)

    def facing_lon(self, lon, y, dr=0.0, eps=1e-3):
        """>0 where the surface at (lon, y) faces the viewer."""
        lon = np.asarray(lon, float)
        y = np.asarray(y, float)
        p = np.stack(self.lon_xyz(lon, y, dr), -1)
        pl = np.stack(self.lon_xyz(lon + eps, y, dr), -1)
        py = np.stack(self.lon_xyz(lon, y + eps, dr), -1)
        n = np.cross(pl - p, py - p)
        n = n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-12)
        v = np.array([-math.sin(self.yaw), 0.0, math.cos(self.yaw)])
        f = n @ v
        # orientation: front point must face the viewer
        n0 = np.cross(np.stack(self.lon_xyz(eps, 0.5), -1) - np.stack(self.lon_xyz(0.0, 0.5), -1),
                      np.stack(self.lon_xyz(0.0, 0.5 + eps), -1) - np.stack(self.lon_xyz(0.0, 0.5), -1))
        return f * (1 if n0[2] > 0 else -1)

    def far_side(self):
        """+1 if the far (narrow) side of the face is on the viewer's right."""
        return 1 if self.yaw >= 0 else -1

    def unit(self, v):
        return v * self.s
