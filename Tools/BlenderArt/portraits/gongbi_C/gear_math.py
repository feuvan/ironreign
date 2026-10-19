"""Pure-numpy pieces of the hair / gear design shared by Blender (gear.py) and the 2D stage."""

import math

import numpy as np

import geo


def hairline(hp, t):
    """Hairline height z(t) round the head (t = 0 front, +-pi back)."""
    at = np.abs(np.asarray(t, np.float64))
    hz = hp.get("line_z", 0.30)
    temple = hp.get("temple_z", hz - 0.07)        # temple corners (M recession for elders)
    side = hp.get("side_z", -0.06)                # bottom of the sideburn in front of the ear
    over = hp.get("over_ear_z", 0.10)             # hair line over the ear
    nape = hp.get("nape_z", -0.30)
    widow = hp.get("widow", 0.0)
    xs = [0.0, 0.35, 0.80, 0.98, 1.12, 1.28, 1.48, 1.75, 1.95, math.pi]
    zs = [hz - widow, hz - 0.01, temple, temple - 0.04, side + 0.06, side, over, over,
          nape + 0.05, nape]
    return geo.pchip(xs, zs, at)
