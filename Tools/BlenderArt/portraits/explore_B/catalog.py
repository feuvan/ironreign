"""Scaling approach B to the 103 portrait ids: id + scenario officer -> spec (no bpy).

Every portrait is a small *spec* derived from
  * its archetype template (warrior / scholar / elder / monk / rogue x gender x age band),
  * a deterministic per-id seed that jitters the MakeHuman face sliders (``identity.variant``),
    skin tone, groom lengths, costume palette and light angle by small amounts,
  * keywords from the assigned officer's epithet / bio (steppe, khan, prince, monk, merchant,
    outlaw, admiral, physician, assassin, sword sect ...) that switch outfit options,
  * the officer's faction (palette accents) and birth year (age).

    python3 -c "from explore_B import catalog; print(catalog.spec_for('m_warrior_07')['outfit'])"
"""

import copy
import hashlib
import json
import os
import random

from .identity import ARCH, wrinkle_default
from . import specs as S

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
SCENARIO = os.path.join(REPO, "Content", "Data", "Scenarios", "BrokenMandate.json")

COUNTS = dict(m_warrior=30, m_scholar=20, m_elder=12, m_monk=6, m_rogue=10, f_warrior=10,
              f_scholar=10, f_elder=4)

FACTION = {
    # accent colours for silk / lacing / trims (sRGB hex) - muted, never the raw UI faction colour
    "iron_banner": dict(silk="#5A1712", trim="#B08A3A", lacing="#6A1E14"),
    "wolf_riders": dict(silk="#5E4220", trim="#A88A50", lacing="#5A3A1A"),
    "azure_court": dict(silk="#1F3552", trim="#C9A24A", lacing="#22324E"),
    "sea_league": dict(silk="#1B4A4A", trim="#B89A5A", lacing="#1E3C3A"),
    "southern_lotus": dict(silk="#24564A", trim="#C9A24A", lacing="#3A4A2A"),
    "black_mountain": dict(silk="#2A2A30", trim="#7A6A48", lacing="#2A2018"),
    None: dict(silk="#4A3A2A", trim="#9A8050", lacing="#4A2A1A"),
}

KEYWORDS = {
    "steppe": ("steppe", "khan", "clan", "horse-lord", "herds", "jade gate", "nomad"),
    "prince": ("prince", "heir to the", "emperor's son"),
    "monk": ("monk", "abbot", "monastery"),
    "merchant": ("merchant", "salt", "silk", "caravan", "ledger", "counting", "trader", "accounts"),
    "outlaw": ("outlaw", "brotherhood", "thief", "smuggler", "mercenary", "street fighter"),
    "sword": ("sword sect", "swordswoman", "knight-errant", "duel"),
    "physician": ("physician", "healer", "medicine"),
    "naval": ("fleet", "admiral", "galley", "pirates", "sails"),
    "court": ("chancellor", "minister", "censor", "rites", "governor", "magistrate", "court"),
    "recluse": ("recluse", "hermit", "farms", "sage"),
}


def _seed(pid):
    return int(hashlib.sha1(pid.encode()).hexdigest()[:8], 16)


def officers_by_portrait():
    try:
        d = json.load(open(SCENARIO))
    except OSError:
        return {}
    return {o["portrait"]: o for o in d.get("officers", [])}


def all_ids():
    out = []
    for k, n in COUNTS.items():
        out += ["%s_%02d" % (k, i) for i in range(1, n + 1)]
    return out


def traits(officer):
    if not officer:
        return set()
    txt = (officer.get("epithet", "") + " " + officer.get("bio", "")).lower()
    return {k for k, words in KEYWORDS.items() if any(w in txt for w in words)}


def spec_for(pid, officer=None, start_year=211):
    officer = officer if officer is not None else officers_by_portrait().get(pid)
    rng = random.Random(_seed(pid))
    kind = pid.rsplit("_", 1)[0]
    gender, arch = kind.split("_")
    tr = traits(officer)
    fac = FACTION.get(officer.get("faction") if officer else None, FACTION[None])
    if officer and "birth" in officer:
        age = max(17, start_year - officer["birth"])
    else:
        age = dict(warrior=rng.randint(24, 48), scholar=rng.randint(22, 50), elder=rng.randint(60, 78),
                   monk=rng.randint(35, 70), rogue=rng.randint(22, 45))[arch]
    if arch == "elder":
        age = max(age, 58)
    if gender == "m" and arch in ("warrior", "rogue"):
        spec = copy.deepcopy(S.WARLORD)
    elif gender == "m" and arch in ("elder", "monk"):
        spec = copy.deepcopy(S.SAGE)
    elif gender == "f":
        spec = copy.deepcopy(S.SCHOLAR_F)
    else:
        spec = copy.deepcopy(S.SAGE)
    spec["name"] = pid
    spec["seed"] = _seed(pid) % 100000
    idn = spec["identity"]
    idn["age"] = age
    idn["wrinkles"] = wrinkle_default(age) if gender == "m" else 0.6 * wrinkle_default(age)
    # face: jitter the archetype preset (identity.variant does the same inside Blender)
    base = dict(ARCH["warlord" if arch in ("warrior", "rogue") else "sage" if age > 55 else "scholar_f"
                     if gender == "f" else "warlord"])
    if gender == "m" and arch == "scholar":
        base = {k: v * 0.4 for k, v in ARCH["warlord"].items()}
        base.update(head_oval=0.4, cheek_volume=-0.2, nose_width=-0.2)
    for k in list(base) + ["nose_hump", "nose_length", "mouth_width", "eye_scale", "chin_prominent",
                           "brow_angle", "ear_scale", "eye_fold_angle", "jaw_drop", "cheek_bones"]:
        base[k] = max(-1.0, min(1.0, base.get(k, 0.0) + rng.gauss(0, 0.28)))
    idn["sliders"] = base
    idn["skin_tone"] = min(1, max(0, idn.get("skin_tone", 0.5) + rng.gauss(0, 0.12)))
    idn["muscle"] = min(1, max(0, idn.get("muscle", 0.5) + rng.gauss(0, 0.12)))
    idn["weight"] = min(1, max(0, idn.get("weight", 0.5) + rng.gauss(0, 0.12)))
    idn["grey"] = max(0.0, min(1.0, (age - 38) / 30.0)) if gender == "m" else max(0.0, (age - 50) / 25.0)
    idn["frown"] = rng.choice([0.0, 0.2, 0.5, 0.8]) if arch in ("warrior", "rogue") else rng.choice([0.0, 0.2])
    g = spec["groom"]
    if gender == "m":
        style = rng.choice(["full", "full", "chin", "goatee", "none"]) if age > 27 else "none"
        if arch in ("elder",) or "recluse" in tr:
            style = "full"
        if arch == "monk":
            style = rng.choice(["none", "chin"])
            g.pop("scalp", None)                                       # shaved head
        if style == "none":
            g.pop("beard", None)
            idn["beard_shadow"] = 0.4
        else:
            g.setdefault("beard", {})
            g["beard"]["style"] = style
            g["beard"]["chin_len"] = (0.04 + 0.22 * rng.random()) * (1.6 if age > 60 else 1.0)
    # outfit options from traits / archetype
    o = spec["outfit"]
    if spec["outfit"]["builder"] == "warlord_armour":
        o["palette"] = dict(lacing=fac["lacing"])
        o["helmet"] = arch == "warrior" and rng.random() < 0.7 and "outlaw" not in tr
        o["fur"] = "steppe" in tr or rng.random() < 0.3
        o["mirror"] = rng.random() < 0.5
        o["robe"] = fac["silk"]
        o["trim"] = fac["trim"]
        if "outlaw" in tr or arch == "rogue":
            o["helmet"] = False
            o["lames"] = 2
    else:
        lay = o["layers"]
        lay[-1]["color"] = fac["silk"]
        lay[-1]["border"] = fac["trim"]
        if "monk" in tr or arch == "monk":
            lay[-1].update(color="#7A4A1E", band="#5A3014", pattern=None)       # ochre kasaya
            o["beads"] = dict(r=0.008, drop=0.2, hex="#3A2010", big_every=0)
            o["headwear"] = None
        elif "merchant" in tr:
            lay[-1].update(pattern="cloud", pattern_color="#C9A24A")
    spec["light"]["key_angle"] = spec["light"].get("key_angle", 150) + rng.uniform(-6, 6)
    spec["traits"] = sorted(tr)
    return spec


def manifest_entry(pid, officer=None):
    kind = pid.rsplit("_", 1)[0]
    gender, arch = kind.split("_")
    sp = spec_for(pid, officer)
    age = sp["identity"]["age"]
    band = "young" if age < 30 else "adult" if age < 55 else "old"
    note = (officer or {}).get("name", "") + (" - " + officer.get("epithet", "") if officer else "")
    return dict(id=pid, gender=gender, archetype=arch, age=band, notes=note.strip(" -") or "unassigned")
