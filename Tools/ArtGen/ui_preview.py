#!/usr/bin/env python3
"""Compose 1920x1080 mock screenshots from the generated UI art, to review it in context.

    python3 Tools/ArtGen/ui_preview.py [out_dir]     (default: ./ui_preview_out)

Writes mock_ui.png (panels as 9-slices at several sizes, buttons in every state with text,
tab row, icons at 32/64 px, portrait frame, divider, seal, scroll dialog) and mock_title.png
(title screen). Nothing is written into Content/. Missing art is skipped.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from artlib_ui import ART, FONT_BODY, FONT_BOLD, FONT_BRUSH, FONT_HEADING

UI = os.path.join(ART, "UI")

ICONS = ["Farm", "Commerce", "Walls", "Patrol", "Draft", "Train", "Search", "Recruit", "Move",
         "Transport", "SectTraining", "Alliance", "Truce", "Gift", "March", "Market", "Tavern",
         "Officers", "Factions", "Save", "Load", "EndTurn", "Gold", "Food", "Troops", "Population",
         "Order", "Defense", "Training", "Loyalty", "Settings", "Delegate", "Prisoner", "Fire",
         "Confuse", "Rally", "Duel", "Attack", "Wait", "Undo"]

# 9-slice margins (left, top, right, bottom) in texture pixels
MARGINS = {
    "Panel.png": (24, 24, 24, 24),
    "PanelDark.png": (24, 24, 24, 24),
    "Button.png": (20, 16, 20, 16),
    "Button_Hover.png": (20, 16, 20, 16),
    "Button_Pressed.png": (20, 16, 20, 16),
    "Button_Disabled.png": (20, 16, 20, 16),
    "Tab.png": (16, 14, 16, 8),
    "Tab_Active.png": (16, 14, 16, 8),
    "Scroll.png": (80, 80, 80, 80),
}

TEXT_LIGHT = (243, 231, 204)
TEXT_DIM = (191, 167, 122)
INK = (42, 33, 25)
INK_SOFT = (90, 74, 58)
LACQUER = (126, 31, 23)
GOLD = (201, 162, 74)


def load(name, sub=UI):
    p = os.path.join(sub, name)
    if not os.path.exists(p):
        return None
    return Image.open(p).convert("RGBA")


def nine(name, w, h, scale=1.0):
    """Slate-style box brush: corners fixed, edges and centre stretched."""
    img = load(name)
    if img is None:
        return Image.new("RGBA", (w, h), (120, 60, 60, 255))
    l, t, r, b = [int(round(m * scale)) for m in MARGINS[name]]
    if scale != 1.0:
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    W, H = img.size
    sx = [0, l, W - r, W]
    sy = [0, t, H - b, H]
    dx = [0, l, w - r, w]
    dy = [0, t, h - b, h]
    out = Image.new("RGBA", (w, h))
    for i in range(3):
        for j in range(3):
            box = (sx[i], sy[j], sx[i + 1], sy[j + 1])
            dw, dh = dx[i + 1] - dx[i], dy[j + 1] - dy[j]
            if dw <= 0 or dh <= 0 or box[2] <= box[0] or box[3] <= box[1]:
                continue
            piece = img.crop(box).resize((dw, dh), Image.BILINEAR)
            out.paste(piece, (dx[i], dy[j]))
    return out


def text(d, xy, s, path, size, fill, anchor="mm", shadow=None):
    f = ImageFont.truetype(path, size)
    if shadow:
        d.text((xy[0] + 1, xy[1] + 1), s, font=f, fill=shadow, anchor=anchor)
    d.text(xy, s, font=f, fill=fill, anchor=anchor)


def button(canvas, x, y, w, h, label, state="", size=18):
    name = "Button%s.png" % (("_" + state) if state else "")
    b = nine(name, w, h)
    canvas.alpha_composite(b, (x, y))
    d = ImageDraw.Draw(canvas)
    col = TEXT_LIGHT if state != "Disabled" else (168, 158, 140)
    if state == "Hover":
        col = (255, 244, 214)
    oy = 1 if state == "Pressed" else 0
    text(d, (x + w // 2, y + h // 2 + oy), label, FONT_BOLD, size, col, shadow=(30, 8, 5))


def icon(canvas, name, x, y, size):
    im = load("Icon_%s.png" % name)
    if im is None:
        return
    if size != im.width:
        im = im.resize((size, size), Image.LANCZOS)
    canvas.alpha_composite(im, (x, y))


def mock_ui(out):
    W, H = 1920, 1080
    bg = load("Title_Background.png")
    canvas = Image.new("RGBA", (W, H), (60, 58, 50, 255))
    if bg is not None:
        canvas.alpha_composite(bg.filter(ImageFilter.GaussianBlur(2)))
        canvas.alpha_composite(Image.new("RGBA", (W, H), (20, 16, 12, 110)))
    d = ImageDraw.Draw(canvas)

    # top bar (dark panel stretched wide)
    canvas.alpha_composite(nine("PanelDark.png", W - 24, 64), (12, 8))
    text(d, (44, 40), "Spring, Year 184  -  Month 3", FONT_HEADING, 24, GOLD, anchor="lm")
    text(d, (410, 40), "Planning", FONT_BOLD, 18, TEXT_LIGHT, anchor="lm")
    x = 560
    for nm, val in (("Gold", "12,480"), ("Food", "48,200"), ("Troops", "31,050")):
        icon(canvas, nm, x, 24, 32)
        text(d, (x + 38, 40), val, FONT_BOLD, 17, TEXT_LIGHT, anchor="lm")
        x += 150
    bx = 1010
    for lab, st in (("Officers", ""), ("Factions", ""), ("Save", ""), ("Load", "Disabled"), ("End Turn", "Hover")):
        bw = 168 if lab == "End Turn" else 150
        button(canvas, bx, 14, bw, 52, lab, st, size=17)
        bx += bw + 10

    # left: city panel (parchment, tall)
    px, py, pw, ph = 12, 84, 420, 700
    canvas.alpha_composite(nine("Panel.png", pw, ph), (px, py))
    text(d, (px + 34, py + 44), "Luoyang", FONT_HEADING, 28, LACQUER, anchor="lm")
    text(d, (px + 200, py + 46), "洛阳", FONT_BRUSH, 30, INK, anchor="lm")
    seal = load("Seal.png")
    if seal is not None:
        canvas.alpha_composite(seal.resize((44, 44), Image.LANCZOS), (px + pw - 80, py + 22))
    div = load("Divider.png")
    if div is not None:
        canvas.alpha_composite(div.resize((pw - 60, 16), Image.LANCZOS), (px + 30, py + 76))
    rows = [("Population", "Population", "182,000"), ("Farm", "Farm", "640 / 999"),
            ("Commerce", "Commerce", "512 / 999"), ("Defense", "Defense", "430 / 999"),
            ("Order", "Public Order", "78"), ("Troops", "Troops", "8,400"),
            ("Training", "Training", "62"), ("Loyalty", "Loyalty", "88")]
    yy = py + 112
    for ic, lab, val in rows:
        icon(canvas, ic, px + 34, yy - 16, 32)
        text(d, (px + 76, yy), lab, FONT_BODY, 16, INK, anchor="lm")
        text(d, (px + pw - 40, yy), val, FONT_BOLD, 16, INK, anchor="rm")
        yy += 38
    # officer list with portrait frames
    fr = load("Frame_Portrait.png")
    text(d, (px + 34, yy + 14), "Officers in city", FONT_HEADING, 20, LACQUER, anchor="lm")
    if fr is not None:
        for k in range(3):
            fx = px + 34 + k * 122
            fy = yy + 36
            ph_im = Image.new("RGBA", (192, 240), (70, 62, 52, 255))
            pd = ImageDraw.Draw(ph_im)
            pd.ellipse([56, 40, 136, 140], fill=(150, 120, 95, 255))
            pd.rectangle([30, 150, 162, 240], fill=(90, 40, 30, 255))
            tile = Image.new("RGBA", (212, 260))
            tile.alpha_composite(ph_im, (10, 10))
            tile.alpha_composite(fr)
            tile = tile.resize((106, 130), Image.LANCZOS)
            canvas.alpha_composite(tile, (fx, fy))

    # right: command panel with tabs
    rx, ry, rw, rh = 1440, 132, 468, 560
    tabs = ["Domestic", "Military", "Personnel", "Diplomacy", "Town"]
    tw = rw // len(tabs) - 2
    for i, t in enumerate(tabs):
        act = i == 1
        tb = nine("Tab_Active.png" if act else "Tab.png", tw, 40 if act else 36)
        canvas.alpha_composite(tb, (rx + 2 + i * (tw + 2), ry - (40 if act else 36) + 6))
        text(d, (rx + 2 + i * (tw + 2) + tw // 2, ry - (14 if act else 12) - 1), t, FONT_BOLD, 14,
             TEXT_LIGHT if act else TEXT_DIM)
    canvas.alpha_composite(nine("PanelDark.png", rw, rh), (rx, ry))
    cmds = [("Draft", "Draft"), ("Train", "Train"), ("March", "March"), ("Transport", "Transport")]
    by = ry + 36
    for ic, lab in cmds:
        button(canvas, rx + 30, by, rw - 60, 56, "", "")
        icon(canvas, ic, rx + 46, by + 4, 48)
        text(d, (rx + 110, by + 28), lab, FONT_BOLD, 18, TEXT_LIGHT, anchor="lm", shadow=(30, 8, 5))
        by += 68
    # all button states
    by += 10
    text(d, (rx + 30, by + 10), "Button states", FONT_HEADING, 18, GOLD, anchor="lm")
    by += 30
    for i, (st, lab) in enumerate((("", "Normal"), ("Hover", "Hover"), ("Pressed", "Pressed"), ("Disabled", "Disabled"))):
        button(canvas, rx + 30 + (i % 2) * 208, by + (i // 2) * 56, 196, 46, lab, st, size=17)
    by += 120
    button(canvas, rx + 30, by, rw - 60, 64, "Large: 192x64 native", "", size=20)

    # middle area: scroll event dialog
    sx, sy, sw, sh = 470, 120, 940, 600
    canvas.alpha_composite(nine("Scroll.png", sw, sh), (sx, sy))
    ev = load("Harvest.png", os.path.join(ART, "Events"))
    text(d, (sx + sw // 2, sy + 112), "A Bountiful Harvest", FONT_HEADING, 28, LACQUER)
    if ev is not None:
        evs = ev.resize((448, 252), Image.LANCZOS)
        canvas.alpha_composite(evs, (sx + 96, sy + 140))
        d.rectangle([sx + 95, sy + 139, sx + 96 + 448, sy + 140 + 252], outline=INK, width=2)
    if fr is not None:
        tile = Image.new("RGBA", (212, 260), (70, 62, 52, 0))
        ph_im = Image.new("RGBA", (192, 240), (60, 54, 46, 255))
        tile.alpha_composite(ph_im, (10, 10))
        tile.alpha_composite(fr)
        tile = tile.resize((159, 195), Image.LANCZOS)
        canvas.alpha_composite(tile, (sx + 576, sy + 150))
    lines = ["The fields of the river plain ripen early.",
             "Granaries overflow; the people sing of you."]
    for k, ln in enumerate(lines):
        text(d, (sx + 96, sy + 420 + k * 26), ln, FONT_BODY, 18, INK, anchor="lm")
    button(canvas, sx + 96, sy + 486, 230, 48, "Distribute grain", "")
    button(canvas, sx + 340, sy + 486, 230, 48, "Fill the granary", "Hover")

    # bottom: log panel (wide, short)
    canvas.alpha_composite(nine("Panel.png", 1396, 150), (12, 918))
    text(d, (44, 952), "Month 3: Liu Bei's envoy arrives bearing gifts.", FONT_BODY, 16, INK, anchor="lm")
    text(d, (44, 978), "Month 3: The Wolf Riders march on Chang'an (12,000 troops).", FONT_BODY, 16, INK_SOFT, anchor="lm")
    text(d, (44, 1004), "Month 2: Harvest in Luoyang yields 8,200 food.", FONT_BODY, 16, INK_SOFT, anchor="lm")
    # icon sheet: 64 px and 32 px, on dark panel and on parchment
    canvas.alpha_composite(nine("PanelDark.png", 492, 370), (1420, 700))
    canvas.alpha_composite(nine("Panel.png", 300, 64), (1104, 1004 - 140))
    n = len(ICONS)
    for i, nm in enumerate(ICONS):
        icon(canvas, nm, 1442 + (i % 7) * 64, 720 + (i // 7) * 56, 48 if False else 48)
    for i, nm in enumerate(ICONS[:14]):
        pass
    # 64 px row on parchment and 32px row on parchment
    canvas.alpha_composite(nine("Panel.png", 690, 82), (470, 730 + 0 * 0 + 6 - 6 + 0))
    for i, nm in enumerate(ICONS[:10]):
        icon(canvas, nm, 494 + i * 66, 739, 64)
    for i, nm in enumerate(ICONS):
        icon(canvas, nm, 1440 + (i % 13) * 36, 1000 + (i // 13) * 0, 32) if i < 13 else None
    canvas.alpha_composite(nine("Panel.png", 1396 - 0, 0 + 60), (12, 852)) if False else None
    for i, nm in enumerate(ICONS):
        icon(canvas, nm, 1128 + (i % 7) * 38, 886 + (i // 7) * 0, 32) if i < 7 else None
    canvas.convert("RGB").save(os.path.join(out, "mock_ui.png"))


def mock_icons(out):
    """Icon review sheet: every icon at 64 and 32 px on parchment and on the dark panel."""
    W, H = 1920, 1080
    canvas = Image.new("RGBA", (W, H), (40, 36, 30, 255))
    d = ImageDraw.Draw(canvas)
    canvas.alpha_composite(nine("Panel.png", 940, 1040), (16, 20))
    canvas.alpha_composite(nine("PanelDark.png", 940, 1040), (964, 20))
    for side, ox, col in ((0, 16, INK), (1, 964, TEXT_LIGHT)):
        for i, nm in enumerate(ICONS):
            cx = ox + 40 + (i % 5) * 178
            cy = 50 + (i // 5) * 124
            icon(canvas, nm, cx, cy, 64)
            icon(canvas, nm, cx + 76, cy + 16, 32)
            text(d, (cx + 2, cy + 82), nm, FONT_BODY, 15, col, anchor="lm")
    canvas.convert("RGB").save(os.path.join(out, "mock_icons.png"))


def mock_title(out):
    W, H = 1920, 1080
    canvas = Image.new("RGBA", (W, H), (30, 26, 20, 255))
    bg = load("Title_Background.png")
    if bg is not None:
        canvas.alpha_composite(bg)
    logo = load("Title_Logo.png")
    if logo is not None:
        lw = 900
        canvas.alpha_composite(logo.resize((lw, lw * logo.height // logo.width), Image.LANCZOS), (70, 70))
    by = 520
    for lab, st in (("New Game", "Hover"), ("Load Game", ""), ("Quit", "")):
        button(canvas, 210, by, 320, 60, lab, st, size=22)
        by += 78
    canvas.convert("RGB").save(os.path.join(out, "mock_title.png"))


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.getcwd(), "ui_preview_out")
    os.makedirs(out, exist_ok=True)
    mock_ui(out)
    mock_icons(out)
    mock_title(out)
    print("wrote previews to %s" % out)


if __name__ == "__main__":
    main()
