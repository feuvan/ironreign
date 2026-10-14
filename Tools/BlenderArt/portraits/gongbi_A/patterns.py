"""Painted textile and armour motifs as shader node functions (paint data, no lighting).

Each function takes the node builder, the current paint colour socket and returns a new paint
socket.  UV conventions: torso shells u = angle / 2pi, v = height in metres; band meshes
u = angle / 2pi, v = 0..1 across the band.
"""

import math

import shade


def _cells(nb, rep_u, rep_v, stagger=True, uv=None):
    uv = uv or nb.sep(nb.uv())
    U = nb.math("MULTIPLY", uv[0], rep_u)
    V = nb.math("MULTIPLY", uv[1], rep_v)
    row = nb.math("FLOOR", V)
    if stagger:
        U = nb.math("ADD", U, nb.math("MULTIPLY", nb.math("MODULO", row, 2.0), 0.5))
    cu = nb.math("SUBTRACT", nb.math("FRACT", U), 0.5)
    cv = nb.math("SUBTRACT", nb.math("FRACT", V), 0.5)
    return cu, cv, row, U, V


def roundels(paint, motif="gold", rep_u=22.0, rep_v=16.0, r=0.3, petals=6, amount=0.85,
             ring=0.06):
    """团花 roundels: a small flower in a ring, staggered rows."""
    def f(nb, p):
        cu, cv, _, _, _ = _cells(nb, rep_u, rep_v)
        d = nb.math("SQRT", nb.math("ADD", nb.math("MULTIPLY", cu, cu), nb.math("MULTIPLY", cv, cv)))
        th = nb.math("ARCTAN2", cv, cu)
        pr = nb.math("MULTIPLY", nb.math("ADD", 0.62, nb.math("MULTIPLY", nb.math(
            "COSINE", nb.math("MULTIPLY", th, float(petals))), 0.28)), r * 0.72)
        flower = nb.math("SUBTRACT", 1.0, nb.smooth(nb.math("SUBTRACT", d, pr), -0.015, 0.015))
        rg = nb.math("SUBTRACT", 1.0, nb.smooth(nb.math("ABSOLUTE", nb.math("SUBTRACT", d, r)),
                                                ring * 0.5, ring))
        dot = nb.math("SUBTRACT", 1.0, nb.smooth(d, r * 0.12, r * 0.2))
        m = nb.math("MAXIMUM", nb.math("MAXIMUM", flower, rg), 0.0)
        m = nb.math("MULTIPLY", m, amount)
        out = nb.mix(m, p, shade.rgb(motif))
        return nb.mix(nb.math("MULTIPLY", dot, amount), out, shade.rgb(paint))
    return f


def scattered_flowers(motif="gold", rep_u=30.0, rep_v=22.0, r=0.22, amount=0.7):
    """Small scattered blossoms (碎花) for ladies' silks."""
    def f(nb, p):
        cu, cv, _, _, _ = _cells(nb, rep_u, rep_v)
        d = nb.math("SQRT", nb.math("ADD", nb.math("MULTIPLY", cu, cu), nb.math("MULTIPLY", cv, cv)))
        th = nb.math("ARCTAN2", cv, cu)
        pr = nb.math("MULTIPLY", nb.math("ADD", 0.55, nb.math("MULTIPLY", nb.math(
            "COSINE", nb.math("MULTIPLY", th, 5.0)), 0.45)), r)
        m = nb.math("SUBTRACT", 1.0, nb.smooth(nb.math("SUBTRACT", d, pr), -0.02, 0.02))
        return nb.mix(nb.math("MULTIPLY", m, amount), p, shade.rgb(motif))
    return f


def band(edge="gold", motif="gold", rep=60.0, amount=0.9, edge_w=0.09, kind="dots"):
    """Collar / hem band: two fine gilt edge lines and a repeating motif between them."""
    def f(nb, p):
        uv = nb.sep(nb.uv())
        v = uv[1]
        e1 = nb.math("SUBTRACT", 1.0, nb.smooth(nb.math("ABSOLUTE", nb.math("SUBTRACT", v, edge_w)),
                                                0.012, 0.03))
        e2 = nb.math("SUBTRACT", 1.0, nb.smooth(nb.math("ABSOLUTE", nb.math(
            "SUBTRACT", v, 1.0 - edge_w)), 0.012, 0.03))
        out = nb.mix(nb.math("MULTIPLY", nb.math("MAXIMUM", e1, e2), amount), p, shade.rgb(edge))
        U = nb.math("MULTIPLY", uv[0], rep)
        cu = nb.math("SUBTRACT", nb.math("FRACT", U), 0.5)
        cv = nb.math("SUBTRACT", v, 0.5)
        if kind == "dots":
            d = nb.math("SQRT", nb.math("ADD", nb.math("MULTIPLY", cu, cu),
                                        nb.math("MULTIPLY", nb.math("MULTIPLY", cv, 2.2),
                                                nb.math("MULTIPLY", cv, 2.2))))
            m = nb.math("SUBTRACT", 1.0, nb.smooth(d, 0.16, 0.24))
        else:  # diamonds lattice
            d = nb.math("ADD", nb.math("ABSOLUTE", cu), nb.math("ABSOLUTE", nb.math("MULTIPLY", cv, 1.6)))
            m = nb.math("SUBTRACT", 1.0, nb.smooth(nb.math("ABSOLUTE", nb.math("SUBTRACT", d, 0.32)),
                                                    0.03, 0.07))
        return nb.mix(nb.math("MULTIPLY", m, amount), out, shade.rgb(motif))
    return f


def lamellar(plate="iron", plate_light="iron_light", line="ink_dense", lacing="cinnabar",
             rivet="gold", rep_u=70.0, rows_per_m=34.0, lace=True):
    """札甲 lamellar: staggered rows of small round-topped plates, each washed lighter at its
    top edge (晕染), outlined in ink, with a red lacing line under each row and gilt rivets."""
    def f(nb, p):
        cu, cv, row, U, V = _cells(nb, rep_u, rows_per_m)
        # v inside the plate: 0 top .. 1 bottom (V grows upward with z -> flip)
        pv = nb.math("SUBTRACT", 0.5, cv)
        # rounded plate top
        top = nb.math("MULTIPLY", nb.math("MULTIPLY", cu, cu), 0.9)
        inside_v = nb.math("SUBTRACT", pv, top)
        grad = nb.smooth(inside_v, 0.0, 0.9)
        col = nb.mix(grad, shade.rgb(plate_light), shade.rgb(plate))
        # outlines: plate sides and rounded tops
        side = nb.smooth(nb.math("SUBTRACT", 0.5, nb.math("ABSOLUTE", cu)), 0.0, 0.06)
        topl = nb.smooth(inside_v, 0.0, 0.06)
        edge = nb.math("SUBTRACT", 1.0, nb.math("MULTIPLY", side, topl))
        col = nb.mix(nb.math("MULTIPLY", edge, 0.62), col, shade.rgb(line))
        if lace:
            lv = nb.math("SUBTRACT", 1.0, nb.smooth(nb.math("ABSOLUTE", nb.math("SUBTRACT", pv, 0.8)),
                                                    0.02, 0.06))
            lu = nb.smooth(nb.math("ABSOLUTE", nb.math("SINE", nb.math("MULTIPLY", U, 2 * math.pi))),
                           0.2, 0.6)
            col = nb.mix(nb.math("MULTIPLY", lv, lu), col, shade.rgb(lacing))
        if rivet:
            d = nb.math("SQRT", nb.math("ADD", nb.math("MULTIPLY", cu, cu), nb.math(
                "MULTIPLY", nb.math("SUBTRACT", pv, 0.22), nb.math("SUBTRACT", pv, 0.22))))
            r = nb.math("SUBTRACT", 1.0, nb.smooth(d, 0.05, 0.09))
            col = nb.mix(nb.math("MULTIPLY", r, 0.8), col, shade.rgb(rivet))
        return col
    return f


def scales(plate="iron", plate_light="iron_light", line="ink_dense", rep_u=60.0, rows_per_m=40.0,
           rim="gold", rim_amt=0.0):
    """鱼鳞甲 fish-scale armour: staggered round scales, overlapping downward."""
    def f(nb, p):
        cu, cv, row, U, V = _cells(nb, rep_u, rows_per_m)
        # circle centred at the cell top: scales hang down
        cy = nb.math("SUBTRACT", cv, -0.1)
        d = nb.math("SQRT", nb.math("ADD", nb.math("MULTIPLY", cu, cu), nb.math("MULTIPLY", cy, cy)))
        g = nb.smooth(d, 0.1, 0.62)
        col = nb.mix(g, shade.rgb(plate_light), shade.rgb(plate))
        ring = nb.math("SUBTRACT", 1.0, nb.smooth(nb.math("ABSOLUTE", nb.math("SUBTRACT", d, 0.6)),
                                                  0.03, 0.08))
        col = nb.mix(nb.math("MULTIPLY", ring, 0.9), col, shade.rgb(line))
        return col
    return f


def stripes_v(color, rep=40.0, width=0.08, amount=0.5):
    def f(nb, p):
        uv = nb.sep(nb.uv())
        s = nb.math("ABSOLUTE", nb.math("SUBTRACT", nb.math("FRACT", nb.math("MULTIPLY", uv[0], rep)),
                                        0.5))
        m = nb.math("SUBTRACT", 1.0, nb.smooth(s, width * 0.5, width))
        return nb.mix(nb.math("MULTIPLY", m, amount), p, shade.rgb(color))
    return f


def chain(*fs):
    def f(nb, p):
        for g in fs:
            p = g(nb, p)
        return p
    return f


def kasaya(seam="#7A4A20", rep_u=9.0, rep_v=7.0, amount=0.8):
    """袈裟 patchwork (田相): rectangles of cloth outlined by darker seams."""
    def f(nb, p):
        cu, cv, row, U, V = _cells(nb, rep_u, rep_v, stagger=False)
        su = nb.smooth(nb.math("SUBTRACT", 0.5, nb.math("ABSOLUTE", cu)), 0.0, 0.04)
        sv = nb.smooth(nb.math("SUBTRACT", 0.5, nb.math("ABSOLUTE", cv)), 0.0, 0.05)
        m = nb.math("SUBTRACT", 1.0, nb.math("MULTIPLY", su, sv))
        return nb.mix(nb.math("MULTIPLY", m, amount), p, shade.rgb(seam))
    return f
