"""Quick look-dev: build a spec with overrides (JSON string), render small, no paint.
    blender -b -P lab.py -- <spec.json> <out.png> '<json overrides>' [samples]"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portrait as PR  # noqa: E402
import rig  # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:]
spec = json.load(open(a[0]))
over = json.loads(a[2]) if len(a) > 2 else {}
spec = PR._deep(spec, over)
samples = int(a[3]) if len(a) > 3 else 16
spec2, times = PR.build(spec, os.path.dirname(a[1]), "lab", samples)
print("LAB build", {k: round(v, 1) for k, v in times.items()})
print("LAB render", round(rig.render(a[1]), 1))
