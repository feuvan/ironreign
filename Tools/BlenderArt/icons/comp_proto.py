"""Look-dev compositions (not part of the build)."""

import math

from common import M, flame_material, cloud_material
from ironart import icons_gongbi as gb
from ironart import icons_kit as K
from ironart import icons_props as P

FACE = -24.0


def Gold(M, cam):
    objs = []
    kw = dict(rim=0.2, wing=0.24, trough=0.12, dome=(0.3, 0.25, 0.3), flare=0.14, W=0.7)
    objs += P.group("ingotA", P.yuanbao("ingA", M["gold"], **kw), (-0.52, 0.32, 0.0), (0, 0, -18))
    objs += P.group("ingotB", P.yuanbao("ingB", M["gold"], **kw), (0.52, 0.38, 0.0), (0, 0, 16))
    objs += P.group("ingotC", P.yuanbao("ingC", M["gold"], **kw), (0.02, -0.32, 0.0), (0, 0, 4),
                    1.12)
    return dict(objs=objs, fill=1.0)


def Walls(M, cam):
    objs = []
    L, D, H = 2.2, 0.55, 0.8
    wall = K.box("wall", (L, D, H), M["masonry"])
    wall.location = (0, 0, H / 2)
    objs.append(wall)
    # parapet coping and merlons
    cop = K.box("coping", (L + 0.06, D + 0.06, 0.06), M["stone"])
    cop.location = (0, 0, H + 0.03)
    objs.append(cop)
    n = 6
    w = L / (2 * n - 1)
    for i in range(n):
        x = -L / 2 + w / 2 + i * 2 * w
        m = K.box("merlon%d" % i, (w, 0.16, 0.24), M["masonry"])
        m.location = (x, -D / 2 + 0.08, H + 0.06 + 0.12)
        objs.append(m)
    # gate arch hint: dark opening
    return dict(objs=objs, fill=1.0)


def _flame_outline(h=1.0, w=0.5, curl=0.25, n=48, lean=0.0):
    pts = []
    for i in range(n + 1):
        t = i / n                      # 0 bottom-left -> 1 bottom-right around the top
        a = math.pi * t
        # base: a tear drop; the tip curls
        x = -math.cos(a) * w * (math.sin(a) ** 0.6)
        z = math.sin(a) ** 2.2 * 0.2 * h
        pts.append((x, z))
    # build explicitly: left edge up to tip, right edge down
    left, right = [], []
    for i in range(n + 1):
        t = i / n
        z = t * h
        bulge = math.sin(min(1.0, t * 1.35) * math.pi) ** 0.8 if t < 0.74 else 0.0
        width = w * (math.sin(math.pi * min(t, 0.999) ** 0.75) ** 1.2) * (1.0 - t) ** 0.35
        cx = lean * t * t + curl * math.sin(t * math.pi * 1.5) * t
        left.append((cx - width, z))
        right.append((cx + width, z))
    return left + right[::-1][1:-1]


def Fire(M, cam):
    objs = []
    fm = flame_material("I_Flame", 0.0, 1.6)
    specs = [  # (x, h, w, curl, lean, depth y, scale)
        (0.0, 1.6, 0.42, 0.16, -0.1, 0.0),
        (-0.42, 1.0, 0.3, -0.12, -0.25, 0.08),
        (0.44, 1.15, 0.3, 0.12, 0.28, 0.08),
        (-0.15, 0.7, 0.22, 0.1, 0.1, -0.1),
    ]
    for i, (x, h, w, curl, lean, dy) in enumerate(specs):
        ol = _flame_outline(h, w, curl, 40, lean)
        o = K.outline_mesh("flame%d" % i, ol, 0.16, fm, plane="XZ")
        K.place(o, (x, dy, 0), (0, 0, FACE))
        objs.append(o)
    # logs
    for i, (x, rz) in enumerate(((-0.25, 30), (0.25, -30))):
        lg = K.cylinder("log%d" % i, 0.09, 1.1, M["wood_dark"], 16)
        K.place(lg, (x, 0.1, 0.0), (90, 0, rz + FACE))
        objs.append(lg)
    gb.put(objs[:4], "red")
    return dict(objs=objs, fill=1.0)


def Wait(M, cam):
    objs = []
    cup = K.lathe("cup", [(0.0, 0.0), (0.2, 0.0), (0.22, 0.03), (0.24, 0.06), (0.36, 0.3),
                          (0.44, 0.52), (0.45, 0.55), (0.42, 0.55), (0.41, 0.52),
                          (0.33, 0.32), (0.0, 0.3)], M["celadon"], 64)
    tea = K.lathe("tea", [(0.0, 0.47), (0.405, 0.47), (0.405, 0.475), (0.0, 0.475)], M["tea"], 64)
    sau = K.lathe("saucer", [(0.0, 0.0), (0.28, 0.0), (0.3, -0.04), (0.62, 0.0), (0.66, 0.06),
                             (0.63, 0.07), (0.3, 0.02), (0.0, 0.02)], M["celadon"], 64)
    sau.location = (0, 0, -0.06)
    objs += [cup, tea, sau]
    # steam wisps
    for i, (x, ph) in enumerate(((-0.1, 0.0), (0.12, 1.3))):
        pts = [(x + 0.08 * math.sin(ph + t * 4.0), 0.0, 0.62 + t * 0.7) for t in
               [k / 8.0 for k in range(9)]]
        s = K.curve_tube("steam%d" % i, pts, 0.018, M["white"], 4, 12)
        objs.append(s)
    gb.put(objs[-2:], "soft")
    return dict(objs=objs, fill=1.0)
