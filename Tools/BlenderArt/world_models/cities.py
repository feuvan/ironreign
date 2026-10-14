"""City_1 / City_2 / City_3 -> ArtSource/Models/City_N.glb (DESIGN.md 12.3).

    Tools/BlenderArt/render.sh Tools/BlenderArt/world_models/cities.py [1 2 3] [--preview] [--no-render]

Per tier (ironart.world_city): build every prototype the layout uses (world_kit, W_* procedural
materials), Smart-UV-pack them into ONE atlas and bake base / ORM / normal (world_bake), place
the instances (shared UVs), paint the ground layout mask and bake the ground plate with the city
present (contact AO), add trees (Tree_* bark and leaf textures), join everything into ONE mesh,
export GLB, verify it by re-import, and render review images of the re-imported file.
Needs the tree textures (run trees.py first; build.py does).
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

from ironart import scene, world_bake as WB, world_city as WC, world_mats as WM, world_render as WR  # noqa: E402
from ironart import world_trees as WT  # noqa: E402

#: tier: (footprint x, y m, height m, atlas px, ground px, seed)
TIER = {
    1: dict(footprint=(45.0, 45.0), height=22.0, atlas=2048, ground=1024, seed=101),
    2: dict(footprint=(76.0, 72.0), height=30.0, atlas=2048, ground=2048, seed=202),
    3: dict(footprint=(110.0, 121.0), height=40.0, atlas=2048, ground=2048, seed=303),
}
TREE_BASE_H = {"broad": 22.0, "pine": 26.0}


def tree_protos(tex_dir):
    """Broadleaf + pine prototypes at full size (instances are scaled), with the Tree_* textures."""
    out = {}
    for kind, name in (("broad", "Broad"), ("pine", "Pine")):
        la, bt = TR.textures(name, tex_dir, reuse=True)
        tb = WT.TreeBuilder(tile=TR.BARK_EXT[kind])
        rng = random.Random(TR.SPECS[name][4] + 5)
        if kind == "broad":
            WT.broadleaf(tb, rng, H=TREE_BASE_H[kind], lobes=5, cards_per=20, sides=6)
        else:
            WT.pine(tb, rng, H=TREE_BASE_H[kind], tiers=5, sides=6)
        bn, ln = "Bark_" + name, "Leaves_" + name
        mats = {"Bark": bpy.data.materials.get(bn) or WB.pbr_material(bn, maps=bt, roughness=0.9),
                "Foliage": bpy.data.materials.get(ln) or WB.pbr_material(ln, maps=la, alpha=True, double_sided=True)}
        out[kind] = tb.build("T_" + kind, mats)
    return out


def build_city(tier, preview=False, render=True):
    cfg = TIER[tier]
    name = "City_%d" % tier
    t0 = time.time()
    times = {}
    scene.reset(cfg["seed"])
    tex_dir = common.out("textures")
    mats = WM.library()
    mats["Water"] = WB.pbr_material("Water", color=(0.030, 0.060, 0.058), roughness=0.06)
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
    maps, atlas = WB.atlas_bake(plist, asz, tex_dir, "%s_Atlas" % name, preview=preview)
    for o in plist:      # water faces keep their 0..1 quad UVs (no texture, valid tangents)
        idx = [i for i, m in enumerate(o.data.materials) if m and m.name.startswith("Water")]
        faces = [p.index for p in o.data.polygons if p.material_index in idx]
        if faces:
            WB.copy_uv(o, "MetreUV", "UV0", faces=faces)
    times["atlas"] = time.time() - t1
    # ---- instances + trees ----
    t1 = time.time()
    tp = tree_protos(tex_dir)
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
    gmat = WM.ground("W_Ground_%d" % tier, mask, lay.half)
    gp.data.materials[0] = gmat
    gmaps = WB.bake([gp], gsz, tex_dir, "%s_Ground" % name, ao_samples=8 if preview else 32,
                    ao_distance=6.0, cavity=0.0, ao_floor=0.25, jpeg=True, margin=4)
    # the ground base keeps a little of the contact AO in colour (grounding under Lumen)
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
        WR.beauty([o], os.path.join(prev, "%s_closest_zoom.png" % name), res=(1280, 720), samples=28 if preview else 48,
                  pitch=45.0, yaw=-12.0, target=(0, 0, 0), dist=250.0)
        times["render_closest"] = time.time() - t1
    rep = common.Report()
    rep.add(name, glb=path, kb=round(info["kb"], 1), triangles=info["triangles"], size_m=info["size"],
            bounds=info["bounds"], images=[(i["name"], i["size"], round(i["kb"])) for i in info["images"]],
            materials=info["materials"], prototypes=tris_proto, instances=len(lay.items), trees=len(lay.trees),
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
