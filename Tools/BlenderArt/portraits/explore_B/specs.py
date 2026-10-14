"""Hero specs + archetype presets for approach B."""
import copy

from .identity import ARCH, wrinkle_default

WARLORD = dict(
    name="hero_warlord", seed=11,
    identity=dict(gender=1.0, age=54, muscle=0.8, weight=0.5,
                  sliders=dict(ARCH["warlord"], head_fat=-0.8, cheek_volume=-0.7, cheek_bones=0.8,
                               brow_ridge=1.0, eye_push1=0.3, eye_push2=0.3, eye_fold=0.6,
                               eye_height2=0.2, head_age=0.6, jaw_drop=0.3, chin_width=0.6,
                               nose_hump=0.5),
                  skin_tone=0.65, weathered=0.7, wrinkles=0.75, frown=0.7, gaunt=0.25,
                  beard_shadow=0.35, beard_paint=0.55, brow_paint=0.8,
                  hair_melanin=0.985, hair_redness=0.1, grey=0.2, skin_ruddy=0.45,
                  expression={"eyebrows-down": 0.5, "mouth-compression": 0.4}),
    groom=dict(beard=dict(chin_len=0.09, cheek_len=0.04, clumping=0.75, count=9000, curl=0.06),
               moustache=dict(length=0.045, droop=0.7, count=2000),
               brows_kw=dict(angle=0.3),
               scalp=dict(count=6000, knot=(0, 0.02, -0.006))),
    light=dict(key_angle=155, key_elev=18, fill=2.0, key=40, key_size=0.25, world=0.02),
    camera=dict(head_frac=0.46),
    outfit=dict(builder="warlord_armour"),
)

SCHOLAR_F = dict(
    name="hero_scholar", seed=23,
    identity=dict(gender=0.0, age=24, muscle=0.35, weight=0.42,
                  sliders=dict(ARCH["scholar_f"], eye_scale=0.3, eye_height2=0.3, brow_height=-0.35,
                               lip_lower_vol=0.1, lip_upper_vol=0.05, mouth_width=-0.35),
                  skin_tone=0.12, skin_ruddy=0.3, makeup=0.5, scalp_mask="scalp_low",
                  lip_color="#9A3A3C", wrinkles=0.0, brow_paint=0.6, scalp_paint=0.9,
                  hair_melanin=0.98, hair_redness=0.1, grey=0.0, weathered=0.0,
                  expression={"mouth-corner-puller": 0.12, "eye-slit": 0.1}),
    groom=dict(brows_kw=dict(angle=0.12, length=0.008, count=800, r_root=0.0001),
               lash_kw=dict(length=0.0085, count=90),
               scalp=dict(count=18000, knot=(0, 0.012, 0.004), part="center", layer=(0.0008, 0.004),
                          mask="z_scalp_low", puff=0.008,
                          buns=[dict(radius=0.036, height=0.030, count=5000, turns=1.4, offset=(0, 0.004, 0.024)),
                                dict(radius=0.024, height=0.020, count=2000, offset=(0, 0.034, 0.004), turns=1.2)]),
               side_locks=dict(count=90, length=0.17), rough=0.3),
    light=dict(key_angle=140, key_elev=30, fill=3.0, key=34, key_size=0.3, world=0.025, rim=30),
    camera=dict(head_frac=0.47),
    outfit=dict(builder="robe", headwear="pins", flower="#E9A6B4",
                layers=[dict(color="#E6DECF", band="#EFE8DA", border="#D8C8A0", border_width=0.0,
                             thickness=0.006, dip=0.03, depth=0.055, band_w=0.016),
                        dict(color="#D49A9E", band="#C98088", border="#E8D2A0", thickness=0.011, dip=0.07,
                             depth=0.085, band_w=0.022),
                        dict(color="#24564A", band="#1A3A34", border="#C9A24A", pattern="cloud",
                             pattern_color="#3E7A62", thickness=0.017, dip=0.11, depth=0.12, band_w=0.034,
                             folds=0.003, border_width=0.32)]),
    background=dict(tint=(0.8, 1.0, 0.95), tint_amt=0.25),
)

SAGE = dict(
    name="hero_elder", seed=37,
    identity=dict(gender=1.0, age=74, muscle=0.35, weight=0.4, sliders=dict(ARCH["sage"]),
                  skin_tone=0.4, weathered=0.35, wrinkles=1.0, frown=0.2, gaunt=0.6, smile=0.3,
                  brow_paint=0.35, scalp_paint=0.5, beard_paint=0.25,
                  hair_melanin=0.3, hair_redness=0.1, grey=0.97, skin_ruddy=0.35,
                  expression={"eyebrows-inner-up": 0.25, "eye-slit": 0.25, "mouth-corner-puller": 0.15}),
    groom=dict(beard=dict(chin_len=0.26, cheek_len=0.07, clumping=0.8, count=9000, curl=0.0, droop=0.95,
                          forward=0.15, width_scale=1.3, noise=0.0, wave=0.004),
               moustache=dict(length=0.075, droop=0.9, count=1800),
               brows_kw=dict(angle=-0.25, tail_len=3.0, droop=0.6, length=0.016, count=1300),
               scalp=dict(count=14000, knot=(0, 0.018, 0.0), layer=(0.0008, 0.003), recede=0.5,
                          buns=[dict(radius=0.020, height=0.018, count=1600, offset=(0, 0, 0.012))]),
               beard_grey=1.0, brow_grey=1.0, rough=0.4),
    light=dict(key_angle=145, key_elev=28, fill=2.5, key=36, key_size=0.28, world=0.022),
    camera=dict(head_frac=0.47),
    outfit=dict(builder="robe", headwear="crown", crown_at=(0, 0.018, 0.016),
                beads=dict(r=0.0065, drop=0.17, hex="#5A2C18", big_every=9),
                layers=[dict(color="#E4DED2", band="#ECE6DA", border_width=0.0, thickness=0.006, dip=0.03,
                             depth=0.06, band_w=0.018),
                        dict(color="#8E9AA6", band="#7A8794", border="#C9B98A", border_width=0.0,
                             thickness=0.011, dip=0.07, depth=0.09, band_w=0.022),
                        dict(color="#2B3442", band="#121314", border="#7A6A48", pattern="diamond",
                             pattern_color="#323C4C", pattern_scale=30.0, thickness=0.018, dip=0.12,
                             depth=0.13, band_w=0.045, folds=0.004, border_width=0.18)]),
    background=dict(tint=(1.0, 0.95, 0.85), tint_amt=0.15),
)

SPECS = {"hero_warlord": WARLORD, "hero_scholar": SCHOLAR_F, "hero_elder": SAGE}


def get(name):
    return copy.deepcopy(SPECS[name])
