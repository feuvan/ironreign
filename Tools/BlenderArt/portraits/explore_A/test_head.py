"""Bare head test: identity -> head/eyes/skin maps -> camera/lights -> render."""
import os
import sys
import time

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import head as H  # noqa: E402
import identity as I  # noqa: E402
import mh  # noqa: E402
import rig  # noqa: E402
import skin  # noqa: E402
import skinmaps  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
out = args[0]
seed = int(args[1]) if len(args) > 1 else 1
gender = args[2] if len(args) > 2 else "m"
age = float(args[3]) if len(args) > 3 else 50
arch = args[4] if len(args) > 4 else "warrior"
samples = int(args[5]) if len(args) > 5 else 64
sss = args[6] if len(args) > 6 else "BURLEY"

t0 = time.time()
bpy.ops.wm.read_factory_settings(use_empty=True)
idn = I.make_identity(seed, gender, age, arch)
print("identity", idn.expression, round(idn.muscle, 2), round(idn.weight, 2))
b = H.build(idn)
print("F", b["F"])
style = {"hair_rgb": (0.09, 0.07, 0.06), "recede": 0.2, "scars": [((0.62, 0.55), (0.95, 0.05))]}
A, Rg, Hh = skinmaps.make(b, idn, style, seed=seed)
if "--dump" in sys.argv:
    from PIL import Image
    import numpy as np
    Image.fromarray((A[..., :3] * 255).astype(np.uint8)).save(out.replace(".png", "_albedo.png"))
    Image.fromarray((Hh * 255).astype(np.uint8)).save(out.replace(".png", "_height.png"))
ia = skinmaps.to_bpy("SkinA", A)
ir = skinmaps.to_bpy("SkinR", Rg, "Non-Color")
ih = skinmaps.to_bpy("SkinH", Hh, "Non-Color", float_buffer=True)
b["head"].data.materials.append(skin.skin_material_tex(idn, ia, ir, ih, sss=sss))
b["head"].pass_index = rig.PASS["skin"]
em = skin.eye_material(os.path.join(mh.MH_DATA, "eyes", "materials", "brown_eye.png"))
for e in b["eyes"]:
    e.data.materials.append(em)
    e.pass_index = rig.PASS["eyes"]
rig.setup_render(samples=samples)
lm = b["lm"]
cam = rig.camera(lm)
H.aim_eyes(b["eyes"], cam.location, 0.9)
rig.lights(cam, lm["eye_c"])
print("build", time.time() - t0)
dt = rig.render(out)
print("render", dt)
