"""In-render compositor for approach B.

    light groups --(per-light gain/tint: art-directed relight)--> lit
    lit over the painted background --> three anisotropic Kuwahara scales, chosen per region by
    the material AOVs (skin small & soft, hair medium, costume/background broad strokes), eyes
    kept clean --> ink accents (AOV 'accent') --> Composite

A File Output node also writes the region masks (R skin, G hair, B costume, A alpha) and the eye
mask, used by :mod:`finish` for the brush texture / edge dissolve / local sharpening.
"""

import os

import bpy

from . import background

AOVS = ("skin", "hair", "costume", "eye", "detail", "accent", "metal")
GROUPS = ("key", "fill", "rim", "rim2", "bounce", "world")


def _n(nt, kind, **props):
    n = nt.nodes.new(kind)
    for k, v in props.items():
        setattr(n, k, v)
    return n


def _mix(nt, a, b, fac, blend="MIX"):
    m = _n(nt, "CompositorNodeMixRGB", blend_type=blend, use_alpha=False)
    if isinstance(fac, (int, float)):
        m.inputs[0].default_value = fac
    else:
        nt.links.new(fac, m.inputs[0])
    nt.links.new(a, m.inputs[1]) if not isinstance(a, tuple) else setattr(m.inputs[1], "default_value", a)
    nt.links.new(b, m.inputs[2]) if not isinstance(b, tuple) else setattr(m.inputs[2], "default_value", b)
    return m.outputs[0]


def _kuwa(nt, src, size, ecc, sharp=0.5, unif=4):
    k = _n(nt, "CompositorNodeKuwahara", variation="ANISOTROPIC")
    k.size = max(1, int(size))
    k.uniformity = unif
    k.sharpness = sharp
    k.eccentricity = ecc
    nt.links.new(src, k.inputs[0])
    return k.outputs[0]


def _kuwa_half(nt, src, size, ecc, sharp=0.5, unif=4):
    """Kuwahara at half resolution (1/16 of the cost for the same stroke size), scaled back."""
    d = _n(nt, "CompositorNodeScale", space="RELATIVE")
    d.inputs[1].default_value = 0.5
    d.inputs[2].default_value = 0.5
    nt.links.new(src, d.inputs[0])
    k = _kuwa(nt, d.outputs[0], max(1, size / 2), ecc, sharp, unif)
    u = _n(nt, "CompositorNodeScale", space="RELATIVE")   # (RENDER_SIZE mis-places the canvas in 4.0)
    u.inputs[1].default_value = 2.0
    u.inputs[2].default_value = 2.0
    nt.links.new(k, u.inputs[0])
    return u.outputs[0]


def _blur(nt, src, px):
    b = _n(nt, "CompositorNodeBlur", filter_type="GAUSS")
    b.size_x = b.size_y = max(1, int(px))
    nt.links.new(src, b.inputs[0])
    return b.outputs[0]


def _math(nt, op, a, b=None, clamp=True):
    m = _n(nt, "CompositorNodeMath", operation=op, use_clamp=clamp)
    for i, x in enumerate((a, b)):
        if x is None:
            continue
        if isinstance(x, (int, float)):
            m.inputs[i].default_value = x
        else:
            nt.links.new(x, m.inputs[i])
    return m.outputs[0]


def _curve(nt, src, pts, scale=0.5):
    """RGB curve applied to ``src * scale`` (then divided back) - value grouping of light."""
    pre = _n(nt, "CompositorNodeMixRGB", blend_type="MULTIPLY")
    pre.inputs[0].default_value = 1.0
    nt.links.new(src, pre.inputs[1])
    pre.inputs[2].default_value = (scale, scale, scale, 1.0)
    c = _n(nt, "CompositorNodeCurveRGB")
    m = c.mapping
    m.extend = "EXTRAPOLATED"
    cv = m.curves[3]
    while len(cv.points) > 2:
        cv.points.remove(cv.points[1])
    cv.points[0].location = pts[0]
    cv.points[-1].location = pts[-1]
    for x, y in pts[1:-1]:
        cv.points.new(x, y)
    m.update()
    nt.links.new(pre.outputs[0], c.inputs["Image"])
    post = _n(nt, "CompositorNodeMixRGB", blend_type="MULTIPLY")
    post.inputs[0].default_value = 1.0
    nt.links.new(c.outputs[0], post.inputs[1])
    post.inputs[2].default_value = (1 / scale, 1 / scale, 1 / scale, 1.0)
    return post.outputs[0]


def _ramp(nt, fac, stops):
    r = _n(nt, "CompositorNodeValToRGB")
    cr = r.color_ramp
    while len(cr.elements) > len(stops):
        cr.elements.remove(cr.elements[-1])
    while len(cr.elements) < len(stops):
        cr.elements.new(0.5)
    for el, (p, c) in zip(cr.elements, stops):
        el.position = p
        el.color = (*c, 1.0)
    nt.links.new(fac, r.inputs[0])
    return r.outputs[0]


def _add(nt, a, b):
    return _mix(nt, a, b, 1.0, "ADD")


def _mul(nt, a, b):
    return _mix(nt, a, b, 1.0, "MULTIPLY")


#: value grouping of the diffuse light (x = light / 2): shadow plateau, quick soft terminator,
#: broad half-tone, compressed lights -> the planar "painted" read of form
BAND = [(0.0, 0.0), (0.02, 0.022), (0.10, 0.045), (0.20, 0.22), (0.30, 0.36), (0.55, 0.47),
        (0.9, 0.6), (1.0, 0.64)]


def relight(nt, rl, P):
    """Rebuild the beauty from passes with art direction (approach B):
    diffuse light value-grouped (per region) and tinted by value (cool shadow, warm saturated
    terminator, warm-neutral light); specular shaped; rim light emphasised."""
    o = rl.outputs
    aov = {a: o.get(a) for a in AOVS}
    diffL = _add(nt, o["DiffDir"], o["DiffInd"])
    banded = _curve(nt, diffL, P.get("band", BAND))
    # region weights: skin strongest, costume medium, hair light
    w = _math(nt, "ADD", _math(nt, "MULTIPLY", aov["skin"], P.get("band_skin", 0.6)),
              _math(nt, "MULTIPLY", aov["costume"], P.get("band_cost", 0.45)))
    w = _math(nt, "ADD", w, _math(nt, "MULTIPLY", aov["hair"], P.get("band_hair", 0.2)))
    diffP = _mix(nt, diffL, banded, w)
    # tint by light value
    lum = _n(nt, "CompositorNodeRGBToBW")
    nt.links.new(diffP, lum.inputs[0])
    lv = _math(nt, "MULTIPLY", lum.outputs[0], 0.5)
    tint = _ramp(nt, lv, P.get("value_tint", [(0.0, (0.88, 0.93, 1.10)), (0.03, (0.92, 0.94, 1.04)),
                                               (0.10, (1.28, 0.86, 0.66)), (0.22, (1.12, 0.96, 0.84)),
                                               (0.45, (1.03, 1.0, 0.96)), (1.0, (1.0, 1.0, 1.0))]))
    tint = _mix(nt, (1.0, 1.0, 1.0, 1.0), tint, _math(nt, "ADD", 0.25, _math(nt, "MULTIPLY", aov["skin"], 0.55)))
    diffuse = _mul(nt, _mul(nt, o["DiffCol"], diffP), tint)
    gloss = _mul(nt, _add(nt, o["GlossDir"], o["GlossInd"]), o["GlossCol"])
    # controlled specular: weak sheen suppressed on skin, strong highlights kept crisp
    gl = _n(nt, "CompositorNodeRGBToBW")
    nt.links.new(gloss, gl.inputs[0])
    keep = _n(nt, "CompositorNodeMapRange", use_clamp=True)
    nt.links.new(gl.outputs[0], keep.inputs[0])
    keep.inputs[1].default_value = P.get("spec_lo", 0.02)
    keep.inputs[2].default_value = P.get("spec_hi", 0.10)
    keep.inputs[3].default_value = 0.25
    keep.inputs[4].default_value = 1.15
    kf = _mix(nt, (1.0, 1.0, 1.0, 1.0), _n_set(nt, keep.outputs[0]), aov["skin"])
    gloss = _mul(nt, gloss, kf)
    trans = _mul(nt, _add(nt, o["TransDir"], o["TransInd"]), o["TransCol"])
    img = _add(nt, _add(nt, diffuse, gloss), trans)
    img = _add(nt, img, o["Emit"])
    img = _add(nt, img, o["Env"])
    # rim emphasis (cool edge light) and kicker
    rimx = _n(nt, "CompositorNodeMixRGB", blend_type="MULTIPLY")
    rimx.inputs[0].default_value = 1.0
    nt.links.new(o["Combined_rim"], rimx.inputs[1])
    rimx.inputs[2].default_value = (*P.get("rim_extra", (0.35, 0.5, 0.8)), 1.0)
    img = _add(nt, img, rimx.outputs[0])
    return img


def _n_set(nt, val):
    """Value socket -> grey RGB socket."""
    c = _n(nt, "CompositorNodeCombineColor", mode="RGB")
    nt.links.new(val, c.inputs[0])
    nt.links.new(val, c.inputs[1])
    nt.links.new(val, c.inputs[2])
    c.inputs[3].default_value = 1.0
    return c.outputs[0]


def setup(spec, sc, out, ss):
    vl = bpy.context.view_layer
    have = {a.name for a in vl.aovs}
    for a in AOVS:
        if a not in have:
            x = vl.aovs.add()
            x.name = a
            x.type = "VALUE"
    for pname in ("diffuse_direct", "diffuse_indirect", "diffuse_color", "glossy_direct",
                  "glossy_indirect", "glossy_color", "transmission_direct", "transmission_indirect",
                  "transmission_color", "emit", "environment"):
        setattr(vl, "use_pass_" + pname, True)
    sc.use_nodes = True
    nt = sc.node_tree
    nt.nodes.clear()
    rl = _n(nt, "CompositorNodeRLayers")
    comp = _n(nt, "CompositorNodeComposite", use_alpha=True)
    P = spec.get("paint", {})
    lit = relight(nt, rl, P)
    sa = _n(nt, "CompositorNodeSetAlpha", mode="REPLACE_ALPHA")
    nt.links.new(lit, sa.inputs["Image"])
    nt.links.new(rl.outputs["Alpha"], sa.inputs["Alpha"])
    # painted background (numpy) under the figure
    W, H = sc.render.resolution_x, sc.render.resolution_y
    bg_path = os.path.join(out, "%s_bg.png" % spec["name"])
    background.paint(bg_path, W, H, spec.get("background", {}), seed=spec.get("seed", 1))
    img = bpy.data.images.load(bg_path, check_existing=False)
    bgn = _n(nt, "CompositorNodeImage")
    bgn.image = img
    ao = _n(nt, "CompositorNodeAlphaOver")
    nt.links.new(bgn.outputs[0], ao.inputs[1])
    nt.links.new(sa.outputs[0], ao.inputs[2])
    over = ao.outputs[0]
    # region masks
    aov = {a: rl.outputs.get(a) for a in AOVS}
    s = ss / 2.0
    k_face = _kuwa(nt, over, P.get("face_size", 5) * s, P.get("face_ecc", 1.0), P.get("face_sharp", 0.6))
    k_hair = _kuwa_half(nt, over, P.get("hair_size", 8) * s, P.get("hair_ecc", 2.0), 0.5)
    k_cost = _kuwa_half(nt, over, P.get("cost_size", 12) * s, P.get("cost_ecc", 1.6), 0.45)
    skin = _blur(nt, aov["skin"], 2 * s)
    hair = _blur(nt, aov["hair"], 2 * s)
    eye = _blur(nt, aov["eye"], 3 * s)
    painted = k_cost
    painted = _mix(nt, painted, k_hair, hair)
    painted = _mix(nt, painted, k_face, skin)
    # detail retention: a little of the clean render everywhere, a lot on the eyes
    painted = _mix(nt, painted, over, P.get("detail", 0.12))
    painted = _mix(nt, painted, over, _math(nt, "MULTIPLY", eye, P.get("eye_clean", 0.9)))
    # ink accents (lash line etc.): multiply towards warm ink
    acc = _math(nt, "MULTIPLY", aov["accent"], P.get("accent", 0.7))
    painted = _mix(nt, painted, (0.018, 0.011, 0.008, 1.0), acc)
    nt.links.new(painted, comp.inputs["Image"])
    # masks for numpy finishing
    cc = _n(nt, "CompositorNodeCombineColor", mode="RGB")
    nt.links.new(aov["skin"], cc.inputs[0])
    nt.links.new(aov["hair"], cc.inputs[1])
    nt.links.new(aov["costume"], cc.inputs[2])
    nt.links.new(rl.outputs["Alpha"], cc.inputs[3])
    fo = _n(nt, "CompositorNodeOutputFile")
    fo.base_path = out
    fo.format.file_format = "PNG"
    fo.format.color_mode = "RGBA"
    fo.format.color_depth = "8"
    fo.format.color_management = "OVERRIDE"
    fo.format.view_settings.view_transform = "Standard"
    fo.file_slots.clear()
    fo.file_slots.new("%s_masks" % spec["name"])
    nt.links.new(cc.outputs[0], fo.inputs[0])
    fo.file_slots.new("%s_eye" % spec["name"])
    nt.links.new(aov["eye"], fo.inputs[1])
    return dict(rl=rl, bg=bg_path)
