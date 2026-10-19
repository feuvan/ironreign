"""World Terrain family: regenerate every output deterministically.

    Tools/BlenderArt/render.sh Tools/BlenderArt/world_terrain/build.py [options]

Outputs (DESIGN.md 12.2 / section 8):
    Content/Data/Art3D/Terrain/Terrain.json   terrain contract
    Content/Data/Art3D/Terrain/Height.png      1201 x 751, 16-bit grey (pixel (i, j) = map (2i, 2j))
    Content/Data/Art3D/Terrain/Trees.json      tree instances
    ArtSource/Terrain/Albedo.png               4800 x 3000 sRGB ground pigment (gongbi blue-green,
                                               no lighting)
    ArtSource/Terrain/Masks.png                4800 x 3000 RGBA: R water, G forest, B rock/snow, A road
    ArtSource/Textures/Water_Normal.png        1024 x 1024 tileable normal map (OpenGL)
    ArtSource/Textures/Water_Foam.png          1024 x 1024 tileable foam mask
    Content/Data/Art/Map/WorldMap.png          2400 x 1500 gongbi painted map on silk (2D fallback)
    ArtSource/manifest.json                    entries added, version bumped
Scratch (previews, caches, passes, contact sheet): $IRONART_OUT/world_terrain/

Modules (Tools/BlenderArt/ironart/):
    world_terrain_fields    the world: coast, plains, lakes, rivers, city pads, roads, forests
    world_terrain_relief    mountain ranges and hill chains as ridge networks (crest, spurs, gullies)
    world_terrain_paint     Albedo.png / Masks.png painter
    world_terrain_trees     Trees.json scatter
    world_terrain_water     Water_Normal.png / Water_Foam.png
    world_terrain_mapglyphs the 2D map's pictorial peaks, hills and trees (layout, forms, Blender)
    world_terrain_mappaint  the 2D map's numpy painting on silk
    world_terrain_glyphs    oblique projection + Blender helpers shared by the two above
    world_terrain_render    the scratch 3/4 previews
The 2D map's glyph layer renders in tiles, each in its own Blender process (glyph_tile.py), so
Freestyle's memory is returned after every tile.

Options
    --stages a,b,...   subset of: fields paint trees water worldmap preview qa manifest
                       (default: all, in that order)
    --reuse            load the world cache from scratch when present (iteration only; a clean run
                       rebuilds everything and produces identical files)
    --crop x0,y0,x1,y1 worldmap stage: paint only this map rectangle (metres) to scratch
    --spp N            override the glyph / preview samples (iteration)
    --views N          preview stage: number of 3/4 views (default all)
"""

import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from ironart import REPO_DIR  # noqa: E402
from ironart import world_terrain_fields as F  # noqa: E402

STAGES = ["fields", "paint", "trees", "water", "worldmap", "preview", "qa", "manifest"]
ART3D = os.path.join(REPO_DIR, "Content", "Data", "Art3D", "Terrain")
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ARTSRC = os.path.join(REPO_DIR, "ArtSource")
WORLDMAP = os.path.join(REPO_DIR, "Content", "Data", "Art", "Map", "WorldMap.png")
MANIFEST_FILES = ["Terrain/Albedo.png", "Terrain/Masks.png", "Textures/Water_Normal.png",
                  "Textures/Water_Foam.png"]

#: worldmap render: glyph layer samples (flat emission + AOVs: anti-aliasing only)
GLYPH_SPP = 12
#: worldmap glyph render tiles (map metres) and the margin each tile renders around itself
TILE_M = (620.0, 520.0)
TILE_MARGIN = 60.0
#: the 3/4 previews: (map x, map y, camera distance m, pitch deg) like the Unreal strategy camera
PREVIEW_VIEWS = [(1240, 760, 1700.0, 55.0), (700, 430, 1050.0, 55.0), (1250, 1250, 1000.0, 55.0),
                 (1750, 900, 900.0, 55.0), (1200, 820, 2800.0, 62.0)]


def scratch(*p):
    base = os.path.join(os.environ.get("IRONART_OUT") or "/tmp/ironart", "world_terrain")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, *p)


def parse_args(argv):
    a = {"stages": list(STAGES), "reuse": False, "crop": None, "spp": None, "views": None}
    i = 0
    while i < len(argv):
        k = argv[i]
        if k == "--stages":
            a["stages"] = [s.strip() for s in argv[i + 1].split(",") if s.strip()]
            bad = [s for s in a["stages"] if s not in STAGES]
            if bad:
                raise SystemExit("unknown stage(s): %s" % ", ".join(bad))
            i += 2
        elif k == "--reuse":
            a["reuse"] = True
            i += 1
        elif k == "--crop":
            a["crop"] = [float(v) for v in argv[i + 1].split(",")]
            i += 2
        elif k == "--spp":
            a["spp"] = int(argv[i + 1])
            i += 2
        elif k == "--views":
            a["views"] = int(argv[i + 1])
            i += 2
        else:
            raise SystemExit("unknown option %s" % k)
    return a


def log(msg):
    print(msg)
    sys.stdout.flush()


class Build:
    def __init__(self, args):
        self.a = args
        self.times = {}
        self.world = None
        self.painter = None
        self.trees = None
        self.trees_cat = None

    # -- world ---------------------------------------------------------------------------------
    def get_world(self):
        if self.world is not None:
            return self.world
        cache = scratch("world.pkl")
        if self.a["reuse"] and os.path.isfile(cache):
            try:
                self.world = F.World.load(cache, log=log)
                log("[build] world from cache")
                return self.world
            except Exception as exc:          # a cache from another numpy: rebuild
                log("[build] world cache unusable (%s): rebuilding" % exc)
        self.world = F.build_world(log=log)
        self.world.save(cache)
        return self.world

    def get_world_cached(self):
        if self.world is None:
            self.world = F.World.load(scratch("world.pkl"), log=log)
        return self.world

    def stage_fields(self):
        w = self.get_world()
        os.makedirs(ART3D, exist_ok=True)
        hp = w.height_png16()
        Image.fromarray(hp, "I;16").save(os.path.join(ART3D, "Height.png"))
        with open(os.path.join(ART3D, "Terrain.json"), "w", encoding="utf-8") as f:
            json.dump(w.terrain_json(), f, separators=(",", ":"))
            f.write("\n")
        rgb = F.preview_rgb(w, 2)
        Image.fromarray((rgb * 255).astype(np.uint8)).save(scratch("fields_preview.png"))
        with open(scratch("vectors.json"), "w") as f:
            json.dump(w.vector_data(), f)
        log("[build] Height.png %s, h %.1f..%.1f m" % (hp.shape[::-1], float(w.f["h"].min()),
                                                      float(w.f["h"].max())))

    # -- albedo / masks ----------------------------------------------------------------------------
    def get_painter(self):
        if self.painter is not None:
            return self.painter
        from ironart import world_terrain_paint as P
        self.painter = P.Painter(self.get_world(), log=log).paint()
        return self.painter

    def stage_paint(self):
        p = self.get_painter()
        os.makedirs(os.path.join(ARTSRC, "Terrain"), exist_ok=True)
        alb = p.albedo8(True)
        Image.fromarray(alb, "RGB").save(os.path.join(ARTSRC, "Terrain", "Albedo.png"), optimize=True)
        m = p.masks()
        Image.fromarray(m, "RGBA").save(os.path.join(ARTSRC, "Terrain", "Masks.png"), optimize=True)
        Image.fromarray(m[..., 0], "L").save(scratch("water_mask.png"))
        np.save(scratch("fieldm.npy"), p.fieldm.astype(np.float16))
        Image.fromarray(alb, "RGB").resize((1200, 750), Image.LANCZOS).save(scratch("albedo_small.png"))
        Image.fromarray(m[..., :3], "RGB").resize((1200, 750), Image.LANCZOS).save(scratch("masks_small.png"))

    # -- trees -----------------------------------------------------------------------------------
    def stage_trees(self):
        from ironart import world_terrain_trees as TR
        w = self.get_world()
        fm = None
        if self.painter is not None:
            fm = self.painter.fieldm
        elif os.path.isfile(scratch("fieldm.npy")):
            fm = np.load(scratch("fieldm.npy")).astype(np.float32)
        trees, counts = TR.scatter(w, fm, log=log)
        probs = TR.check(w, trees)
        if probs:
            for pr in probs[:20]:
                log("[trees] QA " + pr)
            raise RuntimeError("%d tree placement problems" % len(probs))
        self.trees_cat = trees
        with open(scratch("trees_cat.json"), "w") as f:
            json.dump(trees, f)
        self.trees = TR.to_json(trees)
        os.makedirs(ART3D, exist_ok=True)
        with open(os.path.join(ART3D, "Trees.json"), "w", encoding="utf-8") as f:
            json.dump(self.trees, f, separators=(",", ":"))
            f.write("\n")

    def get_trees(self):
        if self.trees is None:
            with open(os.path.join(ART3D, "Trees.json"), encoding="utf-8") as f:
                self.trees = json.load(f)
        return self.trees

    def get_trees_cat(self):
        if self.trees_cat is None:
            with open(scratch("trees_cat.json")) as f:
                self.trees_cat = json.load(f)
        return self.trees_cat

    # -- water -----------------------------------------------------------------------------------
    def stage_water(self):
        from ironart import world_terrain_water as WA
        os.makedirs(os.path.join(ARTSRC, "Textures"), exist_ok=True)
        rgb, info = WA.water_normal(1024)
        Image.fromarray(rgb, "RGB").save(os.path.join(ARTSRC, "Textures", "Water_Normal.png"))
        foam = WA.water_foam(1024)
        Image.fromarray(foam, "L").save(os.path.join(ARTSRC, "Textures", "Water_Foam.png"))
        log("[water] normal map: %s" % json.dumps(info))
        n = rgb.astype(np.float32) / 127.5 - 1.0
        L = np.array([-0.5, 0.5, 0.7])
        L /= np.linalg.norm(L)
        shade = np.clip(n @ L, 0, 1)
        tile = np.tile(shade, (2, 2))
        ftile = np.tile(foam, (2, 2))
        prev = np.concatenate([np.round(tile * 255).astype(np.uint8), ftile], 1)
        Image.fromarray(prev).resize((1024, 512), Image.LANCZOS).save(scratch("water_tiles.png"))

    # -- the 2D gongbi map -------------------------------------------------------------------------
    def stage_worldmap(self):
        import bpy
        from ironart import scene
        from ironart import world_terrain_glyphs as G
        from ironart import world_terrain_mapglyphs as MG
        from ironart import world_terrain_mappaint as MP
        w = self.get_world()
        self.painter = None                      # the albedo painter holds ~2 GB of layers
        import gc
        gc.collect()
        crop = self.a["crop"]
        x0, y0, x1, y1 = crop if crop else (0.0, 0.0, float(F.MAP_W), float(F.MAP_H))
        t0 = time.time()
        peaks = MG.layout(w)
        r = MG.rasterize(peaks, cell=0.5)
        mtrees = MG.map_trees(w, self.get_trees_cat())
        for t in mtrees:
            t["z"] = MG.raster_z(r, t["x"], t["y"])
        del r
        log("[worldmap] %d glyph peaks (%d mountain), %d painted trees" % (
            len(peaks), sum(p["kind"] == "mountain" for p in peaks), len(mtrees)))
        with open(scratch("peaks.json"), "w") as f:
            json.dump(peaks, f)
        # the world is not needed while the tiles render (each in its own Blender process):
        # free it and reload it from the cache for the painting
        if os.path.isfile(scratch("world.pkl")):
            self.world = None
            w = None
            gc.collect()
        # ---- Blender: the glyph layer (flat emission + AOVs + Freestyle ink as passes), rendered in
        #      overlapping tiles (Freestyle on the whole map needs > 13 GB); each tile frames its
        #      region plus a margin and gets the geometry around it, the margins are cropped away
        W2, H2 = int(round((x1 - x0) * MP.SS)), int(round((y1 - y0) * MP.SS))
        passes = None
        tiles = _tiles(x0, y0, x1, y1, TILE_M)
        self.times["worldmap_render"] = 0.0
        for ti, (tx0, ty0, tx1, ty1) in enumerate(tiles):
            fx0, fy0 = max(x0, tx0 - TILE_MARGIN), max(y0, ty0 - TILE_MARGIN)
            fx1, fy1 = min(x1, tx1 + TILE_MARGIN), min(y1, ty1 + TILE_MARGIN)
            P = self._render_glyph_tile(peaks, mtrees, (fx0, fy0, fx1, fy1), ti)
            if passes is None:      # float16 is plenty for the colour/attribute passes
                passes = {nm: np.zeros((H2, W2, 4), np.float32 if nm in ("gD", "Depth") else np.float16)
                          for nm in P}
            sx0, sy0 = int(round((tx0 - fx0) * MP.SS)), int(round((ty0 - fy0) * MP.SS))
            sx1, sy1 = sx0 + int(round((tx1 - tx0) * MP.SS)), sy0 + int(round((ty1 - ty0) * MP.SS))
            dx0, dy0 = int(round((tx0 - x0) * MP.SS)), int(round((ty0 - y0) * MP.SS))
            for nm, arr in P.items():
                passes[nm][dy0:dy0 + (sy1 - sy0), dx0:dx0 + (sx1 - sx0)] = arr[sy0:sy1, sx0:sx1]
            del P
            log("[worldmap] tile %d/%d done" % (ti + 1, len(tiles)))
        self.times["worldmap_build"] = time.time() - t0 - self.times["worldmap_render"]
        # ---- numpy: the painting
        w = self.get_world_cached()
        passes = {nm: np.asarray(v, np.float32) if v.dtype != np.float32 else v for nm, v in passes.items()}
        crop_tx = tuple(int(round(v * MP.SS)) for v in (x0, y0, x1, y1))
        mp = MP.MapPainter(w, log=log, crop=crop_tx)
        t1 = time.time()
        col = mp.paint_map(passes)
        del passes
        small = MP.downsample(col)
        self.times["worldmap_paint"] = time.time() - t1
        img = np.concatenate([small, np.ones(small.shape[:2] + (1,), np.float32)], -1)
        if crop:
            tag = "crop_%d_%d_%d_%d" % tuple(int(v) for v in (x0, y0, x1, y1))
            Image.fromarray(np.round(small * 255).astype(np.uint8)).save(scratch("worldmap_%s.png" % tag))
            Image.fromarray(np.round(np.clip(col, 0, 1) * 255).astype(np.uint8)).save(
                scratch("worldmap_%s_2x.png" % tag))
            log("[build] crop saved %s" % scratch("worldmap_%s.png" % tag))
        else:
            from ironart import post
            path = post.save_asset(img, "Art/Map/WorldMap.png")
            Image.open(path).convert("RGB").resize((1200, 750), Image.LANCZOS).save(scratch("worldmap_small.png"))
            Image.fromarray(np.round(np.clip(col, 0, 1) * 255).astype(np.uint8)).save(scratch("worldmap_2x.png"))
            log("[build] WorldMap.png -> %s" % path)

    def _render_glyph_tile(self, peaks, mtrees, frame, ti):
        """Render one glyph tile in its own Blender process (glyph_tile.py) and read its passes."""
        import subprocess
        from ironart import world_terrain_glyphs as G
        pdir = scratch("passes")
        os.makedirs(pdir, exist_ok=True)
        if ti == 0 or not os.path.isfile(scratch("mtrees.json")):
            with open(scratch("mtrees.json"), "w") as f:
                json.dump(mtrees, f)
        tag = "glyph%d" % ti
        cmd = [os.path.join(TOOLS, "render.sh"), os.path.join(HERE, "glyph_tile.py"),
               "%.3f,%.3f,%.3f,%.3f" % frame, tag, str(self.a["spp"] or GLYPH_SPP), scratch(), pdir]
        t0 = time.time()
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        out = res.stdout or ""
        for line in out.splitlines():
            if "rendered" in line or "Traceback" in line or "Error" in line or "FAILED" in line:
                log("[tile %d] %s" % (ti, line))
        if res.returncode != 0:
            log(out[-3000:])
            raise RuntimeError("glyph tile %d failed (exit %d)" % (ti, res.returncode))
        self.times["worldmap_render"] += time.time() - t0
        P = {}
        for nm in ("Image", "Freestyle", "gA", "gB", "gC", "gD", "Depth"):
            P[nm] = G.read_exr(os.path.join(pdir, "%s_%s_0001.exr" % (tag, nm)))
        return P

    # -- 3/4 previews (scratch) ------------------------------------------------------------------
    def stage_preview(self):
        import bpy
        import math
        from mathutils import Vector
        from ironart import scene
        from ironart import world_terrain_render as WR
        trees = self.get_trees()
        hp = np.asarray(Image.open(os.path.join(ART3D, "Height.png")), np.float64)
        tj = json.load(open(os.path.join(ART3D, "Terrain.json")))
        h2 = (tj["minHeight"] + hp / 65535.0 * (tj["maxHeight"] - tj["minHeight"])).astype(np.float32)
        hfull = _upsample_grid2(h2)
        Image.open(os.path.join(ARTSRC, "Terrain", "Masks.png")).getchannel("R").save(scratch("masks_r.png"))
        views = PREVIEW_VIEWS[: (self.a["views"] or len(PREVIEW_VIEWS))]
        for vi, (fx, fy, dist, pitch) in enumerate(views):
            scene.reset(seed=12)
            scene.setup_cycles(samples=self.a["spp"] or 24, transparent=False, preset="map",
                               view="Standard", look="None", adaptive_threshold=0.03)
            scene.set_resolution(1280, 720, 1)
            # terrain exactly as Unreal builds it: the exported Height.png grid (2 m)
            WR.build_terrain(hfull, os.path.join(ARTSRC, "Terrain", "Albedo.png"), scratch("masks_r.png"),
                             None, step=2)
            _sea_plane(WR)
            protos = _glb_tree_protos()
            if protos:
                WR.instance_trees(trees, hfull, protos)
            WR.camera_persp((fx, fy), dist, hfull, tilt=pitch, fov=40.0)
            # the painted look of AIronEnvironment: a soft key from the north-west (bearing 305)
            # at ~48 deg and a strong warm sky fill
            az, el = math.radians(305.0), math.radians(48.0)
            d = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
            WR._sun("Sun", d, 3.2, "#FFF4E2", 8.0)
            WR.world_color("#E8DCC0", 0.9)
            _mist_comp()
            raw = scratch("preview3d_%d.png" % vi)
            self.times["preview_%d" % vi] = scene.render(raw)
            log("[build] preview %s" % raw)

    def stage_qa(self):
        qa_report(self)
        contact_sheet(self)

    def stage_manifest(self):
        update_manifest(MANIFEST_FILES)

    def run(self):
        for st in STAGES:
            if st in self.a["stages"]:
                t0 = time.time()
                log("[build] ---- stage %s" % st)
                getattr(self, "stage_" + st)()
                self.times[st] = time.time() - t0
                log("[build] stage %s %.1fs" % (st, self.times[st]))
        log("[build] TIMES " + json.dumps({k: round(v, 1) for k, v in self.times.items()}))


def _tiles(x0, y0, x1, y1, size):
    """Split a map rectangle into a grid of tiles of at most ``size`` (w, h) metres."""
    nx = max(1, int(math.ceil((x1 - x0) / size[0])))
    ny = max(1, int(math.ceil((y1 - y0) / size[1])))
    xs = [x0 + (x1 - x0) * i / nx for i in range(nx + 1)]
    ys = [y0 + (y1 - y0) * j / ny for j in range(ny + 1)]
    xs = [round(v) for v in xs]
    ys = [round(v) for v in ys]
    return [(xs[i], ys[j], xs[i + 1], ys[j + 1]) for j in range(ny) for i in range(nx)]


def _upsample_grid2(h2):
    """Height.png grid (751, 1201) -> master grid (1501, 2401) by bilinear interpolation."""
    H2, W2 = h2.shape
    out = np.zeros((2 * H2 - 1, 2 * W2 - 1), np.float32)
    out[::2, ::2] = h2
    out[1::2, ::2] = 0.5 * (h2[:-1] + h2[1:])
    out[:, 1::2] = 0.5 * (out[:, :-2:2] + out[:, 2::2])
    return out


def _sea_plane(WR):
    """Preview stand-in for M_IronWater: a pale azurite, slightly glossy plane at sea level."""
    import bpy
    import bmesh
    me = bpy.data.meshes.new("Sea")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=4000)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("Sea", me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(WR.simple_material("SeaM", "#6F93AE", 0.25))
    return ob


def _glb_tree_protos():
    """SM_Tree_* stand-ins for the previews: the World Models family's glbs (when present)."""
    import bpy
    protos = {}
    for kind, name in (("pine", "Tree_Pine"), ("broad", "Tree_Broad"), ("bamboo", "Tree_Bamboo")):
        path = os.path.join(ARTSRC, "Models", name + ".glb")
        if not os.path.isfile(path):
            continue
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=path)
        meshes = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
        if not meshes:
            continue
        bpy.ops.object.select_all(action="DESELECT")
        for o in meshes:
            o.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]
        if len(meshes) > 1:
            bpy.ops.object.join()
        p = bpy.context.view_layer.objects.active
        p.location = (0, 0, -5000)
        protos[kind] = p
    return protos if len(protos) == 3 else None


def _mist_comp():
    """Aerial perspective for the 3/4 previews: mist pass -> warm silk haze."""
    import bpy
    sc = bpy.context.scene
    vl = sc.view_layers[0]
    vl.use_pass_mist = True
    w = sc.world
    w.mist_settings.start = 800.0
    w.mist_settings.depth = 3200.0
    w.mist_settings.falloff = "QUADRATIC"
    sc.use_nodes = True
    nt = sc.node_tree
    nt.nodes.clear()
    rl = nt.nodes.new("CompositorNodeRLayers")
    comp = nt.nodes.new("CompositorNodeComposite")
    mix = nt.nodes.new("CompositorNodeMixRGB")
    mix.blend_type = "MIX"
    mul = nt.nodes.new("CompositorNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = 0.35
    nt.links.new(rl.outputs["Mist"], mul.inputs[0])
    nt.links.new(mul.outputs[0], mix.inputs[0])
    nt.links.new(rl.outputs["Image"], mix.inputs[1])
    mix.inputs[2].default_value = (0.86, 0.80, 0.66, 1.0)
    nt.links.new(mix.outputs[0], comp.inputs["Image"])


def qa_report(b):
    """Contract checks on the written files (raises on a broken contract)."""
    probs = []
    tj = json.load(open(os.path.join(ART3D, "Terrain.json")))
    want = {"width": 2400, "height": 1500, "gridStep": 2, "minHeight": -40, "maxHeight": 180, "seaLevel": 0}
    if tj != want:
        probs.append("Terrain.json %r != %r" % (tj, want))
    im = Image.open(os.path.join(ART3D, "Height.png"))
    if im.size != (1201, 751) or im.mode not in ("I;16", "I;16B", "I"):
        probs.append("Height.png is %s %s" % (im.size, im.mode))
    hv = np.asarray(im, np.float64)
    hm = -40 + hv / 65535.0 * 220.0
    log("[qa] Height.png %s %s, %.2f..%.2f m, land %.1f %%, >140 m %.3f %%" % (
        im.size, im.mode, hm.min(), hm.max(), 100 * (hm > 0).mean(), 100 * (hm > 140).mean()))
    for name, mode in (("Albedo.png", "RGB"), ("Masks.png", "RGBA")):
        p = os.path.join(ARTSRC, "Terrain", name)
        im = Image.open(p)
        if im.size != (4800, 3000) or im.mode != mode:
            probs.append("%s is %s %s" % (name, im.size, im.mode))
        log("[qa] %s %s %s %d KB" % (name, im.size, im.mode, os.path.getsize(p) // 1024))
    m = np.asarray(Image.open(os.path.join(ARTSRC, "Terrain", "Masks.png")))
    if m[..., 3].min() < 1:
        probs.append("Masks.png alpha has zeros (Unreal FillPNGZeroAlpha would wipe RGB)")
    log("[qa] masks coverage: water %.1f %%, forest %.1f %%, rock/alt %.1f %%, road %.2f %%" % tuple(
        100 * float((m[..., c] > 127).mean()) for c in range(4)))
    trees = b.get_trees()
    kinds = {}
    for t in trees:
        kinds[t["t"]] = kinds.get(t["t"], 0) + 1
    log("[qa] Trees.json %d instances %s" % (len(trees), kinds))
    if len(trees) > 25000:
        probs.append("too many trees")
    for t in trees:
        for c in b.get_world().cities:
            if (t["x"] - c[1]) ** 2 + (t["y"] - c[2]) ** 2 < 25.0 ** 2:
                probs.append("tree within 25 m of %s" % c[0])
    nimg = Image.open(os.path.join(ARTSRC, "Textures", "Water_Normal.png"))
    if nimg.size != (1024, 1024):
        probs.append("Water_Normal.png size")
    if os.path.isfile(WORLDMAP):
        wm = Image.open(WORLDMAP)
        log("[qa] WorldMap.png %s %s %d KB" % (wm.size, wm.mode, os.path.getsize(WORLDMAP) // 1024))
        if wm.size != (2400, 1500):
            probs.append("WorldMap.png size")
        else:
            off = worldmap_alignment(b, np.asarray(wm.convert("RGB"), np.int16))
            if off != (0, 0):
                probs.append("WorldMap.png coast is offset by %s px from the map data" % (off,))
            calm = worldmap_city_calm(b, np.asarray(wm.convert("RGB"), np.float32))
            if calm:
                probs.extend(calm)
    if probs:
        for pr in probs:
            log("[qa] PROBLEM " + pr)
        raise RuntimeError("QA failed: %d problem(s)" % len(probs))
    log("[qa] all contract checks passed")


def _height_at_pixels(w=2400, h=1500):
    """Height.png sampled (bilinear) at the WorldMap pixel centres (map x + 0.5, y + 0.5)."""
    hp = np.asarray(Image.open(os.path.join(ART3D, "Height.png")), np.float64)
    hg = -40 + hp / 65535.0 * 220.0
    u = (np.arange(w) + 0.5) / 2.0
    v = (np.arange(h) + 0.5) / 2.0
    i0 = np.clip(np.floor(u).astype(int), 0, hg.shape[1] - 2)
    j0 = np.clip(np.floor(v).astype(int), 0, hg.shape[0] - 2)
    fu = (u - i0)[None, :]
    fv = (v - j0)[:, None]
    a = hg[j0][:, i0] * (1 - fu) + hg[j0][:, i0 + 1] * fu
    b_ = hg[j0 + 1][:, i0] * (1 - fu) + hg[j0 + 1][:, i0 + 1] * fu
    return a * (1 - fv) + b_ * fv


def worldmap_alignment(b, rgb):
    """Best (dx, dy) shift between the painted sea (pale azurite: blue above red) and the
    heightfield's sea (h < 0), measured in the shore band (|h| < 6 m) and ignoring the coast's
    ink line (dark pixels); (0, 0) means the 2D map is registered to map metres.  A shift is only
    reported when it beats (0, 0) clearly (the ink line straddles the coast, which can tip a
    1 px shift by a hair)."""
    hm = _height_at_pixels()
    sea_d = hm < 0.0
    band = np.abs(hm) < 6.0
    sea_r = rgb[..., 2] > rgb[..., 0] + 6
    luma = rgb @ np.array([0.299, 0.587, 0.114])
    valid = luma > 110
    scores = {}
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            a = np.roll(np.roll(sea_d, dy, 0), dx, 1)[8:-8, 8:-8]
            m = np.roll(np.roll(band, dy, 0), dx, 1)[8:-8, 8:-8] & valid[8:-8, 8:-8]
            r = sea_r[8:-8, 8:-8]
            scores[(dx, dy)] = float((a == r)[m].mean())
    arg = max(scores, key=scores.get)
    best, s0 = scores[arg], scores[(0, 0)]
    log("[qa] WorldMap registration: best shift %s (%.4f), at (0, 0) %.4f" % (arg, best, s0))
    if s0 < 0.9:
        log("[qa] WARNING low sea agreement")
    return (0, 0) if s0 >= best - 0.01 else arg


def worldmap_city_calm(b, rgb):
    """The city sites must stay calm (no glyph ink on them): little dark ink within 22 px."""
    probs = []
    luma = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    for (k, cx, cy, s) in b.get_world().cities:
        x0, x1 = int(max(0, cx - 22)), int(min(2400, cx + 23))
        y0, y1 = int(max(0, cy - 22)), int(min(1500, cy + 23))
        ys, xs = np.mgrid[y0:y1, x0:x1]
        m = (xs - cx) ** 2 + (ys - cy) ** 2 < 22 ** 2
        dark = float((luma[y0:y1, x0:x1][m] < 90).mean())
        if dark > 0.04:
            probs.append("city %s site is not calm: %.1f %% dark ink within 22 px" % (k, 100 * dark))
    log("[qa] city sites calm: %d problem(s)" % len(probs))
    return probs


def contact_sheet(b):
    """Scratch overview: WorldMap, albedo, masks, roads, relief and tree density side by side."""
    from PIL import ImageDraw
    tw, th = 800, 500
    tiles = []

    def add(img, label):
        im = img.convert("RGB").resize((tw, th), Image.LANCZOS)
        ImageDraw.Draw(im).text((8, 6), label, fill=(30, 26, 22))
        tiles.append(im)
    if os.path.isfile(WORLDMAP):
        add(Image.open(WORLDMAP), "WorldMap.png (2D gongbi map)")
    alb = Image.open(os.path.join(ARTSRC, "Terrain", "Albedo.png"))
    add(alb, "Albedo.png (pigment, no lighting)")
    m = Image.open(os.path.join(ARTSRC, "Terrain", "Masks.png"))
    add(Image.merge("RGB", m.split()[:3]), "Masks.png RGB = water / forest / rock-snow")
    add(m.getchannel("A"), "Masks.png A = road")
    hp = np.asarray(Image.open(os.path.join(ART3D, "Height.png")), np.float32) / 65535.0
    hm = -40 + hp * 220
    add(Image.fromarray((np.clip(F.preview_rgb_from_h(hm, 2.0), 0, 1) * 255).astype(np.uint8)),
        "Height.png relief (1201x751, 2 m)")
    small = alb.resize((tw, th), Image.LANCZOS)
    d = ImageDraw.Draw(small)
    cols = {"pine": (20, 60, 30), "broad": (90, 140, 40), "bamboo": (200, 230, 90)}
    for t in b.get_trees():
        x, y = t["x"] / F.MAP_W * tw, t["y"] / F.MAP_H * th
        d.point((x, y), fill=cols[t["t"]])
    ImageDraw.Draw(small).text((8, 6), "Trees.json (%d)" % len(b.get_trees()), fill=(30, 26, 22))
    tiles.append(small)
    sheet = Image.new("RGB", (2 * tw + 12, 3 * th + 16), (27, 23, 18))
    for i, im in enumerate(tiles):
        sheet.paste(im, ((i % 2) * (tw + 12), (i // 2) * (th + 8)))
    sheet.save(scratch("world_terrain_sheet.png"))
    log("[qa] contact sheet %s" % scratch("world_terrain_sheet.png"))


def update_manifest(files):
    """Read-modify-write ArtSource/manifest.json under an exclusive lock: add our files, bump
    the version (other artists add their entries concurrently)."""
    import fcntl
    os.makedirs(ARTSRC, exist_ok=True)
    path = os.path.join(ARTSRC, "manifest.json")
    lock = open(os.path.join(ARTSRC, ".manifest.lock"), "a+")      # shared with the other families
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        data = {"version": 0, "files": []}
        if os.path.isfile(path):
            with open(path, encoding="utf-8-sig") as f:
                data = json.load(f)
        data.setdefault("files", [])
        have = set(x if isinstance(x, str) else x.get("path") for x in data["files"])
        for fn in files:
            if fn not in have:
                data["files"].append(fn)
        data["version"] = int(data.get("version", 0)) + 1
        data.setdefault("normalMapConvention", "opengl")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
        log("[manifest] version %d, %d files" % (data["version"], len(data["files"])))
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


if __name__ == "__main__":
    from ironart import scene
    Build(parse_args(scene.args())).run()
