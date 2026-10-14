"""Render several portraits in one Blender session.

    blender -b --factory-startup -noaudio -P batch.py -- <out dir> key1 key2 ... [--ss 3]
          [--samples 6] [--scenario path/to/BrokenMandate.json]

Keys are hero specs (specs.py) or canon keys like m_warrior_07; with --scenario the officer
using that portrait key supplies age and gender.
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import portrait  # noqa: E402
import specs  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    opts = {}
    keys = []
    i = 0
    out = argv[0]
    i = 1
    while i < len(argv):
        if argv[i].startswith("--"):
            opts[argv[i][2:]] = argv[i + 1]
            i += 2
        else:
            keys.append(argv[i])
            i += 1
    officers = {}
    start = 212
    if "scenario" in opts:
        d = json.load(open(opts["scenario"]))
        start = d.get("startYear", 212)
        officers = {o["portrait"]: o for o in d["officers"]}
    times = {}
    for k in keys:
        t0 = time.time()
        if k in specs.REG:
            sp = specs.get(k)
        else:
            import canon
            sp = canon.spec(k, officers.get(k), start)
        portrait.run(sp, out, int(opts.get("ss", 3)), int(opts.get("samples", 6)))
        times[k] = time.time() - t0
    for k, t in times.items():
        print("[batch] %-16s %.1fs" % (k, t))


main()
