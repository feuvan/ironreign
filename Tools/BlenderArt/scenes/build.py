"""Illustrated Scenes family - one entry script regenerating every output deterministically.

    Tools/BlenderArt/render.sh Tools/BlenderArt/scenes/build.py [options]

Outputs (DESIGN.md section 8 manifest + @2x masters in ArtSource):

    Content/Data/Art/UI/Title_Background.png   1920x1080   ArtSource/UI/Title_Background@2x.png  3840x2160
    Content/Data/Art/Events/<Name>.png         640x360     ArtSource/Events/<Name>@2x.png        1280x720
    Content/Data/Art/Duel/Background.png       1280x720    (rendered 2x and downsampled)

Options
    --only A,B      scenes to build (Title, Court, Battle, Harvest, Disaster, Wanderer, Sect,
                    Bandits, Envoy, Festival, Plague, Flood, Omen, Duel)
    --preview       half-size, low samples, writes only to the preview folder
    --spp N         override samples          --scale F   override master scale (preview)
    --out DIR       preview / intermediates folder (default $IRONART_OUT/scenes)
    --no-save       do not write Content/Data or ArtSource
    --no-manifest   do not touch ArtSource/manifest.json (batch the update yourself)

Each scene module ``sc_<name>.py`` defines ``SPEC`` (name, art, master, size, ss, spp, seed) and
``build(r)`` (builds geometry, lights, camera and sky; returns a dict with ``camera``, optional
``beams`` = world point of the light source for compositor sun beams, ``grade`` and compositor
overrides).  Look numbers: ``ironart/scenes_look.py`` (RECIPE) + each scene's grade.
"""

import importlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from ironart import scene, scenes_look as L, scenes_sky as S  # noqa: E402

ORDER = ["Title", "Court", "Battle", "Harvest", "Disaster", "Wanderer", "Sect", "Bandits", "Envoy",
         "Festival", "Plague", "Flood", "Omen", "Duel"]


def opt(name, default=None, cast=str):
    a = scene.args()
    if name in a:
        i = a.index(name)
        if i + 1 < len(a):
            return cast(a[i + 1])
    return default


def run_one(name, out_dir, preview=False, spp=None, scale=None, save=True):
    import bpy
    mod = importlib.import_module("sc_" + name.lower())
    spec = dict(mod.SPEC)
    t = L.Timer()
    scene.reset(seed=spec.get("seed", 1))
    w, h = spec["size"]
    ss = spec.get("ss", 1)
    if preview:
        k = scale or 0.5
        w, h, ss = int(w * k), int(h * k), 1
    r = L.setup(w, h, ss=ss, spp=spp or (None if not preview else spec.get("preview_spp", 16)),
                preview=preview, seed=spec.get("seed", 1), look=spec.get("look", L.RECIPE["look"]),
                light_paths=spec.get("light_paths"))
    if not preview and spec.get("spp") and not spp:
        bpy.context.scene.cycles.samples = spec["spp"]
        r["samples"] = spec["spp"]
    r["preview"] = preview
    r["name"] = name
    r["brush_scale"] = float(w) / float(spec["size"][0])
    d = mod.build(r) or {}
    t.lap("build")
    n_fog = S.apply_fog()
    cam = d.get("camera") or bpy.context.scene.camera
    beams = None
    if d.get("beams") is not None:
        x, y, z = L.screen_pos(cam, d["beams"])
        if z > 0:
            beams = (x, y)
    comp_kw = dict(beams_source=beams, beams=d.get("beams_cfg"), glow=d.get("glow"),
                   kuwahara=d.get("kuwahara"), lens=d.get("lens", 0.0))
    pdir = os.path.join(out_dir, "%s_passes" % name)
    os.makedirs(pdir, exist_ok=True)
    L.passes_compositor(pdir)
    t0 = time.time()
    bpy.context.scene.render.filepath = os.path.join(pdir, "composite.png")
    scene.check_render_settings()
    bpy.ops.render.render(write_still=False)
    secs = time.time() - t0
    print("[scenes] %s rendered %dx%d %d spp in %.1fs" % (name, bpy.context.scene.render.resolution_x,
                                                          bpy.context.scene.render.resolution_y,
                                                          r["samples"], secs))
    t.lap("render")
    C = L.load_exr(os.path.join(pdir, "beauty0001.exr"))
    dn = d.get("denoise", {})
    if dn is not False:
        A_ = L.load_exr(os.path.join(pdir, "albedo0001.exr"))
        N_ = L.load_exr(os.path.join(pdir, "normal0001.exr"))
        Z_ = L.load_exr(os.path.join(pdir, "depth0001.exr"))
        D = L.denoise(C, A_, N_, Z_[..., :1], **(dn or {}))
    else:
        D = C[..., :3]
    t.lap("denoise")
    dexr = L.save_exr(D, os.path.join(pdir, "denoised.exr"))
    raw = os.path.join(out_dir, "%s_raw.png" % name)
    L.post_render(dexr, raw, r, depth_path=os.path.join(pdir, "depth0001.exr"), **comp_kw)
    t.lap("post")
    img = L.load16(raw)
    fin = L.finish(img, d.get("grade"), seed=spec.get("seed", 1), master_scale=img.shape[1] / 1280.0)
    if ss > 1:
        fin = L.downsample(fin, (fin.shape[1] // ss, fin.shape[0] // ss))
    t.lap("finish")
    rep = {}
    pv = os.path.join(out_dir, "preview")
    os.makedirs(pv, exist_ok=True)
    L.save_png(L.to_rgba8(fin, spec.get("seed", 1)), os.path.join(pv, "%s_master.png" % name))
    if save and not preview:
        rep = L.save_outputs(fin, spec["art"], spec.get("master"), preview_dir=pv,
                             seed=spec.get("seed", 1))
    else:
        one = L.downsample(fin, (fin.shape[1] // 2, fin.shape[0] // 2)) if spec.get("master") else fin
        L.save_png(L.to_rgba8(one, spec.get("seed", 1)), os.path.join(pv, "%s.png" % name))
    t.lap("save")
    q = L.qa(fin if not spec.get("master") else L.downsample(fin, (fin.shape[1] // 2, fin.shape[0] // 2)), name)
    print("[scenes] QA %s %s" % (name, json.dumps(q)))
    info = dict(scene=name, render_s=round(secs, 1), times=t.t, samples=r["samples"], qa=q,
                render_size=[bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y],
                fogged_materials=n_fog,
                outputs={k: dict(path=os.path.relpath(p, L.REPO), size=list(sz), kB=round(kb, 1))
                         for k, (p, sz, kb) in rep.items()})
    print("[scenes] %s" % json.dumps(info))
    return info


def main():
    out = opt("--out", os.path.join(os.environ.get("IRONART_OUT", "/tmp/ironart"), "scenes"))
    os.makedirs(out, exist_ok=True)
    only = opt("--only")
    names = [n.strip() for n in only.split(",")] if only else ORDER
    preview = "--preview" in scene.args()
    spp = opt("--spp", None, int)
    scale = opt("--scale", None, float)
    save = "--no-save" not in scene.args()
    infos = []
    t0 = time.time()
    for n in names:
        infos.append(run_one(n, out, preview, spp, scale, save))
    masters = [i["outputs"]["master"]["path"] for i in infos if "master" in i.get("outputs", {})]
    if masters and save and not preview and "--no-manifest" not in scene.args():
        rel = [os.path.relpath(os.path.join(L.REPO, p), L.ART_SOURCE).replace(os.sep, "/") for p in masters]
        ver, added = L.manifest_add(rel)
        print("[scenes] ArtSource/manifest.json version %d (+%d files)" % (ver, len(added)))
    tl = os.path.join(out, "timings.json")
    old = {}
    if os.path.exists(tl):
        try:
            old = json.load(open(tl))
        except ValueError:
            old = {}
    for i in infos:
        old[i["scene"]] = i
    json.dump(old, open(tl, "w"), indent=1)
    print("[scenes] %d scene(s) in %.1fs" % (len(infos), time.time() - t0))


if __name__ == "__main__":
    main()
