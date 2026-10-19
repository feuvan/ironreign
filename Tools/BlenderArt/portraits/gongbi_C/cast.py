"""Render the whole cast (102 portraits + unknown) with gongbi_C.

    python3 portraits/gongbi_C/cast.py <out_dir> [--jobs N] [--only m_warrior]

Each key goes through make.sh (Blender 3D stage, then the 2D stage).  With the 4 shared cores,
--jobs 2 keeps two portraits in flight (the 2D stage of one overlaps the render of the next).
"""

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import wardrobe  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    keys = [k for k in wardrobe.roster() if k.startswith(a.only)]
    t0 = time.time()

    def one(k):
        t = time.time()
        r = subprocess.run([os.path.join(HERE, "make.sh"), a.out, k], capture_output=True, text=True)
        ok = r.returncode == 0 and os.path.exists(os.path.join(a.out, k + ".png"))
        print("%-14s %s %.1fs" % (k, "ok" if ok else "FAILED", time.time() - t), flush=True)
        return ok
    with ThreadPoolExecutor(a.jobs) as ex:
        res = list(ex.map(one, keys))
    print("%d/%d ok in %.1f min" % (sum(res), len(res), (time.time() - t0) / 60))


if __name__ == "__main__":
    main()
