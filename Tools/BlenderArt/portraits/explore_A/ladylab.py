"""Face variants for one spec: renders head+brows+lashes (no costume/hair) close-ups."""
import json
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portrait as PR  # noqa: E402
import rig  # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:]
base = json.load(open(a[0]))
out = a[1]
variants = json.loads(a[2])
os.makedirs(out, exist_ok=True)
for k, v in enumerate(variants):
    spec = PR._deep(base, {"outfit": {"kind": "none"}, "beard": None, "lab_res": [300, 375]})
    spec = PR._deep(spec, v)
    if "face_set" in v:
        spec["face"] = v["face_set"]
    PR.build(spec, out, "fl", 16)
    rig.render(os.path.join(out, "v%02d.png" % k))
