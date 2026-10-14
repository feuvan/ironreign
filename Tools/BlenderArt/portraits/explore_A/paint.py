#!/usr/bin/env python3
"""Digital-painting finish for a rendered bust (system python3: numpy + scipy + Pillow).

    python3 paint.py <render_dir> <tag> <out_png_2x> [--bg warm|cool|jade|crimson] [--seed N]

Inputs (written by the Blender pass outputs): <tag>.png (beauty RGBA, 2x), <tag>_m_*.png masks
(skin, eyes, hair, metal, cloth, fur, orn, brow, alpha), <tag>_depth.png.

Pipeline (all at the 2x render size, then Lanczos to 1x):
 1. painted backdrop (umber/smoky ground, key-side glow, oriented brush mottling)
 2. figure over backdrop; silhouette edges broken by dry-brush noise; bust fades to dark below
 3. variable-radius *anisotropic Kuwahara* (structure-tensor ellipses, 8 sectors): small on
    skin, tight on eyes, larger on hair/costume, large on the backdrop and in deep shadow
 4. brush-stroke texture: line-integral convolution of noise along the image flow, applied as
    value modulation + a faint impasto relief lit from the upper left
 5. crisp eyes / brows / lips: detail restored from the render and unsharp-masked
 6. grade: warm/cool split toning, gentle S curve, saturation shaping, vignette
 7. canvas weave + paper grain
"""

import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi


def load(path, mode="RGBA"):
    im = Image.open(path)
    if mode == "L":
        return np.asarray(im.convert("L"), np.float32) / 255.0
    return np.asarray(im.convert(mode), np.float32) / 255.0


def save(img, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)).save(path)


def srgb_to_lin(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(x):
    x = np.clip(x, 0, None)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1 / 2.4) - 0.055)


def luma(img):
    return img[..., 0] * 0.2126 + img[..., 1] * 0.7152 + img[..., 2] * 0.0722


def smooth_noise(h, w, scale, rng, octaves=4, gain=0.55):
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    s = scale
    for _ in range(octaves):
        gh, gw = int(h / s) + 3, int(w / s) + 3
        g = rng.random((gh, gw)).astype(np.float32)
        up = ndi.zoom(g, (h / (gh - 3) * 1.0, w / (gw - 3) * 1.0), order=3)[:h, :w]
        out += amp * up
        tot += amp
        amp *= gain
        s /= 2.0
    return out / tot


# ----------------------------------------------------------------------------- structure tensor
def structure(lum, sigma_d=1.0, sigma_i=3.0):
    gx = ndi.sobel(ndi.gaussian_filter(lum, sigma_d), 1)
    gy = ndi.sobel(ndi.gaussian_filter(lum, sigma_d), 0)
    E = ndi.gaussian_filter(gx * gx, sigma_i)
    F = ndi.gaussian_filter(gx * gy, sigma_i)
    G = ndi.gaussian_filter(gy * gy, sigma_i)
    tr = E + G
    det = np.sqrt(np.maximum((E - G) ** 2 + 4 * F * F, 0))
    l1 = (tr + det) / 2
    l2 = (tr - det) / 2
    # eigenvector of the minor eigenvalue = edge tangent (flow direction)
    tx = l1 - E
    ty = -F
    n = np.hypot(tx, ty)
    bad = n < 1e-9
    tx = np.where(bad, 1.0, tx / np.maximum(n, 1e-9))
    ty = np.where(bad, 0.0, ty / np.maximum(n, 1e-9))
    A = np.where(l1 + l2 > 1e-9, (l1 - l2) / np.maximum(l1 + l2, 1e-9), 0.0)
    return tx, ty, A


# ---------------------------------------------------------------------- anisotropic Kuwahara
def kuwahara_aniso(img, radius, tx, ty, A, sectors=8, rings=(0.45, 1.0), q=8.0, alpha=1.0):
    """Generalised anisotropic Kuwahara with a per-pixel radius map.

    For each pixel an ellipse aligned with the flow (tx, ty) - long axis along the edge - is
    split into ``sectors``; each sector's gaussian-weighted mean/variance are estimated from
    samples on ``rings``; sectors are blended with weights 1/(1+sigma^q)."""
    H, W, C = img.shape
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    # ellipse axes: along flow a = r * (alpha + A)/alpha, across b = r * alpha/(alpha + A)
    sa = radius * np.clip((alpha + A) / alpha, 1.0, 2.2)
    sb = radius * np.clip(alpha / (alpha + A), 0.45, 1.0)
    acc = np.zeros((H, W, C), np.float32)
    wsum = np.zeros((H, W), np.float32)
    chans = [img[..., c] for c in range(C)]
    for k in range(sectors):
        m = np.zeros((H, W, C), np.float32)
        m2 = np.zeros((H, W), np.float32)
        ws = 0.0
        for rr in rings:
            for da in (-0.25, 0.25):
                ang = (k + 0.5 + da) * 2 * np.pi / sectors
                ca, sn = np.cos(ang) * rr, np.sin(ang) * rr
                # local ellipse coords -> image offsets
                ox = ca * sa * tx - sn * sb * ty
                oy = ca * sa * ty + sn * sb * tx
                wgt = np.exp(-2.0 * rr * rr) * (1.0 - 0.3 * abs(da))
                coords = [yy + oy, xx + ox]
                samp = np.stack([ndi.map_coordinates(ch, coords, order=1, mode="nearest") for ch in chans], -1)
                m += samp * wgt
                l = luma(samp) if C >= 3 else samp[..., 0]
                m2 += l * l * wgt
                ws += wgt
        # centre sample shared by all sectors
        m += img * 0.6
        lc = luma(img) if C >= 3 else img[..., 0]
        m2 += lc * lc * 0.6
        ws += 0.6
        m /= ws
        mean_l = luma(m) if C >= 3 else m[..., 0]
        var = np.maximum(m2 / ws - mean_l * mean_l, 0)
        w = 1.0 / (1.0 + (np.sqrt(var) * 40.0) ** q)
        acc += m * w[..., None]
        wsum += w
    return acc / np.maximum(wsum, 1e-8)[..., None]


# ------------------------------------------------------------------------------- brush texture
def lic(noise, tx, ty, length=12, step=1.0):
    """Line integral convolution of ``noise`` along the flow field (streaky strokes)."""
    H, W = noise.shape
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    acc = noise.copy()
    tot = np.ones_like(noise)
    for sgn in (1, -1):
        px, py = xx.copy(), yy.copy()
        dx, dy = tx * sgn, ty * sgn
        for i in range(length):
            px = px + dx * step
            py = py + dy * step
            v = ndi.map_coordinates(noise, [py, px], order=1, mode="reflect")
            w = 1.0 - i / length
            acc += v * w
            tot += w
            # follow the field
            ntx = ndi.map_coordinates(tx, [py, px], order=0, mode="nearest")
            nty = ndi.map_coordinates(ty, [py, px], order=0, mode="nearest")
            flip = (ntx * dx + nty * dy) < 0
            dx = np.where(flip, -ntx, ntx)
            dy = np.where(flip, -nty, nty)
    return acc / tot


def backdrop(h, w, rng, scheme="warm"):
    """Painted ground: dark umber with a lit haze behind the head on the key side."""
    schemes = {
        "warm": ((0.10, 0.075, 0.055), (0.42, 0.33, 0.24), (0.20, 0.17, 0.15)),
        "cool": ((0.06, 0.07, 0.08), (0.32, 0.33, 0.33), (0.13, 0.14, 0.16)),
        "jade": ((0.05, 0.075, 0.065), (0.30, 0.36, 0.30), (0.12, 0.15, 0.13)),
        "crimson": ((0.10, 0.04, 0.035), (0.42, 0.24, 0.17), (0.20, 0.10, 0.08)),
        "smoke": ((0.07, 0.065, 0.06), (0.36, 0.33, 0.29), (0.16, 0.15, 0.14)),
    }
    dark, lite, mid = (np.array(c, np.float32) for c in schemes.get(scheme, schemes["warm"]))
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    u, v = x / w, y / h
    glow = np.exp(-(((u - 0.36) / 0.38) ** 2 + ((v - 0.28) / 0.42) ** 2))
    n1 = smooth_noise(h, w, w * 0.45, rng, 4)
    n2 = smooth_noise(h, w, w * 0.12, rng, 3)
    g = np.clip(glow * (0.75 + 0.5 * (n1 - 0.5)), 0, 1)
    col = dark[None, None] + (lite - dark)[None, None] * g[..., None]
    col = col * (1 + 0.25 * (n2 - 0.5))[..., None]
    col = col + (mid - col) * (0.25 * smooth_noise(h, w, w * 0.25, rng, 2))[..., None]
    # darken toward the bottom and the right (away from the key)
    col *= (1 - 0.45 * np.clip(v - 0.55, 0, 1) / 0.45)[..., None]
    col *= (1 - 0.25 * np.clip(u - 0.6, 0, 1) / 0.4)[..., None]
    return np.clip(col, 0, 1)


def canvas(h, w, rng, period=3.2):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    weave = (np.sin(x * 2 * np.pi / period) * np.sin(y * 2 * np.pi / period * 1.1)) * 0.5
    fib = ndi.gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), 0.7)
    fib /= fib.std() + 1e-6
    big = smooth_noise(h, w, w * 0.05, rng, 3) - 0.5
    return weave * 0.5 + fib * 0.35 + big * 0.8


def joint_bilateral(img, guides, weight_mask, radius=3, sigma_s=2.0, sigma_r=0.12):
    """Cross-bilateral denoise guided by render passes (normal, albedo, depth) - stands in for
    the missing OpenImageDenoise.  ``guides``: list of (array (H,W,C), sigma)."""
    H, W, C = img.shape
    acc = np.zeros_like(img)
    wsum = np.zeros((H, W), np.float32)
    L0 = luma(img)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            ws = np.exp(-(dx * dx + dy * dy) / (2 * sigma_s ** 2))
            sh = np.roll(np.roll(img, dy, 0), dx, 1)
            w = np.full((H, W), ws, np.float32)
            for g, sg in guides:
                gs = np.roll(np.roll(g, dy, 0), dx, 1)
                d2 = ((gs - g) ** 2).sum(-1) if g.ndim == 3 else (gs - g) ** 2
                w *= np.exp(-d2 / (2 * sg * sg))
            dl = luma(sh) - L0
            w *= np.exp(-dl * dl / (2 * sigma_r ** 2))
            acc += sh * w[..., None]
            wsum += w
    out = acc / np.maximum(wsum, 1e-8)[..., None]
    return img + (out - img) * weight_mask[..., None]


def unsharp(img, sigma, amount):
    bl = ndi.gaussian_filter(img, (sigma, sigma, 0))
    return img + (img - bl) * amount


def finish(render_dir, tag, out2x, scheme="warm", seed=0, params=None):
    P = dict(r_skin=2.6, r_eye=1.2, r_hair=3.6, r_cloth=4.6, r_metal=3.8, r_bg=9.0, stroke=0.07,
             impasto=0.05, grain=0.035, sat=1.0, warm=0.035, cool=0.045, contrast=1.08,
             vignette=0.32, edge_break=1.0, fade_bottom=0.55, eye_detail=0.75, denoise=1.0,
             skin_stroke=0.15, bg_stroke=0.35)
    P.update(params or {})
    rng = np.random.default_rng(seed)
    base = load(os.path.join(render_dir, tag + "_raw.png"))
    H, W = base.shape[:2]

    def m(name):
        p = os.path.join(render_dir, "%s_m_%s0001.png" % (tag, name))
        return load(p, "L") if os.path.exists(p) else np.zeros((H, W), np.float32)
    alpha = base[..., 3]
    fg = base[..., :3]
    npath = os.path.join(render_dir, "%s_normal0001.png" % tag)
    apath = os.path.join(render_dir, "%s_albedo0001.png" % tag)
    if os.path.exists(npath) and os.path.exists(apath):
        nrm = load(npath, "RGB")
        alb = load(apath, "RGB")
        hm_ = load(os.path.join(render_dir, "%s_m_hair0001.png" % tag), "L")
        fm_ = load(os.path.join(render_dir, "%s_m_fur0001.png" % tag), "L")
        bm_ = load(os.path.join(render_dir, "%s_m_brow0001.png" % tag), "L")
        dmask = np.clip(alpha - np.clip(hm_ + fm_ + bm_ * 1.5, 0, 1) * 0.85, 0, 1) * P["denoise"]
        fg = joint_bilateral(fg, [(nrm, 0.08), (alb, 0.06)], dmask, radius=3, sigma_s=1.8, sigma_r=0.1)
    skin, eyes, hairm, metal, cloth = m("skin"), m("eyes"), m("hair"), m("metal"), m("cloth")
    fur, orn, brow = m("fur"), m("orn"), m("brow")
    # --- 1/2 backdrop + composite with broken edges
    bg = backdrop(H, W, rng, scheme)
    # unpremultiply-safe: Cycles PNG is straight alpha
    edge_noise = smooth_noise(H, W, 6.0, rng, 3)
    soft = ndi.gaussian_filter(alpha, 1.2)
    a = alpha.copy()
    band = (soft > 0.02) & (soft < 0.98)
    a = np.where(band, np.clip(soft + (edge_noise - 0.5) * 0.9 * P["edge_break"], 0, 1), alpha)
    # bust dissolves into the dark at the bottom of the frame (painted vignette)
    yy = np.mgrid[0:H, 0:W][0].astype(np.float32) / H
    strokes_v = smooth_noise(H, W, 14.0, rng, 3)
    fade = np.clip((yy - 0.80) / 0.2 + (strokes_v - 0.5) * 0.6, 0, 1) * P["fade_bottom"]
    a = a * (1 - fade)
    img = fg * a[..., None] + bg * (1 - a[..., None])
    # --- 3 Kuwahara with a per-pixel radius
    lum = luma(img)
    tx, ty, A = structure(lum, 1.0, 2.5 * W / 768)
    sc = W / 768.0
    # backdrop flow: broad diagonal strokes with a slow wander instead of noise-driven swirls
    wander = (smooth_noise(H, W, W * 0.3, rng, 2) - 0.5) * 1.6
    ang = np.radians(62.0) + wander
    bgw = np.clip(1 - ndi.gaussian_filter(a, 6.0) * 1.5, 0, 1)
    tx = tx * (1 - bgw) + np.cos(ang) * bgw
    ty = ty * (1 - bgw) - np.sin(ang) * bgw
    nn = np.hypot(tx, ty) + 1e-6
    tx, ty = tx / nn, ty / nn
    A = A * (1 - bgw) + 0.8 * bgw
    face_core = np.clip(skin + eyes, 0, 1)
    r = np.full((H, W), P["r_bg"], np.float32)
    fgm = np.clip(a, 0, 1)
    r = r * (1 - fgm) + fgm * P["r_cloth"]
    r = r * (1 - metal) + metal * P["r_metal"]
    r = r * (1 - hairm) + hairm * P["r_hair"]
    r = r * (1 - fur) + fur * P["r_hair"]
    r = r * (1 - skin) + skin * P["r_skin"]
    eyes_d = np.clip(ndi.gaussian_filter(ndi.maximum_filter(eyes, int(9 * sc)), 3 * sc) * 2.0, 0, 1)
    r = r * (1 - eyes_d) + eyes_d * P["r_eye"]
    # looser in deep shadow and toward the bottom of the frame
    dark = np.clip((0.12 - lum) / 0.12, 0, 1)
    r = r * (1 + 0.6 * dark * (1 - face_core)) * (1 + 0.5 * np.clip(yy - 0.75, 0, 1) / 0.25)
    r = ndi.gaussian_filter(r, 2.0) * sc
    kw = kuwahara_aniso(img, r, tx, ty, A)
    # --- 4 brush strokes (LIC) + impasto
    noise = rng.random((H, W)).astype(np.float32)
    noise = ndi.gaussian_filter(noise, 1.3 * sc)
    st = lic(noise, tx, ty, length=int(12 * sc) + 2)
    st = (st - st.mean()) / (st.std() + 1e-6)
    st_amt = P["stroke"] * (P["skin_stroke"] + (1 - P["skin_stroke"]) * (1 - np.clip(skin * 1.4, 0, 1)))
    st_amt = st_amt * (1 - bgw * (1 - P["bg_stroke"]))
    kl = luma(kw)
    kw = kw * (1 + st[..., None] * st_amt[..., None] * (0.4 + 0.6 * np.clip(kl * 3, 0, 1))[..., None])
    hx = ndi.sobel(st, 1)
    hy = ndi.sobel(st, 0)
    relief = (-hx * 0.7 - hy * 0.7) * 0.25  # light from the upper left
    kw = kw + relief[..., None] * P["impasto"] * (1 - 0.85 * skin)[..., None]
    # --- 5 crisp eyes / brows / lips: restore render detail and sharpen
    detail = np.clip(eyes_d * P["eye_detail"] + ndi.gaussian_filter(brow, 1.0) * 0.35, 0, 1)
    kw = kw * (1 - detail[..., None]) + img * detail[..., None]
    sharp_m = np.clip(eyes_d * 1.0 + brow * 0.6 + skin * 0.25, 0, 1)
    kw = kw + (unsharp(kw, 1.2 * sc, 0.8) - kw) * sharp_m[..., None]
    # --- 6 grade
    x = np.clip(kw, 0, 1)
    L = luma(x)
    # split toning: cool shadows, warm highlights
    sh = np.clip(1 - L / 0.45, 0, 1)[..., None]
    hi = np.clip((L - 0.45) / 0.55, 0, 1)[..., None]
    x = x + sh * np.array([-P["cool"] * 0.6, 0.0, P["cool"]], np.float32) * 0.6
    x = x + hi * np.array([P["warm"], P["warm"] * 0.35, -P["warm"] * 0.6], np.float32)
    # S curve around 0.42
    c = P["contrast"]
    x = np.clip(0.42 + (x - 0.42) * c, 0, 1)
    x = x + 0.06 * np.sin(np.clip(x, 0, 1) * np.pi) * (x - 0.42)
    # saturation: rich mids, muted darks
    L = luma(x)[..., None]
    satf = P["sat"] * (0.75 + 0.35 * np.clip(L * 2.2, 0, 1))
    x = L + (x - L) * satf
    # vignette (key side lighter)
    y2, x2 = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((x2 / W - 0.45) / 0.75) ** 2 + ((y2 / H - 0.40) / 0.8) ** 2)
    x = x * (1 - P["vignette"] * np.clip(d - 0.35, 0, 1) ** 1.5)[..., None]
    # --- 7 canvas
    cv = canvas(H, W, rng)
    x = x * (1 + cv[..., None] * P["grain"])
    return np.clip(x, 0, 1)


def downsample(img, size):
    out = []
    for c in range(3):
        ch = Image.fromarray((np.clip(img[..., c], 0, 1) * 255).astype(np.float32), mode="F")
        out.append(np.asarray(ch.resize(size, Image.LANCZOS), np.float32) / 255.0)
    return np.clip(np.stack(out, -1), 0, 1)


def main():
    a = sys.argv[1:]
    rdir, tag, out = a[0], a[1], a[2]
    scheme = a[a.index("--bg") + 1] if "--bg" in a else "warm"
    seed = int(a[a.index("--seed") + 1]) if "--seed" in a else 0
    params = {}
    if "--params" in a:
        import json
        params = json.loads(a[a.index("--params") + 1])
    import time
    t = time.time()
    img = finish(rdir, tag, out, scheme, seed, params)
    H, W = img.shape[:2]
    out = out[:-4] if out.endswith(".png") else out
    x1 = downsample(img, (W // 2, H // 2))
    save(x1, out + ".png")
    x2 = downsample(x1, (W // 4, H // 4))
    save(x2, out + "_192.png")
    save(img, out + "_full.png")
    print("[paint] %s %.1fs" % (tag, time.time() - t))


if __name__ == "__main__":
    main()
