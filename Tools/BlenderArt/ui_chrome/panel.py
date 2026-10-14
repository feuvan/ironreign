"""Panel.png (128x128 9-slice, 24 px border): handmade xuan paper mounted in a slim dark
rosewood moulding with an inset gold-leaf bead; gilt corner guards with a ruyi terminal.

Cross-section (distance d from the outer edge, target px = mm; mitred like a picture frame):
    0-8.4   rosewood moulding, straight grain along the rail, clear coat (crowned at 3.4 mm)
    8.6-11  gold-leaf bead (round, 2.4 px)
    11-11.8 black-lacquer reveal (shadow line)
    11.8-24 paper, aged towards the frame (PaperDark-ish) -> Paper by d = 22
Centre (24..104): Paper with xuan "formation" clouds + fine bast fibres, faded in over 8 px from
the 9-slice boundary so the stretched strips stay uniform.  Corner guards: 19 px gilt brackets
with a ruyi terminal, engraved outline and a domed boss, inside the 24 px corners.
"""

import numpy as np

from ironart import ui_chrome_motifs as MO
from ironart import ui_chrome_sdf as S
from ironart.ui_chrome_maps import Maps, L

NAME = "Panel"
SPEC = dict(size=(128, 128), ss=4, spp=64, margins=(24, 24, 24, 24), seed=11)
W = H = 128
M = 24

#: calibration: albedo multipliers so the rendered flat field lands on its token (measured)
CAL = {"paper": (1.0, 1.0, 1.0)}


def grain1d(d, seed, freq=0.7, lo=0.5, hi=1.3):
    """Straight wood grain as a function of the inset distance only (stretch-safe)."""
    rng = np.random.default_rng(seed)
    n = 4096
    lat = rng.random(n).astype(np.float32)
    x = np.clip(d * freq + 7.0, 0, n - 2)
    i = np.floor(x).astype(np.int32)
    f = x - i
    f = f * f * (3 - 2 * f)
    v = lat[i] * (1 - f) + lat[i + 1] * f
    # sharpen into streaks (late-wood lines) + a slower tonal wave
    streak = np.clip((v - 0.35) / 0.5, 0, 1) ** 1.6
    x2 = np.clip(d * 0.35 + 50.0, 0, n - 2)
    i2 = np.floor(x2).astype(np.int32)
    f2 = x2 - i2
    slow = lat[i2 + 1000] * (1 - f2) + lat[i2 + 1001] * f2
    return (lo + (hi - lo) * (0.65 * streak + 0.35 * slow)).astype(np.float32)


def bead(c, r, z0, n=9):
    """Profile points of a round bead centred at d = c, radius r, standing on z0."""
    a = np.linspace(np.pi, 0, n)
    return [(c + r * np.cos(t), z0 + r * 0.75 * np.sin(t)) for t in a]


def corner_guard(ss, T=8.4):
    """Gilt-bronze corner guard of the top-left corner on a local 24 x 24 grid, folded about the
    diagonal: a flat bevelled plate - a ruyi head on the mitre (lobes towards the panel), slim
    arms along both rails ending in spear tips - with an engraved outline, curls and a boss.
    Returns (height, mask, engraving_mask, boss_mask)."""
    G = S.Grid(M, M, ss)
    u, v = MO.corner_fold(G)
    F = _Folded(u, v)
    w = 2.7
    arm = S.sd_round_box_uv(u, v, 8.0, T / 2, 8.0, w, 0.8)
    spear = S.sd_polygon(_lat(G), [(15.6, T / 2 - w), (21.2, T / 2), (15.6, T / 2 + w)])
    spear = _fold_poly(G, [(15.6, T / 2 - w), (21.2, T / 2), (15.6, T / 2 + w)])
    arm = np.minimum(S.sd_round_box_uv(u, v, 7.8, T / 2, 7.8, w, 0.6), spear)
    ry, ry_eng = MO.ruyi(F, 8.6, 8.6, 10.5, rot=135.0)
    sq = S.sd_round_box_uv(u, v, 4.0, 4.0, 4.0, 4.0, 0.8)
    guard = S.smooth_union(S.smooth_union(arm, sq, 0.6), ry, 0.9)
    boss = np.hypot(u - 4.3, v - 4.3) - 2.0
    z = S.round_relief(guard, 0.5, 0.4)
    eng = np.minimum(np.abs(guard + 0.8), np.where((u - 8.6) + (v - 8.6) > -2.0, ry_eng, 9.0))
    eng = np.minimum(eng, np.where(u > 12.5, np.abs(v - T / 2) + 0.0 * u, 9.0) + 9.0 * (spear > -0.6))
    eng = np.where(np.hypot(u - 4.3, v - 4.3) < 2.9, 9.0, eng)
    z = z + S.groove(eng, 0.32, 0.15) * (guard < -0.25)
    z = z + MO.dome(boss, 1.0, 0.6) + S.groove(np.abs(boss + 0.7), 0.26, 0.1)
    return (z.astype(np.float32), S.aa_mask(guard, G), S.aa_mask(eng - 0.2, G),
            S.aa_mask(boss, G))


def _fold_poly(G, poly):
    """Polygon sd evaluated in the folded frame (u >= v), via both mirror images."""
    a = S.sd_polygon(G, poly)
    b = S.sd_polygon(G, [(y, x) for x, y in poly])
    u_ge_v = G.X >= G.Y
    return np.where(u_ge_v, a, b)


def _lat(G):
    return G


class _Folded:
    """Grid-like wrapper exposing folded coordinates as X / Y (for motif functions)."""

    def __init__(self, u, v):
        self.X, self.Y = u, v


def build(G, variant=None):
    d = S.inset_distance(G, W, H, r=2.5)
    m = Maps(G.shape, base="#E9DCC0")
    # ---- cross-section --------------------------------------------------------------------
    pts = [(-1, 0.0), (0.0, 0.3), (0.5, 1.4), (1.3, 2.35), (2.4, 2.75), (3.6, 2.9), (4.9, 2.75),
           (5.9, 2.35), (6.35, 2.05), (6.6, 1.92), (7.5, 1.92), (8.0, 1.6), (8.4, 1.05)]
    pts += bead(9.8, 1.2, 0.95)
    pts += [(11.05, 0.9), (11.25, 0.55), (11.75, 0.45), (12.3, 0.42), (30, 0.42)]
    prof = S.Profile(pts, round_px=0.14)
    z = prof(d)

    wood = S.band(d, -5, 8.45, G)
    gold = S.band(d, 8.45, 11.05, G)
    reveal = S.band(d, 11.05, 11.8, G)
    paper = S.band(d, 11.8, 999, G)

    # ---- rosewood ---------------------------------------------------------------------------
    g = grain1d(d, 3)
    m.paint(wood, "rosewood")
    m.tint(wood, g)
    # darker sapwood shadow in the fillet and a tiny dark arris line at the inner edge
    m.tint(S.band(d, 6.3, 7.6, G), 0.72)
    m.tint(S.band(d, 7.9, 8.45, G), 0.55)
    m.paint(wood, rough=0.30 + 0.12 * (1 - (g - 0.62) / 0.6))

    # ---- gold-leaf bead ------------------------------------------------------------------------
    m.paint(gold, "gold")
    m.paint(reveal, "lacquer_black")

    # ---- paper ---------------------------------------------------------------------------------
    t = np.clip((d - 12.0) / 10.0, 0, 1)
    t = t * t * (3 - 2 * t)
    aged = L("#D3C29E")
    base = aged[None, None, :] * (1 - t[..., None]) + L("#E9DCC0", 1.0)[None, None, :] * t[..., None]
    m.paint(paper, "paper", base=base * np.array(CAL["paper"], np.float32))
    # centre texture only inside the 9-slice centre, faded in from its boundary
    cx = np.minimum(G.X - M, (W - M) - G.X)
    cy = np.minimum(G.Y - M, (H - M) - G.Y)
    cmask = np.clip(np.minimum(cx, cy) / 8.0, 0, 1)
    cmask = cmask * cmask * (3 - 2 * cmask)
    tex, rel = xuan(G.shape, G.ss, seed=5)
    m.tint(paper * cmask, tex)
    z = z + rel * cmask * paper

    # ---- corner guards (local top-left piece stamped into the 4 corners) -----------------------
    gz, gm, ge, gb = corner_guard(G.ss)
    full = lambda a: MO.stamp_corners(np.zeros(G.shape, np.float32), a)
    gz, gm, ge, gb = full(gz), full(gm), full(ge), full(gb)
    z = z * (1 - gm) + np.maximum(z, 2.95 + gz) * gm
    m.paint(gm, "gold_satin")
    recess = np.clip(S.blur(gz, 1.2 * G.ss) - gz, 0, None)
    m.tint(gm, np.clip(1.0 - 2.2 * recess, 0.55, 1.0))
    m.tint(gm * ge, 0.6)
    m.paint(gm * ge, rough=0.5)
    m.paint(gb, rough=0.18)
    m.height = z.astype(np.float32)
    m.alpha = S.aa_mask(-d, G)
    return m


def xuan(shape, ss, seed=0):
    """Xuan paper albedo multiplier (mean 1) + relief (mm): cloudy formation and fine fibres."""
    h, w = shape
    form = S.fbm(shape, 22.0 * ss, seed, octaves=4, gain=0.55)
    form = (form - form.mean()) / (form.std() + 1e-6)
    fib = S.fibres(shape, count=w * h / (ss * ss) * 0.10, length=9 * ss, width=0.22 * ss,
                   seed=seed + 7, curl=0.5, lo=0.4, hi=1.0)
    fib2 = S.fibres(shape, count=w * h / (ss * ss) * 0.02, length=22 * ss, width=0.3 * ss,
                    seed=seed + 9, curl=0.35, lo=0.5, hi=1.0)
    fibs = S.blur(fib + 0.6 * fib2, 0.35 * ss / 4)
    fibs = fibs - fibs.mean()
    tex = 1.0 + 0.012 * form + 0.035 * fibs
    rel = 0.025 * fibs + 0.01 * form
    return tex.astype(np.float32), rel.astype(np.float32)
