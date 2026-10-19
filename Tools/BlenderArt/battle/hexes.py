"""Hex_<Terrain>.glb builder (DESIGN.md 12.3 / 12.4).

    Tools/BlenderArt/render.sh Tools/BlenderArt/battle/hexes.py [Plain Forest ...] [--preview] [--no-render]

Per terrain (:mod:`tiles`): ground heightfield + skirt -> painted ground texture (numpy) ->
props (MeshBuilder, gongbi B_*/W_* materials) -> props atlas bake (Cycles: base colour without
light, tangent normal) -> ONE mesh (materials Ground + Props) -> GLB -> verified by re-import
-> gongbi review render of the re-imported file.
"""

import functools
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import tiles  # noqa: E402

import bpy  # noqa: E402
import numpy as np  # noqa: E402

from ironart import scene  # noqa: E402
from ironart import battle_arch as BA  # noqa: E402
from ironart import battle_hex as BH  # noqa: E402
from ironart import battle_mats as BM  # noqa: E402
from ironart import battle_paint as BP  # noqa: E402
from ironart import world_bake as WB  # noqa: E402
from ironart.geometry import MeshBuilder  # noqa: E402

FOOTPRINT = (8.0, BP.APO * 2)


def build_tile(name, preview=False, render=True, verify=True, export=True):
    t = common.Timer()
    sp = tiles.spec(name)
    scene.reset(sp.seed)
    tex = common.out("textures")
    model = "Hex_" + name
    # ground
    ground = BH.ground_object("Ground", sp.h, n=sp.n)
    cv = BP.Canvas(1024 if preview else BH.GROUND_PX)
    sp.paint(cv)
    BH.paint_skirt(cv, sp.top_z, sp.skirt, seed=sp.seed)
    gmaps = BH.save_ground(cv, tex, model + "_Ground")
    gmat = BH.ground_material("Ground", gmaps)
    ground.data.materials.clear()
    ground.data.materials.append(gmat)
    t.mark("ground")
    parts = [ground]
    # props
    mb = MeshBuilder()
    sp.props(mb)
    bake = []
    if mb.faces:
        pobj = WB.build(mb, "Props", {})
        bake.append(pobj)
        parts.append(pobj)
    protos = {}
    for pname, fn in sp.prototypes().items():
        mbp = MeshBuilder()
        fn(mbp)
        protos[pname] = WB.build(mbp, "PR_" + pname, {})
        bake.append(protos[pname])
    if bake:
        size = sp.props_px // (2 if preview else 1)
        BH.bake_props(bake, size, tex, model + "_Props", functools.partial(BM.library, kit_scale=BA.K),
                      samples=2 if preview else 4)
    for pname, mw in sp.placements():
        pr = protos[pname]
        o = pr.copy()
        o.data = pr.data
        bpy.context.scene.collection.objects.link(o)
        o.matrix_world = mw
        parts.append(o)
    t.mark("props")
    obj = BH.finalize(model, parts)
    for pr in protos.values():
        for c in list(pr.users_collection):
            c.objects.unlink(pr)
        bpy.data.objects.remove(pr, do_unlink=True)
    bpy.context.view_layer.update()
    tris = WB.tri_count(obj)
    path = os.path.join(common.MODELS_DIR if export else common.out("glb"), model + ".glb")
    WB.export_glb(obj, path)
    t.mark("export")
    info, probs = {}, []
    if verify:
        info, probs = WB.verify_glb(path, footprint=FOOTPRINT, tint=False)
        t.mark("verify")
    rsecs = 0.0
    if render and verify:
        import review
        rsecs = review.tile_preview([info["obj"]], os.path.join(common.out("previews"), model + ".png"),
                                    fast=preview)
        t.mark("render")
    rep = common.Report()
    rep.add(model, glb=path, kb=round(os.path.getsize(path) / 1024.0, 1), triangles=tris,
            size_m=info.get("size"), bounds=info.get("bounds"), base_centre=info.get("base_centre"),
            images=[(i["name"], i["size"], round(i["kb"])) for i in info.get("images", [])],
            materials=[m["name"] for m in info.get("materials", [])], problems=probs, times=t.marks,
            render_s=round(rsecs, 1), notes=sp.notes)
    rep.save()
    print("[battle] %s: %d tris, %.0f KB, problems=%s, times=%s" % (model, tris, os.path.getsize(path) / 1024.0,
                                                                     probs, t.marks))
    if probs:
        raise SystemExit("%s failed verification: %s" % (model, probs))
    return path


def main():
    fl = common.flags()
    names = [n for n in fl["names"] if n in common.TERRAINS] or list(common.TERRAINS)
    names = [n for n in names if n in tiles.TERRAIN_SPECS]
    for n in names:
        # preview runs (half-size textures) write their GLBs to scratch, never to ArtSource/Models
        build_tile(n, fl["preview"], fl["render"], fl["verify"], export=not fl["preview"])


if __name__ == "__main__":
    main()
