#!/usr/bin/env python3
"""Iron Reign event illustrations (640x360 painted vignettes) and the duel background (1280x720).

    python3 Tools/ArtGen/ui_events.py [Name ...] [--fast]

Names: Court Battle Harvest Disaster Wanderer Sect Bandits Envoy Festival Plague Flood Omen Duel
Outputs Content/Data/Art/Events/<Name>.png and Content/Data/Art/Duel/Background.png.

All scenes share the ink-wash toolkit in artlib_ui (layered ridges, mist, pines, figures) and
finish with the same paper grain, warm grade and soft vignette so they sit together on the
event scroll.
"""
import math
import os
import sys
import zlib

import numpy as np

from artlib_ui import (ART, PAL, Mask, Painting, arc_pts, bez, blur, clamp01, fbm, figure, flag,
                       hexc, horse, mix, noise1d, pavilion, qbez, roof_poly, shift, smoothstep, stroke_poly)

EV = os.path.join(ART, "Events")
FAST = "--fast" in sys.argv
SS = 1 if FAST else 2


# ----------------------------------------------------------------------------------------------
# Scene helpers
# ----------------------------------------------------------------------------------------------

def new(w=640, h=360, seed=1):
    return Painting(w, h, ss=SS, seed=seed)


def poly_mask(p, pts):
    return p.mask().poly(pts).arr()


def house(p, x, yb, w, h, wall, roof, door=None, rim=None, win=None, roof_h=None, shade=0.35):
    """Chinese house front: plastered wall, dark tiled hip roof with upturned eaves."""
    rh = roof_h or h * 0.75
    wall_poly = [(x - w / 2, yb), (x - w / 2, yb - h), (x + w / 2, yb - h), (x + w / 2, yb)]
    wm = poly_mask(p, wall_poly)
    col = mix(wall, np.asarray(wall) * 0.8, smoothstep(yb - h, yb, p.Y))
    p.paint(col, wm)
    # shadow under the eaves
    sm = wm * smoothstep(yb - h + h * 0.45, yb - h, p.Y)
    p.paint(np.asarray(wall) * 0.45, sm, shade)
    if door is not None:
        dm = poly_mask(p, [(x - w * 0.12, yb), (x - w * 0.12, yb - h * 0.62), (x + w * 0.12, yb - h * 0.62), (x + w * 0.12, yb)])
        p.paint(door, dm)
    if win is not None:
        for sx in (-0.32, 0.32):
            wmm = poly_mask(p, [(x + w * sx - w * 0.08, yb - h * 0.35), (x + w * sx - w * 0.08, yb - h * 0.65),
                                (x + w * sx + w * 0.08, yb - h * 0.65), (x + w * sx + w * 0.08, yb - h * 0.35)])
            p.paint(win, wmm)
    rp = roof_poly(x, yb - h - rh * 0.72, w * 1.3, rh)
    rm = poly_mask(p, rp)
    p.paint(mix(np.asarray(roof) * 1.15, roof, smoothstep(yb - h - rh, yb - h, p.Y)), rm)
    # tile lines
    tl = p.mask()
    n = max(3, int(w / 7))
    for i in range(n + 1):
        tx = x - w * 0.62 + w * 1.24 * i / n
        tl.line([(x + (tx - x) * 0.55, yb - h - rh * 0.72), (tx, yb - h - rh * 0.08)], 0.5)
    p.paint(np.asarray(roof) * 0.6, tl.arr() * rm, 0.6)
    if rim is not None:
        rr = p.mask().line([(q[0], q[1]) for q in rp[:len(rp) // 3]], 1.0).arr()
        p.paint(rim, rr * 0.7)
    return wm, rm


def tree(p, x, yb, h, col, seed=0, spread=1.0, leaf=True, opacity=1.0):
    """Deciduous ink tree: forked trunk with clustered dabs of foliage."""
    rng = np.random.default_rng(seed)
    m = p.mask()
    tips = []

    def branch(x0, y0, ang, L, w, depth):
        x1 = x0 + math.cos(ang) * L
        y1 = y0 + math.sin(ang) * L
        mx = (x0 + x1) / 2 + rng.uniform(-L, L) * 0.12
        my = (y0 + y1) / 2 + rng.uniform(-L, L) * 0.12
        m.brush(qbez((x0, y0), (mx, my), (x1, y1), 8), w, w * 0.6)
        if depth == 0 or L < 4:
            tips.append((x1, y1))
            return
        for _ in range(2 if depth > 1 else int(rng.integers(2, 4))):
            branch(x1, y1, ang + rng.uniform(-0.75, 0.75) * spread, L * rng.uniform(0.55, 0.78), w * 0.62, depth - 1)
    branch(x, yb, -math.pi / 2 + rng.uniform(-0.15, 0.15), h * 0.42, h * 0.07, 4)
    p.paint(col, m.arr(), opacity)
    if leaf:
        lm = p.mask()
        for (tx, ty) in tips:
            for _ in range(5):
                lm.ellipse(tx + rng.uniform(-h, h) * 0.08, ty + rng.uniform(-h, h) * 0.06,
                           h * rng.uniform(0.04, 0.09), h * rng.uniform(0.025, 0.055))
        p.paint(col, lm.arr(), opacity * 0.92)
    return tips


def willow(p, x, yb, h, col, seed=0, opacity=1.0):
    rng = np.random.default_rng(seed)
    m = p.mask()
    m.brush(bez((x, yb), (x - h * 0.05, yb - h * 0.4), (x + h * 0.08, yb - h * 0.6), (x + h * 0.02, yb - h * 0.85), 12), h * 0.07, h * 0.03)
    for _ in range(40):
        sx = x + rng.uniform(-h * 0.35, h * 0.35)
        sy = yb - h * rng.uniform(0.7, 0.95)
        L = h * rng.uniform(0.3, 0.6)
        m.brush(qbez((sx, sy), (sx + rng.uniform(-6, 6), sy + L * 0.5), (sx + rng.uniform(-10, 10), sy + L), 10), 1.0, 0.3)
    p.paint(col, m.arr(), opacity)


def bamboo(p, x, yb, h, w, col, seed=0, lean=0.0, leaves=True, opacity=1.0, leaf_col=None):
    """Ink bamboo stalk with nodes and drooping leaf clusters."""
    rng = np.random.default_rng(seed)
    m = p.mask()
    seg = h / int(rng.integers(6, 9))
    y = yb
    nodes = []
    while y > yb - h:
        y1 = max(yb - h, y - seg * rng.uniform(0.85, 1.1))
        t0 = (yb - y) / h
        t1 = (yb - y1) / h
        x0 = x + lean * h * t0 * t0
        x1 = x + lean * h * t1 * t1
        m.brush([(x0, y - 0.8), (x1, y1 + 0.8)], w * (1 - 0.25 * t0), w * (1 - 0.25 * t1))
        nodes.append((x1, y1, w * (1 - 0.25 * t1)))
        y = y1
    p.paint(col, m.arr(), opacity)
    nm = p.mask()
    for (nx, ny, nw) in nodes[:-1]:
        nm.ellipse(nx, ny, nw * 0.65, max(0.5, nw * 0.12))
    p.paint(np.asarray(col) * 0.5, nm.arr(), opacity)
    if leaves:
        lm = p.mask()
        for (nx, ny, nw) in nodes[len(nodes) // 3:]:
            if rng.random() < 0.65:
                side = rng.choice([-1, 1])
                bx = nx + side * h * rng.uniform(0.05, 0.12)
                by = ny + h * rng.uniform(-0.02, 0.04)
                lm.brush([(nx, ny), (bx, by)], max(0.6, nw * 0.2), 0.4)
                for k in range(int(rng.integers(3, 6))):
                    ang = math.radians(rng.uniform(15, 75) if side > 0 else rng.uniform(105, 165))
                    L = h * rng.uniform(0.06, 0.11)
                    ex, ey = bx + math.cos(ang) * L, by + math.sin(ang) * L * 0.8
                    lm.brush([(bx, by), ((bx + ex) / 2, (by + ey) / 2 - L * 0.08), (ex, ey)], L * 0.16, 0.3)
        p.paint(leaf_col if leaf_col is not None else col, lm.arr(), opacity)


def flames(p, x, yb, w, h, seed=0, glow=True):
    rng = np.random.default_rng(seed)
    for layer, (col, scale) in enumerate(((hexc("B23A1E"), 1.0), (hexc("E8742A"), 0.75), (hexc("F7C55A"), 0.45), (hexc("FFF0C0"), 0.22))):
        m = p.mask()
        n = max(2, int(w / 10))
        for i in range(n):
            fx = x - w / 2 + w * (i + 0.5) / n + rng.uniform(-3, 3)
            fh = h * scale * rng.uniform(0.6, 1.1) * (1 - abs(fx - x) / (w * 0.7))
            fw = w / n * 1.4 * (0.6 + scale * 0.5)
            if fh <= 2:
                continue
            tipx = fx + rng.uniform(-fw, fw) * 0.6
            pts = bez((fx - fw / 2, yb), (fx - fw / 2, yb - fh * 0.5), (tipx - fw * 0.2, yb - fh * 0.75), (tipx, yb - fh), 10) + \
                bez((tipx, yb - fh), (tipx + fw * 0.25, yb - fh * 0.7), (fx + fw / 2, yb - fh * 0.45), (fx + fw / 2, yb), 10)
            m.poly(pts)
        p.paint(col, blur(m.arr(), 0.6 * SS))
    if glow:
        p.glow(x, yb - h * 0.4, max(w, h) * 1.4, hexc("FF9A40"), 0.35, power=1.6)


def smoke(p, x, yb, h, w, col, seed=0, opacity=0.8, drift=0.4):
    rng = np.random.default_rng(seed)
    n = fbm(p.H, p.W, 22 * SS, rng, octaves=5)
    t = clamp01((yb - p.Y) / h)
    cx = x + drift * h * t ** 1.4
    width = w * (0.35 + 1.2 * t)
    m = np.exp(-((p.X - cx) / width) ** 2) * (p.Y < yb) * smoothstep(1.0, 0.6, t)
    m = clamp01(m * (0.4 + 1.3 * (n - 0.3)))
    p.paint(col, m, opacity)


def rain(p, n, col, seed=0, angle=0.25, length=(8, 18), opacity=0.35, width=0.6):
    rng = np.random.default_rng(seed)
    m = p.mask()
    for _ in range(n):
        x = rng.uniform(-40, p.ow + 40)
        y = rng.uniform(-20, p.oh)
        L = rng.uniform(*length)
        m.line([(x, y), (x - angle * L, y + L)], width, round_caps=False)
    p.paint(col, m.arr(), opacity)


def lantern(p, x, y, r, col=None, glow=0.5):
    col = hexc("D0402A") if col is None else col
    m = p.mask().ellipse(x, y, r, r * 1.15).arr()
    d = np.hypot(p.X - x + r * 0.25, p.Y - y + r * 0.3) / r
    p.paint(mix(hexc("FFD27A"), col, smoothstep(0.0, 1.1, d)), m)
    caps = p.mask().rect(x - r * 0.55, y - r * 1.25, x + r * 0.55, y - r * 0.95).rect(x - r * 0.55, y + r * 0.95, x + r * 0.55, y + r * 1.25)
    p.paint(hexc("2A1A12"), caps.arr())
    p.paint(hexc("C8A04A"), p.mask().line([(x, y + r * 1.25), (x, y + r * 1.9)], max(0.6, r * 0.12)).arr())
    if glow:
        p.glow(x, y, r * 6, hexc("FFB050"), glow, power=1.5)


def stars(p, n, y_max, seed=0, col=None):
    rng = np.random.default_rng(seed)
    m = p.mask()
    for _ in range(n):
        x, y = rng.uniform(0, p.ow), rng.uniform(0, y_max) ** 1.0
        r = rng.choice([0.4, 0.5, 0.6, 0.9], p=[0.4, 0.3, 0.2, 0.1])
        m.circle(x, y, r)
    p.paint(col if col is not None else hexc("F2E8D0"), m.arr(), 0.8)


def crowd(p, x0, x1, yb, h, col, seed=0, density=0.25, hats=("topknot", "straw", "guan"), poses=("stand", "walk"),
          weapons=(None,), opacity=1.0, jitter=3.0):
    rng = np.random.default_rng(seed)
    m = p.mask()
    x = x0
    while x < x1:
        hh = h * rng.uniform(0.85, 1.1)
        figure(m, x, yb + rng.uniform(-jitter, jitter), hh, pose=rng.choice(poses), hat=rng.choice(hats),
               weapon=rng.choice(weapons), facing=rng.choice([-1, 1]))
        x += rng.exponential(1.0 / density) + h * 0.12
    p.paint(col, m.arr(), opacity)


def finish(p, name, vign=0.45, grain=0.05, sat=0.95, tint=None, dither=11):
    p.paper(strength=grain, seed=zlib.crc32(name.encode()) % 1000)
    # low-frequency wash unevenness, like pigment pooling on paper
    rng = np.random.default_rng(zlib.crc32(name.encode()) % 997)
    wash = fbm(p.H, p.W, 90 * SS, rng, octaves=3) - 0.5
    p.multiply(1 + wash * 0.07)
    p.vignette(vign, color=(0.10, 0.07, 0.05), inner=0.5)
    p.grade(sat=sat, tint=tint)
    p.save(os.path.join(EV, name + ".png"), dither_seed=dither)




def people(p, specs, col, rim=None, rim_dx=-1.0, rim_op=0.8, grad=0.25):
    """Paint figures one by one: body colour with a slight top-lit gradient and an optional rim
    light on the side facing the light (rim_dx < 0: light from the left)."""
    for sp in specs:
        sp = dict(sp)
        c = np.asarray(sp.pop("col", col), np.float32)
        m = p.mask()
        figure(m, **sp)
        fm = m.arr()
        top = sp["yf"] - sp["h"]
        cc = mix(np.clip(c * (1 + grad), 0, 1), c, smoothstep(top, sp["yf"], p.Y))
        p.paint(cc, fm)
        if rim is not None:
            edge = clamp01(fm - shift(fm, 0, -rim_dx * 1.3 * SS))
            p.paint(rim, edge, rim_op)


def rider(m, x, yf, h, facing=1, gallop=True, weapon="spear", hat="helmet", banner=False):
    horse(m, x, yf, h, facing=facing, gallop=gallop)
    sx = x + facing * h * 0.05
    sy = yf - h * 0.6
    figure(m, sx, sy + h * 0.32, h * 0.72, pose="stand", hat=hat, weapon=weapon, facing=facing)
    return m


def comet(p, hx, hy, tx, ty, width, seed=0):
    rng = np.random.default_rng(seed)
    L = math.hypot(tx - hx, ty - hy)
    ux, uy = (tx - hx) / L, (ty - hy) / L
    # coordinates along / across the tail
    a = (p.X - hx) * ux + (p.Y - hy) * uy
    c = -(p.X - hx) * uy + (p.Y - hy) * ux
    t = clamp01(a / L)
    wdt = width * (0.15 + 1.0 * t ** 0.7)
    streak = fbm(p.H, p.W, 6 * SS, rng, octaves=2, aniso=(1, 1)) - 0.5
    m = np.exp(-(c / np.maximum(wdt, 0.5)) ** 2) * (a > -4) * (1 - t) ** 1.2 * (1 + streak * 0.6)
    p.add_light(hexc("F8E6C0"), clamp01(m) * 0.85)
    p.glow(hx, hy, width * 3, hexc("FFF4DA"), 0.9, power=1.3)
    p.disc(hx, hy, width * 0.35, hexc("FFFFF4"), 1.0, soft=1.5)


def waves(p, y0, y1, col, crest, seed=0, rows=7, amp=7.0, opacity=1.0):
    """Classical curling wave bands between y0 and y1."""
    rng = np.random.default_rng(seed)
    for k in range(rows):
        t = k / max(1, rows - 1)
        yb = y0 + (y1 - y0) * t
        a = amp * (0.6 + 0.8 * t)
        wl = 60 + 50 * t
        ph = rng.uniform(0, 6.28)
        xs = np.linspace(-20, p.ow + 20, 160)
        top = [(x, yb - a * (0.5 + 0.5 * math.sin(x / wl * 6.28 + ph)) - a * 0.4 * math.sin(x / (wl * 0.37) + ph * 2)) for x in xs]
        body = top + [(p.ow + 20, p.oh + 10), (-20, p.oh + 10)]
        m = poly_mask(p, body)
        p.paint(mix(col, np.asarray(col) * 0.7, smoothstep(yb - a, yb + 40, p.Y)), m, opacity)
        cm = p.mask()
        cm.line(top, 1.2 + t * 1.2, round_caps=False)
        for x in xs[::14]:
            i = int((x + 20) / (p.ow + 40) * 159)
            cx, cy = top[i]
            cm.line(arc_pts(cx + 4, cy + 4, 4 + 3 * t, 4 + 3 * t, 200, 330, 8), 0.9 + t * 0.8)
        p.paint(crest, cm.arr(), 0.85 * opacity)


def dragon(p, x0, x1, ybase, amp, col, gold, seed=0):
    """Festival dragon dance: a sinuous scaled body on poles with a horned head."""
    xs = np.linspace(x0, x1, 80)
    pts = [(x, ybase - amp * math.sin((x - x0) / (x1 - x0) * 2.4 * math.pi)) for x in xs]
    body = stroke_poly(pts, 10, 16)
    bm = poly_mask(p, body)
    p.paint(col, bm)
    sc = p.mask()
    for i in range(2, 78, 3):
        cx, cy = pts[i]
        sc.line(arc_pts(cx, cy - 2, 4, 3, 20, 160, 8), 0.9)
    p.paint(gold, sc.arr() * bm, 0.8)
    p.paint(gold, p.mask().line(pts, 1.4).arr(), 0.9)
    hx, hy = pts[-1]
    head = [(hx - 4, hy - 9), (hx + 12, hy - 12), (hx + 22, hy - 4), (hx + 20, hy + 4), (hx + 8, hy + 9), (hx - 4, hy + 8)]
    p.paint(col, poly_mask(p, head))
    p.paint(gold, p.mask().brush([(hx + 2, hy - 9), (hx - 6, hy - 22)], 2.2, 0.6).brush([(hx + 8, hy - 11), (hx + 4, hy - 24)], 2.2, 0.6).arr())
    p.paint(gold, p.mask().circle(hx + 12, hy - 3, 2).arr())
    poles = p.mask()
    for i in range(6, 80, 13):
        cx, cy = pts[i]
        poles.line([(cx, cy + 6), (cx, ybase + amp + 26)], 1.2, round_caps=False)
    p.paint(hexc("2A1A12"), poles.arr())
    return pts


# ----------------------------------------------------------------------------------------------
# Scenes
# ----------------------------------------------------------------------------------------------

def ev_Court():
    p = new(seed=1)
    p.vgradient([(0, hexc("2A0E0A")), (0.45, hexc("5A1A12")), (0.72, hexc("4A140E")), (1, hexc("1E0F0A"))])
    # polished floor
    p.paint(mix(hexc("3E2016"), hexc("1A0E0A"), smoothstep(280, 360, p.Y)), smoothstep(276, 280, p.Y))
    p.paint(hexc("C9A24A"), p.mask().line([(0, 278), (640, 278)], 1.0).arr(), 0.5)
    # golden screen with five panels and a faint ink landscape
    sx0, sx1, sy0, sy1 = 196, 444, 52, 214
    scr = poly_mask(p, [(sx0, sy1), (sx0, sy0), (sx1, sy0), (sx1, sy1)])
    gold = mix(hexc("E6C26A"), hexc("B8893A"), smoothstep(sy0, sy1, p.Y))
    gold = gold * (1 + (fbm(p.H, p.W, 14 * SS, p.rng, octaves=3) - 0.5)[..., None] * 0.18)
    p.paint(gold, scr)
    r = p.ridge(190, [(230, 75, 40, "karst"), (290, 100, 30, "karst"), (380, 62, 40, "karst"), (425, 84, 30, "karst")],
                rough=5, rough_cell=20, seed=3)
    mt = clamp01((p.Y - r[None, :]) * SS + 0.5) * scr * (1 - smoothstep(150, 214, p.Y))
    p.paint(hexc("6A5030"), mt, 0.45)
    pm = p.mask()
    for i in range(1, 5):
        xx = sx0 + (sx1 - sx0) * i / 5
        pm.line([(xx, sy0), (xx, sy1)], 1.2, round_caps=False)
    pm.d.rectangle([sx0 * SS, sy0 * SS, sx1 * SS, sy1 * SS], outline=255, width=int(3 * SS))
    p.paint(hexc("3A1A0C"), pm.arr())
    # ceiling beam with gold lozenges
    p.paint(hexc("1A0C08"), poly_mask(p, [(0, 0), (640, 0), (640, 26), (0, 26)]))
    p.paint(hexc("B8913F"), p.mask().line([(0, 24), (640, 24)], 1.4).arr(), 0.9)
    for x in range(20, 640, 40):
        p.paint(hexc("8A6A2A"), p.mask().poly([(x, 8), (x + 8, 14), (x, 20), (x - 8, 14)]).arr(), 0.8)
    # dais steps
    for k, (w, yy) in enumerate(((300, 214), (360, 230), (420, 246), (480, 262))):
        p.paint(mix(hexc("6A2418"), hexc("3A120C"), k / 3.0), poly_mask(p, [(320 - w / 2, yy), (320 + w / 2, yy), (320 + w / 2 + 6, yy + 16), (320 - w / 2 - 6, yy + 16)]))
        p.paint(hexc("C9A24A"), p.mask().line([(320 - w / 2, yy), (320 + w / 2, yy)], 1.0).arr(), 0.8)
    # throne: lacquer chair with gold frame
    p.paint(hexc("3A140C"), poly_mask(p, [(282, 214), (284, 160), (292, 150), (348, 150), (356, 160), (358, 214)]))
    p.paint(hexc("C9A24A"), p.mask().line([(284, 212), (284, 160), (292, 151), (348, 151), (356, 160), (356, 212)], 2.0).arr())
    p.paint(hexc("C9A24A"), p.mask().circle(292, 150, 3).circle(348, 150, 3).arr())
    # the ruler, seated, in an ochre robe
    ru = p.mask()
    ru.poly([(296, 214), (298, 192), (306, 176), (334, 176), (342, 192), (344, 214)])
    ru.ellipse(300, 196, 8, 12).ellipse(340, 196, 8, 12)
    robe = ru.arr()
    p.paint(mix(hexc("D8A84A"), hexc("8A5A1E"), smoothstep(176, 214, p.Y)), robe)
    p.paint(hexc("2A1A10"), p.mask().line([(320, 180), (320, 214)], 1.0).line([(306, 200), (334, 200)], 0.8).arr(), 0.6)
    p.paint(hexc("6A2418"), p.mask().poly([(312, 176), (328, 176), (320, 190)]).arr())
    hd = p.mask().ellipse(320, 166, 8, 9.5).arr()
    p.paint(hexc("C89A72"), hd)
    p.paint(hexc("1A120C"), p.mask().poly([(312, 166), (328, 166), (326, 176), (320, 179), (314, 176)]).arr(), 0.85)
    p.paint(hexc("1A120C"), p.mask().rect(312, 152, 328, 160).arr())
    p.paint(hexc("C9A24A"), p.mask().rect(304, 149, 336, 153).arr())
    for xx in range(306, 336, 4):
        p.paint(hexc("E8C870"), p.mask().line([(xx, 153), (xx, 160)], 0.6).arr(), 0.8)
    # red pillars with gold capitals
    for px in (70, 570):
        pmk = poly_mask(p, [(px - 22, 360), (px - 22, 26), (px + 22, 26), (px + 22, 360)])
        u = (p.X - px) / 22.0
        lam = clamp01(0.35 + 0.65 * (np.sqrt(clamp01(1 - u ** 2)) * 0.8 - u * 0.35))
        p.paint(mix(hexc("3A0C08"), hexc("B8382A"), lam), pmk)
        cap = poly_mask(p, [(px - 26, 46), (px - 26, 26), (px + 26, 26), (px + 26, 46)])
        p.paint(mix(hexc("7A5A20"), hexc("E8C870"), lam), cap)
        p.paint(hexc("1A0C08"), p.mask().line([(px - 26, 46), (px + 26, 46)], 1.2).arr())
        base = poly_mask(p, [(px - 28, 360), (px - 28, 344), (px + 28, 344), (px + 28, 360)])
        p.paint(mix(hexc("2A1A10"), hexc("8A6A3A"), lam), base)
    # officials in two lines, holding tablets, facing the throne
    specs = []
    cols = [hexc("5A1C16"), hexc("1E3A36"), hexc("2A2A44")]
    for k, (x, y, h) in enumerate(((128, 356, 92), (176, 330, 74), (214, 312, 62), (244, 298, 52))):
        specs.append(dict(x=x, yf=y, h=h, pose="salute", hat="guan", robe=True, facing=1, col=cols[k % 3]))
        specs.append(dict(x=640 - x, yf=y, h=h, pose="salute", hat="guan", robe=True, facing=-1, col=cols[(k + 1) % 3]))
    specs.sort(key=lambda d: d["yf"])
    people(p, specs, cols[0], rim=hexc("E8B060"), rim_dx=0, rim_op=0.0, grad=0.35)
    for sp in specs:  # rim light from the throne side
        m = p.mask()
        figure(m, **{k: v for k, v in sp.items() if k != "col"})
        fm = m.arr()
        edge = clamp01(fm - shift(fm, 0, -sp["facing"] * 1.2 * SS))
        p.paint(hexc("F0C070"), edge, 0.75)
    p.glow(320, 150, 260, hexc("FFB860"), 0.22, power=1.5)
    for x in (150, 490):
        p.paint(hexc("C9A24A"), p.mask().line([(x, 26), (x, 60)], 0.8).arr())
        lantern(p, x, 74, 11, glow=0.35)
    finish(p, "Court", vign=0.5)


def ev_Battle():
    p = new(seed=2)
    p.vgradient([(0, hexc("3A2422")), (0.35, hexc("8A4A34")), (0.55, hexc("D98A52")), (0.7, hexc("E0A06A")), (1, hexc("7A5A44"))])
    p.disc(470, 150, 34, hexc("F2B070"), 0.75, soft=3)
    p.glow(470, 150, 220, hexc("FFB070"), 0.35)
    mist = hexc("D9A47A")
    r1 = p.ridge(205, [(80, 70, 90, "karst"), (190, 50, 70, "karst"), (430, 90, 60, "karst"), (560, 60, 80, "karst")], rough=8, rough_cell=40, seed=5)
    p.mountain(r1, hexc("6A4038"), mist, fade=70, texture=0.3, edge=0.3, edge_w=1.2, seed=6, folds=2, fold_depth=(10, 50), mist_col=mist, mist_from=(190, 230))
    p.mist(225, 40, mist, 0.8, seed=7, cell=90)
    for (x, y, w) in ((140, 250, 140), (420, 245, 170), (300, 262, 220)):
        smoke(p, x, y + 30, 130, w * 0.45, hexc("B88A66"), seed=int(x), opacity=0.55, drift=0.1)
    # distant armies: forests of spears and banners
    rng = np.random.default_rng(9)
    m = p.mask()
    ban = p.mask()
    ban2 = p.mask()
    for x in np.arange(10, 640, 4.2):
        h = rng.uniform(26, 40)
        yb = 262 + rng.uniform(-3, 3)
        m.line([(x, yb), (x + rng.uniform(-3, 3), yb - h)], 0.7, round_caps=False)
        m.ellipse(x, yb - 6, 2.2, 6)
        if rng.random() < 0.06:
            flag(ban if x < 320 else ban2, x, yb - h - 12, 14, 9, wave=0.3, facing=1 if x < 320 else -1, phase=x)
            m.line([(x, yb), (x, yb - h - 12)], 0.9, round_caps=False)
    p.paint(hexc("3A2620"), m.arr(), 0.9)
    p.paint(hexc("A82A26"), ban.arr(), 0.9)
    p.paint(hexc("2F4A7A"), ban2.arr(), 0.9)
    g = p.ridge(275, [(320, 10, 400)], rough=4, rough_cell=50, seed=10)
    p.mountain(g, hexc("4A3026"), hexc("8A6248"), fade=80, texture=0.4, edge=0.4, seed=11)
    smoke(p, 330, 330, 120, 90, hexc("A07A5A"), seed=12, opacity=0.45, drift=0.0)
    # charging cavalry (left) against spear infantry (right)
    cav = p.mask()
    for (x, y, h) in ((40, 318, 40), (230, 316, 38), (170, 330, 50), (92, 340, 60)):
        rider(cav, x, y, h, facing=1, gallop=True)
    p.paint(hexc("1E1412"), cav.arr())
    specs = []
    for (x, y, h, wp) in ((395, 318, 44, "spear"), (450, 326, 52, "sword_up"), (610, 330, 58, "spear"), (500, 336, 64, "spear"), (560, 346, 74, "sword_up")):
        specs.append(dict(x=x, yf=y, h=h, pose="run", hat="helmet", weapon=wp, facing=-1, col=hexc("1E1412")))
    people(p, specs, hexc("1E1412"), rim=hexc("F0A060"), rim_dx=1, rim_op=0.5, grad=0.1)
    fl = p.mask()
    p.paint(hexc("1E1412"), p.mask().line([(108, 330), (100, 230)], 1.6).line([(548, 346), (552, 244)], 1.6).arr())
    p.paint(hexc("B3282D"), poly_mask(p, flag(Mask(1, 1), 100, 232, 40, 22, wave=0.3, facing=-1, phase=1.0)))
    p.paint(hexc("2F5A9A"), poly_mask(p, flag(Mask(1, 1), 552, 246, 34, 20, wave=0.3, facing=1, phase=2.0)))
    am = p.mask()
    for _ in range(22):
        x = rng.uniform(170, 520)
        y = rng.uniform(70, 170)
        am.brush([(x, y), (x + 16, y + 6)], 0.9, 0.3)
    p.paint(hexc("2A1A16"), am.arr(), 0.7)
    p.haze(300, 360, hexc("3A2018"), 0.25)
    finish(p, "Battle", vign=0.5)


def ev_Harvest():
    p = new(seed=3)
    p.vgradient([(0, hexc("C9C2A8")), (0.5, hexc("EADBB4")), (1, hexc("E8D2A0"))])
    p.glow(120, 40, 300, hexc("FFF0C0"), 0.4)
    mist = hexc("EAD9B0")
    r1 = p.ridge(150, [(420, 70, 80, "karst"), (520, 95, 60, "karst"), (600, 60, 60, "karst"), (300, 40, 80, "round")], rough=6, rough_cell=40, seed=31)
    p.mountain(r1, hexc("7C8A8C"), mist, fade=70, texture=0.25, edge=0.3, edge_w=1.2, seed=32, folds=2, fold_depth=(10, 50), mist_col=mist, mist_from=(140, 180))
    p.mist(170, 30, mist, 0.8, seed=33, cell=80)
    for k in range(9):
        y0 = 180 + k * 21
        rr = p.ridge(y0, [(160 + k * 10, 14 + k * 1.5, 280, "round"), (520 - k * 12, 10, 200, "round")], rough=3, rough_cell=60, seed=40 + k, smooth=10)
        gold = mix(hexc("D6A63C"), hexc("E7C060"), 0.5 + 0.5 * math.sin(k * 1.3))
        p.mountain(rr, hexc("6A7A38") if k % 3 == 0 else hexc("8A6A28"), gold, fade=10, texture=0.35, edge=0.7, edge_w=1.0, seed=50 + k, lit=0.05)
        tm = p.mask()
        rng = np.random.default_rng(60 + k)
        for _ in range(140):
            x = rng.uniform(0, 640)
            yb = rr[min(p.W - 1, int(x * SS))] + rng.uniform(4, 18)
            tm.line([(x, yb), (x + rng.uniform(-1.5, 1.5), yb - 4)], 0.5, round_caps=False)
        p.paint(hexc("8A5A1A"), tm.arr(), 0.35)
    house(p, 92, 200, 70, 30, hexc("E6D8B8"), hexc("8A6A3A"), door=hexc("3A2A1A"), roof_h=24)
    willow(p, 150, 210, 90, hexc("4A5A30"), seed=3, opacity=0.85)
    sm = p.mask()
    sheaves = ((380, 278), (410, 284), (440, 276), (470, 286))
    for (x, y) in sheaves:
        sm.poly([(x - 8, y), (x - 2, y - 22), (x + 2, y - 22), (x + 8, y)])
        sm.ellipse(x, y - 22, 5, 3)
    p.paint(mix(hexc("E0B048"), hexc("A87A26"), smoothstep(255, 285, p.Y)), sm.arr())
    for (x, y) in sheaves:
        p.paint(hexc("7A4A1A"), p.mask().line([(x - 5, y - 9), (x + 5, y - 9)], 1.2).arr(), 0.8)
    specs = [dict(x=250, yf=322, h=62, pose="bow", hat="straw", weapon=None, facing=1, col=hexc("3A4A5A")),
             dict(x=318, yf=302, h=50, pose="bow", hat="straw", facing=-1, col=hexc("4A3A2A")),
             dict(x=545, yf=334, h=70, pose="walk", hat="straw", weapon="pole", facing=-1, col=hexc("2E3A4A"))]
    people(p, specs, hexc("2E2418"), rim=hexc("FFE8B0"), rim_dx=-1, rim_op=0.6)
    # sickles
    p.paint(hexc("2A2018"), p.mask().line(arc_pts(270, 300, 6, 6, 200, 340, 8), 1.2).line(arc_pts(332, 286, 5, 5, -160, -20, 8), 1.0).arr())
    rng = np.random.default_rng(70)
    fg = p.mask()
    for _ in range(220):
        x = rng.uniform(0, 640)
        h = rng.uniform(20, 46)
        fg.brush([(x, 360), (x + rng.uniform(-4, 4), 360 - h * 0.6), (x + rng.uniform(-8, 8), 360 - h)], 1.4, 0.3)
    p.paint(hexc("A87A2A"), fg.arr(), 0.8)
    hd = p.mask()
    for _ in range(90):
        hd.ellipse(rng.uniform(0, 640), rng.uniform(318, 345), 1.6, 4.0)
    p.paint(hexc("E2B850"), hd.arr(), 0.8)
    bm = p.mask()
    for (bx, by, bs) in ((330, 70, 6), (350, 62, 5), (366, 74, 4)):
        bm.brush([(bx - bs, by - bs * 0.3), (bx, by)], bs * 0.25, 0.3).brush([(bx, by), (bx + bs, by - bs * 0.4)], bs * 0.25, 0.3)
    p.paint(hexc("4A4038"), bm.arr())
    p.add_light(hexc("FFE0A0"), smoothstep(360, 0, p.Y) * 0.12)
    finish(p, "Harvest", vign=0.4, sat=1.0)


def ev_Disaster():
    p = new(seed=4)
    p.vgradient([(0, hexc("140C0C")), (0.5, hexc("4A1A12")), (0.75, hexc("9A3A1A")), (1, hexc("2A140E"))])
    rng = np.random.default_rng(41)
    for (x, w, h) in ((160, 60, 70), (300, 100, 120), (470, 80, 90), (560, 50, 60)):
        smoke(p, x, 210, 230, w * 0.55, hexc("4A3028"), seed=x, opacity=0.9, drift=0.5)
    for (x, w, h, rh) in ((60, 90, 40, 30), (170, 70, 34, 26), (280, 110, 50, 36), (400, 80, 36, 28), (520, 120, 46, 34), (620, 60, 30, 24)):
        house(p, x, 260, w, h, hexc("2A1A14"), hexc("120C0A"), roof_h=rh, shade=0.2)
    pv = p.mask()
    pavilion(pv, 300, 212, 60, tiers=2)
    p.paint(hexc("120C0A"), pv.arr())
    # broken beams
    p.paint(hexc("120C0A"), p.mask().brush([(440, 262), (470, 226)], 3, 2).brush([(150, 262), (126, 232)], 3, 2).arr())
    for (x, w, h) in ((160, 60, 50), (300, 110, 90), (470, 90, 70), (560, 50, 40), (60, 50, 30)):
        flames(p, x, 262, w, h, seed=x)
    em = p.mask()
    for _ in range(140):
        em.circle(rng.uniform(80, 600), rng.uniform(30, 250), rng.uniform(0.4, 1.1))
    p.paint(hexc("FFC060"), em.arr(), 0.8)
    p.paint(hexc("1A100C"), smoothstep(258, 266, p.Y))
    p.paint(hexc("C85A2A"), smoothstep(300, 262, p.Y) * smoothstep(258, 270, p.Y), 0.35)
    # cracks in the ground
    cm = p.mask()
    for (x0, y0) in ((220, 300), (420, 320)):
        pts = [(x0, y0)]
        for k in range(8):
            pts.append((pts[-1][0] + rng.uniform(8, 18), pts[-1][1] + rng.uniform(-6, 6)))
        cm.brush(pts, 2.0, 0.4)
    p.paint(hexc("E06A2A"), cm.arr(), 0.7)
    specs = []
    for (x, y, h, f) in ((90, 342, 62, -1), (132, 330, 48, -1), (205, 350, 70, -1), (560, 344, 60, 1), (602, 332, 46, 1), (246, 322, 38, -1)):
        specs.append(dict(x=x, yf=y, h=h, pose="run", hat=["topknot", "straw"][int(x) % 2], facing=f, col=hexc("0E0A08")))
    people(p, specs, hexc("0E0A08"), rim=hexc("FF8A3A"), rim_dx=-1, rim_op=0.6, grad=0.0)
    finish(p, "Disaster", vign=0.45, sat=1.0)


def ev_Wanderer():
    p = new(seed=5)
    p.vgradient([(0, hexc("8C9196")), (0.5, hexc("D8D2C2")), (1, hexc("CFC6B0"))])
    p.disc(150, 80, 24, hexc("F4EEDC"), 0.9, soft=2)
    mist = hexc("E2DCCB")
    r1 = p.ridge(220, [(80, 160, 60, "karst"), (190, 120, 50, "karst"), (330, 200, 60, "karst"), (470, 140, 55, "karst")], rough=8, rough_cell=30, seed=51)
    p.mountain(r1, hexc("6E7478"), mist, fade=120, texture=0.35, edge=0.35, edge_w=1.2, seed=52, folds=3, fold_depth=(15, 90), mist_col=mist, mist_from=(170, 240))
    # waterfall: a ribbon falling from a cleft, dissolving into mist
    wx = np.interp(p.Y, [60, 120, 230], [312, 314, 317])
    wfw = np.interp(p.Y, [60, 230], [2.0, 5.5])
    wf = clamp01((wfw - np.abs(p.X - wx)) * SS * 0.7) * smoothstep(58, 70, p.Y)
    p.paint(hexc("F6F2E8"), wf, 0.8)
    p.mist(240, 60, mist, 0.9, seed=53, cell=90)
    r2 = p.ridge(300, [(80, 60, 160, "round"), (300, 20, 150, "round")], rough=6, rough_cell=40, seed=54)
    p.mountain(r2, hexc("4A4E50"), hexc("B8B4A6"), fade=80, texture=0.35, edge=0.4, seed=55, folds=2, fold_depth=(10, 40), mist_col=mist, mist_from=(300, 360))
    r3 = p.ridge(380, [(520, 140, 200, "dome"), (660, 170, 120, "dome")], rough=8, rough_cell=30, seed=56, smooth=10)
    p.mountain(r3, hexc("26282A"), hexc("6A6A64"), fade=120, texture=0.5, edge=0.6, edge_w=2.0, seed=57, folds=3, fold_depth=(15, 80))
    pm = p.mask()
    p.pine(pm, 600, 252, 150, lean=-0.35, seed=12, pads=5, spread=1.1)
    p.paint(hexc("1C1C1C"), pm.arr())
    yb = r3[int(462 * SS)] + 2
    m = p.mask()
    figure(m, 462, yb, 56, pose="walk", hat="straw", weapon="staff", facing=-1, cloak=True)
    m.brush([(468, yb - 46), (484, yb - 62)], 2.2, 1.4)
    p.paint(hexc("1A1A1A"), m.arr())
    bm = p.mask()
    for (bx, by, bs) in ((230, 120, 7), (250, 112, 5)):
        bm.brush([(bx - bs, by - bs * 0.3), (bx, by)], bs * 0.25, 0.4)
        bm.brush([(bx, by), (bx + bs, by - bs * 0.4)], bs * 0.25, 0.4)
    p.paint(hexc("3A3A3A"), bm.arr())
    finish(p, "Wanderer", vign=0.4, sat=0.9, tint=(1.02, 1.0, 0.97))


def ev_Sect():
    p = new(seed=6)
    p.vgradient([(0, hexc("B8B4A4")), (0.45, hexc("EDE0BE")), (1, hexc("D9CBA6"))])
    p.glow(520, 70, 220, hexc("FFF0C8"), 0.4)
    mist = hexc("EEE2C4")
    r1 = p.ridge(200, [(60, 110, 60, "karst"), (560, 120, 70, "karst"), (620, 90, 40, "karst")], rough=6, rough_cell=30, seed=61)
    p.mountain(r1, hexc("8A8C88"), mist, fade=90, texture=0.3, edge=0.3, seed=62, folds=2, fold_depth=(10, 60), mist_col=mist, mist_from=(150, 220))
    p.mist(230, 70, mist, 0.9, seed=63, cell=80)
    r2 = p.ridge(400, [(300, 300, 110, "karst"), (400, 220, 90, "karst"), (200, 160, 90, "karst")], rough=8, rough_cell=30, seed=64, smooth=12)
    p.mountain(r2, hexc("3A3A36"), hexc("A8A08A"), fade=180, texture=0.5, edge=0.55, edge_w=1.8, seed=65, folds=4, fold_depth=(15, 150), mist_col=mist, mist_from=(260, 360))
    tm = p.mask()
    top = r2[int(300 * SS)]
    pavilion(tm, 300, top + 4, 50, tiers=3)
    for x, w in ((350, 40), (254, 36)):
        pavilion(tm, x, r2[int(x * SS)] + 3, w, tiers=1)
    p.paint(hexc("2A2420"), tm.arr())
    for (x, w) in ((350, 28), (254, 26)):
        yy = r2[int(x * SS)] + 3
        p.paint(hexc("8A2A1E"), poly_mask(p, [(x - w / 2, yy), (x - w / 2, yy - 9), (x + w / 2, yy - 9), (x + w / 2, yy)]), 0.9)
    # pine trees clinging to the cliff
    pm = p.mask()
    for (x, h, ln, sd) in ((236, 40, -0.4, 31), (372, 34, 0.4, 32), (330, 30, 0.3, 33)):
        p.pine(pm, x, r2[int(x * SS)] + 14, h, lean=ln, seed=sd, pads=3)
    p.paint(hexc("2A2A26"), pm.arr())
    p.mist(300, 50, mist, 0.75, seed=66, cell=70)
    # stone courtyard in the foreground with monks training
    ct = smoothstep(318, 324, p.Y)
    p.paint(mix(hexc("8C8470"), hexc("5A5446"), smoothstep(320, 360, p.Y)), ct)
    p.paint(hexc("3A3428"), p.mask().line([(0, 321), (640, 321)], 1.0).arr(), 0.7)
    tl = p.mask()
    for x in range(-200, 840, 46):
        tl.line([(320 + (x - 320) * 0.55, 322), (x, 360)], 0.6)
    p.paint(hexc("4A4436"), tl.arr() * ct, 0.5)
    specs = []
    for k, x in enumerate((96, 156, 446, 506, 566)):
        f = 1 if x < 320 else -1
        specs.append(dict(x=x, yf=354 - (k % 2) * 6, h=46 + (k % 2) * 4, pose="stance", hat="topknot", facing=f,
                          col=hexc("8A4A1E") if k % 2 else hexc("6A3A1A")))
    people(p, specs, hexc("6A3A1A"), rim=hexc("FFE0A0"), rim_dx=-1, rim_op=0.5, grad=0.3)
    bm = p.mask()
    for (bx, by, bs) in ((470, 120, 10), (500, 104, 8), (440, 132, 6)):
        bm.brush([(bx - bs, by - bs * 0.5), (bx, by)], bs * 0.22, 0.4)
        bm.brush([(bx, by), (bx + bs, by - bs * 0.6)], bs * 0.22, 0.4)
        bm.brush([(bx, by), (bx + bs * 0.7, by + bs * 0.15)], bs * 0.1, 0.3)
    p.paint(hexc("2A2A28"), bm.arr())
    pm = p.mask()
    p.pine(pm, 30, 330, 140, lean=0.3, seed=21, pads=5)
    p.paint(hexc("1E1E1A"), pm.arr())
    finish(p, "Sect", vign=0.4, sat=0.95)


def ev_Bandits():
    p = new(seed=7)
    p.vgradient([(0, hexc("0E1420")), (0.5, hexc("223048")), (1, hexc("141A24"))])
    p.disc(470, 70, 26, hexc("E8EEF0"), 0.95, soft=2)
    p.glow(470, 70, 150, hexc("9AB0D0"), 0.35)
    stars(p, 70, 160, seed=7)
    mist = hexc("3A4A62")
    r1 = p.ridge(200, [(120, 50, 140, "round"), (500, 40, 160, "round")], rough=8, rough_cell=40, seed=71)
    p.mountain(r1, hexc("1A2232"), mist, fade=80, texture=0.3, edge=0.3, seed=72)
    p.mist(215, 40, hexc("4A5A74"), 0.6, seed=73, cell=80)
    # moonlit road winding into the forest
    road = poly_mask(p, [(250, 360), (420, 360), (350, 280), (330, 240), (318, 220), (308, 220), (300, 240), (270, 290)])
    p.paint(mix(hexc("5A6478"), hexc("8A90A0"), smoothstep(360, 220, p.Y)), road, 0.85)
    for (x, h, sd) in ((40, 300, 1), (120, 240, 2), (180, 190, 3), (230, 150, 4), (470, 170, 5), (530, 230, 6), (610, 310, 7), (400, 130, 8)):
        tree(p, x, 360 if h > 200 else 250 + (300 - h) * 0.2, h, hexc("0A0C12"), seed=sd, spread=1.1)
    # torch light
    tx, ty = 230, 248
    p.glow(tx, ty, 160, hexc("FF9A40"), 0.55, power=1.4)
    flames(p, tx, ty, 10, 18, seed=3, glow=False)
    specs = [dict(x=222, yf=336, h=76, pose="stance", hat="hood", weapon=None, facing=1, cloak=True),
             dict(x=300, yf=346, h=84, pose="stance", hat="topknot", weapon="sword_up", facing=1),
             dict(x=400, yf=340, h=80, pose="walk", hat="hood", weapon="sword", facing=-1),
             dict(x=470, yf=330, h=66, pose="stance", hat="straw", weapon="spear", facing=-1)]
    people(p, specs, hexc("0E0C0C"), rim=hexc("FFA050"), rim_dx=-1, rim_op=0.85, grad=0.0)
    p.paint(hexc("2A1A10"), p.mask().line([(230, 300), (230, 250)], 2.0).arr())
    # an overturned cart
    cm = p.mask()
    cm.poly([(520, 352), (600, 340), (604, 316), (526, 326)])
    cm.circle(530, 350, 10)
    p.paint(hexc("1A1410"), cm.arr())
    p.paint(hexc("4A5A7A"), p.mask().line(arc_pts(530, 350, 10, 10, 180, 300, 10), 1.0).arr(), 0.8)
    p.haze(300, 360, hexc("080A10"), 0.4)
    finish(p, "Bandits", vign=0.55, sat=1.0)


def ev_Envoy():
    p = new(seed=8)
    p.vgradient([(0, hexc("AFB8BC")), (0.5, hexc("E6DEC8")), (1, hexc("DCCFAE"))])
    mist = hexc("E8E0CA")
    r1 = p.ridge(190, [(60, 90, 70, "karst"), (160, 60, 60, "karst"), (300, 50, 90, "round")], rough=6, rough_cell=30, seed=81)
    p.mountain(r1, hexc("7A8690"), mist, fade=70, texture=0.3, edge=0.3, seed=82, folds=2, fold_depth=(10, 50), mist_col=mist, mist_from=(170, 220))
    p.mist(215, 40, mist, 0.85, seed=83, cell=80)
    # city wall with a gate tower on the right
    wall = poly_mask(p, [(380, 290), (380, 196), (640, 186), (640, 296)])
    p.paint(mix(hexc("A69C88"), hexc("7A7060"), smoothstep(190, 296, p.Y)), wall)
    bl = p.mask()
    for y in range(204, 292, 9):
        bl.line([(380, y), (640, y - 6 * (1 - (y - 196) / 100))], 0.5)
    p.paint(hexc("5A5246"), bl.arr() * wall, 0.45)
    cren = p.mask()
    for x in range(382, 640, 10):
        yy = 196 - (x - 380) * 10 / 260
        cren.rect(x, yy - 6, x + 6, yy + 1)
    p.paint(hexc("8A8070"), cren.arr())
    gate = poly_mask(p, [(476, 294)] + arc_pts(500, 252, 24, 26, 180, 360, 20) + [(524, 294)])
    p.paint(hexc("2A221C"), gate)
    p.paint(hexc("8A2A1E"), poly_mask(p, [(482, 294), (482, 256), (518, 256), (518, 294)]), 0.0)
    # gate tower
    gt = p.mask()
    pav = pavilion(gt, 500, 190, 130, tiers=2, story_h=36, roof_h=26)
    for kind, poly in pav:
        col = hexc("8A2A1E") if kind == "body" else hexc("2E2E30")
        p.paint(col, poly_mask(p, poly))
    pil = p.mask()
    for x in (462, 482, 518, 538):
        pil.rect(x - 2, 154, x + 2, 190)
    p.paint(hexc("5A1810"), pil.arr())
    flagm = p.mask()
    for (x, ph) in ((400, 0.5), (600, 1.3)):
        yy = 196 - (x - 380) * 10 / 260
        p.paint(hexc("2A221C"), p.mask().line([(x, yy), (x, yy - 34)], 1.2).arr())
        flag(flagm, x, yy - 34, 18, 10, wave=0.3, facing=-1, phase=ph)
    p.paint(hexc("A82A26"), flagm.arr())
    # road
    road = poly_mask(p, [(0, 330), (476, 294), (524, 294), (300, 360), (0, 360)])
    p.paint(hexc("C8B490"), road, 0.7)
    willow(p, 80, 300, 150, hexc("4A5A3A"), seed=8, opacity=0.9)
    # the envoy party: rider with a white banner, bearers with a gift chest, a scholar with a scroll
    rm = p.mask()
    rider(rm, 250, 330, 70, facing=1, gallop=False, weapon="banner", hat="guan")
    p.paint(hexc("2A2622"), rm.arr())
    p.paint(hexc("F2ECDC"), poly_mask(p, flag(Mask(1, 1), 262, 196, 30, 44, wave=0.15, facing=1, phase=0.4)))
    p.paint(hexc("2A2622"), p.mask().line([(262, 196), (292, 198)], 0.8).arr())
    specs = [dict(x=150, yf=342, h=58, pose="walk", hat="straw", facing=1, col=hexc("3A3A4A")),
             dict(x=196, yf=338, h=56, pose="walk", hat="straw", facing=1, col=hexc("3A3A4A")),
             dict(x=330, yf=320, h=50, pose="salute", hat="guan", robe=True, facing=1, col=hexc("2A3A5A"))]
    people(p, specs, hexc("2A2A30"), rim=hexc("FFF0D0"), rim_dx=-1, rim_op=0.5)
    # gift chest on a pole between the bearers
    p.paint(hexc("2A2018"), p.mask().line([(140, 299), (206, 297)], 1.6).arr())
    p.paint(hexc("8A2418"), poly_mask(p, [(162, 300), (186, 300), (186, 318), (162, 318)]))
    p.paint(hexc("D0A848"), p.mask().line([(162, 309), (186, 309)], 1.2).line([(174, 300), (174, 318)], 1.2).arr())
    finish(p, "Envoy", vign=0.4, sat=0.95)


def ev_Festival():
    p = new(seed=9)
    p.vgradient([(0, hexc("0E1220")), (0.55, hexc("2A2440")), (1, hexc("3A2028"))])
    stars(p, 50, 140, seed=9)
    p.disc(90, 60, 22, hexc("F8E8C0"), 0.95, soft=2)
    p.glow(90, 60, 120, hexc("F0D090"), 0.3)
    # fireworks
    rng = np.random.default_rng(91)
    for (fx, fy, r, col) in ((330, 70, 46, hexc("F8C860")), (470, 50, 34, hexc("F07050")), (210, 110, 28, hexc("F0E0A0")), (560, 110, 30, hexc("F8B048"))):
        m = p.mask()
        for k in range(40):
            a = k / 40 * 6.283 + rng.uniform(-0.05, 0.05)
            rr = r * rng.uniform(0.75, 1.0)
            m.brush([(fx + math.cos(a) * rr * 0.25, fy + math.sin(a) * rr * 0.25), (fx + math.cos(a) * rr, fy + math.sin(a) * rr + rr * 0.08)], 0.3, 1.3)
        p.paint(col, m.arr(), 0.9)
        p.glow(fx, fy, r * 1.6, col, 0.25)
    # street of houses with lit windows
    for (x, w, h, rh, yb) in ((40, 110, 70, 40, 300), (170, 120, 60, 36, 296), (470, 120, 64, 38, 296), (600, 110, 74, 42, 300)):
        house(p, x, yb, w, h, hexc("3A2A28"), hexc("16121A"), door=hexc("F0A050"), win=hexc("F8C070"), roof_h=rh, shade=0.3)
    pv = p.mask()
    pavilion(pv, 320, 230, 80, tiers=2)
    p.paint(hexc("16121A"), pv.arr())
    # lantern strings
    for (x0, y0, x1, y1, n) in ((40, 190, 600, 186, 12), (100, 150, 540, 150, 9)):
        pts = qbez((x0, y0), ((x0 + x1) / 2, y0 + 36), (x1, y1), 40)
        p.paint(hexc("1A1410"), p.mask().line(pts, 0.7).arr())
        for k in range(1, n):
            lx, ly = pts[int(k / n * 39)]
            lantern(p, lx, ly + 9, 6.5, glow=0.18)
    # the dragon dance and crowd
    p.paint(mix(hexc("4A3028"), hexc("1A1210"), smoothstep(300, 360, p.Y)), smoothstep(296, 302, p.Y))
    p.glow(320, 320, 260, hexc("FF9A50"), 0.2)
    dragon(p, 160, 470, 286, 14, hexc("C0302A"), hexc("F2C050"), seed=1)
    specs = []
    for i, x in enumerate(np.arange(170, 470, 50)):
        specs.append(dict(x=x, yf=348, h=50, pose="walk", hat="topknot", facing=1, col=hexc("1A1210")))
    for x in (30, 70, 110, 520, 560, 610):
        specs.append(dict(x=x, yf=356, h=60, pose="stand", hat=rng.choice(["topknot", "straw"]), facing=1 if x < 320 else -1, col=hexc("140E0C")))
    people(p, specs, hexc("1A1210"), rim=hexc("FFB060"), rim_dx=0.0, rim_op=0.0)
    finish(p, "Festival", vign=0.45, sat=1.0)


def ev_Plague():
    p = new(seed=10)
    p.vgradient([(0, hexc("6A7266")), (0.6, hexc("A8AE98")), (1, hexc("7A806E"))])
    fog = hexc("B4B8A0")
    for (x, w, h, rh, yb) in ((30, 100, 60, 34, 270), (160, 110, 52, 32, 262), (470, 120, 58, 36, 262), (600, 100, 66, 38, 270)):
        house(p, x, yb, w, h, hexc("8A8A78"), hexc("3A3E36"), door=hexc("2A2A24"), roof_h=rh, shade=0.3)
        # paper talismans on the doors
        p.paint(hexc("D8C050"), poly_mask(p, [(x - 4, yb - h * 0.55), (x + 4, yb - h * 0.55), (x + 4, yb - h * 0.25), (x - 4, yb - h * 0.25)]))
        p.paint(hexc("9A2A1E"), p.mask().line([(x, yb - h * 0.52), (x, yb - h * 0.3)], 0.8).arr())
    p.mist(240, 80, fog, 0.65, seed=101, cell=90)
    # dead tree with crows
    tips = tree(p, 330, 300, 170, hexc("2A2C26"), seed=11, spread=1.3, leaf=False)
    cm = p.mask()
    for (tx, ty) in tips[::4][:6]:
        cm.ellipse(tx, ty - 3, 4, 3)
        cm.circle(tx + 3, ty - 6, 2)
        cm.poly([(tx - 4, ty - 2), (tx - 9, ty), (tx - 4, ty + 1)])
    p.paint(hexc("1A1A18"), cm.arr())
    # street
    p.paint(mix(hexc("8A8C78"), hexc("5A5C4E"), smoothstep(280, 360, p.Y)), smoothstep(276, 284, p.Y))
    # a physician with a medicine basket and lantern
    specs = [dict(x=420, yf=340, h=78, pose="walk", hat="hood", weapon="staff", facing=-1, cloak=True, col=hexc("2A2E28"))]
    people(p, specs, hexc("2A2E28"), rim=hexc("E0E4C8"), rim_dx=-1, rim_op=0.5)
    p.paint(hexc("6A5A3A"), poly_mask(p, [(426, 292), (446, 292), (444, 306), (428, 306)]))
    lantern(p, 393, 300, 5, col=hexc("C8B060"), glow=0.25)
    # a covered body cart and a kneeling mourner far left
    m = p.mask()
    figure(m, 150, 316, 46, pose="kneel", hat="topknot", facing=1)
    p.paint(hexc("3A3C34"), m.arr())
    p.mist(320, 70, fog, 0.5, seed=102, cell=70)
    p.haze(0, 360, hexc("A0A890"), 0.15)
    finish(p, "Plague", vign=0.5, sat=0.7, tint=(0.98, 1.02, 0.96))


def ev_Flood():
    p = new(seed=11)
    p.vgradient([(0, hexc("2A3038")), (0.4, hexc("5A6470")), (1, hexc("4A4E50"))])
    for (y, h, op) in ((40, 60, 0.6), (100, 50, 0.5)):
        p.mist(y, h, hexc("1E2228"), op, seed=int(y), cell=120)
    mist = hexc("7A8288")
    r1 = p.ridge(200, [(100, 60, 120, "round"), (480, 80, 110, "karst"), (580, 50, 80, "karst")], rough=8, rough_cell=40, seed=111)
    p.mountain(r1, hexc("343A40"), mist, fade=60, texture=0.3, edge=0.3, seed=112, mist_col=mist, mist_from=(190, 220))
    # submerged village: roofs above the water line
    for (x, w, rh, yb) in ((120, 90, 30, 250), (260, 80, 26, 246), (420, 100, 32, 252)):
        rp = roof_poly(x, yb - rh * 0.7, w * 1.3, rh)
        p.paint(hexc("26282A"), poly_mask(p, rp))
    tree(p, 540, 250, 120, hexc("1E2220"), seed=12, spread=1.0)
    tree(p, 40, 252, 90, hexc("1E2220"), seed=13)
    waves(p, 230, 340, hexc("6A5A44"), hexc("D8D0B8"), seed=114, rows=7, amp=6)
    # rescue boat
    bm = p.mask()
    bm.poly([(230, 300), (330, 300), (318, 312), (242, 312)])
    figure(bm, 260, 302, 34, pose="bow", hat="straw", facing=1)
    figure(bm, 300, 302, 38, pose="stand", hat="straw", facing=-1)
    bm.line([(306, 270), (330, 330)], 1.4)
    p.paint(hexc("1A1816"), bm.arr())
    rain(p, 900, hexc("C8D0D8"), seed=115, angle=0.3, length=(10, 22), opacity=0.35)
    finish(p, "Flood", vign=0.5, sat=0.85, tint=(0.97, 1.0, 1.03))


def ev_Omen():
    p = new(seed=12)
    p.vgradient([(0, hexc("080A14")), (0.55, hexc("1E1A30")), (0.8, hexc("4A2228")), (1, hexc("1A1012"))])
    stars(p, 160, 260, seed=12)
    comet(p, 420, 110, 80, 20, 22, seed=12)
    p.disc(560, 236, 30, hexc("C0402A"), 0.9, soft=2)
    p.glow(560, 236, 140, hexc("C04030"), 0.3)
    mist = hexc("3A2A34")
    r1 = p.ridge(280, [(80, 90, 70, "karst"), (200, 120, 60, "karst"), (330, 70, 70, "karst"), (470, 60, 80, "round")], rough=8, rough_cell=30, seed=121)
    p.mountain(r1, hexc("14121C"), mist, fade=80, texture=0.3, edge=0.3, seed=122, mist_col=mist, mist_from=(250, 300))
    p.mist(290, 40, hexc("4A3440"), 0.6, seed=123, cell=80)
    r2 = p.ridge(380, [(560, 160, 140, "dome"), (660, 200, 90, "dome")], rough=6, rough_cell=30, seed=124, smooth=10)
    p.mountain(r2, hexc("0A0A10"), hexc("2A2230"), fade=100, texture=0.4, edge=0.5, seed=125)
    tm = p.mask()
    top = r2[int(560 * SS)]
    pavilion(tm, 580, top + 4, 46, tiers=2)
    p.paint(hexc("0A0A10"), tm.arr())
    specs = [dict(x=516, yf=r2[int(516 * SS)] + 2, h=40, pose="point", hat="guan", robe=True, facing=-1, col=hexc("0A0A10")),
             dict(x=490, yf=r2[int(490 * SS)] + 3, h=34, pose="kneel", hat="topknot", facing=-1, col=hexc("0A0A10"))]
    people(p, specs, hexc("0A0A10"), rim=hexc("C86048"), rim_dx=1, rim_op=0.6)
    finish(p, "Omen", vign=0.5, sat=1.0)


def duel_background():
    p = Painting(1280, 720, ss=SS, seed=20)
    p.vgradient([(0, hexc("3A2830")), (0.3, hexc("8A4A3E")), (0.55, hexc("E08A50")), (0.68, hexc("F2B070")), (1, hexc("6A4A40"))])
    sx, sy = 700, 430
    p.glow(sx, sy, 600, hexc("FFB070"), 0.45, power=1.4)
    p.disc(sx, sy, 92, hexc("F28A52"), 0.95, soft=2.5)
    p.glow(sx, sy, 110, hexc("FFE0A0"), 0.35, power=3)
    for (y, h, op, col) in ((90, 80, 0.4, hexc("3A2A30")), (200, 60, 0.35, hexc("6A3A36")), (330, 30, 0.45, hexc("C07050")), (430, 14, 0.5, hexc("E89A6A"))):
        p.mist(y, h, col, op, seed=int(y), cell=240)
    mist = hexc("E8A878")
    r1 = p.ridge(470, [(150, 130, 90, "karst"), (300, 90, 80, "karst"), (980, 170, 80, "karst"), (1120, 120, 90, "karst"), (1230, 150, 60, "karst")], rough=10, rough_cell=50, seed=201)
    p.mountain(r1, hexc("8A5A54"), mist, fade=140, texture=0.3, edge=0.3, seed=202, folds=2, fold_depth=(20, 90), mist_col=mist, mist_from=(420, 500))
    p.mist(500, 60, mist, 0.9, seed=203, cell=200)
    r2 = p.ridge(560, [(80, 130, 100, "karst"), (420, 80, 100, "karst"), (1060, 140, 90, "karst")], rough=10, rough_cell=40, seed=204)
    p.mountain(r2, hexc("5A3A38"), hexc("D8946A"), fade=120, texture=0.35, edge=0.4, seed=205, folds=2, fold_depth=(20, 80), mist_col=mist, mist_from=(540, 600))
    # sea of clouds below the cliff
    p.mist(590, 90, hexc("F0B888"), 0.95, seed=206, cell=220)
    p.mist(620, 70, hexc("E8A878"), 0.8, seed=207, cell=180)
    # the cliff plateau (duel ground) from the left, dropping off at the right
    cliff = p.ridge(600, [(300, 40, 700, "dome"), (980, -60, 160, "round")], rough=6, rough_cell=60, seed=208, smooth=30)
    x = p.xs()
    drop = smoothstep(940, 1060, x) * 260
    cliff = cliff + drop
    p.mountain(cliff, hexc("2A1C1A"), hexc("6A4A3E"), fade=120, texture=0.5, edge=0.7, edge_w=2.4, seed=209, lit=0.15, folds=3, fold_depth=(20, 100))
    # rim light on the plateau edge
    rim = np.exp(-np.maximum(p.Y - cliff[None, :], 0) / 1.5) * clamp01((p.Y - cliff[None, :]) * SS + 0.5)
    p.paint(hexc("F0A060"), rim, 0.45)
    # bamboo grove framing left and right
    rng = np.random.default_rng(210)
    for k in range(9):
        bx = rng.uniform(-10, 200)
        bamboo(p, bx, 760, rng.uniform(700, 820), rng.uniform(7, 14), hexc("1E1A16"), seed=300 + k, lean=rng.uniform(-0.05, 0.08), opacity=0.92 if k % 2 else 0.7, leaf_col=hexc("1A1814"))
    for k in range(6):
        bx = rng.uniform(1120, 1290)
        bamboo(p, bx, 760, rng.uniform(650, 800), rng.uniform(6, 12), hexc("1E1A16"), seed=400 + k, lean=rng.uniform(-0.08, 0.04), opacity=0.92 if k % 2 else 0.7, leaf_col=hexc("1A1814"))
    # falling leaves
    lm = p.mask()
    for _ in range(40):
        lx, ly = rng.uniform(150, 1150), rng.uniform(150, 600)
        a = rng.uniform(0, 3.14)
        L = rng.uniform(5, 10)
        lm.brush([(lx, ly), (lx + math.cos(a) * L, ly + math.sin(a) * L)], 1.8, 0.4)
    p.paint(hexc("2A2018"), lm.arr(), 0.75)
    p.paper(strength=0.045, seed=211)
    p.vignette(0.45, color=(0.10, 0.06, 0.05), inner=0.5)
    p.grade(sat=0.95)
    p.save(os.path.join(ART, "Duel", "Background.png"), dither_seed=212)


SCENES = {
    "Court": ev_Court, "Battle": ev_Battle, "Harvest": ev_Harvest, "Disaster": ev_Disaster,
    "Wanderer": ev_Wanderer, "Sect": ev_Sect, "Bandits": ev_Bandits, "Envoy": ev_Envoy,
    "Festival": ev_Festival, "Plague": ev_Plague, "Flood": ev_Flood, "Omen": ev_Omen,
    "Duel": duel_background,
}


def main():
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or list(SCENES)
    for n in names:
        SCENES[n]()


if __name__ == "__main__":
    main()
