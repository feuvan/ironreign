"""Icons family: regenerate every Icon_* deterministically.

    Tools/BlenderArt/render.sh Tools/BlenderArt/icons/build.py [--only A,B,...] [--preview]
                                                              [--spp N] [--no-save] [--out DIR]
                                                              [--module comp_test]
    python3 Tools/BlenderArt/icons/build.py --sheets [--out DIR]   # review sheets only

Outputs
    Content/Data/Art/UI/Icon_<Name>.png          64 x 64 RGBA (manifest-validated)
    ArtSource/UI/Icons/Icon_<Name>@2x.png        128 x 128 RGBA master (same render)
    ArtSource/manifest.json                      the @2x masters are listed (version bumped)
    $OUT/raw/<Name>_raw.png                      512 px raw render (straight alpha)
    $OUT/final/<Name>_{64,128}.png               finished icons (also when --no-save)
    $OUT/sheet_*.png, timings.json, qa.json      review sheets, timings, QA measurements

Every icon is a 3D still life (``comp_*.py`` builders) shot with the family camera and light rig
of :mod:`ironart.icons_look`, rendered once at 512 px (Cycles CPU, no denoiser) and finished in
numpy (outline, drop shadow, Lanczos to 128 and 64).  ``--preview`` renders 256 px at low
samples (fast look-dev; never saved to the game).
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
for p in (HERE, TOOLS):
    if p not in sys.path:
        sys.path.insert(0, p)

from ironart import icons_look as look  # noqa: E402
from ironart import post  # noqa: E402

DEFAULT_OUT = os.path.join(os.environ.get("IRONART_OUT", "/tmp/ironart"), "icons")
MODULES = ("comp_a", "comp_b", "comp_c", "comp_d")


def _args(argv):
    a = dict(only=None, preview=False, spp=None, save=True, out=DEFAULT_OUT, sheets=False,
             modules=None, seed=0)
    i = 0
    while i < len(argv):
        k = argv[i]
        if k == "--only":
            a["only"] = argv[i + 1].split(","); i += 1
        elif k == "--preview":
            a["preview"] = True
        elif k == "--spp":
            a["spp"] = int(argv[i + 1]); i += 1
        elif k == "--no-save":
            a["save"] = False
        elif k == "--out":
            a["out"] = argv[i + 1]; i += 1
        elif k == "--sheets":
            a["sheets"] = True
        elif k == "--module":
            a["modules"] = argv[i + 1].split(","); i += 1
        else:
            raise SystemExit("unknown argument %r" % k)
        i += 1
    if a["preview"]:
        a["save"] = False
    return a


def registry(modules=None):
    import importlib
    reg = {}
    for m in modules or MODULES:
        mod = importlib.import_module(m)
        for name in look.ICONS:
            fn = getattr(mod, name, None)
            if fn is not None:
                reg[name] = fn
    return reg


def render_icon(name, fn, a, times):
    import bpy
    from ironart import scene
    from common import M
    t0 = time.time()
    scene.reset(seed=11)
    look.setup(preview=a["preview"], spp=a["spp"])
    cam = look.camera()
    spec = fn(M(), cam)
    objs = [o for o in spec["objs"] if o.type == "MESH"]
    look.fit(cam, objs, spec.get("fill", 1.0), offset=spec.get("offset", (0.0, 0.0)))
    look.rig(cam, objs)
    t1 = time.time()
    raw_path = os.path.join(a["out"], "raw", "%s_raw.png" % name)
    secs = scene.render(raw_path, quiet=True)
    raw = post.load(raw_path)
    icons = {s: look.compose(raw, s) for s in look.RECIPE["sizes"]}
    t2 = time.time()
    tris = 0
    dg = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        me = o.evaluated_get(dg).to_mesh()
        me.calc_loop_triangles()
        tris += len(me.loop_triangles)
        o.evaluated_get(dg).to_mesh_clear()
    times[name] = dict(build=round(t1 - t0, 2), render=round(secs, 2),
                       finish=round(time.time() - t2, 2), total=round(time.time() - t0, 2),
                       tris=tris)
    print("[icons] %-12s build %.1fs render %.1fs total %.1fs (%d tris)"
          % (name, t1 - t0, secs, time.time() - t0, tris))
    return raw, icons


def main():
    from ironart import scene
    a = _args(scene.args())
    os.makedirs(a["out"], exist_ok=True)
    if a["sheets"]:
        return sheets(a["out"])
    reg = registry(a["modules"])
    names = [n for n in (a["only"] or look.ICONS) if n in reg]
    missing = [n for n in (a["only"] or look.ICONS) if n not in reg]
    if missing:
        print("[icons] no builder yet for: %s" % ", ".join(missing))
    times, qa_rows, saved = {}, {}, []
    tpath = os.path.join(a["out"], "timings.json")
    if os.path.exists(tpath):
        try:
            times = json.load(open(tpath))
        except ValueError:
            times = {}
    fails = []
    for name in names:
        raw, icons = render_icon(name, reg[name], a, times)
        for s, img in icons.items():
            post.save(img, os.path.join(a["out"], "final", "%s_%d.png" % (name, s)))
        q = look.qa(name, raw, icons, strict=False)
        qa_rows[name] = [(n, ok, t) for n, ok, t in q.rows]
        if not all(ok for _, ok, _ in q.rows):
            fails.append(name)
        if a["save"]:
            rep = look.save_icon(name, icons)
            saved.append("%s/Icon_%s@2x.png" % (look.MASTER_DIR, name))
            for k, (p, size, kb) in rep.items():
                print("[icons] wrote %s %dx%d %.1f kB" % (os.path.relpath(p, look.REPO), size[0],
                                                          size[1], kb))
        with open(tpath, "w") as f:
            json.dump(times, f, indent=1, sort_keys=True)
    with open(os.path.join(a["out"], "qa_last.json"), "w") as f:
        json.dump(qa_rows, f, indent=1)
    if saved:
        ver, added = look.manifest_add(saved)
        print("[icons] ArtSource/manifest.json version %d (+%d files)" % (ver, len(added)))
    sheets(a["out"])
    if fails:
        print("[icons] QA FAILED: %s" % ", ".join(fails))
        if a["save"]:
            raise SystemExit(1)


def sheets(out):
    """Review sheets from whatever finished icons exist in ``out/final``."""
    items = []
    for name in look.ICONS:
        p64 = os.path.join(out, "final", "%s_64.png" % name)
        p128 = os.path.join(out, "final", "%s_128.png" % name)
        if os.path.exists(p64) and os.path.exists(p128):
            items.append((name, {64: post.load(p64), 128: post.load(p128)}))
    if not items:
        return
    look.review_sheet(items, os.path.join(out, "sheet_32_64.png"), sizes=(32, 64), cols=8)
    look.review_sheet(items, os.path.join(out, "sheet_128.png"), sizes=(128,),
                      bgs=("parchment", "lacquer"), cols=8)
    print("[icons] sheets -> %s" % out)


if __name__ == "__main__":
    main()
