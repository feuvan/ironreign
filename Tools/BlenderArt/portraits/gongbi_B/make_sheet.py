"""Review sheets (system python, Pillow only).

  python3 make_sheet.py <dir> key1 key2 ...       sheet.png (384x480 side by side) and
                                                   thumbs_review.png (192 + 96 px versions)
  python3 make_sheet.py --contact <dir> key ...   contact_96.png (all keys at 96x120, labelled)
                                                   and timing.json (merged per-key timings)
"""
import json
import os
import sys

from PIL import Image, ImageDraw


def sheet(d, keys):
    ims = [Image.open(os.path.join(d, k + ".png")).convert("RGB") for k in keys]
    sh = Image.new("RGB", (384 * len(ims), 480), (217, 198, 160))
    for i, im in enumerate(ims):
        sh.paste(im, (384 * i, 0))
    sh.save(os.path.join(d, "sheet.png"))
    th = Image.new("RGB", (196 * len(ims) + 100 * len(ims), 240), (60, 50, 40))
    x = 0
    for k in keys:
        th.paste(Image.open(os.path.join(d, k + "_192.png")).convert("RGB"), (x, 0))
        x += 196
    for im in ims:
        th.paste(im.resize((96, 120), Image.LANCZOS), (x, 0))
        x += 100
    th.save(os.path.join(d, "thumbs_review.png"))


def contact(d, keys, cols=12):
    keys = [k for k in keys if os.path.exists(os.path.join(d, k + ".png"))]
    rows = (len(keys) + cols - 1) // cols
    sh = Image.new("RGB", (cols * 100, rows * 134), (50, 42, 34))
    dr = ImageDraw.Draw(sh)
    timing = {}
    for i, k in enumerate(keys):
        p96 = os.path.join(d, k + "_96.png")
        im = Image.open(p96 if os.path.exists(p96) else os.path.join(d, k + ".png")).convert("RGB")
        if im.size != (96, 120):
            im = im.resize((96, 120), Image.LANCZOS)
        x, y = (i % cols) * 100 + 2, (i // cols) * 134 + 2
        sh.paste(im, (x, y))
        dr.text((x, y + 120), k, fill=(220, 210, 190))
        js = os.path.join(d, k + ".json")
        if os.path.exists(js):
            with open(js) as f:
                timing[k] = json.load(f)
    sh.save(os.path.join(d, "contact_96.png"))
    if timing:
        secs = [v["seconds"] for v in timing.values()]
        summary = dict(count=len(secs), mean=round(sum(secs) / len(secs), 2), max=max(secs),
                       portraits=timing)
        with open(os.path.join(d, "timing.json"), "w") as f:
            json.dump(summary, f, indent=1)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "--contact":
        contact(a[1], a[2:])
    else:
        sheet(a[0], a[1:])
