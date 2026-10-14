"""Gongbi materials.  Nothing here is lit: every material writes *paint data* into AOVs and the
2D finish (finish.py) lays the washes on silk.

AOVs (all values are sRGB-encoded data, written straight into float EXR passes):
  paint  colour  the flat pigment colour of the surface (incl. painted patterns and decal ink)
  tint   colour  the colour that 晕染 shading glazes toward (multiplied in by ``shade``)
  shade  value   0..1 amount of 晕染 soft shading (AO in folds + darkening toward contours)
  ink    value   1 where the colour is an ink stroke (no pigment opacity / silk show-through)
The surface itself is an Emission of ``paint`` (only for the debug combined pass).
"""

import bpy

from palette import hex_rgb

AOVS = (("paint", "COLOR"), ("tint", "COLOR"), ("shade", "VALUE"), ("ink", "VALUE"),
        ("mask", "VALUE"), ("aok", "VALUE"), ("veil", "VALUE"))


def register_aovs(vl=None):
    vl = vl or bpy.context.view_layer
    have = [a.name for a in vl.aovs]
    for n, t in AOVS:
        if n not in have:
            a = vl.aovs.add()
            a.name = n
            a.type = t


def rgb(c):
    if isinstance(c, str):
        c = hex_rgb(c)
    return (c[0], c[1], c[2], 1.0)


class NB:
    """Tiny node-tree builder: every helper returns an output socket; inputs accept sockets or
    constants."""

    def __init__(self, mat):
        mat.use_nodes = True
        self.nt = mat.node_tree
        self.nt.nodes.clear()
        self.x = 0

    def n(self, kind, **props):
        node = self.nt.nodes.new(kind)
        for k, v in props.items():
            setattr(node, k, v)
        node.location = (self.x, 0)
        self.x += 30
        return node

    def put(self, sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.nt.links.new(v, sock)
        elif isinstance(v, str):
            sock.default_value = rgb(v)
        elif isinstance(v, (tuple, list)) and len(v) == 3 and sock.type == "RGBA":
            sock.default_value = (v[0], v[1], v[2], 1.0)
        else:
            sock.default_value = v

    def math(self, op, a, b=0.0, c=0.0, clamp=False):
        m = self.n("ShaderNodeMath", operation=op, use_clamp=clamp)
        self.put(m.inputs[0], a)
        self.put(m.inputs[1], b)
        if len(m.inputs) > 2:
            self.put(m.inputs[2], c)
        return m.outputs[0]

    def vmath(self, op, a, b=(0, 0, 0), scale=None):
        m = self.n("ShaderNodeVectorMath", operation=op)
        self.put(m.inputs[0], a)
        self.put(m.inputs[1], b)
        if scale is not None:
            self.put(m.inputs[3], scale)
        out = m.outputs["Value"] if op in ("LENGTH", "DISTANCE", "DOT_PRODUCT") else m.outputs[0]
        return out

    def sep(self, v):
        s = self.n("ShaderNodeSeparateXYZ")
        self.put(s.inputs[0], v)
        return s.outputs

    def comb(self, x, y, z):
        s = self.n("ShaderNodeCombineXYZ")
        self.put(s.inputs[0], x)
        self.put(s.inputs[1], y)
        self.put(s.inputs[2], z)
        return s.outputs[0]

    def mix(self, fac, a, b, blend="MIX"):
        m = self.n("ShaderNodeMix", data_type="RGBA", blend_type=blend, clamp_factor=True)
        self.put(m.inputs["Factor"], fac)
        self.put(m.inputs[6], a)
        self.put(m.inputs[7], b)
        return m.outputs[2]

    def smooth(self, x, e0, e1):
        m = self.n("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP", clamp=True)
        self.put(m.inputs[0], x)
        self.put(m.inputs[1], e0)
        self.put(m.inputs[2], e1)
        m.inputs[3].default_value = 0.0
        m.inputs[4].default_value = 1.0
        return m.outputs[0]

    def maprange(self, x, a0, a1, b0, b1, clamp=True):
        m = self.n("ShaderNodeMapRange", interpolation_type="LINEAR", clamp=clamp)
        for i, v in enumerate((x, a0, a1, b0, b1)):
            self.put(m.inputs[i], v)
        return m.outputs[0]

    def coord(self, kind="Object"):
        return self.n("ShaderNodeTexCoord").outputs[kind]

    def uv(self):
        return self.n("ShaderNodeUVMap", uv_map="UVMap").outputs[0]

    def attr(self, name, kind="Fac"):
        return self.n("ShaderNodeAttribute", attribute_name=name).outputs[kind]

    def ao(self, dist, local=False, samples=6):
        a = self.n("ShaderNodeAmbientOcclusion", only_local=local, samples=samples)
        a.inputs["Distance"].default_value = dist
        return a.outputs["AO"]

    def facing(self, blend=0.5):
        lw = self.n("ShaderNodeLayerWeight")
        lw.inputs["Blend"].default_value = blend
        return lw.outputs["Facing"]

    def noise(self, vec, scale=5.0, detail=2.0, rough=0.5, dims="3D"):
        t = self.n("ShaderNodeTexNoise", noise_dimensions=dims)
        self.put(t.inputs["Vector"], vec)
        t.inputs["Scale"].default_value = scale
        t.inputs["Detail"].default_value = detail
        t.inputs["Roughness"].default_value = rough
        return t.outputs["Fac"]

    def blob(self, P, center, radii):
        """exp(-|((P - c) / r)|^2) anisotropic gaussian in object space."""
        d = self.vmath("SUBTRACT", P, tuple(center))
        d = self.vmath("DIVIDE", d, tuple(radii))
        l2 = self.vmath("DOT_PRODUCT", d, d)
        return self.math("EXPONENT", self.math("MULTIPLY", l2, -1.0))

    def out(self, paint, tint=None, shade=0.0, ink=0.0, mask=0.0, aok=None, veil=0.0):
        """Write the AOVs + emission surface.  ``aok``: how strongly the render's AO pass
        (folds, contact) adds to 晕染 for this material (default: set by shade_term)."""
        if aok is None:
            aok = getattr(self, "_aok", 0.0)
        for name, v in (("paint", paint), ("tint", tint if tint is not None else paint),
                        ("shade", shade), ("ink", ink), ("mask", mask), ("aok", aok),
                        ("veil", veil)):
            a = self.n("ShaderNodeOutputAOV")
            if hasattr(a, "aov_name"):
                a.aov_name = name
            else:
                a.name = name
            if name in ("paint", "tint"):
                self.put(a.inputs["Color"], v)
            else:
                self.put(a.inputs["Value"], v)
        e = self.n("ShaderNodeEmission")
        self.put(e.inputs[0], paint)
        o = self.n("ShaderNodeOutputMaterial")
        self.nt.links.new(e.outputs[0], o.inputs[0])


def _mat(name):
    """Always a fresh material (Blender suffixes duplicate names)."""
    return bpy.data.materials.new(name)


def shade_term(nb, ao=0.6, ao_dist=0.03, edge=0.35, edge0=0.45, base=0.0, local=False,
               samples=6):
    """晕染 amount: occlusion in folds + darkening toward the contours."""
    s = base
    # occlusion comes from the render's AO pass (one ray per sample, far cheaper than AO
    # nodes); the material only says how strongly it applies
    nb._aok = ao
    if edge > 0:
        s = nb.math("ADD", s, nb.math("MULTIPLY", nb.smooth(nb.facing(0.5), edge0, 1.0), edge))
    return nb.math("MINIMUM", s, 1.0)


# ------------------------------------------------------------------------------- materials
def flat(name, paint, tint=None, ao=0.55, ao_dist=0.03, edge=0.3, edge0=0.5, base=0.0,
         pattern=None, mask=0.0):
    """A pigment surface.  ``pattern(nb, paint_socket) -> paint socket`` adds painted motifs."""
    m = _mat(name)
    nb = NB(m)
    p = rgb(paint)
    if pattern is not None:
        p = pattern(nb, p)
    t = tint if tint is not None else _deepen(paint)
    nb.out(p, rgb(t) if not isinstance(t, bpy.types.NodeSocket) else t,
           shade_term(nb, ao, ao_dist, edge, edge0, base), 0.0, mask)
    return m


def _deepen(c, k=0.62):
    """Glazing the same pigment again: deeper, more saturated."""
    r, g, b = hex_rgb(c) if isinstance(c, str) else c[:3]
    return (r * r ** 0.4 * k + 0.0, g * g ** 0.4 * k, b * b ** 0.4 * k)


def ink(name, color="ink", ink_amt=1.0):
    m = _mat(name)
    nb = NB(m)
    nb.out(rgb(color), rgb(color), 0.0, ink_amt)
    return m


def skin(name, base, rouge, blobs, light_blobs=(), shade_tint="#B97B62", ao=0.75, edge=0.55,
         ao_dist=0.025):
    """Skin wash: base tone, rouge gaussians (cheeks, lids, nose tip, chin), 三白 lighter
    passages; shading glazes toward a warm ochre-rouge."""
    m = _mat(name)
    nb = NB(m)
    p = skin_paint(nb, base, rouge, blobs, light_blobs)
    nb.out(p, rgb(shade_tint), shade_term(nb, ao, ao_dist, edge, 0.42), 0.0, 1.0)
    return m


def skin_paint(nb, base, rouge, blobs, light_blobs=()):
    P = nb.coord("Object")
    acc = 0.0
    for c, r, amt in blobs:
        acc = nb.math("ADD", acc, nb.math("MULTIPLY", nb.blob(P, c, r), amt))
    acc = nb.math("MINIMUM", acc, 1.0)
    col = nb.mix(acc, rgb(base), rgb(rouge))
    if light_blobs:
        la = 0.0
        for c, r, amt in light_blobs:
            la = nb.math("ADD", la, nb.math("MULTIPLY", nb.blob(P, c, r), amt))
        col = nb.mix(nb.math("MINIMUM", la, 1.0), col, rgb("lead_white"))
    return col
