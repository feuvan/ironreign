"""Icons family: PBR still-life materials (Cycles, node-built, procedural detail).

Every factory caches by name and returns a ``bpy.types.Material`` built on one Principled BSDF
(Blender 4.0 socket names).  Pattern scales assume the icon props' scene scale: a composition
is ~2 units across, so a "small" detail is ~0.01-0.05 units.  Texture space is the object's
local space (``Object`` coordinates) unless noted, so builders keep their objects unapplied
(location / rotation on the object) and the grain / weave follows the part.

Colours are sRGB hex strings (palette tokens also work) converted to linear here.  Metals use
measured-looking F0 colours (gold, bronze, iron, steel); dielectrics stay within albedo
0.03-0.85 so Filmic highlights roll off instead of clipping.
"""

import bpy

from . import palette
from .materials import NB, sock

# ---------------------------------------------------------------------------------------------
# vocabulary
# ---------------------------------------------------------------------------------------------


def L(c, k=1.0):
    r, g, b = palette.lin(c)
    return (min(1.0, r * k), min(1.0, g * k), min(1.0, b * k), 1.0)


def _new(name):
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat, None
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nb = NB(mat.node_tree)
    for n in list(nb.nodes):
        if n.bl_idname != "ShaderNodeOutputMaterial":
            nb.nodes.remove(n)
    return mat, V(nb)


class V:
    """Small node vocabulary (sockets in, sockets out)."""

    def __init__(self, nb):
        self.nb = nb

    def obj(self):
        return self.nb.coord("Object")

    def uv(self):
        return self.nb.coord("UV")

    def scale(self, vec, s, loc=(0, 0, 0), rot=(0, 0, 0)):
        return self.nb.mapping(vec, scale=s if isinstance(s, tuple) else (s, s, s), loc=loc,
                               rot=rot)

    def sep(self, vec):
        s = self.nb.node("ShaderNodeSeparateXYZ")
        self.nb.link(vec, s.inputs[0])
        return s.outputs

    def noise(self, vec, scale=4.0, detail=4.0, rough=0.55, dist=0.0):
        n = self.nb.node("ShaderNodeTexNoise", inputs={"Scale": scale, "Detail": detail,
                                                       "Roughness": rough, "Distortion": dist})
        self.nb.link(vec, n.inputs["Vector"])
        return n.outputs["Fac"]

    def voronoi(self, vec, scale=4.0, feature="F1", out="Distance", rand=1.0):
        v = self.nb.node("ShaderNodeTexVoronoi", feature=feature,
                         inputs={"Scale": scale, "Randomness": rand})
        self.nb.link(vec, v.inputs["Vector"])
        return v.outputs[out]

    def wave(self, vec, scale=3.0, dist=4.0, detail=2.0, kind="BANDS", direction="X",
             profile="SIN", dscale=1.0):
        w = self.nb.node("ShaderNodeTexWave", wave_type=kind, wave_profile=profile,
                         inputs={"Scale": scale, "Distortion": dist, "Detail": detail,
                                 "Detail Scale": dscale})
        if kind == "BANDS":
            w.bands_direction = direction
        else:
            w.rings_direction = direction
        self.nb.link(vec, w.inputs["Vector"])
        return w.outputs["Fac"]

    def ramp(self, fac, stops, interp="LINEAR"):
        return self.nb.ramp(fac, [(p, L(c) if isinstance(c, str) else c) for p, c in stops],
                            interp)

    def mr(self, val, a0, a1, b0=0.0, b1=1.0, interp="LINEAR", clamp=True):
        return self.nb.maprange(val, a0, a1, b0, b1, clamp=clamp, interp=interp)

    def m(self, op, a, b=0.0, clamp=False):
        return self.nb.math(op, a, b, clamp)

    def mix(self, a, b, fac, blend="MIX"):
        return self.nb.mix(L(a) if isinstance(a, str) else a, L(b) if isinstance(b, str) else b,
                           fac, blend=blend)

    def gray(self, v):
        c = self.nb.node("ShaderNodeCombineColor")
        for k in ("Red", "Green", "Blue"):
            self.nb.set(c.inputs[k], v)
        return c.outputs[0]

    def mul(self, col, f):
        return self.nb.mix(col, self.gray(f), 1.0, blend="MULTIPLY")

    def bump(self, height, strength=0.3, distance=0.02, normal=None):
        return self.nb.bump(height, strength, distance, normal)

    def ao(self, distance=0.08, only_local=True, samples=8):
        n = self.nb.node("ShaderNodeAmbientOcclusion", samples=samples, only_local=only_local,
                         inputs={"Distance": distance})
        return n.outputs["AO"]

    def attr(self, name, out="Fac"):
        a = self.nb.node("ShaderNodeAttribute", attribute_name=name, attribute_type="GEOMETRY")
        return a.outputs[out]

    def facing(self, blend=0.5):
        lw = self.nb.node("ShaderNodeLayerWeight", inputs={"Blend": blend})
        return lw.outputs["Facing"]

    def obj_random(self):
        oi = self.nb.node("ShaderNodeObjectInfo")
        return oi.outputs["Random"]

    def image(self, img, vec=None, interp="Cubic", extension="CLIP"):
        t = self.nb.node("ShaderNodeTexImage", interpolation=interp, extension=extension)
        t.image = img
        if vec is not None:
            self.nb.link(vec, t.inputs["Vector"])
        return t

    def out(self, base, rough=0.5, metal=0.0, normal=None, spec=0.5, coat=0.0, coat_rough=0.05,
            sheen=0.0, sheen_tint=None, sheen_rough=0.5, sss=0.0, sss_radius=(0.1, 0.05, 0.03),
            sss_scale=0.05, emission=None, emission_strength=0.0, transmission=0.0, ior=1.5,
            aniso=0.0, alpha=1.0, coat_tint=None, spec_tint=None):
        kw = dict(Base_Color=base, Roughness=rough, Metallic=metal, Specular_IOR_Level=spec,
                  IOR=ior)
        if normal is not None:
            kw["Normal"] = normal
        if coat:
            kw["Coat_Weight"] = coat
            kw["Coat_Roughness"] = coat_rough
            if coat_tint is not None:
                kw["Coat_Tint"] = coat_tint
        if sheen:
            kw["Sheen_Weight"] = sheen
            kw["Sheen_Roughness"] = sheen_rough
            if sheen_tint is not None:
                kw["Sheen_Tint"] = sheen_tint
        if sss:
            kw["Subsurface_Weight"] = sss
            kw["Subsurface_Scale"] = sss_scale
        if emission is not None:
            kw["Emission_Color"] = emission
            kw["Emission_Strength"] = emission_strength
        if transmission:
            kw["Transmission_Weight"] = transmission
        if aniso:
            kw["Anisotropic"] = aniso
        if alpha != 1.0:
            kw["Alpha"] = alpha
        if spec_tint is not None:
            kw["Specular_Tint"] = spec_tint
        p = self.nb.principled(**kw)
        if sss:
            sock(p.inputs, "Subsurface Radius").default_value = sss_radius
        self.nb.output(p.outputs[0])
        return p


def _col(v, c, vary=0.0, scale=4.0, vec=None, dark=0.75, light=1.15):
    """Colour ``c`` with low-frequency hand-made variation."""
    if vary <= 0:
        return L(c)
    n = v.noise(vec if vec is not None else v.obj(), scale, 3.0, 0.5)
    return v.ramp(n, [(0.25, L(c, 1.0 - (1.0 - dark) * vary * 4)), (0.5, L(c)),
                      (0.75, L(c, 1.0 + (light - 1.0) * vary * 4))])


# ---------------------------------------------------------------------------------------------
# metals
# ---------------------------------------------------------------------------------------------
def gold(name="I_Gold", color="#E8B860", rough=0.2, vary=0.03, worn=0.0):
    """Polished gold (yuanbao, inlay, fittings).  F0 colour of real gold, low roughness with a
    faint smudge pattern; ``worn`` darkens cavities a little (old gilt)."""
    mat, v = _new(name)
    if v is None:
        return mat
    base = _col(v, color, vary, 2.5)
    n = v.noise(v.obj(), 7.0, 2.0, 0.5)
    r = v.mr(n, 0.25, 0.75, rough * 0.8, rough * 1.25)
    if worn > 0:
        ao = v.ao(0.06)
        base = v.mix(v.mul(base, 0.45), base, v.mr(ao, 0.3, 0.95, 1.0 - worn, 1.0))
    v.out(base, r, 1.0)
    return mat


def bronze(name="I_Bronze", color="#B4884E", patina="#4F8770", patina_amt=0.35, rough=0.3,
           dark="#3A2A1A", ao_dist=0.07, pscale=6.0):
    """Aged ritual bronze: warm metallic body, verdigris patina in cavities and blotches, dark
    grime in the deepest recesses, polished high points."""
    mat, v = _new(name)
    if v is None:
        return mat
    ao = v.ao(ao_dist)
    n = v.noise(v.obj(), pscale, 5.0, 0.62, 0.3)
    n2 = v.noise(v.obj(), pscale * 4.0, 3.0, 0.5)
    cav = v.mr(ao, 0.25, 0.85, 1.0, 0.0)                         # 1 in cavities
    blot = v.mr(n, 0.55, 0.72, 0.0, 1.0)
    pat = v.m("MAXIMUM", v.m("MULTIPLY", cav, 1.2), v.m("MULTIPLY", blot, 0.8))
    pat = v.m("MULTIPLY", pat, patina_amt * 1.6, clamp=True)
    metal_col = v.ramp(n2, [(0.3, L(color, 0.82)), (0.7, L(color, 1.08))])
    pcol = v.ramp(n2, [(0.2, L(patina, 0.75)), (0.8, L(patina, 1.15))])
    col = v.mix(metal_col, pcol, pat)
    col = v.mix(col, dark, v.m("MULTIPLY", v.mr(ao, 0.1, 0.45, 0.7, 0.0), 1.0, clamp=True))
    metal = v.mr(pat, 0.0, 1.0, 1.0, 0.0)
    r = v.mr(pat, 0.0, 1.0, rough, 0.78)
    nrm = v.bump(v.m("ADD", v.m("MULTIPLY", n2, 0.5), v.m("MULTIPLY", pat, 0.6)), 0.25, 0.01)
    v.out(col, r, metal, nrm)
    return mat


def steel(name="I_Steel", color="#C9CDD3", rough=0.2, vary=0.08, streak=(1.0, 1.0, 14.0)):
    """Bright forged steel (blades): stretched roughness streaks along local Z (the blade
    axis), cool F0, a faint darker temper line."""
    mat, v = _new(name)
    if v is None:
        return mat
    vec = v.scale(v.obj(), streak)
    n = v.noise(vec, 9.0, 4.0, 0.6)
    r = v.mr(n, 0.3, 0.7, rough * 0.6, rough * 1.7)
    col = v.ramp(n, [(0.3, L(color, 0.86)), (0.7, L(color, 1.04))])
    v.out(col, r, 1.0)
    return mat


def iron(name="I_Iron", color="#5A5E64", rough=0.42, rust="#6A3E22", rust_amt=0.15):
    """Dark wrought iron / black steel with faint rust in cavities."""
    mat, v = _new(name)
    if v is None:
        return mat
    ao = v.ao(0.05)
    n = v.noise(v.obj(), 14.0, 4.0, 0.6)
    col = v.ramp(n, [(0.3, L(color, 0.8)), (0.7, L(color, 1.1))])
    rf = v.m("MULTIPLY", v.mr(ao, 0.3, 0.9, 1.0, 0.0), rust_amt * 2.0, clamp=True)
    col = v.mix(col, rust, rf)
    v.out(col, v.mr(n, 0.3, 0.7, rough * 0.8, rough * 1.25), v.mr(rf, 0, 1, 0.95, 0.4))
    return mat


# ---------------------------------------------------------------------------------------------
# lacquer, wood, bamboo
# ---------------------------------------------------------------------------------------------
def lacquer(name="I_Lacquer", color="#8E2418", rough=0.38, coat_rough=0.045, vary=0.05,
            edge_wear=0.0, wear_color="#2A120C"):
    """Lacquer: deep base colour under a clear glossy coat; ``edge_wear`` darkens/varies cavities
    (old lacquer)."""
    mat, v = _new(name)
    if v is None:
        return mat
    col = _col(v, color, vary, 3.0)
    if edge_wear > 0:
        ao = v.ao(0.05)
        col = v.mix(col, wear_color, v.mr(ao, 0.2, 0.8, edge_wear, 0.0))
    v.out(col, rough, 0.0, spec=0.5, coat=1.0, coat_rough=coat_rough)
    return mat


def wood(name="I_Wood", color="#7A5232", grain="#4A2E1A", axis="Z", rough=0.55, scale=3.0,
         coat=0.0, ring=0.35, bump=0.15, vary=0.08):
    """Timber with long grain along local ``axis`` ('X', 'Y' or 'Z'): distorted wave bands +
    fine streak noise, darker latewood ``grain``, optional oil/lacquer ``coat``."""
    mat, v = _new(name)
    if v is None:
        return mat
    s = {"X": (0.12, 1.0, 1.0), "Y": (1.0, 0.12, 1.0), "Z": (1.0, 1.0, 0.12)}[axis]
    vec = v.scale(v.obj(), tuple(c * scale for c in s))
    w = v.wave(vec, 3.0, 5.0, 3.0, "RINGS", "SPHERICAL" if False else axis, "SIN", 1.2)
    fine = v.noise(v.scale(v.obj(), tuple(c * scale * 6 for c in s)), 6.0, 3.0, 0.6)
    f = v.m("ADD", v.m("MULTIPLY", w, 1.0 - ring), v.m("MULTIPLY", fine, ring))
    col = v.ramp(f, [(0.25, L(grain)), (0.75, L(color))])
    col = v.mul(col, v.mr(v.noise(v.obj(), 1.5, 2.0), 0.3, 0.7, 1.0 - vary, 1.0 + vary))
    v.out(col, v.mr(f, 0, 1, rough * 1.15, rough * 0.9), 0.0, v.bump(f, bump, 0.01), spec=0.4,
          coat=coat, coat_rough=0.12)
    return mat


def bamboo(name="I_Bamboo", color="#B89A58", node_color="#7A6232", axis="Z", rough=0.35):
    mat, v = _new(name)
    if v is None:
        return mat
    s = {"X": (0.2, 6.0, 6.0), "Y": (6.0, 0.2, 6.0), "Z": (6.0, 6.0, 0.2)}[axis]
    n = v.noise(v.scale(v.obj(), s), 8.0, 3.0, 0.6)
    col = v.ramp(n, [(0.3, L(color, 0.85)), (0.7, L(color, 1.08))])
    v.out(col, rough, 0.0, v.bump(n, 0.08, 0.01), spec=0.5, coat=0.3, coat_rough=0.2)
    return mat


# ---------------------------------------------------------------------------------------------
# stone, jade, ceramic
# ---------------------------------------------------------------------------------------------
def jade(name="I_Jade", color="#4E9A72", cloud="#C8DCC0", rough=0.12, sss=1.0, scale=0.05):
    """Nephrite: translucent green body (subsurface), milky clouds, polished coat."""
    mat, v = _new(name)
    if v is None:
        return mat
    n = v.noise(v.obj(), 3.5, 6.0, 0.6, 0.8)
    n2 = v.noise(v.obj(), 12.0, 3.0, 0.5)
    col = v.ramp(n, [(0.35, L(color, 0.75)), (0.55, L(color)), (0.75, L(cloud, 0.75))])
    col = v.mul(col, v.mr(n2, 0.3, 0.7, 0.92, 1.06))
    v.out(col, rough, 0.0, spec=0.5, sss=sss, sss_radius=(0.35, 0.7, 0.45), sss_scale=scale,
          coat=0.6, coat_rough=0.06)
    return mat


def ceramic(name="I_Ceramic", color="#9DB89C", rough=0.12, sss=0.15, vary=0.05, pool=None,
            crackle=0.0):
    """Glazed ceramic: base colour under a glossy glaze coat; ``pool`` darkens the glaze in
    cavities (glaze pooling); ``crackle`` adds fine crazing lines (celadon)."""
    mat, v = _new(name)
    if v is None:
        return mat
    col = _col(v, color, vary, 3.0)
    if pool:
        ao = v.ao(0.05)
        col = v.mix(col, pool, v.mr(ao, 0.3, 0.9, 0.8, 0.0))
    if crackle > 0:
        cr = v.voronoi(v.obj(), 26.0, "DISTANCE_TO_EDGE", "Distance")
        line = v.mr(cr, 0.0, 0.035, crackle, 0.0)
        col = v.mix(col, "#3A3A30", line)
    v.out(col, rough * 3.0, 0.0, spec=0.5, coat=1.0, coat_rough=rough * 0.4, sss=sss,
          sss_radius=(0.2, 0.2, 0.15), sss_scale=0.02)
    return mat


def stoneware(name="I_Stoneware", color="#5A3220", lip="#B07A44", rough=0.18, drip=0.7,
              zlo=0.2, zhi=0.9):
    """Brown-black glazed stoneware (wine jars): the glaze thins to a warm brown at the
    shoulder and lip (by local height between ``zlo`` and ``zhi``) with drips running down."""
    mat, v = _new(name)
    if v is None:
        return mat
    z = v.sep(v.obj())["Z"]
    n = v.noise(v.scale(v.obj(), (8.0, 8.0, 1.2)), 3.0, 4.0, 0.6)
    t = v.m("ADD", v.mr(z, zlo, zhi, 0.0, 1.0), v.m("MULTIPLY", v.m("SUBTRACT", n, 0.5), drip))
    col = v.ramp(t, [(0.45, L(color)), (0.75, L(lip))])
    n2 = v.noise(v.obj(), 18.0, 3.0, 0.5)
    col = v.mul(col, v.mr(n2, 0.3, 0.7, 0.9, 1.08))
    v.out(col, rough * 2.5, 0.0, spec=0.5, coat=1.0, coat_rough=rough * 0.35)
    return mat


def stone(name="I_Stone", color="#8C877C", dark="#5E5A52", rough=0.85, scale=6.0, bump=0.4):
    """Dressed stone / rock: mottled grey with darker pits, strong bump."""
    mat, v = _new(name)
    if v is None:
        return mat
    n = v.noise(v.obj(), scale, 6.0, 0.62)
    n2 = v.noise(v.obj(), scale * 4, 4.0, 0.6)
    col = v.ramp(v.m("ADD", v.m("MULTIPLY", n, 0.7), v.m("MULTIPLY", n2, 0.3)),
                 [(0.3, L(dark)), (0.7, L(color))])
    ao = v.ao(0.06)
    col = v.mul(col, v.mr(ao, 0.2, 0.9, 0.55, 1.0))
    v.out(col, rough, 0.0, v.bump(v.m("ADD", n, v.m("MULTIPLY", n2, 0.5)), bump, 0.02), spec=0.3)
    return mat


def masonry(name="I_Masonry", color="#8D877B", mortar="#5F5A51", block=(0.22, 0.11),
            vary=0.18, rough=0.85, axis="XZ"):
    """Brick / ashlar on a plane (``axis`` = the local plane of the face pattern; the Object
    coordinates are used so blocks stay square on every face of a box)."""
    mat, v = _new(name)
    if v is None:
        return mat
    o = v.sep(v.obj())
    comb = v.nb.node("ShaderNodeCombineXYZ")
    # use x+y along the wall run so the two visible faces of a wall both get courses
    v.nb.link(v.m("ADD", o["X"], o["Y"]), comb.inputs["X"])
    v.nb.link(o["Z"], comb.inputs["Y"])
    b = v.nb.node("ShaderNodeTexBrick", inputs={
        "Scale": 1.0, "Mortar Size": 0.012, "Mortar Smooth": 0.3, "Bias": 0.0,
        "Brick Width": block[0], "Row Height": block[1],
        "Color1": L(color, 1.08), "Color2": L(color, 0.82), "Mortar": L(mortar)})
    b.offset = 0.5
    b.offset_frequency = 2
    v.nb.link(comb.outputs[0], b.inputs["Vector"])
    n = v.noise(v.obj(), 9.0, 5.0, 0.6)
    col = v.mul(b.outputs["Color"], v.mr(n, 0.3, 0.7, 1.0 - vary, 1.0 + vary * 0.5))
    ao = v.ao(0.05)
    col = v.mul(col, v.mr(ao, 0.2, 0.9, 0.6, 1.0))
    h = v.m("ADD", v.m("MULTIPLY", v.m("SUBTRACT", 1.0, b.outputs["Fac"]), 1.0),
            v.m("MULTIPLY", n, 0.3))
    v.out(col, rough, 0.0, v.bump(h, 0.6, 0.015), spec=0.3)
    return mat


def plaster(name="I_Plaster", color="#E2D8C4", rough=0.9, grime="#8A7A62"):
    mat, v = _new(name)
    if v is None:
        return mat
    n = v.noise(v.obj(), 5.0, 5.0, 0.6)
    col = v.ramp(n, [(0.3, L(color, 0.9)), (0.7, L(color, 1.02))])
    z = v.sep(v.obj())["Z"]
    col = v.mix(col, grime, v.mr(z, 0.0, 0.15, 0.35, 0.0))
    v.out(col, rough, 0.0, v.bump(n, 0.15, 0.01), spec=0.3)
    return mat


def roof_tile(name="I_RoofTile", color="#4E575E", rough=0.55, pitch=0.06, axis="X"):
    """Grey fired roof tiles: alternating channel / cover rows (bands across local ``axis``),
    slightly glossy."""
    mat, v = _new(name)
    if v is None:
        return mat
    o = v.sep(v.obj())
    w = v.nb.node("ShaderNodeTexWave", wave_type="BANDS", wave_profile="SIN",
                  inputs={"Scale": 1.0 / pitch, "Distortion": 0.0, "Detail": 0.0})
    w.bands_direction = axis
    v.nb.link(v.obj(), w.inputs["Vector"])
    n = v.noise(v.obj(), 10.0, 3.0, 0.5)
    col = v.ramp(w.outputs["Fac"], [(0.0, L(color, 0.6)), (0.6, L(color, 1.0)),
                                    (1.0, L(color, 1.25))])
    col = v.mul(col, v.mr(n, 0.3, 0.7, 0.9, 1.1))
    v.out(col, rough, 0.0, v.bump(w.outputs["Fac"], 0.7, 0.02), spec=0.45)
    return mat


# ---------------------------------------------------------------------------------------------
# cloth, paper, straw, rope, hide
# ---------------------------------------------------------------------------------------------
def silk(name="I_Silk", color="#A8281C", sheen=0.9, rough=0.48, vary=0.05, sheen_tint=0.3,
         sss=0.0):
    """Silk: saturated colour, strong sheen towards grazing angles, soft specular."""
    mat, v = _new(name)
    if v is None:
        return mat
    col = _col(v, color, vary, 4.0)
    v.out(col, rough, 0.0, spec=0.35, sheen=sheen, sheen_rough=0.35,
          sheen_tint=(1.0, 1.0, 1.0, 1.0), sss=sss, sss_radius=(0.1, 0.05, 0.04), sss_scale=0.02)
    return mat


def cloth(name="I_Cloth", color="#D8D0BE", rough=0.85, weave=0.25, scale=180.0, sheen=0.35,
          vary=0.06):
    """Woven cotton / hemp: crossed wave bump at ``scale`` threads per unit."""
    mat, v = _new(name)
    if v is None:
        return mat
    a = v.wave(v.obj(), scale, 0.0, 0.0, "BANDS", "X")
    b = v.wave(v.obj(), scale, 0.0, 0.0, "BANDS", "Z")
    h = v.m("MULTIPLY", a, b)
    col = _col(v, color, vary, 3.0)
    col = v.mul(col, v.mr(h, 0.0, 1.0, 0.9, 1.04))
    v.out(col, rough, 0.0, v.bump(h, weave, 0.004), spec=0.3, sheen=sheen, sheen_rough=0.6)
    return mat


def hemp(name="I_Hemp", color="#B49A6C", rough=0.92, scale=60.0, weave=0.5):
    """Coarse sackcloth: loose weave bump, fibre noise, a little sheen."""
    mat, v = _new(name)
    if v is None:
        return mat
    a = v.wave(v.obj(), scale, 1.5, 1.0, "BANDS", "X")
    b = v.wave(v.obj(), scale, 1.5, 1.0, "BANDS", "Z")
    h = v.m("ADD", a, b)
    n = v.noise(v.obj(), 7.0, 4.0, 0.6)
    col = v.ramp(n, [(0.3, L(color, 0.82)), (0.7, L(color, 1.06))])
    col = v.mul(col, v.mr(h, 0.0, 2.0, 0.82, 1.06))
    v.out(col, rough, 0.0, v.bump(h, weave, 0.006), spec=0.25, sheen=0.4, sheen_rough=0.7)
    return mat


def paper(name="I_Paper", color="#EADFC4", rough=0.85, fibre=0.25, image=None,
          ink="#1E1712", aged="#C9B68C", age=0.25, sss=0.12):
    """Xuan paper / silk scroll field: fibres, faint ageing towards the edges, optional painted
    ``image`` (a bpy image whose alpha is ink) mixed in with the ``ink`` colour via UV."""
    mat, v = _new(name)
    if v is None:
        return mat
    n = v.noise(v.scale(v.obj(), (40.0, 40.0, 8.0)), 5.0, 4.0, 0.6)
    n2 = v.noise(v.obj(), 3.0, 3.0, 0.5)
    col = v.ramp(n, [(0.3, L(color, 0.93)), (0.7, L(color, 1.03))])
    col = v.mix(col, aged, v.mr(n2, 0.45, 0.8, 0.0, age))
    if image is not None:
        t = v.image(image, v.uv(), "Cubic", "CLIP")
        col = v.mix(col, ink, t.outputs["Alpha"])
    v.out(col, rough, 0.0, v.bump(n, fibre, 0.004), spec=0.3, sss=sss,
          sss_radius=(0.2, 0.15, 0.1), sss_scale=0.01)
    return mat


def decal(name, image, color="#1E1712", base="#EADFC4", rough=0.8, metal=0.0, coat=0.0,
          base_mat_kw=None):
    """Flat material with an image decal (alpha = paint) over a base colour via UV."""
    mat, v = _new(name)
    if v is None:
        return mat
    t = v.image(image, v.uv(), "Cubic", "CLIP")
    col = v.mix(base, color, t.outputs["Alpha"])
    v.out(col, rough, metal, spec=0.4, coat=coat, coat_rough=0.06)
    return mat


def straw(name="I_Straw", color="#C9A050", tip="#E2C27A", base_col="#9C7A3A", rough=0.55,
          zlo=-1.0, zhi=1.0):
    """Dry rice straw / grain: golden, varies per object (Object Info random) and along local Z
    from the darker cut end to the paler tips."""
    mat, v = _new(name)
    if v is None:
        return mat
    z = v.sep(v.obj())["Z"]
    t = v.mr(z, zlo, zhi)
    col = v.ramp(t, [(0.0, L(base_col)), (0.5, L(color)), (1.0, L(tip))])
    rnd = v.obj_random()
    col = v.mul(col, v.mr(rnd, 0.0, 1.0, 0.8, 1.12))
    n = v.noise(v.scale(v.obj(), (30.0, 30.0, 3.0)), 6.0, 2.0)
    col = v.mul(col, v.mr(n, 0.3, 0.7, 0.9, 1.06))
    v.out(col, rough, 0.0, spec=0.45, sheen=0.3, sheen_rough=0.4, sss=0.15,
          sss_radius=(0.3, 0.2, 0.05), sss_scale=0.01)
    return mat


def rope(name="I_Rope", color="#9A2A1E", rough=0.6, twist=60.0, sheen=0.6):
    """Twisted cord / silk rope: diagonal twist bands along the UV length (MeshBuilder tubes
    write u around, v along), sheen."""
    mat, v = _new(name)
    if v is None:
        return mat
    w = v.wave(v.scale(v.obj(), (twist, twist, twist)), 1.0, 0.0, 0.0, "BANDS", "DIAGONAL")
    col = v.mul(L(color), v.mr(w, 0.0, 1.0, 0.7, 1.08))
    v.out(col, rough, 0.0, v.bump(w, 0.4, 0.004), spec=0.35, sheen=sheen, sheen_rough=0.4)
    return mat


def hide(name="I_Hide", color="#D9C49A", rough=0.6, mottle=0.15):
    """Drum hide / leather: pale, mottled, slightly glossy where stretched."""
    mat, v = _new(name)
    if v is None:
        return mat
    n = v.noise(v.obj(), 4.0, 5.0, 0.6, 0.4)
    col = v.ramp(n, [(0.3, L(color, 1.0 - mottle)), (0.7, L(color, 1.0 + mottle * 0.4))])
    v.out(col, rough, 0.0, v.bump(n, 0.08, 0.01), spec=0.4, sss=0.1,
          sss_radius=(0.3, 0.15, 0.08), sss_scale=0.01)
    return mat


def leather(name="I_Leather", color="#5A3A24", rough=0.55):
    mat, v = _new(name)
    if v is None:
        return mat
    n = v.noise(v.obj(), 30.0, 4.0, 0.6)
    col = v.ramp(n, [(0.3, L(color, 0.8)), (0.7, L(color, 1.1))])
    v.out(col, rough, 0.0, v.bump(n, 0.15, 0.004), spec=0.45, coat=0.2, coat_rough=0.3)
    return mat


def feather(name="I_Feather", color="#E6E0D2", rough=0.7):
    mat, v = _new(name)
    if v is None:
        return mat
    n = v.noise(v.scale(v.obj(), (60.0, 2.0, 2.0)), 4.0, 2.0)
    col = v.ramp(n, [(0.3, L(color, 0.85)), (0.7, L(color, 1.0))])
    v.out(col, rough, 0.0, spec=0.3, sheen=0.5, sheen_rough=0.4, sss=0.2,
          sss_radius=(0.2, 0.2, 0.2), sss_scale=0.01)
    return mat


def plain(name, color, rough=0.6, metal=0.0, spec=0.5, coat=0.0, sheen=0.0, sss=0.0):
    mat, v = _new(name)
    if v is None:
        return mat
    v.out(L(color), rough, metal, spec=spec, coat=coat, sheen=sheen, sss=sss)
    return mat


# ---------------------------------------------------------------------------------------------
# light-emitting
# ---------------------------------------------------------------------------------------------
def flame(name="I_Flame", core="#FFF2C0", mid="#FFB240", edge="#E2421A", strength=6.0,
          attr="flame_t", body=None):
    """Fire: emission driven by a per-vertex ``attr`` (0 = outer edge / tip, 1 = inner core)
    with a little noise; ``body`` adds a translucent reddish diffuse so the flame has form."""
    mat, v = _new(name)
    if v is None:
        return mat
    t = v.attr(attr)
    n = v.noise(v.scale(v.obj(), (3.0, 3.0, 1.5)), 4.0, 3.0, 0.5)
    tt = v.m("ADD", t, v.m("MULTIPLY", v.m("SUBTRACT", n, 0.5), 0.25))
    col = v.ramp(tt, [(0.0, L(edge)), (0.45, L(mid)), (0.9, L(core))])
    stren = v.mr(tt, 0.0, 1.0, strength * 0.45, strength * 1.3)
    v.out(L(body or "#000000"), 1.0, 0.0, spec=0.0, emission=col, emission_strength=stren)
    return mat


def glow_paper(name="I_GlowPaper", color="#E4A060", glow="#FFB25A", strength=2.2,
               rough=0.8, ribs=None):
    """Lit paper lantern skin: diffuse paper + warm emission (light from inside), dimmer along
    the bamboo ribs (``ribs`` = rib count around Z) and at the top / bottom."""
    mat, v = _new(name)
    if v is None:
        return mat
    o = v.sep(v.obj())
    z = o["Z"]
    e = v.mr(v.m("ABSOLUTE", z), 0.0, 1.0, 1.0, 0.25, interp="SMOOTHSTEP")
    if ribs:
        at = v.m("ARCTAN2", o["Y"], o["X"])
        s = v.m("SINE", v.m("MULTIPLY", at, ribs))
        rib = v.mr(v.m("ABSOLUTE", s), 0.82, 1.0, 1.0, 0.45)
        e = v.m("MULTIPLY", e, rib)
    n = v.noise(v.obj(), 6.0, 4.0, 0.6)
    e = v.m("MULTIPLY", e, v.mr(n, 0.3, 0.7, 0.85, 1.1))
    v.out(L(color), rough, 0.0, spec=0.3, emission=L(glow),
          emission_strength=v.m("MULTIPLY", e, strength), sss=0.3, sss_radius=(0.4, 0.2, 0.1),
          sss_scale=0.02)
    return mat


def cloud(name="I_Cloud", color="#E8E4F0", shade="#9A92B8", rough=0.75, rim="#FFE9C0"):
    """Auspicious cloud (xiangyun): soft lilac-white body, cooler in the folds, warm sheen."""
    mat, v = _new(name)
    if v is None:
        return mat
    ao = v.ao(0.12, only_local=False)
    col = v.ramp(ao, [(0.2, L(shade)), (0.9, L(color))])
    v.out(col, rough, 0.0, spec=0.3, sheen=0.8, sheen_rough=0.4, sss=0.4,
          sss_radius=(0.5, 0.5, 0.7), sss_scale=0.05)
    return mat
