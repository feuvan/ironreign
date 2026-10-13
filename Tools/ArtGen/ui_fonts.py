#!/usr/bin/env python3
"""Download the UI fonts (OFL) from github.com/google/fonts into Content/Data/Fonts/.

Pinned to a google/fonts commit and verified by SHA-256 so the result is reproducible.
Re-running is a no-op when the files are already present and valid.

    python3 Tools/ArtGen/ui_fonts.py [--force]

Files produced (see docs/DESIGN.md section 8):
    Body-Regular.ttf   Gentium Book Plus Regular   (SIL Open Font License 1.1)
    Body-Bold.ttf      Gentium Book Plus Bold      (SIL Open Font License 1.1)
    Heading.ttf        Marcellus Regular           (SIL Open Font License 1.1)
    Brush.ttf          Ma Shan Zheng Regular       (SIL Open Font License 1.1)
    OFL-<Family>.txt   the licence text shipped with each family
"""
import hashlib
import os
import sys
import urllib.request

COMMIT = "66928797f271fed5ee428544e7229685e2d90127"
BASE = "https://raw.githubusercontent.com/google/fonts/%s/ofl/" % COMMIT

# (source path inside google/fonts/ofl, destination file name, sha256)
FILES = [
    ("gentiumbookplus/GentiumBookPlus-Regular.ttf", "Body-Regular.ttf",
     "fe7b64eeacc430fcf46836a6f0dfe00d2c5a15483ed36692a2a185cb23ec2a5c"),
    ("gentiumbookplus/GentiumBookPlus-Bold.ttf", "Body-Bold.ttf",
     "b39c3fb12e2e15e2336f2ec6d051c778618ec25f7360bc4765bfe755b408c011"),
    ("gentiumbookplus/OFL.txt", "OFL-GentiumBookPlus.txt",
     "c309a440be606e283ccacc746662d714b9c5b5a7a0a10dd2514b90206b55ddfe"),
    ("marcellus/Marcellus-Regular.ttf", "Heading.ttf",
     "1cf0cd10b17d35e852729962cc1ffaffed94514895972458345e2df34abb2f81"),
    ("marcellus/OFL.txt", "OFL-Marcellus.txt",
     "715ba72697e14daa9b29a333545f69bde7c497b9f77d0a2a4c4a5a752d961801"),
    ("mashanzheng/MaShanZheng-Regular.ttf", "Brush.ttf",
     "6d2546bb189c732a8ca29af9e22457b152387d158aa459e4ac2ce1e51788b7fb"),
    ("mashanzheng/OFL.txt", "OFL-MaShanZheng.txt",
     "d7bdb1cee215b689e23c2f95672a6084c790542170648267a55114103d756a08"),
]

HERE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.normpath(os.path.join(HERE, "..", "..", "Content", "Data", "Fonts"))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    force = "--force" in sys.argv
    os.makedirs(DEST, exist_ok=True)
    ok = True
    for src, dst, digest in FILES:
        out = os.path.join(DEST, dst)
        if not force and os.path.exists(out) and sha256(out) == digest:
            print("ok      %s" % dst)
            continue
        url = BASE + src
        print("fetch   %s <- %s" % (dst, url))
        with urllib.request.urlopen(url, timeout=60) as r:
            data = r.read()
        got = hashlib.sha256(data).hexdigest()
        if got != digest:
            print("  ERROR sha256 mismatch: %s" % got)
            ok = False
            continue
        tmp = out + ".part"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, out)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
