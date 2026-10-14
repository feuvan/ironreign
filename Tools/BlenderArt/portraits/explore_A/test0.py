"""Smoke test: MakeHuman asian male head, cropped, plain SSS skin, one light."""
import os
import sys
import time

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mh  # noqa: E402

OUT = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "/tmp/t0.png"
age_years = float(sys.argv[sys.argv.index("--") + 2]) if len(sys.argv) > sys.argv.index("--") + 2 else 50

t0 = time.time()
bpy.ops.wm.read_factory_settings(use_empty=True)
base = mh.load_base()
w = mh.macro_weights(gender=1.0, age=mh.age_slider(age_years), muscle=0.6, weight=0.55, asian=1.0)
V = mh.apply_targets(base.verts, w)
print("targets", time.time() - t0, len(w))
keep = [i for i in base.group_faces("body") if all(V[j, 1] > 4.2 for j in base.faces[i])]
used = sorted({j for i in keep for j in base.faces[i]})
remap = {j: k for k, j in enumerate(used)}
vb = mh.to_blender(V[used])
faces = [[remap[j] for j in base.faces[i]] for i in keep]
me = bpy.data.meshes.new("Head")
me.from_pydata(vb.tolist(), [], faces)
me.update()
ob = bpy.data.objects.new("Head", me)
bpy.context.scene.collection.objects.link(ob)
for p in me.polygons:
    p.use_smooth = True
ob.modifiers.new("sub", "SUBSURF").levels = 2
ob.modifiers["sub"].render_levels = 2
mat = bpy.data.materials.new("Skin")
mat.use_nodes = True
bsdf = mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.55, 0.33, 0.22, 1)
bsdf.inputs["Subsurface Weight"].default_value = 1.0
bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.2)
bsdf.inputs["Subsurface Scale"].default_value = 0.004
bsdf.inputs["Roughness"].default_value = 0.45
me.materials.append(mat)
# eyes
px = mh.eyes_proxy()
ev, euv, ef, efu = px.load_obj()
pv = mh.to_blender(px.fit(V))
me2 = bpy.data.meshes.new("Eyes")
me2.from_pydata(pv.tolist(), [], [list(f) for f in ef])
ob2 = bpy.data.objects.new("Eyes", me2)
bpy.context.scene.collection.objects.link(ob2)
for p in me2.polygons:
    p.use_smooth = True
m2 = bpy.data.materials.new("Eye")
m2.use_nodes = True
m2.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.7, 0.68, 0.65, 1)
me2.materials.append(m2)
# camera
eye_c = Vector(pv.mean(0))
print("eye centre", eye_c, "head top", vb[:, 2].max(), "min z", vb[:, 2].min())
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
bpy.context.scene.collection.objects.link(cam)
cam.data.lens = 85
cam.data.sensor_fit = "VERTICAL"
cam.data.sensor_height = 36
import math
yaw = math.radians(20)
d = 1.55
cam.location = eye_c + Vector((math.sin(yaw) * d, -math.cos(yaw) * d, 0.0)) + Vector((0, 0, -0.03))
direction = (eye_c + Vector((0, 0, -0.06))) - cam.location
cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
bpy.context.scene.camera = cam
# light
L = bpy.data.lights.new("Key", "AREA")
L.energy = 60
L.size = 0.5
lo = bpy.data.objects.new("Key", L)
bpy.context.scene.collection.objects.link(lo)
lo.location = eye_c + Vector((-0.9, -1.1, 0.8))
lo.rotation_euler = (eye_c - lo.location).to_track_quat("-Z", "Y").to_euler()
F = bpy.data.lights.new("Fill", "AREA")
F.energy = 12
F.size = 1.5
fo = bpy.data.objects.new("Fill", F)
bpy.context.scene.collection.objects.link(fo)
fo.location = eye_c + Vector((1.2, -1.0, 0.2))
fo.rotation_euler = (eye_c - fo.location).to_track_quat("-Z", "Y").to_euler()
wd = bpy.data.worlds.new("W")
wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.045, 0.04, 1)
bpy.context.scene.world = wd
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = 32
sc.cycles.use_denoising = False
sc.render.resolution_x = 384
sc.render.resolution_y = 480
sc.view_settings.view_transform = "Filmic"
sc.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print("total", time.time() - t0)
