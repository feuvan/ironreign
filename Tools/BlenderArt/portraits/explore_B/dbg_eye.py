import os, sys, time, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bpy
from mathutils import Vector
from explore_B import head, rig, shading, mh, nodes
from explore_B.identity import Identity, ARCH
out = sys.argv[sys.argv.index("--") + 1]
rig.reset()
sc = rig.cycles(samples=16, w=400, h=300, ss=1, transparent=False)
ident = Identity(gender=1.0, age=30)
b = head.build(ident, subdiv=1)
lm = b["lm"]
cd = bpy.data.cameras.new("C"); cd.lens = 85; cd.sensor_fit="HORIZONTAL"; cd.sensor_width=36
cam = bpy.data.objects.new("C", cd); sc.collection.objects.link(cam); sc.camera = cam
e = Vector(lm["eye_l"])
cam.location = e + Vector((0.0, -0.35, 0.0))
cam.rotation_euler = (math.radians(90), 0, 0)
cd.shift_x = 0.0
cd.lens = 300
m, nb = nodes.material("E")
img = bpy.data.images.load(os.path.join(mh.MH_DATA, "eyes/materials/brown_eye.png"))
tx = nb.node("ShaderNodeTexImage", image=img)
nb.set(tx.inputs[0], nb.node("ShaderNodeTexCoord").outputs["UV"])
nodes.output(nb, nb.node("ShaderNodeEmission", inputs={"Color": tx.outputs[0], "Strength": 1.0}))
for eo in b["eyes"]: eo.data.materials.append(m)
m2, nb2 = nodes.material("S")
nodes.output(nb2, nb2.node("ShaderNodeEmission", inputs={"Color": (0.3, 0.15, 0.1, 1), "Strength": 1.0}))
b["body"].data.materials.append(m2)
if os.environ.get("HIDE"):
    b["body"].hide_render = True
sc.render.filepath = os.path.join(out, "eye_dbg%s.png" % os.environ.get("HIDE",""))
bpy.ops.render.render(write_still=True)
