"""Battlefield and Units family - ONE entry point that regenerates every output deterministically.

    Tools/BlenderArt/render.sh Tools/BlenderArt/battle/build.py [--preview] [--no-render]
                               [steps: hexes units sprites fx background manifest boards]
                               [names: Plain Forest ... Infantry Cavalry Archer Base]

Order (each step uses the previous one's files):
    hexes.py       ArtSource/Models/Hex_<Terrain>.glb (13 terrains) + gongbi review renders
    units.py       ArtSource/Models/Unit_Infantry / Cavalry / Archer / Base .glb
    sprites2d.py   Content/Data/Art/Battle/Hex_*.png (from the GLBs), Hex_Fill / Hex_Outline,
                   Unit_*.png, Unit_Base.png
    fx.py          Content/Data/Art/Battle/Fx_Fire / Confuse / Rally / Hit.png
    background.py  Content/Data/Art/Battle/Background.png
then adds the GLBs to ArtSource/manifest.json (locked read-modify-write, version bumped) and renders
the review boards (3D board patches with units, 2D boards and contact sheets).

Outputs are committed (ArtSource/Models, Content/Data/Art/Battle); textures, previews and the
report.json go to $BATTLE_OUT or $IRONART_OUT/battle (scratch).  Everything is seeded.
"""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

from ironart import world_bake as WB  # noqa: E402

STEPS = ("hexes", "units", "sprites", "fx", "background", "manifest", "boards")


def glbs():
    names = ["Hex_" + t for t in common.TERRAINS] + ["Unit_" + u for u in common.UNITS] + ["Unit_Base"]
    return [os.path.join(common.MODELS_DIR, n + ".glb") for n in names
            if os.path.isfile(os.path.join(common.MODELS_DIR, n + ".glb"))]


def sub(script, args):
    """Run a step in a fresh Blender process (a clean scene and memory per step)."""
    here = os.path.dirname(os.path.abspath(__file__))
    cmd = [os.path.join(os.path.dirname(here), "render.sh"), os.path.join(here, script)] + args
    t = time.time()
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit("%s failed (exit %d)" % (script, r.returncode))
    return time.time() - t


def main():
    fl = common.flags()
    want = [s for s in fl["names"] if s in STEPS] or list(STEPS)
    names = [n for n in fl["names"] if n not in STEPS]
    flags = (["--preview"] if fl["preview"] else []) + ([] if fl["render"] else ["--no-render"])
    times = {}
    t0 = time.time()
    if "hexes" in want:
        times["hexes"] = sub("hexes.py", [n for n in names if n in common.TERRAINS] + flags)
    if "units" in want:
        times["units"] = sub("units.py", [n for n in names if n in common.UNITS + ("Base",)] + flags)
    if "sprites" in want:
        times["sprites"] = sub("sprites2d.py", names + (["--preview"] if fl["preview"] else []))
    if "fx" in want:
        t = time.time()
        import fx
        fx.main()
        times["fx"] = time.time() - t
    if "background" in want:
        t = time.time()
        import background
        background.main()
        times["background"] = time.time() - t
    v = None
    if "manifest" in want:
        files = glbs()
        v = WB.manifest_add(files)
        print("[battle] ArtSource/manifest.json version %d (%d battle models)" % (v, len(files)))
    if "boards" in want and fl["render"]:
        t = time.time()
        sub("board.py", ["field", "siege"] + (["--preview"] if fl["preview"] else []))
        import sheet2d
        out = common.out("sprites2d")
        sheet2d.main(out)
        print("[battle] 2D review sheets in", out)
        times["boards"] = time.time() - t
    times["total"] = time.time() - t0
    rep = common.Report()
    rep.add("_build", times={k: round(x, 1) for k, x in times.items()}, manifest_version=v)
    rep.save()
    print("[battle] TIMES", {k: round(x, 1) for k, x in times.items()})


if __name__ == "__main__":
    main()
