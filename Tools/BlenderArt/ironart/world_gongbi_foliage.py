"""World Models family: painted (not rendered) gongbi foliage atlases.

:func:`pine_atlas` paints the pine needle-pad atlas the way pines are painted in gongbi and
blue-green landscape (松针 "wheel" needles, 车轮松): every pad seen from above is a lobed cluster of
needle wheels.  Each wheel is a malachite (sometimes teal-azurite) wash disc graded darker towards
its hub (晕染), with 40-70 tapered ink-green needle strokes radiating from the hub; the wheels are
layered back to front so a front wheel's wash veils the needles of the wheels behind it, and a
fine ink twig skeleton joins the hubs.  Pure PIL + numpy (no render): 4x supersampled, box
downsampled, premultiplied.

Output files and layout match :func:`ironart.world_gongbi.leaf_atlas` (2 x 2 cells,
``Pine_Leaves_{Base,Normal,ORM}.png``: sRGB RGBA base with alpha = coverage and colour bled into
the transparent area, tangent-space normal with +Y up, matte ORM without AO), so the tree cards
(:class:`ironart.world_trees.TreeBuilder`, cell (i, j) = UV square [i/2, (i+1)/2] x [j/2, (j+1)/2])
use it unchanged.
"""

import math
import os
import random
import time

import numpy as np

#: sRGB colours (the shared gongbi mineral palette, DESIGN.md 8)
PINE = {
    # pad wash: edge, interior (晕染: deeper inside the pad); one cell in four is teal-azurite
    "pad": ("#4E9678", "#2C6650"),
    "pad_cool": ("#4C8C88", "#2A5E62"),
    "needle": "#132C25", "needle_l": "#24503F", "twig": "#2A2018",
}
ROUGH = 0.9


def _lin(h):
    c = np.array([int(h[k:k + 2], 16) / 255.0 for k in (1, 3, 5)], np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def _to_srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(np.maximum(x, 0.0031308), 1 / 2.4) - 0.055)


def _over(col, alpha, c_layer, a_layer, y0, x0):
    """Straight-colour 'over' of a layer (colour array or constant) into col / alpha at (y0, x0)."""
    h, w = a_layer.shape
    sl = (slice(y0, y0 + h), slice(x0, x0 + w))
    a = a_layer[..., None]
    col[sl] = col[sl] * (1.0 - a) + c_layer * a
    alpha[sl] = alpha[sl] * (1.0 - a_layer) + a_layer


def _taper_poly(p0, p1, w0, w1):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L
    return [(p0[0] + nx * w0, p0[1] + ny * w0), (p1[0] + nx * w1, p1[1] + ny * w1),
            (p1[0] - nx * w1, p1[1] - ny * w1), (p0[0] - nx * w0, p0[1] - ny * w0)]


def _mask(size, polys):
    from PIL import Image, ImageDraw
    im = Image.new("L", size, 0)
    d = ImageDraw.Draw(im)
    for p in polys:
        d.polygon(p, fill=255)
    return np.asarray(im, np.float32) / 255.0


def _wheels(rng, C):
    """Lobed pad: a hub wheel near the centre and 5-7 around it; (cx, cy, r) in cell pixels."""
    out = []
    n = rng.randint(5, 6)
    c0 = (C * 0.5 + rng.uniform(-0.03, 0.03) * C, C * 0.5 + rng.uniform(-0.03, 0.03) * C)
    a0 = rng.uniform(0, math.tau)
    for k in range(n):
        if k == 0:
            r = C * rng.uniform(0.21, 0.24)
            out.append((c0[0], c0[1], r))
            continue
        a = a0 + math.tau * (k - 1) / (n - 1) + rng.uniform(-0.25, 0.25)
        r = C * rng.uniform(0.165, 0.205)
        # pads are wider than deep (flat horizontal clouds): squash the ring in y a little
        d = C * rng.uniform(0.17, 0.23)
        x = c0[0] + math.cos(a) * d
        y = c0[1] + math.sin(a) * d * 0.86
        lim = C * 0.5 - r * 1.1 - C * 0.02
        x = c0[0] + max(-lim, min(lim, x - c0[0]))
        y = c0[1] + max(-lim, min(lim, y - c0[1]))
        out.append((x, y, r))
    return out


def _paint_cell(rng, C, ss, cool=False):
    """One pad: a lobed malachite wash cloud (晕染: deeper inside, clearer towards the pad edge)
    carrying needle wheels in ink-green; each wheel first veils what lies under its disc with the
    pad wash, so the wheels layer like brush work without outlining each one as a rosette."""
    col = np.zeros((C, C, 3), np.float32)
    alpha = np.zeros((C, C), np.float32)
    wheels = _wheels(rng, C)
    yy, xx = np.mgrid[0:C, 0:C].astype(np.float32)
    # twig skeleton (ink) from an entry under the pad to every hub (seen only in the gaps)
    ea = rng.uniform(0, math.tau)
    entry = (C * 0.5 + math.cos(ea) * C * 0.12, C * 0.5 + math.sin(ea) * C * 0.12)
    twigs = []
    for (x, y, r) in wheels:
        mid = ((entry[0] + x) / 2 + rng.uniform(-0.02, 0.02) * C, (entry[1] + y) / 2 + rng.uniform(-0.02, 0.02) * C)
        twigs.append(_taper_poly(entry, mid, C * 0.006, C * 0.0045))
        twigs.append(_taper_poly(mid, (x, y), C * 0.0045, C * 0.0025))
    _over(col, alpha, _lin(PINE["twig"]), _mask((C, C), twigs), 0, 0)
    # the pad: soft union of slightly wobbly discs
    discs = []
    field = np.zeros((C, C), np.float32)
    for k, (x, y, r) in enumerate(wheels):
        ang = np.arctan2(yy - y, xx - x)
        wob = 1.0 + 0.05 * np.sin(ang * 5 + 1.7 * k) + 0.03 * np.sin(ang * 9 + 2.3 * k)
        d = np.hypot(xx - x, yy - y) / (r * 0.95 * wob)
        discs.append(d)
        field = np.maximum(field, 1.0 - d)
    feather = 0.05
    pad_a = np.clip(field / feather, 0, 1)
    t = np.clip(field / 0.55, 0, 1)[..., None] ** 0.8
    edge_c, inner_c = (_lin(h) for h in (PINE["pad_cool"] if cool else PINE["pad"]))
    wash = edge_c * (1 - t) + inner_c * t
    _over(col, alpha, wash, pad_a * 0.96, 0, 0)
    height = np.clip(field, 0, None) * C * 0.06
    # wheels: outer ones first, the hub wheel on top (a domed pad)
    order = list(range(1, len(wheels)))
    rng.shuffle(order)
    order.append(0)
    for k in order:
        x, y, r = wheels[k]
        veil = np.clip((1.0 - discs[k]) / 0.12, 0, 1) * 0.62
        _over(col, alpha, wash, veil * pad_a, 0, 0)
        R = r * 1.18
        x0, y0 = int(max(0, x - R - 2)), int(max(0, y - R - 2))
        x1, y1 = int(min(C, x + R + 2)), int(min(C, y + R + 2))
        n = int(84 * (r / (0.16 * C)) ** 1.2)
        polys_d, polys_l = [], []
        lx, ly = x - x0, y - y0
        for q in range(n):
            a = math.tau * q / n + rng.uniform(-0.6, 0.6) * math.tau / n
            r0 = r * rng.uniform(0.08, 0.2)
            r1 = r * rng.uniform(0.92, 1.12)
            bend = rng.uniform(-0.05, 0.05)
            pa = (lx + math.cos(a) * r0, ly + math.sin(a) * r0)
            pb = (lx + math.cos(a + bend) * r1, ly + math.sin(a + bend) * r1)
            w0 = max(0.5 * ss, r * 0.017)
            poly = _taper_poly(pa, pb, w0, max(0.25 * ss, w0 * 0.18))
            (polys_l if rng.random() < 0.28 else polys_d).append(poly)
        size = (x1 - x0, y1 - y0)
        _over(col, alpha, _lin(PINE["needle"]), _mask(size, polys_d) * 0.9, y0, x0)
        _over(col, alpha, _lin(PINE["needle_l"]), _mask(size, polys_l) * 0.8, y0, x0)
    return col, alpha, height


def pine_atlas(out_dir, size=1024, ss=4, seed=31):
    """Paint the 2 x 2 pine pad atlas; writes ``Pine_Leaves_{Base,Normal,ORM}.png`` into
    ``out_dir`` and returns {'base', 'normal', 'orm', 'secs'}."""
    from PIL import Image
    from . import post
    t0 = time.time()
    rng = random.Random(seed)
    cell = size // 2
    C = cell * ss
    base = np.zeros((size, size, 4), np.float32)
    nrm = np.zeros((size, size, 3), np.float32)
    for j in range(2):          # j: v (row 0 of the image is v = 1)
        for i in range(2):
            col, a, h = _paint_cell(random.Random(rng.random()), C, ss, cool=(i, j) == (1, 0))

            def down(x):
                return x.reshape(cell, ss, cell, ss, *x.shape[2:]).mean(axis=(1, 3))
            a_s = down(a)
            c_s = down(col * a[..., None]) / np.maximum(a_s, 1e-4)[..., None]
            h_s = down(h) / float(ss)
            # normal from the dome height (subtle: a painted pad, 45 % strength)
            gy, gx = np.gradient(h_s)
            k = 0.45
            nv = np.dstack([-gx * k, gy * k, np.ones_like(h_s)])
            nv /= np.linalg.norm(nv, axis=-1, keepdims=True)
            nv[a_s < 0.02] = (0, 0, 1)
            r0 = (1 - j) * cell
            c0 = i * cell
            base[r0:r0 + cell, c0:c0 + cell, :3] = c_s
            base[r0:r0 + cell, c0:c0 + cell, 3] = np.clip(a_s * 1.06, 0, 1)
            nrm[r0:r0 + cell, c0:c0 + cell] = nv
    rgba = np.dstack([_to_srgb(base[..., :3]), base[..., 3]]).astype(np.float32)
    rgba = post.alpha_cleanup(rgba, lo=0.02, hi=0.98, bleed=24)
    mean = rgba[..., :3][rgba[..., 3] > 0.5].mean(0)
    far = (rgba[..., 3] <= 0.0) & (rgba[..., :3].sum(-1) <= 0.0)
    rgba[far, :3] = mean
    orm = np.dstack([np.ones((size, size), np.float32), np.full((size, size), ROUGH, np.float32),
                     np.zeros((size, size), np.float32)])
    os.makedirs(out_dir, exist_ok=True)
    out = {}
    for key, arr, mode in (("base", rgba, "RGBA"), ("normal", nrm * 0.5 + 0.5, "RGB"), ("orm", orm, "RGB")):
        p = os.path.join(out_dir, "Pine_Leaves_%s.png" % (key.capitalize() if key != "orm" else "ORM"))
        Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8), mode).save(p, optimize=True)
        out[key] = p
    out["secs"] = time.time() - t0
    print("[ironart] painted pine atlas %dpx in %.1fs" % (size, out["secs"]))
    return out
