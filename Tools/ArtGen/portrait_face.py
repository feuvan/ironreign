"""Face rendering: skin shading from a height field, eyes, brows, nose, mouth,
ear, wrinkles, scars and facial hair."""
import math

import numpy as np
from scipy import ndimage as ndi

from portrait_raster import (HH, WW, SCALE, LIGHT, grid, clamp01, smoothstep, blur, mix,
                             poly, polys, ellipse, stroke, strokes, stroke_outline, taper,
                             catmull, resample, StrokeLayer, value_noise, fiber_noise,
                             normals_from_height, lambert, ink_outline, edge_distance,
                             hexc)
from portrait_head import gbump, ridge, shadow_map

INK = hexc('#2A2119')


def _line_pts(head, pts_uv, p=0.0):
    out = []
    for item in pts_uv:
        if len(item) == 3:
            u, yu, pp = item
        else:
            u, yu = item
            pp = p
        out.append(head.pt(u, yu, pp))
    return out


# ----------------------------------------------------------------------
# Skin
# ----------------------------------------------------------------------

def skin_palette(base_hex):
    base = hexc(base_hex)
    deep = base * np.array([0.42, 0.30, 0.27]) + np.array([0.03, 0.01, 0.01])
    shade = base * np.array([0.72, 0.56, 0.50])
    lite = mix(base, hexc('#F6E2C8'), 0.45)
    return deep.astype(np.float32), shade.astype(np.float32), base, lite.astype(np.float32)


def face_heightfield(head, fp):
    hu = head.hu
    h = np.zeros((HH, WW), np.float32)
    eu = fp['eye_u']
    # brow ridge
    for sgn in (-1, 1):
        x, y, _, sx = head.project(sgn * eu * 0.95, -0.2)
        h += gbump(x, y, 0.2 * hu * sx + 1, 0.075 * hu, 0.035 * hu * fp.get('brow_ridge', 1.0))
    xb, yb, _, _ = head.project(0, -0.16)
    h += gbump(xb, yb, 0.12 * hu, 0.08 * hu, 0.03 * hu)
    # eye sockets
    for sgn in (-1, 1):
        x, y, _, sx = head.project(sgn * eu * 0.9, 0.02)
        h -= gbump(x, y, 0.19 * hu * sx + 1, 0.085 * hu, 0.05 * hu)
        # eyeball
        x, y, _, sx = head.project(sgn * eu, 0.01)
        h += gbump(x, y, 0.12 * hu * sx + 1, 0.06 * hu, 0.02 * hu)
        # under-eye bag
        x, y, _, sx = head.project(sgn * eu, 0.11)
        h += gbump(x, y, 0.14 * hu * sx + 1, 0.035 * hu, 0.012 * hu * (1 + 2 * fp.get('age', 0)))
    # cheekbones
    for sgn in (-1, 1):
        x, y, _, sx = head.project(sgn * (eu + 0.12), 0.26)
        h += gbump(x, y, 0.2 * hu * sx + 1, 0.13 * hu, 0.025 * hu * fp.get('cheekbone', 1.0))
    # cheek hollow (age / lean)
    hol = fp.get('hollow', 0.0)
    if hol > 0:
        for sgn in (-1, 1):
            x, y, _, sx = head.project(sgn * (eu + 0.08), 0.52)
            h -= gbump(x, y, 0.13 * hu * sx + 1, 0.12 * hu, 0.03 * hu * hol)
    # nose
    np_ = fp['nose_p'] * hu
    nt = fp['nose_y']
    nw = fp['nose_w']
    nas = head.pt(0, -0.06, np_ * 0.18)
    mid = head.pt(0, nt * 0.55, np_ * 0.55)
    tip = head.pt(0, nt, np_)
    h += ridge(nas, mid, 0.03 * hu, np_ * 0.45, 0.11 * hu, 0.055 * hu, 0.05 * hu)
    h += ridge(mid, (tip[0], tip[1] - 0.03 * hu), 0.0, np_ * 0.4, 0.12 * hu, 0.06 * hu, 0.05 * hu)
    tx, ty = tip
    h += gbump(tx - 0.01 * hu, ty, 0.075 * hu, 0.06 * hu, np_ * 0.55)
    # alae
    for sgn, k in ((-1, 1.0), (1, 0.6)):
        x, y, _, sx = head.project(sgn * nw, nt + 0.03, np_ * 0.25)
        h += gbump(x, y, 0.07 * hu * max(sx, 0.4), 0.055 * hu, np_ * 0.35 * k)
    # muzzle / philtrum / lips
    my = fp['mouth_y']
    x, y, _, _ = head.project(0, my - 0.05, 0.01 * hu)
    h += gbump(x, y, 0.32 * hu, 0.2 * hu, 0.04 * hu)
    x, y, _, _ = head.project(0, my - 0.035, 0.02 * hu)
    h += gbump(x, y, 0.16 * hu, 0.03 * hu, 0.012 * hu * fp.get('lip_full', 1.0))
    x, y, _, _ = head.project(0, my + 0.05, 0.02 * hu)
    h += gbump(x, y, 0.15 * hu, 0.035 * hu, 0.018 * hu * fp.get('lip_full', 1.0))
    # chin
    x, y, _, _ = head.project(0, 0.86, 0.0)
    h += gbump(x, y, 0.16 * hu * fp.get('chin_w', 1.0), 0.08 * hu, 0.03 * hu)
    x, y, _, _ = head.project(0, 0.74, 0.0)
    h -= gbump(x, y, 0.12 * hu, 0.03 * hu, 0.012 * hu)
    # nasolabial fold
    nl = fp.get('nasolabial', 0.3)
    for sgn in (-1, 1):
        a = head.pt(sgn * (nw + 0.05), nt + 0.06, 0.02 * hu)
        b = head.pt(sgn * (fp['mouth_u'] + 0.09), my + 0.1, 0.0)
        h -= ridge(a, b, 0.015 * hu * nl, 0.01 * hu * nl, 0.025 * hu, 0.025 * hu, 0.02 * hu)
    return h


def render_skin(cv, head, fp, rng, surf=None):
    """Paint the head skin.  Returns (skin_mask, light map, feature height)."""
    if surf is None:
        surf = head.surface()
    mask = surf['mask']
    inside = surf['inside']
    z = surf['z'].copy()
    # extend z outside so gradients at the silhouette are sane
    idx = ndi.distance_transform_edt(~inside, return_indices=True)[1]
    z = z[idx[0], idx[1]]
    z = blur(z, 1.2)
    hf = face_heightfield(head, fp)
    htot = z + hf
    nx, ny, nz = normals_from_height(htot)
    lit = lambert(nx, ny, nz, wrap=0.35)
    sh = shadow_map(hf, LIGHT, steps=12, max_dist=0.14 * head.hu)
    sh = blur(sh, 1.5)
    ao = clamp01((blur(hf, 3.0) - hf) / (0.03 * head.hu))
    v = lit * (1 - 0.14 * sh) - 0.12 * ao
    # paint texture
    v += 0.035 * value_noise(rng, 10, 3)
    v = clamp01(v)
    deep, shade, base, lite = skin_palette(fp['skin'])
    t = v[..., None]
    # 4-stop ramp: deep (0) -> shade (0.35) -> base (0.62) -> lite (1)
    c = np.where(t < 0.35, mix(deep, shade, clamp01(t / 0.35)),
                 np.where(t < 0.62, mix(shade, base, clamp01((t - 0.35) / 0.27)),
                          mix(base, lite, clamp01((t - 0.62) / 0.38))))
    c = c.astype(np.float32)
    # warm the terminator a touch
    term = np.exp(-((v - 0.36) / 0.12) ** 2)[..., None]
    c = c + term * np.array([0.04, -0.005, -0.02], np.float32)
    # rosy cheeks / nose / ears
    rosy = np.zeros((HH, WW), np.float32)
    for sgn, k in ((-1, 1.0), (1, 0.8)):
        x, y, _, sx = head.project(sgn * (fp['eye_u'] + 0.05), 0.3)
        rosy += gbump(x, y, 0.16 * head.hu * sx + 1, 0.11 * head.hu, k)
    tx, ty = head.pt(0, fp['nose_y'], fp['nose_p'] * head.hu)
    rosy += gbump(tx, ty, 0.07 * head.hu, 0.06 * head.hu, 0.7)
    rosy *= fp.get('rosy', 0.5)
    c = mix(c, c * np.array([1.04, 0.86, 0.84], np.float32), clamp01(rosy)[..., None] * 0.6)
    # beard shadow (men)
    stub = fp.get('stubble', 0.0)
    if stub > 0:
        u, yu = surf['u'], surf['yu']
        bm = beard_region(head, fp, surf, top_off=0.0)
        c = mix(c, c * np.array([0.82, 0.84, 0.86], np.float32), (bm * stub)[..., None])
    # forehead slightly lighter/yellower, jaw cooler
    cv.paint(mask, c)
    return mask, v, hf, surf


def beard_region(head, fp, surf, top_off=0.0, chin_ext=0.0):
    """Mask of the beard-growing area on the face surface."""
    u = surf['u']
    yu = surf['yu']
    my = fp['mouth_y']
    nt = fp['nose_y']
    au = np.abs(u)
    # upper boundary: from sideburn (u=-1, yu~0.0) down the cheek to the moustache
    top = np.where(au > 0.55, 0.05 + (1 - au) * 0.9, 0.55 - (au - 0.25) * 0.2)
    top = np.minimum(top, nt + 0.12 + (au * 0.3)) + top_off
    m = smoothstep(top - 0.02, top + 0.06, yu) * surf['inside']
    return m.astype(np.float32)


# ----------------------------------------------------------------------
# Features
# ----------------------------------------------------------------------

def draw_eyes(cv, head, fp, lit, rng):
    hu = head.hu
    eu = fp['eye_u']
    ew = fp['eye_w']          # in u units (half width)
    eh = fp['eye_h']          # opening height, yu units
    tilt = fp['eye_tilt']     # yu rise of outer corner
    ink_w = fp.get('lid_w', 1.25)
    iris_c = hexc(fp.get('iris', '#2B1D14'))
    for sgn in (-1, 1):       # -1 = near (left) eye, +1 = far eye
        cu = sgn * eu
        inner = (cu - sgn * ew, 0.012)
        outer = (cu + sgn * ew, 0.012 - tilt)
        n = 9
        up, lo = [], []
        for i in range(n + 1):
            t = i / n
            uu = inner[0] + (outer[0] - inner[0]) * t
            yy = inner[1] + (outer[1] - inner[1]) * t
            # upper lid peaks a bit toward the inner side, lower lid flatter
            bu = math.sin(math.pi * t) ** 0.85 * (1 + 0.15 * (0.5 - t))
            bl = math.sin(math.pi * t) ** 1.1
            up.append((uu, yy - eh * bu, 0.012 * hu))
            lo.append((uu, yy + eh * 0.55 * bl, 0.012 * hu))
        up_s = _line_pts(head, up)
        lo_s = _line_pts(head, lo)
        eye_poly = up_s + lo_s[::-1][1:-1]
        em = poly(eye_poly)
        ex, ey, _, sx = head.project(cu, 0.01)
        # sclera: warm white, shadowed under the upper lid and toward corners
        X, Y = grid()
        top_y = np.interp(X, [p[0] for p in sorted(up_s)], [p[1] for p in sorted(up_s)])
        lidsh = clamp01(1 - (Y - top_y) / (eh * hu * 0.9))
        light_here = float(np.clip(lit[int(ey * SCALE), int(ex * SCALE)], 0.2, 1.0))
        scl = hexc('#E6DACA') * (0.62 + 0.38 * light_here)
        scl_c = scl[None, None, :] * (1 - 0.38 * lidsh[..., None]) * np.array([1, 0.97, 0.95], np.float32)
        cv.paint(em, scl_c)
        # iris
        gaze = fp.get('gaze', -0.25)
        iu = cu + gaze * ew * 0.6
        ix, iy, _, isx = head.project(iu, 0.01 - tilt * 0.4 * (1 + sgn * 0) * 0.5, 0.015 * hu)
        r = fp.get('iris_r', 0.43) * eh * hu * 2.05
        iy += r * 0.12
        im = ellipse(ix, iy, r * isx, r) * em
        ir = iris_c[None, None, :] * (1.0 + 0.9 * clamp01((Y - (iy - r * 0.2)) / (r * 1.6)))[..., None]
        cv.paint(im, ir * (0.75 + 0.25 * light_here))
        pm = ellipse(ix, iy, r * 0.45 * isx, r * 0.48) * em
        cv.paint(pm, hexc('#0E0A08'))
        # iris ring
        ring = clamp01(ellipse(ix, iy, r * isx + 0.25, r + 0.25) - ellipse(ix, iy, r * isx - 0.45, r - 0.45)) * em
        cv.paint(ring, hexc('#120C09'), 0.6)
        # upper lid shadow over iris
        cv.paint(em * lidsh * 0.0, INK)
        # catchlight
        hl = ellipse(ix - r * 0.38 * isx, iy - r * 0.38, max(0.55, r * 0.26 * isx), max(0.55, r * 0.26)) * em
        cv.paint(hl, hexc('#F4EEE4'), 0.9)
        # upper lid ink: thicker toward the outer corner, slight overshoot
        ext = (outer[0] + sgn * ew * 0.18, outer[1] - eh * 0.02 + fp.get('lid_flick', 0.0), 0.0)
        lid_pts = up_s + [head.pt(*ext)]
        npt = len(lid_pts)
        wid = [ink_w * (0.45 + 0.75 * math.sin(math.pi * min(1, (i / (npt - 1)) * 1.05)) ** 0.6) for i in range(npt)]
        wid[-1] = 0.25
        wid[0] = 0.5
        lid = stroke(lid_pts, wid)
        cv.paint(lid, hexc('#1A120D'), 0.95)
        # lower lid
        lo_line = lo_s[2:]
        lw = [0.35 + 0.35 * math.sin(math.pi * i / (len(lo_line) - 1)) for i in range(len(lo_line))]
        cv.paint(stroke(lo_line, lw), hexc('#5A3A2C'), 0.55)
        # crease (double eyelid) or lid fold
        crease = fp.get('crease', 0.5)
        if crease > 0:
            cr = []
            for i in range(2, n + 1):
                t = i / n
                uu = inner[0] + (outer[0] - inner[0]) * t
                yy = inner[1] + (outer[1] - inner[1]) * t
                bu = math.sin(math.pi * (0.1 + 0.9 * t)) ** 0.7
                cr.append((uu + sgn * ew * 0.05, yy - eh * bu - 0.045 - 0.02 * (1 - t), 0.015 * hu))
            cr_s = _line_pts(head, cr)
            cw = [0.55 * math.sin(math.pi * i / (len(cr_s) - 1)) + 0.1 for i in range(len(cr_s))]
            cv.paint(stroke(cr_s, cw), hexc('#5C3B2C'), 0.45 * crease)
        # eye bag line for older faces
        age = fp.get('age', 0.0)
        if age > 0.3:
            bag = []
            for i in range(1, n):
                t = i / n
                uu = inner[0] + (outer[0] - inner[0]) * t
                yy = inner[1] + (outer[1] - inner[1]) * t
                bag.append((uu, yy + eh * 0.55 * math.sin(math.pi * t) + 0.06 + 0.02 * math.sin(math.pi * t), 0.0))
            bs = _line_pts(head, bag)
            cv.paint(stroke(bs, [0.45 * math.sin(math.pi * i / (len(bs) - 1)) + 0.05 for i in range(len(bs))]),
                     hexc('#6A4636'), 0.45 * age)
            # crow's feet
            for k in range(3):
                a = (outer[0] + sgn * ew * 0.25, outer[1] + 0.02 + 0.05 * (k - 1))
                b = (outer[0] + sgn * ew * 0.75, outer[1] + 0.02 + 0.09 * (k - 1))
                pts = _line_pts(head, [a, b])
                cv.paint(stroke(pts, [0.35, 0.1]), hexc('#6A4636'), 0.35 * age)


def draw_brows(cv, head, fp, rng, color):
    hu = head.hu
    eu = fp['eye_u']
    ew = fp['eye_w']
    by = fp['brow_y']
    thick = fp['brow_t']
    arch = fp['brow_arch']
    tilt = fp['brow_tilt']        # yu rise at outer end (positive = up-swept)
    lay = StrokeLayer()
    dens = StrokeLayer()
    for sgn in (-1, 1):
        u0 = sgn * (eu - ew * 1.05)
        u1 = sgn * (eu + ew * 1.25 * fp.get('brow_len', 1.0))
        pts = []
        n = 12
        for i in range(n + 1):
            t = i / n
            uu = u0 + (u1 - u0) * t
            yy = by - arch * math.sin(math.pi * min(1, t * 1.25)) - tilt * t + 0.01 * (1 - t)
            pts.append((uu, yy, 0.02 * hu))
        P = _line_pts(head, pts)
        wid = [thick * hu * (1.0 - 0.75 * (i / n) ** 1.3) * (0.75 + 0.25 * math.sin(math.pi * min(1, i / n + 0.3))) for i in range(n + 1)]
        dens.add(P, wid, 1.0)
        # hairs
        nh = int(70 * thick / 0.06)
        for k in range(nh):
            t = rng.uniform(0, 1)
            i = min(n - 1, int(t * n))
            f = t * n - i
            x = P[i][0] + (P[i + 1][0] - P[i][0]) * f
            y = P[i][1] + (P[i + 1][1] - P[i][1]) * f
            dx = P[i + 1][0] - P[i][0]
            dy = P[i + 1][1] - P[i][1]
            L = math.hypot(dx, dy) + 1e-6
            dx, dy = dx / L, dy / L
            wl = wid[i] * 0.5
            off = rng.uniform(-wl, wl)
            # hairs angle from the inner end upward, then along the brow
            ang = math.atan2(dy, dx) - sgn * 0.0
            if t < 0.2:
                ang -= sgn * 0.7 * (1 - t / 0.2) * (1 if sgn < 0 else 1)
            hl = rng.uniform(1.6, 3.2)
            sx0 = x - dy * off
            sy0 = y + dx * off
            ca, sa = math.cos(ang), math.sin(ang)
            pts2 = [(sx0 - ca * hl * 0.5, sy0 - sa * hl * 0.5 + 0.2), (sx0, sy0), (sx0 + ca * hl * 0.5, sy0 + sa * hl * 0.5 - 0.15)]
            lay.add(pts2, [0.35, 0.45, 0.15], rng.uniform(0.5, 1.0))
    d = dens.result()
    h = lay.result()
    a = clamp01(blur(d, 0.3) * 0.8 + h * 0.6) * clamp01(blur(d, 0.6) * 1.8)
    cv.paint(a, color, 0.95)


def draw_nose(cv, head, fp, lit):
    hu = head.hu
    np_ = fp['nose_p'] * hu
    nt = fp['nose_y']
    nw = fp['nose_w']
    ink = hexc('#3A2418')
    # far-side bridge line (soft)
    pts = [head.pt(0.06, -0.02, np_ * 0.2), head.pt(0.05, nt * 0.5, np_ * 0.6), head.pt(0.05, nt - 0.04, np_ * 0.9)]
    pts = catmull(pts, 6)
    w = [0.15 + 0.5 * (i / (len(pts) - 1)) ** 2 for i in range(len(pts))]
    cv.paint(stroke(pts, w), ink, 0.35)
    # tip underside + near ala curve
    tip = head.pt(0, nt, np_)
    ala = [head.pt(-nw * 1.05, nt - 0.05, np_ * 0.2), head.pt(-nw * 1.15, nt + 0.02, np_ * 0.25),
           head.pt(-nw * 0.85, nt + 0.07, np_ * 0.3), head.pt(-nw * 0.45, nt + 0.065, np_ * 0.5)]
    ala = catmull(ala, 6)
    w = [0.2 + 0.75 * math.sin(math.pi * i / (len(ala) - 1)) for i in range(len(ala))]
    cv.paint(stroke(ala, w), ink, 0.75)
    # nostrils
    nx, ny = head.pt(-nw * 0.45, nt + 0.055, np_ * 0.55)
    cv.paint(ellipse(nx, ny, 0.06 * hu, 0.022 * hu, -0.25), hexc('#3B2218'), 0.8)
    fx, fy = head.pt(nw * 0.35, nt + 0.055, np_ * 0.55)
    cv.paint(ellipse(fx, fy, 0.03 * hu, 0.018 * hu, 0.3), hexc('#3B2218'), 0.6)
    # far ala: little hook
    fa = [head.pt(nw * 0.55, nt + 0.065, np_ * 0.5), head.pt(nw * 0.95, nt + 0.03, np_ * 0.3),
          head.pt(nw * 1.0, nt - 0.03, np_ * 0.25)]
    fa = catmull(fa, 5)
    cv.paint(stroke(fa, [0.6 * math.sin(math.pi * i / (len(fa) - 1)) + 0.1 for i in range(len(fa))]), ink, 0.5)
    # tip highlight
    tx, ty = tip
    cv.screen(ellipse(tx - 0.03 * hu, ty - 0.035 * hu, 0.03 * hu, 0.022 * hu), hexc('#F5E4CC'), 0.35)


def draw_mouth(cv, head, fp, lit, female=False):
    hu = head.hu
    my = fp['mouth_y']
    mu = fp['mouth_u']
    curve = fp.get('mouth_curve', 0.0)   # + = smile (corners up)
    lipt = fp.get('lip_full', 1.0)
    lp = 0.035 * hu
    n = 12
    line = []
    for i in range(n + 1):
        t = i / n
        uu = -mu + 2 * mu * t
        c = (2 * t - 1) ** 2
        bow = 0.012 * math.exp(-((t - 0.5) / 0.12) ** 2)
        line.append((uu, my - curve * c + bow, lp * (1 - 0.6 * c)))
    L = _line_pts(head, line)
    # lips colour
    upper = []
    lower = []
    for i in range(n + 1):
        t = i / n
        uu = -mu * 0.92 + 2 * mu * 0.92 * t
        c = (2 * t - 1) ** 2
        cup = 0.012 * (math.exp(-((t - 0.38) / 0.12) ** 2) + math.exp(-((t - 0.62) / 0.12) ** 2))
        upper.append((uu, my - curve * c - (0.055 * lipt) * (1 - c) ** 0.6 - cup * lipt, lp * (1 - 0.5 * c)))
        lower.append((uu, my - curve * c + (0.075 * lipt) * (1 - c) ** 0.7, lp * (1 - 0.5 * c)))
    U = _line_pts(head, upper)
    Lo = _line_pts(head, lower)
    lipcol = hexc(fp.get('lip', '#A25A4C'))
    um = poly(U + L[::-1])
    lm = poly(L + Lo[::-1])
    la = 0.75 if female else 0.4
    cv.multiply(blur(um, 0.25), mix(np.ones(3, np.float32), lipcol / hexc(fp['skin']).clip(0.2, 1), 1.0) * 0.92, la)
    cv.multiply(blur(lm, 0.35), mix(np.ones(3, np.float32), lipcol / hexc(fp['skin']).clip(0.2, 1), 0.8), la * 0.85)
    # lower lip highlight
    hx, hy = head.pt(-0.05, my + 0.04, lp * 1.2)
    cv.screen(ellipse(hx, hy, 0.09 * hu, 0.018 * hu), hexc('#F2D9C4'), 0.3 if female else 0.18)
    # mouth line
    w = [0.3 + 0.75 * (0.35 + 0.65 * math.sin(math.pi * i / n)) * (1.0 if i < n * 0.8 else 0.8) for i in range(n + 1)]
    w[0] = w[-1] = 0.35
    cv.paint(stroke(L, w), hexc('#3A1F17'), 0.85)
    # corner accents
    for t, s in ((0, -1), (1, 1)):
        p = L[0] if t == 0 else L[-1]
        cv.paint(ellipse(p[0], p[1] - 0.2, 0.6, 0.5), hexc('#4A2A1E'), 0.4)
    # shadow under lower lip
    sx, sy = head.pt(0.02, my + 0.13, 0.02 * hu)
    cv.multiply(ellipse(sx, sy, 0.1 * hu, 0.025 * hu), np.array([0.82, 0.74, 0.7], np.float32), 0.5)


def ear_anchor(head):
    """Screen position of the near ear's root (top, bottom)."""
    hu = head.hu
    w0, _, _, o0, _ = (float(v[0]) for v in head.profile(np.array([-0.05])))
    w1, _, _, o1, _ = (float(v[0]) for v in head.profile(np.array([0.42])))
    xt, yt, _ = head.local_to_screen(-w0 * 0.97, -0.1, o0 + 0.04 * hu)
    xb, yb, _ = head.local_to_screen(-w1 * 0.97, 0.42, o1 + 0.06 * hu)
    return (xt, yt), (xb, yb)


def draw_ear(cv, head, fp, rng, skin_hex, lit_level=0.75):
    hu = head.hu
    (tx, ty), (bx, by) = ear_anchor(head)
    reach = 0.21 * hu
    h = by - ty
    pts = [
        (tx + 0.02 * hu, ty + 0.06 * h),
        (tx - reach * 0.45, ty - 0.05 * h),
        (tx - reach * 0.95, ty + 0.12 * h),
        (tx - reach * 0.85, ty + 0.55 * h),
        (bx - reach * 0.45, by - 0.12 * h),
        (bx - reach * 0.2, by + 0.02 * h),
        (bx + 0.03 * hu, by - 0.06 * h),
    ]
    outline = catmull(pts, 8)
    shape = outline + [(bx + 0.06 * hu, by - 0.3 * h), (tx + 0.06 * hu, ty + 0.25 * h)]
    m = poly(shape)
    from portrait_raster import pillow
    l = pillow(m, 0.07 * hu, 1.0)
    deep, shade, base, lite = skin_palette(skin_hex)
    v = clamp01(l * lit_level * 1.15)
    c = mix(shade, base, v[..., None]) * np.array([1.03, 0.93, 0.9], np.float32)
    cv.paint(m, c)
    # helix inner fold and concha
    inner = catmull([(tx - reach * 0.2, ty + 0.16 * h), (tx - reach * 0.6, ty + 0.12 * h),
                     (tx - reach * 0.62, ty + 0.45 * h), (bx - reach * 0.3, by - 0.25 * h)], 6)
    cv.multiply(blur(poly(inner + [(tx + 0.0, ty + 0.55 * h)]), 0.6), shade / base.clip(0.2, 1), 0.85)
    cv.paint(stroke(inner, [0.25, 0.8, 0.9, 0.7, 0.4]), hexc('#5B3426'), 0.6)
    cv.paint(ink_outline(m, 0.55, rng, 0.3), INK, 0.8)
    return m


def draw_wrinkles(cv, head, fp, rng):
    age = fp.get('age', 0.0)
    if age <= 0.2:
        return
    col = hexc('#6A4232')
    # forehead lines
    for k in range(int(2 + age * 2)):
        yy = -0.38 - 0.085 * k
        pts = []
        for i in range(9):
            t = i / 8
            uu = -0.45 + 0.9 * t
            pts.append((uu, yy + 0.015 * math.sin(t * 6 + k) + 0.03 * (t - 0.5) ** 2, 0.03 * head.hu))
        P = _line_pts(head, pts)
        w = [0.45 * math.sin(math.pi * i / 8) * age + 0.05 for i in range(9)]
        cv.paint(stroke(P, w), col, 0.35 + 0.2 * age)
    # nasolabial lines
    nt, nw, my, mu = fp['nose_y'], fp['nose_w'], fp['mouth_y'], fp['mouth_u']
    for sgn in (-1, 1):
        pts = [(sgn * (nw + 0.06), nt + 0.04), (sgn * (nw + 0.12), (nt + my) * 0.5 + 0.02),
               (sgn * (mu + 0.08), my + 0.1)]
        P = _line_pts(head, pts, 0.03 * head.hu)
        P = catmull(P, 6)
        w = [0.7 * math.sin(math.pi * i / (len(P) - 1)) * age + 0.05 for i in range(len(P))]
        cv.paint(stroke(P, w), col, 0.45 + 0.2 * age)
    # mouth corner lines
    if age > 0.6:
        for sgn in (-1, 1):
            P = _line_pts(head, [(sgn * (mu + 0.02), my + 0.06), (sgn * (mu + 0.0), my + 0.2)], 0.02 * head.hu)
            cv.paint(stroke(P, [0.4, 0.1]), col, 0.35)
