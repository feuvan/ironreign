#!/usr/bin/env python3
"""Iron Reign UI chrome: 9-slice panels, buttons, tabs, portrait frame, seal, scroll, divider.

    python3 Tools/ArtGen/ui_skin.py

Outputs (Content/Data/Art/UI/):
    Panel.png, PanelDark.png               128x128  9-slice, 24 px margins on all sides
    Button{,_Hover,_Pressed,_Disabled}.png 192x64   9-slice, 20 px left/right, 16 px top/bottom
    Tab.png, Tab_Active.png                160x48   9-slice, 16 px left/right, 14 px top, 8 px bottom
    Frame_Portrait.png                     212x260  10 px frame around a 192x240 transparent hole
    Seal.png                               128x128
    Scroll.png                             1024x640 9-slice, 80 px margins on all sides
    Divider.png                            512x16

Design rules for the 9-slice pieces: every styling term is a function of the distance to the
outer edge (so edge strips are constant along their length and stretch cleanly), and the centre
region is a flat colour with only faint grain.
"""
import os

import numpy as np

from artlib_ui import (ART, PAL, Layer, Mask, band, clamp01, emboss, fbm, hexc, make_seal, mix,
                       rrect_sdf, shade, smoothstep, paper_grain, inner_dist, blur)

OUT = os.path.join(ART, "UI")
S = 4  # supersampling for chrome


def P(name):
    return os.path.join(OUT, name)


def grain(h, w, seed, amp, scale=1.0):
    rng = np.random.default_rng(seed)
    return paper_grain(h, w, rng, scale=scale) * amp


# ----------------------------------------------------------------------------------------------
# Corner ornaments
# ----------------------------------------------------------------------------------------------

def stepped_frame_line(m, w, h, inset, step, lw):
    """Inner frame line with stepped (notched) corners, drawn on Mask m in output px."""
    a, b = inset, inset + step
    # straight runs
    m.line([(b, a), (w - b, a)], lw, round_caps=False)
    m.line([(b, h - a), (w - b, h - a)], lw, round_caps=False)
    m.line([(a, b), (a, h - b)], lw, round_caps=False)
    m.line([(w - a, b), (w - a, h - b)], lw, round_caps=False)
    for sx, sy in ((0, 0), (1, 0), (0, 1), (1, 1)):
        def T(x, y):
            return (w - x if sx else x, h - y if sy else y)
        m.line([T(b + lw / 2, a), T(b, a), T(b, b), T(a, b), T(a, b + lw / 2)], lw, round_caps=False)
    return m


def corner_dots(m, w, h, c, r):
    for x, y in ((c, c), (w - c, c), (c, h - c), (w - c, h - c)):
        m.poly([(x, y - r), (x + r, y), (x, y + r), (x - r, y)])
    return m


# ----------------------------------------------------------------------------------------------
# Panels
# ----------------------------------------------------------------------------------------------

def panel(dark):
    w = h = 128
    W, H = w * S, h * S
    d = -rrect_sdf(H, W, 0, 0, W, H, 4.0 * S) / S          # distance inside, output px
    inside = clamp01(d * S + 0.5)
    lay = Layer(W, H)

    if not dark:
        paper = PAL["paper"]
        frame = hexc("6E4C2C")
        rim = PAL["ink"]
        field = paper.copy()
        # height profile -> bevel lighting on the mount band and the gold trim
        hgt = (band(d, 1.6, 7.5, 0.5) * np.sin(np.clip((d - 1.6) / 5.9, 0, 1) * np.pi) * 1.6
               + band(d, 10.0, 12.6, 0.5) * np.sin(np.clip((d - 10.0) / 2.6, 0, 1) * np.pi) * 1.2)
        sh = emboss(blur(hgt, S * 0.4) * S, strength=1.3)
        col = np.broadcast_to(field, (H, W, 3)).copy()
        # aged paper towards the frame (function of d only)
        age = np.exp(-np.maximum(d - 12.6, 0) / 4.5)
        col = mix(col, PAL["paper_dark"], age * 0.55)
        # mount band
        fcol = shade(frame, sh, hexc("B08A5A"), hexc("2E1C0E"), 0.8, 0.85)
        fgloss = band(d, 2.4, 3.8, 1.0) * clamp01(sh) * 0.25
        fcol = mix(fcol, hexc("E2C49A"), fgloss)
        col = mix(col, fcol, band(d, 1.6, 7.5, 0.6))
        # ink lines
        col = mix(col, rim, band(d, -1, 1.7, 0.6))
        col = mix(col, rim, band(d, 7.3, 8.8, 0.6) * 0.9)
        # gold trim
        gcol = shade(PAL["gold"], sh, PAL["gold_light"], PAL["gold_dark"], 1.0, 1.0)
        col = mix(col, gcol, band(d, 10.0, 12.6, 0.6))
        col = mix(col, PAL["ink"], band(d, 12.6, 13.4, 0.6) * 0.35)  # shadow under trim
        # stepped inner line with corner diamonds
        m = Mask(W, H, S)
        stepped_frame_line(m, w, h, 16.5, 4.5, 1.1)
        col = mix(col, PAL["ink_soft"], m.arr() * 0.85)
        m = Mask(W, H, S)
        corner_dots(m, w, h, 18.75, 1.9)
        dm = m.arr()
        col = mix(col, PAL["lacquer"], dm)
        # grain (subtle; strong only on the band)
        g = grain(H, W, 11, 1.0, scale=S)
        amp = 0.018 + 0.03 * band(d, 1.6, 7.5, 0.6)
        col = col * (1 + g[..., None] * amp[..., None])
    else:
        night = PAL["night"]
        frame = hexc("4A1A12")
        hgt = (band(d, 1.4, 8.0, 0.5) * np.sin(np.clip((d - 1.4) / 6.6, 0, 1) * np.pi) * 2.0
               + band(d, 9.6, 12.2, 0.5) * np.sin(np.clip((d - 9.6) / 2.6, 0, 1) * np.pi) * 1.2)
        sh = emboss(blur(hgt, S * 0.4) * S, strength=1.3)
        col = np.broadcast_to(night, (H, W, 3)).copy()
        col = mix(col, hexc("2A231B"), smoothstep(40, 13, d) * 0.0)
        # inner shadow under the frame
        col = col * (1 - 0.45 * np.exp(-np.maximum(d - 12.2, 0) / 3.0))[..., None]
        # lacquer frame with glossy bevel
        fcol = shade(frame, sh, hexc("9A4A35"), hexc("1A0705"), 0.75, 0.9)
        gloss = band(d, 2.4, 4.0, 1.2) * clamp01(sh) * 0.35
        fcol = mix(fcol, hexc("D9A07A"), gloss)
        col = mix(col, fcol, band(d, 1.4, 8.0, 0.6))
        col = mix(col, hexc("0D0907"), band(d, -1, 1.5, 0.6))
        col = mix(col, hexc("0D0907"), band(d, 8.0, 9.6, 0.6))
        gcol = shade(PAL["gold"], sh, PAL["gold_light"], PAL["gold_dark"], 1.0, 1.0)
        col = mix(col, gcol, band(d, 9.6, 12.2, 0.6))
        m = Mask(W, H, S)
        stepped_frame_line(m, w, h, 16.5, 4.5, 1.0)
        col = mix(col, hexc("8C7038"), m.arr() * 0.9)
        m = Mask(W, H, S)
        corner_dots(m, w, h, 18.75, 1.9)
        col = mix(col, PAL["gold"], m.arr())
        # gold corner fittings over the frame band
        fit = Mask(W, H, S)
        for sx in (0, 1):
            for sy in (0, 1):
                def T(x, y):
                    return (w - x if sx else x, h - y if sy else y)
                L = 13.0
                fit.poly([T(1.2, 1.2), T(L, 1.2), T(L, 3.2), T(5.2, 3.2), T(3.2, 5.2), T(3.2, L), T(1.2, L)])
        fm = fit.arr()
        fh = blur(fm, S * 0.6) * 1.5
        fsh = emboss(fh * S, strength=1.6)
        fc = shade(hexc("B8913F"), fsh, PAL["gold_light"], PAL["gold_dark"], 1.0, 1.0)
        col = mix(col, fc, fm)
        g = grain(H, W, 12, 1.0, scale=S)
        amp = 0.03 + 0.04 * band(d, 1.4, 8.0, 0.6)
        col = col * (1 + g[..., None] * amp[..., None])
    lay.paint(np.clip(col, 0, 1), inside)
    return lay.reduced(S)


# ----------------------------------------------------------------------------------------------
# Buttons and tabs
# ----------------------------------------------------------------------------------------------

BUTTON_STATES = {
    #           face top    face bottom  rim        edge        edge hi     glow  emboss  gloss
    "normal":   ("982A1E", "61160F", "250907", "B08A3E", "E8C873", 0.0, 1.0, 0.10),
    "hover":    ("B0352A", "7A1F16", "2A0A07", "E2BC5C", "FFF0B0", 0.45, 1.0, 0.14),
    "pressed":  ("4C110B", "6A1910", "1C0605", "8E7034", "C8A85A", 0.0, -1.0, 0.0),
    "disabled": ("5E504A", "463A34", "231C18", "7E7464", "A49A86", 0.0, 0.6, 0.03),
}


def lacquer_shape(w, h, state, radius, open_bottom=False, seed=3):
    """Shared renderer for buttons and tabs."""
    top, bot, rim, edge, edge_hi, glow, emb, gloss = BUTTON_STATES[state]
    W, H = w * S, h * S
    if open_bottom:
        sdf = rrect_sdf(H, W, 0.5 * S, 0.5 * S, W - 0.5 * S, H + 40 * S, radius * S, top_only=True)
    else:
        sdf = rrect_sdf(H, W, 0.5 * S, 0.5 * S, W - 0.5 * S, H - 0.5 * S, radius * S)
    d = -sdf / S
    inside = clamp01(d * S + 0.5)
    y = (np.arange(H, dtype=np.float32)[:, None] + 0.5) / S
    t = np.broadcast_to(y / h, (H, W))
    face = mix(hexc(top), hexc(bot), smoothstep(0.0, 1.0, t))
    # bevel: pillow rising over the first pixels inside the gold edge
    hgt = smoothstep(4.0, 9.5, d) * 2.2 * emb + band(d, 1.4, 3.6, 0.5) * np.sin(np.clip((d - 1.4) / 2.2, 0, 1) * np.pi) * 1.0
    sh = emboss(blur(hgt, S * 0.5) * S, strength=1.2)
    face_sh = shade(face, sh * band(d, 3.6, 99, 0.6), face * 1.45, face * 0.55, 0.55, 0.6)
    col = face_sh
    # gloss on the upper part of the face
    if gloss > 0:
        gm = smoothstep(h * 0.55, h * 0.12, y) * smoothstep(4.5, 8.0, d) * gloss
        col = mix(col, hexc("FFE6C8"), np.broadcast_to(gm, (H, W)))
    # lacquer grain
    rng = np.random.default_rng(seed)
    g = fbm(H, W, 30 * S, rng, octaves=4, aniso=(0.25, 3.0)) - 0.5
    col = col * (1 + g[..., None] * 0.06)
    # inner gold glow (hover)
    if glow > 0:
        gl = np.exp(-np.maximum(d - 3.6, 0) / 3.0) * band(d, 3.4, 99, 0.6) * glow
        col = mix(col, hexc("F0C060"), gl)
    # dark gap, gold edge, rim
    col = mix(col, hexc(rim), band(d, 3.4, 4.4, 0.6) * 0.85)
    ecol = shade(hexc(edge), sh, hexc(edge_hi), hexc(edge) * 0.55, 1.0, 0.9)
    col = mix(col, ecol, band(d, 1.4, 3.6, 0.6))
    col = mix(col, hexc(rim), band(d, -1, 1.5, 0.6))
    # corner brackets (inside the corner regions only)
    m = Mask(W, H, S)
    k = 7.0
    o = 6.2
    corners = ((0, 0), (1, 0)) if open_bottom else ((0, 0), (1, 0), (0, 1), (1, 1))
    for sx, sy in corners:
        def T(px, py):
            return (w - px if sx else px, h - py if sy else py)
        m.line([T(o, o + k - 1.5), T(o, o), T(o + k + 1.0, o)], 1.0, round_caps=False)
    bm = m.arr()
    col = mix(col, mix(hexc(edge), hexc(edge_hi), 0.35), bm * 0.9)
    lay = Layer(W, H)
    lay.paint(np.clip(col, 0, 1), inside)
    if open_bottom:
        # tabs: fade the bottom rows slightly into shadow so the tab sits behind the panel edge
        pass
    return lay.reduced(S)


def tab(active):
    w, h = 160, 48
    if active:
        lay = lacquer_shape(w, h, "hover" if False else "normal", 9.0, open_bottom=True, seed=21)
        # brighten slightly and add a gold underline? Active tab opens into the panel below.
        rgb, a = lay.straight()
        rgb = np.clip(rgb * 1.12, 0, 1)
        out = Layer(w, h)
        out.paint(rgb, a)
        return out
    # inactive: dark brown lacquer, dim bronze edge, recessed (darker towards the bottom)
    saved = BUTTON_STATES["normal"]
    BUTTON_STATES["_tab"] = ("4A3527", "2C2019", "140E0A", "8C6F3A", "C2A162", 0.0, 0.8, 0.06)
    lay = lacquer_shape(w, h, "_tab", 9.0, open_bottom=True, seed=22)
    BUTTON_STATES["normal"] = saved
    return lay


# ----------------------------------------------------------------------------------------------
# Portrait frame
# ----------------------------------------------------------------------------------------------

def portrait_frame():
    w, h = 212, 260
    W, H = w * S, h * S
    d = -rrect_sdf(H, W, 0, 0, W, H, 3.0 * S) / S
    inside = clamp01(d * S + 0.5)
    hgt = (band(d, 0.8, 3.8, 0.5) * np.sin(np.clip((d - 0.8) / 3.0, 0, 1) * np.pi) * 1.4
           + band(d, 4.4, 8.0, 0.5) * (1 - np.sin(np.clip((d - 4.4) / 3.6, 0, 1) * np.pi)) * 0.6
           + band(d, 8.0, 9.3, 0.5) * 0.8)
    sh = emboss(blur(hgt, S * 0.4) * S, strength=1.4)
    col = np.zeros((H, W, 3), np.float32)
    lac = shade(hexc("4E1A12"), sh, hexc("8E3E2C"), hexc("1E0806"), 0.7, 0.8)
    col = mix(col, lac, band(d, 3.0, 9.0, 0.5))
    gold = shade(PAL["gold"], sh, PAL["gold_light"], PAL["gold_dark"], 1.0, 1.0)
    col = mix(col, gold, band(d, 0.8, 3.8, 0.6))
    col = mix(col, gold * 0.95, band(d, 8.0, 9.3, 0.6))
    col = mix(col, hexc("120C09"), band(d, -1, 0.9, 0.6))
    col = mix(col, hexc("120C09"), band(d, 3.7, 4.5, 0.6))
    col = mix(col, hexc("120C09"), band(d, 9.2, 10.5, 0.6))
    # corner caps and mid-edge studs
    m = Mask(W, H, S)
    for x, y in ((5, 5), (w - 5, 5), (5, h - 5), (w - 5, h - 5)):
        m.rrect(x - 5, y - 5, x + 5, y + 5, 1.2)
    for x, y in ((w / 2, 5), (w / 2, h - 5), (5, h / 2), (w - 5, h / 2)):
        m.poly([(x, y - 4.2), (x + 4.2, y), (x, y + 4.2), (x - 4.2, y)])
    cm = m.arr()
    ch = blur(cm, S * 0.8) * 1.6
    csh = emboss(ch * S, strength=1.6)
    cc = shade(hexc("C29A42"), csh, PAL["gold_light"], PAL["gold_dark"], 1.0, 1.0)
    col = mix(col, cc, cm)
    m2 = Mask(W, H, S)
    for x, y in ((5, 5), (w - 5, 5), (5, h - 5), (w - 5, h - 5)):
        m2.poly([(x, y - 2.4), (x + 2.4, y), (x, y + 2.4), (x - 2.4, y)])
    for x, y in ((w / 2, 5), (w / 2, h - 5), (5, h / 2), (w - 5, h / 2)):
        m2.circle(x, y, 1.1)
    col = mix(col, PAL["lacquer"], m2.arr())
    g = grain(H, W, 31, 1.0, scale=S)
    col = col * (1 + g[..., None] * 0.04)
    lay = Layer(W, H)
    lay.paint(np.clip(col, 0, 1), inside)
    out = lay.reduced(S)
    # exact transparent hole for the 192x240 portrait at (10, 10)
    out.a[10:250, 10:202] = 0.0
    out.c[10:250, 10:202] = 0.0
    out.a[:10, :] = np.maximum(out.a[:10, :], 0)
    return out


# ----------------------------------------------------------------------------------------------
# Scroll (event dialog backdrop)
# ----------------------------------------------------------------------------------------------

def scroll():
    w, h = 1024, 640
    s = 2
    W, H = w * s, h * s
    lay = Layer(W, H)
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    y = (y + 0.5) / s
    x = (x + 0.5) / s
    rng = np.random.default_rng(41)
    # geometry (output px)
    py0, py1 = 46.0, h - 46.0          # paper/mount vertical extent
    px0, px1 = 56.0, w - 56.0          # mount horizontal extent (meets the rollers)
    rcx_l, rcx_r = 36.0, w - 36.0      # roller centres
    rr = 19.0                          # roller radius
    ry0, ry1 = 24.0, h - 24.0          # roller body extent
    # --- drop shadow (constant along each edge) ---
    sd = rrect_sdf(H, W, (px0 - 6) * s, (py0 + 3) * s, (px1 + 6) * s, (py1 + 7) * s, 6 * s) / s
    shadow = np.exp(-np.maximum(sd, 0) / 5.0) * 0.45 * clamp01(-sd + 12)
    rs = rrect_sdf(H, W, (rcx_l - rr) * s, (ry0 + 4) * s, (rcx_l + rr + 4) * s, (ry1 + 8) * s, rr * s) / s
    rs2 = rrect_sdf(H, W, (rcx_r - rr) * s, (ry0 + 4) * s, (rcx_r + rr + 4) * s, (ry1 + 8) * s, rr * s) / s
    shadow = np.maximum(shadow, np.exp(-np.maximum(np.minimum(rs, rs2), 0) / 4.0) * 0.5 * clamp01(-np.minimum(rs, rs2) + 10))
    lay.paint(hexc("0E0906"), clamp01(shadow))
    # --- mounting silk ---
    mount_m = (clamp01((x - px0) * s + 0.5) * clamp01((px1 - x) * s + 0.5)
               * clamp01((y - py0) * s + 0.5) * clamp01((py1 - y) * s + 0.5))
    silk = hexc("33434A")
    dy = np.minimum(y - py0, py1 - y)
    dx = np.minimum(x - px0, px1 - x)
    silk_tex = fbm(H, W, 3 * s, rng, octaves=2, aniso=(0.3, 6.0)) - 0.5
    silk_col = silk * (1 + silk_tex[..., None] * 0.10)
    # soft fold shading along the outer edges
    silk_col = silk_col * (0.80 + 0.2 * smoothstep(0, 6, np.minimum(dy, dx + 30)))[..., None]
    lay.paint(np.clip(silk_col, 0, 1), mount_m)
    # gold thread lines on the silk
    dmin = np.minimum(dy, dx)
    gl = band(dmin, 5.0, 6.3, 0.6)
    lay.paint(PAL["gold"] * 0.95, gl * mount_m * 0.9)
    # --- paper ---
    qx0, qx1, qy0, qy1 = 74.0, w - 74.0, 66.0, h - 66.0
    pm = (clamp01((x - qx0) * s + 0.5) * clamp01((qx1 - x) * s + 0.5)
          * clamp01((y - qy0) * s + 0.5) * clamp01((qy1 - y) * s + 0.5))
    pdy = np.minimum(y - qy0, qy1 - y)
    pdx = np.minimum(x - qx0, qx1 - x)
    pd = np.minimum(pdx, pdy)
    pcol = np.broadcast_to(PAL["paper"], (H, W, 3)).copy()
    pcol = mix(pcol, PAL["paper_dark"], np.exp(-np.maximum(pd, 0) / 5.0) * 0.75)
    g = paper_grain(H, W, rng, scale=s)
    # texture: stronger within the margins, faint in the centre region
    centre = (x > 80) & (x < w - 80) & (y > 80) & (y < h - 80)
    amp = np.where(centre, 0.012, 0.012 + 0.03 * np.exp(-np.maximum(pd, 0) / 6.0))
    pcol = pcol * (1 + g[..., None] * amp[..., None])
    lay.paint(np.clip(pcol, 0, 1), pm)
    # ink border line on the paper
    lay.paint(PAL["ink_soft"], band(pd, 3.5, 4.6, 0.6) * pm * 0.7)
    lay.paint(PAL["ink"], band(pd, -2, 0.8, 0.6) * pm * 0.6)
    # --- rollers ---
    for cxr, side in ((rcx_l, -1), (rcx_r, 1)):
        u = (x - cxr) / rr                      # -1..1 across the cylinder
        body = clamp01((rr - np.abs(x - cxr)) * s + 0.5) * clamp01((y - ry0) * s + 0.5) * clamp01((ry1 - y) * s + 0.5)
        nz = np.sqrt(clamp01(1 - u ** 2))
        lam = clamp01(0.25 + 0.75 * (nz * 0.75 + (-u) * 0.45))
        wood = mix(hexc("1E0F09"), hexc("6E3A20"), lam)
        spec = np.exp(-((u + 0.45) / 0.12) ** 2) * 0.45
        wood = mix(wood, hexc("E8B890"), spec)
        wtex = fbm(H, W, 12 * s, rng, octaves=3, aniso=(6.0, 0.4)) - 0.5
        wood = wood * (1 + wtex[..., None] * 0.18)
        lay.paint(np.clip(wood, 0, 1), body)
        # gold bands near the ends of the roller (in the corner regions)
        for by in (ry0 + 10, ry1 - 10):
            bm = body * band(np.abs(y - by), -1, 3.0, 0.6)
            gcol = mix(PAL["gold_dark"], PAL["gold_light"], lam)
            lay.paint(gcol, bm)
        # knobs (caps) at both ends
        for ky, kdir in ((ry0, -1), (ry1, 1)):
            kr = rr * 0.72
            kh = 13.0
            k_y0 = ky - kh if kdir < 0 else ky
            k_y1 = ky if kdir < 0 else ky + kh
            kcy = (k_y0 + k_y1) / 2
            ku = (x - cxr) / kr
            kv = (y - kcy) / (kh / 2)
            km = clamp01((1 - np.sqrt(ku ** 2 * 0.98 + (np.maximum(np.abs(kv) - 0.35, 0) / 0.65) ** 2)) * kr * s * 0.5 + 0.5)
            knz = np.sqrt(clamp01(1 - ku ** 2))
            klam = clamp01(0.2 + 0.8 * (knz * 0.7 + (-ku) * 0.5) - 0.25 * kv * kdir * 0)
            kcol = mix(hexc("3A5E4E"), hexc("A9CDB6"), klam)  # jade cap
            kcol = mix(kcol, hexc("F2FFF6"), np.exp(-((ku + 0.4) / 0.15) ** 2) * 0.5)
            lay.paint(np.clip(kcol, 0, 1), km)
            # gold collar between cap and roller
            cm = clamp01((rr * 0.9 - np.abs(x - cxr)) * s + 0.5) * band(np.abs(y - ky), -1, 2.2, 0.6)
            lay.paint(mix(PAL["gold_dark"], PAL["gold_light"], lam), cm)
        # roller shadow onto the silk/paper next to it
        sx = (x - (cxr - side * rr)) * (-side)  # distance from roller edge into the scroll
        shm = np.exp(-np.maximum(sx, 0) / 5.0) * clamp01(sx * s) * clamp01((y - py0) * s) * clamp01((py1 - y) * s)
        lay.multiply(1 - 0.35 * shm)
    return lay.reduced(s)


# ----------------------------------------------------------------------------------------------
# Divider
# ----------------------------------------------------------------------------------------------

def divider():
    w, h = 512, 16
    W, H = w * S, h * S
    cx, cy = w / 2, h / 2
    gold = Mask(W, H, S)
    for sgn in (-1, 1):
        gold.brush([(cx + sgn * 20, cy), (cx + sgn * 120, cy), (cx + sgn * 244, cy)], 2.2, 0.3)
        # short bracket strokes framing the ornament
        gold.brush([(cx + sgn * 22, cy - 3.6), (cx + sgn * 62, cy - 3.6)], 1.0, 0.25)
        gold.brush([(cx + sgn * 22, cy + 3.6), (cx + sgn * 62, cy + 3.6)], 1.0, 0.25)
        gold.circle(cx + sgn * 14.5, cy, 2.5)
        gold.poly([(cx + sgn * 120, cy - 2.6), (cx + sgn * 123.2, cy), (cx + sgn * 120, cy + 2.6),
                   (cx + sgn * 116.8, cy)])
    gold.poly([(cx, cy - 6.6), (cx + 7.4, cy), (cx, cy + 6.6), (cx - 7.4, cy)])
    gm = gold.arr()
    red = Mask(W, H, S)
    red.poly([(cx, cy - 3.0), (cx + 3.3, cy), (cx, cy + 3.0), (cx - 3.3, cy)])
    for sgn in (-1, 1):
        red.circle(cx + sgn * 14.5, cy, 1.0)
    rm = red.arr()
    from artlib_ui import shift
    shadow = blur(shift(gm, S * 0.9, S * 0.6), S * 0.5)
    hgt = blur(gm, S * 0.5)
    sh = emboss(hgt * S * 1.5, strength=1.3)
    lay = Layer(W, H)
    lay.paint(PAL["ink"], clamp01(shadow * 1.2) * 0.7)
    gcol = shade(PAL["gold"], sh, PAL["gold_light"], PAL["gold_dark"], 1.0, 1.0)
    lay.paint(gcol, gm)
    lay.paint(PAL["lacquer"], rm)
    xx = (np.arange(W, dtype=np.float32) + 0.5) / S
    fade = smoothstep(4, 70, np.minimum(xx, w - xx))[None, :]
    lay.c *= fade[..., None]
    lay.a *= fade
    return lay.reduced(S)


def main():
    panel(False).save(P("Panel.png"))
    panel(True).save(P("PanelDark.png"))
    for st, name in (("normal", "Button.png"), ("hover", "Button_Hover.png"),
                     ("pressed", "Button_Pressed.png"), ("disabled", "Button_Disabled.png")):
        lacquer_shape(192, 64, st, 7.0, seed=3).save(P(name))
    tab(False).save(P("Tab.png"))
    tab(True).save(P("Tab_Active.png"))
    portrait_frame().save(P("Frame_Portrait.png"))
    make_seal(128).save(P("Seal.png"))
    scroll().save(P("Scroll.png"))
    divider().save(P("Divider.png"))


if __name__ == "__main__":
    main()
