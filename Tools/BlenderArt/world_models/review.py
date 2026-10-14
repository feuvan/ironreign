"""Gongbi review renders of the exported World Models (re-imported GLBs, no rebuild).

    Tools/BlenderArt/render.sh Tools/BlenderArt/world_models/review.py [City_1 Tree_Pine ...] [--sheet]

Each GLB in ArtSource/Models is re-imported into a clean scene and rendered with
ironart.world_gongbi_render.preview (soft shadowless light + Freestyle ink on aged silk, an
approximation of Unreal's painted post-process) to <scratch>/previews/<Name>_gongbi.png;
``--sheet`` also writes previews/World_Models_gongbi_sheet.png (all nine).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

from ironart import world_bake as WB, world_gongbi_render as GR  # noqa: E402

#: name: preview kwargs
VIEWS = {
    "City_1": dict(res=(1280, 800), pitch=48.0, yaw=-20.0, fill=0.84),
    "City_2": dict(res=(1280, 800), pitch=48.0, yaw=-20.0, fill=0.84),
    "City_3": dict(res=(1280, 800), pitch=48.0, yaw=-20.0, fill=0.84),
    "Sect": dict(res=(960, 800), pitch=38.0, yaw=-25.0, fill=0.92),
    "Banner": dict(res=(640, 800), pitch=12.0, yaw=-30.0, target=(2.0, 0.0, 11.8), dist=44.0),
    "Flag": dict(res=(640, 800), pitch=12.0, yaw=-30.0, target=(1.4, 0.0, 5.3), dist=21.0),
    "Tree_Pine": dict(res=(640, 640), pitch=24.0, yaw=-20.0, fill=0.9),
    "Tree_Broad": dict(res=(640, 640), pitch=24.0, yaw=-20.0, fill=0.9),
    "Tree_Bamboo": dict(res=(640, 640), pitch=24.0, yaw=-20.0, fill=0.9),
}


def render(name, samples=24):
    objs = WB.reimport(os.path.join(common.MODELS_DIR, name + ".glb"))
    path = os.path.join(common.out("previews"), "%s_gongbi.png" % name)
    secs = GR.preview(objs, path, samples=samples, ink_px=1.1, **VIEWS[name])
    return path, secs


def sheet(paths, out):
    from PIL import Image
    ims = [Image.open(p).convert("RGB") for p in paths]
    h = 400
    ims = [im.resize((int(im.width * h / im.height), h), Image.LANCZOS) for im in ims]
    rows = [ims[:3], ims[3:6], ims[6:]]
    W = max(sum(i.width for i in r) for r in rows if r)
    sh = Image.new("RGB", (W, h * len([r for r in rows if r])), (230, 216, 184))
    for j, r in enumerate([r for r in rows if r]):
        x = 0
        for im in r:
            sh.paste(im, (x, j * h))
            x += im.width
    sh.save(out)
    return out


def main():
    fl = common.flags()
    names = [n for n in fl["names"] if n in VIEWS] or list(VIEWS)
    paths = []
    for n in names:
        p, secs = render(n, 12 if fl["preview"] else 24)
        print("[ironart] review %s -> %s (%.1fs)" % (n, p, secs))
        paths.append(p)
    if "--sheet" in sys.argv:
        print("[ironart] sheet", sheet(paths, os.path.join(common.out("previews"), "World_Models_gongbi_sheet.png")))


if __name__ == "__main__":
    main()
