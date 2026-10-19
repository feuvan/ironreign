"""Battle family: architecture for the board tiles (ramparts, gate, gate tower, houses, the
commander's hall, compound walls, banners, timber bridge, gate rubble).

Built with the World Models kit (:mod:`ironart.world_kit`, ``W_*`` gongbi materials of
:mod:`ironart.world_gongbi`) at **kit scale** :data:`K`: every piece is authored in kit metres
(the kit's MetreUV patterns - stone courses, tile channels, studs - keep their proportions) and
placed scaled by K, so the board's buildings are miniatures beside the 1.8 m soldiers (a
miniature-terrain convention; the gate tower tops out at ~6.4 m).  Line widths of the W_*
materials follow the atlas density times K (:func:`ironart.battle_mats.library`).

World frame: hex tile, +Z up, front (camera side) = -Y.  Ramparts run along Y with the outer
(battlemented) face towards -X; the merlon rhythm is global (5 per 6.928 m hex row, phase from
the hex edge), so a column of Wall / Gate / Rubble tiles reads as one continuous wall.
"""

import math

from mathutils import Matrix, Vector

from . import battle_props as PR
from . import world_kit as WK
from .geometry import MeshBuilder

K = 0.42
ROW = 6.928203230275509
HALF = ROW / 2
#: rampart (world metres)
WALL_H = 3.3          # walk level
WALL_T = 3.0          # base thickness
MERLON_N = 5          # merlons per hex row
MERLON_W = 0.74
MERLON_H = 0.42
PARAPET_H = 0.5
GATE_W = 3.7          # gate block along y
GATE_D = 3.5          # gate block along x


def kit(mb, build, M=None):
    """Build ``build(sub)`` in kit metres and append it scaled by K (then ``M``)."""
    sub = MeshBuilder()
    build(sub)
    m = (M if M is not None else Matrix.Identity(4)) @ Matrix.Scale(K, 4)
    mb.extend(sub, m)


def ROT_WALL():
    """Kit frame (along x, outer face -y) -> world (along -y, outer face -x)."""
    return Matrix.Rotation(-math.pi / 2, 4, "Z")


# ---------------------------------------------------------------------------------------------
# rampart
# ---------------------------------------------------------------------------------------------
def rampart(mb, y0, y1, cap0=True, cap1=True, H=WALL_H, T=WALL_T, merlons=True, mat="W_Stone",
            top="W_Paving", par="W_Brick", broken=None):
    """Battered city wall between world y0 < y1 along y (centred x = 0), outer face -x.
    Skirt to z = -1.  ``broken`` = (z_lo, z_hi, seed) replaces the parapet / merlons by a ragged
    broken top (rubble stubs)."""
    def build(sb):
        Hk = H / K
        hy = T / 2 / K
        z0 = -1.0 / K
        ob = 0.42 / K
        ib = 0.22 / K
        # kit x = -world y; the end caps sit 1 cm inside the hex edge (never coplanar with the skirt)
        e0 = 0.01 if cap0 else 0.0
        e1 = 0.01 if cap1 else 0.0
        xa, xb = -(y1 - e1) / K, -(y0 + e0) / K
        prof = [(-hy, z0), (-hy + ob, Hk), (hy - ib, Hk), (hy, z0)]

        def facequad(p, q, m, flip=False):
            ids = [sb.v((xa, p[0], p[1])), sb.v((xb, p[0], p[1])), sb.v((xb, q[0], q[1])), sb.v((xa, q[0], q[1]))]
            lu = math.hypot(q[0] - p[0], q[1] - p[1])
            uv = [(xa, p[1]), (xb, p[1]), (xb, p[1] + lu), (xa, p[1] + lu)]
            if flip:
                ids, uv = ids[::-1], uv[::-1]
            sb.face(ids, m, uv)

        facequad(prof[0], prof[1], mat)
        ids = [sb.v((xa, prof[1][0], Hk)), sb.v((xb, prof[1][0], Hk)), sb.v((xb, prof[2][0], Hk)), sb.v((xa, prof[2][0], Hk))]
        sb.face(ids, top, [(xa, prof[1][0]), (xb, prof[1][0]), (xb, prof[2][0]), (xa, prof[2][0])])
        facequad(prof[3], prof[2], mat, flip=True)
        for (x, flip, on) in ((xa, False, cap1), (xb, True, cap0)):
            if not on:
                continue
            poly = [(x, p[0], p[1]) for p in prof]
            ids = [sb.v(p) for p in poly]
            uv = [(p[1], p[2]) for p in poly]
            if not flip:
                ids, uv = ids[::-1], uv[::-1]
            sb.face(ids, mat, uv)
        L = xb - xa
        cx = (xa + xb) / 2
        # string course under the parapet (outer face)
        sb.box((cx, prof[1][0] - 0.06 / K, Hk - 0.16 / K), (L, 0.14 / K, 0.14 / K), par, skip=("bottom",))
        oy = prof[1][0] + 0.2 / K
        if broken is None:
            sb.box((cx, oy, Hk), (L, 0.36 / K, PARAPET_H / K), par, skip=("bottom",))
            if merlons:
                pitch = ROW / MERLON_N
                k0 = int(math.floor((y0 + HALF) / pitch)) - 1
                k1 = int(math.ceil((y1 + HALF) / pitch)) + 1
                for k in range(k0, k1 + 1):
                    yc = -HALF + pitch * (k + 0.5)
                    a, b = max(y0, yc - MERLON_W / 2), min(y1, yc + MERLON_W / 2)
                    if b - a < 0.05:
                        continue
                    xm = -(a + b) / 2 / K
                    sb.box((xm, oy, Hk + PARAPET_H / K), ((b - a) / K, 0.36 / K, MERLON_H / K), par)
            sb.box((cx, prof[2][0] - 0.12 / K, Hk), (L, 0.24 / K, 0.3 / K), par, skip=("bottom",))
        else:
            import random
            zlo, zhi, seed = broken
            rng = random.Random(seed)
            n = max(2, int(L / (0.5 / K)))
            for i in range(n):
                x = xa + L * (i + 0.5) / n
                h = rng.uniform(zlo, zhi) / K
                sb.box((x, oy, Hk), (L / n * rng.uniform(0.7, 1.0), 0.36 / K, h), par)
    kit(mb, build, ROT_WALL())


# ---------------------------------------------------------------------------------------------
# gate and tower
# ---------------------------------------------------------------------------------------------
def gate(mb, tower=True):
    """Gate block (city gate, tunnel along x, studded cinnabar doors toward -x) with a
    gate-tower pavilion on top; the rampart continues to the hex edges on both sides.
    Returns the top z (m)."""
    W, D, H = GATE_W, GATE_D, WALL_H + 0.15
    rampart(mb, -HALF, -W / 2 + 0.02, cap0=True, cap1=True)
    rampart(mb, W / 2 - 0.02, HALF, cap0=True, cap1=True)

    def build(sb):
        WK.gate_base(sb, W / K, D / K, H / K, 1.75 / K, 2.45 / K, mat="W_Stone", top="W_Paving", par="W_Brick",
                     batter=0.3 / K, skirt=1.0 / K, doors=True, crenels=True)
    kit(mb, build, ROT_WALL())
    top = H
    if tower:
        hs = WK.HallSpec(bays=(3, 2), bay=2.45, depth_bay=1.9, col_h=3.0, col_r=0.22, plat_h=0.0, steps=False,
                         front="lattice", side="wall", front_inset=0.0, brackets=True, bracket_k=0.6,
                         wall_mat="W_RedWall",
                         roof=WK.RoofSpec(style="hip_gable", overhang=1.0, lift=0.65, flare=0.3, thick=0.22,
                                          pitch=0.5, tile_seg=4, tile_faces=3, nv=5, mat="W_TileDark",
                                          ridge_mat="W_Ridge", chiwen=True),
                         roof_h=2.2)
        info = {}

        def build_t(sb):
            _, inf = WK.hall(sb, (0, 0, 0), hs)
            info.update(inf)
        kit(mb, build_t, Matrix.Translation(Vector((0.15, 0, H))) @ ROT_WALL())
        top = H + info.get("top", 7.0) * K
    return top


# ---------------------------------------------------------------------------------------------
# town and castle
# ---------------------------------------------------------------------------------------------
def house(mb, at, yaw, w=2.3, d=1.55, h=1.25, wall="W_Brick", upper="W_Plaster", roof="W_Tile", seed=0):
    """A small courtyard dwelling (world size w x d, wall height h), front toward its local -y."""
    hs = WK.HouseSpec(w=w / K, d=d / K, h=h / K, base=0.35, wall=wall, upper=upper, dado=1.0,
                      roof=WK.RoofSpec(style="gable", overhang=0.6, lift=0.2, flare=0.08, thick=0.2, pitch=0.5,
                                       tile_seg=3, tile_faces=2, nv=4, ridge_h=0.36, ridge_ends="curl", mat=roof,
                                       fascia_mat="W_WoodDark", under_mat="W_WoodDark"))
    kit(mb, lambda sb: WK.house(sb, (0, 0, 0), hs),
        Matrix.Translation(Vector(at)) @ Matrix.Rotation(yaw, 4, "Z"))


def compound_wall(mb, p0, p1, h=0.75, t=0.24):
    """Low tiled compound wall from world p0 to p1 (xy)."""
    a, b = Vector((p0[0], p0[1], 0)), Vector((p1[0], p1[1], 0))
    L = (b - a).length
    ang = math.atan2(b.y - a.y, b.x - a.x)
    c = (a + b) / 2
    kit(mb, lambda sb: WK.courtyard_wall(sb, L / K, h=h / K, t=t / K, mat="W_RedWall", cap="W_TileDark",
                                         top_mat="W_RedWall"),
        Matrix.Translation(c) @ Matrix.Rotation(ang, 4, "Z"))


def command_hall(mb, at=(0.0, 2.45, 0.0)):
    """The commander's hall: marble terrace with steps, red columns, painted beams, brackets,
    double-eaved hip roof with gilt ridge ends; facing -y (the courtyard and the camera)."""
    hs = WK.HallSpec(bays=(3, 1), bay=3.1, depth_bay=2.9, col_h=3.3, col_r=0.24, plat_h=0.75, plat_margin=0.55,
                     steps=True, front="lattice", side="wall", front_inset=0.0, brackets=True, bracket_k=0.6,
                     wall_mat="W_RedWall", double=True, upper_h=1.6,
                     roof=WK.RoofSpec(style="hip", overhang=1.05, lift=0.7, flare=0.35, thick=0.22, pitch=0.45,
                                      tile_seg=4, tile_faces=3, nv=5, mat="W_TileDark", ridge_mat="W_Ridge",
                                      chiwen=True),
                     roof_h=1.9)
    kit(mb, lambda sb: WK.hall(sb, (0, 0, 0), hs), Matrix.Translation(Vector(at)))


def banner(mb, at, height=4.6, cloth=(0.75, 1.5), seed=0, mat="B_Cinnabar", yaw=0.0):
    """War banner on a lacquered pole: a tall cinnabar cloth with a mud-gold border and tail
    ribbons, hanging from a crossbar, gently waving."""
    import random
    rng = random.Random(seed)
    at = Vector(at)
    top = at + Vector((0, 0, height))
    mb.cylinder(tuple(at + Vector((0, 0, -0.2))), tuple(top), 0.045, 0.035, "W_Lacquer", 8)
    mb.cylinder(tuple(top), tuple(top + Vector((0, 0, 0.22))), 0.03, 0.0, "B_Gold", 6)
    W, Hc = cloth
    R = Matrix.Rotation(yaw, 3, "Z")
    side = R @ Vector((1, 0, 0))
    bar = top - Vector((0, 0, 0.12))
    mb.cylinder(tuple(bar - side * 0.05), tuple(bar + side * (W + 0.05)), 0.018, 0.018, "W_Lacquer", 6)
    ph = rng.uniform(0, math.tau)

    def fp(u, v):
        p = bar + side * (u * W) - Vector((0, 0, v * Hc))
        wave = 0.08 * math.sin(u * 4.5 + ph + v * 1.5) * (0.25 + u)
        p += R @ Vector((0, wave, 0)) + Vector((0, 0, -0.04 * u * u))
        return tuple(p)
    mb.grid(fp, 8, 8, mat, uv_fn=lambda u, v: (u * W, v * Hc), smooth=True)
    mb.grid(fp, 8, 8, mat, uv_fn=lambda u, v: (u * W, v * Hc), smooth=True, flip=True)
    # mud-gold border strip at the hem and the free edge
    mb.grid(lambda u, v: tuple(Vector(fp(u, 1.0)) - Vector((0, 0, 0.07 * v))), 8, 1, "B_Gold",
            uv_fn=lambda u, v: (u, v), smooth=True)
    mb.grid(lambda u, v: tuple(Vector(fp(u, 1.0)) - Vector((0, 0, 0.07 * v))), 8, 1, "B_Gold",
            uv_fn=lambda u, v: (u, v), smooth=True, flip=True)


# ---------------------------------------------------------------------------------------------
# bridge
# ---------------------------------------------------------------------------------------------
def timber_bridge(mb, L=8.8, W=2.7, rise=0.26, z_end=0.02, water_z=-0.32):
    """Wooden arched beam bridge along x (corner to corner of the hex, landing on the banks):
    cambered plank deck with ruled plank joints, side beams, lacquered rails on posts, two
    timber trestle piers in the water and arched struts beneath."""
    def build(sb):
        Lk, Wk = L / K, W / K
        hw = Wk / 2

        def deck_z(x):
            t = x / (Lk / 2)
            return (z_end + rise * (1 - t * t)) / K

        n = 16
        xs = [-Lk / 2 + Lk * i / n for i in range(n + 1)]
        th = 0.16 / K
        top = [(x, deck_z(x)) for x in xs]
        # deck slab: top planks, underside, sides (side beams)
        for i in range(n):
            (x0, z0), (x1, z1) = top[i], top[i + 1]
            sb.face([sb.v((x0, -hw, z0)), sb.v((x1, -hw, z1)), sb.v((x1, hw, z1)), sb.v((x0, hw, z0))], "W_Wood",
                    [(-hw, x0), (-hw, x1), (hw, x1), (hw, x0)])
            sb.face([sb.v((x0, hw, z0 - th)), sb.v((x1, hw, z1 - th)), sb.v((x1, -hw, z1 - th)), sb.v((x0, -hw, z0 - th))],
                    "W_WoodDark", [(hw, x0), (hw, x1), (-hw, x1), (-hw, x0)])
            for sy in (-1, 1):
                y = sy * hw
                q = [sb.v((x0, y, z0 - th - 0.06 / K)), sb.v((x1, y, z1 - th - 0.06 / K)), sb.v((x1, y, z1 + 0.02 / K)),
                     sb.v((x0, y, z0 + 0.02 / K))]
                uv = [(x0, 0), (x1, 0), (x1, th), (x0, th)]
                if sy > 0:
                    q, uv = q[::-1], uv[::-1]
                sb.face(q, "W_WoodDark", uv)
        for (x, z) in (top[0], top[-1]):
            sx = -1 if x < 0 else 1
            q = [sb.v((x, -hw, z - th)), sb.v((x, hw, z - th)), sb.v((x, hw, z)), sb.v((x, -hw, z))]
            if sx < 0:
                q = q[::-1]
            sb.face(q, "W_WoodDark")
        # rails: posts + a top rail + a mid rail, lacquered
        post = 0.09 / K
        rail_h = 0.72 / K
        for sy in (-1, 1):
            y = sy * (hw - 0.06 / K)
            for i in range(0, n + 1, 2):
                x, z = top[i]
                sb.box((x, y, z), (post, post, rail_h + 0.08 / K), "W_Lacquer")
                sb.box((x, y, z + rail_h + 0.08 / K), (post * 1.3, post * 1.3, 0.05 / K), "B_Gold")
            for hh, r in ((rail_h, 0.035 / K), (rail_h * 0.45, 0.025 / K)):
                sb.tube([(x, y, z + hh) for (x, z) in top], r, "W_Lacquer", 6)
        # piers: two rows of posts in the water with cap beams and cross bracing
        zw = water_z / K
        for xp in (-Lk * 0.2, Lk * 0.2):
            zt = deck_z(xp) - th
            for yp in (-hw * 0.8, -hw * 0.27, hw * 0.27, hw * 0.8):
                sb.cylinder((xp, yp, zw - 0.6 / K), (xp, yp, zt), 0.07 / K, 0.065 / K, "W_WoodDark", 8)
            sb.box((xp, 0, zt - 0.14 / K), (0.16 / K, Wk * 0.95, 0.14 / K), "W_WoodDark")
            sb.cylinder((xp, -hw * 0.8, zw + 0.05 / K), (xp, hw * 0.8, zt - 0.15 / K), 0.03 / K, 0.03 / K, "W_WoodDark", 6)
        # arched struts under the deck (the "arched" timber bridge)
        for yp in (-hw * 0.55, hw * 0.55):
            pts = []
            for i in range(13):
                t = -1 + 2 * i / 12
                x = t * Lk * 0.42
                z = zw + 0.02 / K + (deck_z(x) - th - zw - 0.02 / K) * (1 - 0.35 * t * t) ** 1.0
                pts.append((x, yp, min(z, deck_z(x) - th)))
            sb.tube(pts, 0.06 / K, "W_WoodDark", 6)
        # stone abutments at the banks
        for sx in (-1, 1):
            x = sx * (Lk / 2 - 0.45 / K)
            sb.box((x, 0, zw - 0.7 / K), (0.9 / K, Wk + 0.3 / K, (z_end - water_z + 0.68) / K), "W_Stone",
                   skip=("bottom",))
    kit(mb, build)
