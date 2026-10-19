"""Analytic bust geometry shared by the Blender stage (meshes) and the 2D stage (feature wrap).

Units are *head units* (crown-to-chin = 1.0; Blender scales by ``HEAD_M`` metres).  Head-local
axes: +X = viewer's right when the face looks straight at the camera, -Y = forward (the face
looks along -Y), +Z = up; origin on the midline at the eye line.

The head and the torso are lofts of horizontal slices.  Each slice is two superellipse halves:

    front half  x = W sgn(s)|s|^(2/nf),  y = Y0 - (Y0 - F)|c|^(2/nf)     (c = cos t >= 0)
    back half   x = W sgn(s)|s|^(2/nb),  y = Y0 + (B - Y0)|c|^(2/nb)

with W (half width), F (front y), B (back y), Y0 (y of the widest point), nf / nb (squareness)
given as smooth profiles over z.  Because the front half is a function x -> y, the face surface
y = front(x, z) is closed form, so 2D strokes are wrapped onto the exact 3D head.
"""

import math

import numpy as np

HEAD_M = 0.232          # metres per head unit


# =============================================================================================
# interpolation
# =============================================================================================
def pchip_slopes(xs, ys):
    """Fritsch-Carlson slopes of a monotone cubic through (xs, ys) (xs ascending)."""
    xs = np.asarray(xs, np.float64)
    ys = np.asarray(ys, np.float64)
    h = np.diff(xs)
    d = np.diff(ys) / h
    m = np.zeros_like(ys)
    for k in range(1, len(xs) - 1):
        if d[k - 1] * d[k] <= 0:
            m[k] = 0.0
        else:
            w1, w2 = 2 * h[k] + h[k - 1], h[k] + 2 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])
    m[0], m[-1] = d[0], d[-1]
    return m


def pchip_eval(xs, ys, m, x):
    xs = np.asarray(xs, np.float64)
    x = np.clip(np.asarray(x, np.float64), xs[0], xs[-1])
    h = np.diff(xs)
    i = np.clip(np.searchsorted(xs, x) - 1, 0, len(xs) - 2)
    t = (x - xs[i]) / h[i]
    h00 = (1 + 2 * t) * (1 - t) ** 2
    h10 = t * (1 - t) ** 2
    h01 = t * t * (3 - 2 * t)
    h11 = t * t * (t - 1)
    return h00 * ys[i] + h10 * h[i] * m[i] + h01 * ys[i + 1] + h11 * h[i] * m[i + 1]


def pchip(xs, ys, x):
    """Monotone cubic (Fritsch-Carlson) interpolation; xs ascending; clamps outside."""
    ys = np.asarray(ys, np.float64)
    return pchip_eval(xs, ys, pchip_slopes(xs, ys), x)


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, np.float64) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# =============================================================================================
# slices
# =============================================================================================
class Loft:
    """A loft of superellipse slices given by control tables over z (ascending)."""

    def __init__(self, z, W, F, B, Y0, nf, nb):
        self.z = np.asarray(z, np.float64)
        self.tab = dict(W=np.asarray(W, float), F=np.asarray(F, float), B=np.asarray(B, float),
                        Y0=np.asarray(Y0, float), nf=np.asarray(nf, float),
                        nb=np.asarray(nb, float))
        self.slopes = {k: pchip_slopes(self.z, v) for k, v in self.tab.items()}

    def params(self, z):
        return {k: pchip_eval(self.z, v, self.slopes[k], z) for k, v in self.tab.items()}

    def ring(self, z, n=96):
        """(n, 3) points of the slice at height z; t = 0 at the front, increasing towards +X."""
        p = self.params(z)
        t = np.linspace(0, 2 * math.pi, n, endpoint=False)
        s, c = np.sin(t), np.cos(t)
        front = c >= 0
        ex = np.where(front, 2.0 / p["nf"], 2.0 / p["nb"])
        x = p["W"] * np.sign(s) * np.abs(s) ** ex
        y = np.where(front, p["Y0"] - (p["Y0"] - p["F"]) * np.abs(c) ** ex,
                     p["Y0"] + (p["B"] - p["Y0"]) * np.abs(c) ** ex)
        return np.stack([x, y, np.full(n, float(z))], -1)

    def grid(self, zs, n=96):
        return np.stack([self.ring(z, n) for z in zs], 0)

    def point(self, z, t):
        """Surface point(s) at height z and slice parameter t (arrays broadcast)."""
        z, t = np.broadcast_arrays(np.asarray(z, np.float64), np.asarray(t, np.float64))
        p = self.params(z)
        s, c = np.sin(t), np.cos(t)
        front = c >= 0
        ex = np.where(front, 2.0 / p["nf"], 2.0 / p["nb"])
        x = p["W"] * np.sign(s) * np.abs(s) ** ex
        y = np.where(front, p["Y0"] - (p["Y0"] - p["F"]) * np.abs(c) ** ex,
                     p["Y0"] + (p["B"] - p["Y0"]) * np.abs(c) ** ex)
        return np.stack([x, y, z], -1)

    def normal(self, z, t, eps=1e-3):
        """Outward unit normal(s) at (z, t)."""
        Pt = self.point(z, np.asarray(t) + eps) - self.point(z, np.asarray(t) - eps)
        Pz = self.point(np.asarray(z) + eps, t) - self.point(np.asarray(z) - eps, t)
        n = np.cross(Pt, Pz)
        n /= np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-12)
        # outward: away from the slice centre
        p = self.params(z)
        P = self.point(z, t)
        out = P - np.stack([np.zeros_like(p["Y0"]), p["Y0"], P[..., 2]], -1)
        sgn = np.sign((n * out).sum(-1, keepdims=True) + 1e-12)
        return n * sgn

    def t_of_x(self, x, z, front=True):
        """Slice parameter of the surface point with this x at height z (front or back half)."""
        p = self.params(z)
        a = np.clip(np.asarray(x, np.float64) / np.maximum(p["W"], 1e-6), -1, 1)
        ex = p["nf"] / 2.0 if front else p["nb"] / 2.0
        s = np.sign(a) * np.abs(a) ** ex
        t = np.arcsin(np.clip(s, -1, 1))
        return t if front else np.pi - t

    def front(self, x, z):
        """y of the front surface at (x, z) (nan outside the silhouette)."""
        x = np.asarray(x, np.float64)
        p = self.params(z)
        a = np.clip(np.abs(x) / np.maximum(p["W"], 1e-6), 0, 1)
        s = a ** (p["nf"] / 2.0)
        c = np.sqrt(np.clip(1 - s * s, 0, 1))
        y = p["Y0"] - (p["Y0"] - p["F"]) * c ** (2.0 / p["nf"])
        return np.where(np.abs(x) <= p["W"], y, np.nan)

    def width(self, z):
        return self.params(z)["W"]


# =============================================================================================
# head
# =============================================================================================
HEAD_DEFAULT = dict(
    skull_w=0.335,       # half width of the cranium
    temple_w=0.318,      # half width at the brow line
    cheek_w=0.322,       # half width over the cheekbones (z -0.10)
    jaw_w=0.262,         # half width at the jaw angle
    chin_w=0.115,        # half width of the chin
    chin_z=-0.5,         # bottom of the chin
    jaw_z=-0.29,         # height of the jaw angle
    face_d=0.405,        # forward reach of the face plane (y = -face_d)
    chin_d=0.375,        # forward reach of the chin
    back=0.45,           # back of the skull
    flat=2.5,            # squareness of the face front (2 = round)
    jaw_sq=2.3,          # squareness at the jaw (higher = squarer jaw)
    crown=0.5,
    brow_ridge=0.010,    # brow ridge bulge
    cheek_full=0.0,      # + fuller (young / ladies), - gaunt
)


def head_loft(hp=None):
    h = dict(HEAD_DEFAULT, **(hp or {}))
    cz, jz = h["chin_z"], h["jaw_z"]
    fd, cd = h["face_d"], h["chin_d"]
    cw, jw, chw = h["cheek_w"], h["jaw_w"], h["chin_w"]
    full = h["cheek_full"]
    jt = (cz + jz) * 0.5
    # control heights from the chin to the top of the face; the dome is added below
    z = [cz, cz + 0.012, cz + 0.035, cz + 0.08, cz + 0.135, jz, -0.19, -0.09, 0.0, 0.07, 0.14]
    W = [0.065, chw * 0.88, chw * 1.04, chw + (jw - chw) * 0.42, chw + (jw - chw) * 0.80 + full * 0.25,
         jw + full * 0.5, cw - 0.022 + full * 0.6, cw + full * 0.3, cw - 0.004, h["temple_w"],
         h["skull_w"]]
    F = [-cd + 0.065, -cd + 0.026, -cd + 0.004, -cd - 0.006, -cd - 0.014, -fd + 0.012,
         -fd + 0.004, -fd + 0.006, -fd + 0.004, -fd - h["brow_ridge"], -fd + 0.012]
    B = [-cd + 0.12, -cd + 0.17, -0.17, -0.09, 0.02, 0.12, 0.25, 0.34, 0.40, h["back"], h["back"]]
    Y0 = [-cd + 0.095, -cd + 0.10, -0.165, -0.09, -0.02, 0.05, 0.03, 0.0, 0.0, 0.03, 0.04]
    nf = [2.0, 2.0, 2.05, 2.1, h["jaw_sq"], h["jaw_sq"], h["flat"] - 0.05, h["flat"], h["flat"],
          h["flat"], 2.3]
    nb = [2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.1, 2.2, 2.2, 2.3, 2.3]
    # dome: superellipse cap from the top control (z0) to the crown
    z0 = z[-1]
    crown = h["crown"]
    yc = 0.05
    for zz in np.linspace(z0 + 0.04, crown, 10):
        t = (zz - z0) / (crown - z0)
        k = max(0.0, 1 - t ** 2.3) ** (1 / 2.3)
        k = max(k, 0.015)
        z.append(zz)
        W.append(h["skull_w"] * k)
        F.append(yc + (-fd + 0.012 - yc) * k ** 0.8)
        B.append(yc + (h["back"] - yc) * k)
        Y0.append(yc - 0.01 * k)
        nf.append(2.3)
        nb.append(2.3)
    return Loft(z, W, F, B, Y0, nf, nb)


def neck_loft(nk=None):
    """Neck tube (head units, body space): from inside the jaw down into the chest."""
    n = dict(w=0.25, d=0.21, top=-0.18, bottom=-1.05, lean=0.06, yc=0.11)
    n.update(nk or {})
    z = np.linspace(n["bottom"], n["top"], 6)
    t = (z - n["bottom"]) / (n["top"] - n["bottom"])
    flare = 1 + 0.35 * (1 - t) ** 3          # the neck flares into the trapezius
    W = n["w"] * flare
    yc = n["yc"] + n["lean"] * (t - 0.5)
    F = yc - n["d"] * (1 + 0.15 * (1 - t) ** 3)
    B = yc + n["d"] * flare * 1.05
    return Loft(z, W, F, B, yc, np.full(6, 2.1), np.full(6, 2.1))


TORSO_DEFAULT = dict(
    shoulder_w=1.0,      # half width at the shoulder points
    shoulder_z=-1.08,    # height of the shoulder points
    neck_base=-0.70,     # top of the trapezius at the neck (the collar sits here)
    slope=0.5,           # 0 = square shoulders, 1 = very sloped
    chest_d=0.44,        # forward reach of the chest
    back_d=0.52,
    bulk=1.0,            # overall girth multiplier
    square=2.8,
    neck_w=0.25,         # half width of the torso top ring (round the neck)
)


def torso_loft(tp=None):
    t = dict(TORSO_DEFAULT, **(tp or {}))
    sw, sz, nb_ = t["shoulder_w"] * t["bulk"], t["shoulder_z"], t["neck_base"]
    sl = t["slope"]
    cd, bd = t["chest_d"] * t["bulk"], t["back_d"] * t["bulk"]
    nw = t["neck_w"]
    # heights from below the frame up to the neck base
    z = [-2.2, -1.6, -1.32, sz - 0.07, sz + 0.02, sz + 0.09 + 0.03 * (1 - sl),
         nb_ - 0.17 + 0.03 * sl, nb_ - 0.07, nb_]
    W = [sw * 1.02, sw * 1.04, sw * 1.03, sw * 1.0, sw * 0.93, sw * 0.78, sw * 0.50,
         nw * 1.25, nw]
    F = [-cd + 0.02, -cd, -cd - 0.005, -cd + 0.02, -cd + 0.06, -cd + 0.12, -0.25, -0.16, -0.11]
    B = [bd, bd, bd, bd - 0.02, bd - 0.05, bd - 0.08, 0.42, 0.36, 0.33]
    Y0 = [0.08, 0.08, 0.08, 0.09, 0.10, 0.10, 0.10, 0.10, 0.11]
    nf = [t["square"]] * 6 + [2.4, 2.2, 2.1]
    nb = [2.6] * 6 + [2.3, 2.2, 2.1]
    return Loft(z, W, F, B, Y0, nf, nb)


# =============================================================================================
# face landmarks (canonical, before per-character offsets) - head units, head-local x / z
# =============================================================================================
def default_landmarks():
    return dict(
        eye_x=0.142, eye_z=0.0,           # eye centres at +-eye_x
        brow_z=0.085,
        nose_z=-0.185,                    # nose tip height
        mouth_z=-0.285,
        chin_z=-0.5,
        hair_z=0.30,                      # hairline at the midline
        ear_z=(-0.21, 0.07),              # ear bottom / top
    )


def ear_outline(n=48, h=0.27, w=0.125):
    """Ear outline in the ear plane (a = forwards/backwards, b = up), closed, starting at the
    top of the attachment.  Returns (n, 2)."""
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    # C-shaped: wide rounded top, narrower lobe, attachment edge straighter
    a = 0.5 * w * (np.sin(t) * (1 + 0.18 * np.cos(t))) + 0.18 * w
    b = 0.5 * h * np.cos(t) * (1 - 0.06 * np.sin(t))
    # lobe a bit narrower and fuller (fortune ears): pull the bottom part forward
    lob = smoothstep(-0.1, -0.5, np.cos(t))
    a = a - lob * 0.12 * w * np.maximum(np.sin(t), 0)
    return np.stack([a, b], -1)
