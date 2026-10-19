"""Pure-numpy pieces of the hair / gear design shared by Blender (gear.py) and the 2D stage."""

import math

import numpy as np

import geo


def hairline(hp, t):
    """Hairline height z(t) round the head (t = 0 front, +-pi back)."""
    at = np.abs(np.asarray(t, np.float64))
    hz = hp.get("line_z", 0.36)                   # 三庭: hairline-brow = brow-nose = nose-chin
    temple = hp.get("temple_z", hz - 0.11)        # temple corners (M recession for elders)
    side = hp.get("side_z", 0.0)                  # bottom of the sideburn in front of the ear
    over = hp.get("over_ear_z", 0.12)             # hair line over the ear
    nape = hp.get("nape_z", -0.22)
    widow = hp.get("widow", 0.0)
    xs = [0.0, 0.18, 0.40, 0.80, 0.98, 1.12, 1.28, 1.48, 1.75, 1.95, math.pi]
    zs = [hz - widow, hz - 0.006, hz - hp.get("arch", 0.03), temple, temple - 0.05,
          side + 0.07, side, over, over, nape + 0.05, nape]
    return geo.pchip(xs, zs, at)
