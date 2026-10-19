"""World Terrain family - the 2D painted map (WorldMap.png): numpy painting on aged silk.

A blue-green (青绿) court map (舆图) in the manner of A Thousand Li of Rivers and Mountains, style
only.  The canvas is the albedo texel grid (2 px per metre, 4800 x 3000; downsampled to the 2400 x
1500 map), so every plan feature sits exactly on its map coordinates.  Layers, bottom to top:

    silk        aged silk ground (:func:`ironart.scenes_gongbi.silk`, shared with the scenes):
                warp / weft fibres, slubs, mottling, darker toward the edges
    land        bare silk with the faintest washes: greener along the rivers and in the humid
                south, ochre in the dry north-west; ochre sand wash at the coast
    desert      ochre wash with fine ink-ochre dots (点) and a few wind strokes
    water       pale azurite-green washes; 晕染 deeper along every shore; 水纹: coast-parallel ripple
                lines close in, then rows of fish-scale waves fading out to sea; lakes with ripple
                rings; rivers as fine ink double lines with a pale azurite wash and flow strokes
    coast       one tapered, pressure-varied ink line (warm black), never pure black
    glyphs      the pictorial peaks, mounds and trees rendered by Blender
                (:mod:`ironart.world_terrain_mapglyphs`): flat mineral washes from their
                attributes - ochre feet, malachite slopes, azurite crowns, paler back rows, ridges
                lighter, folds deeper, fold lines and 披麻皴 strokes, moss dots (苔点), feet
                dissolving in bare-silk mist; trees in malachite / pine green / bamboo green with
                ink-dot foliage (点叶); Freestyle calligraphic ink with a little bleed
    finish      pigment granulation, the silk fibres multiplied through, 2x -> 1x Lanczos

The city sites stay calm: no glyph covers them (layout) and the land under them is bare silk.
"""

import math

import numpy as np

from . import terrain as T
from . import world_terrain_fields as F
from .world_terrain_paint import Painter, hexc, AW, AH

SS = 2       # canvas pixels per metre

#: palette (sRGB) - DESIGN.md mineral palette and the gongbi mixes
GP = {
    "silk": "#E6D6B0", "ink": "#1E1A16", "ink_soft": "#3A3129",
    "ochre_l": "#D3B489", "ochre": "#B4825A", "ochre_d": "#7E5234",
    "mal_l": "#8CBFA0", "mal": "#3E8E6E", "mal_d": "#2A6A52",
    "azu_l": "#7FA6C8", "azu": "#2B5C8A", "azu_d": "#1F4468",
    "ink_green": "#1F3329", "ink_blue": "#1A2738",
    "hill_l": "#B9C08E", "hill": "#8DB08A",
    "land_green": "#C9CDA4", "land_ochre": "#D8BF92", "sand": "#DCC79A",
    "desert": "#D3B07A", "desert_d": "#A97C4A", "desert_dot": "#7E5A36",
    "water_l": "#C3D1C9", "water": "#A6BFC2", "water_d": "#86A6B4", "wave": "#4E6E7E",
    "river": "#A9C3CA", "lake": "#A3BEC6",
    "tree_l": "#8DB58E", "tree": "#4F8C6A", "tree_d": "#2F6A50", "pine": "#355E48", "pine_l": "#5A8466",
    "bamboo": "#7FA76C", "bamboo_d": "#557F4C", "trunk": "#4A3626", "leaf_dot": "#1E3A2C",
}
GC = {k: hexc(v) for k, v in GP.items()}


def mix(a, b, t):
    t = np.asarray(t, np.float32)[..., None]
    return a + (b - a) * t


def over(dst, col, t):
    t = np.asarray(t, np.float32)[..., None]
    dst += (np.asarray(col, np.float32) - dst) * t
    return dst


def aa_line(dist, width, soft=0.7):
    """Anti-aliased line coverage from a distance (px) and a full width (px)."""
    return np.clip(0.5 * width + 0.5 * soft - dist, 0.0, soft) / soft


def screen_grad(a):
    gy, gx = np.gradient(a)
    return np.sqrt(gx * gx + gy * gy)


class MapPainter(Painter):
    """The 2D painter on the albedo texel grid (``crop`` = texel box, like :class:`Painter`)."""

    def __init__(self, world, log=print, seed=None, crop=None):
        Painter.__init__(self, world, log=log, seed=(seed if seed is not None else world.seed) + 500,
                         crop=crop)
        self.map_trees = []

    # -- ground ---------------------------------------------------------------------------------
    def silk(self):
        from . import scenes_gongbi as GB
        h, w = self.shape
        col, tex = GB.silk(h, w, seed=self.seed % 1000, m=2.0)
        # the shared silk darkens toward *its* frame: for a crop keep only the centre tone
        if self.shape != (AH, AW):
            col = np.broadcast_to(GC["silk"], col.shape).astype(np.float32) * (0.97 + 0.03 * col / max(col.mean(), 1e-3))
        self.silk_col, self.silk_tex = col, tex
        return col.copy()

    def land(self, col):
        """Faint washes on the land: humid green near the rivers / south, dry ochre north-west."""
        x, y = self.x, self.y
        land = T.smoothstep(-0.2, 0.3, self.h)
        moist = 0.45 + 0.2 * self.vn(300.0, 1, 3, 0.5)
        moist += 0.35 * np.exp(-np.maximum(self.river_d - self.river_hw, 0) / 120.0)
        moist += 0.2 * np.exp(-np.maximum(-self.lake_sd, 0) / 120.0)
        moist -= 0.35 * T.smoothstep(950.0, 250.0, x) * T.smoothstep(1050.0, 550.0, y)
        moist += 0.12 * T.smoothstep(700.0, 1300.0, y)
        moist = np.clip(moist, 0, 1)
        b1, t1 = self.wash(150.0, 2)
        b2, _ = self.wash(50.0, 3)
        g = T.smoothstep(0.45, 0.95, moist) * (0.25 + 0.2 * b1 + 0.12 * b2)
        o = T.smoothstep(0.38, 0.05, moist) * (0.28 + 0.15 * (1 - b1))
        col = over(col, GC["land_green"], g * land)
        col = over(col, GC["land_ochre"], o * land)
        col = over(col, GC["ochre_d"], 0.035 * t1 * land)
        # the coast: a soft ochre sand wash along the shore
        beach = T.smoothstep(28.0, 3.0, self.sd) * T.smoothstep(-0.3, 0.6, self.h)
        col = over(col, GC["sand"], 0.45 * beach)
        # bare silk under the cities (calm sites for the game's icons and labels)
        calm = T.smoothstep(60.0, 25.0, self.cityd)
        col = over(col, self.silk_col, 0.6 * calm)
        self.land_m = land
        return col

    def desert_layer(self, col):
        """Ochre desert: an even, softly edged wash, fine stippled dots (点) and short wind-ripple
        dashes; the steppe around it a thinner wash with sparse dots."""
        des = self.desert
        n = self.vn(70.0, 11, 3)
        edge = np.clip(T.smoothstep(0.25, 0.6, des + 0.12 * n), 0, 1)
        core = np.clip(T.smoothstep(0.45, 0.9, des + 0.1 * n), 0, 1)
        col = over(col, GC["desert"], 0.26 * edge + 0.14 * core)
        dens = 0.07 * edge + 0.1 * core
        dm = T.smoothstep(0.01, 0.05, dens)
        d1 = self.dots(0.4, dens, 13) * dm
        d2 = self.dots(0.75, 0.45 * dens, 14) * dm
        col = over(col, GC["desert_dot"], 0.5 * d1 + 0.35 * d2)
        # 沙丘: small crescent dunes scattered in staggered rows (a map's desert sign)
        cw, chh = 46.0, 27.0
        wx = self.x + 4.0 * self.vn(40.0, 16, 2)
        wy = self.y + 3.0 * self.vn(40.0, 17, 2)
        rowi = np.floor(wy / chh)
        xx = wx / cw + 0.5 * (rowi % 2)
        coli = np.floor(xx)
        hsh = np.sin(coli * 12.9898 + rowi * 78.233) * 43758.5453
        hsh = hsh - np.floor(hsh)
        jx = (hsh - 0.5) * 0.5 * cw
        dx = (xx - coli - 0.5) * cw - jx
        dy = wy - (rowi + 0.62) * chh
        rad = 7.0 + 5.0 * hsh
        rr = np.hypot(dx, dy * 1.6)
        arc = aa_line(np.abs(rr - rad) * SS, 1.0 * SS) * (dy < 0.0) * (np.abs(dx) < 0.9 * rad)
        arc2 = aa_line(np.abs(rr - 0.6 * rad) * SS, 0.7 * SS) * (dy < 0.0) * (np.abs(dx) < 0.5 * rad)
        keep = (hsh < 0.5) * core
        col = over(col, GC["desert_dot"], 0.6 * np.clip(arc + 0.6 * arc2, 0, 1) * keep)
        return col

    # -- water ----------------------------------------------------------------------------------
    def water(self, col):
        """Sea, lakes and rivers (see the module doc)."""
        h = self.h
        sea = T.smoothstep(0.15, -0.15, h) * (self.lake_sd < -0.5)
        dsea = np.maximum(-self.sd, 0.0)          # metres off the coast
        n = self.vn(60.0, 71, 3)
        # wash: deeper along the shore (晕染), lighter further out
        shore = np.exp(-dsea / 26.0)
        wc = mix(GC["water"], GC["water_l"], T.smoothstep(40.0, 420.0, dsea + 30.0 * n))
        wc = mix(wc, GC["water_d"], 0.55 * shore)
        col = over(col, wc, 0.92 * sea)
        # 水纹 1: coast-parallel ripple lines hugging the shore (broken, tapered)
        px = SS
        wob = 2.2 * self.vn(14.0, 72, 2)
        ring = (dsea + wob) / 5.5
        fr = np.abs(ring - np.round(ring)) * 5.5 * px
        brk = T.smoothstep(-0.3, 0.6, self.vn(9.0, 73, 2))
        near = T.smoothstep(4.0, 7.0, dsea) * T.smoothstep(34.0, 14.0, dsea)
        lines = aa_line(fr, 0.9 * px) * near * brk
        # 水纹 2: rows of fish-scale waves further out, fading to sea
        wx = self.x + 6.0 * self.vn(70.0, 74, 2)
        wy = self.y + 4.0 * self.vn(70.0, 75, 2)
        sw, sh = 22.0, 9.0                       # scale width / row height (m)
        row = np.floor(wy / sh)
        xx = wx / sw + 0.5 * (row % 2)
        cx = (np.floor(xx) + 0.5) * sw
        cy = (row + 1.0) * sh
        dx = (xx - np.floor(xx) - 0.5) * sw
        dy = wy - cy
        r = np.hypot(dx, dy * 1.25)
        arcs = np.zeros_like(r)
        for rr, a in ((0.5 * sw, 1.0), (0.32 * sw, 0.7)):
            arcs = np.maximum(arcs, a * aa_line(np.abs(r - rr) * px, 0.75 * px))
        arcs *= (dy < 0.6)
        del wx, wy, row, xx, cx, cy, dx, dy, r
        far = T.smoothstep(16.0, 34.0, dsea) * (0.85 * np.exp(-np.maximum(dsea - 34.0, 0) / 170.0) + 0.1)
        arcs = arcs * far * T.smoothstep(-0.8, 0.5, self.vn(40.0, 76, 2) + 0.4)
        wl = np.clip(lines * 0.75 + arcs * 0.55, 0, 1) * sea
        col = over(col, GC["wave"], 0.62 * wl)
        # lakes: wash, deeper at the shore, ripple rings, ink outline
        lsd = self.lake_sd
        lake = T.smoothstep(-0.6, 0.6, lsd)
        lc = mix(GC["lake"], GC["water_d"], 0.55 * np.exp(-np.maximum(lsd, 0) / 9.0))
        col = over(col, lc, 0.92 * lake)
        lring = (lsd + 1.2 * self.vn(8.0, 77, 2)) / 3.6
        lfr = np.abs(lring - np.round(lring)) * 3.6 * px
        lw = aa_line(lfr, 0.75 * px) * T.smoothstep(2.0, 4.0, lsd) * T.smoothstep(-0.2, 0.7, self.vn(6.0, 78, 2))
        col = over(col, GC["wave"], 0.5 * lw * lake)
        # rivers: pale azurite wash between fine ink banks, flow strokes in the wide rivers
        rd = self.river_d - self.river_hw
        rw = T.smoothstep(0.35, -0.35, rd) * (sea < 0.5) * (lake < 0.5)
        col = over(col, GC["river"], 0.95 * rw)
        flow = self.strokes(8.0, 0.25, 0.0, 79) + 0.7 * self.strokes(6.0, 0.25, 90.0, 80)
        col = over(col, GC["wave"], 0.22 * T.smoothstep(1.5, 2.2, flow) * rw * T.smoothstep(4.0, 6.0, self.river_hw))
        self.sea_m, self.lake_m, self.river_m = sea, lake, rw
        return col

    def water_ink(self):
        """Ink of the coast, lake shores and river banks (alpha, H x W)."""
        px = SS
        press = 0.75 + 0.5 * T.smoothstep(-1.2, 1.2, self.vn(30.0, 81, 2))
        # coast: the zero line of h, one tapered line ~1.4 px (1x) with pressure
        hg = screen_grad(self.h)
        dist = np.abs(self.h) / np.maximum(hg, 1e-3)
        coast = aa_line(dist, 1.45 * px * press) * (self.lake_sd < -1.0)
        # a faint second line just off the coast
        dsea = np.maximum(-self.sd, 0.0)
        coast2 = aa_line(np.abs(dsea - 3.2) * px, 0.6 * px) * 0.45 * T.smoothstep(-0.4, 0.6, self.vn(11.0, 82, 2)) \
            * (self.h < 0)
        lg = screen_grad(self.lake_sd)
        ld = np.abs(self.lake_sd) / np.maximum(lg, 1e-3)
        lake = aa_line(ld, 1.1 * px * press)
        rg = screen_grad(self.river_d)
        rdd = np.abs(self.river_d - self.river_hw) / np.maximum(rg, 1e-3)
        bank = aa_line(rdd, 0.75 * px * press) * (self.river_hw > 0.5) * (self.lake_sd < -1.0) \
            * (self.river_d < self.river_hw + 6.0) \
            * T.smoothstep(-1.0, 0.5, self.h)
        return np.clip(np.maximum.reduce([coast, coast2, lake, 0.9 * bank]), 0, 1)

    # -- glyphs ---------------------------------------------------------------------------------
    def glyphs(self, col, P):
        """Paint the Blender glyph passes (see the module doc).  Returns (colour, ink alpha)."""
        img = P["Image"]
        a = np.clip(img[..., 3], 0, 1)
        safe = np.maximum(a, 1e-4)[..., None]
        gA = P["gA"][..., :3] / safe
        gB = P["gB"][..., :3] / safe
        gC = P["gC"][..., :3] / safe
        hn, rho, rnd = gA[..., 0], gA[..., 1], gA[..., 2]
        fold, fw, kind = gB[..., 0] * 2 - 1, gB[..., 1], np.round(gB[..., 2] * 2)
        row, hpage, crown = (gC[..., 0] - 0.5) * 4, gC[..., 1], gC[..., 2]
        fs = np.clip(P["Freestyle"][..., 3], 0, 1)
        if "gD" in P and "Depth" in P:
            fs = np.maximum(fs, self.contours(P, a, hn, kind))
        ink_blur = F.fast_blur(fs, 2.2 * SS)
        out = col.copy()
        mt = (kind < 0.5) & (a > 0.01)
        hl = (np.abs(kind - 1) < 0.5) & (a > 0.01)
        tr = (kind > 1.5) & (a > 0.01)
        n1 = self.vn(14.0, 91, 2)
        n2 = self.vn(4.0, 92, 2)
        # fall direction on the page (down the glyph surface) for the brush work
        hs_ = F.fast_blur(hn * (a > 0.5), 1.5)
        gy_, gx_ = np.gradient(hs_)
        ang = np.arctan2(gy_, gx_)
        down = self.flow_strokes(ang, 16.0, 2.6, 93, n_dir=6)
        # rib grooves inside one peak (the rib id changes) -> fold lines and their 晕染 halo
        ribid = np.round(fold * 0.5 * 24.0 + 12.0 - 1.0)
        rid = np.where(a > 0.6, ribid, -99.0)
        groove_l = np.zeros(self.shape, np.float32)
        for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
            nb = np.roll(np.roll(rid, dy, 0), dx, 1)
            g_ = (rid >= 0) & (nb >= 0) & (nb != rid) & (np.abs(nb - rid) < 19)
            groove_l = np.maximum(groove_l, g_.astype(np.float32))
        groove_l *= (kind < 0.5)
        groove = np.clip(ink_blur * 2.5 + F.fast_blur(groove_l, 2.0 * SS) * 3.0, 0, 1)   # near a line
        # ---- mountains: ochre feet -> malachite -> azurite crowns, layered washes whose edges
        #      are brushed down the slope
        e = hn + 0.012 * down + 0.012 * n1 + 0.04 * (rnd - 0.5) - 0.05 * groove
        c = mix(GC["ochre_l"], GC["ochre"], T.smoothstep(0.06, 0.26, e))
        c = mix(c, GC["mal_l"], T.smoothstep(0.27, 0.36, e))
        c = mix(c, GC["mal"], T.smoothstep(0.34, 0.5, e))
        c = mix(c, mix(GC["mal"], GC["azu"], 0.55), T.smoothstep(0.52, 0.66, e))
        c = mix(c, GC["azu"], T.smoothstep(0.62, 0.8, e))
        c = mix(c, GC["azu_d"], 0.5 * T.smoothstep(0.82, 1.0, e))
        deep = mix(GC["ochre_d"], GC["mal_d"], T.smoothstep(0.3, 0.45, e))
        deep = mix(deep, GC["azu_d"], T.smoothstep(0.6, 0.72, e))
        lite = mix(GC["ochre_l"], GC["mal_l"], T.smoothstep(0.3, 0.45, e))
        lite = mix(lite, GC["azu_l"], T.smoothstep(0.6, 0.8, e))
        # 晕染: the pigment pools deeper beside every contour and fold line, the rib backs between
        # them stay lighter
        c = mix(c, deep, 0.38 * groove)
        c = mix(c, lite, 0.16 * (1 - groove) * T.smoothstep(0.2, 0.5, rho) * fw)
        # each rib face is washed separately: a slightly different tone per face
        hsh = np.sin(ribid * 12.9898 + rnd * 78.233) * 43758.5453
        hsh = hsh - np.floor(hsh)
        c = c * (0.94 + 0.12 * hsh)[..., None] * mt[..., None] + c * (1 - mt[..., None])
        # back rows paler and bluer (distance), front rows warmer
        back = T.smoothstep(-0.3, -0.9, row)
        c = mix(c, mix(self.silk_col, GC["azu_l"], 0.35), 0.3 * back)
        # hills / foot mounds: ochre with pale green crowns, a few fold strokes
        foot = row > 1.5
        ch = mix(GC["ochre_l"], GC["hill_l"], T.smoothstep(0.35, 0.7, hn + 0.06 * n1 + 0.03 * down)
                 * np.where(foot, 0.35, 1.0))
        ch = mix(ch, GC["hill"], 0.45 * T.smoothstep(0.65, 1.0, hn) * np.where(foot, 0.0, 1.0))
        ch = mix(ch, GC["ochre"], 0.3 * groove)
        # trees
        tcol = mix(GC["tree_l"], GC["tree"], T.smoothstep(0.2, 0.8, rnd + 0.3 * n2))
        tcol = mix(tcol, GC["tree_d"], 0.35 * T.smoothstep(0.75, 0.3, hn))
        pine = np.abs(rho - 0.5) < 0.15
        bam = rho > 0.65
        tcol = np.where(pine[..., None], mix(GC["pine"], GC["pine_l"], T.smoothstep(0.4, 0.95, hn)), tcol)
        tcol = np.where(bam[..., None], mix(GC["bamboo_d"], GC["bamboo"], T.smoothstep(0.3, 0.9, hn)), tcol)
        tcol = np.where((crown < 0.5)[..., None], GC["trunk"], tcol)
        gc = np.where(mt[..., None], c, np.where(hl[..., None], ch, tcol))
        # feet dissolve in mist (bare silk between the rows); the back rows sink deeper in it
        mist_h = 0.12 + 0.08 * T.smoothstep(-1.0, 1.0, self.vn(30.0, 94, 2)) + 0.08 * back
        fade = np.where(tr, 1.0, T.smoothstep(0.0, mist_h, hn + 0.02 * down))
        fade = np.where(hl, T.smoothstep(0.0, 0.3, hn) * np.where(row > 1.5, 0.7, 1.0), fade)
        alpha = a * fade
        out = over(out, gc, alpha)
        ink = np.zeros(self.shape, np.float32)
        # fold lines: the grooves where two ribs meet (rib id changes inside one peak)
        brk = T.smoothstep(-0.6, 0.4, self.vn(6.0, 87, 2) + 0.3)
        fl = np.clip(F.fast_blur(groove_l, 0.3 * SS) * 1.5, 0, 1) * mt * brk
        fl *= T.smoothstep(0.12, 0.3, hn) * T.smoothstep(0.97, 0.75, hn)
        ink = np.maximum(ink, 0.5 * fl * fade)
        # 披麻皴: a fan of fine, broken hemp-fibre strokes radiating down the faces from each
        #      summit (crisp ~0.55 px lines), gathered where the folds are
        if "gE" in P:
            gE = P["gE"][..., :3] / safe
            sxm, sym = gE[..., 0] * F.MAP_W, gE[..., 1] * F.MAP_H
            ddx, ddy = self.x - sxm, self.y - sym
            rr = np.hypot(ddx, ddy) + 1e-3
            th = np.arctan2(ddx, ddy + 0.35 * rr)
            Hm = np.maximum(hpage * 160.0, 10.0)
            k = 0.62 * Hm / 3.6                              # strokes per radian (~3.6 px apart)
            ph = th * k + 0.12 * self.vn(14.0, 89, 2)
            dpx = np.abs(ph - np.round(ph)) * rr * SS / k
            hatch = aa_line(dpx, 0.7 * SS) * T.smoothstep(-0.5, 0.3, self.vn(3.5, 90, 2))
            hatch *= mt * T.smoothstep(0.26, 0.4, hn) * T.smoothstep(0.9, 0.62, hn) * (0.35 + 0.65 * groove)
            cun_col = mix(GC["ochre_d"], GC["ink_green"], T.smoothstep(0.3, 0.45, e))
            cun_col = mix(cun_col, GC["ink_blue"], T.smoothstep(0.6, 0.75, e))
            out = over(out, cun_col, np.clip(0.5 * hatch * fade * a, 0, 0.6))
            self.debug = dict(getattr(self, "debug", {}), hatch=hatch, sx=(sxm / 2400.0), th=(th / 6.3 + 0.5))
        # 苔点: moss dots on the crowns and along the ridges
        dots = self.dots(0.6, 0.6, 96) + 0.6 * self.dots(1.0, 0.4, 97)
        moss = dots * mt * T.smoothstep(0.6, 0.85, hn) * (0.45 + 0.55 * groove) * T.smoothstep(-0.4, 0.5, n1)
        out = over(out, GC["ink_green"], np.clip(0.85 * moss * a, 0, 0.9))
        # 点叶: ink-dot foliage on the tree crowns
        leaf = (self.dots(0.42, 0.5, 98) + 0.7 * self.dots(0.7, 0.3, 99)) * tr * (crown > 0.5)
        out = over(out, GC["leaf_dot"], np.clip(0.75 * leaf * a, 0, 0.85))
        # Freestyle contours, faded at the misty feet
        fade_ink = np.where(tr, 1.0, T.smoothstep(0.02, 0.12 + 0.06 * back, hn))
        ink = np.maximum(ink, fs * np.where(a > 0.02, fade_ink, 1.0)
                         * np.where(hl, np.where(row > 1.5, 0.22, 0.6), 1.0))
        self.glyph_alpha = alpha
        return out, ink

    def contours(self, P, a, hn, kind):
        """The outline of every peak where it stands in front of another one or of the ground
        (Freestyle only finds the edge-on silhouettes of the steep upper flanks): object-id
        changes towards a farther surface or the background, a ~1.2 px line on the near side,
        pressure-varied and fading out at the misty foot."""
        safe = np.maximum(a, 1e-4)
        oid = np.round(P["gD"][..., 0] / safe * 1000.0) + 1000.0 * np.round(P["gD"][..., 1] / safe * 8.0)
        oid = np.where(a > 0.5, oid, -1.0)
        dep = np.where(a > 0.5, P["Depth"][..., 0], 1e9)
        edge = np.zeros(self.shape, np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            on = np.roll(np.roll(oid, dy, 0), dx, 1)
            dn = np.roll(np.roll(dep, dy, 0), dx, 1)
            e = (oid >= 0) & (on != oid) & (dn > dep + 0.5)
            edge = np.maximum(edge, e.astype(np.float32))
        edge *= (kind < 1.5)                         # trees keep their Freestyle outline
        press = 0.7 + 0.6 * T.smoothstep(-1.2, 1.2, self.vn(12.0, 88, 2))
        line = np.clip(F.fast_blur(edge, 0.55 * SS) * 2.3 * press, 0, 1)
        line *= T.smoothstep(0.03, 0.2, F.fast_blur(hn * (a > 0.5), 1.0))
        self.debug = {"edge": edge, "line": line}
        return line

    # -- finish ---------------------------------------------------------------------------------
    def finish(self, col, ink):
        """Ink over the pigment (warm black, a little bleed), granulation, silk fibres."""
        bleed = F.fast_blur(ink, 0.9 * SS)
        ink_a = np.clip(np.maximum(ink, 0.25 * bleed), 0, 1) * 0.94
        dens = np.clip(1.0 - col / np.maximum(self.silk_col, 1e-3), 0.0, 1.0).mean(-1)
        g = (0.6 * self.vn(0.5, 101, 1) + 0.5 * self.vn(1.8, 102, 1)) * 0.07 * np.sqrt(dens)
        col = col * (1.0 - g[..., None])
        col = over(col, GC["ink"], ink_a)
        texw = 1.0 - 0.5 * ink_a
        col = col * (self.silk_tex ** texw)[..., None]
        return np.clip(col, 0, 1)

    def paint_map(self, passes=None):
        import time
        t0 = time.time()
        col = self.silk()
        col = self.land(col)
        col = self.desert_layer(col)
        col = self.water(col)
        ink = self.water_ink()
        if passes is not None:
            col, gink = self.glyphs(col, passes)
            # the glyphs hide the water ink they stand on
            ink = np.maximum(ink * (1 - self.glyph_alpha), gink)
        col = self.finish(col, ink)
        self.log("[mappaint] painted %dx%d in %.1fs" % (self.shape[1], self.shape[0], time.time() - t0))
        return col


def downsample(col, factor=SS):
    """2x canvas -> map size (Lanczos per channel) with a light unsharp mask."""
    from PIL import Image
    h, w = col.shape[:2]
    out = np.dstack([np.asarray(Image.fromarray(np.ascontiguousarray(col[..., c], np.float32), "F")
                                .resize((w // factor, h // factor), Image.LANCZOS), np.float32)
                     for c in range(3)])
    b = F.fast_blur(out.mean(-1), 0.8)
    lum = out.mean(-1)
    out = out + 0.25 * (lum - b)[..., None]
    return np.clip(out, 0, 1)
