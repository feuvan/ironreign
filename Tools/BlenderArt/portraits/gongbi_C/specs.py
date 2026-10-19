"""Character specs for gongbi_C (pure python).

A spec is a dict:

    pose      yaw (camera, deg; + turns the face to the image left), pitch, head_yaw/pitch/roll,
              x_frac (head centre across the frame)
    head      3D head shape (b_body.head_params): scale, width, jaw, chin, cheek, face_len ...
    body      torso (b_body.body_params): shoulder, chest, slope, neck, bulk
    skin      looks.SKIN key
    face      2D face canon (canon.face(...)): eyes, brows, nose, mouth, beard, age, makeup
    hair      dict(style=..., color=...)
    headgear  dict(kind=...)
    costume   dict(robe=..., collar=..., armour=..., cloak=..., shawl=...)
"""

import copy

import canon

SPECS = {}


def reg(name, spec):
    SPECS[name] = spec
    return spec


#: portrait keys of the scenario officers that use a hand-tuned spec
ALIASES = {"m_warrior_01": "hero_warlord", "f_scholar_04": "hero_scholar", "m_elder_07": "hero_elder"}


def get(name):
    name = ALIASES.get(name, name)
    if name in SPECS:
        return copy.deepcopy(SPECS[name])
    return canon.generate(name)


def robe_folds(k=1.0, side=1):
    """Fold lines (alpha, z) of a robe seen in a bust: from the collar crossing towards the far
    armpit, and the drapes falling from the shoulders."""
    return [
        dict(pts=[(0.62, -0.215), (0.40, -0.262), (0.22, -0.32)], amp=0.004 * k, width=0.016, side=1),
        dict(pts=[(1.10, -0.205), (0.95, -0.255), (0.86, -0.32)], amp=0.005 * k, width=0.018, side=-1),
        dict(pts=[(1.38, -0.215), (1.30, -0.27), (1.26, -0.33)], amp=0.004 * k, width=0.016, side=-1, weight=0.8),
        dict(pts=[(-0.62, -0.240), (-0.78, -0.285), (-0.86, -0.33)], amp=0.004 * k, width=0.016, side=-1),
        dict(pts=[(-1.12, -0.205), (-1.02, -0.26), (-0.98, -0.33)], amp=0.005 * k, width=0.018, side=1),
        dict(pts=[(-1.40, -0.215), (-1.34, -0.27), (-1.30, -0.33)], amp=0.004 * k, width=0.016, side=1, weight=0.8),
    ]


def collar(layers, **kw):
    d = dict(layers=layers, neck_x=0.034, neck_z=-0.144, cross_x=-0.018, cross_z=-0.208,
             step_x=0.011, step_z=0.020, armpit=(-0.20, -0.40))
    d.update(kw)
    return d


reg("test_body", dict(
    seed=1,
    pose=dict(yaw=22.0, pitch=-2.0, head_yaw=4.0, head_pitch=-2.0),
    head=dict(),
    body=dict(),
    skin="warm",
    face=canon.face("m_scholar"),
    costume=dict(
        robe=dict(color="azurite", folds=robe_folds()),
        collar=collar([dict(color="white", band_w=0.013), dict(color="cinnabar", band_w=0.012),
                       dict(color="indigo_d", band_w=0.03, brocade=dict(kind="lozenge", period=0.02))]),
    ),
))

# ---------------------------------------------------------------------------------------------
# the three heroes
# ---------------------------------------------------------------------------------------------
reg("hero_warlord", dict(
    # Yan Tieshan 燕铁山, "the Iron Mountain": grizzled northern warlord in his fifties
    seed=11,
    pose=dict(yaw=24.0, pitch=-3.0, head_yaw=3.0, head_pitch=-2.0, head_roll=-1.0),
    head=dict(canon.HEAD["m_warrior"], width=1.06, jaw=1.16, chin=1.14, cheek=1.05),
    body=dict(canon.BODY["m_warrior"], shoulder=1.10, neck=1.12),
    skin="weathered",
    face=canon.face("m_warrior", brow="sword", brow_w=(0.0056, 0.0072, 0.0022), brow_rise=0.0062,
                    brow_knit=0.0030, brow_color="grizzled", brow_hairs=40, eye_h=0.44, eye_w=0.0300,
                    brow_v=0.0128, iris=0.38, iris_v=0.18, fierce=0.9, age=0.70, bag=0.35, lid_w=2.0, mouth_curve=-0.0014, lip_alpha=0.18,
                    nose_w=0.0178, nose_h=0.0215, rouge=0.12, shade=0.17,
                    hairline=dict(on=False),
                    beard=dict(kind="short_full", length=1.25, density=1.2,
                               color=[("#1C1816", 0.24), ("#45403A", 0.22), ("#8A847C", 0.26),
                                      ("#ECE8E0", 0.28)])),
    hair=dict(style="none"),
    headgear=dict(kind="helmet", plume="cinnabar"),
    costume=dict(
        robe=dict(color="cinnabar", folds=[]),
        collar=collar([dict(color="white", band_w=0.012), dict(color="cinnabar", band_w=0.014)],
                      neck_x=0.030, cross_z=-0.200),
        armour=dict(color="#5E7488", deep="#26323E", lace="#B03A2C"),
        cloak=dict(color="cinnabar", collar="gold"),
    ),
))

reg("hero_scholar", dict(
    # Su Wanqing 苏婉卿: young poet-queen and strategist
    seed=23,
    pose=dict(yaw=-21.0, pitch=-1.0, head_yaw=-3.0, head_pitch=3.0, head_roll=2.5),
    head=dict(canon.HEAD["f_scholar"], chin=0.9, jaw=0.88, face_len=0.96),
    body=dict(canon.BODY["f_scholar"], neck_len=0.70, slope=0.95, neck=0.86, shoulder=0.88),
    skin="ivory",
    face=canon.face("f_scholar", huadian="#C0362C", lip_color="#B8323E", lip_alpha=0.62, mouth_curve=0.0004,
                    eye_w=0.0315, eye_h=0.40, iris=0.46, eye_shadow=0.22, eye_in=0.0148,
                    gaze=(0.0008, 0.0),
                    hairline=dict(on=True, top=0.074, temple_u=0.058, temple_v=0.030, side_v=-0.012,
                                  color="hair", strands=34, widow=0.0)),
    hair=dict(style="lady_high", color="hair", part=0.0015, crown=0.004, thick=0.0045,
              ornaments=dict(comb=True, pins=[(-1, 0.7), (1, 0.55), (1, -0.35)], buyao=True,
                             peony=True, peony_color="rouge", flower_color="cinnabar")),
    earrings=dict(kind="pearl"),
    costume=dict(
        robe=dict(color="#8E2E3E", deep="#5A1828", folds=robe_folds(0.8),
                  roundels=dict(color="#D8B060", alpha=0.45, period=0.07)),
        collar=collar([dict(color="white", band_w=0.010), dict(color="malachite", band_w=0.012),
                       dict(color="#22304A", band_w=0.026,
                            brocade=dict(kind="cloud", period=0.022, motif="gold", edge="gold"))],
                      neck_x=0.030, neck_z=-0.140, cross_z=-0.200, step_x=0.010),
        shawl=dict(color="#A8CDB4", motif="#F6F2E8", width=0.075),
    ),
))

reg("hero_elder", dict(
    # an old white-bearded sage
    seed=37,
    pose=dict(yaw=18.0, pitch=-2.0, head_yaw=2.0, head_pitch=4.0, head_roll=-1.5),
    head=dict(canon.HEAD["m_elder"]),
    body=dict(canon.BODY["m_elder"]),
    skin="elder",
    face=canon.face("m_elder", smile=0.25, mouth_curve=0.0006, brow_droop=0.006,
                    hairline=dict(on=True, top=0.070, temple_u=0.060, temple_v=0.026, side_v=0.002,
                                  color="white", strands=30),
                    beard=dict(kind="five_lock", color="white", length=1.0, density=1.1)),
    hair=dict(style="elder_bun", color="white", thick=0.004, crown=0.0, back=0.004),
    headgear=dict(kind="dongpo", color="#33302E"),
    costume=dict(
        robe=dict(color="#5E7468", deep="#34463E", folds=robe_folds(1.0)),
        collar=collar([dict(color="white", band_w=0.012),
                       dict(color="#2A2420", band_w=0.032)],
                      neck_x=0.032, cross_z=-0.205),
    ),
))
