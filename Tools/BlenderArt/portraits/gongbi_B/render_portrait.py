"""Render gongbi portraits.

  render.sh portraits/gongbi_B/render_portrait.py <out_dir> <key> [<key> ...]

Writes <key>.png (384x480) and <key>_192.png; keeps <key>_raw3x.png for inspection.
"""
import os
import sys
import time

import numpy as np

from ironart import scene as S
import backend
import characters
import finish
import portrait


def main():
    a = S.args()
    out = a[0]
    keys = a[1:] or list(characters.HEROES)
    os.makedirs(out, exist_ok=True)
    for key in keys:
        t0 = time.time()
        ch = characters.HEROES[key]()
        cv, fd, T = portrait.draw(ch)
        raw = os.path.join(out, key + "_raw3x.png")
        backend.render(cv, raw, ss=3, samples=5)
        finish.finish(raw, os.path.join(out, key + ".png"), os.path.join(out, key + "_192.png"))
        print("[gongbi] %s total %.1fs" % (key, time.time() - t0))


main()
