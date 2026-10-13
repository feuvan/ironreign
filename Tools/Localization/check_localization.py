#!/usr/bin/env python3
"""Verifies the string tables of every culture.

Fails when a culture misses a key of the English tables, when placeholders ({city}...) differ from
English, or when the English tables are stale compared with the code/scenarios (run extract_strings.py).
With --warn-missing, keys missing from a culture are reported as warnings instead of errors (used while a
translation pass is still in progress).
"""
import sys

from loclib import LOC_DIR, SCENARIO_DIR, TARGET_CULTURES, load_json, placeholders, scan_source_strings, scenario_strings


def main() -> int:
    warn_missing = "--warn-missing" in sys.argv[1:]
    errors, warnings = [], []
    en_dir = LOC_DIR / "en"
    if not en_dir.exists():
        print("error: Content/Data/Localization/en is missing; run Tools/Localization/extract_strings.py")
        return 1

    code_strings, conflicts = scan_source_strings()
    errors += [f"conflicting defaults: {c}" for c in conflicts]
    en_strings = load_json(en_dir / "Strings.json") if (en_dir / "Strings.json").exists() else {}
    if en_strings != code_strings:
        stale = set(code_strings) ^ set(en_strings)
        changed = [k for k in code_strings if k in en_strings and en_strings[k] != code_strings[k]]
        errors.append(f"en/Strings.json is stale ({len(stale)} added/removed, {len(changed)} changed); run extract_strings.py")

    tables = {"Strings.json": en_strings}
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        scenario = load_json(path)
        name = f"Scenario_{scenario.get('key', path.stem)}.json"
        expected = scenario_strings(scenario)
        on_disk = load_json(en_dir / name) if (en_dir / name).exists() else {}
        if on_disk != expected:
            errors.append(f"en/{name} is stale; run extract_strings.py")
        tables[name] = expected

    english_union = {}
    for table in tables.values():
        english_union.update(table)
    for culture in TARGET_CULTURES:
        # A culture may split its translations over several files; the game loads every .json in the folder.
        translated = {}
        folder = LOC_DIR / culture
        for path in sorted(folder.glob("*.json")) if folder.exists() else []:
            for key, text in load_json(path).items():
                if key in translated and translated[key] != text:
                    errors.append(f"{culture}/{path.name}: '{key}' is defined twice with different text")
                translated[key] = text
        missing = [k for k in english_union if not translated.get(k)]
        report = warnings if warn_missing else errors
        for key in missing[:8]:
            report.append(f"{culture}: missing '{key}'")
        if len(missing) > 8:
            report.append(f"{culture}: ... {len(missing) - 8} more missing keys")
        for key, text in translated.items():
            if key not in english_union:
                warnings.append(f"{culture}: unused key '{key}'")
            elif placeholders(text) != placeholders(english_union[key]):
                errors.append(f"{culture}: placeholders differ for '{key}': {sorted(placeholders(text))} vs {sorted(placeholders(english_union[key]))}")
        print(f"{culture}: {len(translated)} translated, {len(missing)} missing")

    for message in warnings[:20]:
        print(f"warning: {message}")
    for message in errors:
        print(f"error: {message}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
