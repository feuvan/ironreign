"""Node-built procedural materials (Cycles) + the NPR "paint" shading option.

Every factory returns a ``bpy.types.Material`` and caches by name (calling twice with the same
``name`` returns the existing material, so builders can request "Stone" freely).

Texture coordinates
    Builders in :mod:`ironart.geometry` write a ``UVMap`` in **metres** (u along the surface,
    v up/along the slope), so pattern scales below are physical: ``brick=(0.5, 0.25)`` means
    50 x 25 cm blocks.  Materials fall back to Object coordinates where noted.

NPR paint option
    Blender's "Shader to RGB" is EEVEE-only and does nothing in Cycles, so the studio "paint"
    look is built from Cycles' Toon BSDF: :func:`paint` mixes a banded Toon diffuse (soft
    terminator, ``size``/``smooth``) into any material's surface shader.  ``amount`` 0.25-0.45 gives
    the painted two-tone feel while keeping Cycles' soft shadows and bounce light.

Colours are palette tokens (see :mod:`ironart.palette`) or '#hex'; conversion to linear is done here.
"""

import bpy

from . import palette


# ---------------------------------------------------------------------------------------------
# tiny node-graph builder
# ---------------------------------------------------------------------------------------------
def sock(coll, name):
    """Socket by identifier *or* display name (some 4.0 sockets, e.g. the Hair BSDF's
    'Random Color', have identifiers that differ from their names)."""
    s = coll.get(name)
    if s is None:
        s = next((x for x in coll if x.name == name), None)
    if s is None:
        raise KeyError(name)
    return s


class NB:
    """Minimal helper around a node tree: ``nb.node(type, inputs={...}, **props)`` and ``nb.link``.

    Input values may be plain values (assigned to ``default_value``) or output sockets (linked).
    Colour inputs accept palette tokens / '#hex' strings (sRGB, converted to linear) or 3/4-tuples
    (taken as *linear* values).
    """

    def __init__(self, tree):
        self.tree = tree
        self.nodes = tree.nodes
        self.links = tree.links

    def node(self, kind, inputs=None, **props):
        n = self.nodes.new(kind)
        for k, v in props.items():
            setattr(n, k, v)
        for k, v in (inputs or {}).items():
            self.set(sock(n.inputs, k), v)
        return n

    def set(self, sock, value):
        if isinstance(value, bpy.types.NodeSocket):
            self.links.new(value, sock)
        elif isinstance(value, str):
            sock.default_value = palette.lin4(value) if len(sock.default_value) == 4 else palette.lin(value)
        elif isinstance(value, (tuple, list)) and hasattr(sock.default_value, "__len__") \
                and len(sock.default_value) == 4 and len(value) == 3:
            sock.default_value = tuple(value) + (1.0,)        # tuples are LINEAR colours
        else:
            sock.default_value = value
        return sock

    def link(self, out, inp):
        self.links.new(out, inp)

    # common snippets -------------------------------------------------------------------------
    def coord(self, kind="UV"):
        """Texture coordinate output: 'UV', 'Object', 'Generated', 'Normal'..."""
        tc = self.nodes.get("_TexCoord") or self.node("ShaderNodeTexCoord", name="_TexCoord")
        return tc.outputs[kind]

    def mapping(self, vec, scale=(1, 1, 1), loc=(0, 0, 0), rot=(0, 0, 0)):
        m = self.node("ShaderNodeMapping")
        self.link(vec, m.inputs["Vector"])
        m.inputs["Scale"].default_value = scale
        m.inputs["Location"].default_value = loc
        m.inputs["Rotation"].default_value = rot
        return m.outputs[0]

    def noise(self, vec=None, scale=5.0, detail=4.0, roughness=0.55, distortion=0.0):
        n = self.node("ShaderNodeTexNoise", inputs={"Scale": scale, "Detail": detail,
                                                    "Roughness": roughness, "Distortion": distortion})
        if vec is not None:
            self.link(vec, n.inputs["Vector"])
        return n

    def ramp(self, fac, stops, interpolation="LINEAR"):
        """Colour ramp. ``stops`` = [(pos, colour_token_or_rgba), ...]."""
        r = self.node("ShaderNodeValToRGB")
        cr = r.color_ramp
        cr.interpolation = interpolation
        while len(cr.elements) < len(stops):
            cr.elements.new(0.5)
        for el, (pos, col) in zip(cr.elements, stops):
            el.position = pos
            el.color = palette.lin4(col) if isinstance(col, str) else tuple(col)
        self.link(fac, r.inputs[0])
        return r.outputs["Color"]

    def mix(self, a, b, fac, blend="MIX", clamp=True):
        """Colour mix (ShaderNodeMix, RGBA). ``a``/``b`` sockets or colours."""
        m = self.node("ShaderNodeMix", data_type="RGBA", blend_type=blend, clamp_result=clamp)
        self.set(m.inputs[0], fac)
        self.set(m.inputs[6], a)
        self.set(m.inputs[7], b)
        return m.outputs[2]

    def math(self, op, a, b=0.0, clamp=False):
        m = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        self.set(m.inputs[0], a)
        self.set(m.inputs[1], b)
        return m.outputs[0]

    def maprange(self, val, a0, a1, b0=0.0, b1=1.0, clamp=True, interp="LINEAR"):
        m = self.node("ShaderNodeMapRange", interpolation_type=interp, clamp=clamp)
        self.set(m.inputs["Value"], val)
        m.inputs["From Min"].default_value = a0
        m.inputs["From Max"].default_value = a1
        m.inputs["To Min"].default_value = b0
        m.inputs["To Max"].default_value = b1
        return m.outputs[0]

    def bump(self, height, strength=0.3, distance=0.02, normal=None):
        b = self.node("ShaderNodeBump", inputs={"Strength": strength, "Distance": distance})
        self.link(height, b.inputs["Height"])
        if normal is not None:
            self.link(normal, b.inputs["Normal"])
        return b.outputs[0]

    def attr(self, name, kind="GEOMETRY"):
        a = self.node("ShaderNodeAttribute", attribute_name=name, attribute_type=kind)
        return a

    def principled(self, **inputs):
        p = self.nodes.get("Principled BSDF") or self.node("ShaderNodeBsdfPrincipled")
        for k, v in inputs.items():
            self.set(sock(p.inputs, k.replace("_", " ")), v)
        return p

    def output(self, shader):
        out = None
        for n in self.nodes:
            if n.bl_idname == "ShaderNodeOutputMaterial":
                out = n
        out = out or self.node("ShaderNodeOutputMaterial")
        out.target = "ALL"
        self.link(shader, out.inputs["Surface"])
        return out


def new(name, reuse=True):
    """New node material (or the cached one). Returns ``(material, NB, created)``."""
    mat = bpy.data.materials.get(name)
    if mat is not None and reuse:
        return mat, NB(mat.node_tree), False
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nb = NB(mat.node_tree)
    for n in list(nb.nodes):
        if n.bl_idname != "ShaderNodeOutputMaterial":
            nb.nodes.remove(n)
    return mat, nb, True


def _vary(nb, color, amount=0.12, scale=3.0, vec=None, dark=None, light=None, detail=3.0):
    """Base colour with low-frequency hand-painted variation (darker/lighter blotches)."""
    n = nb.noise(vec if vec is not None else nb.coord("Object"), scale=scale, detail=detail)
    dark = dark or tuple(c * (1.0 - amount * 1.6) for c in palette.lin(color)) + (1.0,)
    light = light or tuple(min(1.0, c * (1.0 + amount)) for c in palette.lin(color)) + (1.0,)
    return nb.ramp(n.outputs["Fac"], [(0.3, dark), (0.5, palette.lin4(color)), (0.7, light)])


def assign(obj, *mats):
    """Append materials to an object's slots (in order)."""
    for m in mats:
        obj.data.materials.append(m)
    return obj


# ---------------------------------------------------------------------------------------------
# generic
# ---------------------------------------------------------------------------------------------
def principled(name, color="#808080", roughness=0.6, metallic=0.0, specular=0.4, vary=0.0,
               vary_scale=3.0, coat=0.0, sheen=0.0):
    mat, nb, created = new(name)
    if not created:
        return mat
    base = _vary(nb, color, vary, vary_scale) if vary > 0 else color
    p = nb.principled(Base_Color=base, Roughness=roughness, Metallic=metallic,
                      Specular_IOR_Level=specular, Coat_Weight=coat, Sheen_Weight=sheen)
    nb.output(p.outputs[0])
    return mat


def flat(name, color="#FFFFFF", strength=1.0):
    """Unlit emission colour (masks, debug, pure-white tint plates)."""
    mat, nb, created = new(name)
    if created:
        e = nb.node("ShaderNodeEmission", inputs={"Color": color, "Strength": strength})
        nb.output(e.outputs[0])
    return mat


def vertex_color(name, attr="Col", roughness=0.85, specular=0.25):
    """Albedo from a mesh colour attribute (terrain painted in numpy, merged props...)."""
    mat, nb, created = new(name)
    if created:
        a = nb.attr(attr)
        p = nb.principled(Base_Color=a.outputs["Color"], Roughness=roughness,
                          Specular_IOR_Level=specular)
        nb.output(p.outputs[0])
    return mat


def image(name, path, roughness=0.85, specular=0.2, interpolation="Cubic", colorspace="sRGB",
          roughness_path=None):
    """Albedo from an image file mapped on the UVs (terrain albedo baked by numpy)."""
    mat, nb, created = new(name)
    if created:
        img = bpy.data.images.load(path, check_existing=True)
        img.colorspace_settings.name = colorspace
        t = nb.node("ShaderNodeTexImage", image=img, interpolation=interpolation,
                    extension="EXTEND")
        nb.link(nb.coord("UV"), t.inputs["Vector"])
        rough = roughness
        if roughness_path:
            rimg = bpy.data.images.load(roughness_path, check_existing=True)
            rimg.colorspace_settings.name = "Non-Color"
            rt = nb.node("ShaderNodeTexImage", image=rimg, interpolation="Linear",
                         extension="EXTEND")
            nb.link(nb.coord("UV"), rt.inputs["Vector"])
            rough = rt.outputs["Color"]
        p = nb.principled(Base_Color=t.outputs["Color"], Roughness=rough,
                          Specular_IOR_Level=specular)
        nb.output(p.outputs[0])
    return mat


# ---------------------------------------------------------------------------------------------
# architecture
# ---------------------------------------------------------------------------------------------
def stone_wall(name="Stone", color="stone", mortar="mortar", block=(0.55, 0.28), vary=0.16,
               bump=0.35, roughness=0.85):
    """Grey ashlar blocks (UV metres). Block colour varies per brick; soft mortar lines."""
    mat, nb, created = new(name)
    if not created:
        return mat
    uv = nb.coord("UV")
    br = nb.node("ShaderNodeTexBrick", inputs={
        "Scale": 1.0, "Mortar Size": 0.018, "Mortar Smooth": 0.35, "Bias": 0.0,
        "Brick Width": block[0], "Row Height": block[1],
        "Color1": tuple(c * 0.86 for c in palette.lin(color)) + (1,),
        "Color2": tuple(min(1, c * 1.12) for c in palette.lin(color)) + (1,),
        "Mortar": mortar})
    br.offset = 0.5
    br.squash = 1.0
    nb.link(uv, br.inputs["Vector"])
    n = nb.noise(nb.coord("Object"), scale=2.5, detail=3)
    stain = nb.ramp(n.outputs["Fac"], [(0.35, (0.75, 0.75, 0.75, 1)), (0.65, (1.08, 1.06, 1.02, 1))])
    base = nb.mix(br.outputs["Color"], stain, 1.0, blend="MULTIPLY")
    fine = nb.noise(uv, scale=14.0, detail=6)
    height = nb.math("SUBTRACT", nb.math("MULTIPLY", br.outputs["Fac"], -1.0),
                     nb.math("MULTIPLY", fine.outputs["Fac"], 0.15))
    p = nb.principled(Base_Color=base, Roughness=roughness, Specular_IOR_Level=0.25,
                      Normal=nb.bump(height, bump, 0.02))
    nb.output(p.outputs[0])
    return mat


def roof_tiles(name="RoofTile", color="roof_tile", channel=0.16, course=0.22, bump=0.6,
               roughness=0.42, glaze=0.25):
    """Glazed barrel-tile roof (UV metres: u along the eave, v down/up the slope).

    Channels (tile rows running down the slope) every ``channel`` m, tile courses every ``course``.
    """
    mat, nb, created = new(name)
    if not created:
        return mat
    uv = nb.coord("UV")
    sep = nb.node("ShaderNodeSeparateXYZ")
    nb.link(uv, sep.inputs[0])
    import math as _m
    # rounded barrel profile across u: |sin|
    u = nb.math("MULTIPLY", sep.outputs["X"], _m.pi / channel)
    prof = nb.math("POWER", nb.math("ABSOLUTE", nb.math("SINE", u)), 0.6)
    v = nb.math("MULTIPLY", sep.outputs["Y"], 1.0 / course)
    vfrac = nb.math("FRACT", v)
    lip = nb.maprange(vfrac, 0.0, 0.18, 1.0, 0.0)
    height = nb.math("SUBTRACT", prof, nb.math("MULTIPLY", lip, 0.35))
    lin = palette.lin(color)
    dark = tuple(c * 0.55 for c in lin) + (1,)
    light = tuple(min(1, c * 1.25) for c in lin) + (1,)
    col = nb.ramp(height, [(0.0, dark), (0.55, palette.lin4(color)), (1.0, light)])
    col = nb.mix(col, _vary(nb, color, 0.12, 1.5), 0.35)
    p = nb.principled(Base_Color=col, Roughness=roughness, Specular_IOR_Level=0.5,
                      Coat_Weight=glaze, Coat_Roughness=0.25,
                      Normal=nb.bump(height, bump, 0.03))
    nb.output(p.outputs[0])
    return mat


def lacquer(name="Lacquer", color="lacquer", roughness=0.32, coat=1.0, coat_roughness=0.06,
            vary=0.08):
    """Red (or black) lacquer: deep base + clear glossy coat; very subtle brushing variation."""
    mat, nb, created = new(name)
    if created:
        base = _vary(nb, color, vary, 4.0) if vary else color
        p = nb.principled(Base_Color=base, Roughness=roughness, Specular_IOR_Level=0.45,
                          Coat_Weight=coat, Coat_Roughness=coat_roughness)
        nb.output(p.outputs[0])
    return mat


def gold_leaf(name="Gold", color="gold", roughness=0.28, vary=0.1):
    mat, nb, created = new(name)
    if created:
        base = _vary(nb, color, vary, 8.0)
        n = nb.noise(nb.coord("Object"), scale=30.0, detail=2)
        rough = nb.maprange(n.outputs["Fac"], 0.3, 0.7, roughness * 0.7, roughness * 1.4)
        p = nb.principled(Base_Color=base, Metallic=1.0, Roughness=rough)
        nb.output(p.outputs[0])
    return mat


def dark_wood(name="DarkWood", color="dark_wood", grain_scale=6.0, roughness=0.45, coat=0.4):
    """Lacquered dark timber; grain along local X (UV u)."""
    mat, nb, created = new(name)
    if not created:
        return mat
    vec = nb.mapping(nb.coord("UV"), scale=(0.5, grain_scale, 1.0))
    w = nb.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="Y",
                wave_profile="SIN", inputs={"Scale": 3.0, "Distortion": 6.0, "Detail": 3.0,
                                            "Detail Scale": 1.5})
    nb.link(vec, w.inputs["Vector"])
    lin = palette.lin(color)
    col = nb.ramp(w.outputs["Fac"], [(0.0, tuple(c * 0.7 for c in lin) + (1,)),
                                     (1.0, tuple(min(1, c * 1.25) for c in lin) + (1,))])
    p = nb.principled(Base_Color=col, Roughness=roughness, Coat_Weight=coat, Coat_Roughness=0.15,
                      Normal=nb.bump(w.outputs["Fac"], 0.08, 0.01))
    nb.output(p.outputs[0])
    return mat


def plaster(name="Plaster", color="plaster", vary=0.08):
    return principled(name, color, roughness=0.9, specular=0.2, vary=vary, vary_scale=2.0)


# ---------------------------------------------------------------------------------------------
# cloth, armour, paper
# ---------------------------------------------------------------------------------------------
def cloth(name="Cloth", color="silk_red", sheen=0.5, roughness=0.75, weave=0.0, vary=0.08):
    """Silk / cotton.  For tintable areas use :func:`white_cloth`."""
    mat, nb, created = new(name)
    if not created:
        return mat
    base = _vary(nb, color, vary, 3.0) if vary else color
    kw = {}
    if weave > 0:
        w = nb.noise(nb.mapping(nb.coord("UV"), scale=(60, 60, 60)), scale=8.0, detail=1)
        kw["Normal"] = nb.bump(w.outputs["Fac"], weave, 0.002)
    p = nb.principled(Base_Color=base, Roughness=roughness, Sheen_Weight=sheen,
                      Sheen_Roughness=0.4, Specular_IOR_Level=0.3, **kw)
    nb.output(p.outputs[0])
    return mat


def white_cloth(name="ClothWhite", roughness=0.8):
    """**Pure white** tintable cloth (albedo exactly 1.0, no sheen, no variation).

    The runtime multiplies these pixels by the faction colour, so any hue here would shift the
    faction colour.  Shading (grey shadows) is fine and desired.
    """
    mat, nb, created = new(name)
    if created:
        p = nb.principled(Base_Color=(1, 1, 1, 1), Roughness=roughness, Specular_IOR_Level=0.2)
        nb.output(p.outputs[0])
    return mat


def iron(name="Iron", color="iron", roughness=0.42, metallic=0.85, vary=0.12):
    mat, nb, created = new(name)
    if created:
        base = _vary(nb, color, vary, 6.0)
        n = nb.noise(nb.coord("Object"), scale=25.0, detail=3)
        rough = nb.maprange(n.outputs["Fac"], 0.3, 0.7, roughness * 0.75, roughness * 1.3)
        p = nb.principled(Base_Color=base, Metallic=metallic, Roughness=rough)
        nb.output(p.outputs[0])
    return mat


def lamellar(name="Lamellar", color="iron", lacing="lacing_red", plate=(0.026, 0.055),
             metallic=0.75, roughness=0.42, bump=0.8, vary=0.15):
    """Lamellar armour: staggered rows of small plates (UV metres; u around, v down) with
    coloured lacing showing in the gaps.  ``color`` 'iron' / 'bronze' / '#hex'."""
    mat, nb, created = new(name)
    if not created:
        return mat
    uv = nb.coord("UV")
    br = nb.node("ShaderNodeTexBrick", inputs={
        "Scale": 1.0, "Mortar Size": plate[0] * 0.07, "Mortar Smooth": 0.5, "Bias": 0.0,
        "Brick Width": plate[0], "Row Height": plate[1],
        "Color1": (1, 1, 1, 1), "Color2": (0.8, 0.8, 0.8, 1), "Mortar": (0, 0, 0, 1)})
    br.offset = 0.5
    nb.link(uv, br.inputs["Vector"])
    # plate shading: each plate is slightly convex and the lower edge overlaps the next row
    sep = nb.node("ShaderNodeSeparateXYZ")
    nb.link(uv, sep.inputs[0])
    vrow = nb.math("FRACT", nb.math("DIVIDE", sep.outputs["Y"], plate[1]))
    slope = nb.maprange(vrow, 0.0, 1.0, 0.0, 1.0)
    height = nb.math("MULTIPLY", nb.math("SUBTRACT", 1.0, br.outputs["Fac"]), slope)
    plate_col = _vary(nb, color, vary, 9.0)
    tone = nb.mix((0.55, 0.55, 0.55, 1), (1.0, 1.0, 1.0, 1), br.outputs["Color"])
    plate_col = nb.mix(plate_col, tone, 1.0, blend="MULTIPLY")
    col = nb.mix(lacing, plate_col, nb.math("SUBTRACT", 1.0, br.outputs["Fac"]))
    metal = nb.math("MULTIPLY", nb.math("SUBTRACT", 1.0, br.outputs["Fac"]), metallic)
    p = nb.principled(Base_Color=col, Metallic=metal, Roughness=roughness,
                      Normal=nb.bump(height, bump, 0.004))
    nb.output(p.outputs[0])
    return mat


def parchment(name="Parchment", color="paper", fibre=0.5, stain=0.12, roughness=0.92):
    """Warm paper: fibres + soft stains (Object coords, works without UVs)."""
    mat, nb, created = new(name)
    if not created:
        return mat
    obj = nb.coord("Object")
    f = nb.noise(nb.mapping(obj, scale=(40, 6, 40)), scale=6.0, detail=8, roughness=0.7)
    st = nb.noise(obj, scale=1.4, detail=4)
    lin = palette.lin(color)
    col = nb.ramp(st.outputs["Fac"], [(0.35, tuple(c * (1 - stain * 1.5) for c in lin) + (1,)),
                                      (0.6, palette.lin4(color)),
                                      (0.8, tuple(min(1, c * 1.03) for c in lin) + (1,))])
    fib = nb.ramp(f.outputs["Fac"], [(0.4, (1 - 0.08 * fibre,) * 3 + (1,)), (0.6, (1, 1, 1, 1))])
    col = nb.mix(col, fib, 1.0, blend="MULTIPLY")
    p = nb.principled(Base_Color=col, Roughness=roughness, Specular_IOR_Level=0.15,
                      Normal=nb.bump(f.outputs["Fac"], 0.05, 0.002))
    nb.output(p.outputs[0])
    return mat


# ---------------------------------------------------------------------------------------------
# nature
# ---------------------------------------------------------------------------------------------
def water(name="Water", deep="sea_deep", shallow="sea_shallow", roughness=0.18, ripple=0.15,
          depth_attr=None):
    """Map water.  With ``depth_attr`` (0 = coast, 1 = deep) the colour ramps shallow -> deep."""
    mat, nb, created = new(name)
    if not created:
        return mat
    if depth_attr:
        d = nb.attr(depth_attr).outputs["Fac"]
        col = nb.ramp(d, [(0.0, shallow), (1.0, deep)])
    else:
        col = deep
    rip = nb.noise(nb.mapping(nb.coord("Object"), scale=(3, 8, 3)), scale=12.0, detail=2)
    p = nb.principled(Base_Color=col, Roughness=roughness, Specular_IOR_Level=0.35,
                      Normal=nb.bump(rip.outputs["Fac"], ripple, 0.01))
    nb.output(p.outputs[0])
    return mat


def foliage(name="Foliage", color="forest", vary=0.22, roughness=0.8, translucency=0.12):
    """Tree canopies: varied greens, soft sheen, a little translucency (back-lit glow)."""
    mat, nb, created = new(name)
    if not created:
        return mat
    obj = nb.coord("Object")
    base = _vary(nb, color, vary, 4.0, vec=obj)
    leaf = nb.noise(obj, scale=60.0, detail=2)
    col = nb.mix(base, nb.ramp(leaf.outputs["Fac"], [(0.35, (0.8, 0.85, 0.75, 1)), (0.65, (1.1, 1.1, 1.0, 1))]),
                 1.0, blend="MULTIPLY")
    p = nb.principled(Base_Color=col, Roughness=roughness, Specular_IOR_Level=0.2,
                      Sheen_Weight=0.2, Normal=nb.bump(leaf.outputs["Fac"], 0.25, 0.02))
    shader = p.outputs[0]
    if translucency > 0:
        tr = nb.node("ShaderNodeBsdfTranslucent")
        nb.link(col, tr.inputs["Color"])
        mx = nb.node("ShaderNodeMixShader", inputs={"Fac": translucency})
        nb.link(p.outputs[0], mx.inputs[1])
        nb.link(tr.outputs[0], mx.inputs[2])
        shader = mx.outputs[0]
    nb.output(shader)
    return mat


def grass_ground(name="Ground", color="grass", dry="plain", vary=0.25, scale=1.2):
    """Ground for hex tiles / sprite bases: green-to-ochre blotches + fine speckle (Object coords)."""
    mat, nb, created = new(name)
    if not created:
        return mat
    obj = nb.coord("Object")
    n = nb.noise(obj, scale=scale, detail=5)
    col = nb.ramp(n.outputs["Fac"], [(0.3, color), (0.75, dry)])
    sp = nb.noise(obj, scale=40.0, detail=2)
    col = nb.mix(col, nb.ramp(sp.outputs["Fac"], [(0.3, (0.85, 0.85, 0.8, 1)), (0.7, (1.1, 1.08, 1.0, 1))]),
                 1.0, blend="MULTIPLY")
    p = nb.principled(Base_Color=col, Roughness=0.92, Specular_IOR_Level=0.15,
                      Normal=nb.bump(sp.outputs["Fac"], 0.15, 0.01))
    nb.output(p.outputs[0])
    return mat


def rock(name="Rock", color="rock", vary=0.2):
    mat, nb, created = new(name)
    if created:
        obj = nb.coord("Object")
        base = _vary(nb, color, vary, 3.0, vec=obj)
        n = nb.noise(obj, scale=9.0, detail=6, roughness=0.65)
        p = nb.principled(Base_Color=base, Roughness=0.85, Specular_IOR_Level=0.25,
                          Normal=nb.bump(n.outputs["Fac"], 0.5, 0.05))
        nb.output(p.outputs[0])
    return mat


# ---------------------------------------------------------------------------------------------
# people
# ---------------------------------------------------------------------------------------------
def skin(name="Skin", color="skin", sss=0.25, roughness=0.48, blush=0.25, vary=0.06,
         pores=0.05, blush_attr="blush"):
    """Warm skin with subsurface.  ``blush_attr`` (mesh float attribute 0..1, optional) reddens
    cheeks/nose/ears; missing attributes read as 0 so it is safe to leave."""
    mat, nb, created = new(name)
    if not created:
        return mat
    obj = nb.coord("Object")
    base = _vary(nb, color, vary, 6.0, vec=obj)
    bl = nb.attr(blush_attr).outputs["Fac"]
    base = nb.mix(base, "#B0584A", nb.math("MULTIPLY", bl, blush))
    pn = nb.noise(obj, scale=160.0, detail=2)
    p = nb.principled(Base_Color=base, Roughness=roughness, Specular_IOR_Level=0.45,
                      Subsurface_Weight=sss, Subsurface_Radius=(1.0, 0.4, 0.25),
                      Subsurface_Scale=0.006, Normal=nb.bump(pn.outputs["Fac"], pores, 0.001))
    nb.output(p.outputs[0])
    return mat


def hair_strands(name="HairStrands", color="hair_black", melanin=None, redness=0.25,
                 roughness=0.35, random_color=0.1, radial_roughness=0.4):
    """Principled Hair BSDF for curve hair (beards, brows, plumes, buns).

    Natural hair: pass ``melanin`` (0 blond/white .. 1 black) - physically based, never greyish.
    Dyed/horsehair colours (red tassels): leave ``melanin=None`` and give ``color``.
    """
    mat, nb, created = new(name)
    if created:
        if melanin is not None:
            h = nb.node("ShaderNodeBsdfHairPrincipled", parametrization="MELANIN")
            sock(h.inputs, "Melanin").default_value = melanin
            sock(h.inputs, "Melanin Redness").default_value = redness
        else:
            h = nb.node("ShaderNodeBsdfHairPrincipled", parametrization="COLOR")
            nb.set(sock(h.inputs, "Color"), color)
        sock(h.inputs, "Roughness").default_value = roughness
        sock(h.inputs, "Radial Roughness").default_value = radial_roughness
        sock(h.inputs, "Random Color").default_value = random_color
        nb.output(h.outputs[0])
    return mat


def hair_mesh(name="HairMesh", color="hair_black", strand_scale=180.0, roughness=0.45,
              direction="Z"):
    """Hair/beard as a mesh shell: anisotropic strand stripes along ``direction`` (object axis)."""
    mat, nb, created = new(name)
    if not created:
        return mat
    obj = nb.coord("Object")
    sc = {"X": (1, strand_scale, strand_scale), "Y": (strand_scale, 1, strand_scale),
          "Z": (strand_scale, strand_scale, 2.0)}[direction]
    n = nb.noise(nb.mapping(obj, scale=sc), scale=1.0, detail=3, distortion=0.3)
    lin = palette.lin(color)
    col = nb.ramp(n.outputs["Fac"], [(0.3, tuple(c * 0.5 for c in lin) + (1,)),
                                     (0.7, tuple(min(1, c * 1.8 + 0.02) for c in lin) + (1,))])
    p = nb.principled(Base_Color=col, Roughness=roughness, Specular_IOR_Level=0.5,
                      Sheen_Weight=0.3, Normal=nb.bump(n.outputs["Fac"], 0.6, 0.004))
    nb.output(p.outputs[0])
    return mat


def eye(name="Eye", iris="iris", sclera="eye_white", iris_radius=0.5, pupil_radius=0.2,
        axis="-Y"):
    """Eyeball for a unit sphere looking along ``axis`` (object space): sclera, iris, pupil,
    glossy cornea.  Scale the sphere object; the pattern is in object coordinates."""
    mat, nb, created = new(name)
    if not created:
        return mat
    obj = nb.coord("Object")
    sep = nb.node("ShaderNodeSeparateXYZ")
    nb.link(obj, sep.inputs[0])
    a, b = {"-Y": ("X", "Z"), "Y": ("X", "Z"), "-X": ("Y", "Z"), "X": ("Y", "Z")}[axis]
    r = nb.math("SQRT", nb.math("ADD", nb.math("POWER", sep.outputs[a], 2.0),
                                nb.math("POWER", sep.outputs[b], 2.0)))
    face = sep.outputs[axis[-1]]
    front = nb.math("LESS_THAN", face, 0.0) if axis.startswith("-") else nb.math("GREATER_THAN", face, 0.0)
    col = nb.ramp(r, [(pupil_radius - 0.02, "#080605"), (pupil_radius + 0.03, iris),
                      (iris_radius - 0.05, "#5A3A22"), (iris_radius, "#24160E"),
                      (iris_radius + 0.03, sclera)])
    col = nb.mix(sclera, col, front)
    p = nb.principled(Base_Color=col, Roughness=0.08, Specular_IOR_Level=0.6, Coat_Weight=0.6,
                      Coat_Roughness=0.02)
    nb.output(p.outputs[0])
    return mat


# ---------------------------------------------------------------------------------------------
# NPR paint option
# ---------------------------------------------------------------------------------------------
def paint(mat, amount=0.35, size=0.85, smooth=0.12):
    """Mix a banded Toon diffuse into ``mat`` (the Cycles-compatible "paint" shading).

    The toon colour is taken from the material's Principled ``Base Color`` (linked or value).
    Idempotent: calling again just updates the parameters.
    """
    nb = NB(mat.node_tree)
    toon = nb.nodes.get("_PaintToon")
    if toon is None:
        out = None
        for n in nb.nodes:
            if n.bl_idname == "ShaderNodeOutputMaterial":
                out = n
        if out is None or not out.inputs["Surface"].is_linked:
            return mat
        src = out.inputs["Surface"].links[0].from_socket
        toon = nb.node("ShaderNodeBsdfToon", name="_PaintToon", component="DIFFUSE")
        p = next((n for n in nb.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)
        if p is not None:
            bc = p.inputs["Base Color"]
            if bc.is_linked:
                nb.link(bc.links[0].from_socket, toon.inputs["Color"])
            else:
                toon.inputs["Color"].default_value = bc.default_value
            if p.inputs["Normal"].is_linked:
                nb.link(p.inputs["Normal"].links[0].from_socket, toon.inputs["Normal"])
        mx = nb.node("ShaderNodeMixShader", name="_PaintMix")
        nb.link(src, mx.inputs[1])
        nb.link(toon.outputs[0], mx.inputs[2])
        nb.link(mx.outputs[0], out.inputs["Surface"])
    toon.inputs["Size"].default_value = size
    toon.inputs["Smooth"].default_value = smooth
    nb.nodes["_PaintMix"].inputs["Fac"].default_value = amount
    return mat


def paint_all(amount=0.35, size=0.85, smooth=0.12, skip=("Eye",)):
    """Apply :func:`paint` to every material in the file except names starting with ``skip``."""
    for m in bpy.data.materials:
        if m.use_nodes and not m.name.startswith(tuple(skip)):
            paint(m, amount, size, smooth)
