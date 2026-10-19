"""Calligraphic face for gongbi_C: the canon features drawn in 2D, wrapped onto the 3D head.

Every feature is designed frontally in face space (:mod:`canon` units) and mapped through
:meth:`strokes.Proj.face_px` - the head height grid plus the camera - so a 3/4 view foreshortens
the far eye, slides the nose over the far cheek and wraps the mouth exactly as the 3D head turns,
while each line keeps a painter's brush profile.

Line families (人物画十八描):
* 高古游丝描  fine even lines - eyelid folds, lower lids, ears, wrinkles
* 铁线描      firm even lines - upper lids, nose contour, mouth line
* tapered hair strokes (丝毛) - brows, beards, temple hair
Colour is laid as washes before the lines: 胭脂 rouge on cheeks / lips / eye sockets, 赭石 ochre
shading (分染), lead white (三白) highlights, eye whites, ink irises with a highlight.
"""

import math

import numpy as np

import strokes as S
from looks import PAL, srgb, mix


# =============================================================================================
# helpers
# =============================================================================================
def _shape(t, p, k):
    """Bump 0..1 on t in [0, 1] peaking at p (k = sharpness at the corners)."""
    a, b = p * k, (1 - p) * k
    f = np.power(np.clip(t, 1e-6, 1), a) * np.power(np.clip(1 - t, 1e-6, 1), b)
    fm = (p ** a) * ((1 - p) ** b)
    return f / fm


def _ppx(pr, uv, dh=0.0):
    uv = np.asarray(uv, np.float64)
    return pr.face_px(uv[..., 0], uv[..., 1], dh)


def _local_scale(pr, u, v, du=0.004, dv=0.004):
    """Screen length (work px) of a small step along u and v at a face point."""
    a = pr.face_px(u, v)[:2]
    b = pr.face_px(u + du, v)[:2]
    c = pr.face_px(u, v + dv)[:2]
    return np.hypot(*(b - a)) / du, np.hypot(*(c - a)) / dv, math.atan2(b[1] - a[1], b[0] - a[0])


def wash(pp, pr, u, v, ru, rv, color, alpha, clip, mode="glaze", soft=0.5):
    """Soft elliptic wash centred at a face point, radii in face metres (foreshortened)."""
    if alpha <= 0:
        return
    su, sv, ang = _local_scale(pr, u, v)
    c = pr.face_px(u, v)
    pp.blob(c[:2], max(1.0, ru * su), max(1.0, rv * sv), color, alpha, rot=ang, mode=mode,
            clip=clip, soft=soft)


class Ctx:
    def __init__(self, pp, pr, c, masks, seed=0):
        self.pp, self.pr, self.c = pp, pr, c
        self.face = masks["face"]
        self.skin = masks["skin"]
        self.hair = masks["hair"]
        self.rng = np.random.default_rng(seed)
        self.far = pr.far_sign()
        yaw, pitch = pr.gaze()
        self.gyaw, self.gpitch = yaw, pitch
        self.line = c.get("line_color", "#4A3024")
        self.lid_ink = "#221814"
        self.pxm = pr.px_per_m()            # work px per canon metre

    def fpx(self, uv, dh=0.0):
        return _ppx(self.pr, uv, dh)


# =============================================================================================
# eyes
# =============================================================================================
def eye_geom(c, side):
    w = c["eye_w"]
    h = c["eye_h"] * w
    I = np.array([side * c["eye_in"], c["eye_v"]])
    O = np.array([side * (c["eye_in"] + w), c["eye_v"] + c["eye_tilt"]])
    L = np.linalg.norm(O - I)
    e = (O - I) / L
    n = np.array([-e[1], e[0]])
    if n[1] < 0:
        n = -n
    t = np.linspace(0, 1, 40)
    up = I + np.outer(t * L, e) + np.outer(h * c["eye_up"] * _shape(t, c["eye_peak"], c["eye_k"]), n)
    lo = I + np.outer(t * L, e) - np.outer(h * (1 - c["eye_up"]) * _shape(t, c["eye_low"], c["eye_k"] * 0.85), n)
    return dict(I=I, O=O, e=e, n=n, L=L, h=h, w=w, t=t, up=up, lo=lo)


def eye(cx, side):
    c, pp, pr = cx.c, cx.pp, cx.pr
    g = eye_geom(c, side)
    I, O, e, n, L, h, t = g["I"], g["O"], g["e"], g["n"], g["L"], g["h"], g["t"]
    bulge = lambda tt: 0.0018 * np.sin(np.pi * np.clip(tt, 0, 1))
    up_px = cx.fpx(g["up"], bulge(t))
    lo_px = cx.fpx(g["lo"], bulge(t))
    opening = np.concatenate([up_px[:, :2], lo_px[::-1, :2]])
    om = S.polygon_mask(pp.H, pp.W, opening)
    if om is None:
        return
    oy, ox, oa = om
    omask = np.zeros((pp.H, pp.W), np.float32)
    omask[oy:oy + oa.shape[0], ox:ox + oa.shape[1]] = oa
    omask *= np.clip(cx.face * 1.2, 0, 1)
    fm = cx.face
    # ---- eye socket washes -------------------------------------------------------------------
    mid = (I + O) / 2
    if c["eye_shadow"] > 0:
        wash(pp, pr, mid[0] + side * 0.002, mid[1] + h * 0.9, g["w"] * 0.62, h * 1.25,
             c["eye_shadow_color"], c["eye_shadow"], fm)
    wash(pp, pr, mid[0], mid[1] + h * 0.55, g["w"] * 0.55, h * 0.75, "#B07A5A", c["shade"] * 0.55, fm)
    # ---- eye white, lid shadow, corners --------------------------------------------------------
    pp.layer(omask, "#F6F0E4", "paint", 0.86)
    band = np.concatenate([up_px[:, :2], cx.fpx(g["up"] - np.outer(np.full(len(t), h * 0.42), n), bulge(t))[::-1, :2]])
    pp.fill(band, "#8C7468", alpha=0.38, mode="glaze", soft=0.45, clip=omask)
    ci = cx.fpx(I + e * L * 0.05)[:2]
    co = cx.fpx(O - e * L * 0.06)[:2]
    k = cx.pxm * pr.s
    pp.blob(ci, 0.004 * k, 0.003 * k, "#C88A80", 0.45, clip=omask)
    pp.blob(co, 0.004 * k, 0.003 * k, "#B8988A", 0.35, clip=omask)
    # ---- iris -----------------------------------------------------------------------------------
    R_eye = 0.0115
    gu = R_eye * math.sin(cx.gyaw) * 0.85 + c["gaze"][0]
    gv = R_eye * math.sin(cx.gpitch) * 0.6 + c["gaze"][1]
    ic = mid + n * (c["iris_v"] * h) + np.array([gu, gv])
    icp = pr.face_px(ic[0], ic[1], 0.0045)
    r = c["iris"] * g["w"] / 2 * k
    iris = S.ellipse_pts(icp[:2], r, r * 1.0, n=48)
    pp.fill(iris, mix(c["iris_color"], "#1A120E", 0.15), alpha=0.97, clip=omask)
    # lighter lower half (the iris catches light below the lid shadow)
    pp.blob(icp[:2] + np.array([0, r * 0.38]), r * 0.62, r * 0.38, "#8A5A3A", 0.28, mode="paint", clip=omask)
    ring = S.ellipse_pts(icp[:2], r * 0.98, r * 0.98, n=48)
    pp.stroke(np.concatenate([ring, ring[:1]]), 0.45, "#120C0A", alpha=0.75, clip=omask)
    pp.fill(S.ellipse_pts(icp[:2], r * 0.44, r * 0.44, n=32), "#0C0807", alpha=1.0, clip=omask)
    # catch light from the top-left (the studio light), and a faint reflected one
    hl = icp[:2] + np.array([-0.30 * r, -0.36 * r])
    pp.fill(S.ellipse_pts(hl, r * 0.19, r * 0.19, n=24), "#FFFDF8", alpha=0.95, clip=omask)
    pp.fill(S.ellipse_pts(icp[:2] + np.array([0.34 * r, 0.30 * r]), r * 0.08, r * 0.08, n=16),
            "#F4EEE6", alpha=0.55, clip=omask)
    # ---- lids ------------------------------------------------------------------------------------
    lw = c["lid_w"]
    # upper lid: from a small hook at the inner corner, swelling to the outer third, then the
    # tail (phoenix eyes extend it upwards past the corner)
    hook = I + e * (-0.05 * L) - n * (0.18 * h)
    tail = [O + e * c["tail"] * 0.5 + n * c["tail_rise"] * 0.4, O + e * c["tail"] + n * c["tail_rise"]] \
        if c["tail"] > 0 else []
    ul = np.concatenate([[hook], g["up"][1:], tail]) if tail else np.concatenate([[hook], g["up"][1:]])
    ul = S.catmull(ul, 60)
    ulp = cx.fpx(ul, 0.0019)
    tt = np.linspace(0, 1, len(ulp))
    endt = 1.0 / (1.0 + c["tail"] / L) if c["tail"] > 0 else 1.0
    prof = (0.28 + 0.72 * S.smoothstep(0.0, 0.42, tt)) * (1 - S.smoothstep(endt - 0.05, 1.0, tt) * 0.92)
    prof *= 1 + c["lash"] * 0.35 * np.exp(-((tt - 0.82 * endt) / 0.12) ** 2)
    pp.stroke(ulp, lw, cx.lid_ink, alpha=0.95, prof=prof, clip=np.clip(fm * 1.5, 0, 1))
    # crease of the double lid (游丝描)
    if c["lid_fold"] > 0:
        a0, a1 = c["lid_fold_span"]
        sel = (t >= a0) & (t <= a1)
        tt2 = t[sel]
        off = c["lid_fold"] * (0.55 + 0.45 * np.sin(np.pi * (tt2 - a0) / (a1 - a0)))
        fold = g["up"][sel] + np.outer(off, n) + np.outer(np.full(len(tt2), 0.0004), e)
        fp = cx.fpx(fold, 0.0016)
        pp.stroke(fp, 0.55, cx.line, alpha=0.65, prof=S.brush_profile(len(fp), 0.3, 0.4, 0.2), clip=fm)
    # heavy lid of age (hooded fold drooping over the outer corner)
    if c["hood"] > 0:
        tt3 = np.linspace(0.28, 1.08, 30)
        base = I + np.outer(tt3 * L, e)
        hh = h * c["eye_up"] * _shape(np.clip(tt3, 0, 1), c["eye_peak"], c["eye_k"]) + h * 0.45 - h * 0.35 * S.smoothstep(0.7, 1.08, tt3)
        hood = base + np.outer(hh, n)
        hp = cx.fpx(hood, 0.0016)
        pp.stroke(hp, 0.6, cx.line, alpha=0.55 * c["hood"] + 0.2, prof=S.brush_profile(len(hp), 0.3, 0.3, 0.2), clip=fm)
    # lower lid: fine, light, not quite reaching the inner corner
    sel = t >= 0.16
    lp = cx.fpx(g["lo"][sel], bulge(t[sel]))
    tl = np.linspace(0, 1, len(lp))
    la = c["lower_a"] * (0.55 + 0.45 * S.smoothstep(0.0, 0.5, tl))
    pp.stroke(lp, c["lower_w"], cx.line, alpha=1.0, alphas=la, prof=S.brush_profile(len(lp), 0.3, 0.15, 0.3), clip=fm)
    if c["bag"] > 0:
        tb = np.linspace(0.2, 0.9, 24)
        bag = I + np.outer(tb * L, e) - np.outer(h * (1 - c["eye_up"]) * _shape(tb, c["eye_low"], 2.0) + h * 0.55, n)
        bp = cx.fpx(bag, 0.0012)
        pp.stroke(bp, 0.5, cx.line, alpha=0.32 * c["bag"] + 0.08, prof=S.brush_profile(len(bp), 0.4, 0.4, 0.1), clip=fm)
    return g


# =============================================================================================
# brows
# =============================================================================================
BROW_STYLES = {
    #            hair angle head/tail (deg), length k, base wash alpha, base soft
    "sword": dict(ang=(58, 8), lk=1.25, base=0.80, soft=0.22, hook=0.0),
    "silkworm": dict(ang=(62, 10), lk=1.35, base=0.85, soft=0.25, hook=0.0),
    "willow": dict(ang=(40, 6), lk=1.15, base=0.72, soft=0.18, hook=0.0),
    "calm": dict(ang=(55, 10), lk=1.2, base=0.75, soft=0.25, hook=0.0),
    "longevity": dict(ang=(50, -8), lk=1.6, base=0.45, soft=0.30, hook=0.0),
}


def brow(cx, side):
    c, pp, pr = cx.c, cx.pp, cx.pr
    st = BROW_STYLES.get(c["brow"], BROW_STYLES["calm"])
    Lb = c["brow_len"]
    B0 = np.array([side * (c["brow_in"] + c["brow_knit"] * 0.5), c["brow_v"] - c["brow_knit"]])
    B3 = np.array([side * (c["brow_in"] + Lb), c["brow_v"] + c["brow_rise"]])
    arch = c["brow_arch"]
    if c["brow"] == "silkworm":
        P1 = B0 + np.array([side * 0.28 * Lb, arch * 1.5 + c["brow_knit"] * 0.8])
        P2 = B0 + np.array([side * 0.68 * Lb, c["brow_rise"] + arch * 1.3])
    elif c["brow"] == "sword":
        P1 = B0 + np.array([side * 0.33 * Lb, arch * 0.9 + c["brow_rise"] * 0.3 + c["brow_knit"] * 0.7])
        P2 = B0 + np.array([side * 0.72 * Lb, c["brow_rise"] * 0.95 + arch * 0.7])
    elif c["brow"] == "longevity":
        P1 = B0 + np.array([side * 0.30 * Lb, arch * 1.2])
        P2 = B0 + np.array([side * 0.62 * Lb, arch * 1.1])
    else:
        P1 = B0 + np.array([side * 0.30 * Lb, arch * 1.25 + c["brow_rise"] * 0.2])
        P2 = B0 + np.array([side * 0.66 * Lb, c["brow_rise"] * 0.8 + arch * 1.15])
    C = S.bezier(B0, P1, P2, B3, 40)
    t = np.linspace(0, 1, len(C))
    w0, w1, w2 = c["brow_w"]
    wv = np.where(t < 0.35, w0 + (w1 - w0) * S.smoothstep(0, 0.35, t), w1 + (w2 - w1) * S.smoothstep(0.35, 1.0, t))
    if c["brow"] == "willow":
        wv = wv * (0.45 + 0.55 * S.smoothstep(0.0, 0.25, t))
    d = np.gradient(C, axis=0)
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    n = np.stack([-d[:, 1], d[:, 0]], -1)
    n *= np.sign(n[:, 1:2] + 1e-9)
    upper = C + n * (wv * 0.55)[:, None]
    lower = C - n * (wv * 0.45)[:, None]
    fm = np.clip(cx.face * 1.3, 0, 1)
    poly = np.concatenate([cx.fpx(upper, 0.003)[:, :2], cx.fpx(lower[::-1], 0.003)[:, :2]])
    white = c["brow_color"] in ("white", "grey")
    base_col = {"ink": "#2A2420", "grey": "#7A746C", "white": "#9A948C", "grizzled": "#3A3430"}[c["brow_color"]]
    hair_col = {"ink": "#16110E", "grey": "#5A544E", "white": "#FBF8F0", "grizzled": "#16110E"}[c["brow_color"]]
    pp.fill(poly, base_col, alpha=st["base"] * (0.7 if white else 1.0), mode="glaze" if not white else "glaze",
            soft=st["soft"], clip=fm)
    # hair strokes (丝眉): rooted on the lower edge, flowing outwards
    rng = cx.rng
    nh = int(c["brow_hairs"] * (1.25 if white else 1.0))
    ts = np.sort(np.concatenate([rng.uniform(0, 0.35, nh // 3), rng.uniform(0, 1.0, nh - nh // 3)]))
    a_head, a_tail = st["ang"]
    for ti in ts:
        i = int(ti * (len(C) - 1))
        root = C[i] - n[i] * wv[i] * rng.uniform(0.15, 0.45)
        ang = math.radians(a_head + (a_tail - a_head) * ti ** 0.7 + rng.normal(0, 4))
        dirv = d[i] * math.cos(ang) + n[i] * math.sin(ang)
        ln = wv[i] * st["lk"] / max(0.35, math.sin(abs(ang)) + 0.3) * rng.uniform(0.8, 1.25)
        ln = min(max(ln, 0.0035), 0.011)
        pts = np.array([root, root + dirv * ln * 0.5 + n[i] * wv[i] * 0.05, root + dirv * ln])
        pts = S.resample(pts, 6)
        P = cx.fpx(pts, 0.003)
        if c["brow_color"] == "grizzled" and rng.random() < 0.3:
            pp.stroke(P, 0.5, "#E8E2D8", alpha=0.85, prof=S.brush_profile(len(P), 0.2, 0.7, 0.15, "tail"),
                      clip=fm, mode="paint", ink=False)
        elif white:
            pp.stroke(P, 0.55, hair_col, alpha=0.9, prof=S.brush_profile(len(P), 0.2, 0.7, 0.15, "tail"),
                      clip=fm, mode="paint", ink=False)
        else:
            pp.stroke(P, 0.5, hair_col, alpha=0.8, prof=S.brush_profile(len(P), 0.2, 0.7, 0.15, "tail"), clip=fm)
    if white:
        # long hairs of a longevity brow drooping past the eye (painted over the skin)
        for j in range(9 if c["brow"] == "longevity" else 0):
            ti = 0.72 + 0.28 * j / 8
            i = int(ti * (len(C) - 1))
            root = C[i]
            droop = c["brow_droop"] + 0.008
            tip = root + np.array([side * (0.006 + 0.004 * rng.random()), -droop - 0.006 * rng.random()])
            mid = root + np.array([side * 0.006, 0.0])
            pts = S.bezier(root, mid, (mid + tip) / 2 + np.array([side * 0.002, 0]), tip, 10)
            P = cx.fpx(pts, 0.003)
            pp.stroke(P, 0.55, "#FBF8F0", alpha=0.85, prof=S.brush_profile(len(P), 0.1, 0.8, 0.1, "tail"),
                      clip=np.clip(cx.skin * 1.3, 0, 1), mode="paint", ink=False)
            pp.stroke(P + np.array([0.6, 0.6, 0]), 0.35, "#8A8278", alpha=0.35,
                      prof=S.brush_profile(len(P), 0.1, 0.8, 0.1, "tail"), clip=np.clip(cx.skin * 1.3, 0, 1))
    return C


# =============================================================================================
# nose
# =============================================================================================
def nose(cx):
    c, pp, pr = cx.c, cx.pp, cx.pr
    Ln = c["nose_len"]
    far = cx.far
    near = -far
    vt = -Ln + 0.0080                       # centre of the tip bulb
    v_top = 0.0060

    def hp(v):
        # forward height of the nose ridge above the face surface
        tt = np.clip((v_top - v) / (v_top - vt), 0, 1)
        base = c["nose_bridge"] * 0.4 + (c["nose_h"] - c["nose_bridge"] * 0.4) * tt ** 1.15
        below = np.clip((vt - v) / (vt - (-Ln - 0.001)), 0, 1)
        return base * (1 - 0.75 * below ** 2)

    def wb(v):
        tt = np.clip((v_top - v) / (v_top - vt), 0, 1)
        return 0.0050 + 0.0042 * tt ** 2

    def surf(u, v):
        return hp(v) * np.sqrt(np.clip(1 - (u / wb(v)) ** 2, 0, 1))

    # screen direction of the far side
    a = pr.face_px(0.0, -0.02)[:2]
    b = pr.face_px(far * 0.02, -0.02)[:2]
    fdir = (b - a) / max(np.linalg.norm(b - a), 1e-9)
    vs = np.linspace(v_top + 0.004, vt - 0.0015, 34)
    cont = []
    ridge = []
    for v in vs:
        us = np.linspace(-1.6 * wb(v), 1.6 * wb(v), 41)
        P = pr.face_px(us, np.full_like(us, v), surf(us, v))
        sc = P[:, :2] @ fdir
        cont.append(P[np.argmax(sc)])
        ridge.append(pr.face_px(0.0, v, surf(0.0, v)))
    cont = np.array(cont)
    ridge = np.array(ridge)
    fm = np.clip(cx.face * 1.3, 0, 1)
    # 分染 on the far plane of the nose and its cast-free shading under the tip
    poly = np.concatenate([cont[:, :2], ridge[::-1, :2]])
    pp.fill(poly, "#B07A5A", alpha=c["shade"] * 0.9, mode="glaze", soft=0.6, clip=fm)
    wash(pp, pr, 0.0, -Ln - 0.0035, 0.009, 0.0035, "#A86A50", c["shade"] * 1.1, fm)
    wash(pp, pr, near * 0.0125, -Ln + 0.004, 0.004, 0.0045, "#A86A50", c["shade"] * 0.9, fm)
    # bridge contour (铁线描): fades in under the brow, firm at the tip
    tt = np.linspace(0, 1, len(cont))
    al = S.smoothstep(c["nose_fade"] - 0.55, c["nose_fade"], tt) * 0.85 * c["nose_line"]
    pp.stroke(cont, 0.85, cx.line, alpha=1.0, alphas=al, prof=0.7 + 0.3 * tt, clip=fm)
    # tip: round the bulb on the far side and under it to the near nostril
    vw = -Ln + 0.0040
    nw = c["nose_w"]
    tip_far = [(far * 0.0060, vt - 0.0040), (far * 0.0045, -Ln + 0.0006), (0.0, -Ln - 0.0004),
               (near * 0.0050, -Ln + 0.0003), (near * 0.0080, -Ln + 0.0007)]
    T = S.catmull(tip_far, 24)
    TP = pr.face_px(T[:, 0], T[:, 1], surf(T[:, 0], T[:, 1]) + 0.0015)
    pp.stroke(TP, 0.85, cx.line, alpha=0.85, prof=S.brush_profile(len(TP), 0.25, 0.35, 0.3), clip=fm)
    # near ala (鼻翼): a C round the nostril
    ala = [(near * 0.0085, -Ln + 0.0105), (near * (nw - 0.0012), -Ln + 0.0075), (near * nw, vw),
           (near * (nw - 0.0015), -Ln + 0.0006), (near * 0.0100, -Ln - 0.0002)]
    A = S.catmull(ala, 24)
    AP = pr.face_px(A[:, 0], A[:, 1], 0.0045)
    pp.stroke(AP, 0.8, cx.line, alpha=0.85, prof=S.brush_profile(len(AP), 0.4, 0.3, 0.15), clip=fm)
    # far ala: only the part that shows beyond the tip
    fa = [(far * 0.0065, -Ln + 0.0004), (far * (nw - 0.0015), -Ln + 0.0010), (far * nw, vw + 0.0010),
          (far * (nw - 0.0010), -Ln + 0.0080)]
    F = S.catmull(fa, 20)
    FP = pr.face_px(F[:, 0], F[:, 1], 0.0040)
    tipx = (cont[-6:, :2] @ fdir).max()
    vis = S.smoothstep(tipx - 1.0, tipx + 3.0, FP[:, :2] @ fdir)
    pp.stroke(FP, 0.7, cx.line, alpha=1.0, alphas=0.75 * vis, prof=S.brush_profile(len(FP), 0.2, 0.5, 0.2), clip=fm)
    # nostrils
    k = cx.pxm * pr.s
    for sgn, aa in ((near, 0.8), (far, 0.55)):
        nc = pr.face_px(sgn * 0.0066, -Ln + 0.0010, 0.0035)
        su, sv, ang = _local_scale(pr, sgn * 0.0066, -Ln + 0.0010)
        pts = S.ellipse_pts(nc[:2], 0.0026 * su, 0.0011 * sv, rot=ang + sgn * 0.25, n=24)
        pp.fill(pts, "#3A2018", alpha=aa, soft=0.25, clip=fm)
    return cont


# =============================================================================================
# mouth
# =============================================================================================
def mouth(cx):
    c, pp, pr = cx.c, cx.pp, cx.pr
    v0, w, cu = c["mouth_v"], c["mouth_w"], c["mouth_curve"]
    lu, ll, bow = c["lip_up"], c["lip_low"], c["bow"]
    smile = c["smile"]
    dh = lambda u: 0.0045 * (1 - np.clip(np.abs(u) / (w * 1.15), 0, 1) ** 2)
    line = S.catmull([(-w, v0 + cu), (-0.62 * w, v0 + 0.0002 + cu * 0.35), (-0.22 * w, v0 + 0.0005),
                      (0.0, v0 - 0.0002), (0.22 * w, v0 + 0.0005), (0.62 * w, v0 + 0.0002 + cu * 0.35),
                      (w, v0 + cu)], 48)
    upper = S.catmull([(-w, v0 + cu), (-0.58 * w, v0 + lu * 0.72), (-0.22 * w, v0 + lu),
                       (0.0, v0 + lu - bow), (0.22 * w, v0 + lu), (0.58 * w, v0 + lu * 0.72),
                       (w, v0 + cu)], 48)
    lower = S.catmull([(-w, v0 + cu), (-0.66 * w, v0 - ll * 0.62), (-0.25 * w, v0 - ll * 0.98),
                       (0.0, v0 - ll), (0.25 * w, v0 - ll * 0.98), (0.66 * w, v0 - ll * 0.62),
                       (w, v0 + cu)], 48)
    fm = np.clip(cx.face * 1.3, 0, 1)
    LP = pr.face_px(line[:, 0], line[:, 1], dh(line[:, 0]))
    UP = pr.face_px(upper[:, 0], upper[:, 1], dh(upper[:, 0]) * 0.92)
    LO = pr.face_px(lower[:, 0], lower[:, 1], dh(lower[:, 0]) * 0.95)
    # shadow under the lower lip, philtrum
    wash(pp, pr, 0.0, v0 - ll - 0.0035, w * 0.42, 0.0030, "#A86A50", c["shade"] * 1.2, fm)
    wash(pp, pr, 0.0, v0 + lu + 0.004, 0.0035, 0.004, "#B07A5A", c["shade"] * 0.6, fm)
    lc = c["lip_color"]
    a = c["lip_alpha"]
    pp.fill(np.concatenate([LP[:, :2], UP[::-1, :2]]), mix(lc, "#6A2028", 0.25), alpha=a, soft=0.3, clip=fm)
    pp.fill(np.concatenate([LP[:, :2], LO[::-1, :2]]), lc, alpha=a * 0.85, soft=0.35, clip=fm)
    # sheen on the lower lip
    wash(pp, pr, 0.0, v0 - ll * 0.55, w * 0.32, ll * 0.22, "#FFF4EA", a * 0.35, fm, mode="paint")
    # faint contour of the upper lip (helps small sizes), mouth line, corners
    pp.stroke(UP[6:-6], 0.45, mix(lc, "#3A1A18", 0.4), alpha=0.22 + a * 0.2, prof=S.brush_profile(len(UP) - 12, 0.3, 0.3, 0.3), clip=fm)
    tl = np.linspace(0, 1, len(LP))
    prof = 0.35 + 0.65 * np.sin(np.pi * tl) ** 0.6
    pp.stroke(LP, 0.95, "#4A2220", alpha=0.88, prof=prof, clip=fm)
    for sgn in (-1, 1):
        cp = pr.face_px(sgn * w * 1.02, v0 + cu, dh(w))
        pp.blob(cp[:2], 1.1 * pp.ss * 0.5, 0.8 * pp.ss * 0.5, "#4A2220", 0.6, mode="paint", clip=fm)
        if smile > 0 or cu > 0.0004:
            q = S.catmull([(sgn * (w + 0.0012), v0 + cu + 0.0012), (sgn * (w + 0.0025), v0 + cu - 0.0005),
                           (sgn * (w + 0.0022), v0 + cu - 0.0028)], 10)
            QP = pr.face_px(q[:, 0], q[:, 1], dh(w))
            pp.stroke(QP, 0.45, cx.line, alpha=0.25 + 0.3 * smile, prof=S.brush_profile(len(QP), 0.3, 0.5, 0.2), clip=fm)


# =============================================================================================
# washes, age, makeup
# =============================================================================================
def skin_washes(cx):
    c, pp, pr = cx.c, cx.pp, cx.pr
    fm = cx.face
    for side in (-1, 1):
        wash(pp, pr, side * 0.040, -0.030, 0.022, 0.016, c["rouge_color"], c["rouge"], fm)
        # under the cheekbone / temple 分染
        wash(pp, pr, side * 0.058, -0.045, 0.014, 0.025, "#B07A5A", c["shade"] * 0.7, fm)
        wash(pp, pr, side * 0.062, 0.030, 0.012, 0.022, "#B07A5A", c["shade"] * 0.5, fm)
        # under the brow head, beside the nose root
        wash(pp, pr, side * 0.011, 0.004, 0.005, 0.008, "#A87050", c["shade"] * 0.8, fm)
    # chin and jaw: a breath of rouge on the chin (ladies), ochre under it
    wash(pp, pr, 0.0, c["mouth_v"] - 0.030, 0.014, 0.008, c["rouge_color"], c["rouge"] * 0.5, fm)
    if c["three_whites"] > 0:
        a = c["three_whites"]
        wash(pp, pr, 0.0, 0.047, 0.022, 0.016, "#FBF6EC", a, fm, mode="paint")
        wash(pp, pr, 0.0, -0.012, 0.0045, 0.018, "#FBF6EC", a * 0.9, fm, mode="paint")
        wash(pp, pr, 0.0, c["mouth_v"] - 0.034, 0.010, 0.007, "#FBF6EC", a * 0.8, fm, mode="paint")


def wrinkles(cx):
    c, pp, pr = cx.c, cx.pp, cx.pr
    age, fierce = c["age"], c["fierce"]
    fm = cx.face
    rng = cx.rng
    if age > 0.25:
        n = 2 + int(age > 0.6)
        for i in range(n):
            v = 0.044 + 0.0095 * i
            for side in (-1, 1):
                us = np.linspace(side * 0.004, side * (0.030 - 0.004 * i), 14)
                vv = v + 0.0007 * np.sin(us / 0.016 * math.pi + i * 1.7) - 0.0020 * (np.abs(us) / 0.03) ** 2
                P = pr.face_px(us, vv, 0.0006)
                pp.stroke(P, 0.45, cx.line, alpha=0.14 + 0.2 * age, prof=S.brush_profile(len(P), 0.35, 0.35, 0.05), clip=fm)
                wash(pp, pr, float(us.mean()), v - 0.0025, 0.012, 0.0018, "#A87050", 0.05 * age, fm)
    for side in (-1, 1):
        g = eye_geom(c, side)
        # crow's feet
        if age > 0.35:
            for j, ang in enumerate((-28, -4, 20)):
                a = math.radians(ang)
                o = g["O"] + g["e"] * 0.0035
                dvec = g["e"] * math.cos(a) + g["n"] * math.sin(a)
                pts = np.array([o, o + dvec * 0.0045, o + dvec * 0.0085 + g["n"] * 0.0006 * j])
                P = pr.face_px(pts[:, 0], pts[:, 1], 0.0008)
                pp.stroke(S.resample(P, 6), 0.42, cx.line, alpha=0.18 + 0.2 * age, prof=S.brush_profile(6, 0.3, 0.6, 0.05, "tail"), clip=fm)
        # nasolabial fold (法令)
        k = max(age, 0.45 * fierce)
        if k < 0.2:
            wash(pp, pr, side * (c["mouth_w"] + 0.007), c["mouth_v"] + 0.006, 0.004, 0.010, "#B07A5A", 0.05, fm)
            continue
        a0 = np.array([side * (c["nose_w"] + 0.0015), -c["nose_len"] + 0.0075])
        a2 = np.array([side * (c["mouth_w"] + 0.0075), c["mouth_v"] - 0.0085 - 0.006 * age])
        a1 = np.array([side * (c["mouth_w"] + 0.0060), (a0[1] + a2[1]) / 2 + 0.0010])
        pts = S.catmull([a0, a1, a2], 20)
        P = pr.face_px(pts[:, 0], pts[:, 1], 0.0008)
        sel = slice(0, len(P) if k > 0.3 else int(len(P) * 0.6))
        pp.stroke(P[sel], 0.55, cx.line, alpha=0.1 + 0.4 * k, prof=S.brush_profile(len(P[sel]), 0.2, 0.6, 0.05), clip=fm)
        wash(pp, pr, float(pts[:, 0].mean()) + side * 0.004, float(pts[:, 1].mean()), 0.004, 0.010, "#A87050", 0.10 * k, fm)
        # mouth-corner lines of old age
        if age > 0.6:
            m0 = np.array([side * (c["mouth_w"] + 0.0012), c["mouth_v"] - 0.002])
            pts = np.array([m0, m0 + np.array([side * 0.0012, -0.0060]), m0 + np.array([side * 0.0014, -0.0115])])
            P = pr.face_px(pts[:, 0], pts[:, 1], 0.001)
            pp.stroke(S.resample(P, 8), 0.45, cx.line, alpha=0.25 * age, prof=S.brush_profile(8, 0.3, 0.6, 0.05), clip=fm)
    # frown (川字纹) of a fierce or stern face
    if fierce > 0.25 or age > 0.7:
        a = max(fierce, age * 0.6)
        for uu in (-0.0035, 0.0032):
            pts = np.array([(uu, 0.0105), (uu * 1.15, 0.0170), (uu * 1.4, 0.0235)])
            P = pr.face_px(pts[:, 0], pts[:, 1], 0.002)
            pp.stroke(S.resample(P, 8), 0.5, cx.line, alpha=0.18 + 0.3 * a, prof=S.brush_profile(8, 0.3, 0.5, 0.05), clip=fm)


def huadian(cx):
    """Forehead ornament (花钿) between the brows: a small cinnabar flower."""
    c, pp, pr = cx.c, cx.pp, cx.pr
    if not c.get("huadian"):
        return
    col = c["huadian"] if isinstance(c["huadian"], str) else "#C0362C"
    fm = cx.face
    cen = pr.face_px(0.0, 0.026, 0.001)
    su, sv, ang = _local_scale(pr, 0.0, 0.026)
    for i in range(4):
        a = i * math.pi / 2 + math.pi / 4
        pc = cen[:2] + np.array([math.cos(a) * su, math.sin(a) * sv]) * 0.0016
        pts = S.ellipse_pts(pc, 0.0016 * su, 0.0010 * sv, rot=a, n=16)
        pp.fill(pts, col, alpha=0.9, clip=fm)
    pts = S.ellipse_pts(cen[:2] + np.array([0, -0.0044 * sv]), 0.0008 * su, 0.0018 * sv, n=16)
    pp.fill(pts, col, alpha=0.9, clip=fm)
    pp.fill(S.ellipse_pts(cen[:2], 0.0007 * su, 0.0007 * sv, n=12), "#E8C46A", alpha=0.95, clip=fm)


# =============================================================================================
# entry
# =============================================================================================
def paint_washes(cx):
    skin_washes(cx)


def paint_lines(cx):
    """Features in painting order: wrinkles, brows, eyes, nose, mouth, ornament."""
    wrinkles(cx)
    for side in (-1, 1):
        brow(cx, side)
    for side in (-1, 1):
        eye(cx, side)
    nose(cx)
    mouth(cx)
    huadian(cx)
