"""World Models family: the gongbi (工笔) / jiehua (界画) look of the 3D models (DESIGN.md 8 + 12.3).

Unreal renders the models under a painted post-process (ink outlines, silk grading, soft light), so
their **base colour is painted, not photographed**: flat mineral-colour washes with soft 晕染
gradients and a faint mineral granulation, painted structure (tile channels, block and brick
courses, layer lines of rammed earth, wood grain, caihua bands) in graded ink tones, and **no**
baked AO, dirt, moss, rain streaks or photo texture.  Roughness is high and uniform (matte
pigment, :data:`ROUGH`), metallic is 0 everywhere (mud-gold is a pigment, not metal), normal
maps are subtle (only the painted structure is embossed a little).

:func:`library` returns the same slot names as :func:`ironart.world_mats.library` (``W_Stone``,
``W_TileDark``...), so every :mod:`world_kit` / :mod:`world_city` builder works unchanged: the
geometry stays the same, only the paint changes.  Patterns read ``MetreUV`` (metres) and object
space exactly like ``world_mats``; painted line widths follow the atlas texel density
(:func:`set_density`) so a ruled line is never thinner than ~1 texel (no moire, no aliasing).

Foliage: :func:`leaf_atlas` renders the modelled leaves of :mod:`world_trees` as gongbi leaves:
flat malachite / azurite washes darkening towards the leaf base (晕染), double-line ink outlines
(双勾) found from a per-leaf ID pass, pine needles as ink-green strokes over a soft malachite
wash pad.  :func:`bark_texture` bakes seamless painted bark (ink scale rings on pine, furrows on
broadleaf, ink node rings on bamboo).

The mineral palette (:data:`G`) is the one shared by every gongbi family (DESIGN.md section 8).
"""

import math
import os
import random

import bpy
import numpy as np

from . import scene
from .geometry import MeshBuilder
from .materials import NB
from .world_mats import W, L, _new

TAU = math.tau

#: the shared gongbi mineral palette (sRGB) plus the World Models mixes used on buildings
G = {
    "ink": "#1E1A16", "silk": "#E6D6B0", "silk_d": "#D8C39A",
    "malachite": "#3E8E6E", "malachite_l": "#8CBFA0", "malachite_d": "#2C6A52",
    "azurite": "#2B5C8A", "azurite_l": "#7FA6C8", "azurite_d": "#22476C",
    "cinnabar": "#B5382A", "vermilion": "#D0643C", "ochre": "#A0643A", "rouge": "#9E3B4A",
    "gold": "#C9A24B", "white": "#F0E8D8",
    # building mixes (washes of the minerals above over silk, graded with ink)
    "stone": "#ABA190", "stone_dk": "#9C9A92", "stone_line": "#615A50",
    "brick": "#9DA3A4", "brick_w": "#A9A195", "mortar": "#D9D2C2",
    "paving": "#C2B9A5", "pave_line": "#8C8474",
    "earth": "#BDA07A", "earth_line": "#8C7052",
    "plaster": "#EEE5D2", "plaster_w": "#E6D6B6",
    "redwall": "#AE4535", "marble": "#EBE4D4",
    "lacquer": "#B5382A", "lacquer_dk": "#8C2C22",
    "wood": "#93653F", "wood_dk": "#644430", "grain": "#4A3020",
    "tile": "#8A949C", "tile_line": "#4C5660", "tile_dk": "#75808B", "tile_dk_line": "#3E4852",
    "tile_gold": "#D4A748", "tile_gold_line": "#97672A", "tile_green": "#3E8E6E",
    "tile_green_line": "#245E48",
    "ridge": "#4B545D", "ridge_gold": "#B9882F", "ridge_green": "#2C6A52",
    "fascia": "#3B2C22", "paper": "#EADDC2", "dark": "#2E2822", "iron": "#4C4A48",
    "rock": "#B78E60", "rock_line": "#3A3026",
}
#: matte pigment
ROUGH = 0.9
#: atlas texel density (px per metre) the painted line widths follow (see set_density)
_PX = [13.0]


def set_density(px_per_m):
    """Painted lines are drawn at least ~1.1 texels wide at this atlas density (px / m)."""
    _PX[0] = max(2.0, float(px_per_m))


def density():
    return _PX[0]


def atlas_density(objs, size):
    """Texel density (px / m) of the atlas: area-weighted median over the faces of ``objs``
    (active UV layer) - robust to the trim strips, swatches and roof rows."""
    dens = []
    wts = []
    for o in objs:
        me = o.data
        uv = me.uv_layers.active
        if uv is None:
            continue
        for p in me.polygons:
            if p.area < 0.05:
                continue
            pts = [uv.data[li].uv for li in p.loop_indices]
            s = 0.0
            for i in range(1, len(pts) - 1):
                (x0, y0), (x1, y1), (x2, y2) = pts[0], pts[i], pts[i + 1]
                s += abs((x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)) * 0.5
            if s > 0:
                dens.append(math.sqrt(s * size * size / p.area))
                wts.append(p.area)
    if not dens:
        return _PX[0]
    order = np.argsort(dens)
    cw = np.cumsum(np.array(wts)[order])
    return float(np.array(dens)[order][np.searchsorted(cw, cw[-1] * 0.5)])


# ---------------------------------------------------------------------------------------------
# node vocabulary
# ---------------------------------------------------------------------------------------------
class GW(W):
    """:class:`ironart.world_mats.W` plus washes and anti-aliased painted lines."""

    def line(self, dist, half_m, soft=1.0):
        """1 on a ruled line of half width ``half_m`` metres (>= ~0.55 texel) at distance
        ``dist`` (metres), 0 off it; anti-aliased over ~1 texel."""
        px = _PX[0]
        hw = max(half_m, 0.55 / px)
        t = 0.5 * soft / px
        return self.mr(dist, hw - t, hw + t, 1.0, 0.0)

    def wash(self, col, amount=0.05, scale=0.22, grain=0.03, gscale=24.0):
        """Flat colour -> a hand-laid wash: a soft low-frequency 晕染 swell (+-``amount``) and
        a faint mineral granulation (+-``grain``)."""
        o = self.obj()
        big = self.noise(self.scale(o, scale), 1.0, 2, 0.5)
        col = self.mix(self.mul(col, self.gray(1.0 - amount)), self.mul(col, self.gray(1.0 + amount * 0.7)),
                       self.mr(big, 0.3, 0.7))
        if grain > 0:
            fine = self.noise(self.scale(o, gscale), 1.0, 2, 0.5)
            col = self.mul(col, self.gray(self.mr(fine, 0.3, 0.7, 1.0 - grain, 1.0 + grain * 0.6)))
        return col

    def foot(self, col, h=1.4, k=0.88, tint=None, amount=0.0):
        """Graded deepening towards the wall foot (a wash laid darker at the bottom - never grime)."""
        z = self.height_z()
        f = self.mr(z, 0.0, h, 1.0, 0.0, interp="SMOOTHSTEP")
        out = self.mix(col, self.mul(col, self.gray(k)), f)
        if tint and amount:
            out = self.mix(out, L(tint), self.m("MULTIPLY", f, amount))
        return out

    def ink(self, col, mask, color, alpha=1.0):
        return self.mix(col, L(color), self.m("MULTIPLY", mask, alpha) if alpha != 1.0 else mask)

    def grid(self, uv, bw, bh, offset=0.5):
        """Running-bond block grid on ``uv`` (metres): (dist to bed joints, dist to head joints,
        block id vector)."""
        s = self.sep(uv)
        y = self.m("DIVIDE", s["Y"], bh)
        row = self.m("FLOOR", y)
        fy = self.m("FRACT", y)
        shift = self.m("MULTIPLY", self.m("FLOOR", self.m("MULTIPLY", self.m("FRACT", self.m("MULTIPLY", row, 0.5)), 2.0)),
                       offset)
        x = self.m("ADD", self.m("DIVIDE", s["X"], bw), shift)
        col = self.m("FLOOR", x)
        fx = self.m("FRACT", x)
        dh = self.m("MULTIPLY", self.m("MINIMUM", fy, self.m("SUBTRACT", 1.0, fy)), bh)
        dv = self.m("MULTIPLY", self.m("MINIMUM", fx, self.m("SUBTRACT", 1.0, fx)), bw)
        return dh, dv, self.comb(col, row, 0.0)

    def periodic_dist(self, x, period):
        """Distance (metres) from ``x`` to the nearest multiple of ``period``."""
        f = self.m("FRACT", self.m("DIVIDE", x, period))
        return self.m("MULTIPLY", self.m("MINIMUM", f, self.m("SUBTRACT", 1.0, f)), period)

    def tone(self, ids, spread=0.06, scale=3.7):
        """Per-block tone multiplier (grey colour) from a block id vector."""
        n = self.noise(ids, scale, 1)
        return self.gray(self.mr(n, 0.25, 0.75, 1.0 - spread, 1.0 + spread * 0.6))

    def paint_out(self, base, height=None, strength=0.2, distance=0.02, rough=ROUGH):
        nrm = self.bump(height, strength, distance) if height is not None else None
        return self.out(base, rough, 0.0, nrm, spec=0.3)


def _mat(name):
    mat, nb = _new(name)
    return mat, (GW(nb) if nb is not None else None)


# ---------------------------------------------------------------------------------------------
# masonry and walls
# ---------------------------------------------------------------------------------------------
def stone(name="W_Stone", color=G["stone"], line=G["stone_line"], block=(1.25, 0.55), alpha=0.55):
    """Ashlar city wall: warm grey wash, ruled ink-grey block joints, faint per-block tone."""
    mat, w = _mat(name)
    if w is None:
        return mat
    uv = w.uv()
    dh, dv, ids = w.grid(uv, *block)
    col = w.mul(L(color), w.tone(ids, 0.05))
    col = w.wash(col, 0.05)
    col = w.foot(col, 1.6, 0.9)
    joints = w.m("MAXIMUM", w.line(dh, 0.025), w.line(dv, 0.025))
    col = w.ink(col, joints, line, alpha)
    w.paint_out(col, w.m("SUBTRACT", 1.0, joints), 0.18, 0.03)
    return mat


def brick(name="W_Brick", color=G["brick"], mortar=G["mortar"], size=(0.96, 0.42), alpha=0.6):
    """Grey qing brick, painted as ruled courses (one line per three brick courses, readable at
    the map's texel density) in pale mortar over a blue-grey wash."""
    mat, w = _mat(name)
    if w is None:
        return mat
    uv = w.uv()
    dh, dv, ids = w.grid(uv, *size)
    col = w.mul(L(color), w.tone(ids, 0.04))
    col = w.wash(col, 0.05)
    col = w.foot(col, 1.2, 0.92)
    joints = w.m("MAXIMUM", w.line(dh, 0.018), w.m("MULTIPLY", w.line(dv, 0.016), 0.7))
    col = w.ink(col, joints, mortar, alpha)
    w.paint_out(col, w.m("SUBTRACT", 1.0, joints), 0.12, 0.02)
    return mat


def paving(name="W_Paving", color=G["paving"], line=G["pave_line"], size=(1.2, 1.2), alpha=0.45):
    mat, w = _mat(name)
    if w is None:
        return mat
    uv = w.uv()
    dh, dv, ids = w.grid(uv, *size)
    col = w.mul(L(color), w.tone(ids, 0.04))
    col = w.wash(col, 0.05, 0.12)
    joints = w.m("MAXIMUM", w.line(dh, 0.02), w.line(dv, 0.02))
    col = w.ink(col, joints, line, alpha)
    w.paint_out(col, w.m("SUBTRACT", 1.0, joints), 0.1, 0.02)
    return mat


def rammed_earth(name="W_Earth", color=G["earth"], line=G["earth_line"], layer=0.34):
    """Rammed-earth town wall: ochre wash, tamped layers as soft ruled ochre lines, a gentle
    deeper wash at the foot."""
    mat, w = _mat(name)
    if w is None:
        return mat
    uv = w.uv()
    s = w.sep(uv)
    wob = w.noise(w.scale(uv, (0.5, 0.5, 0.5)), 1.0, 2)
    y = w.m("ADD", s["Y"], w.m("MULTIPLY", wob, 0.05))
    band_id = w.m("FLOOR", w.m("DIVIDE", y, layer))
    col = w.mul(L(color), w.tone(w.comb(band_id, 0.0, 0.0), 0.05, 1.7))
    col = w.wash(col, 0.06, 0.15)
    col = w.foot(col, 1.6, 0.86)
    lines = w.line(w.periodic_dist(y, layer), 0.02)
    col = w.ink(col, lines, line, 0.4)
    w.paint_out(col, w.m("SUBTRACT", 1.0, lines), 0.12, 0.03)
    return mat


def plaster(name="W_Plaster", color=G["plaster"], foot_tint="#CDB792"):
    """Lead-white lime plaster: flat, a pale ochre wash rising from the foot."""
    mat, w = _mat(name)
    if w is None:
        return mat
    col = w.wash(L(color), 0.03, 0.3, 0.02)
    col = w.foot(col, 1.2, 0.97, foot_tint, 0.35)
    w.paint_out(col)
    return mat


def red_wall(name="W_RedWall", color=G["redwall"]):
    """Palace / temple wall: cinnabar-rouge wash, graded a little deeper at the foot."""
    mat, w = _mat(name)
    if w is None:
        return mat
    col = w.wash(L(color), 0.05, 0.25, 0.025)
    col = w.foot(col, 1.6, 0.88)
    w.paint_out(col)
    return mat


def marble(name="W_Marble", color=G["marble"]):
    """Lead-white marble terraces and balustrades: flat, a whisper of grey wash."""
    mat, w = _mat(name)
    if w is None:
        return mat
    col = w.wash(L(color), 0.035, 0.4, 0.02)
    col = w.foot(col, 0.8, 0.94)
    w.paint_out(col)
    return mat


def rock(name="W_Rock", color=G["rock"], line=G["rock_line"]):
    """Blue-green landscape (青绿山水) rock: ochre underpainting on the faces, malachite laid on
    up-facing ledges and slopes, azurite on the highest tops, ink texture strokes (皴) along the
    strata and the cracks."""
    mat, w = _mat(name)
    if w is None:
        return mat
    o = w.obj()
    s = w.sep(o)
    nz = w.sep(w.nb.coord("Normal"))["Z"]
    wob = w.noise(w.scale(o, 0.15), 1.0, 2)
    zz = w.m("ADD", s["Z"], w.m("MULTIPLY", wob, 3.0))
    # ochre underlayer, paler up the cliff (wash graded with height)
    base = w.mix(L(color, 0.86), L("#C9A57A"), w.mr(s["Z"], 0.0, 22.0))
    base = w.wash(base, 0.06, 0.18, 0.03)
    # mineral green on up-facing parts, azurite on high tops; soft wash boundaries
    patch = w.noise(w.scale(o, 0.35), 1.0, 3, 0.5)
    up = w.mr(w.m("ADD", nz, w.m("MULTIPLY", w.m("SUBTRACT", patch, 0.5), 0.5)), 0.42, 0.8)
    green = w.mix(L(G["malachite"]), L("#5FA585"), w.mr(patch, 0.35, 0.65))
    high = w.m("MULTIPLY", w.mr(s["Z"], 16.0, 30.0), w.mr(nz, 0.5, 0.85))
    green = w.mix(green, L(G["azurite"], 1.05), w.m("MULTIPLY", high, 0.85))
    col = w.mix(base, green, up)
    # 皴 texture strokes: strata lines + crack lines, both thin graded ink
    strata = w.line(w.periodic_dist(zz, 1.1), 0.03)
    brk = w.noise(w.scale(o, (0.6, 0.6, 0.2)), 1.0, 2)
    strata = w.m("MULTIPLY", strata, w.mr(brk, 0.45, 0.6))
    cr = w.voronoi(w.scale(o, (0.35, 0.35, 0.6)), 1.0, "DISTANCE_TO_EDGE")
    crack = w.m("MULTIPLY", w.mr(cr, 0.0, 0.06, 1.0, 0.0), w.mr(brk, 0.3, 0.5))
    strokes = w.m("MAXIMUM", strata, crack)
    strokes = w.m("MULTIPLY", strokes, w.mr(nz, 0.75, 0.4))      # strokes on the faces, not the tops
    col = w.ink(col, strokes, line, 0.55)
    w.paint_out(col, w.m("SUBTRACT", 1.0, strokes), 0.2, 0.05)
    return mat


# ---------------------------------------------------------------------------------------------
# timber, lacquer, caihua
# ---------------------------------------------------------------------------------------------
def lacquer(name="W_Lacquer", color=G["lacquer"]):
    """Cinnabar lacquer columns and frames: a flat mineral red with a soft graded wash."""
    mat, w = _mat(name)
    if w is None:
        return mat
    col = w.wash(L(color), 0.05, 0.5, 0.02)
    col = w.foot(col, 0.8, 0.9)
    w.paint_out(col)
    return mat


def wood(name="W_Wood", color=G["wood"], grain=G["grain"]):
    """Timber: ochre-brown wash with painted grain lines along MetreUV u."""
    mat, w = _mat(name)
    if w is None:
        return mat
    uv = w.uv()
    s = w.sep(uv)
    wob = w.noise(w.scale(uv, (0.8, 4.0, 1.0)), 1.0, 2)
    y = w.m("ADD", s["Y"], w.m("MULTIPLY", wob, 0.06))
    g = w.m("MULTIPLY", w.line(w.periodic_dist(y, 0.16), 0.012), w.mr(wob, 0.3, 0.6))
    col = w.wash(L(color), 0.05, 0.4, 0.02)
    col = w.ink(col, g, grain, 0.35)
    w.paint_out(col, w.m("SUBTRACT", 1.0, g), 0.08, 0.01)
    return mat


def beam_paint(name="W_BeamPaint", c1=G["malachite"], c2=G["azurite"], gold=G["gold"], period=1.0):
    """Architrave caihua (旋子彩画) in mineral colours: azurite field, malachite box head and end
    bands, mud-gold rims, lead-white pin lines and swirls.  MetreUV u is 0..1 per bay (as
    world_mats.beam_paint, shared trim strip), v in metres up the face."""
    mat, w = _mat(name)
    if w is None:
        return mat
    uv = w.uv()
    s = w.sep(uv)
    u = w.m("FRACT", w.m("DIVIDE", s["X"], period))
    v = w.m("FRACT", w.m("DIVIDE", s["Y"], 0.55))
    d = w.m("ABSOLUTE", w.m("SUBTRACT", u, 0.5))
    col = w.mix(L(c2), L(c1), w.mr(d, 0.16, 0.17))
    col = w.mix(col, L(c1), w.mr(d, 0.40, 0.41))
    rim = w.m("MAXIMUM", w.mr(w.m("ABSOLUTE", w.m("SUBTRACT", d, 0.165)), 0.012, 0.0),
              w.mr(w.m("ABSOLUTE", w.m("SUBTRACT", d, 0.405)), 0.012, 0.0))
    col = w.mix(col, L(gold), rim)
    vline = w.m("MAXIMUM", w.mr(v, 0.07, 0.04), w.mr(v, 0.93, 0.96))
    col = w.mix(col, L(G["white"]), w.m("MULTIPLY", vline, 0.9))
    ring = w.m("SINE", w.m("MULTIPLY", w.m("SQRT", w.m("ADD", w.m("POWER", w.m("SUBTRACT", d, 0.29), 2.0),
                                                        w.m("POWER", w.m("MULTIPLY", w.m("SUBTRACT", v, 0.5), 0.35), 2.0))), 90.0))
    swirl = w.m("MULTIPLY", w.mr(ring, 0.6, 0.9), w.mr(d, 0.18, 0.2))
    swirl = w.m("MULTIPLY", swirl, w.mr(d, 0.39, 0.37))
    col = w.mix(col, L(G["azurite_l"]), w.m("MULTIPLY", swirl, 0.75))
    col = w.wash(col, 0.03, 0.5, 0.02)
    w.paint_out(col, rim, 0.06, 0.004)
    return mat


def bracket(name="W_Bracket", c1=G["malachite"], c2=G["azurite"]):
    """Dougong: malachite and azurite blocks alternating (object-space checker), lighter
    granular wash."""
    mat, w = _mat(name)
    if w is None:
        return mat
    s = w.sep(w.obj())
    k = w.m("ADD", w.m("ADD", w.m("FLOOR", w.m("DIVIDE", s["X"], 0.55)), w.m("FLOOR", w.m("DIVIDE", s["Y"], 0.55))),
            w.m("FLOOR", w.m("DIVIDE", s["Z"], 0.32)))
    par = w.m("FRACT", w.m("MULTIPLY", k, 0.5))
    col = w.mix(L(c1), L(c2), w.mr(par, 0.2, 0.3))
    col = w.wash(col, 0.04, 0.6, 0.03)
    w.paint_out(col)
    return mat


def lattice(name="W_Lattice", frame="#A63A2B", paper=G["paper"], cell=0.16, bar=0.022, sill=0.9):
    """Door / window bays: cinnabar lattice over paper-white panels, a solid sill board."""
    mat, w = _mat(name)
    if w is None:
        return mat
    uv = w.uv()
    s = w.sep(uv)
    fx = w.m("ABSOLUTE", w.m("SUBTRACT", w.m("FRACT", w.m("DIVIDE", s["X"], cell)), 0.5))
    fy = w.m("ABSOLUTE", w.m("SUBTRACT", w.m("FRACT", w.m("DIVIDE", s["Y"], cell)), 0.5))
    half = 0.5 - bar / cell
    bars = w.m("MAXIMUM", w.mr(fx, half - 0.04, half), w.mr(fy, half - 0.04, half))
    diag = w.m("ABSOLUTE", w.m("SUBTRACT", w.m("FRACT", w.m("DIVIDE", w.m("ADD", s["X"], s["Y"]), cell * 2.0)), 0.5))
    bars = w.m("MAXIMUM", bars, w.m("MULTIPLY", w.mr(diag, 0.06, 0.03), 0.7))
    col = w.mix(L(paper), L(frame), bars)
    board = w.mr(s["Y"], sill - 0.02, sill + 0.02, 1.0, 0.0)
    col = w.mix(col, L(frame, 0.85), board)
    col = w.wash(col, 0.03, 0.5, 0.02)
    w.paint_out(col, w.m("MAXIMUM", bars, board), 0.15, 0.01)
    return mat


def gate_door(name="W_GateDoor", color="#B03628", stud=G["gold"], pitch=0.55):
    """Gate leaves: cinnabar with rows of mud-gold bosses (门钉), each ringed with a fine ink line."""
    mat, w = _mat(name)
    if w is None:
        return mat
    uv = w.uv()
    s = w.sep(uv)
    fx = w.m("SUBTRACT", w.m("FRACT", w.m("DIVIDE", s["X"], pitch)), 0.5)
    fy = w.m("SUBTRACT", w.m("FRACT", w.m("DIVIDE", s["Y"], pitch)), 0.5)
    r = w.m("MULTIPLY", w.m("SQRT", w.m("ADD", w.m("POWER", fx, 2.0), w.m("POWER", fy, 2.0))), pitch)
    boss = w.line(r, 0.09)
    ring = w.line(w.m("ABSOLUTE", w.m("SUBTRACT", r, 0.1)), 0.012)
    col = w.wash(L(color), 0.04, 0.5, 0.02)
    col = w.mix(col, L(stud), boss)
    col = w.ink(col, ring, G["ink"], 0.55)
    w.paint_out(col, boss, 0.3, 0.02)
    return mat


def flat(name, color, amount=0.04):
    mat, w = _mat(name)
    if w is None:
        return mat
    w.paint_out(w.wash(L(color), amount, 0.5, 0.02))
    return mat


# ---------------------------------------------------------------------------------------------
# roofs
# ---------------------------------------------------------------------------------------------
def roof_tile(name="W_Tile", color=G["tile"], line=G["tile_line"], pitch=0.5, alpha=0.4, light=None):
    """Tiled roof painted as in jiehua: an even wash with the tile channels ruled in graded ink
    every ``pitch`` m across the slope (MetreUV u, matching the builder's cover rows), each pan
    graded lighter in its middle (晕染) - no moss, dust or gloss."""
    mat, w = _mat(name)
    if w is None:
        return mat
    uv = w.uv()
    s = w.sep(uv)
    u = w.m("FRACT", w.m("DIVIDE", s["X"], pitch))
    col_id = w.m("FLOOR", w.m("DIVIDE", s["X"], pitch))
    row = w.m("FLOOR", w.m("DIVIDE", s["Y"], 0.9))
    pan = w.m("SINE", w.m("MULTIPLY", u, math.pi))
    col = w.mul(L(color), w.tone(w.comb(col_id, row, 0.0), 0.035, 2.3))
    col = w.mix(w.mul(col, w.gray(0.9)), L(light) if light else w.mul(col, w.gray(1.06)), w.mr(pan, 0.0, 1.0))
    col = w.wash(col, 0.05, 0.12, 0.025)
    gutter = w.line(w.periodic_dist(s["X"], pitch), 0.03)
    col = w.ink(col, gutter, line, alpha)
    h = w.m("SUBTRACT", w.m("MULTIPLY", pan, 0.6), w.m("MULTIPLY", gutter, 0.4))
    w.paint_out(col, h, 0.22, 0.03)
    return mat


def fascia(name="W_Fascia", band=G["fascia"], end1=G["malachite"], end2=G["azurite"], pitch=0.5):
    """Eave edge: ink-brown rafter band with painted rafter ends (malachite / azurite rings,
    lead-white ring line)."""
    mat, w = _mat(name)
    if w is None:
        return mat
    uv = w.uv()
    s = w.sep(uv)
    fx = w.m("SUBTRACT", w.m("FRACT", w.m("DIVIDE", s["X"], pitch)), 0.5)
    fy = w.m("SUBTRACT", w.m("FRACT", w.m("DIVIDE", s["Y"], 0.3)), 0.5)
    r = w.m("SQRT", w.m("ADD", w.m("POWER", fx, 2.0), w.m("POWER", w.m("MULTIPLY", fy, 0.6), 2.0)))
    ring = w.mr(r, 0.3, 0.26)
    col = w.mix(L(band), L(end1), ring)
    col = w.mix(col, L(end2), w.mr(r, 0.16, 0.12))
    col = w.mix(col, L(G["white"]), w.m("MULTIPLY", w.mr(w.m("ABSOLUTE", w.m("SUBTRACT", r, 0.21)), 0.025, 0.0), 0.85))
    w.paint_out(col, ring, 0.15, 0.01)
    return mat


# ---------------------------------------------------------------------------------------------
# cloth
# ---------------------------------------------------------------------------------------------
def fabric(name="W_Trim", color="#2C2824", motif=G["gold"]):
    """Banner trim: ink-dark silk with a mud-gold cloud-scroll line motif (MetreUV)."""
    mat, w = _mat(name)
    if w is None:
        return mat
    uv = w.uv()
    s = w.sep(uv)
    sc = w.m("SINE", w.m("ADD", w.m("MULTIPLY", s["X"], 5.0), w.m("MULTIPLY", w.m("SINE", w.m("MULTIPLY", s["Y"], 5.0)), 1.6)))
    col = w.wash(L(color), 0.05, 0.6, 0.02)
    col = w.mix(col, L(motif), w.m("MULTIPLY", w.mr(sc, 0.86, 0.94), 0.75))
    w.paint_out(col)
    return mat


# ---------------------------------------------------------------------------------------------
# ground plates
# ---------------------------------------------------------------------------------------------
def ground(name, mask_path, size_m, earth="#CDB58C", pave="#C3BBA8", grass=G["malachite_l"],
           water=G["azurite_l"]):
    """City ground from the layout mask (R paved, G garden, B canal / wet): bare-silk ochre earth,
    pale flagstones with faint ruled joints, light-malachite gardens laid as soft washes,
    azurite-light water.  No ruts, puddles or stains."""
    mat, w = _mat(name)
    if w is None:
        return mat
    nb = w.nb
    img = bpy.data.images.load(mask_path, check_existing=True)
    img.colorspace_settings.name = "Non-Color"
    t = nb.node("ShaderNodeTexImage", image=img, interpolation="Cubic", extension="EXTEND")
    gu = nb.node("ShaderNodeUVMap")
    gu.uv_map = "GroundUV"
    nb.link(gu.outputs["UV"], t.inputs["Vector"])
    ms = w.sep(t.outputs["Color"])
    paved, green, wet = ms["X"], ms["Y"], ms["Z"]
    o = w.obj()
    col_e = w.wash(L(earth), 0.06, 0.06, 0.03)
    dh, dv, ids = w.grid(o, 1.6, 1.2)
    col_p = w.mul(L(pave), w.tone(ids, 0.04))
    col_p = w.ink(col_p, w.m("MAXIMUM", w.line(dh, 0.03), w.line(dv, 0.03)), G["pave_line"], 0.3)
    gn = w.noise(w.scale(o, 0.12), 1.0, 2)
    col_g = w.mix(L(grass), L("#6FAE8C"), w.mr(gn, 0.3, 0.7))
    col_g = w.wash(col_g, 0.04, 0.3, 0.03)
    edge_n = w.noise(w.scale(o, 0.5), 1.0, 2)
    gmask = w.mr(w.m("ADD", green, w.m("MULTIPLY", w.m("SUBTRACT", edge_n, 0.5), 0.4)), 0.3, 0.7)
    pmask = w.mr(paved, 0.4, 0.6)
    col = w.mix(col_e, col_p, pmask)
    col = w.mix(col, col_g, gmask)
    col = w.mix(col, w.mix(L(water), L(G["azurite"]), w.mr(wet, 0.9, 1.0, 0.0, 0.35)), w.mr(wet, 0.55, 0.9))
    w.paint_out(col)
    return mat


def water(name="Water", color="#6F96B8"):
    """Canal water (factor-only material; Unreal's M_IronWater handles the open sea)."""
    from . import world_bake as WB
    return WB.pbr_material(name, color=L(color)[:3], roughness=0.6)


# ---------------------------------------------------------------------------------------------
# library
# ---------------------------------------------------------------------------------------------
def library():
    """Every architecture material in the gongbi palette, under the world_mats slot names."""
    m = {}
    for fn, args, kw in (
            (stone, ("W_Stone",), {}),
            (stone, ("W_StoneDark", G["stone_dk"], "#55524C"), {}),
            (brick, ("W_Brick",), {}),
            (brick, ("W_BrickWarm", G["brick_w"], "#DDD3BF"), {}),
            (paving, ("W_Paving",), {}),
            (rammed_earth, ("W_Earth",), {}),
            (plaster, ("W_Plaster",), {}),
            (plaster, ("W_PlasterWarm", G["plaster_w"]), {}),
            (red_wall, ("W_RedWall",), {}),
            (marble, ("W_Marble",), {}),
            (lacquer, ("W_Lacquer",), {}),
            (lacquer, ("W_LacquerDark", G["lacquer_dk"]), {}),
            (wood, ("W_Wood",), {}),
            (wood, ("W_WoodDark", G["wood_dk"], "#2E1E14"), {}),
            (beam_paint, ("W_BeamPaint",), {}),
            (bracket, ("W_Bracket",), {}),
            (lattice, ("W_Lattice",), {}),
            (gate_door, ("W_GateDoor",), {}),
            (flat, ("W_Gold", G["gold"]), {}),
            (flat, ("W_Iron", G["iron"]), {}),
            (flat, ("W_Dark", G["dark"], 0.02), {}),
            (roof_tile, ("W_Tile",), {}),
            (roof_tile, ("W_TileDark", G["tile_dk"], G["tile_dk_line"]), {}),
            (roof_tile, ("W_TileGold", G["tile_gold"], G["tile_gold_line"]), dict(alpha=0.4, light="#E2BE62")),
            (roof_tile, ("W_TileGreen", G["tile_green"], G["tile_green_line"]), dict(alpha=0.42, light="#5FA585")),
            (flat, ("W_Ridge", G["ridge"]), {}),
            (flat, ("W_RidgeGold", G["ridge_gold"]), {}),
            (flat, ("W_RidgeGreen", G["ridge_green"]), {}),
            (fascia, ("W_Fascia",), {}),
            (flat, ("W_Gable", "#A83A2C"), {}),
            (rock, ("W_Rock",), {}),
            (fabric, ("W_Trim",), {}),
            (flat, ("W_Tassel", G["cinnabar"]), {}),
    ):
        mat = fn(*args, **kw)
        m[mat.name] = mat
    return m


def relibrary(objs, size, verbose=True):
    """After the atlas unwrap: measure the texel density, then rebuild every library material
    for it (painted line widths are node constants) and swap them into the slots of ``objs``.
    Use as ``world_bake.atlas_bake(..., on_unwrapped=lambda p: world_gongbi.relibrary(p, size))``."""
    d = atlas_density(objs, size)
    set_density(d)
    names = set()
    for o in objs:
        for m in o.data.materials:
            if m is not None:
                names.add(m.name)
    old = {}
    for nm in list(names):
        m = bpy.data.materials.get(nm)
        if m is not None and nm.startswith("W_"):
            m.name = nm + "__pre"
            old[nm] = m
    lib = library()
    for o in objs:
        me = o.data
        for i, m in enumerate(me.materials):
            if m is not None and m.name.endswith("__pre") and m.name[:-5] in lib:
                me.materials[i] = lib[m.name[:-5]]
    for m in old.values():
        if m.users == 0:
            bpy.data.materials.remove(m)
    if verbose:
        print("[ironart] gongbi materials rebuilt for %.1f px/m" % d)
    return d


# ---------------------------------------------------------------------------------------------
# foliage: gongbi leaf atlases
# ---------------------------------------------------------------------------------------------
LEAF = {
    # (base, mid, tip) wash colours, outline ink, twig, outline alpha
    "broad": dict(cols=("#2A5C44", "#3D8062", "#88B490"), alt=("#285A72", "#3A7690", "#7FA6C8"), alt_frac=0.12,
                  line="#1C3328", twig="#3A2A20", line_alpha=0.9),
    "pine": dict(cols=("#16302A", "#1F4436", "#33604C"), pad=("#4F9A7A", "#9CC9AE"), line="#1C3328",
                 twig="#3A2A20", line_alpha=0.0),
    "bamboo": dict(cols=("#2C6248", "#468866", "#9CC4A2"), alt=("#2E6070", "#4A8098", "#8EB2CC"), alt_frac=0.1,
                   line="#1C3328", twig="#56704A", line_alpha=0.85),
}


def _emit_material(name, kind, which):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nb = NB(m.node_tree)
    for n in list(nb.nodes):
        if n.bl_idname != "ShaderNodeOutputMaterial":
            nb.nodes.remove(n)
    w = W(nb)
    em = nb.node("ShaderNodeEmission", inputs={"Strength": 1.0})
    geo_ = nb.node("ShaderNodeNewGeometry")
    spec = LEAF[kind]
    if which == "albedo":
        tone = nb.attr("tone").outputs["Fac"]
        along = nb.attr("along").outputs["Fac"]
        c = spec["cols"]
        # 晕染: dark at the leaf base, clear towards the tip; per-leaf shift of the whole ramp
        t = w.m("ADD", w.m("POWER", along, 0.8), w.m("MULTIPLY", w.m("SUBTRACT", tone, 0.5), 0.35))
        col = w.ramp(t, [(0.0, c[0]), (0.5, c[1]), (1.0, c[2])])
        if "alt" in spec:
            a = spec["alt"]
            col2 = w.ramp(t, [(0.0, a[0]), (0.5, a[1]), (1.0, a[2])])
            col = w.mix(col, col2, w.mr(tone, 1.0 - spec["alt_frac"] - 0.01, 1.0 - spec["alt_frac"]))
        nb.link(col, em.inputs["Color"])
    elif which == "twig":
        nb.set(em.inputs["Color"], L(spec["twig"]))
    elif which == "id":
        tone = nb.attr("tone").outputs["Fac"]
        nb.link(w.gray(w.m("ADD", w.m("MULTIPLY", tone, 0.9), 0.05)), em.inputs["Color"])
    elif which == "idtwig":
        nb.set(em.inputs["Color"], (0.0, 0.0, 0.0, 1.0))
    else:  # normal
        vm = nb.node("ShaderNodeVectorMath", operation="MULTIPLY_ADD")
        flip = nb.node("ShaderNodeMath", operation="MULTIPLY_ADD")
        nb.link(geo_.outputs["Backfacing"], flip.inputs[0])
        flip.inputs[1].default_value = -2.0
        flip.inputs[2].default_value = 1.0
        sgn = nb.node("ShaderNodeVectorMath", operation="SCALE")
        nb.link(geo_.outputs["Normal"], sgn.inputs[0])
        nb.link(flip.outputs[0], sgn.inputs["Scale"])
        nb.link(sgn.outputs[0], vm.inputs[0])
        vm.inputs[1].default_value = (0.5, 0.5, 0.5)
        vm.inputs[2].default_value = (0.5, 0.5, 0.5)
        nb.link(vm.outputs[0], em.inputs["Color"])
    nb.output(em.outputs[0])
    return m


def _shift(a, dy, dx):
    out = np.zeros_like(a)
    H, Wd = a.shape[:2]
    ys0, ys1 = max(0, dy), H + min(0, dy)
    xs0, xs1 = max(0, dx), Wd + min(0, dx)
    out[ys0:ys1, xs0:xs1] = a[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
    return out


def _blur(a, sigma):
    from .post import gaussian
    return gaussian(a, sigma)


def leaf_atlas(kind, out_dir, size=1024, ss=3, seed=7, samples=6):
    """Gongbi leaf atlas for ``kind`` ('broad', 'pine', 'bamboo') from the world_trees leaf
    cells (2x2 cells, same layout as world_trees.leaf_atlas).  Writes
    ``<Kind>_Leaves_{Base,Normal,ORM}.png``; returns {'base', 'normal', 'orm', 'secs'}."""
    import time as _t
    from PIL import Image
    from . import post, world_trees as WT
    t0 = _t.time()
    scene.reset(seed)
    rng = random.Random(seed)
    mb = MeshBuilder()
    cells = {"broad": WT._cell_broad, "pine": WT._cell_pine, "bamboo": WT._cell_bamboo}
    for j in range(2):
        for i in range(2):
            cells[kind](mb, rng, -0.5 + i, -0.5 + j)
    obj = mb.build("Leaves_" + kind, {}, auto_smooth_deg=None)
    sc = bpy.context.scene
    scene.setup_cycles(samples=samples, transparent=True, preset="fast", view="Standard", look="None",
                       adaptive_threshold=0.0, filter_width=1.0)
    R = size * ss
    sc.render.resolution_x = sc.render.resolution_y = R
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "OPEN_EXR"
    sc.render.image_settings.color_depth = "32"
    sc.render.image_settings.color_mode = "RGBA"
    sc.use_nodes = False
    cd = bpy.data.cameras.new("LeafCam")
    cd.type = "ORTHO"
    cd.ortho_scale = 2.0
    cam = bpy.data.objects.new("LeafCam", cd)
    sc.collection.objects.link(cam)
    cam.location = (0, 0, 5)
    sc.camera = cam
    wo = bpy.data.worlds.new("LeafWorld")
    sc.world = wo
    wo.use_nodes = True
    wo.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
    slot_names = [m.name for m in obj.data.materials]
    passes = {}
    os.makedirs(out_dir, exist_ok=True)
    mats = {k: _emit_material("GLeaf_%s" % k, kind, k) for k in ("albedo", "twig", "id", "idtwig", "normal")}
    for which in ("albedo", "id", "normal"):
        for i, nm in enumerate(slot_names):
            twig = nm.startswith("Twig")
            if which == "albedo":
                obj.data.materials[i] = mats["twig"] if twig else mats["albedo"]
            elif which == "id":
                obj.data.materials[i] = mats["idtwig"] if twig else mats["id"]
            else:
                obj.data.materials[i] = mats["normal"]
        sc.cycles.samples = 1 if which == "id" else samples
        sc.cycles.filter_width = 0.01 if which == "id" else 1.0
        p = os.path.join(out_dir, "_gleaf_%s_%s.exr" % (kind, which))
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(p)
        a = np.empty(img.size[0] * img.size[1] * 4, np.float32)
        img.pixels.foreach_get(a)
        passes[which] = a.reshape(img.size[1], img.size[0], 4)[::-1].copy()
        bpy.data.images.remove(img)
        os.remove(p)
    spec = LEAF[kind]
    alb = passes["albedo"]
    alpha = alb[..., 3]
    col = alb[..., :3] / np.maximum(alpha, 1e-4)[..., None]          # straight linear colour
    ids = passes["id"][..., 0]
    inside = passes["id"][..., 3] > 0.5
    lw = 0.9 * ss                                                     # outline width, render px
    if spec["line_alpha"] > 0:
        # 双勾 outlines: leaf boundaries (ID changes) and the outer contour, drawn inside the leaf
        edge = np.zeros(alpha.shape, bool)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nid = _shift(ids, dy, dx)
            nin = _shift(inside.astype(np.float32), dy, dx) > 0.5
            edge |= inside & ((~nin) | (np.abs(nid - ids) > 0.004))
        e = _blur(edge.astype(np.float32), lw * 0.45)
        lines = np.clip(e * 2.2, 0, 1) * inside
        ink = np.array([((int(spec["line"][k:k + 2], 16) / 255.0)) for k in (1, 3, 5)], np.float32)
        ink = np.where(ink <= 0.04045, ink / 12.92, ((ink + 0.055) / 1.055) ** 2.4)
        col = col * (1 - lines[..., None] * spec["line_alpha"]) + ink * lines[..., None] * spec["line_alpha"]
    if kind == "pine":
        # malachite wash pad under the needle strokes: a soft blob around each tuft
        pad = _blur((alpha > 0.3).astype(np.float32), 5.0 * ss)
        pad = np.clip((pad - 0.12) / 0.25, 0, 1)
        core = np.clip((_blur((alpha > 0.3).astype(np.float32), 9.0 * ss) - 0.2) / 0.4, 0, 1)
        pc = [np.array([int(h[k:k + 2], 16) / 255.0 for k in (1, 3, 5)], np.float32) for h in spec["pad"]]
        pc = [np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4) for c in pc]
        padcol = pc[1] * (1 - core[..., None]) + pc[0] * core[..., None]
        a_needle = np.clip(alpha, 0, 1)
        col = col * a_needle[..., None] + padcol * (1 - a_needle[..., None])
        alpha = np.maximum(alpha, pad * 0.98)
    nrm = passes["normal"][..., :3] / np.maximum(passes["normal"][..., 3], 1e-4)[..., None]

    def down(x):
        h, w_ = x.shape[:2]
        return x.reshape(h // ss, ss, w_ // ss, ss, *x.shape[2:]).mean(axis=(1, 3))
    a_s = down(alpha)
    col_s = down(col * alpha[..., None]) / np.maximum(a_s, 1e-4)[..., None]
    a_n = down(passes["normal"][..., 3])
    n_s = down(nrm * passes["normal"][..., 3:4]) / np.maximum(a_n, 1e-4)[..., None]
    n_v = n_s * 2 - 1
    n_v[..., :2] *= 0.5                                                # subtle: a painted leaf
    n_v /= np.maximum(np.linalg.norm(n_v, axis=-1, keepdims=True), 1e-4)
    n_v[a_n < 0.02] = (0, 0, 1)
    a_out = np.clip(a_s * 1.12, 0, 1)
    srgb = np.where(col_s <= 0.0031308, col_s * 12.92, 1.055 * np.power(np.maximum(col_s, 0.0031308), 1 / 2.4) - 0.055)
    rgba = np.dstack([np.clip(srgb, 0, 1), a_out]).astype(np.float32)
    rgba = post.alpha_cleanup(rgba, lo=0.02, hi=0.98, bleed=24)
    mean = rgba[..., :3][rgba[..., 3] > 0.5].mean(0)
    far = (rgba[..., 3] <= 0.0) & (rgba[..., :3].sum(-1) <= 0.0)
    rgba[far, :3] = mean
    nrm8 = np.clip(n_v * 0.5 + 0.5, 0, 1)
    orm = np.dstack([np.ones_like(a_s), np.full_like(a_s, ROUGH), np.zeros_like(a_s)])
    out = {}
    for key, arr, mode in (("base", rgba, "RGBA"), ("normal", nrm8, "RGB"), ("orm", orm, "RGB")):
        p = os.path.join(out_dir, "%s_Leaves_%s.png" % (kind.capitalize(), key.capitalize() if key != "orm" else "ORM"))
        Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8), mode).save(p, optimize=True)
        out[key] = p
    out["secs"] = _t.time() - t0
    print("[ironart] gongbi leaf atlas %s %dpx in %.1fs" % (kind, size, out["secs"]))
    return out


# ---------------------------------------------------------------------------------------------
# bark: periodic painted tiles
# ---------------------------------------------------------------------------------------------
def bark_material(kind, ext=(1.6, 3.2)):
    """Seamless painted bark (UV0 0..1 = one tile of ``ext`` metres, 4D torus noise)."""
    from .world_trees import _torus, _noise4, _vor4
    name = "GTrunkSrc_" + kind
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nb = NB(m.node_tree)
    for n in list(nb.nodes):
        if n.bl_idname != "ShaderNodeOutputMaterial":
            nb.nodes.remove(n)
    w = GW(nb)
    uvn = nb.node("ShaderNodeUVMap")
    uvn.uv_map = "UV0"
    uv = uvn.outputs["UV"]
    vec, wv = _torus(w, uv, *ext)
    if kind == "bamboo":
        s = w.sep(uv)
        fv = w.m("FRACT", w.m("MULTIPLY", s["Y"], 4.0))
        node_ring = w.mr(w.m("ABSOLUTE", w.m("SUBTRACT", fv, 0.03)), 0.012, 0.03, 1.0, 0.0)
        under = w.mr(fv, 0.03, 0.2, 1.0, 0.0)
        streak = _noise4(w, vec, wv, 3.0, 2, 0.5, aniso=(9.0, 9.0, 0.4))
        col = w.mix(L("#4E9A78"), L("#78B092"), w.mr(streak, 0.3, 0.7))
        col = w.mix(col, L("#A9CDB4"), w.m("MULTIPLY", under, 0.5))
        col = w.mix(col, L("#24503E"), node_ring)
        w.out(col, ROUGH, 0.0, w.bump(node_ring, 0.25, 0.01), spec=0.3)
        return m
    if kind == "pine":
        # 鳞皴: plates outlined in ink over an ochre-umber wash
        plates = _vor4(w, vec, wv, 2.6, aniso=(1.0, 1.0, 0.45))
        cell = _vor4(w, vec, wv, 2.6, feature="F1", aniso=(1.0, 1.0, 0.45), out="Color")
        tone = w.sep(cell)["X"]
        col = w.mix(L("#6E4A32"), L("#8C6040"), w.mr(tone, 0.2, 0.8))
        rim = w.mr(plates, 0.0, 0.07, 1.0, 0.0)
        inner = w.mr(plates, 0.07, 0.2, 1.0, 0.0)
        col = w.mix(col, L("#4A3222"), w.m("MULTIPLY", inner, 0.35))
        col = w.mix(col, L("#22180F"), w.m("MULTIPLY", rim, 0.9))
        w.out(col, ROUGH, 0.0, w.bump(w.m("SUBTRACT", 1.0, rim), 0.3, 0.02), spec=0.3)
        return m
    # broadleaf: ink-grey trunk with long furrow strokes
    fur = _noise4(w, vec, wv, 2.6, 4, 0.6, aniso=(5.0, 5.0, 0.6))
    ridge = w.m("ABSOLUTE", w.m("SUBTRACT", fur, 0.5))
    furrow = w.mr(ridge, 0.0, 0.05, 1.0, 0.0)
    col = w.mix(L("#4C433C"), L("#6A5C50"), w.mr(fur, 0.3, 0.7))
    col = w.mix(col, L("#1E1813"), w.m("MULTIPLY", furrow, 0.85))
    w.out(col, ROUGH, 0.0, w.bump(w.m("SUBTRACT", 1.0, furrow), 0.3, 0.02), spec=0.3)
    return m


def bark_texture(kind, out_dir, size=(512, 1024), ext=(1.6, 3.2)):
    """Bake a seamless painted bark tile to ``<Kind>_Bark_{Base,ORM,Normal}.png``."""
    from . import world_bake as WB
    scene.reset(5)
    me = bpy.data.meshes.new("BarkPlane")
    me.from_pydata([(0, 0, 0), (ext[0], 0, 0), (ext[0], ext[1], 0), (0, ext[1], 0)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UV0")
    uv.data.foreach_set("uv", [0, 0, 1, 0, 1, 1, 0, 1])
    o = bpy.data.objects.new("BarkPlane", me)
    bpy.context.scene.collection.objects.link(o)
    me.materials.append(bark_material(kind, ext))
    scene.setup_cycles(samples=4, transparent=False, preset="fast")
    return WB.bake([o], size[0], out_dir, "%s_Bark" % kind.capitalize(), ao=False, samples=4,
                   margin=0, cavity=0.0, height=size[1], const={"metal": 0.0, "rough": ROUGH})
