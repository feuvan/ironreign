#!/usr/bin/env python3
"""Verifies the string tables of every culture.

Fails when a culture misses a key of the English tables, when placeholders ({city}...) differ from
English, or when the English tables are stale compared with the code/scenarios (run extract_strings.py).
"""
import sys

from loclib import LOC_DIR, SCENARIO_DIR, TARGET_CULTURES, load_json, placeholders, scan_source_strings, scenario_strings


def main() -> int:
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

    for culture in TARGET_CULTURES:
        missing_total = 0
        for name, english in tables.items():
            path = LOC_DIR / culture / name
            translated = load_json(path) if path.exists() else {}
            missing = [k for k in english if not translated.get(k)]
            missing_total += len(missing)
            for key in missing[:5]:
                errors.append(f"{culture}/{name}: missing '{key}'")
            if len(missing) > 5:
                errors.append(f"{culture}/{name}: ... {len(missing) - 5} more missing keys")
            for key, text in translated.items():
                if key not in english:
                    warnings.append(f"{culture}/{name}: unused key '{key}'")
                elif placeholders(text) != placeholders(english[key]):
                    errors.append(f"{culture}/{name}: placeholders differ for '{key}': {sorted(placeholders(text))} vs {sorted(placeholders(english[key]))}")
        print(f"{culture}: {missing_total} missing")

    for message in warnings[:20]:
        print(f"warning: {message}")
    for message in errors:
        print(f"error: {message}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
