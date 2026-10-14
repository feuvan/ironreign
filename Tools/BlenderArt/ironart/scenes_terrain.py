"""Illustrated Scenes: heightfields, terrain meshes and materials, water, rock, mist cards.

numpy noise (value noise upsampled bicubically, fBm, ridged multifractal with domain warping,
thermal erosion) -> :func:`grid` (a heightfield mesh over an arbitrary x/y rectangle, UVs in
metres) -> procedural PBR materials that read slope / height / 3D noise in *world* coordinates
(no UV stretching on cliffs).  Every material goes through the ``IR_Fog`` aerial perspective.
"""

import math
import random

import numpy as np

# =============================================================================================
# numpy noise
# =============================================================================================


def value_noise(h, w, cell, rng):
    """Bicubic value noise (h x w) with feature size ``cell`` px, ~0..1."""
    from PIL import Image
    cell = max(1.0, float(cell))
    gh, gw = int(math.ceil(h / cell)) + 3, int(math.ceil(w / cell)) + 3
    g = rng.random((gh, gw)).astype(np.float32)
    im = Image.fromarray(g, "F").resize((int(gw * cell), int(gh * cell)), Image.BICUBIC)
    a = np.asarray(im, np.float32)
    oy = int(rng.integers(0, max(1, int(cell))))
    ox = int(rng.integers(0, max(1, int(cell))))
    return a[oy:oy + h, ox:ox + w]


def fbm(h, w, cell=64.0, octaves=6, gain=0.5, lac=2.0, seed=0):
    rng = np.random.default_rng(seed)
    acc = np.zeros((h, w), np.float32)
    amp, tot, c = 1.0, 0.0, float(cell)
    for _ in range(octaves):
        acc += amp * value_noise(h, w, c, rng)
        tot += amp
        amp *= gain
        c /= lac
    return acc / tot


def ridged(h, w, cell=96.0, octaves=6, gain=0.5, lac=2.1, sharp=1.6, seed=0, warp=0.0,
           warp_cell=None):
    """Ridged multifractal (0..1), optionally domain warped by ``warp`` px."""
    rng = np.random.default_rng(seed)
    if warp > 0:
        wc = warp_cell or cell
        wx = (fbm(h, w, wc, 4, 0.5, seed=seed + 101) - 0.5) * 2 * warp
        wy = (fbm(h, w, wc, 4, 0.5, seed=seed + 202) - 0.5) * 2 * warp
    acc = np.zeros((h, w), np.float32)
    amp, tot, c = 1.0, 0.0, float(cell)
    prev = np.ones((h, w), np.float32)
    for o in range(octaves):
        n = value_noise(h + 2 * int(warp) + 4, w + 2 * int(warp) + 4, c, rng) if warp > 0 else \
            value_noise(h, w, c, rng)
        if warp > 0:
            p = int(warp) + 2
            ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
            sx = np.clip(xs + wx + p, 0, n.shape[1] - 1.001)
            sy = np.clip(ys + wy + p, 0, n.shape[0] - 1.001)
            x0, y0 = sx.astype(int), sy.astype(int)
            fx, fy = sx - x0, sy - y0
            n = (n[y0, x0] * (1 - fx) * (1 - fy) + n[y0, x0 + 1] * fx * (1 - fy)
                 + n[y0 + 1, x0] * (1 - fx) * fy + n[y0 + 1, x0 + 1] * fx * fy)
        r = 1.0 - np.abs(2.0 * np.clip(n, 0.0, 1.0) - 1.0)
        r = r ** sharp
        r *= np.clip(prev * 1.6, 0.25, 1.0) if o > 0 else 1.0
        prev = r
        acc += amp * r
        tot += amp
        amp *= gain
        c /= lac
    return acc / tot


def thermal_erosion(hm, iters=30, talus=0.6, k=0.25):
    """Simple thermal erosion: material slides to lower neighbours where the drop exceeds
    ``talus`` (height units per px).  Softens peaks into scree slopes, keeps ridges."""
    h = hm.astype(np.float32).copy()
    for _ in range(iters):
        p = np.pad(h, 1, mode="edge")
        nb = [p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:]]
        out = np.zeros_like(h)
        inc = np.zeros_like(h)
        for i, n in enumerate(nb):
            d = h - n
            m = np.where(d > talus, (d - talus) * k * 0.25, 0.0)
            out += m
            # give to that neighbour: shift back
            if i == 0:
                inc[:-1, :] += m[1:, :]
            elif i == 1:
                inc[1:, :] += m[:-1, :]
            elif i == 2:
                inc[:, :-1] += m[:, 1:]
            else:
                inc[:, 1:] += m[:, :-1]
        h = h - out + inc
    return h


def blur(a, r):
    from .scenes_look import soft_blur
    return soft_blur(a, r)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# =============================================================================================
# meshes
# =============================================================================================
def grid(name, heights, x0, x1, y0, y1, mat=None, col=None, attrs=None, smooth=True):
    """Heightfield mesh over [x0, x1] x [y0, y1].  ``heights[j, i]``: j = 0 is the y0 (near)
    row, i = 0 is x0.  UVs in metres (x, y).  ``attrs`` {name: HxW float array} become POINT
    float attributes readable by materials (Attribute node)."""
    import bpy
    H, W = heights.shape
    xs = np.linspace(x0, x1, W, dtype=np.float32)
    ys = np.linspace(y0, y1, H, dtype=np.float32)
    gx, gy = np.meshgrid(xs, ys)
    co = np.stack([gx, gy, heights.astype(np.float32)], -1).reshape(-1)
    me = bpy.data.meshes.new(name)
    me.vertices.add(W * H)
    me.vertices.foreach_set("co", co)
    ii, jj = np.meshgrid(np.arange(W - 1), np.arange(H - 1))
    v0 = (jj * W + ii).reshape(-1)
    # CCW seen from above (+y is row j+1)
    quads = np.stack([v0, v0 + 1, v0 + W + 1, v0 + W], -1).reshape(-1).astype(np.int32)
    nq = (W - 1) * (H - 1)
    me.loops.add(nq * 4)
    me.loops.foreach_set("vertex_index", quads)
    me.polygons.add(nq)
    me.polygons.foreach_set("loop_start", np.arange(0, nq * 4, 4, dtype=np.int32))
    me.polygons.foreach_set("loop_total", np.full(nq, 4, dtype=np.int32))
    me.polygons.foreach_set("use_smooth", np.full(nq, smooth, dtype=bool))
    uv = me.uv_layers.new(name="UVMap")
    u = gx.reshape(-1)[quads]
    v = gy.reshape(-1)[quads]
    uv.data.foreach_set("uv", np.stack([u, v], -1).reshape(-1).astype(np.float32))
    for k, arr in (attrs or {}).items():
        a = me.attributes.new(k, "FLOAT", "POINT")
        a.data.foreach_set("value", arr.astype(np.float32).reshape(-1))
    me.update(calc_edges=True)
    me.validate()
    obj = bpy.data.objects.new(name, me)
    (col or bpy.context.scene.collection).objects.link(obj)
    if mat is not None:
        me.materials.append(mat)
    return obj


def sample(heights, x0, x1, y0, y1, x, y):
    """Bilinear height at world (x, y) of a :func:`grid` heightfield."""
    H, W = heights.shape
    fx = (x - x0) / (x1 - x0) * (W - 1)
    fy = (y - y0) / (y1 - y0) * (H - 1)
    fx = min(max(fx, 0.0), W - 1.001)
    fy = min(max(fy, 0.0), H - 1.001)
    i, j = int(fx), int(fy)
    tx, ty = fx - i, fy - j
    return float(heights[j, i] * (1 - tx) * (1 - ty) + heights[j, i + 1] * tx * (1 - ty)
                 + heights[j + 1, i] * (1 - tx) * ty + heights[j + 1, i + 1] * tx * ty)


def normal_z(heights, x0, x1, y0, y1):
    """Per-vertex up component of the surface normal (1 = flat)."""
    H, W = heights.shape
    dx = (x1 - x0) / (W - 1)
    dy = (y1 - y0) / (H - 1)
    gy, gx = np.gradient(heights, dy, dx)
    return 1.0 / np.sqrt(1.0 + gx * gx + gy * gy)


class Field:
    """A heightfield with its world rectangle (for sampling/scattering after building)."""

    def __init__(self, heights, x0, x1, y0, y1):
        self.h = heights
        self.x0, self.x1, self.y0, self.y1 = x0, x1, y0, y1

    def z(self, x, y):
        return sample(self.h, self.x0, self.x1, self.y0, self.y1, x, y)

    def nz(self):
        return normal_z(self.h, self.x0, self.x1, self.y0, self.y1)

    def nz_at(self, x, y, eps=None):
        e = eps or (self.x1 - self.x0) / (self.h.shape[1] - 1)
        dzdx = (self.z(x + e, y) - self.z(x - e, y)) / (2 * e)
        dzdy = (self.z(x, y + e) - self.z(x, y - e)) / (2 * e)
        return 1.0 / math.sqrt(1 + dzdx * dzdx + dzdy * dzdy)

    def build(self, name, mat=None, col=None, attrs=None):
        return grid(name, self.h, self.x0, self.x1, self.y0, self.y1, mat, col, attrs)


# =============================================================================================
# materials
# =============================================================================================
def _nb(name):
    from .materials import new
    return new(name)


def _fin(mat, nb, shader):
    """Fog + output."""
    from .scenes_sky import fog_node
    nb.output(fog_node(nb, shader))
    mat["ir_fog"] = 1
    return mat


def wcoord(nb, scale=1.0):
    """World-position vector scaled (objects of this family are built in world space)."""
    from .scenes_sky import G
    g = G(nb.tree)
    p = nb.node("ShaderNodeNewGeometry").outputs["Position"]
    if scale == 1.0:
        return p
    return g.vmath("SCALE", p, scale=scale).outputs[0]


def noise(nb, vec, scale, detail=6.0, rough=0.55, dist=0.0, dim="3D"):
    n = nb.node("ShaderNodeTexNoise", noise_dimensions=dim)
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = rough
    n.inputs["Distortion"].default_value = dist
    nb.link(vec, n.inputs["Vector"])
    return n.outputs["Fac"]


def terrain_material(name="Terrain", grass=("#56703A", "#7E8442"), dry="#9A8A58", dirt="#76644A",
                     rock=("#6C675E", "#9A9384"), snow=None, slope=(0.80, 0.90), rock_scale=0.06,
                     grass_scale=0.012, snow_h=(9e9, 9e9), strata=0.25, bump=0.35, dry_amt=0.35,
                     roughness=0.92, sheen=0.15, extra=None):
    """Painterly-realistic ground: two greens + dry patches on gentle slopes, rock with strata on
    steep ones (world-space 3D noise: no stretching on cliffs), optional snow above ``snow_h``
    (z0, z1).  Colours sRGB hex."""
    from .scenes_sky import G, lin4
    mat, nb, created = _nb(name)
    if not created:
        return mat
    b = G(nb.tree)
    geo = nb.node("ShaderNodeNewGeometry")
    P = geo.outputs["Position"]
    nz = b.sep(geo.outputs["Normal"])[2]
    z = b.sep(P)[2]
    big = noise(nb, P, grass_scale, 5, 0.6)
    mid = noise(nb, P, grass_scale * 6, 4, 0.6)
    fine = noise(nb, P, grass_scale * 60, 3, 0.6)
    g = b.mix(lin4(grass[0]), lin4(grass[1]), b.smooth(big, 0.35, 0.68))
    g = b.mix(g, lin4(dry), b.math("MULTIPLY", b.smooth(mid, 0.55, 0.75), dry_amt))
    g = b.mix(g, b.cmul(g, 0.78), b.smooth(fine, 0.45, 0.7))
    # dirt on transitions
    rn = noise(nb, P, rock_scale, 6, 0.62)
    rock_c = b.mix(lin4(rock[0]), lin4(rock[1]), b.smooth(rn, 0.35, 0.65))
    if strata > 0:
        w = nb.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="Z",
                    wave_profile="SIN")
        w.inputs["Scale"].default_value = 0.35
        w.inputs["Distortion"].default_value = 8.0
        w.inputs["Detail"].default_value = 4.0
        b.link(b.vmath("SCALE", P, scale=0.18).outputs[0], w.inputs["Vector"])
        rock_c = b.mix(rock_c, b.cmul(rock_c, 0.72), b.math("MULTIPLY", w.outputs["Fac"], strata))
    rock_c = b.mix(rock_c, b.cmul(rock_c, 0.6), b.smooth(fine, 0.55, 0.85))
    # slope mask with noisy edge
    edge = b.math("ADD", nz, b.math("MULTIPLY", b.math("SUBTRACT", mid, 0.5), 0.12))
    rocky = b.smooth(edge, slope[1], slope[0])
    dirt_m = b.math("MULTIPLY", b.smooth(edge, slope[1] + 0.06, slope[0] + 0.02), 0.6)
    col = b.mix(g, lin4(dirt), dirt_m)
    col = b.mix(col, rock_c, rocky)
    if snow:
        sm = b.smooth(b.math("ADD", z, b.math("MULTIPLY", b.math("SUBTRACT", mid, 0.5), (snow_h[1] - snow_h[0]) * 0.8)),
                      snow_h[0], snow_h[1])
        sm = b.math("MULTIPLY", sm, b.smooth(nz, 0.55, 0.75))
        col = b.mix(col, lin4(snow), sm)
    if extra:
        col = extra(b, col, P, nz, z)
    h = b.math("ADD", b.math("MULTIPLY", fine, 0.5), b.math("MULTIPLY", rn, rocky))
    p = b.principled(Base_Color=col, Roughness=roughness, Specular_IOR_Level=0.3,
                     Sheen_Weight=sheen, Sheen_Roughness=0.5,
                     Normal=b.bump(h, bump, 0.15))
    return _fin(mat, nb, p.outputs[0])


def rock_material(name="Rock", colors=("#5E5A54", "#8C8578"), scale=0.08, strata=0.35,
                  moss=None, moss_amt=0.0, bump=0.6, vertical=True, roughness=0.88):
    """Cliff / boulder rock: world-space noise, vertical strata (karst) or horizontal, optional
    moss on up-facing parts."""
    from .scenes_sky import G, lin4
    mat, nb, created = _nb(name)
    if not created:
        return mat
    b = G(nb.tree)
    geo = nb.node("ShaderNodeNewGeometry")
    P = geo.outputs["Position"]
    nz = b.sep(geo.outputs["Normal"])[2]
    n1 = noise(nb, P, scale, 7, 0.62, 0.3)
    n2 = noise(nb, P, scale * 8, 4, 0.6)
    col = b.mix(lin4(colors[0]), lin4(colors[1]), b.smooth(n1, 0.3, 0.7))
    w = nb.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="X" if vertical else "Z",
                wave_profile="SAW")
    w.inputs["Scale"].default_value = 1.0
    w.inputs["Distortion"].default_value = 6.0
    w.inputs["Detail"].default_value = 6.0
    sc = (scale * 4, scale * 4, scale * 0.6) if vertical else (scale * 0.8, scale * 0.8, scale * 5)
    b.link(b.vmath("MULTIPLY", P, b.vec(sc)).outputs[0], w.inputs["Vector"])
    st = w.outputs["Fac"]
    col = b.mix(col, b.cmul(col, 0.62), b.math("MULTIPLY", b.smooth(st, 0.6, 0.95), strata))
    col = b.mix(col, b.cmul(col, 1.18), b.math("MULTIPLY", b.smooth(n2, 0.6, 0.8), 0.6))
    if moss and moss_amt > 0:
        mm = b.math("MULTIPLY", b.smooth(b.math("ADD", nz, b.math("MULTIPLY", n2, 0.3)), 0.75, 1.0), moss_amt)
        col = b.mix(col, lin4(moss), mm)
    h = b.math("ADD", n1, b.math("MULTIPLY", st, 0.4))
    p = b.principled(Base_Color=col, Roughness=roughness, Specular_IOR_Level=0.3,
                     Normal=b.bump(h, bump, 0.2))
    return _fin(mat, nb, p.outputs[0])


def water_material(name="Water", deep="#1C3440", shallow="#3E6670", roughness=0.04, ripple=0.25,
                   ripple_scale=0.6, stretch=(1.0, 4.0), foam=None, murk=0.0, flow=None):
    """Reflective water (glossy + fresnel, base tint), ripples stretched along x (wind).  ``murk``
    > 0 = muddy flood water (more diffuse)."""
    from .scenes_sky import G, lin4
    mat, nb, created = _nb(name)
    if not created:
        return mat
    b = G(nb.tree)
    P = nb.node("ShaderNodeNewGeometry").outputs["Position"]
    Pw = b.vmath("MULTIPLY", P, b.vec((ripple_scale / stretch[0], ripple_scale / stretch[1] * 4.0,
                                        ripple_scale))).outputs[0]
    r1 = noise(nb, Pw, 1.0, 6, 0.6, 0.5)
    r2 = noise(nb, b.vmath("SCALE", Pw, scale=4.3).outputs[0], 1.0, 3, 0.5)
    h = b.math("ADD", r1, b.math("MULTIPLY", r2, 0.4))
    col = b.mix(lin4(shallow), lin4(deep), b.smooth(noise(nb, P, 0.01, 3, 0.5), 0.3, 0.7))
    if foam:
        fm = b.smooth(noise(nb, b.vmath("MULTIPLY", P, b.vec((0.25, 1.4, 0.25))).outputs[0], 1.0, 6, 0.6, 1.0),
                      0.62, 0.8)
        col = b.mix(col, lin4(foam), b.math("MULTIPLY", fm, 0.7))
    p = b.principled(Base_Color=col, Roughness=roughness + murk * 0.25, Specular_IOR_Level=0.5,
                     IOR=1.33, Coat_Weight=0.0, Normal=b.bump(h, ripple, 0.05))
    return _fin(mat, nb, p.outputs[0])


def plane(name, x0, x1, y0, y1, z=0.0, mat=None, col=None, res=1):
    import bpy
    me = bpy.data.meshes.new(name)
    me.from_pydata([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    uv.data.foreach_set("uv", [x0, y0, x1, y0, x1, y1, x0, y1])
    me.update()
    o = bpy.data.objects.new(name, me)
    (col or bpy.context.scene.collection).objects.link(o)
    if mat:
        me.materials.append(mat)
    return o


# =============================================================================================
# mist cards (painterly low cloud banks / valley mist)
# =============================================================================================
def mist_material(name, color="#E8E0D4", strength=1.0, density=0.8, scale=1.0, seed=0.0,
                  softness=0.35, light=0.0, stretch=3.0, edge=0.18):
    """Emissive, alpha-cut card shader for mist banks: fbm alpha with soft edges (generated
    coordinates so a card fades to 0 at its rim), no fog wrap (it is the fog)."""
    from .scenes_sky import G, lin4
    mat, nb, created = _nb(name)
    if not created:
        return mat
    mat.blend_method = "BLEND"
    b = G(nb.tree)
    tc = nb.node("ShaderNodeTexCoord")
    gen = tc.outputs["Generated"]
    gx, gy, _ = b.sep(gen)
    v = b.comb(b.math("MULTIPLY", gx, 3.0 * scale * stretch), b.math("MULTIPLY", gy, 3.0 * scale), seed)
    n = noise(nb, v, 1.0, 7, 0.6, 0.4)
    # rim falloff
    ex = b.math("MULTIPLY", b.smooth(gx, 0.0, edge), b.smooth(gx, 1.0, 1.0 - edge))
    ey = b.math("MULTIPLY", b.smooth(gy, 0.0, edge * 1.6), b.smooth(gy, 1.0, 1.0 - edge * 1.6))
    a = b.math("MULTIPLY", b.smooth(n, 0.5 - softness * 0.5, 0.5 + softness), density)
    a = b.math("MULTIPLY", a, b.math("MULTIPLY", ex, ey))
    # brighter tops
    shade = b.math("ADD", 0.75, b.math("MULTIPLY", gy, 0.35))
    em = nb.node("ShaderNodeEmission")
    b.link(b.cmul(lin4(color), b.math("MULTIPLY", shade, strength)), em.inputs["Color"])
    em.inputs["Strength"].default_value = 1.0
    sh = em.outputs[0]
    if light > 0:
        tr = nb.node("ShaderNodeBsdfTranslucent")
        tr.inputs["Color"].default_value = lin4(color)
        ad = nb.node("ShaderNodeAddShader")
        b.link(em.outputs[0], ad.inputs[0])
        tr2 = nb.node("ShaderNodeMixShader")
        tr2.inputs[0].default_value = 1.0 - light
        b.link(tr.outputs[0], tr2.inputs[1])
        b.link(tr.outputs[0], tr2.inputs[2])
        b.link(tr2.outputs[0], ad.inputs[1])
        sh = ad.outputs[0]
    tp = nb.node("ShaderNodeBsdfTransparent")
    mx = nb.node("ShaderNodeMixShader")
    b.link(a, mx.inputs[0])
    b.link(tp.outputs[0], mx.inputs[1])
    b.link(sh, mx.inputs[2])
    nb.output(mx.outputs[0])
    mat["ir_fog"] = 1
    # cards must not cast shadows or be seen by diffuse rays
    return mat


def card(name, center, size, mat, facing=None, rot_z=0.0, tilt=0.0, col=None, shadow=False):
    """Vertical card centred at ``center`` (x, y, z) of ``size`` (w, h), facing -Y (towards a
    camera looking +Y) rotated by ``rot_z``; generated coords span the card 0..1."""
    import bpy
    from mathutils import Euler
    w, h = size
    me = bpy.data.meshes.new(name)
    me.from_pydata([(-w / 2, 0, -h / 2), (w / 2, 0, -h / 2), (w / 2, 0, h / 2), (-w / 2, 0, h / 2)],
                   [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    uv.data.foreach_set("uv", [0, 0, 1, 0, 1, 1, 0, 1])
    me.update()
    o = bpy.data.objects.new(name, me)
    o.location = center
    o.rotation_euler = Euler((tilt, 0, rot_z))
    (col or bpy.context.scene.collection).objects.link(o)
    me.materials.append(mat)
    o.visible_shadow = shadow
    o.visible_diffuse = False
    o.visible_glossy = False
    o.visible_transmission = False
    o.visible_volume_scatter = False
    return o


def flat_card(name, center, size, mat, rot_z=0.0, col=None):
    """Horizontal card (a mist sheet lying over a valley)."""
    import bpy
    from mathutils import Euler
    w, h = size
    me = bpy.data.meshes.new(name)
    me.from_pydata([(-w / 2, -h / 2, 0), (w / 2, -h / 2, 0), (w / 2, h / 2, 0), (-w / 2, h / 2, 0)],
                   [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    uv.data.foreach_set("uv", [0, 0, 1, 0, 1, 1, 0, 1])
    me.update()
    o = bpy.data.objects.new(name, me)
    o.location = center
    o.rotation_euler = Euler((0, 0, rot_z))
    (col or bpy.context.scene.collection).objects.link(o)
    me.materials.append(mat)
    o.visible_shadow = False
    o.visible_diffuse = False
    o.visible_glossy = False
    o.visible_transmission = False
    return o


# =============================================================================================
# landscape recipes
# =============================================================================================
def mountain_range(w_px, h_px, seed, peak=1.0, cell=None, warp=None, erosion=20, base=0.0,
                   ridge_profile=None):
    """A ridged mountain heightfield (h_px rows from near to far, w_px columns), 0..peak.
    ``ridge_profile(u, v)`` (0..1 grids) multiplies the result (shapes the skyline)."""
    cell = cell or w_px / 4.0
    r = ridged(h_px, w_px, cell, 7, 0.52, 2.05, 1.7, seed, warp=warp if warp is not None else cell * 0.35)
    f = fbm(h_px, w_px, cell * 1.5, 4, 0.5, seed=seed + 7)
    hm = (0.7 * r + 0.3 * f)
    if ridge_profile is not None:
        v, u = np.mgrid[0:h_px, 0:w_px].astype(np.float32)
        hm = hm * ridge_profile(u / (w_px - 1), v / (h_px - 1))
    if erosion:
        hm = thermal_erosion(hm, erosion, talus=0.6 / max(w_px, h_px) * 8, k=0.35)
    hm = (hm - hm.min()) / max(1e-6, hm.max() - hm.min())
    return base + hm * peak
