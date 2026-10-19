"""2D stage of gongbi_C (system python3): paint the canon face, beard, hair strands and the
designed 3D curves over the Blender passes, then finish on aged silk.

    python3 stage2d.py <scene_dir> <out_png> [--debug]

Writes ``<out_png>`` (384x480), ``<out>_192.png`` and ``<out>_timing.json``.
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

import brush as B  # noqa: E402
import face2d  # noqa: E402
import hair2d  # noqa: E402
import palette as PL  # noqa: E402
from ironart import scenes_gongbi as GB  # noqa: E402

SILK_REF = np.array(PL.srgb("silk"), np.float32)

LOOK = dict(pooling=0.14, granulation=0.06, streak=0.015,
            silk=dict(fibre=0.034, slub=0.028, mottle=0.05, stain=0.03, edge=0.11),
            age=dict(yellow=0.025, desat=0.04))


def to_srgb(x):
    x = np.clip(np.asarray(x, np.float32), 0.0, None)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def load(scene_dir):
    with open(os.path.join(scene_dir, "scene.json")) as f:
        meta = json.load(f)
    npz = dict(np.load(os.path.join(scene_dir, "scene.npz")))
    return meta, npz


def base_image(npz):
    C = npz["color"]
    A = np.clip(C[..., 3], 0, 1)
    col = np.clip(to_srgb(C[..., :3] / np.maximum(A, 1e-4)[..., None]), 0, 1)
    img = SILK_REF[None, None] * (1 - A[..., None]) + col * A[..., None]
    return img.astype(np.float32), A


def lay_freestyle(cv, npz, strength=0.95):
    L = npz["line"]
    la = np.clip(L[..., 3], 0, 1)
    lcol = to_srgb(np.clip(L[..., :3] / np.maximum(la, 1e-4)[..., None], 0, None))
    lcol = np.where(la[..., None] > 1e-4, lcol, np.array(PL.srgb("ink")))
    # a hint of bleed into the silk
    bl = B.blur(la, 0.6 * cv.ss) * 0.22
    a = np.clip(np.maximum(la, bl), 0, 1) * strength
    cv.img = cv.img * (1 - a[..., None]) + lcol * a[..., None]
    cv.ink_a = np.maximum(cv.ink_a, a)


def id_mask(npz, meta, names):
    ids = meta["ids"]
    r = np.round(npz["id"] * 100).astype(int)
    m = np.zeros(r.shape, np.float32)
    for n in names:
        if n in ids:
            m = np.maximum(m, (r == ids[n]).astype(np.float32))
    return m


def curves(cv, pr, meta, npz, spec):
    """Designed 3D curves: robe folds (兰叶描 + a 分染 wash beside), ear detail."""
    cos = spec.get("costume", {})
    robe = cos.get("robe", {})
    deep = robe.get("deep") or PL.deepen(robe.get("color", "azurite"), 0.55)
    robe_m = id_mask(npz, meta, ["Robe", "Cloak", "Sleeve"])
    for cvd in meta["curves"]:
        P = pr.world(np.array(cvd["pts"]))
        P = B.resample(P, max(12, len(P)))
        st = cvd["style"]
        tol = cvd.get("tol", 0.06 if st == "fold" else 0.02)
        vis = pr.visible(P, tol=tol, soft=0.03)
        if st == "fold":
            if vis.mean() < 0.05:
                continue
            wt = cvd.get("w", 1.0)
            prof = B.profile(len(P), 0.12, 0.6, "nail", pressure=0.2, seed=len(P))
            d = np.gradient(P[:, :2], axis=0)
            d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
            nrm = np.stack([-d[:, 1], d[:, 0]], -1) * cvd.get("side", 1)
            wpx = cv.k(10.0) * wt
            side_pts = P[:, :2] + nrm * wpx * (0.3 + 0.7 * np.sin(np.linspace(0, math.pi, len(P))))[:, None]
            poly = np.concatenate([P[:, :2], side_pts[::-1]])
            m = B.blur(cv.raster([poly]), cv.k(3.0))
            cv.apply(m * robe_m, cvd.get("wash", deep), "glaze", 0.35 * wt)
            cv.stroke(P, prof * 1.25 * wt, "ink", vis * 0.9, clip=np.clip(robe_m * 1.5, 0, 1))
        elif st == "ear":
            if vis.mean() < 0.05:
                continue
            prof = B.profile(len(P), 0.2, 0.4, "silk")
            cv.stroke(P, prof * cvd.get("w", 0.55) * 1.4, PL.srgb("skin_line"), vis * 0.75)
        elif st == "line":
            cv.stroke(P, B.profile(len(P), 0.2, 0.3, "even") * cvd.get("w", 0.8),
                      cvd.get("color", "ink"), vis * cvd.get("a", 0.9))


def contact_shade(cv, npz, masks, strength=0.30, radius=7.0):
    """分染 along overlaps: where a nearer layer lies over a farther one (collar over robe, hat
    over forehead, armour over cloak), the farther surface is deepened next to the edge."""
    from scipy.ndimage import minimum_filter
    D = npz["depth"].astype(np.float32)
    A = masks["alpha"]
    D = np.where(A > 0.5, D, 1e3)
    k = max(3, int(radius * cv.ss))
    Dmin = minimum_filter(D, size=k, mode="nearest")
    gap = np.clip((D - Dmin - 0.004) / 0.03, 0, 1) * (A > 0.5)
    sh = B.blur(gap, radius * cv.ss * 0.35)
    skin = np.clip(masks["face"] + masks["skin"], 0, 1)
    sh = sh * (1 - 0.55 * skin)
    # deepen: multiply by a warm dark, proportionally to the local colour
    cv.img *= (1 - strength * sh[..., None] * np.array([0.55, 0.62, 0.70], np.float32))


def finish(img, ink_a, seed, size=(384, 480)):
    mw, mh = size[0] * 2, size[1] * 2
    master = np.clip(GB.lanczos(img, (mw, mh)), 0, 1)
    ink_m = np.clip(GB.lanczos(ink_a, (mw, mh)), 0, 1)
    out = GB.finish_silk(master, ink_m, LOOK, seed=seed, m=2.0)["master"]
    one = GB.downsample_1x(out, size)
    half = GB.downsample_1x(out, (size[0] // 2, size[1] // 2))
    return out, one, half


def silhouette(cv, npz, A, scene_dir, out_png, seed, t0):
    """unknown.png: the bust as a soft ink-wash shadow on silk, outlined, no features."""
    h, w = A.shape
    cv.img = np.broadcast_to(SILK_REF[None, None], cv.img.shape).copy()
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    grad = 0.55 + 0.35 * yy
    sil = B.blur(np.clip(A, 0, 1), 0.8 * cv.ss)
    cv.apply(B.blur(sil, 10 * cv.ss), "#8A8478", "glaze", 0.35)
    cv.apply(sil * grad, "#4A453E", "paint", 0.85)
    cv.apply(sil * (1 - B.blur(sil, 6 * cv.ss)) * 2.0, "#2A2622", "paint", 0.5)
    lay_freestyle(cv, npz, 0.35)
    master, one, half = finish(cv.img, cv.ink_a * 0.4, seed)
    GB.save_png(one, out_png, seed=1)
    GB.save_png(half, out_png.replace(".png", "_192.png"), seed=2)
    tim = {"paint2d": time.time() - t0}
    with open(out_png.replace(".png", "_timing.json"), "w") as f:
        json.dump(tim, f)
    return tim


def run(scene_dir, out_png, debug=False):
    t0 = time.time()
    meta, npz = load(scene_dir)
    spec = meta["spec"]
    pr = B.Proj(meta, npz["depth"])
    img, A = base_image(npz)
    cv = B.Canvas(img, meta["ss"])
    mask = npz["mask"]
    masks = dict(face=np.clip(mask[..., 0], 0, 1), hair=np.clip(mask[..., 1], 0, 1),
                 skin=np.clip(mask[..., 2], 0, 1), alpha=A)
    seed = spec.get("seed", 0)
    if spec.get("silhouette"):
        return silhouette(cv, npz, A, scene_dir, out_png, seed, t0)
    # 1. washes and folds under the ink
    contact_shade(cv, npz, masks)
    curves(cv, pr, meta, npz, spec)
    # 2. the 3D ink
    lay_freestyle(cv, npz)
    # 3. hair strands over the hair masses (before the face: the face is never covered)
    hair2d.paint_hair(cv, pr, meta, npz, spec, masks, seed)
    # 4. the face
    fc = face2d.Face(cv, pr, spec, masks, seed)
    fc.paint()
    # 5. beard, plumes, tassels (over everything)
    hair2d.paint_beard(cv, pr, fc, spec, seed)
    hair2d.paint_strands(cv, pr, meta, spec, seed)
    # 6. finish on silk
    master, one, half = finish(cv.img, cv.ink_a, seed)
    t2d = time.time() - t0
    os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
    GB.save_png(one, out_png, seed=1)
    GB.save_png(half, out_png.replace(".png", "_192.png"), seed=2)
    if debug:
        GB.save_png(master, out_png.replace(".png", "_master.png"), seed=3)
    tim = {}
    tp = os.path.join(scene_dir, "timing3d.json")
    if os.path.exists(tp):
        with open(tp) as f:
            tim = json.load(f)
    tim["paint2d"] = t2d
    with open(out_png.replace(".png", "_timing.json"), "w") as f:
        json.dump(tim, f)
    print("[gongbi_C] 2D %s: %.1fs" % (spec.get("name", "?"), t2d))
    return tim


if __name__ == "__main__":
    a = sys.argv[1:]
    run(a[0], a[1], debug="--debug" in a)
