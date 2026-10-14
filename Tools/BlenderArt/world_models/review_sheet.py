"""Review sheets for the World Models family (scratch only, nothing committed).

    Tools/BlenderArt/render.sh Tools/BlenderArt/world_models/review_sheet.py [--no-turntables]

* turntables of every re-imported GLB (4 yaws at the game pitch) -> previews/<Name>_turntable.png
* sprites_context.png: the 2D fallbacks at the UI sizes (cities 46 / 58 / 74 px, sect marker,
  banners, pennants over the city icons) composited on the approved map style frame
* models_overview.png: the beauty / closest-zoom previews side by side
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

from ironart import REPO_DIR, scene, world_bake as WB, world_render as WR  # noqa: E402

MODELS = ["City_1", "City_2", "City_3", "Sect", "Banner", "Flag", "Tree_Pine", "Tree_Broad", "Tree_Bamboo"]
STYLEFRAME_MAP = os.path.join(os.path.dirname(os.environ.get("IRONART_OUT", "/tmp/ironart")), "blender",
                              "styleframes", "sf_terrain_512x320.png")


def turntables():
    for n in MODELS:
        p = os.path.join(common.MODELS_DIR, n + ".glb")
        if not os.path.isfile(p):
            continue
        objs = WB.reimport(p)
        city = n.startswith("City") or n == "Sect"
        WR.turntable(objs, os.path.join(common.out("previews"), "%s_turntable.png" % n),
                     res=(480, 300) if city else (320, 320), samples=16 if city else 20,
                     yaws=(-30, 60, 150, 240), pitch=45.0 if city else 25.0, fill=0.9)


def context_sheet():
    from PIL import Image, ImageDraw
    art = os.path.join(REPO_DIR, "Content", "Data", "Art", "Map")
    cand = [STYLEFRAME_MAP, os.path.join(os.environ.get("IRONART_OUT", "/tmp/ironart"), "styleframes",
                                         "sf_terrain_512x320.png")]
    bgp = next((c for c in cand if os.path.isfile(c)), None)
    bg = Image.open(bgp).convert("RGBA").resize((1024, 640), Image.BICUBIC) if bgp else \
        Image.new("RGBA", (1024, 640), (151, 162, 110, 255))
    im = {k: Image.open(os.path.join(art, k + ".png")).convert("RGBA")
          for k in ("City_1", "City_2", "City_3", "Sect", "Banner", "Flag")}
    d = ImageDraw.Draw(bg)
    # (city, icon px, anchor x, anchor y) - the UI draws the icon bottom-centred on the city point
    for (k, s, ax, ay) in (("City_1", 46, 300, 420), ("City_2", 58, 480, 380), ("City_3", 74, 700, 470)):
        icon = im[k].resize((s, s), Image.LANCZOS)
        bg.alpha_composite(icon, (ax - s // 2, ay - s))
        fh = int(s * 0.42)
        fw = int(fh * 32 / 48)
        flag = im["Flag"].resize((fw, fh), Image.LANCZOS)
        r, g, b, a = flag.split()
        tint = Image.merge("RGBA", (r.point(lambda v: v * 179 // 255), g.point(lambda v: v * 40 // 255),
                                    b.point(lambda v: v * 45 // 255), a))
        bg.alpha_composite(tint, (ax + int(s * 0.08), ay - s - int(fh * 0.45)))
        d.text((ax - 20, ay + 4), k, fill=(40, 30, 20, 255))
    sm = im["Sect"].resize((22, 22), Image.LANCZOS)
    bg.alpha_composite(sm, (480 - 29 - 12, 380 - 23))
    # banners (army markers) in three faction colours, glyph box outlined
    gx, gy, gw, gh = [int(v) for v in open(os.path.join(art, "BannerGlyphArea.txt")).read().split()]
    for (col, x) in (((179, 40, 45), 160), ((47, 109, 181), 840), ((76, 154, 60), 900)):
        bh = 64
        bw = bh * 64 // 96
        ban = im["Banner"].resize((bw, bh), Image.LANCZOS)
        r, g, b, a = ban.split()
        tint = Image.merge("RGBA", (r.point(lambda v, c=col[0]: v * c // 255), g.point(lambda v, c=col[1]: v * c // 255),
                                    b.point(lambda v, c=col[2]: v * c // 255), a))
        bg.alpha_composite(tint, (x - bw // 2, 560 - bh))
        k = bh / 96.0
        d.rectangle([x - bw // 2 + gx * k, 560 - bh + gy * k, x - bw // 2 + (gx + gw) * k, 560 - bh + (gy + gh) * k],
                    outline=(233, 220, 192, 255))
    bg.save(os.path.join(common.out(), "sprites_context.png"))
    # x4 sheet of every sprite on checker and on the map plain
    tiles = []
    for k in ("City_1", "City_2", "City_3", "Sect", "Banner", "Flag"):
        t = im[k].resize((im[k].width * 3, im[k].height * 3), Image.NEAREST)
        base = Image.new("RGBA", t.size, (151, 162, 110, 255))
        base.alpha_composite(t)
        tiles.append(base)
    W = sum(t.width for t in tiles) + 10 * (len(tiles) + 1)
    H = max(t.height for t in tiles) + 20
    sheet = Image.new("RGBA", (W, H), (42, 33, 25, 255))
    x = 10
    for t in tiles:
        sheet.alpha_composite(t, (x, 10))
        x += t.width + 10
    sheet.save(os.path.join(common.out(), "sprites_x3.png"))


def overview():
    from PIL import Image
    prev = common.out("previews")
    names = ["City_1_closest_zoom", "City_2_closest_zoom", "City_3_closest_zoom", "Sect_beauty", "Banner_beauty",
             "Flag_beauty", "Tree_Pine_beauty", "Tree_Broad_beauty", "Tree_Bamboo_beauty"]
    tiles = []
    for n in names:
        p = os.path.join(prev, n + ".png")
        if os.path.isfile(p):
            im = Image.open(p).convert("RGB")
            im.thumbnail((640, 400))
            tiles.append(im)
    if not tiles:
        return
    cols = 3
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 650 + 10, rows * 410 + 10), (30, 26, 22))
    for i, t in enumerate(tiles):
        sheet.paste(t, (10 + (i % cols) * 650, 10 + (i // cols) * 410))
    sheet.save(os.path.join(common.out(), "models_overview.png"))


def main():
    if "--no-turntables" not in sys.argv:
        turntables()
    context_sheet()
    overview()


if __name__ == "__main__":
    main()
