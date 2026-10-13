"""Style frame (c): 128x111 flat-top forest hex tile, transparent outside the hexagon.

    Tools/BlenderArt/render.sh Tools/BlenderArt/styleframes/sf_hex_forest.py [out_dir]

Hex convention (DESIGN.md): flat-top, width 128 = 2r (r = 64 px), height round(sqrt(3) * 64) = 111.
In the scene r = 1 m, so 64 px per metre; the top-down ortho camera covers exactly 2 m x 1.734 m
and :func:`ironart.post.hex_mask` cuts the alpha.  Ground extends past the hexagon so the mask
edge is always clean.
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from ironart import cameras, geometry as geo, ink, lights, materials as M, post, scene  # noqa: E402

W, H = 128, 111
SS = 4


def build_forest(mb, rng, r=1.0, density=1.0):
    """Mixed forest on a grass hex: broadleaf canopy clusters + a few pines, inside 0.9 r."""
    geo.hex_prism(mb, (0, 0, -0.05), r * 1.12, 0.05, "Ground")
    inner = [(x * 0.86, y * 0.86) for x, y in geo.hex_points(r)]

    def inside(p, poly):
        x, y = p
        for i in range(6):
            x0, y0 = poly[i]
            x1, y1 = poly[(i + 1) % 6]
            if (x1 - x0) * (y - y0) - (y1 - y0) * (x - x0) < 0:
                return False
        return True

    def cand():
        p = (rng.uniform(-r, r), rng.uniform(-r, r))
        return p if inside(p, inner) else None

    pts = geo.scatter(rng, int(44 * density), cand, min_dist=0.16)
    leaves = ["Foliage", "Foliage", "FoliageLight", "FoliageYellow", "FoliageDark"]
    for i, (x, y) in enumerate(pts):
        kind = rng.random()
        if kind < 0.15:
            geo.tree_pine(mb, (x, y, 0), height=rng.uniform(0.42, 0.55),
                          radius=rng.uniform(0.11, 0.14), rng=rng, leaf="FoliagePine", detail=1)
        else:
            geo.tree_broadleaf(mb, (x, y, 0), height=rng.uniform(0.3, 0.45),
                               radius=rng.uniform(0.11, 0.16), rng=rng,
                               leaf=rng.choice(leaves), blobs=rng.choice((5, 6, 7)))
    # undergrowth bushes and rocks along the clearing
    for _ in range(10):
        p = cand()
        if p:
            geo.tree_broadleaf(mb, (p[0], p[1], -0.05), height=0.12, radius=0.07, rng=rng,
                               leaf="FoliageLight", blobs=3)
    for _ in range(3):
        p = cand()
        if p:
            geo.rock(mb, (p[0], p[1], 0.0), 0.05, rng)


def main():
    out = scene.args()[0] if scene.args() else os.path.join(os.environ["IRONART_OUT"], "styleframes")
    times = {}
    scene.reset(seed=5)
    rng = random.Random(5)
    scene.setup_cycles(samples=48, transparent=True, preset="sprite", view="Standard")
    scene.set_resolution(W, H, SS)
    with scene.timer("build", times):
        mats = {
            "Ground": M.grass_ground("Ground", "grass", "#A39A62", scale=1.6),
            "Foliage": M.foliage("Foliage", "forest"),
            "FoliageDark": M.foliage("FoliageDark", "#3A5536"),
            "FoliageLight": M.foliage("FoliageLight", "forest_light"),
            "FoliageYellow": M.foliage("FoliageYellow", "#7A8A48"),
            "FoliagePine": M.foliage("FoliagePine", "#35523E", translucency=0.05),
            "Trunk": M.principled("Trunk", "trunk", 0.8),
            "Rock": M.rock("Rock"),
        }
        mb = geo.MeshBuilder()
        build_forest(mb, rng)
        obj = mb.build("Forest", mats)
        for k in ("Foliage", "FoliageDark", "FoliageLight", "FoliageYellow", "FoliagePine"):
            M.paint(mats[k], 0.3)
    cam = cameras.ortho_top_down((0, 0), width=2.0)
    lights.rig_map(cam, key=3.2, sky=0.6, elevation_deg=42)
    ink.enable(thickness_px=0.55, alpha=0.7, inner_scale=0.7, inner_alpha=0.6, as_pass=True,
               crease=False, calligraphy=0.3)
    post.comp_painterly(size=7, sharpness=0.5, eccentricity=1.2, amount=0.85, ink_opacity=0.8)
    raw = os.path.join(out, "hex_forest_raw_%dx.png" % SS)
    times["render"] = scene.render(raw)
    with scene.timer("post", times):
        img = post.load(raw)
        img = post.downsample(img, SS)
        img = post.grade(img, saturation=1.08, contrast=1.06, warmth=0.015, brightness=0.02)
        img = post.apply_mask(img, post.hex_mask(W, H))
        img = post.alpha_cleanup(img, bleed=2)
        final = os.path.join(out, "sf_hex_forest_128x111.png")
        post.save(img, final)
        # board preview: 3 tiles in a flat-top layout
        # board preview: flat-top layout (column pitch 96 px, row pitch 111 px, odd columns +55.5)
        board = post.solid(96 * 3 + 32, 111 * 2 + 56, "#1B1712")
        for col in range(4):
            for row in range(3):
                board = post.paste(board, img, col * 96 - 16, row * 111 + (56 if col % 2 else 0) - 56)
        sheet = post.contact_sheet([(img, "128x111"), (board, "tiling")], cols=2)
        post.save(sheet, os.path.join(out, "sf_hex_forest_sheet.png"))
    print("[ironart] TIMES", {k: round(v, 2) for k, v in times.items()})


main()
