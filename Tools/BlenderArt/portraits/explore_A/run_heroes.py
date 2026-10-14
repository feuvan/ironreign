#!/usr/bin/env python3
"""Render the three Approach A hero portraits and their contact sheets.

    python3 run_heroes.py [out_dir] [--samples N] [--only warlord,scholar,elder]

Writes <out>/hero_<name>.png (384x480), hero_<name>_192.png (192x240), hero_<name>_full.png
(768x960 painted), *_times.json, and A_sheet_1x.png / A_sheet_2x.png.
"""
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = "/tmp/claude-0/-home-user-ironreign/7c9c7cee-d827-5b3c-8cb6-e644913e9b45/scratchpad/portraits/A"


def main():
    a = sys.argv[1:]
    out = a[0] if a and not a[0].startswith("--") else DEFAULT_OUT
    samples = a[a.index("--samples") + 1] if "--samples" in a else "32"
    only = a[a.index("--only") + 1].split(",") if "--only" in a else ["warlord", "scholar", "elder"]
    work = os.path.join(out, "work")
    os.makedirs(work, exist_ok=True)
    subprocess.run([sys.executable, os.path.join(HERE, "heroes.py")], check=True)
    for h in only:
        t = time.time()
        subprocess.run(["nice", "-n", os.environ.get("IRONART_NICE", "5"), "blender", "-b", "--factory-startup",
                        "-noaudio", "-P", os.path.join(HERE, "portrait.py"), "--",
                        os.path.join(HERE, "specs", "hero_%s.json" % h), work, "--samples", samples], check=True,
                       stdout=subprocess.DEVNULL)
        for suf in ("", "_192", "_full"):
            shutil.copy(os.path.join(work, "hero_%s%s.png" % (h, suf)), os.path.join(out, "hero_%s%s.png" % (h, suf)))
        shutil.copy(os.path.join(work, "hero_%s_times.json" % h), os.path.join(out, "hero_%s_times.json" % h))
        print("[heroes] %s done in %.0fs: %s" % (h, time.time() - t,
              json.load(open(os.path.join(out, "hero_%s_times.json" % h)))))
    names = ["warlord", "scholar", "elder"]
    labels = "Warlord (Yan Tieshan),Strategist (Su Wanqing),Sage (elder)"
    for scale, suf in ((1, "_192"), (2, "")):
        files = [os.path.join(out, "hero_%s%s.png" % (n, suf)) for n in names]
        if all(os.path.exists(f) for f in files):
            subprocess.run([sys.executable, os.path.join(HERE, "sheet.py"), os.path.join(out, "A_sheet_%dx.png" % scale),
                            str(scale)] + files + ["--labels", labels], check=True)


if __name__ == "__main__":
    main()
