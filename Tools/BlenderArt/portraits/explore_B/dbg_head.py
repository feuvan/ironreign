"""Debug: clay render of a morphed MakeHuman bust + a zone-mask view."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bpy
from explore_B import head, rig, identity, nodes
from explore_B.identity import Identity, ARCH

out = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv and len(sys.argv) > sys.argv.index("--") + 1 else "/tmp/dbg"
mask = sys.argv[sys.argv.index("--") + 2] if len(sys.argv) > sys.argv.index("--") + 2 else ""
os.makedirs(out, exist_ok=True)
rig.reset()
sc = rig.cycles(samples=16, w=int(os.environ.get("DW",192)), h=int(os.environ.get("DH",240)), ss=1, transparent=False)
ident = Identity(gender=1.0, age=52, muscle=0.7, sliders=dict(ARCH["warlord"]))
b = head.build(ident, subdiv=1)
lm = b["lm"]
cam = rig.portrait_camera(lm["eye_c"], yaw_deg=float(os.environ.get("YAW",22)), head_frac=float(os.environ.get("HF",0.48)))
r = rig.light_rig(cam, lm["eye_c"])
m, nb = nodes.material("Clay")
if mask:
    a = nb.attr("z_" + mask)
    em = nb.node("ShaderNodeEmission", inputs={"Color": a, "Strength": 1.0})
    nodes.output(nb, em)
else:
    p = nodes.principled(nb, Base_Color="#B08060", Roughness=0.6)
    nodes.output(nb, p)
b["body"].data.materials.append(m)
m2, nb2 = nodes.material("EyeClay")
nodes.output(nb2, nodes.principled(nb2, Base_Color="#DDDDDD", Roughness=0.2))
b["eyes"].data.materials.append(m2)
t = time.time()
sc.render.filepath = os.path.join(out, "head_%s_%s.png" % (mask or "clay", os.environ.get("YAW","22")))
bpy.ops.render.render(write_still=True)
print("render", time.time() - t)
