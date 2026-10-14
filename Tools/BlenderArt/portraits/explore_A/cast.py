"""Cast generator: scenario officers -> one portrait spec per portrait id (scaling to 103).

    python3 cast.py [out_dir]          writes specs/<id>.json + manifest_draft.json

Every id gets a deterministic seed; archetype, gender and age come from the id and from the
officer the scenario assigns to it (age = startYear - birth, clamped to 18..75); faction picks the
palette; keywords in the bio/epithet pick costume variants (steppe furs, monk robes, merchants'
brocade, physicians' plain linen, sword-sect white, admirals' sea blue...); stats pick the
expression (ambition/bravery -> fierce/stern, politics/charm -> serene/scheming).
Ids no officer uses (spares) are drawn from the archetype priors.
"""

import hashlib
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
SCENARIO = os.path.join(REPO, "Content", "Data", "Scenarios", "BrokenMandate.json")

IDS = ([("m_warrior_%02d" % i) for i in range(1, 31)] + [("m_scholar_%02d" % i) for i in range(1, 21)]
       + [("m_elder_%02d" % i) for i in range(1, 13)] + [("m_monk_%02d" % i) for i in range(1, 7)]
       + [("m_rogue_%02d" % i) for i in range(1, 11)] + [("f_warrior_%02d" % i) for i in range(1, 11)]
       + [("f_scholar_%02d" % i) for i in range(1, 11)] + [("f_elder_%02d" % i) for i in range(1, 5)])

# faction palettes (linear rgb): silk, accent band, metal trim, tassel, backdrop
PALETTE = {
    "iron_banner": dict(silk=(0.20, 0.016, 0.012), band=(0.05, 0.035, 0.03), trim=(0.62, 0.42, 0.16), tassel=(0.22, 0.008, 0.006), bg="smoke"),
    "wolf_riders": dict(silk=(0.18, 0.09, 0.03), band=(0.08, 0.05, 0.03), trim=(0.55, 0.40, 0.2), tassel=(0.25, 0.12, 0.03), bg="warm"),
    "azure_court": dict(silk=(0.02, 0.05, 0.16), band=(0.55, 0.42, 0.18), trim=(0.66, 0.5, 0.2), tassel=(0.03, 0.06, 0.2), bg="cool"),
    "sea_league": dict(silk=(0.015, 0.10, 0.10), band=(0.05, 0.05, 0.06), trim=(0.6, 0.6, 0.62), tassel=(0.02, 0.12, 0.12), bg="cool"),
    "southern_lotus": dict(silk=(0.04, 0.12, 0.05), band=(0.30, 0.03, 0.035), trim=(0.7, 0.52, 0.22), tassel=(0.2, 0.02, 0.03), bg="jade"),
    "black_mountain": dict(silk=(0.05, 0.05, 0.06), band=(0.16, 0.03, 0.02), trim=(0.35, 0.33, 0.32), tassel=(0.05, 0.05, 0.05), bg="smoke"),
    None: dict(silk=(0.12, 0.10, 0.07), band=(0.04, 0.035, 0.03), trim=(0.5, 0.42, 0.3), tassel=(0.15, 0.1, 0.05), bg="warm"),
}

KEYWORDS = {
    "steppe": ("steppe", "khan", "clan", "horse", "herds", "nomad", "mounted", "jade gate", "lance"),
    "monk": ("monk", "abbot", "monastery", "temple"),
    "merchant": ("merchant", "salt", "silk", "trader", "caravan", "fortune", "counting", "ledger"),
    "physician": ("physician", "healer", "medicine", "plague"),
    "sword": ("sword", "sect", "duel", "blade", "knight-errant"),
    "sea": ("fleet", "admiral", "galley", "sails", "pirates", "waves", "ships"),
    "outlaw": ("outlaw", "bandit", "smuggl", "thief", "mercenary", "assassin", "street"),
    "court": ("court", "chancellor", "minister", "prince", "palace", "imperial", "censor", "rites"),
    "scout": ("scout", "archer", "hunter", "bells"),
}


def _seed(pid):
    return int(hashlib.sha1(pid.encode()).hexdigest()[:8], 16) % 100000


def _tags(o):
    text = " ".join([o.get("bio", ""), o.get("epithet", "")]).lower()
    return {k for k, words in KEYWORDS.items() if any(w in text for w in words)}


def _expression(o, rng, arch):
    if not o:
        return None
    amb, brav = o.get("ambition", 50), o.get("bravery", 50)
    pol, cha, loy = o.get("politics", 50), o.get("charm", 50), o.get("loyalty", 80)
    if brav > 80 and amb > 70:
        return "fierce"
    if brav > 75:
        return "stern"
    if loy < 50 or (pol > 75 and amb > 70):
        return "scheming"
    if cha > 75 or pol > 75:
        return "serene"
    if arch == "elder":
        return rng.choice(["serene", "weary", "stern"])
    return rng.choice(["stern", "proud", "serene"])


def spec_for(pid, o=None, start_year=212):
    g = pid[0]
    arch = pid.split("_")[1]
    seed = _seed(pid)
    rng = random.Random(seed)
    if o:
        age = max(18, min(75, start_year - o["birth"]))
    else:
        age = {"warrior": rng.randint(22, 45), "scholar": rng.randint(22, 50), "elder": rng.randint(58, 75),
               "monk": rng.randint(25, 65), "rogue": rng.randint(20, 42)}[arch]
    tags = _tags(o) if o else set()
    fac = o.get("faction") if o else None
    pal = PALETTE.get(fac, PALETTE[None])
    base_arch = "elder" if arch == "elder" else ("warrior" if arch in ("warrior",) else arch)
    s = {"id": pid, "seed": seed, "gender": g, "age": age, "archetype": base_arch,
         "expression": _expression(o, rng, base_arch), "bg": pal["bg"],
         "notes": (o["name"] + ", " + o.get("epithet", "")) if o else "spare " + arch}
    grey = max(0.0, min(1.0, (age - 38) / 30.0 + rng.gauss(0, 0.08))) if age > 38 else 0.0
    s["hair"] = {"style": "topknot", "grey": round(grey, 2), "recede": round(0.1 + 0.4 * max(0, age - 45) / 30, 2)}
    s["skin"] = {"weather": 0.8 if arch in ("warrior", "rogue") else 0.2, "scars": []}
    if arch in ("warrior", "rogue") and rng.random() < 0.35:
        s["skin"]["scars"] = [[[round(rng.uniform(0.4, 0.8), 2), round(rng.uniform(0.2, 0.7), 2)],
                               [round(rng.uniform(0.8, 1.1), 2), round(rng.uniform(-0.6, 0.0), 2)]]]
    s["camera"] = {"yaw": rng.choice([20.0, 18.0, 22.0, -18.0, -20.0]), "pitch": -3.0, "head_frac": 0.42,
                   "eye_line": 0.39}
    # ---------------------------------------------------------------- facial hair (men)
    if g == "m" and arch != "monk":
        r = rng.random()
        if age < 24:
            beard = None
        elif age < 34:
            beard = "moustache" if r < 0.45 else ("goatee" if r < 0.8 else None)
        else:
            beard = "full" if r < 0.55 else ("goatee" if r < 0.85 else "moustache")
        if arch == "elder":
            beard = "long"
        if "steppe" in tags and beard:
            beard = "moustache" if rng.random() < 0.6 else beard
        s["beard"] = _beard(beard, age, rng)
        s["beard_grey"] = round(min(1.0, grey * 1.15 + (0.05 if grey else 0)), 2)
    # ---------------------------------------------------------------- costume
    if g == "m" and arch == "warrior" or (g == "f" and arch == "warrior"):
        s["outfit"] = {"kind": "armour", "silk": pal["silk"], "trim": pal["trim"]}
        helm = rng.random() < (0.6 if g == "m" else 0.25)
        s["headgear"] = {"kind": "helmet", "tassel": pal["tassel"], "trim": pal["trim"]} if helm else {"kind": "none"}
        if helm:
            s["hair"]["style"] = "helmet"
        if "steppe" in tags:
            s["outfit"]["fur"] = True
    elif arch in ("scholar", "elder") and g == "m":
        kind = "sage" if (arch == "elder" and rng.random() < 0.5) else "scholar"
        motif = rng.choice(["roundels", "clouds", "lattice"])
        s["outfit"] = {"kind": kind, "outer": pal["silk"] if "court" not in tags else (0.02, 0.05, 0.16),
                       "band": pal["band"], "motif": motif, "depth": 0.13}
        if "merchant" in tags:
            s["outfit"].update(outer=(0.18, 0.09, 0.02), motif="roundels", motif_rgb=(0.7, 0.5, 0.15))
        if "physician" in tags:
            s["outfit"].update(outer=(0.35, 0.33, 0.28), motif=None)
        s["headgear"] = {"kind": "guan", "rgb": (0.015, 0.013, 0.012), "size": 1.1}
    elif arch == "monk":
        s["hair"]["style"] = "bald"
        s["outfit"] = {"kind": "scholar", "outer": (0.32, 0.12, 0.02), "mid": (0.18, 0.1, 0.05), "band": (0.25, 0.08, 0.02),
                       "motif": None, "beads": True}
        s["headgear"] = {"kind": "none"}
    elif arch == "rogue":
        s["outfit"] = {"kind": "scholar", "outer": (0.06, 0.045, 0.03), "mid": (0.12, 0.1, 0.08), "band": (0.03, 0.025, 0.02),
                       "motif": None, "depth": 0.18, "fur": "outlaw" in tags and rng.random() < 0.5}
        s["headgear"] = {"kind": "none"}
    elif g == "f":
        s["hair"].update(style="lady", count=10000, bun=0.03 + 0.006 * rng.random(), puff=0.016)
        s["outfit"] = {"kind": "lady", "outer": pal["silk"], "mid": (0.32, 0.03, 0.04), "band": pal["band"],
                       "motif": rng.choice(["roundels", "clouds", "lattice"]), "earrings": arch != "elder",
                       "shawl": arch == "scholar" and rng.random() < 0.7}
        s["headgear"] = {"kind": "pins"}
        s["identity"] = {"makeup": 0.0 if arch == "elder" else round(0.6 + 0.3 * rng.random(), 2)}
        s["skin"]["huadian"] = arch == "scholar" and rng.random() < 0.5
    return s


def _beard(kind, age, rng):
    if kind is None:
        return None
    L = 0.06 + 0.002 * max(0, age - 30)
    base = {"mustache": 1.0, "soul": 0.8, "tails": 0.8, "gravity": 0.7, "radius": 0.0001, "frizz": 0.0014,
            "must_len": 0.035 + 0.01 * rng.random()}
    if kind == "moustache":
        base.update(chin=0.0, jaw=0.0, cheeks=0.0, neck=0.0, sideburns=0.0, soul=0.0, length=0.02, count=2500)
    elif kind == "goatee":
        base.update(chin=1.0, jaw=0.0, cheeks=0.0, neck=0.0, sideburns=0.0, length=L * 0.9, taper=0.5, count=4500)
    elif kind == "full":
        base.update(chin=1.0, jaw=1.0, cheeks=0.0, neck=0.6, sideburns=1.0, length=L, cheek_len=0.03, taper=0.3, count=9000)
    elif kind == "long":
        base.update(chin=1.0, jaw=1.0, cheeks=0.3, neck=0.7, sideburns=1.0, length=0.14 + 0.06 * rng.random(),
                    must_len=0.055, cheek_len=0.05, taper=0.55, gravity=0.85, count=9000, clump=0.6, frizz=0.002)
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in base.items()}


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "specs", "cast")
    os.makedirs(out, exist_ok=True)
    sc = json.load(open(SCENARIO))
    by_id = {o["portrait"]: o for o in sc["officers"]}
    manifest = []
    for pid in IDS:
        o = by_id.get(pid)
        s = spec_for(pid, o, sc.get("startYear", 212))
        with open(os.path.join(out, pid + ".json"), "w") as f:
            json.dump(s, f, indent=1)
        a = s["age"]
        manifest.append({"id": pid, "gender": s["gender"], "archetype": pid.split("_")[1],
                         "age": "young" if a < 30 else ("adult" if a < 55 else "old"), "notes": s["notes"]})
    with open(os.path.join(out, "manifest_draft.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print("wrote %d specs to %s" % (len(IDS), out))


if __name__ == "__main__":
    main()
