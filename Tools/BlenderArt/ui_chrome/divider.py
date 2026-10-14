"""Divider.png (512x16, transparent; the UI stretches it to the widget width at 8-16 px high):
gold filigree with a central ruyi knot.

    knot     two ruyi heads back to back (lobes outwards, 13 px tall) clasping a domed cinnabar
             cabochon in a gold bezel, x 256 +- 14
    scrolls  a cloud curl above and below the wires on each side of the knot
    wires    twin twisted gold wires (r 0.55 px, 2.9 px apart) that converge into one and taper
             to a point at x = 256 +- 246 (the ends fade so any stretch stays graceful)
The filigree floats 1 mm above a shadow catcher, so it carries its own soft cast shadow
(bottom-right) onto whatever the UI draws it on - legible on paper and on dark lacquer.
"""

import numpy as np

import kit
from ironart import ui_chrome_motifs as MO
from ironart import ui_chrome_sdf as S
from ironart.ui_chrome_maps import Maps, L

NAME = "Divider"
SPEC = dict(shader_alpha=True, size=(512, 16), ss=4, spp=48, seed=51)
W, H = 512, 16
CX, CY = 256.0, 8.0
LIFT = 1.0
KY = CY - 0.3            # knot centre (a hair high: its shadow falls down-right)


def build(G, variant=None):
    m = Maps(G.shape, base="#000000", alpha=0.0)
    X, Y = G.X, G.Y
    ax = np.abs(X - CX)
    # ---- wires: separation shrinks from 2.9 px to 0 between x+-60 and x+-200 -----------------
    sep = 1.45 * (1 - kit.smoothstep(60.0, 205.0, ax))
    rad = 0.58 * (1 - kit.smoothstep(150.0, 246.0, ax)) + 0.0
    rad = np.maximum(rad, 0.0)
    dw = np.minimum(np.abs(Y - (CY - sep)), np.abs(Y - (CY + sep))) - rad
    dw = np.where(ax < 14.5, 9.0, dw)
    dw = np.where(ax > 246.0, 9.0, dw)
    wire = S.aa_mask(dw, G)
    # twisted-wire profile: round section + diagonal cuts (period 1.1 px)
    zr = np.sqrt(np.clip(1 - ((np.clip(dw + rad, -9, 9)) / np.maximum(rad, 1e-3)) ** 2, 0, 1)) * rad
    ph = (X + (Y - CY) * 0.9) / 1.1
    cut = np.abs((ph - np.floor(ph)) - 0.5) * 2.0
    zw = zr * (0.78 + 0.22 * kit.smoothstep(0.0, 0.5, cut))

    # ---- knot: ruyi heads back to back + bezel + cabochon -------------------------------------
    F = kit.Folded(X, Y)
    rl, rl_e = MO.ruyi(F, CX - 7.2, KY, 8.0, rot=-90.0)    # point towards +x (the centre)
    rr, rr_e = MO.ruyi(F, CX + 7.2, KY, 8.0, rot=90.0)
    knot = np.minimum(rl, rr)
    eng = np.minimum(np.where(rl < -0.25, rl_e, 9.0), np.where(rr < -0.25, rr_e, 9.0))
    bez = np.hypot(X - CX, Y - KY) - 3.5
    gem = np.hypot(X - CX, Y - KY) - 2.4
    knot = S.smooth_union(knot, bez, 0.6)
    zk = MO.dome(knot, 1.2, 0.75) + S.groove(eng, 0.3, 0.2) * (knot < -0.3)

    # ---- cloud curls beside the knot (above and below, both sides) ----------------------------
    curls = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            p0 = (CX + sx * 15.0, CY + sy * 1.5)
            stem = S.bezier(p0, (CX + sx * 19.0, CY + sy * 1.6), (CX + sx * 24.0, CY + sy * 3.6),
                            (CX + sx * 27.5, CY + sy * 4.6), n=26)
            cc = S.spiral(CX + sx * 27.6, CY + sy * 2.6, 2.0, 0.35, 1.0,
                          90.0 if sy > 0 else -90.0, cw=(sx * sy < 0), n=48)
            path = np.concatenate([stem, cc[1:]], 0)
            curls.append((path, S.taper(len(path), 0.62, 0.22, power=0.9)))
    sc = MO.strokes_sd(G, curls, pad=2.0)
    zc = MO.dome(sc, 0.5, 0.45)

    shape = np.minimum(np.minimum(dw, knot), sc)
    a = S.aa_mask(shape, G)
    z = np.maximum(np.maximum(zw * wire, zk), zc) + LIFT
    gemm = S.aa_mask(gem, G)
    z = z + MO.dome(gem, 1.6, 0.6) * gemm
    m.paint(a, "gold")
    m.tint(a, kit.recess_shade(z, G.ss, radius=0.8, k=1.4, floor=0.6))
    m.paint(wire, rough=0.2 + 0.1 * (1 - cut))
    m.paint(gemm, dict(base=L("#8E1A12"), metal=0.0, rough=0.12, coat=1.0, spec=0.5))
    # ends fade: the last 40 px of each wire become translucent
    fade = 1.0 - kit.smoothstep(206.0, 246.0, ax)
    m.alpha = (a * np.maximum(fade, 1.0 - wire * (1 - fade))).astype(np.float32)
    m.height = z.astype(np.float32)
    return m


def extras(variant, G):
    """Shadow catcher under the floating filigree."""
    import bpy
    from ironart.ui_chrome_render import MM
    me = bpy.data.meshes.new("Catcher")
    hw, hh = (W / 2) * MM, (H / 2) * MM
    me.from_pydata([(-hw, -hh, 0.0), (hw, -hh, 0.0), (hw, hh, 0.0), (-hw, hh, 0.0)], [],
                   [(0, 1, 2, 3)])
    ob = bpy.data.objects.new("Catcher", me)
    bpy.context.scene.collection.objects.link(ob)
    ob.is_shadow_catcher = True
    return ob
