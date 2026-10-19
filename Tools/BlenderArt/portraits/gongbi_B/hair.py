"""Hair and beards: ink-wash masses with combed strands (丝发) after the gongbi method.

Method (as painted): 1) an even ink wash fills the hair mass, 2) a lighter sheen band follows
the skull's curvature (light from the upper left), 3) fine strands in darker ink and a few
lighter ones show the combing direction, 4) the hairline is softened with very fine short
strands.  Grey and white hair reverse the values: pale wash, grey strands, white strands on top.

Volumes (skull, buns, temple puffs) are ellipsoids in head space (:class:`Shell`), so strands
wrap and the outline turns correctly with the head.
"""

import math

import numpy as np

import geom2d as g
import palette as pal


class Shell:
    """Ellipsoid in head units: centre c, radii r, optional roll about z (deg) / pitch about x."""

    def __init__(self, head, c, r, tilt=0.0, pitch=0.0):
        self.H = head
        self.c = np.asarray(c, float)
        self.r = np.asarray(r, float)
        self.tilt = math.radians(tilt)
        self.pitch = math.radians(pitch)

    def xyz(self, lon, lat, dr=0.0):
        lon = np.asarray(lon, float)
        lat = np.asarray(lat, float)
        rx, ry, rz = self.r + dr
        x = rx * np.cos(lat) * np.sin(lon)
        y = -ry * np.sin(lat)
        z = rz * np.cos(lat) * np.cos(lon)
        if self.tilt:
            c, s = math.cos(self.tilt), math.sin(self.tilt)
            x, y = x * c - y * s, x * s + y * c
        if self.pitch:
            c, s = math.cos(self.pitch), math.sin(self.pitch)
            y, z = y * c - z * s, y * s + z * c
        return x + self.c[0], y + self.c[1], z + self.c[2]

    def normal(self, lon, lat):
        x, y, z = self.xyz(lon, lat)
        rx, ry, rz = self.r
        return ((x - self.c[0]) / rx ** 2, (y - self.c[1]) / ry ** 2, (z - self.c[2]) / rz ** 2)

    def P(self, lon, lat, dr=0.0):
        x, y, z = self.xyz(lon, lat, dr)
        return self.H.proj(x, y, z)

    def facing(self, lon, lat):
        nx, ny, nz = self.normal(lon, lat)
        return -nx * math.sin(self.H.yaw) + nz * math.cos(self.H.yaw)

    def outline(self, dr=0.0, n=72, keep=None):
        """Projected outline (star polygon about the projected centre).  ``keep(x, y, z)`` may
        restrict which surface samples count."""
        lon, lat = np.meshgrid(np.linspace(-math.pi, math.pi, 90),
                               np.linspace(-math.pi / 2, math.pi / 2, 46))
        x, y, z = self.xyz(lon, lat, dr)
        if keep is not None:
            m = keep(x, y, z)
            x, y, z = x[m], y[m], z[m]
        Pp = self.H.proj(x.ravel(), y.ravel(), z.ravel())
        c = Pp.mean(0)
        ang = np.arctan2(Pp[:, 1] - c[1], Pp[:, 0] - c[0])
        rad = np.linalg.norm(Pp - c, axis=1)
        bins = np.linspace(-math.pi, math.pi, n + 1)
        out = []
        for i in range(n):
            m = (ang >= bins[i]) & (ang < bins[i + 1])
            if m.any():
                j = np.argmax(np.where(m, rad, -1))
                out.append(Pp[j])
        return np.array(out)


def _segments_visible(P, vis):
    segs = []
    cur = []
    for p, v in zip(P, vis):
        if v:
            cur.append(p)
        elif cur:
            if len(cur) > 2:
                segs.append(np.array(cur))
            cur = []
    if len(cur) > 2:
        segs.append(np.array(cur))
    return segs


def strands_on(cv, shell, starts, ends, width, color, alpha, dr=0.02, mode="paint", bend=0.0,
               n=24, prof="hair", rng=None, min_facing=0.02, alpha_jitter=0.3):
    """Combed strands over an ellipsoid between (lon, lat) start and end pairs."""
    rng = rng or np.random.default_rng(0)
    for (l0, a0), (l1, a1) in zip(starts, ends):
        t = np.linspace(0, 1, n)
        lon = l0 + (l1 - l0) * t + bend * np.sin(np.pi * t)
        lat = a0 + (a1 - a0) * t
        P = shell.P(lon, lat, dr)
        vis = shell.facing(lon, lat) > min_facing
        for seg in _segments_visible(P, vis):
            cv.stroke(seg, width * rng.uniform(0.7, 1.2), color,
                      alpha * (1 - alpha_jitter * rng.uniform()), mode=mode, prof=prof,
                      noise=0.15)


# ------------------------------------------------------------------------------------------
def skull_shell(fd, volume=0.02):
    H = fd.H
    w = H.sh["width"]
    return Shell(H, (0.0, 0.43, -0.035), (0.330 * w + volume, 0.432 + volume, 0.475 + volume))


def male_hairline(far, top=0.205, sideburn=0.50, recede=0.0, nape=0.64):
    """Hairline on the head surface as (lon, y): far temple -> forehead -> near sideburn ->
    over the near ear -> nape."""
    t = top + 0.035 * recede
    r = recede
    # a gentle arch: highest at the centre, curving down to the temples and sideburns
    return np.array([
        (far * 1.36, 0.44), (far * 1.18, 0.325 + 0.03 * r), (far * 0.88, 0.268 + 0.05 * r),
        (far * 0.42, t + 0.022), (0.0, t), (-far * 0.42, t + 0.022),
        (-far * 0.88, 0.268 + 0.05 * r), (-far * 1.14, 0.315 + 0.04 * r),
        (-far * 1.30, 0.40), (-far * 1.37, sideburn),
        (-far * 1.47, sideburn - 0.04), (-far * 1.62, 0.43), (-far * 1.85, 0.45),
        (-far * 2.05, 0.54), (-far * 2.30, nape)])


def male_hair(cv, fd, color="hair", grey=0.0, top=0.205, sideburn=0.50, bun=True,
              recede=0.0, volume=0.022, seed=0, strands=150, nape=0.64):
    """Hair combed up into a topknot (束发).  Returns dict with polygons and the bun shell."""
    H = fd.H
    s = H.s
    far = fd.far
    rng = np.random.default_rng(seed + 5)
    hl = male_hairline(far, top, sideburn, recede, nape)
    HLc = g.catmull(hl, 8)
    HL = H.Plon(HLc[:, 0], HLc[:, 1], 0.004)
    y_nape = hl[-1, 1]
    near_sil, _ = H.silhouette(0.0, y_nape, 40, side=-far, dr=volume)
    far_sil, _ = H.silhouette(0.0, hl[0, 1], 40, side=far, dr=volume)
    base = pal.hexs(pal.mix(pal.hexs(pal.mix(color, "ink_m", 0.20 * (1 - grey))), "hair_white",
                            grey * 0.85))
    HLin = feather_hairline(cv, fd, HL, base, s)
    poly = np.vstack([HLin, near_sil[::-1], far_sil])
    cv.fill(poly, base, 0.97, "paint")
    # sheen band following the skull (light from the upper left): a lighter ink, not white
    sheen_col = pal.hexs(pal.mix(base, "ink_l", 0.55 + 0.3 * grey))
    lon = np.linspace(-1.5, 1.5, 50)
    for yc, al in ((0.11, 0.16), (0.17, 0.08)):
        P1 = H.Plon(lon, np.full_like(lon, yc - 0.035), volume * 0.8)
        P2 = H.Plon(lon, np.full_like(lon, yc + 0.035), volume * 0.8)
        vis = H.facing_lon(lon, np.full_like(lon, yc)) > 0.05
        if vis.sum() > 4:
            cv.band(P1[vis], P2[vis], sheen_col,
                    lambda S, T: al * np.sin(np.pi * T) * np.sin(np.pi * S) ** 0.8
                    * (1.2 - 0.6 * S if far > 0 else 0.6 + 0.6 * S), mode="paint", rows=4)
    dark = pal.hexs(pal.mix("ink", base, 0.20 if grey < 0.5 else 0.55))
    light = pal.hexs(pal.mix(base, "white", 0.22 + 0.5 * grey))
    # combed strands from the hairline up to the knot
    def strand(lon0, y0, lon1, y1, w, col, al, n=26):
        t = np.linspace(0, 1, n)
        lo = lon0 + (lon1 - lon0) * t ** 1.3
        yy = y0 + (y1 - y0) * t ** 0.85
        P = H.Plon(lo, yy, volume * (0.4 + 0.6 * t))
        vis = H.facing_lon(lo, yy) > 0.02
        for seg in _segments_visible(P, vis):
            cv.stroke(seg, w, col, al, prof="hair", noise=0.15)
    front = HLc[: int(len(HLc) * 0.62)]
    for i in range(strands):
        u = rng.uniform(0, 1)
        lon0, y0 = g.at(front, u)
        y0 -= 0.006
        lon1 = lon0 * 0.18 + rng.normal(0, 0.06)
        y1 = 0.015 + rng.normal(0, 0.01)
        strand(lon0, y0, lon1, y1, s * 0.0026 * rng.uniform(0.7, 1.2), dark,
               0.75 * rng.uniform(0.5, 1.0))
        if i % 3 == 0:
            strand(lon0 + 0.02, y0, lon1, y1, s * 0.0022, light, (0.35 + 0.4 * grey) * rng.uniform(0.5, 1))
    # back hair: from the nape and behind the ear up to the knot
    for i in range(int(strands * 0.45)):
        lon0 = -far * rng.uniform(1.55, 2.6)
        y0 = rng.uniform(0.45, 0.72)
        strand(lon0, y0, lon0 * 0.3, 0.02, s * 0.0026, dark, 0.65 * rng.uniform(0.5, 1))
        if i % 3 == 0:
            strand(lon0, y0, lon0 * 0.3, 0.02, s * 0.0022, light, (0.3 + 0.4 * grey) * rng.uniform(0.5, 1))
    # hairline fringe: fine short strokes softening the edge into the skin
    HLd = g.resample(HL[: int(len(HL) * 0.70)], 150)
    nrm = g.normals(HLd)
    tan = g.tangents(HLd)
    cen = H.P([(0.0, 0.5)])[0]
    for i in range(len(HLd)):
        p = HLd[i]
        nv = nrm[i] if np.dot(cen - p, nrm[i]) < 0 else -nrm[i]      # into the hair
        L = s * rng.uniform(0.015, 0.035)
        q = p + nv * L + tan[i] * rng.normal(0, 0.35) * L
        cv.stroke(np.array([p - nv * s * 0.005, (p + q) / 2, q]), s * 0.0022, base,
                  rng.uniform(0.45, 0.85), prof="hair", noise=0.1)
    # edge wash so the mass reads round
    rim = np.vstack([near_sil[::-1], far_sil])
    cv.edge(rim, s * 0.05, "ink", 0.30 * (1 - grey * 0.6), side=_inward(rim, poly), rows=4)
    cv.stroke(rim, s * 0.004, "ink", 0.6, prof="iron")
    out = dict(poly=poly, hairline=HL, base=base, dark=dark, light=light)
    if bun:
        out["bun"] = topknot(cv, fd, base, dark, light, grey, rng)
    return out


def feather_hairline(cv, fd, HL, base, s, width=0.011, wash=0.16):
    """Soft hairline (发际): the hair mass stops a little short of the hairline and fades in
    over it, with a pale ink wash on the skin side, as a painter softens the edge with a damp
    brush.  Returns the inner (hair-side) curve used to close the hair mass."""
    H = fd.H
    cen = H.P([(0.0, 0.5)])[0]
    m = len(HL) // 2
    nrm = g.normals(HL)
    into_hair = 1 if np.dot(nrm[m], HL[m] - cen) > 0 else -1
    HLin = g.offset(HL, into_hair * s * width)
    cv.band(HL, HLin, base, lambda S, T: 0.97 * g.smoothstep(0.0, 1.0, T) ** 0.8, mode="paint",
            rows=4, cols=max(20, len(HL)))
    cv.edge(HL, s * 0.022, "ink_l", wash, side=-into_hair, rows=4, end_fade=0.08, power=1.6)
    return HLin


def _inward(P, poly):
    c = poly.mean(0)
    m = len(P) // 2
    nrm = g.normals(P)[m]
    return 1 if np.dot(c - P[m], nrm) > 0 else -1


def topknot(cv, fd, base, dark, light, grey, rng, c=(0.0, -0.045, -0.05), r=(0.088, 0.075, 0.088)):
    H = fd.H
    s = H.s
    bun = Shell(H, c, r)
    O = bun.outline(0.0, n=48)
    cv.fill(O, base, 0.98, "paint")
    # wrapped strands round the knot
    starts = []
    ends = []
    for k in range(26):
        lat = rng.uniform(-0.9, 1.2)
        starts.append((-math.pi, lat))
        ends.append((math.pi, lat + rng.normal(0, 0.15)))
    strands_on(cv, bun, starts, ends, s * 0.0026, dark, 0.7, rng=rng, n=40)
    strands_on(cv, bun, starts[::2], ends[::2], s * 0.0022, light, 0.35 + 0.3 * grey, rng=rng, n=40)
    cv.stroke(np.vstack([O, O[:1]]), s * 0.004, "ink", 0.8, prof="flat", caps=False)
    return bun


# ------------------------------------------------------------------------------------------
# beards (胡须): drawn as locks (绺) - bundles of near-parallel tapering strands


def beard_colors(grey, color="hair"):
    """grey 0 black .. 0.5 grizzled iron-grey .. 1 white.  -> (base, strand mix)."""
    g_ = float(np.clip(grey, 0, 1))
    base = pal.hexs(pal.mix(color, "hair_white", 0.08 + 0.85 * g_ ** 1.6))
    dark = pal.hexs(pal.mix("ink", "hair_grey", max(0.0, g_ - 0.6) * 1.5))
    mid = pal.hexs(pal.mix("ink_m", "hair_grey", 0.3 + 0.7 * g_))
    light = "hair_white"
    mix = [(dark, 0.85, max(0.05, 1.0 - 1.15 * g_)), (mid, 0.75, 0.40 + 0.3 * g_),
           (light, 0.80, 0.04 + 0.85 * g_ ** 1.4), ("white", 0.85, 0.5 * max(0.0, g_ - 0.55))]
    return base, mix


def flow_mass(cv, R, B, cols, rng, n, s, sway=0.012, tips=None, tip_pull=0.6,
              base_alpha=0.55, root_band=0.25, strand_w=0.0030, waves=1.3, phase=0.0,
              soft=True, end_spread=0.04, fade_in=0.35, wash=0.0):
    """Hair mass flowing from root curve R to end curve B (both ordered the same way).
    Strands keep their order (combed), sway together in soft waves, and cluster into the lock
    tips given as parameters along B.  cols = (base, [(colour, alpha, weight), ...])."""
    base, mix = cols
    M = 120
    Rr = g.resample(R, M)
    Br = g.resample(B, M)
    poly = np.vstack([Rr, Br[::-1]])
    if soft:
        cv.band(Rr, Br, base, lambda S, T: base_alpha * g.smoothstep(-0.01, fade_in, T)
                * (1 - 0.95 * g.smoothstep(0.78, 0.96, T))
                * (0.3 + 0.7 * g.smoothstep(0.0, 0.12, S) * g.smoothstep(0.0, 0.12, 1 - S)),
                mode="paint", rows=8)
    else:
        cv.fill(poly, base, base_alpha, "paint")
    # ink-wash body of the mass: denser near the roots and inside the locks, mottled, so the
    # beard reads as a mass with combed strands on top (not as loose hairs)
    if wash:
        sd = int(rng.integers(1 << 20))
        cv.band(Rr, Br, "ink_m", lambda S, T: wash * g.smoothstep(-0.02, fade_in * 0.8, T)
                * (1 - 0.8 * g.smoothstep(0.45, 1.0, T))
                * (0.35 + 0.65 * g.smoothstep(0.0, 0.15, S) * g.smoothstep(0.0, 0.15, 1 - S)),
                rows=8, alpha_xy=lambda V: np.clip(1 + 0.45 * g.vnoise(V, s * 0.05, sd), 0.2, 1.6))
    tips = np.asarray(tips if tips is not None else [], float)
    wts = np.array([m[2] for m in mix], float)
    wts = wts / wts.sum()

    def endmap(v):
        if len(tips) == 0:
            return v
        k = np.argmin(np.abs(tips - v))
        return v + (tips[k] - v) * tip_pull * rng.uniform(0.5, 1.0)
    for i in range(n):
        col, al, _ = mix[rng.choice(len(mix), p=wts)]
        v = rng.uniform(0, 1)
        ve = np.clip(endmap(v) + rng.normal(0, end_spread * 0.5), 0, 1)
        iv = int(v * (M - 1))
        ie = int(ve * (M - 1))
        r0 = Rr[iv] + (Br[iv] - Rr[iv]) * (root_band * rng.uniform(0, 1) ** 1.5
                                            - 0.05 * rng.uniform(0, 1))
        e = Br[ie] + (Br[ie] - Rr[iv]) * rng.uniform(-0.12, 0.04)
        d = e - r0
        ln = np.linalg.norm(d)
        if ln < 1:
            continue
        nrm = np.array([-d[1], d[0]]) / ln
        ph = 2 * np.pi * (v * waves) + phase
        pts = []
        for t in (0.0, 0.3, 0.62, 1.0):
            w = s * sway * math.sin(math.pi * t) * math.sin(ph + 2.2 * t)
            pts.append(r0 + d * t + nrm * w)
        cv.stroke(g.catmull(pts, 8), s * strand_w * rng.uniform(0.7, 1.25), col,
                  al * rng.uniform(0.5, 1.0), prof="hair", noise=0.12, taper=(0.10, 0.55))
    return poly


def lock(cv, C, W0, cols, rng, n, s, strand_w=0.0034, wash=0.3, base_alpha=0.95):
    """One lock of hair (绺) along centreline C (root -> tip) of half-width W0 px at its fullest:
    a soft base mass, an ink-wash body, then strands combed along it converging to the tip."""
    base, mix = cols
    M = 60
    Cr = g.resample(C, M)
    t = np.linspace(0, 1, M)
    w = W0 * (0.60 + 0.40 * np.sin(np.pi * np.clip(t * 1.7, 0, 1)) ** 0.7) \
        * (1 - 0.80 * g.smoothstep(0.50, 1.0, t))
    N = g.normals(Cr)
    L = Cr + N * w[:, None]
    R = Cr - N * w[:, None]
    cv.band(L, R, base, lambda S, T: base_alpha * g.smoothstep(0.0, 0.10, S)
            * (1 - 0.35 * (np.abs(T - 0.5) * 2) ** 3), mode="paint", rows=4)
    if wash:
        sd = int(rng.integers(1 << 20))
        cv.band(L, R, "ink_m", lambda S, T: wash * (1 - 0.6 * S) * (1 - (np.abs(T - 0.5) * 2) ** 2),
                rows=4, alpha_xy=lambda V: np.clip(1 + 0.4 * g.vnoise(V, s * 0.03, sd), 0.3, 1.6))
    wts = np.array([m[2] for m in mix], float)
    wts = wts / wts.sum()
    for i in range(n):
        col, al, _ = mix[rng.choice(len(mix), p=wts)]
        v = rng.uniform(-0.95, 0.95)
        t0 = rng.uniform(0.0, 0.25)
        t1 = rng.uniform(0.55, 1.0)
        ts = np.linspace(t0, t1, 8)
        k = (ts * (M - 1)).astype(int)
        conv = 1 - 0.55 * (ts - t0) / max(t1 - t0, 1e-3)          # strands converge to the tip
        P = Cr[k] + N[k] * (v * conv * w[k])[:, None]
        cv.stroke(g.catmull(P, 4), s * strand_w * rng.uniform(0.7, 1.2), col,
                  al * rng.uniform(0.55, 1.0), prof="hair", noise=0.12, taper=(0.12, 0.6))


def beard(cv, fd, kind="full", length=0.30, width=1.0, grey=0.0, density=1.0, seed=0,
          moustache=True, whiskers=True, color="hair", droop=1.0):
    """kind: 'full' (络腮胡 whiskers + chin beard + moustache), 'long' (长髯 to the chest),
    'goatee' (scholar's moustache and chin beard), 'stubble' (short full)."""
    F = fd.F
    H = fd.H
    s = H.s
    far = fd.far
    rng = np.random.default_rng(seed + 31)
    cols = beard_colors(grey, color)
    my = F.mouth_y
    mw = F.mouth_w / 2
    chin = fd.lm["chin"]
    L = length * s
    out = {}

    def Pf(pts, dz=0.012):
        return H.P(pts, dz)
    tip = np.array([chin[0] + far * s * 0.012, chin[1] + L])
    if kind in ("full", "stubble", "long", "goatee"):
        if kind in ("full", "stubble"):
            top = [(-far * 1.36, 0.52), (-far * 1.25, 0.64), (-far * 1.05, 0.76),
                   (-far * 0.55, 0.85), (-far * 0.15, 0.855), (0.0, my + F.lip_lo + 0.03),
                   (far * 0.15, 0.855), (far * 0.50, 0.84), (far * 0.95, 0.76),
                   (far * 1.12, 0.66)]
        elif kind == "long":
            top = [(-far * 1.10, 0.78), (-far * 0.75, 0.85), (-far * 0.3, 0.875),
                   (0.0, my + F.lip_lo + 0.04), (far * 0.3, 0.875), (far * 0.7, 0.85),
                   (far * 0.95, 0.79)]
        else:
            top = [(-far * 0.36, 0.89), (-far * 0.15, my + F.lip_lo + 0.05), (0.0, my + F.lip_lo + 0.045),
                   (far * 0.15, my + F.lip_lo + 0.05), (far * 0.36, 0.89)]
        top = np.array(top)
        R = H.Plon(*g.catmull(top, 8).T, 0.012)
        # end curve: short below the jaw at the sides, long at the centre, lobed into locks
        jn = R[0]
        jf = R[-1]
        if kind in ("full", "stubble"):
            sp = s * 0.17 * width
            B = g.catmull([jn + np.array([-far * s * 0.005, s * 0.16]),
                           tip + np.array([-far * sp * 0.75, -L * 0.45]),
                           tip + np.array([-far * sp * 0.25, -L * 0.05]), tip,
                           tip + np.array([far * sp * 0.3, -L * 0.12]),
                           tip + np.array([far * sp * 0.65, -L * 0.55]),
                           jf + np.array([far * s * 0.0, s * 0.15])], 8)
            tips = [0.30, 0.47, 0.56, 0.70]
        elif kind == "long":
            sp = s * 0.11 * width
            B = g.catmull([jn + np.array([-far * s * 0.01, s * 0.30]),
                           tip + np.array([-far * sp, -L * 0.30]),
                           tip + np.array([-far * sp * 0.35, -L * 0.04]), tip,
                           tip + np.array([far * sp * 0.4, -L * 0.10]),
                           tip + np.array([far * sp * 0.9, -L * 0.40]),
                           jf + np.array([far * s * 0.005, s * 0.26])], 8)
            tips = [0.35, 0.5, 0.62]
        else:
            # 山羊须 done the dignified way: a full, rounded chin lock, not a stringy point
            sp = s * 0.075 * width
            B = g.catmull([R[0] + np.array([-far * s * 0.015, s * 0.06]),
                           tip + np.array([-far * sp, -L * 0.30]),
                           tip + np.array([-far * sp * 0.45, -L * 0.04]), tip,
                           tip + np.array([far * sp * 0.45, -L * 0.04]),
                           tip + np.array([far * sp, -L * 0.30]),
                           R[-1] + np.array([far * s * 0.015, s * 0.06])], 8)
            tips = [0.42, 0.5, 0.58]
        n = int({"full": 900, "stubble": 450, "long": 900, "goatee": 380}[kind] * density)
        out["mass"] = flow_mass(cv, R, B, cols, rng, n, s, sway=0.014 if kind != "long" else 0.02,
                                tips=tips, tip_pull=0.55, root_band=0.35 if kind == "full" else 0.15,
                                base_alpha=0.92, fade_in=0.30, wash=0.45 * (1 - 0.6 * grey))
    # --- moustache (髭): two locks combed outward from the philtrum over the upper lip, full
    # at the root, draping past the mouth corners and tapering (into the beard when there is
    # one) - never thin drooping whiskers ---
    if moustache and kind != "none":
        ny = F.nose_y + 0.020
        drop = {"long": 0.17, "full": 0.085, "goatee": 0.028, "stubble": 0.030}[kind] * droop
        W0 = {"long": 0.022, "full": 0.030, "goatee": 0.022, "stubble": 0.020}[kind]
        for side in (-far, far):
            fs = side == far
            if kind in ("goatee", "stubble"):
                # a neat moustache that ends at the mouth corner (never thin drooping whiskers)
                fr = [(side * 0.006, ny + 0.010), (side * mw * 0.50, ny + 0.024),
                      (side * mw * 0.92, my - 0.016), (side * (mw + 0.010), my + drop)]
            else:
                fr = [(side * 0.006, ny + 0.010), (side * mw * 0.45, ny + 0.026),
                      (side * mw * 0.90, my - 0.014), (side * (mw + 0.020), my + drop * 0.45),
                      (side * (mw + 0.028), my + drop)]
            dz = [0.050, 0.048, 0.040, 0.020, 0.0][:len(fr)]
            C = g.catmull(H.P(fr, np.array(dz)), 10)
            lock(cv, C, s * W0 * (0.85 if fs else 1.0), cols, rng,
                 int(170 * density * (0.8 if fs else 1.0)), s, wash=0.35 * (1 - 0.5 * grey))
    out["tip"] = tip
    return out


# ------------------------------------------------------------------------------------------
# lady's hair: centre parting, temple puffs over the ears (鬓), high bun with a loop (高髻)


def _shell_strands(cv, sh, axis_lat=True, n=40, w=0.6, col="ink", alpha=0.6, rng=None,
                   lat_range=(-1.2, 1.3), lon_range=(-math.pi, math.pi), dr=0.0, steps=40):
    """strands on a shell along longitude circles (axis_lat) or meridians."""
    rng = rng or np.random.default_rng(0)
    for i in range(n):
        if axis_lat:
            la = rng.uniform(*lat_range)
            lo = np.linspace(*lon_range, steps)
            la_a = np.full_like(lo, la) + 0.05 * np.sin(lo * 2 + rng.uniform(0, 6))
            P = sh.P(lo, la_a, dr)
            vis = sh.facing(lo, la_a) > 0.02
        else:
            lo0 = rng.uniform(*lon_range)
            la = np.linspace(*lat_range, steps)
            lo = np.full_like(la, lo0) + 0.08 * np.sin(la * 2 + rng.uniform(0, 6))
            P = sh.P(lo, la, dr)
            vis = sh.facing(lo, la) > 0.02
        for seg in _segments_visible(P, vis):
            cv.stroke(seg, w * rng.uniform(0.7, 1.2), col, alpha * rng.uniform(0.5, 1.0),
                      prof="hair", noise=0.1)


def _shell_mass(cv, sh, base, rng, s, keep=None, sheen=0.18, dark="ink", lines=40,
                axis_lat=True, lat_range=(-1.2, 1.3), outline=True):
    O = sh.outline(0.0, n=64, keep=keep)
    cv.fill(O, base, 0.98, "paint")
    # sheen: lighter crescent towards the upper left
    c = O.mean(0)
    cv.blob(c + np.array([-0.18, -0.22]) * (O.max(0) - O.min(0)), (O[:, 0].max() - O[:, 0].min()) * 0.32,
            (O[:, 1].max() - O[:, 1].min()) * 0.18, "ink_l", sheen * 1.2, rot=-0.5, mode="paint")
    _shell_strands(cv, sh, axis_lat, lines, s * 0.0026, dark, 0.7, rng, lat_range)
    _shell_strands(cv, sh, axis_lat, lines // 3, s * 0.0022, pal.hexs(pal.mix(base, "white", 0.35)),
                   0.35, rng, lat_range)
    cv.edge(O, s * 0.025, "ink", 0.45, side=_inward(O, O), rows=3, closed=True)
    if outline:
        cv.stroke(np.vstack([O, O[:1]]), s * 0.0045, "ink", 0.85, prof="iron", caps=False)
    return O


def lady_hair_back(cv, fd, T, length=0.0, color="hair"):
    """Hair behind the neck (drawn before the body)."""
    H = fd.H
    s = H.s
    far = fd.far
    sk = Shell(H, (0.0, 0.62, -0.20), (0.24, 0.20, 0.18))
    O = sk.outline(0.0, n=48)
    cv.fill(O, color, 0.97, "paint")
    return O


def lady_hair(cv, fd, color="hair", style="high_bun", seed=0, volume=0.03, puff=1.0,
              bun_h=1.0, loops=0, tiers=2):
    """Court lady's hair (仕女): centre parting, hair swept smoothly over the temples and the
    tops of the ears with soft volume (鬓), gathered into a high two-tier bun (高髻)."""
    H = fd.H
    s = H.s
    far = fd.far
    rng = np.random.default_rng(seed + 9)
    # the mass is laid in a slightly lighter ink so the combed strands (darker) can be read
    base = pal.hexs(pal.mix(pal.hexs(pal.mix(color, "ink_m", 0.22)), "hair_white", 0.03))
    dark = "ink"
    light = pal.hexs(pal.mix(base, "white", 0.32))
    out = {}
    # --- high bun: one big cloud bun (云髻), optionally a second lobe set back ---
    buns = []
    tilt = -6 * far
    if style == "double":           # 双髻: twin buns, for young ladies and swordswomen
        tiers_spec = [((-far * 0.17, -0.03, -0.02), (0.125, 0.115, 0.12)),
                      ((far * 0.17, -0.03, -0.06), (0.120, 0.110, 0.115))]
    elif style == "low":            # 低髻: a low, quiet chignon behind the crown (matrons)
        tiers_spec = [((0.0, 0.03, -0.20), (0.20, 0.13, 0.17))]
    elif style == "tilted":         # 倭堕髻: a large bun leaning to one side
        tiers_spec = [((-far * 0.12, -0.07, -0.05), (0.21, 0.15 * bun_h, 0.17))]
        if tiers > 1:
            tiers_spec.append(((far * 0.06, -0.15 * bun_h, -0.12), (0.12, 0.09 * bun_h, 0.10)))
        tilt = 16 * far
    else:                           # 高髻: one big cloud bun, optionally a second lobe set back
        tiers_spec = [((0.0, -0.06, -0.04), (0.235, 0.16 * bun_h, 0.19))]
        if tiers > 1:
            tiers_spec.append(((-far * 0.10, -0.17 * bun_h, -0.12), (0.13, 0.10 * bun_h, 0.11)))
    for c, r in tiers_spec[::-1]:
        bun = Shell(H, c, r, tilt=tilt)
        O = _shell_mass(cv, bun, base, rng, s, lines=55, lat_range=(-1.3, 1.4), sheen=0.22)
        buns.append(bun)
    out["bun"] = buns[-1]
    out["bun_top"] = buns[0]
    # --- cranium hair with centre parting, temples puffed over the ears ---
    def vol(y):
        return volume + 0.06 * puff * np.exp(-((y - 0.42) / 0.12) ** 2)
    hl = np.array([(far * 1.30, 0.56), (far * 1.05, 0.44), (far * 0.85, 0.33), (far * 0.55, 0.262),
                   (far * 0.22, 0.236), (0.0, 0.240), (-far * 0.22, 0.236), (-far * 0.55, 0.262),
                   (-far * 0.85, 0.33), (-far * 1.02, 0.44), (-far * 1.18, 0.54),
                   (-far * 1.45, 0.585), (-far * 1.75, 0.58), (-far * 2.3, 0.62)])
    HLc = g.catmull(hl, 8)
    dr_l = np.array([vol(y) * (0.15 if abs(lo) < 1.0 else min(1.0, (abs(lo) - 0.9) * 2.0))
                     for lo, y in HLc])
    HL = np.vstack([H.Plon(lo, y, d) for (lo, y), d in zip(HLc, dr_l)])
    near_sil, _ = H.silhouette(0.0, hl[-1, 1], 50, side=-far, dr=vol)
    far_sil, _ = H.silhouette(0.0, hl[0, 1], 50, side=far, dr=vol)
    HLin = feather_hairline(cv, fd, HL, base, s, width=0.009, wash=0.12)
    poly = np.vstack([HLin, near_sil[::-1], far_sil])
    cv.fill(poly, base, 0.98, "paint")

    def strand(lon0, y0, lon1, y1, w, col, al, n=30):
        t = np.linspace(0, 1, n)
        lo = lon0 + (lon1 - lon0) * t
        yy = y0 + (y1 - y0) * (1 - (1 - t) ** 1.6)
        P = np.vstack([H.Plon(a, b, vol(b) * (0.2 + 0.8 * min(1, abs(a) / 1.0))) for a, b in zip(lo, yy)])
        vis = H.facing_lon(lo, yy) > 0.02
        for seg in _segments_visible(P, vis):
            cv.stroke(seg, w, col, al, prof="hair", noise=0.12)
    # strands from the parting sweeping down over the temples then back to the nape
    for i in range(190):
        sd = 1 if rng.uniform() < 0.5 else -1
        y_start = rng.uniform(0.0, 0.05)
        lon_end = sd * rng.uniform(1.2, 2.4)
        y_end = rng.uniform(0.38, 0.56)
        strand(sd * 0.03, y_start, lon_end, y_end, s * 0.0026 * rng.uniform(0.7, 1.2), dark,
               0.7 * rng.uniform(0.5, 1))
        if i % 3 == 0:
            strand(sd * 0.03, y_start, lon_end, y_end, s * 0.0022, light, 0.35)
    # sheen bands either side of the parting
    for sd in (-1, 1):
        lo = np.linspace(sd * 0.10, sd * 1.3, 30)
        yy = np.linspace(0.07, 0.30, 30)
        A_ = np.vstack([H.Plon(a, b - 0.025, vol(b)) for a, b in zip(lo, yy)])
        B_ = np.vstack([H.Plon(a, b + 0.025, vol(b)) for a, b in zip(lo, yy)])
        vis = H.facing_lon(lo, yy) > 0.05
        if vis.sum() > 4:
            cv.band(A_[vis], B_[vis], "ink_l", lambda S, T: 0.22 * np.sin(np.pi * T) *
                    np.sin(np.pi * S) ** 0.7, mode="paint", rows=3)
    pt = H.Plon(np.zeros(12), np.linspace(0.0, 0.215, 12), volume)
    cv.stroke(pt, s * 0.003, "skin_ivory", 0.45, prof="silk")
    # hairline fringe (fine baby hairs at the forehead and temples)
    HLd = g.resample(HL[int(len(HL) * 0.12): int(len(HL) * 0.55)], 120)
    nrm = g.normals(HLd)
    tan = g.tangents(HLd)
    cen = H.P([(0.0, 0.5)])[0]
    for i in range(len(HLd)):
        p = HLd[i]
        nv = nrm[i] if np.dot(cen - p, nrm[i]) < 0 else -nrm[i]
        L = s * rng.uniform(0.010, 0.025)
        q = p + nv * L + tan[i] * rng.normal(0, 0.4) * L
        cv.stroke(np.array([p - nv * s * 0.003, (p + q) / 2, q]), s * 0.0018, base,
                  rng.uniform(0.45, 0.85), prof="hair", noise=0.1)
    rim = np.vstack([near_sil[::-1], far_sil])
    cv.edge(rim, s * 0.05, "ink", 0.35, side=_inward(rim, poly), rows=4)
    cv.edge(HL, s * 0.03, "ink", 0.25, side=_inward(HL, poly), rows=3)
    cv.stroke(rim, s * 0.0045, "ink", 0.7, prof="iron")
    out.update(poly=poly, hairline=HL, base=base)
    return out


def lady_ornaments(cv, fd, hres, phoenix=True, flower="rouge", pins=3, comb=True,
                   pearls=True, gold="gold", jade="malachite_l", crown=True, huadian=True,
                   earring=True):
    H = fd.H
    s = H.s
    far = fd.far
    F = fd.F
    rng = np.random.default_rng(5)
    bun = hres["bun"]
    # 花钿: a small red petal mark between the brows
    if huadian:
        c = H.P([(0.0, F.brow_y - 0.035)], 0.01)[0]
        P = np.array([c + [0, -s * 0.016], c + [s * 0.007, -s * 0.002], c + [0, s * 0.010],
                      c + [-s * 0.007, -s * 0.002]])
        cv.fill(g.catmull(P, 6, closed=True), "vermilion", 0.9, "paint")
        cv.dot(c + [0, s * 0.014], s * 0.0035, "vermilion", 0.9)
    # earring (耳坠) on the visible ear: gold hook, pearl and a jade drop
    if earring and "ear" in fd.lm:
        E = fd.lm["ear"]
        lobe = E[int(len(E) * 0.80)]
        cv.stroke(np.array([lobe, lobe + [0, s * 0.02]]), s * 0.004, gold, 1.0, prof="flat")
        cv.dot(lobe + [0, s * 0.026], s * 0.008, "white", 1.0)
        P = g.ellipse(lobe + [0, s * 0.052], s * 0.009, s * 0.016, n=14)
        cv.fill(P, jade, 1.0, "paint")
        cv.dot(lobe + [-s * 0.003, s * 0.046], s * 0.003, "white", 0.7)
    # gold crown fan (花冠) in front of the bun: radiating gilt leaves with gems
    if crown:
        base = bun.P(0.0, 0.05, 0.02)
        for k in range(-3, 4):
            a = math.radians(-90 + 17 * k)
            L = s * (0.13 - 0.012 * abs(k))
            tip = base + np.array([math.cos(a), math.sin(a)]) * L
            mid = base + (tip - base) * 0.55
            nrm = np.array([-math.sin(a), math.cos(a)])
            leaf = g.catmull([base, mid + nrm * s * 0.022, tip, mid - nrm * s * 0.022], 6, closed=True)
            cv.fill(leaf, gold, 1.0, "paint")
            cv.stroke(np.array([base + (tip - base) * 0.15, tip - (tip - base) * 0.1]), s * 0.002,
                      "gold_d", 0.9, prof="silk")
            cv.stroke(np.vstack([leaf, leaf[:1]]), s * 0.0035, "gold_d", 0.95, prof="flat", caps=False)
            cv.dot(tip, s * 0.008, "cinnabar" if k % 2 else "malachite_l", 1.0)
        cv.fill(g.ellipse(base, s * 0.05, s * 0.022, n=24), gold, 1.0, "paint")
        cv.dot(base, s * 0.013, "cinnabar", 1.0)
        cv.dot(base - s * 0.003, s * 0.005, "white", 0.6)
    # comb (梳) at the front of the bun: half-moon of gold with fine teeth
    if comb:
        c = bun.P(0.0, -0.05, 0.01)
        ar = g.ellipse(c, s * 0.10, s * 0.045, 0.0, n=30, a0=math.pi, a1=2 * math.pi, endpoint=True)
        cv.fill(np.vstack([ar, ar[:1]]), gold, 1.0, "paint")
        cv.band(ar, c + (ar - c) * 0.55, "gold_d", 0.35, rows=2)
        for k in range(1, 12):
            p = g.at(ar, k / 12)
            cv.stroke(np.array([p, c + (p - c) * 0.55]), s * 0.002, "gold_d", 0.8, prof="flat")
        cv.stroke(ar, s * 0.004, "ink", 0.85, prof="iron", caps=False)
        for k in (0.25, 0.5, 0.75):
            cv.dot(g.at(ar, k) + (c - g.at(ar, k)) * 0.2, s * 0.010, "cinnabar", 1.0)
    # hairpins (簪): long gold pins with jade heads, inserted diagonally into the bun
    for k in range(pins):
        ang = math.radians(-35 + 35 * k) * far
        base_p = bun.P(far * (0.6 + 0.3 * k), 0.3 - 0.25 * k, 0.0)
        d = np.array([math.cos(ang) * far, -abs(math.sin(ang)) - 0.3])
        d = d / np.linalg.norm(d)
        a = base_p - d * s * 0.05
        b = base_p + d * s * 0.16
        cv.stroke(np.array([a, b]), s * 0.007, gold, 1.0, prof="flat")
        cv.stroke(np.array([a, b]) + np.array([-s * 0.002, -s * 0.002]), s * 0.002, "gold_l", 0.9,
                  prof="flat")
        cv.dot(b, s * 0.016, jade if k % 2 == 0 else "white", 1.0)
        cv.dot(b - s * 0.004, s * 0.006, "white", 0.7)
        cv.stroke(np.vstack([g.ellipse(b, s * 0.016, s * 0.016, n=16), g.ellipse(b, s * 0.016, s * 0.016, n=16)[:1]]),
                  s * 0.003, "ink", 0.8, prof="flat", caps=False)
    # phoenix hairpin (凤钗) with dangling pearls (步摇) on the near side of the bun
    if phoenix:
        p0 = bun.P(-far * 1.05, 0.15, 0.02)
        body = np.array([p0, p0 + [-far * s * 0.05, -s * 0.03], p0 + [-far * s * 0.10, -s * 0.015],
                         p0 + [-far * s * 0.13, s * 0.02]])
        B = g.catmull(body, 8)
        cv.stroke(B, s * 0.022, gold, 1.0, prof="orchid", taper=(0.3, 0.7))
        # head and crest
        hd = p0 + [far * s * 0.012, -s * 0.012]
        cv.dot(hd, s * 0.014, gold, 1.0)
        cv.stroke(np.array([hd, hd + [far * s * 0.03, -s * 0.03]]), s * 0.006, gold, 1.0, prof="tail")
        cv.dot(hd + [far * s * 0.004, -s * 0.004], s * 0.004, "ink", 1.0)
        # tail feathers sweeping back
        for k in range(4):
            a0 = p0 + [-far * s * 0.04, -s * 0.02]
            a1 = a0 + [-far * s * (0.08 + 0.02 * k), -s * (0.07 - 0.03 * k)]
            a2 = a1 + [-far * s * 0.05, s * 0.02 * k]
            cv.stroke(g.catmull([a0, a1, a2], 6), s * 0.010, gold, 1.0, prof="orchid")
            cv.stroke(g.catmull([a0, a1, a2], 6), s * 0.003, "gold_d", 0.9, prof="silk")
            cv.dot(a2, s * 0.007, "cinnabar", 1.0)
        cv.stroke(B, s * 0.004, "gold_d", 0.9, prof="silk")
        # 步摇: pearl strings from the beak/tail
        if pearls:
            for k in range(3):
                top = p0 + [-far * s * (0.03 + 0.04 * k), s * 0.01]
                L = s * (0.10 + 0.05 * (k == 1))
                for j in range(7):
                    c = top + np.array([math.sin(j * 0.6 + k) * s * 0.004, j * L / 7])
                    cv.dot(c, s * 0.0065, "white", 1.0)
                    cv.dot(c + [s * 0.002, s * 0.002], s * 0.0035, "#c9c1b2", 0.7)
                cv.fill(g.ellipse(top + [0, L + s * 0.012], s * 0.008, s * 0.014, n=12), gold, 1.0)
    # flower (簪花) on the far side of the bun / temple
    if flower:
        c = bun.P(far * 1.25, -0.25, 0.04)
        dark = pal.hexs(pal.mix(flower, "carmine", 0.5))
        for ring_k, (rr, n_p, col, al) in enumerate(((0.050, 7, flower, 1.0), (0.032, 6, "rouge", 1.0),
                                                     (0.018, 5, dark, 1.0))):
            for k in range(n_p):
                a = 2 * math.pi * k / n_p + ring_k * 0.4
                pc = c + np.array([math.cos(a), math.sin(a) * 0.8]) * s * rr * 0.65
                P = g.ellipse(pc, s * rr * 0.62, s * rr * 0.40, a, n=16)
                cv.fill(P, col, al, "paint")
                cv.band(P[:8], (P[:8] + pc) / 2, "white", 0.25, mode="paint", rows=2)
                cv.stroke(np.vstack([P, P[:1]]), s * 0.0025, dark, 0.8, prof="silk", caps=False)
        cv.dot(c, s * 0.010, "gold_l", 1.0)
        for k in range(2):
            a = (0.6 + 1.6 * k) * far
            lf = c + np.array([math.cos(a), math.sin(a)]) * s * 0.06
            P = g.ellipse(lf, s * 0.035, s * 0.014, a, n=16)
            cv.fill(P, "malachite", 1.0, "paint")
            cv.stroke(np.vstack([P, P[:1]]), s * 0.0025, "ink", 0.7, prof="silk", caps=False)
    return True


def bald(cv, fd, skin=None, dots=True, stubble=0.25):
    """Shaven head (monks): the cranium in skin with a soft crown light and ordination dots."""
    H = fd.H
    s = H.s
    far = fd.far
    F = fd.F
    skin = skin or F.skin
    near_sil, _ = H.silhouette(0.0, 0.62, 40, side=-far, dr=0.004)
    far_sil, _ = H.silhouette(0.0, 0.45, 40, side=far, dr=0.004)
    # join with the face polygon top: fill the dome down to the brow line
    poly = np.vstack([near_sil[::-1], far_sil, H.P([(far * 0.2, 0.30), (0.0, 0.26), (-far * 0.25, 0.30)])])
    cv.fill(poly, skin, 1.0, "paint")
    if stubble:
        cv.fill(poly, "ink_l", 0.12 * stubble, "glaze")
    rim = np.vstack([near_sil[::-1], far_sil])
    cv.edge(rim, s * 0.07, F.shade, 0.35 * F.shade_k, side=_inward(rim, poly), rows=5)
    cv.blob(H.Plon(np.array([-0.4]), np.array([0.12]))[0],
            s * 0.10, s * 0.06, "white", 0.25, mode="paint")
    cv.stroke(rim, s * 0.0045, F.line, 0.85, prof="iron")
    if dots:
        for i in range(3):
            for j in range(3):
                lo = (i - 1) * 0.28
                y = 0.08 + 0.05 * j
                if H.facing_lon(np.array([lo]), np.array([y]))[0] > 0.1:
                    p = H.Plon(np.array([lo]), np.array([y]), 0.003)[0]
                    cv.dot(p, s * 0.006, F.shade, 0.6)
    return dict(poly=poly)
