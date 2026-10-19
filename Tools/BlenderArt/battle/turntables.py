"""Turntable strips of every exported battle GLB, re-imported into a clean scene (review only).

    Tools/BlenderArt/render.sh Tools/BlenderArt/battle/turntables.py [names...]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import review  # noqa: E402


def main():
    fl = common.flags()
    names = ["Hex_" + t for t in common.TERRAINS] + ["Unit_" + u for u in common.UNITS] + ["Unit_Base"]
    want = fl["names"]
    if want:
        names = [n for n in names if n in want or n.split("_", 1)[1] in want]
    out = common.out("turntables")
    for n in names:
        p = os.path.join(common.MODELS_DIR, n + ".glb")
        if os.path.isfile(p):
            print("[battle] turntable", review.turntable(p, os.path.join(out, n + "_turntable.png")))


if __name__ == "__main__":
    main()
