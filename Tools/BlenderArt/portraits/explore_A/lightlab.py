"""Lighting lab: one identity, several light rigs, head + brows only, 1x renders."""
import json
import os
import sys

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portrait as PR  # noqa: E402
import rig  # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:]
spec = json.load(open(a[0]))
out = a[1]
rigs = json.loads(a[2])
spec = PR._deep(spec, {"outfit": {"kind": "none"}, "beard": None, "lab_res": [384, 480]})
spec2, times = PR.build(spec, out, "ll", 20)
for k, r in enumerate(rigs):
    for o in list(bpy.data.objects):
        if o.type == "LIGHT":
            bpy.data.objects.remove(o)
    cam = bpy.context.scene.camera
    import head as H
    lm = None
    eyes = [o for o in bpy.data.objects if o.name.startswith("Eye")]
    tgt = sum((o.location for o in eyes), eyes[0].location * 0) / 2
    rig.lights(cam, tgt, eyes=eyes, **r)
    rig.render(os.path.join(out, "ll_%02d.png" % k))
