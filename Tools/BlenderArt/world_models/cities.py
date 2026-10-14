"""City_1 / City_2 / City_3 -> ArtSource/Models/City_N.glb (DESIGN.md 12.3), gongbi paint.

    Tools/BlenderArt/render.sh Tools/BlenderArt/world_models/cities.py [1 2 3] [--preview] [--no-render]

Per tier (ironart.world_city): build every prototype the layout uses (world_kit geometry, the
gongbi W_* materials of ironart.world_gongbi), pack them into ONE atlas, rebuild the materials for
the measured texel density (ruled lines >= ~1 texel) and bake base / normal (no AO, no cavity
grime; ORM = (1, 0.9 matte, 0)), place the instances (shared UVs), paint the ground layout mask
and bake the ground plate (flat washes, no contact AO), add trees (Tree_* gongbi bark and leaf
textures), join everything into ONE mesh, export GLB, verify it by re-import, and render a gongbi
review image of the re-imported file (soft shadowless light + Freestyle ink, like Unreal's
painted post-process).  Needs the tree textures (run trees.py first; build.py does).

City_3 uses lighter tree prototypes (4 lobes x 12 cards, 4 pine tiers, 5-sided limbs) to stay
inside the 150k triangle budget; the buildings are unchanged.
"""

import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import trees as TR  # noqa: E402

import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from ironart import scene, world_bake as WB, world_city as WC, world_gongbi as WG  # noqa: E402
from ironart import world_gongbi_render as GR, world_trees as WT  # noqa: E402

#: tier: (footprint x, y m, height m, atlas px, ground px, seed)
TIER = {
    1: dict(footprint=(45.0, 45.0), height=22.0, atlas=2048, ground=1024, seed=101, trees="full"),
    2: dict(footprint=(76.0, 72.0), height=30.0, atlas=2048, ground=2048, seed=202, trees="full"),
    3: dict(footprint=(110.0, 121.0), height=40.0, atlas=2048, ground=2048, seed=303, trees="light"),
}
TREE_BASE_H = {"broad": 22.0, "pine": 26.0}
#: tree prototype detail: (broadleaf lobes, cards per lobe, limb sides), (pine tiers, limb sides)
TREE_LOD = {"full": ((5, 20, 6), (5, 6)), "light": ((4, 12, 5), (4, 5))}


def tree_protos(tex_dir=None, lod="full"):
    """Broadleaf + pine prototypes at full size (instances are scaled), with the Tree_* textures."""
    out = {}
    (lobes, cards, bsides), (tiers, psides) = TREE_LOD[lod]
    for kind, name in (("broad", "Broad"), ("pine", "Pine")):
        la, bt = TR.textures(name, tex_dir, reuse=True)
        tb = WT.TreeBuilder(tile=TR.BARK_EXT[kind])
        rng = random.Random(TR.SPECS[name][4] + 5)
        if kind == "broad":
            WT.broadleaf(tb, rng, H=TREE_BASE_H[kind], lobes=lobes, cards_per=cards, sides=bsides)
        else:
            WT.pine(tb, rng, H=TREE_BASE_H[kind], tiers=tiers, sides=psides)
        bn, ln = "Bark_" + name, "Leaves_" + name
        mats = {"Bark": bpy.data.materials.get(bn) or WB.pbr_material(bn, maps=bt, roughness=WG.ROUGH),
                "Foliage": bpy.data.materials.get(ln) or WB.pbr_material(ln, maps=la, alpha=True, double_sided=True,
                                                                         roughness=WG.ROUGH)}
        out[kind] = tb.build("T_" + kind, mats)
    return out


def build_city(tier, preview=False, render=True):
    cfg = TIER[tier]
    name = "City_%d" % tier
    t0 = time.time()
    times = {}
    scene.reset(cfg["seed"])
    tex_dir = TR.tex_dir()
    mats = WG.library()
    mats["Water"] = WG.water()
    P, lay = WC.TIERS[tier]()
    used = sorted(set(p for p, _ in lay.items))
    protos = {}
    for pn in used:
        protos[pn] = WB.build(P[pn](), "P_%s" % pn, mats)
    times["build"] = time.time() - t0
    tris_proto = {pn: WB.tri_count(o) for pn, o in protos.items()}
    # ---- atlas ----
    t1 = time.time()
    plist = [protos[pn] for pn in used]
    asz = 1024 if preview else cfg["atlas"]
    maps, atlas = WB.atlas_bake(plist, asz, tex_dir, "%s_Atlas" % name, preview=preview, ao=False, cavity=0.0,
                                samples=4, const={"rough": WG.ROUGH, "metal": 0.0}, jpeg=False,
                                on_unwrapped=lambda p: WG.relibrary(p, asz))
    density = WG.density()
    for o in plist:      # water faces keep their 0..1 quad UVs (no texture, valid tangents)
        idx = [i for i, m in enumerate(o.data.materials) if m and m.name.startswith("Water")]
        faces = [p.index for p in o.data.polygons if p.material_index in idx]
        if faces:
            WB.copy_uv(o, "MetreUV", "UV0", faces=faces)
    times["atlas"] = time.time() - t1
    # ---- instances + trees ----
    t1 = time.time()
    tp = tree_protos(tex_dir, cfg["trees"])
    placements = [(protos[pn], m) for pn, m in lay.items]
    for (kind, x, y, s, r) in lay.trees:
        placements.append((tp[kind], Matrix.Translation(Vector((x, y, 0.0))) @ Matrix.Rotation(r, 4, "Z")
                           @ Matrix.Scale(s, 4)))
    city = WB.instance_join(name, placements)
    for o in list(protos.values()) + list(tp.values()):
        bpy.data.objects.remove(o, do_unlink=True)
    times["assemble"] = time.time() - t1
    # ---- ground ----
    t1 = time.time()
    gsz = 512 if preview else cfg["ground"]
    mask = WC.ground_mask(lay, gsz, os.path.join(tex_dir, "%s_GroundMask.png" % name))
    gp = WC.ground_plate("%s_Ground" % name, lay)
    WG.set_density(gsz / (2.0 * max(lay.half)))
    gmat = WG.ground("W_Ground_%d" % tier, mask, lay.half)
    gp.data.materials[0] = gmat
    gmaps = WB.bake([gp], gsz, tex_dir, "%s_Ground" % name, ao=False, cavity=0.0, jpeg=False, margin=4,
                    const={"rough": WG.ROUGH, "metal": 0.0})
    gp.data.materials.clear()
    gp.data.materials.append(WB.pbr_material("Ground", maps=gmaps))
    me = gp.data
    me.uv_layers.remove(me.uv_layers["GroundUV"])
    times["ground"] = time.time() - t1
    # ---- join + export ----
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    gp.select_set(True)
    city.select_set(True)
    bpy.context.view_layer.objects.active = city
    bpy.ops.object.join()
    WB.merge_slots(city)
    WB.strip_uvs(city, "UV0")
    path = os.path.join(common.MODELS_DIR, "%s.glb" % name)
    WB.export_glb(city, path)
    info, probs = WB.verify_glb(path, footprint=cfg["footprint"], tint=False)
    print("[ironart] %s: %d tris, size %s, materials %s, images %s" % (
        name, info["triangles"], info["size"], [m["name"] for m in info["materials"]],
        [(i["name"], i["size"]) for i in info["images"]]))
    for p in probs:
        print("[ironart] PROBLEM %s: %s" % (name, p))
    times["export_verify"] = time.time() - t0 - sum(times.values())
    if render:
        t1 = time.time()
        o = info["obj"]
        prev = common.out("previews")
        GR.preview([o], os.path.join(prev, "%s_gongbi.png" % name), res=(1280, 800), samples=12 if preview else 24,
                   pitch=48.0, yaw=-20.0, fill=0.84, ink_px=1.1)
        times["render_preview"] = time.time() - t1
    rep = common.Report()
    rep.add(name, glb=path, kb=round(info["kb"], 1), triangles=info["triangles"], size_m=info["size"],
            bounds=info["bounds"], images=[(i["name"], i["size"], round(i["kb"])) for i in info["images"]],
            materials=info["materials"], prototypes=tris_proto, instances=len(lay.items), trees=len(lay.trees),
            atlas_px_per_m=round(density, 2),
            problems=probs, times={k: round(v, 1) for k, v in times.items()}, total_s=round(time.time() - t0, 1))
    rep.save()
    if probs:
        raise SystemExit("%s failed verification: %s" % (name, probs))
    return path


def main():
    fl = common.flags()
    tiers = [int(n) for n in fl["names"] if n.isdigit()] or [1, 2, 3]
    return [build_city(t, fl["preview"], fl["render"]) for t in tiers]


if __name__ == "__main__":
    main()
