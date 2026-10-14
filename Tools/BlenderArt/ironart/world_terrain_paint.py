"""World Terrain family - albedo and masks painter (numpy only).

Paints the 4800 x 3000 ground colour (sRGB, 2 texels per metre, map aligned, NO lighting) and the
linear masks (R water, G forest floor, B rock/snow altitude, A road) of DESIGN.md 12.2 from a
:class:`ironart.world_terrain_fields.World`.

Texel (j, i) covers map [i/2, (i+1)/2) x [j/2, (j+1)/2) metres; master-grid fields are brought to
the texel centres with :func:`ironart.world_terrain_fields.upsample2`.

Layer order (each a colour + coverage, composited with soft edges):

    meadow ground   macro hue drift (lush lowland <-> dry upland), meso meadow mosaic, painterly
                    dabs and tufts, brush-stroke grain
    steppe/desert   dry steppe grass ring, ochre sand with dune banding and scrub
    hills/uplands   drier convex tops, greener hollows; alpine turf high up
    rock/scree/snow slope + altitude exposure, warm/cool rock with strata, scree aprons, snow caps
                    above ~140 m (less on steep faces, more in gullies)
    farmland        per-city parcel patchwork (wheat, ripening grain, millet, fallow, ploughed,
                    vegetables, rice in the humid south) with furrows and grassy banks
    forest floor    dark olive litter under the forests
    banks/water     wet banks + lush riparian strips, clear blue-green rivers and lakes with
                    shallow rims, beaches, wet sand line, sea floor under the sea plane
    city grounds    trodden earth on the pads
    roads           packed-earth tracks with wheel ruts (Albedo.png only; WorldMap.png has none:
                    DESIGN.md 8 - the UI draws the roads)
"""

import math
import zlib

import numpy as np

from . import terrain as T
from . import world_terrain_fields as F

AW, AH = 4800, 3000          # albedo size (2 texels per metre)


def hexc(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


#: albedo palette (sRGB).  Values are *albedo*: what the ground is, not how it is lit.  Muted,
#: olive/sage greens and earth tones so the lit result reads natural (no quilt, no neon).
PAL = {
    # grassland
    "grass_lush": "#5C7A3C", "grass_mid": "#6E8445", "grass_dry": "#8C8B56",
    "grass_cool": "#56733F", "grass_warm": "#7F8749", "meadow_flower": "#97975A",
    "tuft_dark": "#4C6434", "steppe": "#A39867", "steppe_dry": "#B3A273",
    "sand": "#C8AF82", "sand_light": "#D6C196", "sand_dark": "#B09670", "scrub": "#6A6744",
    # uplands / mountains
    "alpine": "#7E8256", "alpine_brown": "#877C5C", "rock_warm": "#8A7F70", "rock_cool": "#7A7B79",
    "rock_dark": "#5B5852", "rock_light": "#A0998C", "scree": "#9D978B", "snow": "#ECEFF2",
    "snow_blue": "#DCE3EA",
    # farmland (close in value to the meadows: a patchwork you feel, not a quilt)
    "wheat_green": "#6E8642", "wheat_ripe": "#A29A5A", "wheat_gold": "#AE9F5C",
    "millet": "#958F52", "fallow": "#878A58", "ploughed": "#7C6C50", "ploughed_dark": "#6C5D45",
    "veg": "#5E7A3E", "rice": "#68884A", "rice_flood": "#6C8A6C", "orchard": "#617A3E",
    "field_bank": "#647A40", "field_path": "#9A8B6A",
    # forest, wet ground, water
    "forest_floor": "#4A5832", "litter": "#5E5536", "moss": "#506437",
    "mud": "#7A6E5A", "gravel": "#9C968A", "riparian": "#557A3D",
    "river": "#3D7480", "river_deep": "#30626E", "river_edge": "#5A8C8A",
    "lake": "#376878", "lake_deep": "#2B5867", "lake_edge": "#588C8A",
    "beach": "#D2C29C", "beach_wet": "#AE9F80", "seabed_sand": "#BDB08C", "seabed": "#888872",
    "seabed_deep": "#56625C",
    # people
    "pad": "#958866", "pad_grass": "#7F8650", "road": "#A79572", "road_rut": "#8B7A5C",
    "road_edge": "#8E8C60",
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
    def __init__(self, world, log=print, seed=None):
        self.w = world
        self.log = log
        self.seed = (seed if seed is not None else world.seed) + 9000
        self.shape = (AH, AW)
        ys, xs = np.mgrid[0:AH, 0:AW].astype(np.float32)
        self.x = (xs + 0.5) * 0.5          # map metres of the texel centres
        self.y = (ys + 0.5) * 0.5
        del xs, ys
        up = F.upsample2
        f = world.f
        self.h = up(f["h"])
        self.slope = up(f["slope"])
        self.curv = up(f["curv"])
        self.sd = up(f["sd"])
        self.desert = up(f["desert"])
        self.forest = np.clip(up(f["forest"]), 0, 1)
        self.hill = up(f["hill_env"])
        self.core = up(f["mtn_core"])
        self.foot = up(f["mtn_foot"])
        self.cityd = up(f["city_d"])
        self.lake_sd = up(f["lake_sd"])
        rd = np.where(np.isfinite(f["river_d"]), f["river_d"], 1e4).astype(np.float32)
        self.river_d = up(rd)
        self.river_hw = up(f["river_hw"])
        self.river_bed = up(f["river_bed"])
        self.layers = {}

    # -- noise -----------------------------------------------------------------------------------
    def vn(self, cell_m, seed, octaves=1, gain=0.5):
        """Value noise on the texel grid with features of ``cell_m`` metres (zero mean, unit std)."""
        return F.vnoise(self.shape, cell_m * 2.0, self.seed + seed, octaves, gain)

    def dabs(self, cell_m, seed, levels=4, soft=0.18):
        """Painterly dabs: noise posterised into a few soft-edged levels (0..1)."""
        n = 0.5 + 0.18 * self.vn(cell_m, seed, 2, 0.45)
        q = n * levels
        fl = np.floor(q)
        fr = q - fl
        return np.clip((fl + T.smoothstep(0.5 - soft, 0.5 + soft, fr)) / levels, 0, 1)

    def strokes(self, length_m, width_m, angle_deg, seed):
        """Anisotropic brush-stroke grain: noise stretched along ``angle`` (zero mean)."""
        from PIL import Image
        a = math.radians(angle_deg)
        # draw stretched noise on a rotated canvas, rotate back (cheap, C code)
        big = int(math.hypot(AW, AH)) + 8
        rng = np.random.default_rng(self.seed + seed)
        gw = max(4, int(big / (length_m * 2)) + 4)
        gh = max(4, int(big / (width_m * 2)) + 4)
        lat = rng.standard_normal((gh, gw)).astype(np.float32)
        im = Image.fromarray(lat, "F").resize((big, big), Image.BICUBIC)
        im = im.rotate(math.degrees(a), resample=Image.BILINEAR)
        arr = np.asarray(im, np.float32)
        oy, ox = (big - AH) // 2, (big - AW) // 2
        out = arr[oy:oy + AH, ox:ox + AW].copy()
        out -= out.mean()
        out /= max(1e-6, out.std())
        return out

    # -- layers ----------------------------------------------------------------------------------
    def ground(self):
        """Meadow ground: lush/dry drift, meadow mosaic, dabs, tufts, strokes."""
        h, x, y = self.h, self.x, self.y
        macro = self.vn(260.0, 1, 3, 0.5)                 # big hue drift
        moist = 0.5 + 0.22 * macro
        # wetter near rivers / lakes / low coast, drier on uplands and towards the west steppe
        moist += 0.32 * np.exp(-np.maximum(self.river_d - self.river_hw, 0) / 70.0)
        moist += 0.18 * np.exp(-np.maximum(-self.lake_sd, 0) / 80.0)
        moist -= 0.20 * T.smoothstep(18.0, 60.0, h) + 0.25 * T.smoothstep(800.0, 150.0, x)
        moist += 0.10 * T.smoothstep(700.0, 1300.0, y)        # humid south
        moist = np.clip(moist, 0, 1)
        self.moist = moist
        col = lerp(C["grass_dry"], C["grass_mid"], T.smoothstep(0.15, 0.55, moist))
        col = lerp(col, C["grass_lush"], T.smoothstep(0.55, 0.95, moist))
        # meadow mosaic: soft-edged patches 20-60 m of cooler / warmer grass
        mos = self.dabs(26.0, 2, levels=5, soft=0.22)
        col = lerp(col, C["grass_cool"], 0.35 * T.smoothstep(0.55, 0.9, mos) * (0.5 + moist))
        col = lerp(col, C["grass_warm"], 0.38 * T.smoothstep(0.45, 0.1, mos))
        # flowering meadow drifts
        fl = self.vn(18.0, 3, 2)
        col = lerp(col, C["meadow_flower"], 0.22 * T.smoothstep(0.9, 1.8, fl) * (1 - self.forest))
        # small painterly dabs (3-6 m) and tufts (1-2 m)
        d1 = self.dabs(4.5, 4, levels=4, soft=0.2) - 0.5
        tuft = self.vn(1.4, 5, 2, 0.6)
        col *= (1.0 + 0.075 * d1 + 0.035 * tuft)[..., None]
        col = lerp(col, C["tuft_dark"], 0.18 * T.smoothstep(1.0, 2.2, self.vn(2.6, 6, 2)))
        # brush-stroke grain (two directions, very low contrast)
        st = 0.6 * self.strokes(9.0, 1.2, 28.0, 7) + 0.4 * self.strokes(6.0, 1.0, -52.0, 8)
        col *= (1.0 + 0.03 * st)[..., None]
        self.grain = st
        return col

    def steppe_desert(self, col):
        des = self.desert
        ring = T.smoothstep(0.0, 0.35, des) * (1 - T.smoothstep(0.5, 0.95, des))
        n = self.vn(40.0, 11, 3)
        col = lerp(col, lerp(C["steppe"], C["steppe_dry"], T.smoothstep(-0.5, 1.0, n)),
                   np.clip(T.smoothstep(0.0, 0.45, des + 0.12 * n), 0, 1) * 0.9)
        # sand core with dune banding (dune crests run along the dune swell phase)
        phase = (self.x * 0.8 + self.y * 0.6) / 23.0
        band = 0.5 + 0.5 * np.sin(phase * 1.0 + 1.6 * self.vn(60.0, 12, 2))
        ripple = np.sin((self.x * 0.8 + self.y * 0.6) / 1.9 + 3.0 * self.vn(8.0, 13, 2))
        sand = lerp(C["sand_dark"], C["sand"], T.smoothstep(0.1, 0.6, band))
        sand = lerp(sand, C["sand_light"], T.smoothstep(0.65, 0.98, band))
        sand *= (1.0 + 0.025 * ripple + 0.03 * self.vn(3.0, 14))[..., None]
        core = np.clip(T.smoothstep(0.42, 0.85, des + 0.15 * n), 0, 1)
        col = lerp(col, sand, core)
        # scrub dots on the steppe and the sand fringe
        scrub = T.smoothstep(1.6, 2.3, self.vn(1.6, 15, 1)) * T.smoothstep(0.1, 0.4, des) * (1 - core * 0.6)
        col = lerp(col, C["scrub"], 0.6 * scrub)
        self.sand_core = core
        del ring
        return col

    def uplands(self, col):
        h, sl, cv = self.h, self.slope, self.curv
        up = T.smoothstep(14.0, 55.0, h) * (1 - self.sand_core)
        convex = T.smoothstep(0.0, -0.05, cv)
        hollow = T.smoothstep(0.0, 0.06, cv)
        col = lerp(col, C["grass_dry"], 0.45 * up * convex)
        col = lerp(col, C["grass_lush"], 0.30 * up * hollow)
        alp = T.smoothstep(70.0, 115.0, h + 10.0 * self.vn(30.0, 21))
        col = lerp(col, lerp(C["alpine"], C["alpine_brown"], T.smoothstep(-0.6, 0.8, self.vn(22.0, 22))),
                   0.85 * alp)
        return col

    def rock_snow(self, col):
        h, sl, cv = self.h, self.slope_s, self.curv
        n1 = self.vn(16.0, 31, 3)
        n2 = self.vn(5.0, 32, 2)
        # exposure: steep faces, high crests, convex ridges; patchy
        rock = (T.smoothstep(0.62, 1.15, sl + 0.12 * n1)
                + 0.55 * T.smoothstep(95.0, 150.0, h + 12.0 * n1) * T.smoothstep(0.25, 0.6, sl)
                + 0.35 * T.smoothstep(-0.02, -0.12, cv) * T.smoothstep(40.0, 90.0, h))
        rock = np.clip(rock, 0, 1) * (1 - 0.7 * self.sand_core)
        rock *= T.smoothstep(22.0, 45.0, h)                      # no rock on the plains
        self.rock = rock
        # rock colour: warm/cool massifs, strata bands following the contours
        rc = lerp(C["rock_cool"], C["rock_warm"], T.smoothstep(-0.8, 0.8, self.vn(120.0, 33, 2)))
        strata = np.sin(h / 2.7 + 1.8 * self.vn(26.0, 34, 2) + 0.6 * n2)
        rc = lerp(rc, C["rock_dark"], 0.38 * T.smoothstep(0.35, 0.95, strata))
        rc = lerp(rc, C["rock_light"], 0.30 * T.smoothstep(-0.4, -0.95, strata))
        rc *= (1.0 + 0.07 * n2 + 0.05 * self.vn(1.5, 35))[..., None]
        # gullies: darker weathered rock / soil
        rc = lerp(rc, C["rock_dark"], 0.35 * T.smoothstep(0.02, 0.1, cv))
        col = lerp(col, rc, rock)
        # scree aprons below the rock: light gravel on moderate slopes near exposed rock
        near_rock = np.clip(F.gaussian(F.box_down(rock, 4), 2.0), 0, 1)
        near_rock = F.smooth_up(near_rock, self.shape)
        scree = (T.smoothstep(0.15, 0.45, near_rock) * T.smoothstep(0.25, 0.55, sl)
                 * (1 - T.smoothstep(0.75, 1.1, sl)) * T.smoothstep(25.0, 60.0, h))
        scree *= T.smoothstep(-0.3, 0.6, n1 + 0.5 * self.vn(3.0, 36))
        col = lerp(col, C["scree"] * (1.0 + 0.06 * n2[..., None]), 0.75 * scree)
        # snow: above ~140 m, broken edge, sheds from steep faces, lingers in gullies
        sline = 140.0 + 7.0 * n1 + 3.0 * n2 - 14.0 * T.smoothstep(0.0, 0.08, cv)
        snow = T.smoothstep(sline - 3.0, sline + 5.0, h)
        snow *= 1.0 - 0.75 * T.smoothstep(1.15, 1.7, sl)
        snow = np.clip(snow, 0, 1)
        sc = lerp(C["snow"], C["snow_blue"], 0.35 * T.smoothstep(0.0, 0.1, cv) + 0.15 * (0.5 + 0.5 * n2))
        col = lerp(col, sc, snow)
        self.snow = snow
        return col

    # -- farmland ----------------------------------------------------------------------------------
    CROPS_NORTH = (("wheat_green", 0.26), ("wheat_ripe", 0.16), ("wheat_gold", 0.07),
                   ("millet", 0.13), ("fallow", 0.14), ("ploughed", 0.10), ("veg", 0.07),
                   ("orchard", 0.07))
    CROPS_SOUTH = (("rice", 0.32), ("rice_flood", 0.12), ("wheat_green", 0.12), ("veg", 0.12),
                   ("fallow", 0.10), ("ploughed", 0.07), ("orchard", 0.09), ("wheat_ripe", 0.06))

    def farmland(self, col):
        """Per-city strip-field patchwork: columns of random width, each cut into its own rows
        (staggered like real strip fields), muted crops with furrows, thin grassy banks, a
        ragged parcel-wise edge.  Only on flat dry open land near the cities."""
        rng = np.random.default_rng(self.seed + 50)
        fieldm = np.zeros(self.shape, np.float32)
        names = sorted(set(k for k, _ in self.CROPS_NORTH + self.CROPS_SOUTH))
        lut = np.stack([C[k] for k in names])
        n_low = self.vn(70.0, 51, 2)
        for (key, cx, cy, size) in self.w.cities:
            R = 105.0 + 50.0 * size
            x0, x1 = int(max(0, (cx - R - 30) * 2)), int(min(AW, (cx + R + 30) * 2))
            y0, y1 = int(max(0, (cy - R - 30) * 2)), int(min(AH, (cy + R + 30) * 2))
            sl = (slice(y0, y1), slice(x0, x1))
            X, Y = self.x[sl], self.y[sl]
            ang = rng.uniform(0, np.pi)
            ca, sa = math.cos(ang), math.sin(ang)
            wu = 3.0 * n_low[sl]
            U = (X - cx) * ca + (Y - cy) * sa + wu
            V = -(X - cx) * sa + (Y - cy) * ca + 0.5 * wu
            ncol = 60
            cols = np.cumsum(rng.uniform(14.0, 30.0, ncol))
            cols -= cols[ncol // 2]
            ci = np.clip(np.searchsorted(cols, U), 1, ncol - 1)
            c_lo, c_hi = cols[ci - 1], cols[ci]
            rows_off = rng.uniform(0, 60.0, ncol)
            rh = rng.uniform(26.0, 62.0, ncol)
            Vr = V + rows_off[ci]
            ri = np.floor(Vr / rh[ci])
            r_lo = ri * rh[ci]
            du = np.minimum(U - c_lo, c_hi - U)
            dv = np.minimum(Vr - r_lo, r_lo + rh[ci] - Vr)
            edge = np.minimum(du, dv)                       # metres to the parcel border
            hsh = (ci * 73856093 + (ri.astype(np.int64) + 1000) * 19349663 + size * 83492791
                   + zlib.crc32(key.encode()) % 100000) % 1000003
            r01 = (hsh % 9973) / 9973.0
            r02 = (hsh % 7919) / 7919.0
            r03 = (hsh % 6007) / 6007.0
            south = cy > 900
            table = self.CROPS_SOUTH if south else self.CROPS_NORTH
            cum = np.cumsum([q for _, q in table])
            cum /= cum[-1]
            crop_i = np.clip(np.searchsorted(cum, r01), 0, len(table) - 1)
            crop_idx = np.array([names.index(k) for k, _ in table])[crop_i]
            ccol = lut[crop_idx] * (0.94 + 0.12 * r03)[..., None]
            # furrows along the parcel's long axis (1.2-1.6 m), low contrast; soft inner mottling
            along_u = (c_hi - c_lo) > rh[ci]
            per = 4.2 + 1.2 * r02
            fur = np.where(along_u, np.sin(U * per + r02 * 6), np.sin(Vr * per + r01 * 6))
            mott = self.vn_small[sl]
            ccol = ccol * (1.0 + 0.035 * fur + 0.03 * mott)[..., None]
            # extent: parcel-wise, denser near the city, ragged edge
            uc = 0.5 * (c_lo + c_hi)
            vc = r_lo + 0.5 * rh[ci] - rows_off[ci]
            dpar = np.hypot(uc, vc)
            dcity = np.hypot(X - cx, Y - cy)
            keep = ((r02 < 1.15 - dpar / R) & (dcity > F.PAD_RADIUS[size] + 10.0)).astype(np.float32)
            ok = (T.smoothstep(0.13, 0.06, self.slope_s[sl])
                  * (1 - T.smoothstep(0.15, 0.4, self.forest[sl]))
                  * T.smoothstep(1.5, 3.0, self.h[sl]) * (1 - T.smoothstep(0.2, 0.45, self.core[sl]))
                  * T.smoothstep(4.0, 9.0, self.river_d[sl] - self.river_hw[sl])
                  * T.smoothstep(-6.0, -14.0, self.lake_sd[sl]))
            if not south:
                ok = ok * (1 - T.smoothstep(0.75, 0.95, self.sand_core[sl]))
            m = keep * ok
            # grassy banks (0.5-0.9 m) and the odd field path
            bank_w = 0.45 + 0.35 * r01
            bank = T.smoothstep(bank_w + 0.45, bank_w - 0.25, edge)
            path = (r02 > 0.86) & (du < dv)
            bank_col = np.where(path[..., None], C["field_path"], C["field_bank"])
            fc = ccol + (bank_col - ccol) * (bank * 0.8)[..., None]
            prev = fieldm[sl]
            sub = col[sl]
            sub += (fc - sub) * (m * (1 - prev))[..., None]
            col[sl] = sub
            fieldm[sl] = np.maximum(prev, m)
        self.fieldm = fieldm
        self.log("[paint] farmland %.1f %% of the map" % (100.0 * float((fieldm > 0.5).mean())))
        return col

    def forest_floor(self, col):
        fz = self.forest
        litter = T.smoothstep(-0.3, 1.0, self.vn(6.0, 61, 2))
        fc = lerp(C["forest_floor"], C["litter"], 0.45 * litter)
        fc = lerp(fc, C["moss"], 0.3 * T.smoothstep(0.5, 1.5, self.vn(3.0, 62)))
        col = lerp(col, fc, 0.9 * T.smoothstep(0.15, 0.7, fz) * (1 - self.rock))
        return col

    def wet_and_water(self, col):
        """River banks, riparian strips, rivers, lakes, beaches, sea floor.  Returns water mask."""
        h = self.h
        rd = self.river_d - self.river_hw                 # metres outside the channel edge
        n = self.vn(10.0, 71, 2)
        n2 = self.vn(2.5, 72)
        # lush riparian strips and wet banks
        rip = np.exp(-np.maximum(rd, 0) / (9.0 + 4.0 * n)) * (1 - self.sand_core * 0.5)
        col = lerp(col, C["riparian"], 0.55 * np.clip(rip, 0, 1) * (1 - self.rock))
        bank = T.smoothstep(2.6, 0.4, rd + 0.5 * n2)
        col = lerp(col, lerp(C["mud"], C["gravel"], T.smoothstep(-0.2, 1.0, n)), 0.85 * bank)
        # river water: deeper centre, lighter rim, soft 0.5 m edge
        rw = T.smoothstep(0.5, -0.5, rd)
        across = np.clip(self.river_d / np.maximum(self.river_hw, 0.5), 0, 1)
        wc = lerp(C["river_deep"], C["river"], T.smoothstep(0.0, 0.6, across))
        wc = lerp(wc, C["river_edge"], T.smoothstep(0.65, 1.0, across))
        wc *= (1.0 + 0.03 * n2)[..., None]
        col = lerp(col, wc, rw)
        # lakes
        lsd = self.lake_sd
        lake = T.smoothstep(-0.5, 0.5, lsd)
        lc = lerp(C["lake_edge"], C["lake"], T.smoothstep(0.0, 9.0, lsd))
        lc = lerp(lc, C["lake_deep"], T.smoothstep(10.0, 40.0, lsd + 6.0 * n))
        shore = T.smoothstep(-3.5, -0.3, lsd) * (1 - lake)
        col = lerp(col, lerp(C["mud"], C["beach_wet"], 0.5), 0.8 * shore)
        col = lerp(col, lc, lake)
        # coast: beaches on low gentle shores, wet sand at the waterline, sea floor below 0
        sd = self.sd
        gentle = 1 - T.smoothstep(0.25, 0.6, self.slope)
        beach = (T.smoothstep(14.0 + 6.0 * n, 2.0, sd) * T.smoothstep(3.2, 1.6, h) * gentle
                 * T.smoothstep(-0.5, 0.2, h))
        col = lerp(col, C["beach"] * (1.0 + 0.04 * n2[..., None]), np.clip(beach, 0, 1))
        wet = T.smoothstep(0.9, 0.05, h) * T.smoothstep(-1.5, -0.1, h)
        col = lerp(col, C["beach_wet"], 0.8 * wet)
        sea = T.smoothstep(0.05, -0.4, h) * (lake < 0.5)
        dep = np.clip(-h, 0, 40.0)
        sb = lerp(C["seabed_sand"], C["seabed"], T.smoothstep(1.0, 12.0, dep + 2.0 * n))
        sb = lerp(sb, C["seabed_deep"], T.smoothstep(14.0, 38.0, dep))
        sb *= (1.0 + 0.05 * n2)[..., None]
        col = lerp(col, sb, sea)
        water = np.maximum(np.maximum(rw, lake), T.smoothstep(0.1, -0.3, h) * (lake < 0.5))
        self.river_w = rw
        self.lake_w = lake
        return col, np.clip(water, 0, 1)

    def city_grounds(self, col):
        pad = np.zeros(self.shape, np.float32)
        for (_k, cx, cy, size) in self.w.cities:
            R = F.PAD_RADIUS[size]
            x0, x1 = int(max(0, (cx - R - 30) * 2)), int(min(AW, (cx + R + 30) * 2))
            y0, y1 = int(max(0, (cy - R - 30) * 2)), int(min(AH, (cy + R + 30) * 2))
            sl = (slice(y0, y1), slice(x0, x1))
            d = np.hypot(self.x[sl] - cx, self.y[sl] - cy)
            pad[sl] = np.maximum(pad[sl], T.smoothstep(0.95 * R, 0.55 * R, d + 7.0 * self.vn_small[sl]))
        pc = lerp(C["pad_grass"], C["pad"], T.smoothstep(-0.2, 1.0, self.vn(4.0, 81, 2)))
        col = lerp(col, pc, 0.55 * pad)
        self.pad = pad
        return col

    def roads(self, col):
        """Packed-earth tracks + road mask.  Returns (albedo with roads, mask)."""
        road = np.zeros(self.shape, np.float32)
        rut = np.zeros(self.shape, np.float32)
        edge = np.zeros(self.shape, np.float32)
        for r in self.w.roads:
            pts = np.asarray(r["pts"], np.float64)
            half = 0.5 * r["width"]
            R = half + 3.0
            sy, sx, org = F.window(pts, R, (AH // 2 + 1, AW // 2 + 1))
            # work on the texel grid of that window
            ty0, ty1, tx0, tx1 = sy.start * 2, min(AH, sy.stop * 2), sx.start * 2, min(AW, sx.stop * 2)
            shp = (ty1 - ty0, tx1 - tx0)
            # polyline_field on a 0.5 m grid: scale coordinates by 2
            d, t = F.polyline_field((pts - 0.25) * 2.0, R * 2.0, want_t=True, shape=shp,
                                    origin=(tx0, ty0))
            d = d * 0.5
            ok = np.isfinite(d)
            d = np.where(ok, d, 1e4)
            # roads fade inside the city pads (the city model sits there) and stop at water
            a = self.w.sc["cities"][r["a"]]
            b = self.w.sc["cities"][r["b"]]
            X, Y = self.x[ty0:ty1, tx0:tx1], self.y[ty0:ty1, tx0:tx1]
            ra = F.PAD_RADIUS[int(a.get("size", 1))] * 0.7
            rb = F.PAD_RADIUS[int(b.get("size", 1))] * 0.7
            fade = (T.smoothstep(ra - 8, ra + 6, np.hypot(X - a["x"], Y - a["y"]))
                    * T.smoothstep(rb - 8, rb + 6, np.hypot(X - b["x"], Y - b["y"])))
            dry = (1 - self.river_w[ty0:ty1, tx0:tx1]) * (1 - self.lake_w[ty0:ty1, tx0:tx1]) \
                * T.smoothstep(-0.2, 0.4, self.h[ty0:ty1, tx0:tx1])
            wob = 0.35 * self.vn_small[ty0:ty1, tx0:tx1]
            cov = T.smoothstep(half + 0.45, half - 0.45, d + wob) * fade * dry
            ruts = (np.exp(-((d - 0.42 * half) / 0.35) ** 2)) * cov
            ed = T.smoothstep(half + 2.6, half + 0.2, d + wob) * (1 - cov) * fade * dry
            road[ty0:ty1, tx0:tx1] = np.maximum(road[ty0:ty1, tx0:tx1], cov)
            rut[ty0:ty1, tx0:tx1] = np.maximum(rut[ty0:ty1, tx0:tx1], ruts)
            edge[ty0:ty1, tx0:tx1] = np.maximum(edge[ty0:ty1, tx0:tx1], ed)
        out = col.copy()
        out = lerp(out, C["road_edge"], 0.45 * edge)
        rc = C["road"] * (1.0 + 0.05 * self.vn(1.2, 91)[..., None])
        out = lerp(out, rc, road)
        out = lerp(out, C["road_rut"], 0.55 * rut)
        return out, road

    # -- run -------------------------------------------------------------------------------------
    def paint(self):
        import time
        t0 = time.time()
        self.vn_small = self.vn(3.0, 99, 2)
        hs = F.gaussian(self.w.f["h"], 1.6)
        gy, gx = np.gradient(hs)
        self.slope_s = F.upsample2(np.sqrt(gx * gx + gy * gy))
        del hs, gx, gy
        col = self.ground()
        col = self.steppe_desert(col)
        col = self.uplands(col)
        col = self.rock_snow(col)
        col = self.farmland(col)
        col = self.forest_floor(col)
        col = self.city_grounds(col)
        col, water = self.wet_and_water(col)
        self.base = np.clip(col, 0, 1)            # no roads (WorldMap.png)
        withroads, road = self.roads(self.base)
        self.albedo = np.clip(withroads, 0, 1)
        self.water = water
        self.road = road
        self.log("[paint] albedo %.1fs" % (time.time() - t0))
        return self

    def masks(self):
        """RGBA uint8: R water, G forest floor, B rock/snow altitude, A road (>= 1: see note)."""
        r = self.water
        g = np.clip(T.smoothstep(0.1, 0.65, self.forest) * (1 - self.water), 0, 1)
        alt = T.smoothstep(75.0, 145.0, self.h) * (1 - 0.6 * g)
        b = np.clip(np.maximum(self.rock, alt), 0, 1) * (1 - self.water)
        # A never 0: Unreal's PNG import rewrites the RGB of alpha-0 pixels (FillPNGZeroAlpha),
        # which would wipe the R/G/B masks almost everywhere; 1/255 road is invisible.
        a = np.maximum(self.road, 1.0 / 255.0)
        m = np.stack([r, g, b, a], -1)
        return np.round(np.clip(m, 0, 1) * 255.0).astype(np.uint8)

    def albedo8(self, roads=True):
        img = self.albedo if roads else self.base
        return np.round(np.clip(img, 0, 1) * 255.0).astype(np.uint8)
