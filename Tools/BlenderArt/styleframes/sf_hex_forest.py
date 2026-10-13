"""Style frame (c): 128x111 flat-top forest hex tile, transparent outside the hexagon.

    Tools/BlenderArt/render.sh Tools/BlenderArt/styleframes/sf_hex_forest.py [out_dir] [--variant N]

Hex convention (DESIGN.md): flat-top, width 128 = 2r (r = 64 px), height round(sqrt(3) * 64) = 111.
In the scene r = 1 m (64 px per metre); the top-down ortho camera covers exactly 2 m x 1.734 m and
:func:`ironart.post.hex_mask` cuts the alpha.

Tiling rules (recipe "hex"): forest floor painted out to 1.12 r, trunks out to 0.98 r with
canopies crossing the hex edge (the mask cuts them) and a radially uniform density, so neighbouring
forest tiles meet canopy to canopy.  The studio sun (135 / 50) as on the world map.  Ink only on
canopy silhouettes.  QA (asserted): gap floor value, lit/shadow canopy hue swing, seam contrast in
the tiling preview.
"""

import colorsys
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import numpy as np  # noqa: E402

from ironart import cameras, geometry as geo, materials as M, post, recipes, scene  # noqa: E402

W, H = 128, 111
VARIANT = int(sys.argv[sys.argv.index("--variant") + 1]) if "--variant" in sys.argv else 0


def forest_materials():
    return {
        "Ground": M.grass_ground("Ground", "#5E7244", "#5E7244", scale=1.6),
        "Foliage": M.foliage("Foliage", "#5A7E48", vary=0.14, translucency=0.06),
        "FoliageDark": M.foliage("FoliageDark", "#4A6E42", vary=0.14, translucency=0.06),
        "FoliageLight": M.foliage("FoliageLight", "#6E8C50", vary=0.14, translucency=0.06),
        "FoliagePine": M.foliage("FoliagePine", "#466A48", vary=0.12, translucency=0.04),
        "Trunk": M.principled("Trunk", "trunk", 0.8),
    }


#: flat-top hex lattice (r = 1): the 6 neighbour offsets (board column pitch 1.5 = 96 px,
#: row pitch sqrt(3) = 111 px)
LATTICE = [(1.5, 3 ** 0.5 / 2), (1.5, -3 ** 0.5 / 2), (-1.5, 3 ** 0.5 / 2), (-1.5, -3 ** 0.5 / 2),
           (0.0, 3 ** 0.5), (0.0, -3 ** 0.5)]
EDGE_SEED = 777          # shared by every variant: the edge band is identical, so variants mix


def hex_metric(x, y, r=1.0):
    """1.0 on the flat-top hex boundary of radius ``r`` (max over the 3 edge normals / apothem)."""
    a = r * 3 ** 0.5 / 2
    return max(abs(y), abs(x * 0.8660254 + y * 0.5), abs(x * 0.8660254 - y * 0.5)) / a


def tree(tb, x, y, key, leaves, pine_ratio):
    """One tree whose shape depends only on ``key`` (so periodic copies are identical)."""
    rng = random.Random(key)
    if rng.random() < pine_ratio:
        geo.tree_pine(tb, (x, y, 0), height=rng.uniform(0.22, 0.28),
                      radius=rng.uniform(0.075, 0.095), rng=rng, leaf="FoliagePine", detail=1)
    else:
        geo.tree_broadleaf(tb, (x, y, 0), height=rng.uniform(0.16, 0.21),
                           radius=rng.uniform(0.07, 0.10), rng=rng, leaf=rng.choice(leaves),
                           blobs=rng.choice((7, 8, 9)))


def build_forest(rng, r=1.0, density=54.0, pine_ratio=0.27, edge_band=0.72, min_dist=0.102):
    """Periodic forest on the hex lattice. Returns (ground, trees, n_trees, trees_collection).

    * edge band (hex metric > ``edge_band``): Poisson points from the shared :data:`EDGE_SEED`
      - the same in every variant - copied to the 6 lattice neighbours, so a canopy cut by this
      tile's mask continues in the neighbour exactly (seamless, identical shadows across the edge)
    * interior: Poisson points from the variant ``rng``
    * forest floor: one flat colour with fine speckle only (no low-frequency blotches that would
      differ across the seam), out to 1.12 r
    """
    gb = geo.MeshBuilder()
    geo.hex_prism(gb, (0, 0, -0.05), r * 1.12, 0.05, "Ground")
    tb = geo.MeshBuilder()
    area = 3 * 3 ** 0.5 / 2 * r * r
    ergn = random.Random(EDGE_SEED)

    def cand(rr, lo, hi):
        def f():
            p = (rr.uniform(-r, r), rr.uniform(-r, r))
            return p if lo <= hex_metric(*p, r) < hi else None
        return f

    def periodic_ok(p, pts):
        # min distance against existing points and their lattice copies
        for q in pts:
            for ox, oy in [(0.0, 0.0)] + LATTICE:
                if (p[0] - q[0] - ox) ** 2 + (p[1] - q[1] - oy) ** 2 < min_dist ** 2:
                    return False
        return True

    edge_pts = []
    n_edge = int(density * area * (1 - edge_band ** 2))
    for _ in range(n_edge):
        for _t in range(80):
            p = cand(ergn, edge_band, 1.0)()
            if p and periodic_ok(p, edge_pts):
                edge_pts.append(p)
                break
    pts = list(edge_pts)
    n_in = int(density * area * edge_band ** 2)
    for _ in range(n_in):
        for _t in range(80):
            p = cand(rng, 0.0, edge_band)()
            if p and periodic_ok(p, pts):
                pts.append(p)
                break
    leaves = ["Foliage", "Foliage", "FoliageLight", "FoliageDark"]
    n = 0
    for i, (x, y) in enumerate(pts):
        key = (EDGE_SEED if i < len(edge_pts) else rng.random(), round(x, 4), round(y, 4))
        key = hash(key) & 0xFFFFFFFF
        tree(tb, x, y, key, leaves, pine_ratio)
        n += 1
        if i < len(edge_pts):
            for ox, oy in LATTICE:
                if hex_metric(x + ox, y + oy, r) < 1.18:
                    tree(tb, x + ox, y + oy, key, leaves, pine_ratio)
    ground = gb.build("HexGround", MATS)
    col = scene.collection("Trees")
    trees = tb.build("HexTrees", MATS, col=col)
    return ground, trees, n, col


MATS = {}


def tiling_preview(img, cols=4, rows=3):
    """Flat-top board: column pitch 96 px, row pitch 111 px, odd columns +55.5 px."""
    board = post.solid(96 * (cols - 1) + 128, 111 * rows + 56, "#1B1712")
    for c in range(cols):
        for rr in range(rows):
            board = post.paste(board, img, c * 96, rr * 111 + (56 if c % 2 else 0))
    return board


def main():
    a = [x for x in scene.args() if not x.startswith("--") and not x.isdigit()]
    out = a[0] if a else os.path.join(os.environ["IRONART_OUT"], "styleframes")
    os.makedirs(out, exist_ok=True)
    times = {}
    seed = 5 + 101 * VARIANT
    scene.reset(seed=seed)
    rng = random.Random(seed)
    recipes.setup("hex", W, H)
    with scene.timer("build", times):
        MATS.update(forest_materials())
        ground, trees, n, col = build_forest(rng)
        for k in ("Foliage", "FoliageDark", "FoliageLight", "FoliagePine"):
            M.paint(MATS[k], 0.4, 0.8, 0.1)
        print("[ironart] trees", n)
    cam = recipes.camera("hex")
    recipes.light("hex", cam)
    recipes.ink("hex", collection=col)
    recipes.paint("hex")
    raw = os.path.join(out, "hex_forest_raw_4x.png")
    import bpy
    rl = bpy.context.scene.node_tree.nodes["Render Layers"]
    post.comp_outputs(out, {"hex_ink": rl.outputs["Freestyle"]})
    times["render"] = scene.render(raw)
    samples = cameras.surface_samples(cam)
    with scene.timer("post", times):
        img = recipes.finish("hex", raw)
        suffix = "" if VARIANT == 0 else "_v%d" % VARIANT
        post.save(img, os.path.join(out, "sf_hex_forest%s_128x111.png" % suffix))
        board = tiling_preview(img)
        sheet = post.contact_sheet([(post.resize(img, (256, 222), "nearest"), "128x111 (x2)"),
                                    (board, "tiling (1:1)")], cols=2)
        post.save(sheet, os.path.join(out, "sf_hex_forest%s_sheet.png" % suffix))
    # ---- QA
    qa = post.QA("hex")
    mask = post.hex_mask(W, H, inset=3) > 0.99
    rgb = img[..., :3][mask]
    hsv = np.array([colorsys.rgb_to_hsv(*p) for p in rgb[::3]])
    # gap floor: the darkest paint that is not an ink stroke (ink pass written next to the raw)
    ink_a = post.downsample(post.load(post.pass_path(out, "hex_ink")), 4)[..., 3]
    paint = mask & (ink_a < 0.15)
    vmax = img[..., :3].max(-1)
    floor = paint & (samples["mat"] == "Ground")
    leaf = paint & np.char.startswith(samples["mat"].astype(str), "Foliage")
    qa.range("gap floor value (p5 HSV v, ground)", float(np.percentile(vmax[floor], 5)), 0.22, 1.0)
    qa.range("canopy shadow value (p5 HSV v)", float(np.percentile(vmax[leaf], 5)), 0.18, 1.0)
    print("[ironart] ground px %d (%.0f %%), canopy px %d" % (floor.sum(), 100 * floor.sum() / mask.sum(),
                                                             leaf.sum()))
    qa.range("ink coverage (alpha > 0.1)", float((ink_a[mask] > 0.1).mean()), 0.03, 0.25)
    lum = post.luma8(img)[mask][::3]
    lit = hsv[lum >= np.percentile(lum, 80)]
    shd = hsv[lum <= np.percentile(lum, 20)]
    dh = abs(float(np.median(lit[:, 0])) - float(np.median(shd[:, 0]))) * 360.0
    qa.max("lit vs shadow canopy hue swing (deg)", dh, 15.0)
    # seam: the band where 3 tiles meet vs tile interiors (luma), measured on the 1:1 board
    bl = post.luma8(board)
    ys, xs = np.mgrid[0:board.shape[0], 0:board.shape[1]]
    inner_m = np.zeros(bl.shape, bool)
    edge_m = np.zeros(bl.shape, bool)
    m_in = post.hex_mask(W, H, inset=14) > 0.99
    m_edge = (post.hex_mask(W, H, inset=1) > 0.99) & (post.hex_mask(W, H, inset=5) < 0.01)
    for c in (1, 2):
        oy = 111 + (56 if c % 2 else 0)
        inner_m[oy:oy + H, c * 96:c * 96 + W] |= m_in
        edge_m[oy:oy + H, c * 96:c * 96 + W] |= m_edge
    seam = float(bl[edge_m].mean() - bl[inner_m].mean())
    qa.range("seam band minus interior luma", seam, -8.0, 8.0)
    print("[ironart] TIMES", {k: round(v, 2) for k, v in times.items()})
    qa.check()


if __name__ == "__main__":
    main()
