"""World Terrain family - render one tile of the 2D map's glyph layer (run by build.py).

    Tools/BlenderArt/render.sh Tools/BlenderArt/world_terrain/glyph_tile.py x0,y0,x1,y1 tag spp data_dir out_dir

Reads ``peaks.json`` and ``mtrees.json`` from ``data_dir`` (written by build.py's worldmap stage)
and writes the passes (Image, Freestyle, gA..gD AOVs, Depth) of the map rectangle x0..x1, y0..y1
(metres) as float EXRs ``<tag>_<pass>_0001.exr`` into ``out_dir``.  Each tile runs in its own
Blender process, so Freestyle's memory is returned after every tile.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def main(argv):
    import bpy
    from ironart import scene
    from ironart import world_terrain_glyphs as G
    from ironart import world_terrain_mapglyphs as MG
    from ironart import world_terrain_mappaint as MP
    fx0, fy0, fx1, fy1 = [float(v) for v in argv[0].split(",")]
    tag, spp, data_dir, out_dir = argv[1], int(argv[2]), argv[3], argv[4]
    with open(os.path.join(data_dir, "peaks.json")) as f:
        peaks = json.load(f)
    with open(os.path.join(data_dir, "mtrees.json")) as f:
        mtrees = json.load(f)
    scene.reset(seed=3)
    scene.setup_cycles(samples=spp, transparent=True, preset="fast", view="Standard", look="None",
                       adaptive_threshold=0.0)
    bpy.context.scene.cycles.filter_width = 1.0
    scene.set_resolution(int(round(fx1 - fx0)), int(round(fy1 - fy0)), MP.SS)
    mat = MG.glyph_material()
    rel = bpy.data.collections.new("Relief")
    bpy.context.scene.collection.children.link(rel)
    gb = (fx0 - 160.0, fy0 - 20.0, fx1 + 160.0, fy1 + 190.0)
    MG.build_peak_objects(peaks, mat, rel, box=gb)
    trc = bpy.data.collections.new("Trees")
    bpy.context.scene.collection.children.link(trc)
    prc = bpy.data.collections.new("Protos")
    bpy.context.scene.collection.children.link(prc)
    protos = MG.tree_prototypes(prc)
    sel = [t for t in mtrees if gb[0] < t["x"] < gb[2] and gb[1] < t["y"] < gb[3]]
    if sel:
        MG.instance_trees(sel, protos, trc)
    G.camera((fx0, fy0, fx1, fy1))
    G.ground_plane()
    MG.setup_aovs()
    MG.ink_lines(MP.SS, relief_collection=rel, tree_collection=trc)
    os.makedirs(out_dir, exist_ok=True)
    MG.comp_passes(out_dir, tag)
    scene.render(os.path.join(out_dir, "%s_beauty.png" % tag))


if __name__ == "__main__":
    from ironart import scene as _scene
    main(_scene.args())
