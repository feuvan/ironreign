"""Character specs for gongbi_C (pure python).

A spec is a dict:

    name, seed
    pose      body_yaw / head_yaw / head_pitch / cam_pitch (deg)
    frame     eye_frac / head_frac / x_frac
    skin      key of palette.SKIN
    head      geo.HEAD_DEFAULT overrides (3D skull / jaw / chin shape)
    neck      geo.neck_loft overrides
    torso     geo.TORSO_DEFAULT overrides
    face      canon.FACE parameters for the 2D features (see canon.py)
    hair      hair masses (gear.py) + 2D hair strands
    beard     2D beard (canon.py)
    headgear  helmet / hat (gear.py)
    costume   robe, collar layers, armour, cloak (bust.py, gear.py)
"""

import copy
import json
import os

HEROES = {}


def load(name):
    if os.path.exists(name):
        with open(name) as f:
            return json.load(f)
    if name in HEROES:
        return copy.deepcopy(HEROES[name])
    import cast
    return cast.spec_for(name)


HEROES["test"] = dict(
    name="test", seed=1,
    pose=dict(body_yaw=-28.0, head_yaw=6.0, cam_pitch=-2.0),
    skin="warm",
    costume=dict(
        robe=dict(color="azurite"),
        collar=dict(layers=[dict(color="white", w=0.05), dict(color="cinnabar", w=0.06),
                            dict(color="indigo", w=0.10)]),
    ),
)


# =============================================================================================
# heroes (hand-tuned; the cast generator in cast.py builds the other officers)
# =============================================================================================
HEROES["hero_warlord"] = dict(
    name="hero_warlord", seed=101,
    # Yan Tieshan, the Iron Mountain: grizzled northern warlord in his fifties
    pose=dict(body_yaw=-30.0, head_yaw=8.0, head_pitch=-1.0, cam_pitch=-3.0),
    frame=dict(head_frac=0.47),
    skin="weathered",
    head=dict(cheek_w=0.338, jaw_w=0.290, chin_w=0.13, jaw_sq=2.6, temple_w=0.322,
              skull_w=0.338, flat=2.55, chin_d=0.385),
    neck=dict(w=0.285, d=0.23),
    torso=dict(shoulder_w=1.1, bulk=1.05, slope=0.3, neck_w=0.30),
    face=dict(eye="tiger", brow="silkworm", nose="strong", mouth="firm", knit=0.7,
              brow_color="ink", gaze=0.85,
              brow_dz=-0.008, eye_mod=dict(open=0.38, iris_up=0.05, iris=0.21),
              mouth_mod=dict(corner=-0.008, w=0.10),
              rouge=dict(color="#C2735E", alpha=0.13, r=0.13),
              whites=0.10, socket=0.32,
              wrinkles=dict(forehead=2, crow=2, naso=0.9, bags=0.55, knit=2, mouth=0.5)),
    beard=dict(color="grizzled", width=1.0,
               moustache=dict(len=0.12, droop=0.07, angle=26, density=1.1, thick=1.2),
               chin=dict(len=0.40, width=0.24, shape="full", density=1.6),
               cheeks=dict(density=1.1, len=0.10, top=-0.10, depth=0.06),
               tuft=dict(len=0.05), stubble=0.10),
    hair=dict(kind="topknot", color="#3E3A36", line_z=0.27, buns=[]),
    headgear=dict(kind="helmet", color="steel", brim_z=0.17, lift=0.035, peak=0.11,
                  tassel_color="cinnabar", tassel_len=0.20, guard_drop=0.50, guard_flare=0.38,
                  open_t=1.05),
    costume=dict(
        robe=dict(color="cinnabar"),
        collar=dict(neck_z=-0.68, cross_z=-0.96, x_neck=0.16,
                    layers=[dict(color="white", w=0.04), dict(color="cinnabar_d", w=0.05)]),
        armour=dict(color="steel", light="steel_l", lace="cinnabar", collar_color="cinnabar",
                    collar_pattern=dict(kind="brocade", motif="dots", color="gold", period=0.05),
                    mirror_z=-1.26, mirror_x=0.38, mirror_r=0.14, top_z=-0.80, strap=False),
        cloak=dict(color="cinnabar_d"),
    ),
)

HEROES["hero_scholar"] = dict(
    name="hero_scholar", seed=202,
    # Su Wanqing, the Lotus Poet: young poet-queen and strategist
    pose=dict(body_yaw=-27.0, head_yaw=6.0, head_pitch=1.0, head_roll=-2.0, cam_pitch=-2.0),
    frame=dict(head_frac=0.45, min_head=0.88, eye_frac=0.40),
    skin="ivory",
    head=dict(cheek_w=0.312, jaw_w=0.240, chin_w=0.115, jaw_sq=1.85, temple_w=0.31,
              skull_w=0.322, cheek_full=0.022, flat=2.35, chin_d=0.37, chin_z=-0.47,
              jaw_z=-0.28),
    neck=dict(w=0.205, d=0.18),
    torso=dict(shoulder_w=0.94, shoulder_z=-1.0, slope=0.7, chest_d=0.40, neck_w=0.225,
               neck_base=-0.645),
    ear=dict(h=0.25, w=0.115),
    earrings=dict(color="pearl", metal="gold"),
    face=dict(eye="almond", brow="willow", nose="small", mouth="cherry", gaze=0.8,
              eye_mod=dict(tilt=0.075, tail=0.10, open=0.37, w=0.142, line=2.1),
              mouth_mod=dict(z=-0.278, corner=0.007),
              rouge=dict(color="#E08A88", alpha=0.30, r=0.13, x=0.17, z=-0.12),
              eye_rouge=0.14, whites=0.30, socket=0.16,
              mark=dict(kind="petals", color="cinnabar")),
    hair=dict(kind="lady", color="hair", line_z=0.345, arch=0.035, temple_z=0.235, side_z=-0.02,
              over_ear_z=0.05, nape_z=-0.15, side_puff=0.10, puff_t=1.45, puff_z=0.09,
              volume=0.016, top_volume=0.03, widow=0.012, knot_at=(0.0, 0.08, 0.66),
              flow_n=72,
              buns=[dict(kind="ellipsoid", c=(0.0, 0.10, 0.50), r=(0.22, 0.20, 0.11)),
                    dict(kind="ellipsoid", c=(0.0, 0.07, 0.70), r=(0.165, 0.15, 0.20), tilt=-12,
                         flow_n=14),
                    dict(kind="loop", c=(0.0, 0.16, 0.66), R=0.11, r=0.045, yaw=90, tilt=0,
                         a0=-0.1, a1=1.1)],
              ornaments=[dict(kind="flower", c=(0.02, -0.07, 0.86), r=0.085, color="lotus",
                              petals=8),
                         dict(kind="pin", a=(0.10, 0.10, 0.62), b=(0.32, -0.02, 0.78),
                              r=0.010, head=0.032, head_color="gold", dangles=3,
                              dangle_len=0.16, dangle_color="cinnabar"),
                         dict(kind="pin", a=(-0.08, 0.12, 0.64), b=(-0.30, 0.0, 0.74),
                              r=0.009, head=0.026, head_color="malachite"),
                         dict(kind="comb", c=(0.0, -0.11, 0.60), w=0.15, h=0.06,
                              color="gold", tilt=-35)]),
    costume=dict(
        robe=dict(color="azurite", pattern=dict(kind="roundels", period=0.15, size=0.24,
                                                color="azurite_l", color2="gold_l",
                                                alpha=0.38)),
        collar=dict(neck_z=-0.66, cross_z=-0.98, x_neck=0.12,
                    layers=[dict(color="white", w=0.035), dict(color="lotus_l", w=0.04),
                            dict(color="cinnabar", w=0.085,
                                 pattern=dict(kind="brocade", motif="lozenge", color="gold",
                                              period=0.05))]),
        shawl=dict(color="malachite_l", w=0.30),
    ),
)

HEROES["hero_elder"] = dict(
    name="hero_elder", seed=303,
    # an old white-bearded sage in a 东坡 scholar's hat
    pose=dict(body_yaw=-26.0, head_yaw=6.0, head_pitch=2.5, cam_pitch=-2.0),
    frame=dict(head_frac=0.45, min_head=0.8),
    skin="elder",
    head=dict(cheek_w=0.312, jaw_w=0.252, chin_w=0.11, flat=2.4, cheek_full=-0.008,
              chin_d=0.375),
    neck=dict(w=0.24, d=0.2),
    torso=dict(shoulder_w=0.95, slope=0.6),
    ear=dict(h=0.29, w=0.13),
    face=dict(eye="kind", brow="longevity", nose="strong", mouth="elder", gaze=0.7,
              brow_color="white", brow_mod=dict(droop=0.11, wash=0.7),
              rouge=dict(color="#D08A7E", alpha=0.10), whites=0.14, socket=0.26,
              wrinkles=dict(forehead=2, crow=3, naso=0.9, bags=0.8, mouth=0.6)),
    beard=dict(color="white", width=1.0, strand_w=0.45,
               moustache=dict(len=0.13, droop=0.10, angle=40, density=1.0, reach=1.0),
               chin=dict(len=0.78, width=0.14, shape="pointed", density=1.8, lean=0.02),
               cheeks=dict(density=0.45, len=0.08, top=-0.27, depth=0.04, grow=0.1),
               tuft=dict(len=0.06)),
    hair=dict(kind="elder", color="white_hair", strand="#8E8880", line_z=0.24, temple_z=0.16,
              buns=[]),
    headgear=dict(kind="dongpo", color="ink", base_z=0.175, h=0.42, h_out=0.26),
    costume=dict(
        robe=dict(color="#6F8F86"),
        collar=dict(neck_z=-0.66, cross_z=-0.98, x_neck=0.15,
                    layers=[dict(color="white", w=0.04), dict(color="#2A2622", w=0.11)]),
    ),
)
