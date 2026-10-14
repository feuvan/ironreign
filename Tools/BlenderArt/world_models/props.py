"""Sect / Banner / Flag -> ArtSource/Models/{Sect,Banner,Flag}.glb (DESIGN.md 12.3).

    Tools/BlenderArt/render.sh Tools/BlenderArt/world_models/props.py [Sect Banner Flag] [--preview]

Sect: heightfield outcrop + temple prototypes in one baked atlas, pines with the Tree_* textures.
Banner / Flag: pole, finial, trim etc. baked into a small atlas; the cloth is the pure white
``Tint`` material (no texture), double sided.  Writes the banner glyph field corners to
``<scratch>/banner_glyph_world.json`` for the 2D sprite step.
"""

import json
import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import trees as TR  # noqa: E402
import cities as CI  # noqa: E402

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from ironart import scene, world_bake as WB, world_city as WC, world_kit as K, world_mats as WM  # noqa: E402
from ironart import world_props as WP, world_render as WR  # noqa: E402
from ironart.geometry import MeshBuilder  # noqa: E402


def _finish(name, obj, footprint=None, height=None, tint=None, max_tris=150000, render=True, preview=False,
            view=None):
    WB.merge_slots(obj)
    WB.strip_uvs(obj, "UV0")
    path = os.path.join(common.MODELS_DIR, "%s.glb" % name)
    WB.export_glb(obj, path)
    info, probs = WB.verify_glb(path, footprint=footprint, height=height, tint=tint, max_tris=max_tris)
    print("[ironart] %s: %d tris, size %s, base %s, materials %s, images %s" % (
        name, info["triangles"], info["size"], info.get("base_centre"), [m["name"] for m in info["materials"]],
        [(i["name"], i["size"]) for i in info["images"]]))
    for p in probs:
        print("[ironart] PROBLEM %s: %s" % (name, p))
    t1 = time.time()
    if render:
        v = dict(pitch=45.0, yaw=-20.0, fill=0.85)
        v.update(view or {})
        WR.beauty([info["obj"]], os.path.join(common.out("previews"), "%s_beauty.png" % name), res=(960, 720),
                  samples=24 if preview else 40, **v)
    return path, info, probs, time.time() - t1


def _tint_uvs(obj, mat_prefix, scale):
    """Tint / water faces keep their metre UVs (scaled) in UV0 (valid tangents, no texture)."""
    me = obj.data
    idx = [i for i, m in enumerate(me.materials) if m and m.name.startswith(mat_prefix)]
    faces = [p.index for p in me.polygons if p.material_index in idx]
    if faces:
        WB.copy_uv(obj, "MetreUV", "UV0", scale=scale, faces=faces)


def build_sect(preview=False, render=True):
    t0 = time.time()
    scene.reset(77)
    tex_dir = common.out("textures")
    mats = WM.library()
    protos = {}
    mb = MeshBuilder()
    WP.sect_rock(mb)
    protos["rock"] = WB.build(mb, "P_rock", mats, auto_smooth_deg=70.0)
    builders = {
        "paifang": lambda: WC.p_paifang(),
        "side_hall": lambda: WC.p_hall(bays=(3, 2), bay=3.0, col_h=3.6, plat_h=0.7, roof="W_TileGreen",
                                       ridge="W_RidgeGreen", style="hip_gable", wall="W_RedWall", beasts=0,
                                       plat_mat="W_Stone", bracket_k=0.55, overhang=1.4),
        "main_hall": lambda: WC.p_hall(bays=(5, 2), bay=3.2, col_h=4.2, plat_h=0.9, roof="W_TileDark",
                                       ridge="W_Ridge", style="hip_gable", wall="W_RedWall", beasts=2,
                                       plat_mat="W_Stone", bracket_k=0.65, overhang=1.6),
        "pagoda": lambda: WC.p_pagoda(5, 2.8, body="W_PlasterWarm", roof="W_TileDark"),
        "pavilion": WP.p_pavilion,
    }
    for pn, fn in builders.items():
        protos[pn] = WB.build(fn(), "P_" + pn, mats)
    smb = MeshBuilder()
    for (x, y, z0, w, rise, n, run, rz) in WP.SECT_STAIRS:
        K.steps(smb, x, y, z0, w, rise, n, run, "W_Stone", rz=rz)
    protos["stairs"] = WB.build(smb, "P_stairs", mats)
    plist = list(protos.values())
    size = 1024 if preview else 2048
    WB.atlas_bake(plist, size, tex_dir, "Sect_Atlas", preview=preview, angle_deg=50.0, ao_distance=2.5,
                  weights={"P_rock": 1.15})
    tp = CI.tree_protos(tex_dir)
    place = [(protos["rock"], Matrix.Identity(4)), (protos["stairs"], Matrix.Identity(4))]
    for (pn, x, y, z, rz) in WP.sect_layout():
        place.append((protos[pn], Matrix.Translation(Vector((x, y, z))) @ Matrix.Rotation(rz, 4, "Z")))
    rng = random.Random(5)
    for (kind, x, y, s) in WP.SECT_TREES:
        z = max(0.0, float(WP.sect_height(np.array([[x]]), np.array([[y]]))[0, 0]) - 0.3)
        place.append((tp[kind], Matrix.Translation(Vector((x, y, z))) @ Matrix.Rotation(rng.uniform(0, 6.28), 4, "Z")
                      @ Matrix.Scale(s, 4)))
    obj = WB.instance_join("Sect", place)
    for o in list(protos.values()) + list(tp.values()):
        bpy.data.objects.remove(o, do_unlink=True)
    path, info, probs, tr = _finish("Sect", obj, footprint=(35.0, 35.0), tint=False, render=render, preview=preview,
                                    view=dict(pitch=45.0, yaw=-20.0, fill=0.9))
    return "Sect", path, info, probs, time.time() - t0, tr


def build_banner(kind="Banner", preview=False, render=True):
    t0 = time.time()
    scene.reset(88)
    tex_dir = common.out("textures")
    mats = WM.library()
    mats["Tint"] = WB.tint_material("Tint")
    mb = MeshBuilder()
    if kind == "Banner":
        glyph = WP.banner(mb)
        H = 22.0
    else:
        glyph = WP.flag(mb)
        H = 10.0
    obj = WB.build(mb, "P_" + kind, mats)
    size = 512 if (preview or kind == "Flag") else 1024
    WB.atlas_bake([obj], size, tex_dir, "%s_Atlas" % kind, preview=preview, angle_deg=55.0, ao_distance=0.6,
                  jpeg=False)
    _tint_uvs(obj, "Tint", 1.0 / (9.0 if kind == "Banner" else 5.5))
    with open(os.path.join(common.out(), "%s_glyph_world.json" % kind.lower()), "w") as f:
        json.dump([list(v) for v in glyph], f)
    path, info, probs, tr = _finish(kind, obj, height=H, tint=True, max_tris=40000, render=render, preview=preview,
                                    view=dict(pitch=20.0, yaw=-25.0, fill=0.8))
    return kind, path, info, probs, time.time() - t0, tr


def main():
    fl = common.flags()
    names = [n for n in fl["names"] if n in ("Sect", "Banner", "Flag")] or ["Banner", "Flag", "Sect"]
    rep = common.Report()
    paths = []
    bad = []
    for n in names:
        if n == "Sect":
            r = build_sect(fl["preview"], fl["render"])
        else:
            r = build_banner(n, fl["preview"], fl["render"])
        name, path, info, probs, secs, tr = r
        rep.add(name, glb=path, kb=round(info["kb"], 1), triangles=info["triangles"], size_m=info["size"],
                bounds=info["bounds"], base_centre=info.get("base_centre"),
                images=[(i["name"], i["size"], round(i["kb"])) for i in info["images"]], materials=info["materials"],
                problems=probs, total_s=round(secs, 1), render_s=round(tr, 1))
        paths.append(path)
        bad += probs
    rep.save()
    if bad:
        raise SystemExit("verification failed: %s" % bad)
    return paths


if __name__ == "__main__":
    main()
