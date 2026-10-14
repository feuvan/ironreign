"""Illustrated Scenes: real-scale Chinese architecture built from the shared world builders.

:mod:`ironart.geometry` builds cities in *sprite metres* (a house 1.2 m wide, a gate 3.2 m wide).
Here they are reused at real scale: every builder runs at sprite scale into a MeshBuilder and is
then scaled by ``k`` (default 8: a house becomes ~9 m wide, a gate tower ~25 m).  Because the
builders write UVs in sprite metres, :func:`materials` divides every texture size by ``k`` so
blocks and tiles keep their real sizes (0.6 m ashlar, 25 cm tile channels).

Also: thatched village houses, terrain-following walls, palace terraces, lantern strings.
"""

import math
import random

from mathutils import Matrix, Vector

from . import geometry as geo

TAU = math.tau
K = 8.0


def materials(k=K, roof="#4E5A5E", roof_hi=None, stone="#8E8A80", plaster="#D6C8AC",
              pillar="#8A2A1C", ground=("#8A7E64", "#9A8C6E"), thatch="#8E7A52"):
    """Real-scale material set for the slot names of the geometry builders (+ Thatch, Mud,
    Paving, Lattice, RoofGold)."""
    from . import materials as M
    from . import palette
    s = 1.0 / k
    m = {
        "Stone": M.stone_wall("AStone", stone, block=(0.62 * s, 0.32 * s), bump=0.25, vary=0.14),
        "StoneTop": M.principled("AStoneTop", "#A8A294", 0.85, vary=0.06, vary_scale=0.3),
        "StoneDark": M.principled("AStoneDark", "stone_dark", 0.9, vary=0.1),
        "RoofTile": M.roof_tiles("ARoofTile", roof, channel=0.26 * s, course=0.3 * s, glaze=0.25,
                                 roughness=0.5, bump=0.5, specular=0.4),
        "RoofRidge": M.principled("ARoofRidge", "#3A4446", 0.55, vary=0.03),
        "PillarRed": M.lacquer("APillarRed", pillar, roughness=0.42, coat=0.35, coat_roughness=0.2),
        "GateDoor": M.lacquer("AGateDoor", pillar, roughness=0.5, coat=0.2, coat_roughness=0.3, vary=0.04),
        "Plaster": M.plaster("APlaster", plaster, vary=0.1),
        "Timber": M.dark_wood("ATimber", "timber", grain_scale=6.0 * k),
        "DoorDark": M.principled("ADoorDark", "#211812", 0.8),
        "Gold": M.gold_leaf("AGold"),
        "Ground": M.grass_ground("AGround", ground[0], ground[1], scale=0.6 / k),
        "Foliage": M.foliage("AFoliage", "#4C6A3E", translucency=0.15),
        "FoliageDark": M.foliage("AFoliageDark", "#3A5536", translucency=0.15),
        "Trunk": M.principled("ATrunk", "trunk", 0.8),
        "Thatch": thatch_material("AThatch", thatch),
        "Mud": M.principled("AMud", "#9A8466", 0.95, vary=0.15, vary_scale=0.5),
        "Paving": M.stone_wall("APaving", "#8A857A", block=(0.9 * s, 0.6 * s), bump=0.15, vary=0.12),
        "Lattice": M.principled("ALattice", "#3A2418", 0.7),
        "Window": glow_material("AWindow", "#FFB060", 0.0),
    }
    if roof_hi:
        m["RoofGold"] = M.roof_tiles("ARoofGold", roof_hi, channel=0.26 * s, course=0.3 * s,
                                     glaze=0.6, roughness=0.3, bump=0.5, specular=0.5)
    return m


def thatch_material(name, color="#8E7A52"):
    from .materials import new
    from .scenes_sky import G, lin4
    from .scenes_terrain import _fin, noise
    mat, nb, created = new(name)
    if not created:
        return mat
    b = G(nb.tree)
    P = nb.node("ShaderNodeNewGeometry").outputs["Position"]
    n = noise(nb, b.vmath("MULTIPLY", P, b.vec((40.0, 40.0, 6.0))).outputs[0], 1.0, 5, 0.6, 0.6)
    col = b.mix(b.cmul(lin4(color), 0.6), b.cmul(lin4(color), 1.15), b.smooth(n, 0.3, 0.75))
    p = b.principled(Base_Color=col, Roughness=0.95, Specular_IOR_Level=0.2, Normal=b.bump(n, 0.8, 0.1))
    return _fin(mat, nb, p.outputs[0])


def glow_material(name, color="#FFB060", strength=4.0, base="#2A1E16"):
    """Window/door glow (night scenes): emission over a dark base."""
    from .materials import new
    from .scenes_sky import G, lin4
    mat, nb, created = new(name)
    if not created:
        return mat
    b = G(nb.tree)
    p = b.principled(Base_Color=lin4(base), Roughness=0.8)
    em = nb.node("ShaderNodeEmission")
    em.inputs["Color"].default_value = lin4(color)
    em.inputs["Strength"].default_value = strength
    ad = nb.node("ShaderNodeAddShader")
    b.link(p.outputs[0], ad.inputs[0])
    b.link(em.outputs[0], ad.inputs[1])
    from .scenes_sky import fog_node
    nb.output(fog_node(nb, ad.outputs[0]))
    mat["ir_fog"] = 1
    return mat


# ---------------------------------------------------------------------------------------------
# scaled builders (sprite-metre builders x k)
# ---------------------------------------------------------------------------------------------
def scaled(fn, k=K, at=(0, 0, 0), rot_z=0.0):
    """Run ``fn(mb)`` at sprite scale and return a MeshBuilder scaled by ``k`` placed at ``at``."""
    mb = geo.MeshBuilder()
    fn(mb)
    mb.transform(0, Matrix.Translation(Vector(at)) @ Matrix.Rotation(rot_z, 4, "Z") @ Matrix.Scale(k, 4))
    return mb


def house(rng, style="gable", size=1.0, foundation=0.0, storeys=1, wall="Plaster", roof="RoofTile"):
    """Town house (sprite metres; wrap with :func:`scaled`).  ``foundation`` adds a stone
    plinth that extends below ground (for slopes)."""
    def fn(mb):
        w = rng.uniform(1.0, 1.35) * size
        d = rng.uniform(0.75, 0.95) * size
        if foundation > 0:
            mb.box((0, 0, -foundation), (w + 0.12, d + 0.12, foundation + 0.02), "Stone")
        h = 0.55 * size
        if storeys == 2:
            mb.box((0, 0, 0), (w, d, 0.5 * size), wall)
            mb.box((0, -d * 0.5 - 0.004, 0.08 * size), (w * 0.2, 0.01, 0.3 * size), "DoorDark")
            geo.chinese_roof(mb, (0, 0, 0.5 * size), w, d, 0.2 * size, overhang=0.12 * size,
                             lift=0.04, flare=0.02, style="hip", v_max=0.45, thickness=0.03,
                             res=(8, 3), mat=roof, ornaments=False)
            mb.box((0, 0, 0.56 * size), (w * 0.9, d * 0.85, 0.42 * size), wall)
            for i in range(3):
                mb.box((-w * 0.3 + w * 0.3 * i, -d * 0.425 - 0.004, 0.66 * size),
                       (w * 0.18, 0.01, 0.18 * size), "Lattice")
            geo.chinese_roof(mb, (0, 0, 0.98 * size), w * 0.9, d * 0.85, 0.4 * size,
                             overhang=0.14 * size, lift=0.07, flare=0.04, style=style,
                             thickness=0.035, res=(10, 5), mat=roof, ornaments=False)
        else:
            geo.house(mb, (0, 0, 0), width=w, depth=d, height=h, roof_h=0.42 * size,
                      style=style, wall=wall, roof=roof, lift=0.06)
            mb.box((w * 0.25, -d * 0.48 - 0.006, 0.18 * size), (w * 0.2, 0.01, 0.16 * size), "Lattice")
    return fn


def thatched_house(rng, size=1.0, foundation=0.0):
    """Peasant house: mud walls, steep thatched gable roof, low door."""
    def fn(mb):
        w = rng.uniform(1.0, 1.3) * size
        d = rng.uniform(0.7, 0.85) * size
        h = 0.45 * size
        if foundation > 0:
            mb.box((0, 0, -foundation), (w + 0.08, d + 0.08, foundation + 0.02), "Stone")
        mb.box((0, 0, 0), (w, d, h), "Mud")
        mb.box((-w * 0.15, -d * 0.5 - 0.004, 0.0), (w * 0.18, 0.01, h * 0.62), "DoorDark")
        mb.box((w * 0.25, -d * 0.5 - 0.004, h * 0.4), (w * 0.14, 0.01, h * 0.22), "Lattice")
        geo.chinese_roof(mb, (0, 0, h), w, d, 0.42 * size, overhang=0.1 * size, lift=0.0,
                         flare=0.0, style="gable", curve=1.15, thickness=0.06, res=(6, 4),
                         mat="Thatch", ridge_mat="Thatch", ornaments=False)
    return fn


def gate_tower(two_storey=True, width=3.2, base_h=1.9, door=True):
    def fn(mb):
        geo.gate_tower(mb, (0, 0, 0), width=width, depth=1.8, base_h=base_h, hall_h=0.75,
                       two_storey=two_storey, door=door)
    return fn


def hall(width=3.0, depth=1.8, height=0.9, roof_h=0.9, platform=0.25, double=False, roof="RoofTile"):
    def fn(mb):
        mb.box((0, 0, 0), (width + 0.6, depth + 0.5, platform), "Stone", taper=(0.04, 0.04))
        geo.pavilion(mb, (0, 0, platform), width, depth, height, cols=(6, 3))
        z = platform + height
        if double:
            geo.chinese_roof(mb, (0, 0, z), width, depth, 0.45, overhang=0.4, lift=0.18, flare=0.1,
                             style="hip", v_max=0.42, thickness=0.05, res=(16, 4), mat=roof)
            geo.pavilion(mb, (0, 0, z + 0.2), width * 0.8, depth * 0.75, height * 0.45, cols=(5, 2),
                         lattice=False)
            z += 0.2 + height * 0.45
            geo.chinese_roof(mb, (0, 0, z), width * 0.8, depth * 0.75, roof_h, overhang=0.42,
                             lift=0.24, flare=0.14, style="hip_gable", thickness=0.05, res=(18, 8),
                             mat=roof)
        else:
            geo.chinese_roof(mb, (0, 0, z), width, depth, roof_h, overhang=0.4, lift=0.22,
                             flare=0.12, style="hip_gable", res=(18, 8), mat=roof)
    return fn


def pagoda(tiers=7, base_w=1.4, tier_h=0.55):
    def fn(mb):
        geo.pagoda(mb, (0, 0, 0), tiers=tiers, base_w=base_w, tier_h=tier_h)
    return fn


def wall_run(mb, pts, height=1.4, thickness=0.8, ground=None, step=2.5, foundation=1.2,
             crenels=True, mat="Stone", top_mat="StoneTop"):
    """City wall along a 2D polyline (sprite metres) following ``ground(x, y) -> z`` by short
    segments, each sunk ``foundation`` below its lowest ground point."""
    for i in range(len(pts) - 1):
        a = Vector(pts[i][:2])
        b = Vector(pts[i + 1][:2])
        L = (b - a).length
        n = max(1, int(math.ceil(L / step)))
        for j in range(n):
            p0 = a + (b - a) * (j / n)
            p1 = a + (b - a) * ((j + 1) / n)
            # overlap a little so segments never show seams
            dirv = (p1 - p0).normalized()
            p0e = p0 - dirv * 0.05
            p1e = p1 + dirv * 0.05
            if ground:
                z0 = min(ground(p0e.x, p0e.y), ground(p1e.x, p1e.y))
                z1 = max(ground(p0e.x, p0e.y), ground(p1e.x, p1e.y))
            else:
                z0 = z1 = 0.0
            base = z0 - foundation
            geo.wall_segment(mb, (p0e.x, p0e.y, base), (p1e.x, p1e.y), height=height + (z1 - z0) * 0.5 + foundation,
                             thickness=thickness, mat=mat, top_mat=top_mat, crenels=crenels,
                             merlon=(0.3, 0.2, 0.26), gap=0.22, batter=0.08)


def tower(mb, at, size=1.3, height=2.2, ground_z=0.0, foundation=1.0, roof=True):
    x, y = at[:2]
    mb.box((x, y, ground_z - foundation), (size, size, height + foundation), "Stone",
           taper=(0.1, 0.1), top_mat="StoneTop")
    if roof:
        top = ground_z + height
        tw = size * 0.66
        mb.box((x, y, top), (tw, tw, 0.5), "Plaster")
        geo.pavilion(mb, (x, y, top), tw, tw, 0.5, cols=(3, 3), lattice=False)
        geo.chinese_roof(mb, (x, y, top + 0.5), tw, tw, 0.38, overhang=0.22, lift=0.1, flare=0.05,
                         style="hip_gable", thickness=0.04, res=(10, 5))


def lantern_string(mb, p0, p1, n=8, sag=0.15, mat="Lantern", rope="Rope", size=0.06):
    """A rope between two points with ``n`` round lanterns hanging from it (sprite metres)."""
    a, b = Vector(p0), Vector(p1)
    pts = []
    for i in range(17):
        t = i / 16
        p = a + (b - a) * t - Vector((0, 0, sag * 4 * t * (1 - t)))
        pts.append(tuple(p))
    mb.tube(pts, size * 0.06, rope, 4, caps=False)
    for i in range(n):
        t = (i + 0.5) / n
        p = a + (b - a) * t - Vector((0, 0, sag * 4 * t * (1 - t) + size * 1.3))
        mb.sphere(tuple(p), size, mat, 10, 7, scale=(1, 1, 1.15))
        mb.cylinder(tuple(p + Vector((0, 0, size * 1.1))), tuple(p + Vector((0, 0, size * 1.35))),
                    size * 0.45, size * 0.45, "Gold", 6)


# ---------------------------------------------------------------------------------------------
# world_kit (real-scale kit of the World Models family) helpers
# ---------------------------------------------------------------------------------------------
def wk_materials(**variants):
    """The World Models material library (``W_*`` slots) + optional recoloured variants
    {new_name: (base_name, '#hex')} where the factory supports a colour argument."""
    from . import world_mats as WM
    m = WM.library()
    return m


def wk_build(mb, name, mats, col=None):
    """MeshBuilder -> object with the UV layer named ``MetreUV`` (what world_mats reads)."""
    o = mb.build(name, mats, col=col, auto_smooth_deg=40.0)
    if o.data.uv_layers:
        o.data.uv_layers[0].name = "MetreUV"
    return o


def wk_prototypes(builders, mats, name="WKProtos"):
    """Like :func:`ironart.scenes_flora.prototypes` for world_kit builders (MetreUV)."""
    import bpy
    from .geometry import MeshBuilder
    col = bpy.data.collections.new(name)
    for i, fn in enumerate(builders):
        mb = MeshBuilder()
        fn(mb)
        wk_build(mb, "P%03d_%s" % (i, name), mats, col=col)
    return col


def banner_pole(mb, rng, color=0, height=9.0, cloth=(2.4, 4.2), wind=1.0, at=(0, 0, 0)):
    """A war banner on a tall pole (real scale) using the people kit's flag (Banner<i> slots)."""
    from .scenes_people import _flag
    x, y, z = at
    mb.cylinder((x, y, z - 0.5), (x, y, z + height), 0.09, 0.07, "Wood", 6)
    mb.cylinder((x, y, z + height), (x, y, z + height + 0.5), 0.07, 0.0, "Gold", 6)
    s = cloth[1] / 1.25
    _flag(mb, Vector((x, y, z + height - 0.1)), Vector((0, 0, 1)), color, s, rng,
          w=cloth[0] / s, h=1.25)
