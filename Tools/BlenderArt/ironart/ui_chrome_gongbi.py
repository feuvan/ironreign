"""UI chrome family: gongbi (工笔) material painting, v2 - numpy + Pillow only (no bpy, no scipy).

The UI chrome is painted like a classical Chinese mounting (装裱): woven silk grounds, patterned
silk brocade, mud-gold (泥金) paint, mineral colours (cinnabar, azurite) with 晕染 gradients and
granulation, ruled and calligraphic ink.  This module holds the *materials*; the pieces in
``Tools/BlenderArt/ui_chrome/`` compose them on an :class:`ironart.ui_chrome_paint.Canvas`
(sampled on a ``ui_chrome_sdf.Grid``: ``ss`` samples per target px, image convention, +y down,
units = target px), and :mod:`ironart.ui_chrome_flat` renders the result through Cycles as a flat
orthographic emission plate.

Physical models (all deterministic from a seed)
    silk_weave       plain weave: warp/weft threads with per-thread tone, interlacing checker,
                     slubs along the weft; ~0.55 px pitch (resolves at @2x, a fine grain at @1x)
    silk_ground      aged silk colour: weave + large ageing mottle + tea stains + foxing specks
    strip_threads    the same silk reduced to a function of the distance across a 9-slice strip
                     (lengthwise threads), so Slate can stretch it
    brocade          woven pattern: twill ground (diagonal) + weft-float figure (horizontal floats
                     with staggered binding points), the figure in gold or coloured thread
    mineral          opaque mineral paint (cinnabar / azurite / malachite): granulation,
                     pigment pooling at the edge, 晕染 deepening towards the outline
    mud_gold         matte gold powder in glue: fine grain, sparse paler flecks, rim pooling
    ink_density      ink loading variation along a stroke (never flat black)
    glyph_mask       Pillow text rendering at the grid resolution (fonts from Content/Data/Fonts)
    lic / dry_brush  brush-hair streaks along a stroke-direction field (line integral
                     convolution) and 飞白 dry-brush breaks for calligraphy and brush lines

Colours are sRGB floats.  Every function returns float32 arrays on the grid.
"""

import math

import numpy as np

from . import ui_chrome_paint as P
from . import ui_chrome_sdf as S

TAU = 2.0 * math.pi


# =============================================================================================
# hashing / small helpers
# =============================================================================================
def _table(lo, hi, seed, kind="normal"):
    rng = np.random.default_rng(seed)
    n = int(hi - lo + 1)
    if kind == "normal":
        return rng.standard_normal(n).astype(np.float32)
    return rng.random(n).astype(np.float32)


def thread_index(coord, pitch, phase=0.0):
    """Thread index and the fractional position across the thread (0..1)."""
    q = np.asarray(coord, np.float32) / pitch + phase
    idx = np.floor(q).astype(np.int64)
    return idx, (q - idx).astype(np.float32)


def per_index(idx, seed, kind="normal"):
    lo, hi = int(idx.min()), int(idx.max())
    tab = _table(lo, hi, seed, kind)
    return tab[idx - lo]


def blur(a, sigma_px, G):
    """Gaussian blur with sigma in *target px* on grid G."""
    return S.blur(a, sigma_px * G.ss)


def norm(a):
    a = a.astype(np.float32)
    return (a - a.mean()) / (a.std() + 1e-6)


def value2(G, cell_px, seed, aniso=(1.0, 1.0)):
    """Value noise in [0, 1] with cell size in target px."""
    return S.value_noise(G.shape, cell_px * G.ss, seed, aniso)


def grain(G, seed, size_px=0.45):
    """Unit-std blurred white noise, feature size ``size_px`` (pigment particles)."""
    rng = np.random.default_rng(seed)
    n = rng.standard_normal(G.shape).astype(np.float32)
    n = S.blur(n, max(0.3, size_px * G.ss * 0.5))
    return norm(n)


def speckle(G, seed, density, size_px=0.6, sharp=0.7):
    """Sparse soft dots (0..1) covering about ``density`` of the area."""
    g = grain(G, seed, size_px)
    thr = _quantile_normal(1.0 - density)
    return P.smoothstep(thr - sharp * 0.5, thr + sharp * 0.5, g)


def _quantile_normal(p):
    # Acklam-ish rational approximation is overkill here; a few points are enough
    p = min(max(p, 1e-4), 1 - 1e-4)
    # inverse error function via Newton on erf
    x = 0.0
    for _ in range(40):
        f = 0.5 * (1.0 + math.erf(x / math.sqrt(2.0))) - p
        x -= f / (math.exp(-0.5 * x * x) / math.sqrt(TAU))
    return x


# =============================================================================================
# silk
# =============================================================================================
def silk_weave(G, seed, pitch=0.55, slub=1.0, crossing=0.55, region=None):
    """Plain-weave texture, zero-mean and ~unit std: per-thread tone of the warp (vertical) and
    weft (horizontal) threads, the interlacing checker (where the weft floats on top its tone
    shows, else the warp's), a darker gap between threads and slubs (thick spots) along the
    weft.  ``region`` = optional (slice_y, slice_x) to compute only part of the grid."""
    ys, xs = G.ys, G.xs
    if region is not None:
        ys, xs = ys[region[0]], xs[region[1]]
    iy, fy = thread_index(ys, pitch, 0.13)
    ix, fx = thread_index(xs, pitch * 1.07, 0.41)
    weft = per_index(iy, seed + 1)[:, None]
    warp = per_index(ix, seed + 2)[None, :]
    # thickness varies slowly along each thread (spun silk is not uniform)
    rng = np.random.default_rng(seed + 3)
    along = P.noise1d(xs, 9.0, seed + 4, octaves=2)[None, :] * (0.5 + 0.5 * rng.random(1)[0])
    weft = weft * 0.8 + 0.45 * along * per_index(iy, seed + 5)[:, None]
    chk = ((iy[:, None] + ix[None, :]) % 2).astype(np.float32)
    top = chk * weft + (1.0 - chk) * warp
    # thread cross-profile: brighter crown, darker gaps (both directions)
    gap = (np.cos(TAU * fy)[:, None] + np.cos(TAU * fx)[None, :]) * 0.5
    tex = top * 0.75 + crossing * (-gap)
    if slub > 0:
        shape = (len(ys), len(xs))
        sl = S.value_noise(shape, pitch * G.ss, seed + 6, aniso=(26.0, 1.0))
        sl = P.smoothstep(0.80, 0.93, sl) * 2.2 - P.smoothstep(0.80, 0.95, 1.0 - sl) * 1.2
        tex = tex + slub * sl
    return norm(tex)


def silk_ground(G, seed, light="#E6D6B0", dark="#D8C39A", weave=0.020, mottle=0.35,
                mottle_cell=70.0, stain=0.25, foxing=0.0, edge=None, edge_k=0.0,
                weave_field=None):
    """Aged silk colour field (rows, cols, 3).

    ``mottle``  0..1 how much of the light->dark range the large ageing mottle spans
    ``stain``   strength of warm tea-coloured stain blooms (soft, sparse)
    ``foxing``  density of tiny brown specks
    ``edge``    optional distance-from-edge field (target px) for an ageing wash towards the
                edges: weight ``edge_k`` at d = 0, gone by d = 40
    """
    m = P.fbm2(G, mottle_cell, seed + 11, octaves=4, gain=0.55)
    t = np.clip(0.5 + 0.28 * m * mottle * 2.0, 0.0, 1.0)
    col = P.mix(light, dark, t)
    if stain > 0:
        s = P.fbm2(G, mottle_cell * 0.6, seed + 12, octaves=3, gain=0.5)
        bloom = P.smoothstep(1.0, 2.2, s) * stain
        col = col * (1.0 - bloom[..., None] * (1.0 - P.rgb("#C9A878") / P.rgb(light)))
    if edge is not None and edge_k > 0:
        e = (1.0 - P.smoothstep(0.0, 40.0, edge)) ** 1.6 * edge_k
        col = P.mix(col, col * P.rgb("#C4AE84") / P.rgb(light), e)
    w = silk_weave(G, seed + 13) if weave_field is None else weave_field
    col = col * (1.0 + weave * w)[..., None]
    if foxing > 0:
        f = speckle(G, seed + 14, foxing, 0.9, 0.8)
        col = P.mix(col, col * np.array([0.80, 0.70, 0.58], np.float32), 0.55 * f)
    return np.clip(col, 0, 1).astype(np.float32)


def strip_threads(d, seed, pitch=0.5, amp=0.05, gap=0.35, slow=0.02, slow_period=3.0):
    """Lengthwise threads of a 9-slice strip as a multiplicative field of the across
    coordinate ``d`` only (~1.0): per-thread tone, darker gaps, a slow tonal drift."""
    idx, fr = thread_index(d, pitch, 0.27)
    tone = per_index(idx, seed) * 0.8
    prof = -gap * np.cos(TAU * fr)
    n = amp * (tone + prof)
    if slow > 0:
        n = n + slow * P.noise1d(d, slow_period, seed + 1, octaves=1)
    return (1.0 + n).astype(np.float32)


# =============================================================================================
# brocade
# =============================================================================================
def twill(G, seed, pitch=0.5, slope=1.0, region=None):
    """Twill ground: diagonal ridges (warp floats stepping one thread per pick), unit std."""
    ys, xs = G.ys, G.xs
    if region is not None:
        ys, xs = ys[region[0]], xs[region[1]]
    q = (xs[None, :] + slope * ys[:, None]) / (pitch * 2.0)
    idx = np.floor(q).astype(np.int64)
    fr = q - idx
    tone = per_index(idx, seed) * 0.6
    ridge = -np.cos(TAU * fr) * 0.9
    iy, _ = thread_index(ys, pitch)
    weft = per_index(iy, seed + 1)[:, None] * 0.35
    return norm(tone + ridge + weft)


def weft_floats(G, seed, pitch=0.5, float_len=2.2, region=None):
    """Figure texture of a brocade: horizontal weft floats (gold / coloured thread) with
    staggered binding points, unit std.  Returns (texture, binding mask)."""
    ys, xs = G.ys, G.xs
    if region is not None:
        ys, xs = ys[region[0]], xs[region[1]]
    iy, fy = thread_index(ys, pitch, 0.3)
    stagger = ((iy % 3) / 3.0)[:, None] * float_len
    qx = (xs[None, :] + stagger) / float_len
    fx = qx - np.floor(qx)
    bind = np.exp(-((np.minimum(fx, 1.0 - fx) * float_len) / 0.22) ** 2)     # binding point
    crown = np.cos(TAU * fy)[:, None]                                          # thread round
    tone = per_index(iy, seed)[:, None] * 0.5
    tex = tone + 0.9 * crown - 1.4 * bind
    return norm(tex), bind.astype(np.float32)


def brocade(G, figure, ground="#3B5D7C", ground_deep="#26425E", fig="#C2A060",
            fig_deep="#8E6E36", seed=0, pitch=0.5, float_len=2.2, ground_tex=0.07,
            fig_tex=0.10, outline=None, region=None):
    """Woven brocade colour field: ``figure`` (0..1 mask, the pattern) woven in ``fig`` thread
    over a twill ``ground``.  The figure deepens to ``fig_deep`` at its edges (threads dive
    into the cloth), the ground carries a soft tonal variation.  ``outline`` (0..1 mask) adds a
    darker contour thread around the figure."""
    shape = figure.shape
    tw = twill(G, seed + 1, pitch, region=region)
    fl, bind = weft_floats(G, seed + 2, pitch, float_len, region=region)
    gcol = P.mix(ground_deep, ground, 0.55 + 0.45 * np.clip(0.5 + 0.35 * tw, 0, 1))
    gcol = gcol * (1.0 + ground_tex * tw)[..., None]
    # figure edge falls off into the cloth: use a blurred figure as the depth cue
    soft = S.blur(figure, 0.35 * G.ss)
    fcol = P.mix(fig_deep, fig, P.smoothstep(0.25, 0.95, soft))
    fcol = fcol * (1.0 + fig_tex * fl)[..., None]
    col = gcol + (fcol - gcol) * figure[..., None]
    if outline is not None:
        col = col + (P.rgb(ground_deep) * 0.7 - col) * (outline * 0.8)[..., None]
    del shape
    return np.clip(col, 0, 1).astype(np.float32)


# =============================================================================================
# paints
# =============================================================================================
def rim(sd, width):
    """0..1 weight that is 1 at a shape's edge (sd = 0) and fades inwards over ``width`` px."""
    return (1.0 - P.smoothstep(0.0, width, -sd)).astype(np.float32)


def mineral(G, sd, base, deep, light=None, seed=0, yun=4.0, yun_power=1.4, gran=0.045,
            gran_size=0.45, pool=0.10, pool_w=0.6, bloom=0.0, bloom_cell=18.0, inner=None):
    """Opaque mineral paint inside ``sd`` < 0.

    ``yun``      晕染 width (px): the colour deepens from ``base`` to ``deep`` towards the edge
    ``light``    optional paler colour in the middle of wide shapes (the wash's light side)
    ``gran``     granulation amplitude (mineral particles settled in the silk)
    ``pool``     pigment pooled at the drying edge (darker rim ``pool_w`` px wide)
    ``bloom``    soft uneven loading of the wash (large cells), multiplicative
    ``inner``    optional field replacing ``-sd`` as the 晕染 coordinate (e.g. distance from
                 the outer edge of a 9-slice piece)
    """
    t = -sd if inner is None else inner
    k = P.smoothstep(0.0, yun, t) ** (1.0 / yun_power)
    col = P.mix(deep, base, k)
    if light is not None:
        col = P.mix(col, light, P.smoothstep(yun, yun * 3.0, t) * 0.6)
    if gran > 0:
        g = grain(G, seed + 1, gran_size)
        dark = np.maximum(g, 0.0) * 1.2 - np.maximum(-g, 0.0) * 0.6
        col = col * (1.0 - gran * dark)[..., None]
    if bloom > 0:
        b = P.fbm2(G, bloom_cell, seed + 2, octaves=3)
        col = col * (1.0 + bloom * b)[..., None]
    if pool > 0:
        col = col * (1.0 - pool * rim(sd, pool_w))[..., None]
    return np.clip(col, 0, 1).astype(np.float32)


def mud_gold(G, sd=None, seed=0, base="#C9A24B", light="#E2C67E", deep="#9A7633",
             yun=0.0, gran=0.07, flecks=0.010, pool=0.18, pool_w=0.45, shade=None):
    """Matte mud-gold (泥金): gold powder in glue.  Fine grain, sparse paler flecks (larger
    flakes), the powder pooled darker at the drying edge, optional 晕染 to ``deep`` over ``yun``
    px.  Never metallic: no highlight, no environment, no specular."""
    g = grain(G, seed + 1, 0.38)
    col = P.rgb(base) * (1.0 + gran * g)[..., None]
    col = np.broadcast_to(col, G.shape + (3,)).copy()
    if flecks > 0:
        f = speckle(G, seed + 2, flecks, 0.55, 0.6)
        col = P.mix(col, light, 0.75 * f)
    if sd is not None:
        if yun > 0:
            col = P.mix(deep, col, P.smoothstep(0.0, yun, -sd) ** 0.8)
        if pool > 0:
            col = col * (1.0 - pool * rim(sd, pool_w))[..., None]
    if shade is not None:
        col = col * shade[..., None]
    return np.clip(col, 0, 1).astype(np.float32)


def ink_density(G, seed, base="#1E1A16", var=0.10, cell=6.0):
    """Ink colour with a slight loading variation (a brush line is never flat black)."""
    n = P.fbm2(G, cell, seed, octaves=2)
    k = np.clip(var * n, -0.5, 0.5)
    c = P.rgb(base)
    paler = P.rgb("#4A3E33")
    return (c + (paler - c) * np.maximum(k, 0)[..., None]).astype(np.float32)


# =============================================================================================
# ruled lines / mounts
# =============================================================================================
def ruled(d, at, width, G, soft=1.0):
    """Anti-aliased ruled line (mitred when ``d`` is an inset distance): centre ``at``."""
    return S.aa_mask(np.abs(d - at) - width * 0.5, G, soft)


def band(d, d0, d1, G, soft=1.0):
    return S.band(d, d0, d1, G, soft)


def mitre_seam(G, w, h, d_lo, d_hi, width=0.18):
    """Thin diagonal seam where two mitred border strips meet (the four corners), limited to
    the band d_lo..d_hi of the mitred inset distance.  Returns a 0..1 mask."""
    X, Y = G.X, G.Y
    out = np.zeros(G.shape, np.float32)
    for (cx, cy, sx, sy) in ((0, 0, 1, 1), (w, 0, -1, 1), (0, h, 1, -1), (w, h, -1, -1)):
        u = (X - cx) * sx
        v = (Y - cy) * sy
        dd = np.abs(u - v) / math.sqrt(2.0)
        m = S.aa_mask(dd - width * 0.5, G) * (np.minimum(u, v) > d_lo) * (np.minimum(u, v) < d_hi)
        out = np.maximum(out, m.astype(np.float32))
    return out


def strip_axis(G, w, h):
    """Which way each sample's mitred strip runs: 1 = horizontal strip (top/bottom), 0 =
    vertical strip (left/right).  Lengthwise threads use the across coordinate of their
    strip; the switch happens on the mitre diagonals."""
    dx = np.minimum(G.X, w - G.X)
    dy = np.minimum(G.Y, h - G.Y)
    return (dy <= dx).astype(np.float32)


# =============================================================================================
# glyphs and brush
# =============================================================================================
def glyph_mask(G, text, font_path, size_px, x, y, anchor="ls", stroke_px=0.0, tracking=0.0,
               scale_xy=(1.0, 1.0), rotate=0.0, oversample=1):
    """Coverage mask (0..1) of ``text`` rendered with Pillow/FreeType at the grid resolution.
    ``size_px`` font size in target px, (x, y) the anchor point (target px), ``stroke_px`` a
    FreeType stroker outline (dilation), ``tracking`` extra letter spacing (target px),
    ``scale_xy`` an anisotropic scale about the anchor, ``rotate`` degrees (counter-clockwise
    on screen) about the anchor."""
    from PIL import Image, ImageDraw, ImageFont
    ss = G.ss * oversample
    f = ImageFont.truetype(font_path, max(1, int(round(size_px * ss))))
    sw = int(round(stroke_px * ss))
    # draw each glyph separately when tracking is used
    pad = int(size_px * ss * 0.6) + sw + 4
    if tracking:
        advs = [f.getlength(ch) + tracking * ss for ch in text]
        tw = int(sum(advs)) + 2 * pad
    else:
        tw = int(f.getlength(text)) + 2 * pad
    th = int(size_px * ss * 1.6) + 2 * pad
    im = Image.new("L", (tw, th), 0)
    dr = ImageDraw.Draw(im)
    ox, oy = pad, int(size_px * ss * 1.1) + pad      # baseline origin inside the tile
    if tracking:
        cx = ox
        for ch, a in zip(text, advs):
            dr.text((cx, oy), ch, font=f, fill=255, anchor="ls", stroke_width=sw, stroke_fill=255)
            cx += a
        total = cx - ox - tracking * ss
    else:
        dr.text((ox, oy), text, font=f, fill=255, anchor="ls", stroke_width=sw, stroke_fill=255)
        total = f.getlength(text)
    # anchor: horizontal l/m/r, vertical s (baseline) / m (middle of the ink bbox)
    a = np.asarray(im, np.float32) / 255.0
    nz = np.nonzero(a.max(1) > 0)[0]
    if anchor[0] == "m":
        axp = ox + total / 2.0
    elif anchor[0] == "r":
        axp = ox + total
    else:
        axp = ox
    if anchor[1] == "m" and len(nz):
        ayp = 0.5 * (nz[0] + nz[-1] + 1)
    else:
        ayp = oy
    if scale_xy != (1.0, 1.0) or rotate:
        im = im.transform(im.size, Image.AFFINE, _affine_about(axp, ayp, scale_xy, rotate),
                          resample=Image.BICUBIC)
        a = np.asarray(im, np.float32) / 255.0
    if oversample > 1:
        h2, w2 = a.shape[0] // oversample * oversample, a.shape[1] // oversample * oversample
        a = a[:h2, :w2].reshape(h2 // oversample, oversample, w2 // oversample, oversample).mean((1, 3))
        axp /= oversample
        ayp /= oversample
    # paste into the grid so that (axp, ayp) lands on (x, y)
    out = np.zeros(G.shape, np.float32)
    gx = int(round((x - G.x0) * G.ss - axp))
    gy = int(round((y - G.y0) * G.ss - ayp))
    h, w = a.shape
    y0, x0 = max(0, gy), max(0, gx)
    y1, x1 = min(G.ny, gy + h), min(G.nx, gx + w)
    if y1 > y0 and x1 > x0:
        out[y0:y1, x0:x1] = a[y0 - gy:y1 - gy, x0 - gx:x1 - gx]
    return out


def _affine_about(cx, cy, scale_xy, rot_deg):
    """Pillow AFFINE coefficients (output -> input) for scale then rotate about (cx, cy)."""
    sx, sy = scale_xy
    a = math.radians(rot_deg)
    c, s = math.cos(a), math.sin(a)
    # forward: p' = R S (p - c) + c ; inverse: p = S^-1 R^-1 (p' - c) + c
    # R^-1 for screen-ccw rotation with y down
    m00, m01 = c / sx, -s / sx
    m10, m11 = s / sy, c / sy
    return (m00, m01, cx - m00 * cx - m01 * cy, m10, m11, cy - m10 * cx - m11 * cy)


def direction_field(mask, sigma):
    """Dominant stroke direction (unit vectors along the stroke) from the structure tensor of
    a smoothed coverage mask; ``sigma`` in samples.  Returns (ux, uy, coherence)."""
    m = S.blur(mask, sigma * 0.5)
    gy, gx = np.gradient(m)
    jxx = S.blur(gx * gx, sigma)
    jyy = S.blur(gy * gy, sigma)
    jxy = S.blur(gx * gy, sigma)
    # eigenvector of the *smaller* eigenvalue = along the stroke
    ang = 0.5 * np.arctan2(2.0 * jxy, jxx - jyy) + math.pi / 2.0
    tr = jxx + jyy + 1e-9
    coh = np.sqrt((jxx - jyy) ** 2 + 4.0 * jxy ** 2) / tr
    return np.cos(ang).astype(np.float32), np.sin(ang).astype(np.float32), coh.astype(np.float32)


def _bilinear(img, x, y):
    h, w = img.shape
    x = np.clip(x, 0, w - 1.001)
    y = np.clip(y, 0, h - 1.001)
    x0 = x.astype(np.int32)
    y0 = y.astype(np.int32)
    fx = x - x0
    fy = y - y0
    a = img[y0, x0]
    b = img[y0, x0 + 1]
    c = img[y0 + 1, x0]
    d = img[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def lic(noise, ux, uy, length, step=1.0, sel=None):
    """Line integral convolution of ``noise`` along the unit field (ux, uy): streaks of
    ``length`` samples (brush hairs).  ``sel`` = optional boolean mask of samples to compute
    (others return 0)."""
    h, w = noise.shape
    if sel is None:
        sel = np.ones((h, w), bool)
    yy, xx = np.nonzero(sel)
    px = xx.astype(np.float32)
    py = yy.astype(np.float32)
    acc = noise[yy, xx].astype(np.float32).copy()
    wsum = np.ones_like(acc)
    n = int(length / step / 2)
    for sgn in (1.0, -1.0):
        x, y = px.copy(), py.copy()
        dx, dy = ux[yy, xx] * sgn, uy[yy, xx] * sgn
        for i in range(n):
            x += dx * step
            y += dy * step
            xi = np.clip(x.astype(np.int32), 0, w - 1)
            yi = np.clip(y.astype(np.int32), 0, h - 1)
            ndx, ndy = ux[yi, xi], uy[yi, xi]
            flip = (ndx * dx + ndy * dy) < 0
            ndx = np.where(flip, -ndx, ndx)
            ndy = np.where(flip, -ndy, ndy)
            dx, dy = ndx, ndy
            wgt = 1.0 - (i + 1) / (n + 1)
            acc += _bilinear(noise, x, y) * wgt
            wsum += wgt
    out = np.zeros((h, w), np.float32)
    out[yy, xx] = acc / wsum
    return out


def edge_distance(mask, G, max_px=8.0, steps=None):
    """Approximate distance (target px) from the inside of a coverage mask to its edge, up to
    ``max_px``: the mask is blurred at a ladder of radii and each level contributes where it is
    still saturated (cheap, smooth, good enough for washes and dry-brush weighting)."""
    steps = steps or [0.5, 1.0, 2.0, 3.0, 4.5, 6.0, 8.0, 12.0, 16.0, 24.0, 32.0]
    d = np.zeros(mask.shape, np.float32)
    prev = 0.0
    for r in steps:
        if r > max_px:
            break
        b = S.blur(mask, r * G.ss * 0.5)
        inside = P.smoothstep(0.80, 0.98, b)
        d += inside * (r - prev)
        prev = r
    return d * (mask > 0.5)


# =============================================================================================
# corner shapes
# =============================================================================================
def corner_uv(G, cx, cy, sx, sy):
    """Local corner coordinates: u, v = distance from the corner (cx, cy) along the two edges
    (``sx``, ``sy`` = +1/-1 direction into the piece)."""
    return (G.X - cx) * sx, (G.Y - cy) * sy


def ruyi_corner_sd(u, v, t0=8.0, tc=11.6, rc=3.1, sa=4.0, ts=8.4, rs=2.5, k=1.1, tip=1.6):
    """Ruyi-cloud corner wrap (包角) in local corner coordinates (target px): the corner
    triangle up to the diagonal distance ``t0`` plus a trefoil of lobes on the diagonal - a
    central lobe (radius ``rc`` centred at ``tc``) and two side lobes (``rs`` at ``ts``, ``sa``
    off the diagonal) - smooth-unioned, with a small point on the axis (``tip`` px beyond the
    central lobe).  sd < 0 inside."""
    r2 = math.sqrt(2.0)
    t = (u + v) / r2
    s = (u - v) / r2
    tri = t - t0
    c = np.hypot(s, t - tc) - rc
    l1 = np.hypot(s - sa, t - ts) - rs
    l2 = np.hypot(s + sa, t - ts) - rs
    lob = S.smooth_union(S.smooth_union(c, l1, k), l2, k)
    sd = S.smooth_union(tri, lob, k)
    if tip > 0:
        # the ruyi point: a narrow wedge on the axis beyond the central lobe
        tp = np.maximum(np.abs(s) * 2.2 - (tc + rc + tip - t), t - (tc + rc + tip))
        sd = np.minimum(sd, np.maximum(tp, -(t - tc)))
    # clip to the piece (u, v >= 0)
    sd = np.maximum(sd, np.maximum(-u, -v))
    return sd.astype(np.float32)


def mirror4(a):
    """Union (min) of an array with its three mirror images (four symmetric corners)."""
    out = np.minimum(a, a[:, ::-1])
    return np.minimum(out, out[::-1, :])


# =============================================================================================
# local painting
# =============================================================================================
def subcanvas(C, x0, y0, x1, y1):
    """A Canvas over the rectangle (x0, y0)-(x1, y1) target px of canvas ``C`` whose layers are
    *views* into C's arrays: paint small motifs there at a fraction of the cost (every painting
    operation of the Canvas works in place)."""
    G = C.G
    ss = G.ss
    i0 = max(0, int(math.floor((x0 - G.x0) * ss)))
    j0 = max(0, int(math.floor((y0 - G.y0) * ss)))
    i1 = min(G.nx, int(math.ceil((x1 - G.x0) * ss)))
    j1 = min(G.ny, int(math.ceil((y1 - G.y0) * ss)))
    Gs = S.Grid((i1 - i0) / ss, (j1 - j0) / ss, ss, x0=G.x0 + i0 / ss, y0=G.y0 + j0 / ss)
    Cs = P.Canvas.__new__(P.Canvas)
    Cs.G = Gs
    Cs.P = C.P[j0:j1, i0:i1]
    Cs.A = C.A[j0:j1, i0:i1]
    return Cs
