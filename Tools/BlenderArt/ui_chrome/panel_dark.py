"""PanelDark.png (128x128 9-slice, 24 px border): deep black lacquer with mother-of-pearl and
gold inlay trim.

Cross-section (d from the outer edge, px = mm, mitred):
    0-5.8    black-lacquer rim, flat top between crisp rounded arrises, glassy coat
    5.9-7.9  gold bead
    7.9-11.8 lacquer band with an inlaid mother-of-pearl strip (9.45-10.45, flush; the shell's
             pastel play of colour runs *across* the strip so it stretches cleanly)
    11.8-12.9 gold fillet, 13-13.8 bevel down to the field
    field    Night #1B1712 in the strips, lifted to #2A2119 in the middle of the 9-slice centre
Corners: a raden (mother-of-pearl) ruyi head inlaid flush in the field corner - small nacre
pieces with hairline lacquer gaps, point to the corner, lobes to the panel - outlined and curled
in raised gold wire, inside the 24 px corners.
"""

import numpy as np

import kit
from ironart import ui_chrome_motifs as MO
from ironart import ui_chrome_sdf as S
from ironart.ui_chrome_maps import Maps, L

NAME = "PanelDark"
SPEC = dict(size=(128, 128), ss=4, spp=48, margins=(24, 24, 24, 24), seed=12)
W = H = 128
M = 24


def corner_inlay(ss):
    """Top-left corner on a 24 x 24 grid: (shell mask, shell colour, gap mask, shell relief,
    wire height, wire mask).  The ruyi is raden work - small nacre pieces with hairline gaps -
    outlined in raised gold wire, its curls drawn in gold wire too."""
    G = S.Grid(M, M, ss)
    F = kit.Folded(G.X, G.Y)
    sd, eng = MO.ruyi(F, 16.6, 16.6, 8.6, rot=135.0)        # max reach x = 22.9 < 24
    wire = np.abs(sd + 0.15) - 0.42
    wire = np.minimum(wire, eng - 0.2)
    wm = S.aa_mask(wire, G)
    wz = S.round_relief(wire, 0.45, 0.3)
    shell = S.aa_mask(sd, G)
    col, gaps, rel = kit.raden(G, shell, seed=77, cell=1.9)
    return shell, col, gaps, rel, wz, wm


def build(G, variant=None):
    d = S.inset_distance(G, W, H, r=2.5)
    m = Maps(G.shape, base="#1B1712")
    # rim: a flat lacquer top (mirrors the dark ceiling: deep black) between two crisp
    # rounded arrises that catch the studio light as fine highlight lines
    pts = [(-1, 0.0), (0.0, 0.25), (0.35, 1.45), (0.9, 2.15), (1.5, 2.32), (4.5, 2.32),
           (5.1, 2.12), (5.55, 1.7), (5.85, 1.45)]
    pts += kit.bead(6.9, 1.0, 1.35)
    pts += [(7.95, 1.32), (8.2, 1.28), (11.7, 1.28), (11.85, 1.5), (12.85, 1.5), (13.0, 1.25),
            (13.8, 0.62), (14.4, 0.6), (40, 0.6)]
    z = S.Profile(pts, round_px=0.12)(d)

    rim = S.band(d, -5, 5.9, G)
    gold = S.band(d, 5.9, 7.95, G)
    bandl = S.band(d, 7.95, 11.8, G)
    fillet = S.band(d, 11.8, 12.95, G)
    field = S.band(d, 12.95, 999, G)
    shell_strip = S.band(d, 9.45, 10.45, G)

    m.paint(rim, "lacquer_black", base=kit.coat_cal(L("#1E1914")))
    m.paint(gold, "gold")
    m.paint(bandl, "lacquer_black", base=kit.coat_cal(L("#17130F")))
    # mother-of-pearl strip: pastel interference colours ACROSS the strip (stretch-safe)
    t = np.clip((d - 9.45) / 1.0, 0, 1)
    pearl = (kit.lerp3(L("#E7C9D4"), L("#C9E2DA"), kit.smoothstep(0.0, 0.55, t)) * (1 - kit.smoothstep(0.5, 1.0, t))[..., None]
             + kit.lerp3(L("#C9E2DA"), L("#CFD9F0"), kit.smoothstep(0.5, 1.0, t)) * kit.smoothstep(0.5, 1.0, t)[..., None])
    m.paint(shell_strip, "pearl", base=pearl * 0.42 * L("#FFE6D8", 1.0) / L("#FFFFFF"), mop=0.0)
    m.paint(fillet, "gold_satin")
    lift = kit.centre_mask(G, W, H, (M, M, M, M), fade=34.0)
    fb = kit.lerp3(kit.coat_cal(L("#1B1712")), kit.coat_cal(L("#2A2119")), lift)
    m.paint(field, "lacquer_black", base=fb)

    # ---- corner ruyi inlays -----------------------------------------------------------------------
    shell, col, gaps, rel, wz, wm = corner_inlay(G.ss)
    shell, gaps, wz, wm = (kit.stamp(G, a) for a in (shell, gaps, wz, wm))
    rel = kit.stamp_signed(G, rel)
    colf = np.dstack([kit.stamp(G, col[..., c]) for c in range(3)])
    # flush nacre pieces in the field corner (each tilted a hair) + raised gold wire outline
    z = z + rel * shell * (1 - wm) + wz * wm
    m.paint(shell, "pearl", base=colf, mop=0.35)
    m.paint(shell * gaps, "lacquer_black", base=kit.coat_cal(L("#1B1712")))
    m.paint(wm, "gold")
    m.height = z.astype(np.float32)
    m.alpha = S.aa_mask(-d, G)
    return m
