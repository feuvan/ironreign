"""Unit_Infantry / Unit_Cavalry / Unit_Archer / Unit_Base .glb (DESIGN.md 12.3).

    Tools/BlenderArt/render.sh Tools/BlenderArt/battle/units.py [Infantry Cavalry Archer Base] [--preview] [--no-render]

Squads of gongbi soldier figures (:mod:`ironart.battle_figures`) facing -Y (the board turns the
model's front to the unit's facing), standing on z = 0 (the board puts them on the plinth top),
footprint <= 6 m; side colour on the ``Tint`` slots (tabards, helmet tassels, spear tassels,
banners, saddle cloths).  Unit_Base: a 6 m lacquered plinth disc, 0.18 m high, ``Tint`` top.
One atlas per model (Cycles bake of the gongbi node materials: base colour, tangent normal).
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from ironart import scene  # noqa: E402
from ironart import battle_figures as BF  # noqa: E402
from ironart import battle_hex as BH  # noqa: E402
from ironart import battle_unit_mats as UM  # noqa: E402
from ironart import world_bake as WB  # noqa: E402
from ironart.geometry import MeshBuilder  # noqa: E402

SQUADS = {"Infantry": (BF.squad_infantry, 4101), "Cavalry": (BF.squad_cavalry, 4202), "Archer": (BF.squad_archers, 4303)}
BASE_R = 3.0
BASE_H = 0.18


def build_base(mb):
    prof = [(0.0, BASE_H), (BASE_R - 0.1, BASE_H), (BASE_R - 0.03, BASE_H - 0.015), (BASE_R, BASE_H - 0.05)]
    mb.lathe(prof, "Tint", 72, smooth=True)
    side = [(BASE_R, BASE_H - 0.05), (BASE_R, 0.02), (BASE_R - 0.02, 0.0)]
    mb.lathe(side, "U_BaseRim", 72, smooth=True)
    mb.lathe([(BASE_R - 0.02, 0.0), (0.0, 0.0)], "Tint", 72, smooth=True)


def build_unit(name, preview=False, render=True, verify=True):
    t = common.Timer()
    model = "Unit_" + name
    seed = SQUADS[name][1] if name in SQUADS else 4404
    scene.reset(seed)
    WB.tint_material("Tint")
    rng = random.Random(seed)
    mb = MeshBuilder()
    if name == "Base":
        build_base(mb)
        px = 512
    else:
        SQUADS[name][0](mb, rng)
        px = 2048
    obj = WB.build(mb, "Units", {})
    t.mark("build")
    tex = common.out("textures")
    BH.bake_props([obj], px // (2 if preview else 1), tex, model, UM.library, samples=2 if preview else 4,
                  angle_deg=55.0, margin_px=4)
    t.mark("bake")
    obj = BH.finalize(model, [obj])
    tris = WB.tri_count(obj)
    path = os.path.join(common.MODELS_DIR, model + ".glb")
    WB.export_glb(obj, path)
    t.mark("export")
    info, probs = {}, []
    if verify:
        info, probs = WB.verify_glb(path, tint=True)
        lo, hi = info["bounds"]
        ext = (hi[0] - lo[0], hi[1] - lo[1])
        if name == "Base":
            if abs(ext[0] - 6.0) > 0.05 or abs(ext[1] - 6.0) > 0.05:
                probs.append("base disc %.2f x %.2f m (want 6 m)" % ext)
        elif max(ext) > 6.0:
            probs.append("footprint %.2f x %.2f m > 6 m" % ext)
        if lo[2] < -0.05:
            probs.append("below the plinth top (min z %.2f)" % lo[2])
        t.mark("verify")
    rsecs = 0.0
    if render and verify:
        import review
        cam = review.camera([info["obj"]], pitch=42.0, yaw=-25.0, fill=0.9)
        rsecs = review.preview([info["obj"]], os.path.join(common.out("previews"), model + ".png"), res=(960, 720),
                               samples=10 if preview else 20, cam=cam, ground_z=0.0)
        t.mark("render")
    rep = common.Report()
    rep.add(model, glb=path, kb=round(os.path.getsize(path) / 1024.0, 1), triangles=tris, size_m=info.get("size"),
            bounds=info.get("bounds"), images=[(i["name"], i["size"], round(i["kb"])) for i in info.get("images", [])],
            materials=[m["name"] for m in info.get("materials", [])], problems=probs, times=t.marks,
            render_s=round(rsecs, 1))
    rep.save()
    print("[battle] %s: %d tris, %.0f KB, size %s, problems=%s, times=%s" % (
        model, tris, os.path.getsize(path) / 1024.0, info.get("size"), probs, t.marks))
    if probs:
        raise SystemExit("%s failed verification: %s" % (model, probs))
    return path


def main():
    fl = common.flags()
    names = [n for n in fl["names"] if n in ("Infantry", "Cavalry", "Archer", "Base")] or \
        ["Base", "Infantry", "Cavalry", "Archer"]
    for n in names:
        build_unit(n, fl["preview"], fl["render"], fl["verify"])


if __name__ == "__main__":
    main()
