"""2D stage of gongbi_C: paint the face, beard, hair strands and folds over the 3D passes and
finish on aged silk.  Pure numpy + Pillow: runs in system python3 or inside Blender.

    python3 stage2d.py <scene_dir> <spec_name> <out_png> [--debug]
"""

import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(os.path.dirname(HERE))
for p in (HERE, TOOLS):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402

import face2d  # noqa: E402
import hair2d  # noqa: E402
import specs  # noqa: E402
import strokes as S  # noqa: E402
from looks import PAL, srgb, deepen  # noqa: E402
from ironart import scenes_gongbi as GB  # noqa: E402

SILK_REF = np.array(srgb(PAL["silk"]), np.float32)

LOOK = dict(pooling=0.16, granulation=0.07, streak=0.018,
            silk=dict(fibre=0.038, slub=0.03, mottle=0.055, stain=0.035, edge=0.12),
            age=dict(yellow=0.03, desat=0.05))


def to_srgb(x):
    x = np.clip(np.asarray(x, np.float32), 0.0, None)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055).astype(np.float32)


def base_image(npz):
    C = npz["color"]
    A = np.clip(C[..., 3], 0, 1)
    col = to_srgb(np.clip(C[..., :3] / np.maximum(A, 1e-4)[..., None], 0, None))
    col = np.clip(col, 0, 1)
    img = SILK_REF[None, None] * (1 - A[..., None]) + col * A[..., None]
    return img, A


def lay_freestyle(pp, npz, strength=0.95):
    L = npz["line"]
    la = np.clip(L[..., 3], 0, 1)
    lcol = to_srgb(np.clip(L[..., :3] / np.maximum(la, 1e-4)[..., None], 0, None))
    lcol = np.where(la[..., None] > 1e-4, lcol, srgb(PAL["ink"]))
    bl = S.blur(la, 0.35 * pp.ss) * 0.28
    la2 = np.clip(np.maximum(la, bl), 0, 1) * strength
    pp.img = pp.img * (1 - la2[..., None]) + lcol * la2[..., None]
    pp.ink_a = np.maximum(pp.ink_a, la2)


def region_mask(npz, name):
    from b_regions import REGION
    r = np.round(npz["region"] * 100).astype(int)
    if isinstance(name, (list, tuple)):
        m = np.zeros(r.shape, np.float32)
        for n in name:
            m = np.maximum(m, (r == REGION[n]).astype(np.float32))
        return m
    return (r == REGION[name]).astype(np.float32)


def curves_2d(pp, pr, meta, npz, spec):
    """Designed 3D curves: robe folds (兰叶描 with a 分染 wash beside), ear detail."""
    cos = spec.get("costume", {})
    robe = cos.get("robe", {})
    deep = robe.get("deep") or deepen(robe.get("color", "azurite"), 0.55)
    for cv in meta["curves"]:
        P = pr.world_px(np.array(cv["pts"]))
        P = S.resample(P, max(8, len(P)))
        vis = pr.visible(P, tol=cv.get("tol", 0.006)) if cv.get("test", True) else np.ones(len(P))
        vis = S.blur(vis[None], 1.0)[0] if len(vis) > 4 else vis
        st = cv["style"]
        if st == "fold":
            reg = region_mask(npz, cv.get("region", "robe"))
            wt = cv.get("weight", 1.0)
            prof = S.brush_profile(len(P), 0.12, 0.55, 0.12, "nail", pressure=0.15, seed=len(P))
            # 分染: a soft deeper wash on one side of the fold line
            d = np.gradient(P[:, :2], axis=0)
            d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
            nrm = np.stack([-d[:, 1], d[:, 0]], -1) * cv.get("side", 1)
            wpx = pp.k(9.0) * wt
            side_pts = P[:, :2] + nrm * wpx * (0.4 + 0.6 * np.sin(np.linspace(0, math.pi, len(P))))[:, None]
            poly = np.concatenate([P[:, :2], side_pts[::-1]])
            pp.fill(poly, cv.get("wash", deep), alpha=0.30 * wt, mode="glaze", soft=3.0, clip=reg)
            pp.stroke(P, 1.15 * wt, "ink", alpha=0.88, alphas=vis, prof=prof, clip=np.clip(reg * 1.5, 0, 1))
        elif st == "ear":
            pp.stroke(P, 0.55, spec["face"].get("line_color", "#4A3024"), alpha=0.75, alphas=vis,
                      prof=S.brush_profile(len(P), 0.3, 0.4, 0.2))
        elif st == "line":
            pp.stroke(P, cv.get("w", 0.8), cv.get("color", "ink"), alpha=cv.get("a", 0.9), alphas=vis,
                      prof=S.brush_profile(len(P), 0.2, 0.3, 0.3))


def finish(img, ink_a, ss, seed, size=(384, 480)):
    """work (ss x) -> master (2x) -> silk -> final 1x and half size."""
    mw, mh = size[0] * 2, size[1] * 2
    master = np.clip(GB.lanczos(img, (mw, mh)), 0, 1)
    ink_m = np.clip(GB.lanczos(ink_a, (mw, mh)), 0, 1)
    out = GB.finish_silk(master, ink_m, LOOK, seed=seed, m=2.0)["master"]
    one = GB.downsample_1x(out, size)
    half = GB.downsample_1x(out, (size[0] // 2, size[1] // 2))
    return out, one, half


def run(scene_dir, spec_name, out_png, debug=False):
    t0 = time.time()
    meta, npz = S.load_scene(scene_dir)
    spec = specs.get(spec_name)
    pr = S.Proj(meta, npz)
    img, A = base_image(npz)
    pp = S.Paper(img, meta["ss"])
    mask = npz["mask"]
    masks = dict(face=np.clip(mask[..., 0], 0, 1), hair=np.clip(mask[..., 1], 0, 1),
                 skin=np.clip(mask[..., 2], 0, 1))
    c = spec["face"]
    cx = face2d.Ctx(pp, pr, c, masks, seed=spec.get("seed", 0))
    if spec.get("silhouette"):
        # unknown officer: the figure as a soft ink-wash shadow with its outline, no features
        pp.img = np.broadcast_to(SILK_REF[None, None], pp.img.shape).copy()
        sil = S.blur(np.clip(A, 0, 1), pp.k(1.0))
        pp.layer(S.blur(sil, pp.k(8)), "#8A8478", "glaze", 0.30)
        pp.layer(sil, "#6A645A", "paint", 0.72)
        lay_freestyle(pp, npz, 0.55)
        master, one, half = finish(pp.img, pp.ink_a * 0.3, meta["ss"], spec.get("seed", 0))
        GB.save_png(one, out_png, seed=1)
        GB.save_png(half, out_png.replace(".png", "_192.png"), seed=2)
        return {}
    # 1. washes under everything: costume folds, skin
    curves_2d(pp, pr, meta, npz, spec)
    face2d.paint_washes(cx)
    # 2. the 3D ink
    lay_freestyle(pp, npz)
    # 3. face lines and fills, hair at the temples, beard
    face2d.paint_lines(cx)
    hair2d.paint(cx, spec, meta, npz)
    # 4. finish on silk
    master, one, half = finish(pp.img, pp.ink_a, meta["ss"], spec.get("seed", 0))
    t2d = time.time() - t0
    os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
    GB.save_png(one, out_png, seed=1)
    GB.save_png(half, out_png.replace(".png", "_192.png"), seed=2)
    if debug:
        GB.save_png(master, out_png.replace(".png", "_master.png"), seed=3)
        GB.save_png(np.clip(pp.img, 0, 1), out_png.replace(".png", "_work.png"), seed=3)
    tim = {}
    tp = os.path.join(scene_dir, "timing3d.json")
    if os.path.exists(tp):
        tim = json.load(open(tp))
    tim["paint2d"] = t2d
    with open(out_png.replace(".png", "_timing.json"), "w") as f:
        json.dump(tim, f)
    print("[gongbi_C] 2D %s: %.1fs" % (spec_name, t2d))
    return tim


if __name__ == "__main__":
    a = sys.argv[1:]
    run(a[0], a[1], a[2], debug="--debug" in a)
