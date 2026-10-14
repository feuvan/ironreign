"""Assemble sheet.png (heroes side by side at 384x480) and 96x120 review thumbnails.
python3 make_sheet.py <dir> key1 key2 ...  (system python, Pillow only)"""
import os
import sys
from PIL import Image

d = sys.argv[1]
keys = sys.argv[2:]
ims = [Image.open(os.path.join(d, k + ".png")).convert("RGB") for k in keys]
sheet = Image.new("RGB", (384 * len(ims), 480), (217, 198, 160))
for i, im in enumerate(ims):
    sheet.paste(im, (384 * i, 0))
sheet.save(os.path.join(d, "sheet.png"))
th = Image.new("RGB", (96 * len(ims) + 192 * len(ims) + 8 * len(ims), 240), (60, 50, 40))
x = 0
for k, im in zip(keys, ims):
    a = Image.open(os.path.join(d, k + "_192.png")).convert("RGB")
    th.paste(a, (x, 0))
    x += 196
for im in ims:
    th.paste(im.resize((96, 120), Image.LANCZOS), (x, 0))
    x += 100
th.save(os.path.join(d, "thumbs_review.png"))
