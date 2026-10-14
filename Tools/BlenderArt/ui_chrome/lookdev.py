"""Look-dev helper (system python3, no Blender): paint one piece through the numpy path and
write the @1x / @2x images, a nearest-neighbour zoom and a 9-slice check to the preview dir.

    python3 Tools/BlenderArt/ui_chrome/lookdev.py panel [variant] [--zoom 4] [--ss 4]
"""

import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import common  # noqa: E402
from ironart import post  # noqa: E402


def zoom(img, k, bg=(0.45, 0.45, 0.45)):
    a = img[..., 3:4]
    rgb = img[..., :3] * a + np.array(bg, np.float32) * (1 - a)
    im = Image.fromarray((np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")
    return im.resize((im.width * k, im.height * k), Image.NEAREST)


def main():
    args = [a for a in sys.argv[1:] if a != "--sheets"]
    k = 4
    if "--zoom" in args:
        i = args.index("--zoom")
        k = int(args[i + 1])
        del args[i:i + 2]
    out = os.environ.get("LOOKDEV_OUT") or common.out_dir("lookdev")
    art = os.path.join(out, "art")
    os.makedirs(art, exist_ok=True)
    jobs = []
    for spec in args:
        name, _, only = spec.partition(":")
        mod = importlib.import_module(name)
        vs = getattr(mod, "VARIANTS", (None,))
        if only:
            vs = [v for v in vs if v in only.split(",")]
        jobs += [(mod, v) for v in vs]
    for mod, variant in jobs:
        res = common.render_piece(mod, variant, numpy_only=True)
        fname = mod.FILE[variant] if hasattr(mod, "FILE") else mod.NAME
        post.save(res["img1"], os.path.join(art, fname + ".png"))
        post.save(res["img2"], os.path.join(art, fname + "@2x.png"))
        zoom(res["img1"], k).save(os.path.join(out, fname + "_z%d.png" % k))
        zoom(res["img2"], max(1, k // 2)).save(os.path.join(out, fname + "@2x_z%d.png" % max(1, k // 2)))
    if "--sheets" in sys.argv:
        os.environ["IRONART_UI_ART"] = art
        os.environ["IRONART_UI_SRC"] = art
        import importlib as il
        import preview
        il.reload(preview)
        preview.main(out)
    print("lookdev ->", out)


if __name__ == "__main__":
    main()
