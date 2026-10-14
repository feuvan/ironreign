"""Archetype check sheet: warrior, scholar and female busts side by side (run before any batch).

    Tools/BlenderArt/render.sh Tools/BlenderArt/styleframes/sf_archetypes.py [out_dir] [--final]

Renders each :data:`ironart.figure.ARCHETYPES` entry through the same portrait recipe as style
frame (d) - preview quality (2x, 24 spp) unless ``--final`` - runs the portrait QA on each and
writes ``portrait_archetypes.png`` (1:1 and on the Night UI colour).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

from ironart import post, scene  # noqa: E402

import sf_portrait  # noqa: E402

KINDS = ("warrior", "scholar", "female")
SEEDS = {"warrior": 21, "scholar": 33, "female": 45}


def main():
    a = [x for x in scene.args() if not x.startswith("--")]
    out = a[0] if a else os.path.join(os.environ["IRONART_OUT"], "styleframes")
    os.makedirs(out, exist_ok=True)
    final = "--final" in sys.argv
    items, fails = [], []
    for k in KINDS:
        img, times, q = sf_portrait.render_bust(out, kind=k, seed=SEEDS[k], preview=not final,
                                                tag="arch_%s" % k)
        bad = [n for n, ok, _ in q.rows if not ok] if q is not None else []
        if bad:
            fails.append("%s: %s" % (k, ", ".join(bad)))
        items.append((img, "%s (%.0fs)" % (k, times["render"])))
    big = [(post.resize(i, (384, 480), "lanczos"), lab + " x2") for i, lab in items]
    sheet = post.contact_sheet(items + big, cols=3)
    post.save(sheet, os.path.join(out, "portrait_archetypes.png"))
    print("[ironart] wrote portrait_archetypes.png")
    if fails:
        raise AssertionError("archetype QA failed: " + "; ".join(fails))


if __name__ == "__main__":
    main()
