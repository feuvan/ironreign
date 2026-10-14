"""Facial features drawn as brush decals on the head (gongbi canon).

All features are designed in 2D *face coordinates* (x lateral, z up, metres, the frontal head
frame) and ray-projected onto the head, so the 3/4 view foreshortens them correctly.  Each eye and
brow is built in an *eye-local* frame (u outward from the nose, v up, centimetres in the specs)
and mirrored for the two sides.

Canon (classical figure painting, not a caricature): eyes are long almonds with a clearly drawn,
pressure-varied upper lid line, a faint lower lid, a large dark iris with a pupil and a tiny
highlight (点睛); brows are washed then hair-stroked; lips are rouged with a darker parting line.
"""

import math

import numpy as np

import geo
import shade
from palette import hex_rgb, mix

CM = 0.01


def _local_to_face(side, origin, pts):
    pts = np.asarray(pts, np.float64) * CM
    return np.stack([origin[0] + side * pts[:, 0], origin[1] + pts[:, 1]], 1)


def _bump(t, peak, q=0.85):
    p = math.log(0.5) / math.log(max(1e-3, min(0.999, peak)))
    return np.sin(math.pi * np.clip(t, 0, 1) ** p) ** q


# ---------------------------------------------------------------------------------- shapes
def eye_curves(e, n=40):
    """Upper and lower lid curves (eye-local cm), inner corner -> outer corner."""
    W, Hu, Hl, tilt = e["W"], e["Hu"], e["Hl"], e.get("tilt", 0.0)
    t = np.linspace(0, 1, n)
    u = -W / 2 + t * W
    chord = t * tilt
    up = chord + Hu * _bump(t, e.get("peak_u", 0.42), e.get("q_u", 0.8))
    lo = chord - Hl * _bump(t, e.get("peak_l", 0.58), e.get("q_l", 0.9))
    # the inner corner (眼头) dips a little: a pointed tear-duct corner
    dip = e.get("inner_dip", 0.06) * np.exp(-(t / 0.08) ** 2)
    up -= dip
    lo -= dip
    return np.stack([u, up], 1), np.stack([u, lo], 1)


def upper_lid_stroke(e, up):
    """Upper-lid line + tail flick beyond the outer corner (phoenix eyes)."""
    pts = up[1:]
    tail = e.get("tail", 0.25)
    if tail > 0:
        d = pts[-1] - pts[-4]
        d /= np.linalg.norm(d)
        ang = math.radians(e.get("tail_rise", 12.0))
        R = np.array([[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]])
        d2 = R @ d
        ext = [pts[-1] + d2 * tail * k for k in np.linspace(0.15, 1.0, 6)]
        pts = np.vstack([pts, ext])
    return geo.resample(pts, 48)


# ------------------------------------------------------------------------------- materials
SKIN_SHADE = dict(ao=0.7, edge=0.5, tint="#B97B62")


def _skin_out(nb, color, a, ink=0.0):
    """Output for decals painted on skin: where the decal is transparent (a < 1) it carries
    the skin's own 晕染 (edge darkening + AO strength) so no patch shows."""
    st = shade.shade_term(nb, SKIN_SHADE["ao"], 0.025, SKIN_SHADE["edge"], 0.42)
    inv = nb.math("SUBTRACT", 1.0, a)
    nb.out(color, shade.rgb(SKIN_SHADE["tint"]), nb.math("MULTIPLY", st, inv), ink, 2.0,
           aok=nb.math("MULTIPLY", inv, SKIN_SHADE["ao"]))


def eye_material(name, e, iris_c, skin_cfg):
    """Sclera + iris + pupil + highlight in eye-local cm UV space."""
    m = shade._mat(name)
    nb = shade.NB(m)
    uv = nb.uv()
    s = nb.sep(uv)
    u, v = s[0], s[1]
    r = e["iris_r"]
    ic = (iris_c[0], iris_c[1], 0.0)
    d = nb.math("DIVIDE", nb.vmath("DISTANCE", uv, ic), r)
    white = shade.rgb(e.get("white", "#EFE7D8"))
    shadow = nb.math("MULTIPLY", nb.smooth(v, e["Hu"] * 0.15, e["Hu"] * 0.95), 0.42)
    col_w = nb.mix(shadow, white, shade.rgb("#B5A898"))
    caruncle = nb.blob(nb.comb(u, v, 0.0), (-e["W"] / 2 + 0.22, 0.0, 0.0), (0.26, 0.2, 1.0))
    col_w = nb.mix(nb.math("MULTIPLY", caruncle, 0.8), col_w, shade.rgb("#D99A8C"))
    # iris: warm dark-brown ring, darker limbal edge, black pupil, lid shadow on top
    ring = nb.smooth(d, 0.55, 0.97)
    col_i = nb.mix(ring, shade.rgb(e.get("iris_col", "#3E2B20")), shade.rgb("#15100D"))
    col_i = nb.mix(nb.math("SUBTRACT", 1.0, nb.smooth(d, 0.36, 0.46)), col_i,
                   shade.rgb("#0B0908"))
    top = nb.smooth(nb.math("SUBTRACT", v, iris_c[1]), 0.0, r * 0.9)
    col_i = nb.mix(nb.math("MULTIPLY", top, 0.55), col_i, shade.rgb("#0B0908"))
    a_i = nb.math("SUBTRACT", 1.0, nb.smooth(d, 0.95, 1.04))
    col = nb.mix(a_i, col_w, col_i)
    # highlight (点睛): a tiny clean dot up-left of the pupil
    hc = (iris_c[0] + e.get("hl_dx", -0.3) * r, iris_c[1] + 0.34 * r, 0.0)
    hd = nb.vmath("DISTANCE", uv, hc)
    h = nb.math("SUBTRACT", 1.0, nb.smooth(hd, r * 0.12, r * 0.2))
    col = nb.mix(h, col, shade.rgb("#FBF8F0"))
    nb.out(col, col, 0.0, 0.0, 2.0)
    return m


def stroke_material(name, color, soft=0.0, skin_cfg=None, dry=0.0):
    """Decal ink stroke.  ``soft`` > 0 feathers the stroke edges into the skin paint."""
    m = shade._mat(name)
    nb = shade.NB(m)
    c = shade.rgb(color)
    if soft > 0 and skin_cfg is not None:
        uv = nb.sep(nb.uv())
        a = nb.math("MULTIPLY", nb.smooth(uv[1], 0.0, soft), nb.smooth(nb.math("SUBTRACT", 1.0,
                                                                                uv[1]), 0.0, soft))
        if dry > 0:
            a = nb.math("MULTIPLY", a, nb.math("ADD", 1.0 - dry, nb.math(
                "MULTIPLY", nb.noise(nb.comb(nb.math("MULTIPLY", uv[0], 30.0),
                                             nb.math("MULTIPLY", uv[1], 3.0), 0.0), 4.0), dry)))
        sk = shade.skin_paint(nb, **skin_cfg)
        c = nb.mix(a, sk, c)
        _skin_out(nb, c, a, ink=a)
    else:
        nb.out(c, c, 0.0, 1.0, 2.0)
    return m


def brow_material(name, color, length_cm, skin_cfg, head_soft=0.3, hair=0.55, sharp=0.18,
                  streak=None):
    """Brow: an ink wash in the brow shape, hair streaks along it, a soft head and crisp tail.
    ``streak``: a second colour for the hair strokes (white brows: grey wash + white hairs)."""
    m = shade._mat(name)
    nb = shade.NB(m)
    uv = nb.sep(nb.uv())
    u, v = uv[0], uv[1]
    a = nb.math("MULTIPLY", nb.smooth(v, 0.0, sharp), nb.smooth(nb.math("SUBTRACT", 1.0, v),
                                                               0.0, sharp))
    a = nb.math("MULTIPLY", a, nb.maprange(nb.smooth(u, 0.0, head_soft), 0, 1, 0.35, 1.0))
    # hair streaks: noise stretched along the brow, slightly slanted
    q = nb.comb(nb.math("ADD", nb.math("MULTIPLY", u, length_cm * 1.2),
                        nb.math("MULTIPLY", v, 0.8)), nb.math("MULTIPLY", v, 9.0), 0.0)
    st = nb.smooth(nb.noise(q, 3.0, 3.0, 0.6), 0.35, 0.7)
    a = nb.math("MULTIPLY", a, nb.math("ADD", 1.0 - hair, nb.math("MULTIPLY", st, hair)))
    sk = shade.skin_paint(nb, **skin_cfg)
    if streak is not None:
        a0 = nb.math("MULTIPLY", nb.math("MULTIPLY", nb.smooth(v, 0.0, sharp), nb.smooth(
            nb.math("SUBTRACT", 1.0, v), 0.0, sharp)), nb.maprange(nb.smooth(u, 0.0, head_soft),
                                                                  0, 1, 0.35, 1.0))
        base = nb.mix(nb.math("MULTIPLY", a0, 0.85), sk, shade.rgb(color))
        c = nb.mix(nb.math("MULTIPLY", nb.math("MULTIPLY", st, a0), 1.0), base, shade.rgb(streak))
        _skin_out(nb, c, a0)
        return m
    a2 = nb.math("MINIMUM", nb.math("MULTIPLY", a, 1.15), 1.0)
    c = nb.mix(a2, sk, shade.rgb(color))
    _skin_out(nb, c, a2, ink=nb.math("MULTIPLY", a, 0.6))
    return m


def wash_material(name, color, alpha, skin_cfg, soft0=0.35):
    """A soft-edged ink / colour wash decal on the skin (beard shadow, stubble, tattoo...)."""
    m = shade._mat(name)
    nb = shade.NB(m)
    ring = nb.attr("ring")
    a = nb.math("MULTIPLY", nb.math("SUBTRACT", 1.0, nb.smooth(ring, soft0, 1.0)), alpha)
    sk = shade.skin_paint(nb, **skin_cfg)
    c = nb.mix(a, sk, shade.rgb(color))
    _skin_out(nb, c, a)
    return m


def lip_material(name, color, skin_cfg, upper=True):
    m = shade._mat(name)
    nb = shade.NB(m)
    ring = nb.attr("ring")
    uv = nb.sep(nb.uv())
    v = uv[1]
    base = shade.rgb(color)
    deep = shade.rgb(mix(color, "#3A1414", 0.35))
    light = shade.rgb(mix(color, "#F2C6B4", 0.35))
    # darker toward the parting line (v ~ 0), lighter toward the outer edge
    k = nb.smooth(nb.math("ABSOLUTE", v), 0.0, 0.35)
    c = nb.mix(k, deep, base)
    if not upper:
        c = nb.mix(nb.math("MULTIPLY", nb.blob(nb.comb(uv[0], v, 0.0), (0.0, -0.33, 0.0),
                                               (0.5, 0.18, 1.0)), 0.6), c, light)
    a = nb.math("SUBTRACT", 1.0, nb.smooth(ring, 0.55, 1.0))
    sk = shade.skin_paint(nb, **skin_cfg)
    c = nb.mix(a, sk, c)
    _skin_out(nb, c, a)
    return m


# --------------------------------------------------------------------------------- builder
class Face:
    def __init__(self, H, spec, col, parent, skin_cfg):
        self.H = H
        self.s = spec
        self.col = col
        self.parent = parent
        self.skin_cfg = skin_cfg
        self.surf = H.surf
        self.objs = []

    def eye_origin(self, side):
        c = self.H.eye_l if side > 0 else self.H.eye_r
        e = self.s["eye"]
        return np.array([c[0] + side * e.get("dx", 0.0) * CM, c[2] + e.get("dz", 0.0) * CM])

    def strip(self, name, path_face, widths_m, mat, offset=0.0005):
        ob = geo.decal_strip(name, self.surf, path_face, widths_m, self.col, mat, offset,
                             parent=self.parent)
        self.objs.append(ob)
        return ob

    def build(self):
        for side in (1, -1):
            self.eye(side)
            self.brow(side)
        self.nose()
        self.mouth()
        self.wrinkles()
        return self.objs

    # ---------------------------------------------------------------------------- eye
    def eye(self, side):
        e = self.s["eye"]
        o = self.eye_origin(side)
        up, lo = eye_curves(e)
        outline = np.vstack([up, lo[::-1][1:-1]])
        face_out = _local_to_face(side, o, outline)
        # iris centre in local cm: gaze is given in *face* x (toward the viewer)
        gx, gz = e.get("gaze", (0.0, 0.0))
        ic = (e.get("iris_u", 0.0) + side * gx, e.get("iris_v", e["Hu"] * 0.32) + gz)
        mat = eye_material("Eye%+d" % side, e, ic, self.skin_cfg)
        ob = geo.decal_fill("EyeFill%+d" % side, self.surf, face_out, self.col, mat,
                            offset=0.00035, rings=8, parent=self.parent, local=outline,
                            center=_local_to_face(side, o, [[(up[0, 0] + up[-1, 0]) / 2,
                                                             0.0]])[0])
        self.objs.append(ob)
        ink = self.s.get("line_ink", "ink_dense")
        # upper lid: 铁线 iron-wire firmness, swelling toward the outer third, tail lifting off
        path = upper_lid_stroke(e, up)
        w = geo.brush_profile(len(path), head=0.25, tail=0.3, start=0.35, end=0.08, swell=0.15)
        lid_w = e.get("lid_w", 0.17) * CM
        self.strip("LidUp%+d" % side, _local_to_face(side, o, path), w * lid_w,
                   stroke_material("LidInk", ink))
        # lower lid: faint, broken before the inner corner
        n = len(lo)
        lp = lo[int(n * e.get("lo_start", 0.22)):int(n * 0.97)]
        lp = geo.resample(lp, 30)
        w = geo.brush_profile(len(lp), head=0.35, tail=0.35, start=0.1, end=0.2)
        self.strip("LidLo%+d" % side, _local_to_face(side, o, lp),
                   w * e.get("lower_w", 0.075) * CM,
                   stroke_material("LidLoInk", e.get("lower_col", "ink_ochre"), soft=0.3,
                                   skin_cfg=self.skin_cfg))
        # double-lid crease (optional): parallel to the upper lid, thin and light
        if e.get("crease", 0.0) > 0:
            g = e["crease"]
            t = np.linspace(0, 1, len(up))
            cp = up + np.stack([np.zeros_like(t), g * np.sin(math.pi * t ** 0.9) ** 0.6 + 0.02],
                               1)
            cp = cp[int(len(cp) * e.get("crease_start", 0.3)):int(len(cp) * 0.96)]
            cp = geo.resample(cp, 30)
            w = geo.brush_profile(len(cp), head=0.4, tail=0.35, start=0.1, end=0.15)
            self.strip("Crease%+d" % side, _local_to_face(side, o, cp),
                       w * e.get("crease_w", 0.05) * CM,
                       stroke_material("CreaseInk", "ink_ochre", soft=0.45,
                                       skin_cfg=self.skin_cfg))

    # --------------------------------------------------------------------------- brow
    BROWS = {
        # control points in eye-local cm relative to the eye chord centre; width profile
        "sword": dict(pts=[(-1.95, 1.05), (-1.1, 1.32), (0.2, 1.62), (1.4, 1.95), (2.2, 2.12)],
                      w=0.62, head=0.2, tail=0.62, start=0.75, end=0.06, swell=0.0),
        "silkworm": dict(pts=[(-1.9, 1.05), (-0.8, 1.58), (0.5, 1.78), (1.6, 1.62), (2.25, 1.3)],
                         w=0.78, head=0.25, tail=0.35, start=0.55, end=0.3, swell=0.12),
        "willow": dict(pts=[(-1.7, 1.12), (-0.6, 1.5), (0.6, 1.62), (1.55, 1.42), (2.1, 1.08)],
                       w=0.3, head=0.3, tail=0.55, start=0.5, end=0.05, swell=0.1),
        "calm": dict(pts=[(-1.85, 1.1), (-0.7, 1.45), (0.6, 1.6), (1.65, 1.48), (2.15, 1.25)],
                     w=0.45, head=0.25, tail=0.5, start=0.6, end=0.08, swell=0.05),
        "elder": dict(pts=[(-1.9, 1.1), (-0.8, 1.48), (0.5, 1.6), (1.6, 1.38), (2.5, 0.75)],
                      w=0.6, head=0.25, tail=0.45, start=0.6, end=0.15, swell=0.1),
    }

    def brow(self, side):
        b = self.s["brow"]
        e = self.s["eye"]
        kind = self.BROWS[b.get("kind", "calm")]
        o = self.eye_origin(side)
        pts = np.array(kind["pts"], np.float64)
        pts[:, 0] *= b.get("length", 1.0)
        pts[:, 1] += b.get("dz", 0.0)
        # raise the tail (sword / angry) or lower it (kind elder)
        ramp = (pts[:, 0] - pts[0, 0]) / (pts[-1, 0] - pts[0, 0])
        pts[:, 1] += ramp * b.get("rise", 0.0)
        path = geo.catmull(pts, per=10)
        path = geo.resample(path, 50)
        w = geo.brush_profile(len(path), head=kind["head"], tail=kind["tail"],
                              start=kind["start"], end=kind["end"], swell=kind["swell"])
        w = w * kind["w"] * b.get("thick", 1.0) * CM
        L = float(np.sum(np.linalg.norm(np.diff(path, axis=0), axis=1)))
        mat = brow_material("Brow", b.get("color", "ink_dense"), L, self.skin_cfg,
                            hair=b.get("hair", 0.5), sharp=b.get("sharp", 0.2),
                            streak=b.get("streak"))
        self.strip("Brow%+d" % side, _local_to_face(side, o, path), w, mat, offset=0.0006)

    # --------------------------------------------------------------------------- nose
    def nose(self):
        """3/4 canon nose: a fine far-side line from the brow down the bridge into the far
        wing, the near alar groove as one soft C, and two small dark nostril commas."""
        lm = self.H.lm
        n = self.s.get("nose", {})
        nt = lm["nose_tip"]
        tz = nt[2] / CM
        nz = lm["nasion"][2] / CM
        far = self.s.get("far", 1)
        near = -far
        wing = n.get("wing", 1.0)
        soft = stroke_material("NoseInk", "ink_ochre", soft=0.4, skin_cfg=self.skin_cfg)
        # far bridge line (faded at the top)
        bl = n.get("bridge", 1.0)
        if bl > 0:
            pts = np.array([(0.42, nz - 0.6), (0.5, (nz + tz) / 2), (0.62, tz + 0.75),
                            (0.86, tz + 0.05), (1.05 * wing, tz - 0.4)], np.float64)
            p = geo.resample(geo.catmull(pts, per=10), 40)
            p = np.stack([far * p[:, 0] * CM, p[:, 1] * CM], 1)
            w = geo.brush_profile(len(p), head=0.6, tail=0.25, start=0.05, end=0.3, swell=0.1)
            self.strip("Bridge", p, w * n.get("bridge_w", 0.055) * CM * bl, soft, 0.0006)
        # near alar groove
        pts = np.array([(0.92, tz + 0.3), (1.22, tz - 0.05), (1.22, tz - 0.45),
                        (0.95, tz - 0.72)], np.float64)
        pts[:, 0] *= wing
        p = geo.resample(geo.catmull(pts, per=8), 30)
        p = np.stack([near * p[:, 0] * CM, p[:, 1] * CM], 1)
        w = geo.brush_profile(len(p), head=0.35, tail=0.35, start=0.1, end=0.25, swell=0.2)
        self.strip("Wing", p, w * n.get("w", 0.07) * CM, soft, 0.0006)
        # nostrils
        dark = stroke_material("NostrilInk", "#4A2A20", soft=0.3, skin_cfg=self.skin_cfg)
        for side, L in ((near, 1.0), (far, 0.75)):
            q = np.array([(0.68, tz - 0.66), (0.45, tz - 0.8), (0.22, tz - 0.74)], np.float64)
            q[:, 0] *= wing
            q = geo.resample(geo.catmull(q, per=6), 16)
            q = np.stack([side * q[:, 0] * CM, q[:, 1] * CM], 1)
            w = geo.brush_profile(len(q), head=0.4, tail=0.45, start=0.4, end=0.2, swell=0.35)
            self.strip("Nostril", q, w * 0.1 * CM * L, dark, 0.0006)

    # -------------------------------------------------------------------------- mouth
    def mouth(self):
        mo = self.s["mouth"]
        lm = self.H.lm
        z0 = lm["mouth"][2] + mo.get("dz", 0.0) * CM
        a = mo["W"] / 2
        hu, hl = mo["Hu"], mo["Hl"]
        cl = mo.get("corner", 0.0)       # +: smile, -: stern
        t = np.linspace(-1, 1, 41)
        # parting line: slight bow, corners lifted/dropped
        part = cl * np.abs(t) ** 2.2 + mo.get("bow", 0.03) * np.cos(t * math.pi / 2) ** 2 * 0.5
        # upper outline: cupid's bow
        bow = hu * (np.abs(np.sin(math.pi * (np.abs(t) ** 0.8))) ** 0.6) * (1 - 0.18 * np.exp(
            -(t / 0.12) ** 2))
        top = part + bow + 0.0
        bot = part - hl * np.sin(math.pi * (t + 1) / 2) ** 0.75
        x = t * a
        up_outline = np.vstack([np.stack([x, top], 1), np.stack([x[::-1], part[::-1]], 1)[1:-1]])
        lo_outline = np.vstack([np.stack([x, part], 1), np.stack([x[::-1], bot[::-1]], 1)[1:-1]])
        col = mo.get("color", "rouge_lip_m")
        for nm, outl, upper in (("LipUp", up_outline, True), ("LipLo", lo_outline, False)):
            face = np.stack([outl[:, 0] * CM, z0 + outl[:, 1] * CM], 1)
            local = np.stack([outl[:, 0] / a, outl[:, 1] / max(hu, hl)], 1)
            mat = lip_material(nm, col, self.skin_cfg, upper)
            ob = geo.decal_fill(nm, self.surf, face, self.col, mat, offset=0.00035, rings=5,
                                parent=self.parent, local=local)
            self.objs.append(ob)
        # parting line stroke
        pp = np.stack([x * CM * mo.get("line_len", 0.9), z0 + part * CM], 1)
        w = geo.brush_profile(len(pp), head=0.25, tail=0.25, start=0.1, end=0.1, swell=0.3)
        self.strip("LipLine", pp, w * mo.get("line_w", 0.075) * CM,
                   stroke_material("LipInk", mo.get("line", "ink_rouge")), 0.0006)

    # ----------------------------------------------------------------------- wrinkles
    def wrinkles(self):
        wr = self.s.get("wrinkles", {})
        if not wr:
            return
        lm = self.H.lm
        mat = stroke_material("Wrinkle", wr.get("color", "#7A5040"), soft=0.4,
                              skin_cfg=self.skin_cfg, dry=0.3)
        ez = self.H.eye_z
        k = 0
        if wr.get("forehead", 0) > 0:
            for i, dz in enumerate((3.2, 3.95, 4.7)[:wr["forehead"]]):
                xs = np.linspace(-1.9 + 0.3 * i, 1.9 - 0.3 * i, 7)
                zs = ez + (dz + 0.12 * np.cos(xs * 1.6)) * CM
                p = geo.catmull(np.stack([xs * CM, zs], 1), per=6)
                w = geo.brush_profile(len(p), head=0.35, tail=0.35, start=0.1, end=0.1)
                self.strip("Fh%d" % k, p, w * 0.05 * CM, mat, 0.0006)
                k += 1
        if wr.get("crows", 0) > 0:
            e = self.s["eye"]
            for side in (1, -1):
                o = self.eye_origin(side)
                for j, ang in enumerate((10, -12, -32)[:wr["crows"]]):
                    a = math.radians(ang)
                    p0 = np.array([e["W"] / 2 + 0.3, 0.1])
                    p = np.array([p0, p0 + 0.45 * np.array([math.cos(a), math.sin(a)]),
                                  p0 + 0.85 * np.array([math.cos(a * 1.2), math.sin(a * 1.2)])])
                    p = geo.catmull(p, per=5)
                    w = geo.brush_profile(len(p), head=0.3, tail=0.5, start=0.2, end=0.05)
                    self.strip("Cr%d" % k, _local_to_face(side, o, p), w * 0.04 * CM, mat,
                               0.0006)
                    k += 1
        if wr.get("nasolabial", 0) > 0:
            nt = lm["nose_tip"]
            mz = lm["mouth"][2]
            L = wr["nasolabial"]
            for side in (1, -1):
                p = np.array([(1.45, nt[2] / CM + 0.1), (1.95, nt[2] / CM - 0.6),
                              (2.3, mz / CM - 0.1), (2.35, mz / CM - 0.4 * L)])
                p = geo.catmull(p, per=6)
                p = np.stack([side * p[:, 0] * CM, p[:, 1] * CM], 1)
                w = geo.brush_profile(len(p), head=0.2, tail=0.5, start=0.2, end=0.05)
                self.strip("Nl%d" % k, p, w * 0.055 * CM, mat, 0.0006)
                k += 1
        if wr.get("under_eye", 0) > 0:
            e = self.s["eye"]
            for side in (1, -1):
                o = self.eye_origin(side)
                up, lo = eye_curves(e)
                p = lo[int(len(lo) * 0.3):int(len(lo) * 0.9)] + np.array([0.0, -0.35])
                p = geo.resample(p, 20)
                w = geo.brush_profile(len(p), head=0.4, tail=0.4, start=0.1, end=0.1)
                self.strip("Ue%d" % k, _local_to_face(side, o, p), w * 0.04 * CM, mat, 0.0006)
                k += 1


def skin_config(H, spec):
    """Skin paint parameters: base tone, rouge gaussians (cheeks, lids, nose, chin, ears),
    三白 lighter passages on forehead / nose bridge / chin."""
    sk = spec.get("skin", {})
    lm = H.lm
    s = H.surf
    ez = H.eye_z
    blobs = []

    def at(x, z):
        return tuple(s.hit(x, z)[0])
    ck = sk.get("cheek", 0.3)
    for side in (1, -1):
        blobs.append((at(side * 0.043, ez - 0.026), (0.03, 0.035, 0.03), ck))
        if sk.get("eyelid", 0.0) > 0:
            ex = (H.eye_l if side > 0 else H.eye_r)[0]
            blobs.append((at(ex, ez + 0.002), (0.022, 0.03, 0.012), sk["eyelid"]))
        blobs.append(((side * 0.072, lm["nose_tip"][1] + 0.095, ez - 0.02), (0.02, 0.03, 0.035),
                      sk.get("ear", 0.35)))
    blobs.append((tuple(lm["nose_tip"]), (0.012, 0.02, 0.012), sk.get("nose", 0.12)))
    blobs.append((tuple(lm["chin"]), (0.018, 0.02, 0.014), sk.get("chin", 0.08)))
    light = []
    tw = sk.get("three_white", 0.0)
    if tw > 0:
        light.append((tuple(lm["forehead"]), (0.03, 0.04, 0.03), tw))
        light.append(((0, lm["nasion"][1] - 0.01, ez - 0.015), (0.008, 0.04, 0.022), tw * 0.8))
        light.append((tuple(lm["chin"]), (0.014, 0.03, 0.01), tw * 0.6))
    return dict(base=sk.get("base", "skin_warm"), rouge=sk.get("rouge", "rouge"), blobs=blobs,
                light_blobs=light)
