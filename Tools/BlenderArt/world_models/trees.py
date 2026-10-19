"""Tree_Pine / Tree_Broad / Tree_Bamboo -> ArtSource/Models/Tree_*.glb (DESIGN.md 12.3), gongbi paint.

    Tools/BlenderArt/render.sh Tools/BlenderArt/world_models/trees.py [Pine|Broad|Bamboo ...] [--preview]
                               [--reuse | --reuse-leaves] [--no-render]

Per tree: gongbi leaf atlas (world_gongbi.leaf_atlas: broadleaf / bamboo rendered from modelled
leaves as malachite / azurite washes darkening to the leaf base with 双勾 ink outlines; pine pads
painted as ink-green needle wheels over a malachite wash cloud by world_gongbi_foliage), seamless
painted bark (world_gongbi.bark_texture: ink scale rings, dry-brush furrows, bamboo node rings),
the card-and-limb model of world_trees (< 3k triangles, canopy normals), two materials (Bark opaque, Leaves alpha-MASK double sided, matte ORM without AO), GLB
export, re-import verification and a gongbi review render of the re-imported file.
"""

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401

from ironart import scene, world_bake as WB, world_gongbi as WG, world_gongbi_render as GR  # noqa: E402
from ironart import world_trees as WT  # noqa: E402

#: the stand-alone map pine is fuller than the city prototypes (cities.py keeps WT.pine's defaults
#: so City_3 stays inside its triangle budget): 1.9x cards per pad, tighter pads, more tilted cards
PINE_FULL = dict(pad_density=1.9, pad_spread=0.34, tilt_every=3)
SPECS = {
    # name: (leaf kind, bark kind, height m, builder, seed, leaf atlas px, bark px)
    "Pine": ("pine", "pine", 26.0, lambda tb, rng, H: WT.pine(tb, rng, H=H, **PINE_FULL), 31, 1024, (512, 1024)),
    "Broad": ("broad", "broad", 22.0, WT.broadleaf, 17, 1024, (512, 1024)),
    "Bamboo": ("bamboo", "bamboo", 18.0, WT.bamboo, 23, 1024, (256, 1024)),
}
BARK_EXT = {"pine": (1.6, 3.2), "broad": (1.6, 3.2), "bamboo": (0.6, 3.0)}
KEYS = {"base": "Base", "normal": "Normal", "orm": "ORM"}


def tex_dir():
    """Gongbi textures live apart from the earlier realistic set (never mix the two)."""
    return common.out("textures_gongbi")


def textures(name, tdir=None, preview=False, reuse=False, reuse_leaves=False):
    """Leaf atlas + bark tile for ``name``.  ``reuse``: take both from the folder when present;
    ``reuse_leaves``: only the (slower) leaf atlas."""
    tdir = tdir or tex_dir()
    leaf, bark, H, fn, seed, lpx, bpx = SPECS[name]
    la = {k: os.path.join(tdir, "%s_Leaves_%s.png" % (leaf.capitalize(), v)) for k, v in KEYS.items()}
    bt = {k: os.path.join(tdir, "%s_Bark_%s.png" % (bark.capitalize(), v)) for k, v in KEYS.items()}
    if reuse and all(os.path.isfile(p) for p in list(la.values()) + list(bt.values())):
        return la, bt
    if not (reuse_leaves and all(os.path.isfile(p) for p in la.values())):
        la = WG.leaf_atlas(leaf, tdir, size=512 if preview else lpx, ss=3, seed=seed)
    bt = WG.bark_texture(bark, tdir, size=(bpx[0] // 2, bpx[1] // 2) if preview else bpx, ext=BARK_EXT[bark])
    return la, bt


def materials(name, la, bt, suffix=""):
    return {"Bark": WB.pbr_material("Bark" + suffix, maps=bt, roughness=WG.ROUGH),
            "Foliage": WB.pbr_material("Leaves" + suffix, maps=la, alpha=True, double_sided=True,
                                       roughness=WG.ROUGH)}


def build(name, la, bt, seed=None):
    """Model in the current (reset) scene; returns the object."""
    leaf, bark, H, fn, sd, _, _ = SPECS[name]
    rng = random.Random(seed or sd)
    tb = WT.TreeBuilder(tile=BARK_EXT[bark])
    fn(tb, rng, H=H)
    return tb.build("Tree_" + name, materials(name, la, bt))


def main():
    fl = common.flags()
    names = [n for n in fl["names"] if n in SPECS] or list(SPECS)
    rep = common.Report()
    produced = []
    for name in names:
        t0 = time.time()
        la, bt = textures(name, None, fl["preview"], "--reuse" in sys.argv, "--reuse-leaves" in sys.argv)
        t_tex = time.time() - t0
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
        tr = 0.0
        if fl["render"]:
            o = info["obj"]
            tr = GR.preview([o], os.path.join(common.out("previews"), "Tree_%s_gongbi.png" % name), res=(640, 640),
                            samples=16, pitch=24.0, yaw=-20.0, fill=0.9, ink_px=1.1)
        rep.add("Tree_" + name, glb=path, kb=round(info["kb"], 1), triangles=info["triangles"],
                size_m=info["size"], images=[(i["name"], i["size"]) for i in info["images"]],
                materials=info["materials"], problems=probs, textures_s=round(t_tex, 1), build_s=round(t_build, 1),
                render_s=round(tr, 1), total_s=round(time.time() - t0, 1))
        produced.append(path)
        if probs:
            raise SystemExit("Tree_%s failed verification: %s" % (name, probs))
    rep.save()
    return produced


if __name__ == "__main__":
    main()
