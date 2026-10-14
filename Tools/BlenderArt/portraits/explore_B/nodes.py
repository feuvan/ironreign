"""Tiny shader/compositor node-graph builder (own copy so ironart refactors cannot break us)."""

import bpy


def lin(c):
    """'#rrggbb' (sRGB) or tuple (linear) -> linear RGBA tuple."""
    if isinstance(c, str):
        h = c.lstrip("#")
        rgb = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
        out = []
        for x in rgb:
            out.append(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4)
        return (out[0], out[1], out[2], 1.0)
    c = tuple(c)
    return c if len(c) == 4 else (c[0], c[1], c[2], 1.0)


def sock(coll, name):
    s = coll.get(name)
    if s is None:
        s = next((x for x in coll if x.name == name), None)
    if s is None:
        raise KeyError("%s (have %s)" % (name, [x.name for x in coll]))
    return s


class NB:
    def __init__(self, tree):
        self.tree = tree
        self.nodes = tree.nodes
        self.links = tree.links

    def node(self, kind, inputs=None, **props):
        n = self.nodes.new(kind)
        for k, v in props.items():
            setattr(n, k, v)
        for k, v in (inputs or {}).items():
            self.set(sock(n.inputs, k) if isinstance(k, str) else n.inputs[k], v)
        return n

    def set(self, s, value):
        if value is None:
            return
        if isinstance(value, bpy.types.NodeSocket):
            self.links.new(value, s)
        elif isinstance(value, bpy.types.Node):
            self.links.new(value.outputs[0], s)
        elif isinstance(value, str):
            s.default_value = lin(value)
        elif isinstance(value, (tuple, list)) and s.type == "RGBA":
            s.default_value = lin(value)
        else:
            s.default_value = value

    def out(self, n, name=0):
        if isinstance(n, bpy.types.NodeSocket):
            return n
        return n.outputs[name] if isinstance(name, int) else sock(n.outputs, name)

    # ---- shader helpers
    def math(self, op, a, b=0.0, c=0.0, clamp=False):
        n = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        self.set(n.inputs[0], a)
        self.set(n.inputs[1], b)
        if len(n.inputs) > 2:
            self.set(n.inputs[2], c)
        return n.outputs[0]

    def vmath(self, op, a, b=None, scale=None):
        n = self.node("ShaderNodeVectorMath", operation=op)
        self.set(n.inputs[0], a)
        if b is not None:
            self.set(n.inputs[1], b)
        if scale is not None:
            self.set(sock(n.inputs, "Scale"), scale)
        return n.outputs["Value"] if op in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else n.outputs[0]

    def maprange(self, v, a0, a1, b0=0.0, b1=1.0, clamp=True, interp="LINEAR"):
        n = self.node("ShaderNodeMapRange", interpolation_type=interp, clamp=clamp)
        self.set(n.inputs["Value"], v)
        n.inputs["From Min"].default_value = a0
        n.inputs["From Max"].default_value = a1
        n.inputs["To Min"].default_value = b0
        n.inputs["To Max"].default_value = b1
        return n.outputs["Result"]

    def ramp(self, fac, stops, interp="LINEAR"):
        n = self.node("ShaderNodeValToRGB")
        cr = n.color_ramp
        cr.interpolation = interp
        while len(cr.elements) > len(stops):
            cr.elements.remove(cr.elements[-1])
        while len(cr.elements) < len(stops):
            cr.elements.new(0.5)
        for el, (p, c) in zip(cr.elements, stops):
            el.position = p
            el.color = lin(c) if not isinstance(c, (int, float)) else (c, c, c, 1.0)
        self.set(n.inputs[0], fac)
        return n.outputs[0]

    def mix(self, a, b, fac, blend="MIX", clamp=False):
        n = self.node("ShaderNodeMix", data_type="RGBA", blend_type=blend, clamp_result=clamp)
        self.set(n.inputs[0], fac)
        self.set(n.inputs[6], a)
        self.set(n.inputs[7], b)
        return n.outputs[2]

    def mixf(self, a, b, fac):
        n = self.node("ShaderNodeMix", data_type="FLOAT")
        self.set(n.inputs[0], fac)
        self.set(n.inputs[2], a)
        self.set(n.inputs[3], b)
        return n.outputs[0]

    def attr(self, name, kind="GEOMETRY", out="Fac"):
        n = self.node("ShaderNodeAttribute", attribute_name=name, attribute_type=kind)
        return n.outputs[out]

    def noise(self, vec=None, scale=5.0, detail=2.0, rough=0.5, distortion=0.0, dims="3D", out="Fac"):
        n = self.node("ShaderNodeTexNoise", noise_dimensions=dims)
        if vec is not None:
            self.set(n.inputs["Vector"], vec)
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        n.inputs["Distortion"].default_value = distortion
        return n.outputs[out]

    def voronoi(self, vec=None, scale=5.0, feature="F1", out="Distance", randomness=1.0):
        n = self.node("ShaderNodeTexVoronoi", feature=feature)
        if vec is not None:
            self.set(n.inputs["Vector"], vec)
        n.inputs["Scale"].default_value = scale
        n.inputs["Randomness"].default_value = randomness
        return n.outputs[out]

    def bump(self, height, strength=0.3, distance=0.001, normal=None):
        n = self.node("ShaderNodeBump")
        self.set(n.inputs["Height"], height)
        n.inputs["Strength"].default_value = strength
        n.inputs["Distance"].default_value = distance
        if normal is not None:
            self.set(n.inputs["Normal"], normal)
        return n.outputs[0]

    def combine(self, x, y, z):
        n = self.node("ShaderNodeCombineXYZ")
        self.set(n.inputs[0], x)
        self.set(n.inputs[1], y)
        self.set(n.inputs[2], z)
        return n.outputs[0]

    def separate(self, v):
        n = self.node("ShaderNodeSeparateXYZ")
        self.set(n.inputs[0], v)
        return n.outputs

    def hsv(self, col, h=0.5, s=1.0, v=1.0, fac=1.0):
        n = self.node("ShaderNodeHueSaturation")
        self.set(n.inputs["Hue"], h)
        self.set(n.inputs["Saturation"], s)
        self.set(n.inputs["Value"], v)
        self.set(n.inputs["Fac"], fac)
        self.set(n.inputs["Color"], col)
        return n.outputs[0]

    def aov(self, name, value, color=False):
        n = self.node("ShaderNodeOutputAOV")
        n.name = name  # 4.0: the AOV name property shadows the node name
        self.set(n.inputs["Color" if color else "Value"], value)
        return n


def material(name):
    m = bpy.data.materials.get(name)
    if m is not None:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes.clear()
    return m, NB(m.node_tree)


def principled(nb, **inputs):
    p = nb.node("ShaderNodeBsdfPrincipled")
    for k, v in inputs.items():
        nb.set(sock(p.inputs, k.replace("_", " ")), v)
    return p


def output(nb, shader, displacement=None):
    o = nb.node("ShaderNodeOutputMaterial", target="CYCLES")
    nb.set(o.inputs["Surface"], shader)
    if displacement is not None:
        nb.set(o.inputs["Displacement"], displacement)
    return o
