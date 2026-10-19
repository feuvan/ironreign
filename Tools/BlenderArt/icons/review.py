"""Icons family: review images (system python3 or Blender's python).

    python3 Tools/BlenderArt/icons/review.py [--out DIR] [--only A,B] [--zoom]

* ``zoom_<n>.png``      each icon at 128 px on parchment and on black lacquer, 64 px, and the
                        in-game sizes (26 px on a cinnabar button, 20 px on the dark panel)
* ``context_mock.png``  the icons where the UI draws them: 26 px on the real Button.png beside a
                        label, 20-22 px value rows on the real Panel.png and PanelDark.png
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
for p in (HERE, TOOLS):
    if p not in sys.path:
        sys.path.insert(0, p)

from ironart import icons_gongbi as gb  # noqa: E402

UI = os.path.join(gb.REPO, "Content", "Data", "Art", "UI")


def _pil(img):
    from PIL import Image
    return Image.fromarray(gb.to8(img), "RGBA")


def zoom_sheet(items, path, per_row=4):
    from PIL import Image, ImageDraw
    b = gb.RECIPE["backgrounds"]
    cw, ch = 128 * 2 + 64 + 26 + 20 + 50, 128 + 22
    rows = int(math.ceil(len(items) / float(per_row)))
    W, H = per_row * cw + 10, rows * ch + 10
    sh = Image.new("RGBA", (W, H), (58, 50, 42, 255))
    d = ImageDraw.Draw(sh)
    f = gb._font(12)

    def col(name):
        return tuple(int(round(v * 255)) for v in gb.srgb(b[name])) + (255,)
    for k, (name, icons) in enumerate(items):
        x = 6 + (k % per_row) * cw
        y = 6 + (k // per_row) * ch
        for j, bg in enumerate(("parchment", "lacquer")):
            tile = Image.new("RGBA", (128, 128), col(bg))
            tile.alpha_composite(_pil(icons[128]))
            sh.paste(tile, (x + j * 130, y))
        t = Image.new("RGBA", (64, 64), col("panel"))
        t.alpha_composite(_pil(icons[64]))
        sh.paste(t, (x + 262, y))
        t = Image.new("RGBA", (64, 64), col("paneldark"))
        t.alpha_composite(_pil(icons[64]))
        sh.paste(t, (x + 262, y + 64))
        t = Image.new("RGBA", (30, 30), col("button"))
        t.alpha_composite(_pil(gb._scaled(icons[64], icons[128], 26)), (2, 2))
        sh.paste(t, (x + 330, y))
        t = Image.new("RGBA", (24, 24), col("paneldark"))
        t.alpha_composite(_pil(gb._scaled(icons[64], icons[128], 20)), (2, 2))
        sh.paste(t, (x + 330, y + 34))
        t = Image.new("RGBA", (24, 24), col("parchment"))
        t.alpha_composite(_pil(gb._scaled(icons[64], icons[128], 20)), (2, 2))
        sh.paste(t, (x + 330, y + 62))
        d.text((x, y + 130), name, fill=(233, 220, 192, 255), font=f)
    sh.save(path)
    return path


def _load_ui(name):
    from PIL import Image
    p = os.path.join(UI, name)
    return Image.open(p).convert("RGBA") if os.path.exists(p) else None


def _nine(img, margins, size):
    """Simple 9-slice stretch (Pillow) for the mock."""
    from PIL import Image
    l, t, r, b = margins
    W, H = img.size
    w, h = size
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    xs = [(0, l, 0, l), (l, W - r, l, w - r), (W - r, W, w - r, w)]
    ys = [(0, t, 0, t), (t, H - b, t, h - b), (H - b, H, h - b, h)]
    for sx0, sx1, dx0, dx1 in xs:
        for sy0, sy1, dy0, dy1 in ys:
            if sx1 > sx0 and sy1 > sy0 and dx1 > dx0 and dy1 > dy0:
                out.paste(img.crop((sx0, sy0, sx1, sy1)).resize((dx1 - dx0, dy1 - dy0),
                                                                 Image.BILINEAR), (dx0, dy0))
    return out


def context_mock(items, path):
    """The icons at their in-game sizes on the real UI chrome (Button 26 px, value rows 20-22
    px on Panel / PanelDark, order rows 24 px), at 2x zoom so the pixels can be judged."""
    from PIL import Image, ImageDraw
    btn = _load_ui("Button.png")
    pan = _load_ui("Panel.png")
    pdk = _load_ui("PanelDark.png")
    if btn is None or pan is None or pdk is None:
        return None
    fb = gb._font(16, "Body-Bold.ttf")
    fr = gb._font(15, "Body-Regular.ttf")
    n = len(items)
    cols = 4
    rows = int(math.ceil(n / float(cols)))
    bw, bh = 200, 44
    cw = bw + 20
    W = cols * cw + 20
    Hb = rows * (bh + 8) + 20
    Hp = rows * 30 + 40
    img = Image.new("RGBA", (W, Hb + 2 * Hp + 20), (40, 34, 28, 255))
    # buttons
    for k, (name, icons) in enumerate(items):
        x = 10 + (k % cols) * cw
        y = 10 + (k // cols) * (bh + 8)
        bimg = _nine(btn, (20, 16, 20, 16), (bw, bh))
        ic = _pil(gb._scaled(icons[64], icons[128], 26))
        bimg.alpha_composite(ic, (14, (bh - 26) // 2))
        dd = ImageDraw.Draw(bimg)
        dd.text((14 + 26 + 8 + 1, bh // 2 + 1), name, font=fb, fill=(0, 0, 0, 150), anchor="lm")
        dd.text((14 + 26 + 8, bh // 2), name, font=fb, fill=(240, 232, 216, 255), anchor="lm")
        img.alpha_composite(bimg, (x, y))
    for j, (panel, ink, size) in enumerate(((pan, (42, 33, 25, 255), 20),
                                            (pdk, (233, 220, 192, 255), 22))):
        y0 = Hb + j * (Hp + 10)
        pimg = _nine(panel, (24, 24, 24, 24), (W - 20, Hp))
        dd = ImageDraw.Draw(pimg)
        for k, (name, icons) in enumerate(items):
            x = 24 + (k % cols) * cw
            y = 20 + (k // cols) * 30
            ic = _pil(gb._scaled(icons[64], icons[128], size))
            pimg.alpha_composite(ic, (x, y))
            dd.text((x + size + 5, y + size // 2), "%s 1,240" % name, font=fr, fill=ink,
                    anchor="lm")
        img.alpha_composite(pimg, (10, y0))
    big = img.resize((img.width * 2, img.height * 2), Image.NEAREST)
    big.save(path)
    img.save(path.replace(".png", "_1x.png"))
    return path


def load_items(out, names=None):
    items = []
    for name in names or gb.ICONS:
        p64 = os.path.join(out, "final", "%s_64.png" % name)
        p128 = os.path.join(out, "final", "%s_128.png" % name)
        if os.path.exists(p64) and os.path.exists(p128):
            items.append((name, {64: gb.load_png(p64), 128: gb.load_png(p128)}))
    return items


if __name__ == "__main__":
    out = os.path.join(os.environ.get("IRONART_OUT", "/tmp/ironart"), "icons")
    only = None
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == "--out":
            out = argv[i + 1]; i += 1
        elif argv[i] == "--only":
            only = argv[i + 1].split(","); i += 1
        i += 1
    items = load_items(out, only)
    for k in range(0, len(items), 8):
        zoom_sheet(items[k:k + 8], os.path.join(out, "zoom_%d.png" % (k // 8)))
    context_mock(items, os.path.join(out, "context_mock.png"))
    print("[review] %d icons -> %s" % (len(items), out))
