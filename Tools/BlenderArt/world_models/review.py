"""Review render of any exported model (re-imported from its GLB, as Unreal will get it).

    Tools/BlenderArt/render.sh Tools/BlenderArt/world_models/review.py <Name> [pitch yaw fill W H spp] [--dist D] [--out file]

Writes <scratch>/previews/<Name>_review_p<pitch>_y<yaw>.png (perspective 40 deg FOV, studio sun, sky,
terrain-like ground, Filmic Medium Contrast).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

from ironart import scene, world_bake as WB, world_render as WR  # noqa: E402


def main():
    a = scene.args()
    dist = None
    out = None
    if "--dist" in a:
        i = a.index("--dist")
        dist = float(a[i + 1])
        del a[i:i + 2]
    tgt = None
    if "--target" in a:
        i = a.index("--target")
        tgt = tuple(float(v) for v in a[i + 1].split(","))
        del a[i:i + 2]
    if "--out" in a:
        i = a.index("--out")
        out = a[i + 1]
        del a[i:i + 2]
    name = a[0]
    vals = [float(x) for x in a[1:]]
    pitch, yaw, fill, W, H, spp = (vals + [50.0, -25.0, 0.9, 1280, 720, 40][len(vals):])[:6]
    path = os.path.join(common.MODELS_DIR, name + ".glb")
    objs = WB.reimport(path)
    target = tgt if tgt else ((0, 0, 0) if dist else None)
    out = out or os.path.join(common.out("previews"), "%s_review_p%d_y%d%s.png" % (name, pitch, yaw, "_d%d" % dist if dist else ""))
    WR.beauty(objs, out, res=(int(W), int(H)), samples=int(spp), pitch=pitch, yaw=yaw, fill=fill, dist=dist,
              target=target)
    print("[ironart] review", out)


if __name__ == "__main__":
    main()
