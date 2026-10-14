"""Button*.png (192x64 9-slice, margins 20 h / 16 v): carved red cinnabar lacquer plaques with
a bevelled gold edge.  Variants: normal, hover, pressed, disabled.

Cross-section (d from the outer edge, px = mm, outer radius 4):
    0-1.2    dark lacquer lip
    1.25-4.2 bevelled gold frame (chamfer / flat / chamfer)
    4.2-5.3  carved groove (cinnabar dark)
    5.3-7.1  carved cinnabar bead, 7.1-8.2 cove
    field    cinnabar plaque, cylindrical across the height (1.5 mm crown: the clear coat catches the
             overhead strip light as a soft horizontal highlight band), vertical-only colour gradient - stretch-safe
Carved corners: a small gilded xiangyun cloud carved in relief in each field corner (inside
20 x 16).

States: hover = brighter, warmer lacquer with a warm inner glow and brighter, glossier gold;
pressed = the plaque sinks 0.7 mm below the frame (the frame's own shadow falls inside) in
LacquerDark with satin gold; disabled = matte grey-brown lacquer, dull bronze trim.
"""

import numpy as np

import kit
from ironart import ui_chrome_sdf as S
from ironart.ui_chrome_maps import Maps, L

NAME = "Button"
SPEC = dict(size=(192, 64), ss=4, spp=64, margins=(20, 16, 20, 16), seed=21)
W, H = 192, 64
MX, MY = 20, 16
VARIANTS = ("normal", "hover", "pressed", "disabled")
FILE = {"normal": "Button", "hover": "Button_Hover", "pressed": "Button_Pressed",
        "disabled": "Button_Disabled"}

#: per-state looks (albedos linear via L(); calibrated so the centre row lands on the token)
LOOK = {
    "normal": dict(field="#7E1F17", field_k=1.0, glow=0.0, gold="gold", gold_rough=0.24,
                   sink=0.0, lip="#2A0B07", groove="#3A0E09", rough=0.42, coat=1.0, sat=1.0),
    "hover": dict(field="#93281C", field_k=1.0, glow=1.0, gold="gold", gold_rough=0.17,
                  gold_base="#FFD98C", sink=0.0, lip="#341009", groove="#47120B", rough=0.38,
                  coat=1.0, sat=1.0),
    "pressed": dict(field="#4A120D", field_k=1.0, glow=0.0, gold="gold_satin", gold_rough=0.34,
                    gold_base="#D9AE62", sink=0.75, lip="#1E0805", groove="#2A0906", rough=0.46,
                    coat=1.0, sat=1.0),
    "disabled": dict(field="#594A42", field_k=1.0, glow=0.0, gold="bronze_dull", gold_rough=0.6,
                     sink=0.0, lip="#2B2420", groove="#3A302A", rough=0.75, coat=0.12, sat=0.0),
}


def corner_clouds(ss, top=True):
    """Carved cloud of one left corner (top or bottom) on a local 20 x 16 grid."""
    cy = 11.7 if top else 16 - 11.7
    return kit.carved_cloud(ss, 7.4, MX, MY, 13.0, cy, rot=0.0, mirror=not top, height=0.42,
                            lobes=[(-0.40, -0.02, 0.33, 1), (0.08, -0.24, 0.27, -1),
                                   (0.44, -0.04, 0.22, 1)], tail=False)


def build(G, variant="normal"):
    variant = variant or "normal"
    lk = LOOK[variant]
    d = S.inset_distance(G, W, H, r=4.0)
    m = Maps(G.shape, base=lk["field"])
    sink = lk["sink"]
    zf = 0.85 - sink
    pts = [(-1, 0.0), (0.0, 0.25), (0.4, 0.85), (1.1, 1.2), (1.3, 1.28), (2.1, 1.95),
           (3.3, 1.95), (4.2, 1.35), (4.5, 1.0), (5.0, 0.92)]
    pts += kit.bead(6.2, 0.9, 0.95)
    pts += [(7.35, 0.98), (8.2, zf + 0.02), (8.6, zf), (60, zf)]
    z = S.Profile(pts, round_px=0.12)(d)

    lip = S.band(d, -5, 1.25, G)
    gold = S.band(d, 1.25, 4.25, G)
    groove = S.band(d, 4.25, 5.3, G)
    beadm = S.band(d, 5.3, 7.15, G)
    field = S.band(d, 7.15, 999, G)

    # field: cylindrical across the height (zero at the cove, +0.5 mm in the middle)
    yy = np.clip(np.abs(G.Y - H / 2) / (H / 2 - 8.0), 0, 1)
    dome = (1.5 * (1 - yy ** 2)) * kit.smoothstep(8.0, 12.0, d) * (1 - 0.6 * (sink > 0))
    z = z + dome * field

    def lac(col, k=1.0):
        return dict(base=L(col, k), metal=0.0, rough=lk["rough"], coat=lk["coat"], spec=0.06)

    m.paint(lip, lac(lk["lip"]))
    gl = dict(kit_gold(lk))
    m.paint(gold, gl)
    m.paint(groove, lac(lk["groove"]))
    m.paint(beadm, lac(lk["field"], 0.92))
    m.paint(field, lac(lk["field"]))
    # vertical-only gradient (top lighter): stretch-safe glow of lacquer
    m.tint(field + beadm, kit.vgrad(G, H, 0.10))

    # carved corner clouds (inside the 20 x 16 corners)
    for top in (True, False):
        cz, cm, cg = corner_clouds(G.ss, top)
        full = np.zeros(G.shape, np.float32)
        fm = np.zeros(G.shape, np.float32)
        fg = np.zeros(G.shape, np.float32)
        ys = slice(0, MY) if top else slice(H - MY, H)
        for arr, dst in ((cz, full), (cm, fm), (cg, fg)):
            sl = (slice(ys.start * G.ss, ys.stop * G.ss), slice(0, MX * G.ss))
            sr = (sl[0], slice(G.shape[1] - MX * G.ss, G.shape[1]))
            dst[sl] = np.maximum(dst[sl], arr)
            dst[sr] = np.maximum(dst[sr], arr[:, ::-1])
        z = z + full * field
        # gilded carving: the cloud's surface is gold leaf, its engraved curls stay dark lacquer
        m.paint(fm * field, kit_gold(lk))
        m.tint(fm * field, kit.recess_shade(full, G.ss, radius=0.8, k=1.6, floor=0.6))
        m.paint(fg * fm * field, lac(lk["groove"]))

    if lk["glow"] > 0:
        # warm inner glow: strongest in the plaque, fading to nothing under the gold frame
        gw = kit.smoothstep(6.0, 20.0, d) * lk["glow"]
        m.emit = m.emit + (np.array([0.075, 0.020, 0.006], np.float32) * gw[..., None])
    if lk["sat"] < 1.0:
        lum = (m.base * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1, keepdims=True)
        m.base = lum + (m.base - lum) * lk["sat"]
        m.base = m.base * np.array([1.04, 1.0, 0.95], np.float32)
    m.height = z.astype(np.float32)
    m.alpha = S.aa_mask(-d, G)
    return m


def kit_gold(lk):
    from ironart.ui_chrome_maps import MATS
    g = dict(MATS[lk["gold"]])
    g["rough"] = lk["gold_rough"]
    if "gold_base" in lk:
        g["base"] = L(lk["gold_base"])
    return g
