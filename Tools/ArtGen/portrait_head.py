"""Head model for the procedural portraits: a yawed 3D head built from
horizontal egg-shaped cross-sections, projected orthographically.

Face-local coordinates:
    u  = sin(phi) where phi is the angle around the vertical axis
         (0 = facial midline, -1 = near/left ear, +1 = far/right ear)
    yu = height in "head units" relative to the eye line (+ = down);
         the crown is at about -1 and the chin at about +1.
Head-local 3D: x lateral (px, + = subject's left = viewer's right before
yaw), z forward (px), measured from the vertical head axis.
"""
import math

import numpy as np
from scipy.interpolate import PchipInterpolator

from portrait_raster import (HH, WW, SCALE, grid, clamp01, smoothstep, blur)

NPHI = 241


class Head:
    def __init__(self, fp):
        self.hu = fp['hu']
        self.ye = fp['ye']
        self.xc = fp['xc']
        self.th = math.radians(fp['yaw'])
        self.crown = fp.get('crown', -1.0)
        self.chin = fp.get('chin', 1.0)
        Wc, Wz, Wk, Wm, Wj, Wch = (fp['w_cran'], fp['w_zyg'], fp['w_cheek'], fp.get('w_mouth', (fp['w_cheek'] + fp['w_jaw']) * 0.5),
                                   fp['w_jaw'], fp['w_chin'])
        self._Wc = Wc
        self.Wz = Wz
        jy = fp.get('jaw_y', 0.62)
        chin = self.chin
        cf = fp.get('chin_f', 0.0)    # chin projection
        ff = fp.get('front', 0.64)
        vs = fp.get('vshape', 1.0)
        # keypoints (yu, w, F, B, o, e)
        self._top = -0.3
        self._ftop = ff + 0.02
        ycs = chin - 0.1
        keys = [
            (-0.3, Wc, ff + 0.02, -1.0, -0.2, 0.0),
            (0.0, Wz, ff - 0.02, -0.98, -0.15, 0.04),
            (0.3, Wk, ff, -0.8, -0.12, 0.12 * vs),
            (jy, Wj, ff + 0.02, -0.28, -0.1, 0.26 * vs),
            ((jy + ycs) * 0.5, (Wj + Wch) * 0.5 + 0.02, ff - 0.01 + cf * 0.5, 0.05, 0.12, 0.34),
            (ycs, Wch, ff - 0.04 + cf, 0.3, 0.34, 0.4),
        ]
        ky = [k[0] for k in keys]
        self._interp = [PchipInterpolator(ky, [k[i] for k in keys]) for i in range(1, 6)]
        self._ycs = ycs
        self._Wch = Wch
        self._Fch = ff - 0.04 + cf
        # tabulate the rows of the working canvas
        X, Y = grid()
        self.row_yu = (Y[:, 0] - self.ye) / self.hu
        self._rows = self.profile(self.row_yu)

    # ------------------------------------------------------------------
    def profile(self, yu):
        """w, F, B, o (final px) and egg factor e for heights yu (array)."""
        yu = np.atleast_1d(np.asarray(yu, dtype=np.float64))
        hu = self.hu
        w = np.zeros_like(yu)
        F = np.zeros_like(yu)
        B = np.zeros_like(yu)
        o = np.zeros_like(yu)
        e = np.zeros_like(yu)
        top = (yu >= self.crown) & (yu < self._top)
        t = (self._top - yu[top]) / (self._top - self.crown)
        s = np.sqrt(clamp01(1 - t ** 2))
        w[top] = self._Wc * s
        F[top] = -0.2 + (self._ftop + 0.2) * s
        B[top] = -0.2 - 0.8 * s
        o[top] = -0.2
        mid = (yu >= self._top) & (yu <= self._ycs)
        ym = yu[mid]
        w[mid], F[mid], B[mid], o[mid], e[mid] = (f(ym) for f in self._interp)
        bot = (yu > self._ycs) & (yu <= self.chin)
        t = (yu[bot] - self._ycs) / (self.chin - self._ycs)
        s = np.sqrt(clamp01(1 - t ** 2))
        w[bot] = self._Wch * s
        F[bot] = self._Fch - 0.1 * t ** 2
        B[bot] = 0.3 + 0.15 * t
        o[bot] = 0.34 + 0.12 * t
        e[bot] = 0.4
        o = np.minimum(np.maximum(o, B + 0.02), F - 0.02)
        return w * hu, F * hu, B * hu, o * hu, e

    def _section(self, w, F, B, o, e, phi):
        """Cross-section points (x, z) for angles phi (broadcastable)."""
        c = np.cos(phi)
        sn = np.sin(phi)
        front = c >= 0
        x = np.where(front, w * sn * (1 - e * c), w * sn)
        z = np.where(front, o + (F - o) * c, o + (o - B) * c)
        return x, z

    # ------------------------------------------------------------------
    def local_to_screen(self, x, yu, z):
        """Head-local 3D point (x lateral px, yu, z forward px) -> screen (X, Y, Z)."""
        c, s = math.cos(self.th), math.sin(self.th)
        return self.xc + x * c + z * s, self.ye + yu * self.hu, -x * s + z * c

    def project(self, u, yu, p=0.0):
        """Face-local (u, yu) plus outward protrusion p (final px) -> screen.

        Returns (x, y, z, sx) where sx is the horizontal foreshortening factor.
        """
        u = float(np.clip(u, -1.0, 1.0))
        phi = math.asin(u)
        w, F, B, o, e = (float(v[0]) for v in self.profile(np.array([yu])))
        w = max(w, 1e-3)
        ph = np.array([phi - 1e-3, phi, phi + 1e-3])
        x, z = self._section(w, F, B, o, e, ph)
        tx, tz = x[2] - x[0], z[2] - z[0]
        ln = math.hypot(tx, tz) + 1e-12
        nx, nz = tz / ln, -tx / ln
        if nz < 0 or (abs(nz) < 1e-6 and nx * x[1] < 0):
            nx, nz = -nx, -nz
        px, pz = x[1] + p * nx, z[1] + p * nz
        X, Y, Z = self.local_to_screen(px, yu, pz)
        c, s = math.cos(self.th), math.sin(self.th)
        sx = abs(tx * c + tz * s) / ln
        return X, Y, Z, max(0.05, sx)

    def pt(self, u, yu, p=0.0):
        x, y, _, _ = self.project(u, yu, p)
        return (x, y)

    def midline_x(self, yu, p=0.0):
        return self.project(0.0, yu, p)[0]

    def width_at(self, yu):
        return float(self.profile(np.array([yu]))[0][0])

    # ------------------------------------------------------------------
    def surface(self, grow=0.0):
        """Per-pixel maps of the (optionally inflated) head surface.

        Returns dict(mask, z, u, phi, yu, inside, face, fmask).
        `grow` inflates the head by that many final px (hair/hat volume).
        """
        X, Y = grid()
        hu = self.hu
        if grow:
            yu_rows = self.row_yu + grow * 0.9 / hu * (self.row_yu < 0)
            rows = self.profile(yu_rows)
        else:
            yu_rows = self.row_yu
            rows = self._rows
        w, F, B, o, e = rows
        phi = np.linspace(-math.pi, math.pi, NPHI)
        c, s = math.cos(self.th), math.sin(self.th)
        valid = w > 0.05
        xs, zs = self._section(w[:, None], F[:, None], B[:, None], o[:, None], e[:, None], phi[None, :])
        if grow:
            # simple inflation: push points away from the section centre
            cx0 = 0.0
            cz0 = o[:, None]
            dx = xs - cx0
            dz = zs - cz0
            ln = np.sqrt(dx * dx + dz * dz) + 1e-6
            xs = xs + grow * dx / ln
            zs = zs + grow * dz / ln
        Xs = self.xc + xs * c + zs * s
        Zs = -xs * s + zs * c
        out_phi = np.zeros((HH, WW), np.float32)
        out_z = np.full((HH, WW), -1e4, np.float32)
        out_m = np.zeros((HH, WW), np.float32)
        xrow = X[0]
        for r in np.nonzero(valid)[0]:
            xr = Xs[r]
            i0 = int(np.argmin(xr))
            i1 = int(np.argmax(xr))
            if i0 < i1:
                idx = np.arange(i0, i1 + 1)
            else:
                idx = np.concatenate([np.arange(i0, NPHI - 1), np.arange(0, i1 + 1)])
            xb = xr[idx]
            # enforce monotonic
            xb = np.maximum.accumulate(xb)
            pb = np.unwrap(phi[idx])
            zb = Zs[r][idx]
            lo, hi = xb[0], xb[-1]
            sel = (xrow >= lo - 1.0) & (xrow <= hi + 1.0)
            xx = xrow[sel]
            out_phi[r, sel] = np.interp(xx, xb, pb)
            out_z[r, sel] = np.interp(xx, xb, zb)
            out_m[r, sel] = clamp01(np.minimum(xx - lo, hi - xx) * SCALE + 0.5)
        # vertical antialias at the crown / chin is handled by row validity; soften a little
        inside = out_m > 0.0
        ph = (out_phi + math.pi) % (2 * math.pi) - math.pi
        face = inside & (np.abs(ph) <= math.pi / 2)
        u = np.where(face, np.sin(ph), np.where(ph < 0, -1.0, 1.0))
        yu = (Y - self.ye) / hu
        return dict(mask=out_m, z=np.where(inside, out_z, 0).astype(np.float32),
                    u=u.astype(np.float32), phi=ph.astype(np.float32), yu=yu.astype(np.float32),
                    inside=inside, face=face, fmask=(out_m * face).astype(np.float32))


# ----------------------------------------------------------------------
# Height-field primitives (screen space)
# ----------------------------------------------------------------------

def gbump(cx, cy, rx, ry, h, ang=0.0):
    X, Y = grid()
    c, s = math.cos(ang), math.sin(ang)
    u = (X - cx) * c + (Y - cy) * s
    v = -(X - cx) * s + (Y - cy) * c
    return (h * np.exp(-((u / rx) ** 2 + (v / ry) ** 2))).astype(np.float32)


def ridge(p0, p1, h0, h1, s_left, s_right, s_end=None):
    """Asymmetric ridge along segment p0->p1 (height interpolated h0->h1).

    s_left/s_right: falloff widths on the left/right side of the segment
    (screen left = smaller x when the segment points down).
    """
    X, Y = grid()
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    L2 = dx * dx + dy * dy
    t = ((X - x0) * dx + (Y - y0) * dy) / L2
    tc = np.clip(t, 0, 1)
    qx = x0 + tc * dx
    qy = y0 + tc * dy
    L = math.sqrt(L2)
    # signed perpendicular distance (positive = right of direction)
    perp = ((X - x0) * dy - (Y - y0) * dx) / L
    sig = np.where(perp < 0, s_right, s_left)
    along = (t - tc) * L
    se = s_end if s_end is not None else min(s_left, s_right)
    h = h0 + (h1 - h0) * tc
    return (h * np.exp(-(perp / sig) ** 2 - (along / se) ** 2)).astype(np.float32)


def soft_max(a, b, k=2.0):
    """Smooth maximum for blending height fields."""
    return np.logaddexp(a * k, b * k) / k


def shadow_map(h, light, steps=24, max_dist=16.0):
    """Hard shadow of a height field (final px heights) -> 0..1 (1 = shadowed)."""
    lx, ly, lz = light
    l2 = math.hypot(lx, ly)
    dx, dy = lx / l2, ly / l2
    tan_e = lz / l2
    sh = np.zeros_like(h)
    for i in range(1, steps + 1):
        t = max_dist * i / steps
        ox = int(round(dx * t * SCALE))
        oy = int(round(dy * t * SCALE))
        q = np.roll(np.roll(h, -oy, axis=0), -ox, axis=1)
        sh = np.maximum(sh, clamp01((q - (h + t * tan_e)) * 1.5))
    return sh
