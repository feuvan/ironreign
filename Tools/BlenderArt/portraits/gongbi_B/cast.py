"""Cast generator: portrait key -> a distinct Character, deterministic per key, steered by the
officer who uses the key in ``Content/Data/Scenarios/BrokenMandate.json``.

* age = scenario startYear (212) - birth: wrinkles, grey hair, beard length, brow colour
* faction: robe palette, armour palette / metal, cloak and scarf colours
* epithet / bio keywords: steppe khans and riders get a fur hat and fur-collared robe, abbots
  and monks a shaven head, kasaya and prayer beads, ...
* every face: a head-shape family of its archetype, an expression preset and a per-key
  variation of eye spacing / size, brow, nose and mouth (so two officers of one archetype are
  two different people), all inside the canon and checked by :func:`canon.check`

Faces are built only from the classical vocabulary; there is no ethnicity concept anywhere.
Hand-tuned heroes override their keys (:data:`HERO_KEYS`).

    python3 cast.py --keys            # the 103 keys
    python3 cast.py --check           # canon gate over all keys (exit 1 on any violation)
    python3 cast.py --check-drawn     # ... plus the drawn-eye gate (draws every face, ~5 min)
    python3 cast.py m_warrior_07 ...  # summary lines
"""

import json
import os
import sys
import zlib

import numpy as np

import canon
from face import FaceSpec
from portrait import Character

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
SCENARIO = os.path.join(REPO, "Content", "Data", "Scenarios", "BrokenMandate.json")

ARCHETYPES = {"m_warrior": 30, "m_scholar": 20, "m_elder": 12, "m_monk": 6, "m_rogue": 10,
              "f_warrior": 10, "f_scholar": 10, "f_elder": 4}

HERO_KEYS = {"m_warrior_01": "hero_warlord",     # Yan Tieshan, the Iron Mountain
             "f_scholar_04": "hero_scholar",     # Su Wanqing, the Lotus Poet
             "m_elder_03": "hero_elder"}         # Wen Tingjian, the Grand Chancellor

# warm skins only (粉 + 赭 + 胭脂 mixes): ivory, peach, warm, weathered ochre
SKIN_M = ["#ecd0b8", "#e9c8ae", "#e3bea2", "#dcb497", "#d8a98e", "#d2a387", "#e6c3ab"]
SKIN_F = ["#f4dccc", "#f3d8c4", "#f5e0d2", "#efd3c0", "#f1d6c2", "#eccdb4", "#f0d2bc"]
SKIN_OLD = ["#ecd3bd", "#e6cbb4", "#e9cdb9"]

# faction palettes: robe (outer, outer collar, middle, middle collar), armour, cloak, accents
FACTIONS = {
    "iron_banner": dict(
        robes=[("#7a2a28", "#3b1512", "cream", "gold"), ("cinnabar", "#5a1a14", "white", "white"),
               ("#3c3a3a", "ink_d", "cinnabar", "cinnabar_l"), ("#56687c", "ink_d", "cinnabar", "cinnabar_l")],
        armour=["steel", "black_lacquer", "azure_iron"], cloak=["carmine", "cinnabar", "#3a3a3a"],
        accent=["cinnabar", "gold"]),
    "wolf_riders": dict(
        robes=[("ochre_robe", "#5a3326", "cream", "gold"), ("tea", "#3a2a1a", "#2f7a62", "gold"),
               ("#7a5a36", "#3a2a16", "cinnabar", "gold"), ("#2f6a62", "#173a34", "cream", "gold")],
        armour=["bronze", "leather", "green_iron"], cloak=["#7a5a36", "#5a3326", "carmine"],
        accent=["gold", "#2f7457"], steppe=True),
    "azure_court": dict(
        robes=[("azurite", "#2c3e55", "white", "white"), ("indigo", "#1e2a3a", "azurite_p", "white"),
               ("#2e4e86", "#16264a", "cinnabar", "gold"), ("white", "#2c3e55", "azurite", "gold")],
        armour=["azure_iron", "steel"], cloak=["#2c3e55", "azurite", "white"],
        accent=["gold", "white"]),
    "sea_league": dict(
        robes=[("#1f6f6a", "#0f3a36", "white", "white"), ("malachite", "#24493c", "cream", "gold"),
               ("indigo", "#1e2a3a", "#9cc4ab", "white"), ("#2f7457", "#123a2a", "azurite_p", "gold")],
        armour=["green_iron", "steel"], cloak=["#1f6f6a", "#2c3e55"], accent=["white", "gold"]),
    "southern_lotus": dict(
        robes=[("malachite_l", "#2f5a4a", "#e8a0a8", "white"), ("#b5374a", "#5a1a24", "white", "gold"),
               ("malachite", "#24493c", "cinnabar", "gold"), ("#e6c27a", "#8a5a2a", "cinnabar", "white")],
        armour=["bronze", "red_lacquer"], cloak=["#4c7a3c", "carmine"], accent=["gold", "#e8a0a8"]),
    "black_mountain": dict(
        robes=[("#3c3a3a", "ink_d", "cream", "cream"), ("tea", "#3a2a1a", "white", "white"),
               ("indigo", "#1e2a3a", "tea", "cream"), ("#5a4a3a", "#2a1c14", "cinnabar", "cream")],
        armour=["leather", "black_lacquer"], cloak=["#3a3a3a", "#5a4a3a"], accent=["cinnabar", "cream"]),
    None: dict(
        robes=[("#56687c", "ink_d", "cinnabar", "cinnabar_l"), ("azurite", "#2c3e55", "white", "white"),
               ("malachite", "#24493c", "cream", "gold"), ("purple", "#3a2440", "white", "cream"),
               ("ochre_robe", "#5a3326", "cinnabar", "cinnabar_l"), ("#7a2a28", "#3b1512", "cream", "gold"),
               ("indigo", "#1e2a3a", "azurite_p", "white"), ("tea", "#3a2a1a", "white", "white"),
               ("#8a8f7a", "ink_d", "white", "white"), ("malachite_l", "#2f5a4a", "cinnabar", "gold")],
        armour=["azure_iron", "steel", "black_lacquer", "bronze", "green_iron", "red_lacquer"],
        cloak=["carmine", "#2c3e55", "#3a3a3a", "cinnabar"], accent=["gold", "cinnabar", "white"]),
}
LADY_ROBES = [
    ("azurite", "#2c3e55", "cinnabar", "cinnabar_l"), ("#b5374a", "#5a1a24", "white", "gold"),
    ("malachite_l", "#2f5a4a", "#e8a0a8", "white"), ("purple_l", "#4a2a50", "cream", "gold"),
    ("#e6c27a", "#8a5a2a", "cinnabar", "white"), ("#9db8cf", "#2c3e55", "#d77a8a", "white"),
]
PLUMES = ["cinnabar", "carmine", "#2c3e55", "white", "#b38a2a"]
MOTIFS = [None, None, "roundels", "flowers", "damask", "clouds"]

_OFFICERS = None


def scenario():
    """{portrait key: officer dict with '_age'} from the scenario (startYear - birth)."""
    global _OFFICERS
    if _OFFICERS is None:
        _OFFICERS = {}
        try:
            with open(SCENARIO) as f:
                d = json.load(f)
            y0 = int(d.get("startYear", 212))
            for o in d.get("officers", []):
                o = dict(o)
                if o.get("birth") is not None:
                    o["_age"] = y0 - int(o["birth"])
                _OFFICERS[o.get("portrait")] = o
        except (OSError, ValueError):
            pass
    return _OFFICERS


class Rng:
    def __init__(self, key, salt=0):
        self.g = np.random.default_rng(zlib.crc32(("%s/%d" % (key, salt)).encode()))

    def u(self, a, b):
        return float(self.g.uniform(a, b))

    def pick(self, seq):
        return seq[int(self.g.integers(len(seq)))]

    def chance(self, p):
        return bool(self.g.uniform() < p)

    def int(self, n):
        return int(self.g.integers(n))


def parse(key):
    arch, _, idx = key.rpartition("_")
    return arch, int(idx)


def all_keys():
    return ["%s_%02d" % (a, i + 1) for a, n in ARCHETYPES.items() for i in range(n)] + ["unknown"]


# ---------------------------------------------------------------------------------------------
# faces


def vary(F, r, fem):
    """Per-officer variation inside the canon: spacing, sizes, heights, angles."""
    F.eye_gap = r.u(0.058, 0.068)
    F.eye_y = F.eye_y + r.u(-0.012, 0.012)
    F.eye_w = r.u(0.124, 0.136) if not fem else r.u(0.124, 0.134)
    F.eye_tilt = F.eye_tilt + r.u(-0.02, 0.02)
    F.brow_y = F.brow_y + r.u(-0.010, 0.010)
    F.brow_len = r.u(0.155, 0.185)
    F.brow_gap = r.u(-0.006, 0.010)
    F.nose_y = F.nose_y + r.u(-0.012, 0.010)
    F.nose_w = F.nose_w * r.u(0.90, 1.12)
    F.nose_tip = F.nose_tip * r.u(0.90, 1.10)
    F.mouth_y = F.mouth_y + r.u(-0.010, 0.010)
    F.mouth_w = F.mouth_w * r.u(0.90, 1.10)
    F.lip_up = F.lip_up * r.u(0.85, 1.15)
    F.lip_lo = F.lip_lo * r.u(0.85, 1.15)


def male_face(r, age, arch, kind):
    old = float(np.clip((age - 38) / 32.0, 0, 1))
    yaw = r.u(14, 24) * (1 if r.chance(0.5) else -1)
    eye = {"warrior": r.pick(["fierce", "fierce", "phoenix", "almond"]),
           "scholar": r.pick(["phoenix", "phoenix", "almond"]),
           "elder": "elder", "monk": r.pick(["elder", "phoenix", "almond"]),
           "rogue": r.pick(["fierce", "almond", "phoenix"])}[kind]
    if age > 62:
        eye = "elder"
    brow = {"warrior": r.pick(["sword", "silkworm", "sword"]),
            "scholar": r.pick(["sword", "silkworm", "sword"]),
            "elder": "longevity", "monk": r.pick(["longevity", "sword", "silkworm"]),
            "rogue": r.pick(["sword", "silkworm"])}[kind]
    if age < 50 and brow == "longevity":
        brow = "sword"
    fam = canon.HEAD_FAMILIES[r.pick(canon.FAMILIES_BY_ARCH[arch])]
    shape = dict(fam)
    for k in ("width", "jaw", "chin"):
        shape[k] = shape.get(k, 1.0) * r.u(0.97, 1.03)
    shape["chin_fwd"] = r.u(0.9, 1.12)
    skin = r.pick(SKIN_OLD if age > 60 else SKIN_M)
    if kind in ("warrior", "rogue") and r.chance(0.4):
        skin = r.pick(["#d8a98e", "#d2a387", "#dcb497"])           # weathered
    F = FaceSpec(
        sex="m", age=age, yaw=yaw, skin=skin, shade_k=r.u(0.95, 1.35), rouge_k=r.u(0.3, 0.6),
        white_k=r.u(0.3, 0.6), line_w=r.u(0.95, 1.1), eye=eye,
        eye_h=r.u(0.32, 0.355) if eye != "elder" else r.u(0.32, 0.34), eye_tilt=r.u(0.0, 0.08),
        iris=r.u(0.46, 0.50), iris_tuck=r.u(0.24, 0.32), gaze=(r.u(0.40, 0.60), r.u(0.0, 0.3)),
        tail=r.u(0.0, 0.08) if eye == "phoenix" else 0.0, crease=r.u(0.5, 0.9), brow=brow,
        brow_th=r.u(0.024, 0.038), brow_lift=r.u(0.0, 0.045),
        brow_grey=min(1.0, old * 1.1) if old > 0.25 else 0.0, brow_y=r.u(0.415, 0.430),
        nose_tip=r.u(0.085, 0.11), nose_w=r.u(0.054, 0.068), mouth_w=r.u(0.155, 0.185),
        lip_up=r.u(0.014, 0.02), lip_lo=r.u(0.02, 0.027),
        lip=r.pick(["#a55a4e", "#b8645a", "#a8584c", "#b06055"]), lip_k=r.u(0.6, 0.85),
        wrinkles=min(1.0, old * 1.1), shape=shape, seed=r.int(1 << 20))
    vary(F, r, False)
    canon.apply_expression(F, r.pick(canon.EXPRESSIONS_BY_ARCH[arch]))
    return F


def female_face(r, age, arch, kind):
    old = float(np.clip((age - 40) / 30.0, 0, 1))
    yaw = r.u(14, 22) * (1 if r.chance(0.5) else -1)
    fam = canon.HEAD_FAMILIES[r.pick(canon.FAMILIES_BY_ARCH[arch])]
    shape = dict(fam)
    for k in ("width", "jaw", "chin"):
        shape[k] = shape.get(k, 1.0) * r.u(0.97, 1.03)
    eye = r.pick(["phoenix", "phoenix", "almond"]) if age < 55 else r.pick(["almond", "elder"])
    F = FaceSpec(
        sex="f", age=age, yaw=yaw, skin=r.pick(SKIN_OLD if age > 55 else SKIN_F),
        shade="#c98a74", shade_k=r.u(0.75, 0.95) + 0.3 * old, rouge_k=r.u(0.8, 1.35) * (1 - 0.5 * old),
        white_k=r.u(0.5, 0.7), line="ink_brown", line_w=0.8, eye=eye, eye_y=0.525,
        eye_h=r.u(0.32, 0.36), eye_tilt=r.u(0.05, 0.12) if eye == "phoenix" else r.u(0.01, 0.06),
        iris=r.u(0.42, 0.47), iris_tuck=r.u(0.26, 0.34), gaze=(r.u(0.42, 0.62), r.u(0.0, 0.4)),
        eye_rouge=r.u(0.4, 1.0) * (1 - old), crease=0.9,
        tail=r.u(0.10, 0.22) if eye == "phoenix" else r.u(0.04, 0.10), lower_lid=0.5,
        brow=r.pick(["willow", "willow", "crescent"]), brow_y=r.u(0.410, 0.428), brow_th=r.u(0.018, 0.027),
        brow_lift=r.u(0.015, 0.04), brow_grey=min(1.0, old * 1.2) if old > 0.4 else 0.0,
        nose_y=0.696, nose_tip=r.u(0.062, 0.074), nose_w=r.u(0.041, 0.049), bridge=0.3,
        mouth_y=0.783, mouth_w=r.u(0.110, 0.140), lip_up=r.u(0.016, 0.023),
        lip_lo=r.u(0.022, 0.032), lip=r.pick(["#c43a42", "#b8323c", "#c84a4a", "#c0404a"]),
        lip_k=r.u(0.95, 1.25) * (1 - 0.4 * old), wrinkles=min(1.0, old), shape=shape,
        seed=r.int(1 << 20))
    vary(F, r, True)
    canon.apply_expression(F, r.pick(canon.EXPRESSIONS_BY_ARCH[arch]))
    return F


# ---------------------------------------------------------------------------------------------
# wardrobe


def _robes(r, table, inner_white=True, crosses=(1.24, 1.34, 1.46), motif=None):
    outer, ocol, mid, mcol = r.pick(table)
    layers = []
    if inner_white:
        layers.append(dict(color="white", collar="white", cross_y=crosses[0], neck_u=0.40, cw=0.035))
    layers.append(dict(color=mid, collar=mcol, cross_y=crosses[1], neck_u=0.50, cw=0.05,
                       pattern=r.pick([None, "gold_dots"])))
    m = motif if motif is not None else r.pick(MOTIFS)
    pb = None
    if m:
        pb = dict(kind=m, color=r.pick(["gold", "gold", "white"]) if m != "damask" else None,
                  alpha=0.85 if m != "damask" else 0.42, size=r.u(0.040, 0.058),
                  period=r.u(0.27, 0.36), seed=r.int(100))
        if pb["color"] is None:
            del pb["color"]
        if m == "clouds":
            pb.update(color=r.pick(["gold", "white"]), alpha=0.6)
    layers.append(dict(color=outer, collar=ocol, cross_y=crosses[2], neck_u=0.63,
                       cw=r.u(0.07, 0.11), pattern=r.pick([None, None, "cloud", "gold_dots"]),
                       pattern_body=pb))
    return layers


def _keywords(off):
    txt = " ".join(str(off.get(k, "")) for k in ("epithet", "bio", "specialty")).lower()
    return txt


def generate(key, officer=None):
    """Character for a portrait key (hero override, else seeded from the key + officer)."""
    if key in HERO_KEYS:
        import characters
        ch = characters.HEROES[HERO_KEYS[key]]()
        ch.key = key
        ch.officer = (officer if officer is not None else scenario().get(key, {})).get("key")
        return ch
    arch, idx = parse(key)
    off = officer if officer is not None else scenario().get(key, {})
    r = Rng(key)
    sex, kind = arch.split("_")
    age = off.get("_age")
    if age is None:
        age = {"warrior": r.u(24, 50), "scholar": r.u(22, 45), "elder": r.u(58, 76),
               "monk": r.u(30, 66), "rogue": r.u(22, 45)}[kind]
    age = float(max(16, age))
    if kind == "elder":
        age = max(age, 52.0)
    fac = FACTIONS.get(off.get("faction"), FACTIONS[None])
    kw = _keywords(off)
    ep = str(off.get("epithet", "")).lower()
    steppe = any(w in ep for w in ("khan", "steppe", "wolf"))
    if fac.get("steppe"):
        steppe = steppe or r.chance(0.6)
    monk = kind == "monk" or "abbot" in kw
    if sex == "m":
        ch = _male(key, r, age, kind, arch, fac, steppe, monk, kw)
    else:
        ch = _female(key, r, age, kind, arch, fac, steppe, kw)
    ch.officer = off.get("key")
    if ch.officer in OVERRIDES:
        OVERRIDES[ch.officer](ch)
    return ch


# ---------------------------------------------------------------------------------------------
# named officers: small hand-tuned touches on top of the seeded character (the heroes above
# are fully hand-built)


def _helian_bo(ch):
    """the Grey Wolf Khan (42): weathered, grizzled full beard, wolf-fur hat, proud."""
    F = ch.face
    F.skin, F.eye, F.brow, F.brow_th = "#d2a387", "fierce", "silkworm", 0.036
    F.eye_h, F.iris = 0.34, 0.48
    canon.apply_expression(F, "proud")
    F.shape = dict(canon.HEAD_FAMILIES["square"], chin_fwd=1.05)
    ch.beard = dict(kind="full", length=0.26, grey=0.35, density=1.0, seed=ch.seed)
    ch.headgear = dict(kind="fur_hat", color="#7a5a36", fur="#8d8781", tassel="cinnabar")
    ch.hair.update(bun=False, grey=0.3)


def _liu_chengxuan(ch):
    """the Last Prince (19): gentle, earnest, fair; gold crown, azure robe with gold roundels."""
    F = ch.face
    F.skin, F.eye, F.brow, F.eye_h, F.iris = "#ecd0b8", "phoenix", "sword", 0.34, 0.47
    F.brow_th, F.wrinkles = 0.026, 0.0
    canon.apply_expression(F, "gentle")
    F.shape = dict(canon.HEAD_FAMILIES["oval"])
    ch.beard = None
    ch.headgear = dict(kind="crown", color="gold")
    ch.hair.update(bun=True, grey=0.0)
    ch.costume = dict(robes=[
        dict(color="white", collar="white", cross_y=1.24, neck_u=0.40, cw=0.035),
        dict(color="#e6c27a", collar="gold", cross_y=1.34, neck_u=0.50, cw=0.05, pattern="gold_dots"),
        dict(color="azurite", collar="#2c3e55", cross_y=1.46, neck_u=0.63, cw=0.10, pattern="cloud",
             pattern_body=dict(kind="roundels", color="gold", alpha=0.85, size=0.045, period=0.30))])


def _mo_xuan(ch):
    """the Black Tiger (36): outlaw chief, disgraced lieutenant; short black beard, black
    headband, leather armour, a confident direct look."""
    F = ch.face
    F.skin, F.eye, F.brow, F.brow_th, F.eye_h, F.iris = "#d2a387", "fierce", "silkworm", 0.036, 0.34, 0.48
    canon.apply_expression(F, "determined")
    ch.beard = dict(kind="full", length=0.18, grey=0.0, density=1.0, seed=ch.seed)
    ch.headgear = dict(kind="headband", color="ink_d")
    ch.costume = dict(
        robes=[dict(color="#3c3a3a", collar="cream", cross_y=1.24, neck_u=0.45, cw=0.06)],
        armour=dict(palette="leather", cuirass=dict(neck_y=1.08, neck_depth=0.14, neck_u=0.60),
                    pauldron=dict(rows=3), scarf=dict(color="#2a2520", knot=(-0.32, 1.24))),
        cloak=dict(color="#2a2a2a", spread=0.2))


def _shen_jiuling(ch):
    """the Salt King (52): merchant prince; round, shrewd and genial, grey goatee, teal robe
    with gold roundels, gold crown."""
    F = ch.face
    F.eye, F.brow, F.eye_h, F.iris = "phoenix", "sword", 0.33, 0.47
    canon.apply_expression(F, "confident")
    F.shape = dict(canon.HEAD_FAMILIES["round"])
    ch.beard = dict(kind="goatee", length=0.22, grey=0.45, density=1.0, seed=ch.seed)
    ch.headgear = dict(kind="crown", color="gold")
    ch.hair.update(bun=True, grey=0.45)
    ch.costume = dict(robes=[
        dict(color="white", collar="white", cross_y=1.24, neck_u=0.40, cw=0.035),
        dict(color="cream", collar="gold", cross_y=1.34, neck_u=0.50, cw=0.05),
        dict(color="#1f6f6a", collar="#0f3a36", cross_y=1.46, neck_u=0.63, cw=0.10, pattern="gold_dots",
             pattern_body=dict(kind="roundels", color="gold", alpha=0.9, size=0.05, period=0.29))])


OVERRIDES = {"helian_bo": _helian_bo, "liu_chengxuan": _liu_chengxuan, "mo_xuan": _mo_xuan,
             "shen_jiuling": _shen_jiuling}


def _male(key, r, age, kind, arch, fac, steppe, monk, kw):
    F = male_face(r, age, arch, kind)
    seed = r.int(1 << 20)
    grey = float(np.clip((age - 40) / 28.0, 0, 1))
    body = dict(shoulder=r.u(0.98, 1.1) if kind in ("warrior", "rogue") else r.u(0.88, 1.0),
                neck_r=r.u(0.19, 0.23), yaw_k=0.9)
    beard = None
    if age >= 24 and not monk:
        bk = {"warrior": ["full", "full", "goatee", "long" if age > 40 else "full", None],
              "scholar": ["goatee", "goatee", "long" if age > 38 else "goatee", None],
              "elder": ["long", "long", "full"], "monk": [None],
              "rogue": ["stubble", "full", "full", None]}[kind]
        b = r.pick(bk)
        if b:
            beard = dict(kind=b, length={"full": r.u(0.16, 0.24) + 0.10 * grey,
                                         "goatee": r.u(0.14, 0.22) + 0.08 * grey,
                                         "long": r.u(0.42, 0.62), "stubble": 0.12}[b],
                         grey=grey, density=1.0, seed=seed)
    elif monk and age > 50 and r.chance(0.5):
        beard = dict(kind="goatee", length=r.u(0.14, 0.24), grey=grey, density=0.8, seed=seed)
    hair = dict(kind="male", grey=grey, bun=True, seed=seed)
    costume, headgear = {}, None
    if monk:
        hair = dict(kind="bald")
        costume = dict(robes=[dict(color="white", collar="white", cross_y=1.24, neck_u=0.40, cw=0.035),
                              dict(color=r.pick(["ochre_robe", "#b0662e", "tea", "#8a8f7a"]),
                                   collar="#5a3326", cross_y=1.44, neck_u=0.63, cw=0.09)],
                       kasaya=dict(color=r.pick(["cinnabar", "#a8402a", "#b5372a", "ochre_robe"]),
                                   side=1 if r.chance(0.5) else -1),
                       mala=dict(bead=r.pick(["#5a3a26", "#3a2a20", "#7a4a2a"])))
    elif kind in ("warrior", "rogue"):
        armoured = kind == "warrior" or r.chance(0.35)
        palette = r.pick(fac["armour"]) if kind == "warrior" else "leather"
        if steppe:
            headgear = dict(kind="fur_hat", color=r.pick(["#7a5a36", "#2f6a62", "#8e2a22", "ochre_robe"]),
                            fur=r.pick(["#8a6a48", "#6a5a4a", "#a08a6a", "#4a3a30"]))
            hair["bun"] = False
        elif kind == "warrior" and r.chance(0.65):
            headgear = dict(kind="helmet", metal=r.pick(["#3f4c5c", "#50627a", "#5a6470", "#6a5a4a", "#4a5a52"]),
                            trim="gold", plume=r.pick(PLUMES), rim_front=r.u(0.29, 0.32),
                            guard_color=r.pick([None, "#2b2827", "#7a2a22"]))
            hair["bun"] = False
        else:
            headgear = dict(kind="headband", color=r.pick(fac["accent"] + ["ink_d", "carmine"]))
        robes = _robes(r, fac["robes"], inner_white=not armoured, motif=None if armoured else r.pick(MOTIFS))
        if steppe:
            robes[-1].update(collar=r.pick(["#8a6a48", "#6a5a4a", "#a08a6a"]), cw=0.12, pattern="fur")
        costume = dict(robes=robes)
        if armoured:
            costume = dict(
                robes=[dict(color=r.pick(fac["accent"] + ["cinnabar", "azurite", "malachite"]),
                            collar=r.pick(["cinnabar_l", "gold", "cream"]), cross_y=1.24,
                            neck_u=0.45, cw=0.06, pattern="gold_dots")],
                armour=dict(palette=palette,
                            cuirass=dict(neck_y=1.08, neck_depth=0.14, neck_u=0.60,
                                         scale=r.u(0.9, 1.15)),
                            pauldron=dict(rows=int(r.g.integers(3, 5))),
                            **({"mirror": dict(u=0.0, y=r.u(1.55, 1.65), r=r.u(0.10, 0.125))}
                               if r.chance(0.5) else {}),
                            **({"scarf": dict(knot=(r.u(0.25, 0.4) * r.pick([-1, 1]), 1.24))}
                               if r.chance(0.6) else {})))
            if r.chance(0.55):
                costume["cloak"] = dict(color=r.pick(fac["cloak"]), spread=0.2)
    else:   # scholar / elder
        if kind == "elder" and r.chance(0.6) or r.chance(0.35):
            headgear = dict(kind="scholar_cap")
            hair["bun"] = False
        elif steppe:
            headgear = dict(kind="fur_hat", color=r.pick(["#7a5a36", "#2f6a62"]),
                            fur=r.pick(["#8a6a48", "#6a5a4a"]))
            hair["bun"] = False
        else:
            headgear = dict(kind="crown", color=r.pick(["gold", "#2a2420", "malachite_l"]))
        costume = dict(robes=_robes(r, fac["robes"]))
    return Character(key=key, face=F, body=body, hair=hair, beard=beard, headgear=headgear,
                     costume={k: v for k, v in costume.items() if v is not None}, seed=seed)


def _female(key, r, age, kind, arch, fac, steppe, kw):
    if kind == "elder":
        age = max(age, 46.0)
    F = female_face(r, age, arch, kind)
    seed = r.int(1 << 20)
    grey = float(np.clip((F.age - 45) / 22.0, 0, 1))
    hair_col = "hair" if grey < 0.3 else ("hair_grey" if grey < 0.8 else "#c9c4bc")
    style = r.pick({"scholar": ["high", "tilted", "high", "double"],
                     "warrior": ["double", "high", "tilted"],
                     "elder": ["low", "high", "low"]}[kind])
    hair = dict(kind="lady", style=style, tiers=int(r.g.integers(1, 3)), seed=seed, volume=0.04,
                puff=r.u(0.85, 1.35), color=hair_col,
                ornaments=dict(phoenix=kind == "scholar" and r.chance(0.5),
                               flower=r.pick(["#d77a8a", "#e6a0b0", "#f0e0c0", None]),
                               pins=int(r.g.integers(1, 4)), comb=r.chance(0.3),
                               crown=kind == "scholar" and r.chance(0.35),
                               huadian=kind != "elder" and r.chance(0.6)))
    body = dict(shoulder=r.u(0.82, 0.9), neck_r=0.165, yaw_k=0.9)
    headgear = None
    if kind == "warrior":
        palette = r.pick(fac["armour"])
        headgear = dict(kind="headband", color=r.pick(["cinnabar", "carmine", "white"] + fac["accent"]))
        if steppe:
            headgear = dict(kind="fur_hat", color=r.pick(["#8e2a22", "#2f6a62"]), fur="#a08a6a")
            hair["style"] = "low"              # the hair is gathered low under the hat
        costume = dict(robes=[dict(color=r.pick(["cinnabar", "white", "azurite"]), collar="gold",
                                   cross_y=1.22, neck_y=1.05, neck_u=0.42, cw=0.05)],
                       armour=dict(palette=palette,
                                   cuirass=dict(neck_y=1.07, neck_depth=0.12, neck_u=0.55, scale=0.85),
                                   pauldron=dict(rows=3, size=0.9)),
                       cloak=dict(color=r.pick(fac["cloak"] + ["white"]), spread=0.18)
                       if r.chance(0.6) else None)
    else:
        table = LADY_ROBES + fac["robes"][:2] if kind == "scholar" else fac["robes"]
        robes = _robes(r, table, crosses=(1.18, 1.28, 1.42))
        for lay in robes:
            lay["neck_y"] = 1.05
        costume = dict(robes=robes,
                       shawl=dict(color=r.pick(["malachite_p", "azurite_p", "#f0d0d4", "cream"]),
                                  alpha=0.8) if kind == "scholar" and r.chance(0.7) else None,
                       necklace=dict() if kind == "scholar" and r.chance(0.5) else None)
    return Character(key=key, face=F, body=body, hair=hair, beard=None, headgear=headgear,
                     costume={k: v for k, v in costume.items() if v is not None}, seed=seed)


# ---------------------------------------------------------------------------------------------


def check_all(keys=None, drawn=True):
    bad = []
    for k in keys or all_keys():
        if k == "unknown":
            continue
        try:
            ch = generate(k)
            canon.check(ch)
            if drawn:
                import portrait
                cv, fd, T = portrait.draw(ch)
                canon.check_drawn(fd, k)
        except (AssertionError, ValueError) as e:
            bad.append("%s: %s" % (k, e))
    return bad


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["--keys"]:
        print(" ".join(all_keys()))
        sys.exit(0)
    if a and a[0] in ("--check", "--check-drawn"):
        bad = check_all(a[1:] or None, drawn=a[0] == "--check-drawn")
        for b in bad:
            print("FAIL", b)
        print("canon gate: %d keys checked, %d failures" % (len(a[1:] or all_keys()) - 1, len(bad)))
        sys.exit(1 if bad else 0)
    for k in a or all_keys():
        if k == "unknown":
            continue
        ch = generate(k)
        F = ch.face
        print("%-14s %-16s age %4.0f %-5s eye %-7s h%.2f brow %-9s skin %s hg %s" % (
            k, getattr(ch, "officer", None), F.age, F.sex, F.eye, F.eye_h, F.brow, F.skin,
            (ch.headgear or {}).get("kind")))
