"""Art-directed "painterly" materials for Cycles (approach B).

The painter's tricks are built into the shaders instead of being faked afterwards:

* **colour zones** - skin is blocked in like a portrait painter would (yellower forehead, ruddy
  cheeks / nose / ears, blue-grey beard shadow, darker lids, cool neck) from the per-vertex zone
  masks of :mod:`zones`;
* **painted terminator** - the albedo is pushed warm and saturated in a band around the key
  light's terminator and cooled on the shadow side (N.L against the known key direction), which is
  what makes painted skin glow instead of looking grey-CG;
* **controlled specular** - specular only where a painter puts highlights (forehead, nose bridge,
  cheekbone, lower lip), broken up by noise; rough elsewhere;
* **AOVs** - ``accent`` (where a painter puts ink-dark accents: lash line, lip parting, nostril,
  deep folds), ``skin`` (skin mask) and ``detail`` (eyes / face, kept crisp in the compositor).
"""

import math

import bpy
from mathutils import Vector

from .nodes import NB, lin, material, output, principled, sock


def _key_dot(nb, key_dir, normal=None):
    g = nb.node("ShaderNodeNewGeometry")
    n = normal if normal is not None else g.outputs["Normal"]
    kv = nb.node("ShaderNodeCombineXYZ", inputs={"X": key_dir[0], "Y": key_dir[1], "Z": key_dir[2]})
    return nb.vmath("DOT_PRODUCT", n, kv.outputs[0])


def painter_tint(nb, col, key_dir, warm="#FFB08A", cool="#7F93B8", band=(-0.05, 0.12, 0.35),
                 warm_amt=0.35, cool_amt=0.35, lit="#FFF4E6", lit_amt=0.0):
    """Multiply ``col`` by a key-relative ramp: cool shadow side, warm saturated terminator band,
    optional warm-white lit side."""
    d = _key_dot(nb, key_dir)
    a, b, c = band
    # terminator band weight (peaks between a..b, fades by c)
    up = nb.maprange(d, a - 0.12, b, 0.0, 1.0, interp="SMOOTHSTEP")
    down = nb.maprange(d, b, c, 1.0, 0.0, interp="SMOOTHSTEP")
    term = nb.math("MULTIPLY", up, down)
    shadow = nb.maprange(d, a, a - 0.25, 0.0, 1.0, interp="SMOOTHSTEP")
    litw = nb.maprange(d, c, 0.85, 0.0, 1.0, interp="SMOOTHSTEP")
    w_t = nb.math("MULTIPLY", term, warm_amt)
    w_s = nb.math("MULTIPLY", shadow, cool_amt)
    out = nb.mix(col, nb.mix(col, warm, 1.0, blend="MULTIPLY"), w_t)
    out = nb.mix(out, nb.mix(out, cool, 1.0, blend="MULTIPLY"), w_s)
    if lit_amt > 0:
        out = nb.mix(out, nb.mix(out, lit, 1.0, blend="MULTIPLY"), nb.math("MULTIPLY", litw, lit_amt))
    return out, d


def skin(ident, key_dir, name="Skin"):
    m, nb = material(name)
    z = lambda k: nb.attr("z_" + k)
    rest = nb.attr("rest", out="Vector")
    tone = ident.skin_tone
    # base albedo (linear): ivory .. warm tan; East Asian skin = yellow-olive undertone
    pale = (0.50, 0.33, 0.23)
    tan = (0.30, 0.15, 0.08)
    base = tuple(p + (t - p) * tone for p, t in zip(pale, tan))
    w = ident.weathered
    base = (base[0] * (1 - 0.12 * w), base[1] * (1 - 0.18 * w), base[2] * (1 - 0.22 * w))
    col = nb.node("ShaderNodeRGB").outputs[0]
    col.default_value = (*base, 1.0)
    # large painterly mottling (value + hue), in rest space
    mott = nb.noise(nb.vmath("SCALE", rest, scale=1.0), scale=28.0, detail=3.0, rough=0.55)
    mott_c = nb.ramp(mott, [(0.3, (0.92, 0.95, 1.0)), (0.5, (1.0, 1.0, 1.0)), (0.7, (1.06, 0.97, 0.92))])
    col = nb.mix(col, mott_c, 1.0, blend="MULTIPLY")
    # zones
    ruddy = ident.skin_ruddy + 0.35 * w
    col = nb.mix(col, (0.62, 0.40, 0.22), nb.math("MULTIPLY", z("forehead"), 0.25))       # yellower
    col = nb.mix(col, (0.55, 0.17, 0.12), nb.math("MULTIPLY", z("cheek"), 0.30 * ruddy))   # rosy cheek
    col = nb.mix(col, (0.55, 0.16, 0.11), nb.math("MULTIPLY", z("nose_tip"), 0.45 * ruddy))
    col = nb.mix(col, (0.55, 0.15, 0.10), nb.math("MULTIPLY", z("ears"), 0.45 * ruddy + 0.1))
    col = nb.mix(col, (0.30, 0.15, 0.13), nb.math("MULTIPLY", z("eyebag"), 0.30 + 0.3 * ident.wrinkles))
    col = nb.mix(col, (0.36, 0.19, 0.14), nb.math("MULTIPLY", z("lid"), 0.45))
    col = nb.mix(col, (0.30, 0.22, 0.18), nb.math("MULTIPLY", z("neck"), 0.25))
    if ident.beard_shadow > 0:
        bs = nb.math("MULTIPLY", nb.math("MAXIMUM", z("beard"), z("moustache")), ident.beard_shadow)
        col = nb.mix(col, (0.22, 0.20, 0.20), bs)
    # hair-root masses (dark under brows / scalp / beard so gaps between strands read as hair)
    mel = ident.hair_melanin
    hc = (0.012 + 0.10 * (1 - mel), 0.009 + 0.07 * (1 - mel), 0.007 + 0.05 * (1 - mel))
    gc = (0.30, 0.29, 0.28)
    hcol = tuple(h + (g - h) * ident.grey * 0.6 for h, g in zip(hc, gc))
    if ident.brow_paint > 0:
        bm = brow_shape(nb, rest, female=(ident.brow_mask == "brow_f"), thick=ident.brow_thick,
                        angle=ident.brow_angle)
        col = nb.mix(col, hcol, nb.math("MULTIPLY", bm, ident.brow_paint))
    if ident.scalp_paint > 0:
        col = nb.mix(col, hcol, nb.math("MULTIPLY", z(ident.scalp_mask), ident.scalp_paint))
    if ident.beard_paint > 0:
        col = nb.mix(col, hcol, nb.math("MULTIPLY", nb.math("MAXIMUM", z("beard"), z("moustache")),
                                        ident.beard_paint))
    # lips
    lipc = lin(ident.lip_color)
    lipmix = 0.55 + 0.35 * ident.makeup
    col = nb.mix(col, lipc, nb.math("MULTIPLY", z("lips"), lipmix))
    if ident.makeup > 0:
        mk = ident.makeup
        col = nb.mix(col, (0.62, 0.20, 0.17), nb.math("MULTIPLY", z("cheek"), 0.35 * mk))
        col = nb.mix(col, (0.28, 0.12, 0.10), nb.math("MULTIPLY", z("lid"), 0.4 * mk))
        col = nb.mix(col, (0.70, 0.52, 0.42), nb.math("MULTIPLY", z("forehead"), 0.25 * mk))
    # ---- wrinkles / creases (height field in rest space, metres)
    wr = ident.wrinkles
    height = nb.math("MULTIPLY", nb.noise(rest, scale=900.0, detail=1.0, rough=0.5), 0.15)  # pores
    sep = nb.separate(rest)
    if wr > 0:
        warp = nb.noise(rest, scale=40.0, detail=2.0)
        fz = nb.math("ADD", nb.math("MULTIPLY", sep[2], 520.0), nb.math("MULTIPLY", warp, 3.5))
        lines = nb.math("POWER", nb.math("ABSOLUTE", nb.math("SINE", fz)), 0.35)
        brk = nb.maprange(nb.noise(rest, scale=60.0, detail=1.0), 0.35, 0.6, 0.0, 1.0)
        fl = nb.math("MULTIPLY", nb.math("MULTIPLY", lines, z("forehead")), nb.math("MULTIPLY", brk, wr))
        height = nb.math("ADD", height, nb.math("MULTIPLY", fl, 0.9))
        # crow's feet: radial lines around the outer eye corner
        crow_ang = nb.math("ARCTAN2", sep[2], nb.math("ABSOLUTE", sep[0]))
        cf = nb.math("POWER", nb.math("ABSOLUTE", nb.math("SINE", nb.math("MULTIPLY", crow_ang, 70.0))), 0.4)
        height = nb.math("ADD", height, nb.math("MULTIPLY", nb.math("MULTIPLY", cf, z("crows")), 0.6 * wr))
        # folds: nasolabial, under-eye, marionette, glabella (grooves = negative height)
        fold = nb.math("ADD", nb.math("MULTIPLY", z("nasolabial"), 1.0),
                       nb.math("MULTIPLY", z("undereye"), 0.7))
        fold = nb.math("ADD", fold, nb.math("MULTIPLY", z("marionette"), 0.6))
        height = nb.math("SUBTRACT", height, nb.math("MULTIPLY", fold, 1.6 * wr))
        # crease colour: warm dark in the grooves
        col = nb.mix(col, (0.24, 0.11, 0.08), nb.math("MULTIPLY", fold, 0.30 * wr))
    gl = ident.sliders.get("_frown", 0.0)
    if gl > 0:
        gx = nb.math("ABSOLUTE", nb.math("SINE", nb.math("MULTIPLY", sep[0], 900.0)))
        height = nb.math("SUBTRACT", height, nb.math("MULTIPLY", nb.math("MULTIPLY", gx, z("glabella")), gl))
    bump = nb.bump(height, strength=0.25 + 0.25 * wr, distance=0.0006)
    # ---- painterly terminator
    col, kd = painter_tint(nb, col, key_dir, warm=(1.30, 0.86, 0.70), cool=(0.80, 0.90, 1.18),
                           warm_amt=0.8, cool_amt=0.6)
    # ---- controlled specular / roughness
    shine = nb.math("ADD", nb.math("MULTIPLY", z("nose"), 0.6), nb.math("MULTIPLY", z("forehead"), 0.45))
    shine = nb.math("ADD", shine, nb.math("MULTIPLY", z("cheekbone"), 0.4))
    shine = nb.math("ADD", shine, nb.math("MULTIPLY", z("lips"), 0.5))
    brk = nb.maprange(nb.noise(rest, scale=140.0, detail=2.0), 0.3, 0.7, 0.55, 1.0)
    shine = nb.math("MULTIPLY", nb.math("MINIMUM", shine, 1.0), brk)
    spec = nb.maprange(shine, 0.0, 1.0, 0.18, 0.55)
    rough = nb.maprange(shine, 0.0, 1.0, 0.62, 0.38)
    rough = nb.math("ADD", rough, 0.08 * w)
    p = principled(nb, Base_Color=col, Roughness=rough, Subsurface_Weight=0.35,
                   Subsurface_Radius=(1.0, 0.38, 0.22), Subsurface_Scale=0.0045,
                   Specular_IOR_Level=spec, Coat_Weight=nb.math("MULTIPLY", z("lips"), 0.4 + 0.4 * ident.makeup),
                   Coat_Roughness=0.25, Normal=bump)
    p.subsurface_method = "BURLEY"
    output(nb, p)
    # AOVs: accents where a painter puts dark strokes
    acc = nb.math("MAXIMUM", nb.math("MULTIPLY", z("lash"), 1.0), 0.0)
    nb.aov("accent", acc)
    nb.aov("skin", 1.0)
    nb.aov("detail", 1.0)
    return m


def brow_shape(nb, rest, female=False, thick=1.0, angle=0.0, soft=0.0009):
    """Crisp painted eyebrow evaluated per shading point from the rest position (metres, base
    mesh): an arched centre line and a tapering half-width, plus slanted hair strokes."""
    sep = nb.separate(rest)
    ax = nb.math("ABSOLUTE", sep[0])
    u = nb.maprange(ax, 0.0, 0.07, 0.0, 1.0)
    if female:
        cl = [(0.0, 0.36), (0.13, 0.42), (0.29, 0.60), (0.51, 0.72), (0.71, 0.67), (0.92, 0.44), (1.0, 0.33)]
        hw = [(0.0, 0.0), (0.12, 0.55), (0.24, 0.75), (0.57, 0.50), (0.90, 0.12), (1.0, 0.0)]
        hmax = 0.0034
    else:
        cl = [(0.0, 0.30), (0.13, 0.35), (0.29, 0.62), (0.51, 0.80), (0.71, 0.74), (0.92, 0.40), (1.0, 0.30)]
        hw = [(0.0, 0.0), (0.11, 0.85), (0.28, 1.0), (0.64, 0.75), (0.92, 0.25), (1.0, 0.0)]
        hmax = 0.0050
    cy = nb.maprange(nb.fcurve(u, cl), 0.0, 1.0, 0.734 - (0.002 if female else 0.0), 0.754 - (0.002 if female else 0.0))
    cy = nb.math("ADD", cy, nb.math("MULTIPLY", nb.math("SUBTRACT", ax, 0.02), angle * 0.12))
    half = nb.math("MULTIPLY", nb.fcurve(u, hw), hmax * thick)
    d = nb.math("ABSOLUTE", nb.math("SUBTRACT", sep[2], cy))
    m = nb.maprange(nb.math("SUBTRACT", d, half), soft, -soft, 0.0, 1.0, interp="SMOOTHSTEP")
    front = nb.maprange(sep[1], -0.10, -0.125, 0.0, 1.0)
    m = nb.math("MULTIPLY", m, front)
    # slanted hair strokes inside the brow (lighter gaps): hairs lean laterally-up
    st = nb.math("SINE", nb.math("ADD", nb.math("MULTIPLY", ax, 2600.0), nb.math("MULTIPLY", sep[2], 1500.0)))
    strokes = nb.maprange(st, -1.0, 1.0, 0.72, 1.0)
    return nb.math("MULTIPLY", m, strokes)


def eyes(ident, name="Eye", tex_path=None):
    m, nb = material(name)
    img = bpy.data.images.load(tex_path, check_existing=True)
    tx = nb.node("ShaderNodeTexImage", image=img, interpolation="Cubic")
    uv = nb.node("ShaderNodeTexCoord")   # (a named UVMap node renders black on these meshes)
    nb.set(tx.inputs[0], uv.outputs["UV"])
    c = tx.outputs["Color"]
    # iris detection: the MH iris is red-brown, the sclera near-white
    hsv = nb.node("ShaderNodeSeparateColor", mode="HSV")
    nb.set(hsv.inputs[0], c)
    sat = hsv.outputs[1]
    iris = nb.maprange(sat, 0.25, 0.5, 0.0, 1.0)
    ec = lin(ident.eye_color)
    iris_col = nb.mix(nb.mix(c, ec, 0.82), (0.0, 0.0, 0.0), nb.maprange(hsv.outputs[2], 0.25, 0.08, 0.0, 1.0))
    sclera = nb.mix(c, (0.62, 0.55, 0.48), 0.55)
    col = nb.mix(sclera, iris_col, iris)
    p = principled(nb, Base_Color=col, Roughness=0.35, Specular_IOR_Level=0.3, Coat_Weight=1.0,
                   Coat_Roughness=0.02, Coat_IOR=1.38, Subsurface_Weight=0.0)
    output(nb, p)
    nb.aov("detail", 1.0)
    nb.aov("eye", 1.0)
    return m


def cornea(name="Cornea", catch_dir=None, catch_size=0.9965, catch_strength=6.0):
    """Clear shell in front of the iris: transparent + sharp reflection, plus a *painter's
    catchlight*: an emissive spot where the mirror direction points at ``catch_dir`` (a virtual
    window up-left of the camera), so every portrait gets the same crisp highlight in both eyes
    whatever the key light does."""
    m, nb = material(name)
    tr = nb.node("ShaderNodeBsdfTransparent")
    gl = nb.node("ShaderNodeBsdfGlossy", inputs={"Roughness": 0.03, "Color": (1, 1, 1, 1)})
    fr = nb.node("ShaderNodeFresnel", inputs={"IOR": 1.6})
    mix = nb.node("ShaderNodeMixShader")
    nb.set(mix.inputs[0], nb.math("ADD", nb.math("MULTIPLY", fr.outputs[0], 0.8), 0.06))
    nb.set(mix.inputs[1], tr.outputs[0])
    nb.set(mix.inputs[2], gl.outputs[0])
    sh = mix.outputs[0]
    if catch_dir is not None:
        g = nb.node("ShaderNodeNewGeometry")
        I = g.outputs["Incoming"]
        N = g.outputs["Normal"]
        ndi = nb.vmath("DOT_PRODUCT", N, I)
        R = nb.vmath("SUBTRACT", nb.vmath("SCALE", N, scale=2.0), I)
        sc = nb.node("ShaderNodeVectorMath", operation="SCALE")
        nb.set(sc.inputs[0], N)
        nb.set(sc.inputs["Scale"], nb.math("MULTIPLY", ndi, 2.0))
        R = nb.vmath("SUBTRACT", sc.outputs[0], I)
        cd = nb.node("ShaderNodeCombineXYZ", inputs={"X": catch_dir[0], "Y": catch_dir[1], "Z": catch_dir[2]})
        dd = nb.vmath("DOT_PRODUCT", nb.vmath("NORMALIZE", R), cd.outputs[0])
        spot = nb.maprange(dd, catch_size, catch_size + 0.0025, 0.0, 1.0, interp="SMOOTHSTEP")
        em = nb.node("ShaderNodeEmission", inputs={"Color": (1.0, 0.96, 0.9, 1.0)})
        nb.set(em.inputs["Strength"], nb.math("MULTIPLY", spot, catch_strength))
        add = nb.node("ShaderNodeAddShader")
        nb.set(add.inputs[0], sh)
        nb.set(add.inputs[1], em.outputs[0])
        sh = add.outputs[0]
    output(nb, sh)
    nb.aov("detail", 1.0)
    nb.aov("eye", 1.0)
    return m


# ---------------------------------------------------------------------------------------------
# costume materials
# ---------------------------------------------------------------------------------------------
def painted_strokes(nb, col, amount=0.08, scale=60.0, stretch=(1.0, 1.0, 7.0), hue=0.015):
    """Hand-painted value/hue variation: noise stretched along ``stretch`` (object space) so it
    reads as brush strokes, not as CG grime."""
    obj = nb.node("ShaderNodeTexCoord").outputs["Object"]
    v = nb.node("ShaderNodeMapping")
    nb.set(v.inputs["Vector"], obj)
    v.inputs["Scale"].default_value = (scale / stretch[0], scale / stretch[1], scale / stretch[2])
    n = nb.noise(v.outputs[0], scale=1.0, detail=3.0, rough=0.6, distortion=0.4)
    val = nb.maprange(n, 0.3, 0.7, 1.0 - amount, 1.0 + amount)
    return nb.hsv(col, h=nb.maprange(n, 0.3, 0.7, 0.5 - hue, 0.5 + hue), s=1.0, v=val)


def _edge_from_uv(nb, width=0.08):
    uv = nb.node("ShaderNodeTexCoord").outputs["UV"]
    s = nb.separate(uv)
    du = nb.math("MINIMUM", s[0], nb.math("SUBTRACT", 1.0, s[0]))
    dv = nb.math("MINIMUM", s[1], nb.math("SUBTRACT", 1.0, s[1]))
    e = nb.math("MINIMUM", du, dv)
    return nb.maprange(e, width, 0.0, 0.0, 1.0, interp="SMOOTHSTEP"), s


def iron_plate(name="IronPlate", color=(0.045, 0.05, 0.058), lacing=(0.30, 0.025, 0.018),
               rough=0.38, key_dir=None, edge_bright=0.35, lace=True, rivet=True, inlay=None):
    """Lamellar plate: dark blued iron, polished worn edges, two laced holes near the top with
    red cord, a rivet, grime in the middle; per-plate variation from ``plate_rand``."""
    m, nb = material(name)
    edge, s = _edge_from_uv(nb, 0.12)
    pr = nb.attr("plate_rand")
    obj = nb.node("ShaderNodeTexCoord").outputs["Object"]
    grime = nb.noise(obj, scale=60.0, detail=3.0)
    base = nb.mix(color, (color[0] * 1.6, color[1] * 1.5, color[2] * 1.35), nb.math("MULTIPLY", pr, 0.6))
    base = nb.mix(base, (0.055, 0.035, 0.022), nb.maprange(grime, 0.45, 0.75, 0.0, 0.5))   # rust/grime
    base = nb.mix(base, (0.16, 0.16, 0.17), nb.math("MULTIPLY", edge, edge_bright))          # worn edges
    base = painted_strokes(nb, base, amount=0.18, scale=70.0, stretch=(6.0, 6.0, 1.0), hue=0.03)
    r = nb.mixf(rough + 0.1, rough - 0.12, edge)
    r = nb.math("ADD", r, nb.math("MULTIPLY", nb.math("SUBTRACT", grime, 0.5), 0.2))
    metal = 0.92
    cord = 0.0
    if lace:
        # two lacing holes with cord near the top of the plate
        u, v = s[0], s[1]
        d1 = nb.math("ADD", nb.math("POWER", nb.math("SUBTRACT", u, 0.3), 2.0),
                     nb.math("POWER", nb.math("MULTIPLY", nb.math("SUBTRACT", v, 0.82), 0.6), 2.0))
        d2 = nb.math("ADD", nb.math("POWER", nb.math("SUBTRACT", u, 0.7), 2.0),
                     nb.math("POWER", nb.math("MULTIPLY", nb.math("SUBTRACT", v, 0.82), 0.6), 2.0))
        dd = nb.math("MINIMUM", d1, d2)
        cord = nb.maprange(dd, 0.006, 0.003, 0.0, 1.0)
        # horizontal stitch between the holes
        st = nb.math("MULTIPLY", nb.maprange(nb.math("ABSOLUTE", nb.math("SUBTRACT", v, 0.82)), 0.035, 0.02, 0.0, 1.0),
                     nb.maprange(nb.math("ABSOLUTE", nb.math("SUBTRACT", u, 0.5)), 0.22, 0.18, 0.0, 1.0))
        cord = nb.math("MAXIMUM", cord, st)
        base = nb.mix(base, lacing, cord)
        metal = nb.mixf(0.92, 0.0, cord)
        r = nb.mixf(r, 0.65, cord)
    bump_h = nb.math("ADD", nb.math("MULTIPLY", grime, 0.3), nb.math("MULTIPLY", cord, 0.6) if lace else 0.0)
    if rivet:
        u, v = s[0], s[1]
        dr = nb.math("ADD", nb.math("POWER", nb.math("SUBTRACT", u, 0.5), 2.0),
                     nb.math("POWER", nb.math("MULTIPLY", nb.math("SUBTRACT", v, 0.3), 0.5), 2.0))
        rv = nb.maprange(dr, 0.01, 0.0, 0.0, 1.0, interp="SMOOTHSTEP")
        bump_h = nb.math("ADD", bump_h, nb.math("MULTIPLY", rv, 1.5))
        base = nb.mix(base, (0.35, 0.25, 0.12), nb.math("MULTIPLY", rv, 0.8))
    if inlay is not None:
        # gold scroll inlay in a band (UV v range) - helmet bowls, cuirass rims
        uvv = nb.node("ShaderNodeTexCoord").outputs["UV"]
        sp2 = nb.separate(uvv)
        v0, v1 = inlay.get("band", (0.06, 0.30))
        band = nb.math("MULTIPLY", nb.maprange(sp2[1], v0, v0 + 0.02, 0.0, 1.0), nb.maprange(sp2[1], v1, v1 - 0.02, 0.0, 1.0))
        w = nb.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="X")
        nb.set(w.inputs["Vector"], nb.combine(nb.math("MULTIPLY", sp2[0], inlay.get("repeat", 24.0)),
                                              nb.math("MULTIPLY", sp2[1], 6.0), 0.0))
        w.inputs["Scale"].default_value = 1.0
        w.inputs["Distortion"].default_value = 9.0
        w.inputs["Detail"].default_value = 2.0
        pat = nb.math("MULTIPLY", nb.maprange(w.outputs["Fac"], 0.62, 0.72, 0.0, 1.0), band)
        edge_l = nb.math("MULTIPLY", nb.maprange(nb.math("ABSOLUTE", nb.math("SUBTRACT", sp2[1], v0 + 0.01)), 0.006, 0.0, 0.0, 1.0), 1.0)
        edge_h = nb.maprange(nb.math("ABSOLUTE", nb.math("SUBTRACT", sp2[1], v1 - 0.01)), 0.006, 0.0, 0.0, 1.0)
        pat = nb.math("MAXIMUM", pat, nb.math("MAXIMUM", edge_l, edge_h))
        base = nb.mix(base, (0.62, 0.40, 0.13), pat)
        metal = 1.0
        r = nb.mixf(r, 0.25, pat)
        bump_h = nb.math("ADD", bump_h, nb.math("MULTIPLY", pat, 0.5))
    bump = nb.bump(bump_h, strength=0.4, distance=0.0008)
    p = principled(nb, Base_Color=base, Metallic=metal, Roughness=r, Normal=bump,
                   Specular_IOR_Level=0.5)
    output(nb, p)
    nb.aov("costume", 1.0)
    nb.aov("metal", 1.0)
    return m


def metal(name, color=(0.62, 0.38, 0.12), rough=0.3, vary=0.25, scale=80.0, engrave=0.0):
    m, nb = material(name)
    obj = nb.node("ShaderNodeTexCoord").outputs["Object"]
    n = nb.noise(obj, scale=scale, detail=3.0)
    c = nb.mix(color, (color[0] * 0.55, color[1] * 0.5, color[2] * 0.45), nb.maprange(n, 0.4, 0.75, 0.0, vary * 2))
    r = nb.math("ADD", rough, nb.math("MULTIPLY", nb.math("SUBTRACT", n, 0.5), 0.25))
    bump = None
    if engrave > 0:
        uv = nb.node("ShaderNodeTexCoord").outputs["UV"]
        w = nb.node("ShaderNodeTexWave", wave_type="RINGS", rings_direction="SPHERICAL")
        nb.set(w.inputs["Vector"], uv)
        w.inputs["Scale"].default_value = 6.0
        w.inputs["Distortion"].default_value = 6.0
        w.inputs["Detail"].default_value = 3.0
        bump = nb.bump(w.outputs["Fac"], strength=engrave, distance=0.0005)
    p = principled(nb, Base_Color=c, Metallic=1.0, Roughness=r, Normal=bump)
    output(nb, p)
    nb.aov("costume", 1.0)
    nb.aov("metal", 1.0)
    return m


def cloth(name, color, sheen=0.4, rough=0.7, pattern=None, pattern_color=None, pattern_scale=12.0,
          aniso=0.0, key_dir=None, weave=0.15, border=None, border_color=None, border_width=0.18,
          painter=True, spec=0.12):
    """Silk / brocade / linen.  ``pattern``: None, 'cloud' (brocade cloud scrolls), 'diamond',
    'dots'.  ``border``: 'u' or 'v' -> an embroidered band along that UV edge."""
    m, nb = material(name)
    uv = nb.node("ShaderNodeTexCoord").outputs["UV"]
    obj = nb.node("ShaderNodeTexCoord").outputs["Object"]
    base = nb.node("ShaderNodeRGB").outputs[0]
    base.default_value = lin(color)
    col = base
    fold = nb.noise(obj, scale=18.0, detail=2.0)
    col = nb.mix(col, nb.mix(col, (0.6, 0.6, 0.65), 1.0, blend="MULTIPLY"), nb.maprange(fold, 0.3, 0.7, 0.15, 0.0))
    bump_h = nb.math("MULTIPLY", nb.noise(obj, scale=900.0, detail=1.0), weave)
    if pattern:
        pc = lin(pattern_color or "#C9A24A")
        sv = nb.vmath("SCALE", uv, scale=pattern_scale)
        if pattern == "cloud":
            # brocade roundels: a ring + a curl in every tile, alternate rows offset
            sp = nb.separate(sv)
            row = nb.math("FLOOR", sp[1])
            off = nb.math("MULTIPLY", nb.math("MODULO", row, 2.0), 0.5)
            tu = nb.math("SUBTRACT", nb.math("FRACT", nb.math("ADD", sp[0], off)), 0.5)
            tv = nb.math("SUBTRACT", nb.math("FRACT", sp[1]), 0.5)
            r = nb.math("SQRT", nb.math("ADD", nb.math("MULTIPLY", tu, tu), nb.math("MULTIPLY", tv, tv)))
            ring = nb.maprange(nb.math("ABSOLUTE", nb.math("SUBTRACT", r, 0.32)), 0.05, 0.025, 0.0, 1.0)
            ang = nb.math("ARCTAN2", tv, tu)
            curl = nb.maprange(nb.math("ABSOLUTE", nb.math("SUBTRACT", r, nb.math("ADD", 0.08, nb.math("MULTIPLY", ang, 0.025)))),
                               0.035, 0.015, 0.0, 1.0)
            pat = nb.math("MAXIMUM", ring, nb.math("MULTIPLY", curl, nb.maprange(r, 0.26, 0.22, 0.0, 1.0)))
        elif pattern == "diamond":
            sp = nb.separate(sv)
            a = nb.math("ABSOLUTE", nb.math("SINE", nb.math("ADD", sp[0], sp[1])))
            b = nb.math("ABSOLUTE", nb.math("SINE", nb.math("SUBTRACT", sp[0], sp[1])))
            pat = nb.maprange(nb.math("MINIMUM", a, b), 0.12, 0.05, 0.0, 1.0)
        else:
            vo = nb.voronoi(sv, scale=1.0, feature="F1", out="Distance", randomness=0.3)
            pat = nb.maprange(vo, 0.18, 0.12, 0.0, 1.0)
        col = nb.mix(col, pc, nb.math("MULTIPLY", pat, 0.85))
        bump_h = nb.math("ADD", bump_h, nb.math("MULTIPLY", pat, 0.4))
    if border:
        sp = nb.separate(uv)
        coord = sp[1] if border == "v" else sp[0]
        band = nb.maprange(coord, border_width, border_width - 0.03, 0.0, 1.0)
        bc = lin(border_color or "#C9A24A")
        # embroidered meander inside the band
        sv = nb.vmath("SCALE", uv, scale=pattern_scale * 2.5)
        vo = nb.voronoi(sv, scale=1.0, feature="F1", out="Distance")
        emb = nb.maprange(vo, 0.4, 0.25, 0.0, 1.0)
        bcol = nb.mix(nb.mix(col, bc, 0.25), bc, nb.math("MULTIPLY", emb, 0.8))
        col = nb.mix(col, bcol, band)
        bump_h = nb.math("ADD", bump_h, nb.math("MULTIPLY", nb.math("MULTIPLY", band, emb), 0.5))
    col = painted_strokes(nb, col, amount=0.10, scale=45.0, stretch=(1.0, 1.0, 6.0))
    if painter and key_dir is not None:
        col, _ = painter_tint(nb, col, key_dir, warm=(1.18, 0.95, 0.82), cool=(0.85, 0.92, 1.12),
                              warm_amt=0.6, cool_amt=0.5)
    bump = nb.bump(bump_h, strength=0.25, distance=0.0006)
    # sheen tinted by the cloth itself (white sheen turns dark silk into pale felt)
    p = principled(nb, Base_Color=col, Roughness=rough, Sheen_Weight=sheen * 0.35, Sheen_Roughness=0.45,
                   Sheen_Tint=nb.hsv(col, s=1.2, v=2.5), Normal=bump, Anisotropic=aniso,
                   Specular_IOR_Level=spec)
    output(nb, p)
    nb.aov("costume", 1.0)
    return m


def leather(name="Leather", color=(0.09, 0.045, 0.022), rough=0.55):
    m, nb = material(name)
    obj = nb.node("ShaderNodeTexCoord").outputs["Object"]
    n = nb.noise(obj, scale=120.0, detail=4.0)
    c = nb.mix(color, (color[0] * 1.6, color[1] * 1.5, color[2] * 1.4), nb.maprange(n, 0.4, 0.7, 0.0, 1.0))
    bump = nb.bump(nb.noise(obj, scale=600.0, detail=2.0), strength=0.2, distance=0.0005)
    p = principled(nb, Base_Color=c, Roughness=rough, Normal=bump, Specular_IOR_Level=0.4)
    output(nb, p)
    nb.aov("costume", 1.0)
    return m


def costume_materials(key_dir, palette=None):
    pal = dict(iron=(0.040, 0.044, 0.052), bronze=(0.42, 0.24, 0.08), gold=(0.70, 0.47, 0.17),
               lacing=(0.16, 0.018, 0.012), leather=(0.08, 0.04, 0.02))
    pal.update(palette or {})
    return dict(
        iron=iron_plate("IronPlate", pal["iron"], pal["lacing"], key_dir=key_dir),
        iron_plain=iron_plate("IronPlain", pal["iron"], pal["lacing"], key_dir=key_dir, lace=False, rivet=False),
        iron_inlay=iron_plate("IronInlay", pal["iron"], pal["lacing"], key_dir=key_dir, lace=False, rivet=False,
                              inlay=dict(band=(0.30, 0.52), repeat=16.0)),
        bronze=metal("Bronze", pal["bronze"], rough=0.32),
        gold=metal("Gold", pal["gold"], rough=0.25, engrave=0.3),
        leather=leather("Leather", pal["leather"]),
        lacing=cloth("LacingCord", "#6A1E14", sheen=0.3, rough=0.6, painter=False),
    )
