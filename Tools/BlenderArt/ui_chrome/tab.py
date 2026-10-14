"""Tab.png / Tab_Active.png (160x48 9-slice, margins l 18, t 14, r 18, b 10): lighter variants
of the button - a slim gold bead around the top and sides (the bottom is open: tabs sit on the
panel below), rounded top corners.

    inactive  lacquered rosewood plaque, straight horizontal grain (a function of y only, so it
              stretches cleanly sideways), satin gold bead, darkening towards the bottom edge
    active    cinnabar lacquer plaque, bright gold bead, a gold underline bar along the bottom
              edge (y 44.6-47) with a warm glow rising from it

The UI tints the inactive tab x0.78 (normal) and shows it unmodified on hover; text is TextLight
(inactive) / Gold (active), 13 px.
"""

import numpy as np

import kit
from ironart import ui_chrome_sdf as S
from ironart.ui_chrome_maps import Maps, L

NAME = "Tab"
SPEC = dict(size=(160, 48), ss=4, spp=64, margins=(18, 14, 18, 10), seed=31)
W, H = 160, 48
VARIANTS = ("inactive", "active")
FILE = {"inactive": "Tab", "active": "Tab_Active"}


def build(G, variant="inactive"):
    active = variant == "active"
    ext = 60.0
    d = -S.sd_round_box(G, W / 2, (H + ext) / 2, W / 2, (H + ext) / 2, 6.0)
    m = Maps(G.shape, base="#7E1F17")
    zf = 0.75
    pts = [(-1, 0.0), (0.0, 0.25), (0.45, 0.8), (0.9, 0.95)]
    pts += kit.bead(1.9, 0.95, 0.9)
    pts += [(2.95, 0.9), (3.2, 0.7), (3.7, 0.66), (4.4, zf), (60, zf)]
    z = S.Profile(pts, round_px=0.12)(d)
    lip = S.band(d, -5, 0.95, G)
    gold = S.band(d, 0.95, 2.9, G)
    groove = S.band(d, 2.9, 3.75, G)
    field = S.band(d, 3.75, 999, G)
    # gentle cylindrical plaque across the visible height
    yy = np.clip(np.abs(G.Y - (H / 2 - 2)) / (H / 2 - 2), 0, 1)
    z = z + 0.35 * (1 - yy ** 2) * kit.smoothstep(4.0, 7.0, d) * field

    def lac(col, k=1.0, rough=0.42):
        return dict(base=L(col, k), metal=0.0, rough=rough, coat=1.0, spec=0.06)

    if active:
        m.paint(lip, lac("#2A0B07"))
        m.paint(gold, "gold")
        m.paint(groove, lac("#3A0E09"))
        m.paint(field, lac("#7E1F17"))
        m.tint(field, kit.vgrad(G, H, 0.10))
        # gold underline bar + glow above it
        bar = S.band(G.Y, H - 3.4, H + 5, G)
        bz = S.Profile([(H - 3.6, 0.0), (H - 3.3, 0.55), (H - 2.2, 0.85), (H - 1.2, 0.85),
                        (H - 0.3, 0.55), (H, 0.4)], round_px=0.12)(G.Y)
        z = np.where(bar > 0, np.maximum(z, zf + bz), z)
        m.paint(bar, "gold")
        glow = np.clip(1.0 - (H - 3.4 - G.Y) / 9.0, 0, 1) ** 2 * (G.Y < H - 3.4) * field
        m.emit = m.emit + np.array([0.06, 0.022, 0.006], np.float32) * glow[..., None]
    else:
        m.paint(lip, lac("#1A0F0A"))
        m.paint(gold, "gold_satin")
        m.paint(groove, lac("#1E120C"))
        g = kit.grain1d(G.Y, 8, freq=0.55, lo=0.62, hi=1.25)
        m.paint(field, lac("#5A3A28", rough=0.36))
        m.tint(field, g)
        # towards the bottom the plaque falls into the panel's shadow
        m.tint(field, 1.0 - 0.35 * kit.smoothstep(H - 16.0, H, G.Y))
        m.tint(field, kit.vgrad(G, H, 0.06))
    m.height = z.astype(np.float32)
    m.alpha = S.aa_mask(-d, G)
    return m
