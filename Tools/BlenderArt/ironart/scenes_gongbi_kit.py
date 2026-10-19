"""Illustrated Scenes (gongbi): scene-assembly helpers shared by the ``scenes/sc_*.py`` modules.

* :func:`emit`        MeshBuilder -> object in the right ink collection (resolves the world kit's
                      bake-suffixed slots, names the UV layer ``MetreUV``)
* :func:`city`        a complete World Models city tier (walls, gates, halls, pagodas, compounds,
                      trees) placed and scaled in the scene
* :func:`banner`      war banner on a pole (people kit flag cloth)
* :func:`person`      one posed, dressed figure placed in the scene
* :func:`trees`       scatter gongbi trees from a list of placements
* :func:`materials`   one slot dict for architecture + people + flora + land
"""

import math
import random

from mathutils import Matrix, Vector

from . import scenes_gongbi as GB
from . import scenes_gongbi_flora as F
from .geometry import MeshBuilder


def materials(arch=None, cloth=None, banners=None, flora=None, skin=None, armor="#6A665E", extra=None):
    m = {}
    m.update(GB.arch_materials(arch))
    m.update(GB.people_materials(cloth, banners, skin=skin, armor=armor))
    m.update(F.materials(**(flora or {})))
    m.update(extra or {})
    return m


def split(mb, names):
    """Split a MeshBuilder by material: returns (rest, part with the faces whose slot is in
    ``names``).  Vertices are shared (unused ones are harmless)."""
    a, b = MeshBuilder(), MeshBuilder()
    for o in (a, b):
        o.verts = mb.verts
        o.vattr = mb.vattr
    for f, mi, sm, uv in zip(mb.faces, mb.face_mat, mb.face_smooth, mb.face_uv):
        nm = mb.mat_names[mi]
        o = b if nm in names else a
        o.faces.append(f)
        o.face_mat.append(o.mat(nm))
        o.face_smooth.append(sm)
        o.face_uv.append(uv)
    return a, b


def rename(mb, mapping):
    """Rename material slots in place (e.g. {'Armor': 'ArmorBlue'})."""
    mb.mat_names = [mapping.get(n, n) for n in mb.mat_names]
    return mb


#: thin props (spear shafts, bows, ropes, blades) get the light 'fine' ink instead of the
#: figure outline, so a 2 cm shaft does not become a heavy black bar
THIN = ("Wood", "Rope", "Metal", "Blade")


def emit(mb, name, mats, kind="arch", thin=None):
    """Build ``mb`` into an object linked to the ink collection ``kind`` (faces whose slot is in
    ``thin`` go to a second object in the 'fine' collection)."""
    if thin:
        rest, part = split(mb, thin)
        if part.faces:
            emit(part, name + "_thin", mats, "fine")
        mb = rest
        if not mb.faces:
            return None
    if kind == "fig" and "Skin" in mb.mat_names:
        rest, skin = split(mb, ("Skin",))
        if skin.faces:
            emit(skin, name + "_skin", mats, "skin")
        mb = rest
        if not mb.faces:
            return None
    m = dict(mats)
    for nm in mb.mat_names:
        if nm not in m and "~" in nm:
            base = nm.split("~", 1)[0]
            if base in m:
                m[nm] = m[base]
        if nm not in m:
            raise KeyError("no gongbi material for slot %r (object %s)" % (nm, name))
    o = mb.build(name, m, col=GB.col(kind), auto_smooth_deg=40.0)
    if o.data.uv_layers:
        o.data.uv_layers[0].name = "MetreUV"
    return o


def city(tier=3, at=(0, 0, 0), rz=0.0, scale=1.0, seed=None, skip=(), only=None):
    """World Models city layout (``world_city.tierN``) as one MeshBuilder in scene space.

    Returns (MeshBuilder, tree list [(kind, (x, y, z), size)])."""
    from . import world_city as WC
    P, lay = WC.TIERS[tier]() if seed is None else WC.TIERS[tier](seed)
    cache = {}
    mb = MeshBuilder()
    M = Matrix.Translation(Vector(at)) @ Matrix.Rotation(rz, 4, "Z") @ Matrix.Scale(scale, 4)
    for proto, m in lay.items:
        if proto in skip or (only is not None and proto not in only):
            continue
        if proto not in cache:
            cache[proto] = P[proto]()
        mb.extend(cache[proto], M @ m)
    trees = []
    for (kind, x, y, s, rot) in lay.trees:
        p = M @ Vector((x, y, 0))
        trees.append((kind, tuple(p), s * scale))
    return mb, trees


def trees(mb, placements, rng, cam_dir=(0, 1, 0), size=1.0, low=False):
    """Gongbi trees for [(kind, (x, y, z), s)] placements ('broad' / 'pine' / 'willow' / ...)."""
    for kind, p, s in placements:
        h = s * size
        if kind == "pine":
            F.pine(mb, rng, height=h * 26.0, at=p, cam_dir=cam_dir, limbs=4 if low else 5,
                   pad_seg=(10, 6) if low else (14, 8), seg=5 if low else 7)
        elif kind == "willow":
            F.willow(mb, rng, height=h * 22.0, at=p)
        elif kind == "bamboo":
            F.bamboo(mb, rng, height=h * 20.0, at=p, cam_dir=cam_dir)
        elif kind == "dead":
            F.dead_tree(mb, rng, height=h * 20.0, at=p)
        else:
            leaf = kind if kind in ("Leaf", "LeafDark", "LeafLight", "LeafAutumn") else rng.choice(["Leaf", "LeafDark", "Leaf"])
            F.broadleaf(mb, rng, height=h * 22.0, at=p, leaf=leaf, masses=5 if low else 7,
                        mass_seg=(10, 7) if low else (14, 9), seg=5 if low else 7)


def banner(mb, rng, color=0, at=(0, 0, 0), height=9.0, cloth=(2.4, 4.2)):
    from .scenes_arch import banner_pole
    banner_pole(mb, rng, color=color, height=height, cloth=cloth, at=at)


def person(mb, rng, pose, outfit, at=(0, 0, 0), rz=0.0, scale=1.0, **kw):
    """Dress + pose one figure (``scenes_people.figure``) and place it (facing -Y rotated by rz)."""
    from . import scenes_people as P
    f = MeshBuilder()
    sk = P.figure(f, rng, pose, outfit, **kw)
    mb.extend(f, Matrix.Translation(Vector(at)) @ Matrix.Rotation(rz, 4, "Z") @ Matrix.Scale(scale, 4))
    return sk


def rider(mb, rng, at=(0, 0, 0), rz=0.0, scale=1.0, **kw):
    from . import scenes_people as P
    f = MeshBuilder()
    P.rider(f, rng, **kw)
    mb.extend(f, Matrix.Translation(Vector(at)) @ Matrix.Rotation(rz, 4, "Z") @ Matrix.Scale(scale, 4))


def face_cam(cam_loc, p):
    """rz that turns a figure (built facing -Y) towards the camera position."""
    d = Vector(cam_loc) - Vector(p)
    return math.atan2(d.x, -d.y) if (d.x or d.y) else 0.0


def grove(rng, center, radius, n, height_fn=None, kinds=("Leaf", "LeafDark", "pine"), size=(0.7, 1.2),
          ground=None):
    """Placements for a grove: ``n`` trees within ``radius`` of ``center`` (bigger ones near the
    middle), ``ground(x, y) -> z`` to sit them on the terrain."""
    out = []
    cx, cy = center[0], center[1]
    for i in range(n):
        a = rng.uniform(0, math.tau)
        rr = radius * math.sqrt(rng.random())
        x, y = cx + math.cos(a) * rr, cy + math.sin(a) * rr * 0.7
        z = ground(x, y) if ground else (center[2] if len(center) > 2 else 0.0)
        s = rng.uniform(*size) * (1.15 - 0.4 * rr / max(radius, 1e-6))
        out.append((rng.choice(kinds), (x, y, z - 0.5), s))
    return out


class ScreenMap:
    """Compose in screen space: map (sx, sy) image coordinates (0..1, y down) at a horizontal
    distance ``d`` to world points for a level-ish camera at ``loc`` looking at ``target``."""

    def __init__(self, loc, target, focal_mm=35.0, sensor=36.0, aspect=16.0 / 9.0, shift_y=0.0):
        self.loc = Vector(loc)
        t = Vector(target) - self.loc
        self.yaw = math.atan2(t.x, t.y)
        self.pitch = math.atan2(t.z, math.hypot(t.x, t.y))
        self.fn = focal_mm / sensor
        self.aspect = aspect
        self.shift_y = shift_y

    def at(self, sx, sy, d):
        ax = math.atan((sx - 0.5) / self.fn)
        a = self.yaw + ax
        x = self.loc.x + d * math.sin(a)
        y = self.loc.y + d * math.cos(a)
        beta = self.pitch + math.atan(((0.5 - sy) / self.aspect + self.shift_y) / self.fn)
        z = self.loc.z + d / math.cos(ax) * math.tan(beta)
        return (x, y, z)

    def sx(self, X, Y):
        import numpy as np
        a = np.arctan2(X - self.loc.x, Y - self.loc.y) - self.yaw
        return 0.5 + np.tan(a) * self.fn

    def dist(self, X, Y):
        import numpy as np
        return np.hypot(X - self.loc.x, Y - self.loc.y)

    def peaks(self, specs):
        """[(sx, sy_top, d, radius, shape)] -> peak_field tuples (x, y, height, radius, shape)."""
        out = []
        for (sx, sy, d, r, shape) in specs:
            x, y, z = self.at(sx, sy, d)
            out.append((x, y, z, r, shape))
        return out

    def ground(self, sx, sy, z=0.0):
        """World point where the view ray through (sx, sy) meets the plane at height ``z``
        (None above the horizon)."""
        ax = math.atan((sx - 0.5) / self.fn)
        beta = self.pitch + math.atan(((0.5 - sy) / self.aspect + self.shift_y) / self.fn)
        dz = z - self.loc.z
        if beta >= 0 or dz >= 0:
            return None
        d = dz / math.tan(beta) * math.cos(ax)
        a = self.yaw + ax
        return (self.loc.x + d * math.sin(a), self.loc.y + d * math.cos(a), z)


def cottage(mb, at=(0, 0, 0), rz=0.0, w=7.0, d=4.6, h=2.8, thatch=True, wall="W_PlasterWarm"):
    """Rural house (world kit house) with a thatched (``Thatch`` slot, no tile rows) or tiled
    gable roof."""
    from . import world_kit as WK
    hs = WK.HouseSpec(w=w, d=d, h=h, wall="W_Earth" if thatch else "W_Brick", upper=wall)
    if thatch:
        hs.roof.tiles = False
        hs.roof.mat = "Thatch"
        hs.roof.ridge_mat = "Thatch"
        hs.roof.ridge_ends = "plain"
        hs.roof.lift = 0.05
        hs.roof.flare = 0.0
        hs.roof.thick = 0.35
        hs.roof.overhang = 0.9
    s0 = mb.n
    WK.house(mb, (0, 0, 0), hs)
    mb.transform(s0, Matrix.Translation(Vector(at)) @ Matrix.Rotation(rz, 4, "Z"))
