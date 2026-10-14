"""Hero specs for the Approach A exploration (written as JSON for portrait.py)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

WARLORD = {
    "id": "hero_warlord", "seed": 11, "gender": "m", "age": 54, "archetype": "warrior",
    "expression": "fierce", "expr": {"eyebrows-left-down": 0.25, "eyebrows-right-down": 0.25,
                                     "eye-left-slit": 0.08, "eye-right-slit": 0.08},
    "face": {"chin/chin-width-decr|incr": 0.35, "chin/chin-bones-decr|incr": 0.4, "nose/nose-hump-decr|incr": 0.5,
             "nose/nose-scale-vert-decr|incr": 0.3, "nose/nose-point-width-decr|incr": -0.2,
             "cheek/{s}-cheek-bones-decr|incr": 0.5, "cheek/{s}-cheek-volume-decr|incr": -0.5,
             "eyebrows/eyebrows-trans-backward|forward": 0.5, "eyebrows/eyebrows-angle-down|up": 0.3,
             "eyes/{s}-eye-push1-in|out": -0.3, "head/head-fat-decr|incr": -0.4,
             "forehead/forehead-trans-backward|forward": 0.2, "mouth/mouth-scale-horiz-decr|incr": 0.15,
             "mouth/mouth-laugh-lines-in|out": 0.4, "head/head-age-decr|incr": 0.35,
             "eyes/{s}-eye-bag-decr|incr": 0.5, "eyes/{s}-eye-height2-decr|incr": -0.15},
    "identity": {"skin_tone": 0.85, "skin_red": 0.75, "muscle": 0.85, "weight": 0.5},
    "iris": 0.3,
    "skin": {"weather": 0.9, "scars": [[[0.62, 0.62], [0.98, -0.05]]], "stubble": 0.3},
    "hair": {"style": "helmet", "grey": 0.3, "recede": 0.2},
    "brows": {"thick": 1.45, "arch": 0.6, "angle": 0.35, "count": 2600, "hair_len": 0.012},
    "beard": {"mustache": 1.0, "chin": 1.0, "cheeks": 0.0, "jaw": 1.0, "neck": 0.6, "sideburns": 1.0,
              "soul": 1.0, "tails": 1.0, "length": 0.10, "must_len": 0.045, "cheek_len": 0.03,
              "taper": 0.3, "gravity": 0.7, "radius": 0.00009, "count": 11000, "frizz": 0.0015},
    "beard_grey": 0.35,
    "outfit": {"kind": "armour", "silk": [0.20, 0.016, 0.012], "cape": [0.16, 0.012, 0.01]},
    "exposure": 0.1,
    "headgear": {"kind": "helmet"},
    "camera": {"yaw": 20.0, "pitch": -3.0, "head_frac": 0.42, "eye_line": 0.40},
    "bg": "smoke",
}

SCHOLAR = {
    "id": "hero_scholar", "seed": 5, "gender": "f", "age": 26, "archetype": "scholar",
    "expression": "serene", "expr": {"mouth-corner-puller": 0.1, "eyebrows-right-extern-up": 0.15,
                                     "eye-left-slit": 0.15, "eye-right-slit": 0.15},
    "face": {"eyes/{s}-eye-scale-decr|incr": 0.3, "eyes/{s}-eye-height2-decr|incr": -0.45,
             "head/head-oval": 0.7, "head/head-scale-horiz-decr|incr": -0.45, "head/head-scale-vert-decr|incr": 0.3,
             "chin/chin-width-decr|incr": -0.4, "chin/chin-height-decr|incr": 0.4,
             "nose/nose-scale-horiz-decr|incr": -0.3, "head/head-invertedtriangular": 0.45,
             "cheek/{s}-cheek-inner-decr|incr": -0.3, "eyes/{s}-eye-corner2-down|up": 0.4,
             "mouth/mouth-upperlip-volume-decr|incr": -0.35, "mouth/mouth-lowerlip-volume-decr|incr": -0.2,
             "mouth/mouth-scale-horiz-decr|incr": 0.1, "neck/neck-scale-horiz-decr|incr": -0.4,
             "neck/neck-scale-vert-decr|incr": -0.4, "forehead/forehead-scale-vert-decr|incr": -0.2},
    "identity": {"skin_tone": 0.28, "skin_red": 0.4, "makeup": 0.5, "muscle": 0.3, "weight": 0.4},
    "skin": {"huadian": True, "stubble": 0.0},
    "hair": {"style": "lady", "grey": 0.0, "recede": -0.5, "count": 12000, "bun": 0.045, "puff": 0.004,
             "side_puff": 0.013, "volume": 0.004, "physical": True, "clump": 0.55},
    "light": {"key": 40.0, "key_angle": 145.0, "key_elev": 16.0, "key_size": 0.6, "fill": 2.2, "bounce": 1.6, "rim": 50.0},
    "brows": {"thick": 0.85, "arch": 1.15, "angle": 0.1, "count": 1300, "hair_len": 0.008, "radius": 0.00005},
    "outfit": {"kind": "lady", "outer": [0.02, 0.08, 0.09], "mid": [0.32, 0.03, 0.04], "inner": [0.78, 0.74, 0.66],
               "motif": "roundels", "motif_rgb": [0.62, 0.48, 0.2], "band": [0.30, 0.03, 0.035],
               "band_thread": [0.7, 0.55, 0.25], "depth": 0.17, "shawl": True, "shawl_rgb": [0.78, 0.62, 0.5],
               "earrings": True},
    "headgear": {"kind": "pins", "petal": [0.75, 0.3, 0.35]},
    "camera": {"yaw": -14.0, "pitch": -1.0, "head_frac": 0.42, "eye_line": 0.42},
    "bg": "jade",
}

ELDER = {
    "id": "hero_elder", "seed": 37, "gender": "m", "age": 72, "archetype": "elder",
    "expression": "scheming", "expr": {"eye-left-slit": 0.12, "eye-right-slit": 0.18, "mouth-corner-puller": 0.1},
    "face": {"nose/nose-scale-vert-decr|incr": 0.2, "cheek/{s}-cheek-volume-decr|incr": -0.2,
             "eyes/{s}-eye-height2-decr|incr": -0.4, "eyes/{s}-eye-eyefold-down|up": -0.4},
    "identity": {"skin_tone": 0.45, "skin_red": 0.5},
    "skin": {"weather": 0.4},
    "hair": {"style": "topknot", "grey": 0.92, "recede": 0.45, "melanin": 0.9, "count": 9000, "bun": 0.022},
    "brows": {"thick": 1.2, "arch": 0.9, "angle": -0.1, "droop": 1.0, "count": 1200, "hair_len": 0.012,
              "grey_mul": 1.0},
    "beard": {"mustache": 1.0, "chin": 1.0, "cheeks": 0.3, "jaw": 1.0, "neck": 0.7, "sideburns": 1.0,
              "soul": 1.0, "tails": 1.0, "length": 0.2, "must_len": 0.06, "cheek_len": 0.05,
              "taper": 0.55, "gravity": 0.85, "radius": 0.00011, "count": 9000, "frizz": 0.0022,
              "clump": 0.6},
    "beard_grey": 0.95,
    "iris": 0.38,
    "outfit": {"kind": "sage", "outer": [0.02, 0.035, 0.075], "mid": [0.06, 0.05, 0.045], "inner": [0.7, 0.67, 0.6],
               "motif": "clouds", "motif_rgb": [0.10, 0.10, 0.13], "band": [0.6, 0.56, 0.48], "band_w": 0.05, "sheen": 0.12,
               "depth": 0.11},
    "headgear": {"kind": "guan", "rgb": [0.015, 0.013, 0.012], "pin_metal": False, "size": 1.25},
    "camera": {"yaw": 22.0, "pitch": -2.0, "head_frac": 0.40, "eye_line": 0.38},
    "bg": "warm",
}

HEROES = {"warlord": WARLORD, "scholar": SCHOLAR, "elder": ELDER}

if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "specs"), exist_ok=True)
    for k, v in HEROES.items():
        with open(os.path.join(HERE, "specs", "hero_%s.json" % k), "w") as f:
            json.dump(v, f, indent=1)
    print("wrote", list(HEROES))
