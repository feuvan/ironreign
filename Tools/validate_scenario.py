#!/usr/bin/env python3
"""Validates an Iron Reign scenario file (docs/DESIGN.md section 7).

Usage:
    python3 Tools/validate_scenario.py [scenario.json ...] [--strict] [--summary]

With no file arguments every Content/Data/Scenarios/*.json is checked.
Errors break loading or the rules (unknown keys, bad enums, broken references...).
Warnings are content-guideline issues (balance ranges, missing flavour text...).
Exit code: 0 when clean, 1 on errors (or on warnings with --strict), 2 on bad usage.

Enum tables mirror Source/IronReign/Sim/IronTypes.cpp; keep them in sync.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "Content", "Data")

# ---- Enum tables (IronTypes.cpp) ----
STATS = ["martial", "command", "strategy", "politics", "charm"]
TROOP_TYPES = ["infantry", "cavalry", "archer"]
GENDERS = ["m", "f"]
STATUSES = ["serving", "free", "hidden", "prisoner", "dead", "unborn"]
TERRAINS = ["plains", "forest", "hills", "river", "mountains", "coast"]
ROAD_KINDS = ["road", "pass", "river"]
DUEL_MOVES = ["strike", "guard", "feint"]
EFFECT_TYPES = ["gold", "food", "troops", "order", "farm", "commerce", "defense", "population", "training",
                "loyalty", "loyaltyAll", "stat", "joinOfficer", "revealOfficer", "trust", "alliance", "truce",
                "sectFavor", "learnTechnique", "message"]
EVENT_CONTEXTS = ["random_player_city", "capital", "random_city"]

# ---- Asset ids (DESIGN.md section 8) ----
PORTRAIT_SETS = {"m_warrior": 30, "m_scholar": 20, "m_elder": 12, "m_monk": 6, "m_rogue": 10,
                 "f_warrior": 10, "f_scholar": 10, "f_elder": 4}
PORTRAIT_IDS = {"%s_%02d" % (prefix, i) for prefix, count in PORTRAIT_SETS.items() for i in range(1, count + 1)}
EVENT_IMAGES = {"Events/%s.png" % name for name in
                ["Court", "Battle", "Harvest", "Disaster", "Wanderer", "Sect", "Bandits", "Envoy", "Festival",
                 "Plague", "Flood", "Omen"]}
PLACEHOLDERS = {"city", "ruler", "faction", "officer"}

CITY_EFFECTS = {"gold", "food", "troops", "order", "farm", "commerce", "defense", "population", "training"}

# ---- Known fields (unknown fields are reported as warnings to catch typos) ----
TOP_FIELDS = {"format", "version", "key", "name", "description", "startYear", "startMonth", "map", "techniques",
              "factions", "cities", "roads", "officers", "sects", "relations", "events",
              # save-game only
              "session", "armies", "orders", "pendingEvents", "pendingPrisoners", "battleQueue", "log"}
TECHNIQUE_FIELDS = {"key", "name", "nameZh", "description", "kind", "power", "minMartial"}
FACTION_FIELDS = {"key", "name", "nameZh", "glyph", "color", "ruler", "capital", "alive"}
CITY_FIELDS = {"key", "name", "nameZh", "description", "x", "y", "size", "terrain", "owner", "population",
               "populationMax", "farm", "farmMax", "commerce", "commerceMax", "defense", "defenseMax", "order",
               "troops", "training", "gold", "food", "delegated"}
ROAD_FIELDS = {"a", "b", "days", "kind", "points"}
OFFICER_FIELDS = {"key", "name", "nameZh", "epithet", "bio", "rumor", "portrait", "gender", "birth", "appear",
                  "martial", "command", "strategy", "politics", "charm", "affinity", "ambition", "bravery",
                  "specialty", "status", "faction", "captor", "city", "army", "loyalty", "merit", "sect",
                  "techniques", "exp"}
SECT_FIELDS = {"key", "name", "nameZh", "description", "city", "master", "techniques", "favor"}
RELATION_FIELDS = {"a", "b", "trust", "alliance", "truce"}
EVENT_FIELDS = {"key", "title", "image", "text", "speaker", "world", "once", "context", "when", "effects",
                "choices", "fired"}
WHEN_FIELDS = {"minYear", "maxYear", "months", "chance", "ownsCity", "hasOfficer", "faction", "minCities",
               "maxCities"}
CHOICE_FIELDS = {"label", "gold", "effects"}
EFFECT_FIELDS = {"type", "amount", "city", "officer", "faction", "sect", "technique", "stat", "text"}

KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
CJK_PATTERN = re.compile(r"[㐀-鿿]")
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class Report:
    def __init__(self, path):
        self.path = path
        self.errors = []
        self.warnings = []

    def error(self, where, message):
        self.errors.append("%s: %s" % (where, message))

    def warn(self, where, message):
        self.warnings.append("%s: %s" % (where, message))


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def check_unknown(report, where, obj, allowed):
    for field in obj:
        if field not in allowed:
            report.warn(where, "unknown field '%s'" % field)


def check_int(report, where, obj, field, low, high, required=True, warn_only=False):
    """Checks obj[field] is an int in [low, high]. Returns the value or None."""
    if field not in obj:
        if required:
            report.error(where, "missing '%s'" % field)
        return None
    value = obj[field]
    if not is_int(value):
        report.error(where, "'%s' must be an integer (got %r)" % (field, value))
        return None
    if (low is not None and value < low) or (high is not None and value > high):
        message = "'%s' = %d outside %s..%s" % (field, value, low, high)
        if warn_only:
            report.warn(where, message)
        else:
            report.error(where, message)
    return value


def check_text(report, where, obj, field, required=True, warn_missing=False):
    value = obj.get(field)
    if value is None:
        if required:
            report.error(where, "missing '%s'" % field)
        elif warn_missing:
            report.warn(where, "missing '%s'" % field)
        return None
    if not isinstance(value, str):
        report.error(where, "'%s' must be a string" % field)
        return None
    if not value.strip():
        if required:
            report.error(where, "'%s' is empty" % field)
        elif warn_missing:
            report.warn(where, "'%s' is empty" % field)
    return value


def check_placeholders(report, where, text):
    for name in re.findall(r"\{([^{}]*)\}", text or ""):
        if name not in PLACEHOLDERS:
            report.error(where, "unknown placeholder {%s}" % name)


def collect_keys(report, section, items):
    keys = {}
    if not isinstance(items, list):
        report.error(section, "must be an array")
        return keys
    for index, item in enumerate(items):
        where = "%s[%d]" % (section, index)
        if not isinstance(item, dict):
            report.error(where, "must be an object")
            continue
        key = item.get("key")
        if not isinstance(key, str) or not key:
            report.error(where, "missing key")
            continue
        if not KEY_PATTERN.match(key):
            report.error(where, "key '%s' must be snake_case ascii" % key)
        if key in keys:
            report.error(where, "duplicate key '%s'" % key)
        keys[key] = item
    return keys


def validate(path, report, summary):
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        report.error(path, "cannot read: %s" % exc)
        return
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        report.error(path, "invalid JSON: %s" % exc)
        return
    if not isinstance(data, dict):
        report.error(path, "root must be an object")
        return

    check_unknown(report, "scenario", data, TOP_FIELDS)
    if data.get("format") != "ironreign":
        report.error("scenario", "format must be 'ironreign'")
    check_int(report, "scenario", data, "version", 1, None)
    check_text(report, "scenario", data, "key")
    check_text(report, "scenario", data, "name")
    check_text(report, "scenario", data, "description", required=False, warn_missing=True)
    start_year = check_int(report, "scenario", data, "startYear", 1, None) or 212
    check_int(report, "scenario", data, "startMonth", 1, 12, required=False)

    map_def = data.get("map", {})
    map_w = map_def.get("width", 2400) if isinstance(map_def, dict) else 2400
    map_h = map_def.get("height", 1500) if isinstance(map_def, dict) else 1500

    techniques = collect_keys(report, "techniques", data.get("techniques", []))
    factions = collect_keys(report, "factions", data.get("factions", []))
    cities = collect_keys(report, "cities", data.get("cities", []))
    officers = collect_keys(report, "officers", data.get("officers", []))
    sects = collect_keys(report, "sects", data.get("sects", []))
    events = collect_keys(report, "events", data.get("events", []))

    # ---- Techniques ----
    for key, tech in techniques.items():
        where = "technique '%s'" % key
        check_unknown(report, where, tech, TECHNIQUE_FIELDS)
        check_text(report, where, tech, "name")
        check_text(report, where, tech, "nameZh")
        check_text(report, where, tech, "description", required=False, warn_missing=True)
        if tech.get("kind") not in DUEL_MOVES:
            report.error(where, "kind must be one of %s" % DUEL_MOVES)
        power = check_int(report, where, tech, "power", 100, 400)
        if power is not None and not 140 <= power <= 220:
            report.warn(where, "power %d outside the 140..220 guideline" % power)
        minimum = check_int(report, where, tech, "minMartial", 1, 100)
        if minimum is not None and not 60 <= minimum <= 90:
            report.warn(where, "minMartial %d outside the 60..90 guideline" % minimum)

    # ---- Factions ----
    for key, faction in factions.items():
        where = "faction '%s'" % key
        check_unknown(report, where, faction, FACTION_FIELDS)
        check_text(report, where, faction, "name")
        check_text(report, where, faction, "nameZh")
        check_text(report, where, faction, "glyph")
        if not HEX_COLOR.match(str(faction.get("color", ""))):
            report.error(where, "color must be #RRGGBB")
        ruler = faction.get("ruler")
        if ruler not in officers:
            report.error(where, "unknown ruler '%s'" % ruler)
        capital = faction.get("capital")
        if capital not in cities:
            report.error(where, "unknown capital '%s'" % capital)
        elif cities[capital].get("owner") != key:
            report.error(where, "capital '%s' is not owned by the faction" % capital)

    # ---- Cities ----
    for key, city in cities.items():
        where = "city '%s'" % key
        check_unknown(report, where, city, CITY_FIELDS)
        check_text(report, where, city, "name")
        check_text(report, where, city, "nameZh")
        check_text(report, where, city, "description", required=False, warn_missing=True)
        x = city.get("x")
        y = city.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)) or not (0 <= x <= map_w and 0 <= y <= map_h):
            report.error(where, "position must lie on the map")
        check_int(report, where, city, "size", 1, 3)
        if city.get("terrain") not in TERRAINS:
            report.error(where, "terrain must be one of %s" % TERRAINS)
        owner = city.get("owner")
        if owner is not None and owner not in factions:
            report.error(where, "unknown owner '%s'" % owner)
        for value_field, max_field in (("population", "populationMax"), ("farm", "farmMax"),
                                       ("commerce", "commerceMax"), ("defense", "defenseMax")):
            value = check_int(report, where, city, value_field, 0, None)
            maximum = check_int(report, where, city, max_field, 1, None)
            if value is not None and maximum is not None and value > maximum:
                report.error(where, "%s %d exceeds %s %d" % (value_field, value, max_field, maximum))
        check_int(report, where, city, "order", 0, 100)
        check_int(report, where, city, "training", 0, 100)
        troops = check_int(report, where, city, "troops", 0, None)
        check_int(report, where, city, "gold", 0, None)
        check_int(report, where, city, "food", 0, None)
        if troops is not None:
            is_capital = any(f.get("capital") == key for f in factions.values())
            low, high = (15000, 25000) if is_capital else ((5000, 14000) if owner else (2000, 8000))
            if not low <= troops <= high:
                report.warn(where, "troops %d outside the %d..%d guideline" % (troops, low, high))

    # ---- Roads ----
    pairs = set()
    for index, road in enumerate(data.get("roads", [])):
        where = "road[%d]" % index
        check_unknown(report, where, road, ROAD_FIELDS)
        a, b = road.get("a"), road.get("b")
        if a not in cities or b not in cities:
            report.error(where, "unknown city in '%s'-'%s'" % (a, b))
        if a == b:
            report.error(where, "connects a city to itself")
        pair = frozenset((a, b))
        if pair in pairs:
            report.error(where, "duplicate road %s-%s" % (a, b))
        pairs.add(pair)
        check_int(report, where, road, "days", 1, 60)
        if road.get("kind", "road") not in ROAD_KINDS:
            report.error(where, "kind must be one of %s" % ROAD_KINDS)

    # ---- Officers ----
    portraits_used = {}
    manifest_ids = load_manifest_ids()
    for key, officer in officers.items():
        where = "officer '%s'" % key
        check_unknown(report, where, officer, OFFICER_FIELDS)
        check_text(report, where, officer, "name")
        name_zh = check_text(report, where, officer, "nameZh")
        if name_zh and not CJK_PATTERN.search(name_zh):
            report.error(where, "nameZh must contain Chinese characters")
        check_text(report, where, officer, "epithet", required=False, warn_missing=True)
        check_text(report, where, officer, "bio", required=False, warn_missing=True)
        gender = officer.get("gender", "m")
        if gender not in GENDERS:
            report.error(where, "gender must be one of %s" % GENDERS)
        status = officer.get("status", "free")
        if status not in STATUSES:
            report.error(where, "status must be one of %s" % STATUSES)
        if status in ("free", "hidden", "unborn"):
            check_text(report, where, officer, "rumor", required=False, warn_missing=True)

        portrait = officer.get("portrait")
        if portrait not in PORTRAIT_IDS:
            report.error(where, "portrait '%s' is not a valid portrait id" % portrait)
        else:
            if not portrait.startswith(gender + "_"):
                report.error(where, "portrait '%s' does not match gender '%s'" % (portrait, gender))
            if portrait in portraits_used:
                report.error(where, "portrait '%s' already used by '%s'" % (portrait, portraits_used[portrait]))
            portraits_used[portrait] = key
            if manifest_ids is not None and portrait not in manifest_ids:
                report.warn(where, "portrait '%s' is not listed in the portrait manifest" % portrait)

        stats = [check_int(report, where, officer, stat, 1, 100) for stat in STATS]
        check_int(report, where, officer, "affinity", 0, 149)
        check_int(report, where, officer, "ambition", 0, 100)
        check_int(report, where, officer, "bravery", 0, 100)
        check_int(report, where, officer, "loyalty", 0, 100, required=False)
        check_int(report, where, officer, "merit", 0, None, required=False)
        if officer.get("specialty", "infantry") not in TROOP_TYPES:
            report.error(where, "specialty must be one of %s" % TROOP_TYPES)

        birth = check_int(report, where, officer, "birth", None, None)
        appear = check_int(report, where, officer, "appear", 0, None, required=False) or 0
        if birth is not None:
            if status == "unborn":
                if appear <= start_year:
                    report.error(where, "unborn officers need appear > startYear (%d)" % start_year)
                elif appear - birth < 15:
                    report.warn(where, "only %d years old when appearing in %d" % (appear - birth, appear))
            else:
                age = start_year - birth
                if not 17 <= age <= 70:
                    report.warn(where, "age %d at scenario start outside 17..70" % age)
                if appear:
                    report.warn(where, "'appear' is only meaningful for unborn officers")

        faction = officer.get("faction")
        city = officer.get("city")
        captor = officer.get("captor")
        if faction is not None and faction not in factions:
            report.error(where, "unknown faction '%s'" % faction)
        if captor is not None and captor not in factions:
            report.error(where, "unknown captor '%s'" % captor)
        if city is not None and city not in cities:
            report.error(where, "unknown city '%s'" % city)
        if status == "serving":
            if faction is None:
                report.error(where, "serving officers need a faction")
            if city is None and officer.get("army") is None:
                report.error(where, "serving officers need a city")
            elif city in cities and faction in factions and cities[city].get("owner") != faction:
                report.error(where, "serves '%s' but sits in '%s' owned by '%s'" % (faction, city, cities[city].get("owner")))
            if officer.get("loyalty") is None:
                report.warn(where, "serving officer without explicit loyalty")
        elif status == "prisoner":
            if captor is None or city is None:
                report.error(where, "prisoners need a captor and a city")
            elif city in cities and cities[city].get("owner") != captor:
                report.error(where, "held in '%s' which is not owned by captor '%s'" % (city, captor))
            if captor is not None and captor == faction:
                report.error(where, "captor equals own faction")
        elif status in ("free", "hidden", "unborn"):
            if city is None:
                report.error(where, "%s officers need a city" % status)
            if faction is not None:
                report.error(where, "%s officers must not have a faction" % status)
        sect = officer.get("sect")
        if sect is not None and sect not in sects:
            report.error(where, "unknown sect '%s'" % sect)
        known = officer.get("techniques", [])
        if not isinstance(known, list):
            report.error(where, "techniques must be an array")
            known = []
        if len(set(known)) != len(known):
            report.error(where, "duplicate techniques")
        for tech_key in known:
            if tech_key not in techniques:
                report.error(where, "unknown technique '%s'" % tech_key)
            elif stats[0] is not None and stats[0] < techniques[tech_key].get("minMartial", 0):
                report.warn(where, "martial %d below minMartial %d of '%s'" % (stats[0], techniques[tech_key]["minMartial"], tech_key))

    # ---- Rulers and garrisons ----
    for key, faction in factions.items():
        where = "faction '%s'" % key
        ruler = officers.get(faction.get("ruler"))
        if ruler is not None:
            if ruler.get("status") != "serving" or ruler.get("faction") != key:
                report.error(where, "ruler '%s' must serve the faction" % faction["ruler"])
            elif cities.get(ruler.get("city"), {}).get("owner") != key:
                report.error(where, "ruler '%s' must sit in a city of the faction" % faction["ruler"])
            if ruler.get("loyalty", 100) != 100:
                report.warn(where, "ruler loyalty should be 100")
        serving = [o for o in officers.values() if o.get("status") == "serving" and o.get("faction") == key]
        for city_key, city in cities.items():
            if city.get("owner") != key:
                continue
            here = [o for o in serving if o.get("city") == city_key]
            if not here:
                report.error(where, "city '%s' has no serving officer" % city_key)
            if faction.get("capital") == city_key and len(here) < 3:
                report.warn(where, "capital '%s' has only %d officers" % (city_key, len(here)))
        if not 8 <= len(serving) <= 12:
            report.warn(where, "%d serving officers (guideline: ruler + 7..11)" % len(serving))
        affinity = ruler.get("affinity") if ruler else None
        if is_int(affinity):
            for officer in serving:
                distance = abs(officer.get("affinity", 75) - affinity)
                distance = min(distance, 150 - distance)
                if distance > 25:
                    report.warn(where, "officer '%s' affinity is %d away from the ruler" % (officer["key"], distance))

    # ---- Sects ----
    for key, sect in sects.items():
        where = "sect '%s'" % key
        check_unknown(report, where, sect, SECT_FIELDS)
        check_text(report, where, sect, "name")
        check_text(report, where, sect, "nameZh")
        check_text(report, where, sect, "description", required=False, warn_missing=True)
        city = sect.get("city")
        if city not in cities:
            report.error(where, "unknown city '%s'" % city)
        master_key = sect.get("master")
        master = officers.get(master_key)
        if master is None:
            report.error(where, "unknown master '%s'" % master_key)
        else:
            if master.get("status") != "free":
                report.error(where, "master '%s' must be free" % master_key)
            if master.get("city") != city:
                report.error(where, "master '%s' must live in the sect city" % master_key)
            if master.get("sect") != key:
                report.error(where, "master '%s' must have sect '%s'" % (master_key, key))
        sect_techniques = sect.get("techniques", [])
        for tech_key in sect_techniques:
            if tech_key not in techniques:
                report.error(where, "unknown technique '%s'" % tech_key)
        if not 3 <= len(sect_techniques) <= 4:
            report.warn(where, "%d techniques (guideline 3..4)" % len(sect_techniques))
        favor = sect.get("favor", {})
        if not isinstance(favor, dict):
            report.error(where, "favor must be an object")
            favor = {}
        for faction_key, value in favor.items():
            if faction_key not in factions:
                report.error(where, "unknown faction '%s' in favor" % faction_key)
            if not is_int(value) or not 0 <= value <= 100:
                report.error(where, "favor for '%s' must be 0..100" % faction_key)
            elif value > 30:
                report.warn(where, "starting favor %d for '%s' above the 0..30 guideline" % (value, faction_key))

    # ---- Relations ----
    relation_pairs = set()
    for index, relation in enumerate(data.get("relations", [])):
        where = "relation[%d]" % index
        check_unknown(report, where, relation, RELATION_FIELDS)
        a, b = relation.get("a"), relation.get("b")
        if a not in factions or b not in factions or a == b:
            report.error(where, "needs two different known factions ('%s', '%s')" % (a, b))
            continue
        pair = frozenset((a, b))
        if pair in relation_pairs:
            report.error(where, "duplicate relation %s-%s" % (a, b))
        relation_pairs.add(pair)
        check_int(report, where, relation, "trust", 0, 100, required=False)
        check_int(report, where, relation, "alliance", 0, None, required=False)
        check_int(report, where, relation, "truce", 0, None, required=False)

    # ---- Events ----
    for key, event in events.items():
        validate_event(report, key, event, cities, officers, factions, sects, techniques)

    if summary:
        print_summary(data, officers, factions, cities)


def validate_event(report, key, event, cities, officers, factions, sects, techniques):
    where = "event '%s'" % key
    check_unknown(report, where, event, EVENT_FIELDS)
    check_text(report, where, event, "title")
    text = check_text(report, where, event, "text")
    check_placeholders(report, where, text)
    image = event.get("image")
    if image not in EVENT_IMAGES:
        report.error(where, "image '%s' is not an event illustration" % image)
    world = event.get("world", False)
    if not isinstance(world, bool):
        report.error(where, "world must be true/false")
    if not isinstance(event.get("once", True), bool):
        report.error(where, "once must be true/false")
    speaker = event.get("speaker", "advisor")
    if speaker != "advisor" and speaker not in officers:
        report.error(where, "unknown speaker '%s'" % speaker)
    context = event.get("context", "random_city" if world else "random_player_city")
    if context not in EVENT_CONTEXTS and context not in cities:
        report.error(where, "context '%s' is not a context keyword or city" % context)
    if world and context in ("random_player_city", "capital"):
        report.warn(where, "world event with player context '%s'" % context)

    when = event.get("when", {})
    if not isinstance(when, dict):
        report.error(where, "when must be an object")
        when = {}
    check_unknown(report, where + " when", when, WHEN_FIELDS)
    for field in ("minYear", "maxYear", "minCities", "maxCities"):
        check_int(report, where + " when", when, field, 0, None, required=False)
    if is_int(when.get("minYear")) and is_int(when.get("maxYear")) and when["minYear"] > when["maxYear"]:
        report.error(where, "minYear > maxYear")
    check_int(report, where + " when", when, "chance", 0, 100, required=False)
    for month in when.get("months", []):
        if not is_int(month) or not 1 <= month <= 12:
            report.error(where, "month %r outside 1..12" % (month,))
    if "ownsCity" in when and when["ownsCity"] not in cities:
        report.error(where, "unknown ownsCity '%s'" % when["ownsCity"])
    if "hasOfficer" in when and when["hasOfficer"] not in officers:
        report.error(where, "unknown hasOfficer '%s'" % when["hasOfficer"])
    when_faction = when.get("faction")
    if when_faction is not None and when_faction not in factions:
        report.error(where, "unknown faction '%s'" % when_faction)
    if world and any(f in when for f in ("ownsCity", "hasOfficer", "faction")):
        report.warn(where, "player conditions on a world event")
    if speaker in officers and when.get("hasOfficer") != speaker and speaker != "advisor":
        speaker_faction = officers[speaker].get("faction")
        if when_faction is not None and speaker_faction == when_faction and \
                factions.get(when_faction, {}).get("ruler") != speaker:
            report.warn(where, "speaker '%s' serves the player but is not guarded by when.hasOfficer" % speaker)

    effects = event.get("effects", [])
    choices = event.get("choices", [])
    if world:
        if not effects:
            report.error(where, "world events need effects")
        if choices:
            report.error(where, "world events cannot have choices")
    else:
        if not 2 <= len(choices) <= 3:
            report.warn(where, "%d choices (guideline 2..3)" % len(choices))
        if not choices and not effects:
            report.error(where, "player events need choices or effects")
    for index, effect in enumerate(effects):
        validate_effect(report, "%s effect[%d]" % (where, index), effect, world, when_faction,
                        cities, officers, factions, sects, techniques)
    for choice_index, choice in enumerate(choices):
        choice_where = "%s choice[%d]" % (where, choice_index)
        check_unknown(report, choice_where, choice, CHOICE_FIELDS)
        check_text(report, choice_where, choice, "label")
        gold = check_int(report, choice_where, choice, "gold", 0, None, required=False) or 0
        choice_effects = choice.get("effects", [])
        if not choice_effects:
            report.warn(choice_where, "choice has no effects")
        for index, effect in enumerate(choice_effects):
            validate_effect(report, "%s effect[%d]" % (choice_where, index), effect, world, when_faction,
                            cities, officers, factions, sects, techniques)
        if gold > 0:
            spent = [e for e in choice_effects if e.get("type") == "gold" and e.get("city") == "context"]
            if not any(e.get("amount") == -gold for e in spent):
                report.error(choice_where, "requires %d gold but has no matching gold effect of -%d on the context city" % (gold, gold))
        for effect in choice_effects:
            if effect.get("type") == "gold" and is_int(effect.get("amount")) and effect["amount"] < 0 \
                    and effect.get("city") == "context" and gold < -effect["amount"]:
                report.error(choice_where, "spends %d gold but only requires %d" % (-effect["amount"], gold))


def validate_effect(report, where, effect, world, when_faction, cities, officers, factions, sects, techniques):
    check_unknown(report, where, effect, EFFECT_FIELDS)
    kind = effect.get("type")
    if kind not in EFFECT_TYPES:
        report.error(where, "unknown effect type '%s'" % kind)
        return

    def need_city():
        city = effect.get("city")
        if city is None:
            report.error(where, "'%s' needs a city" % kind)
        elif city not in ("context", "capital") and city not in cities:
            report.error(where, "unknown city '%s'" % city)
        elif world and city == "capital":
            report.warn(where, "'capital' in a world event")

    def need_officer(allow_refs=True):
        officer = effect.get("officer")
        if officer is None:
            report.error(where, "'%s' needs an officer" % kind)
        elif officer in ("context", "ruler"):
            if not allow_refs:
                report.error(where, "'%s' needs an explicit officer key" % kind)
        elif officer not in officers:
            report.error(where, "unknown officer '%s'" % officer)
        return officers.get(officer)

    def need_faction(allow_player=True):
        faction = effect.get("faction")
        if faction is None:
            report.error(where, "'%s' needs a faction" % kind)
        elif faction in ("player", "context"):
            if not allow_player:
                report.error(where, "'%s' needs another faction's key (relations are with the player)" % kind)
        elif faction not in factions:
            report.error(where, "unknown faction '%s'" % faction)
        elif when_faction is not None and faction == when_faction and not allow_player:
            report.error(where, "'%s' targets the player's own faction" % kind)
        elif when_faction is None and not allow_player and not world:
            report.warn(where, "'%s' with '%s' fires even when the player is that faction" % (kind, faction))

    def need_amount(nonzero=True, positive=False):
        amount = effect.get("amount")
        if not is_int(amount):
            report.error(where, "'%s' needs an integer amount" % kind)
        elif positive and amount <= 0:
            report.error(where, "'%s' amount must be positive" % kind)
        elif nonzero and amount == 0:
            report.warn(where, "'%s' amount is 0" % kind)

    if kind in CITY_EFFECTS:
        need_city()
        need_amount()
    elif kind == "loyalty":
        need_officer()
        need_amount()
    elif kind == "loyaltyAll":
        need_faction()
        need_amount()
    elif kind == "stat":
        need_officer()
        if effect.get("stat") not in STATS:
            report.error(where, "stat must be one of %s" % STATS)
        need_amount()
    elif kind == "joinOfficer":
        officer = need_officer(allow_refs=False)
        need_faction()
        need_city()
        if officer is not None and officer.get("status") == "serving":
            report.warn(where, "joinOfficer on '%s' who starts serving another faction" % effect.get("officer"))
    elif kind == "revealOfficer":
        officer = need_officer(allow_refs=False)
        need_city()
        if officer is not None and officer.get("status") not in ("hidden", "unborn"):
            report.error(where, "revealOfficer needs a hidden or unborn officer, '%s' is %s" % (effect.get("officer"), officer.get("status")))
    elif kind == "trust":
        need_faction(allow_player=False)
        need_amount()
    elif kind in ("alliance", "truce"):
        need_faction(allow_player=False)
        need_amount(positive=True)
    elif kind == "sectFavor":
        if effect.get("sect") not in sects:
            report.error(where, "unknown sect '%s'" % effect.get("sect"))
        need_amount()
    elif kind == "learnTechnique":
        officer = need_officer()
        tech_key = effect.get("technique")
        if tech_key not in techniques:
            report.error(where, "unknown technique '%s'" % tech_key)
        elif officer is not None and officer.get("martial", 0) < techniques[tech_key].get("minMartial", 0):
            report.warn(where, "'%s' lacks the martial for '%s'" % (effect.get("officer"), tech_key))
    elif kind == "message":
        check_text(report, where, effect, "text")
    if "text" in effect:
        check_placeholders(report, where, effect.get("text"))
    if "stat" in effect and kind != "stat":
        report.warn(where, "'stat' is ignored for '%s'" % kind)


def load_manifest_ids():
    path = os.path.join(DATA_DIR, "Art", "Portraits", "manifest.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, ValueError):
        return None
    ids = set()

    def walk(node):
        if isinstance(node, dict):
            for field in ("id", "key", "portrait"):
                if isinstance(node.get(field), str):
                    ids.add(node[field])
            for name, value in node.items():
                if name in PORTRAIT_IDS:
                    ids.add(name)
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(manifest)
    return ids & PORTRAIT_IDS or None


def print_summary(data, officers, factions, cities):
    print("  techniques %d, sects %d, events %d (%d world), relations %d" % (
        len(data.get("techniques", [])), len(data.get("sects", [])), len(data.get("events", [])),
        sum(1 for e in data.get("events", []) if e.get("world")), len(data.get("relations", []))))
    statuses = {}
    for officer in officers.values():
        statuses[officer.get("status")] = statuses.get(officer.get("status"), 0) + 1
    print("  officers %d: %s" % (len(officers), ", ".join("%s %d" % item for item in sorted(statuses.items()))))
    for key in factions:
        serving = [o for o in officers.values() if o.get("status") == "serving" and o.get("faction") == key]
        owned = [c for c, city in cities.items() if city.get("owner") == key]
        troops = sum(cities[c].get("troops", 0) for c in owned)
        best = [max(o.get(s, 0) for o in serving) for s in STATS] if serving else [0] * 5
        print("  %-15s officers %2d  cities %d  troops %6d  best M/C/S/P/Ch %s" % (
            key, len(serving), len(owned), troops, "/".join(str(v) for v in best)))
    legends = sorted((o["key"], s, o[s]) for o in officers.values() for s in STATS if o.get(s, 0) >= 90)
    names = sorted({k for k, _, _ in legends})
    print("  officers with a 90+ stat: %d (%s)" % (len(names), ", ".join("%s %s %d" % item for item in legends)))


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    unknown = flags - {"--strict", "--summary"}
    if unknown:
        print("unknown option(s): %s" % ", ".join(sorted(unknown)))
        return 2
    paths = args or sorted(glob.glob(os.path.join(DATA_DIR, "Scenarios", "*.json")))
    if not paths:
        print("no scenario files found")
        return 2
    failed = False
    for path in paths:
        report = Report(path)
        print("%s" % os.path.relpath(path, ROOT))
        validate(path, report, "--summary" in flags)
        for message in report.errors:
            print("  ERROR   %s" % message)
        for message in report.warnings:
            print("  warning %s" % message)
        print("  %d error(s), %d warning(s)" % (len(report.errors), len(report.warnings)))
        if report.errors or ("--strict" in flags and report.warnings):
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
