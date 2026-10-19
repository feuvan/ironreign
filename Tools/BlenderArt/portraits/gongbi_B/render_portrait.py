"""Render the hand-built hero portraits.

  render.sh portraits/gongbi_B/render_portrait.py <out_dir> [<key> ...]

Writes <key>.png (384x480), <key>_192.png, <key>_96.png; keeps raw/<key>_raw3x.png for
inspection.  Every hero passes the canon gate first.
"""
import os
import time

from ironart import scene as S
import backend
import canon
import characters
import finish
import portrait


def main():
    a = S.args()
    out = a[0]
    keys = a[1:] or list(characters.HEROES)
    os.makedirs(os.path.join(out, "raw"), exist_ok=True)
    for key in keys:
        t0 = time.time()
        ch = characters.HEROES[key]()
        canon.check(ch)
        cv, fd, T = portrait.draw(ch)
        canon.check_drawn(fd, key)
        raw = os.path.join(out, "raw", key + "_raw3x.png")
        backend.render(cv, raw, ss=3, samples=5)
        finish.finish(raw, os.path.join(out, key + ".png"), os.path.join(out, key + "_192.png"),
                      os.path.join(out, key + "_96.png"))
        print("[gongbi] %s total %.1fs" % (key, time.time() - t0))


main()
