"""Look-dev in-context check (system python3 or Blender python): 9-slice pieces stretched the
way Slate draws them (corners 1:1, edges and centre bilinear-stretched), over a crop of the
painted world map / the night colour, with real labels in the game fonts.

    python3 Tools/BlenderArt/ui_chrome/ctx.py <art_dir> <out_dir> [piece ...]

pieces: panel panel_dark button tab scroll frame divider seal logo (default: all present)
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from ironart import REPO_DIR, post  # noqa: E402

FONTS = os.path.join(REPO_DIR, "Content", "Data", "Fonts")
INK = (42, 33, 25)
INK_SOFT = (90, 74, 58)
TEXT_LIGHT = (243, 232, 207)
GOLD = (201, 162, 74)
LACQUER = (126, 31, 23)
NIGHT = (27, 23, 18)
JADE = (63, 110, 90)

DEFAULT_NINE = {"Panel": 24, "PanelDark": 24, "Button": [20, 16], "Tab": [16, 14, 16, 8],
                "Scroll": 80}


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def margins(art):
    p = os.path.join(art, "NineSlice.json")
    js = dict(DEFAULT_NINE)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            js.update({k.replace(".png", ""): v for k, v in json.load(f).items()})
    out = {}
    for k, v in js.items():
        if k.startswith("_"):
            continue
        if isinstance(v, (int, float)):
            v = [v] * 4
        elif len(v) == 2:
            v = [v[0], v[1], v[0], v[1]]
        key = k.split("_")[0] if k.startswith(("Button", "Tab")) else k
        out.setdefault(key, tuple(int(x) for x in v))
    return out


def load(art, name):
    return np.asarray(Image.open(os.path.join(art, name + ".png")).convert("RGBA"),
                      np.float32) / 255.0


def nine(img, m, size):
    out = post.nine_slice(img, m, size)
    return Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")


def map_bg(w, h, x0=700, y0=300):
    p = os.path.join(REPO_DIR, "Content", "Data", "Art", "Map", "WorldMap.png")
    if os.path.exists(p):
        im = Image.open(p).convert("RGBA")
        return im.crop((x0, y0, x0 + w, y0 + h))
    return Image.new("RGBA", (w, h), (200, 190, 150, 255))


def shadow_text(dr, xy, s, f, fill, anchor="la", sh=(0, 0, 0, 150)):
    dr.text((xy[0] + 1, xy[1] + 1), s, font=f, fill=sh, anchor=anchor)
    dr.text(xy, s, font=f, fill=fill, anchor=anchor)


def panels(art, out):
    ms = margins(art)
    W, H = 1400, 560
    bg = map_bg(W, H)
    dr = ImageDraw.Draw(bg)
    fh = font("Heading.ttf", 24)
    fb = font("Body-Bold.ttf", 16)
    fr = font("Body-Regular.ttf", 15)
    div = Image.open(os.path.join(art, "Divider.png")).convert("RGBA") \
        if os.path.exists(os.path.join(art, "Divider.png")) else None
    x = 30
    for name, (w, h), dark in (("Panel", (380, 300), False), ("PanelDark", (330, 300), True),
                               ("Panel", (180, 500), False), ("PanelDark", (400, 70), True),
                               ):
        if not os.path.exists(os.path.join(art, name + ".png")):
            continue
        y = 30
        p = nine(load(art, name), ms[name], (w, h))
        bg.alpha_composite(p, (x, y))
        if h > 100:
            dr.text((x + 20, y + 18), "Luoyang 洛阳", font=fh, fill=GOLD if dark else LACQUER)
            if div is not None:
                dv = div.resize((w - 40, 12), Image.BILINEAR)
                bg.alpha_composite(dv, (x + 20, y + 52))
            lines = [("Governor  Cao Ren", True), ("Gold 1,240    Food 8,600", False),
                     ("Troops 12,000    Training 64", False), ("Order 78    Defense 64", False),
                     ("Population 182,000", False)]
            for k, (ln, bold) in enumerate(lines):
                yy = y + 74 + k * 24
                if yy < y + h - 30:
                    dr.text((x + 20, yy), ln, font=fb if bold else fr,
                            fill=TEXT_LIGHT if dark else INK)
        else:
            dr.text((x + 18, y + h // 2), "Spring, Year 184  ·  Planning", font=fh,
                    fill=GOLD, anchor="lm")
        x += w + 24
        if x > W - 150:
            break
    bg.save(os.path.join(out, "ctx_panels.png"))
    return bg


def buttons(art, out):
    ms = margins(art)
    names = [n for n in ("Button", "Button_Hover", "Button_Pressed", "Button_Disabled")
             if os.path.exists(os.path.join(art, n + ".png"))]
    if not names:
        return None
    sizes = [(260, 44), (150, 40), (420, 48)]
    labels = ["New Game", "Wait", "Attack the city"]
    W = sum(s[0] for s in sizes) + 40 * 4
    H = 60 * len(names) * 2 + 40
    bg = map_bg(W, H, 300, 900)
    dr = ImageDraw.Draw(bg)
    # lower half: on a light panel
    pn = os.path.join(art, "Panel.png")
    if os.path.exists(pn):
        bg.alpha_composite(nine(load(art, "Panel"), ms["Panel"], (W - 20, H // 2 - 10)),
                           (10, H // 2))
    fb = font("Body-Bold.ttf", 16)
    y = 22
    for half in range(2):
        for nm in names:
            im = load(art, nm)
            x = 40
            for (w, h), lab in zip(sizes, labels):
                bg.alpha_composite(nine(im, ms["Button"], (w, h)), (x, y))
                off = 1 if nm == "Button_Pressed" else 0
                col = TEXT_LIGHT if nm != "Button_Disabled" else (180, 172, 160)
                shadow_text(dr, (x + w // 2, y + h // 2 + off), lab, fb, col, anchor="mm")
                x += w + 40
            y += 60
        y += 20
    bg.save(os.path.join(out, "ctx_buttons.png"))
    return bg


def tabs(art, out):
    ms = margins(art)
    if not os.path.exists(os.path.join(art, "Tab.png")):
        return None
    labels = ["Domestic", "Military", "Personnel", "Diplomacy", "Town"]
    W, H = 760, 330
    bg = map_bg(W, H, 1200, 700)
    dr = ImageDraw.Draw(bg)
    pnl = load(art, "Panel") if os.path.exists(os.path.join(art, "Panel.png")) else None
    f = font("Body-Bold.ttf", 15)
    y = 30
    for (w, h), active in (((118, 36), 1), ((96, 32), 0), ((140, 44), 3)):
        if pnl is not None:
            bg.alpha_composite(nine(pnl, ms["Panel"], (5 * (w + 4) + 30, h + 50)), (20, y - 14))
        x = 35
        for k, lab in enumerate(labels):
            src = load(art, "Tab_Active" if k == active else "Tab")
            p = nine(src, ms["Tab"], (w, h))
            if k != active:
                a = np.asarray(p, np.float32)
                a[..., :3] *= 0.78
                p = Image.fromarray(a.astype(np.uint8), "RGBA")
            bg.alpha_composite(p, (x, y))
            dr.text((x + w // 2, y + h // 2 + 1), lab, font=f,
                    fill=LACQUER if k == active else INK, anchor="mm")
            x += w + 4
        y += h + 70
    bg.save(os.path.join(out, "ctx_tabs.png"))
    return bg


def scroll(art, out):
    ms = margins(art)
    if not os.path.exists(os.path.join(art, "Scroll.png")):
        return None
    im = load(art, "Scroll")
    res = []
    for (w, h) in ((1040, 640), (1040, 480), (1060, 760)):
        bg = map_bg(w + 80, h + 80, 400, 200)
        bg.alpha_composite(nine(im, ms["Scroll"], (w, h)), (40, 40))
        dr = ImageDraw.Draw(bg)
        dr.text((40 + w // 2, 40 + 82), "A Wanderer at the Gate", font=font("Heading.ttf", 30),
                fill=LACQUER, anchor="mm")
        fr = font("Body-Regular.ttf", 17)
        txt = ("A ragged swordsman asks for an audience. He claims to have served the Azure "
               "Court and offers his blade to our cause, for a price in gold.")
        dr.multiline_text((40 + 110, 40 + 130), _wrap(txt, fr, w - 220), font=fr, fill=INK,
                          spacing=6)
        res.append(bg)
        bg.save(os.path.join(out, "ctx_scroll_%dx%d.png" % (w, h)))
    return res


def _wrap(txt, f, width):
    words, lines, cur = txt.split(), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if f.getlength(t) > width:
            lines.append(cur)
            cur = w_
        else:
            cur = t
    lines.append(cur)
    return "\n".join(lines)


def main():
    art, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    which = sys.argv[3:] or ["panel", "button", "tab", "scroll"]
    for w in which:
        {"panel": panels, "button": buttons, "tab": tabs, "scroll": scroll}[w](art, out)
    print("ctx ->", out)


if __name__ == "__main__":
    main()
