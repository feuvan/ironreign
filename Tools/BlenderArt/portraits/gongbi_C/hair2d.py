"""2D hair of gongbi_C.

* :func:`paint_hair`    combed strands (勾丝) along the 3D hair-flow curves, a soft feathered
  hairline (fine strands rooted just below the hairline) and the temple hair (鬓).
* :func:`paint_beard`   moustache, chin beard and side whiskers as hundreds of tapered 丝毛
  strands over a soft wash; roots are anchored on the 3D face (wrapped like the features),
  the hanging part flows in screen space (gravity) in front of the neck and collar.
* :func:`paint_strands` the helmet's red horse-hair tassel (盔缨), hairpin dangles (步摇),
  chest-mirror glints.
"""

import math

import numpy as np

import brush as B
import gear_math as GM
import palette as PL

STRAND_SETS = {
    #            base wash        wash a   strand colours (colour, share, alpha)
    "black": ("#2E2A26", 0.55, [("#14110F", 0.75, 0.85), ("#4A4440", 0.25, 0.7)]),
    "grizzled": ("#3A3632", 0.78, [("#120F0D", 0.52, 0.92), ("#5E5852", 0.26, 0.85),
                                   ("#E6E2D8", 0.22, 0.9)]),
    "grey": ("#8E8880", 0.45, [("#4A4540", 0.30, 0.8), ("#9A948C", 0.35, 0.8),
                               ("#EEEAE0", 0.35, 0.9)]),
    "white": ("#A9A49A", 0.42, [("#7E786E", 0.18, 0.65), ("#F7F4EC", 0.82, 0.95)]),
}


# =============================================================================================
# hair
# =============================================================================================
def paint_hair(cv, pr, meta, npz, spec, masks, seed):
    hp = spec.get("hair", {})
    if hp.get("kind", "topknot") in ("none", "bald"):
        return
    rng = np.random.default_rng(seed + 31)
    col = hp.get("color", "hair")
    light_hair = sum(PL.srgb(col)) > 1.2
    s_col = hp.get("strand") or ("#7A746C" if light_hair else "#5C554E")
    s_col2 = "#F4F1EA" if light_hair else "#0C0A09"
    strokes, strokes2 = [], []
    for c in meta["curves"]:
        if c["style"] != "hairflow":
            continue
        P = pr.world(np.array(c["pts"]))
        P = B.catmull(P, 30)
        v = pr.visible(P, tol=0.02, soft=0.02)
        if v.max() < 0.1:
            continue
        for k in range(3):
            off = (rng.random(2) - 0.5) * cv.k(2.2)
            Q = P.copy()
            Q[:, :2] += off * np.linspace(0.3, 1.0, len(Q))[:, None]
            w = B.profile(len(Q), 0.15, 0.4, "silk", lo=0.1) * 0.55
            if k == 0:
                strokes.append((Q, w, v * 0.55))
            else:
                strokes2.append((Q, w * 0.8, v * 0.5))
    hm = masks["hair"]
    if strokes:
        cv.apply(cv.strokes_mask(strokes, soft=0.3), s_col, "paint", 0.6, clip=np.clip(hm * 1.3, 0, 1))
    if strokes2:
        cv.apply(cv.strokes_mask(strokes2, soft=0.3), s_col2, "paint", 0.5, clip=np.clip(hm * 1.3, 0, 1))
    hairline(cv, pr, spec, hp, rng, light_hair,
             clip=np.clip(masks["hair"] + masks["face"] + masks["skin"], 0, 1))


def hairline(cv, pr, spec, hp, rng, light_hair, clip=None):
    """Fine strands rooted just below the hairline, combed up into the hair (soft edge)."""
    import geo
    import gear_math as GM
    L = geo.head_loft(spec.get("head", {}))
    n = hp.get("fringe_n", 260)
    t = rng.uniform(-1.9, 1.9, n)
    z0 = GM.hairline(hp, t)
    strokes = []
    col = hp.get("color", "hair")
    a = np.linspace(0, 1, 8)[None, :]
    up = z0[:, None] - 0.014 + a * (0.05 + 0.02 * rng.random((n, 1)))
    at = np.abs(t)[:, None]
    tmp = (at > 0.95) & (at < 1.32)
    dn = (z0[:, None] + 0.10 - a * (0.11 + 0.02 * rng.random((n, 1))))[:, ::-1]
    zz = np.where(tmp, dn, up)
    tt = t[:, None] + (rng.random((n, 1)) - 0.5) * 0.02 * a
    P = L.point(zz, tt) + L.normal(zz, tt) * (0.004 + 0.02 * a[..., None] ** 2)
    Q = pr.head(P.reshape(-1, 3)).reshape(n, 8, 3)
    V = pr.visible(Q.reshape(-1, 3), tol=0.008, soft=0.01).reshape(n, 8)
    w = np.linspace(0.08, 0.6, 8)
    for i in range(n):
        if V[i].max() < 0.1:
            continue
        strokes.append((Q[i], w, V[i] * (0.55 + 0.35 * rng.random())))
    if strokes:
        m = cv.strokes_mask(strokes, soft=0.3)
        if clip is not None:
            m = m * clip
        base = "#5A544C" if light_hair else PL.srgb(col)
        cv.apply(m, base, "paint", 0.8, ink=0.4)
        if light_hair:
            cv.apply(B.blur(m, cv.k(0.8)), "#F2EEE6", "paint", 0.5)


# =============================================================================================
# beard
# =============================================================================================
def lock(R, T, wr, rng, n, c1=0.0, c2=0.0, k=18, spread=1.0):
    """Strands of one lock (绺): a cubic S-curve from root R to tip T (2D work px); strands
    fan across ``wr`` px at the root and converge at the tip."""
    R = np.asarray(R, float)
    T = np.asarray(T, float)
    v = T - R
    L = max(np.linalg.norm(v), 1e-6)
    d = v / L
    perp = np.array([-d[1], d[0]])
    P0, P3 = R, T
    P1 = R + v * 0.33 + perp * c1 * L
    P2 = R + v * 0.70 + perp * c2 * L
    s = np.linspace(0, 1, k)[:, None]
    G = ((1 - s) ** 3) * P0 + 3 * ((1 - s) ** 2) * s * P1 + 3 * (1 - s) * s * s * P2 + s ** 3 * P3
    dG = np.gradient(G, axis=0)
    dG /= np.maximum(np.linalg.norm(dG, axis=1, keepdims=True), 1e-9)
    nG = np.stack([-dG[:, 1], dG[:, 0]], -1)
    out = []
    for j in range(n):
        o = (rng.random() * 2 - 1) * spread
        f = rng.uniform(0.55, 1.0) if rng.random() < 0.6 else 1.0
        conv = (1 - s[:, 0]) ** 0.7 * 0.85 + 0.15
        wig = np.sin(s[:, 0] * math.pi * rng.uniform(1.0, 2.2) + rng.random() * 6) * rng.normal() * 0.04 * L * s[:, 0]
        P = G + nG * (o * wr * 0.5 * conv + wig)[:, None]
        m = max(4, int(k * f))
        out.append(P[:m])
    return out


def paint_beard(cv, pr, fc, spec, seed):
    bd = spec.get("beard")
    if not bd:
        return
    rng = np.random.default_rng(seed + 77)
    f = fc.f
    m = f["mouthP"]
    n = f["noseP"]
    L = fc.L
    upx = fc.upx                      # work px per head unit
    base_c, base_a, cols = STRAND_SETS[bd.get("color", "black")]
    layers = {"back": [], "mid": [], "top": []}
    bases = {"back": [], "mid": [], "top": []}
    chin = fc.P(np.array([0.0, 0.0]), np.array([-0.49, -0.40]))
    chin_pt = chin[0]
    near = fc.near
    ws = bd.get("width", 1.0)

    def add(layer, strands, w=0.55, a=(0.55, 0.85)):
        for P in strands:
            layers[layer].append((P, w * rng.uniform(0.8, 1.15), rng.uniform(*a)))

    # ---- side whiskers (髯) along the jaw: hang down and towards the beard ----------------
    ch = bd.get("cheeks")
    cb = bd.get("chin")
    if ch:
        nl = int(14 * ch.get("density", 1.0))
        zs = np.linspace(ch.get("top", -0.10), -0.44, nl)
        for side in (-1, 1):
            Wz = L.width(zs)
            x = side * (Wz - ch.get("depth", 0.06) * 0.5)
            R = fc.P(x, zs, lift=0.008)
            V = pr.visible(R, tol=0.08, soft=0.04)
            for i in range(nl):
                if V[i] < 0.3:
                    continue
                a = (zs[0] - zs[i]) / max(zs[0] - zs[-1], 1e-6)
                ln = upx * (ch.get("len", 0.14) + a * ch.get("grow", 0.25)
                            + a * a * (cb.get("len", 0.3) * 0.7 if cb else 0.0))
                tox = chin_pt[0] - R[i, 0]
                T = R[i, :2] + np.array([tox * (0.25 + 0.45 * a) + rng.normal() * 0.015 * upx, ln])
                wr = upx * 0.055 * ws
                st = lock(R[i, :2], T, wr, rng, 11, c1=side * 0.06, c2=-side * 0.05)
                add("back", st, 0.5)
                bases["back"].append((R[i, :2], T, wr))
    # ---- chin beard (须): locks from under the lower lip and round the chin -----------------
    cb = bd.get("chin")
    if cb:
        length = cb.get("len", 0.4) * upx
        width = cb.get("width", 0.15)
        shape = cb.get("shape", "pointed")
        nl = int(16 * cb.get("density", 1.0))
        ztop = m["z"] - m["lower"] - 0.02
        tip = chin_pt[:2] + np.array([cb.get("lean", 0.0) * upx, length])
        for i in range(nl):
            u = (i + 0.5) / nl * 2 - 1
            x = u * width * (0.9 if shape != "full" else 1.05)
            z = ztop - (1 - abs(u)) * 0.02 - abs(u) ** 1.6 * (ztop + 0.47) * 0.9 - rng.random() * 0.03
            R = fc.P(np.array([x]), np.array([z]), lift=0.008)[0]
            if shape == "pointed":
                T = tip + np.array([u * 0.035 * upx, -abs(u) * 0.15 * length])
            elif shape == "forked":
                T = tip + np.array([np.sign(u) * 0.06 * upx, -abs(u) * 0.12 * length])
            else:   # full beard: a rounded spade
                T = tip + np.array([u * width * 0.55 * upx, -(abs(u) ** 1.5) * 0.30 * length])
            T = T + np.array([rng.normal() * 0.01 * upx, rng.normal() * 0.04 * length])
            wr = upx * (0.05 + 0.02 * (1 - abs(u))) * ws
            cs = rng.normal() * 0.06
            st = lock(R[:2], T, wr, rng, 15, c1=cs + u * 0.06, c2=-cs * 1.3 - u * 0.03, k=22)
            add("mid", st, 0.55)
            bases["mid"].append((R[:2], T, wr))
    # ---- moustache (髭): sweeping locks on the upper lip, on the 3D face --------------------
    ms = bd.get("moustache")
    if ms:
        nl = int(8 * ms.get("density", 1.0))
        z_lip = m["z"] + m["upper"] * 0.5
        z_top = n["tip_z"] - 0.03
        for side in (-1, 1):
            for i in range(nl):
                u = (i + 0.5) / nl
                x0 = side * (0.008 + u * m["w"] * 0.55)
                z0 = z_top - (z_top - z_lip) * (0.15 + 0.6 * u) + rng.normal() * 0.004
                ln = ms.get("len", 0.10) * (0.65 + 0.5 * u)
                a = math.radians(ms.get("angle", 30) + 18 * u)
                kk = 14
                s_ = np.linspace(0, 1, kk)
                xs = x0 + side * ln * math.cos(a) * s_
                zs = z0 - ln * math.sin(a) * s_ - ms.get("droop", 0.05) * s_ ** 2
                C = fc.P(xs, zs, lift=0.010)[:, :2]
                # strands of the lock in screen space round the centre line
                d = np.gradient(C, axis=0)
                d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
                nn = np.stack([-d[:, 1], d[:, 0]], -1)
                wr = upx * 0.028 * ws * ms.get("thick", 1.0)
                for j in range(11):
                    o = (rng.random() * 2 - 1)
                    conv = (1 - s_) ** 0.8 * 0.9 + 0.1
                    P = C + nn * (o * wr * conv)[:, None]
                    mlen = max(4, int(kk * rng.uniform(0.6, 1.0)))
                    layers["top"].append((P[:mlen], 0.5 * rng.uniform(0.8, 1.2), rng.uniform(0.6, 0.9)))
                bases["top"].append((C[0], C[-1], wr))
    # soul patch (a small tuft under the lower lip)
    tp = bd.get("tuft")
    if tp:
        R = fc.P(np.array([0.0]), np.array([m["z"] - m["lower"] - 0.006]), lift=0.009)[0]
        T = R[:2] + np.array([0.0, tp.get("len", 0.05) * upx])
        add("top", lock(R[:2], T, upx * 0.03, rng, 10), 0.45)
    # ---- stubble / shadow -------------------------------------------------------------------
    sb = bd.get("stubble", 0.0)
    if sb > 0:
        for (x, z, r, asp) in ((0.0, -0.42, 0.13, 1.4), (near * 0.19, -0.36, 0.12, 1.0),
                               (-near * 0.19, -0.36, 0.11, 1.0), (0.0, m["z"] + 0.03, 0.07, 2.2)):
            fc.wash_at(x, z, r, "#6A6460", sb, mode="glaze", power=1.0, aspect=asp)
    # ---- render: per layer a soft mass wash, then strands dark -> light --------------------
    for key in ("back", "mid", "top"):
        st = layers[key]
        if not st:
            continue
        polys = []
        for R, T, wr in bases[key]:
            G = np.stack([R + (T - R) * t for t in np.linspace(0, 1, 10)], 0)
            polys.append((G, np.linspace(wr * 1.1, wr * 0.25, 10) / cv.ss, 1.0))
        if polys:
            base = cv.strokes_mask(polys, soft=1.6)
            cv.apply(base, base_c, "paint", base_a * (0.85 if key == "back" else 1.0), ink=0.3)
        groups = {i: [] for i in range(len(cols))}
        shares = np.cumsum([c[1] for c in cols])
        for P, w, a in st:
            g = min(int(np.searchsorted(shares, rng.random() * shares[-1])), len(cols) - 1)
            prof = B.profile(len(P), 0.06, 0.55, "nail", lo=0.05) * w
            groups[g].append((P, prof, a))
        order = sorted(range(len(cols)), key=lambda i: sum(PL.srgb(cols[i][0])))
        for gi in order:
            if groups[gi]:
                mk = cv.strokes_mask(groups[gi], soft=0.2)
                cv.apply(mk, cols[gi][0], "paint", cols[gi][2], ink=0.5)


# =============================================================================================
# tassels, dangles, glints
# =============================================================================================
def paint_strands(cv, pr, meta, spec, seed):
    rng = np.random.default_rng(seed + 5)
    upx = pr.px_per_unit()
    for c in meta["curves"]:
        st = c["style"]
        if st == "tassel":
            a = pr.world(np.array(c["pts"]))[0]
            col = c.get("color", "cinnabar")
            ln = c.get("length", 0.22) * upx
            strokes, strokes2 = [], []
            for i in range(260):
                ang = math.radians(rng.uniform(-170, -10) if rng.random() < 0.75 else rng.uniform(-200, 20))
                v0 = np.array([math.cos(ang), math.sin(ang)])
                L = ln * rng.uniform(0.55, 1.0)
                s = np.linspace(0, 1, 14)[:, None]
                g = np.array([0.0, 1.0]) * (0.9 + 0.4 * rng.random())
                P = a[None, :2] + v0[None] * L * s * 0.75 + g[None] * L * s ** 2 * 0.9
                w = B.profile(14, 0.05, 0.7, "nail", lo=0.05) * 0.75
                (strokes if rng.random() < 0.7 else strokes2).append((P, w, rng.uniform(0.6, 0.95)))
            base = cv.strokes_mask([(P, np.full(len(P), 4.0) * np.linspace(1, 0.3, len(P)), 1.0)
                                    for P, _, _ in strokes[::4]], soft=1.5)
            cv.apply(base, col, "paint", 0.55)
            cv.apply(cv.strokes_mask(strokes, soft=0.22), col, "paint", 0.9, ink=0.2)
            cv.apply(cv.strokes_mask(strokes2, soft=0.22), PL.deepen(col, 0.6), "paint", 0.85,
                     ink=0.3)
        elif st == "dangle":
            a = pr.world(np.array(c["pts"]))[0]
            k, tot = c.get("n", 0), max(1, c.get("total", 1))
            ln = c.get("length", 0.1) * upx
            off = (k - (tot - 1) / 2) * cv.k(3.0)
            P = np.stack([a[0] + off * np.linspace(0, 1, 10) * 0.6 + rng.normal() * 0.5,
                          a[1] + np.linspace(0, ln, 10)], -1)
            cv.stroke(P, np.full(10, 0.45), "gold_d", 0.85)
            # beads / pearls along the chain
            for j, t in enumerate((0.35, 0.7, 1.0)):
                q = P[int(t * 9)]
                r = cv.k(1.3 if j < 2 else 2.0)
                colb = "pearl" if j % 2 == 0 else c.get("color", "gold")
                cv.radial(q[:2], r, colb, 0.95, mode="paint", power=0.25)
                cv.radial(q[:2] + np.array([-0.3 * r, -0.3 * r]), r * 0.45, "#FFFFFF", 0.5,
                          mode="paint", power=0.5)
        elif st == "mirror":
            q = pr.world(np.array(c["pts"]))[0]
            r = c.get("r", 0.17) * upx
            # a crescent glint on the polished disc (painted, not lit)
            cv.radial(q[:2] + np.array([-0.25 * r, -0.25 * r]), r * 0.45, "#F2F2EA", 0.55,
                      mode="paint", power=1.5, aspect=0.6, angle=math.radians(-40))
