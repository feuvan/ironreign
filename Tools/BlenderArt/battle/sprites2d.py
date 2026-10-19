"""2D fallbacks of the battle board, painted from the 3D models (DESIGN.md section 8 manifest):

    Art/Battle/Hex_<Terrain>.png   128x111  the hex model seen from straight above in the
                                            planimetric-oblique convention of Chinese map
                                            painting (ground plan exact, heights drawn leaning
                                            north: y' = y + 0.45 z), with its six neighbours of
                                            the same terrain so trees / walls continue across the
                                            edges; ink from the depth / normal buffers, soft
                                            shadowless light, a touch of silk; transparent outside
                                            the hexagon
    Art/Battle/Hex_Fill.png         white hexagon (tinted highlights)
    Art/Battle/Hex_Outline.png      white hexagon outline, 3 px
    Art/Battle/Unit_<Type>.png      96x96   the front of the squad model in 3/4 view (the two
                                            front ranks and the standard), fine ink outlines, flat
                                            colour; Tint areas pure neutral white
    Art/Battle/Unit_Base.png        96x96   the plinth disc in the same 3/4 view, neutral white

    Tools/BlenderArt/render.sh Tools/BlenderArt/battle/sprites2d.py [hex units base masks] [names...] [--preview]
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from ironart import cameras, lights, palette, post, scene  # noqa: E402
from ironart import world_gongbi_render as GR  # noqa: E402

ROW = 6.928203230275509
SHEAR = 0.45
NEIGH = {"N": (0.0, ROW), "S": (0.0, -ROW), "NE": (6.0, ROW / 2), "SE": (6.0, -ROW / 2),
         "NW": (-6.0, ROW / 2), "SW": (-6.0, -ROW / 2)}
NEIGHBOURS = {  # terrain -> neighbour terrains (N/S first, then the diagonals)
    "Ford": ("Water", "Plain"), "Bridge": ("Water", "Plain"), "Water": ("Water", "Water"),
    "Wall": ("Wall", "Plain"), "Gate": ("Wall", "Plain"), "Rubble": ("Wall", "Plain"),
    "Castle": ("Town", "Town"), "Town": ("Town", "Town"), "Road": ("Plain", "Road"),
}
TINT_AOV = "TintMask"


def load_glb(name):
    path = os.path.join(common.MODELS_DIR, name + ".glb")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    for o in new:
        if o.type != "MESH":
            bpy.data.objects.remove(o)
    return meshes[0]


def _aov(mat, name, value):
    nt = mat.node_tree
    a = nt.nodes.new("ShaderNodeOutputAOV")
    if hasattr(a, "aov_name"):
        a.aov_name = name
    else:
        a.name = name
    a.inputs["Value"].default_value = value


def gongbi_render(objs, cam, path, res, ss, samples=16, ink_px=1.0, crease_alpha=0.55, transparent=False,
                  sun_angle=135.0, sun_elev=50.0, sky=0.8, key=1.05, tint=False, thr_min=0.05):
    """Render ``objs`` with ``cam`` at ``res`` x ``ss`` in the gongbi review look; returns
    (rgba float image at res x ss, tint mask or None).  Ink widths are in target pixels."""
    sc = bpy.context.scene
    scene.setup_cycles(samples=samples, transparent=transparent, preset="sprite", view="Standard", look="None",
                       clamp_indirect=4.0)
    sc.cycles.max_bounces = 3
    sc.cycles.diffuse_bounces = 2
    sc.cycles.glossy_bounces = 0
    sc.render.resolution_x, sc.render.resolution_y = res[0] * ss, res[1] * ss
    sc.render.resolution_percentage = 100
    sc.render.use_freestyle = False
    sc.render.filter_size = 1.5
    GR.matte(objs)
    sc.camera = cam
    w = bpy.data.worlds.new("SoftSky")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = sky
    d = lights.screen_dir(cam, sun_angle, sun_elev)
    lights.sun("SoftKey", d, key, (1.0, 1.0, 1.0), 8.0, shadow=False)
    vl = bpy.context.view_layer
    vl.use_pass_z = True
    vl.use_pass_normal = True
    if tint:
        if TINT_AOV not in [a.name for a in vl.aovs]:
            a = vl.aovs.add()
            a.name = TINT_AOV
            a.type = "VALUE"
        done = set()
        for o in objs:
            for m in o.data.materials:
                if m and m.name not in done and m.use_nodes:
                    _aov(m, TINT_AOV, 1.0 if m.name.lower().startswith("tint") else 0.0)
                    done.add(m.name)
    sc.use_nodes = True
    ct = sc.node_tree
    for n in list(ct.nodes):
        ct.nodes.remove(n)
    rl = ct.nodes.new("CompositorNodeRLayers")
    comp = ct.nodes.new("CompositorNodeComposite")
    ct.links.new(rl.outputs["Image"], comp.inputs["Image"])
    tmp = os.path.join(os.path.dirname(os.path.abspath(path)), "_passes_" + os.path.basename(path)[:-4])
    fo = ct.nodes.new("CompositorNodeOutputFile")
    fo.base_path = tmp
    fo.format.file_format = "OPEN_EXR"
    fo.format.color_depth = "32"
    fo.format.color_mode = "RGBA"
    fo.file_slots.clear()
    socks = [("depth", rl.outputs["Depth"]), ("normal", rl.outputs["Normal"])]
    if tint:
        socks.append(("tint", rl.outputs[TINT_AOV]))
    for slot, sock in socks:
        fo.file_slots.new(slot)
        ct.links.new(sock, fo.inputs[slot])
    secs = scene.render(path)
    depth = GR.exr_pixels(os.path.join(tmp, "depth0001.exr"))[..., 0]
    normal = GR.exr_pixels(os.path.join(tmp, "normal0001.exr"))
    tm = GR.exr_pixels(os.path.join(tmp, "tint0001.exr"))[..., 0] if tint else None
    try:
        os.rmdir(tmp)
    except OSError:
        pass
    img = post.load(path)
    H, W = depth.shape
    if cam.data.type == "ORTHO":
        px_m = np.full(depth.shape, cam.data.ortho_scale / float(max(W, H)), np.float32)
    else:
        px_m = depth * 2.0 * math.tan(cam.data.angle / 2.0) / float(max(W, H))
    valid = depth < 1e5
    fwd = cam.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))
    contour, crease = GR.edge_lines(depth, normal, valid, valid, px_m, thr_px=2.0, thr_min=thr_min, view_dir=tuple(fwd))
    # outer silhouette (against the empty background) for sprites
    if transparent:
        sil = valid & ~(GR._sh(valid, 0, 1, False) & GR._sh(valid, 1, 0, False) & GR._sh(valid, 0, -1, False) &
                        GR._sh(valid, -1, 0, False))
        contour = contour | sil
    rgb = post.srgb_to_linear(img[..., :3])
    rgb = GR.ink_over(rgb, crease, palette.lin("#3A2E26"), crease_alpha, ink_px * ss * 0.9)
    rgb = GR.ink_over(rgb, contour, palette.lin("#1E1A16"), 0.95, ink_px * ss * 1.25)
    rgb = post.linear_to_srgb(np.clip(rgb, 0, 1))
    a = img[..., 3] if transparent else np.ones((H, W), np.float32)
    if transparent:
        # ink lines on the silhouette must be opaque where they fall on the figure's edge
        e = np.clip(post.gaussian(contour.astype(np.float32), 0.45 * ink_px * ss * 1.25) * 2.0, 0, 1)
        a = np.maximum(a, e * (post.gaussian(valid.astype(np.float32), ink_px * ss) > 0.05))
    out = np.dstack([rgb, a]).astype(np.float32)
    print("[battle] gongbi render %s %dx%d in %.1fs" % (os.path.basename(path), W, H, secs))
    return out, tm


def silk_tone(img, strength=0.1, seed=0):
    """A touch of aged silk on a painted 2D tile: warm tint, slightly less chroma, faint weave."""
    rgb = img[..., :3]
    lum = (rgb * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1, keepdims=True)
    rgb = lum + (rgb - lum) * 0.92
    silk = np.array([0.902, 0.839, 0.69], np.float32)
    rgb = rgb * (1 - strength + strength * silk / silk.max())
    h, w = rgb.shape[:2]
    weave = post.paper_texture(w, h, seed=seed, fibre=1.0, grain=0.6, scale=1.0)
    if weave.ndim == 3:
        weave = weave[..., 0]
    rgb = rgb * (1.0 + 0.035 * (weave[..., None] - weave.mean()))
    out = img.copy()
    out[..., :3] = np.clip(rgb, 0, 1)
    return out


# ---------------------------------------------------------------------------------------------
# hex tiles
# ---------------------------------------------------------------------------------------------
def shear_matrix(k=SHEAR):
    m = Matrix.Identity(4)
    m[1][2] = k
    return m


def hex_tile(name, preview=False):
    scene.reset(7)
    ns, diag = NEIGHBOURS.get(name, (name, name))
    protos = {}

    def proto(t):
        if t not in protos:
            o = load_glb("Hex_" + t)
            o.hide_render = True
            # the planimetric-oblique projection: shear the mesh itself (an object matrix cannot
            # hold a shear - Blender would decompose it into a rotation)
            o.data = o.data.copy()
            o.data.transform(shear_matrix())
            o.data.update()
            protos[t] = o
        return protos[t]

    placed = []
    centre = proto(name)
    for key, (dx, dy) in [("C", (0.0, 0.0))] + list(NEIGH.items()):
        t = name if key == "C" else (ns if key in ("N", "S") else diag)
        p = proto(t)
        o = p.copy()
        o.hide_render = False
        bpy.context.scene.collection.objects.link(o)
        o.matrix_world = Matrix.Translation(Vector((dx, dy, 0.0)))
        placed.append(o)
    ss = 4 if preview else 8
    W, H = 128, 111
    cam = cameras.ortho_top_down(center=(0.0, 0.0), width=8.0, height=8.0 * H / W, z=60.0)
    cam.data.ortho_scale = 8.0
    cam.data.clip_end = 200.0
    raw = os.path.join(common.out("sprites2d", "raw"), "Hex_%s_raw.png" % name)
    img, _ = gongbi_render(placed, cam, raw, (W, H), ss, samples=12 if preview else 24, ink_px=0.75,
                           crease_alpha=0.5, thr_min=0.04)
    img = silk_tone(img, 0.08, seed=3)
    img = post.downsample(img, ss)
    img[..., 3] = post.hex_mask(W, H)
    img[..., :3] = np.clip(img[..., :3], 0, 1)
    return img


def masks():
    W, H = 128, 111
    m = post.hex_mask(W, H)
    fill = np.dstack([np.ones((H, W, 3), np.float32), m])
    o = np.clip(m - post.hex_mask(W, H, inset=3.0), 0, 1)
    outline = np.dstack([np.ones((H, W, 3), np.float32), o])
    return fill, outline


# ---------------------------------------------------------------------------------------------
# units and base
# ---------------------------------------------------------------------------------------------
UNIT_CAM = dict(elevation_deg=38.0, azimuth_deg=-24.0)
#: the part of each squad the icon shows: keep vertices with y below this (the front ranks and
#: the standard), so the figures read at 96 px
ICON_KEEP = {"Infantry": (-2.0, 1.8), "Cavalry": (-3.0, 1.6), "Archer": (-2.0, 1.9)}


def unit_icon(name, preview=False):
    """The icon group of the squad (same figure builders and gongbi materials as the GLB,
    rendered directly), 3/4 view, fitted to 96 x 96."""
    import random
    from ironart import battle_figures as BF
    from ironart import battle_unit_mats as UM
    from ironart import world_bake as WB
    from ironart.geometry import MeshBuilder
    scene.reset(11)
    WB.tint_material("Tint")
    rng = random.Random({"Infantry": 51, "Cavalry": 52, "Archer": 53}[name])
    mb = MeshBuilder()
    BF.STANDARD_LEN[0] = 2.55
    try:
        {"Infantry": BF.icon_infantry, "Cavalry": BF.icon_cavalry, "Archer": BF.icon_archers}[name](mb, rng)
    finally:
        BF.STANDARD_LEN[0] = 3.5
    lib = UM.library(260.0)
    o = mb.build("Icon_" + name, lib)
    ss = 4 if preview else 8
    scene.set_resolution(96, 96, ss)
    cam = cameras.sprite_camera(**UNIT_CAM)
    cameras.fit_ortho(cam, [o], margin_px=(3, 3, 3, 4), anchor="center")
    raw = os.path.join(common.out("sprites2d", "raw"), "Unit_%s_raw.png" % name)
    img, tm = gongbi_render([o], cam, raw, (96, 96), ss, samples=16 if preview else 32, ink_px=0.75,
                            crease_alpha=0.45, transparent=True, tint=True, thr_min=0.02)
    img = post.downsample(img, ss)
    tm = post.downsample(np.dstack([tm, tm, tm, np.ones_like(tm)]), ss)[..., 0]
    return finish_sprite(img, tm)


def finish_sprite(img, tm):
    """Alpha clean-up, neutral tint areas (R = G = B), clear 1 px border."""
    img = post.alpha_cleanup(img)
    img = post.neutralize(img, np.clip(tm * 1.3, 0, 1))
    # any other bright, unsaturated pixel is a white the runtime may tint: make it neutral too
    rgb = img[..., :3]
    mx = rgb.max(-1)
    sat = (mx - rgb.min(-1)) / np.maximum(mx, 1e-6)
    heur = ((img[..., 3] > 0.9) & (mx > 0.45) & (sat < 0.3)).astype(np.float32)
    img = post.neutralize(img, heur)
    img[0, :, 3] = img[-1, :, 3] = 0
    img[:, 0, 3] = img[:, -1, 3] = 0
    return img


def base_icon(preview=False):
    scene.reset(12)
    o = load_glb("Unit_Base")
    ss = 4 if preview else 8
    scene.set_resolution(96, 96, ss)
    cam = cameras.sprite_camera(**UNIT_CAM)
    cameras.fit_ortho(cam, [o], margin_px=(4, 4, 4, 4), anchor="center")
    raw = os.path.join(common.out("sprites2d", "raw"), "Unit_Base_raw.png")
    img, tm = gongbi_render([o], cam, raw, (96, 96), ss, samples=16, ink_px=0.6, crease_alpha=0.3, transparent=True,
                            tint=True, sky=1.0, key=0.6)
    img = post.downsample(img, ss)
    tm = post.downsample(np.dstack([tm, tm, tm, np.ones_like(tm)]), ss)[..., 0]
    # the plinth is a tint plate: everything neutral (the dark lacquer band stays dark)
    img = post.alpha_cleanup(img)
    img = post.neutralize(img, np.ones(img.shape[:2], np.float32))
    img[0, :, 3] = img[-1, :, 3] = 0
    img[:, 0, 3] = img[:, -1, 3] = 0
    return img


def save(img, rel):
    p = post.save_asset(img, rel)
    print("[battle] wrote %s" % os.path.relpath(p, common.REPO_DIR))
    return p


def main():
    fl = common.flags()
    want = set(fl["names"])
    steps = {"hex", "units", "base", "masks"} & want or {"hex", "units", "base", "masks"}
    names = [n for n in fl["names"] if n in common.TERRAINS] or list(common.TERRAINS)
    units = [n for n in fl["names"] if n in common.UNITS] or list(common.UNITS)
    if "masks" in steps:
        fill, outline = masks()
        save(fill, "Art/Battle/Hex_Fill.png")
        save(outline, "Art/Battle/Hex_Outline.png")
    if "hex" in steps:
        for n in names:
            save(hex_tile(n, fl["preview"]), "Art/Battle/Hex_%s.png" % n)
    if "units" in steps:
        for u in units:
            save(unit_icon(u, fl["preview"]), "Art/Battle/Unit_%s.png" % u)
    if "base" in steps:
        save(base_icon(fl["preview"]), "Art/Battle/Unit_Base.png")


if __name__ == "__main__":
    main()
