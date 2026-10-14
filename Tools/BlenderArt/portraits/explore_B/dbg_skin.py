"""Debug: shaded skin + eyes under the portrait rig (no hair/costume)."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bpy
from explore_B import head, rig, shading, mh
from explore_B.identity import Identity, ARCH, wrinkle_default

out = sys.argv[sys.argv.index("--") + 1]
os.makedirs(out, exist_ok=True)
rig.reset()
W, H, SS = int(os.environ.get("DW", 384)), int(os.environ.get("DH", 480)), int(os.environ.get("SS", 1))
sc = rig.cycles(samples=int(os.environ.get("SPP", 48)), w=W, h=H, ss=SS, transparent=False)
kind = os.environ.get("KIND", "warlord")
if kind == "warlord":
    ident = Identity(gender=1.0, age=54, muscle=0.75, weight=0.55, sliders=dict(ARCH["warlord"]),
                     skin_tone=0.6, weathered=0.6, wrinkles=wrinkle_default(54), beard_shadow=0.4)
elif kind == "scholar_f":
    ident = Identity(gender=0.0, age=24, muscle=0.4, weight=0.45, sliders=dict(ARCH["scholar_f"]),
                     skin_tone=0.15, skin_ruddy=0.25, makeup=0.7, lip_color="#B0403C")
else:
    ident = Identity(gender=1.0, age=74, muscle=0.35, weight=0.4, sliders=dict(ARCH["sage"]),
                     skin_tone=0.35, weathered=0.3, wrinkles=wrinkle_default(74))
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
    e.data.materials.append(em)
    e.data.materials.append(cm)
t = time.time()
sc.render.filepath = os.path.join(out, "skin_%s.png" % kind)
bpy.ops.render.render(write_still=True)
print("RENDER %.1fs" % (time.time() - t))
