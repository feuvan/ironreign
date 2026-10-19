"""Fx_Fire / Fx_Confuse / Fx_Rally / Fx_Hit (96x96, transparent): painted gongbi motifs.

    Tools/BlenderArt/render.sh Tools/BlenderArt/battle/fx.py      (or system python3)

Painted as exact signed-distance shapes on a 4x grid (:mod:`ironart.ui_chrome_sdf`, the UI
family's ornament vocabulary), laid like a gongbi painter lays them - mineral fills graded with
soft 晕染, then a fine ink (or cinnabar-ink) contour and engraved inner lines - and downsampled.

    Fire     火焰纹: one flame mass - teardrop body, S-curved main tongue, four side tongues and
             two foot licks with curled tips - in concentric bands (cinnabar rim, vermilion,
             mud-gold core, pale heart), cinnabar-ink contour and inner contour lines, sparks
    Confuse  swirling ink clouds: an ink spiral at the centre wound by three xiangyun cloud
             heads in an azurite-grey wash with engraved volutes, motion strokes
    Rally    a war drum (cinnabar-lacquered barrel, mud-gold studs, pale hide) on its stand with
             two crossed drumsticks, radiating mud-gold brush strokes behind
    Hit      an ink splash (泼墨): a lobed blot with wet-ink density, radiating flicks, droplets
"""

import math
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from ironart import post  # noqa: E402
from ironart import ui_chrome_ornament as O  # noqa: E402
from ironart import ui_chrome_sdf as S  # noqa: E402

SS = 4
W = H = 96


def rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


class Layer:
    """Premultiplied RGBA painting on the 4x grid."""

    def __init__(self, G):
        self.G = G
        self.c = np.zeros(G.shape + (3,), np.float32)
        self.a = np.zeros(G.shape, np.float32)

    def over(self, mask, color, alpha=1.0):
        m = np.clip(mask * alpha, 0, 1)
        col = color if isinstance(color, np.ndarray) and color.ndim == 3 else np.asarray(color, np.float32)
        self.c = self.c * (1 - m[..., None]) + col * m[..., None]
        self.a = self.a * (1 - m) + m

    def glaze(self, mask, color, k=1.0):
        """Multiply what is painted (keeps alpha)."""
        m = np.clip(mask * k, 0, 1)[..., None]
        self.c = self.c * (1 - m + m * np.asarray(color, np.float32))

    def rgba(self):
        a = np.maximum(self.a, 1e-6)
        out = np.dstack([self.c / a[..., None], self.a])
        out[..., :3] = np.where(self.a[..., None] > 1e-5, out[..., :3], 0)
        return out.astype(np.float32)

    def composite(self, img):
        """Lay an RGBA (straight) image over."""
        self.over(img[..., 3], img[..., :3], 1.0)


def finish(layer, name):
    img = layer.rgba()
    img = post.downsample(img, SS)
    img = post.alpha_cleanup(img, bleed=2)
    img[0, :, 3] = img[-1, :, 3] = 0
    img[:, 0, 3] = img[:, -1, 3] = 0
    return img


def grid():
    return S.Grid(W, H, SS)


def rotate_rgba(img, deg, cx, cy):
    """Rotate a straight RGBA float image about (cx, cy) target px (premultiplied resample)."""
    pm = img.copy()
    pm[..., :3] *= pm[..., 3:4]
    chans = []
    for k in range(4):
        im = Image.fromarray(pm[..., k], "F")
        im = im.rotate(deg, resample=Image.BICUBIC, center=(cx * SS, cy * SS))
        chans.append(np.asarray(im, np.float32))
    out = np.dstack(chans)
    a = np.clip(out[..., 3], 0, 1)
    out[..., :3] = np.where(a[..., None] > 1e-4, out[..., :3] / np.maximum(a[..., None], 1e-4), 0)
    out[..., 3] = a
    return np.clip(out, 0, 1)


# ---------------------------------------------------------------------------------------------
# fire
# ---------------------------------------------------------------------------------------------
def fire():
    """火焰纹: one flame mass - a broad teardrop body whose S-curved central tongue leans up to a
    sharp tip, with four side tongues licking out of its flanks at different heights, each tip
    turning over in a small curl. Laid in concentric bands like a painted flame halo: cinnabar
    rim, vermilion middle, mud-gold core (paler at the heart), cinnabar-ink contour and inner
    contour lines following the outline, a few curling sparks."""
    G = grid()
    L = Layer(G)
    rng = np.random.default_rng(3)

    def tongue(p0, c1, c2, tip, w, curl, out, curl_r=2.6):
        p = S.bezier(p0, c1, c2, tip, 56)
        t = np.linspace(0.0, 1.0, len(p), dtype=np.float32)
        r = (w * np.clip(np.sin(np.pi * np.clip(0.5 + 0.5 * t ** 0.8, 0, 1)), 0, 1) ** 0.9 + 0.3).astype(np.float32)
        S.sd_polyline(G, p, r, out=out, pad=2)
        if curl:
            d = p[-1] - p[-4]
            ta = math.degrees(math.atan2(float(d[1]), float(d[0])))
            # the curl continues the tip direction and rolls over towards ``curl`` (+1 right, -1 left)
            cx = float(p[-1][0]) + curl * curl_r * math.cos(math.radians(ta + 90))
            cy = float(p[-1][1]) + curl * curl_r * math.sin(math.radians(ta + 90))
            a0 = math.degrees(math.atan2(float(p[-1][1]) - cy, float(p[-1][0]) - cx))
            sp = S.spiral(cx, cy, curl_r, curl_r * 0.25, 0.8, a0, cw=curl > 0, n=18)
            S.sd_polyline(G, sp, np.linspace(0.75, 0.25, len(sp)).astype(np.float32), out=out, pad=2)
        return p

    body = G.empty()
    # the teardrop: round base, S-curved column tapering to the main tip
    lines = []
    lines.append(tongue((48, 70), (36, 46), (60, 30), (49, 6), 18.0, -1, body, 2.8))
    S.sd_circle(G, 48, 69, 19.5, out=body, pad=2)
    side = G.empty()
    lines.append(tongue((36, 70), (20, 64), (12, 50), (17, 32), 7.5, 1, side))
    lines.append(tongue((38, 52), (26, 44), (25, 32), (31, 21), 5.5, 1, side, 2.2))
    lines.append(tongue((60, 71), (76, 64), (85, 52), (80, 30), 7.5, -1, side))
    lines.append(tongue((58, 50), (70, 42), (71, 31), (65, 18), 5.5, -1, side, 2.2))
    # small licks at the foot
    lines.append(tongue((40, 82), (30, 84), (25, 78), (24, 72), 3.6, 1, side, 1.6))
    lines.append(tongue((57, 82), (67, 84), (72, 78), (73, 70), 3.6, -1, side, 1.6))
    body = S.smooth_union(body, side, 3.2)
    m = S.aa_mask(body, G)
    # bands: rim (cinnabar) / middle (vermilion) / core (mud gold), soft-edged (晕染)
    t = np.clip((G.Y - 8) / 80.0, 0, 1)[..., None]
    rim = rgb("#A8301F")[None, None] * (1 - t) + rgb("#C2412A")[None, None] * t
    L.over(m, rim)
    mid = S.blur(S.aa_mask(body + 4.2, G), 0.7 * SS)
    L.over(mid * m, rgb("#DD6B36"), 0.95)
    core = S.blur(S.aa_mask(body + 9.5, G), 1.0 * SS)
    L.over(core * m, rgb("#E9B85A"), 0.95)
    heart = S.blur(S.aa_mask(body + 14.0, G), 1.6 * SS)
    L.over(heart * m, rgb("#F6E2AE"), 0.85)
    # deeper cinnabar along the rim (graded inward)
    L.glaze(np.clip(1 + body / 2.6, 0, 1) * m, rgb("#8E2618") / rgb("#B8402A"), 0.5)
    # inner contour lines following the outline (engraved flame lines), cinnabar ink
    for off, a in ((4.2, 0.55), (9.5, 0.4)):
        L.over(S.band(body, -off - 0.32, -off + 0.32, G) * m, rgb("#8A2417"), a)
    # outer contour
    L.over(S.band(body, -0.8, 0.35, G), rgb("#5A140E"), 0.95)
    # sparks: curls and dots rising beside the tongues
    for i, (cx, cy) in enumerate(((22, 14), (76, 12), (60, 6))):
        sp = S.spiral(cx, cy, rng.uniform(2.0, 2.6), 0.5, 0.85, rng.uniform(0, 360), cw=bool(i % 2), n=16)
        sd = S.sd_polyline(G, sp, np.linspace(0.85, 0.3, len(sp)).astype(np.float32), pad=1)
        L.over(S.aa_mask(sd, G), rgb("#C2452E") if i % 2 else rgb("#D9A24A"), 0.95)
    return finish(L, "Fire")


# ---------------------------------------------------------------------------------------------
# confuse
# ---------------------------------------------------------------------------------------------
def cloud_layer(cx, cy, size, flip=False):
    G = grid()
    L = Layer(G)
    shape, lines = O.xiangyun(G, cx, cy, size, flip=flip)
    m = S.aa_mask(shape, G)
    t = np.clip((G.Y - (cy - size)) / (2 * size), 0, 1)
    fill = rgb("#C4CCD6")[None, None] * (1 - t[..., None]) + rgb("#7E90A6")[None, None] * t[..., None]
    L.over(m, fill, 0.92)
    L.glaze(np.clip(1 + shape / 3.0, 0, 1) * m, rgb("#5E6E86") / rgb("#A0AEC0"), 0.5)
    L.over(np.clip(0.5 - (lines - 0.45) / (G.px), 0, 1) * m, rgb("#2A2F3A"), 0.75)
    L.over(S.band(shape, -0.7, 0.3, G), rgb("#1E1A16"), 0.95)
    return L.rgba()


def confuse():
    G = grid()
    L = Layer(G)
    # swirl strokes (ink) at the centre: a wet ink spiral and two thinner ones
    for (r0, turns, w, a0, alpha, col) in ((30, 1.55, 3.4, 0, 0.9, "#1E1A16"), (26, 1.2, 1.6, 140, 0.7, "#2E3A50"),
                                           (34, 0.9, 1.2, 250, 0.55, "#3E4E68")):
        sp = S.spiral(48, 50, r0, 3.0, turns, a0, cw=True, n=90)
        sd = S.sd_polyline(G, sp, S.taper(len(sp), w * 0.3, w * 0.2, w_mid=w), pad=2)
        L.over(S.aa_mask(sd, G), rgb(col), alpha)
    # three cloud heads wound round it
    for k, (ang, size, flip) in enumerate(((-90, 15, False), (30, 13, True), (150, 13.5, False))):
        a = math.radians(ang)
        cx, cy = 48 + 27 * math.cos(a), 50 + 27 * math.sin(a)
        img = cloud_layer(cx, cy, size, flip)
        img = rotate_rgba(img, -(ang + 90), cx, cy)
        L.composite(img)
    # small motion dots
    rng = np.random.default_rng(5)
    for i in range(7):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(36, 42)
        sd = S.sd_circle(G, 48 + r * math.cos(a), 50 + r * math.sin(a), rng.uniform(0.8, 1.6))
        L.over(S.aa_mask(sd, G), rgb("#2A2F3A"), 0.8)
    return finish(L, "Confuse")


# ---------------------------------------------------------------------------------------------
# rally
# ---------------------------------------------------------------------------------------------
def rally():
    G = grid()
    L = Layer(G)
    cx, cy = 48, 50
    rng = np.random.default_rng(9)
    # radiating brush strokes (behind)
    for k in range(18):
        a = 2 * math.pi * k / 18 + 0.08
        long = k % 2 == 0
        r0, r1 = 26, (45 if long else 37) + rng.uniform(-2, 2)
        p = np.array([[cx + r0 * math.cos(a), cy + r0 * math.sin(a)],
                      [cx + (r0 + r1) / 2 * math.cos(a + 0.03), cy + (r0 + r1) / 2 * math.sin(a + 0.03)],
                      [cx + r1 * math.cos(a + 0.05), cy + r1 * math.sin(a + 0.05)]], np.float32)
        p = S.bezier(p[0], p[1], p[1], p[2], 16)
        sd = S.sd_polyline(G, p, S.taper(len(p), 2.4 if long else 1.8, 0.2), pad=2)
        m = S.aa_mask(sd, G)
        L.over(m, rgb("#C9A24B") if long else rgb("#D0643C"), 0.95)
        L.over(S.band(sd, -0.5, 0.3, G), rgb("#6E4A1E"), 0.5)
    # stand: two crossed legs
    for sx in (-1, 1):
        p = np.array([[cx - sx * 14, cy + 8], [cx + sx * 16, cy + 36]], np.float32)
        sd = S.sd_polyline(G, p, 2.0, pad=2)
        L.over(S.aa_mask(sd, G), rgb("#4A3020"))
        L.over(S.band(sd, -0.6, 0.3, G), rgb("#1E1A16"))
    # barrel: a bulging drum seen a little from above
    rx, top, bot = 20.0, cy - 9.0, cy + 12.0
    X, Y = G.X, G.Y
    yy = np.clip((Y - top) / (bot - top), 0, 1)
    bulge = rx + 3.0 * np.sin(np.pi * yy)
    side = np.abs(X - cx) - bulge
    vert = np.maximum(top - Y, Y - bot)
    bottom_ell = ((X - cx) / rx) ** 2 + ((Y - bot) / 6.0) ** 2 - 1.0
    barrel = np.maximum(side, np.minimum(vert, bottom_ell * 6.0))
    barrel = np.minimum(barrel, np.maximum(side, bottom_ell * 6.0))
    barrel = np.maximum(barrel, -np.minimum(np.maximum(side, vert), 0) * 0 - 999) if False else barrel
    m = S.aa_mask(np.maximum(side, np.where(Y < top, top - Y, np.where(Y > bot, bottom_ell * 6.0, -1.0))), G)
    shade = np.clip(np.abs(X - cx) / (rx + 3), 0, 1) ** 2
    lac = rgb("#B5382A")[None, None] * (1 - shade[..., None]) + rgb("#7A2418")[None, None] * shade[..., None]
    L.over(m, lac)
    # mud-gold studs along the top and bottom rims, gold hoops
    for ycen, ry in ((top, 6.0), (bot, 6.0)):
        ring = ((X - cx) / (rx + 0.5)) ** 2 + ((Y - ycen - 2.2) / ry) ** 2
        hoop = np.clip(1 - np.abs(ring - 1.0) * 9, 0, 1) * (Y > ycen - 0.5) * m
        L.over(hoop, rgb("#C9A24B"), 0.85)
        for k in range(9):
            a = math.pi * (0.1 + 0.8 * k / 8)
            sx_, sy_ = cx + (rx + 0.3) * math.cos(a), ycen + 2.2 + ry * math.sin(a)
            sd = S.sd_circle(G, sx_, sy_, 1.25)
            L.over(S.aa_mask(sd, G), rgb("#E0C47E"))
            L.over(S.band(sd, -0.35, 0.25, G), rgb("#6E4A1E"), 0.8)
    # hide (top ellipse)
    skin = ((X - cx) / rx) ** 2 + ((Y - top) / 6.5) ** 2 - 1.0
    ms = np.clip(0.5 - skin * 8.0 / (G.px * 8.0), 0, 1)
    ms = S.aa_mask(skin * 6.5, G)
    L.over(ms, rgb("#EAD9B4"))
    L.glaze(ms * np.clip((Y - top + 6.5) / 13.0, 0, 1), rgb("#C8B08A") / rgb("#EAD9B4"), 0.6)
    emb = ((X - cx) / 7.0) ** 2 + ((Y - top) / 2.4) ** 2 - 1.0
    L.over(S.aa_mask(emb * 2.4, G) * ms, rgb("#B5382A"), 0.85)
    # ink contours
    L.over(np.clip(1 - np.abs(skin * 6.5) / 0.8, 0, 1), rgb("#1E1A16"), 0.95)
    outline = np.maximum(side, np.where(Y < top, top - Y, np.where(Y > bot, bottom_ell * 6.0, -1.0)))
    L.over(S.band(outline, -0.8, 0.3, G) * (Y > top - 0.5), rgb("#1E1A16"), 0.95)
    # crossed drumsticks with cinnabar knobs
    for sx in (-1, 1):
        p = np.array([[cx + sx * 22, cy - 30], [cx - sx * 4, cy - 8]], np.float32)
        sd = S.sd_polyline(G, p, np.array([1.6, 1.1], np.float32), pad=2)
        L.over(S.aa_mask(sd, G), rgb("#8A6440"))
        L.over(S.band(sd, -0.5, 0.3, G), rgb("#1E1A16"))
        kn = S.sd_circle(G, cx + sx * 22, cy - 30, 3.0)
        L.over(S.aa_mask(kn, G), rgb("#B5382A"))
        L.over(S.band(kn, -0.5, 0.3, G), rgb("#1E1A16"))
    return finish(L, "Rally")


# ---------------------------------------------------------------------------------------------
# hit
# ---------------------------------------------------------------------------------------------
def hit():
    G = grid()
    L = Layer(G)
    rng = np.random.default_rng(13)
    cx, cy = 48, 48
    X, Y = G.X, G.Y
    ang = np.arctan2(Y - cy, X - cx)
    r = np.hypot(X - cx, Y - cy)
    lob = 15.0 + 3.0 * np.sin(5 * ang + 0.7) + 2.0 * np.sin(9 * ang + 2.1) + 1.2 * np.sin(14 * ang + 0.3)
    n = S.fbm(G.shape, 10 * SS, 21, octaves=3)
    blot = r - lob - (n - 0.5) * 7.0
    sd = blot
    # flicks radiating out
    for k in range(17):
        a = 2 * math.pi * k / 17 + rng.uniform(-0.2, 0.2)
        L0 = rng.uniform(12, 18)
        L1 = L0 + rng.uniform(6, 28)
        p = np.array([[cx + L0 * math.cos(a), cy + L0 * math.sin(a)],
                      [cx + L1 * math.cos(a + rng.uniform(-0.06, 0.06)), cy + L1 * math.sin(a + rng.uniform(-0.06, 0.06))]],
                     np.float32)
        p = S.bezier(p[0], (p[0] + p[1]) / 2, (p[0] + p[1]) / 2, p[1], 12)
        f = S.sd_polyline(G, p, S.taper(len(p), rng.uniform(1.3, 2.8), 0.15, power=0.7), pad=2)
        sd = S.smooth_union(sd, f, 2.0)
        # a droplet beyond the flick
        if rng.random() < 0.7:
            d = L1 + rng.uniform(3, 8)
            sd = np.minimum(sd, S.sd_circle(G, cx + d * math.cos(a), cy + d * math.sin(a), rng.uniform(0.9, 2.4)))
    for i in range(14):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(20, 42)
        sd = np.minimum(sd, S.sd_circle(G, cx + d * math.cos(a), cy + d * math.sin(a), rng.uniform(0.6, 1.8)))
    halo = S.blur(S.aa_mask(blot - 2.5, G), 1.6 * SS)
    L.over(halo, rgb("#5A5650"), 0.3)
    m = S.aa_mask(sd, G)
    # wet ink density: darker pools, greyer thin parts
    dens = S.fbm(G.shape, 6 * SS, 33, octaves=3)
    col = rgb("#1E1A16")[None, None] * np.ones(G.shape + (1,), np.float32)
    grey = np.clip((dens - 0.45) * 2.2, 0, 1) * np.clip(-sd / 6.0, 0, 1) * 0.35
    col = col * (1 - grey[..., None]) + rgb("#5C5650")[None, None] * grey[..., None]
    L.over(m, col, 0.97)
    # a dry-brush edge: a few lighter streaks across the blot
    streak = S.fbm(G.shape, 3 * SS, 41, octaves=2, aniso=(3.0, 0.4))
    L.glaze(m * np.clip((streak - 0.62) * 4, 0, 1) * (r < lob - 3), rgb("#7A7468") / rgb("#1E1A16") * 0.3 + 0.7, 0.5)
    return finish(L, "Hit")


FX = {"Fire": fire, "Confuse": confuse, "Rally": rally, "Hit": hit}


def main(names=None):
    names = names or list(FX)
    out = []
    for n in names:
        img = FX[n]()
        p = post.save_asset(img, "Art/Battle/Fx_%s.png" % n)
        print("[battle] wrote %s" % p)
        out.append(p)
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-") and a in FX]
    main(args or None)
