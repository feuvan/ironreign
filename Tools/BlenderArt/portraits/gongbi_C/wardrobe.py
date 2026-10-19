"""Cast generator for gongbi_C: portrait key -> character spec (pure python).

    wardrobe.generate("m_warrior_07")      # -> spec dict for stage3d / stage2d

The key's archetype gives the face canon, head/body build and costume family; if an officer in
the scenario uses that portrait, his or her record personalises it:

* age (startYear - birth)      -> wrinkles, eye bags, beard and hair colour (black / grizzled /
                                  grey / white), heavier lids
* martial / bravery            -> brow type and weight, the fierce glare (wider eyes, knitted brows)
* charm                        -> a faint smile, rouge
* faction                      -> mineral colours of cloak, robe and trim (DESIGN.md faction hues
                                  translated to pigments)
* specialty and bio keywords   -> steppe dress (左衽, fur hat), monk, physician, sword sect,
                                  prince, merchant, outlaw headband ...

Everything else is drawn from a seeded RNG (the key), inside the canon limits, so each of the
102 portraits is distinct and re-renders identically.
"""

import copy
import json
import os
import random
import zlib

import canon

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
SCENARIO = os.path.join(REPO, "Content", "Data", "Scenarios", "BrokenMandate.json")

#: faction -> (main pigment, accent, trim)
FACTION = {
    "iron_banner": ("cinnabar", "#2E2A28", "gold"),
    "wolf_riders": ("ochre", "#6E4A32", "#C9A24B"),
    "azure_court": ("azurite", "#E8DCC4", "gold"),
    "sea_league": ("teal", "#2B5C8A", "#C9A24B"),
    "southern_lotus": ("rouge", "malachite", "gold"),
    "black_mountain": ("#3A3A44", "cinnabar", "#8E98A0"),
    None: ("#7A6A54", "#4A443C", "#B8A27A"),
}
ROBES = ["azurite", "malachite", "indigo", "#6E3A52", "ochre", "teal", "#5E7468", "#7A5A3E",
         "#3E4E5E", "cinnabar", "#8E2E3E", "#4A5A3A"]
ARMOUR = [("#6A7884", "#2A323A"), ("#7A6A4A", "#3A2E1E"), ("#3E3A3A", "#141212"), ("#5E7080", "#27303A"),
          ("#8A5A3A", "#3A2416")]

#: eye types: almond 杏眼, phoenix 丹凤眼, round 环眼, calm 睡凤眼
EYE_TYPES = {
    "almond": dict(eye_h=0.38, eye_peak=0.42, eye_low=0.56, tail=0.0016, tail_rise=0.0006, lid_fold=0.0021),
    "phoenix": dict(eye_h=0.33, eye_peak=0.36, eye_low=0.60, tail=0.0034, tail_rise=0.0013, lid_fold=0.0,
                    eye_tilt=0.0026),
    "round": dict(eye_h=0.44, eye_peak=0.50, eye_low=0.50, tail=0.0008, tail_rise=0.0, lid_fold=0.0024,
                  iris=0.40),
    "calm": dict(eye_h=0.31, eye_peak=0.42, eye_low=0.55, tail=0.0018, tail_rise=0.0004, lid_fold=0.0016,
                 hood=0.3),
}
EYES = {"m_warrior": ["round", "phoenix", "almond", "round"], "m_scholar": ["phoenix", "almond", "calm"],
        "m_elder": ["calm", "phoenix", "almond"], "m_monk": ["calm", "almond"],
        "m_rogue": ["round", "almond", "phoenix"], "f_warrior": ["phoenix", "almond"],
        "f_scholar": ["almond", "phoenix"], "f_elder": ["calm", "almond"]}

_OFFICERS = None


def officers():
    global _OFFICERS
    if _OFFICERS is None:
        try:
            d = json.load(open(SCENARIO))
            sy = d.get("startYear", 212)
            _OFFICERS = {o["portrait"]: dict(o, age=sy - o.get("birth", sy - 35)) for o in d["officers"]}
        except (OSError, ValueError, KeyError):
            _OFFICERS = {}
    return _OFFICERS


def _has(o, *words):
    t = (o.get("bio", "") + " " + o.get("epithet", "")).lower()
    return any(w in t for w in words)


def generate(key):
    if key == "unknown":
        spec = generate("m_scholar_00")
        spec.update(silhouette=True, headgear=dict(kind="futou"), pose=dict(yaw=18.0, pitch=-2.0))
        spec["face"]["beard"] = None
        return spec
    arch = key.rsplit("_", 1)[0] if key[-1].isdigit() else key
    if arch not in canon.ARCH:
        arch = "m_scholar"
    rng = random.Random(zlib.crc32(key.encode()))
    o = officers().get(key, {})
    female = arch.startswith("f_")
    default_age = {"m_warrior": 34, "m_scholar": 36, "m_elder": 64, "m_monk": 45, "m_rogue": 32,
                   "f_warrior": 23, "f_scholar": 26, "f_elder": 58}[arch]
    age = o.get("age", default_age + rng.randint(-8, 8))
    martial = o.get("martial", 50 + rng.randint(-20, 30))
    bravery = o.get("bravery", 50 + rng.randint(-20, 30))
    charm = o.get("charm", 50 + rng.randint(-15, 30))
    fac = o.get("faction") if o else rng.choice(list(FACTION))
    main, accent, trim = FACTION.get(fac, FACTION[None])
    steppe = fac == "wolf_riders" or _has(o, "steppe", "khan", "clans", "nomad")
    monk = arch == "m_monk" or _has(o, "abbot", "monastery", "monk")
    sect = _has(o, "sect", "disciple", "sword", "knight-errant", "moonwell")
    prince = _has(o, "prince", "emperor's son", "ninth son")
    merchant = _has(o, "salt", "merchant", "caravan", "counting")
    outlaw = arch == "m_rogue" or _has(o, "outlaw", "brotherhood", "bandit", "smuggler")
    healer = _has(o, "physician", "healer")

    a = max(0.0, min(1.0, (age - 26) / 46.0))
    fierce = max(0.0, min(1.0, (max(martial, bravery) - 55) / 40.0)) * (0.4 if female else 1.0)
    over = {}
    # ---- face -----------------------------------------------------------------------------
    f = canon.face(arch)
    canon.vary(f, rng, 1.4)
    # feature types (人物画 manuals) drawn per character, inside the archetype's range
    eye_t = rng.choice(EYES[arch])
    f.update(EYE_TYPES[eye_t])
    f["eye_w"] += rng.uniform(-0.001, 0.0012)
    canon.enforce(f)
    f["age"] = max(f["age"], a) if arch in ("m_elder", "f_elder") else a
    f["fierce"] = fierce if arch in ("m_warrior", "m_rogue", "f_warrior") else fierce * 0.4
    f["bag"] = max(f["bag"], 0.6 * max(0.0, a - 0.35))
    f["hood"] = max(f["hood"], 0.8 * max(0.0, a - 0.55))
    f["smile"] = max(0.0, (charm - 70) / 40.0) * 0.6
    f["mouth_curve"] += 0.0006 * f["smile"] - 0.0008 * f["fierce"]
    if not female:
        if martial > 85 and rng.random() < 0.5:
            f["brow"] = "silkworm"
        if fierce > 0.5:
            f["brow_knit"] = 0.0012 + 0.0012 * fierce
            f["eye_h"] = min(0.46, f["eye_h"] + 0.04 * fierce)
            f["iris"] = max(0.37, f["iris"] - 0.02 * fierce)
            f["lid_w"] += 0.3 * fierce
            f["brow_w"] = tuple(w * (1.0 + 0.35 * fierce) for w in f["brow_w"])
        beard_col = "black" if age < 40 else "grizzled" if age < 55 else "grey" if age < 64 else "white"
        f["brow_color"] = {"black": "ink", "grizzled": "grizzled", "grey": "grey", "white": "white"}[beard_col]
        kinds = {"m_warrior": ["short_full", "short_full", "curly", "goatee", "five_lock", "stubble"],
                 "m_scholar": ["goatee", "goatee", "five_lock", "none", "stubble"],
                 "m_elder": ["five_lock", "five_lock", "goatee", "short_full"],
                 "m_monk": ["none"], "m_rogue": ["stubble", "curly", "short_full", "goatee"]}[arch]
        kind = rng.choice(kinds)
        if age < 22:
            kind = "none"
        f["beard"] = None if kind == "none" else dict(kind=kind, color=beard_col,
                                                      length=rng.uniform(0.85, 1.3), density=1.0)
        if f["brow"] == "longevity" and age < 58:
            f["brow"] = "calm"
    else:
        f["huadian"] = rng.choice([None, "#C0362C", "#C9A24B"]) if arch == "f_scholar" else None
        if age > 45:
            f["brow_color"] = "grey"
    # ---- head, body, skin ------------------------------------------------------------------
    head = copy.deepcopy(canon.HEAD[arch])
    for k, s in canon.HEAD_JITTER.items():
        head[k] = head.get(k, 1.0) + rng.uniform(-s, s)
    body = copy.deepcopy(canon.BODY[arch])
    skin = {"m_warrior": "weathered", "m_scholar": "peach", "m_elder": "elder", "m_monk": "warm",
            "m_rogue": "weathered", "f_warrior": "peach", "f_scholar": "ivory", "f_elder": "ivory"}[arch]
    if steppe:
        skin = "bronze"
    # ---- hair and headgear ---------------------------------------------------------------------
    hair_col = "hair" if age < 48 else ("grey" if age < 62 else "white")
    hairline = dict(f["hairline"])
    hairline["color"] = hair_col
    f["hairline"] = hairline
    if female:
        if arch == "f_scholar" or prince:
            hair = dict(style="lady_high", color=hair_col, crown=0.004, thick=0.0045,
                        ornaments=dict(comb=rng.random() < 0.7, buyao=rng.random() < 0.6,
                                       peony=rng.random() < 0.5, peony_color=rng.choice(["rouge", "#E7B9B0", "cinnabar"]),
                                       peony_side=rng.choice([-1, 1]),
                                       pins=[(rng.choice([-1, 1]), rng.uniform(-0.6, 0.8)) for _ in range(rng.randint(1, 3))]))
            gear = {}
        else:
            hair = dict(style="bun_low" if arch == "f_elder" or rng.random() < 0.3 else "lady_high",
                        color=hair_col, crown=0.004, thick=0.0045,
                        ornaments=dict(comb=False, buyao=False, peony=False, pins=[(1, 0.4)]))
            gear = dict(kind="headband", color=rng.choice([main, "cinnabar", "white"])) \
                if arch == "f_warrior" and rng.random() < 0.6 else {}
    else:
        hair = dict(style="topknot", color=hair_col)
        if arch in ("m_warrior",):
            gear = dict(kind="helmet", plume=rng.choice(["cinnabar", "cinnabar", "#2E2A28", "white"])) \
                if rng.random() < 0.65 else dict(kind="headband", color=main)
        elif arch == "m_scholar":
            gear = rng.choice([dict(kind="crown"), dict(kind="futou"), dict(kind="dongpo")])
            if prince:
                gear = dict(kind="crown", color="gold", pin="gold")
        elif arch == "m_elder":
            gear = rng.choice([dict(kind="dongpo"), dict(kind="crown", pin="jade"), dict(kind="futou")])
        elif arch == "m_rogue":
            gear = dict(kind="headband", color=rng.choice(["#2E2A28", "cinnabar", "#5A4A3A"]))
        else:
            gear = {}
        if monk:
            hair = dict(style="none")
            gear = {}
            f["hairline"] = dict(on=False)
        if steppe:
            gear = dict(kind="fur_hat", color=rng.choice(["#9A3A2A", "#6E4A32", "#2E3F5C"]))
            hair["crown"] = 0.0
    # ---- costume -----------------------------------------------------------------------------
    import specs
    robe_c = rng.choice(ROBES) if not (fac and rng.random() < 0.6) else main
    cos = dict(robe=dict(color=robe_c, folds=specs.robe_folds(rng.uniform(0.7, 1.1))))
    band_out = rng.choice(["#2A2420", "indigo_d", accent, "#22304A"])
    layers = [dict(color="white", band_w=0.012)]
    if rng.random() < 0.6:
        layers.append(dict(color=rng.choice(["cinnabar", "malachite", "azurite", "ochre"]), band_w=0.011))
    brocade = dict(kind=rng.choice(["lozenge", "dots", "cloud"]), motif=trim, edge=trim) \
        if (merchant or prince or arch == "f_scholar" or rng.random() < 0.35) else None
    layers.append(dict(color=band_out, band_w=rng.uniform(0.022, 0.032), brocade=brocade))
    cos["collar"] = specs.collar(layers, left=steppe)
    if arch in ("m_warrior", "f_warrior") and (gear.get("kind") == "helmet" or rng.random() < 0.5):
        ac, ad = rng.choice(ARMOUR)
        cos["armour"] = dict(color=ac, deep=ad, lace=rng.choice(["#A8382A", "#C9A24B", "#2B5C8A"]),
                             mirrors=rng.random() < 0.7, pauldrons=arch == "m_warrior" or rng.random() < 0.5)
        cos["robe"]["folds"] = []
        if rng.random() < 0.6:
            cos["cloak"] = dict(color=main if main not in ("#3A3A44",) else "cinnabar", collar=trim)
    if female and (arch == "f_scholar" or rng.random() < 0.4) and "armour" not in cos:
        cos["shawl"] = dict(color=rng.choice(["#A8CDB4", "#E8DCC4", "#C8B4D8", "#E7B9B0", "#9ABCD8"]),
                            motif="#F6F2E8")
    if merchant or prince:
        cos["robe"]["roundels"] = dict(color=trim if isinstance(trim, str) else "gold", alpha=0.4, period=0.07)
    if monk:
        cos["robe"]["color"] = rng.choice(["#B07A3A", "#8A5A2E", "#6E4A32"])
        cos["collar"] = specs.collar([dict(color="#E8DCC4", band_w=0.014), dict(color="#7A2A1E", band_w=0.04)])
        cos["beads"] = dict(color="#5A3020")
    if healer:
        cos["robe"]["color"] = rng.choice(["#E2D6BC", "#B8C8B0", "#9AA8B2"])
    pose = dict(yaw=rng.choice([-1, 1]) * rng.uniform(16, 26), pitch=-rng.uniform(1, 4),
                head_yaw=rng.uniform(-4, 4), head_pitch=rng.uniform(-3, 4), head_roll=rng.uniform(-2.5, 2.5))
    if arch == "f_scholar":
        hair_ears = True
    spec = dict(seed=zlib.crc32(key.encode()) & 0xFFFF, pose=pose, head=head, body=body, skin=skin,
                face=f, hair=hair, headgear=gear, costume=cos)
    if female and rng.random() < 0.7:
        spec["earrings"] = dict(kind=rng.choice(["pearl", "jade"]))
    if over:
        spec.update(over)
    return spec


def roster():
    """The 102 portrait keys by archetype + 'unknown' (DESIGN.md manifest)."""
    counts = dict(m_warrior=30, m_scholar=20, m_elder=12, m_monk=6, m_rogue=10, f_warrior=10,
                  f_scholar=10, f_elder=4)
    keys = ["%s_%02d" % (a, i) for a, n in counts.items() for i in range(1, n + 1)]
    return keys + ["unknown"]
