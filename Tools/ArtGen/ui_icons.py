#!/usr/bin/env python3
"""Iron Reign UI icons: 64x64 ink-and-colour icons with transparent backgrounds.

    python3 Tools/ArtGen/ui_icons.py [Name ...]      (default: all icons)

Every icon is built from simple vector shapes on a 64-unit grid, rendered at 8x and box-filtered
down. Each shape gets a watercolour wash (lit from the top-left, darker towards its edges) and an
ink outline of constant weight; the whole silhouette then gets an extra ink rim plus a faint
paper-coloured halo so the icons read on both parchment and dark lacquer panels, at 64 and 32 px.
Writes Content/Data/Art/UI/Icon_<Name>.png.
"""
import math
import os
import sys

import numpy as np

from artlib_ui import (ART, FONT_BRUSH, PAL, Layer, Mask, arc_pts, bez, blur, clamp01, dilate, emboss,
                       fbm, font, hexc, inner_dist, mix, qbez, stroke_poly)

OUT = os.path.join(ART, "UI")
R = 8                 # supersampling
N = 64 * R
INK = PAL["ink"]
OUTLINE = 1.55        # per-shape ink outline (output px)

C = {
    "wood": hexc("8E5C30"), "wood_dark": hexc("5E3B1E"), "wood_light": hexc("B88452"),
    "straw": hexc("D8B25A"), "grain": hexc("E2C46E"),
    "leaf": hexc("5F8D3B"), "leaf_dark": hexc("3E6A33"),
    "red": hexc("AE3424"), "red_dark": hexc("7A1F15"),
    "gold": hexc("D6AC48"), "bronze": hexc("A8783A"),
    "iron": hexc("7D858C"), "steel": hexc("A9B2B8"),
    "stone": hexc("A8A08E"), "stone_dark": hexc("7E7766"),
    "cloth": hexc("EFE6D2"), "paper": hexc("EADDC0"),
    "blue": hexc("3D5E8E"), "teal": hexc("3F6E6A"), "jade": hexc("5C9A7E"),
    "earth": hexc("8C6440"), "skin": hexc("DDAA7C"),
    "purple": hexc("6E4E96"), "flame": hexc("E2632A"), "flame_core": hexc("F8C746"),
    "black": hexc("2C2622"), "glass": hexc("BFD6DA"),
}


def rot(pts, cx, cy, ang):
    a = math.radians(ang)
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for x, y in pts]


def leaf_pts(x, y, length, width, ang, n=20):
    a = math.radians(ang)
    dx, dy = math.cos(a), math.sin(a)
    nx, ny = -dy, dx
    left, right = [], []
    for i in range(n + 1):
        t = i / n
        hw = width / 2 * math.sin(math.pi * t) ** 0.8 * (1 - 0.25 * t)
        px, py = x + dx * length * t, y + dy * length * t
        left.append((px + nx * hw, py + ny * hw))
        right.append((px - nx * hw, py - ny * hw))
    return left + right[::-1]


def ellipse_pts(cx, cy, rx, ry, a0=0, a1=360, n=48):
    return arc_pts(cx, cy, rx, ry, a0, a1, n)


def star_pts(cx, cy, r1, r2, n=5, ang=-90):
    pts = []
    for i in range(n * 2):
        r = r1 if i % 2 == 0 else r2
        a = math.radians(ang + i * 180.0 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


class Icon:
    def __init__(self, seed):
        self.lay = Layer(N, N)
        self.rng = np.random.default_rng(seed)
        y, x = np.mgrid[0:N, 0:N].astype(np.float32)
        self.y = (y + 0.5) / R
        self.x = (x + 0.5) / R
        self.mott = fbm(N, N, 7 * R, self.rng, octaves=3) - 0.5
        self.wvar = fbm(N, N, 5 * R, self.rng, octaves=2) - 0.5

    def mask(self):
        return Mask(N, N, R)

    def _m(self, fn):
        if isinstance(fn, np.ndarray):
            return fn
        if isinstance(fn, list):
            return self.mask().poly(fn).arr()
        m = self.mask()
        fn(m)
        return m.arr()

    def shape(self, fn, color, outline=OUTLINE, lit=1.0, wash=0.22, flat=False, opacity=1.0,
              hi=None, lo=None):
        m = self._m(fn)
        if m.max() <= 0:
            return m
        col = np.asarray(color, np.float32)
        ys, xs = np.nonzero(m > 0.5)
        if len(xs) == 0:
            return m
        x0, x1 = xs.min() / R, xs.max() / R
        y0, y1 = ys.min() / R, ys.max() / R
        diag = ((self.x - x0) / max(1, x1 - x0) + (self.y - y0) / max(1, y1 - y0)) / 2.0
        fill = col * (1 + wash * (0.5 - diag) * 1.6)[..., None]
        fill = fill * (1 + self.mott[..., None] * 0.10)
        if not flat:
            sh = emboss(blur(m, 2.2 * R) * 2.2 * R, strength=1.0) * lit
            hic = hi if hi is not None else np.clip(col * 1.35 + 0.10, 0, 1)
            loc = lo if lo is not None else col * 0.55
            fill = mix(fill, hic, clamp01(sh) * 0.85)
            fill = mix(fill, loc, clamp01(-sh) * 0.8)
        d = inner_dist(m) / R
        fill = fill * (1 - 0.14 * np.exp(-np.maximum(d - outline, 0) / 1.4))[..., None]
        self.lay.paint(np.clip(fill, 0, 1), m, opacity)
        if outline > 0:
            w = outline * (1 + self.wvar * 0.5)
            ol = clamp01((w - d) * R / 2 + 0.5) * m
            self.lay.paint(INK, ol, opacity)
        return m

    def ink(self, fn, color=None, opacity=1.0):
        m = self._m(fn)
        self.lay.paint(INK if color is None else color, m, opacity)
        return m

    def line(self, pts, w, color=None, opacity=1.0, w1=None):
        m = self.mask()
        if w1 is None:
            m.line(pts, w)
        else:
            m.brush(pts, w, w1)
        return self.ink(m.arr(), color, opacity)

    def hilite(self, pts, w, opacity=0.6, color=(1.0, 0.97, 0.88)):
        m = self.mask().brush(pts, w, w * 0.3).arr()
        self.lay.paint(np.asarray(color, np.float32), m, opacity)

    def badge(self, kind, cx=50.5, cy=50.5, r=11.0):
        self.shape(lambda m: m.circle(cx, cy, r), C["gold"], outline=1.6)
        m = self.mask()
        if kind == "plus":
            m.rect(cx - 6.2, cy - 1.9, cx + 6.2, cy + 1.9)
            m.rect(cx - 1.9, cy - 6.2, cx + 1.9, cy + 6.2)
        elif kind == "arrow":
            m.rect(cx - 6.5, cy - 1.8, cx + 0.5, cy + 1.8)
            m.poly([(cx - 0.5, cy - 6.2), (cx + 7.0, cy), (cx - 0.5, cy + 6.2)])
        self.ink(m.arr(), C["red_dark"])

    def finish(self):
        a = self.lay.a
        sil = (a > 0.5).astype(np.float32)
        rim = clamp01(dilate(sil, 0.85 * R) - a)
        halo = clamp01(dilate(sil, 2.3 * R))
        halo = blur(halo, 0.7 * R)
        base = Layer(N, N)
        base.paint(PAL["paper_light"], halo, 0.55)
        base.paint(INK, rim)
        base.paint_layer(self.lay)
        return base.reduced(R)


# ----------------------------------------------------------------------------------------------
# Reusable parts
# ----------------------------------------------------------------------------------------------

def helmet(ic, cx=30, cy=34, s=1.0):
    def S(pts):
        return [(cx + (x - 30) * s, cy + (y - 34) * s) for x, y in pts]
    # plume
    plume = S([(30, 12), (22, 6), (20, 2.5), (27, 4.5), (30, 1.5), (33, 4.5), (40, 2.5), (38, 6)])
    ic.shape(plume, C["red"])
    ic.line(S([(30, 14), (30, 7)]), 2.6 * s, C["gold"])
    # neck guard
    guard = S([(10, 38), (50, 38), (55, 56), (44, 52), (30, 56), (16, 52), (5, 56)])
    ic.shape(guard, C["iron"])
    ic.line(S([(16, 44), (17.5, 51)]), 1.0 * s, opacity=0.8)
    ic.line(S([(44, 44), (42.5, 51)]), 1.0 * s, opacity=0.8)
    ic.line(S([(30, 46), (30, 54)]), 1.0 * s, opacity=0.8)
    # dome
    dome = S(ellipse_pts(30, 38, 19, 25, 180, 360) + [(49, 40), (11, 40)])
    ic.shape(dome, C["steel"], hi=hexc("E8EEF0"))
    # gold band and brow
    ic.shape(S([(11.5, 33), (48.5, 33), (49, 39.5), (11, 39.5)]), C["gold"])
    ic.shape(S([(22, 39), (38, 39), (35, 45), (25, 45)]), C["gold"])
    ic.hilite(S([(19, 26), (22, 19), (28, 15)]), 2.4 * s, 0.7)


def bust(ic, cx, cy, s, robe, hat="guan", beard=True):
    def S(pts):
        return [(cx + x * s, cy + y * s) for x, y in pts]
    body = S([(-22, 30), (-20, 14), (-14, 7), (14, 7), (20, 14), (22, 30)])
    ic.shape(body, robe)
    ic.shape(S([(-7, 7), (7, 7), (0, 20)]), C["cloth"], outline=1.2)
    ic.line(S([(-7, 7), (3, 22)]), 1.2 * s)
    ic.shape(lambda m: m.ellipse(cx, cy - 4 * s, 9 * s, 10.5 * s), C["skin"])
    if beard:
        ic.shape(S([(-5, 1), (5, 1), (2.5, 10), (0, 12), (-2.5, 10)]), C["black"], outline=0.8)
    ic.line(S([(-3.5, -5), (-1.5, -5)]), 1.3 * s)
    ic.line(S([(1.5, -5), (3.5, -5)]), 1.3 * s)
    if hat == "guan":
        ic.shape(S([(-9.5, -9), (9.5, -9), (8, -19), (-8, -19)]), C["black"], hi=hexc("6A625A"))
        ic.shape(S([(-14, -15.5), (14, -15.5), (14, -12.5), (-14, -12.5)]), C["black"], outline=1.0)
    elif hat == "straw":
        ic.shape(S([(-17, -8), (0, -20), (17, -8), (0, -6)]), C["straw"])
    elif hat == "topknot":
        ic.shape(lambda m: m.ellipse(cx, cy - 15.5 * s, 4.5 * s, 4 * s), C["black"])
        ic.shape(S([(-9.5, -7), (-8, -13), (0, -15.5), (8, -13), (9.5, -7), (0, -10)]), C["black"])


def bow_knot(ic, cx, cy, s, color):
    ic.shape(lambda m: m.ellipse(cx - 6 * s, cy - 1 * s, 6 * s, 3.8 * s), color)
    ic.shape(lambda m: m.ellipse(cx + 6 * s, cy - 1 * s, 6 * s, 3.8 * s), color)
    ic.shape(lambda m: m.circle(cx, cy, 2.8 * s), color)


# ----------------------------------------------------------------------------------------------
# Icons
# ----------------------------------------------------------------------------------------------

def icon_Farm(ic):
    soil = [(5, 54)] + bez((5, 54), (10, 42), (54, 40), (59, 54), 24) + [(59, 58), (5, 58)]
    ic.shape(soil, C["earth"])
    for k, yy in enumerate((48, 53)):
        ic.line(bez((12 + k * 3, yy), (24, yy - 3), (40, yy - 3), (52 - k * 3, yy)), 1.1, opacity=0.8)
    for (x, y, sc) in ((16, 49, 0.62), (48, 49, 0.62), (32, 46, 1.0)):
        ic.line(qbez((x, y), (x + 1 * sc, y - 12 * sc), (x - 1 * sc, y - 24 * sc)), 3.0 * sc, C["leaf_dark"])
        ic.shape(leaf_pts(x, y - 12 * sc, 19 * sc, 9 * sc, -150), C["leaf"])
        ic.shape(leaf_pts(x, y - 19 * sc, 18 * sc, 8.5 * sc, -35), C["leaf"])
        ic.shape(leaf_pts(x - 0.5, y - 22 * sc, 12 * sc, 6 * sc, -95), C["leaf"])


def icon_Commerce(ic):
    def frame(m):
        m.rrect(5, 11, 59, 54, 3)
        m.rect(10, 16, 54, 49, 0)
    ic.shape([(9, 15), (55, 15), (55, 50), (9, 50)], hexc("4A2E18"), outline=0.0, flat=True)
    for i in range(5):
        x = 15 + i * 8.5
        ic.line([(x, 16), (x, 49)], 1.3, C["wood_light"], opacity=0.9)
    ic.shape(frame, C["wood"])
    ic.shape([(10, 24), (54, 24), (54, 27.5), (10, 27.5)], C["wood"], outline=1.0)
    ups = [1, 0, 1, 1, 0]
    downs = [2, 4, 1, 3, 0]
    for i in range(5):
        x = 15 + i * 8.5
        yb = 21.0 if ups[i] else 18.5
        ic.shape(lambda m, x=x, yb=yb: m.ellipse(x, yb, 3.9, 2.4), C["red"], outline=0.9)
        for j in range(4):
            yy = (30.5 + j * 4.6) if j < downs[i] else (30.5 + j * 4.6 + 1.2)
            if j >= downs[i]:
                yy = 49 - (4 - j) * 4.6 + 2.3
            ic.shape(lambda m, x=x, yy=yy: m.ellipse(x, yy, 3.9, 2.4), C["red"], outline=0.9)


def icon_Walls(ic):
    wall = [(4, 30), (60, 30), (60, 58), (4, 58)]
    ic.shape(wall, C["stone"])
    for x in (4, 14, 42, 52):
        ic.shape([(x, 23), (x + 8, 23), (x + 8, 31), (x, 31)], C["stone"])
    for k, yy in enumerate((37, 44, 51)):
        ic.line([(5, yy), (59, yy)], 0.9, opacity=0.65)
        off = 0 if k % 2 == 0 else 5
        for x in range(9 + off, 60, 10):
            if 20 < x < 44:
                continue
            ic.line([(x, yy - 7), (x, yy)], 0.9, opacity=0.65)
    # gate tower
    ic.shape([(21, 20), (43, 20), (43, 58), (21, 58)], C["stone_dark"])
    ic.shape([(24, 25), (40, 25), (40, 31), (24, 31)], C["red"], outline=1.0)
    gate = [(26, 58)] + arc_pts(32, 47, 6, 7, 180, 360, 16) + [(38, 58)]
    ic.shape(gate, C["black"], outline=1.0)
    roof = [(15, 21), (19, 16), (24, 11), (40, 11), (45, 16), (49, 21), (44, 19.5), (32, 19), (20, 19.5)]
    ic.shape(roof, C["blue"])
    ic.shape([(22, 11), (42, 11), (42, 8), (22, 8)], C["black"], outline=1.0)


def icon_Patrol(ic):
    ic.line([(13, 61), (40, 5)], 3.4, C["wood_dark"])
    ic.shape([(38.5, 9), (44, 1.5), (42.5, 10.5)], C["steel"], outline=1.0)
    ic.line([(37, 12), (37, 18)], 1.2)
    body = ellipse_pts(37, 33, 13.5, 14.5)
    ic.shape(lambda m: m.ellipse(37, 33, 18, 17), C["flame_core"], outline=0, flat=True, opacity=0.35)
    ic.shape(body, hexc("D0502E"), hi=hexc("FFD08A"))
    for k in (-8, 0, 8):
        ic.line(arc_pts(37 + k * 0.0, 33, abs(k) + 0.1, 14.3, -90, 90, 20) if k > 0 else
                (arc_pts(37, 33, abs(k) + 0.1, 14.3, 90, 270, 20) if k < 0 else [(37, 19), (37, 47)]), 0.9, opacity=0.7)
    ic.shape([(30, 17), (44, 17), (43, 20.5), (31, 20.5)], C["black"], outline=0.8)
    ic.shape([(30, 45.5), (44, 45.5), (43, 49), (31, 49)], C["black"], outline=0.8)
    ic.line([(37, 49), (37, 54)], 1.3, C["red"])
    ic.shape([(34.5, 53), (39.5, 53), (40.5, 60), (33.5, 60)], C["red"], outline=0.9)


def icon_Draft(ic):
    helmet(ic, 28, 32, 0.9)
    ic.badge("plus")


def icon_Troops(ic):
    helmet(ic, 32, 33, 1.0)


def icon_Train(ic):
    ic.line([(18, 40), (10, 62)], 3.2, C["wood_dark"])
    ic.line([(42, 40), (50, 62)], 3.2, C["wood_dark"])
    for r, col in ((23, C["cloth"]), (17, C["red"]), (11, C["cloth"]), (5.5, C["red"])):
        ic.shape(lambda m, r=r: m.circle(30, 31, r), col, outline=1.3 if r < 23 else OUTLINE)
    # arrow stuck in the target
    ic.line([(31, 30), (56, 7)], 2.4, C["wood"])
    ic.shape([(52, 6), (60, 1.5), (58, 9), (55, 13), (51, 9)], C["red"], outline=1.0)
    ic.line([(53, 8), (58, 4)], 0.8, opacity=0.8)


def icon_Search(ic):
    ic.line([(37, 37), (56, 56)], 8.5, C["black"])
    ic.line([(39, 39), (55, 55)], 5.2, C["red"])
    ic.shape([(35.5, 41.5), (41.5, 35.5), (45, 39), (39, 45)], C["gold"], outline=1.0)

    def ring(m):
        m.circle(26, 26, 18.5)
    ic.shape(ring, C["bronze"])
    ic.shape(lambda m: m.circle(26, 26, 13.2), C["glass"], hi=(1, 1, 1))
    ic.hilite(arc_pts(26, 26, 8.5, 8.5, 190, 260, 12), 2.6, 0.9)


def icon_Recruit(ic):
    bust(ic, 28, 30, 1.0, C["teal"])
    ic.badge("plus")


def icon_Move(ic):
    bust(ic, 28, 30, 1.0, C["blue"], hat="topknot")
    ic.badge("arrow")


def icon_Officers(ic):
    bust(ic, 41, 27, 0.78, C["blue"], hat="topknot")
    bust(ic, 24, 33, 0.92, C["red"], hat="guan")


def icon_Population(ic):
    for (x, y, s, robe) in ((18, 33, 0.7, C["earth"]), (46, 33, 0.7, C["teal"]), (32, 38, 0.88, C["blue"])):
        bust(ic, x, y, s, robe, hat="straw", beard=False)


def icon_Transport(ic):
    ic.line([(40, 41), (61, 33)], 2.6, C["wood_dark"])
    ic.line([(40, 37), (61, 29)], 2.6, C["wood_dark"])
    for (x, y, rx, ry) in ((15, 26, 9, 8), (28, 23, 9.5, 9.5), (39, 27, 7.5, 7)):
        ic.shape(lambda m, x=x, y=y, rx=rx, ry=ry: m.ellipse(x, y, rx, ry), C["straw"])
        ic.line([(x - 2, y - ry + 1), (x + 1, y - ry - 2)], 1.2, C["wood_dark"])
    ic.shape([(5, 31), (46, 31), (44, 44), (7, 44)], C["wood"])
    ic.line([(6, 37.5), (45, 37.5)], 0.9, opacity=0.7)

    def wheel(m):
        m.circle(22, 46, 13)
        m.circle(22, 46, 9.5, 0)
    ic.shape(wheel, C["wood_dark"], hi=C["wood_light"])
    for a in range(0, 180, 45):
        ra = math.radians(a)
        ic.line([(22 - 9.5 * math.cos(ra), 46 - 9.5 * math.sin(ra)), (22 + 9.5 * math.cos(ra), 46 + 9.5 * math.sin(ra))], 1.4, C["wood_dark"])
    ic.shape(lambda m: m.circle(22, 46, 3.2), C["gold"], outline=1.0)


def icon_SectTraining(ic):
    # sword behind
    ic.line([(8, 58), (54, 8)], 3.6, C["steel"])
    ic.line([(8, 58), (54, 8)], 0.9, opacity=0.5)
    ic.shape(rot([(4, 58), (20, 58), (20, 61), (4, 61)], 12, 59.5, -47), C["gold"], outline=1.0)
    # bamboo slips
    for i in range(7):
        x = 13 + i * 6.0
        dy = abs(i - 3) * 1.2
        ic.shape([(x, 14 + dy), (x + 5.6, 14 + dy), (x + 5.6, 52 - dy), (x, 52 - dy)], C["straw"] * (0.92 + 0.08 * (i % 2)), outline=1.0, wash=0.1)
        ic.line([(x + 2.8, 18 + dy), (x + 2.8, 30)], 0.8, opacity=0.55)
        ic.line([(x + 2.8, 34), (x + 2.8, 47 - dy)], 0.8, opacity=0.55)
    ic.line([(12, 21), (56, 21)], 1.2, C["red_dark"])
    ic.line([(12, 45), (56, 45)], 1.2, C["red_dark"])


def icon_Alliance(ic):
    ic.line([(12, 60), (46, 5)], 3.0, C["wood_dark"])
    ic.line([(52, 60), (18, 5)], 3.0, C["wood_dark"])
    fl = [(45, 7), (60, 11), (56, 17), (61, 23), (41, 18)]
    ic.shape(fl, C["blue"])
    fr = [(19, 7), (4, 11), (8, 17), (3, 23), (23, 18)]
    ic.shape(fr, C["red"])
    ic.shape(lambda m: m.circle(32, 37.5, 4.2), C["gold"], outline=1.0)
    ic.line([(27, 43), (25, 50)], 1.4, C["red"])
    ic.line([(37, 43), (39, 50)], 1.4, C["red"])


def icon_Truce(ic):
    ic.line([(17, 61), (17, 7)], 3.2, C["wood_dark"])
    ic.shape(lambda m: m.circle(17, 5.5, 3.2), C["gold"], outline=1.0)
    top = [(18, 10)] + bez((18, 10), (28, 6), (38, 14), (56, 9), 20)
    bot = bez((54, 36), (40, 41), (30, 33), (18, 37), 20)
    ic.shape(top + bot, C["cloth"], hi=(1, 1, 1))
    ic.line(bez((24, 16), (32, 13), (40, 20), (48, 16), 16), 0.9, opacity=0.35)
    ic.line(bez((24, 28), (32, 26), (40, 31), (48, 28), 16), 0.9, opacity=0.35)


def icon_Gift(ic):
    ic.shape([(10, 27), (54, 27), (54, 57), (10, 57)], C["red"])
    ic.shape([(7, 19), (57, 19), (57, 29), (7, 29)], C["red_dark"], hi=C["red"])
    ic.shape([(28, 19), (36, 19), (36, 57), (28, 57)], C["gold"], outline=1.0)
    ic.shape([(10, 39), (54, 39), (54, 44), (10, 44)], C["gold"], outline=1.0)
    bow_knot(ic, 32, 15, 1.25, C["gold"])
    ic.line([(30, 18), (24, 26)], 1.8, C["gold"])
    ic.line([(34, 18), (40, 26)], 1.8, C["gold"])


def icon_March(ic):
    head = [(10, 61), (13, 44), (18, 30), (24, 17), (29, 9), (31, 3), (34, 7.5), (37, 4), (38.5, 10),
            (45, 15), (53, 25), (59.5, 33), (58.5, 39), (53, 41.5), (47, 38.5), (41, 37), (37, 41),
            (35, 50), (36, 61)]
    ic.shape(head, hexc("8C4A26"), hi=hexc("C98656"))
    mane = [(29, 9), (24, 17), (18, 30), (13, 44), (10, 61), (5, 58), (8, 50), (4, 47), (9, 40), (6, 34),
            (12, 28), (10, 22), (17, 17), (17, 11), (24, 8)]
    ic.shape(mane, C["black"], hi=hexc("5A4E46"))
    ic.ink(lambda m: m.ellipse(41.5, 19.5, 2.0, 1.6))
    ic.ink(lambda m: m.ellipse(55.5, 34, 1.4, 1.1))
    # bridle
    ic.line([(37, 13), (44, 28), (52, 37)], 1.6, C["red"])
    ic.line([(44, 28), (37, 33)], 1.6, C["red"])
    ic.shape(lambda m: m.circle(44, 28, 2.0), C["gold"], outline=0.8)
    ic.shape([(36, 32), (39, 33), (37, 44), (34, 43)], C["red"], outline=0.8)


def icon_Market(ic):
    ic.line([(10, 22), (10, 59)], 3.0, C["wood_dark"])
    ic.line([(54, 22), (54, 59)], 3.0, C["wood_dark"])
    ic.shape([(5, 41), (59, 41), (59, 49), (5, 49)], C["wood"])
    # goods
    ic.shape(lambda m: m.ellipse(18, 35, 6.5, 7), C["blue"])
    ic.shape([(15, 27), (21, 27), (21, 30), (15, 30)], C["blue"], outline=1.0)
    ic.shape(lambda m: m.ellipse(32, 36, 7, 6), C["straw"])
    ic.shape(lambda m: m.ellipse(45, 36.5, 6, 5.5), hexc("C6713A"))
    ic.shape(lambda m: m.ellipse(48, 33, 4, 3.5), hexc("C6713A"))
    # awning with scallops
    aw = [(3, 20), (9, 9), (55, 9), (61, 20)]
    sc = []
    for i in range(6):
        x0 = 3 + i * 58 / 6.0
        sc += arc_pts(x0 + 58 / 12.0, 20, 58 / 12.0, 4.5, 180, 0, 10)[::-1][::-1]
    awning = aw[:1] + aw[1:3] + [aw[3]] + [p for p in reversed(sum([arc_pts(3 + i * 58 / 6.0 + 58 / 12.0, 20, 58 / 12.0, 4.5, 0, 180, 10) for i in range(6)], []))]
    ic.shape(awning, C["red"])
    for i in range(1, 6, 2):
        x0 = 3 + i * 58 / 6.0
        stripe = [(x0 + 1.0 + (i - 3) * 0.0, 20)] + [(9 + (x0 - 3) * 46 / 58.0 + 0.0, 9), (9 + (x0 + 58 / 6.0 - 3) * 46 / 58.0, 9), (x0 + 58 / 6.0, 20)]
        stripe = stripe + [p for p in reversed(arc_pts(x0 + 58 / 12.0, 20, 58 / 12.0, 4.5, 0, 180, 10))]
        ic.shape(stripe, C["cloth"], outline=0.9)


def icon_Tavern(ic):
    ic.shape(lambda m: m.ellipse(27, 40, 19, 18), hexc("8A5634"), hi=hexc("C08A5E"))
    ic.shape([(19, 16), (35, 16), (37, 24), (17, 24)], hexc("8A5634"))
    cover = [(13, 18)] + bez((13, 18), (16, 6), (38, 6), (41, 18), 16) + [(36, 22), (27, 20), (18, 22)]
    ic.shape(cover, C["red"])
    ic.line([(15, 18.5), (39, 18.5)], 1.6, C["gold"])
    label = [(27, 29), (38, 40), (27, 51), (16, 40)]
    ic.shape(label, C["red"], outline=1.0)
    f = font(FONT_BRUSH, 15 * R)
    ic.ink(lambda m: m.text((27, 40.5), "酒", f), C["black"])
    cup = [(43, 47), (61, 47)] + arc_pts(52, 47, 9, 9.5, 0, 180, 16)
    ic.shape(cup, C["cloth"], hi=(1, 1, 1))
    ic.line([(44.5, 50), (59.5, 50)], 1.0, C["blue"], opacity=0.9)


def icon_Factions(ic):
    ic.line([(13, 62), (13, 5)], 3.4, C["wood_dark"])
    ic.shape(lambda m: m.circle(13, 4.5, 3.4), C["gold"], outline=1.0)
    teeth = [(15, 9), (54, 9)]
    for i in range(6):
        y = 9 + i * 6.5
        teeth += [(59, y + 3.25), (54, y + 6.5)]
    bottom = []
    for i in range(6):
        x = 54 - i * 6.5
        bottom += [(x - 3.25, 53), (x - 6.5, 48)]
    flagp = teeth + [(54, 48)] + bottom + [(15, 48)]
    ic.shape(flagp, C["gold"], outline=1.2)
    ic.shape([(15, 12), (51, 12), (51, 45), (15, 45)], C["red"], outline=1.0)
    ic.shape(lambda m: m.circle(33, 28.5, 10), C["gold"], outline=1.2)
    f = font(FONT_BRUSH, 15 * R)
    ic.ink(lambda m: m.text((33, 29.5), "王", f), C["red_dark"])


def icon_Save(ic):
    ic.shape([(9, 7), (46, 7), (46, 57), (9, 57)], C["blue"], hi=hexc("6E8CB8"))
    ic.shape([(39, 7), (46, 7), (46, 57), (39, 57)], hexc("2E4670"), outline=1.0)
    for y in (14, 25, 39, 50):
        ic.line([(39, y), (46, y)], 1.0, C["cloth"])
    ic.shape([(15, 12), (26, 12), (26, 38), (15, 38)], C["cloth"], outline=1.0)
    ic.line([(20.5, 16), (20.5, 33)], 1.4, opacity=0.8)
    # brush
    ic.line([(60, 5), (32, 44)], 3.4, C["wood_light"])
    ic.line([(60, 5), (57.5, 8.5)], 3.8, C["red"])
    tip = [(34.5, 41.5), (30, 47), (24, 58), (27, 50), (29.5, 40)]
    ic.shape(tip, C["black"], outline=0.8)


def icon_Load(ic):
    paper = [(13, 14), (51, 14), (51, 50), (13, 50)]
    ic.shape(paper, C["cloth"], hi=(1, 1, 1))
    for i, x in enumerate((42, 35, 28, 21)):
        ic.line([(x, 19), (x, 45 - (i % 2) * 8)], 1.6, opacity=0.65)
    ic.shape(lambda m: m.ellipse(13, 32, 4.6, 24), C["wood"], hi=C["wood_light"])
    ic.shape(lambda m: m.ellipse(51, 32, 4.6, 24), C["wood"], hi=C["wood_light"])
    for x in (13, 51):
        ic.shape(lambda m, x=x: m.ellipse(x, 6.5, 2.8, 2.6), C["jade"], outline=1.0)
        ic.shape(lambda m, x=x: m.ellipse(x, 57.5, 2.8, 2.6), C["jade"], outline=1.0)
    ic.shape([(31, 27), (36, 27), (36, 35), (31, 35)], C["red"], outline=0.9)


def icon_EndTurn(ic):
    ic.line([(8, 62), (8, 12)], 3.6, C["wood_dark"])
    ic.line([(56, 62), (56, 12)], 3.6, C["wood_dark"])
    beam = [(2, 12), (7, 8), (57, 8), (62, 12), (57, 14.5), (7, 14.5)]
    ic.shape(beam, C["red"])
    ic.line([(25, 15), (25, 22)], 1.1)
    ic.line([(39, 15), (39, 22)], 1.1)
    ic.shape(lambda m: m.circle(32, 37, 17), C["bronze"], hi=hexc("F0CF7A"))
    ic.line(arc_pts(32, 37, 12.5, 12.5, 0, 360, 40), 0.9, opacity=0.6)
    ic.shape(lambda m: m.circle(32, 37, 5), C["gold"], outline=1.0)
    ic.line([(58, 61), (44, 46)], 2.4, C["wood"])
    ic.shape(lambda m: m.ellipse(42.5, 44.5, 4.6, 4.0), C["red"], outline=1.1)


def icon_Gold(ic):
    def T(pts, k=0.86, ox=-1.5, oy=-4.0):
        return [(32 + (x - 32) * k + ox, 32 + (y - 32) * k + oy) for x, y in pts]
    ic.shape(lambda m: m.ellipse(32 - 1.5, 33 * 0.86 + 4.5 - 4.0, 13.5 * 0.86, 12 * 0.86), C["gold"], hi=hexc("FFF4C0"))
    body = (bez((3, 24), (5, 44), (18, 56), (32, 56), 20) + bez((32, 56), (46, 56), (59, 44), (61, 24), 20)[1:]
            + bez((61, 24), (55, 36), (44, 39), (32, 39), 16)[1:] + bez((32, 39), (20, 39), (9, 36), (3, 24), 16)[1:])
    ic.shape(T(body), C["gold"], hi=hexc("FFF0B0"))
    ic.line(T(bez((9, 33), (16, 41), (48, 41), (55, 33), 20)), 0.9, opacity=0.45)
    ic.hilite(T([(25, 29), (31, 25.5)]), 2.4, 0.95)
    ic.hilite(T([(8, 33), (14, 44)]), 1.8, 0.75)

    def coin(m, x=48.5, y=49.5):
        m.circle(x, y, 11.5)
        m.rect(x - 3.0, y - 3.0, x + 3.0, y + 3.0, 0)
    ic.shape(coin, hexc("C99E3E"), hi=hexc("F6DC8A"))
    ic.line(arc_pts(48.5, 49.5, 8.2, 8.2, 0, 360, 36), 0.8, opacity=0.5)


def icon_Food(ic):
    rice = [(9, 34)] + bez((9, 34), (12, 13), (52, 13), (55, 34), 24)
    ic.shape(rice, hexc("F4EEDC"), hi=(1, 1, 1))
    for (x, y) in ((22, 26), (30, 22), (38, 25), (27, 30), (42, 30), (34, 29), (18, 31), (46, 27)):
        ic.ink(lambda m, x=x, y=y: m.ellipse(x, y, 1.2, 0.7), opacity=0.35)
    ic.line([(28, 30), (52, 3)], 2.2, C["red"])
    ic.line([(33, 31), (58, 7)], 2.2, C["red"])
    bowl = [(5, 33), (59, 33)] + arc_pts(32, 33, 27, 22, 0, 180, 30)
    ic.shape(bowl, C["cloth"], hi=(1, 1, 1))
    ic.shape([(13, 42), (51, 42), (48.5, 47), (15.5, 47)], C["blue"], outline=0.9)
    ic.shape([(23, 54), (41, 54), (40, 59), (24, 59)], C["cloth"], outline=1.2)


def icon_Order(ic):
    ic.line([(32, 12), (32, 55)], 3.6, C["wood_dark"])
    ic.shape([(18, 54), (46, 54), (50, 60), (14, 60)], C["wood"])
    ic.line([(6, 16), (58, 16)], 3.2, C["bronze"])
    ic.shape(lambda m: m.circle(32, 11, 4), C["gold"], outline=1.1)
    for x in (12, 52):
        ic.line([(x, 17), (x - 7, 38)], 0.9)
        ic.line([(x, 17), (x + 7, 38)], 0.9)
        pan = [(x - 10, 37), (x + 10, 37)] + arc_pts(x, 37, 10, 6.5, 0, 180, 16)
        ic.shape(pan, C["bronze"], hi=hexc("F0CF7A"))


def icon_Defense(ic):
    ic.shape(lambda m: m.circle(32, 32, 27), C["gold"], hi=hexc("FFE9A0"))
    ic.shape(lambda m: m.circle(32, 32, 22), C["red"], hi=hexc("D8604A"))
    for k in range(8):
        a = math.radians(k * 45 + 22.5)
        ic.shape(lambda m, a=a: m.circle(32 + 17 * math.cos(a), 32 + 17 * math.sin(a), 2.2), C["gold"], outline=0.9)
    ic.shape(lambda m: m.circle(32, 32, 9), C["gold"], hi=hexc("FFF0B0"))
    ic.ink(lambda m: m.poly([(32, 26), (37, 32), (32, 38), (27, 32)]), C["red_dark"])


def icon_Training(ic):
    bow = bez((22, 4), (48, 12), (48, 52), (22, 60), 30)
    ic.line([(20, 4), (20, 60)], 1.0, C["cloth"])
    ic.line([(20.5, 5), (20.5, 59)], 0.6)
    poly = stroke_poly(bow, 4.2, 4.2)
    ic.shape(poly, C["wood"], outline=1.2)
    ic.shape([(39, 26), (45, 26), (45, 38), (39, 38)], C["red"], outline=1.0)
    ic.shape(lambda m: m.circle(22, 4.5, 2.2), C["gold"], outline=0.8)
    ic.shape(lambda m: m.circle(22, 59.5, 2.2), C["gold"], outline=0.8)
    ic.line([(8, 32), (54, 32)], 2.0, C["wood_light"])
    ic.shape([(53, 27.5), (62, 32), (53, 36.5)], C["steel"], outline=1.0)
    ic.shape([(4, 27), (12, 29.5), (14, 32), (4, 32)], C["red"], outline=0.9)
    ic.shape([(4, 37), (12, 34.5), (14, 32), (4, 32)], C["red"], outline=0.9)


def icon_Loyalty(ic):
    ic.shape(lambda m: m.circle(32, 32, 27), C["gold"], hi=hexc("FFE9A0"))
    ic.shape(lambda m: m.circle(32, 32, 23), C["red"], hi=hexc("C85040"))
    f = font(FONT_BRUSH, 34 * R)
    ic.shape(lambda m: m.text((32, 33.5), "忠", f), C["gold"], outline=0.0, hi=hexc("FFF0B0"))


def icon_Settings(ic):
    pts = []
    n = 8
    for i in range(n * 4):
        a = math.radians(i * 360.0 / (n * 4) - 90 + 360.0 / (n * 8))
        r = 27 if (i % 4) in (1, 2) else 20.5
        pts.append((32 + r * math.cos(a), 32 + r * math.sin(a)))

    def gear(m):
        m.poly(pts)
        m.circle(32, 32, 8, 0)
    ic.shape(gear, C["bronze"], hi=hexc("F0CF7A"))
    ic.line(arc_pts(32, 32, 14, 14, 0, 360, 40), 1.0, opacity=0.55)


def icon_Delegate(ic):
    tab = [(16, 58), (16, 20)] + arc_pts(32, 20, 16, 13, 180, 360, 20) + [(48, 20), (48, 58)]
    ic.shape(tab, C["gold"], hi=hexc("FFEAA0"))
    inner = [(20, 54), (20, 21)] + arc_pts(32, 21, 12, 9.5, 180, 360, 20) + [(44, 21), (44, 54)]
    ic.line(inner + [inner[0]], 1.0, C["red_dark"], opacity=0.85)
    f = font(FONT_BRUSH, 25 * R)
    ic.ink(lambda m: m.text((32, 35), "令", f), C["red_dark"])
    ic.line([(32, 58), (32, 61)], 1.5, C["red"])
    ic.shape([(29, 59), (35, 59), (37, 64), (27, 64)], C["red"], outline=0.9)


def icon_Prisoner(ic):
    links = [(24, 18, 5.5, 3.6, 0), (32, 14, 3.4, 5.4, 0), (40, 18, 5.5, 3.6, 0)]
    for (x, y, rx, ry, _) in links:
        def lk(m, x=x, y=y, rx=rx, ry=ry):
            m.ellipse(x, y, rx, ry)
            m.ellipse(x, y, rx - 2.4, ry - 2.4, 0)
        ic.shape(lk, C["iron"], outline=1.0)
    for x in (17, 47):
        def cuff(m, x=x):
            m.ellipse(x, 39, 13, 14)
            m.ellipse(x, 39, 7.8, 8.8, 0)
        ic.shape(cuff, C["iron"], hi=hexc("D8DEE2"))
        ic.shape(lambda m, x=x: m.rect(x - 3, 23, x + 3, 28), C["iron"], outline=1.0)
    ic.shape(lambda m: m.circle(17, 52.5, 2.2), C["stone_dark"], outline=0.8)
    ic.shape(lambda m: m.circle(47, 52.5, 2.2), C["stone_dark"], outline=0.8)


def icon_Fire(ic):
    outer = [(32, 61)] + bez((32, 61), (6, 60), (6, 34), (20, 20), 16) + bez((20, 20), (18, 30), (24, 32), (26, 26), 8) \
        + bez((26, 26), (26, 14), (36, 10), (34, 2), 12) + bez((34, 2), (48, 12), (46, 26), (44, 30), 12) \
        + bez((44, 30), (48, 28), (50, 24), (50, 20), 6) + bez((50, 20), (62, 34), (58, 60), (32, 61), 16)
    ic.shape(outer, C["flame"], hi=hexc("FFB060"))
    mid = [(32, 60)] + bez((32, 60), (16, 58), (16, 40), (26, 32), 12) + bez((26, 32), (28, 38), (32, 38), (33, 30), 8) \
        + bez((33, 30), (36, 22), (40, 24), (40, 18), 8) + bez((40, 18), (50, 32), (50, 56), (32, 60), 14)
    ic.shape(mid, C["flame_core"], outline=0.0, hi=(1, 1, 0.85))
    core = [(32, 59)] + bez((32, 59), (24, 58), (24, 48), (31, 42), 10) + bez((31, 42), (34, 46), (37, 44), (38, 40), 6) \
        + bez((38, 40), (44, 50), (40, 58), (32, 59), 10)
    ic.shape(core, hexc("FFF6D0"), outline=0.0, flat=True)


def icon_Confuse(ic):
    pts = []
    for i in range(80):
        t = i / 79.0
        a = t * 2.6 * 2 * math.pi
        r = 3 + 22 * t
        pts.append((32 + r * math.cos(a), 33 + r * math.sin(a)))
    ic.shape(stroke_poly(pts, 2.5, 7.5), C["purple"], hi=hexc("B49AE0"))
    for (x, y, r) in ((50, 10, 6.5), (12, 52, 5), (54, 50, 4.5)):
        ic.shape(star_pts(x, y, r, r * 0.42), C["gold"], outline=1.0)


def icon_Rally(ic):
    ic.line([(14, 62), (48, 40)], 3.2, C["wood_dark"])
    ic.line([(50, 62), (16, 40)], 3.2, C["wood_dark"])
    drum = [(10, 26), (54, 26), (52, 50), (12, 50)]
    ic.shape(lambda m: m.ellipse(32, 38, 23, 14.5), C["red"], hi=hexc("D8604A"))
    ic.shape(lambda m: m.ellipse(32, 28, 21, 7.5), C["cloth"], hi=(1, 1, 1))
    for k in range(9):
        a = math.radians(200 + k * 17.5)
        ic.shape(lambda m, a=a: m.circle(32 + 21 * math.cos(a) * 1.0, 28 + 7.5 * math.sin(a) + 3.2, 1.3), C["gold"], outline=0.6)
    ic.line(arc_pts(32, 38, 22.5, 14.0, 20, 160, 20), 1.0, C["gold"])
    # drumsticks
    ic.line([(40, 23), (60, 4)], 2.6, C["wood_light"])
    ic.line([(24, 23), (6, 6)], 2.6, C["wood_light"])
    ic.shape(lambda m: m.circle(39.5, 23.5, 3.2), C["red"], outline=1.0)
    ic.shape(lambda m: m.circle(24.5, 23.5, 3.2), C["red"], outline=1.0)


def jian(ic, x0, y0, x1, y1, guard_col=None):
    L = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / L, (y1 - y0) / L
    nx, ny = -uy, ux
    gx, gy = x0 + ux * 15, y0 + uy * 15

    def P(t, w):
        return (x0 + ux * t + nx * w, y0 + uy * t + ny * w)
    blade = [P(16, -2.6), P(L - 6, -2.4), P(L, 0), P(L - 6, 2.4), P(16, 2.6)]
    ic.shape(blade, C["steel"], hi=(1, 1, 1))
    ic.line([P(17, 0), P(L - 6, 0)], 0.8, opacity=0.5)
    ic.shape([P(4, -2), P(14, -2), P(14, 2), P(4, 2)], C["black"], outline=1.0)
    ic.shape([P(13, -6.5), P(17, -6.5), P(17, 6.5), P(13, 6.5)], guard_col if guard_col is not None else C["gold"], outline=1.0)
    ic.shape(lambda m: m.circle(*P(2.2, 0), 2.6), C["gold"], outline=0.9)
    ic.line([P(0.5, 0), P(-4, 4), P(-7, 3)], 1.6, C["red"])


def icon_Duel(ic):
    jian(ic, 8, 58, 58, 6)
    jian(ic, 56, 58, 6, 6)


def icon_Attack(ic):
    ic.line(arc_pts(10, 60, 46, 46, -86, -6, 30), 2.2, C["red"], opacity=0.8, w1=0.4)
    ic.line(arc_pts(10, 60, 40, 40, -80, -10, 30), 1.4, C["red"], opacity=0.6, w1=0.3)
    blade = [(16, 46), (19, 50)] + bez((19, 50), (34, 38), (48, 22), (60, 3), 18) + bez((60, 3), (50, 10), (36, 22), (16, 46), 18)
    ic.shape(blade, C["steel"], hi=(1, 1, 1))
    ic.line(bez((20, 46), (34, 34), (46, 20), (57, 7), 16), 0.8, opacity=0.5)
    ic.shape(rot([(8, 46), (24, 46), (24, 50.5), (8, 50.5)], 16, 48.25, 45), C["gold"], outline=1.0)
    ic.line([(16, 50), (5, 61)], 4.0, C["black"])
    ic.shape(lambda m: m.circle(5, 61, 2.5), C["gold"], outline=0.8)


def icon_Wait(ic):
    for (x, a) in ((26, -6), (32, 0), (38, 6)):
        ic.line([(x, 34), (x + a * 0.5, 12)], 1.4, C["red_dark"])
        ic.shape(lambda m, x=x, a=a: m.circle(x + a * 0.5, 11.5, 1.4), C["flame_core"], outline=0.6)
    for (x, ph) in ((29, 0.0), (35, 2.2)):
        pts = [(x + math.sin(i / 3.0 + ph) * 2.2, 9.5 - i * 0.95) for i in range(10)]
        ic.line(pts, 1.1, PAL["ink_soft"], opacity=0.5, w1=0.3)
    ic.line([(16, 50), (12, 61)], 3.0, C["bronze"])
    ic.line([(48, 50), (52, 61)], 3.0, C["bronze"])
    ic.line([(32, 52), (32, 61)], 3.0, C["bronze"])
    body = [(9, 32), (55, 32)] + arc_pts(32, 32, 23, 21, 0, 180, 24)
    ic.shape(body, C["bronze"], hi=hexc("F0CF7A"))
    ic.shape([(7, 29), (57, 29), (57, 34), (7, 34)], C["bronze"], outline=1.2)
    for x in (12, 52):
        ic.shape(lambda m, x=x: m.rect(x - 2.5, 21, x + 2.5, 30), C["bronze"], outline=1.0)
    ic.line([(14, 42), (50, 42)], 1.0, opacity=0.6)
    ic.line(arc_pts(32, 42, 4, 4, 180, 360, 12), 1.0, opacity=0.6)


def icon_Undo(ic):
    pts = arc_pts(34, 36, 20, 19, 170, 360 + 100, 40)
    body = stroke_poly(pts[::-1], 3.0, 8.5)
    ic.shape(body, C["red"], hi=hexc("E0705A"))
    hx, hy = pts[0]
    head = [(hx - 9.5, hy - 6), (hx + 10.5, hy - 5), (hx - 0.5, hy + 12)]
    head = rot(head, hx, hy, 8)
    ic.shape(head, C["red"], hi=hexc("E0705A"))


ICONS = ["Farm", "Commerce", "Walls", "Patrol", "Draft", "Train", "Search", "Recruit", "Move",
         "Transport", "SectTraining", "Alliance", "Truce", "Gift", "March", "Market", "Tavern",
         "Officers", "Factions", "Save", "Load", "EndTurn", "Gold", "Food", "Troops", "Population",
         "Order", "Defense", "Training", "Loyalty", "Settings", "Delegate", "Prisoner", "Fire",
         "Confuse", "Rally", "Duel", "Attack", "Wait", "Undo"]


def main():
    names = sys.argv[1:] or ICONS
    for i, name in enumerate(ICONS):
        if name not in names:
            continue
        ic = Icon(seed=1000 + i)
        globals()["icon_" + name](ic)
        ic.finish().save(os.path.join(OUT, "Icon_%s.png" % name))


if __name__ == "__main__":
    main()
