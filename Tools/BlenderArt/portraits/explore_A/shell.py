"""Garment shells fitted to the MakeHuman bust (bpy + numpy).

The bust surface is sampled by rays from a point inside the upper chest over an (azimuth,
elevation) grid; every garment layer, collar band, armour row and ornament is placed in that
(az, z) parameter space, so clothing fits every body shape and stacks cleanly in layers.

az: degrees, 0 = front (-Y), +90 = the character's left (+X), +-180 = back.
"""

import math

import bpy
import numpy as np
from mathutils import Vector


def _dir(az, el):
    a, e = np.radians(az), np.radians(el)
    return np.stack([np.sin(a) * np.cos(e), -np.cos(a) * np.cos(e), np.sin(e) * np.ones_like(a)], -1)


def _blur2(a, s_az, s_el, wrap=True):
    from texgen import blur
    if wrap:
        pad = int(3 * s_az) + 1
        a2 = np.concatenate([a[:, -pad:], a, a[:, :pad]], 1)
        out = _gauss_sep(a2, s_el, s_az)
        return out[:, pad:-pad]
    return _gauss_sep(a, s_el, s_az)


def _gauss_sep(a, sy, sx):
    def k1(s):
        r = max(1, int(3 * s + 0.5))
        k = np.exp(-0.5 * (np.arange(-r, r + 1) / max(s, 1e-3)) ** 2)
        return k / k.sum(), r
    out = a.astype(np.float64)
    if sy > 0:
        k, r = k1(sy)
        p = np.pad(out, ((r, r), (0, 0)), mode="edge")
        out = sum(k[i] * p[i:i + out.shape[0]] for i in range(2 * r + 1))
    if sx > 0:
        k, r = k1(sx)
        p = np.pad(out, ((0, 0), (r, r)), mode="edge")
        out = sum(k[i] * p[:, i:i + out.shape[1]] for i in range(2 * r + 1))
    return out


class Shell:
    def __init__(self, surf, origin, az_step=1.5, el_min=-84.0, el_max=84.0, el_step=1.0,
                 smooth=(2.5, 2.0), hull=True, hull_zmax=None):
        self.O = np.array(origin, np.float64)
        self.az = np.arange(-180.0, 180.0, az_step)
        self.el = np.arange(el_min, el_max + 1e-6, el_step)
        AZ, EL = np.meshgrid(self.az, self.el)
        D = _dir(AZ, EL)
        r = np.full(AZ.shape, np.nan)
        O = Vector(self.O)
        bvh = surf.bvh
        for i in range(D.shape[0]):
            for j in range(D.shape[1]):
                d = Vector(D[i, j])
                loc, nrm, idx, dist = bvh.ray_cast(O, d, 2.0)
                if loc is None:
                    continue
                r[i, j] = dist
                if hull and (hull_zmax is None or loc.z < hull_zmax):
                    # outermost surface along the ray (wraps arm + torso like a robe); start a
                    # bounded distance out so the head/chin is never picked up
                    far = min(0.5, dist * 3.0)
                    loc2, n2, i2, d2 = bvh.ray_cast(O + d * far, -d, far)
                    if loc2 is not None and (hull_zmax is None or loc2.z < hull_zmax):
                        r[i, j] = max(dist, far - d2)
        # misses (below the crop / through the open neck top): extend columns
        for j in range(r.shape[1]):
            col = r[:, j]
            ok = np.isfinite(col)
            if not ok.any():
                col[:] = 0.15
                continue
            first = np.argmax(ok)
            last = len(col) - 1 - np.argmax(ok[::-1])
            # below: keep the hit point's horizontal distance (vertical extension of the torso)
            e0 = np.radians(self.el[first])
            hd = col[first] * math.cos(e0)
            for i in range(first):
                col[i] = hd / max(math.cos(np.radians(self.el[i])), 0.2)
            col[last + 1:] = col[last]
            bad = ~np.isfinite(col)
            if bad.any():
                col[bad] = np.interp(np.where(bad)[0], np.where(~bad)[0], col[~bad])
            r[:, j] = col
        self.r_raw = r
        # smooth, but never inside the body (shoulder/arm peaks would otherwise poke through)
        rb = _blur2(r, smooth[0], smooth[1])
        self.r = _blur2(np.maximum(rb, r), smooth[0] * 0.5, smooth[1] * 0.5)
        self.r = np.maximum(self.r, r)
        self.D = D
        self.P = self.O + D * self.r[..., None]
        self.Z = self.P[..., 2]

    # ------------------------------------------------------------------------------ queries
    def el_at(self, az, z):
        """Elevation where the shell column at ``az`` reaches height ``z`` (first crossing)."""
        az = np.atleast_1d(az)
        z = np.broadcast_to(np.atleast_1d(z), az.shape)
        out = np.empty(az.shape)
        for k, (a, zz) in enumerate(zip(az, z)):
            j = int(round((a + 180.0) / (self.az[1] - self.az[0]))) % len(self.az)
            zc = np.maximum.accumulate(self.Z[:, j])
            out[k] = np.interp(zz, zc + np.arange(len(zc)) * 1e-7, self.el)
        return out

    def r_at(self, az, el):
        """Bilinear smoothed radius at (az, el) arrays."""
        az = np.asarray(az, np.float64)
        el = np.asarray(el, np.float64)
        da = self.az[1] - self.az[0]
        de = self.el[1] - self.el[0]
        fj = ((az + 180.0) / da) % len(self.az)
        fi = np.clip((el - self.el[0]) / de, 0, len(self.el) - 1.001)
        j0 = np.floor(fj).astype(int) % len(self.az)
        j1 = (j0 + 1) % len(self.az)
        i0 = np.floor(fi).astype(int)
        i1 = np.minimum(i0 + 1, len(self.el) - 1)
        tj = fj - np.floor(fj)
        ti = fi - i0
        R = self.r
        return ((R[i0, j0] * (1 - tj) + R[i0, j1] * tj) * (1 - ti)
                + (R[i1, j0] * (1 - tj) + R[i1, j1] * tj) * ti)

    def point(self, az, el, offset=0.0):
        az = np.asarray(az, np.float64)
        el = np.asarray(el, np.float64)
        return self.O + _dir(az, el) * (self.r_at(az, el) + offset)[..., None]

    def normal(self, az, el, eps=0.6):
        p0 = self.point(az, el)
        pa = self.point(az + eps, el)
        pe = self.point(az, el + eps)
        n = np.cross(pe - p0, pa - p0)
        n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-12
        # outward
        out = p0 - self.O
        flip = (n * out).sum(-1) < 0
        n[flip] *= -1
        return n

    # ---------------------------------------------------------------------------- building
    def layer(self, name, cut_z, offset, rows=80, el_bottom=None, folds=None, mats=None,
              band=None, coll=None, seed=0, az_range=None, mat_fn=None, flare=None):
        """Garment layer from the bottom up to the neckline ``cut_z(az) -> z`` (array fn).

        offset   metres off the body (float or fn(az, t) with t = 0 bottom .. 1 neckline)
        folds    fn(az, t) -> extra offset (cloth folds)
        band     (width_m, extra_offset, rolled) collar band along the neckline (material 1)
        flare    fn(az, t) -> extra radial offset added at the bottom (sleeves/drape)
        Returns the object; UV u = az arc, v = metres down from the neckline."""
        az = self.az if az_range is None else self.az[(self.az >= az_range[0]) & (self.az <= az_range[1])]
        el_top = self.el_at(az, cut_z(az))
        el_bot = np.full(az.shape, self.el[0] if el_bottom is None else el_bottom)
        t = np.linspace(0, 1, rows)
        EL = el_bot[None, :] + (el_top - el_bot)[None, :] * t[:, None]
        AZ = np.broadcast_to(az[None, :], EL.shape)
        off = offset(AZ, t[:, None] * np.ones_like(AZ)) if callable(offset) else np.full(EL.shape, offset)
        if folds is not None:
            off = off + folds(AZ, t[:, None] * np.ones_like(AZ))
        if flare is not None:
            off = off + flare(AZ, t[:, None] * np.ones_like(AZ))
        P = self.point(AZ, EL, off)
        # distance down from the neckline along each column (for UV v and the collar band)
        seg = np.linalg.norm(np.diff(P, axis=0), axis=-1)
        down = np.zeros(P.shape[:2])
        down[:-1] = np.cumsum(seg[::-1], axis=0)[::-1]
        if band is not None:
            bw, boff, roll = band
            inb = np.clip(1.0 - down / bw, 0, 1)
            lift = boff * np.sqrt(np.clip(inb * 4, 0, 1))
            n = self.normal(AZ, EL)
            P = P + n * lift[..., None]
            if roll:
                # roll the top edge over: last row tucked inward
                P[-1] = P[-1] - n[-1] * boff * 0.6
        nr, nc = P.shape[:2]
        wrap = az_range is None
        verts = P.reshape(-1, 3)
        faces = []
        mid = []
        for i in range(nr - 1):
            for j in range(nc - (0 if wrap else 1)):
                j2 = (j + 1) % nc
                a, b_, c, d = i * nc + j, i * nc + j2, (i + 1) * nc + j2, (i + 1) * nc + j
                faces.append((a, b_, c, d))
                mid.append((i, j))
        me = bpy.data.meshes.new(name)
        me.from_pydata(verts.tolist(), [], faces)
        # UVs
        circ = np.radians(AZ) * 0.16
        uvl = me.uv_layers.new(name="UVMap")
        loop_v = np.empty(len(me.loops), np.int64)
        me.loops.foreach_get("vertex_index", loop_v)
        U = circ.reshape(-1)
        V = down.reshape(-1)
        uv = np.stack([U[loop_v], V[loop_v]], 1).astype(np.float32)
        # wrap seam: faces crossing az = +-180 get u continued
        uvl.data.foreach_set("uv", uv.ravel())
        if band is not None or mat_fn is not None:
            mi = np.zeros(len(faces), np.int32)
            for k, (i, j) in enumerate(mid):
                dmid = (down[i, j] + down[i + 1, j]) / 2
                if band is not None and dmid < band[0]:
                    mi[k] = 1
                if mat_fn is not None:
                    m = mat_fn(AZ[i, j], dmid, t[i])
                    if m is not None:
                        mi[k] = m
            me.polygons.foreach_set("material_index", mi)
        for p in me.polygons:
            p.use_smooth = True
        for m in (mats or []):
            me.materials.append(m)
        ob = bpy.data.objects.new(name, me)
        (coll or bpy.context.scene.collection).objects.link(ob)
        ob["down"] = 0
        self.last = dict(AZ=AZ, EL=EL, P=P, down=down, off=off)
        return ob

    def strip(self, name, path_az, path_z, width, offset, mat, coll=None, n=120, thick=0.0025,
              side_bias=0.0, profile=None):
        """A band (collar edge, trim) following a polyline in (az, z) space, laid on the shell
        at ``offset``; ``side_bias`` shifts it across its own width (-1..1)."""
        s = np.linspace(0, 1, len(path_az))
        tt = np.linspace(0, 1, n)
        az = np.interp(tt, s, path_az)
        z = np.interp(tt, s, path_z)
        el = self.el_at(az, z)
        c = self.point(az, el, offset)
        nrm = self.normal(az, el)
        tan = np.gradient(c, axis=0)
        tan /= np.linalg.norm(tan, axis=1, keepdims=True) + 1e-12
        side = np.cross(nrm, tan)
        side /= np.linalg.norm(side, axis=1, keepdims=True) + 1e-12
        cols = 5
        w = np.linspace(-0.5, 0.5, cols) + side_bias * 0.5
        prof = profile if profile is not None else (lambda u: np.sqrt(np.clip(1 - (2 * u) ** 2, 0, 1)))
        verts = []
        for k in range(cols):
            verts.append(c + side * (w[k] * width) + nrm * (thick * prof(w[k]))[None])
        V = np.stack(verts, 1)  # n, cols, 3
        faces = []
        for i in range(n - 1):
            for k in range(cols - 1):
                faces.append((i * cols + k, i * cols + k + 1, (i + 1) * cols + k + 1, (i + 1) * cols + k))
        me = bpy.data.meshes.new(name)
        me.from_pydata(V.reshape(-1, 3).tolist(), [], faces)
        arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(c, axis=0), axis=1))])
        uvl = me.uv_layers.new(name="UVMap")
        loop_v = np.empty(len(me.loops), np.int64)
        me.loops.foreach_get("vertex_index", loop_v)
        U = np.repeat(arc, cols)
        Vv = np.tile((w + 0.5) * width, n)
        uv = np.stack([U[loop_v], Vv[loop_v]], 1).astype(np.float32)
        uvl.data.foreach_set("uv", uv.ravel())
        for p in me.polygons:
            p.use_smooth = True
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        (coll or bpy.context.scene.collection).objects.link(ob)
        return ob, c, nrm, side
