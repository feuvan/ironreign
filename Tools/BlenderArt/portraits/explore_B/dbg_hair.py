"""Debug: warlord head + hair grooms under the rig."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bpy
import numpy as np
from explore_B import head, rig, shading, mh, hair
from explore_B.identity import Identity, ARCH, wrinkle_default

out = sys.argv[sys.argv.index("--") + 1]
rig.reset()
W, H, SS = int(os.environ.get("DW", 384)), int(os.environ.get("DH", 480)), int(os.environ.get("SS", 1))
sc = rig.cycles(samples=int(os.environ.get("SPP", 48)), w=W, h=H, ss=SS, transparent=False)
ident = Identity(gender=1.0, age=54, muscle=0.75, weight=0.55, sliders=dict(ARCH["warlord"]),
                 skin_tone=0.6, weathered=0.6, wrinkles=wrinkle_default(54), beard_shadow=0.4)
ident.sliders["eye_height2"] = 0.1
t0 = time.time()
b = head.build(ident, subdiv=2)
lm = b["lm"]
cam = rig.portrait_camera(lm["eye_c"], head_frac=float(os.environ.get("HF", 0.48)))
head.aim_eyes(b["eyes"], cam.location, 0.85)
r = rig.light_rig(cam, lm["eye_c"])
sk = shading.skin(ident, tuple(r["key_dir"]))
b["body"].data.materials.append(sk)
em = shading.eyes(ident, tex_path=os.path.join(mh.MH_DATA, "eyes/materials/brown_eye.png"))
cm = shading.cornea()
for e in b["eyes"]:
    e.data.materials.append(em); e.data.materials.append(cm)
surf = hair.Surface([b["body"]], attrs=["z_beard", "z_moustache", "z_brow", "z_lash", "z_scalp", "z_goatee"])
print("surface %.1fs" % (time.time() - t0))
rng = np.random.default_rng(3)
hm = hair.hair_material("HairDark", melanin=0.92, redness=0.15, grey=0.3, roughness=0.4)
lm2 = dict(lm)
t1 = time.time()
hair.make("Beard", hair.beard(surf, lm, rng, chin_len=0.13, cheek_len=0.05), hm)
hair.make("Must", hair.moustache(surf, lm, rng, length=0.05), hm)
hair.make("Brows", hair.brows(surf, lm, rng, angle=0.25), hm)
lmat = hair.hair_material("Lash", melanin=1.0, redness=0.1, roughness=0.5)
hair.make("Lashes", hair.lashes(surf, lm, rng), lmat)
knot = np.asarray(lm["eye_c"]) + np.array([0, 0.035, 0.125])
hair.make("Scalp", hair.scalp_to_knot(surf, lm, rng, knot, count=9000), hm)
hair.make("Bun", hair.bun(knot + np.array([0, 0, 0.012]), rng, radius=0.028, height=0.025), hm)
print("hair %.1fs" % (time.time() - t1))
t = time.time()
sc.render.filepath = os.path.join(out, "hair_warlord.png")
bpy.ops.render.render(write_still=True)
print("RENDER %.1fs" % (time.time() - t))
