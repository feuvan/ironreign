"""Tree_Pine / Tree_Broad / Tree_Bamboo -> ArtSource/Models/Tree_*.glb (DESIGN.md 12.3).

    Tools/BlenderArt/render.sh Tools/BlenderArt/world_models/trees.py [Pine|Broad|Bamboo ...] [--preview]

Per tree: leaf atlas rendered from modelled leaves (world_trees.leaf_atlas), seamless bark baked
from a periodic procedural (bark_texture), card-and-limb model (< 3k triangles) with canopy
normals, two materials (Bark opaque, Leaves alpha-MASK double sided), GLB export, re-import
verification and review renders of the re-imported file.
"""

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401

from ironart import scene, world_bake as WB, world_render as WR, world_trees as WT  # noqa: E402

SPECS = {
    # name: (leaf kind, bark kind, height m, builder, seed, leaf atlas px, bark px)
    "Pine": ("pine", "pine", 26.0, WT.pine, 31, 1024, (512, 1024)),
    "Broad": ("broad", "broad", 22.0, WT.broadleaf, 17, 1024, (512, 1024)),
    "Bamboo": ("bamboo", "bamboo", 18.0, WT.bamboo, 23, 1024, (256, 1024)),
}
BARK_EXT = {"pine": (1.6, 3.2), "broad": (1.6, 3.2), "bamboo": (0.6, 3.0)}


def textures(name, tex_dir, preview=False, reuse=False, reuse_leaves=False):
    """Leaf atlas + bark tile for ``name``.  ``reuse``: take both from ``tex_dir`` when present;
    ``reuse_leaves``: only the (slow) leaf atlas."""
    leaf, bark, H, fn, seed, lpx, bpx = SPECS[name]
    if reuse:
        keys = {"base": "Base", "normal": "Normal", "orm": "ORM"}
        la = {k: os.path.join(tex_dir, "%s_Leaves_%s.png" % (leaf.capitalize(), v)) for k, v in keys.items()}
        bt = {k: os.path.join(tex_dir, "%s_Bark_%s.png" % (bark.capitalize(), v)) for k, v in keys.items()}
        if all(os.path.isfile(p) for p in list(la.values()) + list(bt.values())):
            return la, bt
    lp = {k: os.path.join(tex_dir, "%s_Leaves_%s.png" % (leaf.capitalize(), v))
          for k, v in {"base": "Base", "normal": "Normal", "orm": "ORM"}.items()}
    if reuse_leaves and all(os.path.isfile(p) for p in lp.values()):
        la = lp
    else:
        la = WT.leaf_atlas(leaf, tex_dir, size=512 if preview else lpx, ss=2, seed=seed)
    bt = WT.bark_texture(bark, tex_dir, size=(bpx[0] // 2, bpx[1] // 2) if preview else bpx,
                         ext=BARK_EXT[bark])
    return la, bt


def build(name, la, bt, seed=None):
    """Model in the current (reset) scene; returns the object."""
    leaf, bark, H, fn, sd, _, _ = SPECS[name]
    rng = random.Random(seed or sd)
    tb = WT.TreeBuilder(tile=BARK_EXT[bark])
    fn(tb, rng, H=H)
    mats = {"Bark": WB.pbr_material("Bark", maps=bt, roughness=0.9),
            "Foliage": WB.pbr_material("Leaves", maps=la, alpha=True, double_sided=True)}
    return tb.build("Tree_" + name, mats)


def main():
    fl = common.flags()
    names = [n for n in fl["names"] if n in SPECS] or list(SPECS)
    rep = common.Report()
    produced = []
    for name in names:
        t0 = time.time()
        tex_dir = common.out("textures")
        la, bt = textures(name, tex_dir, fl["preview"], "--reuse" in sys.argv, "--reuse-leaves" in sys.argv)
        scene.reset(SPECS[name][4])
        obj = build(name, la, bt)
        tris = WB.tri_count(obj)
        path = os.path.join(common.MODELS_DIR, "Tree_%s.glb" % name)
        WB.export_glb(obj, path)
        info, probs = WB.verify_glb(path, height=SPECS[name][2], max_tris=3000)
        print("[ironart] Tree_%s: %d tris, size %s, materials %s" % (name, tris, info["size"],
                                                                    [m["name"] for m in info["materials"]]))
        for p in probs:
            print("[ironart] PROBLEM Tree_%s: %s" % (name, p))
        t_build = time.time() - t0
        if fl["render"]:
            o = info["obj"]
            prev = common.out("previews")
            WR.beauty([o], os.path.join(prev, "Tree_%s_beauty.png" % name), res=(560, 560), samples=32,
                      pitch=28.0, yaw=-20.0, fill=0.95)
        rep.add("Tree_" + name, glb=path, kb=round(info["kb"], 1), triangles=info["triangles"],
                size_m=info["size"], images=[(i["name"], i["size"]) for i in info["images"]],
                materials=info["materials"], problems=probs, build_s=round(t_build, 1),
                total_s=round(time.time() - t0, 1))
        produced.append(path)
        if probs:
            raise SystemExit("Tree_%s failed verification: %s" % (name, probs))
    rep.save()
    return produced


if __name__ == "__main__":
    main()
