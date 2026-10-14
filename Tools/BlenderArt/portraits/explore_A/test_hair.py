"""Head + hair test."""
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
out = args[0]
seed = int(args[1]) if len(args) > 1 else 1
gender = args[2] if len(args) > 2 else "m"
age = float(args[3]) if len(args) > 3 else 50
arch = args[4] if len(args) > 4 else "warrior"
samples = int(args[5]) if len(args) > 5 else 32

t0 = time.time()
bpy.ops.wm.read_factory_settings(use_empty=True)
idn = I.make_identity(seed, gender, age, arch)
idn.expression = "stern"
b = H.build(idn)
bstyle = {"mustache": 1.0, "chin": 1.0, "cheeks": 0.9, "jaw": 1.0, "neck": 0.6, "sideburns": 1.0, "soul": 1.0,
          "tails": 1.0, "length": 0.11, "must_len": 0.04, "cheek_len": 0.03, "taper": 0.3, "gravity": 0.7}
style = {"hair_rgb": (0.08, 0.065, 0.055), "recede": 0.15, "beard": bstyle, "beard_rgb": (0.25, 0.23, 0.22)}
A, Rg, Hh = skinmaps.make(b, idn, style, seed=seed)
ia = skinmaps.to_bpy("SkinA", A)
ir = skinmaps.to_bpy("SkinR", Rg, "Non-Color")
ih = skinmaps.to_bpy("SkinH", Hh, "Non-Color", float_buffer=True)
b["head"].data.materials.append(skin.skin_material_tex(idn, ia, ir, ih))
b["head"].pass_index = rig.PASS["skin"]
em, ec = skin.eye_materials(os.path.join(mh.MH_DATA, "eyes", "materials", "brown_eye.png"))
for e in b["eyes"]:
    e.data.materials.append(em)
    e.data.materials.append(ec)
    e.pass_index = rig.PASS["eyes"]
t1 = time.time()
rng = np.random.default_rng(seed)
surf = hair.Surface(b["head"])
grey = 0.45
hm = hair.hair_material("HairM", melanin=0.92, grey=grey)
bm = hair.hair_material("BeardM", melanin=0.9, grey=grey + 0.1)
hair.brows(surf, b, hm, rng, count=1100, thick=1.15, arch=0.8, angle=0.25)
hair.lashes(surf, b, b["eyes"], hair.hair_material("LashM", melanin=1.0, roughness=0.5), rng)
hair.beard(surf, b, bstyle, bm, rng, count=9000)
F = b["F"]
lm = b["lm"]
ez = np.array(lm["ez"])


def topknot(pos, fc, C):
    top = surf.P[np.argmax(surf.P[:, 2])]
    G = top + ez * 0.004 + np.array(lm["ey"]) * -0.01
    return [np.tile(G, (len(pos), 1))]


cap = hair.hair_cap(surf, b, hair.cap_material("CapM", grey=grey * 0.5), recede=0.15)
hob, C = hair.comb(surf, b, hm, rng, topknot, count=6000, recede=0.15, lift=0.0015, volume=0.004)
top = surf.P[np.argmax(surf.P[:, 2])]
bun = hair.bun_strands(top + ez * 0.018 + np.array(lm["ey"]) * -0.008, ez, 0.017, 0.013, 1200, rng)
hair.curves_object("Bun", bun, 0.00007, 0.00003, hm)
print("hair", time.time() - t1)
rig.setup_render(samples=samples)
cam = rig.camera(lm, head_frac=0.47)
H.aim_eyes(b["eyes"], cam.location, 0.3)
rig.lights(cam, lm["eye_c"])
print("build", time.time() - t0)
dt = rig.render(out)
print("render", dt)
