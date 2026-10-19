"""3D stage entry (run through Tools/BlenderArt/render.sh):

    render.sh portraits/gongbi_C/stage3d.py <spec_name> <out_dir> [ss] [samples]

Builds the bust for ``specs.SPECS[spec_name]``, renders the passes and writes
``<out_dir>/scene.npz`` + ``scene.json`` for the 2D stage (:mod:`stage2d`).
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from ironart import scene as _scene  # noqa: E402

import b_stage  # noqa: E402
import build  # noqa: E402
import specs  # noqa: E402


def run(name, out_dir, ss=3, samples=8):
    t0 = time.time()
    spec = specs.get(name)
    st = b_stage.Stage(384, 480, ss=ss, samples=samples, seed=spec.get("seed", 0))
    H, torso = build.bust(st, spec)
    pose = spec.get("pose", {})
    fit = [o for o in st.col("gear").all_objects] + [o for o in st.col("hair").all_objects]
    st.camera(yaw=pose.get("yaw", 22.0), pitch=pose.get("pitch", -2.0),
              x_frac=pose.get("x_frac", 0.5), fit_objs=fit,
              head_frac=spec.get("frame", {}).get("head_frac", 0.48))
    st.ink(scale=spec.get("ink_scale", 1.0))
    t_build = time.time() - t0
    ps, secs = st.render(out_dir)
    meta = st.export(out_dir, ps, extra=dict(spec=name))
    tot = time.time() - t0
    with open(os.path.join(out_dir, "timing3d.json"), "w") as f:
        json.dump(dict(build=t_build, render=secs, total=tot), f)
    print("[gongbi_C] %s: build %.1fs render %.1fs total %.1fs" % (name, t_build, secs, tot))


if __name__ == "__main__":
    a = _scene.args()
    run(a[0], a[1], int(a[2]) if len(a) > 2 else 3, int(a[3]) if len(a) > 3 else 8)
