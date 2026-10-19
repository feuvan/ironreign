"""Hero portrait specs (hand-tuned) - the archetype generator lives in canon.py."""

import costume
import gear
import patterns as pat


def _robe(layers):
    def b(C):
        for L in layers:
            costume.robe_layer(C, L, C.root)
    return b


def hero_elder():
    robe_out = dict(name="RobeOuter", color="#3C4A58", tint="#1C242C", ease=0.016,
                    ease_low=0.02, z_back=0.122, v_left=(0.05, 0.13), v_bottom=(-0.012, 0.215),
                    v_right=(-0.05, 0.13), ext=(-0.13, 0.37),
                    pattern=pat.roundels("#3C4A58", "#4D5D6C", rep_u=20, rep_v=17, amount=0.45),
                    band=dict(w=0.036, color="lead_white", tint="#8A8478",
                              pattern=pat.band("#B9B2A2", "#B9B2A2", rep=70, amount=0.5,
                                               kind="diamond")))
    robe_in = dict(name="RobeInner", color="lead_white", tint="#9A9282", ease=0.008,
                   z_back=0.118, v_left=(0.036, 0.125), v_bottom=(-0.004, 0.19),
                   v_right=(-0.036, 0.125), ext=None,
                   band=dict(w=0.016, color="#D8D0BE", tint="#8A8478"))
    return dict(
        key="hero_elder", seed=11, yaw=-27.0, pitch=4.0,
        body=dict(gender=1.0, years=78, muscle=0.4, weight=0.45,
                  mods={"head/head-oval": 0.5, "cheek/{s}-cheek-volume-decr|incr": -0.3,
                        "nose/nose-scale-vert-decr|incr": 0.25,
                        "chin/chin-height-decr|incr": 0.2}),
        face=dict(
            eye=dict(W=3.0, Hu=0.62, Hl=0.3, tilt=-0.08, peak_u=0.4, peak_l=0.55, tail=0.06,
                     tail_rise=-5, lid_w=0.16, lower_w=0.075, crease=0.26, crease_w=0.06,
                     iris_r=0.47, gaze=(0.22, -0.02), dx=0.03),
            brow=dict(kind="elder", color="#8E877C", streak="#F2EEE6", thick=1.2, rise=-0.2,
                      hair=0.7),
            mouth=dict(W=3.8, Hu=0.32, Hl=0.4, corner=0.09, color="#B06A5E", line="#6A3A30"),
            nose=dict(wing=1.0),
            wrinkles=dict(forehead=3, crows=3, nasolabial=1.2, under_eye=1),
            skin=dict(base="skin_old", cheek=0.26, ear=0.3),
        ),
        builders=[
            _robe([robe_in, robe_out]),
            lambda C: gear.hair_cap(C, dict(color="#BDB6AA", thick=0.004, top=0.004,
                                            line=[(0, 70), (40, 74), (60, 82), (75, 100),
                                                  (95, 96), (120, 108), (180, 124)]), C.root),
            lambda C: gear.tall_hat(C, dict(half=0.072, height=0.12, flare=0.06), C.root),
            lambda C: gear.beard(C, dict(style="long3", length=0.17, n=420, n_side=120, n_m=90,
                                         colors=[("#F4F1EA", 0.55), ("#9E978C", 0.45)],
                                         wash="#D6D1C6", wash_r=0.0022, r=0.0002,
                                         m_len=0.045, m_droop=1.2), C.root),
        ],
    )


def hero_warlord():
    robe = dict(name="RobeUnder", color="#8E2A22", tint="#4A1410", ease=0.012, ease_low=0.014,
                z_back=0.118, v_left=(0.045, 0.125), v_bottom=(-0.01, 0.2), v_right=(-0.045, 0.125),
                ext=None, fold_lines=[],
                band=dict(w=0.026, color="#2A2520", tint="#100E0C",
                          pattern=pat.band("gold", "gold", rep=60, amount=0.8, kind="dots")))
    arm = dict(plate="#4D5E70", plate_light="#6E8194", lacing="#9A3A28", rep_u=80.0, rows=44.0,
               ease=0.03, z_neck=0.168, front_dip=0.03, trim="gold", disc_r=0.031,
               disc_x=0.06, disc_dz=0.232, z_top=0.158, z_bot=0.3, span=52,
               p_plate="#8C3A2A", p_plate_light="#B5604A")

    def armour(C):
        costume.robe_layer(C, robe, C.root)
        costume.cuirass(C, arm, C.root)
        costume.pauldrons(C, arm, C.root)
        costume.chest_discs(C, arm, C.root)
        costume.scarf(C, dict(color="#B3301F", dz=0.152, r=0.013, ease=0.016, sag=0.02), C.root)
    return dict(
        key="hero_warlord", seed=21, yaw=26.0, pitch=4.0,
        body=dict(gender=1.0, years=55, muscle=0.75, weight=0.6,
                  mods={"head/head-square": 0.55, "chin/chin-width-decr|incr": 0.35,
                        "chin/chin-prominent-decr|incr": 0.25,
                        "cheek/{s}-cheek-bones-decr|incr": 0.3,
                        "eyebrows/eyebrows-trans-backward|forward": 0.35,
                        "neck/neck-scale-horiz-decr|incr": 0.4,
                        "nose/nose-scale-horiz-decr|incr": 0.15,
                        "nose/nose-flaring-decr|incr": 0.25}),
        face=dict(
            eye=dict(W=3.3, Hu=0.7, Hl=0.33, tilt=0.26, peak_u=0.45, peak_l=0.6, tail=0.22,
                     tail_rise=14, lid_w=0.2, lower_w=0.08, crease=0.2, crease_w=0.06,
                     iris_r=0.47, gaze=(-0.24, 0.0), dx=0.05),
            brow=dict(kind="sword", color="#2A2622", streak="#6E6964", thick=1.3, rise=0.32,
                      hair=0.55),
            mouth=dict(W=4.4, Hu=0.36, Hl=0.42, corner=-0.09, color="#9E5A4C", line="#5A2A22"),
            nose=dict(wing=1.08),
            wrinkles=dict(forehead=2, crows=2, nasolabial=1.0),
            skin=dict(base="skin_bronze", cheek=0.16, ear=0.3, shade_tint="#9C6448"),
        ),
        builders=[
            armour,
            lambda C: gear.helmet(C, dict(color="#4D5E70", color_light="#8396A8", band="gold",
                                          guard="#4D5E70", guard_light="#6E8194",
                                          lacing="cinnabar", stem=0.022, tassel_len=0.075,
                                          tassel_n=420),
                                  C.root),
            lambda C: gear.beard(C, dict(style="full", length=0.09, n=130, n_m=120, locks=9,
                                         fork=0.0, span=0.05, above=0.009,
                                         colors=[("ink_dense", 0.45), ("#4A4642", 0.25),
                                                 ("#A8A39B", 0.3)],
                                         wash="#3A3632", wash_r=0.0011, r=0.00017,
                                         m_len=0.042, m_droop=1.3, shadow=0.45), C.root),
        ],
    )


def hero_scholar():
    """Su Wanqing, poet-queen and strategist."""
    robe_out = dict(name="RobeOuter", color="#2E4E86", tint="#16264A", ease=0.016, ease_low=0.02,
                    z_back=0.11, v_left=(0.046, 0.12), v_bottom=(-0.008, 0.235),
                    v_right=(-0.046, 0.12), ext=(-0.12, 0.36), fold_w=0.0014,
                    pattern=pat.scattered_flowers("gold", rep_u=26, rep_v=22, r=0.2,
                                                  amount=0.8),
                    band=dict(w=0.03, color="#A82A2E", tint="#4A1012",
                              pattern=pat.band("gold", "gold", rep=55, amount=0.85,
                                               kind="diamond")))
    robe_mid = dict(name="RobeMid", color="#D9776E", tint="#7A2E2A", ease=0.011,
                    z_back=0.108, v_left=(0.04, 0.116), v_bottom=(-0.005, 0.21),
                    v_right=(-0.04, 0.116), ext=None, fold_lines=[],
                    band=dict(w=0.012, color="#E8C3B0", tint="#8A5A4A"))
    robe_in = dict(name="RobeInner", color="lead_white", tint="#9A9282", ease=0.007,
                   z_back=0.105, v_left=(0.034, 0.112), v_bottom=(-0.003, 0.19),
                   v_right=(-0.034, 0.112), ext=None, fold_lines=[],
                   band=dict(w=0.01, color="#F2EEE4", tint="#8A8478"))
    return dict(
        key="hero_scholar", seed=31, yaw=-24.0, pitch=4.0, head_frac=0.47,
        shoulder_dz=0.19, arm_drop=0.3,
        body=dict(gender=0.0, years=26, muscle=0.4, weight=0.48,
                  mods={"head/head-oval": 0.5, "head/head-round": 0.3,
                        "head/head-scale-vert-decr|incr": -0.25,
                        "chin/chin-height-decr|incr": -0.3,
                        "chin/chin-width-decr|incr": -0.3,
                        "chin/chin-bones-decr|incr": -0.35,
                        "neck/neck-scale-horiz-decr|incr": 0.25,
                        "cheek/{s}-cheek-volume-decr|incr": 0.25,
                        "nose/nose-scale-horiz-decr|incr": -0.2,
                        "nose/nose-scale-depth-decr|incr": -0.15,
                        "mouth/mouth-scale-horiz-decr|incr": -0.2}),
        face=dict(
            eye=dict(W=3.4, Hu=0.78, Hl=0.36, tilt=0.27, peak_u=0.42, peak_l=0.58, tail=0.3,
                     tail_rise=17, lid_w=0.19, lower_w=0.065, crease=0.18, crease_w=0.05,
                     iris_r=0.54, gaze=(0.24, 0.0), dx=0.02, iris_col="#3A2418"),
            brow=dict(kind="willow", color="#2E2925", thick=1.4, dz=-0.12, hair=0.35,
                      sharp=0.3, length=1.0),
            mouth=dict(W=3.3, Hu=0.46, Hl=0.56, corner=0.08, color="#C43A3A", line="#7A2226",
                       line_w=0.05, line_len=0.72),
            nose=dict(wing=0.8, bridge=0.6, w=0.06),
            huadian=dict(color="#C8302A", r=0.3, petals=5, dz=2.05),
            skin=dict(base="skin_ivory", cheek=0.3, eyelid=0.22, ear=0.35, three_white=0.3,
                      nose=0.08, shade_tint="#C98A78", edge=0.45, ao=0.6),
        ),
        builders=[
            _robe([robe_in, robe_mid, robe_out]),
            lambda C: costume.shawl(C, dict(color="#A9CFB5", w=0.036, ease=0.02, twist=0.8,
                                            pattern=pat.scattered_flowers("lead_white", rep_u=40,
                                                                          rep_v=40, amount=0.6)),
                                    C.root),
            lambda C: gear.lady_hair(C, dict(flower_r=0.03, comb=False, bun_lift=0.012,
                                             bun_back=0.016), C.root),
            lambda C: gear.earrings(C, dict(), C.root),
        ],
    )


REG = {"hero_elder": hero_elder, "hero_warlord": hero_warlord, "hero_scholar": hero_scholar}


def get(key):
    if key in REG:
        return REG[key]()
    import canon
    return canon.spec(key)
