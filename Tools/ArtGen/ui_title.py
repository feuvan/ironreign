#!/usr/bin/env python3
"""Iron Reign title screen art: Title_Background.png (1920x1080) and Title_Logo.png (1200x400).

    python3 Tools/ArtGen/ui_title.py [--fast] [background] [logo]

--fast renders at 1x instead of 2x supersampling (for quick iteration; output size unchanged).

Background: dusk ink-wash landscape, layered karst mountains with atmospheric perspective, a walled
fortress with red banners on the right-hand ridge, a river catching the setting sun, a foreground
pine. The left ~40% is kept calm (haze, low contrast) for the main menu.
Logo: 铁血王座 in brush calligraphy (Brush.ttf) with dry-brush texture, "IRON REIGN" in
Heading.ttf with a gold/bronze bevel, and the red Seal.
"""
import math
import os
import sys

import numpy as np
from scipy import ndimage

from artlib_ui import (ART, FONT_BRUSH, FONT_HEADING, PAL, Layer, Mask, Painting, blur, clamp01,
                       dilate, emboss, fbm, figure, flag, font, hexc, inner_dist, make_seal, mix,
                       noise1d, pavilion, roof_poly, shade, shift, smoothstep)

OUT = os.path.join(ART, "UI")
FAST = "--fast" in sys.argv


# ----------------------------------------------------------------------------------------------
# Fortress builder (shared idea with the event paintings)
# ----------------------------------------------------------------------------------------------

def fortress(p, ridge, x0, x1, wall_h, towers, banners_every=46, seed=3, body_col=None, roof_col=None,
             rim_col=None, banner_col=None, window_col=None, scale=1.0, wind=1):
    """Walls following `ridge` between x0..x1 with towers [(x, width, tiers)], banners on poles.
    All in output px. Paints directly into Painting p."""
    rng = np.random.default_rng(seed)
    s = p.s
    xs = np.arange(int(x0), int(x1) + 1)
    rid = np.array([ridge[min(p.W - 1, int(x * s))] for x in xs], np.float32)
    rid = ndimage.gaussian_filter1d(rid, 6 * scale)
    top = rid - wall_h
    body = p.mask()
    wall = [(x, t) for x, t in zip(xs, top)] + [(x, r + wall_h * 0.6) for x, r in zip(xs[::-1], rid[::-1])]
    body.poly(wall)
    # crenellations
    step = 9 * scale
    x = x0 + 2
    while x < x1 - 4:
        i = int(x - x0)
        body.rect(x, top[i] - 5 * scale, x + 5 * scale, top[i] + 1)
        x += step
    roofs = p.mask()
    wins = p.mask()
    rims = p.mask()
    for (tx, tw, tiers) in towers:
        i = int(np.clip(tx - x0, 0, len(xs) - 1))
        base = top[i] + wall_h * 0.25
        parts = pavilion(Mask(1, 1), tx, base, tw, tiers=tiers, story_h=tw * 0.36, roof_h=tw * 0.22)
        for kind, poly in parts:
            if kind == "body":
                body.poly(poly)
                xs_ = [q[0] for q in poly]
                ys_ = [q[1] for q in poly]
                # windows: a row of small lit openings
                bx0, bx1, by0, by1 = min(xs_), max(xs_), min(ys_), max(ys_)
                n = max(2, int((bx1 - bx0) / (9 * scale)))
                for k in range(n):
                    wx = bx0 + (k + 0.5) * (bx1 - bx0) / n
                    if rng.random() < 0.65:
                        wins.rect(wx - 1.5 * scale, by0 + (by1 - by0) * 0.35, wx + 1.5 * scale, by0 + (by1 - by0) * 0.75)
                rims.rect(bx0, by0, bx0 + 1.6 * scale, by1)
            else:
                roofs.poly(poly)
                rims.poly([(q[0] - 0.8 * scale, q[1] - 0.8 * scale) for q in poly[: len(poly) // 2]] +
                          [(q[0], q[1]) for q in poly[: len(poly) // 2]][::-1])
    # gate in the main tower
    bm = body.arr()
    rm = roofs.arr()
    p.paint(body_col, bm)
    p.paint(roof_col, rm)
    p.paint(rim_col, rims.arr() * (bm + rm).clip(0, 1), 0.55)
    p.paint(window_col, wins.arr() * bm, 0.9)
    # banners on poles along the wall top
    poles = p.mask()
    cloth = p.mask()
    x = x0 + 14
    k = 0
    while x < x1 - 10:
        i = int(x - x0)
        if all(abs(x - t[0]) > t[1] * 0.6 for t in towers):
            yb = top[i] - 2
            ph = (34 + rng.uniform(-4, 6)) * scale
            poles.line([(x, yb), (x, yb - ph)], 1.6 * scale, round_caps=False)
            flag(cloth, x, yb - ph + 1, 20 * scale, 11 * scale, wave=0.35, facing=wind, phase=k * 1.7)
        x += banners_every * scale * rng.uniform(0.8, 1.2)
        k += 1
    p.paint(body_col, poles.arr())
    p.paint(banner_col, cloth.arr())


# ----------------------------------------------------------------------------------------------
# Title background
# ----------------------------------------------------------------------------------------------

def title_background():
    ss = 1 if FAST else 2
    p = Painting(1920, 1080, ss=ss, seed=101)
    W, H = 1920, 1080
    # dusk sky
    p.vgradient([(0.0, hexc("4F4A57")), (0.22, hexc("7C6E72")), (0.45, hexc("C59C80")),
                 (0.58, hexc("E9BE8A")), (0.66, hexc("EFCB98")), (1.0, hexc("D8B488"))])
    # setting sun and glow
    sx, sy = 1180, 548
    p.glow(sx, sy, 520, hexc("F6C27A"), 0.55, power=1.4)
    p.glow(sx, sy, 160, hexc("FFE0A0"), 0.55, power=1.6)
    p.disc(sx, sy, 58, hexc("EE8E5A"), 0.95, soft=2.0)
    p.glow(sx, sy, 64, hexc("FFD9A0"), 0.35, power=4)
    # long cloud streaks, lit from below near the sun
    rng = np.random.default_rng(7)
    for (cy, ch, op, col) in ((150, 70, 0.35, hexc("3E3946")), (260, 60, 0.30, hexc("5A4B52")),
                              (380, 40, 0.35, hexc("8C6E66")), (455, 26, 0.45, hexc("B98A72"))):
        p.mist(cy, ch, col, op, seed=int(cy), cell=260, streak=True)
    cl = smoothstep(0.62, 0.0, np.hypot((p.X - sx) / 700, (p.Y - sy) / 300)) * smoothstep(300, 470, p.Y) * smoothstep(560, 470, p.Y)
    p.add_light(hexc("FFB070"), cl * 0.25)
    # birds
    bm = p.mask()
    for (bx, by, bs) in ((1010, 330, 9), (1040, 318, 7), (1062, 340, 6), (985, 352, 5), (1092, 326, 5), (1120, 300, 4)):
        bm.brush([(bx - bs, by - bs * 0.2), (bx - bs * 0.4, by - bs * 0.45), (bx, by)], bs * 0.28, bs * 0.12)
        bm.brush([(bx, by), (bx + bs * 0.45, by - bs * 0.5), (bx + bs, by - bs * 0.25)], bs * 0.28, bs * 0.08)
    p.paint(hexc("3A3036"), bm.arr(), 0.85)

    mist_col = hexc("E7CDA4")
    # far range 1 (very pale karst peaks)
    r1 = p.ridge(640, [(120, 120, 140, "karst"), (380, 80, 120, "karst"), (700, 160, 110, "sharp"),
                       (860, 220, 90, "karst"), (980, 150, 110, "karst"), (1400, 240, 90, "karst"),
                       (1540, 300, 80, "karst"), (1660, 200, 100, "sharp"), (1850, 260, 120, "karst")],
                 rough=18, rough_cell=70, jag=2, seed=11)
    p.mountain(r1, hexc("A08C94"), mist_col, fade=150, texture=0.18, edge=0.25, edge_w=2.0, seed=12, lit=0.05)
    p.mist(650, 90, mist_col, 0.85, seed=13, cell=220)
    # far range 2
    r2 = p.ridge(720, [(60, 200, 120, "karst"), (260, 120, 100, "round"), (560, 90, 140, "round"),
                       (930, 150, 120, "karst"), (1120, 110, 110, "round"), (1330, 260, 85, "karst"),
                       (1470, 190, 90, "karst"), (1760, 330, 95, "karst"), (1900, 220, 90, "karst")],
                 rough=20, rough_cell=60, jag=2.5, seed=21)
    p.mountain(r2, hexc("7E6E78"), hexc("D7BC9A"), fade=160, texture=0.25, edge=0.35, edge_w=2.2, seed=22, lit=0.08)
    p.tree_dots(r2, hexc("5A4C55"), density=0.06, size=1.6, xr=(1200, 1920), seed=23, opacity=0.6)
    p.mist(760, 110, mist_col, 0.9, seed=24, cell=240)
    # the fortress ridge (mid ground, right)
    r3 = p.ridge(860, [(1060, 120, 220, "round"), (1330, 300, 220, "dome"), (1560, 320, 260, "dome"),
                       (1790, 300, 220, "dome"), (700, 60, 180, "round")],
                 rough=14, rough_cell=50, jag=1.5, seed=31, smooth=20)
    p.mountain(r3, hexc("3C3438"), hexc("B39A88"), fade=210, texture=0.4, edge=0.6, edge_w=2.6, seed=32, lit=0.12)
    p.tree_dots(r3, hexc("2A2428"), density=0.10, size=2.2, xr=(980, 1290), seed=33, opacity=0.85)
    p.tree_dots(r3, hexc("2A2428"), density=0.10, size=2.2, xr=(1790, 1920), seed=34, opacity=0.85)
    fortress(p, r3, 1290, 1800, 30, [(1340, 70, 2), (1545, 118, 3), (1730, 76, 2)], seed=35,
             body_col=hexc("2E282B"), roof_col=hexc("1F1B1F"), rim_col=hexc("F2B276"),
             banner_col=hexc("A82A26"), window_col=hexc("F3B060"))
    # valley mist and river
    p.mist(890, 120, mist_col, 0.85, seed=41, cell=260)
    p.haze(820, 1000, hexc("E2C49A"), 0.35)
    # river band reflecting the sun
    rv = p.mask()
    rv.poly([(0, 948), (420, 930), (800, 918), (1180, 912), (1500, 916), (1920, 926), (1920, 958),
             (1500, 948), (1180, 944), (800, 952), (420, 966), (0, 990)])
    rvm = blur(rv.arr(), 2 * ss)
    p.paint(hexc("E4C79A"), rvm, 0.75)
    rng = np.random.default_rng(42)
    st = p.mask()
    for _ in range(140):
        x = rng.normal(sx, 160)
        y = rng.uniform(912, 958)
        L = rng.uniform(8, 40) * (1 - min(1, abs(x - sx) / 500))
        if L > 3:
            st.brush([(x - L / 2, y), (x + L / 2, y)], 1.4, 0.6)
    p.paint(hexc("FFE3B0"), st.arr() * rvm, 0.8)
    # near hills (left low and soft, right darker)
    r4 = p.ridge(1000, [(160, 70, 260, "round"), (560, 40, 200, "round"), (1500, 60, 280, "round"),
                        (1850, 150, 220, "round")], rough=10, rough_cell=60, jag=1.2, seed=51, smooth=20)
    p.mountain(r4, hexc("4A3E3A"), hexc("A88C72"), fade=120, texture=0.35, edge=0.5, edge_w=2.4, seed=52, lit=0.1)
    # foreground rocks right + big pine
    r5 = p.ridge(1100, [(1760, 190, 220, "dome"), (1950, 260, 160, "dome")], rough=12, rough_cell=40, jag=1.5,
                 seed=61, smooth=15)
    p.mountain(r5, hexc("221C1C"), hexc("5A4A42"), fade=160, texture=0.45, edge=0.7, edge_w=3.0, seed=62, lit=0.15)
    pm = p.mask()
    p.pine(pm, 1735, 925, 380, lean=-0.22, seed=4, pads=7, spread=1.3)
    p.pine(pm, 1868, 905, 300, lean=-0.05, seed=9, pads=6, spread=1.1)
    p.paint(hexc("1A1716"), pm.arr())
    # grass at the very bottom left, very soft
    gm = p.mask()
    p.grass_tufts(gm, 0, 700, lambda x: 1080 - 30 + 18 * math.sin(x / 90.0), np.random.default_rng(5),
                  density=0.08, hmin=10, hmax=26)
    p.paint(hexc("4A3E36"), gm.arr(), 0.55)

    # calm the left side: lift towards warm haze, reduce contrast
    calm = smoothstep(0.52, 0.12, p.X / W) * (0.55 + 0.45 * smoothstep(1000, 400, p.Y))
    p.paint(hexc("D9BE98"), calm, 0.32)
    p.paper(strength=0.05, seed=77)
    p.vignette(0.42, color=(0.12, 0.08, 0.06), inner=0.55)
    p.grade(sat=0.92, gamma=1.02)
    p.save(os.path.join(OUT, "Title_Background.png"))


# ----------------------------------------------------------------------------------------------
# Logo
# ----------------------------------------------------------------------------------------------

def title_logo():
    S = 2 if FAST else 3
    w, h = 1200, 400
    W, H = w * S, h * S
    rng = np.random.default_rng(303)
    lay = Layer(W, H)

    # --- calligraphy ---
    cal = Mask(W, H, S)
    chars = [("铁", 150, 150, 230, -3), ("血", 382, 148, 222, 2), ("王", 604, 146, 214, -1), ("座", 838, 150, 236, 3)]
    for ch, cx, cy, size, ang in chars:
        f = font(FONT_BRUSH, size * S)
        g = Mask(int(size * 1.6 * S), int(size * 1.6 * S), S)
        g.text((size * 0.8, size * 0.8), ch, f)
        ga = g.im.rotate(ang, resample=3)
        cal.im.paste(ga, (int((cx - size * 0.8) * S), int((cy - size * 0.8) * S)), ga)
    cm = cal.arr()
    # dry brush streaks near stroke edges
    d = inner_dist(cm) / S
    streak = fbm(H, W, 7 * S, rng, octaves=3, aniso=(0.12, 1.0)) - 0.5
    streak2 = fbm(H, W, 9 * S, rng, octaves=3, aniso=(1.0, 0.15)) - 0.5
    dry = clamp01((np.maximum(streak, streak2) - 0.12) * 5) * clamp01(1 - d / 7.0)
    ink_a = cm * (1 - 0.85 * dry)
    # splatter
    sp = Mask(W, H, S)
    for _ in range(26):
        x = rng.uniform(60, 980)
        y = rng.uniform(40, 270)
        r = rng.exponential(2.0) + 0.6
        sp.circle(x, y, r)
    spm = sp.arr() * (1 - cm)
    near = blur(cm, 22 * S)
    spm = spm * clamp01(near * 6)
    # pale mist glow behind the calligraphy so it reads over the painting
    glow = blur(dilate(cm, 10 * S), 18 * S)
    lay.paint(hexc("F2E3C4"), clamp01(glow * 1.3), 0.55)
    ink = hexc("1A1410")
    tone = (fbm(H, W, 30 * S, rng, octaves=3) - 0.5)[..., None] * 0.25
    lay.paint(np.clip(ink * (1 + tone) + 0.02, 0, 1), clamp01(ink_a + spm * 0.9))

    # --- IRON REIGN ---
    txt = Mask(W, H, S)
    f = font(FONT_HEADING, 116 * S)
    letters = "IRON REIGN"
    track = 14
    widths = [f.getlength(c) / S for c in letters]
    total = sum(widths) + track * (len(letters) - 1)
    x = 520 - total / 2
    ty = 338
    for c, cw in zip(letters, widths):
        txt.d.text((x * S, ty * S), c, font=f, fill=255, anchor="ls")
        x += cw + track
    tm = txt.arr()
    # gold bevel: height from inner distance
    td = inner_dist(tm) / S
    hgt = np.minimum(td, 3.5)
    sh = emboss(blur(hgt, 0.8 * S) * S, strength=0.9)
    yy = (np.arange(H, dtype=np.float32)[:, None] + 0.5) / S
    vert = smoothstep(ty - 88, ty + 4, yy)
    base = mix(hexc("F4DB8E"), hexc("9A6A26"), np.broadcast_to(vert, (H, W)))
    # horizon line of polished metal
    band_ = np.exp(-((yy - (ty - 40)) / 5.0) ** 2) * 0.35
    base = mix(base, hexc("FFF6D2"), np.broadcast_to(band_, (H, W)))
    gold = shade(base, sh, hexc("FFF8DC"), hexc("5A3A12"), 0.8, 0.7)
    outline = clamp01(dilate(tm, 3.2 * S))
    shadow = blur(shift(outline, 5 * S, 4 * S), 4 * S)
    lay.paint(hexc("0E0A07"), clamp01(shadow) * 0.65)
    lay.paint(hexc("1E140C"), outline)
    lay.paint(np.clip(gold, 0, 1), tm)

    # flanking rules with diamonds
    rl = Mask(W, H, S)
    for sgn in (-1, 1):
        x_in = 520 + sgn * (total / 2 + 30)
        x_out = 520 + sgn * (total / 2 + 150)
        rl.brush([(x_in, ty - 40), (x_out, ty - 40)], 3.0, 0.6)
        rl.poly([(x_in + sgn * 2, ty - 48), (x_in - sgn * 8, ty - 40), (x_in + sgn * 2, ty - 32), (x_in + sgn * 12, ty - 40)])
    rlm = rl.arr()
    lay.paint(hexc("1E140C"), clamp01(dilate(rlm, 1.6 * S)))
    lay.paint(mix(hexc("F0D48A"), hexc("A87A30"), 0.35), rlm)

    out = lay.reduced(S)
    # seal at the end of the calligraphy
    seal = make_seal(150, seed=8, rot=-4)
    sx, sy = 1020, 66
    big = Layer(w, h)
    big.c[sy:sy + 150, sx:sx + 150] = seal.c
    big.a[sy:sy + 150, sx:sx + 150] = seal.a
    out.paint_layer(big)
    out.save(os.path.join(OUT, "Title_Logo.png"))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args or "background" in args:
        title_background()
    if not args or "logo" in args:
        title_logo()


if __name__ == "__main__":
    main()
