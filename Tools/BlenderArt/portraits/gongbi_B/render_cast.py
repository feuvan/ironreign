"""Render generated cast portraits (one Blender process for many portraits).

  render.sh portraits/gongbi_B/render_cast.py <out_dir> <arch>:<idx> [...]
  render.sh portraits/gongbi_B/render_cast.py <out_dir> all
"""
import os
import time

from ironart import scene as S
import backend
import cast
import finish
import portrait


def main():
    a = S.args()
    out = a[0]
    os.makedirs(out, exist_ok=True)
    items = cast.all_keys() if a[1:] == ["all"] else [(x.split(":")[0], int(x.split(":")[1]))
                                                      for x in a[1:]]
    for arch, idx in items:
        t0 = time.time()
        ch = cast.generate(arch, idx)
        cv, fd, T = portrait.draw(ch)
        raw = os.path.join(out, ch.key + "_raw3x.png")
        backend.render(cv, raw, ss=3, samples=5)
        finish.finish(raw, os.path.join(out, ch.key + ".png"), os.path.join(out, ch.key + "_192.png"))
        print("[gongbi] %s total %.1fs" % (ch.key, time.time() - t0))


main()
