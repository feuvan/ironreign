#!/usr/bin/env python3
"""Batch-render the cast (specs/cast/*.json from cast.py) with Approach A.

    python3 build_cast.py [--ids m_warrior_01,f_scholar_04] [--out DIR] [--samples 32]
                          [--preview] [--jobs 1] [--deliver]

Without ``--deliver`` everything stays in the scratch ``--out`` directory.  With ``--deliver``
(Build phase only) each portrait is copied to
    Content/Data/Art/Portraits/<id>.png        192x240 opaque
    ArtSource/Portraits/<id>@2x.png            384x480
and Content/Data/Art/Portraits/manifest.json is written from the cast manifest draft.
Renders are resumable: an id whose @2x output exists is skipped unless --force.
"""
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
SCRATCH = "/tmp/claude-0/-home-user-ironreign/7c9c7cee-d827-5b3c-8cb6-e644913e9b45/scratchpad/portraits/A/cast"


def arg(a, name, default=None):
    return a[a.index(name) + 1] if name in a else default


def main():
    a = sys.argv[1:]
    out = arg(a, "--out", SCRATCH)
    samples = arg(a, "--samples", "16" if "--preview" in a else "32")
    spec_dir = os.path.join(HERE, "specs", "cast")
    if not os.path.isdir(spec_dir):
        subprocess.run([sys.executable, os.path.join(HERE, "cast.py"), spec_dir], check=True)
    ids = arg(a, "--ids")
    ids = ids.split(",") if ids else sorted(f[:-5] for f in os.listdir(spec_dir) if f.endswith(".json") and not f.startswith("manifest"))
    os.makedirs(out, exist_ok=True)
    work = os.path.join(out, "work")
    os.makedirs(work, exist_ok=True)
    times = {}
    for pid in ids:
        final2x = os.path.join(out, pid + ".png")
        if os.path.exists(final2x) and "--force" not in a:
            continue
        t = time.time()
        cmd = ["nice", "-n", os.environ.get("IRONART_NICE", "5"), "blender", "-b", "--factory-startup", "-noaudio",
               "-P", os.path.join(HERE, "portrait.py"), "--", os.path.join(spec_dir, pid + ".json"), work,
               "--samples", samples]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if r.returncode != 0 or not os.path.exists(os.path.join(work, pid + ".png")):
            print("[cast] FAILED %s\n%s" % (pid, "\n".join(r.stdout.splitlines()[-25:])))
            continue
        for suf in ("", "_192"):
            shutil.copy(os.path.join(work, pid + suf + ".png"), os.path.join(out, pid + suf + ".png"))
        times[pid] = round(time.time() - t, 1)
        print("[cast] %s %.0fs" % (pid, times[pid]), flush=True)
        # keep scratch small: drop the 2x passes once painted
        for f in os.listdir(work):
            if f.startswith(pid + "_") and ("0001.png" in f or f.endswith("_raw.png")):
                os.remove(os.path.join(work, f))
    if "--deliver" in a:
        art = os.path.join(REPO, "Content", "Data", "Art", "Portraits")
        src = os.path.join(REPO, "ArtSource", "Portraits")
        os.makedirs(art, exist_ok=True)
        os.makedirs(src, exist_ok=True)
        for pid in ids:
            if os.path.exists(os.path.join(out, pid + ".png")):
                shutil.copy(os.path.join(out, pid + "_192.png"), os.path.join(art, pid + ".png"))
                shutil.copy(os.path.join(out, pid + ".png"), os.path.join(src, pid + "@2x.png"))
        man = json.load(open(os.path.join(spec_dir, "manifest_draft.json")))
        with open(os.path.join(art, "manifest.json"), "w") as f:
            json.dump(man, f, indent=1)
    print("[cast] done", times)


if __name__ == "__main__":
    main()
