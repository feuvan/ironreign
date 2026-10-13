"""Post-processing: Blender compositor graphs + numpy/Pillow image helpers.

Two halves:

1. **Compositor** (needs ``bpy``; functions prefixed ``comp_``): build the painterly chain that runs
   inside the render -  Render Layers -> [over background] -> Kuwahara (anisotropic, brush-like)
   -> mix with the clean render -> saturation/colour balance -> ink pass on top -> Composite.
2. **Image helpers** (numpy + Pillow only, importable from the system ``python3`` as well):
   supersample downsampling with premultiplied alpha, alpha clean-up/edge bleed, paper grain,
   colour grading, hexagon masks, 9-slice previews, contact sheets.

Image convention for the numpy helpers: ``float32`` arrays ``H x W x 4``, **sRGB-encoded**,
**straight** (un-premultiplied) alpha, values 0..1.  :func:`load` / :func:`save` convert.

Standard finishing recipe (what the style frames do)::

    img = post.load(raw_png)                       # 2x/4x render, compositor already painted it
    img = post.downsample(img, factor=ss)          # Lanczos, premultiplied
    img = post.grade(img, saturation=0.92, warmth=0.03)
    img = post.apply_paper(img, post.paper_texture(w, h, seed), strength=0.06)
    img = post.alpha_cleanup(img)                  # sprites: kill dust, bleed edge colour
    post.save(img, final_png)
"""

import math
import os

import numpy as np

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:  # pragma: no cover - Blender without python3-pil
    Image = None


# =============================================================================================
# compositor (bpy)
# =============================================================================================
def comp_reset(scene=None):
    """Enable compositing nodes and clear the tree. Returns (tree, render_layers, composite)."""
    import bpy
    sc = scene or bpy.context.scene
    sc.use_nodes = True
    sc.render.use_compositing = True
    nt = sc.node_tree
    nt.nodes.clear()
    rl = nt.nodes.new("CompositorNodeRLayers")
    comp = nt.nodes.new("CompositorNodeComposite")
    comp.use_alpha = True
    return nt, rl, comp


def comp_painterly(size=6, variation="ANISOTROPIC", uniformity=4, sharpness=0.6, eccentricity=1.0,
                   amount=1.0, saturation=1.0, value=1.0, background=None, lift=None, gamma=None,
                   gain=None, ink=True, ink_opacity=1.0, blur_before=0.0, scene=None):
    """Build the standard painterly compositor chain (see module doc). Returns a dict of nodes.

    size          Kuwahara radius in *render* pixels (scale with supersampling; STYLE.md table)
    amount        0..1 mix of the painted result over the clean render (detail retention)
    background    None (keep alpha), an RGBA tuple (linear), or a path to an image placed under
                  the render (portrait paper backgrounds); its size should match the render
    lift/gamma/gain  optional Color Balance (LGG) RGB triples, e.g. warm shadows / cool lights
    ink           overlay the Freestyle pass (requires ``ink.enable(as_pass=True)``)
    blur_before   small pre-blur (px) that removes residual Cycles noise before the Kuwahara
    """
    import bpy
    sc = scene or bpy.context.scene
    nt, rl, comp = comp_reset(sc)
    L = nt.links
    cur = rl.outputs["Image"]
    nodes = {"rl": rl, "composite": comp}
    if background is not None:
        if isinstance(background, str):
            img = bpy.data.images.load(background, check_existing=True)
            bg = nt.nodes.new("CompositorNodeImage")
            bg.image = img
            bgs = bg.outputs["Image"]
            sc_node = nt.nodes.new("CompositorNodeScale")
            sc_node.space = "RENDER_SIZE"
            sc_node.frame_method = "STRETCH"
            L.new(bgs, sc_node.inputs["Image"])
            bgs = sc_node.outputs[0]
        else:
            rgb = nt.nodes.new("CompositorNodeRGB")
            rgb.outputs[0].default_value = tuple(background)
            bgs = rgb.outputs[0]
        ao = nt.nodes.new("CompositorNodeAlphaOver")
        L.new(bgs, ao.inputs[1])
        L.new(cur, ao.inputs[2])
        cur = ao.outputs[0]
        nodes["background"] = ao
    clean = cur
    if blur_before > 0:
        b = nt.nodes.new("CompositorNodeBilateralblur")
        b.iterations = 1
        b.sigma_color = 0.15
        b.sigma_space = blur_before
        L.new(cur, b.inputs["Image"])
        L.new(cur, b.inputs["Determinator"])
        cur = b.outputs[0]
    if size > 0:
        k = nt.nodes.new("CompositorNodeKuwahara")
        k.variation = variation
        k.size = int(size)
        if variation == "ANISOTROPIC":
            k.uniformity = int(uniformity)
            k.sharpness = sharpness
            k.eccentricity = eccentricity
        L.new(cur, k.inputs[0])
        cur = k.outputs[0]
        nodes["kuwahara"] = k
        if amount < 1.0:
            mx = nt.nodes.new("CompositorNodeMixRGB")
            mx.blend_type = "MIX"
            mx.use_alpha = False
            mx.inputs[0].default_value = amount
            L.new(clean, mx.inputs[1])
            L.new(cur, mx.inputs[2])
            # keep the clean alpha (MixRGB outputs input-1 alpha)
            cur = mx.outputs[0]
            nodes["mix"] = mx
    if saturation != 1.0 or value != 1.0:
        hs = nt.nodes.new("CompositorNodeHueSat")
        hs.inputs["Saturation"].default_value = saturation
        hs.inputs["Value"].default_value = value
        L.new(cur, hs.inputs["Image"])
        cur = hs.outputs[0]
    if lift or gamma or gain:
        cb = nt.nodes.new("CompositorNodeColorBalance")
        cb.correction_method = "LIFT_GAMMA_GAIN"
        if lift:
            cb.lift = lift
        if gamma:
            cb.gamma = gamma
        if gain:
            cb.gain = gain
        L.new(cur, cb.inputs["Image"])
        cur = cb.outputs[0]
    if ink and "Freestyle" in rl.outputs and rl.outputs["Freestyle"].enabled:
        ao = nt.nodes.new("CompositorNodeAlphaOver")
        ao.inputs[0].default_value = ink_opacity
        L.new(cur, ao.inputs[1])
        L.new(rl.outputs["Freestyle"], ao.inputs[2])
        cur = ao.outputs[0]
        nodes["ink"] = ao
    L.new(cur, comp.inputs["Image"])
    nodes["out"] = cur
    return nodes


def comp_outputs(base_dir, sockets, scene=None, depth="8"):
    """Extra File Output node writing ``{name: socket}`` as RGBA PNGs into ``base_dir``.

    Files are named ``<name>0001.png`` (Blender appends the frame); use :func:`pass_path`.
    """
    import bpy
    sc = scene or bpy.context.scene
    nt = sc.node_tree
    fo = nt.nodes.new("CompositorNodeOutputFile")
    fo.base_path = base_dir
    fo.format.file_format = "PNG"
    fo.format.color_mode = "RGBA"
    fo.format.color_depth = depth
    fo.file_slots.clear()
    for name, sock in sockets.items():
        fo.file_slots.new(name)
        nt.links.new(sock, fo.inputs[name])
    return fo


def pass_path(base_dir, name, frame=1):
    return os.path.join(base_dir, "%s%04d.png" % (name, frame))


# =============================================================================================
# image I/O and conversions (numpy / Pillow)
# =============================================================================================
def load(path):
    """PNG/any -> float32 RGBA (sRGB, straight alpha).

    Intermediates are written as 8-bit PNGs on purpose: supersampling + Lanczos downsampling
    removes banding, and Pillow cannot read 16-bit RGBA PNGs at full precision anyway.
    """
    im = Image.open(path).convert("RGBA")
    return np.asarray(im, dtype=np.float32) / 255.0


def save(img, path, opaque=False):
    """float RGBA -> 8-bit PNG (RGB when ``opaque``). Creates folders."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    a = np.clip(img, 0.0, 1.0)
    a8 = (a * 255.0 + 0.5).astype(np.uint8)
    if opaque:
        Image.fromarray(a8[..., :3], "RGB").save(path, optimize=True)
    else:
        Image.fromarray(a8, "RGBA").save(path, optimize=True)
    return path


def to_pil(img):
    return Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")


def from_pil(im):
    return np.asarray(im.convert("RGBA"), dtype=np.float32) / 255.0


def srgb_to_linear(x):
    x = np.asarray(x, dtype=np.float32)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(x):
    x = np.clip(np.asarray(x, dtype=np.float32), 0, None)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def premultiply(img):
    out = img.copy()
    out[..., :3] *= out[..., 3:4]
    return out


def unpremultiply(img, eps=1e-5):
    out = img.copy()
    a = out[..., 3:4]
    out[..., :3] = np.where(a > eps, out[..., :3] / np.maximum(a, eps), 0.0)
    return out


def solid(w, h, color, alpha=1.0):
    """Solid image; ``color`` = '#hex' / palette token / sRGB triple."""
    from . import palette
    c = palette.srgb(color) if isinstance(color, str) else color
    img = np.zeros((h, w, 4), np.float32)
    img[..., :3] = c
    img[..., 3] = alpha
    return img


# =============================================================================================
# resampling
# =============================================================================================
def _resize_channels(arr, size, method):
    out = []
    for c in range(arr.shape[2]):
        im = Image.fromarray(arr[..., c].astype(np.float32), "F")
        out.append(np.asarray(im.resize(size, method), dtype=np.float32))
    return np.dstack(out)


def resize(img, size, method="lanczos"):
    """Resize RGBA (premultiplied internally so transparent pixels never bleed dark)."""
    m = {"lanczos": Image.LANCZOS, "bicubic": Image.BICUBIC, "bilinear": Image.BILINEAR,
         "box": Image.BOX, "nearest": Image.NEAREST}[method]
    pm = premultiply(img)
    out = _resize_channels(pm, size, m)
    out = np.clip(out, 0.0, 1.0)
    return unpremultiply(out)


def downsample(img, factor=2, method="lanczos"):
    """Supersampled render -> target size (integer or float ``factor``)."""
    h, w = img.shape[:2]
    return resize(img, (int(round(w / factor)), int(round(h / factor))), method)


def gaussian(arr, sigma):
    """Separable gaussian blur of a 2D or HxWxC float array (numpy only, edge-clamped)."""
    if sigma <= 0:
        return arr.astype(np.float32)
    r = max(1, int(math.ceil(sigma * 3)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2).astype(np.float32)
    k /= k.sum()
    a = arr.astype(np.float32)
    for axis in (0, 1):
        pad = [(0, 0)] * a.ndim
        pad[axis] = (r, r)
        p = np.pad(a, pad, mode="edge")
        acc = np.zeros_like(a)
        n = a.shape[axis]
        for i, w in enumerate(k):
            sl = [slice(None)] * a.ndim
            sl[axis] = slice(i, i + n)
            acc += w * p[tuple(sl)]
        a = acc
    return a


def blur(img, radius):
    """Gaussian blur of an RGBA image (premultiplied so edges stay clean)."""
    return unpremultiply(gaussian(premultiply(img), radius))


def unsharp(img, radius=1.0, amount=0.35, threshold=0.0):
    """Unsharp mask on colour (crisp eyes / edges after downsampling)."""
    b = blur(img, radius)
    out = img.copy()
    d = img[..., :3] - b[..., :3]
    if threshold > 0:
        d = np.where(np.abs(d) > threshold, d, 0)
    out[..., :3] = np.clip(img[..., :3] + amount * d, 0, 1)
    return out


# =============================================================================================
# alpha
# =============================================================================================
def alpha_cleanup(img, lo=0.03, hi=0.97, bleed=4):
    """Make sprite alpha engine-friendly.

    * alpha < ``lo`` -> 0 (removes dust/fireflies around the sprite), alpha > ``hi`` -> 1
    * colour of fully transparent pixels is filled with the nearest opaque colour (``bleed``
      iterations of dilation) so bilinear filtering in Slate never pulls in black fringes.
    """
    out = img.copy()
    a = out[..., 3]
    a = np.where(a < lo, 0.0, a)
    a = np.where(a > hi, 1.0, a)
    out[..., 3] = a
    rgb = out[..., :3].copy()
    known = a > 0.0
    for _ in range(bleed):
        acc = np.zeros_like(rgb)
        cnt = np.zeros(a.shape, np.float32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                sk = np.roll(np.roll(known, dy, 0), dx, 1)
                sr = np.roll(np.roll(rgb, dy, 0), dx, 1)
                acc += sr * sk[..., None]
                cnt += sk
        grow = (~known) & (cnt > 0)
        rgb[grow] = acc[grow] / cnt[grow][:, None]
        known = known | grow
    out[..., :3] = rgb
    return out


def drop_shadow(img, offset=(1.5, 1.0), blur_px=1.2, opacity=0.35, color="#1B1712",
                squash=1.0):
    """Soft ground shadow under a sprite (light from the top-left -> shadow to the bottom-right).

    ``squash`` < 1 flattens the shadow vertically towards the sprite bottom (contact shadow look).
    The sprite is composited over its own shadow; returns the new RGBA image.
    """
    from . import palette
    h, w = img.shape[:2]
    a = img[..., 3].copy()
    if squash != 1.0:
        bb = bbox(img)
        if bb is not None:
            y1 = bb[3]
            ys = np.arange(h, dtype=np.float32)
            src = y1 - (y1 - ys) / squash
            src = np.clip(src, 0, h - 1)
            i0 = np.floor(src).astype(int)
            i1 = np.minimum(i0 + 1, h - 1)
            f = (src - i0)[:, None]
            a = a[i0] * (1 - f) + a[i1] * f
    a = gaussian(a, blur_px)
    dx, dy = offset
    M = np.float32
    # sub-pixel shift via bilinear interpolation
    ys, xs = np.mgrid[0:h, 0:w].astype(M)
    sx, sy = xs - dx, ys - dy
    x0 = np.clip(np.floor(sx).astype(int), 0, w - 1)
    y0 = np.clip(np.floor(sy).astype(int), 0, h - 1)
    x1 = np.clip(x0 + 1, 0, w - 1)
    y1 = np.clip(y0 + 1, 0, h - 1)
    fx = np.clip(sx - np.floor(sx), 0, 1)
    fy = np.clip(sy - np.floor(sy), 0, 1)
    sh = (a[y0, x0] * (1 - fx) * (1 - fy) + a[y0, x1] * fx * (1 - fy) + a[y1, x0] * (1 - fx) * fy
          + a[y1, x1] * fx * fy)
    valid = (sx >= 0) & (sy >= 0) & (sx <= w - 1) & (sy <= h - 1)
    sh = np.where(valid, sh, 0.0) * opacity
    shadow = solid(w, h, color, 0.0)
    shadow[..., 3] = sh
    return over(img, shadow)


def bbox(img, thresh=0.02):
    """(x0, y0, x1, y1) of pixels with alpha > thresh (x1/y1 exclusive), or None."""
    ys, xs = np.nonzero(img[..., 3] > thresh)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def place(img, size, anchor="bottom_center", margin=1, scale_to_fit=True):
    """Trim to content and place into a ``size`` canvas (fallback when not framed by camera)."""
    W, H = size
    bb = bbox(img)
    if bb is None:
        return np.zeros((H, W, 4), np.float32)
    x0, y0, x1, y1 = bb
    crop = img[y0:y1, x0:x1]
    ch, cw = crop.shape[:2]
    if scale_to_fit and (cw > W - 2 * margin or ch > H - 2 * margin):
        s = min((W - 2 * margin) / cw, (H - 2 * margin) / ch)
        crop = resize(crop, (max(1, int(cw * s)), max(1, int(ch * s))))
        ch, cw = crop.shape[:2]
    out = np.zeros((H, W, 4), np.float32)
    ox = (W - cw) // 2
    oy = H - margin - ch if anchor == "bottom_center" else (H - ch) // 2
    out[oy:oy + ch, ox:ox + cw] = crop
    return out


def hex_mask(w=128, h=111, flat_top=True, inset=0.0, ss=8):
    """Anti-aliased hexagon alpha mask exactly filling a ``w x h`` tile (flat-top: corners at the
    left/right middle).  ``inset`` shrinks it (px).  Coverage computed with ``ss``x``ss`` samples.
    """
    ys, xs = np.mgrid[0:h * ss, 0:w * ss].astype(np.float32)
    x = (xs + 0.5) / ss - w / 2.0
    y = (ys + 0.5) / ss - h / 2.0
    if not flat_top:
        x, y = y, x
        w, h = h, w
    r = w / 2.0 - inset
    hh = h / 2.0 - inset
    # flat-top hexagon: |y| <= hh and |x| <= r - |y| * (r/2) / hh
    inside = (np.abs(y) <= hh) & (np.abs(x) <= r - np.abs(y) * (r / 2.0) / hh)
    m = inside.astype(np.float32)
    if not flat_top:
        m = m.T
        w, h = h, w
    m = m.reshape(h, ss, w, ss).mean(axis=(1, 3))
    return m


def apply_mask(img, mask):
    out = img.copy()
    out[..., 3] = out[..., 3] * mask
    return out


# =============================================================================================
# colour, paper, painterly helpers
# =============================================================================================
def grade(img, saturation=1.0, contrast=1.0, brightness=0.0, warmth=0.0, gamma=1.0, pivot=0.5):
    """Simple painterly grade in sRGB: saturation, contrast about ``pivot``, warmth (+R -B)."""
    out = img.copy()
    rgb = out[..., :3]
    lum = (rgb * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1, keepdims=True)
    rgb = lum + (rgb - lum) * saturation
    rgb = (rgb - pivot) * contrast + pivot + brightness
    rgb = rgb + np.array([warmth, warmth * 0.25, -warmth], np.float32)
    if gamma != 1.0:
        rgb = np.power(np.clip(rgb, 0, 1), 1.0 / gamma)
    out[..., :3] = np.clip(rgb, 0, 1)
    return out


def _value_noise(h, w, cell, rng):
    gh, gw = int(math.ceil(h / cell)) + 2, int(math.ceil(w / cell)) + 2
    g = rng.random((gh, gw)).astype(np.float32)
    im = Image.fromarray(g, "F").resize((int(gw * cell), int(gh * cell)), Image.BICUBIC)
    a = np.asarray(im, np.float32)
    oy, ox = rng.integers(0, max(1, int(cell))), rng.integers(0, max(1, int(cell)))
    return a[oy:oy + h, ox:ox + w]


def fbm(h, w, cell=64.0, octaves=5, gain=0.5, seed=0):
    """Fractal value noise in ~0..1 (numpy, deterministic)."""
    rng = np.random.default_rng(seed)
    acc = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    c = float(cell)
    for _ in range(octaves):
        acc += amp * _value_noise(h, w, max(c, 1.0), rng)
        tot += amp
        amp *= gain
        c /= 2.0
    return acc / tot


def paper_texture(w, h, seed=0, fibre=1.0, grain=1.0, scale=1.0):
    """Paper luminance texture centred on 1.0 (multiply it in): fibres + grain + soft blotches."""
    rng = np.random.default_rng(seed)
    blot = fbm(h, w, 160 * scale, 4, 0.5, seed + 1) - 0.5
    g = rng.normal(0, 1, (h, w)).astype(np.float32)
    g = gaussian(g, 0.6 * scale)
    # fibres: stretched noise in two directions
    f1 = _value_noise(h, int(w / 6) + 2, 2.0 * scale, rng)
    f1 = np.asarray(Image.fromarray(f1, "F").resize((w, h), Image.BICUBIC), np.float32) - 0.5
    f2 = _value_noise(int(h / 6) + 2, w, 2.0 * scale, rng)
    f2 = np.asarray(Image.fromarray(f2, "F").resize((w, h), Image.BICUBIC), np.float32) - 0.5
    t = 1.0 + 0.10 * blot + 0.035 * grain * g / max(1e-6, g.std()) + 0.05 * fibre * (f1 + f2)
    return t.astype(np.float32)


def apply_paper(img, paper, strength=0.08, mode="multiply"):
    """Lay paper texture over colour (alpha untouched). ``strength`` scales the deviation."""
    out = img.copy()
    p = 1.0 + (paper - 1.0) * (strength / 0.1)
    if mode == "multiply":
        out[..., :3] = np.clip(out[..., :3] * p[..., None], 0, 1)
    else:  # overlay-ish: affect mid-tones more than darks/lights
        x = out[..., :3]
        d = (p[..., None] - 1.0)
        out[..., :3] = np.clip(x + d * 4.0 * x * (1 - x), 0, 1)
    return out


def vignette(img, strength=0.25, power=2.2, center=(0.45, 0.42)):
    h, w = img.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((xs / w - center[0]) / 0.75) ** 2 + ((ys / h - center[1]) / 0.75) ** 2)
    v = 1.0 - strength * np.clip(d, 0, 1.5) ** power
    out = img.copy()
    out[..., :3] *= v[..., None]
    return out


def over(fg, bg):
    """Porter-Duff ``fg`` over ``bg`` (straight alpha both)."""
    fa = fg[..., 3:4]
    ba = bg[..., 3:4]
    oa = fa + ba * (1 - fa)
    rgb = (fg[..., :3] * fa + bg[..., :3] * ba * (1 - fa)) / np.maximum(oa, 1e-6)
    return np.concatenate([rgb, oa], -1)


def kuwahara(img, radius=3):
    """Classic 4-quadrant Kuwahara in numpy (alpha-aware fallback for when the compositor's
    anisotropic node cannot be used, e.g. post-hoc on an existing PNG).  Picks, per pixel, the
    quadrant mean with the lowest luminance variance; transparent pixels are excluded."""
    pm = premultiply(img)
    a = img[..., 3]
    lum = (img[..., :3] * np.array([0.299, 0.587, 0.114], np.float32)).sum(-1) * a
    r = radius
    H, W = a.shape

    def integral(x):
        s = np.zeros((x.shape[0] + 1, x.shape[1] + 1) + x.shape[2:], np.float64)
        s[1:, 1:] = x.cumsum(0).cumsum(1)
        return s

    pad = lambda x: np.pad(x, [(r, r), (r, r)] + [(0, 0)] * (x.ndim - 2), mode="edge")
    I_rgb = integral(pad(pm))
    I_a = integral(pad(a))
    I_l = integral(pad(lum))
    I_l2 = integral(pad(lum * lum))
    yy, xx = np.mgrid[0:H, 0:W]
    yy = yy + r
    xx = xx + r
    best_var = np.full((H, W), np.inf)
    out = np.zeros_like(pm)
    for (dy0, dx0) in ((-r, -r), (-r, 0), (0, -r), (0, 0)):
        y0, x0 = yy + dy0, xx + dx0
        y1, x1 = y0 + r + 1, x0 + r + 1

        def box(I):
            return I[y1, x1] - I[y0, x1] - I[y1, x0] + I[y0, x0]
        n = float((r + 1) ** 2)
        sa = box(I_a)
        wsum = np.maximum(sa, 1e-6)
        ml = box(I_l) / wsum
        var = box(I_l2) / wsum - ml * ml
        var = np.where(sa < 0.5, np.inf, var)
        m = var < best_var
        best_var = np.where(m, var, best_var)
        mean = box(I_rgb) / n
        out[m] = mean[m]
    out = np.clip(out, 0, 1).astype(np.float32)
    keep = np.isinf(best_var)
    out[keep] = pm[keep]
    out[..., 3] = np.where(keep, a, out[..., 3])
    return unpremultiply(out)


# =============================================================================================
# previews
# =============================================================================================
def checker(w, h, cell=8, c0=(0.78, 0.78, 0.78), c1=(0.62, 0.62, 0.62)):
    ys, xs = np.mgrid[0:h, 0:w]
    m = ((xs // cell + ys // cell) % 2).astype(np.float32)[..., None]
    rgb = np.array(c0, np.float32) * (1 - m) + np.array(c1, np.float32) * m
    return np.dstack([rgb, np.ones((h, w), np.float32)])


def nine_slice(img, margins, size):
    """Stretch a 9-slice image to ``size`` (w, h). ``margins`` = (left, top, right, bottom)."""
    l, t, r, b = margins
    H, W = img.shape[:2]
    w, h = size
    out = np.zeros((h, w, 4), np.float32)
    xs_src = [(0, l), (l, W - r), (W - r, W)]
    ys_src = [(0, t), (t, H - b), (H - b, H)]
    xs_dst = [(0, l), (l, w - r), (w - r, w)]
    ys_dst = [(0, t), (t, h - b), (h - b, h)]
    for (sy0, sy1), (dy0, dy1) in zip(ys_src, ys_dst):
        for (sx0, sx1), (dx0, dx1) in zip(xs_src, xs_dst):
            if dy1 <= dy0 or dx1 <= dx0 or sy1 <= sy0 or sx1 <= sx0:
                continue
            piece = img[sy0:sy1, sx0:sx1]
            if (sy1 - sy0, sx1 - sx0) != (dy1 - dy0, dx1 - dx0):
                piece = resize(piece, (dx1 - dx0, dy1 - dy0), "bilinear")
            out[dy0:dy1, dx0:dx1] = piece
    return out


def nine_slice_preview(img, margins, sizes, bg="#1B1712", gap=12):
    """Row of the 9-slice stretched to each size in ``sizes`` on a dark background."""
    pieces = [img] + [nine_slice(img, margins, s) for s in sizes]
    W = sum(p.shape[1] for p in pieces) + gap * (len(pieces) + 1)
    H = max(p.shape[0] for p in pieces) + 2 * gap
    sheet = solid(W, H, bg)
    x = gap
    for p in pieces:
        sheet = paste(sheet, p, x, gap)
        x += p.shape[1] + gap
    return sheet


def paste(dst, src, x, y):
    """Alpha-composite ``src`` onto ``dst`` at (x, y) (clipped)."""
    out = dst.copy()
    h, w = src.shape[:2]
    H, W = dst.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return out
    out[y0:y1, x0:x1] = over(src[y0 - y:y1 - y, x0 - x:x1 - x], out[y0:y1, x0:x1])
    return out


def contact_sheet(items, cols=4, pad=10, bg="#2A2119", label_color=(0.91, 0.86, 0.75),
                  checker_alpha=True, scale=1):
    """Grid of (image, label) for review. Transparent images sit on a checkerboard."""
    if not items:
        return None
    imgs = []
    for im, lab in items:
        if scale != 1:
            im = resize(im, (im.shape[1] * scale, im.shape[0] * scale), "nearest")
        imgs.append((im, lab))
    cw = max(i.shape[1] for i, _ in imgs)
    chh = max(i.shape[0] for i, _ in imgs)
    rows = int(math.ceil(len(imgs) / cols))
    lab_h = 16
    W = cols * (cw + pad) + pad
    H = rows * (chh + pad + lab_h) + pad
    sheet = to_pil(solid(W, H, bg))
    d = ImageDraw.Draw(sheet)
    for k, (im, lab) in enumerate(imgs):
        cx = pad + (k % cols) * (cw + pad)
        cy = pad + (k // cols) * (chh + pad + lab_h)
        h, w = im.shape[:2]
        tile = im
        if checker_alpha and im[..., 3].min() < 0.999:
            tile = over(im, checker(w, h))
        sheet.alpha_composite(to_pil(tile), (cx, cy))
        d.text((cx, cy + chh + 2), str(lab), fill=tuple(int(c * 255) for c in label_color) + (255,))
    return from_pil(sheet)
