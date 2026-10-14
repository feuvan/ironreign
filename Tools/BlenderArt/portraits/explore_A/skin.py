"""Skin and eye materials for the MakeHuman head (bpy).

The skin reads the head's point attributes (``fc`` face coordinates in inter-pupil units, region
masks ``m_*``) so pigment zones, make-up and age wrinkles land in the right place on every face.
fc axes: x = toward the character's left, y = up, z = forward; origin between the eyes.
"""

import bpy

from nodes import NB, lin

_SKIN_LIGHT = (0.86, 0.68, 0.56)
_SKIN_DARK = (0.66, 0.45, 0.33)


def _lerp3(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def skin_material(idn, name="Skin"):
    """Principled skin with SSS, zone pigments, pores, roughness breakup and age wrinkles."""
    m = bpy.data.materials.new(name)
    nb = NB(m)
    old = max(0.0, min(1.0, (idn.age - 30.0) / 45.0))
    male = not idn.female
    fc = nb.attr("fc", "Vector")
    fx, fy, fz = nb.sep(fc)
    ax = nb.math("ABSOLUTE", fx)
    obj = nb.coord("Object")
    # ------------------------------------------------------------------ base pigment
    base = _lerp3(_SKIN_LIGHT, _SKIN_DARK, idn.skin_tone)
    mott = nb.noise(obj, scale=38.0, detail=4.0, rough=0.6)[0]
    mott2 = nb.noise(obj, scale=140.0, detail=2.0, rough=0.5)[0]
    col = nb.mix(tuple(c * 0.93 for c in base), tuple(min(1, c * 1.06) for c in base),
                 nb.math("ADD", nb.math("MULTIPLY", mott, 0.8), nb.math("MULTIPLY", mott2, 0.2)))
    col = nb.mix(col, (0.80, 0.58, 0.47), nb.math("MULTIPLY", nb.maprange(mott, 0.45, 0.75), 0.25))
    # forehead slightly yellower/lighter; lower face a touch darker
    fore = nb.maprange(fy, 0.35, 0.9)
    col = nb.mix(col, tuple(min(1, c * 1.05) for c in (base[0], base[1] * 1.02, base[2] * 0.95)),
                 nb.math("MULTIPLY", fore, 0.35))
    # flush zones: cheeks, nose, ears, chin, lids
    red = nb.math("MAXIMUM", nb.math("MULTIPLY", nb.attr("m_cheek"), 0.8),
                  nb.math("MAXIMUM", nb.math("MULTIPLY", nb.attr("m_nose"), 0.75),
                          nb.math("MAXIMUM", nb.attr("m_ear"), nb.math("MULTIPLY", nb.attr("m_chin"), 0.4))))
    red = nb.math("MULTIPLY", red, 0.18 + 0.3 * idn.skin_red)
    col = nb.mix(col, (0.78, 0.40, 0.34), red)
    # socket darkening (upper lid crease and under-eye)
    rr = nb.vmath("LENGTH", nb.combine(nb.math("SUBTRACT", ax, 0.5), fy, 0.0), out=1)
    sock = nb.maprange(rr, 0.42, 0.18)
    sock = nb.math("MULTIPLY", sock, 0.30 + 0.25 * old)
    col = nb.mix(col, (0.48, 0.30, 0.26), sock)
    # beard shadow on shaved male skin (lower face)
    if male:
        jaw = nb.math("MULTIPLY", nb.maprange(fy, -0.45, -0.75), nb.maprange(ax, 1.25, 0.95))
        jaw = nb.math("MULTIPLY", jaw, nb.math("SUBTRACT", 1.0,
                      nb.math("MINIMUM", 1.0, nb.math("MULTIPLY", nb.math("ADD", nb.attr("m_lip_u"), nb.attr("m_lip_l")), 2.0))))
        col = nb.mix(col, (0.45, 0.40, 0.38), nb.math("MULTIPLY", jaw, 0.22))
    # age spots
    if old > 0.4:
        vs = nb.voronoi(obj, scale=55.0)[0]
        spots = nb.maprange(vs, 0.12, 0.05)
        spn = nb.maprange(nb.noise(obj, scale=9.0)[0], 0.5, 0.7)
        col = nb.mix(col, (0.45, 0.30, 0.20), nb.math("MULTIPLY", nb.math("MULTIPLY", spots, spn), 0.5 * old))
    # lips
    lip = nb.math("MINIMUM", 1.0, nb.math("MULTIPLY", nb.math("MAXIMUM", nb.attr("m_lip_u"), nb.attr("m_lip_l")), 1.6))
    lip = nb.maprange(lip, 0.35, 0.8)
    if idn.female and idn.makeup > 0:
        lipc = _lerp3((0.66, 0.36, 0.34), (0.60, 0.10, 0.12), idn.makeup)
    else:
        lipc = (0.62, 0.36, 0.32) if not old > 0.6 else (0.58, 0.40, 0.36)
    col = nb.mix(col, lipc, nb.math("MULTIPLY", lip, 0.85))
    # make-up: blush, eye shadow (warm peach at the outer upper lid), eyeliner handled by lashes
    if idn.female and idn.makeup > 0:
        blush = nb.math("MULTIPLY", nb.attr("m_cheek"), 0.35 * idn.makeup)
        col = nb.mix(col, (0.86, 0.45, 0.45), blush)
        es = nb.math("MULTIPLY", nb.maprange(fy, -0.02, 0.18), nb.maprange(fy, 0.42, 0.25))
        es = nb.math("MULTIPLY", es, nb.maprange(ax, 0.2, 0.55))
        es = nb.math("MULTIPLY", es, nb.maprange(ax, 1.0, 0.75))
        col = nb.mix(col, (0.72, 0.30, 0.26), nb.math("MULTIPLY", es, 0.55 * idn.makeup))
        # porcelain powder: lift and even the face
        col = nb.mix(col, (0.92, 0.80, 0.72), 0.18 * idn.makeup)
    # ------------------------------------------------------------------ wrinkles (height field)
    h = nb.value(0.0)
    cav = nb.value(0.0)
    if old > 0.05:
        wn = nb.noise(obj, scale=60.0, detail=2.0)[0]
        # forehead: horizontal creases
        fl = nb.wave(nb.combine(fy, fx, 0.0), scale=4.6, distortion=1.2, detail=1.5, direction="X")[1]
        fl = nb.maprange(fl, 0.88, 1.0)  # thin crease where the band peaks
        fmask = nb.math("MULTIPLY", nb.maprange(fy, 0.55, 0.75), nb.maprange(fy, 1.35, 1.1))
        fmask = nb.math("MULTIPLY", fmask, nb.maprange(ax, 0.95, 0.55))
        fl = nb.math("MULTIPLY", fl, fmask)
        # crow's feet: radial bands around the outer eye corner
        dx = nb.math("SUBTRACT", ax, 0.66)
        ang = nb.math("ARCTAN2", fy, dx)
        cf = nb.wave(nb.combine(nb.math("ADD", ang, nb.math("MULTIPLY", wn, 0.4)), 0, 0), scale=2.2,
                     direction="X")[1]
        cf = nb.maprange(cf, 0.82, 1.0)
        rad = nb.vmath("LENGTH", nb.combine(dx, fy, 0.0), out=1)
        cmask = nb.math("MULTIPLY", nb.maprange(rad, 0.06, 0.12), nb.maprange(rad, 0.36, 0.22))
        cmask = nb.math("MULTIPLY", cmask, nb.maprange(dx, -0.02, 0.06))
        cf = nb.math("MULTIPLY", cf, cmask)
        # under-eye arcs
        ue = nb.vmath("LENGTH", nb.combine(nb.math("SUBTRACT", ax, 0.5), nb.math("MULTIPLY", fy, 1.3), 0.0), out=1)
        uel = nb.wave(nb.combine(nb.math("ADD", ue, nb.math("MULTIPLY", wn, 0.03)), 0, 0), scale=22.0,
                      direction="X")[1]
        uel = nb.maprange(uel, 0.85, 1.0)
        umask = nb.math("MULTIPLY", nb.maprange(ue, 0.24, 0.3), nb.maprange(ue, 0.5, 0.4))
        umask = nb.math("MULTIPLY", umask, nb.maprange(fy, 0.0, -0.08))
        uel = nb.math("MULTIPLY", uel, umask)
        # nasolabial crease: distance to the nose-wing -> mouth-corner line
        t = nb.math("SUBTRACT", fy, -0.62)
        lx = nb.math("ADD", 0.36, nb.math("MULTIPLY", t, -0.36))  # x of the line at height fy
        nd = nb.math("ABSOLUTE", nb.math("SUBTRACT", ax, lx))
        nl = nb.maprange(nd, 0.05, 0.0)
        nmask = nb.math("MULTIPLY", nb.maprange(fy, -0.55, -0.68), nb.maprange(fy, -1.35, -1.15))
        nl = nb.math("MULTIPLY", nl, nmask)
        # glabella frown lines (vertical)
        gl = nb.wave(nb.combine(fx, fy, 0.0), scale=9.0, distortion=0.6, direction="X")[1]
        gl = nb.maprange(gl, 0.9, 1.0)
        gmask = nb.math("MULTIPLY", nb.maprange(ax, 0.2, 0.08), nb.math("MULTIPLY", nb.maprange(fy, 0.08, 0.2), nb.maprange(fy, 0.55, 0.4)))
        gl = nb.math("MULTIPLY", gl, gmask)
        wr = nb.math("ADD", nb.math("MULTIPLY", fl, 0.9 * old), nb.math("MULTIPLY", cf, 0.9 * old))
        wr = nb.math("ADD", wr, nb.math("MULTIPLY", uel, 0.7 * old))
        wr = nb.math("ADD", wr, nb.math("MULTIPLY", nl, 0.6 + 0.6 * old))
        wr = nb.math("ADD", wr, nb.math("MULTIPLY", gl, 0.3 + 0.6 * old))
        h = nb.math("SUBTRACT", h, wr)
        cav = nb.math("ADD", cav, wr)
        col = nb.mix(col, (0.42, 0.26, 0.20), nb.math("MULTIPLY", nb.math("MINIMUM", cav, 1.0), 0.45))
    # pores / micro relief
    por = nb.voronoi(obj, scale=1400.0, feature="F1")[0]
    micro = nb.noise(obj, scale=500.0, detail=3.0)[0]
    pore_h = nb.math("ADD", nb.math("MULTIPLY", por, 0.5), nb.math("MULTIPLY", micro, 0.5))
    nrm = nb.bump(pore_h, strength=0.05 + 0.04 * old, distance=0.0004)
    nrm = nb.bump(h, strength=0.6, distance=0.0012, normal=nrm)
    # ------------------------------------------------------------------ roughness
    tz = nb.math("MAXIMUM", nb.attr("m_nose"), nb.math("MULTIPLY", fore, 0.8))
    rough = nb.math("SUBTRACT", 0.5 + 0.06 * old, nb.math("MULTIPLY", tz, 0.12))
    rough = nb.math("SUBTRACT", rough, nb.math("MULTIPLY", lip, 0.18 if not idn.female else 0.25))
    rough = nb.math("ADD", rough, nb.math("MULTIPLY", nb.math("SUBTRACT", mott2, 0.5), 0.2))
    p = nb.principled(Base_Color=col, Roughness=rough, Subsurface_Weight=1.0,
                      Subsurface_Radius=(1.0, 0.42, 0.22), Subsurface_Scale=0.0042,
                      Specular_IOR_Level=0.5, Normal=nrm,
                      Sheen_Weight=0.12 if idn.female else 0.05, Sheen_Roughness=0.4,
                      Sheen_Tint=(0.95, 0.85, 0.8, 1))
    p.subsurface_method = "RANDOM_WALK"
    nb.output(p.outputs[0])
    return m


def eye_materials(eye_png, iris_dark=0.5, name="Eye"):
    """(eyeball, cornea) materials.  The MakeHuman eye is an inner textured ball plus a cornea
    shell (alpha 0 in the texture): the shell becomes a clear fresnel-glossy layer that carries the
    catchlights."""
    m = bpy.data.materials.new(name)
    nb = NB(m)
    img = bpy.data.images.load(eye_png, check_existing=True)
    tex = nb.image(img)[0]
    hsv = nb.node("ShaderNodeSeparateColor", mode="HSV")
    nb.link(tex, hsv.inputs[0])
    iris = nb.maprange(hsv.outputs[1], 0.3, 0.55)
    # dark brown iris; sclera toned down to a warm ivory (never paper white)
    ir = nb.hsv(tex, h=0.53, s=0.85, v=iris_dark)
    scl = nb.mix(nb.hsv(tex, h=0.5, s=0.5, v=0.95), (0.86, 0.81, 0.75), 0.4)
    col = nb.mix(scl, ir, iris)
    p = nb.principled(Base_Color=col, Roughness=0.35, Specular_IOR_Level=0.3)
    nb.output(p.outputs[0])
    c = bpy.data.materials.new(name + "Cornea")
    nb2 = NB(c)
    tr = nb2.node("ShaderNodeBsdfTransparent")
    gl = nb2.node("ShaderNodeBsdfGlossy", distribution="GGX")
    gl.inputs["Roughness"].default_value = 0.015
    fr = nb2.node("ShaderNodeLayerWeight")
    fr.inputs["Blend"].default_value = 0.12
    fac = nb2.math("ADD", fr.outputs["Fresnel"], 0.03, clamp=True)
    mx = nb2.node("ShaderNodeMixShader")
    nb2.link(fac, mx.inputs[0])
    nb2.link(tr.outputs[0], mx.inputs[1])
    nb2.link(gl.outputs[0], mx.inputs[2])
    nb2.output(mx.outputs[0])
    c.blend_method = "BLEND"
    return m, c


def skin_material_tex(idn, A_img, R_img, H_img, name="Skin", sss="BURLEY", bump=None):
    """Texture-driven skin (maps from :mod:`skinmaps`): cheap to render, rich in detail."""
    m = bpy.data.materials.new(name)
    nb = NB(m)
    uv = nb.coord("UV")
    alb = nb.image(A_img, uv)[0]
    rough = nb.image(R_img, uv)[0]
    hgt = nb.image(H_img, uv, interp="Cubic")[0]
    if bump is None:
        bump = 1.0 + 0.8 * max(0.0, min(1.0, (idn.age - 35.0) / 35.0))
    nrm = nb.bump(hgt, strength=min(1.0, bump), distance=0.0009 * max(1.0, bump))
    p = nb.principled(Base_Color=alb, Roughness=rough, Subsurface_Weight=1.0,
                      Subsurface_Radius=(1.0, 0.40, 0.20), Subsurface_Scale=0.0045,
                      Specular_IOR_Level=0.5, Normal=nrm,
                      Sheen_Weight=0.15 if idn.female else 0.06, Sheen_Roughness=0.35,
                      Sheen_Tint=(1.0, 0.92, 0.88, 1))
    p.subsurface_method = sss
    nb.output(p.outputs[0])
    return m
