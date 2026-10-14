"""World Terrain family - albedo and masks painter (numpy only), gongbi blue-green (青绿山水).

Paints the 4800 x 3000 ground colour (sRGB, 2 texels per metre, map aligned, NO lighting) and the
linear masks (R water, G forest floor, B rock/snow altitude, A road) of DESIGN.md 12.2 from a
:class:`ironart.world_terrain_fields.World`.  Unreal lights it in real time, so the albedo holds
only *pigment*: the 3D map reads as a living blue-green landscape painting on silk.

Texel (j, i) covers map [i/2, (i+1)/2) x [j/2, (j+1)/2) metres; master-grid fields are brought to
the texel centres with :func:`ironart.world_terrain_fields.upsample2`.

Layers (each a pigment wash with soft 晕染 edges, granulation and wash tide-lines):

    silk plains     pale silk-toned greens and ochres, broad soft washes, humid south greener,
                    dry west ochre; a hint of field patchwork near the cities (soft parcels)
    steppe/desert   ochre wash with fine dotted texture (点), dune banding very faint
    uplands         赭石 ochre/umber on the foothills and lower slopes; 石绿 malachite on the
                    middle slopes deepening to 石青 azurite on the upper slopes and ridges;
                    hemp-fibre texture strokes (披麻皴) running downslope, moss dots (苔点) on the
                    crests, darker valley washes
    forest floor    deeper malachite green with ink dots (点叶) under the forests
    water           pale azurite rivers and lakes, sand at the coast, azurite sea floor
    roads           pale packed-earth tracks (Albedo.png only; WorldMap.png has none)
"""

import math

import numpy as np

from . import terrain as T
from . import world_terrain_fields as F

AW, AH = 4800, 3000          # albedo size (2 texels per metre)


def hexc(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


#: albedo pigments (sRGB).  Mineral palette of DESIGN.md section 8 laid over silk: plains are
#: pale washes on the silk tone, mountains carry the saturated malachite / azurite.
PAL = {
    "silk": "#DCCBA2",
    "plain_green": "#B4BF94", "plain_green_deep": "#9DB287", "plain_ochre": "#C8BA97",
    "plain_warm": "#C3B691", "field_a": "#B0BD8E", "field_b": "#C6B588", "field_c": "#BABB8E",
    "field_d": "#A9B990", "field_edge": "#97A479",
    "steppe": "#CCBD99", "desert": "#CFBA90", "desert_light": "#D8C7A2", "desert_dot": "#8F7356",
    "foot_ochre": "#C09D70", "ochre": "#A97C52", "umber": "#7F5F42",
    "mal_light": "#8CBFA0", "malachite": "#3E8E6E", "mal_deep": "#2D7258",
    "azu_light": "#7FA6C8", "azurite": "#2B5C8A", "azu_deep": "#244E78",
    "forest": "#6E9670", "forest_deep": "#557E5C", "ink_dot": "#2F4636",
    "sand": "#E4D5AE", "sand_wet": "#C9BC98",
    "river": "#93B2C2", "river_deep": "#7E9FB6", "lake": "#8FAFC2", "lake_deep": "#7095B0",
    "sea_shallow": "#8DAFB8", "sea_mid": "#5F88A4", "sea_deep": "#3E6789",
    "road": "#CDB68C", "road_edge": "#BFA982",
    "ink": "#1E1A16",
}
C = {k: hexc(v) for k, v in PAL.items()}


def lerp(a, b, t):
    """Blend colour images/constants: ``a`` and ``b`` are HxWx3 or 3-vectors, ``t`` HxW."""
    t = np.asarray(t, np.float32)[..., None]
    return a + (b - a) * t


def over(dst, col, t):
    """In-place ``dst = lerp(dst, col, t)`` (saves memory on the 14 M texel image)."""
    t = np.asarray(t, np.float32)[..., None]
    dst += (np.asarray(col, np.float32) - dst) * t
    return dst


class Painter:
    """``crop`` = (tx0, ty0, tx1, ty1) texel window for look iteration: every value inside it is
    identical to the full-map run (noise is defined on the full grid)."""

    def __init__(self, world, log=print, seed=None, crop=None):
        self.w = world
        self.log = log
        self.seed = (seed if seed is not None else world.seed) + 9000
        tx0, ty0, tx1, ty1 = crop or (0, 0, AW, AH)
        self.box = (tx0, ty0, tx1, ty1)
        self.ox, self.oy = tx0, ty0
        self.shape = (ty1 - ty0, tx1 - tx0)
        ys, xs = np.mgrid[ty0:ty1, tx0:tx1].astype(np.float32)
        self.x = (xs + 0.5) * 0.5          # map metres of the texel centres
        self.y = (ys + 0.5) * 0.5
        del xs, ys
        m0x, m0y = tx0 // 2, ty0 // 2
        m1x, m1y = min(F.MAP_W + 1, tx1 // 2 + 2), min(F.MAP_H + 1, ty1 // 2 + 2)
        self.m0 = (m0x, m0y, m1x, m1y)

        def up(a):
            u = F.upsample2(a[m0y:m1y, m0x:m1x])
            return u[ty0 - 2 * m0y: ty0 - 2 * m0y + self.shape[0], tx0 - 2 * m0x: tx0 - 2 * m0x + self.shape[1]]
        self.up = up
        f = world.f
        self.h = up(f["h"])
        self.curv = up(f["curv"])
        self.sd = up(f["sd"])
        self.desert = up(f["desert"])
        self.forest = np.clip(up(f["forest"]), 0, 1)
        self.hill = up(f["hill_env"])
        self.core = up(f["mtn_core"])
        self.foot = up(f["mtn_foot"])
        self.cityd = up(f["city_d"])
        self.lake_sd = up(np.clip(np.nan_to_num(f["lake_sd"], nan=-500.0, neginf=-500.0, posinf=500.0),
                                  -500.0, 500.0).astype(np.float32))
        rd = np.where(np.isfinite(f["river_d"]), f["river_d"], 1e4).astype(np.float32)
        self.river_d = up(rd)
        self.river_hw = up(f["river_hw"])

    # -- noise -----------------------------------------------------------------------------------
    def vn(self, cell_m, seed, octaves=1, gain=0.5):
        """Value noise on the texel grid with features of ``cell_m`` metres (zero mean, ~unit std)."""
        return F.vnoise_box((AH, AW), self.box, cell_m * 2.0, self.seed + seed, octaves, gain)

    def sl(self, x0, y0, x1, y1):
        """Absolute texel window -> (local slices) clipped to the crop, or None."""
        tx0, ty0, tx1, ty1 = self.box
        a0, a1 = max(x0, tx0), min(x1, tx1)
        b0, b1 = max(y0, ty0), min(y1, ty1)
        if a1 <= a0 or b1 <= b0:
            return None
        return (slice(b0 - ty0, b1 - ty0), slice(a0 - tx0, a1 - tx0))

    def strokes(self, length_m, width_m, angle_deg, seed):
        """Anisotropic brush-stroke grain: noise stretched along ``angle`` (zero mean, ~unit std).
        One affine bicubic resample of a small random lattice, evaluated only on this crop (and
        identical to the same window of the full map)."""
        from PIL import Image
        a = math.radians(angle_deg)
        ca, sa = math.cos(a), math.sin(a)
        lp, wp = length_m * 2.0, width_m * 2.0            # texels
        reach = math.hypot(AW, AH) + 8.0
        gu, gv = int(2 * reach / lp) + 8, int(2 * reach / wp) + 8
        rng = np.random.default_rng(self.seed + seed)
        lat = Image.fromarray(rng.standard_normal((gv, gu)).astype(np.float32), "F")
        tx0, ty0, tx1, ty1 = self.box
        ou, ov = reach / lp + 4.0, reach / wp + 4.0
        data = (ca / lp, sa / lp, (ca * (tx0 + 0.5) + sa * (ty0 + 0.5)) / lp + ou,
                -sa / wp, ca / wp, (-sa * (tx0 + 0.5) + ca * (ty0 + 0.5)) / wp + ov)
        out = lat.transform((tx1 - tx0, ty1 - ty0), Image.AFFINE, data, resample=Image.BICUBIC)
        return np.asarray(out, np.float32) / 0.908

    def wash(self, cell_m, seed, octaves=2):
        """A watercolour wash: soft blotches (0..1) plus the darker tide-line where a wash dried
        (returned separately, 0..1)."""
        n = self.vn(cell_m, seed, octaves, 0.5)
        body = T.smoothstep(-1.0, 1.0, n)
        tide = np.exp(-(n / 0.07) ** 2)
        return body, tide

    def granulation(self, seed):
        """Fine pigment granulation (zero mean)."""
        return 0.6 * self.vn(0.7, seed, 1) + 0.4 * self.vn(2.2, seed + 1, 1)

    def dots(self, cell_m, density, seed, soft=0.25):
        """Blobby ink dots (0..1): thresholded small noise, ``density`` 0..1 of the area."""
        n = self.vn(cell_m, seed, 1)
        thr = 2.6 - 3.0 * np.clip(density, 0.0, 1.0)
        return T.smoothstep(thr, thr + soft, n)

    def flow_strokes(self, angle, length_m, width_m, seed, n_dir=6):
        """Texture strokes aligned with a per-texel ``angle`` field (radians): fixed-orientation
        stroke noises blended by cos^4 weights of the angle difference (orientation period pi)."""
        acc = np.zeros(self.shape, np.float32)
        wsum = np.zeros(self.shape, np.float32)
        for k in range(n_dir):
            th = math.pi * k / n_dir
            wk = np.maximum(np.cos(2.0 * (angle - th)), 0.0) ** 3
            acc += wk * self.strokes(length_m, width_m, math.degrees(th), seed + 13 * k)
            wsum += wk
        return acc / np.maximum(wsum, 1e-4)

    # -- layers ----------------------------------------------------------------------------------
    def plains(self):
        """Silk plains: pale malachite / ochre washes, humid south and river lands greener, the
        dry west ochre; broad soft washes with tide-lines and granulation."""
        h, x, y = self.h, self.x, self.y
        macro = self.vn(300.0, 1, 3, 0.5)
        moist = 0.5 + 0.2 * macro
        moist += 0.30 * np.exp(-np.maximum(self.river_d - self.river_hw, 0) / 90.0)
        moist += 0.15 * np.exp(-np.maximum(-self.lake_sd, 0) / 90.0)
        moist -= 0.30 * T.smoothstep(900.0, 250.0, x) * T.smoothstep(1000.0, 600.0, y)
        moist += 0.14 * T.smoothstep(700.0, 1300.0, y)
        moist = np.clip(moist, 0, 1)
        self.moist = moist
        col = lerp(C["plain_ochre"], C["plain_green"], T.smoothstep(0.2, 0.62, moist))
        col = over(col, C["plain_green_deep"], 0.7 * T.smoothstep(0.62, 0.95, moist))
        # broad and medium washes: a little more pigment in some places, tide-lines where they dried
        b1, t1 = self.wash(110.0, 2)
        b2, t2 = self.wash(36.0, 3)
        col = over(col, C["plain_warm"], 0.22 * (1 - b1) * (1 - moist))
        col = over(col, C["plain_green_deep"], 0.18 * b2 * moist)
        col *= (1.0 - 0.035 * t1 - 0.025 * t2)[..., None]
        # brush grain (soft, two directions) and granulation
        st = 0.6 * self.strokes(10.0, 1.4, 22.0, 7) + 0.4 * self.strokes(7.0, 1.2, -38.0, 8)
        col *= (1.0 + 0.018 * st + 0.022 * self.granulation(9))[..., None]
        return col

    def fields(self, col):
        """A hint of field patchwork around the cities: soft painted parcels (no ruled edges) in
        alternating pale greens and ochres, fading out irregularly with distance."""
        rng = np.random.default_rng(self.seed + 50)
        fieldm = np.zeros(self.shape, np.float32)
        tints = np.stack([C["field_a"], C["field_b"], C["field_c"], C["field_d"]])
        n_low = self.vn(80.0, 51, 2)
        jag = self.vn(9.0, 52, 2)
        for (key, cx, cy, size) in self.w.cities:
            R = 70.0 + 35.0 * size
            x0, x1 = int(max(0, (cx - R - 40) * 2)), int(min(AW, (cx + R + 40) * 2))
            y0, y1 = int(max(0, (cy - R - 40) * 2)), int(min(AH, (cy + R + 40) * 2))
            sl = self.sl(x0, y0, x1, y1)
            if sl is None:
                continue
            X, Y = self.x[sl], self.y[sl]
            ang = rng.uniform(0, np.pi)
            ca, sa = math.cos(ang), math.sin(ang)
            wu = 4.0 * n_low[sl]
            U = (X - cx) * ca + (Y - cy) * sa + wu
            V = -(X - cx) * sa + (Y - cy) * ca + 0.6 * wu
            cw = rng.uniform(22.0, 42.0, 64)
            cols = np.cumsum(cw)
            cols -= cols[32]
            ci = np.clip(np.searchsorted(cols, U), 1, 63)
            roff = rng.uniform(0, 60.0, 64)
            rh = rng.uniform(28.0, 60.0, 64)
            Vr = V + roff[ci]
            ri = np.floor(Vr / rh[ci]).astype(np.int64)
            hsh = (ci * 73856093 + (ri + 1000) * 19349663 + size * 83492791) % 1000003
            pick = hsh % 4
            r2 = (hsh % 7919) / 7919.0
            pc = tints[pick] * (0.97 + 0.06 * (hsh % 101) / 101.0)[..., None]
            du = np.minimum(U - cols[ci - 1], cols[ci] - U)
            dv = np.minimum(Vr - ri * rh[ci], (ri + 1) * rh[ci] - Vr)
            edge = np.minimum(du, dv)
            # parcels kept by an irregular, parcel-wise extent around the city
            dcity = np.hypot(X - cx, Y - cy)
            keep = T.smoothstep(R, 0.55 * R, dcity + 40.0 * (r2 - 0.5) + 25.0 * n_low[sl])
            keep *= T.smoothstep(F.PAD_FLAT[size] + 6.0, F.PAD_FLAT[size] + 40.0, dcity)
            ok = (T.smoothstep(26.0, 18.0, self.h[sl]) * T.smoothstep(1.5, 3.0, self.h[sl])
                  * (1 - T.smoothstep(0.15, 0.4, self.forest[sl]))
                  * (1 - T.smoothstep(0.1, 0.35, self.core[sl] + self.hill[sl]))
                  * T.smoothstep(4.0, 10.0, self.river_d[sl] - self.river_hw[sl])
                  * T.smoothstep(-6.0, -14.0, self.lake_sd[sl])
                  * (1 - T.smoothstep(0.25, 0.45, self.desert[sl])))
            m = np.clip(keep * ok * (0.3 + 0.35 * (r2 > 0.35)), 0, 1)
            # soft painted parcel edges (a slightly deeper wash pools along them), ragged
            e = T.smoothstep(0.3, 3.0, edge + 1.2 * jag[sl])
            pc = pc * (0.965 + 0.035 * e)[..., None]
            prev = fieldm[sl]
            sub = col[sl]
            sub += (pc - sub) * (m * (1 - prev))[..., None]
            col[sl] = sub
            fieldm[sl] = np.maximum(prev, m)
        self.fieldm = fieldm
        self.log("[paint] field washes %.1f %% of the map" % (100.0 * float((fieldm > 0.3).mean())))
        return col

    def steppe_desert(self, col):
        """Ochre steppe and desert washes with fine dotted texture."""
        des = self.desert
        n = self.vn(50.0, 11, 3)
        st = lerp(C["steppe"], C["plain_ochre"], 0.4 * T.smoothstep(-1.0, 1.0, n))
        col = over(col, st, 0.85 * np.clip(T.smoothstep(0.0, 0.5, des + 0.12 * n), 0, 1))
        band = 0.5 + 0.5 * np.sin((self.x * 0.8 + self.y * 0.6) / 23.0 + 0.8 * self.vn(80.0, 12, 2))
        sand = lerp(C["desert"], C["desert_light"], 0.35 * band + 0.25 * T.smoothstep(-1, 1, self.vn(140.0, 17, 2)))
        core = np.clip(T.smoothstep(0.4, 0.85, des + 0.15 * n), 0, 1)
        col = over(col, sand, core)
        # 点: fine ochre-ink dots, denser in the sand, sparse in the steppe
        dens = 0.10 * T.smoothstep(0.1, 0.5, des) + 0.16 * core
        d1 = self.dots(0.55, dens, 13)
        d2 = self.dots(1.1, 0.5 * dens, 14)
        col = over(col, C["desert_dot"], 0.55 * d1 + 0.35 * d2)
        self.sand_core = core
        self.steppe = T.smoothstep(0.1, 0.5, des)
        return col

    def uplands(self, col):
        """青绿: ochre/umber foothills and lower slopes, malachite middle slopes deepening to
        azurite on the upper slopes.  The colour follows the form as in a painting: the higher
        pigment runs down the ridges and spurs, the valleys are washed deeper (晕染 from the
        gullies outwards) and carry the hemp-fibre strokes (披麻皴); ridge crests get a pale
        highlight wash and moss dots (苔点)."""
        h = self.h
        hm = self.w.f["h"]
        n1 = self.vn(34.0, 21, 2)
        n2 = self.vn(9.0, 22, 2)
        # form: ridge (+) / valley (-) at three scales (master grid -> texels)
        rl = self.up(np.clip((hm - F.fast_blur(hm, 30.0)) / 16.0, -1.0, 1.0))
        rm = self.up(np.clip((hm - F.fast_blur(hm, 12.0)) / 7.0, -1.0, 1.0))
        rs = self.up(np.clip((hm - F.fast_blur(hm, 4.0)) / 2.2, -1.0, 1.0))
        form = 0.45 * rl + 0.35 * rm + 0.2 * rs
        relief = np.clip(np.maximum(self.foot, self.hill) + T.smoothstep(18.0, 40.0, h), 0, 1)
        relief *= T.smoothstep(6.0, 16.0, h) * (1 - 0.6 * self.sand_core)
        valley = T.smoothstep(0.02, 0.5, -form)
        ridge = T.smoothstep(0.02, 0.5, form)
        # pigment height: the higher pigments run down the ridges, valleys keep the lower ones
        hp = h + 10.0 * n1 + 34.0 * form
        # 1. ochre underpainting on foothills and lower slopes (umber washed into the valleys)
        och = lerp(C["foot_ochre"], C["ochre"], T.smoothstep(20.0, 70.0, hp))
        och = lerp(och, C["umber"], 0.55 * valley * T.smoothstep(20.0, 60.0, h))
        col = over(col, och, 0.82 * relief * T.smoothstep(8.0, 32.0, hp))
        # hills: pale malachite over the ochre on their tops and shoulders
        hilltop = (self.hill * T.smoothstep(20.0, 46.0, hp) * (1 - T.smoothstep(0.3, 0.6, self.core)))
        col = over(col, lerp(C["mal_light"], C["malachite"], 0.25 + 0.3 * valley), 0.55 * hilltop)
        # 2. malachite on the middle slopes, 3. azurite on the upper slopes (soft 晕染 gradients)
        mid = T.smoothstep(40.0, 92.0, hp)
        top = T.smoothstep(105.0, 172.0, hp)
        mal = lerp(C["malachite"], C["mal_deep"], 0.2 + 0.6 * valley + 0.12 * T.smoothstep(-0.6, 0.9, n2))
        col = over(col, mal, 0.92 * mid)
        azu = lerp(C["azurite"], C["azu_deep"], 0.5 * valley)
        azu = lerp(azu, C["azu_light"], 0.18 * T.smoothstep(0.0, 1.5, n2))
        col = over(col, azu, (0.62 + 0.22 * T.smoothstep(-1.0, 1.0, self.vn(16.0, 36, 2))) * top)
        # ridge highlight: a paler wash on the crests and spur backs (lead white over the pigment)
        hi = ridge * T.smoothstep(40.0, 100.0, h) * (0.6 + 0.4 * T.smoothstep(-0.5, 1.0, n2))
        hl = lerp(C["mal_light"], C["azu_light"], top)
        col = over(col, hl, 0.32 * hi)
        # valley wash: deeper ink-green pooled in the gullies
        col = over(col, lerp(C["mal_deep"], C["ink"], 0.35), 0.3 * valley * T.smoothstep(30.0, 80.0, h))
        # 4. hemp-fibre texture strokes (披麻皴) running down the slope in the valleys and on
        #    the steep flanks
        hs = F.fast_blur(hm, 2.0)
        gy, gx = np.gradient(hs)
        ang_m = np.arctan2(gy, gx).astype(np.float32)
        self.slope_s = self.up(np.hypot(gx, gy).astype(np.float32))
        ca = self.up(np.cos(ang_m).astype(np.float32))
        sa = self.up(np.sin(ang_m).astype(np.float32))
        del hs, gx, gy, ang_m
        ang = np.arctan2(sa, ca)
        del ca, sa
        steep = T.smoothstep(0.25, 0.9, self.slope_s) * T.smoothstep(40.0, 75.0, hp)
        fib = self.flow_strokes(ang, 26.0, 1.0, 31)
        fib2 = self.flow_strokes(ang, 12.0, 0.8, 47)
        lines = 0.85 * T.smoothstep(1.1, 1.7, fib) + 0.5 * T.smoothstep(1.3, 1.9, fib2)
        ink_t = lerp(C["ink"], C["mal_deep"], 0.5)
        col = over(col, ink_t, np.clip(0.42 * lines * steep * (0.25 + 0.75 * valley), 0, 1))
        # 5. moss dots (苔点) clustered along the crests
        crest = T.smoothstep(0.45, 0.85, form) * T.smoothstep(70.0, 120.0, h)
        clus = T.smoothstep(0.0, 0.8, self.vn(7.0, 35, 1))
        moss = self.dots(1.3, 0.45, 33) * crest * clus
        col = over(col, lerp(C["ink"], C["mal_deep"], 0.25), 0.75 * moss)
        # granulation of the mineral pigments
        col *= (1.0 + 0.03 * self.vn(1.4, 34, 2) * relief)[..., None]
        self.mid, self.top = mid, top
        return col

    def forest_floor(self, col):
        """Deeper malachite under the forests with ink dots (点叶)."""
        fz = T.smoothstep(0.12, 0.6, self.forest)
        n = self.vn(14.0, 61, 2)
        fc = lerp(C["forest"], C["forest_deep"], T.smoothstep(-0.8, 1.0, n))
        on_mtn = 1 - 0.7 * self.top
        col = over(col, fc, 0.82 * fz * on_mtn)
        d1 = self.dots(1.0, 0.28, 62)
        d2 = self.dots(1.8, 0.16, 63)
        col = over(col, C["ink_dot"], (0.5 * d1 + 0.4 * d2) * fz * on_mtn)
        return col

    def water(self, col):
        """Pale azurite rivers and lakes, sand at the coast, azurite sea floor.  Returns the
        water mask."""
        h = self.h
        rd = self.river_d - self.river_hw                 # metres outside the channel edge
        n = self.vn(10.0, 71, 2)
        n2 = self.vn(2.5, 72)
        # river banks: a soft greener, then pale sandy rim
        rip = np.exp(-np.maximum(rd, 0) / 10.0) * (1 - 0.6 * self.sand_core) * (1 - self.top)
        col = over(col, C["plain_green_deep"], 0.4 * rip)
        col = over(col, C["sand_wet"], 0.5 * T.smoothstep(2.4, 0.4, rd + 0.4 * n2))
        rw = T.smoothstep(0.5, -0.5, rd)
        across = np.clip(self.river_d / np.maximum(self.river_hw, 0.5), 0, 1)
        wc = lerp(C["river_deep"], C["river"], T.smoothstep(0.1, 0.9, across))
        wc *= (1.0 + 0.02 * n2)[..., None]
        col = over(col, wc, rw)
        lsd = self.lake_sd
        lake = T.smoothstep(-0.5, 0.5, lsd)
        lc = lerp(C["lake"], C["lake_deep"], T.smoothstep(4.0, 40.0, lsd + 6.0 * n))
        shore = T.smoothstep(-3.5, -0.3, lsd) * (1 - lake)
        col = over(col, C["sand_wet"], 0.7 * shore)
        col = over(col, lc, lake)
        # coast: pale sand band, a wet line, then the sea floor under the sea plane
        sd = self.sd
        beach = T.smoothstep(16.0 + 6.0 * n, 3.0, sd) * T.smoothstep(4.0, 1.6, h) * T.smoothstep(-0.5, 0.2, h)
        col = over(col, C["sand"] * (1.0 + 0.03 * n2[..., None]), np.clip(beach, 0, 1))
        col = over(col, C["sand_wet"], 0.8 * T.smoothstep(0.9, 0.05, h) * T.smoothstep(-1.5, -0.1, h))
        sea = T.smoothstep(0.05, -0.4, h) * (lake < 0.5)
        dep = np.clip(-h, 0, 40.0)
        sb = lerp(C["sea_shallow"], C["sea_mid"], T.smoothstep(1.0, 14.0, dep + 2.0 * n))
        sb = lerp(sb, C["sea_deep"], T.smoothstep(16.0, 38.0, dep))
        col = over(col, sb, sea)
        water = np.maximum(np.maximum(rw, lake), T.smoothstep(0.1, -0.3, h) * (lake < 0.5))
        self.river_w = rw
        self.lake_w = lake
        return col, np.clip(water, 0, 1)

    def roads(self, col):
        """Pale packed-earth tracks + road mask.  Returns (albedo with roads, mask)."""
        road = np.zeros(self.shape, np.float32)
        edge = np.zeros(self.shape, np.float32)
        wob_all = self.vn(3.0, 99, 2)
        for r in self.w.roads:
            pts = np.asarray(r["pts"], np.float64)
            half = 0.5 * r["width"]
            R = half + 3.0
            sy, sx, org = F.window(pts, R, (AH // 2 + 1, AW // 2 + 1))
            ty0, ty1, tx0, tx1 = sy.start * 2, min(AH, sy.stop * 2), sx.start * 2, min(AW, sx.stop * 2)
            ty0, ty1 = max(ty0, self.box[1]), min(ty1, self.box[3])
            tx0, tx1 = max(tx0, self.box[0]), min(tx1, self.box[2])
            if ty1 <= ty0 or tx1 <= tx0:
                continue
            shp = (ty1 - ty0, tx1 - tx0)
            d, t = F.polyline_field((pts - 0.25) * 2.0, R * 2.0, want_t=True, shape=shp,
                                    origin=(tx0, ty0))
            d = d * 0.5
            ok = np.isfinite(d)
            d = np.where(ok, d, 1e4)
            a = self.w.sc["cities"][r["a"]]
            b = self.w.sc["cities"][r["b"]]
            ty0, ty1 = ty0 - self.oy, ty1 - self.oy
            tx0, tx1 = tx0 - self.ox, tx1 - self.ox
            X, Y = self.x[ty0:ty1, tx0:tx1], self.y[ty0:ty1, tx0:tx1]
            ra = F.PAD_FLAT[int(a.get("size", 1))] * 0.6
            rb = F.PAD_FLAT[int(b.get("size", 1))] * 0.6
            fade = (T.smoothstep(ra - 8, ra + 10, np.hypot(X - a["x"], Y - a["y"]))
                    * T.smoothstep(rb - 8, rb + 10, np.hypot(X - b["x"], Y - b["y"])))
            dry = (1 - self.river_w[ty0:ty1, tx0:tx1]) * (1 - self.lake_w[ty0:ty1, tx0:tx1]) \
                * T.smoothstep(-0.2, 0.4, self.h[ty0:ty1, tx0:tx1])
            wob = 0.4 * wob_all[ty0:ty1, tx0:tx1]
            cov = T.smoothstep(half + 0.5, half - 0.5, d + wob) * fade * dry
            ed = T.smoothstep(half + 2.2, half + 0.2, d + wob) * (1 - cov) * fade * dry
            road[ty0:ty1, tx0:tx1] = np.maximum(road[ty0:ty1, tx0:tx1], cov)
            edge[ty0:ty1, tx0:tx1] = np.maximum(edge[ty0:ty1, tx0:tx1], ed)
        out = col.copy()
        out = lerp(out, C["road_edge"], 0.35 * edge)
        rc = C["road"] * (1.0 + 0.03 * self.vn(2.5, 91)[..., None])
        out = lerp(out, rc, 0.85 * road)
        return out, road

    # -- run -------------------------------------------------------------------------------------
    def paint(self):
        import time
        t0 = time.time()
        col = self.plains()
        col = self.fields(col)
        col = self.steppe_desert(col)
        col = self.uplands(col)
        col = self.forest_floor(col)
        col, water = self.water(col)
        self.base = np.clip(col, 0, 1)
        withroads, road = self.roads(self.base)
        self.albedo = np.clip(withroads, 0, 1)
        self.water = water
        self.road = road
        self.log("[paint] albedo %.1fs" % (time.time() - t0))
        return self

    def masks(self):
        """RGBA uint8: R water, G forest floor, B rock/snow altitude, A road (>= 1: see note)."""
        r = self.water
        g = np.clip(T.smoothstep(0.1, 0.6, self.forest) * (1 - self.water), 0, 1)
        alt = T.smoothstep(124.0, 148.0, self.h)
        steep = T.smoothstep(1.2, 1.9, self.slope_s) * T.smoothstep(60.0, 100.0, self.h)
        b = np.clip(np.maximum(alt, 0.6 * steep), 0, 1) * (1 - self.water) * (1 - 0.5 * g)
        # A never 0: Unreal's PNG import rewrites the RGB of alpha-0 pixels (FillPNGZeroAlpha),
        # which would wipe the R/G/B masks almost everywhere; 1/255 road is invisible.
        a = np.maximum(self.road, 1.0 / 255.0)
        m = np.stack([r, g, b, a], -1)
        return np.round(np.clip(m, 0, 1) * 255.0).astype(np.uint8)

    def albedo8(self, roads=True):
        img = self.albedo if roads else self.base
        return np.round(np.clip(img, 0, 1) * 255.0).astype(np.uint8)
