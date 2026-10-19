"""Gongbi wash materials for the gongbi_C bust (Cycles emission only: no light, no shadow).

Every surface is a *flat mineral wash* (``light``) that deepens towards its outline (分染, the
facing ratio) and, optionally, in recesses (AO).  A tiny painter's light (``form``) keeps the
volume legible.  Materials also write two AOVs that the 2D stage uses to clip its washes and
face strokes:

* ``pc_region`` (value): region id of the material (see :data:`REGION`)
* ``pc_mask``   (colour): R = face skin of the head, G = hair, B = any skin

Patterns (lamellae, brocade, roundels, hair streaks, gauze) are drawn by the shader in UV metres
so they keep their painted size on every piece.
"""

import math

import bpy

from ironart.materials import new as _new_mat
from ironart.scenes_sky import G

from looks import srgb, lin

from b_regions import REGION  # noqa: E402

PAINT_LIGHT = (-0.55, -0.62, 0.56)   # towards the painter's light (top-left, in front)


def _builder(name):
    mat, nb, created = _new_mat(name)
    return mat, G(nb.tree), created


def _aov(b, name, value, kind="Value"):
    a = b.node("ShaderNodeOutputAOV")
    if hasattr(a, "aov_name"):
        a.aov_name = name
    else:
        a.name = name           # Blender 4.0: the AOV name shadows Node.name
    b.set(a.inputs[kind], value)
    return a


def facing(b, blend=0.4, lo=0.05, hi=1.0, power=1.0):
    lw = b.node("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = blend
    f = lw.outputs["Facing"]
    if power != 1.0:
        f = b.math("POWER", f, power)
    return b.smooth(f, lo, hi)


def uv(b):
    s = b.sep(b.coord("UV"))
    return s[0], s[1]


def form_term(b, amount):
    """1 - amount .. 1 + amount/4 from a soft N.L with the painter's light."""
    geo = b.node("ShaderNodeNewGeometry")
    n = math.sqrt(sum(v * v for v in PAINT_LIGHT))
    L = b.vec(tuple(v / n for v in PAINT_LIGHT))
    d = b.vmath("DOT_PRODUCT", geo.outputs["Normal"], L)
    f = b.math("ADD", b.math("MULTIPLY", d.outputs["Value"], 0.5), 0.5, clamp=True)
    return b.maprange(f, 0.0, 1.0, 1.0 - amount, 1.0 + amount * 0.25)


def wash(name, light, deep=None, region="none", face=0.0, hair=0.0, skin=0.0, blend=0.42,
         lo=0.06, hi=1.0, power=1.0, form=0.07, ao=0.0, ao_dist=0.03, pattern=None,
         grad=None):
    """Emission wash.  ``pattern(b, col) -> col`` may add shader-painted detail.
    ``grad(b) -> 0..1`` replaces the facing gradient."""
    mat, b, created = _builder(name)
    if not created:
        return mat
    lc = lin(light)
    dc = lin(deep) if deep is not None else tuple(x * 0.62 for x in lc)
    g = grad(b) if grad is not None else facing(b, blend, lo, hi, power)
    if ao > 0:
        a = b.node("ShaderNodeAmbientOcclusion")
        a.samples = 6
        a.only_local = True
        a.inputs["Distance"].default_value = ao_dist
        occ = b.math("MULTIPLY", b.math("SUBTRACT", 1.0, a.outputs["AO"]), ao)
        g = b.math("MAXIMUM", g, occ)
    col = b.mix(lc + (1.0,), dc + (1.0,), g)
    if pattern is not None:
        col = pattern(b, col)
    if form > 0:
        col = b.cmul(col, form_term(b, form))
    em = b.node("ShaderNodeEmission")
    b.set(em.inputs["Color"], col)
    em.inputs["Strength"].default_value = 1.0
    b.output(em.outputs[0])
    _aov(b, "pc_region", REGION[region] / 100.0)
    if face or hair or skin:
        c = b.comb(float(face), float(hair), float(skin))
        _aov(b, "pc_mask", c, "Color")
    return mat


# ---------------------------------------------------------------------------------------------
# shader patterns (UV metres)
# ---------------------------------------------------------------------------------------------


def _frac(b, x):
    return b.math("FRACT", x)


def _line(b, f, width):
    """1 near f == 0 or 1 (a ruled line of relative ``width``), soft edge."""
    d = b.math("MINIMUM", f, b.math("SUBTRACT", 1.0, f))
    return b.smooth(d, width, width * 0.35, 0.0, 1.0)


def lamellae(ph=0.020, pw=0.011, ink="#2A2622", lace="#A83A2A", deep_k=0.55, line=0.07,
             vline=0.10, gold_rows=None):
    """Lamellar plates (札甲): rows of overlapping plates, darker towards each plate's lower
    edge, ink outlines, cinnabar lacing between the plates."""
    def pat(b, col):
        u, v = uv(b)
        rv = b.math("DIVIDE", b.math("MULTIPLY", v, -1.0), ph)
        row = b.math("FLOOR", rv)
        fv = _frac(b, rv)
        uu = b.math("ADD", b.math("DIVIDE", u, pw), b.math("MULTIPLY", row, 0.5))
        fu = _frac(b, uu)
        # per plate: lighter at the top, deeper towards the overlap at the bottom
        shade = b.math("MULTIPLY", b.math("POWER", fv, 2.2), deep_k)
        dark = b.cmul(col, 0.5)
        col = b.mix(col, dark, shade)
        # a soft highlight on the plate's rounded centre line and a pale rim along its top
        hl = b.math("MULTIPLY", b.smooth(b.math("ABSOLUTE", b.math("SUBTRACT", fu, 0.5)), 0.32, 0.0),
                    0.22)
        rim = b.math("MULTIPLY", b.smooth(fv, 0.16, 0.06), 0.35)
        col = b.mix(col, (0.80, 0.84, 0.86, 1.0), rim)
        col = b.mix(col, (0.92, 0.92, 0.9, 1.0), b.math("MULTIPLY", hl, b.math("SUBTRACT", 1.0, fv)))
        # lacing: short cinnabar ties across the vertical joints near the top and bottom
        jd = b.math("MINIMUM", fu, b.math("SUBTRACT", 1.0, fu))
        near_j = b.smooth(jd, 0.16, 0.08)
        bands = b.math("MAXIMUM", b.smooth(b.math("ABSOLUTE", b.math("SUBTRACT", fv, 0.22)), 0.07, 0.03),
                       b.smooth(b.math("ABSOLUTE", b.math("SUBTRACT", fv, 0.62)), 0.07, 0.03))
        lacing = b.math("MULTIPLY", near_j, bands)
        col = b.mix(col, lin(lace) + (1.0,), lacing)
        # ink: row edges (strong) and plate edges (lighter)
        rline = _line(b, fv, line)
        pline = b.math("MULTIPLY", _line(b, fu, vline * pw / ph * 1.6), 0.75)
        ink_f = b.math("MAXIMUM", rline, b.math("MULTIPLY", pline, b.math("SUBTRACT", 1.0, lacing)))
        return b.mix(col, lin(ink) + (1.0,), b.math("MULTIPLY", ink_f, 0.92))
    return pat


def scales(ph=0.016, pw=0.016, ink="#2A2622", deep_k=0.5):
    """Fish-scale / round-headed plates (鱼鳞甲) for shoulder guards."""
    def pat(b, col):
        u, v = uv(b)
        rv = b.math("DIVIDE", b.math("MULTIPLY", v, -1.0), ph)
        row = b.math("FLOOR", rv)
        fv = _frac(b, rv)
        uu = b.math("ADD", b.math("DIVIDE", u, pw), b.math("MULTIPLY", row, 0.5))
        fu = _frac(b, uu)
        # rounded bottom edge of each scale: distance to an arc
        dx = b.math("SUBTRACT", fu, 0.5)
        arc = b.math("SUBTRACT", fv, b.math("SUBTRACT", 1.0, b.math("MULTIPLY", b.math("MULTIPLY", dx, dx), 1.6)))
        edge = b.smooth(b.math("ABSOLUTE", arc), 0.10, 0.04)
        shade = b.math("MULTIPLY", b.math("POWER", fv, 2.0), deep_k)
        col = b.mix(col, b.cmul(col, 0.55), shade)
        side = _line(b, fu, 0.05)
        ink_f = b.math("MAXIMUM", edge, b.math("MULTIPLY", side, b.smooth(fv, 0.3, 0.7)))
        return b.mix(col, lin(ink) + (1.0,), b.math("MULTIPLY", ink_f, 0.9))
    return pat


def brocade(period=0.022, width=0.03, motif="#C9A24B", edge="#C9A24B", edge_w=0.0016, size=0.33,
            kind="lozenge", motif2=None):
    """Trim band: gold edge lines and a repeating motif along the band (u along, v across)."""
    def pat(b, col):
        u, v = uv(b)
        su = b.math("DIVIDE", u, period)
        fu = b.math("SUBTRACT", _frac(b, su), 0.5)
        vv = b.math("SUBTRACT", b.math("DIVIDE", v, width), 0.5)
        if kind == "lozenge":
            d = b.math("ADD", b.math("ABSOLUTE", fu), b.math("MULTIPLY", b.math("ABSOLUTE", vv), period / width * 1.0))
            m = b.smooth(d, size, size * 0.8)
            ring = b.smooth(b.math("ABSOLUTE", b.math("SUBTRACT", d, size * 0.5)), 0.06, 0.03)
            m = b.math("SUBTRACT", m, b.math("MULTIPLY", ring, 0.7))
        elif kind == "dots":
            d = b.math("SQRT", b.math("ADD", b.math("MULTIPLY", fu, fu),
                                       b.math("MULTIPLY", b.math("MULTIPLY", vv, vv), (width / period) ** 2)))
            m = b.smooth(d, size * 0.6, size * 0.45)
        else:   # cloud scroll: two offset rings
            d1 = b.math("SQRT", b.math("ADD", b.math("MULTIPLY", b.math("SUBTRACT", fu, 0.15), b.math("SUBTRACT", fu, 0.15)),
                                        b.math("MULTIPLY", b.math("MULTIPLY", vv, vv), (width / period) ** 2)))
            m = b.smooth(b.math("ABSOLUTE", b.math("SUBTRACT", d1, size * 0.6)), 0.07, 0.035)
        col = b.mix(col, lin(motif) + (1.0,), b.math("MULTIPLY", m, 0.95))
        if edge_w > 0:
            ev = b.math("DIVIDE", v, width)
            e = b.math("MAXIMUM", b.smooth(ev, edge_w / width * 2.2, edge_w / width * 1.2),
                       b.smooth(b.math("SUBTRACT", 1.0, ev), edge_w / width * 2.2, edge_w / width * 1.2))
            col = b.mix(col, lin(edge) + (1.0,), b.math("MULTIPLY", e, 0.9))
        return col
    return pat


def roundels(period=0.075, color="#D8B868", alpha=0.35, r=0.26):
    """Scattered flower roundels (团花) in a lighter / gold tone on a robe: six round petals
    round a centre, inside a fine ring."""
    def pat(b, col):
        u, v = uv(b)
        su = b.math("DIVIDE", u, period)
        sv = b.math("DIVIDE", v, period)
        row = b.math("FLOOR", sv)
        fu = b.math("SUBTRACT", _frac(b, b.math("ADD", su, b.math("MULTIPLY", row, 0.5))), 0.5)
        fv = b.math("SUBTRACT", _frac(b, sv), 0.5)
        d = b.math("SQRT", b.math("ADD", b.math("MULTIPLY", fu, fu), b.math("MULTIPLY", fv, fv)))
        ang = b.math("ARCTAN2", fv, fu)
        # petal radius modulated by |cos 3 theta|: six rounded petals
        pr = b.math("MULTIPLY", b.math("ADD", b.math("MULTIPLY", b.math("ABSOLUTE", b.math("COSINE", b.math("MULTIPLY", ang, 3.0))), 0.45), 0.55), r * 0.82)
        petals = b.smooth(b.math("SUBTRACT", d, pr), 0.012, -0.012)
        hole = b.smooth(d, r * 0.16, r * 0.10)
        centre = b.smooth(d, r * 0.13, r * 0.08)
        ring = b.smooth(b.math("ABSOLUTE", b.math("SUBTRACT", d, r * 1.05)), 0.018, 0.008)
        m = b.math("MAXIMUM", b.math("MAXIMUM", b.math("SUBTRACT", petals, hole), centre), ring)
        return b.mix(col, lin(color) + (1.0,), b.math("MULTIPLY", m, alpha))
    return pat


def streaks(freq=180.0, color="#6A645C", alpha=0.45, axis_center=(0.0, 0.0, 0.0), coord="Object",
            warp=0.35, mode="azimuth"):
    """Combed hair streaks: stripes of azimuth around a vertical axis through ``axis_center``
    (object space), or along UV u (``mode='uv'``)."""
    def pat(b, col):
        if mode == "uv":
            u, v = uv(b)
            t = b.math("MULTIPLY", u, freq)
        else:
            s = b.sep(b.coord(coord))
            x = b.math("SUBTRACT", s[0], axis_center[0])
            y = b.math("SUBTRACT", s[1], axis_center[1])
            t = b.math("MULTIPLY", b.math("ARCTAN2", x, y), freq / (2 * math.pi))
        n = b.node("ShaderNodeTexNoise", noise_dimensions="3D")
        n.inputs["Scale"].default_value = 30.0
        n.inputs["Detail"].default_value = 2.0
        b.link(b.coord("Object"), n.inputs["Vector"])
        t = b.math("ADD", t, b.math("MULTIPLY", n.outputs["Fac"], warp * 6))
        st = b.smooth(b.math("SINE", b.math("MULTIPLY", t, 2 * math.pi)), 0.55, 0.98)
        return b.mix(col, lin(color) + (1.0,), b.math("MULTIPLY", st, alpha))
    return pat


def gauze(color="#4A4644", alpha=0.25, period=0.0035):
    """Black gauze (纱): a faint lighter weave."""
    def pat(b, col):
        u, v = uv(b)
        a = b.math("SINE", b.math("MULTIPLY", u, 2 * math.pi / period))
        c = b.math("SINE", b.math("MULTIPLY", v, 2 * math.pi / period))
        m = b.math("MULTIPLY", b.smooth(b.math("MULTIPLY", a, c), 0.3, 0.9), alpha)
        return b.mix(col, lin(color) + (1.0,), m)
    return pat


def stripes_uv(freq=120.0, color="#2A1E1A", alpha=0.5, along="u", warp=2.0):
    """Fine strands along UV (plume tassels, fur)."""
    def pat(b, col):
        u, v = uv(b)
        t = b.math("MULTIPLY", u if along == "u" else v, freq)
        n = b.node("ShaderNodeTexNoise", noise_dimensions="3D")
        n.inputs["Scale"].default_value = 40.0
        b.link(b.coord("Object"), n.inputs["Vector"])
        t = b.math("ADD", t, b.math("MULTIPLY", n.outputs["Fac"], warp))
        st = b.smooth(b.math("SINE", b.math("MULTIPLY", t, 2 * math.pi)), 0.6, 0.98)
        return b.mix(col, lin(color) + (1.0,), b.math("MULTIPLY", st, alpha))
    return pat


def combine(*pats):
    def pat(b, col):
        for p in pats:
            col = p(b, col)
        return col
    return pat
