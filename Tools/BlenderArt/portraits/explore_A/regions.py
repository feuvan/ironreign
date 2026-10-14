"""Face regions as functions of rest face coordinates (numpy; shared by textures and hair).

``fc`` = (x, y, z) in inter-pupil units, origin between the eyeball centres, x toward the
character's left, y up, z forward, measured on the identity *before* expressions so painted
features ride with the skin.  ``F`` is the per-identity :class:`FaceFrame` (landmark heights).
"""

from dataclasses import dataclass

import numpy as np


def sstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


@dataclass
class FaceFrame:
    eye_in: float = 0.30      # inner canthus |x|
    eye_out: float = 0.79     # outer canthus |x|
    lid_top: float = 0.09     # upper lid margin peak y
    lid_bot: float = -0.12
    brow_y: float = 0.36      # brow base at the inner end
    nose_y: float = -0.85     # nostril base
    nose_w: float = 0.2       # alar half width
    mouth_y: float = -1.4     # lip line
    mouth_w: float = 0.37     # corner |x|
    lip_top: float = -1.28
    lip_bot: float = -1.62
    chin_y: float = -2.05     # chin centre
    crown_y: float = 2.2
    back_z: float = -3.5

    @staticmethod
    def from_masks(fc, masks, lash_up, lash_lo):
        f = FaceFrame()
        f.eye_in = float(np.abs(lash_up[:, 0]).min())
        f.eye_out = float(np.abs(lash_up[:, 0]).max())
        f.lid_top = float(lash_up[:, 1].max())
        f.lid_bot = float(lash_lo[:, 1].min())
        lu = masks["m_lip_u"] > 0.5
        ll = masks["m_lip_l"] > 0.5
        f.lip_top = float(fc[lu, 1].max())
        f.lip_bot = float(fc[ll, 1].min())
        f.mouth_y = float(0.5 * (fc[lu, 1].min() + fc[ll, 1].max()))
        f.mouth_w = float(np.abs(fc[lu, 0]).max())
        nm = masks["m_nose"] > 0.5
        f.nose_y = float(fc[nm, 1].min())
        f.nose_w = float(np.abs(fc[nm, 0]).max())
        cm = masks["m_chin"] > 0.5
        f.chin_y = float(fc[cm, 1].mean())
        f.crown_y = float(fc[:, 1].max())
        f.back_z = float(fc[:, 2].min())
        f.brow_y = f.lid_top + 0.27
        return f


# --------------------------------------------------------------------------------- spherical frame
def head_angles(fc, F):
    """Azimuth (deg, 0 = front, +90 = character's left) and elevation (deg) around the cranium
    centre."""
    cz = F.back_z * 0.46
    cy = 0.35
    x, y, z = fc[..., 0], fc[..., 1] - cy, fc[..., 2] - cz
    az = np.degrees(np.arctan2(x, z))
    el = np.degrees(np.arctan2(y, np.sqrt(x * x + z * z)))
    return az, el


def hairline_elev(az, recede=0.0, widow=0.0):
    """Hairline elevation (deg) as a function of azimuth: forehead high, temples notch, sideburns
    low in front of the ears, nape low at the back.  ``recede`` (0..1) lifts the temples/front."""
    a = np.abs(az)
    # knots: (azimuth, elevation)
    ka = np.array([0, 18, 32, 48, 62, 75, 95, 115, 140, 180], np.float32)
    ke = np.array([30, 29, 24, 23, 12, -4, 4, -8, -25, -32], np.float32)
    if recede >= 0:
        ke = ke + recede * np.array([10, 11, 14, 12, 4, 0, 0, 0, 0, 0], np.float32)
    else:
        # lower, rounder hairline (young women): forehead and temples come down
        ke = ke + recede * np.array([22, 22, 20, 16, 8, 2, 0, 0, 0, 0], np.float32)
    e = np.interp(a, ka, ke)
    e = e - widow * 4.0 * np.exp(-(az / 6.0) ** 2)
    return e


def scalp(fc, F, recede=0.0, soft=2.5):
    az, el = head_angles(fc, F)
    return sstep(-soft, soft, el - hairline_elev(az, recede))


# ------------------------------------------------------------------------------------- eyebrows
def brow(fc, F, thick=1.0, arch=1.0, length=1.0, angle=0.0, inner_gap=0.0):
    """Eyebrow density 0..1 (a tapered arched band above each eye)."""
    x, y = np.abs(fc[..., 0]), fc[..., 1]
    x0 = F.eye_in - 0.08 + inner_gap
    x1 = F.eye_out + 0.18 * length
    t = (x - x0) / (x1 - x0)
    base = F.brow_y + 0.02 * thick
    cy = base + arch * 0.10 * np.sin(np.clip(t, 0, 1) * np.pi * 0.9) + angle * 0.12 * (t - 0.3) - 0.06 * np.clip(t - 0.75, 0, 1) * 4
    hw = 0.075 * thick * (1.15 - 0.55 * np.clip(t, 0, 1))
    d = np.abs(y - cy) / hw
    band = 1.0 - sstep(0.6, 1.0, d)
    ends = sstep(-0.04, 0.06, t) * (1.0 - sstep(0.92, 1.02, t))
    front = sstep(-0.6, -0.3, fc[..., 2])
    return band * ends * front, t, cy


# ---------------------------------------------------------------------------------------- beard
def beard(fc, F, style):
    """Facial hair density 0..1 for a style dict:
        mustache (0..1 density), mustache_w (width scale), goatee, chin (chin beard), cheeks,
        jaw (along the jawline), neck, sideburns, soul (patch under the lower lip), fill
    """
    x, y, z = fc[..., 0], fc[..., 1], fc[..., 2]
    ax = np.abs(x)
    out = np.zeros(x.shape, np.float32)
    front = sstep(-1.2, -0.8, z)
    lip_gap_top = F.lip_top + 0.02
    lip_gap_bot = F.lip_bot - 0.03
    # upper lip: from the nostrils to the lip line, out to past the mouth corners
    mw = F.mouth_w * style.get("mustache_w", 1.0)
    must = sstep(F.nose_y - 0.02, F.nose_y - 0.08, y) * sstep(lip_gap_top - 0.04, lip_gap_top + 0.0, y)
    must *= 1.0 - sstep(mw + 0.05, mw + 0.16, ax)
    # philtrum gap
    must *= 1.0 - style.get("philtrum_gap", 0.0) * (1.0 - sstep(0.03, 0.08, ax))
    out = np.maximum(out, must * style.get("mustache", 0.0))
    # mustache tails beside the mouth corners going down
    tail = sstep(mw - 0.08, mw + 0.02, ax) * (1.0 - sstep(mw + 0.08, mw + 0.2, ax))
    tail *= sstep(F.chin_y + 0.05, F.mouth_y, y) * (1.0 - sstep(lip_gap_top - 0.02, lip_gap_top + 0.06, y))
    out = np.maximum(out, tail * style.get("mustache", 0.0) * style.get("tails", 0.6))
    # soul patch & chin
    soul = (1.0 - sstep(0.08, 0.16, ax)) * sstep(lip_gap_bot + 0.02, lip_gap_bot - 0.05, y) * sstep(F.chin_y - 0.05, F.chin_y + 0.15, y)
    out = np.maximum(out, soul * style.get("soul", 0.0))
    chin = (1.0 - sstep(F.mouth_w * 0.9, F.mouth_w * 1.5, ax)) * sstep(lip_gap_bot, lip_gap_bot - 0.12, y)
    chin *= sstep(-1.0, -0.4, z)
    out = np.maximum(out, chin * style.get("chin", 0.0))
    # cheeks & jaw: below the cheekbone line, back to the ear
    cheek_top = F.nose_y + 0.18 + 0.25 * sstep(0.5, 1.1, ax) - style.get("cheek_high", 0.0) * 0.2
    cheek = sstep(cheek_top + 0.06, cheek_top - 0.06, y) * sstep(F.mouth_w + 0.02, F.mouth_w + 0.2, ax)
    cheek *= sstep(-1.9, -1.3, z)
    out = np.maximum(out, cheek * style.get("cheeks", 0.0))
    jaw = sstep(F.mouth_y - 0.1, F.mouth_y - 0.35, y) * sstep(-1.9, -1.3, z)
    out = np.maximum(out, jaw * style.get("jaw", 0.0))
    # sideburns in front of the ears
    sb = sstep(-1.9, -1.55, z) * (1.0 - sstep(-1.0, -0.75, z)) * sstep(0.4, 0.2, y) * sstep(F.mouth_y - 0.2, F.mouth_y + 0.2, y)
    out = np.maximum(out, sb * style.get("sideburns", 0.0))
    # under the jaw / upper neck
    nk = sstep(F.chin_y + 0.1, F.chin_y - 0.25, y) * sstep(-2.0, -1.0, z) * (1.0 - sstep(F.chin_y - 0.6, F.chin_y - 0.95, y))
    out = np.maximum(out, nk * style.get("neck", 0.0))
    # never on the lips
    lips = sstep(lip_gap_top + 0.01, lip_gap_top - 0.03, y) * sstep(lip_gap_bot - 0.01, lip_gap_bot + 0.03, y) * (1.0 - sstep(F.mouth_w - 0.05, F.mouth_w + 0.02, ax))
    out *= 1.0 - lips
    out *= front * sstep(-3.0, -2.6, y)
    return np.clip(out * style.get("fill", 1.0), 0, 1)
