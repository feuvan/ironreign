"""World Models family: City_1 / City_2 / City_3 (DESIGN.md 12.3) - prototypes, layouts, ground.

A city is a set of **prototypes** (one mesh per building type, built with :mod:`world_kit`)
placed many times.  Prototypes share one baked atlas (instances share UVs), the ground plate has
its own unique-UV texture painted from a layout mask (streets, plazas, gardens, canal beds) and
baked with the whole city present (contact AO), trees use the Tree_* bark / leaf textures.

Layout conventions: metres, origin = city centre on the ground, front gate on -y (map south,
towards the strategy camera), main buildings face -y.  The 2D sprite camera looks from the
front-left, so tall landmarks (watchtower, pagodas) stand at the back-left: the back-right corner
is the pennant keep-out of ``City_N.png``.

Tiers
    1  town: rammed-earth wall (single gate with a timber gate house), lanes of courtyard
       houses with grey tiled roofs, a shrine, a brick-and-timber watchtower, trees
    2  walled city: crenellated stone walls, four corner towers, double-eaved gate tower, drum
       tower at the crossroads, yamen hall, dense courtyard compounds (hutong), a 7-tier pagoda
    3  imperial capital: outer wall with a barbican and arrow tower in front of a three-arch
       gate, a red-walled palace city with golden roofs on marble terraces, a canal with marble
       bridges, a bell tower at the crossroads, two pagoda temples, dense compounds
"""

import math
import random

import numpy as np
from mathutils import Matrix, Vector

from . import world_kit as K
from .geometry import MeshBuilder

TAU = math.tau
R90 = math.pi / 2


# ---------------------------------------------------------------------------------------------
# prototypes (each returns a MeshBuilder; local frame: ground origin, front -y)
# ---------------------------------------------------------------------------------------------
def p_house(w=9.0, d=5.6, wall="W_Brick", upper="W_Plaster", roof="W_Tile", h=3.4, pitch=0.6,
            rh=None, ends="curl"):
    mb = MeshBuilder()
    hs = K.HouseSpec(w=w, d=d, h=h, wall=wall, upper=upper, roof_h=rh)
    hs.roof.mat = roof
    hs.roof.pitch = pitch
    hs.roof.ridge_ends = ends
    K.house(mb, (0, 0, 0), hs)
    return mb


def p_house_hip(w=11.0, d=7.0, roof="W_Tile", ridge="W_Ridge", wall="W_Plaster", col_h=3.8, bays=(3, 2)):
    """Larger hall-type house (main hall of a rich compound / temple side hall)."""
    mb = MeshBuilder()
    hs = K.HallSpec(bays=bays, bay=w / bays[0], depth_bay=d / bays[1], col_h=col_h, col_r=0.22,
                    plat_h=0.6, plat_margin=0.9, plat_mat="W_Stone", plat_top="W_Paving", steps=True,
                    wall_mat=wall, front="lattice", front_inset=0.8, brackets=False,
                    beam_mat="W_BeamPaint",
                    roof=K.RoofSpec(style="hip_gable", overhang=1.2, lift=0.45, flare=0.25, thick=0.24,
                                    pitch=0.6, tile_seg=4, tile_faces=2, nv=5, mat=roof, ridge_mat=ridge,
                                    ridge_h=0.45))
    K.hall(mb, (0, 0, 0), hs)
    return mb


def p_cwall(L=8.0, h=2.8, mat="W_Brick", cap="W_TileDark", top="W_Plaster"):
    mb = MeshBuilder()
    K.courtyard_wall(mb, L, h, 0.5, mat, cap, top)
    return mb


def p_cgate():
    mb = MeshBuilder()
    K.gatehouse_small(mb, 4.4, 3.2, 3.4)
    return mb


def p_row_house(w=16.0, d=6.0, roof="W_TileDark"):
    """Long hutong row building (shops facing the street), one long gable roof."""
    mb = MeshBuilder()
    hs = K.HouseSpec(w=w, d=d, h=3.6, wall="W_BrickWarm", upper="W_PlasterWarm")
    hs.roof.mat = roof
    hs.roof.ridge_ends = "plain"
    K.house(mb, (0, 0, 0), hs)
    return mb


def p_wall(L, H, T, mat="W_Stone", par="W_Brick", earth=False):
    mb = MeshBuilder()
    K.wall_segment(mb, L, H, T, batter=min(1.2, T * 0.14), mat=mat, top="W_Paving" if not earth else mat,
                   par=par, earth=earth)
    return mb


def p_corner_tower(S, H, roof="W_TileDark", double=False, mat="W_Stone"):
    """Corner bastion (S x S, a little above the wall walk) with crenels and a watch pavilion."""
    mb = MeshBuilder()
    K.gate_base(mb, S, S, H + 0.4, 0.1, 0.1, mat=mat, doors=False, crenels=True) if False else None
    s = mb.n
    mb.box((0, 0, -2.0), (S, S, H + 2.4), mat, taper=(0.5, 0.5), top_mat="W_Paving", skip=("bottom",))
    # crenels all around
    top = H + 0.4
    for rz in (0, R90, math.pi, -R90):
        s2 = mb.n
        L = S - 1.0
        mb.box((0, -L / 2 + 0.3, top), (L, 0.6, 0.85), "W_Brick", skip=("bottom",))
        n = max(2, int(round(L / 2.1)))
        pitch = L / n
        for i in range(n):
            mb.box((-L / 2 + pitch * (i + 0.5), -L / 2 + 0.3, top + 0.85), (pitch - 0.65, 0.6, 0.95), "W_Brick")
        mb.transform(s2, K.T(0, 0, 0, rz))
    bw = S * 0.52
    K.hall(mb, (0, 0, top), K.HallSpec(
        bays=(3, 3), bay=bw / 3, col_h=3.4, col_r=0.22, plat_h=0.0, steps=False, wall_mat="W_RedWall",
        front="lattice", front_inset=0.0, brackets=True, bracket_k=0.6, double=double, upper_h=2.4,
        roof=K.RoofSpec(style="hip_gable", overhang=1.3, lift=0.6, flare=0.3, thick=0.26, pitch=0.55,
                        tile_seg=4, tile_faces=2, nv=5, mat=roof, ridge_h=0.5)), roof_h=bw * 0.42)
    return mb


def p_gate(W, D, H, arch_w, arch_h, n_arches=1, mat="W_Stone", tower=(5, 2), bay=4.0, col_h=4.6,
           roof="W_TileDark", ridge="W_Ridge", double=True, beasts=3, earth=False):
    """City gate: gate block with tunnels + gate-tower pavilion with a balcony railing."""
    mb = MeshBuilder()
    K.gate_base(mb, W, D, H, arch_w, arch_h, mat=mat, n_arches=n_arches, crenels=not earth,
                par="W_Brick" if not earth else mat, top="W_Paving" if not earth else mat)
    nx, ny = tower
    hw = nx * bay
    hd = ny * bay
    K.railing_rect(mb, hw + 3.0, hd + 3.0, H, 1.0)
    K.platform(mb, hw + 2.4, hd + 2.4, 0.5, "W_Stone", "W_Paving", z0=H, skirt=0.0, plinth=False)
    K.hall(mb, (0, 0, H + 0.5), K.HallSpec(
        bays=tower, bay=bay, col_h=col_h, col_r=0.3, plat_h=0.0, steps=False, wall_mat="W_RedWall",
        front="lattice", front_inset=0.0 if double else 1.0, brackets=True, bracket_k=0.8 if double else 0.6,
        double=double, upper_h=col_h * 0.7,
        roof=K.RoofSpec(style="hip_gable", overhang=1.8, lift=0.8, flare=0.4, thick=0.3, pitch=0.55,
                        tile_seg=5, tile_faces=3 if double else 2, nv=6, mat=roof, ridge_mat=ridge,
                        beasts=beasts)), roof_h=hd * 0.42 + 1.0)
    return mb


def p_earth_gate():
    """Town gate: rammed-earth block, one tunnel, a timber gate house with a grey tile roof."""
    mb = MeshBuilder()
    K.gate_base(mb, 11.0, 7.0, 5.4, 3.6, 4.4, mat="W_Earth", crenels=False, par="W_Earth", top="W_Earth")
    K.railing_rect(mb, 8.6, 5.6, 5.4, 0.9, mat="W_Wood")
    K.hall(mb, (0, 0, 5.4), K.HallSpec(
        bays=(3, 2), bay=2.6, col_h=2.9, col_r=0.18, plat_h=0.0, steps=False, wall_mat="W_PlasterWarm",
        front="lattice", front_inset=0.0, brackets=False, col_mat="W_LacquerDark",
        roof=K.RoofSpec(style="hip_gable", overhang=1.0, lift=0.35, flare=0.2, thick=0.22, pitch=0.55,
                        tile_seg=4, tile_faces=2, nv=4, mat="W_Tile", ridge_h=0.4)), roof_h=2.4)
    return mb


def p_watchtower():
    """Town watchtower: battered brick shaft with arrow slits, timber lookout with a pyramid roof."""
    mb = MeshBuilder()
    mb.box((0, 0, -1.5), (6.4, 6.4, 13.5), "W_Brick", taper=(0.6, 0.6), skip=("bottom",))
    for k in range(4):
        rz = k * R90
        for z in (4.5, 8.5):
            s = mb.n
            mb.box((0, 0, 0), (0.35, 0.05, 1.1), "W_Dark")
            mb.transform(s, K.T(0, 0, z, rz) @ Matrix.Translation(Vector((0, -2.95 + (z - 0) * 0.03, 0))))
    K.platform(mb, 6.6, 6.6, 0.3, "W_Stone", "W_Paving", z0=12.0, skirt=0.0)
    K.railing_rect(mb, 6.2, 6.2, 12.3, 1.0, mat="W_Wood")
    K.hall(mb, (0, 0, 12.3), K.HallSpec(
        bays=(2, 2), bay=2.2, col_h=2.8, col_r=0.15, plat_h=0.0, steps=False, wall_mat="W_PlasterWarm",
        front="open", side="open", front_inset=0.0, brackets=False, col_mat="W_LacquerDark",
        roof=K.RoofSpec(style="pyramid", overhang=1.2, lift=0.45, flare=0.25, thick=0.2, pitch=0.5,
                        tile_seg=4, tile_faces=2, nv=4, mat="W_Tile", finial="gold", ridge_h=0.4)),
           roof_h=2.6)
    return mb


def p_drum_tower(roof="W_TileDark", W=18.0, D=13.0, H=8.0):
    """Drum / bell tower: brick block with a through-arch, two-storey pavilion, double eaves."""
    mb = MeshBuilder()
    K.gate_base(mb, W, D, H, 4.2, 5.6, mat="W_Brick", crenels=False, par="W_Brick", doors=False)
    K.railing_rect(mb, W - 1.2, D - 1.2, H, 1.0)
    K.hall(mb, (0, 0, H), K.HallSpec(
        bays=(3, 2), bay=W * 0.6 / 3, depth_bay=D * 0.55 / 2, col_h=4.0, col_r=0.28, plat_h=0.0, steps=False,
        wall_mat="W_RedWall", front="lattice", front_inset=0.0, brackets=True, bracket_k=0.7,
        double=True, upper_h=3.0,
        roof=K.RoofSpec(style="hip_gable", overhang=1.7, lift=0.8, flare=0.4, thick=0.28, pitch=0.55,
                        tile_seg=5, tile_faces=2, nv=6, mat=roof, beasts=2)), roof_h=4.4)
    return mb


def p_pagoda(tiers=7, R=3.6, body="W_Brick", roof="W_TileDark", ridge="W_Ridge", frames=True):
    mb = MeshBuilder()
    K.pagoda(mb, (0, 0, 0), tiers=tiers, R=R, body_mat=body, roof_mat=roof, ridge_mat=ridge,
             lacquer_frames=frames, tier_h=3.4, base_h=5.2)
    return mb


def p_hall(bays=(5, 3), bay=4.0, col_h=5.0, plat_h=1.2, roof="W_TileDark", ridge="W_Ridge", style="hip_gable",
           double=False, tiers=1, balustrade=False, wall="W_RedWall", beasts=3, plat_mat="W_Marble",
           roof_h=None, bracket_k=0.8, overhang=1.9):
    mb = MeshBuilder()
    K.hall(mb, (0, 0, 0), K.HallSpec(
        bays=bays, bay=bay, col_h=col_h, col_r=0.3, plat_h=plat_h, plat_margin=2.0, plat_mat=plat_mat,
        steps=True, wall_mat=wall, front="lattice", front_inset=1.0, brackets=True, bracket_k=bracket_k,
        double=double, upper_h=col_h * 0.65, tiers=tiers, balustrade=balustrade,
        roof=K.RoofSpec(style=style, overhang=overhang, lift=0.75, flare=0.4, thick=0.32, pitch=0.6,
                        tile_seg=5, tile_faces=3, nv=6, mat=roof, ridge_mat=ridge, beasts=beasts)),
           roof_h=roof_h)
    return mb


def p_arrow_tower(W=26.0, D=12.0, H=10.0):
    """Barbican arrow tower (jianlou): massive brick block with rows of arrow windows on a
    stone gate base, big hip-gable roof."""
    mb = MeshBuilder()
    K.gate_base(mb, W, D, H, 5.0, 6.6, mat="W_StoneDark", crenels=False, par="W_Brick")
    s = mb.n
    mb.box((0, 0, H), (W - 1.0, D - 1.0, 7.0), "W_Brick", skip=("bottom",))
    for row in range(3):
        for i in range(9):
            x = -W / 2 + 1.8 + i * (W - 3.6) / 8
            for (yy, rz) in ((-(D - 1.0) / 2 - 0.02, 0.0), ((D - 1.0) / 2 + 0.02, math.pi)):
                s2 = mb.n
                mb.box((0, 0, 0), (0.7, 0.04, 0.8), "W_Dark")
                mb.transform(s2, K.T(x, yy, H + 1.2 + row * 2.0, rz))
    for i in range(4):
        for sx in (-1, 1):
            s2 = mb.n
            mb.box((0, 0, 0), (0.04, 0.7, 0.8), "W_Dark")
            mb.transform(s2, K.T(sx * ((W - 1.0) / 2 + 0.02), -D * 0.3 + i * D * 0.2, H + 3.2, 0))
    mb.box((0, 0, H + 7.0), (W + 0.2, D + 0.2, 0.5), "W_WoodDark", skip=("bottom",))
    K.roof(mb, (0, 0, H + 7.5), W, D, 5.6, K.RoofSpec(style="hip_gable", overhang=1.8, lift=0.8, flare=0.4,
                                                      thick=0.3, pitch=0.55, tile_seg=5, tile_faces=2, nv=6,
                                                      mat="W_TileDark", beasts=3))
    return mb


def p_red_wall(L=8.0, h=6.0, t=1.8, cap="W_TileGold", ridge="W_RidgeGold"):
    """Palace enclosure wall: red plaster on a marble plinth, glazed tile coping."""
    mb = MeshBuilder()
    mb.box((0, 0, -1.5), (L, t + 0.3, 2.1), "W_Marble", skip=("bottom",))
    mb.box((0, 0, 0.6), (L, t, h - 0.6), "W_RedWall", skip=("bottom",))
    K.roof(mb, (0, 0, h), L, t, 0.9, K.RoofSpec(style="gable", overhang=0.5, lift=0.0, flare=0.0, thick=0.15,
                                                pitch=0.5, tile_seg=2, tile_faces=2, nv=2, ridge_h=0.3,
                                                ridge_ends="plain", mat=cap, ridge_mat=ridge,
                                                fascia_mat="W_Fascia"))
    return mb


def p_canal(L=8.0, Wc=7.0, depth=1.6):
    """Canal section along x: stone embankments with a coping, water 1.2 m below the street."""
    mb = MeshBuilder()
    hw = Wc / 2
    for sy in (-1, 1):
        y = sy * (hw + 0.3)
        mb.box((0, y, -depth - 0.5), (L, 0.6, depth + 0.5), "W_Stone", skip=("bottom",))
        mb.box((0, sy * (hw + 0.45), 0.0), (L, 0.9, 0.18), "W_Paving", skip=("bottom",))
    mb.box((0, 0, -depth - 0.5), (L, Wc, 0.05), "W_Dark")
    ids = [mb.v((-L / 2, -hw, -1.2)), mb.v((L / 2, -hw, -1.2)), mb.v((L / 2, hw, -1.2)), mb.v((-L / 2, hw, -1.2))]
    mb.face(ids, "Water", [(0, 0), (1, 0), (1, 1), (0, 1)])
    return mb


def p_bridge(L=14.0, W=6.0):
    mb = MeshBuilder()
    K.bridge(mb, L, W, 1.6, 0.0)
    return mb


def p_shrine():
    return p_hall(bays=(3, 2), bay=3.4, col_h=3.8, plat_h=0.8, roof="W_TileDark", style="hip_gable",
                  wall="W_RedWall", beasts=0, plat_mat="W_Stone", roof_h=3.4, bracket_k=0.55, overhang=1.4)


def p_paifang():
    mb = MeshBuilder()
    K.paifang(mb, 10.0, 7.5)
    return mb


# ---------------------------------------------------------------------------------------------
# layout helpers
# ---------------------------------------------------------------------------------------------
class Layout:
    """Placements + ground mask strokes + tree list for one city."""

    def __init__(self, half, seed):
        self.half = half                # ground plate half extents (gx, gy)
        self.items = []                 # (proto, Matrix)
        self.trees = []                 # (kind, x, y, scale, rot)
        self.paved = []                 # rects (x0, y0, x1, y1) or ('ell', cx, cy, rx, ry)
        self.green = []
        self.wet = []
        self.rng = random.Random(seed)

    def put(self, proto, x, y, rz=0.0, z=0.0, sx=1.0, sy=1.0, sz=1.0):
        m = Matrix.Translation(Vector((x, y, z))) @ Matrix.Rotation(rz, 4, "Z") @ Matrix.Diagonal((sx, sy, sz, 1.0))
        self.items.append((proto, m))

    def tree(self, kind, x, y, s=1.0):
        self.trees.append((kind, x, y, s, self.rng.uniform(0, TAU)))

    def span(self, proto, L0, p0, p1, rz, z=0.0):
        """Fill the straight run p0 -> p1 with ``proto`` segments (length L0 each, stretched to
        fit exactly)."""
        a, b = Vector((p0[0], p0[1])), Vector((p1[0], p1[1]))
        d = b - a
        Ln = d.length
        n = max(1, int(round(Ln / L0)))
        k = Ln / (n * L0)
        for i in range(n):
            c = a + d * ((i + 0.5) / n)
            self.put(proto, c.x, c.y, rz, z, sx=k)

    def compound(self, x, y, w, d, rz=0.0, rich=False, houses=("house_a", "house_b"), trees=True):
        """Siheyuan around a courtyard: main house at the back, side houses, walls, a gate in
        the front wall (local front -y, rotated by ``rz`` about (x, y))."""
        rng = self.rng
        R = Matrix.Rotation(rz, 4, "Z")

        def P(lx, ly):
            v = R @ Vector((lx, ly, 0))
            return x + v.x, y + v.y

        hw, hd = w / 2, d / 2
        main = "house_hip" if rich else houses[0]
        mx, my = P(0, hd - 4.2)
        self.put(main, mx, my, rz)
        side = houses[1]
        if w > 17:
            for sx in (-1, 1):
                px, py = P(sx * (hw - 3.4), -0.8)
                self.put(side, px, py, rz - sx * R90, sx=0.92)
        # walls: front with a gate at the right third, sides, back
        gx = hw * 0.45
        for (a, b, wr) in (((-hw, -hd), (gx - 2.6, -hd), 0.0), ((gx + 2.6, -hd), (hw, -hd), 0.0),
                           ((hw, -hd), (hw, hd), R90), ((hw, hd), (-hw, hd), math.pi), ((-hw, hd), (-hw, -hd), -R90)):
            pa, pb = P(*a), P(*b)
            if (Vector(pb) - Vector(pa)).length > 1.0:
                self.span("cwall", 8.0, pa, pb, rz + wr)
        gx_, gy_ = P(gx, -hd)
        self.put("cgate", gx_, gy_, rz)
        # courtyard paving + garden
        cx, cy = P(0, -0.8)
        self.paved.append(("ell", cx, cy, hw * 0.45, hd * 0.35))
        if trees:
            tx, ty = P(rng.uniform(-hw * 0.4, hw * 0.4), rng.uniform(-hd * 0.5, 0))
            self.green.append(("ell", tx, ty, 2.5, 2.5))
            self.tree("broad", tx, ty, rng.uniform(0.36, 0.46))

    def street(self, x0, y0, x1, y1):
        self.paved.append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))


def wall_ring(lay, protos, half_x, half_y, T, gate_w, tower_s, corner=True, gate_proto=None, gate_D=None,
              towers_proto="corner_tower", wall_proto="wall", seg=8.0, earth=False):
    """Outer wall around [-half_x, half_x] x [-half_y, half_y] (outer face), gate on the front."""
    cx, cy = half_x - T / 2, half_y - T / 2          # centreline
    ts = tower_s / 2 if corner else 0.0
    gw = gate_w / 2
    # front (outward -y): two runs beside the gate
    lay.span(wall_proto, seg, (-cx + ts, -cy), (-gw, -cy), 0.0)
    lay.span(wall_proto, seg, (gw, -cy), (cx - ts, -cy), 0.0)
    lay.span(wall_proto, seg, (cx, -cy + ts), (cx, cy - ts), R90)          # east, outward +x
    lay.span(wall_proto, seg, (cx - ts, cy), (-cx + ts, cy), math.pi)      # north, outward +y
    lay.span(wall_proto, seg, (-cx, cy - ts), (-cx, -cy + ts), -R90)       # west, outward -x
    if corner:
        for (x, y) in ((-cx, -cy), (cx, -cy), (cx, cy), (-cx, cy)):
            lay.put(towers_proto, x, y, 0.0)
    if gate_proto:
        lay.put(gate_proto, 0.0, -cy, 0.0)
    return cx, cy


# ---------------------------------------------------------------------------------------------
# tiers
# ---------------------------------------------------------------------------------------------
def tier1(seed=101):
    """Small walled town (~45 m)."""
    P = {
        "wall": lambda: p_wall(8.0, 4.6, 3.2, mat="W_Earth", earth=True),
        "gate": p_earth_gate,
        "tower": p_watchtower,
        "house_a": lambda: p_house(8.2, 5.4, "W_Brick", "W_PlasterWarm", "W_Tile", 3.2),
        "house_b": lambda: p_house(6.6, 4.8, "W_BrickWarm", "W_Plaster", "W_TileDark", 3.0),
        "house_c": lambda: p_house(10.0, 5.6, "W_Earth", "W_PlasterWarm", "W_Tile", 3.2, ends="plain"),
        "shrine": p_shrine,
        "cwall": lambda: p_cwall(8.0, 2.5, "W_Earth", "W_TileDark", "W_PlasterWarm"),
        "cgate": p_cgate,
    }
    hx, hy = 21.0, 19.0
    lay = Layout((hx - 2.5, hy - 2.5), seed)
    T = 3.2
    cx, cy = wall_ring(lay, P, hx, hy, T, 11.0, 0.0, corner=False, gate_proto="gate")
    # watchtower straddles the back-left corner
    lay.put("tower", -cx + 0.6, cy - 0.6, 0.0)
    # streets: main N-S, one E-W lane
    lay.street(-2.2, -hy, 2.2, 6.0)
    lay.street(-hx, -3.4, hx, -0.6)
    lay.paved.append(("ell", 0.0, 3.0, 5.0, 3.2))
    # shrine at the back centre with a court
    lay.put("shrine", 1.0, 11.0, 0.0)
    lay.paved.append((-5.0, 5.0, 7.0, 9.0))
    # houses
    rng = lay.rng
    for (x, y, rz, p) in ((-10.5, -10.0, 0.0, "house_a"), (-12.0, -6.5, 0.0, "house_b"),
                          (10.0, -10.5, 0.0, "house_c"), (11.5, -5.6, math.pi, "house_b"),
                          (-11.0, 4.5, 0.0, "house_c"), (-10.0, 9.5, 0.0, "house_a"),
                          (11.0, 3.4, 0.0, "house_a"), (12.5, 9.0, -R90, "house_b"),
                          (-5.6, -13.0, R90, "house_b"), (5.8, -13.0, -R90, "house_b")):
        lay.put(p, x, y, rz)
    for (a, b, rz) in (((-16.5, 7.2), (-5.5, 7.2), 0.0), ((5.5, 6.2), (16.0, 6.2), 0.0)):
        lay.span("cwall", 8.0, a, b, rz)
    # gardens and trees
    for (x, y, s) in ((-3.8, 2.6, 0.5), (6.5, 0.8, 0.42), (-15.0, -1.5, 0.44), (15.5, -1.0, 0.4),
                      (-4.5, 13.5, 0.5), (8.0, 14.0, 0.46), (-7.0, -6.8, 0.38), (4.6, -7.2, 0.4)):
        lay.green.append(("ell", x, y, 3.2, 3.0))
        lay.tree("broad", x, y, s)
    lay.tree("pine", -1.5, 14.5, 0.42)
    lay.green.append((-hx, -hy, -hx + 3.0, hy))
    lay.green.append((hx - 3.0, -hy, hx, hy))
    return P, lay


def tier2(seed=202):
    """Walled city (~75 m)."""
    P = {
        "wall": lambda: p_wall(8.0, 8.0, 6.0),
        "corner_tower": lambda: p_corner_tower(11.0, 8.0),
        "gate": lambda: p_gate(22.0, 13.0, 9.0, 5.2, 7.0, tower=(5, 2), bay=3.8, col_h=4.4),
        "drum": lambda: p_drum_tower(W=16.0, D=12.0, H=7.0),
        "pagoda": lambda: p_pagoda(7, 3.4),
        "yamen": lambda: p_hall(bays=(5, 3), bay=3.8, col_h=4.6, plat_h=1.0, roof="W_TileDark", style="hip_gable",
                               wall="W_RedWall", beasts=2, plat_mat="W_Stone", bracket_k=0.7),
        "house_a": lambda: p_house(9.0, 5.6),
        "house_b": lambda: p_house(7.0, 5.0, "W_BrickWarm", "W_PlasterWarm", "W_TileDark"),
        "house_hip": lambda: p_house_hip(11.0, 7.0),
        "row": lambda: p_row_house(15.0, 6.0),
        "cwall": p_cwall,
        "cgate": p_cgate,
        "temple": lambda: p_hall(bays=(3, 2), bay=3.6, col_h=4.0, plat_h=0.8, roof="W_TileGreen",
                                 ridge="W_RidgeGreen", style="hip_gable", wall="W_RedWall", beasts=0,
                                 plat_mat="W_Stone", bracket_k=0.6, overhang=1.5),
    }
    hx, hy = 35.0, 33.0
    T = 6.0
    lay = Layout((hx - T + 0.5, hy - T + 0.5), seed)
    cx, cy = wall_ring(lay, P, hx, hy, T, 22.0, 11.0, gate_proto="gate")
    ix, iy = hx - T, hy - T           # inner face
    # streets: avenue gate -> drum tower -> yamen; cross street
    lay.street(-3.0, -iy, 3.0, 14.0)
    lay.street(-ix, -6.5, ix, -1.5)
    lay.street(-ix, 6.0, ix, 9.5)
    lay.paved.append(("ell", 0.0, -4.0, 11.0, 8.5))
    lay.put("drum", 0.0, -4.0, 0.0)
    # yamen compound at the back centre
    lay.put("yamen", 0.0, 18.5, 0.0)
    lay.paved.append((-9.0, 10.0, 9.0, 26.0))
    lay.span("cwall", 8.0, (-11.0, 10.4), (-3.4, 10.4), 0.0)
    lay.span("cwall", 8.0, (3.4, 10.4), (11.0, 10.4), 0.0)
    lay.span("cwall", 8.0, (11.0, 10.4), (11.0, 26.5), R90)
    lay.span("cwall", 8.0, (-11.0, 26.5), (-11.0, 10.4), -R90)
    for (x, y) in ((-6.5, 12.6), (6.5, 12.6)):
        lay.tree("pine", x, y, 0.36)
    # pagoda temple back-left
    lay.put("pagoda", -19.5, 19.5, 0.0)
    lay.put("temple", -19.5, 11.5, 0.0)
    lay.paved.append(("ell", -19.5, 16.5, 7.5, 9.0))
    for (x, y) in ((-25.0, 13.0), (-14.0, 23.5)):
        lay.tree("pine", x, y, 0.38)
    # compounds
    lay.compound(-17.5, -19.5, 20.0, 15.0, 0.0, rich=True)
    lay.compound(17.5, -19.5, 20.0, 15.0, 0.0)
    lay.compound(18.5, 17.5, 18.0, 16.0, 0.0, rich=True)
    lay.put("row", -18.0, 1.6, math.pi)
    lay.put("row", 18.0, 1.6, math.pi)
    lay.put("row", -18.0, -10.0, 0.0)
    lay.put("row", 18.0, -10.0, 0.0)
    for (x, y) in ((-9.0, -14.0), (9.0, -14.0), (-9.0, -22.0), (9.0, -22.5)):
        lay.put("house_b", x, y, R90 if x < 0 else -R90)
    for (x, y, s) in ((-6.2, -11.5, 0.42), (6.0, -12.0, 0.38), (-26.0, 3.5, 0.4), (25.5, 4.5, 0.42),
                      (-3.2, 27.0, 0.4), (14.5, 4.8, 0.36)):
        lay.green.append(("ell", x, y, 3.0, 3.0))
        lay.tree("broad", x, y, s)
    for e in ((-ix, -iy, -ix + 2.5, iy), (ix - 2.5, -iy, ix, iy), (-ix, iy - 2.5, ix, iy)):
        lay.green.append(e)
    return P, lay


def tier3(seed=303):
    """Imperial capital (~120 m)."""
    P = {
        "wall": lambda: p_wall(8.0, 10.0, 8.0, mat="W_StoneDark"),
        "corner_tower": lambda: p_corner_tower(13.0, 10.0, double=True, mat="W_StoneDark"),
        "gate": lambda: p_gate(30.0, 17.0, 11.0, 5.4, 7.6, n_arches=3, mat="W_StoneDark", tower=(7, 3), bay=3.9,
                               col_h=5.0, beasts=4),
        "arrow": lambda: p_arrow_tower(24.0, 10.0, 10.0),
        "bwall": lambda: p_wall(8.0, 9.0, 6.5, mat="W_StoneDark"),
        "redwall": p_red_wall,
        "pgate": lambda: p_gate(20.0, 10.0, 6.5, 3.6, 5.0, n_arches=3, mat="W_RedWall", tower=(5, 2), bay=3.4,
                                col_h=4.0, roof="W_TileGold", ridge="W_RidgeGold", beasts=4),
        "throne": lambda: p_hall(bays=(7, 4), bay=4.0, col_h=5.6, plat_h=1.5, roof="W_TileGold", ridge="W_RidgeGold",
                                 style="hip", double=True, tiers=3, balustrade=True, wall="W_RedWall", beasts=6,
                                 bracket_k=0.9, overhang=2.1, roof_h=7.2),
        "phall": lambda: p_hall(bays=(5, 3), bay=3.8, col_h=4.8, plat_h=1.2, roof="W_TileGold", ridge="W_RidgeGold",
                                style="hip_gable", wall="W_RedWall", beasts=4, balustrade=True, bracket_k=0.75),
        "pside": lambda: p_hall(bays=(5, 2), bay=3.4, col_h=4.0, plat_h=0.8, roof="W_TileGold", ridge="W_RidgeGold",
                                style="hip_gable", wall="W_RedWall", beasts=2, bracket_k=0.6, overhang=1.5),
        "bell": lambda: p_drum_tower(roof="W_TileGreen", W=17.0, D=17.0, H=8.0),
        "pagoda9": lambda: p_pagoda(9, 3.8),
        "pagoda7r": lambda: p_pagoda(7, 3.2, body="W_PlasterWarm", roof="W_TileGreen", ridge="W_RidgeGreen"),
        "temple": lambda: p_hall(bays=(5, 3), bay=3.4, col_h=4.2, plat_h=1.0, roof="W_TileGreen", ridge="W_RidgeGreen",
                                 style="hip_gable", wall="W_RedWall", beasts=2, plat_mat="W_Stone", bracket_k=0.6,
                                 overhang=1.6),
        "house_a": lambda: p_house(9.0, 5.6, pitch=0.7),
        "house_b": lambda: p_house(7.0, 5.0, "W_BrickWarm", "W_PlasterWarm", "W_TileDark", pitch=0.7),
        "house_hip": lambda: p_house_hip(11.0, 7.0, roof="W_TileDark"),
        "row": lambda: p_row_house(15.0, 6.0),
        "cwall": p_cwall,
        "cgate": p_cgate,
        "canal": p_canal,
        "bridge": p_bridge,
        "paifang": p_paifang,
    }
    hx, hy = 52.0, 50.0
    T = 8.0
    lay = Layout((hx - T + 0.5, hy - T + 0.5), seed)
    cx, cy = wall_ring(lay, P, hx, hy, T, 30.0, 13.0, gate_proto="gate")
    ix, iy = hx - T, hy - T
    # barbican in front of the main gate: two flanking walls and the arrow tower
    bx, byf = 17.0, -hy - 13.0
    lay.span("bwall", 8.0, (-bx, byf + 3.0), (-bx, -hy + 1.0), -R90)
    lay.span("bwall", 8.0, (bx, -hy + 1.0), (bx, byf + 3.0), R90)
    lay.span("bwall", 8.0, (-bx + 3.0, byf), (-12.0, byf), 0.0)
    lay.span("bwall", 8.0, (12.0, byf), (bx - 3.0, byf), 0.0)
    lay.put("arrow", 0.0, byf, 0.0)
    for (x, y) in ((-bx, byf), (bx, byf)):
        lay.put("bwall", x, y, 0.0, sx=0.8)
    # palace city: red wall x in [-24, 24], y in [-2, 38]
    px0, px1, py0, py1 = -24.0, 24.0, -2.0, 38.0
    lay.span("redwall", 8.0, (px0, py0), (-10.0, py0), 0.0)
    lay.span("redwall", 8.0, (10.0, py0), (px1, py0), 0.0)
    lay.span("redwall", 8.0, (px1, py0), (px1, py1), R90)
    lay.span("redwall", 8.0, (px1, py1), (px0, py1), math.pi)
    lay.span("redwall", 8.0, (px0, py1), (px0, py0), -R90)
    lay.put("pgate", 0.0, py0, 0.0)
    lay.put("throne", 0.0, 22.5, 0.0)
    lay.put("phall", 0.0, 6.5, 0.0, sx=0.92, sy=0.92, sz=0.92) if False else None
    lay.put("pside", -15.5, 11.0, -R90)
    lay.put("pside", 15.5, 11.0, R90)
    lay.paved.append((px0, py0, px1, py1))
    for (x, y) in ((-19.0, 33.0), (19.0, 33.0), (-19.0, 3.0), (19.0, 3.0)):
        lay.tree("pine", x, y, 0.34)
    # canal (golden water) across the city in front of the palace, with bridges
    ycan = -9.5
    lay.span("canal", 8.0, (-ix, ycan), (-12.0, ycan), 0.0)
    lay.span("canal", 8.0, (-4.0, ycan), (4.0, ycan), 0.0) if False else None
    lay.span("canal", 8.0, (12.0, ycan), (ix, ycan), 0.0)
    lay.span("canal", 8.0, (-12.0, ycan), (12.0, ycan), 0.0)
    lay.wet.append((-ix, ycan - 4.0, ix, ycan + 4.0))
    for x in (-30.0, 0.0, 30.0):
        lay.put("bridge", x, ycan, 0.0)
    lay.street(-3.5, -iy, 3.5, py0)
    lay.street(-ix, ycan - 7.5, ix, ycan - 4.0)
    lay.street(-ix, ycan + 4.0, ix, ycan + 7.5)
    lay.street(-33.0, -iy, -27.0, iy)
    lay.street(27.0, -iy, 33.0, iy)
    # bell tower at the southern crossroads
    lay.put("bell", 0.0, -27.0, 0.0)
    lay.street(-ix, -29.5, ix, -24.5)
    lay.paved.append(("ell", 0.0, -27.0, 13.0, 10.0))
    lay.put("paifang", 0.0, -40.0 + 2.0, 0.0) if False else None
    # temples: west 9-tier pagoda (back-left), east 7-tier
    lay.put("pagoda9", -36.5, 27.0, 0.0)
    lay.put("temple", -37.5, 12.5, 0.0)
    lay.paved.append(("ell", -37.0, 20.0, 6.0, 12.0))
    lay.put("pagoda7r", 37.0, 9.5, 0.0)
    lay.put("temple", 38.0, 23.0, 0.0)
    lay.paved.append(("ell", 37.5, 16.0, 6.0, 11.0))
    # compounds south of the canal
    for (x, y, rich) in ((-37.0, -33.0, True), (-15.0, -36.0, False), (15.0, -36.0, False), (37.0, -33.0, True),
                         (-16.5, -18.0, True), (16.5, -18.0, False)):
        lay.compound(x, y, 18.0 if abs(x) < 20 else 14.0, 13.0, 0.0, rich=rich)
    for (x, y, rz) in ((-38.0, -19.0, 0.0), (38.0, -19.0, 0.0)):
        lay.put("row", x, y, rz, sx=0.8)
    # compounds north of the canal outside the palace
    lay.compound(-36.0, 0.5, 13.0, 11.0, 0.0)
    lay.compound(36.0, 34.0, 13.0, 12.0, 0.0)
    lay.put("house_a", -36.5, 37.0, math.pi)
    for (x, y, s) in ((-27.0, -38.0, 0.42), (27.0, -38.0, 0.4), (-8.0, -38.0, 0.38), (8.5, -37.5, 0.4),
                      (-29.5, 4.0, 0.42), (29.5, 30.0, 0.42), (-6.5, -18.5, 0.36), (6.5, -18.5, 0.36),
                      (-28.0, 36.5, 0.4), (28.0, 4.5, 0.38)):
        lay.green.append(("ell", x, y, 3.0, 3.0))
        lay.tree("broad", x, y, s)
    for e in ((-ix, -iy, -ix + 2.5, iy), (ix - 2.5, -iy, ix, iy), (-ix, iy - 2.5, ix, iy)):
        lay.green.append(e)
    return P, lay


TIERS = {1: tier1, 2: tier2, 3: tier3}


# ---------------------------------------------------------------------------------------------
# ground mask
# ---------------------------------------------------------------------------------------------
def ground_mask(lay, size, path, seed=0):
    """Paint the layout strokes into an RGB mask (R paved, G green, B wet) over the ground plate
    and save it; row 0 = north (+y)."""
    from PIL import Image
    gx, gy = lay.half
    H = W = size
    ys = gy - (np.arange(H) + 0.5) / H * 2 * gy
    xs = -gx + (np.arange(W) + 0.5) / W * 2 * gx
    X, Y = np.meshgrid(xs, ys)
    out = np.zeros((H, W, 3), np.float32)
    for ch, strokes in ((0, lay.paved), (1, lay.green), (2, lay.wet)):
        m = np.zeros((H, W), np.float32)
        for s in strokes:
            if s[0] == "ell":
                _, cx, cy, rx, ry = s
                d = ((X - cx) / rx) ** 2 + ((Y - cy) / ry) ** 2
                m = np.maximum(m, np.clip((1.15 - d) / 0.3, 0, 1))
            else:
                x0, y0, x1, y1 = s
                dx = np.minimum(X - x0, x1 - X)
                dy = np.minimum(Y - y0, y1 - Y)
                m = np.maximum(m, np.clip(np.minimum(dx, dy) / 0.6 + 0.5, 0, 1))
        out[..., ch] = m
    # soften
    from .post import gaussian
    out = gaussian(out, max(1.0, size / 512.0))
    Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB").save(path)
    return path


def ground_plate(name, lay, res=48):
    """Flat ground grid over the plate (z = 0.04), GroundUV = UV0 = 0..1 planar."""
    import bpy
    gx, gy = lay.half
    mb = MeshBuilder()
    ids = [[mb.v((-gx + 2 * gx * i / res, -gy + 2 * gy * j / res, 0.04)) for i in range(res + 1)] for j in range(res + 1)]
    for j in range(res):
        for i in range(res):
            uv = [(i / res, j / res), ((i + 1) / res, j / res), ((i + 1) / res, (j + 1) / res), (i / res, (j + 1) / res)]
            mb.face((ids[j][i], ids[j][i + 1], ids[j + 1][i + 1], ids[j + 1][i]), "Ground", uv, False)
    # skirt down to -1.5 m under the edges (hidden by the walls; avoids gaps on sloped terrain)
    obj = mb.build(name, {}, auto_smooth_deg=None)
    me = obj.data
    me.uv_layers["UVMap"].name = "GroundUV"
    uv0 = me.uv_layers.new(name="UV0")
    buf = np.zeros(len(me.loops) * 2, np.float32)
    me.uv_layers["GroundUV"].data.foreach_get("uv", buf)
    uv0.data.foreach_set("uv", buf)
    me.uv_layers.active = uv0
    return obj
