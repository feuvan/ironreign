"""Contact sheet of the approach-B heroes (system python3 or Blender python).

    python3 make_sheet.py <dir>   -> <dir>/sheet_1x.png (192x240 each) + sheet_2x.png (384x480 each)
"""
import os
import sys

from PIL import Image, ImageDraw

NAMES = ["hero_warlord", "hero_scholar", "hero_elder"]


def sheet(d, suffix, size, out, pad=12, bg=(27, 23, 18)):
    ims = [Image.open(os.path.join(d, n + suffix)).convert("RGB") for n in NAMES]
    W = len(ims) * (size[0] + pad) + pad
    H = size[1] + 2 * pad + 18
    s = Image.new("RGB", (W, H), bg)
    dr = ImageDraw.Draw(s)
    for i, (n, im) in enumerate(zip(NAMES, ims)):
        x = pad + i * (size[0] + pad)
        s.paste(im.resize(size, Image.LANCZOS) if im.size != size else im, (x, pad))
        dr.text((x, pad + size[1] + 3), n, fill=(233, 220, 192))
    s.save(os.path.join(d, out))


if __name__ == "__main__":
    d = sys.argv[1]
    sheet(d, "_192x240.png", (192, 240), "sheet_1x.png")
    sheet(d, ".png", (384, 480), "sheet_2x.png")
