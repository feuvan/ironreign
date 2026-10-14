"""Character specs: the three hero test portraits (archetype generators live in cast.py)."""

from face import FaceSpec
from portrait import Character


def hero_warlord():
    """Yan Tieshan 燕铁山, the Iron Mountain: grizzled northern warlord in his fifties."""
    F = FaceSpec(sex="m", age=55, yaw=21, skin="#d6a68d", shade_k=1.35, rouge_k=0.35,
                 white_k=0.25, line_w=1.1, eye="fierce", eye_h=0.36, eye_tilt=0.05,
                 eye_w=0.128, iris=0.46, gaze=(0.35, 0.0), tail=0.0, crease=0.6,
                 brow="sword", brow_th=0.036, brow_lift=0.040, brow_knit=1.2, brow_grey=0.08,
                 brow_y=0.425, nose_tip=0.10, nose_w=0.064, mouth_w=0.180, lip_up=0.016,
                 lip_lo=0.022, smile=-0.6, lip="#a55a4e", lip_k=0.8, wrinkles=0.75, frown=1.0,
                 shape=dict(jaw=1.10, chin=1.12, width=1.02, cheekbone=1.3), seed=11)
    return Character(
        key="hero_warlord", face=F, seed=11,
        body=dict(shoulder=1.08, neck_r=0.23, yaw_k=0.9, adam=0.0),
        hair=dict(kind="male", grey=0.45, bun=False, ear=False),
        beard=dict(kind="full", length=0.30, grey=0.36, density=1.0, seed=3),
        headgear=dict(kind="helmet", metal="#50627a", trim="gold", plume="cinnabar",
                      rim_front=0.305, wings=False),
        costume=dict(
            cloak=dict(color="carmine", spread=0.22),
            robes=[dict(color="cinnabar", collar="cinnabar_l", cross_y=1.24, neck_u=0.45,
                        cw=0.06, collar_line="ink", pattern="gold_dots")],
            armour=dict(cuirass=dict(color="#50627a", neck_y=1.08, neck_depth=0.14, neck_u=0.60,
                                     rows=13, cols=24),
                        mingguang=dict(u=0.36, y=1.56, r=0.125),
                        pauldron=dict(color="#50627a", rows=4, size=1.0))))


def hero_scholar():
    """Su Wanqing 苏婉清: young poet-queen and strategist."""
    F = FaceSpec(sex="f", age=24, yaw=-18, skin="#f4dccc", shade="#c98a74", shade_k=0.8,
                 rouge_k=1.3, white_k=0.8, line="ink_brown", line_w=0.8, eye="phoenix",
                 eye_y=0.525, eye_h=0.30, eye_tilt=0.11, eye_w=0.132, eye_gap=0.062, iris=0.50,
                 gaze=(0.45, 0.5), eye_rouge=1.0, crease=0.9, tail=0.22, lower_lid=0.5,
                 brow="willow", brow_y=0.420, brow_len=0.172, brow_th=0.024, brow_lift=0.03,
                 nose_y=0.698, nose_tip=0.068, nose_w=0.044, bridge=0.3, mouth_y=0.788,
                 mouth_w=0.126, lip_up=0.021, lip_lo=0.028, smile=0.25, lip="#c8323f", lip_k=1.25,
                 shape=dict(width=0.92, jaw=0.95, chin=0.80, cheekbone=0.6, chin_fwd=0.85, round=1.0), seed=21)
    return Character(
        key="hero_scholar", face=F, seed=21,
        body=dict(shoulder=0.84, neck_r=0.165, yaw_k=0.9),
        hair=dict(kind="lady", loops=0, tiers=2, seed=4, volume=0.04, puff=1.25,
                  ornaments=dict(phoenix=True, flower="#d77a8a", pins=2, comb=False)),
        costume=dict(
            robes=[dict(color="white", collar="white", cross_y=1.22, neck_u=0.36, cw=0.035),
                   dict(color="cinnabar", collar="cinnabar_l", cross_y=1.32, neck_u=0.48, cw=0.05,
                        pattern="gold_dots"),
                   dict(color="azurite", collar="#2c3e55", cross_y=1.46, neck_u=0.62, cw=0.10,
                        pattern="cloud")],
            shawl=dict(color="malachite_p", alpha=0.8),
            necklace=dict()))


def hero_elder():
    """An old white-bearded sage in a scholar's cap: calm and wise."""
    F = FaceSpec(sex="m", age=75, yaw=17, skin="skin_elder", shade_k=1.1, rouge_k=0.45,
                 white_k=0.5, line_w=0.95, eye="elder", eye_h=0.27, eye_tilt=0.0, eye_w=0.124,
                 iris=0.46, gaze=(0.5, 0.0), tail=0.0, crease=0.8, brow="longevity",
                 brow_th=0.026, brow_grey=0.95, brow_lift=0.0, brow_y=0.425, nose_tip=0.105,
                 nose_w=0.058, mouth_w=0.165, smile=0.3, lip="#b8645a", lip_k=0.6,
                 wrinkles=1.0, shape=dict(width=0.97, jaw=0.94, chin=1.0, cheekbone=1.1), seed=31)
    return Character(
        key="hero_elder", face=F, seed=31,
        body=dict(shoulder=0.92, neck_r=0.19, yaw_k=0.9),
        hair=dict(kind="male", grey=0.95, bun=False),
        beard=dict(kind="long", length=0.62, grey=0.96, density=1.0, seed=5),
        headgear=dict(kind="scholar_cap"),
        costume=dict(
            robes=[dict(color="white", collar="white", cross_y=1.24, neck_u=0.42, cw=0.04),
                   dict(color="#56687c", collar="ink_d", cross_y=1.44, neck_u=0.62, cw=0.11)]))


HEROES = {"hero_warlord": hero_warlord, "hero_scholar": hero_scholar, "hero_elder": hero_elder}
