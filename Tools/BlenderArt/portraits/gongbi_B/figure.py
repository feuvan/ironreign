"""Bust construction: neck and torso frame, robes with the crossed collar (交领右衽).

Torso surface: per height y (head units, same origin as the head) an elliptic cross-section of
half-width a(y) and half-depth d(y).  A surface point is addressed by (u, y) where u is the
angle around the body in quarter turns: u = 0 chest centre, u = +-1 the sides, |u| > 1 the back.
``u`` is in the *wearer-independent frontal* sense: u < 0 is the viewer's left in a frontal view
(= the wearer's right).

The crossed collar is always 右衽: the wearer's LEFT panel (u > 0 side) lies on top and crosses
to the wearer's right - a "y" seen from the front.  It is built in body space and projected, so
turning the figure never mirrors it into 左衽.
"""

import math

import numpy as np

import geom2d as g
import palette as pal


class Torso:
    def __init__(self, head, yaw_deg=None, shoulder=1.0, neck_r=0.20, slope=1.0, depth=1.0,
                 drop=0.0, pitch=12.0):
        self.H = head
        self.s = head.s
        self.cx = head.cx
        self.cy = head.cy
        self.yaw = math.radians(yaw_deg) if yaw_deg is not None else head.yaw
        self.neck_r = neck_r
        sw = shoulder
        sl = slope
        self.a_keys = [(0.95, neck_r), (1.06, neck_r * 1.06), (1.12, 0.40 * sw),
                       (1.19, 0.66 * sw), (1.28, 0.86 * sw), (1.38 + 0.04 * sl, 0.95 * sw),
                       (1.52 + 0.04 * sl, 0.99 * sw), (1.75, 1.00 * sw), (2.2, 0.98 * sw)]
        self.d_keys = [(0.95, neck_r * 0.95), (1.08, neck_r), (1.16, 0.30 * depth),
                       (1.30, 0.40 * depth), (1.5, 0.44 * depth), (2.2, 0.44 * depth)]
        self.drop = drop
        self.zoff = -0.03     # torso axis slightly behind the head axis
        self.pitch = math.radians(pitch)

    def a(self, y):
        k = self.a_keys
        return np.interp(y, [p[0] for p in k], [p[1] for p in k])

    def d(self, y):
        k = self.d_keys
        return np.interp(y, [p[0] for p in k], [p[1] for p in k])

    def xyz(self, u, y, dr=0.0):
        u = np.asarray(u, float)
        y = np.asarray(y, float)
        ph = u * math.pi / 2
        a = self.a(y) + dr
        d = self.d(y) + dr
        return a * np.sin(ph), y + self.drop, d * np.cos(ph) + self.zoff

    def proj(self, x0, yy, z):
        """torso-space point -> canvas.  The camera is at eye level, so the chest is seen a
        little from above: nearer points drop (pitch), which curves collars and rows."""
        x0 = np.asarray(x0, float)
        yy = np.asarray(yy, float)
        z = np.asarray(z, float)
        X = x0 * math.cos(self.yaw) + z * math.sin(self.yaw)
        zr = -x0 * math.sin(self.yaw) + z * math.cos(self.yaw)
        k = np.clip((yy - 1.0) / 0.35, 0, 1)            # neck base -> chest
        Y = yy + zr * math.sin(self.pitch) * k
        return np.stack([self.cx + self.s * X, self.cy + self.s * Y], -1)

    def P(self, u, y, dr=0.0):
        x0, yy, z = self.xyz(u, y, dr)
        return self.proj(x0, yy, z)

    def Puv(self, pts, dr=0.0):
        pts = g.A(pts)
        return self.P(pts[:, 0], pts[:, 1], dr)

    def u_of_x(self, x0, y):
        return np.arcsin(np.clip(np.asarray(x0) / self.a(y), -1, 1)) / (math.pi / 2)

    def sil_u(self, y, side):
        """u of the silhouette at height y on screen side (+1 right)."""
        a = float(self.a(y))
        d = float(self.d(y))
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        ph = math.atan2(a * c, d * s) if side > 0 else math.atan2(-a * c, -d * s)
        # we want the maximum of a sin(ph) c + d cos(ph) s  (side +1) -> ph = atan2(a c, d s)
        return ph / (math.pi / 2)

    def outline(self, y0=1.0, y1=2.2, n=40, side=+1, dr=0.0):
        ys = np.linspace(y0, y1, n)
        us = np.array([self.sil_u(y, side) for y in ys])
        return self.P(us, ys, dr), us, ys

    def front_x(self):
        """Canvas x of the chest centre line at shoulder height."""
        return float(self.P(0.0, 1.4)[0])


# ------------------------------------------------------------------------------------------
def draw_neck(cv, fd, torso, skin, shade="ochre", shade_k=1.0, line="ink_brown", y_bot=1.45,
              lw=1.0, adam=0.0):
    """Neck cylinder from under the jaw into the collar (drawn before the robes)."""
    H = fd.H
    s = H.s
    r = torso.neck_r
    c, sn = math.cos(H.yaw), math.sin(H.yaw)
    zc = -0.04
    far = fd.far

    def NP(xs, ys):
        xs = np.asarray(xs, float)
        ys = np.asarray(ys, float)
        X = xs * c + zc * sn
        return np.stack([H.cx + s * X, H.cy + s * ys], -1)
    ys = np.linspace(0.78, y_bot, 20)
    near = NP(np.full_like(ys, -far * r), ys)
    farl = NP(np.full_like(ys, far * r * 0.98), ys)
    poly = np.vstack([near, farl[::-1]])
    cv.fill(poly, skin, 1.0, "paint")
    # shadow under the jaw (cast-free: a graded ochre wash from the jaw line down)
    jaw = fd.lm["face_poly"]
    chin_y = fd.lm["chin"][1]
    xs = np.linspace(near[0][0], farl[0][0], 30)
    top = np.stack([xs, np.interp(xs, *_jaw_y(jaw))], 1)
    bot = top + np.array([0, s * 0.16])
    cv.band(top, bot, shade, lambda S, T: 0.42 * shade_k * (1 - T) ** 1.5, rows=6,
            alpha_xy=lambda V: np.clip(1 + 0.25 * g.vnoise(V, s * 0.05, 7), 0.5, 1.5))
    cv.band(top, top + np.array([0, s * 0.07]), shade, lambda S, T: 0.22 * shade_k * (1 - T) ** 1.2,
            rows=4)
    # sternocleidomastoid: soft diagonal from behind the ear to the pit of the neck
    p0 = NP([-far * r * 0.85], [0.78])[0]
    p1 = NP([-far * r * 0.10], [y_bot - 0.12])[0]
    cv.stroke(np.array([p0, (p0 + p1) / 2 + np.array([far * s * 0.02, 0]), p1]), s * 0.05,
              shade, 0.10 * shade_k, mode="glaze", prof="orchid")
    cv.edge(near, s * 0.07, shade, 0.30 * shade_k, side=_side_to(near, far), rows=5)
    cv.edge(farl, s * 0.05, shade, 0.22 * shade_k, side=_side_to(farl, -far), rows=5)
    w = fd.px(1.1) * lw
    # neck lines: near from behind the ear lobe, far from under the jaw
    nl = near[near[:, 1] > H.cy + s * 0.82]
    cv.stroke(nl, w, line, 0.70, prof="silk", taper=(0.35, 0.25), bleed=0.3,
              alpha_along=lambda t: g.smoothstep(0.0, 0.3, t))
    fl = farl[farl[:, 1] > chin_y + s * 0.01]
    cv.stroke(fl, w, line, 0.65, prof="silk", taper=(0.35, 0.25), bleed=0.3,
              alpha_along=lambda t: g.smoothstep(0.0, 0.3, t))
    if adam > 0:
        a = NP([far * r * 0.25], [1.02])[0]
        cv.line([a + np.array([0, -s * 0.03]), a + np.array([far * s * 0.008, 0]),
                 a + np.array([0, s * 0.025])], w * 0.8, line, alpha=0.45 * adam, prof="silk")
    return poly


def _jaw_y(poly):
    """lower envelope of the face polygon: x -> max y (for shading under the jaw)."""
    xs = np.linspace(poly[:, 0].min(), poly[:, 0].max(), 60)
    ys = []
    for x in xs:
        m = np.abs(poly[:, 0] - x) < (xs[1] - xs[0]) * 1.5
        ys.append(poly[m, 1].max() if m.any() else poly[:, 1].max())
    return xs, np.array(ys)


def _side_to(P, xdir):
    nrm = g.normals(g.resample(P, 9))[4]
    return 1 if nrm[0] * xdir > 0 else -1


# ------------------------------------------------------------------------------------------
class Robe:
    """One garment layer with a crossed collar.

    neck_u    u of the collar at the neck sides (where it leaves the neck), ~0.55-0.8
    cross_y   height where the two collar edges cross on the chest centre
    cw        collar band width (head units)
    """

    def __init__(self, color, collar, cross_y=1.42, neck_y=1.08, neck_u=0.62, cw=0.07,
                 collar_line="ink", fold_color=None, pattern=None, border=None, sleeve=None,
                 open_front=False, dr=0.0, x_cross=0.0, pattern_body=None, contour=True):
        self.color = color
        self.collar = collar
        self.cross_y = cross_y
        self.neck_y = neck_y
        self.neck_u = neck_u
        self.cw = cw
        self.line = collar_line
        self.fold = fold_color
        self.pattern = pattern
        self.border = border
        self.dr = dr
        self.x_cross = x_cross
        self.pattern_body = pattern_body      # textile motif over the garment field
        self.contour = contour


def collar_edges(T, R, y_end=2.3):
    """Top panel (wearer's left, u>0 side) and under panel inner collar edges in (u, y)."""
    # top panel: from the neck on the u>0 side, across the chest to the u<0 side, downward
    # both edges start at the side of the neck (its silhouette) and wrap round the front of the
    # neck before turning down the chest, so the collars hug the neck instead of ending flat
    ur = T.sil_u(R.neck_y - 0.03, +1) * 0.97
    ul = T.sil_u(R.neck_y - 0.03, -1) * 0.97
    top = [(ur, R.neck_y - 0.035), (0.55 * ur + 0.45 * R.neck_u, R.neck_y - 0.022),
           (R.neck_u, R.neck_y), (R.neck_u * 0.55, R.neck_y + 0.07),
           (R.x_cross + 0.0, R.cross_y), (-0.30, R.cross_y + 0.22), (-0.52, R.cross_y + 0.45),
           (-0.70, y_end)]
    under = [(ul, R.neck_y - 0.035), (0.55 * ul - 0.45 * R.neck_u, R.neck_y - 0.022),
             (-R.neck_u, R.neck_y), (-R.neck_u * 0.55, R.neck_y + 0.07),
             (R.x_cross + 0.0, R.cross_y), (0.26, R.cross_y + 0.20)]
    return np.array(top), np.array(under)


def draw_robe(cv, T, R, fd, y_bot=2.25, lw=1.0, folds=True, seed=0):
    """Fill + collar bands + folds for one layer.  Returns dict of useful curves."""
    s = T.s
    top_uv, under_uv = collar_edges(T, R, y_bot + 0.1)
    TOP = g.catmull(T.Puv(top_uv, R.dr), 10)
    UND = g.catmull(T.Puv(under_uv, R.dr), 10)
    # crossing point (index on each)
    xp = T.P(R.x_cross, R.cross_y, R.dr)
    it = int(np.argmin(np.linalg.norm(TOP - xp, axis=1)))
    iu = int(np.argmin(np.linalg.norm(UND - xp, axis=1)))
    # body outline: shoulders (silhouettes) down to the frame bottom
    far = 1 if T.yaw >= 0 else -1
    ys = np.linspace(R.neck_y, y_bot, 30)
    right = T.P(np.array([T.sil_u(y, +1) for y in ys]), ys, R.dr)
    left = T.P(np.array([T.sil_u(y, -1) for y in ys]), ys, R.dr)
    # neck points on the shoulder line
    nr = T.P(R.neck_u, R.neck_y, R.dr)
    nl = T.P(-R.neck_u, R.neck_y, R.dr)
    # shoulder line from each neck point outwards to the silhouette
    def shoulder(u0, side):
        y0 = R.neck_y - 0.035
        us = np.linspace(u0, T.sil_u(R.neck_y + 0.25, side), 12)
        yy = np.linspace(y0, R.neck_y + 0.25, 12)
        yy = y0 + (yy - y0) * (0.4 + 0.6 * np.linspace(0, 1, 12))
        return T.P(us, yy, R.dr)
    shr = shoulder(top_uv[0][0], +1)
    shl = shoulder(under_uv[0][0], -1)
    rside = right[right[:, 1] > shr[-1][1]]
    lside = left[left[:, 1] > shl[-1][1]]
    # u>0 side is screen right when the figure is frontal-ish (yaw small): screen order holds
    body = np.vstack([UND[:iu + 1], TOP[it::-1], shr, rside, lside[::-1], shl[::-1]])
    cv.fill(body, R.color, 1.0, "paint", grain=0.9)
    # body modelling: darker towards both silhouettes (分染), stronger on the shadow side
    shade_col = R.fold or pal.hexs(pal.mix(R.color, "ink", 0.45))
    cv.edge(rside, s * 0.20, shade_col, 0.35, side=_side_to(rside, -1), rows=6)
    cv.edge(lside, s * 0.20, shade_col, 0.35, side=_side_to(lside, +1), rows=6)
    # shoulder top line darkening
    cv.edge(shr, s * 0.06, shade_col, 0.25, side=1, rows=4)
    out = dict(top=TOP, under=UND, it=it, iu=iu, body=body, shr=shr, shl=shl,
               rside=rside, lside=lside, cross=xp)
    if R.pattern_body:
        textile(cv, T, R, out, seed=seed)
    if folds:
        robe_folds(cv, T, R, out, seed=seed)
    if R.contour:
        robe_contour(cv, T, R, out, seed=seed)
    return out


def robe_contour(cv, T, R, geo, seed=0):
    """Outer contour of the garment in 兰叶描 / 折芦描: the shoulder lines and the falling
    sides, each laid as two or three separate brush strokes (the brush lifts and lands again),
    swelling in the middle, pressed at the entry, dry at the tail."""
    s = T.s
    rng = np.random.default_rng(seed + 41)
    ink = pal.hexs(pal.mix(R.color, "ink", 0.82))
    w = s * 0.0150
    for sh_, side_ in ((geo["shr"], geo["rside"]), (geo["shl"], geo["lside"])):
        line = np.vstack([sh_, side_])
        line = g.resample(line, 120)
        cut = [0.0, rng.uniform(0.22, 0.32), rng.uniform(0.55, 0.68), 1.0]
        for a, b in zip(cut[:-1], cut[1:]):
            seg = g.sub(line, max(0.0, a - 0.015), min(1.0, b + 0.01))
            cv.brush(seg, w * rng.uniform(0.85, 1.1), ink, style="orchid" if a > 0 else "reed",
                     alpha=0.92, taper=(0.3, 0.7), dry=0.6)


def robe_folds(cv, T, R, geo, seed=0, n=None, ink=None):
    """Drapery (衣纹): long 兰叶描 strokes falling from the shoulders and the collar, each with a
    graded wash on its shadow side (分染); arm seams where the sleeves hang."""
    s = T.s
    rng = np.random.default_rng(seed + 17)
    dark = R.fold or pal.hexs(pal.mix(R.color, "ink", 0.40))
    line = ink or pal.hexs(pal.mix(R.color, "ink", 0.75))
    body = geo["body"]
    folds = []
    # arm/sleeve contours: the arm hangs inside the shoulder silhouette
    for side in (-1, 1):
        us = np.array([side * 0.66, side * 0.73, side * 0.77, side * 0.79])
        ys = np.array([1.36, 1.55, 1.80, 2.1])
        folds.append((us, ys, 0.9))
    # chest/body folds descending from the collar region
    for k in range(n or 5):
        u0 = rng.uniform(-0.62, 0.62)
        if abs(u0 - R.x_cross) < 0.12:
            u0 += 0.2 * np.sign(u0 - R.x_cross + 1e-6)
        y0 = rng.uniform(1.18, 1.38)
        du = rng.uniform(-0.08, 0.08)
        us = np.array([u0, u0 + du * 0.4, u0 + du])
        ys = np.array([y0, y0 + 0.25, 2.1])
        folds.append((us, ys, 0.7))
    for us, ys, w in folds:
        C = g.catmull(T.Puv(np.stack([us, ys], 1), R.dr + 0.002), 10)
        inside = g.poly_contains(body, C)
        if inside.sum() < 6:
            continue
        idx = np.where(inside)[0]
        C = C[idx[0]:idx[-1] + 1]
        side = 1 if rng.uniform() < 0.5 else -1
        cv.wash(C, s * 0.075 * w, dark, 0.55, side=side, rows=4, end_fade=0.25, passes=3)
        cv.brush(C, s * 0.0165 * w, line, style="orchid" if w < 1 else "nail", alpha=0.88,
                 taper=(0.3, 0.7), dry=0.6)
    return folds


def draw_collar(cv, T, R, geo, lw=1.0, pattern_fn=None, contact=None):
    """Collar bands of a robe layer (under panel band first, then the top panel)."""
    s = T.s
    TOP, UND, it, iu = geo["top"], geo["under"], geo["it"], geo["iu"]
    cw = R.cw * s
    # under panel collar (visible from neck to the crossing)
    U1 = UND[:iu + 1]
    Uo = _band_outer(U1, cw, T, toward=-1)
    cv.band(U1, Uo, R.collar, 1.0, mode="paint", rows=2)
    # top panel collar: from neck all the way down
    Ti = TOP
    To = _band_outer(Ti, cw, T, toward=+1)
    # back collar between the neck points is drawn separately (behind the neck)
    cv.band(Ti, To, R.collar, 1.0, mode="paint", rows=2)
    for A_, B_ in ((U1, Uo), (Ti, To)):
        cv.edge(A_, cw * 0.6, "ink", 0.18, side=_side_away(A_, B_), rows=3)
        # contact shading: the layer (or the neck) under this collar darkens where it tucks in
        cv.wash(A_, s * 0.045, contact or "ochre", 0.30, side=-_side_away(A_, B_), rows=4,
                end_fade=0.12, passes=2)
        if pattern_fn:
            pattern_fn(cv, A_, B_)
    w = s * 0.0068 * lw
    cv.brush(U1, w, R.line, style="iron", alpha=0.9)
    cv.brush(Uo, w * 0.9, R.line, style="iron", alpha=0.85)
    cv.brush(Ti, w * 1.1, R.line, style="reed", alpha=0.92, dry=0.3)
    cv.brush(To, w * 0.95, R.line, style="iron", alpha=0.85)
    return Ti, To, U1, Uo


def _band_outer(P, w, T, toward):
    """Offset P by w to the side pointing away from the V opening (towards u*toward)."""
    nrm = g.normals(P)
    mid = len(P) // 2
    # the V opening is around the chest centre line; outer side is away from it
    cxs = T.front_x()
    test = P[mid] + nrm[mid] * 3
    d0 = abs(P[mid][0] - cxs)
    sign = 1
    # top panel's outer side is towards +x on screen for its upper part; decide by direction
    if toward > 0:
        sign = 1 if nrm[mid][0] > 0 else -1
    else:
        sign = 1 if nrm[mid][0] < 0 else -1
    return P + nrm * (sign * w)


def _side_away(A_, B_):
    nrm = g.normals(A_)
    m = len(A_) // 2
    return 1 if np.dot(B_[m] - A_[m], nrm[m]) > 0 else -1


# ------------------------------------------------------------------------------------------
def shawl(cv, T, color="malachite_p", alpha=0.75, width=0.17, pattern="gold", seed=0):
    """披帛: a long light silk stole draped behind the neck and over both shoulders."""
    s = T.s
    rng = np.random.default_rng(seed + 3)
    far = 1 if T.yaw >= 0 else -1
    dark = pal.hexs(pal.mix(color, "ink", 0.35))
    out = []
    for side in (far, -far):
        # centreline: behind the neck, over the shoulder, down the outer arm
        pts = [(side * 0.98, 1.13), (side * 0.80, 1.17), (side * 0.64, 1.32),
               (side * 0.66, 1.60), (side * 0.70, 2.1)]
        C = g.catmull(np.array(pts), 10)
        tt = np.linspace(0, 1, len(C))
        dr = 0.03 + 0.05 * tt
        wk = g.smoothstep(0.0, 0.12, tt) * 0.85 + 0.15        # tucked start behind the shoulder
        L = []
        R = []
        for (u, y), d, k in zip(C, dr, wk):
            L.append(T.P(u - side * width * 0.5 * k, y - 0.01, d))
            R.append(T.P(u + side * width * 0.6 * k, y + 0.02, d + 0.02))
        L = np.array(L)
        R = np.array(R)
        # only the part in front of the body silhouette matters; draw whole band (light)
        cv.band(L, R, color, alpha, mode="paint", rows=3)
        cv.band(L, R, dark, lambda S, Tt: 0.35 * (np.abs(Tt - 0.5) * 2) ** 2, rows=4)
        # folds along the stole
        for k in range(3):
            t = 0.25 + 0.25 * k
            F_ = L * (1 - t) + R * t
            cv.stroke(g.sub(F_, 0.2, 0.95), s * 0.0035, dark, 0.6, prof="orchid")
        if pattern:
            n = int(g.length(L) / (s * 0.05))
            for k in range(n):
                u = (k + 0.5) / n
                c = (g.at(L, u) + g.at(R, u)) / 2
                cv.dot(c, s * 0.006, pattern, 0.85)
        cv.stroke(L, s * 0.0045, "ink", 0.85, prof="iron")
        cv.stroke(R, s * 0.0045, "ink", 0.85, prof="iron")
        out.append((L, R))
    return out


def necklace(cv, T, gold="gold", pendant="malachite_l", pearls=True, y_c=1.36, bead="white"):
    """璎珞: gold chain with pearls hanging in an arc on the chest, a jade pendant."""
    s = T.s
    us = np.linspace(-0.42, 0.42, 40)
    ys = 1.12 + (y_c - 1.12) * (1 - (us / 0.42) ** 2)
    C = T.Puv(np.stack([us, ys], 1), 0.06)
    cv.stroke(C, s * 0.007, gold, 1.0, prof="flat", caps=False)
    cv.stroke(C, s * 0.002, "gold_d", 0.9, prof="flat", caps=False)
    if pearls:
        for k in range(1, 18):
            p = g.at(C, k / 18)
            cv.dot(p + [0, s * 0.008], s * 0.0075, bead, 1.0)
            cv.dot(p + [s * 0.002, s * 0.010], s * 0.003, "#bdb4a5", 0.8)
    c = T.P(0.0, y_c + 0.05, 0.07)
    P = np.array([c + [0, -s * 0.03], c + [s * 0.025, 0], c + [0, s * 0.04], c + [-s * 0.025, 0]])
    cv.fill(g.catmull(P, 6, closed=True), pendant, 1.0, "paint")
    cv.blob(c + [-s * 0.006, -s * 0.008], s * 0.01, s * 0.008, "white", 0.6, mode="paint")
    cv.stroke(np.vstack([g.catmull(P, 6, closed=True), P[:1]]), s * 0.004, gold, 1.0, prof="flat", caps=False)


# ------------------------------------------------------------------------------------------
# textiles: motifs woven or painted in gold over the garment field (sparse: they must read as
# pattern at 96 px, not as noise)


def _chest_circle(T, x0, y, r, dr, n=24, squash=0.95):
    """Circle of radius r (head units) centred at chest coordinates (x0, y) -> canvas pts."""
    ph = np.linspace(0, 2 * math.pi, n, endpoint=False)
    xs = x0 + r * np.cos(ph)
    ys = y + r * np.sin(ph) * squash
    us = T.u_of_x(xs, ys)
    return T.P(us, ys, dr)


def textile(cv, T, R, geo, seed=0):
    """Pattern over the robe field: 'roundels' 团花, 'flowers' 散花 (scattered gold florets),
    'clouds' 云纹 or 'damask' 暗花 (tone-on-tone roundels)."""
    p = dict(R.pattern_body)
    kind = p.get("kind", "roundels")
    col = p.get("color", "gold")
    al = p.get("alpha", 0.9)
    size = p.get("size", 0.050)
    per = p.get("period", 0.27)
    s = T.s
    rng = np.random.default_rng(seed + p.get("seed", 3))
    body = geo["body"]
    if kind == "damask":
        col = pal.hexs(pal.mix(R.color, "white", 0.30))
        al = p.get("alpha", 0.45)
    dark = pal.hexs(pal.mix(col, "ink", 0.45))
    dr = R.dr + 0.006
    y = 1.28
    row = 0
    while y < 2.25:
        a = float(T.a(y))
        x = -a + per * (0.25 + 0.5 * (row % 2)) + rng.uniform(-0.03, 0.03)
        while x < a:
            xx = x + rng.uniform(-0.025, 0.025)
            yy = y + rng.uniform(-0.02, 0.02)
            x += per
            if abs(xx) > a * 0.93:
                continue
            c = T.P(T.u_of_x(xx, yy), yy, dr)
            if not g.poly_contains(body, c[None])[0]:
                continue
            # skip motifs on the far, foreshortened flank (they would turn to smears)
            uu = float(T.u_of_x(xx, yy))
            if abs(uu - (T.sil_u(yy, 1) + T.sil_u(yy, -1)) / 2) > 0.80:
                continue
            r = size * rng.uniform(0.9, 1.1)
            if kind in ("roundels", "damask"):
                # 团花: a thin ring round an eight-petal flower (petals as small brush leaves)
                ring = _chest_circle(T, xx, yy, r, dr, 28)
                cv.stroke(np.vstack([ring, ring[:1]]), s * r * 0.11, col, al, prof="flat",
                          caps=False, noise=0.10, grain=1.0)
                rot = rng.uniform(0, 2 * math.pi)
                for k in range(8):
                    ang = rot + k * math.pi / 4
                    a0 = (xx + 0.16 * r * math.cos(ang), yy + 0.16 * r * math.sin(ang) * 0.95)
                    a1 = (xx + 0.70 * r * math.cos(ang), yy + 0.70 * r * math.sin(ang) * 0.95)
                    P = T.P(T.u_of_x(np.array([a0[0], a1[0]]), np.array([a0[1], a1[1]])),
                            np.array([a0[1], a1[1]]), dr)
                    cv.stroke(P, s * r * (0.30 if k % 2 == 0 else 0.20), col, al, prof="orchid",
                              taper=(0.45, 0.55), noise=0.08, grain=1.0)
                cv.dot(c, s * r * 0.14, dark if kind == "roundels" else col, al, grain=1.0)
            elif kind == "flowers":
                rot = rng.uniform(0, 2 * math.pi)
                for k in range(5):
                    ang = rot + k * 2 * math.pi / 5
                    pc = T.P(T.u_of_x(xx + 0.42 * r * math.cos(ang), yy), yy + 0.42 * r * math.sin(ang) * 0.95, dr)
                    cv.dot(pc, s * r * 0.30, col, al, grain=1.0)
                cv.dot(c, s * r * 0.20, p.get("heart", "cinnabar"), al, grain=1.0)
            elif kind == "clouds":
                # 如意云: a small double scroll
                for sgn in (-1, 1):
                    ph = np.linspace(0, 1.6 * math.pi, 14)
                    rr = r * 0.45 * (1 - 0.35 * ph / (1.6 * math.pi))
                    xs = xx + sgn * (r * 0.42 + rr * np.cos(ph + (0 if sgn > 0 else math.pi)) * -sgn)
                    ys = yy + rr * np.sin(ph) * 0.9
                    P = T.P(T.u_of_x(xs, ys), ys, dr)
                    cv.stroke(P, s * r * 0.15, col, al, prof="silk", grain=1.0)
                base = np.array([(xx - r * 0.85, yy + r * 0.35), (xx, yy + r * 0.55), (xx + r * 0.85, yy + r * 0.35)])
                Pb = T.P(T.u_of_x(base[:, 0], base[:, 1]), base[:, 1], dr)
                cv.stroke(g.catmull(Pb, 6), s * r * 0.15, col, al, prof="silk", grain=1.0)
        y += per * 0.86
        row += 1


def kasaya(cv, T, color="cinnabar", border=None, side=1, y_bot=2.3):
    """袈裟: the patchwork mantle (田相 grid) over one shoulder, fastened on the chest with a
    ring; the other shoulder shows the under-robe."""
    s = T.s
    border = border or pal.hexs(pal.mix(color, "ink", 0.35))
    sd = side
    # outline in (u, y): over the wearer's shoulder (u*sd > 0), diagonally down to under the
    # other arm
    u_out_top = T.sil_u(1.30, sd)
    pts = [(sd * 0.30, 1.10), (sd * 0.55, 1.13), (u_out_top * 1.02, 1.30)]
    ys = np.linspace(1.35, y_bot, 10)
    pts += [(T.sil_u(y, sd) * 1.02, y) for y in ys]
    ys2 = np.linspace(y_bot, 1.62, 6)
    pts += [(T.sil_u(y, -sd) * 1.02, y) for y in ys2]
    pts += [(-sd * 0.55, 1.50), (-sd * 0.10, 1.32), (sd * 0.15, 1.16)]
    uv = np.array(pts)
    poly = T.Puv(uv, 0.03)
    cv.fill(poly, color, 1.0, "paint", grain=1.0)
    dark = pal.hexs(pal.mix(color, "ink", 0.45))
    # patch grid: strips (条) of a darker tone with stitched seams
    x_seams = np.arange(-1.0, 1.01, 0.28)
    for x0 in x_seams:
        ys_ = np.linspace(1.15, y_bot, 30)
        a = T.a(ys_)
        m = np.abs(x0) < a * 0.98
        if m.sum() < 4:
            continue
        P = T.P(T.u_of_x(np.full(m.sum(), x0), ys_[m]), ys_[m], 0.032)
        inside = g.poly_contains(poly, P)
        for seg in _runs(P, inside):
            cv.band(seg, seg + np.array([s * 0.022, 0]), border, 0.9, mode="paint", rows=1, grain=1.0)
            cv.stroke(seg, s * 0.004, dark, 0.8, prof="iron", noise=0.08)
    for y0 in np.arange(1.30, y_bot, 0.24):
        a = float(T.a(y0))
        xs_ = np.linspace(-a * 0.98, a * 0.98, 30)
        P = T.P(T.u_of_x(xs_, np.full_like(xs_, y0)), np.full_like(xs_, y0), 0.032)
        inside = g.poly_contains(poly, P)
        for seg in _runs(P, inside):
            cv.band(seg, seg + np.array([0, s * 0.020]), border, 0.9, mode="paint", rows=1, grain=1.0)
            cv.stroke(seg, s * 0.004, dark, 0.8, prof="iron", noise=0.08)
    # broad border along the diagonal edge and folds
    edge_uv = np.array([(sd * 0.15, 1.16), (-sd * 0.10, 1.32), (-sd * 0.55, 1.50),
                        (T.sil_u(1.62, -sd), 1.62)])
    E = g.catmull(T.Puv(edge_uv, 0.034), 8)
    E2 = E + np.array([0, s * 0.045])
    cv.band(E, E2, border, 1.0, mode="paint", rows=2, grain=1.0)
    cv.edge(E2, s * 0.06, "ink", 0.30, side=1 if g.normals(E2)[len(E2) // 2][1] > 0 else -1, rows=4)
    cv.brush(E, s * 0.009, "ink", style="reed", alpha=0.9)
    cv.brush(E2, s * 0.007, "ink", style="iron", alpha=0.8)
    # ring fastener (钩环) on the chest
    c = T.P(-sd * 0.30, 1.47, 0.05)
    ring = g.ellipse(c, s * 0.032, s * 0.032, n=24)
    cv.stroke(np.vstack([ring, ring[:1]]), s * 0.009, "gold", 1.0, prof="flat", caps=False)
    cv.stroke(np.vstack([ring, ring[:1]]), s * 0.003, "gold_d", 0.9, prof="flat", caps=False)
    cv.stroke(np.vstack([poly, poly[:1]]), s * 0.009, "ink", 0.85, prof="orchid", noise=0.15,
              caps=False)
    return poly


def _runs(P, mask):
    out, cur = [], []
    for p, m in zip(P, mask):
        if m:
            cur.append(p)
        elif cur:
            if len(cur) > 2:
                out.append(np.array(cur))
            cur = []
    if len(cur) > 2:
        out.append(np.array(cur))
    return out


def mala(cv, T, bead="#5a3a26", y_c=1.62, n=26, guru="#8e2a22"):
    """念珠: a long string of large prayer beads round the neck, a guru bead and tassel."""
    s = T.s
    us = np.linspace(-0.55, 0.55, n)
    ys = 1.10 + (y_c - 1.10) * (1 - (us / 0.55) ** 2) ** 0.9
    C = T.Puv(np.stack([us, ys], 1), 0.07)
    light = pal.hexs(pal.mix(bead, "white", 0.45))
    for k, p in enumerate(C):
        r = s * 0.016
        cv.dot(p, r, bead, 1.0, grain=0.8)
        cv.dot(p + np.array([-r * 0.35, -r * 0.35]), r * 0.35, light, 0.8)
        cv.stroke(np.vstack([g.ellipse(p, r, r, n=14), g.ellipse(p, r, r, n=14)[:1]]), s * 0.0035,
                  "ink", 0.85, prof="flat", caps=False)
    bot = C[n // 2] + np.array([0, s * 0.03])
    cv.dot(bot, s * 0.022, guru, 1.0)
    cv.dot(bot + np.array([-s * 0.007, -s * 0.007]), s * 0.007, "white", 0.6)
    for k in range(9):
        a = bot + np.array([0, s * 0.02])
        b = a + np.array([(k - 4) * s * 0.006, s * 0.09])
        cv.stroke(np.array([a, (a + b) / 2, b]), s * 0.004, guru, 0.9, prof="hair")
