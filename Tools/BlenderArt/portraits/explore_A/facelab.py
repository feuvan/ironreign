"""Face lab: render face close-ups for identity variants (JSON list of overrides)."""
import json
import os
import sys
import time

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hair  # noqa: E402
import head as H  # noqa: E402
import identity as I  # noqa: E402
import mh  # noqa: E402
import rig  # noqa: E402
import skin  # noqa: E402
import skinmaps  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
outdir = args[0]
spec = json.loads(open(args[1]).read())
os.makedirs(outdir, exist_ok=True)
for k, v in enumerate(spec):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    idn = I.make_identity(v.get("seed", 1), v.get("g", "m"), v.get("age", 50), v.get("arch", "warrior"))
    for key, val in v.get("set", {}).items():
        setattr(idn, key, val)
    for key, val in v.get("face", {}).items():
        idn.face[key] = idn.face.get(key, 0.0) + val
    idn.expr_extra = v.get("expr", {})
    b = H.build(idn)
    style = {"hair_rgb": (0.06, 0.05, 0.045), "recede": 0.1}
    A, Rg, Hh = skinmaps.make(b, idn, style, seed=1)
    b["head"].data.materials.append(skin.skin_material_tex(idn, skinmaps.to_bpy("A", A), skinmaps.to_bpy("R", Rg, "Non-Color"), skinmaps.to_bpy("H", Hh, "Non-Color", True)))
    em, ec = skin.eye_materials(os.path.join(mh.MH_DATA, "eyes", "materials", "brown_eye.png"))
    for e in b["eyes"]:
        e.data.materials.append(em)
        e.data.materials.append(ec)
    rng = np.random.default_rng(1)
    surf = hair.Surface(b["head"])
    hm = hair.hair_material("HairM", melanin=0.98, redness=0.15)
    hair.brows(surf, b, hm, rng, count=1100, thick=1.1, arch=0.8, angle=0.2)
    hair.lashes(surf, b, b["eyes"], hair.hair_material("LashM", melanin=1.0, roughness=0.5), rng)
    rig.setup_render(w=320, h=240, ss=1, samples=v.get("spp", 48))
    lm = b["lm"]
    cam = rig.camera(lm, head_frac=1.9, eye_line=0.45)
    H.aim_eyes(b["eyes"], cam.location, v.get("aim", 0.3))
    rig.lights(cam, lm["eye_c"])
    rig.render(os.path.join(outdir, "v%02d.png" % k))
