"""Archetype generators: (archetype, index) -> a distinct Character, deterministic per seed.

Every face is sampled inside the canon ranges of its archetype (no ethnic morphs exist in this
system at all: faces are built only from the classical figure-painting vocabulary), then the
hair, beard, headgear, costume and palette are chosen from the archetype's wardrobe.  Officer
data (age from birth year, faction colour) can steer the choice.

Archetypes (DESIGN.md portrait keys): m_warrior x30, m_scholar x20, m_elder x12, m_monk x6,
m_rogue x10, f_warrior x10, f_scholar x10, f_elder x4.
"""

import zlib

import numpy as np

from face import FaceSpec
from portrait import Character

ARCHETYPES = {"m_warrior": 30, "m_scholar": 20, "m_elder": 12, "m_monk": 6, "m_rogue": 10,
              "f_warrior": 10, "f_scholar": 10, "f_elder": 4}

SKIN_M = ["#e9c8ae", "#e3bea2", "#dcb497", "#d6a68d", "#cf9f86", "#e6c3ab"]
SKIN_F = ["#f4dccc", "#f2d8c6", "#f5e0d2", "#efd3c0"]
SKIN_OLD = ["#ecd3bd", "#e6cbb4", "#e9cdb9"]

ROBES = [  # (outer, outer collar, middle, middle collar)
    ("#56687c", "ink_d", "cinnabar", "cinnabar_l"),
    ("azurite", "#2c3e55", "white", "white"),
    ("malachite", "#24493c", "cream", "gold"),
    ("purple", "#3a2440", "white", "cream"),
    ("ochre_robe", "#5a3326", "cinnabar", "cinnabar_l"),
    ("#7a2a28", "#3b1512", "cream", "gold"),
    ("indigo", "#1e2a3a", "azurite_p", "white"),
    ("tea", "#3a2a1a", "white", "white"),
    ("#8a8f7a", "ink_d", "white", "white"),
    ("malachite_l", "#2f5a4a", "cinnabar", "gold"),
]
METALS = ["#50627a", "#5a6470", "#6a5a4a", "#4a5a52", "#7a6a40"]
PLUMES = ["cinnabar", "carmine", "#2c3e55", "white", "#b38a2a"]
LADY_ROBES = [
    ("azurite", "#2c3e55", "cinnabar", "cinnabar_l"),
    ("#b5374a", "#5a1a24", "white", "gold"),
    ("malachite_l", "#2f5a4a", "#e8a0a8", "white"),
    ("purple_l", "#4a2a50", "cream", "gold"),
    ("#e6c27a", "#8a5a2a", "cinnabar", "white"),
    ("#9db8cf", "#2c3e55", "#d77a8a", "white"),
]


def _rng(arch, idx, salt=0):
    return np.random.default_rng(zlib.crc32(("%s/%d/%d" % (arch, idx, salt)).encode()))


def _u(r, a, b):
    return float(r.uniform(a, b))


def _pick(r, seq):
    return seq[int(r.integers(len(seq)))]


def _robes(r, table, inner_white=True, crosses=(1.24, 1.34, 1.46)):
    outer, ocol, mid, mcol = _pick(r, table)
    layers = []
    if inner_white:
        layers.append(dict(color="white", collar="white", cross_y=crosses[0], neck_u=0.40, cw=0.035))
    layers.append(dict(color=mid, collar=mcol, cross_y=crosses[1], neck_u=0.50, cw=0.05,
                       pattern=_pick(r, [None, "gold_dots"])))
    layers.append(dict(color=outer, collar=ocol, cross_y=crosses[2], neck_u=0.63,
                       cw=_u(r, 0.07, 0.11), pattern=_pick(r, [None, None, "cloud", "gold_dots"])))
    return layers


def male_face(r, age, kind):
    yaw = _u(r, 14, 24) * (1 if r.uniform() < 0.5 else -1)
    eye = {"warrior": _pick(r, ["fierce", "fierce", "phoenix"]),
           "scholar": _pick(r, ["phoenix", "phoenix", "almond"]),
           "elder": "elder", "monk": _pick(r, ["elder", "phoenix"]),
           "rogue": _pick(r, ["fierce", "almond"])}[kind]
    brow = {"warrior": _pick(r, ["sword", "silkworm", "sword"]),
            "scholar": _pick(r, ["sword", "silkworm"]),
            "elder": "longevity", "monk": _pick(r, ["longevity", "sword"]),
            "rogue": _pick(r, ["sword", "silkworm"])}[kind]
    old = max(0.0, (age - 40) / 35.0)
    skin = _pick(r, SKIN_OLD if age > 60 else SKIN_M)
    return FaceSpec(
        sex="m", age=age, yaw=yaw, skin=skin, shade_k=_u(r, 0.9, 1.35), rouge_k=_u(r, 0.3, 0.6),
        white_k=_u(r, 0.3, 0.6), line_w=_u(r, 0.95, 1.1), eye=eye,
        eye_h=_u(r, 0.27, 0.34), eye_tilt=_u(r, -0.01, 0.09), eye_w=_u(r, 0.122, 0.132),
        iris=_u(r, 0.44, 0.48), gaze=(_u(r, 0.3, 0.8), 0.0), tail=_u(r, 0.0, 0.08),
        crease=_u(r, 0.5, 0.9), brow=brow, brow_th=_u(r, 0.024, 0.036),
        brow_lift=_u(r, 0.0, 0.045), brow_knit=_u(r, -0.3, 1.2) if kind in ("warrior", "rogue") else _u(r, -0.3, 0.4),
        brow_grey=min(1.0, old * 1.1) if old > 0.3 else 0.0, brow_y=_u(r, 0.415, 0.430),
        nose_tip=_u(r, 0.085, 0.11), nose_w=_u(r, 0.054, 0.066), mouth_w=_u(r, 0.16, 0.185),
        lip_up=_u(r, 0.014, 0.02), lip_lo=_u(r, 0.02, 0.026), smile=_u(r, -0.6, 0.4),
        lip=_pick(r, ["#a55a4e", "#b8645a", "#a8584c"]), lip_k=_u(r, 0.6, 0.85),
        wrinkles=min(1.0, old * 1.2), frown=_u(r, 0, 1.0) if kind in ("warrior", "rogue") else 0.0,
        shape=dict(jaw=_u(r, 0.95, 1.12), chin=_u(r, 0.92, 1.12), width=_u(r, 0.96, 1.04),
                   cheekbone=_u(r, 0.8, 1.3), chin_fwd=_u(r, 0.9, 1.1)),
        seed=int(r.integers(1 << 20)))


def female_face(r, age, kind):
    yaw = _u(r, 14, 22) * (1 if r.uniform() < 0.5 else -1)
    old = max(0.0, (age - 40) / 35.0)
    return FaceSpec(
        sex="f", age=age, yaw=yaw, skin=_pick(r, SKIN_OLD if age > 55 else SKIN_F),
        shade="#c98a74", shade_k=_u(r, 0.7, 0.9) + 0.3 * old, rouge_k=_u(r, 0.9, 1.4) * (1 - 0.5 * old),
        white_k=0.8, line="ink_brown", line_w=0.8, eye=_pick(r, ["phoenix", "phoenix", "almond"]),
        eye_y=0.525, eye_h=_u(r, 0.28, 0.33), eye_tilt=_u(r, 0.06, 0.12), eye_w=_u(r, 0.126, 0.134),
        eye_gap=0.062, iris=_u(r, 0.46, 0.50), gaze=(_u(r, 0.3, 0.7), _u(r, 0, 0.6)),
        eye_rouge=_u(r, 0.5, 1.0) * (1 - old), crease=0.9, tail=_u(r, 0.12, 0.24), lower_lid=0.5,
        brow="willow", brow_y=_u(r, 0.412, 0.425), brow_len=_u(r, 0.16, 0.18), brow_th=_u(r, 0.019, 0.026),
        brow_lift=_u(r, 0.015, 0.04), nose_y=0.698, nose_tip=_u(r, 0.064, 0.074),
        nose_w=_u(r, 0.042, 0.048), bridge=0.3, mouth_y=0.788, mouth_w=_u(r, 0.12, 0.135),
        lip_up=_u(r, 0.018, 0.022), lip_lo=_u(r, 0.024, 0.030), smile=_u(r, 0.0, 0.35),
        lip=_pick(r, ["#c8323f", "#b8323c", "#c84a4a"]), lip_k=_u(r, 1.0, 1.3) * (1 - 0.4 * old),
        wrinkles=min(1.0, old), shape=dict(width=_u(r, 0.90, 0.95), jaw=_u(r, 0.92, 0.98),
                                          chin=_u(r, 0.78, 0.86), cheekbone=0.6, chin_fwd=0.85,
                                          round=1.0), seed=int(r.integers(1 << 20)))


def generate(arch, idx, officer=None):
    r = _rng(arch, idx)
    seed = int(r.integers(1 << 20))
    sex, kind = arch.split("_")
    age = {"warrior": _u(r, 24, 50), "scholar": _u(r, 22, 45), "elder": _u(r, 62, 80),
           "monk": _u(r, 30, 70), "rogue": _u(r, 22, 45)}[kind]
    if officer and officer.get("birth") is not None:
        age = max(18.0, 190 - officer["birth"])           # scenario starts ~190
    key = "%s_%02d" % (arch, idx + 1)
    if sex == "m":
        F = male_face(r, age, kind)
        grey = float(np.clip((age - 42) / 30.0, 0, 1))
        body = dict(shoulder=_u(r, 0.95, 1.1) if kind == "warrior" else _u(r, 0.88, 1.0),
                    neck_r=_u(r, 0.19, 0.23), yaw_k=0.9)
        beard = None
        bk = {"warrior": ["full", "full", "goatee", None], "scholar": ["goatee", "goatee", None],
              "elder": ["long"], "monk": [None, None, "goatee"],
              "rogue": ["stubble", "full", None]}[kind]
        b = _pick(r, bk)
        if b:
            beard = dict(kind=b, length={"full": _u(r, 0.18, 0.32), "goatee": _u(r, 0.15, 0.28),
                                         "long": _u(r, 0.45, 0.65), "stubble": 0.12}[b],
                         grey=grey, density=1.0, seed=seed)
        hair = dict(kind="male", grey=grey, bun=True, seed=seed)
        costume = {}
        headgear = None
        if kind == "warrior":
            metal = _pick(r, METALS)
            if r.uniform() < 0.7:
                headgear = dict(kind="helmet", metal=metal, trim="gold", plume=_pick(r, PLUMES),
                                rim_front=_u(r, 0.29, 0.32))
                hair["bun"] = False
            else:
                headgear = dict(kind="headband", color=_pick(r, ["cinnabar", "carmine", "ink_d"]))
            robe_col = _pick(r, ["cinnabar", "carmine", "azurite", "malachite", "ochre_robe"])
            costume = dict(
                cloak=dict(color=_pick(r, ["carmine", "#2c3e55", "#3a3a3a", "cinnabar"]), spread=0.2)
                if r.uniform() < 0.6 else None,
                robes=[dict(color=robe_col, collar=_pick(r, ["cinnabar_l", "gold", "cream"]),
                            cross_y=1.24, neck_u=0.45, cw=0.06, pattern="gold_dots")],
                armour=dict(cuirass=dict(color=metal, neck_y=1.08, neck_depth=0.14, neck_u=0.60,
                                         rows=int(r.integers(10, 14)), cols=int(r.integers(18, 26))),
                            mingguang=dict(u=0.36, y=1.56, r=0.125) if r.uniform() < 0.6 else None,
                            pauldron=dict(color=metal, rows=int(r.integers(3, 5)))))
            if costume["armour"]["mingguang"] is None:
                del costume["armour"]["mingguang"]
        elif kind == "monk":
            hair = dict(kind="bald")
            costume = dict(robes=[dict(color="white", collar="white", cross_y=1.24, neck_u=0.40, cw=0.035),
                                  dict(color=_pick(r, ["ochre_robe", "#b0662e", "tea", "#8a8f7a"]),
                                       collar="#5a3326", cross_y=1.44, neck_u=0.63, cw=0.09)],
                           necklace=dict(gold="leather", bead="#5a3326", pendant="#5a3326", y_c=1.45))
        elif kind == "rogue":
            headgear = dict(kind="headband", color=_pick(r, ["ink_d", "carmine", "#2c3e55", "tea"]))
            costume = dict(robes=_robes(r, ROBES[-4:] + [("leather", "#2a1c14", "cream", "cream")],
                                        inner_white=False))
        else:   # scholar / elder
            if r.uniform() < 0.45 or kind == "elder" and r.uniform() < 0.6:
                headgear = dict(kind="scholar_cap")
                hair["bun"] = False
            else:
                headgear = dict(kind="crown", color=_pick(r, ["gold", "#2a2420", "malachite_l"]))
            costume = dict(robes=_robes(r, ROBES))
        return Character(key=key, face=F, body=body, hair=hair, beard=beard, headgear=headgear,
                         costume={k: v for k, v in costume.items() if v is not None}, seed=seed)
    # ladies
    F = female_face(r, age if kind != "elder" else _u(r, 60, 75), kind)
    grey = float(np.clip((F.age - 45) / 25.0, 0, 1))
    hair_col = "hair" if grey < 0.3 else ("hair_grey" if grey < 0.8 else "#c9c4bc")
    hair = dict(kind="lady", tiers=int(r.integers(1, 3)), seed=seed, volume=0.04,
                puff=_u(r, 0.9, 1.3), color=hair_col,
                ornaments=dict(phoenix=kind == "scholar" and r.uniform() < 0.6,
                               flower=_pick(r, ["#d77a8a", "#e6a0b0", "#f0e0c0", None]),
                               pins=int(r.integers(1, 4)), comb=False,
                               crown=kind == "scholar" and r.uniform() < 0.4,
                               huadian=kind != "elder" and r.uniform() < 0.6))
    body = dict(shoulder=_u(r, 0.82, 0.9), neck_r=0.165, yaw_k=0.9)
    headgear = None
    if kind == "warrior":
        metal = _pick(r, METALS)
        headgear = dict(kind="headband", color=_pick(r, ["cinnabar", "carmine", "white"]))
        costume = dict(robes=[dict(color=_pick(r, ["cinnabar", "white", "azurite"]), collar="gold",
                                   cross_y=1.24, neck_u=0.42, cw=0.05)],
                       armour=dict(cuirass=dict(color=metal, neck_y=1.08, neck_depth=0.12, neck_u=0.55,
                                                rows=12, cols=22),
                                   pauldron=dict(color=metal, rows=3, size=0.9)),
                       cloak=dict(color=_pick(r, ["carmine", "white", "#2c3e55"]), spread=0.18))
    else:
        costume = dict(robes=_robes(r, LADY_ROBES if kind == "scholar" else ROBES[:3] + ROBES[7:8]),
                       shawl=dict(color=_pick(r, ["malachite_p", "azurite_p", "#f0d0d4", "cream"]),
                                  alpha=0.8) if kind == "scholar" else None,
                       necklace=dict() if kind == "scholar" and r.uniform() < 0.5 else None)
    return Character(key=key, face=F, body=body, hair=hair, beard=None, headgear=headgear,
                     costume={k: v for k, v in costume.items() if v is not None}, seed=seed)


def all_keys():
    return [(a, i) for a, n in ARCHETYPES.items() for i in range(n)]
