"""Render cast portraits by key (one Blender process renders many portraits).

  render.sh portraits/gongbi_B/render_cast.py <out_dir> <key> [<key> ...]
  render.sh portraits/gongbi_B/render_cast.py <out_dir> all

Keys are the scenario portrait keys (m_warrior_01 .. f_elder_04, unknown).  Every character
passes :func:`canon.check` (face-design rules + policy guard) before it is drawn.  Writes
<key>.png (384x480), <key>_192.png, <key>_96.png and <key>.json (timing, officer); keeps
<key>_raw3x.png only with GONGBI_KEEP_RAW=1.
"""
import json
import os
import time

from ironart import scene as S
import backend
import canon
import cast
import finish
import portrait


def main():
    a = S.args()
    out = a[0]
    os.makedirs(out, exist_ok=True)
    keys = cast.all_keys() if a[1:] == ["all"] else a[1:]
    keep = os.environ.get("GONGBI_KEEP_RAW") == "1"
    for key in keys:
        t0 = time.time()
        if key == "unknown":
            cv = portrait.draw_unknown()
            officer = None
        else:
            ch = cast.generate(key)
            canon.check(ch)
            cv, fd, T = portrait.draw(ch)
            canon.check_drawn(fd, key)
            officer = getattr(ch, "officer", None)
        raw = os.path.join(out, key + "_raw3x.png")
        t_draw = time.time() - t0
        backend.render(cv, raw, ss=3, samples=5)
        t_render = time.time() - t0 - t_draw
        finish.finish(raw, os.path.join(out, key + ".png"), os.path.join(out, key + "_192.png"),
                      os.path.join(out, key + "_96.png"))
        if not keep:
            os.remove(raw)
        tot = time.time() - t0
        with open(os.path.join(out, key + ".json"), "w") as f:
            json.dump(dict(key=key, officer=officer, seconds=round(tot, 2),
                           draw=round(t_draw, 2), render=round(t_render, 2),
                           primitives=len(cv.prims)), f)
        print("[gongbi] %s total %.1fs" % (key, tot))


main()
