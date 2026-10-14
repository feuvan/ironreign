"""Costume materials: silks with woven motifs, brocade bands, iron/bronze/gold, leather, cords,
jade, pearls (bpy)."""

import bpy

import patterns as PT
from nodes import NB, lin

_IMG = {}


def _pat(kind, size=512):
    if kind not in _IMG:
        arr = {"clouds": lambda: PT.clouds(size), "roundels": lambda: PT.roundels(size),
               "fret": lambda: PT.fret(256), "lattice": lambda: PT.lattice(256)}[kind]()
        _IMG[kind] = PT.to_image("pat_" + kind, arr)
    return _IMG[kind]


def silk(name, rgb, sheen=0.6, rough=0.42, motif=None, motif_rgb=None, motif_scale=9.0,
         motif_metal=0.0, weave=1.0, vary=0.08, sss=0.0, pass_index=5, band=None):
    """Silk/satin: soft sheen, fine weave breakup, optional woven/embroidered motif in UV space
    (UVs are metres, so ``motif_scale`` = tiles per metre)."""
    m = bpy.data.materials.new(name)
    nb = NB(m)
    uv = nb.coord("UV")
    obj = nb.coord("Object")
    base = lin(rgb) if isinstance(rgb, str) else tuple(rgb) + (1,)
    n1 = nb.noise(obj, scale=18.0, detail=3.0)[0]
    col = nb.mix(tuple(c * (1 - vary) for c in base[:3]), tuple(min(1, c * (1 + vary)) for c in base[:3]), n1)
    weave_tex = nb.wave(nb.mapping(uv, scale=(1.0, 1.0, 1.0)), scale=900.0, direction="X")[1]
    h = nb.math("MULTIPLY", weave_tex, 0.15 * weave)
    rough_s = nb.math("ADD", rough, nb.math("MULTIPLY", nb.math("SUBTRACT", n1, 0.5), 0.12))
    metal = 0.0
    if motif:
        img = _pat(motif)
        mv = nb.image(img, nb.mapping(uv, scale=(motif_scale, motif_scale, 1.0)), interp="Linear")[0]
        mvf = nb.math("POWER", nb.sep(mv)[0], 0.8)
        col = nb.mix(col, motif_rgb or (0.75, 0.58, 0.28), mvf)
        h = nb.math("ADD", h, nb.math("MULTIPLY", mvf, 0.6))
        rough_s = nb.mixf(rough_s, 0.32, mvf)
        if motif_metal:
            metal = nb.math("MULTIPLY", mvf, motif_metal)
    if band is not None:
        # collar band painted in the shader along UV v (= metres below the neckline): a crisp,
        # smooth edge whatever the mesh density.  band = dict(width, rgb, thread, motif, edge_rgb)
        u, v, _ = nb.sep(uv)
        bw = band.get("width", 0.03)
        inb = nb.maprange(v, bw + 0.0012, bw - 0.0012)
        bcol = lin(band["rgb"]) if isinstance(band["rgb"], str) else tuple(band["rgb"]) + (1,)
        bc = bcol
        if band.get("motif"):
            vec = nb.combine(nb.math("MULTIPLY", u, 1.0 / bw), nb.math("MULTIPLY", v, 1.0 / bw), 0.0)
            mv = nb.sep(nb.image(_pat(band["motif"]), vec, interp="Linear")[0])[0]
            bc = nb.mix(bcol, tuple(band.get("thread", (0.6, 0.45, 0.2))) + (1,), mv)
            h = nb.math("ADD", h, nb.math("MULTIPLY", nb.math("MULTIPLY", mv, inb), 0.5))
        # thin piping at the band's outer edge
        pipe = nb.math("MULTIPLY", nb.maprange(v, bw - 0.0045, bw - 0.0025), nb.maprange(v, bw - 0.0005, bw - 0.0022))
        bc = nb.mix(bc, tuple(band.get("edge_rgb", (0.5, 0.36, 0.12))) + (1,), pipe)
        col = nb.mix(col, bc, inb)
        rough_s = nb.mixf(rough_s, band.get("rough", 0.45), inb)
    # sheen tinted toward the dye (white sheen turns dark silks silvery under a hard key)
    stint = tuple(min(1.0, 0.35 + 2.5 * c) for c in base[:3]) + (1,)
    p = nb.principled(Base_Color=col, Roughness=nb.math("ADD", rough_s, 0.12), Metallic=metal,
                      Sheen_Weight=sheen * 0.7, Sheen_Roughness=0.45, Sheen_Tint=stint,
                      Specular_IOR_Level=0.2, Normal=nb.bump(h, 0.35, 0.0006))
    if sss:
        p.inputs["Subsurface Weight"].default_value = sss
        p.inputs["Subsurface Scale"].default_value = 0.002
    nb.output(p.outputs[0])
    m.pass_index = pass_index
    return m


def brocade(name, rgb, thread_rgb=(0.80, 0.62, 0.30), motif="fret", scale=1.0, rough=0.4):
    """Collar/trim band: a border motif running along the band (UV u = length, v = across)."""
    m = bpy.data.materials.new(name)
    nb = NB(m)
    uv = nb.coord("UV")
    u, v, _ = nb.sep(uv)
    # tile: band width ~3.5 cm -> one motif square per band width
    vec = nb.combine(nb.math("MULTIPLY", u, 28.0 * scale), nb.math("MULTIPLY", v, 28.0 * scale), 0.0)
    img = _pat(motif)
    mv = nb.sep(nb.image(img, vec, interp="Linear")[0])[0]
    base = lin(rgb) if isinstance(rgb, str) else tuple(rgb) + (1,)
    col = nb.mix(base, thread_rgb, mv)
    p = nb.principled(Base_Color=col, Roughness=nb.mixf(rough, 0.3, mv), Metallic=nb.math("MULTIPLY", mv, 0.5),
                      Sheen_Weight=0.4, Sheen_Tint=(1, 1, 1, 1), Normal=nb.bump(mv, 0.5, 0.0008))
    nb.output(p.outputs[0])
    return m


def metal(name, rgb, rough=0.38, metallic=1.0, patina=0.25, scratches=0.4, pass_index=4):
    """Iron/bronze/gold with roughness breakup, dark patina in cavities (noise) and fine scratches."""
    m = bpy.data.materials.new(name)
    nb = NB(m)
    obj = nb.coord("Object")
    base = lin(rgb) if isinstance(rgb, str) else tuple(rgb) + (1,)
    n1 = nb.noise(obj, scale=40.0, detail=4.0, rough=0.6)[0]
    n2 = nb.noise(obj, scale=6.0, detail=2.0)[0]
    pat = nb.maprange(n2, 0.45, 0.7)
    col = nb.mix(base, tuple(c * 0.35 for c in base[:3]), nb.math("MULTIPLY", pat, patina))
    col = nb.mix(col, tuple(min(1, c * 1.25) for c in base[:3]), nb.math("MULTIPLY", nb.maprange(n1, 0.55, 0.8), 0.4))
    sc = nb.wave(nb.mapping(obj, rot=(0.3, 0.8, 0.2), scale=(1, 1, 1)), scale=400.0, distortion=8.0, detail=2.0)[1]
    scr = nb.maprange(sc, 0.92, 1.0)
    r = nb.math("ADD", rough, nb.math("MULTIPLY", nb.math("SUBTRACT", n1, 0.5), 0.25))
    r = nb.math("ADD", r, nb.math("MULTIPLY", pat, patina * 0.3))
    r = nb.math("SUBTRACT", r, nb.math("MULTIPLY", scr, scratches * 0.2))
    p = nb.principled(Base_Color=col, Metallic=metallic, Roughness=r,
                      Normal=nb.bump(nb.math("ADD", n1, nb.math("MULTIPLY", scr, 0.3)), 0.12, 0.0008))
    nb.output(p.outputs[0])
    m.pass_index = pass_index
    return m


def plain(name, rgb, rough=0.6, metallic=0.0, sheen=0.0, coat=0.0, bump=0.0, bump_scale=60.0,
          vary=0.1):
    m = bpy.data.materials.new(name)
    nb = NB(m)
    obj = nb.coord("Object")
    base = lin(rgb) if isinstance(rgb, str) else tuple(rgb) + (1,)
    n1 = nb.noise(obj, scale=bump_scale, detail=3.0)[0]
    col = nb.mix(tuple(c * (1 - vary) for c in base[:3]), tuple(min(1, c * (1 + vary)) for c in base[:3]), n1)
    kw = dict(Base_Color=col, Roughness=rough, Metallic=metallic, Sheen_Weight=sheen, Coat_Weight=coat)
    if bump:
        kw["Normal"] = nb.bump(n1, bump, 0.001)
    p = nb.principled(**kw)
    nb.output(p.outputs[0])
    return m


def jade(name="Jade", rgb=(0.35, 0.62, 0.45)):
    m = bpy.data.materials.new(name)
    nb = NB(m)
    p = nb.principled(Base_Color=tuple(rgb) + (1,), Roughness=0.15, Subsurface_Weight=1.0,
                      Subsurface_Radius=(0.4, 0.8, 0.5), Subsurface_Scale=0.004, Coat_Weight=0.6)
    nb.output(p.outputs[0])
    return m


def pearl(name="Pearl"):
    m = bpy.data.materials.new(name)
    nb = NB(m)
    p = nb.principled(Base_Color=(0.85, 0.82, 0.78, 1), Roughness=0.2, Coat_Weight=1.0,
                      Coat_Roughness=0.05, Sheen_Weight=0.5, Subsurface_Weight=0.3,
                      Subsurface_Scale=0.002)
    nb.output(p.outputs[0])
    return m


def tassel(name="Tassel", rgb=(0.55, 0.05, 0.04)):
    """Dyed horsehair (helmet tassels): principled with sheen and per-strand value jitter."""
    m = bpy.data.materials.new(name)
    nb = NB(m)
    info = nb.node("ShaderNodeHairInfo")
    col = nb.mix(tuple(c * 0.6 for c in rgb), tuple(min(1, c * 1.5) for c in rgb), info.outputs["Random"])
    p = nb.principled(Base_Color=col, Roughness=0.4, Sheen_Weight=0.5, Sheen_Tint=(1, 0.6, 0.6, 1))
    nb.output(p.outputs[0])
    return m


def _tassel_physical(name="Tassel", rgb=(0.55, 0.05, 0.04)):
    from nodes import sock
    m = bpy.data.materials.new(name)
    nb = NB(m)
    h = nb.node("ShaderNodeBsdfHairPrincipled", parametrization="COLOR")
    sock(h.inputs, "Color").default_value = tuple(rgb) + (1,)
    sock(h.inputs, "Roughness").default_value = 0.35
    sock(h.inputs, "Radial Roughness").default_value = 0.4
    sock(h.inputs, "Random Color").default_value = 0.15
    nb.output(h.outputs[0])
    return m


_PLATES = {}


def scales(name, rgb=(0.05, 0.05, 0.055), lace_rgb=(0.3, 0.02, 0.015), plate=(0.014, 0.024),
           metallic=0.9, rough=0.4):
    """Texture-based lamellar/scale cloth for small parts (helmet flaps): plate relief, dark
    gaps, lacing cords."""
    if "img" not in _PLATES:
        _PLATES["img"] = PT.to_image("pat_plates", PT.plates(512))
    m = bpy.data.materials.new(name)
    nb = NB(m)
    uv = nb.coord("UV")
    t = nb.image(_PLATES["img"], nb.mapping(uv, scale=(1.0 / (plate[0] * 4), 1.0 / (plate[1] * 4), 1)), interp="Linear")[0]
    hR, lG, _ = nb.sep(t)
    base = tuple(rgb) + (1,)
    col = nb.mix((0.01, 0.01, 0.01), base, nb.maprange(hR, 0.0, 0.3))
    col = nb.mix(col, tuple(lace_rgb) + (1,), lG)
    met = nb.math("MULTIPLY", nb.math("SUBTRACT", 1.0, lG), metallic)
    p = nb.principled(Base_Color=col, Metallic=met, Roughness=nb.mixf(rough, 0.6, lG),
                      Normal=nb.bump(nb.math("ADD", hR, nb.math("MULTIPLY", lG, 0.5)), 0.8, 0.0015))
    nb.output(p.outputs[0])
    m.pass_index = 4
    return m


def lacquer_iron(name, rgb=(0.035, 0.03, 0.028), edge_rgb=(0.32, 0.30, 0.28), rough=0.42, coat=0.6):
    """Black-lacquered iron plates (Chinese lamellar): dark glossy coat over iron, worn to bare
    metal where the noise peaks (edges catch light without the chrome look)."""
    m = bpy.data.materials.new(name)
    nb = NB(m)
    obj = nb.coord("Object")
    n1 = nb.noise(obj, scale=60.0, detail=4.0, rough=0.6)[0]
    wear = nb.maprange(n1, 0.62, 0.78)
    col = nb.mix(tuple(rgb) + (1,), tuple(edge_rgb) + (1,), wear)
    met = nb.mixf(0.25, 0.9, wear)
    r = nb.mixf(rough, 0.35, wear)
    p = nb.principled(Base_Color=col, Metallic=met, Roughness=r, Coat_Weight=coat,
                      Coat_Roughness=0.18, Normal=nb.bump(n1, 0.15, 0.0008))
    nb.output(p.outputs[0])
    m.pass_index = 4
    return m
