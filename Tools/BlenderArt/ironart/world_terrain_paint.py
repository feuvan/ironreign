"""World Terrain family - albedo and masks painter (numpy only), gongbi blue-green (青绿山水).

Paints the 4800 x 3000 ground colour (sRGB, 2 texels per metre, map aligned, NO lighting) and the
linear masks (R water, G forest floor, B rock/snow altitude, A road) of DESIGN.md 12.2 from a
:class:`ironart.world_terrain_fields.World`.  Unreal lights it in real time, so the albedo holds
only *pigment*: the 3D map reads as a living blue-green landscape painting on silk.  Nothing in it
depends on a light direction (no hillshade, no cast shadow); the form is told the way a painter
tells it: colour layered by height, deeper in the gullies (晕染), paler on the crests, and brush
texture that runs down the fall lines.

Texel (j, i) covers map [i/2, (i+1)/2) x [j/2, (j+1)/2) metres; master-grid fields are brought to
the texel centres with :func:`ironart.world_terrain_fields.upsample2`.

Layers, bottom to top (every one a pigment wash with soft edges, granulation and brush grain):

    silk plains     pale silk-toned greens and ochres in broad soft washes (humid south and the
                    river lands greener, the dry north-west ochre), wash tide-lines, brush grain
    fields          a hint of field patchwork near the cities: parcels in pale greens, wheat and
                    fallow ochre with darker balks, fading out irregularly (never a disc)
    steppe/desert   ochre wash with fine dotted texture (点) and faint wind streaks
    uplands         hills: ochre flanks under pale malachite tops; ranges: 赭石 ochre on the
                    foothills and lower slopes, 石绿 malachite on the middle slopes deepening to
                    石青 azurite on the upper slopes and crests, the boundaries brushed down the
                    fall lines; gullies washed deeper, crests paler; hemp-fibre strokes (披麻皴)
                    running downslope and moss dots (苔点) along the crests
    forest floor    deeper malachite green densely dotted with ink (点叶)
    water           pale azurite rivers and lakes with faint 水纹 ripple lines, pale sand at the
                    coast, azurite sea floor deepening offshore
    roads           pale packed-earth tracks with darker worn edges
"""

import math

import numpy as np

from . import terrain as T
from . import world_terrain_fields as F

AW, AH = 4800, 3000          # albedo size (2 texels per metre)


def hexc(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


#: albedo pigments (sRGB).  The DESIGN.md mineral palette laid over silk: plains are pale washes on
#: the silk tone, the ranges carry the saturated malachite / azurite over an ochre underpainting.
PAL = {
    # plains (silk-toned washes)
    "plain_silk": "#D6CBA4", "plain_green": "#BCC39C", "plain_green_deep": "#A6B58F",
    "plain_ochre": "#D2C098", "plain_warm": "#CDB68C", "wash_tide": "#9C9A78",
    # fields
    "field_a": "#B3C094", "field_b": "#D3C48E", "field_c": "#C9B387", "field_d": "#A6BA8C",
    "field_balk": "#8E9670",
    # steppe / desert
    "steppe": "#D2BC90", "desert": "#D4B583", "desert_light": "#DEC69A", "desert_dot": "#93704A",
    # uplands
    "foot_ochre": "#C8A57A", "ochre": "#B07C4E", "umber": "#86603F",
    "hill_green": "#ABBD8C", "mal_light": "#8CBFA0", "malachite": "#3E8E6E", "mal_deep": "#2C6E56",
    "azu_light": "#7FA6C8", "azurite": "#2B5C8A", "azu_deep": "#23496F",
    "ink": "#1E1A16", "ink_green": "#24382E", "ink_blue": "#1C2A3C", "ink_umber": "#4A3324",
    # forest floor
    "forest": "#869E74", "forest_deep": "#6A8762", "leaf_dot": "#33503E", "leaf_dot2": "#4F7556",
    # water
    "sand": "#E2D4AC", "sand_wet": "#C8BE9C", "bank": "#9BA884",
    "river": "#9DB7C6", "river_deep": "#87A6BC", "lake": "#98B4C6", "lake_deep": "#7F9FB8",
    "ripple": "#B8CCD6",
    "sea_shallow": "#9AB6C0", "sea_mid": "#6F95AE", "sea_deep": "#4E7598",
    # roads
    "road": "#CEB78E", "road_edge": "#B49B76",
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


def maxfilter(a, r):
    """Running maximum over a (2r+1)^2 box (separable, numpy only, no wrap-around)."""
    out = np.asarray(a, np.float32)
    for ax in (0, 1):
        pad = [(0, 0), (0, 0)]
        pad[ax] = (r, r)
        src = np.pad(out, pad, mode="edge")
        n = out.shape[ax]
        res = np.take(src, np.arange(0, n), axis=ax)
        for k in range(1, 2 * r + 1):
            np.maximum(res, np.take(src, np.arange(k, k + n), axis=ax), out=res)
        out = res
    return out


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
        self.sd = up(f["sd"])
        self.desert = up(f["desert"])
        self.forest = np.clip(up(f["forest"]), 0, 1)
        self.cityd = up(f["city_d"])
        self.lake_sd = up(np.clip(np.nan_to_num(f["lake_sd"], nan=-500.0, neginf=-500.0, posinf=500.0),
                                  -500.0, 500.0).astype(np.float32))
        rd = np.where(np.isfinite(f["river_d"]), f["river_d"], 1e4).astype(np.float32)
        self.river_d = up(rd)
        self.river_hw = up(f["river_hw"])
        # relief above the plain and the range it belongs to (master grid, then texels)
        hm = f["h"]
        lift = np.maximum(hm - f["base"], 0.0) * f["land0"]
        self.lift_m = lift
        self.mtn_w = up(T.smoothstep(4.0, 30.0, F.fast_blur(f["mtn_h"] + 0.5 * f["foot_h"], 6.0)))
        self.hill_w = up(T.smoothstep(3.0, 16.0, F.fast_blur(f["hill_h"], 6.0)))
        # the local top of each range: colour zones scale with it (a lower range still gets its
        # azurite crest)
        k = 4
        lk = F.box_down(lift, k)
        top = maxfilter(lk, 32)
        top = F.fast_blur(top, 10.0)
        top_m = np.zeros_like(lift)
        tu = F.smooth_up(top, (lk.shape[0] * k, lk.shape[1] * k))
        top_m[:tu.shape[0], :tu.shape[1]] = tu
        top_m[tu.shape[0]:, :] = top_m[tu.shape[0] - 1:tu.shape[0], :]
        top_m[:, tu.shape[1]:] = top_m[:, tu.shape[1] - 1:tu.shape[1]]
        self.lift = up(lift)
        self.top = up(np.maximum(top_m, 1.0))

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
        tide = np.exp(-(n / 0.06) ** 2)
        return body, tide

    def granulation(self, seed):
        """Fine pigment granulation (zero mean)."""
        return 0.6 * self.vn(0.6, seed, 1) + 0.4 * self.vn(2.0, seed + 1, 1)

    def dots(self, cell_m, density, seed, soft=0.25):
        """Blobby ink dots (0..1): thresholded small noise, ``density`` 0..1 of the area."""
        n = self.vn(cell_m, seed, 1)
        thr = 2.6 - 3.0 * np.clip(density, 0.0, 1.0)
        return T.smoothstep(thr, thr + soft, n)

    def flow_strokes(self, angle, length_m, width_m, seed, n_dir=8):
        """Texture strokes aligned with a per-texel ``angle`` field (radians): fixed-orientation
        stroke noises blended by cos^4 weights of the angle difference (orientation period pi)."""
        acc = np.zeros(self.shape, np.float32)
        wsum = np.zeros(self.shape, np.float32)
        for k in range(n_dir):
            th = math.pi * k / n_dir
            wk = np.maximum(np.cos(2.0 * (angle - th)), 0.0) ** 4
            acc += wk * self.strokes(length_m, width_m, math.degrees(th), seed + 13 * k)
            wsum += wk
        return acc / np.maximum(wsum, 1e-4)

    # -- layers ----------------------------------------------------------------------------------
    def plains(self):
        """Silk plains: pale malachite / ochre washes, humid south and river lands greener, the
        dry north-west ochre; broad soft washes with tide-lines, brush grain and granulation."""
        x, y = self.x, self.y
        macro = self.vn(320.0, 1, 3, 0.5)
        moist = 0.5 + 0.22 * macro
        moist += 0.32 * np.exp(-np.maximum(self.river_d - self.river_hw, 0) / 110.0)
        moist += 0.18 * np.exp(-np.maximum(-self.lake_sd, 0) / 110.0)
        moist -= 0.34 * T.smoothstep(950.0, 250.0, x) * T.smoothstep(1050.0, 550.0, y)
        moist += 0.14 * T.smoothstep(700.0, 1300.0, y)
        moist = np.clip(moist, 0, 1)
        self.moist = moist
        col = lerp(C["plain_ochre"], C["plain_silk"], T.smoothstep(0.15, 0.45, moist))
        col = over(col, C["plain_green"], 0.85 * T.smoothstep(0.42, 0.75, moist))
        col = over(col, C["plain_green_deep"], 0.55 * T.smoothstep(0.72, 1.0, moist))
        # broad and medium washes laid in patches, their rims dried a little darker
        b1, t1 = self.wash(140.0, 2)
        b2, t2 = self.wash(45.0, 3)
        b3, _ = self.wash(14.0, 4, 1)
        col = over(col, C["plain_warm"], 0.30 * (1 - b1) * (1 - moist))
        col = over(col, C["plain_green_deep"], 0.26 * b2 * moist)
        col = over(col, C["plain_silk"], 0.18 * (1 - b2) * b3)
        col = over(col, C["wash_tide"], 0.10 * t1 + 0.07 * t2)
        # brush grain (soft strokes in two directions) and granulation
        st = 0.6 * self.strokes(9.0, 1.1, 18.0, 7) + 0.4 * self.strokes(6.0, 0.9, -32.0, 8)
        col *= (1.0 + 0.022 * st + 0.026 * self.granulation(9))[..., None]
        return col

    def fields(self, col):
        """A hint of field patchwork around the cities: parcels in pale greens, wheat and fallow
        ochre with slightly darker balks, kept parcel by parcel inside an irregular, warped extent
        (the patchwork never forms a disc) and only on open, dry, gentle ground."""
        rng = np.random.default_rng(self.seed + 50)
        fieldm = np.zeros(self.shape, np.float32)
        tints = np.stack([C["field_a"], C["field_b"], C["field_c"], C["field_d"]])
        n_low = self.vn(90.0, 51, 2)
        jag = self.vn(6.0, 52, 2)
        for (key, cx, cy, size) in self.w.cities:
            R = 75.0 + 32.0 * size
            x0, x1 = int(max(0, (cx - R - 60) * 2)), int(min(AW, (cx + R + 60) * 2))
            y0, y1 = int(max(0, (cy - R - 60) * 2)), int(min(AH, (cy + R + 60) * 2))
            sl = self.sl(x0, y0, x1, y1)
            if sl is None:
                continue
            X, Y = self.x[sl], self.y[sl]
            ang = rng.uniform(0, np.pi)
            ca, sa = math.cos(ang), math.sin(ang)
            wu = 5.0 * n_low[sl]
            U = (X - cx) * ca + (Y - cy) * sa + wu
            V = -(X - cx) * sa + (Y - cy) * ca + 0.6 * wu
            cw = rng.uniform(20.0, 40.0, 64)
            cols = np.cumsum(cw)
            cols -= cols[32]
            ci = np.clip(np.searchsorted(cols, U), 1, 63)
            roff = rng.uniform(0, 60.0, 64)
            rh = rng.uniform(26.0, 58.0, 64)
            Vr = V + roff[ci]
            ri = np.floor(Vr / rh[ci]).astype(np.int64)
            hsh = (ci * 73856093 + (ri + 1000) * 19349663 + size * 83492791 + len(key) * 2654435761) % 1000003
            pick = hsh % 4
            r2 = (hsh % 7919) / 7919.0
            pc = tints[pick] * (0.97 + 0.06 * (hsh % 101) / 101.0)[..., None]
            du = np.minimum(U - cols[ci - 1], cols[ci] - U)
            dv = np.minimum(Vr - ri * rh[ci], (ri + 1) * rh[ci] - Vr)
            edge = np.minimum(du, dv)
            # parcel-wise irregular extent: each parcel is in or out as a whole (by its own
            # random number against a warped distance), so the edge of the patchwork is ragged
            dcity = np.hypot(X - cx, Y - cy)
            reach = R * (0.65 + 0.45 * r2) + 45.0 * n_low[sl]
            keep = T.smoothstep(reach, reach - 12.0, dcity)
            keep *= T.smoothstep(F.PAD_FLAT[size] + 2.0, F.PAD_FLAT[size] + 22.0, dcity)
            ok = (T.smoothstep(30.0, 20.0, self.h[sl]) * T.smoothstep(1.5, 3.0, self.h[sl])
                  * T.smoothstep(6.0, 1.5, self.lift[sl])
                  * (1 - T.smoothstep(0.1, 0.35, self.forest[sl]))
                  * T.smoothstep(5.0, 12.0, self.river_d[sl] - self.river_hw[sl])
                  * T.smoothstep(-6.0, -16.0, self.lake_sd[sl])
                  * T.smoothstep(25.0, 60.0, self.sd[sl])
                  * (1 - T.smoothstep(0.2, 0.4, self.desert[sl])))
            m = np.clip(keep * ok * np.where(r2 > 0.3, 0.42, 0.0), 0, 1)
            # balks: a slightly deeper, ragged line along every parcel edge
            balk = T.smoothstep(1.6, 0.4, edge + 0.6 * jag[sl])
            pc = lerp(pc, C["field_balk"], 0.45 * balk)
            prev = fieldm[sl]
            sub = col[sl]
            sub += (pc - sub) * (m * (1 - prev))[..., None]
            col[sl] = sub
            fieldm[sl] = np.maximum(prev, m)
        self.fieldm = fieldm
        self.log("[paint] field washes %.1f %% of the map" % (100.0 * float((fieldm > 0.2).mean())))
        return col

    def steppe_desert(self, col):
        """Ochre steppe and desert washes with fine dotted texture and faint wind streaks."""
        des = self.desert
        n = self.vn(55.0, 11, 3)
        st = lerp(C["steppe"], C["plain_ochre"], 0.4 * T.smoothstep(-1.0, 1.0, n))
        col = over(col, st, 0.85 * np.clip(T.smoothstep(0.0, 0.5, des + 0.12 * n), 0, 1))
        band = 0.5 + 0.5 * np.sin((self.x * 0.8 + self.y * 0.6) / 34.0 + 1.6 * self.vn(70.0, 12, 2))
        sand = lerp(C["desert"], C["desert_light"], 0.22 * band + 0.25 * T.smoothstep(-1, 1, self.vn(140.0, 17, 2)))
        core = np.clip(T.smoothstep(0.35, 0.85, des + 0.15 * n), 0, 1)
        col = over(col, sand, core)
        streak = self.strokes(26.0, 1.2, 33.0, 15)
        col *= (1.0 - 0.012 * streak * core)[..., None]
        # 点: fine ochre-ink dots, denser in the sand, sparse in the steppe
        dens = 0.10 * T.smoothstep(0.1, 0.5, des) + 0.17 * core
        d1 = self.dots(0.5, dens, 13)
        d2 = self.dots(1.0, 0.5 * dens, 14)
        col = over(col, C["desert_dot"], 0.5 * d1 + 0.32 * d2)
        self.sand_core = core
        return col

    def uplands(self, col):
        """青绿 hills and ranges (see the module doc).  The colour zones follow the height above
        the plain relative to the range's own top, brushed along the fall lines; the form adds
        晕染 (gullies deeper, crests paler)."""
        hm = self.w.f["h"]
        lift, top = self.lift, self.top
        mt = self.mtn_w
        hl = self.hill_w * (1 - mt)
        # form: ridge (+) / valley (-) at three scales (master grid -> texels)
        rl = self.up(np.clip((hm - F.fast_blur(hm, 26.0)) / 14.0, -1.0, 1.0))
        rm = self.up(np.clip((hm - F.fast_blur(hm, 10.0)) / 5.0, -1.0, 1.0))
        rs = self.up(np.clip((hm - F.fast_blur(hm, 3.5)) / 1.6, -1.0, 1.0))
        form = 0.45 * rl + 0.35 * rm + 0.2 * rs
        del rl, rm, rs
        valley = T.smoothstep(0.03, 0.5, -form)
        ridge = T.smoothstep(0.03, 0.5, form)
        # fall-line direction (radians) and slope
        hs = F.fast_blur(hm, 2.0)
        gy, gx = np.gradient(hs)
        self.slope_s = self.up(np.hypot(gx, gy).astype(np.float32))
        ca = self.up(gx.astype(np.float32))
        sa = self.up(gy.astype(np.float32))
        del hs, gx, gy
        ang = np.arctan2(sa, ca)
        del ca, sa
        # strokes down the fall lines: long soft ones brush the colour boundaries, fine ones are
        # the hemp-fibre texture
        brush = self.flow_strokes(ang, 16.0, 2.2, 31)
        fib = self.flow_strokes(ang, 9.0, 0.55, 47)
        fib2 = self.flow_strokes(ang, 5.0, 0.45, 59)
        n1 = self.vn(30.0, 21, 2)
        n2 = self.vn(8.0, 22, 2)
        hf = lift / np.maximum(top, 40.0)
        hp = hf + 0.10 * form + 0.025 * brush + 0.045 * n1          # brushed pigment height
        relief = T.smoothstep(3.0, 14.0, lift) * (1 - 0.7 * self.sand_core)
        # ---- 1. ochre underpainting: foothills, lower slopes, every hill flank
        och = lerp(C["foot_ochre"], C["ochre"], T.smoothstep(0.08, 0.38, hp))
        och = lerp(och, C["umber"], 0.45 * valley * T.smoothstep(0.1, 0.4, hp))
        a_och = relief * (0.55 * hl + 0.85 * mt * T.smoothstep(0.02, 0.14, hp))
        col = over(col, och, a_och)
        # ---- 2. hills: pale malachite over the ochre on their tops and shoulders
        hill_top = hl * T.smoothstep(0.30, 0.70, hp) * relief
        hg = lerp(C["hill_green"], C["mal_light"], 0.3 * T.smoothstep(0.55, 0.95, hp))
        hg = lerp(hg, C["malachite"], 0.10 + 0.18 * valley)
        col = over(col, hg, 0.70 * hill_top)
        # ---- 3. ranges: malachite middle slopes, azurite upper slopes and crests
        mid = mt * T.smoothstep(0.20, 0.42, hp) * relief
        mal = lerp(C["mal_light"], C["malachite"], T.smoothstep(0.20, 0.45, hp))
        mal = lerp(mal, C["mal_deep"], 0.55 * valley + 0.1 * T.smoothstep(-0.5, 1.0, n2))
        col = over(col, mal, 0.94 * mid)
        up_ = mt * T.smoothstep(0.55, 0.86, hp) * relief
        azu = lerp(C["azurite"], C["azu_deep"], 0.55 * valley)
        azu = lerp(azu, C["azu_light"], 0.14 * T.smoothstep(0.0, 1.5, n2))
        col = over(col, azu, (0.78 + 0.16 * T.smoothstep(-1.0, 1.0, self.vn(18.0, 36, 2))) * up_)
        # ---- 4. 晕染: crests and spur backs paler (lead white thinly over the pigment), gullies
        #      pooled deeper
        hi = ridge * T.smoothstep(0.3, 0.6, hp) * (mt + 0.5 * hl) * (0.55 + 0.45 * T.smoothstep(-0.5, 1.0, n2))
        hlc = lerp(C["mal_light"], C["azu_light"], T.smoothstep(0.55, 0.85, hp))
        col = over(col, hlc, 0.32 * hi)
        deep = lerp(C["mal_deep"], C["ink_green"], 0.35)
        deep = lerp(deep, C["azu_deep"], T.smoothstep(0.55, 0.85, hp))
        col = over(col, deep, 0.30 * valley * T.smoothstep(0.25, 0.5, hp) * mt * relief)
        # ---- 5. 披麻皴: hemp-fibre strokes running downslope, thicker in the gullies and on the
        #      steep flanks; their ink takes the colour of the pigment they lie in
        steep = T.smoothstep(0.25, 1.0, self.slope_s)
        lines = T.smoothstep(1.05, 1.75, fib) * 0.9 + 0.55 * T.smoothstep(1.25, 1.9, fib2)
        ink = lerp(C["ink_umber"], C["ink_green"], T.smoothstep(0.18, 0.4, hp))
        ink = lerp(ink, C["ink_blue"], T.smoothstep(0.55, 0.85, hp))
        dens = (0.25 + 0.75 * valley) * steep * relief * (mt + 0.35 * hl)
        col = over(col, ink, np.clip(0.42 * lines * dens, 0, 0.8))
        # ---- 6. 苔点: moss dots clustered along the crests and spur backs
        crest = T.smoothstep(0.35, 0.8, form) * T.smoothstep(0.3, 0.55, hp) * (mt + 0.4 * hl)
        clus = T.smoothstep(-0.1, 0.9, self.vn(9.0, 35, 1))
        moss = (self.dots(0.9, 0.55, 33) + 0.7 * self.dots(0.55, 0.45, 37)) * crest * clus
        col = over(col, lerp(C["ink_green"], C["mal_deep"], 0.3), np.clip(0.8 * moss, 0, 0.85))
        # granulation of the mineral pigments (stronger where the pigment lies thick)
        col *= (1.0 + 0.045 * self.granulation(34) * relief * (mt + 0.5 * hl))[..., None]
        self.mid, self.upper = mid, up_
        self.form = form
        return col

    def forest_floor(self, col):
        """Deeper malachite under the woods, densely dotted with ink (点叶) in clustered drifts."""
        fz = T.smoothstep(0.12, 0.6, self.forest)
        n = self.vn(16.0, 61, 2)
        fc = lerp(C["forest"], C["forest_deep"], T.smoothstep(-0.8, 1.0, n))
        on_mtn = 1 - 0.75 * self.upper
        col = over(col, fc, 0.85 * fz * on_mtn)
        clus = T.smoothstep(-0.6, 0.8, self.vn(5.0, 64, 2))
        d1 = self.dots(0.8, 0.30 + 0.25 * clus, 62)
        d2 = self.dots(1.5, 0.18 + 0.15 * clus, 63)
        d3 = self.dots(0.55, 0.25, 65)
        col = over(col, C["leaf_dot2"], 0.55 * d3 * fz * on_mtn)
        col = over(col, C["leaf_dot"], (0.6 * d1 + 0.5 * d2) * fz * on_mtn)
        return col

    def water(self, col):
        """Pale azurite rivers and lakes with faint 水纹, sand at the coast, azurite sea floor.
        Returns (colour, water mask)."""
        h = self.h
        rd = self.river_d - self.river_hw                 # metres outside the channel edge
        n = self.vn(10.0, 71, 2)
        n2 = self.vn(2.5, 72)
        # river banks: a thin greener margin, then a pale sandy rim
        rip = np.exp(-np.maximum(rd, 0) / 9.0) * (1 - 0.6 * self.sand_core) * (1 - self.upper)
        col = over(col, C["bank"], 0.30 * rip)
        col = over(col, C["sand_wet"], 0.55 * T.smoothstep(2.2, 0.3, rd + 0.4 * n2))
        rw = T.smoothstep(0.4, -0.4, rd)
        across = np.clip(self.river_d / np.maximum(self.river_hw, 0.5), 0, 1)
        wc = lerp(C["river_deep"], C["river"], T.smoothstep(0.05, 0.95, across))
        # faint ripple lines along the flow
        rp = self.strokes(7.0, 0.35, 0.0, 74) + 0.6 * self.strokes(5.0, 0.3, 90.0, 75)
        wc = lerp(wc, C["ripple"], 0.25 * T.smoothstep(1.2, 1.9, rp))
        col = over(col, wc, rw)
        lsd = self.lake_sd
        lake = T.smoothstep(-0.5, 0.5, lsd)
        lc = lerp(C["lake"], C["lake_deep"], T.smoothstep(4.0, 45.0, lsd + 6.0 * n))
        # 水纹: concentric wave lines following the shore, broken
        wave = 0.5 + 0.5 * np.cos(lsd / 2.6 * math.pi + 1.2 * n)
        wl = T.smoothstep(0.86, 0.98, wave) * T.smoothstep(0.0, 1.0, self.vn(12.0, 76, 2)) * T.smoothstep(2.0, 8.0, lsd)
        lc = lerp(lc, C["ripple"], 0.35 * wl)
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
        sb = lerp(C["sea_shallow"], C["sea_mid"], T.smoothstep(1.0, 14.0, dep + 2.0 * self.vn(60.0, 73, 2)))
        sb = lerp(sb, C["sea_deep"], T.smoothstep(16.0, 38.0, dep))
        col = over(col, sb, sea)
        water = np.maximum(np.maximum(rw, lake), T.smoothstep(0.1, -0.3, h) * (lake < 0.5))
        self.river_w = rw
        self.lake_w = lake
        return col, np.clip(water, 0, 1)

    def roads(self, col):
        """Pale packed-earth tracks with worn, darker edges + the road mask.  Returns (albedo with
        roads, mask)."""
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
            ed = T.smoothstep(half + 1.8, half + 0.2, d + wob) * (1 - cov) * fade * dry
            road[ty0:ty1, tx0:tx1] = np.maximum(road[ty0:ty1, tx0:tx1], cov)
            edge[ty0:ty1, tx0:tx1] = np.maximum(edge[ty0:ty1, tx0:tx1], ed)
        out = col.copy()
        out = lerp(out, C["road_edge"], 0.35 * edge)
        rut = self.strokes(6.0, 0.3, 0.0, 92)
        rc = C["road"] * (1.0 + 0.035 * self.vn(2.5, 91)[..., None] - 0.02 * rut[..., None])
        out = lerp(out, rc, 0.82 * road)
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
        alt = T.smoothstep(126.0, 146.0, self.h)
        steep = T.smoothstep(1.2, 1.9, self.slope_s) * T.smoothstep(70.0, 110.0, self.h)
        b = np.clip(np.maximum(alt, 0.6 * steep), 0, 1) * (1 - self.water) * (1 - 0.5 * g)
        # A never 0: Unreal's PNG import rewrites the RGB of alpha-0 pixels (FillPNGZeroAlpha),
        # which would wipe the R/G/B masks almost everywhere; 1/255 road is invisible.
        a = np.maximum(self.road, 1.0 / 255.0)
        m = np.stack([r, g, b, a], -1)
        return np.round(np.clip(m, 0, 1) * 255.0).astype(np.uint8)

    def albedo8(self, roads=True):
        img = self.albedo if roads else self.base
        return np.round(np.clip(img, 0, 1) * 255.0).astype(np.uint8)
