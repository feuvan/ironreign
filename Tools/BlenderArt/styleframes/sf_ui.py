"""Style frame (e): 192x64 red-lacquer 9-slice button + 128x128 parchment 9-slice panel.

    Tools/BlenderArt/render.sh Tools/BlenderArt/styleframes/sf_ui.py [out_dir]

UI pieces are real 3D slabs swept from a cross-section profile (:func:`geometry.profile_sweep`)
around a rounded rectangle, lit by the calibrated UI rig (white key + white ambient: a flat
face-up surface renders at its albedo), rendered top-down at 4x and Lanczos-downsampled (recipe
"ui": no Kuwahara, no paper, outer ink only).  1 target pixel = 1 mm.

Panel border (24 px):  0-9 lacquered dark wood (#3A2619) rolling into a LacquerDark bevel,
9-12 a 2.5 px gold bead (lit top-left), 12-24 aged paper PaperDark -> Paper over 10 px, gold
meander ("hui" pattern, 1.5 px stroke) in the four 24 px corners; Paper field.
Button: 3 px LacquerDark rim with a top-left catchlight, 2 px bevelled gold trim, gold L-bracket
corner fittings (7 x 7 px, 2 px boss) inside the 20 x 16 corners, Lacquer field with a vertical
gradient and a soft sheen band (+15 % at 25-40 % of the height).

QA (asserted): field means within 3 levels of their tokens; 9-slice border strips uniform along
the stretch direction (per-row / per-column std <= 2 levels); field mottling std <= 4.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import numpy as np  # noqa: E402

from ironart import geometry as geo, materials as M, post, recipes, scene  # noqa: E402

MM = 0.001
BUTTON_MARGINS = (20, 16, 20, 16)
PANEL_MARGINS = (24, 24, 24, 24)


def px(v):
    return v * MM


def ui_scene(w, h, seed):
    scene.reset(seed=seed)
    recipes.setup("ui", w, h)
    cam = recipes.camera("ui", width=px(w), height=px(h))
    recipes.light("ui", cam)
    return cam


def sweep(mb, w, h, r, prof, mats, **kw):
    """profile_sweep with a profile given in target px; returns the rings."""
    return geo.profile_sweep(mb, px(w), px(h), px(r), [(px(a), px(b)) for a, b in prof],
                             mats[0], mats=mats, **kw)


def corner_l(mb, cx, cy, sx, sy, arm, width, z, mat="GoldTrim", boss=2.0):
    """Gold L-bracket corner fitting: two flat arms of ``arm`` px from the corner (cx, cy) inwards
    (directions sx, sy) + a round boss on the corner."""
    t = width
    for (dx, dy) in ((1, 0), (0, 1)):
        x0, y0 = cx, cy
        x1 = cx + sx * (arm if dx else t)
        y1 = cy + sy * (arm if dy else t)
        mb.box(((px(x0) + px(x1)) / 2, (px(y0) + px(y1)) / 2, px(z)),
               (abs(px(x1 - x0)), abs(px(y1 - y0)), px(0.8)), mat)
    mb.sphere((px(cx + sx * t * 0.5), px(cy + sy * t * 0.5), px(z + 0.6)), px(boss / 2), mat, 12, 6,
              scale=(1, 1, 0.55))


def button(out):
    W, H = 192, 64
    cam = ui_scene(W, H, 1)
    mats = {
        "Rim": M.lacquer("Rim", "#3A1A12", roughness=0.5, coat=0.4, coat_roughness=0.05,
                         vary=0, specular=0.0),
        "GoldTrim": M.gold_leaf("GoldTrim", "Gold", roughness=0.32, uniform=True),
        "Groove": M.principled("Groove", "#2A0D09", 0.6),
        # UI lacquer: no broad specular (even level 0.12 lifts G/B by 7-9 levels), a sharp clear
        # coat that mirrors the dark zenith on the flat field and the bright ring on the bevels
        "Lacquer": M.lacquer("Lacquer", "Lacquer", roughness=0.5, coat=0.4, coat_roughness=0.04,
                             vary=0, gradient=0.12, sheen_band=0.15, band=(0.60, 0.75),
                             specular=0.0),
    }
    mb = geo.MeshBuilder()
    prof = [(0.0, 0.0), (0.0, 2.2), (0.35, 3.1), (1.1, 3.6), (2.3, 3.5), (3.0, 3.0),   # rim
            (3.25, 3.5), (3.8, 4.0), (4.5, 3.9), (5.0, 3.2),                           # gold
            (5.5, 2.7),                                                                # groove
            (6.4, 3.0), (8.0, 3.2)]                                                    # field
    seq = ["Rim"] * 5 + ["GoldTrim"] * 4 + ["Groove"] + ["Lacquer"] * 2
    sweep(mb, W, H, 8, prof, seq, corner_segments=8, fill_top=True, fill_mat="Lacquer")
    # corner fittings inside the 20 x 16 corners, on the lacquer field
    for sx in (1, -1):
        for sy in (1, -1):
            cx, cy = sx * (W / 2 - 6.5), sy * (H / 2 - 6.5)
            corner_l(mb, cx, cy, -sx, -sy, 7.0, 1.6, 3.2, boss=2.4)
    mb.build("Button", mats)
    recipes.ink("ui")
    recipes.paint("ui")
    raw = os.path.join(out, "ui_button_raw_4x.png")
    t = scene.render(raw)
    img = recipes.finish("ui", raw)
    post.save(img, os.path.join(out, "sf_button_192x64.png"))
    return img, t


def meander(mb, ox, oy, sx, sy, z, size=9.0, stroke=1.5, mat="GoldOrn"):
    """Square-spiral "hui" corner ornament, ``size`` px, inner corner of the border at (ox, oy),
    pointing into the panel along (sx, sy)."""
    s = size - stroke
    path = [(0, 0), (s, 0), (s, s), (stroke * 2, s), (stroke * 2, stroke * 2), (s - stroke * 2,
            stroke * 2), (s - stroke * 2, s - stroke * 2), (stroke * 4, s - stroke * 2)]
    o = stroke / 2
    pts = [(px(ox + sx * (o + a)), px(oy + sy * (o + b)), px(z + stroke * 0.3)) for a, b in path]
    # a round gold wire (catches the top-left key on its upper-left flank, like the bead)
    mb.tube(pts, px(stroke / 2), mat, 8)


def panel(out):
    W, H = 128, 128
    cam = ui_scene(W, H, 2)
    mats = {
        "Wood": M.lacquer("Wood", "dark_wood", roughness=0.5, coat=0.45, coat_roughness=0.05,
                          vary=0, specular=0.0),
        "WoodBevel": M.lacquer("WoodBevel", "LacquerDark", roughness=0.5, coat=0.5,
                               coat_roughness=0.05, vary=0, specular=0.0),
        "GoldOrn": M.principled("GoldOrn", "#D2AA50", roughness=0.35, metallic=0.55,
                                specular=0.5),
        "GoldTrim": M.gold_leaf("GoldTrim", "Gold", roughness=0.3, uniform=True),
        "Paper": M.parchment("Paper", "Paper", fibre=0.3, stain=0.012, edge_attr="edge_t",
                             edge_color="PaperDark"),
    }
    mb = geo.MeshBuilder()
    wood = [(0.0, 0.0), (0.0, 3.0), (0.5, 4.2), (1.5, 4.8), (7.0, 4.8), (8.2, 4.3), (9.0, 3.6)]
    gold = [(9.0, 3.6), (9.3, 4.3), (10.0, 4.8), (10.8, 4.8), (11.5, 4.3), (11.8, 3.6)]
    paper = [(11.8, 3.6), (12.0, 3.0), (14.0, 3.0), (16.0, 3.0), (18.0, 3.0), (20.0, 3.0),
             (22.0, 3.0), (24.0, 3.0)]
    sweep(mb, W, H, 4, wood, ["Wood"] * 4 + ["WoodBevel"] * 2, corner_segments=6)
    sweep(mb, W, H, 4, gold, ["GoldTrim"] * 5, corner_segments=6)
    s0 = mb.n
    rings = sweep(mb, W, H, 4, paper, ["Paper"] * 7, corner_segments=6, fill_top=True,
                  fill_mat="Paper")
    # aged edge: PaperDark at 12 px -> Paper at 22 px (per ring: uniform along every edge)
    for (inset, _z), ring in zip(paper, rings):
        t = float(np.clip((inset - 12.0) / 10.0, 0, 1))
        for vi in ring:
            mb.vattr.setdefault("edge_t", {})[vi] = t
    del s0
    for sx in (1, -1):
        for sy in (1, -1):
            meander(mb, sx * (W / 2 - 13.0), sy * (H / 2 - 13.0), -sx, -sy, 3.0)
    mb.build("Panel", mats)
    recipes.ink("ui")
    recipes.paint("ui")
    raw = os.path.join(out, "ui_panel_raw_4x.png")
    t = scene.render(raw)
    img = recipes.finish("ui", raw)
    post.save(img, os.path.join(out, "sf_panel_128.png"))
    return img, t


def main():
    out = scene.args()[0] if scene.args() else os.path.join(os.environ["IRONART_OUT"], "styleframes")
    os.makedirs(out, exist_ok=True)
    b, tb = button(out)
    p, tp = panel(out)
    prev_b = post.nine_slice_preview(b, BUTTON_MARGINS, [(320, 64), (140, 48), (192, 96)])
    prev_p = post.nine_slice_preview(p, PANEL_MARGINS, [(360, 200), (80, 160)])
    sheet = post.contact_sheet([(prev_b, "button 192x64 + 9-slice"),
                                (prev_p, "panel 128 + 9-slice")], cols=1, scale=2)
    post.save(sheet, os.path.join(out, "sf_ui_sheet.png"))
    qa = post.QA("ui")
    qa.color("button field (centre row)", post.region_mean(b, (24, 31, 168, 33)), "Lacquer", 3)
    qa.color("panel field", post.region_mean(p, (30, 30, 98, 98)), "Paper", 3)
    br, bc = post.nine_slice_uniformity(b, BUTTON_MARGINS)
    pr, pc = post.nine_slice_uniformity(p, PANEL_MARGINS)
    qa.max("panel border row std (raw, no detrend)",
           post.nine_slice_uniformity(p, PANEL_MARGINS, detrend=False)[0], 2.5)
    qa.max("button border row std", br, 2.0)
    qa.max("button border column std", bc, 2.0)
    qa.max("panel border row std", pr, 2.0)
    qa.max("panel border column std", pc, 2.0)
    qa.max("panel field mottling std", float(p[30:98, 30:98, :3].std(axis=(0, 1)).max() * 255), 4.0)
    qa.max("button field row std (stretch)", float(b[16:48, 20:172, :3].std(axis=1).max() * 255), 2.0)
    print("[ironart] TIMES", {"button_render": round(tb, 2), "panel_render": round(tp, 2)})
    qa.check()


if __name__ == "__main__":
    main()
