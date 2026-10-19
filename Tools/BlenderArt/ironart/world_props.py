"""World Models family: Sect (cliff temple), Banner (war banner) and Flag (pennant) builders.

Sect
    A rocky outcrop (~35 m) sculpted as a heightfield of nested mesas - a low forecourt, two
    temple terraces with cliffs between them, a summit and a spur - with real cliff noise and
    strata, stone stairs carved up the risers, a memorial gateway at the foot, a main hall, a side
    hall, a pavilion on the spur, a five-tier pagoda on the summit and pines on the ledges.

Banner (~22 m) and Flag (~10 m)
    Dark lacquered pole, iron spear tip with a gilt collar and red horsehair tassel, crossbar;
    the cloth is a dense grid with a gentle sculpted wave and a **pure white** ``Tint`` material
    (the runtime multiplies the faction colour); the banner's free edges carry a dark flame-tooth
    trim band (non-tint).  :func:`banner` returns the corners of the clean glyph field.
"""

import math
import random

import numpy as np
from mathutils import Vector

from . import world_kit as K
from .geometry import MeshBuilder

TAU = math.tau


# ---------------------------------------------------------------------------------------------
# sect
# ---------------------------------------------------------------------------------------------
def _smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _fbm(X, Y, seed, cell=6.0, octaves=4):
    rng = np.random.default_rng(seed)
    acc = np.zeros_like(X)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        f = (2 ** o) / cell
        ph = rng.uniform(0, TAU, 4)
        acc += amp * (np.sin(X * f * 1.3 + ph[0]) * np.cos(Y * f * 0.9 + ph[1])
                      + np.sin((X + Y) * f * 0.7 + ph[2]) * 0.6 + np.cos((X - Y) * f * 1.1 + ph[3]) * 0.4)
        tot += amp * 2.0
        amp *= 0.5
    return acc / tot


#: mesas: (cx, cy, rx, ry, top z, cliff width) - nested, the max wins.  The first one is the
#: outcrop body rising from below the ground (-2.5 m) so the model sits on any terrain.
SECT_MESAS = [
    (0.0, 0.5, 17.5, 18.0, 3.0, 2.2),        # outcrop body
    (0.0, -2.0, 15.0, 9.5, 6.5, 1.2),        # terrace 1 (side hall)
    (-1.0, 5.0, 12.5, 7.8, 12.0, 1.4),       # terrace 2 (main hall)
    (-8.0, 13.0, 6.3, 5.0, 19.0, 1.3),       # summit (pagoda)
    (9.0, 12.5, 4.8, 4.2, 16.0, 1.2),        # spur (pavilion)
]


def sect_height(X, Y, seed=7):
    nz = _fbm(X, Y, seed, 7.0, 5)
    ang = np.arctan2(Y, X)
    h = None
    for k, (cx, cy, rx, ry, top, cw) in enumerate(SECT_MESAS):
        wob = 1.0 + 0.1 * np.sin(ang * 3 + k) + 0.06 * np.sin(ang * 5 + 2 * k) + 0.12 * _fbm(X, Y, seed + k, 5.0, 3)
        d = np.sqrt(((X - cx) / rx) ** 2 + ((Y - cy) / ry) ** 2) / wob
        edge = _smooth(1.0, 1.0 - cw / max(rx, ry), d)
        cliff = (nz * 0.9 + 0.25) * edge * (1 - edge) * 4.0
        if h is None:
            h = -2.6 + (top + 2.6) * edge + cliff + nz * 0.3 * edge
        else:
            # only inside its own outline (outside, the mesa must not pull the ground up to 0)
            layer = top * edge + cliff + nz * 0.22 * edge
            h = np.where(edge > 1e-4, np.maximum(h, layer), h)
    # forecourt cut into the front of the outcrop (flat at z = 0.3)
    fc = _smooth(1.0, 0.7, np.sqrt((X / 7.0) ** 2 + ((Y + 14.5) / 4.2) ** 2))
    h = h * (1 - fc) + 0.3 * fc
    return h


def sect_rock(mb, size=(40.0, 42.0), step=0.6, seed=7, mat="W_Rock"):
    """Heightfield outcrop mesh (skirted to -2.5 m outside the outline)."""
    sx, sy = size
    nx, ny = int(sx / step), int(sy / step)
    xs = np.linspace(-sx / 2, sx / 2, nx + 1)
    ys = np.linspace(-sy / 2, sy / 2, ny + 1)
    X, Y = np.meshgrid(xs, ys)
    Hh = sect_height(X, Y, seed)
    ids = [[mb.v((float(X[j, i]), float(Y[j, i]), float(Hh[j, i]))) for i in range(nx + 1)] for j in range(ny + 1)]
    for j in range(ny):
        for i in range(nx):
            if max(Hh[j, i], Hh[j, i + 1], Hh[j + 1, i], Hh[j + 1, i + 1]) < -2.4:
                continue
            mb.face((ids[j][i], ids[j][i + 1], ids[j + 1][i + 1], ids[j + 1][i]), mat, None, True)
    return Hh


def sect_layout():
    """(prototype, x, y, z, rz) for the sect buildings on the terraces (z = terrace tops)."""
    return [
        ("paifang", 0.0, -16.0, 0.3, 0.0),
        ("side_hall", 8.0, -5.0, 6.5, 0.0),
        ("main_hall", -0.5, 4.0, 12.0, 0.0),
        ("pagoda", -8.0, 13.5, 19.0, 0.0),
        ("pavilion", 9.0, 12.5, 16.0, 0.0),
    ]


#: stairs: (x, y, z0, width, rise, n, run, rz)
SECT_STAIRS = [
    (-1.0, -13.6, 0.3, 3.0, 6.2, 26, 0.2, 0.0),
    (-0.5, -6.2, 6.5, 3.0, 5.5, 22, 0.22, 0.0),
    (-1.2, 9.6, 12.0, 2.2, 7.0, 28, 0.22, math.pi / 2),
]

#: trees: (kind, x, y, scale) - z from the rock (ground level outside it)
SECT_TREES = [
    ("pine", 12.5, 3.0, 0.42), ("pine", -12.5, -5.0, 0.4), ("pine", -3.5, 16.5, 0.38),
    ("pine", 13.5, -11.0, 0.36), ("pine", -14.5, 5.5, 0.4), ("pine", 4.0, 15.5, 0.34),
    ("pine", -11.5, -12.5, 0.34), ("broad", 11.0, -14.5, 0.32), ("broad", -9.0, 1.5, 0.3),
]


def p_pavilion():
    mb = MeshBuilder()
    K.hall(mb, (0, 0, 0), K.HallSpec(
        bays=(1, 1), bay=3.4, col_h=2.8, col_r=0.16, plat_h=0.5, plat_margin=0.7, plat_mat="W_Stone",
        steps=False, wall_mat="W_Plaster", front="open", side="open", front_inset=0.0, brackets=False,
        roof=K.RoofSpec(style="pyramid", overhang=1.0, lift=0.5, flare=0.3, thick=0.2, pitch=0.5, tile_seg=4,
                        tile_faces=2, nv=8, mat="W_TileGreen", ridge_mat="W_RidgeGreen", finial="gold",
                        ridge_h=0.35)), roof_h=2.4)
    K.railing_rect(mb, 4.4, 4.4, 0.5, 0.8)
    return mb


# ---------------------------------------------------------------------------------------------
# banner / flag
# ---------------------------------------------------------------------------------------------
def _wave(u, v, amp, waves=1.4, phase=0.3):
    """Out-of-plane cloth offset at (u along the fly 0..1, v down 0..1): a travelling ripple that
    grows away from the hoist, plus a soft diagonal fold and a little belly."""
    return amp * ((0.15 + 0.85 * u) * math.sin(TAU * (waves * u - 0.18 * v) + phase)
                  + 0.35 * math.sin(math.pi * u) * math.sin(math.pi * v)
                  + 0.18 * u * math.sin(TAU * 1.3 * v + 1.1))


def pole(mb, h, r0=0.16, r1=0.11, mat="W_LacquerDark", z0=-1.0):
    mb.lathe([(r0, 0.0), (r1, h - z0)], mat, 10, center=(0, 0, z0), smooth=True)


def spear_tip(mb, z, scale=1.0):
    k = scale
    mb.lathe([(0.17 * k, 0.0), (0.22 * k, 0.12 * k), (0.15 * k, 0.3 * k), (0.2 * k, 0.42 * k), (0.12 * k, 0.55 * k)],
             "W_Gold", 10, center=(0, 0, z), smooth=True)
    # leaf blade (flattened lathe)
    s = mb.n
    mb.lathe([(0.1 * k, 0.0), (0.2 * k, 0.35 * k), (0.17 * k, 0.9 * k), (0.0, 1.55 * k)], "W_Iron", 8,
             center=(0, 0, 0), smooth=True)
    for i in range(s, mb.n):
        v = mb.verts[i]
        mb.verts[i] = Vector((v.x, v.y * 0.28, v.z + z + 0.55 * k))
    # horsehair tassel under the collar: flared skirt of strands (lathe with a ragged rim)
    mb.lathe([(0.2 * k, 0.0), (0.42 * k, -0.35 * k), (0.62 * k, -0.95 * k), (0.55 * k, -1.25 * k)],
             "W_Tassel", 12, center=(0, 0, z + 0.02), smooth=True)


def banner(mb, H=22.0, cloth_w=7.0, cloth_h=10.0, trim=0.6, amp=0.34, seed=3, nu=22, nv=30):
    """War banner (front = -y): pole on a stone foot, spear tip, crossbar, white Tint cloth hung
    from the crossbar and laced to the pole, flame-tooth trim on the fly and foot.  Returns the
    4 world corners (TL, TR, BR, BL) of the clean glyph field (cloth minus trim)."""
    rng = random.Random(seed)
    mb.box((0, 0, -1.0), (1.3, 1.3, 1.5), "W_Stone", taper=(0.15, 0.15), top_mat="W_Stone")
    mb.box((0, 0, 0.5), (0.8, 0.8, 0.35), "W_Stone", taper=(0.1, 0.1))
    pole(mb, H - 1.9, 0.17, 0.12)
    spear_tip(mb, H - 1.9, 1.0)
    top = H - 2.6
    x0 = 0.18
    # crossbar with gilt end caps
    mb.cylinder((-0.25, 0, top + 0.05), (x0 + cloth_w + 0.35, 0, top + 0.05), 0.085, mat="W_LacquerDark", segments=8)
    mb.sphere((x0 + cloth_w + 0.4, 0, top + 0.05), 0.13, "W_Gold", 8, 5)
    # cloth grid: u along the fly, v down
    def P(u, v):
        x = x0 + u * cloth_w
        z = top - 0.12 - v * cloth_h - 0.25 * u * v * v
        y = _wave(u, v, amp)
        return Vector((x, y, z))

    def cloth_patch(u0, u1, v0, v1, mat, nu_, nv_, uv_scale=1.0):
        ids = [[mb.v(P(u0 + (u1 - u0) * i / nu_, v0 + (v1 - v0) * j / nv_)) for i in range(nu_ + 1)] for j in range(nv_ + 1)]
        for j in range(nv_):
            for i in range(nu_):
                uu = [(u0 + (u1 - u0) * a / nu_) * cloth_w for a in (i, i + 1)]
                vv = [(v0 + (v1 - v0) * b / nv_) * cloth_h for b in (j, j + 1)]
                mb.face((ids[j][i], ids[j][i + 1], ids[j + 1][i + 1], ids[j + 1][i]), mat,
                        [(uu[0], -vv[0]), (uu[1], -vv[0]), (uu[1], -vv[1]), (uu[0], -vv[1])], True)
        return ids

    tu = trim / cloth_w
    tv = trim / cloth_h
    # the Tint field
    cloth_patch(0.0, 1.0 - tu, 0.0, 1.0 - tv, "Tint", nu, nv)
    # trim: fly edge (right) and foot (bottom), continuous with the field
    cloth_patch(1.0 - tu, 1.0, 0.0, 1.0 - tv, "W_Trim", 2, nv)
    cloth_patch(0.0, 1.0, 1.0 - tv, 1.0, "W_Trim", nu + 2, 2)
    # flame teeth beyond the trim
    nt = 9
    for k in range(nt):
        v0 = (k / nt) * (1.0 - tv)
        v1 = ((k + 1) / nt) * (1.0 - tv)
        a, b = P(1.0, v0), P(1.0, v1)
        c = P(1.0, (v0 + v1) / 2) + Vector((0.55, 0.0, -0.15))
        quad = [mb.v(a), mb.v(c), mb.v(b)]
        mb.face(quad[::-1], "W_Trim")
    nb = 7
    for k in range(nb):
        u0, u1 = k / nb, (k + 1) / nb
        a, b = P(u0, 1.0), P(u1, 1.0)
        c = P((u0 + u1) / 2, 1.0) + Vector((0.15, 0.0, -0.6))
        mb.face([mb.v(a), mb.v(b), mb.v(c)][::-1], "W_Trim")
    # gilt piping between the field and the trim
    pip = [P(1.0 - tu, v * (1.0 - tv) / 12) + Vector((0, -0.03, 0)) for v in range(13)]
    pip += [P((1.0 - tu) * (1 - k / 12), 1.0 - tv) + Vector((0, -0.03, 0)) for k in range(1, 13)]
    K.sweep(mb, [tuple(p) for p in pip], [(-0.05, -0.05), (-0.05, 0.05), (0.05, 0.05), (0.05, -0.05)],
            "W_Gold~d", closed_section=True, caps=False, smooth=True, up=(0, -1, 0))
    # lacing rings on the pole
    for k in range(7):
        z = top - 0.4 - k * (cloth_h - 0.8) / 6
        mb.lathe([(0.19, -0.06), (0.23, 0.0), (0.19, 0.06)], "W_Gold~d", 10, center=(0, 0, z), smooth=True)
    return [P(0.0, 0.0), P(1.0 - tu, 0.0), P(1.0 - tu, 1.0 - tv), P(0.0, 1.0 - tv)]


def flag(mb, H=10.0, length=5.2, hoist=3.0, amp=0.28, nu=18, nv=8):
    """Pennant on a short pole: tapering swallowtail pennant (Tint) laced to the pole, gilt ball
    and spike finial.  Returns the pennant corners (hoist top, fly tip top, fly tip bottom,
    hoist bottom)."""
    mb.box((0, 0, -0.8), (0.7, 0.7, 1.1), "W_Stone", taper=(0.1, 0.1))
    pole(mb, H - 0.9, 0.11, 0.08)
    mb.sphere((0, 0, H - 0.75), 0.2, "W_Gold", 10, 6)
    mb.cylinder((0, 0, H - 0.6), (0, 0, H), 0.07, 0.0, "W_Gold", 8)
    top = H - 1.2
    x0 = 0.1

    def P(u, v):
        taper = 1.0 - 0.62 * u
        x = x0 + u * length
        zc = top - hoist / 2 - 0.35 * u * u
        z = zc + (0.5 - v) * hoist * taper
        y = _wave(u, v, amp, waves=1.2, phase=0.8)
        return Vector((x, y, z))

    # swallowtail: the fly edge is a clean V - every row of the grid ends at u_end(v), 1 at the two
    # tails and 1 - notch on the centre line (no skipped quads, so no stair-stepped notch)
    notch = 0.2

    def u_end(v):
        return 1.0 - notch * (1.0 - abs(2.0 * v - 1.0))

    uu = [[u_end(j / nv) * i / nu for i in range(nu + 1)] for j in range(nv + 1)]
    ids = [[mb.v(P(uu[j][i], j / nv)) for i in range(nu + 1)] for j in range(nv + 1)]
    for j in range(nv):
        for i in range(nu):
            mb.face((ids[j][i], ids[j][i + 1], ids[j + 1][i + 1], ids[j + 1][i]), "Tint",
                    [(uu[j][i] * length, -j / nv * hoist), (uu[j][i + 1] * length, -j / nv * hoist),
                     (uu[j + 1][i + 1] * length, -(j + 1) / nv * hoist), (uu[j + 1][i] * length, -(j + 1) / nv * hoist)],
                    True)
    for k in range(4):
        z = top - 0.2 - k * (hoist - 0.4) / 3
        mb.lathe([(0.12, -0.05), (0.15, 0.0), (0.12, 0.05)], "W_Gold~d", 8, center=(0, 0, z), smooth=True)
    return [P(0, 0), P(1, 0), P(1, 1), P(0, 1)]
