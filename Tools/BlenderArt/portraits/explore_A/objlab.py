"""Build a spec and print the objects whose geometry overlaps a world point region; render with
objects hidden by name prefix.  blender -P objlab.py -- spec.json out.png 'prefix1,prefix2'"""
import json
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portrait as PR  # noqa: E402
import rig  # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:]
spec = PR._deep(json.load(open(a[0])), {"lab_res": [384, 480]})
spec2, times = PR.build(spec, os.path.dirname(a[1]), "objlab", int(os.environ.get("SPP", "10")))
hide = [p for p in a[2].split(",") if p]
for o in bpy.data.objects:
    if any(o.name.startswith(p) for p in hide):
        o.hide_render = True
print("OBJECTS", sorted(o.name for o in bpy.data.objects if not o.hide_render)[:80])
rig.render(a[1])
