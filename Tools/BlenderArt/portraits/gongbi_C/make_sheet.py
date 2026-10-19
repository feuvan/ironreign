"""Side-by-side sheet of 384x480 portraits: python3 make_sheet.py <dir> <out.png> name..."""
import sys

from PIL import Image


def main():
    d, out, names = sys.argv[1], sys.argv[2], sys.argv[3:]
    ims = [Image.open("%s/%s.png" % (d, n)).convert("RGB") for n in names]
    W = sum(i.width for i in ims)
    sheet = Image.new("RGB", (W, max(i.height for i in ims)), (230, 214, 176))
    x = 0
    for im in ims:
        sheet.paste(im, (x, 0))
        x += im.width
    sheet.save(out)


if __name__ == "__main__":
    main()
