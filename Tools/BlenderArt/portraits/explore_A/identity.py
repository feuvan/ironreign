"""Identity sliders -> MakeHuman target weights, plus the archetype-driven random generator.

An :class:`Identity` is everything that makes one officer's *body and face* (not costume):
macro sliders, a dict of bipolar face modifiers (MakeHuman target pairs), expression units,
skin and hair pigment.  ``make_identity(seed, gender, age, archetype)`` draws a believable,
distinct East Asian adult from archetype priors, so 103 portraits come from 103 seeds.
"""

import random
from dataclasses import dataclass, field

import mh

# ------------------------------------------------------------------------------------------------
# Face modifiers we vary.  name -> (sigma for random draws).  "{s}" = both sides (symmetric);
# asymmetry is added separately with small per-side jitter.
FACE_MODS = {
    "head/head-age-decr|incr": 0.0,
    "head/head-angle-in|out": 0.0,
    "head/head-fat-decr|incr": 0.25,
    "head/head-scale-horiz-decr|incr": 0.18,
    "head/head-scale-vert-decr|incr": 0.15,
    "head/head-scale-depth-decr|incr": 0.15,
    "head/head-back-scale-depth-decr|incr": 0.2,
    "forehead/forehead-scale-vert-decr|incr": 0.3,
    "forehead/forehead-temple-decr|incr": 0.3,
    "forehead/forehead-trans-backward|forward": 0.25,
    "forehead/forehead-nubian-decr|incr": 0.25,
    "eyebrows/eyebrows-angle-down|up": 0.35,
    "eyebrows/eyebrows-trans-down|up": 0.25,
    "eyebrows/eyebrows-trans-backward|forward": 0.3,
    "eyes/{s}-eye-height1-decr|incr": 0.25,
    "eyes/{s}-eye-height2-decr|incr": 0.25,
    "eyes/{s}-eye-height3-decr|incr": 0.2,
    "eyes/{s}-eye-corner1-down|up": 0.3,
    "eyes/{s}-eye-corner2-down|up": 0.35,
    "eyes/{s}-eye-epicanthus-in|out": 0.25,
    "eyes/{s}-eye-eyefold-down|up": 0.3,
    "eyes/{s}-eye-eyefold-angle-down|up": 0.25,
    "eyes/{s}-eye-scale-decr|incr": 0.2,
    "eyes/{s}-eye-trans-in|out": 0.2,
    "eyes/{s}-eye-push1-in|out": 0.2,
    "eyes/{s}-eye-bag-decr|incr": 0.2,
    "nose/nose-trans-down|up": 0.25,
    "nose/nose-trans-backward|forward": 0.2,
    "nose/nose-scale-vert-decr|incr": 0.25,
    "nose/nose-scale-horiz-decr|incr": 0.25,
    "nose/nose-scale-depth-decr|incr": 0.25,
    "nose/nose-nostrils-width-decr|incr": 0.3,
    "nose/nose-point-width-decr|incr": 0.3,
    "nose/nose-hump-decr|incr": 0.3,
    "nose/nose-volume-decr|incr": 0.25,
    "nose/nose-width1-decr|incr": 0.25,
    "nose/nose-width2-decr|incr": 0.25,
    "nose/nose-flaring-decr|incr": 0.25,
    "nose/nose-curve-concave|convex": 0.25,
    "nose/nose-greek-decr|incr": 0.2,
    "mouth/mouth-scale-horiz-decr|incr": 0.25,
    "mouth/mouth-scale-vert-decr|incr": 0.2,
    "mouth/mouth-trans-down|up": 0.15,
    "mouth/mouth-upperlip-volume-decr|incr": 0.3,
    "mouth/mouth-lowerlip-volume-decr|incr": 0.3,
    "mouth/mouth-upperlip-width-decr|incr": 0.2,
    "mouth/mouth-cupidsbow-decr|incr": 0.3,
    "mouth/mouth-angles-down|up": 0.2,
    "mouth/mouth-philtrum-volume-decr|incr": 0.2,
    "mouth/mouth-laugh-lines-in|out": 0.0,
    "chin/chin-width-decr|incr": 0.3,
    "chin/chin-height-decr|incr": 0.25,
    "chin/chin-prominent-decr|incr": 0.3,
    "chin/chin-bones-decr|incr": 0.25,
    "chin/chin-jaw-drop-decr|incr": 0.2,
    "chin/chin-prognathism-decr|incr": 0.15,
    "cheek/{s}-cheek-bones-decr|incr": 0.3,
    "cheek/{s}-cheek-volume-decr|incr": 0.3,
    "cheek/{s}-cheek-inner-decr|incr": 0.25,
    "cheek/{s}-cheek-trans-down|up": 0.2,
    "ears/{s}-ear-scale-decr|incr": 0.2,
    "ears/{s}-ear-wing-decr|incr": 0.3,
    "ears/{s}-ear-lobe-decr|incr": 0.3,
    "neck/neck-scale-horiz-decr|incr": 0.2,
    "neck/neck-scale-depth-decr|incr": 0.15,
}

HEAD_SHAPES = ["head/head-oval", "head/head-round", "head/head-square", "head/head-rectangular",
               "head/head-triangular", "head/head-invertedtriangular", "head/head-diamond"]

# expression units (asian set) - additive, 0..1
EXPR_UNITS = ["eyebrows-left-down", "eyebrows-right-down", "eyebrows-left-inner-up",
              "eyebrows-right-inner-up", "eyebrows-left-extern-up", "eyebrows-right-extern-up",
              "eyebrows-left-up", "eyebrows-right-up",
              "eye-left-slit", "eye-right-slit", "eye-left-opened-up", "eye-right-opened-up",
              "mouth-compression", "mouth-corner-puller", "mouth-depression", "mouth-elevation",
              "mouth-pursing", "mouth-retraction", "mouth-upward-retraction", "nose-compression",
              "neck-platysma"]

#: expressions are named recipes of units (values 0..1, scaled by intensity)
EXPRESSIONS = {
    "neutral": {},
    "stern": {"eyebrows-left-down": 0.6, "eyebrows-right-down": 0.6, "eye-left-slit": 0.05,
              "eye-right-slit": 0.05, "mouth-compression": 0.35, "mouth-depression": 0.25},
    "fierce": {"eyebrows-left-down": 0.9, "eyebrows-right-down": 0.9, "eye-left-slit": 0.12,
               "eye-right-slit": 0.12, "mouth-compression": 0.4, "nose-compression": 0.3,
               "mouth-depression": 0.2},
    "scheming": {"eyebrows-left-down": 0.25, "eyebrows-right-extern-up": 0.35, "eye-left-slit": 0.22,
                 "eye-right-slit": 0.12, "mouth-corner-puller": 0.22, "mouth-compression": 0.1},
    "serene": {"eye-left-slit": 0.08, "eye-right-slit": 0.08, "mouth-corner-puller": 0.12,
               "eyebrows-left-inner-up": 0.1, "eyebrows-right-inner-up": 0.1},
    "proud": {"eyebrows-left-extern-up": 0.2, "eyebrows-right-extern-up": 0.2, "eye-left-slit": 0.06,
              "eye-right-slit": 0.06, "mouth-compression": 0.2, "mouth-corner-puller": 0.06},
    "weary": {"eyebrows-left-inner-up": 0.35, "eyebrows-right-inner-up": 0.35, "eye-left-slit": 0.15,
              "eye-right-slit": 0.15, "mouth-depression": 0.3},
}


@dataclass
class Identity:
    gender: float = 1.0          # 0 female .. 1 male
    age: float = 35.0            # years
    muscle: float = 0.5
    weight: float = 0.5
    asian: float = 1.0
    caucasian: float = 0.0
    african: float = 0.0
    shape: dict = field(default_factory=dict)   # HEAD_SHAPES -> 0..1
    face: dict = field(default_factory=dict)    # FACE_MODS name -> -1..1
    asym: dict = field(default_factory=dict)    # per-side extra: name with l/r -> value
    expression: str = "neutral"
    expr_amount: float = 1.0
    expr_extra: dict = field(default_factory=dict)
    # pigments
    skin_tone: float = 0.5       # 0 pale porcelain .. 1 sun-darkened
    skin_red: float = 0.5        # flush / weathering
    hair_melanin: float = 0.95   # natural hair colour
    hair_grey: float = 0.0       # 0 .. 1 white
    beard_grey: float = None     # default = hair_grey (+ a bit)
    makeup: float = 0.0          # 0 none .. 1 court make-up (women)
    seed: int = 0

    @property
    def female(self):
        return self.gender < 0.5

    def target_weights(self, expression=True):
        """All MakeHuman target weights for this identity (``expression=False``: rest face)."""
        w = mh.macro_weights(self.gender, mh.age_slider(self.age), self.muscle, self.weight,
                             self.african, self.asian, self.caucasian)
        for k, v in self.shape.items():
            if v > 0:
                w[k] = w.get(k, 0.0) + v
        mods = dict(self.face)
        for k, v in mh.modifier_weights(mods).items():
            w[k] = w.get(k, 0.0) + v
        for k, v in mh.modifier_weights(self.asym).items():
            w[k] = w.get(k, 0.0) + v
        if not expression:
            return w
        units = {}
        for k, v in EXPRESSIONS.get(self.expression, {}).items():
            units[k] = units.get(k, 0.0) + v * self.expr_amount
        for k, v in self.expr_extra.items():
            units[k] = units.get(k, 0.0) + v
        for k, v in units.items():
            if v:
                w["expression/units/asian/%s" % k] = v
        return w


# ------------------------------------------------------------------------------------------------
ARCHETYPES = {
    # name: macro priors (muscle, weight), face biases, expression choices
    "warrior": dict(muscle=(0.72, 0.1), weight=(0.6, 0.08), skin_tone=(0.6, 0.12),
                    bias={"chin/chin-width-decr|incr": 0.35, "chin/chin-bones-decr|incr": 0.3,
                          "eyebrows/eyebrows-trans-down|up": -0.25,
                          "cheek/{s}-cheek-bones-decr|incr": 0.3, "neck/neck-scale-horiz-decr|incr": 0.45,
                          "nose/nose-scale-horiz-decr|incr": 0.15, "head/head-fat-decr|incr": 0.1,
                          "eyebrows/eyebrows-trans-backward|forward": 0.2},
                    shapes={"head/head-square": (0.35, 0.2), "head/head-rectangular": (0.2, 0.15)},
                    expressions=["stern", "fierce", "proud", "stern"]),
    "scholar": dict(muscle=(0.42, 0.06), weight=(0.45, 0.06), skin_tone=(0.38, 0.1),
                    bias={"head/head-scale-horiz-decr|incr": -0.1, "nose/nose-scale-horiz-decr|incr": -0.15,
                          "chin/chin-width-decr|incr": -0.15, "neck/neck-scale-horiz-decr|incr": -0.2},
                    shapes={"head/head-oval": (0.45, 0.2), "head/head-invertedtriangular": (0.15, 0.1)},
                    expressions=["serene", "scheming", "proud", "serene"]),
    "elder": dict(muscle=(0.45, 0.06), weight=(0.42, 0.08), skin_tone=(0.5, 0.12),
                  bias={"cheek/{s}-cheek-volume-decr|incr": -0.35, "eyes/{s}-eye-bag-decr|incr": 0.45,
                        "head/head-fat-decr|incr": -0.25, "forehead/forehead-temple-decr|incr": -0.3,
                        "chin/chin-bones-decr|incr": 0.15, "nose/nose-scale-vert-decr|incr": 0.15},
                  shapes={"head/head-oval": (0.3, 0.2), "head/head-rectangular": (0.2, 0.15)},
                  expressions=["serene", "weary", "stern", "scheming"]),
    "monk": dict(muscle=(0.65, 0.1), weight=(0.6, 0.1), skin_tone=(0.55, 0.1),
                 bias={"head/head-fat-decr|incr": 0.2}, shapes={"head/head-round": (0.4, 0.2)},
                 expressions=["serene", "stern"]),
    "rogue": dict(muscle=(0.62, 0.1), weight=(0.5, 0.1), skin_tone=(0.62, 0.12),
                  bias={"cheek/{s}-cheek-bones-decr|incr": 0.25, "chin/chin-bones-decr|incr": 0.2},
                  shapes={"head/head-diamond": (0.3, 0.2), "head/head-triangular": (0.15, 0.1)},
                  expressions=["scheming", "fierce", "proud"]),
}

FEMALE_BIAS = {"chin/chin-width-decr|incr": -0.25, "nose/nose-scale-horiz-decr|incr": -0.2,
               "nose/nose-volume-decr|incr": -0.25, "mouth/mouth-upperlip-volume-decr|incr": 0.15,
               "mouth/mouth-lowerlip-volume-decr|incr": 0.2, "eyes/{s}-eye-scale-decr|incr": 0.15,
               "eyebrows/eyebrows-trans-down|up": 0.1, "neck/neck-scale-horiz-decr|incr": -0.25,
               "cheek/{s}-cheek-volume-decr|incr": 0.2, "eyes/{s}-eye-corner2-down|up": 0.25}


def _g(rng, mu_sigma):
    mu, s = mu_sigma
    return rng.gauss(mu, s)


def make_identity(seed, gender="m", age=35, archetype="warrior", variety=1.0, **over):
    """Draw an identity.  ``gender`` 'm'/'f', ``age`` years, ``variety`` scales the face noise."""
    rng = random.Random(seed * 7919 + 17)
    a = ARCHETYPES[archetype]
    fem = gender == "f"
    idn = Identity(gender=0.0 if fem else 1.0, age=float(age), seed=seed)
    idn.muscle = min(0.95, max(0.15, _g(rng, a["muscle"]) - (0.15 if fem else 0.0)))
    idn.weight = min(0.85, max(0.25, _g(rng, a["weight"]) - (0.05 if fem else 0.0)))
    # mostly East Asian; a touch of variation in bone structure from the other macros
    idn.caucasian = max(0.0, rng.gauss(0.06, 0.06))
    idn.asian = 1.0
    face = {}
    for k, s in FACE_MODS.items():
        if s > 0:
            face[k] = max(-1.0, min(1.0, rng.gauss(0.0, s * variety)))
    for k, v in a["bias"].items():
        face[k] = face.get(k, 0.0) + v
    if fem:
        for k, v in FEMALE_BIAS.items():
            face[k] = face.get(k, 0.0) + v
    # open, readable eyes (the MakeHuman asian lids are heavy at portrait scale)
    eo = {"warrior": 1.0, "scholar": 0.8, "elder": 0.3, "monk": 0.5, "rogue": 0.8}.get(archetype, 0.8)
    for k, v in (("eyes/{s}-eye-height2-decr|incr", 0.55), ("eyes/{s}-eye-scale-decr|incr", 0.25),
                 ("eyes/{s}-eye-eyefold-down|up", 0.4), ("eyes/{s}-eye-bag-decr|incr", -0.35)):
        face[k] = face.get(k, 0.0) + v * (eo if v > 0 else 1.0)
    # age-driven shape
    old = max(0.0, (age - 40.0) / 35.0)
    face["head/head-age-decr|incr"] = min(1.0, max(-0.6, (age - 35.0) / 35.0))
    face["mouth/mouth-laugh-lines-in|out"] = min(1.0, 0.25 + 0.8 * old) * (0.6 if fem else 1.0)
    face["eyes/{s}-eye-bag-decr|incr"] = face.get("eyes/{s}-eye-bag-decr|incr", 0.0) + 0.5 * old
    idn.face = {k: max(-1.0, min(1.0, v)) for k, v in face.items()}
    idn.shape = {k: max(0.0, _g(rng, ms)) for k, ms in a.get("shapes", {}).items()}
    # mild asymmetry
    asym = {}
    for k in ("eyes/%s-eye-height2-decr|incr", "eyes/%s-eye-corner2-down|up", "cheek/%s-cheek-bones-decr|incr",
              "ears/%s-ear-rot-backward|forward"):
        side = rng.choice("lr")
        asym[k % side] = rng.gauss(0, 0.12 * variety)
    idn.asym = asym
    idn.expression = rng.choice(a["expressions"])
    idn.expr_amount = min(1.2, max(0.5, rng.gauss(0.85, 0.15)))
    idn.skin_tone = min(1.0, max(0.0, _g(rng, a["skin_tone"]) - (0.15 if fem else 0.0)))
    idn.skin_red = min(1.0, max(0.0, rng.gauss(0.45 + 0.2 * old, 0.12)))
    idn.hair_melanin = min(1.0, max(0.75, rng.gauss(0.93, 0.04)))
    idn.hair_grey = min(1.0, max(0.0, (age - 38.0) / 35.0 + rng.gauss(0, 0.1))) if age > 38 else 0.0
    idn.beard_grey = min(1.0, idn.hair_grey * 1.1 + 0.05) if idn.hair_grey > 0 else 0.0
    idn.makeup = (0.6 + 0.3 * rng.random()) if fem and age < 50 else 0.0
    for k, v in over.items():
        setattr(idn, k, v)
    return idn
