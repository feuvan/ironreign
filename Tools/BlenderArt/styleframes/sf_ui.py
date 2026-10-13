"""Style frame (e): 192x64 red-lacquer 9-slice button + 128x128 parchment 9-slice panel.

    Tools/BlenderArt/render.sh Tools/BlenderArt/styleframes/sf_ui.py [out_dir]

UI pieces are real 3D slabs swept from a cross-section profile (:func:`geometry.profile_sweep`)
around a rounded rectangle, lit by the *calibrated* UI rig (flat tops render at exactly their
palette albedo), rendered top-down at 4x and Lanczos-downsampled.  All ornament stays inside the
9-slice margins (button 20 px horizontal / 16 px vertical, panel 24 px) so the centre stretches
cleanly - the preview sheet proves it.

Scene scale: 1 target pixel = 1 mm.
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import numpy as np  # noqa: E402

from ironart import cameras, geometry as geo, ink, lights, materials as M, post, scene  # noqa: E402

SS = 4
MM = 0.001


def px(v):
    return v * MM


def ui_scene(w, h, seed):
    scene.reset(seed=seed)
    scene.setup_cycles(samples=48, transparent=True, preset="ui", view="Standard")
    scene.set_resolution(w, h, SS)
    cam = cameras.ortho_top_down((0, 0), width=px(w), height=px(h))
    lights.rig_ui(cam, flat_gain=1.0, ambient=0.2)
    return cam


def button(out):
    W, H = 192, 64
    cam = ui_scene(W, H, 1)
    mats = {
        "LacquerDark": M.lacquer("LacquerDark", "LacquerDark", roughness=0.35, vary=0.05),
        "Lacquer": M.lacquer("Lacquer", "Lacquer", roughness=0.3, coat=1.0, vary=0.04),
        "Gold": M.gold_leaf("Gold", "Gold", roughness=0.3, vary=0.08),
        "Groove": M.principled("Groove", "#2A0D09", 0.6),
    }
    mb = geo.MeshBuilder()
    prof = [(0.0, 0.0), (0.0, 2.6), (0.7, 3.6), (2.0, 4.1), (3.3, 3.9), (4.0, 3.3),
            (4.6, 3.5), (5.2, 4.5), (6.0, 4.9), (6.8, 4.5), (7.4, 3.5),
            (8.0, 3.3), (8.8, 3.7), (10.5, 4.3), (12.5, 4.5)]
    mats_seq = (["LacquerDark"] * 4 + ["Groove"] + ["Gold"] * 5 + ["Groove"] + ["Lacquer"] * 3)
    geo.profile_sweep(mb, px(W), px(H), px(9), [(px(a), px(b)) for a, b in prof], "Lacquer",
                      corner_segments=8, fill_top=True, fill_mat="Lacquer", mats=mats_seq)
    obj = mb.build("Button", mats)
    ink.enable(thickness_px=1.0, inner_scale=0.0, as_pass=True, calligraphy=0.0,
               pressure_noise=0.0, taper=False)
    post.comp_painterly(size=0, ink=True, ink_opacity=0.85)
    raw = os.path.join(out, "ui_button_raw_%dx.png" % SS)
    t = scene.render(raw)
    img = post.load(raw)
    img = post.downsample(img, SS)
    img = post.alpha_cleanup(img, bleed=2)
    final = os.path.join(out, "sf_button_192x64.png")
    post.save(img, final)
    return img, t


def panel(out):
    W, H = 128, 128
    cam = ui_scene(W, H, 2)
    mats = {
        "Paper": M.parchment("Paper", "Paper", fibre=0.35, stain=0.05),
        "PaperEdge": M.parchment("PaperEdge", "PaperDark", fibre=0.4, stain=0.08),
        "Ink": M.principled("Ink", "Ink", 0.7),
        "Gold": M.gold_leaf("Gold", "Gold", roughness=0.3, vary=0.08),
    }
    mb = geo.MeshBuilder()
    # paper slab: slightly darker, raised deckled rim, then flat field
    geo.profile_sweep(mb, px(W), px(H), px(6), [(px(a), px(b)) for a, b in
                      [(0.0, 0.0), (0.0, 1.6), (0.8, 2.2), (2.0, 2.0), (3.0, 1.8)]],
                      "PaperEdge", corner_segments=6, mats=["PaperEdge"] * 4)
    # ink line (inlaid) at 3.5-5 px
    geo.profile_sweep(mb, px(W), px(H), px(6), [(px(a), px(b)) for a, b in
                      [(3.0, 1.8), (3.6, 1.95), (4.9, 1.95), (5.5, 1.8)]],
                      "Ink", corner_segments=6, mats=["Ink"] * 3)
    geo.profile_sweep(mb, px(W), px(H), px(6), [(px(a), px(b)) for a, b in
                      [(5.5, 1.8), (8.0, 1.8), (14.0, 1.8)]], "PaperEdge", corner_segments=6,
                      mats=["PaperEdge", "Paper"])
    # gold inner trim (raised moulding) at 14-19 px
    geo.profile_sweep(mb, px(W), px(H), px(6), [(px(a), px(b)) for a, b in
                      [(14.0, 1.8), (14.6, 2.5), (15.6, 3.0), (16.6, 3.0), (17.6, 2.5), (18.2, 1.8)]],
                      "Gold", corner_segments=6, mats=["Gold"] * 5)
    geo.profile_sweep(mb, px(W), px(H), px(6), [(px(a), px(b)) for a, b in
                      [(18.2, 1.8), (19.0, 1.8)]], "Paper", corner_segments=6, fill_top=True,
                      fill_mat="Paper", mats=["Paper"])
    # corner ornaments: gold L-brackets with a small boss, between the ink line and the trim
    for sx in (1, -1):
        for sy in (1, -1):
            cx, cy = sx * px(W / 2), sy * px(H / 2)
            a = (cx - sx * px(8.5), cy - sy * px(12.5), px(2.0))
            b = (cx - sx * px(8.5), cy - sy * px(8.5), px(2.0))
            c = (cx - sx * px(12.5), cy - sy * px(8.5), px(2.0))
            mb.tube([a, b, c], px(0.75), "Gold", 6)
            mb.sphere((cx - sx * px(11.0), cy - sy * px(11.0), px(2.0)), px(1.2), "Gold", 10, 6,
                      scale=(1, 1, 0.6))
    obj = mb.build("Panel", mats)
    ink.enable(thickness_px=1.0, inner_scale=0.0, as_pass=True, calligraphy=0.0,
               pressure_noise=0.0, taper=False)
    post.comp_painterly(size=0, ink=True, ink_opacity=0.8)
    raw = os.path.join(out, "ui_panel_raw_%dx.png" % SS)
    t = scene.render(raw)
    img = post.load(raw)
    img = post.downsample(img, SS)
    img = post.alpha_cleanup(img, bleed=2)
    final = os.path.join(out, "sf_panel_128.png")
    post.save(img, final)
    return img, t


def main():
    out = scene.args()[0] if scene.args() else os.path.join(os.environ["IRONART_OUT"], "styleframes")
    os.makedirs(out, exist_ok=True)
    b, tb = button(out)
    p, tp = panel(out)
    prev_b = post.nine_slice_preview(b, (20, 16, 20, 16), [(320, 64), (140, 48), (192, 96)])
    prev_p = post.nine_slice_preview(p, (24, 24, 24, 24), [(360, 200), (80, 160)])
    sheet = post.contact_sheet([(prev_b, "button 192x64 + 9-slice"), (prev_p, "panel 128 + 9-slice")],
                               cols=1)
    post.save(sheet, os.path.join(out, "sf_ui_sheet.png"))
    print("[ironart] TIMES", {"button_render": round(tb, 2), "panel_render": round(tp, 2)})


main()
