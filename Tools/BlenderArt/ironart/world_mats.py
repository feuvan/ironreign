"""World Models family: procedural PBR materials authored for **baking** (DESIGN.md 12.3).

Every factory returns a node material whose output is a single Principled BSDF (no mix
shaders), so :mod:`ironart.world_bake` can rewire Base Color / Roughness / Metallic into an
emission shader and bake each channel, and bake the shading normal (bump) as a tangent-space
normal map.  Colours are *albedo* (sRGB hex, converted to linear here) chosen for physically
plausible PBR under Unreal's Lumen: no baked light, no painted shadows - only material colour,
weathering and cavity grime.

Texture space
    ``MetreUV``  the builders' UV layer in metres (u along the surface, v up / down the slope);
                 :func:`ironart.world_bake.prepare` renames the MeshBuilder ``UVMap`` to it and
                 creates the atlas UVs separately, so patterns keep physical sizes after unwrap.
    Object       prototype space: origin on the ground, so ``z`` is the height above the ground
                 (weathering at the wall foot, rain streaks under the eaves).

Material names double as builder slot names (``world_kit`` uses them), e.g. ``W_Stone``.
:func:`library` creates the whole set; :func:`variant` derives a recoloured copy.
"""

import math

import bpy

from . import palette
from .materials import NB, sock


# ---------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------
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
    return mat, nb


def L(c, k=1.0):
    """sRGB hex/token -> linear RGBA tuple (optionally scaled)."""
    r, g, b = palette.lin(c)
    return (min(1.0, r * k), min(1.0, g * k), min(1.0, b * k), 1.0)


class W:
    """Small node-graph vocabulary on top of :class:`ironart.materials.NB`."""

    def __init__(self, nb):
        self.nb = nb

    def uv(self):
        n = self.nb.nodes.get("_MetreUV")
        if n is None:
            n = self.nb.node("ShaderNodeUVMap", name="_MetreUV")
            n.uv_map = "MetreUV"
        return n.outputs["UV"]

    def obj(self):
        return self.nb.coord("Object")

    def sep(self, vec):
        s = self.nb.node("ShaderNodeSeparateXYZ")
        self.nb.link(vec, s.inputs[0])
        return s.outputs

    def comb(self, x, y, z):
        c = self.nb.node("ShaderNodeCombineXYZ")
        for k, v in zip(("X", "Y", "Z"), (x, y, z)):
            self.nb.set(c.inputs[k], v)
        return c.outputs[0]

    def scale(self, vec, s):
        return self.nb.mapping(vec, scale=s if isinstance(s, tuple) else (s, s, s))

    def noise(self, vec, scale=4.0, detail=4.0, rough=0.55, dist=0.0, dims="3D", w=0.0):
        n = self.nb.node("ShaderNodeTexNoise", noise_dimensions=dims,
                         inputs={"Scale": scale, "Detail": detail, "Roughness": rough,
                                 "Distortion": dist})
        if dims == "4D":
            self.nb.set(n.inputs["W"], w)
        self.nb.link(vec, n.inputs["Vector"])
        return n.outputs["Fac"]

    def voronoi(self, vec, scale=4.0, feature="F1", metric="EUCLIDEAN", rand=1.0, out="Distance"):
        v = self.nb.node("ShaderNodeTexVoronoi", feature=feature, distance=metric,
                         inputs={"Scale": scale, "Randomness": rand})
        self.nb.link(vec, v.inputs["Vector"])
        return v.outputs[out]

    def brick(self, vec, w, h, mortar, c1, c2, mc, offset=0.5, freq=2, squash=1.0,
              smooth=0.25, bias=0.0):
        b = self.nb.node("ShaderNodeTexBrick", inputs={
            "Scale": 1.0, "Mortar Size": mortar, "Mortar Smooth": smooth, "Bias": bias,
            "Brick Width": w, "Row Height": h, "Color1": c1, "Color2": c2, "Mortar": mc})
        b.offset = offset
        b.offset_frequency = freq
        b.squash = squash
        self.nb.link(vec, b.inputs["Vector"])
        return b.outputs["Color"], b.outputs["Fac"]

    def ramp(self, fac, stops, interp="LINEAR"):
        return self.nb.ramp(fac, [(p, L(c) if isinstance(c, str) else c) for p, c in stops], interp)

    def mr(self, val, a0, a1, b0=0.0, b1=1.0, interp="LINEAR", clamp=True):
        return self.nb.maprange(val, a0, a1, b0, b1, clamp=clamp, interp=interp)

    def m(self, op, a, b=0.0, clamp=False):
        return self.nb.math(op, a, b, clamp)

    def mix(self, a, b, fac, blend="MIX"):
        return self.nb.mix(a, b, fac, blend=blend)

    def mul(self, col, fac_col):
        return self.nb.mix(col, fac_col, 1.0, blend="MULTIPLY")

    def gray(self, v):
        """Float socket -> grey colour (for multiplies)."""
        c = self.nb.node("ShaderNodeCombineColor")
        for k in ("Red", "Green", "Blue"):
            self.nb.set(c.inputs[k], v)
        return c.outputs[0]

    def bump(self, height, strength=0.5, distance=0.02, normal=None):
        return self.nb.bump(height, strength, distance, normal)

    def out(self, base, rough=0.8, metal=0.0, normal=None, spec=0.5, coat=0.0):
        kw = dict(Base_Color=base, Roughness=rough, Metallic=metal, Specular_IOR_Level=spec)
        if normal is not None:
            kw["Normal"] = normal
        if coat:
            kw["Coat_Weight"] = coat
        p = self.nb.principled(**kw)
        self.nb.output(p.outputs[0])
        return p

    # -- weathering ------------------------------------------------------------------------
    def height_z(self):
        return self.sep(self.obj())["Z"]

    def foot_grime(self, col, h0=0.0, h1=1.6, dark=0.62, tint="#4A4032"):
        """Darker, earth-tinted band at the foot of walls (splash, damp)."""
        z = self.height_z()
        n = self.noise(self.scale(self.obj(), (1.0, 1.0, 3.0)), 2.5, 4)
        z2 = self.m("ADD", z, self.m("MULTIPLY", self.m("SUBTRACT", n, 0.5), 0.6))
        f = self.mr(z2, h0, h1, 1.0, 0.0, interp="SMOOTHSTEP")
        dirty = self.mix(col, L(tint), 0.35)
        dirty = self.mul(dirty, self.gray(dark))
        return self.mix(col, dirty, f)

    def streaks(self, col, amount=0.18, scale=6.0):
        """Vertical rain streaks: noise stretched along Z, darkening."""
        v = self.scale(self.obj(), (scale, scale, 0.35))
        n = self.noise(v, 3.0, 3, 0.6)
        f = self.mr(n, 0.45, 0.75, 0.0, amount)
        return self.mul(col, self.gray(self.m("SUBTRACT", 1.0, f)))

    def blotch(self, col, amount=0.12, scale=0.6, warm="#6B5A44"):
        """Low-frequency colour variation (sun bleaching vs. stains)."""
        n = self.noise(self.obj(), scale, 3, 0.5)
        lo = self.mix(col, L(warm), amount)
        hi = self.mul(col, self.gray(1.0 + amount))
        return self.mix(lo, hi, self.mr(n, 0.35, 0.65))

    def moss(self, col, amount=0.35, scale=1.4, color="#4E5A30", z1=1.2):
        """Moss / lichen patches, mostly near the ground."""
        n = self.noise(self.obj(), scale, 5, 0.6)
        z = self.height_z()
        f = self.m("MULTIPLY", self.mr(n, 0.58, 0.72), self.mr(z, 0.0, z1, 1.0, 0.25))
        return self.mix(col, L(color), self.m("MULTIPLY", f, amount))


# ---------------------------------------------------------------------------------------------
# masonry
# ---------------------------------------------------------------------------------------------
def ashlar(name="W_Stone", color="#8D877B", mortar="#A59D8C", block=(1.25, 0.55), vary=0.18,
           bump=0.6, foot=1.8):
    """City wall ashlar: big grey-beige blocks (per-block tone), recessed soft mortar, chipped
    arrises, foot grime, rain streaks, moss near the ground."""
    mat, nb = _new(name)
    if nb is None:
        return mat
    w = W(nb)
    uv = w.uv()
    c1, c2 = L(color, 1.0 - vary), L(color, 1.0 + vary * 0.6)
    col, fac = w.brick(uv, block[0], block[1], 0.035, c1, c2, L(mortar), smooth=0.3)
    # per-block noise texture (pitting) + large patches
    fine = w.noise(w.scale(uv, 9.0), 1.0, 6, 0.65)
    col = w.mul(col, w.ramp(fine, [(0.3, (0.86, 0.86, 0.86, 1)), (0.7, (1.06, 1.06, 1.04, 1))]))
    col = w.blotch(col, 0.14, 0.35)
    col = w.streaks(col, 0.16)
    col = w.moss(col, 0.45, 1.1, z1=foot)
    col = w.foot_grime(col, 0.0, foot)
    # height: block faces slightly domed + chipped edges, mortar recessed
    chip = w.noise(w.scale(uv, 3.0), 2.0, 4, 0.6)
    edge = w.mr(fac, 0.0, 1.0)
    h = w.m("SUBTRACT", w.m("MULTIPLY", fine, 0.25), w.m("MULTIPLY", edge, 1.0))
    h = w.m("SUBTRACT", h, w.m("MULTIPLY", w.mr(chip, 0.55, 0.8), 0.25))
    rough = w.mr(fine, 0.2, 0.8, 0.78, 0.92)
    w.out(col, rough, 0.0, w.bump(h, bump, 0.04), spec=0.35)
    return mat


def brick(name="W_Brick", color="#6F7376", mortar="#9C9890", size=(0.48, 0.14), vary=0.16,
          bump=0.45, foot=1.2):
    """Grey 'qing' brick (Ming walls, houses, pagodas): blue-grey bricks, light mortar."""
    mat, nb = _new(name)
    if nb is None:
        return mat
    w = W(nb)
    uv = w.uv()
    col, fac = w.brick(uv, size[0], size[1], 0.018, L(color, 1 - vary), L(color, 1 + vary * 0.5),
                       L(mortar), smooth=0.2)
    fine = w.noise(w.scale(uv, 14.0), 1.0, 5, 0.6)
    col = w.mul(col, w.ramp(fine, [(0.3, (0.9, 0.9, 0.9, 1)), (0.7, (1.05, 1.05, 1.05, 1))]))
    col = w.blotch(col, 0.1, 0.5, "#5E5548")
    col = w.streaks(col, 0.12)
    col = w.foot_grime(col, 0.0, foot, 0.7)
    h = w.m("SUBTRACT", w.m("MULTIPLY", fine, 0.2), fac)
    w.out(col, w.mr(fine, 0.2, 0.8, 0.8, 0.92), 0.0, w.bump(h, bump, 0.02), spec=0.35)
    return mat


def paving(name="W_Paving", color="#8E8A80", size=(0.9, 0.9), vary=0.14, bump=0.5):
    """Wall-walk / terrace paving slabs (MetreUV on horizontal faces = x, y)."""
    mat, nb = _new(name)
    if nb is None:
        return mat
    w = W(nb)
    uv = w.uv()
    col, fac = w.brick(uv, size[0], size[1], 0.03, L(color, 1 - vary), L(color, 1 + vary * 0.4),
                       L("#6E6A62"), offset=0.5, smooth=0.2)
    fine = w.noise(w.scale(uv, 6.0), 1.0, 5, 0.6)
    col = w.mul(col, w.ramp(fine, [(0.3, (0.88, 0.88, 0.88, 1)), (0.7, (1.05, 1.05, 1.04, 1))]))
    col = w.blotch(col, 0.12, 0.4)
    gr = w.noise(w.scale(uv, 0.9), 1.0, 4, 0.6)
    col = w.mix(col, L("#5C6236"), w.m("MULTIPLY", w.mr(gr, 0.62, 0.75), w.m("MULTIPLY", fac, 0.8)))
    h = w.m("SUBTRACT", w.m("MULTIPLY", fine, 0.2), fac)
    w.out(col, 0.85, 0.0, w.bump(h, bump, 0.03), spec=0.3)
    return mat


def rammed_earth(name="W_Earth", color="#A88B62", bump=0.6):
    """Rammed-earth (hangtu) town wall: horizontal tamped layers 12-20 cm, eroded vertical
    gullies, darker damp foot."""
    mat, nb = _new(name)
    if nb is None:
        return mat
    w = W(nb)
    uv = w.uv()
    s = w.sep(uv)
    wob = w.noise(w.scale(uv, (0.6, 0.6, 0.6)), 1.5, 3)
    layer = w.m("ADD", s["Y"], w.m("MULTIPLY", wob, 0.12))
    band = w.m("FRACT", w.m("DIVIDE", layer, 0.17))
    band_id = w.m("FLOOR", w.m("DIVIDE", layer, 0.17))
    tone = w.noise(w.comb(band_id, 0.0, 0.0), 1.7, 1)       # per-layer tone
    seam = w.mr(band, 0.0, 0.12, 1.0, 0.0)
    col = w.ramp(tone, [(0.25, L(color, 0.86)), (0.75, L(color, 1.1))])
    col = w.mul(col, w.gray(w.m("SUBTRACT", 1.0, w.m("MULTIPLY", seam, 0.18))))
    fine = w.noise(w.scale(uv, 10.0), 1.0, 6, 0.65)
    col = w.mul(col, w.ramp(fine, [(0.3, (0.88, 0.88, 0.88, 1)), (0.7, (1.06, 1.05, 1.03, 1))]))
    gul = w.noise(w.scale(w.obj(), (5.0, 5.0, 0.25)), 2.0, 3, 0.6)
    gully = w.mr(gul, 0.55, 0.8)
    col = w.mul(col, w.gray(w.m("SUBTRACT", 1.0, w.m("MULTIPLY", gully, 0.18))))
    col = w.streaks(col, 0.1)
    col = w.foot_grime(col, 0.0, 1.4, 0.72, "#5A4632")
    h = w.m("SUBTRACT", w.m("MULTIPLY", fine, 0.35), w.m("ADD", seam, w.m("MULTIPLY", gully, 0.6)))
    w.out(col, 0.93, 0.0, w.bump(h, bump, 0.04), spec=0.25)
    return mat


def plaster(name="W_Plaster", color="#DCD3C1", foot=1.4, dado="#8A8478", dado_h=0.0):
    """Lime plaster wall with soft blotches, rain streaks and a damp foot; optional painted
    dado band (``dado_h`` metres, e.g. a grey brick skirt)."""
    mat, nb = _new(name)
    if nb is None:
        return mat
    w = W(nb)
    fine = w.noise(w.scale(w.obj(), 6.0), 1.0, 6, 0.6)
    col = w.ramp(fine, [(0.3, L(color, 0.9)), (0.7, L(color, 1.03))])
    col = w.blotch(col, 0.1, 0.8, "#A39478")
    col = w.streaks(col, 0.2, 5.0)
    if dado_h > 0:
        z = w.height_z()
        col = w.mix(col, L(dado), w.mr(z, dado_h - 0.02, dado_h + 0.02, 1.0, 0.0))
    col = w.foot_grime(col, 0.0, foot, 0.7)
    w.out(col, w.mr(fine, 0.2, 0.8, 0.85, 0.95), 0.0, w.bump(fine, 0.12, 0.01), spec=0.3)
    return mat


def red_wall(name="W_RedWall", color="#8E3426"):
    """Imperial red-ochre plastered wall (palace enclosures) with faded patches."""
    mat, nb = _new(name)
    if nb is None:
        return mat
    w = W(nb)
    fine = w.noise(w.scale(w.obj(), 5.0), 1.0, 6, 0.6)
    col = w.ramp(fine, [(0.3, L(color, 0.88)), (0.7, L(color, 1.06))])
    col = w.blotch(col, 0.12, 0.7, "#A0553C")
    col = w.streaks(col, 0.18, 5.0)
    col = w.foot_grime(col, 0.0, 1.2, 0.75, "#5A3426")
    w.out(col, 0.85, 0.0, w.bump(fine, 0.1, 0.01), spec=0.3)
    return mat


def marble(name="W_Marble", color="#D9D5CA", bump=0.3):
    """White marble (hanbaiyu) terraces, balustrades, bridges: soft veins, grime in the low
    parts."""
    mat, nb = _new(name)
    if nb is None:
        return mat
    w = W(nb)
    o = w.obj()
    vein = w.noise(w.scale(o, (1.2, 1.2, 1.2)), 2.0, 6, 0.6, dist=4.0)
    vein = w.m("ABSOLUTE", w.m("SUBTRACT", vein, 0.5))
    col = w.mix(L(color), L("#B9B5AC"), w.mr(vein, 0.03, 0.0))
    fine = w.noise(w.scale(o, 8.0), 1.0, 5, 0.6)
    col = w.mul(col, w.ramp(fine, [(0.3, (0.93, 0.93, 0.93, 1)), (0.7, (1.03, 1.03, 1.03, 1))]))
    col = w.streaks(col, 0.14, 4.0)
    col = w.foot_grime(col, 0.0, 0.8, 0.82, "#7A7060")
    w.out(col, 0.45, 0.0, w.bump(fine, bump * 0.3, 0.01), spec=0.5)
    return mat


def rock(name="W_Rock", color="#7F7B72", moss="#56603A", strata=0.55):
    """Cliff granite / limestone with horizontal strata, cracks, moss and grass on ledges
    (Object normal Z: up-facing parts get moss)."""
    mat, nb = _new(name)
    if nb is None:
        return mat
    w = W(nb)
    o = w.obj()
    s = w.sep(o)
    wob = w.noise(w.scale(o, 0.15), 1.0, 3)
    zz = w.m("ADD", s["Z"], w.m("MULTIPLY", wob, 3.0))
    band = w.m("FRACT", w.m("DIVIDE", zz, strata))
    band_id = w.m("FLOOR", w.m("DIVIDE", zz, strata))
    tone = w.noise(w.comb(band_id, 0.3, 0.0), 1.3, 1)
    col = w.ramp(tone, [(0.2, L(color, 0.78)), (0.5, L(color)), (0.8, L("#958B7A"))])
    cr = w.voronoi(w.scale(o, (0.9, 0.9, 1.6)), 1.0, "DISTANCE_TO_EDGE")
    crack = w.mr(cr, 0.0, 0.04, 1.0, 0.0)
    fine = w.noise(w.scale(o, 4.0), 1.0, 7, 0.65)
    col = w.mul(col, w.ramp(fine, [(0.25, (0.78, 0.78, 0.78, 1)), (0.75, (1.1, 1.08, 1.05, 1))]))
    col = w.mix(col, L("#2E2A26"), w.m("MULTIPLY", crack, 0.7))
    col = w.streaks(col, 0.2, 1.5)
    # moss / grass on up-facing ledges
    nz = w.sep(nb.coord("Normal"))["Z"]
    mn = w.noise(w.scale(o, 0.7), 1.0, 5, 0.6)
    up = w.m("MULTIPLY", w.mr(nz, 0.55, 0.85), w.mr(mn, 0.35, 0.6))
    col = w.mix(col, w.ramp(mn, [(0.3, L(moss, 0.85)), (0.7, L("#6E7A40"))]), up)
    seam = w.mr(band, 0.0, 0.08, 1.0, 0.0)
    h = w.m("SUBTRACT", w.m("MULTIPLY", fine, 0.6), w.m("ADD", crack, w.m("MULTIPLY", seam, 0.4)))
    w.out(col, 0.88, 0.0, w.bump(h, 0.8, 0.08), spec=0.3)
    return mat


# ---------------------------------------------------------------------------------------------
# timber, paint, lacquer, metal
# ---------------------------------------------------------------------------------------------
def lacquer(name="W_Lacquer", color="#8A2417", rough=0.38, wear=0.18):
    """Vermilion lacquer (columns, frames): deep red, faint vertical brush streaks, sun-faded
    patches and a few chips showing dark wood."""
    mat, nb = _new(name)
    if nb is None:
        return mat
    w = W(nb)
    o = w.obj()
    st = w.noise(w.scale(o, (14.0, 14.0, 0.8)), 2.0, 3)
    col = w.ramp(st, [(0.3, L(color, 0.9)), (0.7, L(color, 1.06))])
    col = w.blotch(col, wear, 0.9, "#A3523E")
    chip = w.noise(w.scale(o, 6.0), 2.0, 5, 0.7)
    chips = w.mr(chip, 0.72, 0.78)
    col = w.mix(col, L("#3A2418"), w.m("MULTIPLY", chips, 0.7))
    col = w.foot_grime(col, 0.0, 0.6, 0.75)
    rough_s = w.mr(chips, 0.0, 1.0, rough, 0.7)
    w.out(col, rough_s, 0.0, w.bump(w.m("SUBTRACT", st, w.m("MULTIPLY", chips, 2.0)), 0.15, 0.005),
          spec=0.5)
    return mat


def wood(name="W_Wood", color="#5B3E28", grain=0.4, rough=0.7):
    """Weathered timber (railings, rafters, doors): grain along the MetreUV u axis."""
    mat, nb = _new(name)
    if nb is None:
        return mat
    w = W(nb)
    uv = w.uv()
    g = w.noise(w.scale(uv, (1.2, 26.0, 1.0)), 2.0, 5, 0.6, dist=1.5)
    col = w.ramp(g, [(0.25, L(color, 0.72)), (0.6, L(color)), (0.85, L(color, 1.25))])
    col = w.blotch(col, 0.12, 1.2, "#3A2A1E")
    w.out(col, rough, 0.0, w.bump(g, grain, 0.006), spec=0.35)
    return mat


def beam_paint(name="W_BeamPaint", c1="#2E6B6A", c2="#2C4F86", gold="#C29A44", red="#8A2417",
               period=3.2):
    """Painted architraves (xuanzi caihua): along the beam (MetreUV u) repeating panels -
    teal / lapis bands with gold and white rims, red ends; faded and chalky."""
    mat, nb = _new(name)
    if nb is None:
        return mat
    w = W(nb)
    uv = w.uv()
    s = w.sep(uv)
    u = w.m("FRACT", w.m("DIVIDE", s["X"], period))
    v = w.m("FRACT", w.m("DIVIDE", s["Y"], 0.55))
    d = w.m("ABSOLUTE", w.m("SUBTRACT", u, 0.5))             # 0 centre .. 0.5 end of panel
    # central panel (box head) teal, middle field lapis, end bands teal with gold rim lines
    col = w.mix(L(c2), L(c1), w.mr(d, 0.16, 0.17))
    col = w.mix(col, L(c1), w.mr(d, 0.40, 0.41))
    rim = w.m("MAXIMUM", w.mr(w.m("ABSOLUTE", w.m("SUBTRACT", d, 0.165)), 0.012, 0.0),
              w.mr(w.m("ABSOLUTE", w.m("SUBTRACT", d, 0.405)), 0.012, 0.0))
    col = w.mix(col, L(gold), rim)
    # horizontal white pin lines top/bottom of the beam band
    vline = w.m("MAXIMUM", w.mr(v, 0.06, 0.04), w.mr(v, 0.94, 0.96))
    col = w.mix(col, L("#D8D2C2"), w.m("MULTIPLY", vline, 0.8))
    # "xuanzi" swirl hint: concentric rings in the end bands
    ring = w.m("SINE", w.m("MULTIPLY", w.m("SQRT", w.m("ADD", w.m("POWER", w.m("SUBTRACT", d, 0.29), 2.0),
                                                        w.m("POWER", w.m("MULTIPLY", w.m("SUBTRACT", v, 0.5), 0.35), 2.0))), 90.0))
    swirl = w.m("MULTIPLY", w.mr(ring, 0.6, 0.9), w.mr(d, 0.18, 0.2))
    swirl = w.m("MULTIPLY", swirl, w.mr(d, 0.39, 0.37))
    col = w.mix(col, L("#E3DCC8"), w.m("MULTIPLY", swirl, 0.55))
    fade = w.noise(w.scale(w.obj(), 1.5), 1.0, 4)
    col = w.mix(col, L("#9A9A88"), w.mr(fade, 0.5, 0.8, 0.0, 0.22))
    w.out(col, 0.75, 0.0, w.bump(rim, 0.15, 0.004), spec=0.35)
    return mat


def bracket(name="W_Bracket", c1="#2F6A62", c2="#2D4C7E", edge="#D6CFBE"):
    """Dougong brackets: alternating teal / lapis blocks with pale edge lines."""
    mat, nb = _new(name)
    if nb is None:
        return mat
    w = W(nb)
    o = w.obj()
    n = w.noise(w.scale(o, 0.9), 1.0, 2)
    col = w.mix(L(c1), L(c2), w.mr(n, 0.48, 0.52))
    fine = w.noise(w.scale(o, 9.0), 1.0, 4)
    col = w.mul(col, w.ramp(fine, [(0.3, (0.88, 0.88, 0.88, 1)), (0.7, (1.05, 1.05, 1.05, 1))]))
    w.out(col, 0.72, 0.0, w.bump(fine, 0.1, 0.01), spec=0.35)
    return mat


def lattice(name="W_Lattice", frame="#7A2316", paper="#CDBF9E", cell=0.16, bar=0.022,
            sill=0.9):
    """Door / window bays: red-brown frames, square lattice over translucent paper above a solid
    sill board (``sill`` m above the bay bottom, from MetreUV v)."""
    mat, nb = _new(name)
    if nb is None:
        return mat
    w = W(nb)
    uv = w.uv()
    s = w.sep(uv)
    fx = w.m("ABSOLUTE", w.m("SUBTRACT", w.m("FRACT", w.m("DIVIDE", s["X"], cell)), 0.5))
    fy = w.m("ABSOLUTE", w.m("SUBTRACT", w.m("FRACT", w.m("DIVIDE", s["Y"], cell)), 0.5))
    half = 0.5 - bar / cell
    bars = w.m("MAXIMUM", w.mr(fx, half - 0.04, half), w.mr(fy, half - 0.04, half))
    # diagonal fret every other cell for richness
    diag = w.m("ABSOLUTE", w.m("SUBTRACT", w.m("FRACT", w.m("DIVIDE", w.m("ADD", s["X"], s["Y"]), cell * 2.0)), 0.5))
    bars = w.m("MAXIMUM", bars, w.m("MULTIPLY", w.mr(diag, 0.06, 0.03), 0.7))
    col = w.mix(L(paper), L(frame), bars)
    board = w.mr(s["Y"], sill - 0.02, sill + 0.02, 1.0, 0.0)
    col = w.mix(col, L(frame, 0.9), board)
    fine = w.noise(w.scale(w.obj(), 5.0), 1.0, 4)
    col = w.mul(col, w.ramp(fine, [(0.3, (0.88, 0.88, 0.88, 1)), (0.7, (1.04, 1.04, 1.04, 1))]))
    col = w.foot_grime(col, 0.0, 0.5, 0.8)
    h = w.m("MAXIMUM", bars, board)
    w.out(col, w.mr(h, 0.0, 1.0, 0.8, 0.5), 0.0, w.bump(h, 0.6, 0.02), spec=0.4)
    return mat


def gate_door(name="W_GateDoor", color="#7E2216", stud="#C9A24A", pitch=0.55):
    """Great gate leaves: red lacquer with rows of gilt bosses (men ding) on a grid."""
    mat, nb = _new(name)
    if nb is None:
        return mat
    w = W(nb)
    uv = w.uv()
    s = w.sep(uv)
    fx = w.m("SUBTRACT", w.m("FRACT", w.m("DIVIDE", s["X"], pitch)), 0.5)
    fy = w.m("SUBTRACT", w.m("FRACT", w.m("DIVIDE", s["Y"], pitch)), 0.5)
    r = w.m("SQRT", w.m("ADD", w.m("POWER", fx, 2.0), w.m("POWER", fy, 2.0)))
    boss = w.mr(r, 0.2, 0.15)
    st = w.noise(w.scale(w.obj(), (10.0, 10.0, 0.7)), 2.0, 3)
    col = w.ramp(st, [(0.3, L(color, 0.88)), (0.7, L(color, 1.05))])
    col = w.blotch(col, 0.15, 1.0, "#9E4A36")
    col = w.mix(col, L(stud), boss)
    dome = w.m("POWER", w.mr(r, 0.2, 0.0), 0.5)
    w.out(col, w.mr(boss, 0.0, 1.0, 0.45, 0.3), boss, w.bump(dome, 0.8, 0.03), spec=0.5)
    return mat


def gold(name="W_Gold", color="#C9A24A", rough=0.3):
    mat, nb = _new(name)
    if nb is None:
        return mat
    w = W(nb)
    n = w.noise(w.scale(w.obj(), 8.0), 1.0, 4)
    col = w.ramp(n, [(0.3, L(color, 0.8)), (0.7, L(color, 1.08))])
    w.out(col, w.mr(n, 0.3, 0.7, rough * 0.8, rough * 1.4), 1.0, w.bump(n, 0.1, 0.005))
    return mat


def iron(name="W_Iron", color="#5D6066", rough=0.38):
    mat, nb = _new(name)
    if nb is None:
        return mat
    w = W(nb)
    n = w.noise(w.scale(w.obj(), 12.0), 1.0, 4)
    col = w.ramp(n, [(0.3, L(color, 0.8)), (0.7, L(color, 1.1))])
    w.out(col, w.mr(n, 0.3, 0.7, rough * 0.8, rough * 1.3), 1.0, w.bump(n, 0.08, 0.003))
    return mat


def dark(name="W_Dark", color="#1C1814"):
    """Openings / tunnel interiors / under-roof cavities (no light of their own)."""
    mat, nb = _new(name)
    if nb is None:
        return mat
    W(nb).out(L(color), 0.95, 0.0, spec=0.2)
    return mat


def flat(name, color, rough=0.8, metal=0.0):
    mat, nb = _new(name)
    if nb is None:
        return mat
    w = W(nb)
    n = w.noise(w.scale(w.obj(), 5.0), 1.0, 3)
    col = w.ramp(n, [(0.3, L(color, 0.92)), (0.7, L(color, 1.05))])
    w.out(col, rough, metal)
    return mat


# ---------------------------------------------------------------------------------------------
# roofs
# ---------------------------------------------------------------------------------------------
def roof_tile(name="W_Tile", color="#4C535A", pitch=0.5, course=0.32, glaze=False, vary=0.14,
              moss=0.25, rough=None):
    """Roof surface between the geometric cover-tile rows: concave pan-tile channels every
    ``pitch`` m across (MetreUV u, matching the builder's cover rows) and overlapping courses
    every ``course`` m down the slope (v).  ``glaze`` = imperial glazed tiles (glossy, little
    moss).  The cover rows themselves use the same material (they read as the round tiles)."""
    mat, nb = _new(name)
    if nb is None:
        return mat
    w = W(nb)
    uv = w.uv()
    s = w.sep(uv)
    u = w.m("FRACT", w.m("DIVIDE", s["X"], pitch))
    vv = w.m("FRACT", w.m("DIVIDE", s["Y"], course))
    row = w.m("FLOOR", w.m("DIVIDE", s["Y"], course))
    col_id = w.m("FLOOR", w.m("DIVIDE", s["X"], pitch))
    # pan channel: concave across u (dark in the gutter between cover rows at u = 0 / 1)
    chan = w.m("SINE", w.m("MULTIPLY", u, math.pi))
    lip = w.mr(vv, 0.0, 0.14, 1.0, 0.0)                  # shadowed overlap line at each course
    per = w.noise(w.comb(col_id, row, 0.0), 2.3, 1)        # per-tile tone
    col = w.ramp(per, [(0.2, L(color, 1 - vary)), (0.8, L(color, 1 + vary * 0.7))])
    col = w.mul(col, w.gray(w.mr(chan, 0.0, 1.0, 0.72, 1.0)))
    col = w.mul(col, w.gray(w.m("SUBTRACT", 1.0, w.m("MULTIPLY", lip, 0.25))))
    big = w.noise(w.scale(w.obj(), 0.4), 1.0, 3)
    col = w.mix(col, w.mul(col, w.gray(1.15)), w.mr(big, 0.4, 0.7, 0.0, 0.6))
    if moss > 0:
        mn = w.noise(w.scale(w.obj(), 1.1), 1.0, 5, 0.6)
        col = w.mix(col, L("#5F6440"), w.m("MULTIPLY", w.mr(mn, 0.6, 0.75), moss))
        dust = w.noise(w.scale(w.obj(), 3.0), 1.0, 4)
        col = w.mix(col, L("#8E8676"), w.mr(dust, 0.55, 0.8, 0.0, 0.25))
    h = w.m("SUBTRACT", w.m("MULTIPLY", chan, 0.6), w.m("MULTIPLY", lip, 0.5))
    r = rough if rough is not None else (0.28 if glaze else 0.62)
    rs = w.mr(per, 0.0, 1.0, r * 0.85, r * 1.2)
    w.out(col, rs, 0.0, w.bump(h, 0.55, 0.03), spec=0.6 if glaze else 0.4)
    return mat


def fascia(name="W_Fascia", wood="#3E2A1E", end1="#2E6B6A", end2="#2C4F86", pitch=0.5):
    """Eave edge: dark rafter band with painted round rafter ends (teal / lapis rings)."""
    mat, nb = _new(name)
    if nb is None:
        return mat
    w = W(nb)
    uv = w.uv()
    s = w.sep(uv)
    fx = w.m("SUBTRACT", w.m("FRACT", w.m("DIVIDE", s["X"], pitch)), 0.5)
    fy = w.m("SUBTRACT", w.m("FRACT", w.m("DIVIDE", s["Y"], 0.3)), 0.5)
    r = w.m("SQRT", w.m("ADD", w.m("POWER", fx, 2.0), w.m("POWER", w.m("MULTIPLY", fy, 0.6), 2.0)))
    ring = w.mr(r, 0.3, 0.26)
    col = w.mix(L(wood), L(end1), ring)
    col = w.mix(col, L(end2), w.mr(r, 0.16, 0.12))
    col = w.mix(col, L("#D8D2C2"), w.m("MULTIPLY", w.mr(w.m("ABSOLUTE", w.m("SUBTRACT", r, 0.21)), 0.02, 0.0), 0.7))
    w.out(col, 0.7, 0.0, w.bump(ring, 0.3, 0.01), spec=0.35)
    return mat


# ---------------------------------------------------------------------------------------------
# ground (unique-UV ground plates read a layout mask image painted in numpy)
# ---------------------------------------------------------------------------------------------
def ground(name, mask_path, size_m, earth="#8C7656", pave="#8F8B82", grass="#647A40",
           water="#2F4A48"):
    """City ground: layout image (R = paved street/plaza, G = grass/garden, B = water bank /
    canal bed, A unused) on the ground UV (0..1 over ``size_m`` metres), mixed into packed earth,
    flagstone paving and grass, with ruts, puddle stains and worn edges."""
    mat, nb = _new(name)
    if nb is None:
        return mat
    w = W(nb)
    img = bpy.data.images.load(mask_path, check_existing=True)
    img.colorspace_settings.name = "Non-Color"
    t = nb.node("ShaderNodeTexImage", image=img, interpolation="Cubic", extension="EXTEND")
    gu = nb.node("ShaderNodeUVMap")
    gu.uv_map = "GroundUV"
    nb.link(gu.outputs["UV"], t.inputs["Vector"])
    ms = w.sep(t.outputs["Color"])
    paved, green, wet = ms["X"], ms["Y"], ms["Z"]
    o = w.obj()
    # packed earth
    en = w.noise(w.scale(o, 0.25), 1.0, 5, 0.55)
    ef = w.noise(w.scale(o, 3.0), 1.0, 6, 0.6)
    col_e = w.ramp(en, [(0.25, L(earth, 0.85)), (0.75, L(earth, 1.1))])
    col_e = w.mul(col_e, w.ramp(ef, [(0.3, (0.85, 0.85, 0.85, 1)), (0.7, (1.07, 1.06, 1.04, 1))]))
    # flagstones in object XY (metres)
    pv_col, pv_fac = w.brick(o, 1.1, 0.7, 0.04, L(pave, 0.88), L(pave, 1.08), L("#6B665C"),
                             smooth=0.2)
    pfine = w.noise(w.scale(o, 5.0), 1.0, 5)
    pv_col = w.mul(pv_col, w.ramp(pfine, [(0.3, (0.88, 0.88, 0.88, 1)), (0.7, (1.05, 1.05, 1.04, 1))]))
    pv_col = w.mix(pv_col, col_e, w.mr(en, 0.62, 0.8, 0.0, 0.5))
    # grass
    gn = w.noise(w.scale(o, 0.5), 1.0, 5, 0.6)
    gf = w.noise(w.scale(o, 6.0), 1.0, 4)
    col_g = w.ramp(gn, [(0.2, L(grass, 0.8)), (0.6, L(grass)), (0.9, L("#7E8A4A"))])
    col_g = w.mul(col_g, w.ramp(gf, [(0.3, (0.82, 0.82, 0.82, 1)), (0.7, (1.08, 1.08, 1.04, 1))]))
    edge_n = w.noise(w.scale(o, 1.2), 1.0, 4)
    gmask = w.mr(w.m("ADD", green, w.m("MULTIPLY", w.m("SUBTRACT", edge_n, 0.5), 0.6)), 0.35, 0.65)
    pmask = w.mr(w.m("ADD", paved, w.m("MULTIPLY", w.m("SUBTRACT", edge_n, 0.5), 0.25)), 0.4, 0.6)
    col = w.mix(col_e, pv_col, pmask)
    col = w.mix(col, col_g, gmask)
    col = w.mix(col, w.mul(col, w.gray(0.62)), w.m("MULTIPLY", wet, 0.8))
    col = w.mix(col, L(water), w.mr(wet, 0.8, 0.95))
    h = w.m("ADD", w.m("MULTIPLY", w.m("SUBTRACT", 1.0, pv_fac), w.m("MULTIPLY", pmask, 0.6)),
            w.m("MULTIPLY", ef, 0.3))
    rough = w.mr(wet, 0.0, 1.0, 0.92, 0.45)
    w.out(col, rough, 0.0, w.bump(h, 0.6, 0.03), spec=0.3)
    return mat


# ---------------------------------------------------------------------------------------------
# library
# ---------------------------------------------------------------------------------------------
def library():
    """Create every architecture material; returns {slot name: material}."""
    m = {}
    for fn, args in (
            (ashlar, ("W_Stone",)),
            (ashlar, ("W_StoneDark", "#77736A", "#8E8778")),
            (brick, ("W_Brick",)),
            (brick, ("W_BrickWarm", "#7D776E", "#A39C8C")),
            (paving, ("W_Paving",)),
            (rammed_earth, ("W_Earth",)),
            (plaster, ("W_Plaster",)),
            (plaster, ("W_PlasterWarm", "#D5C6A8")),
            (red_wall, ("W_RedWall",)),
            (marble, ("W_Marble",)),
            (lacquer, ("W_Lacquer",)),
            (lacquer, ("W_LacquerDark", "#5E1B12", 0.42, 0.1)),
            (wood, ("W_Wood",)),
            (wood, ("W_WoodDark", "#3B2A1E")),
            (beam_paint, ("W_BeamPaint",)),
            (bracket, ("W_Bracket",)),
            (lattice, ("W_Lattice",)),
            (gate_door, ("W_GateDoor",)),
            (gold, ("W_Gold",)),
            (iron, ("W_Iron",)),
            (dark, ("W_Dark",)),
            (roof_tile, ("W_Tile",)),
            (roof_tile, ("W_TileDark", "#3E444B", 0.5, 0.32, False, 0.12, 0.35)),
            (roof_tile, ("W_TileGold", "#D09A28", 0.5, 0.32, True, 0.1, 0.0)),
            (roof_tile, ("W_TileGreen", "#3B7452", 0.5, 0.32, True, 0.1, 0.0)),
            (flat, ("W_Ridge", "#3F454B", 0.6)),
            (flat, ("W_RidgeGold", "#B88420", 0.3)),
            (flat, ("W_RidgeGreen", "#2F5E44", 0.3)),
            (fascia, ("W_Fascia",)),
            (flat, ("W_Gable", "#7A2418", 0.6)),
            (rock, ("W_Rock",)),
    ):
        mat = fn(*args)
        m[mat.name] = mat
    return m
