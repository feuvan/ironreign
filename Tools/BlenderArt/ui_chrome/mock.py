"""In-context check: a 1920x1080 strategy-screen mock-up assembled from the committed UI chrome
(panels, tabs, buttons, dividers, portrait frame, seal, event scroll, logo thumbnail) the way the
Slate code draws them (9-slices at 1:1 corners, divider stretched, frame scaled)."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

import preview as P  # noqa: E402


def map_backdrop(W, H):
    wm = os.path.join(os.path.dirname(P.ART), "Map", "WorldMap.png")
    if not os.path.exists(wm):
        from ironart import REPO_DIR
        wm = os.path.join(REPO_DIR, "Content", "Data", "Art", "Map", "WorldMap.png")
    if os.path.exists(wm):
        im = Image.open(wm).convert("RGBA")
        return im.crop((200, 150, 200 + W, 150 + H)) if im.width >= W + 200 else im.resize((W, H))
    sf = os.path.join(os.environ.get("IRONART_OUT", "/tmp/ironart"), "styleframes",
                      "sf_terrain_512x320.png")
    if os.path.exists(sf):
        im = Image.open(sf).convert("RGBA").resize((W, int(W * 320 / 512)), Image.BICUBIC)
        return im.crop((0, 0, W, H))
    return P.backdrop(W, H, "map")


def _portrait():
    """A portrait to put in the frame: the committed art, else $IRONART_UI_PORTRAIT."""
    from ironart import REPO_DIR
    for p in (os.path.join(REPO_DIR, "Content", "Data", "Art", "Portraits", "m_warrior_01.png"),
              os.environ.get("IRONART_UI_PORTRAIT", ""),
              os.path.join(os.environ.get("IRONART_OUT", "/tmp/ironart"), "styleframes",
                           "sf_portrait_192x240.png")):
        if p and os.path.exists(p):
            return p
    return None


def _event():
    from ironart import REPO_DIR
    for n in ("Wanderer", "Court", "Festival", "Battle"):
        p = os.path.join(REPO_DIR, "Content", "Data", "Art", "Events", n + ".png")
        if os.path.exists(p):
            return p
    return None


def main(out):
    W, H = 1920, 1080
    ms = P.margins()
    bg = map_backdrop(W, H)
    dr = ImageDraw.Draw(bg)
    fb16 = P.font("Body-Bold.ttf", 16)
    fr15 = P.font("Body-Regular.ttf", 15)
    fh26 = P.font("Heading.ttf", 26)
    fh20 = P.font("Heading.ttf", 20)
    f13 = P.font("Body-Regular.ttf", 13)
    f13b = P.font("Body-Bold.ttf", 13)
    fbr = P.font("Brush.ttf", 30)

    # ---- top bar -------------------------------------------------------------------------------
    top = P.nine(P.load("PanelDark"), ms["PanelDark"], (W, 72))
    bg.alpha_composite(top, (0, 0))
    dr.text((34, 36), "Spring, Year 184", font=fh20, fill=P.GOLD, anchor="lm")
    dr.text((250, 36), "Planning", font=fr15, fill=P.TEXT_LIGHT, anchor="lm")
    dr.text((420, 36), "Gold 12,480    Food 96,200    Troops 84,000", font=fb16, fill=P.TEXT_LIGHT,
            anchor="lm")
    x = W - 34
    for lab, w in (("End Turn", 150), ("Load", 110), ("Save", 110), ("Factions", 130),
                   ("Officers", 130)):
        x -= w
        st = "Button_Hover" if lab == "Factions" else "Button"
        b = P.nine(P.load(st), ms["Button"], (w, 44))
        bg.alpha_composite(b, (x, 14))
        P.text_shadow(dr, (x + w // 2, 36), lab, fb16, P.TEXT_LIGHT)
        x -= 10

    # ---- left: city panel (paper) ---------------------------------------------------------------
    lx, ly, lw, lh = 24, 92, 400, 700
    bg.alpha_composite(P.nine(P.load("Panel"), ms["Panel"], (lw, lh)), (lx, ly))
    dr.text((lx + 30, ly + 30), "Luoyang", font=fh26, fill=P.LACQUER)
    dr.text((lx + 160, ly + 26), "洛阳", font=fbr, fill=P.INK)
    dv = P.load("Divider").resize((lw - 60, 12), Image.BICUBIC)
    bg.alpha_composite(dv, (lx + 30, ly + 70))
    # portrait frame + portrait (scaled to 156 px high, as the city panel does)
    sf = _portrait()
    s = 156 / 260.0
    fx, fy = lx + 30, ly + 96
    if sf and os.path.exists(sf):
        bg.alpha_composite(Image.open(sf).convert("RGBA").resize((int(192 * s), int(240 * s)),
                                                                  Image.LANCZOS),
                           (fx + int(10 * s), fy + int(10 * s)))
    bg.alpha_composite(P.load("Frame_Portrait").resize((int(212 * s), 156), Image.LANCZOS), (fx, fy))
    tx = fx + int(212 * s) + 16
    for k, (a, b) in enumerate((("Governor", "Cao Ren"), ("Owner", "Iron Banner"),
                                ("Population", "182,000"), ("Order", "78"))):
        dr.text((tx, fy + 6 + k * 26), a, font=fr15, fill=P.INK)
        dr.text((tx + 100, fy + 6 + k * 26), b, font=fb16, fill=P.INK)
    seal = P.load("Seal").resize((64, 64), Image.LANCZOS)
    bg.alpha_composite(seal, (lx + lw - 96, ly + 26))
    yy = fy + 176
    for lab in ("Farm  420 / 999", "Commerce  310 / 999", "Walls  640 / 999", "Defense  512"):
        dr.text((lx + 30, yy), lab, font=fr15, fill=P.INK)
        yy += 28
    bg.alpha_composite(P.load("Divider").resize((lw - 60, 10), Image.BICUBIC), (lx + 30, yy + 4))
    yy += 28
    for k, lab in enumerate(("Develop", "Recruit", "March")):
        b = P.nine(P.load("Button" if k else "Button_Pressed"), ms["Button"], (lw - 60, 42))
        bg.alpha_composite(b, (lx + 30, yy))
        P.text_shadow(dr, (lx + lw // 2 + (1 if k == 0 else 0), yy + 21 + (1 if k == 0 else 0)),
                      lab, fb16, P.TEXT_LIGHT)
        yy += 52

    # ---- right: command panel (dark) with tabs ---------------------------------------------------
    rx, ry, rw, rh = W - 24 - 440, 92, 440, 700
    bg.alpha_composite(P.nine(P.load("Panel"), ms["Panel"], (rw, rh)), (rx, ry))
    dr.text((rx + 18, ry + 16), "Luoyang: 2 officers awaiting orders", font=f13, fill=P.INK)
    tabs = ["Domestic", "Military", "Personnel", "Diplomacy", "Town"]
    tw = (rw - 28 - 4 * 2) // 5
    tx0, ty0 = rx + 14, ry + 40
    for k, lab in enumerate(tabs):
        act = k == 1
        t = P.nine(P.load("Tab_Active" if act else "Tab"), ms["Tab"], (tw, 36))
        if not act:
            a = np.asarray(t, np.float32)
            a[..., :3] *= 0.78
            t = Image.fromarray(a.astype(np.uint8), "RGBA")
        bg.alpha_composite(t, (tx0 + k * (tw + 2), ty0))
        dr.text((tx0 + k * (tw + 2) + tw // 2, ty0 + 18), lab, font=f13b if act else f13,
                fill=P.LACQUER if act else P.INK, anchor="mm")
    dr.text((rx + 26, ty0 + 52), "Military", font=fh26, fill=P.LACQUER)
    bg.alpha_composite(P.load("Divider").resize((rw - 52, 12), Image.BICUBIC), (rx + 26, ty0 + 88))
    yy = ty0 + 112
    for k, lab in enumerate(("Draft", "Train", "Patrol", "Transport", "March")):
        st = "Button_Disabled" if lab == "Transport" else "Button"
        b = P.nine(P.load(st), ms["Button"], (rw - 52, 44))
        bg.alpha_composite(b, (rx + 26, yy))
        P.text_shadow(dr, (rx + rw // 2, yy + 22), lab, fb16,
                      (170, 160, 150) if st == "Button_Disabled" else P.TEXT_LIGHT)
        yy += 54
    bg.alpha_composite(P.load("Divider").resize((rw - 52, 10), Image.BICUBIC), (rx + 26, yy + 6))
    b = P.nine(P.load("Button"), ms["Button"], (rw - 52, 44))
    bg.alpha_composite(b, (rx + 26, yy + 28))
    P.text_shadow(dr, (rx + rw // 2, yy + 50), "Delegate this city", fb16, P.TEXT_LIGHT)

    # ---- bottom: message log (light panel, 16 x 10 padding) and a dark battle-style panel -----
    lgx, lgy, lgw, lgh = 24, 812, 900, 244
    bg.alpha_composite(P.nine(P.load("Panel"), ms["Panel"], (lgw, lgh)), (lgx, lgy))
    for k, ln in enumerate(("Spring 184: Iron Banner troops entered Xuchang.",
                            "Cao Ren completed the walls of Luoyang (Walls 640).",
                            "A wandering swordsman was seen near Mount Hua.",
                            "The Azure Court proposes a truce.",
                            "Harvest in Ye: +8,600 food.")):
        dr.text((lgx + 16, lgy + 10 + k * 22), ln, font=fr15, fill=P.INK)
    dkx, dky, dkw, dkh = 944, 812, 520, 244
    bg.alpha_composite(P.nine(P.load("PanelDark"), ms["PanelDark"], (dkw, dkh)), (dkx, dky))
    dr.text((dkx + 22, dky + 18), "Zhang Liao", font=fh26, fill=P.GOLD)
    for k, ln in enumerate(("Cavalry   Troops 6,400   Morale 82", "Attack 88   Defense 71",
                            "Fire  Confuse  Rally  Duel")):
        dr.text((dkx + 22, dky + 60 + k * 24), ln, font=fr15, fill=P.TEXT_LIGHT)
    for k, st in enumerate(("Button", "Button_Hover", "Button_Pressed")):
        b = P.nine(P.load(st), ms["Button"], (150, 44))
        bg.alpha_composite(b, (dkx + 22 + k * 162, dky + 170))
        off = 1 if st == "Button_Pressed" else 0
        P.text_shadow(dr, (dkx + 22 + k * 162 + 75 + off, dky + 192 + off),
                      ("Attack", "Duel", "Wait")[k], fb16, P.TEXT_LIGHT)

    # ---- centre: event dialog ----------------------------------------------------------------------
    dw, dh = 1040, 700
    dx, dy = (W - dw) // 2, 200
    shadow = Image.new("RGBA", (dw + 60, dh + 60), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle((30, 40, dw + 30, dh + 30), fill=(0, 0, 0, 120))
    bg.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)), (dx - 30, dy - 30))
    bg.alpha_composite(P.nine(P.load("Scroll"), ms["Scroll"], (dw, dh)), (dx, dy))
    dr.text((dx + dw // 2, dy + 78), "A Wandering Swordsman", font=P.font("Heading.ttf", 30),
            fill=P.LACQUER, anchor="mm")
    bg.alpha_composite(P.load("Divider").resize((dw - 200, 12), Image.BICUBIC), (dx + 100, dy + 100))
    ev = _event()
    if ev:
        ill = Image.open(ev).convert("RGBA").resize((533, 300), Image.LANCZOS)
        bg.alpha_composite(ill, (dx + (dw - 533) // 2, dy + 128))
    else:
        ill = Image.new("RGBA", (640, 300), (120, 110, 95, 255))
        bg.alpha_composite(ill, (dx + 200, dy + 128))
        dr.text((dx + 520, dy + 278), "[event illustration]", font=fr15, fill=(230, 220, 200),
                anchor="mm")
    dr.text((dx + 100, dy + 446), "A ragged traveller asks for an audience. He claims to have studied",
            font=P.font("Body-Regular.ttf", 17), fill=P.INK)
    dr.text((dx + 100, dy + 470), "the sword under the hermits of Mount Hua and offers his service.",
            font=P.font("Body-Regular.ttf", 17), fill=P.INK)
    for k, lab in enumerate(("Welcome him", "Send him away")):
        b = P.nine(P.load("Button"), ms["Button"], (260, 44))
        bx = dx + dw // 2 - 280 + k * 300
        bg.alpha_composite(b, (bx, dy + 540))
        P.text_shadow(dr, (bx + 130, dy + 562), lab, fb16, P.TEXT_LIGHT)

    bg.convert("RGB").save(os.path.join(out, "context_mock.png"))
    bg.convert("RGB").resize((1280, 720), Image.LANCZOS).save(os.path.join(out, "context_mock_720.png"))
