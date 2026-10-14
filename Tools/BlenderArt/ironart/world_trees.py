"""World Models family: trees for the 3D map (Tree_Pine, Tree_Broad, Tree_Bamboo) and city greenery.

Foliage is alpha-tested **cards** carrying a leaf atlas that is *rendered from real geometry*
(hundreds of modelled leaves / pine needle fascicles / bamboo leaf fans per cell, seen from above):
:func:`leaf_atlas` renders albedo, tangent-space normals and cluster AO as float EXR passes, then
writes ``<kind>_Leaves_Base.png`` (sRGB RGBA, alpha = coverage, colour bled into the transparent
area so mips never fringe), ``_Normal.png`` and ``_ORM.png``.  Bark / culm textures are baked from
**periodic** procedural node trees (4D noise on a torus, so the tile repeats seamlessly around the
trunk and along it) by :func:`bark_texture`.

Builders (:func:`broadleaf`, :func:`pine`, :func:`bamboo`) write into a MeshBuilder with two
material slots - ``Bark`` (tiled UVs: integer repeats around each limb) and ``Foliage`` (atlas cell
UVs) - and record per-vertex canopy normals (``cn_x/y/z`` attributes) that
:func:`apply_canopy_normals` turns into custom split normals: cards are shaded like one soft
volume instead of flat planes.  Each model stays under ~3k triangles (they are instanced by the
thousand).
"""

import math
import os
import random

import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import scene
from .geometry import MeshBuilder
from .materials import NB
from .world_mats import W, L

TAU = math.tau


# ---------------------------------------------------------------------------------------------
# leaf atlases
# ---------------------------------------------------------------------------------------------
LEAF_KINDS = {
    # colours: (dark, mid, light) albedo sRGB, underside tint
    "broad": dict(cols=("#3E5A2A", "#58773A", "#7E9748"), under="#8EA070", twig="#4A3A2A"),
    "pine": dict(cols=("#2E4A30", "#446642", "#6E8E4E"), under="#728864", twig="#4E3A2A"),
    "bamboo": dict(cols=("#3E5E2A", "#577A36", "#7E9A48"), under="#8EA46C", twig="#6E7E3E"),
    "shrub": dict(cols=("#3A552C", "#4F6E36", "#728C44"), under="#86986A", twig="#4A3A2A"),
}


def _leaf_shape(mb, base, d, Lh, Wd, z0, tilt, tone, seg=6, fold=0.18, droop=0.0, mat="Leaf", tip=0.0):
    """One leaf: blade outline (ovate / lanceolate by ``Wd/Lh``), folded on the midrib, laid
    from ``base`` along the 2D direction ``d``; ``tilt`` lifts the tip; ``droop`` bends it down."""
    dx, dy = d
    px, py = -dy, dx
    s = mb.n
    rows = []
    for i in range(seg + 1):
        t = i / seg
        w = Wd * 0.5 * (math.sin(math.pi * min(1.0, t * 1.05)) ** 0.75) * (1.0 - 0.25 * t)
        if i == seg:
            w = 0.0
        cx = base[0] + dx * Lh * t
        cy = base[1] + dy * Lh * t
        cz = z0 + tilt * Lh * t - droop * Lh * t * t
        l = mb.v((cx + px * w, cy + py * w, cz + fold * w))
        m = mb.v((cx, cy, cz))
        r = mb.v((cx - px * w, cy - py * w, cz + fold * w))
        rows.append((l, m, r))
    for i in range(seg):
        a, b = rows[i], rows[i + 1]
        mb.face((a[0], a[1], b[1], b[0]), mat, None, True)
        mb.face((a[1], a[2], b[2], b[1]), mat, None, True)
    mb.set_attr("tone", s, mb.n, tone)
    for i, row in enumerate(rows):
        for vid in row:
            mb.vattr.setdefault("along", {})[vid] = i / seg
    return s


def _twig(mb, pts, w, mat="Twig"):
    for a, b in zip(pts[:-1], pts[1:]):
        d = Vector((b[0] - a[0], b[1] - a[1], 0))
        if d.length < 1e-6:
            continue
        n = Vector((-d.y, d.x, 0)).normalized() * w / 2
        ids = [mb.v(Vector(a) + n), mb.v(Vector(b) + n * 0.7), mb.v(Vector(b) - n * 0.7), mb.v(Vector(a) - n)]
        mb.face(ids[::-1], mat)
        mb.set_attr("tone", ids[0], ids[-1] + 1, 0.0)


def _cell_broad(mb, rng, cx, cy, n=105, R=0.47):
    # twigs from the centre outwards (seen in the gaps)
    for k in range(5):
        a = rng.uniform(0, TAU)
        pts = [(cx, cy, 0.0)]
        for j in range(1, 4):
            r = R * 0.8 * j / 3
            a += rng.uniform(-0.25, 0.25)
            pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r, 0.01 * j))
        _twig(mb, pts, 0.012)
    for i in range(n):
        r = R * (rng.random() ** 0.6) * 0.82
        a = rng.uniform(0, TAU)
        bx, by = cx + math.cos(a) * r, cy + math.sin(a) * r
        da = a + rng.uniform(-0.9, 0.9)
        Lh = rng.uniform(0.12, 0.17) * (1.0 - 0.2 * r / R)
        dome = 0.08 * (1.0 - (r / R) ** 2)
        _leaf_shape(mb, (bx, by), (math.cos(da), math.sin(da)), Lh, Lh * rng.uniform(0.5, 0.62),
                    dome + rng.uniform(0.0, 0.03), rng.uniform(-0.25, 0.3), rng.random(), seg=6,
                    fold=0.22)


def _needle(mb, rng, p, d, Ln, w=0.0055, z0=0.0, rise=0.03):
    s = mb.n
    px, py = -d[1] * w, d[0] * w
    z1 = z0 + rise
    ids = [mb.v((p[0] + px, p[1] + py, z0)), mb.v((p[0] + d[0] * Ln + px * 0.3, p[1] + d[1] * Ln + py * 0.3, z1)),
           mb.v((p[0] + d[0] * Ln - px * 0.3, p[1] + d[1] * Ln - py * 0.3, z1)), mb.v((p[0] - px, p[1] - py, z0))]
    mb.face(ids[::-1], "Leaf", None, True)
    mb.set_attr("tone", s, mb.n, rng.random())
    for vid, al in zip(ids, (0.0, 1.0, 1.0, 0.0)):
        mb.vattr.setdefault("along", {})[vid] = al


def _cell_pine(mb, rng, cx, cy, R=0.47):
    """Pine pad seen from above: a lobed 'cloud' of needle tufts (as in Chinese pine painting) -
    4-6 overlapping tufts, each a dense rosette of needles radiating from its twig tip, joined by
    the twig skeleton."""
    tufts = []
    for k in range(rng.randint(5, 7)):
        a = TAU * k / 6 + rng.uniform(-0.4, 0.4)
        r = R * rng.uniform(0.12, 0.36) if k else 0.0
        tufts.append((cx + math.cos(a) * r, cy + math.sin(a) * r, R * rng.uniform(0.3, 0.38)))
    # skeleton: from the pad centre-left to each tuft centre (hidden under the needles)
    entry = (cx - R * 0.35, cy + rng.uniform(-0.08, 0.08), 0.0)
    for (tx, ty, tr) in tufts:
        mid = ((entry[0] + tx) / 2 + rng.uniform(-0.05, 0.05), (entry[1] + ty) / 2 + rng.uniform(-0.05, 0.05), 0.01)
        _twig(mb, [entry, mid, (tx, ty, 0.02)], 0.016)
    for (tx, ty, tr) in tufts:
        n = int(260 * (tr / (R * 0.3)) ** 1.5)
        for q in range(n):
            a = rng.uniform(0, TAU)
            rr = tr * (rng.random() ** 0.8) * 0.55
            b = (tx + math.cos(a) * rr, ty + math.sin(a) * rr)
            da = a + rng.uniform(-0.6, 0.6)
            Ln = tr * rng.uniform(0.45, 0.75) * (1.0 - 0.35 * rr / tr)
            z0 = 0.04 * (1.0 - rr / tr) + rng.uniform(0, 0.03)
            _needle(mb, rng, b, (math.cos(da), math.sin(da)), Ln, 0.0055, z0, rng.uniform(-0.01, 0.04))


def _cell_bamboo(mb, rng, cx, cy, R=0.47):
    """Bamboo sprays: 3 thin twigs across the cell, each with fans of lanceolate drooping leaves."""
    for t in range(3):
        a = rng.uniform(0, TAU)
        d = Vector((math.cos(a), math.sin(a), 0))
        off = Vector((rng.uniform(-0.15, 0.15), rng.uniform(-0.15, 0.15), 0))
        start = Vector((cx, cy, 0)) + off - d * R * 0.7
        pts = [start + d * (R * 1.3 * k / 5) + Vector((0, 0, 0.02 * k + 0.03 * t)) for k in range(6)]
        _twig(mb, [tuple(p) for p in pts], 0.01)
        for f in range(5):
            p = pts[1 + f // 1] if f < 5 else pts[-1]
            k = rng.randint(5, 7)
            base_ang = a + rng.uniform(-0.4, 0.4) + (0.5 if f % 2 else -0.5)
            for q in range(k):
                ang = base_ang + (q - (k - 1) / 2) * rng.uniform(0.22, 0.34)
                Lh = rng.uniform(0.18, 0.26)
                _leaf_shape(mb, (p.x, p.y), (math.cos(ang), math.sin(ang)), Lh, Lh * rng.uniform(0.13, 0.17),
                            0.06 + 0.02 * f + 0.03 * t, rng.uniform(-0.05, 0.15), rng.random(), seg=5, fold=0.12,
                            droop=rng.uniform(0.1, 0.3))


def _cell_shrub(mb, rng, cx, cy):
    _cell_broad(mb, rng, cx, cy, n=95, R=0.47)


def _pass_material(kind, which, cols):
    """Emission material for a leaf-atlas pass: 'albedo', 'normal' or 'ao'."""
    m = bpy.data.materials.new("Leaf_%s" % which)
    m.use_nodes = True
    nb = NB(m.node_tree)
    for n in list(nb.nodes):
        if n.bl_idname != "ShaderNodeOutputMaterial":
            nb.nodes.remove(n)
    w = W(nb)
    em = nb.node("ShaderNodeEmission", inputs={"Strength": 1.0})
    geo_ = nb.node("ShaderNodeNewGeometry")
    if which == "albedo":
        tone = nb.attr("tone").outputs["Fac"]
        along = nb.attr("along").outputs["Fac"]
        c = LEAF_KINDS[kind]["cols"]
        col = w.ramp(tone, [(0.0, c[0]), (0.55, c[1]), (1.0, c[2])])
        # lighter, yellower tips; midrib / along-gradient
        col = w.mix(col, L(c[2], 1.12), w.m("MULTIPLY", along, 0.35))
        col = w.mix(col, L(LEAF_KINDS[kind]["under"]), w.m("MULTIPLY", geo_.outputs["Backfacing"], 0.55))
        fine = w.noise(w.scale(nb.coord("Object"), 60.0), 1.0, 3)
        col = w.mul(col, w.ramp(fine, [(0.3, (0.9, 0.9, 0.9, 1)), (0.7, (1.06, 1.06, 1.03, 1))]))
        nb.link(col, em.inputs["Color"])
    elif which == "twig":
        nb.set(em.inputs["Color"], L(LEAF_KINDS[kind]["twig"]))
    elif which == "normal":
        vm = nb.node("ShaderNodeVectorMath", operation="MULTIPLY_ADD")
        # flip back faces so every texel's normal faces the viewer (+z)
        flip = nb.node("ShaderNodeMath", operation="MULTIPLY_ADD")
        nb.link(geo_.outputs["Backfacing"], flip.inputs[0])
        flip.inputs[1].default_value = -2.0
        flip.inputs[2].default_value = 1.0
        sgn = nb.node("ShaderNodeVectorMath", operation="SCALE")
        nb.link(geo_.outputs["Normal"], sgn.inputs[0])
        nb.link(flip.outputs[0], sgn.inputs["Scale"])
        nb.link(sgn.outputs[0], vm.inputs[0])
        vm.inputs[1].default_value = (0.5, 0.5, 0.5)
        vm.inputs[2].default_value = (0.5, 0.5, 0.5)
        nb.link(vm.outputs[0], em.inputs["Color"])
    else:  # ao
        ao = nb.node("ShaderNodeAmbientOcclusion", samples=8, inputs={"Distance": 0.06})
        nb.link(ao.outputs["AO"], em.inputs["Color"])
    nb.output(em.outputs[0])
    return m


def leaf_atlas(kind, out_dir, size=1024, ss=2, seed=7, samples=12):
    """Render a 2x2-cell leaf atlas for ``kind`` ('broad', 'pine', 'bamboo', 'shrub').
    Returns {'base', 'normal', 'orm': path}.  Cells: (0,0) bottom-left .. (1,1) top-right in UV."""
    import time as _t
    t0 = _t.time()
    scene.reset(seed)
    rng = random.Random(seed)
    mb = MeshBuilder()
    for j in range(2):
        for i in range(2):
            cx, cy = -0.5 + i, -0.5 + j
            {"broad": _cell_broad, "pine": _cell_pine, "bamboo": _cell_bamboo,
             "shrub": _cell_shrub}[kind](mb, rng, cx, cy)
    obj = mb.build("Leaves_" + kind, {}, auto_smooth_deg=None)
    sc = bpy.context.scene
    scene.setup_cycles(samples=samples, transparent=True, preset="fast", view="Standard", look="None",
                       adaptive_threshold=0.0, filter_width=1.0)
    sc.render.resolution_x = sc.render.resolution_y = size * ss
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "OPEN_EXR"
    sc.render.image_settings.color_depth = "32"
    sc.render.image_settings.color_mode = "RGBA"
    sc.use_nodes = False
    cd = bpy.data.cameras.new("LeafCam")
    cd.type = "ORTHO"
    cd.ortho_scale = 2.0
    cam = bpy.data.objects.new("LeafCam", cd)
    sc.collection.objects.link(cam)
    cam.location = (0, 0, 5)
    sc.camera = cam
    w = bpy.data.worlds.new("LeafWorld")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
    passes = {}
    mats = {k: _pass_material(kind, k, None) for k in ("albedo", "normal", "ao", "twig")}
    slot_names = [m.name for m in obj.data.materials]
    os.makedirs(out_dir, exist_ok=True)
    for which in ("albedo", "normal", "ao"):
        for i, nm in enumerate(slot_names):
            if nm.startswith("Twig") and which == "albedo":
                obj.data.materials[i] = mats["twig"]
            else:
                obj.data.materials[i] = mats[which]
        p = os.path.join(out_dir, "_leaf_%s_%s.exr" % (kind, which))
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(p)
        a = np.empty(img.size[0] * img.size[1] * 4, np.float32)
        img.pixels.foreach_get(a)
        passes[which] = a.reshape(img.size[1], img.size[0], 4)[::-1].copy()   # top-down
        bpy.data.images.remove(img)
        os.remove(p)
    from . import post
    from PIL import Image
    alb = passes["albedo"]                     # premultiplied linear (Cycles film is premult)
    alpha = alb[..., 3]
    ao = np.clip(passes["ao"][..., 0] / np.maximum(alpha, 1e-4), 0, 1)
    nrm = passes["normal"][..., :3] / np.maximum(alpha, 1e-4)[..., None]
    # downsample (premultiplied box -> exact coverage), then un-premultiply
    def down(x):
        h, w_ = x.shape[:2]
        return x.reshape(h // ss, ss, w_ // ss, ss, *x.shape[2:]).mean(axis=(1, 3))
    a_s = down(alpha)
    col_s = down(alb[..., :3]) / np.maximum(a_s, 1e-4)[..., None]
    ao_s = down(ao * alpha) / np.maximum(a_s, 1e-4)
    n_s = down(nrm * alpha[..., None]) / np.maximum(a_s, 1e-4)[..., None]
    n_v = n_s * 2 - 1
    n_v /= np.maximum(np.linalg.norm(n_v, axis=-1, keepdims=True), 1e-4)
    n_v[a_s < 0.02] = (0, 0, 1)
    # albedo with soft cluster self-shadowing (AO) multiplied in
    col_s = col_s * (0.55 + 0.45 * ao_s[..., None])
    a_out = np.clip(a_s * 1.15, 0, 1)            # alpha-test at 0.5: keep coverage through mips
    srgb = np.where(col_s <= 0.0031308, col_s * 12.92, 1.055 * np.power(np.maximum(col_s, 0.0031308), 1 / 2.4) - 0.055)
    rgba = np.dstack([np.clip(srgb, 0, 1), a_out]).astype(np.float32)
    rgba = post.alpha_cleanup(rgba, lo=0.02, hi=0.98, bleed=24)
    # colour beyond the bleed: the mean leaf colour (mips of far trees stay green, never black)
    mean = rgba[..., :3][rgba[..., 3] > 0.5].mean(0)
    far = (rgba[..., 3] <= 0.0) & (rgba[..., :3].sum(-1) <= 0.0)
    rgba[far, :3] = mean
    nrm8 = np.clip(n_v * 0.5 + 0.5, 0, 1)
    nrm8[a_s < 0.02] = (0.5, 0.5, 1.0)
    orm = np.dstack([np.clip(0.4 + 0.6 * ao_s, 0, 1), np.full_like(ao_s, 0.62 if kind != "pine" else 0.7),
                     np.zeros_like(ao_s)])
    out = {}
    for key, arr, mode in (("base", rgba, "RGBA"), ("normal", nrm8, "RGB"), ("orm", orm, "RGB")):
        p = os.path.join(out_dir, "%s_Leaves_%s.png" % (kind.capitalize(), key.capitalize() if key != "orm" else "ORM"))
        Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8), mode).save(p, optimize=True)
        out[key] = p
    out["secs"] = _t.time() - t0
    print("[ironart] leaf atlas %s %dpx in %.1fs" % (kind, size, out["secs"]))
    return out


# ---------------------------------------------------------------------------------------------
# periodic bark / culm textures
# ---------------------------------------------------------------------------------------------
def _torus(w, uv, ext_u, ext_v):
    """UV (0..1 tile) -> 4D torus coordinate in metres: seamless in u and v."""
    s = w.sep(uv)
    a = w.m("MULTIPLY", s["X"], TAU)
    b = w.m("MULTIPLY", s["Y"], TAU)
    ru, rv = ext_u / TAU, ext_v / TAU
    vec = w.comb(w.m("MULTIPLY", w.m("COSINE", a), ru), w.m("MULTIPLY", w.m("SINE", a), ru),
                 w.m("MULTIPLY", w.m("COSINE", b), rv))
    return vec, w.m("MULTIPLY", w.m("SINE", b), rv)


def _noise4(w, vec, wv, scale, detail=4.0, rough=0.55, aniso=None):
    n = w.nb.node("ShaderNodeTexNoise", noise_dimensions="4D",
                  inputs={"Scale": scale, "Detail": detail, "Roughness": rough})
    v = vec
    if aniso:
        v = w.nb.mapping(vec, scale=aniso)
    w.nb.link(v, n.inputs["Vector"])
    w.nb.link(wv if not aniso else w.m("MULTIPLY", wv, aniso[2]), n.inputs["W"])
    return n.outputs["Fac"]


def _vor4(w, vec, wv, scale, feature="DISTANCE_TO_EDGE", aniso=None, out="Distance"):
    v = w.nb.node("ShaderNodeTexVoronoi", voronoi_dimensions="4D", feature=feature,
                  inputs={"Scale": scale, "Randomness": 1.0})
    vv = vec
    if aniso:
        vv = w.nb.mapping(vec, scale=aniso)
    w.nb.link(vv, v.inputs["Vector"])
    w.nb.link(wv if not aniso else w.m("MULTIPLY", wv, aniso[2]), v.inputs["W"])
    return v.outputs[out]


def bark_material(kind, ext=(1.6, 3.2)):
    """Periodic bark (UV0 0..1 = one tile of ``ext`` metres): 'pine' (plated, reddish),
    'broad' (grey furrowed), 'bamboo' (green culm with nodes)."""
    name = "TrunkSrc_" + kind      # not "Bark*": world_bake skips final Bark materials
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nb = NB(m.node_tree)
    for n in list(nb.nodes):
        if n.bl_idname != "ShaderNodeOutputMaterial":
            nb.nodes.remove(n)
    w = W(nb)
    uvn = nb.node("ShaderNodeUVMap")
    uvn.uv_map = "UV0"
    uv = uvn.outputs["UV"]
    vec, wv = _torus(w, uv, *ext)
    if kind == "bamboo":
        s = w.sep(uv)
        fv = w.m("FRACT", w.m("MULTIPLY", s["Y"], 4.0))          # 4 nodes per tile
        node_ring = w.mr(w.m("ABSOLUTE", w.m("SUBTRACT", fv, 0.02)), 0.0, 0.025, 1.0, 0.0)
        powder = w.mr(fv, 0.03, 0.12, 1.0, 0.0)
        streak = _noise4(w, vec, wv, 3.0, 3, 0.5, aniso=(9.0, 9.0, 0.4))
        col = w.ramp(streak, [(0.3, L("#5E7A34")), (0.7, L("#7C9442"))])
        col = w.mix(col, L("#A8AE84"), w.m("MULTIPLY", powder, 0.55))
        col = w.mix(col, L("#4A5A2A"), node_ring)
        patch = _noise4(w, vec, wv, 1.2, 3)
        col = w.mix(col, L("#9A8E52"), w.mr(patch, 0.6, 0.8, 0.0, 0.35))
        h = w.m("ADD", node_ring, w.m("MULTIPLY", streak, 0.15))
        w.out(col, w.mr(powder, 0.0, 1.0, 0.45, 0.7), 0.0, w.bump(h, 0.5, 0.01), spec=0.45)
        return m
    if kind == "pine":
        plates = _vor4(w, vec, wv, 3.2, aniso=(1.0, 1.0, 0.45))
        cell = _vor4(w, vec, wv, 3.2, feature="F1", aniso=(1.0, 1.0, 0.45), out="Color")
        fiss = w.mr(plates, 0.0, 0.06, 1.0, 0.0)
        tone = w.sep(cell)["X"]
        col = w.ramp(tone, [(0.0, L("#5B4436")), (0.5, L("#7A5A44")), (1.0, L("#8E6A4C"))])
        fine = _noise4(w, vec, wv, 18.0, 5, 0.6)
        col = w.mul(col, w.ramp(fine, [(0.3, (0.82, 0.82, 0.82, 1)), (0.7, (1.08, 1.06, 1.04, 1))]))
        col = w.mix(col, L("#2A1E16"), fiss)
        lich = _noise4(w, vec, wv, 2.0, 4)
        col = w.mix(col, L("#7E8070"), w.mr(lich, 0.62, 0.75, 0.0, 0.5))
        h = w.m("SUBTRACT", w.m("MULTIPLY", fine, 0.3), fiss)
        w.out(col, 0.88, 0.0, w.bump(h, 0.9, 0.03), spec=0.3)
        return m
    # broad: vertical furrows (anisotropic noise), grey-brown, lichen
    fur = _noise4(w, vec, wv, 2.6, 6, 0.6, aniso=(5.0, 5.0, 0.6))
    ridge = w.m("ABSOLUTE", w.m("SUBTRACT", fur, 0.5))
    furrow = w.mr(ridge, 0.0, 0.08, 1.0, 0.0)
    col = w.ramp(fur, [(0.3, L("#5A5048")), (0.7, L("#776B5C"))])
    fine = _noise4(w, vec, wv, 20.0, 4)
    col = w.mul(col, w.ramp(fine, [(0.3, (0.85, 0.85, 0.85, 1)), (0.7, (1.07, 1.06, 1.04, 1))]))
    col = w.mix(col, L("#2C241E"), w.m("MULTIPLY", furrow, 0.85))
    lich = _noise4(w, vec, wv, 1.6, 4)
    col = w.mix(col, L("#7F876A"), w.mr(lich, 0.6, 0.75, 0.0, 0.55))
    h = w.m("SUBTRACT", w.m("MULTIPLY", fine, 0.25), furrow)
    w.out(col, 0.9, 0.0, w.bump(h, 0.8, 0.03), spec=0.3)
    return m


def bark_texture(kind, out_dir, size=(512, 1024), ext=(1.6, 3.2)):
    """Bake a seamless bark tile (``ext`` metres around x along) to Base / ORM / Normal PNGs."""
    from . import world_bake as WB
    scene.reset(5)
    me = bpy.data.meshes.new("BarkPlane")
    me.from_pydata([(0, 0, 0), (ext[0], 0, 0), (ext[0], ext[1], 0), (0, ext[1], 0)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UV0")
    uv.data.foreach_set("uv", [0, 0, 1, 0, 1, 1, 0, 1])
    o = bpy.data.objects.new("BarkPlane", me)
    bpy.context.scene.collection.objects.link(o)
    me.materials.append(bark_material(kind, ext))
    scene.setup_cycles(samples=8, transparent=False, preset="fast")
    return WB.bake([o], size[0], out_dir, "%s_Bark" % kind.capitalize(), ao=False, samples=8,
                   margin=0, cavity=0.0, height=size[1])


# ---------------------------------------------------------------------------------------------
# tree geometry
# ---------------------------------------------------------------------------------------------
class TreeBuilder:
    """MeshBuilder wrapper: bark limbs with tiled UVs, foliage cards with atlas cells and
    canopy normals."""

    def __init__(self, tile=(1.6, 3.2), bark="Bark", leaf="Foliage"):
        self.mb = MeshBuilder()
        self.tile = tile
        self.bark = bark
        self.leaf = leaf
        self.normals = {}

    def limb(self, pts, radii, sides=7, cap=True, v0=0.0):
        """Tapered limb along ``pts`` with parallel-transport rings; u wraps an integer number
        of bark tiles around, v = length / tile height."""
        mb = self.mb
        P = [Vector(p) for p in pts]
        n = len(P)
        tang = []
        for i in range(n):
            a, b = P[max(0, i - 1)], P[min(n - 1, i + 1)]
            tang.append((b - a).normalized())
        ref = Vector((1, 0, 0)) if abs(tang[0].x) < 0.9 else Vector((0, 1, 0))
        nrm = tang[0].cross(ref).normalized()
        rings = []
        acc = v0
        vs = []
        for i in range(n):
            if i > 0:
                ax = tang[i - 1].cross(tang[i])
                if ax.length > 1e-8:
                    nrm = Matrix.Rotation(tang[i - 1].angle(tang[i]), 3, ax.normalized()) @ nrm
                acc += (P[i] - P[i - 1]).length
            vs.append(acc / self.tile[1])
            bn = tang[i].cross(nrm).normalized()
            ring = [mb.v(P[i] + (nrm * math.cos(TAU * k / sides) + bn * math.sin(TAU * k / sides)) * radii[i])
                    for k in range(sides)]
            rings.append(ring)
        rmean = sum(radii) / len(radii)
        reps = max(1, int(round(TAU * rmean / self.tile[0])))
        for i in range(n - 1):
            for k in range(sides):
                kk = (k + 1) % sides
                u0, u1 = reps * k / sides, reps * (k + 1) / sides
                mb.face((rings[i][k], rings[i][kk], rings[i + 1][kk], rings[i + 1][k]), self.bark,
                        [(u0, vs[i]), (u1, vs[i]), (u1, vs[i + 1]), (u0, vs[i + 1])], True)
        if cap and radii[-1] > 1e-4:
            tip = mb.v(P[-1] + tang[-1] * radii[-1] * 1.5)
            for k in range(sides):
                kk = (k + 1) % sides
                mb.face((rings[-1][k], rings[-1][kk], tip), self.bark,
                        [(reps * k / sides, vs[-1]), (reps * (k + 1) / sides, vs[-1]),
                         (reps * (k + 0.5) / sides, vs[-1] + radii[-1] / self.tile[1])], True)
        return rings

    def card(self, center, normal, size, spin, cell, bend_center=None, bend=0.6, up_bias=0.25,
             aspect=1.0, tilt_axis=None):
        """Square foliage card (``size`` m) facing ``normal``, rotated ``spin`` about it, UVs on
        atlas ``cell`` (i, j) of a 2x2 atlas; canopy normal = blend of the card normal and the
        direction from ``bend_center``."""
        mb = self.mb
        nrm = Vector(normal).normalized()
        ref = Vector((0, 0, 1)) if abs(nrm.z) < 0.95 else Vector((1, 0, 0))
        a = nrm.cross(ref).normalized()
        b = nrm.cross(a).normalized()
        rot = Matrix.Rotation(spin, 3, nrm)
        a, b = rot @ a, rot @ b
        h = size / 2
        c = Vector(center)
        corners = [c - a * h - b * h * aspect, c + a * h - b * h * aspect, c + a * h + b * h * aspect,
                   c - a * h + b * h * aspect]
        i, j = cell
        e = 0.004
        uvs = [(i * 0.5 + e, j * 0.5 + e), (i * 0.5 + 0.5 - e, j * 0.5 + e), (i * 0.5 + 0.5 - e, j * 0.5 + 0.5 - e),
               (i * 0.5 + e, j * 0.5 + 0.5 - e)]
        ids = [mb.v(p) for p in corners]
        mb.face(ids, self.leaf, uvs, True)
        for vid, p in zip(ids, corners):
            if bend_center is not None:
                d = (p - Vector(bend_center))
                d = d.normalized() if d.length > 1e-6 else nrm
                cn = (nrm * (1 - bend) + d * bend + Vector((0, 0, up_bias))).normalized()
            else:
                cn = (nrm + Vector((0, 0, up_bias))).normalized()
            self.normals[vid] = cn
        return ids

    def build(self, name, mats):
        obj = self.mb.build(name, mats, auto_smooth_deg=180.0)
        me = obj.data
        if "UVMap" in me.uv_layers:
            me.uv_layers["UVMap"].name = "UV0"
        apply_canopy_normals(obj, self.normals)
        return obj


def apply_canopy_normals(obj, normals):
    """Custom split normals: card vertices get their canopy normal, bark keeps smooth normals."""
    me = obj.data
    me.use_auto_smooth = True
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    me.update()
    vn = np.zeros(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("normal", vn)
    vn = vn.reshape(-1, 3)
    for vid, n in normals.items():
        vn[vid] = tuple(n)
    me.normals_split_custom_set_from_vertices([tuple(v) for v in vn])
    me.update()


def _curve(p0, d, length, n, bend=(0.0, 0.0, 0.0), rng=None, wobble=0.0):
    pts = []
    p = Vector(p0)
    d = Vector(d).normalized()
    step = length / n
    for i in range(n + 1):
        pts.append(p.copy())
        d = (d + Vector(bend) * (1.0 / n) + (Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.5, 0.5))) * wobble if rng else Vector())).normalized()
        p = p + d * step
    return pts


def _lobe_cards(tb, rng, c, R, n, crown_c, card, zsq=0.8, up=0.35):
    """Fill one foliage lobe (ellipsoid radius R, z squashed) with cards biased to its shell."""
    c = Vector(c)
    for q in range(n):
        d = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1) + up)).normalized()
        r = R * (0.45 + 0.55 * rng.random() ** 0.35)
        p = c + Vector((d.x * r, d.y * r, d.z * r * zsq))
        out = (p - crown_c).normalized()
        n_ = (d * 0.55 + out * 0.45 + Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), 0.2))).normalized()
        tb.card(p, n_, rng.uniform(*card), rng.uniform(0, TAU), (rng.randint(0, 1), rng.randint(0, 1)),
                bend_center=crown_c, bend=0.7, up_bias=0.3)


def broadleaf(tb, rng, H=22.0, crown=0.66, lobes=7, cards_per=30, card=(3.0, 4.4), trunk_r=None, sides=8,
              width=0.86):
    """Round-crowned broadleaf (camphor / elm type): flared trunk forking at the crown base, limbs
    reaching into 6-8 overlapping foliage lobes around a core (an irregular cumulus crown).
    Returns the crown centre."""
    r0 = trunk_r or H * 0.03
    hb = H * (1.0 - crown)                       # crown base
    crown_c = Vector((rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), hb + H * crown * 0.5))
    Rx = H * width * 0.5
    Rz = H * crown * 0.5
    lean = (crown_c - Vector((0, 0, 0))).normalized()
    trunk = _curve((0, 0, -0.8), Vector((lean.x * 0.3, lean.y * 0.3, 1.0)), hb + 0.8 + H * 0.12, 5,
                   (rng.uniform(-0.1, 0.1), rng.uniform(-0.1, 0.1), 0), rng, 0.02)
    radii = [r0 * (1.65 if i == 0 else 1.15 if i == 1 else 1.0 - 0.3 * i / 5) for i in range(len(trunk))]
    tb.limb(trunk, radii, sides)
    fork = trunk[-2]
    # lobes on the crown shell + a core
    centres = []
    for k in range(lobes):
        az = TAU * k / lobes + rng.uniform(-0.3, 0.3)
        el = rng.uniform(-0.15, 0.75)
        d = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))
        centres.append((crown_c + Vector((d.x * Rx * 0.55, d.y * Rx * 0.55, d.z * Rz * 0.5)),
                        H * rng.uniform(0.2, 0.26)))
    centres.append((crown_c + Vector((0, 0, Rz * 0.35)), H * 0.24))
    for (c, R) in centres:
        d = (c - fork)
        Lb = d.length * 0.85
        pts = _curve(fork, d.normalized() + Vector((0, 0, 0.25)), Lb, 4, (0, 0, 0.0), rng, 0.08)
        tb.limb(pts, [r0 * 0.62 * (1 - 0.75 * i / 4) for i in range(5)], 6)
        for q in range(2):
            b2 = pts[2 + q]
            az2 = math.atan2(d.y, d.x) + rng.choice((-1, 1)) * rng.uniform(0.6, 1.2)
            d2 = Vector((math.cos(az2), math.sin(az2), rng.uniform(0.2, 0.8))).normalized()
            p2 = _curve(b2, d2, R * 0.7, 2, (0, 0, 0.3), rng, 0.05)
            tb.limb(p2, [r0 * 0.24, r0 * 0.15, r0 * 0.06], 5)
    for (c, R) in centres:
        _lobe_cards(tb, rng, c, R, cards_per, crown_c, card)
    return crown_c


def pine(tb, rng, H=26.0, sides=7, tiers=6, card=(3.4, 4.8)):
    """Chinese pine (Pinus tabuliformis): tall, slightly bent trunk; near-horizontal limbs in
    loose tiers getting shorter upwards (an umbrella / flat top); layered needle-pad clouds of
    horizontal cards at the limb ends and along them."""
    r0 = H * 0.024
    lean = Vector((rng.uniform(-0.1, 0.1), rng.uniform(-0.1, 0.1), 1.0)).normalized()
    trunk = _curve((0, 0, -0.8), lean, H * 0.9, 8, (rng.uniform(-0.2, 0.2), rng.uniform(-0.2, 0.2), 0), rng, 0.035)
    radii = [r0 * (1.5 if i == 0 else 1.1 if i == 1 else 1.0 - 0.75 * i / 8) for i in range(len(trunk))]
    tb.limb(trunk, radii, sides)
    pads = []
    az = rng.uniform(0, TAU)
    for t in range(tiers):
        f = t / max(1, tiers - 1)
        z = H * (0.4 + 0.5 * f)
        i = min(7, int(z / (H * 0.9) * 8))
        base = trunk[i].lerp(trunk[i + 1], max(0.0, min(1.0, (z - trunk[i].z) / max(1e-3, trunk[i + 1].z - trunk[i].z))))
        nb = 3 if t < tiers - 2 else 2
        for k in range(nb):
            az += TAU / nb * 0.62 + rng.uniform(-0.5, 0.5)
            el = math.radians(rng.uniform(-8, 14))
            Lb = H * (0.36 - 0.22 * f) * rng.uniform(0.75, 1.15)
            d = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))
            pts = _curve(base, d, Lb, 3, (0, 0, 0.3), rng, 0.08)
            tb.limb(pts, [r0 * 0.4, r0 * 0.28, r0 * 0.16, r0 * 0.06], 5)
            pads.append((pts[-1] + Vector((0, 0, 0.4)), 1.6 + Lb * 0.32))
            if Lb > H * 0.15:
                pads.append((pts[1].lerp(pts[2], 0.6) + Vector((0, 0, 0.5)), 1.2 + Lb * 0.22))
    pads.append((trunk[-1] + Vector((0, 0, 0.5)), H * 0.13))
    centre = Vector((0, 0, H * 0.72))
    for (c, R) in pads:
        c = Vector(c)
        n_cards = 4 + int(R * 1.3)
        for q in range(n_cards):
            off = Vector((rng.gauss(0, 0.42), rng.gauss(0, 0.42), 0.0)) * R
            off.z = rng.gauss(0, 0.05) * R + 0.18 * R * (1.0 - min(1.0, off.length / R))
            p = c + off
            n = Vector((rng.uniform(-0.18, 0.18), rng.uniform(-0.18, 0.18), 1.0)).normalized()
            if q % 5 == 4:
                out = Vector((off.x, off.y, 0)).normalized() if off.length > 1e-3 else Vector((1, 0, 0))
                n = (out + Vector((0, 0, 1.0))).normalized()
            tb.card(p, n, rng.uniform(*card) * (0.75 + 0.18 * R / 2.5), rng.uniform(0, TAU),
                    (rng.randint(0, 1), rng.randint(0, 1)), bend_center=c - Vector((0, 0, R * 0.7)),
                    bend=0.5, up_bias=0.5)
    return centre


def bamboo(tb, rng, H=18.0, culms=20, radius=1.3, card=(2.4, 3.4), sides=5, segs=7):
    """Bamboo clump: culms leaning out from a root circle and arching at the top, dense drooping
    leaf sprays along the upper two thirds and a crown at each tip."""
    centre = Vector((0, 0, H * 0.65))
    for c in range(culms):
        a = rng.uniform(0, TAU)
        rr = radius * math.sqrt(rng.random())
        base = Vector((math.cos(a) * rr, math.sin(a) * rr, -0.6))
        h = H * rng.uniform(0.7, 1.0)
        out = Vector((math.cos(a), math.sin(a), 0)) * (rr / radius + 0.3)
        lean = (Vector((0, 0, 1)) + out * 0.08 + Vector((rng.uniform(-0.04, 0.04), rng.uniform(-0.04, 0.04), 0))).normalized()
        pts = _curve(base, lean, h, segs, out * 0.22, None)
        r = rng.uniform(0.09, 0.13) * H / 18.0
        tb.limb(pts, [r * (1.0 - 0.45 * i / segs) for i in range(segs + 1)], sides)
        for k in range(rng.randint(9, 12)):
            t = 0.5 + 0.5 * k / 11 + rng.uniform(-0.03, 0.03)
            i = min(segs - 1, int(t * segs))
            p = pts[i].lerp(pts[i + 1], min(1.0, t * segs - i))
            az = a + rng.uniform(-1.8, 1.8)
            dirh = Vector((math.cos(az), math.sin(az), 0))
            sz = rng.uniform(*card) * (0.7 + 0.4 * t)
            cpos = p + dirh * sz * 0.38 - Vector((0, 0, sz * 0.15))
            n = (dirh * 0.9 + Vector((0, 0, 0.8)) + Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), 0))).normalized()
            tb.card(cpos, n, sz, rng.uniform(0, TAU), (rng.randint(0, 1), rng.randint(0, 1)),
                    bend_center=Vector((0, 0, p.z - 3.0)), bend=0.55, up_bias=0.25)
        tipd = (pts[-1] - pts[-2]).normalized()
        for k in range(3):
            hd = Vector((tipd.x, tipd.y, 0)).normalized() if Vector((tipd.x, tipd.y, 0)).length > 1e-3 else Vector((1, 0, 0))
            n = (hd + Vector((0, 0, 0.35)) + Vector((rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), 0))).normalized()
            tb.card(pts[-1] + tipd * 0.6 - Vector((0, 0, 0.6 * k)), n, rng.uniform(*card), rng.uniform(0, TAU),
                    (rng.randint(0, 1), rng.randint(0, 1)), bend_center=centre, bend=0.5, up_bias=0.2)
    return centre
