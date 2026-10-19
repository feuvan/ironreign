"""Battle family: gongbi materials of the unit figures, horses and plinth (baked by Cycles).

Flat mineral colours with soft 晕染 grading and fine painted structure, in the manner of a
gongbi figure painting: iron lamellar painted plate by plate (ink-ruled plates, cinnabar lacing,
mud-gold bands), lacquered leather lamellar for the horsemen, a quilted ochre coat for the
archers, indigo trousers with drapery lines (衣纹), striped leg wraps, a face with fine ink brows
and eyes, horses painted as in court horse painting (graded washes, darker stockings, dapples).
``Tint`` stays pure white and is never baked (the runtime multiplies the side colour).
"""

import math

import bpy

from . import world_gongbi as WG
from .battle_mats import _fresh, flat
from .world_mats import L


def lamellar(name="U_Lamellar", plate="#8C949C", plate2="#727A84", line="#24262C", lace="#9E3A2C",
             band="#C9A24B", pw=0.03, ph=0.044):
    """Plates on MetreUV (u around, v along): ink-ruled plates in running bond, each graded
    lighter towards its top edge, cinnabar lacing between the rows, a mud-gold band every six
    rows."""
    mat, w = _fresh(name)
    uv = w.uv()
    s = w.sep(uv)
    row = w.m("FLOOR", w.m("DIVIDE", s["Y"], ph))
    fy = w.m("FRACT", w.m("DIVIDE", s["Y"], ph))
    shift = w.m("MULTIPLY", w.m("FRACT", w.m("MULTIPLY", row, 0.5)), 1.0)
    x = w.m("ADD", w.m("DIVIDE", s["X"], pw), shift)
    fx = w.m("FRACT", x)
    ids = w.comb(w.m("FLOOR", x), row, 0.0)
    col = w.mix(L(plate2), L(plate), w.mr(fy, 0.15, 0.85))
    col = w.mul(col, w.tone(ids, 0.06, 3.1))
    dv = w.m("MULTIPLY", w.m("MINIMUM", fx, w.m("SUBTRACT", 1.0, fx)), pw)
    dh = w.m("MULTIPLY", w.m("MINIMUM", fy, w.m("SUBTRACT", 1.0, fy)), ph)
    edges = w.m("MAXIMUM", w.line(dv, 0.0018), w.line(dh, 0.0022))
    col = w.ink(col, edges, line, 0.75)
    # lacing: short cinnabar stitches at the lower edge of each row, two per plate
    lx = w.m("FRACT", w.m("MULTIPLY", x, 2.0))
    lace_m = w.m("MULTIPLY", w.mr(fy, 0.18, 0.08), w.mr(w.m("ABSOLUTE", w.m("SUBTRACT", lx, 0.5)), 0.18, 0.1))
    col = w.mix(col, L(lace), w.m("MULTIPLY", lace_m, 0.9))
    bandm = w.m("MULTIPLY", w.mr(w.m("FRACT", w.m("DIVIDE", row, 6.0)), 0.0, 0.02, 1.0, 0.0), w.mr(fy, 0.25, 0.35))
    col = w.mix(col, L(band), w.m("MULTIPLY", bandm, 0.85))
    col = w.wash(col, 0.04, 3.0, 0.02, 60.0)
    w.paint_out(col, w.m("SUBTRACT", 1.0, edges), 0.25, 0.002)
    return mat


def cloth(name, color, deep, line="#1E1A16", fold=0.06, line_alpha=0.35, quilt=None):
    """Cloth: a wash graded deeper along the folds, drapery lines (衣纹) running down the
    garment (MetreUV v), broken and of varying pressure; ``quilt`` = row spacing of quilting."""
    mat, w = _fresh(name)
    uv = w.uv()
    s = w.sep(uv)
    o = w.obj()
    n = w.noise(w.scale(o, 6.0), 1.0, 2)
    col = w.mix(L(deep), L(color), w.mr(w.m("SINE", w.m("MULTIPLY", s["X"], math.tau / fold)), -0.8, 0.9))
    col = w.mix(col, L(color), 0.45)
    lines = w.line(w.periodic_dist(w.m("ADD", s["X"], w.m("MULTIPLY", w.m("SUBTRACT", n, 0.5), 0.03)), fold), 0.0016)
    lines = w.m("MULTIPLY", lines, w.mr(w.noise(w.scale(uv, (4.0, 9.0, 1.0)), 1.0, 2), 0.42, 0.55))
    col = w.ink(col, lines, line, line_alpha)
    if quilt:
        q = w.line(w.periodic_dist(s["Y"], quilt), 0.0014)
        col = w.ink(col, q, line, 0.3)
    col = w.wash(col, 0.04, 3.0, 0.02, 60.0)
    w.paint_out(col, lines, 0.15, 0.002)
    return mat


def wrap(name="U_Wrap", color="#AE9670", line="#4A3A28"):
    """Leg wraps (绑腿): diagonal binding stripes."""
    mat, w = _fresh(name)
    s = w.sep(w.uv())
    d = w.periodic_dist(w.m("ADD", w.m("MULTIPLY", s["X"], 0.5), s["Y"]), 0.035)
    lines = w.line(d, 0.0016)
    col = w.wash(L(color), 0.05, 3.0, 0.02, 60.0)
    col = w.ink(col, lines, line, 0.5)
    w.paint_out(col, lines, 0.2, 0.002)
    return mat


def skin(name="U_Skin", color="#E2C2A0", rouge="#C98C76"):
    mat, w = _fresh(name)
    o = w.obj()
    n = w.noise(w.scale(o, 8.0), 1.0, 2)
    col = w.mix(L(color), L(rouge), w.mr(n, 0.55, 0.8, 0.0, 0.25))
    w.paint_out(w.wash(col, 0.03, 4.0, 0.01, 80.0))
    return mat


def face(name="U_Face", color="#E4C4A2", ink="#1E1A16", rouge="#C8806E"):
    """Head with a face in the figure-painting canon (UV of :func:`battle_figures.ellipsoid_uv`:
    u = angle / 2pi, front at u = 0.75; v = 0 chin .. 1 crown): fine arched ink brows, almond
    eyes as short dark strokes, a small mouth line, a soft rouge on the cheeks, hair in ink at
    the temples and nape (under the helmet)."""
    mat, w = _fresh(name)
    s = w.sep(w.uv())
    u, v = s["X"], s["Y"]
    du = w.m("SUBTRACT", u, 0.75)
    adu = w.m("ABSOLUTE", du)
    col = L(color)
    # rouge on the cheeks
    ch = w.m("ADD", w.m("POWER", w.m("DIVIDE", w.m("SUBTRACT", adu, 0.07), 0.035), 2.0),
             w.m("POWER", w.m("DIVIDE", w.m("SUBTRACT", v, 0.41), 0.05), 2.0))
    col = w.mix(col, L(rouge), w.mr(ch, 1.0, 0.0, 0.0, 0.35))
    # eyes: short dark ellipses
    e = w.m("ADD", w.m("POWER", w.m("DIVIDE", w.m("SUBTRACT", adu, 0.052), 0.022), 2.0),
            w.m("POWER", w.m("DIVIDE", w.m("SUBTRACT", v, 0.5), 0.013), 2.0))
    eye = w.mr(e, 1.1, 0.8)
    # brows: arched strokes
    by = w.m("ADD", 0.565, w.m("MULTIPLY", w.m("POWER", w.m("SUBTRACT", adu, 0.055), 2.0), -6.0))
    b = w.m("ADD", w.m("POWER", w.m("DIVIDE", w.m("SUBTRACT", adu, 0.058), 0.034), 2.0),
            w.m("POWER", w.m("DIVIDE", w.m("SUBTRACT", v, by), 0.009), 2.0))
    brow = w.mr(b, 1.1, 0.8)
    # mouth
    mth = w.m("ADD", w.m("POWER", w.m("DIVIDE", du, 0.022), 2.0), w.m("POWER", w.m("DIVIDE", w.m("SUBTRACT", v, 0.31), 0.007), 2.0))
    mouth = w.mr(mth, 1.1, 0.7)
    # hair: back half and the top (under the helmet)
    hair = w.m("MAXIMUM", w.mr(adu, 0.17, 0.21), w.mr(v, 0.64, 0.68))
    col = w.mix(col, L("#2A2420"), hair)
    col = w.ink(col, eye, ink, 0.9)
    col = w.ink(col, brow, ink, 0.85)
    col = w.ink(col, mouth, "#8E4A40", 0.8)
    w.paint_out(col)
    return mat


def shield(name="U_Shield", field="#A83C2C", band="#C9A24B", rim="#2A2420", motif="#E0C47E"):
    """Round shield on lathe UV (v = distance from the boss outward): cinnabar field with a
    painted mud-gold cloud-scroll ring, a gold band and an ink-dark rim."""
    mat, w = _fresh(name)
    s = w.sep(w.uv())
    o = w.obj()
    r = s["Y"]
    col = w.mix(L(field), L("#8E2E22"), w.mr(r, 0.05, 0.3))
    # scroll ring: a wavy gold line at mid radius
    wav = w.m("ADD", w.m("SUBTRACT", r, 0.17), w.m("MULTIPLY", w.m("SINE", w.m("MULTIPLY", s["X"], 55.0)), 0.025))
    col = w.ink(col, w.line(w.m("ABSOLUTE", wav), 0.004), motif, 0.9)
    col = w.mix(col, L(band), w.mr(w.m("ABSOLUTE", w.m("SUBTRACT", r, 0.28)), 0.016, 0.01))
    col = w.mix(col, L(rim), w.mr(r, 0.305, 0.315))
    col = w.wash(col, 0.04, 3.0, 0.02, 60.0)
    w.paint_out(col)
    return mat


def helm(name="U_Helm", color="#A4ACB4", deep="#6E7680", line="#24262C"):
    """Iron helmet: a pale ink-grey wash, deeper toward the rim, ruled segment lines."""
    mat, w = _fresh(name)
    o = w.obj()
    nz = w.sep(w.nb.coord("Normal"))["Z"]
    col = w.mix(L(deep), L(color), w.mr(nz, -0.2, 0.8))
    s = w.sep(w.uv())
    seg = w.line(w.periodic_dist(s["X"], 0.045), 0.0015)
    col = w.ink(col, seg, line, 0.45)
    w.paint_out(w.wash(col, 0.03, 4.0, 0.015, 60.0), seg, 0.2, 0.002)
    return mat


def steel(name="U_Steel", color="#C2CAD0", edge="#5E666E"):
    mat, w = _fresh(name)
    nz = w.sep(w.nb.coord("Normal"))["Z"]
    col = w.mix(L(edge), L(color), w.mr(nz, -0.4, 0.6))
    w.paint_out(w.wash(col, 0.03, 4.0, 0.01))
    return mat


def wood(name="U_Wood", color="#8A6440", grain="#4A3424"):
    mat, w = _fresh(name)
    o = w.obj()
    n = w.noise(w.scale(o, (30.0, 30.0, 3.0)), 1.0, 2)
    col = w.mix(L(color), L(grain), w.mr(n, 0.55, 0.75, 0.0, 0.4))
    w.paint_out(w.wash(col, 0.04, 4.0, 0.02))
    return mat


def horse(name, coat, deep, belly, stock=None, dapple=None, line="#3A2E26"):
    """Court horse painting: a graded coat (deeper on the belly and the rump, 晕染), darker
    stockings below the knees, optional dapples, faint ink hair lines on the barrel."""
    mat, w = _fresh(name)
    o = w.obj()
    s = w.sep(o)
    nz = w.sep(w.nb.coord("Normal"))["Z"]
    n = w.noise(w.scale(o, 2.5), 1.0, 3)
    col = w.mix(L(deep), L(coat), w.mr(w.m("ADD", nz, w.m("MULTIPLY", w.m("SUBTRACT", n, 0.5), 0.6)), -0.6, 0.5))
    col = w.mix(col, L(belly), w.mr(nz, -0.45, -0.85, 0.0, 0.55))
    if dapple:
        v = w.voronoi(w.scale(o, 9.0), 1.0)
        dm = w.m("MULTIPLY", w.mr(v, 0.32, 0.2), w.mr(s["Z"], 0.9, 1.2))
        col = w.mix(col, L(dapple), w.m("MULTIPLY", dm, 0.6))
    if stock:
        col = w.mix(col, L(stock), w.mr(s["Z"], 0.5, 0.32))
    hair = w.noise(w.scale(o, (40.0, 4.0, 40.0)), 1.0, 2)
    col = w.ink(col, w.mr(hair, 0.62, 0.7, 0.0, 1.0), line, 0.12)
    col = w.wash(col, 0.04, 2.0, 0.02, 40.0)
    w.paint_out(col)
    return mat


def base_rim(name="U_BaseRim", color="#2A2119", gold="#C9A24B"):
    """The plinth's side band: dark lacquer with a mud-gold line (lathe UV v = height)."""
    mat, w = _fresh(name)
    s = w.sep(w.uv())
    col = w.mix(L(color), L(gold), w.mr(w.m("ABSOLUTE", w.m("SUBTRACT", s["Y"], 0.08)), 0.012, 0.006))
    w.paint_out(w.wash(col, 0.03, 2.0, 0.015))
    return mat


def library(density=None):
    if density:
        WG.set_density(density)
    lib = {}
    for fn, args, kw in (
            (lamellar, (), {}),
            (lamellar, ("U_LamellarRed", "#9A5038", "#7A3A2A", "#241812", "#C9A24B", "#C9A24B"), {}),
            (cloth, ("U_Coat", "#B89464", "#9C7848"), dict(fold=0.07, quilt=0.05)),
            (cloth, ("U_Trousers", "#56627C", "#3E4A62"), dict(fold=0.05)),
            (cloth, ("U_Sleeve", "#9A4A36", "#7A3428"), dict(fold=0.045)),
            (wrap, (), {}),
            (skin, (), {}),
            (face, (), {}),
            (shield, (), {}),
            (helm, (), {}),
            (steel, (), {}),
            (wood, (), {}),
            (horse, ("U_HorseWhite", "#E8E1D2", "#B9B2A4", "#A8A194"), dict(dapple="#9C978C")),
            (horse, ("U_HorseBay", "#9A6238", "#6E4024", "#5A3420"), dict(stock="#2A2220")),
            (horse, ("U_HorseChestnut", "#B47A46", "#8A5430", "#7A4A2A"), {}),
            (horse, ("U_HorseDun", "#CDB07A", "#A68A58", "#8E7448"), dict(stock="#4A3A2A")),
            (horse, ("U_HorseBlack", "#3E3834", "#2A2420", "#24201C"), {}),
            (flat, ("U_Mane", "#2A2420"), {}),
            (flat, ("Hoof", "#3A3028"), {}),
            (flat, ("Rope", "#5A4632"), {}),
            (flat, ("Leather", "#5A4030"), {}),
            (flat, ("U_Leather", "#5E4432"), {}),
            (flat, ("Saddle", "#7A3E2A"), {}),
            (flat, ("U_Gold", "#C9A24B"), {}),
            (flat, ("U_Dark", "#2A2420"), {}),
            (flat, ("U_Feather", "#E2DCCB"), {}),
            (base_rim, (), {}),
    ):
        m = fn(*args, **kw)
        lib[m.name] = m
    return lib
