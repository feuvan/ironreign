"""The face canon: gongbi face templates with per-character parameters.

Every feature is authored frontally as through-points in head units (crown 0 .. chin 1) after
the classical canon (三庭五眼: hairline-brow, brow-nose base, nose base-chin equal; the face five
eyes wide) and wrapped onto the turned head by :class:`head.Head`.

Feature vocabulary (traditional names, the painter's choices):
  eyes   丹凤眼 'phoenix' (long, lifted, pointed outer corner, scholars and heroes)
         杏眼   'almond'  (bright, open, ladies and youths)
         环眼   'fierce'  (wide open, round upper lid, warriors - never bulging)
         'elder'          (heavier hooded lid, slightly lowered outer corner)
  brows  剑眉 'sword', 卧蚕眉 'silkworm', 柳叶眉 'willow', 寿眉 'longevity' (long white)
Line work: 铁线描 for male faces, 游丝描 for ladies; 赭墨 (brown ink) for skin lines, 浓墨 for the
eyes, 胭脂 for lips.  Shading: 分染 ochre along the contour and sockets, 胭脂 rouge on cheeks,
三白 shell-white lifts on forehead, nose bridge and chin.
"""

import math
from dataclasses import dataclass, field

import numpy as np

import geom2d as g
import palette as pal
from head import Head


@dataclass
class FaceSpec:
    sex: str = "m"
    age: float = 35.0
    yaw: float = 20.0
    roll: float = 0.0
    shape: dict = field(default_factory=dict)
    # skin & paint
    skin: str = "skin_peach"
    shade: str = "ochre"
    shade_k: float = 1.0          # strength of ochre modelling
    rouge_k: float = 0.5          # cheek rouge
    white_k: float = 0.5          # 三白 lifts
    line: str = "ink_brown"
    line_w: float = 1.0           # line weight multiplier
    # eyes
    eye: str = "phoenix"
    eye_y: float = 0.50
    eye_w: float = 0.128
    eye_h: float = 0.30           # opening height / width
    eye_tilt: float = 0.07        # outer-corner lift (fraction of eye width)
    eye_gap: float = 0.062        # inner corner offset from the centre line
    crease: float = 0.7
    lower_lid: float = 0.6
    iris: float = 0.47            # iris diameter / eye width
    gaze: tuple = (0.6, 0.0)      # (0 = with the head .. 1 = at the viewer, vertical px)
    eye_rouge: float = 0.0
    tail: float = 0.10            # phoenix tail length (fraction of eye width)
    # brows
    brow: str = "sword"
    brow_y: float = 0.418         # height of the brow head
    brow_len: float = 0.175
    brow_th: float = 0.026
    brow_lift: float = 0.035      # tail rise
    brow_knit: float = 0.0        # +: inner ends pulled down (fierce), -: raised (worried)
    brow_col: str = "ink"
    brow_grey: float = 0.0        # 0 black .. 1 white hairs
    brow_gap: float = 0.0
    # nose
    nose_y: float = 0.688
    nose_tip: float = 0.090
    nose_w: float = 0.058
    nose_len: float = 1.0
    bridge: float = 1.0           # strength of the nose-bridge line (ladies: faint)
    # mouth
    mouth_y: float = 0.792
    mouth_w: float = 0.165
    lip_up: float = 0.020
    lip_lo: float = 0.026
    smile: float = 0.0            # + corners up, - down (stern)
    lip: str = "lip"
    lip_k: float = 1.0
    # age / character
    wrinkles: float = 0.0
    frown: float = 0.0
    cheekbone_line: float = 0.0
    seed: int = 0


# ------------------------------------------------------------------------------------------
# eye templates: (u along inner->outer corner, v up), heights as fractions of the opening h

EYES = {
    "phoenix": dict(
        U=[(0.0, 0.0), (0.09, 0.60), (0.30, 1.0), (0.58, 0.94), (0.84, 0.58), (1.0, 0.0)],
        L=[(0.0, 0.0), (0.16, -0.30), (0.46, -0.40), (0.78, -0.27), (1.0, 0.0)]),
    "almond": dict(
        U=[(0.0, 0.0), (0.08, 0.56), (0.30, 0.95), (0.55, 1.0), (0.80, 0.74), (1.0, 0.0)],
        L=[(0.0, 0.0), (0.14, -0.36), (0.42, -0.52), (0.74, -0.42), (1.0, 0.0)]),
    # fierce: the inner half of the upper lid presses down (anger), peak towards the outside
    "fierce": dict(
        U=[(0.0, 0.0), (0.10, 0.42), (0.36, 0.82), (0.64, 1.0), (0.87, 0.74), (1.0, 0.08)],
        L=[(0.0, 0.0), (0.15, -0.36), (0.46, -0.48), (0.78, -0.36), (1.0, 0.08)]),
    "elder": dict(
        U=[(0.0, 0.0), (0.10, 0.62), (0.34, 1.0), (0.62, 0.90), (0.86, 0.52), (1.0, -0.04)],
        L=[(0.0, 0.0), (0.16, -0.32), (0.48, -0.42), (0.80, -0.30), (1.0, -0.04)]),
}


class FaceDrawer:
    """Draws one face on a canvas; keeps the computed landmarks for hair/beard/headgear."""

    def __init__(self, cv, head: Head, F: FaceSpec):
        self.cv = cv
        self.H = head
        self.F = F
        self.s = head.s
        self.far = head.far_side()          # screen side (+1 right) of the far half
        self.rng = np.random.default_rng(F.seed + 11)
        self.lm = {}

    # -- helpers ---------------------------------------------------------------------------
    def px(self, v):
        return v * self.s / 230.0           # widths authored for a 230 px head

    def W(self, pts, dz=0.0):
        return self.H.P(pts, dz)

    def side_sign(self, side):
        """frontal side (-1 viewer-left, +1 viewer-right) -> 'near'/'far'."""
        return "far" if side == self.far else "near"

    # -- face shape ------------------------------------------------------------------------
    def outline(self):
        H = self.H
        far = self.far
        ys = np.linspace(0.18, 1.0, 70)
        cy, sy = math.cos(H.yaw), math.sin(H.yaw)
        farpts, nearpts = [], []
        for y in ys:
            x0, z = H.section(y, 240)
            m = z >= H.zc(y) - 1e-6
            x0, z = x0[m], z[m]
            X = x0 * cy + z * sy
            i = np.argmax(X * far)
            farpts.append((x0[i], y, z[i]))
            j = np.argmin(X * far)
            nearpts.append((x0[j], y, z[j]))
        farpts = np.array(farpts)
        nearpts = np.array(nearpts)
        # painter's modelling of the far silhouette: brow ridge, temple dip under it, cheekbone
        # (颧骨) swell, hollow under the cheekbone, masseter
        sh = self.H.sh
        cb = sh.get("cheekbone", 1.0)
        def bump(y, c, w):
            return np.exp(-((y - c) / w) ** 2)
        dx = (0.003 * bump(ys, 0.40, 0.04) - 0.002 * bump(ys, 0.47, 0.04)
              + 0.006 * cb * bump(ys, 0.57, 0.06) - 0.004 * cb * bump(ys, 0.70, 0.06)
              + 0.002 * bump(ys, 0.83, 0.05))
        farpts[:, 0] += dx * far / max(math.cos(H.yaw), 0.5)
        # full, rounded lower cheeks and jaw (鹅蛋脸) for ladies and youths
        rnd = sh.get("round", 0.0)
        if rnd:
            b = bump(ys, 0.86, 0.075)
            farpts[:, 0] += far * rnd * (0.010 * b + 0.016 * bump(ys, 0.78, 0.09))
            nearpts[:, 0] -= far * rnd * 0.022 * b
        # chin: rounded bottom between the two y=1 points, through the chin's lowest point
        chin_c = np.array([0.0, 1.012, float(H.zc(1.0) + H.d(1.0) * 0.85)])
        return farpts, nearpts, chin_c

    def face_poly(self):
        farpts, nearpts, chin_c = self.outline()
        Fp = self.H.Pz(farpts)
        Np = self.H.Pz(nearpts)
        C = self.H.Pz([chin_c])[0]
        bottom = g.catmull([Fp[-3], Fp[-1], C, Np[-1], Np[-3]], n=8)
        poly = np.vstack([Fp[:-3], bottom, Np[:-3][::-1]])
        self.lm["far_outline"] = Fp
        self.lm["near_outline"] = Np
        self.lm["chin"] = C
        self.lm["face_poly"] = poly
        return poly

    # -- skin ------------------------------------------------------------------------------
    def skin(self):
        cv, F, H = self.cv, self.F, self.H
        poly = self.face_poly()
        cen = self.W([(0.0, 0.62)])[0]
        cv.fill(poly, F.skin, 1.0, "paint")
        # uneven hand-laid wash: soft mottling so the skin never reads as a flat vector fill
        def mott(col, scale, k, sd):
            B = g.resample(poly, 140, closed=True)
            c = self.W([(0.0, 0.6)])[0]
            cv.radial(B, c, col, k, rings=15,
                      alpha_xy=lambda V: np.clip(g.vnoise(V, scale, sd), 0, 1))
        mott(F.shade, self.px(45), 0.07 * F.shade_k, F.seed + 1)
        mott("rouge", self.px(60), 0.05, F.seed + 2)
        sk = F.shade_k
        # contour 分染 all round the face, stronger at the jaw and on the far cheek edge
        Fp = self.lm["far_outline"]
        Np = self.lm["near_outline"]
        far_side = 1 if g.area(poly) > 0 else -1
        self._edge_in(Fp[12:], self.px(22), F.shade, 0.36 * sk)
        self._edge_in(Np[38:], self.px(24), F.shade, 0.38 * sk)
        # broad near plane (from the ear forward) turned from the viewer: soft tone
        self._edge_in(Np[10:46], self.px(34), F.shade, 0.22 * sk, rows=8, power=1.2)
        # temples and under the cheekbone
        for side in (-1, 1):
            k = 0.7 if side == self.far else 1.0
            c = self.W([(side * 0.26, 0.69)])[0]
            cv.blob(c, self.px(22) * (0.6 if side == self.far else 1.0), self.px(30),
                    F.shade, 0.10 * sk * k)
        # chin / jaw underside
        C = self.lm["chin"]
        cv.blob(C + np.array([0, -self.px(10)]), self.px(18), self.px(10), F.shade, 0.16 * sk)

    def _edge_in(self, P, width, color, alpha, rows=6, power=1.4):
        """graded wash along P towards the face interior."""
        if len(P) < 3:
            return
        cen = self.W([(0.0, 0.6)])[0]
        mid = P[len(P) // 2]
        nrm = g.normals(g.resample(P, 20))[10]
        side = 1 if np.dot(cen - mid, nrm) > 0 else -1
        self.cv.edge(P, width, color, alpha, side=side, rows=rows, power=power, end_fade=0.15)

    def rouge_and_lifts(self):
        cv, F = self.cv, self.F
        for side in (-1, 1):
            fs = side == self.far
            c = self.W([(side * 0.18, F.eye_y + 0.105)])[0]
            rx = self.px(34) * (0.62 if fs else 1.0)
            cv.blob(c, rx, self.px(28), "#e3828a", 0.17 * F.rouge_k, power=1.2)
        # 三白: forehead, nose bridge, chin lifted with shell white
        wk = F.white_k
        cv.blob(self.W([(0.0, 0.31)])[0], self.px(30), self.px(18), "white", 0.30 * wk,
                mode="paint")
        cv.blob(self.W([(0.0, 0.56)], dz=0.04)[0], self.px(5), self.px(18), "white", 0.35 * wk,
                mode="paint")
        cv.blob(self.W([(0.0, 0.92)])[0], self.px(11), self.px(7), "white", 0.25 * wk,
                mode="paint")
        # soft rouge on the chin and forehead centre (warm life)
        cv.blob(self.W([(0.0, 0.94)])[0], self.px(14), self.px(9), "rouge", 0.10 * F.rouge_k)

    # -- eyes ------------------------------------------------------------------------------
    def eye_curves(self, side):
        F = self.F
        T = EYES[F.eye]
        h = F.eye_h
        knit = 0.0

        def to_frontal(pts):
            pts = np.asarray(pts, float)
            u, v = pts[:, 0], pts[:, 1] * h
            x0 = side * (F.eye_gap + u * F.eye_w)
            y = F.eye_y - (v + F.eye_tilt * u) * F.eye_w
            return np.stack([x0, y], 1)
        U = g.catmull(T["U"], n=10)
        L = g.catmull(T["L"], n=10)
        # relief: the eye sits in the socket; lids bulge forward over the ball
        dzU = -0.012 + 0.020 * np.sin(np.pi * U[:, 0])
        dzL = -0.012 + 0.016 * np.sin(np.pi * L[:, 0])
        Uf = to_frontal(U)
        Lf = to_frontal(L)
        return self.W(Uf, dzU), self.W(Lf, dzL), Uf, Lf, to_frontal

    def eye(self, side):
        """One eye after the gongbi canon: socket wash, toned eye white, a large dark iris
        tucked under the upper lid, lid shadow, a tiny catch light; then the lines: the heavy
        upper lid (浓墨, the strongest line of the face) with the inner hook and outer tail,
        the fine crease and the faint broken lower lid."""
        cv, F, H = self.cv, self.F, self.H
        fs = side == self.far
        U, L, Uf, Lf, to_frontal = self.eye_curves(side)
        ew0 = F.eye_w * self.s
        lw = self.px(1.0) * F.line_w
        # --- socket: ochre between lid and brow, deeper at the inner corner (the nose side)
        lidtop = g.catmull(self.W(to_frontal([(-0.05, 1.6), (0.35, 2.5), (0.8, 2.2), (1.12, 0.8)])), 8)
        cv.band(lidtop, U, F.shade,
                lambda S, T: 0.24 * F.shade_k * g.smoothstep(0, 1, T) ** 1.3
                * (0.55 + 0.45 * np.cos(np.pi * np.clip(S, 0, 1)) ** 2), rows=6)
        if F.eye_rouge > 0:
            cv.band(lidtop, U, "rouge",
                    lambda S, T: 0.30 * F.eye_rouge * g.smoothstep(0, 1, T) ** 1.2
                    * np.sin(np.pi * np.clip(S * 0.8 + 0.2, 0, 1)) ** 0.6, rows=6)
            # rouge flushing out from the outer corner towards the temple (Tang 红妆)
            oc = U[-1]
            cv.blob(oc + np.array([side * self.px(6), self.px(2)]), self.px(13), self.px(8),
                    "rouge", 0.22 * F.eye_rouge, rot=-side * 0.4)
        inner = U[0]
        nose_root = self.W([(0.0, F.eye_y - 0.03)])[0]
        cv.blob(inner + (nose_root - inner) * 0.45 + np.array([0, -self.px(2)]),
                self.px(6), self.px(10), F.shade, 0.26 * F.shade_k)
        # --- eye white, toned to the skin, pinker in the corners
        skin = pal.srgb(F.skin)
        wcol = pal.mix(F.skin, "#f4efe6", 0.62)

        def white_col(S, T):
            c1 = pal.mix(pal.hexs(wcol), "rouge", 0.28)
            k = (1 - np.sin(np.pi * S)) ** 2
            return wcol[None, None, :] * (1 - k[..., None]) + c1[None, None, :] * k[..., None]
        cv.band(U, L, pal.hexs(wcol), 0.95, mode="paint", rows=4, colors=white_col)
        # --- iris: screen-space disc, its top tucked under the upper lid
        ball_c = g.at(U, 0.5) * 0.5 + g.at(L, 0.5) * 0.5
        rb = 0.085
        shift_x = -math.sin(H.yaw) * rb * self.s * F.gaze[0]
        ri = F.iris * ew0 / 2
        icx = ball_c[0] + shift_x
        ord_u = np.argsort(U[:, 0])
        uy = float(np.interp(icx, U[ord_u, 0], U[ord_u, 1]))
        ord_l = np.argsort(L[:, 0])
        ly = float(np.interp(icx, L[ord_l, 0], L[ord_l, 1]))
        icy = min(uy + ri * 0.70, (uy + ly) / 2 + ri * 0.25) + F.gaze[1]
        ic = np.array([icx, icy])
        open_poly = np.vstack([U, L[::-1][1:-1]])
        ring = g.clip_convex(g.ellipse(ic, ri, ri, n=48), open_poly)
        if len(ring) >= 3:
            cv.fill(ring, "#2b1e17", 1.0, "paint")
            cv.blob(ic + np.array([0, ri * 0.38]), ri * 0.72, ri * 0.50, "#6a4a34", 0.45,
                    mode="paint")
            pup = g.clip_convex(g.ellipse(ic, ri * 0.48, ri * 0.48, n=24), open_poly)
            if len(pup) >= 3:
                cv.fill(pup, "#0c0907", 0.95, "paint")
            lim = g.clip_convex(g.ellipse(ic, ri * 0.97, ri * 0.97, n=48), open_poly)
            if len(lim) > 3:
                cv.stroke(lim, lw * 0.5, "#130d0a", 0.55, caps=False, prof="flat", noise=0)
        # --- shadow of the upper lid over the ball and iris
        Ur = g.resample(U, 40)
        Lr = g.resample(L, 40)
        cv.band(Ur, Ur * 0.45 + Lr * 0.55, "#3d2f2a",
                lambda S, T: 0.62 * (1 - T) ** 1.6 * (0.55 + 0.45 * np.sin(np.pi * S)), rows=5)
        # catch light, light from the upper left
        hl = ic + np.array([-ri * 0.32, -ri * 0.18])
        if g.poly_contains(open_poly, hl[None])[0]:
            cv.dot(hl, max(0.55, ri * 0.14), "white", 0.85)
        self.lm["iris_%s" % ("far" if fs else "near")] = ic
        # --- upper lid line
        n = 60
        Uu = g.resample(U, n)
        t = np.linspace(0, 1, n)
        wprof = (0.28 + 0.72 * g.smoothstep(0.0, 0.42, t)) * (1 - 0.5 * g.smoothstep(0.88, 1.0, t))
        wmax = self.px(2.6) * F.line_w
        tail = F.tail
        if tail > 0:
            ext = to_frontal([(1.0, 0.0), (1.0 + tail * 0.55, 0.06 + 0.45 * tail),
                              (1.0 + tail, 0.10 + 0.85 * tail)])
            E = g.catmull(self.W(ext, -0.01), 6)
            Uu2 = g.resample(np.vstack([Uu[:-1], E]), n + 14)
            t2 = np.linspace(0, 1, len(Uu2))
            k_end = 1.0 / (1 + tail)
            wl = np.interp(t2 / k_end, t, wprof, right=wprof[-1])
            wl = wl * (1 - 0.95 * g.smoothstep(k_end * 0.97, 1.0, t2))
            cv.stroke(Uu2, 1, "ink", 0.97, widths=wmax * wl, noise=0.04)
        else:
            cv.stroke(Uu, 1, "ink", 0.97, widths=wmax * wprof, noise=0.04)
        # inner corner hook (内眦)
        ic0 = U[0]
        dn = (L[4] - ic0)
        hook = np.array([ic0 + (U[4] - ic0) * 0.9, ic0, ic0 + dn * 0.6 + np.array([0, self.px(0.6)])])
        cv.stroke(g.catmull(hook, 5), self.px(0.9) * F.line_w, "ink_d", 0.8, prof="tail")
        cv.blob(ic0 + (g.at(L, 0.07) - ic0) * 0.5 + (g.at(U, 0.07) - ic0) * 0.5, self.px(2.2),
                self.px(1.6), "rouge_d", 0.40)
        # crease (双眼皮): a fine line echoing the lid, joining the tail
        if F.crease > 0:
            cr = to_frontal([(0.20, 1.30), (0.50, 1.42), (0.82, 1.15), (1.0 + tail * 0.5, 0.40 + 0.4 * tail)])
            C = g.catmull(self.W(cr, 0.0), 8)
            cv.stroke(C, self.px(0.8) * F.line_w, F.line, 0.70 * F.crease, prof="silk")
            cv.edge(C, self.px(3.5), F.shade, 0.18 * F.shade_k, side=self._down_side(C), rows=3)
        # lower lid: fine and broken
        if F.lower_lid > 0:
            Ls = g.sub(L, 0.22, 1.0)[::-1]
            cv.stroke(Ls, self.px(0.8) * F.line_w, F.line, 0.80 * F.lower_lid, prof="silk",
                      alpha_along=lambda t: 1 - 0.75 * g.smoothstep(0.45, 1.0, t))
            Lb = g.sub(L, 0.1, 0.95)
            k = 0.10 + 0.22 * F.wrinkles
            cv.edge(Lb, self.px(4 + 4 * F.wrinkles), F.shade, k * F.shade_k,
                    side=self._down_side(Lb), rows=4)
            if F.wrinkles > 0.3:
                bag = to_frontal([(0.15, -0.95), (0.5, -1.35), (0.9, -0.9)])
                cv.stroke(g.catmull(self.W(bag), 8), self.px(0.7), F.line, 0.40 * F.wrinkles,
                          prof="silk")
        self.lm["eye_%s" % ("far" if fs else "near")] = (U, L)

    def _down_side(self, P):
        nrm = g.normals(g.resample(P, 9))[4]
        return 1 if nrm[1] > 0 else -1

    def _up_side(self, P):
        return -self._down_side(P)

    # -- brows -----------------------------------------------------------------------------
    def brow(self, side):
        cv, F = self.cv, self.F
        fs = side == self.far
        kind = F.brow
        L0 = F.brow_len
        x_in = F.eye_gap - 0.004 + F.brow_gap
        y_in = F.brow_y + 0.012 * F.brow_knit
        lift = F.brow_lift
        if kind == "sword":
            C = [(0.0, 0.0), (0.30, -0.30 * lift - 0.006), (0.66, -0.70 * lift - 0.008),
                 (1.0, -1.0 * lift)]
            thick = lambda t: (0.95 + 0.15 * np.sin(np.pi * t * 0.8)) * (1 - g.smoothstep(0.55, 1.0, t) * 0.92)
        elif kind == "silkworm":
            C = [(0.0, 0.004), (0.28, -0.022), (0.62, -0.040 - 0.3 * lift), (1.0, -0.018 - 0.5 * lift)]
            thick = lambda t: (0.75 + 0.35 * np.sin(np.pi * np.clip(t * 1.1, 0, 1))) * (1 - g.smoothstep(0.7, 1.0, t) * 0.85)
        elif kind == "willow":
            C = [(0.0, 0.0), (0.33, -0.022), (0.70, -0.026), (1.06, -0.004)]
            thick = lambda t: np.sin(np.pi * np.clip(0.08 + t * 0.92, 0, 1)) ** 0.7 * (1 - 0.3 * t)
        elif kind == "longevity":
            C = [(0.0, 0.0), (0.35, -0.018), (0.72, -0.010), (1.05, 0.030)]
            thick = lambda t: (0.85 + 0.2 * np.sin(np.pi * t)) * (1 - g.smoothstep(0.8, 1.0, t) * 0.6)
        else:
            raise KeyError(kind)
        pts = np.array([(side * (x_in + u * L0), y_in + v - 0.012 * F.brow_knit * (u > 0.0) * u * 0)
                        for u, v in C])
        # knit: inner end pulled down/in (fierce) - rotate the inner part
        if F.brow_knit:
            pts[0, 1] += 0.010 * F.brow_knit
            pts[1, 1] += 0.004 * F.brow_knit
        Cf = g.catmull(pts, 12)
        Cs = self.W(Cf, 0.012)
        n = 50
        Cs = g.resample(Cs, n)
        t = np.linspace(0, 1, n)
        th = F.brow_th * self.s * thick(t) * (0.88 if fs else 1.0)
        Nn = g.normals(Cs)
        # make normals point up on screen
        if Nn[n // 2][1] > 0:
            Nn = -Nn
        top = Cs + Nn * (th * 0.45)[:, None]
        bot = Cs - Nn * (th * 0.55)[:, None]
        grey = F.brow_grey
        base_col = pal.hexs(pal.mix("ink_m", "hair_grey", min(1, grey * 1.2)))
        # wash body
        if kind == "willow":
            cv.band(top, bot, "ink_m", lambda S, T: 0.60 * np.sin(np.pi * np.clip(T, 0, 1)) ** 0.6
                    * (0.35 + 0.65 * np.sin(np.pi * np.clip(S * 0.9 + 0.1, 0, 1)) ** 0.6),
                    mode="glaze", rows=4)
            cv.stroke(Cs, 1, "ink_d", 0.60, widths=th * 0.42, noise=0.05)
            # fine hairs along the brow
            rng = np.random.default_rng(F.seed + (3 if fs else 5))
            for i in range(26):
                u = rng.uniform(0.05, 0.95)
                k = int(u * (n - 1))
                p0 = Cs[k] + Nn[k] * th[k] * rng.uniform(-0.4, 0.2)
                tg = g.tangents(Cs)[k]
                p1 = p0 + (tg * 0.9 + Nn[k] * 0.25) * th[k] * 1.6
                cv.stroke(np.array([p0, p1]), self.px(0.45), "ink_d", 0.5, prof="hair")
            self.lm["brow_%s" % ("far" if fs else "near")] = Cs
            return
        cv.band(top, bot, base_col, lambda S, T: (0.55 - 0.25 * grey) * np.sin(np.pi * np.clip(T, 0, 1)) ** 0.5
                * (0.45 + 0.55 * g.smoothstep(0, 0.3, S)), mode="glaze", rows=4)
        # hair strokes (丝毛): head hairs rise steeply, body hairs slant outward, tail lies flat
        rng = np.random.default_rng(F.seed * 7 + (3 if fs else 5))
        nh = int(70 * (F.brow_th / 0.026) * (0.8 if fs else 1.0))
        dir_out = Cs[-1] - Cs[0]
        dir_out = dir_out / np.linalg.norm(dir_out)
        for i in range(nh):
            u = rng.uniform(0, 1) ** 0.85
            k = int(u * (n - 1))
            v = rng.uniform(-0.55, 0.35)
            p0 = Cs[k] + Nn[k] * th[k] * v
            tang = g.tangents(Cs)[k]
            ang_up = (1 - g.smoothstep(0.0, 0.35, u)) * 1.1 + 0.25      # radians from tangent
            d = tang * math.cos(ang_up) + Nn[k] * math.sin(ang_up)
            ln = th[k] * (0.9 + 0.8 * rng.uniform()) * (1.6 - 0.8 * u) + self.px(1.5)
            p1 = p0 + d * ln * 0.5 + Nn[k] * rng.normal(0, 0.1) * ln
            p2 = p0 + d * ln + tang * ln * 0.25
            if grey > 0 and rng.uniform() < grey:
                col, al = "hair_white", 0.85
                mode = "paint"
            else:
                col, al = ("ink" if grey < 0.5 else "ink_m"), rng.uniform(0.55, 0.9)
                mode = "paint"
            cv.stroke(g.catmull([p0, p1, p2], 5), self.px(0.55 + 0.25 * rng.uniform()), col, al,
                      prof="hair", mode=mode, noise=0.1)
        if kind == "longevity":
            # long white hairs drooping past the tail
            for i in range(14):
                k = int((0.55 + 0.45 * rng.uniform()) * (n - 1))
                p0 = Cs[k] + Nn[k] * th[k] * rng.uniform(-0.4, 0.3)
                dx = dir_out * self.px(14 + 10 * rng.uniform())
                p1 = p0 + dx * 0.6 + np.array([0, self.px(4)])
                p2 = p0 + dx + np.array([0, self.px(10 + 8 * rng.uniform())])
                cv.stroke(g.catmull([p0, p1, p2], 6), self.px(0.6), "hair_white", 0.85,
                          prof="hair", mode="paint")
        self.lm["brow_%s" % ("far" if fs else "near")] = Cs

    # -- nose ------------------------------------------------------------------------------
    def nose(self):
        cv, F, H = self.cv, self.F, self.H
        far = self.far
        tipy = F.nose_y
        top = F.brow_y + 0.03
        L = F.nose_len
        tip_z = F.nose_tip
        # bridge profile (frontal x0 = far * small, relief dz rising to the tip)
        ys = np.linspace(top, tipy - 0.012, 14)
        dz = 0.004 + (tip_z - 0.004) * g.smoothstep(top, tipy + 0.01, ys) ** 1.6
        bridge_far = self.W(np.stack([far * (0.020 + 0.010 * (ys - top) / (tipy - top)), ys], 1), dz)
        self.lm["nose_tip"] = self.W([(far * 0.0, tipy - 0.010)], tip_z)[0]
        # near-side bridge shading (soft tone, no line)
        bridge_near = self.W(np.stack([-far * (0.022 + 0.012 * (ys - top) / (tipy - top)), ys], 1), dz * 0.85)
        cv.edge(bridge_near[2:], self.px(8), F.shade, 0.18 * F.shade_k,
                side=self._side_towards(bridge_near[2:], -far), rows=4)
        # far bridge line: from the brow head down (broken in the middle like a painter's line)
        lw = self.px(1.0) * F.line_w
        if F.bridge >= 0.5:
            cv.stroke(bridge_far[:5], lw * 0.9, F.line, 0.55 * F.bridge, prof="silk")
            cv.stroke(g.catmull(bridge_far[6:], 4), lw, F.line, 0.75 * F.bridge, prof="silk")
        elif F.bridge > 0:
            cv.stroke(g.catmull(bridge_far[9:], 4), lw * 0.8, F.line, 0.9 * F.bridge, prof="silk")
        # tip and wings
        w = F.nose_w
        y_w = tipy - 0.004
        tip3 = [(far * 0.012, tipy - 0.020, tip_z * 0.95), (far * 0.020, tipy - 0.004, tip_z * 0.85),
                (far * 0.010, tipy + 0.012, tip_z * 0.70), (-far * 0.012, tipy + 0.016, tip_z * 0.62)]
        tip = g.catmull(self.H.Pz([(x, y, self.H.zsurf(x, y) + z) for x, y, z in tip3]), 6)
        dl = 0.55 if F.sex == "f" else 1.0          # ladies: the most delicate nose lines
        cv.stroke(tip, lw * 1.05 * dl, F.line, 0.85 * dl ** 2, prof="iron")
        # near wing (鼻翼): C curve
        wn = [(-far * (w * 0.55), y_w - 0.026, 0.035), (-far * (w * 0.98), y_w - 0.006, 0.010),
              (-far * (w * 0.90), y_w + 0.010, 0.012), (-far * (w * 0.55), y_w + 0.014, 0.030)]
        WN = g.catmull(self.H.Pz([(x, y, self.H.zsurf(x, y) + z) for x, y, z in wn]), 8)
        cv.stroke(WN, lw * 1.05 * (0.8 if F.sex == "f" else 1.0), F.line, 0.85 * dl,
                  prof="orchid", taper=(0.4, 0.6))
        # far wing peeking past the tip
        wf = [(far * (w * 0.55), y_w - 0.010, 0.040), (far * (w * 0.92), y_w + 0.002, 0.015),
              (far * (w * 0.60), y_w + 0.014, 0.030)]
        WF = g.catmull(self.H.Pz([(x, y, self.H.zsurf(x, y) + z) for x, y, z in wf]), 6)
        cv.stroke(WF, lw * 0.8, F.line, 0.6 * dl, prof="silk")
        # nostrils
        nn = [(-far * w * 0.50, y_w + 0.010, 0.045), (-far * w * 0.22, y_w + 0.016, 0.06)]
        NN = g.catmull(self.H.Pz([(x, y, self.H.zsurf(x, y) + z) for x, y, z in nn]), 5)
        cv.stroke(NN, lw * 1.5, "ink_brown", 0.85, prof="orchid")
        nf = [(far * w * 0.18, y_w + 0.016, 0.06), (far * w * 0.40, y_w + 0.012, 0.045)]
        NF = g.catmull(self.H.Pz([(x, y, self.H.zsurf(x, y) + z) for x, y, z in nf]), 5)
        cv.stroke(NF, lw * 1.0, "ink_brown", 0.6, prof="orchid")
        # shadow under the nose & wing creases
        under = self.W([(-far * w, y_w + 0.016), (0, y_w + 0.026), (far * w * 0.8, y_w + 0.016)], 0.03)
        cv.edge(g.catmull(under, 6), self.px(7), F.shade, 0.26 * F.shade_k,
                side=self._down_side(g.catmull(under, 6)), rows=4)
        cv.blob(WN[len(WN) // 2], self.px(5), self.px(6), F.shade, 0.22 * F.shade_k)
        # philtrum: faint
        ph = self.W([(0.0, y_w + 0.03), (0.0, F.mouth_y - F.lip_up - 0.004)], 0.03)
        cv.stroke(ph, self.px(3.0), F.shade, 0.10 * F.shade_k, mode="glaze", prof="orchid")
        self.lm["nose_wing_near"] = WN
        self.lm["nose_base"] = self.W([(0.0, y_w + 0.024)], 0.03)[0]

    def _side_towards(self, P, xdir):
        nrm = g.normals(g.resample(P, 9))[4]
        return 1 if nrm[0] * xdir > 0 else -1

    # -- mouth -----------------------------------------------------------------------------
    def mouth(self):
        cv, F = self.cv, self.F
        mw = F.mouth_w / 2
        y = F.mouth_y
        sm = F.smile * 0.012
        up = F.lip_up
        lo = F.lip_lo

        def M(pts, dz=0.0):
            pts = np.asarray(pts, float)
            # lips protrude: relief strongest in the middle
            rel = 0.020 * (1 - (pts[:, 0] / (mw * 1.15)) ** 2).clip(0, 1) + dz
            return self.W(pts, rel)
        # stomion (lip parting line)
        line = [(-mw, y - sm), (-mw * 0.55, y + 0.002), (-mw * 0.18, y - 0.002), (0.0, y + 0.003),
                (mw * 0.18, y - 0.002), (mw * 0.55, y + 0.002), (mw, y - sm)]
        upper = [(-mw, y - sm), (-mw * 0.55, y - up * 0.75), (-mw * 0.20, y - up * 1.05),
                 (0.0, y - up * 0.80), (mw * 0.20, y - up * 1.05), (mw * 0.55, y - up * 0.75),
                 (mw, y - sm)]
        lower = [(-mw, y - sm), (-mw * 0.62, y + lo * 0.65), (-mw * 0.2, y + lo * 1.0),
                 (mw * 0.2, y + lo * 1.0), (mw * 0.62, y + lo * 0.65), (mw, y - sm)]
        Ls = g.catmull(M(line), 8)
        Us = g.catmull(M(upper), 8)
        Lo = g.catmull(M(lower), 8)
        k = F.lip_k
        # lips: rouge washes, upper lip deeper (胭脂), lower lip lighter with a soft lift
        cv.band(Us, g.resample(Ls, len(Us)), F.lip,
                lambda S, T: k * (0.55 + 0.35 * T) * (0.25 + 0.75 * np.sin(np.pi * S) ** 0.6),
                rows=4)
        cv.band(g.resample(Ls, len(Lo)), Lo, F.lip,
                lambda S, T: k * (0.62 - 0.30 * T) * (0.25 + 0.75 * np.sin(np.pi * S) ** 0.6),
                rows=4)
        cv.blob(g.at(Lo, 0.5) + (g.at(Ls, 0.5) - g.at(Lo, 0.5)) * 0.45, self.px(7), self.px(2.2),
                "white", 0.25 * k, mode="paint")
        # under-lip shadow & mouth corners
        ul = M([(-mw * 0.6, y + lo * 1.25), (0, y + lo * 1.55), (mw * 0.6, y + lo * 1.25)])
        ulc = g.catmull(ul, 8)
        cv.edge(ulc, self.px(7), F.shade, 0.24 * F.shade_k, side=self._down_side(ulc), rows=4)
        lw = self.px(1.1) * F.line_w
        cv.stroke(Ls, lw, "ink_rouge", 0.9, prof="orchid", taper=(0.5, 0.5))
        for sx in (-1, 1):
            c = M([(sx * mw, y - sm)])[0]
            d = M([(sx * mw * 1.12, y - sm + 0.006 - 0.01 * F.smile)])[0]
            cv.stroke(np.array([c - (d - c) * 0.6, d]), lw * 0.9, "ink_rouge", 0.7, prof="tail")
        # upper lip edge hint (very light)
        cv.stroke(g.sub(Us, 0.25, 0.75), self.px(0.6), "rouge_d", 0.3, prof="silk")
        self.lm["mouth"] = (Us, Ls, Lo)
        self.lm["mouth_c"] = g.at(Ls, 0.5)

    # -- ear (near side) -------------------------------------------------------------------
    def ear(self, top=0.455, bot=0.70, lobe=1.0):
        cv, F, H = self.cv, self.F, self.H
        side = -self.far
        def E(pts):
            out = []
            for z, y, outk in pts:
                a = float(H.a(y))
                out.append((side * (a + 0.004 + 0.045 * outk), y, z))
            return H.Pz(out)
        h = bot - top
        helix = [(-0.005, top + 0.03 * h, 0.1), (-0.04, top, 0.5), (-0.095, top + 0.06 * h, 0.9),
                 (-0.12, top + 0.32 * h, 1.0), (-0.11, top + 0.62 * h, 0.85),
                 (-0.085, top + 0.86 * h, 0.55), (-0.055, bot, 0.35 * lobe),
                 (-0.025, bot - 0.02 * h, 0.2), (-0.012, bot - 0.10 * h, 0.1)]
        He = g.catmull(E(helix), 8)
        # ear skin
        cv.fill(np.vstack([He, E([(0.01, top + 0.5 * h, 0.0)])]), F.skin, 1.0, "paint")
        cv.fill(np.vstack([He, E([(0.01, top + 0.5 * h, 0.0)])]), "rouge", 0.14, "glaze")
        anti = [(-0.03, top + 0.18 * h, 0.4), (-0.075, top + 0.20 * h, 0.7),
                (-0.088, top + 0.45 * h, 0.75), (-0.07, top + 0.70 * h, 0.55),
                (-0.045, top + 0.76 * h, 0.4)]
        An = g.catmull(E(anti), 6)
        concha = g.catmull(E([(-0.03, top + 0.32 * h, 0.3), (-0.06, top + 0.42 * h, 0.5),
                              (-0.055, top + 0.62 * h, 0.4), (-0.025, top + 0.62 * h, 0.2)]), 6)
        cv.fill(concha, F.shade, 0.30 * F.shade_k, "glaze")
        cv.edge(He[3:-3], self.px(4), F.shade, 0.28 * F.shade_k,
                side=1, rows=3)
        lw = self.px(1.0) * F.line_w
        cv.stroke(He, lw, F.line, 0.85, prof="iron")
        cv.stroke(An, lw * 0.8, F.line, 0.65, prof="silk")
        tr = g.catmull(E([(-0.005, top + 0.45 * h, 0.1), (-0.022, top + 0.52 * h, 0.25),
                          (-0.012, top + 0.62 * h, 0.15)]), 5)
        cv.stroke(tr, lw * 0.8, F.line, 0.7, prof="silk")
        self.lm["ear"] = He

    # -- contour & age ---------------------------------------------------------------------
    def contour(self):
        cv, F = self.cv, self.F
        poly = self.lm["face_poly"]
        Fp = self.lm["far_outline"]
        Np = self.lm["near_outline"]
        n_far = len(Fp) - 3
        # far side from the temple (below the hairline) round the chin to the near jaw angle
        start = int(len(Fp) * 0.18)
        far_part = poly[start:]
        # cut the near part at the ear lobe height
        ylobe = self.H.cy + self.s * 0.74
        k = len(poly) - 1
        while k > 0 and poly[k][1] < ylobe:
            k -= 1
        line = poly[start:k + 1]
        lw = self.px(1.25) * F.line_w
        t = np.linspace(0, 1, 80)
        cv.stroke(g.resample(line, 160), 1, F.line, 0.92,
                  widths=lw * (0.55 + 0.45 * g.smoothstep(0.0, 0.5, t) * (1 - 0.35 * g.smoothstep(0.75, 1.0, t))),
                  noise=0.06)

    def age_lines(self):
        cv, F = self.cv, self.F
        wk = F.wrinkles
        lw = self.px(0.8) * F.line_w
        if F.frown > 0:
            for sx in (-0.016, 0.016):
                P = self.W([(sx, F.brow_y - 0.035), (sx * 1.25, F.brow_y + 0.005), (sx * 0.9, F.brow_y + 0.03)])
                cv.stroke(g.catmull(P, 6), lw, F.line, 0.55 * F.frown, prof="silk")
            cv.blob(self.W([(0.0, F.brow_y)])[0], self.px(9), self.px(9), F.shade, 0.18 * F.frown)
        if wk <= 0:
            return
        rng = np.random.default_rng(F.seed + 99)
        # forehead lines
        for i, yy in enumerate((0.29, 0.325, 0.36)):
            if rng.uniform() > wk + 0.2:
                continue
            w = 0.16 - 0.02 * i
            P = self.W([(-w, yy + 0.008), (-w * 0.3, yy - 0.004), (w * 0.35, yy - 0.002), (w, yy + 0.01)])
            cv.stroke(g.catmull(P, 8), lw * 0.9, F.line, 0.35 * wk, prof="silk",
                      alpha_along=lambda t: 0.4 + 0.6 * np.sin(np.pi * t))
        # nasolabial folds
        for side in (-1, 1):
            fs = side == self.far
            P = self.W([(side * (F.nose_w + 0.012), F.nose_y - 0.012),
                        (side * (F.nose_w + 0.035), F.nose_y + 0.05),
                        (side * (F.mouth_w / 2 + 0.03), F.mouth_y + 0.035)], 0.01)
            Pc = g.catmull(P, 8)
            cv.stroke(Pc, lw * (0.8 if fs else 1.0), F.line, 0.55 * wk, prof="silk")
            cv.edge(Pc, self.px(6), F.shade, 0.16 * wk, side=self._side_towards(Pc, side), rows=3)
            # crow's feet
            oc = self.W([(side * (F.eye_gap + F.eye_w + 0.012), F.eye_y - 0.004)])[0]
            for j in range(3):
                a = (-0.35 + 0.35 * j)
                d = np.array([side * math.cos(a), math.sin(a)]) * self.px(7)
                cv.stroke(np.array([oc, oc + d]), lw * 0.7, F.line, 0.3 * wk, prof="silk")

    # -- all ---------------------------------------------------------------------------------
    def draw_skin_layers(self):
        self.skin()
        self.rouge_and_lifts()

    def draw_features(self, ear=True):
        far = self.far
        if ear:
            self.ear()
        self.nose()
        self.mouth()
        for side in (-far, far):
            self.eye(side)
        for side in (-far, far):
            self.brow(side)
        self.age_lines()
        self.contour()
