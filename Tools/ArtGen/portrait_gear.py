"""Armour, headgear and accessories for the procedural portraits."""
import math

import numpy as np

from portrait_raster import (W, H, HH, WW, SCALE, LIGHT, grid, clamp01, smoothstep, blur, mix,
                             poly, polys, ellipse, stroke, strokes, catmull, resample,
                             StrokeLayer, value_noise, normals_from_height, lambert, ink_outline,
                             edge_distance, pillow, hexc, shade_ramp)
from portrait_face import INK, ear_anchor
from portrait_dress import (paint_shaded, body_light, tone, flow_strands, paint_hair_mass,
                            surface_light, hairline_map, topknot_point, draw_bun, _band)

METALS = {
    'iron': ('#121417', '#43484C', '#9A9C98'),
    'steel': ('#181B1F', '#596066', '#B8BBB5'),
    'bronze': ('#2E2214', '#7A5C34', '#D2B27A'),
    'black': ('#121214', '#36353A', '#8A8A8E'),
    'redlac': ('#2A0E0A', '#7A2A20', '#C47A62'),
    'leather': ('#24170E', '#6A4A2E', '#B8946A'),
    'gold': ('#3A2A10', '#9A7838', '#E8CF8A'),
}


def metal_cols(name):
    d, m, l = METALS[name]
    return hexc(d), hexc(m), hexc(l)


def paint_metal(cv, mask, light, metal, rng, outline=0.7, spec=0.6, ink_a=0.85):
    dark, mid, lite = metal_cols(metal)
    v = clamp01(light + 0.04 * value_noise(rng, 3.0, 2))
    c = shade_ramp(v, dark, mid, lite)
    # specular sparkle on the brightest parts
    sp = smoothstep(0.72, 0.95, v) * spec
    c = c + sp[..., None] * (np.array([1, 0.97, 0.9], np.float32) - c) * 0.6
    cv.paint(mask, c)
    if outline:
        cv.paint(ink_outline(mask, outline, rng, 0.3), INK, ink_a)


# ----------------------------------------------------------------------
# Armour
# ----------------------------------------------------------------------

def lamellar_pattern(body, pw, ph, slope=0.3):
    """Per-pixel plate shading (0..1), gap mask and lacing mask for lamellar rows."""
    X, Y = grid()
    hu = body.hu
    cxb = body.nbx - 0.1 * hu
    Rb = 2.1 * hu
    s = np.clip((X - cxb) / Rb, -0.98, 0.98)
    uu = np.arcsin(s) * Rb
    side = np.maximum(np.abs(X - body.nbx) - 0.35 * hu, 0)
    vv = Y - body.nby - slope * side
    row = np.floor(vv / ph)
    fy = vv / ph - row
    shift = 0.5 * (np.mod(row, 2))
    cu = uu / pw + shift
    col = np.floor(cu)
    fx = cu - col
    # foreshortening -> thinner gaps near the edges
    plate = 0.62 + 0.38 * (1 - (2 * fx - 1) ** 2) ** 0.5
    plate = plate * (1.0 - 0.45 * smoothstep(0.62, 1.0, fy)) + 0.35 * (1 - smoothstep(0.0, 0.18, fy))
    gap = np.maximum(1 - smoothstep(0.0, 0.07, fx), smoothstep(0.93, 1.0, fx))
    gap = np.maximum(gap * (fy > 0.1), smoothstep(0.9, 1.0, fy))
    lace = ((fy > 0.22) & (fy < 0.34)).astype(np.float32) * np.maximum(1 - smoothstep(0.0, 0.2, fx), smoothstep(0.8, 1.0, fx))
    rivet = clamp01(1 - (((fx - 0.5) / 0.12) ** 2 + ((fy - 0.55) / 0.1) ** 2))
    return plate.astype(np.float32), gap.astype(np.float32), lace.astype(np.float32), rivet.astype(np.float32)


def draw_armour(cv, head, body, ap, rng):
    """Lamellar cuirass with shoulder guards over whatever robe is already drawn."""
    hu = head.hu
    metal = ap['metal']
    trim = ap.get('trim', 'gold')
    cord = hexc(ap.get('cord', '#8A2A1E'))
    torso = poly(body.torso_poly(out=0.05 * hu))
    nbx, nby = body.nbx, body.nby
    (lx, ly), (rx, ry) = body.neck_l, body.neck_r
    depth = ap.get('open_depth', 0.62)
    open_pts = catmull([(lx - 0.5 * hu, ly - 0.6 * hu), (lx - 0.38 * hu, ly + 0.08 * hu),
                        (nbx - 0.02 * hu, nby + depth * hu),
                        (rx + 0.32 * hu, ry + 0.05 * hu), (rx + 0.45 * hu, ry - 0.6 * hu)], 8)
    opening = poly(open_pts)
    arm = clamp01(torso - opening)
    gl = body_light(arm, 0.5 * hu)
    plate, gap, lace, rivet = lamellar_pattern(body, ap.get('pw', 0.095) * hu, ap.get('ph', 0.13) * hu)
    v = gl * (0.55 + 0.6 * plate) * (1 - 0.55 * gap)
    paint_metal(cv, arm, v, metal, rng, outline=0.8)
    cv.paint(lace * arm * (1 - gap), cord * (0.5 + 0.6 * gl[..., None]), 0.85)
    if ap.get('rivets', False):
        cv.paint(rivet * arm, hexc('#E2C98A') * (0.4 + 0.7 * gl[..., None]), 0.8)
    # gorget band around the opening
    edge_pts = resample(catmull([(lx - 0.38 * hu, ly + 0.08 * hu), (nbx - 0.02 * hu, nby + depth * hu),
                                 (rx + 0.32 * hu, ry + 0.05 * hu)], 10), 30)
    bw = ap.get('gorget_w', 0.12) * hu
    band_m = stroke(edge_pts, [bw * 2] * 30) * torso * (1 - clamp01(opening - 0.0) * 0.0)
    band_m = band_m * clamp01(1 - edge_distance(1 - opening + 0) * 0)  # keep simple
    tl = pillow(band_m, bw * 0.6, 1.0) * gl.clip(0.4, 1)
    if ap.get('gorget', 'trim') == 'cloth':
        paint_shaded(cv, band_m, hexc(ap.get('cloth', '#7A2A20')), tl, rng, outline=0.6)
    else:
        paint_metal(cv, band_m, tl, trim, rng, outline=0.6)
    # chest mirror
    if ap.get('mirror', False):
        mx, my = nbx + 0.15 * hu, nby + 1.05 * hu
        mm = ellipse(mx, my, 0.36 * hu, 0.4 * hu) * torso
        ml = pillow(mm, 0.25 * hu, 0.6)
        paint_metal(cv, mm, ml * 0.95, trim if trim != 'gold' else 'bronze', rng, outline=0.7)
        ring = clamp01(ellipse(mx, my, 0.3 * hu, 0.34 * hu) - ellipse(mx, my, 0.26 * hu, 0.3 * hu)) * torso
        cv.paint(ring, hexc('#2A2018'), 0.5)
    # shoulder guards
    for side in (-1, 1):
        draw_pauldron(cv, head, body, ap, side, rng)
    return arm


def draw_pauldron(cv, head, body, ap, side, rng):
    hu = head.hu
    metal = ap.get('shoulder_metal', ap['metal'])
    trim = ap.get('trim', 'gold')
    n = ap.get('lames', 3)
    sc = body.shoulder_curve(side, out=0.08 * hu, n=10)
    # use the outer 60% of the shoulder curve
    k0 = int(len(sc) * (0.2 if side < 0 else 0.26))
    top = sc[k0:]
    lame_h = 0.27 * hu
    for i in range(n):
        dy0 = i * lame_h * 0.82
        dy1 = dy0 + lame_h
        flare = 0.06 * hu * i
        up = [(x - side * 0 - (flare if side < 0 else -flare) * t, y + dy0 + 0.04 * hu * t)
              for t, (x, y) in zip(np.linspace(0, 1, len(top)), top)]
        lo = [(x - (flare if side < 0 else -flare) * t, y + dy1 + 0.06 * hu * t)
              for t, (x, y) in zip(np.linspace(0, 1, len(top)), top)]
        # round the inner end
        inner = (top[0][0] + side * 0.05 * hu, top[0][1] + (dy0 + dy1) * 0.5)
        m = poly(up + lo[::-1] + [inner])
        l = pillow(m, 0.09 * hu, 1.3)
        _, Y = grid()
        l = l * (1 - 0.35 * smoothstep(top[0][1] + dy0, top[0][1] + dy1 + 0.1 * hu, Y))
        paint_metal(cv, m, l, metal, rng, outline=0.6)
        # trim along the lower edge
        tm = stroke(lo, [0.07 * hu] * len(lo)) * m
        paint_metal(cv, tm, l * 1.1, trim, rng, outline=0.0, spec=0.8)


# ----------------------------------------------------------------------
# Headgear
# ----------------------------------------------------------------------

def cap_region(head, grow, brim_front, brim_side, back=0.25, soft=0.02):
    """Region of an inflated head above a brim line (front height brim_front at u=0,
    brim_side at the ears, `back` at the back of the skull)."""
    surf = head.surface(grow=grow)
    u, yu, face = surf['u'], surf['yu'], surf['face']
    au = np.abs(u)
    br = brim_front + (brim_side - brim_front) * smoothstep(0.2, 1.0, au) ** 1.5
    m_face = 1 - smoothstep(br - soft, br + soft, yu)
    m_back = 1 - smoothstep(back - soft, back + soft, yu)
    m = np.where(face, m_face, m_back) * surf['mask']
    return surf, clamp01(m).astype(np.float32), br


def brim_curve(head, grow, brim_front, brim_side, u0=-1.0, u1=0.97, n=24):
    pts = []
    for i in range(n + 1):
        u = u0 + (u1 - u0) * i / n
        au = abs(u)
        br = brim_front + (brim_side - brim_front) * smoothstep(0.2, 1.0, au) ** 1.5
        pts.append(head.pt(u, br, grow))
    return pts


def draw_helmet(cv, head, hp, rng):
    hu = head.hu
    metal = hp['metal']
    trim = hp.get('trim', 'gold')
    grow = 0.13 * hu
    bf, bs = hp.get('brim', -0.5), hp.get('brim_side', -0.12)
    # neck/ear flaps first (behind the dome edge)
    if hp.get('flaps', True):
        draw_helmet_flaps(cv, head, hp, rng, grow, bs)
    surf, m, _ = cap_region(head, grow, bf, bs, back=0.12)
    light, _ = surface_light(surf, 0.3)
    # vertical ribs (segmented helmet)
    phi = surf['phi']
    nr = hp.get('ribs', 0)
    if nr:
        rib = 0.5 + 0.5 * np.cos(phi * nr)
        v = light * (0.88 + 0.12 * rib) * 0.92
    else:
        v = light * 0.92
    paint_metal(cv, m, v, metal, rng, outline=0.8)
    if nr:
        rl = smoothstep(0.94, 1.0, rib) * m
        cv.paint(rl, hexc(METALS[metal][0]), 0.5)
    # brim band
    bc = brim_curve(head, grow + 0.3, bf, bs)
    bm = clamp01(stroke(bc, [0.13 * hu] * len(bc)) * clamp01(m * 3 + 0.0))
    bm = np.maximum(bm, stroke(bc, [0.13 * hu] * len(bc)) * (surf['mask'] > 0.5))
    bl = surface_light(surf, 0.3)[0]
    paint_metal(cv, bm, bl * 1.05, trim, rng, outline=0.6, spec=0.9)
    # forehead plate / ornament
    if hp.get('crest', True):
        cx, cy = head.pt(0.0, bf - 0.03, grow + 1)
        pts = [(cx - 0.11 * hu, cy + 0.02 * hu), (cx - 0.13 * hu, cy - 0.12 * hu), (cx - 0.05 * hu, cy - 0.2 * hu),
               (cx + 0.01 * hu, cy - 0.32 * hu), (cx + 0.07 * hu, cy - 0.2 * hu), (cx + 0.12 * hu, cy - 0.12 * hu),
               (cx + 0.09 * hu, cy + 0.02 * hu)]
        cm = poly(catmull(pts, 4, closed=True))
        paint_metal(cv, cm, pillow(cm, 0.06 * hu, 1.2), trim, rng, outline=0.55, spec=0.9)
    # finial + plume
    tx, ty, _ = head.local_to_screen(0.0, -1.0 - grow / hu - 0.02, -0.12 * hu)
    plume = hp.get('plume', 'tassel')
    if plume == 'tassel':
        draw_tassel(cv, tx, ty - 0.12 * hu, hu, hexc(hp.get('plume_col', '#9A2A1E')), rng)
    elif plume == 'feathers':
        draw_feathers(cv, tx, ty, hu, rng)
    fm = ellipse(tx, ty - 0.06 * hu, 0.06 * hu, 0.12 * hu)
    paint_metal(cv, fm, pillow(fm, 0.05 * hu, 1.2), trim, rng, outline=0.5)
    km = ellipse(tx, ty + 0.02 * hu, 0.12 * hu, 0.05 * hu)
    paint_metal(cv, km, pillow(km, 0.04 * hu, 1.2), trim, rng, outline=0.5)


def draw_helmet_flaps(cv, head, hp, rng, grow, bs):
    hu = head.hu
    (tx, ty), (bx, by) = ear_anchor(head)
    style = hp.get('flap_style', 'lamellar')
    top_front = head.pt(-0.78, bs - 0.05, grow)
    sk_back = head.local_to_screen(-0.3 * hu, -0.1, -1.05 * hu)
    pts = [top_front, (top_front[0] - 0.03 * hu, (top_front[1] + by) * 0.5),
           (bx + 0.1 * hu, by + 0.3 * hu), (bx - 0.05 * hu, by + 0.52 * hu),
           (bx - 0.45 * hu, by + 0.6 * hu), (min(sk_back[0], tx - 0.4 * hu) - 0.1 * hu, by + 0.35 * hu),
           (min(sk_back[0], tx - 0.4 * hu) - 0.02 * hu, ty - 0.1 * hu), (tx - 0.2 * hu, ty - 0.3 * hu)]
    m = poly(catmull(pts, 6, closed=True))
    l = pillow(m, 0.18 * hu, 1.0) * 0.7
    X, Y = grid()
    if style == 'lamellar':
        ph = 0.13 * hu
        fy = np.mod((Y - ty) / ph, 1.0)
        fx = np.mod((X - tx + 0.5 * ph * (np.floor((Y - ty) / ph) % 2)) / (0.09 * hu), 1.0)
        pat = (1 - 0.45 * smoothstep(0.65, 1.0, fy)) * (1 - 0.4 * np.maximum(1 - smoothstep(0, 0.1, fx), smoothstep(0.9, 1, fx)))
        paint_metal(cv, m, l * pat, hp.get('flap_metal', hp['metal']), rng, outline=0.7)
    else:
        # quilted cloth with studs
        col = hexc(hp.get('flap_col', '#5A2A20'))
        qy = np.mod((Y - ty) / (0.16 * hu), 1.0)
        pat = 1 - 0.3 * smoothstep(0.8, 1.0, qy)
        paint_shaded(cv, m, col, l * pat, rng, outline=0.7)
        st = clamp01(1 - ((np.mod((X - tx) / (0.14 * hu), 1) - 0.5) ** 2 + (qy - 0.4) ** 2) / 0.02) * m
        cv.paint(st, hexc('#D8BE7A') * (0.5 + 0.6 * l[..., None]), 0.8)


def draw_tassel(cv, x, y, hu, col, rng):
    """Red horsehair tassel spraying from the helmet top, falling back."""
    lay_l = StrokeLayer()
    mass = StrokeLayer()
    for i in range(220):
        a = rng.uniform(-2.6, -0.2)  # angles (screen, up = -pi/2)
        L = rng.uniform(0.25, 0.55) * hu
        pts = []
        for k in range(6):
            t = k / 5
            ang = a + (t ** 1.5) * (1.6 if a < -1.4 else 0.9) * (-1 if a < -1.4 else 1) * -1
            px = x + math.cos(a) * L * t * 0.8 - 0.25 * hu * t * t
            py = y + math.sin(a) * L * t * 0.7 + 0.35 * hu * t * t
            pts.append((px, py))
        w = rng.uniform(0.5, 1.1)
        mass.add(pts, [w * 2.2, w * 2.4, w * 2, w * 1.5, w, 0.3], 1.0)
        lay_l.add(pts, [w * 0.6, w * 0.6, w * 0.5, w * 0.4, w * 0.3, 0.1], rng.uniform(0.2, 1.0))
    m = clamp01(blur(mass.result(), 0.4) * 1.3)
    st = lay_l.result()
    X, Y = grid()
    l = clamp01(0.75 - (Y - y) / (0.9 * hu) * 0.6 + 0.0 * X)
    v = clamp01(l * 0.7 + 0.4 * st - 0.1)
    c = shade_ramp(v, col * 0.35, col, mix(col, hexc('#F0C0A0'), 0.4))
    cv.paint(m, c)
    cv.paint(ink_outline(m, 0.45, rng, 0.4), INK, 0.6)


def draw_feathers(cv, x, y, hu, rng):
    """Two long pheasant tail feathers arcing back over the head."""
    for k, (dx, ln, bend) in enumerate(((-0.05, 2.1, 1.0), (0.06, 1.9, 0.8))):
        pts = []
        for i in range(21):
            t = i / 20
            px = x + dx * hu - (0.15 + 1.6 * t * bend) * hu * t * 0.9 + 0.25 * hu * math.sin(t * 2.2)
            py = y - 0.1 * hu - ln * hu * t * 0.85 + 1.4 * hu * t * t * bend
            pts.append((px, py))
        wid = [0.12 * hu * (0.5 + 0.5 * math.sin(math.pi * min(1, t * 1.1 + 0.05))) for t in np.linspace(0, 1, 21)]
        m = stroke(pts, wid)
        # banded feather pattern
        X, Y = grid()
        dist = np.zeros_like(X)
        band = 0.5 + 0.5 * np.sin((X * 0.6 + Y * 1.0) / (0.05 * hu))
        l = pillow(m, 0.04 * hu, 1.0)
        v = clamp01(l * (0.55 + 0.45 * band))
        c = shade_ramp(v, hexc('#2A1E14'), hexc('#7A5A34'), hexc('#E8D8B0'))
        cv.paint(m, c)
        cv.paint(stroke(pts, [0.5] * 21), hexc('#2A1E14'), 0.5)
        cv.paint(ink_outline(m, 0.4, rng, 0.3), INK, 0.6)


def draw_headband(cv, head, hp, rng):
    hu = head.hu
    col = hexc(hp['band_col'])
    y0 = hp.get('band_y', -0.5)
    th = hp.get('band_h', 0.11)
    g = hp.get('grow', 0.06 * hu)
    surf = head.surface(grow=g)
    u, yu, face = surf['u'], surf['yu'], surf['face']
    au = np.abs(u)
    yb = y0 + 0.12 * smoothstep(0.3, 1.0, au)
    yb = np.where(face, yb, y0 + 0.12 + 0.02)
    m = (smoothstep(yb - 0.012, yb + 0.008, yu) * (1 - smoothstep(yb + th - 0.008, yb + th + 0.012, yu))) * surf['mask']
    light, _ = surface_light(surf, 0.35)
    # cloth wrinkles
    X, Y = grid()
    wr = 0.5 + 0.5 * np.sin((X * 0.9 + Y * 0.3) / (0.045 * hu) + value_noise(rng, 6, 1) * 2)
    v = light * (0.8 + 0.2 * wr)
    paint_shaded(cv, m, col, v, rng, outline=0.55)
    if hp.get('band_jewel', False):
        cx, cy = head.pt(0, y0 + th * 0.5, g + 1)
        jm = ellipse(cx, cy, 0.07 * hu, 0.06 * hu)
        paint_metal(cv, jm, pillow(jm, 0.05 * hu, 1.2), 'gold', rng, outline=0.4)
        jm2 = ellipse(cx, cy, 0.04 * hu, 0.035 * hu)
        cv.paint(jm2, hexc(hp.get('jewel_col', '#3F6E5A')), 0.9)
    # knot and tails at the back
    if hp.get('tails', True):
        kx, ky = head.pt(-0.995, y0 + 0.12 + th * 0.5, g)
        kx -= 0.08 * hu
        for i, (ang, ln) in enumerate(((2.3, 0.9), (2.0, 1.1))):
            pts = []
            for k in range(9):
                t = k / 8
                px = kx - 0.3 * hu * t * ln - 0.05 * hu * math.sin(t * 5 + i)
                py = ky + 0.95 * hu * t * ln + 0.03 * hu * i
                pts.append((px, py))
            wid = [th * hu * (0.9 - 0.3 * t) for t in np.linspace(0, 1, 9)]
            tm = stroke(pts, wid)
            paint_shaded(cv, tm, col, pillow(tm, 0.04 * hu, 1.0) * 0.85, rng, outline=0.5)
        km = ellipse(kx, ky, 0.08 * hu, 0.07 * hu)
        paint_shaded(cv, km, col, pillow(km, 0.05 * hu, 1.0), rng, outline=0.5)
    return m


# ----------------------------------------------------------------------
# Scholar / civilian headgear
# ----------------------------------------------------------------------

def draw_pin(cv, x0, y0, x1, y1, hu, rng, metal='gold', head_r=0.045, jewel=None):
    pts = resample([(x0, y0), (x1, y1)], 8)
    m = stroke(pts, [0.035 * hu] * 8)
    paint_metal(cv, m, pillow(m, 0.02 * hu, 1.0) * 0.9 + 0.1, metal, rng, outline=0.35, ink_a=0.6)
    for (x, y) in ((x0, y0),):
        hm = ellipse(x, y, head_r * hu, head_r * hu)
        paint_metal(cv, hm, pillow(hm, head_r * hu * 0.8, 1.2), metal, rng, outline=0.35)
        if jewel is not None:
            cv.paint(ellipse(x, y, head_r * hu * 0.55, head_r * hu * 0.55), hexc(jewel), 0.9)


def draw_guan(cv, head, p, rng):
    """Small crown (xiao guan) capping the topknot, held by a hairpin."""
    hu = head.hu
    kx, ky = topknot_point(head, p)
    col = p.get('guan_col', 'black')
    w0 = 0.25 * hu
    h0 = 0.36 * hu
    tilt = -0.15
    ca, sa = math.cos(tilt), math.sin(tilt)

    def rot(x, y):
        return (kx + x * ca - y * sa, ky + 0.06 * hu + x * sa + y * ca)
    pts = [rot(-w0, 0.08 * hu), rot(-w0 * 0.95, -h0 * 0.55), rot(-w0 * 0.55, -h0 * 0.95), rot(0, -h0),
           rot(w0 * 0.6, -h0 * 0.9), rot(w0 * 0.95, -h0 * 0.5), rot(w0, 0.08 * hu)]
    m = poly(catmull(pts, 6) + [rot(0, 0.14 * hu)])
    l = pillow(m, 0.12 * hu, 1.1)
    if col == 'black':
        c = (hexc('#0E0D0C'), hexc('#2C2A28'), hexc('#77736C'))
        v = clamp01(l)
        cv.paint(m, shade_ramp(v, *c))
        cv.paint(ink_outline(m, 0.6, rng, 0.3), INK, 0.9)
        # gauze ridges
        X, Y = grid()
        rid = smoothstep(0.75, 1.0, 0.5 + 0.5 * np.sin((X - kx) * 1.2 + (Y - ky) * 0.35)) * m * (Y < ky)
        cv.paint(rid, hexc('#4A4642'), 0.35)
    else:
        paint_metal(cv, m, l, col, rng, outline=0.6)
    # band at the base
    bpts = [rot(-w0 * 1.02, 0.0), rot(0, 0.05 * hu), rot(w0 * 1.02, 0.0)]
    bm = stroke(catmull(bpts, 6), [0.08 * hu] * 13) * 1.0
    paint_metal(cv, bm, pillow(bm, 0.04 * hu, 1.0), p.get('guan_trim', 'gold'), rng, outline=0.4)
    # hairpin through the crown
    a = rot(-w0 * 1.9, -h0 * 0.35)
    b = rot(w0 * 1.6, -h0 * 0.45)
    draw_pin(cv, a[0], a[1], b[0], b[1], hu, rng, p.get('pin_metal', 'gold'), jewel=p.get('pin_jewel'))


def draw_cloth_cap(cv, head, p, rng):
    """Soft scholar's cap (lun jin) / headscarf with ties at the back."""
    hu = head.hu
    col = hexc(p['cap_col'])
    g = 0.09 * hu
    surf = head.surface(grow=g)
    u, yu, face = surf['u'], surf['yu'], surf['face']
    au = np.abs(u)
    edge = p.get('cap_edge', -0.5)
    yb = edge + 0.2 * smoothstep(0.35, 1.0, au)
    yb = np.where(face, yb, edge + 0.32)
    m = (1 - smoothstep(yb - 0.015, yb + 0.015, yu)) * surf['mask']
    # peaked top/back (the knot inside)
    kx, ky = topknot_point(head, p)
    peak = ellipse(kx - 0.02 * hu, ky + 0.04 * hu, 0.27 * hu, 0.25 * hu)
    m = clamp01(np.maximum(m, peak * (1 - smoothstep(-0.2, 0.0, (surf['yu'] - 0.0)) * 0)))
    light, _ = surface_light(surf, 0.35)
    lp = pillow(peak, 0.16 * hu, 1.0)
    light = np.maximum(light * (1 - peak), lp * peak)
    X, Y = grid()
    folds = 0.5 + 0.5 * np.sin((X * 0.5 - Y * 1.0) / (0.06 * hu) + 2 * value_noise(rng, 8, 1))
    v = light * (0.82 + 0.18 * folds)
    paint_shaded(cv, m, col, v, rng, outline=0.7)
    # front hem band
    bc = []
    for i in range(25):
        uu = -1.0 + 1.97 * i / 24
        bc.append(head.pt(uu, edge + 0.2 * smoothstep(0.35, 1.0, abs(uu)) - 0.04, g + 0.5))
    hem = stroke(bc, [0.1 * hu] * 25) * clamp01(m * 2)
    paint_shaded(cv, hem, tone(col, 0.8), light * 0.95, rng, outline=0.45)
    # ties at the back
    if p.get('cap_ties', True):
        (tx, ty), (bx, by) = ear_anchor(head)
        sx = tx - 0.42 * hu
        sy = ty - 0.05 * hu
        for i, ln in enumerate((1.0, 1.25)):
            pts = [(sx - 0.02 * hu * i, sy + 0.02 * hu * i)]
            for k in range(1, 9):
                t = k / 8
                pts.append((sx - 0.22 * hu * t * ln - 0.04 * hu * i - 0.03 * hu * math.sin(t * 4 + i),
                            sy + 1.0 * hu * t * ln))
            wid = [0.1 * hu * (1 - 0.3 * t) for t in np.linspace(0, 1, 9)]
            tm = stroke(pts, wid)
            paint_shaded(cv, tm, tone(col, 0.9), pillow(tm, 0.04 * hu, 1.0) * 0.8, rng, outline=0.45)
    return m


def draw_tall_hat(cv, head, p, rng):
    """Tall black official's hat (jin xian guan): gauze cap band plus a slanted crown."""
    hu = head.hu
    g = 0.08 * hu
    col = (hexc('#0D0C0B'), hexc('#2A2826'), hexc('#6E6A64'))
    # rising back plate drawn first (behind the band)
    f0 = head.pt(0.15, -0.62, g)
    f1 = head.pt(-0.55, -0.62, g)
    back = head.local_to_screen(-0.1 * hu, -0.62, -0.95 * hu)
    apex_h = p.get('hat_h', 0.75) * hu
    pts = [(f0[0] + 0.02 * hu, f0[1] + 0.05 * hu), (f0[0] - 0.04 * hu, f0[1] - apex_h * 0.75),
           (f0[0] - 0.22 * hu, f0[1] - apex_h), (back[0] + 0.1 * hu, back[1] - apex_h * 0.55),
           (back[0] - 0.02 * hu, back[1] + 0.02 * hu)]
    m = poly(catmull(pts, 6) + [(f1[0], f1[1] + 0.2 * hu)])
    l = pillow(m, 0.15 * hu, 0.9)
    X, Y = grid()
    rid = 0.5 + 0.5 * np.sin((X * 0.25 + Y * 1.0) / (0.035 * hu))
    v = clamp01(l * (0.85 + 0.15 * rid))
    cv.paint(m, shade_ramp(v, *col))
    cv.paint(ink_outline(m, 0.6, rng, 0.3), INK, 0.9)
    # front ridge rim
    rim = stroke(catmull(pts[:4], 6), [0.06 * hu] * 19)
    paint_metal(cv, rim * m, pillow(rim, 0.03 * hu, 1.0), p.get('hat_trim', 'gold') if p.get('hat_trim') else 'black', rng,
                outline=0.0)
    # cap band
    surf = head.surface(grow=g)
    u, yu, face = surf['u'], surf['yu'], surf['face']
    au = np.abs(u)
    yb = -0.52 + 0.18 * smoothstep(0.35, 1.0, au)
    yb = np.where(face, yb, -0.34)
    band = (1 - smoothstep(yb - 0.015, yb + 0.015, yu)) * surf['mask']
    light, _ = surface_light(surf, 0.35)
    cv.paint(band, shade_ramp(clamp01(light * 0.9), *col))
    cv.paint(ink_outline(band, 0.6, rng, 0.3), INK, 0.9)
    # hairpin
    a = (back[0] - 0.25 * hu, back[1] - apex_h * 0.25)
    b = (f0[0] + 0.15 * hu, f0[1] - apex_h * 0.35)
    draw_pin(cv, a[0], a[1], b[0], b[1], hu, rng, 'gold')


def draw_hood(cv, head, body, p, rng, front=False):
    """Cloth hood: back part (front=False) is drawn before the head, the rim after."""
    hu = head.hu
    col = hexc(p['hood_col'])
    g = 0.15 * hu
    (tx, ty), (bx, by) = ear_anchor(head)
    if not front:
        # drape over shoulders behind the head
        nbx, nby = body.nbx, body.nby
        pts = [head.pt(0.95, -0.55, g), head.local_to_screen(0, -1.12, -0.3 * hu)[:2],
               head.local_to_screen(-0.4 * hu, -0.6, -1.1 * hu)[:2], (tx - 0.75 * hu, by + 0.4 * hu),
               (nbx - 1.3 * hu, nby + 0.45 * hu), (nbx - 0.2 * hu, nby + 0.75 * hu),
               (nbx + 0.9 * hu, nby + 0.35 * hu), head.pt(0.9, 0.7, g * 0.6)]
        m = poly(catmull(pts, 8, closed=True))
        l = pillow(m, 0.4 * hu, 0.8)
        X, Y = grid()
        folds = 0.5 + 0.5 * np.sin((X - head.xc) / (0.09 * hu) + 0.7 * np.sin(Y / (0.2 * hu)))
        paint_shaded(cv, m, col, l * (0.8 + 0.2 * folds) * 0.85, rng, outline=0.8)
        return m
    # rim framing the face
    surf = head.surface(grow=g * 0.6)
    u, yu, face = surf['u'], surf['yu'], surf['face']
    au = np.abs(u)
    open_top = p.get('hood_top', -0.48)
    # face opening: an ellipse in (u, yu)
    eo = ((u / 0.86) ** 2 + ((yu - 0.3) / (0.3 - open_top)) ** 2)
    rim = (smoothstep(0.92, 1.0, eo)) * surf['mask'] * (yu < 0.75)
    rim = rim * (1 - smoothstep(0.6, 0.75, yu) * (eo < 1.4))
    light, _ = surface_light(surf, 0.35)
    paint_shaded(cv, rim, col, light * 0.9, rng, outline=0.75)
    # inner shadow of the rim on the face
    return rim


def draw_neck_scarf(cv, head, body, p, rng):
    hu = head.hu
    col = hexc(p['scarf_col'])
    lt, rt = body.neck_l_top, body.neck_r_top
    lb, rb = body.neck_l, body.neck_r
    y_top = head.ye + 0.98 * hu
    pts = [(lb[0] - 0.25 * hu, lb[1] + 0.05 * hu), (lt[0] - 0.05 * hu, y_top + 0.08 * hu),
           (rt[0] + 0.05 * hu, y_top - 0.02 * hu), (rb[0] + 0.3 * hu, rb[1] + 0.05 * hu),
           (rb[0] + 0.1 * hu, rb[1] + 0.4 * hu), (body.nbx - 0.1 * hu, body.nby + 0.5 * hu),
           (lb[0] - 0.1 * hu, lb[1] + 0.35 * hu)]
    m = poly(catmull(pts, 8, closed=True))
    X, Y = grid()
    folds = 0.5 + 0.5 * np.sin((Y - X * 0.25) / (0.07 * hu) + value_noise(rng, 6, 1) * 1.5)
    l = pillow(m, 0.2 * hu, 1.0)
    paint_shaded(cv, m, col, l * (0.7 + 0.3 * folds), rng, outline=0.7)
    # hanging end
    ex = body.nbx + 0.35 * hu
    ey = body.nby + 0.3 * hu
    tail = [(ex, ey - 0.1 * hu), (ex + 0.25 * hu, ey + 0.2 * hu), (ex + 0.15 * hu, ey + 0.75 * hu),
            (ex - 0.08 * hu, ey + 0.72 * hu), (ex - 0.1 * hu, ey + 0.2 * hu)]
    tm = poly(catmull(tail, 6, closed=True))
    paint_shaded(cv, tm, tone(col, 0.92), pillow(tm, 0.08 * hu, 1.0) * 0.85, rng, outline=0.6)


# ----------------------------------------------------------------------
# Female hair and ornaments
# ----------------------------------------------------------------------

def draw_flower(cv, x, y, r, col, rng, petals=5, rot=0.0):
    ms = []
    for k in range(petals):
        a = rot + 2 * math.pi * k / petals
        px, py = x + math.cos(a) * r * 0.55, y + math.sin(a) * r * 0.55
        ms.append(ellipse(px, py, r * 0.5, r * 0.36, a))
    m = clamp01(sum(ms))
    l = pillow(m, r * 0.4, 1.0)
    c = hexc(col)
    paint_shaded(cv, m, c, l, rng, outline=0.35, ink_a=0.6, tex=0.02)
    cv.paint(ellipse(x, y, r * 0.22, r * 0.22), hexc('#D9B54A'), 0.95)


def draw_buyao(cv, x, y, hu, rng, n=3, length=0.45, metal='gold', bead='#B03A2E'):
    """Dangling ornament: short chains with beads hanging from (x, y)."""
    for k in range(n):
        dx = (k - (n - 1) / 2) * 0.06 * hu
        L = length * hu * (0.8 + 0.4 * rng.uniform())
        pts = [(x + dx * 0.3, y), (x + dx, y + L)]
        cv.paint(stroke(resample(pts, 6), [0.25] * 6), hexc('#C9A24A'), 0.9)
        for j in range(3):
            t = (j + 1) / 3
            bx, by = x + dx * (0.3 + 0.7 * t), y + L * t
            bm = ellipse(bx, by, 0.03 * hu + 0.3, 0.03 * hu + 0.3)
            paint_metal(cv, bm, pillow(bm, 0.03 * hu, 1.2), metal if j < 2 else 'gold', rng, outline=0.25)
            if j == 2:
                cv.paint(ellipse(bx, by, 0.022 * hu, 0.022 * hu), hexc(bead), 0.9)


# ----------------------------------------------------------------------
# Monk, props and marks
# ----------------------------------------------------------------------

def scalp_stubble(cv, head, surf, hp, rng, strength=0.5):
    """Bluish shaved-scalp tint over the hair region of a bald head."""
    u, yu, face = surf['u'], surf['yu'], surf['face']
    above = hairline_map(u, yu, dict(hp, soft=0.08))
    reg = np.where(face, above, 1 - smoothstep(0.35, 0.55, yu)) * surf['mask']
    g = value_noise(rng, 0.6, 1) * 0.5 + 0.5
    cv.multiply(reg * strength, np.array([0.8, 0.84, 0.88], np.float32) * (0.95 + 0.05 * g[..., None]))


def ordination_dots(cv, head, rng, rows=2, cols=3):
    hu = head.hu
    for r in range(rows):
        for c in range(cols):
            u = (c - (cols - 1) / 2) * 0.16
            yu = -0.78 - r * 0.1
            x, y, _, sx = head.project(u, yu, 0.5)
            m = ellipse(x, y, 0.028 * hu * sx + 0.4, 0.022 * hu + 0.3)
            cv.paint(m, hexc('#8A5A48'), 0.55)
            cv.paint(ellipse(x - 0.3, y - 0.3, 0.012 * hu, 0.01 * hu), hexc('#E8C8B0'), 0.3)


def draw_beads(cv, head, body, p, rng):
    """Prayer beads hanging around the neck over the robe."""
    hu = head.hu
    nbx, nby = body.nbx, body.nby
    col = hexc(p.get('bead_col', '#4A2E1C'))
    r = p.get('bead_r', 0.075) * hu
    (lx, ly), (rx, ry) = body.neck_l, body.neck_r
    a = (lx - 0.05 * hu, ly + 0.05 * hu)
    b = (rx + 0.1 * hu, ry + 0.05 * hu)
    low = (nbx - 0.05 * hu, nby + 1.15 * hu)
    curve = catmull([a, (lx - 0.25 * hu, ly + 0.6 * hu), low, (rx + 0.3 * hu, ry + 0.6 * hu), b], 20)
    pts = resample(curve, 60)
    # sample beads at spacing ~ 2r
    arr = np.array(curve)
    seg = np.sqrt(((arr[1:] - arr[:-1]) ** 2).sum(1))
    total = seg.sum()
    n = int(total / (2.05 * r))
    pts = resample(curve, n)
    for i, (x, y) in enumerate(pts):
        if y < nby - 0.02 * hu and (abs(x - nbx) < 0.45 * hu):
            continue  # hidden behind the neck
        big = (i == n // 2)
        rr = r * (1.5 if big else 1.0)
        m = ellipse(x, y, rr, rr)
        l = pillow(m, rr * 0.8, 1.3)
        c = shade_ramp(clamp01(l), col * 0.3, col, mix(col, hexc('#F0D8B0'), 0.5))
        cv.paint(m, c)
        cv.paint(ink_outline(m, 0.35, None, 0, 0.5), INK, 0.7)
    if p.get('tassel', True):
        x, y = pts[n // 2]
        tm = poly([(x - 0.06 * hu, y + r * 1.4), (x + 0.06 * hu, y + r * 1.4), (x + 0.12 * hu, y + 0.55 * hu),
                   (x - 0.1 * hu, y + 0.55 * hu)])
        paint_shaded(cv, tm, hexc(p.get('tassel_col', '#8A2A1E')), pillow(tm, 0.05 * hu, 1.0), rng, outline=0.4)


def draw_kasaya(cv, head, body, p, rng):
    """Diagonal patchwork sash from the far shoulder across the chest."""
    hu = head.hu
    col = hexc(p.get('kasaya_col', '#8A3A1E'))
    nbx, nby = body.nbx, body.nby
    (rx, ry) = body.neck_r
    pts = [(rx + 0.05 * hu, ry - 0.05 * hu), (body.sh_r[0] + 0.2 * hu, body.sh_r[1] - 0.05 * hu),
           (body.sh_r[0] + 0.4 * hu, H + 20), (nbx - 0.9 * hu, H + 20), (nbx - 0.1 * hu, nby + 0.75 * hu)]
    torso = poly(body.torso_poly())
    m = poly(pts) * torso
    l = body_light(m, 0.3 * hu)
    X, Y = grid()
    # patchwork grid along the sash direction
    ang = math.atan2(H - ry, -0.9 * hu - (rx - nbx))
    gu = (X * math.cos(ang) + Y * math.sin(ang)) / (0.32 * hu)
    gv = (-X * math.sin(ang) + Y * math.cos(ang)) / (0.45 * hu)
    lines = np.maximum(smoothstep(0.9, 0.97, np.abs(np.mod(gu, 1) * 2 - 1)), smoothstep(0.9, 0.97, np.abs(np.mod(gv, 1) * 2 - 1)))
    patch = np.mod(np.floor(gu) + np.floor(gv), 2)
    v = l * (0.88 + 0.12 * patch) * (1 - 0.35 * lines)
    paint_shaded(cv, m, col, v, rng, outline=0.75)
    # edge band
    edge = stroke(resample([pts[0], pts[4], (nbx - 0.9 * hu, H + 20)], 20), [0.12 * hu] * 20) * torso
    paint_shaded(cv, edge * m, tone(col, 0.75), l, rng, outline=0.0)
    # ring clasp
    cx, cy = nbx + 0.1 * hu, nby + 0.85 * hu
    rm = clamp01(ellipse(cx, cy, 0.12 * hu, 0.12 * hu) - ellipse(cx, cy, 0.07 * hu, 0.07 * hu))
    paint_metal(cv, rm, pillow(rm, 0.03 * hu, 1.0) * 0.9 + 0.1, 'gold', rng, outline=0.35)


def draw_fan(cv, head, body, p, rng):
    """White feather fan held up at the lower right."""
    hu = head.hu
    cx, cy = body.nbx + 1.25 * hu, body.nby + 0.62 * hu
    r = 0.62 * hu
    # handle
    hpts = [(cx - 0.05 * hu, cy + r * 0.85), (cx - 0.12 * hu, H + 15)]
    hm = stroke(resample(hpts, 6), [0.09 * hu] * 6)
    paint_shaded(cv, hm, hexc('#5A3A22'), pillow(hm, 0.04 * hu, 1.0), rng, outline=0.5)
    # feather blades
    lay = StrokeLayer()
    mass = StrokeLayer()
    for i in range(40):
        a = -math.pi / 2 + (i / 39 - 0.5) * 2.3 + 0.15
        L = r * (0.85 + 0.15 * math.cos((i / 39 - 0.5) * 3))
        p0 = (cx - 0.05 * hu, cy + r * 0.8)
        p1 = (cx + math.cos(a) * L * 0.4, cy + r * 0.2 + math.sin(a) * L * 0.4)
        p2 = (cx + math.cos(a) * L, cy + r * 0.05 + math.sin(a) * L * 0.95)
        mass.add([p0, p1, p2], [0.5, 0.2 * hu, 0.24 * hu], 1.0)
        lay.add([p1, p2], [0.3, 0.3], rng.uniform(0.3, 1.0))
    m = clamp01(mass.result())
    l = pillow(m, 0.25 * hu, 0.7) * 0.9
    st = lay.result()
    col = hexc(p.get('fan_col', '#E6DED0'))
    v = clamp01(l * 0.9 + 0.1 - 0.25 * st)
    c = shade_ramp(v, col * 0.45, col * 0.85, col)
    cv.paint(m, c)
    cv.paint(ink_outline(m, 0.6, rng, 0.4), INK, 0.75)
    # binding
    bm = ellipse(cx - 0.05 * hu, cy + r * 0.78, 0.1 * hu, 0.07 * hu)
    paint_metal(cv, bm, pillow(bm, 0.05 * hu, 1.0), 'gold', rng, outline=0.4)


def draw_scar(cv, head, fp, p, rng):
    hu = head.hu
    kind = p.get('scar', 'cheek')
    if kind == 'cheek':
        uv = [(-0.62, 0.12), (-0.5, 0.32), (-0.38, 0.52)]
    elif kind == 'brow':
        uv = [(0.3, -0.38), (0.44, -0.12), (0.52, 0.12)]
    elif kind == 'nose':
        uv = [(-0.35, -0.02), (0.0, 0.12), (0.35, 0.22)]
    else:  # chin
        uv = [(-0.2, 0.78), (-0.05, 0.86), (0.08, 0.94)]
    pts = [head.pt(u, y, 0.03 * hu) for u, y in uv]
    pts = catmull(pts, 8)
    n = len(pts)
    w = [0.04 * hu * math.sin(math.pi * (i + 0.5) / n) + 0.3 for i in range(n)]
    m = stroke(pts, w)
    cv.paint(blur(stroke(pts, [x * 2.2 for x in w]), 0.6), hexc('#9A5A48'), 0.3)
    cv.paint(m, hexc('#D9A08A'), 0.7)
    cv.paint(stroke(pts, [x * 0.35 for x in w]), hexc('#6A2E24'), 0.6)
    if p.get('stitches', False):
        for i in range(2, n - 2, 3):
            x, y = pts[i]
            dx, dy = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
            L = math.hypot(dx, dy) + 1e-6
            nx, ny = -dy / L, dx / L
            s = 0.05 * hu
            cv.paint(stroke([(x - nx * s, y - ny * s), (x + nx * s, y + ny * s)], [0.4, 0.4]), hexc('#4A2A20'), 0.6)


def draw_earring(cv, head, rng):
    hu = head.hu
    (tx, ty), (bx, by) = ear_anchor(head)
    x, y = bx - 0.1 * hu, by + 0.06 * hu
    m = clamp01(ellipse(x, y + 0.05 * hu, 0.06 * hu, 0.08 * hu) - ellipse(x, y + 0.05 * hu, 0.035 * hu, 0.055 * hu))
    paint_metal(cv, m, pillow(m, 0.02 * hu, 1.0) * 0.8 + 0.2, 'gold', rng, outline=0.3)


def draw_eyepatch(cv, head, fp, rng):
    hu = head.hu
    eu = fp['eye_u']
    cx, cy, _, sx = head.project(eu, 0.0, 0.03 * hu)
    m = ellipse(cx, cy + 0.01 * hu, 0.17 * hu * sx + 1, 0.13 * hu)
    # strap
    a = head.pt(eu + 0.25, -0.12, 0.02 * hu)
    b = head.pt(eu - 0.3, -0.3, 0.03 * hu)
    c = head.pt(-0.6, -0.45, 0.03 * hu)
    d = head.pt(-0.98, -0.42, 0.03 * hu)
    sm = stroke(catmull([a, (cx, cy - 0.08 * hu), b, c, d], 6), [0.035 * hu + 0.4] * 21)
    paint_shaded(cv, sm, hexc('#2A211A'), np.full((HH, WW), 0.5, np.float32), rng, outline=0.0)
    paint_shaded(cv, m, hexc('#2A211A'), pillow(m, 0.08 * hu, 1.0), rng, outline=0.5)


def draw_side_lock(cv, head, colors, rng, hp):
    """Hair lock swept over the top of the near ear toward the back."""
    hu = head.hu
    (tx, ty), (bx, by) = ear_anchor(head)
    pts = [head.pt(-0.78, -0.45, 2.0), head.pt(-0.86, -0.12, 2.5), (tx + 0.06 * hu, ty + 0.25 * hu),
           (tx - 0.12 * hu, ty + 0.3 * hu), (tx - 0.32 * hu, ty + 0.1 * hu), (tx - 0.3 * hu, ty - 0.35 * hu)]
    m = poly(catmull(pts, 6, closed=True))
    l = pillow(m, 0.12 * hu, 1.0) * 0.85
    kx, ky = topknot_point(head, hp)

    def direction(x, y):
        return (tx - 0.4 * hu) - x, (ty - 0.1 * hu) - y + 0.3 * (y - ty)
    st = flow_strands(m, 120, rng, direction, length=(6, 12), width=(0.3, 0.6), curl=0.05)
    paint_hair_mass(cv, m, l, colors, st, rng, outline=0.6)


def draw_ponytail(cv, head, hp, rng, colors):
    hu = head.hu
    kx, ky = topknot_point(head, hp)
    pts = [(kx, ky)]
    for k in range(1, 10):
        t = k / 9
        pts.append((kx - 0.55 * hu * t - 0.15 * hu * math.sin(t * 3), ky + 2.0 * hu * t ** 1.1))
    wid = [0.32 * hu * (1.0 - 0.55 * t) * (0.8 + 0.4 * math.sin(math.pi * min(1, t * 1.6))) for t in np.linspace(0, 1, 10)]
    m = stroke(pts, wid)
    m = clamp01(m * (1 + 0.5 * value_noise(rng, 2.0, 2) * (1 - smoothstep(0, 1.5, edge_distance(m)))))
    l = pillow(m, 0.15 * hu, 1.0) * 0.85

    def direction(x, y):
        return -0.3, 1.0
    st = flow_strands(m, 260, rng, direction, length=(10, 24), width=(0.3, 0.7), curl=0.03)
    paint_hair_mass(cv, m, l, colors, st, rng, outline=0.6)


def draw_female_hair(cv, head, body, hp, rng, colors, stage):
    """stage 'back': hair behind the body; 'front': cap, buns, ornaments."""
    from portrait_dress import draw_hair_cap, draw_loose_back
    hu = head.hu
    style = hp['style']
    if stage == 'back':
        if style in ('loose', 'half_up'):
            draw_loose_back(cv, head, body, hp, rng, colors, length=hp.get('length', 1.0), spread=1.1)
        if style == 'ponytail':
            draw_ponytail(cv, head, hp, rng, colors)
        if style == 'low_bun':
            kx, ky = topknot_point(head, hp)
            draw_bun(cv, head, kx, ky, 0.28 * hu, 0.22 * hu, colors, rng)
        return
    # front stage ------------------------------------------------------
    if style in ('high_bun', 'double_bun'):
        # bun(s) partly behind the skull -> draw before the cap
        kx, ky = topknot_point(head, hp)
        if style == 'high_bun':
            draw_bun(cv, head, kx - 0.05 * hu, ky - 0.05 * hu, 0.34 * hu, 0.26 * hu, colors, rng, ang=-0.3)
        else:
            draw_bun(cv, head, kx - 0.32 * hu, ky + 0.05 * hu, 0.24 * hu, 0.2 * hu, colors, rng, ang=-0.5)
            draw_bun(cv, head, kx + 0.25 * hu, ky - 0.08 * hu, 0.23 * hu, 0.19 * hu, colors, rng, ang=0.3)
    m, surf = draw_hair_cap(cv, head, hp, rng, colors)
    if style in ('high_bun', 'double_bun', 'half_up', 'ponytail'):
        # front part of the bun / tie over the cap
        kx, ky = topknot_point(head, hp)
        if style == 'high_bun':
            draw_bun(cv, head, kx + 0.04 * hu, ky - 0.12 * hu, 0.26 * hu, 0.2 * hu, colors, rng, ang=-0.2)
        elif style == 'half_up':
            draw_bun(cv, head, kx, ky, 0.18 * hu, 0.15 * hu, colors, rng)
        elif style == 'ponytail':
            tie = ellipse(kx, ky, 0.13 * hu, 0.1 * hu)
            paint_shaded(cv, tie, hexc(hp.get('ribbon', '#8E2A20')), pillow(tie, 0.06 * hu, 1.0), rng, outline=0.45)
    return m, surf


def draw_hair_ornaments(cv, head, hp, rng):
    hu = head.hu
    kx, ky = topknot_point(head, hp)
    orn = hp.get('ornaments', [])
    metal = hp.get('orn_metal', 'gold')
    if 'pins' in orn:
        for k, (dx, dy, ang, ln) in enumerate(((-0.2, 0.0, 2.6, 0.75), (0.15, -0.12, 0.35, 0.6))):
            x0 = kx + dx * hu
            y0 = ky + dy * hu
            x1 = x0 + math.cos(ang) * ln * hu
            y1 = y0 + math.sin(ang) * ln * hu * 0.5
            draw_pin(cv, x1, y1, x0, y0, hu, rng, metal, head_r=0.06, jewel=hp.get('jewel', '#3F6E5A'))
    if 'comb' in orn:
        cx, cy = kx + 0.05 * hu, ky + 0.12 * hu
        m = clamp01(ellipse(cx, cy, 0.24 * hu, 0.11 * hu, -0.2) * (1 - ellipse(cx + 0.01 * hu, cy + 0.08 * hu, 0.2 * hu, 0.09 * hu, -0.2)))
        paint_metal(cv, m, pillow(m, 0.04 * hu, 1.0) * 0.9 + 0.1, metal, rng, outline=0.4, spec=0.9)
    if 'flower' in orn:
        fx, fy = kx + 0.28 * hu, ky + 0.2 * hu
        draw_flower(cv, fx, fy, 0.12 * hu, hp.get('flower_col', '#B5524A'), rng, rot=0.3)
        draw_flower(cv, fx + 0.14 * hu, fy - 0.12 * hu, 0.08 * hu, hp.get('flower_col2', '#D8C8B8'), rng, rot=1.0)
    if 'buyao' in orn:
        bx, by = kx + 0.3 * hu, ky - 0.05 * hu
        draw_pin(cv, bx + 0.25 * hu, by - 0.15 * hu, bx - 0.05 * hu, by + 0.05 * hu, hu, rng, metal, head_r=0.07,
                 jewel=hp.get('jewel', '#A8423A'))
        draw_buyao(cv, bx + 0.25 * hu, by - 0.08 * hu, hu, rng, n=3, length=0.45, bead=hp.get('jewel', '#A8423A'))
    if 'band' in orn:
        draw_headband(cv, head, dict(band_col=hp.get('band_col', '#7E1F17'), band_y=-0.6, band_h=0.08,
                                     tails=False, band_jewel=True, jewel_col=hp.get('jewel', '#3F6E5A'),
                                     grow=0.07 * hu), rng)


def draw_forehead_mark(cv, head, rng, col='#B03A2E'):
    hu = head.hu
    x, y, _, sx = head.project(0.0, -0.3, 0.04 * hu)
    m = clamp01(ellipse(x, y, 0.035 * hu * sx + 0.3, 0.06 * hu) + ellipse(x, y + 0.05 * hu, 0.02 * hu, 0.02 * hu))
    cv.paint(m, hexc(col), 0.8)
