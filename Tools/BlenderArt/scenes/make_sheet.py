#!/usr/bin/env python3
"""Contact sheet of the Illustrated Scenes outputs (system python3 + Pillow).

    python3 Tools/BlenderArt/scenes/make_sheet.py [preview_dir] [out.png] [--width W]

Lays the 1x images out in a grid with labels (the Title and Duel are scaled to the event width).
"""
import os
import sys

from PIL import Image, ImageDraw

ORDER = ["Title", "Duel", "Court", "Battle", "Harvest", "Disaster", "Wanderer", "Sect", "Bandits",
         "Envoy", "Festival", "Plague", "Flood", "Omen"]


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    src = args[0] if args else "."
    out = args[1] if len(args) > 1 else os.path.join(src, "..", "scenes_sheet.png")
    w = 640
    if "--width" in argv:
        w = int(argv[argv.index("--width") + 1])
    ims = []
    for n in ORDER:
        p = os.path.join(src, n + ".png")
        if os.path.exists(p):
            im = Image.open(p).convert("RGB")
            im = im.resize((w, int(round(im.height * w / im.width))), Image.LANCZOS)
            ims.append((n, im))
    if not ims:
        print("no images in", src)
        return 1
    cols = 3
    pad, lab = 8, 16
    h = max(i.height for _, i in ims)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (w + pad) + pad, rows * (h + pad + lab) + pad), (27, 23, 18))
    d = ImageDraw.Draw(sheet)
    for k, (n, im) in enumerate(ims):
        x = pad + (k % cols) * (w + pad)
        y = pad + (k // cols) * (h + pad + lab)
        sheet.paste(im, (x, y))
        d.text((x, y + h + 2), n, fill=(233, 220, 192))
    sheet.save(out)
    print("sheet", out, sheet.size)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
