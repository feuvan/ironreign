"""Shared plumbing of the UI chrome family scripts (Tools/BlenderArt/ui_chrome/), gongbi style.

Every piece module exposes

    NAME, SPEC            name, dict(size=(w, h), ss=4, spp=1, margins=..., seed=...)
    VARIANTS, FILE        optional state variants and their file names
    paint(G, variant)     -> straight sRGB RGBA float array on grid G (numpy only: the painted
                             layers of :mod:`ironart.ui_chrome_paint`)
    extras(variant, G)    optional bpy: toon-shaded 3D parts + Freestyle ink (scroll rollers)

:func:`render_piece` renders ``paint`` through Cycles as a flat emission plate at ``ss`` x the
target size (plus the extras) and returns the finished @1x and @2x images (premultiplied
Lanczos downsample of the same render, so both resolutions are the same art).  With
``numpy_only=True`` (look-dev, system python3) the plate is used directly without Blender; for
pieces without extras that gives the identical image.
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import numpy as np  # noqa: E402

from ironart import REPO_DIR, post  # noqa: E402
from ironart import ui_chrome_sdf as S  # noqa: E402

FONTS = os.path.join(REPO_DIR, "Content", "Data", "Fonts")
ART_UI = os.path.join(REPO_DIR, "Content", "Data", "Art", "UI")
SRC_UI = os.path.join(REPO_DIR, "ArtSource", "UI")


def out_dir(*parts):
    base = os.environ.get("IRONART_UI_OUT") or os.path.join(
        os.environ.get("IRONART_OUT", "/tmp/ironart"), "ui_chrome")
    p = os.path.join(base, *parts)
    os.makedirs(p, exist_ok=True)
    return p


def font(name):
    return os.path.join(FONTS, name)


def finish(raw, ss, lo=0.004, hi=0.996):
    """Supersampled RGBA render -> (@1x, @2x) straight-alpha float images (premultiplied
    Lanczos; an odd ``ss`` resamples the @2x by ss/2)."""
    img = post.load(raw) if isinstance(raw, str) else raw
    h, w = img.shape[:2]
    if ss % 2 == 0:
        x2 = post.downsample(img, ss // 2) if ss > 2 else img
    else:
        x2 = post.resize(img, (w * 2 // ss, h * 2 // ss))
    x1 = post.downsample(img, ss)
    out = []
    for im in (x1, x2):
        out.append(post.alpha_cleanup(im, lo=lo, hi=hi, bleed=4))
    return out


def quantize8(rgba):
    """What an 8-bit PNG round trip does to a float image (look-dev path parity)."""
    return np.round(np.clip(rgba, 0, 1) * 255.0) / 255.0


def render_piece(mod, variant=None, preview=False, tag=None, numpy_only=False):
    """Paint + render one piece module.  Returns dict(img1, img2, raw, times, plate)."""
    spec = mod.SPEC
    w, h = spec["size"]
    ss = spec.get("ss", 4)
    spp = spec.get("spp", 1)
    if preview:
        ss = 2
    tag = tag or (mod.NAME + (("_" + variant) if variant else ""))
    t0 = time.time()
    G = S.Grid(w, h, ss)
    paint = getattr(mod, "paint_lookdev", mod.paint) if numpy_only else mod.paint
    rgba = paint(G, variant).astype(np.float32)
    t_paint = time.time() - t0
    raw = os.path.join(out_dir("raw"), "%s_raw_%dx.png" % (tag, ss))
    if numpy_only:
        post.save(rgba, raw)
        t_render = 0.0
        t1 = time.time()
    else:
        import bpy
        from ironart import scene
        from ironart import ui_chrome_flat as F
        scene.reset(seed=spec.get("seed", 1))
        has_3d = hasattr(mod, "extras")
        F.setup(ss=ss, spp=spp if has_3d else 1, seed=spec.get("seed", 1))
        F.camera(w, h, ss)
        F.plate(tag, rgba, w, h)
        if has_3d:
            mod.extras(variant, G)
        t1 = time.time()
        t_render = scene.render(raw)
        bpy.ops.wm.read_factory_settings(use_empty=True)
    img1, img2 = finish(raw, ss)
    if hasattr(mod, "post"):
        img1, img2 = mod.post(img1, img2, variant)
    times = {"paint": round(t_paint, 2), "build": round(t1 - t0 - t_paint, 2),
             "render": round(t_render, 2), "total": round(time.time() - t0, 2)}
    print("[ui_chrome] %s times %s" % (tag, times))
    return {"img1": img1, "img2": img2, "raw": raw, "times": times, "plate": rgba}


def save_pair(res, name, rel=None):
    """@1x into Content/Data/Art/UI (through the manifest check) and @2x into ArtSource/UI."""
    rel = rel or "Art/UI/%s.png" % name
    p1 = post.save_asset(res["img1"], rel)
    os.makedirs(SRC_UI, exist_ok=True)
    p2 = post.save(res["img2"], os.path.join(SRC_UI, "%s@2x.png" % name))
    return p1, p2
