"""Character specs: the three hero test portraits (archetype generators live in cast.py).

Heroes are mapped onto scenario portrait keys by :data:`cast.HERO_KEYS`
(Yan Tieshan m_warrior_01, Su Wanqing f_scholar_04, Wen Tingjian m_elder_03).
"""

from face import FaceSpec
from portrait import Character


def hero_warlord():
    """Yan Tieshan 燕铁山, the Iron Mountain (46): grizzled, iron-willed northern warlord of the
    Iron Banner.  Black-lacquered 山文 armour, red-lacquer shoulder guards, gilt gorget, red
    scarf and cloak; a direct, commanding gaze (never a side-glance)."""
    F = FaceSpec(sex="m", age=46, yaw=21, skin="#d8a98e", shade_k=1.30, rouge_k=0.40,
                 white_k=0.30, line_w=1.1, eye="fierce", eye_h=0.34, eye_tilt=0.05,
                 eye_w=0.128, iris=0.47, iris_tuck=0.32, gaze=(0.52, 0.0), tail=0.0, crease=0.6,
                 brow="sword", brow_th=0.036, brow_lift=0.042, brow_knit=0.8, brow_grey=0.10,
                 brow_y=0.425, nose_tip=0.10, nose_w=0.064, mouth_w=0.180, lip_up=0.016,
                 lip_lo=0.022, smile=-0.35, lip="#a55a4e", lip_k=0.8, wrinkles=0.55, frown=0.8,
                 shape=dict(jaw=1.10, chin=1.12, width=1.02, cheekbone=1.3), seed=11)
    return Character(
        key="hero_warlord", face=F, seed=11,
        body=dict(shoulder=1.08, neck_r=0.23, yaw_k=0.9, adam=0.0),
        hair=dict(kind="male", grey=0.40, bun=False, ear=False),
        beard=dict(kind="full", length=0.30, grey=0.34, density=1.0, seed=3),
        headgear=dict(kind="helmet", metal="#3f4c5c", trim="gold", plume="cinnabar",
                      rim_front=0.305, wings=False, guard_color="#2b2827"),
        costume=dict(
            cloak=dict(color="carmine", spread=0.22),
            robes=[dict(color="cinnabar", collar="cinnabar_l", cross_y=1.24, neck_u=0.45,
                        cw=0.06, collar_line="ink", pattern="gold_dots")],
            armour=dict(palette="steel",
                        cuirass=dict(neck_y=1.08, neck_depth=0.14, neck_u=0.60),
                        mirror=dict(u=0.0, y=1.60, r=0.115, trim="gold"),
                        pauldron=dict(rows=4, size=1.0, color="#8e2a22", style="scale"),
                        scarf=dict(color="#b3301f", knot=(0.34, 1.24)))))


def hero_scholar():
    """Su Wanqing 苏婉清, the Lotus Poet (28): poet-queen and strategist of the south.  A full
    鹅蛋 oval face, willow brows, bright phoenix eyes, 花钿 and rouge; azurite robe with gold
    roundels over cinnabar and white, a malachite stole."""
    F = FaceSpec(sex="f", age=28, yaw=-18, skin="#f3d8c4", shade="#c98a74", shade_k=0.85,
                 rouge_k=1.2, white_k=0.6, line="ink_brown", line_w=0.8, eye="phoenix",
                 eye_y=0.525, eye_h=0.33, eye_tilt=0.10, eye_w=0.130, eye_gap=0.063, iris=0.44,
                 iris_tuck=0.28, gaze=(0.5, 0.3), eye_rouge=0.9, crease=0.9, tail=0.20,
                 lower_lid=0.5, brow="willow", brow_y=0.420, brow_len=0.170, brow_th=0.023,
                 brow_lift=0.03, nose_y=0.696, nose_tip=0.066, nose_w=0.044, bridge=0.3,
                 mouth_y=0.783, mouth_w=0.124, lip_up=0.020, lip_lo=0.027, smile=0.32,
                 lip="#c43a42", lip_k=1.15,
                 shape=dict(width=0.94, jaw=0.97, chin=0.95, cheekbone=0.6, chin_fwd=0.85,
                            round=0.3, chin_len=0.97, oval=1.0, oval_p=2.6), seed=21)
    return Character(
        key="hero_scholar", face=F, seed=21,
        body=dict(shoulder=0.86, neck_r=0.168, yaw_k=0.9),
        hair=dict(kind="lady", loops=0, tiers=2, seed=4, volume=0.04, puff=1.25,
                  ornaments=dict(phoenix=True, flower="#d77a8a", pins=2, comb=False)),
        costume=dict(
            robes=[dict(color="white", collar="white", cross_y=1.17, neck_y=1.05, neck_u=0.38,
                        cw=0.035),
                   dict(color="cinnabar", collar="cinnabar_l", cross_y=1.27, neck_y=1.05,
                        neck_u=0.50, cw=0.05, pattern="gold_dots"),
                   dict(color="azurite", collar="#2c3e55", cross_y=1.41, neck_y=1.05,
                        neck_u=0.64, cw=0.10, pattern="cloud",
                        pattern_body=dict(kind="roundels", color="gold", alpha=0.85,
                                          size=0.040, period=0.30))],
            shawl=dict(color="malachite_p", alpha=0.8),
            necklace=dict()))


def hero_elder():
    """Wen Tingjian 文庭坚, the Grand Chancellor (66): an old white-bearded sage in a 东坡
    scholar's cap, calm and wise, kindly long white 寿眉 brows."""
    F = FaceSpec(sex="m", age=66, yaw=17, skin="skin_elder", shade_k=1.1, rouge_k=0.45,
                 white_k=0.5, line_w=0.95, eye="elder", eye_h=0.32, eye_tilt=0.0, eye_w=0.124,
                 iris=0.47, iris_tuck=0.34, gaze=(0.5, 0.0), tail=0.0, crease=0.8,
                 brow="longevity", brow_th=0.026, brow_grey=0.95, brow_lift=0.0, brow_y=0.425,
                 nose_tip=0.105, nose_w=0.058, mouth_w=0.165, smile=0.3, lip="#b8645a",
                 lip_k=0.6, wrinkles=1.0,
                 shape=dict(width=0.97, jaw=0.94, chin=1.0, cheekbone=1.1), seed=31)
    return Character(
        key="hero_elder", face=F, seed=31,
        body=dict(shoulder=0.92, neck_r=0.19, yaw_k=0.9),
        hair=dict(kind="male", grey=0.95, bun=False),
        beard=dict(kind="long", length=0.62, grey=0.96, density=1.0, seed=5),
        headgear=dict(kind="scholar_cap"),
        costume=dict(
            robes=[dict(color="white", collar="white", cross_y=1.24, neck_u=0.42, cw=0.04),
                   dict(color="#56687c", collar="ink_d", cross_y=1.44, neck_u=0.62, cw=0.11,
                        pattern_body=dict(kind="damask", alpha=0.42, size=0.060,
                                          period=0.34))]))


HEROES = {"hero_warlord": hero_warlord, "hero_scholar": hero_scholar, "hero_elder": hero_elder}
