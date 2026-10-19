"""Illustrated Scenes family - gongbi ink-and-colour paintings on silk.  One entry script
regenerates every output deterministically:

    Tools/BlenderArt/render.sh Tools/BlenderArt/scenes/build.py [options]

Outputs (DESIGN.md section 8 manifest + @2x masters in ArtSource):

    Content/Data/Art/UI/Title_Background.png   1920x1080   ArtSource/UI/Title_Background@2x.png  3840x2160
    Content/Data/Art/Events/<Name>.png         640x360     ArtSource/Events/<Name>@2x.png        1280x720
    Content/Data/Art/Duel/Background.png       1280x720    ArtSource/Duel/Background@2x.png      2560x1440

Options
    --only A,B      scenes to build (Title, Court, Battle, Harvest, Disaster, Wanderer, Sect,
                    Bandits, Envoy, Festival, Plague, Flood, Omen, Duel)
    --preview F     preview at F x the game size (e.g. 0.5), low samples, preview folder only
    --spp N         override samples
    --out DIR       preview / intermediates folder (default $IRONART_OUT/scenes)
    --region x0,y0,x1,y1   render only this normalised region (y down); writes <Name>_region.png
                    (master crop) next to the previews - for full-resolution detail checks
    --no-save       do not write Content/Data or ArtSource
    --no-manifest   do not touch ArtSource/manifest.json
    --no-ink        skip Freestyle (scenes that still ask for it); image-space ink is unaffected
    --reuse         re-composite the passes of the previous render (look / ink iteration)

Each scene module ``sc_<name>.py`` defines ``SPEC`` (name, art, master, size = game size,
k = render px per game px, m = master px per game px, seed, spp) and ``build(r)`` which builds
the scene with the gongbi kit and returns a dict: ``camera``, ``look`` (composite settings, see
``ironart.scenes_gongbi.composite``), optional ``ink`` (per-kind overrides), ``ink_scale``,
``paint2d(cv, r)`` (painted 2D motifs) and ``notes`` (UI anchors for the report).
"""

import importlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from ironart import scene, scenes_gongbi as GB, scenes_gongbi_2d as G2  # noqa: E402

ORDER = ["Title", "Court", "Battle", "Harvest", "Disaster", "Wanderer", "Sect", "Bandits", "Envoy",
         "Festival", "Plague", "Flood", "Omen", "Duel"]


def opt(name, default=None, cast=str):
    a = scene.args()
    if name in a:
        i = a.index(name)
        if i + 1 < len(a):
            return cast(a[i + 1])
    return default


def rss_mb():
    """(current, peak) resident memory of this process in MB."""
    cur = peak = 0.0
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    cur = int(line.split()[1]) / 1024.0
                elif line.startswith("VmHWM:"):
                    peak = int(line.split()[1]) / 1024.0
    except OSError:
        pass
    return cur, peak


def free_scene():
    """Drop the built scene (objects, meshes, materials, node groups, images) once its passes are
    on disk, so the numpy composite does not stack on top of the render's memory (the 3840x2160
    title otherwise peaks above the machine's memory)."""
    import gc
    import bpy
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.node_groups,
                 bpy.data.images, bpy.data.cameras, bpy.data.lights, bpy.data.linestyles):
        items = list(coll)
        if items:
            bpy.data.batch_remove(items)
    gc.collect()


class Timer:
    def __init__(self):
        self.t = {}
        self._t0 = time.time()

    def lap(self, name):
        print("[scenes] %s done, RSS %.0f MB (peak %.0f MB)" % ((name,) + rss_mb()))
        now = time.time()
        self.t[name] = round(now - self._t0, 1)
        self._t0 = now


def run_one(name, out_dir, preview=None, spp=None, save=True):
    import bpy
    import numpy as np
    mod = importlib.import_module("sc_" + name.lower())
    spec = dict(mod.SPEC)
    t = Timer()
    seed = spec.get("seed", 1)
    scene.reset(seed=seed)
    W1, H1 = spec["size"]
    s = preview or 1.0
    k = spec.get("k", 4) * s
    m = spec.get("m", 2) * s
    rw, rh = int(round(W1 * k)), int(round(H1 * k))
    samples = spp or (spec.get("preview_spp", GB.RECIPE["preview_spp"]) if preview else spec.get("spp", GB.RECIPE["spp"]))
    r = GB.setup(rw, rh, ss=1, spp=samples, preview=bool(preview), seed=seed)
    r.update(k=k, m=m, name=name, game=(W1, H1), render=(rw, rh), scale=s)
    d = mod.build(r) or {}
    cam = d.get("camera") or bpy.context.scene.camera
    GB.set_screen(cam.data.lens / cam.data.sensor_width * W1)
    t.lap("build")
    if d.get("ink_mode") == "freestyle" and "--no-ink" not in scene.args():
        GB.setup_ink(k=k, scale=d.get("ink_scale", 1.0), overrides=d.get("ink"),
                     crease_deg=d.get("crease_deg", 140.0))
    region = opt("--region")
    if region:
        x0, y0, x1, y1 = [float(v) for v in region.split(",")]
        sc = bpy.context.scene
        sc.render.use_border = True
        sc.render.use_crop_to_border = False
        sc.render.border_min_x, sc.render.border_max_x = x0, x1
        sc.render.border_min_y, sc.render.border_max_y = 1.0 - y1, 1.0 - y0
    pdir = os.path.join(out_dir, "%s_passes" % name)
    if "--reuse" in scene.args() and os.path.isdir(pdir) and any(f.endswith(".exr") for f in os.listdir(pdir)):
        # composite-only iteration on the passes of the previous render
        ps, secs = GB.load_passes(pdir), 0.0
    else:
        ps, secs = GB.render(pdir)
    print("[scenes] %s rendered %dx%d %d spp in %.1fs" % (name, rw, rh, samples, secs))
    t.lap("render")
    cv = G2.Canvas(rw, rh, k=k, ovs=2 if rw < 5000 else 1)
    if d.get("paint2d"):
        d["paint2d"](cv, r)
    look = dict(d.get("look", {}))
    notes = d.get("notes", "")
    d = None
    free_scene()
    t.lap("free")
    master_size = (int(round(W1 * m)), int(round(H1 * m)))
    res = GB.composite(ps, look, seed=seed, overlays=cv, master_size=master_size, k=k, m=m)
    master = res["master"]
    t.lap("composite")
    game = (int(round(W1 * s)), int(round(H1 * s)))
    one = GB.downsample_1x(master, game) if master_size != game else master
    pv = os.path.join(out_dir, "preview")
    os.makedirs(pv, exist_ok=True)
    GB.save_png(one, os.path.join(pv, "%s.png" % name), seed)
    GB.save_png(master, os.path.join(pv, "%s_master.png" % name), seed)
    if region:
        mh, mw = master.shape[:2]
        crop = master[int(y0 * mh):int(y1 * mh), int(x0 * mw):int(x1 * mw)]
        GB.save_png(crop, os.path.join(pv, "%s_region.png" % name), seed)
    outputs = {}
    if save and not preview:
        outputs = save_outputs(master, one, spec, seed)
    t.lap("save")
    q = qa(one)
    print("[scenes] QA %s %s" % (name, json.dumps(q)))
    info = dict(scene=name, render_s=round(secs, 1), times=t.t, samples=samples, render_size=[rw, rh],
                qa=q, outputs=outputs, notes=notes)
    print("[scenes] %s" % json.dumps(info))
    return info


def save_outputs(master, one, spec, seed):
    from ironart import post
    from ironart.scenes_look import ART_SOURCE, REPO
    out = {}
    rgba = GB.to_png8(one, seed).astype("float32") / 255.0
    p1 = post.save_asset(rgba, spec["art"])
    out["asset"] = p1
    if spec.get("master"):
        pm = os.path.join(ART_SOURCE, spec["master"])
        GB.save_png(master, pm, seed)
        out["master"] = pm
    rep = {}
    from PIL import Image
    for kk, p in out.items():
        with Image.open(p) as im:
            rep[kk] = dict(path=os.path.relpath(p, REPO), size=list(im.size), kB=round(os.path.getsize(p) / 1024.0, 1))
    return rep


def qa(img):
    """Measured values of the game image: mean luma, silk share, ink share, clipping."""
    import numpy as np
    lum = (img * np.array([0.299, 0.587, 0.114], np.float32)).sum(-1)
    return dict(mean=round(float(lum.mean() * 255), 1), p02=round(float(np.percentile(lum, 2) * 255), 1),
                p98=round(float(np.percentile(lum, 98) * 255), 1),
                dark=round(float((lum < 0.12).mean() * 100), 2), white=round(float((lum > 0.97).mean() * 100), 2))


def main():
    out = opt("--out", os.path.join(os.environ.get("IRONART_OUT", "/tmp/ironart"), "scenes"))
    os.makedirs(out, exist_ok=True)
    only = opt("--only")
    names = [n.strip() for n in only.split(",")] if only else ORDER
    preview = opt("--preview", None, float)
    spp = opt("--spp", None, int)
    save = "--no-save" not in scene.args()
    infos = []
    t0 = time.time()
    for n in names:
        infos.append(run_one(n, out, preview, spp, save))
    masters = [i["outputs"]["master"]["path"] for i in infos if "master" in i.get("outputs", {})]
    if masters and save and not preview and "--no-manifest" not in scene.args():
        from ironart.scenes_look import ART_SOURCE, REPO, manifest_add
        rel = [os.path.relpath(os.path.join(REPO, p), ART_SOURCE).replace(os.sep, "/") for p in masters]
        ver, added = manifest_add(rel)
        print("[scenes] ArtSource/manifest.json version %d (+%d files)" % (ver, len(added)))
    tl = os.path.join(out, "timings.json")
    old = {}
    if os.path.exists(tl):
        try:
            old = json.load(open(tl))
        except ValueError:
            old = {}
    for i in infos:
        old[i["scene"] + ("_preview" if preview else "")] = i
    json.dump(old, open(tl, "w"), indent=1)
    print("[scenes] %d scene(s) in %.1fs" % (len(infos), time.time() - t0))


if __name__ == "__main__":
    main()
