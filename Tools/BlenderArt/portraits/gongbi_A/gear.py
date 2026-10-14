"""Hair, headgear, beards and ornaments.

Hair masses and caps are skull shells (shells.Skull) with exact hairline / rim cuts; buns and
loops are swept tubes; beards, moustaches, long brows and plumes are Cycles curves drawn as ink
strokes (a soft wide wash pass under fine dark lines, like 丝毛 hair painting).
"""

import math

import numpy as np

import geo
import shade
import shells
from palette import hex_rgb

D2R = math.pi / 180.0


def skull(C):
    if getattr(C, "skull", None) is None:
        C.skull = shells.Skull(C.H)
        C.skullR = C.skull.radius(1.5, 1.5)
    return C.skull, C.skullR


def interp_deg(table):
    """[(azimuth deg, polar deg), ...] symmetric profile -> fn(p radians) -> t radians."""
    ps = np.array([a for a, _ in table], np.float64)
    ts = np.array([b for _, b in table], np.float64)

    def f(p):
        d = abs(((p / D2R) + 180.0) % 360.0 - 180.0)
        return float(np.interp(d, ps, ts)) * D2R
    return f


# ------------------------------------------------------------------------------- materials
def hair_material(name, color="hair", streak=0.12, tint="#0E0D0C", ao=0.5, edge=0.45):
    m = shade._mat(name)
    nb = shade.NB(m)
    uv = nb.sep(nb.uv())
    q = nb.comb(nb.math("MULTIPLY", uv[0], 260.0), nb.math("MULTIPLY", uv[1], 2.0), 0.0)
    s = nb.noise(q, 1.0, 2.0, 0.5)
    c = shade.rgb(color)
    light = shade.rgb(tuple(min(1, x * 1.0 + 0.16) for x in hex_rgb(color)))
    col = nb.mix(nb.math("MULTIPLY", nb.smooth(s, 0.45, 0.75), streak * 4), c, light)
    nb.out(col, shade.rgb(tint), shade.shade_term(nb, ao, 0.03, edge, 0.4), 0.0, 3.0)
    return m


def strand_material(name, color, ink=1.0, veil=1.0):
    """Curves (beards, plumes) are invisible to Freestyle, so they write ``veil``: the finish
    hides the brush lines of whatever lies behind them."""
    m = shade._mat(name)
    nb = shade.NB(m)
    nb.out(shade.rgb(color), shade.rgb(color), 0.0, ink, 3.0, aok=0.0, veil=veil)
    return m


# ------------------------------------------------------------------------------------ hair
def hair_cap(C, Hc, parent):
    """Scalp hair: a thin shell cut at the hairline (front hairline, temples, sideburns,
    behind the ears, nape).  Hc: dict(line=[(az, polar)...], thick, top, color)."""
    S, R = skull(C)
    line = interp_deg(Hc.get("line", [(0, 58), (30, 63), (55, 76), (75, 98), (90, 92),
                                       (115, 105), (150, 122), (180, 126)]))
    th = Hc.get("thick", 0.005)
    top = Hc.get("top", 0.012)

    def off(p, t, v):
        # thick on the crown, thinning to almost nothing at the hairline
        return th + top * (1 - v) ** 1.5 - (th * 0.85) * np.clip((v - 0.85) / 0.15, 0, 1)
    mat = hair_material("Hair", Hc.get("color", "hair"))
    ob = S.shell("HairCap", C.cols["hair"], mat, R, line, nu=120, nv=36, offset_fn=off,
                 parent=parent)
    return [ob]


def tube(path, radius, nr=12, closed=False):
    """Sweep a circle along a 3D path; radius scalar or per point.  Returns V, F."""
    path = np.asarray(path, np.float64)
    n = len(path)
    rad = np.full(n, radius) if np.isscalar(radius) else np.asarray(radius)
    T = np.gradient(path, axis=0)
    if closed:
        T = np.roll(path, -1, 0) - np.roll(path, 1, 0)
    T /= np.linalg.norm(T, axis=1, keepdims=True) + 1e-12
    ref = np.array([0, 0, 1.0]) if abs(T[0][2]) < 0.9 else np.array([1.0, 0, 0])
    N = np.cross(T[0], ref)
    N /= np.linalg.norm(N)
    V = []
    for i in range(n):
        N = N - T[i] * np.dot(N, T[i])
        N /= np.linalg.norm(N) + 1e-12
        B = np.cross(T[i], N)
        for k in range(nr):
            a = 2 * math.pi * k / nr
            V.append(path[i] + rad[i] * (math.cos(a) * N + math.sin(a) * B))
    F = []
    segs = n if closed else n - 1
    for i in range(segs):
        i1 = (i + 1) % n
        for k in range(nr):
            k1 = (k + 1) % nr
            F.append((i * nr + k, i1 * nr + k, i1 * nr + k1, i * nr + k1))
    if not closed:
        V.append(path[0])
        V.append(path[-1])
        c0, c1 = len(V) - 2, len(V) - 1
        for k in range(nr):
            k1 = (k + 1) % nr
            F.append((c0, k1, k))
            F.append((c1, (n - 1) * nr + k, (n - 1) * nr + k1))
    return np.array(V), F


def ellipsoid(center, radii, n=24, m=16, frame=None):
    vv, ff = geo.lathe([(math.sin(a), -math.cos(a)) for a in np.linspace(0.02, math.pi - 0.02, m)],
                       n)
    vv = vv * np.asarray(radii)
    if frame is not None:
        vv = vv @ np.asarray(frame).T
    vv = vv + np.asarray(center)
    ff = [f[::-1] for f in ff]
    k = len(vv)
    vv = np.vstack([vv, [center + (np.asarray(frame) @ [0, 0, -radii[2]] if frame is not None
                                   else [0, 0, -radii[2]])],
                    [center + (np.asarray(frame) @ [0, 0, radii[2]] if frame is not None
                               else [0, 0, radii[2]])]])
    for i in range(n):
        i1 = (i + 1) % n
        ff.append((k, i1, i))
        ff.append((k + 1, (m - 1) * n + i, (m - 1) * n + i1))
    return vv, ff


def topknot(C, K, parent):
    """男子发髻 topknot: a bun on the crown wrapped by a band, optional crown (冠) and pin."""
    S, R = skull(C)
    top = S.point(R, np.array([0.0]), np.array([K.get("tilt", 14) * D2R]), 0.0)[0]
    c = top + np.array([0, K.get("back", 0.006), K.get("lift", 0.02)])
    rr = K.get("r", 0.026)
    V, F = ellipsoid(c, (rr, rr * 0.9, rr * 1.05))
    mat = hair_material("Bun", K.get("color", "hair"))
    out = [geo.mesh_obj("Bun", V, F, C.cols["hair"], mat, smooth=True, parent=parent)]
    if K.get("crown"):
        # small gilt crown (小冠) clasping the bun, with a cross pin
        cr = K["crown"]
        prof = [(rr * 1.05, -rr * 0.9), (rr * 1.12, -rr * 0.2), (rr * 1.0, rr * 0.6),
                (rr * 0.55, rr * 1.15), (0.0, rr * 1.2)]
        vv, ff = geo.lathe(prof, 36)
        vv = vv * np.array([1.0, 0.85, 1.0]) + c
        mat = shade.flat("Crown", cr.get("color", "gold"), None, ao=0.3, edge=0.5, edge0=0.3)
        out.append(geo.mesh_obj("Crown", vv, [f[::-1] for f in ff], C.cols["robe"], mat,
                                parent=parent))
        pin = np.array([c + np.array([-0.06, 0.0, 0.006]), c + np.array([0.06, 0.0, 0.006])])
        V2, F2 = tube(pin, 0.0022, 8)
        out.append(geo.mesh_obj("Pin", V2, F2, C.cols["robe"],
                                shade.flat("Pin", cr.get("pin", "gold_light"), None, ao=0.1),
                                parent=parent))
    return out


# ---------------------------------------------------------------------------------- helmet
def helmet(C, Hm, parent):
    """Song-style general's helmet: iron bowl with a gilt brow band and peak, flared neck
    guard (顿项), a finial with a red horse-hair tassel (盔缨)."""
    S, R = skull(C)
    rim = interp_deg(Hm.get("rim", [(0, 66), (40, 70), (80, 80), (120, 88), (180, 92)]))
    th = Hm.get("thick", 0.016)
    col = C.cols["robe"]
    out = []

    def off(p, t, v):
        return th + Hm.get("dome", 0.012) * (1 - v) ** 2
    bowl_mat = shade.flat("Helmet", Hm.get("color", "iron"), "#14181E", ao=0.4, edge=0.45,
                          edge0=0.35, pattern=_helmet_ribs(Hm))
    bowl = S.shell("Helmet", col, bowl_mat, R, rim, nu=120, nv=30, offset_fn=off, parent=parent)
    out.append(bowl)
    # brow band: a raised gilt band along the rim
    pp = np.linspace(0, 2 * math.pi, 160, endpoint=False)
    tr = np.array([rim(p) for p in pp])
    bw = Hm.get("band_w", 9.0) * D2R
    V, UV = [], []
    nv = 5
    for j in range(nv):
        v = j / (nv - 1)
        tt = tr - bw * v
        V.append(S.point(R, pp, tt, th + 0.0035 + Hm.get("dome", 0.012) * 0.0))
        UV.append(np.stack([pp / (2 * math.pi), np.full(len(pp), v)], 1))
    V = np.vstack(V)
    F = [f for f in geo.grid_faces(len(pp), nv, wrap_u=True)]
    import patterns as pat
    bmat = shade.flat("HelmBand", Hm.get("band", "gold"), "#6B4A1A", ao=0.3, edge=0.4,
                      pattern=pat.band("ochre", "ochre", rep=40, amount=0.55, kind="dots"))
    out.append(geo.mesh_obj("HelmBand", V, F, col, bmat, smooth=True, uvs=np.vstack(UV),
                            parent=parent))
    # peak (眉庇): a short curved brim in front
    ps = np.linspace(-Hm.get("peak_span", 75) * D2R, Hm.get("peak_span", 75) * D2R, 40)
    tr2 = np.array([rim(p) for p in ps])
    inner = S.point(R, ps, tr2, th + 0.002)
    fwd = S.dir(ps, tr2)
    fwd[:, 2] = 0
    fwd /= np.linalg.norm(fwd, axis=1, keepdims=True)
    depth = Hm.get("peak", 0.022) * np.cos(ps / (Hm.get("peak_span", 75) * D2R) * math.pi / 2) ** 0.6
    outer = inner + fwd * depth[:, None] + np.array([0, 0, -0.004])
    V = np.vstack([inner, outer])
    n = len(ps)
    F = [(i, i + 1, n + i + 1, n + i) for i in range(n - 1)]
    pk = geo.mesh_obj("HelmPeak", V, F, col, shade.flat("HelmPeak", Hm.get("band", "gold"),
                                                        "#6B4A1A", ao=0.3, edge=0.3),
                      smooth=True, parent=parent)
    m = pk.modifiers.new("Solid", "SOLIDIFY")
    m.thickness = 0.003
    out.append(pk)
    # neck guard (顿项): flared skirt around the sides and back
    if Hm.get("neck_guard", True):
        a0, a1 = Hm.get("guard_from", 62) * D2R, (360 - Hm.get("guard_from", 62)) * D2R
        ps = np.linspace(a0, a1, 90)
        tr = np.array([rim(p) for p in ps])
        nvg = 14
        V, UV = [], []
        L = Hm.get("guard_len", 0.085)
        for j in range(nvg):
            v = j / (nvg - 1)
            base = S.point(R, ps, tr, th)
            d = S.dir(ps, tr)
            d[:, 2] = 0
            d /= np.linalg.norm(d, axis=1, keepdims=True)
            P = base + np.array([0, 0, -L * v]) + d * (Hm.get("flare", 0.045) * v ** 1.4 + 0.004)
            V.append(P)
            UV.append(np.stack([ps / (2 * math.pi), np.full(len(ps), v * L)], 1))
        V = np.vstack(V)
        F = [f[::-1] for f in geo.grid_faces(len(ps), nvg)]
        gmat = shade.flat("NeckGuard", Hm.get("guard", "iron"), "#14181E", ao=0.5, edge=0.35,
                          pattern=pat.lamellar(Hm.get("guard", "iron"),
                                               Hm.get("guard_light", "#7E878F"),
                                               rep_u=70, rows_per_m=70,
                                               lacing=Hm.get("lacing", "cinnabar")))
        g = geo.mesh_obj("NeckGuard", V, F, col, gmat, smooth=True, uvs=np.vstack(UV),
                         parent=parent)
        m = g.modifiers.new("Solid", "SOLIDIFY")
        m.thickness = 0.003
        out.append(g)
        # gilt hem band on the guard
    # finial + tassel
    topp = S.point(R, np.array([0.0]), np.array([0.0]), th + Hm.get("dome", 0.012))[0]
    stem = np.array([topp - [0, 0, 0.004], topp + [0, 0, Hm.get("stem", 0.03)]])
    rad = np.array([0.006, 0.0035])
    V, F = tube(geo.resample(stem, 8), np.linspace(rad[0], rad[1], 8), 10)
    out.append(geo.mesh_obj("Finial", V, F, col, shade.flat("Finial", "gold", "#6B4A1A",
                                                           ao=0.2, edge=0.4), parent=parent))
    ball_c = topp + [0, 0, Hm.get("stem", 0.03) + 0.006]
    V, F = ellipsoid(ball_c, (0.008, 0.008, 0.009))
    out.append(geo.mesh_obj("FinialBall", V, F, col, shade.flat("FinialBall", "gold", "#6B4A1A",
                                                               ao=0.2, edge=0.5), parent=parent))
    if Hm.get("tassel", True):
        out += tassel(C, ball_c + [0, 0, 0.004], Hm, parent)
    return out


def _helmet_ribs(Hm):
    """Bowl painted as riveted segments (vertical ribs) with a soft top highlight."""
    def f(nb, p):
        uv = nb.sep(nb.uv())
        u = nb.math("MULTIPLY", uv[0], float(Hm.get("ribs", 12)))
        s = nb.math("ABSOLUTE", nb.math("SUBTRACT", nb.math("FRACT", u), 0.5))
        rib = nb.math("SUBTRACT", 1.0, nb.smooth(nb.math("SUBTRACT", 0.5, s), 0.0, 0.05))
        col = nb.mix(nb.smooth(uv[1], 0.2, 1.2), shade.rgb(Hm.get("color_light", "iron_light")), p)
        col = nb.mix(nb.math("MULTIPLY", rib, 0.75), col, shade.rgb("gold"))
        return col
    return f


def tassel(C, root, Hm, parent):
    """盔缨: a burst of red horse-hair falling back and down from the finial."""
    rng = C.rng
    n = Hm.get("tassel_n", 260)
    strands, radii = [], []
    L0 = Hm.get("tassel_len", 0.075)
    back = np.array([0.0, 1.0, 0.0])
    for i in range(n):
        ang = rng.uniform(0, 2 * math.pi)
        spread = rng.uniform(0.2, 1.0)
        d0 = np.array([math.cos(ang) * spread, math.sin(ang) * spread * 0.7 + 0.5, 0.9])
        d0 /= np.linalg.norm(d0)
        L = L0 * rng.uniform(0.6, 1.1)
        pts = [root.copy()]
        p = root.copy()
        d = d0.copy()
        for k in range(10):
            p = p + d * L / 10
            d = d + np.array([0, 0.22, -0.5]) + rng.normal(0, 0.03, 3)
            d /= np.linalg.norm(d)
            pts.append(p.copy())
        strands.append(np.array(pts))
        r0 = 0.0011
        radii.append(np.linspace(r0, r0 * 0.25, len(pts)))
    mat = strand_material("Tassel", Hm.get("tassel_col", "cinnabar"), ink=0.0)
    ob = geo.strands_obj("Tassel", strands, radii, C.cols["fine"], mat, parent=parent)
    # darker red accents
    strands2 = strands[::4]
    radii2 = [r * 0.6 for r in radii[::4]]
    mat2 = strand_material("Tassel2", "carmine", ink=0.0)
    ob2 = geo.strands_obj("Tassel2", strands2, radii2, C.cols["fine"], mat2, parent=parent)
    return [ob, ob2]


# ----------------------------------------------------------------------------- scholar hat
def tall_hat(C, Ht, parent):
    """东坡巾-like tall square black gauze cap with an outer front panel."""
    S, R = skull(C)
    ez = C.H.eye_z
    c = S.c
    col = C.cols["robe"]
    half = Ht.get("half", 0.075)
    zb_front = ez + Ht.get("rim_front", 0.05)
    zb_back = ez + Ht.get("rim_back", 0.012)
    h = Ht.get("height", 0.135)
    out = []

    def layer(name, half_x, half_y, z0f, z0b, height, ofs_y, color, pattern):
        nu, nv = 64, 18
        a = np.linspace(0, 2 * math.pi, nu, endpoint=False)
        ex = 6.0
        # superellipse rounded square
        sx = np.sign(np.sin(a)) * np.abs(np.sin(a)) ** (2 / ex) * half_x
        sy = -np.sign(np.cos(a)) * np.abs(np.cos(a)) ** (2 / ex) * half_y
        z0 = z0b + (z0f - z0b) * (0.5 + 0.5 * np.cos(a))
        V, UV = [], []
        for j in range(nv):
            v = j / (nv - 1)
            taper = 1.0 + Ht.get("flare", 0.08) * v
            V.append(np.stack([sx * taper, c[1] + ofs_y + sy * taper, z0 + (c[2] + height - z0) * v
                               - 0 * v], 1))
            UV.append(np.stack([a / (2 * math.pi), np.full(nu, v)], 1))
        V = np.vstack(V)
        F = geo.grid_faces(nu, nv, wrap_u=True)
        top = len(V)
        ctr = np.array([0, c[1] + ofs_y, c[2] + height])
        V = np.vstack([V, ctr[None]])
        UV = np.vstack(UV + [np.array([[0.5, 1.0]])])
        last = (nv - 1) * nu
        F += [(last + i, last + (i + 1) % nu, top) for i in range(nu)]
        mat = shade.flat(name, color, "#0A0A0A", ao=0.35, edge=0.4, pattern=pattern)
        return geo.mesh_obj(name, V, F, col, mat, smooth=False, uvs=UV, parent=parent)

    gauze = _gauze(Ht)
    out.append(layer("HatInner", half, half * 1.05, zb_front, zb_back, h, 0.004,
                     Ht.get("color", "#2A2A2C"), gauze))
    if Ht.get("outer", True):
        out.append(layer("HatOuter", half * 1.06, half * 1.1, zb_front - 0.003, zb_back - 0.004,
                         h * 0.5, 0.0, Ht.get("color", "#2A2A2C"), gauze))
    for ob in out:
        m = ob.modifiers.new("Solid", "SOLIDIFY")
        m.thickness = 0.002
    return out


def _gauze(Ht):
    def f(nb, p):
        uv = nb.sep(nb.uv())
        g = nb.math("MULTIPLY", nb.math("ABSOLUTE", nb.math("SINE", nb.math("MULTIPLY", uv[0], 900.0))),
                    nb.math("ABSOLUTE", nb.math("SINE", nb.math("MULTIPLY", uv[1], 300.0))))
        return nb.mix(nb.math("MULTIPLY", g, 0.12), p, shade.rgb("#5A5A5E"))
    return f


# ------------------------------------------------------------------------------- beards
def _in_poly(pts, poly):
    x, y = pts[:, 0], pts[:, 1]
    inside = np.zeros(len(pts), bool)
    px, py = poly[:, 0], poly[:, 1]
    j = len(poly) - 1
    for i in range(len(poly)):
        cond = ((py[i] > y) != (py[j] > y)) & (x < (px[j] - px[i]) * (y - py[i]) /
                                                (py[j] - py[i] + 1e-12) + px[i])
        inside ^= cond
        j = i
    return inside


def _front_y(C, x, z):
    """y of the torso front (robe surface) at face coords (x, z), for keeping strands in front."""
    import costume
    T, R = costume.torso(C)
    r = T.sample(R, 0.0, z)
    a = math.asin(max(-0.9, min(0.9, x / max(r, 1e-3))))
    r = T.sample(R, a, z) + 0.02
    return T.yc - r * math.cos(a)


def lock(C, root, spread, n, length, direction=(0.0, -1.0), sway=0.0, curl=0.0, tip=0.25,
         forward=0.012, rng=None, radius=0.00028, lift=-0.0006, droop=1.0, flow_amp=0.12,
         hug=0.0, hug_off=0.0009):
    """One flowing lock of hair (a 绺): n strands rooted in an ellipse around ``root`` (face
    coords x, z), following a shared spine that leaves along ``direction`` and falls with
    gravity, converging toward the tip (``tip`` = remaining spread fraction)."""
    rng = rng or C.rng
    surf = C.H.surf
    pts = np.asarray(root) + rng.normal(0, 1, (n, 2)) * np.asarray(spread) * 0.5
    roots = surf.project(pts, lift)
    r0c = surf.project(np.asarray(root)[None], lift)[0]
    d0 = np.array([direction[0], 0.0, direction[1]])
    d0 /= np.linalg.norm(d0) + 1e-9
    seg = 16
    # shared spine
    spine = [r0c]
    p = r0c.copy()
    d = d0.copy()
    for s in range(seg):
        t = (s + 1) / seg
        p = p + d * length / seg
        p[1] = min(p[1], r0c[1]) - forward / seg
        try:
            yf = _front_y(C, p[0], p[2])
            p[1] = min(p[1], yf)
        except Exception:
            pass
        p[0] += sway * math.sin(t * math.pi) * length / seg
        d = d + np.array([0.0, 0.0, -0.22 * droop]) * t
        d /= np.linalg.norm(d)
        spine.append(p.copy())
    spine = np.array(spine)
    strands, radii = [], []
    side_axis = np.cross(np.array([0, -1.0, 0]), (spine[-1] - spine[0]) /
                         (np.linalg.norm(spine[-1] - spine[0]) + 1e-9))
    for k in range(n):
        off = roots[k] - r0c
        ph = rng.uniform(0, 2 * math.pi)
        amp = curl * rng.uniform(0.5, 1.2)
        flow = flow_amp * rng.uniform(0.4, 1.0) * length
        # pointed lock: strands far from the lock centre are shorter
        lat = abs(off[0]) / max(spread[0] * 0.5, 1e-4)
        L = float(np.clip(1.04 - 0.38 * lat ** 1.3 + rng.normal(0, 0.06), 0.35, 1.04))
        m = max(3, int(seg * L))
        tip_off = rng.normal(0, 1, 3) * np.array([1, 0.3, 0.3]) * tip * np.linalg.norm(spread) * 0.5
        P = []
        for s in range(m + 1):
            t = s / seg
            conv = (1 - t) ** 0.9
            q = spine[s] + off * conv + tip_off * t
            # gentle S-flow: every strand sways a little differently
            q = q + side_axis * flow * math.sin(math.pi * t * 1.3 + ph * 0.3) * t
            if amp:
                q = q + np.array([math.sin(t * 9 + ph) * amp, 0, math.cos(t * 7 + ph) * amp * 0.3])
            if hug > 0 and t <= hug:
                # lie on the skin: re-project onto the face, blending out at the end of the hug
                hp, hn = surf.hit(q[0], q[2])
                if hn[1] > 0:
                    hn = -hn
                w = 1.0 if t < hug * 0.7 else (hug - t) / (hug * 0.3)
                tgt = hp + hn * hug_off
                q = q * (1 - w) + tgt * w if q[1] > tgt[1] or w >= 1.0 else q
            P.append(q)
        strands.append(np.array(P))
        tt = np.linspace(0, 1, len(P))
        radii.append(radius * (0.35 + 0.65 * np.clip(tt / 0.08, 0, 1)) * (1 - tt) ** 0.6 + 2e-5)
    return strands, radii


def beard(C, B, parent):
    """Beard / moustache from locks.  B: dict(style, length, colors, wash ...).  Styles:
    'long3' 三绺长髯 (two moustache-side locks + a long chin lock), 'full' 虬髯 (curly full
    beard of many locks), 'goatee' (short chin tuft + moustache), 'moustache' only."""
    rng = C.rng
    H = C.H
    lm = H.lm
    mz = lm["mouth"][2]
    ul = lm["upper_lip"][2]
    CM = 0.01
    style = B.get("style", "long3")
    L = B.get("length", 0.15)
    locks = []
    # moustache (八字胡): from under the nose outward and down past the mouth corners
    if B.get("moustache", True):
        for sd in (1, -1):
            sn = lm["subnasale"][2]
            locks.append(dict(root=(sd * 0.95 * CM, sn - 0.5 * CM), spread=(1.1 * CM, 0.15 * CM),
                              n=B.get("n_m", 70), length=B.get("m_len", 0.035),
                              direction=(sd * 1.0, -0.3 * B.get("m_droop", 1.0)), tip=0.3,
                              forward=0.003, droop=B.get("m_droop", 1.0) * 2.2, sway=0.0,
                              flow_amp=0.02, hug=B.get("m_hug", 0.75)))
    if style == "long3":
        for sd in (1, -1):
            locks.append(dict(root=(sd * 2.6 * CM, mz - 1.2 * CM), spread=(1.0 * CM, 1.6 * CM),
                              n=B.get("n_side", 110), length=L * 0.62,
                              direction=(sd * 0.2, -1.0), tip=0.2, sway=-sd * 0.08,
                              forward=0.03))
        locks.append(dict(root=(0.0, mz - 2.5 * CM), spread=(3.0 * CM, 1.6 * CM),
                          n=B.get("n", 260), length=L, direction=(0.0, -1.0), tip=0.2,
                          sway=B.get("sway", 0.06), forward=0.035))
    elif style == "full":
        # 髯: locks rooted just above the mandible from jaw corner to chin, falling down and
        # inward into a spade, the chin locks longest (optionally forked)
        jp = H.jaw_pts
        span = B.get("span", 0.05)
        k = B.get("locks", 9)
        for i in range(k):
            t = i / (k - 1) * 2 - 1
            x = t * span
            j = int(np.argmin(np.abs(jp[:, 0] - x)))
            z = jp[j, 2] + B.get("above", 0.011) * (1 - 0.3 * abs(t))
            Lk = L * (1.0 - 0.5 * abs(t) ** 1.3)
            locks.append(dict(root=(x, z), spread=(1.5 * CM, 1.5 * CM), n=B.get("n", 90),
                              length=Lk, direction=(-t * 0.35, -1.0), tip=0.28,
                              sway=-t * 0.04, curl=B.get("curl", 0.0), forward=0.028,
                              flow_amp=0.08, hug=0.12))
        fork = B.get("fork", 0.0)
        for sd in ((1, -1) if fork else (0,)):
            locks.append(dict(root=(sd * fork, mz - 2.6 * CM), spread=(3.0 * CM, 1.2 * CM),
                              n=B.get("n", 90) * 2, length=L * 1.05,
                              direction=(sd * 0.08, -1.0), tip=0.3, forward=0.035,
                              flow_amp=0.08, hug=0.1))
    elif style == "goatee":
        locks.append(dict(root=(0.0, mz - 2.2 * CM), spread=(1.6 * CM, 1.2 * CM),
                          n=B.get("n", 120), length=L, direction=(0.0, -1.0), tip=0.15,
                          forward=0.02))
    colors = B.get("colors", [("ink_dense", 1.0)])
    wsum = sum(w for _, w in colors)
    out = []
    # the beard grows out of a soft ink shadow on the skin (no abrupt roots)
    if B.get("shadow", 0.0) > 0 and style in ("full", "long3", "goatee"):
        import face as _face
        jp = H.jaw_pts
        sp = B.get("span", 0.05) + 0.008
        sel = jp[np.abs(jp[:, 0]) <= sp]
        sel = sel[np.argsort(sel[:, 0])]
        lower = sel[:, [0, 2]] + np.array([0.0, -0.004])
        upper = []
        for x in np.linspace(sp, -sp, 15):
            if abs(x) < 0.028:
                z = ul + 0.0035
            else:
                z = mz + (abs(x) - 0.028) / max(sp - 0.028, 1e-3) * 0.022
            upper.append((x, z))
        poly = np.vstack([lower, np.array(upper)])
        if style != "full":
            cx = np.clip(poly[:, 0], -0.032, 0.032)
            poly = np.stack([cx, poly[:, 1]], 1)
        mat = _face.wash_material("BeardShadow", B.get("shadow_col", "ink_mid"), B["shadow"],
                                  C.skin_cfg, 0.3)
        out.append(geo.decal_fill("BeardShadow", H.surf, geo.resample(
            np.vstack([poly, poly[:1]]), 64)[:-1], C.cols["nolines"], mat, offset=0.0003, rings=6,
            parent=parent))
    by = {c: ([], []) for c, _ in colors}
    wash_s, wash_r = [], []
    for lk in locks:
        ss, rr = lock(C, rng=rng, radius=B.get("r", 0.00028), **lk)
        for s, r in zip(ss, rr):
            u = rng.uniform(0, wsum)
            acc = 0.0
            for cname, w in colors:
                acc += w
                if u <= acc:
                    break
            by[cname][0].append(s)
            by[cname][1].append(r)
        # body wash: thick strands along the same lock, ending before the fine lines
        for s in ss[::max(1, B.get("wash_every", 1))]:
            m = max(3, int(len(s) * 0.85))
            wash_s.append(s[:m])
            tt = np.linspace(0, 1, m)
            wash_r.append(B.get("wash_r", 0.0016) * (0.4 + 0.6 * np.clip(tt / 0.15, 0, 1))
                          * (1 - tt) ** 0.8 + 0.00003)
    if B.get("wash") and wash_s:
        out.append(geo.strands_obj("BeardWash", wash_s, wash_r, C.cols["fine"],
                                   strand_material("BeardWash", B["wash"], ink=0.0),
                                   parent=parent))
    for cname, (ss, rr) in by.items():
        if ss:
            out.append(geo.strands_obj("Beard", ss, rr, C.cols["fine"],
                                       strand_material("Beard", cname), parent=parent))
    return out


# ------------------------------------------------------------------------------ lady hair
def tube_uv(path, radius, nr=12):
    """tube() + UVs (u = arc length along the path in metres, v = around 0..1)."""
    V, F = tube(path, radius, nr, closed=False)
    path = np.asarray(path)
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
    UV = [(s[i], k / nr) for i in range(len(path)) for k in range(nr)]
    UV += [(0.0, 0.5), (s[-1], 0.5)]
    return V, F, np.array(UV)


def flow_hair_material(name, color="hair", streak=0.12, tint="#0E0D0C"):
    """Hair on swept tubes: fine strand streaks running along u (the sweep direction)."""
    m = shade._mat(name)
    nb = shade.NB(m)
    uv = nb.sep(nb.uv())
    q = nb.comb(nb.math("MULTIPLY", uv[0], 6.0), nb.math("MULTIPLY", uv[1], 60.0), 0.0)
    s = nb.noise(q, 1.0, 2.0, 0.5)
    c = shade.rgb(color)
    light = shade.rgb(tuple(min(1, x + 0.17) for x in hex_rgb(color)))
    col = nb.mix(nb.math("MULTIPLY", nb.smooth(s, 0.45, 0.75), streak * 4), c, light)
    nb.out(col, shade.rgb(tint), shade.shade_term(nb, 0.5, 0.03, 0.5, 0.35), 0.0, 3.0)
    return m


def lady_hair(C, L, parent):
    """Court lady's hair: a smooth cap with puffed temple locks (鬓) covering the ear tops, a
    high chignon (高髻) with two looped buns (双环), and ornaments (gold comb, hairpins with
    dangling pearls 步摇, a peony)."""
    S, R = skull(C)
    col_h = C.cols["hair"]
    out = []
    line = interp_deg(L.get("line", [(0, 60), (14, 62), (30, 68), (46, 80), (60, 94),
                                     (78, 106), (100, 110), (135, 120), (180, 124)]))
    puff = L.get("puff", 0.03)

    def off(p, t, v):
        side = np.exp(-((np.abs(((p / D2R) + 180) % 360 - 180) - 85) / 28.0) ** 2)
        band = np.exp(-((t / D2R - 86) / 15.0) ** 2)
        return 0.004 + 0.006 * (1 - v) ** 2 + puff * side * band - 0.0035 * np.clip(
            (v - 0.88) / 0.12, 0, 1)
    mat = hair_material("LadyHair", L.get("color", "hair"), streak=0.18)
    out.append(S.shell("LadyHairCap", col_h, mat, R, line, nu=120, nv=40, offset_fn=off,
                       parent=parent))
    # chignon on the crown, slightly back
    top = S.point(R, np.array([0.0]), np.array([L.get("bun_tilt", 18) * D2R]), 0.0)[0]
    bc = top + np.array([0.0, L.get("bun_back", 0.012), L.get("bun_lift", 0.03)])
    br = L.get("bun_r", (0.034, 0.03, 0.036))
    V, F = ellipsoid(bc, br)
    out.append(geo.mesh_obj("Chignon", V, F, col_h, mat, parent=parent))
    # two loops (双环望仙髻): tubes tilted outward
    fmat = flow_hair_material("Loop", L.get("color", "hair"))
    loops = L.get("loops", 0)
    if L.get("cloud", True):
        # 云髻 cloud bun: a broad mass of lobes over the crown, leaning forward
        for k, (dx, dy, dz, rx, ry, rz) in enumerate(L.get("lobes", [
                (0.0, 0.004, 0.035, 0.036, 0.03, 0.026),
                (0.034, 0.008, 0.022, 0.026, 0.026, 0.022),
                (-0.034, 0.008, 0.022, 0.026, 0.026, 0.022),
                (0.0, -0.012, 0.05, 0.022, 0.02, 0.018)])):
            V, F = ellipsoid(bc + np.array([dx, dy, dz]), (rx, ry, rz))
            out.append(geo.mesh_obj("CloudBun", V, F, col_h, mat, parent=parent))
    if loops == 1:
        # one tall loop (高髻 with a 'flying' ring) in the mid plane, leaning back
        r = L.get("loop_r", 0.034)
        ang = np.linspace(-0.2, 2 * math.pi - 0.75, 48)
        lean = L.get("loop_lean", 22) * D2R
        ly = np.sin(ang) * r * 0.85
        lz = (1 - np.cos(ang)) * r
        py = ly * math.cos(lean) + lz * math.sin(lean)
        pz = lz * math.cos(lean) - ly * math.sin(lean)
        path = np.stack([np.sin(ang * 0.5) * 0.004, py, pz], 1) + bc + np.array(
            [0, 0.004, br[2] * 0.6])
        rad = L.get("loop_tube", 0.0125) * (0.7 + 0.3 * np.sin(np.linspace(0, math.pi, 48)))
        V, F, UV = tube_uv(path, rad, 14)
        out.append(geo.mesh_obj("HairLoop", V, F, col_h, fmat, uvs=UV, parent=parent))
    for sd in ((1, -1) if loops == 2 else ()):
        r = L.get("loop_r", 0.03)
        ang = np.linspace(-0.15, 2 * math.pi - 0.6, 40)
        tilt = L.get("loop_tilt", 32) * D2R
        # loop in a vertical plane through the bun, rotated outward by tilt about the y axis
        lx = np.sin(ang) * r * 0.75
        lz = (1 - np.cos(ang)) * r
        ly = np.cos(ang) * 0.0 + np.sin(ang * 0.5) * 0.004
        px = sd * (0.012 + lx * math.cos(tilt) * sd + lz * math.sin(tilt))
        pz = lz * math.cos(tilt) - 0.0 * lx
        path = np.stack([px, ly, pz], 1) + bc + np.array([0, 0.0, br[2] * 0.55])
        rad = L.get("loop_tube", 0.0105) * (0.75 + 0.25 * np.sin(np.linspace(0, math.pi, 40)))
        V, F, UV = tube_uv(path, rad, 14)
        out.append(geo.mesh_obj("HairLoop", V, F, col_h, fmat, uvs=UV, parent=parent))
    out += hair_ornaments(C, L, bc, br, parent)
    return out


def hair_ornaments(C, L, bc, br, parent):
    S, R = skull(C)
    col = C.cols["robe"]
    fine = C.cols["fine"]
    out = []
    gold = shade.flat("OrnGold", "gold", "#7A5A1E", ao=0.2, edge=0.5, edge0=0.3)
    # gold comb (梳背) across the front of the chignon
    if L.get("comb", True):
        a = np.linspace(-1.1, 1.1, 30)
        cr = 0.024
        front = bc + np.array([0, -br[1] * 0.92, -br[2] * 0.25])
        arc = np.stack([np.sin(a) * cr * 1.2, -np.cos(a) * 0.004, np.cos(a) * cr * 0.55], 1) + front
        V = np.vstack([arc, arc * np.array([1, 1, 1]) + np.array([0, 0, -0.012])])
        n = len(a)
        F = [(i, i + 1, n + i + 1, n + i) for i in range(n - 1)]
        cm = shade.flat("Comb", "gold", "#7A5A1E", ao=0.2, edge=0.3,
                        pattern=_comb_pattern())
        uv = np.vstack([np.stack([a, np.ones(n)], 1), np.stack([a, np.zeros(n)], 1)])
        ob = geo.mesh_obj("Comb", V, F, col, cm, uvs=uv, parent=parent)
        ob.modifiers.new("Solid", "SOLIDIFY").thickness = 0.002
        out.append(ob)
    # gilt floral crown plaque (花冠) on the front of the chignon
    if L.get("crown", True):
        pc = bc + np.array([0, -br[1] * 0.95, br[2] * 0.15])
        nu = 40
        a = np.linspace(-1.25, 1.25, nu)
        hgt = 0.022 * (0.75 + 0.25 * np.cos(a * 5.0)) * np.cos(a * 0.6)
        base = np.stack([np.sin(a) * br[0] * 1.02, -np.cos(a) * br[1] * 0.3, np.zeros(nu)], 1) + pc
        topr = base + np.stack([np.zeros(nu), -0.004 * np.ones(nu), hgt], 1)
        V = np.vstack([base, topr])
        F = [(i, i + 1, nu + i + 1, nu + i) for i in range(nu - 1)]
        uv = np.vstack([np.stack([a, np.zeros(nu)], 1), np.stack([a, np.ones(nu)], 1)])
        cm = shade.flat("CrownPlaque", "gold", "#7A5A1E", ao=0.2, edge=0.3,
                        pattern=_crown_pattern())
        ob = geo.mesh_obj("CrownPlaque", V, F, col, cm, uvs=uv, parent=parent)
        ob.modifiers.new("Solid", "SOLIDIFY").thickness = 0.0015
        out.append(ob)
        # jewels on the crown
        jm = shade.flat("Jewel", L.get("jewel", "#2F7457"), "#123024", ao=0.1, edge=0.5, edge0=0.2)
        for aa in (-0.7, 0.0, 0.7):
            p = pc + np.array([math.sin(aa) * br[0] * 1.02, -math.cos(aa) * br[1] * 0.3 - 0.003,
                               0.011])
            V, F = ellipsoid(p, (0.0035, 0.0025, 0.0035), n=12, m=8)
            out.append(geo.mesh_obj("Jewel", V, F, col, jm, parent=parent))
    # hairpins (簪/步摇): long gold pins with a flower head and dangling pearl strings
    pins = L.get("pins", [(1, 0.6, 0.35), (-1, 0.75, 0.2)])
    for sd, up, fwd in pins:
        head = bc + np.array([sd * br[0] * 1.15, -br[1] * fwd, br[2] * up])
        tail = head + np.array([-sd * 0.07, 0.03, -0.012])
        V, F = tube(np.array([head, tail]), 0.0016, 8)
        out.append(geo.mesh_obj("Pin", V, F, col, gold, parent=parent))
        # head: small gold flower plaque
        V, F = ellipsoid(head, (0.007, 0.004, 0.007))
        out.append(geo.mesh_obj("PinHead", V, F, col, gold, parent=parent))
        # dangling pearls (步摇)
        pearl = shade.flat("Pearl", "lead_white", "#9A948A", ao=0.1, edge=0.6, edge0=0.2)
        for j, dx in enumerate((-0.006, 0.0, 0.006)):
            st = head + np.array([dx, -0.004, -0.006])
            for k in range(3):
                p = st + np.array([0, 0, -0.011 * (k + 1)])
                V, F = ellipsoid(p, (0.0028, 0.0028, 0.0028), n=10, m=8)
                out.append(geo.mesh_obj("Pearl", V, F, fine, pearl, parent=parent))
            chain = np.array([st, st + np.array([0, 0, -0.034])])
            out.append(geo.strands_obj("Chain", [chain], [np.array([0.0004, 0.0004])], fine,
                                       strand_material("ChainGold", "gold", ink=0.0, veil=0.0),
                                       parent=parent))
    # peony (牡丹) at the side of the chignon
    if L.get("flower", True):
        fc = bc + np.array([-L.get("flower_side", 1) * br[0] * 1.05, -br[1] * 0.55, br[2] * 0.05])
        out += peony(C, fc, L.get("flower_r", 0.026), L.get("flower_col", ("#E8A7A0", "#C2414A")),
                     L.get("flower_side", 1), parent)
    return out


def _crown_pattern():
    def f(nb, p):
        uv = nb.sep(nb.uv())
        s = nb.math("ABSOLUTE", nb.math("SINE", nb.math("MULTIPLY", uv[0], 12.0)))
        m = nb.math("MULTIPLY", nb.smooth(s, 0.75, 0.95), nb.smooth(uv[1], 0.2, 0.5))
        return nb.mix(nb.math("MULTIPLY", m, 0.55), p, shade.rgb("#8A6A28"))
    return f


def _comb_pattern():
    def f(nb, p):
        uv = nb.sep(nb.uv())
        s = nb.math("ABSOLUTE", nb.math("SINE", nb.math("MULTIPLY", uv[0], 40.0)))
        m = nb.math("MULTIPLY", nb.smooth(s, 0.6, 0.9), nb.smooth(uv[1], 0.3, 0.6))
        return nb.mix(nb.math("MULTIPLY", m, 0.5), p, shade.rgb("#8A6A28"))
    return f


def peony(C, center, r, colors, side, parent):
    """Layered petal cups with lobed rims, outer petals pale, heart deep; two leaves."""
    out = []
    col = C.cols["robe"]
    light, deep = colors
    # facing: outward-front
    z = np.array([side * -0.55, -0.8, 0.25])
    z /= np.linalg.norm(z)
    x = np.cross([0, 0, 1.0], z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    M = np.stack([x, y, z], 1)
    for k, (rr, h, lobes, c0) in enumerate(((1.0, 0.25, 6, light), (0.72, 0.45, 7, light),
                                            (0.45, 0.6, 5, deep))):
        nu, nv = 60, 6
        a = np.linspace(0, 2 * math.pi, nu, endpoint=False)
        V = []
        for j in range(nv):
            v = j / (nv - 1)
            rim = 1.0 + 0.16 * np.cos(a * lobes + k) * v
            rad = r * rr * v * rim
            zz = np.full(nu, r * h * (v ** 1.8) - r * 0.1)
            V.append(np.stack([rad * np.cos(a), rad * np.sin(a), zz], 1))
        V = np.vstack(V) @ M.T + center
        F = [f[::-1] for f in geo.grid_faces(nu, nv, wrap_u=True)]
        UV = np.array([(i / nu, j / (nv - 1)) for j in range(nv) for i in range(nu)])
        mat = shade.flat("Petal%d" % k, c0, deep, ao=0.6, edge=0.3, pattern=_petal_grad(light,
                                                                                        deep))
        ob = geo.mesh_obj("Petal", V, F, col, mat, uvs=UV, parent=parent)
        ob.modifiers.new("Solid", "SOLIDIFY").thickness = 0.0012
        out.append(ob)
    # leaves
    for s in (1, -1):
        base = center + M @ np.array([s * r * 0.7, -r * 0.6, -r * 0.05])
        tip = base + M @ np.array([s * r * 0.9, -r * 0.7, -r * 0.2])
        mid = (base + tip) / 2
        nrm = np.cross(tip - base, M[:, 2])
        nrm /= np.linalg.norm(nrm)
        pts = []
        for t in np.linspace(0, 1, 9):
            w = math.sin(math.pi * t) * r * 0.35
            c = base + (tip - base) * t + M[:, 2] * (math.sin(math.pi * t) * r * 0.1)
            pts.append((c - nrm * w, c + nrm * w))
        V = np.array([p for pr in pts for p in pr])
        F = [(2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1) for i in range(len(pts) - 1)]
        lm = shade.flat("Leaf", "malachite", "#16402E", ao=0.4, edge=0.3)
        ob = geo.mesh_obj("Leaf", V, F, col, lm, parent=parent)
        ob.modifiers.new("Solid", "SOLIDIFY").thickness = 0.001
        out.append(ob)
    return out


def _petal_grad(light, deep):
    def f(nb, p):
        uv = nb.sep(nb.uv())
        return nb.mix(nb.smooth(uv[1], 0.15, 0.95), shade.rgb(deep), shade.rgb(light))
    return f


def earrings(C, E, parent):
    """Pearl drop earrings under the ear lobes."""
    H = C.H
    out = []
    pearl = shade.flat("EarPearl", E.get("color", "lead_white"), "#9A948A", ao=0.1, edge=0.6,
                       edge0=0.2)
    gold = shade.flat("EarGold", "gold", "#7A5A1E", ao=0.1, edge=0.4)
    V0 = np.asarray(H.verts)
    lm = H.lm
    for sd in (1, -1):
        # ear lobe: lowest outer point of the ear region
        m = (np.sign(V0[:, 0]) == sd) & (np.abs(V0[:, 0]) > 0.06) & \
            (np.abs(V0[:, 2] - (H.eye_z - 0.045)) < 0.02) & (V0[:, 1] > lm["nose_tip"][1] + 0.07) \
            & (V0[:, 1] < lm["nose_tip"][1] + 0.12)
        if not m.any():
            continue
        p = V0[m][np.argmin(V0[m][:, 2])]
        hook = np.array([p + [sd * 0.002, 0, -0.002], p + [sd * 0.003, 0, -0.012]])
        V, F = tube(hook, 0.0008, 6)
        out.append(geo.mesh_obj("EarHook", V, F, C.cols["fine"], gold, parent=parent))
        V, F = ellipsoid(hook[1] + [0, 0, -0.005], (0.0042, 0.0042, 0.0052), n=12, m=10)
        out.append(geo.mesh_obj("EarPearl", V, F, C.cols["fine"], pearl, parent=parent))
    return out


# --------------------------------------------------------------------- more headgear
def futou(C, Fu, parent):
    """幞头 black gauze cap: a close cap cut at the brow with a raised two-lobed crown (巾子)."""
    S, R = skull(C)
    rim = interp_deg(Fu.get("rim", [(0, 64), (40, 68), (80, 84), (120, 96), (180, 100)]))
    col = C.cols["robe"]
    gz = _gauze(Fu)
    mat = shade.flat("Futou", Fu.get("color", "#26262A"), "#0A0A0A", ao=0.4, edge=0.45,
                     pattern=gz)
    out = [S.shell("Futou", col, mat, R, rim, nu=96, nv=26,
                   offset_fn=lambda p, t, v: 0.009 + 0.004 * (1 - v), parent=parent)]
    top = S.point(R, np.array([math.pi]), np.array([Fu.get("lobe_t", 22) * D2R]), 0.0)[0]
    for k, dx in enumerate(Fu.get("lobes", (0.0,))):
        V, F = ellipsoid(top + np.array([dx, -0.006, 0.016]), (0.034, 0.032, 0.036))
        out.append(geo.mesh_obj("FutouLobe", V, F, col, mat, parent=parent))
    return out


def head_band(C, B, parent):
    """抹额 / cloth band around the head at the forehead, knotted behind."""
    S, R = skull(C)
    rim = interp_deg(B.get("rim", [(0, 66), (60, 72), (100, 84), (180, 92)]))
    pp = np.linspace(0, 2 * math.pi, 140, endpoint=False)
    tr = np.array([rim(p) for p in pp])
    bw = B.get("w", 8.0) * D2R
    V, UV = [], []
    nv = 5
    for j in range(nv):
        v = j / (nv - 1)
        V.append(S.point(R, pp, tr - bw * v, B.get("lift", 0.009)))
        UV.append(np.stack([pp / (2 * math.pi), np.full(len(pp), v)], 1))
    F = geo.grid_faces(len(pp), nv, wrap_u=True)
    import patterns as pat
    mat = shade.flat("HeadBand", B.get("color", "cinnabar"), None, ao=0.4, edge=0.35,
                     pattern=B.get("pattern"))
    out = [geo.mesh_obj("HeadBand", np.vstack(V), F, C.cols["robe"], mat, smooth=True,
                        uvs=np.vstack(UV), parent=parent)]
    # two tails hanging behind
    knot = S.point(R, np.array([math.pi]), np.array([rim(math.pi) - bw / 2]),
                   B.get("lift", 0.009) + 0.004)[0]
    for sd in (1, -1):
        pts = np.array([knot, knot + [sd * 0.015, 0.02, -0.03], knot + [sd * 0.03, 0.03, -0.08]])
        pts = geo.catmull(pts, per=8)
        n = len(pts)
        w = B.get("tail_w", 0.018)
        V = np.vstack([pts + [-w / 2 * 0.0, 0, 0] + np.array([sd * 0.0, 0, 0]) - [w / 2, 0, 0],
                       pts + [w / 2, 0, 0]])
        F = [(i, i + 1, n + i + 1, n + i) for i in range(n - 1)]
        ob = geo.mesh_obj("BandTail", V, F, C.cols["robe"], mat, parent=parent)
        ob.modifiers.new("Solid", "SOLIDIFY").thickness = 0.0015
        out.append(ob)
    return out


def loose_locks(C, L, parent):
    """A few loose locks (碎发) escaping at the temples: rogues, warrior women."""
    H = C.H
    ez = H.eye_z
    out = []
    ss, rr = [], []
    for sd in (1, -1):
        s, r = lock(C, root=(sd * L.get("x", 0.052), ez + L.get("dz", 0.042)),
                    spread=(0.012, 0.006), n=L.get("n", 40), length=L.get("len", 0.07),
                    direction=(sd * 0.25, -1.0), tip=0.3, forward=0.006, flow_amp=0.15,
                    radius=0.00035, hug=0.6, hug_off=0.002)
        ss += s
        rr += r
    out.append(geo.strands_obj("Locks", ss, rr, C.cols["fine"],
                               strand_material("Locks", L.get("color", "hair")), parent=parent))
    return out
