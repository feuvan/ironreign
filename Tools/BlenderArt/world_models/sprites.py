"""2D map sprites rendered from the exported World Models as gongbi jiehua (界画) paintings.

    Tools/BlenderArt/render.sh Tools/BlenderArt/world_models/sprites.py [City_1 City_2 City_3 Sect Banner Flag]

Each sprite re-imports its GLB from ArtSource/Models (the exact file Unreal gets, already painted in
the gongbi palette), removes the below-ground skirts and renders it as a painting, not a photo:

* colour = the baked gongbi albedo through an emission "wash" shader: a gentle plane separation
  (0.80 + 0.13 * key + 0.07 * up, key from the studio sun's screen direction), no cast shadows,
  no speculars, no AO - flat mineral washes;
* ruled ink (Freestyle): the sprite's outer contour ``OUTER_PX`` target px in warm ink #1E1A16,
  inner silhouettes / creases ``INNER_PX`` px in graded ink; leaf cards are excluded (face marks)
  and get a thin ink-green outline in post from the ``LeafMask`` AOV instead;
* post (numpy): premultiplied Lanczos 4x -> target, unsharp (0.6 px, 0.35), a soft lead-white wash
  halo round the sprite (gaussian 2 px of the alpha x 2, 65 %, fading out over the last 3 px)
  instead of a drop shadow (cities and sect; never on the tint plates), 1 px clear border.

    City_1/2/3 (96x96), Sect (64x64)   ground centre at (0.5, 0.70) of the canvas (the studio sprite
                                        rule), cities keep the UI pennant box x 56-83, y 0-23 clear
    Banner (64x96), Flag (32x48)        cloth = neutral white (TintMask AOV, post.neutralize +
                                        neutral_check), ink outlines, no halo; the pole base sits
                                        left of centre; Banner writes Art/Map/BannerGlyphArea.txt

Writes previews (x4 nearest, on silk / blue-green map grounds, UI sizes) to <scratch>/sprites/.
"""

import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402

from ironart import cameras, ink, lights, materials as M, post, recipes, scene, world_bake as WB  # noqa: E402
from ironart import world_gongbi_render as GR  # noqa: E402
from ironart import REPO_DIR  # noqa: E402

#: jiehua sprite recipe (registered at runtime; ironart/recipes.py is not modified): the studio
#: sprite camera / anchor, emission washes (no rig, no Kuwahara), ruled ink, wash halo.
JIEHUA = recipes.get("sprite")
JIEHUA.update(spp=16, rig=None, kuwahara=None, grade=None, unsharp=None, shadow=None, paper=0.0,
              margins=(3, 3, 4, 5),
              ink=dict(thickness_px=0.95, alpha=0.95, inner_scale=0.0, crease_angle=118.0,
                       calligraphy=0.0, pressure_noise=0.0, taper=False, smooth=False),
              notes="World Models 2D fallbacks as gongbi jiehua: emission washes of the baked gongbi albedo "
                    "(0.80 + 0.13 key + 0.07 up), ruled Freestyle ink 0.95 px outer / 0.43 px inner, leaf "
                    "outlines from a LeafMask AOV, lead-white wash halo, no shadow")
recipes.RECIPES["world_jiehua"] = JIEHUA
JIEHUA_TINT = recipes.get("tint_plate")
JIEHUA_TINT.update(spp=16, rig=None, kuwahara=None, grade=None, unsharp=None, shadow=None, paper=0.0,
                   ink=dict(thickness_px=0.9, alpha=0.95, inner_scale=0.0, crease_angle=118.0,
                            calligraphy=0.0, pressure_noise=0.0, taper=False, smooth=False),
                   notes="Banner / Flag jiehua tint plates: neutral white cloth (TintMask), ink outlines, no halo")
recipes.RECIPES["world_jiehua_tint"] = JIEHUA_TINT

SPRITES = {
    # name: (asset path, size, family, anchor (frac) or None = recipe)
    "City_1": ("Art/Map/City_1.png", (96, 96), "world_jiehua", None),
    "City_2": ("Art/Map/City_2.png", (96, 96), "world_jiehua", None),
    "City_3": ("Art/Map/City_3.png", (96, 96), "world_jiehua", None),
    "Sect": ("Art/Map/Sect.png", (64, 64), "world_jiehua", None),
    "Banner": ("Art/Map/Banner.png", (64, 96), "world_jiehua_tint", (0.24, 0.93)),
    "Flag": ("Art/Map/Flag.png", (32, 48), "world_jiehua_tint", (0.16, 0.89)),
}
#: per-sprite ink overrides: the 32x48 pennant's pole is ~1 px wide, a heavier contour keeps it an
#: ink stroke (the UI multiplies the whole Flag.png by the owner colour)
INK_OVERRIDE = {"Flag": dict(thickness_px=1.2)}
#: SIronMapView draws Flag.png over this box of the 96 px city canvas
PENNANT_KEEPOUT = (56, 0, 83, 23)
INK = "#1E1A16"
LEAF_INK = (0.11, 0.20, 0.16)
HALO = "#F4EEDF"
#: plane separation of the wash shader: base + key * max(0, N.L) + up * max(0, N.z)
SHADE = (0.86, 0.10, 0.06)
LEAF_AOV = "LeafMask"
#: inner ruled lines (depth / normal edges, drawn in post): graded ink, opacity
INNER_INK = "#2E2620"
INNER_ALPHA = 0.8


def largest_rect(mask):
    """Largest axis-aligned rectangle of True cells (x, y, w, h) - maximal rectangle by histogram."""
    H, W = mask.shape
    heights = np.zeros(W, np.int32)
    best = (0, 0, 0, 0, 0)
    for y in range(H):
        heights = np.where(mask[y], heights + 1, 0)
        stack = []
        for x in range(W + 1):
            hgt = heights[x] if x < W else 0
            start = x
            while stack and stack[-1][1] >= hgt:
                sx, sh = stack.pop()
                area = sh * (x - sx)
                if area > best[0]:
                    best = (area, sx, y - sh + 1, x - sx, sh)
                start = sx
            stack.append((start, hgt))
    return best[1:]


def cut_below_ground(obj, z=0.0):
    """Remove the below-ground skirts (they sit under the terrain in the game)."""
    scene.select_only(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.bisect(plane_co=(0, 0, z), plane_no=(0, 0, 1), clear_inner=True, clear_outer=False)
    bpy.ops.object.mode_set(mode="OBJECT")


def _base_image(mat):
    """(image or None, base colour factor) of an imported glTF material."""
    if not mat or not mat.use_nodes:
        return None, (0.8, 0.8, 0.8, 1.0)
    p = next((n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)
    if p is None:
        return None, (0.8, 0.8, 0.8, 1.0)
    s = p.inputs["Base Color"]
    if s.is_linked:
        n = s.links[0].from_node
        seen = 0
        while n.bl_idname != "ShaderNodeTexImage" and seen < 4:
            ins = [i for i in n.inputs if i.is_linked]
            if not ins:
                break
            n = ins[0].links[0].from_node
            seen += 1
        if n.bl_idname == "ShaderNodeTexImage":
            return n.image, tuple(s.default_value)
    return None, tuple(s.default_value)


def _aov(nb, name, value=1.0):
    a = nb.node("ShaderNodeOutputAOV")
    if hasattr(a, "aov_name"):
        a.aov_name = name
    else:
        a.name = name        # Blender 4.0: 'name' is the AOV name (shadows Node.name)
    a.inputs["Value"].default_value = value
    return a


def wash_material(src, key_dir, kind="paint"):
    """Emission wash for sprite renders: ``kind`` 'paint' (baked albedo), 'leaf' (alpha-tested,
    writes LeafMask) or 'cloth' (neutral white, writes TintMask)."""
    img, factor = _base_image(src)
    m = bpy.data.materials.new("Wash_%s" % (src.name if src else kind))
    m.use_nodes = True
    nb = M.NB(m.node_tree)
    for n in list(nb.nodes):
        if n.bl_idname != "ShaderNodeOutputMaterial":
            nb.nodes.remove(n)
    geo = nb.node("ShaderNodeNewGeometry")
    dot = nb.node("ShaderNodeVectorMath", operation="DOT_PRODUCT")
    nb.link(geo.outputs["Normal"], dot.inputs[0])
    dot.inputs[1].default_value = tuple(key_dir)
    key = nb.math("MAXIMUM", dot.outputs["Value"], 0.0)
    sep = nb.node("ShaderNodeSeparateXYZ")
    nb.link(geo.outputs["Normal"], sep.inputs[0])
    up = nb.math("MAXIMUM", sep.outputs["Z"], 0.0)
    shade = nb.math("ADD", nb.math("ADD", SHADE[0], nb.math("MULTIPLY", key, SHADE[1])), nb.math("MULTIPLY", up, SHADE[2]))
    grey = nb.node("ShaderNodeCombineColor")
    for k in ("Red", "Green", "Blue"):
        nb.link(shade, grey.inputs[k])
    em = nb.node("ShaderNodeEmission", inputs={"Strength": 1.0})
    alpha = None
    if kind == "cloth":
        # neutral white cloth: the shade only (R = G = B), a touch brighter than the paint
        c = nb.math("MINIMUM", nb.math("ADD", shade, 0.04), 1.0)
        g2 = nb.node("ShaderNodeCombineColor")
        for k in ("Red", "Green", "Blue"):
            nb.link(c, g2.inputs[k])
        nb.link(g2.outputs[0], em.inputs["Color"])
        _aov(nb, M.TINT_AOV, 1.0)
    else:
        if img is not None:
            t = nb.node("ShaderNodeTexImage", image=img, interpolation="Smart")
            col = t.outputs["Color"]
            alpha = t.outputs["Alpha"]
        else:
            col = factor
        nb.link(nb.mix(col, grey.outputs[0], 1.0, blend="MULTIPLY"), em.inputs["Color"])
        if kind == "leaf":
            _aov(nb, LEAF_AOV, 1.0)
    out = em.outputs[0]
    if kind == "leaf" and alpha is not None:
        tr = nb.node("ShaderNodeBsdfTransparent")
        mix = nb.node("ShaderNodeMixShader")
        nb.link(nb.math("GREATER_THAN", alpha, 0.5), mix.inputs[0])
        nb.link(tr.outputs[0], mix.inputs[1])
        nb.link(out, mix.inputs[2])
        out = mix.outputs[0]
    nb.output(out)
    return m


def paint_scene(obj, key_dir):
    """Swap every material of ``obj`` for its wash; mark leaf faces for Freestyle exclusion."""
    me = obj.data
    leaf_idx = set()
    for i, src in enumerate(list(me.materials)):
        nm = src.name if src else ""
        if nm.lower().startswith("tint"):
            me.materials[i] = wash_material(src, key_dir, "cloth")
        elif nm.startswith("Leaves"):
            me.materials[i] = wash_material(src, key_dir, "leaf")
            leaf_idx.add(i)
        else:
            me.materials[i] = wash_material(src, key_dir, "paint")
    marks = [p.material_index in leaf_idx for p in me.polygons]
    me.polygons.foreach_set("use_freestyle_mark", marks)
    me.update()


def ruled_ink(family, **over):
    r = dict(recipes.get(family)["ink"])
    r.update(over)
    inner_sil = bool(r.pop("inner_silhouette", True))
    sets = ink.enable(color=INK, border=False, crease=True, wobble=0.0, as_pass=False,
                      outer_select="external_contour", **r)
    if sets["inner"] is not None:
        # creases only: the ruled lines of walls, eaves, ridges and tiers - not the silhouette of
        # every round tile row, which turns a 96 px roof into a dark hatch
        sets["inner"].select_silhouette = inner_sil
    for ls in (sets["outer"], sets["inner"]):
        if ls is None:
            continue
        ls.select_by_face_marks = True
        ls.face_mark_negation = "EXCLUSIVE"
        ls.face_mark_condition = "ONE"
    if sets["inner"] is not None:
        sets["inner"].linestyle.color = (0.14, 0.11, 0.09)
    return sets


def compositor(raw_dir, name, tint):
    sc = bpy.context.scene
    sc.use_nodes = True
    nt = sc.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    rl = nt.nodes.new("CompositorNodeRLayers")
    comp = nt.nodes.new("CompositorNodeComposite")
    nt.links.new(rl.outputs["Image"], comp.inputs["Image"])
    nt.links.new(rl.outputs["Alpha"], comp.inputs["Alpha"])
    socks = {"leaf_%s" % name: rl.outputs[LEAF_AOV]}
    if tint:
        socks["tint_%s" % name] = rl.outputs[M.TINT_AOV]
    post.comp_outputs(raw_dir, socks)
    # float depth + normal for the inner ruled lines (drawn in post, like Unreal's ink pass)
    fo = nt.nodes.new("CompositorNodeOutputFile")
    fo.base_path = raw_dir
    fo.format.file_format = "OPEN_EXR"
    fo.format.color_depth = "32"
    fo.format.color_mode = "RGBA"
    fo.file_slots.clear()
    for slot, sock in (("depth_%s" % name, rl.outputs["Depth"]), ("normal_%s" % name, rl.outputs["Normal"])):
        fo.file_slots.new(slot)
        nt.links.new(sock, fo.inputs[slot])
    return rl


def inner_lines(depth, normal, alpha, leaf, px_m, view_dir=None):
    """Inner ruled contours + sharp creases from the depth / normal buffers (render scale), the
    same rule as the 3D review renders (world_gongbi_render.edge_lines)."""
    valid = alpha > 0.5
    solid = valid & (leaf < 0.5)
    contour, crease = GR.edge_lines(depth, normal, solid, valid, px_m, thr_px=2.5, thr_min=0.3, view_dir=view_dir)
    return contour | crease


def _blur(a, s):
    return post.gaussian(a, s)


def leaf_outline(img, leaf, ss):
    """Thin ink-green outline round the leaf masses (at render scale, ~0.5 target px)."""
    a = img[..., 3]
    solid = a > 0.5
    lm = (leaf > 0.5) & solid
    r = max(1, int(round(0.5 * ss)))
    edge = np.zeros_like(lm)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy > r * r or (dx == 0 and dy == 0):
                continue
            sh = np.zeros_like(solid)
            ys0, ys1 = max(0, dy), solid.shape[0] + min(0, dy)
            xs0, xs1 = max(0, dx), solid.shape[1] + min(0, dx)
            sh[ys0:ys1, xs0:xs1] = solid[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
            edge |= lm & ~sh
    e = _blur(edge.astype(np.float32), 0.6) * 1.6
    e = np.clip(e, 0, 1)[..., None] * 0.8
    out = img.copy()
    out[..., :3] = out[..., :3] * (1 - e) + np.array(LEAF_INK, np.float32) * e
    return out


def halo(img, sigma=2.0, gain=2.0, strength=0.65, keepout=None):
    """Soft lead-white wash round the painting (bare-silk mist instead of a drop shadow)."""
    a = img[..., 3]
    hz = np.clip(_blur(a, sigma) * gain, 0, 1) * strength
    if keepout is not None:
        x0, y0, x1, y1 = keepout
        k = np.zeros_like(hz)
        k[y0:y1, x0:x1] = 1.0
        k = np.clip(_blur(k, 1.0) * 1.5, 0, 1)
        hz = hz * (1 - k)
    H, W = a.shape
    yy, xx = np.mgrid[0:H, 0:W]
    edge = np.minimum(np.minimum(xx, W - 1 - xx), np.minimum(yy, H - 1 - yy)).astype(np.float32)
    hz *= np.clip(edge / 3.0, 0.0, 1.0)            # fades out over the last 3 px (1 px ring clear)
    hc = np.array([int(HALO[k:k + 2], 16) / 255.0 for k in (1, 3, 5)], np.float32)
    base = np.dstack([np.broadcast_to(hc, a.shape + (3,)), hz])
    return post.over(img, base)


def render_sprite(name, out_dir, ss=None, spp=None):
    rel, (W, H), family, anchor = SPRITES[name]
    times = {}
    t0 = time.time()
    objs = WB.reimport(os.path.join(common.MODELS_DIR, name + ".glb"))
    obj = objs[0]
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.render.use_freestyle = False
    for vl in sc.view_layers:
        while len(vl.freestyle_settings.linesets) > 0:
            vl.freestyle_settings.linesets.remove(vl.freestyle_settings.linesets[0])
    scene.seed_all(31)
    sc["ironart_seed"] = 31
    cut_below_ground(obj)
    tint = family == "world_jiehua_tint"
    vl = bpy.context.view_layer
    M.enable_tint_aov(vl)
    if LEAF_AOV not in [a.name for a in vl.aovs]:
        a = vl.aovs.add()
        a.name = LEAF_AOV
        a.type = "VALUE"
    r = recipes.setup(family, W, H, ss=ss, spp=spp)
    vl.use_pass_z = True
    vl.use_pass_normal = True
    sc.cycles.use_adaptive_sampling = False
    sc.cycles.max_bounces = 0
    sc.cycles.transparent_max_bounces = 24
    w = bpy.data.worlds.new("NoLight")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
    cam = recipes.camera(family)
    if anchor:
        cameras.fit_ortho(cam, [obj], margin_px=recipes.get(family)["margins"], anchor_world=(0.0, 0.0, 0.0),
                          anchor_px=(W * anchor[0], H * anchor[1]))
    else:
        recipes.frame(family, cam, [obj])
    key = lights.screen_dir(cam, 135.0, 50.0)
    paint_scene(obj, key)
    ruled_ink(family, **INK_OVERRIDE.get(name, {}))
    raw_dir = common.out("sprites", "raw")
    compositor(raw_dir, name, tint)
    raw = os.path.join(raw_dir, "%s_raw_%dx.png" % (name, r["ss"]))
    times["setup"] = time.time() - t0
    times["render"] = scene.render(raw)
    img = post.load(raw)
    leaf = post.load(post.pass_path(raw_dir, "leaf_%s" % name))[..., 0]
    depth = GR.exr_pixels(os.path.join(raw_dir, "depth_%s0001.exr" % name))[..., 0]
    normal = GR.exr_pixels(os.path.join(raw_dir, "normal_%s0001.exr" % name))
    px_m = cam.data.ortho_scale / float(max(sc.render.resolution_x, sc.render.resolution_y))
    fwd = cam.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))
    e = inner_lines(depth, normal, img[..., 3], leaf, px_m, tuple(fwd)).astype(np.float32)
    e = np.clip(_blur(e, 0.55) * 1.7, 0, 1)[..., None] * INNER_ALPHA
    ic = np.array([int(INNER_INK[k:k + 2], 16) / 255.0 for k in (1, 3, 5)], np.float32)
    img[..., :3] = img[..., :3] * (1 - e) + ic * e
    img = leaf_outline(img, leaf, r["ss"])
    mask = None
    if tint:
        mask = post.load(post.pass_path(raw_dir, "tint_%s" % name))[..., 0]
    img = post.downsample(img, r["ss"])
    img = post.alpha_cleanup(img, lo=0.02, hi=0.98, bleed=3)
    img = post.unsharp(img, 0.6, 0.35)
    img = np.clip(img, 0, 1)
    if not tint:
        img = halo(img, keepout=PENNANT_KEEPOUT if name.startswith("City_") else None)
    img = np.clip(img, 0, 1)
    qa = post.QA(name)
    extra = {}
    if tint:
        m8 = post.resize(np.dstack([mask] * 3 + [np.ones_like(mask)]), (W, H))[..., 0]
        img = post.neutralize(img, (m8 > 0.5).astype(np.float32))
        # the whole plate is multiplied by the faction colour at runtime: light, low-saturation
        # paint outside the cloth (stone foot, anti-aliased gold piping) is laid neutral too, so
        # check_art.py's mask-free heuristic (bright + unsaturated => cloth) holds as well
        rgb = img[..., :3]
        mx = rgb.max(-1)
        sat = (mx - rgb.min(-1)) / np.maximum(mx, 1e-6)
        light = (img[..., 3] > 0.5) & (mx > 0.4) & (sat < 0.34)
        img = post.neutralize(img, light.astype(np.float32))
        mean, p99 = post.neutral_check(img, m8)
        qa.max("plate neutral p99 (check_art heuristic)", post.neutral_check(img)[1], 4.0)
        qa.max("tint neutral mean", mean, 1.0)
        qa.max("tint neutral p99", p99, 4.0)
        extra["neutral"] = (round(mean, 2), round(p99, 2))
        if name == "Banner":
            cm = m8 > 0.6
            er = cm & np.roll(cm, 1, 0) & np.roll(cm, -1, 0) & np.roll(cm, 1, 1) & np.roll(cm, -1, 1)
            x, y, w_, h_ = largest_rect(er)
            corners = json.load(open(os.path.join(common.out(), "banner_glyph_world.json")))
            extra["glyph_field_projected"] = cameras.target_rect(cam, corners)
            with open(os.path.join(REPO_DIR, "Content", "Data", "Art", "Map", "BannerGlyphArea.txt"), "w") as f:
                f.write("%d %d %d %d\n" % (x, y, w_, h_))
            cov = float((m8[y:y + h_, x:x + w_] > 0.5).mean())
            qa.range("glyph area on white cloth", cov, 0.98, 1.0)
            qa.range("glyph area size (px^2)", w_ * h_, 300, 64 * 96)
            extra["glyph_area"] = (x, y, w_, h_)
            extra["glyph_cloth_coverage"] = round(cov, 3)
    img[0, :, 3] = img[-1, :, 3] = 0.0
    img[:, 0, 3] = img[:, -1, 3] = 0.0
    qa.max("border alpha (1 px ring)", post.border_alpha_max(img), 0.0)
    if name.startswith("City_"):
        x0, y0, x1, y1 = PENNANT_KEEPOUT
        qa.max("pennant keep-out alpha", float(img[y0:y1, x0:x1, 3].max()), 0.1)
    qa.check()
    path = post.save_asset(img, rel)
    times["total"] = time.time() - t0
    preview_sheet(name, img)
    kb = os.path.getsize(path) / 1024.0
    print("[ironart] sprite %s -> %s (%dx%d, %.1f KB) render %.1fs total %.1fs %s" % (
        name, rel, W, H, kb, times["render"], times["total"], extra))
    return {"path": path, "size": (W, H), "kb": round(kb, 1), "times": {k: round(v, 1) for k, v in times.items()},
            **extra}


# ---------------------------------------------------------------------------------------------
# previews: the sprite on the painted map grounds
# ---------------------------------------------------------------------------------------------
def silk_ground(w, h, seed=3, green=0.0):
    """Aged silk (#E6D6B0 .. #D8C39A, warp / weft fibres, mottling) with an optional malachite wash
    (the blue-green map plains)."""
    rng = np.random.default_rng(seed)
    a = np.array([0xE6, 0xD6, 0xB0], np.float32) / 255.0
    b = np.array([0xD8, 0xC3, 0x9A], np.float32) / 255.0
    mott = post.fbm(h, w, max(8.0, w / 4.0), 4, 0.5, seed)
    col = a * (1 - mott[..., None]) + b * mott[..., None]
    if green > 0:
        g = np.array([0x8C, 0xBF, 0xA0], np.float32) / 255.0
        gm = (0.75 + 0.25 * post.fbm(h, w, max(8.0, w / 3.0), 3, 0.5, seed + 1))[..., None] * green
        col = col * (1 - gm) + col * g * gm * 1.15
    fib = 1.0 + 0.025 * (rng.random((h, 1)) - 0.5) + 0.025 * (rng.random((1, w)) - 0.5)
    col = np.clip(col * fib[..., None], 0, 1)
    return np.dstack([col, np.ones((h, w), np.float32)]).astype(np.float32)


def map_crop(w, h):
    """The current painted world map (Content/Data/Art/Map/WorldMap.png) around a plain, if any."""
    p = os.path.join(REPO_DIR, "Content", "Data", "Art", "Map", "WorldMap.png")
    if not os.path.isfile(p):
        return None
    from PIL import Image
    im = Image.open(p).convert("RGBA")
    cx, cy = int(im.width * 0.44), int(im.height * 0.45)
    c = im.crop((cx - w // 2, cy - h // 2, cx - w // 2 + w, cy - h // 2 + h))
    return np.asarray(c, np.float32) / 255.0


def preview_sheet(name, img):
    H, W = img.shape[:2]
    items = [(img, "%dx%d" % (W, H)), (post.resize(img, (W * 4, H * 4), "nearest"), "x4"),
             (post.over(img, silk_ground(W, H)), "on silk"),
             (post.over(img, silk_ground(W, H, green=0.55)), "on blue-green")]
    mc = map_crop(W, H)
    if mc is not None:
        items.append((post.over(img, mc), "on WorldMap.png"))
    if name.startswith("City_"):
        for s in (46, 58, 74):
            items.append((post.over(post.resize(img, (s, s)), silk_ground(s, s, green=0.55)), "%d px (UI)" % s))
    sheet = post.contact_sheet(items, cols=len(items))
    post.save(sheet, os.path.join(common.out("sprites"), "%s_sheet.png" % name))


def context_sheet(out_path, on_map=True):
    """All six sprites at UI sizes, placed as SIronMapView places them, on the current
    WorldMap.png (``on_map``) or on a blue-green silk patch (the gongbi map ground)."""
    from PIL import Image
    base = Image.new("RGBA", (520, 300))
    g = silk_ground(520, 300, seed=11, green=0.5)
    mc = map_crop(520, 300) if on_map else None
    bg = Image.fromarray((np.clip(g if mc is None else mc, 0, 1) * 255).astype(np.uint8), "RGBA")
    base.alpha_composite(bg)
    p = lambda n: Image.open(os.path.join(REPO_DIR, "Content", "Data", "Art", "Map", n + ".png")).convert("RGBA")
    placed = []
    for n, (x, y), s in (("City_1", (70, 120), 46), ("City_2", (210, 130), 58), ("City_3", (380, 140), 74)):
        if os.path.isfile(os.path.join(REPO_DIR, "Content", "Data", "Art", "Map", n + ".png")):
            im = p(n).resize((s, s), Image.LANCZOS)
            base.alpha_composite(im, (x - s // 2, y - s))
            placed.append((n, x, y, s))
    for n, x, y, s in placed:
        fh = int(s * 0.42)
        fw = int(fh * 32 / 48)
        fl = p("Flag").resize((fw, fh), Image.LANCZOS)
        tint = (0xB3, 0x28, 0x2D) if n != "City_2" else (0x2F, 0x6D, 0xB5)
        arr = np.asarray(fl, np.float32)
        arr[..., :3] *= np.array(tint, np.float32) / 255.0
        base.alpha_composite(Image.fromarray(arr.astype(np.uint8), "RGBA"), (int(x + s * 0.08), int(y - s - fh * 0.45)))
    sect = p("Sect").resize((28, 28), Image.LANCZOS)
    base.alpha_composite(sect, (210 - 29 - 16, 130 - 30))
    ban = p("Banner").resize((33, 50), Image.LANCZOS)
    arr = np.asarray(ban, np.float32)
    arr[..., :3] *= np.array((0xB3, 0x28, 0x2D), np.float32) / 255.0
    base.alpha_composite(Image.fromarray(arr.astype(np.uint8), "RGBA"), (300, 200))
    big = base.resize((1040, 600), Image.NEAREST)
    out = Image.new("RGBA", (1040, 900))
    out.alpha_composite(big, (0, 0))
    out.alpha_composite(base, (260, 600))
    out.convert("RGB").save(out_path)
    return out_path


def main():
    fl = common.flags()
    names = [n for n in fl["names"] if n in SPRITES] or list(SPRITES)
    rep = common.Report()
    for n in names:
        rep.add(n + ".png", **render_sprite(n, common.out("sprites")))
    rep.save()
    if all(os.path.isfile(os.path.join(REPO_DIR, "Content", "Data", "Art", "Map", n + ".png")) for n in SPRITES):
        print("[ironart] context sheets", context_sheet(os.path.join(common.out("sprites"), "Sprites_in_context.png")),
              context_sheet(os.path.join(common.out("sprites"), "Sprites_on_silk.png"), on_map=False))


if __name__ == "__main__":
    main()
