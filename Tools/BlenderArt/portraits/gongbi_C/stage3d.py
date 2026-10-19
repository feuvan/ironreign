"""3D stage (Blender): build the bust of a spec, render the passes, export for the 2D stage.

    Tools/BlenderArt/render.sh portraits/gongbi_C/stage3d.py <spec> <scene_dir> [ss] [spp]

``<spec>`` is a name in :mod:`specs` or a path to a spec JSON.  Writes
``<scene_dir>/scene.npz`` + ``scene.json`` + ``timing3d.json``.
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from ironart import scene as _scene  # noqa: E402

import b3d  # noqa: E402
import bust  # noqa: E402
import gear  # noqa: E402
import specs  # noqa: E402


def run(name, out_dir, ss=3, samples=6):
    t0 = time.time()
    spec = specs.load(name)
    st = b3d.Stage(384, 480, ss=ss, samples=samples, seed=spec.get("seed", 0))
    pose = spec.get("pose", {})
    st.pose(body_yaw=pose.get("body_yaw", -28.0), head_yaw=pose.get("head_yaw", 6.0),
            head_pitch=pose.get("head_pitch", 0.0), head_roll=pose.get("head_roll", 0.0))
    head = bust.build_head(st, spec)
    bust.build_torso(st, spec)
    gear.build(st, spec)
    fr = spec.get("frame", {})
    st.camera(yaw=pose.get("cam_yaw", 0.0), pitch=pose.get("cam_pitch", -2.0),
              eye_frac=fr.get("eye_frac", 0.38), head_frac=fr.get("head_frac", 0.48),
              x_frac=fr.get("x_frac", 0.5), head_objs=[head], min_head=fr.get("min_head", 0.82))
    st.ink(scale=spec.get("ink_scale", 1.0), overrides=spec.get("ink"))
    t_build = time.time() - t0
    ps, secs = st.render(out_dir)
    st.export(out_dir, ps, extra=dict(spec=spec))
    tot = time.time() - t0
    with open(os.path.join(out_dir, "timing3d.json"), "w") as f:
        json.dump(dict(build=t_build, render=secs, total=tot), f)
    print("[gongbi_C] %s: build %.1fs render %.1fs total %.1fs" % (spec.get("name", name),
                                                                    t_build, secs, tot))


if __name__ == "__main__":
    a = _scene.args()
    run(a[0], a[1], int(a[2]) if len(a) > 2 else 3, int(a[3]) if len(a) > 3 else 6)
