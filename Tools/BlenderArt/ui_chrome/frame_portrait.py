"""Frame_Portrait.png (212x260, transparent window for a 192x240 portrait at x 10-202,
y 10-250): the portrait mounted like a painting - a brocade border woven with a running
cloud scroll (卷云纹) in mud-gold on azurite, a mud-gold thread, an ink rule and an ivory inner
rule (lead white) that frames the silk of the portrait.

Cross-section (d = mitred distance from the outer edge, target px):
    0.0-1.0    ink edge (outer corner r 1.5)
    1.0-7.3    azurite brocade with the running cloud scroll (period ~11.5 px, fitted so each
               edge holds a whole number of repeats, symmetric about its centre), 晕染 at
               both edges; mitred at the corners where a mud-gold 柿蒂 flower sits
    7.3-7.9    mud-gold thread
    7.9-8.4    ink rule
    8.4-10.4   ivory inner rule (lead white)
    10.4-11.0  ink hairline - lies 0.4-1.0 px over the portrait's edge
    > 11.0     transparent window
The frame is an overlay (drawn over the portrait), scaled uniformly with the portrait height.
"""

import math

import numpy as np

from ironart import ui_chrome_paint as P
from ironart import ui_chrome_sdf as S
import panel

NAME = "Frame_Portrait"
SPEC = dict(size=(212, 260), ss=4, seed=51)
W, H = 212, 260
B0, B1 = 1.0, 7.3          # brocade band
WINDOW = 11.0


def scroll_strokes(length, t0, t1, period, lw=0.85):
    """Running cloud scroll along a band: s in 0..length, t across (t0..t1).  A waving stem
    (sinusoid) with a curl springing from every crest into the hump below it and from every
    trough into the hump above (point-symmetric linked clouds).  ``period`` is adjusted so the
    band holds a whole number of repeats, symmetric about its centre.  [(pts (s, t), radii)]."""
    n = max(2, int(round(length / period)))
    p = length / n
    mid = 0.5 * (t0 + t1)
    amp = 0.21 * (t1 - t0)
    r = 1.0 * amp
    s = np.linspace(-p * 0.5, length + p * 0.5, int((length + p) * 8))
    wave = np.stack([s, mid - amp * np.sin(2 * math.pi * s / p)], 1)
    strokes = [(wave, np.full(len(wave), lw * 0.5, np.float32))]
    for k in range(-1, n + 1):
        sc = (k + 0.25) * p                       # crest (smallest t)
        pts = S.spiral(sc + 0.15, mid - amp + r, r, r * 0.22, 1.05, -90.0, cw=False, n=48)
        strokes.append((pts, S.taper(len(pts), lw * 0.5, lw * 0.2, power=0.9)))
        st = (k + 0.75) * p                       # trough
        pts = S.spiral(st - 0.15, mid + amp - r, r, r * 0.22, 1.05, 90.0, cw=False, n=48)
        strokes.append((pts, S.taper(len(pts), lw * 0.5, lw * 0.2, power=0.9)))
    return strokes


def band_pattern(G, seed):
    """sd of the brocade scroll on all four edges (mitred)."""
    out = G.empty()
    sts = []
    # each edge in its own (s, t) frame -> image coordinates
    for edge in ("top", "bottom", "left", "right"):
        L = W if edge in ("top", "bottom") else H
        for pts, rad in scroll_strokes(L, B0 + 0.3, B1 - 0.3, 11.5):
            s_, t_ = pts[:, 0], pts[:, 1]
            if edge == "top":
                xy = np.stack([s_, t_], 1)
            elif edge == "bottom":
                xy = np.stack([L - s_, H - t_], 1)
            elif edge == "left":
                xy = np.stack([t_, L - s_], 1)
            else:
                xy = np.stack([W - t_, s_], 1)
            sts.append((edge, xy, rad))
    masks = {}
    ys, xs = G.Y, G.X
    dist = {"top": ys, "bottom": H - ys, "left": xs, "right": W - xs}
    near = np.argmin(np.stack([dist[e] for e in ("top", "bottom", "left", "right")]), 0)
    for i, e in enumerate(("top", "bottom", "left", "right")):
        sd = G.empty()
        for edge, xy, rad in sts:
            if edge == e:
                S.sd_polyline(G, xy, rad, out=sd, pad=2.0)
        out = np.where(near == i, sd, out)
        masks[e] = sd
    return out


def paint(G, variant=None, seed=None):
    seed = SPEC["seed"] if seed is None else seed
    d = S.inset_distance(G, W, H, r=1.5)
    C = P.Canvas(G)
    frame = P.aa(-d, G) * P.aa(d - WINDOW, G)

    # an opaque ivory underlay for the whole border, so the AA edges between adjacent rings
    # never leave semi-transparent seams
    C.over(P.aa(d - WINDOW, G) * P.aa(-d, G), "ivory")

    # ---- brocade ------------------------------------------------------------------------------
    t = np.minimum(d - B0, B1 - d)
    base = P.mix("brocade_blue_deep", "brocade_blue", P.smoothstep(0.0, 2.0, t))
    base = base * (1.0 + 0.05 * P.fine_grain(G, seed, 0.35))[..., None]
    C.over(P.band(d, B0 - 0.2, B1, G), base)
    pat = band_pattern(G, seed)
    gold = P.mix(P.gold_field(G, seed + 1, flecks=0.0), "brocade_ochre", 0.45)
    C.over(P.aa(pat, G) * P.band(d, B0 + 0.2, B1 - 0.2, G), gold, 0.92)

    # ---- rules --------------------------------------------------------------------------------
    C.over(P.band(d, 7.3, 7.9, G), P.strip_color(d, "gold", seed + 2, amp=0.05))
    C.over(P.band(d, 7.9, 8.4, G), "ink_ui")
    C.over(P.band(d, 8.4, 10.4, G), P.mix("lead_white", "ivory", 0.35 + 0.3 * P.smoothstep(8.4, 10.4, d)))
    C.over(P.band(d, 10.4, WINDOW, G), "ink_soft", 0.92)
    C.over(P.band(d, -5, B0, G) * P.aa(-d, G), "ink")

    # ---- corner flowers on the mitre ----------------------------------------------------------------
    c = 0.5 * (B0 + B1)
    for (x, y) in ((c, c), (W - c, c), (c, H - c), (W - c, H - c)):
        sd = G.empty()
        S.sd_circle(G, x, y, 3.0, out=sd)
        C.over(P.aa(sd, G), "brocade_blue_deep")
        panel.flower(C, G, x, y, 2.6, seed + 5)
    C.erase(1.0 - frame)
    return C.rgba()


def post(img1, img2, variant=None):
    """Clear the faint Lanczos ringing (alpha < 3 %) so the window is exactly transparent."""
    out = []
    for im in (img1, img2):
        im = im.copy()
        a = im[..., 3]
        im[..., 3] = np.where(a < 0.03, 0.0, a)
        out.append(im)
    return out
