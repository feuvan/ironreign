"""World Terrain family: regenerate every output deterministically.

    Tools/BlenderArt/render.sh Tools/BlenderArt/world_terrain/build.py [options]

Outputs (DESIGN.md 12.2 / section 8):
    Content/Data/Art3D/Terrain/Terrain.json   terrain contract
    Content/Data/Art3D/Terrain/Height.png      1201 x 751, 16-bit grey (pixel (i, j) = map (2i, 2j))
    Content/Data/Art3D/Terrain/Trees.json      tree instances
    ArtSource/Terrain/Albedo.png               4800 x 3000 sRGB ground colour, no lighting
    ArtSource/Terrain/Masks.png                4800 x 3000 RGBA: R water, G forest, B rock/snow, A road
    ArtSource/Textures/Water_Normal.png        1024 x 1024 tileable normal map (OpenGL)
    ArtSource/Textures/Water_Foam.png          1024 x 1024 tileable foam mask
    Content/Data/Art/Map/WorldMap.png          2400 x 1500 2D fallback map (Cycles, top-down)
    ArtSource/manifest.json                    entries added, version bumped
Scratch (previews, caches): $IRONART_OUT/world_terrain/

Options
    --stages a,b,...   subset of: fields paint trees water worldmap preview qa manifest
                       (default: all, in that order)
    --reuse            load the field / paint caches from scratch when present (iteration only;
                       a clean run rebuilds everything and produces identical files)
    --crop x0,y0,x1,y1 worldmap stage: render only this map rectangle (metres) to scratch
    --spp N            override the worldmap samples (iteration)
    --views N          preview stage: number of 3/4 views (default all)
"""

import json
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
ARTSRC = os.path.join(REPO_DIR, "ArtSource")
WORLDMAP = os.path.join(REPO_DIR, "Content", "Data", "Art", "Map", "WorldMap.png")


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

    # -- stages ------------------------------------------------------------------------------
    def get_world(self):
        if self.world is not None:
            return self.world
        cache = scratch("world.pkl")
        if self.a["reuse"] and os.path.isfile(cache):
            self.world = F.World.load(cache, log=log)
            log("[build] world from cache")
        else:
            self.world = F.build_world(log=log)
            self.world.save(cache)
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

    def get_painter(self):
        if self.painter is not None:
            return self.painter
        from ironart import world_terrain_paint as P
        self.painter = P.Painter(self.get_world(), log=log).paint()
        return self.painter

    def stage_paint(self):
        from ironart import world_terrain_recipe as RC
        from ironart import world_terrain_water as WA
        p = self.get_painter()
        os.makedirs(os.path.join(ARTSRC, "Terrain"), exist_ok=True)
        Image.fromarray(p.albedo8(True), "RGB").save(os.path.join(ARTSRC, "Terrain", "Albedo.png"))
        Image.fromarray(p.masks(), "RGBA").save(os.path.join(ARTSRC, "Terrain", "Masks.png"))
        # scratch inputs of the 2D render
        Image.fromarray(p.albedo8(False), "RGB").save(scratch("albedo_noroads.png"))
        Image.fromarray(np.round(p.water * 255).astype(np.uint8), "L").save(scratch("water_mask.png"))
        np.save(scratch("fieldm.npy"), p.fieldm.astype(np.float16))
        np.save(scratch("bankm.npy"), p.bankm.astype(np.float16))
        sea = WA.sea_colour(p, RC.WORLDMAP["sea"])
        Image.fromarray(np.round(sea * 255).astype(np.uint8), "RGB").save(scratch("sea.png"))
        a = Image.fromarray(p.albedo8(True), "RGB")
        a.resize((1200, 750), Image.LANCZOS).save(scratch("albedo_small.png"))
        Image.fromarray(p.masks()[..., :3], "RGB").resize((1200, 750), Image.LANCZOS).save(scratch("masks_small.png"))

    def stage_trees(self):
        from ironart import world_terrain_trees as TR
        w = self.get_world()
        fm = bk = None
        if self.painter is not None:
            fm, bk = self.painter.fieldm, self.painter.bankm
        elif os.path.isfile(scratch("fieldm.npy")):
            fm = np.load(scratch("fieldm.npy")).astype(np.float32)
            if os.path.isfile(scratch("bankm.npy")):
                bk = np.load(scratch("bankm.npy")).astype(np.float32)
        trees, counts = TR.scatter(w, fm, log=log, bankm=bk)
        probs = TR.check(w, trees)
        if probs:
            for pr in probs[:20]:
                log("[trees] QA " + pr)
            raise RuntimeError("%d tree placement problems" % len(probs))
        self.trees = TR.to_json(trees)
        os.makedirs(ART3D, exist_ok=True)
        with open(os.path.join(ART3D, "Trees.json"), "w", encoding="utf-8") as f:
            json.dump(self.trees, f, separators=(",", ":"))
            f.write("\n")
        self.tree_counts = counts

    def get_trees(self):
        if self.trees is None:
            with open(os.path.join(ART3D, "Trees.json"), encoding="utf-8") as f:
                self.trees = json.load(f)
        return self.trees

    def stage_water(self):
        from ironart import world_terrain_water as WA
        os.makedirs(os.path.join(ARTSRC, "Textures"), exist_ok=True)
        rgb, info = WA.water_normal(1024)
        Image.fromarray(rgb, "RGB").save(os.path.join(ARTSRC, "Textures", "Water_Normal.png"))
        foam = WA.water_foam(1024)
        Image.fromarray(foam, "L").save(os.path.join(ARTSRC, "Textures", "Water_Foam.png"))
        log("[water] normal map: %s" % json.dumps(info))
        # preview: 2x2 tiles lit from the top-left (seam check) + foam tiles
        n = rgb.astype(np.float32) / 127.5 - 1.0
        L = np.array([-0.5, 0.5, 0.7])
        L /= np.linalg.norm(L)
        shade = np.clip(n @ L, 0, 1)
        tile = np.tile(shade, (2, 2))
        ftile = np.tile(foam, (2, 2))
        prev = np.concatenate([np.round(tile * 255).astype(np.uint8), ftile], 1)
        Image.fromarray(prev).resize((1024, 512), Image.LANCZOS).save(scratch("water_tiles.png"))

    def stage_worldmap(self):
        from ironart import world_terrain_render as WR
        from ironart import world_terrain_recipe as RC
        from ironart import scene, post
        rec = RC.WORLDMAP
        w = self.get_world()
        trees = self.get_trees()
        crop = self.a["crop"]
        scene.reset(seed=11)
        if crop:
            x0, y0, x1, y1 = crop
            tw, th = int(round(x1 - x0)), int(round(y1 - y0))
        else:
            x0, y0, x1, y1 = 0.0, 0.0, float(F.MAP_W), float(F.MAP_H)
            tw, th = rec["size"]
        spp = self.a["spp"] or rec["spp"]
        scene.setup_cycles(samples=spp, transparent=False, preset="map", view="Standard", look="None",
                           adaptive_threshold=rec["adaptive"])
        scene.set_resolution(tw, th, rec["ss"])
        normal = os.path.join(ARTSRC, "Textures", "Water_Normal.png")
        t0 = time.time()
        WR.build_terrain(w.f["h"], scratch("albedo_noroads.png"), scratch("water_mask.png"), normal, step=1)
        WR.build_sea(scratch("sea.png"), normal)
        protos = WR.tree_prototypes()
        sel = [t for t in trees if x0 - 20 <= t["x"] <= x1 + 20 and y0 - 20 <= t["y"] <= y1 + 20]
        WR.instance_trees(sel, w.f["h"], protos)
        cam = WR.camera_top(x0, y0, x1, y1)
        WR.light_top(cam, rec)
        k = rec["kuwahara"]
        post.comp_painterly(size=k["size"], sharpness=k["sharpness"], eccentricity=k["eccentricity"],
                            amount=k["amount"], ink=False)
        self.times["worldmap_build"] = time.time() - t0
        tag = "crop_%d_%d_%d_%d" % tuple(int(v) for v in (x0, y0, x1, y1)) if crop else "full"
        raw = scratch("worldmap_raw_%s.png" % tag)
        self.times["worldmap_render"] = scene.render(raw)
        img = post.load(raw)
        img = post.downsample(img, rec["ss"])
        img = post.grade(img, **rec["grade"])
        if rec.get("unsharp"):
            img = post.unsharp(img, *rec["unsharp"])
        img[..., 3] = 1.0
        if crop:
            post.save(img, scratch("worldmap_%s.png" % tag), opaque=True)
            log("[build] crop saved %s" % scratch("worldmap_%s.png" % tag))
        else:
            path = post.save_asset(img, "Art/Map/WorldMap.png")
            post.save(img, scratch("worldmap_full.png"), opaque=True)
            Image.open(path).resize((1200, 750), Image.LANCZOS).save(scratch("worldmap_small.png"))
            log("[build] WorldMap.png -> %s" % path)

    def stage_preview(self):
        from ironart import world_terrain_render as WR
        from ironart import world_terrain_recipe as RC
        from ironart import scene, post
        rec = RC.PREVIEW3D
        trees = self.get_trees()
        # terrain from the *exported* Height.png (checks the contract round trip)
        hp = np.asarray(Image.open(os.path.join(ART3D, "Height.png")), np.float64)
        tj = json.load(open(os.path.join(ART3D, "Terrain.json")))
        h2 = (tj["minHeight"] + hp / 65535.0 * (tj["maxHeight"] - tj["minHeight"])).astype(np.float32)
        hfull = _upsample_grid2(h2)
        Image.open(os.path.join(ARTSRC, "Terrain", "Masks.png")).getchannel("R").save(scratch("masks_r.png"))
        views = rec["focus"][: (self.a["views"] or len(rec["focus"]))]
        for vi, (fx, fy, dist) in enumerate(views):
            scene.reset(seed=12)
            w_, h_ = rec["size"]
            scene.setup_cycles(samples=self.a["spp"] or rec["spp"], transparent=False, preset="map",
                               view="Filmic", look="Medium Contrast", adaptive_threshold=0.03)
            scene.set_resolution(w_, h_, 1)
            normal = os.path.join(ARTSRC, "Textures", "Water_Normal.png")
            WR.build_terrain(hfull, os.path.join(ARTSRC, "Terrain", "Albedo.png"), scratch("masks_r.png"),
                             normal, step=2)
            WR.build_sea(scratch("sea.png"), normal, margin=3000.0)
            protos = WR.tree_prototypes()
            WR.instance_trees(trees, hfull, protos)
            WR.camera_persp((fx, fy), dist, hfull, tilt=rec["tilt"], fov=rec["focal_fov"])
            WR.light_persp(rec)
            _mist_comp(scene_obj=None)
            raw = scratch("preview3d_%d.png" % vi)
            self.times["preview_%d" % vi] = scene.render(raw)
            log("[build] preview %s" % raw)

    def stage_qa(self):
        qa_report(self)
        contact_sheet(self)

    def stage_manifest(self):
        update_manifest(["Terrain/Albedo.png", "Terrain/Masks.png", "Textures/Water_Normal.png",
                         "Textures/Water_Foam.png"])

    def run(self):
        for st in STAGES:
            if st in self.a["stages"]:
                t0 = time.time()
                log("[build] ---- stage %s" % st)
                getattr(self, "stage_" + st)()
                self.times[st] = time.time() - t0
                log("[build] stage %s %.1fs" % (st, self.times[st]))
        log("[build] TIMES " + json.dumps({k: round(v, 1) for k, v in self.times.items()}))


def _upsample_grid2(h2):
    """Height.png grid (751, 1201) -> master grid (1501, 2401) by bilinear interpolation."""
    H2, W2 = h2.shape
    out = np.zeros((2 * H2 - 1, 2 * W2 - 1), np.float32)
    out[::2, ::2] = h2
    out[1::2, ::2] = 0.5 * (h2[:-1] + h2[1:])
    out[:, 1::2] = 0.5 * (out[:, :-2:2] + out[:, 2::2])
    return out


def _mist_comp(scene_obj=None):
    """Aerial perspective for the 3/4 previews: mist pass -> haze colour."""
    import bpy
    sc = bpy.context.scene
    vl = sc.view_layers[0]
    vl.use_pass_mist = True
    w = sc.world
    w.mist_settings.start = 500.0
    w.mist_settings.depth = 2600.0
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
    mul.inputs[1].default_value = 0.42
    nt.links.new(rl.outputs["Mist"], mul.inputs[0])
    nt.links.new(mul.outputs[0], mix.inputs[0])
    nt.links.new(rl.outputs["Image"], mix.inputs[1])
    mix.inputs[2].default_value = (0.62, 0.70, 0.78, 1.0)
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
    if probs:
        for pr in probs:
            log("[qa] PROBLEM " + pr)
        raise RuntimeError("QA failed: %d problem(s)" % len(probs))
    log("[qa] all contract checks passed")


def worldmap_alignment(b, rgb):
    """Best (dx, dy) shift between the rendered sea (blue-dominant pixels) and the heightfield's
    sea (h < 0 at the pixel centres); (0, 0) means the 2D map is registered to map metres."""
    hp = np.asarray(Image.open(os.path.join(ART3D, "Height.png")), np.float64)
    h = -40 + hp / 65535.0 * 220.0
    # pixel (i, j) centre = map (i + 0.5, j + 0.5) -> Height.png (2 m grid) bilinear
    hm = np.asarray(Image.fromarray(h.astype(np.float32), "F").resize((2400, 1500), Image.BILINEAR))
    sea_d = hm < -0.5
    sea_r = (rgb[..., 2] > rgb[..., 0] + 25) & (rgb[..., 2] > 70)
    best, arg = -1.0, (0, 0)
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            a = np.roll(np.roll(sea_d, dy, 0), dx, 1)[8:-8, 8:-8]
            r = sea_r[8:-8, 8:-8]
            score = float((a == r).mean())
            if score > best:
                best, arg = score, (dx, dy)
    log("[qa] WorldMap registration: best shift %s, sea agreement %.4f" % (arg, best))
    return arg


def contact_sheet(b):
    """Scratch overview: WorldMap, albedo, masks, roads, relief and tree density side by side."""
    from PIL import ImageDraw
    tw, th = 800, 500
    tiles = []

    def add(img, label):
        im = img.convert("RGB").resize((tw, th), Image.LANCZOS)
        ImageDraw.Draw(im).text((8, 6), label, fill=(255, 255, 255))
        tiles.append(im)
    if os.path.isfile(WORLDMAP):
        add(Image.open(WORLDMAP), "WorldMap.png (2D fallback)")
    alb = Image.open(os.path.join(ARTSRC, "Terrain", "Albedo.png"))
    add(alb, "Albedo.png (no lighting)")
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
    ImageDraw.Draw(small).text((8, 6), "Trees.json (%d)" % len(b.get_trees()), fill=(255, 255, 255))
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
