"""World Terrain family - the 2D campaign map as a gongbi blue-green painting on silk (numpy only).

``Content/Data/Art/Map/WorldMap.png`` (2400 x 1500, 1 px = 1 m, map aligned): a Ming/Qing court
map (舆图) in the manner of the Northern Song blue-green landscape (青绿山水).  Plan view for land,
coast, rivers and lakes; mountains, hills and trees pictorial (see
:mod:`ironart.world_terrain_glyphs`, rendered by Blender with Freestyle ink and attribute AOVs).

The canvas is painted at 2x (the albedo texel grid: pixel (j, i) centre = map ((i + .5) / 2,
(j + .5) / 2)) and downsampled at the end.  Layers, bottom to top:

    silk        aged silk #E6D6B0 .. #D8C39A, warp/weft fibres, mottling, darker edges
    land        pale malachite / ochre glazes, ochre steppe and desert with fine dots (点),
                ochre and green under the ranges, green under the woods
    water       sea and lakes: pale azurite glaze graded from the shore (晕染), ink wave lines
                (水纹) following the shore and fading out; rivers as fine ink double lines with a
                pale azurite wash between
    coast       tapered, pressure-varied ink line, pale sand inside
    glyphs      mineral washes from the AOVs (ochre foot -> malachite -> azurite crown, deeper
                along the outlines), fold lines and hemp-fibre strokes, moss dots, bare-silk
                mist at the feet; trees in malachite / pine green / bamboo green with leaf dots
    ink         the Freestyle contours over everything
    finish      silk fibre through the paint, granulation, edge darkening, Lanczos to 1x

Colours are glazes: ``col *= 1 - a * (1 - pigment)`` (transparent pigment over the silk), so
the silk always shows through and nothing is flat or opaque except the ink.
"""

import math

import numpy as np

from . import terrain as T
from . import world_terrain_fields as F
from .world_terrain_paint import Painter, hexc, AW, AH

SS = 2       # canvas pixels per metre
K_PAGE = 1.0 / math.tan(math.radians(38.0))    # glyph height -> page (world_terrain_glyphs.K)

#: palette (sRGB) - DESIGN.md section 8 mineral pigments and the silk ground
GP = {
    "silk_light": "#E6D6B0", "silk_dark": "#D8C39A", "stain": "#B89A6A",
    "ink": "#1E1A16", "ink_blue": "#2C4058",
    "malachite": "#3E8E6E", "mal_light": "#8CBFA0", "mal_deep": "#2A6E55",
    "azurite": "#2B5C8A", "azu_light": "#7FA6C8", "azu_deep": "#21476E",
    "ochre": "#A0643A", "ochre_light": "#C49A6A", "ochre_pale": "#D2B48A", "umber": "#6E4A30",
    "plain_green": "#A9BE92", "plain_ochre": "#CDB283", "sand": "#E4D3A8",
    "desert": "#D4A867", "dot": "#7A5534",
    "pine": "#2F5E4C", "broad": "#4F8A63", "bamboo": "#7EA766", "trunk": "#5B4330",
    "leaf_dot": "#1F3A2E", "tree_ink": "#1C3328",
    "water": "#86AEC6", "water_deep": "#5F8DB0", "wave": "#3E6386", "river": "#86B0CF",
    "sea": "#94B9D2",
    "white": "#F0E8D8",
}
GC = {k: hexc(v) for k, v in GP.items()}


def glaze(col, pigment, a):
    """Transparent pigment over the ground (multiply-style watercolour glaze), in place."""
    a = np.asarray(a, np.float32)[..., None]
    col *= 1.0 - a * (1.0 - np.asarray(pigment, np.float32))
    return col


def body(col, pigment, a):
    """Opaque-ish mineral body colour (malachite / azurite are ground minerals: they cover)."""
    a = np.asarray(a, np.float32)[..., None]
    col += (np.asarray(pigment, np.float32) - col) * a
    return col


def line_cov(dist_px, width_px):
    """Anti-aliased coverage of a line of ``width_px`` whose centre is ``dist_px`` away."""
    return np.clip(0.5 * width_px + 0.5 - np.abs(dist_px), 0.0, 1.0)


def grad_mag(a):
    gy, gx = np.gradient(a)
    return np.sqrt(gx * gx + gy * gy) + 1e-6


class MapPainter(Painter):
    """The 2D painter on the albedo texel grid (``crop`` = texel box, like :class:`Painter`)."""

    def __init__(self, world, log=print, seed=None, crop=None):
        Painter.__init__(self, world, log=log, seed=(seed if seed is not None else world.seed) + 500,
                         crop=crop)
        self.sd_px = self.sd * SS

    # -- silk ----------------------------------------------------------------------------------
    def silk(self):
        """Aged silk: mottled warm ground, warp and weft fibres, faint stains, darker edges."""
        t = 0.4 + 0.13 * self.vn(300.0, 1, 3) + 0.05 * self.vn(45.0, 2, 2)
        col = np.empty(self.shape + (3,), np.float32)
        col[:] = GC["silk_light"]
        col += (GC["silk_dark"] - GC["silk_light"]) * np.clip(t, 0, 1)[..., None]
        # stains / foxing: a few soft blooms of darker ochre
        st = T.smoothstep(1.2, 2.4, self.vn(60.0, 3, 2))
        glaze(col, GC["stain"] * 1.05, 0.07 * st)
        # warp (vertical) and weft (horizontal) threads: per-column / per-row tone, broken up
        rng = np.random.default_rng(self.seed + 11)
        rows = rng.standard_normal(AH).astype(np.float32)
        cols = rng.standard_normal(AW).astype(np.float32)
        tx0, ty0, tx1, ty1 = self.box
        r = rows[ty0:ty1][:, None] * (0.5 + 0.5 * self.vn(6.0, 4, 1))
        c = cols[tx0:tx1][None, :] * (0.5 + 0.5 * self.vn(6.0, 5, 1))
        self.fibre = (0.006 * r + 0.005 * c + 0.006 * self.vn(0.3, 6, 1)).astype(np.float32)
        col *= (1.0 + self.fibre)[..., None]
        # older, darker toward the edges of the scroll
        e = np.minimum(np.minimum(self.x, F.MAP_W - self.x), np.minimum(self.y, F.MAP_H - self.y))
        self.edge = T.smoothstep(0.0, 240.0, e + 30.0 * self.vn(80.0, 7, 2))
        col *= (0.93 + 0.07 * self.edge)[..., None]
        return col

    # -- land -------------------------------------------------------------------------------------
    def land(self, col):
        land = T.smoothstep(-0.3, 0.3, self.sd_px)
        self.land_m = land
        n1 = self.vn(140.0, 21, 3)
        n2 = self.vn(40.0, 22, 2)
        x, y = self.x, self.y
        dry = np.clip(T.smoothstep(950.0, 300.0, x) * T.smoothstep(1050.0, 650.0, y) + 0.15 * n1, 0, 1)
        humid = np.clip(T.smoothstep(700.0, 1300.0, y) + 0.4 * np.exp(-np.maximum(self.river_d - self.river_hw, 0) / 80.0), 0, 1)
        # pale plains glaze: green in the humid lands, ochre in the dry west
        a_g = (0.10 + 0.05 * n1 + 0.03 * n2 + 0.07 * humid) * (1 - dry) * land
        a_o = (0.10 + 0.03 * n2) * dry * land
        glaze(col, GC["plain_green"], np.clip(a_g, 0, 1))
        glaze(col, GC["plain_ochre"], np.clip(a_o, 0, 1))
        # washes dry with a deeper tide-line
        tide = np.exp(-(n1 / 0.06) ** 2) * land
        col *= (1.0 - 0.012 * tide)[..., None]
        # deserts: ochre with fine dots
        des = np.clip(T.smoothstep(0.3, 0.62, self.desert + 0.08 * n2), 0, 1) * land
        glaze(col, GC["desert"], (0.2 + 0.03 * n2) * des)
        d1 = self.dots(0.4, 0.16 * des, 31, soft=0.2)
        d2 = self.dots(0.75, 0.07 * des, 32, soft=0.2)
        glaze(col, GC["dot"], np.clip(0.6 * d1 + 0.5 * d2, 0, 1) * des)
        # dune marks: short crescent strokes across the wind, scattered over the sand
        dph = (self.x * 0.8 + self.y * 0.6) / 16.0 + 0.9 * self.vn(70.0, 33, 1) + 0.15 * self.vn(14.0, 35, 1)
        dk = np.floor(dph + 0.5)
        dd = np.abs(dph - dk) / np.maximum(grad_mag(dph), 0.02)
        dash = T.smoothstep(1.0, 1.4, self.vn(9.0, 34, 1) + 0.5 * np.sin(dk * 4.1))
        dune = line_cov(dd, 0.85 * SS * 0.65) * dash * T.smoothstep(0.55, 0.9, des)
        glaze(col, GC["dot"], 0.4 * dune)
        # ranges and hills: ochre and green glazes on the ground they stand on (plan)
        foot = np.clip(np.maximum(self.foot, 0.8 * self.hill), 0, 1) * land
        glaze(col, GC["ochre_light"], 0.12 * T.smoothstep(0.25, 0.7, foot + 0.1 * n2))
        glaze(col, GC["mal_light"], 0.12 * T.smoothstep(0.3, 0.8, foot + 0.15 * n1))
        # woods: a green glaze under the painted trees (where the painting has trees), deeper at
        # its drying edge
        fz = T.smoothstep(0.15, 0.55, self.wood_density() + 0.06 * n2) * land
        glaze(col, GC["mal_light"], 0.32 * fz)
        edge = np.clip(fz - F.fast_blur(fz, 6.0), 0, 1)
        glaze(col, GC["malachite"], 0.25 * T.smoothstep(0.0, 0.12, edge))
        return col

    def wood_density(self):
        """0..1 density of the painted trees (``self.map_trees``) on this crop."""
        trees = getattr(self, "map_trees", None)
        if not trees:
            return np.clip(self.forest, 0, 1)
        tx0, ty0, tx1, ty1 = self.box
        acc = np.zeros(self.shape, np.float32)
        for t in trees:
            i, j = int(t["x"] * SS) - tx0, int((t["y"] - 0.3 * K_PAGE * t.get("z", 0.0)) * SS) - ty0
            if 0 <= i < self.shape[1] and 0 <= j < self.shape[0]:
                acc[j, i] += 1.0
        dens = F.fast_blur(acc, 6.0 * SS) * (math.pi * (6.0 * SS) ** 2) / 2.2
        return np.clip(dens, 0, 1)

    # -- water ----------------------------------------------------------------------------------
    def _coast_along(self):
        """Arc length (px) of the nearest point on the main coast polyline, near the coast."""
        poly = self.w.m["land"][0]
        ring = F._chaikin_coast(poly, 3)
        segs = [(a, b) for a, b in zip(ring, np.roll(ring, -1, axis=0)) if not F._on_border(a, b)]
        pts = np.array([segs[0][0]] + [b for (_a, b) in segs], np.float64)
        tx0, ty0, tx1, ty1 = self.box
        d, t = F.polyline_field((pts - 0.25) * SS, 260.0 * SS, want_t=True, shape=self.shape,
                                origin=(tx0, ty0))
        return np.where(np.isfinite(d), t, 0.0).astype(np.float32)

    def water(self, col):
        sea = T.smoothstep(0.3, -0.3, self.sd_px)
        lake = T.smoothstep(-0.6, 0.6, self.lake_sd * SS)
        self.sea_m, self.lake_m = sea, lake
        off = np.maximum(-self.sd, 0.0)                            # metres offshore
        n1 = self.vn(90.0, 41, 3)
        n2 = self.vn(12.0, 42, 2)
        # sea: a pale azurite wash, deeper along the shore (晕染) and settling offshore
        body(col, GC["sea"], np.clip(0.62 + 0.06 * n1, 0, 1) * sea)
        glaze(col, GC["water"], np.clip(0.28 * np.exp(-off / 60.0) + 0.1 * T.smoothstep(80.0, 500.0, off + 60.0 * n1), 0, 1) * sea)
        # wave lines (水纹): gently waving parallel lines along the shore, broken into strokes,
        # fading out offshore
        S = 9.0 * SS
        dpx = off * SS
        along = self.y * 0.95 + self.x * 0.3
        wav = 0.24 * np.sin(along / 13.0 + 0.8 * n1) * T.smoothstep(10.0, 120.0, dpx)
        phase = dpx / S + wav + 0.08 * n1
        k = np.floor(phase + 0.5)
        dl = np.abs(phase - k) / np.maximum(grad_mag(phase), 0.02)
        dash = self.vn(24.0, 43, 1) + 0.7 * np.sin(k * 2.7 + along / 31.0)
        gaps = T.smoothstep(-0.65, -0.05, dash)
        fade = T.smoothstep(5.0, 14.0, dpx) * T.smoothstep(130.0 * SS, 20.0 * SS, dpx + 20.0 * SS * n1)
        lw = (0.75 + 0.55 * gaps) * SS * 0.62
        wl = line_cov(dl, lw) * gaps * fade * sea
        glaze(col, GC["wave"], 0.55 * np.clip(wl, 0, 1))
        # lakes: glaze, concentric ripples, ink shore
        lsd = self.lake_sd * SS
        body(col, GC["sea"], 0.7 * lake)
        glaze(col, GC["water"], 0.22 * lake)
        glaze(col, GC["water_deep"], 0.15 * T.smoothstep(10.0, 70.0, lsd) * lake)
        lp = lsd / (7.0 * SS) + 0.2 * n2
        lk = np.floor(lp + 0.5)
        ldl = np.abs(lp - lk) * 7.0 * SS / np.maximum(grad_mag(lp) * 7.0 * SS, 0.35)
        lgaps = T.smoothstep(-0.5, 0.1, self.vn(9.0, 45, 2))
        lwl = line_cov(ldl, 1.2) * lgaps * T.smoothstep(3.0, 9.0, lsd) * T.smoothstep(60.0, 20.0, lsd) * lake
        glaze(col, GC["wave"], 0.5 * lwl)
        g = grad_mag(lsd)
        shore = line_cov(lsd / g, (1.2 + 0.5 * self.vn(10.0, 46, 1)) * SS * 0.75)
        self.ink_extra = 0.85 * shore
        return col

    def rivers(self, col):
        """Fine ink double lines with a pale azurite wash between them."""
        tx0, ty0, tx1, ty1 = self.box
        ink = np.zeros(self.shape, np.float32)
        wash = np.zeros(self.shape, np.float32)
        ripple = np.zeros(self.shape, np.float32)
        for c in self.w.rivers:
            pts = np.asarray(c["pts"], np.float64)
            t_m, w_m = np.asarray(c["t"]), np.asarray(c["w"])
            R = float(w_m.max()) * 0.5 + 6.0
            sy, sx, org = F.window(pts * SS, R * SS, (AH, AW))
            y0, y1 = max(sy.start, ty0), min(sy.stop, ty1)
            x0, x1 = max(sx.start, tx0), min(sx.stop, tx1)
            if y1 <= y0 or x1 <= x0:
                continue
            d, t = F.polyline_field((pts - 0.25) * SS, R * SS, want_t=True, shape=(y1 - y0, x1 - x0),
                                    origin=(x0, y0))
            ok = np.isfinite(d)
            d = np.where(ok, d, 1e4)
            tm = t / SS
            hw = 0.5 * np.interp(tm, t_m, w_m) * SS * 0.9
            src = T.smoothstep(0.0, 60.0, tm)
            sl = (slice(y0 - ty0, y1 - ty0), slice(x0 - tx0, x1 - tx0))
            w_ = np.where(ok, T.smoothstep(hw + 0.5, hw - 0.5, d), 0.0)
            lw = (0.95 + 0.25 * src) * SS * 0.62
            bank = np.where(ok, line_cov(d - hw, lw), 0.0) * (0.35 + 0.65 * src)
            # a few ripple strokes down the middle of the wider reaches
            rip = np.where(ok, line_cov(d, 0.6 * SS * 0.6), 0.0) * T.smoothstep(4.0 * SS, 6.0 * SS, hw)
            rip *= T.smoothstep(0.2, 0.6, np.sin(t / (9.0 * SS)) + 0.4 * np.sin(t / (3.1 * SS) + 1.0))
            wash[sl] = np.maximum(wash[sl], w_)
            ink[sl] = np.maximum(ink[sl], bank)
            ripple[sl] = np.maximum(ripple[sl], rip)
        dry = self.land_m * (1.0 - self.lake_m)
        body(col, GC["river"], 0.74 * wash * dry)
        glaze(col, GC["wave"], 0.45 * ripple * wash * dry)
        self.ink_extra = np.maximum(self.ink_extra, 0.8 * ink * T.smoothstep(-2.0, 2.0, self.sd_px)
                                    * (1.0 - self.lake_m))
        return col

    def coast(self, col):
        """Tapered ink line along the shore, pale sand inside it."""
        g = grad_mag(self.sd_px)
        dpx = self.sd_px / g
        glaze(col, GC["sand"], 0.45 * T.smoothstep(14.0 * SS, 1.0, dpx) * T.smoothstep(-0.5, 0.5, dpx))
        press = 0.5 + 0.5 * self.vn(30.0, 51, 2)
        lw = (1.35 + 1.0 * press) * SS * 0.72
        cl = line_cov(dpx - 0.4 * lw, lw)
        self.ink_extra = np.maximum(self.ink_extra, 0.92 * cl)
        return col

    # -- glyphs ---------------------------------------------------------------------------------
    def glyphs(self, col, P):
        """Paint the glyph layer from the render passes ``P`` (arrays on this crop): Image
        (alpha), gA (hn, rho, rand), gB (cos th, sin th, kind/2), gC (fold), Freestyle."""
        A = np.clip(P["Image"][..., 3], 0.0, 1.0)
        inv = 1.0 / np.maximum(A, 1e-3)
        hn = np.clip(P["gA"][..., 0] * inv, 0, 1)
        rho = np.clip(P["gA"][..., 1] * inv, 0, 1)
        rnd = np.clip(P["gA"][..., 2] * inv, 0, 1)
        ct = P["gB"][..., 0] * inv * 2.0 - 1.0
        st = P["gB"][..., 1] * inv * 2.0 - 1.0
        kind = np.round(P["gB"][..., 2] * inv * 2.0)
        psi = P["gC"][..., 0] * inv
        fold_w = np.clip(P["gC"][..., 1] * inv, 0, 1)
        hpage = np.clip(P["gC"][..., 2] * inv, 0, 1.2)
        ink_a = np.clip(P["Freestyle"][..., 3], 0, 1)
        mtn = (kind < 0.5) * A
        hil = ((kind > 0.5) & (kind < 1.5)) * A
        tre = (kind > 1.5) * A
        n1 = self.vn(20.0, 61, 2)
        n2 = self.vn(5.0, 62, 2)
        near = np.clip(F.fast_blur(ink_a, 5.0) * 2.2, 0, 1)        # inside the outlines
        # ---- mountains: 赭石 foot -> 石绿 -> 石青 crown, per peak
        h2 = hn + 0.08 * (rnd - 0.5) + 0.05 * n1
        green_pk = rnd < 0.3
        c_m = np.empty(self.shape + (3,), np.float32)
        c_m[:] = GC["ochre_pale"]
        c_m += (GC["ochre"] - c_m) * T.smoothstep(0.1, 0.32, h2 + 0.03 * n1)[..., None] * 0.55
        tm = T.smoothstep(0.2, 0.46, h2)
        c_m += (GC["malachite"] - c_m) * tm[..., None]
        tall = T.smoothstep(0.35, 0.75, hpage + 0.15 * (rnd - 0.5))
        ta = T.smoothstep(0.5, 0.86, h2) * np.where(green_pk, 0.45, 1.0) * (0.25 + 0.75 * tall)
        c_m += (GC["azurite"] - c_m) * ta[..., None]
        # deeper along the outlines and on the far (east) faces; a lighter heart (晕染)
        side = np.clip(ct, -1, 1) * T.smoothstep(0.1, 0.5, rho)
        deep = np.clip(0.55 * near + 0.3 * np.maximum(side, 0), 0, 1)
        tgt = np.where((ta > 0.5)[..., None], GC["azu_deep"], GC["mal_deep"])
        c_m += (tgt - c_m) * (0.55 * deep)[..., None]
        c_m += (GC["mal_light"] - c_m) * (0.18 * np.maximum(-side, 0) * (1 - near) * tm)[..., None]
        c_m *= (1.0 + 0.025 * n2 + 0.02 * self.vn(1.2, 67, 1))[..., None]
        # fold lines (constant pixel width from the fold field gradient) and hemp-fibre strokes
        q = psi / np.pi - 0.5
        qk = np.floor(q + 0.5)
        gq = grad_mag(q)
        fl = line_cov(np.abs(q - qk) / np.maximum(gq, 1e-3), (0.8 + 0.7 * fold_w) * SS * 0.75)
        fl *= fold_w * T.smoothstep(-0.2, 0.4, self.vn(6.0, 66, 1) + 0.3 * np.sin(qk * 2.3)) \
            * (gq < 0.25) * T.smoothstep(0.08, 0.3, hn)
        th = np.arctan2(st, ct)
        ph = th * (26.0 / (2 * np.pi)) + 0.25 * n2 + 7.0 * rnd
        kk = np.floor(ph + 0.5)
        gth = grad_mag(ph)
        cun = line_cov(np.abs(ph - kk) / gth, 0.95 * SS * 0.65)
        cun *= T.smoothstep(-0.1, 0.5, self.vn(3.0, 63, 1) + 0.3 * np.sin(kk * 3.1)) * T.smoothstep(0.15, 0.4, rho)
        cun *= (0.35 + 0.65 * np.maximum(side, 0)) * T.smoothstep(0.12, 0.35, hn)
        strokes = np.clip(0.85 * fl + 0.5 * cun, 0, 1)
        c_m += (GC["ink"] * 0.9 + 0.1 * GC["mal_deep"] - c_m) * (strokes * (0.4 + 0.6 * tm))[..., None]
        # moss dots (苔点) on the crowns near the outlines
        moss = self.dots(0.9, 0.35, 64, soft=0.3) * T.smoothstep(0.55, 0.8, hn) * near
        c_m += (GC["ink"] - c_m) * (0.8 * moss)[..., None]
        # ---- hills: ochre with a pale malachite crown, a few hemp strokes
        c_h = np.empty(self.shape + (3,), np.float32)
        c_h[:] = GC["ochre_light"]
        th_h = T.smoothstep(0.35, 0.8, hn + 0.06 * n1)
        c_h += (GC["mal_light"] - c_h) * (0.75 * th_h)[..., None]
        c_h += (GC["malachite"] - c_h) * (0.35 * th_h * (0.4 + 0.6 * near))[..., None]
        c_h += (GC["umber"] - c_h) * (0.25 * near * (1 - th_h))[..., None]
        c_h += (GC["ink"] - c_h) * (np.clip(0.5 * fl + 0.32 * cun, 0, 1) * T.smoothstep(0.2, 0.5, hn))[..., None]
        moss_h = self.dots(0.9, 0.3, 69, soft=0.3) * T.smoothstep(0.7, 0.9, hn) * near
        c_h += (GC["ink"] - c_h) * (0.7 * moss_h)[..., None]
        # ---- trees: crown by species, leaf dots, trunks in umber
        spc = ct * 0.5 + 0.5
        tc = np.where((spc < 0.35)[..., None], GC["broad"], np.where((spc < 0.65)[..., None], GC["pine"], GC["bamboo"]))
        tc = tc * (0.92 + 0.16 * rnd)[..., None]
        tc = tc + (GC["mal_deep"] - tc) * (0.35 * near)[..., None]
        leaf = self.dots(0.55, 0.42, 65, soft=0.3)
        tc = tc + (GC["leaf_dot"] - tc) * (0.55 * leaf)[..., None]
        trunk = (rho < 0.5)
        tc = np.where(trunk[..., None], GC["trunk"], tc)
        # ---- mist: the feet of the glyphs dissolve into bare silk
        mist_m = T.smoothstep(0.06, 0.22, hn + 0.05 * n1 + 0.04 * self.vn(60.0, 68, 1))
        mist_h = T.smoothstep(0.02, 0.3, hn + 0.06 * n1)
        a_m = mtn * mist_m
        a_h = hil * mist_h
        a_t = tre * 0.95
        # glyph colours lie on the silk as mineral body colour, a little transparent
        body(col, c_m, 0.9 * a_m)
        body(col, c_h, 0.8 * a_h)
        body(col, tc, a_t)
        # ink: Freestyle contours (fading into the mist with the foot), then the 2D ink
        mist_ink = np.where(kind > 1.5, 1.0, np.where(kind > 0.5, mist_h, mist_m) ** 0.7)
        self.tree_w = np.clip(F.fast_blur(tre, 1.5) * 1.5, 0, 1) * (1 - np.clip(mtn + hil, 0, 1))
        # the plan-view ink (rivers, shores) lies under the glyphs
        self.ink_extra = self.ink_extra * (1.0 - np.clip(a_m + a_h + a_t, 0, 1))
        self.ink_glyph = ink_a * np.where(A > 0.02, mist_ink, 1.0)
        return col

    def ink(self, col):
        a = np.clip(np.maximum(getattr(self, "ink_glyph", 0.0), self.ink_extra), 0, 1)
        ink_c = np.empty(self.shape + (3,), np.float32)
        ink_c[:] = GC["ink"]
        tw = getattr(self, "tree_w", None)
        if tw is not None:
            ink_c += (GC["tree_ink"] - ink_c) * tw[..., None]
        col += (ink_c - col) * (0.88 * a)[..., None]
        return col

    def finish(self, col):
        """Silk fibre through the paint, granulation, edge darkening."""
        col *= (1.0 + 0.8 * self.fibre + 0.012 * self.vn(0.6, 71, 1))[..., None]
        col *= (0.97 + 0.03 * self.edge)[..., None]
        return np.clip(col, 0, 1)

    # -- run -------------------------------------------------------------------------------------
    def paint_map(self, passes=None):
        import time
        t0 = time.time()
        col = self.silk()
        col = self.land(col)
        col = self.water(col)
        col = self.rivers(col)
        col = self.coast(col)
        if passes is not None:
            col = self.glyphs(col, passes)
        col = self.ink(col)
        col = self.finish(col)
        self.log("[gongbi] painted %dx%d in %.1fs" % (self.shape[1], self.shape[0], time.time() - t0))
        return col


def downsample(col, factor=SS):
    """Lanczos downsample of a float RGB canvas (per channel, Pillow 'F' images)."""
    from PIL import Image
    h, w = col.shape[:2]
    out = []
    for c in range(3):
        im = Image.fromarray(np.ascontiguousarray(col[..., c]), "F")
        out.append(np.asarray(im.resize((w // factor, h // factor), Image.LANCZOS), np.float32))
    return np.clip(np.stack(out, -1), 0, 1)
