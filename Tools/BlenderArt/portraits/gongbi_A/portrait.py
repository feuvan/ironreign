"""Gongbi officer portrait (approach A: 3D forms + Freestyle brush lines + decal features).

Run inside Blender (headless):

    blender -b --factory-startup -noaudio -P portrait.py -- <spec key> <out dir> [--ss 3]
          [--samples 12] [--keep]

Pipeline: spec -> MakeHuman head (neutral race blend, canon feature targets) -> decal features
-> hair / headgear / costume builders -> Cycles AOV paint passes + Freestyle line pass ->
finish.py (system python3) lays washes and lines on aged silk -> 384x480 + 192x240.
"""

import math
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.abspath(os.path.join(HERE, "..", ".."))
for p in (HERE, TOOLS):
    if p not in sys.path:
        sys.path.insert(0, p)

import bpy  # noqa: E402
import numpy as np  # noqa: E402

import face  # noqa: E402
import geo  # noqa: E402
import head  # noqa: E402
import lines  # noqa: E402
import render  # noqa: E402
import shade  # noqa: E402


class Ctx:
    """Everything a builder needs: collections, root, head, materials, spec, rng."""


def build(spec, ss=3, samples=6, size=(384, 480)):
    from ironart import scene as S
    S.reset(seed=spec.get("seed", 0))
    rng = np.random.default_rng(spec.get("seed", 0))
    sc = render.setup(size[0], size[1], ss, samples)
    C = Ctx()
    C.spec = spec
    C.rng = rng
    C.ss = ss
    C.cols = {k: geo.collection(k) for k in ("skin", "robe", "hair", "fine", "nolines")}
    root = bpy.data.objects.new("Root", None)
    sc.collection.objects.link(root)
    C.root = root
    tmp = shade.flat("SkinTmp", "skin_warm")
    H = head.build(spec["body"], C.cols["skin"], C.cols["nolines"], tmp, root)
    C.H = H
    skin_cfg = face.skin_config(H, spec["face"])
    C.skin_cfg = skin_cfg
    spec["face"].setdefault("far", 1 if spec.get("yaw", 28.0) >= 0 else -1)
    sk = shade.skin(
        "Skin", skin_cfg["base"], skin_cfg["rouge"], skin_cfg["blobs"], skin_cfg["light_blobs"],
        shade_tint=spec["face"].get("skin", {}).get("shade_tint", "#B97B62"),
        ao=spec["face"].get("skin", {}).get("ao", 0.7),
        edge=spec["face"].get("skin", {}).get("edge", 0.5))
    for ob in [H.obj] + H.eyeballs:
        ob.data.materials.clear()
        ob.data.materials.append(sk)
    C.skin_mat = sk
    sks = spec["face"].get("skin", {})
    face.SKIN_SHADE.update(ao=sks.get("ao", 0.7), edge=sks.get("edge", 0.5),
                           tint=sks.get("shade_tint", "#B97B62"))
    F = face.Face(H, spec["face"], C.cols["nolines"], root, skin_cfg)
    F.build()
    # builders (hair, headgear, costume) register through the spec
    for b in spec.get("builders", []):
        b(C)
    # pose: yaw (3/4 view), slight tilt
    root.rotation_euler = (math.radians(spec.get("pitch", 5.0)),
                           math.radians(spec.get("roll", 0.0)),
                           math.radians(spec.get("yaw", 28.0)))
    bpy.context.view_layer.update()
    # framing: eye line 38 % from the top, head (menton..crown) = head_frac of the frame
    lm = H.lm
    head_h = lm["crown"][2] - lm["menton"][2]
    frame_h = head_h / spec.get("head_frac", 0.46)
    # headgear must fit: keep >= top_margin target px above the highest point
    from mathutils import Vector
    top = -1e9
    for ob in bpy.data.objects:
        if ob.type in ("MESH", "CURVES"):
            for c in ob.bound_box:
                top = max(top, (ob.matrix_world @ Vector(c)).z)
    ez0 = (np.array(root.matrix_world)[:3, :3] @ np.array([0.0, lm["nasion"][1], H.eye_z])
           + np.array(root.matrix_world)[:3, 3])[2]
    el = spec.get("eye_line", 0.38)
    need = (top - ez0) / (el - spec.get("top_margin", 10) / size[1])
    if need > frame_h:
        frame_h = need
    C.frame_h = frame_h
    M = np.array(root.matrix_world)
    hc = M[:3, :3] @ np.array([0.0, lm["nose_tip"][1] + 0.085, H.eye_z]) + M[:3, 3]
    ez = (M[:3, :3] @ np.array([0.0, lm["nasion"][1], H.eye_z]) + M[:3, 3])[2]
    yaw_sign = 1 if spec.get("yaw", 28.0) >= 0 else -1
    cx = hc[0] + spec.get("frame_dx", 0.0) * frame_h * yaw_sign
    render.camera(cx, ez, frame_h, spec.get("eye_line", 0.38), size[0], size[1])
    lines.enable({k: C.cols[k] for k in ("skin", "robe", "hair", "fine")}, ss,
                 spec.get("lines", {}))
    return C


def run(spec, outdir, ss=3, samples=6, keep=False, size=(384, 480)):
    t0 = time.time()
    C = build(spec, ss, samples, size)
    tb = time.time() - t0
    tmp = os.path.join(outdir, "_passes_" + spec["key"])
    tr = render.render(tmp)
    npz = render.to_npz(tmp, os.path.join(tmp, "passes.npz"))
    out = os.path.join(outdir, spec["key"] + ".png")
    t1 = time.time()
    cmd = ["python3", os.path.join(HERE, "finish.py"), npz, out, "--size", "%dx%d" % size,
           "--seed", str(spec.get("seed", 1)), "--silk", spec.get("silk", "#DCCAA4")]
    if keep:
        cmd.append("--debug")
    subprocess.run(cmd, check=True)
    tf = time.time() - t1
    print("[gongbi] %s build %.1fs render %.1fs finish %.1fs total %.1fs" % (
        spec["key"], tb, tr, tf, time.time() - t0))
    return out


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    key, outdir = argv[0], argv[1]
    ss = int(argv[argv.index("--ss") + 1]) if "--ss" in argv else 3
    samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 6
    import specs
    spec = specs.get(key)
    run(spec, outdir, ss, samples, "--keep" in argv)


if __name__ == "__main__":
    main()
