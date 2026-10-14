"""9-slice verification composites + in-context mock screen for the UI chrome family (numpy +
Pillow only; runs in Blender's python or the system python3).

    python3 Tools/BlenderArt/ui_chrome/preview.py [out_dir]

reads the committed @1x art from Content/Data/Art/UI (and @2x from ArtSource/UI) and writes:
    nineslice_<piece>.png   each 9-slice drawn at three sizes with real labels (Body-Bold.ttf)
    states_buttons.png      the four button states + tabs, at 1x and 2x zoom
    context_mock.png        a strategy-screen mock-up: panels, buttons, tabs, divider, portrait
                            frame, seal, scroll dialog and logo together
    sheet_ui_chrome.png     contact sheet of every asset on checker + dark backgrounds
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

from ironart import REPO_DIR, post  # noqa: E402

ART = os.path.join(REPO_DIR, "Content", "Data", "Art", "UI")
SRC = os.path.join(REPO_DIR, "ArtSource", "UI")
FONTS = os.path.join(REPO_DIR, "Content", "Data", "Fonts")
INK = (42, 33, 25)
TEXT_LIGHT = (243, 232, 207)
GOLD = (201, 162, 74)
LACQUER = (126, 31, 23)
NIGHT = (27, 23, 18)
PAPER = (233, 220, 192)


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def load(name, two=False):
    p = os.path.join(SRC, name + "@2x.png") if two else os.path.join(ART, name + ".png")
    return Image.open(p).convert("RGBA")


def margins():
    with open(os.path.join(ART, "NineSlice.json"), encoding="utf-8") as f:
        js = json.load(f)
    out = {}
    for k, v in js.items():
        if k.startswith("_"):
            continue
        k = k.replace(".png", "")
        if isinstance(v, (int, float)):
            v = [v] * 4
        elif len(v) == 2:
            v = [v[0], v[1], v[0], v[1]]
        out[k] = tuple(int(x) for x in v)
    return out


def nine(im, m, size):
    """Slate-like 9-slice: corners 1:1, edges stretched along, centre stretched both ways."""
    arr = np.asarray(im, np.float32) / 255.0
    out = post.nine_slice(arr, m, size)
    return Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")


def text_shadow(dr, xy, s, f, fill, shadow=(0, 0, 0, 150), anchor="mm"):
    dr.text((xy[0] + 1, xy[1] + 1), s, font=f, fill=shadow, anchor=anchor)
    dr.text(xy, s, font=f, fill=fill, anchor=anchor)


def backdrop(w, h, kind="map"):
    """A neutral painterly-ish backdrop to judge alpha edges (map greens / dark table)."""
    rng = np.random.default_rng(3)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    if kind == "map":
        base = np.array([120, 136, 92], np.float32)
        n = (np.sin(x / 37.0) + np.sin(y / 23.0 + x / 61.0)) * 6
    else:
        base = np.array([38, 32, 27], np.float32)
        n = (np.sin(x / 47.0) + np.sin(y / 29.0)) * 3
    img = base[None, None, :] + n[..., None] + rng.normal(0, 2, (h, w, 1))
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


def nineslice_sheet(out):
    ms = margins()
    fb = font("Body-Bold.ttf", 16)
    fr = font("Body-Regular.ttf", 15)
    fh = font("Heading.ttf", 24)
    sheets = {}
    # panels
    for name, txt, tcol in (("Panel", INK, LACQUER), ("PanelDark", TEXT_LIGHT, GOLD)):
        im = load(name)
        sizes = [(360, 220), (180, 420), (640, 300)]
        W = sum(s[0] for s in sizes) + 40 * 4
        H = max(s[1] for s in sizes) + 80
        bg = backdrop(W, H, "map")
        x = 40
        for (w, h) in sizes:
            p = nine(im, ms[name], (w, h))
            bg.alpha_composite(p, (x, 40))
            dr = ImageDraw.Draw(bg)
            dr.text((x + 28, 40 + 26), "City of Luoyang", font=fh, fill=tcol)
            lines = ["Governor: Cao Ren", "Gold 1,240   Food 8,600", "Troops 12,000",
                     "Order 78   Defense 64"]
            for k, ln in enumerate(lines):
                if 40 + 66 + k * 22 < 40 + h - 28:
                    dr.text((x + 28, 40 + 66 + k * 22), ln, font=fb if k == 0 else fr, fill=txt)
            x += w + 40
        bg.save(os.path.join(out, "nineslice_%s.png" % name))
        sheets[name] = bg
    # buttons (all states) at three sizes
    names = ["Button", "Button_Hover", "Button_Pressed", "Button_Disabled"]
    sizes = [(260, 44), (140, 40), (320, 56)]
    W = sum(s[0] for s in sizes) + 40 * 4
    H = (max(s[1] for s in sizes) + 30) * len(names) + 40
    bg = backdrop(W, H, "dark")
    dr = ImageDraw.Draw(bg)
    y = 30
    for nm in names:
        im = load(nm)
        x = 40
        for (w, h), label in zip(sizes, ("New Game", "Wait", "End Turn")):
            p = nine(im, ms["Button"], (w, h))
            bg.alpha_composite(p, (x, y))
            off = 1 if nm == "Button_Pressed" else 0
            col = (170, 160, 150) if nm == "Button_Disabled" else TEXT_LIGHT
            text_shadow(dr, (x + w // 2 + off, y + h // 2 + off), label, fb, col)
            x += w + 40
        y += max(s[1] for s in sizes) + 30
    bg.save(os.path.join(out, "nineslice_Button.png"))
    sheets["Button"] = bg
    # tabs: a bar of five on a dark panel, one active, at the UI size and at 2 others
    labels = ["Domestic", "Military", "Personnel", "Diplomacy", "Town"]
    rows = [((82, 34), 1), ((120, 40), 0), ((60, 30), 3)]
    W = 5 * 122 + 80
    H = sum(r[0][1] for r in rows) + 40 * (len(rows) + 1) + 30
    bg = backdrop(W, H, "dark")
    dr = ImageDraw.Draw(bg)
    tab, tab_a = load("Tab"), load("Tab_Active")
    f13 = font("Body-Regular.ttf", 13)
    f13b = font("Body-Bold.ttf", 13)
    y = 40
    for (w, h), active in rows:
        x = 40
        for k, lab in enumerate(labels):
            src = tab_a if k == active else tab
            p = nine(src, ms["Tab"], (w, h))
            if k != active:
                a = np.asarray(p, np.float32)
                a[..., :3] *= 0.78
                p = Image.fromarray(a.astype(np.uint8), "RGBA")
            bg.alpha_composite(p, (x, y))
            dr.text((x + w // 2, y + h // 2), lab, font=f13b if k == active else f13,
                    fill=GOLD if k == active else TEXT_LIGHT, anchor="mm")
            x += w + 2
        # the panel the tabs sit on
        pd = nine(load("PanelDark"), ms["PanelDark"], (5 * (w + 2), 22))
        bg.alpha_composite(pd.crop((0, 11, pd.width, 22)), (40, y + h))
        y += h + 40
    bg.save(os.path.join(out, "nineslice_Tab.png"))
    sheets["Tab"] = bg
    # scroll at three sizes (dialog widths ~1040)
    im = load("Scroll")
    for k, size in enumerate([(1040, 720), (900, 560), (1200, 860)]):
        bg = backdrop(size[0] + 80, size[1] + 80, "map")
        p = nine(im, ms["Scroll"], size)
        bg.alpha_composite(p, (40, 40))
        dr = ImageDraw.Draw(bg)
        dr.text((40 + size[0] // 2, 40 + 78), "A Wandering Swordsman", font=font("Heading.ttf", 30),
                fill=LACQUER, anchor="mm")
        dv = load("Divider").resize((size[0] - 260, 12), Image.BICUBIC)
        bg.alpha_composite(dv, (40 + 130, 40 + 100))
        body = ("A ragged traveller asks for an audience. He claims to have studied the sword "
                "under the hermits of Mount Hua and offers his service for a modest stipend.")
        fbody = font("Body-Regular.ttf", 17)
        words, line, yy = body.split(), "", 40 + 130
        for wd in words:
            t = (line + " " + wd).strip()
            if dr.textlength(t, font=fbody) > size[0] - 220:
                dr.text((40 + 110, yy), line, font=fbody, fill=INK)
                yy += 24
                line = wd
            else:
                line = t
        dr.text((40 + 110, yy), line, font=fbody, fill=INK)
        sl = load("Seal").resize((84, 84), Image.LANCZOS)
        bg.alpha_composite(sl, (40 + size[0] - 220, 40 + size[1] - 190))
        bg.save(os.path.join(out, "nineslice_Scroll_%d.png" % k))
    return sheets


def divider_sheet(out):
    dv = load("Divider")
    W, H = 1000, 220
    bg = Image.new("RGBA", (W, H), PAPER + (255,))
    dark = Image.new("RGBA", (W, H // 2), NIGHT + (255,))
    bg.alpha_composite(dark, (0, H // 2))
    y = 18
    for (w, h) in ((300, 8), (512, 12), (900, 16)):
        bg.alpha_composite(dv.resize((w, h), Image.BICUBIC), ((W - w) // 2, y))
        bg.alpha_composite(dv.resize((w, h), Image.BICUBIC), ((W - w) // 2, H // 2 + y))
        y += 30
    bg.save(os.path.join(out, "divider_sizes.png"))


def frame_sheet(out, portrait=None):
    fr = load("Frame_Portrait")
    portrait = portrait or os.path.join(os.environ.get("IRONART_OUT", "/tmp/ironart"), "styleframes",
                                        "sf_portrait_192x240.png")
    bg = backdrop(212 * 3 + 80, 300, "dark")
    for k, h in enumerate((260, 130, 200)):
        s = h / 260.0
        x = 30 + sum(int(212 * hh / 260.0) + 20 for hh in (260, 130, 200)[:k])
        if os.path.exists(portrait):
            p = Image.open(portrait).convert("RGBA").resize((int(192 * s), int(240 * s)), Image.LANCZOS)
            bg.alpha_composite(p, (x + int(10 * s), 20 + int(10 * s)))
        bg.alpha_composite(fr.resize((int(212 * s), int(260 * s)), Image.LANCZOS), (x, 20))
    bg.save(os.path.join(out, "frame_portrait_sizes.png"))


def logo_sheet(out):
    lg = load("Title_Logo")
    W, H = 1200, 400
    rows = []
    for kind in ("mist", "dark", "title"):
        if kind == "title":
            tb = os.path.join(ART, "Title_Background.png")
            if not os.path.exists(tb):
                continue
            bg = Image.open(tb).convert("RGBA").crop((360, 120, 1560, 520))
        elif kind == "mist":
            y, x = np.mgrid[0:H, 0:W].astype(np.float32)
            g = 150 + 60 * (y / H) + 10 * np.sin(x / 90.0)
            img = np.dstack([g * 0.92, g * 0.95, g * 0.98])
            bg = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
        else:
            bg = backdrop(W, H, "dark")
        bg.alpha_composite(lg)
        rows.append(bg)
    sheet = Image.new("RGBA", (W, H * len(rows) + 10 * (len(rows) - 1)), (0, 0, 0, 255))
    for k, r in enumerate(rows):
        sheet.alpha_composite(r, (0, k * (H + 10)))
    sheet.save(os.path.join(out, "logo_backgrounds.png"))


def contact(out):
    names = ["Panel", "PanelDark", "Button", "Button_Hover", "Button_Pressed", "Button_Disabled",
             "Tab", "Tab_Active", "Frame_Portrait", "Divider", "Seal", "Scroll", "Title_Logo"]
    items = []
    for n in names:
        p = os.path.join(ART, n + ".png")
        if os.path.exists(p):
            im = post.load(p)
            if im.shape[1] > 520:
                im = post.resize(im, (520, int(im.shape[0] * 520 / im.shape[1])))
            items.append((im, n))
    sheet = post.contact_sheet(items, cols=4, scale=1)
    post.save(sheet, os.path.join(out, "sheet_ui_chrome.png"))


def main(out=None):
    out = out or os.path.join(os.environ.get("IRONART_OUT", "/tmp/ironart"), "ui_chrome")
    os.makedirs(out, exist_ok=True)
    nineslice_sheet(out)
    divider_sheet(out)
    frame_sheet(out)
    logo_sheet(out)
    contact(out)
    try:
        import mock
        mock.main(out)
    except ImportError:
        pass
    print("[ui_chrome] previews ->", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
