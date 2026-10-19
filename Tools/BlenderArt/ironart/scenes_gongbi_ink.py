"""Illustrated Scenes (gongbi): image-space ink lines from the render passes.

Freestyle is single-threaded and took ~85 % of every scene's render time (90 s of 100 s for a
1280x720 preview), so the outlines are drawn here, in numpy, from passes Cycles writes at sample
0 (no anti-aliasing): depth, object index, material index and the (filtered) normal.

Edges (at render resolution, ``k`` render px per game px):

* **silhouette / occlusion**: inverse depth ``w = 1/z`` is affine across a plane in screen space,
  so a pixel whose neighbour is notably *farther* than the linear extrapolation from its other
  neighbour sits on the near side of a depth step.  The threshold is relative to ``w`` and to the
  local gradient (sample-0 depth is jittered inside the pixel).
* **crease**: neighbouring normals differ by more than ``crease`` degrees.
* **boundary**: object or material index changes (drawn on the nearer pixel).

Each object's ink kind comes from its pass index (``index = seq * 16 + code``, set by
:func:`tag_objects` from the ``GB_<kind>`` collections).  Every kind has its own width (game px),
pressure (low-frequency width noise along the strokes), distance thinning / fading, colour, and
which edge types it draws (:data:`KINDS`).  Lines are grown to their width with an anti-aliased
variable-radius dilation, then given dry-brush breaks.

:func:`rim` returns the soft band along the outlines used for 分染 (colour deepening towards the
outline inside each form).
"""

import math

import numpy as np

from . import scenes_gongbi as GB

#: kind -> code stored in the low 4 bits of the object pass index
CODES = {"none": 0, "arch": 1, "fig": 2, "land": 3, "tree": 4, "fine": 5, "skin": 6, "cloud": 7,
         "water": 8, "prop": 9}

#: per-kind ink.  w = line width in GAME px at ``near``; far = (distance m where the width / alpha
#: reach ``wfar`` / ``afar``); pressure = width noise amplitude; dry = break-up amount;
#: edges = which edge types the kind draws; t_sil = relative inverse-depth step for a
#: silhouette; crease = degrees; rim = 分染 strength along this kind's outlines
KINDS = {
    "arch":  dict(w=0.62, a=0.95, near=15.0, far=260.0, wfar=0.55, afar=0.55, pressure=0.0,
                  dry=0.05, edges=("sil", "crease", "id"), t_sil=0.012, crease=38.0,
                  color="ink", rim=1.0),
    "fig":   dict(w=0.55, a=0.95, near=8.0, far=160.0, wfar=0.6, afar=0.65, pressure=0.22,
                  dry=0.06, edges=("sil", "crease", "id"), t_sil=0.006, crease=55.0,
                  color="ink", rim=1.0),
    "skin":  dict(w=0.42, a=0.8, near=6.0, far=120.0, wfar=0.6, afar=0.6, pressure=0.1,
                  dry=0.0, edges=("sil", "id"), t_sil=0.006, crease=80.0, color="#8A5A40", rim=0.5),
    "land":  dict(w=0.95, a=0.92, near=40.0, far=2500.0, wfar=0.45, afar=0.3, pressure=0.55,
                  dry=0.22, edges=("sil", "id"), t_sil=0.02, crease=70.0, color="ink", rim=1.0),
    "tree":  dict(w=0.6, a=0.92, near=15.0, far=1200.0, wfar=0.5, afar=0.4, pressure=0.35,
                  dry=0.12, edges=("sil", "id"), t_sil=0.01, crease=60.0, color="ink", rim=0.8),
    "fine":  dict(w=0.42, a=0.75, near=10.0, far=300.0, wfar=0.6, afar=0.5, pressure=0.0,
                  dry=0.0, edges=("sil", "id"), t_sil=0.006, crease=60.0, color="ink", rim=0.0),
    "prop":  dict(w=0.5, a=0.9, near=8.0, far=200.0, wfar=0.6, afar=0.6, pressure=0.1,
                  dry=0.0, edges=("sil", "crease", "id"), t_sil=0.006, crease=45.0, color="ink",
                  rim=0.8),
    "cloud": dict(w=0.6, a=0.6, near=40.0, far=3000.0, wfar=0.6, afar=0.5, pressure=0.35,
                  dry=0.1, edges=("sil",), t_sil=0.01, crease=90.0, color="ink_grey", rim=0.4),
    "water": dict(w=0.5, a=0.6, near=10.0, far=1000.0, wfar=0.6, afar=0.4, pressure=0.3,
                  dry=0.2, edges=("sil",), t_sil=0.02, crease=90.0, color="ink_grey", rim=0.0),
    "none":  dict(w=0.0, a=0.0, near=10.0, far=100.0, wfar=1.0, afar=1.0, pressure=0.0, dry=0.0,
                  edges=(), t_sil=1.0, crease=180.0, color="ink", rim=0.0),
}

NKIND = 16


def kind_table(overrides=None):
    """KINDS with per-scene overrides ({kind: {key: value}}) -> list indexed by code."""
    tab = [dict(KINDS["none"]) for _ in range(NKIND)]
    for name, code in CODES.items():
        spec = dict(KINDS.get(name, KINDS["none"]))
        spec.update((overrides or {}).get(name, {}))
        tab[code] = spec
    return tab


def tag_objects():
    """Set every object's pass index from its ``GB_<kind>`` collection (seq * 16 + code) and give
    every material a unique pass index (material boundaries)."""
    import bpy
    seq = 1
    for kind, code in CODES.items():
        c = bpy.data.collections.get("GB_" + kind)
        if c is None:
            continue
        for o in c.all_objects:
            o.pass_index = seq * NKIND + code
            seq += 1
    for i, m in enumerate(bpy.data.materials):
        m.pass_index = i + 1


# =============================================================================================
# numpy helpers
# =============================================================================================
def _nb(a, dy, dx, fill):
    """Neighbour array: out[y, x] = a[y + dy, x + dx] (``fill`` outside)."""
    h, w = a.shape[:2]
    out = np.empty_like(a)
    out[...] = fill
    ys0, ys1 = max(0, -dy), min(h, h - dy)
    xs0, xs1 = max(0, -dx), min(w, w - dx)
    out[ys0:ys1, xs0:xs1] = a[ys0 + dy:ys1 + dy, xs0 + dx:xs1 + dx]
    return out


def detect(Z, oid, mid, N, A, tab, k):
    """Edge pixels (bool H x W) and the kind code of each pixel (int H x W).

    Z depth (background >= 1e9), oid / mid object / material pass index, N normal (H x W x 3),
    A coverage."""
    H, W = Z.shape
    cov = (A > 0.5) & (Z < 1e9)
    w = np.where(cov, 1.0 / np.maximum(Z, 1e-3), 0.0).astype(np.float32)
    code = np.where(cov, np.mod(np.round(oid).astype(np.int64), NKIND), 0).astype(np.int16)
    t_sil = np.array([t["t_sil"] for t in tab], np.float32)[code]
    want = {e: np.array([e in t["edges"] for t in tab], bool)[code] for e in ("sil", "crease", "id")}
    cos_cr = np.cos(np.radians(np.array([t["crease"] for t in tab], np.float32)))[code]
    ids = np.where(cov, np.round(oid) * 4096.0 + np.round(mid), -1.0)
    Nn = N / np.maximum(np.linalg.norm(N, axis=-1, keepdims=True), 1e-6)
    E = np.zeros((H, W), bool)
    for dy, dx in ((0, 1), (1, 0)):
        for sgn in (1, -1):
            wn = _nb(w, dy * sgn, dx * sgn, 0.0)            # neighbour on this side
            wp = _nb(w, -dy * sgn, -dx * sgn, 0.0)          # neighbour on the other side
            wp = np.where(wp > 0, wp, w)                    # background behind: no slope info
            pred = 2.0 * w - wp
            grad = np.abs(w - wp)
            thr = t_sil * w + 1.5 * grad
            sil = cov & (wn < pred - thr) & (wn < w * (1.0 - t_sil * 0.5))
            E |= sil & want["sil"]
        nn = _nb(Nn, dy, dx, 0.0)
        idn = _nb(ids, dy, dx, -1.0)
        wn = _nb(w, dy, dx, 0.0)
        both = cov & (idn >= 0)
        cr = both & ((Nn * nn).sum(-1) < cos_cr) & (np.abs(w - wn) < 0.05 * w)
        E |= cr & want["crease"]
        diff = both & (ids != idn)
        # boundary on the nearer pixel: this one if nearer or equal, else the neighbour
        E |= diff & (w >= wn) & want["id"]
        E |= _nb(diff & (wn > w), -dy, -dx, False) & want["id"]
    return E & cov, code


def dilate(E, R, rmax):
    """Anti-aliased variable-radius dilation: coverage of discs of radius ``R`` (px, per edge
    pixel) centred on the edge pixels ``E``."""
    ER = np.where(E, R, -10.0).astype(np.float32)
    out = np.zeros(E.shape, np.float32)
    r = int(math.ceil(rmax + 0.5))
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            d = math.hypot(dx, dy)
            if d > rmax + 0.75:
                continue
            s = _nb(ER, dy, dx, -10.0)
            np.maximum(out, np.clip(s - d + 0.5, 0.0, 1.0), out=out)
    return out


def ink(ps, tab, k, seed=0):
    """Ink lines from the passes -> (alpha H x W, colour H x W x 3 sRGB, raw edges, code)."""
    C = ps["color"]
    A = np.clip(C[..., 3], 0.0, 1.0)
    Z = ps["depth"][..., 0]
    oid = ps["index_ob"][..., 0]
    mid = ps["index_ma"][..., 0]
    N = ps["normal"][..., :3]
    H, W = Z.shape
    E, code = detect(Z, oid, mid, N, A, tab, k)
    Zc = np.where(Z < 1e9, Z, 1e6)
    # per-pixel width (render px radius) and alpha from the kind and distance
    wk = np.array([t["w"] for t in tab], np.float32)[code]
    ak = np.array([t["a"] for t in tab], np.float32)[code]
    near = np.array([t["near"] for t in tab], np.float32)[code]
    far = np.array([t["far"] for t in tab], np.float32)[code]
    wfar = np.array([t["wfar"] for t in tab], np.float32)[code]
    afar = np.array([t["afar"] for t in tab], np.float32)[code]
    pr = np.array([t["pressure"] for t in tab], np.float32)[code]
    dry = np.array([t["dry"] for t in tab], np.float32)[code]
    td = np.clip((np.log(np.maximum(Zc, 1e-3)) - np.log(near)) / np.maximum(np.log(far) - np.log(near), 1e-3), 0, 1)
    wd = 1.0 + (wfar - 1.0) * td
    ad = 1.0 + (afar - 1.0) * td
    # pressure: low-frequency noise along the strokes (~18 game px period), swelling and thinning
    n1 = GB.value_noise(H, W, 18.0 * k, seed + 301, 2, 0.5)
    p = 1.0 + pr * (n1 - 0.5) * 2.0
    R = np.maximum(wk * wd * p * k * 0.5, 0.0)
    rmax = float(R[E].max()) if E.any() else 1.0
    la = dilate(E, R, rmax)
    # alpha / dryness / colour carried from the nearby edge pixels (weighted box average)
    r = int(math.ceil(rmax + 0.5))
    Ef = E.astype(np.float32)
    wsum = np.maximum(GB.box_blur(Ef, r), 1e-6)

    def carry(v):
        return GB.box_blur(Ef * v, r) / wsum
    la = la * carry(ak * ad)
    dn = GB.value_noise(H, W, 2.2 * k, seed + 307, 2, 0.55)
    la = la * np.clip(1.0 - carry(dry) * GB.smoothstep(0.5, 0.85, dn) * 1.6, 0, 1)
    cols = np.array([GB.srgb(t["color"]) for t in tab], np.float32)[code]
    lc = np.dstack([carry(cols[..., c]) for c in range(3)])
    lc = np.where(la[..., None] > 0, lc, np.array(GB.srgb("ink"), np.float32))
    return np.clip(la, 0, 1), lc.astype(np.float32), E, code


def rim(E, code, tab, A, k, px=2.6):
    """分染 band: soft falloff (0..1) inward from the outlines, weighted by each kind's ``rim``,
    restricted to painted pixels.  ``px`` = width of the band in game px."""
    wr = np.array([t["rim"] for t in tab], np.float32)[code]
    src = (E * wr).astype(np.float32)
    b1 = GB.blur(src, px * k * 0.45)
    b2 = GB.blur(src, px * k * 1.1)
    band = np.clip(b1 * 1.6 + b2 * 0.9, 0, 1)
    return band * (A > 0.5)
