#!/usr/bin/env python3
"""Contact sheets: python3 sheet.py <out.png> <scale 1|2> <img> [<img> ...] [--labels a,b,c]"""
import sys

from PIL import Image, ImageDraw


def main():
    a = sys.argv[1:]
    labels = None
    if "--labels" in a:
        i = a.index("--labels")
        labels = a[i + 1].split(",")
        a = a[:i] + a[i + 2:]
    out, scale, files = a[0], int(a[1]), a[2:]
    W, H = 192 * scale, 240 * scale
    pad, lab = 12, 18
    sheet = Image.new("RGB", (pad + len(files) * (W + pad), pad * 2 + H + lab), (27, 23, 18))
    d = ImageDraw.Draw(sheet)
    for k, f in enumerate(files):
        im = Image.open(f).convert("RGB")
        if im.size != (W, H):
            im = im.resize((W, H), Image.LANCZOS)
        x = pad + k * (W + pad)
        # thin gold frame like the in-game portrait frame
        d.rectangle((x - 2, pad - 2, x + W + 1, pad + H + 1), outline=(150, 118, 60))
        sheet.paste(im, (x, pad))
        if labels and k < len(labels):
            d.text((x, pad + H + 4), labels[k], fill=(220, 205, 175))
    sheet.save(out)


if __name__ == "__main__":
    main()
