"""Contact sheets for gongbi_C.

    python3 make_sheet.py heroes <dir>            -> <dir>/sheet.png (three heroes, 1152x480)
    python3 make_sheet.py cast <dir> <out.png> [cols] [--thumb 96]
"""

import glob
import os
import sys

from PIL import Image

HEROES = ("hero_warlord", "hero_scholar", "hero_elder")


def heroes(d):
    ims = [Image.open(os.path.join(d, h + ".png")).convert("RGB") for h in HEROES]
    sh = Image.new("RGB", (384 * len(ims), 480), (40, 36, 32))
    for i, im in enumerate(ims):
        sh.paste(im, (i * 384, 0))
    sh.save(os.path.join(d, "sheet.png"), optimize=True)


def cast(d, out, cols=6, thumb=None):
    fs = sorted(f for f in glob.glob(os.path.join(d, "*.png"))
                if not f.endswith(("_192.png", "_master.png")) and "sheet" not in f
                and "cast" not in os.path.basename(f))
    w, h = (192, 240) if not thumb else (thumb, int(thumb * 1.25))
    g = 6
    rows = (len(fs) + cols - 1) // cols
    sh = Image.new("RGB", (cols * (w + g) + g, rows * (h + g) + g), (40, 36, 32))
    for i, f in enumerate(fs):
        im = Image.open(f).convert("RGB").resize((w, h), Image.LANCZOS)
        sh.paste(im, (g + (i % cols) * (w + g), g + (i // cols) * (h + g)))
    sh.save(out, optimize=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "heroes":
        heroes(a[1])
    else:
        th = None
        if "--thumb" in a:
            th = int(a[a.index("--thumb") + 1])
            a = a[:a.index("--thumb")]
        cast(a[1], a[2], int(a[3]) if len(a) > 3 else 6, th)
