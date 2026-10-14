"""Title_Logo.png (1200x400, transparent; the title screen draws it at 960x320).

Back to front:
    calligraphy  铁血王座 in large flowing brush calligraphy (Brush.ttf = Ma Shan Zheng), set as
                 a rising, tilting line across the whole width: graded ink (wet strokes near
                 black #1E1A16, thin and dry parts greyer), flying-white (飞白) dry-brush streaks
                 that follow each stroke (line-integral convolution along the stroke direction),
                 a little bleed into the paper fibres at the edges
    seal         the 铁血 baiwen impression of Seal.png, smaller, lower right
    letters      "IRON REIGN" (Heading.ttf = Marcellus) in mud-gold (泥金): flat gold powder
                 with a soft 晕染 (paler top, deeper ochre towards the bottom and into the
                 outline), a fine ink outline and a narrow silk-coloured keyline outside it, so
                 the word reads over the black calligraphy and over any background
No shading, no shine, no shadow: a painted title block on a transparent ground.
"""

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ironart import ui_chrome_paint as P
from ironart import ui_chrome_sdf as S
import seal

NAME = "Title_Logo"
SPEC = dict(size=(1200, 400), ss=4, seed=81)
W, H = 1200, 400
TEXT = "IRON REIGN"
TEXT_W = 1000.0           # width of the gold word (px)
TEXT_CY = 210.0           # its vertical centre
TRACK = 0.075             # letter spacing (fraction of the cap height)
#: calligraphy layout: (char, cx, cy, height px, rotation deg, shear)
CALLI = [("铁", 188.0, 178.0, 330.0, -5.0, 0.08), ("血", 452.0, 214.0, 290.0, 3.0, 0.05),
         ("王", 735.0, 180.0, 270.0, -3.0, 0.08), ("座", 1012.0, 196.0, 330.0, 4.0, 0.07)]
SEAL = (1128.0, 330.0, 72.0, -4.0)
OUTLINE = 3.0             # ink outline of the letters (px)
KEYLINE = 1.7             # silk keyline outside the ink


def _font(name):
    from common import font
    return font(name)


def glyph_layer(G):
    """Anti-aliased coverage of the calligraphy composition on the render grid."""
    ss = G.ss
    big = 600
    f = ImageFont.truetype(_font("Brush.ttf"), big)
    canvas = Image.new("L", (G.nx, G.ny), 0)
    for ch, cx, cy, hgt, rot, shear in CALLI:
        im = Image.new("L", (big * 2, big * 2), 0)
        ImageDraw.Draw(im).text((big // 2, big // 2), ch, font=f, fill=255)
        im = im.crop(im.getbbox())
        k = hgt * ss / im.height
        im = im.resize((max(1, int(im.width * k)), int(im.height * k)), Image.LANCZOS)
        w0, h0 = im.size
        im = im.transform((w0 + int(abs(shear) * h0), h0), Image.AFFINE,
                          (1, shear, -shear * h0 if shear > 0 else 0, 0, 1, 0), Image.BICUBIC)
        im = im.rotate(rot, Image.BICUBIC, expand=True)
        canvas.paste(Image.new("L", im.size, 255), (int(cx * ss - im.width / 2),
                                                    int(cy * ss - im.height / 2)), im)
    return np.asarray(canvas, np.float32) / 255.0


def lic(noise, angle, length, step):
    """Line integral convolution of ``noise`` along per-pixel directions ``angle`` (radians):
    straight-line samples +-length (samples) - streaks that follow each brush stroke."""
    h, w = noise.shape
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    ca, sa = np.cos(angle), np.sin(angle)
    acc = np.zeros_like(noise)
    n = 0
    for t in np.arange(-length, length + 1e-3, step):
        x = np.clip(xs + ca * t, 0, w - 1).astype(np.int32)
        y = np.clip(ys + sa * t, 0, h - 1).astype(np.int32)
        acc += noise[y, x]
        n += 1
    return acc / n


def _down(a, k):
    h, w = a.shape
    return a[:h // k * k, :w // k * k].reshape(h // k, k, w // k, k).mean((1, 3))


def _up(a, shape):
    return np.asarray(Image.fromarray(a.astype(np.float32), "F").resize((shape[1], shape[0]),
                      Image.BILINEAR), np.float32)


def stroke_angle(mask, sigma_px, ss):
    """Stroke direction (radians, along the stroke) from the structure tensor of the blurred
    glyph mask, at 1 sample per target px, upsampled as tensor components."""
    lo = _down(mask, ss)
    b = S.blur(lo, sigma_px)
    gy, gx = np.gradient(b)
    jxx = S.blur(gx * gx, sigma_px * 1.5)
    jyy = S.blur(gy * gy, sigma_px * 1.5)
    jxy = S.blur(gx * gy, sigma_px * 1.5)
    c2 = _up(jxx - jyy, mask.shape)
    s2 = _up(2 * jxy, mask.shape)
    return 0.5 * np.arctan2(s2, c2) + math.pi / 2


def calligraphy(G, seed):
    """(alpha, colour) of the ink calligraphy."""
    ss = G.ss
    g = glyph_layer(G)
    rng = np.random.default_rng(seed)
    ang = stroke_angle(g, 5.0, ss)
    noise = S.blur(rng.random(G.shape).astype(np.float32), 0.6 * ss)
    streak = lic(noise, ang, 10.0 * ss, 1.0 * ss)
    streak = (streak - streak.mean()) / (streak.std() + 1e-6)
    inner = _up(S.blur(_down(g, ss), 2.4), G.shape)              # ~ depth inside the stroke
    patch = P.fbm2(G, 55.0, seed + 9, octaves=3)
    thin = 1 - P.smoothstep(0.45, 0.9, inner)                      # stroke edges and tails
    dry = P.smoothstep(0.2, 1.3, patch) * (0.35 + 0.65 * thin) + 0.3 * P.smoothstep(0.9, 1.7, patch)
    gaps = P.smoothstep(0.15, 0.95, streak * 0.9 + dry * 2.0 - 0.45)
    cover = g * (1 - 0.97 * gaps * P.smoothstep(0.1, 0.38, dry + 0.06 * streak))
    # edge bleed into the paper fibres + a faint watery halo
    feather = S.blur(cover, 0.45 * ss)
    fib = S.fibres(G.shape, G.w * G.h * 0.008, 3 * ss, 0.3 * ss, seed + 13, 0.8, 0.6, 1.0)
    cover = np.maximum(cover, 0.55 * feather * (fib > 0.2))
    halo = np.clip(S.blur(g, 1.4 * ss) - g, 0, 1) * 0.35 * (1 - dry)
    # ink tone: wet cores near black, pools where the brush paused, greyer dry edges
    pools = P.smoothstep(0.6, 1.6, P.fbm2(G, 26.0, seed + 15, octaves=2))
    tone = np.clip(P.smoothstep(0.25, 0.85, inner) * (1 - 0.55 * dry) + 0.35 * pools * inner, 0, 1)
    alpha = np.clip(np.clip(cover, 0, 1) * (0.74 + 0.24 * tone) + halo, 0, 1)
    col = P.mix("#5C5249", "ink", 0.25 + 0.75 * tone)
    col = col * (1.0 + 0.05 * P.fine_grain(G, seed + 14, 0.6) * (1 - tone))[..., None]
    return alpha, col


def word_mask(G):
    """Coverage of the word on the render grid (letter-spaced, centred)."""
    ss = G.ss
    px = 400
    f = ImageFont.truetype(_font("Heading.ttf"), px)
    # measure each letter for tracking
    asc, desc = f.getmetrics()
    cap = f.getbbox("I")[3] - f.getbbox("I")[1]
    track = TRACK * cap
    widths = [f.getlength(c) for c in TEXT]
    total = sum(widths) + track * (len(TEXT) - 1)
    im = Image.new("L", (int(total + px), px * 2), 0)
    dr = ImageDraw.Draw(im)
    x = px / 2
    for c, w in zip(TEXT, widths):
        dr.text((x, px / 2), c, font=f, fill=255)
        x += w + track
    im = im.crop(im.getbbox())
    k = TEXT_W * ss / im.width
    im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    canvas = Image.new("L", (G.nx, G.ny), 0)
    canvas.paste(im, (int((G.nx - im.width) / 2), int(TEXT_CY * ss - im.height / 2)))
    return np.asarray(canvas, np.float32) / 255.0, im.height / ss


def dilate(mask, r, G):
    """Round dilation by ``r`` target px (gaussian + threshold), anti-aliased."""
    sig = max(0.5, r * G.ss / 1.6)
    b = S.blur(mask, sig)
    th = 0.5 * math.erfc(1.6 / math.sqrt(2))       # value of the blurred step at distance r
    return P.smoothstep(th * 0.6, th * 1.6, b) if r > 0 else mask


def paint(G, variant=None, seed=None):
    seed = SPEC["seed"] if seed is None else seed
    C = P.Canvas(G)
    a, col = calligraphy(G, seed)
    C.over(a, col)
    sx, sy, side, rot = SEAL
    sa, scol = seal.impression(G, sx, sy, side, rot, seed + 30, width=5.0 * side / 104.0,
                               stretch=2.2, gap=4.0 * side / 104.0, margin=6.5 * side / 104.0)
    C.over(sa * 0.95, scol)
    # ---- the gold word -----------------------------------------------------------------------
    m, hpx = word_mask(G)
    key = dilate(m, OUTLINE + KEYLINE, G)
    ink = dilate(m, OUTLINE, G)
    C.over(key, P.mix("silk", "lead_white", 0.2), 0.88)
    C.over(ink, "ink")
    y = (G.Y - (TEXT_CY - hpx / 2)) / hpx
    y = np.broadcast_to(y, G.shape)
    gold = P.gold_field(G, seed + 5, grain=0.04, flecks=0.05)
    gold = P.mix(gold, "#E3C77F", 0.45 * (1 - P.smoothstep(0.0, 0.55, y)))
    gold = P.mix(gold, "#9A7432", 0.45 * P.smoothstep(0.45, 1.05, y))
    inner = S.blur(m, 1.6 * G.ss)
    gold = P.mix(gold, "#8E6A2C", 0.55 * (1 - P.smoothstep(0.55, 0.98, inner)))
    C.over(m, gold)
    return C.rgba()
