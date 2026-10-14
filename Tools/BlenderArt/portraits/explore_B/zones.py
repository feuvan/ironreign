"""Per-vertex 'paint zones' on the hm08 base mesh (numpy only, cached).

A portrait painter blocks skin in colour zones - a yellower forehead, ruddy cheeks / nose / ears,
a blue-grey beard shadow, darker lids - and lays dark accents only in a few places.  Because every
portrait uses the same topology, the zones are computed once on the *base* mesh and ride along with
the morphs:

* anatomical regions come from the MakeHuman morph targets themselves (the displacement magnitude
  of e.g. ``mouth-upperlip-volume-incr`` is a clean soft mask of the upper lip),
* hair-bearing regions (scalp, beard, moustache, brows) are analytic in head-centred coordinates.

All coordinates here are MakeHuman base coords (decimetres, y up, z forward).
"""

import os

import numpy as np

from . import mh

_MASKS = None


def _ss(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _tmag(rel):
    b = mh.load_base()
    m = np.zeros(len(b.verts), np.float32)
    idx, d = mh.load_target(rel)
    m[idx] = np.linalg.norm(d, axis=1)
    return m


def _norm(m, lo=0.15, hi=0.6):
    mx = float(m.max()) or 1.0
    return _ss(lo, hi, m / mx)


def landmark_index():
    """Fixed base-mesh vertex indices of facial landmarks (hm08)."""
    return dict(nose_tip=297, subnasale=5342, lip_top=466, lip_bottom=492, chin=5162,
                chin_low=732, nasion=136, brow_mid=237, forehead=983, crown=881,
                cheek_l=11906, cheek_r=_mirror(11906), ear_l=_ear_idx(1), ear_r=_ear_idx(-1),
                mouth_l=_mouth_corner(1), mouth_r=_mouth_corner(-1))


_MIRROR = None


def _mirror(i):
    global _MIRROR
    b = mh.load_base()
    if _MIRROR is None:
        _MIRROR = {}
    if i not in _MIRROR:
        p = b.verts[i] * np.array([-1, 1, 1], np.float32)
        _MIRROR[i] = int(np.argmin(np.linalg.norm(b.verts[:13380] - p, axis=1)))
    return _MIRROR[i]


def _ear_idx(side):
    b = mh.load_base()
    m = _tmag("ears/%s-ear-scale-incr" % ("l" if side > 0 else "r"))
    m[13380:] = 0
    w = m ** 4
    c = (b.verts * w[:, None]).sum(0) / w.sum()
    return int(np.argmin(np.linalg.norm(b.verts[:13380] - c, axis=1)))


def _mouth_corner(side):
    b = mh.load_base()
    lips = np.maximum(_tmag("mouth/mouth-upperlip-volume-incr"), _tmag("mouth/mouth-lowerlip-volume-incr"))
    sel = np.nonzero(lips > lips.max() * 0.05)[0]
    sel = sel[sel < 13380]
    j = sel[np.argmax(b.verts[sel, 0] * side)]
    return int(j)


def masks():
    """dict name -> (N,) float32 in [0,1] over all base vertices (cached on disk)."""
    global _MASKS
    if _MASKS is not None:
        return _MASKS
    cp = mh._cache_path("zones_v11")
    if os.path.exists(cp):
        d = np.load(cp)
        _MASKS = {k: d[k] for k in d.files}
        return _MASKS
    b = mh.load_base()
    V = b.verts.astype(np.float64)
    x, y, z = V[:, 0], V[:, 1], V[:, 2]
    ax = np.abs(x)
    M = {}
    lu = _norm(_tmag("mouth/mouth-upperlip-volume-incr"), 0.12, 0.5)
    ll = _norm(_tmag("mouth/mouth-lowerlip-volume-incr"), 0.12, 0.5)
    M["lips"] = np.maximum(lu, ll)
    M["nose"] = _norm(_tmag("nose/nose-trans-forward"), 0.4, 0.95)
    nt = V[297]
    M["nose_tip"] = np.exp(-np.sum(((V - nt) / [0.16, 0.13, 0.12]) ** 2, 1))
    ears = _tmag("ears/l-ear-trans-backward") + _tmag("ears/r-ear-trans-backward")
    M["ears"] = _norm(ears, 0.55, 0.95)
    cheek = _tmag("cheek/l-cheek-volume-incr") + _tmag("cheek/r-cheek-volume-incr")
    M["cheek"] = _norm(cheek, 0.05, 0.7)
    cb = _tmag("cheek/l-cheek-bones-incr") + _tmag("cheek/r-cheek-bones-incr")
    M["cheekbone"] = _norm(cb, 0.1, 0.7)
    M["chin"] = _norm(_tmag("chin/chin-prominent-incr"), 0.1, 0.6)
    eb = _tmag("eyes/l-eye-bag-incr") + _tmag("eyes/r-eye-bag-incr")
    M["eyebag"] = _norm(eb, 0.05, 0.6)
    lid = _tmag("eyes/l-eye-eyefold-up") + _tmag("eyes/r-eye-eyefold-up")
    M["lid"] = _norm(lid, 0.03, 0.5)
    esc = _tmag("eyes/l-eye-scale-incr") + _tmag("eyes/r-eye-scale-incr")
    M["eye_area"] = _norm(esc, 0.05, 0.5)
    # lash line: base verts closest to the upper lash helper roots
    M["lash"] = _lash_line(b, V)
    # ---- analytic regions, head-centred azimuth (0 = front, +-180 = back)
    phi = np.degrees(np.arctan2(x, z - 0.55))
    aphi = np.abs(phi)
    # front of face/forehead
    brow_y = 7.56
    # scalp hairline height as a function of azimuth
    hl = np.interp(aphi, [0, 25, 45, 62, 80, 100, 130, 180],
                   [8.06, 8.02, 7.86, 7.66, 7.42, 7.18, 6.88, 6.62])
    scalp = _ss(hl - 0.04, hl + 0.10, y) * (y > 6.4)
    scalp *= 1.0 - M["ears"]
    M["scalp"] = scalp
    M["hairline"] = _ss(hl - 0.06, hl + 0.02, y) * (1 - _ss(hl + 0.02, hl + 0.22, y)) * (y > 6.4)
    # lower, rounder hairline (women, youths): covers the temples and the top of the ears
    hl2 = np.interp(aphi, [0, 25, 45, 62, 80, 100, 130, 180],
                    [7.86, 7.80, 7.64, 7.46, 7.28, 7.08, 6.84, 6.58])
    sc2 = _ss(hl2 - 0.03, hl2 + 0.08, y) * (y > 6.4)
    sc2 *= 1.0 - M["ears"] * _ss(7.35, 7.2, y)
    M["scalp_low"] = sc2
    M["forehead"] = _ss(brow_y + 0.05, brow_y + 0.25, y) * (1 - scalp) * _ss(70, 40, aphi)
    # beard: below the cheek line, above the under-jaw line, on the face/jaw
    cheek_line = np.interp(aphi, [0, 15, 26, 36, 50, 65, 80, 92],
                           [6.77, 6.74, 6.62, 6.64, 6.76, 6.92, 7.12, 7.34])
    neck_line = np.interp(aphi, [0, 30, 60, 85, 100], [6.10, 6.12, 6.22, 6.45, 6.75])
    beard = _ss(cheek_line + 0.02, cheek_line - 0.08, y) * _ss(neck_line - 0.08, neck_line + 0.06, y)
    beard *= _ss(102, 88, aphi) * (1 - M["lips"] * 0.97) * (1 - _ss(0.3, 0.7, M["nose"]))
    M["beard"] = np.clip(beard, 0, 1)
    # moustache: between subnasale and the upper lip, out to the mouth corners
    must = _ss(6.80, 6.74, y) * _ss(6.60, 6.66, y) * _ss(0.42, 0.30, ax) * (z > 1.2)
    must *= (1 - lu * 0.95) * (1 - _ss(0.4, 0.8, M["nose"]))
    M["moustache"] = np.clip(must, 0, 1)
    # chin tuft region (goatee root area)
    M["goatee"] = _ss(6.52, 6.42, y) * _ss(6.05, 6.15, y) * _ss(0.30, 0.16, ax) * (z > 1.0)
    # eyebrows: band following the brow ridge above each eye
    M["brow"] = _brow_mask(V)
    M["neck"] = _ss(6.3, 6.0, y) * _ss(5.2, 5.6, y)
    # nasolabial fold distance field (dm): polyline nose wing -> past the mouth corner
    M["nasolabial"] = _poly_band(V, [(0.20, 6.80, 1.42), (0.30, 6.68, 1.40), (0.37, 6.55, 1.33),
                                     (0.40, 6.42, 1.24)], 0.035)
    # crow's feet / under-eye crease / forehead lines params (used by shaders as masks)
    M["crows"] = np.exp(-(((ax - 0.58) / 0.10) ** 2 + ((y - 7.27) / 0.12) ** 2)) * (z > 0.6)
    M["undereye"] = _poly_band(V, [(0.18, 7.18, 1.32), (0.32, 7.12, 1.34), (0.48, 7.15, 1.24)], 0.03)
    M["marionette"] = _poly_band(V, [(0.30, 6.55, 1.38), (0.28, 6.38, 1.33), (0.24, 6.25, 1.30)], 0.03)
    M["glabella"] = np.exp(-(((ax - 0.06) / 0.05) ** 2 + ((y - 7.47) / 0.08) ** 2)) * (z > 1.3)
    M["jaw_under"] = _ss(6.25, 6.0, y) * _ss(5.8, 6.0, y) * _ss(110, 60, aphi)
    M["temple"] = np.exp(-(((ax - 0.66) / 0.10) ** 2 + ((y - 7.62) / 0.18) ** 2)) * (z > 0.3)
    rows, cols = adjacency()
    for k, it in (("beard", 3), ("moustache", 2), ("scalp", 3), ("scalp_low", 3), ("hairline", 2), ("goatee", 3),
                  ("brow", 1), ("forehead", 3), ("ears", 1), ("nose", 2), ("cheek", 2)):
        M[k] = smooth(M[k].astype(np.float64), it, rows, cols)
    for k in list(M):
        M[k] = np.clip(np.nan_to_num(M[k]), 0, 1).astype(np.float32)
        M[k][13380:] = 0
    np.savez(cp, **M)
    _MASKS = M
    return M


def _brow_mask(V):
    x, y, z = V[:, 0], V[:, 1], V[:, 2]
    ax = np.abs(x)
    # brow centre line (|x| -> y): rises from the head of the brow, arches, falls at the tail
    cy = np.interp(ax, [0.08, 0.20, 0.35, 0.50, 0.62], [7.47, 7.52, 7.56, 7.54, 7.46])
    half = np.interp(ax, [0.08, 0.20, 0.45, 0.62], [0.040, 0.044, 0.030, 0.012])
    m = _ss(half + 0.012, half - 0.008, np.abs(y - cy)) * _ss(0.06, 0.10, ax) * _ss(0.66, 0.58, ax)
    return m * (z > 0.9)


def _poly_band(V, pts, width):
    """1 on a polyline (x mirrored for both sides), 0 beyond ``width`` (dm)."""
    P = np.array(pts, np.float64)
    out = np.zeros(len(V))
    for sx in (1, -1):
        Q = P * [sx, 1, 1]
        d = np.full(len(V), 1e9)
        for a, c in zip(Q[:-1], Q[1:]):
            ab = c - a
            t = np.clip(((V - a) @ ab) / (ab @ ab), 0, 1)
            pr = a + t[:, None] * ab
            d = np.minimum(d, np.linalg.norm(V - pr, axis=1))
        out = np.maximum(out, _ss(width, 0.0, d))
    return out


def _lash_line(b, V):
    """Upper lid margin: body vertices hugging the eyeball (helper sphere) above its centre."""
    out = np.zeros(len(V))
    body = V[:13380]
    for g in ("helper-l-eye", "helper-r-eye"):
        c = b.verts[b.group_verts(g)].astype(np.float64)
        cc = c.mean(0)
        r = np.linalg.norm(c - cc, axis=1).mean()
        rel = body - cc
        d = np.linalg.norm(rel, axis=1) - r
        up = _ss(-0.035, 0.0, rel[:, 1])
        out[:13380] = np.maximum(out[:13380], _ss(0.05, 0.022, d) * up * (rel[:, 2] > 0.02))
    return out


def adjacency():
    """(rows, cols) vertex adjacency of the body faces (for mask smoothing)."""
    b = mh.load_base()
    F = b.faces[b.group_faces("body")]
    a = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 3]], F[:, [3, 0]]])
    a = a[a[:, 0] != a[:, 1]]
    a = np.concatenate([a, a[:, ::-1]])
    return a[:, 0], a[:, 1]


def smooth(m, iters=3, rows=None, cols=None):
    if rows is None:
        rows, cols = adjacency()
    n = len(m)
    deg = np.bincount(rows, minlength=n).astype(np.float64)
    deg[deg == 0] = 1
    for _ in range(iters):
        acc = np.bincount(rows, weights=m[cols], minlength=n)
        m = 0.5 * m + 0.5 * acc / deg
    return m
