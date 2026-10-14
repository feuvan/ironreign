"""World Models family - ONE entry point that regenerates every output deterministically (gongbi look).

    Tools/BlenderArt/render.sh Tools/BlenderArt/world_models/build.py [--preview] [--no-render] [--skip-sprites]
                               [--reuse-leaves]
                               [only: trees cities props sprites | Tree_Pine City_2 Banner ...]

Order (each step uses the previous one's files):
    trees.py    Tree_Pine / Tree_Broad / Tree_Bamboo .glb (+ gongbi leaf atlases and bark tiles the
                cities and the sect reuse)
    cities.py   City_1 / City_2 / City_3 .glb
    props.py    Banner / Flag / Sect .glb (Sect reuses the tree textures)
    sprites.py  Content/Data/Art/Map/City_1..3.png, Sect.png, Banner.png (+ BannerGlyphArea.txt), Flag.png
                as jiehua paintings rendered from the GLBs
then writes Content/Data/Art3D/Models.json, adds the GLBs to ArtSource/manifest.json (locked
read-modify-write, version bumped) and assembles the gongbi review sheet of the nine models.

Outputs: ArtSource/Models/*.glb, Content/Data/Art3D/Models.json and Content/Data/Art/Map/*
(committed); previews, textures, contact sheets and report.json in $WORLD_MODELS_OUT or
$IRONART_OUT/world_models (scratch).  Everything is seeded: re-running gives the same geometry and
textures.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json  # noqa: E402

import common  # noqa: E402
import cities  # noqa: E402
import review  # noqa: E402
import props  # noqa: E402
import sprites  # noqa: E402
import trees  # noqa: E402

from ironart import world_bake as WB  # noqa: E402

MODELS = ["Tree_Pine", "Tree_Broad", "Tree_Bamboo", "City_1", "City_2", "City_3", "Banner", "Flag", "Sect"]
#: Content/Data/Art3D/Models.json (DESIGN.md 12.3, IronWorldAssets.h).  frontYaw = the yaw that turns
#: the imported model's front towards UE +Y.  Blender's front (-Y) is exported as glTF +Z
#: (export_yup: Blender (x, y, z) -> glTF (x, z, -y)), and Unreal's glTF import converts glTF
#: (x, y, z) -> UE (x, z, y) (GLTFCore ConvertVec3: "Y swapped with Z", the right- to left-handed
#: swap), so the front already lands on UE +Y (map south, facing the default camera): frontYaw 0.
#: If the editor's import ever measures a different axis map (the import's "gltfAxes" note), fix it
#: here at runtime: 90 = front imported on +X, 180 = on -Y, -90 = on -X.  Every model is authored at
#: its exaggerated map size (scale 1).
FRONT_YAW = 0
MODELS_JSON = {"frontYaw": FRONT_YAW, "models": {m: {"scale": 1.0} for m in MODELS}}


def write_models_json():
    from ironart import REPO_DIR
    p = os.path.join(REPO_DIR, "Content", "Data", "Art3D", "Models.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(MODELS_JSON, f, indent=2)
        f.write("\n")
    return p


def main():
    fl = common.flags()
    argv0 = list(sys.argv)
    want = set(fl["names"])
    t0 = time.time()
    times = {}

    def on(step, *names):
        return not want or step in want or any(n in want for n in names)

    if on("trees", "Tree_Pine", "Tree_Broad", "Tree_Bamboo"):
        sys.argv = [sys.argv[0], "--"] + [n.replace("Tree_", "") for n in want if n.startswith("Tree_")] + \
            (["--preview"] if fl["preview"] else []) + ([] if fl["render"] else ["--no-render"]) + \
            (["--reuse-leaves"] if "--reuse-leaves" in argv0 else [])
        t = time.time()
        trees.main()
        times["trees"] = time.time() - t
    if on("cities", "City_1", "City_2", "City_3"):
        t = time.time()
        tiers = [int(n[-1]) for n in want if n.startswith("City_")] or [1, 2, 3]
        for tier in tiers:
            cities.build_city(tier, fl["preview"], fl["render"])
        times["cities"] = time.time() - t
    if on("props", "Banner", "Flag", "Sect"):
        t = time.time()
        rep = common.Report()
        for n in [n for n in ("Banner", "Flag", "Sect") if not want or "props" in want or n in want]:
            r = props.build_sect(fl["preview"], fl["render"]) if n == "Sect" else \
                props.build_banner(n, fl["preview"], fl["render"])
            name, path, info, probs, secs, tr = r
            rep.add(name, glb=path, kb=round(info["kb"], 1), triangles=info["triangles"], size_m=info["size"],
                    bounds=info["bounds"], base_centre=info.get("base_centre"),
                    images=[(i["name"], i["size"], round(i["kb"])) for i in info["images"]],
                    materials=info["materials"], problems=probs, total_s=round(secs, 1), render_s=round(tr, 1))
            if probs:
                raise SystemExit("%s failed verification: %s" % (name, probs))
        rep.save()
        times["props"] = time.time() - t
    if on("sprites") and "--skip-sprites" not in sys.argv:
        t = time.time()
        rep = common.Report()
        names = [n for n in sprites.SPRITES if not want or "sprites" in want or n in want]
        for n in names:
            rep.add(n + ".png", **sprites.render_sprite(n, common.out("sprites")))
        rep.save()
        times["sprites"] = time.time() - t
    print("[ironart] wrote", write_models_json())
    glbs = [os.path.join(common.MODELS_DIR, m + ".glb") for m in MODELS
            if os.path.isfile(os.path.join(common.MODELS_DIR, m + ".glb"))]
    v = WB.manifest_add(glbs)
    prev = [os.path.join(common.out("previews"), "%s_gongbi.png" % m) for m in
            ("City_1", "City_2", "City_3", "Sect", "Banner", "Flag", "Tree_Pine", "Tree_Broad", "Tree_Bamboo")]
    if all(os.path.isfile(p) for p in prev):
        print("[ironart] review sheet", review.sheet(prev, os.path.join(common.out("previews"),
                                                                          "World_Models_gongbi_sheet.png")))
    times["total"] = time.time() - t0
    print("[ironart] ArtSource/manifest.json version %d (%d World Models files)" % (v, len(glbs)))
    print("[ironart] TIMES", {k: round(x, 1) for k, x in times.items()})
    rep = common.Report()
    rep.add("_build", times={k: round(x, 1) for k, x in times.items()}, manifest_version=v)
    rep.save()


if __name__ == "__main__":
    main()
