"""Background, neck, garments, armour, hair, facial hair and headgear for the
procedural portraits."""
import math

import numpy as np
from scipy import ndimage as ndi

from portrait_raster import (W, H, HH, WW, SCALE, LIGHT, grid, clamp01, smoothstep, blur, mix,
                             poly, polys, ellipse, stroke, strokes, stroke_outline, catmull,
                             resample, StrokeLayer, value_noise, fiber_noise, normals_from_height,
                             lambert, ink_outline, edge_distance, outside_distance, pillow, hexc,
                             shade_ramp)
from portrait_face import skin_palette, ear_anchor, INK

INK_SOFT = hexc('#3B2C20')


def ramp3(v, dark, mid, lite):
    return shade_ramp(v, dark, mid, lite)


def tone(col, k):
    """Darken (k<1) / lighten (k>1) a colour, keeping it muted."""
    c = np.asarray(col, np.float32)
    if k >= 1:
        return mix(c, np.array([0.95, 0.9, 0.82], np.float32), clamp01(k - 1))
    return c * k * np.array([1.0, 0.95, 0.92], np.float32) ** (1 - k)


def paint_shaded(cv, mask, col, light, rng=None, dark_k=0.42, lite_k=1.25, tex=0.05, tex_scale=4.0,
                 outline=0.75, ink_a=0.85, ink_light_bias=0.6):
    """Fill a mask with a 3-tone ramp driven by `light`, add texture and an ink outline."""
    v = light
    if rng is not None and tex:
        v = v + tex * value_noise(rng, tex_scale, 2)
    c = ramp3(clamp01(v), tone(col, dark_k), np.asarray(col, np.float32), tone(col, lite_k))
    cv.paint(mask, c)
    if outline:
        cv.paint(ink_outline(mask, outline, rng, 0.35, ink_light_bias), INK, ink_a)


def body_light(mask, radius, extra=None):
    """Pillow shading plus a top-to-bottom falloff for torso shapes."""
    _, Y = grid()
    l = pillow(mask, radius, 1.0)
    fall = 1.0 - 0.35 * smoothstep(170, 240, Y)
    v = l * fall
    if extra is not None:
        v = v * extra
    return v


# ----------------------------------------------------------------------
# Background
# ----------------------------------------------------------------------

def draw_background(cv, rng):
    X, Y = grid()
    r = np.sqrt(((X - 78) / 150.0) ** 2 + ((Y - 78) / 175.0) ** 2)
    mid = hexc('#4A3C2D')
    edge = hexc('#16120E')
    t = clamp01(r) ** 1.4
    col = mix(mid, edge, t[..., None])
    mott = value_noise(rng, 28, 3)
    fib = fiber_noise(rng, 5.0, rng.uniform(-0.4, 0.4))
    col = col * (1.0 + 0.07 * mott + 0.025 * fib)[..., None]
    # faint warm wash, like a stained scroll
    wash = clamp01(value_noise(rng, 60, 2) * 0.8 + 0.2)
    col = mix(col, col * np.array([1.08, 1.0, 0.9], np.float32), (wash * 0.4)[..., None])
    cv.rgb[:] = col


def finish(cv, rng):
    """Paper grain, vignette and a gentle colour grade over the whole image."""
    X, Y = grid()
    grain = value_noise(rng, 1.4, 2) * 0.025 + fiber_noise(rng, 3.0, 0.15) * 0.012
    cv.rgb *= (1.0 + grain)[..., None]
    r = np.sqrt(((X - 96) / 128.0) ** 2 + ((Y - 112) / 150.0) ** 2)
    vig = 1.0 - 0.38 * smoothstep(0.55, 1.25, r)
    cv.rgb *= vig[..., None]
    # mute: pull saturation down a little toward warm grey
    g = cv.rgb.mean(axis=2, keepdims=True)
    cv.rgb = mix(cv.rgb, g * np.array([1.04, 0.99, 0.9], np.float32), 0.12)


# ----------------------------------------------------------------------
# Body geometry
# ----------------------------------------------------------------------

class Body:
    def __init__(self, head, bp):
        hu = head.hu
        self.hu = hu
        self.head = head
        self.nbx = head.xc + bp.get('nb_dx', -0.02) * hu
        self.nby = head.ye + 1.3 * hu
        self.sw = bp.get('shoulder', 1.0)       # shoulder breadth factor
        self.slope = bp.get('slope', 1.0)
        nbx, nby, sw = self.nbx, self.nby, self.sw
        # neck
        (etx, ety), (ebx, eby) = ear_anchor(head)
        chin_x = head.midline_x(0.95)
        nw = bp.get('neck_w', 1.0)
        self.neck_l_top = (ebx - 0.1 * hu, eby - 0.1 * hu)
        self.neck_r_top = (chin_x - 0.32 * hu * nw, head.ye + 0.85 * hu)
        self.neck_l = (nbx - 0.5 * hu * nw, nby - 0.1 * hu)
        self.neck_r = (nbx + 0.36 * hu * nw, nby - 0.06 * hu)
        # shoulders (near = left, far = right)
        sy = nby + 0.32 * hu * self.slope
        self.sh_l = (nbx - 1.62 * hu * sw, sy + 0.12 * hu)
        self.sh_r = (nbx + 1.42 * hu * sw, sy + 0.05 * hu)

    def torso_poly(self, out=0.0):
        hu = self.hu
        nbx, nby = self.nbx, self.nby
        lx, ly = self.neck_l
        rx, ry = self.neck_r
        slx, sly = self.sh_l
        srx, sry = self.sh_r
        pts_l = catmull([(lx - out, ly - out * 0.5), (lx - 0.35 * hu - out, ly + 0.14 * hu - out),
                         (slx * 0.5 + lx * 0.5 - out, sly * 0.55 + ly * 0.45 - out * 0.6),
                         (slx - out, sly - out * 0.2), (slx - 0.25 * hu - out, sly + 0.45 * hu)], 6)
        pts_r = catmull([(srx + 0.25 * hu + out, sry + 0.45 * hu), (srx + out, sry - out * 0.2),
                         (srx * 0.5 + rx * 0.5 + out, sry * 0.6 + ry * 0.4 - out * 0.6),
                         (rx + 0.3 * hu + out, ry + 0.1 * hu - out), (rx + out, ry - out * 0.5)], 6)
        bottom = [(slx - 0.3 * hu - out, H + 20), (srx + 0.3 * hu + out, H + 20)]
        return pts_l + [bottom[0], bottom[1]] + pts_r

    def neck_poly(self, extra_down=0.0):
        hu = self.hu
        lt, rt = self.neck_l_top, self.neck_r_top
        lb, rb = self.neck_l, self.neck_r
        lb2 = (lb[0] + 0.05 * hu, lb[1] + extra_down)
        rb2 = (rb[0] - 0.05 * hu, rb[1] + extra_down)
        left = catmull([(lt[0], lt[1] - 0.3 * hu), lt, (lb[0] + 0.02 * hu, lb[1] - 0.05 * hu), lb2], 6)
        right = catmull([rb2, (rb[0] - 0.02 * hu, rb[1] - 0.1 * hu), rt, (rt[0] + 0.1 * hu, rt[1] - 0.3 * hu)], 6)
        return left + right


def draw_neck(cv, head, body, fp, rng, extra_down=0.6):
    hu = head.hu
    m = poly(body.neck_poly(extra_down * hu))
    l = pillow(m, 0.25 * hu, 1.0)
    # the neck turns away from light on its front
    X, Y = grid()
    side = clamp01((X - (body.nbx - 0.3 * hu)) / (0.7 * hu))
    v = l * (0.85 - 0.35 * side)
    # jaw cast shadow
    surf_mask = head.surface()['mask']
    sh = np.roll(np.roll(surf_mask, int(0.12 * hu * SCALE), 0), int(0.05 * hu * SCALE), 1)
    sh = blur(sh, 0.06 * hu)
    v = v * (1 - 0.55 * sh)
    deep, shade, base, lite = skin_palette(fp['skin'])
    c = shade_ramp(clamp01(v), deep, shade, base)
    cv.paint(m, c)
    cv.paint(ink_outline(m, 0.6, rng, 0.3), INK, 0.75)
    return m


# ----------------------------------------------------------------------
# Garments
# ----------------------------------------------------------------------

def _cross(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def collar_lines(body, k, spread=1.0):
    """Lines of the k-th layer's crossed collar: (A, C, B, E) points.

    A: top of the under-lapel (viewer's left of the neck), C: crossing point,
    B: top of the over-lapel (viewer's right), E: over-lapel exit at the bottom.
    """
    hu = body.hu
    nbx, nby = body.nbx, body.nby
    A = (nbx - (0.36 + 0.13 * k * spread) * hu, nby - (0.22 - 0.06 * k) * hu)
    B = (nbx + (0.36 + 0.12 * k * spread) * hu, nby - (0.2 - 0.05 * k) * hu)
    C = (nbx + (0.1 - 0.05 * k) * hu, nby + (0.5 + 0.22 * k * spread) * hu)
    dx, dy = C[0] - B[0], C[1] - B[1]
    t = (H + 20 - B[1]) / dy
    E = (B[0] + dx * t * 0.92, H + 20)
    return A, C, B, E


def _band(p_from, p_to, width, side, n=10, curve=0.0):
    """Polygon strip along a (slightly curved) segment, offset to `side` (+1/-1)."""
    pts = []
    for i in range(n + 1):
        t = i / n
        x = p_from[0] + (p_to[0] - p_from[0]) * t
        y = p_from[1] + (p_to[1] - p_from[1]) * t
        dx, dy = p_to[0] - p_from[0], p_to[1] - p_from[1]
        L = math.hypot(dx, dy)
        nx, ny = -dy / L, dx / L
        b = curve * math.sin(math.pi * t)
        pts.append((x + nx * b, y + ny * b))
    pts = np.array(pts)
    d = pts[1:] - pts[:-1]
    d = np.vstack([d, d[-1:]])
    ln = np.sqrt((d ** 2).sum(1))[:, None]
    nrm = np.stack([-d[:, 1], d[:, 0]], 1) / ln
    off = pts + nrm * width * side
    return [tuple(p) for p in pts] + [tuple(p) for p in off[::-1]]


def draw_robe(cv, head, body, dp, rng):
    """Layered cross-collar robe.  dp['layers'] = list of (fill, band) colours, inner first."""
    hu = head.hu
    torso = poly(body.torso_poly())
    layers = dp['layers']
    outer_fill = hexc(layers[-1][0])
    v = body_light(torso, 0.45 * hu)
    # subtle cloth folds: a few long soft streaks
    folds = StrokeLayer()
    for i in range(7):
        x0 = rng.uniform(5, 187)
        y0 = rng.uniform(185, 205)
        pts = catmull([(x0, y0), (x0 + rng.uniform(-6, 6), y0 + 20), (x0 + rng.uniform(-10, 10), 250)], 6)
        folds.add(pts, [0.6, 2.5, 3.5], rng.uniform(0.4, 1.0))
    fl = blur(folds.result(), 1.2)
    v = v * (1 - 0.3 * fl)
    paint_shaded(cv, torso, outer_fill, v, rng, outline=0.8)
    # back collar standing behind the neck
    A0, C0, B0, E0 = collar_lines(body, 0)
    nb = len(layers)
    Ao, Co, Bo, Eo = collar_lines(body, nb - 1, dp.get('spread', 1.0))
    back = catmull([(A0[0] - 0.02 * hu, A0[1] + 0.1 * hu), (A0[0] + 0.05 * hu, A0[1] - 0.12 * hu),
                    ((A0[0] + B0[0]) * 0.5, A0[1] - 0.28 * hu), (B0[0] - 0.05 * hu, B0[1] - 0.12 * hu),
                    (B0[0], B0[1] + 0.1 * hu)], 6)
    bm = clamp01(poly(back + [((A0[0] + B0[0]) * 0.5, A0[1] + 0.3 * hu)]))
    band_col = hexc(layers[-1][1])
    bl = body_light(bm, 0.1 * hu) * 0.7
    paint_shaded(cv, bm, band_col, bl, rng, outline=0.6)
    # neck goes over the back collar
    draw_neck(cv, head, body, dp['face'], rng, extra_down=0.7)
    # front layers, inner first
    for k, (fill, bandc) in enumerate(layers):
        A, C, B, E = collar_lines(body, k, dp.get('spread', 1.0))
        fill = hexc(fill)
        bandc = hexc(bandc)
        bw = dp.get('band_w', [0.1, 0.12, 0.2, 0.2])[min(k, 3)] * hu
        # region covered by this layer = torso minus its V opening
        opening = [A, (A[0] - 0.1 * hu, A[1] - 0.6 * hu), (B[0] + 0.1 * hu, B[1] - 0.6 * hu), B, C]
        under_lap = [(A[0] - 2 * hu, A[1] + 0.2 * hu), A, C, (C[0] - 0.1 * hu, H + 30), (A[0] - 2 * hu, H + 30)]
        over_lap = [B, (B[0] + 3 * hu, B[1] + 0.1 * hu), (B[0] + 3 * hu, H + 30), E]
        # shift the panels with the layer so inner layers peek out
        m_under = poly(under_lap) * torso
        m_over = poly(over_lap) * torso
        lv = body_light(torso, 0.45 * hu)
        if k < len(layers) - 1:
            # inner layers: only the bands are really visible
            paint_shaded(cv, m_under, fill, lv, rng, outline=0.5)
            paint_shaded(cv, m_over, fill, lv, rng, outline=0.0)
        else:
            paint_shaded(cv, m_under, fill, lv * (1 - 0.3 * fl), rng, outline=0.5)
            paint_shaded(cv, m_over, fill, lv * (1 - 0.3 * fl), rng, outline=0.0)
        # collar bands
        b1 = poly(_band(A, C, bw, -1, curve=-0.04 * hu)) * torso
        b2 = poly(_band(B, E, bw, -1, curve=0.08 * hu)) * torso
        bl = body_light(np.maximum(b1, b2), 0.08 * hu)
        paint_shaded(cv, b1, bandc, bl, rng, outline=0.45, ink_a=0.7)
        paint_shaded(cv, b2, bandc, bl, rng, outline=0.5, ink_a=0.8)
        # ink line on the overlapping lapel edge
        edge = stroke(resample([B, E], 12), [0.9] * 12)
        cv.paint(edge * torso, INK, 0.7)
    return torso


# ----------------------------------------------------------------------
# Strand helpers
# ----------------------------------------------------------------------

def sample_points(mask, n, rng, thresh=0.5):
    ys, xs = np.nonzero(mask > thresh)
    if len(xs) == 0:
        return np.zeros((0, 2))
    idx = rng.integers(0, len(xs), n)
    jx = rng.uniform(0, 1, n)
    jy = rng.uniform(0, 1, n)
    return np.stack([(xs[idx] + jx) / SCALE, (ys[idx] + jy) / SCALE], 1)


def flow_strands(mask, n, rng, direction, length=(6, 14), width=(0.35, 0.7), curl=0.15, steps=5,
                 thresh=0.5):
    """Draw n strands inside mask following direction(x, y) -> (dx, dy).

    Returns (light_strands, dark_strands) maps in 0..1.
    """
    lite = StrokeLayer()
    dark = StrokeLayer()
    pts0 = sample_points(mask, n, rng, thresh)
    for (x, y) in pts0:
        L = rng.uniform(*length)
        wv = rng.uniform(*width)
        c = rng.uniform(-curl, curl)
        pts = [(x, y)]
        ang = None
        for s in range(steps):
            dx, dy = direction(x, y)
            a = math.atan2(dy, dx)
            if ang is None:
                ang = a
            else:
                da = (a - ang + math.pi) % (2 * math.pi) - math.pi
                ang = ang + da * 0.6
            ang += c
            x += math.cos(ang) * L / steps
            y += math.sin(ang) * L / steps
            pts.append((x, y))
        wid = [wv * (0.3 + 0.7 * math.sin(math.pi * (i + 0.5) / (len(pts)))) for i in range(len(pts))]
        if rng.uniform() < 0.55:
            lite.add(pts, wid, rng.uniform(0.35, 1.0))
        else:
            dark.add(pts, wid, rng.uniform(0.35, 1.0))
    return lite.result() * mask, dark.result() * mask


def paint_hair_mass(cv, mask, light, colors, strands=None, rng=None, outline=0.7, sheen=None,
                    ink_a=0.85):
    """colors = (dark, mid, lite).  strands = (lite_map, dark_map)."""
    dark, mid, lite = colors
    v = clamp01(light)
    if strands is not None:
        ls, ds = strands
        v = clamp01(v + 0.32 * ls * (0.4 + v) - 0.3 * ds)
    c = shade_ramp(v, dark, mid, lite)
    if sheen is not None:
        c = c + sheen[..., None] * (lite - mid) * 0.8
    cv.paint(mask, c)
    if outline:
        cv.paint(ink_outline(mask, outline, rng, 0.4), INK, ink_a)


def hair_colors(hex_mid, grey=0.0):
    mid = hexc(hex_mid)
    if grey > 0:
        mid = mix(mid, hexc('#B9B4AA'), grey)
    dark = mid * 0.45
    lite = mix(mid, hexc('#C8BCAA'), 0.35 + 0.25 * grey)
    if grey > 0.7:
        dark = mix(hexc('#5D5952'), mid * 0.6, 0.3)
        lite = hexc('#EDEAE2')
    return dark.astype(np.float32), mid.astype(np.float32), lite.astype(np.float32)


# ----------------------------------------------------------------------
# Hair
# ----------------------------------------------------------------------

def hairline_map(u, yu, hp):
    """Return a soft 0..1 map of 'is above the hairline' for face pixels."""
    au = np.abs(u)
    h0 = hp.get('hairline', -0.62)
    rc = hp.get('recede', 0.0)
    sb = hp.get('sideburn', 0.1)
    xs = [0.0, 0.3, 0.55, 0.75, 0.88, 0.94, 1.0]
    ys = [h0, h0 + 0.02 + 0.06 * rc, h0 + 0.1 + 0.16 * rc, h0 + 0.2 + 0.08 * rc, -0.22, sb, sb]
    hl = np.interp(au, xs, ys)
    soft = hp.get('soft', 0.03)
    return 1.0 - smoothstep(hl - soft, hl + soft * 0.5, yu)


def hair_region(head, hp, grow):
    surf = head.surface(grow=grow)
    u, yu, face = surf['u'], surf['yu'], surf['face']
    above = hairline_map(u, yu, hp)
    nape = 1.0 - smoothstep(hp.get('nape', 0.5) - 0.03, hp.get('nape', 0.5) + 0.03, yu)
    reg = np.where(face, above, nape)
    return surf, clamp01(reg * surf['mask'])


def surface_light(surf, wrap=0.4):
    z = surf['z']
    inside = surf['inside']
    idx = ndi.distance_transform_edt(~inside, return_indices=True)[1]
    z = z[idx[0], idx[1]]
    nx, ny, nz = normals_from_height(z)
    return lambert(nx, ny, nz, wrap=wrap), (nx, ny, nz)


def topknot_point(head, hp):
    hu = head.hu
    x, y, _ = head.local_to_screen(0.0, hp.get('knot_y', -0.98), hp.get('knot_z', -0.42) * hu)
    return x, y


def draw_hair_cap(cv, head, hp, rng, colors, flow_to=None):
    """Hair hugging the skull (combed back to a knot or loose)."""
    hu = head.hu
    g = hp.get('thick', 2.5)
    surf, m = hair_region(head, hp, g)
    light, _ = surface_light(surf, 0.35)
    if flow_to is None:
        flow_to = topknot_point(head, hp)
    kx, ky = flow_to

    def direction(x, y):
        return kx - x, ky - y
    n = int(m.sum() / (SCALE * SCALE) / 6) + 80
    st = flow_strands(m, n, rng, direction, length=(8, 18), width=(0.3, 0.65), curl=0.04)
    # sheen band (anisotropic highlight) across the lit part of the skull
    X, Y = grid()
    sheen = np.exp(-(((X - head.xc + 0.15 * hu) * 0.6 + (Y - head.ye + 0.72 * hu)) / (0.12 * hu)) ** 2) * light
    sheen *= clamp01(0.5 + st[0] - st[1] * 0.5)
    paint_hair_mass(cv, m, light * 0.95, colors, st, rng, outline=0.7, sheen=sheen * 0.6)
    return m, surf


def draw_bun(cv, head, cx, cy, rx, ry, colors, rng, ang=0.0, outline=0.7):
    m = ellipse(cx, cy, rx, ry, ang)
    l = pillow(m, min(rx, ry) * 0.9, 1.2)

    def direction(x, y):
        # circular flow around the bun centre
        return -(y - cy), (x - cx)
    st = flow_strands(m, int(rx * ry * 0.5) + 30, rng, direction, length=(5, 11), width=(0.3, 0.6), curl=0.05)
    paint_hair_mass(cv, m, l, colors, st, rng, outline=outline)
    return m


def draw_loose_back(cv, head, body, hp, rng, colors, length=1.0, spread=1.0):
    """Long hair falling behind the head and shoulders (drawn before the body)."""
    hu = head.hu
    (tx, ty), (bx, by) = ear_anchor(head)
    top = head.ye - 0.9 * hu
    left = tx - 0.55 * hu * spread
    right = head.midline_x(0.0) + 0.55 * hu
    bot = head.ye + (1.3 + 1.2 * length) * hu
    pts = [(head.xc - 0.1 * hu, top), (left + 0.1 * hu, head.ye - 0.4 * hu), (left - 0.1 * hu * spread, head.ye + 0.5 * hu),
           (left - 0.15 * hu * spread, bot - 0.3 * hu), (left + 0.15 * hu, bot), (bx + 0.25 * hu, bot - 0.2 * hu),
           (body.nbx + 0.1 * hu, body.nby), (right, head.ye + 0.6 * hu), (right, head.ye - 0.3 * hu)]
    outline = catmull(pts, 8, closed=True)
    # ragged bottom edge
    m = poly(outline)
    l = pillow(m, 0.35 * hu, 0.8) * 0.75

    def direction(x, y):
        return (x - head.xc) * 0.08, 1.0
    st = flow_strands(m, 500, rng, direction, length=(14, 30), width=(0.3, 0.8), curl=0.03)
    paint_hair_mass(cv, m, l, colors, st, rng, outline=0.7)
    return m


# ----------------------------------------------------------------------
# Facial hair
# ----------------------------------------------------------------------

def draw_moustache(cv, head, fp, rng, colors, style='thin'):
    hu = head.hu
    nt, my, mu = fp['nose_y'], fp['mouth_y'], fp['mouth_u']
    lp = 0.045 * hu
    lay = StrokeLayer()
    mass = StrokeLayer()
    thick = {'thin': 0.045, 'full': 0.08, 'droop': 0.06}[style]
    droop = {'thin': 0.12, 'full': 0.08, 'droop': 0.3}[style]
    for sgn in (-1, 1):
        pts_uv = [(sgn * 0.02, nt + 0.1), (sgn * mu * 0.55, nt + 0.12), (sgn * (mu + 0.04), my - 0.02),
                  (sgn * (mu + 0.1), my + droop)]
        P = [head.pt(u, y, lp * (1 - abs(u))) for u, y in pts_uv]
        P = catmull(P, 6)
        n = len(P)
        wid = [thick * hu * (1.0 - 0.85 * (i / (n - 1)) ** 1.2) for i in range(n)]
        mass.add(P, wid, 1.0)
        for k in range(int(30 + thick * 400)):
            t = rng.uniform(0.0, 0.85)
            i = int(t * (n - 1))
            x, y = P[i]
            dx, dy = P[min(n - 1, i + 2)][0] - x, P[min(n - 1, i + 2)][1] - y
            L = math.hypot(dx, dy) + 1e-6
            off = rng.uniform(-0.5, 0.5) * wid[i]
            sx, sy = x - dy / L * off, y + dx / L * off
            ln = rng.uniform(2.5, 6)
            lay.add([(sx, sy), (sx + dx / L * ln * 0.5, sy + dy / L * ln * 0.5 + 0.3), (sx + dx / L * ln, sy + dy / L * ln + 0.8)],
                    [0.4, 0.35, 0.1], rng.uniform(0.3, 1))
    m = clamp01(blur(mass.result(), 0.3))
    h = lay.result()
    a = clamp01(m * 0.75 + h * 0.6) * clamp01(blur(m, 0.6) * 2)
    dark, mid, lite = colors
    v = clamp01(0.45 + 0.4 * h - 0.2 * m)
    c = shade_ramp(v, dark, mid, lite)
    cv.paint(a, c)
    return a


def beard_mass(head, fp, style, length):
    """Screen-space polygon for the part of the beard hanging below the jaw."""
    hu = head.hu
    (tx, ty), (bx, by) = ear_anchor(head)
    chin = head.pt(0.0, 0.98)
    far = head.pt(0.75, 0.62)
    L = length * hu
    if style == 'goatee':
        cx = chin[0] - 0.02 * hu
        return [head.pt(-0.2, fp['mouth_y'] + 0.16), head.pt(0.2, fp['mouth_y'] + 0.16),
                (cx + 0.14 * hu, chin[1] + 0.1 * L), (cx + 0.02 * hu, chin[1] + L), (cx - 0.12 * hu, chin[1] + 0.15 * L)]
    if style == 'long':
        cx = chin[0] - 0.08 * hu
        return catmull([(bx + 0.05 * hu, by - 0.15 * hu), (bx + 0.1 * hu, by + 0.25 * hu),
                        (cx - 0.35 * hu, chin[1] + 0.4 * L), (cx - 0.15 * hu, chin[1] + L),
                        (cx + 0.05 * hu, chin[1] + 0.92 * L), (cx + 0.3 * hu, chin[1] + 0.45 * L),
                        (far[0], far[1] + 0.25 * hu), (far[0] + 0.02 * hu, far[1] - 0.05 * hu)], 8)
    # full
    cx = chin[0] - 0.05 * hu
    return catmull([(bx + 0.02 * hu, by - 0.2 * hu), (bx + 0.08 * hu, by + 0.2 * hu),
                    (cx - 0.35 * hu, chin[1] + 0.55 * L), (cx, chin[1] + L),
                    (cx + 0.3 * hu, chin[1] + 0.5 * L), (far[0] + 0.02 * hu, far[1] + 0.25 * hu),
                    (far[0] + 0.04 * hu, far[1] - 0.05 * hu)], 8)


def draw_beard(cv, head, fp, surf, rng, colors, style='full', length=0.5):
    from portrait_face import beard_region
    hu = head.hu
    my, mu = fp['mouth_y'], fp['mouth_u']
    if style == 'goatee':
        face_part = np.zeros((HH, WW), np.float32)
    else:
        face_part = beard_region(head, fp, surf, top_off=0.08 if style == 'full' else 0.04) * surf['fmask']
    below = poly(beard_mass(head, fp, style, length))
    m = np.maximum(face_part, below)
    # keep the lower lip clear
    mx, myy = head.pt(0, my + 0.04, 0.03 * hu)
    lip = ellipse(mx - 0.01 * hu, myy, mu * hu * 0.75, 0.09 * hu)
    m = m * (1 - lip)
    m = clamp01(m)
    # ragged edges: erode by noise
    nz = value_noise(rng, 2.5, 2)
    m = clamp01(m * (1 + 0.6 * nz * (1 - smoothstep(0.0, 1.5, edge_distance(m)))))
    light = pillow(m, 0.25 * hu, 0.9)

    mx9 = head.midline_x(0.9)

    def direction(x, y):
        return (x - mx9) * 0.15, 1.0
    st = flow_strands(m, int(m.sum() / (SCALE * SCALE) / 3) + 60, rng, direction,
                      length=(6, 16), width=(0.3, 0.7), curl=0.06, thresh=0.3)
    paint_hair_mass(cv, m, light * 0.9, colors, st, rng, outline=0.55, ink_a=0.6)
    return m
