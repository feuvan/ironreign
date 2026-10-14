"""Debug: close-up face render for slider exploration.
blender -b -P dbg_face.py -- out.png '{"identity":{...}}'"""
import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bpy
from explore_B import head, rig, shading, mh, hair
from explore_B.identity import Identity, ARCH, wrinkle_default
import numpy as np
a = sys.argv[sys.argv.index("--") + 1:]
out, cfg = a[0], json.loads(a[1])
rig.reset()
sc = rig.cycles(samples=cfg.get("spp", 24), w=240, h=300, ss=1, transparent=False)
ident = Identity()
for k, v in cfg["identity"].items():
    if k == "arch":
        ident.sliders.update(ARCH[v])
    elif k == "sliders":
        ident.sliders.update(v)
    else:
        setattr(ident, k, v)
b = head.build(ident, subdiv=2)
lm = b["lm"]
cam = rig.portrait_camera(lm["eye_c"], head_frac=cfg.get("hf", 0.85), eye_line=0.42, yaw_deg=cfg.get("yaw", 22))
head.aim_eyes(b["eyes"], cam.location, 0.85)
r = rig.light_rig(cam, lm["eye_c"], **cfg.get("light", {}))
b["body"].data.materials.append(shading.skin(ident, tuple(r["key_dir"])))
em = shading.eyes(ident, tex_path=os.path.join(mh.MH_DATA, "eyes/materials/brown_eye.png"))
cm = shading.cornea()
for e in b["eyes"]:
    e.data.materials.append(em); e.data.materials.append(cm)
if cfg.get("brows", True):
    surf = hair.Surface([b["body"]], attrs=["z_brow", "z_brow_f", "z_lash", "z_scalp"])
    rng = np.random.default_rng(1)
    hm = hair.hair_material("H", melanin=0.97, redness=0.1, roughness=0.45)
    hair.make("Brows", hair.brows(surf, lm, rng, **cfg.get("brows_kw", {})), hm)
    hair.make("Lashes", hair.lashes(surf, lm, rng), hm)
w = bpy.data.worlds["World"]
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
