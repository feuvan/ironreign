#!/usr/bin/env python3
"""Validate committed art against the DESIGN.md section 8 manifest (system python3, no Blender).

    python3 Tools/BlenderArt/check_art.py [--strict] [Content/Data]

* manifest.py and the DESIGN.md tables agree (sizes, paths)
* every present PNG has the exact size, is RGBA, transparent assets have alpha, map/board sprites
  have a clear 1 px border, white tint plates are neutral (R = G = B within 1 level on average)
* missing files are listed (the UI tolerates them); ``--strict`` makes them an error

Exit status 1 on any error.  Used by ``styleframes/run_all.sh``-style batch scripts and CI.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from ironart import manifest, post  # noqa: E402


def main(argv):
    strict = "--strict" in argv
    args = [a for a in argv if not a.startswith("--")]
    repo = os.path.dirname(os.path.dirname(HERE))
    root = args[0] if args else os.path.join(repo, "Content", "Data")
    errors, missing = [], []
    for p in manifest.cross_check_design(os.path.join(repo, "docs", "DESIGN.md")):
        errors.append("manifest: " + p)
    for rel, e in sorted(manifest.MANIFEST.items()):
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            missing.append(rel)
            continue
        try:
            from PIL import Image
            mode = Image.open(path).mode
            img = post.load(path)
            manifest.validate(img, rel)
            if mode not in ("RGBA",):
                errors.append("%s: PNG mode %s (manifest says RGBA)" % (rel, mode))
            if e["tint"] == "white":
                mean, p99 = post.neutral_check(img)
                if mean > 1.0 or p99 > 4.0:
                    errors.append("%s: tint area not neutral (mean %.1f, p99 %.1f)" % (rel, mean, p99))
        except Exception as ex:  # noqa: BLE001 - report every problem
            errors.append(str(ex))
    print("[check_art] %d manifest entries, %d present, %d missing, %d errors"
          % (len(manifest.MANIFEST), len(manifest.MANIFEST) - len(missing), len(missing), len(errors)))
    for m in errors:
        print("  ERROR", m)
    if missing and (strict or len(missing) <= 20):
        for m in missing:
            print("  missing", m)
    return 1 if errors or (strict and missing) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
