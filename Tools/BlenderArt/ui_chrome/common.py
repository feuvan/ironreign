"""Shared plumbing of the UI chrome family scripts (Tools/BlenderArt/ui_chrome/).

Every piece module exposes ``SPEC`` (size, supersample, samples, 9-slice margins) and
``build(G, variant) -> Maps`` (numpy only) plus optional ``extras(variant)`` (extra bpy objects:
text, cylinders...).  :func:`render_piece` turns that into a Cycles render at ``ss`` x the target
size and returns the finished @1x and @2x images (premultiplied Lanczos downsample of the same
render, so both resolutions are identical art).
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


def finish(raw, ss, lo=0.004, hi=0.996):
    """Supersampled RGBA render -> (@1x, @2x) straight-alpha float images."""
    img = post.load(raw) if isinstance(raw, str) else raw
    x2 = post.downsample(img, ss // 2) if ss > 2 else img
    x1 = post.downsample(img, ss)
    out = []
    for im in (x1, x2):
        im = post.alpha_cleanup(im, lo=lo, hi=hi, bleed=4)
        out.append(im)
    return out


def render_piece(mod, variant=None, preview=False, tag=None):
    """Build + render one piece module.  Returns dict(img1, img2, raw, times, maps)."""
    import bpy
    from ironart import scene
    from ironart import ui_chrome_render as R
    spec = mod.SPEC
    w, h = spec["size"]
    ss = spec.get("ss", 4)
    spp = spec.get("spp", 64)
    if preview:
        spp = max(12, spp // 3)
        ss = 2
    tag = tag or (mod.NAME + (("_" + variant) if variant else ""))
    t0 = time.time()
    scene.reset(seed=spec.get("seed", 1))
    R.setup(ss=ss, spp=spp, transparent=True, view=spec.get("view", "Standard"),
            look=spec.get("look", "None"))
    G = S.Grid(w, h, ss)
    m = mod.build(G, variant)
    t_maps = time.time() - t0
    R.camera(w, h, ss)
    rig = getattr(mod, "rig", None)
    if rig is not None:
        rig(variant)
    else:
        R.rig_chrome(**spec.get("rig", {}))
    if m is not None:
        R.plate(tag, m, w, h, step=spec.get("mesh_step", 1), cut=spec.get("cut", True))
    if hasattr(mod, "extras"):
        mod.extras(variant, G)
    raw = os.path.join(out_dir("raw"), "%s_raw_%dx.png" % (tag, ss))
    t1 = time.time()
    t_render = scene.render(raw)
    img1, img2 = finish(raw, ss)
    if hasattr(mod, "post"):
        img1, img2 = mod.post(img1, img2, variant)
    times = {"maps": round(t_maps, 2), "build": round(t1 - t0 - t_maps, 2),
             "render": round(t_render, 2), "total": round(time.time() - t0, 2)}
    print("[ui_chrome] %s times %s" % (tag, times))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return {"img1": img1, "img2": img2, "raw": raw, "times": times, "maps": m}


def save_pair(res, name, rel=None):
    """@1x into Content/Data/Art/UI (through the manifest check) and @2x into ArtSource/UI."""
    rel = rel or "Art/UI/%s.png" % name
    p1 = post.save_asset(res["img1"], rel)
    os.makedirs(SRC_UI, exist_ok=True)
    p2 = post.save(res["img2"], os.path.join(SRC_UI, "%s@2x.png" % name))
    return p1, p2
