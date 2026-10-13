"""Overview contact sheet of the five style frames (system python3 or Blender's python).

    python3 Tools/BlenderArt/styleframes/make_sheet.py <styleframes_dir>
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from ironart import post  # noqa: E402

d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ.get("IRONART_OUT", "/tmp/ironart"), "styleframes")
items = []
for name, label, scale in [("sf_terrain_512x320.png", "(a) terrain 512x320", 1),
                           ("sf_city_96.png", "(b) city 96x96 (x2)", 2),
                           ("sf_hex_forest_128x111.png", "(c) hex 128x111 (x2)", 2),
                           ("sf_portrait_192x240.png", "(d) portrait 192x240", 1),
                           ("sf_button_192x64.png", "(e) button 192x64", 1),
                           ("sf_panel_128.png", "(e) panel 128 (x2)", 2)]:
    p = os.path.join(d, name)
    if os.path.exists(p):
        img = post.load(p)
        if scale != 1:
            img = post.resize(img, (img.shape[1] * scale, img.shape[0] * scale), "nearest")
        items.append((img, label))
sheet = post.contact_sheet(items, cols=3)
out = os.path.join(d, "styleframes_overview.png")
post.save(sheet, out)
print("[make_sheet] wrote", out)
