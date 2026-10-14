"""Per-identity skin texture maps painted in numpy in the MakeHuman UV layout.

``make(b, idn, style)`` rasterises the head's rest face coordinates and region masks into UV
space, then paints albedo (sRGB), roughness and height (bump) maps:

* pigment: tone, multi-scale mottling, flush zones (cheeks, nose, ears), socket shading, beard
  shadow + stubble, scalp/brow underlay in the hair colour, lips, make-up, age spots
* relief: pores, forehead lines, glabella frown lines, crow's feet, under-eye arcs, nasolabial
  folds, marionette lines, lip striations, neck rings, optional scars
Everything is placed with :mod:`regions` (face frame landmarks) so it fits every face.
"""

import time

import numpy as np

import regions as R
import texgen as T

MASK_KEYS = ["m_lip_u", "m_lip_l", "m_brow", "m_nose", "m_cheek", "m_bag", "m_ear", "m_chin",
             "m_neck", "m_laugh", "m_lids"]


def _tris(b):
    base = b["base"]
    tris_uv, tris_v = [], []
    for i in b["keep"]:
        f = base.faces[i]
        fu = base.face_uvs[i]
        for a, c in ((1, 2), (2, 3)) if len(f) == 4 else ((1, 2),):
            tris_v.append((f[0], f[a], f[c]))
            tris_uv.append((fu[0], fu[a], fu[c]))
    return np.array(tris_v), np.array(tris_uv)


def texel_map(b, res):
    """Identity-independent UV raster cache: for every covered texel the triangle index and
    barycentric weights (padded a few texels past island borders)."""
    import os
    import mh
    cp = os.path.join(mh.CACHE, "texelmap_%d_%d.npz" % (res, len(b["keep"])))
    if os.path.exists(cp):
        d = np.load(cp)
        return d["tri"], d["bary"], d["yy"], d["xx"]
    tv, tu = _tris(b)
    uv = b["base"].uvs[tu]
    T_ = len(tv)
    ids = np.zeros((T_, 3, 4), np.float32)
    ids[:, :, 0] = np.arange(T_)[:, None]
    ids[:, 0, 1] = 1
    ids[:, 1, 2] = 1
    ids[:, 2, 3] = 1
    img, cov = T.rasterize(uv, ids, res, 4)
    # triangle id must not be interpolated: recover it from the corner-constant channel
    img[..., 0] = np.round(img[..., 0])
    img, cov = T.pad(img, cov, 4)
    yy, xx = np.where(cov)
    tri = np.clip(np.round(img[yy, xx, 0]).astype(np.int32), 0, T_ - 1)
    bary = img[yy, xx, 1:4]
    bary = bary / np.maximum(bary.sum(1, keepdims=True), 1e-6)
    np.savez(cp, tri=tri, bary=bary.astype(np.float32), yy=yy.astype(np.int32), xx=xx.astype(np.int32))
    return tri, bary, yy, xx


def _line_dist(px, py, ax, ay, bx, by):
    """Distance from points to segment a-b and the param t."""
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy + 1e-12
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / L2, 0, 1)
    qx, qy = ax + t * dx, ay + t * dy
    return np.sqrt((px - qx) ** 2 + (py - qy) ** 2), t


def _srgb(c):
    return np.array(c, np.float32)


def make(b, idn, style, res=2048, seed=0):
    _ta = time.time()
    rng = np.random.default_rng(seed + 101)
    tri, bary, yy, xx = texel_map(b, res)
    tv, _ = _tris(b)
    fc = b["fc"]
    masks = b["masks"]
    vals = np.concatenate([fc[:, :3]] + [masks[k][:len(fc), None] for k in MASK_KEYS], 1).astype(np.float32)
    corner = tv[tri]  # (n,3) vertex ids
    P = (vals[corner] * bary[..., None]).sum(1)
    _tb = time.time()
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    ax = np.abs(x)
    M = {k: P[:, 3 + i] for i, k in enumerate(MASK_KEYS)}
    F = b["F"]
    n = len(x)
    old = float(np.clip((idn.age - 30.0) / 45.0, 0, 1))
    male = not idn.female
    fcp = np.stack([x, y, z], 1)

    def nz(cell, octaves=1, gain=0.5):
        # value noise in texel space (sampled at the covered texels)
        return T.noise_at(xx.astype(np.float32), yy.astype(np.float32), cell, rng, octaves, gain)

    # ------------------------------------------------------------------ pigment
    light = _srgb((0.87, 0.70, 0.58))
    dark = _srgb((0.68, 0.47, 0.35))
    tone = light + (dark - light) * idn.skin_tone
    col = np.tile(tone, (n, 1))
    m1 = nz(90.0, 3) - 0.5
    m2 = nz(14.0, 2) - 0.5
    m3 = nz(3.0, 1) - 0.5
    col *= (1.0 + 0.10 * m1 + 0.05 * m2 + 0.025 * m3)[:, None]
    hue = nz(60.0, 2) - 0.5
    col += np.outer(hue, np.array([0.03, -0.004, -0.03], np.float32))
    fore = R.sstep(F.brow_y + 0.1, F.brow_y + 0.6, y) * R.sstep(-1.2, -0.4, z)
    col = T.mix(col, col * _srgb((1.03, 1.02, 0.97)), fore * 0.6)
    # flush
    red = np.maximum.reduce([M["m_cheek"] * 0.85, M["m_nose"] * 0.8, M["m_ear"] * 0.9, M["m_chin"] * 0.35])
    red = red * (0.22 + 0.35 * idn.skin_red) * (0.8 + 0.4 * (nz(30.0, 2)))
    col = T.mix(col, _srgb((0.80, 0.42, 0.36)), np.clip(red, 0, 1))
    # eye sockets: upper crease shadow + under-eye darkness (tear trough)
    dsock = np.sqrt((ax - 0.53) ** 2 + ((y - 0.02) * 1.15) ** 2)
    sock = R.sstep(0.48, 0.2, dsock) * R.sstep(-1.0, -0.3, z)
    tear = R.sstep(0.12, 0.0, np.abs(y - (F.lid_bot - 0.12 + 0.15 * (ax - F.eye_in)))) * R.sstep(F.eye_in - 0.05, F.eye_in + 0.1, ax) * R.sstep(F.eye_out + 0.05, F.eye_out - 0.15, ax)
    col = T.mix(col, col * _srgb((0.80, 0.70, 0.70)), np.clip(sock * (0.35 + 0.3 * old) + tear * (0.25 + 0.35 * old), 0, 1))
    # lips
    lip = np.clip(np.maximum(M["m_lip_u"], M["m_lip_l"]) * 1.5, 0, 1)
    lip = R.sstep(0.45, 0.85, lip)
    if idn.female and idn.makeup > 0:
        lipc = _srgb((0.70, 0.38, 0.36)) + (_srgb((0.66, 0.12, 0.14)) - _srgb((0.70, 0.38, 0.36))) * idn.makeup
    else:
        lipc = _srgb((0.66, 0.38, 0.33)) * (1.0 - 0.1 * old)
    col = T.mix(col, lipc * (0.92 + 0.16 * nz(4.0, 1))[:, None], lip * 0.9)
    # mouth line (between the lips) darker
    ml = R.sstep(0.03, 0.0, np.abs(y - F.mouth_y)) * (1.0 - R.sstep(F.mouth_w - 0.05, F.mouth_w + 0.03, ax))
    col = T.mix(col, col * 0.45, ml * 0.8)
    # hair underlay on the scalp and brows (so gaps between strands never show bare skin)
    hair_rgb = _srgb(style.get("hair_rgb", (0.10, 0.08, 0.07)))
    if style.get("scalp", True):
        sc = R.scalp(fcp, F, style.get("recede", 0.0), soft=4.0)
        shaved = style.get("shaved", 0.0)
        col = T.mix(col, hair_rgb if not shaved else col * _srgb((0.78, 0.76, 0.78)),
                    sc * (0.85 if not shaved else 0.6))
    bd, _, _ = R.brow(fcp, F, **style.get("brow", {}))
    col = T.mix(col, T.mix(col, hair_rgb, 0.55), np.clip(bd * 1.2, 0, 1) * 0.6)
    # beard shadow + stubble on shaved male skin; beard underlay where a beard grows
    if male:
        full = {"mustache": 1, "chin": 1, "cheeks": 1, "jaw": 1, "neck": 0.7, "sideburns": 1, "soul": 1,
                "tails": 1}
        shadow = R.beard(fcp, F, full)
        stub = R.sstep(0.62, 0.8, nz(1.2, 1)) * shadow
        col = T.mix(col, col * _srgb((0.80, 0.80, 0.84)), shadow * style.get("stubble", 0.35))
        col = T.mix(col, hair_rgb, stub * style.get("stubble", 0.35) * 0.5)
        bstyle = style.get("beard")
        if bstyle:
            bden = R.beard(fcp, F, bstyle)
            col = T.mix(col, T.mix(col, _srgb(style.get("beard_rgb", hair_rgb)), 0.6), bden * 0.75)
    # make-up: blush, eye shadow, powder, forehead ornament (huadian)
    if idn.female and idn.makeup > 0:
        mk = idn.makeup
        col = T.mix(col, _srgb((0.92, 0.80, 0.74)), 0.22 * mk)
        bl = M["m_cheek"] * R.sstep(-0.8, -0.2, z)
        col = T.mix(col, _srgb((0.88, 0.48, 0.48)), bl * 0.38 * mk)
        es = R.sstep(F.lid_top - 0.04, F.lid_top + 0.04, y) * R.sstep(F.brow_y + 0.05, F.lid_top + 0.1, y)
        es *= R.sstep(F.eye_in - 0.05, F.eye_in + 0.15, ax) * R.sstep(F.eye_out + 0.25, F.eye_out + 0.02, ax)
        es2 = R.sstep(0.12, 0.0, np.abs(y - (F.lid_top + 0.02))) * R.sstep(F.eye_out - 0.25, F.eye_out + 0.08, ax) * R.sstep(F.eye_out + 0.22, F.eye_out + 0.05, ax)
        col = T.mix(col, _srgb((0.78, 0.36, 0.32)), np.clip(es * 0.5 + es2 * 0.4, 0, 1) * mk)
        # liner flick at the outer corner
        if style.get("huadian", False):
            hd = R.sstep(0.035, 0.02, np.sqrt((x * 1.5) ** 2 + (y - (F.brow_y + 0.12)) ** 2))
            hd = np.maximum(hd, R.sstep(0.02, 0.008, np.abs(x)) * R.sstep(0.09, 0.07, np.abs(y - (F.brow_y + 0.18))))
            col = T.mix(col, _srgb((0.62, 0.10, 0.10)), hd * 0.9)
    # age spots and weathering
    if old > 0.3:
        sp = R.sstep(0.78, 0.86, nz(6.0, 1)) * R.sstep(0.4, 0.7, nz(80.0, 1))
        col = T.mix(col, col * _srgb((0.78, 0.68, 0.60)), sp * old * 0.8)
    # ------------------------------------------------------------------ relief (height)
    h = np.zeros(n, np.float32)
    pores = (nz(1.0, 1) - 0.5) * 0.6 + (nz(2.5, 1) - 0.5) * 0.4
    pore_amt = 0.25 + 0.5 * np.maximum(M["m_nose"], M["m_cheek"]) * (1 - lip)
    h += pores * pore_amt * (0.5 + 0.5 * old)
    h += (nz(12.0, 2) - 0.5) * 0.35
    wr = np.zeros(n, np.float32)
    weather = style.get("weather", 0.0)
    age_w = np.clip(old * 1.2 + weather * 0.4, 0, 1.3)
    exr = {"stern": 0.6, "fierce": 1.0, "weary": 0.5, "scheming": 0.3}.get(idn.expression, 0.0)
    rr = np.random.default_rng(idn.seed * 31 + 7)
    fi = np.where((z > -1.5) & (y > F.chin_y - 1.8) & (y < F.crown_y + 0.1))[0]
    X_, Y_, Z_, AX_ = x, y, z, ax
    x, y, z, ax = x[fi], y[fi], z[fi], ax[fi]
    lip_f = lip[fi]
    wr_f = np.zeros(len(fi), np.float32)
    h_f = np.zeros(len(fi), np.float32)
    xxf, yyf = xx[fi].astype(np.float32), yy[fi].astype(np.float32)

    def nzf(cell, octaves=1, gain=0.5):
        return T.noise_at(xxf, yyf, cell, rng, octaves, gain)

    # forehead lines
    nf = 3 + int(old * 3)
    for k in range(nf):
        yk = F.brow_y + 0.30 + k * (0.12 + 0.02 * rr.random()) + 0.02 * rr.standard_normal()
        amp = (0.5 + 0.5 * rr.random()) * age_w
        ext = 0.45 + 0.35 * rr.random()
        wav = 0.025 * np.sin(x * (2.0 + rr.random() * 2.0) + rr.random() * 6) + 0.012 * (nzf(25.0, 1) - 0.5) + 0.05 * (x * x)
        d = np.abs(y - (yk + wav))
        w = 0.012 + 0.012 * old
        line = np.exp(-(d / w) ** 2) * R.sstep(ext, ext - 0.25, ax) * R.sstep(0.25, 0.6, nzf(18.0, 1) + 0.3)
        wr_f += line * amp * R.sstep(-0.9, -0.4, z)
    # glabella frown lines
    for s in (-1, 1):
        gx = s * (0.07 + 0.03 * rr.random())
        d, t = _line_dist(x, y, gx, F.brow_y - 0.06, gx + s * 0.03, F.brow_y + 0.28)
        wr_f += np.exp(-(d / 0.012) ** 2) * (0.3 * old + 0.6 * exr) * np.clip(np.sin(np.pi * t), 0, 1)
    # crow's feet
    for s in (-1, 1):
        ox, oy = s * (F.eye_out + 0.05), 0.0
        for k in range(3 + int(old * 3)):
            ang = np.radians(-38 + k * 15 + rr.standard_normal() * 5)
            L = 0.16 + 0.12 * rr.random()
            ex_, ey_ = ox + s * np.cos(ang) * L, oy + np.sin(ang) * L
            d, t = _line_dist(x, y, ox + s * 0.02 * np.cos(ang), oy, ex_, ey_)
            wr_f += np.exp(-(d / 0.010) ** 2) * np.clip(np.sin(np.pi * np.clip(t, 0, 1)), 0, 1) ** 0.7 * age_w * 0.8
    # under-eye arcs (bags)
    for s in (-1, 1):
        cx = s * 0.53
        for k, rad in enumerate((0.26 + 0.02 * old, 0.34 + 0.03 * old)):
            dd = np.sqrt((x - cx) ** 2 + ((y - 0.05) * 1.1) ** 2)
            arc = np.exp(-((dd - rad) / 0.012) ** 2) * R.sstep(-0.02, -0.1, y - 0.0) * R.sstep(F.eye_in - 0.05, F.eye_in + 0.05, ax) * R.sstep(F.eye_out + 0.1, F.eye_out - 0.05, ax)
            wr_f += arc * age_w * (0.7 if k == 0 else 0.4)
    # nasolabial folds (crease + cheek bulge highlight)
    for s in (-1, 1):
        a = (s * (F.nose_w + 0.06), F.nose_y + 0.06)
        c2 = (s * (F.mouth_w + 0.13), F.mouth_y - 0.12)
        mid = (s * (F.nose_w + 0.16), (a[1] + c2[1]) / 2)
        d1, t1 = _line_dist(x, y, a[0], a[1], mid[0], mid[1])
        d2, t2 = _line_dist(x, y, mid[0], mid[1], c2[0], c2[1])
        d = np.minimum(d1, d2)
        crease = np.exp(-(d / (0.016 + 0.01 * old)) ** 2)
        side = R.sstep(0.0, 0.08, (ax - (np.abs(a[0]) + (np.abs(c2[0]) - np.abs(a[0])) * R.sstep(a[1], c2[1], y))))
        bulge = side * np.exp(-(d / 0.09) ** 2)
        amt = 0.35 + 0.8 * old + 0.2 * (1 if male else 0)
        if idn.female:
            amt *= 0.45
        wr_f += crease * amt
        h_f += bulge * amt * 0.25 * R.sstep(F.nose_y + 0.1, F.nose_y - 0.05, y)
        if old > 0.35:
            d3, t3 = _line_dist(x, y, s * (F.mouth_w + 0.02), F.mouth_y - 0.05, s * (F.mouth_w + 0.08), F.chin_y + 0.12)
            wr_f += np.exp(-(d3 / 0.016) ** 2) * (old - 0.3) * 1.2
    # lips: vertical striations; perioral lines for the old
    h_f += lip_f * (np.sin(x * 260.0 + (nzf(6.0, 1) - 0.5) * 3) * 0.5) * 0.25
    if old > 0.4:
        per = R.sstep(F.lip_top + 0.12, F.lip_top + 0.02, y) * R.sstep(F.lip_top - 0.02, F.lip_top + 0.03, y) * (1 - R.sstep(F.mouth_w - 0.05, F.mouth_w + 0.05, ax))
        wr_f += per * R.sstep(0.6, 0.9, np.abs(np.sin(x * 70 + nzf(5.0, 1) * 4))) * old * 0.6
    # neck rings
    for k, yo in enumerate((0.75, 1.05, 1.4)):
        d = np.abs(y - (F.chin_y - yo + 0.05 * np.sin(x * 2)))
        wr_f += np.exp(-(d / 0.02) ** 2) * R.sstep(-1.6, -0.9, z) * (0.2 + old * 0.8) * 0.6
    # scars
    for sc_ in style.get("scars", []):
        (x0, y0), (x1, y1) = sc_
        d, t = _line_dist(x, y, x0, y0, x1, y1)
        s_ = np.exp(-(d / 0.012) ** 2) * np.clip(np.sin(np.pi * t), 0, 1) ** 0.5 * R.sstep(-1.0, -0.4, z)
        h_f += s_ * 0.5
        col[fi] = T.mix(col[fi], col[fi] * _srgb((1.05, 0.88, 0.86)), s_ * 0.6)
    x, y, z, ax = X_, Y_, Z_, AX_
    wr[fi] += wr_f
    h[fi] += h_f
    h -= wr * 1.0
    col = T.mix(col, col * _srgb((0.74, 0.62, 0.58)), np.clip(wr * 0.55, 0, 0.6))
    # ------------------------------------------------------------------ roughness
    tz = np.maximum(M["m_nose"], fore * 0.8)
    rough = 0.50 + 0.06 * old - 0.13 * tz - (0.22 if idn.female and idn.makeup > 0 else 0.16) * lip
    rough += (nz(20.0, 2) - 0.5) * 0.12 + np.clip(wr, 0, 1) * 0.1
    if style.get("scalp", True):
        rough = T.mix(rough[:, None], np.full((n, 1), 0.7, np.float32), R.scalp(fcp, F, style.get("recede", 0.0))[:, None] * 0.8)[:, 0]
    # ------------------------------------------------------------------ scatter back into images
    A = np.zeros((res, res, 4), np.float32)
    A[..., :3] = tone
    A[..., 3] = 1
    A[yy, xx, :3] = np.clip(col, 0, 1)
    Rg = np.full((res, res), 0.5, np.float32)
    Rg[yy, xx] = np.clip(rough, 0.15, 0.9)
    Hh = np.full((res, res), 0.5, np.float32)
    Hh[yy, xx] = 0.5 + 0.5 * np.clip(h, -1, 1)
    _tc = time.time()
    print("[skinmaps] raster %.2fs paint %.2fs (%d texels)" % (_tb - _ta, _tc - _tb, n))
    return A, Rg, Hh


def to_bpy(name, arr, colorspace="sRGB", float_buffer=False):
    """numpy (h,w[,4]) -> packed bpy image.  The colour space is set *before* the pixels: changing
    it afterwards reloads a generated image and silently blanks it."""
    import bpy
    h, w = arr.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=False, float_buffer=float_buffer)
    img.colorspace_settings.name = colorspace
    if arr.ndim == 2:
        arr = np.dstack([arr, arr, arr, np.ones_like(arr)])
    img.pixels.foreach_set(np.ascontiguousarray(arr[::-1]).ravel().astype(np.float32))
    img.update()
    return img
