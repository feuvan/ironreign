"""Board review: re-imported Hex_*.glb / Unit_*.glb laid out exactly like the game's board
(DESIGN.md 12.4: hex (col, row) centre = (6 col, (row + 0.5 (col & 1)) 6.928) m in UE; Blender
y = -UE y), natural tiles at random 60 deg yaws (as AIronBattleBoard3D), rendered with the
board camera (FOV 38 deg, pitch 50 deg) in the gongbi review look.

    Tools/BlenderArt/render.sh Tools/BlenderArt/battle/board.py [--preview] [layout name]
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import review  # noqa: E402

import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from ironart import scene  # noqa: E402

ROW = 6.928203230275509

#: board patches: rows of terrain letters (P plain, F forest, H hill, M mountain, W water, O ford,
#: B bridge, R road, L wall, G gate, T town, C castle, X rubble); units as (col, row, type, side)
LEGEND = {"P": "Plain", "F": "Forest", "H": "Hill", "M": "Mountain", "W": "Water", "O": "Ford", "B": "Bridge",
          "R": "Road", "L": "Wall", "G": "Gate", "T": "Town", "C": "Castle", "X": "Rubble"}
LAYOUTS = {
    "plains": (["PPPPP", "PPPPP", "PPPPP", "PPPPP"], []),
    "field": (["PFFPHHMP", "PFPWPHMM", "RRROBRRP", "PPPWPPFP", "FPPWFFPP", "FFPOPPHP"],
              [(1, 2, "Infantry", 0), (2, 3, "Cavalry", 0), (1, 1, "Archer", 0), (5, 2, "Infantry", 1),
               (6, 3, "Archer", 1), (4, 4, "Cavalry", 1)]),
    "siege": (["PPPLTTT", "RRRGTCT", "PPPLTTT", "PFPXTTT", "FFPLTTP"],
              [(1, 1, "Infantry", 0), (2, 3, "Cavalry", 0), (3, 3, "Infantry", 0), (5, 1, "Archer", 1),
               (4, 2, "Infantry", 1)]),
    "all": (["PFHMWOB", "RLGTCXP", "PFHMWOB"], []),
}


def centre(col, row):
    return Vector((6.0 * col, -(row + 0.5 * (col & 1)) * ROW, 0.0))


def load(name):
    path = os.path.join(common.MODELS_DIR, name + ".glb")
    if not os.path.isfile(path):
        return None
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    objs = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    for o in bpy.data.objects:
        if o not in before and o.type != "MESH":
            bpy.data.objects.remove(o)
    o = objs[0]
    o.name = "P_" + name
    o.hide_render = True
    return o


def build(layout, seed=5, units=()):
    rows, unit_list = LAYOUTS[layout] if isinstance(layout, str) else layout
    protos = {}
    rng = random.Random(seed)
    placed = []
    for r, line in enumerate(rows):
        for c, ch in enumerate(line):
            name = LEGEND[ch]
            if name not in protos:
                protos[name] = load("Hex_" + name)
            p = protos[name] or protos.get("Plain") or load("Hex_Plain")
            if p is None:
                continue
            o = p.copy()
            o.hide_render = False
            bpy.context.scene.collection.objects.link(o)
            yaw = 60.0 * rng.randint(0, 5) if name in common.NATURAL else 0.0
            o.matrix_world = Matrix.Translation(centre(c, r)) @ Matrix.Rotation(math.radians(yaw), 4, "Z")
            placed.append(o)
    for (c, r, kind, side) in list(unit_list) + list(units):
        for nm in ("Unit_Base", "Unit_" + kind):
            if nm not in protos:
                protos[nm] = load(nm)
            p = protos[nm]
            if p is None:
                continue
            o = p.copy()
            o.hide_render = False
            bpy.context.scene.collection.objects.link(o)
            # units face +x (side 0) or -x (side 1): the model's front (-y) turned to the facing
            yaw = 90.0 if side == 0 else -90.0
            lift = 0.0 if nm == "Unit_Base" else base_top(protos.get("Unit_Base"))
            o.matrix_world = Matrix.Translation(centre(c, r) + Vector((0, 0, lift))) @ \
                Matrix.Rotation(math.radians(yaw), 4, "Z")
            placed.append(o)
    return placed, rows


def base_top(o):
    if o is None:
        return 0.0
    return min(0.6, max(v.co.z for v in o.data.vertices))


def render(layout="field", out=None, fast=False, res=(1600, 1000), units=(), pitch=50.0, close=None):
    scene.reset(3)
    placed, rows = build(layout, units=units)
    ncol = max(len(r) for r in rows)
    nrow = len(rows)
    lo = centre(0, 0) + Vector((-4, 4, 0))
    hi = centre(ncol - 1, nrow - 1) + Vector((4, -4 - ROW * 0.5, 0))
    target = (lo + hi) * 0.5
    if close is not None:
        target = centre(*close[:2])
    span = max(hi.x - lo.x, (lo.y - hi.y) * 1.25)
    dist = span / (2 * math.tan(math.radians(19))) * (0.98 if close is None else close[2])
    cam = review.camera(placed, pitch=pitch, yaw=0.0, fov=38.0, target=target, dist=dist)
    out = out or os.path.join(common.out("previews"), "Board_%s.png" % layout)
    secs = review.preview(placed, out, res=res, samples=8 if fast else 16, cam=cam, ground_z=-1.0, ss=1)
    print("[battle] board %s -> %s (%.1fs)" % (layout, out, secs))
    return out


def main():
    fl = common.flags()
    names = [n for n in fl["names"] if n in LAYOUTS] or ["field"]
    for n in names:
        render(n, fast=fl["preview"])


if __name__ == "__main__":
    main()
