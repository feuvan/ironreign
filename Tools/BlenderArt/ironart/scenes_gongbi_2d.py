"""Illustrated Scenes (gongbi): painted 2D elements laid into the composite.

Some motifs are painted, not modelled: the moon left as bare silk inside an ink-blue sky
(烘云托月), the sun disc, a comet, fireworks bursts, falling petals, rain, locust swarms, soft
washes.  A :class:`Canvas` holds two layers at render resolution:

* ``sky``    under every 3D object (composited over the sky wash, can also *cut* the wash)
* ``front``  over the painting (petals, rain) before the silk texture is applied

Shapes are rasterised with Pillow at ``ovs`` x the render size and box-filtered down, so edges are
anti-aliased.  Coordinates are normalised image coordinates (x right, y down, 0..1); widths and
radii are in game (1x) px and scaled by ``k`` (render px per game px).
"""

import math

import numpy as np

from . import scenes_gongbi as GB


class _Draw:
    def __init__(self, cv, where, color, alpha, soft, mode):
        from PIL import Image, ImageDraw
        self.cv = cv
        self.where = where
        self.color = np.array(GB.srgb(color), np.float32) if color is not None else None
        self.alpha = alpha
        self.soft = soft
        self.mode = mode
        self.W, self.H = cv.W * cv.ovs, cv.H * cv.ovs
        self.im = Image.new("L", (self.W, self.H), 0)
        self.d = ImageDraw.Draw(self.im)

    # coordinates -------------------------------------------------------------------------------
    def P(self, x, y):
        return (x * self.W, y * self.H)

    def px(self, v):
        return v * self.cv.k * self.cv.ovs

    # shapes ------------------------------------------------------------------------------------
    def disc(self, c, r, value=255):
        x, y = self.P(*c)
        rr = self.px(r)
        self.d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=value)

    def ellipse(self, c, rx, ry, value=255):
        x, y = self.P(*c)
        self.d.ellipse((x - self.px(rx), y - self.px(ry), x + self.px(rx), y + self.px(ry)), fill=value)

    def ring(self, c, r, width, value=255):
        x, y = self.P(*c)
        rr = self.px(r)
        self.d.ellipse((x - rr, y - rr, x + rr, y + rr), outline=value, width=max(1, int(round(self.px(width)))))

    def polygon(self, pts, value=255):
        self.d.polygon([self.P(*p) for p in pts], fill=value)

    def stroke(self, pts, width, profile="taper", value=255, w_fn=None):
        """Tapered brush stroke along normalised points ``pts`` (width in game px)."""
        P = np.array([self.P(*p) for p in pts], np.float64)
        if len(P) < 2:
            return
        # resample densely
        seg = np.sqrt(((P[1:] - P[:-1]) ** 2).sum(-1))
        L = np.concatenate([[0], np.cumsum(seg)])
        if L[-1] < 1e-6:
            return
        n = max(8, int(L[-1] / 3))
        t = np.linspace(0, L[-1], n)
        Q = np.stack([np.interp(t, L, P[:, 0]), np.interp(t, L, P[:, 1])], -1)
        u = t / L[-1]
        if w_fn is not None:
            wp = np.array([w_fn(x) for x in u])
        elif profile == "taper":
            wp = np.minimum(np.clip(u / 0.15, 0, 1) ** 0.6, np.clip((1 - u) / 0.45, 0, 1) ** 0.8) * 0.9 + 0.1
        elif profile == "tail":
            wp = np.clip(1 - u, 0, 1) ** 0.9 * np.clip(u / 0.05, 0, 1) ** 0.5
        elif profile == "head":
            wp = np.clip(u, 0, 1) ** 1.2
        else:
            wp = np.ones_like(u)
        w = self.px(width) * wp * 0.5
        d = np.gradient(Q, axis=0)
        nrm = np.stack([-d[:, 1], d[:, 0]], -1)
        nrm /= np.maximum(np.linalg.norm(nrm, axis=-1, keepdims=True), 1e-9)
        left = Q + nrm * w[:, None]
        right = Q - nrm * w[:, None]
        poly = [tuple(p) for p in left] + [tuple(p) for p in right[::-1]]
        self.d.polygon(poly, fill=value)

    def petal(self, c, size, angle, value=255):
        """Single tear-drop petal (normalised centre, size in game px, angle radians)."""
        x, y = self.P(*c)
        s = self.px(size)
        pts = []
        for i in range(24):
            a = i / 24 * math.tau
            r = (0.55 + 0.45 * math.cos(a)) * s
            px_, py_ = math.cos(a) * r, math.sin(a) * r * 0.55
            ca, sa = math.cos(angle), math.sin(angle)
            pts.append((x + px_ * ca - py_ * sa, y + px_ * sa + py_ * ca))
        self.d.polygon(pts, fill=value)


class Canvas:
    """Two painted 2D layers (``sky`` under the 3D objects, ``front`` over the painting)."""

    def __init__(self, W, H, k=4.0, ovs=2):
        self.W, self.H, self.k, self.ovs = W, H, k, ovs
        self.layers = {"sky": [], "front": []}

    def paint(self, where, color, alpha=1.0, soft=0.0, mode="over"):
        """Context manager collecting shapes into one mask, composited on exit.

        mode 'over' paints ``color``; 'cut' erases the sky wash under the shapes (bare silk)."""
        cv = self

        class _Ctx:
            def __enter__(s):
                s.dr = _Draw(cv, where, color, alpha, soft, mode)
                return s.dr

            def __exit__(s, *a):
                dr = s.dr
                m = np.asarray(dr.im.reduce(cv.ovs), np.float32) / 255.0 if cv.ovs > 1 else \
                    np.asarray(dr.im, np.float32) / 255.0
                if soft > 0:
                    m = GB.blur(m, soft * cv.k)
                cv.layers[where].append((m * alpha, dr.color, mode))
                return False
        return _Ctx()

    def add_mask(self, where, mask, color, alpha=1.0, mode="over"):
        self.layers[where].append((np.clip(mask, 0, 1).astype(np.float32) * alpha,
                                   np.array(GB.srgb(color), np.float32) if color is not None else None, mode))

    def under(self, skc, ska):
        """Composite the sky layer over the sky wash (colour, alpha)."""
        for m, c, mode in self.layers["sky"]:
            if mode == "cut":
                ska = ska * (1 - m)
                continue
            skc = (skc * (ska * (1 - m))[..., None] + c[None, None, :] * m[..., None]) / \
                np.maximum(m + ska * (1 - m), 1e-5)[..., None]
            ska = m + ska * (1 - m)
        return skc, ska

    def over(self, img):
        for m, c, mode in self.layers["front"]:
            if mode == "cut":
                continue
            img = img * (1 - m[..., None]) + c[None, None, :] * m[..., None]
        return img


# =============================================================================================
# motifs
# =============================================================================================
def moon(cv, c, r, sky_cut=1.0, halo=2.2, color="white", rim="ink_grey", rim_alpha=0.35,
         where="sky"):
    """Full moon left as (nearly) bare silk in the sky wash: a soft cleared halo, a lead-white
    disc with a whisper of an ink rim."""
    with cv.paint(where, None, sky_cut * 0.6, soft=r * 0.9, mode="cut") as d:
        d.disc(c, r * halo)
    with cv.paint(where, None, sky_cut, soft=0.6, mode="cut") as d:
        d.disc(c, r * 1.02)
    with cv.paint(where, color, 0.85, soft=0.4) as d:
        d.disc(c, r)
    with cv.paint(where, rim, rim_alpha, soft=0.25) as d:
        d.ring(c, r, 0.9)


def sun(cv, c, r, color="vermilion", alpha=0.85, halo_color="#E8B888", halo=0.25):
    """Sun as a flat cinnabar / vermilion disc (as in court landscape paintings), with a faint
    warm wash around it."""
    with cv.paint("sky", halo_color, halo, soft=r * 1.6) as d:
        d.disc(c, r * 2.0)
    with cv.paint("sky", color, alpha, soft=0.35) as d:
        d.disc(c, r)


def comet(cv, head, tail_dir, length, width, color="cinnabar", core="#F2D8A8", rays=9, seed=0):
    """Broom star (彗星): a bright head and a fan of tapered cinnabar tail strokes."""
    rng = np.random.default_rng(seed)
    hx, hy = head
    a0 = math.atan2(tail_dir[1], tail_dir[0])
    asp = cv.W / cv.H
    with cv.paint("sky", color, 0.35, soft=width * 1.4) as d:
        pts = [(hx + math.cos(a0) * length * t / asp, hy + math.sin(a0) * length * t) for t in np.linspace(0, 1, 12)]
        d.stroke(pts, width * 2.6, "tail")
    for i in range(rays):
        f = (i - (rays - 1) / 2) / max(1, (rays - 1) / 2)
        a = a0 + f * 0.11 + rng.uniform(-0.015, 0.015)
        L = length * (1.0 - abs(f) * 0.35) * rng.uniform(0.85, 1.05)
        curve = rng.uniform(-0.03, 0.03)
        pts = []
        for t in np.linspace(0, 1, 16):
            aa = a + curve * t
            pts.append((hx + math.cos(aa) * L * t / asp, hy + math.sin(aa) * L * t))
        with cv.paint("sky", color if i % 3 else "vermilion", 0.75, soft=0.3) as d:
            d.stroke(pts, width * rng.uniform(0.35, 0.6), "tail")
    with cv.paint("sky", core, 0.95, soft=width * 0.4) as d:
        d.disc(head, width * 0.75)
    with cv.paint("sky", "white", 1.0, soft=0.3) as d:
        d.disc(head, width * 0.35)


def firework(cv, c, r, colors=("gold", "vermilion"), rays=36, seed=0, dots=True, alpha=0.9):
    """Painted fireworks burst: tapered rays from a centre ending in dots (like a chrysanthemum)."""
    rng = np.random.default_rng(seed)
    cx, cy = c
    with cv.paint("sky", colors[0], 0.18, soft=r * 0.35) as d:
        d.disc(c, r * 0.9)
    for i in range(rays):
        a = i / rays * math.tau + rng.uniform(-0.06, 0.06)
        L = r * rng.uniform(0.75, 1.0)
        r0 = r * 0.12
        pts = [(cx + math.cos(a) * (r0 + (L - r0) * t) * cv.k / cv.W,
                cy + math.sin(a) * (r0 + (L - r0) * t) * cv.k / cv.H) for t in np.linspace(0, 1, 6)]
        col = colors[i % len(colors)]
        with cv.paint("sky", col, alpha, soft=0.2) as d:
            d.stroke(pts, rng.uniform(1.0, 1.6), "head")
            if dots:
                ex, ey = pts[-1]
                d.disc((ex + math.cos(a) * 1.8 * cv.k / cv.W, ey + math.sin(a) * 1.8 * cv.k / cv.H), rng.uniform(0.9, 1.4))
    with cv.paint("sky", "white", 0.9, soft=0.4) as d:
        d.disc(c, r * 0.07)


def petals(cv, n, region, size=(2.0, 3.5), colors=("#E8B4B8", "white", "rouge"), seed=0,
           wind=(1.0, 0.35), where="front", outline=0.45):
    """Falling blossom petals drifting with the wind (front layer), each with a fine rouge /
    ink outline."""
    rng = np.random.default_rng(seed)
    x0, y0, x1, y1 = region
    for col in colors:
        m = n // len(colors)
        cs = [(rng.uniform(x0, x1), rng.uniform(y0, y1)) for _ in range(m)]
        ss = [rng.uniform(*size) for _ in range(m)]
        aa = [math.atan2(wind[1], wind[0]) + rng.uniform(-1.2, 1.2) for _ in range(m)]
        with cv.paint(where, "rouge", outline, soft=0.0) as d:
            for c, s, a in zip(cs, ss, aa):
                d.petal(c, s * 1.18, a)
        with cv.paint(where, col, 0.95, soft=0.0) as d:
            for c, s, a in zip(cs, ss, aa):
                d.petal(c, s, a)


def rain(cv, n, region, length=40.0, angle=1.25, width=0.5, color="ink_grey", alpha=0.35, seed=0,
         where="front"):
    rng = np.random.default_rng(seed)
    x0, y0, x1, y1 = region
    with cv.paint(where, color, alpha, soft=0.0) as d:
        for _ in range(n):
            x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
            L = length * rng.uniform(0.5, 1.2) * cv.k
            dx, dy = math.cos(angle) * L / (cv.W), math.sin(angle) * L / (cv.H)
            d.stroke([(x, y), (x + dx, y + dy)], width * rng.uniform(0.6, 1.2), "taper")


def swarm(cv, n, density, size=(1.2, 2.4), color="ink", alpha=0.85, seed=0, where="front",
          wing_color="#8A7A50"):
    """Locust swarm: ``n`` insects placed by ``density`` (H x W array 0..1, render res) - each a
    tiny body stroke with two pale wing strokes."""
    rng = np.random.default_rng(seed)
    p = density.ravel().astype(np.float64)
    p = p / p.sum()
    idx = rng.choice(p.size, size=n, p=p)
    ys, xs = np.unravel_index(idx, density.shape)
    xs = (xs + rng.random(n)) / density.shape[1]
    ys = (ys + rng.random(n)) / density.shape[0]
    ang = rng.uniform(-0.6, 0.6, n) + rng.choice([0, math.pi], n)
    sz = rng.uniform(*size, n)
    with cv.paint(where, wing_color, alpha * 0.55, soft=0.0) as d:
        for x, y, a, s in zip(xs, ys, ang, sz):
            for sd in (-1, 1):
                wa = a + sd * 1.9
                ex = x + math.cos(wa) * s * 0.9 * cv.k / cv.W
                ey = y + math.sin(wa) * s * 0.9 * cv.k / cv.H
                d.stroke([(x, y), (ex, ey)], s * 0.5, "taper")
    with cv.paint(where, color, alpha, soft=0.0) as d:
        for x, y, a, s in zip(xs, ys, ang, sz):
            ex = x + math.cos(a) * s * cv.k / cv.W
            ey = y + math.sin(a) * s * cv.k / cv.H
            d.stroke([(x, y), (ex, ey)], s * 0.42, "flat")


def wash(cv, where, color, alpha, shape, soft, **kw):
    """Soft painted wash: ``shape`` = ('disc', c, r) | ('ellipse', c, rx, ry) | ('poly', pts)."""
    with cv.paint(where, color, alpha, soft=soft) as d:
        if shape[0] == "disc":
            d.disc(shape[1], shape[2])
        elif shape[0] == "ellipse":
            d.ellipse(shape[1], shape[2], shape[3])
        else:
            d.polygon(shape[1])
