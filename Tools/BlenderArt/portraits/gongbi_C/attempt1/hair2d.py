"""Hair strokes for gongbi_C (2D): temple hair along the 3D hairline, beards grown on the face
surface, and the designed 3D strand curves (helmet tassels, 步摇 chains, earrings).

Beards are grown strand by strand in face space from root zones (moustache 髭, chin beard 须,
cheek beard 髯), with gravity and an optional curl, draped over the front-most surface of the
bust (the exported ``h_front`` grid) so a long beard falls over the collar and armour in true
3/4 perspective.  Every strand is a tapered brush stroke, depth tested against the 3D render.
"""

import math

import numpy as np

import strokes as S
from looks import PAL, mix

BEARD_COLORS = {
    "black": [("#141010", 0.55), ("#2E2824", 0.35), ("#4A423C", 0.10)],
    "grizzled": [("#1C1816", 0.36), ("#3E3832", 0.24), ("#7A746C", 0.22), ("#E8E4DC", 0.18)],
    "grey": [("#5E5852", 0.3), ("#9A948C", 0.35), ("#E6E0D6", 0.35)],
    "white": [("#FBF8F2", 0.55), ("#DCD6CC", 0.27), ("#9A948A", 0.18)],
    "brown": [("#2A1E16", 0.5), ("#4A3626", 0.4), ("#7A5E44", 0.1)],
}
BEARD_BASE = {"black": "#3A3430", "grizzled": "#5A544E", "grey": "#8A847C", "white": "#B8B2A8",
              "brown": "#4A3A2E"}


def paint(cx, spec, meta, npz):
    hairline(cx, spec, meta)
    strands(cx, meta)
    beard(cx, spec)


# =============================================================================================
def hairline(cx, spec, meta):
    """Fine strokes and a soft ink edge where the hair meets the forehead and temples."""
    pp, pr = cx.pp, cx.pr
    hl = [c for c in meta["curves"] if c["style"] == "hairline"]
    up = [c for c in meta["curves"] if c["style"] == "hairline_up"]
    if not hl or not up:
        return
    base = np.array(hl[0]["pts"])
    top = np.array(up[0]["pts"])
    col = hl[0].get("color", "#1C1814")
    light = hl[0].get("light", False)
    B = pr.world_px(base)
    T = pr.world_px(top)
    visB = pr.visible(B, 0.0025)
    # soft edge wash (hair side), only where the hairline is visible
    E = B[:, :2] + (T[:, :2] - B[:, :2]) * 0.45
    for i in range(len(B) - 1):
        if visB[i] > 0.5 and visB[i + 1] > 0.5:
            quad = np.array([B[i, :2], B[i + 1, :2], E[i + 1], E[i]])
            pp.fill(quad, col, alpha=0.30 if not light else 0.22, mode="glaze" if not light else "paint", soft=0.6)
    rng = cx.rng
    n = int(hl[0].get("n", 160))
    for i in range(n):
        t = rng.uniform(0, len(base) - 1.001)
        j = int(t)
        f = t - j
        b = base[j] * (1 - f) + base[j + 1] * f
        tp = top[j] * (1 - f) + top[j + 1] * f
        d = tp - b
        L = rng.uniform(0.45, 1.0)
        root = b - d * rng.uniform(0.02, 0.12)
        mid = root + d * L * 0.5 + rng.normal(0, 0.0008, 3)
        tip = root + d * L + rng.normal(0, 0.0012, 3)
        P = pr.world_px(S.bezier(root, mid, mid, tip, 6))
        vis = pr.visible(P, 0.0025)
        if vis[0] < 0.5:
            continue
        pp.stroke(P, rng.uniform(0.35, 0.5), col, alpha=rng.uniform(0.55, 0.85), alphas=vis,
                  prof=S.brush_profile(len(P), 0.15, 0.6, 0.05, "tail"), mode="paint", ink=not light)


# =============================================================================================
def strands(cx, meta):
    pp, pr = cx.pp, cx.pr
    cs = [c for c in meta["curves"] if c["style"] in ("strand", "chain")]
    # dark first so the bright strands sit on top
    cs.sort(key=lambda c: sum(_lum(c.get("color", "#000000"))))
    for c in cs:
        P = pr.world_px(np.array(c["pts"]))
        P = S.resample(P, max(6, len(P) * 2))
        vis = pr.visible(P, c.get("tol", 0.006)) if c.get("test", True) else np.ones(len(P))
        if c["style"] == "strand":
            prof = S.brush_profile(len(P), 0.08, 0.7, 0.05, "tail")
            pp.stroke(P, c.get("w", 0.9), c.get("color", "cinnabar"), alpha=c.get("a", 0.9), alphas=vis,
                      prof=prof, ink=False)
        else:
            pp.stroke(P, c.get("w", 0.5), c.get("color", "#B08A3A"), alpha=0.9, alphas=vis, ink=False)


def _lum(h):
    from looks import srgb
    if isinstance(h, (list, tuple)):
        return tuple(h)
    return srgb(PAL.get(h, h))


# =============================================================================================
def beard(cx, spec):
    b = spec["face"].get("beard")
    if not b:
        return
    import canon
    kind = b.get("kind", "none")
    z = canon.BEARDS.get(kind)
    if not z:
        return
    z = dict(z)
    z.update({k: v for k, v in b.items() if k in ("moustache", "chin", "cheek", "curl", "base", "alpha")})
    color = b.get("color", "black")
    pal = BEARD_COLORS[color] if isinstance(color, str) and color in BEARD_COLORS else color
    pp, pr, c = cx.pp, cx.pr, cx.c
    rng = np.random.default_rng(cx.rng.integers(1 << 30))
    curl = z.get("curl", 0.0)
    scale = b.get("length", 1.0)
    chin_v = c["mouth_v"] - 0.043
    zones = []
    if z.get("cheek"):
        zones.append(("cheek", z["cheek"]))
    if z.get("chin"):
        zones.append(("chin", z["chin"]))
    if z.get("moustache"):
        zones.append(("moustache", z["moustache"]))
    all_px = []
    strands_ = []
    for zn, zp in zones:
        n = int(zp.get("n", 40) * b.get("density", 1.0))
        for i in range(n):
            lock = None
            if zn == "moustache":
                side = -1 if i % 2 else 1
                r = rng.uniform(0.0, 1.0) ** 0.8
                u0 = side * (0.0025 + r * (c["mouth_w"] * 0.92))
                vtop = -c["nose_len"] - 0.0018
                vbot = c["mouth_v"] + c["lip_up"] * (1.0 - 0.6 * r) + 0.0008
                v0 = vbot + (vtop - vbot) * rng.uniform(0.15, 0.85) * (1 - 0.5 * r)
                ang = math.radians(-12 - 55 * zp.get("droop", 0.6) * (0.4 + 0.6 * r) + rng.normal(0, 6))
                d = np.array([side * math.cos(ang), math.sin(ang)])
                L = zp["len"] * scale * (0.55 + 0.45 * r) * rng.uniform(0.8, 1.15)
                wbase = zp.get("w", 0.8)
                grav = 0.9 * zp.get("droop", 0.6)
            elif zn == "chin":
                wdt = zp.get("width", 0.014)
                u0 = rng.uniform(-1, 1) * wdt
                v0 = rng.uniform(chin_v + 0.002, c["mouth_v"] - c["lip_low"] - 0.003)
                sp = zp.get("spread", 0.5)
                d = np.array([u0 / max(wdt, 1e-6) * 0.35 * sp + rng.normal(0, 0.08), -1.0])
                d /= np.linalg.norm(d)
                L = zp["len"] * scale * rng.uniform(0.65, 1.1) * (1 - 0.3 * abs(u0) / max(wdt, 1e-6))
                wbase = 0.95
                grav = 0.3
                lock = (0.0, zp.get("converge", 0.0))
            else:   # cheek: along the jaw from the sideburn to the chin
                t = rng.uniform(0, 1) ** 0.9
                side = -1 if i % 2 else 1
                top = zp.get("top", -0.01)
                u0 = side * (0.063 - 0.040 * t ** 1.1) * rng.uniform(0.86, 1.0)
                v0 = top + (chin_v + 0.008 - top) * t ** 0.8 + rng.normal(0, 0.0025)
                # root a little up the cheek from the jaw line
                v0 += rng.uniform(0.0, 0.012) * (1 - t)
                d = np.array([-side * (0.05 + 0.30 * t), -1.0])
                d /= np.linalg.norm(d)
                L = zp["len"] * scale * (0.40 + 0.60 * t) * rng.uniform(0.75, 1.1)
                wbase = 0.9
                grav = 0.2
                if zp.get("locks"):
                    lock = (side * 0.028, 0.55)
            strands_.append((zn, u0, v0, d, L, wbase, grav, lock))
    # grow every strand in face space, drape over the front-most surface
    s = pr.s
    for zn, u0, v0, d, L, wbase, grav, lock in strands_:
        nseg = 14
        pts = [np.array([u0, v0])]
        dirv = d.copy()
        ph = rng.uniform(0, 2 * math.pi)
        for k in range(nseg):
            dirv = dirv + np.array([0.0, -grav * 0.12])
            if curl > 0:
                a = curl * 0.55 * math.sin(ph + k * 0.9)
                ca, sa = math.cos(a), math.sin(a)
                dirv = np.array([dirv[0] * ca - dirv[1] * sa, dirv[0] * sa + dirv[1] * ca])
            dirv /= np.linalg.norm(dirv)
            pts.append(pts[-1] + dirv * L / nseg)
        Q = np.array(pts)
        if lock is not None and lock[1] > 0:
            f = np.linspace(0, 1, len(Q)) ** 1.5 * lock[1]
            Q[:, 0] = Q[:, 0] * (1 - f) + lock[0] * f
        u, v = Q[:, 0] * s, Q[:, 1] * s
        hf = pr.h_face(u, v)
        hfr = pr.h_front(u, v)
        hfr = np.where(np.isfinite(hfr), hfr, -1.0)
        h = np.zeros(len(Q))
        h[0] = hf[0] + 0.0015 * s
        for k in range(1, len(Q)):
            surf = max(hfr[k], hf[k] if pr.hh_ok[_gi(pr, v[k])][_gj(pr, u[k])] else -1.0) + 0.003 * s
            h[k] = max(h[k - 1] - 0.0045 * s * (L / 0.05), surf)
        P = pr.face_px(u, v, h=h, scaled=False)
        all_px.append(P)
    if not all_px:
        return
    # beard mass: every strand laid first as a broad soft stroke (the 墨底 under-wash), so the
    # mass follows the locks and thins out towards their tips
    base_col = BEARD_BASE.get(color, "#4A443C") if isinstance(color, str) else "#4A443C"
    light = isinstance(color, str) and color in ("white", "grey", "grizzled")
    mass = np.zeros((pp.H, pp.W), np.float32)
    for (zn, *_r), P in zip(strands_, all_px):
        vis = pr.visible(P, 0.008)
        t = np.linspace(0, 1, len(P))
        R = 0.5 * pp.k(3.2 if zn != "moustache" else 2.4) * (0.55 + 0.45 * np.sin(np.pi * np.clip(t * 1.2, 0, 1)))
        A = vis * S.smoothstep(0.0, 0.3, t) * (1 - S.smoothstep(0.55, 1.0, t))
        cov = S.capsule_chain(pp.H, pp.W, P[:, :2], R, A)
        if cov is None:
            continue
        y0, x0, cv = cov
        sub = mass[y0:y0 + cv.shape[0], x0:x0 + cv.shape[1]]
        np.maximum(sub, cv, out=sub)
    mass = S.blur(mass, pp.k(1.2))
    pp.layer(mass, base_col, mode="paint" if light else "glaze", alpha=min(0.9, z.get("base", 0.5)))
    # strands: thin tapered lines that fade in from the skin (roots) and out at the tips
    order = rng.permutation(len(all_px))
    for idx in order:
        P = all_px[idx]
        vis = pr.visible(P, 0.008)
        vis = S.blur(vis[None], 0.8)[0]
        r = rng.random()
        acc = 0.0
        colr = pal[-1][0]
        for cc, wgt in pal:
            acc += wgt
            if r <= acc:
                colr = cc
                break
        zn = strands_[idx][0]
        wbase = strands_[idx][5]
        t = np.linspace(0, 1, len(P))
        fade = S.smoothstep(0.0, 0.22 if zn != "chin" else 0.12, t) * 0.85 + 0.15
        prof = S.brush_profile(len(P), 0.06, 0.75, 0.04, "tail")
        pp.stroke(P, wbase * rng.uniform(0.65, 0.95), colr, alpha=z.get("alpha", 0.92) * rng.uniform(0.75, 1.0),
                  alphas=vis * fade, prof=prof, mode="paint", ink=_dark(colr))


def _dark(h):
    return sum(_lum(h)) < 1.2


def _gi(pr, v):
    return int(np.clip(round((v - pr.vs[0]) / (pr.vs[1] - pr.vs[0])), 0, len(pr.vs) - 1))


def _gj(pr, u):
    return int(np.clip(round((u - pr.us[0]) / (pr.us[1] - pr.us[0])), 0, len(pr.us) - 1))


def _hull(P):
    """Convex hull (monotone chain)."""
    P = np.unique(np.round(P, 1), axis=0)
    P = P[np.lexsort((P[:, 1], P[:, 0]))]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in P:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in P[::-1]:
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1])


def _shrink(H, k):
    c = H.mean(0)
    return c + (H - c) * k
