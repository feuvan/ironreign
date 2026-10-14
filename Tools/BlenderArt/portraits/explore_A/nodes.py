"""Tiny shader-node builder used by the portrait materials (bpy only)."""

import bpy


def lin(c):
    """'#RRGGBB' or (r,g,b) sRGB 0..1 -> linear rgba tuple."""
    if isinstance(c, str):
        h = c.lstrip("#")
        c = tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    out = []
    for v in c[:3]:
        out.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
    return tuple(out) + (1.0,)


def sock(coll, name):
    for s in coll:
        if s.name == name or s.identifier == name:
            return s
    raise KeyError(name)


class NB:
    def __init__(self, mat):
        self.mat = mat
        mat.use_nodes = True
        self.nt = mat.node_tree
        for n in list(self.nt.nodes):
            self.nt.nodes.remove(n)
        self.out = self.nt.nodes.new("ShaderNodeOutputMaterial")

    def node(self, kind, **props):
        n = self.nt.nodes.new(kind)
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def link(self, a, b):
        self.nt.links.new(a, b)

    def set(self, s, v):
        """Socket <- value / socket / colour string."""
        if hasattr(v, "is_output") or (hasattr(v, "node") and hasattr(v, "links")):
            self.link(v, s)
        elif isinstance(v, str):
            s.default_value = lin(v)
        elif isinstance(v, (tuple, list)) and len(v) in (3, 4) and s.type == "RGBA":
            s.default_value = tuple(v[:3]) + (1.0,) if len(v) == 3 else tuple(v)
        else:
            s.default_value = v

    def _in(self, n, key, v):
        s = n.inputs[key] if isinstance(key, int) else sock(n.inputs, key)
        self.set(s, v)

    # ---- inputs
    def attr(self, name, kind="Fac"):
        n = self.node("ShaderNodeAttribute", attribute_name=name)
        return n.outputs[kind]

    def coord(self, kind="Object"):
        n = self.node("ShaderNodeTexCoord")
        return n.outputs[kind]

    def value(self, v):
        n = self.node("ShaderNodeValue")
        n.outputs[0].default_value = v
        return n.outputs[0]

    # ---- math
    def math(self, op, a, b=0.0, c=0.0, clamp=False):
        n = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        self._in(n, 0, a)
        if len(n.inputs) > 1:
            self._in(n, 1, b)
        if len(n.inputs) > 2:
            self._in(n, 2, c)
        return n.outputs[0]

    def vmath(self, op, a, b=(0, 0, 0), out=0):
        n = self.node("ShaderNodeVectorMath", operation=op)
        self._in(n, 0, a)
        self._in(n, 1, b)
        return n.outputs[out]

    def sep(self, v):
        n = self.node("ShaderNodeSeparateXYZ")
        self._in(n, 0, v)
        return n.outputs

    def combine(self, x, y, z):
        n = self.node("ShaderNodeCombineXYZ")
        self._in(n, 0, x)
        self._in(n, 1, y)
        self._in(n, 2, z)
        return n.outputs[0]

    def maprange(self, v, a0, a1, b0=0.0, b1=1.0, interp="SMOOTHSTEP", clamp=True):
        n = self.node("ShaderNodeMapRange", interpolation_type=interp, clamp=clamp)
        self._in(n, "Value", v)
        n.inputs[1].default_value = a0
        n.inputs[2].default_value = a1
        n.inputs[3].default_value = b0
        n.inputs[4].default_value = b1
        return n.outputs[0]

    def mix(self, a, b, fac, blend="MIX", clamp=True):
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

    def hsv(self, col, h=0.5, s=1.0, v=1.0, fac=1.0):
        n = self.node("ShaderNodeHueSaturation")
        self._in(n, "Hue", h)
        self._in(n, "Saturation", s)
        self._in(n, "Value", v)
        self._in(n, "Fac", fac)
        self._in(n, "Color", col)
        return n.outputs[0]

    def ramp(self, fac, stops, interp="LINEAR"):
        n = self.node("ShaderNodeValToRGB")
        cr = n.color_ramp
        cr.interpolation = interp
        while len(cr.elements) > len(stops):
            cr.elements.remove(cr.elements[-1])
        while len(cr.elements) < len(stops):
            cr.elements.new(0.5)
        for e, (pos, col) in zip(cr.elements, stops):
            e.position = pos
            e.color = lin(col) if isinstance(col, str) else (tuple(col) + (1.0,) if len(col) == 3 else tuple(col))
        self.set(n.inputs[0], fac)
        return n.outputs[0]

    # ---- textures
    def noise(self, vec=None, scale=5.0, detail=2.0, rough=0.5, distortion=0.0, dims="3D", w=0.0):
        n = self.node("ShaderNodeTexNoise", noise_dimensions=dims)
        if vec is not None:
            self._in(n, "Vector", vec)
        self._in(n, "Scale", scale)
        self._in(n, "Detail", detail)
        self._in(n, "Roughness", rough)
        self._in(n, "Distortion", distortion)
        if dims == "4D":
            self._in(n, "W", w)
        return n.outputs

    def voronoi(self, vec=None, scale=5.0, feature="F1", metric="EUCLIDEAN", rand=1.0, dims="3D"):
        n = self.node("ShaderNodeTexVoronoi", feature=feature, distance=metric, voronoi_dimensions=dims)
        if vec is not None:
            self._in(n, "Vector", vec)
        self._in(n, "Scale", scale)
        self._in(n, "Randomness", rand)
        return n.outputs

    def wave(self, vec=None, scale=5.0, distortion=0.0, detail=2.0, kind="BANDS", direction="X",
             profile="SIN", phase=0.0):
        n = self.node("ShaderNodeTexWave", wave_type=kind, bands_direction=direction,
                      wave_profile=profile)
        if vec is not None:
            self._in(n, "Vector", vec)
        self._in(n, "Scale", scale)
        self._in(n, "Distortion", distortion)
        self._in(n, "Detail", detail)
        self._in(n, "Phase Offset", phase)
        return n.outputs

    def image(self, img, vec=None, interp="Cubic", extension="REPEAT"):
        n = self.node("ShaderNodeTexImage", interpolation=interp, extension=extension)
        n.image = img
        if vec is not None:
            self._in(n, "Vector", vec)
        return n.outputs

    def mapping(self, vec, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
        n = self.node("ShaderNodeMapping")
        self._in(n, "Vector", vec)
        n.inputs["Location"].default_value = loc
        n.inputs["Rotation"].default_value = rot
        n.inputs["Scale"].default_value = scale
        return n.outputs[0]

    def bump(self, height, strength=0.5, distance=0.001, normal=None, invert=False):
        n = self.node("ShaderNodeBump", invert=invert)
        self._in(n, "Height", height)
        self._in(n, "Strength", strength)
        self._in(n, "Distance", distance)
        if normal is not None:
            self._in(n, "Normal", normal)
        return n.outputs[0]

    # ---- shaders
    def principled(self, **kw):
        n = self.node("ShaderNodeBsdfPrincipled")
        for k, v in kw.items():
            self._in(n, k.replace("_", " "), v)
        return n

    def output(self, shader):
        self.link(shader, self.out.inputs["Surface"])


def material(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    return m, NB(m)
