"""Identity = everything that makes one officer's face and body (no bpy).

An :class:`Identity` holds the MakeHuman macro values (gender, age, muscle, weight, race mix),
named face sliders (see ``mh.SLIDERS``), expression units (``mh.EXPRESSIONS``) and skin / eye /
hair colour parameters.  :func:`variant` derives a believable random individual from an archetype
seed, so 103 portraits come from a handful of archetype presets plus per-officer seeds.
"""

import copy
import random
from dataclasses import dataclass, field


@dataclass
class Identity:
    gender: float = 1.0               # 0 female .. 1 male
    age: float = 35.0                 # years
    muscle: float = 0.55
    weight: float = 0.5
    race: dict = field(default_factory=lambda: {"asian": 1.0})
    sliders: dict = field(default_factory=dict)
    expression: dict = field(default_factory=dict)
    arm_drop_deg: float = 34.0
    shoulder_width: float = 1.0
    neck_scale: float = 1.0
    # skin
    skin_tone: float = 0.5            # 0 pale ivory .. 1 deep tan
    skin_ruddy: float = 0.4           # redness of cheeks / nose / ears
    weathered: float = 0.3            # sun/wind: darker, redder, rougher (soldiers)
    wrinkles: float = 0.0             # 0..1 (age-driven by default)
    frown: float = 0.0                # glabella creases + brow knot (stern / scheming)
    smile: float = 0.0                # deeper nasolabial folds (jovial)
    gaunt: float = 0.0                # hollow cheeks (ascetic, old)
    beard_shadow: float = 0.0         # blue-grey stubble tint (shaved men)
    makeup: float = 0.0               # heroines: rouge, lip colour, lid shadow
    lip_color: str = "#A4524A"
    eye_color: str = "#2B1A10"
    # hair colour as Principled Hair melanin params
    hair_melanin: float = 0.95
    hair_redness: float = 0.15
    grey: float = 0.0                 # fraction of grey/white strands
    # painted hair-root masses in the skin (painters block the mass in before the strands)
    brow_paint: float = 0.75
    brow_mask: str = "brow"           # 'brow' or 'brow_f' (thin willow-leaf brows)
    brow_thick: float = 1.0
    brow_angle: float = 0.0           # + raises the tails (fierce), - drops them (sage / worried)
    scalp_paint: float = 0.0
    scalp_mask: str = "scalp"         # 'scalp' (men) or 'scalp_low' (women / youths)
    beard_paint: float = 0.0


def wrinkle_default(age):
    return max(0.0, min(1.0, (age - 32.0) / 38.0))


ARCH = {
    # face slider presets per archetype (values -1..1); variant() jitters around them
    "warlord": dict(head_square=0.45, jaw_drop=0.0, chin_width=0.35, chin_prominent=0.25,
                    cheek_bones=0.35, brow_ridge=0.45, brow_angle=-0.35, nose_width=0.2,
                    nose_hump=0.25, nose_length=0.15, mouth_width=0.15, lip_upper_vol=-0.3,
                    lip_lower_vol=-0.1, eye_fold_angle=0.2, neck_width=0.4, eye_height2=-0.25,
                    temples=-0.2, head_fat=-0.2),
    "scholar_f": dict(head_oval=0.5, chin_width=-0.35, chin_prominent=0.05, cheek_bones=0.1,
                      cheek_volume=-0.25, nose_width=-0.35, nose_point_width=-0.3, nose_length=-0.1,
                      mouth_width=-0.25, lip_upper_vol=0.2, lip_lower_vol=0.35, cupid=0.4,
                      eye_fold_angle=0.45, eye_scale=0.15, eye_corner_out=0.3, brow_angle=0.1,
                      neck_width=-0.35, neck_height=0.25, jaw_drop=-0.2, head_fat=-0.3,
                      eye_height2=0.15),
    "sage": dict(head_oval=0.35, head_rect=0.2, cheek_bones=0.45, cheek_volume=-0.55,
                 temples=-0.6, nose_length=0.35, nose_hump=0.35, nose_width=0.05, eye_bag=0.55,
                 eye_fold_angle=-0.35, brow_ridge=0.3, mouth_corners=-0.3, lip_upper_vol=-0.55,
                 lip_lower_vol=-0.35, chin_prominent=0.15, neck_double=-0.3, ear_scale=0.4,
                 ear_lobe=0.6, head_fat=-0.45, laugh_lines=0.5),
}


def variant(base, seed, amount=0.25, keys=None):
    """Copy of ``base`` with face sliders jittered (gaussian, clamped to [-1, 1])."""
    rng = random.Random(seed)
    out = copy.deepcopy(base)
    keys = keys or ["head_square", "head_oval", "chin_width", "chin_prominent", "cheek_bones",
                    "nose_width", "nose_hump", "nose_length", "nose_tip", "mouth_width",
                    "lip_upper_vol", "lip_lower_vol", "eye_fold_angle", "eye_scale", "brow_ridge",
                    "brow_angle", "jaw_drop", "ear_scale", "eye_spacing", "forehead_height"]
    for k in keys:
        v = out.sliders.get(k, 0.0) + rng.gauss(0, amount)
        out.sliders[k] = max(-1.0, min(1.0, v))
    out.skin_tone = min(1, max(0, out.skin_tone + rng.gauss(0, 0.1)))
    return out
