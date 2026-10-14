"""Headgear: helmet with visor, phoenix wings, plume and lamellar neck guard (兜鍪/凤翅盔/顿项),
scholar's caps (东坡巾 / 方巾), small topknot crown with hairpin (小冠/簪).

All built in head space (head units) and projected with the head, so they turn with it.
"""

import math

import numpy as np

import geom2d as g
import palette as pal
from hair import Shell, _segments_visible


def _lin_cols(a, b, n):
    return [pal.hexs(pal.mix(a, b, t)) for t in np.linspace(0, 1, n)]


def _inward(P, poly):
    c = poly.mean(0)
    m = len(P) // 2
    nrm = g.normals(g.resample(P, 9))[4]
    return 1 if np.dot(c - P[m], nrm) > 0 else -1


# ------------------------------------------------------------------------------------------
class Helmet:
    def __init__(self, fd, metal="iron", trim="gold", plume="cinnabar", rim_front=0.300,
                 rim_back=0.40, height=0.37, width=1.0, wings=False, guard="lamellar",
                 guard_color=None, seed=0):
        self.fd = fd
        self.H = fd.H
        self.s = fd.H.s
        self.metal = metal
        self.trim = trim
        self.plume_col = plume
        self.rf = rim_front
        self.rb = rim_back
        self.wings = wings
        self.guard = guard
        self.guard_color = guard_color or metal
        self.rng = np.random.default_rng(seed + 77)
        w = self.H.sh["width"] * width
        self.shell = Shell(self.H, (0.0, 0.33, -0.03), (0.352 * w, height, 0.50))

    def rim_lat(self, lon):
        y = self.rf + (self.rb - self.rf) * (1 - np.cos(np.asarray(lon))) / 2
        return np.arcsin(np.clip((self.shell.c[1] - y) / self.shell.r[1], -1, 1))

    def rim(self, lon, dr=0.0):
        return self.shell.P(lon, self.rim_lat(lon), dr)

    def bowl_poly(self):
        sh = self.shell
        lon = np.linspace(-math.pi, math.pi, 361)
        f = sh.facing(lon, self.rim_lat(lon))
        vis = f > 0
        idx = np.where(vis)[0]
        lon_v = lon[idx[0]:idx[-1] + 1]
        front = self.rim(lon_v)
        O = sh.outline(0.0, n=120, keep=lambda x, y, z: y <= self.rf + (self.rb - self.rf) * 0.5 + 0.0 * x)
        i0 = int(np.argmin(np.linalg.norm(O - front[-1], axis=1)))
        i1 = int(np.argmin(np.linalg.norm(O - front[0], axis=1)))

        def walk(a, b, step):
            out = [a]
            i = a
            while i != b:
                i = (i + step) % len(O)
                out.append(i)
            return O[out]
        w1 = walk(i0, i1, 1)
        w2 = walk(i0, i1, -1)
        arc = w1 if w1[:, 1].min() < w2[:, 1].min() else w2
        return np.vstack([front, arc]), front, lon_v

    # -- neck guard (顿项): lamellar flaps from the rim to the shoulders ---------------------
    def neck_guard(self, cv, part="back", y_bot=1.06, flare=0.42):
        """顿项: lamellar flaps from the rim to the shoulders.  part='back' draws both flaps
        whole (call before the face: they hang behind the head); part='front' redraws the near
        flap's front piece over the ear and temple (call after the face)."""
        H, s, fd = self.H, self.s, self.fd
        far = fd.far
        sh = self.shell
        col = self.guard_color
        if part == "back":
            flaps = ((-far, 1.0, 3.0), (far, 1.3, 3.0))
        else:
            flaps = ((-far, 1.0, 1.75),)
        for side, lon0, lon1 in flaps:
            lons = np.linspace(lon0, lon1, 30) * side
            top = sh.P(lons, self.rim_lat(lons), 0.01)
            bx = []
            for lo in lons:
                x, y, z = sh.xyz(lo, self.rim_lat(lo), 0.01)
                k = (abs(lo) - 1.0) / 2.0
                xo = x * (1 + flare * (0.5 + 0.5 * k)) + side * 0.02
                zo = z * (1 + flare * 0.2)
                bx.append((xo, y_bot - 0.05 * k, zo))
            bot = H.Pz(bx)
            self._lamellar_band(cv, top, bot, rows=7, cols=int(9 * (lon1 - lon0)), color=col)
        return True

    def _lamellar_band(self, cv, top, bot, rows=6, cols=10, color="iron"):
        s = self.s
        poly = np.vstack([top, bot[::-1]])
        cv.fill(poly, color, 1.0, "paint")
        lamellar(cv, top, bot, rows, cols, color, s, lace="cinnabar", rng=self.rng)
        # gilded lower hem and soft modelling
        hem = top + (bot - top) * 0.94
        cv.band(hem, bot, self.trim, 1.0, mode="paint", rows=1)
        cv.edge(bot, s * 0.10, "ink", 0.25, side=_inward(bot, poly), rows=4)
        cv.stroke(np.vstack([poly, poly[:1]]), s * 0.005, "ink", 0.9, prof="iron", caps=False)

    # -- bowl -------------------------------------------------------------------------------
    def bowl(self, cv):
        H, s, fd = self.H, self.s, self.fd
        sh = self.shell
        far = fd.far
        poly, front, lon_v = self.bowl_poly()
        metal = self.metal
        cv.fill(poly, metal, 1.0, "paint")
        # modelling: light from the upper left, dark on the right and at the rim
        cen = poly.mean(0)
        hl_c = sh.P(-0.55, 0.55)
        cv.blob(hl_c, s * 0.16, s * 0.10, "white", 0.35, rot=-0.5, mode="paint")
        cv.blob(sh.P(-0.4, 0.75), s * 0.05, s * 0.03, "white", 0.5, rot=-0.3, mode="paint")
        cv.edge(poly[len(front):], s * 0.07, "ink", 0.45, side=_inward(poly[len(front):], poly), rows=6)
        cv.edge(front, s * 0.05, "ink", 0.35, side=_inward(front, poly), rows=4)
        # ridges (盔梁): gold bands from rim to crown
        for lo in (-1.0, -0.5, 0.0, 0.5, 1.0):
            lat = np.linspace(float(self.rim_lat(lo)), 1.45, 30)
            lon_l = np.full_like(lat, lo - 0.035)
            lon_r = np.full_like(lat, lo + 0.035)
            vis = sh.facing(np.full_like(lat, lo), lat) > 0.05
            if vis.sum() < 4:
                continue
            A_ = sh.P(lon_l[vis], lat[vis], 0.004)
            B_ = sh.P(lon_r[vis], lat[vis], 0.004)
            wmul = 1.0 if lo == 0 else 0.8
            cv.band(A_, B_, self.trim, 1.0, mode="paint", rows=2)
            cv.band(A_, B_, "gold_d", lambda S, T: 0.6 * T ** 2, rows=3)
            cv.stroke(A_, s * 0.0035, "ink", 0.8, prof="iron")
            cv.stroke(B_, s * 0.0035, "ink", 0.8, prof="iron")
            # rivets
            for k in range(2, len(A_) - 2, 4):
                c = (A_[k] + B_[k]) / 2
                cv.dot(c, s * 0.0045, "gold_d", 0.9)
                cv.dot(c - s * 0.0012, s * 0.002, "gold_l", 0.9)
        cv.stroke(np.vstack([poly, poly[:1]]), s * 0.0065, "ink", 0.95, prof="iron", caps=False)
        self.poly = poly
        self.front = front

    def visor(self, cv):
        """眉庇: projecting brim over the brows, gilded edge, with a central flame plaque."""
        H, s, fd = self.H, self.s, self.fd
        sh = self.shell
        far = fd.far
        lon = np.linspace(-1.25, 1.25, 60)
        lat = self.rim_lat(lon)
        inner = sh.P(lon, lat, 0.0)
        # outer edge: pushed forward and slightly down, deepest at the front
        out3 = []
        for lo, la in zip(lon, lat):
            x, y, z = sh.xyz(lo, la, 0.0)
            k = math.cos(lo) ** 2
            out3.append((x * 1.05, y + 0.030 + 0.020 * k, z + 0.075 * k + 0.01))
        outer = H.Pz(out3)
        vis = sh.facing(lon, lat) > -0.25
        inner, outer = inner[vis], outer[vis]
        cv.band(inner, outer, self.metal, 1.0, mode="paint", rows=2)
        cv.band(inner, outer, "ink", lambda S, T: 0.25 + 0.35 * T, rows=3)
        # gilded edge
        edge_in = inner + (outer - inner) * 0.72
        cv.band(edge_in, outer, self.trim, 1.0, mode="paint", rows=2)
        cv.stroke(outer, s * 0.006, "ink", 0.95, prof="iron")
        cv.stroke(inner, s * 0.004, "ink", 0.8, prof="iron")
        cv.stroke(edge_in, s * 0.003, "gold_d", 0.9, prof="iron")
        # shadow cast-free: the brow area under the visor darkens softly
        brow = H.P([(x, 0.355) for x in np.linspace(-0.26, 0.26, 20)])
        top = H.P([(x, self.rf + 0.03) for x in np.linspace(-0.26, 0.26, 20)])
        cv.band(top, brow, "ochre", lambda S, T: 0.30 * (1 - T) ** 1.5 * np.sin(np.pi * S) ** 0.5, rows=5)
        # front plaque (flame / cloud scroll in gold)
        c = sh.P(0.0, float(self.rim_lat(0.0)) + 0.28, 0.01)
        hw = s * 0.045
        hh = s * 0.075
        flame = np.array([c + [0, -hh], c + [hw * 0.55, -hh * 0.35], c + [hw, hh * 0.15],
                          c + [hw * 0.45, hh * 0.55], c + [0, hh * 0.35], c + [-hw * 0.45, hh * 0.55],
                          c + [-hw, hh * 0.15], c + [-hw * 0.55, -hh * 0.35]])
        F = g.catmull(flame, 6, closed=True)
        cv.fill(F, self.trim, 1.0, "paint")
        cv.blob(c + [-hw * 0.2, -hh * 0.1], hw * 0.5, hh * 0.4, "gold_l", 0.6, mode="paint")
        cv.stroke(np.vstack([F, F[:1]]), s * 0.004, "ink", 0.9, prof="iron", caps=False)
        cv.dot(c + [0, hh * 0.05], s * 0.016, "cinnabar", 1.0)
        cv.dot(c + [-s * 0.004, hh * 0.0], s * 0.006, "cinnabar_l", 0.9)

    def phoenix_wings(self, cv):
        """凤翅: upswept gilded wings on both sides of the bowl."""
        H, s, fd = self.H, self.s, self.fd
        sh = self.shell
        for side in (-1, 1):
            base = sh.P(side * 1.3, 0.25, 0.0)
            x, y, z = sh.xyz(side * 1.3, 0.25, 0.0)
            pts3 = [(x, y + 0.02, z), (x + side * 0.12, y - 0.06, z - 0.05),
                    (x + side * 0.22, y - 0.22, z - 0.10), (x + side * 0.20, y - 0.30, z - 0.11),
                    (x + side * 0.13, y - 0.16, z - 0.07), (x + side * 0.03, y - 0.10, z - 0.03)]
            W = g.catmull(H.Pz(pts3), 8, closed=True)
            cv.fill(W, self.trim, 1.0, "paint")
            # feather lines
            for k in range(5):
                t = 0.2 + 0.15 * k
                a = H.Pz([(x + side * 0.03, y - 0.02, z)])[0]
                b = H.Pz([(x + side * (0.08 + 0.12 * t), y - 0.08 - 0.18 * t, z - 0.06)])[0]
                cv.stroke(np.array([a, (a + b) / 2, b]), s * 0.003, "gold_d", 0.8, prof="orchid")
            cv.edge(W, s * 0.03, "gold_d", 0.5, side=_inward(W, W), rows=3, closed=True)
            cv.stroke(np.vstack([W, W[:1]]), s * 0.005, "ink", 0.9, prof="iron", caps=False)

    def plume(self, cv):
        """盔枪 spike with a red horsehair tassel (红缨)."""
        H, s = self.H, self.s
        sh = self.shell
        top = sh.P(0.0, math.pi / 2 - 0.02, 0.0)
        x, y, z = sh.xyz(0.0, math.pi / 2, 0.0)
        # spike stem + bead
        tip = H.Pz([(x, y - 0.30, z)])[0]
        base = H.Pz([(x, y - 0.02, z)])[0]
        # tassel mass hanging from a ring at y-0.12
        ring = H.Pz([(x, y - 0.13, z)])[0]
        rng = self.rng
        col = self.plume_col
        dark = pal.hexs(pal.mix(col, "ink", 0.45))
        light = pal.hexs(pal.mix(col, "white", 0.25))
        mass = []
        for a in np.linspace(0, 2 * math.pi, 24, endpoint=False):
            r = s * (0.11 + 0.015 * math.sin(3 * a))
            mass.append(ring + np.array([math.cos(a) * r * 1.1, abs(math.sin(a)) * r * 0.75 + s * 0.02]))
        mass = np.array(mass)
        hull = g.catmull(np.vstack([ring + [-s * 0.035, -s * 0.015], ring + [s * 0.035, -s * 0.015],
                                    ring + [s * 0.14, s * 0.06], ring + [s * 0.13, s * 0.13],
                                    ring + [0, s * 0.15], ring + [-s * 0.13, s * 0.13],
                                    ring + [-s * 0.14, s * 0.06]]), 8, closed=True)
        cv.stroke(np.array([base, tip]), s * 0.012, "gold_d", 1.0, prof="flat")
        cv.fill(hull, col, 0.95, "paint")
        cv.edge(hull, s * 0.035, dark, 0.6, side=_inward(hull, hull), rows=4, closed=True)
        for i in range(220):
            a = rng.uniform(-1.1, 1.1) * math.pi / 2
            ln = s * rng.uniform(0.09, 0.17)
            p0 = ring + np.array([rng.normal(0, s * 0.01), rng.uniform(-s * 0.01, s * 0.01)])
            d = np.array([math.sin(a) * 1.15, 0.55 + 0.6 * math.cos(a)])
            d = d / np.linalg.norm(d)
            p1 = p0 + d * ln * 0.5 + np.array([0, -s * 0.01])
            p2 = p0 + d * ln + np.array([0, s * 0.02])
            c = [dark, col, light][rng.choice(3, p=[0.35, 0.4, 0.25])]
            cv.stroke(g.catmull([p0, p1, p2], 5), s * 0.004, c, rng.uniform(0.6, 0.95), prof="hair")
        # bead and top
        cv.dot(H.Pz([(x, y - 0.14, z)])[0], s * 0.02, "gold", 1.0)
        cv.dot(H.Pz([(x, y - 0.14, z)])[0] - s * 0.006, s * 0.007, "gold_l", 1.0)
        cv.dot(tip, s * 0.012, "gold", 1.0)
        cv.stroke(np.array([H.Pz([(x, y - 0.16, z)])[0], tip]), s * 0.008, "gold", 1.0, prof="flat")


def lamellar(cv, top, bot, rows, cols, color, s, lace="cinnabar", rng=None, row_light=0.22,
             line="ink"):
    """Rows of small plates (札甲) between curves top and bot: each row lit at its upper edge,
    shaded at the lower, staggered plate seams, red lacing at the joints."""
    rng = rng or np.random.default_rng(0)
    n = max(len(top), len(bot), 30)
    T = g.resample(top, n)
    B = g.resample(bot, n)
    for r in range(rows):
        t0, t1 = r / rows, (r + 1) / rows
        A_ = T + (B - T) * t0
        B_ = T + (B - T) * t1
        cv.band(A_, B_, "white", lambda S, Tt: row_light * (1 - Tt) ** 2, mode="paint", rows=3)
        cv.band(A_, B_, "ink", lambda S, Tt: 0.40 * Tt ** 2, rows=3)
        cv.stroke(B_, s * 0.0035, line, 0.85, prof="iron", caps=False)
        off = 0.5 * (r % 2)
        L = g.length(A_)
        k = max(3, int(cols))
        for c in range(k + 1):
            u = (c + off) / k
            if u <= 0.01 or u >= 0.99:
                continue
            p = g.at(A_, u)
            q = g.at(B_, u)
            cv.stroke(np.array([p + (q - p) * 0.05, q]), s * 0.0028, line, 0.75, prof="iron")
            if lace and (c + r) % 2 == 0:
                m = p + (q - p) * 0.72
                cv.stroke(np.array([m - (q - p) * 0.08, m + (q - p) * 0.08]), s * 0.0045, lace,
                          0.85, prof="flat")


# ------------------------------------------------------------------------------------------
class ScholarCap:
    """东坡巾: black gauze; a tall square inner cap and a lower square outer wall whose front
    is parted in a V; two ribbons hang behind."""

    def __init__(self, fd, color="#1d1916", rim_front=0.255, rim_back=0.34, top=-0.11,
                 outer_top=0.04, width=0.98, ribbons=True):
        self.fd = fd
        self.H = fd.H
        self.s = fd.H.s
        self.color = color
        self.rf, self.rb = rim_front, rim_back
        self.top = top
        self.otop = outer_top
        self.w = width
        self.ribbons = ribbons

    def _section(self, lon, dr, shrink=1.0):
        H = self.H
        a = (0.318 * H.sh["width"] * self.w + dr) * shrink
        d = 0.44 * shrink + dr
        k = 3.4
        sl, cl = np.sin(lon), np.cos(lon)
        x = a * np.sign(sl) * np.abs(sl) ** (2 / k)
        z = -0.03 + d * np.sign(cl) * np.abs(cl) ** (2 / k)
        return x, z

    def _rim_y(self, lon):
        return self.rf + (self.rb - self.rf) * (1 - np.cos(lon)) / 2

    def _wall(self, cv, dr, ytop_fn, taper=1.0, notch=0.0):
        H, s = self.H, self.s
        lon = np.linspace(-math.pi, math.pi, 241)
        x, z = self._section(lon, dr)
        X = x * math.cos(H.yaw) + z * math.sin(H.yaw)
        i_min, i_max = int(np.argmin(X)), int(np.argmax(X))
        if i_min < i_max:
            idx = np.arange(i_min, i_max + 1)
        else:
            idx = np.concatenate([np.arange(i_min, len(lon)), np.arange(0, i_max + 1)])
        lv = lon[idx]
        xb, zb = x[idx], z[idx]
        xt, zt = self._section(lv, dr, taper)
        yt = ytop_fn(lv)
        if notch:
            yt = yt + notch * np.exp(-(lv / 0.22) ** 2)
        bottom = H.proj(xb, self._rim_y(lv), zb)
        topl = H.proj(xt, yt, zt)
        poly = np.vstack([bottom, topl[::-1]])
        cv.fill(poly, self.color, 0.95, "paint")
        # gauze: fine diagonal threads catching the light
        n = 26
        for k in range(n):
            u0 = k / n
            p = g.at(bottom, u0)
            q = g.at(topl, min(1.0, u0 + 0.06))
            cv.stroke(np.array([p, q]), s * 0.0018, "#6d655e", 0.25, prof="flat", caps=False)
        # corner edges where the square section turns
        for lc in (-math.pi / 4, math.pi / 4):
            xc, zc = self._section(np.array([lc]), dr)
            Xc = xc * math.cos(H.yaw) + zc * math.sin(H.yaw)
            if X[idx].min() + 1e-3 < Xc[0] < X[idx].max() - 1e-3:
                xct, zct = self._section(np.array([lc]), dr, taper)
                p0 = H.proj(xc, self._rim_y(np.array([lc])), zc)[0]
                p1 = H.proj(xct, ytop_fn(np.array([lc])) + (notch * math.exp(-(lc / 0.22) ** 2) if notch else 0), zct)[0]
                cv.stroke(np.array([p0, p1]), s * 0.004, "#8a8279", 0.55, prof="iron")
        # light from the left: a soft sheen on the left part; dark at the rim
        cv.band(bottom, topl, "white", lambda S, T: 0.10 * (1 - S) ** 2 * np.sin(np.pi * T),
                mode="paint", rows=3)
        cv.edge(bottom, s * 0.03, "ink", 0.35, side=_inward(bottom, poly), rows=3)
        cv.stroke(topl, s * 0.004, "#7d756c", 0.6, prof="iron")
        cv.stroke(np.vstack([poly, poly[:1]]), s * 0.005, "ink", 0.95, prof="iron", caps=False)
        return poly, bottom, topl

    def draw(self, cv):
        H, s = self.H, self.s
        far = self.fd.far
        if self.ribbons:
            for k in range(2):
                p0 = H.Pz([(-far * 0.29, self.rb - 0.03, -0.30 - 0.06 * k)])[0]
                pts = [p0, p0 + np.array([-far * s * (0.03 + 0.01 * k), s * 0.20]),
                       p0 + np.array([-far * s * 0.02, s * 0.40]),
                       p0 + np.array([-far * s * (0.06 + 0.03 * k), s * (0.58 + 0.05 * k)])]
                C = g.catmull(pts, 10)
                cv.stroke(C, s * 0.030, self.color, 0.96, prof="tail", taper=(0.02, 0.9), noise=0.04)
        inner, ib, it = self._wall(cv, 0.0, lambda lv: np.full_like(lv, self.top), taper=0.94)
        outer, ob, ot = self._wall(cv, 0.035, lambda lv: np.full_like(lv, self.otop), notch=0.07)
        self.poly = np.vstack([inner, outer])
        self.rim = ob


# ------------------------------------------------------------------------------------------
def small_crown(cv, fd, bun_shell, color="gold", pin="gold"):
    """小冠 over the topknot with a hairpin (簪) through it."""
    H, s = fd.H, fd.H.s
    c = bun_shell.c
    cr = Shell(H, (c[0], c[1] + 0.01, c[2]), bun_shell.r * np.array([1.12, 1.05, 1.12]))
    O = cr.outline(0.0, n=48, keep=lambda x, y, z: y < c[1] + 0.035)
    cv.fill(O, color, 1.0, "paint")
    cv.edge(O, s * 0.02, "ink", 0.35, side=_inward(O, O), rows=3, closed=True)
    cv.stroke(np.vstack([O, O[:1]]), s * 0.004, "ink", 0.9, prof="iron", caps=False)
    a = H.Pz([(c[0] - 0.16, c[1] - 0.01, c[2] + 0.03)])[0]
    b = H.Pz([(c[0] + 0.16, c[1] - 0.025, c[2] - 0.02)])[0]
    cv.stroke(np.array([a, b]), s * 0.009, pin, 1.0, prof="flat")
    cv.stroke(np.array([a, b]) + [0, -s * 0.003], s * 0.003, "gold_l", 0.9, prof="flat")
    cv.dot(a, s * 0.010, pin, 1.0)


def headband(cv, fd, color="cinnabar", y=0.255, width=0.05, tails=True):
    """抹额: a cloth band round the forehead, knotted behind with two short tails."""
    H, s = fd.H, fd.H.s
    far = fd.far
    lon = np.linspace(-2.2, 2.2, 90)
    yy = y + 0.02 * (1 - np.cos(lon)) / 2
    vis = H.facing_lon(lon, yy, 0.03) > -0.05
    lo = lon[vis]
    A_ = H.Plon(lo, yy[vis] - width / 2, 0.035)
    B_ = H.Plon(lo, yy[vis] + width / 2, 0.035)
    cv.band(A_, B_, color, 1.0, mode="paint", rows=2)
    cv.band(A_, B_, "ink", lambda S, T: 0.35 * (np.abs(T - 0.5) * 2) ** 2, rows=4)
    cv.band(A_, B_, "ink", lambda S, T: 0.35 * (1 - np.sin(np.pi * S)) ** 2, rows=2)
    cv.stroke(A_, s * 0.004, "ink", 0.9, prof="iron")
    cv.stroke(B_, s * 0.004, "ink", 0.9, prof="iron")
    if tails:
        k = H.Plon(np.array([-far * 2.0]), np.array([y + 0.02]), 0.04)[0]
        for j in range(2):
            pts = [k, k + np.array([-far * s * (0.06 + 0.03 * j), s * (0.08 + 0.02 * j)]),
                   k + np.array([-far * s * (0.08 + 0.05 * j), s * (0.20 + 0.04 * j)])]
            cv.stroke(g.catmull(pts, 8), s * 0.03, color, 1.0, prof="tail", taper=(0.05, 0.8))
