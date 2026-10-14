"""Icons family (gongbi 工笔): regenerate every Icon_* deterministically.

    Tools/BlenderArt/render.sh Tools/BlenderArt/icons/build.py [--only A,B,...] [--preview]
                                                              [--no-save] [--out DIR]
    python3 Tools/BlenderArt/icons/build.py --recomp [--only ...] [--out DIR] [--save]
                                            # re-run the 2D finishing from the saved passes
    python3 Tools/BlenderArt/icons/build.py --sheets [--out DIR]   # review sheets only

Outputs
    Content/Data/Art/UI/Icon_<Name>.png          64 x 64 RGBA (manifest-validated)
    ArtSource/UI/Icons/Icon_<Name>@2x.png        128 x 128 RGBA master (same render)
    ArtSource/manifest.json                      the @2x masters are listed (version bumped)
    $OUT/passes/<Name>.npz                       render passes (float16) for --recomp
    $OUT/final/<Name>_{64,128}.png               finished icons (also with --no-save)
    $OUT/sheet_*.png, context_*.png              review sheets (20/26/32/64 px on parchment,
                                                 dark panel, cinnabar button; in-UI mock)
    $OUT/timings.json, qa_last.json              render times, QA measurements

Every icon is a subject modelled in 3D (``comp_*.py``: ``<Name>(M, cam) -> dict(objs, fill,
offset)``), rendered flat with the family camera, pigments and Freestyle ink of
:mod:`ironart.icons_gongbi` at 512 px, and finished in numpy (分染, ink, silk halo, Lanczos to
128 and 64).  ``--preview`` renders 256 px at low samples (look-dev only, never saved).
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

from ironart import icons_gongbi as gb  # noqa: E402

DEFAULT_OUT = os.path.join(os.environ.get("IRONART_OUT", "/tmp/ironart"), "icons")
MODULES = ("comp_docs", "comp_war", "comp_realm", "comp_town")


def _args(argv):
    a = dict(only=None, preview=False, spp=None, save=True, out=DEFAULT_OUT, sheets=False,
             recomp=False, modules=None)
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
        elif k == "--save":
            a["save"] = True
        elif k == "--out":
            a["out"] = argv[i + 1]; i += 1
        elif k == "--sheets":
            a["sheets"] = True
        elif k == "--recomp":
            a["recomp"] = True
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
        try:
            mod = importlib.import_module(m)
        except ImportError as e:
            if m in MODULES:
                print("[icons] module %s not available: %s" % (m, e))
                continue
            raise
        for name in gb.ICONS:
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
    gb._MAT_INDEX[0] = 0
    sc = gb.setup(preview=a["preview"], spp=a["spp"])
    cam = gb.camera()
    gb.collections()
    spec = fn(M(), cam)
    objs = [o for o in spec["objs"] if o.type == "MESH"]
    # every mesh not already sorted into an ink collection gets the default ink
    cols = gb.collections()
    inked = set()
    for c in cols.values():
        inked.update(c.objects)
    gb.put([o for o in objs if o not in inked], "ink")
    for i, o in enumerate(objs):
        o.pass_index = i + 1
    gb.fit(cam, objs, spec.get("fill", 1.0), offset=spec.get("offset", (0.0, 0.0)))
    R = sc.render.resolution_x
    gb.setup_ink(R / 64.0)
    t1 = time.time()
    pdir = os.path.join(a["out"], "exr", name)
    ps, secs = gb.render_passes(pdir)
    gb.save_npz(ps, os.path.join(a["out"], "passes", "%s.npz" % name))
    icons, painted = gb.compose(ps, seed=len(name))
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
    print("[icons] %-12s build %.1fs render %.1fs finish %.1fs total %.1fs (%d tris)"
          % (name, t1 - t0, secs, time.time() - t2, time.time() - t0, tris))
    return icons, painted


def _finish_one(name, icons, painted, a, qa_rows, saved, fails):
    for s, img in icons.items():
        gb.save_png(img, os.path.join(a["out"], "final", "%s_%d.png" % (name, s)))
    gb.save_png(painted, os.path.join(a["out"], "painted", "%s.png" % name))
    rows = gb.qa(name, painted, icons)
    qa_rows[name] = rows
    bad = [t for _, ok, t in rows if not ok]
    if bad:
        fails.append(name)
        print("[icons] QA %s: %s" % (name, "; ".join(bad)))
    if a["save"]:
        rep = gb.save_icon(name, icons)
        saved.append("%s/Icon_%s@2x.png" % (gb.MASTER_DIR, name))
        for k, (p, size, kb) in rep.items():
            print("[icons] wrote %s %dx%d %.1f kB" % (os.path.relpath(p, gb.REPO), size[0],
                                                      size[1], kb))


def main(argv):
    a = _args(argv)
    os.makedirs(a["out"], exist_ok=True)
    if a["sheets"]:
        return sheets(a["out"])
    qa_rows, saved, fails = {}, [], []
    if a["recomp"]:
        names = a["only"] or list(gb.ICONS)
        for name in names:
            p = os.path.join(a["out"], "passes", "%s.npz" % name)
            if not os.path.exists(p):
                continue
            t0 = time.time()
            icons, painted = gb.compose(gb.load_npz(p), seed=len(name))
            print("[icons] recomposed %s in %.1fs" % (name, time.time() - t0))
            _finish_one(name, icons, painted, a, qa_rows, saved, fails)
    else:
        reg = registry(a["modules"])
        names = [n for n in (a["only"] or gb.ICONS) if n in reg]
        missing = [n for n in (a["only"] or gb.ICONS) if n not in reg]
        if missing:
            print("[icons] no builder yet for: %s" % ", ".join(missing))
        times = {}
        tpath = os.path.join(a["out"], "timings.json")
        if os.path.exists(tpath):
            try:
                times = json.load(open(tpath))
            except ValueError:
                times = {}
        for name in names:
            icons, painted = render_icon(name, reg[name], a, times)
            _finish_one(name, icons, painted, a, qa_rows, saved, fails)
            with open(tpath, "w") as f:
                json.dump(times, f, indent=1, sort_keys=True)
    with open(os.path.join(a["out"], "qa_last.json"), "w") as f:
        json.dump({k: [[l, bool(ok), t] for l, ok, t in v] for k, v in qa_rows.items()}, f,
                  indent=1)
    if saved:
        ver, added = gb.manifest_add(saved)
        print("[icons] ArtSource/manifest.json version %d (+%d files)" % (ver, len(added)))
    sheets(a["out"])
    if fails:
        print("[icons] QA FAILED: %s" % ", ".join(fails))
        if a["save"]:
            raise SystemExit(1)


def sheets(out):
    """Review sheets from whatever finished icons exist in ``out/final``."""
    items = []
    for name in gb.ICONS:
        p64 = os.path.join(out, "final", "%s_64.png" % name)
        p128 = os.path.join(out, "final", "%s_128.png" % name)
        if os.path.exists(p64) and os.path.exists(p128):
            items.append((name, {64: gb.load_png(p64), 128: gb.load_png(p128)}))
    if not items:
        return
    gb.review_sheet(items, os.path.join(out, "sheet_small.png"), sizes=(20, 26, 32, 64),
                    bgs=("parchment", "paneldark", "button"), cols=5)
    gb.review_sheet(items, os.path.join(out, "sheet_128.png"), sizes=(128,),
                    bgs=("parchment", "lacquer"), cols=8)
    try:
        import review
        review.context_mock(items, os.path.join(out, "context_mock.png"))
    except ImportError:
        pass
    print("[icons] sheets -> %s" % out)


if __name__ == "__main__":
    try:
        import bpy  # noqa: F401
        from ironart import scene
        main(scene.args())
    except ImportError:
        main(sys.argv[1:])
