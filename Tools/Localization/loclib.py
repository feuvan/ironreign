"""Shared helpers for the Iron Reign localization tools."""
import collections
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "Source" / "IronReign"
DATA_DIR = ROOT / "Content" / "Data"
LOC_DIR = DATA_DIR / "Localization"
SCENARIO_DIR = DATA_DIR / "Scenarios"
CULTURES = ["en", "zh-Hans", "zh-Hant", "ja", "ko"]
TARGET_CULTURES = [c for c in CULTURES if c != "en"]

# Loc("key", "default") / LocF("key", "default", {...}) in Sim/ and IronUI::Loc/LocF in UI/.
_LITERAL = r'"((?:[^"\\]|\\.)*)"'
LOC_CALL = re.compile(r'\bLocF?\s*\(\s*' + _LITERAL + r'\s*,\s*' + _LITERAL)
PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"', "'": "'", "r": "\r", "0": "\0"}


def unescape_cpp(literal: str) -> str:
    out = []
    i = 0
    while i < len(literal):
        c = literal[i]
        if c == "\\" and i + 1 < len(literal):
            out.append(_ESCAPES.get(literal[i + 1], literal[i + 1]))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def strip_comments(text: str) -> str:
    """Blanks out // and /* */ comments (keeping newlines and string/char literals) so examples in docs are ignored."""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            quote, j = c, i + 1
            while j < n and text[j] != quote:
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("\n" * text.count("\n", i, j))
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def scan_source_strings():
    """Returns ({key: default}, [conflict messages])."""
    strings, origins, conflicts = {}, {}, []
    for path in sorted(SOURCE_DIR.rglob("*")):
        if path.suffix not in (".cpp", ".h"):
            continue
        text = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        for match in LOC_CALL.finditer(text):
            key, default = match.group(1), unescape_cpp(match.group(2))
            where = f"{path.relative_to(ROOT)}:{text.count(chr(10), 0, match.start()) + 1}"
            if key in strings and strings[key] != default:
                conflicts.append(f"{key}: '{strings[key]}' ({origins[key]}) vs '{default}' ({where})")
                continue
            strings[key] = default
            origins.setdefault(key, where)
    return strings, conflicts


def scenario_strings(scenario: dict) -> dict:
    """Mirror of IronSim::ExtractScenarioStrings (Sim/IronLocale.cpp) plus banner glyphs."""
    table = {}

    def add(key, value):
        if value:
            table[key] = value

    skey = scenario.get("key", "scenario")
    add(f"scenario.{skey}.name", scenario.get("name"))
    add(f"scenario.{skey}.description", scenario.get("description"))
    for i, label in enumerate(scenario.get("map", {}).get("labels", [])):
        add(f"scenario.{skey}.label.{i}", label.get("text"))
    for f in scenario.get("factions", []):
        add(f"faction.{f['key']}.name", f.get("name"))
        add(f"faction.{f['key']}.glyph", f.get("glyph"))
    for c in scenario.get("cities", []):
        add(f"city.{c['key']}.name", c.get("name"))
        add(f"city.{c['key']}.description", c.get("description"))
    for o in scenario.get("officers", []):
        for field in ("name", "epithet", "bio", "rumor"):
            add(f"officer.{o['key']}.{field}", o.get(field))
    for t in scenario.get("techniques", []):
        add(f"technique.{t['key']}.name", t.get("name"))
        add(f"technique.{t['key']}.description", t.get("description"))
    for s in scenario.get("sects", []):
        add(f"sect.{s['key']}.name", s.get("name"))
        add(f"sect.{s['key']}.description", s.get("description"))
    for e in scenario.get("events", []):
        add(f"event.{e['key']}.title", e.get("title"))
        add(f"event.{e['key']}.text", e.get("text"))
        for j, effect in enumerate(e.get("effects", [])):
            add(f"event.{e['key']}.effect.{j}", effect.get("text"))
        for i, choice in enumerate(e.get("choices", [])):
            add(f"event.{e['key']}.choice.{i}", choice.get("label"))
            for j, effect in enumerate(choice.get("effects", [])):
                add(f"event.{e['key']}.choice.{i}.effect.{j}", effect.get("text"))
    return table


def load_json(path: pathlib.Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load_json_with_duplicates(path: pathlib.Path):
    """Returns (data, [keys defined more than once in the same object]); json.load silently keeps the last value."""
    duplicates = []

    def pairs_hook(pairs):
        seen = set()
        for key, _ in pairs:
            if key in seen:
                duplicates.append(key)
            seen.add(key)
        return dict(pairs)

    with open(path, encoding="utf-8") as handle:
        return json.load(handle, object_pairs_hook=pairs_hook), duplicates


def save_json(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def placeholders(text: str) -> set:
    return set(PLACEHOLDER.findall(text or ""))


def placeholder_counts(text: str) -> collections.Counter:
    """Multiset of placeholders: translations must keep each placeholder as many times as English does."""
    return collections.Counter(PLACEHOLDER.findall(text or ""))
