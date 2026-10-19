"""The 13 hex terrains of the battle board (DESIGN.md 4 + 12.3): height, painted ground, props.

Every terrain is a :class:`Spec`: ``h(x, y)`` (vectorised heightfield of the top, 0 on the
boundary), ``paint(cv)`` (the planar ground painting, :mod:`ironart.battle_paint`), ``props(mb)``
(MeshBuilder content with ``B_*`` / ``W_*`` slots).  Board facts that shaped them:

* units stand at z = 0 on the hex centre on a 6 m plinth (r = 3 m, figures within r ~2.2 m), so
  every passable terrain keeps its centre low and clear and puts tall things near the corners
* natural terrains (Plain, Forest, Hill, Mountain, Water) are rotated by random multiples of 60
  deg: their rims are 12-fold symmetric (see battle_paint); the others keep the Blender frame:
  roads, fords and bridges run along x (corner to corner, flaring along the corner edges so a
  row of road hexes joins), walls and gates along y (board columns), the castle's hall at +y
  (the back, away from the camera)
* tall things stay low enough not to hide the row behind at the 50 deg board camera
  (mountains <= 4.6 m, trees <= 4.3 m, gate tower ~6.3 m)
"""

import math
import random

import numpy as np
from mathutils import Matrix, Vector

from ironart import battle_paint as BP
from ironart import battle_arch as BA
from ironart import battle_props as PR
from ironart.battle_hex import WATER_Z

P = BP.P
RIM_MEADOW = P["meadow"]
TAU = math.tau


class Spec:
    def __init__(self, name, seed, n=40, water=None, skirt="land", props_px=2048, notes=""):
        self.name = name
        self.seed = seed
        self.rng = random.Random(seed)
        self.n = n
        self.water = water
        self.skirt = skirt
        self.props_px = props_px
        self.notes = notes
        self.layout = []          # prop footprints (x, y, radius) the painter grounds with marks

    def h(self, x, y):
        return np.zeros_like(x)

    def paint(self, cv):
        meadow(cv, self.rng, self.seed)

    def props(self, mb):
        pass

    def prototypes(self):
        """{name: builder(mb)} of instanced props (baked once, placed many times)."""
        return {}

    def placements(self):
        """[(prototype name, world Matrix)]."""
        return []

    @property
    def top_z(self):
        return self.water if self.water is not None else 0.0


# ---------------------------------------------------------------------------------------------
# shared painting
# ---------------------------------------------------------------------------------------------
def scatter(rng, n, d_min=0.0, r_max=None, avoid=(), min_sep=0.0, tries=4000, r_min=0.0):
    """Random points inside the hexagon: at least ``d_min`` from the boundary, within
    [``r_min``, ``r_max``] of the centre, ``min_sep`` apart and outside ``avoid`` discs."""
    pts = []
    for _ in range(tries):
        if len(pts) >= n:
            break
        x, y = rng.uniform(-BP.R, BP.R), rng.uniform(-BP.APO, BP.APO)
        r = math.hypot(x, y)
        if r_max is not None and r > r_max or r < r_min:
            continue
        if float(BP.hex_d(np.float32(x), np.float32(y))) < d_min:
            continue
        if any(math.hypot(x - ax, y - ay) < ar for ax, ay, ar in avoid):
            continue
        if any(math.hypot(x - px, y - py) < min_sep for px, py in pts):
            continue
        pts.append((x, y))
    return pts


def sym12_strokes(strokes):
    """The 12 symmetric copies (6 rotations x mirror) of strokes painted in the fundamental wedge."""
    out = []
    for m in (1.0, -1.0):
        for k in range(6):
            a = math.radians(60.0 * k)
            ca, sa = math.cos(a), math.sin(a)
            for st in strokes:
                q = np.asarray(st["pts"], np.float32) * np.array([1.0, m], np.float32)
                d = dict(st)
                d["pts"] = np.stack([q[:, 0] * ca - q[:, 1] * sa, q[:, 0] * sa + q[:, 1] * ca], -1)
                out.append(d)
    return out


def patchiness(x, y, seed):
    """0..1 density of grass clumps (meadow patches): a low-frequency field that is 12-fold
    symmetric in the rim (folded polar coordinates) and free inside."""
    x = np.asarray(x, np.float32)
    y = np.asarray(y, np.float32)
    d = BP.hex_d(x, y)
    r = np.hypot(x, y)
    a = np.mod(np.arctan2(y, x), math.pi / 3)
    a = np.minimum(a, math.pi / 3 - a)               # 0..30 deg from the corner direction
    fx, fy = r * np.cos(a), r * np.sin(a)
    sym = BP.fbm(fx, fy, scale=0.7, octaves=2, seed=seed + 77)
    free = BP.fbm(x, y, scale=0.55, octaves=3, seed=seed + 78)
    w = BP.smooth(0.5, 1.1, d)
    return sym * (1 - w) + free * w


def meadow_clumps(rng, seed, density=9.0, d_in=0.62, layout=(), color=None, alpha=0.6, rim=True,
                  length=(0.05, 0.11)):
    """Grass clumps: free inside (d > d_in), 12-fold symmetric in the rim band, denser in
    patches and around the props' feet."""
    pts = []
    tries = int(density * 41.6 * 3)
    for _ in range(tries):
        x, y = rng.uniform(-4, 4), rng.uniform(-3.47, 3.47)
        if float(BP.hex_d(np.float32(x), np.float32(y))) <= d_in:
            continue
        if rng.random() < 0.05 + 0.95 * float(BP.smooth(0.42, 0.7, patchiness(x, y, seed))):
            pts.append((x, y))
        if len(pts) >= density * 41.6:
            break
    for (px, py, pr) in layout:
        for _ in range(int(5 + 8 * pr)):
            a = rng.uniform(0, TAU)
            r = pr * rng.uniform(0.9, 1.6)
            x, y = px + r * math.cos(a), py + r * math.sin(a)
            if float(BP.hex_d(np.float32(x), np.float32(y))) > d_in:
                pts.append((x, y))
    out = BP.grass_clumps(rng, pts, color=color, alpha=alpha, length=length)
    if rim:
        wedge = []
        n_w = int(density * 1.15)
        tries = 0
        while len(wedge) < n_w and tries < 5000:
            tries += 1
            p = BP.wedge_points(rng, 1, 0.1, d_in)[0]
            if rng.random() < 0.05 + 0.95 * float(BP.smooth(0.42, 0.7, patchiness(p[0], p[1], seed))):
                wedge.append(tuple(p))
        out += sym12_strokes(BP.grass_clumps(rng, wedge, color=color, alpha=alpha, length=length))
    return out


def meadow(cv, rng, seed, marks=1.0, flowers=0.6, rim=RIM_MEADOW, base=None, layout=(), d_in=0.62):
    """The meadow family ground: a pale silk-green wash with soft 晕染 swells and bare-silk
    patches, deeper green grass patches, ink-green grass clumps (12-fold symmetric in the rim),
    sparse flower dots, clumps gathered round the props' feet."""
    X, Y = cv.X, cv.Y
    d = BP.hex_d(X, Y)
    w_in = BP.smooth(0.3, 1.2, d)
    if base is None:
        n1 = BP.fbm(X, Y, scale=0.3, octaves=3, seed=seed)
        n2 = BP.fbm(X, Y, scale=0.85, octaves=3, seed=seed + 1)
        col = BP.mix(P["meadow_d"], P["meadow_l"], BP.smooth(0.3, 0.72, n1))
        col = BP.mix(col, P["meadow_blue"], BP.smooth(0.5, 0.78, n2) * 0.55)
        col = BP.mix(col, P["meadow_silk"], BP.smooth(0.6, 0.78, n1) * 0.55)
    else:
        col = base
    col = BP.mix(rim, col, w_in)
    cv.wash(col)
    if marks <= 0:
        return
    # grass patches: a soft deeper glaze where the clumps gather (symmetric in the rim)
    pt = patchiness(X, Y, seed)
    cv.glaze(P["meadow_d"] / np.maximum(rim, 1e-3), BP.smooth(0.5, 0.75, pt) * 0.2)
    cv.strokes(meadow_clumps(rng, seed, density=3.2 * marks, layout=layout))
    cv.strokes(meadow_clumps(rng, seed + 1, density=1.0 * marks, color=P["grass_mark_d"], alpha=0.5,
                             length=(0.04, 0.08)))
    if flowers > 0:
        nf = int(18 * flowers)
        for _ in range(nf):
            x, y = rng.uniform(-3, 3), rng.uniform(-2.8, 2.8)
            if float(BP.hex_d(np.float32(x), np.float32(y))) < 1.0:
                continue
            colf = [P["white"], P["cinnabar"], P["gold"], P["white"]][rng.randint(0, 3)]
            cl = [(x + rng.gauss(0, 0.07), y + rng.gauss(0, 0.07)) for _ in range(rng.randint(2, 5))]
            cv.dots(cl, 0.012, colf, 0.9, h=0.002)


def moss_dots(cv, rng, layout, color=None, alpha=0.75):
    """苔点: clusters of ink dots at the foot of rocks."""
    col = P["ink_green"] if color is None else color
    for (px, py, pr) in layout:
        for _ in range(int(4 + 10 * pr)):
            a = rng.uniform(0, TAU)
            r = pr * rng.uniform(0.85, 1.3)
            x, y = px + r * math.cos(a), py + r * math.sin(a)
            cv.dots([(x, y)], rng.uniform(0.008, 0.016), col, alpha * rng.uniform(0.6, 1.0), h=0.003,
                    squash=rng.uniform(0.6, 1.0), angle=rng.uniform(0, TAU))


def micro_relief(x, y, seed, amp=0.05, scale=0.5):
    d = BP.hex_d(x, y)
    return amp * (BP.fbm(x, y, scale=scale, octaves=3, seed=seed) - 0.5) * 2.0 * BP.smooth(0.3, 1.2, d)


# ---------------------------------------------------------------------------------------------
# terrains
# ---------------------------------------------------------------------------------------------
class Plain(Spec):
    """Meadow with grass tufts, a few stones and flowers; centre kept clear for the plinth."""

    def __init__(self):
        super().__init__("Plain", 1101, n=32, props_px=1024)
        rng = self.rng
        self.stones = []
        for cl in scatter(rng, 2, d_min=0.8, r_min=2.2, min_sep=2.5):
            for k in range(rng.randint(1, 3)):
                a = rng.uniform(0, TAU)
                r = 0.0 if k == 0 else rng.uniform(0.25, 0.45)
                s = rng.uniform(0.36, 0.5) if k == 0 else rng.uniform(0.14, 0.24)
                self.stones.append((cl[0] + r * math.cos(a), cl[1] + r * math.sin(a), s))
        self.tufts = scatter(rng, 9, d_min=0.35, r_min=1.9, min_sep=0.9,
                             avoid=[(x, y, s + 0.15) for x, y, s in self.stones])
        self.tufts += scatter(rng, 2, d_min=1.5, r_max=1.6, min_sep=0.9)
        self.layout = [(x, y, s * 1.1) for x, y, s in self.stones] + [(x, y, 0.12) for x, y in self.tufts]

    def h(self, x, y):
        return micro_relief(x, y, self.seed)

    def paint(self, cv):
        meadow(cv, self.rng, self.seed, layout=self.layout)
        moss_dots(cv, self.rng, [(x, y, s * 1.1) for x, y, s in self.stones])

    def props(self, mb):
        rng = self.rng
        for x, y, s in self.stones:
            PR.facet_rock(mb, rng, (x, y, float(self.h(np.float32(x), np.float32(y)))), s,
                          "B_Rock" if rng.random() < 0.7 else "B_RockGrey")
        for i, (x, y) in enumerate(self.tufts):
            small = math.hypot(x, y) < 1.7
            PR.grass_tuft(mb, rng, (x, y, 0.0), height=rng.uniform(0.18, 0.24) if small else rng.uniform(0.26, 0.4),
                          n=rng.randint(4, 6) if small else rng.randint(5, 8))


def relief(cv, hfn):
    """Height, slope (rise / run) and downhill direction of a heightfield on the canvas."""
    H = hfn(cv.X, cv.Y)
    gy, gx = np.gradient(H)
    hx = gx * cv.ppm
    hy = -gy * cv.ppm
    return H, np.hypot(hx, hy), np.arctan2(-hy, -hx)


def grad_at(hfn, x, y, e=0.02):
    x = np.float32(x)
    y = np.float32(y)
    hx = (hfn(x + e, y) - hfn(x - e, y)) / (2 * e)
    hy = (hfn(x, y + e) - hfn(x, y - e)) / (2 * e)
    return float(hx), float(hy)


def slope_strokes(rng, hfn, n, cond, length=(0.15, 0.35), width=0.012, color=None, alpha=0.4, steps=5,
                  region=3.9, d_min=0.25, jitter=0.25):
    """皴 texture strokes running down the slope (hemp-fibre / axe-cut shorthand): start points
    where ``cond(x, y, z, slope)`` holds, traced downhill."""
    col = P["ink_umber"] if color is None else color
    out = []
    tries = 0
    while len(out) < n and tries < n * 40:
        tries += 1
        x, y = rng.uniform(-region, region), rng.uniform(-region, region)
        if float(BP.hex_d(np.float32(x), np.float32(y))) < d_min:
            continue
        z = float(hfn(np.float32(x), np.float32(y)))
        hx, hy = grad_at(hfn, x, y)
        sl = math.hypot(hx, hy)
        if not cond(x, y, z, sl):
            continue
        L = rng.uniform(*length)
        pts = [(x, y)]
        cx, cy = x, y
        wob = rng.uniform(-jitter, jitter)
        for k in range(steps):
            hx, hy = grad_at(hfn, cx, cy)
            g = math.hypot(hx, hy) + 1e-6
            dx, dy = -hx / g, -hy / g
            ca, sa = math.cos(wob), math.sin(wob)
            dx, dy = dx * ca - dy * sa, dx * sa + dy * ca
            cx += dx * L / steps
            cy += dy * L / steps
            if float(BP.hex_d(np.float32(cx), np.float32(cy))) < 0.05:
                break
            pts.append((cx, cy))
        if len(pts) < 3:
            continue
        out.append(dict(pts=np.array(pts), w=width * rng.uniform(0.8, 1.25), color=col, alpha=alpha * rng.uniform(0.6, 1.0),
                        taper=(0.15, 0.6), dry=0.35, h=0.003, seed=rng.randint(0, 99999)))
    return out


def moss_cluster(cv, rng, x, y, n, spread, color=None, alpha=0.8, size=(0.012, 0.022)):
    col = P["ink_green"] if color is None else color
    pts = [(x + rng.gauss(0, spread), y + rng.gauss(0, spread * 0.6)) for _ in range(n)]
    for (px, py) in pts:
        cv.dots([(px, py)], rng.uniform(*size), col, alpha * rng.uniform(0.6, 1.0), h=0.004,
                squash=rng.uniform(0.5, 0.9), angle=rng.uniform(0, TAU))


TREE_PROTOS = {
    "broadA": lambda mb: PR.broadleaf(mb, random.Random(71), (0, 0, 0), height=3.7, crown=1.05, canopy="B_Canopy",
                                      clusters=11),
    "broadB": lambda mb: PR.broadleaf(mb, random.Random(72), (0, 0, 0), height=3.5, crown=1.0, canopy="B_CanopyAz",
                                      clusters=10),
    "broadC": lambda mb: PR.broadleaf(mb, random.Random(73), (0, 0, 0), height=3.3, crown=0.95, canopy="B_CanopyOl",
                                      clusters=10),
    "pineA": lambda mb: PR.pine(mb, random.Random(74), (0, 0, 0), height=4.1, tiers=6),
    "pineB": lambda mb: PR.pine(mb, random.Random(75), (0, 0, 0), height=3.6, tiers=5),
}


def place(x, y, z=0.0, yaw=0.0, s=1.0):
    return Matrix.Translation(Vector((x, y, z))) @ Matrix.Rotation(yaw, 4, "Z") @ Matrix.Scale(s, 4)


class Forest(Spec):
    """Forest floor with 7-9 gongbi trees (dotted-leaf broadleaves in malachite, azurite and
    olive, pines with needle pads; instanced prototypes) gathered at the corners and the rim, a
    clearing in the centre for the plinth; shrubs, moss dots and fallen-leaf marks beneath."""

    def __init__(self):
        super().__init__("Forest", 2202, n=32, props_px=2048)
        rng = self.rng
        trees = []
        # one tree near most corners (the lattice vertices: three tiles' corner trees make a copse)
        for k in range(6):
            if k == 2:
                continue
            a = math.radians(60 * k + rng.uniform(-12, 12))
            r = rng.uniform(2.75, 3.15)
            trees.append((r * math.cos(a), r * math.sin(a)))
        for k in range(6):
            if rng.random() < 0.5:
                a = math.radians(60 * k + 30 + rng.uniform(-10, 10))
                r = rng.uniform(2.35, 2.6)
                trees.append((r * math.cos(a), r * math.sin(a)))
        kinds = ["broadA", "pineA", "broadB", "broadC", "pineB", "broadA", "broadB", "pineA", "broadC", "broadA"]
        self.trees = [(x, y, kinds[i % len(kinds)], rng.uniform(0, TAU), rng.uniform(0.8, 0.95))
                      for i, (x, y) in enumerate(trees)]
        self.shrubs = scatter(rng, 6, d_min=0.45, r_min=1.6, r_max=3.0, min_sep=1.0,
                              avoid=[(x, y, 0.85) for x, y, *_ in self.trees])
        self.tufts = scatter(rng, 9, d_min=0.35, r_min=1.4, min_sep=0.7,
                             avoid=[(x, y, 0.6) for x, y, *_ in self.trees] + [(x, y, 0.6) for x, y in self.shrubs])
        self.layout = [(x, y, 0.35) for x, y, *_ in self.trees]

    def h(self, x, y):
        return micro_relief(x, y, self.seed, amp=0.06)

    def paint(self, cv):
        X, Y = cv.X, cv.Y
        rng = self.rng
        n1 = BP.fbm(X, Y, scale=0.35, octaves=3, seed=self.seed)
        n2 = BP.fbm(X, Y, scale=1.1, octaves=3, seed=self.seed + 1)
        col = BP.mix(P["forest_floor_d"], P["forest_floor"], BP.smooth(0.3, 0.7, n1))
        col = BP.mix(col, P["meadow_blue"], BP.smooth(0.55, 0.8, n2) * 0.4)
        # shade washes under the crowns (painted 晕染, not light): soft deeper green round each trunk
        shade = np.zeros_like(X)
        for (x, y, *_r) in self.trees:
            shade = np.maximum(shade, np.exp(-((X - x) ** 2 + (Y - y) ** 2) / (2 * 0.75 ** 2)))
        col = BP.mix(col, P["forest_floor_d"] * 0.92, shade * 0.45)
        meadow(cv, rng, self.seed, marks=0.0, base=col, rim=P["forest_floor"])
        cv.strokes(meadow_clumps(rng, self.seed, density=3.0, layout=self.layout, color=P["grass_mark_d"],
                                 alpha=0.55))
        for (x, y, *_r) in self.trees:
            moss_cluster(cv, rng, x, y, 14, 0.35)
            for _ in range(10):
                a = rng.uniform(0, TAU)
                r = rng.uniform(0.3, 1.0)
                px, py = x + r * math.cos(a), y + r * math.sin(a)
                if float(BP.hex_d(np.float32(px), np.float32(py))) > 0.6:
                    cv.dots([(px, py)], rng.uniform(0.012, 0.02), P["leaf_litter"] if rng.random() < 0.7 else P["ochre"],
                            0.7, h=0.002, squash=0.5, angle=rng.uniform(0, TAU))

    def props(self, mb):
        rng = self.rng
        for (x, y) in self.shrubs:
            PR.shrub(mb, rng, (x, y, 0.0), size=rng.uniform(0.35, 0.5),
                     canopy=["B_Canopy", "B_CanopyOl"][rng.randint(0, 1)])
        for (x, y) in self.tufts:
            PR.grass_tuft(mb, rng, (x, y, 0.0), height=rng.uniform(0.22, 0.32), n=rng.randint(4, 6))

    def prototypes(self):
        used = {k for _x, _y, k, *_r in self.trees}
        return {k: v for k, v in TREE_PROTOS.items() if k in used}

    def placements(self):
        return [(k, place(x, y, 0.0, yaw, s)) for (x, y, k, yaw, s) in self.trees]


def bump(x, y, cx, cy, h, rad, power=2.0):
    r2 = ((x - cx) ** 2 + (y - cy) ** 2) / (rad * rad)
    return h * np.clip(1.0 - r2, 0.0, 1.0) ** power


class Hill(Spec):
    """Grassy rise in blue-green landscape manner: two or three knolls toward the rim (the
    centre stays low for the plinth), malachite on the upper slopes over an ochre underlayer on
    the steep ones, hemp-fibre 皴 strokes downslope, moss dots on the crests, embedded rocks."""

    def __init__(self):
        super().__init__("Hill", 3303, n=44, props_px=1024)
        rng = self.rng
        a = rng.uniform(0, TAU)
        self.knolls = [(2.25 * math.cos(a), 2.25 * math.sin(a), 1.45, 2.1),
                       (2.35 * math.cos(a + 2.5), 2.35 * math.sin(a + 2.5), 1.05, 1.75),
                       (2.55 * math.cos(a + 4.3), 2.55 * math.sin(a + 4.3), 0.7, 1.35)]
        self.rocks = []
        for (cx, cy, hh, rr) in self.knolls[:2]:
            for k in range(2):
                b = rng.uniform(0, TAU)
                px, py = cx + 0.55 * rr * 0.5 * math.cos(b), cy + 0.55 * rr * 0.5 * math.sin(b)
                if float(BP.hex_d(np.float32(px), np.float32(py))) > 0.5:
                    self.rocks.append((px, py, rng.uniform(0.3, 0.48)))
        self.tufts = scatter(rng, 10, d_min=0.4, r_min=1.2, min_sep=0.7, avoid=[(x, y, s + 0.2) for x, y, s in self.rocks])
        # shrubs at the knolls' feet and a small dotted-leaf tree on the second knoll
        self.shrubs = []
        for (cx, cy, hh, rr) in self.knolls:
            b = math.atan2(cy, cx) + rng.choice((-1, 1)) * rng.uniform(0.7, 1.1)
            px, py = cx + 0.62 * rr * math.cos(b), cy + 0.62 * rr * math.sin(b)
            if float(BP.hex_d(np.float32(px), np.float32(py))) > 0.45:
                self.shrubs.append((px, py))
        cx, cy, hh, rr = self.knolls[1]
        self.tree = (cx * 0.95, cy * 0.95)
        self.rocks = [(x, y, s) for (x, y, s) in self.rocks if math.hypot(x - self.tree[0], y - self.tree[1]) > s + 0.55]

    def h(self, x, y):
        x = np.asarray(x, np.float32)
        y = np.asarray(y, np.float32)
        d = BP.hex_d(x, y)
        z = 0.22 * np.exp(-(x * x + y * y) / (2 * 2.2 ** 2))
        for (cx, cy, hh, rr) in self.knolls:
            z = z + bump(x, y, cx, cy, hh, rr, 1.6)
        n = BP.fbm(x, y, scale=0.8, octaves=3, seed=self.seed)
        z = z * (0.85 + 0.3 * n) + 0.04 * (n - 0.5)
        return z * BP.smooth(0.18, 1.45, d)

    def paint(self, cv):
        X, Y = cv.X, cv.Y
        rng = self.rng
        H, S, A = relief(cv, self.h)
        meadow(cv, rng, self.seed, marks=0.6, layout=[(x, y, s) for x, y, s in self.rocks])
        n = BP.fbm(X, Y, scale=0.9, octaves=3, seed=self.seed + 4)
        hmax = max(k[2] for k in self.knolls)
        t = np.clip(H / hmax + (n - 0.5) * 0.25, 0, 1.2)
        hc = BP.mix(BP.c("#B8C496"), BP.c("#A9C49C"), BP.smooth(0.08, 0.4, t))
        hc = BP.mix(hc, BP.c("#79AE8E"), BP.smooth(0.4, 0.8, t))
        hc = BP.mix(hc, BP.c("#5E95A0"), BP.smooth(0.82, 1.05, t) * 0.6)
        hc = BP.mix(hc, BP.c("#C4B88C"), BP.smooth(0.8, 1.3, S) * (1 - BP.smooth(0.25, 0.55, t)) * 0.2)
        wgt = BP.smooth(0.03, 0.3, H)
        cv.wash(hc, wgt * 0.92)
        foot = BP.smooth(0.02, 0.1, H) * (1 - BP.smooth(0.1, 0.35, H))
        cv.glaze(P["meadow_d"] / P["meadow"], foot * 0.55)
        def cond(x, y, z, sl):
            return z > 0.12 and sl > 0.3
        cv.strokes(slope_strokes(rng, self.h, 150, cond, color=BP.c("#5A5A3C"), alpha=0.3, length=(0.08, 0.2),
                                 width=0.011))
        cv.strokes(slope_strokes(rng, self.h, 110, lambda x, y, z, sl: z > 0.45 and sl > 0.15,
                                 color=P["ink_green"], alpha=0.32, length=(0.07, 0.16), width=0.011))
        for (cx, cy, hh, rr) in self.knolls:
            for _ in range(3):
                moss_cluster(cv, rng, cx + rng.gauss(0, 0.35), cy + rng.gauss(0, 0.35), rng.randint(5, 9), 0.08)
        moss_dots(cv, rng, [(x, y, s * 1.05) for x, y, s in self.rocks])

    def props(self, mb):
        rng = self.rng
        for x, y, s in self.rocks:
            z = float(self.h(np.float32(x), np.float32(y)))
            PR.facet_rock(mb, rng, (x, y, z), s, "B_Rock", flat=0.95, n=16)
        for (x, y) in self.tufts:
            z = float(self.h(np.float32(x), np.float32(y)))
            PR.grass_tuft(mb, rng, (x, y, z), height=rng.uniform(0.22, 0.34), n=rng.randint(4, 7))
        for (x, y) in self.shrubs:
            z = float(self.h(np.float32(x), np.float32(y)))
            PR.shrub(mb, rng, (x, y, z - 0.04), size=rng.uniform(0.32, 0.42), canopy=["B_Canopy", "B_CanopyOl"][rng.randint(0, 1)])
        x, y = self.tree
        PR.broadleaf(mb, rng, (x, y, float(self.h(np.float32(x), np.float32(y))) - 0.05), height=2.3, crown=0.72,
                     canopy="B_CanopyOl", clusters=7)
        # a small pine on the main knoll
        cx, cy, hh, rr = self.knolls[0]
        px, py = cx * 0.92, cy * 0.92
        PR.pine(mb, rng, (px, py, float(self.h(np.float32(px), np.float32(py))) - 0.05), height=1.75, tiers=4,
                first=0.2, lean=0.3)


class Mountain(Spec):
    """Craggy blue-green peaks (青绿山水): a main peak and two lower ones (max 4.6 m so the row
    behind stays visible), ochre underpainting on the cliffs, malachite on the shoulders,
    azurite on the summits, axe-cut and hemp-fibre 皴, strata lines, moss dots, crag rocks and
    two small pines on ledges."""

    def __init__(self):
        super().__init__("Mountain", 4404, n=56, props_px=1024)
        rng = self.rng
        a = rng.uniform(0, TAU)
        self.peaks = [(0.35 * math.cos(a), 0.35 * math.sin(a), 4.5, 3.1),
                      (1.9 * math.cos(a + 2.2), 1.9 * math.sin(a + 2.2), 2.9, 2.0),
                      (2.05 * math.cos(a - 1.9), 2.05 * math.sin(a - 1.9), 2.3, 1.7)]

    def h(self, x, y):
        x = np.asarray(x, np.float32)
        y = np.asarray(y, np.float32)
        d = BP.hex_d(x, y)
        z = np.zeros_like(x)
        for i, (cx, cy, hh, rr) in enumerate(self.peaks):
            r = np.clip(np.hypot(x - cx, y - cy) / rr, 0.0, 1.0)
            # steep flanks, rounded (mantou) summit, concave foot
            prof = np.clip(1.0 - r ** 1.5, 0.0, 1.0) ** 1.6
            z = np.maximum(z, hh * prof)
        rid = BP.ridged(x, y, scale=0.85, octaves=5, seed=self.seed)
        crag = 1.0 - 0.5 * BP.smooth(2.6, 4.2, z)
        z = z * (0.66 + 0.5 * rid * crag) + 0.36 * rid * BP.smooth(0.3, 1.8, z) * crag
        # terraces: soft steps (ledges) every ~0.55 m
        step = 0.55
        q = z / step
        f = q - np.floor(q)
        z = (np.floor(q) + BP.smooth(0.2, 0.8, f)) * step * 0.18 + z * 0.82
        return z * BP.smooth(0.15, 1.35, d)

    def paint(self, cv):
        X, Y = cv.X, cv.Y
        rng = self.rng
        H, S, A = relief(cv, self.h)
        meadow(cv, rng, self.seed, marks=0.5)
        n = BP.fbm(X, Y, scale=1.0, octaves=3, seed=self.seed + 4)
        n2 = BP.fbm(X, Y, scale=2.4, octaves=2, seed=self.seed + 5)
        t = H + (n - 0.5) * 0.9
        flat = 1 - BP.smooth(0.8, 1.6, S + (n2 - 0.5) * 0.5)
        ochre = BP.mix(BP.c("#C4A57A"), BP.c("#A8865E"), BP.smooth(0.8, 1.6, S))
        green = BP.mix(BP.c("#4F9677"), BP.c("#93B894"), flat * 0.6 + (n - 0.5) * 0.3)
        azu = BP.mix(BP.c("#3F6F98"), BP.c("#7FA2C2"), flat * 0.55 + (n - 0.5) * 0.3)
        # layered minerals (青绿): ochre underlayer at the foot and on the lower cliffs, malachite
        # laid over the shoulders, azurite over the summits - narrow soft-edged transitions, no mud
        # green over everything above the foot; the ochre underlayer shows at the foot and in
        # crevice patches on the steepest faces
        crev = BP.smooth(1.5, 2.3, S) * BP.smooth(0.5, 0.62, n2)
        gmask = BP.smooth(0.42, 0.58, BP.smooth(0.12, 0.55, t) - 0.45 * crev)
        # the foot is not a brown ring: meadow-dark grading into the green; the ochre underlayer
        # shows only in crevices and in a thin broken band where the steep foot meets the meadow
        footc = BP.mix(BP.c("#A6B78E"), ochre, BP.smooth(0.9, 1.8, S) * BP.smooth(0.45, 0.6, n2) * 0.4)
        col = BP.mix(footc, ochre, BP.smooth(0.25, 0.6, H) * (1 - gmask))
        col = BP.mix(col, green, gmask)
        amask = BP.smooth(0.42, 0.58, BP.smooth(2.0, 3.0, t) * (0.6 + 0.4 * flat) + (n2 - 0.5) * 0.25)
        col = BP.mix(col, azu, amask)
        cv.wash(col, BP.smooth(0.02, 0.3, H))
        zz = H + (n - 0.5) * 0.3
        ph = np.mod(zz / 0.32, 1.0)
        line = BP.smooth(0.05, 0.0, np.minimum(ph, 1 - ph)) * BP.smooth(1.2, 1.7, S) * BP.smooth(0.55, 0.65, n2)
        cv.glaze(P["ink_umber"] * 1.5, line * 0.25)
        cv.strokes(slope_strokes(rng, self.h, 200, lambda x, y, z, sl: z > 0.3 and z < 2.6 and sl > 0.9,
                                 color=P["ink_umber"], alpha=0.38, length=(0.15, 0.35), width=0.013))
        cv.strokes(slope_strokes(rng, self.h, 110, lambda x, y, z, sl: z > 2.3 and sl > 0.6,
                                 color=P["ink_blue"], alpha=0.38, length=(0.12, 0.3), width=0.013))
        cv.strokes(slope_strokes(rng, self.h, 90, lambda x, y, z, sl: z > 0.9 and sl < 1.1,
                                 color=P["ink_green"], alpha=0.32, length=(0.1, 0.2)))
        # moss dots along the shoulders and summits
        for _ in range(26):
            x, y = rng.uniform(-3, 3), rng.uniform(-3, 3)
            z = float(self.h(np.float32(x), np.float32(y)))
            if z > 1.2:
                moss_cluster(cv, rng, x, y, rng.randint(4, 8), 0.07)

    def props(self, mb):
        rng = self.rng
        # cliff pines on the two flattest ledges at mid height: short, leaning, branched low
        cands = []
        for _ in range(400):
            px, py = rng.uniform(-3.2, 3.2), rng.uniform(-3.0, 3.0)
            if float(BP.hex_d(np.float32(px), np.float32(py))) < 0.8:
                continue
            z = float(self.h(np.float32(px), np.float32(py)))
            hx, hy = grad_at(self.h, px, py, 0.1)
            if 0.9 < z < 2.4:
                cands.append((math.hypot(hx, hy), px, py, z))
        cands.sort()
        ledges = []
        for sl, px, py, z in cands:
            if all(math.hypot(px - qx, py - qy) > 2.2 for qx, qy, _z in ledges):
                ledges.append((px, py, z))
            if len(ledges) == 2:
                break
        for (px, py, z) in ledges:
            PR.pine(mb, rng, (px, py, z - 0.1), height=rng.uniform(1.5, 1.8), tiers=4, first=0.16, lean=0.35)
        for p in scatter(rng, 4, d_min=0.35, r_min=3.0, min_sep=1.0):
            PR.facet_rock(mb, rng, (p[0], p[1], float(self.h(np.float32(p[0]), np.float32(p[1])))),
                          rng.uniform(0.2, 0.32), "B_Rock")


class Water(Spec):
    """Deep water: azurite wash with ink 水纹 wave lines with curling crests (quiet near the rim
    so any rotation joins), a few lead-white glints.  The surface sits at WATER_Z: the land
    tiles' earthen skirts are the banks."""

    def __init__(self):
        super().__init__("Water", 5505, n=16, water=WATER_Z, skirt="water", props_px=256)

    def h(self, x, y):
        return np.full_like(np.asarray(x, np.float32), WATER_Z)

    def paint(self, cv):
        water_paint(cv, self.rng, self.seed)


def water_paint(cv, rng, seed, keep_out=None, density=1.0):
    """Azurite water (pale, matte) with flowing 水纹 lines: long, gently undulating ink-blue
    lines in loose parallel bands along one heading, a few curling crests, lead-white glints;
    all quiet within 0.35 m of the rim.  ``keep_out(x, y) -> bool`` skips lines (fords)."""
    X, Y = cv.X, cv.Y
    d = BP.hex_d(X, Y)
    w_in = BP.smooth(0.3, 1.5, d)
    n1 = BP.fbm(X, Y, scale=0.35, octaves=3, seed=seed)
    n2 = BP.fbm(X * 0.6, Y * 1.6, scale=0.8, octaves=3, seed=seed + 1)
    col = BP.mix(P["water"], P["water_d"], BP.smooth(0.35, 0.75, n1) * 0.6)
    col = BP.mix(col, P["water_l"], BP.smooth(0.55, 0.8, n2) * 0.45)
    cv.wash(BP.mix(P["water"], col, w_in))
    # ripple motifs (涟漪): nested elongated arcs in random headings - no global direction, so a
    # river of randomly rotated water tiles reads as one surface
    strokes = []
    placed = []
    for _ in range(int(22 * density)):
        for _t in range(40):
            cx, cy = rng.uniform(-3.4, 3.4), rng.uniform(-3.0, 3.0)
            if float(BP.hex_d(np.float32(cx), np.float32(cy))) > 0.75 and \
                    all(math.hypot(cx - px, cy - py) > 1.0 for px, py in placed) and \
                    (keep_out is None or not keep_out(cx, cy)):
                break
        else:
            continue
        placed.append((cx, cy))
        ang = rng.uniform(0, math.pi)
        ca, sa = math.cos(ang), math.sin(ang)
        size = rng.uniform(0.55, 0.9)
        nk = rng.randint(4, 6)
        for k in range(nk):
            # a gentle flowing line: long, low arc with a soft S, stacked with even spacing
            L = size * (1.0 - 0.1 * abs(k - (nk - 1) / 2)) * rng.uniform(0.85, 1.1)
            ts = np.linspace(-1, 1, 24)
            ex = ts * L
            ey = 0.035 * size * np.sin(ts * math.pi * rng.uniform(1.0, 1.6) + rng.uniform(0, 1)) - 0.05 * size * ts * ts \
                + (k - (nk - 1) / 2) * 0.065
            pts = np.stack([cx + ex * ca - ey * sa, cy + ex * sa + ey * ca], -1)
            if min(float(BP.hex_d(np.float32(px), np.float32(py))) for px, py in pts[::4]) < 0.3:
                continue
            strokes.append(dict(pts=pts, w=0.008, color=P["wave"], alpha=rng.uniform(0.24, 0.36), taper=(0.3, 0.35),
                                seed=rng.randint(0, 9999)))
        if rng.random() < 0.25:
            # a curling crest hook beside the ripple
            hx, hy = cx + size * 0.9 * ca, cy + size * 0.9 * sa
            hook = [(hx + 0.07 * math.cos(ang + 0.5 * j) * (1 - j / 9.0), hy + 0.07 * math.sin(ang + 0.5 * j) * (1 - j / 9.0))
                    for j in range(8)]
            strokes.append(dict(pts=np.array(hook), w=0.009, color=P["wave"], alpha=0.4, taper=(0.05, 0.7)))
    cv.strokes(strokes)
    for _ in range(int(26 * density)):
        x, y = rng.uniform(-3, 3), rng.uniform(-2.6, 2.6)
        if float(BP.hex_d(np.float32(x), np.float32(y))) > 0.6 and (keep_out is None or not keep_out(x, y)):
            a = rng.uniform(0, math.pi)
            L = rng.uniform(0.08, 0.2)
            cv.strokes([dict(pts=np.array([(x, y), (x + L * math.cos(a), y + L * math.sin(a))]), w=0.011,
                             color=P["white"], alpha=0.45, taper=(0.3, 0.5))])


# ---------------------------------------------------------------------------------------------
# built terrains
# ---------------------------------------------------------------------------------------------
def road_halfwidth(x, w0=0.85, flare=0.62, start=1.4):
    """Half width of a road along x: w0 in the middle, flaring towards the corners so that it
    covers the corner half of the four side edges (a row of road hexes joins corner to corner)."""
    return w0 + flare * np.maximum(0.0, np.abs(x) - start)


def road_mask(X, Y, seed, w0=0.85, soft=0.12):
    d = BP.hex_d(X, Y)
    wob = (BP.fbm(X, Y, scale=1.3, octaves=2, seed=seed + 31) - 0.5) * 0.22 * BP.smooth(0.15, 0.7, d)
    hw = road_halfwidth(X, w0) + wob
    return BP.smooth(hw + soft, hw - soft, np.abs(Y))


def paint_earth(cv, mask, seed, rng, ruts=True, pebbles=True, color=None, rut_y=(-0.36, 0.36), rut_x=2.6):
    """Packed earth (赭石 wash over silk): soft 晕染 swells, darker rim along its edge, cart ruts
    as broken ink-umber lines along x, pebble dots, grass marks on the verges."""
    X, Y = cv.X, cv.Y
    n = BP.fbm(X, Y, scale=0.7, octaves=3, seed=seed + 41)
    base = BP.c("#CDB58C") if color is None else color
    col = BP.mix(base, BP.c("#B99D74"), BP.smooth(0.35, 0.75, n) * 0.6)
    col = BP.mix(col, BP.c("#DAC9A4"), BP.smooth(0.6, 0.8, BP.fbm(X, Y, scale=1.6, octaves=2, seed=seed + 42)) * 0.5)
    cv.wash(col, mask)
    edge = mask * (1 - mask) * 4.0
    cv.glaze(BP.c("#A88C66") / base, edge * 0.35)
    if ruts:
        for yr in rut_y:
            for side in (-1, 1):
                pts = []
                for t in np.linspace(0, 1, 30):
                    x = side * t * rut_x
                    y = yr + 0.04 * math.sin(t * 7 + seed) + (BP.fbm(np.float32(x), np.float32(0), scale=0.6, seed=seed + 5) - 0.5) * 0.1
                    pts.append((x, y))
                pts = np.array(pts)
                k = 0
                while k < len(pts) - 3:
                    L = rng.randint(4, 9)
                    seg = pts[k:k + L]
                    if len(seg) >= 3:
                        cv.strokes([dict(pts=seg, w=0.035, color=BP.c("#8C7254"), alpha=0.35, taper=(0.2, 0.2),
                                         dry=0.5, h=-0.006, seed=rng.randint(0, 9999))])
                    k += L + rng.randint(1, 4)
    if pebbles:
        pts = []
        for _ in range(240):
            x, y = rng.uniform(-4, 4), rng.uniform(-3.5, 3.5)
            if float(BP.hex_d(np.float32(x), np.float32(y))) > 0.2:
                pts.append((x, y))
        m = mask
        for (x, y) in pts:
            i = int((4 - y) * cv.ppm)
            j = int((x + 4) * cv.ppm)
            if 0 <= i < cv.size and 0 <= j < cv.size and m[i, j] > 0.6:
                cv.dots([(x, y)], rng.uniform(0.012, 0.028), BP.c("#8A7A66") if rng.random() < 0.6 else BP.c("#6E6458"),
                        0.65, h=0.004, squash=rng.uniform(0.5, 0.9), angle=rng.uniform(0, TAU))


class Road(Spec):
    """Packed-earth road along x (corner to corner, flaring at the corners so a row of road
    hexes joins), cart ruts, pebbles, grassy verges with tufts, a roadside stone."""

    def __init__(self):
        super().__init__("Road", 6606, n=32, props_px=1024)
        rng = self.rng
        self.tufts = []
        for p in scatter(rng, 30, d_min=0.35, min_sep=0.6):
            if abs(p[1]) > float(road_halfwidth(np.float32(p[0]))) + 0.35:
                self.tufts.append(p)
        self.tufts = self.tufts[:9]
        self.stone = (0.3, 1.45)

    def h(self, x, y):
        m = road_mask(np.asarray(x, np.float32), np.asarray(y, np.float32), self.seed)
        return micro_relief(x, y, self.seed, amp=0.04) * (1 - m) - 0.03 * m * BP.smooth(0.2, 0.9, BP.hex_d(x, y))

    def paint(self, cv):
        meadow(cv, self.rng, self.seed, layout=[(x, y, 0.12) for x, y in self.tufts], flowers=0.4)
        m = road_mask(cv.X, cv.Y, self.seed)
        paint_earth(cv, m, self.seed, self.rng)

    def props(self, mb):
        rng = self.rng
        for (x, y) in self.tufts:
            PR.grass_tuft(mb, rng, (x, y, 0.0), height=rng.uniform(0.24, 0.36), n=rng.randint(5, 7))
        PR.facet_rock(mb, rng, (self.stone[0], self.stone[1], 0.0), 0.3, "B_RockGrey", flat=0.9)


def ford_mask(X, Y, seed):
    d = BP.hex_d(X, Y)
    wob = (BP.fbm(X, Y, scale=1.6, octaves=2, seed=seed + 7) - 0.5) * 0.3 * BP.smooth(0.15, 0.7, d)
    hw = road_halfwidth(X, 0.95, 0.55) + wob
    return BP.smooth(hw + 0.25, hw - 0.25, np.abs(Y))


class Ford(Spec):
    """A shallow stony crossing in the river: water at the rim (joins the river), a gravel bar
    along x rising just above the water with flat stepping stones (tops at z ~0, where the
    plinth stands), wet gravel washes, reeds at the bar ends."""

    def __init__(self):
        super().__init__("Ford", 7707, n=40, water=WATER_Z, skirt="water", props_px=1024)
        rng = self.rng
        self.stones = []
        for i in range(9):
            x = -3.2 + 6.4 * i / 8 + rng.uniform(-0.12, 0.12)
            y = rng.uniform(-0.3, 0.3)
            self.stones.append((x, y, rng.uniform(0.32, 0.42)))
        self.reeds = [(-2.6, 1.3), (-2.9, -1.2), (2.7, 1.25), (2.5, -1.35)]

    def h(self, x, y):
        x = np.asarray(x, np.float32)
        y = np.asarray(y, np.float32)
        m = ford_mask(x, y, self.seed)
        bar = -0.16 + 0.04 * (BP.fbm(x, y, scale=2.0, octaves=2, seed=self.seed) - 0.5)
        return WATER_Z + (bar - WATER_Z) * m

    def paint(self, cv):
        X, Y = cv.X, cv.Y
        rng = self.rng
        m = ford_mask(X, Y, self.seed)
        water_paint(cv, rng, self.seed, keep_out=lambda x, y: abs(y) < float(road_halfwidth(np.float32(x), 0.95, 0.55)) + 0.5,
                    density=0.8)
        n = BP.fbm(X, Y, scale=1.1, octaves=3, seed=self.seed + 3)
        grav = BP.mix(BP.c("#C4B28E"), BP.c("#A8A08A"), BP.smooth(0.3, 0.7, n))
        wet = BP.smooth(0.35, 0.75, m)
        cv.wash(BP.mix(BP.c("#9DB0B4"), grav, wet), m)
        # pebbles
        for _ in range(900):
            x, y = rng.uniform(-4, 4), rng.uniform(-2.2, 2.2)
            i = int((4 - y) * cv.ppm)
            j = int((x + 4) * cv.ppm)
            if 0 <= i < cv.size and 0 <= j < cv.size and m[i, j] > 0.45 and float(BP.hex_d(np.float32(x), np.float32(y))) > 0.1:
                cv.dots([(x, y)], rng.uniform(0.012, 0.035), [BP.c("#8E8676"), BP.c("#B8AE98"), BP.c("#6E6A62")][rng.randint(0, 2)],
                        0.7, h=0.006, squash=rng.uniform(0.5, 0.9), angle=rng.uniform(0, TAU))
        # ripple lines where the water runs over the bar's edges
        for side in (-1, 1):
            for k in range(14):
                x = rng.uniform(-2.8, 2.8)
                y = side * (float(road_halfwidth(np.float32(x), 0.95, 0.55)) + rng.uniform(0.05, 0.3))
                if float(BP.hex_d(np.float32(x), np.float32(y))) < 0.4:
                    continue
                cv.strokes(BP.wave_line(rng, x - 0.3, y, 0.6, 0.02, 0.3, 0.0, 0.008, P["wave"], 0.4, crest=False))
        for (x, y, s) in self.stones:
            cv.dots([(x, y)], s * 0.62, BP.c("#7F8A86"), 0.35)        # wet halo round each stone

    def props(self, mb):
        rng = self.rng
        for (x, y, s) in self.stones:
            # flat-topped stepping stones: tops at about z = 0
            PR.facet_rock(mb, rng, (x, y, 0.02 - s * 0.55 * 0.62), s, "B_StoneFlat", flat=0.55, n=14, sink=0.0,
                          elong=(1.0, 1.25))
        for (x, y) in self.reeds:
            PR.reeds(mb, rng, (x, y, float(self.h(np.float32(x), np.float32(y)))), n=10, height=0.7)


class Bridge(Spec):
    """The river under a wooden arched beam bridge along x (corner to corner, landing on the
    banks): cambered plank deck, lacquered rails, trestle piers and arched struts."""

    def __init__(self):
        super().__init__("Bridge", 8808, n=16, water=WATER_Z, skirt="water", props_px=2048)

    def h(self, x, y):
        return np.full_like(np.asarray(x, np.float32), WATER_Z)

    def paint(self, cv):
        water_paint(cv, self.rng, self.seed, density=0.9)
        # the bridge's reflection-free shade: a soft deeper wash under the deck (painted, not light)
        X, Y = cv.X, cv.Y
        cv.glaze(P["water_d"] / P["water"], BP.smooth(1.7, 1.0, np.abs(Y)) * 0.5 * BP.smooth(0.3, 1.0, BP.hex_d(X, Y)))

    def props(self, mb):
        BA.timber_bridge(mb)
        rng = self.rng
        for (x, y) in ((-3.0, 1.0), (3.1, -0.95)):
            PR.reeds(mb, rng, (x, y, WATER_Z), n=8, height=0.6)


def wall_ground(cv, rng, seed, gate=False):
    """Meadow rim, a packed-earth strip along the wall foot on both sides; for the gate the road
    runs through along x."""
    X, Y = cv.X, cv.Y
    meadow(cv, rng, seed, flowers=0.3)
    d = BP.hex_d(X, Y)
    wob = (BP.fbm(X, Y, scale=1.2, octaves=2, seed=seed + 3) - 0.5) * 0.3
    strip = BP.smooth(2.35 + wob * BP.smooth(0.2, 0.8, d), 1.95, np.abs(X))
    paint_earth(cv, strip, seed, rng, ruts=False)
    if gate:
        m = road_mask(X, Y, seed, w0=0.95)
        paint_earth(cv, m, seed + 1, rng, ruts=True, rut_y=(-0.4, 0.4), rut_x=3.0)


class Wall(Spec):
    """City rampart along y (a column of Wall hexes reads as one wall): battered stone faces with
    ruled courses, a paved walk, a brick parapet with five merlons per hex row on the outer
    (-x) side and a low inner parapet; packed earth at its foot."""

    def __init__(self):
        super().__init__("Wall", 9909, n=32, props_px=2048)
        rng = self.rng
        self.tufts = [p for p in scatter(rng, 40, d_min=0.4, min_sep=0.7) if abs(p[0]) > 2.0][:8]

    def h(self, x, y):
        return micro_relief(x, y, self.seed, amp=0.03)

    def paint(self, cv):
        wall_ground(cv, self.rng, self.seed)

    def props(self, mb):
        BA.rampart(mb, -BA.HALF, BA.HALF, cap0=True, cap1=True)
        # a small cinnabar pennant on the inner parapet: along a wall column they fly every hex row
        BA.banner(mb, (1.12, 1.75, BA.WALL_H), height=1.7, cloth=(0.36, 0.62), seed=31, yaw=math.pi)
        rng = self.rng
        for (x, y) in self.tufts:
            PR.grass_tuft(mb, rng, (x, y, 0.0), height=rng.uniform(0.24, 0.34), n=rng.randint(5, 7))
        PR.facet_rock(mb, rng, (-2.25, 1.6, 0.0), 0.3, "B_RockGrey", flat=0.8)


class Gate(Spec):
    """The rampart with a fortified gate: a stone gate block with an arched tunnel along x,
    studded cinnabar doors facing out (-x), a crenellated front, a gate-tower pavilion (red
    columns, lattice, painted beams, brackets, a grey-tiled hip-gable roof); the road runs
    through."""

    def __init__(self):
        super().__init__("Gate", 1010, n=32, props_px=2048)

    def h(self, x, y):
        return micro_relief(x, y, self.seed, amp=0.03)

    def paint(self, cv):
        wall_ground(cv, self.rng, self.seed, gate=True)

    def props(self, mb):
        self.top = BA.gate(mb, tower=True)
        for sy in (-1, 1):
            BA.banner(mb, (1.15, sy * 2.55, BA.WALL_H), height=2.0, cloth=(0.4, 0.72), seed=40 + sy, yaw=math.pi)


class Rubble(Spec):
    """The broken gate: rampart stubs at both ends with ragged broken tops, and in the breach a
    low heap of stone blocks, split beams, a fallen studded door leaf and scattered roof tiles
    (low in the centre, where the plinth stands)."""

    def __init__(self):
        super().__init__("Rubble", 1111, n=40, props_px=2048)

    def h(self, x, y):
        x = np.asarray(x, np.float32)
        y = np.asarray(y, np.float32)
        heap = 0.0
        for (cx, cy, hh, rr) in ((0.0, 1.9, 0.75, 1.5), (0.0, -1.9, 0.7, 1.5), (0.3, 0.0, 0.18, 1.6)):
            heap = heap + bump(x, y, cx, cy, hh, rr, 1.5)
        n = BP.fbm(x, y, scale=2.0, octaves=3, seed=self.seed)
        return (heap * (0.8 + 0.4 * n)) * BP.smooth(0.3, 1.3, BP.hex_d(x, y))

    def paint(self, cv):
        X, Y = cv.X, cv.Y
        rng = self.rng
        wall_ground(cv, rng, self.seed, gate=True)
        H = self.h(X, Y)
        n = BP.fbm(X, Y, scale=1.5, octaves=3, seed=self.seed + 2)
        deb = BP.mix(BP.c("#B9AE9A"), BP.c("#9C8E78"), BP.smooth(0.3, 0.7, n))
        cv.wash(deb, BP.smooth(0.03, 0.2, H))
        for _ in range(500):
            x, y = rng.uniform(-2.2, 2.2), rng.uniform(-3.2, 3.2)
            z = float(self.h(np.float32(x), np.float32(y)))
            if z > 0.05:
                cv.dots([(x, y)], rng.uniform(0.02, 0.06), [BP.c("#7E786C"), BP.c("#A49A88"), BP.c("#5E5A54")][rng.randint(0, 2)],
                        0.75, h=0.01, squash=rng.uniform(0.4, 0.9), angle=rng.uniform(0, TAU))

    def props(self, mb):
        rng = self.rng
        BA.rampart(mb, -BA.HALF, -2.15, cap0=True, cap1=True, broken=(-0.6, 0.35, 3))
        BA.rampart(mb, 2.15, BA.HALF, cap0=True, cap1=True, broken=(-0.6, 0.35, 4))
        # stone blocks
        for _ in range(26):
            y = rng.choice([-1, 1]) * rng.uniform(0.7, 2.4)
            x = rng.uniform(-1.4, 1.4)
            z = float(self.h(np.float32(x), np.float32(y)))
            PR.facet_rock(mb, rng, (x, y, z), rng.uniform(0.18, 0.36), "W_Stone", flat=0.7, n=10, sink=0.3)
        for _ in range(10):
            x, y = rng.uniform(-1.6, 1.6), rng.uniform(-0.8, 0.8)
            PR.facet_rock(mb, rng, (x, y, 0.0), rng.uniform(0.1, 0.18), "B_RockGrey", flat=0.6, n=9, sink=0.3)
        # split beams
        for k in range(4):
            a = rng.uniform(0, math.pi)
            c = Vector((rng.uniform(-1.2, 1.2), rng.choice([-1, 1]) * rng.uniform(0.6, 1.6), 0.0))
            c.z = float(self.h(np.float32(c.x), np.float32(c.y))) + 0.05
            L = rng.uniform(1.2, 2.0)
            d = Vector((math.cos(a), math.sin(a), rng.uniform(-0.15, 0.25)))
            mb.cylinder(tuple(c - d * L / 2), tuple(c + d * L / 2), 0.08, 0.07, "W_WoodDark", 6)
        # a fallen door leaf, askew
        s0 = mb.n
        mb.box((0, 0, 0), (1.5, 0.12, 1.1), "W_GateDoor")
        mb.transform(s0, Matrix.Translation(Vector((-0.6, 0.9, 0.12))) @ Matrix.Rotation(0.5, 4, "Z") @
                     Matrix.Rotation(-1.35, 4, "X"))
        # scattered roof tiles
        for _ in range(16):
            x, y = rng.uniform(-1.5, 1.5), rng.uniform(-2.5, 2.5)
            z = float(self.h(np.float32(x), np.float32(y)))
            s0 = mb.n
            mb.box((0, 0, 0), (0.22, 0.14, 0.04), "W_TileDark")
            mb.transform(s0, Matrix.Translation(Vector((x, y, z))) @ Matrix.Rotation(rng.uniform(0, TAU), 4, "Z") @
                         Matrix.Rotation(rng.uniform(-0.5, 0.5), 4, "X"))


def town_streets(X, Y, seed, w=0.62, square=1.15):
    """Street mask: lanes from the centre to the six edge midpoints and a central square;
    12-fold symmetric edges (folded noise), so town hexes join in every direction."""
    r = np.hypot(X, Y)
    a = np.mod(np.arctan2(Y, X), math.pi / 3)
    a = np.minimum(a, math.pi / 3 - a)                    # 0 at the corner direction, 30 deg at a midpoint
    lane_d = r * np.sin(math.pi / 6 - a)                  # distance from the lane axis (midpoint direction)
    fx, fy = r * np.cos(a), r * np.sin(a)
    wob = (BP.fbm(fx, fy, scale=1.4, octaves=2, seed=seed + 9) - 0.5) * 0.16
    lane = BP.smooth(w + 0.1 + wob, w - 0.1 + wob, lane_d)
    sq = BP.smooth(square + 0.15 + wob, square - 0.15 + wob, r)
    return np.maximum(lane, sq)


class Town(Spec):
    """Streets from a little square to the six edge midpoints (town hexes join in any
    direction).  Courtyard houses (plaster and grey brick, grey-blue tiled gable roofs) stand at
    the corners 0, 2, 4 and garden trees at 1, 3, 5: around the lattice vertices of a town the
    three hexes' corners make alternately a block of three houses and a little grove."""

    def __init__(self):
        super().__init__("Town", 1212, n=32, props_px=2048)
        rng = self.rng
        self.houses = []
        for k in (0, 2, 4):
            a = math.radians(60 * k + rng.uniform(-4, 4))
            r = 2.95
            x, y = r * math.cos(a), r * math.sin(a)
            yaw = a + math.pi / 2 + rng.uniform(-0.1, 0.1)       # long side tangential, front to the centre
            self.houses.append((x, y, yaw, k))
        self.trees = []
        for k in (1, 3, 5):
            a = math.radians(60 * k + rng.uniform(-8, 8))
            r = rng.uniform(2.9, 3.15)
            self.trees.append((r * math.cos(a), r * math.sin(a), "broadA" if k != 3 else "broadC",
                               rng.uniform(0, TAU), rng.uniform(0.62, 0.72)))

    def h(self, x, y):
        return micro_relief(x, y, self.seed, amp=0.02)

    def paint(self, cv):
        X, Y = cv.X, cv.Y
        rng = self.rng
        meadow(cv, rng, self.seed, marks=0.4, flowers=0.2, rim=BP.c("#CDBF98"),
               base=BP.mix(BP.c("#CDBF98"), BP.c("#B9C095"), BP.smooth(0.4, 0.7, BP.fbm(X, Y, scale=0.6, seed=self.seed))))
        st = town_streets(X, Y, self.seed)
        paint_earth(cv, st, self.seed, rng, ruts=False, color=BP.c("#D4BE94"))
        for (x, y, yaw, k) in self.houses:
            m = BP.smooth(1.3, 1.1, np.hypot(X - x, Y - y)) * (1 - st)
            cv.wash(BP.c("#CFC7B2"), m * 0.8)
        for (x, y, *_r) in self.trees:
            m = BP.smooth(1.2, 0.8, np.hypot(X - x, Y - y)) * (1 - st)
            cv.wash(BP.c("#AFBF8E"), m * 0.7)
            moss_cluster(cv, rng, x, y, 10, 0.3)

    def props(self, mb):
        rng = self.rng
        walls = [("W_Brick", "W_Plaster"), ("W_BrickWarm", "W_PlasterWarm"), ("W_Brick", "W_PlasterWarm")]
        for i, (x, y, yaw, k) in enumerate(self.houses):
            wl, up = walls[i % 3]
            BA.house(mb, (x, y, 0.0), yaw, w=rng.uniform(1.7, 1.9), d=rng.uniform(1.15, 1.3), h=rng.uniform(0.95, 1.1),
                     wall=wl, upper=up, roof="W_Tile" if i % 2 else "W_TileDark", seed=k)
        # well in the square
        mb.cylinder((0.85, 0.5, -0.1), (0.85, 0.5, 0.38), 0.3, 0.28, "W_Stone", 12)
        mb.cylinder((0.85, 0.5, 0.38), (0.85, 0.5, 0.42), 0.22, 0.22, "B_Dark", 12)
        for sx in (-1, 1):
            mb.box((0.85 + sx * 0.28, 0.5, 0.38), (0.05, 0.05, 0.55), "W_WoodDark")
        mb.box((0.85, 0.5, 0.93), (0.62, 0.05, 0.05), "W_WoodDark")
        for (x, y, *_r) in self.trees:
            PR.shrub(mb, rng, (x + 0.45, y - 0.2, 0.0), size=0.32, canopy="B_Canopy")

    def prototypes(self):
        used = {k for _x, _y, k, *_r in self.trees}
        return {k: TREE_PROTOS[k] for k in used}

    def placements(self):
        return [(k, place(x, y, 0.0, yaw, s)) for (x, y, k, yaw, s) in self.trees]


class Castle(Spec):
    """The commander's keep: a paved courtyard (where the commander's unit stands) closed by a
    low red compound wall with openings at the street ends, the commander's double-eaved hall
    on a marble terrace at the back (+y), two great cinnabar war banners flanking the court,
    stone lanterns."""

    def __init__(self):
        super().__init__("Castle", 1313, n=32, props_px=2048)

    def h(self, x, y):
        return np.zeros_like(np.asarray(x, np.float32))

    def paint(self, cv):
        X, Y = cv.X, cv.Y
        rng = self.rng
        d = BP.hex_d(X, Y)
        meadow(cv, rng, self.seed, marks=0.0, rim=BP.c("#D4BE94"), base=BP.c("#D4BE94"))
        st = town_streets(X, Y, self.seed)
        paint_earth(cv, BP.smooth(0.55, 0.35, d) + 0 * st, self.seed, rng, ruts=False, color=BP.c("#D4BE94"))
        # flagstone court inside the compound wall
        court = BP.smooth(0.42, 0.62, d)
        n = BP.fbm(X, Y, scale=1.3, octaves=2, seed=self.seed)
        cv.wash(BP.mix(BP.c("#DDD6C4"), BP.c("#CBC2AC"), BP.smooth(0.3, 0.7, n)), court)
        g = 0.62
        u = np.mod(X / g, 1.0)
        v = np.mod((Y + 0.5 * g * np.floor(X / g)) / g, 1.0)
        joint = np.maximum(BP.smooth(0.03, 0.0, np.minimum(u, 1 - u)), BP.smooth(0.03, 0.0, np.minimum(v, 1 - v)))
        cv.glaze(BP.c("#8C8474") / BP.c("#D6CEBA"), joint * court * 0.55)
        cv.h += -0.004 * joint * court
        # imperial way: a central band of larger slabs toward the hall
        way = BP.smooth(0.62, 0.5, np.abs(X)) * BP.smooth(-3.0, -2.6, Y) * BP.smooth(2.2, 1.8, Y)
        cv.wash(BP.c("#E6E0D0"), way * 0.85)

    def props(self, mb):
        BA.command_hall(mb, at=(0.0, 2.25, 0.0))
        # compound wall along the five non-back edges (inset), open at the edge midpoints
        inset = 0.38
        apo = BP.APO - inset
        corners = []
        for k in range(6):
            a = math.radians(60 * k)
            r = apo / math.cos(math.radians(30))
            corners.append((r * math.cos(a), r * math.sin(a)))
        gap = 0.75
        for k in range(6):
            p0, p1 = corners[k], corners[(k + 1) % 6]
            mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
            if k == 1:          # the back edge (+y): the hall closes it
                continue
            for (a, b) in ((p0, mid), (mid, p1)):
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
                if b is mid:
                    b = (b[0] - ux * gap, b[1] - uy * gap)
                else:
                    a = (a[0] + ux * gap, a[1] + uy * gap)
                BA.compound_wall(mb, a, b)
        for sx in (-1, 1):
            BA.banner(mb, (sx * 2.35, 0.15, 0.0), height=4.6, cloth=(0.78, 1.65), seed=7 + sx, yaw=0.0 if sx < 0 else math.pi)
            # stone lantern
            x, y = sx * 1.25, 0.9
            mb.cylinder((x, y, 0.0), (x, y, 0.5), 0.07, 0.06, "W_Marble", 8)
            mb.box((x, y, 0.5), (0.26, 0.26, 0.22), "W_Marble")
            mb.cylinder((x, y, 0.72), (x, y, 0.86), 0.2, 0.0, "W_TileDark", 8)


TERRAIN_SPECS = {"Plain": Plain, "Forest": Forest, "Hill": Hill, "Mountain": Mountain, "Water": Water, "Ford": Ford,
                 "Bridge": Bridge, "Road": Road, "Wall": Wall, "Gate": Gate, "Town": Town, "Castle": Castle,
                 "Rubble": Rubble}


def spec(name):
    return TERRAIN_SPECS[name]()
