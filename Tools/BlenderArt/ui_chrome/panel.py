"""Panel.png (128x128 9-slice, 24 px border): handmade xuan paper mounted in a slim dark
rosewood moulding with an inset gold-leaf bead; gilt-bronze corner mounts.

Cross-section (distance d from the outer edge, target px = mm; mitred like a picture frame):
    0-8.4   rosewood moulding, straight grain along the rail, clear coat (crown 2.9 mm)
    8.6-11  gold-leaf bead (round, 2.4 px)
    11-11.8 black-lacquer reveal (shadow line)
    11.8-24 paper, aged towards the frame -> Paper by d = 22
Centre (24..104): Paper with xuan "formation" clouds + fine bast fibres, faded in over 8 px from
the 9-slice boundary so the stretched strips stay uniform.  Corner mounts: Ming-style flat
gilt-bronze L plates over the mitre with spear tips, engraved border and a domed boss, inside the
24 px corners.
"""

import numpy as np

import kit
from ironart import ui_chrome_motifs as MO
from ironart import ui_chrome_sdf as S
from ironart.ui_chrome_maps import Maps, L

NAME = "Panel"
SPEC = dict(size=(128, 128), ss=4, spp=64, margins=(24, 24, 24, 24), seed=11)
W = H = 128
M = 24
#: albedo multiplier so the rendered flat field lands on Paper (measured, see build QA)
CAL_PAPER = (1.0, 1.0, 1.0)


def corner_mount(ss, T=8.4, M=24):
    """Gilt-bronze corner mount of the top-left corner on a local M x M grid, folded about the
    diagonal: a flat bevelled L plate over the mitre whose arms end in spear tips, a chamfered
    inner corner, an engraved border line and a domed boss.
    Returns (height, mask, engraving_mask, boss_mask)."""
    G = S.Grid(M, M, ss)
    u, v = MO.corner_fold(G)
    k = T / 8.4
    w = 2.9 * k
    tip = [(11.0 * k, T / 2 - w), (15.4 * k, T / 2 - w), (20.6 * k, T / 2), (15.4 * k, T / 2 + w),
           (11.0 * k, T / 2 + w)]
    spear = kit.fold_poly(G, tip)
    arm = np.minimum(S.sd_round_box_uv(u, v, 7.6 * k, T / 2, 7.6 * k, w, 0.5), spear)
    sq = S.sd_round_box_uv(u, v, 5.4 * k, 5.4 * k, 5.4 * k, 5.4 * k, 0.6)
    sq = np.maximum(sq, (u + v - 14.2 * k) / np.sqrt(2))
    guard = np.minimum(arm, sq)
    bc = 4.6 * k
    boss = np.hypot(u - bc, v - bc) - 2.1 * k
    z = S.round_relief(guard, 0.5, 0.42)
    eng = np.abs(guard + 0.85)
    eng = np.where(np.hypot(u - bc, v - bc) < 3.0 * k, 9.0, eng)
    eng = np.minimum(eng, np.where((u > 11.0 * k) & (u < 16.6 * k), np.abs(v - T / 2), 9.0))
    z = z + S.groove(eng, 0.32, 0.15) * (guard < -0.25)
    z = z + MO.dome(boss, 1.0, 0.6) + S.groove(np.abs(boss + 0.7 * k), 0.26, 0.1)
    return (z.astype(np.float32), S.aa_mask(guard, G), S.aa_mask(eng - 0.2, G),
            S.aa_mask(boss, G))


def build(G, variant=None):
    d = S.inset_distance(G, W, H, r=2.5)
    m = Maps(G.shape, base="#E9DCC0")
    # ---- cross-section --------------------------------------------------------------------
    pts = [(-1, 0.0), (0.0, 0.3), (0.5, 1.4), (1.3, 2.35), (2.4, 2.75), (3.6, 2.9), (4.9, 2.75),
           (5.9, 2.35), (6.35, 2.05), (6.6, 1.92), (7.5, 1.92), (8.0, 1.6), (8.4, 1.05)]
    pts += kit.bead(9.8, 1.2, 0.95)
    pts += [(11.05, 0.9), (11.25, 0.55), (11.75, 0.45), (12.3, 0.42), (30, 0.42)]
    z = S.Profile(pts, round_px=0.14)(d)

    wood = S.band(d, -5, 8.45, G)
    gold = S.band(d, 8.45, 11.05, G)
    reveal = S.band(d, 11.05, 11.8, G)
    paper = S.band(d, 11.8, 999, G)

    # ---- rosewood ---------------------------------------------------------------------------
    g = kit.grain1d(d, 3)
    m.paint(wood, "rosewood", base=L("#5E2C1D"))
    m.tint(wood, g)
    m.tint(S.band(d, 6.3, 7.6, G), 0.72)          # fillet in shade
    m.tint(S.band(d, 7.9, 8.45, G), 0.55)         # dark arris at the inner edge
    m.paint(wood, rough=0.30 + 0.12 * (1 - (g - 0.5) / 0.8))

    # ---- gold-leaf bead + reveal ----------------------------------------------------------------
    m.paint(gold, "gold")
    m.paint(reveal, "lacquer_black", base=L("#24150F"))

    # ---- paper ---------------------------------------------------------------------------------
    t = kit.smoothstep(12.0, 22.0, d)
    base = kit.lerp3(L("#D3C29E"), L("#E9DCC0"), t) * np.array(CAL_PAPER, np.float32)
    m.paint(paper, "paper", base=base)
    cm = kit.centre_mask(G, W, H, (M, M, M, M))
    tex, rel = kit.xuan(G.shape, G.ss, seed=5)
    m.tint(paper * cm, tex)
    z = z + rel * cm * paper

    # ---- corner mounts ---------------------------------------------------------------------------
    gz, gm, ge, gb = (kit.stamp(G, a) for a in corner_mount(G.ss))
    z = z * (1 - gm) + np.maximum(z, 2.95 + gz) * gm
    m.paint(gm, "gold_satin")
    m.tint(gm, kit.recess_shade(gz, G.ss))
    m.tint(gm * ge, 0.6)
    m.paint(gm * ge, rough=0.5)
    m.paint(gb, rough=0.18)

    m.height = z.astype(np.float32)
    m.alpha = S.aa_mask(-d, G)
    return m
